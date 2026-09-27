"""Resample swisstopo tiles onto the local map frame.

Outputs (WORK):
  dtm05      swissALTI3D 0.5 m bare-earth heights over the playable area (area.raster_bounds);
             the Italian side is filled from Copernicus GLO-30 (smoothed, shifted onto swissALTI3D)
  dtm05_nodata.npy  cells filled from Copernicus
  dsm05      swissSURFACE3D 0.5 m surface heights (trees, buildings), same grid (gaps: DTM)
  dtm2       swissALTI3D 2 m over the whole terrain block (area.block_bounds), Copernicus where missing
  ortho.tif  SWISSIMAGE 2 m (RGB) over the terrain block
The 0.5 m grids are large (about 22 000 x 18 000 cells): geo.Grid stores them as memory-mapped
.npy files and every step here works on row bands.
"""
import os
import numpy as np
from rasterio.warp import Resampling
from scipy.ndimage import binary_dilation, gaussian_filter
from config import WORK
from geo import mosaic, save_geotiff, Grid
import area

RES = 0.5
COARSE = 2.0
BAND = 1024


def copernicus(x0, y0, x1, y1, res=10.0):
    """Copernicus GLO-30 (a 30 m DSM) on a local grid, smoothed to ~20 m."""
    cop = mosaic("copdem30/*.tif", x0, y0, x1, y1, res, src_crs="EPSG:4326")[0]
    cop = gaussian_filter(np.nan_to_num(cop, nan=float(np.nanmean(cop))), 20.0 / res)
    return Grid(cop.astype(np.float32), x0, y1, res)


def fill_from_copernicus(a, x0, y1, res):
    """Fill the NaN cells of the grid `a` (north-up, top-left x0, y1) in place from Copernicus,
    shifted by the median difference on a ring of valid cells around the gaps. Returns the mask."""
    h, w = a.shape
    nod = np.isnan(a)
    if not nod.any():
        return nod
    bx1, by0 = x0 + w * res, y1 - h * res
    cop = copernicus(x0 - 50, by0 - 50, bx1 + 50, y1 + 50)
    # ring of valid cells around the gaps, on a 10 m block grid
    f = max(int(round(10.0 / res)), 1)
    hc, wc = -(-h // f), -(-w // f)
    pad = np.full((hc * f, wc * f), np.nan, np.float32)
    pad[:h, :w] = a
    blk = pad.reshape(hc, f, wc, f)
    nodc = np.isnan(blk).any((1, 3))
    with np.errstate(all="ignore"):
        meanc = np.nanmean(blk, (1, 3))
    ringc = binary_dilation(nodc, iterations=4) & ~nodc & ~np.isnan(meanc)
    rr, cc = np.nonzero(ringc)
    xs = x0 + (cc + 0.5) * f * res
    ys = y1 - (rr + 0.5) * f * res
    off = float(np.nanmedian(meanc[rr, cc] - cop.sample(xs, ys))) if len(rr) > 50 else 0.0
    print("Copernicus -> swissALTI3D offset %.2f m (%d ring cells)" % (off, len(rr)), flush=True)
    for r0 in range(0, h, BAND):
        band = a[r0:r0 + BAND]
        m = np.isnan(band)
        if m.any():
            r, c = np.nonzero(m)
            band[m] = cop.sample(x0 + (c + 0.5) * res, y1 - (r0 + r + 0.5) * res) + off
    return nod


def main():
    x0, y0, x1, y1 = area.raster_bounds(RES)
    dtm = mosaic("swissalti3d_05/*.tif", x0, y0, x1, y1, RES)[0]
    print("dtm05", dtm.shape, "nodata fraction %.4f" % np.isnan(dtm).mean(), flush=True)
    nod = fill_from_copernicus(dtm, x0, y1, RES)
    Grid(dtm, x0, y1, RES).save(os.path.join(WORK, "dtm05.npz"))
    np.save(os.path.join(WORK, "dtm05_nodata.npy"), nod)
    del nod
    dsm = mosaic("dsm_05/*.tif", x0, y0, x1, y1, RES)[0]
    for r0 in range(0, dsm.shape[0], BAND):
        band = dsm[r0:r0 + BAND]
        m = np.isnan(band)
        band[m] = dtm[r0:r0 + BAND][m]
    Grid(dsm, x0, y1, RES).save(os.path.join(WORK, "dsm05.npz"))
    del dsm, dtm

    bx0, by0, bx1, by1 = area.block_bounds(COARSE)
    d2 = mosaic("swissalti3d_2/*.tif", bx0, by0, bx1, by1, COARSE, resampling=Resampling.average)[0]
    print("dtm2", d2.shape, "nodata fraction %.4f" % np.isnan(d2).mean(), flush=True)
    fill_from_copernicus(d2, bx0, by1, COARSE)
    Grid(d2, bx0, by1, COARSE).save(os.path.join(WORK, "dtm2.npz"))
    ortho = mosaic("swissimage_2/*.tif", bx0, by0, bx1, by1, COARSE, resampling=Resampling.average,
                   dtype=np.uint8, nodata=0)
    save_geotiff(os.path.join(WORK, "ortho.tif"), ortho, bx0, by1, COARSE)
    print("done", flush=True)


if __name__ == "__main__":
    main()
