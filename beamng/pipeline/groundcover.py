"""Grass and meadow flowers on the terrain (v2.4): a BeamNG GroundCover of small clumps around the
camera, on the terrain layers of the meadows and the gardens (terrain.py).

Nothing here comes from a photograph: the blades and the flowers are drawn with numpy (blades
tapering and bending, darker at the base, some dry ones; daisies, buttercups, meadow sage and clover,
the flowers of the hay meadows of the area), their mean colour is the grass colour measured on the
orthophoto (terrain_colors.json), and the clumps are three crossed quads (6 triangles).

The density, the radius around the camera and the share of flowers are guesses, kept low for the
frame rate and set by the constants below; no grass within a terrain square of the roads and paths
(terrain.NO_COVER: the verges keep the look of the meadow without the clumps, which would stand
through the road meshes). The GroundCover format could not be tried in the game here.
"""
import json, os
import numpy as np
from scipy.ndimage import gaussian_filter
import bng
from bld_textures import to8, save

RADIUS = 50.0               # m around the camera
DISSOLVE = 35.0             # m, the clumps fade out from here to RADIUS
MAX_ELEMENTS = 40000        # clumps around the camera (all types)
GRID = 7                    # cells of the cover per side
SEED = 41
# type: (shape, terrain layer, probability, size min, size max, clumps min, max, clump radius m)
TYPES = [
    ("gc_grass_a", "Grass", 1.0, 0.75, 1.25, 1, 3, 0.45),
    ("gc_grass_b", "Grass", 0.35, 0.8, 1.3, 1, 2, 0.6),
    ("gc_flowers", "Grass", 0.12, 0.8, 1.15, 1, 3, 0.5),
    ("gc_grass_short", "GardenGrass", 0.6, 0.6, 1.0, 1, 2, 0.4),
]
SHAPES = {                   # width, height (m) of the clump at size 1; texture
    "gc_grass_a": (0.55, 0.42, "gc_grass"), "gc_grass_b": (0.7, 0.65, "gc_grass"),
    "gc_grass_short": (0.45, 0.22, "gc_grass"), "gc_flowers": (0.5, 0.48, "gc_flowers"),
}


def _blades(img, rng, n_blades, color, dry_share=0.06, size=512):
    """Blades of grass painted into an RGBA float image (rows down), from the bottom edge up."""
    H, W = img.shape[:2]
    for _ in range(n_blades):
        x0 = rng.uniform(0.08, 0.92) * W
        h = rng.uniform(0.45, 0.98) * H
        bend = rng.normal(0, 0.12) * W
        w0 = rng.uniform(3.0, 7.0) * W / size
        dry = rng.random() < dry_share
        base = np.array([0.20, 0.27, 0.10]) if not dry else np.array([0.36, 0.34, 0.18])
        tip = np.asarray(color) * rng.uniform(0.85, 1.2) if not dry else np.array([0.55, 0.50, 0.28])
        t = np.linspace(0, 1, int(h))
        xs = x0 + bend * t ** 2
        ys = H - 1 - t * h
        ws = w0 * (1 - t) + 0.6
        for k in range(len(t)):
            r = int(ys[k])
            if r < 0 or r >= H:
                continue
            c0, c1 = int(max(xs[k] - ws[k] / 2, 0)), int(min(xs[k] + ws[k] / 2 + 1, W))
            if c1 <= c0:
                continue
            col = base * (1 - t[k]) + tip * t[k]
            shade = 0.85 + 0.3 * (np.arange(c0, c1) - xs[k] + ws[k] / 2) / max(ws[k], 1)
            img[r, c0:c1, :3] = col[None, :] * shade[:, None]
            img[r, c0:c1, 3] = 1.0


def _flower(img, rng, cx, cy, kind, size=512):
    H, W = img.shape[:2]
    rr, cc = np.ogrid[:H, :W]
    s = W / size
    if kind == "daisy":
        petals = np.array([0.95, 0.95, 0.92])
        for a in np.linspace(0, 2 * np.pi, 12, endpoint=False):
            px, py = cx + 7 * s * np.cos(a), cy + 3.5 * s * np.sin(a)
            m = (cc - px) ** 2 / (4 * s) ** 2 + (rr - py) ** 2 / (2 * s) ** 2 < 1
            img[m, :3] = petals * rng.uniform(0.9, 1.0)
            img[m, 3] = 1
        m = (cc - cx) ** 2 + ((rr - cy) * 1.8) ** 2 < (3.2 * s) ** 2
        img[m, :3] = [0.92, 0.75, 0.15]
        img[m, 3] = 1
    else:
        colr = {"buttercup": [0.95, 0.80, 0.10], "sage": [0.42, 0.30, 0.65], "clover": [0.80, 0.45, 0.60],
                "bell": [0.45, 0.50, 0.80]}[kind]
        r = {"buttercup": 4.5, "sage": 4.0, "clover": 5.0, "bell": 4.0}[kind] * s
        elong = 2.2 if kind == "sage" else 1.0
        m = ((cc - cx) / r) ** 2 + ((rr - cy) / (r * elong)) ** 2 < 1
        shade = 0.8 + 0.4 * rng.random(int(m.sum()))
        img[m, :3] = np.asarray(colr)[None, :] * shade[:, None]
        img[m, 3] = 1


