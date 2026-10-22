"""Shrubs and hedges along the route from the canopy height model (0.6-6 m vegetation).

Within CORRIDOR m of the road, pixels of the vegetation height model (DSM - DTM with
buildings, walls, bridges masked, not paved, not water) between 0.6 and 6 m are low
vegetation that the tree-top detection (>= 3 m tops with crowns) does not represent.
The binary low-vegetation mask is analysed with the structure tensor: coherent, narrow
(< 3 m) strips are hedges -> hedge segments every 2 m along their orientation at the
measured height; the rest is sampled on a 2 m grid -> bushes scaled to the measured
height. Points within 2.5 m of a detected tree top are skipped (the tree covers them).
v3.0.40: the strips the street photos saw (street_hedges.py, dati/street_hedges.json): a hedge wherever they see
vegetation, also away from the route (every 2 m along the strip, at its height), and no hedge where they see a
wall, a fence, a building (a strip the surface model alone takes for a hedge).
Output: work/understory.npz (x, y, z, h, yaw, kind 0=bush 1=hedge)
"""
import os
import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from config import WORK
from geo import Grid
from landcover import CODE
import trees as trees_mod
import argparse, io, json, os, re, struct, sys, time, zipfile
from PIL import Image
import bng
import groundcover
import optimize_level
import walls as pw
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

CORRIDOR = 60.0
STREET_HEDGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "street_hedges.json")
PHOTO_NEAR = 1.0              # m: a strip point this near a cell the photos saw takes its verdict


def main():
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    lc = np.load(os.path.join(WORK, "landcover05.npz"))["a"]
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    chm = (dsm.a - dtm.a).astype(np.float32)
    excl = trees_mod.masks(dtm)
    bad = excl | np.isin(lc, [CODE["specchio_acqua"], CODE["bacino_idrico"], CODE["strada_sentiero"],
                              CODE["marciapiede"], CODE["altro_rivestimento_duro"], CODE["edificio"],
                              CODE["ferrovia"]])
    # corridor mask
    from rasterio import features
    from rasterio.transform import Affine
    tr = Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, dtm.y_max)
    corr = features.rasterize([(shapely.LineString(rp["center"]).buffer(CORRIDOR), 1)], out_shape=chm.shape,
                              transform=tr, fill=0, dtype=np.uint8).astype(bool)
    low = (chm > 0.6) & (chm < 6.0) & ~bad & corr
    low = ndi.binary_opening(low, iterations=1)
    # structure tensor of the smoothed mask
    m = ndi.gaussian_filter(low.astype(np.float32), 1.0)
    gy, gx = np.gradient(m)
    Jxx = ndi.gaussian_filter(gx * gx, 3); Jyy = ndi.gaussian_filter(gy * gy, 3); Jxy = ndi.gaussian_filter(gx * gy, 3)
    tr_ = Jxx + Jyy
    det = Jxx * Jyy - Jxy * Jxy
    disc = np.sqrt(np.maximum(tr_ ** 2 / 4 - det, 0))
    l1, l2 = tr_ / 2 + disc, tr_ / 2 - disc
    coh = (l1 - l2) / np.maximum(l1 + l2, 1e-9)
    # thickness: distance to the mask border (edt) * 2
    thick = 2 * ndi.distance_transform_edt(low) * dtm.res
    hedge = low & (coh > 0.55) & (ndi.maximum_filter(thick, 5) < 3.0)
    # orientation of the strip (perpendicular to the dominant gradient)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2
    t = np.load(os.path.join(WORK, "trees.npz"))
    ttree = cKDTree(np.column_stack([t["x"], t["y"]]))
    out = {k: [] for k in ("x", "y", "z", "h", "yaw", "kind")}
    for kind, mask, step in ((1, hedge, 2.0), (0, low & ~hedge, 2.0)):
        k = int(round(step / dtm.res))
        r, c = np.where(mask)
        sel = (r % k == 0) & (c % k == 0)
        r, c = r[sel], c[sel]
        x = dtm.x_min + (c + 0.5) * dtm.res
        y = dtm.y_max - (r + 0.5) * dtm.res
        d, _ = ttree.query(np.column_stack([x, y]))
        keep = d > 2.5
        r, c, x, y = r[keep], c[keep], x[keep], y[keep]
        h = ndi.maximum_filter(chm, 3)[r, c]
        z = dtm.sample(x, y)
        yaw = theta[r, c] if kind == 1 else np.random.default_rng(5).uniform(0, 2 * np.pi, len(x))
        for key, val in (("x", x), ("y", y), ("z", z), ("h", h), ("yaw", yaw), ("kind", np.full(len(x), kind))):
            out[key].append(val)
    res = {k: np.concatenate(v) for k, v in out.items()}
    res = photo_hedges(res, dtm)
    np.savez_compressed(os.path.join(WORK, "understory.npz"), **res)
    print("hedge segments", int((res["kind"] == 1).sum()), "bushes", int((res["kind"] == 0).sum()),
          "height median %.1f m" % np.median(res["h"]))


