"""Far trees (v2.7): every measured tree away from the roads, in a model the game draws as a picture.

Since v2.3 the forest away from the roads was thinned (vegetation.thin: the tallest tree of every
11-17 m cell up to 100 m from a road, beyond that of every cell of a grid coarse enough for CAP),
because the vanilla tree models are drawn in full up to a few hundred metres from the camera and
the slopes with many hairpins slowed the game down. Seen from the valley the mountains then looked
bald: one tree in five or six on a slope that is a closed forest.

Here the trees the thinning leaves out come back, all of them, as instances of three drawn models
(round and narrow broad-leaved crowns, a fir) in three shades each. Every model has two detail
levels: the mesh (150-300 triangles of cut-out leaf cards around a trunk) while it covers more
than MESH_PX pixels on screen, within about ten metres of the camera, and below that an imposter
(Torque 'autobillboard'): BB['BB::EQUATOR_STEPS'] pictures of the mesh around it, rendered and
lit by the game itself, drawn as one camera-facing quad per tree and batched per forest cell. These
trees are never near a road (they are where thin() drops a tree: more than 30 m from a road, 5 m
from a path), so from the roads they are always quads: the count of the forest comes back for the
cost of two triangles a tree, and the vanilla trees near the roads are the same as before.

Models are scaled to the measured height (H0 m at scale 1); among the broad-leaved forms the one
whose crown at that scale is closest to the measured crown diameter. The shade is the measured
orthophoto colour of the tree: the trees of each kind (broad-leaved, conifer) are split into
SHADES equal groups by brightness and every group gets its median colour, made more saturated and
darker (SATURATION, VALUE: the orthophoto sees the crowns through haze, and next to the vanilla trees
the plain median looked pale and frosted in the game).
Nothing is taken from a photograph: the leaf and needle shapes are drawn here, as the cut-out
(opacityMap) of each leaf material; the colour is the material's own (baseColorFactor) times a vertex
colour per card. With a colour texture the game baked the imposters grey: it bakes them at load,
before the texture is there, and kept that picture in its cache.
"""
import os, struct
import numpy as np
import bng
from bld_textures import noise
import json, os, re, shutil, sys, tempfile, zipfile
from scipy.spatial import cKDTree
import osm_surface
import vegetation
from config import LEVEL_NAME, WORK
from landcover import CODE
from markings_net import read_items, shape_tris, up_faces

H0 = 10.0                 # m, height of every far model at scale 1
# form -> (kind, crown diameter at scale 1, m)
FORMS = {"broad": ("broadleaf", 8.0), "narrow": ("broadleaf", 5.0), "fir": ("conifer", 4.6)}
SHADES = 3
SHADE_NAMES = "abc"
SATURATION = 1.4         # the orthophoto sees the crowns through haze: grey-green, paler than the vanilla trees
VALUE = 0.62              # at 0.8 the imposters came out ~1.4x brighter than the vanilla trees beside them, at 0.55 the meshes near-black
MESH_PX = 5000            # detail size of the mesh: within about 12 m of a 20 m tree (in game at 1440p: 8000 -> 8 m, 600 -> 150 m)
BB_PX = 100               # detail size of the imposter (any size under MESH_PX: the last detail is never culled)
BB = {"BB::EQUATOR_STEPS": 8, "BB::POLAR_STEPS": 0, "BB::POLAR_ANGLE": 25, "BB::DL": 0,
      "BB::DIM": 256, "BB::INCLUDE_POLES": 1}
CARD_SHADE = (0.78, 1.0)   # vertex colour of each leaf card (the shade colour is the material's at the top)
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
        out[kind] = (edges, [vivid(np.median(rgb[m][idx == k], 0) / 255.0) for k in range(SHADES)])
    return out


