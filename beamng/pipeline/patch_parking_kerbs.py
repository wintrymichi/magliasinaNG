"""Patch of the v3.1 nightly zip after the sidewalks patch (2026-10-23), without building it again: the parking spots of
the parked cars (city.sites.json, facilities.sites.json) whose box reaches over a raised pavement go (a car spawned there
clipped the kerb and jumped: 8 of 10,877 spots). The build keeps the pavement flush under the spots instead
(sidewalks.parking_boxes); this script is only for the zip patched before that.

Run: python patch_parking_kerbs.py <folder that holds levels/>
"""
import json, sys
import numpy as np
from scipy.spatial import cKDTree
import bng
import sidewalks
from config import LEVEL_NAME
from markings_net import read_items, shape_tris

STEP_OVER = 0.05         # m: a pavement this much over the spot's height under its box


def main(root):
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    S = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/sidewalks/items.level.json"))
    T = S[sidewalks.SIDEWALK]
    T = T[sidewalks.up(T)]
    tree = cKDTree(T.mean(1)[:, :2])

    def ztop(P):
        out = np.full(len(P), np.nan)
        _, I = tree.query(P, k=8)
        for j in range(I.shape[1]):
            ii = I[:, j]
            a, b, c = T[ii, 0], T[ii, 1], T[ii, 2]
            v0, v1, v2 = c[:, :2] - a[:, :2], b[:, :2] - a[:, :2], P - a[:, :2]
            d00, d01, d02 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v0 * v2).sum(1)
            d11, d12 = (v1 * v1).sum(1), (v1 * v2).sum(1)
            den = d00 * d11 - d01 * d01
            den = np.where(np.abs(den) < 1e-12, 1.0, den)
            u = (d11 * d02 - d01 * d12) / den
            v = (d00 * d12 - d01 * d02) / den
            ins = (u >= 0) & (v >= 0) & (u + v <= 1) & np.isnan(out)
            out[ins] = (a[:, 2] + u * (c[:, 2] - a[:, 2]) + v * (b[:, 2] - a[:, 2]))[ins]
        return out
    gone = 0
    with zi.writer() as zo:
        for i in zi.infolist():
            nm = i.filename
            if nm in (f"{lv}/city.sites.json", f"{lv}/facilities.sites.json"):
                s = json.loads(zi.read(nm))
                keep = []
                for sp in s.get("parkingSpots", []):
                    x, y, z = sp["pos"]
                    qx, qy, qz, qw = sp.get("rot", [0, 0, 0, 1])
                    yaw = 2 * np.arctan2(qz, qw)
                    w, l = sp.get("scl", [2.5, 5.0, 3])[:2]
                    u, v = np.meshgrid(np.linspace(-w / 2, w / 2, 5), np.linspace(-l / 2, l / 2, 9))
                    u, v = u.ravel(), v.ravel()
                    c, s_ = np.cos(yaw), np.sin(yaw)
                    zt = ztop(np.c_[x + u * c - v * s_, y + u * s_ + v * c])
                    if (np.isfinite(zt) & (zt > z + STEP_OVER)).any():
                        gone += 1
                        continue
                    keep.append(sp)
                s["parkingSpots"] = keep
                zo.writestr(i, json.dumps(s, indent=1))
            else:
                zo.writestr(i, zi.read(i))
    print(f"parking kerbs: {gone} spots removed", flush=True)
    return gone


if __name__ == "__main__":
    main(sys.argv[1])
