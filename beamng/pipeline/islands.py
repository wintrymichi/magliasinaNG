"""Traffic islands raised on their kerbs, with the keep-right sign on their noses (v3.0), in the built level.

The islands of the cadastral survey (spartitraffico: the splitter islands of the roundabouts and junctions, the
refuges of the crossings) were meshed like the road, at the height of the asphalt: in the game a pale patch in
the carriageway that a car drove over without noticing (the user's screenshots 21, 31, 32), and no sign told
which side to pass. Here, on the built level:
- every island face of the road meshes (material mp_island) goes, and the island is built again KERB_H m over
  the asphalt: its top in Italy's cobbles (granite setts, as most islands of the area are paved), a kerb of
  Italy's concrete kerb stone all round it, down to KERB_DOWN m under the road; with collision (a car hits the kerb);
- on the nose of every island at least NOSE_MIN m long that an approaching driver faces (the carriageway goes on
  beyond the end of the island, along its long axis), the signal 2.33 (pass the obstacle on the right, signs_ch.py)
  on a grey pole, facing that traffic; the pole's foot in the black and yellow sleeve of the Swiss island posts
  (BOLLARD_H m, BANDS bands, black at the bottom and the top), as the street photos of the area show them (v3.1:
  up to then a separate short white beacon with a yellow reflector stood beside the pole, which no island here has).
- the AI roads (MissionGroup/AIRoads) round the islands (v3.1 review, island_lanes): a swissTLM3D line runs down the
  middle of a roundabout arm, its splitter island included, and the AI lanes (a quarter of the width either side)
  ran along the kerb or over the island (at the Magliaso roundabout exit a car set mid lane stood on it, and the AI
  traffic crashed there, issue #83). Where an island stands in a lane, a two-way road is split there into two
  one-way roads, one on each side of the island, in the middle of the carriageway left on that side; where only
  one side has room, the road moves over to it. The pieces meet the rest of the road at its own nodes.
Meshes in MissionGroup/roads/islands, one shape per TILE m tile; the rest of the level is copied as it is.

A finishing step of build_level.py (FINISH), after the road paint and wear (which keep off the islands' faces) and
before the steps that place objects (they see the islands as raised ground); alone: python build_level.py --finish islands
"""
import json, math, os, re, tempfile, time, zipfile
import numpy as np
import shapely
import bng
import optimize_level
import signs_ch
from config import LEVEL_NAME
from markings_net import read_items

TILE = 512.0
KERB_H = 0.12            # m, the island over the asphalt
KERB_DOWN = 0.10         # m, the kerb's face goes this far under the asphalt
KERB_W = 0.15            # m, the kerb stone on the top, round the edge
NOSE_MIN = 3.0           # m: shorter islands get no sign
APPROACH = 6.0           # m beyond a nose: carriageway there, traffic comes this way
SIGN_D = 0.6             # m, the disk of 2.33
SIGN_C = 1.45            # m, its middle over the island
NOSE_IN = 0.6            # m from the nose to the pole
ISLAND_MAT = "mp_island"
BOLLARD_W = 0.14         # m, the sleeve round the pole's foot
BOLLARD_H = 1.05         # m over the island
BANDS = 7                # black, yellow, ..., black
BOLLARD_TEX = "t_island_bollard_b.color.png"
LANE_CLEAR = 0.3         # m kept from an island's edge (its kerb) by the free carriageway beside it
LANE_MIN = 2.3           # m: the narrowest free carriageway a lane is moved onto
LANE_BAND = 1.1          # m: an island this close to a lane's middle stands in the lane (half a car and a margin)
LANE_LEAD = 8.0          # m before and after the island over which a lane moves aside
LANE_STEP = 1.0          # m between the stations the lanes are measured at
LANE_REACH = 5.0         # m: the free carriageway is looked for this far beyond the AI road's edge
LANE_SPLIT = 0.6         # share of the stations in an island that must have room on both sides to split the road
AI_ITEMS = "main/MissionGroup/AIRoads/items.level.json"
SHAPE = re.compile(r"art/shapes/roads/islands_[-+]\d+_[-+]\d+\.dae$")
L = f"/levels/{LEVEL_NAME}"
TEX_DIR = f"levels/{LEVEL_NAME}/art/shapes/roads"


