"""Find the sign convention of Street View pitch/roll by making verticals vertical.

For each candidate convention every panorama in a sample is resampled into
level perspective views (8 directions); near-vertical line segments are detected
and their tilt from the image vertical is measured. The convention with the
smallest tilt wins and is stored in work/attitude_convention.json.
Also reports the residual tilt per panorama (a check on the metadata itself).
"""
import json, math, os, sys
import numpy as np
import cv2
from PIL import Image
from config import DATASET, WORK
from camera import Pano, rot_z

Image.MAX_IMAGE_PIXELS = None
VW = 1024
FOV = 90.0


def level_view(img, pano, yaw_deg, w=VW, h=VW, fov=FOV, pitch_deg=0.0):
    f = w / 2 / math.tan(math.radians(fov) / 2)
    ii, jj = np.meshgrid(np.arange(w) - w / 2 + 0.5, h / 2 - np.arange(h) - 0.5)
    y = math.radians(yaw_deg)
    p = math.radians(pitch_deg)
    fwd = np.array([math.sin(y) * math.cos(p), math.cos(y) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(y), -math.sin(y), 0.0])
    up = np.cross(right, fwd)
    d = fwd * f + ii[..., None] * right + jj[..., None] * up
    u, v = pano.dir_to_pixel(d)
    return cv2.remap(img, u.astype(np.float32), v.astype(np.float32), cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_WRAP)


def vertical_tilts(gray):
    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = lsd.detect(gray)[0]
    if lines is None:
        return np.zeros(0), np.zeros(0)
    l = np.asarray(lines).reshape(-1, 4)
    dx, dy = l[:, 2] - l[:, 0], l[:, 3] - l[:, 1]
    length = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dx, dy))            # 0 = vertical
    ang = (ang + 90) % 180 - 90
    # keep long near-vertical segments away from the image border (less distortion)
    xm = (l[:, 0] + l[:, 2]) / 2
    ok = (length > 50) & (np.abs(ang) < 8) & (np.abs(xm - VW / 2) < VW * 0.35)
    return ang[ok], length[ok]


def main():
    panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
    files = {p["id"]: os.path.join(DATASET, "panorami", f"{p['index']:04d}_{p['id']}.jpg") for p in panos}
    sample = panos[::12]
    cands = {"none": dict(sp=0, sr=0, order="pr")}
    for sp in (1, -1):
        for sr in (1, -1):
            cands[f"sp{sp:+d}_sr{sr:+d}"] = dict(sp=sp, sr=sr, order="pr")
    score = {k: [] for k in cands}
    per_pano = []
    for rec in sample:
        img = cv2.imread(files[rec["id"]])
        img = cv2.resize(img, (3328, 1664), interpolation=cv2.INTER_AREA)
        row = {"index": rec["index"]}
        for k, conv in cands.items():
            pano = Pano(rec, W=3328, H=1664, conv=conv)
            angs, wts = [], []
            for yaw in range(0, 360, 45):
                g = cv2.cvtColor(level_view(img, pano, pano.heading + yaw), cv2.COLOR_BGR2GRAY)
                a, w = vertical_tilts(g)
                angs.append(a); wts.append(w)
            a, w = np.concatenate(angs), np.concatenate(wts)
            s = float(np.sum(np.abs(a) * w) / max(w.sum(), 1))
            score[k].append(s)
            row[k] = round(s, 3)
        per_pano.append(row)
        print(row, flush=True)
    res = {k: float(np.mean(v)) for k, v in score.items()}
    print("mean |tilt| (deg, length-weighted):", res)
    best = min((k for k in res if k != "none"), key=res.get)
    conv = cands[best]
    json.dump(conv, open(os.path.join(WORK, "attitude_convention.json"), "w"))
    json.dump({"scores": res, "per_pano": per_pano, "best": best},
              open(os.path.join(WORK, "attitude_calibration.json"), "w"), indent=1)
    print("best", best, conv)


if __name__ == "__main__":
    main()
