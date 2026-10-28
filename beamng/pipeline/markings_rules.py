"""Road markings of the whole network laid by the Swiss rules, from the road geometry (v3.0).

Up to v2.8 the paint of the network was the orthophoto's trace (network_markings.py), cleaned
(markings_clean.py, v2.7) and laid as standard pieces along the road (markings_std.py, v2.8); the
cantonal road Magliaso - Pura kept the paint of the v1.1 release (carryover.py), traced in the same
photo. In the v3 test the traces showed through: white blobs at junctions, on a splitter island and
along edges, wavy broken centre dashes, crossings with zig-zag bars, fragments on the mountain roads
(the user's screenshots 03, 11, 13, 20, 21, 44). Both had the defects, so both are replaced.

Now no traced shape is laid. Every marking is drawn from the AI roads of the level (axis, width, lanes,
one-way) and its road meshes, by the Swiss rules of dati/swiss_markings.json (SSV Art. 72-79 and the
public cantonal directives for the VSS norms; summary with the sources: verifica/v3/markings/REGOLE.md):
1. axis: the nodes of every AI road without the spikes where it turns back, a smoothing spline through
   them (SIGMA m), stations every STEP m;
2. carriageway: both edges measured on the carriageway faces of the road meshes across every station
   (EDGE_STEP m), the openings (mouths of side roads, forecourts) found as jumps of the edge, the edge
   interpolated across them and smoothed: lines follow the asphalt without wobble, EDGE_INSET m inside it;
3. context of every station: OpenStreetMap (class, speed, 30 zone, lanes, one-way, lane_markings,
   roundabout, turn lanes), inside or outside a village (the Federal Register as lamps.py), the
   carriageway width, paved or not, the bends and the vertical profile;
4. junctions: the AI roads that meet; the road with priority by OSM (stop, give_way, traffic signals),
   roundabouts (the ring) and the classes (a minor road joining a main road gives way); the minor roads
   get the stop line with STOP and 6.12, or the give-way line with 6.12 (and 6.14 at roundabout entries
   of main roads), and their lines end there; the main road's edge line opens across the mouth, closed by
   a guide line beside the give-way line, its centre line 1/2 across the junctions of real roads; with the
   legal right of way every line ends at the other carriageway;
5. longitudinal lines: the centre line (3/6; 2/4 on winding stretches; a safety line with its 4/2 warning
   line on blind bends, hairpins and crests outside villages, where wide enough) on two-way roads wide
   enough for it, main roads always, minor roads only where the orthophoto trace confirms one; edge lines
   outside villages on main roads; nothing on narrow roads, in 30 zones, on one-way village lanes, on gravel
   and earth; on the ring of a roundabout only its inner edge line;
6. pedestrian crossings at the marked crossings of OSM: yellow bars square to the road across the whole
   carriageway (interrupted at an island), the lines stopping before them;
7. arrows only where OSM turn:lanes say so; painted splitter islands of roundabouts hatched where the
   mesh shows no physical island; 'ZONE 30' at the gates of the 30 zones;
8. the cantonal road Magliaso - Pura: the same rules, with its layout of 2022 measured in the photos
   (dati/cantonale_paint_2022.json, from the v1.1 paint): centre and edge lines only where it had them,
   nothing on the stretches without paint, its red bands laid again smooth along the road.
The orthophoto trace (dati/network_markings.json.gz) only confirms whether a minor road has a centre or
edge line. One mesh per TILE m tile without collision in MissionGroup/roads/markings (the names of the
v2.7 step, so a new run replaces them), the cantonal road's markings.dae goes. Re-runnable on a built level.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish markings
    python markings_rules.py --layout-2022 <root>   dati/cantonale_paint_2022.json from the v1.1 paint of a level
    python markings_rules.py <root> --bbox x0 y0 x1 y1 [--plot out.png] [--write]   a test on part of the map
"""
import gzip, json, math, os, re, shutil, sys, tempfile, time, zipfile
import numpy as np
import shapely
import shapely.affinity
from scipy.interpolate import splev, splprep
from scipy.ndimage import binary_dilation, median_filter
from scipy.signal import savgol_filter
from scipy.spatial import cKDTree
import bng
import optimize_level
import osm
from config import LEVEL_NAME
from markings_net import CARRIAGE_MATS, ROAD_MATS, NET_SHAPE, TILE, LIFT, read_items, shape_tris, up_faces
from road_mesh import TriSurface

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
RULES_FILE = os.path.join(DATI, "swiss_markings.json")
LAYOUT_2022 = os.path.join(DATI, "cantonale_paint_2022.json")
TRACE = os.path.join(DATI, "network_markings.json.gz")
LV = f"levels/{LEVEL_NAME}"
CANTONAL = "strada_cantonale"          # the AI road of the Street View route (ai_roads.py)
OLD_SHAPE = re.compile(r"art/shapes/roads/markings\.dae$")    # the cantonal road's v1.1 paint (carryover.py)

STEP = 0.5             # m between the stations of a road axis
SIGMA = 0.20           # m, RMS distance of the smoothing spline from the nodes of the AI road
MIN_ROAD = 8.0         # m, shorter AI roads get no paint
MIN_DRIVE = 0.3        # drivability: the roads closed to general traffic (0.1, ai_roads.BANNED) get none
EDGE_STEP = 2.0        # m between the measured cross sections
EDGE_REACH = 3.0       # m beyond the AI road's half width where the edge is looked for
EDGE_DT = 0.1          # m between the samples of a cross section
Z_TOL = 1.2            # m: a face this far from the road's height is another level (a bridge)
MOUTH_JUMP = 0.9       # m beyond the edge around it: an opening of the edge (a side road, a forecourt)
EDGE_MED = 5           # cross sections (EDGE_STEP m) of the median of the edge
EDGE_FIT = 11          # cross sections of the quadratic fit of the edge
EDGE_MIN_IN = 0.2      # m: no line closer than this to the measured edge of the asphalt
JOIN_R = 6.0           # m: road ends this close are one junction
ATTACH = 1.0           # m beyond the half width of a road where another road's end attaches to it
MOUTH_MARGIN = 3.0     # m beyond a side road's half width on the main road: the mouth
CUT_IN = 0.2           # m: a line is cut where it lies this far inside another road's carriageway
CUT_ANGLE = 25.0       # degrees: a road in line with another (its continuation) does not cut it
MIN_PIECE = 0.5        # m, shorter pieces of a line are left out
MIN_DASH = 0.6         # share of its length a dash keeps where it is cut, else it goes
RUN_MIN = 25.0         # m, shorter stretches of a centre or edge line are left out
GAP_FILL = 12.0        # m, shorter gaps between them are closed
WIND_WIN = 100.0       # m window of the heading change of a winding stretch
WIND_TURN = 70.0       # degrees of heading change in WIND_WIN: a winding stretch (2/4)
CONFIRM = 0.30         # share of the visible length a traced line must cover to confirm a minor road's line
CONFIRM_R = 0.6        # m from a traced point to the line it confirms
EYE = 1.0              # m, eye and object height of the crest sight test
VILLAGE_STEP = 2.0
RANK = {"motorway": 6, "motorway_link": 6, "trunk": 5, "trunk_link": 5, "primary": 5, "primary_link": 5,
        "secondary": 4, "secondary_link": 4, "tertiary": 3, "tertiary_link": 3, "unclassified": 2,
        "residential": 1, "road": 1, "living_street": 0, "service": 0, "track": -1}
MAIN_RANK = 3
UNPAVED = {"gravel", "fine_gravel", "dirt", "ground", "grass", "unpaved", "compacted", "pebblestone", "earth",
           "mud", "sand", "grass_paver", "wood"}
CROSS_TAGS = {"zebra", "marked", "uncontrolled", "traffic_signals"}
PAINT = {"white": "mp_road_paint", "yellow": "mp_road_paint_yellow", "red": "mp_road_paint_red"}


# ---------------------------------------------------------------------- the rules (dati/swiss_markings.json)
def cross2(a, b):
    """z of the cross product of 2D vectors (np.cross takes no 2D vectors from numpy 2.5)."""
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def load_rules(path=RULES_FILE):
    """The numbers of the dataset this module uses, by name."""
    R = json.load(open(path, encoding="utf-8"))
    m = R["markings"]
    p3 = m["6.03"]["pattern"]
    return {
        "w": _v(R["line_width"]["standard"]),
        "leit": tuple(_v(p3["normal"])), "wind": tuple(_v(p3["winding"])), "junction": tuple(_v(p3["junction"])),
        "opening": tuple(_v(p3["opening"])),
        "centre_w_in": m["6.03"]["min_carriageway_width"]["inside"],
        "centre_w_out": m["6.03"]["min_carriageway_width"]["exceptional"],
        "safe_w": _v(m["6.01"]["min_carriageway_width"]),
        "safe_len": m["6.01"]["min_length"]["outside"],
        "sight": m["6.01"]["rule_here"]["sight_min"], "blind_r": m["6.01"]["rule_here"]["blind_radius"],
        "hairpin_turn": m["6.01"]["rule_here"]["hairpin_turn"], "hairpin_len": m["6.01"]["rule_here"]["hairpin_length"],
        "warn": tuple(_v(m["6.05"]["pattern"])), "warn_len": m["6.05"]["length"]["outside"],
        "warn_gap": _v(m["6.05"]["gap_before_safety_line"]),
        "edge_off": m["6.15"]["offset_from_edge"]["used"], "edge_w": _v(m["6.15"]["min_carriageway_width"]),
        "edge_w_centre": _v(m["6.15"]["with_centre_line_min_width"]),
        "guide": tuple(_v(m["6.16"]["pattern"])),
        "stop_w": m["6.10"]["width"], "stop_clear": _v(m["6.10"]["kerb_clearance"]),
        "stop_text_h": _v(m["6.11"]["letter_height"]), "stop_text_d": _v(m["6.11"]["distance_from_stop_line"]),
        "long_len": _v(m["6.12"]["length"]), "long_w": _v(m["6.12"]["min_road_width"]),
        "lead_dash": _v(m["6.12"]["lead_in_dash"]),
        "tooth": (m["6.13"]["triangle"]["base"], m["6.13"]["triangle"]["height"], m["6.13"]["triangle"]["gap"]),
        "giveway_min_mouth": _v(m["6.13"]["min_mouth_width"]),
        "pre_len": _v(m["6.14"]["length"]), "pre_base": _v(m["6.14"]["base"]), "pre_w": _v(m["6.14"]["outline_width"]),
        "pre_d": _v(m["6.14"]["distance_from_give_way_line"]),
        "bar_w": _v(m["6.17"]["bar_width"]), "bar_gap": _v(m["6.17"]["bar_gap"]),
        "bar_main": m["6.17"]["bar_length"]["normal"], "bar_minor": m["6.17"]["bar_length"]["reduced"],
        "cross_clear": _v(m["6.17"]["lines_stop_before"]),
        "hatch_w": _v(m["6.20"]["bar_width"]), "hatch_gap": m["6.20"]["bar_gap"]["normal"],
        "hatch_angle": _v(m["6.20"]["bar_angle_to_axis"]), "hatch_outline": _v(m["6.20"]["outline_width"]),
        "hatch_clear": _v(m["6.20"]["outline_clearance"]),
        "arrow_len": _v(m["6.06"]["length"]), "arrow_d": _v(m["6.06"]["distance_stop_line_to_shaft"]),
        "arrow_step": _v(m["6.06"]["spacing"]),
        "zone_digit_h": _v(m["zone_30_text"]["digit_height"]), "zone_letter_h": _v(m["zone_30_text"]["letter_height"]),
        "zone_d": _v(m["zone_30_text"]["distance_from_gate"]),
        "village_n": R["context"]["village"]["n"], "village_r": R["context"]["village"]["radius"],
        "village_run": R["context"]["village"]["min_run"], "village_gap": R["context"]["village"]["close_gap"],
    }


R = load_rules()


# ---------------------------------------------------------------------- small helpers
def runs(mask):
    """[(a, b)] index ranges (b exclusive) where mask is true."""
    m = np.asarray(mask, bool)
    e = np.flatnonzero(np.diff(np.r_[0, m.astype(np.int8), 0]))
    return list(zip(e[::2], e[1::2]))


def clean_mask(mask, step, min_run, max_gap):
    """Gaps shorter than max_gap m closed, then runs shorter than min_run m dropped."""
    m = np.asarray(mask, bool).copy()
    for a, b in runs(~m):
        if a > 0 and b < len(m) and (b - a) * step < max_gap:
            m[a:b] = True
    for a, b in runs(m):
        if (b - a) * step < min_run:
            m[a:b] = False
    return m


def merge(iv, gap=0.0):
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def subtract(iv, cut):
    out = []
    for a, b in iv:
        pieces = [(a, b)]
        for c, d in cut:
            nxt = []
            for x, y in pieces:
                if d <= x or c >= y:
                    nxt.append((x, y))
                    continue
                if c > x:
                    nxt.append((x, c))
                if d < y:
                    nxt.append((d, y))
            pieces = nxt
        out += pieces
    return out


def dashes(a, b, dash, gap):
    """Dash intervals from a to b, the first dash at a; a last dash shorter than MIN_DASH of its length goes."""
    out, x = [], a
    while x < b - 1e-6:
        y = min(x + dash, b)
        if y - x >= MIN_DASH * dash or y - x >= dash - 1e-6:
            out.append((x, y))
        x += dash + gap
    return out


def unit(v):
    v = np.asarray(v, np.float64)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def rect(c, ax, length, width):
    """Corners of a rectangle centred at c, `length` along ax, `width` across."""
    ax = unit(ax)
    n = np.array([-ax[1], ax[0]])
    h, w = ax * length / 2, n * width / 2
    return np.array([c - h - w, c + h - w, c + h + w, c - h + w])


# ---------------------------------------------------------------------- 1. the road axis
def _chaikin(P, n=3):
    for _ in range(n):
        if len(P) < 3:
            return P
        Q = np.empty((2 * (len(P) - 1), P.shape[1]))
        Q[0::2] = 0.75 * P[:-1] + 0.25 * P[1:]
        Q[1::2] = 0.25 * P[:-1] + 0.75 * P[1:]
        P = np.vstack([P[:1], Q, P[-1:]])
    return P


