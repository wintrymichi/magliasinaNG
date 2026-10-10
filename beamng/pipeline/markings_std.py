"""Road paint of the network laid from a library of standard pieces along the road axis (v2.8).

Up to v2.7 the paint of the network was the orthophoto's tracing, cleaned (markings_clean.py): every
line followed its own traced track, so it wobbled against the road and the dashes of the two sides of a
line did not match; a line traced twice ran as two staggered lines; crossings, stop lines and bars took
the angle of their traced blobs; arrows and letters were the traced blobs themselves. In the game it
looked crooked and drawn by a machine.

Now the orthophoto only says WHAT is painted WHERE along a road; the paint is laid from the pieces of
dati/road_marking_templates.json (the dataset of the Swiss markings, VSS SN 640 850 / 640 851 /
640 877 shapes in metres) along the axis of the road network (the AI roads of the level, the swissTLM3D
and OSM centre lines with their widths):
1. lines: every cleaned line is cut into the stretches along each road it follows; on one road the
   lines of one colour at the same offset (within SLOT m) are one line, at one offset from the axis
   (on the axis when within AXIS m of it) or, near the edge, at one inset from the edge (it follows
   the road's width); dashed stretches get one dash and one period of the dataset and one phase,
   solid stretches are joined across short gaps; a line is one width of the dataset;
2. pedestrian crossings: the standard crossing (bars parallel to the road, across the carriageway) at
   the measured place, square to the road;
3. stop and give-way lines, bars of hatched areas, parking lines: the standard bar widths, square to the
   road (or along it) when within SQUARE degrees, the bars of a hatched area at one angle;
4. arrows: the traced blob only chooses the arrow of the dataset (straight, left, right and their
   combinations, the way it points) that covers it best, laid in the middle of its lane; letters and
   blobs no arrow covers are left out.
The result has the format of network_markings.json, built by markings_net.py.
    python markings_std.py --templates      writes the dataset (dati/road_marking_templates.json)
"""
import json, os, sys
import numpy as np
import shapely
import shapely.affinity
from scipy.spatial import cKDTree

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                         "road_marking_templates.json")
STEP = 0.5            # m between the stations of the road axis
NEAR = 1.2            # m beyond the half width where paint still belongs to a road
ALIGN = 0.9           # |cos| between the paint and the road
SLOT = 0.45           # m, lines of one road and colour this close across are one line
AXIS = 0.30           # m, a line this close to the axis lies on it
EDGE = 1.0            # m, a line this close inside the edge keeps its inset from the edge
GAP_SOLID = 4.0       # m, gaps of a solid line closed
GAP_DASHED = 30.0     # m, dashes this far apart are one dashed stretch
MIN_PIECE = 0.6       # m
SQUARE = 15.0         # deg, a bar this close to square (or along) the road is laid square (along)
HATCH_R = 6.0         # m, bars of one hatched area
ARROW_IOU = 0.42      # least overlap of an arrow of the dataset with the traced blob
LANE_SNAP = 0.9       # m, an arrow this close to the middle of a lane is laid there


# ---------------------------------------------------------------------- the dataset
def _arrow_shapes(length=5.0, shaft=0.25, head_len=1.4, head_w=0.80, arm=1.45, arm_at=2.2):
    """Swiss direction arrows (x forward from the tail at 0, y to the left), as shapely polygons."""
    def head(tip, d):
        d = np.asarray(d, float) / np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        base = np.asarray(tip) - d * head_len
        return shapely.Polygon([base + n * head_w / 2, tip, base - n * head_w / 2])

    def bar(a, b, w=shaft):
        return shapely.LineString([a, b]).buffer(w / 2, cap_style="flat", join_style="mitre")

    straight = shapely.union_all([bar((0, 0), (length - head_len + 0.05, 0)), head((length, 0), (1, 0))])
    out = {"straight": straight}
    for side, sgn in (("left", 1), ("right", -1)):
        d = np.array([1.0, sgn * 1.0]) / np.sqrt(2)
        a = np.array([arm_at, 0.0])
        tip = a + d * (arm + head_len)
        turn = shapely.union_all([bar((0, 0), (arm_at + 0.05, 0)), bar(a, a + d * (arm + 0.05)), head(tip, d)])
        out[side] = turn
        out[f"straight_{side}"] = shapely.union_all([straight, bar(a, a + d * (arm + 0.05)), head(tip, d)])
    out["left_right"] = shapely.union_all([out["left"], out["right"]])
    return out


