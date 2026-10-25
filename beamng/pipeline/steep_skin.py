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
  at the foot of the face (RELIEF_HAB; the clamp is G1's foot_line); the rock texture without the fine streaks across it.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish steep_skin
"""
import io, json, os, re, tempfile, time, zipfile
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
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
TILE_M = 6.0                  # m of slope per repeat of the texture (v3.1.3; 3 m up to v3.1.2)
TEX_N = 2048                  # pixels of the texture (v3.1.3; 512)
TEX_MEAN = 180.0              # mean sRGB of the texture: the vertex colours bring it to the terrain's (v3.1.3; 205)
ROCK_TEX_MEAN = 180.0         # mean sRGB of the rock texture (v3.1.3: = TEX_MEAN; 150 up to v3.1.2: the rock was 27 %
                              # darker than the earth of the same vertex colour, a hard line where they met)
TEX_TINT = (1.04, 1.0, 0.95)   # v3.1.3: the earth texture's mean colour over TEX_MEAN (nearly neutral)
OLD_TEX_MEAN, OLD_ROCK_TEX_MEAN = 205.0, 150.0   # the means up to v3.1.2 (skin_blend_step brings a built level's colours over)
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
MAT_FRINGE = "mp_steep_fringe"  # v3.1.3: + _1 ... (FRINGE_BANDS): the earth's fringe over the rock (border)
FRINGE_BANDS = ((0.35, 0.8), (0.7, 0.6), (1.05, 0.42), (1.4, 0.26), (1.8, 0.12))   # (m from the line where earth
                              # and rock meet, up to; share of the rock the fringe covers there)
FRINGE_LIFT = 0.035           # m over the rock along its normals
MOSS_CALM = 0.4              # v3.1.3: share of the moss green left on the rock away from the earth (border)
AXIS_CELL = 1.5               # m, cells of the face normals the projection axis is taken from (smooth_axes) ...
AXIS_WIN = 3                  # ... averaged over this many cells
RW_BLUR = 1.5                 # half squares, blur of the rock weight (G1: no saw along the rock's lower edge)
ROCK_TILE_M = 6.0             # m of rock per repeat of its texture (v3.1.3; 4 m)
ROCK_TEX_N = 2048             # pixels of the rock texture (v3.1.3; 1024)
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
EARTH_MIX = 0.25              # v3.1.1: 0.45 up to v3.1 (with the brightness of EARTH: pale, grey-beige banks)
EARTH_LIFT = 0.08             # v3.1.1: luminance added to the terrain's for the earth of a bank (bare earth is a little
                              # lighter than the leaf litter, and the terrain's detail textures are lighter up close)
PAVED_LAYERS = ("Asphalt", "Concrete", "Gravel")   # v3.1.1: terrain layers of roads and yards, never the skin's colour
SCREE = (0.95, 0.93, 0.90)
ROADS = ("roads",)
SOLID = ("roads", "walls", "buildings", "railway")
HARD = ("walls", "buildings", "railway")   # v3.1: the skin never on these; it goes on down to a road (FOOT)
FOOT = 2                      # v3.1: terrain squares the skin goes on from a steep bank into the road beside it
ROAD_DIVE = 0.06              # m: ... there under the road surface (hidden by it), never over it
ROAD_LIFT_MAX = 1.0           # m: skin points up to this over a road surface go under it (more: a road below)
# (v3.1 ROAD_CLAMP, 1.5 m: within it of a road the skin no higher than the terrain, against a lip at the road edge
# where the smoothed lattice lifted the low side of a 5-7 m step, issue #15; replaced by FOOT_TAN below, G1)
# v3.1 visual check G1: within ROAD_CLAMP of a road the skin took the terrain's own facets (EPS over them), and where
# a road runs across the terrain grid its carve leaves the foot of a cut as a staircase of vertices (road level, then
# 2-3 m up one square further), which the higher split of the squares turns into a row of pyramids one square apart
# (green and brown "teeth" along the foot of the rock cuts, about 45 points of the check). Now the skin there keeps
# under a line drawn from the true edge of the road surface (FOOT_FINE m raster): FOOT_TAN m up per m out, up to
# FOOT_REACH m; and the terrain vertices under the skin that stand over it are lowered under it (FOOT_LOWER_MAX m
# at most, only inside the skin), never the road's, a wall's or a building's.
FOOT_TAN = 1.5
FOOT_REACH = 4.0
FOOT_FINE = 0.375             # m (a quarter of a terrain square)
FOOT_LOWER_MAX = 3.0
FOOT_DIVE = 0.5               # m inside the road edge over which the line goes on down (then flat under the road)
RELIEF_NEAR = 0.12            # m, the most relief within RELIEF_ROAD m (horizontal) of a road: a rib 55 cm out of a
RELIEF_ROAD = 2.0             # vertical cut at the road edge would overhang the lane at mirror height
RELIEF_RAMP = 1.5             # m beyond RELIEF_ROAD in which the relief grows to RELIEF
RELIEF_CLEAR = 0.6            # v3.2: beside a road the relief may also reach RELIEF_NEAR + this x the m to the road edge
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
# v3.1.1: the steep faces of the yards. The survey's 'altro_rivestimento_duro' (yards, forecourts, the ground of a
# farm) is meshed on the DTM, which smears every wall and terrace edge into a slope: 14 ha of the v3.1 yards were
# asphalt at 20-60 degrees, grey wedges under the walls and asphalt banks beside the roads (visual review of v3.1,
# 0030, 0160, 0161, 0399). A yard face steeper than YARD_DEG is
# ground: the earth of the skin's banks, with the colour of the terrain beside it (YARD_MAT; same mesh, same
# collision). The faces steeper than YARD_SKIRT are the skirts that take a surface's edge down into the ground.
YARD_MATS = ("mp_hard_asphalt", "mp_hard_sett", "mp_hard_cobble")
YARD_MAT = "mp_hard_bank"
YARD_DEG = 18.0             # 32 %: the steepest driveways of the area are about 25-30 %
YARD_SKIRT = 72.0
YARD_MIN_M2 = 6.0             # m2: smaller pieces of steep faces stay as they are (a speck of earth in a yard)
# v3.1.2: the banks of the meadows. The skin's earth (light earth with stones, roots and bright moss patches) was laid on
# every bank under ROCK_DEG, also on the grass slopes between the hairpins and beside the vineyards of the Magliaso-Pura
# road, where the terrain round it is meadow with the game's grass: pale yellow-green patches with sharp edges seen from
# the road and from above (michi, 2026-10-25). A grass texture of the skin's own in the meadow's colour still showed
# (michi: "non si deve vedere differenza"): no mesh looks like the terrain with its GroundCover grass. So the earth of the
# skin on meadow ground (MEADOW_LAYERS; the Bank layer of the steep vertices under it takes the layer of the nearest other
# vertex) goes, and the terrain there is the meadow again, Bank -> that meadow layer, with its grass. Rock stays (outcrops).
# Finishing step skin_grass, after steep_skin, on the skin meshes as they are (so it also runs on a built level).
MEADOW_LAYERS = ("Grass", "GardenGrass", "GrassVerge", "GardenGrassVerge")
NEAREST_OF = ("Bank",)        # layers that take the layer of the nearest other vertex (with PAVED_LAYERS)
GRASS_BLUR = 1.5              # terrain squares, blur of the meadow mask: the skin ends along a round line


# ------------------------------------------------------------------------------------------------ texture

def bank_texture(n=TEX_N, seed=47):
    """(colour, normal) uint8 images of the bank: bare earth, grains, gravel and stones, tileable, its mean TEX_MEAN
    (neutral: the vertex colours tint it). v3.1.3: 2048 px over 6 m (3 mm a pixel; v3.1: 512 px over 3 m) and no green
    moss patches nor root lines: bright blobs of a fixed shape every 3 m read as a pattern on every bank (michi's
    screenshot 2026-10-25); the colour of the place comes from the vertex colours only."""
    from bld_textures import noise, normal_map, to8
    from surface_textures import _domes
    rng = np.random.default_rng(seed)
    mm = TILE_M * 1000 / n
    fine, grain, mid, patch = noise(n, n, 0.7, rng), noise(n, n, 2.5, rng), noise(n, n, 14, rng), noise(n, n, 70, rng)
    hgt = 0.8 * fine + 1.5 * grain + 3.0 * mid + 3.0 * patch
    lum = 1 + 0.07 * fine + 0.07 * grain + 0.07 * mid + 0.05 * patch
    warm = np.clip(noise(n, n, 40, rng) * 0.5, -1, 1)           # drier (lighter, yellower) and damper (browner) earth
    col = np.array([0.50, 0.44, 0.36], np.float32) * lum[..., None]
    col = col * (1 + 0.03 * warm[..., None] * np.array([1.0, 0.6, -0.6], np.float32))
    # gravel 5-15 mm and stones 2-8 cm, grey gneiss and brown, sunk in the earth more where the patch noise is low
    for count, (r0, r1), embed, kk in ((14000, (3.0, 8.0), 0.40, 0.7), (900, (8, 22), 0.35, 0.9), (160, (25, 60), 0.35, 1.0)):
        h, sid = _domes(n, rng, count, (r0 / mm, r1 / mm), aspect=(1.0, 1.8), embed=embed)
        on = sid >= 0
        tone = np.array([[0.50, 0.48, 0.45], [0.40, 0.39, 0.37], [0.47, 0.41, 0.34], [0.34, 0.31, 0.27]],
                        np.float32)[rng.integers(0, 4, count)] * rng.uniform(0.9, 1.1, count)[:, None]
        sc = tone[np.maximum(sid, 0)] * (0.80 + 0.35 * h[..., None]) * (1 + 0.05 * fine[..., None])
        a = (on * np.clip(h * 4, 0, 1) * kk)[..., None]           # soft edges: earth on the stones' feet
        col = col * (1 - a) + sc * a
        hgt = np.where(on, hgt + 10.0 * kk * h, hgt)
    # dark crumbs and shadowed pores, a few dry grass stalks (small, pale, not green)
    dark = np.clip((noise(n, n, 1.2, rng) - 2.0) * 0.6, 0, 1)
    col = col * (1 - 0.35 * dark[..., None])
    hgt = hgt - 2.0 * dark
    for _ in range(260):
        p0 = rng.random(2) * n
        ang = rng.uniform(0, np.pi)
        ln = rng.uniform(4, 12) / mm
        t = np.linspace(0, 1, int(ln) + 1)
        P = (p0[None] + np.outer(t, [np.cos(ang), np.sin(ang)]) * ln).astype(int) % n
        col[P[:, 1], P[:, 0]] = col[P[:, 1], P[:, 0]] * 0.4 + 0.6 * np.array([0.62, 0.57, 0.42], np.float32)
        hgt[P[:, 1], P[:, 0]] += 1.5
    # its mean nearly grey (v3.1.3: 225 212 167 up to v3.1.2, which turned every bank ochre over the terrain's colour)
    col = np.clip(col * (np.array(TEX_TINT) * TEX_MEAN / 255.0 / col.reshape(-1, 3).mean(0)), 0, 1)
    return to8(col), normal_map(hgt, 1.0 / mm)


def fringe_alpha(n=TEX_N, seed=61):
    """v3.1.3: uint8 alpha of the earth fringe over the rock (FRINGE_BANDS): clumps of earth 5-40 cm with ragged
    edges, uniform in 0..255 (cut out at alphaRef r it covers 1 - r/255 of the face, and a lower r covers all a
    higher one does: the bands nest, no edge between them)."""
    from bld_textures import noise
    rng = np.random.default_rng(seed)
    f = 1.0 * noise(n, n, 40, rng) + 0.6 * noise(n, n, 12, rng) + 0.35 * noise(n, n, 3, rng) + 0.15 * noise(n, n, 1, rng)
    r = np.empty(f.size, np.float64)
    r[np.argsort(f.ravel(), kind="stable")] = np.arange(f.size)
    return np.clip(r / (f.size - 1) * 255 + 0.5, 0, 255).astype(np.uint8).reshape(n, n)


def rock_texture(n=ROCK_TEX_N, seed=53):
    """(colour, normal) uint8 images of a bare gneiss face, tileable: layers across the image (the texture's v is
    up the face), joints across them, broken blocks with lighter fresh breaks, dark lichen, earth in the joints; its
    mean ROCK_TEX_MEAN. v3.1.3: 2048 px over 6 m (3 mm a pixel; v3.1: 1024 over 4 m, washed out), crystals and
    sharper joints."""
    from bld_textures import noise, aniso_noise, normal_map, to8
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    mm = ROCK_TILE_M * 1000 / n
    s = n / 1024.0 * 4.0 / ROCK_TILE_M                            # v3.1's pixel scales at the new size
    fine, mid = noise(n, n, 1.0, rng), noise(n, n, 6 * s, rng)
    crystal = noise(n, n, 0.6, rng)
    layers = aniso_noise(n, n, 6.0 * s, 24.0 * s, rng)
    warp = aniso_noise(n, n, 20.0 * s, 40.0 * s, rng)
    rows = (np.arange(n)[:, None] + 9.0 * s * warp) % n
    band = np.sin(rows / n * 2 * np.pi * 9 * ROCK_TILE_M / 4.0) * 0.5 + 0.5   # a layer every 0.44 m
    from scipy.spatial import cKDTree
    k = int(80 * (ROCK_TILE_M / 4.0) ** 2)
    C = rng.random((k, 2)) * [n, n]
    tiles = np.concatenate([C + [dx * n, dy * n] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    Y, X = np.mgrid[0:n, 0:n]
    stretch = np.array([2.4, 1.0])
    wy, wx = noise(n, n, 12 * s, rng), noise(n, n, 12 * s, rng)
    jag = noise(n, n, 2.0 * s, rng)
    Yw, Xw = Y + 6.0 * s * wy + 1.5 * s * jag, X + 6.0 * s * wx + 1.5 * s * jag
    d, i = cKDTree(tiles * stretch).query(np.column_stack([Yw.ravel() % n, Xw.ravel() % n]) * stretch, k=2)
    cid = (i[:, 0] % k).reshape(n, n)
    edge = np.clip((d[:, 1] - d[:, 0]).reshape(n, n) / (11.0 * s), 0, 1)
    edge = np.maximum(edge, np.clip(noise(n, n, 30 * s, rng) - 0.9, 0, 1))
    tilt = rng.normal(0, 1, (k, 2))
    dy = (Yw - C[cid, 0] + n / 2) % n - n / 2
    dx = (Xw - C[cid, 1] + n / 2) % n - n / 2
    plane = (tilt[cid, 0] * dy + tilt[cid, 1] * dx) / n * 8
    plane = (plane - plane.mean()) / max(plane.std(), 1e-6)
    hgt = 6.0 * plane + 6.0 * edge ** 0.5 + 2.0 * mid + 1.2 * fine + 0.8 * crystal + 1.2 * band
    tone = rng.uniform(-0.07, 0.07, k)[cid]
    base = np.array([0.55, 0.53, 0.50], np.float32)
    col = base * (1 + tone[..., None] + 0.05 * fine[..., None] + 0.06 * mid[..., None] + 0.04 * (band[..., None] - 0.5))
    col = col * (1 - 0.06 * np.clip(layers, 0, None)[..., None])
    # quartz and feldspar light, biotite dark: the grain of the stone (what makes it read sharp from a car)
    col = col * (1 + 0.10 * np.clip(crystal - 0.8, 0, None)[..., None] - 0.12 * np.clip(-crystal - 1.2, 0, None)[..., None])
    col = col * (0.50 + 0.50 * edge[..., None] ** 0.6) * (1 + 0.13 * plane[..., None])
    # light from above baked in (the facets' tops lit, the undersides of the blocks in shade: relief from afar)
    hs = gaussian_filter(hgt, 2.0 * s, mode="wrap")
    up = (np.roll(hs, 1, 0) - np.roll(hs, -1, 0)) * 0.5 / (2 * mm)
    col = col * np.clip(1 + 0.9 * np.tanh(up)[..., None] * 0.25, 0.7, 1.3)
    # earth in the open joints (the bank's own colour: the fringe of earth over the rock meets it)
    soil = np.clip(1 - edge / 0.25, 0, 1) * np.clip(noise(n, n, 8 * s, rng) + 0.3, 0, 1)
    col = col * (1 - 0.6 * soil[..., None]) + 0.6 * soil[..., None] * np.array([0.45, 0.39, 0.31], np.float32)
    fresh = (rng.random(k) < 0.12)[cid] & (edge > 0.3)
    col = np.where(fresh[..., None], col * [1.07, 1.03, 0.97], col)
    lich = np.clip((noise(n, n, 4 * s, rng) - 1.6) * 1.5, 0, 1) * edge
    col = col * (1 - 0.5 * lich[..., None]) + 0.5 * lich[..., None] * np.array([0.34, 0.34, 0.31], np.float32)
    wet = np.clip(aniso_noise(n, n, 60.0 * s, 16.0 * s, rng) - 1.0, 0, 1)
    col = col * (1 - 0.12 * wet[..., None])
    col = np.clip(col * (ROCK_TEX_MEAN / 255.0 / col.reshape(-1, 3).mean()), 0, 1)
    return to8(col), normal_map(hgt, 1.2 / mm * 0.3)


def texture_files(lv):
    """{level path: PNG bytes} of the skin's textures (v3.1.3: and the fringe's, the bank's colour with fringe_alpha)."""
    col_img, nrm_img = bank_texture()
    rock_col, rock_nrm = rock_texture()
    out = {}
    for name, im in (("t_steep_bank_b.color.png", col_img), ("t_steep_bank_nm.normal.png", nrm_img),
                     ("t_steep_rock_b.color.png", rock_col), ("t_steep_rock_nm.normal.png", rock_nrm),
                     ("t_steep_fringe_b.color.png", np.dstack([col_img, fringe_alpha()]))):
        b = io.BytesIO()
        Image.fromarray(im).save(b, "PNG", optimize=True)
        out[f"{lv}/{D}/{name}"] = b.getvalue()
    return out


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
        # ... and as far out as a part of the clearance to the road edge (a rib a metre back from the edge stays over
        # the verge): the face of a cut in the square beside the road was one plane up to RELIEF_HAB
        d = np.minimum(d, np.maximum(RELIEF_NEAR + (RELIEF - RELIEF_NEAR) * far, RELIEF_NEAR + RELIEF_CLEAR * droad))
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
    # G1: the rock weight blurred over the lattice before the rock and the earth are cut apart at 1/2: the slope of
    # neighbouring points differs by a few degrees, and where it stays near ROCK_DEG the cut drew a saw of rock teeth
    M = np.zeros(kk.max(0) + 1)
    M[kk[:, 0], kk[:, 1]] = 1.0
    g = np.zeros_like(M)
    g[kk[:, 0], kk[:, 1]] = rw
    rw = (ndi.gaussian_filter(g, RW_BLUR) / np.maximum(ndi.gaussian_filter(M, RW_BLUR), 1e-9))[kk[:, 0], kk[:, 1]]
    G = np.full(kk.max(0) + 1, np.inf)
    G[kk[:, 0], kk[:, 1]] = z
    toe = ndi.minimum_filter(G, size=TOE_WIN, mode="nearest")[kk[:, 0], kk[:, 1]]
    hab = z - toe
    d, ribs = relief(P, rw, hab, wv, droad)
    Pm = P + N * d[:, None]
    # colours: rock grey-brown with big soft patches, moss on the ledges; earth less green; scree at the foot
    big = vnoise3(P, (COLOUR_SCALE,) * 3, 4)
    rc = np.array(ROCK_TONE) * (0.88 + 0.24 * big)[:, None] * (OLD_ROCK_TEX_MEAN / ROCK_TEX_MEAN)   # v3.1.3: as bright as before
    moss = np.clip((MOSS_DEG - deg) / 6.0, 0, 1) * np.clip((vnoise3(P, (3.0,) * 3, 5) - 0.45) * 3, 0, 1)
    rc = rc * (1 - moss[:, None]) + np.array(MOSS) * (OLD_ROCK_TEX_MEAN / ROCK_TEX_MEAN) * moss[:, None]
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


def earth_colour(colour):
    """The skin's earth: the terrain colour (k, 3) pulled towards the hue of EARTH by EARTH_MIX, at the terrain's own
    brightness (plus EARTH_LIFT). v3.1.1: up to v3.1 it was pulled towards EARTH itself (a light colour): every bank was about twice as
    bright as the forest floor or meadow round it, a pale patch with a sharp edge (visual review 0192, 0509, 0519)."""
    colour = np.asarray(colour, np.float64)
    lum = lambda c: c @ np.array([0.2126, 0.7152, 0.0722])
    e = np.array(EARTH)[None] * (lum(colour) / lum(np.array(EARTH)))[:, None]
    lc = np.maximum(lum(colour), 1e-3)
    return np.clip(((1 - EARTH_MIX) * colour + EARTH_MIX * e) * ((lc + EARTH_LIFT) / lc)[:, None], 0, 1)


def face_normals(P, T, N0):
    """Vertex normals of the triangles T (area weighted); N0 where a vertex has none."""
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    N = np.zeros_like(P)
    for j in range(3):
        np.add.at(N, T[:, j], fn)
    L = np.linalg.norm(N, axis=1, keepdims=True)
    return np.where(L > 1e-9, N / np.maximum(L, 1e-9), N0)


def yard_material():
    t = f"/levels/{LEVEL_NAME}/{D}"
    return bng.material(YARD_MAT, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                        roughness=0.95, ground_type="DIRT", vert_color=True)


def materials():
    t = f"/levels/{LEVEL_NAME}/{D}"
    m = bng.material(MAT, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                     roughness=0.95, ground_type="DIRT", vert_color=True)
    far = bng.material(MAT_FAR, f"{t}/t_steep_bank_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                       roughness=0.95, ground_type="DIRT", vert_color=True, extra={"castShadows": False})
    rk = bng.material(MAT_ROCK, f"{t}/t_steep_rock_b.color.png", normal_map=f"{t}/t_steep_rock_nm.normal.png",
                      roughness=0.9, ground_type="ROCK", vert_color=True)
    fr = [bng.material(f"{MAT_FRINGE}_{j + 1}", f"{t}/t_steep_fringe_b.color.png", normal_map=f"{t}/t_steep_bank_nm.normal.png",
                       roughness=0.95, ground_type="ROCK", vert_color=True, alpha_test=int(round(255 * (1 - cover))),
                       extra={"castShadows": False})
          for j, (_, cover) in enumerate(FRINGE_BANDS)]
    return [m, far, rk] + fr


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


def foot_line(RS, road, ox, oy, sq, keys, reach=FOOT_REACH):
    """v3.1 (G1): per lattice point (keys in half squares of the block whose vertex (0, 0) is at ox, oy): (the height
    the skin keeps under beside a road: the road surface at its nearest edge point + FOOT_TAN times the distance to
    it, nan farther than reach or with no road; the distance of the points on the road from its edge). The
    distances are measured on a FOOT_FINE raster of the road surface (RS), not on the terrain vertices the road
    footprint marks: those step across the road one square at a time and the line would step with them."""
    out, din = np.full(len(keys), np.nan), np.zeros(len(keys))
    if not road.any():
        return out, din
    f = int(round(sq / FOOT_FINE))
    edge = ndi.binary_dilation(road, np.ones((3, 3))) & ~ndi.binary_erosion(road, np.ones((3, 3)))
    near = ndi.distance_transform_edt(~road) * sq <= reach + sq
    rows, cols = road.shape
    R, C = np.mgrid[0:rows * f, 0:cols * f]
    vr, vc = R // f, C // f
    ask = edge[vr, vc] & near[vr, vc]
    fy, fx = (R + 0.5) / f - 0.5, (C + 0.5) / f - 0.5            # fine cell centres in terrain vertex units
    hf = np.full(R.shape, np.nan)
    hf[ask] = RS.height(ox + fx[ask] * sq, oy + fy[ask] * sq, "low")
    on = np.isfinite(hf) | (road[vr, vc] & ~edge[vr, vc])          # inside the footprint: road (its height unused)
    if not on.any():
        return out, din
    d, (ir, ic) = ndi.distance_transform_edt(~on, return_indices=True)
    kr = np.clip(np.rint((keys[:, 0] / 2.0 + 0.5) * f - 0.5).astype(np.int64), 0, rows * f - 1)
    kc = np.clip(np.rint((keys[:, 1] / 2.0 + 0.5) * f - 0.5).astype(np.int64), 0, cols * f - 1)
    dk = d[kr, kc] * FOOT_FINE
    hk = hf[ir[kr, kc], ic[kr, kc]]
    ok = (dk <= reach) & np.isfinite(hk)
    out[ok] = hk[ok] + FOOT_TAN * dk[ok]
    din = ndi.distance_transform_edt(on)[kr, kc] * FOOT_FINE
    return out, din


def lower_under(Hq, keys, z, wv, hr, free):
    """v3.1 (G1): the terrain vertices (free: those that may move) lowered until the higher split of every terrain
    square stays EPS under the skin (z at the lattice points keys, in half squares) where the skin is whole (wv) and
    not under a road (hr: there the road hides both). (new heights, the lattice z raised over what could not move)."""
    Hn = Hq.copy()
    whole = (wv >= EDGE_ISO + EDGE_FADE) & ~np.isfinite(hr)
    R, C = keys[:, 0] / 2.0, keys[:, 1] / 2.0
    r0 = np.clip(np.floor(R).astype(np.int64), 0, Hq.shape[0] - 2)
    c0 = np.clip(np.floor(C).astype(np.int64), 0, Hq.shape[1] - 2)
    corners = [(r0 + a, c0 + b) for a in (0, 1) for b in (0, 1)]
    on_vertex = (keys[:, 0] % 2 == 0) & (keys[:, 1] % 2 == 0)
    # a vertex may move only if every lattice point round it is whole skin (nothing of it seen beside the skin)
    span = int(keys[:, 1].max()) + 3
    have = set((keys[whole, 0] * span + keys[whole, 1]).tolist())
    vk = keys[on_vertex]
    sur = np.ones(len(vk), bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            sur &= np.array([int(k) in have for k in (vk[:, 0] + dr) * span + vk[:, 1] + dc], bool)
    mov = np.zeros_like(free)
    mov[vk[sur, 0] // 2, vk[sur, 1] // 2] = True
    mov &= free
    floor = Hq - FOOT_LOWER_MAX
    for _ in range(6):
        viol = split_max(Hn, R, C) + EPS - z
        bad = whole & (viol > 0.002)
        if not bad.any():
            break
        need = np.zeros_like(Hn)
        k = np.where(on_vertex, 1.0, 2.0)[bad] * viol[bad]          # one corner of a diagonal may be fixed
        for rr, cc in corners:
            np.maximum.at(need, (rr[bad], cc[bad]), k)
        Hn = np.where(mov, np.maximum(Hn - need, floor), Hn)
    zr = np.where(np.isfinite(hr), z, np.maximum(z, split_max(Hn, R, C) + EPS))   # nothing of the terrain over it
    return Hn, zr


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
    earth = earth_colour(colour)
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
    parts = {}
    for mat, sgn in ((MAT, -1.0), (MAT_ROCK, 1.0)):
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
        parts[mat] = [Pk, Nk, ck[:, :4], Tk]
    add_parts(mb, border(parts, RS))
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


def add_projected(mb, mat, P, N, col, T, tile_m=TILE_M, axis=None):
    """The triangles T into mb, one add per projection axis (each face takes the axis it is turned to, or axis:
    (k,) 0 x, 1 y, 2 z per triangle)."""
    if not len(T):
        return
    if axis is None:
        fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
        axis = np.argmax(np.abs(fn), axis=1)             # 0: x (u = y, v = z), 1: y (u = x, v = z), 2: z (u = x, v = y)
    for ax, (ui, vi) in enumerate(((1, 2), (0, 2), (0, 1))):
        Ta = T[axis == ax]
        if not len(Ta):
            continue
        used, inv = np.unique(Ta.ravel(), return_inverse=True)
        uv = np.column_stack([P[used, ui], P[used, vi]]) / tile_m
        mb.add(mat, P[used], uvs=uv, normals=N[used], tris=inv.reshape(-1, 3), colors=col[used])


def smooth_axes(P, T):
    """v3.1.3: the projection axis of every triangle (P, T: all the near triangles of a tile, earth, rock and fringe)
    from the face normals averaged over AXIS_CELL x AXIS_WIN m round it. Up to v3.1.2 each face took the axis it is
    turned to itself: on a rock face standing about 45 degrees to x and y its ribs and knobs flipped the axis from
    one triangle to the next, a patchwork of texture seams (michi's screenshot 2026-10-25, the renders of 0039)."""
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])      # area weighted
    c = P[T].mean(1)
    k = np.floor((c - c.min(0)) / AXIS_CELL).astype(np.int64)
    shape = tuple(k.max(0) + 1)
    out = np.empty((len(T), 3))
    for j in range(3):
        g = np.zeros(shape)
        np.add.at(g, (k[:, 0], k[:, 1], k[:, 2]), fn[:, j])
        out[:, j] = ndi.uniform_filter(g, AXIS_WIN, mode="constant")[k[:, 0], k[:, 1], k[:, 2]]
    return np.argmax(np.abs(out), axis=1)


def calm_moss(C, d):
    """v3.1.3: the moss green of the rock's vertex colours C (k, 4), in place, down to MOSS_CALM of it at d >= 1 m from
    the line where it meets the earth (at the line it is the earth's colour): one lattice step (0.75 m) sharp, the
    green smeared over the faces read as a blurred texture (michi's screenshot 2026-10-25)."""
    lum = (C[:, :3] @ np.array([0.2126, 0.7152, 0.0722]))[:, None]
    k = (np.clip((C[:, 1] - C[:, 0]) / 0.05, 0, 1) * np.clip(d / 1.0, 0, 1) * (1 - MOSS_CALM))[:, None]
    C[:, :3] = C[:, :3] * (1 - k) + lum * k


def border(parts, RS=None):
    """v3.1.3: where the earth meets the rock, a fringe of earth over the rock (FRINGE_BANDS: less of it further from
    the line, cut out by the clumps of fringe_alpha), FRINGE_LIFT m out along the normals, in the colour of the earth
    at the line: the hard line where one texture stopped and the other began (michi 2026-10-25) becomes a ragged
    passage of earth patches over rock. parts {material: [P, N, col (k, 4), T]} (world coordinates); adds the
    fringe materials. RS: no fringe point over a road surface (the skin's foot is under it)."""
    if MAT_ROCK not in parts:
        return parts
    Pr, Nr, Cr, Tr = parts[MAT_ROCK]
    if MAT not in parts or not len(parts[MAT][3]) or not len(Tr):
        calm_moss(Cr, np.full(len(Cr), np.inf))
        return parts
    Pe, Ne, Ce, Te = parts[MAT]
    # the line: rock corners at an earth corner (the two clips of tile_mesh cut the same edges at the same points)
    ue, ur = np.unique(Te), np.unique(Tr)
    de, ie = cKDTree(Pe[ue]).query(Pr[ur], distance_upper_bound=5e-3)
    on = np.isfinite(de)
    if not on.any():
        calm_moss(Cr, np.full(len(Cr), np.inf))
        return parts
    line, line_col = Pr[ur[on]], Ce[ue[ie[on]]]
    d, il = cKDTree(line).query(Pr, distance_upper_bound=FRINGE_BANDS[-1][0] + 1.0)
    far = ~np.isfinite(d)
    d[far], il[far] = 1e9, 0
    calm_moss(Cr, d)
    dt = d[Tr].mean(1)
    lo = 0.0
    for j, (hi, cover) in enumerate(FRINGE_BANDS):
        sel = (dt >= lo) & (dt < hi)
        lo = hi
        if not sel.any():
            continue
        T = Tr[sel]
        used, inv = np.unique(T.ravel(), return_inverse=True)
        P = Pr[used] + Nr[used] * FRINGE_LIFT
        C = line_col[il[used]].copy()
        C[:, 3] = 1.0
        T = inv.reshape(-1, 3)
        if RS is not None:
            hr = RS.height(P[:, 0], P[:, 1], "near", P[:, 2])
            bad = np.isfinite(hr) & (P[:, 2] > hr - ROAD_DIVE) & (P[:, 2] < hr + ROAD_LIFT_MAX)
            T = T[~bad[T].any(1)]
        if len(T):
            parts[f"{MAT_FRINGE}_{j + 1}"] = [P, Nr[used], C, T]
    return parts


def add_parts(mb, parts):
    """v3.1.3: the near triangles of a tile into mb, projected along the smoothed axes (smooth_axes) of all of them."""
    mats = [m for m in parts if len(parts[m][3])]
    if not mats:
        return
    off = np.cumsum([0] + [len(parts[m][0]) for m in mats])
    P = np.concatenate([parts[m][0] for m in mats])
    ax = smooth_axes(P, np.concatenate([parts[m][3] + o for m, o in zip(mats, off)]))
    k0 = 0
    for m in mats:
        Pm, Nm, Cm, Tm = parts[m]
        add_projected(mb, m, Pm, Nm, Cm, Tm, ROCK_TILE_M if m == MAT_ROCK else TILE_M, ax[k0:k0 + len(Tm)])
        k0 += len(Tm)


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
    of the vertex (BASE_FLIP: image row 0 at the north edge). v3.1.1: the map each layer of the .ter names in the
    level's terrain materials (baseColorBaseTex). Up to v3.1 the map was looked up as t_base_<layer>_b.png, which the
    twins added by understory and forest_mosaic (ForestFloorVerge, ForestFloorLight, ForestRock, BankWood...) do
    not have: their vertices took a flat 0.55 grey, and with EARTH_MIX the whole skin of a bank in the wood came out
    a pale grey-green sheet (visual review of v3.1: the hairpin at -3872,119 and every cut in the woods)."""

    def __init__(self, zi, lv, names, n):
        import terrain
        self.n, self.img = n, {}
        tex = {}
        mf = f"{lv}/art/terrains/main.materials.json"
        if mf in zi.NameToInfo:
            for m in json.loads(zi.read(mf)).values():
                if isinstance(m, dict) and m.get("class") == "TerrainMaterial" and m.get("baseColorBaseTex"):
                    tex[m["internalName"]] = m["baseColorBaseTex"].lstrip("/")
        for i, name in enumerate(names):
            src = terrain.VERGE_OF.get(name, name)
            for f in (tex.get(name), f"{lv}/art/terrains/t_base_{src.lower()}_b.png"):
                if f and f in zi.NameToInfo:
                    self.img[i] = np.asarray(Image.open(io.BytesIO(zi.read(f))).convert("RGB"), np.float32)
                    break
        self.missing = [nm for i, nm in enumerate(names) if i not in self.img]
        self.paved = np.isin(np.arange(256), [i for i, nm in enumerate(names) if nm in PAVED_LAYERS])
        self.nearest = np.isin(np.arange(256), [i for i, nm in enumerate(names) if nm in PAVED_LAYERS + NEAREST_OF])
        self.meadow_ids = np.isin(np.arange(256), [i for i, nm in enumerate(names) if nm in MEADOW_LAYERS])
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

    def ground(self, lay, r0, c0):
        """(h, w, 3) colours of the window lay (rows from r0, columns from c0) of the ground beside the roads: a
        vertex of a road or yard layer (PAVED_LAYERS: the light grey of the asphalt under the meshes) takes the
        colour of the nearest vertex of another layer (v3.1.1: the skin runs into the road and its colours are
        blurred over COLOUR_BLUR squares, so the asphalt layer greyed the foot of every bank)."""
        h, w = lay.shape
        gr, gc = np.mgrid[0:h, 0:w]
        cg = self(lay.ravel(), (gr + r0).ravel(), (gc + c0).ravel()).reshape(h, w, 3)
        pv = self.paved[lay]
        if pv.any() and not pv.all():
            _, (ir, ic) = ndi.distance_transform_edt(pv, return_indices=True)
            cg = cg[ir, ic]
        return cg


    def meadow(self, lay):
        """v3.1.2: ((h, w) layer, (h, w) 1.0 on meadow) of the window lay: the vertices of a road or yard layer and of the
        Bank layer (the steep vertices of any natural ground) take the layer of the nearest vertex of another."""
        src = self.nearest[lay]
        if src.any() and not src.all():
            _, (ir, ic) = ndi.distance_transform_edt(src, return_indices=True)
            lay = lay[ir, ic]
        return lay, self.meadow_ids[lay].astype(np.float64)


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
    if colours.missing:
        print("steep skin: no base colour map for the layers %s (flat grey)" % colours.missing, flush=True)
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
            sol_hard = hard[a0:a1, b0:b1]
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
            cut = np.isfinite(hr) & (z > hr)                # G1: the bank over the road here (a cut, not a fill)
            z = np.where(np.isfinite(hr), np.minimum(z, hr - ROAD_DIVE), z)
            # v3.1: m from the nearest road vertex (less half a square: about the edge of its surface); beside a road
            # the skin no higher than the terrain (EPS): no lip at the road edge
            dv = ndi.distance_transform_edt(~road[a0:a1, b0:b1]) * sq
            droad = np.maximum(ndi.map_coordinates(dv, [R, C], order=1) - sq / 2, 0.0)
            # v3.1 (G1): under a line from the true road edge, not the terrain's facets (ROAD_CLAMP: teeth), and the
            # terrain under the skin lowered under it
            ox, oy = X0 + b0 * sq, Y0 + a0 * sq
            F, din = foot_line(RS, road[a0:a1, b0:b1], ox, oy, sq, keys)
            clamp = np.isfinite(F) & ~np.isfinite(hr)
            rep["lip_clamped_points"] = rep.get("lip_clamped_points", 0) + int((clamp & (z > F + 1e-6)).sum())
            z = np.where(clamp, np.minimum(z, F), z)
            # ... and on the road under a cut the same line on down under it: the skin comes out of the asphalt along
            # its edge, not between the lattice points that happen to lie on the road (a saw edge along a diagonal
            # road). Not where the bank falls away from the road (a fill): the skin comes up to the edge from below
            # there, and going on down it left the ground at the road edge over it. Never under the terrain under the
            # road either: from there to the road edge the terrain stood over the skin
            dive = np.maximum(hr - FOOT_TAN * np.minimum(din, FOOT_DIVE), np.minimum(split_max(Hq, R, C) + EPS, hr - ROAD_DIVE))
            z = np.where(cut, np.minimum(z, dive), z)
            own = np.zeros_like(S)
            own[cr, ccs] = True
            # the road footprint holds the vertices nearest to the road's faces, up to half a square beyond its edge:
            # those outside the road surface (not under it) may go down too, under a cut they hold its foot
            rv = road[a0:a1, b0:b1] & own & S
            if rv.any():
                vr, vc = np.nonzero(rv)
                rv[vr, vc] = np.isfinite(RS.height(X0 + (b0 + vc) * sq, Y0 + (a0 + vr) * sq, "low"))
            free = own & S & ~sol_hard & ~rv & (H >= lake_z + 0.3)
            Hq2, z = lower_under(Hq, keys, z, wv, hr, free)
            moved = Hq2 < Hq - 1e-4
            rep["foot_lowered_vertices"] = rep.get("foot_lowered_vertices", 0) + int(moved[cr, ccs].sum())
            rep["foot_lowered_max_m"] = round(max(rep.get("foot_lowered_max_m", 0.0),
                                                  float((Hq - Hq2)[cr, ccs].max())), 3)
            Hn = np.where(moved, Hq2, Hn)
            low = low | moved
            lo = low[cr, ccs]
            qn = np.clip(np.rint((Hn[cr, ccs] - Z0) / MAXH * 65535.0), 0, 65535).astype(np.uint16)
            cg = colours.ground(lay[a0:a1, b0:b1], a0, b0)
            col = np.column_stack([ndi.map_coordinates(ndi.gaussian_filter(cg[..., k], COLOUR_BLUR), [R, C], order=1)
                                   for k in range(3)])
            mb = bng.MeshBuilder()
            far = [(1, LOD_LIFT[1], bng.MeshBuilder()), (2, LOD_LIFT[2], bng.MeshBuilder())]
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
        files.update(texture_files(lv))
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


def steep_faces(F):
    """bool (k,): the faces F (k, 3, 3) between YARD_DEG and YARD_SKIRT degrees, in pieces of YARD_MIN_M2 or more
    (pieces joined through corners within 1 cm)."""
    nn = np.cross(F[:, 1] - F[:, 0], F[:, 2] - F[:, 0])
    a = np.linalg.norm(nn, axis=1) / 2
    deg = np.degrees(np.arccos(np.clip(np.abs(nn[:, 2]) / np.maximum(2 * a, 1e-12), 0, 1)))
    st = (deg >= YARD_DEG) & (deg < YARD_SKIRT) & (a > 1e-6)
    if not st.any():
        return st
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    idx = np.flatnonzero(st)
    key = np.round(F[idx].reshape(-1, 3) * 100).astype(np.int64)
    _, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    k, nv = len(idx), int(vid.max()) + 1
    A = coo_matrix((np.ones(3 * k), (np.repeat(np.arange(k), 3), vid.ravel())), shape=(k, nv)).tocsr()
    nc, comp = connected_components(A @ A.T, directed=False)
    area = np.bincount(comp, weights=a[idx], minlength=nc)
    st[idx] = area[comp] >= YARD_MIN_M2
    return st


def steep_yards_step(root, report=None):
    """v3.1.1 (finish step after steep_skin, whose bank texture it uses): the yard faces steeper than YARD_DEG take
    YARD_MAT, coloured like the natural ground beside them."""
    import walls as pw
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    rep = {"shapes": 0, "faces": 0, "m2": 0.0}
    if f"{lv}/{D}/t_steep_bank_b.color.png" not in zi.NameToInfo:
        print("steep yards: no terrain skin texture (run steep_skin first)", flush=True)
        return rep
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    X0, Y0, sq = float(blk["position"][0]), float(blk["position"][1]), float(blk.get("squareSize", 1.0))
    n, _, lay, names = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    colours = BaseColours(zi, lv, names, n)
    files = {}
    for o in read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        if not any(f'material="{m}-mat"' in text for m in YARD_MATS) or f'material="{YARD_MAT}-mat"' in text:
            continue
        V, N, UV, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        mb = bng.MeshBuilder()
        moved = []
        for mat, idx in parts:
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            if mat in YARD_MATS:
                st = np.repeat(steep_faces(V[idx[:, 0]].reshape(-1, 3, 3)), 3)
                if st.any():
                    moved.append(idx[st])
                    idx = idx[~st]
                    col = col[~st] if col is not None else None
                    if not len(idx):
                        continue
            mb.add(mat, V[idx[:, 0]], uvs=UV[idx[:, 2]], normals=N[idx[:, 1]],
                   tris=np.arange(len(idx)).reshape(-1, 3), colors=col)
        if not moved:
            continue
        idx = np.concatenate(moved)
        P, Nm = V[idx[:, 0]], N[idx[:, 1]]
        W = P + pos
        # the colour of the natural ground nearest each corner, as the skin's earth (EARTH_MIX)
        cc = (W[:, 0] - X0) / sq
        rr = (W[:, 1] - Y0) / sq
        r0, r1 = max(int(rr.min()) - 12, 0), min(int(rr.max()) + 14, n)
        c0, c1 = max(int(cc.min()) - 12, 0), min(int(cc.max()) + 14, n)
        cg = colours.ground(lay[r0:r1, c0:c1], r0, c0)
        cg = np.stack([ndi.gaussian_filter(cg[..., k], COLOUR_BLUR) for k in range(3)], -1)
        ir = np.clip(np.rint(rr).astype(int) - r0, 0, r1 - r0 - 1)
        ic = np.clip(np.rint(cc).astype(int) - c0, 0, c1 - c0 - 1)
        earth = earth_colour(cg[ir, ic])
        col = np.column_stack([earth, np.ones(len(P))])
        add_projected(mb, YARD_MAT, P, Nm, col, np.arange(len(P)).reshape(-1, 3))
        F = P.reshape(-1, 3, 3)
        rep["shapes"] += 1
        rep["faces"] += len(F)
        rep["m2"] += float(np.linalg.norm(np.cross(F[:, 1] - F[:, 0], F[:, 2] - F[:, 0]), axis=1).sum() / 2)
        base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.dae")
            mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
            files[sn] = open(path, "rb").read()
    rep["m2"] = round(rep["m2"])
    print("steep yards: %s" % rep, flush=True)
    if files:
        mf = f"{lv}/art/shapes/roads/main.materials.json"
        mats = json.loads(zi.read(mf))
        mm = yard_material()
        mats[mm["name"]] = mm
        files[mf] = json.dumps(mats, indent=1).encode("utf-8")
        with zi.writer() as zo:
            for i in zi.infolist():
                nm = i.filename
                zo.writestr(i, files.pop(nm) if nm in files else zi.read(i), compress_type=i.compress_type)
    rep["seconds"] = round(time.time() - t0)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


# ------------------------------------------------------------------------------------------------ meadow banks

_ARR = r'<float_array id="%s" count="(\d+)">([^<]*)</float_array>'
_TRI = re.compile(r'<triangles material="([^"]+)-mat" count="(\d+)">((?:<input[^>]*/>)+)<p>([^<]*)</p></triangles>')


def _fmt(a, d):
    return re.sub(r"\.?0+(?= |$)", "", " ".join(f"{v:.{d}f}" for v in np.asarray(a).ravel()))


def meadow_cut(txt, origin, colours, lay, Hter, X0, Y0, sq):
    """v3.1.2: one skin DAE (txt, at origin) without its earth triangles on meadow ground, in every detail level.
    (new text, or None when nothing changed, or "" when nothing is left; (k, 2) terrain vertices (row, col) under the
    removed near triangles; counts). The kept earth's corners on the cut go down onto the terrain (no lip)."""
    rep = {"removed_triangles": 0, "kept_triangles": 0}
    out, removed = txt, np.zeros((0, 2), np.int64)
    origin = np.asarray(origin, np.float64)
    n = lay.shape[0]
    for gid, mat in (("g", MAT), ("g1", MAT_FAR), ("g2", MAT_FAR)):
        mp = re.search(_ARR % f"{gid}-pa", out)
        g0 = out.find(f'<geometry id="{gid}"')
        if not mp or g0 < 0:
            continue
        g1 = out.find("</geometry>", g0)
        geom = out[g0:g1]
        lists = {m.group(1): m for m in _TRI.finditer(geom)}
        if mat not in lists:
            continue
        V = np.array(mp.group(2).split(), np.float64).reshape(-1, 3) + origin[None]
        m = lists[mat]
        nin = m.group(3).count("<input")
        I = np.array(m.group(4).split(), np.int64).reshape(-1, nin)[:, 0].reshape(-1, 3)
        R_, C_ = (V[:, 1] - Y0) / sq, (V[:, 0] - X0) / sq
        pad = int(4 * GRASS_BLUR) + 2
        r0, r1 = max(int(R_.min()) - pad, 0), min(int(R_.max()) + pad + 2, n)
        c0, c1 = max(int(C_.min()) - pad, 0), min(int(C_.max()) + pad + 2, n)
        _, mw = colours.meadow(lay[r0:r1, c0:c1])
        gw = ndi.map_coordinates(ndi.gaussian_filter(mw, GRASS_BLUR), [R_ - r0, C_ - c0], order=1)
        cut = gw[I].mean(1) >= 0.5
        if gid == "g":
            rep["removed_triangles"] += int(cut.sum())
            rep["kept_triangles"] += int((~cut).sum()) + sum(int(o.group(2)) for k, o in lists.items() if k != mat)
        if not cut.any():
            continue
        if gid == "g":
            vr = np.unique(I[cut].ravel())
            removed = np.column_stack([np.rint(R_[vr]), np.rint(C_[vr])]).astype(np.int64)
            # the corners the kept triangles share with the removed ones: down onto the terrain (EPS over its higher split)
            keep_v = np.zeros(len(V), bool)
            keep_v[I[~cut].ravel()] = True
            for k, o in lists.items():
                if k != mat:
                    keep_v[np.array(o.group(4).split(), np.int64).reshape(-1, o.group(3).count("<input"))[:, 0]] = True
            edge = np.zeros(len(V), bool)
            edge[I[cut].ravel()] = True
            edge &= keep_v
            if edge.any():
                Vl = V - origin[None]
                zt = split_max(Hter[r0:r1, c0:c1], R_[edge] - r0, C_[edge] - c0) + EPS
                Vl[edge, 2] = np.minimum(Vl[edge, 2], zt - origin[2])
                geom = geom.replace(mp.group(0), f'<float_array id="{gid}-pa" count="{Vl.size}">{_fmt(Vl, 3)}</float_array>')
        idx = np.repeat(I[~cut].ravel()[:, None], nin, 1).ravel()
        new = (f'<triangles material="{mat}-mat" count="{int((~cut).sum())}">{m.group(3)}'
               f'<p>{" ".join(map(str, idx))}</p></triangles>') if (~cut).any() else ""
        k0 = geom.find(m.group(0))
        geom = geom[:k0] + new + geom[k0 + len(m.group(0)):]
        out = out[:g0] + geom + out[g1:]
        if not (~cut).any():                           # no earth left in this level: its binding goes too
            k = out.find(f'<instance_geometry url="#{gid}"')
            e = out.find("</instance_geometry>", k)
            ob = re.search(r'<instance_material symbol="%s-mat".*?</instance_material>' % mat, out[k:e])
            if ob:
                out = out[:k + ob.start()] + out[k + ob.end():]
    if out == txt:
        return None, removed, rep
    # a detail level with no triangles left: its node and geometry go; the whole shape when the near one is empty
    for gid in ("g2", "g1", "g"):
        g0 = out.find(f'<geometry id="{gid}"')
        if g0 < 0:
            continue
        g1 = out.find("</geometry>", g0) + len("</geometry>")
        if "<triangles" in out[g0:g1]:
            continue
        if gid == "g":
            return "", removed, rep
        out = out[:g0] + out[g1:].lstrip("\n")
        k = out.find(f'<instance_geometry url="#{gid}"')
        a = out.rfind("<node ", 0, k)
        b = out.find("</node>", k) + len("</node>")
        out = out[:a] + out[b:]
    return out, removed, rep


def skin_grass_step(root, report=None):
    """v3.1.2 (finishing step after steep_skin): no skin earth on the meadow banks; the terrain there meadow again."""
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
    Hter = Z0 + q.astype(np.float32) / 65535.0 * MAXH
    colours = BaseColours(zi, lv, names, n)
    rep = {"files": 0, "changed_files": 0, "removed_files": 0, "removed_triangles": 0, "kept_triangles": 0}
    files, gone = {}, set()
    under = np.zeros((n, n), bool)
    items = f"{lv}/main/MissionGroup/level_objects/terrain_skin/items.level.json"
    objs = read_items(zi, items) if items in zi.NameToInfo else []
    keep_objs = []
    for o in objs:
        f = o.get("shapeName", "").lstrip("/")
        if not f or f not in zi.NameToInfo:
            keep_objs.append(o)
            continue
        rep["files"] += 1
        new, rem, r = meadow_cut(zi.read(f).decode("utf-8"), o["position"], colours, lay, Hter, X0, Y0, sq)
        for k in ("removed_triangles", "kept_triangles"):
            rep[k] += r[k]
        if len(rem):
            ok = (rem >= 0).all(1) & (rem < n).all(1)
            under[rem[ok, 0], rem[ok, 1]] = True
        if new == "":
            gone.add(f)
            rep["removed_files"] += 1
            continue
        keep_objs.append(o)
        if new is not None:
            files[f] = new.encode("utf-8")
            rep["changed_files"] += 1
    if not (files or gone):
        rep["seconds"] = round(time.time() - t0)
        print("skin grass: nothing to do %s" % rep, flush=True)
        return rep
    # the terrain under the removed skin: its Bank vertices take the meadow layer beside them (the game's grass grows there)
    under = ndi.binary_dilation(under, iterations=1)
    bank = np.isin(lay, [i for i, nm in enumerate(names) if nm in NEAREST_OF])
    ch = under & bank
    lay2 = lay.copy()
    if ch.any():
        rr, cc = np.nonzero(ch)
        c0, c1 = cc.min(), cc.max() + 1
        B, M = 1024, 64                                 # in bands (the nearest-layer transform of the whole block is big)
        for a in range(rr.min(), rr.max() + 1, B):
            a1 = min(a + B, rr.max() + 1)
            b0, b1 = max(a - M, 0), min(a1 + M, n)
            near, mw = colours.meadow(lay[b0:b1, c0:c1])
            near, mw = near[a - b0:a1 - b0], mw[a - b0:a1 - b0]
            sel = ch[a:a1, c0:c1] & (mw > 0.5)
            lay2[a:a1, c0:c1] = np.where(sel, near, lay2[a:a1, c0:c1])
    rep["relayered_vertices"] = int((lay2 != lay).sum())
    files[ter_name] = data[:5 + 2 * n * n] + lay2.astype(np.uint8).tobytes() + data[5 + 3 * n * n:]
    assert len(files[ter_name]) == len(data)
    # the skin's bushes on what was removed go (they stood on the skin; the meadow has its own shrubs)
    rm_plants = 0
    for t in PLANTS:
        ff = f"{lv}/forest/{t}.forest4.json"
        if ff not in zi.NameToInfo:
            continue
        rows = [ln for ln in zi.read(ff).decode("utf-8").splitlines() if ln.strip()]
        kept = []
        for ln in rows:
            x, y = json.loads(ln)["pos"][:2]
            r, c = int(round((y - Y0) / sq)), int(round((x - X0) / sq))
            if 0 <= r < n and 0 <= c < n and under[r, c] and colours.meadow_ids[lay2[r, c]]:
                rm_plants += 1
                continue
            kept.append(ln)
        if len(kept) != len(rows):
            files[ff] = ("\n".join(kept) + "\n").encode("utf-8") if kept else b""
    rep["removed_plants"] = rm_plants
    if gone:
        files[items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in keep_objs) + "\n").encode("utf-8")
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in gone:
                continue
            if nm in files:
                ni = zipfile.ZipInfo(nm, now)          # a new date: the game converts the terrain again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, files.pop(nm))
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, b in files.items():
            zo.writestr(zipfile.ZipInfo(nm, now), b, compress_type=zipfile.ZIP_DEFLATED)
    tot = rep["removed_triangles"] + rep["kept_triangles"]
    rep["removed_share"] = round(rep["removed_triangles"] / max(tot, 1), 3)
    rep["seconds"] = round(time.time() - t0)
    print("skin grass: %s" % rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


# ------------------------------------------------------------------------------------------------ one look for the banks

def read_skin_dae(txt):
    """[(node name, {material: [P (local), N, col (k, 4), T]})] of the detail levels of a skin DAE (write_dae with
    weld=False: every corner one index into all the arrays)."""
    out = []
    for nm, gid in re.findall(r'<node id="([^"]+)" name="[^"]+" type="NODE"><instance_geometry url="#([^"]+)"', txt):
        g0 = txt.find(f'<geometry id="{gid}"')
        geom = txt[g0:txt.find("</geometry>", g0)]
        arr = lambda k, w: np.array(re.search(_ARR % f"{gid}-{k}a", geom).group(2).split(), np.float64).reshape(-1, w)
        V, N, C = arr("p", 3), arr("n", 3), arr("c", 4)
        parts = {}
        for m in _TRI.finditer(geom):
            nin = m.group(3).count("<input")
            I = np.array(m.group(4).split(), np.int64).reshape(-1, nin)[:, 0]
            used, inv = np.unique(I, return_inverse=True)
            parts[m.group(1)] = [V[used], N[used], C[used].copy(), inv.reshape(-1, 3)]
        out.append((nm, parts))
    return out


def skin_blend_step(root, report=None):
    """v3.1.3 (finishing step after skin_grass): a level whose skin was built before v3.1.3 brought to its look: the
    new textures (2048 px over 6 m, the earth without green patches, both of one mean brightness), the vertex colours
    to the new means, the projection along smoothed axes (smooth_axes), the earth's fringe over the rock (border).
    The same as a build of this version gives; nothing to do on a level that has the fringe already (a build). The
    steep yards (mp_hard_bank, on the road shapes) keep the old bank texture, copied to t_hard_bank_*."""
    import network_mesh, road_mesh
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    mf = f"{lv}/{D}/terrain_skin.materials.json"
    rep = {"files": 0, "fringe_triangles": 0, "triangles": 0}
    if mf not in zi.NameToInfo or f"{MAT_FRINGE}_1" in json.loads(zi.read(mf)):
        rep["seconds"] = round(time.time() - t0)
        print("skin blend: nothing to do (no skin, or its fringe is there)", flush=True)
        return rep
    _, rtop = network_mesh.top_faces(zi, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    RS = road_mesh.TriSurface(rtop)
    gain = {MAT: OLD_TEX_MEAN / TEX_MEAN, MAT_FAR: OLD_TEX_MEAN / TEX_MEAN, MAT_ROCK: OLD_ROCK_TEX_MEAN / ROCK_TEX_MEAN}
    files = {}
    items = f"{lv}/main/MissionGroup/level_objects/terrain_skin/items.level.json"
    for o in read_items(zi, items):
        f = o.get("shapeName", "").lstrip("/")
        if not f or f not in zi.NameToInfo:
            continue
        origin = np.asarray(o["position"], np.float64)
        levels = read_skin_dae(zi.read(f).decode("utf-8"))
        mbs = []
        for k, (node, parts) in enumerate(levels):
            for m, pt in parts.items():
                pt[0] = pt[0] + origin
                pt[2][:, :3] = np.clip(pt[2][:, :3] * gain.get(m, 1.0), 0, 1)
            if k == 0:
                parts = border(parts, RS)
                rep["fringe_triangles"] += sum(len(pt[3]) for m, pt in parts.items() if m.startswith(MAT_FRINGE))
                rep["triangles"] += sum(len(pt[3]) for pt in parts.values())
            mb = bng.MeshBuilder()
            add_parts(mb, parts)
            base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
            mbs.append((int(detail), mb))
        if not mbs or mbs[0][1].empty():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.dae")
            mbs[0][1].write_dae(path, name=base, origin=origin, detail=mbs[0][0], weld=False,
                                lods=[(d, mb) for d, mb in mbs[1:] if not mb.empty()])
            files[f] = open(path, "rb").read()
        rep["files"] += 1
    # the yards keep the bank as it was (their uvs and colours are for it)
    for a, b in (("t_steep_bank_b.color.png", "t_hard_bank_b.color.png"), ("t_steep_bank_nm.normal.png", "t_hard_bank_nm.normal.png")):
        if f"{lv}/{D}/{a}" in zi.NameToInfo:
            files[f"{lv}/{D}/{b}"] = zi.read(f"{lv}/{D}/{a}")
    rmf = f"{lv}/art/shapes/roads/main.materials.json"
    if rmf in zi.NameToInfo:
        rm = json.loads(zi.read(rmf))
        if YARD_MAT in rm:
            st = rm[YARD_MAT]["Stages"][0]
            st["baseColorMap"] = st["baseColorMap"].replace("t_steep_bank_b", "t_hard_bank_b")
            st["normalMap"] = st["normalMap"].replace("t_steep_bank_nm", "t_hard_bank_nm")
            files[rmf] = json.dumps(rm, indent=1).encode("utf-8")
    files.update(texture_files(lv))
    files[mf] = json.dumps({mm["name"]: mm for mm in materials()}, indent=1).encode("utf-8")
    with zi.writer() as zo:
        for i in zi.infolist():
            nm = i.filename
            zo.writestr(i, files.pop(nm) if nm in files else zi.read(i), compress_type=i.compress_type)
        for nm, b in files.items():
            zo.writestr(zipfile.ZipInfo(nm, time.localtime()[:6]), b, compress_type=zipfile.ZIP_DEFLATED)
    rep["fringe_share"] = round(rep["fringe_triangles"] / max(rep["triangles"], 1), 3)
    rep["seconds"] = round(time.time() - t0)
    print("skin blend: %s" % rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
