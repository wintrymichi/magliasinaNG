"""Road paint of the network (network_markings.py) cleaned into the shapes of Swiss road markings (v2.7).

network_markings.py traces what the 10 cm orthophoto shows, so the paint it writes carries the noise
of the photo: in the game (v2.1 - v2.6) the lines wobbled, the dashes of one line had different
lengths and steps, a line was traced twice side by side (the paint and the light concrete gutter
beside it, or the same paint seen from two network segments), solid lines broke wherever a car or
its shadow covered them, a pedestrian crossing was a handful of yellow blobs and cars, glare and
manholes left white blobs on the asphalt. This step keeps where the paint is (the positions the
orthophoto measured) and redraws it the way it is painted (VSS SN 640 850 / 640 851):
1. lines: every track smoothed (a quadratic fit over SMOOTH m, which keeps the curves of the road);
   a track that runs along another one of the same colour within DUP m is the same line and is
   trimmed where the other covers it; of two solid lines DUP-GUTTER m apart on the same side of a
   road the outer one is the gutter beside the edge line;
2. dashed stretches: one dash length and one period per stretch, snapped to the Swiss values
   (dashes 1.5 / 3 / 6 m, periods of 4.5 / 6 / 9 / 12 m) where the measure is within SNAP, laid at
   the measured phase from the first dash to the last (a dash a car covered is put back);
3. solid lines: pieces joined across gaps up to GAP_SOLID m (a parked car, a shadow) and across the
   stretches hidden by trees up to GAP_HIDDEN m, never across a junction of the road network of OSM;
4. pedestrian crossings (yellow in Switzerland): the yellow bars of one crossing replaced by the
   standard crossing: bars ZEBRA_W m wide ZEBRA_W m apart, parallel to the road, across the whole
   carriageway, at the measured phase; marked crossings of OSM that the photo does not show (under
   a tree, a car on them) are added where the carriageway is;
5. the other paint: strips (stop and give-way lines, bars of hatched areas) as clean rectangles,
   arrows and letters as they were traced; blobs that have neither shape (a car, glare, a manhole)
   are left out.
The result has the format of network_markings.json, and markings_net.py builds it.
"""
import numpy as np
import shapely
from scipy.signal import savgol_filter

SMOOTH = 14.0                  # m, window of the quadratic fit along a track
DUP = 0.40                     # m, two tracks closer than this are one line
GUTTER = 0.95                  # m, a second solid line this close outside an edge line is the gutter
GAP_SOLID = 9.0                # m, gaps of a solid line closed (cars, shadows)
MIN_SOLID_PIECE = 8.0          # m, a solid line is joined across a gap only next to a piece this long
GAP_HIDDEN = 150.0             # m, gaps of a line under trees closed (hidden over half their length)
JUNCTION = 7.0                 # m around a junction of the network where a line is not continued
DASHES = (1.5, 3.0, 6.0)       # m, Swiss dash lengths
PERIODS = (4.5, 6.0, 9.0, 12.0, 18.0)   # m, dash + gap (1.5/3, 3/3, 3/6, 6/6, 6/12)
SNAP = 0.15                    # relative difference within which a measure takes the Swiss value
MAX_MISSING = 5                # dashes in a row that may be missing inside one dashed stretch
MIN_DASHES = 3
ZEBRA_W = 0.5                  # m, bars of a pedestrian crossing and gaps between them
ZEBRA_L = (2.5, 3.0, 4.0)      # m, lengths of the bars (along the road)
ZEBRA_EDGE = 0.3               # m between the carriageway edge and the outer bar
PAINTED_CLEAR = 40.0           # m around the paint of the Street View route where OSM adds no crossing
CROSS_CLEAR = 0.5              # m between a crossing and the lines along the road
GROUP_R = 4.5                  # m, bars of one crossing are this close (a car on it hides a few)
CROSS_TAGS = {"zebra", "marked", "uncontrolled", "traffic_signals"}