def axis_of(nodes):
    """Stations every STEP m of the smoothed axis of an AI road: (X (n, 2), z (n,), w (n,), closed), or None."""
    N = np.asarray(nodes, np.float64)
    if len(N) < 2:
        return None
    keep = np.r_[True, np.hypot(*np.diff(N[:, :2], axis=0).T) > 0.05]
    N = N[keep]
    # spikes: nodes where the line turns back (keep_to_surface of the cantonal road, recentred nodes)
    for _ in range(50):
        if len(N) < 3:
            break
        d = np.diff(N[:, :2], axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        bad = np.flatnonzero((d[:-1] * d[1:]).sum(1) < -0.17) + 1
        if not len(bad):
            break
        drop = np.zeros(len(N), bool)
        drop[bad[np.r_[True, np.diff(bad) > 1]]] = True
        N = N[~drop]
    u = np.r_[0, np.cumsum(np.hypot(*np.diff(N[:, :2], axis=0).T))]
    L = float(u[-1])
    if L < MIN_ROAD:
        return None
    closed = L > 30 and np.hypot(*(N[0, :2] - N[-1, :2])) < 1.0
    ud = np.linspace(0, L, max(int(np.ceil(L)), 2) + 1)
    x, y = np.interp(ud, u, N[:, 0]), np.interp(ud, u, N[:, 1])
    P = None
    try:
        if len(ud) >= 6:
            tck, _ = splprep([x, y], u=ud, s=len(ud) * SIGMA ** 2, k=3, per=1 if closed else 0, quiet=2)
            uf = np.linspace(0, L, int(L / 0.25) + 2)
            P = np.column_stack(splev(uf, tck))
            ref = shapely.LineString(np.column_stack([x, y]))
            if shapely.hausdorff_distance(ref, shapely.LineString(P)) > 1.5:
                P = None
    except Exception:
        P = None
    if P is None:
        P = _chaikin(np.column_stack([x, y]))
    a = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    s = np.arange(0, a[-1] + 1e-9, STEP)
    X = np.column_stack([np.interp(s, a, P[:, 0]), np.interp(s, a, P[:, 1])])
    f = s / max(a[-1], 1e-9) * L
    return X, np.interp(f, u, N[:, 2]), np.interp(f, u, N[:, 3]), closed


class Road:
    """An AI road: its stations (X, T, N, s, z), AI width, and what the steps below find along it."""

    def __init__(self, k, obj, ax):
        self.k, self.name = k, obj.get("name", "")
        self.drive = float(obj.get("drivability", 1))
        self.oneway = bool(obj.get("oneWay"))
        self.X, self.z, self.w, self.closed = ax
        T = np.gradient(self.X, axis=0)
        self.T = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        self.N = np.column_stack([-self.T[:, 1], self.T[:, 0]])
        self.s = np.arange(len(self.X)) * STEP
        self.L = float(self.s[-1])
        n = len(self.X)
        self.eL, self.eR = self.w / 2, -self.w / 2                 # smoothed edges (left +)
        self.rawL, self.rawR = self.w / 2, -self.w / 2
        self.openL, self.openR = np.zeros(n, bool), np.zeros(n, bool)
        self.paved = np.ones(n, bool)
        self.block = np.zeros(n, bool)                             # no paint of this road here
        self.cut = []                                               # station intervals cut from every line
        self.jcut = []                                              # the part of them at junctions
        self.keep_out = []                                          # station intervals of give-way lines beside it
        self.centre_override = []                                   # [(s0, s1, pattern, ...)] 1/2, 6.12
        self.mouths = {}                                            # "arms": [(main arm, side arm)]

    @property
    def W(self):
        return self.eL - self.eR

    @property
    def c(self):
        return (self.eL + self.eR) / 2

    def idx(self, s):
        return np.clip(np.round(np.asarray(s) / STEP).astype(int), 0, len(self.X) - 1)

    def at(self, s, t=0.0):
        """Points at stations s (array) and offsets t (array or scalar) left of the axis."""
        s = np.clip(np.asarray(s, np.float64), 0, self.L)
        f = s / STEP
        i0 = np.clip(np.floor(f).astype(int), 0, len(self.X) - 2)
        w = (f - i0)[..., None]
        X = self.X[i0] * (1 - w) + self.X[i0 + 1] * w
        Nn = self.N[i0] * (1 - w) + self.N[i0 + 1] * w
        Nn /= np.maximum(np.linalg.norm(Nn, axis=-1, keepdims=True), 1e-9)
        return X + Nn * np.asarray(t, np.float64)[..., None]

    def interp(self, arr, s):
        return np.interp(s, self.s, arr)


def load_roads(objs, bbox=None):
    roads = []
    for k, o in enumerate(objs):
        if o.get("class", "DecalRoad") != "DecalRoad" or float(o.get("drivability", 1)) < MIN_DRIVE:
            continue
        nd = np.asarray(o.get("nodes", []), np.float64)
        if len(nd) < 2:
            continue
        if bbox is not None and not ((nd[:, 0] > bbox[0]) & (nd[:, 0] < bbox[2]) & (nd[:, 1] > bbox[1]) & (nd[:, 1] < bbox[3])).any():
            continue
        ax = axis_of(nd)
        if ax is not None:
            roads.append(Road(k, o, ax))
    return roads


# ---------------------------------------------------------------------- 2. the carriageway
def measure_edges(roads, carr, chunk=600000):
    """Both edges of the carriageway (faces of `carr`, TriSurface) across every EDGE_STEP m of every road:
    raw, the openings, and smoothed (interpolated across the openings, median and quadratic fit)."""
    k = int(round(EDGE_STEP / STEP))
    jobs = []
    for r in roads:
        ii = np.r_[np.arange(0, len(r.X), k), len(r.X) - 1] if (len(r.X) - 1) % k else np.arange(0, len(r.X), k)
        R = min(float(r.w.max()) / 2 + EDGE_REACH, 14.0)
        t = np.arange(-R, R + 1e-9, EDGE_DT)
        jobs.append((r, ii, t))
    res = {}
    buf, owners = [], []

    def flush():
        if not buf:
            return
        P = np.concatenate([b[0] for b in buf])
        Z = np.concatenate([b[1] for b in buf])
        h = carr.height(P[:, 0], P[:, 1], "near", Z)
        ok = np.isfinite(h) & (np.abs(h - Z) < Z_TOL)
        o = 0
        for (r, ii, t), n in owners:
            res[r.k] = ok[o:o + n].reshape(len(ii), len(t))
            o += n
        buf.clear()
        owners.clear()
    size = 0
    for r, ii, t in jobs:
        P = (r.X[ii][:, None, :] + r.N[ii][:, None, :] * t[None, :, None]).reshape(-1, 2)
        Z = np.repeat(r.z[ii] - 0.1, len(t))
        buf.append((P, Z))
        owners.append(((r, ii, t), len(P)))
        size += len(P)
        if size > chunk:
            flush()
            size = 0
    flush()
    for r, ii, t in jobs:
        ins = res[r.k]
        c0 = int(np.argmin(np.abs(t)))
        cols = np.arange(len(t))
        # the sample inside nearest to the axis, within 1 m
        cand = np.where(ins, np.abs(cols - c0)[None, :], 10 ** 6)
        a = np.argmin(cand, axis=1)
        found = cand[np.arange(len(ii)), a] <= int(1.0 / EDGE_DT)
        outR = np.where((cols[None, :] > a[:, None]) & ~ins, cols[None, :], len(t))
        right_end = outR.min(1)                                  # first outside sample to the left (+t)
        outL = np.where((cols[None, :] < a[:, None]) & ~ins, cols[None, :], -1)
        left_end = outL.max(1)
        eL = np.where(right_end < len(t), t[np.minimum(right_end, len(t) - 1)] - EDGE_DT / 2, np.nan)
        eR = np.where(left_end >= 0, t[np.maximum(left_end, 0)] + EDGE_DT / 2, np.nan)
        eL[~found], eR[~found] = np.nan, np.nan
        se = r.s[ii]
        r.paved = np.interp(r.s, se, found.astype(float)) > 0.5
        smooth = {}
        for side, e in ((1, eL), (-1, eR)):
            half = np.interp(se, r.s, r.w) / 2
            mag = side * e
            fill = np.where(np.isfinite(mag), mag, half)
            typ = median_filter(fill, size=min(31, len(fill) | 1), mode="nearest")
            opening = ~np.isfinite(mag) | (mag > typ + MOUTH_JUMP)
            good = ~opening
            if good.sum() >= 2:
                m = np.interp(np.arange(len(mag)), np.flatnonzero(good), mag[good])
            elif good.any():
                m = np.full(len(mag), mag[good][0])
            else:
                m = half.copy()
            m = median_filter(m, size=EDGE_MED, mode="nearest")
            wdw = min(EDGE_FIT, len(m) if len(m) % 2 else len(m) - 1)
            if wdw >= 5:
                m = savgol_filter(m, wdw, 2, mode="interp")
            raw = np.where(np.isfinite(mag), mag, m)
            smooth[side] = (np.interp(r.s, se, m), np.interp(r.s, se, raw),
                            np.interp(r.s, se, opening.astype(float)) > 0.5)
        r.eL, r.rawL, r.openL = smooth[1]
        r.eR, r.rawR, r.openR = -smooth[-1][0], -smooth[-1][1], smooth[-1][2]
        bad = r.eL - r.eR < 2.0                                   # no carriageway measured: the AI width
        r.eL = np.where(bad, r.w / 2, r.eL)
        r.eR = np.where(bad, -r.w / 2, r.eR)


# ---------------------------------------------------------------------- 3. the context
class Context:
    """OSM ways and nodes, the buildings of the Federal Register."""

    def __init__(self):
        ways, nodes = osm.load()
        self.ways = [w for w in ways if w["tags"].get("highway") in osm.DRIVE]
        self.nodes = nodes
        self.node_ways = {}
        for i, w in enumerate(self.ways):
            for nd in w["nodes"]:
                self.node_ways.setdefault(nd, []).append(i)
        gwr = json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz")))["buildings"]
        G = np.array([[b["x"], b["y"]] for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or 30) >= 30])
        self.gtree = cKDTree(G)
        rings = [w["line"] for w in self.ways if w["tags"].get("junction") in ("roundabout", "circular")]
        self.rings = shapely.union_all(rings) if rings else None


def _zone(tags):
    import signs_net
    return signs_net._zone(tags) is not None or tags.get("highway") == "living_street"


def road_context(roads, cx):
    """Per station: the OSM way (index or -1), class rank, 30 zone, OSM unpaved, lane_markings=no,
    lanes; inside a village; per road: main, ring (roundabout), class."""
    for r in roads:
        idx, sgn = osm.match_lines(r.X, cx.ways)
        n = len(idx)
        m = idx >= 0
        if m.any():
            pos = (np.arange(n) + 0.5) * r.L / n
            near = np.flatnonzero(m)
            pn = pos[near]
            k = np.clip(np.searchsorted(pn, r.s), 1, max(len(pn) - 1, 1))
            k = np.where(np.abs(pn[k - 1] - r.s) <= np.abs(pn[np.minimum(k, len(pn) - 1)] - r.s), k - 1,
                         np.minimum(k, len(pn) - 1))
            j = near[k]
            way = idx[j]
            wsgn = sgn[j]
        else:
            way = np.full(len(r.X), -1)
            wsgn = np.zeros(len(r.X), int)
        r.way, r.wsgn = way, wsgn
        tags = [cx.ways[i]["tags"] if i >= 0 else {} for i in way]
        default = 3 if r.drive >= 1.0 else (1 if r.drive >= 0.8 else 0)
        r.rank = np.array([RANK.get(t.get("highway"), default) if t else default for t in tags])
        r.zone = np.array([_zone(t) if t else False for t in tags])
        r.osm_unpaved = np.array([t.get("surface") in UNPAVED or t.get("highway") == "track" if t else False for t in tags])
        r.lm_no = np.array([t.get("lane_markings") == "no" if t else False for t in tags])
        r.lanes = np.array([int(t["lanes"]) if t.get("lanes", "").isdigit() else 0 for t in tags])
        ring = np.array([t.get("junction") in ("roundabout", "circular") if t else False for t in tags])
        # per station too: an AI road can go on through the ring (the cantonal road over the Magliaso roundabout)
        if cx.rings is not None:
            ring |= shapely.dwithin(cx.rings, shapely.points(r.X), 3.0)
        r.ring_st = ring
        r.ring = bool(ring.mean() > 0.5) if m.any() else False
        r.main = bool(np.median(r.rank) >= MAIN_RANK)
        hw = [t.get("highway") for t in tags if t]
        r.cls = max(set(hw), key=hw.count) if hw else None
        # inside a village: the Federal Register (lamps.py), runs cleaned
        q = np.arange(0, len(r.X), int(VILLAGE_STEP / STEP))
        v = cx.gtree.query_ball_point(r.X[q], R["village_r"], return_length=True) >= R["village_n"]
        v = clean_mask(v, VILLAGE_STEP, R["village_run"], R["village_gap"])
        r.village = np.interp(r.s, r.s[q], v.astype(float)) > 0.5


# ---------------------------------------------------------------------- 4. junctions
class Arm:
    def __init__(self, road, s, d, end):
        self.r, self.s, self.d, self.end = road, float(s), d, end       # d: +1 away from the junction along s
        i = road.idx(s)
        far = road.idx(s + d * 10.0)
        self.dir = unit(road.X[far] - road.X[i]) if far != i else unit(road.T[i] * d)
        near = road.idx(np.clip(s + d * np.arange(0, 25, 2.0), 0, road.L))
        self.rank = int(np.median(road.rank[near]))
        self.ring = bool(road.ring_st[road.idx(np.clip(s + d * np.arange(0, 8, 2.0), 0, road.L))].mean() > 0.5)
        if road.oneway:
            self.enter, self.leave = d < 0, d > 0                   # the nodes run in the direction of travel
        else:
            self.enter = self.leave = True
        self.control = None
        self.stop_s = None