def write_templates(path=TEMPLATES):
    """The dataset of the standard pieces: arrows as polygons, the rest as their measures."""
    arrows = {k: np.asarray(g.simplify(0.005).exterior.coords).round(3).tolist() for k, g in _arrow_shapes().items()}
    data = {
        "_about": "Swiss road markings (VSS SN 640 850, 640 851, 640 877) as standard pieces in metres, laid by "
                  "markings_std.py along the road axis. Arrows: x forward from the tail, y to the left, 5 m long "
                  "(scaled to the lengths of 'arrow_lengths').",
        "line_widths": [0.10, 0.15, 0.20, 0.30],
        "dashed": {"dash": [1.5, 2.0, 3.0, 4.0, 6.0], "period": [3.0, 4.5, 6.0, 8.0, 9.0, 12.0, 18.0]},
        "crossing": {"bar_width": 0.5, "gap": 0.5, "bar_lengths": [2.5, 3.0, 4.0], "edge": 0.3, "color": "yellow"},
        "bar_widths": [0.15, 0.30, 0.50],
        "arrow_lengths": [3.0, 5.0, 7.5],
        "arrows": arrows,
    }
    json.dump(data, open(path, "w"), indent=1)
    return data


def templates():
    if not os.path.exists(TEMPLATES):
        return write_templates()
    return json.load(open(TEMPLATES))


def snap_to(v, values):
    return min(values, key=lambda s: abs(v - s))


# ---------------------------------------------------------------------- the road axis
def _chaikin(P, n=2):
    for _ in range(n):
        if len(P) < 3:
            return P
        Q = np.empty((2 * (len(P) - 1), P.shape[1]))
        Q[0::2] = 0.75 * P[:-1] + 0.25 * P[1:]
        Q[1::2] = 0.25 * P[:-1] + 0.75 * P[1:]
        P = np.vstack([P[:1], Q, P[-1:]])
    return P


