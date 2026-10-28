"""Guardrails along the measured polylines (work/guardrails_final.json) and the ones seen in the panoramas.

v2.8: the rails are the guard rail modules of the game's own Italy level (italy_guardrails_basic: a 3 m W-beam
on its posts, with its collision mesh), as Italy places them: forest items every MODULE_STEP m along the line,
the beam towards the carriageway, pitched with the road, an end piece flared away from the road at both ends of
a run (italy_guardrails_basic_end_cw before the first module, _end_ccw after the last). The models are referred
to in /levels/italy/, not copied; the definitions of their materials that only Italy has are copied into the
level (dati/italy_guardrail_materials.json). Up to v2.7 the rails were drawn here (the A-profile swept along the
line, C-posts every 2 m) with the visible mesh as collision: a car caught on the thin beam and its posts.
rail() still draws the rails of the fences (fences.py).
The foot of the rail is re-based on the road surface of roadheight.py as guardrails2.py does: the ground, but
never lower than the road edge next to it minus 0.1 m (rails on valley-side walls and on the bridge stand at
road level).
"""
import json, os
import numpy as np
from config import WORK, ZONE
import bng

# (depth towards the road, height below the top) of the rail face, top -> bottom
PROFILE = np.array([[0.00, 0.00], [0.05, 0.035], [0.08, 0.07], [0.04, 0.155], [0.08, 0.24], [0.05, 0.275],
                    [0.00, 0.31]])
POST_W, POST_D, POST_STEP = 0.10, 0.06, 2.0


def resample(P, step=0.5):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    s = np.arange(0, d[-1] + 1e-6, step)
    return np.column_stack([np.interp(s, d, P[:, k]) for k in range(P.shape[1])]), s


def rail(mb, P, side):
    """P: (n, 4) x, y, z_ground, top height; side +1 = left of travel (road to the right)."""
    P, s = resample(P)
    if len(P) < 2:
        return
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nl = np.column_stack([-T[:, 1], T[:, 0]])
    to_road = -side * Nl                                    # horizontal unit vector towards the road
    top = P[:, 2] + P[:, 3]
    rings = []
    for d, dz in PROFILE:
        rings.append(np.column_stack([P[:, :2] + to_road * d, top - dz]))
    rings = np.array(rings)                                 # (k, n, 3)
    k, n = rings.shape[:2]
    tris = []
    for a in range(k - 1):
        A0, A1 = rings[a, :-1], rings[a, 1:]
        B0, B1 = rings[a + 1, :-1], rings[a + 1, 1:]
        tris.append(np.stack([A0, B0, B1, A0, B1, A1], 1).reshape(-1, 3))
    # back plate (flat) so the rail is closed from behind
    back_top, back_bot = rings[0], rings[-1]
    tris.append(np.stack([back_top[1:], back_bot[1:], back_bot[:-1], back_top[1:], back_bot[:-1], back_top[:-1]],
                         1).reshape(-1, 3))
    V = np.concatenate(tris)
    mb.add("mp_guardrail", V, uvs=np.column_stack([V[:, 0] + V[:, 1], V[:, 2]]) / 2.0,
           normals=bng.flat_normals_soup(V))
    # posts (down into the ground behind the rail, where a fifth column gives its height)
    for sp in np.arange(0.5, s[-1] - 0.2, POST_STEP):
        q = int(np.clip(np.searchsorted(s, sp), 0, n - 1))
        c = P[q, :2] - to_road[q] * 0.12                     # behind the rail (spacer)
        t = T[q]; nn = to_road[q]
        z0, z1 = min(P[q, 2], P[q, 4] if P.shape[1] > 4 else P[q, 2]) - 0.3, top[q] - 0.02
        corners = [c + t * POST_W / 2 + nn * POST_D / 2, c - t * POST_W / 2 + nn * POST_D / 2,
                   c - t * POST_W / 2 - nn * POST_D / 2, c + t * POST_W / 2 - nn * POST_D / 2]
        box = []
        for a in range(4):
            p0, p1 = corners[a], corners[(a + 1) % 4]
            q0b, q1b = np.r_[p0, z0], np.r_[p1, z0]
            q0t, q1t = np.r_[p0, z1], np.r_[p1, z1]
            box += [q0t, q0b, q1b, q0t, q1b, q1t]
        box += [np.r_[corners[0], z1], np.r_[corners[1], z1], np.r_[corners[2], z1],
                np.r_[corners[0], z1], np.r_[corners[2], z1], np.r_[corners[3], z1]]
        box = np.array(box)
        mb.add("mp_guardrail_post", box, uvs=np.column_stack([box[:, 0] + box[:, 1], box[:, 2]]),
               normals=bng.flat_normals_soup(box))


