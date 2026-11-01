"""Far trees: the forest beyond the streamed Forest (forest.lua RADIUS, ~1.5-1.9 km) as static shapes, one per 384 m tile
(fartrees/t_<cx>_<cy>.cdae), so the woods go on to the far tiles' distance instead of ending in a line (michi
2026-11-01, "non puoi anche aumentare la distanza degli alberi?").

Why not more Forest: every frame that adds or removes Forest items cost the engine ~200 ms on the PC (2026-10-30/31,
whatever it added; BeamNG.Earth trees.lua: ~0.5 us for every item in the level of each shape touched), so more rings
of real trees would mean more such frames. A far-tree tile is a plain TSStatic with no collision, made like a far
ground tile (objects.lua stepFar), which costs a few ms.

A tile's trees (tiles/t_<cx>_<cy>.trees.json of the slices, the rows forest.lua streams) are binned on a CELL m grid;
every cell with trees becomes one card: two crossed vertical quads with a cut-out texture of a clump of crowns
(fartrees.png, made here: conifers, broadleaves, narrow crowns, mixed; two of each), as wide as the cell's crowns
cover it and as tall as its tall trees, standing on its lowest tree foot. Colours: vertex colours by the clump's kind
(material with vertColor; the texture is a near-white shading). Normals point up: lit like the ground under them.
Bushes, hedges and guard rails of the forest list are left out (and trees under MIN_H).

    fartrees.build(read_tiles, out_dir, tile_m) -> [keys]                          (region_base.py)
    python fartrees.py --trees <folder of t_*.trees.json> --stream stream.json --out <level folder>   (a test)
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402

DIR = "fartrees"
MAT = "tc_far_trees"
TEX = "fartrees.png"
CELL = 28.0                 # m: one card per cell with trees
MIN_H = 5.0                 # m: shorter items are no far tree
CROWN = 0.6                 # crown radius / bounding-box half width (the boxes are wider than the leaves)
SINK = 1.5                  # m: a card's foot under the lowest tree foot of its cell (slopes)
WIDTH_MIN, WIDTH_MAX = 6.0, 1.3 * CELL
TOP_PCT = 75                # the card's top: this percentile of the cell's tree tops
ATLAS = (1024, 512)         # 4 x 2 cells of 256 px
KINDS = ("conifer", "broad", "narrow", "mixed")
# vertex colours (sRGB 0..1) of a clump's kind; the texture's shading multiplies them. Darker than the meadows,
# conifers blue-green: to be checked against the near forest's imposters in a screenshot.
COLOUR = {"conifer": (0.20, 0.27, 0.17), "broad": (0.27, 0.34, 0.17), "narrow": (0.30, 0.36, 0.19),
          "mixed": (0.24, 0.31, 0.17)}
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


def cards(rows, types, x0, y0, tile_m, key=(0, 0)):
    """The cards of one tile: centre (n, 3) local to the tile's corner (z: the foot), width, height, kind, yaw."""
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
    x, y, z = R[:, 1] - x0, R[:, 2] - y0, R[:, 3]
    r = types.r[t] * R[:, 5]
    k = types.kind[t]
    n = int(round(tile_m / CELL))
    ci = np.clip((x / CELL).astype(np.int64), 0, n - 1)
    cj = np.clip((y / CELL).astype(np.int64), 0, n - 1)
    cell = cj * n + ci
    order = np.argsort(cell, kind="stable")
    cell, x, y, z, H, r, k = cell[order], x[order], y[order], z[order], H[order], r[order], k[order]
    starts = np.flatnonzero(np.r_[True, cell[1:] != cell[:-1]])
    ends = np.r_[starts[1:], len(cell)]
    out = []
    for s, e in zip(starts, ends):
        cx, cy = x[s:e].mean(), y[s:e].mean()
        foot = z[s:e].min() - SINK
        top = np.percentile(z[s:e] + H[s:e], TOP_PCT)
        cover = float(np.sum(np.pi * r[s:e] ** 2))
        w = float(np.clip(CELL * math.sqrt(min(1.0, cover / CELL ** 2)) * 1.15, WIDTH_MIN, WIDTH_MAX))
        w = max(w, 2.2 * float(r[s:e].max()))
        kc = np.bincount(k[s:e], minlength=3)
        kind = int(np.argmax(kc))
        if kc.max() < 0.7 * (e - s):
            kind = 3
        hs = _hash(key[0], key[1], cell[s])
        out.append((cx, cy, foot, w, top - foot, kind, (hs % 900) / 10.0, (hs >> 10) % 2, (hs >> 12) % 1000))
    return out