class Roads:
    """The axis of the AI roads (DecalRoad nodes x, y, z, width): stations every STEP m with their
    direction, left normal and width."""

    def __init__(self, roads, min_drivability=0.3):
        X, T, W, S, R = [], [], [], [], []
        self.start = []
        k = 0
        for o in roads:
            if o.get("class", "DecalRoad") != "DecalRoad" or float(o.get("drivability", 1)) < min_drivability:
                continue
            N = np.asarray(o["nodes"], np.float64)
            if len(N) < 2:
                continue
            keep = np.r_[True, np.hypot(*np.diff(N[:, :2], axis=0).T) > 0.05]
            N = _chaikin(N[keep][:, [0, 1, 3]])
            u = np.r_[0, np.cumsum(np.hypot(*np.diff(N[:, :2], axis=0).T))]
            if u[-1] < 2 * STEP:
                continue
            s = np.arange(0, u[-1] + 1e-9, STEP)
            x, y, w = (np.interp(s, u, N[:, i]) for i in range(3))
            P = np.column_stack([x, y])
            d = np.gradient(P, axis=0)
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            self.start.append(len(np.concatenate(X)) if X else 0)
            X.append(P); T.append(d); W.append(w); S.append(s); R.append(np.full(len(s), k))
            k += 1
        self.X, self.T = np.concatenate(X), np.concatenate(T)
        self.W, self.S, self.R = np.concatenate(W), np.concatenate(S), np.concatenate(R)
        self.N = np.column_stack([-self.T[:, 1], self.T[:, 0]])
        self.start = np.asarray(self.start + [len(self.X)])
        self.kd = cKDTree(self.X)

    def __len__(self):
        return len(self.start) - 1

    def locate(self, P, D=None, r=8.0):
        """Road, station and offset of the points P (n, 2) (with directions D (n, 2), either way):
        (rid, idx, s, t) arrays, rid -1 where no road holds the point."""
        P = np.atleast_2d(np.asarray(P, np.float64))
        dist, idx = self.kd.query(P, k=12, distance_upper_bound=r)
        out = np.full((len(P), 4), np.nan)
        out[:, 0] = -1
        for i in range(len(P)):
            best = None
            for dd, j in zip(dist[i], idx[i]):
                if not np.isfinite(dd):
                    break
                v = P[i] - self.X[j]
                along = v @ self.T[j]
                if abs(along) > STEP:                       # not the foot of the perpendicular
                    continue
                t = v @ self.N[j]
                if abs(t) > self.W[j] / 2 + NEAR:
                    continue
                if D is not None and abs(np.asarray(D[i]) @ self.T[j]) < ALIGN:
                    continue
                if best is None or abs(t) < abs(best[3]):
                    best = (self.R[j], j, self.S[j] + along, t)
            if best is not None:
                out[i] = best
        return out[:, 0].astype(int), out[:, 1], out[:, 2], out[:, 3]

    def frame(self, rid, s):
        """Point, direction, left normal and width of road rid at stations s."""
        a, b = self.start[rid], self.start[rid + 1]
        s = np.clip(np.asarray(s, np.float64), self.S[a], self.S[b - 1])
        f = (s - self.S[a]) / STEP
        i0 = np.clip(np.floor(f).astype(int), 0, b - a - 2)
        w = (f - i0)[..., None]
        X = self.X[a + i0] * (1 - w) + self.X[a + i0 + 1] * w
        T = self.T[a + i0] * (1 - w) + self.T[a + i0 + 1] * w
        T /= np.maximum(np.linalg.norm(T, axis=-1, keepdims=True), 1e-9)
        Wd = self.W[a + i0] * (1 - w[..., 0]) + self.W[a + i0 + 1] * w[..., 0]
        return X, T, np.stack([-T[..., 1], T[..., 0]], -1), Wd

    def length(self, rid):
        return float(self.S[self.start[rid + 1] - 1])


# ---------------------------------------------------------------------- lines
def _merge(iv, gap):
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _densify(P, step=1.0):
    P = np.asarray(P, np.float64)
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(int(np.ceil(np.hypot(*(b - a)) / step)), 1)
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.concatenate(out)


def _relay(dashes, tpl):
    """One dash length, one period of the dataset and one phase for the dashes [(s0, s1)] of a stretch."""
    st = np.array([a for a, b in dashes])
    ln = np.array([b - a for a, b in dashes])
    steps = np.diff(st)
    if len(steps) == 0:
        return dashes
    base = float(np.median(steps[steps <= np.percentile(steps, 60) * 1.2]))
    k = np.round((st - st[0]) / max(base, 1e-6))
    period = float(np.polyfit(k, st, 1)[0]) if k[-1] > 0 else base
    p = snap_to(period, tpl["dashed"]["period"])
    d = snap_to(float(np.median(ln)), tpl["dashed"]["dash"])
    if d >= 0.8 * p or abs(p - period) > 0.25 * p:
        return None
    k = np.round((st - st[0]) / p)
    s0 = float(np.median((st + ln / 2) - k * p)) - d / 2
    first = s0 + np.floor((st.min() - 0.2 * p - s0) / p) * p
    if first + d < st.min():
        first += p
    out, a = [], first
    while a <= (st + ln).max() - 0.5 * d:
        out.append((a, a + d))
        a += p
    return out


