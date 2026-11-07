"""Far trees: the woods beyond the streamed Forest (forest.lua RADIUS, ~1.5-1.9 km) as static shapes, one per 384 m tile
(fartrees/t_<cx>_<cy>.cdae) and, further out, one per L2_TILES x L2_TILES tiles (fartrees/l2_<bx>_<by>.cdae), so the
woods go on to the horizon instead of ending in a line (michi 2026-11-01: "non puoi anche aumentare la distanza degli
alberi?", "gli alberi devono vedersi sempre come anche le case").

Why not more Forest: every frame that adds or removes Forest items cost the engine ~200 ms on the PC (2026-10-30/31,
whatever it added; BeamNG.Earth trees.lua: ~0.5 us for every item in the level of each shape touched), so more rings
of real trees would mean more such frames. A far-tree tile is a plain TSStatic with no collision, made like a far
ground tile (objects.lua stepFar), which costs a few ms.

A canopy, not cards. The woods are one surface over the far ground: a height field on the far ground's own 12 m grid
(farlod.Ground, the far tiles' heights; 24 m in the coarse tiles), standing on the ground by the height of the trees'
crowns, vertex coloured (no texture) and lit like the terrain by normals of its own heights. The first versions stood
a card (two crossed quads with a cut-out clump of trees, drawn from the Malcantone's far tree imposters) in every 28 m
cell: in the game they read as pale flat quads whatever their texture's colour and their normals, a dotted carpet on
the slopes, and on every ridge their even spacing drew a comb against the sky (PC photos from San Salvatore and
Paradiso, 2026-11-01). A wood seen from kilometres away is a dark rough mass, which is what a canopy surface is.

Per vertex: the far trees (the slices' tiles/t_<cx>_<cy>.trees.json rows, forest.lua's; no bushes, hedges, rails, nor
trees under MIN_H) in the box of 2 x 2 cells round it give crown cover (crown discs over the box), height (the trees'
heights weighted by their crowns, smoothed over the vertices round it: one tall tree is no spike) and kind (conifer,
broadleaf, narrow). A vertex with cover over COVER_MIN is in the wood: the canopy stands that high over the ground
(lower in a sparse wood), with a little height and shade of its own (a hash of the vertex's place: crowns and gaps). The other vertices go DROP m under the ground, so a wood ends in a
steep edge and no canopy lies on open ground. Every tile closes its border with a skirt down to under the ground (the
tile beside it may be real Forest or the other level). Tiles are made a block of L2_TILES x L2_TILES tiles at a time,
with the trees of the tiles round the block, so a vertex two tiles share is the same in both.

    fartrees.build(tiles, names, origin, tile_m, out_dir, ground=g) -> ([tile keys], [L2 keys])   (region_base.py)
    python fartrees.py --trees <folder of t_*.trees.json> --stream stream.json --ground ground.npz --out <level folder>
"""
import argparse
import json
import os
import re
import sys
import time
import uuid

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402

DIR = "fartrees"
MAT = "tc_far_trees"
K = 32                      # squares along a tile's edge: the far ground's grid (farlod.K, 12 m in a 384 m tile)
L2_TILES = 4                # tiles along a coarse tile's edge (1,536 m)
COARSE = 2                  # fine squares along a coarse square's edge (24 m)
MIN_H = 5.0                 # m: shorter items are no far tree
CROWN = 0.6                 # crown radius / bounding-box half width (the boxes are wider than the leaves)
COVER_MIN = 0.22            # crown cover of the box round a vertex: under it, no canopy
COVER_FULL = 0.55           # over it the canopy has the trees' full height (in between it is lower, LOW at COVER_MIN)
LOW = 0.45
MIN_TREES = 2               # trees in the box round a vertex, at least
H_MAX = 32.0                # m: the canopy at most this high over the ground (a few trees are scaled to 40-50 m)
LIFT_MIN = 2.0              # m: the canopy at least this high over the ground
NOISE = 3.5                 # m: +- height of a vertex's own (crowns and gaps), less in a sparse wood
SHADE = 0.25                # +- of its colour with it (a crown lighter, a gap darker)
DROP = 5.0                  # m under the ground: the vertices out of the wood and the foot of the skirts
EDGE = 0.7                  # colour of the canopy's edge (the faces down to those vertices) and of the skirts
# sRGB vertex colours of the canopy (the material is white): conifers, broadleaves, narrow crowns. A little darker and
# greener than the far ground's own forest colour (median 62,66,42 near Lugano), as a wood is from afar.
COLORS = np.array([(38, 50, 32), (52, 66, 36), (50, 63, 36)], np.float64)
SKIP = re.compile(r"bush|hedge|guardrail|^skin_")
MARGIN = 3                  # vertices round a block made with it (the boxes and the normals of its border vertices)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def kind_of(name):
    n = name.lower()
    if "fir" in n or "cypress" in n or "spruce" in n or "pine" in n or "larch" in n:
        return 0
    if "narrow" in n or "aspen" in n or "poplar" in n:
        return 2
    return 1


