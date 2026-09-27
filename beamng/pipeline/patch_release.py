"""Apply the road fixes of v1.1 to a built level (the v1.0 release zip), without the source data.

The level build (build_level.py) needs the DTM, the cadastral survey and the photos, which are not
in the repository. This script repairs a built level with what the level itself contains, and
with the light results in ../dati (road_profile.npz, trees/understory/photo shrubs):
- paved polygons: the road meshes (triangles of one polygon share vertices; pieces of a polygon
  cut by the 128 m chunks are joined again), their heights are the v1.0 surface (the DTM);
- surfaces: surface_fit.fit, as roadheight.py does on the DTM (stiffer on the carriageway of
  road_profile.npz);
- road meshes: meshed again like build_level.stage_roads (same pieces, materials, UV scale;
  skirts down to the ground or to the next surface, stone faces under bridges and at steps);
- everything placed on the old road surface moves with it (height change of the surface at the
  nearest paved point, fading out 2-4 m from the paved areas): markings, AI roads, street
  lights, poles, signs, furniture, guardrails; the main AI route keeps to one surface;
- terrain: carved again 0.1 m under the lowest paved surface within 0.7 m;
- vegetation: clearance.clear_paved (trees off the paved surfaces, shrubs and hedges moved back
  from the edges or dropped), with the model sizes of the vanilla shapes.
Walls and fences are left as they are.
Usage: python patch_release.py magliaso_pura_v1.0.zip magliaso_pura_v1.1.zip
"""
import json, os, re, shutil, sys, tempfile, time, zipfile
import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.ndimage import map_coordinates
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from rasterio import features
from rasterio.transform import Affine
import bng
import clearance
import road_mesh
import surface_fit

HERE = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(os.path.dirname(HERE), "dati")
LEVEL = "levels/magliaso_pura"
L = "/" + LEVEL
RES = 0.5
CHUNK = 128.0
# material: (mesh cell m, uv tile m) as build_level.ROAD_CLASSES
MATS = {"mp_road_asphalt": (1.0, 1.25), "mp_road_asphalt_fresh": (1.0, 1.25), "mp_hard_asphalt": (2.0, 1.25),
        "mp_sidewalk": (1.0, 1.25), "mp_island": (1.0, 2.5)}
# vanilla vegetation shapes: height (m, recovered from the measured heights and the scales of
# v1.0), width (m, x / y extent). Shrubs about as wide as 0.8 x their height; the hedge is 3 m long.
VEG = {"cypress_hedge_3m": ("hedge", 1.69, 3.0, 1.2), "fluffy_bush": ("bush", 2.41, 1.9, 1.9),
       "generibush": ("bush", 1.90, 1.5, 1.5), "tree_beech_bush_c": ("bush", 3.79, 3.0, 3.0),
       "tree_beech_bush_e": ("bush", 6.60, 5.3, 5.3), "tree_oak_bush_b": ("bush", 4.08, 3.3, 3.3)}


# ------------------------------------------------------------------ COLLADA of the pipeline
def read_dae(path):
    s = open(path, encoding="utf-8").read()

    def arr(i):
        m = re.search(r'<float_array id="%s" count="\d+">([^<]*)</float_array>' % i, s)
        return np.array(m.group(1).split(), np.float64) if m else None
    V = arr("g-pa").reshape(-1, 3)
    N = arr("g-na").reshape(-1, 3)
    T = arr("g-ta").reshape(-1, 2)
    C = arr("g-ca")
    C = C.reshape(-1, 4) if C is not None else None
    parts = []
    for m in re.finditer(r'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', s):
        nin = m.group(2).count("<input")
        idx = np.array(m.group(3).split(), np.int64).reshape(-1, nin)
        parts.append((m.group(1), idx))
    return V, N, T, C, parts