def road_lanes(roads, ways, drive):
    """Lanes and one-way of every road from the drivable OSM way along it (None where OSM has no lanes):
    (lanes (n,) int, 0 unknown; oneway (n,) bool)."""
    P, D, tags = [], [], []
    for w in ways:
        if w["tags"].get("highway") not in drive or len(w["xy"]) < 2:
            continue
        Q = _densify(np.asarray(w["xy"], np.float64)[:, :2], 2.0)
        d = np.gradient(Q, axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        P.append(Q); D.append(d); tags += [w["tags"]] * len(Q)
    lanes = np.zeros(len(roads), int)
    oneway = np.zeros(len(roads), bool)
    if not P:
        return lanes, oneway
    P, D = np.concatenate(P), np.concatenate(D)
    kd = cKDTree(P)
    for r in range(len(roads)):
        a, b = roads.start[r], roads.start[r + 1]
        votes = {}
        for j in np.linspace(a, b - 1, 7).astype(int):
            for k in kd.query_ball_point(roads.X[j], 6.0):
                if abs(D[k] @ roads.T[j]) >= 0.8:
                    t = tags[k]
                    key = (t.get("lanes"), t.get("oneway") in ("yes", "-1") or t.get("highway") in ("motorway", "motorway_link"))
                    votes[key] = votes.get(key, 0) + 1
                    break
        if votes:
            (ln, ow), _ = max(votes.items(), key=lambda kv: kv[1])
            try:
                lanes[r] = int(ln) if ln else 0
            except ValueError:
                lanes[r] = 0
            oneway[r] = ow
    return lanes, oneway


def _lane_model(slots, W, lanes, oneway):
    """Number of lanes of a road that explains its interior lines best: (n, positions as fractions of W
    from the left edge). slots: [(t, length)] of the white interior lines."""
    default = 1 if oneway else 2
    cands = [lanes] if lanes > 0 else sorted({default, 2, 3, 4} - ({1} if not oneway else set()))
    best = None
    for n in cands:
        pos = [(-0.5 + i / n) * W for i in range(1, n)]
        if not pos:
            score = 0.0
        else:
            tol = max(0.5, 0.12 * W / n)
            score = sum(L for t, L in slots if min(abs(t - p) for p in pos) <= tol)
        score -= 25.0 * abs(n - default) * (lanes == 0)
        if best is None or score > best[0]:
            best = (score, n)
    n = best[1]
    return n, [(-0.5 + i / n) for i in range(1, n)]


def lay_lines(lines, roads, tpl, stats, lanes=None, oneway=None):
    """The cleaned lines laid along the road axis: [{"color", "width", "pattern", "runs"}]. On every road
    the lines inside the carriageway go on the lane lines of its lanes (OSM, or the count that explains
    the traced lines best), the others keep their inset from the edge; paint at neither is left out."""
    pieces = {}                       # rid -> [(t, width, kind, s0, s1, W, color)]
    for ln in lines:
        width = snap_to(float(ln.get("width", 0.12)), tpl["line_widths"])
        dashed_line = ln.get("pattern") in ("dashed", "mixed")
        for run in ln["runs"]:
            P = _densify(run, 0.5)
            if len(P) < 2:
                continue
            D = np.gradient(P, axis=0)
            D /= np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-9)
            rid, _, s, t = roads.locate(P, D)
            run_len = float(np.hypot(*np.diff(P, axis=0).T).sum())
            kind = "dash" if dashed_line and run_len <= 7.5 else "solid"
            for r in np.unique(rid[rid >= 0]):
                m = rid == r
                if m.sum() < 2:
                    continue
                pieces.setdefault(int(r), []).append(
                    (float(np.median(t[m])), width, kind, float(s[m].min()), float(s[m].max()),
                     float(np.median(roads.frame(int(r), s[m])[3])), ln["color"]))
            stats["paint_off_axis"] += int((rid < 0).sum())
    out = []
    for rid, pcs in pieces.items():
        W = float(np.median([q[5] for q in pcs]))
        # slots: pieces of one colour at the same offset
        slots = []
        for color in ("white", "yellow"):
            cp = sorted((q for q in pcs if q[6] == color), key=lambda q: q[0])
            cur = []
            for q in cp:
                if cur and q[0] - np.median([x[0] for x in cur]) > SLOT:
                    slots.append(cur)
                    cur = []
                cur.append(q)
            if cur:
                slots.append(cur)
        info = []
        for sl in slots:
            L = np.array([q[4] - q[3] for q in sl]) + 0.1
            t = np.array([q[0] for q in sl])
            o = np.argsort(t)
            tm = float(t[o][np.searchsorted(np.cumsum(L[o]), L.sum() / 2)])
            info.append((tm, float(L.sum()), W / 2 - abs(tm) <= EDGE and abs(tm) > AXIS, sl[0][6]))
        n, frac = _lane_model([(tm, L) for tm, L, edge, c in info if not edge and c == "white"], W,
                              int(lanes[rid]) if lanes is not None else 0, bool(oneway[rid]) if oneway is not None else False)
        # each slot to its place: an edge (inset), a lane line, or nowhere
        placed = {}
        for sl, (tm, L, edge, color) in zip(slots, info):
            if edge:
                key = ("edge", color, int(np.sign(tm)), round((W / 2 - abs(tm)) / 0.5))
            else:
                if not frac or color != "white":
                    stats["lines_dropped"] += 1
                    continue
                pos = [f * W for f in frac]
                k = int(np.argmin([abs(tm - p) for p in pos]))
                if abs(tm - pos[k]) > max(0.5, 0.12 * W / n):
                    stats["lines_dropped"] += 1
                    continue
                key = ("lane", color, k)
            placed.setdefault(key, []).append((sl, tm))
        for key, group in placed.items():
            sl = [q for g, _ in group for q in g]
            color = key[1]
            if key[0] == "edge":
                sgn = key[2]
                inset = float(np.median([W / 2 - abs(tm) for _, tm in group]))
                off = lambda s, rid=rid, sgn=sgn, inset=inset: sgn * np.maximum(roads.frame(rid, s)[3] / 2 - inset, 0.3)
                tm = sgn * (W / 2 - inset)
            else:
                f = frac[key[2]]
                off = lambda s, rid=rid, f=f: f * roads.frame(rid, s)[3]
                tm = f * W
            width = float(np.median([q[1] for q in sl]))
            dashes = sorted((q[3], q[4]) for q in sl if q[2] == "dash")
            solids = _merge(sorted((q[3], q[4]) for q in sl if q[2] == "solid"), GAP_SOLID)
            iv = []
            groups, g = [], []
            for a, b in _merge(dashes, 0.0):
                if g and a - g[-1][1] > GAP_DASHED:
                    groups.append(g)
                    g = []
                g.append((a, b))
            if g:
                groups.append(g)
            for g in groups:
                lay = _relay(g, tpl) if len(g) >= 3 else None
                if lay is None:
                    iv += g
                    stats["dashes_kept"] += len(g)
                else:
                    lo, hi = lay[0][0], lay[-1][1]
                    solids = [(a, b) for a, b in solids if b < lo or a > hi]
                    iv += lay
                    stats["dashed_stretches"] += 1
            iv += solids
            iv = [(max(a, 0.0), min(b, roads.length(rid))) for a, b in iv]
            iv = [(a, b) for a, b in _merge(sorted(iv), 0.0) if b - a >= MIN_PIECE]
            if not iv:
                continue
            runs = []
            for a, b in iv:
                s = np.r_[np.arange(a, b, 1.0), b]
                X, T, Nn, _ = roads.frame(rid, s)
                runs.append((X + Nn * off(s)[:, None]).round(3).tolist())
            pattern = "dashed" if dashes and not solids else ("solid" if not dashes else "mixed")
            out.append({"color": color, "width": width, "pattern": pattern, "runs": runs, "road": rid,
                        "t": round(float(tm), 2), "lanes": n})
            stats["lines"] += 1
    return out