class Types:
    """Height, crown radius and kind of every forest type of the plan (dati/asset_bounds.json, by file name)."""

    def __init__(self, names, bounds_path=None):
        bounds_path = bounds_path or os.path.join(HERE, "..", "dati", "asset_bounds.json")
        B = json.load(open(bounds_path))
        by_name = {os.path.basename(k).rsplit(".", 1)[0]: v for k, v in B.items()}
        n = len(names)
        self.h = np.zeros(n)
        self.r = np.zeros(n)
        self.kind = np.zeros(n, np.int64)
        self.use = np.zeros(n, bool)
        for i, t in enumerate(names):
            b = by_name.get(t)
            if b is None or SKIP.search(t):
                continue
            (x0, y0, _), (x1, y1, z1) = b
            self.h[i] = z1
            self.r[i] = CROWN * max(abs(x0), abs(x1), abs(y0), abs(y1))
            self.kind[i] = kind_of(t)
            self.use[i] = True


def trees(rows, types, x0, y0):
    """The far trees of one tile's rows as an (n, 6) float32 array: x, y from the corner (x0, y0), foot z, height,
    crown radius, kind; None if there is none."""
    if not len(rows):
        return None
    R = np.asarray(rows, np.float64).reshape(-1, 6)
    t = R[:, 0].astype(np.int64)
    ok = (t >= 0) & (t < len(types.use))
    R, t = R[ok], t[ok]
    use = types.use[t]
    R, t = R[use], t[use]
    H = types.h[t] * R[:, 5]
    big = H >= MIN_H
    R, t, H = R[big], t[big], H[big]
    if not len(R):
        return None
    return np.stack([R[:, 1] - x0, R[:, 2] - y0, R[:, 3], H, types.r[t] * R[:, 5], types.kind[t]], 1).astype(np.float32)


