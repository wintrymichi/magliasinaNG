"""v3.0: two bridge decks side by side that are one bridge.

Where the network has two lines crossing the same river a few metres apart (the Via Cantonale and its slip road
over the Magliasina between Magliaso and Caslano), each got its own deck with its own parapets, and the river
showed in the gap between them: in reality one wide slab carries both. The places are listed in
dati/ponti_fill.json (a box each, reviewed by hand on the orthophoto and the panoramas):
- the decks there are the road top faces standing more than "min_height" over the terrain; the two (or more)
  largest are the bridge;
- the gap between them (their convex hull less themselves) gets a slab: a paved top at the height of the decks
  on both sides (weighted by the distance to each), its underside SLAB m lower, its open sides down into the
  ground; a parapet along the open sides where the ground beside drops more than PARAPET_DROP;
- the parapets and the side faces of the decks inside the gap are taken out; the street furniture standing in
  the gap is put on the slab and the plants there are taken out.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish bridge_fill
"""
import json, os, re, tempfile, time, zipfile
import numpy as np
import shapely
from scipy.spatial import cKDTree
import bng
import optimize_level
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE
from markings_net import read_items
from walls import read_ter
import bridges

HERE = os.path.dirname(os.path.abspath(__file__))
PLACES = os.path.join(os.path.dirname(HERE), "dati", "ponti_fill.json")
SLAB = bridges.SLAB
PARAPET_DROP = bridges.PARAPET_DROP
PARAPET_H = bridges.PARAPET
PARAPET_W = bridges.PARAPET_W
CUT = ("mp_bridge_parapet", "mp_road_wall")      # faces of the decks taken out in the gap
SEG = 1.0                                        # m between the vertices along the sides of the slab
MIN_DECK = 40.0                                  # m2: a smaller piece over the ground is no deck
SHAPE = re.compile(r"art/shapes/roads/bridge_fill_[^/]+\.dae$")


def places():
    return json.load(open(PLACES, encoding="utf-8"))["places"] if os.path.exists(PLACES) else []


def terrain(zi, lv):
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    q = read_ter(zi.read(f"{lv}/theTerrain.ter"))[1]
    H = Z0 + q.astype(np.float64) / 65535.0 * MAXH
    n = H.shape[0]

    def at(x, y):
        fx, fy = (np.asarray(x) - TER_X0) / TER_SQUARE, (np.asarray(y) - TER_Y0) / TER_SQUARE
        c = np.clip(np.floor(fx).astype(np.int64), 0, n - 2)
        r = np.clip(np.floor(fy).astype(np.int64), 0, n - 2)
        u, v = np.clip(fx - c, 0, 1), np.clip(fy - r, 0, 1)
        return (H[r, c] * (1 - u) * (1 - v) + H[r, c + 1] * u * (1 - v) + H[r + 1, c] * (1 - u) * v
                + H[r + 1, c + 1] * u * v)
    return at


def surfaces(zi, lv, box):
    """[(shape name, object position, material, triangle indices (k,) in the shape part, triangles (k, 3, 3))]
    of the road surface shapes with faces in the box."""
    x0, y0, x1, y1 = box
    out = []
    for o in read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + pos
        for pi, (mat, idx) in enumerate(parts):
            T = W[idx[:, 0]].reshape(-1, 3, 3)
            c = T.mean(1)
            k = np.flatnonzero((c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1))
            if len(k):
                out.append((sn, pi, mat, k, T[k]))
    return out


