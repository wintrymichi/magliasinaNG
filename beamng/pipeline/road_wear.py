"""Wear of the asphalt: tyre tracks, patches and dirty edges of the carriageways (v3.0), in the built level.

An asphalt road is never one even grey: where the wheels run, two bands per lane are darker and smoother
(the bitumen polished, oil and rubber), and along the edges, where nothing drives, dust, sand and leaves
gather in a lighter, browner band. Up to v2.8 the carriageways of the map were one texture from edge to
edge, the main reason they looked drawn rather than driven on.

The first v3 builds laid every band along the AI roads at their half width: the AI width is not the width
of the asphalt, so the dusty edges ran across the carriageway in the bends, across the mouths of the side
roads and through the roundabouts, two of them side by side where two roads meet (they looked like kerbs);
and their texture carried its opacity in the colour map, which the game draws opaque: sand-coloured bands
of 64 pixels across. Now:
- edges: along the real edges of the asphalt, the boundary of the carriageway faces of the level where
  nothing paved goes on at the same height (not the joints of two meshes, not the mouth of a drive or a
  yard flush with the road): a band EDGE_W m wide inward from the edge (narrower on narrow roads), on its own
  texture drawn here with a separate opacity map (t_wear_edge_o.data.png), EDGE_PX px across;
- tracks, patches and cracks: along the AI roads (their nodes with the lanes each way), but placed in the
  asphalt as measured across the road at every station (the distance from the axis to the edge of the
  carriageway faces on each side, smoothed): the lighter and darker patches of Italy over the carriageway
  (italy_asphalt_overlay_light), in every lane two tyre tracks TRACK_W m wide TRACK_GAP m apart (Italy's
  m_asphalt_trackwear; one pair in the middle of a road narrower than NARROW m), and on stretches of CRACK_LEN m
  now and then (one about every CRACK_EVERY m) Italy's cracked and patched asphalt (italy_road_cracks);
  none of them inside a junction (JUNCTION_PAD m beyond the carriageways of the roads that meet there), on a
  roundabout and its entries (ROUNDABOUT_PAD m around the ring OpenStreetMap maps), where the measured
  width jumps (a lay-by, a widening, the mouth of a side road) or where they would leave the asphalt.
Every layer at its own height, LIFT m over the top faces of the asphalt (the height of the face under it,
never the deck of a bridge above it). One mesh per TILE m tile in MissionGroup/roads/markings, without
collision; the textures in art/shapes/roads. Everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish road_wear
"""
import json, os, re, shutil, tempfile, time, zipfile
import numpy as np
from PIL import Image
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.spatial import cKDTree
import bng
import optimize_level
from config import LEVEL_NAME
from bld_textures import aniso_noise, to8
from markings_net import read_items, shape_tris, up_faces
from road_mesh import TriSurface

TILE = 512.0
ASPHALT = ("mp_road_asphalt", "mp_road_asphalt_fresh")       # the wear goes on these only (not setts, gravel)
# paved ground that goes on from the asphalt at its height: no dusty edge there (a drive, a yard); not the
# pavements and islands, at whose kerb the dust gathers
PAVED = ("mp_hard_asphalt", "mp_hard_sett", "mp_hard_cobble", "mp_path_paved",
         "mp_road_sett", "mp_road_cobble", "mp_path_sett", "mp_path_cobble", "mp_bridge_parapet")
