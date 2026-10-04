"""Far trees (v2.7): every measured tree away from the roads, in a model the game draws as a picture.

Since v2.3 the forest away from the roads was thinned (vegetation.thin: the tallest tree of every
11-17 m cell up to 100 m from a road, beyond that of every cell of a grid coarse enough for CAP),
because the vanilla tree models are drawn in full up to a few hundred metres from the camera and
the slopes with many hairpins slowed the game down. Seen from the valley the mountains then looked
bald: one tree in five or six on a slope that is a closed forest.

Here the trees the thinning leaves out come back, all of them, as instances of three drawn models
(round and narrow broad-leaved crowns, a fir) in three shades each. Every model has two detail
levels: the mesh (about 150 triangles of cut-out leaf cards around a trunk) while it covers more
than MESH_PX pixels on screen, a few tens of metres from the camera, and below that an imposter
(Torque 'autobillboard'): BB['BB::EQUATOR_STEPS'] pictures of the mesh around it, rendered and
lit by the game itself, drawn as one camera-facing quad per tree and batched per forest cell. These
trees are never near a road (they are where thin() drops a tree: more than 30 m from a road, 5 m
from a path), so from the roads they are always quads: the count of the forest comes back for the
cost of two triangles a tree, and the vanilla trees near the roads are the same as before.

Models are scaled to the measured height (H0 m at scale 1); among the broad-leaved forms the one
whose crown at that scale is closest to the measured crown diameter. The shade is the measured
orthophoto colour of the tree: the trees of each kind (broad-leaved, conifer) are split into
SHADES equal groups by brightness and every group gets its median colour (times ALBEDO_K: the
orthophoto sees crowns with their own shadow in them, the game shades the model again).
Nothing is taken from a photograph: the leaf and needle textures are drawn here.
"""
import os
import numpy as np
import bng
from bld_textures import noise, to8, save

H0 = 10.0                 # m, height of every far model at scale 1
# form -> (kind, crown diameter at scale 1, m)
FORMS = {"broad": ("broadleaf", 8.0), "narrow": ("broadleaf", 5.0), "fir": ("conifer", 4.6)}
SHADES = 3
SHADE_NAMES = "abc"
ALBEDO_K = 1.15
MESH_PX = 600             # detail size of the mesh: about 30-40 m from the camera for a 10 m tree
BB_PX = 100               # detail size of the imposter (any size under MESH_PX: the last detail is never culled)
BB = {"BB::EQUATOR_STEPS": 8, "BB::POLAR_STEPS": 0, "BB::POLAR_ANGLE": 25, "BB::DL": 0,
      "BB::DIM": 128, "BB::INCLUDE_POLES": 1}
PATH_GAP = 0.5            # m: no far tree whose crown comes closer than this to a path
SEED = 61


def name(form, shade):
    return f"far_{form}_{SHADE_NAMES[shade]}"


def names():
    return [name(f, k) for f in FORMS for k in range(SHADES)]


# ---------------------------------------------------------------------- colours
def colors(rgb, conifer):
    """{kind: (brightness edges between the shades, [SHADES sRGB colours 0..1])} from the orthophoto
    colour of the trees (rgb (n, 3), 0..255) and their kind."""
    out = {}
    fallback = {"broadleaf": (0.24, 0.31, 0.16), "conifer": (0.15, 0.21, 0.13)}
    for kind, m in (("broadleaf", ~conifer), ("conifer", conifer)):
        if m.sum() < 3 * SHADES:
            c = np.array(fallback[kind])
            out[kind] = (np.array([-1.0, 1e9]), [c * (0.85 + 0.15 * k) for k in range(SHADES)])
            continue
        v = rgb[m].mean(1)
        edges = np.quantile(v, np.arange(1, SHADES) / SHADES)
        idx = np.digitize(v, edges)
        out[kind] = (edges, [np.clip(np.median(rgb[m][idx == k], 0) / 255.0 * ALBEDO_K, 0, 1) for k in range(SHADES)])
    return out


def assign(h, d, rgb, conifer, cols):
    """Model name, scale and crown radius (m) of every tree (heights h, crown diameters d)."""
    s = h / H0
    shade = np.zeros(len(h), int)
    for kind, m in (("broadleaf", ~conifer), ("conifer", conifer)):
        shade[m] = np.digitize(rgb[m].mean(1), cols[kind][0])
    err = {f: np.abs(np.log(np.maximum(FORMS[f][1] * s, 0.3) / np.maximum(d, 0.5))) for f in ("broad", "narrow")}
    form = np.where(conifer, "fir", np.where(err["broad"] <= err["narrow"], "broad", "narrow"))
    out = np.array([name(f, k) for f, k in zip(form, shade)], object)
    radius = np.array([FORMS[f][1] / 2 for f in form]) * s
    return out, s, radius


