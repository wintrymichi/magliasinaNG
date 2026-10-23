"""Roundabouts as one recognises them (v3.1): a raised green middle on its kerb inside a mountable ring of setts, in
the built level.

In the v3.1 test zip the middle of a roundabout was either a flat disk of the survey's island setts as wide as the
whole hole in the carriageway (raised 12 cm by islands.py) or the terrain's grass at the height of the asphalt, with no
kerb. In the orthophoto (SWISSIMAGE 2024) and the street photos every roundabout of the area has a green middle (lawn,
shrubs, at Magliaso the hedge letters of the village's name) on a kerb, inside a ring of reddish granite setts a lorry
can drive over. Here, on the built level, for every roundabout of OSM (junction=roundabout) in the level:
- the hole in the carriageway round the ring's middle is found on a raster of the asphalt (RES m): its middle and
  radius R (from its area); holes that are not round enough (ROUND) or outside R_MIN..R_MAX are left alone;
- an island of islands.py that goes all round the hole within RING_OUT m (the survey draws the setts round the middle as
  an island, and islands.py put a keep-right sign on it) belongs to the middle: R reaches out to it;
- the island faces of islands.py within R + 0.3 m go, and the road faces under the middle (within R - 0.15 m), and in their place: the ring of setts (APRON m wide, R >= R_GREEN)
  APRON_H m over the asphalt with a low kerb, and the green middle GREEN_H m high on its kerb (the game's grass of the
  terrain), on the plane through the asphalt round the hole and never under the terrain (the survey's mounds in the
  middle stay mounds); a small roundabout is all setts;
- what stands in the middle (signs, trees, shrubs) goes up with it.
Meshes in MissionGroup/roads/roundabouts (collision); the rest of the level is copied as it is.

A finishing step of build_level.py (FINISH), after islands and sidewalks; on a built level: python roundabouts.py <folder>
"""
import gzip, json, math, os, re, sys, tempfile, time, zipfile
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import bng
import optimize_level
import osm_surface
from config import LEVEL_NAME, DATA, lv95_to_local, wgs_to_lv95
from markings_net import read_items, shape_tris

HERE = os.path.dirname(os.path.abspath(__file__))
OSM = os.path.join(HERE, "..", "dati", "osm_area.json.gz")
RES = 0.25               # m, raster of the asphalt round a roundabout
WIN = 30.0               # m round its middle
R_MIN, R_MAX = 1.5, 14.0  # m, radius of the hole in the carriageway
RING_OUT = 5.0           # m beyond the hole: an island ring of setts there belongs to the middle
ROUND = 0.75             # hole area / area of the circle round it from its middle
APRON = 1.6              # m, the ring of setts
APRON_H = 0.04           # m over the asphalt (mountable)
GREEN_H = 0.16           # m, the green middle over the asphalt
R_GREEN = 3.2            # m: smaller holes are all setts
SEG = 72                 # segments round the circle
KERB_DOWN = 0.10
GRASS_UV = 2.0           # m per texture tile
CARRIAGE = set(osm_surface.ROAD_MATS) | {"mp_road_asphalt_fresh"}
L = f"/levels/{LEVEL_NAME}"
SHAPE = re.compile(r"art/shapes/roads/roundabouts\.dae$")
GRASS = "/assets/materials/terrain/grass/t_grass_01/t_grass_01"


def materials():
    return [bng.material("mp_rb_grass", f"{GRASS}_b.png", f"{GRASS}_nm.png", f"{GRASS}_r.png", f"{GRASS}_ao.png",
                         base_color=[0.78, 0.86, 0.7, 1], ground_type="GRASS")]


def osm_rings():
    """Middles (local x, y) of the roundabouts of OSM: the ways of one ring joined by shared nodes."""
    d = json.load(gzip.open(OSM))
    ways = [e for e in d["elements"] if e.get("type") == "way" and e.get("tags", {}).get("junction") in
            ("roundabout", "circular") and e.get("geometry")]
    pts = []
    for w in ways:
        P = np.array([lv95_to_local(*wgs_to_lv95(p["lat"], p["lon"])) for p in w["geometry"]])
        pts.append(P)
    # group ways whose points come within 3 m
    n = len(pts)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(n):
        ti = cKDTree(pts[i])
        for j in range(i + 1, n):
            if np.isfinite(ti.query(pts[j], distance_upper_bound=3.0)[0]).any():
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(pts[i])
    out = []
    for g in groups.values():
        P = np.concatenate(g)
        c = (P.min(0) + P.max(0)) / 2               # the middle of the ring's box (an arc's mean is off-centre)
        out.append(c)
    return out


