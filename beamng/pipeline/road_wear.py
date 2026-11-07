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
  none of them inside a junction a road ends at (JUNCTION_PAD m beyond the carriageways of the roads that meet
  there), on a roundabout and its entries (ROUNDABOUT_PAD m around the ring OpenStreetMap maps), where the
  measured width jumps for longer than BRIDGE_JUMP stations or where they would leave the asphalt. The AI roads
  that go on as one another (split at a bridge, a junction, a change of name) are joined first, so the bands
  run on through those points, through a T for the road that goes straight on and past a lay-by or the mouth
  of a side road (the first v3.0 broke them for 15 m at 1157 such points and 410 width jumps).
Every layer at its own height, LIFT m over the top faces of the asphalt, translucent with depth writes as Italy
draws them (italy_mats.OVERLAY: they take the shadows) (the height of the face under it,
never the deck of a bridge above it), and as high over the asphalt between its vertices too: rows of vertices at
most ROW_STEP m apart across a band, every triangle lifted where the crown or a crest of the road came through it
(clear_of: the v3.0 bands had holes in 1-5 % of their area), a triangle that would hang over a step of the road
left out; in every mesh the layers from the lowest up, the order the game draws them in. One mesh per TILE m tile in MissionGroup/roads/markings, without
collision; the textures in art/shapes/roads. Everything else is copied as it is.

