"""Far ground beyond the far tiles: coarser levels of the 384 m far tiles (far/f_<cx>_<cy>.cdae, blocks.write_far), so
the whole of Ticino stands on the horizon instead of nothing past ~6 km (michi 2026-10-31: "io voglio vedere di più da
lontano"). The idea is BeamNG.Earth's far field (c) 2026 TecnaGamer, MIT licence (github.com/TecnaGamer/BeamNG.Earth,
server/farfield.py, mod farfield.lua): a quadtree of render-only TSStatic tiles, finer near the camera, a fixed number
of tiles per ring, the coarse tiles replaced only once their finer ones are there (no holes).

Level k (2..5) tile (i, j) covers the far tiles [i * 2^k, (i + 1) * 2^k) x [j * 2^k, ...): 1,536 m (48 m between
vertices), 3,072 m (96 m), 6,144 m (192 m), 12,288 m (384 m); always 33 x 33 vertices like a far tile, so a coarse
tile costs the game what a far tile costs. Level 1 is left out (objects.lua goes from level 2 straight to the far
tiles): it would be 9,800 more files for 3-6 km, which the far tiles already cover today.

Heights are the far tiles' own vertices (every 2^k-th); the vertices on a tile's border take the highest far-tile
height along their stretch of the border, and the skirt goes down to the lowest one plus a margin: a coarse tile's
edge is never under the finer tile beside it, and its skirt closes the step to it. Colours are the mean of the far
tiles' vertex colours round each vertex. Material, shading and colours are those of the far tiles (no new look).

    farlod.build(read_far, keys, origin, tile_m, out_dir) -> {level: [keys]}       (region_base.py)
    python farlod.py --tag ticino-all --out <folder>                                (a test: all zones of a release)
"""
import argparse
import collections
import io
import json
import os
import re
import sys
import time
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402

LEVELS = (2, 3, 4, 5)
K = 32                      # squares per far tile edge (blocks.write_far: cell 256 samples / far_step 8)
SKIRT_MARGIN = 3.0          # m under the lowest finer height along a border stretch
FAR_MAT = "tc_far_ground"   # blocks.FAR_MAT
DIR = "farlod"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def tile_grid(data, tile_m):
    """Heights (33, 33) and colours (33, 33, 3) of one far tile .cdae, rows along +y; NaN where no vertex."""
    s = cdae.decode(data)
    m = s["meshes"][0]
    a = cdae.mesh_arrays(m)
    P = a["verts"]
    n, size, cb = m["colors"]
    C = np.frombuffer(cb, np.uint8).reshape(n, -1)[:, :3] if n else np.full((len(P), 3), 128, np.uint8)
    step = tile_m / K
    ix = np.rint(P[:, 0] / step).astype(int)
    iy = np.rint(P[:, 1] / step).astype(int)
    ok = (ix >= 0) & (ix <= K) & (iy >= 0) & (iy <= K)
    H = np.full((K + 1, K + 1), -np.inf, np.float32)
    col = np.zeros((K + 1, K + 1, 3), np.float32)
    # a skirt vertex has the xy of a border vertex and is 4 m lower: the highest vertex of an xy is the ground
    order = np.argsort(P[:, 2])
    for v in order[ok[order]]:
        H[iy[v], ix[v]] = P[v, 2]
        col[iy[v], ix[v]] = C[v]
    H[~np.isfinite(H)] = np.nan
    return H, col


class Ground:
    """All far tiles on one grid of tile_m / K metres."""

    def __init__(self, keys, tile_m):
        xy = np.array([list(map(int, k.split("_"))) for k in keys])
        self.cx0, self.cy0 = xy.min(0)
        self.ncx, self.ncy = xy.max(0) - xy.min(0) + 1
        self.tile_m = tile_m
        self.H = np.full((self.ncy * K + 1, self.ncx * K + 1), np.nan, np.float32)
        self.C = np.zeros((self.ncy * K + 1, self.ncx * K + 1, 3), np.float32)
        self.has = set(keys)
        self.n = 0

    def put(self, key, data):
        cx, cy = map(int, key.split("_"))
        H, col = tile_grid(data, self.tile_m)
        r0, c0 = (cy - self.cy0) * K, (cx - self.cx0) * K
        sub = self.H[r0:r0 + K + 1, c0:c0 + K + 1]
        put = np.isfinite(H)
        # the shared border: keep the higher of the two tiles' heights (they are the same samples)
        keep = put & ~(np.isfinite(sub) & (sub >= H))
        sub[keep] = H[keep]
        self.C[r0:r0 + K + 1, c0:c0 + K + 1][keep] = col[keep]
        self.n += 1

    def save(self, path):
        np.savez(path, H=self.H, C=self.C.astype(np.uint8), o=[self.cx0, self.cy0, self.ncx, self.ncy, self.tile_m])

    @classmethod
    def load(cls, path, keys):
        d = np.load(path)
        g = cls.__new__(cls)
        g.H, g.C = d["H"], d["C"].astype(np.float32)
        g.cx0, g.cy0, g.ncx, g.ncy, tm = d["o"]
        g.cx0, g.cy0, g.ncx, g.ncy, g.tile_m = int(g.cx0), int(g.cy0), int(g.ncx), int(g.ncy), float(tm)
        g.has, g.n = set(keys), len(keys)
        return g


