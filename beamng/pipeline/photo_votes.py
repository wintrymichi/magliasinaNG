"""Multi-view label votes: what the segmented panoramas see at given 3D points.

label_votes(P) projects every point into the horizon views (Mask2Former labels) of the
panoramas 3-16 m away (calibrated poses) and returns, per point, a histogram of the labels
over the panoramas that see it (first view that contains the point).
"""
import json, os
import numpy as np
from PIL import Image
from config import WORK, DATASET
import camera

VW, VH = 1600, 1200
_cache = {}


def _seg(rec, dn):
    f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
    if f not in _cache:
        if len(_cache) > 64:
            _cache.clear()
        _cache[f] = np.asarray(Image.open(f)) if os.path.exists(f) else None
    return _cache[f]


def label_votes(P, d_min=3.0, d_max=16.0, n_labels=65):
    """P: (n, 3) world points -> (n, n_labels) vote counts."""
    P = np.asarray(P, float)
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    H = np.zeros((len(P), n_labels), np.int32)
    for p in poses:
        pos = np.array(p["pos"])
        d = np.hypot(P[:, 0] - pos[0], P[:, 1] - pos[1])
        near = np.where((d > d_min) & (d < d_max))[0]
        if not len(near):
            continue
        rec = D[p["index"]]
        done = np.zeros(len(near), bool)
        for dn, rel in camera.VIEW_REL.items():
            cc, rr, ok = camera.world_to_view(P[near], pos, p["R"], rec, rel, 0)
            inb = ok & (cc >= 0) & (cc < VW - 0.5) & (rr >= 0) & (rr < VH - 0.5) & ~done
            if not inb.any():
                continue
            seg = _seg(rec, dn)
            if seg is None:
                continue
            k = np.where(inb)[0]
            lab = seg[np.round(rr[k]).astype(int).clip(0, VH - 1), np.round(cc[k]).astype(int).clip(0, VW - 1)]
            np.add.at(H, (near[k], lab), 1)
            done[k] = True
    return H
