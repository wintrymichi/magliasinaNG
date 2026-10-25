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
- v3.0 review: three detail levels per tile (the v3.0 skin, 18 million triangles drawn at every distance, cost more
  frames than anything else on the map): near (LOD_PX[0] px on screen and more: about LOD_DIST[0] m) the
  round skin as above; then two triangles per terrain square (LOD_LIFT[1] m higher, the plane of a square
  over both ways the game may split it); then two per 2 x 2 squares; nothing beyond about LOD_DIST[2] m,
  where the terrain under it is lowered by LOWER at most and looks the same. The far levels cast no shadow
  (the terrain under them casts the same) on a material of their own (MAT_FAR).

- v3.1 (the cut slopes, "burroni"): the skin drawn on a lattice seen from above takes a colour per lattice column, and
  on a face of 60-80 degrees one lattice step is 2-4 m of height: the green of the meadow above ran down the cut in
  vertical streaks and the whole face was one smooth, stretched sheet of earth and moss. Now the faces steeper than
  ROCK_DEG (a wavy line, ROCK_JITTER: outcrops on the gentler banks too) are bare rock as in the road cuts of the Malcantone (gneiss in layers, joints,
  lichen): their own material (MAT_ROCK, rock_texture, ROCK_TILE_M m per repeat), a relief of ribs and gullies
  (ROCK_RIB m apart, up to RELIEF m out of the face, along its normal: always over the terrain, never towards the
  road at its foot, TOE_CLEAR m) and their own colour (ROCK_TONE, from a 3D noise of COLOUR_SCALE m: no streaks),
  moss only on the ledges (under MOSS_DEG). The gentler banks keep the earth, their colour pulled towards EARTH
  (less meadow green) and blurred over COLOUR_BLUR squares; the foot of a cut (TOE_SCREE m) greyer, as scree.

- v3.2 (visual review of v3.1, group 3: steep, faceted cuts with a stretched texture): the cuts right beside a road
  (steep vertices only in the ring of the road, STEEP_ROAD) take the skin too; the rock edges that climb more than
  SUB_DZ m are halved, with their own relief; beside a road the relief is small and the skin flat on the terrain only
  at the foot of the face (RELIEF_HAB, CLAMP_HAB); the rock texture without the fine streaks across it.

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
STEEP_ROAD = 45.0             # v3.2: degrees, the same in the ring beside a road (skin_mask: seeds)
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
COLOUR_BLUR = 3.0             # terrain squares, blur of the vertex colours (v3.0: 1.5, vertical streaks on the cuts)
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
ROCK_TEX_MEAN = 150.0         # mean sRGB of the rock texture (v3.1; the vertex colours only shade it)
FOOT_STEP = 0.5               # m between the samples of the shapes' footprints
D = "art/shapes/terrain_skin"
MAT = "mp_steep_bank"
MAT_FAR = "mp_steep_bank_far"
# v3.1: rock on the steepest faces
MAT_ROCK = "mp_steep_rock"
ROCK_DEG = 47.0               # degrees: the faces steeper than this are bare rock (the skin is round: 5 % of it over 55)
ROCK_JITTER = 10.0            # degrees, the line between rock and earth made wavy (outcrops on the gentler banks) by a noise of ROCK_JITTER_M m
ROCK_JITTER_M = 8.0
ROCK_BLEND = 5.0              # degrees over which the rock colour blends into the earth
ROCK_TILE_M = 4.0             # m of rock per repeat of its texture
ROCK_TEX_N = 1024             # pixels of the rock texture
RELIEF = 0.55                 # m, the most a rock face stands out of the smooth skin (ribs and knobs)
ROCK_RIB = 2.6                # m between the ribs and gullies of a rock face (across), ROCK_RIB_V up the face
ROCK_RIB_V = 7.0
ROCK_KNOB = 1.4               # m, size of the smaller knobs on it
TOE_WIN = 9                   # half squares: the foot of a cut, the lowest skin point within this window
TOE_CLEAR = 0.6               # m over the foot of the cut: no relief below (nothing stands out towards the road)
TOE_RAMP = 1.2                # m over TOE_CLEAR in which the relief grows to its full height
TOE_SCREE = 1.0               # m over the foot: scree colour
COLOUR_SCALE = 9.0            # m, the size of the colour patches of the rock (3D noise, not per lattice column)
MOSS_DEG = 63.0               # degrees: rock gentler than this (ledges) may take moss
ROCK_TONE = (0.98, 0.96, 0.92)          # colour multiplier of the rock texture (gneiss grey-brown)
MOSS = (0.70, 0.84, 0.50)               # ... where moss grows on it
EARTH = (1.00, 0.93, 0.84)              # the earth texture's own colour, mixed into the terrain colour by EARTH_MIX
EARTH_MIX = 0.45
SCREE = (0.95, 0.93, 0.90)
ROADS = ("roads",)
SOLID = ("roads", "walls", "buildings", "railway")
HARD = ("walls", "buildings", "railway")   # v3.1: the skin never on these; it goes on down to a road (FOOT)
FOOT = 2                      # v3.1: terrain squares the skin goes on from a steep bank into the road beside it
ROAD_DIVE = 0.06              # m: ... there under the road surface (hidden by it), never over it
ROAD_LIFT_MAX = 1.0           # m: skin points up to this over a road surface go under it (more: a road below)
ROAD_CLAMP = 1.5              # m: within this of a road the skin no higher than the terrain (EPS): the smoothed
                              # lattice lifted the low side of a 5-7 m step into a lip at the road edge (issue #15)