def coarse_tile(g, k, i, j):
    """positions (n, 3) from the tile's corner, triangles, colours (n, 4) uint8 of level k tile (i, j); None if empty."""
    s = 1 << k                                   # far-grid squares between two vertices (and far tiles per edge)
    r0 = (j * s - g.cy0) * K                     # the tile's corner on the far grid
    c0 = (i * s - g.cx0) * K
    rows = r0 + np.arange(K + 1) * s
    cols = c0 + np.arange(K + 1) * s
    Hn, Wn = g.H.shape

    def take(r, c):
        r, c = np.asarray(r), np.asarray(c)
        inside = (r >= 0) & (r < Hn) & (c >= 0) & (c < Wn)
        out = np.full(np.broadcast(r, c).shape, np.nan, np.float32)
        out[inside] = g.H[np.clip(r, 0, Hn - 1), np.clip(c, 0, Wn - 1)][inside]
        return out

    R, C = np.meshgrid(rows, cols, indexing="ij")
    h = take(R, C)
    if not np.isfinite(h).any():
        return None
    lo = np.full_like(h, np.nan)
    half = s // 2
    # border vertices: the highest far height along their stretch of the border (lowest kept for the skirt)
    for side in range(4):
        for t in range(K + 1):
            if side == 0:
                rr, cc = rows[0], cols[t] + np.arange(-half, half + 1); a, b = 0, t
            elif side == 1:
                rr, cc = rows[-1], cols[t] + np.arange(-half, half + 1); a, b = K, t
            elif side == 2:
                rr, cc = rows[t] + np.arange(-half, half + 1), cols[0]; a, b = t, 0
            else:
                rr, cc = rows[t] + np.arange(-half, half + 1), cols[-1]; a, b = t, K
            v = take(rr, cc)
            # only the stretch inside the tile's edge (a corner's stretch runs on along both sides)
            if np.isfinite(v).any():
                h[a, b] = np.nanmax(v)
                lo[a, b] = np.nanmin(v)
    # colours: mean of the far colours in the square round each vertex
    col = np.zeros((K + 1, K + 1, 3), np.float32)
    for a in range(K + 1):
        ra = slice(max(0, rows[a] - half), max(0, min(Hn, rows[a] + half + 1)))
        for b in range(K + 1):
            if not np.isfinite(h[a, b]):
                continue
            cb = slice(max(0, cols[b] - half), max(0, min(Wn, cols[b] + half + 1)))
            hh = g.H[ra, cb]
            cc = g.C[ra, cb][np.isfinite(hh)]
            col[a, b] = cc.mean(0) if len(cc) else (90, 95, 70)
    step = g.tile_m / K * s
    X, Y = np.meshgrid(np.arange(K + 1) * step, np.arange(K + 1) * step)
    valid = np.isfinite(h).ravel()
    V = np.stack([X.ravel(), Y.ravel(), np.nan_to_num(h).ravel()], 1)
    ii = np.arange((K + 1) ** 2).reshape(K + 1, K + 1)
    a, b, c2, d = ii[:-1, :-1].ravel(), ii[:-1, 1:].ravel(), ii[1:, :-1].ravel(), ii[1:, 1:].ravel()
    T = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c2], 1)])
    T = T[valid[T].all(1)]
    if not len(T):
        return None
    # skirt: the border ring again, down to under the lowest finer height of its stretch
    ring = np.concatenate([ii[0, :], ii[1:, -1], ii[-1, -2::-1], ii[-2:0:-1, 0]])
    hz, lz = h.ravel(), lo.ravel()
    drop = np.where(np.isfinite(lz), hz - lz, 0.0) + SKIRT_MARGIN + 0.5 * s
    Vs = V[ring] - np.stack([np.zeros(len(ring)), np.zeros(len(ring)), drop[ring]], 1)
    base = len(V)
    nr = len(ring)
    j_ = np.arange(nr)
    A, Bn = ring[j_], ring[(j_ + 1) % nr]
    As, Bs = base + j_, base + (j_ + 1) % nr
    Ts = np.concatenate([np.stack([A, As, Bs], 1), np.stack([A, Bs, Bn], 1)])
    okq = valid[A] & valid[Bn]
    Ts = Ts[np.concatenate([okq, okq])]
    cols8 = np.concatenate([col.reshape(-1, 3), np.full(((K + 1) ** 2, 1), 255.0)], 1)
    C8 = np.clip(np.round(np.concatenate([cols8, cols8[ring]])), 0, 255).astype(np.uint8)
    P = np.concatenate([V, Vs])
    TT = np.concatenate([T, Ts])
    # drop the vertices no triangle uses (NaN corners outside Ticino)
    used = np.zeros(len(P), bool)
    used[TT.ravel()] = True
    remap = np.cumsum(used) - 1
    return P[used], remap[TT], C8[used]