def noise(gx, gy):
    """-1..1 of a grid vertex (its global indices): the same for that vertex in every tile and level."""
    h = ((np.asarray(gx, np.int64) * 73856093) ^ (np.asarray(gy, np.int64) * 19349663)) & 0xFFFFFFFF
    for _ in range(2):
        h = ((h ^ (h >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return h / 2.0 ** 31 - 1.0


# ------------------------------------------------------------------ one block
def cell_stats(T, nc, cell):
    """Per cell of an nc x nc grid of cell m (T: trees with x, y from the grid's corner): count, crown area, heights
    times crown areas, conifers, broadleaves (all (nc, nc), row = y)."""
    c = np.floor(T[:, 0] / cell).astype(np.int64)
    r = np.floor(T[:, 1] / cell).astype(np.int64)
    ok = (c >= 0) & (c < nc) & (r >= 0) & (r < nc)
    T, idx = T[ok], (r * nc + c)[ok]
    k = T[:, 5].astype(np.int64)
    area = np.pi * T[:, 4].astype(np.float64) ** 2
    return {"n": np.bincount(idx, minlength=nc * nc).reshape(nc, nc).astype(np.float64),
            "area": np.bincount(idx, area, nc * nc).reshape(nc, nc),
            "ah": np.bincount(idx, area * T[:, 3].astype(np.float64), nc * nc).reshape(nc, nc),
            "k0": np.bincount(idx[k == 0], minlength=nc * nc).reshape(nc, nc).astype(np.float64),
            "k1": np.bincount(idx[k == 1], minlength=nc * nc).reshape(nc, nc).astype(np.float64)}


def box(a, w, op="sum"):
    """Sums (or maxima) of the w x w cells round every inner corner of a grid of cells: out[i, j] is the corner
    between cells i, i + 1 (and j, j + 1) and covers cells i - w/2 + 1 .. i + w/2 (w even), out of the grid as 0."""
    h = w // 2
    n0, n1 = a.shape
    p = np.pad(a, h, mode="constant")
    if op == "sum":
        s = np.pad(np.cumsum(np.cumsum(p, 0), 1), ((1, 0), (1, 0)))
        out = s[w:, w:] - s[:-w, w:] - s[w:, :-w] + s[:-w, :-w]
    else:
        out = np.full((n0 + 1, n1 + 1), -np.inf)
        for di in range(w):
            for dj in range(w):
                out = np.maximum(out, p[di:di + n0 + 1, dj:dj + n1 + 1])
    return out[1:-1, 1:-1]


def box_mean(a, m):
    """The mean of a over the vertices with m among every vertex and its 8 neighbours (a where none has)."""
    s = np.pad(np.where(m, a, 0.0), 1)
    c = np.pad(m.astype(np.float64), 1)
    S = sum(s[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3))
    N = sum(c[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3))
    return np.where(N > 0, S / np.maximum(N, 1), a)


def around(a, op):
    """The max (or min) of every value and its 8 neighbours (the border repeated)."""
    p = np.pad(a, 1, mode="edge")
    out = a.copy()
    f = np.maximum if op == "max" else np.minimum
    for di in range(3):
        for dj in range(3):
            out = f(out, p[di:di + a.shape[0], dj:dj + a.shape[1]])
    return out


def canopy(vs, side, G, gx, gy):
    """The canopy at grid vertices from the trees of the box of side m round each (vs: box() of cell_stats): height z
    (G - DROP out of the wood; NaN where no ground), in the wood or not, sRGB colour (..., 3)."""
    n = vs["n"]
    cover = np.minimum(1.0, vs["area"] / side ** 2)
    wood = np.isfinite(G) & (cover >= COVER_MIN) & (n >= MIN_TREES)
    full = np.clip((cover - COVER_MIN) / (COVER_FULL - COVER_MIN), 0, 1)
    nn = np.maximum(n, 1)
    # the trees' height weighted by their crowns (the big trees make the canopy, one tall tree no spike), smoothed
    # over the wood's vertices round each
    h = np.where(wood, np.minimum(H_MAX, vs["ah"] / np.maximum(vs["area"], 1e-9)), 0.0)
    h = box_mean(h, wood) * (LOW + (1 - LOW) * full)
    rnd = noise(gx, gy)
    h = np.maximum(LIFT_MIN, h + NOISE * rnd * (0.5 + 0.5 * full))
    z = np.where(wood, G + h, G - DROP)
    f0, f1 = vs["k0"] / nn, vs["k1"] / nn
    f2 = np.maximum(0.0, 1 - f0 - f1)
    col = f0[..., None] * COLORS[0] + f1[..., None] * COLORS[1] + f2[..., None] * COLORS[2]
    col[n == 0] = COLORS[1]
    col = col * (1 + SHADE * rnd)[..., None]
    col[~wood] *= EDGE
    return z, wood, col


def normals(z, step):
    """Unit normals of a height grid (row = y) by central differences, one-sided at its border and next to NaN."""
    def slope(lo, a, hi):
        both = np.isfinite(lo) & np.isfinite(hi)
        out = np.zeros(a.shape)
        out[both] = (hi - lo)[both] / (2 * step)
        up = ~both & np.isfinite(hi) & np.isfinite(a)
        out[up] = (hi - a)[up] / step
        dn = ~both & np.isfinite(lo) & np.isfinite(a)
        out[dn] = (a - lo)[dn] / step
        return out
    p = np.pad(z, 1, mode="constant", constant_values=np.nan)
    dx = slope(p[1:-1, :-2], z, p[1:-1, 2:])
    dy = slope(p[:-2, 1:-1], z, p[2:, 1:-1])
    n = np.stack([-dx, -dy, np.ones(z.shape)], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def tile_mesh(z, wood, col, N, foot, step):
    """One tile of a canopy grid ((m, m) arrays of its vertices, row = y): positions from the tile's corner, triangles
    (counter-clockwise from above: cdae turns them round), normals, colours (n, 4) uint8 of the used vertices; None if
    no face. The grid's faces with a vertex in the wood (the far ground's diagonal), and a skirt along the tile's border
    from every vertex in the wood down to foot (the next tile may be real Forest or the other level)."""
    m = z.shape[0]
    ii = np.arange(m * m).reshape(m, m)
    a, b, c2, d = ii[:-1, :-1].ravel(), ii[:-1, 1:].ravel(), ii[1:, :-1].ravel(), ii[1:, 1:].ravel()
    T = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c2], 1)])
    w = wood.ravel()
    ok = np.isfinite(z).ravel() & np.isfinite(foot).ravel()
    T = T[w[T].any(1) & ok[T].all(1)]
    if not len(T):
        return None
    X, Y = np.meshgrid(np.arange(m) * step, np.arange(m) * step)
    P = np.stack([X.ravel(), Y.ravel(), np.nan_to_num(z).ravel()], 1)
    NN = N.reshape(-1, 3)
    C = col.reshape(-1, 3)
    # the border ring, counter-clockwise seen from above (farlod._ring): a foot under every ring vertex in the wood,
    # the others (already DROP under the ground) are their own foot
    ring = np.concatenate([ii[0, :], ii[1:, -1], ii[-1, -2::-1], ii[-2:0:-1, 0]])
    nr = len(ring)
    rw = w[ring] & ok[ring]
    feet = ring[rw]
    fidx = ring.copy()
    fidx[rw] = len(P) + np.arange(len(feet))
    Pf = P[feet].copy()
    Pf[:, 2] = foot.ravel()[feet]
    j = np.arange(nr)
    j1 = (j + 1) % nr
    A, Bn, As, Bs = ring[j], ring[j1], fidx[j], fidx[j1]
    use = ok[A] & ok[Bn] & (rw[j] | rw[j1])
    Ts = np.concatenate([np.stack([A, As, Bs], 1)[use & rw[j]],      # (A, its foot, B's foot): A in the wood
                         np.stack([A, Bs, Bn], 1)[use & rw[j1]]])    # (A, B's foot, B): B in the wood
    P = np.concatenate([P, Pf])
    NN = np.concatenate([NN, NN[feet]])
    C = np.concatenate([C, C[feet] * EDGE])
    TT = np.concatenate([T, Ts])
    used = np.zeros(len(P), bool)
    used[TT.ravel()] = True
    remap = np.cumsum(used) - 1
    C8 = np.concatenate([np.clip(np.round(C[used]), 0, 255), np.full((used.sum(), 1), 255.0)], 1).astype(np.uint8)
    return P[used], remap[TT], NN[used], C8