def mesh(cs):
    """Positions, triangles, uvs (Collada: v up), colours of a tile's cards."""
    nc = len(cs)
    P = np.zeros((nc * 8, 3))
    UV = np.zeros((nc * 8, 2))
    C = np.zeros((nc * 8, 4), np.uint8)
    T = np.zeros((nc * 4, 3), np.int64)
    cw, ch = 1.0 / 4, 1.0 / 2
    for i, (cx, cy, foot, w, h, kind, yaw, var, jit) in enumerate(cs):
        u0 = kind * cw + 0.002
        u1 = (kind + 1) * cw - 0.002
        v0 = 1.0 - (var + 1) * ch + 0.002          # cell row var (0: the image's top row)
        v1 = 1.0 - var * ch - 0.002
        f = 0.88 + 0.24 * (jit / 1000.0)
        col = np.clip(np.array(COLOUR[KINDS[kind]]) * f, 0, 1)
        rgba = np.r_[np.round(col * 255), 255].astype(np.uint8)
        for q in range(2):
            a = math.radians(yaw + 90 * q)
            dx, dy = 0.5 * w * math.cos(a), 0.5 * w * math.sin(a)
            b = i * 8 + q * 4
            P[b:b + 4] = [(cx - dx, cy - dy, foot), (cx + dx, cy + dy, foot),
                          (cx + dx, cy + dy, foot + h), (cx - dx, cy - dy, foot + h)]
            # the second quad mirrored in u: the two faces of a card do not show the same clump
            if q == 0:
                UV[b:b + 4] = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            else:
                UV[b:b + 4] = [(u1, v0), (u0, v0), (u0, v1), (u1, v1)]
            C[b:b + 4] = rgba
            T[i * 4 + q * 2] = (b, b + 1, b + 2)
            T[i * 4 + q * 2 + 1] = (b, b + 2, b + 3)
    return P, T, UV, C


def tile_bytes(cs):
    P, T, UV, C = mesh(cs)
    N = np.tile([0.0, 0.0, 1.0], (len(P), 1))
    return cdae.encode(P, T, normals=N, uvs=UV, material=MAT, colors=C, object_name="fartrees")


def material(tex_path):
    from blocks import bng
    return bng.material(MAT, color_map=tex_path, base_color=[1, 1, 1, 1], vert_color=True, roughness=1.0,
                        alpha_test=70, double_sided=True, extra={"castShadows": False})