def _fit_opaque(img, target):
    """Colour of the opaque pixels scaled to a mean (sRGB 0..255)."""
    m = img[..., 3] > 0.5
    mean = img[m, :3].mean(0)
    img[m, :3] = np.clip(img[m, :3] * (np.asarray(target) / 255.0 / np.maximum(mean, 1e-6)), 0, 1)


def textures(dst, grass_rgb):
    """gc_grass (blades) and gc_flowers (blades with flowers): RGBA, alpha cut-out."""
    rng = np.random.default_rng(SEED)
    n = 512
    g = np.zeros((n, n, 4), np.float32)
    _blades(g, rng, 260, (0.42, 0.55, 0.22))
    _fit_opaque(g, grass_rgb)
    save(os.path.join(dst, "gc_grass_b.color.png"), to8(g))
    f = np.zeros((n, n, 4), np.float32)
    _blades(f, rng, 160, (0.42, 0.55, 0.22))
    _fit_opaque(f, grass_rgb)
    kinds = ["daisy", "buttercup", "sage", "clover", "bell"]
    for _ in range(26):
        kind = kinds[rng.choice(len(kinds), p=[0.32, 0.26, 0.2, 0.12, 0.1])]
        cx, cy = rng.uniform(0.1, 0.9) * n, rng.uniform(0.08, 0.5) * n
        # the stem down to the bottom
        x = int(cx)
        f[int(cy):, max(x - 1, 0):x + 1, :3] = [0.25, 0.36, 0.14]
        f[int(cy):, max(x - 1, 0):x + 1, 3] = 1
        _flower(f, rng, cx, cy, kind)
    save(os.path.join(dst, "gc_flowers_b.color.png"), to8(f))


def clump(width, height):
    """Three crossed vertical quads (6 triangles) standing on (0, 0, 0); normals up, so the clumps
    take the light of the ground."""
    V, UV = [], []
    for a in (0.0, np.pi / 3, 2 * np.pi / 3):
        dx, dy = 0.5 * width * np.cos(a), 0.5 * width * np.sin(a)
        p = [(-dx, -dy, 0), (dx, dy, 0), (dx, dy, height), (-dx, -dy, height)]
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for i in (0, 1, 2, 0, 2, 3):
            V.append(p[i])
            UV.append(uv[i])
    V = np.array(V, np.float64)
    return V, np.array(UV, np.float64), np.repeat([[0.0, 0.0, 1.0]], len(V), 0)


def build(level_dir, level_name, scene, group="MissionGroup/level_objects/vegetation"):
    """Textures, shapes, materials and the GroundCover object; returns the counts for the log."""
    from config import WORK
    colors = json.load(open(os.path.join(WORK, "terrain_colors.json")))
    d = os.path.join(level_dir, "art", "shapes", "groundcover")
    os.makedirs(d, exist_ok=True)
    textures(d, colors.get("Grass", [104, 126, 85]))
    L = f"/levels/{level_name}/art/shapes/groundcover"
    mats = [bng.material(m, f"{L}/{m}_b.color.png", alpha_test=90, double_sided=True, roughness=0.95)
            for m in ("gc_grass", "gc_flowers")]
    bng.write_materials(os.path.join(d, "main.materials.json"), mats)
    for name, (w, h, tex) in SHAPES.items():
        mb = bng.MeshBuilder()
        V, UV, N = clump(w, h)
        mb.add(tex, V, uvs=UV, normals=N)
        mb.write_dae(os.path.join(d, f"{name}.dae"), name=name)
    types = []
    for shape, layer, prob, smin, smax, cmin, cmax, crad in TYPES:
        types.append({"layer": layer, "invertLayer": False, "probability": prob,
                      "shapeFilename": f"{L}/{shape}.dae", "billboardUVs": [0, 0, 1, 1],
                      "sizeMin": smin, "sizeMax": smax, "sizeExponent": 1, "windScale": 0.6,
                      "maxSlope": 40, "minElevation": -1000, "maxElevation": 5000,
                      "minClumpCount": cmin, "maxClumpCount": cmax, "clumpExponent": 1, "clumpRadius": crad})
    scene.add(group, {"name": "grass_cover", "class": "GroundCover", "persistentId": bng.pid(),
                      "position": [0, 0, 0], "material": "gc_grass", "radius": RADIUS,
                      "dissolveRadius": DISSOLVE, "reflectScale": 0.25, "gridSize": GRID, "zOffset": 0,
                      "seed": SEED, "maxElements": MAX_ELEMENTS, "maxBillboardTiltAngle": 90,
                      "shapeCullRadius": RADIUS, "shapesCastShadows": False, "Types": types})
    return {"types": len(types), "max_elements": MAX_ELEMENTS, "radius_m": RADIUS,
            "triangles_per_clump": 6}


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    textures(out, (104, 126, 85))