def vivid(c):
    c = np.asarray(c, float)
    lum = c.mean()
    return np.clip((lum + (c - lum) * SATURATION) * VALUE, 0, 1)


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
def clump_texture(col, rng, n=256, leaves=420):
    """RGBA cluster of leaves: single leaves (ellipses, each its own shade, lighter on top) packed in
    a round patch, sparser towards its edge; between them the texture is transparent."""
    img = np.zeros((n, n, 4), np.float32)
    col = np.asarray(col, np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    for _ in range(leaves):
        r = 0.47 * n * np.sqrt(rng.uniform(0, 1)) ** 0.8
        a = rng.uniform(0, 2 * np.pi)
        cx, cy = n / 2 + r * np.cos(a), n / 2 + r * np.sin(a)
        L = rng.uniform(0.035, 0.06) * n
        W = L * rng.uniform(0.45, 0.6)
        th = rng.uniform(0, np.pi)
        x0, x1 = int(max(cx - L, 0)), int(min(cx + L + 1, n))
        y0, y1 = int(max(cy - L, 0)), int(min(cy + L + 1, n))
        if x1 <= x0 or y1 <= y0:
            continue
        dx, dy = xx[y0:y1, x0:x1] - cx, yy[y0:y1, x0:x1] - cy
        u = dx * np.cos(th) + dy * np.sin(th)
        v = -dx * np.sin(th) + dy * np.cos(th)
        inside = (u / L) ** 2 + (v / W) ** 2 <= 1.0
        shade = rng.uniform(0.88, 1.06) * (1.04 - 0.12 * cy / n)   # low contrast: the imposter bake shows it as streaks
        sub = img[y0:y1, x0:x1]
        sub[inside, :3] = (col * shade)[None, :]
        sub[inside, 3] = 1.0
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


def broadleaf_mesh(diam, leaf_mat, trunk_mat, rng, n_cards=140, n_inner=16):
    """Ellipsoid crown (half axes diam/2 across, 0.33 H0 high, as canopy.py's broad-leaved crown)
    of leaf cards, normals pointing out of the crown so it shades like one volume."""
    a, c = diam / 2, 0.33 * H0
    zc = H0 - c
    centre = np.array([0, 0, zc])
    parts = {}
    _trunk(parts, trunk_mat, -0.3, zc, 0.035 * H0, 0.02 * H0)

    def nfn(p):
        g = (p - centre) / np.array([a * a, a * a, c * c])
        g = g / max(np.linalg.norm(g), 1e-6)
        return tuple(g / np.linalg.norm(g))

    side = 0.45 * np.sqrt(a * c)
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
        g = g / max(np.linalg.norm(g), 1e-6) + np.array([0, 0, 0.1])
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


# ---------------------------------------------------------------------- DDS
def _bc1(rgb):
    """BC1 blocks (bytes) of rgb (h, w, 3) 0..1, h and w multiples of 4: per block the two end
    colours are the texels farthest apart along the main axis of its colours, 4-colour mode."""
    h, w = rgb.shape[:2]
    b = rgb.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.float32)
    c = b - b.mean(1, keepdims=True)
    axis = np.einsum("nki,nkj->nij", c, c)
    v = np.ones((len(b), 3), np.float32)
    for _ in range(8):                                          # power iteration: the main axis
        v = np.einsum("nij,nj->ni", axis, v)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    p = np.einsum("nki,ni->nk", c, v)
    lo, hi = b[np.arange(len(b)), p.argmin(1)], b[np.arange(len(b)), p.argmax(1)]

    def q565(x):
        r, g, bl = (np.clip(np.rint(x * s), 0, s).astype(np.uint32) for x, s in
                    ((x[:, 0], 31), (x[:, 1], 63), (x[:, 2], 31)))
        return (r << 11) | (g << 5) | bl

    def rgb565(k):
        return np.stack([(k >> 11) / 31.0, ((k >> 5) & 63) / 63.0, (k & 31) / 31.0], 1).astype(np.float32)

    c0, c1 = q565(hi), q565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    e0, e1 = rgb565(c0), rgb565(c1)
    pal = np.stack([e0, e1, (2 * e0 + e1) / 3, (e0 + 2 * e1) / 3], 1)  # (n, 4, 3)
    idx = ((b[:, :, None, :] - pal[:, None]) ** 2).sum(-1).argmin(-1).astype(np.uint32)
    idx[c0 == c1] = 0                                           # one colour: 3-colour mode, keep index 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1, dtype=np.uint64).astype(np.uint32)
    out = np.zeros(len(b), dtype=[("c0", "<u2"), ("c1", "<u2"), ("bits", "<u4")])
    out["c0"], out["c1"], out["bits"] = c0, c1, bits
    return out.tobytes()


