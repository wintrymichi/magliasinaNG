"""Forest items for the measured trees (work/trees.npz).

Model choice per tree (the species cannot be measured from aerial data, so the
choice is driven by measurable shape cues): pointed crown + dark colour -> conifer
(Douglas fir, or cypress when very narrow in gardens); otherwise deciduous
(beech / oak / aspen models) chosen by the height : crown ratio; below 4 m bushes.
Every instance is scaled so its height equals the measured tree height; among the
candidate models the one whose crown width after scaling is closest to the
measured crown diameter is used. Yaw is random (not observable).
Nothing stands on the paved surfaces (clear_paved): the canopy model puts a tree where its crown
peaks, which over a road is often the middle of the carriageway, and the shrub and hedge models
are scaled wider than the gap between the road and the verge. Trees whose trunk is on a paved
surface or within 0.5 m of it are dropped; shrubs and hedges reaching more than 0.2 m over a
paved edge are moved back from it (up to 1.5 m), or dropped (clearance.py).
"""
import json, os
import numpy as np
from config import WORK
import asset_bounds
import bng

from clearance import clear_paved

T = "/levels/east_coast_usa/art/shapes/trees/"   # level copies: their materials are defined
E = "/levels/east_coast_usa/art/shapes/trees/trees_douglasfir/"
I = "/levels/italy/art/shapes/trees/trees_italy/"
MODELS = {
    "deciduous_large": [T + "trees_beech/tree_beech_large_b.dae", T + "trees_beech/tree_beech_forest_b.dae",
                        T + "trees_oak/tree_oak_large_b.dae", T + "trees_oak/tree_oak_forest_a.dae", T + "trees_oak/tree_oak_forest_b.dae",
                        T + "trees_oak/tree_oak_large_a.dae", I + "holm_oak.dae"],
    "deciduous_narrow": [T + "trees_beech/tree_beech_forest_a.dae", T + "trees_aspen/tree_aspen_forest_a.dae",
                         T + "trees_oak/tree_oak_large_c.dae"],
    "deciduous_small": [T + "trees_beech/tree_beech_small_b.dae", T + "trees_beech/tree_beech_small_c.dae",
                        T + "trees_beech/tree_beech_small_d.dae", T + "trees_oak/tree_oak_sml_a.dae", T + "trees_oak/tree_oak_sml_b.dae",
                        T + "trees_aspen/tree_aspen_large_b.dae", T + "trees_aspen/tree_aspen_small_a.dae"],
    "bush": [T + "trees_beech/tree_beech_bush_e.dae", T + "trees_beech/tree_beech_bush_c.dae", T + "trees_oak/tree_oak_bush_b.dae",
             I + "generibush.dae", I + "fluffy_bush.dae"],
    "conifer": [E + "tree_douglasfir_large_a.dae", E + "tree_douglasfir_large_b.dae",
                E + "tree_douglasfir_small_a.dae", E + "tree_douglasfir_small_b.dae"],
    "conifer_narrow": [I + "cypress_tree.dae"],
}


def paved_dist_dir():
    """Signed distance to the meshed paved areas (roadheight.paved_polygons; negative inside)
    and the unit vector away from them."""
    import shapely
    import roadheight
    polys = [g for g, _, _ in roadheight.paved_polygons()]
    tree = shapely.STRtree(polys)
    union = shapely.union_all(polys)
    shapely.prepare(union)
    edge = union.boundary

    def fn(x, y):
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        pts = shapely.points(x, y)
        d = np.full(len(pts), 99.0)
        u = np.tile([1.0, 0.0], (len(pts), 1))
        (ip, ig), dist = tree.query_nearest(pts, max_distance=10.0, return_distance=True, all_matches=False)
        d[ip] = dist
        inside = shapely.contains_xy(union, x, y)
        for i, g in zip(ip, ig):
            if inside[i]:
                a, b = np.asarray(shapely.shortest_line(edge, pts[i]).coords)
                d[i] = -np.hypot(*(b - a))
                v = a - b                                  # towards the outline: out of the paved area
            else:
                a, b = np.asarray(shapely.shortest_line(polys[g], pts[i]).coords)
                v = b - a
            n = np.hypot(*v)
            if n > 1e-9:
                u[i] = v / n
        return d, u[:, 0], u[:, 1]
    return fn


