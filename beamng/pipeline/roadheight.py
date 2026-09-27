"""Height of the paved surfaces (road meshes, markings, road furniture).

The smoothed DTM sags at the edge of a road that ends in a drop (valley-side retaining wall,
embankment): the 0.5 m cells straddling the edge and the smoothing mix in the lower ground, up
to ~1 m within the outer metre of the carriageway. Here the surface is taken from the DTM only
well inside the surveyed paved areas (0.75 m from their edges) and carried outwards by
normalised convolution:
    Z = G(dtm * M) / G(M)      M = paved areas eroded by 0.75 m, G = Gaussian (sigma 0.5 m;
                               1.0 m where the finer one has no support)
so the edge strip continues the surface next to it. Farther than ~2 m from any paved area the
plain smoothed DTM is used.
Output: work/road_height.npz (Grid, same raster as dtm05).
"""
import os, pickle
import numpy as np
from scipy.ndimage import gaussian_filter
from rasterio import features
from rasterio.transform import Affine
from config import WORK
from geo import Grid

CLASSES = ("strada_sentiero", "altro_rivestimento_duro", "marciapiede", "spartitraffico")
ERODE = 0.75


def build():
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    inner = [g.buffer(-ERODE) for c in CLASSES for g, _ in av["LCSF"].get(c, [])]
    inner = [g for g in inner if not g.is_empty]
    H, W = dtm.a.shape
    tr = Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, dtm.y_max)       # row 0 = north edge (geo.Grid)
    M = features.rasterize([(g, 1) for g in inner], out_shape=(H, W), transform=tr, fill=0,
                           dtype=np.uint8).astype(np.float32)
    a = dtm.a.astype(np.float32)
    n1, d1 = gaussian_filter(a * M, 1.0), gaussian_filter(M, 1.0)
    n2, d2 = gaussian_filter(a * M, 2.0), gaussian_filter(M, 2.0)
    base = gaussian_filter(a, 1.0)
    z = np.where(d1 > 0.25, n1 / np.maximum(d1, 1e-6), np.where(d2 > 0.03, n2 / np.maximum(d2, 1e-6), base))
    w = np.clip((d2 - 0.03) / 0.12, 0, 1)                             # blend into the DTM at the rim
    z = w * z + (1 - w) * base
    Grid(z.astype(np.float32), dtm.x_min, dtm.y_max, dtm.res).save(os.path.join(WORK, "road_height.npz"))
    d = z - base
    print("paved cells (eroded)", int(M.sum()), "| surface minus smoothed DTM: inside median %.3f m"
          % np.median(d[M > 0]), "| cells raised > 0.2 m:", int((d > 0.2).sum()), "| > 0.5 m:", int((d > 0.5).sum()))


def height_fn():
    """Bilinear sampler of work/road_height.npz (built on demand)."""
    from scipy.ndimage import map_coordinates
    f = os.path.join(WORK, "road_height.npz")
    if not os.path.exists(f):
        build()
    g = Grid.load(f)

    def fn(x, y):
        r, c = g.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(g.a, [r, c], order=1, mode="nearest")
    return fn


if __name__ == "__main__":
    build()
