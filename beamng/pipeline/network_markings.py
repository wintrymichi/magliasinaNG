"""Road paint of the whole network (v2.1), measured in the 10 cm SWISSIMAGE orthophoto (2024).

Up to v2.0 only the Strada Cantonale Magliaso - Pura had road markings (markings*.py, from the
orthophoto checked in the panoramas); the other 208 km of roads, the cantonal road to Gravesano
included, had none. Only paint that the orthophoto shows is built here: no line is added because
a road of that kind "normally" has one.

For every drivable swissTLM3D line of the network (network.py) outside the Street View corridor, a
straightened strip of the orthophoto (DS m along the line, DT m across it, the carriageway and
EXTRA m beyond each edge):
1. paint response, white (top-hat of the luminance across the road on low-saturation pixels,
   relative to the local contrast, as markings.response) and yellow (top-hat of the yellowness);
   cells under the canopy (swissSURFACE3D - swissALTI3D over NDSM_TREE m) or in deep shade are hidden;
2. longitudinal lines: in windows of WIN m every WIN/2 m, the column profile of the response (the
   mean of its top 30 % over the rows that are not hidden: a dashed line paints a third of a
   window) has peaks where a line runs; peaks are linked from window to window into tracks;
3. along every track the painted runs: dashed stretches (dashes DASH m apart by gaps, regular)
   are regularised to their measured dash length and period, a dash hidden by a car in between
   put back; solid runs (> SOLID m) are kept as measured;
4. hidden stretches: a track seen on both sides of one no longer than FILL m continues through it
   with the same pattern; longer ones stay unpainted and are listed for the review;
5. the other paint inside the carriageways (pedestrian crossings, which are yellow in
   Switzerland, stop and give-way lines, arrows, hatched areas, text): paint blobs vectorised as
   in markings_raster.py, vehicles (compact blobs, yellow buses) left out.
Output: work/network_markings.json
    {"lines": [{"seg", "color", "width", "pts": [[x, y], ...], "runs": [[x0, y0, x1, y1] ...]}],
     "polygons": [{"color", "ring": [[x, y], ...]}], "hidden": [{"seg", "from", "to", "len"}],
     "segments": {seg: {"visible_m", "hidden_m", "lines": n, "pattern": ...}}}
Built into the level by markings_net.py (stage 'markings' of build_level.py).
    python network_markings.py [seg ids for a debug image]
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import cv2
import shapely
from scipy.ndimage import gaussian_filter1d, median_filter, uniform_filter1d
from scipy.signal import find_peaks, peak_widths
from config import WORK
from geo import Grid

DS, DT = 0.10, 0.05
EXTRA = 0.8            # m of strip beyond each carriageway edge
WIN, STEP = 12.0, 6.0  # m, windows of the column profile
PEAK_WHITE = 14.0      # response of a painted line in the profile (markings.response scale)
PEAK_YELLOW = 18.0
ROW_FRAC = 0.5         # a row is painted where the response is over this fraction of its track's peaks
LINK = 0.30            # m, largest lateral step of a track between two windows
JOIN = 0.50            # m, lateral step between the end of a track and the start of the next one it continues
DUP = 0.35             # m, two tracks closer than this side by side are the same line
MAX_MISS = 3           # windows a track may miss (hidden, a car) before it ends
MIN_TRACK = 3          # windows of evidence of a track
DASH = (0.8, 6.5)      # m, dash lengths
GAP = (1.0, 13.0)      # m, gaps of a dashed line
PERIOD = (3.0, 15.0)   # m, dash + gap of a dashed line (Swiss lines: 1.5 / 3, 2 / 4, 3 / 3, 3 / 6, 4 / 8 m ...)
SOLID = 6.5            # m, runs longer than this are solid
MERGE = 0.6            # m, painted runs closer than this are one
SIDE = 0.15            # m beyond the edge of a line where the asphalt on either side of it is measured
INSIDE = 0.05          # m beyond the surveyed carriageway edge a line may lie
SIDE_DL = 18.0         # luminance the line is brighter than the asphalt on both sides
SIDE_SAT = 75.0        # saturation (0-255) over which a side is a verge, grass or a coloured surface
FILL = 60.0            # m, hidden stretches a track continues through
SMALL_GAP = 1.2        # m, gaps of a solid line that are not interruptions (a worn spot, a car's shadow)
MIN_SOLID = 3.0        # m, shortest piece of a solid line
ISOLATED = 20.0        # m, a solid line alone on its road shorter than this is not trusted
NDSM_TREE = 2.0        # m of canopy over the road that hides it
DARK = 62.0            # mean luminance (1 m x 0.25 m) under which the road is in shade: paint there is not trusted
MIN_CLASSES = {"10m Strasse", "8m Strasse", "6m Strasse", "4m Strasse", "3m Strasse", "Autobahn", "Autostrasse",
               "Ausfahrt", "Einfahrt", "Verbindung", "Platz", "Zufahrt", "Dienstzufahrt", "Raststaette"}
OUT = os.path.join(WORK, "network_markings.json")
RES_O = 0.10           # m, cells of the blocks of the other paint


# ---------------------------------------------------------------------- strip
def centre_line(net, k):
    """Smoothed stations of segment k: (points (n, 2), arc length (n,), widths (n,))."""
    s = net["segs"][k]
    a, n = s["first"], s["n"]
    X, Y = net["x"][a:a + n], net["y"][a:a + n]
    if n >= 4:
        X = gaussian_filter1d(X, 1.5, mode="nearest")
        Y = gaussian_filter1d(Y, 1.5, mode="nearest")
    d = np.r_[0, np.cumsum(np.hypot(np.diff(X), np.diff(Y)))]
    w = median_filter(net["width"][a:a + n], min(7, n | 1), mode="nearest") if n >= 3 else net["width"][a:a + n]
    return np.column_stack([X, Y]), d, w


def strip_geometry(P, d, w):
    """Rows along the line every DS m: centre, normal (left), half width; columns across it."""
    ss = np.arange(0.0, d[-1] + 1e-6, DS)
    x, y = np.interp(ss, d, P[:, 0]), np.interp(ss, d, P[:, 1])
    tx, ty = np.gradient(x), np.gradient(y)
    nn = np.maximum(np.hypot(tx, ty), 1e-9)
    tx, ty = tx / nn, ty / nn
    half = np.interp(ss, d, w) / 2
    tmax = float(half.max() + EXTRA)
    tt = np.arange(-tmax, tmax + 1e-6, DT)
    return ss, x, y, -ty, tx, half, tt


def response_white(rgb):
    """markings.response on a strip (rows along the road, columns across it)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    L = rgb.astype(np.float32).mean(-1)
    top = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (13, 1)))
    r = top * np.clip((110 - hsv[..., 1]) / 60, 0, 1)
    loc = cv2.blur(L, (41, 41)) + 20
    return r / loc * 100, L