v3.1: and what the photos say about the asphalt (road_age.py): older and newer stretches with sealed joints, patches,
crumbled edges, manholes and gullies, the joints with yards and setts (layers mp_wear_age_*, _patch, _frayed, _joint,
_seam, _drain_*), the cracks and light blotches off the new asphalt.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish road_wear
"""
import json, os, re, shutil, tempfile, time, zipfile
import numpy as np
from PIL import Image
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.spatial import cKDTree
import bng
import optimize_level
import road_age
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
RING_PAD = 9.0               # m about the ring's line: the AI road of the ring itself
WIDTH_JUMP = 1.25            # m: a station whose measured width differs this much from the road's median is cut
MEASURE_MAX = 8.0            # m from the axis: the farthest an edge is looked for
CONT_DZ = 0.10               # m between two samples 0.25 m apart across the road: still the same asphalt
WIDTH_LOCAL = 15             # stations (30 m): a road widening through a bend follows its own local median
RING_SHARE = 0.6             # of an AI road's stations on a roundabout's ring: the ring itself
JOIN_D = 1.0                 # m: two AI road ends this close are one point (the road goes on as another)
JOIN_ANGLE = 35.0            # degrees: the most a road may turn there to go on as the other
CROSS_IN = 0.4               # m: a band is cut where it lies this far inside the carriageway of another AI road
CROSS_ANGLE = 25.0           # degrees
CROSS_END = 1.5              # m beyond a band's half width: the end of a road reaching this far in only meets it
CROSS_WIDER = 0.25           # m of half width: a road this much wider keeps its bands across the other
BRIDGE_JUMP = 20             # stations (40 m): the longest jump of the width the bands go on past
BRIDGE_OFF = 3               # stations (6 m): the longest stretch off the asphalt they go on past
MIN_PIECE = 6                # stations: shorter pieces of a band are left out
ROW_STEP = 2.0               # m at most between the rows of vertices across a band
# where the faces of the road are higher between the vertices of a band (the crown, a crest, the joint of two
# meshes) the band was under them, the road over it: holes in the wear (1-5 % of the bands of the first v3.0).
# The band is checked at these points of every triangle (barycentric) and lifted where the road comes too close
CLEAR_AT = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5],
                     [.75, .25, 0], [.25, .75, 0], [0, .75, .25], [0, .25, .75], [.25, 0, .75], [.75, 0, .25],
                     [2 / 3, 1 / 6, 1 / 6], [1 / 6, 2 / 3, 1 / 6], [1 / 6, 1 / 6, 2 / 3]])
CLEAR_MAX = 0.10             # m: a face higher than this over the band is another level (a bridge), not its road
FLOAT_MAX = 0.10             # m: a triangle of a band this high over the road somewhere spans a step of the road
                             # (the band would hang over the lower side like a sheet): left out
SHAPE = re.compile(r"art/shapes/roads/road_wear_[-+]\d+_[-+]\d+\.dae$")
# material: (lift m over the road, m of road per repeat of the texture for a band 1 m wide)
LAYER = {"mp_wear_variation": (0.006, 112.0 / 6.0), "mp_wear_cracks": (0.008, 16.0 / 4.0),
         "mp_wear_track": (0.010, 4.0), "mp_wear_edge": (0.012, None)}
LAYER.update({m: (road_age.LIFT[m], road_age.PER_M.get(m)) for m in road_age.LIFT})   # v3.1: road_age.py
KERB = ("mp_sidewalk", "mp_island")      # (mp_sidewalk_kerb, the stone faces of sidewalks.py, are not tops)        # beyond an edge: a kerb holds the asphalt (no crumbled edge there)
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
def outer_edges(A, Sa, Sall, Sp, flush_too=False, Sk=None):
    """Boundary edges (k, 2, 3) of the asphalt top faces A that are the edge of the paved surface, each
    turned so that the asphalt lies on its left. Sa: the asphalt, Sall: all carriageway faces, Sp: the other
    paved faces (TriSurface). flush_too: also the edges where paved ground goes on at the asphalt's height (v3.1:
    the joint of the carriageway with a yard, a drive, setts)."""
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
    if flush_too:
        f = ~joint & flush & (L > 1e-3)
        zk = Sk.height(q[:, 0], q[:, 1], "near", zhint=m[:, 2])         # a kerb: a pavement, an island beyond
        k = np.isfinite(zk) & (np.abs(zk - m[:, 2]) < 0.4) & (L > 1e-3)
        return np.stack([a3[keep], b3[keep]], 1), np.stack([a3[f], b3[f]], 1), np.stack([a3[k], b3[k]], 1)
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
            t, ok = clear_of(t, Sa, lift)
            tris.append(t[ok])
            uvs.append(uv[ok])
            stats["edge_m"] += float(s[b - 1] - s[a])
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2))
    return np.concatenate(tris), np.concatenate(uvs)


def edge_strip(P, Nl, w, mask, lift, v_tile, Sa, min_n=3):
    """Triangles and uvs of a band of widths w (n,) inward (Nl) from the edge points P (n, 3) where mask: u 0 at
    the edge, 1 inside, v along over v_tile m (as edge_bands)."""
    tris, uvs = [], []
    inner = P[:, :2] + Nl * (w + 0.02)[:, None]
    outer = P[:, :2] + Nl * 0.02
    zi = Sa.height(inner[:, 0], inner[:, 1], "near", zhint=P[:, 2])
    zo = Sa.height(outer[:, 0], outer[:, 1], "near", zhint=P[:, 2])
    ok = mask & np.isfinite(zi) & np.isfinite(zo) & (np.abs(zi - P[:, 2]) < 0.3) & (np.abs(zo - P[:, 2]) < 0.3)
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
    v = s / v_tile
    Ri = np.column_stack([inner, zi + lift])
    Ro = np.column_stack([outer, zo + lift])
    length = 0.0
    e = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
    for a, b in zip(e[::2], e[1::2]):
        if b - a < min_n:
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
        t, k = clear_of(t, Sa, lift)
        tris.append(t[k])
        uvs.append(uv[k])
        length += float(s[b - 1] - s[a])
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2)), 0.0
    return np.concatenate(tris), np.concatenate(uvs), length


def edge_extras(A, Sa, Sall, Sp, Sk, survey, stats):
    """v3.1 (road_age.py), along the edges of the asphalt: a crumbled edge where the asphalt is old and no kerb
    holds it, a gully at every low point of a kerbed edge, a sealed joint where the carriageway meets a yard, a
    drive or setts at its height. Returns ({material: [(triangles, uvs)]}, gullies [(xy, tangent)], the edge
    points (m, 2) with their inward normals (m, 2) and kerb flags (m,): where Mapillary's gullies are snapped)."""
    out, gullies, pts, nrm, kerbs = {}, [], [], [], []
    E, F, K = outer_edges(A, Sa, Sall, Sp, flush_too=True, Sk=Sk)
    sag_n = int(10 / EDGE_STEP)
    for C in chains(E):
        if float(np.hypot(*np.diff(C[:, :2], axis=0).T).sum()) < EDGE_MIN:
            continue
        P = resample(C, EDGE_STEP)
        if len(P) < 5:
            continue
        P[:, :2] = uniform_filter1d(P[:, :2], 3, axis=0, mode="nearest")
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        q = P[:, :2] - Nl * 0.35
        zk = Sk.height(q[:, 0], q[:, 1], "near", zhint=P[:, 2])
        kerb = np.isfinite(zk) & (np.abs(zk - P[:, 2]) < 0.4)
        kerb = median_filter(kerb.astype(np.uint8), 5, mode="nearest").astype(bool)
        pts.append(P[:, :2])
        nrm.append(Nl)
        kerbs.append(kerb)
        # the edge is on the right of the road as seen along the chain (the asphalt on its left)
        age = survey.query(P[:, :2] + Nl * 1.5, T, bound=4.0)[1] if survey is not None else np.zeros(len(P), np.int8)
        fray = ~kerb & (age == road_age.OLD)
        if fray.sum() >= 8:
            lift, per_m = LAYER["mp_wear_frayed"]
            t, uv, length = edge_strip(P, Nl, np.full(len(P), 0.45), fray, lift, per_m * 0.45, Sa, 8)
            if len(t):
                out.setdefault("mp_wear_frayed", []).append((t, uv))
                stats["frayed_m"] = stats.get("frayed_m", 0.0) + length
    # low points of a kerbed edge: the water of the road runs there
    for C in chains(K):
        P = resample(C, EDGE_STEP)
        if len(P) <= 2 * sag_n:
            continue
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        pts.append(P[:, :2])
        nrm.append(Nl)
        kerbs.append(np.ones(len(P), bool))
        z = uniform_filter1d(P[:, 2], 5, mode="nearest")
        for i in range(sag_n, len(P) - sag_n):
            if z[i] > z[i - sag_n:i + sag_n + 1].min():
                continue
            if z[i - sag_n] - z[i] >= road_age.DRAIN_SAG and z[i + sag_n] - z[i] >= road_age.DRAIN_SAG:
                gullies.append((P[i, :2] + Nl[i] * (0.06 + road_age.GRATE / 2), T[i]))
    for C in chains(F):
        if float(np.hypot(*np.diff(C[:, :2], axis=0).T).sum()) < 1.5:
            continue
        P = resample(C, 0.5)
        if len(P) < 3:
            continue
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        lift, per_m = LAYER["mp_wear_seam"]
        t, uv, length = edge_strip(P, Nl, np.full(len(P), road_age.SEAM_W), np.ones(len(P), bool), lift,
                                   per_m * road_age.SEAM_W, Sa)
        if len(t):
            out.setdefault("mp_wear_seam", []).append((t, uv))
            stats["transition_m"] = stats.get("transition_m", 0.0) + length
    cat = lambda xs, d: np.concatenate(xs) if xs else np.zeros((0,) + d)
    return out, gullies, (cat(pts, (2,)), cat(nrm, (2,)), cat(kerbs, ()).astype(bool))


def top_height(S, Q):
    """Heights (n,) of the faces S at the points Q (n, 2): the face nearest to the top one at the first point (the
    photos see the top surface; a deck over a road is not mixed with the road under it)."""
    z0 = S.height(Q[:1, 0], Q[:1, 1], "high")
    return S.height(Q[:, 0], Q[:, 1], "near", zhint=np.full(len(Q), z0[0])) if np.isfinite(z0[0]) else \
        np.full(len(Q), np.nan)


def patches(survey, Sa, stats):
    """[(material, triangles, uvs)] of the patches of the photos (road_age.Survey.patches): a rectangle of patch
    asphalt with a sealed seam round it, where it lies whole on the asphalt."""
    out = []
    lift, per_m = LAYER["mp_wear_patch"]
    jl, jper = LAYER["mp_wear_joint"]
    for p in survey.patches if survey is not None else []:
        c, t, L, W = p["xy"], p["t"], p["along"], p["across"]
        n = np.array([-t[1], t[0]])
        corners = np.array([c + t * a * L / 2 + n * b * W / 2 for a in (-1, 1) for b in (-1, 1)] + [c])
        z = top_height(Sa, corners)
        if not np.isfinite(z).all() or np.ptp(z) > 0.4:
            continue
        k = max(int(np.ceil(L / 0.5)), 2)
        f = np.linspace(-L / 2, L / 2, k + 1)
        C = c[None, :] + t[None, :] * f[:, None]
        Nl = np.repeat(n[None, :], len(C), 0)
        zc = Sa.height(C[:, 0], C[:, 1], "near", zhint=np.full(len(C), z[-1]))
        zc = np.where(np.isfinite(zc), zc, z[-1])
        tr, uv, _ = strip(C, np.full(len(C), W), zc, Nl, Sa, np.ones(len(C), bool), lift, per_m * W, f - f[0], 2)
        if not len(tr):
            continue
        out.append(("mp_wear_patch", tr, uv))
        # the seam: both long sides, both ends
        for sg in (-1, 1):
            Cs = C + n[None, :] * sg * W / 2
            zs = Sa.height(Cs[:, 0], Cs[:, 1], "near", zhint=zc)
            tr, uv, _ = strip(Cs, np.full(len(C), road_age.JOINT_W), np.where(np.isfinite(zs), zs, zc), Nl, Sa,
                              np.ones(len(C), bool), jl, jper * road_age.JOINT_W, f - f[0], 2)
            if len(tr):
                out.append(("mp_wear_joint", tr, uv))
            out.extend(joint_line(c + t * sg * L / 2, t, n, 0.0, W + road_age.JOINT_W, z[-1], Sa, {}))
        stats["patches"] = stats.get("patches", 0) + 1
    return out


def drains(Sa, gullies, edge_pts, stats):
    """[(material, triangles, uvs)] of the manholes and gullies: Mapillary's (snapped onto the asphalt, a gully to
    the nearest edge within road_age.SNAP m, a kerbed one first) and the gullies at the low points of the edges."""
    P, N, K = edge_pts
    tree = cKDTree(P) if len(P) else None
    items = []                                                        # (material, xy, tangent, size)
    for d in road_age.mapillary_drains():
        c = np.array([d["x"], d["y"]], float)
        if d["v"] == "catch-basin":
            if tree is None:
                continue
            near = tree.query_ball_point(c, road_age.SNAP)
            if not near:
                continue
            near = np.asarray(near)
            kn = near[K[near]] if K[near].any() else near
            j = kn[np.argmin(np.hypot(*(P[kn] - c).T))]
            t = np.array([N[j, 1], -N[j, 0]])
            items.append(("mp_wear_drain_grate", P[j] + N[j] * (0.06 + road_age.GRATE / 2), t, road_age.GRATE, "mly"))
        else:
            # onto the asphalt, at least 0.6 m in from its edge: the nearest such point within SNAP m
            g = np.arange(-road_age.SNAP, road_age.SNAP + 0.01, 0.5)
            Q = (c[None, :] + np.stack(np.meshgrid(g, g), -1).reshape(-1, 2))
            Q = Q[np.hypot(*(Q - c).T) <= road_age.SNAP]
            Q = Q[np.argsort(np.hypot(*(Q - c).T))]
            ring = np.array([[np.cos(a), np.sin(a)] for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]) * 0.6
            for q in Q:
                R = np.vstack([q, q + ring])
                z = top_height(Sa, R)
                if np.isfinite(z).all() and np.ptp(z) < 0.15:
                    items.append(("mp_wear_drain_cover", q, np.array([1.0, 0.0]), road_age.COVER, "mly"))
                    break
    for c, t in gullies:
        items.append(("mp_wear_drain_grate", c, t, road_age.GRATE, "sag"))
    out, placed = [], []
    for mat, c, t, size, src in items:
        if placed and np.min(np.hypot(*(np.asarray(placed) - c).T)) < road_age.DRAIN_GAP:
            continue
        n = np.array([-t[1], t[0]])
        corners = np.array([c - t * size / 2 - n * size / 2, c + t * size / 2 - n * size / 2,
                            c + t * size / 2 + n * size / 2, c - t * size / 2 + n * size / 2])
        z = top_height(Sa, corners)
        if not np.isfinite(z).all() or np.ptp(z) > 0.15:
            continue
        tr, uv = road_age.quad(c, t, size, size, z + LAYER[mat][0])
        tr, keep = clear_of(tr, Sa, LAYER[mat][0])
        if not keep.all():
            continue
        out.append((mat, tr, uv))
        placed.append(c)
        key = "drains_" + src + "_" + mat.rsplit("_", 1)[1]
        stats[key] = stats.get(key, 0) + 1
    return out


# ------------------------------------------------------------------ the bands along the AI roads
class Carriageways:
    """The carriageways of all the AI roads, sampled every metre along their axes with their half widths:
    where a road meets another (a junction, a roundabout), its bands stop at the other's edge."""
    def __init__(self, roads):
        pts, half, rid, tang, end_d = [], [], [], [], []
        self.ends = []                                                # (road, point, half width, end 0/1)
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
            end_d.append(np.minimum(sd, sd[-1] - sd))
            self.ends += [(k, nodes[0, :2], nodes[0, 3] / 2, 0), (k, nodes[-1, :2], nodes[-1, 3] / 2, 1)]
        self.P, self.half, self.rid = np.concatenate(pts), np.concatenate(half), np.concatenate(rid)
        self.tang, self.end_d = np.concatenate(tang), np.concatenate(end_d)
        self.tree = cKDTree(self.P)
        self.rmax = float(self.half.max())

    def junctions(self, joined=()):
        """(n, 4): x, y, radius and road of every junction: the end of an AI road on or near another AI road (a
        T, a crossing, the ends of three roads at one point); the radius takes in the carriageways that meet.
        Not the ends in joined ((road, end) pairs, see continuations): there the road just goes on."""
        out = []
        for k, p, h, e in self.ends:
            if (k, e) in joined:
                continue
            near = np.asarray(self.tree.query_ball_point(p, self.rmax + 1.5))
            if not len(near):
                continue
            near = near[self.rid[near] != k]
            d = np.hypot(*(self.P[near] - p).T)
            on = near[d < self.half[near] + 1.5]
            if not len(on):
                continue
            out.append((p[0], p[1], max(h, float(self.half[on].max())) * 1.2 + JUNCTION_PAD, k))
        return np.array(out).reshape(-1, 4)

    def inside_other(self, C, k, half):
        """(n,) bool: the points C (n, 2) of a band of AI road k (half widths half (n,)) lie CROSS_IN m or more
        inside the carriageway of another AI road that crosses it (more than CROSS_ANGLE off its direction) and
        goes on across it: not the end of a side road reaching into it (the tracks of the road going on broke
        for 2-4 m at 700 such ends), and not a narrower road (the wider one keeps its bands across a crossing;
        of two as wide, the one listed first)."""
        out = np.zeros(len(C), bool)
        T = np.gradient(C, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        cmax = np.cos(np.radians(CROSS_ANGLE))
        for i, near in enumerate(self.tree.query_ball_point(C, self.rmax)):
            if not near:
                continue
            near = np.asarray(near)
            near = near[(self.rid[near] != k) & (np.abs(self.tang[near] @ T[i]) < cmax)
                        & (self.end_d[near] > half[i] + CROSS_END)
                        & ((self.half[near] > half[i] + CROSS_WIDER)
                           | ((np.abs(self.half[near] - half[i]) <= CROSS_WIDER) & (self.rid[near] < k)))]
            if len(near):
                d = np.hypot(*(self.P[near] - C[i]).T)
                out[i] = bool((d < self.half[near] - CROSS_IN).any())
        return out


    def continuations(self, roads, rings=frozenset()):
        """The (road, end) pairs where an AI road goes on as another one: two ends of two roads at one point
        (within JOIN_D m), running on within JOIN_ANGLE degrees of each other, with the same lanes; where three
        or four ends meet (a T, a crossing, the main road split there), the straightest such pairs. The network
        splits its roads at bridges, at a change of name or speed limit and at every junction: the first v3.0
        took every such point for a junction and broke all the wear of the road going on for 15 m there.
        A road of a roundabout's ring (rings: their indices) goes on only as another one of the ring."""
        E = np.array([e[1] for e in self.ends]).reshape(-1, 2)
        tree = cKDTree(E)
        joined, links, seen = set(), [], set()
        for i in range(len(E)):
            if i in seen:
                continue
            group = sorted(tree.query_ball_point(E[i], JOIN_D))
            seen |= set(group)
            if not 2 <= len(group) <= 4 or len({self.ends[g][0] for g in group}) < len(group):
                continue
            d = {}
            for g in group:
                k, _, _, e = self.ends[g]
                n = np.asarray(roads[k]["nodes"], float)
                d[g] = self._away(n if e == 0 else n[::-1])        # leaving the point along the road, ~5 m in
            pairs = []
            for x in range(len(group)):
                for y in range(x + 1, len(group)):
                    gi, gj = group[x], group[y]
                    (ki, _, _, ei), (kj, _, _, ej) = self.ends[gi], self.ends[gj]
                    if d[gi] is None or d[gj] is None:
                        continue
                    if (ki in rings) != (kj in rings):
                        continue
                    straight = -float(d[gi] @ d[gj])
                    if straight >= np.cos(np.radians(JOIN_ANGLE)) and \
                            lane_key(roads[ki], ei == 1) == lane_key(roads[kj], ej == 0):
                        pairs.append((straight, gi, gj))
            used = set()
            for _, gi, gj in sorted(pairs, reverse=True):
                if gi in used or gj in used:
                    continue
                used |= {gi, gj}
                (ki, _, _, ei), (kj, _, _, ej) = self.ends[gi], self.ends[gj]
                joined |= {(ki, ei), (kj, ej)}
                links.append(((ki, ei), (kj, ej)))
        return joined, links

    @staticmethod
    def _away(nodes):
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(nodes[:, :2], axis=0).T))]
        if s[-1] < 0.5:
            return None
        q = np.array([np.interp(min(5.0, s[-1]), s, nodes[:, 0]), np.interp(min(5.0, s[-1]), s, nodes[:, 1])])
        d = q - nodes[0, :2]
        return d / max(np.linalg.norm(d), 1e-9)


