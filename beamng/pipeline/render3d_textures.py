"""Stand-ins for the game's own textures in the renders of render3d.py (v3.0).

Since v3.0 the level draws its asphalt, its stone walls and cobbles and the wear of its roads on textures of the
game (Italy's asphalt, medieval stone wall, cobblestones and old concrete, the tyre tracks, the light and dark
patches and the cracks Italy lays over its roads: /levels/italy/..., /assets/..., /art/...). Those files are not
here without the game, and render3d drew every such surface in one flat colour and the overlays not at all: what
the game shows on a road could not be judged from a render. Here every such texture gets an original procedural
stand-in of the same kind and layout, chosen by the file's base name (KINDS):
- the same metres per repeat as the uv tiles of the meshes (italy_mats.ASPHALT_TILE for the asphalt,
  italy_mats.STONE_TILE for the stone wall, surface_textures.TILE_M for the setts and cobbles, 1 m for the chain
  link), so grains, stones and joints have their size on the ground;
- the overlays as the strips road_wear.py lays them (u across the band, v along the road, about four times longer
  than wide), their opacity in alpha;
- a normal map where the relief shows (stones, setts, cobbles, grain of the asphalt and concrete).
Nothing comes from the game: the look is not Italy's, the kind of surface, its scale and its tiling are.
Drawn once with numpy (about a minute) into WORK/render3d_textures/<VERSION>; render3d reads them from there.

    colour(ref) -> path of the stand-in (RGBA PNG, sRGB) of a texture path of the game, or None
    normal(ref) -> path of its normal map (OpenGL convention), or None
"""
import os
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from config import WORK
from bld_textures import noise, aniso_noise, normal_map, to8, lit, coursed_stones

VERSION = "v1"
CACHE = os.path.join(WORK, "render3d_textures", VERSION)
SEED = 73
ASPHALT_M = 4.0               # m per repeat: italy_mats.ASPHALT_TILE
STONE_M = 3.0                 # italy_mats.STONE_TILE
STONE_SURFACE_M = 2.0         # surface_textures.TILE_M: setts, cobbles, gravel
# base name of the game's texture (substring, lower case) -> stand-in; the first match wins. The macro and detail
# maps, the trees and the vanilla models' own textures have none (drawn as before: flat colours, proxies)
KINDS = [("asphalt_trackwear", "track"), ("asphalt_variation", "variation"), ("asphalt_decayed", "cracks"),
         ("damaged_edge", "edge_damage"), ("line_yellow", "line_yellow"), ("line_white", "line"), ("line_", "line"),
         ("macro", None), ("detail", None), ("asphalt", "asphalt"), ("medieval_stone_wall", "stone_wall"),
         ("cobblestone_patterned", "setts"), ("cobblestone", "cobbles"), ("sidewalk_tiles", "slabs"),
         ("concrete_sidewalk", "slabs"), ("chainlink", "chainlink"), ("concrete", "concrete"), ("curb", "concrete"),
         ("gravel", "gravel")]


def kind(ref):
    """The stand-in of a texture path (None: none)."""
    if not isinstance(ref, str) or not ref:
        return None
    base = ref.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for sub, k in KINDS:
        if sub in base:
            return k
    return None


def colour(ref):
    k = kind(ref)
    return _files(k)[0] if k else None


def normal(ref):
    k = kind(ref)
    return _files(k)[1] if k else None


def _files(k):
    c, n = os.path.join(CACHE, f"{k}.color.png"), os.path.join(CACHE, f"{k}.normal.png")
    if not os.path.exists(c):
        os.makedirs(CACHE, exist_ok=True)
        rgba, hgt, strength = GENERATORS[k]()
        _save(c, to8(rgba))
        if hgt is not None:
            _save(n, normal_map(hgt, strength))
    return c, (n if os.path.exists(n) else None)


def _save(path, a):
    tmp = path + f".{os.getpid()}.tmp.png"
    Image.fromarray(a).save(tmp)
    os.replace(tmp, path)


def _rgba(col, alpha=None):
    col = np.clip(np.asarray(col, np.float32), 0, 1)
    a = np.ones(col.shape[:2], np.float32) if alpha is None else np.clip(alpha, 0, 1)
    return np.dstack([col, a])


def _fit(v, mean):
    """Grey levels scaled so that their mean is `mean` (sRGB 0..1)."""
    return v * (mean / max(float(v.mean()), 1e-6))


def _walk(n_h, n_w, count, length_px, rng, turn=0.25, start=None, heading=None):
    """Thin meandering lines (random walks) on a tileable grid: float mask 0/1."""
    g = np.zeros((n_h, n_w), np.float32)
    for k in range(count):
        y, x = (rng.uniform(0, n_h), rng.uniform(0, n_w)) if start is None else start[k]
        a = rng.uniform(0, 2 * np.pi) if heading is None else heading + rng.normal(0, 0.3)
        for _ in range(int(length_px)):
            a += rng.normal(0, turn)
            x, y = (x + np.cos(a)) % n_w, (y + np.sin(a)) % n_h
            g[int(y), int(x)] = 1.0
    return g