def hole(c, carr_xy):
    """Middle and radius of the hole in the carriageway round c, or None."""
    n = int(2 * WIN / RES)
    x0, y0 = c[0] - WIN, c[1] - WIN
    m = (carr_xy[:, 0] > x0) & (carr_xy[:, 0] < x0 + 2 * WIN) & (carr_xy[:, 1] > y0) & (carr_xy[:, 1] < y0 + 2 * WIN)
    g = np.zeros((n, n), bool)
    P = carr_xy[m]
    g[((P[:, 1] - y0) / RES).astype(int).clip(0, n - 1), ((P[:, 0] - x0) / RES).astype(int).clip(0, n - 1)] = True
    g = ndi.binary_closing(g, iterations=2)
    lab, k = ndi.label(~g)
    ci, cj = int(n / 2), int(n / 2)
    best = None
    for dr in range(0, int(6 / RES)):           # the hole nearest the OSM middle (within 6 m)
        sl = lab[max(ci - dr, 0):ci + dr + 1, max(cj - dr, 0):cj + dr + 1]
        ids = [i for i in np.unique(sl) if i]
        if ids:
            best = ids
            break
    if not best:
        return None
    for i in best:
        comp = lab == i
        if comp[0, :].any() or comp[-1, :].any() or comp[:, 0].any() or comp[:, -1].any():
            continue
        rr, cc = np.nonzero(comp)
        mid = np.array([x0 + (cc.mean() + 0.5) * RES, y0 + (rr.mean() + 0.5) * RES])
        area = comp.sum() * RES * RES
        R = math.sqrt(area / math.pi)
        far = np.hypot(x0 + (cc + 0.5) * RES - mid[0], y0 + (rr + 0.5) * RES - mid[1]).max()
        if R_MIN <= R <= R_MAX and area / (math.pi * far * far) >= ROUND:
            return mid, R
    return None


def ring(c, r, z, seg=SEG):
    a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    return np.c_[c[0] + r * np.cos(a), c[1] + r * np.sin(a), z(c[0] + r * np.cos(a), c[1] + r * np.sin(a))]


def terrain_fn(zi, lv):
    """Height of the level's terrain at x, y."""
    rows = read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
    blk = [o for o in rows if o.get("class") == "TerrainBlock"][0]
    x0, y0, z0 = blk["position"]
    maxh, sq = float(blk["maxHeight"]), float(blk.get("squareSize", 1))
    path = zi.path(f"{lv}/theTerrain.ter")
    n = int(np.fromfile(path, "<u4", count=1, offset=1)[0])
    q = np.memmap(path, "<u2", "r", offset=5, shape=(n, n))

    def fn(x, y):
        """The highest of the terrain vertices round each point (a mesh over it never cuts its triangles)."""
        fy, fx = (np.asarray(y) - y0) / sq, (np.asarray(x) - x0) / sq
        out = None
        for r in (np.floor(fy), np.ceil(fy)):
            for c in (np.floor(fx), np.ceil(fx)):
                h = q[np.clip(r.astype(int), 0, n - 1), np.clip(c.astype(int), 0, n - 1)].astype(np.float64)
                out = h if out is None else np.maximum(out, h)
        return z0 + out / 65535.0 * maxh
    return fn