def classify(h, d, sharp, rgb, lc_garden):
    v = rgb.mean(1)
    conifer = (sharp > 0.15) & (v < 72)
    narrow = h / np.maximum(d, 0.5)
    cls = np.full(len(h), "deciduous_large", object)
    cls[narrow > 2.3] = "deciduous_narrow"
    cls[h < 9] = "deciduous_small"
    cls[h < 4] = "bush"
    cls[conifer & (h >= 6)] = "conifer"
    cls[conifer & (h >= 4) & (narrow > 3.0) & lc_garden] = "conifer_narrow"
    return cls


NEAR = 150.0          # m from a road: every tree measured is kept
NEAR_PATH = (60.0, 40.0, 30.0, 20.0, 10.0, 0.0)   # m from a path: the widest that fits the cap
CAP = 250_000         # forest items at most: farther trees are thinned to stay under it
SHRUBS = 12_000       # of them left for the shrubs and hedges (about 10 000 in v2.0)


def thin(x, y, h, dist, cap, dist_path=None):
    """Indices of the trees kept: all within NEAR m of the roads and the widest band of NEAR_PATH
    along the paths that fits, farther the tallest of every cell of a grid coarse enough to stay
    within `cap` items in all."""
    near = dist <= NEAR
    if dist_path is not None:
        for band in NEAR_PATH:
            both = near | (dist_path <= band)
            if both.sum() <= 0.92 * cap:
                break
        near = both
        print("trees: every tree within %.0f m of the roads and %.0f m of the paths" % (NEAR, band))
    far = np.flatnonzero(~near)
    budget = cap - int(near.sum())
    if len(far) <= budget:
        return np.arange(len(x))
    if budget <= 0:
        return np.flatnonzero(near)
    order = far[np.argsort(-h[far])]
    for cell in np.arange(5.0, 60.0, 1.0):
        key = np.floor(x[order] / cell).astype(np.int64) * 1_000_003 + np.floor(y[order] / cell).astype(np.int64)
        _, first = np.unique(key, return_index=True)
        if len(first) <= budget:
            break
    keep_far = order[np.sort(first)]
    print("trees: %d within %.0f m of the network, %d of %d farther (tallest per %.0f m cell)" %
          (int(near.sum()), NEAR, len(keep_far), len(far), cell))
    return np.sort(np.concatenate([np.flatnonzero(near), keep_far]))


