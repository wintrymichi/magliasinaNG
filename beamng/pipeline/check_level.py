"""Automatic checks of a built level (v2.0), run before a release, tile by tile over the whole map:

- terrain over the road meshes: the terrain surface more than TERRAIN_TOL m above a top face of the
  road and bridge meshes, sampled on the faces (centre, corners and edges) with the terrain between
  its vertices (the higher of the two diagonals of a terrain square), so a triangle from a vertex
  beside a narrow path that reaches over it counts, not only a vertex under a face;
- the network drivable everywhere: at every station of the swissTLM3D network (network.py, every
  2 m along every road and path) a top face within PROFILE_TOL m of the profile of
  network_surface.py (the face nearest to it where a bridge passes over a road); no bumps of the
  meshes along the stations (second difference over 2 m beyond the profile's above BUMP_TOL m); roads more than FLOAT_TOL m above the
  ground outside the bridges are listed for the review;
- road faces under the ground: top faces more than UNDER_TOL m under the lowest bare ground
  (swissALTI3D) within 1 m of them (a surface given the height of a line it is not on: the terrain
  carve would open a pit around it);
- road continuity: vertices of neighbouring road chunks at the same place and different heights;
- holes in the terrain: vertices more than PIT_TOL m under the bare ground outside the lake;
- obstacles on the carriageway: from every station to the next, on the axis and half way to each
  edge (of the median width of the line), OBST_Z m over the surface a car drives on, no mesh with collision is crossed (a deck, parapet
  or culvert block across a road, a pier, a wall, a building, a step of the surface), roads and
  paths counted apart;
- trees and shrubs: forest items whose trunk is on a road or path or closer than the clearance of
  clearance.py (1 m roads, 0.5 m paths), and shrubs on the drivable surface;
- crowns and ground (canopy.check): crowns in the clearance profile of the roads (4.5 m over the
  carriageways, 2.5 m over sidewalks, yards and paths), trunks inside walls, buildings, parapets,
  guardrails, fences or street furniture, plants floating over the ground or sunk into it;
- AI network: connected components of the AI roads (ends closer than 3 m are joined);
- forest item count and the size of the level folder.
Prints a table and writes beamng/verifica/check_level.json with the counts and the places of the
problems (worst first, one per PLACE_CELL m; review_map.py draws them); exit code 1 when a limit is
exceeded.
    python check_level.py [level folder]
"""
import glob, json, os, sys
import numpy as np
import shapely
import patch_release as pr
from road_mesh import TriSurface as Surface
from config import LEVEL_DIR

TERRAIN_TOL = 0.10
SEAM_TOL = 0.02
PROFILE_TOL = 0.25
BUMP_TOL = 0.06
FLOAT_TOL = 1.5          # m of a road above the ground under it (listed for the review, no limit)
UNDER_TOL = 1.25         # m of a road face under the lowest bare ground within 1 m
OBST_Z = (0.5, 1.6)      # m over the profile: a car along a road or path crosses no mesh up to its roof
PIT_TOL = 20.0           # m of terrain under the bare ground (a hole in the terrain)
LAKE_Z = 271.5           # m, the DTM up to here is the lake and its shore (the lake bed lies under it)
OBST_GROUPS = ("roads/surfaces", "roads/guardrails", "roads/fences", "walls", "buildings", "props", "railway")
OBST_WHAT = ("ponte o gradino", "guardrail", "recinzione", "muro", "edificio", "oggetto", "binario")
TILE = 512.0
PLACE_CELL = 40.0
MAX_PLACES = 400
# release gates. Zero where nothing may be left (vegetation on the roads, roads under the lake);
# for the surfaces, the places the data themselves contradict (a swissTLM3D path drawn inside
# the survey polygon of a street below it, the edge of a facet on a chunk line, a yard whose survey
# polygon takes in a steep bank) are few and listed for the review, so the gates catch a build that
# went wrong, not every one of them: before the carve on the faces the terrain stood over 54 648
# samples of them, and faces lay up to 7.5 m under the ground. Obstacles: before the cuts of walls
# and buildings 127 road and 1053 path stations; left are steps between surfaces at junctions, the
# walls and posts of the checked route of v1.x where side streets meet it, and on paths mostly
# steps (stairs, a path at the foot of a wall).
LIMITS = {"terrain_over_road": 50, "terrain_over_road_max_m": 1.5, "road_seams": 200,
          "trunks_on_surface": 0, "trunks_near_roads": 0, "shrubs_on_surface": 0, "road_faces_under_water": 0,
          "road_faces_under_ground": 500, "road_faces_under_ground_max_m": 3.0,
          "network_holes": 10, "network_off_profile": 500, "network_off_profile_max_m": 3.0,
          "network_bumps": 7000, "network_bump_max_m": 5.0, "terrain_pits": 0,
          "road_obstacles": 30, "path_obstacles": 160,
          "forest_items": 250_000, "ai_components_over_1km": 1,
          # v2.1 (canopy.py): what is left is at the tolerance of the rule (0.3 m of crown over an edge)
          "crowns_in_profile": 10, "trunks_in_solids": 10, "forest_floating": 0, "forest_buried": 10}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica", "check_level.json")