def lane_key(road, forward):
    """The lanes of an AI road (left, right) as seen running along it (forward) or against it."""
    ll, lr = road.get("lanesLeft"), road.get("lanesRight")
    return (ll, lr) if forward else (lr, ll)


def joined_roads(roads, links):
    """The AI roads joined into one where they go on as another (links: ((road, end), (road, end)) pairs):
    [(road dict with the nodes of the whole run, [member road indices])]. The wear runs on along them without a
    break, its texture without a seam."""
    nb = {}
    for a, b in links:
        nb[a], nb[b] = b, a
    done, out = set(), []

    def walk(k, e):
        """Members (road, reversed) from road k entered at its end e."""
        run = []
        while k not in done:
            done.add(k)
            run.append((k, e == 1))                                   # entered at its end: run it backwards
            nxt = nb.get((k, 1 - e))
            if nxt is None:
                break
            k, e = nxt
        return run
    starts = [k for k in range(len(roads)) if (k, 0) not in nb or (k, 1) not in nb]
    for k in starts + list(range(len(roads))):                        # open runs first, then closed loops
        if k in done:
            continue
        e = 0 if (k, 0) not in nb else 1
        run = walk(k, e)
        nodes, members = [], []
        for m, rev in run:
            n = list(roads[m]["nodes"])
            n = n[::-1] if rev else n
            nodes += n if not nodes else n[1:]
            members.append(m)
        first, rev0 = run[0]
        r = dict(roads[first])
        r["nodes"] = nodes
        r["lanesLeft"], r["lanesRight"] = lane_key(roads[first], not rev0)
        out.append((r, members))
    return out


