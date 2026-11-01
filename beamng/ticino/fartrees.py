"""Far trees: the forest beyond the streamed Forest (forest.lua RADIUS, ~1.5-1.9 km) as static shapes, one per 384 m tile
(fartrees/t_<cx>_<cy>.cdae), so the woods go on to the far tiles' distance instead of ending in a line (michi
2026-11-01, "non puoi anche aumentare la distanza degli alberi?").

Why not more Forest: every frame that adds or removes Forest items cost the engine ~200 ms on the PC (2026-10-30/31,
whatever it added; BeamNG.Earth trees.lua: ~0.5 us for every item in the level of each shape touched), so more rings
of real trees would mean more such frames. A far-tree tile is a plain TSStatic with no collision, made like a far
ground tile (objects.lua stepFar), which costs a few ms.

A tile's trees (tiles/t_<cx>_<cy>.trees.json of the slices, the rows forest.lua streams) are binned on a CELL m grid;
every cell with trees becomes one card: two crossed vertical quads with a cut-out texture of a clump of trees
(fartrees.png: conifers, broadleaves, narrow crowns, mixed; VARIANTS of each), as wide as the cell's crowns cover it
and as tall as its tall trees, standing on the plane of its tree feet (sheared along the slope, its sides still
vertical). The clumps are drawn from the side views of the
Malcantone level's own far trees (their imposters in dati/far_imposters, michi 2026-11-01: "metti gli alberi low poly
quelli lontani del Malcantone"), so the shapes are the same woods; their colour is darkened to a wood seen from afar
(CROWN_RGB). Each quad is two single-sided faces back to back, each with the normal of its side tilted up (TILT).
Coarse tiles (l2_<bx>_<by>.cdae, L2_TILES x L2_TILES tiles, cards of CELL2 m) carry the woods out to the horizon
(michi: "gli alberi devono vedersi sempre come le case"). Bushes, hedges and guard rails are left out (and trees
under MIN_H).

    fartrees.build(read_tiles, names, origin, tile_m, out_dir) -> ([tile keys], [L2 keys])   (region_base.py)
    python fartrees.py --trees <folder of t_*.trees.json> --stream stream.json --out <level folder>   (a test)
"""
import argparse
import json
import math
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
TEX = "fartrees.png"
CELL = 28.0                 # m: one card per cell with trees (far-tree tiles of 384 m)
CELL2 = 64.0                # m: the same for the coarse far-tree tiles (L2_TILES x L2_TILES tiles, 1,536 m)
L2_TILES = 4
MIN_H = 5.0                 # m: shorter items are no far tree
CROWN = 0.6                 # crown radius / bounding-box half width (the boxes are wider than the leaves)
SINK = 1.5                  # m: a card's foot under the lowest tree foot of its cell (under the plane of the feet)
WIDTH_MIN = 6.0
TOP_PCT = 75                # the card's top: this percentile of the cell's tree heights over the plane of the feet
# A card follows the plane of its cell's tree feet (each quad sheared along it). The first cards stood level on the
# LOWEST foot with the top at the tallest tops: on a slope a 28 m cell spans 8-21 m of height (median, 90th pct near
# Lugano), the cards were 1.5 times the trees' height or more (a quarter of them) and every hill was stairs of flat-
# topped blocks (PC photos from San Salvatore, 2026-11-01).
PLANE_REG = 4.0             # m2 a tree: the plane fit's ridge (no slope across one tree or a row of trees)
SLOPE_MAX = 1.5             # the plane's steepest slope (56 degrees)
ATLAS = (2048, 1024)        # 4 kinds (columns of 512 px) x VARIANTS (rows of 256 px)
VARIANTS = 4
KINDS = ("conifer", "broad", "narrow", "mixed")
# the Malcantone's far trees (pipeline/far_trees.py), as the game baked their imposters (dati/far_imposters): the
# clumps are drawn from their side views, so the far woods look like the far trees of the Malcantone level
IMPOSTERS = os.path.join(HERE, "..", "dati", "far_imposters")
MODELS = {"conifer": ["far_fir_a", "far_fir_b", "far_fir_c"],
          "broad": ["far_broad_a", "far_broad_b", "far_broad_c"],
          "narrow": ["far_narrow_a", "far_narrow_b", "far_narrow_c"]}