PATH_MATS = ("mp_path_dirt", "mp_path_paved")
SKIP_MATS = ("mp_road_wall", "mp_bridge_parapet")


def terrain_top(ter, x, y):
    """Height of the terrain surface at (x, y): the higher of the two ways a terrain square can be
    split into triangles."""
    c = (np.asarray(x) - ter.x0) / ter.sq
    r = (np.asarray(y) - ter.y0) / ter.sq
    c0 = np.clip(np.floor(c).astype(np.int64), 0, ter.n - 2)
    r0 = np.clip(np.floor(r).astype(np.int64), 0, ter.n - 2)
    fc, fr = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
    z00, z10, z01, z11 = ter.h[r0, c0], ter.h[r0, c0 + 1], ter.h[r0 + 1, c0], ter.h[r0 + 1, c0 + 1]
    a = np.where(fc >= fr, z00 + fc * (z10 - z00) + fr * (z11 - z10), z00 + fr * (z01 - z00) + fc * (z11 - z01))
    b = np.where(fc + fr <= 1, z00 + fc * (z10 - z00) + fr * (z01 - z00),
                 z11 + (1 - fc) * (z01 - z11) + (1 - fr) * (z10 - z11))
    return np.maximum(a, b)


def face_samples(T):
    """Points on every face (k, 3, 3): the centre, near every corner and near every edge middle."""
    c = T.mean(1)
    pts = [c] + [0.75 * T[:, i] + 0.25 * c for i in range(3)] + \
          [0.8 * (0.5 * (T[:, i] + T[:, (i + 1) % 3])) + 0.2 * c for i in range(3)]
    return np.concatenate(pts)


def solid_meshes(lv):
    """Triangles (k, 3, 3) of every mesh of the level a car collides with and the index in
    OBST_GROUPS of each: the pipeline's own shapes (roads and bridges, walls, buildings, guardrails,
    fences, OSM signs, railway); the vanilla props of the route are not in the level folder (checked
    in v1.x)."""
    tris, grp = [], []
    for gi, g in enumerate(OBST_GROUPS):
        for dp, _, fs in os.walk(os.path.join(lv, "main", "MissionGroup", *g.split("/"))):
            if "items.level.json" not in fs:
                continue
            for o in pr.items(os.path.join(dp, "items.level.json")):
                if o.get("class") != "TSStatic" or o.get("collisionType") == "None":
                    continue
                path = os.path.join(lv, *o["shapeName"].split("/")[3:])
                if not os.path.exists(path) or o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1]) != [1, 0, 0, 0, 1,
                                                                                                         0, 0, 0, 1]:
                    continue
                V, N, T, C, parts = pr.read_dae(path)
                Vw = V * np.array(o.get("scale", [1, 1, 1]), float) + np.array(o.get("position", [0, 0, 0]), float)
                for mat, idx in parts:
                    t = Vw[idx[:, 0].reshape(-1, 3)].astype(np.float32)
                    tris.append(t)
                    grp.append(np.full(len(t), gi, np.int8))
    if not tris:
        return np.zeros((0, 3, 3), np.float32), np.zeros(0, np.int8)
    return np.concatenate(tris), np.concatenate(grp)