def roundabouts_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    items = read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json")
    surf = shape_tris(zi, lv, items)
    carr = np.concatenate([t for m, t in surf.items() if m in CARRIAGE])
    del surf
    n_ = np.cross(carr[:, 1] - carr[:, 0], carr[:, 2] - carr[:, 0])
    carr = carr[n_[:, 2] / np.maximum(np.linalg.norm(n_, axis=1), 1e-12) > 0.5]
    # points over the asphalt every ~RES/2: the corners, the middles of the edges and of the faces
    Pz = np.concatenate([carr.reshape(-1, 3), (carr[:, [0, 1, 2]] + carr[:, [1, 2, 0]]).reshape(-1, 3) / 2,
                         carr.mean(1)])
    sub = []
    # faces up to 2 m: sample them more finely
    for u, v in ((0.25, 0.25), (0.5, 0.25), (0.25, 0.5), (0.6, 0.2), (0.2, 0.6), (0.4, 0.4)):
        sub.append(carr[:, 0] + (carr[:, 1] - carr[:, 0]) * u + (carr[:, 2] - carr[:, 0]) * v)
    Pz = np.concatenate([Pz] + sub)
    ztree = cKDTree(Pz[:, :2])
    rep = {"roundabouts": 0, "all_setts": 0, "skipped": 0, "objects_raised": 0,
           "forest_raised": 0, "list": []}
    isl = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/islands/items.level.json")) \
        if f"{lv}/main/MissionGroup/roads/islands/items.level.json" in zi.NameToInfo else {}
    isl_c = isl["mp_island_top"].mean(1)[:, :2] if "mp_island_top" in isl else np.zeros((0, 2))
    del isl
    found = []
    for c in osm_rings():
        if not ztree.query_ball_point(c, 15.0, return_length=True):
            continue                             # outside the level
        h = hole(c, Pz[:, :2])
        if h is None:
            rep["skipped"] += 1
            continue
        mid, R = h
        # the survey often draws the setts round the middle as an island (islands.py raised it, with a keep-right
        # sign on it): the roundabout's middle reaches out to that ring when it goes all round
        if len(isl_c):
            dd = np.hypot(isl_c[:, 0] - mid[0], isl_c[:, 1] - mid[1])
            k = (dd > R - 0.5) & (dd < R + RING_OUT)
            if k.sum() > 20:
                ang = np.floor((np.arctan2(isl_c[k, 1] - mid[1], isl_c[k, 0] - mid[0]) + np.pi) / (2 * np.pi) * 36)
                if len(np.unique(ang)) >= 30:
                    R = max(R, float(np.percentile(dd[k], 97)) + 0.3)
        if any(np.hypot(*(mid - f[0])) < 5 for f in found):
            continue
        # the plane through the asphalt just outside the hole
        q = ring(mid, R + 0.5, lambda x, y: np.zeros_like(x), 36)[:, :2]
        d, i = ztree.query(q, k=4)
        zq = np.where(np.isfinite(d[:, 0]), Pz[i[:, 0], 2], np.nan)
        ok = d[:, 0] < 1.0
        if ok.sum() < 12:
            rep["skipped"] += 1
            continue
        A = np.c_[q[ok] - mid, np.ones(ok.sum())]
        coef, *_ = np.linalg.lstsq(A, zq[ok], rcond=None)
        found.append((mid, R, coef))
    builders = bng.MeshBuilder()
    remove = []                                     # (mid, radius) whose island faces go
    lifts = []                                      # (mid, radius, dz)

    def zf(mid, coef, dz):
        return lambda x, y: coef[0] * (x - mid[0]) + coef[1] * (y - mid[1]) + coef[2] + dz

    ter = terrain_fn(zi, lv)

    def band(mid, r0, r1, z0, z1, mat, uvs="radial"):
        """Annulus r0..r1 (r0 0: a disk in rings 1 m apart, never under the terrain: a mound in the middle) at
        heights z0(x, y) inside, z1 outside."""
        if r0 <= 0.01:
            zg = z1
            rs = list(np.arange(r1, 0.5, -1.0))[::-1]
            T = []
            cz = zg(np.array([mid[0]]), np.array([mid[1]]))[0]
            C = np.r_[mid, cz]
            o = ring(mid, rs[0], zg)
            T.append(np.stack([np.repeat(C[None], SEG, 0), o, np.roll(o, -1, 0)], 1))
            for ra, rb in zip(rs[:-1], rs[1:]):
                i_, o = ring(mid, ra, zg), ring(mid, rb, zg if rb < r1 else z1)
                i2, o2 = np.roll(i_, -1, 0), np.roll(o, -1, 0)
                T += [np.stack([i_, o, o2], 1), np.stack([i_, o2, i2], 1)]
            T = np.concatenate(T)
        else:
            i_, o = ring(mid, r0, z0), ring(mid, r1, z1)
            i2, o2 = np.roll(i_, -1, 0), np.roll(o, -1, 0)
            T = np.concatenate([np.stack([i_, o, o2], 1), np.stack([i_, o2, i2], 1)])
        V = T.reshape(-1, 3)
        uv = V[:, :2] / (GRASS_UV if mat == "mp_rb_grass" else 1.5)
        builders.add(mat, V, uvs=uv, normals=bng.flat_normals_soup(V))

    def wall(mid, r, zlo, zhi, mat, out=True):
        lo, hi = ring(mid, r, zlo), ring(mid, r, zhi)
        lo2, hi2 = np.roll(lo, -1, 0), np.roll(hi, -1, 0)
        T = np.concatenate([np.stack([hi, lo2, lo], 1), np.stack([hi, hi2, lo2], 1)])
        if not out:
            T = T[:, ::-1]
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[lo, lo[:1]][:, :2], axis=0).T))][:-1]
        s2 = np.roll(s, -1); s2[-1] = s[-1] + np.hypot(*(lo[0, :2] - lo[-1, :2]))
        hgt = (hi[:, 2] - lo[:, 2])
        uv = np.concatenate([np.stack([np.c_[s, hgt], np.c_[s2, 0 * s], np.c_[s, 0 * s]], 1),
                             np.stack([np.c_[s, hgt], np.c_[s2, hgt], np.c_[s2, 0 * s]], 1)])
        if not out:
            uv = uv[:, ::-1]
        V = T.reshape(-1, 3)
        builders.add(mat, V, uvs=uv.reshape(-1, 2), normals=bng.flat_normals_soup(V))

    for mid, R, coef in found:
        base = zf(mid, coef, 0.0)
        pa, pg = zf(mid, coef, APRON_H), zf(mid, coef, GREEN_H)

        def top_a(x, y, pa=pa):
            return np.maximum(pa(x, y), ter(x, y) + 0.02)

        def top_g(x, y, pg=pg):
            return np.maximum(pg(x, y), ter(x, y) + 0.03)
        green = R >= R_GREEN
        r_g = R - APRON if green else 0.0
        # the setts ring (or disk) and its low kerb on the outside
        band(mid, r_g, R, top_a, top_a, "mp_island_top")
        wall(mid, R, zf(mid, coef, -KERB_DOWN), top_a, "mp_island_kerb", out=True)
        if green:
            band(mid, 0.0, r_g, top_g, top_g, "mp_rb_grass")
            wall(mid, r_g, top_a, top_g, "mp_island_kerb", out=True)
        rep["roundabouts"] += 1
        rep["all_setts"] += int(not green)
        rep["list"].append({"x": round(float(mid[0]), 1), "y": round(float(mid[1]), 1), "R": round(R, 2),
                            "green": bool(green)})
        remove.append((mid, R + 0.3))
        lifts.append((mid, R, coef))

    # the islands of islands.py inside the roundabouts go, and the road faces under the middle (the asphalt the
    # survey left in the middle stood up through the green where the ground slopes)
    new_dae = {}
    groups = [(f"{lv}/main/MissionGroup/roads/islands/items.level.json", 0.3, "island_faces_removed"),
              (f"{lv}/main/MissionGroup/roads/surfaces/items.level.json", -0.15, "road_faces_removed")]
    for g_name, extra, key in groups:
        rep[key] = 0
        for o in read_items(zi, g_name) if g_name in zi.NameToInfo else []:
            sn = o.get("shapeName", "").lstrip("/")
            if sn not in zi.NameToInfo:
                continue
            pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
            near = [(mid, r + extra) for mid, r in remove
                    if abs(mid[0] - pos[0]) < 400 and abs(mid[1] - pos[1]) < 400]
            if not near:
                continue
            V, N, UV, C, parts, node = optimize_level.parse(zi.read(sn).decode("utf-8"))
            mb = bng.MeshBuilder()
            gone = 0
            for mat, idx in parts:
                F = (V[idx[:, 0]] + pos).reshape(-1, 3, 3)
                cxy = F.mean(1)[:, :2]
                kill = np.zeros(len(F), bool)
                for mid, r in near:
                    kill |= np.hypot(cxy[:, 0] - mid[0], cxy[:, 1] - mid[1]) < r
                gone += int(kill.sum())
                keep = np.repeat(~kill, 3)
                if keep.any():
                    ii = idx[keep]
                    col = C[ii[:, 3]] if C is not None and ii.shape[1] > 3 else None
                    mb.add(mat, V[ii[:, 0]], uvs=UV[ii[:, 2]], normals=N[ii[:, 1]],
                           tris=np.arange(len(ii)).reshape(-1, 3), colors=col)
            if gone and not mb.empty():
                rep[key] += gone
                base_, detail = re.match(r"(.*)_a(\d+)$", node).groups()
                with tempfile.TemporaryDirectory() as tmp:
                    p = os.path.join(tmp, "s.dae")
                    mb.write_dae(p, name=base_, origin=(0, 0, 0), detail=int(detail))
                    new_dae[sn] = open(p, "rb").read()

    def lift(P):
        P = np.asarray(P, float).reshape(-1, 2)
        dz = np.zeros(len(P))
        for mid, R, coef in lifts:
            d = np.hypot(P[:, 0] - mid[0], P[:, 1] - mid[1])
            green = R >= R_GREEN
            dz = np.where(d < R, np.where(green & (d < R - APRON), GREEN_H, APRON_H), dz)
        return dz

    files = {}
    if not builders.empty():
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "r.dae")
            org = np.array([0.0, 0.0, 0.0])
            builders.write_dae(p, name="roundabouts", origin=org)
            files[f"{lv}/art/shapes/roads/roundabouts.dae"] = open(p, "rb").read()
        ob = bng.tsstatic(f"{L}/art/shapes/roads/roundabouts.dae", org, collision=True, decal=True)
        ob["__parent"] = "roundabouts"
        files[f"{lv}/main/MissionGroup/roads/roundabouts/items.level.json"] = (json.dumps(ob, separators=(",", ":"))
                                                                              + "\n").encode()
        r_items = f"{lv}/main/MissionGroup/roads/items.level.json"
        rows = read_items(zi, r_items)
        if not any(r.get("name") == "roundabouts" and r.get("class") == "SimGroup" for r in rows):
            rows.append({"name": "roundabouts", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"})
        files[r_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode()
        mats_name = f"{lv}/art/shapes/roads/main.materials.json"
        mats = json.loads(zi.read(mats_name))
        for m in materials():
            mats[m["name"]] = m
        files[mats_name] = json.dumps(mats, indent=1).encode()
        # objects in the middles
        for name in zi.namelist():
            if not name.endswith("items.level.json") or "/MissionGroup/props/" not in name:
                continue
            rows = read_items(zi, name)
            mine = [isinstance(r.get("position"), list) and len(r["position"]) == 3 and r["position"][2] != 0
                    for r in rows]
            P = [r["position"][:2] for r, m in zip(rows, mine) if m]
            if not P:
                continue
            dzv = iter(lift(P))
            n = 0
            for r, m in zip(rows, mine):
                if m:
                    dz = float(next(dzv))
                    if dz > 0:
                        r["position"] = [r["position"][0], r["position"][1], round(r["position"][2] + dz, 4)]
                        n += 1
            if n:
                rep["objects_raised"] += n
                files[name] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode()
        for name in zi.namelist():
            if not (name.startswith(f"{lv}/forest/") and name.endswith(".forest4.json")):
                continue
            rows = [json.loads(s) for s in zi.read(name).decode().splitlines() if s.strip()]
            if not rows:
                continue
            dzv = lift([r["pos"][:2] for r in rows])
            if not (dzv > 0).any():
                continue
            for r, dz in zip(rows, dzv):
                if dz > 0:
                    r["pos"] = [r["pos"][0], r["pos"][1], round(r["pos"][2] + float(dz), 4)]
            rep["forest_raised"] += int((dzv > 0).sum())
            files[name] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode()
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in files or SHAPE.search(nm):
                continue
            if nm in new_dae:
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[nm])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(n, data)
    rep["seconds"] = round(time.time() - t0)
    print("roundabouts:", {k: v for k, v in rep.items() if k != "list"}, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    roundabouts_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