def fill_place(zi, lv, pl, ground, B, rep):
    """The slab of one place into the MeshBuilder B; returns (fill polygon, {shape: {part: triangles to drop}},
    height function)."""
    found = surfaces(zi, lv, pl["box"])
    tops, alltops, drop = [], [], {}
    for sn, pi, mat, k, T in found:
        if mat in CUT:
            continue
        up = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, 2] > 0
        c = T.mean(1)
        hi = c[:, 2] - ground(c[:, 0], c[:, 1])
        tops.append(T[up & (hi > pl.get("min_height", 1.0))])
        alltops.append(T[up])
    T = np.concatenate(tops)
    A = np.concatenate(alltops)
    roads = shapely.union_all([shapely.Polygon(t[:, :2]).buffer(0.02) for t in A])
    polys = shapely.union_all([shapely.Polygon(t[:, :2]) for t in T if abs(shapely.Polygon(t[:, :2]).area) > 1e-4])
    decks = sorted([g for g in getattr(polys, "geoms", [polys]) if g.area > MIN_DECK], key=lambda g: -g.area)
    decks = decks[:pl.get("decks", 2)]
    if len(decks) < 2:
        rep["skipped"].append(pl["name"])
        return None, drop, None
    both = shapely.union_all(decks)
    fill = both.convex_hull.difference(roads)                          # not over a road at grade either
    fill = max(getattr(fill, "geoms", [fill]), key=lambda g: g.area)
    # the slab reaches 0.1 m under the decks (no crack), just below their tops
    fill = fill.buffer(0.1, join_style="mitre").intersection(both.convex_hull)
    fill = fill if fill.geom_type == "Polygon" else max(fill.geoms, key=lambda g: g.area)
    fill = shapely.segmentize(fill, SEG)
    # heights: the road surfaces at the level of the decks all round, the nearest vertices weighted by the
    # inverse square distance
    P = np.unique(np.round(A.reshape(-1, 3), 3), axis=0)
    on = shapely.contains_xy(both.buffer(0.05), T.mean(1)[:, 0], T.mean(1)[:, 1])
    P = P[P[:, 2] > T[on][..., 2].min() - 0.3]                     # not the paths down by the river
    tree = cKDTree(P[:, :2])

    def height(x, y):
        Q = np.column_stack([np.atleast_1d(x), np.atleast_1d(y)])
        dd, kk = tree.query(Q, k=12)
        w = 1.0 / np.maximum(dd, 0.05) ** 2
        return (P[kk, 2] * w).sum(1) / w.sum(1) - 0.01
    tris = shapely.constrained_delaunay_triangles(fill)
    top = []
    for t in tris.geoms:
        p = np.asarray(t.exterior.coords)[:3]
        if not fill.buffer(1e-6).contains(t.centroid):
            continue
        z = height(p[:, 0], p[:, 1])
        tri = np.column_stack([p, z])
        if np.cross(tri[1] - tri[0], tri[2] - tri[0])[2] < 0:
            tri = tri[[0, 2, 1]]
        top.append(tri)
    top = np.array(top)
    V = top.reshape(-1, 3)
    B["top"].add(pl.get("material", "mp_hard_asphalt"), V, uvs=V[:, :2] / 4.0, normals=bng.flat_normals_soup(V))
    bot = top[:, [0, 2, 1]].copy()
    bot[..., 2] -= SLAB
    Vb = bot.reshape(-1, 3)
    B["side"].add("mp_road_wall", Vb, uvs=bng.box_uvs_soup(Vb, 1.6), normals=bng.flat_normals_soup(Vb))
    # the open sides (not along a deck): a face down into the ground, a parapet where the ground drops
    ring = np.asarray(fill.exterior.coords)
    sides, par = [], []
    for a, b in zip(ring[:-1], ring[1:]):
        m = (a + b) / 2
        if both.buffer(0.3).contains(shapely.Point(m)):
            continue
        za, zb = height(a[0], a[1])[0], height(b[0], b[1])[0]
        ga, gb = ground(a[0], a[1]) - 0.3, ground(b[0], b[1]) - 0.3
        out = np.array([b[1] - a[1], a[0] - b[0]])
        if fill.contains(shapely.Point(m + out / max(np.hypot(*out), 1e-9) * 0.2)):
            out = -out
        out3 = np.r_[out, 0.0]
        sides.append(bridges._quad([*a, za - SLAB], [*b, zb - SLAB], [*b, min(gb, zb - SLAB)],
                                   [*a, min(ga, za - SLAB)], out3))
        fall = (za + zb) / 2 - ground(m[0] + out[0] / np.hypot(*out) * 1.0, m[1] + out[1] / np.hypot(*out) * 1.0)
        if fall > PARAPET_DROP:
            nrm = out / max(np.hypot(*out), 1e-9)
            ai, bi = a - nrm * PARAPET_W, b - nrm * PARAPET_W               # its inner face, on the slab
            par.append(bridges._quad([*a, za - SLAB], [*b, zb - SLAB], [*b, zb + PARAPET_H], [*a, za + PARAPET_H], out3))
            par.append(bridges._quad([*ai, za], [*bi, zb], [*bi, zb + PARAPET_H], [*ai, za + PARAPET_H], -out3))
            par.append(bridges._quad([*a, za + PARAPET_H], [*b, zb + PARAPET_H], [*bi, zb + PARAPET_H],
                                     [*ai, za + PARAPET_H], (0, 0, 1)))
    if sides:
        S = np.concatenate(sides).reshape(-1, 3)
        B["side"].add("mp_road_wall", S, uvs=bng.box_uvs_soup(S, 1.6), normals=bng.flat_normals_soup(S))
    if par:
        S = np.concatenate(par).reshape(-1, 3)
        B["side"].add("mp_bridge_parapet", S, uvs=bng.box_uvs_soup(S, 1.6), normals=bng.flat_normals_soup(S))
    # the parapets and sides of the decks in the gap
    cut = fill.buffer(0.8)
    for sn, pi, mat, k, Tk in found:
        if mat not in CUT:
            continue
        c = Tk.mean(1)
        inside = shapely.contains_xy(cut, c[:, 0], c[:, 1])
        if inside.any():
            drop.setdefault(sn, {}).setdefault(pi, set()).update(int(i) for i in k[inside])
    rep["places"].append({"name": pl["name"], "decks": len(decks), "fill_m2": round(fill.area, 1),
                          "faces_cut": int(sum(len(v) for d in drop.values() for v in d.values()))})
    return fill, drop, height