def shape_bytes(mesh):
    P, T, N, C = mesh
    return cdae.encode(P, T, normals=N, uvs=np.zeros((len(P), 2)), material=MAT, colors=C, object_name="fartrees")


def grids(T, G, bx, by, tile_m):
    """The canopy of a block with its margin: (fine z, wood, colour, normals, skirt foot) on the 12 m grid and
    (the same) on the coarse grid (every COARSE-th vertex from the block's corner, one more round it)."""
    step = tile_m / K
    M, s = MARGIN, COARSE
    nv = L2_TILES * K + 2 * M + 1               # the block's vertices along an edge, with the margin
    # cell u covers [(u - M - 1) step, (u - M) step) from the block's corner, so vertex v lies between cells v, v + 1
    st = cell_stats(T + np.array([(M + 1) * step, (M + 1) * step, 0, 0, 0, 0], np.float32), nv + 1, step)
    GX, GY = np.meshgrid(bx * L2_TILES * K - M + np.arange(nv), by * L2_TILES * K - M + np.arange(nv))
    fine = {k: box(v, 2) for k, v in st.items()}
    z, wood, col = canopy(fine, 2 * step, G, GX, GY)
    F = (z, wood, col, normals(z, step), G - DROP)
    # coarse: the trees of the 2 s x 2 s cells round every vertex, every s-th vertex (and one more round the block)
    coarse = {k: box(v, 2 * s) for k, v in st.items()}
    sub = (slice(M - s, nv - M + s, s), slice(M - s, nv - M + s, s))
    cz, cwood, ccol = canopy({k: v[sub] for k, v in coarse.items()}, 2 * s * step, G[sub], GX[sub], GY[sub])
    # the canopy over the highest ground half a coarse square round it (a ridge between two coarse vertices would come
    # through the coarse surface), and out of the wood under the lowest (no edge face over the far ground)
    gmax = around(np.where(np.isfinite(G), G, -np.inf), "max")[sub]
    gmin = around(np.where(np.isfinite(G), G, np.inf), "min")[sub]
    cfoot = np.where(np.isfinite(gmin), gmin, np.nan) - DROP
    cz = np.where(cwood, np.maximum(cz, gmax + LIFT_MIN), np.where(np.isfinite(cz), cfoot, np.nan))
    Cg = (cz, cwood, ccol, normals(cz, s * step), cfoot)
    return F, Cg


