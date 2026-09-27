"""Longitudinal road markings of the Strada Cantonale from the straightened orthophoto strip.

Marking response: white top-hat of the luminance across the road (0.6 m kernel) on
low-saturation pixels. Three line tracks are followed along the road with dynamic
programming (smooth lateral position): the centre line (near the carriageway centre)
and the two edge lines (0.1-0.8 m inside each carriageway edge). Along each track the
response is binarised; runs give painted segments, classified as dashed when the
pattern is regular (dash 1.5-6 m, gap 2-12 m) and solid otherwise. Stretches hidden
by canopy (low orthophoto brightness / tree nDSM over the road) are flagged: there
the panorama strip is used for the response instead.
Output: work/markings.json  {tracks: [{kind, pts [[x,y],...], segments [[s0,s1],...],
pattern}], occluded [[s0,s1],...]}
"""
import json, os
import numpy as np
import cv2
from scipy.ndimage import uniform_filter1d, gaussian_filter1d, maximum_filter1d
from config import WORK
from geo import Grid

DS, DT = 0.10, 0.05


def response(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    L = rgb.astype(np.float32).mean(-1)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 1))          # across the road (t axis = columns)
    top = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, k)
    sat = hsv[..., 1]
    r = top * np.clip((110 - sat) / 60, 0, 1)
    # normalise by local contrast so shaded stretches still respond
    loc = cv2.blur(L, (41, 41)) + 20
    return r / loc * 100


def track(R, t, lo, hi, smooth_px=2):
    """DP over rows: lateral index per row within [lo, hi] (per-row arrays of t)."""
    ns, nt = R.shape
    ti = np.arange(nt)
    cost = np.full((ns, nt), -1e9, np.float32)
    back = np.zeros((ns, nt), np.int16)
    Rs = uniform_filter1d(R, 20, axis=0)                              # 2 m along
    for i in range(ns):
        allowed = (t >= lo[i]) & (t <= hi[i])
        e = np.where(allowed, Rs[i], -1e9)
        if i == 0:
            cost[i] = e
            continue
        prev = cost[i - 1]
        best = maximum_filter1d(prev, size=2 * smooth_px + 1)
        arg = np.zeros(nt, np.int16)
        # argmax within window (small window: explicit)
        cand = np.stack([np.roll(prev, d) for d in range(-smooth_px, smooth_px + 1)])
        arg = (np.argmax(cand, 0) - smooth_px)
        back[i] = (ti - arg).clip(0, nt - 1)
        cost[i] = best + e
    path = np.zeros(ns, np.int64)
    path[-1] = int(np.argmax(cost[-1]))
    for i in range(ns - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    return path


def runs(on, s, min_len=0.6):
    on = np.r_[False, on, False]
    d = np.diff(on.astype(int))
    a = np.where(d == 1)[0]; b = np.where(d == -1)[0]
    out = [(s[x], s[min(y, len(s) - 1)]) for x, y in zip(a, b)]
    return [(x, y) for x, y in out if y - x >= min_len]


def main():
    st = np.load(os.path.join(WORK, "road_strip.npz"))
    rgb, s, t = st["rgb"], st["s"], st["t"]
    X, Y, Nx, Ny = st["X"], st["Y"], st["Nx"], st["Ny"]
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    # carriageway edges in strip coordinates (strip centre = profile centre)
    half = np.interp(s, rp["s"], rp["width"] / 2)
    openL = np.interp(s, rp["s"], rp["openL"].astype(float)) > 0.5
    openR = np.interp(s, rp["s"], rp["openR"].astype(float)) > 0.5
    R = response(rgb)
    # canopy occlusion: tree nDSM over the carriageway centre
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz")); dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    nd = dsm.sample(X, Y) - dtm.sample(X, Y)
    dark = rgb[:, len(t) // 2 - 20:len(t) // 2 + 20].mean((1, 2)) < 75
    occl = (maximum_filter1d((nd > 2.0).astype(np.uint8), 30) > 0) | dark
    tracks = []
    specs = [("centre", -1.2 * np.ones_like(s), 1.2 * np.ones_like(s)),
             ("edge_left", half - 0.9, half - 0.05),
             ("edge_right", -half + 0.05, -half + 0.9)]
    for kind, lo, hi in specs:
        path = track(R, t, lo, hi)
        tt = gaussian_filter1d(t[path].astype(float), 15)
        val = R[np.arange(len(s)), path]
        # local maximum across +-2 px to tolerate the smoothed path
        val = np.max(np.stack([R[np.arange(len(s)), np.clip(path + d, 0, len(t) - 1)] for d in (-2, -1, 0, 1, 2)]), 0)
        on = uniform_filter1d((val > 12).astype(float), 5) > 0.5
        if kind == "edge_left":
            on &= ~openL
        if kind == "edge_right":
            on &= ~openR
        seg = runs(on & ~occl, s)
        # pattern classification over sliding windows
        lens = np.array([b - a for a, b in seg]) if seg else np.zeros(0)
        gaps = np.array([seg[k + 1][0] - seg[k][1] for k in range(len(seg) - 1)]) if len(seg) > 1 else np.zeros(0)
        pts = np.column_stack([X + Nx * tt, Y + Ny * tt])
        tracks.append({"kind": kind, "t": tt.round(3).tolist()[::5], "s": s[::5].round(2).tolist(),
                       "segments": [[round(a, 2), round(b, 2)] for a, b in seg],
                       "dash_len_median": float(np.median(lens[(lens > 1) & (lens < 8)])) if (lens > 1).any() else None,
                       "gap_median": float(np.median(gaps[(gaps > 1.5) & (gaps < 15)])) if (gaps > 1.5).any() else None})
        print(kind, "segments", len(seg), "painted %.0f m" % lens.sum() if len(lens) else 0,
              "dash median", tracks[-1]["dash_len_median"], "gap median", tracks[-1]["gap_median"])
    occ = runs(occl, s, min_len=2.0)
    json.dump({"tracks": tracks, "occluded": [[round(a, 1), round(b, 1)] for a, b in occ]},
              open(os.path.join(WORK, "markings.json"), "w"))
    print("occluded stretches", len(occ), "total %.0f m" % sum(b - a for a, b in occ))
    # diagnostic image of a few stretches
    vis = rgb.copy()
    for tr in tracks:
        tt = np.interp(s, tr["s"], tr["t"])
        cols = np.clip(((tt - t[0]) / DT).astype(int), 0, len(t) - 1)
        for a, b in tr["segments"]:
            ia, ib = int(a / DS), int(b / DS)
            vis[ia:ib, cols[ia:ib]] = (255, 0, 0)
    tiles = [np.rot90(vis[int(a / DS):int((a + 60) / DS)]) for a in (150, 700, 1600, 2950)]
    cv2.imwrite(os.path.join(WORK, "markings_check.jpg"), cv2.cvtColor(np.concatenate(tiles, 0), cv2.COLOR_RGB2BGR))


if __name__ == "__main__":
    main()
