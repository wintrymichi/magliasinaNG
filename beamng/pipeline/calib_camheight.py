"""Camera height above the road: NCC of the ground registration at the solved poses
for a range of heights (small local search in shift/heading). Writes camera_height.json."""
import json, math, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import cv2
from config import DATASET, WORK

HS = (2.05, 2.1, 2.15, 2.2, 2.25, 2.3, 2.35, 2.4, 2.45)


def job(i):
    import refine_poses as rp, ortho
    from camera import Pano, rot_z
    P = json.load(open(os.path.join(DATASET, "panoramas.json")))
    S = json.load(open(os.path.join(WORK, "poses.json")))
    rec = P[i]
    img = cv2.imread(rp.pano_file(rec))
    p = Pano(rec, W=img.shape[1], H=img.shape[0])
    p.pos, p.R = np.array(S[i]["pos"]), np.array(S[i]["R"])
    cx, cy = p.pos[:2]
    nf = int(round(rp.PATCH / rp.RES))
    orth = ortho.patch(cx - rp.PATCH, cy - rp.PATCH, cx + rp.PATCH, cy + rp.PATCH, rp.RES)
    ob = cv2.cvtColor(orth, cv2.COLOR_RGB2BGR)
    xs = cx + (np.arange(2 * nf) - nf + 0.5) * rp.RES
    ys = cy + (nf - np.arange(2 * nf) - 0.5) * rp.RES
    X, Y = np.meshgrid(xs, ys)
    nd = (rp.dsm().sample(X.ravel(), Y.ravel()) - rp.dtm().sample(X.ravel(), Y.ravel())).reshape(X.shape)
    F = rp.feature(ob, (orth.sum(-1) > 0) & (nd < 0.4))
    res = {}
    for h in HS:
        D, m = rp.ground_geometry((cx, cy), h, nf)
        best = -1.0
        for dh in (-0.2, 0.0, 0.2):
            g = rp.ground_sample(img, rot_z(-math.radians(dh)) @ p.R, D)
            ncc = rp.masked_ncc(F, rp.feature(g, m), m)
            c = ncc.shape[0] // 2
            best = max(best, float(np.nan_to_num(ncc[c - 3:c + 4, c - 3:c + 4], nan=-1).max()))
        res[h] = best
    return i, res


def main():
    idx = list(range(1, 366, 3))
    with ProcessPoolExecutor(6) as ex:
        out = list(ex.map(job, idx))
    T = np.array([[r[h] for h in HS] for _, r in out])
    good = T.max(1) > 0.2
    m = T[good].mean(0)
    print("n", int(good.sum()), dict(zip(HS, np.round(m, 4))))
    u, c = np.unique(np.array(HS)[T[good].argmax(1)], return_counts=True)
    print("per-pano best height:", dict(zip(u.tolist(), c.tolist())))
    k = int(np.argmax(m))
    h = HS[k]
    if 0 < k < len(HS) - 1:
        a, b, _ = np.polyfit(np.array(HS[k - 1:k + 2]), m[k - 1:k + 2], 2)
        if a < 0:
            h = float(-b / (2 * a))
    print("camera height", h)
    json.dump({"h_cam": h, "table": T.tolist(), "hs": HS}, open(os.path.join(WORK, "camera_height_calib.json"), "w"))


if __name__ == "__main__":
    main()
