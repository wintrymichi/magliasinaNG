"""Guard rails standing on something (Switzerland Builder, 2026-11-07).

michi: "controlla anche che i guardrail non siano volanti". In a zone the rails are laid by rule where the ground falls
beside a road (guardrail_mesh.drop_runs), 0.3 m beyond the road's edge (to_edge): on the first Axenstrasse build 28 %
of the 3,037 modules had a post more than 0.3 m over whatever was under it, 11 % more than 1 m, a few over 20 m. The
road's edge stood over the DTM's slope, which the carve of the terrain and its 1.5 m grid let fall away from 1-2 m
inside the edge, and paved_edges kept its embankment out of the 2 m round every rail. paved_edges fills it in a zone
now; what is left (a fall deeper than its EMB_MAX, a pavement or a yard lower than the road beside it, the clearance
round a railway) stands on a concrete edge beam on a wall down into the ground: the rail of a mountain road on its
retaining wall. A rail hanging more than BEAM_MAX over the ground is left as it is and listed (a road over a gorge
with no bridge: no wall that high).

A finishing step of build_level.py after tunnels (the ground the posts stand on is final then: the skin, the holes of
the tubes, the rails the tunnels took away), in a zone only (the Malcantone's rails are measured on its panoramas):
python build_level.py --finish rail_walls
"""
import json, os, re, time
import numpy as np
from scipy.ndimage import binary_closing, binary_dilation, median_filter, minimum_filter1d
from scipy.spatial import cKDTree
import bng
import guardrail_mesh as gm
import road_mesh
from config import LEVEL_NAME, ZONE

POSTS = {gm.MODULE: ((-0.75, 0.095), (0.75, 0.095)),         # local x, y of the feet of the posts (the beam on -y)
         gm.END_START: ((-0.18, 0.095),), gm.END_END: ((0.18, 0.095),)}
HANG_OK = 0.25          # m a post may stand over the ground (the models' posts reach a little under their origin)
TOP_OVER = 0.9          # m: a face higher over a foot than this is beside the post, not under it (the beam's top)
STEP = 0.5              # m between the stations of a wall
BEAM_OUT = 0.42         # m behind the rail's origin (local y) the beam reaches: the posts stand 0.1 m behind it
BEAM_IN = -0.36         # m: its inner side, 0.1 m under the road's edge (found from the rail inwards, ROAD_SEARCH m)
BEAM_IN_MAX = -0.2      # ... never nearer the rail than this
ROAD_SEARCH = 1.5
ROAD_DZ = 0.3           # m: a face within this of the foot's height is the road beside the rail
BEAM_SINK = 0.4         # m, the foot of the wall under the lowest ground across it
BEAM_MAX = 8.0          # m: over a deeper fall no wall, only the beam (a road over a gorge with no bridge)
CORNICE = 0.6           # m, the depth of the beam alone (and the least depth of the wall under its top)
BEAM_LEAD = 1.0         # m the wall goes on along the rail beyond the last post that hangs
BEAM_JOIN = 4.0         # m: two hanging stretches of one rail this close are one wall
LINK = (1.8, 3.1, 0.3, 1.5)    # m: the next module of a rail lies this far along, at most this far across and over
SHAPE_REACH = 600.0     # m: a merged shape whose position is this far from every foot holds no face near them
FACE_REACH = 2.0        # m from a foot: the faces kept (the cross-section of the wall reaches about this far)
TREE_CLEAR = 0.15       # m round the beam's footprint: no forest item there
CH = 128.0              # m, the shapes are chunks of this size
MAT, MAT_TOP = "mp_wall_concrete", "mp_wall_concrete_top"
TILE = 4.0              # m per texture repeat (walls.WALL_TILE of both)
OWN = "/art/shapes/walls/rail_walls_"


