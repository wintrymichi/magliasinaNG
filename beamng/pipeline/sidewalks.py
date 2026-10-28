"""Pavements raised on their kerbs, lowered at the driveways and at the pedestrian crossings (v3.1), in the built level.

The pavements of the cadastral survey (marciapiede) were meshed like the road, at the height of the asphalt (in the
v3.1 test zip every edge a pavement shares with a carriageway was flush: dz 0 at the median and the 90th
percentile). In the villages of the area a pavement stands on a kerb (Swiss practice: about 12-16 cm, lowered to a
few cm where a car crosses it into a yard and at the crossings), and the kerb line is one of the things one
recognises while driving: the edge of the street, where the parked cars stop, where the crossing is. Here, on the
built level:
- the top faces of every pavement of the road meshes (material mp_sidewalk) go, and the pavement is built again
  KERB_H m over the asphalt, with its texture coordinates and normals; the faces under it (the skirts down to the
  ground) stay where they are;
- LOW_H only where a car crosses it: within LOW_R m of an edge of the pavement on a yard or driveway (mp_hard_*:
  the entrances of the survey) not closed by a wall or a fence and of a pedestrian crossing (its yellow bars in the road paint, ZEBRA_* as
  markings_clean.zebra draws them), rising to KERB_H over RAMP m;
- flush (no kerb) where an AI road runs over the pavement (a side street across a continuous pavement, an AI line
  over a lay-by the survey draws as pavement) and under the parking spots of the parked cars, back up over AI_RAMP m;
- every open edge of the raised top gets a face down to under the surface beside it: Italy's concrete kerb stone
  against a carriageway (KERB_DOWN m under the asphalt) and against a yard, the same stone down to the old edge
  (the skirt carries on under it) towards gardens, walls and paths;
- the objects that stood on a pavement (street lights, signs, poles, bins, benches, shelters, the trees and
  shrubs of the forest files) move up with it, and so does every piece of the prop shapes merged per tile
  (delineators, direction signs, OSM furniture) whose feet stood on it.
Meshes in MissionGroup/roads/sidewalks, one shape per TILE m tile, with collision; the rest is copied as it is.

A finishing step of build_level.py (FINISH), after the steps that place what stands on the pavements (it lifts it);
alone: python build_level.py --finish sidewalks. On a built level (the v3.1 nightly patch, the zip extracted):
python sidewalks.py <folder that holds levels/> [report.json]
"""
import json, os, re, sys, tempfile, time, zipfile
import numpy as np
import shapely
from scipy.spatial import cKDTree
import bng
import optimize_level
import osm_surface
from config import LEVEL_NAME
from markings_net import read_items

TILE = 512.0
KERB_H = 0.12            # m, the pavement over the asphalt
LOW_H = 0.03             # m, the lowered kerb at an entrance or a crossing
LOW_R = 2.0              # m from an entrance edge / a crossing: lowered
RAMP = 1.0               # m beyond LOW_R: back up to KERB_H
KERB_DOWN = 0.10         # m, the kerb's face goes this far under the surface beside it
BARRIER_R = 0.35         # m: a wall or fence this close along an edge on a yard closes it
PROBE = 0.25             # m out of an open edge: what lies there
ZEBRA_W = (0.3, 0.75)    # m, short side of a crossing's bar (markings_clean.ZEBRA_W 0.5)
ZEBRA_L = (1.8, 4.6)     # m, long side (markings_clean.ZEBRA_L 2.5-4)
ZEBRA_GAP = 1.4          # m between the middles of two bars of one crossing (2 x ZEBRA_W)
ZEBRA_N = 3              # bars at least
ZEBRA_OUT = 1.0          # m round a crossing's bars: the kerb there is lowered
SIDEWALK = "mp_sidewalk"
AI_STEP = 0.5            # m between the points of an AI road
AI_CLEAR = -1.25         # m beyond its half width (inside it): the pavement there stays flush with the road; the
                         # AI roads are as wide as the carriageway, so their edge is the kerb itself