def foot_fn():
    """Foot of a rail: max(DTM, road surface continued to the rail - 0.1 m)."""
    from geo import Grid
    import roadheight
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    S = roadheight.load()

    def fn(x, y):
        return np.maximum(dtm.sample(x, y), S.height(x, y) - 0.1)
    return fn


EDGE_IN, EDGE_SEARCH, EDGE_OUT = 1.5, 3.0, 0.3     # m: search the road's edge from inside to outside, rail beyond it
SMOOTH_LINE = 9.0        # m: the line of a rail smoothed over this length before it goes to the edge
SMOOTH_E = 10.0          # m: its distance from the road's edge smoothed over this length
SMOOTH_Z = 6.0           # m: its foot smoothed over this length
JOIN_GAP = 12.0          # m: two runs of the panoramas on one side of a road this far apart, in line, are one rail
GAP_CROSS = 1.0          # m beyond the half width of a line that crosses a rail: the rail is open there
MIN_PIECE = 4.0          # m, shorter pieces of a rail cut at a crossing are dropped
SV_RUNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "guardrails_sv.json")


def sv_runs(existing):
    """Guard rails of the rest of the network seen in the Street View panoramas (sv_guardrails.py, v2.2):
    [{pts: [[x, y, z of the road edge, top height]], side}], without the ones along the rails of the
    original route (existing runs, within 1.5 m): a run is cut there into the pieces before and after (up to
    v2.8 the points left were joined, and the rail went on across the stretch along the existing one)."""
    if not os.path.exists(SV_RUNS):
        return []
    import area
    import shapely
    old = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(1.5) for r in existing
                             if len(r["pts"]) > 1]) if existing else None
    out = []
    for r in json.load(open(SV_RUNS)):
        P = np.array(r["pts"], float)
        if len(P) < 2:
            continue
        keep = ~shapely.contains_xy(old, P[:, 0], P[:, 1]) if old is not None else np.ones(len(P), bool)
        keep &= area.in_zone(P[:, 0], P[:, 1])
        for piece in pieces(keep):
            if len(piece) >= 3:
                out.append({"pts": P[piece], "side": r["side"], "seg": r.get("seg", -1), "votes": r.get("votes", 0)})
    return out


def pieces(keep):
    """The runs of consecutive True of a mask, as index arrays."""
    idx = np.flatnonzero(keep)
    return np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []


DOUBLE = 1.0             # m: a rail this close to one already laid, and running along it, is the same rail
STEP_DOUBLE = 0.5        # m between the points tested


def length(P):
    return float(np.linalg.norm(np.diff(np.asarray(P)[:, :2], axis=0), axis=1).sum()) if len(P) > 1 else 0.0


