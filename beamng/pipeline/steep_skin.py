"""The steep banks along the roads drawn as a smooth mesh over the terrain (v3.0).

Between the hairpins, in the cuttings and on the embankments the terrain drops 4-15 m within a few terrain
squares (TER_SQUARE m): its triangles show as big facets (a sawtooth along the top of the drop) and its
material, projected from above, is smeared down the slope. Here, near the roads (REACH m of a road or path
surface), the terrain vertices steeper than STEEP degrees and DILATE squares around them (not under a road,
a wall, a building, the railway or the lake) take a skin:
- a mesh every TER_SQUARE / 2 m (a fan of 8 triangles per square) on a bicubic surface through the terrain vertices (round instead of
  faceted, the same at the vertices), over the terrain everywhere (EPS m over the higher of the two ways
  the game may split a square); the terrain under its inner squares lowered by up to LOWER m (smoothly,
  none on its edge) so the round surface stays over it, its heights smoothed under the skin; the skin cut
  along a smooth line (a blurred mask), not in the steps of the squares, with its colours blurred;
- its texture (earth, stones, roots and moss, drawn here) laid on the slope: every triangle takes the
  projection of the axis its face is turned to (as the terrain's side projection), TILE_M m per repeat;
- its colour that of the terrain there (the base colour maps of the terrain materials, per vertex);
- with collision (the car rides on it where it leaves the road), in TILE x TILE vertex tiles;
- v3.1: three detail levels per tile (the v3.0 skin, 18 million triangles drawn at every distance, cost more
  frames than anything else on the map): near (LOD_PX[0] px on screen and more: about LOD_DIST[0] m) the
  round skin as above; then two triangles per terrain square (LOD_LIFT[1] m higher, the plane of a square
  over both ways the game may split it); then two per 2 x 2 squares; nothing beyond about LOD_DIST[2] m,
  where the terrain under it is lowered by LOWER at most and looks the same. The far levels cast no shadow
  (the terrain under them casts the same) on a material of their own (MAT_FAR).

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish steep_skin
"""
import io, json, os, tempfile, time, zipfile
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import bng
import optimize_level
from lamps import read_items
from config import LEVEL_NAME

STEEP = 38.0                  # degrees, terrain vertices this steep (and more) take the skin
REACH = 30.0                  # m from a road or path surface
DILATE = 3                    # terrain squares of skin around the steep vertices
MIN_VERTS = 12                # smaller patches of steep vertices are left as they are
LOWER = 0.25                  # m, the terrain under the inner squares of a skin lowered by this much
EPS = 0.03                    # m, the skin over the terrain
EDGE_BLUR = 2.0               # terrain squares, blur of the skin mask: its edge a smooth line
EDGE_ISO = 0.55               # the skin cut where the blurred mask is under this
EDGE_FADE = 0.3               # ... and down onto the terrain where it is under EDGE_ISO + this
SMOOTH = 0.8                  # terrain squares, blur of the heights the skin is drawn through
RING_BLUR = 1.2               # terrain squares, blur of the terrain under the skin
COLOUR_BLUR = 1.5             # terrain squares, blur of the vertex colours
INSIDE_IN = 2.0               # half squares: the cut at least this far inside the outline of the skin squares
INSIDE_FADE = 3.0             # half squares further in: the skin down onto the terrain over these
INSIDE_BLUR = 1.5             # half squares, blur of the distance inside (a round line, not the staircase)
TILE = 128                    # terrain vertices per side of a mesh tile (v3.0: 256; smaller tiles change
                              # their detail level closer to the camera)
LOD_DIST = (350.0, 1000.0, 3000.0)   # m: round skin, one quad per square, one per 2 x 2 squares, nothing
LOD_LIFT = (0.0, 0.04, 0.12)  # m over the lattice heights of the level (the coarse planes stay over the terrain)
PIX_K = 1000.0                # = optimize_level.PIX_K: pixels on screen per (radius / distance)
TILE_M = 3.0                  # m of slope per repeat of the texture
TEX_N = 512                   # pixels of the texture
TEX_MEAN = 205.0              # mean sRGB of the texture: the vertex colours bring it to the terrain's
FOOT_STEP = 0.5               # m between the samples of the shapes' footprints
D = "art/shapes/terrain_skin"
MAT = "mp_steep_bank"
MAT_FAR = "mp_steep_bank_far"
ROADS = ("roads",)
SOLID = ("roads", "walls", "buildings", "railway")