def ring_roads(roads, rb):
    """The indices of the AI roads that run round a roundabout's ring (on_ring)."""
    if rb is None:
        return frozenset()
    out = set()
    for k, road in enumerate(roads):
        n = np.asarray(road.get("nodes", []), float).reshape(-1, 4)
        if len(n) < 2:
            continue
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(n[:, :2], axis=0).T))]
        sd = np.linspace(0, s[-1], max(int(np.ceil(s[-1] / STEP)), 1) + 1)
        P = np.column_stack([np.interp(sd, s, n[:, 0]), np.interp(sd, s, n[:, 1])])
        T = np.gradient(P, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        if on_ring(P, T, rb[1]):
            out.add(k)
    return frozenset(out)


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
    shapely.prepare(g)
    return g, (shapely.union_all(rings) if rings else None)


def on_ring(P, T, ring):
    """Whether an AI road (stations P, unit tangents T) runs round a roundabout's ring (the rings' lines): most of
    its stations within RING_PAD m of a ring and running along it (not across it, as the entries do). The AI
    road of a ring runs in its lane, a few metres off the line OpenStreetMap maps."""
    import shapely
    if ring is None:
        return False
    d = shapely.distance(ring, shapely.points(P))
    near = d < RING_PAD
    if near.mean() < RING_SHARE:
        return False
    Q = np.asarray([ring.interpolate(ring.project(shapely.Point(p))).coords[0] for p in P[near]])
    Q2 = np.asarray([ring.interpolate(ring.project(shapely.Point(p)) + 1.0).coords[0] for p in P[near]])
    Tr = Q2 - Q
    Tr /= np.maximum(np.linalg.norm(Tr, axis=1, keepdims=True), 1e-9)
    return float(np.mean(np.abs((Tr * T[near]).sum(1)) > 0.8)) >= RING_SHARE


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


def bridge(keep, ok, arrays):
    """(n,) bool: the stations of the gaps of keep (n,) between two kept stations that are filled: up to
    BRIDGE_JUMP stations where the asphalt was measured (ok, a jump of the width), up to BRIDGE_OFF anywhere.
    And the arrays (n,), interpolated over them from the stations either side."""
    out = np.zeros(len(keep), bool)
    e = np.flatnonzero(np.diff(np.r_[0, (~keep).astype(int), 0]))
    for a, b in zip(e[::2], e[1::2]):
        if a == 0 or b == len(keep):
            continue
        if b - a <= BRIDGE_OFF or (b - a <= BRIDGE_JUMP and ok[a:b].all()):
            out[a:b] = True
    vals = []
    for v in arrays:
        v = v.copy()
        if out.any():
            i = np.flatnonzero(keep & np.isfinite(v))
            v[out] = np.interp(np.flatnonzero(out), i, v[i])
        vals.append(v)
    return out, vals


def clear_of(t, S, lift):
    """The triangles t (k, 3, 3) of a band (a soup: a corner of several triangles is one vertex) lifted so that
    at every point CLEAR_AT of every triangle the band is at least `lift` m over the faces S under it: each
    triangle's shortfall is added to its three corners (a vertex shared by several takes the largest), so the
    band stays whole. A face more than CLEAR_MAX m over the band is left out (the deck of a bridge above).
    Returns (triangles, keep (k,)): keep false for a triangle more than FLOAT_MAX m over the road somewhere."""
    if not len(t):
        return t, np.ones(0, bool)
    P = np.einsum("bk,tkd->tbd", CLEAR_AT, t)                         # (k, m, 3)
    x, y, z = P[..., 0].ravel(), P[..., 1].ravel(), P[..., 2].ravel()
    zs = S.height(x, y, "near", zhint=z - lift)
    short = np.where(np.isfinite(zs) & (zs - z < CLEAR_MAX - lift), zs + lift - z, 0.0).reshape(len(t), -1)
    up = np.maximum(short.max(1), 0.0)
    if up.any():
        key = np.round(t[..., :2].reshape(-1, 2) * 1e4).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.ravel()
        lift_v = np.zeros(inv.max() + 1)
        np.maximum.at(lift_v, inv, np.repeat(up, 3))
        t = t.copy()
        t[..., 2] += lift_v[inv].reshape(len(t), 3)
        z = np.einsum("bk,tk->tb", CLEAR_AT, t[..., 2]).ravel()            # the band's points, lifted
    over = np.where(np.isfinite(zs), z - lift - zs, 0.0).reshape(len(t), -1)
    return t, over.max(1) <= FLOAT_MAX


def strip(C, width, zc, Nl, Sa, keep, lift, v_tile, s, min_piece=None):
    """Triangles and texture coordinates of a band of widths (n,) about the points C (n, 2) (heights zc) on the
    asphalt Sa, only where keep (n,) is true; u across the band, v along it. Rows of vertices at most ROW_STEP
    m apart across it, the whole band clear of the asphalt (clear_of). Returns (triangles, uvs, m of band)."""
    tris, uvs, length = [], [], 0.0
    e = np.flatnonzero(np.diff(np.r_[0, keep.astype(int), 0]))
    for a, b in zip(e[::2], e[1::2]):
        if b - a < (min_piece or MIN_PIECE):
            continue
        m = max(2, 2 * int(np.ceil(float(np.nanmax(width[a:b])) / (2 * ROW_STEP))))   # an even number: a middle row
        rows = []
        for j in range(m + 1):                                       # left side, ..., middle, ..., right side
            f = 1 - 2 * j / m
            Q = C[a:b] + Nl[a:b] * (f * width[a:b] / 2)[:, None]
            z = zc[a:b] if 2 * j == m else Sa.height(Q[:, 0], Q[:, 1], "near", zhint=zc[a:b])
            z = np.where(np.isfinite(z), z, zc[a:b])
            rows.append(np.column_stack([Q, z + lift]))
        v = s[a:b] / v_tile
        n1 = b - a - 1
        ts, us = [], []
        for j in range(m):
            Lr, uL, Rr, uR = rows[j], j / m, rows[j + 1], (j + 1) / m
            ts.append(np.stack([Rr[:-1], Rr[1:], Lr[1:], Rr[:-1], Lr[1:], Lr[:-1]], 1))
            us.append(np.stack([np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uR), v[1:]], np.c_[np.full(n1, uL), v[1:]],
                                np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uL), v[1:]], np.c_[np.full(n1, uL), v[:-1]]], 1))
        t = np.concatenate(ts, 1).reshape(-1, 3, 3)
        uv = np.concatenate(us, 1).reshape(-1, 3, 2)
        down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
        t[down] = t[down][:, ::-1]
        uv[down] = uv[down][:, ::-1]
        t, ok = clear_of(t, Sa, lift)
        tris.append(t[ok])
        uvs.append(uv[ok])
        length += float(s[b - 1] - s[a])
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2)), 0.0
    return np.concatenate(tris), np.concatenate(uvs), length