# ------------------------------------------------------------------ the texture
def texture(path, seed=7):
    """The clump atlas: 4 kinds (columns) x 2 variants (rows) of 256 px, near-white shading with a cut-out alpha."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    W, Hh = ATLAS
    cw, ch = W // 4, Hh // 2
    img = np.zeros((Hh, W, 4), np.float32)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    v = 1.0 - yy / ch                  # 0 at the bottom, 1 at the top
    u = xx / cw

    def noise(scale):
        g = rng.random((ch // scale + 2, cw // scale + 2)).astype(np.float32)
        gy, gx = yy / scale, xx / scale
        i, j = gy.astype(int), gx.astype(int)
        fy, fx = gy - i, gx - j
        a = g[i, j] * (1 - fx) + g[i, j + 1] * fx
        b = g[i + 1, j] * (1 - fx) + g[i + 1, j + 1] * fx
        return a * (1 - fy) + b * fy

    def cone(lum, alpha, px, h, hw):
        """a conifer: apex (px, h), half width hw at the bottom, ragged sides, lit from the left."""
        rel = (h - v) / max(h, 1e-3)                       # 0 at the apex, 1 at the foot
        edge = hw * np.clip(rel, 0, 1) * (0.85 + 0.3 * noise(6))
        inside = (v <= h) & (np.abs(u - px) <= edge)
        side = np.clip((u - px) / np.maximum(edge, 1e-3), -1, 1)
        l = 0.80 - 0.18 * side + 0.12 * (1 - rel) + 0.12 * (noise(3) - 0.5)
        l = l * (0.9 + 0.1 * np.sin(rel * 40 + noise(4) * 6))          # tiers of branches
        m = inside & (alpha < 0.5)
        lum[m], alpha[m] = l[m], 1.0
        m = inside & (alpha >= 0.5) & (l < lum)                          # the nearer crown in front: darker overlap
        lum[m] = 0.5 * (lum[m] + l[m])

    def blob(lum, alpha, px, py, rx, ry):
        """a broadleaf crown: a ragged ellipse, lit from the upper left, darker at its foot."""
        dx, dy = (u - px) / rx, (v - py) / ry
        d = np.sqrt(dx * dx + dy * dy)
        inside = d <= 0.82 + 0.3 * noise(5) + 0.12 * noise(2)
        nz = np.sqrt(np.clip(1 - d * d, 0, 1))
        l = 0.62 + 0.28 * (-0.5 * dx + 0.6 * dy + 0.6 * nz) / 1.4 + 0.16 * (noise(2) - 0.5)
        m = inside & ((alpha < 0.5) | (py < 0.5))                         # lower crowns drawn over the higher ones
        lum[m], alpha[m] = l[m], 1.0

    for kind in range(4):
        for var in range(2):
            lum = np.zeros((ch, cw), np.float32)
            alpha = np.zeros((ch, cw), np.float32)
            # crowns spread over the whole width (a card is as wide as its cell's crowns cover it), the back row first
            if kind in (0, 3):
                n = 8 if kind == 0 else 4
                xs = np.sort((np.arange(n) + rng.uniform(0.2, 0.8, n)) / n)
                for px in rng.permutation(xs):
                    cone(lum, alpha, 0.06 + 0.88 * px, rng.uniform(0.55, 0.98), rng.uniform(0.11, 0.17))
            if kind in (1, 3):
                for row, (n, lo, hi) in enumerate(((4, 0.50, 0.68), (5, 0.30, 0.42))):
                    n = n if kind == 1 else n // 2 + 1
                    xs = (np.arange(n) + rng.uniform(0.25, 0.75, n)) / n
                    for px in xs:
                        py = rng.uniform(lo, hi)
                        blob(lum, alpha, 0.08 + 0.84 * px, py, rng.uniform(0.13, 0.19), rng.uniform(0.18, 0.26))
            if kind == 2:
                xs = (np.arange(7) + rng.uniform(0.2, 0.8, 7)) / 7
                for px in xs:
                    py = rng.uniform(0.45, 0.62)
                    blob(lum, alpha, 0.06 + 0.88 * px, py, rng.uniform(0.055, 0.08), py * 0.92)
            # under the crowns, down to the card's foot: the shaded foliage of the lower trees (no trunks or sky
            # under a wood seen from kilometres away)
            covered = alpha > 0.5
            any_ = covered.any(0)
            low = np.where(any_, ch - 1 - np.argmax(covered[::-1], 0), 0)    # the lowest crown pixel of each column
            under = (yy >= low[None, :] - 1) & any_[None, :] & ~covered
            shade = 0.42 + 0.12 * noise(3)
            lum[under], alpha[under] = shade[under], 1.0
            rgb = np.clip(lum, 0, 1)[..., None] * np.array([0.96, 1.0, 0.92], np.float32)
            # the colour of the clump under its cut-out too: no dark fringe in the mipmaps
            fill = rgb[alpha > 0.5].mean(0) if (alpha > 0.5).any() else np.array([0.7, 0.7, 0.7])
            rgb[alpha < 0.5] = fill
            r0, c0 = var * ch, kind * cw
            img[r0:r0 + ch, c0:c0 + cw, :3] = rgb
            img[r0:r0 + ch, c0:c0 + cw, 3] = alpha
    out = np.clip(np.round(img * 255), 0, 255).astype(np.uint8)
    if os.path.lexists(path):
        os.remove(path)
    Image.fromarray(out, "RGBA").save(path)
    return path


# ------------------------------------------------------------------ the whole level
_W = {}


def _init(names, origin, tile_m, out_dir):
    _W.update(types=Types(names), origin=origin, tile_m=tile_m, out_dir=out_dir)


def _one(item):
    """Write one tile's far trees (rows as JSON bytes or a list); (key, cards, bytes) or None."""
    key, rows = item
    if isinstance(rows, (bytes, str)):
        rows = json.loads(rows)
    cx, cy = (int(v) for v in key.split("_"))
    o, tm = _W["origin"], _W["tile_m"]
    cs = cards(rows, _W["types"], o[0] + cx * tm, o[1] + cy * tm, tm, (cx, cy))
    if not cs:
        return None
    data = tile_bytes(cs)
    p = os.path.join(_W["out_dir"], f"t_{key}.cdae")
    if os.path.lexists(p):
        os.remove(p)
    with open(p, "wb") as f:
        f.write(data)
    return key, len(cs), len(data)


def build(tiles, names, origin, tile_m, out_dir, level="ticino", workers=1):
    """tiles: iterable of (key "cx_cy", rows or their JSON bytes). Writes out_dir/t_<key>.cdae, the texture and the
    material; returns the keys written."""
    os.makedirs(out_dir, exist_ok=True)
    keys, ncards, nbytes = [], 0, 0
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
        if len(keys) % 2000 == 0:
            log("far trees: %d tiles, %d cards, %.0f MB (%.0f s)" % (len(keys), ncards, nbytes / 1e6, time.time() - t0))
    if pool:
        pool.close()
        pool.join()
    texture(os.path.join(out_dir, TEX))
    from blocks import bng
    bng.write_materials(os.path.join(out_dir, "fartrees.materials.json"),
                        [material(f"/levels/{level}/{DIR}/{TEX}")])
    log("far trees: %d tiles, %d cards, %.0f MB in %.0f s" % (len(keys), ncards, nbytes / 1e6, time.time() - t0))
    return sorted(keys)


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
    keys = build(tiles(), st["forestTypes"], st["origin"], tile_m, os.path.join(a.out, DIR), workers=a.workers)
    print(len(keys), "tiles")


if __name__ == "__main__":
    main()