TRACK_W = 0.75               # m, width of a tyre track
TRACK_GAP = 1.6              # m between the middles of the two tracks of a lane (a car's track width)
PAIR_W = TRACK_GAP + TRACK_W + 0.35   # m, the band that carries the two tracks of a lane
NARROW = 5.2                 # m: on narrower carriageways one pair of tracks in the middle
MIN_W = 2.6                  # m: no tracks or patches on narrower carriageways (paths, ramps)
STEP = 2.0                   # m between the stations of a band along an AI road
EDGE_W = 0.55                # m, the dusty band inward from the edge of the asphalt
EDGE_SHARE = 0.18            # of the local width of the road, at most (narrow lanes)
EDGE_STEP = 1.0              # m between the vertices of an edge band
EDGE_V = 8.0                 # m of edge per repeat of its texture
EDGE_PX = (128, 1024)        # its texture: px across the band, along it
EDGE_ALPHA = 0.40            # most opacity of the dust (at the edge)
EDGE_MIN = 6.0               # m: shorter edges get no band
OUT_TEST = 0.30              # m beyond an edge: carriageway there, the edge is a joint of two meshes
FLUSH_DZ = 0.04              # m: paved ground beyond the edge within this height goes on (a drive, a yard)
JUNCTION_PAD = 4.0           # m beyond the carriageways meeting at a junction: no tracks, patches, cracks
ROUNDABOUT_PAD = 10.0        # m around the ring of a roundabout
RING_PAD = 2.5               # m about the ring's line: the AI road of the ring itself
WIDTH_JUMP = 1.25            # m: a station whose measured width differs this much from the road's median is cut
MEASURE_MAX = 8.0            # m from the axis: the farthest an edge is looked for
CONT_DZ = 0.10               # m between two samples 0.25 m apart across the road: still the same asphalt
WIDTH_LOCAL = 15             # stations (30 m): a road widening through a bend follows its own local median
RING_SHARE = 0.6             # of an AI road's stations on a roundabout's ring: the ring itself
CROSS_IN = 0.4               # m: a band is cut where it lies this far inside the carriageway of another AI road
CROSS_ANGLE = 25.0           # degrees
MIN_PIECE = 6                # stations: shorter pieces of a band are left out
SHAPE = re.compile(r"art/shapes/roads/road_wear_[-+]\d+_[-+]\d+\.dae$")
# material: (lift m over the road, m of road per repeat of the texture for a band 1 m wide)
LAYER = {"mp_wear_variation": (0.006, 112.0 / 6.0), "mp_wear_cracks": (0.008, 16.0 / 4.0),
         "mp_wear_track": (0.010, 4.0), "mp_wear_edge": (0.012, None)}
CRACK_LEN = (15.0, 45.0)     # m, length of a cracked stretch
CRACK_EVERY = 160.0          # m of road per cracked stretch, on average
CRACK_W = 4.0                # m, width of a cracked stretch (Italy's), narrower on narrow roads


def textures(dst):
    """The edge texture: colour (t_wear_edge_b.color.png) and opacity (t_wear_edge_o.data.png); u across the
    band (0 at the edge of the asphalt), v along it over EDGE_V m. Dust and fine grit, lighter and browner than
    the asphalt, strongest at the edge and gone at the inner side, in patches along the road."""
    rng = np.random.default_rng(41)
    w, h = EDGE_PX
    u = (np.arange(w) + 0.5) / w
    px = h / EDGE_V                                                   # pixels per metre along the road
    along = aniso_noise(h, w, 1.2 * px, 0.5 * w, rng)                 # metre-long patches, never dashes
    ragged = aniso_noise(h, w, 0.25 * px, 0.06 * w, rng)              # the inner boundary frays
    speck = aniso_noise(h, w, 0.6, 0.6, rng)                          # grit
    reach = np.clip(0.75 + 0.18 * along + 0.10 * ragged, 0.35, 1.0)  # how far in the dust goes, along the road
    a = np.clip(1.0 - u[None, :] / reach, 0, 1) ** 1.2 * np.clip(u[None, :] / 0.04, 0, 1)
    a = np.clip(a * (0.75 + 0.15 * along + 0.12 * speck), 0, 1) * EDGE_ALPHA
    col = np.zeros((h, w, 3), np.float32) + np.array([0.39, 0.37, 0.33])
    col *= (1 + 0.10 * speck + 0.04 * along)[..., None]
    Image.fromarray(to8(col)).save(os.path.join(dst, "t_wear_edge_b.color.png"))
    Image.fromarray(to8(a)).save(os.path.join(dst, "t_wear_edge_o.data.png"))