TREES_PER_CLUMP = {"conifer": (10, 13), "broad": (6, 8), "narrow": (9, 11), "mixed": (8, 10)}
SATURATE = 1.4             # the imposters' colours, a little more saturated (the sRGB of a linear bake is pale)
SHADE = (0.86, 1.0)         # vertex colour of a card (a little variety between clumps; the colour is the imposters')
# The crowns' mean colour (sRGB) per kind: the imposters' detail scaled to it. A card is one flat face, lit like a
# meadow: the self-shadowing that makes a real wood dark from afar has to be in its colour. The first atlas kept the
# imposters' own mean (broadleaves 80,94,73, twice the far ground's forest 62,65,41 in linear light) and the cards
# stood out as pale grey-green blocks on every hill (PC photos from San Salvatore, 2026-11-01).
CROWN_RGB = {"conifer": (36, 48, 30), "broad": (50, 64, 34), "narrow": (48, 62, 34), "mixed": (43, 56, 32)}
UNDER = 0.65                # the foliage under the crowns: this share of the crowns' colour (one dark mass, no box)
# A card's two faces are single-sided, back to back, each with its own normal: its side, TILT degrees up. The first
# cards had one double-sided face with normals straight up: seen from the side (every far view) the light met them at
# a grazing angle and they took the sky's reflection, pale blue-white; a back face flipped to a normal straight down.
TILT = 40.0
SKIP = re.compile(r"bush|hedge|guardrail|^skin_")


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