# ---------------------------------------------------------------------- geometry of a track
class Track:
    """A polyline with arc length: points at u, positions of points along it."""

    def __init__(self, P):
        P = np.asarray(P, np.float64)
        keep = np.r_[True, np.hypot(*np.diff(P, axis=0).T) > 1e-6]
        self.P = P[keep]
        self.u = np.r_[0, np.cumsum(np.hypot(*np.diff(self.P, axis=0).T))]
        self.line = shapely.LineString(self.P) if len(self.P) >= 2 else None

    @property
    def length(self):
        return float(self.u[-1])

    def at(self, u):
        u = np.clip(np.asarray(u, np.float64), 0, self.u[-1])
        return np.column_stack([np.interp(u, self.u, self.P[:, 0]), np.interp(u, self.u, self.P[:, 1])])

    def project(self, XY):
        return np.array([self.line.project(shapely.Point(p)) for p in np.atleast_2d(XY)])

    def piece(self, a, b, step=1.0):
        """Points of the track from u = a to b, every `step` m and at the corners in between."""
        inner = self.u[(self.u > a) & (self.u < b)]
        uu = np.unique(np.r_[a, np.arange(a, b, step), inner, b])
        return self.at(uu)


def smooth_track(P, spacing):
    """Quadratic fit over SMOOTH m (Savitzky-Golay): removes the lateral noise of the traced peaks and
    keeps the curves."""
    P = np.asarray(P, np.float64)
    n = len(P)
    w = int(round(SMOOTH / max(spacing, 1e-3))) | 1
    w = min(w, n if n % 2 else n - 1)
    if w < 5:
        return P
    return np.column_stack([savgol_filter(P[:, 0], w, 2, mode="interp"), savgol_filter(P[:, 1], w, 2, mode="interp")])


def track_of(ln):
    """The smoothed track of a line, extended over its painted runs."""
    pts = np.asarray(ln["pts"], np.float64)
    runs = [np.asarray(r, np.float64) for r in ln["runs"] if len(r) >= 2]
    if len(pts) < 2:
        pts = np.concatenate(runs) if runs else pts
    if len(pts) < 2:
        return None
    t = Track(pts)
    # the runs may reach a little beyond the points of the track (they are every 2 m)
    ends = np.array([r[0] for r in runs] + [r[-1] for r in runs]) if runs else np.zeros((0, 2))
    if len(ends):
        d0 = t.P[1] - t.P[0]; d0 /= max(np.linalg.norm(d0), 1e-9)
        d1 = t.P[-1] - t.P[-2]; d1 /= max(np.linalg.norm(d1), 1e-9)
        lo = min(((ends - t.P[0]) @ d0).min(), 0.0)
        hi = max(((ends - t.P[-1]) @ d1).max(), 0.0)
        P = t.P
        if lo < -0.05:
            P = np.vstack([P[0] + d0 * lo, P])
        if hi > 0.05:
            P = np.vstack([P, P[-1] + d1 * hi])
        t = Track(P)
    spacing = t.length / max(len(t.P) - 1, 1)
    return Track(smooth_track(t.P, spacing))


def intervals_of(ln, tr):
    """Painted intervals (u0, u1) of a line along its track."""
    out = []
    for r in ln["runs"]:
        if len(r) < 2:
            continue
        a, b = sorted(tr.project(np.asarray([r[0], r[-1]], np.float64)))
        if b - a > 0.2:
            out.append((float(a), float(b)))
    return merge_intervals(out, 0.15)


def merge_intervals(iv, gap=0.0):
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def subtract(iv, cut):
    """Intervals iv minus the intervals cut."""
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
    return [(a, b) for a, b in out if b - a > 0.3]


