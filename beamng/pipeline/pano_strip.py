"""Straightened road strip built from the Street View panoramas (ground projection).

Same geometry as road_strip.py (centre line of the road profile) but finer
(DS x DT) and seen from the car, i.e. also under tree canopy. Every strip pixel is
a point on the road surface (DTM smoothed); it is coloured from the calibrated
panorama that sees it from the best distance (2.9-11 m, closest first), skipping
pixels labelled as vehicles/people in that panorama's view segmentation.
Output: work/pano_strip.npz  rgb (ns, nt, 3), src (pano index), dist.
"""
import json, os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, DATASET
from geo import Grid
import camera

DS, DT, TMAX = 0.05, 0.03, 7.0
DMIN, DMAX = 2.9, 11.0
BAD = {19, 20, 21, 22, 52, 54, 55, 56, 57, 59, 60, 61, 62, 63, 64}


def main():
    rs = np.load(os.path.join(WORK, "road_strip.npz"))
    s0, X0, Y0 = rs["s"], rs["X"], rs["Y"]
    s = np.arange(0, s0[-1], DS)
    X = np.interp(s, s0, X0); Y = np.interp(s, s0, Y0)
    Nx = np.interp(s, s0, rs["Nx"]); Ny = np.interp(s, s0, rs["Ny"])
    nn = np.hypot(Nx, Ny); Nx /= nn; Ny /= nn
    t = np.arange(-TMAX, TMAX + 1e-6, DT)
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    PP = np.array([p["pos"] for p in poses])
    rgb = np.zeros((len(s), len(t), 3), np.uint8)
    src = np.full((len(s), len(t)), -1, np.int16)
    best = np.full((len(s), len(t)), np.inf, np.float32)
    B = 400                                                  # 20 m blocks
    cache = {}
    for a in range(0, len(s), B):
        b = min(len(s), a + B)
        PX = X[a:b, None] + Nx[a:b, None] * t[None, :]
        PY = Y[a:b, None] + Ny[a:b, None] * t[None, :]
        r, c = dtm.rc(PX, PY)
        PZ = map_coordinates(zs, [r, c], order=1, mode="nearest")
        ctr = np.array([PX.mean(), PY.mean()])
        near = np.where(np.hypot(PP[:, 0] - ctr[0], PP[:, 1] - ctr[1]) < 30)[0]
        # closest panoramas first so that ties keep the nearest
        for i in near:
            p, rec = poses[i], D[i]
            d = np.hypot(PX - p["pos"][0], PY - p["pos"][1])
            m = (d > DMIN) & (d < DMAX) & (d < best[a:b])
            if not m.any():
                continue
            key = i
            if key not in cache:
                if len(cache) > 8:
                    cache.pop(next(iter(cache)))
                img = cv2.imread(os.path.join(DATASET, "panorami", f"{rec['index']:04d}_{rec['id']}.jpg"))
                cache[key] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cache[key]
            P3 = np.stack([PX[m], PY[m], PZ[m]], -1)
            dc = (P3 - np.array(p["pos"])) @ np.array(p["R"])
            lon = np.arctan2(dc[:, 0], dc[:, 1])
            lat = np.arcsin(np.clip(dc[:, 2] / np.linalg.norm(dc, axis=1), -1, 1))
            H, W = img.shape[:2]
            u = (lon + np.pi) / (2 * np.pi) * W - 0.5
            v = (np.pi / 2 - lat) / np.pi * H - 0.5
            # vehicles / people in the segmentation of the view that contains the pixel
            okm = np.ones(len(u), bool)
            for dn, rel in camera.VIEW_REL.items():
                cc, rr, ok = camera.world_to_view(P3, p["pos"], p["R"], rec, rel, 0)
                inb = ok & (cc >= 0) & (cc < 1600) & (rr >= 0) & (rr < 1200)
                if not inb.any():
                    continue
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
                if not os.path.exists(f):
                    continue
                sg = np.asarray(Image.open(f))
                lab = sg[rr[inb].astype(int), cc[inb].astype(int)]
                bad = np.isin(lab, list(BAD))
                idx = np.where(inb)[0]
                okm[idx[bad]] = False
            col = np.stack([map_coordinates(img[..., k], [v, u % W], order=1, mode="wrap") for k in range(3)], -1)
            rows, cols = np.where(m)
            rows, cols = rows[okm], cols[okm]
            rgb[a + rows, cols] = col[okm].astype(np.uint8)
            src[a + rows, cols] = i
            best[a + rows, cols] = d[m][okm]
        if (a // B) % 20 == 0:
            print("block", a // B, "of", len(s) // B, flush=True)
    np.savez_compressed(os.path.join(WORK, "pano_strip.npz"), rgb=rgb, src=src, dist=best, s=s, t=t, X=X, Y=Y,
                        Nx=Nx, Ny=Ny)
    print("done", rgb.shape, "coverage %.2f" % (src >= 0).mean())


if __name__ == "__main__":
    main()
