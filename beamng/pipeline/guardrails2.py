"""Guardrails along the Strada Cantonale by multi-view voting of the segmentation.

Candidate positions: every 0.5 m station of the road profile, on both sides, at
offsets 0.2..1.5 m outside the surveyed carriageway edge, at 0.45 m and 0.70 m above
the base (lower and upper part of a W-beam); the base is the DTM but never lower
than the road edge (rails on valley-side retaining walls stand at road level). Each candidate is projected with the
calibrated poses into the dataset p00 views of every panorama 3-18 m away; a vote is
counted when the pixel (6 px tolerance) is labelled 'Guard Rail'. Per station/side
the best offset is kept; stations with support >= 0.45 (and >= 3 views) are
guardrail. Runs shorter than 4 m are dropped, gaps < 2.5 m bridged. Where a
confirmed LiDAR run exists (guardrails.json, support >= 0.3) its measured
lateral position and height replace the photo estimate.
Output: work/guardrails_final.json [{side, pts: [[x,y,zg,h],...], src}]
"""
import json, os
import numpy as np
from PIL import Image
from scipy.ndimage import median_filter, binary_closing, label
from config import WORK, DATASET
from geo import Grid
import camera

GR = 4
OFFS = np.array([0.2, 0.5, 0.8, 1.1, 1.5])
HEIGHTS = (0.45, 0.70)


def main():
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    s, C, N, tL, tR = rp["s"], rp["C"], rp["N"], rp["tL"], rp["tR"]
    openL, openR = rp["openL"], rp["openR"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    ns = len(s)
    votes = np.zeros((2, ns, len(OFFS)))
    seen = np.zeros((2, ns, len(OFFS)))
    # candidate xy per side/offset
    cand = np.zeros((2, ns, len(OFFS), 2))
    for k, (edge, sg) in enumerate(((tL, 1), (tR, -1))):
        for j, o in enumerate(OFFS):
            cand[k, :, j] = C + N * (edge + sg * o)[:, None]
    zg = dtm.sample(cand[..., 0].ravel(), cand[..., 1].ravel()).reshape(cand.shape[:3])
    # guardrails stand at road level: on a valley-side retaining wall the DTM just outside the
    # edge is already far below the road, so the base is never lower than the road edge
    import roadheight
    rfn = roadheight.height_fn()
    ze = np.zeros((2, ns))
    for k, (edge, sg) in enumerate(((tL, 1), (tR, -1))):
        e = C + N * (edge - sg * 0.4)[:, None]
        ze[k] = rfn(e[:, 0], e[:, 1])
    zg = np.maximum(zg, ze[:, :, None] - 0.1)
    segcache = {}
    for p in poses:
        rec = D[p["index"]]
        pos = np.array(p["pos"])
        d = np.hypot(cand[..., 0] - pos[0], cand[..., 1] - pos[1])
        near = (d > 3) & (d < 18)
        if not near.any():
            continue
        ks, ss_, js = np.where(near)
        for h in HEIGHTS:
            P3 = np.column_stack([cand[ks, ss_, js], zg[ks, ss_, js] + h])
            hit_any = np.zeros(len(P3), bool)
            vis_any = np.zeros(len(P3), bool)
            for dn, rel in camera.VIEW_REL.items():
                c, r, ok = camera.world_to_view(P3, pos, p["R"], rec, rel, 0)
                inb = ok & (c >= 6) & (c < 1594) & (r >= 6) & (r < 1194) & ~vis_any
                if not inb.any():
                    continue
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
                if f not in segcache:
                    if len(segcache) > 64:
                        segcache.clear()
                    segcache[f] = np.asarray(Image.open(f)) if os.path.exists(f) else None
                seg = segcache[f]
                if seg is None:
                    continue
                ci, ri = c[inb].astype(int), r[inb].astype(int)
                hit = np.zeros(len(ci), bool)
                for du in (-6, 0, 6):
                    for dv in (-6, 0, 6):
                        hit |= seg[ri + dv, ci + du] == GR
                idx = np.where(inb)[0]
                vis_any[idx] = True
                hit_any[idx] = hit
            np.add.at(votes, (ks, ss_, js), hit_any.astype(float) / len(HEIGHTS))
            np.add.at(seen, (ks, ss_, js), vis_any.astype(float) / len(HEIGHTS))
    sup = votes / np.maximum(seen, 1e-9)
    best = np.argmax(np.where(seen >= 3, sup, -1), axis=2)                 # (2, ns)
    bsup = np.take_along_axis(sup, best[..., None], 2)[..., 0]
    bseen = np.take_along_axis(seen, best[..., None], 2)[..., 0]
    present = (bsup >= 0.45) & (bseen >= 3)
    present[0] &= ~openL
    present[1] &= ~openR
    lid = json.load(open(os.path.join(WORK, "guardrails.json")))
    runs = []
    for k, sg in ((0, 1), (1, -1)):
        pr = binary_closing(present[k], structure=np.ones(13))             # bridge gaps < 6 m
        lab, n = label(pr)
        edge = tL if k == 0 else tR
        for q in range(1, n + 1):
            ii = np.where(lab == q)[0]
            if s[ii[-1]] - s[ii[0]] < 4.0:
                continue
            off = median_filter(OFFS[best[k, ii]], 21, mode="nearest")
            xy = C[ii] + N[ii] * (edge[ii] + sg * off)[:, None]
            h = np.full(len(ii), 0.75)
            src = "photo"
            # LiDAR refinement where a confirmed run overlaps
            for r in lid:
                if r["side"] != sg or (r.get("support") or 0) < 0.3:
                    continue
                lo, hi = max(r["s0"], s[ii[0]]), min(r["s1"], s[ii[-1]])
                if hi - lo < 2:
                    continue
                L = np.array(r["pts"])
                ls = np.linspace(r["s0"], r["s1"], len(L))
                m = (s[ii] >= lo) & (s[ii] <= hi)
                xy[m, 0] = np.interp(s[ii][m], ls, L[:, 0])
                xy[m, 1] = np.interp(s[ii][m], ls, L[:, 1])
                h[m] = np.interp(s[ii][m], ls, L[:, 3])
                src = "photo+lidar"
            zgr = np.maximum(dtm.sample(xy[:, 0], xy[:, 1]), ze[k, ii] - 0.1)
            runs.append({"side": sg, "s0": float(s[ii[0]]), "s1": float(s[ii[-1]]), "src": src,
                         "support": float(np.mean(bsup[k, ii])),
                         "pts": np.column_stack([xy, zgr, h]).round(3).tolist()})
    json.dump(runs, open(os.path.join(WORK, "guardrails_final.json"), "w"))
    tot = sum(r["s1"] - r["s0"] for r in runs)
    print("guardrail runs", len(runs), "length %.0f m" % tot,
          "| right %.0f m, left %.0f m" % (sum(r["s1"] - r["s0"] for r in runs if r["side"] < 0),
                                           sum(r["s1"] - r["s0"] for r in runs if r["side"] > 0)),
          "| with lidar", sum(1 for r in runs if "lidar" in r["src"]))


if __name__ == "__main__":
    main()
