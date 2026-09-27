"""Resample swisstopo tiles onto the local map frame (whole 4096 m terrain square).

Outputs (WORK):
  dtm05.npz   swissALTI3D 0.5 m bare-earth heights (Italian side filled from Copernicus GLO-30)
  dsm05.npz   swissSURFACE3D 0.5 m surface heights (trees, buildings)
  ortho05.tif SWISSIMAGE resampled to 0.5 m (RGB) for overviews / terrain colour
Every file shares the same grid: x in [-H, H], y in [-H, H], H = TER_HALF + MARGIN.
"""
import os
import numpy as np
from rasterio.warp import Resampling
from scipy.ndimage import binary_dilation, gaussian_filter
from config import WORK, TER_HALF
from geo import mosaic, save_geotiff, Grid

MARGIN = 8.0
H = TER_HALF + MARGIN
RES = 0.5


def main():
    ext = (-H, -H, H, H)
    dtm = mosaic("swissalti3d_05/*.tif", *ext, RES)[0]
    nod = np.isnan(dtm)
    print("DTM nodata fraction", nod.mean())
    if nod.any():
        cop = mosaic("copdem30/*.tif", *ext, RES, src_crs="EPSG:4326")[0]
        ring = binary_dilation(nod, iterations=40) & ~nod & ~np.isnan(cop)
        off = np.nanmedian(dtm[ring] - cop[ring]) if ring.any() else 0.0
        print("Copernicus -> swissALTI3D offset", off)
        # Copernicus is a 30 m DSM: smooth it before use
        cop_s = gaussian_filter(np.nan_to_num(cop, nan=np.nanmean(cop)), 6)
        dtm[nod] = cop_s[nod] + off
    Grid(dtm.astype(np.float32), -H, H, RES).save(os.path.join(WORK, "dtm05.npz"))
    np.save(os.path.join(WORK, "dtm05_nodata.npy"), nod)
    save_geotiff(os.path.join(WORK, "dtm05.tif"), dtm.astype(np.float32), -H, H, RES)

    dsm = mosaic("dsm_05/*.tif", *ext, RES)[0]
    dsm[np.isnan(dsm)] = dtm[np.isnan(dsm)]
    Grid(dsm.astype(np.float32), -H, H, RES).save(os.path.join(WORK, "dsm05.npz"))

    ortho = mosaic("swissimage_010/*.tif", *ext, RES, resampling=Resampling.average,
                   dtype=np.uint8, nodata=0)
    save_geotiff(os.path.join(WORK, "ortho05.tif"), ortho, -H, H, RES)
    print("done", dtm.shape, float(np.nanmin(dtm)), float(np.nanmax(dtm)))


if __name__ == "__main__":
    main()