def build(g, out_dir, levels=LEVELS):
    """Every coarse tile of g into out_dir/l<k>_<i>_<j>.cdae; returns {level: [keys]}."""
    os.makedirs(out_dir, exist_ok=True)
    tiles = collections.defaultdict(set)
    for key in g.has:
        cx, cy = map(int, key.split("_"))
        for k in levels:
            tiles[k].add((cx >> k, cy >> k))       # floor division for negative keys too
    out, nbytes = {}, 0
    for k in levels:
        keys = []
        for i, j in sorted(tiles[k]):
            t = coarse_tile(g, k, i, j)
            if t is None:
                continue
            P, T, C8 = t
            key = f"{i}_{j}"
            nbytes += cdae.write(os.path.join(out_dir, f"l{k}_{key}.cdae"), P, T,
                                 uvs=np.zeros((len(P), 2)), material=FAR_MAT, colors=C8, object_name="farground")
            keys.append(key)
        out[str(k)] = keys
        log("far level %d (%d m tiles): %d tiles" % (k, int(g.tile_m) << k, len(keys)))
    log("far levels: %.1f MB" % (nbytes / 1e6))
    return out


def far_members(zf):
    """(key, name) of the far tiles in a slice zip, in the zip's order (read in one sweep)."""
    infos = sorted((i for i in zf.infolist() if re.search(r"/far/f_-?\d+_-?\d+\.cdae$", i.filename)),
                   key=lambda i: i.header_offset)
    return [(re.search(r"f_(-?\d+_-?\d+)\.cdae$", i.filename).group(1), i.filename) for i in infos]


def read_release(tag, keys, tile_m, cache=None, workers=6):
    """The Ground of every far tile in the slice zips of release tag (HTTP range, zipremote)."""
    import zipremote
    from concurrent.futures import ThreadPoolExecutor
    if cache and os.path.exists(cache):
        log("far ground from", cache)
        return Ground.load(cache, keys)
    ids = {n: i for n, i in zipremote.assets(tag).items() if re.fullmatch(r"ticino_ti_[m0-9]+_[m0-9]+_\d+\.zip", n)}
    g = Ground(keys, tile_m)

    def one(item):
        name, aid = item
        zf = zipremote.open_zip(aid)
        got = []
        for key, member in far_members(zf):
            if key in g.has:
                got.append((key, zf.read(member)))
        return name, got

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for name, got in ex.map(one, sorted(ids.items())):
            for key, data in got:
                g.put(key, data)
            log("%s: %d far tiles (%d of %d, %.0f s)" % (name, len(got), g.n, len(keys), time.time() - t0))
    if cache:
        g.save(cache)
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="ticino-all")
    ap.add_argument("--stream", required=True, help="stream.json of the base (far keys, cell, square)")
    ap.add_argument("--out", required=True, help="level folder levels/ticino (writes farlod/)")
    ap.add_argument("--cache", help="npz of the far ground (read once)")
    a = ap.parse_args()
    st = json.load(open(a.stream))
    tile_m = st["cell"] * st["square"]
    g = read_release(a.tag, st["far"], tile_m, a.cache)
    lod = build(g, os.path.join(a.out, DIR))
    with open(os.path.join(a.out, DIR, "farlod.json"), "w") as f:
        json.dump(lod, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