# ---------------------------------------------------------------------------------------------- surfaces
def asphalt(n=1024):
    """Italy's asphalt: an even, fairly light wearing course (mean sRGB about 150 at a colour factor of 1, as
    italy_mats measures it), fine grain of crushed stone with a few light and dark chips, faint blotches."""
    rng = np.random.default_rng(SEED)
    px = n / ASPHALT_M
    fine = noise(n, n, 0.6, rng)
    mid = noise(n, n, 2.5, rng)
    blot = noise(n, n, 0.3 * px, rng)
    big = noise(n, n, 1.0 * px, rng)
    chips = rng.random((n, n))
    light, dark = chips > 0.975, chips < 0.02
    v = 1.0 + 0.10 * fine + 0.05 * mid + 0.025 * blot + 0.015 * big + 0.22 * light - 0.16 * dark
    v = gaussian_filter(v, 0.45, mode="wrap")
    v = _fit(v, 150 / 255)
    col = v[..., None] * np.array([1.0, 1.0, 1.015], np.float32)
    hgt = 0.8 * fine + 0.6 * mid + 1.2 * light
    return _rgba(col), hgt, 0.35


def concrete(n=1024):
    """Old concrete: light grey, a little warm, with weathered stains over metres, pores, a few hairline cracks."""
    rng = np.random.default_rng(SEED + 1)
    fine = noise(n, n, 0.7, rng)
    mid = noise(n, n, 6, rng)
    stain = noise(n, n, n / 10, rng)
    streak = aniso_noise(n, n, n / 12, n / 80, rng)
    pores = rng.random((n, n)) < 0.006
    crack = gaussian_filter(_walk(n, n, 5, n * 0.5, rng, turn=0.18), 0.7, mode="wrap")
    crack = np.clip(crack / max(float(crack.max()), 1e-6) * 2.5, 0, 1)
    v = (1.0 + 0.05 * fine + 0.035 * mid - 0.05 * np.clip(stain - 0.2, 0, None) + 0.02 * streak
         - 0.25 * gaussian_filter(pores.astype(np.float32), 0.6, mode="wrap") * 4 - 0.22 * crack)
    v = _fit(v, 0.64)
    col = v[..., None] * np.array([1.0, 0.985, 0.955], np.float32)
    hgt = 0.6 * fine + 0.4 * mid - 2.0 * pores - 1.5 * crack
    return _rgba(col), hgt, 0.5


def stone_wall(n=1024):
    """Italy's medieval stone wall: light grey limestone and gneiss rubble in rough courses (stones 0.2-0.6 m),
    darker grey joints, little colour; tileable over STONE_M m (bld_textures.coursed_stones)."""
    rng = np.random.default_rng(SEED + 2)
    ids, dist, joint, px = coursed_stones(n, rng, tile_m=STONE_M, h_rng=(0.16, 0.34), w_rng=(0.25, 0.65))
    k = int(ids.max()) + 2
    palette = np.array([[0.66, 0.65, 0.62], [0.72, 0.71, 0.68], [0.60, 0.59, 0.57], [0.68, 0.65, 0.60],
                        [0.56, 0.56, 0.55], [0.76, 0.75, 0.72]], np.float32)
    pick = rng.choice(len(palette), k, p=[0.3, 0.2, 0.18, 0.12, 0.12, 0.08])
    tone = rng.uniform(0.88, 1.08, k)
    base = palette[pick][ids] * tone[ids][..., None]
    g1, g2, g3 = noise(n, n, 0.8, rng), noise(n, n, 4, rng), noise(n, n, 30, rng)
    dome = np.clip(dist / (0.03 * px), 0, 1) ** 0.6
    hgt = dome * 5.0 + 0.5 * g1 + 0.8 * g2
    hgt[joint] = -2.0 + 0.4 * g1[joint]
    shade = np.clip(lit(gaussian_filter(hgt, 1.2, mode="wrap"), 0.3), 0.8, 1.15) * (0.78 + 0.22 * dome)
    col = base * (1 + 0.05 * g1 + 0.06 * g2 + 0.04 * g3)[..., None] * shade[..., None]
    col[joint] = np.array([0.40, 0.39, 0.37]) * (0.85 + 0.2 * np.clip(g2[joint], -1, 1))[:, None]
    return _rgba(col), hgt, 1.0