def response_yellow(rgb):
    """Top-hat of the yellowness (min(R, G) - B) across the road, on saturated yellow hues."""
    f = rgb.astype(np.float32)
    yel = np.clip(np.minimum(f[..., 0], f[..., 1]) - f[..., 2], 0, None)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue_ok = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 38) & (hsv[..., 1] >= 70)
    top = cv2.morphologyEx(yel * hue_ok, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (13, 1)))
    loc = cv2.blur(f.mean(-1), (41, 41)) + 20
    return top / loc * 100


class Canopy:
    """Canopy height over the ground (swissSURFACE3D - swissALTI3D) at local points."""

    def __init__(self):
        self.dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
        self.dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))

    def __call__(self, X, Y):
        return self.dsm.sample(X, Y) - self.dtm.sample(X, Y)


def sample_strip(geom, canopy, block=400):
    """RGB (ns, nt, 3) uint8 of the strip and its hidden cells (canopy over it, no image, deep shade)."""
    import ortho10
    ss, x, y, nx, ny, half, tt = geom
    rgb = np.zeros((len(ss), len(tt), 3), np.uint8)
    hid = np.zeros((len(ss), len(tt)), bool)
    for a in range(0, len(ss), block):
        b = min(a + block, len(ss))
        PX = x[a:b, None] + nx[a:b, None] * tt[None, :]
        PY = y[a:b, None] + ny[a:b, None] * tt[None, :]
        c = ortho10.sample(PX.ravel(), PY.ravel()).reshape(b - a, len(tt), 3)
        miss = ~np.isfinite(c).all(-1)
        rgb[a:b] = np.clip(np.nan_to_num(c), 0, 255).astype(np.uint8)
        # the canopy on a coarser grid (0.5 m cells): every 5th row and 10th column, spread
        sub = canopy(PX[::5, ::10].ravel(), PY[::5, ::10].ravel()).reshape(PX[::5, ::10].shape)
        tall = np.repeat(np.repeat(np.nan_to_num(sub, nan=0.0) > NDSM_TREE, 5, 0), 10, 1)[:b - a, :len(tt)]
        hid[a:b] = tall | miss
    return rgb, hid


