"""Extract swissSURFACE3D LiDAR points (non-vegetation) near the corridor objects.

Reads every corridor LAS tile in chunks and keeps classes 1 (unclassified: walls,
fences, poles, guardrails, vehicles), 2 (ground), 6 (building) and 17 (bridge)
inside a mask (rasterised buffers around walls and the road corridor).
Output: work/lidar_near.npz  (x, y, z local; cls; intensity)
"""
import glob, os, pickle, zipfile
import numpy as np
import laspy
import shapely
from rasterio import features
from rasterio.transform import Affine
from config import DATA, WORK, lv95_to_local
import json

KEEP = (1, 2, 6, 17)


def main(corridor_m=45.0):
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    track = shapely.LineString([p["pos"][:2] for p in poses if p["main_run"]])
    region = [track.buffer(corridor_m)]
    region += [g.buffer(2.0) for g, _ in av["SOSF"].get("muro", [])]
    region += [g.buffer(2.0) for g, _ in av["SOLI"].get("muro", [])]
    U = shapely.union_all(region)
    res = 0.5
    x0, y0, x1, y1 = U.bounds
    W, H = int((x1 - x0) / res) + 2, int((y1 - y0) / res) + 2
    tr = Affine(res, 0, x0, 0, -res, y1)
    mask = features.rasterize([(U, 1)], out_shape=(H, W), transform=tr, fill=0, dtype=np.uint8).astype(bool)
    out = {k: [] for k in ("x", "y", "z", "cls", "inten")}
    las_dir = os.path.join(DATA, "lidar", "las")
    os.makedirs(las_dir, exist_ok=True)
    for zp in sorted(glob.glob(os.path.join(DATA, "lidar", "*.las.zip"))):
        z = zipfile.ZipFile(zp)
        name = z.namelist()[0]
        path = os.path.join(las_dir, name)
        if not os.path.exists(path):
            z.extract(name, las_dir)
        n_keep = 0
        with laspy.open(path) as f:
            for ch in f.chunk_iterator(4_000_000):
                c = np.asarray(ch.classification)
                sel = np.isin(c, KEEP)
                if not sel.any():
                    continue
                X = np.asarray(ch.x)[sel]; Y = np.asarray(ch.y)[sel]; Z = np.asarray(ch.z)[sel]
                lx, ly = lv95_to_local(X, Y)
                ci = ((lx - x0) / res).astype(np.int64)
                ri = ((y1 - ly) / res).astype(np.int64)
                ok = (ci >= 0) & (ci < W) & (ri >= 0) & (ri < H)
                ok[ok] = mask[ri[ok], ci[ok]]
                out["x"].append(lx[ok].astype(np.float32)); out["y"].append(ly[ok].astype(np.float32))
                out["z"].append(Z[ok].astype(np.float32)); out["cls"].append(c[sel][ok].astype(np.uint8))
                out["inten"].append(np.asarray(ch.intensity)[sel][ok].astype(np.uint16))
                n_keep += int(ok.sum())
        print(os.path.basename(zp), "kept", n_keep, flush=True)
    np.savez_compressed(os.path.join(WORK, "lidar_near.npz"), **{k: np.concatenate(v) for k, v in out.items()})
    print("total", sum(len(a) for a in out["x"]))


if __name__ == "__main__":
    main()
