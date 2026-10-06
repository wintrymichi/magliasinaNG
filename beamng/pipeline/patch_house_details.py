"""Details of the houses (v2.8): gutters and downpipes, TV aerials, satellite dishes and solar panels, in a
built level zip.

The buildings of the level are the swissBUILDINGS3D roofs and walls (buildings.py), with the windows, doors and
balconies drawn on the façades: no gutter, no downpipe, nothing on the roofs. Here, from the meshes of the
level and the Federal Register of Buildings (dati/gwr_area.json.gz), by rules (no open data has them):
- gutters along the eaves of every pitched roof: the boundary edges of the roof faces that are level (within
  EAVE_DZ m) and lower than the roof beside them, chained into runs and joined where they run on straight; a
  channel GUTTER_W m wide and GUTTER_H m deep just outside the wall, zinc grey or copper (the same for a roof);
- downpipes (DOWNPIPE m square, down to the ground) at both ends of the runs of eaves of PIPE_RUN m or more,
  the longest runs first, PIPES_MAX a roof at most;
- on the roofs of the houses (GWR residential categories): a TV aerial on the ridge of AERIAL_SHARE of those built
  before 1991 (a mast and two cross-arms), a satellite dish on DISH_SHARE of them (turned to the satellites
  over the equator at 13 degrees east, as most dishes in Ticino), solar panels on PV_SHARE of those with a roof
  face turned within PV_AZ degrees of south, PV_MIN m2 or more: a rectangle of panels PV_INSET m inside it;
- which house gets what: the same every build (a hash of its place);
- meshes in MissionGroup/buildings/details, no collision: gutters, downpipes, aerials and dishes in TILE m tiles
  drawn up to NEAR_DRAW m, the panels in PV_TILE m tiles up to PV_DRAW m (the game measures the drawing distance
  from the centre of a shape: the draw distance over the radius of the tile, so that the details of a house are
  there when the camera is near it, and the tiles no smaller, so that they add few objects to the level).
Everything else is copied as it is.

Usage: python patch_house_details.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, gzip, hashlib, io, json, math, os, re, sys, time, zipfile
import numpy as np
import shapely
from PIL import Image
import bng
import optimize_level
import patch_lamps as pl
import patch_roadside as pr
import patch_unpaved as pu
import patch_wall_fill as pw
from config import LEVEL_NAME

TILE, PV_TILE = 512.0, 1024.0             # m
EAVE_DZ, EAVE_MIN = 0.05, 0.5             # m
GUTTER_W, GUTTER_H, GUTTER_DROP = 0.12, 0.10, 0.03
DOWNPIPE = 0.08
PIPE_RUN, PIPES_MAX = 4.0, 4               # m of eaves for a downpipe; downpipes a roof at most
AERIAL_SHARE, DISH_SHARE, PV_SHARE = 0.30, 0.20, 0.20
PV_AZ, PV_MIN, PV_INSET = 50.0, 12.0, 0.5
NEAR_DRAW, PV_DRAW = 450.0, 1100.0
DISH_AZ, DISH_EL = 174.0, 36.0            # degrees: the satellites at 13 E seen from Lugano
RESIDENTIAL = {1020, 1021, 1025, 1030, 1040}
OLD = 8017                                # GWR period code: built in 1990 or before


def share(key, salt, p):
    """True for a share p of the keys, the same every build."""
    h = hashlib.md5(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(h[:4], "little") / 2 ** 32 < p


def quad(a, b, c, d):
    return [np.array([a, b, c]), np.array([a, c, d])]


def boxv(c, u, half, z0, z1):
    """The four sides and the top of an upright box (k, 3, 3): centre c (2,), axis u, half sizes."""
    n = np.array([-u[1], u[0]])
    P = [c + u * half[0] + n * half[1], c - u * half[0] + n * half[1], c - u * half[0] - n * half[1],
         c + u * half[0] - n * half[1]]
    tri = []
    for a, b in zip(P, P[1:] + P[:1]):
        tri += quad(np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z1])
    tri += quad(*[np.r_[p, z1] for p in P])
    return tri


def beam(a, b, w):
    """A thin square bar from a to b (3,), w across."""
    d = b - a
    L = np.linalg.norm(d)
    d = d / L
    s = np.cross(d, [0, 0, 1.0])
    if np.linalg.norm(s) < 1e-6:
        s = np.array([1.0, 0, 0])
    s = s / np.linalg.norm(s) * w / 2
    t = np.cross(d, s)
    t = t / np.linalg.norm(t) * w / 2
    C = [s + t, -s + t, -s - t, s - t]
    tri = []
    for p, q in zip(C, C[1:] + C[:1]):
        tri += quad(a + p, a + q, b + q, b + p)
    return tri


def dish(c, z):
    """A dish of 0.6 m on a short arm at c (2,) z, facing DISH_AZ / DISH_EL."""
    az, el = math.radians(DISH_AZ), math.radians(DISH_EL)
    f = np.array([math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])
    u = np.cross(f, [0, 0, 1.0])
    u /= np.linalg.norm(u)
    v = np.cross(u, f)
    o = np.r_[c, z + 0.55]
    rim = [o + 0.30 * (math.cos(a) * u + math.sin(a) * v) - 0.06 * f for a in np.linspace(0, 2 * np.pi, 11)[:-1]]
    tri = [np.array([o, rim[k], rim[(k + 1) % 10]]) for k in range(10)]
    tri += beam(np.r_[c, z], o - 0.05 * f, 0.04)
    tri += beam(o, o + 0.35 * f, 0.025)
    return tri


def strip(a, b, w, up=(0, 0, 1.0)):
    """A thin flat bar from a to b (3,), w wide across `up` (two triangles; a double-sided material)."""
    s = np.cross(b - a, up)
    s = s / max(np.linalg.norm(s), 1e-9) * w / 2
    return quad(a - s, b - s, b + s, a + s)


def aerial(c, z):
    """A TV aerial: a 2.2 m mast and two cross-arms with their elements, at c (2,) on the ridge z."""
    top = np.r_[c, z + 2.2]
    tri = beam(np.r_[c, z - 0.2], top, 0.04)
    for h, L in ((2.0, 1.2), (1.5, 0.9)):
        a, b = np.r_[c[0] - L / 2, c[1], z + h], np.r_[c[0] + L / 2, c[1], z + h]
        tri += strip(a, b, 0.025, up=(0, 1.0, 0))
        for x in np.linspace(-L / 2 + 0.1, L / 2 - 0.1, 4):
            tri += strip(np.r_[c[0] + x, c[1] - 0.25, z + h], np.r_[c[0] + x, c[1] + 0.25, z + h], 0.015, up=(1.0, 0, 0))
    return tri


def pv_texture(size=256):
    """Solar cells: dark blue, thin light lines between them and a frame (one panel 1 x 1.7 m)."""
    img = np.zeros((size, size, 3), np.uint8)
    img[:] = (22, 30, 52)
    for k in range(0, size, size // 6):
        img[:, k:k + 1] = (70, 78, 96)
    for k in range(0, size, size // 10):
        img[k:k + 1, :] = (70, 78, 96)
    img[:3, :] = img[-3:, :] = (150, 152, 156)
    img[:, :3] = img[:, -3:] = (150, 152, 156)
    b = io.BytesIO()
    Image.fromarray(img).save(b, "PNG", optimize=True)
    return b.getvalue()


def roof_parts(V, parts):
    """(pitched roof triangles as vertex ids (k, 3), flat roof faces) of a building shape."""
    pitched = [idx[:, 0].reshape(-1, 3) for m, idx in parts if "roof" in m and "flat" not in m]
    return np.concatenate(pitched) if pitched else np.zeros((0, 3), np.int64)


def components(P):
    """Connected components of triangles (k, 3) of welded vertex ids: label per triangle."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    k = len(P)
    rows = np.repeat(np.arange(k), 3)
    cols = P.ravel()
    n = cols.max() + 1
    M = coo_matrix((np.ones(len(rows)), (rows, cols + k)), shape=(k + n, k + n))
    _, lab = connected_components(M, directed=False)
    return lab[:k]