def rewrite_dae(path, name, origin, fn):
    """Read a pipeline DAE, move its vertices (world coordinates) with fn(V) -> V, write it back."""
    V, N, T, C, parts = read_dae(path)
    o = np.asarray(origin, np.float64)
    Vw = fn(V + o)
    mb = bng.MeshBuilder()
    for mat, idx in parts:
        vi, ni, ti = idx[:, 0], idx[:, 1], idx[:, 2]
        cols = C[idx[:, 3]] if (C is not None and idx.shape[1] > 3) else None
        mb.add(mat, Vw[vi], uvs=T[ti], normals=N[ni], colors=cols)
    mb.write_dae(path, name=name, origin=o)


def items(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def write_items(path, objs):
    with open(path, "w", encoding="utf-8") as f:
        for o in objs:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")


# ------------------------------------------------------------------ paved polygons from the meshes
def road_pieces(lv):
    """Top faces of every road mesh, one piece per connected surface of a material in a chunk;
    pieces of one polygon cut by chunk lines get the same polygon id."""
    pieces = []
    for it in items(os.path.join(lv, "main", "MissionGroup", "roads", "surfaces", "items.level.json")):
        path = os.path.join(lv, it["shapeName"].replace(L + "/", ""))
        V, N, T, C, parts = read_dae(path)
        Vw = V + np.array(it["position"])
        for mat, idx in parts:
            tri_idx = idx[:, 0].reshape(-1, 3)
            tri = Vw[tri_idx]
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            top = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.2
            ti = tri_idx[top]
            if not len(ti):
                continue
            k = len(ti)
            A = coo_matrix((np.ones(3 * k), (np.repeat(np.arange(k), 3), ti.ravel())), shape=(k, len(V))).tocsr()
            nc, lab = connected_components(A @ A.T, directed=False)
            for c in range(nc):
                pieces.append({"mat": mat, "tri": Vw[ti[lab == c]], "shape": it["shapeName"],
                               "pos": it["position"]})
    parent = list(range(len(pieces)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    first = {}
    for i, pc in enumerate(pieces):
        v = pc["tri"].reshape(-1, 3)
        on = (np.abs(v[:, 0] / CHUNK - np.round(v[:, 0] / CHUNK)) < 1e-4) | \
             (np.abs(v[:, 1] / CHUNK - np.round(v[:, 1] / CHUNK)) < 1e-4)
        kind = "road" if pc["mat"].startswith("mp_road_asphalt") else pc["mat"]
        for q in {tuple(np.round(x[:2], 2)) for x in v[on]}:
            j = first.setdefault((kind, q), i)
            if find(i) != find(j):
                parent[find(i)] = find(j)
    ids = {r: k for k, r in enumerate(sorted({find(i) for i in range(len(pieces))}))}
    for i, pc in enumerate(pieces):
        pc["poly"] = ids[find(i)]
        pc["geom"] = shapely.union_all(shapely.polygons(pc["tri"][:, :, :2]), grid_size=1e-4)
    return pieces


def raster_heights(tri, x_min, y_max, shape):
    """Height of the triangles (k,3,3) at the cell centres of a north-up raster (NaN elsewhere)."""
    H, W = shape
    out = np.full(shape, np.nan)
    A, B, Cc = tri[:, 0], tri[:, 1], tri[:, 2]
    lo = np.minimum(np.minimum(A, B), Cc)
    hi = np.maximum(np.maximum(A, B), Cc)
    c0 = np.ceil((lo[:, 0] - x_min) / RES - 0.5).astype(int)
    c1 = np.floor((hi[:, 0] - x_min) / RES - 0.5).astype(int)
    r0 = np.ceil((y_max - hi[:, 1]) / RES - 0.5).astype(int)
    r1 = np.floor((y_max - lo[:, 1]) / RES - 0.5).astype(int)
    nc_, nr_ = np.maximum(c1 - c0 + 1, 0), np.maximum(r1 - r0 + 1, 0)
    for w, h in set(zip(nc_.tolist(), nr_.tolist())):
        if w == 0 or h == 0:
            continue
        sel = np.where((nc_ == w) & (nr_ == h))[0]
        dc, dr = np.meshgrid(np.arange(w), np.arange(h))
        cc = c0[sel][:, None] + dc.ravel()[None]
        rr = r0[sel][:, None] + dr.ravel()[None]
        px = x_min + (cc + 0.5) * RES
        py = y_max - (rr + 0.5) * RES
        a, b, c = A[sel], B[sel], Cc[sel]
        v0 = b[:, :2] - a[:, :2]; v1 = c[:, :2] - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        qx, qy = px - a[:, 0:1], py - a[:, 1:2]
        l1 = (qx * v1[:, 1:2] - v1[:, 0:1] * qy) / den[:, None]
        l2 = (v0[:, 0:1] * qy - qx * v0[:, 1:2]) / den[:, None]
        l0 = 1 - l1 - l2
        ins = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & ok[:, None] & (cc >= 0) & (cc < W) & (rr >= 0) & (rr < H)
        z = l0 * a[:, 2:3] + l1 * b[:, 2:3] + l2 * c[:, 2:3]
        out[rr[ins], cc[ins]] = z[ins]
    return out


def raster_free_heights(tri, V2):
    """Heights of the points V2 on the triangles tri (k,3,3) they are vertices of."""
    P = tri.reshape(-1, 3)
    key = {tuple(np.round(q[:2] / 0.002).astype(np.int64)): q[2] for q in P}
    return np.array([key.get(tuple(np.round(v / 0.002).astype(np.int64)), P[:, 2].mean()) for v in V2])


# ------------------------------------------------------------------ terrain
class Terrain:
    def __init__(self, lv):
        self.path = os.path.join(lv, "theTerrain.ter")
        blk = [o for o in items(os.path.join(lv, "main", "MissionGroup", "level_objects", "terrain", "items.level.json"))
               if o.get("class") == "TerrainBlock"][0]
        self.x0, self.y0, self.z0 = blk["position"]
        self.maxh = float(blk["maxHeight"])
        self.sq = float(blk.get("squareSize", 1))
        raw = open(self.path, "rb").read()
        self.n = int(np.frombuffer(raw[1:5], "<u4")[0])
        n2 = self.n * self.n
        self.head, self.tail = raw[:5], raw[5 + 2 * n2:]
        self.q = np.frombuffer(raw[5:5 + 2 * n2], "<u2").reshape(self.n, self.n).copy()   # row 0 = south
        self.h = self.z0 + self.q.astype(np.float64) / 65535.0 * self.maxh

    def sample(self, x, y):
        c = (np.asarray(x) - self.x0) / self.sq
        r = (np.asarray(y) - self.y0) / self.sq
        return map_coordinates(self.h, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")

    def set(self, mask, heights):
        self.h[mask] = heights
        self.q[mask] = np.clip(np.round((heights - self.z0) / self.maxh * 65535.0), 0, 65535).astype("<u2")

    def save(self):
        with open(self.path, "wb") as f:
            f.write(self.head)
            f.write(self.q.astype("<u2").tobytes())
            f.write(self.tail)


# ------------------------------------------------------------------ main
def main(src, dst):
    t0 = time.time()
    work = tempfile.mkdtemp(prefix="magliaso_patch_")
    with zipfile.ZipFile(src) as z:
        z.extractall(work)
    lv = os.path.join(work, LEVEL)
    names_before = sorted(os.path.relpath(os.path.join(dp, f), work) for dp, _, fs in os.walk(work) for f in fs)
    # 1. paved polygons and the v1.0 surface
    pieces = road_pieces(lv)
    allv = np.concatenate([p["tri"].reshape(-1, 3) for p in pieces])
    x_min = np.floor(allv[:, 0].min()) - 10
    y_max = np.ceil(allv[:, 1].max()) + 10
    shape = (int((y_max - np.floor(allv[:, 1].min()) + 10) / RES), int((np.ceil(allv[:, 0].max()) + 10 - x_min) / RES))
    tr = Affine(RES, 0, x_min, 0, -RES, y_max)
    owner = features.rasterize([(p["geom"], p["poly"]) for p in pieces], out_shape=shape, transform=tr, fill=-1,
                               dtype=np.int32)
    D = raster_heights(np.concatenate([p["tri"] for p in pieces]), x_min, y_max, shape)
    owner[np.isnan(D)] = -1
    print("paved polygons %d (%d pieces), cells %d" % (max(p["poly"] for p in pieces) + 1, len(pieces), (owner >= 0).sum()))
    # 2. the idealised surfaces
    rp = np.load(os.path.join(DATI, "road_profile.npz"))
    main_cw = surface_fit.carriageway_mask(shape, x_min, y_max, RES, rp["C"], rp["N"], rp["tL"], rp["tR"])
    S, info = surface_fit.fit(owner, D, x_min, y_max, RES, main=main_cw & (owner >= 0))
    LR0, LD0 = surface_fit.link_same(owner, owner >= 0)
    S_old = surface_fit.Surface(owner, np.nan_to_num(D), LR0, LD0, x_min, y_max, RES)

    def delta(x, y):
        """Height change of the paved surface at the nearest paved point, fading out 2-4 m off it."""
        x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64))
        w = np.clip((4.0 - S.distance(x, y)) / 2.0, 0.0, 1.0)
        d = np.zeros(len(x))
        m = w > 0
        if m.any():
            d[m] = (S.height(x[m], y[m]) - S_old.height(x[m], y[m])) * w[m]
        return np.nan_to_num(d)
    ter = Terrain(lv)
    # 3. road meshes, meshed again on the new surfaces
    by_shape = {}
    for p in pieces:
        by_shape.setdefault((p["shape"], tuple(p["pos"])), []).append(p)
    pid_of = {}
    n_wall = 0
    tops = []
    for (shp, pos), ps in by_shape.items():
        mb = bng.MeshBuilder()
        for p in ps:
            cell, uvt = MATS.get(p["mat"], (1.0, 1.25))
            pid = pid_of.get(p["poly"])
            if pid is None:
                cells = owner == p["poly"]
                pid = pid_of[p["poly"]] = p["poly"] if cells.any() else None
            if pid is None:
                # a sliver without cells of its own: its v1.0 triangles as they were
                V2, T = road_mesh.weld_2d(p["tri"][:, :, :2], 0.002)
                z_old = raster_free_heights(p["tri"], V2)
                parts = [(None, np.column_stack([V2, z_old]), T)]
            else:
                z_fn = (lambda pid_: (lambda x, y, comp: S.height(x, y, pid=pid_, comp=int(comp))))(pid)
                key_fn = (lambda pid_: (lambda x, y: S.surfaces_at_polygon(x, y, pid_)))(pid)
                parts = []
                for sub, comp in road_mesh.split_by_surface(p["geom"], S, pid):
                    kf = key_fn if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                    parts += road_mesh.mesh_polygon_surfaces(sub, z_fn, kf, cell=cell)
            for comp, V, T in parts:
                if not len(T):
                    continue
                mb.add(p["mat"], V, uvs=V[:, :2] / uvt, tris=T)
                tops.append(V[T])
                kerb, wall = road_mesh.skirt_bands(V, T, road_mesh.skirt_depth(V, T, S, ter.sample))
                mb.add(p["mat"], kerb, uvs=np.column_stack([kerb[:, 0] + kerb[:, 1], kerb[:, 2]]) / uvt,
                       normals=bng.flat_normals_soup(kerb))
                if len(wall):
                    mb.add("mp_road_wall", wall, uvs=np.column_stack([wall[:, 0] + wall[:, 1], wall[:, 2]]) / 1.6,
                           normals=bng.flat_normals_soup(wall))
                    n_wall += len(wall) // 6
        m = re.search(r"road_([+-]\d+)_([+-]\d+)\.dae", shp)
        mb.write_dae(os.path.join(lv, shp.replace(L + "/", "")), name=f"road_{int(m.group(1))}_{int(m.group(2))}",
                     origin=np.array(pos))
    st = "/assets/materials/tileable/brick/stone_brick_regular/t_stone_brick_regular"
    bng.write_materials(os.path.join(lv, "art", "shapes", "roads", "main.materials.json"), [
        bng.material("mp_road_wall", f"{st}_b.color.dds", f"{st}_nm.normal.dds", f"{st}_r.data.dds",
                     f"{st}_ao.data.dds", ground_type="ROCK")])
    print("road meshes: %d chunks, stone faces %d (%.0f s)" % (len(by_shape), n_wall, time.time() - t0))
    # 4. terrain: 0.1 m under the lowest paved surface within 0.8 m
    xs = ter.x0 + np.arange(ter.n) * ter.sq
    ys = ter.y0 + np.arange(ter.n) * ter.sq
    trt = Affine(ter.sq, 0, xs[0] - 0.5 * ter.sq, 0, ter.sq, ys[0] - 0.5 * ter.sq)          # row 0 = south
    union = shapely.union_all([p["geom"].buffer(0.35) for p in pieces])
    mask = features.rasterize([(union, 1)], out_shape=(ter.n, ter.n), transform=trt, fill=0, dtype=np.uint8,
                              all_touched=True).astype(bool)
    rr, cc = np.nonzero(mask)
    X, Y = xs[cc], ys[rr]

    def surf(x, y):
        """paved surface within 2 m of the paved cells, the v1.0 carve beyond 4 m, blended"""
        w = np.clip((4.0 - S.distance(x, y)) / 2.0, 0.0, 1.0)
        return w * np.nan_to_num(S.height(x, y)) + (1 - w) * (ter.sample(x, y) + 0.10)
    zc = surf(X, Y)
    for dx, dy in road_mesh.CARVE_RING:
        zc = np.minimum(zc, surf(X + dx, Y + dy))
    old = ter.h[mask].copy()
    ter_old = ter.h.copy()
    ter.set(mask, zc - 0.10)
    ter.save()
    ch = ter.h[mask] - old
    print("terrain: %d vertices carved again, change p50 %.3f m, max +%.2f / %.2f m" % (mask.sum(), np.median(np.abs(ch)),
                                                                                      ch.max(), ch.min()))
    # 5. markings: on the new road meshes, at the height they had over the old ones
    mk = os.path.join(lv, "art", "shapes", "roads", "markings.dae")
    new_road = road_mesh.MeshSampler(np.concatenate(tops))
    old_road = road_mesh.MeshSampler(np.concatenate([p["tri"] for p in pieces]))

    def on_road(V):
        lift = np.clip(np.nan_to_num(V[:, 2] - old_road(V[:, 0], V[:, 1]), nan=0.02), 0.015, 0.04)
        zn = new_road(V[:, 0], V[:, 1]) + lift
        zs = V[:, 2] + delta(V[:, 0], V[:, 1])
        return np.column_stack([V[:, :2], np.where(np.isfinite(zn), zn, zs)])
    rewrite_dae(mk, "markings", (0, 0, 0), on_road)
    # 6. AI roads
    ai_f = os.path.join(lv, "main", "MissionGroup", "AIRoads", "items.level.json")
    objs = items(ai_f)
    for o in objs:
        if o.get("class") != "DecalRoad":
            continue
        n = np.array(o["nodes"], np.float64)
        if o.get("name") == "strada_cantonale":
            P, z, off = clearance.keep_to_surface(n[:, :2], lambda x, y: S.height(x, y), lambda x, y: S.distance(x, y) < 0.4)
            n[:, :2], n[:, 2] = P, z + 0.1
            print("main AI route: %d nodes moved sideways onto one surface" % int((off != 0).sum()))
        else:
            n[:, 2] += delta(n[:, 0], n[:, 1])
        o["nodes"] = n.tolist()
        o["position"] = o["nodes"][0][:3]
    write_items(ai_f, objs)
    # 7. street lights, poles, signs, furniture: on the ground (road or terrain) as before;
    #    guardrails: with the road edge
    def ground(road, h):
        def fn(x, y):
            c = (np.asarray(x) - ter.x0) / ter.sq
            r = (np.asarray(y) - ter.y0) / ter.sq
            zt = map_coordinates(h, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")
            zr = road(x, y)
            return np.where(np.isfinite(zr), np.maximum(zr, zt), zt)
        return fn
    g_old, g_new = ground(old_road, ter_old), ground(new_road, ter.h)
    lift = lambda x, y: g_new(x, y) - g_old(x, y)
    props = os.path.join(lv, "main", "MissionGroup", "props")
    n_obj = 0
    for dp, _, fs in os.walk(props):
        for f in fs:
            if f != "items.level.json":
                continue
            objs = items(os.path.join(dp, f))
            for o in objs:
                if o.get("class") == "TSStatic" and "position" in o and o["position"] != [0.0, 0.0, 0.0]:
                    x, y, z = o["position"]
                    o["position"] = [x, y, z + float(lift([x], [y])[0])]
                    n_obj += 1
            write_items(os.path.join(dp, f), objs)
    rewrite_dae(os.path.join(lv, "art", "shapes", "props", "props_poles.dae"), "props", (0, 0, 0),
                lambda V: V + np.column_stack([np.zeros((len(V), 2)), lift(V[:, 0], V[:, 1])]))
    shift = lambda V: V + np.column_stack([np.zeros((len(V), 2)), delta(V[:, 0], V[:, 1])])
    gr = items(os.path.join(lv, "main", "MissionGroup", "roads", "guardrails", "items.level.json"))
    for o in gr:
        rewrite_dae(os.path.join(lv, o["shapeName"].replace(L + "/", "")), "guardrail", o["position"], shift)
    print("props moved with the road: %d objects, poles/signs mesh, %d guardrail chunks" % (n_obj, len(gr)))
    # 8. vegetation off the paved surfaces
    veg(lv, pieces, ter)
    # 9. notes, package
    readme = os.path.join(lv, "README.md")
    txt = open(readme, encoding="utf-8").read()
    section, rows = notes()
    lines = txt.splitlines()
    for row in rows:                                     # the table rows the new version changes
        key = row.split("|")[1]
        lines = [row if l.startswith("|" + key + "|") else l for l in lines]
    txt = "\n".join(lines)
    txt = txt.replace("## Precisione e verifica", section + "\n## Precisione e verifica", 1) \
        if "## Precisione e verifica" in txt else txt.rstrip() + "\n\n" + section
    open(readme, "w", encoding="utf-8").write(txt.rstrip() + "\n")
    info_f = os.path.join(lv, "info.json")
    inf = json.load(open(info_f, encoding="utf-8"))
    inf["title"] = "Strada Cantonale Magliaso - Pura (v1.1)"
    json.dump(inf, open(info_f, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    names_after = sorted(os.path.relpath(os.path.join(dp, f), work) for dp, _, fs in os.walk(work) for f in fs)
    assert names_before == names_after, set(names_before) ^ set(names_after)
    if os.path.exists(dst):
        os.remove(dst)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n_ in names_after:
            z.write(os.path.join(work, n_), n_.replace(os.sep, "/"))
    shutil.rmtree(work)
    print("written %s (%.1f MB) in %.0f s" % (dst, os.path.getsize(dst) / 1e6, time.time() - t0))


def veg(lv, pieces, ter):
    """clearance.clear_paved on the forest items of the level (distance from a 0.25 m raster of
    the paved areas)."""
    tri = np.concatenate([p["tri"] for p in pieces])[:, :, :2]
    r = 0.25
    x_min, y_max = np.floor(tri[..., 0].min()) - 20, np.ceil(tri[..., 1].max()) + 20
    W = int((np.ceil(tri[..., 0].max()) + 20 - x_min) / r)
    H = int((y_max - np.floor(tri[..., 1].min()) + 20) / r)
    tr = Affine(r, 0, x_min, 0, -r, y_max)
    paved = features.rasterize([(p["geom"], 1) for p in pieces], out_shape=(H, W), transform=tr, fill=0,
                               dtype=np.uint8).astype(bool)
    d_out, (ir_o, ic_o) = ndi.distance_transform_edt(~paved, return_indices=True)
    d_in, (ir_i, ic_i) = ndi.distance_transform_edt(paved, return_indices=True)

    def dist_dir(x, y):
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        c = np.clip(((x - x_min) / r).astype(int), 0, W - 1)
        rr = np.clip(((y_max - y) / r).astype(int), 0, H - 1)
        inside = paved[rr, c]
        # nearest cell of the other kind; distance to the edge between the two cells
        tr_ = np.where(inside, ir_i[rr, c], ir_o[rr, c])
        tc_ = np.where(inside, ic_i[rr, c], ic_o[rr, c])
        px, py = x_min + (tc_ + 0.5) * r, y_max - (tr_ + 0.5) * r
        v = np.column_stack([x - px, y - py])
        n = np.linalg.norm(v, axis=1)
        d = np.maximum(n - 0.5 * r, 0.0)
        u = v / np.maximum(n, 1e-9)[:, None]
        u[inside] *= -1                                  # inside: away from the paved area = towards the edge
        d[inside] *= -1
        far = (x < x_min) | (x >= x_min + W * r) | (y > y_max) | (y <= y_max - H * r)
        d[far] = 99.0
        return d, u[:, 0], u[:, 1]
    und = np.load(os.path.join(DATI, "understory.npz"))
    us_xy = np.column_stack([und["x"], und["y"]])
    from scipy.spatial import cKDTree
    us_tree = cKDTree(us_xy)
    stats = {"tree": [0, 0], "bush": [0, 0], "hedge": [0, 0]}
    import glob
    for f in sorted(glob.glob(os.path.join(lv, "forest", "*.forest4.json"))):
        name = os.path.basename(f).replace(".forest4.json", "")
        objs = items(f)
        P = np.array([o["pos"] for o in objs], np.float64)
        kind, h0, wx, wy = VEG.get(name, ("tree", 0, 0, 0))
        if name == "tree_aspen_small_a":                 # a shrub where it comes from understory.py
            dd, _ = us_tree.query(P[:, :2])
            kinds = np.where(dd < 0.01, "bush", "tree")
            wx = wy = 0.8 * 6.43
        else:
            kinds = np.full(len(objs), kind)
        ents = []
        for o, k in zip(objs, kinds):
            s = float(o["scale"])
            rm = o["rotationMatrix"]
            e = {"x": o["pos"][0], "y": o["pos"][1], "kind": str(k), "r": 0.25 * (wx + wy) * s}
            if k == "hedge":
                e.update(r=0.5 * wy * s, L=0.5 * wx * s, theta=float(np.arctan2(rm[1], rm[0])))
            ents.append(e)
        res = clearance.clear_paved(ents, dist_dir)
        keep = []
        for o, e, rr_ in zip(objs, ents, res):
            if rr_ is None:
                stats[e["kind"]][0] += 1
                continue
            if (rr_[0], rr_[1]) != (e["x"], e["y"]):
                stats[e["kind"]][1] += 1
                o["pos"] = [round(float(rr_[0]), 3), round(float(rr_[1]), 3),
                            round(float(ter.sample([rr_[0]], [rr_[1]])[0]) - 0.1, 3)]
            keep.append(o)
        write_items(f, keep)
    print("vegetation off the paved surfaces (dropped, moved back):", stats)


def notes():
    """The 'Versione 1.1' section of README_livello.md and the table rows it updates."""
    src = open(os.path.join(HERE, "README_livello.md"), encoding="utf-8").read()
    a = src.index("## Versione 1.1")
    b = src.index("\n## ", a + 5)
    rows = [l for l in src.splitlines() if l.startswith("| Strade e marciapiedi") or l.startswith("| Alberi (")]
    return src[a:b].strip() + "\n", rows


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