def photo_hedges(res, dtm, path=STREET_HEDGES):
    """The hedges of the strips the street photos saw: the route's hedge points where a photo sees no vegetation
    dropped, a hedge every 2 m of the strips where they see it added."""
    import json
    if not os.path.exists(path):
        return res
    S = np.array(json.load(open(path))["cells"], float).reshape(-1, 6)       # x, y, h, theta, vegetation, other
    if not len(S):
        return res
    yes = S[:, 4] > S[:, 5]
    tree = cKDTree(S[:, :2])
    d, j = tree.query(np.column_stack([res["x"], res["y"]]))
    drop = (res["kind"] == 1) & (d < PHOTO_NEAR) & ~yes[j]
    res = {k: v[~drop] for k, v in res.items()}
    # the cells of 1 m every 2 m, away from the hedges there are
    Y = S[yes]
    Y = Y[np.unique(np.floor(Y[:, :2] / 2.0).astype(np.int64), axis=0, return_index=True)[1]]
    have = cKDTree(np.column_stack([res["x"], res["y"]])[res["kind"] == 1]) if (res["kind"] == 1).any() else None
    if have is not None and len(Y):
        Y = Y[have.query(Y[:, :2])[0] > PHOTO_NEAR]
    add = {"x": Y[:, 0], "y": Y[:, 1], "z": dtm.sample(Y[:, 0], Y[:, 1]), "h": Y[:, 2],
           "yaw": -Y[:, 3],                                  # back to the image frame of the strips (rows south)
           "kind": np.ones(len(Y), np.int64)}
    print("street photos: %d hedge points dropped (no vegetation there), %d added" % (int(drop.sum()), len(Y)))
    return {k: np.concatenate([res[k], np.asarray(add[k], res[k].dtype)]) for k in res}


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------------------------------
# Undergrowth in the woods and a darker forest floor (v2.8), in the built level.
#
# Up to v2.7 the ground of the woods (terrain layers ForestFloor and ForestFloor2, the cadastral forest)
# was bare, in the colour measured in the panoramas on the forest edges along the cantonal road
# (terrain_colors.py: 102, 98, 67, sunlit leaf litter beside the road): between the trunks, and from afar
# between the crowns, the woods showed light brown ground.
#
# Here:
# - the base colour of the two forest floor layers goes to FLOOR (a darker olive, the leaf litter in the
#   shade of the crowns), the same noise of the texture kept; the backfill behind the walls in the woods
#   uses the same textures (walls.build_backfill) and follows;
# - an undergrowth of low shrubs, the game's bush models the level already uses
#   (groundcover.UNDERSTORY_SHAPES, 0.6-1.5 m tall), placed by a GroundCover around the camera only
#   (groundcover.UNDERSTORY: within 60 m, fading from 40 m; no collision, nothing stored per shrub);
# - no shrubs through the roads, paths, walls, buildings, the backfill or the railway: the forest floor
#   vertices of the terrain squares they touch, and one square around them, go to the verge twins
#   ForestFloorVerge and ForestFloor2Verge (new terrain materials, the same textures, without the
#   undergrowth), as the meadows along the roads since v2.4 (terrain.VERGE).
# v3.1: a wild wood (groundcover.UNDERSTORY_COVERS): ferns, shrubs and brambles, dead wood and stones, sparse in
#   the shade and thick in the light: the forest floor within EDGE_M of the edge of the wood or in a gap of the
#   canopy (no trunk within GAP_M) goes to the light twins ForestFloorLight and ForestFloor2Light (the same textures);
#   the materials of the new models the level lacks go to art/shapes/groundcover/understory.materials.json.
# The heights of the terrain are not changed; the changed files get the date of the build step. Everything
# else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish understory
# --------------------------------------------------------------------------------------------------