def _surface(name):
    """A stone surface of surface_textures.py (the pipeline's own setts, cobbles, gravel of v2.4), drawn there
    over the same TILE_M: (colour, height from its normal map is not needed: the normal map is copied)."""
    import surface_textures as st
    tmp = os.path.join(CACHE, f"_{name}_{os.getpid()}")
    os.makedirs(tmp, exist_ok=True)
    getattr(st, name)(tmp)
    col = np.asarray(Image.open(os.path.join(tmp, f"t_road_{name}_b.color.png")).convert("RGB"), np.float32) / 255
    nrm = os.path.join(tmp, f"t_road_{name}_nm.normal.png")
    out = os.path.join(CACHE, {"sett": "setts", "cobble": "cobbles"}.get(name, name) + ".normal.png")
    os.replace(nrm, out)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    return _rgba(col), None, 0


def setts():
    return _surface("sett")


def cobbles():
    return _surface("cobble")


def gravel():
    return _surface("gravel")


def slabs(n=1024, k=5):
    """Pavement slabs: k x k light concrete slabs per repeat, thin dark joints, each slab its own tone."""
    rng = np.random.default_rng(SEED + 3)
    yy, xx = np.mgrid[0:n, 0:n]
    cell = (yy * k // n) * k + (xx * k // n)
    tone = rng.uniform(0.92, 1.06, k * k)[cell]
    s = n / k
    edge = np.minimum(np.minimum(yy % s, s - 1 - yy % s), np.minimum(xx % s, s - 1 - xx % s))
    joint = edge < 2.0
    fine = noise(n, n, 0.7, rng)
    v = 0.66 * tone * (1 + 0.04 * fine + 0.02 * noise(n, n, 20, rng))
    v = np.where(joint, 0.36, v)
    hgt = np.where(joint, -3.0, np.clip(edge / 4.0, 0, 1)) + 0.3 * fine
    return _rgba(v[..., None] * np.array([1.0, 0.99, 0.97])), hgt, 0.6


def chainlink(n=256, cells=20, wire=1.6):
    """Chain-link mesh: diamonds of 1/cells m (one repeat a metre), galvanised wire, the holes transparent."""
    yy, xx = (np.mgrid[0:n, 0:n] + 0.5) * cells / n
    a, b = (xx + yy) % 1.0, (xx - yy) % 1.0
    d = np.minimum(np.minimum(a, 1 - a), np.minimum(b, 1 - b)) * n / cells
    alpha = np.clip(wire - d, 0, 1)
    col = np.zeros((n, n, 3), np.float32) + np.array([0.62, 0.64, 0.62])
    return _rgba(col * (0.85 + 0.15 * np.clip(1 - d / wire, 0, 1))[..., None], alpha), None, 0


# ---------------------------------------------------------------------------------------------- overlays
def _fade_u(w, edge=0.12):
    """Opacity across a strip: 0 at both sides, 1 inside (the strips must not show their edges)."""
    u = (np.arange(w) + 0.5) / w
    return np.clip(np.minimum(u, 1 - u) / edge, 0, 1)[None, :] ** 1.5


def track(w=256, h=1024):
    """Tyre tracks (m_asphalt_trackwear): two darker, polished bands about the middle of the strip, patchy along
    it; opacity near 1 in the tracks (the material's factors bring it to about a third)."""
    rng = np.random.default_rng(SEED + 10)
    u = (np.arange(w) + 0.5) / w
    across = np.exp(-((u - 0.5 + 0.3) / 0.09) ** 2) + np.exp(-((u - 0.5 - 0.3) / 0.09) ** 2)
    along = aniso_noise(h, w, h / 10, w / 12, rng)
    fine = noise(h, w, 1.0, rng)
    a = np.clip(across[None, :] * (0.85 + 0.15 * along) * (1 + 0.08 * fine), 0, 1)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.17, 0.17, 0.175]) * (1 + 0.08 * fine)[..., None]
    return _rgba(col, a), None, 0


def variation(w=256, h=2048):
    """Light and dark patches over the whole carriageway (italy_asphalt_overlay_light): metres long blotches,
    the light ones dusty and ravelled, the dark ones bitumen-rich; transparent between them and at the sides."""
    rng = np.random.default_rng(SEED + 11)
    p = aniso_noise(h, w, h / 40, w / 6, rng)
    q = noise(h, w, 2.0, rng)
    lightm = np.clip((p - 0.5) / 0.8, 0, 1)
    darkm = np.clip((-p - 0.6) / 0.8, 0, 1)
    a = np.clip(0.75 * lightm + 0.6 * darkm, 0, 1) * (0.85 + 0.15 * q) * _fade_u(w, 0.2)
    col = np.where((lightm > darkm)[..., None], np.array([0.66, 0.65, 0.62]), np.array([0.27, 0.27, 0.28]))
    col = col * (1 + 0.05 * q)[..., None]
    return _rgba(col, a), None, 0