# ---------------------------------------------------------------------- crossings, bars, arrows
def _rect(c, ax, length, width):
    n = np.array([-ax[1], ax[0]])
    h, w = ax * length / 2, n * width / 2
    return np.array([c - h - w, c + h - w, c + h + w, c - h + w, c - h - w])


def _rect_of(q):
    ex = np.asarray(q.minimum_rotated_rectangle.exterior.coords)[:4]
    e1, e2 = ex[1] - ex[0], ex[2] - ex[1]
    l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
    if l1 >= l2:
        return ex.mean(0), e1 / max(l1, 1e-9), l1, l2
    return ex.mean(0), e2 / max(l2, 1e-9), l2, l1


def _rot(ax, deg):
    a = np.radians(deg)
    return np.array([np.cos(a) * ax[0] - np.sin(a) * ax[1], np.sin(a) * ax[0] + np.cos(a) * ax[1]])


def lay_crossings(polys, roads, tpl, carriage, stats):
    cr = tpl["crossing"]
    bars = [(p, shapely.Polygon(p["ring"])) for p in polys if p.get("kind") == "crossing"]
    if not bars:
        return []
    C = np.array([g.centroid.coords[0] for _, g in bars])
    kd = cKDTree(C)
    seen = np.zeros(len(C), bool)
    out = []
    for i in range(len(C)):
        if seen[i]:
            continue
        grp = sorted(set(j for j in kd.query_ball_point(C[i], 6.0) if not seen[j]))
        todo = list(grp)
        while todo:
            j = todo.pop()
            for k in kd.query_ball_point(C[j], 1.6):
                if not seen[k] and k not in grp:
                    grp.append(k); todo.append(k)
        seen[grp] = True
        c = C[grp].mean(0)
        rid, _, s, t = roads.locate(c[None])
        if rid[0] < 0:
            out += [bars[k][0] for k in grp]                  # off the axis: as it was
            stats["crossings_kept"] += 1
            continue
        X, T, Nn, Wd = roads.frame(rid[0], s[0])
        lens = [_rect_of(bars[k][1])[2] for k in grp]
        bar_len = snap_to(float(np.median(lens)), cr["bar_lengths"])
        span = carriage.span(X, Nn) if carriage is not None else None
        if span is None or not 2.5 <= span[1] - span[0] <= 2 * Wd + 2:
            span = (-Wd / 2, Wd / 2)
        a, b = span[0] + cr["edge"], span[1] - cr["edge"]
        p = cr["bar_width"] + cr["gap"]
        n = int(np.floor((b - a - cr["bar_width"]) / p)) + 1
        if n < 2:
            continue
        first = (a + b) / 2 - (n - 1) * p / 2
        cc = X + T * float((c - X) @ T)
        for q in range(n):
            out.append({"color": cr["color"], "ring": _rect(cc + Nn * (first + q * p), T, bar_len, cr["bar_width"]).round(3).tolist(),
                         "kind": "crossing"})
        stats["crossings"] += 1
    return out