def materials():
    import italy_mats as it
    t = f"/levels/{LEVEL_NAME}/art/shapes/roads"
    edge = bng.material("mp_wear_edge", f"{t}/t_wear_edge_b.color.png", roughness=0.95, extra=it.OVERLAY)
    edge["Stages"][0]["opacityMap"] = f"{t}/t_wear_edge_o.data.png"
    return [edge, it.material("mp_wear_track", "m_asphalt_trackwear", overlay=True),
            it.material("mp_wear_variation", "italy_asphalt_overlay_light", overlay=True),
            it.material("mp_wear_cracks", "italy_road_cracks", overlay=True)]


# ------------------------------------------------------------------ the edges of the asphalt
def outer_edges(A, Sa, Sall, Sp):
    """Boundary edges (k, 2, 3) of the asphalt top faces A that are the edge of the paved surface, each
    turned so that the asphalt lies on its left. Sa: the asphalt, Sall: all carriageway faces, Sp: the other
    paved faces (TriSurface)."""
    V = A.reshape(-1, 3)
    key = np.round(V[:, :2] * 200).astype(np.int64)                  # 5 mm: the corners of two faces are one
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    tri = vid.reshape(-1, 3)
    E = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    own = np.tile(np.arange(len(tri)), 3)
    corner = np.concatenate([np.full(len(tri), 2), np.full(len(tri), 0), np.full(len(tri), 1)])
    lo, hi = E.min(1), E.max(1)
    k = lo * (int(vid.max()) + 1) + hi
    _, first, cnt = np.unique(k, return_index=True, return_counts=True)
    b = first[cnt == 1]
    t = own[b]
    ia = np.where(b < len(tri), 0, np.where(b < 2 * len(tri), 1, 2))
    a3 = A[t, ia]
    b3 = A[t, (ia + 1) % 3]
    c3 = A[t, corner[b]]
    d = b3[:, :2] - a3[:, :2]
    left = d[:, 0] * (c3[:, 1] - a3[:, 1]) - d[:, 1] * (c3[:, 0] - a3[:, 0]) > 0
    a3, b3 = np.where(left[:, None], a3, b3), np.where(left[:, None], b3, a3)
    d = b3[:, :2] - a3[:, :2]
    L = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    nout = np.column_stack([d[:, 1], -d[:, 0]]) / L[:, None]            # right of the edge: outside
    m = 0.5 * (a3 + b3)
    q = m[:, :2] + nout * OUT_TEST
    zc = Sall.height(q[:, 0], q[:, 1], "near", zhint=m[:, 2])
    joint = np.isfinite(zc) & (np.abs(zc - m[:, 2]) < 0.15)
    zp = Sp.height(q[:, 0], q[:, 1], "near", zhint=m[:, 2])
    flush = np.isfinite(zp) & (np.abs(zp - m[:, 2]) < FLUSH_DZ)
    keep = ~joint & ~flush & (L > 1e-3)
    return np.stack([a3[keep], b3[keep]], 1)


def chains(E):
    """Polylines (n, 3) of the edges E (k, 2, 3), joined where one ends at the start of another."""
    if not len(E):
        return []
    P = E.reshape(-1, 3)
    key = np.round(P[:, :2] * 200).astype(np.int64)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    s, e = vid[0::2], vid[1::2]
    nxt = {}
    indeg = np.bincount(e, minlength=int(vid.max()) + 1)
    outdeg = np.bincount(s, minlength=int(vid.max()) + 1)
    for i, a in enumerate(s):
        nxt.setdefault(int(a), []).append(i)
    used = np.zeros(len(s), bool)
    out = []
    starts = [i for i in range(len(s)) if indeg[s[i]] != 1 or outdeg[s[i]] != 1]
    for i0 in starts + list(range(len(s))):
        if used[i0]:
            continue
        pts, i = [E[i0, 0]], i0
        while not used[i]:
            used[i] = True
            pts.append(E[i, 1])
            v = int(e[i])
            if indeg[v] != 1 or outdeg[v] != 1:
                break
            cand = [c for c in nxt.get(v, []) if not used[c]]
            if not cand:
                break
            i = cand[0]
        if len(pts) >= 2:
            out.append(np.array(pts))
    return out