def drop_doubles(runs, laid=()):
    """The runs (in the order of trust: the first kept whole) without the stretches that lie along a rail
    already laid (laid: (k, 2, 2) segments, e.g. the modules in the level) or along a run kept before them:
    every point within DOUBLE m of such a rail, its direction within 35 degrees, goes and the run is cut there;
    pieces shorter than MIN_PIECE m are dropped. Two sources (the measured rails of the cantonal road, the
    panoramas of the rest of the network, the rails on the walls of fences.py) saw some rails twice, and the
    game had two rows of modules on one line. Returns (runs, metres dropped)."""
    import shapely
    lines = [shapely.LineString(np.asarray(s, np.float64)) for s in laid]
    tree = shapely.STRtree(lines) if lines else None
    out, dropped = [], 0.0
    for r in runs:
        P = np.asarray(r["pts"], np.float64)
        if len(P) < 2:
            continue
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
        st = np.unique(np.r_[np.arange(0, d[-1], STEP_DOUBLE), d[-1]])
        P = np.column_stack([np.interp(st, d, P[:, k]) for k in range(P.shape[1])])
        if len(P) < 2:
            continue
        keep = np.ones(len(P), bool)
        if tree is not None:
            T = np.gradient(P[:, :2], axis=0)
            T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
            pts = shapely.points(P[:, :2])
            ii, jj = tree.query(pts, predicate="dwithin", distance=DOUBLE)
            for i, j in zip(ii, jj):
                if not keep[i]:
                    continue
                g = lines[j]
                s = g.project(pts[i])
                a, b = g.interpolate(max(s - 0.5, 0.0)), g.interpolate(min(s + 0.5, g.length))
                dv = np.array([b.x - a.x, b.y - a.y])
                if abs(float(dv @ T[i])) > 0.82 * max(np.linalg.norm(dv), 1e-9):
                    keep[i] = False
        dropped += length(P) - sum(length(P[q]) for q in pieces(keep))
        new = []
        for q in pieces(keep):
            Q = P[q]
            if len(Q) >= 2 and length(Q) >= MIN_PIECE:
                new.append({**r, "pts": Q})
            else:
                dropped += length(Q)
        out += new
        if new:
            # the runs kept so far are rails laid for the ones after them
            lines += [shapely.LineString(n_["pts"][:, :2]) for n_ in new]
            tree = shapely.STRtree(lines)
    return out, dropped


def module_segments(src):
    """(k, 2, 2) the beam of every module of a level (folder or zip), end to end."""
    P, R, T = read_modules(src)
    keep = [t == MODULE for t in T]
    if not any(keep):
        return np.zeros((0, 2, 2))
    P, R = P[keep], R[keep]
    return np.stack([P[:, :2] - 1.5 * R[:, 0, :2], P[:, :2] + 1.5 * R[:, 0, :2]], 1)


def open_crossings(runs, gap=GAP_CROSS):
    """The rails cut where another line of the network (a path or a driveway leaving the road, a road
    meeting it) crosses or touches them: no rail point within its half width + gap m of a station of
    another line that is not parallel to the rail (the next piece of the same road, a road alongside), nor
    on a path running alongside. Pieces shorter than MIN_PIECE m are dropped."""
    import network
    from scipy.spatial import cKDTree
    segs, st, _ = network.load()
    xy = np.column_stack([st["x"], st["y"]])
    tree = cKDTree(xy)
    # the direction of every line at every station
    nxt = np.minimum(np.arange(len(xy)) + 1, len(xy) - 1)
    prv = np.maximum(np.arange(len(xy)) - 1, 0)
    nxt = np.where(st["seg"][nxt] == st["seg"], nxt, np.arange(len(xy)))
    prv = np.where(st["seg"][prv] == st["seg"], prv, np.arange(len(xy)))
    D = xy[nxt] - xy[prv]
    D /= np.maximum(np.linalg.norm(D, axis=1, keepdims=True), 1e-9)
    out = []
    for r in runs:
        P = r["pts"]
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        near = tree.query_ball_point(P[:, :2], 6.0)
        keep = np.ones(len(P), bool)
        for k, lst in enumerate(near):
            for j in lst:
                if st["seg"][j] == r["seg"]:
                    continue
                parallel = abs(float(D[j] @ T[k])) > 0.87
                if parallel and segs[st["seg"][j]]["kind"] != "path":
                    continue                     # the next piece of the same road, a road alongside
                # a path alongside the road: the rail may not stand on it
                reach = 0.5 * st["width"][j] + (0.3 if parallel else gap)
                if np.hypot(*(P[k, :2] - xy[j])) < reach:
                    keep[k] = False
                    break
        # continuous pieces
        idx = np.flatnonzero(keep)
        if not len(idx):
            continue
        cuts = np.flatnonzero(np.diff(idx) > 1) + 1
        for piece in np.split(idx, cuts):
            Q = P[piece]
            if len(Q) >= 2 and np.linalg.norm(np.diff(Q[:, :2], axis=0), axis=1).sum() >= MIN_PIECE:
                out.append({**r, "pts": Q})
    return out