def materials():
    import italy_mats as it
    return [it.material("mp_island_top", "italy_cobblestone", ground_type="COBBLESTONE"),
            it.material("mp_island_kerb", "italy_curb_concrete", ground_type="CONCRETE"),
            bng.material("mp_island_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6),
            bng.material("mp_island_bollard", f"{L}/art/shapes/roads/{BOLLARD_TEX}", roughness=0.45, ground_type="PLASTIC"),
            bng.material("mp_island_233", f"{L}/art/shapes/roads/t_island_233_b.color.png", roughness=0.35,
                         alpha_test=100, ground_type="METAL",
                         detail={"opacityMap": f"{L}/art/shapes/roads/t_island_233_o.data.png"}),
            bng.material("mp_island_233_back", base_color=[150 / 255, 152 / 255, 154 / 255, 1], roughness=0.5,
                         metallic=0.5, alpha_test=100, ground_type="METAL",
                         detail={"opacityMap": f"{L}/art/shapes/roads/t_island_233_o.data.png"}),
            # the white beacon and its reflector of v3.0 - v3.0.40 (no shape uses them since v3.1): still defined,
            # so an island shape the game compiled from an earlier version and kept in its cache finds them
            # (the v3.1 test log: 30 "NO-MATERIAL" each, one per island tile with poles)
            bng.material("mp_island_beacon", base_color=[0.93, 0.93, 0.91, 1], roughness=0.5),
            bng.material("mp_island_reflector", base_color=[0.95, 0.75, 0.05, 1], roughness=0.3)]


def box(c, w, d, z0, z1, ax):
    """Triangles of a box w (along ax) x d about c from z0 to z1, outward."""
    ax = np.asarray(ax, float) / max(np.hypot(*ax), 1e-9)
    n = np.array([-ax[1], ax[0]])
    q = [c + ax * w / 2 + n * d / 2, c - ax * w / 2 + n * d / 2, c - ax * w / 2 - n * d / 2, c + ax * w / 2 - n * d / 2]
    out = []
    for a in range(4):
        p0, p1 = q[a], q[(a + 1) % 4]
        out += [np.r_[p0, z1], np.r_[p0, z0], np.r_[p1, z0], np.r_[p0, z1], np.r_[p1, z0], np.r_[p1, z1]]
    out += [np.r_[q[0], z1], np.r_[q[1], z1], np.r_[q[2], z1], np.r_[q[0], z1], np.r_[q[2], z1], np.r_[q[3], z1]]
    return np.array(out).reshape(-1, 3, 3)


def bollard(p, d, zt):
    """(triangles, uvs) of the black and yellow sleeve round a pole at p (its faces along d) from the island's top zt:
    u round the sleeve, v up it (one texture height = the sleeve)."""
    T = box(p, BOLLARD_W, BOLLARD_W, zt, zt + BOLLARD_H, d)
    V = T.reshape(-1, 3)
    ax = np.asarray(d, float) / max(np.hypot(*d), 1e-9)
    ang = np.arctan2(V[:, 1] - p[1], V[:, 0] - p[0])
    u = (ang - math.atan2(ax[1], ax[0])) / (2 * math.pi) % 1.0
    v = (V[:, 2] - zt) / BOLLARD_H
    return T, np.column_stack([u, v])


def bollard_png():
    """The sleeve's texture: BANDS bands up a 1 x 8 strip, black at the bottom and the top."""
    from PIL import Image
    import io
    h = 64 * BANDS
    img = Image.new("RGB", (16, h))
    for k in range(BANDS):
        col = (18, 18, 18) if k % 2 == 0 else (238, 190, 22)
        img.paste(col, (0, h - (k + 1) * 64, 16, h - k * 64))
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def disk(c, nrm, zc, r, n=20):
    """Front (facing nrm) and back fans of a disk, with texture coordinates for the front."""
    rt = np.array([-nrm[1], nrm[0]])
    a = np.linspace(0, 2 * np.pi, n + 1)
    P = [np.r_[c + rt * math.cos(t) * r, zc + math.sin(t) * r] for t in a]
    U = [(0.5 + 0.5 * math.cos(t), 0.5 + 0.5 * math.sin(t)) for t in a]
    C, Uc = np.r_[c, zc], (0.5, 0.5)
    front = np.array([[C, P[k], P[k + 1]] for k in range(n)])
    uv = np.array([[Uc, U[k], U[k + 1]] for k in range(n)])
    back = front[:, ::-1] - np.r_[nrm * 0.004, 0]
    return front, uv, back


def components(T):
    """Groups (lists of face indices) of the faces T (k, 3, 3) that share corners."""
    key = np.round(T.reshape(-1, 3)[:, :2] * 200).astype(np.int64)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    vid = vid.reshape(-1, 3)
    parent = np.arange(vid.max() + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in vid:
        ra = find(t[0])
        for v in t[1:]:
            rb = find(v)
            if ra != rb:
                parent[rb] = ra
    root = np.array([find(t[0]) for t in vid])
    return [np.flatnonzero(root == r) for r in np.unique(root)]


def island_polys(zi, lv):
    """The islands (shapely polygons) of the islands shapes already in the level (a level built before)."""
    objs = read_items(zi, f"{lv}/main/MissionGroup/roads/islands/items.level.json") \
        if f"{lv}/main/MissionGroup/roads/islands/items.level.json" in zi.NameToInfo else []
    out = []
    for o in objs:
        sn = o.get("shapeName", "").lstrip("/")
        if sn not in zi.NameToInfo:
            continue
        V, N, UV, C, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            if mat == "mp_island_top":
                T = (V[idx[:, 0]] + pos).reshape(-1, 3, 3)
                for f in components(T):
                    u = shapely.union_all([shapely.Polygon(t[:, :2]) for t in T[f]]).buffer(0.01).buffer(-0.01)
                    out += [g for g in getattr(u, "geoms", [u]) if g.area >= 0.5]
    return out


def _stations(N, step=LANE_STEP):
    """The nodes N (n, 4) with stations every `step` m between them: (points (m, 4), index of the node or -1)."""
    P, orig = [N[0]], [0]
    for i in range(1, len(N)):
        d = float(np.hypot(*(N[i, :2] - N[i - 1, :2])))
        k = max(1, int(np.ceil(d / step)))
        for j in range(1, k):
            P.append(N[i - 1] + (N[i] - N[i - 1]) * j / k)
            orig.append(-1)
        P.append(N[i])
        orig.append(i)
    return np.array(P), np.array(orig)


def _runs(flags):
    """(start, end) index pairs of the runs of True in flags."""
    f = np.r_[False, flags, False].astype(int)
    d = np.diff(f)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def _ease(n, known, pin0=True, pin1=True):
    """Offsets for n stations from {station: value}, smoothed (the free carriageway measured station by station
    wobbles by a few dm), linear between; 0 at an end of the range that is pinned, else the nearest value."""
    from scipy.ndimage import gaussian_filter1d
    k = sorted(i for i in known if (0 < i or not pin0) and (i < n - 1 or not pin1))
    if not k:
        return np.zeros(n)
    v = np.array([known[i] for i in k], float)
    v = gaussian_filter1d(v, 2.0, mode="nearest") if len(k) > 2 else v
    xs, vs = list(k), list(v)
    if pin0:
        xs, vs = [0] + xs, [0.0] + vs
    if pin1:
        xs, vs = xs + [n - 1], vs + [0.0]
    return np.interp(np.arange(n), xs, vs)


class Lanes:
    """The free carriageway beside the islands, across the AI roads."""
    def __init__(self, islands, carr):
        self.isl = shapely.union_all([g.buffer(LANE_CLEAR) for g in islands]) if islands else shapely.Polygon()
        shapely.prepare(self.isl)
        self.carr = carr
        self.T = np.arange(-12.0, 12.0 + 1e-9, 0.1)

    def near(self, N, two_way):
        line = shapely.LineString(N[:, :2])
        return line.dwithin(self.isl, float(N[:, 3].max()) / (4 if two_way else 2) + LANE_BAND)

    def measure(self, S, two_way):
        """Per station of S (m, 4): whether an island stands in a lane, and the free carriageway right and left
        of it ((middle, width) as offsets along the left normal; width 0 where there is none)."""
        tg = np.gradient(S[:, :2], axis=0)
        tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
        nl = np.column_stack([-tg[:, 1], tg[:, 0]])
        T = self.T
        X = S[:, None, 0] + nl[:, None, 0] * T[None]
        Y = S[:, None, 1] + nl[:, None, 1] * T[None]
        isl = shapely.contains_xy(self.isl, X, Y)
        reach = np.abs(T)[None] <= S[:, 3:4] / 2 + LANE_REACH
        z = np.repeat(S[:, 2] - 0.1, len(T))
        h = self.carr.height(X.ravel(), Y.ravel(), "near", zhint=z).reshape(X.shape)
        ok = np.isfinite(h) & (np.abs(h - z.reshape(X.shape)) < 0.8) & ~isl & reach
        lanes = [-0.25, 0.25] if two_way else [0.0]
        hit = np.zeros(len(S), bool)
        for f in lanes:
            hit |= (isl & (np.abs(T[None] - (f * S[:, 3:4])) < LANE_BAND)).any(1)
        right, left = np.zeros((len(S), 2)), np.zeros((len(S), 2))
        for i in np.flatnonzero(hit):
            span = np.flatnonzero(isl[i] & (np.abs(T) <= S[i, 3] / 2 + 0.05))
            if not len(span):
                span = np.flatnonzero(isl[i] & reach[i])
            a, b = span.min(), span.max()
            for side, k, d in ((right, a - 1, -1), (left, b + 1, 1)):
                j = k
                while 0 <= j < len(T) and not ok[i, j] and abs(j - k) < 4:     # the kerb's few cm
                    j += d
                j0 = j
                while 0 <= j < len(T) and ok[i, j]:
                    j += d
                if 0 <= j0 < len(T) and ok[i, j0]:
                    lo, hi = sorted((T[j0], T[j - d]))
                    side[i] = ((lo + hi) / 2, hi - lo + 0.1)
        return hit, right, left


def island_lanes(roads, islands, carr, rep):
    """The AI roads `roads` (the AIRoads items, replaced in place) kept out of the islands: see the module's
    docstring. Where two roads meet end to end inside an island's stretch (a line split at a node beside a long
    median), both move aside up to their common end and the pieces of the two are joined there, instead of
    meeting in the middle of the island. rep gets the counts."""
    from scipy.spatial import cKDTree
    lanes = Lanes(islands, carr)
    dr = [o for o in roads if o.get("class") == "DecalRoad" and len(o.get("nodes", [])) >= 2]
    P = np.concatenate([np.asarray(o["nodes"], float)[:, :2] for o in dr])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(dr)])
    first = np.r_[0, np.cumsum([len(o["nodes"]) for o in dr])[:-1]]
    nt = cKDTree(P)
    st = {"ai_roads_in_islands": 0, "ai_split": 0, "ai_moved": 0, "ai_blocked": 0, "ai_junction": 0}
    # 1. where the islands stand in the lanes of each road
    meas = {}
    for ri, o in enumerate(dr):
        N = np.asarray(o["nodes"], float)
        two = not o.get("oneWay")
        if lanes.near(N, two):
            S, orig = _stations(N)
            hit, right, left = lanes.measure(S, two)
            if hit.any():
                s_ = np.r_[0, np.cumsum(np.hypot(*np.diff(S[:, :2], axis=0).T))]
                meas[ri] = (S, orig, hit, right, left, s_)

    def hit_near_end(ri, e):
        if ri not in meas:
            return False
        S, orig, hit, right, left, s_ = meas[ri]
        d = s_ if e == 0 else s_[-1] - s_
        return bool((hit & (d <= LANE_LEAD)).any())
    # 2. the open ends: two two-way roads meeting end to end, both with an island in a lane near that end
    opened = {}
    for ri in meas:
        o = dr[ri]
        if o.get("oneWay"):
            continue
        for e in (0, -1):
            others = {own[j] for j in nt.query_ball_point(o["nodes"][e][:2], 0.05)} - {ri}
            if len(others) != 1:
                continue
            rj = others.pop()
            n_j = len(dr[rj]["nodes"])
            k = [j - first[rj] for j in nt.query_ball_point(o["nodes"][e][:2], 0.05) if own[j] == rj]
            if dr[rj].get("oneWay") or not k or k[0] not in (0, n_j - 1):
                continue
            ej = 0 if k[0] == 0 else -1
            if hit_near_end(ri, e) and hit_near_end(rj, ej):
                opened[(ri, e)] = tuple(np.round(np.asarray(o["nodes"][e][:2], float), 2))
    out, tags = [], []                       # tags: (junction, piece, its end 0/-1, road)
    for ri, o in enumerate(dr):
        if ri not in meas:
            out.append(o)
            continue
        S, orig, hit, right, left, s = meas[ri]
        N = np.asarray(o["nodes"], float)
        two = not o.get("oneWay")
        st["ai_roads_in_islands"] += 1
        open0, open1 = (ri, 0) in opened, (ri, -1) in opened
        shared = np.zeros(len(S), bool)
        for k in np.flatnonzero(orig >= 0):
            shared[k] = any(own[j] != ri for j in nt.query_ball_point(N[orig[k], :2], 0.05))
        tg = np.gradient(S[:, :2], axis=0)
        tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
        nl = np.column_stack([-tg[:, 1], tg[:, 0]])
        # the runs of stations in an island, joined across short gaps, with LANE_LEAD m before and after
        runs = []
        for a, b in _runs(hit):
            a2 = int(np.searchsorted(s, s[a] - LANE_LEAD))
            b2 = min(len(S) - 1, int(np.searchsorted(s, s[b] + LANE_LEAD)))
            if runs and a2 <= runs[-1][1]:
                runs[-1][1] = b2
            else:
                runs.append([a2, b2])
        cuts = []                     # (a, b, pieces: [(offsets, widths, reversed)])
        moved = S.copy()
        for a, b in runs:
            if shared[a + 1:b].any():
                st["ai_junction"] += 1
                continue
            p0, p1 = not (a == 0 and open0), not (b == len(S) - 1 and open1)
            idx = [i for i in range(a, b + 1) if hit[i]]
            both = [i for i in idx if right[i, 1] >= LANE_MIN and left[i, 1] >= LANE_MIN]
            if two and len(both) >= LANE_SPLIT * len(idx):
                pc = []
                for side, rev in ((right, False), (left, True)):
                    ok = [i for i in idx if side[i, 1] >= LANE_MIN]
                    off = _ease(b - a + 1, {i - a: side[i, 0] for i in ok}, p0, p1)
                    wd = S[a:b + 1, 3] + _ease(b - a + 1, {i - a: min(side[i, 1], 4.0) - S[i, 3] for i in ok}, p0, p1)
                    pc.append((off, wd, rev))
                cuts.append((a, b, pc))
                continue
            # room on one side only: the road moves over there, its ends held
            best = {}
            for i in idx:
                c = [x for x in (right[i], left[i]) if x[1] >= LANE_MIN]
                if c:
                    best[i] = max(c, key=lambda x: x[1])
            if len(best) < LANE_SPLIT * len(idx) or (shared[a] and a > 0) or (shared[b] and b < len(S) - 1):
                st["ai_blocked"] += 1
                continue
            off = _ease(b - a + 1, {i - a: best[i][0] for i in best}, p0, p1)
            wd = S[a:b + 1, 3] + _ease(b - a + 1, {i - a: min(best[i][1], S[i, 3]) - S[i, 3] for i in best}, p0, p1)
            moved[a:b + 1, :2] += nl[a:b + 1] * off[:, None]
            moved[a:b + 1, 3] = wd
            st["ai_moved"] += 1
        # the nodes: the road's own, and every second station where it moves aside
        aside = np.abs(moved[:, :2] - S[:, :2]).sum(1) > 1e-6
        name, last_s = o["name"], len(S) - 1

        def nodes_of(Q, a, b, every):
            sel = [i for i in range(a, b + 1) if i in (a, b) or orig[i] >= 0 or (every or aside[i]) and i % 2 == 0]
            return [[round(float(v), 4) for v in Q[i]] for i in sel]

        def tag(q, a, b, rev):
            for st_, e, op in ((0, 0, open0), (last_s, -1, open1)):
                if op and a <= st_ <= b:
                    tags.append((opened[(ri, e)], q, (-1 if st_ == a else 0) if rev else (0 if st_ == a else -1), ri))
        k0, last = 0, 0
        for a, b, pc in cuts + [(last_s, None, None)]:
            if a > k0:                                  # the road up to the island (or after the last one)
                q = dict(o) if last == 0 else {**o, "persistentId": bng.pid(), "name": f"{name}_i{last}_0"}
                q["nodes"] = nodes_of(moved, k0, a, False)
                q["position"] = q["nodes"][0][:3]
                out.append(q)
                tag(q, k0, a, False)
            if b is None:
                break
            last += 1
            st["ai_split"] += 1
            for (off, wd, rev), t in zip(pc, ("i", "j")):
                Q = S.copy()
                Q[a:b + 1, :2] += nl[a:b + 1] * off[:, None]
                Q[a:b + 1, 3] = np.round(wd, 2)
                nd = nodes_of(Q, a, b, True)
                if rev:
                    nd = nd[::-1]
                q = {key: v for key, v in o.items() if key not in ("autoLanes", "lanesLeft", "lanesRight")}
                plain = a == 0 and last == 1 and t == "i"     # the road starts in the island: it keeps its name
                q.update({"persistentId": o["persistentId"] if plain else bng.pid(),
                          "name": name if plain else f"{name}_{t}{last}", "nodes": nd, "position": nd[0][:3],
                          "oneWay": True, "lanesLeft": 0, "lanesRight": 1})
                out.append(q)
                tag(q, a, b, rev)
            k0 = b
    # 3. the open ends joined: each piece end to the nearest of the other road's, at their midpoint; where the
    # two roads do not agree (split / moved / kept), all of them back on the common node
    st["ai_open_joints"] = 0
    by = {}
    for jid, q, e, ri in tags:
        by.setdefault(jid, []).append((q, e, ri))
    for jid, ends in by.items():
        fam = sorted({ri for _, _, ri in ends})
        A = [x for x in ends if x[2] == fam[0]]
        B = [x for x in ends if len(fam) > 1 and x[2] == fam[1]]
        if len(fam) == 2 and len(A) == len(B):
            rest = list(B)
            for qa, ea, _ in A:
                pa = np.asarray(qa["nodes"][ea], float)
                k = min(range(len(rest)), key=lambda m: np.hypot(*(np.asarray(rest[m][0]["nodes"][rest[m][1]][:2]) - pa[:2])))
                qb, eb, _ = rest.pop(k)
                mid = ((pa + np.asarray(qb["nodes"][eb], float)) / 2).round(4).tolist()
                qa["nodes"][ea] = list(mid)
                qb["nodes"][eb] = list(mid)
            st["ai_open_joints"] += 1
        else:
            for q, e, _ in ends:
                q["nodes"][e] = [jid[0], jid[1]] + list(q["nodes"][e][2:])
        for q, _, _ in ends:
            q["position"] = q["nodes"][0][:3]
    others = [o for o in roads if not (o.get("class") == "DecalRoad" and len(o.get("nodes", [])) >= 2)]
    roads[:] = others + out
    # what is left: lanes still in an island
    left_ = 0
    for o in out:
        N = np.asarray(o["nodes"], float)
        two = not o.get("oneWay")
        if lanes.near(N, two):
            S, _ = _stations(N)
            left_ += int(lanes.measure(S, two)[0].any())
    st["ai_roads_in_islands_after"] = left_
    rep.update(st)
    return st