CLAMP_HAB = 2.0               # v3.2: m over the foot of the face: the clamp of ROAD_CLAMP only up to this, released over
CLAMP_RAMP = 1.0              # CLAMP_RAMP m above it
RELIEF_NEAR = 0.12            # m, the most relief within RELIEF_ROAD m (horizontal) of a road: a rib 55 cm out of a
RELIEF_ROAD = 2.0             # vertical cut at the road edge would overhang the lane at mirror height
RELIEF_RAMP = 1.5             # m beyond RELIEF_ROAD in which the relief grows to RELIEF
RELIEF_HAB = 3.2              # v3.2: m over the foot of the cut from which the face beside a road has its full relief
                              # too (over RELIEF_RAMP m; a bus is 3.2 m high)
SUB_DZ = 1.5                  # v3.2: m, skin edges on the rock that climb more than this are halved (up to SUB_PASSES
SUB_PASSES = 2                # times): on a face of 70-80 degrees one lattice step of 0.75 m is 2-4 m of height, and the
SUB_RW = 0.2                  # relief (knobs of ROCK_KNOB m) had one point per step: big flat facets (group 3)
# v3.1: plants on the skin (michi's reference: shrubs, ivy-like bushes in the gullies of the rock) as forest items at
# the skin's surface (a groundcover on the terrain would stand on the ground lowered under the skin); vanilla bushes
# that ship their imposters (no bake in the session: white squares), no collision
PLANTS = {   # type: (shape, half width at scale 1 m, scales)
    "skin_fluffy_bush": ("/levels/italy/art/shapes/trees/trees_italy/fluffy_bush.dae", 1.665, (0.30, 0.65)),
    "skin_generibush": ("/levels/italy/art/shapes/trees/trees_italy/generibush.dae", 2.30, (0.25, 0.55)),
}
PLANT_P_EARTH = 0.030         # per lattice point (0.56 m2): earth banks gentler than PLANT_DEG
PLANT_P_LEDGE = 0.050         # rock ledges (gentler than MOSS_DEG)
PLANT_P_GULLY = 0.025         # in the gullies of the rock (hanging bushes)
PLANT_DEG = 50.0
PLANT_FOOT = 1.0              # m: none lower than this over the foot of the cut within PLANT_ROAD m of a road
PLANT_ROAD = 2.0
PLANT_CLEAR = 0.3             # m between a plant's crown (half width x scale) and the road surface
PLANT_SINK = 0.08             # m into the skin
PLANT_MAX = 90000             # cap over the map


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