def cracks(w=512, h=2048):
    """Cracked and patched asphalt (italy_road_cracks): alligator cracking in a few zones, long cracks along the
    road, darker rectangular patches of new asphalt with lighter seams; transparent elsewhere."""
    rng = np.random.default_rng(SEED + 12)
    # alligator cracks: the edges of small cells (about 0.2 m on a 4 m strip) inside the cracked zones
    P = rng.random((1600, 2)) * [h, w]
    tiles = np.concatenate([P + [dy * h, dx * w] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    yy, xx = np.mgrid[0:h, 0:w]
    d, _ = cKDTree(tiles).query(np.column_stack([yy.ravel(), xx.ravel()]), k=2)
    edge = (d[:, 1] - d[:, 0]).reshape(h, w)
    zone = aniso_noise(h, w, h / 18, w / 5, rng) > 0.35
    net = (edge < 1.6) & zone
    longc = _walk(h, w, 6, h * 0.6, rng, turn=0.08, heading=np.pi / 2) > 0
    crack = gaussian_filter((net | longc).astype(np.float32), 0.6, mode="wrap")
    crack = np.clip(crack * 2.5, 0, 1)
    # patches: rectangles of new asphalt
    patch = np.zeros((h, w), bool)
    seam = np.zeros((h, w), bool)
    for _ in range(5):
        y0, x0 = rng.uniform(0, h), rng.uniform(0.1, 0.6) * w
        ph, pw = rng.uniform(0.04, 0.12) * h, rng.uniform(0.2, 0.45) * w
        m = (((yy - y0) % h) < ph) & (xx >= x0) & (xx < x0 + pw)
        inner = (((yy - y0 - 3) % h) < ph - 6) & (xx >= x0 + 3) & (xx < x0 + pw - 3)
        patch |= m
        seam |= m & ~inner
    q = noise(h, w, 1.2, rng)
    a = np.maximum(0.95 * crack, np.where(patch, 0.8, 0.0))
    a = np.clip(a * (0.9 + 0.1 * q), 0, 1) * _fade_u(w, 0.08)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.31, 0.31, 0.32]) * (1 + 0.06 * q)[..., None]
    col[seam] = [0.40, 0.40, 0.40]
    col = col * (1 - 0.65 * crack)[..., None]
    return _rgba(col, a), None, 0


def edge_damage(w=256, h=2048):
    """A crumbled road edge (t_thin_damaged_edge): broken asphalt and grit at u = 0, ragged towards the road."""
    rng = np.random.default_rng(SEED + 13)
    u = (np.arange(w) + 0.5) / w
    lim = 0.35 + 0.2 * aniso_noise(h, 1, h / 60, 0.5, rng)[:, :1] + 0.06 * noise(h, w, 2, rng)
    a = np.clip((lim - u[None, :]) / 0.05, 0, 1)
    q = noise(h, w, 0.8, rng)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.52, 0.49, 0.44]) * (1 + 0.1 * q)[..., None]
    return _rgba(col, a), None, 0


def line(w=64, h=512, rgb=(0.92, 0.92, 0.90)):
    """A painted line: the paint across the middle of the strip, ragged at its sides, a little worn."""
    rng = np.random.default_rng(SEED + 14)
    u = (np.arange(w) + 0.5) / w
    rag = 0.03 * aniso_noise(h, w, 4, 1, rng)
    a = np.clip((0.42 - np.abs(u[None, :] - 0.5) + rag) / 0.03, 0, 1) * (0.88 + 0.12 * np.clip(noise(h, w, 2, rng), -1, 1))
    return _rgba(np.zeros((h, w, 3)) + np.asarray(rgb), a), None, 0


def line_yellow():
    return line(rgb=(0.92, 0.74, 0.16))


GENERATORS = {"asphalt": asphalt, "concrete": concrete, "stone_wall": stone_wall, "setts": setts, "cobbles": cobbles,
              "gravel": gravel, "slabs": slabs, "chainlink": chainlink, "track": track, "variation": variation,
              "cracks": cracks, "edge_damage": edge_damage, "line": line, "line_yellow": line_yellow}


if __name__ == "__main__":
    # python render3d_textures.py [out.jpg]: all the stand-ins on one sheet
    import sys
    tiles = []
    for k in GENERATORS:
        im = Image.open(_files(k)[0]).convert("RGBA")
        bg = Image.new("RGBA", im.size, (110, 110, 112, 255))
        tiles.append(Image.alpha_composite(bg, im).convert("RGB").resize((256, 256)))
    sheet = Image.new("RGB", (256 * 7, 256 * 2))
    for i, t in enumerate(tiles):
        sheet.paste(t, (256 * (i % 7), 256 * (i // 7)))
    sheet.save(sys.argv[1] if len(sys.argv) > 1 else os.path.join(CACHE, "sheet.jpg"), quality=88)