def segment_hits(A, B, T, cell=4.0, batch=2_000_000):
    """Index of a triangle of T (k, 3, 3) that the segment A[i] -> B[i] crosses (Moller-Trumbore),
    -1 where it crosses none. Triangles and segments meet in the cells of a cell m grid."""
    out = np.full(len(A), -1, np.int64)
    if not len(A) or not len(T):
        return out
    M = 2_000_003                                       # cell key: cx * M + cy

    def cells(lo, hi, ids):
        lo = np.floor(lo / cell).astype(np.int64)
        hi = np.floor(hi / cell).astype(np.int64)
        nx, ny = hi[:, 0] - lo[:, 0] + 1, hi[:, 1] - lo[:, 1] + 1
        cnt = nx * ny
        rep = np.repeat(ids, cnt)
        j = np.repeat(np.arange(len(ids)), cnt)
        k = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        return (lo[j, 0] + k % nx[j]) * M + lo[j, 1] + k // nx[j], rep
    tkey, tid = cells(T[:, :, :2].min(1), T[:, :, :2].max(1), np.arange(len(T)))
    order = np.argsort(tkey, kind="stable")
    tkey, tid = tkey[order], tid[order]
    skey, sid = cells(np.minimum(A[:, :2], B[:, :2]), np.maximum(A[:, :2], B[:, :2]), np.arange(len(A)))
    a = np.searchsorted(tkey, skey, "left")
    n = np.searchsorted(tkey, skey, "right") - a
    csum = np.cumsum(n)
    start = 0
    while start < len(skey):
        end = max(int(np.searchsorted(csum, (csum[start - 1] if start else 0) + batch, "right")), start + 1)
        nn = n[start:end]
        if nn.sum():
            ps = np.repeat(sid[start:end], nn)
            pt = tid[np.repeat(a[start:end], nn) + np.arange(int(nn.sum())) - np.repeat(np.cumsum(nn) - nn, nn)]
            P0, d = A[ps], B[ps] - A[ps]
            Tp = T[pt].astype(np.float64)
            V0 = Tp[:, 0]
            e1, e2 = Tp[:, 1] - V0, Tp[:, 2] - V0
            del Tp
            p = np.cross(d, e2)
            det = (e1 * p).sum(1)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = P0 - V0
            u = (tv * p).sum(1) * inv
            q = np.cross(tv, e1)
            v = (d * q).sum(1) * inv
            t = (e2 * q).sum(1) * inv
            hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)
            out[ps[hit]] = pt[hit]
        start = end
    return out