def rock_texture(n=ROCK_TEX_N, seed=53):
    """(colour, normal) uint8 images of a bare gneiss face, tileable: layers across the image (the texture's v is
    up the face), joints across them, broken blocks with lighter fresh breaks, dark lichen; its mean ROCK_TEX_MEAN."""
    from bld_textures import noise, aniso_noise, normal_map, to8
    rng = np.random.default_rng(seed)
    mm = ROCK_TILE_M * 1000 / n
    fine, mid = noise(n, n, 1.0, rng), noise(n, n, 6, rng)
    layers = aniso_noise(n, n, 6.0, 24.0, rng)                    # rows: up the face; long along it (v3.2: 3 x 60 px,
                                                                  # fine hairlines across the face that read as a stretched texture)
    warp = aniso_noise(n, n, 20.0, 40.0, rng)
    rows = (np.arange(n)[:, None] + 9.0 * warp) % n
    band = np.sin(rows / n * 2 * np.pi * 9) * 0.5 + 0.5          # nine layers per repeat
    # blocks: cells of a jittered grid, each a tilted plane (the facets of a blasted face)
    from scipy.spatial import cKDTree
    k = 80
    C = rng.random((k, 2)) * [n, n]
    tiles = np.concatenate([C + [dx * n, dy * n] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    Y, X = np.mgrid[0:n, 0:n]
    stretch = np.array([2.4, 1.0])                                  # wider along the layers than up the face
    wy, wx = noise(n, n, 12, rng), noise(n, n, 12, rng)          # jagged joints, not straight cell edges
    Yw, Xw = Y + 6.0 * wy + 1.5 * fine, X + 6.0 * wx + 1.5 * fine
    d, i = cKDTree(tiles * stretch).query(np.column_stack([Yw.ravel() % n, Xw.ravel() % n]) * stretch, k=2)
    cid = (i[:, 0] % k).reshape(n, n)
    edge = np.clip((d[:, 1] - d[:, 0]).reshape(n, n) / 9.0, 0, 1)   # 0 on a joint between two blocks
    edge = np.maximum(edge, np.clip(noise(n, n, 30, rng) - 0.9, 0, 1))  # joints that fade out (not a mosaic)
    tilt = rng.normal(0, 1, (k, 2))
    dy = (Yw - C[cid, 0] + n / 2) % n - n / 2                     # from the block's centre (wrapped)
    dx = (Xw - C[cid, 1] + n / 2) % n - n / 2
    plane = (tilt[cid, 0] * dy + tilt[cid, 1] * dx) / n * 8
    plane = (plane - plane.mean()) / max(plane.std(), 1e-6)
    hgt = 6.0 * plane + 5.0 * edge + 2.0 * mid + 0.8 * fine + 1.2 * band
    tone = rng.uniform(-0.06, 0.06, k)[cid]
    base = np.array([0.55, 0.53, 0.50], np.float32)
    col = base * (1 + tone[..., None] + 0.05 * fine[..., None] + 0.06 * mid[..., None] + 0.04 * (band[..., None] - 0.5))
    # mica sparkle and darker biotite layers
    col = col * (1 - 0.06 * np.clip(layers, 0, None)[..., None])
    # joints dark
    col = col * (0.62 + 0.38 * edge[..., None] ** 0.6) * (1 + 0.07 * plane[..., None])
    # fresh breaks lighter and warmer (rusty) on a few blocks
    fresh = (rng.random(k) < 0.12)[cid] & (edge > 0.3)
    col = np.where(fresh[..., None], col * [1.07, 1.03, 0.97], col)
    # lichen: dark grey-green patches
    lich = np.clip((noise(n, n, 4, rng) - 1.6) * 1.5, 0, 1) * edge
    col = col * (1 - 0.5 * lich[..., None]) + 0.5 * lich[..., None] * np.array([0.34, 0.34, 0.31], np.float32)
    # dark streaks of water down the face (the texture's rows run down it)
    wet = np.clip(aniso_noise(n, n, 60.0, 16.0, rng) - 1.0, 0, 1)
    col = col * (1 - 0.12 * wet[..., None])          # v3.2: 0.25, a grid of dark bars over the tiles
    col = np.clip(col * (ROCK_TEX_MEAN / 255.0 / col.reshape(-1, 3).mean()), 0, 1)
    return to8(col), normal_map(hgt, 1.2 / mm * 0.25)


def vnoise3(P, scale, seed=0):
    """Smooth value noise 0..1 of points P (k, 3) in m, its cells scale (sx, sy, sz) m."""
    Q = np.asarray(P, np.float64) / np.asarray(scale, np.float64)
    i0 = np.floor(Q).astype(np.int64)
    f = Q - i0
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        v = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        v = (v ^ (v >> 13)) * 1274126177
        return ((v ^ (v >> 16)) & 0xFFFF) / 65535.0
    out = 0.0
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                w = (f[:, 0] if a else 1 - f[:, 0]) * (f[:, 1] if b else 1 - f[:, 1]) * (f[:, 2] if c else 1 - f[:, 2])
                out = out + w * h(i0[:, 0] + a, i0[:, 1] + b, i0[:, 2] + c)
    return out


def relief(P, rw, hab, wv=None, droad=None):
    """(m out of the face along its normal, rib noise) of points P of a rock face: ribs and gullies down the face,
    knobs on them; only out of the face, none at its foot or edge. rw the rock weight, hab m over the foot of the
    cut, wv the cut values, droad m from the road."""
    ribs = vnoise3(P, (ROCK_RIB, ROCK_RIB, ROCK_RIB_V), 2)
    knobs = vnoise3(P, (ROCK_KNOB,) * 3, 3)
    d = RELIEF * np.clip(0.75 * ribs + 0.45 * knobs - 0.15, 0, 1)
    d *= np.clip((rw - 0.3) / 0.5, 0, 1) * np.clip((hab - TOE_CLEAR) / TOE_RAMP, 0, 1)
    if droad is not None:                               # little relief beside a road: nothing over the lane
        # v3.2: only up to RELIEF_HAB m over the foot (the height of a vehicle): above it the face beside the road
        # has its ribs too (a cut right at the road edge was one smooth plane up to the top)
        far = np.maximum(np.clip((droad - RELIEF_ROAD) / RELIEF_RAMP, 0, 1),
                         np.clip((hab - RELIEF_HAB) / RELIEF_RAMP, 0, 1))
        d = np.minimum(d, RELIEF_NEAR + (RELIEF - RELIEF_NEAR) * far)
    if wv is not None:
        d *= np.clip((wv - EDGE_ISO) / EDGE_FADE - 0.5, 0, 1)
    return d, ribs


def rock(keys, P, N, z, wv, droad=None):
    """v3.1: rock on the steep faces. (P moved out along N by the relief, N of the moved faces, rock weight 0..1,
    colour (k, 3)) of the lattice points; z their heights (the foot of the cut from them), wv the cut values."""
    deg = np.degrees(np.arccos(np.clip(N[:, 2], -1, 1)))
    jit = (vnoise3(P, (ROCK_JITTER_M,) * 3, 1) - 0.5) * 2 * ROCK_JITTER
    rw = np.clip((deg + jit - ROCK_DEG) / ROCK_BLEND + 0.5, 0, 1)
    k0 = keys.min(0)
    kk = keys - k0
    G = np.full(kk.max(0) + 1, np.inf)
    G[kk[:, 0], kk[:, 1]] = z
    toe = ndi.minimum_filter(G, size=TOE_WIN, mode="nearest")[kk[:, 0], kk[:, 1]]
    hab = z - toe
    d, ribs = relief(P, rw, hab, wv, droad)
    Pm = P + N * d[:, None]
    # colours: rock grey-brown with big soft patches, moss on the ledges; earth less green; scree at the foot
    big = vnoise3(P, (COLOUR_SCALE,) * 3, 4)
    rc = np.array(ROCK_TONE) * (0.88 + 0.24 * big)[:, None]
    moss = np.clip((MOSS_DEG - deg) / 6.0, 0, 1) * np.clip((vnoise3(P, (3.0,) * 3, 5) - 0.45) * 3, 0, 1)
    rc = rc * (1 - moss[:, None]) + np.array(MOSS) * moss[:, None]
    return Pm, rw, rc, hab, deg, ribs


def subdivide(P, Pm, N, col, rw, hab, wv, droad, T):
    """v3.2: the triangles T halved along their edges on the rock (rock weight over SUB_RW at an end) that climb more
    than SUB_DZ m, SUB_PASSES times (an edge is halved in both its triangles: no cracks). P the lattice points, Pm
    the same moved out by their relief; the new points take the mean of the two ends (on the face before the
    relief), and their own relief. (moved points, normals, colours, rock weights, cut values, triangles)."""
    A = {"P": P, "N": N, "col": col, "rw": rw, "hab": hab}
    if wv is not None:
        A["wv"] = wv
    if droad is not None:
        A["droad"] = droad
    Pm = Pm.copy()
    for _ in range(SUB_PASSES):
        E = np.sort(T[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
        Q = A["P"]
        cut = (np.abs(Q[E[:, 0], 2] - Q[E[:, 1], 2]) > SUB_DZ) & (np.maximum(A["rw"][E[:, 0]], A["rw"][E[:, 1]]) > SUB_RW)
        if not cut.any():
            break
        ue, inv = np.unique(E[cut], axis=0, return_inverse=True)
        m0 = len(Q)
        mid = np.full(len(E), -1, np.int64)
        mid[np.flatnonzero(cut)] = m0 + inv.ravel()
        mid = mid.reshape(-1, 3)                        # per triangle: the new point on its edge (v0 v1, v1 v2, v2 v0)
        for k, v in list(A.items()):
            A[k] = np.concatenate([v, 0.5 * (v[ue[:, 0]] + v[ue[:, 1]])])
        nn = A["N"][m0:]
        A["N"][m0:] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        d, _ = relief(A["P"][m0:], A["rw"][m0:], A["hab"][m0:], A["wv"][m0:] if "wv" in A else None,
                      A["droad"][m0:] if "droad" in A else None)
        Pm = np.concatenate([Pm, A["P"][m0:] + A["N"][m0:] * d[:, None]])
        cnt = (mid >= 0).sum(1)
        out = [T[cnt == 0]]
        for r in range(3):                              # rotate so that the cut edges come first
            Tr, Mr = np.roll(T, -r, axis=1), np.roll(mid, -r, axis=1)
            a, b, c = Tr[:, 0], Tr[:, 1], Tr[:, 2]
            m_ab, m_bc, m_ca = Mr[:, 0], Mr[:, 1], Mr[:, 2]
            one = (cnt == 1) & (m_ab >= 0)
            out += [np.column_stack([a, m_ab, c])[one], np.column_stack([m_ab, b, c])[one]]
            two = (cnt == 2) & (m_ab < 0)               # a b kept, b c and c a halved
            out += [np.column_stack([a, b, m_bc])[two], np.column_stack([a, m_bc, m_ca])[two],
                    np.column_stack([m_ca, m_bc, c])[two]]
        three = cnt == 3
        a, b, c = T[:, 0], T[:, 1], T[:, 2]
        m_ab, m_bc, m_ca = mid[:, 0], mid[:, 1], mid[:, 2]
        out += [np.column_stack([a, m_ab, m_ca])[three], np.column_stack([m_ab, b, m_bc])[three],
                np.column_stack([m_ca, m_bc, c])[three], np.column_stack([m_ab, m_bc, m_ca])[three]]
        T = np.concatenate(out)
    return Pm, A["N"], A["col"], A["rw"], A.get("wv"), T


def face_normals(P, T, N0):
    """Vertex normals of the triangles T (area weighted); N0 where a vertex has none."""
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    N = np.zeros_like(P)
    for j in range(3):
        np.add.at(N, T[:, j], fn)
    L = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(L > 1e-9, N / np.maximum(L, 1e-9), N0)


def materials():
    t = f"/levels/{LEVEL_NAME}/{D}"
    m = bng.material(MAT, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                     roughness=0.95, ground_type="DIRT", vert_color=True)
    far = bng.material(MAT_FAR, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                       roughness=0.95, ground_type="DIRT", vert_color=True, extra={"castShadows": False})
    rk = bng.material(MAT_ROCK, f"{t}/t_steep_rock_b.color.png", normal_map=f"{t}/t_steep_rock_nm.normal.png",
                      roughness=0.9, ground_type="ROCK", vert_color=True)
    return [m, far, rk]


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


def skin_mask(H, road, solid, sq, hard=None):
    """(skin vertices, steep vertices, seeds) of a block of terrain heights H: steep near a road, grown by DILATE,
    never on solid. v3.2: with hard (the walls, buildings, railway and lake of the block) the steep vertices in the
    ring of solid beside a road seed the skin too (seeds: skin themselves, and foot() runs on from them): a cut of
    5-7 m in one or two squares right beside the road had no steep vertex outside that ring, never took a skin and
    stayed bare terrain, its material projected from above in vertical streaks (visual review of v3.1, group 3)."""
    gy, gx = np.gradient(H, sq)
    steep = np.degrees(np.arctan(np.hypot(gx, gy))) > STEEP
    near = ndi.distance_transform_edt(~road) * sq <= REACH if road.any() else np.zeros_like(steep)
    S = steep & near & ~solid
    if hard is not None:
        S |= (np.degrees(np.arctan(np.hypot(gx, gy))) > STEEP_ROAD) & near & solid & ~(hard | road)
    lab, k = ndi.label(S, np.ones((3, 3)))
    if k:
        size = np.bincount(lab.ravel())
        S = (size >= MIN_VERTS)[lab] & S
    seeds = S
    S = ndi.binary_dilation(S, np.ones((3, 3)), iterations=DILATE) & ~solid
    return S, steep, seeds


def foot(S, road, hard):
    """v3.1: the vertices of the road FOOT squares from the skin S (not hard): the skin stopped a square short of
    the road, and the face of a cut right beside it (5-7 m in one square, the terrain drawn from above) stayed
    bare, smeared in vertical streaks. Now the skin runs down to the road and under its edge."""
    near = ndi.binary_dilation(S, np.ones((3, 3)), iterations=FOOT + 1)
    roadish = ndi.binary_dilation(road, np.ones((3, 3)), iterations=1)
    return near & roadish & ~hard & ~S


def tile_skin(H, S, sq, core, sol):
    """Skin of a block: (new terrain heights, changed vertices, squares (r, c) of the core window). The terrain
    under it lowered under the inner squares and smoothed (not on sol)."""
    dch = ndi.distance_transform_cdt(S, metric="chessboard").astype(np.float64)
    Hn = H - LOWER * np.clip((dch - 1) / 2, 0, 1)
    w = np.clip(dch / 2.0, 0, 1) * ~sol                 # its edge vertices half way: the ground beyond as it was
    Hn = Hn + w * (ndi.gaussian_filter(H, RING_BLUR) - H)
    Hn = np.where(sol, H, Hn)                           # v3.1: the skin reaches the road (foot): its ground stays
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


def tile_mesh(mb, keys, z, rr, cc, x0, y0, sq, colour, wv=None, lods=(), droad=None, RS=None):
    """Triangles of the skin squares into mb, one add per projection axis; lods: [(k, lift, MeshBuilder)] the
    far detail levels (coarse_mesh), filled from the same lattice. (triangle count, info): v3.1 the lattice points
    for the plants and the check of the skin over the road surfaces (RS)."""
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
    # v3.1: rock on the steep faces (moved out by its relief), the earth less green, scree at the foot
    Pm, rw, rc, hab, deg, ribs = rock(keys, P, N, z, wv, droad)
    earth = (1 - EARTH_MIX) * np.asarray(colour) + EARTH_MIX * np.array(EARTH)
    scree = np.clip(1 - hab / TOE_SCREE, 0, 1)[:, None] * 0.6
    earth = earth * (1 - scree) + np.array(SCREE) * scree
    colour = earth * (1 - rw[:, None]) + rc * rw[:, None]
    col = np.column_stack([colour, np.ones(len(z))])
    for k, lift, mbk in lods:
        coarse_mesh(mbk, keys, P, N, col, rr, cc, wv if wv is not None else np.ones(len(z)), k, lift)
    # v3.2: the edges on the rock that climb steeply halved, the relief also at the new points
    P, N, col, rws, wvs, T = subdivide(P, Pm, N, col, rw, hab, wv, droad, T)
    N = face_normals(P, T, N)
    col = np.column_stack([col, rws])                  # the rock weight carried through the cut as a fifth column
    if wvs is not None:
        P, N, col, T = clip(P, N, col, T, wvs - EDGE_ISO)
    # rock and earth cut apart along the line where the rock weight is 1/2 (not along the triangles: teeth)
    n_tri = len(T)
    info = {"P": Pm, "rw": rw, "deg": deg, "hab": hab, "ribs": ribs, "over_road": 0, "over_road_max": -9.0}
    for mat, sgn, tile in ((MAT, -1.0, TILE_M), (MAT_ROCK, 1.0, ROCK_TILE_M)):
        Pk, Nk, ck, Tk = clip(P, N, col, T, sgn * (col[:, 4] - 0.5) + 1e-6)
        if RS is not None and len(Tk):
            # v3.1: no point of the skin over a road surface (its foot is under it, ROAD_DIVE). The lattice is
            # clamped before the relief: a point moved by it, or cut in by clip(), can still stand on the road
            used = np.unique(Tk)
            hr = RS.height(Pk[used, 0], Pk[used, 1], "near", Pk[used, 2])
            dz = Pk[used, 2] - hr
            ok = np.isfinite(dz)
            if ok.any():
                info["over_road"] += int((dz[ok] > 0.0).sum())
                info["over_road_max"] = max(info["over_road_max"], float(dz[ok].max()))
                low = ok & (dz > -ROAD_DIVE) & (dz < ROAD_LIFT_MAX)    # not a road far under it (tunnel, gallery)
                Pk[used[low], 2] = hr[low] - ROAD_DIVE
        add_projected(mb, mat, Pk, Nk, ck[:, :4], Tk, tile)
    return n_tri, info


def plants(info, wv, hr, droad, rng):
    """v3.1: forest items on the skin: [(type, x, y, z, yaw, scale)] of the lattice points (info of tile_mesh)."""
    P, rw, deg, hab, ribs = info["P"], info["rw"], info["deg"], info["hab"], info["ribs"]
    inside = (wv > EDGE_ISO + 0.5 * EDGE_FADE) & ~np.isfinite(hr)
    inside &= ~((droad < PLANT_ROAD) & (hab < PLANT_FOOT))
    earth = (rw < 0.5) & (deg < PLANT_DEG)
    ledge = (rw >= 0.5) & (deg < MOSS_DEG)
    gully = (rw >= 0.5) & ~ledge & (ribs < 0.35)
    p = np.where(earth, PLANT_P_EARTH, 0.0) + np.where(ledge, PLANT_P_LEDGE, 0.0) + np.where(gully, PLANT_P_GULLY, 0.0)
    pick = inside & (rng.random(len(P)) < p)
    out = []
    names = list(PLANTS)
    for i in np.flatnonzero(pick):
        t = names[0] if (earth[i] and rng.random() < 0.6) else names[1]
        _, hw, (s0, s1) = PLANTS[t]
        sc = float(rng.uniform(s0, s1))
        if droad[i] < hw * sc + PLANT_CLEAR:                # its crown would reach over the road
            continue
        out.append((t, float(P[i, 0]), float(P[i, 1]), float(P[i, 2]) - PLANT_SINK, float(rng.uniform(0, 2 * np.pi)), sc))
    return out


def add_projected(mb, mat, P, N, col, T, tile_m=TILE_M):
    """The triangles T into mb, one add per projection axis (each face takes the axis it is turned to)."""
    if not len(T):
        return
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    axis = np.argmax(np.abs(fn), axis=1)                 # 0: x (u = y, v = z), 1: y (u = x, v = z), 2: z (u = x, v = y)
    for ax, (ui, vi) in enumerate(((1, 2), (0, 2), (0, 1))):
        Ta = T[axis == ax]
        if not len(Ta):
            continue
        used, inv = np.unique(Ta.ravel(), return_inverse=True)
        uv = np.column_stack([P[used, ui], P[used, vi]]) / tile_m
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
    hard = ndi.binary_dilation(footprints(zi, lv, n, X0, Y0, sq, HARD), iterations=1)
    solid = ndi.binary_dilation(hard | road, iterations=1)
    # v3.1: the road surfaces, to take the skin under them where it runs down to a road (foot)
    import network_mesh, road_mesh
    _, rtop = network_mesh.top_faces(zi, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    RS = road_mesh.TriSurface(rtop)
    # the lake: no skin at or under its level (+0.3 m)
    lake = [o for f in zi.namelist() if f.endswith("items.level.json") and "/Water/" in f
            for o in read_items(zi, f) if o.get("class") == "WaterBlock"]
    lake_z = max((float(o["position"][2]) for o in lake), default=-1e9)
    colours = BaseColours(zi, lv, names, n)
    q_new = q.copy()
    files, objs = {}, []
    trees = []
    rep = {"tiles": 0, "squares": 0, "triangles": 0, "steep_vertices": 0, "changed_vertices": 0,
           "changed_max_m": 0.0}
    m = int(np.ceil(REACH / sq)) + DILATE + 4
    for tr in range(0, n - 1, TILE):
        for tc in range(0, n - 1, TILE):
            a0, a1 = max(tr - m, 0), min(tr + TILE + m + 1, n)
            b0, b1 = max(tc - m, 0), min(tc + TILE + m + 1, n)
            H = Z0 + q[a0:a1, b0:b1].astype(np.float64) / 65535.0 * MAXH
            sol = solid[a0:a1, b0:b1] | (H < lake_z + 0.3)
            hl = hard[a0:a1, b0:b1] | (H < lake_z + 0.3)
            S, steep, seeds = skin_mask(H, road[a0:a1, b0:b1], sol, sq, hl)
            if (S | seeds).any():
                S = S | seeds | foot(S | seeds, road[a0:a1, b0:b1], hl)
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
            # v3.1: under a road surface the skin is under it (its foot): hidden by the road, never over it
            hr = RS.height(X0 + (b0 + C) * sq, Y0 + (a0 + R) * sq, "low")
            z = np.where(np.isfinite(hr), np.minimum(z, hr - ROAD_DIVE), z)
            # v3.1: m from the nearest road vertex (less half a square: about the edge of its surface); beside a road
            # the skin no higher than the terrain (EPS): no lip at the road edge
            dv = ndi.distance_transform_edt(~road[a0:a1, b0:b1]) * sq
            droad = np.maximum(ndi.map_coordinates(dv, [R, C], order=1) - sq / 2, 0.0)
            clamp = (droad <= ROAD_CLAMP) & ~np.isfinite(hr)
            rep["lip_clamped_points"] = rep.get("lip_clamped_points", 0) + int((clamp & (z > fl + 1e-6)).sum())
            # v3.2: only the foot of the face (the lip is at its low side): higher up the face beside the road keeps the
            # round surface, not the plane of one terrain square (a 5-7 m cut at the road edge was one flat facet)
            kk = keys - keys.min(0)
            G = np.full(kk.max(0) + 1, np.inf)
            G[kk[:, 0], kk[:, 1]] = fl
            up = fl - ndi.minimum_filter(G, size=TOE_WIN, mode="nearest")[kk[:, 0], kk[:, 1]]
            z = np.where(clamp, fl + np.clip((up - CLAMP_HAB) / CLAMP_RAMP, 0, 1) * np.maximum(z - fl, 0), z)
            gr, gc = np.mgrid[0:a1 - a0, 0:b1 - b0]
            cg = colours(lay[a0:a1, b0:b1].ravel(), (gr + a0).ravel(), (gc + b0).ravel()).reshape(a1 - a0, b1 - b0, 3)
            col = np.column_stack([ndi.map_coordinates(ndi.gaussian_filter(cg[..., k], COLOUR_BLUR), [R, C], order=1)
                                   for k in range(3)])
            mb = bng.MeshBuilder()
            far = [(1, LOD_LIFT[1], bng.MeshBuilder()), (2, LOD_LIFT[2], bng.MeshBuilder())]
            ox, oy = X0 + b0 * sq, Y0 + a0 * sq
            ntri, info = tile_mesh(mb, keys, z, rr, cc, ox, oy, sq, col, wv, far, droad, RS)
            rep["skin_points_over_road"] = rep.get("skin_points_over_road", 0) + info["over_road"]
            rep["skin_over_road_max_m"] = round(max(rep.get("skin_over_road_max_m", -9.0), info["over_road_max"]), 3)
            if ntri:
                trees += plants(info, wv, hr, droad, np.random.default_rng(tr * 100003 + tc))
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
                for k, (_, mk) in enumerate(lods):
                    rep[f"triangles_lod{k + 1}"] = rep.get(f"triangles_lod{k + 1}", 0) + mk.triangle_count()
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
    # v3.1: the plants, capped, as forest items of their own types (a new run replaces them)
    if len(trees) > PLANT_MAX:
        keep = np.random.default_rng(7).choice(len(trees), PLANT_MAX, replace=False)
        trees = [trees[i] for i in sorted(keep)]
    rep["plants"] = {t: sum(1 for p in trees if p[0] == t) for t in PLANTS}
    if trees:
        for t in PLANTS:
            files[f"{lv}/forest/{t}.forest4.json"] = "".join(
                json.dumps({"ctxid": 1, "pos": [round(x, 3), round(y, 3), round(z, 3)],
                            "rotationMatrix": bng.rot_local_x_to(yaw), "scale": round(sc, 4), "type": t},
                           separators=(",", ":")) + "\n" for (tt, x, y, z, yaw, sc) in trees if tt == t).encode("utf-8")
        mdn = f"{lv}/art/forest/managedItemData.json"
        managed = json.loads(zi.read(mdn)) if mdn in zi.NameToInfo else {}
        for t, (shape, _, _) in PLANTS.items():
            managed[t] = {"name": t, "internalName": t, "class": "TSForestItemData", "persistentId": bng.pid(),
                          "radius": 0.5, "shapeFile": shape}
        files[mdn] = json.dumps(managed, indent=1).encode("utf-8")
    print("steep skin: %s" % rep, flush=True)
    if objs:
        col_img, nrm_img = bank_texture()
        rock_col, rock_nrm = rock_texture()
        for name, im in (("t_steep_bank_b.color.png", col_img), ("t_steep_bank_nm.normal.png", nrm_img),
                         ("t_steep_rock_b.color.png", rock_col), ("t_steep_rock_nm.normal.png", rock_nrm)):
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
