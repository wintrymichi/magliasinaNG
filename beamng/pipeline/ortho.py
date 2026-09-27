"""On-demand access to the 10 cm SWISSIMAGE orthophoto on the local grid."""
import glob, os
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from config import DATA
from geo import local_grid

_FILES = None
_DS = {}


def _files():
    global _FILES
    if _FILES is None:
        _FILES = []
        for f in sorted(glob.glob(os.path.join(DATA, "swissimage_010", "*.tif"))):
            with rasterio.open(f) as s:
                _FILES.append((f, s.bounds))
    return _FILES


def _open(f):
    if f not in _DS:
        _DS[f] = rasterio.open(f)
    return _DS[f]


def patch(x_min, y_min, x_max, y_max, res=0.1, resampling=Resampling.bilinear):
    """RGB uint8 (h, w, 3), north-up, of the local rectangle."""
    tr, w, h = local_grid(x_min, y_min, x_max, y_max, res)
    out = np.zeros((3, h, w), np.uint8)
    e1, n2 = tr * (0, 0)
    e2, n1 = tr * (w, h)
    for f, b in _files():
        if b.right < e1 or b.left > e2 or b.top < n1 or b.bottom > n2:
            continue
        s = _open(f)
        tmp = np.zeros((3, h, w), np.uint8)
        reproject(source=rasterio.band(s, [1, 2, 3]), destination=tmp, src_transform=s.transform,
                  src_crs=s.crs, dst_transform=tr, dst_crs="EPSG:2056", resampling=resampling,
                  src_nodata=0, dst_nodata=0)
        m = tmp.sum(0) > 0
        out[:, m] = tmp[:, m]
    return out.transpose(1, 2, 0)