# ---------------------------------------------------------------------- the network around the paint
class Network:
    """Junctions of the drivable OSM ways (nodes shared by two ways, way ends) and the marked
    pedestrian crossings with the direction of their road."""

    def __init__(self, ways, nodes, drive):
        count, xy = {}, {}
        for w in ways:
            if w["tags"].get("highway") not in drive or len(w["nodes"]) != len(w["xy"]):
                continue
            for k, (nid, p) in enumerate(zip(w["nodes"], w["xy"])):
                xy[nid] = p
                count[nid] = count.get(nid, 0) + (2 if k in (0, len(w["nodes"]) - 1) else 1)
        J = [xy[n] for n, c in count.items() if c >= 2]
        self.junctions = np.array(J) if J else np.zeros((0, 2))
        from scipy.spatial import cKDTree
        self.kd = cKDTree(self.junctions) if len(J) else None
        self.crossings = []
        ok = lambda t: (t.get("highway") == "crossing" and t.get("crossing") != "unmarked"
                        and t.get("crossing:markings") not in ("no", "dashes", "lines", "dots")
                        and (t.get("crossing") in CROSS_TAGS or t.get("crossing_ref") == "zebra"
                             or t.get("crossing:markings") in ("zebra", "yes")))
        by_id = {nd["id"]: nd for nd in nodes if ok(nd["tags"])}
        for w in ways:
            if w["tags"].get("highway") not in drive or len(w["nodes"]) != len(w["xy"]):
                continue
            for k, nid in enumerate(w["nodes"]):
                if nid in by_id:
                    a, b = w["xy"][max(k - 1, 0)], w["xy"][min(k + 1, len(w["xy"]) - 1)]
                    d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
                    self.crossings.append((np.asarray(w["xy"][k], np.float64), d, w["tags"].get("highway")))
                    del by_id[nid]

    def near_junction(self, P, r=JUNCTION):
        if self.kd is None or not len(P):
            return False
        return any(len(q) for q in self.kd.query_ball_point(np.atleast_2d(P), r))


# ---------------------------------------------------------------------- longitudinal lines
def snap(v, values):
    best = min(values, key=lambda s: abs(v - s))
    return best if abs(v - best) <= SNAP * best else v


def dashed_stretches(iv):
    """Groups of intervals that are the dashes of one dashed line: [(indices, period)]."""
    lens = np.array([b - a for a, b in iv])
    is_dash = (lens >= 0.8) & (lens <= 7.0)
    groups, cur = [], []
    for k in range(len(iv)):
        if not is_dash[k]:
            if len(cur) >= MIN_DASHES:
                groups.append(cur)
            cur = []
            continue
        if cur:
            step = iv[k][0] - iv[cur[-1]][0]
            if step > (MAX_MISSING + 1) * 15.0:
                if len(cur) >= MIN_DASHES:
                    groups.append(cur)
                cur = []
        cur.append(k)
    if len(cur) >= MIN_DASHES:
        groups.append(cur)
    out = []
    for g in groups:
        starts = np.array([iv[k][0] for k in g])
        steps = np.diff(starts)
        base = float(np.median(steps[steps <= np.percentile(steps, 60) * 1.2]))
        if not 3.0 <= base <= 20.0:
            continue
        mult = steps / base
        if (np.abs(mult - np.round(mult)) < 0.2).mean() < 0.7:
            continue
        # split where a gap is longer than MAX_MISSING dashes
        cut = np.flatnonzero(np.round(mult) > MAX_MISSING + 1)
        for part in np.split(np.array(g), cut + 1):
            if len(part) >= MIN_DASHES:
                out.append((list(part), base))
    return out


