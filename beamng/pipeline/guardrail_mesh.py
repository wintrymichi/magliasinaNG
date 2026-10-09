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
from config import WORK
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
GAP_CROSS = 1.0          # m beyond the half width of a line that crosses a rail: the rail is open there
MIN_PIECE = 4.0          # m, shorter pieces of a rail cut at a crossing are dropped
SV_RUNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "guardrails_sv.json")


def sv_runs(existing):
    """Guard rails of the rest of the network seen in the Street View panoramas (sv_guardrails.py, v2.2):
    [{pts: [[x, y, z of the road edge, top height]], side}], without the ones along the rails of the
    original route (existing runs, within 1.5 m)."""
    if not os.path.exists(SV_RUNS):
        return []
    import shapely
    old = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(1.5) for r in existing
                             if len(r["pts"]) > 1]) if existing else None
    out = []
    for r in json.load(open(SV_RUNS)):
        P = np.array(r["pts"], float)
        if len(P) < 2:
            continue
        if old is not None:
            keep = ~shapely.contains_xy(old, P[:, 0], P[:, 1])
            if keep.sum() < 3:
                continue
            P = P[keep]
        out.append({"pts": P, "side": r["side"], "seg": r.get("seg", -1)})
    return out


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
    """A rail seen in the panoramas moved onto the edge of the road as built: every point on the line
    across the road through it goes to EDGE_OUT m outside the last road face (searching from EDGE_IN m
    inside to EDGE_SEARCH m outside), its foot at the height of the road's edge; and the ground under it
    for the posts. P: (n, 4) x, y, z, top -> (n, 5) x, y, z, top, ground."""
    P = np.array(P, float)
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    out = side * np.column_stack([-T[:, 1], T[:, 0]])          # away from the road
    offs = np.arange(-EDGE_IN, EDGE_SEARCH + 1e-6, 0.1)
    X = P[:, None, 0] + out[:, None, 0] * offs[None]
    Y = P[:, None, 1] + out[:, None, 1] * offs[None]
    Z = road_fn(X.ravel(), Y.ravel()).reshape(X.shape)
    on = np.isfinite(Z)
    has = on.any(1)
    last = np.where(has, on.shape[1] - 1 - np.argmax(on[:, ::-1], axis=1), 0)
    e = np.where(has, offs[last], 0.0)
    ze = np.where(has, Z[np.arange(len(P)), last], P[:, 2])
    Q = P.copy()
    Q[:, :2] = P[:, :2] + out * (e + EDGE_OUT)[:, None]
    from scipy.ndimage import median_filter
    Q[:, 2] = median_filter(ze - 0.03, size=5, mode="nearest") if len(P) >= 5 else ze - 0.03
    g = ground(Q[:, 0], Q[:, 1])
    return np.column_stack([Q, g])


ITALY = "/levels/italy/art/shapes/buildings/"
MODULE = "italy_guardrails_basic"           # 3 m along local x (-1.5..1.5), the beam on local -y, origin on the ground
END_START, END_END = "italy_guardrails_basic_end_cw", "italy_guardrails_basic_end_ccw"
MODULE_LEN, MODULE_STEP = 3.0, 2.8          # m: Italy lays them 2.8 m apart (0.2 m overlap)
FACE_OUT = 0.02                              # m, the origin this far towards the road from the back of the old rail
MIN_RUN = 1.0                                # m, shorter pieces get no rail
BOX = (-1.5, 1.5, -0.07, 0.15, 0.0, 0.9)     # m, the beam and its posts over the ground, local x, y, z (module_faces)
ITALY_MATERIALS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                               "italy_guardrail_materials.json")


def modules(P, side):
    """The Italy modules along a rail: P (n, >= 3) x, y and foot z of the back of the rail, side as rail().
    Returns [(type, position (3,), rotationMatrix (9,))]: the modules every MODULE_STEP m (the last one ending
    at the end of the line), pitched along the chord they span, then the two end pieces, level."""
    P = np.asarray(P, np.float64)[:, :3]
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    L = d[-1]
    if L < MIN_RUN:
        return []
    at = lambda t: np.array([np.interp(t, d, P[:, k]) for k in range(3)])
    if L <= MODULE_LEN:
        spans = [(0.5 * L - 0.5 * MODULE_LEN, 0.5 * L + 0.5 * MODULE_LEN)]
    else:
        a = list(np.arange(0.0, L - MODULE_LEN + 1e-6, MODULE_STEP))
        if L - MODULE_LEN - a[-1] > 0.05:
            a.append(L - MODULE_LEN)
        spans = [(t, t + MODULE_LEN) for t in a]

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


def build(level_dir, level_name, scene, road_fn=None):
    runs = json.load(open(os.path.join(WORK, "guardrails_final.json")))
    foot = foot_fn()
    items = []
    for r in runs:
        P = np.array(r["pts"])
        P[:, 2] = foot(P[:, 0], P[:, 1])
        items += modules(P, r["side"])
    # the rest of the network: the rails seen in the panoramas, on the edge of the road as built
    extra = sv_runs(runs)
    if road_fn is not None and extra:
        from geo import Grid
        dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
        for r in extra:
            r["pts"] = to_edge(r["pts"], r["side"], road_fn, dtm.sample)
    extra = open_crossings(extra)
    for r in extra:
        items += modules(r["pts"], r["side"])
    if extra:
        print("guard rails seen in the panoramas:", len(extra), "runs,",
              round(sum(np.linalg.norm(np.diff(r["pts"][:, :2], axis=0), axis=1).sum() for r in extra) / 1000, 2), "km")
    counts = write_forest(level_dir, items)
    print("guardrails", len(runs) + len(extra), "runs:", counts)
    return counts