def to_edge(P, side, road_fn, ground):
    """A rail moved onto the edge of the road as built: the line of the rail smoothed (savgol over SMOOTH_LINE m),
    then every point on the line across the road through it goes to EDGE_OUT m outside the last road face
    (searching from EDGE_IN m inside to EDGE_SEARCH m outside), that distance smoothed along the rail (a median
    over SMOOTH_E m, then a quadratic fit: a side road or a lay-by does not pull the rail in or out), its foot at
    the height of the road's edge, smoothed over SMOOTH_Z m; and the ground under it for the posts. Where no road
    face is found along a stretch the distance of the points around it holds. P: (n, 4) x, y, z, top -> (n, 5)
    x, y, z, top, ground. v3.0: up to v2.8 road_fn held only the corridor of the cantonal road, and the rails of
    the rest of the network stood where the panoramas put them, off the asphalt as built and not along it."""
    from scipy.ndimage import median_filter
    from scipy.signal import savgol_filter
    P, _ = resample(np.array(P, float), 0.5)
    n = len(P)
    if n >= 7:
        w = min(int(SMOOTH_LINE / 0.5) | 1, n if n % 2 else n - 1)
        P[:, :2] = savgol_filter(P[:, :2], w, 2, axis=0, mode="interp")
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    out = side * np.column_stack([-T[:, 1], T[:, 0]])          # away from the road
    offs = np.arange(-EDGE_IN, EDGE_SEARCH + 1e-6, 0.1)
    X = P[:, None, 0] + out[:, None, 0] * offs[None]
    Y = P[:, None, 1] + out[:, None, 1] * offs[None]
    Z = road_fn(X.ravel(), Y.ravel()).reshape(X.shape)
    # a face far under or over the rail is another road (under a bridge, above a wall), not this one's edge
    on = np.isfinite(Z) & (np.abs(Z - P[:, None, 2]) < 1.5)
    has = on.any(1)
    last = np.where(has, on.shape[1] - 1 - np.argmax(on[:, ::-1], axis=1), 0)
    e = np.where(has, offs[last], np.nan)
    ze = np.where(has, Z[np.arange(n), last], np.nan)
    if not has.any():
        e, ze = np.zeros(n), P[:, 2] + 0.03
    elif not has.all():
        i = np.arange(n)
        e = np.interp(i, i[has], e[has])
        ze = np.interp(i, i[has], ze[has])
    if n >= 5:
        e = median_filter(e, size=min(int(SMOOTH_E / 0.5) | 1, n if n % 2 else n - 1), mode="nearest")
        ze = median_filter(ze, size=5, mode="nearest")
        w = min(int(SMOOTH_E / 0.5) | 1, n if n % 2 else n - 1)
        if w >= 5:
            e = savgol_filter(e, w, 2, mode="interp")
        w = min(int(SMOOTH_Z / 0.5) | 1, n if n % 2 else n - 1)
        if w >= 5:
            ze = savgol_filter(ze, w, 2, mode="interp")
    Q = P.copy()
    Q[:, :2] = P[:, :2] + out * (e + EDGE_OUT)[:, None]
    Q[:, 2] = ze - 0.03
    g = ground(Q[:, 0], Q[:, 1])
    return np.column_stack([Q, g])


def join_runs(runs, gap=JOIN_GAP):
    """Runs of the panoramas on the same side of the same road line whose end lies within `gap` m of the start
    of the next one, in line with both, joined into one: the panoramas see a rail in pieces (a car, a bush in
    front), and the game had holes of a few metres in rails that run on. Where a road or path really crosses
    the gap, open_crossings opens it again."""
    by = {}
    for r in runs:
        by.setdefault((r.get("seg", -1), r["side"]), []).append(r)
    out = []
    for (seg, side), rs in by.items():
        if seg < 0 or len(rs) == 1:
            out += rs
            continue
        rs = [dict(r, pts=np.asarray(r["pts"], float)) for r in rs]
        merged = True
        while merged:
            merged = False
            for i, a in enumerate(rs):
                for j, b in enumerate(rs):
                    if i == j:
                        continue
                    A, B = a["pts"], b["pts"]
                    if len(A) < 2 or len(B) < 2:
                        continue
                    d = B[0, :2] - A[-1, :2]
                    L = float(np.hypot(*d))
                    ta = A[-1, :2] - A[-2, :2]
                    tb = B[1, :2] - B[0, :2]
                    ta /= max(np.hypot(*ta), 1e-9)
                    tb /= max(np.hypot(*tb), 1e-9)
                    inline = L < 1e-6 or (float(d @ ta) / L > 0.9 and float(d @ tb) / L > 0.9)
                    if L < gap and inline and float(ta @ tb) > 0.8:
                        rs[i] = dict(a, pts=np.vstack([A, B]), votes=max(np.ravel(a.get("votes", 0))[0],
                                                                         np.ravel(b.get("votes", 0))[0]))
                        del rs[j]
                        merged = True
                        break
                if merged:
                    break
        out += rs
    return out