def relay_dashes(iv, idx, base):
    """Dashes of one stretch at one length and period (Swiss values when close) and the measured phase."""
    starts = np.array([iv[k][0] for k in idx])
    ends = np.array([iv[k][1] for k in idx])
    k = np.round((starts - starts[0]) / base)
    # least squares period and phase over the dash numbers
    if k[-1] > 0:
        period, s0 = np.polyfit(k, starts, 1)
    else:
        period, s0 = base, starts[0]
    dl = float(np.median(ends - starts))
    p = snap(period, PERIODS)
    d = snap(dl, DASHES)
    if d >= 0.8 * p:                  # the snapped dash would close the gap: keep the measure
        p, d = period, dl
    # phase: the dash starts relative to the snapped period, centred on the measured dashes
    centres = (starts + ends) / 2
    s0 = float(np.median(centres - k * p)) - d / 2
    n = int(k[-1])
    return [(s0 + q * p, s0 + q * p + d) for q in range(n + 1)], p, d


def clean_line(ln, tr, hidden, net):
    """Painted intervals of one line redrawn: dashed stretches regular, solid pieces joined."""
    iv = intervals_of(ln, tr)
    if not iv:
        return [], "none"
    groups = dashed_stretches(iv)
    in_dash = set(k for g, _ in groups for k in g)
    dashes = []
    for g, base in groups:
        dd, _, _ = relay_dashes(iv, g, base)
        dashes += dd
    solid = [iv[k] for k in range(len(iv)) if k not in in_dash]
    # solid pieces joined across short gaps and hidden stretches, not across junctions
    joined = []
    for a, b in solid:
        if joined:
            pa, pb = joined[-1]
            g = a - pb
            gap_pts = tr.at(np.linspace(pb, a, max(int(g / 2.0), 2)))
            hid = hidden_share(tr, pb, a, hidden)
            long_piece = max(pb - pa, b - a) >= MIN_SOLID_PIECE      # two dashes are not a broken solid line
            if g <= GAP_HIDDEN and ((g <= GAP_SOLID and long_piece) or hid >= 0.5) and not net_junction(net, gap_pts) \
                    and not any(x < a and y > pb for x, y in dashes):
                joined[-1] = (pa, b)
                continue
        joined.append((a, b))
    solid = [(a, b) for a, b in joined if b - a >= 2.0]
    out = merge_intervals(sorted(solid + [(max(a, 0.0), min(b, tr.length)) for a, b in dashes]), 0.05)
    out = [(a, b) for a, b in out if b - a >= 0.5]
    pattern = {(False, False): "none", (True, False): "solid", (False, True): "dashed", (True, True): "mixed"}[
        (bool(solid), bool(dashes))]
    return out, pattern


def net_junction(net, P):
    return net is not None and net.near_junction(P)


def hidden_share(tr, a, b, hidden):
    """Share of the gap (a, b) of a track that lies in the hidden stretches (polygons) of its segment."""
    if hidden is None or b <= a:
        return 0.0
    P = tr.at(np.linspace(a, b, max(int((b - a) / 1.0), 3)))
    return float(shapely.contains_xy(hidden, P[:, 0], P[:, 1]).mean())


def dedupe(items):
    """items: [{"tr", "iv", "color", "pattern", "seg", "t"}]. Trims the paint a longer line of the same
    colour already covers within DUP m, and the outer of two solid lines (the gutter) within GUTTER m on
    the same side of the same road."""
    order = sorted(range(len(items)), key=lambda i: -sum(b - a for a, b in items[i]["iv"]))
    lines = [it["tr"].line for it in items]
    tree = shapely.STRtree(lines)
    for r, i in enumerate(order):
        it = items[i]
        if not it["iv"]:
            continue
        for j in tree.query(lines[i].buffer(GUTTER)):
            j = int(j)
            if j == i or not items[j]["iv"] or items[j]["color"] != it["color"]:
                continue
            o = items[j]
            if order.index(j) < r:                    # j is the longer one, handled from its side
                continue
            # where the paint of o runs along the track of it
            cut = []
            gutter = (o["seg"] == it["seg"] and o["pattern"] == "solid" and it["pattern"] in ("solid", "mixed")
                      and np.sign(o["t"]) == np.sign(it["t"]) and abs(o["t"]) > abs(it["t"]))
            for a, b in o["iv"]:
                uu = np.arange(a, b + 0.5, 0.5)
                P = o["tr"].at(uu)
                d = np.array([it["tr"].line.distance(shapely.Point(p)) for p in P])
                close = d <= (GUTTER if gutter else DUP)
                if not close.any():
                    continue
                e = np.flatnonzero(np.diff(np.r_[0, close.astype(int), 0]))
                cut += [(uu[x] - 0.25, uu[y - 1] + 0.25) for x, y in zip(e[::2], e[1::2])]
            if cut:
                o["iv"] = subtract(o["iv"], merge_intervals(cut, 0.5))
                o["iv"] = [(a, b) for a, b in o["iv"] if b - a >= (0.8 if o["pattern"] != "solid" else 2.0)]