def write_dds(path, rgb):
    """BC1 (DXT1) DDS of rgb (n, n, >=3) 0..1, n a power of two, with its mipmaps down to 4x4 (the
    game rejects uncompressed DDS: "only RGB formats are supported")."""
    mips, a = [], np.asarray(rgb, np.float32)[..., :3]
    while True:
        mips.append(_bc1(a))
        if a.shape[0] == 4:
            break
        a = a.reshape(a.shape[0] // 2, 2, a.shape[1] // 2, 2, 3).mean((1, 3))
    n = rgb.shape[0]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000        # caps, height, width, pixelformat, mipmapcount, linearsize
    pf = struct.pack("<II4sIIIII", 32, 0x4, b"DXT1", 0, 0, 0, 0, 0)
    head = struct.pack("<4sIIIIIII44x", b"DDS ", 124, flags, n, n, len(mips[0]), 0, len(mips)) + pf + \
        struct.pack("<IIII4x", 0x1000 | 0x8 | 0x400000, 0, 0, 0)  # texture, complex, mipmap
    with open(path, "wb") as f:
        f.write(head + b"".join(mips))


def build(level_dir, level_name, cols):
    """Textures, materials and the DAEs of the far models in the level (art/shapes/trees);
    returns {name: (shape path, bounds min, bounds max)}."""
    d = os.path.join(level_dir, "art", "shapes", "trees")
    os.makedirs(d, exist_ok=True)
    L = f"/levels/{level_name}/art/shapes/trees"
    mats = [bng.material("far_trunk", base_color=(0.20, 0.19, 0.17, 1.0), roughness=0.95)]
    for kind, tex in (("broadleaf", clump_texture), ("conifer", branch_texture)):
        for k, col in enumerate(cols[kind][1]):
            m = f"far_{kind}_{SHADE_NAMES[k]}"
            alpha = tex(col, np.random.default_rng(SEED + k))[..., 3:4]
            write_dds(os.path.join(d, f"{m}_o.data.dds"), np.repeat(alpha, 3, axis=2))
            mats.append(bng.material(m, base_color=(*np.asarray(col) / CARD_SHADE[1], 1.0), alpha_test=100,
                                     double_sided=True, roughness=1.0, metallic=0.0, vert_color=True,
                                     detail={"opacityMap": f"{L}/{m}_o.data.dds"}))
    bng.write_materials(os.path.join(d, "far_trees.materials.json"), mats)
    out = {}
    for form, (kind, diam) in FORMS.items():
        mesh = conifer_mesh if kind == "conifer" else broadleaf_mesh
        for k in range(SHADES):
            rng = np.random.default_rng(SEED + 7 * k)
            parts = mesh(diam, f"far_{kind}_{SHADE_NAMES[k]}", "far_trunk", rng)
            mb = bng.MeshBuilder()
            allv = []
            for mat, (Vs, UVs, Ns) in parts.items():
                V = np.concatenate(Vs)
                shade = np.concatenate([np.full(len(v), rng.uniform(*CARD_SHADE)) for v in Vs]) \
                    if mat != "far_trunk" else np.ones(len(V))
                mb.add(mat, V, uvs=np.concatenate(UVs), normals=np.concatenate(Ns),
                       colors=np.column_stack([shade, shade, shade, np.ones(len(V))]))
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


# --------------------------------------------------------------------------------------------------
# Put the far trees (far_trees.py, v2.7) into the built level, a finishing step of build_level.py.
#
# The trees of trees.npz (work/trees.npz of the build, every tree measured in the area) that the
# level lacks come back as far trees: those more than NEAR + MARGIN m from a road surface and
# NEAR_PATH + MARGIN m from a path surface of the zip (nearer, vegetation.thin kept every tree and
# canopy.py may have moved it), with no forest item of the zip within MATCH m (the trees thin() kept
# in the bands, at their measured place). The road and path surfaces are the top faces of the road
# meshes of the zip. The far models, their textures and materials go into art/shapes/trees, the items
# into forest/far_*.forest4.json, their types into art/forest/managedItemData.json. Far trees of an
# earlier run are replaced. Everything else is copied as it is (same entries, same dates: the game
# keeps its converted shapes).
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish far_trees
# --------------------------------------------------------------------------------------------------

MARGIN = 3.0       # m beyond vegetation.NEAR / NEAR_PATH: the distances here are to the meshes, not the lines
MATCH = 1.0        # m: a measured tree with a forest item this close is in the level already
FAR_FILE = re.compile(r"/(forest/far_[a-z]+_[a-z]\.forest4\.json|art/shapes/trees/far_[^/]+)$")


def surface_points(zi, lv):
    """(road points, path points) (n, 2): vertices and centres of the top faces of the road meshes."""
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    road, path = [], []
    for m, t in surf.items():
        t = up_faces(t)
        if not len(t):
            continue
        P = np.concatenate([t.reshape(-1, 3), t.mean(1)])[:, :2]
        (path if m in osm_surface.PATH_MATS else road).append(P)
    cat = lambda L: np.unique(np.round(np.concatenate(L), 1), axis=0) if L else np.zeros((0, 2))
    return cat(road), cat(path)


def far_trees_step(root, trees_f=None):
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    t = np.load(trees_f or os.path.join(WORK, "trees.npz"))
    t = {k: t[k] for k in t.files}
    ok = t["lc"] != CODE["none"]
    t = {k: v[ok] for k, v in t.items()}
    road, path = surface_points(zi, lv)
    xy = np.column_stack([t["x"], t["y"]])
    d_road = cKDTree(road).query(xy)[0] if len(road) else np.full(len(xy), 1e9)
    d_path = cKDTree(path).query(xy)[0] if len(path) else np.full(len(xy), 1e9)
    have = []
    for n in zi.namelist():
        if n.startswith(f"{lv}/forest/") and n.endswith(".forest4.json") and not FAR_FILE.search(n) \
                and not os.path.basename(n).startswith("italy_guardrails"):        # v2.8: the guard rails
            have += [o["pos"][:2] for o in read_items(zi, n)]
    d_have = cKDTree(np.array(have)).query(xy)[0] if have else np.full(len(xy), 1e9)
    cand = (d_road > vegetation.NEAR + MARGIN) & (d_path > vegetation.NEAR_PATH + MARGIN) & (d_have > MATCH)
    print("trees measured %d: road and path surfaces %d / %d points, forest items %d; far tree candidates %d"
          % (len(xy), len(road), len(path), len(have), int(cand.sum())))
    far = {k: v[cand] for k, v in t.items()}
    far["dist_path"] = d_path[cand]
    tmp = tempfile.mkdtemp(prefix="magliaso_far_")
    try:
        items = vegetation.far_items(far, tmp, LEVEL_NAME)
        md_name = f"{lv}/art/forest/managedItemData.json"
        managed = json.loads(zi.read(md_name)) if md_name in zi.NameToInfo else {}
        managed = {k: v for k, v in managed.items() if not k.startswith("far_")}
        new_files = {}
        for (name, p), lst in items.items():
            managed[name] = {"name": name, "internalName": name, "class": "TSForestItemData", "persistentId": bng.pid(),
                             "radius": 0.5, "shapeFile": p}
            lines = [json.dumps({"ctxid": 1, "pos": [round(float(px), 3), round(float(py), 3), round(float(pz), 3)],
                                 "rotationMatrix": [round(v, 5) for v in bng.rot_local_x_to(yaw)], "scale": round(float(s), 4), "type": name},
                                separators=(",", ":")) for (px, py, pz, yaw, s, _) in lst]
            new_files[f"{lv}/forest/{name}.forest4.json"] = ("\n".join(lines) + "\n").encode("utf-8")
        new_files[md_name] = json.dumps(managed, indent=1).encode("utf-8")
        sd = os.path.join(tmp, "art", "shapes", "trees")
        for f in sorted(os.listdir(sd)):
            new_files[f"{lv}/art/shapes/trees/{f}"] = open(os.path.join(sd, f), "rb").read()
        with zi.writer() as zo:
            for i in zi.infolist():
                if i.filename in new_files or FAR_FILE.search(i.filename):
                    continue
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                ctype = zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED
                zo.writestr(n, data, compress_type=ctype)
        counts = {k[0]: len(v) for k, v in items.items()}
        print("%d far trees %s" % (sum(counts.values()), counts))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