PIECE_MAX = 8.0          # m, longest merged prop piece moved up with a pavement
PARK_CLEAR = 0.3         # m round a parking spot: the pavement stays flush
AI_RAMP = 0.75           # m from there back up to the kerb's height
SHAPE = re.compile(r"art/shapes/roads/sidewalks_[-+]\d+_[-+]\d+\.dae$")
L = f"/levels/{LEVEL_NAME}"
CARRIAGE = set(osm_surface.ROAD_MATS) | {"mp_road_asphalt_fresh", "mp_island_top"}
HARD = set(osm_surface.HARD_MATS)
LABELS = ("none", "carriage", "hard", "path", "sidewalk")
# groups whose objects stand on the ground: moved up with the pavement under them
OBJ_GROUPS = ("props",)


def materials():
    import italy_mats as it
    return [it.material("mp_sidewalk_kerb", "italy_curb_concrete", ground_type="CONCRETE")]


def up(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5


class Cover:
    """Which surface lies at a point: triangles (k, 3, 3) with a label each, point-in-triangle over the nearest."""

    def __init__(self, T, lab):
        self.T, self.lab = T, np.asarray(lab, np.int8)
        self.tree = cKDTree(T.mean(1)[:, :2])

    def at(self, P, k=16):
        out = np.zeros(len(P), np.int8)
        if not len(self.T):
            return out
        _, I = self.tree.query(P, k=min(k, len(self.T)))
        I = I.reshape(len(P), -1)
        hit = np.zeros(len(P), bool)
        for j in range(I.shape[1]):
            ii = np.minimum(I[:, j], len(self.T) - 1)
            a, b, c = self.T[ii, 0, :2], self.T[ii, 1, :2], self.T[ii, 2, :2]
            v0, v1, v2 = c - a, b - a, P - a
            d00, d01, d02 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v0 * v2).sum(1)
            d11, d12 = (v1 * v1).sum(1), (v1 * v2).sum(1)
            den = d00 * d11 - d01 * d01
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1.0)
            u = (d11 * d02 - d01 * d12) / den
            v = (d00 * d12 - d01 * d02) / den
            inside = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & ~hit
            out[inside] = self.lab[ii[inside]]
            hit |= inside
        return out