def make_block(task):
    """Write the fine tiles and the coarse tile of one block; returns (bx, by, [(tile key, triangles, bytes)], coarse
    (key, triangles, bytes) or None)."""
    bx, by, T, G, tiles, tile_m, out_dir = task
    step = tile_m / K
    F, Cg = grids(T, G, bx, by, tile_m)
    out = []
    for cx, cy in tiles:
        i0 = MARGIN + (cx - bx * L2_TILES) * K
        j0 = MARGIN + (cy - by * L2_TILES) * K
        sl = (slice(j0, j0 + K + 1), slice(i0, i0 + K + 1))
        mesh = tile_mesh(*(a[sl] for a in F), step)
        if mesh is None:
            continue
        data = shape_bytes(mesh)
        key = "%d_%d" % (cx, cy)
        _write(os.path.join(out_dir, "t_%s.cdae" % key), data)
        out.append((key, len(mesh[1]), len(data)))
    n2 = L2_TILES * K // COARSE
    sl = (slice(1, n2 + 2), slice(1, n2 + 2))
    mesh = tile_mesh(*(a[sl] for a in Cg), COARSE * step)
    coarse = None
    if mesh is not None:
        data = shape_bytes(mesh)
        key = "%d_%d" % (bx, by)
        _write(os.path.join(out_dir, "l2_%s.cdae" % key), data)
        coarse = (key, len(mesh[1]), len(data))
    return bx, by, out, coarse


def material():
    from blocks import bng
    # a persistentId of its own name, not bng's random one: the same material is the same bytes in every base
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "ticino/" + MAT))
    # as the far ground's (blocks.far_material): white, the colour in the vertices, no shadows of its own
    return bng.material(MAT, base_color=[1, 1, 1, 1], vert_color=True, roughness=1.0,
                        extra={"castShadows": False, "persistentId": pid})


# ------------------------------------------------------------------ the whole level
def _write(path, data):
    if os.path.lexists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.write(data)


def ground_block(ground, origin, tile_m, bx, by):
    """The far ground's heights at a block's vertices with the margin ((nv, nv), row = y), NaN where it has none;
    ground None: NaN everywhere (the caller fills it from the trees)."""
    M = MARGIN
    nv = L2_TILES * K + 2 * M + 1
    if ground is None:
        return np.full((nv, nv), np.nan)
    gx0 = bx * L2_TILES * K - M - ground.cx0 * K
    gy0 = by * L2_TILES * K - M - ground.cy0 * K
    Hn, Wn = ground.H.shape
    R, C = np.meshgrid(gy0 + np.arange(nv), gx0 + np.arange(nv), indexing="ij")
    ok = (R >= 0) & (R < Hn) & (C >= 0) & (C < Wn)
    out = np.full((nv, nv), np.nan)
    out[ok] = ground.H[R[ok], C[ok]]
    return out