def read_items(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


def write_items(path, items):
    """A new file (the level may be a hard-linked copy of another)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w", encoding="utf-8") as f:
        for o in items:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")
    os.replace(path + ".part", path)


class Ground:
    """What a post can stand on: the terrain (both splits of a square, none over a hole) and the up faces of every
    shape of the level near the rails (LOD0)."""

    def __init__(self, root, lv, feet):
        import tunnels
        self.ter = tunnels.Terrain(lv)
        kd = cKDTree(feet[:, :2])
        tris, pref = [], f"/levels/{LEVEL_NAME}/"
        for dp, _, fs in os.walk(os.path.join(lv, "main")):
            if "items.level.json" not in fs:
                continue
            for o in read_items(os.path.join(dp, "items.level.json")):
                sn = o.get("shapeName", "")
                if o.get("class") != "TSStatic" or not sn.startswith(pref) or not sn.endswith(".dae") or OWN in sn:
                    continue
                pos = np.array(o.get("position", [0, 0, 0]), np.float64)
                if not np.isfinite(kd.query(pos[:2], distance_upper_bound=SHAPE_REACH)[0]):
                    continue
                path = os.path.join(root, sn.lstrip("/"))
                if not os.path.exists(path):
                    continue
                text = open(path, encoding="utf-8").read()
                lod0 = tunnels.dae_triangles(text.split("</geometry>", 1)[0] + "</geometry>")
                rot = np.array(o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1]), np.float64).reshape(3, 3)
                sc = np.array(o.get("scale", [1, 1, 1]), np.float64)
                for parts in lod0.values():
                    for _, t in parts:
                        t = (t * sc) @ rot + pos
                        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                        t = t[(n[:, 2] > 0.3 * np.linalg.norm(n, axis=1)) & np.isfinite(t).all((1, 2))]
                        if not len(t):
                            continue
                        c = t[:, :, :2].mean(1)
                        rad = np.linalg.norm(t[:, :, :2] - c[:, None], axis=2).max(1)
                        d = kd.query(c, distance_upper_bound=60.0)[0]
                        t = t[d <= rad + FACE_REACH]
                        if len(t):
                            tris.append(t)
        self.faces = road_mesh.TriSurface(np.concatenate(tris) if tris else np.zeros((0, 3, 3)))
        self.n_faces = len(self.faces.t)

    def terrain(self, x, y):
        """(lower, higher) height of the two splits of the terrain square under each point; NaN over a hole."""
        T = self.ter
        c, r = (np.asarray(x, np.float64) - T.x0) / T.sq, (np.asarray(y, np.float64) - T.y0) / T.sq
        c0 = np.clip(np.floor(c).astype(np.int64), 0, T.n - 2)
        r0 = np.clip(np.floor(r).astype(np.int64), 0, T.n - 2)
        u, v = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
        h00, h10, h01, h11 = T.h[r0, c0], T.h[r0, c0 + 1], T.h[r0 + 1, c0], T.h[r0 + 1, c0 + 1]
        a = np.where(u >= v, h00 + u * (h10 - h00) + v * (h11 - h10), h00 + v * (h01 - h00) + u * (h11 - h01))
        b = np.where(u + v <= 1, h00 + u * (h10 - h00) + v * (h01 - h00),
                     h11 + (1 - u) * (h01 - h11) + (1 - v) * (h10 - h11))
        hole = T.lay[r0, c0] == 255
        return np.where(hole, np.nan, np.minimum(a, b)), np.where(hole, np.nan, np.maximum(a, b))

    def under(self, x, y, z, low=False):
        """The highest surface at or under z at each point: a face, or the terrain (its higher split; low: the lower)."""
        lo, hi = self.terrain(x, y)
        return np.fmax(self.faces.height(x, y, "under", z), lo if low else hi)

    def near(self, x, y, z):
        return self.faces.height(x, y, "near", z)


def chains(P, R, T):
    """The modules of each rail in order, and its two end pieces (or -1): [(module ids, start id, end id)]."""
    mod = np.array([t == gm.MODULE for t in T])
    ids = np.flatnonzero(mod)
    if not len(ids):
        return []
    X = R[:, 0, :2] / np.maximum(np.linalg.norm(R[:, 0, :2], axis=1, keepdims=True), 1e-9)
    kd = cKDTree(P[ids, :2])
    nxt = {}
    for i in ids:
        best = None
        for j in ids[kd.query_ball_point(P[i, :2], LINK[1] + 0.1)]:
            d = P[j] - P[i]
            along = d[:2] @ X[i]
            if (j != i and LINK[0] <= along <= LINK[1] and abs(d[0] * X[i, 1] - d[1] * X[i, 0]) <= LINK[2]
                    and abs(d[2]) <= LINK[3] and X[i] @ X[j] > 0.9 and (best is None or along < best[0])):
                best = (along, j)
        if best is not None:
            nxt[i] = best[1]
    prev = {j: i for i, j in nxt.items()}
    if len(prev) < len(nxt):                     # two modules claim the same next one: keep the nearer claim
        prev = {}
        for i, j in sorted(nxt.items(), key=lambda kv: np.linalg.norm(P[kv[1]] - P[kv[0]])):
            prev.setdefault(j, i)
        nxt = {i: j for j, i in prev.items()}
    ends = {t: np.flatnonzero(np.array([tt == t for tt in T])) for t in (gm.END_START, gm.END_END)}
    ekd = {t: cKDTree(P[e, :2]) if len(e) else None for t, e in ends.items()}
    out, seen = [], set()
    for s in ids:
        if s in prev or s in seen:
            continue
        ch = [s]
        seen.add(s)
        while ch[-1] in nxt and nxt[ch[-1]] not in seen:
            ch.append(nxt[ch[-1]])
            seen.add(ch[-1])
        caps = []
        for t, at in ((gm.END_START, P[ch[0]] - 1.5 * R[ch[0], 0]), (gm.END_END, P[ch[-1]] + 1.5 * R[ch[-1], 0])):
            d, k = ekd[t].query(at[:2]) if ekd[t] is not None else (np.inf, -1)
            caps.append(int(ends[t][k]) if d < 0.8 else -1)
        out.append((ch, caps[0], caps[1]))
    for s in ids:                                 # a loop of modules (no first one)
        if s not in seen:
            ch = [s]
            seen.add(s)
            while ch[-1] in nxt and nxt[ch[-1]] not in seen:
                ch.append(nxt[ch[-1]])
                seen.add(ch[-1])
            out.append((ch, -1, -1))
    return out


def quads(Q, want):
    """Two triangles (k*2, 3, 5) of every quad Q (k, 4, 5: x, y, z, u, v), each turned to face `want` (k, 3)."""
    t = np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])
    w = np.concatenate([want, want])
    n = np.cross(t[:, 1, :3] - t[:, 0, :3], t[:, 2, :3] - t[:, 0, :3])
    flip = (n * w).sum(1) < 0
    t[flip] = t[flip][:, ::-1]
    return t


def section(G, p, zf, Y):
    """The cross-section of the edge beam at stations p (m, 2) along a rail's origin line, the foot of the rail zf (m,),
    Y (m, 2) away from the road: its inner side (m along Y: 0.1 m under the road's edge, found from the rail inwards),
    the height of its top there (never over the road), and the lowest ground across it and just beyond (m,)."""
    m = len(p)
    inner = np.full(m, BEAM_IN)
    found = np.zeros(m, bool)
    for yy in -np.arange(0.1, ROAD_SEARCH + 1e-6, 0.1):
        q = p + yy * Y
        h = G.near(q[:, 0], q[:, 1], zf)
        hit = ~found & (np.abs(h - zf) <= ROAD_DZ)
        inner[hit] = yy - 0.1
        found |= hit
    inner = np.minimum(inner, BEAM_IN_MAX)
    inner = minimum_filter1d(median_filter(inner, 5, mode="nearest"), 3, mode="nearest")
    qi, qo = p + inner[:, None] * Y, p + BEAM_OUT * Y
    hi = G.near(qi[:, 0], qi[:, 1], zf)
    zt_in = np.where(np.abs(hi - zf) <= ROAD_DZ, np.minimum(zf, hi - 0.02), zf)
    g = []
    for f in (0.0, 0.5, 1.0, 1.0 + 0.3 / (BEAM_OUT - BEAM_IN_MAX)):
        q = qi + f * (qo - qi)
        g.append(G.under(q[:, 0], q[:, 1], zf - 0.1, low=True))
    g = np.array(g)
    g = np.where(np.isfinite(g).any(0), np.nanmin(np.where(np.isfinite(g), g, np.inf), 0), np.nan)
    return inner, zt_in, g


def prism(p, Y, s, inner, zt_in, zt_out, zb):
    """The beam and its wall as a closed prism: (triangles of the sides (k, 3, 5: x, y, z, u, v), of the top,
    footprint (2m, 2))."""
    m = len(p)
    qi, qo = p + inner[:, None] * Y, p + BEAM_OUT * Y
    A = np.column_stack([qi, zt_in, s, inner])           # inner top: x, y, z, along, across
    B = np.column_stack([qo, zt_out, s, np.full(m, BEAM_OUT)])
    C = np.column_stack([qo, zb, s, np.full(m, BEAM_OUT)])
    D = np.column_stack([qi, zb, s, inner])
    T3 = np.column_stack([np.gradient(p[:, 0]), np.gradient(p[:, 1]), np.zeros(m)])
    T3 /= np.maximum(np.linalg.norm(T3, axis=1, keepdims=True), 1e-9)
    Y3 = np.column_stack([Y, np.zeros(m)])
    up = np.tile([0.0, 0.0, 1.0], (m - 1, 1))
    mid = lambda V: 0.5 * (V[:-1] + V[1:])
    side_uv = lambda Q: np.stack([Q[:, :, 3], Q[:, :, 2]], 2) / TILE          # along, height
    flat_uv = lambda Q: np.stack([Q[:, :, 3], Q[:, :, 4]], 2) / TILE          # along, across

    def strip(U, V, want, uv):
        Q = np.stack([U[:-1], U[1:], V[1:], V[:-1]], 1).copy()
        Q[:, :, 3:] = uv(Q)
        return quads(Q, want)
    sides = [strip(B, C, mid(Y3), side_uv),             # the face to the valley
             strip(D, A, -mid(Y3), side_uv),            # the one under the road
             strip(C, D, -up, flat_uv)]                 # the foot, under the ground
    for k, sgn in ((0, -1.0), (m - 1, 1.0)):            # the ends
        Q = np.array([[A[k], B[k], C[k], D[k]]])
        Q[:, :, 3:] = np.stack([Q[:, :, 4], Q[:, :, 2]], 2) / TILE
        sides.append(quads(Q, sgn * T3[[k]]))
    return np.concatenate(sides), strip(A, B, up, flat_uv), np.vstack([qi, qo[::-1]])


def rail_walls_step(root, report=None):
    t0 = time.time()
    res = {"modules": 0, "end_pieces": 0, "rails": 0, "hanging_before": {}, "walls": 0, "wall_m": 0.0,
           "wall_height_p50_m": 0.0, "wall_height_max_m": 0.0, "triangles": 0, "hanging_after": {}, "too_deep": [],
           "forest_removed": 0, "shapes": 0, "seconds": 0}
    if not ZONE:
        print("rail walls: not in the Malcantone build (its rails are measured on the panoramas)", flush=True)
        return res
    lv = os.path.join(root, "levels", LEVEL_NAME)
    shp_dir = os.path.join(lv, "art", "shapes", "walls")
    gi = os.path.join(lv, "main", "MissionGroup", "walls", "items.level.json")
    old = [f for f in os.listdir(shp_dir) if f.startswith("rail_walls_")] if os.path.isdir(shp_dir) else []
    for f in old:                                  # a rerun: the walls of the last one go first
        os.remove(os.path.join(shp_dir, f))
    items = [o for o in read_items(gi) if OWN not in o.get("shapeName", "")]
    if old:
        write_items(gi, items)
    P, R, T = gm.read_modules(lv)
    kinds = np.array(T)
    res["modules"] = int((kinds == gm.MODULE).sum())
    res["end_pieces"] = len(T) - res["modules"]
    if not len(P):
        print("rail walls: no guard rail in the level", flush=True)
        return res
    feet, owner = [], []
    for i, (p, r, t) in enumerate(zip(P, R, T)):
        for lx, ly in POSTS.get(t, ()):
            feet.append(p + lx * r[0] + ly * r[1])
            owner.append(i)
    F, own = np.array(feet), np.array(owner)
    G = Ground(root, lv, F)
    print("rail walls: %d modules, %d end pieces, %d faces near them (%.0f s)" % (res["modules"], res["end_pieces"],
                                                                                   G.n_faces, time.time() - t0), flush=True)
    gap = F[:, 2] - G.under(F[:, 0], F[:, 1], F[:, 2] + TOP_OVER)
    gap = np.where(np.isfinite(gap), gap, 99.0)
    hang = np.full(len(P), -np.inf)
    np.maximum.at(hang, own, gap)
    bins = ((-1e9, HANG_OK), (HANG_OK, 0.6), (0.6, 1.0), (1.0, 3.0), (3.0, BEAM_MAX), (BEAM_MAX, 1e9))
    label = lambda lo, hi: "under %.2f m" % hi if lo < -1e8 else "over %g m" % lo if hi > 1e8 else "%g-%g m" % (lo, hi)
    res["hanging_before"] = {label(lo, hi): int(((hang >= lo) & (hang < hi)).sum()) for lo, hi in bins}
    print("rail walls: posts over the ground before:", res["hanging_before"], flush=True)
    held = np.zeros(len(P), bool)                  # every foot on a new beam
    builders, footprints, heights = {}, [], []
    lead, join = int(np.ceil(BEAM_LEAD / STEP)), int(np.ceil(BEAM_JOIN / STEP))
    rails = chains(P, R, T)
    res["rails"] = len(rails)
    for ch, cs, ce in rails:
        X0, X1 = R[ch[0], 0], R[ch[-1], 0]
        # the line of the rail's origins, half a metre beyond both ends (the end pieces' feet)
        L3 = np.vstack([P[ch[0]] - 2.0 * X0, P[ch], P[ch[-1]] + 2.0 * X1])
        d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L3[:, :2], axis=0), axis=1))]
        s = np.r_[np.arange(0.0, d[-1], STEP), d[-1]]
        p = np.column_stack([np.interp(s, d, L3[:, 0]), np.interp(s, d, L3[:, 1])])
        zf = np.interp(s, d, L3[:, 2])
        Tg = np.gradient(p, axis=0)
        Tg /= np.maximum(np.linalg.norm(Tg, axis=1, keepdims=True), 1e-9)
        Y = np.column_stack([-Tg[:, 1], Tg[:, 0]])
        if (Y[np.searchsorted(s, d[1:-1]).clip(0, len(s) - 1)] * R[ch, 1, :2]).sum() < 0:
            Y = -Y                                 # away from the road, as the modules' local y
        mark = np.zeros(len(s), bool)
        members = [(k, d[i + 1], 1.5) for i, k in enumerate(ch)] + [(k, a, 0.6) for k, a in ((cs, 0.5), (ce, d[-1] - 0.5)) if k >= 0]
        for k, at, half in members:
            if hang[k] > HANG_OK:
                mark |= np.abs(s - at) <= half
        if not mark.any():
            continue
        pad = np.zeros(join, bool)
        mark = binary_dilation(mark, np.ones(2 * lead + 1, bool))
        mark = binary_closing(np.r_[pad, mark, pad], np.ones(join, bool))[join:-join] | mark
        for piece in gm.pieces(mark):
            if len(piece) < 2:
                continue
            sl = slice(piece[0], piece[-1] + 1)
            inner, zt_in, g = section(G, p[sl], zf[sl], Y[sl])
            if not np.isfinite(g).any():
                continue
            hgt = zf[sl] - g
            deep = ~(hgt <= BEAM_MAX)              # NaN (no ground at all) too
            # the wall down into the ground; over a fall deeper than BEAM_MAX only the beam, as on a bridge
            gw = minimum_filter1d(np.where(deep, np.inf, g), 5, mode="nearest") - BEAM_SINK
            zb = np.where(deep | ~np.isfinite(gw), zf[sl] - CORNICE, np.minimum(gw, zf[sl] - CORNICE))
            sides, top, foot = prism(p[sl], Y[sl], s[sl], inner, zt_in, zf[sl], zb)
            if deep.any():
                c = p[sl][int(np.nanargmax(np.where(np.isfinite(hgt), hgt, 99.0)))]
                res["too_deep"].append({"x": round(float(c[0]), 1), "y": round(float(c[1]), 1),
                                        "m": round(float(np.nanmax(np.where(np.isfinite(hgt), hgt, 99.0))), 1),
                                        "length_m": round(float(deep.sum() * STEP), 1)})
            c = p[sl][len(piece) // 2]
            mb = builders.setdefault((int(np.floor(c[0] / CH)), int(np.floor(c[1] / CH))), bng.MeshBuilder())
            for mat, t in ((MAT, sides), (MAT_TOP, top)):
                V = t.reshape(-1, 5)
                mb.add(mat, V[:, :3], uvs=V[:, 3:], normals=bng.flat_normals_soup(V[:, :3]))
            res["walls"] += 1
            res["wall_m"] += float(s[sl][-1] - s[sl][0])
            res["triangles"] += len(sides) + len(top)
            footprints.append(foot)
            heights.append(hgt[~deep])
    # the shapes and the scene
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/walls/rail_walls_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CH, (ty + 0.5) * CH, 0.0])
        mb.write_dae(os.path.join(lv, rel), name="railwall", origin=origin, orient=True)
        items.append(dict(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True, decal=False),
                          __parent="walls"))
    res["shapes"] = len(builders)
    if builders:
        write_items(gi, items)
        mg = os.path.join(lv, "main", "MissionGroup", "items.level.json")
        groups = read_items(mg)
        if not any(o.get("name") == "walls" and o.get("class") == "SimGroup" for o in groups):
            groups.append({"name": "walls", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "MissionGroup"})
            write_items(mg, groups)
    # no tree or bush inside a beam
    import shapely
    if footprints:
        U = shapely.union_all([shapely.Polygon(f).buffer(TREE_CLEAR) for f in footprints if len(f) >= 4])
        shapely.prepare(U)
        fdir = os.path.join(lv, "forest")
        for f in sorted(os.listdir(fdir)) if os.path.isdir(fdir) else []:
            if not f.endswith(".forest4.json") or gm.is_module(f):
                continue
            path = os.path.join(fdir, f)
            lines = [l for l in open(path, encoding="utf-8") if l.strip()]
            xy = np.array([json.loads(l)["pos"][:2] for l in lines]) if lines else np.zeros((0, 2))
            inside = shapely.contains_xy(U, xy[:, 0], xy[:, 1]) if len(xy) else np.zeros(0, bool)
            if inside.any():
                with open(path + ".part", "w", encoding="utf-8") as fo:
                    fo.writelines(l if l.endswith("\n") else l + "\n" for l, gone in zip(lines, inside) if not gone)
                os.replace(path + ".part", path)
                res["forest_removed"] += int(inside.sum())
    if footprints:
        on = shapely.contains_xy(shapely.union_all([shapely.Polygon(f).buffer(0.02) for f in footprints if len(f) >= 4]),
                                 F[:, 0], F[:, 1])
        held = np.ones(len(P), bool)
        np.logical_and.at(held, own, on)
    after = np.where(held, -np.inf, hang)
    res["held_on_walls"] = int(held.sum())          # guard rail items with every foot on a new beam
    res["hanging_after"] = {label(lo, hi): int(((after >= lo) & (after < hi)).sum()) for lo, hi in bins}
    if heights:
        H = np.concatenate(heights)
        res["wall_height_p50_m"] = round(float(np.nanmedian(H)), 2)     # the top over the lowest ground across it
        res["wall_height_max_m"] = round(float(np.nanmax(H)), 2)
    res["wall_m"] = round(res["wall_m"])
    res["seconds"] = round(time.time() - t0)
    print("rail walls:", {k: v for k, v in res.items() if k != "too_deep"}, flush=True)
    for t in res["too_deep"]:
        print("   rail over a fall too deep for a wall (a road over a gorge with no bridge?):", t, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res
