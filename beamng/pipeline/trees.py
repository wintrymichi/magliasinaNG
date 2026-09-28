"""Individual trees from the swisstopo canopy height model (swissSURFACE3D DSM - swissALTI3D DTM).

1. nDSM at 0.5 m; buildings, walls, water and vehicles on roads are masked out
   (cadastral footprints / walls, swissBUILDINGS3D).
2. Tree tops = local maxima of the smoothed canopy with a height-dependent window.
3. Crowns = marker-controlled watershed of the canopy (tiles with overlap);
   crown diameter = equivalent diameter of the crown area.
4. Each tree gets ground z from the DTM, height = canopy maximum - DTM, and a
   crown shape index (how pointed the top is, for conifers) plus its orthophoto
   colour; the land cover (forest / garden) is recorded for species choice.
Output: work/trees.npz  (x, y, z, h, d, sharp, rgb, lc)
"""
import os, pickle
import numpy as np
import shapely
from scipy import ndimage as ndi
from skimage.segmentation import watershed
from rasterio import features
from rasterio.transform import Affine
import rasterio
from config import WORK
from geo import Grid
from landcover import CODE

MIN_H = 3.0


def mask_shapes():
    """Footprints where the canopy model is not vegetation: buildings, walls, bridges, tanks
    (cadastral survey) and the roofs of swissBUILDINGS3D."""
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    shp = []
    for g, _ in av["LCSF"].get("edificio", []):
        shp.append(g.buffer(1.0))
    for g, _ in av["SOSF"].get("muro", []):
        shp.append(g.buffer(0.5))
    for g, _ in av["SOLI"].get("muro", []):
        shp.append(g.buffer(0.6))
    for key in ("altra_parte_di_edificio", "riparo", "silo_torre_gasometro", "serbatoio", "ponte_passerella"):
        for g, _ in av["SOSF"].get(key, []):
            shp.append(g.buffer(0.5))
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    for b in blds:
        r = b["roofs"]
        if len(r):
            pts = r.reshape(-1, 3)[:, :2]
            shp.append(shapely.MultiPoint(pts).convex_hull.buffer(0.8))
    return [g for g in shp if not g.is_empty]


TILE = 1000.0          # m, trees are found tile by tile (the v2.0 grid is ~22 000 x 18 000 cells)
OVER = 40.0            # m of overlap: crowns across a tile edge are measured whole


def detect(chm, res):
    """Tree tops (row, col) of a canopy height window and their crown areas (m2)."""
    chm_s = ndi.gaussian_filter(chm, 1.0)
    veg = chm_s > 1.5
    tops = np.zeros(chm.shape, bool)
    for lo, hi, win in ((MIN_H, 8, 2.5), (8, 15, 4.0), (15, 25, 5.5), (25, 99, 7.0)):
        k = int(round(win / res)) | 1
        mx = ndi.maximum_filter(chm_s, size=k)
        tops |= (chm_s >= mx - 1e-4) & (chm_s >= lo) & (chm_s < hi)
    lab, n = ndi.label(tops)
    if n == 0:
        return chm_s, np.zeros(0), np.zeros(0), np.zeros(0)
    cy, cx = np.array(ndi.center_of_mass(tops, lab, range(1, n + 1))).T
    markers = np.zeros(chm.shape, np.int32)
    markers[np.round(cy).astype(int), np.round(cx).astype(int)] = np.arange(1, n + 1)
    ws = watershed(-chm_s, markers, mask=veg)
    ids, cnt = np.unique(ws[ws > 0], return_counts=True)
    area = np.zeros(n + 1)
    area[ids] = cnt * res ** 2
    return chm_s, cy, cx, area[1:]


def main():
    from geo import ortho_sampler
    import area as area_mod
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    lcd = np.load(os.path.join(WORK, "landcover05.npz"))
    lc = lcd["a"]
    shp = mask_shapes()
    stree = shapely.STRtree(shp)
    ortho = ortho_sampler()
    res = dtm.res
    gx0, gy0, gx1, gy1 = dtm.bounds()
    ring = np.zeros((7, 7), bool)
    yy, xx = np.mgrid[-3:4, -3:4]
    ring[(np.hypot(yy, xx) >= 2.5) & (np.hypot(yy, xx) <= 3.3)] = True
    ring = ring.astype(np.float32) / ring.sum()
    out = {k: [] for k in ("x", "y", "z", "h", "d", "sharp", "rgb", "lc")}
    for tx0 in np.arange(gx0, gx1, TILE):
        for ty0 in np.arange(gy0, gy1, TILE):
            tx1, ty1 = min(tx0 + TILE, gx1), min(ty0 + TILE, gy1)
            sub_t, r0, c0 = dtm.window(tx0 - OVER, ty0 - OVER, tx1 + OVER, ty1 + OVER)
            sub_s, _, _ = dsm.window(tx0 - OVER, ty0 - OVER, tx1 + OVER, ty1 + OVER)
            H, W = sub_t.a.shape
            chm = (np.asarray(sub_s.a, np.float32) - np.asarray(sub_t.a, np.float32))
            L = lc[r0:r0 + H, c0:c0 + W]
            tr = Affine(res, 0, sub_t.x_min, 0, -res, sub_t.y_max)
            box = shapely.box(sub_t.x_min, sub_t.y_max - H * res, sub_t.x_min + W * res, sub_t.y_max)
            near = stree.query(box, predicate="intersects")
            excl = features.rasterize([(shp[i], 1) for i in near], out_shape=(H, W), transform=tr, fill=0,
                                      dtype=np.uint8, all_touched=True).astype(bool) if len(near) else np.zeros((H, W), bool)
            water = np.isin(L, [CODE["specchio_acqua"], CODE["bacino_idrico"]])
            paved = np.isin(L, [CODE["strada_sentiero"], CODE["altro_rivestimento_duro"], CODE["marciapiede"]])
            chm[excl | water | (paved & (chm < 4.0))] = 0      # vehicles/objects on roads, not trees
            chm[chm < 0] = 0
            chm_s, cy, cx, crown = detect(chm, res)
            if not len(cy):
                continue
            x = sub_t.x_min + (cx + 0.5) * res
            y = sub_t.y_max - (cy + 0.5) * res
            core = (x >= tx0) & (x < tx1) & (y >= ty0) & (y < ty1)
            ri, ci = np.round(cy[core]).astype(int), np.round(cx[core]).astype(int)
            h = np.maximum(chm_s[ri, ci], ndi.maximum_filter(chm, size=3)[ri, ci])
            ringmean = ndi.correlate(chm_s, ring, mode="nearest")[ri, ci]
            out["x"].append(x[core]); out["y"].append(y[core])
            out["z"].append(np.asarray(sub_t.a)[ri, ci].astype(np.float64))
            out["h"].append(h); out["d"].append(2 * np.sqrt(crown[core] / np.pi))
            out["sharp"].append((h - ringmean) / np.maximum(h, 1))
            out["rgb"].append(np.nan_to_num(ortho(x[core], y[core]), nan=80.0))
            out["lc"].append(L[ri, ci])
            print("  tile %.0f %.0f: %d tops" % (tx0, ty0, int(core.sum())), flush=True)
    t = {k: np.concatenate(v) for k, v in out.items()}
    keep = (t["h"] >= MIN_H) & (t["d"] >= 1.0)
    np.savez_compressed(os.path.join(WORK, "trees.npz"), **{k: v[keep] for k, v in t.items()})
    print("trees kept", int(keep.sum()), "height median %.1f m, crown median %.1f m" %
          (np.median(t["h"][keep]), np.median(t["d"][keep])))


if __name__ == "__main__":
    main()