# ------------------------------------------------------------------------------------------------ texture

def bank_texture(n=TEX_N, seed=47):
    """(colour, normal) uint8 images of the bank: earth with stones, small roots and moss patches, tileable,
    its mean TEX_MEAN (neutral: the vertex colours tint it)."""
    from bld_textures import noise, normal_map, to8
    from surface_textures import _domes
    rng = np.random.default_rng(seed)
    fine, mid, patch = noise(n, n, 1.0, rng), noise(n, n, 8, rng), noise(n, n, 45, rng)
    hgt = 1.0 * fine + 3.0 * mid + 4.0 * patch
    col = np.array([0.50, 0.44, 0.36], np.float32) * (1 + 0.10 * fine + 0.10 * mid - 0.10 * np.clip(patch, 0, None))[..., None]
    # stones 3-12 cm, grey gneiss and brown
    mm = TILE_M * 1000 / n
    h, sid = _domes(n, rng, 160, (15 / mm, 60 / mm), aspect=(1.0, 1.8))
    on = sid >= 0
    tone = np.array([[0.58, 0.56, 0.52], [0.48, 0.47, 0.45], [0.55, 0.49, 0.41]], np.float32)[rng.integers(0, 3, 160)]
    col[on] = (tone[np.maximum(sid, 0)] * (0.85 + 0.3 * h[..., None]) * (1 + 0.05 * fine[..., None]))[on]
    hgt = np.where(on, hgt + 8.0 * h, hgt)
    # moss and grass tufts where the patch noise is high
    moss = np.clip((noise(n, n, 20, rng) - 0.6) * 1.5, 0, 1) * np.clip(1 - h * 3, 0, 1)
    col = col * (1 - moss[..., None]) + np.array([0.38, 0.44, 0.24], np.float32) * (1 + 0.15 * fine)[..., None] * moss[..., None]
    # roots: thin dark curves, mostly across the slope
    for _ in range(18):
        p = rng.random(2) * n
        a = rng.normal(0, 0.5)
        for _ in range(int(rng.uniform(40, 160))):
            a += rng.normal(0, 0.12)
            p = (p + [np.cos(a), np.sin(a)]) % n
            r, c = int(p[1]), int(p[0])
            col[r, c] = col[(r + 1) % n, c] = [0.27, 0.20, 0.14]
            hgt[r, c] += 2.0
    col = np.clip(col * (TEX_MEAN / 255.0 / col.reshape(-1, 3).mean()), 0, 1)
    return to8(col), normal_map(hgt, 1.0 / mm)


def materials():
    t = f"/levels/{LEVEL_NAME}/{D}"
    m = bng.material(MAT, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                     roughness=0.95, ground_type="DIRT", vert_color=True)
    far = bng.material(MAT_FAR, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                       roughness=0.95, ground_type="DIRT", vert_color=True, extra={"castShadows": False})
    return [m, far]


# ------------------------------------------------------------------------------------------------ terrain

def footprints(zi, lv, n, x0, y0, sq, groups):
    """(n, n) bool: the terrain vertices nearest to a sample (every FOOT_STEP m) of a triangle of the pipeline
    shapes of the groups (and their subgroups)."""
    out = np.zeros((n, n), bool)
    for f in zi.namelist():
        if not f.endswith("items.level.json") or not any(f.startswith(f"{lv}/main/MissionGroup/{g}/") for g in groups):
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or not sn.endswith(".dae"):
                continue
            try:
                V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            except (AttributeError, ValueError):
                continue
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            for _, idx in parts:
                t = W[idx[:, 0]].reshape(-1, 3, 3)[:, :, :2]
                mark(out, t, x0, y0, sq)
    return out