ITALY = "/levels/italy/art/shapes/buildings/"
MODULE = "italy_guardrails_basic"           # 3 m along local x (-1.5..1.5), the beam on local -y, origin on the ground
END_START, END_END = "italy_guardrails_basic_end_cw", "italy_guardrails_basic_end_ccw"
MODULE_LEN, MODULE_STEP = 3.0, 2.8          # m: Italy lays them 2.8 m apart (0.2 m overlap)
FACE_OUT = 0.02                              # m, the origin this far towards the road from the back of the old rail
MIN_RUN = 1.0                                # m, shorter pieces get no rail
MIN_STEP = 2.0                               # m, the least step of two modules (1 m over each other)
BOX = (-1.5, 1.5, -0.07, 0.15, 0.0, 0.9)     # m, the beam and its posts over the ground, local x, y, z (module_faces)
ITALY_MATERIALS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                               "italy_guardrail_materials.json")


def modules(P, side):
    """The Italy modules along a rail: P (n, >= 3) x, y and foot z of the back of the rail, side as rail().
    Returns [(type, position (3,), rotationMatrix (9,))]: the modules every MODULE_STEP m (the last one ending
    at the end of the line), pitched along the chord they span, then the two end pieces, level."""
    P = np.asarray(P, np.float64)[:, :3]
    if side < 0:
        # road to the left of travel: the same rail walked the other way (road to the right). With the line as
        # given, X along it and Y away from the road would make Z = X x Y point down: the module upside down,
        # its beam under the ground and only the buried part of the posts standing out of it
        P, side = P[::-1], 1
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    L = d[-1]
    if L < MIN_RUN:
        return []
    at = lambda t: np.array([np.interp(t, d, P[:, k]) for k in range(3)])
    if L <= MODULE_LEN:
        spans = [(0.5 * L - 0.5 * MODULE_LEN, 0.5 * L + 0.5 * MODULE_LEN)]
    else:
        # the modules evenly along the line, at most MODULE_STEP apart; where that would lay two of them more
        # than 1 m over each other (up to v2.8 the last one went back to end at the end of the line, over the
        # one before it: a double beam), one fewer at MODULE_STEP, centred (the line a little longer than them)
        n = int(np.ceil((L - MODULE_LEN) / MODULE_STEP - 1e-9)) + 1
        step = (L - MODULE_LEN) / (n - 1)
        if step < MIN_STEP:
            n -= 1
            step = MODULE_STEP
        a0 = 0.5 * (L - (MODULE_LEN + step * (n - 1)))
        spans = [(a0 + k * step, a0 + k * step + MODULE_LEN) for k in range(n)]

    def frame(p0, p1, level=False):
        X = p1 - p0
        if level:
            X[2] = 0.0
        X /= max(np.linalg.norm(X), 1e-9)
        Y = side * np.array([-X[1], X[0], 0.0])               # away from the road, horizontal
        Y /= max(np.linalg.norm(Y), 1e-9)
        Z = np.cross(X, Y)
        return X, Y, Z
    out = []
    for t0, t1 in spans:
        p0, p1 = at(np.clip(t0, 0, L)), at(np.clip(t1, 0, L))
        if t1 - t0 > (np.clip(t1, 0, L) - np.clip(t0, 0, L)) + 1e-6:     # a short run: the chord of the line
            m, X = 0.5 * (p0 + p1), None
            X, Y, Z = frame(at(0.0), at(L))
            c = m
        else:
            X, Y, Z = frame(p0, p1)
            c = 0.5 * (p0 + p1)
        c = c - FACE_OUT * Y
        out.append((MODULE, c, np.r_[X, Y, Z]))
    for name, t, t_in in ((END_START, spans[0][0], spans[0][0] + MODULE_LEN),
                          (END_END, spans[-1][1], spans[-1][1] - MODULE_LEN)):
        tc = float(np.clip(t, 0, L))
        X, Y, Z = frame(at(float(np.clip(min(t, t_in), 0, L))), at(float(np.clip(max(t, t_in), 0, L))), level=True)
        p = at(tc)
        if t < 0 or t > L:                                   # the module overhangs the line (a short run)
            p = p + X * (t - tc)
        out.append((name, p - FACE_OUT * Y, np.r_[X, Y, Z]))
    return out