def obstacles(lv, net, places, zsurf=None):
    """Obstacles on the network: from every station to the next of its line, on the axis and half way
    to each edge of the carriageway, OBST_Z m over the surface a car drives on there (zsurf: the top
    face nearest to the profile at every station, the profile where none), a car crosses no mesh (a
    deck, a parapet or a culvert block across a road, a pier, a wall, a building). Counts of the road
    and path stations with one, by what is hit."""
    segs, st, zs = net
    if zsurf is not None:
        zs = np.where(np.isfinite(zsurf), zsurf, zs)
    T, G = solid_meshes(lv)
    print("solid mesh triangles", len(T), flush=True)
    i = np.flatnonzero((st["seg"][1:] == st["seg"][:-1]) & np.isfinite(zs[1:]) & np.isfinite(zs[:-1]))
    j = i + 1
    dx, dy = st["x"][j] - st["x"][i], st["y"][j] - st["y"][i]
    ln = np.maximum(np.hypot(dx, dy), 1e-9)
    # the width of the line (its median, as the cuts of walls and buildings take it): at a junction the
    # carriageway of a station widens, the way of a car along the line does not
    wmed = np.array([np.median(st["width"][q["first"]:q["first"] + q["n"]]) for q in segs])[st["seg"][i]]
    ox, oy = -dy / ln * 0.25 * wmed, dx / ln * 0.25 * wmed
    A, B = [], []
    for side in (0.0, -1.0, 1.0):
        for h in OBST_Z:
            A.append(np.column_stack([st["x"][i] + side * ox, st["y"][i] + side * oy, zs[i] + h]))
            B.append(np.column_stack([st["x"][j] + side * ox, st["y"][j] + side * oy, zs[j] + h]))
    k = segment_hits(np.concatenate(A), np.concatenate(B), T).reshape(-1, len(i))
    first = np.full(len(i), -1, np.int64)
    for row in k:
        first = np.where(first < 0, row, first)
    road = np.array([s["kind"] == "road" for s in segs])[st["seg"][i]]
    hit = first >= 0
    res = {"road_obstacles": int((hit & road).sum()), "path_obstacles": int((hit & ~road).sum())}
    by = {}
    for is_road, what in ((True, "ostacolo sulla strada"), (False, "ostacolo sul sentiero")):
        for g, name in enumerate(OBST_WHAT):
            sel = hit & (road == is_road)
            sel[sel] = G[first[sel]] == g
            if sel.any():
                by["%s: %s" % ("strade" if is_road else "sentieri", name)] = int(sel.sum())
                # the review looks along the line from behind (compass azimuth of the camera)
                az = np.round((np.degrees(np.arctan2(dx[sel], dy[sel])) + 180.0) % 360.0, 1)
                places.add(what, st["x"][i][sel], st["y"][i][sel], zs[i][sel], np.full(int(sel.sum()), 1.0 + is_road),
                           cosa=name, az=az)
    res["obstacles_by_kind"] = by
    return res


def terrain_pits(ter, bare, places, filled=None):
    """Terrain vertices more than PIT_TOL m under the bare ground (swissALTI3D 0.5 m, nearest cell;
    not the cells filled from Copernicus, `filled`) where the ground is above the lake: a height the
    terrain was given by mistake (a wall measured beyond the edge of the DTM lowered it by 300 m once)."""
    a = bare.a if bare.a.ndim == 2 else bare.a[0]
    cols = np.floor((ter.x0 + np.arange(ter.n) * ter.sq - bare.x_min) / bare.res).astype(np.int64)
    cc = np.flatnonzero((cols >= 0) & (cols < a.shape[1]))
    n, worst = 0, 0.0
    for r0 in range(0, ter.n, 256):
        rows = np.floor((bare.y_max - (ter.y0 + np.arange(r0, min(r0 + 256, ter.n)) * ter.sq)) / bare.res).astype(np.int64)
        rr = np.flatnonzero((rows >= 0) & (rows < a.shape[0]))
        if not len(rr) or not len(cc):
            continue
        D = np.asarray(a[rows[rr][:, None], cols[cc][None, :]], np.float64)
        d = D - ter.h[r0 + rr][:, cc]
        bad = np.isfinite(D) & (D > LAKE_Z) & (d > PIT_TOL)
        if filled is not None:
            bad &= ~np.asarray(filled[rows[rr][:, None], cols[cc][None, :]], bool)
        if bad.any():
            n += int(bad.sum())
            worst = max(worst, float(d[bad].max()))
            i, j = np.nonzero(bad)
            places.add("buco nel terreno", ter.x0 + cc[j] * ter.sq, ter.y0 + (r0 + rr[i]) * ter.sq,
                       ter.h[r0 + rr[i], cc[j]], d[bad])
    return {"terrain_pits": n, "terrain_pit_max_m": round(worst, 2)}


def road_tops(lv):
    """Top faces (k, 3, 3) of every road/bridge mesh with the material of each and the chunk."""
    tris, mats, chunks = [], [], []
    for n, it in enumerate(pr.items(os.path.join(lv, "main", "MissionGroup", "roads", "surfaces", "items.level.json"))):
        path = os.path.join(lv, *it["shapeName"].split("/")[3:])
        V, N, T, C, parts = pr.read_dae(path)
        Vw = V + np.array(it["position"])
        for mat, idx in parts:
            if mat in SKIP_MATS:
                continue
            tri = Vw[idx[:, 0].reshape(-1, 3)]
            nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            up = nrm[:, 2] / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12) > 0.5
            tris.append(tri[up])
            mats.append(np.full(int(up.sum()), mat in PATH_MATS))
            chunks.append(np.full(int(up.sum()), n, np.int32))
    return np.concatenate(tris), np.concatenate(mats), np.concatenate(chunks)