# ---------------------------------------------------------------------- textures (drawn)
def clump_texture(col, rng, n=256):
    """RGBA cluster of leaves: a ragged round patch with holes towards its edge, lighter on top."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    r = np.hypot(xx - 0.5, yy - 0.5) / 0.5
    field = 0.6 * noise(n, n, n / 48, rng, wrap=False) + 0.4 * noise(n, n, n / 14, rng, wrap=False)
    alpha = (1.5 * (1.0 - r ** 1.6) + 0.45 * field) > 0.6
    fine = noise(n, n, 1.2, rng, wrap=False)
    leaves = noise(n, n, n / 64, rng, wrap=False)
    light = (1.08 - 0.3 * yy) * (0.86 + 0.07 * fine + 0.07 * leaves)
    img = np.zeros((n, n, 4), np.float32)
    img[..., :3] = np.asarray(col, np.float32) * light[..., None]
    img[..., 3] = alpha
    return img


def branch_texture(col, rng, n=256):
    """RGBA fir branch seen from above: the trunk end on the left, the tip on the right, needle
    sprays along it, tapering to the tip."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    half = 0.5 * np.clip(1.0 - xx, 0, 1) ** 0.75
    ragged = 0.12 * noise(n, n, n / 40, rng, wrap=False)
    sprays = 0.08 * np.sin(xx * 2 * np.pi * 9 + 6 * np.abs(yy - 0.5))
    alpha = (np.abs(yy - 0.5) < half * (0.9 + ragged + sprays)) & (xx > 0.02)
    alpha &= noise(n, n, 1.5, rng, wrap=False) > -1.3                      # a few gaps between the needles
    shade = 0.82 + 0.1 * noise(n, n, 1.0, rng, wrap=False) + 0.12 * (1.0 - np.abs(yy - 0.5) * 2)
    img = np.zeros((n, n, 4), np.float32)
    img[..., :3] = np.asarray(col, np.float32) * shade[..., None]
    img[..., 3] = alpha
    return img


# ---------------------------------------------------------------------- meshes
def _quad(parts, mat, p0, p1, p2, p3, uvs, nfn):
    V = np.array([p0, p1, p2, p0, p2, p3], float)
    UV = np.array([uvs[0], uvs[1], uvs[2], uvs[0], uvs[2], uvs[3]], float)
    parts.setdefault(mat, [[], [], []])
    parts[mat][0].append(V)
    parts[mat][1].append(UV)
    parts[mat][2].append(np.array([nfn(p) for p in V]))


def _trunk(parts, mat, z0, z1, r0, r1, sides=6):
    for i in range(sides):
        a0, a1 = 2 * np.pi * i / sides, 2 * np.pi * (i + 1) / sides
        c0, c1 = np.array([np.cos(a0), np.sin(a0), 0]), np.array([np.cos(a1), np.sin(a1), 0])
        p0, p1 = c0 * r0 + [0, 0, z0], c1 * r0 + [0, 0, z0]
        p2, p3 = c1 * r1 + [0, 0, z1], c0 * r1 + [0, 0, z1]
        _quad(parts, mat, p0, p1, p2, p3, ((0, 0), (1, 0), (1, 1), (0, 1)),
              lambda p: tuple(np.array([p[0], p[1], 0.0]) / max(np.hypot(p[0], p[1]), 1e-6)))


def broadleaf_mesh(diam, leaf_mat, trunk_mat, rng, n_cards=80, n_inner=12):
    """Ellipsoid crown (half axes diam/2 across, 0.33 H0 high, as canopy.py's broad-leaved crown)
    of leaf cards, normals pointing out of the crown so it shades like one volume."""
    a, c = diam / 2, 0.33 * H0
    zc = H0 - c
    centre = np.array([0, 0, zc])
    parts = {}
    _trunk(parts, trunk_mat, -0.3, zc, 0.035 * H0, 0.02 * H0)

    def nfn(p):
        g = (p - centre) / np.array([a * a, a * a, c * c])
        g = g / max(np.linalg.norm(g), 1e-6) + np.array([0, 0, 0.35])
        return tuple(g / np.linalg.norm(g))

    side = 0.65 * np.sqrt(a * c)
    k = np.arange(n_cards + n_inner) + 0.5
    zz = 1 - 2 * k / len(k)
    az = np.pi * (1 + 5 ** 0.5) * k
    for i in range(len(k)):
        f = rng.uniform(0.55, 0.95) if i < n_cards else rng.uniform(0.15, 0.4)
        rr = np.sqrt(1 - zz[i] ** 2)
        u = np.array([rr * np.cos(az[i]), rr * np.sin(az[i]), zz[i]])
        p = centre + u * f * np.array([a, a, c])
        nrm = u + rng.normal(0, 0.6, 3)
        nrm /= np.linalg.norm(nrm)
        t1 = np.cross(nrm, rng.normal(0, 1, 3))
        t1 /= np.linalg.norm(t1)
        t2 = np.cross(nrm, t1)
        s = side * rng.uniform(0.8, 1.15) * (0.8 if i >= n_cards else 1.0) / 2
        _quad(parts, leaf_mat, p - t1 * s - t2 * s, p + t1 * s - t2 * s, p + t1 * s + t2 * s, p - t1 * s + t2 * s,
              ((0, 0), (1, 0), (1, 1), (0, 1)), nfn)
    return parts