def resample(P, step):
    seg = np.hypot(*np.diff(P[:, :2], axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    if s[-1] < step:
        return P[[0, -1]]
    sd = np.linspace(0, s[-1], int(np.ceil(s[-1] / step)) + 1)
    return np.column_stack([np.interp(sd, s, P[:, k]) for k in range(3)])


def edge_bands(A, Sa, Sall, Sp, stats):
    """Triangles and texture coordinates of the dusty bands along the edges of the asphalt A."""
    tris, uvs = [], []
    for C in chains(outer_edges(A, Sa, Sall, Sp)):
        L = float(np.hypot(*np.diff(C[:, :2], axis=0).T).sum())
        if L < EDGE_MIN:
            continue
        closed = np.hypot(*(C[0, :2] - C[-1, :2])) < 0.05
        P = resample(C, EDGE_STEP)
        if len(P) < 3:
            continue
        if len(P) >= 5:                                           # a light smoothing of the survey's corners
            k = 3
            sm = uniform_filter1d(P[:, :2], k, axis=0, mode="wrap" if closed else "nearest")
            if not closed:
                sm[0], sm[-1] = P[0, :2], P[-1, :2]
            P[:, :2] = sm
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])                   # into the asphalt
        # the width of the road here: how far in the asphalt goes (a narrow lane gets a narrow band)
        reach = np.full(len(P), 2 * MEASURE_MAX)
        for off in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
            q = P[:, :2] + Nl * off
            z = Sa.height(q[:, 0], q[:, 1], "near", zhint=P[:, 2])
            gone = ~(np.isfinite(z) & (np.abs(z - P[:, 2]) < 0.5)) & (reach > off)
            reach[gone] = off
        w = np.minimum(EDGE_W, EDGE_SHARE * reach)
        inner = P[:, :2] + Nl * (w + 0.02)[:, None]
        outer = P[:, :2] + Nl * 0.02
        zi = Sa.height(inner[:, 0], inner[:, 1], "near", zhint=P[:, 2])
        zo = Sa.height(outer[:, 0], outer[:, 1], "near", zhint=P[:, 2])
        ok = np.isfinite(zi) & np.isfinite(zo) & (np.abs(zi - P[:, 2]) < 0.3) & (np.abs(zo - P[:, 2]) < 0.3)
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
        v = s / EDGE_V
        lift = LAYER["mp_wear_edge"][0]
        Ri = np.column_stack([inner, zi + lift])
        Ro = np.column_stack([outer, zo + lift])
        e = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
        for a, b in zip(e[::2], e[1::2]):
            if b - a < 3:
                continue
            o, i_, vv = Ro[a:b], Ri[a:b], v[a:b]
            n1 = b - a - 1
            t = np.stack([o[:-1], o[1:], i_[1:], o[:-1], i_[1:], i_[:-1]], 1).reshape(-1, 3, 3)
            uv = np.stack([np.c_[np.zeros(n1), vv[:-1]], np.c_[np.zeros(n1), vv[1:]], np.c_[np.ones(n1), vv[1:]],
                           np.c_[np.zeros(n1), vv[:-1]], np.c_[np.ones(n1), vv[1:]], np.c_[np.ones(n1), vv[:-1]]],
                          1).reshape(-1, 3, 2)
            down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
            t[down] = t[down][:, ::-1]
            uv[down] = uv[down][:, ::-1]
            tris.append(t)
            uvs.append(uv)
            stats["edge_m"] += float(s[b - 1] - s[a])
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2))
    return np.concatenate(tris), np.concatenate(uvs)