def feet_ground(T, step):
    """A stand-in for the far ground from the trees' feet (a test without one): the mean foot height of the trees
    within 3 cells of each block vertex, NaN where there is none."""
    M = MARGIN
    nv = L2_TILES * K + 2 * M + 1
    st = cell_stats(T + np.array([(M + 1) * step, (M + 1) * step, 0, 0, 0, 0], np.float32), nv + 1, step)
    c = np.floor((T[:, 0] + (M + 1) * step) / step).astype(np.int64)
    r = np.floor((T[:, 1] + (M + 1) * step) / step).astype(np.int64)
    ok = (c >= 0) & (c <= nv) & (r >= 0) & (r <= nv)
    sz = np.bincount((r * (nv + 1) + c)[ok], T[ok, 2].astype(np.float64), (nv + 1) ** 2).reshape(nv + 1, nv + 1)
    n, s = box(st["n"], 6), box(sz, 6)
    return np.where(n > 0, s / np.maximum(n, 1), np.nan)


def block_tasks(T_by_tile, ground, origin, tile_m, out_dir):
    """(bx, by, trees of the block and the tiles round it from the block's corner, ground, tiles to write, ...) for
    every block with a tile with far trees, in the order of the blocks."""
    blocks = {}
    for (cx, cy) in T_by_tile:
        blocks.setdefault((cx // L2_TILES, cy // L2_TILES), []).append((cx, cy))
    step = tile_m / K
    for (bx, by) in sorted(blocks, key=lambda b: (b[1], b[0])):
        parts = []
        for cy in range(by * L2_TILES - 1, by * L2_TILES + L2_TILES + 1):
            for cx in range(bx * L2_TILES - 1, bx * L2_TILES + L2_TILES + 1):
                t = T_by_tile.get((cx, cy))
                if t is not None:
                    parts.append(t + np.array([(cx - bx * L2_TILES) * tile_m, (cy - by * L2_TILES) * tile_m,
                                               0, 0, 0, 0], np.float32))
        T = np.concatenate(parts)
        lo, hi = -(MARGIN + 1) * step, (L2_TILES * K + MARGIN + 1) * step
        T = T[(T[:, 0] >= lo) & (T[:, 0] < hi) & (T[:, 1] >= lo) & (T[:, 1] < hi)]
        G = ground_block(ground, origin, tile_m, bx, by)
        if ground is None:
            G = feet_ground(T, step)
        yield bx, by, T, G, sorted(blocks[(bx, by)], key=lambda t: (t[1], t[0])), tile_m, out_dir


def build(tiles, names, origin, tile_m, out_dir, level="ticino", workers=1, ground=None):
    """tiles: iterable of (key "cx_cy", rows or their JSON bytes); ground: the far ground (farlod.Ground) the canopy
    stands on (None: the trees' feet). Writes out_dir/t_<key>.cdae (one per tile with a wood), out_dir/l2_<bx>_<by>.cdae
    (one per L2_TILES x L2_TILES tiles) and the material; returns (tile keys, L2 keys)."""
    assert abs(tile_m / K / COARSE * COARSE * K - tile_m) < 1e-9
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                  # an older far-tree set (cards: the clump texture) goes
        if re.fullmatch(r"(t|l2)_-?\d+_-?\d+\.cdae|fartrees\.png", f):
            os.remove(os.path.join(out_dir, f))
    types = Types(names)
    t0 = time.time()
    T_by_tile, ntrees = {}, 0
    for key, rows in tiles:
        if isinstance(rows, (bytes, str)):
            rows = json.loads(rows)
        cx, cy = (int(v) for v in key.split("_"))
        tr = trees(rows, types, origin[0] + cx * tile_m, origin[1] + cy * tile_m)
        if tr is not None:
            T_by_tile[(cx, cy)] = tr
            ntrees += len(tr)
    log("far trees: %d tiles with %d far trees read (%.0f s)" % (len(T_by_tile), ntrees, time.time() - t0))
    tasks = block_tasks(T_by_tile, ground, origin, tile_m, out_dir)
    if workers > 1:
        import multiprocessing as mp
        pool = mp.Pool(workers)
        results = pool.imap(make_block, tasks, chunksize=4)
    else:
        pool = None
        results = map(make_block, tasks)
    keys, keys2 = [], []
    nt = nb = nt2 = nb2 = 0
    for i, (bx, by, out, coarse) in enumerate(results):
        for key, ntri, nbytes in out:
            keys.append(key)
            nt += ntri
            nb += nbytes
        if coarse:
            keys2.append(coarse[0])
            nt2 += coarse[1]
            nb2 += coarse[2]
        if (i + 1) % 200 == 0:
            log("far trees: %d blocks, %d tiles, %.0f MB (%.0f s)" % (i + 1, len(keys), (nb + nb2) / 1e6,
                                                                     time.time() - t0))
    if pool:
        pool.close()
        pool.join()
    from blocks import bng
    bng.write_materials(os.path.join(out_dir, "fartrees.materials.json"), [material()])
    log("far trees: %d tiles, %d triangles, %.0f MB; %d coarse tiles, %d triangles, %.0f MB; in %.0f s" % (
        len(keys), nt, nb / 1e6, len(keys2), nt2, nb2 / 1e6, time.time() - t0))
    return sorted(keys), sorted(keys2)


def tree_members(zf):
    """(key, name) of the tree tiles in a slice zip, in the zip's order."""
    infos = sorted((i for i in zf.infolist() if re.search(r"/tiles/t_-?\d+_-?\d+\.trees\.json$", i.filename)),
                   key=lambda i: i.header_offset)
    return [(re.search(r"t_(-?\d+_-?\d+)\.trees\.json$", i.filename).group(1), i.filename) for i in infos]


def read_slices(sl, zones, workers=6):
    """(key, JSON bytes) of every tree tile of the zones' slices (region_base's Slices: local folders or the release
    by HTTP range), as they come; at most `workers` slice zips in memory at a time."""
    if sl.folder:
        for z in zones:
            d = os.path.join(sl.folder, z, "levels", "ticino", "tiles")
            for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                m = re.fullmatch(r"t_(-?\d+_-?\d+)\.trees\.json", f)
                if m:
                    yield m.group(1), open(os.path.join(d, f), "rb").read()
        return
    import zipremote
    from concurrent.futures import ThreadPoolExecutor
    items = [aid for z in zones for aid in sl.ids.get(z, [])]

    def one(aid):
        zf = zipremote.open_zip(aid)
        return [(k, zf.read(m)) for k, m in tree_members(zf)]
    t0, n = time.time(), 0
    with ThreadPoolExecutor(workers) as ex:
        for i in range(0, len(items), workers):
            for got in ex.map(one, items[i:i + workers]):
                n += len(got)
                yield from got
            log("far trees: %d of %d slice zips read, %d tree tiles (%.0f s)" % (
                min(i + workers, len(items)), len(items), n, time.time() - t0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trees", required=True, help="folder with t_<cx>_<cy>.trees.json")
    ap.add_argument("--stream", required=True, help="stream.json (origin, cell, square, forestTypes)")
    ap.add_argument("--ground", help="the far ground (farlod Ground.save .npz); without it the trees' feet")
    ap.add_argument("--out", required=True, help="level folder (writes fartrees/)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    st = json.load(open(a.stream))
    tile_m = st["cell"] * st["square"]
    ground = None
    if a.ground:
        import farlod
        ground = farlod.Ground.load(a.ground, [])

    def tiles():
        for f in sorted(os.listdir(a.trees)):
            m = re.fullmatch(r"t_(-?\d+_-?\d+)\.trees\.json", f)
            if m:
                yield m.group(1), open(os.path.join(a.trees, f), "rb").read()
    keys, keys2 = build(tiles(), st["forestTypes"], st["origin"], tile_m, os.path.join(a.out, DIR),
                        workers=a.workers, ground=ground)
    print(len(keys), "tiles", len(keys2), "coarse tiles")


if __name__ == "__main__":
    main()