class Places:
    """Problem places, the worst per PLACE_CELL m cell and kind."""

    def __init__(self):
        self.best = {}

    def add(self, what, x, y, z, score, **extra):
        """extra: fields of the places, one value for all or an array with one per place."""
        for n, (xi, yi, zi, si) in enumerate(zip(np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z),
                                                 np.atleast_1d(score))):
            k = (what, int(xi // PLACE_CELL), int(yi // PLACE_CELL))
            if k not in self.best or si > self.best[k]["score"]:
                ex = {a: (v[n].item() if isinstance(v, np.ndarray) else v) for a, v in extra.items()}
                self.best[k] = {"what": what, "x": round(float(xi), 1), "y": round(float(yi), 1),
                                "z": round(float(zi), 2), "score": round(float(si), 3), **ex}

    def list(self):
        rows = sorted(self.best.values(), key=lambda r: -r["score"])
        per = {}
        out = []
        for r in rows:                                   # every kind gets its share of the list
            per[r["what"]] = per.get(r["what"], 0) + 1
            if per[r["what"]] <= MAX_PLACES // 4:
                out.append(r)
        return out[:MAX_PLACES]


def main(lv=None):
    lv = lv or LEVEL_DIR
    res, places = {}, Places()
    tri, is_path, chunk = road_tops(lv)
    print("road top faces", len(tri), flush=True)
    ter = pr.Terrain(lv)
    # forest
    items = []
    for f in glob.glob(os.path.join(lv, "forest", "*.forest4.json")):
        name = os.path.basename(f).replace(".forest4.json", "")
        shrub = "bush" in name or "hedge" in name
        for o in pr.items(f):
            items.append((o["pos"][0], o["pos"][1], o["pos"][2], shrub))
    res["forest_items"] = len(items)
    F = np.array(items, np.float64).reshape(-1, 4)
    import canopy
    res.update(canopy.check(lv, places))
    print("canopy:", {k: v for k, v in res.items() if k != "forest_items"}, flush=True)
    # network stations and their profile
    net = None
    try:
        import network
        import network_surface
        segs, st, _ = network.load()
        zs = network_surface.load()["z"]
        net = (segs, st, zs)
    except Exception as e:                                # a level without the v2.0 network data
        print("no network data:", e)
    cen = tri[:, :, :2].mean(1)
    x0, y0 = cen.min(0)
    x1, y1 = cen.max(0)
    zsurf = np.full(len(net[1]["x"]), np.nan) if net is not None else None     # the surface at every station
    counts = {k: 0 for k in ("terrain_over_road", "trunks_on_surface", "trunks_near_roads", "shrubs_on_surface",
                             "network_holes", "network_off_profile", "network_bumps", "network_stations",
                             "network_above_ground")}
    worst = {"terrain_over_road_max_m": 0.0, "network_off_profile_max_m": 0.0, "network_bump_max_m": 0.0}
    # the bare ground (swissALTI3D): what a road is compared with to tell it stands on a bank or a wall
    # the data do not have (the terrain itself is carved under and beside the roads and walls)
    try:
        from config import WORK
        from geo import Grid
        bare = Grid.load(os.path.join(WORK, "dtm05.npz"))
    except FileNotFoundError as e:                       # a level checked without the work data
        print("no DTM, the terrain stands for the ground:", e)
        bare = None
    for ty in np.arange(np.floor(y0 / TILE) * TILE, y1 + TILE, TILE):
        for tx in np.arange(np.floor(x0 / TILE) * TILE, x1 + TILE, TILE):
            m = (cen[:, 0] > tx - 8) & (cen[:, 0] < tx + TILE + 8) & (cen[:, 1] > ty - 8) & (cen[:, 1] < ty + TILE + 8)
            if not m.any():
                continue
            S = Surface(tri[m])
            # the terrain over the faces of the tile
            own = (cen[:, 0] >= tx) & (cen[:, 0] < tx + TILE) & (cen[:, 1] >= ty) & (cen[:, 1] < ty + TILE)
            if own.any():
                P = face_samples(tri[own])
                zt = terrain_top(ter, P[:, 0], P[:, 1])
                over = zt - P[:, 2]
                bad = over > TERRAIN_TOL
                counts["terrain_over_road"] += int(bad.sum())
                if bad.any():
                    worst["terrain_over_road_max_m"] = max(worst["terrain_over_road_max_m"], float(over[bad].max()))
                    places.add("terreno sopra la strada", P[bad, 0], P[bad, 1], zt[bad], over[bad])
            # network stations of the tile
            if net is not None:
                segs, st, zs = net
                sm = (st["x"] >= tx) & (st["x"] < tx + TILE) & (st["y"] >= ty) & (st["y"] < ty + TILE)
                i = np.flatnonzero(sm)
                if len(i):
                    counts["network_stations"] += len(i)
                    zm = S.height(st["x"][i], st["y"][i], "near", zs[i])
                    # a station on the seam between two meshes (a deck end, the edge of a strip)
                    # falls in the sub-millimetre crack of the rounded vertices: look 3 cm around
                    for dx, dy in ((0.03, 0), (-0.03, 0), (0, 0.03), (0, -0.03)):
                        miss = ~np.isfinite(zm)
                        if not miss.any():
                            break
                        zm[miss] = S.height(st["x"][i][miss] + dx, st["y"][i][miss] + dy, "near", zs[i][miss])
                    zsurf[i] = zm
                    hole = ~np.isfinite(zm)
                    counts["network_holes"] += int(hole.sum())
                    if hole.any():
                        places.add("buco nella strada", st["x"][i][hole], st["y"][i][hole], zs[i][hole],
                                   np.ones(int(hole.sum())))
                    # a road high above the ground (on a bank or a wall that the data do not have)
                    nb = ~np.array([segs[k]["bridge"] for k in st["seg"][i]], bool)
                    zt_s = ter.sample(st["x"][i], st["y"][i])
                    if bare is not None:
                        zb = bare.sample(st["x"][i], st["y"][i])
                        zt_s = np.where(np.isfinite(zb), zb, zt_s)
                    up = nb & np.isfinite(zm) & (zm - zt_s > FLOAT_TOL)
                    counts["network_above_ground"] += int(up.sum())
                    if up.any():
                        places.add("strada staccata dal terreno", st["x"][i][up], st["y"][i][up], zm[up],
                                   (zm - zt_s)[up])
                    dz = np.abs(zm - zs[i])
                    off = np.isfinite(dz) & (dz > PROFILE_TOL)
                    counts["network_off_profile"] += int(off.sum())
                    if off.any():
                        worst["network_off_profile_max_m"] = max(worst["network_off_profile_max_m"], float(dz[off].max()))
                        places.add("strada fuori profilo", st["x"][i][off], st["y"][i][off], zm[off], dz[off])
                    # bumps: second difference along each segment (stations 2 m apart, consecutive)
                    seg = st["seg"][i]
                    same = (seg[1:-1] == seg[:-2]) & (seg[1:-1] == seg[2:]) & (np.diff(i)[:-1] == 1) & (np.diff(i)[1:] == 1)
                    # the mesh's own bumps: its second difference beyond the profile's (a path over
                    # a hump keeps the hump)
                    zp = zs[i]
                    d2 = np.abs((zm[:-2] - 2 * zm[1:-1] + zm[2:]) - (zp[:-2] - 2 * zp[1:-1] + zp[2:]))
                    bump = same & np.isfinite(d2) & (d2 > BUMP_TOL)
                    counts["network_bumps"] += int(bump.sum())
                    if bump.any():
                        worst["network_bump_max_m"] = max(worst["network_bump_max_m"], float(d2[bump].max()))
                        k = i[1:-1][bump]
                        places.add("gradino o dosso", st["x"][k], st["y"][k], zm[1:-1][bump], d2[bump])
            # trees and shrubs of the tile
            fm = (F[:, 0] >= tx) & (F[:, 0] < tx + TILE) & (F[:, 1] >= ty) & (F[:, 1] < ty + TILE)
            if fm.any():
                P = F[fm]
                on = np.isfinite(S.height(P[:, 0], P[:, 1], "high"))
                shrub = P[:, 3] > 0
                near = np.zeros(len(P), bool)
                for kind_path, rad in ((False, 0.95), (True, 0.45)):
                    sel = is_path[m] == kind_path
                    if not sel.any():
                        continue
                    Sk = Surface(tri[m][sel])
                    for a in np.linspace(0, 2 * np.pi, 12, endpoint=False):
                        near |= np.isfinite(Sk.height(P[:, 0] + rad * np.cos(a), P[:, 1] + rad * np.sin(a), "high"))
                t_on, t_near, s_on = on & ~shrub, near & ~on & ~shrub, on & shrub
                counts["trunks_on_surface"] += int(t_on.sum())
                counts["trunks_near_roads"] += int(t_near.sum())
                counts["shrubs_on_surface"] += int(s_on.sum())
                for what, sel in (("albero sulla strada", t_on), ("albero a bordo strada", t_near),
                                  ("arbusto sulla strada", s_on)):
                    if sel.any():
                        places.add(what, P[sel, 0], P[sel, 1], P[sel, 2], np.ones(int(sel.sum())))
        print("  tiles of row y=%.0f done" % ty, flush=True)
    res.update(counts)
    res.update({k: round(v, 3) for k, v in worst.items()})
    # roads under the lake: top faces inside a water block and below its surface
    blocks = []
    wf = os.path.join(lv, "main", "MissionGroup", "level_objects", "Water", "items.level.json")
    for o in (pr.items(wf) if os.path.exists(wf) else []):
        if o.get("class") == "WaterBlock":
            (bx, by, bz), (sx, sy, _) = o["position"], o.get("scale", [1, 1, 1])
            blocks.append((bx - sx / 2, by - sy / 2, bx + sx / 2, by + sy / 2, bz))
    wet = np.zeros(len(tri), bool)
    c3 = tri.mean(1)
    for x0_, y0_, x1_, y1_, bz in blocks:
        wet |= (c3[:, 0] > x0_) & (c3[:, 0] < x1_) & (c3[:, 1] > y0_) & (c3[:, 1] < y1_) & (c3[:, 2] < bz + 0.05)
    res["road_faces_under_water"] = int(wet.sum())
    if wet.any():
        places.add("strada sott'acqua", c3[wet, 0], c3[wet, 1], c3[wet, 2], np.ones(int(wet.sum())))
    if bare is not None:
        f = os.path.join(WORK, "dtm05_nodata.npy")
        res.update(terrain_pits(ter, bare, places, np.load(f, mmap_mode="r") if os.path.exists(f) else None))
    if net is not None:
        res.update(obstacles(lv, net, places, zsurf))
    # road faces under the bare ground, band by band of the DTM
    under = np.zeros(len(tri), bool)
    dz_under = np.zeros(len(tri))
    if bare is not None:
        from scipy.ndimage import minimum_filter
        dtm = bare
        gx0, gy0, gx1, gy1 = dtm.bounds()
        for yb in np.arange(np.floor(c3[:, 1].min() / TILE) * TILE, c3[:, 1].max() + TILE, TILE):
            sel = np.flatnonzero((c3[:, 1] >= yb) & (c3[:, 1] < yb + TILE) & (c3[:, 0] > gx0 + 2) & (c3[:, 0] < gx1 - 2)
                                 & (c3[:, 1] > gy0 + 2) & (c3[:, 1] < gy1 - 2))
            if not len(sel):
                continue
            sub, _, _ = dtm.window(c3[sel, 0].min() - 2, yb - 2, c3[sel, 0].max() + 2, yb + TILE + 2, pad=4)
            sub.a = minimum_filter(np.asarray(sub.a, np.float32), size=5)
            d = sub.sample(c3[sel, 0], c3[sel, 1]) - c3[sel, 2]
            dz_under[sel] = np.nan_to_num(d, nan=0.0)
        under = dz_under > UNDER_TOL
    res["road_faces_under_ground"] = int(under.sum())
    res["road_faces_under_ground_max_m"] = round(float(dz_under.max()), 3) if len(dz_under) else 0.0
    if under.any():
        places.add("strada sotto il terreno", c3[under, 0], c3[under, 1], c3[under, 2], dz_under[under])
    # seams: the same vertex position in two chunks with different heights
    P = tri.reshape(-1, 3)
    ch = np.repeat(chunk, 3)
    key = np.round(P[:, :2] / 0.005).astype(np.int64)
    order = np.lexsort((key[:, 1], key[:, 0]))
    k2, z2, c2 = key[order], P[order, 2], ch[order]
    same = (k2[1:] == k2[:-1]).all(1) & (c2[1:] != c2[:-1])
    dz = np.abs(z2[1:] - z2[:-1])
    bad = same & (dz > SEAM_TOL) & (dz < 1.0)            # more than 1 m apart: a deck over a road
    res["road_seams"] = int(bad.sum())
    res["road_seams_max_m"] = round(float(dz[bad].max()) if bad.any() else 0.0, 3)
    if bad.any():
        q = P[order][1:][bad]
        places.add("giunzione tra pezzi", q[:, 0], q[:, 1], q[:, 2], dz[bad])
    # AI network components
    ai = [o for o in pr.items(os.path.join(lv, "main", "MissionGroup", "AIRoads", "items.level.json"))
          if o.get("class") == "DecalRoad"]
    parent = list(range(len(ai)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    if ai:
        lines = [shapely.LineString(np.array(o["nodes"])[:, :2]) for o in ai]
        tree = shapely.STRtree(lines)
        for k, o in enumerate(ai):
            n = np.array(o["nodes"])[:, :2]
            for p in (n[0], n[-1]):
                for j in tree.query(shapely.Point(p).buffer(3.0), predicate="intersects"):
                    ra, rb = find(k), find(int(j))
                    if ra != rb:
                        parent[ra] = rb
        comp = {}
        for k in range(len(ai)):
            comp[find(k)] = comp.get(find(k), 0) + lines[k].length
        big = sorted(comp.values(), reverse=True)
        res["ai_roads"] = len(ai)
        res["ai_components"] = len(big)
        res["ai_components_over_1km"] = sum(1 for v in big if v > 1000)
        res["ai_largest_km"] = round(big[0] / 1000, 1) if big else 0
        if net is not None:
            # the drivable swissTLM3D roads are not all joined inside the area (some pieces meet
            # only through paths or outside it): the AI network may have as many big pieces
            import scipy.sparse as sps
            from scipy.sparse.csgraph import connected_components
            import ai_roads
            segs = net[0]
            E = [(s["nodes"][0], s["nodes"][1], s["length"]) for s in segs
                 if s["kind"] == "road" and s["class"] in ai_roads.TLM_DRIVE]
            nn = 1 + max(max(e[0], e[1]) for e in E)
            _, lab = connected_components(sps.coo_matrix((np.ones(len(E)), ([e[0] for e in E], [e[1] for e in E])),
                                                         shape=(nn, nn)), directed=False)
            L = {}
            for a, b, l in E:
                L[lab[a]] = L.get(lab[a], 0) + l
            LIMITS["ai_components_over_1km"] = sum(1 for v in L.values() if v > 1000)
            res["network_road_pieces_over_1km"] = LIMITS["ai_components_over_1km"]
    size = 0
    for dp, _, fs in os.walk(lv):
        size += sum(os.path.getsize(os.path.join(dp, f)) for f in fs)
    res["level_size_mb"] = round(size / 1e6, 1)
    bad = {k: v for k, v in res.items() if k in LIMITS and v > LIMITS[k]}
    res["failed"] = sorted(bad)
    res["places"] = places.list()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)
    for k, v in res.items():
        if k == "places":
            continue
        flag = "  <-- over the limit %s" % LIMITS[k] if k in bad else ""
        print("%-28s %s%s" % (k, v, flag))
    print(len(res["places"]), "places listed in", OUT)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