# ------------------------------------------------------------------ the bands along the AI roads
class Carriageways:
    """The carriageways of all the AI roads, sampled every metre along their axes with their half widths:
    where a road meets another (a junction, a roundabout), its bands stop at the other's edge."""
    def __init__(self, roads):
        pts, half, rid, tang = [], [], [], []
        self.ends = []
        for k, road in enumerate(roads):
            nodes = np.asarray(road["nodes"], np.float64)
            if len(nodes) < 2:
                continue
            s = np.r_[0, np.cumsum(np.hypot(*np.diff(nodes[:, :2], axis=0).T))]
            sd = np.linspace(0, s[-1], max(int(np.ceil(s[-1])), 1) + 1)
            pts.append(np.column_stack([np.interp(sd, s, nodes[:, 0]), np.interp(sd, s, nodes[:, 1])]))
            half.append(np.interp(sd, s, nodes[:, 3]) / 2)
            tg = np.gradient(pts[-1], axis=0)
            tang.append(tg / np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9))
            rid.append(np.full(len(sd), k))
            self.ends += [(k, nodes[0, :2], nodes[0, 3] / 2), (k, nodes[-1, :2], nodes[-1, 3] / 2)]
        self.P, self.half, self.rid = np.concatenate(pts), np.concatenate(half), np.concatenate(rid)
        self.tang = np.concatenate(tang)
        self.tree = cKDTree(self.P)
        self.rmax = float(self.half.max())

    def junctions(self):
        """(n, 3): x, y, radius of every junction: the end of an AI road on or near another AI road (a T,
        a crossing, the ends of three roads at one point); the radius takes in the carriageways that meet."""
        out = []
        for k, p, h in self.ends:
            near = np.asarray(self.tree.query_ball_point(p, self.rmax + 1.5))
            if not len(near):
                continue
            near = near[self.rid[near] != k]
            d = np.hypot(*(self.P[near] - p).T)
            on = near[d < self.half[near] + 1.5]
            if not len(on):
                continue
            out.append((p[0], p[1], max(h, float(self.half[on].max())) * 1.2 + JUNCTION_PAD))
        return np.array(out).reshape(-1, 3)

    def inside_other(self, C, k):
        """(n,) bool: the points C (n, 2) of a band lie CROSS_IN m or more inside the carriageway of an AI road
        other than k that crosses it (more than CROSS_ANGLE off its direction)."""
        out = np.zeros(len(C), bool)
        T = np.gradient(C, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        cmax = np.cos(np.radians(CROSS_ANGLE))
        for i, near in enumerate(self.tree.query_ball_point(C, self.rmax)):
            if not near:
                continue
            near = np.asarray(near)
            near = near[(self.rid[near] != k) & (np.abs(self.tang[near] @ T[i]) < cmax)]
            if len(near):
                d = np.hypot(*(self.P[near] - C[i]).T)
                out[i] = bool((d < self.half[near] - CROSS_IN).any())
        return out


def roundabouts():
    """Shapely geometries of the roundabouts of OpenStreetMap: ROUNDABOUT_PAD m around their rings (where
    the entries carry no wear) and RING_PAD m about the rings themselves (an AI road along it is the ring);
    None without the extract."""
    import shapely
    import osm
    if not osm.available():
        return None
    ways, _ = osm.load()
    rings = [w["line"] for w in ways if w["tags"].get("junction") in ("roundabout", "circular")]
    mini = [shapely.Point(n["x"], n["y"]).buffer(6.0) for n in osm.load()[1]
            if n["tags"].get("highway") == "mini_roundabout"]
    geoms = [r.buffer(ROUNDABOUT_PAD) for r in rings] + mini
    if not geoms:
        return None
    g = shapely.union_all(geoms)
    on = shapely.union_all([r.buffer(RING_PAD) for r in rings]) if rings else shapely.Point(0, 0).buffer(0)
    shapely.prepare(g)
    shapely.prepare(on)
    return g, on


def measure(P, Nl, Sa, zhint):
    """Distance from the axis points P (n, 2) to the edge of the asphalt on the left and on the right (along
    the normals Nl), at most MEASURE_MAX; NaN where the axis itself is off the asphalt. The asphalt goes on
    while every sample is within CONT_DZ of the one before it (not of the axis: on the cross fall of a banked
    hairpin the far side of the road is half a metre under the axis, and was taken for its edge)."""
    offs = np.arange(0.0, MEASURE_MAX + 0.01, 0.25)
    n = len(P)
    out = np.full((2, n), np.nan)
    for si, sg in enumerate((1.0, -1.0)):
        Q = P[:, None, :] + sg * Nl[:, None, :] * offs[None, :, None]
        z = Sa.height(Q[..., 0].ravel(), Q[..., 1].ravel(), "near",
                      zhint=np.repeat(zhint, len(offs))).reshape(n, len(offs))
        alive = np.isfinite(z[:, 0]) & (np.abs(z[:, 0] - zhint) < 0.4)
        on_axis = alive.copy()
        d = np.zeros(n)
        zprev = np.where(alive, z[:, 0], zhint)
        for j in range(1, len(offs)):
            step = np.isfinite(z[:, j]) & (np.abs(z[:, j] - zprev) < CONT_DZ)
            alive &= step
            d[alive] = offs[j]
            zprev = np.where(alive, z[:, j], zprev)
        out[si] = np.where(on_axis, np.minimum(d + 0.125, MEASURE_MAX), np.nan)
    return out[0], out[1]


def road_bands(road, rng):
    """[(material, offsets (n,) left of the axis, widths (n,), stretches [(s0, s1)] or None)] of an AI road
    whose measured carriageway (left, right: (n,) distances to the edges) is given later; here the kinds."""
    nodes = np.asarray(road["nodes"], np.float64)
    ll, lr = road.get("lanesLeft"), road.get("lanesRight")
    lanes = (int(ll or 0) + int(lr or 0)) if ll is not None or lr is not None else 0
    L = float(np.hypot(*np.diff(nodes[:, :2], axis=0).T).sum())
    spans, s0 = [], rng.exponential(CRACK_EVERY)
    while s0 < L:
        s1 = s0 + rng.uniform(*CRACK_LEN)
        spans.append((s0, min(s1, L)))
        s0 = s1 + rng.exponential(CRACK_EVERY)
    return nodes, lanes, spans, rng.uniform(-0.3, 0.3)


def strip(C, width, zc, Nl, Sa, keep, lift, v_tile, s, min_piece=None):
    """Triangles and texture coordinates of a band of widths (n,) about the points C (n, 2) (heights zc) on the
    asphalt Sa, only where keep (n,) is true; u across the band, v along it."""
    tris, uvs = [], []
    e = np.flatnonzero(np.diff(np.r_[0, keep.astype(int), 0]))
    for a, b in zip(e[::2], e[1::2]):
        if b - a < (min_piece or MIN_PIECE):
            continue
        rows = []
        for k in (1, 0, -1):                                          # left side, middle, right side
            Q = C[a:b] + Nl[a:b] * (k * width[a:b] / 2)[:, None]
            z = zc[a:b] if k == 0 else Sa.height(Q[:, 0], Q[:, 1], "near", zhint=zc[a:b])
            z = np.where(np.isfinite(z), z, zc[a:b])
            rows.append(np.column_stack([Q, z + lift]))
        v = s[a:b] / v_tile
        n1 = b - a - 1
        ts, us = [], []
        for (Lr, uL), (Rr, uR) in (((rows[1], 0.5), (rows[2], 1.0)), ((rows[0], 0.0), (rows[1], 0.5))):
            ts.append(np.stack([Rr[:-1], Rr[1:], Lr[1:], Rr[:-1], Lr[1:], Lr[:-1]], 1))
            us.append(np.stack([np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uR), v[1:]], np.c_[np.full(n1, uL), v[1:]],
                                np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uL), v[1:]], np.c_[np.full(n1, uL), v[:-1]]], 1))
        t = np.concatenate(ts, 1).reshape(-1, 3, 3)
        uv = np.concatenate(us, 1).reshape(-1, 3, 2)
        down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
        t[down] = t[down][:, ::-1]
        uv[down] = uv[down][:, ::-1]
        tris.append(t)
        uvs.append(uv)
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2))
    return np.concatenate(tris), np.concatenate(uvs)