def mark(out, t, x0, y0, sq):
    """Set the vertices of out nearest to samples every FOOT_STEP m over the triangles t (m, 3, 2)."""
    if not len(t):
        return
    L = np.max(np.linalg.norm(t - np.roll(t, 1, axis=1), axis=2), axis=1)
    k = np.clip(np.ceil(L / FOOT_STEP), 1, 400).astype(int)
    n = out.shape[0]
    for kk in np.unique(k):
        tt = t[k == kk]
        i, j = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1))
        keep = (i + j) <= kk
        a, b = i[keep] / kk, j[keep] / kk
        P = tt[:, 0, None] * (1 - a - b)[None, :, None] + tt[:, 1, None] * a[None, :, None] + tt[:, 2, None] * b[None, :, None]
        c = np.rint((P[..., 0].ravel() - x0) / sq).astype(np.int64)
        r = np.rint((P[..., 1].ravel() - y0) / sq).astype(np.int64)
        ok = (c >= 0) & (c < n) & (r >= 0) & (r < n)
        out[r[ok], c[ok]] = True


def split_max(Hn, R, C):
    """Height of the higher of the two triangulations of the squares of Hn at fractional vertex coordinates
    (R rows, C columns)."""
    n0, n1 = Hn.shape
    r0 = np.clip(np.floor(R).astype(np.int64), 0, n0 - 2)
    c0 = np.clip(np.floor(C).astype(np.int64), 0, n1 - 2)
    fr, fc = R - r0, C - c0
    h00, h01, h10, h11 = Hn[r0, c0], Hn[r0, c0 + 1], Hn[r0 + 1, c0], Hn[r0 + 1, c0 + 1]
    za = np.where(fc >= fr, h00 + fc * (h01 - h00) + fr * (h11 - h01), h00 + fr * (h10 - h00) + fc * (h11 - h10))
    zb = np.where(fr + fc <= 1, h00 + fc * (h01 - h00) + fr * (h10 - h00),
                  h11 + (1 - fc) * (h10 - h11) + (1 - fr) * (h01 - h11))
    return np.maximum(za, zb)


def skin_mask(H, road, solid, sq):
    """(skin vertices, steep vertices) of a block of terrain heights H: steep near a road, grown by DILATE,
    never on solid."""
    gy, gx = np.gradient(H, sq)
    steep = np.degrees(np.arctan(np.hypot(gx, gy))) > STEEP
    near = ndi.distance_transform_edt(~road) * sq <= REACH if road.any() else np.zeros_like(steep)
    S = steep & near & ~solid
    lab, k = ndi.label(S, np.ones((3, 3)))
    if k:
        size = np.bincount(lab.ravel())
        S = (size >= MIN_VERTS)[lab] & S
    S = ndi.binary_dilation(S, np.ones((3, 3)), iterations=DILATE) & ~solid
    return S, steep


def tile_skin(H, S, sq, core, sol):
    """Skin of a block: (new terrain heights, changed vertices, squares (r, c) of the core window). The terrain
    under it lowered under the inner squares and smoothed (not on sol)."""
    dch = ndi.distance_transform_cdt(S, metric="chessboard").astype(np.float64)
    Hn = H - LOWER * np.clip((dch - 1) / 2, 0, 1)
    w = np.clip(dch / 2.0, 0, 1) * ~sol                 # its edge vertices half way: the ground beyond as it was
    Hn = Hn + w * (ndi.gaussian_filter(H, RING_BLUR) - H)
    low = np.abs(Hn - H) > 0.005
    sqm = S[:-1, :-1] & S[:-1, 1:] & S[1:, :-1] & S[1:, 1:]
    r0, r1, c0, c1 = core
    sqm_core = np.zeros_like(sqm)
    sqm_core[r0:r1, c0:c1] = sqm[r0:r1, c0:c1]
    rr, cc = np.nonzero(sqm_core)
    return Hn, low, rr, cc