def write_forest(level_dir, items, append=False):
    """The guard rail modules as forest items (forest/<type>.forest4.json, art/forest/managedItemData.json: the
    other types of the level are kept); append: after the modules already written (the rails of fences.py)."""
    fdir = os.path.join(level_dir, "forest")
    os.makedirs(fdir, exist_ok=True)
    md = os.path.join(level_dir, "art", "forest", "managedItemData.json")
    managed = json.load(open(md)) if os.path.exists(md) else {}
    by_type = {}
    for t, p, R in items:
        if R[8] <= 0:
            raise ValueError(f"guard rail module {t} at {np.round(p, 1)} upside down (local z {np.round(R[6:], 3)})")
        by_type.setdefault(t, []).append((p, R))
    for t, lst in by_type.items():
        managed[t] = {"name": t, "internalName": t, "class": "TSForestItemData", "persistentId": bng.pid(),
                      "annotation": "GUARD_RAIL", "radius": 0.9, "shapeFile": f"{ITALY}{t}.dae"}
        with open(os.path.join(fdir, f"{t}.forest4.json"), "a" if append else "w") as f:
            for p, R in lst:
                f.write(json.dumps({"ctxid": 1, "pos": [round(float(v), 3) for v in p],
                                    "rotationMatrix": [round(float(v), 6) for v in R], "scale": 1, "type": t},
                                   separators=(",", ":")) + "\n")
    os.makedirs(os.path.dirname(md), exist_ok=True)
    json.dump(managed, open(md, "w"), indent=1)
    # the materials of the models that only Italy defines (their textures are in the game's Italy level)
    mats = json.load(open(ITALY_MATERIALS))
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "guardrails", "italy.materials.json"),
                        list(mats.values()))
    return {t: len(v) for t, v in by_type.items()}


def is_module(name):
    """A forest type (or file name) of the guard rail modules."""
    return os.path.basename(name).startswith("italy_guardrails")


def read_modules(src):
    """The guard rail modules of a level: (positions (k, 3), rotation matrices (k, 3, 3), types). src: a
    bng.LevelFiles, a zipfile.ZipFile of the mod or a level folder (levels/<name>)."""
    rows = []
    if isinstance(src, str):
        files = [(f, open(os.path.join(src, "forest", f)).read()) for f in sorted(os.listdir(os.path.join(src, "forest")))
                 if is_module(f) and f.endswith(".forest4.json")] if os.path.isdir(os.path.join(src, "forest")) else []
    else:
        files = [(n, src.read(n).decode("utf-8")) for n in src.namelist()
                 if "/forest/" in n and is_module(n) and n.endswith(".forest4.json")]
    for _, text in files:
        for l in text.splitlines():
            if l.strip():
                o = json.loads(l)
                rows.append((o["pos"], o["rotationMatrix"], o["type"]))
    if not rows:
        return np.zeros((0, 3)), np.zeros((0, 3, 3)), []
    return (np.array([r[0] for r in rows], np.float64), np.array([r[1] for r in rows], np.float64).reshape(-1, 3, 3),
            [r[2] for r in rows])