def lay_strips(polys, roads, tpl, stats, lines=()):
    """Stop and give-way lines, bars of hatched areas, parking lines: the standard widths, square to the
    road or along it; a bar along the road on a laid line is a piece of that line (left out)."""
    strips = [p for p in polys if p.get("kind") == "strip"]
    if not strips:
        return []
    on_road = {}
    for ln in lines:
        on_road.setdefault(ln["road"], []).append(ln["t"])
    rec = []
    for p in strips:
        c, ax, L, S = _rect_of(shapely.Polygon(p["ring"]))
        rec.append([c, ax, L, S, p["color"]])
    C = np.array([r[0] for r in rec])
    rid, _, s, tt = roads.locate(C)
    out = []
    ang = np.full(len(rec), np.nan)
    for k, r in enumerate(rec):
        if rid[k] < 0:
            continue
        _, T, _, _ = roads.frame(rid[k], s[k])
        a = np.degrees(np.arctan2(T[0] * r[1][1] - T[1] * r[1][0], T @ r[1])) % 180.0
        ang[k] = a
    hatch = []
    for k, r in enumerate(rec):
        c, ax, L, S, color = r
        w = snap_to(S, tpl["bar_widths"])
        if not np.isfinite(ang[k]) or L < 1.0:
            stats["strips_dropped"] += 1                     # off the roads, or a fragment
            continue
        _, T, _, _ = roads.frame(rid[k], s[k])
        a = ang[k]
        if abs(a - 90) <= SQUARE:
            a2 = 90.0                                        # a stop or give-way line
        elif min(a, 180 - a) <= SQUARE:
            # along the road: a piece of a line (laid already) or a traced kerb or gutter
            stats["strips_on_lines" if any(abs(tt[k] - t0) <= 0.45 for t0 in on_road.get(int(rid[k]), ()))
                  else "strips_dropped"] += 1
            continue
        else:
            hatch.append(k)                                  # a bar of a hatched area: laid with its area below
            continue
        ax = _rot(T, a2)
        stats["strips_squared"] += 1
        out.append({"color": color, "ring": _rect(c, ax, L, w).round(3).tolist(), "kind": "strip"})
    # hatched areas: bars of one colour and angle (10 deg) within HATCH_R m of each other, three at least,
    # laid again at one length, width, angle and spacing along a straight line through their middles
    hatch = np.array(hatch, int)
    seen = np.zeros(len(hatch), bool)
    if len(hatch):
        kd = cKDTree(C[hatch])
    for i in range(len(hatch)):
        if seen[i]:
            continue
        grp, todo = [i], [i]
        seen[i] = True
        while todo:
            j = todo.pop()
            for q in kd.query_ball_point(C[hatch[j]], HATCH_R):
                a, b = ang[hatch[q]], ang[hatch[j]]
                if not seen[q] and rid[hatch[q]] == rid[hatch[i]] and rec[hatch[q]][4] == rec[hatch[i]][4] \
                        and min(abs(a - b), 180 - abs(a - b)) <= 10.0:
                    seen[q] = True
                    grp.append(q)
                    todo.append(q)
        ks = hatch[grp]
        if len(ks) < 3:
            stats["strips_dropped"] += len(ks)
            continue
        r0 = int(rid[ks[0]])
        ss, ts = s[ks], tt[ks]
        o = np.argsort(ss)
        ss, ts = ss[o], ts[o]
        step = float(np.median(np.diff(ss)))
        if step < 0.8:
            stats["strips_dropped"] += len(ks)
            continue
        n = int(round((ss[-1] - ss[0]) / step)) + 1
        fit = np.polyfit(ss, ts, 1)
        a2 = round(float(np.median(ang[ks])) / 7.5) * 7.5
        L = float(np.median([rec[k][2] for k in ks]))
        w = snap_to(float(np.median([rec[k][3] for k in ks])), tpl["bar_widths"])
        for q in range(n):
            sq = ss[0] + q * (ss[-1] - ss[0]) / max(n - 1, 1)
            X, T, Nn, _ = roads.frame(r0, sq)
            cq = X + Nn * np.polyval(fit, sq)
            out.append({"color": rec[ks[0]][4], "ring": _rect(cq, _rot(T, a2), L, w).round(3).tolist(), "kind": "hatch"})
        stats["hatched_areas"] += 1
    return out