def lattice(H, Hn, rr, cc):
    """Lattice points (half squares) of the squares rr, cc: (keys (k, 2) in half-square units, z)."""
    keys = np.unique(np.concatenate([np.column_stack([2 * rr + a, 2 * cc + b]) for a in range(3) for b in range(3)]), axis=0)
    R, C = keys[:, 0] / 2.0, keys[:, 1] / 2.0
    zs = ndi.map_coordinates(H, [R, C], order=3, mode="nearest")
    return keys, np.maximum(zs, split_max(Hn, R, C) + EPS)


def inside(keys):
    """Per lattice point (keys in half squares): how far inside the skin squares it is, as a cut value (< 0 on
    their outline and up to INSIDE_IN half squares in, EDGE_FADE further in), smoothed: the blurred mask of the
    terrain vertices would cut across the notches of the squares' staircase and leave it as the edge, in teeth
    (seen on the slope) and with a lip over the terrain."""
    k0 = keys.min(0)
    k = keys - k0 + 2
    G = np.zeros(k.max(0) + 3, bool)
    G[k[:, 0], k[:, 1]] = True
    d = ndi.gaussian_filter(ndi.distance_transform_edt(G), INSIDE_BLUR)
    return (d[k[:, 0], k[:, 1]] - INSIDE_IN) / INSIDE_FADE * EDGE_FADE


def clip(P, N, col, T, f):
    """The triangles T cut along f = 0 (f per vertex), the parts where f >= 0 kept: new vertices on the cut
    edges (positions, normals and colours interpolated)."""
    s = f[T] >= 0
    keep = T[s.all(1)]
    mixed = T[s.any(1) & ~s.all(1)]
    P, N, col = list(P), list(N), list(col)
    out = [keep]
    cache = {}

    def cut(i, j):
        k = (min(i, j), max(i, j))
        if k not in cache:
            t = f[i] / (f[i] - f[j])
            P.append(P[i] + t * (P[j] - P[i]))
            n = N[i] + t * (N[j] - N[i])
            N.append(n / max(np.linalg.norm(n), 1e-9))
            col.append(col[i] + t * (col[j] - col[i]))
            cache[k] = len(P) - 1
        return cache[k]
    new = []
    for tri in mixed:
        poly = []
        for e in range(3):
            i, j = tri[e], tri[(e + 1) % 3]
            if f[i] >= 0:
                poly.append(i)
            if (f[i] >= 0) != (f[j] >= 0):
                poly.append(cut(i, j))
        for e in range(1, len(poly) - 1):
            new.append((poly[0], poly[e], poly[e + 1]))
    if new:
        out.append(np.array(new, np.int64))
    return np.array(P), np.array(N), np.array(col), np.concatenate(out)


def tile_mesh(mb, keys, z, rr, cc, x0, y0, sq, colour, wv=None, lods=()):
    """Triangles of the skin squares into mb, one add per projection axis; lods: [(k, lift, MeshBuilder)] the
    far detail levels (coarse_mesh), filled from the same lattice."""
    span = int(keys[:, 1].max()) + 2
    lut = {int(k): i for i, k in enumerate(keys[:, 0] * span + keys[:, 1])}
    P = np.column_stack([x0 + keys[:, 1] * sq / 2, y0 + keys[:, 0] * sq / 2, z])
    # vertex normals from the lattice (central differences over the neighbours present)
    idx = lambda dr, dc: np.array([lut.get(int((a + dr) * span + b + dc), -1) for a, b in keys])
    e, w, nn, s = idx(0, 1), idx(0, -1), idx(1, 0), idx(-1, 0)
    me = np.arange(len(keys))
    zx = (z[np.where(e >= 0, e, me)] - z[np.where(w >= 0, w, me)]) / ((e >= 0).astype(float) + (w >= 0) + 1e-9) / (sq / 2)
    zy = (z[np.where(nn >= 0, nn, me)] - z[np.where(s >= 0, s, me)]) / ((nn >= 0).astype(float) + (s >= 0) + 1e-9) / (sq / 2)
    N = np.column_stack([-zx, -zy, np.ones(len(z))])
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    # every square a fan of 8 triangles around its centre: both diagonals (the game splits a square along one
    # or the other) are edges of the fan, so the terrain is flat inside every triangle and under it wherever
    # it is under its corners
    ring = ((0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0))
    tris = []
    for r, c in zip(rr, cc):
        ctr = lut[(2 * r + 1) * span + 2 * c + 1]
        p = [lut[(2 * r + a) * span + 2 * c + b] for a, b in ring]
        tris += [(ctr, p[i], p[(i + 1) % 8]) for i in range(8)]
    T = np.array(tris, np.int64)
    col = np.column_stack([colour, np.ones(len(z))])
    for k, lift, mbk in lods:
        coarse_mesh(mbk, keys, P, N, col, rr, cc, wv if wv is not None else np.ones(len(z)), k, lift)
    if wv is not None:
        P, N, col, T = clip(P, N, col, T, wv - EDGE_ISO)
    add_projected(mb, MAT, P, N, col, T)
    return len(T)