def module_faces(src):
    """Triangles (k, 3, 3) of a box around the beam and posts of every module (BOX; the end pieces: their 0.5 m),
    for what keeps clear of a guard rail (trunks, lamps, posts, the raised ground beside the roads)."""
    P, R, T = read_modules(src)
    if not len(P):
        return np.zeros((0, 3, 3))
    x0, x1, y0, y1, z0, z1 = BOX
    C = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])     # 8 corners, index 4x+2y+z
    Q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tri = np.array([[q[0], q[1], q[2]] for q in Q] + [[q[0], q[2], q[3]] for q in Q])
    out = []
    for p, r, t in zip(P, R, T):
        c = C.copy()
        if t != MODULE:                                    # the end pieces: half a metre
            c[:, 0] *= 0.5 / 3.0
            c[:, 0] += -0.18 if t == END_START else 0.18
        W = p + c @ r                                     # rows of r: the local axes in the world
        out.append(W[tri])
    return np.concatenate(out)


def module_points(src, step=0.25):
    """xy every `step` m along the beam of every module (what a lamp or a post keeps clear of)."""
    P, R, T = read_modules(src)
    if not len(P):
        return np.zeros((0, 2))
    u = np.arange(-1.5, 1.5 + 1e-6, step)
    return np.concatenate([p[None, :2] + u[:, None] * r[0, :2] for p, r in zip(P, R)])


def edge_fn(level_dir, near=8.0):
    """(x, y) -> height of the highest road face of the level (folder as being built: the road meshes written
    by the stage roads, corridor and network) there, NaN off the roads; only the faces within `near` m of a
    rail of guardrails_final.json or of the panoramas are kept (the whole network would not fit the memory)."""
    import markings_net
    import osm_surface
    from road_mesh import TriSurface
    from scipy.spatial import cKDTree
    pts = [np.array(r["pts"], float)[:, :2] for r in json.load(open(os.path.join(WORK, "guardrails_final.json")))]
    if os.path.exists(SV_RUNS):
        pts += [np.array(r["pts"], float)[:, :2] for r in json.load(open(SV_RUNS)) if len(r["pts"])]
    import area
    pts = [p for p in pts if len(p) > 1 and area.in_zone(p[:, 0], p[:, 1]).all()]
    if not pts:                                      # a Ticino zone with no photo rails
        return None
    pts = np.concatenate([resample(np.column_stack([p, np.zeros(len(p))]), 1.0)[0][:, :2] for p in pts])
    mats = osm_surface.ROAD_MATS + osm_surface.HARD_MATS + ("mp_road_asphalt_fresh", "mp_sidewalk", "mp_island")
    tops = markings_net.road_tops(level_dir, mats)
    d, _ = cKDTree(pts).query(tops.mean(1)[:, :2], distance_upper_bound=near)
    S = TriSurface(tops[np.isfinite(d)])
    return lambda x, y: S.height(x, y, "high")


MOTORWAY_CLASSES = ("Autobahn", "Autostrasse")
MOTORWAY_TOP = 0.75      # m, top of the rail over its foot (as the measured ones)
MOTORWAY_CLEAR = 0.8     # m beyond the half width of another road: no rail (ramps, slip roads, junctions)
MOTORWAY_STEP = 2.0      # m between the points of a motorway rail


