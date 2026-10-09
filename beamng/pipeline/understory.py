"""Shrubs and hedges along the route from the canopy height model (0.6-6 m vegetation).

Within CORRIDOR m of the road, pixels of the vegetation height model (DSM - DTM with
buildings, walls, bridges masked, not paved, not water) between 0.6 and 6 m are low
vegetation that the tree-top detection (>= 3 m tops with crowns) does not represent.
The binary low-vegetation mask is analysed with the structure tensor: coherent, narrow
(< 3 m) strips are hedges -> hedge segments every 2 m along their orientation at the
measured height; the rest is sampled on a 2 m grid -> bushes scaled to the measured
height. Points within 2.5 m of a detected tree top are skipped (the tree covers them).
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
    np.savez_compressed(os.path.join(WORK, "understory.npz"), **res)
    print("hedge segments", int((res["kind"] == 1).sum()), "bushes", int((res["kind"] == 0).sum()),
          "height median %.1f m" % np.median(res["h"]))


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
# The heights of the terrain are not changed; the changed files get the date of the build step. Everything
# else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish understory
# --------------------------------------------------------------------------------------------------

FLOOR = (62, 66, 42)        # sRGB base colour of the forest floor layers (v2.7: the measured 102, 98, 67)
TWIN = {m: m + "Verge" for m in groundcover.FOREST_LAYERS}
SOLID = ("roads/surfaces", "walls", "buildings", "railway")    # nothing grows through these
STEP = 0.5                  # m between the samples of a face


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
            tw = dict(m, internalName=TWIN[m["internalName"]], persistentId=bng.pid())
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
    veg = [o for o in read_items(zi, veg_name) if o.get("name") != groundcover.UNDERSTORY[0]]
    parent = next((o["__parent"] for o in veg if o.get("class") == "GroundCover"), "vegetation")
    u = groundcover.understory_object()
    u["__parent"] = parent
    veg.append(u)
    new[veg_name] = write_items(veg)

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
    print("written in %.0f s" % (time.time() - t0), flush=True)
    if report:
        res = {"forest_floor_vertices": forest, "to_verge": moved,
               "floor_colour_before": measured, "floor_colour_after": list(FLOOR),
               "understory": {"radius_m": groundcover.UNDERSTORY[1], "max_elements": groundcover.UNDERSTORY[4],
                              "shapes": [s[0] for s in groundcover.UNDERSTORY_SHAPES]},
               "terrain_heights_unchanged": True}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0