def _hash(*v):
    h = 2166136261
    for x in v:
        h = ((h ^ (int(x) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h


def trees(rows, types, x0, y0):
    """The far trees of one tile's rows: x, y local to the corner (x0, y0), foot z, height, crown radius, kind."""
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
    return R[:, 1] - x0, R[:, 2] - y0, R[:, 3], H, types.r[t] * R[:, 5], types.kind[t]


def plane(x, y, z):
    """The ground plane through tree feet: (mean x, mean y, height at the mean, slope x, slope y, lowest foot under
    it). Ridge-regularised (PLANE_REG m2 a tree), so one tree or a row of trees gives no slope across."""
    mx, my, mz = x.mean(), y.mean(), z.mean()
    dx, dy, dz = x - mx, y - my, z - mz
    lam = PLANE_REG * len(x)
    A = np.array([[dx @ dx + lam, dx @ dy], [dx @ dy, dy @ dy + lam]])
    sx, sy = np.linalg.solve(A, [dx @ dz, dy @ dz])
    g = math.hypot(sx, sy)
    if g > SLOPE_MAX:
        sx, sy = sx * SLOPE_MAX / g, sy * SLOPE_MAX / g
    res = dz - sx * dx - sy * dy
    return mx, my, mz, sx, sy, min(0.0, float(res.min()))


def binned(tr, cell, n):
    """Per cell of cell m (n x n over the tile) with trees: (cell index, count, mean x, mean y, foot, top, cover, max
    crown radius, kind counts 0..2, slope x, slope y) as an (m, 13) array; foot and top at the mean x, y, on the
    plane of the cell's tree feet (the card follows it)."""
    x, y, z, H, r, k = tr
    ci = np.clip((x / cell).astype(np.int64), 0, n - 1)
    cj = np.clip((y / cell).astype(np.int64), 0, n - 1)
    c = cj * n + ci
    order = np.argsort(c, kind="stable")
    c, x, y, z, H, r, k = c[order], x[order], y[order], z[order], H[order], r[order], k[order]
    starts = np.flatnonzero(np.r_[True, c[1:] != c[:-1]])
    ends = np.r_[starts[1:], len(c)]
    out = np.zeros((len(starts), 13))
    for i, (s, e) in enumerate(zip(starts, ends)):
        kc = np.bincount(k[s:e], minlength=3)
        mx, my, mz, sx, sy, low = plane(x[s:e], y[s:e], z[s:e])
        out[i] = (c[s], e - s, mx, my, mz + low - SINK, mz + np.percentile(H[s:e], TOP_PCT),
                  np.sum(np.pi * r[s:e] ** 2), r[s:e].max(), *kc[:3], sx, sy)
    return out


def cards(B, cell, key):
    """Card tuples (x, y, foot, width, height, kind, yaw, variant, shade, slope x, slope y) of binned cells B."""
    out = []
    for c, n, cx, cy, foot, top, cover, rmax, k0, k1, k2, sx, sy in B:
        w = float(np.clip(cell * math.sqrt(min(1.0, cover / cell ** 2)) * 1.15, WIDTH_MIN, 1.3 * cell))
        w = max(w, 2.2 * rmax)
        kc = np.array([k0, k1, k2])
        kind = int(np.argmax(kc))
        if kc.max() < 0.7 * n:
            kind = 3
        hs = _hash(key[0], key[1], key[2] if len(key) > 2 else 0, int(c))
        out.append((cx, cy, foot, w, max(top - foot, 2.0), kind, (hs % 900) / 10.0, (hs >> 10) % VARIANTS,
                    (hs >> 12) % 1000, sx, sy))
    return out


def mesh(cs):
    """Positions, triangles, normals, uvs (Collada: v up), colours of cards: two crossed quads each, every quad two
    single-sided faces back to back (counter-clockwise from their side) with the normal of their side, TILT up. A
    quad's ends stand on the plane of its cell's tree feet (sheared, still vertical)."""
    nc = len(cs)
    P = np.zeros((nc * 16, 3))
    N = np.zeros((nc * 16, 3))
    UV = np.zeros((nc * 16, 2))
    C = np.zeros((nc * 16, 4), np.uint8)
    T = np.zeros((nc * 8, 3), np.int64)
    cw, ch = 1.0 / 4, 1.0 / VARIANTS
    ct, stl = math.cos(math.radians(TILT)), math.sin(math.radians(TILT))
    for i, (cx, cy, foot, w, h, kind, yaw, var, jit, sx, sy) in enumerate(cs):
        u0 = kind * cw + 0.002
        u1 = (kind + 1) * cw - 0.002
        v0 = 1.0 - (var + 1) * ch + 0.002          # atlas row var (0: the image's top row)
        v1 = 1.0 - var * ch - 0.002
        f = SHADE[0] + (SHADE[1] - SHADE[0]) * (jit / 1000.0)
        rgba = np.array([round(f * 255)] * 3 + [255], np.uint8)
        for q in range(2):
            a = math.radians(yaw + 90 * q)
            ex, ey = math.cos(a), math.sin(a)
            dx, dy = 0.5 * w * ex, 0.5 * w * ey
            dz = sx * dx + sy * dy
            quad = [(cx - dx, cy - dy, foot - dz), (cx + dx, cy + dy, foot + dz),
                    (cx + dx, cy + dy, foot + dz + h), (cx - dx, cy - dy, foot - dz + h)]
            # the second quad mirrored in u: the two quads of a card do not show the same clump
            uv = ([(u0, v0), (u1, v0), (u1, v1), (u0, v1)] if q == 0 else
                  [(u1, v0), (u0, v0), (u0, v1), (u1, v1)])
            for s in range(2):
                b = i * 16 + q * 8 + s * 4
                t = i * 8 + q * 4 + s * 2
                P[b:b + 4] = quad
                UV[b:b + 4] = uv
                C[b:b + 4] = rgba
                # (p1 - p0) x (p2 - p0) of (b, b+1, b+2) is (ey, -ex, 0): that face looks that way; the other is
                # the same quad wound the other way round
                sx, sy = (ey, -ex) if s == 0 else (-ey, ex)
                N[b:b + 4] = (ct * sx, ct * sy, stl)
                if s == 0:
                    T[t], T[t + 1] = (b, b + 1, b + 2), (b, b + 2, b + 3)
                else:
                    T[t], T[t + 1] = (b, b + 2, b + 1), (b, b + 3, b + 2)
    return P, T, N, UV, C


def tile_bytes(cs):
    P, T, N, UV, C = mesh(cs)
    return cdae.encode(P, T, normals=N, uvs=UV, material=MAT, colors=C, object_name="fartrees")


def material(tex_path):
    from blocks import bng
    # a persistentId of its own name, not bng's random one: the same material is the same bytes in every base
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "ticino/" + MAT))
    return bng.material(MAT, color_map=tex_path, base_color=[1, 1, 1, 1], vert_color=True, roughness=1.0,
                        alpha_test=70, extra={"castShadows": False, "persistentId": pid})


# ------------------------------------------------------------------ the texture
def _srgb(lin):
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def _views(model):
    """The 8 side views of a far tree's imposter (RGBA float, sRGB, cropped to the tree), or [] if it is missing.
    The game bakes the albedo in linear light (the fir's crown reads 8,12,7): turned into sRGB for a colour map."""
    from PIL import Image
    p = os.path.join(IMPOSTERS, model + ".dae.imposter.dds")
    if not os.path.exists(p):
        return []
    a = np.asarray(Image.open(p).convert("RGBA"), np.float32) / 255.0
    out = []
    for i in range(8):                                   # cells 0..7: around the tree; 8..9 from above
        c = a[(i // 4) * 256:(i // 4 + 1) * 256, (i % 4) * 256:(i % 4 + 1) * 256].copy()
        al = c[..., 3] > 0.5
        if not al.any():
            continue
        ys, xs = np.nonzero(al)
        c = c[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        rgb = _srgb(c[..., :3])
        g = rgb.mean(-1, keepdims=True)
        c[..., :3] = np.clip(g + SATURATE * (rgb - g), 0, 1)     # the bake's grey cast off (lit in the game again)
        out.append(c)
    return out


def _fallback_view(kind):
    """A plain silhouette if the imposters are not there (a test without dati/far_imposters)."""
    h, w = 120, 60
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v, u = 1 - yy / h, xx / w - 0.5
    if kind == "conifer":
        inside = np.abs(u) <= 0.5 * (1 - v)
        col = (0.19, 0.24, 0.17)
    else:
        inside = (u / 0.5) ** 2 + ((v - 0.6) / 0.4) ** 2 <= 1
        col = (0.29, 0.34, 0.22)
    c = np.zeros((h, w, 4), np.float32)
    c[..., :3] = col
    c[..., 3] = inside
    return c


def texture(path, seed=7):
    """The clump atlas: 4 kinds (columns of 512 px) x VARIANTS (rows of 256 px), each a row of the Malcantone's far
    trees (their imposters' side views) standing side by side, the tallest at the back, under-filled with shaded
    foliage below the crowns, cut out by alpha."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    W, Hh = ATLAS
    cw, ch = W // 4, Hh // VARIANTS
    views = {k: [v for m in ms for v in _views(m)] or [_fallback_view(k)] for k, ms in MODELS.items()}
    img = np.zeros((Hh, W, 4), np.float32)
    for ki, kind in enumerate(KINDS):
        for var in range(VARIANTS):
            cell = np.zeros((ch, cw, 4), np.float32)
            n = int(rng.integers(*TREES_PER_CLUMP[kind], endpoint=True))
            pool = (["conifer", "broad"] if kind == "mixed" else [kind])
            hs = np.sort(rng.uniform(0.62, 1.0, n))         # back to front: the tallest first
            hs = hs[::-1]
            xs = rng.permutation((np.arange(n) + rng.uniform(0.15, 0.85, n)) / n)
            for h, x in zip(hs, xs):
                k = pool[int(rng.integers(len(pool)))]
                v = views[k][int(rng.integers(len(views[k])))]
                th = max(8, int(round(h * (ch - 2))))
                tw = max(4, int(round(v.shape[1] * th / v.shape[0] * rng.uniform(0.9, 1.15))))
                im = Image.fromarray(np.clip(np.round(v * 255), 0, 255).astype(np.uint8), "RGBA")
                t = np.asarray(im.resize((tw, th), Image.LANCZOS), np.float32) / 255.0
                c0 = int(round(x * cw - tw / 2))
                r0 = ch - th - int(rng.integers(0, max(1, ch // 20)))
                # clip to the cell
                a0, b0 = max(0, c0), min(cw, c0 + tw)
                a1, b1 = max(0, r0), min(ch, r0 + th)
                if a0 >= b0 or a1 >= b1:
                    continue
                part = t[a1 - r0:b1 - r0, a0 - c0:b0 - c0]
                m = part[..., 3] > 0.5
                dst = cell[a1:b1, a0:b0]
                dst[m] = part[m]
                dst[m, 3] = 1.0
            covered = cell[..., 3] > 0.5
            fill = np.array(CROWN_RGB[kind], np.float32) / 255.0
            # under the crowns down to the card's foot: the shade of the lower wood (no sky between the trunks of a
            # wood seen from kilometres away). The line runs halfway down from the crown tops, smoothed with a running
            # max over a tree's width so the gaps between the cones are filled too; the bare trunks below it (grey, no
            # green) take the shade as well
            yy = np.arange(ch)[:, None]
            any_ = covered.any(0)
            top = np.where(any_, np.argmax(covered, 0), ch).astype(np.float32)
            wwin = max(3, cw // 10)
            pad = np.pad(top, wwin, mode="edge")
            smooth = np.array([pad[i:i + 2 * wwin + 1].min() for i in range(cw)])   # min row = highest crown
            line = smooth + 0.45 * (ch - smooth)
            below = yy >= line[None, :]
            rgb = cell[..., :3]
            bare = covered & ((rgb[..., 1] - 0.5 * (rgb[..., 0] + rgb[..., 2])) < 0.025)
            under = below & (~covered | bare)
            # the crowns' detail kept, their mean colour the kind's (CROWN_RGB); told from the trunks before (scaled,
            # a grey trunk turns green enough to pass as a crown and stood as a light bar in the under-fill)
            crowns = covered & ~under
            if crowns.any():
                mean = np.maximum(cell[crowns, :3].mean(0), 1e-3)
                cell[crowns, :3] = np.clip(cell[crowns, :3] * (fill / mean), 0, 1)
            noise = 0.9 + 0.2 * rng.random((ch, cw)).astype(np.float32)
            cell[under, :3] = fill * UNDER * noise[under][:, None]
            cell[under, 3] = 1.0
            cell[cell[..., 3] < 0.5, :3] = fill          # no dark fringe in the mipmaps
            img[var * ch:(var + 1) * ch, ki * cw:(ki + 1) * cw] = cell
    out = np.clip(np.round(img * 255), 0, 255).astype(np.uint8)
    if os.path.lexists(path):
        os.remove(path)
    Image.fromarray(out, "RGBA").save(path)
    return path


# ------------------------------------------------------------------ the whole level
_W = {}


def _init(names, origin, tile_m, out_dir):
    _W.update(types=Types(names), origin=origin, tile_m=tile_m, out_dir=out_dir)


def _write(path, data):
    if os.path.lexists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.write(data)


def _one(item):
    """Write one tile's far trees (rows as JSON bytes or a list); returns (key, cards, bytes, coarse cards) or None.
    The coarse cards (CELL2, positions local to the corner of the tile's L2 tile) are written by build()."""
    key, rows = item
    if isinstance(rows, (bytes, str)):
        rows = json.loads(rows)
    cx, cy = (int(v) for v in key.split("_"))
    o, tm = _W["origin"], _W["tile_m"]
    tr = trees(rows, _W["types"], o[0] + cx * tm, o[1] + cy * tm)
    if tr is None:
        return None
    cs = cards(binned(tr, CELL, int(math.ceil(tm / CELL))), CELL, (cx, cy))
    data = tile_bytes(cs)
    _write(os.path.join(_W["out_dir"], f"t_{key}.cdae"), data)
    # the coarse cells: tile_m is a whole number of CELL2, so a tile's cells are whole cells of its L2 tile
    B2 = binned(tr, CELL2, int(round(tm / CELL2)))
    c2 = cards(B2, CELL2, (cx, cy, 2))
    ox, oy = (cx % L2_TILES) * tm, (cy % L2_TILES) * tm
    c2 = [(c[0] + ox, c[1] + oy) + tuple(c[2:]) for c in c2]
    return key, len(cs), len(data), c2


def build(tiles, names, origin, tile_m, out_dir, level="ticino", workers=1):
    """tiles: iterable of (key "cx_cy", rows or their JSON bytes). Writes out_dir/t_<key>.cdae (one per tile, CELL
    cards), out_dir/l2_<bx>_<by>.cdae (one per L2_TILES x L2_TILES tiles, CELL2 cards), the texture and the material;
    returns (tile keys, L2 keys)."""
    assert abs(tile_m / CELL2 - round(tile_m / CELL2)) < 1e-9, "tile_m must be a multiple of CELL2"
    os.makedirs(out_dir, exist_ok=True)
    keys, ncards, nbytes = [], 0, 0
    coarse = {}
    t0 = time.time()
    if workers > 1:
        import multiprocessing as mp
        pool = mp.Pool(workers, _init, (names, origin, tile_m, out_dir))
        results = pool.imap_unordered(_one, tiles, chunksize=16)
    else:
        pool = None
        _init(names, origin, tile_m, out_dir)
        results = map(_one, tiles)
    for r in results:
        if r is None:
            continue
        keys.append(r[0])
        ncards += r[1]
        nbytes += r[2]
        cx, cy = (int(v) for v in r[0].split("_"))
        coarse.setdefault("%d_%d" % (cx // L2_TILES, cy // L2_TILES), {})[(cx, cy)] = r[3]
        if len(keys) % 2000 == 0:
            log("far trees: %d tiles, %d cards, %.0f MB (%.0f s)" % (len(keys), ncards, nbytes / 1e6, time.time() - t0))
    if pool:
        pool.close()
        pool.join()
    n2, b2 = 0, 0
    # the coarse cards in the order of their tiles, not in the order the workers finished them: a coarse tile made
    # again from the same rows is the same bytes (the base's part 3 is downloaded again only when it changed)
    coarse = {k: [c for t in sorted(by_tile) for c in by_tile[t]] for k, by_tile in sorted(coarse.items())}
    for k, cs in coarse.items():
        if not cs:
            continue
        data = tile_bytes(cs)
        _write(os.path.join(out_dir, f"l2_{k}.cdae"), data)
        n2 += len(cs)
        b2 += len(data)
    texture(os.path.join(out_dir, TEX))
    from blocks import bng
    bng.write_materials(os.path.join(out_dir, "fartrees.materials.json"),
                        [material(f"/levels/{level}/{DIR}/{TEX}")])
    log("far trees: %d tiles, %d cards, %.0f MB; %d coarse tiles, %d cards, %.0f MB; in %.0f s" % (
        len(keys), ncards, nbytes / 1e6, len(coarse), n2, b2 / 1e6, time.time() - t0))
    return sorted(keys), sorted(k for k, cs in coarse.items() if cs)


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
    ap.add_argument("--out", required=True, help="level folder (writes fartrees/)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    st = json.load(open(a.stream))
    tile_m = st["cell"] * st["square"]

    def tiles():
        for f in sorted(os.listdir(a.trees)):
            m = re.fullmatch(r"t_(-?\d+_-?\d+)\.trees\.json", f)
            if m:
                yield m.group(1), open(os.path.join(a.trees, f), "rb").read()
    keys, keys2 = build(tiles(), st["forestTypes"], st["origin"], tile_m, os.path.join(a.out, DIR),
                        workers=a.workers)
    print(len(keys), "tiles", len(keys2), "coarse tiles")


if __name__ == "__main__":
    main()
