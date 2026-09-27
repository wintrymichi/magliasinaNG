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


def masks(dtm):
    h, w = dtm.a.shape
    tr = Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, dtm.y_max)
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
    excl = features.rasterize([(g, 1) for g in shp if not g.is_empty], out_shape=(h, w), transform=tr,
                              fill=0, dtype=np.uint8, all_touched=True).astype(bool)
    return excl


def main():
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    lc = np.load(os.path.join(WORK, "landcover05.npz"))["a"]
    chm = (dsm.a - dtm.a).astype(np.float32)
    excl = masks(dtm)
    water = np.isin(lc, [CODE["specchio_acqua"], CODE["bacino_idrico"]])
    paved = np.isin(lc, [CODE["strada_sentiero"], CODE["altro_rivestimento_duro"], CODE["marciapiede"]])
    bad = excl | water | (paved & (chm < 4.0))            # vehicles/objects on roads, not trees
    chm[bad] = 0
    chm[chm < 0] = 0
    chm_s = ndi.gaussian_filter(chm, 1.0)
    veg = chm_s > 1.5
    # height dependent local maxima (window diameter in m)
    tops = np.zeros(chm.shape, bool)
    for lo, hi, win in ((MIN_H, 8, 2.5), (8, 15, 4.0), (15, 25, 5.5), (25, 99, 7.0)):
        k = int(round(win / dtm.res)) | 1
        mx = ndi.maximum_filter(chm_s, size=k)
        tops |= (chm_s >= mx - 1e-4) & (chm_s >= lo) & (chm_s < hi)
    lab, n = ndi.label(tops)
    cy, cx = np.array(ndi.center_of_mass(tops, lab, range(1, n + 1))).T
    print("tree tops", n)
    # watershed crowns in tiles
    H, W = chm.shape
    T, O = 2048, 64
    crown_area = np.zeros(n + 1)
    markers_full = np.zeros(chm.shape, np.int32)
    markers_full[np.round(cy).astype(int), np.round(cx).astype(int)] = np.arange(1, n + 1)
    for r0 in range(0, H, T):
        for c0 in range(0, W, T):
            ra, rb = max(0, r0 - O), min(H, r0 + T + O)
            ca, cb = max(0, c0 - O), min(W, c0 + T + O)
            sub = chm_s[ra:rb, ca:cb]
            mk = markers_full[ra:rb, ca:cb]
            if mk.max() == 0:
                continue
            ws = watershed(-sub, mk, mask=veg[ra:rb, ca:cb])
            # count only the core (non-overlap) part to avoid double counting
            core = ws[r0 - ra:r0 - ra + min(T, H - r0), c0 - ca:c0 - ca + min(T, W - c0)]
            ids, cnt = np.unique(core[core > 0], return_counts=True)
            crown_area[ids] += cnt * dtm.res ** 2
    d = 2 * np.sqrt(crown_area[1:] / np.pi)
    # coordinates
    x = dtm.x_min + (cx + 0.5) * dtm.res
    y = dtm.y_max - (cy + 0.5) * dtm.res
    ri, ci = np.round(cy).astype(int), np.round(cx).astype(int)
    h = chm_s[ri, ci]
    hmax = ndi.maximum_filter(chm, size=3)[ri, ci]
    h = np.maximum(h, hmax)
    z = dtm.sample(x, y)
    # pointedness: top minus mean canopy on a ring of 1.5 m radius
    ring = np.zeros((7, 7), bool)
    yy, xx = np.mgrid[-3:4, -3:4]
    ring[(np.hypot(yy, xx) >= 2.5) & (np.hypot(yy, xx) <= 3.3)] = True
    ringmean = ndi.correlate(chm_s, ring.astype(np.float32) / ring.sum(), mode="nearest")[ri, ci]
    sharp = (h - ringmean) / np.maximum(h, 1)
    # orthophoto colour of the crown centre
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        o = s.read()
    rgb = np.stack([ndi.uniform_filter(o[k].astype(np.float32), 5)[ri, ci] for k in range(3)], 1)
    lcs = lc[ri, ci]
    keep = (h >= MIN_H) & (d >= 1.0)
    np.savez_compressed(os.path.join(WORK, "trees.npz"), x=x[keep], y=y[keep], z=z[keep], h=h[keep], d=d[keep],
                        sharp=sharp[keep], rgb=rgb[keep], lc=lcs[keep])
    print("trees kept", int(keep.sum()), "height median %.1f m, crown median %.1f m" %
          (np.median(h[keep]), np.median(d[keep])))


if __name__ == "__main__":
    main()