# ---------------------------------------------------------------------- longitudinal lines
def window_peaks(R, hid, tt, half_at, thr, L, S):
    """Peaks of the column profile in every window: [(window centre row, t, height, width m)].
    A peak is paint only with asphalt on both sides of it: darker than the line by SIDE_DL and
    not saturated (a kerb, a gravel verge, grass or the roof of a bus is not)."""
    ns = R.shape[0]
    nw, st = int(WIN / DS), int(STEP / DS)
    out = []
    for i0 in range(0, max(ns - nw // 2, 1), st):
        i1 = min(i0 + nw, ns)
        vis = ~hid[i0:i1]
        blk = np.where(vis, R[i0:i1], np.nan)
        ok = vis.mean(0) >= 0.4
        if not ok.any():
            continue
        q = np.nanpercentile(np.where(ok[None, :], blk, np.nan), 70, axis=0)
        top = blk >= q[None, :]
        prof = np.nan_to_num(np.nanmean(np.where(top, blk, np.nan), axis=0), nan=0.0)
        prof[~ok] = 0.0
        pk, pr = find_peaks(prof, height=thr, distance=int(0.45 / DT), prominence=0.6 * thr)
        if not len(pk):
            continue
        wd = peak_widths(prof, pk, rel_height=0.5)[0] * DT
        hmax = half_at((i0 + i1) // 2) + INSIDE        # paint lies on the carriageway, a guardrail beside it
        Lb, Sb = L[i0:i1], S[i0:i1]
        for p, hgt, wv in zip(pk, pr["peak_heights"], wd):
            if abs(tt[p]) > hmax or wv > 0.45:
                continue
            line_l = np.nanmean(np.where(top[:, p] & vis[:, p], Lb[:, p], np.nan))
            off = int(round((0.5 * wv + SIDE) / DT))
            sides = []
            for c in (p - off, p + off):
                if 0 <= c < len(tt):
                    m = vis[:, c]
                    sides.append((np.median(Lb[m, c]) if m.any() else np.nan, np.median(Sb[m, c]) if m.any() else np.nan))
            if len(sides) < 2 or not all(np.isfinite(a) and a <= line_l - SIDE_DL and b <= SIDE_SAT for a, b in sides):
                continue
            out.append(((i0 + i1) // 2, float(tt[p]), float(hgt), float(wv)))
    return out


def link_tracks(peaks):
    """Tracks of peaks linked window to window: lists of (row, t, height, width)."""
    by_row = {}
    for p in peaks:
        by_row.setdefault(p[0], []).append(p)
    rows = sorted(by_row)
    active, done = [], []
    for wi, r in enumerate(rows):
        cand = sorted(by_row[r], key=lambda p: -p[2])
        used = set()
        for tr in sorted(active, key=lambda tr: -len(tr["pts"])):
            best, bd = None, LINK
            for j, p in enumerate(cand):
                if j in used:
                    continue
                dd = abs(p[1] - tr["pts"][-1][1])
                if dd <= bd:
                    best, bd = j, dd
            if best is not None:
                used.add(best)
                tr["pts"].append(cand[best])
                tr["last"] = wi
        for j, p in enumerate(cand):
            if j not in used:
                active.append({"pts": [p], "last": wi})
        keep = []
        for tr in active:
            (keep if wi - tr["last"] <= MAX_MISS else done).append(tr)
        active = keep
    done += active
    return [tr["pts"] for tr in done if len(tr["pts"]) >= MIN_TRACK]


def merge_tracks(tracks):
    """Tracks of the same line joined: one that starts where another ended (within FILL m along the
    road, JOIN m across) continues it; two that run side by side closer than DUP m are one."""
    tracks = sorted([sorted(t) for t in tracks], key=lambda t: t[0][0])
    out = []
    for tr in tracks:
        for o in out:
            r0, r1 = o[0][0], o[-1][0]
            a0, a1 = tr[0][0], tr[-1][0]
            if a0 > r1 and (a0 - r1) * DS <= FILL and abs(tr[0][1] - o[-1][1]) <= JOIN:
                o.extend(tr)
                break
            if a0 <= r1 and a1 >= r0:                            # overlapping: the same line twice?
                ov = [p for p in tr if r0 <= p[0] <= r1]
                to = np.interp([p[0] for p in ov], [q[0] for q in o], [q[1] for q in o]) if ov else []
                if ov and np.median(np.abs(np.array([p[1] for p in ov]) - to)) <= DUP:
                    rows = {q[0] for q in o}
                    o.extend(p for p in tr if p[0] not in rows)
                    o.sort()
                    break
        else:
            out.append(list(tr))
    return out


def runs_of(on):
    """(start, end) row index pairs of the True runs of a boolean array."""
    e = np.flatnonzero(np.diff(np.r_[0, on.astype(np.int8), 0]))
    return list(zip(e[::2], e[1::2]))


def painted_runs(R, hid, rows_t, tt, thr_row):
    """Painted runs along a track (t per row): list of (a, b) in metres along the strip, and the
    rows hidden along it."""
    ns = R.shape[0]
    col = np.clip(np.round((rows_t - tt[0]) / DT).astype(int), 0, len(tt) - 1)
    val = np.max(np.stack([R[np.arange(ns), np.clip(col + dd, 0, len(tt) - 1)] for dd in (-2, -1, 0, 1, 2)]), 0)
    hidden = hid[np.arange(ns), col]
    on = (uniform_filter1d((val > thr_row).astype(float), 3) > 0.5) & ~hidden
    rr = [(a * DS, b * DS) for a, b in runs_of(on)]
    merged = []
    for a, b in rr:
        if merged and a - merged[-1][1] < MERGE:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if b - a >= 0.4], hidden


def regularise(runs, hidden_runs, length):
    """Painted intervals of a track from its measured runs (metres along the strip):
    - dashed stretches (three or more dashes DASH m long, steps whole multiples of one period in
      PERIOD, dashes of one length) are regularised to their measured dash length and period, a
      dash hidden by a car in between put back;
    - the other runs are pieces of solid lines: two pieces are one line across a gap shorter than
      SMALL_GAP, or across a gap mostly hidden (canopy, shade) up to FILL m when one of them is
      longer than SOLID; what is left shorter than MIN_SOLID is not paint;
    - a hidden stretch up to FILL m between two dashed stretches continues their rhythm.
    Returns (intervals, pattern: none / solid / dashed / mixed, hidden stretches left unpainted)."""
    if not runs:
        return [], "none", []
    hid = sorted(hidden_runs)

    def hidden_frac(a, b):
        if b <= a:
            return 1.0
        return sum(max(0.0, min(b, y) - max(a, x)) for x, y in hid) / (b - a)
    lens = np.array([b - a for a, b in runs])
    dash = (lens >= DASH[0]) & (lens <= DASH[1])
    groups, cur = [], []
    for k, (a, b) in enumerate(runs):
        if not dash[k] or (cur and not (GAP[0] <= a - runs[cur[-1]][1] <= 4 * GAP[1])):
            if len(cur) >= 3:
                groups.append(cur)
            cur = [k] if dash[k] else []
            continue
        cur.append(k)
    if len(cur) >= 3:
        groups.append(cur)
    dashes, periods, in_group = [], [], set()
    for g in groups:
        starts = np.array([runs[k][0] for k in g])
        dl = float(np.median(lens[g]))
        steps = np.diff(starts)
        base = float(np.median(steps[steps <= np.percentile(steps, 60) * 1.2]))
        mult = steps / base
        regular = (np.abs(mult - np.round(mult)) < 0.18).mean() >= 0.75 and (np.round(mult) <= 5).all()
        cv = float(np.std(lens[g]) / max(dl, 1e-6))
        if not (PERIOD[0] <= base <= PERIOD[1]) or not regular or cv > 0.4 or dl >= 0.8 * base:
            continue
        in_group.update(g)
        periods.append((float(starts[0]), float(starts[-1]) + dl, base, dl))
        for k in range(len(starts)):
            dashes.append((float(starts[k]), float(starts[k]) + dl))
            if k + 1 < len(starts):
                m = int(round((starts[k + 1] - starts[k]) / base))
                for q in range(1, m if 1 < m <= 5 else 1):
                    s0 = starts[k] + q * (starts[k + 1] - starts[k]) / m
                    dashes.append((float(s0), float(s0) + dl))
    # solid lines from the other runs
    pieces = [runs[k] for k in range(len(runs)) if k not in in_group]
    solid = []
    for a, b in pieces:
        if solid:
            pa, pb = solid[-1]
            g = a - pb
            longer = max(pb - pa, b - a) > SOLID
            if g < SMALL_GAP or (longer and g <= FILL and hidden_frac(pb, a) >= 0.5):
                solid[-1] = (pa, b)
                continue
        solid.append((a, b))
    solid = [(a, b) for a, b in solid if b - a >= MIN_SOLID]
    # hidden stretches between dashed stretches: the rhythm goes on
    left = []
    for a, b in hid:
        if b - a <= 5.0:
            continue
        before = [p for p in periods if p[1] <= a + 1.0]
        after = [p for p in periods if p[0] >= b - 1.0]
        covered = any(x <= a and y >= b for x, y in solid)
        if covered:
            continue
        if before and after and b - a <= FILL and after[0][0] - before[-1][1] <= FILL + 2 * before[-1][2]:
            _, end, base, dl = before[-1]
            s0 = end - dl + base
            while s0 + dl < after[0][0] - 0.5:
                dashes.append((s0, s0 + dl))
                s0 += base
        else:
            left.append((a, b))
    out = sorted(solid + dashes)
    merged = []
    for a, b in out:
        a, b = max(a, 0.0), min(b, length)
        if b - a < 0.3:
            continue
        if merged and a - merged[-1][1] < 0.2:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    pattern = {(False, False): "none", (True, False): "solid", (False, True): "dashed", (True, True): "mixed"}[
        (bool(solid), bool(dashes))]
    return merged, pattern, left


def paint_width(measured):
    """Width of a painted line from the width of its peak at half height (the 10 cm image blurs a
    line by about a pixel): the Swiss widths of 0.10-0.15 m (centre, lane and edge lines), 0.20 m and
    0.30 m (wide solid lines)."""
    for lim, w in ((0.30, 0.12), (0.38, 0.15), (0.45, 0.20)):
        if measured < lim:
            return w
    return 0.30


def segment_lines(k, net, canopy, debug=None):
    """The longitudinal lines of segment k: (lines, hidden stretches, stats)."""
    P, d, w = centre_line(net, k)
    if d[-1] < 6.0:
        return [], [], {"visible_m": 0.0, "hidden_m": 0.0}
    geom = strip_geometry(P, d, w)
    ss, x, y, nx, ny, half, tt = geom
    rgb, hid = sample_strip(geom, canopy)
    Rw, L = response_white(rgb)
    Ry = response_yellow(rgb)
    S = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1].astype(np.float32)
    hid |= cv2.blur(L, (21, 5)) < DARK
    half_at = lambda r: float(half[min(max(r, 0), len(half) - 1)])
    lines, hidden_all = [], []
    centre_hid = hid[:, len(tt) // 2]
    stats = {"visible_m": float((~centre_hid).sum() * DS), "hidden_m": float(centre_hid.sum() * DS)}
    for color, R, thr in (("white", Rw, PEAK_WHITE), ("yellow", Ry, PEAK_YELLOW)):
        peaks = window_peaks(R, hid, tt, half_at, thr, L, S)
        for tr in merge_tracks(link_tracks(peaks)):
            rows = np.array([p[0] for p in tr])
            tq = np.array([p[1] for p in tr])
            hq = np.array([p[2] for p in tr])
            wq = np.array([p[3] for p in tr])
            r_all = np.arange(len(ss))
            t_row = np.interp(r_all, rows, gaussian_filter1d(tq, 1.0) if len(tq) > 3 else tq)
            first, last = max(rows.min() - int(WIN / DS / 2), 0), min(rows.max() + int(WIN / DS / 2), len(ss))
            runs, hidden = painted_runs(R[first:last], hid[first:last], t_row[first:last], tt,
                                        max(ROW_FRAC * float(np.median(hq)), 0.6 * thr))
            runs = [(a + first * DS, b + first * DS) for a, b in runs]
            hid_runs = [(a * DS + first * DS, b * DS + first * DS) for a, b in runs_of(hidden)]
            painted, pattern, left = regularise(runs, hid_runs, ss[-1])
            if not painted or sum(b - a for a, b in painted) < 3.0:
                continue
            width = paint_width(float(np.median(wq)))
            segs_xy = []
            for a, b in painted:
                ia, ib = int(round(a / DS)), min(int(round(b / DS)), len(ss) - 1)
                idx = np.unique(np.r_[np.arange(ia, ib, 10), ib])
                segs_xy.append([[round(float(x[i] + nx[i] * t_row[i]), 3), round(float(y[i] + ny[i] * t_row[i]), 3)]
                                for i in idx])
            pts = [[round(float(x[i] + nx[i] * t_row[i]), 3), round(float(y[i] + ny[i] * t_row[i]), 3)]
                   for i in range(first, last, 20)]
            lines.append({"seg": int(k), "color": color, "width": width, "pattern": pattern, "_t_row": t_row.round(3),
                          "t_median": round(float(np.median(tq)), 2), "runs_s": [[round(a, 2), round(b, 2)] for a, b in painted],
                          "runs": segs_xy, "pts": pts})
            hidden_all += [{"seg": int(k), "from": round(a, 1), "to": round(b, 1), "len": round(b - a, 1)} for a, b in left]
    lines = plausible(lines)
    if debug is not None:
        debug_image(debug, rgb, hid, lines, ss, tt)
    for ln in lines:
        del ln["_t_row"]
    return lines, hidden_all, stats


def plausible(lines):
    """The lines of one road that stand as paint: a short solid piece (under ISOLATED m of paint) on a
    road where nothing else is painted is a light kerb, a gutter or the edge of a car park far more
    often than an edge line (random review of the tracks), and is dropped."""
    painted = lambda ln: sum(b - a for a, b in ln["runs_s"])
    other = lambda ln: [q for q in lines if q is not ln and painted(q) >= 3.0]
    return [ln for ln in lines if ln["pattern"] in ("dashed", "mixed") or painted(ln) >= ISOLATED or other(ln)]


def debug_image(path, rgb, hid, lines, ss, tt, row_m=100.0, max_rows=6):
    """The strip in rows of row_m m, hidden cells darkened, every painted run in red (white paint)
    or blue (yellow) beside the line it marks."""
    vis = rgb.copy()
    vis[hid] = (vis[hid] * 0.5).astype(np.uint8)
    for ln in lines:
        c = (255, 0, 0) if ln["color"] == "white" else (0, 0, 255)
        tr = np.array(ln["_t_row"])
        for a, b in ln["runs_s"]:
            for i in range(int(a / DS), min(int(b / DS), len(ss))):
                col = int(round((tr[i] - tt[0]) / DT))
                vis[i, max(col - 5, 0):max(col - 3, 0)] = c
    n = int(row_m / DS)
    rows = [vis[a:a + n] for a in range(0, min(len(ss), n * max_rows), n)]
    rows = [np.pad(r, ((0, n - len(r)), (0, 0), (0, 0))) for r in rows]
    ims = [np.rot90(r, 1) for r in rows]
    im = np.concatenate([np.pad(i, ((0, 6), (0, 0), (0, 0)), constant_values=255) for i in ims], 0)
    im = cv2.resize(im, (im.shape[1], im.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(path, cv2.cvtColor(im, cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------------- other paint
BLOCK = 64.0           # m, blocks of the orthophoto read for the other paint
SUNLIT = 70.0          # mean luminance around a blob: paint in the shade is not trusted
INSET = {"white": 0.6, "yellow": 0.3}   # m inside the surveyed carriageway (it and the image differ by ~0.3-0.5 m)
MIN_AREA = 0.12        # m2, smallest paint mark
STRIP_ASPECT = 2.5     # length : width of a strip of paint
STRIP_W = 0.7          # m, widest strip (crossing bars 0.5 m)
MARK_AREA = 0.6        # m2, arrows and letters
STRIP_FILL = 0.55      # share of its rectangle a straight strip of paint fills
MARKED = 12.0          # m around the traced lines (and the crossings, stops and give-ways of OSM) where white
                       # marks are trusted
# yellow paint, calibrated on the stripes of the marked crossings of OSM (OpenCV HSV: hue 25-31, saturation
# 52-100 as the paint fades, value 183-223 in the sun)
YELLOW_H = (18, 36)    # hue
YELLOW_S = 45          # saturation
YELLOW_V = 150         # value
YELLOW_B = 60          # R + G - 2 B: yellow over the grey of asphalt and concrete (0-20)
YELLOW_TOP = 15        # brighter than the road around it (top-hat of the luminance), unless saturated
LONG_YELLOW = 25.0     # m, longest yellow figure: the zigzags of the bus stops (thin: FILL_THIN of their rectangle)
FILL_THIN = 0.35
YELLOW_BG = 16         # R + G - 2 B of the ground 0.2-1 m around yellow paint: grey asphalt (<= 15 around the
                       # crossings of OSM), not the beige of gravel, dirt and dry grass
VEHICLE_W = 1.0        # m, a blob this wide may be a vehicle seen from above (white or yellow body):
VEHICLE_DARK = 55      # its box, 0.3 m wider, holds windows and its shadow, darker than the road (luminance)
VEHICLE_SHARE = 0.12   # share of the box that dark


def other_paint(block, carriage, lines_near, marked=None):
    """Paint blobs of one block (x0, y0) inside the carriageways, as polygons: yellow paint (Swiss
    crossings, bus stops, no-parking lines) and white paint (stop and give-way lines, arrows, text,
    hatched areas, dashes of lines that leave the direction of the road) away from the lines already
    traced (lines_near: their buffer). Vehicles (compact blobs) and blobs in the shade are left out.
    marked: where white paint is trusted, the surroundings of the lines traced on the roads and of the
    crossings, stops and give-ways OSM records (MARKED m): a lane with no line at all has no arrows
    either, and there a light streak is a stone or a gutter; yellow paint (the crossings) is kept
    everywhere."""
    import ortho10
    from rasterio import features
    from rasterio.transform import Affine
    x0, y0 = block
    n = int(round(BLOCK / RES_O))
    tr = Affine(RES_O, 0, x0, 0, -RES_O, y0 + BLOCK)
    ins = {c: features.rasterize([(carriage.buffer(-(INSET[c] - 0.25)), 1)], out_shape=(n, n), transform=tr, fill=0,
                                 dtype=np.uint8).astype(bool) if not carriage.buffer(-(INSET[c] - 0.25)).is_empty
           else np.zeros((n, n), bool) for c in INSET}
    inside = ins["yellow"]
    if inside.sum() < 50:
        return []
    xs = x0 + (np.arange(n) + 0.5) * RES_O
    ys = y0 + BLOCK - (np.arange(n) + 0.5) * RES_O
    GX, GY = np.meshgrid(xs, ys)
    rgb = ortho10.sample(GX.ravel(), GY.ravel()).reshape(n, n, 3)
    ok = np.isfinite(rgb).all(-1)
    img = np.clip(np.nan_to_num(rgb), 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    L = img.astype(np.float32).mean(-1)
    near = np.zeros((n, n), bool)
    if lines_near is not None and not lines_near.is_empty:
        near = features.rasterize([(lines_near, 1)], out_shape=(n, n), transform=tr, fill=0, dtype=np.uint8).astype(bool)
    sun = cv2.blur(L, (31, 31)) >= SUNLIT
    top = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    rgb16 = img.astype(np.int16)
    yellow = ((hsv[..., 0] >= YELLOW_H[0]) & (hsv[..., 0] <= YELLOW_H[1]) & (hsv[..., 1] > YELLOW_S) &
              (hsv[..., 2] > YELLOW_V) & (rgb16[..., 0] + rgb16[..., 1] - 2 * rgb16[..., 2] > YELLOW_B) &
              ((top > YELLOW_TOP) | (hsv[..., 1] > 90)) & inside & ok)
    white = (top > 28) & (hsv[..., 1] < 60) & (L > 150) & ins["white"] & ok & ~near & ~yellow
    out = []
    for color, m in (("yellow", yellow), ("white", white)):
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        nl, lab, stt, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for k in range(1, nl):
            area = stt[k][4] * RES_O ** 2
            ext = max(stt[k][2], stt[k][3]) * RES_O
            if color == "white" and not (0.1 <= area <= 6.0 and ext <= 6.0):
                continue
            if color == "yellow" and not (0.15 <= area <= 12.0 and ext <= LONG_YELLOW):
                continue
            comp = lab == k
            if not sun[comp].mean() > 0.5:
                continue
            if color == "yellow":                         # on asphalt: the ground around it is grey
                bx_, by_, bw_, bh_ = stt[k][:4]
                r0, r1, c0, c1 = max(by_ - 12, 0), min(by_ + bh_ + 12, n), max(bx_ - 12, 0), min(bx_ + bw_ + 12, n)
                sub = comp[r0:r1, c0:c1].astype(np.uint8)
                ring = (cv2.dilate(sub, np.ones((21, 21), np.uint8)) > 0) & ~(cv2.dilate(sub, np.ones((5, 5), np.uint8)) > 0)
                bg = rgb16[r0:r1, c0:c1][ring & ok[r0:r1, c0:c1] & ~yellow[r0:r1, c0:c1]]
                if len(bg) < 20 or np.median(bg[:, 0] + bg[:, 1] - 2 * bg[:, 2]) >= YELLOW_BG:
                    continue
            pts = np.column_stack(np.nonzero(comp)).astype(np.float32)
            rect = cv2.minAreaRect(pts)
            (_, _), (w_, h_), _ = rect
            long_, short = max(w_, h_) * RES_O, max(min(w_, h_), 1.0) * RES_O
            aspect = long_ / short
            fill = stt[k][4] * RES_O ** 2 / max(long_ * short, 1e-6)
            if short >= VEHICLE_W:                        # a vehicle: dark windows and shadow in its box
                (rc_, cc_), (w1, h1), a1 = rect
                box = cv2.boxPoints(((rc_, cc_), (w1 + 6, h1 + 6), a1))[:, ::-1]
                c0, r0 = np.floor(box.min(0)).astype(int) - 1
                c1, r1 = np.ceil(box.max(0)).astype(int) + 2
                c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, n), min(r1, n)
                bm = np.zeros((r1 - r0, c1 - c0), np.uint8)
                cv2.fillPoly(bm, [np.round(box - [c0, r0]).astype(np.int32)], 1)
                bm = bm.astype(bool) & ~comp[r0:r1, c0:c1] & ok[r0:r1, c0:c1]
                if bm.sum() and (L[r0:r1, c0:c1][bm] < VEHICLE_DARK).mean() > VEHICLE_SHARE:
                    continue
            if color == "yellow" and (ext > 7.0 or area > 8.0) and fill >= FILL_THIN:
                continue                                  # a yellow vehicle, not a thin figure of paint
            # the shapes of paint: strips (dashes, stop lines, crossing bars, hatching: long and thin)
            # or larger marks (arrows, letters); a small compact blob is a kerb corner, a manhole, a
            # reflection, a compact large one a vehicle seen from above
            strip = aspect >= STRIP_ASPECT and short <= STRIP_W and fill >= STRIP_FILL
            mark = area >= MARK_AREA and aspect >= 1.5 and fill < 0.8
            if area < MIN_AREA or not (strip or mark):
                continue
            cnts, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if len(c) < 3:
                    continue
                q = c[:, 0, :].astype(float)
                poly = shapely.Polygon(np.column_stack([x0 + (q[:, 0] + 0.5) * RES_O,
                                                        y0 + BLOCK - (q[:, 1] + 0.5) * RES_O])).buffer(0.02).simplify(0.03)
                if poly.is_empty or poly.area < 0.06:
                    continue
                if color == "white":
                    mrr = poly.minimum_rotated_rectangle
                    ex = np.asarray(mrr.exterior.coords)
                    e1, e2 = np.linalg.norm(ex[1] - ex[0]), np.linalg.norm(ex[2] - ex[1])
                    if max(e1, e2) > 12 and min(e1, e2) < 0.35:
                        continue
                if color == "white" and (marked is None or not marked.intersects(poly)):
                    continue
                for pg in getattr(poly, "geoms", [poly]):
                    if isinstance(pg, shapely.Polygon) and pg.area >= 0.06:
                        out.append({"color": color, "ring": np.asarray(pg.exterior.coords).round(3).tolist()})
    return out


# ---------------------------------------------------------------------- the whole network
def load_net():
    import network
    segs, st, _ = network.load()
    return {"segs": segs, "x": st["x"], "y": st["y"], "width": st["width"]}


def wanted(seg):
    """Roads a car drives on (bridge decks too), not paths."""
    return seg["kind"] == "road" and seg["class"] in MIN_CLASSES


def main(debug_ids=None, other_only=False):
    import roadheight
    net = load_net()
    canopy = Canopy()
    if debug_ids:
        d = os.path.join(WORK, "markings_debug")
        os.makedirs(d, exist_ok=True)
        for k in debug_ids:
            lines, hidden, st = segment_lines(k, net, canopy, debug=os.path.join(d, f"seg{k}.png"))
            print(k, net["segs"][k]["class"], net["segs"][k]["name"], st,
                  [(l["color"], l["pattern"], l["t_median"], l["width"], round(sum(b - a for a, b in l["runs_s"]), 1)) for l in lines])
        return
    # the Street View corridor keeps its own paint (markings_decals.py / the v1.1 carry-over)
    corridor = shapely.union_all([g for g, _, _ in roadheight.paved_polygons()]).buffer(1.0)
    shapely.prepare(corridor)
    todo = []
    for s in net["segs"]:
        if not wanted(s):
            continue
        a, n = s["first"], s["n"]
        inside = shapely.contains_xy(corridor, net["x"][a:a + n], net["y"][a:a + n]).mean()
        if inside > 0.5:
            continue
        todo.append(s["id"])
    print("network markings: %d lines of %.0f km" % (len(todo), sum(net["segs"][k]["length"] for k in todo) / 1000), flush=True)
    t0 = time.time()
    out = {"lines": [], "hidden": [], "segments": {}}
    if other_only:                                # the lines of the last run (checked again), the other paint again
        old = json.load(open(OUT))
        out.update({k: old[k] for k in ("hidden", "segments")})
        by_seg = {}
        for ln in old["lines"]:
            by_seg.setdefault(ln["seg"], []).append(ln)
        out["lines"] = [ln for k in sorted(by_seg) for ln in plausible(by_seg[k])]
        for k, lst in by_seg.items():
            if str(k) in out["segments"]:
                out["segments"][str(k)]["lines"] = len(plausible(lst))
        print("lines of the last run: %d, kept %d" % (len(old["lines"]), len(out["lines"])), flush=True)
        todo = []

    def one(k):
        try:
            return k, segment_lines(k, net, canopy)
        except Exception as e:
            print("segment", k, "failed:", e, flush=True)
            return k, ([], [], {"error": str(e)})
    with ThreadPoolExecutor(4) as ex:
        for n_done, (k, (lines, hidden, st)) in enumerate(ex.map(one, todo)):
            out["lines"] += lines
            out["hidden"] += hidden
            st["lines"] = len(lines)
            st["patterns"] = sorted({l["color"] + ":" + l["pattern"] for l in lines})
            out["segments"][str(k)] = st
            if n_done % 200 == 0:
                print("  %d/%d lines, %d paint tracks (%.0f s)" % (n_done + 1, len(todo), len(out["lines"]),
                                                                  time.time() - t0), flush=True)
    # the other paint, block by block over the surveyed carriageways
    import pickle
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    carr = [g.buffer(-0.25) for g, _ in av["LCSF"].get("strada_sentiero", [])]
    carr = [g for g in carr if not g.is_empty]
    ctree = shapely.STRtree(carr)
    lines_geom = [shapely.LineString(r).buffer(0.35, cap_style="flat") for l in out["lines"] for r in l["runs"] if len(r) >= 2]
    ltree = shapely.STRtree(lines_geom) if lines_geom else None
    # the crossings, stops and give-ways of OSM: white paint is trusted around them too
    osm_pts = []
    try:
        import osm
        if osm.available():
            osm_pts = [shapely.Point(nd["x"], nd["y"]) for nd in osm.load()[1]
                       if nd["tags"].get("highway") in ("crossing", "stop", "give_way")
                       and nd["tags"].get("crossing") != "unmarked" and nd["tags"].get("crossing:markings") != "no"]
    except Exception as e:
        print("OSM nodes not read:", e)
    otree = shapely.STRtree(osm_pts) if osm_pts else None
    blocks = set()
    for g in carr:
        bx0, by0, bx1, by1 = g.bounds
        for bx in range(int(np.floor(bx0 / BLOCK)), int(np.floor(bx1 / BLOCK)) + 1):
            for by in range(int(np.floor(by0 / BLOCK)), int(np.floor(by1 / BLOCK)) + 1):
                blocks.add((bx, by))

    def blk(b):
        box = shapely.box(b[0] * BLOCK, b[1] * BLOCK, (b[0] + 1) * BLOCK, (b[1] + 1) * BLOCK)
        ids = ctree.query(box, predicate="intersects")
        if not len(ids):
            return []
        c = shapely.union_all([carr[i] for i in ids]).intersection(box).difference(corridor)
        if c.is_empty or c.area < 2.0:
            return []
        ids_l = ltree.query(box.buffer(MARKED), predicate="intersects") if ltree else []
        near = shapely.union_all([lines_geom[i] for i in ids_l]) if len(ids_l) else None
        ids_o = otree.query(box.buffer(MARKED), predicate="intersects") if otree else []
        trust = [lines_geom[i].buffer(MARKED) for i in ids_l] + [osm_pts[i].buffer(MARKED) for i in ids_o]
        marked = shapely.union_all(trust) if trust else None
        try:
            return other_paint((b[0] * BLOCK, b[1] * BLOCK), c, near, marked)
        except Exception as e:
            print("block", b, "failed:", e, flush=True)
            return []
    out["polygons"] = []
    t1 = time.time()
    with ThreadPoolExecutor(4) as ex:
        for n_done, polys in enumerate(ex.map(blk, sorted(blocks))):
            out["polygons"] += polys
            if n_done % 500 == 0:
                print("  other paint: block %d/%d, %d polygons (%.0f s)" % (n_done + 1, len(blocks), len(out["polygons"]),
                                                                         time.time() - t1), flush=True)
    json.dump(out, open(OUT, "w"))
    # the compressed copy kept in the repository (dati/): a build without the orthophoto step uses it
    import gzip
    dati = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "network_markings.json.gz")
    with gzip.open(dati, "wt", compresslevel=9) as f:
        json.dump(out, f, separators=(",", ":"))
    painted = sum(b - a for l in out["lines"] for a, b in l["runs_s"])
    print("network markings: %d tracks, %.1f km of paint, %d other paint polygons (%.0f m2); hidden stretches left "
          "%d (%.1f km) (%.0f s)" % (len(out["lines"]), painted / 1000, len(out["polygons"]),
                                     sum(shapely.Polygon(p["ring"]).area for p in out["polygons"]), len(out["hidden"]),
                                     sum(h["len"] for h in out["hidden"]) / 1000, time.time() - t0))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:] if a.isdigit()] or None, other_only="--other-only" in sys.argv)