def junctions(roads):
    """Junctions of the AI roads: [{"c": centre, "arms": [Arm], "main": [Arm]}]."""
    X = np.concatenate([r.X for r in roads])
    rid = np.concatenate([np.full(len(r.X), i) for i, r in enumerate(roads)])
    sid = np.concatenate([np.arange(len(r.X)) for r in roads])
    Z = np.concatenate([r.z for r in roads])
    kd = cKDTree(X)
    ends = []
    for i, r in enumerate(roads):
        if r.closed:
            continue
        ends += [(i, 0), (i, 1)]
    touches = []                               # (end key, road j, station index, is_end_of_j)
    for i, e in ends:
        r = roads[i]
        p, z = (r.X[0], r.z[0]) if e == 0 else (r.X[-1], r.z[-1])
        cand = kd.query_ball_point(p, 14.0)
        best = {}
        for q in cand:
            j = rid[q]
            if j == i or abs(Z[q] - z) > 3.0:
                continue
            d = float(np.hypot(*(X[q] - p)))
            if j not in best or d < best[j][0]:
                best[j] = (d, sid[q])
        for j, (d, st) in best.items():
            o = roads[j]
            half = max(float(o.eL[st] - o.eR[st]) / 2, 1.5)
            if d > half + ATTACH:
                continue
            s_j = st * STEP
            at_end = 0 if s_j < 3.0 else (1 if o.L - s_j < 3.0 else None)
            if o.closed:
                at_end = None
            touches.append(((i, e), j, s_j, at_end, p))
    # union-find over the road ends and the attachments
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)
    pts = {}
    for (i, e) in ends:
        r = roads[i]
        pts[("e", i, e)] = r.X[0] if e == 0 else r.X[-1]
        find(("e", i, e))
    for key, j, s_j, at_end, p in touches:
        a = ("e",) + key
        if at_end is not None:
            union(a, ("e", j, at_end))
        else:
            b = ("i", j, int(s_j // 10))                     # attachments to the inside of road j, by 10 m
            pts[b] = roads[j].X[roads[j].idx(s_j)]
            union(a, b)
    # attachments of one road within JOIN_R are one junction, ends close to each other too
    keys = list(pts)
    P = np.array([pts[k] for k in keys])
    for a, b in cKDTree(P).query_pairs(JOIN_R):
        ka, kb = keys[a], keys[b]
        if ka[0] == "i" and kb[0] == "i" and ka[1] != kb[1]:
            continue
        if ka[0] == "e" and kb[0] == "e" and ka[1] == kb[1]:
            continue                                      # the two ends of a short road
        union(ka, kb)
    groups = {}
    for k in keys:
        groups.setdefault(find(k), []).append(k)
    att = {}
    for key, j, s_j, at_end, p in touches:
        if at_end is None:
            att.setdefault(find(("e",) + key), {}).setdefault(j, []).append(s_j)
    out = []
    for g, members in groups.items():
        arms = []
        for k in members:
            if k[0] == "e":
                i, e = k[1], k[2]
                r = roads[i]
                arms.append(Arm(r, 0.0 if e == 0 else r.L, 1 if e == 0 else -1, True))
        for j, ss in att.get(g, {}).items():
            r = roads[j]
            s = float(np.mean(ss))
            if s > 1.0:
                arms.append(Arm(r, s, -1, False))
            if r.L - s > 1.0:
                arms.append(Arm(r, s, 1, False))
        if len(arms) < 2:
            continue
        c = np.mean([a.r.at(a.s) for a in arms], 0)
        out.append({"c": c, "arms": arms})
    return out


def decide(junc, cx, stats):
    """The main road of every junction and the control of the other arms (stop, give_way, signals,
    right_of_way, driveway, exit)."""
    ctl_nodes = [(np.array([n["x"], n["y"]]), n["tags"].get("highway")) for n in cx.nodes
                 if n["tags"].get("highway") in ("stop", "give_way", "traffic_signals")]
    ckd = cKDTree(np.array([p for p, _ in ctl_nodes])) if ctl_nodes else None
    # the roundabouts of OSM: centre and radius of every ring; at a junction on a ring the arms along the ring
    # (tangential) are the ring, those across it (radial) the entries and exits (the AI roads of a roundabout are
    # short pieces that do not always follow the mapped ring)
    rings = [(c, rad) for c, rad, _ in ring_list(cx)]
    for J in junc:
        arms = J["arms"]
        if any(np.hypot(*(J["c"] - c)) < rad + RING_ZONE for c, rad in rings):
            # on a roundabout: its entries get their give-way lines from the mapped ring (roundabout_entries)
            for a in arms:
                a.control = "ring"
            J["main"] = list(arms)
            stats["arms_ring"] = stats.get("arms_ring", 0) + len(arms)
            continue
        ring = [a for a in arms if a.ring]
        main = []
        if len(arms) == 2:
            main = list(arms)                             # one road going on in two pieces
        elif ring:
            main = ring
        else:
            best = None
            for a in range(len(arms)):
                for b in range(a + 1, len(arms)):
                    A, B = arms[a], arms[b]
                    if A.r is B.r and not A.end and not B.end:
                        score = (min(A.rank, B.rank), 2)
                    elif float(A.dir @ B.dir) < -0.8:
                        score = (min(A.rank, B.rank), 1 if A.r.cls == B.r.cls else 0)
                    else:
                        continue
                    if best is None or score > best[0]:
                        best = (score, [A, B])
            if best is not None:
                main = best[1]
        J["main"] = main
        main_rank = min((a.rank for a in main), default=-9)
        others = [a for a in arms if a not in main]
        # mapped controls: the OSM node on the arm within 30 m of the junction
        if ckd is not None:
            for k in ckd.query_ball_point(J["c"], 30.0):
                p, kind = ctl_nodes[k]
                bestd = None
                for a in arms:
                    s = np.clip(a.s + a.d * np.arange(0, 30, 1.0), 0, a.r.L)
                    Q = a.r.at(s)
                    d = np.hypot(*(Q - p).T)
                    m = int(np.argmin(d))
                    half = float(a.r.eL[a.r.idx(s[m])] - a.r.eR[a.r.idx(s[m])]) / 2
                    if d[m] < half + 2.5 and (bestd is None or d[m] < bestd[0]):
                        bestd = (d[m], a)
                if bestd is not None:
                    a = bestd[1]
                    if a in main and kind != "traffic_signals":
                        continue
                    a.control = {"stop": "stop", "give_way": "give_way", "traffic_signals": "signals"}[kind]
                    a.mapped = True
        for a in others:
            if a.control is not None:
                continue
            if not a.enter:
                a.control = "exit"
            elif ring:
                a.control = "give_way"
            elif main and main_rank >= MAIN_RANK and a.rank < main_rank and a.rank >= 1:
                a.control = "give_way"                     # a minor road joining a main road
            elif main and a.rank <= 0:
                a.control = "driveway"
            else:
                a.control = "right_of_way"
        if not main:
            for a in arms:
                if a.control is None:
                    a.control = "right_of_way"
        # v3.2: traffic lights (OSM highway=traffic_signals on an arm) control every way in of the junction
        J["signalled"] = len(arms) >= 3 and any(a.control == "signals" for a in arms)
        if J["signalled"]:
            for a in arms:
                if a.enter:
                    a.control = "signals"
        for a in arms:
            if a.control:
                stats["arms_" + a.control] = stats.get("arms_" + a.control, 0) + 1


def stop_station(arm, others, extra=0.0):
    """Station of `arm` where it leaves the carriageways of `others` (their measured edges), walking away
    from the junction: the junction side of its stop or give-way line."""
    r = arm.r
    s = np.clip(arm.s + arm.d * np.arange(0, 40, 0.25), 0, r.L)
    P = r.at(s, r.interp(r.c, s))
    inside = np.zeros(len(s), bool)
    for o in others:
        q = o.r
        kd = getattr(q, "_kd", None)
        if kd is None:
            kd = q._kd = cKDTree(q.X)
        d, j = kd.query(P)
        t = ((P - q.X[j]) * q.N[j]).sum(1)
        along = np.abs(((P - q.X[j]) * q.T[j]).sum(1))
        inside |= (t < q.eL[j] + extra) & (t > q.eR[j] - extra) & (along < 1.0)
    if not inside.any():
        return arm.s
    last = np.flatnonzero(inside)
    k = last[-1] + 1 if last[-1] + 1 < len(s) else last[-1]
    # the first station after the last one inside (a long arm inside the other road: its end)
    return float(s[k])


# ---------------------------------------------------------------------- the paint being built
class Paint:
    """Lines (polylines with a width) and polygons, with their colour and kind, for the meshes and the report."""

    def __init__(self):
        self.lines = []        # (P (m, 2), z_hint (m,), width, colour, kind, road index)
        self.polys = []        # (ring (m, 2), z_hint, colour, kind)
        self.count = {}
        self.signals = []      # (position (3,), direction of travel (2,), "stop" / "give_way"): signals.json
        self.lights = []       # (stop point (3,), travel (2,), junction key, pole (3,), kerb side (2,)): traffic lights

    def line(self, P, zh, width, colour, kind, road=-1):
        if len(P) >= 2:
            self.lines.append((np.asarray(P, np.float64), np.asarray(zh, np.float64), width, colour, kind, road))

    def poly(self, ring, zh, colour, kind):
        self.polys.append((np.asarray(ring, np.float64), float(zh), colour, kind))

    def add(self, kind, n=1):
        self.count[kind] = self.count.get(kind, 0) + n


def transverse(junc, roads, paint, stats):
    """Stop and give-way lines, 6.12, STOP, 6.14, and the cuts and mouths they make."""
    align = R["edge_off"] - R["w"] / 2           # the line's junction side in line with the outer side of an edge line
    for J in junc:
        arms, main = J["arms"], J["main"]
        for ji, a in enumerate(arms):
            lit = J.get("signalled") and a.control == "signals"
            if a in main and not lit:
                continue
            r = a.r
            others = [b for b in (main if main and a not in main else arms) if b.r is not r]
            s0 = stop_station(a, others, -align if main else 0.0) if others else a.s
            a.stop_s = s0
            ctl = a.control
            depth = 0.0
            i0 = r.idx(s0)
            W = float(r.W[i0])
            paved = bool(r.paved[i0]) and not bool(r.osm_unpaved[i0])
            line_ok = paved and ctl in ("stop", "give_way", "signals") and r.L > 6.0
            if line_ok and W < R["giveway_min_mouth"] and ctl == "give_way":
                line_ok = False
                stats["giveway_narrow"] = stats.get("giveway_narrow", 0) + 1
            if line_ok:
                depth = draw_stop_line(a, s0, others if main else [], paint)
                a.line = depth > 0
            if ctl in ("stop", "give_way") and r.drive >= 0.3:
                signal_point(a, s0, ctl, paint)
            if lit:
                light_point(a, s0, tuple(np.round(np.asarray(J["c"], float)[:2], 2)), paint)
            r.cut.append(tuple(sorted((a.s, s0 + a.d * (depth + 0.3)))))
            r.jcut.append(tuple(sorted((a.s, s0 + a.d * (depth + 0.3)))))
            if line_ok and depth > 0 and not r.oneway and W >= R["long_w"]:
                # 6.12: the solid line on the middle of the side road, from the line back
                sa = s0 + a.d * depth
                sb = sa + a.d * R["long_len"]
                r.centre_override.append((min(sa, sb), max(sa, sb), "long", a))
            if line_ok and depth > 0 and ctl == "give_way" and any(m.ring for m in main) and a.rank >= MAIN_RANK:
                pre_announce(a, s0 + a.d * (depth + R["pre_d"]), paint)
            for m in main:
                m.r.mouths.setdefault("arms", []).append((m, a))


def signal_point(a, s0, kind, paint):
    """The point where the traffic stops or gives way on arm a (signals.json): the middle of its approach
    lane at the junction side of its line (station s0), the direction of travel towards the junction."""
    r = a.r
    i0 = r.idx(s0)
    c = float(r.c[i0])
    if r.oneway:
        t = (float(r.eL[i0]) + float(r.eR[i0])) / 2
    elif a.d > 0:
        t = (c + float(r.eL[i0])) / 2
    else:
        t = (float(r.eR[i0]) + c) / 2
    p = r.at(s0 + a.d * 0.5, t)
    paint.signals.append((np.array([p[0], p[1], float(r.z[i0])]), -unit(r.T[i0] * a.d), kind))


def light_point(a, s0, key, paint):
    """A traffic light of arm a (v3.2): its stop point (as signal_point) and the pole of its head, on the kerb side
    of the approach LIGHT_OUT m past the carriageway's edge, LIGHT_BACK m before the stop line."""
    r = a.r
    i0 = r.idx(s0)
    c = float(r.c[i0])
    if r.oneway:
        t = (float(r.eL[i0]) + float(r.eR[i0])) / 2
    elif a.d > 0:
        t = (c + float(r.eL[i0])) / 2
    else:
        t = (float(r.eR[i0]) + c) / 2
    p = r.at(s0 + a.d * 0.5, t)
    travel = -unit(r.T[i0] * a.d)
    sp = s0 + a.d * LIGHT_BACK
    ip = r.idx(sp)
    # the kerb side: right of the travel towards the junction (travel -d along s: +t when d > 0)
    if a.d > 0:
        tk, side = float(r.eL[ip]) + LIGHT_OUT, r.N[ip].copy()
    else:
        tk, side = float(r.eR[ip]) - LIGHT_OUT, -r.N[ip].copy()
    q = r.at(sp, tk)
    paint.lights.append((np.array([p[0], p[1], float(r.z[i0])]), travel, key,
                         np.array([q[0], q[1], float(r.z[ip])]), unit(side)))


def draw_stop_line(a, s0, others, paint):
    """The give-way or stop line of arm a at station s0 (its junction side), across the approach lane,
    straight along the edge of the main road (`others`: its arms); returns its depth along the arm."""
    r = a.r
    i0 = r.idx(s0)
    c = float(r.c[i0])
    clear = R["stop_clear"]
    # the approach lane: right of the travel towards the junction (travel -a.d along s)
    if r.oneway:
        lo, hi = float(r.eR[i0]) + clear, float(r.eL[i0]) - clear
    elif a.d > 0:                       # travel towards s = 0: its right side is the left of the axis (+t)
        lo, hi = c + R["w"] / 2, float(r.eL[i0]) - clear
    else:
        lo, hi = float(r.eR[i0]) + clear, c - R["w"] / 2
    if hi - lo < 0.8:
        return 0.0
    away = unit(r.T[i0] * a.d)                           # from the junction into the arm
    across = r.N[i0].copy()
    ref = None
    p0 = r.at(s0, (lo + hi) / 2)
    for o in others:
        q = o.r
        kd = getattr(q, "_kd", None)
        if kd is None:
            kd = q._kd = cKDTree(q.X)
        d, j = kd.query(p0)
        if ref is None or d < ref[0]:
            ref = (d, q, int(j))
    if ref is not None:
        tm = unit(ref[1].T[ref[2]])
        if float(tm @ across) < 0:
            tm = -tm
        if float(tm @ across) > 0.6:                      # within 53 degrees of square: along the main road
            across = tm
    cosa = max(float(abs(across @ r.N[i0])), 0.6)
    m = r.at(s0, (lo + hi) / 2)
    h = (hi - lo) / 2 / cosa
    A2, B2 = m - across * h, m + across * h
    nrm = np.array([-across[1], across[0]])
    if float(nrm @ away) < 0:
        nrm = -nrm
    k_dep = max(float(nrm @ away), 0.5)
    zh = float(r.z[i0]) - 0.1
    if ref is not None:                                   # the main road's guide line leaves this out
        q = ref[1]
        js = q._kd.query(np.array([A2, B2]))[1]
        q.keep_out.append((float(q.s[js].min()) - 0.3, float(q.s[js].max()) + 0.3))
    L = 2 * h
    if a.control in ("stop", "signals"):
        w = R["stop_w"]
        paint.poly(np.array([A2, B2, B2 + nrm * w, A2 + nrm * w]), zh, "white", "stop_line")
        paint.add("stop_line" if a.control == "stop" else "signal_stop_line")
        if a.control == "stop":
            stop_text(a, s0 + a.d * (w / k_dep + R["stop_text_d"]), (lo + hi) / 2, min(hi - lo - 0.2, 2.6), paint)
        return w / k_dep
    base, height, gap = R["tooth"]
    n = int((L + gap) // (base + gap))
    if n < 1:
        return 0.0
    first = (L - (n * base + (n - 1) * gap)) / 2
    u = unit(B2 - A2)
    for k in range(n):
        p = A2 + u * (first + k * (base + gap))
        paint.poly(np.array([p, p + u * base, p + u * base / 2 + nrm * height]), zh, "white", "give_way")
    paint.add("give_way_line")
    return height / k_dep


def pre_announce(a, s_near, paint):
    """6.14: an outlined triangle in the approach lane before the give-way line, its tip towards the driver."""
    r = a.r
    i = r.idx(s_near)
    c = float(r.c[i])
    t = c + (r.W[i] / 4 if a.d > 0 else -r.W[i] / 4) if not r.oneway else c
    if r.L < s_near + R["pre_len"] + 2 if a.d > 0 else s_near - R["pre_len"] < 2:
        return
    fwd = unit(-r.T[i] * a.d)                            # towards the junction
    base_c = r.at(s_near, t)
    side = np.array([-fwd[1], fwd[0]])
    tip = base_c - fwd * R["pre_len"]
    tri = shapely.Polygon([base_c + side * R["pre_base"] / 2, base_c - side * R["pre_base"] / 2, tip])
    ring = tri.difference(tri.buffer(-R["pre_w"], join_style="mitre"))
    paint.polys.append((ring, float(r.z[i]) - 0.1, "white", "pre_give_way"))
    paint.add("give_way_announcement")


# a stroke font for the road texts: polylines in a unit box (x across from left to right, y away from the reader)
GLYPH_PX = 160          # px of a glyph drawn from the font
GLYPH_TOL = 0.006       # of GLYPH_PX: the tolerance of its traced outline
GLYPH_CUT = 0.02        # of a glyph's width: the slit that opens a hole (an O, a 0) into a simple ring
GLYPHS = {
    "S": [[(1, .85), (.8, 1), (.2, 1), (0, .85), (0, .62), (.2, .5), (.8, .5), (1, .38), (1, .15), (.8, 0), (.2, 0), (0, .15)]],
    "T": [[(0, 1), (1, 1)], [(.5, 1), (.5, 0)]],
    "O": [[(.25, 0), (.75, 0), (1, .15), (1, .85), (.75, 1), (.25, 1), (0, .85), (0, .15), (.25, 0)]],
    "P": [[(0, 0), (0, 1), (.75, 1), (1, .85), (1, .62), (.75, .48), (0, .48)]],
    "Z": [[(0, 1), (1, 1), (0, 0), (1, 0)]],
    "N": [[(0, 0), (0, 1), (1, 0), (1, 1)]],
    "E": [[(1, 1), (0, 1), (0, 0), (1, 0)], [(0, .5), (.75, .5)]],
    "3": [[(0, .85), (.2, 1), (.8, 1), (1, .85), (1, .62), (.8, .5), (.35, .5)], [(.8, .5), (1, .38), (1, .15), (.8, 0), (.2, 0), (0, .15)]],
    "0": [[(.25, 0), (.75, 0), (1, .15), (1, .85), (.75, 1), (.25, 1), (0, .85), (0, .15), (.25, 0)]],
}


def glyph_shape(ch, px=GLYPH_PX):
    """Outline of a character in a unit box (x across 0..1, y along the road 0..1, the foot at 0) as a shapely
    geometry, from a bold sans font drawn and traced (v3.0 review: the letters were strokes of a polyline font, thin
    and angular next to the painted ones); holes cut open so every piece is a simple polygon (the paint takes
    rings). None without a font."""
    import cv2
    from PIL import Image, ImageDraw
    from signs_ch import _font
    f = _font(px)
    im = Image.new("L", (px * 2, px * 2), 0)
    ImageDraw.Draw(im).text((px // 2, px // 4), ch, font=f, fill=255)
    a = np.asarray(im)
    ys, xs = np.nonzero(a > 127)
    if not len(xs):
        return None
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = a.shape
    cs, hier = cv2.findContours((a > 127).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hier is None:
        return None
    polys = []
    for i, c in enumerate(cs):
        if hier[0][i][3] != -1:
            continue
        def norm(c):
            c = cv2.approxPolyDP(c, GLYPH_TOL * px, True).reshape(-1, 2).astype(float)
            return np.column_stack([(c[:, 0] + 0.5) / w, 1.0 - (c[:, 1] + 0.5) / h])
        holes = [norm(cs[j]) for j in range(len(cs)) if hier[0][j][3] == i and len(cs[j]) >= 3]
        outer = norm(c)
        if len(outer) < 3:
            continue
        g = shapely.Polygon(outer, [hh for hh in holes if len(hh) >= 3]).buffer(0)
        for hh in holes:                                      # a hole: cut the glyph open through it
            cx = float(np.mean(hh[:, 0]))
            g = g.difference(shapely.box(cx - GLYPH_CUT / 2, -1, cx + GLYPH_CUT / 2, 0.5 * (1 + np.mean(hh[:, 1]))))
        polys += [p for p in getattr(g, "geoms", [g]) if isinstance(p, shapely.Polygon) and p.area > 1e-4]
    return shapely.MultiPolygon(polys) if polys else None


def text_polys(text, origin, fwd, height, width, stroke=0.16, gap=0.2):
    """Polygons of `text` on the road: letters `height` m along `fwd` (away from the reader), the row
    `width` m across, centred on `origin` (the middle of the row's near side). v3.0 review: the glyphs of a bold
    font (glyph_shape), stretched along the road as painted letters are; the stroke font where none."""
    right = np.array([fwd[1], -fwd[0]])
    n = len(text)
    lw = (width - gap * (n - 1)) / n
    out = []
    for k, ch in enumerate(text):
        x0 = -width / 2 + k * (lw + gap)
        g = glyph_shape(ch)
        if g is not None:
            for p in g.geoms:
                Q = np.asarray(p.exterior.coords)[:-1]
                P = origin + right[None] * (x0 + Q[:, :1] * lw) + fwd[None] * (Q[:, 1:2] * height)
                out.append(shapely.Polygon(P))
            continue
        segs = []
        for pl in GLYPHS.get(ch, []):
            P = np.array([origin + right * (x0 + x * (lw - stroke) + stroke / 2) + fwd * (y * (height - stroke) + stroke / 2)
                          for x, y in pl])
            segs.append(shapely.LineString(P).buffer(stroke / 2, cap_style="square", join_style="mitre", mitre_limit=3))
        g = shapely.union_all(segs)
        out += [p for p in getattr(g, "geoms", [g]) if isinstance(p, shapely.Polygon)]
    return out


def stop_text(a, s_near, t_mid, width, paint):
    r = a.r
    h = R["stop_text_h"]
    fwd = unit(-r.T[r.idx(s_near)] * a.d)                     # towards the junction
    origin = r.at(s_near + a.d * h, t_mid)                   # the reader's side of the row
    zh = float(r.z[r.idx(s_near)]) - 0.1
    for p in text_polys("STOP", origin, fwd, h, max(width, 1.6)):
        paint.poly(np.asarray(p.exterior.coords)[:-1], zh, "white", "text")
    paint.add("stop_text")


# ---------------------------------------------------------------------- 5. longitudinal lines
def trace_index(cx_roads):
    """KD-trees of the traced paint: the orthophoto lines of the network (white) and the 2022 paint of the
    cantonal road (white points), and the visible length per swissTLM3D segment."""
    out = {"net": None, "seg_visible": {}, "c22": None, "c22_unmarked": None, "c22_red": []}
    if os.path.exists(TRACE):
        d = json.load(gzip.open(TRACE, "rt"))
        P = []
        for l in d["lines"]:
            if l["color"] != "white":
                continue
            for run in l["runs"]:
                Q = np.asarray(run, np.float64)
                if len(Q) >= 2:
                    u = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
                    s = np.arange(0, u[-1] + 1e-9, 0.5)
                    P.append(np.column_stack([np.interp(s, u, Q[:, 0]), np.interp(s, u, Q[:, 1])]))
        if P:
            out["net"] = cKDTree(np.concatenate(P))
        out["seg_visible"] = {int(k): v.get("visible_m", 0.0) / max(v.get("visible_m", 0.0) + v.get("hidden_m", 0.0), 1e-6)
                              for k, v in d.get("segments", {}).items()}
    if os.path.exists(LAYOUT_2022):
        L = json.load(open(LAYOUT_2022))
        out["c22"] = cKDTree(np.asarray(L["white"], np.float64))
        un = [np.asarray(p, np.float64) for p in L.get("unmarked", []) if len(p) >= 2]
        out["c22_unmarked"] = cKDTree(np.concatenate(un)) if un else None
        out["c22_red"] = [shapely.Polygon(rg) for rg in L.get("red_bands", []) if len(rg) >= 4]
        out["c22_route"] = cKDTree(np.asarray(L["route"], np.float64))
    return out


def covered(tree, P, gap=6.0):
    """(n,) bool: a traced point within CONFIRM_R m of every point of P (stations STEP m apart), the gaps
    of a dashed line (up to `gap` m) bridged."""
    if tree is None:
        return np.zeros(len(P), bool)
    hit = np.isfinite(tree.query(P, distance_upper_bound=CONFIRM_R)[0])
    k = int(gap / STEP)
    return binary_dilation(hit, np.ones(2 * k + 1, bool)) if hit.any() else hit


def is_cantonal(r, tr):
    return r.name == CANTONAL and tr.get("c22") is not None


def sight_blocked(r):
    """(n,) bool, outside villages: the stations where the sight along the centre line is short —
    hairpins, sharp bends, crests."""
    n = len(r.X)
    th = np.unwrap(np.arctan2(r.T[:, 1], r.T[:, 0]))
    k = int(R["hairpin_len"] / 2 / STEP)
    a, b = np.clip(np.arange(n) - k, 0, n - 1), np.clip(np.arange(n) + k, 0, n - 1)
    turn = np.degrees(np.abs(th[b] - th[a]))
    hair = turn >= R["hairpin_turn"]
    # sharp bends: curvature over 1/blind_r along a turn of 40 degrees or more
    kk = int(10 / STEP)
    a2, b2 = np.clip(np.arange(n) - kk, 0, n - 1), np.clip(np.arange(n) + kk, 0, n - 1)
    curv = np.abs(th[b2] - th[a2]) / np.maximum((b2 - a2) * STEP, 1e-6)
    sharp = curv > 1.0 / R["blind_r"]
    for p, q in runs(sharp):
        if np.degrees(abs(th[min(q, n - 1)] - th[p])) < 40.0:
            sharp[p:q] = False
    # crests: a 1 m object hidden from a 1 m eye within the sight distance, either way
    crest = np.zeros(n, bool)
    S = R["sight"]
    m = int(S / STEP)
    z = r.z
    if n > m:
        for i in range(0, n - m, 4):
            seg = z[i:i + m + 1]
            line = np.linspace(seg[0] + EYE, seg[-1] + EYE, len(seg))
            if (seg[1:-1] > line[1:-1]).any():
                crest[i:i + m + 1] |= seg > np.max(seg) - 0.5
    return hair | sharp | crest


def centre_line(r, tr, stats):
    """Centre line of road r: [(s0, s1, pattern)] with pattern 'leit', 'wind', 'safe', 'warn', 'junction', 'long', 'dash1'."""
    n = len(r.X)
    W = r.W
    vil = r.village
    cant = is_cantonal(r, tr)
    two_way = not r.oneway and not r.ring
    base = r.paved & ~r.osm_unpaved & ~r.zone & ~r.lm_no & (r.lanes != 1) & ~r.block
    wmin = np.where(vil, R["centre_w_in"], R["centre_w_out"])
    P = r.at(r.s, r.c)
    if cant:
        real = covered(tr["c22"], P)
        ok = base & real & (W >= 5.0) & ~r.unmarked
        why = "cantonal_2022"
    elif r.main:
        ok = base & (W >= wmin)
        why = "main"
    else:
        vis = tr["seg_visible"].get(int(r.name[4:]), 0.0) if r.name.startswith("tlm_") else 0.0
        hit = covered(tr["net"], P)
        conf = hit.mean() / max(vis, 0.3) if vis > 0 else 0.0
        ok = base & (W >= wmin) & (conf >= CONFIRM)
        why = "minor_confirmed" if conf >= CONFIRM else "minor"
    if not two_way:
        ok[:] = False
    ok = clean_mask(ok, STEP, RUN_MIN, GAP_FILL)
    stats["centre_" + why] = stats.get("centre_" + why, 0) + int(ok.any())
    pat = np.full(n, "", object)
    pat[ok] = "leit"
    if ok.any():
        th = np.unwrap(np.arctan2(r.T[:, 1], r.T[:, 0]))
        k = int(WIND_WIN / 2 / STEP)
        cs = np.r_[0, np.cumsum(np.abs(np.diff(th)))]
        a, b = np.clip(np.arange(n) - k, 0, n - 1), np.clip(np.arange(n) + k, 0, n - 1)
        wind = np.degrees(cs[b] - cs[a]) > WIND_TURN
        wind = clean_mask(wind, STEP, 60.0, 30.0)
        pat[ok & wind & ~vil] = "wind"
        safe = sight_blocked(r) & ok & ~vil & (W >= R["safe_w"])
        safe = clean_mask(safe, STEP, 1.0, 2 * R["warn_len"] + 20.0)
        for p, q in runs(safe):                          # at least the minimum length, centred
            need = int(R["safe_len"] / STEP) - (q - p)
            if need > 0:
                p, q = max(p - need // 2, 0), min(q + need - need // 2, n)
            sl = slice(p, q)
            pat[sl] = np.where(ok[sl], "safe", pat[sl])
            g, wl = int(R["warn_gap"] / STEP), int(R["warn_len"] / STEP)
            for lo, hi in ((max(p - g - wl, 0), max(p - g, 0)), (min(q + g, n), min(q + g + wl, n))):
                seg = slice(lo, hi)
                pat[seg] = np.where(ok[seg] & (pat[seg] != "safe"), "warn", pat[seg])
            for gs in (slice(max(p - g, 0), p), slice(q, min(q + g, n))):     # the gap before the safety line
                pat[gs] = np.where(pat[gs] != "safe", "", pat[gs])
    out = []
    for p, q in runs(pat != ""):
        k0 = p
        for k in range(p + 1, q + 1):
            if k == q or pat[k] != pat[k0]:
                out.append((r.s[k0], r.s[min(k, n - 1)], pat[k0]))
                k0 = k
    return out


def lay_centre(r, segs, paint, stats):
    """Dashes of the centre line, with the overrides (1/2 across junctions, 6.12 at stop and give-way lines)."""
    pieces = []
    PAT = {"leit": R["leit"], "wind": R["wind"], "warn": R["warn"], "junction": R["junction"], "dash1": R["lead_dash"]}
    over = [(a, b) for a, b, k, *_ in r.centre_override]
    for a, b, kind in segs:
        for x, y in subtract([(a, b)], over):
            if kind == "safe":
                pieces.append((x, y, "safe"))
            else:
                d, g = PAT[kind]
                pieces += [(p, q, kind) for p, q in dashes(x, y, d, g)]
    for a, b, kind, *rest in r.centre_override:
        if kind == "long":
            pieces.append((a, b, "long"))
            arm = rest[0]
            has = any(x <= (a + b) / 2 <= y for x, y, _ in segs)
            if not has:                                   # no centre line: a 1 m dash 1 m before it (BS)
                if arm.d > 0:
                    pieces.append((b + 1.0, b + 2.0, "long"))
                else:
                    pieces.append((a - 2.0, a - 1.0, "long"))
        elif kind == "junction":
            if any(x <= (a + b) / 2 <= y for x, y, _ in segs):
                d, g = R["junction"]
                pieces += [(p, q, "junction") for p, q in dashes(a, b, d, g)]
    lay_pieces(r, pieces, lambda s: r.interp(r.c, s), paint, stats, "centre")


def lay_pieces(r, pieces, offset, paint, stats, family, width=None, colour="white"):
    """Lines of road r at stations [(s0, s1, kind)] and the offset function, minus the cuts of the road."""
    cut = merge(r.cut)
    for a, b, kind in pieces:
        a, b = max(a, 0.0), min(b, r.L)
        if b - a < MIN_PIECE:
            continue
        for x, y in subtract([(a, b)], cut):
            if y - x < max(MIN_PIECE, MIN_DASH * (b - a) if b - a < 7 else MIN_PIECE):
                continue
            s = np.r_[np.arange(x, y, STEP), y]
            if len(s) < 2:
                continue
            P = r.at(s, offset(s))
            zh = r.interp(r.z, s) - 0.1
            ok = r.interp(r.block.astype(float), s) < 0.5
            for p, q in runs(ok):
                if (q - p) >= 2 and s[q - 1] - s[p] >= MIN_PIECE:
                    paint.line(P[p:q], zh[p:q], width or R["w"], colour, kind, r.i)
                    stats[kind + "_m"] = stats.get(kind + "_m", 0.0) + float(s[q - 1] - s[p])


def edge_lines(r, tr, centre, stats):
    """Edge lines of road r: {side: mask (n,)} where they are painted; centre: (n,) where it has a centre line."""
    out = {}
    W = r.W
    vil = r.village
    cant = is_cantonal(r, tr)
    wmin = np.where(centre, R["edge_w_centre"], R["edge_w"])
    base = r.paved & ~r.osm_unpaved & ~r.zone & ~r.block & (W >= wmin)
    for side in (1, -1):
        e = r.eL if side > 0 else r.eR
        P = r.at(r.s, e - side * R["edge_off"])
        if r.ring:
            ok = (r.paved & ~r.block) if side == r.island_side else np.zeros(len(r.X), bool)
        elif cant:
            ok = base & covered(tr["c22"], P) & ~r.unmarked & ~r.red_side.get(side, np.zeros(len(r.X), bool))
        elif r.main:
            ok = base & ~vil
        else:
            vis = tr["seg_visible"].get(int(r.name[4:]), 0.0) if r.name.startswith("tlm_") else 0.0
            hit = covered(tr["net"], P)
            conf = hit.mean() / max(vis, 0.3) if vis > 0 else 0.0
            ok = base & ~vil & (conf >= 0.5)
        out[side] = clean_mask(ok, STEP, RUN_MIN, GAP_FILL)
    return out


def lay_edges(r, masks, paint, stats):
    """The edge lines, open across the mouths: a guide line (50/50) where a side road gives way or a side area
    (forecourt, driveway) opens, nothing at a junction with the legal right of way. Where the road has no edge
    line, guide lines only across the mouths of the side roads that give way (6.16.1) and the exits of a
    roundabout's ring; never beside a give-way or stop line (keep_out)."""
    arms = r.mouths.get("arms", [])
    keep_out = merge(r.keep_out)
    for side in (1, -1):
        ok = masks[side]
        opening = (r.openL if side > 0 else r.openR) & r.paved
        e = r.eL if side > 0 else r.eR
        raw = r.rawL if side > 0 else r.rawR
        # the paint never closer than EDGE_MIN_IN to the measured edge
        off = e - side * R["edge_off"]
        lim = raw - side * EDGE_MIN_IN
        off = np.where(side * off > side * lim, lim, off)
        off = np.convolve(np.pad(off, 3, mode="edge"), np.ones(7) / 7, "valid")
        # no edge line where its offset swings (round a splitter island or a lay-by the measured edge leaves the
        # road's): a line there zigzagged across the lane
        if len(off) > 2:
            slope = np.abs(np.gradient(off, r.s))
            swing = np.convolve(slope > EDGE_SWING, np.ones(5), "same") > 0
            ok = ok & ~swing
        f = lambda s, off=off: r.interp(off, s)
        solid, guide = [], []
        for p, q in runs(ok):
            cur = p
            for a, b in runs(opening[p:q]):
                a, b = a + p, b + p
                if a > cur:
                    solid.append((r.s[cur], r.s[a - 1], "edge"))
                if mouth_kind(r, side, r.s[a], r.s[b - 1], arms, True) == "guide":
                    guide.append((r.s[a], r.s[b - 1]))
                cur = b
            if cur < q:
                solid.append((r.s[cur], r.s[q - 1], "edge"))
        # mouths outside the edge lines: side roads that give way, exits of the ring
        for a, b in runs(opening & ~ok):
            if mouth_kind(r, side, r.s[a], r.s[min(b, len(r.s) - 1)], arms, False) == "guide":
                guide.append((r.s[a], r.s[min(b, len(r.s) - 1)]))
        lay_pieces(r, solid, f, paint, stats, "edge")
        g = []
        d, gp = R["guide"]
        for a, b in guide:
            for x, y in subtract([(a, b)], keep_out):
                g += [(p, q, "guide") for p, q in dashes(x, y, d, gp)]
        lay_pieces(r, g, f, paint, stats, "guide")


def mouth_kind(r, side, a, b, arms, has_edge):
    """'guide' or 'gap' for the opening (a, b) on `side` of road r, from the arms of the junctions there: a guide
    line beside a side road that gives way or stops, at an exit of a ring, across a driveway or a side area
    (where the road has an edge line); nothing at a junction with the legal right of way."""
    for m, arm in arms:
        if m.r is not r or abs(m.s - (a + b) / 2) > (b - a) / 2 + 8.0:
            continue
        sd = np.sign(float(arm.dir @ r.N[r.idx(m.s)]))
        if sd != side:
            continue
        if arm.control == "right_of_way":
            return "gap"
        if arm.control in ("give_way", "stop", "signals"):
            return "guide" if getattr(arm, "line", False) or has_edge else "gap"
        if arm.control == "exit":
            return "guide" if r.ring or has_edge else "gap"
        return "guide" if has_edge else "gap"
    return "guide" if has_edge and b - a < 40.0 else "gap"


# ---------------------------------------------------------------------- 6. crossings
def crossings(roads, cx, tr, paint, stats):
    ok = lambda t: (t.get("highway") == "crossing" and t.get("crossing") not in ("unmarked", "no")
                    and t.get("crossing:markings") not in ("no", "dashes", "lines", "dots", "surface")
                    and (t.get("crossing") in CROSS_TAGS or t.get("crossing_ref") == "zebra"
                         or t.get("crossing:markings") in ("zebra", "yes")))
    X = np.concatenate([r.X for r in roads])
    rid = np.concatenate([np.full(len(r.X), i) for i, r in enumerate(roads)])
    sid = np.concatenate([np.arange(len(r.X)) for r in roads])
    kd = cKDTree(X)
    done = []
    for nd in cx.nodes:
        if not ok(nd["tags"]):
            continue
        p = np.array([nd["x"], nd["y"]])
        ws = set(cx.node_ways.get(nd["id"], []))
        best = None
        for q in kd.query_ball_point(p, 9.0):
            r = roads[rid[q]]
            i = sid[q]
            t = float((p - r.X[i]) @ r.N[i])
            if not r.eR[i] - 1.0 <= t <= r.eL[i] + 1.0:
                continue
            d = float(np.hypot(*(p - r.X[i])))
            score = d - (5.0 if r.way[i] in ws else 0.0)
            if best is None or score < best[0]:
                best = (score, r, i)
        if best is None:
            stats["crossings_off_road"] = stats.get("crossings_off_road", 0) + 1
            continue
        _, r, i = best
        if r.ring or not r.paved[i] or r.osm_unpaved[i] or (is_cantonal(r, tr) and r.unmarked[i]):
            stats["crossings_skipped"] = stats.get("crossings_skipped", 0) + 1
            continue
        s = float(r.s[i] + (p - r.X[i]) @ r.T[i])
        if any(rr is r and abs(ss - s) < 6.0 for rr, ss in done):
            continue
        done.append((r, s))
        lay_crossing(r, s, nd["tags"], paint, stats)


def lay_crossing(r, s, tags, paint, stats):
    L = R["bar_main"] if r.main else R["bar_minor"]
    # clear of the junction area of the road (its stop or give-way line): moved back, at most 8 m
    half = L / 2 + R["cross_clear"]
    for a, b in merge(r.jcut):
        if s + half > a and s - half < b:
            s2 = b + half + 0.5 if s > (a + b) / 2 else a - half - 0.5
            if abs(s2 - s) > 8.0 or not half <= s2 <= r.L - half:
                stats["crossings_in_junction"] = stats.get("crossings_in_junction", 0) + 1
                return
            stats["crossings_moved"] = stats.get("crossings_moved", 0) + 1
            s = s2
    i = r.idx(s)
    lo, hi = float(r.eR[i]), float(r.eL[i])
    # islands: the carriageway along the crossing line, sampled finely
    t = np.arange(lo, hi, 0.05)
    P = r.at(np.full(len(t), s), t)
    h = CARR.height(P[:, 0], P[:, 1], "near", np.full(len(t), r.z[i] - 0.1))
    on = np.isfinite(h)
    parts = []
    for a, b in runs(on):
        parts.append([t[a], t[b - 1]])
    parts = merge([tuple(p) for p in parts], 0.6)
    parts = [(a, b) for a, b in parts if b - a >= 1.5] or [(lo, hi)]
    T = r.T[i]
    zh = float(r.z[i]) - 0.1
    nb = 0
    for a, b in parts:
        a, b = max(a, lo), min(b, hi)
        span = b - a
        p = R["bar_w"] + R["bar_gap"]
        n = int((span - 2 * 0.2 + R["bar_gap"]) // p)
        if n < 1:
            continue
        first = (a + b) / 2 - (n - 1) * p / 2
        for k in range(n):
            c = r.at(s, first + k * p)
            paint.poly(rect(c, T, L, R["bar_w"]), zh, "yellow", "crossing")
            nb += 1
    if nb:
        r.cut.append((s - L / 2 - R["cross_clear"], s + L / 2 + R["cross_clear"]))
        paint.add("crossing")
        paint.add("crossing_bars", nb)


# ---------------------------------------------------------------------- 7. arrows, islands, texts
def arrows(roads, cx, paint, stats):
    """Lane arrows (6.06) where OSM maps turn:lanes, in the middle of each lane before the junction."""
    import markings_std
    A = {k: shapely.Polygon(v) for k, v in markings_std.templates()["arrows"].items()}
    names = {frozenset(["through"]): "straight", frozenset(["left"]): "left", frozenset(["right"]): "right",
             frozenset(["through", "left"]): "straight_left", frozenset(["through", "right"]): "straight_right",
             frozenset(["left", "right"]): "left_right", frozenset(["slight_left"]): "left",
             frozenset(["slight_right"]): "right", frozenset(["through", "slight_right"]): "straight_right",
             frozenset(["through", "slight_left"]): "straight_left"}
    for wi, w in enumerate(cx.ways):
        t = w["tags"]
        for key, dirn in (("turn:lanes", 1), ("turn:lanes:forward", 1), ("turn:lanes:backward", -1)):
            if key not in t:
                continue
            lanes = [frozenset(x.split(";")) for x in t[key].split("|")]
            if osm.oneway_dir(t) == -1:
                dirn = -dirn
            for r in roads:
                m = r.way == wi
                if m.sum() < 10:
                    continue
                ii = np.flatnonzero(m)
                travel = int(np.sign(np.median(r.wsgn[ii]))) * dirn       # +1: along s
                if travel == 0:
                    continue
                s_end = r.s[ii[-1]] if travel > 0 else r.s[ii[0]]
                s_beg = r.s[ii[0]] if travel > 0 else r.s[ii[-1]]
                two = not (r.oneway or osm.oneway_dir(t) != 0)
                for k, lane in enumerate(lanes):
                    name = names.get(lane)
                    if name is None:
                        continue
                    for j, back in enumerate((R["arrow_d"], R["arrow_d"] + R["arrow_step"])):
                        s_tail = s_end - travel * back
                        if travel * (s_tail - s_beg) < 0:
                            continue
                        i = r.idx(s_tail)
                        W = float(r.W[i])
                        n = len(lanes)
                        if two:
                            lw = W / 2 / n
                            tl = r.c[i] - travel * (k + 0.5) * lw
                        else:
                            lw = W / n
                            tl = r.c[i] + travel * (W / 2 - (k + 0.5) * lw)
                        if lw < 2.5:
                            break
                        g = shapely.affinity.scale(A[name], R["arrow_len"] / 5.0, R["arrow_len"] / 5.0, origin=(0, 0))
                        fwd = unit(r.T[i] * travel)
                        lft = np.array([-fwd[1], fwd[0]])
                        base = r.at(s_tail, tl)
                        Q = np.asarray(g.exterior.coords)[:-1]
                        ring = base + Q[:, :1] * fwd + Q[:, 1:2] * lft
                        paint.poly(ring, float(r.z[i]) - 0.1, "white", "arrow")
                        paint.add("arrow")


def zone_texts(roads, junc, paint, stats):
    """'30' and 'ZONE' (special marking) in the lane entering a 30 zone, ZONE_D m inside it."""
    gates = []
    for r in roads:
        z = r.zone & r.paved
        if not z.any() or r.rank.max() > 2:
            continue
        for a, b in runs(z):
            if a > 0:
                gates.append((r, r.s[a], 1))
            if b < len(r.X):
                gates.append((r, r.s[b - 1], -1))
    # roads starting in the zone at a junction with a road outside it
    for J in junc:
        zs = [a for a in J["arms"] if a.r.zone[a.r.idx(a.s)]]
        if zs and len(zs) < len(J["arms"]) and any(a.rank >= 1 for a in J["arms"] if a not in zs):
            for a in zs:
                if a.enter or a.leave:
                    gates.append((a.r, a.s, a.d))
    seen = []
    for r, s, d in gates:
        if r.oneway and d < 0:
            continue
        s1 = s + d * R["zone_d"]
        if not 0 < s1 < r.L or any(rr is r and abs(ss - s1) < 20 for rr, ss in seen):
            continue
        i = r.idx(s1)
        if r.block[i] or any(x <= s1 <= y for x, y in r.cut) or not r.paved[i]:
            continue
        seen.append((r, s1))
        W = float(r.W[i])
        fwd = unit(r.T[i] * d)
        if r.oneway or W < 4.5:
            t, lane = float(r.c[i]), min(W - 0.6, 2.6)
        else:
            t, lane = float(r.c[i]) - d * W / 4, min(W / 2 - 0.4, 2.6)
        if lane < 1.6:
            continue
        zh = float(r.z[i]) - 0.1
        o = r.at(s1, t)
        polys = text_polys("30", o, fwd, R["zone_digit_h"], min(lane, 2.0), stroke=0.2, gap=0.3)
        polys += text_polys("ZONE", o + fwd * (R["zone_digit_h"] + 0.8), fwd, R["zone_letter_h"], lane, stroke=0.16)
        for p in polys:
            paint.poly(np.asarray(p.exterior.coords)[:-1], zh, "white", "text")
        paint.add("zone30_text")


def islands(roads, junc, paint, stats):
    """Painted splitter islands (6.20) of the roundabout arms drawn as two one-way roads: the area between
    the entry and the exit, outside their lanes and the ring, hatched where the road mesh is asphalt there
    (no physical island)."""
    ring_roads = [r for r in roads if r.ring]
    if not ring_roads:
        return
    ring_band = shapely.union_all([shapely.LineString(r.X).buffer(float(np.median(r.W)) / 2) for r in ring_roads])
    for J in junc:
        ones = [a for a in J["arms"] if a.r.oneway and not a.r.ring and a.end]
        for A in ones:
            for B in ones:
                if A is B or not (A.leave and B.enter):
                    continue
                # A leaves the fork towards the ring (the entry), B comes back from it (the exit)
                ea = A.r.X[-1] if A.d > 0 else A.r.X[0]
                eb = B.r.X[-1] if B.d > 0 else B.r.X[0]
                if ring_band.distance(shapely.Point(ea)) > 3 or ring_band.distance(shapely.Point(eb)) > 3:
                    continue
                if A.r.L > 80 or B.r.L > 80:
                    continue
                pa = A.r.X if A.d > 0 else A.r.X[::-1]
                pb = B.r.X if B.d > 0 else B.r.X[::-1]
                ring = np.vstack([pa, pb[::-1]])
                poly = shapely.Polygon(ring)
                if not poly.is_valid:
                    poly = shapely.make_valid(poly)
                lanes = shapely.union_all([shapely.LineString(pa).buffer(float(np.median(A.r.W)) / 2),
                                           shapely.LineString(pb).buffer(float(np.median(B.r.W)) / 2), ring_band])
                isl = poly.difference(lanes)
                parts = [g for g in getattr(isl, "geoms", [isl]) if isinstance(g, shapely.Polygon)]
                if not parts:
                    continue
                isl = max(parts, key=lambda g: g.area)
                if isl.area < 4.0:
                    continue
                # asphalt under it: a painted island
                x0, y0, x1, y1 = isl.bounds
                gx, gy = np.meshgrid(np.arange(x0, x1, 0.4), np.arange(y0, y1, 0.4))
                inside = shapely.contains_xy(isl, gx, gy)
                if inside.sum() < 5:
                    continue
                zh = float(np.median(A.r.z)) - 0.1
                h = CARR.height(gx[inside], gy[inside], "near", np.full(int(inside.sum()), zh))
                if np.isfinite(h).mean() < 0.7:
                    stats["islands_physical"] = stats.get("islands_physical", 0) + 1
                    continue
                hatch(isl, unit(pa[-1] - pa[0]), zh, paint)
                stats["islands_painted"] = stats.get("islands_painted", 0) + 1


def hatch(poly, axis, zh, paint):
    """A Sperrfläche: outline and bars at the angle of the dataset to `axis`."""
    out = poly.exterior.buffer(R["hatch_outline"] / 2, join_style="mitre").intersection(poly.buffer(0.01))
    for g in getattr(out, "geoms", [out]):
        if isinstance(g, shapely.Polygon) and g.area > 0.01:
            add_shapely(g, zh, "white", "hatch", paint)
    inner = poly.buffer(-(R["hatch_outline"] + R["hatch_clear"]), join_style="mitre")
    if inner.is_empty:
        return
    ang = math.radians(R["hatch_angle"])
    d = np.array([axis[0] * math.cos(ang) - axis[1] * math.sin(ang), axis[0] * math.sin(ang) + axis[1] * math.cos(ang)])
    nrm = np.array([-d[1], d[0]])
    c = np.asarray(poly.centroid.coords[0])
    R0 = math.sqrt(poly.area) * 3 + 10
    step = R["hatch_w"] + R["hatch_gap"]
    for k in np.arange(-R0, R0, step):
        bar = shapely.Polygon(rect(c + nrm * k, d, 2 * R0, R["hatch_w"])).intersection(inner)
        for g in getattr(bar, "geoms", [bar]):
            if isinstance(g, shapely.Polygon) and g.area > 0.02:
                add_shapely(g, zh, "white", "hatch", paint)
    paint.add("hatched_island")


def add_shapely(g, zh, colour, kind, paint):
    paint.polys.append((g, zh, colour, kind))


# ---------------------------------------------------------------------- 8. the cantonal road of 2022
def cantonal(roads, tr, paint, stats):
    """The cantonal road: stations without paint in 2022, the sides with red bands, the red bands laid again
    smooth along the road."""
    for r in roads:
        r.unmarked = np.zeros(len(r.X), bool)
        r.red_side = {}
        if not is_cantonal(r, tr):
            continue
        if tr["c22_unmarked"] is not None:
            r.unmarked = np.isfinite(tr["c22_unmarked"].query(r.X, distance_upper_bound=3.0)[0])
            r.unmarked = clean_mask(r.unmarked, STEP, 5.0, 10.0)
        for band in tr["c22_red"]:
            lay_red_band(r, band, paint, stats)


def lay_red_band(r, band, paint, stats):
    """A red band (a polygon of 2022) laid again from its inner and outer offsets along the road, smoothed."""
    x0, y0, x1, y1 = band.bounds
    m = (r.X[:, 0] > x0 - 2) & (r.X[:, 0] < x1 + 2) & (r.X[:, 1] > y0 - 2) & (r.X[:, 1] < y1 + 2)
    ii = np.flatnonzero(m)
    if len(ii) < 4:
        return
    t_in, t_out, ss = [], [], []
    for i in ii:
        seg = shapely.LineString([r.X[i] - r.N[i] * 12, r.X[i] + r.N[i] * 12])
        g = band.intersection(seg)
        if g.is_empty:
            continue
        Q = shapely.get_coordinates(g)
        t = (Q - r.X[i]) @ r.N[i]
        if t.max() - t.min() < 0.15:
            continue
        ss.append(r.s[i]); t_in.append(t.min()); t_out.append(t.max())
    if len(ss) < 6:
        return
    ss, a, b = np.array(ss), np.array(t_in), np.array(t_out)
    side = 1 if np.median(a + b) > 0 else -1
    lo, hi = (a, b)
    if len(ss) >= 9:
        lo = savgol_filter(median_filter(lo, 7, mode="nearest"), 9, 2, mode="interp")
        hi = savgol_filter(median_filter(hi, 7, mode="nearest"), 9, 2, mode="interp")
    s = np.arange(ss[0], ss[-1], STEP)
    if len(s) < 2:
        return
    lo, hi = np.interp(s, ss, lo), np.interp(s, ss, hi)
    I, O = r.at(s, lo), r.at(s, hi)
    zh = r.interp(r.z, s) - 0.1
    ring = np.vstack([I, O[::-1]])
    paint.polys.append((shapely.Polygon(ring).buffer(0), float(np.median(zh)), "red", "red_band"))
    i0, i1 = r.idx(s[0]), r.idx(s[-1])
    mask = r.red_side.setdefault(side, np.zeros(len(r.X), bool))
    mask[max(i0 - 2, 0):i1 + 3] = True
    stats["red_band_m"] = stats.get("red_band_m", 0.0) + float(s[-1] - s[0])


def layout_2022(root, out=LAYOUT_2022):
    """dati/cantonale_paint_2022.json from the v1.1 paint of the cantonal road in a level (art/shapes/roads/
    markings.dae, carryover.py) and work/markings_state.json (or dati/): the white paint as points, the red bands
    as polygons, the stretches without paint in 2022 as lines, the route as points."""
    import patch_release as pr
    zi = bng.LevelFiles(root)
    name = f"{LV}/art/shapes/roads/markings.dae"
    V, Nn, T, C, parts = pr.read_dae(zi.path(name))
    white, red = [], []
    for mat, idx in parts:
        t = V[idx[:, 0].reshape(-1, 3)][:, :, :2]
        if mat == "mp_road_paint":
            white.append(t.mean(1))
        elif mat == "mp_road_paint_red":
            red.append(t)
    W = np.concatenate(white)
    keep = np.unique(np.floor(W / 0.5).astype(np.int64), axis=0, return_index=True)[1]
    W = W[np.sort(keep)]
    bands = []
    if red:
        g = shapely.union_all(shapely.polygons(np.concatenate([np.concatenate(red), np.concatenate(red)[:, :1]], 1))).buffer(0.05).buffer(-0.05)
        for p in getattr(g, "geoms", [g]):
            if isinstance(p, shapely.Polygon) and p.area > 1.0:
                bands.append(np.asarray(p.simplify(0.05).exterior.coords).round(3).tolist())
    st = json.load(open(os.path.join(DATI, "markings_state.json")))
    rp = np.load(os.path.join(DATI, "road_profile.npz"))
    s, C2 = rp["s"], rp["center"]
    unmarked = []
    for a, b in st.get("unmarked", []):
        m = (s >= a) & (s <= b)
        unmarked.append(C2[m][::2].round(2).tolist())
    route = C2[::4].round(2).tolist()
    json.dump({"_about": "The paint of the cantonal road Magliaso - Pura as v1.1 built it from the photos (state of "
                         "October 2022, markings_decals.py / markings_state.py), kept for markings_rules.py: 'white' points "
                         "of white paint every 0.5 m (where the centre and edge lines were), 'red_bands' the red edge bands "
                         "(polygons), 'unmarked' the stretches the panoramas showed without paint, 'route' the road's axis.",
               "white": W.round(2).tolist(), "red_bands": bands, "unmarked": unmarked, "route": route},
              open(out, "w"), separators=(",", ":"))
    print("written", out, len(W), "white points,", len(bands), "red bands,", len(unmarked), "unmarked stretches")


# ---------------------------------------------------------------------- the meshes
CARR = None             # TriSurface of the carriageways (set by run)


def tessellate(paint, S, builders, stats):
    """Paint into the mesh builders of the tiles: strips and triangulated polygons on the road faces S."""
    def add(tris, mat):
        c = tris.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(k) for k in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            V = tris[m].reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=V[:, :2], normals=np.repeat([[0, 0, 1.0]], len(V), 0))
    off = 0
    for P, zh, width, colour, kind, _ in paint.lines:
        T = np.gradient(P, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nn = np.column_stack([-T[:, 1], T[:, 0]]) * width / 2
        L, Rr = P + Nn, P - Nn
        zl = S.height(L[:, 0], L[:, 1], "near", zh)
        zr = S.height(Rr[:, 0], Rr[:, 1], "near", zh)
        zc = S.height(P[:, 0], P[:, 1], "near", zh)
        zl = np.where(np.isfinite(zl), zl, zc)
        zr = np.where(np.isfinite(zr), zr, zc)
        ok = np.isfinite(zl) & np.isfinite(zr) & (np.abs(zc - zh) < Z_TOL + 0.3)
        off += int((~ok).sum())
        for a, b in runs(ok):
            if b - a < 2:
                continue
            Lz = np.column_stack([L[a:b], zl[a:b] + LIFT])
            Rz = np.column_stack([Rr[a:b], zr[a:b] + LIFT])
            t = np.stack([Rz[:-1], Rz[1:], Lz[1:], Rz[:-1], Lz[1:], Lz[:-1]], 1).reshape(-1, 3, 3)
            down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
            t[down] = t[down][:, ::-1]
            add(t, PAINT[colour])
    for ring, zh, colour, kind in paint.polys:
        g = ring if isinstance(ring, shapely.Polygon) else shapely.Polygon(ring)
        if not g.is_valid:
            g = shapely.make_valid(g)
        for part in getattr(g, "geoms", [g]):
            if not isinstance(part, shapely.Polygon) or part.area < 0.01:
                continue
            part = shapely.segmentize(part, 0.5)
            tri = shapely.constrained_delaunay_triangles(part)
            V = []
            for t in tri.geoms:
                c = np.asarray(t.exterior.coords)[:3]
                if (c[1, 0] - c[0, 0]) * (c[2, 1] - c[0, 1]) - (c[1, 1] - c[0, 1]) * (c[2, 0] - c[0, 0]) < 0:
                    c = c[::-1]
                V.append(c)
            if not V:
                continue
            V = np.concatenate(V)
            z = S.height(V[:, 0], V[:, 1], "near", np.full(len(V), zh))
            t3 = np.column_stack([V, z + LIFT]).reshape(-1, 3, 3)
            good = np.isfinite(t3[:, :, 2]).all(1) & (np.abs(t3[:, :, 2] - zh - LIFT) < Z_TOL + 0.5).all(1)
            off += int((~good).sum())
            if good.any():
                add(t3[good], PAINT[colour])
    stats["off_road_left_out"] = off


EDGE_SWING = 0.12       # m of offset per m of road: an edge line steeper than this is no edge line
RING_ZONE = 12.0        # m beyond the mapped ring: the junctions of a roundabout
RING_HALF = 4.0         # m from the mapped ring (the middle of the circulating lane) to its outer edge


def ring_list(cx):
    """[(centre, mean radius, ring line)] of the roundabouts of OSM (their ways joined)."""
    lines = [w["line"] for w in cx.ways if w["tags"].get("junction") in ("roundabout", "circular")]
    if not lines:
        return []
    merged = shapely.line_merge(shapely.union_all(lines))
    out = []
    for g in getattr(merged, "geoms", [merged]):
        P = np.asarray(g.coords)[:, :2]
        if len(P) < 4 or np.hypot(*(P[0] - P[-1])) > 2.0:
            continue
        c = P.mean(0)
        out.append((c, float(np.hypot(*(P - c).T).mean()), g))
    return out


def roundabout_entries(cx, paint, stats, bbox=None):
    """The give-way line (6.13, a row of triangles, tips towards the driver) at every entry of a roundabout: where
    the OSM way that enters it crosses the outer edge of the circulating carriageway, across its incoming half (the
    whole carriageway of a one-way entry), measured on the asphalt."""
    tri = R.get("teeth", {"base": 0.5, "height": 0.6, "gap": 0.25})
    base, height, gap = tri.get("base", 0.5), tri.get("height", 0.6), tri.get("gap", 0.25)
    for c, rad, ring in ring_list(cx):
        if bbox is not None and not (bbox[0] - 50 < c[0] < bbox[2] + 50 and bbox[1] - 50 < c[1] < bbox[3] + 50):
            continue
        r_out = rad + RING_HALF
        for w in cx.ways:
            t = w["tags"]
            if t.get("junction") in ("roundabout", "circular") or t.get("highway") in ("service", "track"):
                continue
            P = w["xy"]
            for end in (0, -1):
                if shapely.distance(ring, shapely.Point(P[end])) > 1.5:
                    continue
                Q = P if end == -1 else P[::-1]                  # walking towards the ring
                ow = t.get("oneway") in ("yes", "1", "true", "-1")
                inbound = (end == -1) == (t.get("oneway") != "-1")
                if ow and not inbound:
                    continue
                d = np.hypot(*(Q - c).T)
                k = np.flatnonzero((d[:-1] >= r_out) & (d[1:] < r_out))
                if len(k):
                    k = int(k[-1])
                    f = (d[k] - r_out) / max(d[k] - d[k + 1], 1e-9)
                    p = Q[k] + (Q[k + 1] - Q[k]) * f
                    tv = unit(Q[k + 1] - Q[k])                   # towards the ring
                else:                                            # a short way: on along its last piece
                    e, tv = Q[-1], unit(Q[-1] - Q[0])
                    m = e - c
                    bq = float(m @ -tv)
                    disc = bq * bq - (float(m @ m) - r_out * r_out)
                    if disc < 0:
                        continue
                    p = e - tv * (bq + np.sqrt(disc))
                nr = np.array([tv[1], -tv[0]])                   # right of the driver entering
                # the asphalt across the entry: from the mapped line (the middle of a two-way road, often on its
                # splitter island) to the right for the incoming lane, both ways on a one-way entry
                o = np.arange(-8.0 if ow else 0.0, 8.0, 0.2)
                q = p + nr * o[:, None]
                zq = CARR.height(q[:, 0], q[:, 1], "high")
                zq = np.where(np.abs(zq - np.nanmedian(zq)) < 0.5, zq, np.nan) if np.isfinite(zq).any() else zq
                on = np.isfinite(zq)
                if not on.any():
                    stats["roundabout_entry_off_road"] = stats.get("roundabout_entry_off_road", 0) + 1
                    continue
                runs_ = [(i0, i1) for i0, i1 in runs(on)]
                # the run of asphalt nearest to the line on the right (on a one-way entry the one under the line)
                i0, i1 = min(runs_, key=lambda ab: abs(o[ab[0]] if o[ab[0]] > 0 else (0 if o[ab[1] - 1] >= 0 else -o[ab[1] - 1])))
                lo, hi = max(o[i0], 0.0 if not ow else o[i0]) + 0.3, o[i1 - 1] - 0.3
                z0 = float(np.nanmedian(zq[i0:i1]))
                if hi - lo < 1.5:
                    stats["roundabout_entry_narrow"] = stats.get("roundabout_entry_narrow", 0) + 1
                    continue
                n = int((hi - lo + gap) // (base + gap))
                start = lo + 0.5 * ((hi - lo) - (n * base + (n - 1) * gap))
                mid = p - tv * 1.5
                paint.signals.append((np.array([mid[0], mid[1], z0]), tv, "give_way_ring"))
                for i in range(n):
                    a = p + nr * (start + i * (base + gap))
                    b = a + nr * base
                    tip = (a + b) / 2 - tv * height
                    paint.poly(np.array([a, b, tip]), z0, "white", "give_way_ring")
                stats["roundabout_entries"] = stats.get("roundabout_entries", 0) + 1


# ---------------------------------------------------------------------- the step
def paint_level(zi, bbox=None, stats=None):
    """Everything above on the level of LevelFiles zi: (Paint, roads, junctions, S (road faces))."""
    global CARR
    stats = {} if stats is None else stats
    t0 = time.time()
    items = read_items(zi, f"{LV}/main/MissionGroup/roads/surfaces/items.level.json")
    if bbox is not None:
        items = [o for o in items if "position" not in o or o["position"] == [0, 0, 0] or
                 (bbox[0] - 300 < o["position"][0] < bbox[2] + 300 and bbox[1] - 300 < o["position"][1] < bbox[3] + 300)]
    surf = shape_tris(zi, LV, items)
    if not any(m in CARRIAGE_MATS for m in surf):     # a zone with no carriageway at all (ti_2_7): nothing to paint
        return None
    tops = np.concatenate([up_faces(t) for m, t in surf.items() if m in ROAD_MATS])
    carr = np.concatenate([up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS])
    del surf
    S, CARR = TriSurface(tops), TriSurface(carr)
    print("road faces %d, carriageway %d (%.0f s)" % (len(tops), len(carr), time.time() - t0), flush=True)
    objs = read_items(zi, f"{LV}/main/MissionGroup/AIRoads/items.level.json")
    roads = load_roads(objs, bbox)
    for i, r in enumerate(roads):
        r.i, r.lo, r.hi = i, r.X.min(0) - r.w.max() / 2 - 1, r.X.max(0) + r.w.max() / 2 + 1
    print("AI roads", len(roads), "(%.0f s)" % (time.time() - t0), flush=True)
    measure_edges(roads, CARR)
    print("edges measured (%.0f s)" % (time.time() - t0), flush=True)
    cx = Context()
    road_context(roads, cx)
    print("context (%.0f s)" % (time.time() - t0), flush=True)
    tr = trace_index(roads)
    paint = Paint()
    cantonal(roads, tr, paint, stats)
    for r in roads:
        if r.ring:
            ctr = np.mean(np.concatenate([q.X for q in roads if q.ring and np.hypot(*(q.X.mean(0) - r.X.mean(0))) < 60]), 0)
            v = ctr - r.X
            r.island_side = 1 if np.median(r.T[:, 0] * v[:, 1] - r.T[:, 1] * v[:, 0]) > 0 else -1
    duplicates(roads, stats)
    junc = junctions(roads)
    decide(junc, cx, stats)
    transverse(junc, roads, paint, stats)
    roundabout_entries(cx, paint, stats, bbox)
    snap_ring_signals(paint, roads)
    crossings(roads, cx, tr, paint, stats)
    print("junctions %d, crossings (%.0f s)" % (len(junc), time.time() - t0), flush=True)
    for J in junc:
        for m in J["main"]:
            for a in J["arms"]:
                if a in J["main"] or a.control in ("driveway", "exit", "right_of_way") or a.rank < 2 or a.r.ring:
                    continue
                half = float(a.r.W[a.r.idx(a.s)]) / 2 + MOUTH_MARGIN
                if not m.r.ring:
                    m.r.centre_override.append((m.s - half, m.s + half, "junction"))
    dominated = set()
    for J in junc:
        for m in J["main"]:
            for a in J["arms"]:
                if a not in J["main"]:
                    dominated.add((id(m.r), id(a.r)))
    for r in roads:
        segs = centre_line(r, tr, stats)
        lay_centre(r, segs, paint, stats)
        centre = np.zeros(len(r.X), bool)
        for a, b, _ in segs:
            centre[r.idx(a):r.idx(b) + 1] = True
        lay_edges(r, edge_lines(r, tr, centre, stats), paint, stats)
    arrows(roads, cx, paint, stats)
    islands(roads, junc, paint, stats)
    zone_texts(roads, junc, paint, stats)
    cut_crossing_roads(paint, roads, dominated, stats)
    stats["roads"] = len(roads)
    stats["junctions"] = len(junc)
    print("paint laid (%.0f s)" % (time.time() - t0), flush=True)
    return paint, roads, junc, S


def near_roads(roads, i, P, margin):
    """Indices of the roads (other than i) whose stations come within `margin` m of the bounding box of P."""
    lo, hi = P.min(0) - margin, P.max(0) + margin
    return [j for j, q in enumerate(roads) if j != i and (q.lo <= hi).all() and (q.hi >= lo).all()]


def inside_other(q, P, D, zh, cut_in):
    """(n,) bool: points P (directions D, heights zh) inside the carriageway of road q, which crosses them at
    CUT_ANGLE or more at the same level."""
    if getattr(q, "_kd", None) is None:
        q._kd = cKDTree(q.X)
    d, j = q._kd.query(P)
    v = P - q.X[j]
    along = np.abs((v * q.T[j]).sum(1))
    t = (v * q.N[j]).sum(1)
    cross = np.abs((q.T[j] * D).sum(1)) < math.cos(math.radians(CUT_ANGLE))
    return (along < STEP) & (t < q.eL[j] - cut_in) & (t > q.eR[j] + cut_in) & cross & (np.abs(q.z[j] - zh - 0.1) < 2.0)


def cut_crossing_roads(paint, roads, dominated, stats):
    """No line inside the carriageway of another road it does not belong to: the line points of a road lying
    CUT_IN m inside another road's carriageway (a road crossing at CUT_ANGLE or more, at the same level) are
    left out, unless the line's road has priority over the other there."""
    kept, dropped = [], 0
    for P, zh, width, colour, kind, i in paint.lines:
        D = np.gradient(P, axis=0)
        D /= np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-9)
        bad = np.zeros(len(P), bool)
        for j in near_roads(roads, i, P, 0.5):
            if i >= 0 and (id(roads[i]), id(roads[j])) in dominated:
                continue
            bad |= inside_other(roads[j], P, D, zh, CUT_IN)
        if not bad.any():
            kept.append((P, zh, width, colour, kind, i))
            continue
        for a, b in runs(~bad):
            if b - a >= 2 and float(np.hypot(*np.diff(P[a:b], axis=0).T).sum()) >= MIN_PIECE:
                kept.append((P[a:b], zh[a:b], width, colour, kind, i))
        dropped += int(bad.sum())
    paint.lines = kept
    stats["line_points_in_other_roads"] = dropped


def duplicates(roads, stats):
    """Stretches of a road on the carriageway of another road running the same way (pieces of the network
    drawn twice, a swissTLM3D line along the cantonal road): the lesser road gets no paint there."""
    def rank_of(r):
        return (r.name == CANTONAL, r.main, float(np.median(r.rank)), r.L)
    n = 0
    for i, r in enumerate(roads):
        for j in near_roads(roads, i, r.X, 1.0):
            q = roads[j]
            if rank_of(q) <= rank_of(r):
                continue
            if getattr(q, "_kd", None) is None:
                q._kd = cKDTree(q.X)
            d, k = q._kd.query(r.X)
            v = r.X - q.X[k]
            along = np.abs((v * q.T[k]).sum(1))
            t = (v * q.N[k]).sum(1)
            same = (np.abs((q.T[k] * r.T).sum(1)) > 0.9) & (along < STEP) & (t < q.eL[k] - 0.5) & (t > q.eR[k] + 0.5) \
                & (np.abs(q.z[k] - r.z) < 2.0)
            for a, b in runs(same):
                if (b - a) * STEP >= 10.0:
                    r.block[a:b] = True
                    n += b - a
    stats["duplicate_m"] = round(n * STEP)


def report_numbers(paint, stats):
    km = {}
    for P, zh, width, colour, kind, _ in paint.lines:
        km[kind] = km.get(kind, 0.0) + float(np.hypot(*np.diff(P, axis=0).T).sum())
    stats["km"] = {k: round(v / 1000, 2) for k, v in sorted(km.items())}
    stats["count"] = dict(sorted(paint.count.items()))
    return stats


# the game's simple signal controllers (settings/trafficSignals.json): the traffic stops at a STOP line and gives
# way at a give-way line or a roundabout entry, as the paint and the signs say
SIGNAL_TYPES = {"stop": ("signStop", "basicStop"), "give_way": ("signYield", "basicYield")}
# the game (settings/trafficSignals.json of 0.40) has no give-way sign: the level defines it in
# signalControllerDefinitions.json, which core/trafficSignals.lua reads over the game's types and states
SIGNAL_DEFINITIONS = {"states": {"basicYield": {"action": "yield", "lights": ["black"], "name": "Give Way"}},
                      "types": {"signYield": {"isSimple": True, "name": "Give Way", "states": ["basicYield"]}}}
SIGNAL_SAME = 3.0          # m: signal points of one kind this close, facing the same way, are one
# v3.2: traffic lights. The game's US timings (settings/trafficSignals.json lightsBasic, as east_coast_usa writes its
# controllers); the head is the stock boom of art/ (always loaded), turned so its local +x points to the kerb side
# (BeamNG.Earth places the same model the same way, tested in 0.40.3)
LIGHT_TYPE = "lightsBasic"
LIGHT_STATES = ({"state": "greenTrafficLight", "duration": 15}, {"state": "yellowTrafficLight", "duration": 4},
                {"state": "redTrafficLight", "duration": 1.25})
LIGHT_SHAPE = "/art/shapes/objects/s_trafficlight_boom_sn.dae"
LIGHT_BACK = 1.0           # m from the stop line back along the approach
LIGHT_OUT = 0.8            # m beyond the carriageway's edge
LIGHT_JOIN = 35.0          # m between junction centres of one intersection


def snap_ring_signals(paint, roads):
    """The give-way points of the roundabout entries (found on the OSM ways) onto the entry's AI road: the
    middle of its incoming lane, so the game puts them on the entry and not on the ring."""
    out = []
    for p, d, kind in paint.signals:
        if kind != "give_way_ring":
            out.append((p, d, kind))
            continue
        best = None
        for r in roads:
            if r.ring or not (r.lo[0] - 8 < p[0] < r.hi[0] + 8 and r.lo[1] - 8 < p[1] < r.hi[1] + 8):
                continue
            dd = np.hypot(*(r.X - p[:2]).T)
            i = int(np.argmin(dd))
            c = float(r.T[i] @ d)
            if dd[i] < 8.0 and abs(c) > 0.8 and (best is None or dd[i] < best[0]):
                best = (float(dd[i]), r, i, 1.0 if c > 0 else -1.0)
        if best is None:
            continue
        _, r, i, sg = best
        t = r.T[i] * sg                                  # travel towards the ring
        right = np.array([t[1], -t[0]])
        off = 0.0 if r.oneway else float(r.W[i]) / 4
        q = r.X[i] + right * off
        out.append((np.array([q[0], q[1], float(r.z[i])]), t, "give_way"))
    paint.signals[:] = out


GIVE_WAY_BEFORE, GIVE_WAY_AFTER = 25.0, 12.0   # m of the road lowered before and after a give-way point
GIVE_WAY_DROP = 0.05


def give_way_drivability(points, objs, roads, stats=None):
    """The AI of 0.40 acts on no give-way sign (action "yield" has no handling in vehicle/ai.lua): at a
    junction without a signal it stops and yields when it turns or when its road has a lower drivability than
    another road there. So the AI road of each give-way point gets a short piece (GIVE_WAY_BEFORE m before
    it to GIVE_WAY_AFTER m after) with a drivability GIVE_WAY_DROP under the highest other road at the
    junction ahead; the rest of the road keeps its own. objs (the AIRoads items) are replaced in place."""
    cut = {}                                          # objs index -> [(arc from, arc to, drivability)]
    for p, d, kind in points:
        if kind != "give_way":
            continue
        best = None
        for r in roads:
            if r.ring or not (r.lo[0] - 8 < p[0] < r.hi[0] + 8 and r.lo[1] - 8 < p[1] < r.hi[1] + 8):
                continue
            dd = np.hypot(*(r.X - p[:2]).T)
            i = int(np.argmin(dd))
            c = float(r.T[i] @ d)
            if dd[i] < 8.0 and abs(c) > 0.8 and (best is None or dd[i] < best[0]):
                best = (float(dd[i]), r, i, 1.0 if c > 0 else -1.0)
        if best is None:
            continue
        _, r, i, sg = best
        q = p[:2] + d[:2] * 8.0                       # the junction ahead
        other = [o.drive for o in roads if o is not r and
                 o.lo[0] - 10 < q[0] < o.hi[0] + 10 and o.lo[1] - 10 < q[1] < o.hi[1] + 10 and
                 np.hypot(*(o.X - q).T).min() < max(6.0, float(o.w.max()))]
        if not other or r.drive < max(other):
            continue
        a = float(r.s[i])
        lo, hi = (a - GIVE_WAY_BEFORE, a + GIVE_WAY_AFTER) if sg > 0 else (a - GIVE_WAY_AFTER, a + GIVE_WAY_BEFORE)
        cut.setdefault(r.k, []).append((lo, hi, max(0.05, round(max(other) - GIVE_WAY_DROP, 2))))
    out, n = [], 0
    for k, o in enumerate(objs):
        if k not in cut:
            out.append(o)
            continue
        nd = np.asarray(o["nodes"], float)
        arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(nd[:, :2], axis=0).T))])
        arc *= (len(next(r for r in roads if r.k == k).s) - 1) * STEP / max(arc[-1], 1e-9)   # as the stations
        marks = np.zeros(len(nd) - 1)                 # drivability of each node-to-node stretch (0: the road's)
        for lo, hi, dv in cut[k]:
            a = max(int(np.searchsorted(arc, lo, "right")) - 1, 0)
            b = min(int(np.searchsorted(arc, hi, "left")), len(nd) - 1)
            if b <= a:
                continue
            marks[a:b] = np.where(marks[a:b] > 0, np.minimum(marks[a:b], dv), dv)
        start = 0
        for j in range(1, len(marks) + 1):
            if j == len(marks) or marks[j] != marks[start]:
                q = dict(o) if start == 0 else {**o, "name": "%s_g%d" % (o.get("name", "road"), start),
                                                "persistentId": bng.pid()}
                q["nodes"] = o["nodes"][start:j + 1]
                q["position"] = q["nodes"][0][:3]
                if marks[start] > 0:
                    q["drivability"] = float(marks[start])
                    n += 1
                out.append(q)
                start = j
    objs[:] = out
    if stats is not None:
        stats["give_way_pieces"] = n
    return n


def signals_json(points, stats=None, lights=()):
    """levels/<level>/signals.json of the stop and give-way points: one simple controller per kind, an
    instance per point (sequence 0: no timer); v3.2: the traffic lights, a sequence of two phases per junction (its
    ways in split by axis), one controller per phase, an instance per way in named as its head's signalInstance."""
    ctrl = {}
    out = {"instances": [], "controllers": [], "sequences": {}}
    for kind, (typ, state) in SIGNAL_TYPES.items():
        ctrl[kind] = len(ctrl) + 1
        out["controllers"].append({"id": ctrl[kind], "name": kind, "type": typ, "isSimple": True,
                                   "states": [{"state": state}]})
    kept = []
    for p, d, kind in points:
        if any(k == kind and np.hypot(*(q[:2] - p[:2])) < SIGNAL_SAME and float(e @ d) > 0.7 for q, e, k in kept):
            continue
        kept.append((p, d, kind))
    nid = len(ctrl)
    for i, (p, d, kind) in enumerate(kept):
        nid += 1
        out["instances"].append({"id": nid, "name": "%s %d" % (kind, i + 1), "controllerId": ctrl[kind],
                                 "sequenceId": 0, "pos": [round(float(v), 3) for v in p],
                                 "dir": [round(float(d[0]), 4), round(float(d[1]), 4), 0.0],
                                 "startDisabled": False})
    if stats is not None:
        stats["signals"] = {k: sum(1 for _, _, q in kept if q == k) for k in SIGNAL_TYPES}
    heads = []
    # junctions closer than LIGHT_JOIN (the two halves of a crossing of divided roads, a junction the AI roads
    # draw as two) are one intersection: one sequence, so their ways in are never green against each other
    keys = sorted({L[2] for L in lights})
    root = {k: k for k in keys}

    def find(k):
        while root[k] != k:
            k = root[k]
        return k
    if keys:
        kd = cKDTree(np.array(keys))
        for i, j in kd.query_pairs(LIGHT_JOIN):
            root[find(keys[i])] = find(keys[j])
    by_j = {}
    for L in lights:
        by_j.setdefault(find(L[2]), []).append(L)
    sid = 0                                          # controllers and instances share one id count (as above)
    for J in by_j.values():
        sid += 1
        a0 = np.arctan2(J[0][1][1], J[0][1][0])
        phase = [0 if abs(((np.arctan2(L[1][1], L[1][0]) - a0) + np.pi / 2) % np.pi - np.pi / 2) < np.pi / 4 else 1
                 for L in J]
        ph_ids = []
        for ph in sorted(set(phase)):
            nid += 1
            ph_ids.append((ph, nid))
            out["controllers"].append({"id": nid, "name": "lights_%d_%d" % (sid, ph), "type": LIGHT_TYPE,
                                       "defaultIndex": 3, "states": [dict(st) for st in LIGHT_STATES]})
        seq = {"id": sid, "name": "lights_%d" % sid, "startTime": 0,
               "phases": [{"controllerIds": [c]} for _, c in ph_ids]}
        out.setdefault("_seqs", []).append(seq)
        for L, ph in zip(J, phase):
            nid += 1
            name = "trafficLight_%d_%d" % (sid, nid)
            p, d = L[0], L[1]
            out["instances"].append({"id": nid, "name": name, "controllerId": dict(ph_ids)[ph], "sequenceId": sid,
                                     "group": "lights_%d" % sid, "pos": [round(float(v), 3) for v in p],
                                     "dir": [round(float(d[0]), 4), round(float(d[1]), 4), 0.0],
                                     "startDisabled": False})
            heads.append((name, L[3], L[4]))
    if out.get("_seqs"):
        # the game reads sequences as a list (east_coast_usa) or the empty object of a level without any (italy)
        out["sequences"] = out.pop("_seqs")
    if stats is not None:
        stats["traffic_lights"] = {"junctions": len(by_j), "heads": len(heads)}
    out["_heads"] = heads
    return out


def markings_rules_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    stats = {}
    got = paint_level(zi, stats=stats)
    if got is None:
        # the later steps read roads/markings: give it an empty group when there is none
        print("markings: no carriageway in the level, nothing painted", flush=True)
        mk_items = f"{LV}/main/MissionGroup/roads/markings/items.level.json"
        if mk_items not in zi.NameToInfo:
            g = f"{LV}/main/MissionGroup/roads/items.level.json"
            new_files = {mk_items: b"", g: (zi.read(g) if g in zi.NameToInfo else b"") + (json.dumps(
                {"name": "markings", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"},
                separators=(",", ":")) + "\n").encode("utf-8")}
            with zi.writer() as zo:
                for i in zi.infolist():
                    if i.filename not in new_files:
                        zo.writestr(i, zi.read(i), compress_type=i.compress_type)
                for n, data in sorted(new_files.items()):
                    zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
        return 0
    paint, roads, junc, S = got
    builders = {}
    tessellate(paint, S, builders, stats)
    report_numbers(paint, stats)
    mk_items = f"{LV}/main/MissionGroup/roads/markings/items.level.json"
    # a zone with no v1.1 route paint has no markings group yet (ti_0_7): it is made here
    fresh = mk_items not in zi.NameToInfo
    mk = [] if fresh else read_items(zi, mk_items)
    old = {k: v for k, v in old_paint(zi, mk).items()}
    stats["old_paint_m2"] = old
    tmp = tempfile.mkdtemp(prefix="magliaso_mkr_")
    try:
        new_files, objs = {}, []
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/markings_net_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(f, name=f"markings_net_{tx}_{ty}", origin=origin)
            text = open(f, encoding="utf-8").read()
            out, _ = optimize_level.optimize_dae([(text, np.zeros(3))], rel.split("art/shapes/", 1)[1])
            new_files[f"{LV}/{rel}"] = (out or text).encode("utf-8")
            objs.append(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False))
        mats_name = f"{LV}/art/road/paint.materials.json"
        mats = json.loads(zi.read(mats_name)) if mats_name in zi.NameToInfo else {}
        for m in (bng.material("mp_road_paint", base_color=[0.86, 0.86, 0.84, 1], roughness=0.65),
                  bng.material("mp_road_paint_yellow", base_color=[0.88, 0.72, 0.12, 1], roughness=0.65),
                  bng.material("mp_road_paint_red", base_color=[0.66, 0.46, 0.46, 1], roughness=0.7)):
            mats.setdefault(m["name"], m)
        new_files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
        sj = signals_json(paint.signals, stats, paint.lights)
        heads = sj.pop("_heads")
        new_files[f"{LV}/signals.json"] = json.dumps(sj, indent=1).encode("utf-8")
        ai_items = f"{LV}/main/MissionGroup/AIRoads/items.level.json"
        ai = read_items(zi, ai_items)
        if give_way_drivability(paint.signals, ai, roads, stats):
            new_files[ai_items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in ai) + "\n").encode("utf-8")
        new_files[f"{LV}/signalControllerDefinitions.json"] = json.dumps(SIGNAL_DEFINITIONS, indent=1).encode("utf-8")
        parent = next((o["__parent"] for o in mk if "__parent" in o), "markings")
        keep = [o for o in mk if not NET_SHAPE.search(o.get("shapeName", "")) and not OLD_SHAPE.search(o.get("shapeName", ""))
                and o.get("annotation") != "TRAFFIC_SIGNALS"]
        for name, q, side in heads:
            o = bng.tsstatic(LIGHT_SHAPE, q, collision=True, decal=False, annotation="TRAFFIC_SIGNALS")
            o["rotationMatrix"] = bng.rot_local_x_to(float(np.arctan2(side[1], side[0])))
            o["dynamic"] = True
            o["signalInstance"] = name
            objs.append(o)
        for o in objs:
            o["__parent"] = parent
        new_files[mk_items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in keep + objs) + "\n").encode("utf-8")
        n_old = sum(1 for n in zi.namelist() if NET_SHAPE.search(n) or OLD_SHAPE.search(n))
        if fresh:
            g = f"{LV}/main/MissionGroup/roads/items.level.json"
            new_files[g] = ((zi.read(g) if g in zi.NameToInfo else b"") + (json.dumps(
                {"name": "markings", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"},
                separators=(",", ":")) + "\n").encode("utf-8"))
        with zi.writer() as zo:
            for i in zi.infolist():
                n = i.filename
                if n in new_files or NET_SHAPE.search(n) or OLD_SHAPE.search(n):
                    continue
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
        stats["meshes"] = len(builders)
        stats["old_meshes"] = n_old
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats["seconds"] = round(time.time() - t0)
    print("markings by the rules:", json.dumps({k: v for k, v in stats.items() if k in ("km", "count", "meshes", "seconds", "signals")}), flush=True)
    if report:
        json.dump(stats, open(report, "w"), indent=1, default=float)
    return 0


def old_paint(zi, mk):
    """Area (m2) of the paint of the level before the step, by colour (the report's comparison)."""
    out = {}
    objs = [o for o in mk if NET_SHAPE.search(o.get("shapeName", "")) or OLD_SHAPE.search(o.get("shapeName", ""))]
    for mat, t in shape_tris(zi, LV, objs).items():
        a = 0.5 * np.abs(cross2(t[:, 1, :2] - t[:, 0, :2], t[:, 2, :2] - t[:, 0, :2])).sum()
        out[mat] = round(float(a), 1)
    return out


# ---------------------------------------------------------------------- a test on part of the map
def plot(paint, roads, bbox, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    x0, y0, x1, y1 = bbox
    fig = plt.figure(figsize=(14, 14 * (y1 - y0) / (x1 - x0)), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor((0.25, 0.3, 0.22))
    t = CARR.t[:, :, :2]
    m = (t[:, :, 0].max(1) > x0) & (t[:, :, 0].min(1) < x1) & (t[:, :, 1].max(1) > y0) & (t[:, :, 1].min(1) < y1)
    ax.add_collection(PolyCollection(t[m], facecolors=(0.38, 0.38, 0.39), edgecolors="none"))
    col = {"white": (0.97, 0.97, 0.95), "yellow": (0.95, 0.8, 0.15), "red": (0.8, 0.3, 0.3)}
    for P, zh, width, colour, kind, _ in paint.lines:
        ax.plot(P[:, 0], P[:, 1], color=col[colour], lw=max(width * 110 * 14 / (x1 - x0) * 0.75, 0.4), solid_capstyle="butt")
    for ring, zh, colour, kind in paint.polys:
        g = ring if isinstance(ring, shapely.Polygon) else shapely.Polygon(ring)
        for p in getattr(g, "geoms", [g]):
            if isinstance(p, shapely.Polygon):
                ax.fill(*np.asarray(p.exterior.coords).T, color=col[colour], lw=0)
    for r in roads:
        ax.plot(r.X[:, 0], r.X[:, 1], color=(0.2, 0.6, 1.0), lw=0.3, alpha=0.5)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    fig.savefig(path)
    plt.close(fig)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--layout-2022":
        layout_2022(a[1])
        sys.exit(0)
    root = a[0]
    if "--bbox" in a:
        k = a.index("--bbox")
        bbox = tuple(float(v) for v in a[k + 1:k + 5])
        st = {}
        zi = bng.LevelFiles(root)
        paint, roads, junc, S = paint_level(zi, bbox, st)
        report_numbers(paint, st)
        print(json.dumps(st, indent=1, default=float))
        if "--plot" in a:
            plot(paint, roads, bbox, a[a.index("--plot") + 1])
    else:
        markings_rules_step(root, report=os.path.join(os.getcwd(), "markings_rules.json"))