def crossings(zi, lv):
    """Polygons round the pedestrian crossings: groups of at least ZEBRA_N yellow bars of the road paint."""
    from islands import components
    items = read_items(zi, f"{lv}/main/MissionGroup/roads/markings/items.level.json")
    tris = []
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        if 'material="mp_road_paint_yellow-mat"' not in text:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(text)
        V = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            if mat == "mp_road_paint_yellow":
                tris.append(V[idx[:, 0]].reshape(-1, 3, 3))
    if not tris:
        return []
    T = np.concatenate(tris)
    bars = []
    for g in components(T):
        poly = shapely.union_all([shapely.Polygon(f[:, :2]) for f in T[g]]).buffer(0.02).buffer(-0.02)
        if poly.is_empty:
            continue
        R = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4]
        s = sorted([np.hypot(*(R[1] - R[0])), np.hypot(*(R[2] - R[1]))])
        if ZEBRA_W[0] <= s[0] <= ZEBRA_W[1] and ZEBRA_L[0] <= s[1] <= ZEBRA_L[1] and poly.area > 0.6 * s[0] * s[1]:
            bars.append(poly)
    if not bars:
        return []
    C = np.array([b.centroid.coords[0] for b in bars])
    parent = list(range(len(bars)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i, j in cKDTree(C).query_pairs(ZEBRA_GAP):
        parent[find(i)] = find(j)
    groups = {}
    for i in range(len(bars)):
        groups.setdefault(find(i), []).append(bars[i])
    return [shapely.union_all(g).convex_hull.buffer(ZEBRA_OUT) for g in groups.values() if len(g) >= ZEBRA_N]


def parking_boxes(zi, lv):
    """Footprints of the parking spots of the sites files (parking.py), as shapely polygons."""
    out = []
    for f in ("city.sites.json", "facilities.sites.json"):
        name = f"{lv}/{f}"
        if name not in zi.NameToInfo:
            continue
        for sp in json.loads(zi.read(name)).get("parkingSpots", []):
            x, y = sp["pos"][:2]
            qx, qy, qz, qw = sp.get("rot", [0, 0, 0, 1])
            yaw = 2 * np.arctan2(qz, qw)
            w, l = sp.get("scl", [2.5, 5.0, 3])[:2]
            c, s_ = np.cos(yaw), np.sin(yaw)
            q = [(x + u * c - v * s_, y + u * s_ + v * c) for u, v in ((-w / 2, -l / 2), (w / 2, -l / 2),
                                                                       (w / 2, l / 2), (-w / 2, l / 2))]
            out.append(shapely.Polygon(q))
    return out


def ai_lines(zi, lv):
    """(n, 3) points every AI_STEP m along the AI roads: x, y, half width + AI_CLEAR."""
    rows = read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json")
    out = []
    for r in rows:
        P = np.asarray(r.get("nodes", []), np.float64)
        if r.get("class") != "DecalRoad" or len(P) < 2:
            continue
        for a, b in zip(P[:-1], P[1:]):
            n = max(int(np.ceil(np.hypot(*(b[:2] - a[:2])) / AI_STEP)), 1)
            t = np.linspace(0, 1, n, endpoint=False)[:, None]
            q = a + (b - a) * t
            out.append(np.c_[q[:, :2], q[:, 3] / 2 + AI_CLEAR])
        out.append(np.c_[P[-1:, :2], P[-1:, 3] / 2 + AI_CLEAR])
    return np.concatenate(out) if out else np.zeros((0, 3))


def barriers(zi, lv, sw_tree):
    """(n, 2) points every 0.25 m along the edges of the walls and fences within 3 m of a pavement."""
    from markings_net import shape_tris
    objs = []
    for g in ("walls", "roads/fences"):
        name = f"{lv}/main/MissionGroup/{g}/items.level.json"
        if name in zi.NameToInfo:
            objs += read_items(zi, name)
    out = []
    for t in shape_tris(zi, lv, objs).values():
        d, _ = sw_tree.query(t.mean(1)[:, :2], distance_upper_bound=3.0)
        t = t[np.isfinite(d)]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            A, B = t[:, a, :2], t[:, b, :2]
            n = np.maximum(np.ceil(np.hypot(*(B - A).T) / 0.25).astype(int), 1)
            k = np.repeat(np.arange(len(t)), n)
            f = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
            out.append(A[k] + (B[k] - A[k]) * f[:, None])
    return np.concatenate(out) if out else np.zeros((0, 2))


def sidewalks_step(root, report=None):
    from markings_net import shape_tris
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    items_name = f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"
    items = read_items(zi, items_name)
    new_dae, tops, top_uv, top_n = {}, [], [], []
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        if f'material="{SIDEWALK}-mat"' not in text:
            continue
        V, N, UV, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        mb = bng.MeshBuilder()
        for mat, idx in parts:
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            if mat == SIDEWALK:
                F = (V[idx[:, 0]] + pos).reshape(-1, 3, 3)
                u = up(F)
                tops.append(F[u])
                top_uv.append(UV[idx[:, 2]].reshape(-1, 3, 2)[u])
                top_n.append(N[idx[:, 1]].reshape(-1, 3, 3)[u])
                keep = np.repeat(~u, 3)            # the skirts stay
                if not keep.any():
                    continue
                idx = idx[keep]
                col = col[keep] if col is not None else None
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
    rep = {"sidewalk_faces": 0, "sidewalk_m2": 0, "kerb_m": {}, "lowered_m": 0, "kerb_lowered_m": 0, "crossings": 0, "objects_raised": 0,
           "forest_raised": 0}
    if not tops:
        print("sidewalks: no pavement in the level", flush=True)
        return rep
    T = np.concatenate(tops)
    TUV = np.concatenate(top_uv)
    TN = np.concatenate(top_n)
    rep["sidewalk_faces"] = len(T)
    e1, e2 = T[:, 1, :2] - T[:, 0, :2], T[:, 2, :2] - T[:, 0, :2]
    rep["sidewalk_m2"] = round(float(np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2))

    # what lies beside the pavements: every other top face of the road meshes within reach
    sw_tree = cKDTree(T.reshape(-1, 3)[:, :2])
    isl = f"{lv}/main/MissionGroup/roads/islands/items.level.json"
    surf = shape_tris(zi, lv, items + (read_items(zi, isl) if isl in zi.NameToInfo else []))
    CT, CL = [T], [np.full(len(T), LABELS.index("sidewalk"))]
    for m, t in surf.items():
        if m == SIDEWALK:
            continue
        lab = "carriage" if m in CARRIAGE else "hard" if m in HARD else "path" if m.startswith("mp_path") else None
        if lab is None:
            continue
        t = t[up(t)]
        d, _ = sw_tree.query(t.mean(1)[:, :2], distance_upper_bound=4.0)
        t = t[np.isfinite(d)]
        CT.append(t)
        CL.append(np.full(len(t), LABELS.index(lab)))
    del surf
    cover = Cover(np.concatenate(CT), np.concatenate(CL))

    # open edges of the tops (corners welded on a 5 mm grid, as islands.components)
    key = np.round(T.reshape(-1, 3)[:, :2] * 200).astype(np.int64)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    vid = vid.reshape(-1, 3)
    nv = int(vid.max()) + 1
    Pv = np.zeros((nv, 3))
    Pv[vid.reshape(-1)] = T.reshape(-1, 3)
    E = np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]])
    opp = np.concatenate([vid[:, 2], vid[:, 0], vid[:, 1]])
    EZ = np.concatenate([T[:, [0, 1], 2], T[:, [1, 2], 2], T[:, [2, 0], 2]])
    k = np.sort(E, 1)
    kk = k[:, 0] * nv + k[:, 1]
    _, first, cnt = np.unique(kk, return_index=True, return_counts=True)
    bi = first[cnt == 1]
    Ea, Eb, Eo, Ez = E[bi, 0], E[bi, 1], opp[bi], EZ[bi]
    A2, B2 = Pv[Ea, :2], Pv[Eb, :2]
    d = B2 - A2
    ln = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)
    nrm = np.c_[d[:, 1], -d[:, 0]] / ln[:, None]
    mid = (A2 + B2) / 2
    flip = ((Pv[Eo, :2] - mid) * nrm).sum(1) > 0       # outward: away from the face's third corner
    nrm[flip] *= -1
    lab = cover.at(mid + nrm * PROBE)
    side = lab != LABELS.index("sidewalk")              # T joints between two pavement pieces are no edge
    # a yard behind a wall or a fence is no entrance: the survey draws the wall as a line between the two areas
    hard_e = np.flatnonzero(lab == LABELS.index("hard"))
    if len(hard_e):
        bar = barriers(zi, lv, sw_tree)
        if len(bar):
            bt = cKDTree(bar)
            hits = np.zeros(len(hard_e))
            for t_ in (0.2, 0.5, 0.8):
                q = A2[hard_e] + (B2[hard_e] - A2[hard_e]) * t_ + nrm[hard_e] * 0.15
                hits += np.isfinite(bt.query(q, distance_upper_bound=BARRIER_R)[0])
            walled = hard_e[hits >= 2]
            lab[walled] = LABELS.index("none")
            rep["walled_yard_m"] = round(float(ln[walled].sum()))
    for i, nm in enumerate(LABELS):
        if nm != "sidewalk":
            rep["kerb_m"][nm] = round(float(ln[side & (lab == i)].sum()))

    # the raise of every corner: lowered near the entrances and the crossings
    lowd = np.full(nv, np.inf)
    ent = side & (lab == LABELS.index("hard"))
    if ent.any():
        S = np.linspace(A2[ent], B2[ent], 5, axis=1).reshape(-1, 2)
        lowd = np.minimum(lowd, cKDTree(S).query(Pv[:, :2])[0])
    zeb = crossings(zi, lv)
    rep["crossings"] = len(zeb)
    if zeb:
        zu = shapely.union_all(zeb)
        shapely.prepare(zu)
        dz_ = shapely.distance(zu, shapely.points(Pv[:, :2]))
        lowd = np.minimum(lowd, np.where(dz_ > 0, LOW_R + dz_, 0.0))     # inside a crossing: lowered
    f = np.clip((lowd - LOW_R) / RAMP, 0.0, 1.0)
    raise_v = LOW_H + (KERB_H - LOW_H) * f
    # where an AI road runs over a pavement (a side street across a continuous pavement, an AI line over a lay-by
    # the survey draws as pavement) the pavement stays flush with it: the traffic would hit the kerb
    ai = ai_lines(zi, lv)
    if len(ai):
        da = np.full(nv, np.inf)
        tree = cKDTree(ai[:, :2])
        near = tree.query_ball_point(Pv[:, :2], r=float(ai[:, 2].max()) + AI_RAMP + 1.0)
        for v_, js in enumerate(near):
            if js:
                js = np.asarray(js)
                da[v_] = (np.hypot(*(ai[js, :2] - Pv[v_, :2]).T) - ai[js, 2]).min()
        g = np.clip(da / AI_RAMP, 0.0, 1.0)
        rep["flush_vertices"] = int((g < 1).sum())
        raise_v = raise_v * g
    # nor under a parking spot of the game's parked cars (a car spawned on the kerb jumps)
    spots = parking_boxes(zi, lv)
    if spots:
        su = shapely.union_all(spots).buffer(PARK_CLEAR)
        shapely.prepare(su)
        dp = shapely.distance(su, shapely.points(Pv[:, :2]))
        gp = np.clip(dp / AI_RAMP, 0.0, 1.0)
        rep["parking_flush_vertices"] = int((gp < 1).sum())
        raise_v = raise_v * gp
    low_e = side & (raise_v[Ea] + raise_v[Eb] < 2 * KERB_H - 0.02)
    rep["lowered_m"] = round(float(ln[low_e].sum()))
    rep["kerb_lowered_m"] = round(float(ln[low_e & (lab == LABELS.index("carriage"))].sum()))

    top = T.copy()
    top[:, :, 2] += raise_v[vid]
    # the kerb faces round the open edges
    carr = lab == LABELS.index("carriage")
    hard = lab == LABELS.index("hard")
    m = side
    a3 = np.c_[A2[m], Ez[m, 0]]
    b3 = np.c_[B2[m], Ez[m, 1]]
    ra, rb = raise_v[Ea[m]], raise_v[Eb[m]]
    down = np.where((carr | hard)[m], KERB_DOWN, 0.02)
    at, bt = a3 + np.c_[0 * ra, 0 * ra, ra], b3 + np.c_[0 * rb, 0 * rb, rb]
    ab, bb = a3 - np.c_[0 * ra, 0 * ra, down], b3 - np.c_[0 * rb, 0 * rb, down]
    face = np.stack([at, ab, bb, at, bb, bt], 1).reshape(-1, 3, 3)
    fn = np.cross(face[:, 1] - face[:, 0], face[:, 2] - face[:, 0])[:, :2]
    out = np.repeat(nrm[m], 2, axis=0)
    inward = (fn * out).sum(1) < 0
    face[inward] = face[inward][:, ::-1]
    u = ln[m]
    hgt = np.maximum(ra, rb) + down
    s0 = np.zeros(len(u))
    uv = np.stack([np.c_[s0, hgt], np.c_[s0, s0], np.c_[u, s0], np.c_[s0, hgt], np.c_[u, s0], np.c_[u, hgt]],
                  1).reshape(-1, 3, 2)
    uv[inward] = uv[inward][:, ::-1]

    builders = {}

    def add(mat, tris, uvs, normals=None):
        c = tris.mean(1)
        kx = np.floor(c[:, 0] / TILE).astype(int)
        ky = np.floor(c[:, 1] / TILE).astype(int)
        for key_ in set(zip(kx.tolist(), ky.tolist())):
            s = (kx == key_[0]) & (ky == key_[1])
            Vt = tris[s].reshape(-1, 3)
            Nt = normals[s].reshape(-1, 3) if normals is not None else bng.flat_normals_soup(Vt)
            builders.setdefault(key_, bng.MeshBuilder()).add(mat, Vt, uvs=uvs[s].reshape(-1, 2), normals=Nt)
    add(SIDEWALK, top, TUV, TN)
    add("mp_sidewalk_kerb", face, uv)

    # the objects on the pavements go up with them
    topc = Cover(top, np.ones(len(top)))
    tri_tree = topc.tree

    def lift(P, old=False):
        """Raise (m) of the pavement under each point (n, 2); 0 off the pavements. old: also the pavement's height
        before (nan off the pavements)."""
        P = np.asarray(P, np.float64).reshape(-1, 2)
        r = np.zeros(len(P))
        z0 = np.full(len(P), np.nan)
        if not len(P):
            return (r, z0) if old else r
        _, I = tri_tree.query(P, k=8)
        done = np.zeros(len(P), bool)
        for j in range(I.shape[1]):
            ii = I[:, j]
            a, b, c = T[ii, 0, :2], T[ii, 1, :2], T[ii, 2, :2]
            v0, v1, v2 = c - a, b - a, P - a
            d00, d01, d02 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v0 * v2).sum(1)
            d11, d12 = (v1 * v1).sum(1), (v1 * v2).sum(1)
            den = d00 * d11 - d01 * d01
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1.0)
            uu = (d11 * d02 - d01 * d12) / den
            vv = (d00 * d12 - d01 * d02) / den
            ins = ok & (uu >= -1e-6) & (vv >= -1e-6) & (uu + vv <= 1 + 1e-6) & ~done
            rv = raise_v[vid[ii]]
            r[ins] = (rv[:, 0] * (1 - uu - vv) + rv[:, 2] * uu + rv[:, 1] * vv)[ins]
            z0[ins] = (T[ii, 0, 2] * (1 - uu - vv) + T[ii, 2, 2] * uu + T[ii, 1, 2] * vv)[ins]
            done |= ins
        return (r, z0) if old else r

    files = {}
    with tempfile.TemporaryDirectory() as tmp:
        objs = []
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/sidewalks_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            fp = os.path.join(tmp, "s.dae")
            mb.write_dae(fp, name=f"sidewalks_{tx}_{ty}", origin=origin)
            files[f"{lv}/{rel}"] = open(fp, "rb").read()
            objs.append(bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=True))
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    for mt in materials():
        mats[mt["name"]] = mt
    files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    g_items = f"{lv}/main/MissionGroup/roads/sidewalks/items.level.json"
    for ob in objs:
        ob["__parent"] = "sidewalks"
    files[g_items] = ("\n".join(json.dumps(ob, separators=(",", ":")) for ob in objs) + "\n").encode("utf-8")
    r_items = f"{lv}/main/MissionGroup/roads/items.level.json"
    rows = read_items(zi, r_items)
    if not any(r.get("name") == "sidewalks" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "sidewalks", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"})
    files[r_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")

    # the props merged into one shape per tile (position z 0, the geometry in world coordinates): every piece of it
    # (corners joined by its triangles) that stands on a pavement goes up with it
    rep["merged_pieces_raised"] = 0
    for name in zi.namelist():
        if not name.endswith("items.level.json") or not any(f"/MissionGroup/{g}/" in name for g in OBJ_GROUPS):
            continue
        for o in read_items(zi, name):
            pos, sn = o.get("position"), o.get("shapeName", "").lstrip("/")
            if not (isinstance(pos, list) and len(pos) == 3 and pos[2] == 0) or sn not in zi.NameToInfo \
                    or o.get("rotationMatrix") not in (None, [1, 0, 0, 0, 1, 0, 0, 0, 1]) \
                    or o.get("scale") not in (None, [1, 1, 1]):
                continue
            text = zi.read(sn).decode("utf-8")
            m = re.search(r'(<float_array id="g-pa" count="\d+">)([^<]*)(</float_array>)', text)
            if not m:
                continue
            V = np.array(m.group(2).split(), np.float64).reshape(-1, 3)
            W = V + np.asarray(pos, np.float64)
            dz_v, z0_v = lift(W[:, :2], old=True)
            if not (dz_v > 0.005).any():
                continue
            _, _, _, _, parts, _ = optimize_level.parse(text)
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            tri = np.concatenate([idx[:, 0].reshape(-1, 3) for _, idx in parts])
            ei = np.r_[tri[:, 0], tri[:, 1], tri[:, 2]]
            ej = np.r_[tri[:, 1], tri[:, 2], tri[:, 0]]
            _, comp = connected_components(coo_matrix((np.ones(len(ei)), (ei, ej)), shape=(len(V), len(V))),
                                           directed=False)
            add = np.zeros(len(V))
            n = 0
            for cid in np.unique(comp[dz_v > 0.005]):
                k = np.flatnonzero(comp == cid)
                lo = k[W[k, 2] <= W[k, 2].min() + 0.05]          # the piece's feet
                ext = np.ptp(W[k, :2], axis=0).max()
                if ext > PIECE_MAX or not np.isfinite(z0_v[lo]).all() or \
                        not (-1.0 < (W[lo, 2] - z0_v[lo])).all() or ((W[lo, 2] - z0_v[lo]) > 0.25).any():
                    continue                    # not standing in the pavement (posts go down into it), or too long
                add[k] = dz_v[lo].max()
                n += 1
            if n:
                V[:, 2] += add
                rep["merged_pieces_raised"] += n
                arr = " ".join("%.4f" % v for v in V.reshape(-1))
                files[sn] = (text[:m.start(2)] + arr + text[m.end(2):]).encode("utf-8")

    # objects: TSStatics and prefabs of the prop groups, the items of the forest files
    for name in zi.namelist():
        if not name.endswith("items.level.json") or not any(f"/MissionGroup/{g}/" in name for g in OBJ_GROUPS):
            continue
        rows = read_items(zi, name)
        # not the shapes merged per tile (their position is the tile's middle at z 0, the geometry in world heights)
        mine = [isinstance(r.get("position"), list) and len(r["position"]) == 3 and r["position"][2] != 0
                for r in rows]
        P = [r["position"][:2] for r, m in zip(rows, mine) if m]
        if not P:
            continue
        dzv = iter(lift(P))
        n = 0
        for r, m in zip(rows, mine):
            if m:
                dz = float(next(dzv))
                if dz > 0.005:
                    r["position"] = [r["position"][0], r["position"][1], round(r["position"][2] + dz, 4)]
                    n += 1
        if n:
            rep["objects_raised"] += n
            files[name] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    for name in zi.namelist():
        if not (name.startswith(f"{lv}/forest/") and name.endswith(".forest4.json")):
            continue
        lines = zi.read(name).decode("utf-8").splitlines()
        rows = [json.loads(s) for s in lines if s.strip()]
        P = [r["pos"][:2] for r in rows]
        if not P:
            continue
        dzv = lift(P)
        if not (dzv > 0.005).any():
            continue
        for r, dz in zip(rows, dzv):
            if dz > 0.005:
                r["pos"] = [r["pos"][0], r["pos"][1], round(r["pos"][2] + float(dz), 4)]
        rep["forest_raised"] += int((dzv > 0.005).sum())
        files[name] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")

    gone = {"/" + n for n, dd in new_dae.items() if dd is None}
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
    print("sidewalks:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    sidewalks_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