def _arrow_polys(tpl):
    return {k: shapely.Polygon(v) for k, v in tpl["arrows"].items()}


def lay_arrows(polys, roads, tpl, stats):
    marks = [p for p in polys if p.get("kind") == "mark"]
    A = _arrow_polys(tpl)
    out = []
    for p in marks:
        q = shapely.Polygon(p["ring"])
        if not q.is_valid:
            q = shapely.make_valid(q)
        c = np.asarray(q.centroid.coords[0])
        rid, _, s, t = roads.locate(c[None])
        if rid[0] < 0 or p["color"] != "white":
            stats["marks_dropped"] += 1
            continue
        X, T, Nn, Wd = roads.frame(rid[0], s[0])
        # the blob in the road's frame (x along the road, y to the left), centred
        R = np.asarray(q.exterior.coords if hasattr(q, "exterior") else q.convex_hull.exterior.coords) - c
        loc = shapely.Polygon(np.column_stack([R @ T, R @ Nn]))
        if not loc.is_valid:
            loc = loc.buffer(0)
        Lb = loc.bounds[2] - loc.bounds[0]
        if loc.area > 0.8 * loc.convex_hull.area:            # a convex blob (a triangle, a car) is no arrow
            stats["marks_dropped"] += 1
            continue
        best = (0.0, None, None, None)
        for L in tpl["arrow_lengths"]:
            if not 0.6 * L <= Lb <= 1.35 * L:
                continue
            for name, g in A.items():
                g = shapely.affinity.scale(g, L / 5.0, L / 5.0, origin=(0, 0))
                for sgn in (1, -1):
                    h = shapely.affinity.scale(g, sgn, sgn, origin=(0, 0)) if sgn < 0 else g
                    h = shapely.affinity.translate(h, -h.centroid.x, -h.centroid.y)
                    iou = h.intersection(loc).area / max(h.union(loc).area, 1e-9)
                    if iou > best[0]:
                        best = (iou, name, sgn, L)
        if best[0] < ARROW_IOU:
            stats["marks_dropped"] += 1
            continue
        _, name, sgn, L = best
        g = shapely.affinity.scale(A[name], L / 5.0, L / 5.0, origin=(0, 0))
        if sgn < 0:
            g = shapely.affinity.scale(g, -1, -1, origin=(0, 0))
        g = shapely.affinity.translate(g, -g.centroid.x, -g.centroid.y)
        # in the middle of its lane: a quarter of the width either side of the axis
        tt = float(t[0])
        for lane in (-Wd / 4, Wd / 4, 0.0):
            if abs(tt - lane) <= LANE_SNAP:
                tt = lane
                break
        base = X + T * float((c - X) @ T) + Nn * tt
        P = np.asarray(g.exterior.coords)
        W = base + P[:, :1] * T + P[:, 1:2] * Nn
        out.append({"color": "white", "ring": W.round(3).tolist(), "kind": "arrow", "arrow": name})
        stats["arrows"] += 1
    return out