def lane_bands(road, k, Sa, cw, junc, jtree, rb, rng, stats):
    """[(material, triangles, uvs)] of the tracks, patches and cracks of AI road k."""
    import shapely
    nodes, lanes, spans, crack_shift = road_bands(road, rng)
    P = nodes[:, :2]
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    if s[-1] < 2 * STEP:
        return []
    sd = np.linspace(0, s[-1], int(np.ceil(s[-1] / STEP)) + 1)
    Pd = np.column_stack([np.interp(sd, s, P[:, 0]), np.interp(sd, s, P[:, 1])])
    zd = np.interp(sd, s, nodes[:, 2])
    T = np.gradient(Pd, axis=0)
    if len(T) >= 5:                                                   # no kinks at the corners of the AI nodes
        T = uniform_filter1d(T, 5, axis=0, mode="nearest")
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nl = np.column_stack([-T[:, 1], T[:, 0]])
    za = Sa.height(Pd[:, 0], Pd[:, 1], "near", zhint=zd)
    za = np.where(np.isfinite(za) & (np.abs(za - zd) < 1.5), za, np.nan)
    dl, dr = measure(Pd, Nl, Sa, np.where(np.isfinite(za), za, zd))
    ok = np.isfinite(za) & np.isfinite(dl) & np.isfinite(dr)
    if ok.sum() < 3:
        return []
    # smoothed widths: a median over 7 stations (14 m) where measured
    W = dl + dr
    Wm = float(np.nanmedian(W[ok]))
    if Wm < MIN_W:
        return []
    dl_s = np.where(ok, median_filter(np.where(ok, dl, Wm / 2), 7, mode="nearest"), np.nan)
    dr_s = np.where(ok, median_filter(np.where(ok, dr, Wm / 2), 7, mode="nearest"), np.nan)
    Ws = dl_s + dr_s
    # a jump of the width (a lay-by, the mouth of a side road) is cut; the widening of a bend, which lasts
    # as long as the bend, follows the local median and is kept (tight bends had no wear at all)
    Wloc = median_filter(np.where(ok, Ws, Wm), WIDTH_LOCAL, mode="nearest")
    keep = ok & ((np.abs(Ws - Wm) < WIDTH_JUMP) | (np.abs(Ws - Wloc) < WIDTH_JUMP))
    # the ring of a roundabout carries its own tracks and patches all round, across the mouths of its entries
    ring = rb is not None and shapely.contains_xy(rb[1], Pd[:, 0], Pd[:, 1]).mean() >= RING_SHARE
    min_piece = 3 if ring else MIN_PIECE                              # the ring comes in short pieces between entries
    if ring:
        stats["ring_roads"] += 1
    else:
        # not in a junction, nor on a roundabout and its entries
        if len(junc):
            d, j = jtree.query(Pd)
            keep &= d > junc[j, 2]
        if rb is not None:
            keep &= ~shapely.contains_xy(rb[0], Pd[:, 0], Pd[:, 1])
        keep &= ~cw.inside_other(Pd, k)
    if keep.sum() < min_piece:
        return []
    mid = (dl_s - dr_s) / 2                                           # the middle of the asphalt, left of the axis
    zc = np.where(np.isfinite(za), za, zd)
    out = []

    def lay(mat, off, width, inside):
        lift, per_m = LAYER[mat]
        C = Pd + Nl * np.nan_to_num(off)[:, None]
        zq = Sa.height(C[:, 0], C[:, 1], "near", zhint=zc)
        zq = np.where(np.isfinite(zq) & (np.abs(zq - zc) < 0.4), zq, zc)
        if not inside.any():
            return
        t, uv = strip(C, width, zq, Nl, Sa, inside, lift, per_m * float(np.nanmedian(width[inside])), sd, min_piece)
        if len(t):
            out.append((mat, t, uv))
            stats[mat[8:] + "_m"] += float(len(t) / 4 * STEP)
    # patches over the carriageway, 0.4 m in from both edges
    lay("mp_wear_variation", mid, np.maximum(Ws - 0.8, 1.6), keep & np.isfinite(Ws))
    # tyre tracks: a pair in the middle of every lane (one pair in the middle of a narrow road)
    n = lanes if lanes > 0 and Wm >= NARROW else (1 if Wm < NARROW else 2)
    lw = Ws / n
    for i in range(n):
        off = -dr_s + lw * (i + 0.5)
        width = np.minimum(PAIR_W, lw - 0.3)
        lay("mp_wear_track", off, width, keep & np.isfinite(off) & (width > 1.8))
    # cracked stretches
    inside = np.zeros(len(sd), bool)
    for a, b in spans:
        inside |= (sd >= a) & (sd <= b)
    cw_ = np.minimum(CRACK_W, Ws - 1.2)
    lay("mp_wear_cracks", mid + crack_shift * np.maximum(Ws - cw_ - 0.6, 0) / 2, cw_, keep & inside & (cw_ > 1.5))
    return out