def clean_lines(d, net=None):
    hidden_by_seg = {}
    items = []
    for ln in d["lines"]:
        tr = track_of(ln)
        if tr is None or tr.length < 1.0:
            continue
        items.append({"ln": ln, "tr": tr, "color": ln["color"], "pattern": ln["pattern"], "seg": ln["seg"],
                      "t": ln.get("t_median", 0.0)})
    # hidden stretches as polygons around the tracks of their segment (from the strip stations)
    tracks_by_seg = {}
    for it in items:
        tracks_by_seg.setdefault(it["seg"], []).append(it)
    for h in d.get("hidden", []):
        hidden_by_seg.setdefault(h["seg"], []).append((h["from"], h["to"]))
    hid_poly = {}
    for seg, its in tracks_by_seg.items():
        hs = hidden_by_seg.get(seg)
        if not hs:
            continue
        polys = []
        for it in its:
            ln = it["ln"]
            # strip stations of the line: runs_s (strip s) against its runs (xy) map s onto the track
            if not ln.get("runs_s") or len(ln["runs_s"]) != len(ln["runs"]):
                continue
            S = np.array([s for a, b in ln["runs_s"] for s in (a, b)])
            U = np.array([u for r in ln["runs"] for u in it["tr"].project(np.asarray([r[0], r[-1]], np.float64))])
            if len(S) < 2 or np.ptp(S) < 1.0:
                continue
            o = np.argsort(S)
            S, U = S[o], U[o]
            for a, b in hs:
                ua, ub = np.interp([a, b], S, U, left=np.nan, right=np.nan)
                if not np.isfinite([ua, ub]).all():
                    # beyond the measured runs: extrapolate with unit slope along the track
                    ua = U[0] + (a - S[0]) if a < S[0] else (U[-1] + (a - S[-1]) if a > S[-1] else ua)
                    ub = U[0] + (b - S[0]) if b < S[0] else (U[-1] + (b - S[-1]) if b > S[-1] else ub)
                ua, ub = sorted((float(ua), float(ub)))
                ua, ub = max(ua, 0.0), min(ub, it["tr"].length)
                if ub - ua > 0.5:
                    polys.append(shapely.LineString(it["tr"].piece(ua, ub)).buffer(1.5))
        if polys:
            hid_poly[seg] = shapely.union_all(polys)
            shapely.prepare(hid_poly[seg])
    for it in items:
        it["iv"], it["pattern"] = clean_line(it["ln"], it["tr"], hid_poly.get(it["seg"]), net)
    dedupe(items)
    out = []
    for it in items:
        iv = [(a, b) for a, b in it["iv"] if b - a >= 0.5]
        if not iv or sum(b - a for a, b in iv) < 2.5:
            continue
        ln = dict(it["ln"])
        ln["pattern"] = it["pattern"]
        ln["runs"] = [it["tr"].piece(a, b).round(3).tolist() for a, b in iv]
        ln["pts"] = it["tr"].P[::max(1, len(it["tr"].P) // 400)].round(3).tolist()
        ln["runs_u"] = [[round(a, 2), round(b, 2)] for a, b in iv]
        ln.pop("runs_s", None)
        out.append(ln)
    return out


# ---------------------------------------------------------------------- crossings and other paint
def rect_of(poly):
    """(centre (2,), long axis unit (2,), long, short) of the minimum rotated rectangle."""
    ex = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4]
    e1, e2 = ex[1] - ex[0], ex[2] - ex[1]
    l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
    if l1 >= l2:
        return ex.mean(0), e1 / max(l1, 1e-9), l1, l2
    return ex.mean(0), e2 / max(l2, 1e-9), l2, l1


def rect_poly(c, ax, length, width):
    n = np.array([-ax[1], ax[0]])
    h, w = ax * length / 2, n * width / 2
    return np.array([c - h - w, c + h - w, c + h + w, c - h + w, c - h - w])


class Carriage:
    """The carriageways as the top faces (k, 3, 3) or (k, 3, 2) of the road meshes: what lies on them and
    how far they reach along a line."""

    def __init__(self, tris):
        T = np.asarray(tris, np.float64)[:, :, :2]
        a = (T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1]) - (T[:, 1, 1] - T[:, 0, 1]) * (T[:, 2, 0] - T[:, 0, 0])
        T = T[np.abs(a) > 1e-6]
        self.polys = shapely.polygons(np.concatenate([T, T[:, :1]], 1))
        self.tree = shapely.STRtree(self.polys)

    def contains(self, p):
        return len(self.tree.query(shapely.Point(p), predicate="intersects")) > 0

    def span(self, c, cross, reach=14.0):
        """(t0, t1) of the carriageway along the direction `cross` through c (t = 0 at c), or None."""
        seg = shapely.LineString([c - cross * reach, c + cross * reach])
        iv = []
        for k in self.tree.query(seg, predicate="intersects"):
            g = self.polys[k].intersection(seg)
            for p in getattr(g, "geoms", [g]):
                if isinstance(p, shapely.LineString) and not p.is_empty:
                    t = (np.asarray(p.coords) - c) @ cross
                    iv.append((float(t.min()), float(t.max())))
        for a, b in merge_intervals(iv, 0.05):
            if a <= 0.3 and b >= -0.3:
                return a, b
        return None


