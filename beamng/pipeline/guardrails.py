"""Guardrails from swissSURFACE3D LiDAR, checked against the Street View segmentation.

Candidates: unclassified points (class 1) 0.30-1.05 m above the DTM, at most 4 m
outside / 0.8 m inside the surveyed paved area, near the route. They are expressed in
route coordinates (s = distance along the calibrated Street View track, t = signed
lateral offset), clustered per side into runs with gaps < 3 m, binned at 0.5 m and
smoothed. A run is kept when it is >= 6 m long and the panoramas see 'Guard Rail'
pixels where it projects (vote over the views that see it).
Output: work/guardrails.json  [{side, pts: [[x, y, z_ground, top_h], ...], support}]
"""
import json, math, os, pickle
import numpy as np
import shapely
from scipy.ndimage import median_filter
from scipy.spatial import cKDTree
from PIL import Image
from config import WORK, DATASET
from geo import Grid

GR = 4  # Mapillary 'Guard Rail'


def track_frame(poses):
    P = np.array([p["pos"][:2] for p in poses if p["main_run"]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    # dense resample every 0.5 m
    ss = np.arange(0, s[-1], 0.5)
    X = np.interp(ss, s, P[:, 0]); Y = np.interp(ss, s, P[:, 1])
    from scipy.ndimage import gaussian_filter1d
    X = gaussian_filter1d(X, 6); Y = gaussian_filter1d(Y, 6)
    T = np.column_stack([np.gradient(X), np.gradient(Y)])
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.column_stack([-T[:, 1], T[:, 0]])           # left normal
    return ss, np.column_stack([X, Y]), T, N


def to_st(xy, ss, C, N):
    tree = cKDTree(C)
    d, j = tree.query(xy)
    t = ((xy - C[j]) * N[j]).sum(1)
    return ss[j], t, j


def main():
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    lid = np.load(os.path.join(WORK, "lidar_near.npz"))
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    ss, C, T, N = track_frame(poses)
    track = shapely.LineString(C)
    paved = shapely.union_all([g for cls in ("strada_sentiero", "marciapiede", "altro_rivestimento_duro")
                               for g, _ in av["LCSF"].get(cls, []) if g.distance(track) < 30])
    m = lid["cls"] == 1
    x, y, z = lid["x"][m].astype(float), lid["y"][m].astype(float), lid["z"][m].astype(float)
    hag = z - dtm.sample(x, y)
    m2 = (hag > 0.30) & (hag < 1.05)
    x, y, z, hag = x[m2], y[m2], z[m2], hag[m2]
    pts = shapely.points(x, y)
    dist_out = shapely.distance(pts, paved)
    inside = shapely.contains(paved, pts)
    edge_d = np.where(inside, shapely.distance(pts, paved.boundary), 0)
    keep = (dist_out < 4.0) & (edge_d < 0.8)
    x, y, hag = x[keep], y[keep], hag[keep]
    s, t, j = to_st(np.column_stack([x, y]), ss, C, N)
    near = np.abs(t) < 14
    x, y, hag, s, t = x[near], y[near], hag[near], s[near], t[near]
    print("candidate points", len(x))
    runs = []
    for side in (1, -1):
        sm = np.sign(t) == side
        if sm.sum() < 20:
            continue
        s1, t1, h1 = s[sm], t[sm], hag[sm]
        order = np.argsort(s1)
        s1, t1, h1 = s1[order], t1[order], h1[order]
        # split into runs at gaps > 3 m or lateral jumps > 1.5 m
        br = np.where((np.diff(s1) > 3.0) | (np.abs(np.diff(t1)) > 1.5))[0] + 1
        for a, b in zip(np.r_[0, br], np.r_[br, len(s1)]):
            if s1[b - 1] - s1[a] < 6.0 or b - a < 25:
                continue
            bins = np.arange(s1[a], s1[b - 1] + 0.5, 0.5)
            k = np.clip(np.searchsorted(bins, s1[a:b]) - 1, 0, len(bins) - 1)
            tt = np.full(len(bins), np.nan); hh = np.full(len(bins), np.nan)
            for q in range(len(bins)):
                sel = k == q
                if sel.sum():
                    tt[q] = np.median(t1[a:b][sel]); hh[q] = np.percentile(h1[a:b][sel], 90)
            ok = ~np.isnan(tt)
            tt = np.interp(bins, bins[ok], tt[ok]); hh = np.interp(bins, bins[ok], hh[ok])
            tt = median_filter(tt, 9, mode="nearest"); hh = median_filter(hh, 9, mode="nearest")
            jj = np.clip(np.searchsorted(ss, bins), 0, len(ss) - 1)
            P = C[jj] + N[jj] * tt[:, None]
            zg = dtm.sample(P[:, 0], P[:, 1])
            runs.append({"side": int(side), "s0": float(bins[0]), "s1": float(bins[-1]),
                         "pts": np.column_stack([P, zg, np.clip(hh, 0.6, 0.95)]).round(3).tolist()})
    print("runs", len(runs), "total length %.0f m" % sum(r["s1"] - r["s0"] for r in runs))
    verify(runs, poses)
    json.dump(runs, open(os.path.join(WORK, "guardrails.json"), "w"))


def verify(runs, poses):
    """Fraction of the run's projected points that fall on 'Guard Rail' pixels (8 px tolerance)
    in the dataset p00 views of panoramas within 25 m (exact calibrated projection)."""
    import camera
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    for r in runs:
        P = np.array(r["pts"])
        P3 = np.column_stack([P[:, :2], P[:, 2] + P[:, 3] * 0.75])      # middle of the rail
        mid = P[len(P) // 2, :2]
        hits = tot = 0
        for p in poses:
            if np.min(np.hypot(P[:, 0] - p["pos"][0], P[:, 1] - p["pos"][1])) > 20:
                continue
            rec = D[p["index"]]
            for dn, rel in camera.VIEW_REL.items():
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
                c, rr, ok = camera.world_to_view(P3, p["pos"], p["R"], rec, rel, 0)
                dist = np.hypot(P3[:, 0] - p["pos"][0], P3[:, 1] - p["pos"][1])
                inb = ok & (c >= 8) & (c < 1592) & (rr >= 8) & (rr < 1192) & (dist < 20)
                if inb.sum() < 3 or not os.path.exists(f):
                    continue
                seg = np.asarray(Image.open(f))
                cc, rw = c[inb].astype(int), rr[inb].astype(int)
                win = np.zeros(len(cc), bool)
                for du in (-8, 0, 8):
                    for dv in (-8, 0, 8):
                        win |= seg[rw + dv, cc + du] == GR
                hits += int(win.sum()); tot += int(inb.sum())
        r["support"] = hits / tot if tot else None
    sup = [r["support"] for r in runs if r["support"] is not None]
    print("photo support: median %.2f, runs with support<0.2: %d of %d (no view: %d)" %
          (np.median(sup) if sup else -1, sum(1 for v in sup if v < 0.2), len(runs),
           sum(1 for r in runs if r["support"] is None)))


if __name__ == "__main__":
    main()