def road_wear_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    import markings_net
    A = np.concatenate([up_faces(t) for m, t in surf.items() if m in ASPHALT])
    Sa = TriSurface(A)
    Sall = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in markings_net.CARRIAGE_MATS]))
    other = [up_faces(t) for m, t in surf.items() if m in PAVED]
    Sp = TriSurface(np.concatenate(other) if other else np.zeros((0, 3, 3)))
    stats = {"roads": 0, "ring_roads": 0, "track_m": 0.0, "edge_m": 0.0, "variation_m": 0.0, "cracks_m": 0.0}
    builders = {}

    def add(mat, t, uv):
        c = t.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(q) for q in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            V = t[m].reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=uv[m].reshape(-1, 2),
                                                            normals=np.repeat([[0, 0, 1.0]], len(V), 0))
    t, uv = edge_bands(A, Sa, Sall, Sp, stats)
    if len(t):
        add("mp_wear_edge", t, uv)
    print("road wear: edges %.1f km (%.0f s)" % (stats["edge_m"] / 1000, time.time() - t0), flush=True)
    roads = read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json")
    cw = Carriageways(roads)
    junc = cw.junctions()
    jtree = cKDTree(junc[:, :2]) if len(junc) else None
    rb = roundabouts()
    rng = np.random.default_rng(23)
    for k, road in enumerate(roads):
        if len(road.get("nodes", [])) < 2:
            continue
        bl = lane_bands(road, k, Sa, cw, junc, jtree, rb, rng, stats)
        if bl:
            stats["roads"] += 1
        for mat, t, uv in bl:
            add(mat, t, uv)
    stats["junctions"] = int(len(junc))
    tmp = tempfile.mkdtemp(prefix="magliaso_wear_")
    try:
        new_files = {}
        objs = []
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/road_wear_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(f, name=f"road_wear_{tx}_{ty}", origin=origin)
            text = open(f, encoding="utf-8").read()
            out, _ = optimize_level.optimize_dae([(text, np.zeros(3))], rel.split("art/shapes/", 1)[1])
            new_files[f"{lv}/{rel}"] = (out or text).encode("utf-8")
            objs.append(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False))
        textures(tmp)
        for name in ("t_wear_edge_b.color.png", "t_wear_edge_o.data.png"):
            new_files[f"{lv}/art/shapes/roads/{name}"] = open(os.path.join(tmp, name), "rb").read()
        mats_name = f"{lv}/art/shapes/roads/main.materials.json"
        mats = json.loads(zi.read(mats_name))
        for m in materials():
            mats[m["name"]] = m
        new_files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
        mk_items = f"{lv}/main/MissionGroup/roads/markings/items.level.json"
        mk = [o for o in read_items(zi, mk_items) if not SHAPE.search(o.get("shapeName", ""))]
        parent = next((o["__parent"] for o in mk if "__parent" in o), "markings")
        for o in objs:
            o["__parent"] = parent
        new_files[mk_items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in mk + objs) + "\n").encode("utf-8")
        with zi.writer() as zo:
            for i in zi.infolist():
                if i.filename in new_files or SHAPE.search(i.filename):
                    continue
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                zo.writestr(n, data, compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats.update(meshes=len(builders), seconds=round(time.time() - t0))
    for kind in ("track", "edge", "variation", "cracks"):
        stats[kind + "_km"] = round(stats.pop(kind + "_m") / 1000, 1)
    print("road wear:", stats, flush=True)
    if report:
        json.dump(stats, open(report, "w"), indent=1)
    return 0