def standard(d, roads, carriage=None, ways=None, drive=None):
    """The cleaned paint d (markings_clean.clean) laid from the standard pieces along `roads` (Roads);
    ways, drive: the OSM ways (osm.load) for the lanes."""
    tpl = templates()
    stats = {k: 0 for k in ("lines", "dashed_stretches", "dashes_kept", "paint_off_axis", "crossings", "crossings_kept",
                            "strips_squared", "strips_on_lines", "strips_dropped", "hatched_areas", "arrows", "marks_dropped", "lines_dropped")}
    lanes, oneway = road_lanes(roads, ways, drive) if ways is not None else (None, None)
    lines = lay_lines(d["lines"], roads, tpl, stats, lanes, oneway)
    polys = lay_crossings(d["polygons"], roads, tpl, carriage, stats)
    polys += lay_strips(d["polygons"], roads, tpl, stats, lines)
    polys += lay_arrows(d["polygons"], roads, tpl, stats)
    import markings_clean
    lines = markings_clean.cut_at_crossings(lines, polys)
    out = dict(d)
    out["lines"], out["polygons"] = lines, polys
    out["standard"] = stats
    return out


if __name__ == "__main__":
    if "--templates" in sys.argv:
        t = write_templates()
        print("written", TEMPLATES, len(t["arrows"]), "arrows")