def build(level_dir, level_name, scene, rng_seed=7, drivable=None, net_xy=None):
    """drivable: clearance.Drivable of every road and path (v2.0; None: the cadastral paved
    surfaces of the route corridor, v1.x). net_xy: (points, half widths) of the network lines,
    for the thinning."""
    from landcover import CODE
    t = np.load(os.path.join(WORK, "trees.npz"))
    # no trees where the cadastral land cover is missing (Italy, outside the area): there the
    # buildings have no footprints and the canopy model would turn their roofs into trees
    ok = t["lc"] != CODE["none"]
    t = {k: t[k][ok] for k in t.files}
    print("trees outside the cadastral survey dropped:", int((~ok).sum()))
    if net_xy is not None:
        from scipy.spatial import cKDTree
        pts, hw, is_path = net_xy
        txy = np.column_stack([t["x"], t["y"]])
        dist = []
        for m in (~is_path, is_path):
            dd, jj = cKDTree(pts[m]).query(txy) if m.any() else (np.full(len(txy), 1e9), np.zeros(len(txy), int))
            dist.append(dd - (hw[m][jj] if m.any() else 0.0))
        keep = thin(t["x"], t["y"], t["h"], dist[0], CAP - SHRUBS, dist[1])
        t = {k: v[keep] for k, v in t.items()}
    x, y, z, h, d = t["x"], t["y"], t["z"], t["h"], t["d"]
    garden = np.isin(t["lc"], [CODE["giardino"], CODE["altro_rivestimento_duro"], CODE["edificio"],
                               CODE["campo_prato_pascolo"], CODE["vigna"]])
    cls = classify(h, d, t["sharp"], t["rgb"], garden)
    paths = sorted({p for v in MODELS.values() for p in v})
    bounds = asset_bounds.cached(paths)
    dims = {}
    for p in paths:
        b = bounds.get(p)
        if not b:
            continue
        mn, mx = np.array(b[0]), np.array(b[1])
        dims[p] = (mx[2] - max(mn[2], -0.5), 0.5 * ((mx[0] - mn[0]) + (mx[1] - mn[1])))
    rng = np.random.default_rng(rng_seed)
    items = {}
    for i in range(len(x)):
        cands = [p for p in MODELS[cls[i]] if p in dims]
        H0 = np.array([dims[p][0] for p in cands])
        W0 = np.array([dims[p][1] for p in cands])
        s = h[i] / H0
        err = np.abs(np.log(np.maximum(W0 * s, 0.3) / max(d[i], 0.5)))
        # choose among the two best matches at random to avoid visible repetition
        order = np.argsort(err)[:2]
        k = order[rng.integers(len(order))] if len(order) > 1 and err[order[1]] < err[order[0]] + 0.15 else order[0]
        p = cands[k]
        yaw = rng.uniform(0, 2 * np.pi)
        name = os.path.splitext(os.path.basename(p))[0]
        kind = "bush" if cls[i] == "bush" else "tree"
        items.setdefault((name, p), []).append((x[i], y[i], z[i] - 0.15, yaw, s[k], None, kind))
    # shrubs and hedges along the route (understory.py)
    us_f = os.path.join(WORK, "understory.npz")
    if os.path.exists(us_f):
        u = np.load(us_f)
        bush_models = [p for p in MODELS["bush"] if p in dims] + [T + "trees_aspen/tree_aspen_small_a.dae"]
        bush_models = [p for p in bush_models if p in dims or p in asset_bounds.cached([p])]
        dims.update({p: (np.array(asset_bounds.cached([p])[p][1])[2] - max(np.array(asset_bounds.cached([p])[p][0])[2], -0.5),
                         0.5 * sum(np.array(asset_bounds.cached([p])[p][1])[:2] - np.array(asset_bounds.cached([p])[p][0])[:2]))
                     for p in bush_models if p not in dims})
        hedge_p = I + "cypress_hedge_3m.dae"
        hb = asset_bounds.cached([hedge_p])[hedge_p]
        hedge_h = hb[1][2] - hb[0][2]
        for x_, y_, z_, h_, yaw_img, kind in zip(u["x"], u["y"], u["z"], u["h"], u["yaw"], u["kind"]):
            if kind == 1:
                theta = -float(yaw_img)                 # image rows point south: world angle = -image angle
                s = float(np.clip(h_ / hedge_h, 0.5, 2.5))
                items.setdefault(("cypress_hedge_3m", hedge_p), []).append((x_, y_, z_ - 0.1, None, s, theta, "hedge"))
            else:
                H0 = np.array([dims[p][0] for p in bush_models])
                k = int(np.argmin(np.abs(np.log(np.maximum(h_, 0.5) / H0))))
                p = bush_models[k]
                name = os.path.splitext(os.path.basename(p))[0]
                items.setdefault((name, p), []).append((x_, y_, z_ - 0.1, rng.uniform(0, 2 * np.pi),
                                                       float(np.clip(h_ / H0[k], 0.4, 2.5)), None, "bush"))
        # shrubs the photos show and the game lacked (missing_veg.py, full-dataset comparison)
        ps_f = os.path.join(WORK, "photo_shrubs.npz")
        if os.path.exists(ps_f):
            ps = np.load(ps_f)
            H0 = np.array([dims[p][0] for p in bush_models])
            for x_, y_, z_, h_ in zip(ps["x"], ps["y"], ps["z"], ps["h"]):
                k = int(np.argmin(np.abs(np.log(np.maximum(h_, 0.5) / H0))))
                p = bush_models[k]
                name = os.path.splitext(os.path.basename(p))[0]
                items.setdefault((name, p), []).append((x_, y_, z_ - 0.1, rng.uniform(0, 2 * np.pi),
                                                       float(np.clip(h_ / H0[k], 0.4, 2.5)), None, "bush"))
            print("photo shrubs", len(ps["x"]))
    # nothing on the paved surfaces
    entries, where = [], []
    for key, lst in items.items():
        b = asset_bounds.cached([key[1]]).get(key[1])
        ext = (np.array(b[1]) - np.array(b[0])) if b else np.array([2.0, 2.0, 2.0])
        for j, (px, py, pz, yaw, sc, theta, kind) in enumerate(lst):
            e = {"x": px, "y": py, "kind": kind, "r": 0.25 * (ext[0] + ext[1]) * sc, "h": ext[2] * sc}
            if kind == "hedge":
                e.update(r=0.5 * ext[1] * sc, L=0.5 * ext[0] * sc, theta=theta)
            entries.append(e)
            where.append((key, j))
    if drivable is not None:
        from clearance import clear_network
        res = clear_network(entries, drivable)
    else:
        res = clear_paved(entries, paved_dist_dir())
    from geo import Grid
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    new_items = {}
    n_drop = {"tree": 0, "bush": 0, "hedge": 0}
    n_move = 0
    for (key, j), e, r in zip(where, entries, res):
        px, py, pz, yaw, sc, theta, kind = items[key][j]
        if r is None:
            n_drop[kind] += 1
            continue
        if (r[0], r[1]) != (px, py):
            n_move += 1
            pz = float(dtm.sample([r[0]], [r[1]])[0]) - 0.1          # ground at the new place
        new_items.setdefault(key, []).append((r[0], r[1], pz, yaw, sc, theta))
    items = new_items
    print("off the paved surfaces: dropped", n_drop, "| shrubs and hedges moved back", n_move)
    fdir = os.path.join(level_dir, "forest")
    os.makedirs(fdir, exist_ok=True)
    managed = {}
    for (name, p), lst in items.items():
        managed[name] = {"name": name, "internalName": name, "class": "TSForestItemData", "persistentId": bng.pid(),
                         "radius": 0.5, "shapeFile": p}
        with open(os.path.join(fdir, f"{name}.forest4.json"), "w") as f:
            for (px, py, pz, yaw, s, theta) in lst:
                rotm = bng.rot_local_x_to(theta if theta is not None else yaw)
                f.write(json.dumps({"ctxid": 1, "pos": [round(float(px), 3), round(float(py), 3), round(float(pz), 3)],
                                    "rotationMatrix": rotm,
                                    "scale": round(float(s), 4), "type": name}, separators=(",", ":")) + "\n")
    os.makedirs(os.path.join(level_dir, "art", "forest"), exist_ok=True)
    json.dump(managed, open(os.path.join(level_dir, "art", "forest", "managedItemData.json"), "w"), indent=1)
    # the vanilla models' materials must be defined in this level
    import vanilla
    if vanilla.have_game():
        import copy_materials
        used = sorted({m for (_, p) in items for m in asset_bounds.dae_material_names(p)})
        found, missing = copy_materials.collect(used)
        bng.write_materials(os.path.join(level_dir, "art", "forest", "main.materials.json"), list(found.values()))
        if missing:
            print("WARNING tree materials not found:", missing)
    else:                       # no game here: the definitions of the released level (same models)
        vanilla.copy("art/forest/main.materials.json", os.path.join(level_dir, "art", "forest", "main.materials.json"))
    g = "MissionGroup/level_objects/vegetation"
    scene.add(g, {"name": "theForest", "class": "Forest", "persistentId": bng.pid(), "lodReflectScalar": 0.15})
    scene.add(g, {"class": "ForestWindEmitter", "persistentId": bng.pid(), "position": [0, 0, 400],
                  "radialEmitter": False, "strength": 0.6, "windEnabled": True})
    counts = {k: len(v) for k, v in items.items()}
    print("forest items", sum(counts.values()), "types", len(counts))
    print({k[0]: v for k, v in sorted(counts.items(), key=lambda kv: -kv[1])})
    return counts
