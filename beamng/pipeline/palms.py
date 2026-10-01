"""Windmill palms (Trachycarpus fortunei) of the gardens by the lake (v2.4).

The palm is the tree of the lakeside gardens of Ticino, and the vanilla tree models have none. The
aerial data cannot tell a palm from a small deciduous tree, so this is a guess, kept small and set by
the constants below: among the trees measured in gardens (survey 'giardino') within NEAR_LAKE m of
the lake and below MAX_Z m, those of palm size (HEIGHT m tall, crown at most MAX_CROWN m) become a palm
with probability SHARE (a fixed random draw); every palm keeps the position and the height measured.

The model is drawn here (nothing from a photograph): a straight trunk covered in brown fibre, about
25 fan leaves (each a cut-out texture of a palmate blade with its segments) on stalks around the top,
the lower ones drooping, and a few dead brown leaves hanging under the crown; 70 triangles.
"""
import os
import numpy as np
from scipy.ndimage import gaussian_filter
import bng
from bld_textures import noise, normal_map, to8, save

NEAR_LAKE = 400.0       # m from the lake shore
MAX_Z = 320.0           # m above sea level (the lake is at 271 m)
HEIGHT = (3.0, 9.0)     # m, measured height of a candidate
MAX_CROWN = 6.0         # m, measured crown diameter of a candidate
SHARE = 0.25            # of the candidates
SEED = 53
MODEL_H = 5.0           # m, height of the model at scale 1
NAME = "palm_trachycarpus"