def motorway_runs():
    """Rails along both edges of every motorway carriageway of a zone (swissTLM3D Autobahn / Autostrasse): the
    Ticino zones' motorways had none, nothing measured them (2026-10-28). Open wherever another road comes within
    its half width + MOTORWAY_CLEAR (the ramps leave and join there); the other carriageway only where it overlaps
    the rail (a median of two rails back to back, one is dropped as a double). No rail in a tunnel (the network
    leaves them out)."""
    import network
    from scipy.spatial import cKDTree
    segs, st, _ = network.load()
    xy = np.column_stack([st["x"], st["y"]])
    tree = cKDTree(xy)
    cls = np.array([segs[k]["class"] for k in st["seg"]])
    kind = np.array([segs[k]["kind"] for k in st["seg"]])
    out = []
    for sg in segs:
        if sg["kind"] != "road" or sg["class"] not in MOTORWAY_CLASSES or sg["n"] < 2:
            continue
        a, n = sg["first"], sg["n"]
        Q = np.column_stack([st["x"][a:a + n], st["y"][a:a + n], st["z_tlm"][a:a + n], st["width"][a:a + n]])
        Q, _s = resample(Q, MOTORWAY_STEP)
        if len(Q) < 3:
            continue
        T = np.gradient(Q[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        for side in (1, -1):
            P = Q[:, :2] + side * Nl * (0.5 * Q[:, 3:4] + EDGE_OUT)
            keep = np.ones(len(P), bool)
            for k, lst in enumerate(tree.query_ball_point(P, 10.0)):
                for j in lst:
                    if st["seg"][j] == sg["id"] or kind[j] == "path" or abs(st["z_tlm"][j] - Q[k, 2]) > 3.0:
                        continue                 # a road under a viaduct or over a cutting does not open the rail
                    other_mw = cls[j] in MOTORWAY_CLASSES
                    reach = 0.5 * st["width"][j] + (-0.3 if other_mw else MOTORWAY_CLEAR)
                    if np.hypot(*(P[k] - xy[j])) < reach:
                        keep[k] = False
                        break
            for piece in pieces(keep):
                if len(piece) >= 3:
                    out.append({"pts": np.column_stack([P[piece], Q[piece, 2], np.full(len(piece), MOTORWAY_TOP)]),
                                "side": side, "seg": sg["id"]})
    return out


def build(level_dir, level_name, scene, road_fn=None):
    import area
    runs = [r for r in json.load(open(os.path.join(WORK, "guardrails_final.json")))
            if len(r["pts"]) and area.in_zone(np.array(r["pts"])[:, 0], np.array(r["pts"])[:, 1]).all()]
    foot = foot_fn()
    items = []
    measured = []
    for r in runs:
        P = np.array(r["pts"])
        P[:, 2] = foot(P[:, 0], P[:, 1])
        measured.append({**r, "pts": P})
    # v3.0: the measured rails of the cantonal road on the edge of the road as built too (the corridor surfaces of
    # v1.1 under them were rebuilt since; up to v2.8 they stood on the measured line, here and there off the
    # asphalt or into it)
    from geo import Grid
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    if road_fn is not None:
        for r in measured:
            r["pts"] = to_edge(r["pts"], r["side"], road_fn, dtm.sample)
    # the rails of the cantonal road, measured: a stretch measured twice is laid once
    measured, gone = drop_doubles(measured)
    for r in measured:
        items += modules(r["pts"], r["side"])
    # the rest of the network: the rails seen in the panoramas, on the edge of the road as built
    extra = join_runs(sv_runs(runs))
    if road_fn is not None and extra:
        for r in extra:
            r["pts"] = to_edge(r["pts"], r["side"], road_fn, dtm.sample)
    extra = open_crossings(extra)
    if ZONE:                                  # the motorways of a Ticino zone (not in the Malcantone build)
        # the z of a motorway point is its carriageway's (swissTLM3D), also on a viaduct: to_edge looks for the
        # road's edge at that height (the foot of the measured rails is the ground, the valley under a viaduct)
        mw = motorway_runs()
        if road_fn is not None:
            for r in mw:
                r["pts"] = to_edge(r["pts"], r["side"], road_fn, dtm.sample)
        extra += mw
        print("motorway guard rails: %d runs, %.1f km" % (len(mw), sum(length(r["pts"]) for r in mw) / 1000))
    # where a panorama run lies along a rail laid already (on the edge of the road as built, two runs can
    # come onto one line): only the first; the runs with more votes first
    extra.sort(key=lambda r: -np.ravel(r.get("votes", 0))[0])
    extra, gone2 = drop_doubles(extra, [r["pts"][:, :2] for r in measured])
    print(f"guard rails laid twice, left out: {gone + gone2:.0f} m")
    for r in extra:
        items += modules(r["pts"], r["side"])
    if extra:
        print("guard rails seen in the panoramas:", len(extra), "runs,",
              round(sum(np.linalg.norm(np.diff(r["pts"][:, :2], axis=0), axis=1).sum() for r in extra) / 1000, 2), "km")
    counts = write_forest(level_dir, items)
    print("guardrails", len(runs) + len(extra), "runs:", counts)
    return counts