def bridge_fill_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    ground = terrain(zi, lv)
    rep = {"places": [], "skipped": [], "props_moved": 0, "plants_removed": 0}
    builders = {}
    drops, fills = {}, []
    for i, pl in enumerate(places()):
        B = {"top": bng.MeshBuilder(), "side": bng.MeshBuilder()}
        fill, drop, height = fill_place(zi, lv, pl, ground, B, rep)
        if fill is None:
            continue
        builders[i] = (B, np.r_[np.asarray(fill.centroid.coords[0]), 0.0])
        fills.append((fill, height))
        for sn, d in drop.items():
            for pi, s in d.items():
                drops.setdefault(sn, {}).setdefault(pi, set()).update(s)
    files, objs = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (B, origin) in builders.items():
            for kind, mb in B.items():
                if mb.empty():
                    continue
                rel = f"art/shapes/roads/bridge_fill_{i}_{kind}.dae"
                f = os.path.join(tmp, "s.dae")
                mb.write_dae(f, name=f"bridge_fill_{i}_{kind}", origin=origin)
                files[f"{lv}/{rel}"] = open(f, "rb").read()
                objs.append(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True, decal=(kind == "top")))
    # the faces of the decks in the gaps out of their shapes
    from fuel_stations import drop_triangles
    for sn, d in drops.items():
        files[sn] = drop_triangles(zi.read(sn).decode("utf-8"), d).encode("utf-8")
    # street furniture onto the slab, plants out
    for f in zi.namelist():
        if fills and f.startswith(f"{lv}/main/MissionGroup/props/") and f.endswith("items.level.json"):
            rows, changed = read_items(zi, f), False
            for o in rows:
                p = o.get("position")
                if o.get("class") != "TSStatic" or not p:
                    continue
                for fill, height in fills:
                    if fill.contains(shapely.Point(p[0], p[1])):
                        z = float(height(p[0], p[1])[0]) + 0.01
                        if p[2] < z - 0.05:
                            o["position"] = [p[0], p[1], z]
                            rep["props_moved"] += 1
                            changed = True
            if changed:
                files[f] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in rows) + "\n").encode("utf-8")
        elif fills and f.startswith(f"{lv}/forest/") and f.endswith(".forest4.json"):
            lines = [l for l in zi.read(f).decode("utf-8").splitlines() if l.strip()]
            P = np.array([json.loads(l)["pos"][:2] for l in lines]).reshape(-1, 2)
            out = np.zeros(len(lines), bool)
            for fill, _ in fills:
                out |= shapely.contains_xy(fill.buffer(1.0), P[:, 0], P[:, 1])
            keep = [l for l, o in zip(lines, out) if not o]
            if len(keep) < len(lines):
                rep["plants_removed"] += len(lines) - len(keep)
                files[f] = ("\n".join(keep) + "\n").encode("utf-8")
    sitems = f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"
    rows = [o for o in read_items(zi, sitems) if not SHAPE.search(o.get("shapeName", ""))]
    parent = next((o["__parent"] for o in rows if "__parent" in o), "surfaces")
    for o in objs:
        o["__parent"] = parent
    files[sitems] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in rows + objs) + "\n").encode("utf-8")
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in files or SHAPE.search(i.filename):
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("bridge fill:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    import sys
    bridge_fill_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