def house_details(W, T, ground, gwr, rep):
    """{material: [triangles]} of the details of the houses of one building shape (world coordinates W)."""
    out = {}

    def add(m, tris):
        if tris:
            out.setdefault(m, []).extend(tris)
    if not len(T):
        return out
    key = np.round(W * 1000).astype(np.int64)
    _, pid = np.unique(key, axis=0, return_inverse=True)
    pid = pid.ravel()
    rep_v = np.zeros(pid.max() + 1, np.int64)
    rep_v[pid] = np.arange(len(pid))
    P = pid[T]
    X = W[rep_v]                                           # one position per welded vertex
    t3 = X[P]
    nrm = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
    area = 0.5 * np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    nrm *= np.where(nrm[:, 2] < 0, -1.0, 1.0)[:, None]
    lab = components(P)
    # eaves: level boundary edges lower than their face
    E = np.concatenate([P[:, [0, 1]], P[:, [1, 2]], P[:, [2, 0]]])
    F = np.tile(np.arange(len(P)), 3)
    _, inv, cnt = np.unique(np.sort(E, 1), axis=0, return_inverse=True, return_counts=True)
    b = cnt[inv.ravel()] == 1
    E, F = E[b], F[b]
    A, B = X[E[:, 0]], X[E[:, 1]]
    L = np.linalg.norm(B[:, :2] - A[:, :2], axis=1)
    cz = t3[F].mean(1)
    ok = (np.abs(B[:, 2] - A[:, 2]) < EAVE_DZ) & (L > EAVE_MIN) & (cz[:, 2] > (A[:, 2] + B[:, 2]) / 2 + 0.1)
    E, F, A, B, L, cz = E[ok], F[ok], A[ok], B[ok], L[ok], cz[ok]
    d = (B[:, :2] - A[:, :2]) / L[:, None]
    out_n = np.column_stack([d[:, 1], -d[:, 0]])
    side = (((A[:, :2] + B[:, :2]) / 2 - cz[:, :2]) * out_n).sum(1)
    out_n *= np.where(side < 0, -1.0, 1.0)[:, None]                         # away from the roof
    copper = {c: share(tuple(np.round(t3[lab == c].reshape(-1, 3)[:, :2].mean(0)).astype(int)), "copper", 0.35)
              for c in np.unique(lab)}
    # runs of eaves: the edges chained through the vertices they share, cut where the run turns
    at = {}
    for k, e in enumerate(E):
        for v in e:
            at.setdefault(int(v), []).append(k)
    seen = np.zeros(len(E), bool)
    chains = []
    starts = [v for v, ks in at.items() if len(ks) == 1] + [int(e[0]) for e in E]
    for v0 in starts:
        ks = [k for k in at[v0] if not seen[k]]
        if not ks:
            continue
        verts, edges, v = [v0], [], v0
        while True:
            nxt = [k for k in at[v] if not seen[k]]
            if not nxt:
                break
            k = nxt[0]
            seen[k] = True
            edges.append(k)
            v = int(E[k][1] if E[k][0] == v else E[k][0])
            verts.append(v)
            if len(at[v]) > 2:
                break
        chains.append((verts, edges))
    pipes = {}
    for verts, edges in chains:
        f = F[edges[0]]
        m = "mp_house_copper" if copper[lab[f]] else "mp_house_zinc"
        run = [0]
        for i in range(1, len(edges) + 1):
            end = i == len(edges)
            if not end:
                d0, d1 = d[edges[run[0]]], d[edges[i]]
                d1 = d1 * (1 if np.dot(X[verts[i + 1], :2] - X[verts[i], :2], d1) > 0 else -1)
                d0 = d0 * (1 if np.dot(X[verts[run[0] + 1], :2] - X[verts[run[0]], :2], d0) > 0 else -1)
                if np.dot(d0, d1) > math.cos(math.radians(5)) and abs(X[verts[i], 2] - X[verts[run[0]], 2]) < 0.03:
                    continue
            a, bb, o = X[verts[run[0]]], X[verts[i]], out_n[edges[run[0]]]
            z = (a[2] + bb[2]) / 2 - GUTTER_DROP
            p0, p1 = a[:2], bb[:2]
            i0, i1 = np.r_[p0, z], np.r_[p1, z]                                  # at the wall, top
            ib0, ib1 = np.r_[p0, z - GUTTER_H], np.r_[p1, z - GUTTER_H]
            ob0, ob1 = np.r_[p0 + o * GUTTER_W, z - GUTTER_H], np.r_[p1 + o * GUTTER_W, z - GUTTER_H]
            ot0, ot1 = np.r_[p0 + o * GUTTER_W, z], np.r_[p1 + o * GUTTER_W, z]
            add(m, quad(ib0, ob0, ob1, ib1) + quad(ob0, ot0, ot1, ob1) + quad(i0, ib0, ib1, i1))
            rep["gutter_m"] += float(np.linalg.norm(p1 - p0))
            run = [i]
        length = float(L[edges].sum())
        if length < PIPE_RUN:
            continue
        ends = [(verts[0], edges[0], verts[1]), (verts[-1], edges[-1], verts[-2])]
        if verts[0] == verts[-1]:                       # a ring of eaves: two corners across
            h = len(verts) // 2
            ends = [(verts[0], edges[0], verts[1]), (verts[h], edges[h], verts[h + 1])]
        pipes.setdefault(lab[f], []).append((length, ends, m))
    # downpipes: at both ends of the longest runs, PIPES_MAX a roof at most, none closer than 1.5 m
    for c, runs in pipes.items():
        put = []
        for length, ends, m in sorted(runs, key=lambda r: -r[0]):
            for v, k, w in ends:
                if len(put) >= PIPES_MAX:
                    break
                o = out_n[k]
                q = X[v, :2] + o * (DOWNPIPE / 2 + 0.01) + (X[w, :2] - X[v, :2]) / max(
                    np.linalg.norm(X[w, :2] - X[v, :2]), 1e-9) * 0.15
                if any(np.hypot(*(q - p)) < 1.5 for p in put):
                    continue
                zt = float(ground([q[0]], [q[1]])[0])
                ztop = X[v, 2] - GUTTER_DROP - GUTTER_H
                if ztop - zt < 1.5 or ztop - zt > 30:
                    continue
                sides = boxv(q, np.array([o[1], -o[0]]), (DOWNPIPE / 2, DOWNPIPE / 2), zt - 0.1, ztop)[:8]
                n_out = [k2 for k2 in range(0, 8, 2) if np.dot(np.cross(sides[k2][1] - sides[k2][0],
                                                                   sides[k2][2] - sides[k2][0])[:2], o) > -1e-9]
                add(m, [t for k2 in n_out for t in sides[k2:k2 + 2]])              # not the side against the wall
                put.append(q)
                rep["downpipes"] += 1
    # the roofs of the houses: aerial, dish, solar panels
    for c in np.unique(lab):
        sel = lab == c
        tri = t3[sel]
        foot = shapely.union_all([shapely.Polygon(t[:, :2]) for t in tri if abs(np.cross(t[1, :2] - t[0, :2], t[2, :2] - t[0, :2])) > 1e-6])
        if foot.is_empty or foot.area < 30:
            continue
        hit = gwr.query(foot, predicate="contains")
        if not len(hit):
            continue
        g = gwr.meta[hit[0]]
        if g["gkat"] not in RESIDENTIAL:
            continue
        hkey = f"{g['egid']}"
        rep["houses"] += 1
        V3 = tri.reshape(-1, 3)
        top = V3[np.argmax(V3[:, 2])]
        if (g["gbaup"] or 9999) <= OLD and share(hkey, "aerial", AERIAL_SHARE):
            add("mp_house_metal", aerial(top[:2], top[2]))
            rep["aerials"] += 1
        # roof faces by orientation: planes of similar normals
        n_c = nrm[sel]
        az = np.degrees(np.arctan2(n_c[:, 0], n_c[:, 1])) % 360         # where the face looks
        slope = np.degrees(np.arccos(np.clip(n_c[:, 2], -1, 1)))
        south = (np.abs(az - 180) < PV_AZ) & (slope > 10) & (slope < 50)
        if share(hkey, "dish", DISH_SHARE):
            ix = np.flatnonzero(south) if south.any() else np.arange(len(tri))
            t = tri[ix[np.argmax(area[sel][ix])]]
            cpt = t.mean(0)
            add("mp_house_dish", dish(cpt[:2], cpt[2]))
            rep["dishes"] += 1
        if south.any() and share(hkey, "pv", PV_SHARE):
            # the largest south face plane: its faces with a normal within 3 degrees of the largest one
            ix = np.flatnonzero(south)
            n0 = n_c[ix[np.argmax(area[sel][ix])]]
            plane = ix[np.degrees(np.arccos(np.clip(n_c[ix] @ n0, -1, 1))) < 3]
            pts = tri[plane].reshape(-1, 3)
            o = pts[np.argmin(pts[:, 2])]
            u = np.cross([0, 0, 1.0], n0)
            u /= np.linalg.norm(u)                               # level, along the eave
            v = np.cross(n0, u)                                  # up the slope
            Q = lambda p: np.column_stack([(p - o) @ u, (p - o) @ v])
            poly = shapely.union_all([shapely.Polygon(Q(t)) for t in tri[plane]]).buffer(-PV_INSET, join_style="mitre")
            if poly.is_empty or poly.area < PV_MIN:
                continue
            x0, y0, x1, y1 = poly.bounds
            for _ in range(40):                                  # shrink the box until it lies inside
                r = shapely.box(x0, y0, x1, y1)
                if poly.buffer(1e-6).contains(r):
                    break
                x0, x1, y0, y1 = x0 + 0.15, x1 - 0.15, y0 + 0.1, y1 - 0.1
                if x1 - x0 < 2 or y1 - y0 < 1.7:
                    break
            else:
                continue
            if not poly.buffer(1e-6).contains(shapely.box(x0, y0, x1, y1)) or (x1 - x0) * (y1 - y0) < PV_MIN:
                continue
            lift = n0 * 0.10
            C = [o + u * x + v * y + lift for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            tris = quad(*C)
            uv = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y0], [x1, y1], [x0, y1]]) / np.array([1.0, 1.7])
            out.setdefault("mp_house_pv", []).append((tris, uv))
            rep["pv_m2"] += (x1 - x0) * (y1 - y0)
            rep["pv"] += 1
    return out