def islands_step(root, report=None):
    from road_mesh import TriSurface
    from markings_net import shape_tris, up_faces, CARRIAGE_MATS
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    items_name = f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"
    items = read_items(zi, items_name)
    new_dae, tops = {}, []
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        if f'material="{ISLAND_MAT}-mat"' not in text:
            continue
        V, N, UV, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        mb = bng.MeshBuilder()
        for mat, idx in parts:
            if mat == ISLAND_MAT:
                tops.append(up_faces((V[idx[:, 0]] + pos).reshape(-1, 3, 3)))
                continue
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[idx[:, 0]], uvs=UV[idx[:, 2]], normals=N[idx[:, 1]],
                   tris=np.arange(len(idx)).reshape(-1, 3), colors=col)
        if mb.empty():
            new_dae[sn] = None
            continue
        base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.dae")
            mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
            new_dae[sn] = open(path, "rb").read()
    rep = {"islands": 0, "island_m2": 0.0, "signs": 0}
    builders = {}
    polys = []
    surf = shape_tris(zi, lv, items)
    carr = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS]))
    del surf
    if tops:
        T = np.concatenate(tops)

        def add(mat, tris, uvs=None):
            c = tris.reshape(-1, 3).mean(0)
            key = (int(np.floor(c[0] / TILE)), int(np.floor(c[1] / TILE)))
            V = tris.reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=uvs if uvs is not None else V[:, :2] / 1.5,
                                                            normals=bng.flat_normals_soup(V))
        for g in components(T):
            F = T[g]
            poly = shapely.union_all([shapely.Polygon(f[:, :2]) for f in F]).buffer(0.01).buffer(-0.01)
            if poly.is_empty or poly.area < 0.5:
                continue
            rep["islands"] += 1
            rep["island_m2"] += float(poly.area)
            polys += list(getattr(poly, "geoms", [poly]))
            # the top: the faces raised; the kerb stone and its face round every boundary edge
            top = F.copy()
            top[:, :, 2] += KERB_H
            add("mp_island_top", top)
            key = np.round(F.reshape(-1, 3)[:, :2] * 200).astype(np.int64)
            _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
            vid = vid.reshape(-1, 3)
            E = np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]])
            P3 = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
            k = np.sort(E, 1)
            kk = k[:, 0] * (vid.max() + 1) + k[:, 1]
            _, first, cnt = np.unique(kk, return_index=True, return_counts=True)
            B = P3[first[cnt == 1]]                       # boundary edges (a, b) of the island
            a, b = B[:, 0], B[:, 1]
            at, bt = a + [0, 0, KERB_H], b + [0, 0, KERB_H]
            ab, bb = a - [0, 0, KERB_DOWN], b - [0, 0, KERB_DOWN]
            face = np.stack([at, ab, bb, at, bb, bt], 1).reshape(-1, 3, 3)
            # outward: away from the island's middle
            c2 = np.array(poly.representative_point().coords[0])
            nrm = np.cross(face[:, 1] - face[:, 0], face[:, 2] - face[:, 0])[:, :2]
            out = ((face.mean(1)[:, :2] - c2) * nrm).sum(1) < 0
            face[out] = face[out][:, ::-1]
            u = np.linalg.norm(b - a, axis=1)
            s0 = np.zeros(len(u))
            uv = np.stack([np.c_[s0, np.full(len(u), 1.0)], np.c_[s0, np.zeros(len(u))], np.c_[u, np.zeros(len(u))],
                           np.c_[s0, np.full(len(u), 1.0)], np.c_[u, np.zeros(len(u))], np.c_[u, np.full(len(u), 1.0)]],
                          1).reshape(-1, 3, 2) * [1.0, KERB_H + KERB_DOWN]
            uv[out] = uv[out][:, ::-1]
            add("mp_island_kerb", face, uv.reshape(-1, 2))
            # the signs: on the noses that traffic approaches along the island's axis
            mrr = poly.minimum_rotated_rectangle
            R = np.asarray(mrr.exterior.coords)[:4]
            e0, e1 = R[1] - R[0], R[2] - R[1]
            ax = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
            Lr = float(np.hypot(*ax))
            if Lr < NOSE_MIN or poly.area < 2.0:
                continue
            ax /= Lr
            ctr = np.array(mrr.centroid.coords[0])
            zt = float(np.median(F[:, :, 2])) + KERB_H
            for sgn in (1.0, -1.0):
                d = ax * sgn
                nose = ctr + d * Lr / 2
                q = nose + d * APPROACH
                if not np.isfinite(carr.height([q[0]], [q[1]], "high")[0]):
                    continue
                # the pole on the island, NOSE_IN m in from its end
                p = None
                for back in np.arange(NOSE_IN, Lr / 2, 0.2):
                    cand = nose - d * back
                    if poly.buffer(-0.25).contains(shapely.Point(cand)):
                        p = cand
                        break
                if p is None:
                    continue
                for tri in box(p, 0.06, 0.06, zt - 0.3, zt + SIGN_C + SIGN_D / 2, d):
                    add("mp_island_pole", tri[None])
                front, uv, back_ = disk(p + d * 0.04, d, zt + SIGN_C, SIGN_D / 2)
                add("mp_island_233", front, uv.reshape(-1, 2))
                add("mp_island_233_back", back_)
                bt, buv = bollard(p, d, zt)
                add("mp_island_bollard", bt, buv)
                rep["signs"] += 1
    rep["island_m2"] = round(rep["island_m2"])
    files = {}
    # the AI roads round the islands (on a level built before: round the islands already there)
    ai_name = f"{lv}/{AI_ITEMS}"
    if ai_name in zi.NameToInfo:
        roads = read_items(zi, ai_name)
        island_lanes(roads, polys if tops else island_polys(zi, lv), carr, rep)
        files[ai_name] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in roads) + "\n").encode("utf-8")
    if not tops:
        # nothing to raise (the islands are there already): only the AI roads change
        with zi.writer() as zo:
            for i in zi.infolist():
                if i.filename not in files:
                    zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(files.items()):
                zo.writestr(n, data)
        print("islands:", rep, flush=True)
        if report:
            os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
            json.dump(rep, open(report, "w"), indent=1)
        return rep
    objs = []
    with tempfile.TemporaryDirectory() as tmp:
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/islands_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, "i.dae")
            mb.write_dae(f, name=f"islands_{tx}_{ty}", origin=origin)
            files[f"{lv}/{rel}"] = open(f, "rb").read()
            objs.append(bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=False))
    pl = signs_ch.plate("2.33")
    if pl is not None:
        import signs_net
        col, op = signs_net.rgba_files(pl.img)
        files[f"{TEX_DIR}/t_island_233_b.color.png"] = col
        files[f"{TEX_DIR}/t_island_233_o.data.png"] = op
    files[f"{TEX_DIR}/{BOLLARD_TEX}"] = bollard_png()
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    for m in materials():
        mats[m["name"]] = m
    files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    g_items = f"{lv}/main/MissionGroup/roads/islands/items.level.json"
    for ob in objs:
        ob["__parent"] = "islands"
    files[g_items] = ("\n".join(json.dumps(ob, separators=(",", ":")) for ob in objs) + "\n").encode("utf-8")
    # the group in the roads group
    r_items = f"{lv}/main/MissionGroup/roads/items.level.json"
    rows = read_items(zi, r_items)
    if not any(r.get("name") == "islands" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "islands", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"})
    files[r_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    gone = {"/" + n for n, d in new_dae.items() if d is None}
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in files or SHAPE.search(nm) or (nm in new_dae and new_dae[nm] is None):
                continue
            if nm in new_dae:
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[nm])
            elif nm == items_name and gone:
                zo.writestr(i, "\n".join(json.dumps(o, separators=(",", ":")) for o in items
                                         if o.get("shapeName") not in gone) + "\n")
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(n, data)
    rep["shapes_rewritten"] = len(new_dae)
    rep["seconds"] = round(time.time() - t0)
    print("islands:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