def leaf_texture(n=512):
    """RGBA fan blade: segments radiating from the bottom middle over 200 degrees, split at the tips."""
    rng = np.random.default_rng(SEED)
    img = np.zeros((n, n, 4), np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    cx, cy = n / 2, n * 0.92
    dx, dy = xx - cx, cy - yy
    r = np.hypot(dx, dy) / (n * 0.48)
    a = np.degrees(np.arctan2(dy, dx))                       # 0 = right, 90 = up
    seg = 34
    lo, hi = -10.0, 190.0
    t = (a - lo) / (hi - lo)
    k = t * seg
    frac = k - np.floor(k)
    inside = (t >= 0) & (t <= 1) & (r > 0.06)
    # every segment a long narrow blade, split near its tip
    reach = 0.75 + 0.25 * np.sin(np.pi * np.clip(t, 0, 1)) ** 0.6
    width = 0.42 * (1.0 - 0.6 * np.clip((r - 0.65) / 0.35, 0, 1))
    blade = inside & (r < reach) & (np.abs(frac - 0.5) < width)
    split = (r > 0.82 * reach) & (np.abs(frac - 0.5) < 0.06)
    blade &= ~split
    shade = 0.75 + 0.35 * np.abs(frac - 0.5) * 2               # folds of the plicate blade
    base = np.array([0.22, 0.34, 0.15], np.float32) * (1 + 0.06 * noise(n, n, 3, rng))[..., None]
    img[blade, :3] = (base * shade[..., None])[blade]
    img[blade, 3] = 1.0
    # the stalk where it joins the blade
    stalk = (np.abs(dx) < n * 0.012) & (dy > 0) & (dy < n * 0.08)
    img[stalk, :3] = [0.30, 0.30, 0.18]
    img[stalk, 3] = 1.0
    return img


def dead_texture(n=256):
    """RGBA dead leaf hanging down: a closed brown fan."""
    rng = np.random.default_rng(SEED + 1)
    img = np.zeros((n, n, 4), np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    w = 0.18 + 0.22 * (yy / n)
    m = np.abs(xx / n - 0.5) < w * 0.5
    stripes = 0.85 + 0.15 * np.sin(xx / n * 90)
    col = np.array([0.45, 0.33, 0.20], np.float32) * (1 + 0.08 * noise(n, n, 2, rng))[..., None]
    img[m, :3] = (col * stripes[..., None])[m]
    img[m, 3] = 1.0
    return img


def trunk_texture(n=256):
    """Brown fibre of the trunk, with the rings of old leaf bases."""
    rng = np.random.default_rng(SEED + 2)
    fib = noise(n, n, 0.8, rng) + 0.6 * noise(n, n, 3, rng)
    rings = np.sin(np.arange(n)[:, None] / n * 2 * np.pi * 12) * 0.5
    v = 0.36 * (1 + 0.12 * fib + 0.08 * rings)
    col = np.stack([v * 1.05, v * 0.82, v * 0.58], -1)
    return to8(np.clip(col, 0, 1)), normal_map(fib + 2.0 * rings, 0.8)


def model():
    """MeshBuilder parts of the palm, base at (0, 0, 0), MODEL_H m tall: [(material, V, UV, N)]."""
    rng = np.random.default_rng(SEED + 3)
    parts = []
    top = MODEL_H * 0.78
    # trunk: 8 sides, slightly thicker at the bottom, as a triangle soup
    sides = 8
    a = np.linspace(0, 2 * np.pi, sides + 1)
    rb, rt = 0.13, 0.11
    V, UV, Nn = [], [], []
    for i in range(sides):
        p0 = (rb * np.cos(a[i]), rb * np.sin(a[i]), 0.0)
        p1 = (rb * np.cos(a[i + 1]), rb * np.sin(a[i + 1]), 0.0)
        p2 = (rt * np.cos(a[i + 1]), rt * np.sin(a[i + 1]), top)
        p3 = (rt * np.cos(a[i]), rt * np.sin(a[i]), top)
        u0, u1 = i / sides, (i + 1) / sides
        for p, uv in zip((p0, p1, p2, p0, p2, p3), ((u0, 0), (u1, 0), (u1, 6), (u0, 0), (u1, 6), (u0, 6))):
            V.append(p)
            UV.append(uv)
            ang = np.arctan2(p[1], p[0])
            Nn.append((np.cos(ang), np.sin(ang), 0.0))
    parts.append(("palm_trunk", np.array(V), np.array(UV), np.array(Nn)))
    # crown: fan leaves on stalks around the top
    V, UV, Nn = [], [], []
    n_leaf = 25
    for j in range(n_leaf):
        az = 2 * np.pi * j / n_leaf + rng.uniform(-0.12, 0.12)
        el = np.radians(rng.uniform(-35, 70))                 # angle of the stalk over the horizontal
        stalk = rng.uniform(0.45, 0.8)
        d = np.array([np.cos(az) * np.cos(el), np.sin(az) * np.cos(el), np.sin(el)])
        c = np.array([0, 0, top + 0.15]) + d * stalk          # where the blade starts
        size = rng.uniform(0.95, 1.25)                        # width of the blade (m)
        # the blade spreads across the stalk direction, its face turned up and out
        side = np.array([-np.sin(az), np.cos(az), 0.0])
        up = np.cross(side, d)
        up /= np.linalg.norm(up)
        fwd = d * 0.35 + up * 0.94
        fwd /= np.linalg.norm(fwd)
        # the fan fills the lower 0.6 of the texture: the quad is as long
        p0 = c - side * size * 0.5
        p1 = c + side * size * 0.5
        p2 = p1 + fwd * size * 0.6
        p3 = p0 + fwd * size * 0.6
        for p, uv in zip((p0, p1, p2, p0, p2, p3), ((0, 0), (1, 0), (1, 0.6), (0, 0), (1, 0.6), (0, 0.6))):
            V.append(p)
            UV.append(uv)
            Nn.append((0.0, 0.0, 1.0))                        # lit like the canopy above
    parts.append(("palm_leaf", np.array(V), np.array(UV), np.array(Nn)))
    # dead leaves hanging along the trunk under the crown
    V, UV, Nn = [], [], []
    for j in range(6):
        az = 2 * np.pi * j / 6 + rng.uniform(-0.3, 0.3)
        r = 0.16
        side = np.array([-np.sin(az), np.cos(az), 0.0]) * 0.22
        c = np.array([np.cos(az) * r, np.sin(az) * r, top - 0.05])
        bot = c + np.array([np.cos(az) * 0.08, np.sin(az) * 0.08, -rng.uniform(0.6, 0.9)])
        p0, p1, p2, p3 = bot - side, bot + side, c + side * 0.4, c - side * 0.4
        for p, uv in zip((p0, p1, p2, p0, p2, p3), ((0, 1), (1, 1), (1, 0), (0, 1), (1, 0), (0, 0))):
            V.append(p)
            UV.append(uv)
            Nn.append((np.cos(az), np.sin(az), 0.0))
    parts.append(("palm_dead", np.array(V), np.array(UV), np.array(Nn)))
    return parts


def build(level_dir, level_name):
    """Textures, materials and the DAE of the palm in the level; returns (shape path, bounds min, max)."""
    d = os.path.join(level_dir, "art", "shapes", "trees")
    os.makedirs(d, exist_ok=True)
    save(os.path.join(d, "palm_leaf_b.color.png"), to8(leaf_texture()))
    save(os.path.join(d, "palm_dead_b.color.png"), to8(dead_texture()))
    col, nm = trunk_texture()
    save(os.path.join(d, "palm_trunk_b.color.png"), col)
    save(os.path.join(d, "palm_trunk_nm.normal.png"), nm)
    L = f"/levels/{level_name}/art/shapes/trees"
    bng.write_materials(os.path.join(d, "palm.materials.json"), [
        bng.material("palm_leaf", f"{L}/palm_leaf_b.color.png", alpha_test=100, double_sided=True, roughness=0.8),
        bng.material("palm_dead", f"{L}/palm_dead_b.color.png", alpha_test=100, double_sided=True, roughness=0.95),
        bng.material("palm_trunk", f"{L}/palm_trunk_b.color.png", f"{L}/palm_trunk_nm.normal.png", roughness=0.95),
    ])
    mb = bng.MeshBuilder()
    allv = []
    for mat, V, UV, N in model():
        mb.add(mat, V, uvs=UV, normals=N)
        allv.append(V)
    mb.write_dae(os.path.join(d, f"{NAME}.dae"), name=NAME)
    P = np.concatenate(allv)
    return f"{L}/{NAME}.dae", P.min(0).tolist(), P.max(0).tolist()


def candidates(x, y, z, h, d, lc):
    """Boolean mask of the measured trees that become palms (see the module doc)."""
    import pickle
    import shapely
    from config import WORK
    from landcover import CODE
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    lake = [g for g, _ in av["LCSF"].get("specchio_acqua", []) if g.area > 1e5]
    if not lake:
        return np.zeros(len(x), bool)
    shore = shapely.union_all(lake)
    m = (lc == CODE["giardino"]) & (h >= HEIGHT[0]) & (h <= HEIGHT[1]) & (d <= MAX_CROWN) & (z < MAX_Z)
    idx = np.flatnonzero(m)
    near = shapely.distance(shore, shapely.points(x[idx], y[idx])) < NEAR_LAKE
    idx = idx[near]
    rng = np.random.default_rng(SEED)
    pick = idx[rng.random(len(idx)) < SHARE]
    out = np.zeros(len(x), bool)
    out[pick] = True
    return out