def lane_bands(road, k, Sa, cw, junc, rb, rng, stats, survey=None):
    """[(material, triangles, uvs)] of the tracks, patches and cracks of the AI road k (as joined)."""
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
    # ... but the bands of the road go on past it at the width before and after (they stopped there, 410 times
    # over the map), and past a station or two off the asphalt (a joint, a gap of the survey)
    filled, (dl_s, dr_s, za) = bridge(keep, ok, (dl_s, dr_s, za))
    if filled.any():
        Ws = dl_s + dr_s
        keep |= filled
        stats["bridged_m"] += float(filled.sum() * STEP)
    # the ring of a roundabout carries its own tracks and patches all round, across the mouths of its entries
    ring = rb is not None and on_ring(Pd, T, rb[1])
    min_piece = 3 if ring else MIN_PIECE                              # the ring comes in short pieces between entries
    if ring:
        stats["ring_roads"] += 1
    else:
        # not in a junction it ends at (the road that runs on through a T keeps its bands across the mouth of
        # the side road: they stopped there in the first v3.0), nor on a roundabout and its entries
        for x, y, rad, _ in junc[junc[:, 3] == k]:
            keep &= np.hypot(Pd[:, 0] - x, Pd[:, 1] - y) > rad
        if rb is not None:
            keep &= ~shapely.contains_xy(rb[0], Pd[:, 0], Pd[:, 1])
        keep &= ~cw.inside_other(Pd, k, np.interp(sd, s, nodes[:, 3]) / 2)
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
        t, uv, length = strip(C, width, zq, Nl, Sa, inside, lift, per_m * float(np.nanmedian(width[inside])), sd,
                              min_piece)
        if len(t):
            out.append((mat, t, uv))
            stats[mat[8:] + "_m"] = stats.get(mat[8:] + "_m", 0.0) + length
    # v3.1: the age of the asphalt in the photos (road_age.py), per half of the road
    al, ar = survey.query(Pd, T) if survey is not None else np.zeros((2, len(Pd)), np.int8)
    new = (al == road_age.NEW) | (ar == road_age.NEW)
    old = (al == road_age.OLD) & (ar == road_age.OLD)
    same = al == ar
    full = np.maximum(Ws - 0.3, 1.0)
    lo, lw_ = (mid + dl_s - 0.15) / 2, dl_s - 0.15 - mid
    ro, rw_ = (mid - dr_s + 0.15) / 2, mid + dr_s - 0.15
    for mat, a in (("mp_wear_age_new", road_age.NEW), ("mp_wear_age_old", road_age.OLD)):
        lay(mat, mid, full, keep & same & (al == a))
        lay(mat, lo, lw_, keep & ~same & (al == a) & (lw_ > 0.8))
        lay(mat, ro, rw_, keep & ~same & (ar == a) & (rw_ > 0.8))
    # sealed joints: across the road (or its half) where new asphalt ends on the asphalt, along the axis where only
    # one half is new
    jw = np.full(len(sd), road_age.JOINT_W)
    lay("mp_wear_joint", mid, jw, keep & ~same & new)
    measured = ok | filled
    for side, (o, w) in ((al, (lo, lw_)), (ar, (ro, rw_))):
        nw = keep & (side == road_age.NEW)
        for i in np.flatnonzero(nw[:-1] != nw[1:]):
            if not (measured[i] and measured[i + 1]):
                continue
            both = same[i] and same[i + 1]
            if both and side is ar:
                continue                                              # one joint across the whole road
            oc, wc = (mid[i], full[i]) if both else (o[i], w[i])
            if not np.isfinite(oc) or not np.isfinite(wc) or wc < 0.8:
                continue
            c = 0.5 * (Pd[i] + Pd[i + 1])
            out.extend(joint_line(c, T[i], Nl[i], oc, wc, zc[i], Sa, stats))
    # patches over the carriageway, 0.4 m in from both edges (not on new asphalt)
    lay("mp_wear_variation", mid, np.maximum(Ws - 0.8, 1.6), keep & np.isfinite(Ws) & ~new)
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
    # v3.1: none on new asphalt, OLD_CRACKS times as many on old (their own draws: the rest of the map as it was)
    if old.any():
        r2, s0 = np.random.default_rng(1000 + k), 0.0
        s0 = r2.exponential(CRACK_EVERY / (road_age.OLD_CRACKS - 1))
        while s0 < sd[-1]:
            s1 = s0 + r2.uniform(*CRACK_LEN)
            inside |= (sd >= s0) & (sd <= s1) & old
            s0 = s1 + r2.exponential(CRACK_EVERY / (road_age.OLD_CRACKS - 1))
    cw_ = np.minimum(CRACK_W, Ws - 1.2)
    lay("mp_wear_cracks", mid + crack_shift * np.maximum(Ws - cw_ - 0.6, 0) / 2, cw_,
        keep & inside & (cw_ > 1.5) & ~new)
    return out