FLOOR = (62, 66, 42)        # sRGB base colour of the forest floor layers (v2.7: the measured 102, 98, 67)
TWIN = {m: m + "Verge" for m in groundcover.FOREST_LAYERS}
LIGHT = groundcover.FOREST_LIGHT
EDGE_M = 10.0               # v3.1: forest floor this near the edge of the wood (a meadow, road, yard, wall) is in its light
SPECK_M2 = 400.0            # an opening in the wood smaller than this is no edge
GAP_M = 9.0                 # forest floor with no trunk this near is a gap of the canopy (the measured trees stand a median
                            # 5.4 m from a floor vertex; beyond 9 m: about one floor vertex in ten, v3.0.40)
GAP_WOOD_M = 30.0           # ... when a trunk stands within this (no measured trees at all: not a gap, unknown wood)
NOT_CANOPY = ("bush", "hedge", "guardrail", "palm", "cypress")   # forest items that cast no canopy over the floor
SOLID = ("roads/surfaces", "walls", "buildings", "railway")    # nothing grows through these
STEP = 0.5                  # m between the samples of a face
UNDER_MATS = "{lv}/art/shapes/groundcover/understory.materials.json"


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def write_items(objs):
    return ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")


def face_cells(zi, lv, n):
    """(n - 1, n - 1) bool: the terrain squares under a face of the SOLID groups (every face sampled every STEP m)."""
    cells = np.zeros((n - 1, n - 1), bool)
    for g in SOLID:
        f = f"{lv}/main/MissionGroup/{g}/items.level.json"
        if f not in zi.NameToInfo:
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
                continue
            V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            W = (V + np.asarray(o.get("position", [0, 0, 0]), np.float64))[:, :2]
            t = W[np.concatenate([idx[:, 0] for _, idx in parts])].reshape(-1, 3, 2)
            e = np.stack([np.linalg.norm(t[:, a] - t[:, b], axis=1) for a, b in ((0, 1), (1, 2), (2, 0))], 1)
            k = np.maximum(np.ceil(e.max(1) / STEP).astype(np.int64), 1)
            for kk in np.unique(k):                     # barycentric points on a grid of kk steps per side
                i, j = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1))
                m = i + j <= kk
                a, b = i[m] / kk, j[m] / kk
                sel = t[k == kk]
                per = max(1, 4_000_000 // len(a))       # triangles per batch
                for s0 in range(0, len(sel), per):
                    tt = sel[s0:s0 + per]
                    P = (tt[:, None, 0] * (1 - a - b)[None, :, None] + tt[:, None, 1] * a[None, :, None]
                         + tt[:, None, 2] * b[None, :, None]).reshape(-1, 2)
                    c = np.floor((P[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
                    r = np.floor((P[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
                    ok = (r >= 0) & (r < n - 1) & (c >= 0) & (c < n - 1)
                    cells[r[ok], c[ok]] = True
    return cells


def trunks(zi, lv):
    """(k, 2) x, y of the level's trees (its forest items, not the shrubs, hedges or guard rails)."""
    out = []
    for f in zi.namelist():
        if not (f.startswith(f"{lv}/forest/") and f.endswith(".forest4.json")):
            continue
        if any(w in os.path.basename(f).lower() for w in NOT_CANOPY):
            continue
        out += [o["pos"][:2] for o in read_items(zi, f)]
    return np.array(out, np.float64).reshape(-1, 2)


def light_vertices(lay, names, trees, n):
    """(n, n) bool, v3.1: the forest floor vertices (FOREST_LAYERS) in the light: within EDGE_M of the edge of the
    wood (any vertex of another layer: a meadow, a road, a yard, the verge twins) or in a gap of the canopy (no
    trunk within GAP_M, one within GAP_WOOD_M). Distances on the terrain grid (cv2, L2)."""
    import cv2
    forest = np.isin(lay, [names.index(m) for m in groundcover.FOREST_LAYERS])
    # specks of another layer inside the wood (a few squares of meadow from the land cover) are no edge
    _, comp, stats, _ = cv2.connectedComponentsWithStats((~forest).view(np.uint8), connectivity=8)
    speck = stats[:, cv2.CC_STAT_AREA] * TER_SQUARE ** 2 < SPECK_M2
    speck[0] = False                                                       # label 0: the wood itself
    inner = forest | speck[comp]
    del comp
    d = cv2.distanceTransform(inner.view(np.uint8), cv2.DIST_L2, 5)       # to the nearest vertex not of the wood
    del inner
    light = forest & (d * TER_SQUARE <= EDGE_M)
    del d
    c = np.round((trees[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
    r = np.round((trees[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
    ok = (r >= 0) & (r < n) & (c >= 0) & (c < n)
    free = np.full((n, n), 255, np.uint8)
    free[r[ok], c[ok]] = 0
    d = cv2.distanceTransform(free, cv2.DIST_L2, 5) * TER_SQUARE           # to the nearest trunk
    del free
    gap = forest & (d > GAP_M) & (d <= GAP_WOOD_M)
    del d
    return light | gap, {"edge": int(light.sum()), "gap": int((gap & ~light).sum())}


def darker(png, rgb_from, rgb_to):
    """The base texture with every pixel scaled channel by channel from rgb_from to rgb_to (its noise kept)."""
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), np.float32)
    f = np.asarray(rgb_to, np.float32) / np.maximum(np.asarray(rgb_from, np.float32), 1)
    out = io.BytesIO()
    Image.fromarray(np.clip(a * f, 0, 255).astype(np.uint8)).save(out, "PNG", optimize=True)
    return out.getvalue()


def understory_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = pw.read_ter(data)
    if any(t in names for t in TWIN.values()):
        raise SystemExit("the zip has the forest verge layers already")

    # ---- the forest floor vertices near the solid meshes -> the verge twins (no undergrowth)
    near = pw.corners_of(face_cells(zi, lv, n))
    near = ndi.binary_dilation(near, np.ones((3, 3), bool))               # and one square around
    new_lay = lay.copy()
    names2 = list(names)
    moved = {}
    for m, t in TWIN.items():
        names2.append(t)
        sel = near & (lay == names.index(m))
        new_lay[sel] = names2.index(t)
        moved[f"{m} -> {t}"] = int(sel.sum())
    forest = int(np.isin(lay, [names.index(m) for m in TWIN]).sum())
    print("forest floor vertices: %d, near roads, paths, walls, buildings, railway: %s" % (forest, moved), flush=True)
    # ---- v3.1: the forest floor in the light (the edge of the wood, the gaps of the canopy) -> the light twins
    lit, why = light_vertices(new_lay, names2, trunks(zi, lv), n)
    for m, t in LIGHT.items():
        names2.append(t)
        sel = lit & (new_lay == names2.index(m))
        new_lay[sel] = names2.index(t)
        moved[f"{m} -> {t}"] = int(sel.sum())
    del lit
    print("forest floor in the light: %s, %s" % (why, {k: v for k, v in moved.items() if "Light" in k}), flush=True)
    tail = struct.pack("<I", len(names2)) + b"".join(struct.pack("<B", len(s.encode())) + s.encode() for s in names2)
    new_ter = data[:5 + 2 * n * n] + new_lay.tobytes() + tail
    assert new_ter[:5 + 2 * n * n] == data[:5 + 2 * n * n]                 # heights as they were

    # ---- the other files
    new = {ter_name: new_ter}
    mats_name = f"{lv}/art/terrains/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    base_of = {}
    for key, m in list(mats.items()):
        if m.get("class") == "TerrainMaterial" and m.get("internalName") in TWIN:
            for twin in (TWIN, LIGHT):
                tw = dict(m, internalName=twin[m["internalName"]], persistentId=bng.pid())
                mats[f"{tw['internalName']}-{tw['persistentId']}"] = tw
            base_of[m["internalName"]] = m["baseColorBaseTex"]
    new[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    tj_name = f"{lv}/theTerrain.terrain.json"
    tj = json.loads(zi.read(tj_name))
    tj["materials"] = names2
    new[tj_name] = json.dumps(tj, indent=2).encode("utf-8")
    measured = {}
    for m, tex in base_of.items():
        f = tex.lstrip("/")
        a = np.asarray(Image.open(io.BytesIO(zi.read(f))).convert("RGB"), np.float32)
        measured[m] = np.median(a.reshape(-1, 3), 0).round().astype(int).tolist()
        new[f] = darker(zi.read(f), measured[m], FLOOR)
    veg_name = f"{lv}/main/MissionGroup/level_objects/vegetation/items.level.json"
    ours = groundcover.understory_names() | {groundcover.MEADOW[0]}
    veg = [o for o in read_items(zi, veg_name) if o.get("name") not in ours]
    parent = next((o["__parent"] for o in veg if o.get("class") == "GroundCover"), "vegetation")
    for u in groundcover.understory_objects() + [groundcover.meadow_object()]:     # v3.0: and the meadow shrubs
        u["__parent"] = parent
        veg.append(u)
    new[veg_name] = write_items(veg)
    # v3.1: the materials of the undergrowth models the level does not define yet (ferns, dead wood, stones...)
    have = set()
    for f in zi.namelist():
        if f.startswith(f"{lv}/") and f.endswith("materials.json") and f != UNDER_MATS.format(lv=lv):
            try:
                d = json.loads(zi.read(f))
            except ValueError:
                continue
            have |= {v.get("name", k) for k, v in d.items() if isinstance(v, dict)} | set(d)
    um = groundcover.understory_materials(have)
    new[UNDER_MATS.format(lv=lv)] = json.dumps(um, indent=1).encode("utf-8")

    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new:
                ni = zipfile.ZipInfo(i.filename, now)                       # converted again by the game
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new[i.filename])
            elif re.fullmatch(r"levels/[^/]+/README\.md", i.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(i, open(pw.LEVEL_README, "rb").read(), compress_type=i.compress_type)
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for f in sorted(set(new) - set(zi.NameToInfo)):                    # v3.1: the undergrowth materials
            zo.writestr(f, new[f], compress_type=zipfile.ZIP_DEFLATED)
    print("written in %.0f s" % (time.time() - t0), flush=True)
    if report:
        res = {"forest_floor_vertices": forest, "to_verge": moved,
               "floor_colour_before": measured, "floor_colour_after": list(FLOOR),
               "light": why, "understory_materials": sorted(um),
               "understory": {f"{c[0]}_{zone}": {
                   "radius_m": c[1], "max_elements_per_layer": c[5][zone][0], "layers": list(layers),
                   "max_plants_per_layer": groundcover.max_plants(c, zone),
                   "per_m2": {f"{z}m": round(groundcover.density(c, zone, z), 4) for z in (500, 1200)},
                   "shapes": [r[0] for r in c[5][zone][1]]}
                   for c in groundcover.UNDERSTORY_COVERS for zone, layers in groundcover.UNDERSTORY_LAYERS.items()},
               "terrain_heights_unchanged": True}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0
