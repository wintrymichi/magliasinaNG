"""Automatic checks of a built level (v2.0), run before a release, tile by tile over the whole map:

- terrain over the road meshes: terrain vertices more than TERRAIN_TOL m above the lowest top face
  of the road and bridge meshes over them (a slope poking through the asphalt or a deck);
- the network drivable everywhere: at every station of the swissTLM3D network (network.py, every
  2 m along every road and path) a top face within PROFILE_TOL m of the profile of
  network_surface.py (the face nearest to it where a bridge passes over a road); no bumps of the
  meshes along the stations (second difference over 2 m beyond the profile's above BUMP_TOL m); roads more than FLOAT_TOL m above the
  ground outside the bridges are listed for the review;
- road continuity: vertices of neighbouring road chunks at the same place and different heights;
- trees and shrubs: forest items whose trunk is on a road or path or closer than the clearance of
  clearance.py (1 m roads, 0.5 m paths), and shrubs on the drivable surface;
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
from scipy.spatial import cKDTree
import patch_release as pr
from road_mesh import TriSurface as Surface
from config import LEVEL_DIR

TERRAIN_TOL = 0.10
SEAM_TOL = 0.02
PROFILE_TOL = 0.25
BUMP_TOL = 0.06
FLOAT_TOL = 1.5          # m of a road above the ground under it (listed for the review, no limit)
TILE = 512.0
PLACE_CELL = 40.0
MAX_PLACES = 400
LIMITS = {"terrain_over_road": 0, "road_seams": 0, "trunks_on_surface": 0, "trunks_near_roads": 0,
          "road_faces_under_water": 0,
          "shrubs_on_surface": 0, "network_holes": 0, "network_off_profile": 0, "network_bumps": 0,
          "forest_items": 250_000, "ai_components_over_1km": 1}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica", "check_level.json")
PATH_MATS = ("mp_path_dirt", "mp_path_paved")
SKIP_MATS = ("mp_road_wall", "mp_bridge_parapet")


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
        for xi, yi, zi, si in zip(np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z), np.atleast_1d(score)):
            k = (what, int(xi // PLACE_CELL), int(yi // PLACE_CELL))
            if k not in self.best or si > self.best[k]["score"]:
                self.best[k] = {"what": what, "x": round(float(xi), 1), "y": round(float(yi), 1),
                                "z": round(float(zi), 2), "score": round(float(si), 3), **extra}

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
    counts = {k: 0 for k in ("terrain_over_road", "trunks_on_surface", "trunks_near_roads", "shrubs_on_surface",
                             "network_holes", "network_off_profile", "network_bumps", "network_stations",
                             "network_above_ground")}
    worst = {"terrain_over_road_max_m": 0.0, "network_off_profile_max_m": 0.0, "network_bump_max_m": 0.0}
    for ty in np.arange(np.floor(y0 / TILE) * TILE, y1 + TILE, TILE):
        for tx in np.arange(np.floor(x0 / TILE) * TILE, x1 + TILE, TILE):
            m = (cen[:, 0] > tx - 8) & (cen[:, 0] < tx + TILE + 8) & (cen[:, 1] > ty - 8) & (cen[:, 1] < ty + TILE + 8)
            if not m.any():
                continue
            S = Surface(tri[m])
            # terrain vertices of the tile under a face
            c0, c1 = int(np.floor((tx - ter.x0) / ter.sq)), int(np.ceil((tx + TILE - ter.x0) / ter.sq))
            r0, r1 = int(np.floor((ty - ter.y0) / ter.sq)), int(np.ceil((ty + TILE - ter.y0) / ter.sq))
            c0, r0 = max(c0, 0), max(r0, 0)
            c1, r1 = min(c1, ter.n), min(r1, ter.n)
            if c1 > c0 and r1 > r0:
                X, Y = np.meshgrid(ter.x0 + np.arange(c0, c1) * ter.sq, ter.y0 + np.arange(r0, r1) * ter.sq)
                zt = ter.h[r0:r1, c0:c1].ravel()
                zr = S.height(X.ravel(), Y.ravel(), "low")
                over = zt - zr
                bad = np.isfinite(over) & (over > TERRAIN_TOL)
                counts["terrain_over_road"] += int(bad.sum())
                if bad.any():
                    worst["terrain_over_road_max_m"] = max(worst["terrain_over_road_max_m"], float(over[bad].max()))
                    places.add("terreno sopra la strada", X.ravel()[bad], Y.ravel()[bad], zt[bad], over[bad])
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
                    hole = ~np.isfinite(zm)
                    counts["network_holes"] += int(hole.sum())
                    if hole.any():
                        places.add("buco nella strada", st["x"][i][hole], st["y"][i][hole], zs[i][hole],
                                   np.ones(int(hole.sum())))
                    # a road high above the ground (on a bank or a wall that the data do not have)
                    nb = ~np.array([segs[k]["bridge"] for k in st["seg"][i]], bool)
                    zt_s = ter.sample(st["x"][i], st["y"][i])
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