def joint_line(c, t, n, off, width, z, Sa, stats):
    """[(mp_wear_joint, triangles, uvs)] of a sealed joint across a road: centre c of the axis, its tangent t and
    left normal n, the joint from off - width / 2 to off + width / 2 left of the axis."""
    k = max(int(np.ceil(width / 0.25)), 2)
    f = np.linspace(-width / 2, width / 2, k + 1) + off
    C = c[None, :] + n[None, :] * f[:, None]
    zq = Sa.height(C[:, 0], C[:, 1], "near", zhint=np.full(len(C), z))
    zq = np.where(np.isfinite(zq) & (np.abs(zq - z) < 0.4), zq, z)
    Nl = np.repeat(-t[None, :], len(C), 0)                            # the strip runs along n: its left is -t
    lift, per_m = LAYER["mp_wear_joint"]
    s = f - f[0]
    tr, uv, length = strip(C, np.full(len(C), road_age.JOINT_W), zq, Nl, Sa, np.ones(len(C), bool), lift,
                           per_m * road_age.JOINT_W, s, 2)
    stats["joints"] = stats.get("joints", 0) + 1
    return [("mp_wear_joint", tr, uv)] if len(tr) else []


def no_asphalt(zi, lv, report):
    import italy_mats
    tmp = tempfile.mkdtemp(prefix="magliaso_wear_")
    try:
        textures(tmp)
        new_files = {f"{lv}/art/shapes/roads/{n}": open(os.path.join(tmp, n), "rb").read()
                     for n in ["t_wear_edge_b.color.png", "t_wear_edge_o.data.png"] + road_age.textures(tmp)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    mats = json.loads(zi.read(mats_name)) if mats_name in zi.NameToInfo else {}
    for m in materials() + road_age.materials(italy_mats.OVERLAY):
        mats[m["name"]] = m
    new_files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename not in new_files:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(new_files.items()):
            zo.writestr(n, data, compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
    print("road wear: no asphalt road in the level, overlay materials only", flush=True)
    if report:
        json.dump({"roads": 0}, open(report, "w"), indent=1)
    return 0


def road_wear_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    # v3.1: the pavements raised on their kerbs (sidewalks.py, a finishing step after this one, or the nightly patch
    # of the zip before it) are in roads/sidewalks: their tops are the kerbs here too, in either order
    sw = f"{lv}/main/MissionGroup/roads/sidewalks/items.level.json"
    if sw in zi.NameToInfo:
        for m, t in shape_tris(zi, lv, read_items(zi, sw)).items():
            surf[m] = np.concatenate([surf[m], t]) if m in surf else t
    import markings_net
    if not any(m in ASPHALT for m in surf):
        # a zone with no asphalt road (ti_2_7, paths only): no wear, only the overlay materials yard_wear reads
        return no_asphalt(zi, lv, report)
    A = np.concatenate([up_faces(t) for m, t in surf.items() if m in ASPHALT])
    Sa = TriSurface(A)
    Sall = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in markings_net.CARRIAGE_MATS]))
    other = [up_faces(t) for m, t in surf.items() if m in PAVED]
    Sp = TriSurface(np.concatenate(other) if other else np.zeros((0, 3, 3)))
    stats = {"roads": 0, "ring_roads": 0, "track_m": 0.0, "edge_m": 0.0, "variation_m": 0.0, "cracks_m": 0.0,
             "bridged_m": 0.0}
    pieces = {}                                                       # tile -> material -> [(t, uv)]

    def add(mat, t, uv):
        c = t.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(q) for q in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            pieces.setdefault(key, {}).setdefault(mat, []).append((t[m], uv[m]))
    t, uv = edge_bands(A, Sa, Sall, Sp, stats)
    if len(t):
        add("mp_wear_edge", t, uv)
    print("road wear: edges %.1f km (%.0f s)" % (stats["edge_m"] / 1000, time.time() - t0), flush=True)
    roads = read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json")
    # v3.1: what the photos say about the asphalt (road_age.py)
    survey = road_age.Survey(roads)
    survey = survey if survey.ok else None
    kerb = [up_faces(t) for m, t in surf.items() if m in KERB]
    Sk = TriSurface(np.concatenate(kerb) if kerb else np.zeros((0, 3, 3)))
    extra, gullies, edge_pts = edge_extras(A, Sa, Sall, Sp, Sk, survey, stats)
    for mat, parts in extra.items():
        for t, uv in parts:
            add(mat, t, uv)
    for mat, t, uv in patches(survey, Sa, stats) + drains(Sa, gullies, edge_pts, stats):
        add(mat, t, uv)
    print("road wear: age, joints, patches, drains (%.0f s)" % (time.time() - t0), flush=True)
    rb = roundabouts()
    joined, links = Carriageways(roads).continuations(roads, ring_roads(roads, rb))
    runs = [r for r, _ in joined_roads(roads, links)]
    cw = Carriageways(runs)                                           # the roads as they run on, joined
    junc = cw.junctions()
    rng = np.random.default_rng(23)
    stats["joined"] = len(links)
    for k, road in enumerate(runs):
        if len(road.get("nodes", [])) < 2:
            continue
        bl = lane_bands(road, k, Sa, cw, junc, rb, rng, stats, survey)
        if bl:
            stats["roads"] += 1
        for mat, t, uv in bl:
            add(mat, t, uv)
    stats["junctions"] = int(len(junc))
    # in every mesh the layers from the lowest to the highest: the game draws them in this order, and with depth
    # writes a layer drawn first would hide the parts of a lower one drawn after it under its triangles
    builders = {}
    for key, by_mat in pieces.items():
        mb = builders[key] = bng.MeshBuilder()
        for mat in sorted(by_mat, key=lambda m: LAYER[m][0]):
            for t, uv in by_mat[mat]:
                V = t.reshape(-1, 3)
                mb.add(mat, V, uvs=uv.reshape(-1, 2), normals=np.repeat([[0, 0, 1.0]], len(V), 0))
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
        for name in ["t_wear_edge_b.color.png", "t_wear_edge_o.data.png"] + road_age.textures(tmp):
            new_files[f"{lv}/art/shapes/roads/{name}"] = open(os.path.join(tmp, name), "rb").read()
        mats_name = f"{lv}/art/shapes/roads/main.materials.json"
        mats = json.loads(zi.read(mats_name))
        import italy_mats
        for m in materials() + road_age.materials(italy_mats.OVERLAY):
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
    for kind in [k[:-2] for k in stats if k.endswith("_m")]:
        stats[kind + "_km"] = round(stats.pop(kind + "_m") / 1000, 1)
    print("road wear:", stats, flush=True)
    if report:
        json.dump(stats, open(report, "w"), indent=1)
    return 0
