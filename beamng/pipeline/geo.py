"""Raster helpers: resample swisstopo LV95 tiles onto grids of the local map frame.

Local frame = LV95 shifted to (E0, N0) and divided by K, so a local grid of
resolution r metres is an LV95 grid of resolution r*K; rasterio does the rest.
Arrays are returned north-up (row 0 = largest y), like the source GeoTIFFs.
"""
import glob, os
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
from config import DATA, E0, N0, K


def grid_transform(x_min, y_max, res):
    """Affine (EPSG:2056) of a north-up local grid whose top-left corner is (x_min, y_max)."""
    return Affine(res * K, 0, E0 + x_min * K, 0, -res * K, N0 + y_max * K)


def local_grid(x_min, y_min, x_max, y_max, res):
    w = int(round((x_max - x_min) / res))
    h = int(round((y_max - y_min) / res))
    return grid_transform(x_min, y_max, res), w, h


def mosaic(pattern, x_min, y_min, x_max, y_max, res, resampling=Resampling.bilinear,
           dtype=np.float32, nodata=np.nan, src_crs="EPSG:2056"):
    """Resample every tile matching `pattern` into one local grid (bands, h, w)."""
    files = sorted(glob.glob(os.path.join(DATA, pattern)))
    if not files:
        raise FileNotFoundError(pattern)
    tr, w, h = local_grid(x_min, y_min, x_max, y_max, res)
    with rasterio.open(files[0]) as s:
        bands = s.count
    out = np.full((bands, h, w), nodata, dtype)
    # LV95 bounds of the destination for a cheap tile filter
    e1, n2 = tr * (0, 0)
    e2, n1 = tr * (w, h)
    for f in files:
        with rasterio.open(f) as s:
            b = s.bounds
            if src_crs == "EPSG:2056" and (b.right < e1 or b.left > e2 or b.top < n1 or b.bottom > n2):
                continue
            tmp = np.full((bands, h, w), nodata, dtype)
            reproject(source=rasterio.band(s, list(range(1, bands + 1))), destination=tmp,
                      src_transform=s.transform, src_crs=s.crs, src_nodata=s.nodata,
                      dst_transform=tr, dst_crs="EPSG:2056", dst_nodata=nodata,
                      resampling=resampling)
            m = ~np.isnan(tmp) if np.issubdtype(dtype, np.floating) else tmp != nodata
            out[m] = tmp[m]
    return out


def save_geotiff(path, arr, x_min, y_max, res, nodata=None):
    arr = arr if arr.ndim == 3 else arr[None]
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                dtype=arr.dtype, crs="EPSG:2056", transform=grid_transform(x_min, y_max, res),
                compress="deflate", tiled=True, BIGTIFF="IF_SAFER")
    if nodata is not None:
        prof["nodata"] = nodata
    with rasterio.open(path, "w", **prof) as d:
        d.write(arr)


class Grid:
    """A north-up local raster with bilinear sampling at arbitrary local (x, y)."""

    def __init__(self, arr, x_min, y_max, res):
        self.a, self.x_min, self.y_max, self.res = arr, x_min, y_max, res

    @classmethod
    def load(cls, name):
        d = np.load(name, allow_pickle=False)
        return cls(d["a"], float(d["x_min"]), float(d["y_max"]), float(d["res"]))

    def save(self, name):
        np.savez(name, a=self.a, x_min=self.x_min, y_max=self.y_max, res=self.res)

    def rc(self, x, y):
        """Fractional (row, col) of local points (pixel centres at integer + 0.5 offsets)."""
        return (self.y_max - np.asarray(y)) / self.res - 0.5, (np.asarray(x) - self.x_min) / self.res - 0.5

    def sample(self, x, y, order=1):
        from scipy.ndimage import map_coordinates
        r, c = self.rc(x, y)
        a = self.a if self.a.ndim == 2 else self.a[0]
        return map_coordinates(a, [np.atleast_1d(r), np.atleast_1d(c)], order=order, mode="nearest")