def add_projected(mb, mat, P, N, col, T):
    """The triangles T into mb, one add per projection axis (each face takes the axis it is turned to)."""
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    axis = np.argmax(np.abs(fn), axis=1)                 # 0: x (u = y, v = z), 1: y (u = x, v = z), 2: z (u = x, v = y)
    for ax, (ui, vi) in enumerate(((1, 2), (0, 2), (0, 1))):
        Ta = T[axis == ax]
        if not len(Ta):
            continue
        used, inv = np.unique(Ta.ravel(), return_inverse=True)
        uv = np.column_stack([P[used, ui], P[used, vi]]) / TILE_M
        mb.add(mat, P[used], uvs=uv, normals=N[used], tris=inv.reshape(-1, 3), colors=col[used])


def coarse_mesh(mb, keys, P, N, col, rr, cc, wv, k, lift):
    """Far detail level: two triangles per k x k terrain squares of the skin (k = 1, 2), the corners at the
    lattice heights (lift m higher), the diagonal that keeps the face over the other. Blocks whose lattice is
    cut away entirely (wv under EDGE_ISO at all its points) or that miss a corner are left out."""
    span = int(keys[:, 1].max()) + 2
    lut = {int(a) * span + int(b): i for i, (a, b) in enumerate(keys)}
    blocks = np.unique(np.column_stack([rr // k, cc // k]), axis=0)
    tris = []
    for R, C in blocks:
        r0, c0 = 2 * k * R, 2 * k * C
        q = [lut.get((r0 + a) * span + c0 + b, -1) for a, b in ((0, 0), (0, 2 * k), (2 * k, 2 * k), (2 * k, 0))]
        if min(q) < 0 or max(wv[i] for i in q) < EDGE_ISO:
            continue
        z = P[q, 2]
        if z[0] + z[2] >= z[1] + z[3]:                   # the higher diagonal: the faces over the other split
            tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
        else:
            tris += [(q[0], q[1], q[3]), (q[1], q[2], q[3])]
    if not tris:
        return 0
    T = np.array(tris, np.int64)
    used, inv = np.unique(T.ravel(), return_inverse=True)
    Pc = P[used].copy()
    Pc[:, 2] += lift
    add_projected(mb, MAT_FAR, Pc, N[used], col[used], inv.reshape(-1, 3))
    return len(T)


class BaseColours:
    """Colour (0..1 multiplier of the texture) of the terrain at its vertices: the base colour map of the material
    of the vertex (art/terrains/t_base_<material>_b.png, BASE_FLIP: image row 0 at the north edge)."""

    def __init__(self, zi, lv, names, n):
        import terrain
        self.n, self.img = n, {}
        for i, name in enumerate(names):
            src = terrain.VERGE_OF.get(name, name)
            f = f"{lv}/art/terrains/t_base_{src.lower()}_b.png"
            if f in zi.NameToInfo:
                self.img[i] = np.asarray(Image.open(io.BytesIO(zi.read(f))).convert("RGB"), np.float32)
        self.flip = terrain.BASE_FLIP

    def __call__(self, lay, R, C):
        out = np.full((len(R), 3), 0.55)
        for i, im in self.img.items():
            m = lay == i
            if not m.any():
                continue
            f = self.n / im.shape[0]
            ir = (R[m] / f).astype(int).clip(0, im.shape[0] - 1)
            ic = (C[m] / f).astype(int).clip(0, im.shape[1] - 1)
            if self.flip:
                ir = im.shape[0] - 1 - ir
            out[m] = im[ir, ic] / TEX_MEAN
        return np.clip(out, 0, 1)


# ------------------------------------------------------------------------------------------------ step

def steep_skin_step(root, report=None):
    import walls as pw
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    X0, Y0, sq = float(blk["position"][0]), float(blk["position"][1]), float(blk.get("squareSize", 1.0))
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = pw.read_ter(data)
    road = footprints(zi, lv, n, X0, Y0, sq, ROADS)
    solid = ndi.binary_dilation(footprints(zi, lv, n, X0, Y0, sq, SOLID) | road, iterations=1)
    # the lake: no skin at or under its level (+0.3 m)
    lake = [o for f in zi.namelist() if f.endswith("items.level.json") and "/Water/" in f
            for o in read_items(zi, f) if o.get("class") == "WaterBlock"]
    lake_z = max((float(o["position"][2]) for o in lake), default=-1e9)
    colours = BaseColours(zi, lv, names, n)
    q_new = q.copy()
    files, objs = {}, []
    rep = {"tiles": 0, "squares": 0, "triangles": 0, "steep_vertices": 0, "changed_vertices": 0,
           "changed_max_m": 0.0}
    m = int(np.ceil(REACH / sq)) + DILATE + 4
    for tr in range(0, n - 1, TILE):
        for tc in range(0, n - 1, TILE):
            a0, a1 = max(tr - m, 0), min(tr + TILE + m + 1, n)
            b0, b1 = max(tc - m, 0), min(tc + TILE + m + 1, n)
            H = Z0 + q[a0:a1, b0:b1].astype(np.float64) / 65535.0 * MAXH
            sol = solid[a0:a1, b0:b1] | (H < lake_z + 0.3)
            S, steep = skin_mask(H, road[a0:a1, b0:b1], sol, sq)
            core = (tr - a0, min(tr + TILE, n - 1) - a0, tc - b0, min(tc + TILE, n - 1) - b0)
            if not S[core[0]:core[1] + 1, core[2]:core[3] + 1].any():
                continue
            Hn, low, rr, cc = tile_skin(H, S, sq, core, sol)
            if not len(rr):
                continue
            # the terrain lowered under the core's inner squares only (the margins belong to the next tiles)
            cr = slice(core[0], core[1] + (1 if core[1] + a0 == n - 1 else 0))
            ccs = slice(core[2], core[3] + (1 if core[3] + b0 == n - 1 else 0))
            lo = low[cr, ccs]
            qn = np.clip(np.rint((Hn[cr, ccs] - Z0) / MAXH * 65535.0), 0, 65535).astype(np.uint16)
            Hq = Z0 + np.where(low, np.clip(np.rint((Hn - Z0) / MAXH * 65535.0), 0, 65535), q[a0:a1, b0:b1]) / 65535.0 * MAXH
            keys, z = lattice(ndi.gaussian_filter(H, SMOOTH), Hq, rr, cc)       # rounded crest and toe
            R, C = keys[:, 0] / 2.0, keys[:, 1] / 2.0
            # the edge of the skin: cut along a smooth line (the blurred mask at EDGE_ISO), not the staircase of
            # the squares, and its colours blurred (no spikes of another colour)
            wv = ndi.map_coordinates(ndi.gaussian_filter(S.astype(np.float64), EDGE_BLUR), [R, C], order=1)
            wv = EDGE_ISO + np.minimum(wv - EDGE_ISO, inside(keys))      # the cut never on the squares' staircase
            fl = split_max(Hq, R, C) + EPS                  # down onto the terrain towards the cut: no lip
            z = fl + np.clip((wv - EDGE_ISO) / EDGE_FADE, 0.0, 1.0) * (z - fl)
            gr, gc = np.mgrid[0:a1 - a0, 0:b1 - b0]
            cg = colours(lay[a0:a1, b0:b1].ravel(), (gr + a0).ravel(), (gc + b0).ravel()).reshape(a1 - a0, b1 - b0, 3)
            col = np.column_stack([ndi.map_coordinates(ndi.gaussian_filter(cg[..., k], COLOUR_BLUR), [R, C], order=1)
                                   for k in range(3)])
            mb = bng.MeshBuilder()
            far = [(1, LOD_LIFT[1], bng.MeshBuilder()), (2, LOD_LIFT[2], bng.MeshBuilder())]
            ox, oy = X0 + b0 * sq, Y0 + a0 * sq
            ntri = tile_mesh(mb, keys, z, rr, cc, ox, oy, sq, col, wv, far)
            if not ntri:                                    # nothing left inside the cut: the terrain as it was
                continue
            sub = q_new[a0:a1, b0:b1][cr, ccs]
            q_new[a0:a1, b0:b1][cr, ccs] = np.where(lo, qn, sub)
            origin = np.array([ox + (b1 - b0) * sq / 2, oy + (a1 - a0) * sq / 2, float(np.median(z))])
            with tempfile.TemporaryDirectory() as tmp:
                f = os.path.join(tmp, "s.dae")
                # detail sizes from the radius of the tile's squares: near, middle and far as LOD_DIST
                radius = 0.5 * float(np.hypot(core[1] - core[0], core[3] - core[2])) * sq
                px = [max(2, int(round(radius * PIX_K / d))) for d in LOD_DIST]
                lods = [(px[i + 1], mbk) for i, (_, _, mbk) in enumerate(far) if not mbk.empty()]
                mb.write_dae(f, name=f"skin_{tr}_{tc}", origin=origin, detail=px[0], weld=False, lods=lods)
                rep["triangles_far"] = rep.get("triangles_far", 0) + sum(m.triangle_count() for _, m in lods)
                rel = f"{D}/skin_{tr:04d}_{tc:04d}.dae"
                files[f"{lv}/{rel}"] = open(f, "rb").read()
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True, decal=False)
            ob["__parent"] = "terrain_skin"
            objs.append(ob)
            rep["tiles"] += 1
            rep["squares"] += int(len(rr))
            rep["triangles"] += int(ntri)
            rep["steep_vertices"] += int(steep[core[0]:core[1], core[2]:core[3]].sum())
            rep["changed_vertices"] += int(lo.sum())
            dz = np.abs(Hn - H)[cr, ccs]
            rep["changed_max_m"] = max(rep["changed_max_m"], float(dz.max()) if dz.size else 0.0)
    print("steep skin: %s" % rep, flush=True)
    if objs:
        col_img, nrm_img = bank_texture()
        for name, im in (("t_steep_bank_b.color.png", col_img), ("t_steep_bank_nm.normal.png", nrm_img)):
            b = io.BytesIO()
            Image.fromarray(im).save(b, "PNG", optimize=True)
            files[f"{lv}/{D}/{name}"] = b.getvalue()
        files[f"{lv}/{D}/terrain_skin.materials.json"] = json.dumps({mm["name"]: mm for mm in materials()},
                                                                     indent=1).encode("utf-8")
        files[f"{lv}/main/MissionGroup/level_objects/terrain_skin/items.level.json"] = \
            ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
        mg = f"{lv}/main/MissionGroup/level_objects/items.level.json"
        rows = read_items(zi, mg)
        if not any(r.get("name") == "terrain_skin" and r.get("class") == "SimGroup" for r in rows):
            rows.append({"name": "terrain_skin", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "level_objects"})
        files[mg] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
        files[ter_name] = data[:5] + q_new.astype("<u2").tobytes() + data[5 + 2 * n * n:]
        assert len(files[ter_name]) == len(data)
        with zi.writer() as zo:
            now = time.localtime()[:6]
            for i in zi.infolist():
                nm = i.filename
                if nm in files:
                    ni = zipfile.ZipInfo(nm, now)          # a new date: the game converts the terrain again
                    ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                    zo.writestr(ni, files.pop(nm))
                else:
                    zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for nm, b in files.items():
                zo.writestr(zipfile.ZipInfo(nm, now), b, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
