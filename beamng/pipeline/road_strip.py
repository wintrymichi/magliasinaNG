"""Straightened orthophoto strip of the Strada Cantonale (for road-marking detection).

Each row = station s along the road-profile centre line (DS m), each column =
lateral offset t (DT m, left positive) in [-TMAX, TMAX]. Sampled from the 10 cm
SWISSIMAGE with bilinear interpolation. Written in blocks to work/road_strip.npz:
rgb (ns, nt, 3) uint8, s, t, plus the centre/normal needed to map back.
"""
import os
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.ndimage import map_coordinates, gaussian_filter1d
from config import WORK, local_to_lv95
import ortho

DS, DT, TMAX = 0.10, 0.05, 7.0


def main():
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    s0, center = rp["s"], rp["center"]
    # smooth centre line and recompute normals
    cx = gaussian_filter1d(center[:, 0], 4); cy = gaussian_filter1d(center[:, 1], 4)
    s = np.arange(0, s0[-1], DS)
    X = np.interp(s, s0, cx); Y = np.interp(s, s0, cy)
    Tx, Ty = np.gradient(X), np.gradient(Y)
    n = np.hypot(Tx, Ty); Tx /= n; Ty /= n
    Nx, Ny = -Ty, Tx
    t = np.arange(-TMAX, TMAX + 1e-6, DT)
    rgb = np.zeros((len(s), len(t), 3), np.uint8)
    B = 400                                   # rows per block (40 m)
    for a in range(0, len(s), B):
        b = min(len(s), a + B)
        PX = X[a:b, None] + Nx[a:b, None] * t[None, :]
        PY = Y[a:b, None] + Ny[a:b, None] * t[None, :]
        x0, x1 = PX.min() - 1, PX.max() + 1
        y0, y1 = PY.min() - 1, PY.max() + 1
        o = ortho.patch(x0, y0, x1, y1, 0.1).astype(np.float32)
        r = (y1 - PY) / 0.1 - 0.5
        c = (PX - x0) / 0.1 - 0.5
        for k in range(3):
            rgb[a:b, :, k] = np.clip(map_coordinates(o[..., k], [r, c], order=1), 0, 255).astype(np.uint8)
    np.savez_compressed(os.path.join(WORK, "road_strip.npz"), rgb=rgb, s=s, t=t, X=X, Y=Y, Nx=Nx, Ny=Ny)
    print("strip", rgb.shape)


if __name__ == "__main__":
    main()