def carriage_span(carriage, c, cross):
    return carriage.span(c, cross) if carriage is not None else None


def zebra(c, along, t0, t1, bar_len, phase=None):
    """Bars of a Swiss pedestrian crossing at c: bars parallel to `along`, ZEBRA_W wide and apart, from
    t0 to t1 across the road (t = 0 at c); phase: centre of one bar (t), else centred."""
    cross = np.array([-along[1], along[0]])
    a, b = t0 + ZEBRA_EDGE, t1 - ZEBRA_EDGE
    if b - a < ZEBRA_W:
        return []
    p = 2 * ZEBRA_W
    if phase is None:
        n = int(np.floor((b - a - ZEBRA_W) / p)) + 1
        first = (a + b) / 2 - (n - 1) * p / 2
    else:
        first = phase - np.floor((phase - a - ZEBRA_W / 2) / p) * p
    out = []
    t = first
    while t + ZEBRA_W / 2 <= b + 1e-6:
        if t - ZEBRA_W / 2 >= a - 1e-6:
            out.append(rect_poly(c + cross * t, along, bar_len, ZEBRA_W))
        t += p
    return out


def clean_polygons(d, carriage=None, net=None, painted=None):
    """The other paint: crossings rebuilt, strips as rectangles, arrows and letters kept, blobs left out.
    carriage: the carriageways (Carriage) to span the crossings; painted: points (n, 2) of the paint
    built elsewhere (the Street View route, with its own crossings): no OSM crossing is added within
    PAINTED_CLEAR m of them."""
    polys = []
    for p in d["polygons"]:
        g = shapely.Polygon(p["ring"])
        if not g.is_valid:
            g = shapely.make_valid(g)
        for q in getattr(g, "geoms", [g]):
            if isinstance(q, shapely.Polygon) and q.area >= 0.06:
                polys.append((p["color"], q))
    out, stats = [], {"crossings": 0, "crossings_osm": 0, "strips": 0, "marks": 0, "dropped": 0}
    yellow = [q for c, q in polys if c == "yellow"]
    white = [q for c, q in polys if c == "white"]
    # yellow bars of crossings: strips ZEBRA_L long about, grouped by their neighbours
    bars, other_y = [], []
    for q in yellow:
        c, ax, L, S = rect_of(q)
        fill = q.area / max(L * S, 1e-6)
        if 0.8 <= L <= 4.8 and 0.15 <= S <= 0.8 and fill >= 0.45:
            bars.append((q, c, ax, L, S))
        else:
            other_y.append(q)
    used = np.zeros(len(bars), bool)
    zebras = []
    if bars:
        C = np.array([b[1] for b in bars])
        from scipy.spatial import cKDTree
        kd = cKDTree(C)
        for i in range(len(bars)):
            if used[i]:
                continue
            # bars of one crossing: parallel (10 deg), side by side across the road
            grp, todo = [i], [i]
            used[i] = True
            while todo:
                k = todo.pop()
                for j in kd.query_ball_point(C[k], GROUP_R):
                    if used[j]:
                        continue
                    if abs(bars[j][2] @ bars[k][2]) < np.cos(np.radians(12)):
                        continue
                    along_off = abs((C[j] - C[k]) @ bars[k][2])
                    if along_off > 1.5:
                        continue
                    used[j] = True
                    grp.append(j)
                    todo.append(j)
            ax = np.array([bars[k][2] if bars[k][2] @ bars[grp[0]][2] >= 0 else -bars[k][2] for k in grp]).mean(0)
            ax /= np.linalg.norm(ax)
            cross = np.array([-ax[1], ax[0]])
            cc = C[grp].mean(0)
            t = (C[grp] - cc) @ cross
            if len(grp) < 2 and not (net is not None and any(np.linalg.norm(x - cc) < 6 for x, _, _ in net.crossings)):
                other_y.append(bars[grp[0]][0])         # a single bar: not a crossing
                continue
            if any(z.distance(shapely.Point(cc)) < 1.5 for z in zebras):
                continue                                # part of a crossing already built
            lng = snap_value(float(np.median([bars[k][3] for k in grp])), ZEBRA_L)
            span = carriage_span(carriage, cc, cross)
            if span is None:
                span = (t.min() - ZEBRA_W / 2 - ZEBRA_EDGE, t.max() + ZEBRA_W / 2 + ZEBRA_EDGE)
            else:
                # the bars measured must lie inside it; the surveyed edge may be off by a few dm
                span = (min(span[0], t.min() - ZEBRA_W / 2 - ZEBRA_EDGE), max(span[1], t.max() + ZEBRA_W / 2 + ZEBRA_EDGE))
            phase = float(np.median(((t + ZEBRA_W) % (2 * ZEBRA_W)))) - ZEBRA_W
            rs = zebra(cc, ax, span[0], span[1], lng, phase)
            for r in rs:
                out.append({"color": "yellow", "ring": r.round(3).tolist(), "kind": "crossing"})
            if rs:
                zebras.append(shapely.MultiPolygon([shapely.Polygon(r) for r in rs]).convex_hull)
            stats["crossings"] += 1
    # marked crossings of OSM the photo does not show
    if net is not None and carriage is not None:
        have = [np.array(o["ring"]).mean(0) for o in out if o.get("kind") == "crossing"]
        have += [np.asarray(q.centroid.coords[0]) for q in yellow]
        from scipy.spatial import cKDTree
        kd = cKDTree(np.array(have)) if have else None
        pkd = cKDTree(np.asarray(painted)[:, :2]) if painted is not None and len(painted) else None
        for p, along, hw in net.crossings:
            if kd is not None and kd.query_ball_point(p, 8.0):
                continue
            if pkd is not None and pkd.query_ball_point(p, PAINTED_CLEAR):
                continue
            if not carriage.contains(p):
                continue
            cross = np.array([-along[1], along[0]])
            span = carriage_span(carriage, p, cross)
            if span is None or not 3.0 <= span[1] - span[0] <= 16.0:
                continue
            for r in zebra(p, along, span[0], span[1], 3.0 if span[1] - span[0] < 9 else 4.0):
                out.append({"color": "yellow", "ring": r.round(3).tolist(), "kind": "crossing"})
            stats["crossings_osm"] += 1
    for color, group in (("yellow", other_y), ("white", white)):
        for q in group:
            c, ax, L, S = rect_of(q)
            fill = q.area / max(L * S, 1e-6)
            if S <= 0.75 and L / max(S, 1e-6) >= 2.5 and fill >= 0.5:
                # a strip: stop / give-way lines (0.5 m), bars of hatched areas, parking lines
                w = max(0.12, min(S, 0.6))
                out.append({"color": color, "ring": rect_poly(c, ax, L, w).round(3).tolist(), "kind": "strip"})
                stats["strips"] += 1
            elif q.area >= 0.6 and 1.5 <= L <= 7.0 and S <= 2.0 and L / max(S, 1e-6) >= 1.6 and 0.2 <= fill <= 0.8:
                # arrows and letters: as traced, outline smoothed
                g = q.buffer(0.04).buffer(-0.04).simplify(0.04)
                for gg in getattr(g, "geoms", [g]):
                    if isinstance(gg, shapely.Polygon) and gg.area >= 0.06:
                        out.append({"color": color, "ring": np.asarray(gg.exterior.coords).round(3).tolist(), "kind": "mark"})
                stats["marks"] += 1
            else:
                stats["dropped"] += 1
    return out, stats