def conifer_mesh(diam, leaf_mat, trunk_mat, rng, tiers=10, per_tier=7):
    """Cone of branch cards from 0.18 H0 (full radius diam/2) to the top, as canopy.py's conifer."""
    parts = {}
    zb, zt = 0.18 * H0, 1.02 * H0
    rb = diam / 2
    _trunk(parts, trunk_mat, -0.3, 0.92 * H0, 0.03 * H0, 0.008 * H0)

    def nfn(p):
        g = np.array([p[0], p[1], 0.0])
        g = g / max(np.linalg.norm(g), 1e-6) + np.array([0, 0, 0.6])
        return tuple(g / np.linalg.norm(g))

    golden = np.pi * (3 - 5 ** 0.5)
    for t in range(tiers):
        z = zb + (0.93 * H0 - zb) * t / (tiers - 1)
        r = max(rb * (1 - (z - zb) / (zt - zb)), 0.35)
        for j in range(per_tier):
            az = 2 * np.pi * j / per_tier + golden * t + rng.uniform(-0.2, 0.2)
            droop = np.radians(rng.uniform(12, 28))
            d = np.array([np.cos(az) * np.cos(droop), np.sin(az) * np.cos(droop), -np.sin(droop)])
            sidev = np.array([-np.sin(az), np.cos(az), 0.0])
            tilt = np.radians(rng.uniform(25, 70))            # seen from the side and from above
            w = sidev * np.cos(tilt) + np.array([0, 0, 1.0]) * np.sin(tilt)
            L = r * rng.uniform(1.0, 1.12)
            W = max(0.5, 0.9 * L) / 2
            o = np.array([0, 0, z + 0.1])
            _quad(parts, leaf_mat, o - w * W, o + d * L - w * W, o + d * L + w * W, o + w * W,
                  ((0, 0), (1, 0), (1, 1), (0, 1)), nfn)
    for v in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0])):    # leader at the top
        o, top = np.array([0, 0, 0.86 * H0]), np.array([0, 0, H0])
        _quad(parts, leaf_mat, o - v * 0.35, top - v * 0.35, top + v * 0.35, o + v * 0.35,
              ((0, 0), (1, 0), (1, 1), (0, 1)), nfn)
    return parts


def build(level_dir, level_name, cols):
    """Textures, materials and the DAEs of the far models in the level (art/shapes/trees);
    returns {name: (shape path, bounds min, bounds max)}."""
    d = os.path.join(level_dir, "art", "shapes", "trees")
    os.makedirs(d, exist_ok=True)
    L = f"/levels/{level_name}/art/shapes/trees"
    mats = [bng.material("far_trunk", base_color=(0.30, 0.25, 0.20, 1.0), roughness=0.95)]
    for kind, tex in (("broadleaf", clump_texture), ("conifer", branch_texture)):
        for k, col in enumerate(cols[kind][1]):
            m = f"far_{kind}_{SHADE_NAMES[k]}"
            save(os.path.join(d, f"{m}.color.png"), to8(tex(col, np.random.default_rng(SEED + k))))
            mats.append(bng.material(m, f"{L}/{m}.color.png", alpha_test=100, double_sided=True, roughness=0.9))
    bng.write_materials(os.path.join(d, "far_trees.materials.json"), mats)
    out = {}
    for form, (kind, diam) in FORMS.items():
        mesh = conifer_mesh if kind == "conifer" else broadleaf_mesh
        for k in range(SHADES):
            parts = mesh(diam, f"far_{kind}_{SHADE_NAMES[k]}", "far_trunk", np.random.default_rng(SEED + 7 * k))
            mb = bng.MeshBuilder()
            allv = []
            for mat, (Vs, UVs, Ns) in parts.items():
                V = np.concatenate(Vs)
                mb.add(mat, V, uvs=np.concatenate(UVs), normals=np.concatenate(Ns))
                allv.append(V)
            n = name(form, k)
            mb.write_dae(os.path.join(d, f"{n}.dae"), name=n, detail=MESH_PX,
                         billboard=(BB_PX, BB))
            P = np.concatenate(allv)
            out[n] = (f"{L}/{n}.dae", P.min(0).tolist(), P.max(0).tolist())
    return out


def select(names_, radius, dist_path=None, cap=None, h=None, x=None, y=None):
    """Mask of the far trees kept: none whose crown comes within PATH_GAP m of a path; at most `cap`
    (the tallest of every cell of the coarsest grid that is still too many are dropped first)."""
    keep = np.ones(len(names_), bool)
    if dist_path is not None:
        keep &= dist_path - radius > PATH_GAP
    if cap is not None and keep.sum() > cap:
        import vegetation
        idx = np.flatnonzero(keep)
        for cell in np.arange(3.0, 40.0, 0.5):
            k = vegetation.tallest_per_cell(x, y, h, idx, cell)
            if len(k) <= cap:
                break
        keep[:] = False
        keep[k] = True
    return keep
