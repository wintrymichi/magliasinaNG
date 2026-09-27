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