def cut_at_crossings(lines, polys):
    """Longitudinal lines stop CROSS_CLEAR m before a pedestrian crossing (they were joined across it,
    or traced through it)."""
    cr = [shapely.Polygon(p["ring"]) for p in polys if p.get("kind") == "crossing"]
    if not cr:
        return lines
    tree = shapely.STRtree(cr)
    out = []
    for ln in lines:
        runs = []
        for r in ln["runs"]:
            g = shapely.LineString(r)
            ids = tree.query(g.buffer(CROSS_CLEAR + 1.0))
            if len(ids):
                g = g.difference(shapely.union_all([cr[i] for i in ids]).buffer(CROSS_CLEAR, join_style="mitre"))
            for q in getattr(g, "geoms", [g]):
                if isinstance(q, shapely.LineString) and q.length >= 0.5:
                    runs.append(np.asarray(q.coords).round(3).tolist())
        if runs:
            ln = dict(ln)
            ln["runs"] = runs
            ln.pop("runs_u", None)
            out.append(ln)
    return out


def snap_value(v, values):
    return min(values, key=lambda s: abs(v - s))


def clean(d, carriage=None, ways=None, nodes=None, drive=None, painted=None):
    """The network paint `d` (network_markings.json) redrawn as described above. carriage: the
    carriageways (Carriage: the top faces of the level's road meshes); ways, nodes: OSM
    (osm.load()) for the junctions and the marked crossings; painted: points of the paint built elsewhere."""
    net = Network(ways, nodes, drive) if ways is not None else None
    lines = clean_lines(d, net)
    polys, st = clean_polygons(d, carriage, net, painted)
    lines = cut_at_crossings(lines, polys)
    st["lines_in"], st["lines_out"] = len(d["lines"]), len(lines)
    st["polygons_in"] = len(d["polygons"])
    return {"lines": lines, "polygons": polys, "hidden": d.get("hidden", []), "segments": d.get("segments", {}),
            "clean": st}
