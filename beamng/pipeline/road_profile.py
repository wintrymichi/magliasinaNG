"""Cross-section profile of the Strada Cantonale along the calibrated Street View track.

For every station s (0.5 m) of the smoothed camera track, rays are cast left and
right along the normal until they leave the surveyed carriageway (MU 'strada_sentiero'
polygons near the route). This gives the left/right edge offsets, the carriageway
width and centre. Where the paved area continues beyond 9 m (junctions, squares,
driveways) the edge is marked as open.
Output work/road_profile.npz: s, C (track xy), T, N (left normal), tL, tR, openL, openR,
center (xy), width, z_center.
"""
import json, os, pickle
import numpy as np
import shapely
from scipy.ndimage import gaussian_filter1d, median_filter
from config import WORK
from geo import Grid

STEP = 0.5
MAXW = 9.0


def main():
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    P = np.array([p["pos"][:2] for p in poses if p["main_run"]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s0 = np.concatenate([[0], np.cumsum(seg)])
    s = np.arange(0, s0[-1], STEP)
    X = gaussian_filter1d(np.interp(s, s0, P[:, 0]), 8)
    Y = gaussian_filter1d(np.interp(s, s0, P[:, 1]), 8)
    C = np.column_stack([X, Y])
    T = np.column_stack([np.gradient(X), np.gradient(Y)])
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.column_stack([-T[:, 1], T[:, 0]])
    track = shapely.LineString(C)
    road = shapely.union_all([g for g, _ in av["LCSF"].get("strada_sentiero", []) if g.distance(track) < 20])
    road = road.buffer(0.02)
    tt = np.arange(0.0, MAXW + 0.01, 0.05)
    edges = {}
    for side, sg in (("L", 1), ("R", -1)):
        pts = C[:, None, :] + sg * N[:, None, :] * tt[None, :, None]
        inside = shapely.contains_xy(road, pts[..., 0], pts[..., 1])
        # first sample (from the camera outward) that is outside the carriageway
        first_out = np.where(~inside, 1, 0)
        idx = np.argmax(first_out, axis=1)
        none_out = first_out.sum(1) == 0
        off = tt[idx]
        off[none_out] = MAXW
        edges[side] = (off, none_out | (off >= MAXW - 0.1))
    tL, openL = edges["L"]
    tR, openR = edges["R"]
    tR = -tR
    # smooth edges where both sides are closed; keep raw where open
    tLs = median_filter(tL, 5, mode="nearest"); tRs = median_filter(tR, 5, mode="nearest")
    width = tLs - tRs
    mid = 0.5 * (tLs + tRs)
    center = C + N * mid[:, None]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zc = dtm.sample(center[:, 0], center[:, 1])
    np.savez(os.path.join(WORK, "road_profile.npz"), s=s, C=C, T=T, N=N, tL=tLs, tR=tRs, openL=openL,
             openR=openR, center=center, width=width, z_center=zc)
    closed = ~(openL | openR)
    print("stations", len(s), "length %.0f m" % s[-1])
    print("carriageway width (closed sections): median %.2f m, p10 %.2f, p90 %.2f" %
          (np.median(width[closed]), np.percentile(width[closed], 10), np.percentile(width[closed], 90)))
    print("camera lateral position from centre: median %.2f m (positive = left of centre)" % np.median(-mid[closed]))


if __name__ == "__main__":
    main()