class Gwr:
    def __init__(self, path):
        g = json.load(gzip.open(path, "rt", encoding="utf-8"))["buildings"]
        g = [b for b in g if b.get("gstat") == 1004]
        self.meta = g
        self.tree = shapely.STRtree([shapely.Point(b["x"], b["y"]) for b in g])

    def query(self, poly, predicate):
        return self.tree.query(poly, predicate=predicate)


def main(src, dst, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    ground = lambda x, y: pu.terrain_top(q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))
    gwr = Gwr(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "gwr_area.json.gz"))
    rep = {k: 0 for k in ("shapes", "houses", "downpipes", "aerials", "dishes", "pv")}
    rep.update(gutter_m=0.0, pv_m2=0.0)
    near, far = {}, {}
    for o in pl.read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        T = roof_parts(V, parts)
        det = house_details(W, T, ground, gwr, rep)
        rep["shapes"] += 1
        for m, tris in det.items():
            if not tris:
                continue
            if m == "mp_house_pv":
                for tr, uv in tris:
                    c = tr[0].mean(0)
                    k = (int(math.floor(c[0] / PV_TILE)), int(math.floor(c[1] / PV_TILE)))
                    far.setdefault(k, []).append((m, np.array(tr), uv))
            else:
                arr = np.array(tris)
                ks = np.floor(arr.mean(1)[:, :2] / TILE).astype(int)
                for k in {tuple(x) for x in ks}:
                    sel = (ks[:, 0] == k[0]) & (ks[:, 1] == k[1])
                    near.setdefault(k, []).append((m, arr[sel], None))
        if rep["shapes"] % 50 == 0:
            print("%d building shapes, %.0f s" % (rep["shapes"], time.time() - t0), flush=True)
    print("houses %d: gutters %.0f km, %d downpipes, %d aerials, %d dishes, %d roofs with panels (%.0f m2)"
          % (rep["houses"], rep["gutter_m"] / 1000, rep["downpipes"], rep["aerials"], rep["dishes"], rep["pv"],
             rep["pv_m2"]), flush=True)
    new_files, items, ntri = {}, [], 0

    def write(tiles, name, draw, size):
        nonlocal ntri
        for (tx, ty), ps in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * size, (ty + 0.5) * size, 0.0])
            for m, T, uv in ps:
                Vv = T.reshape(-1, 3)
                mb.add(m, Vv, uvs=uv if uv is not None else Vv[:, :2], normals=bng.flat_normals_soup(Vv))
                ntri += len(T)
            allv = np.concatenate([T.reshape(-1, 3) for _, T, _ in ps])
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / draw)))
            rel = f"art/shapes/buildings/details/{name}_{tx:+03d}_{ty:+03d}.dae"
            tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"{name}_{os.getpid()}.dae")
            mb.write_dae(tmp, name=name, origin=origin, detail=detail)
            new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
            os.remove(tmp)
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False)
            ob["__parent"] = "details"
            items.append(ob)
        return len(tiles)
    nt_n = write(near, "house_details", NEAR_DRAW, TILE)
    nt_f = write(far, "house_pv", PV_DRAW, PV_TILE)
    tex = f"/levels/{LEVEL_NAME}/art/shapes/buildings/details/t_pv_b.color.png"
    new_files[f"{lv}/art/shapes/buildings/details/t_pv_b.color.png"] = pv_texture()
    mats = [bng.material("mp_house_zinc", base_color=[0.60, 0.61, 0.60, 1], roughness=0.45, metallic=0.6, double_sided=True),
            bng.material("mp_house_copper", base_color=[0.47, 0.30, 0.20, 1], roughness=0.5, metallic=0.6,
                         double_sided=True),
            bng.material("mp_house_metal", base_color=[0.70, 0.71, 0.72, 1], roughness=0.35, metallic=0.8,
                         double_sided=True),
            bng.material("mp_house_dish", base_color=[0.86, 0.86, 0.84, 1], roughness=0.4, double_sided=True),
            bng.material("mp_house_pv", tex, roughness=0.15, metallic=0.3)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"details_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/buildings/details/details.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    grp = f"{lv}/main/MissionGroup/buildings/items.level.json"
    group = {"name": "details", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "buildings"}
    root = pl.read_items(zi, grp)
    if any(o.get("name") == "details" for o in root):
        raise SystemExit(f"{src} has a buildings/details group already: run on a zip without the v2.8 house details")
    new_files[grp] = pr.pl_write(root + [group])
    new_files[f"{lv}/main/MissionGroup/buildings/details/items.level.json"] = pr.pl_write(items)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            ni.external_attr = 0o644 << 16
            zo.writestr(ni, data)
    print("%s written in %.0f s: %d detail tiles, %d panel tiles, %d triangles" % (dst, time.time() - t0, nt_n, nt_f, ntri),
          flush=True)
    if report:
        rep.update({"source": os.path.basename(src), "gutter_km": round(rep.pop("gutter_m") / 1000, 1),
                    "pv_m2": round(rep["pv_m2"]), "detail_tiles": nt_n, "panel_tiles": nt_f, "triangles": ntri})
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
