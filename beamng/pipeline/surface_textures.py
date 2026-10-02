"""Original procedural textures of the unpaved and stone surfaces of the roads and paths (v2.4):
nothing here comes from a photograph.

The surfaces come from OpenStreetMap and swissTLM3D (osm_surface.py): gravel roads, earth paths,
granite setts and river cobbles in the nuclei. Each texture is drawn with numpy: the stones, their
shapes and sizes are invented from what these surfaces are made of (crushed granite and gneiss on
the gravel roads, earth with pebbles and leaf litter on the forest paths, rows of grey granite setts
about 10 cm wide, rounded river stones set close in earth or mortar: the "acciottolato" of the old
lanes); the tint of every surface is measured on the 10 cm orthophoto along the OSM ways with that
surface (MEASURED, outside shade and vegetation), its brightness is the material's (BRIGHTNESS).

Every texture tiles over TILE_M m: colour (*.color.png, sRGB), normal (*.normal.png, OpenGL), roughness
and ambient occlusion (*.data.png), written by build(dst) as t_road_<surface>_*.
    python surface_textures.py <folder>        (writes the textures there, plus a preview image)
"""
import os, sys
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from bld_textures import noise, aniso_noise, normal_map, ao_map, to8, save, lit

N = 1024                      # pixels of every texture
TILE_M = 2.0                  # metres covered by one texture (the uv tile of the materials)
SEED = 31
# tint of the surfaces: median sRGB on the 10 cm orthophoto (SWISSIMAGE) along the OSM ways tagged with
# them (60 ways each, every 0.5 m over 40 m), pixels in shade (mean < 70) and on vegetation (green above
# red and blue) left out. The orthophoto is brightened and compressed in the light tones (asphalt
# measures 162 there), so it gives the hue; the brightness (mean sRGB) is that of the material
# (crushed stone about 0.3 albedo, dry earth 0.15-0.2, granite 0.25)
MEASURED = {"gravel": (177.2, 176.4, 164.1), "dirt": (153.3, 149.6, 131.2), "sett": (174.8, 167.6, 160.2),
            "cobble": (173.3, 159.1, 148.7)}
BRIGHTNESS = {"gravel": 150.0, "dirt": 112.0, "sett": 138.0, "cobble": 140.0}


def target(surface):
    m = np.asarray(MEASURED[surface], np.float32)
    return m / m.mean() * BRIGHTNESS[surface]


def _domes(n, rng, count, r_px, aspect=(1.0, 1.6), embed=0.35):
    """Tileable field of round to oval stones: (height 0..1 above the matrix, stone id, -1 outside).
    count stones with radii uniform in r_px; each pixel belongs to the nearest centre (wrapped)."""
    P = rng.random((count, 2))
    r = rng.uniform(r_px[0], r_px[1], count) / n
    asp = rng.uniform(aspect[0], aspect[1], count)
    ang = rng.uniform(0, np.pi, count)
    tiles = np.concatenate([P + [dx, dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    t = cKDTree(tiles)
    g = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(g, g)
    _, i = t.query(np.column_stack([X.ravel(), Y.ravel()]), k=1)
    k = i % count
    d = np.column_stack([X.ravel(), Y.ravel()]) - tiles[i]
    c, s = np.cos(ang[k]), np.sin(ang[k])
    u = (d[:, 0] * c + d[:, 1] * s) / (r[k] * asp[k] ** 0.5)
    v = (-d[:, 0] * s + d[:, 1] * c) * asp[k] ** 0.5 / r[k]
    q = 1.0 - (u * u + v * v)
    h = np.where(q > 0, np.sqrt(np.clip(q, 0, 1)) - embed, -1.0) / (1.0 - embed)
    sid = np.where(h > 0, k, -1)
    return np.clip(h, 0, 1).reshape(n, n), sid.reshape(n, n)


def _fit_mean(col, target):
    """Colour scaled per channel so that its mean is the target (sRGB 0..255)."""
    m = col.reshape(-1, 3).mean(0)
    return np.clip(col * (np.asarray(target, np.float32) / 255.0 / np.maximum(m, 1e-6)), 0, 1)


def _write(dst, name, col, hgt, strength, rough, ao_r=4, ao_k=0.12):
    save(os.path.join(dst, f"{name}_b.color.png"), to8(col))
    save(os.path.join(dst, f"{name}_nm.normal.png"), normal_map(hgt, strength))
    save(os.path.join(dst, f"{name}_r.data.png"), to8(rough))
    save(os.path.join(dst, f"{name}_ao.data.png"), ao_map(hgt, ao_r, ao_k))


def gravel(dst, n=N):
    """Gravel road: compacted fines of crushed granite and gneiss with loose stones of three sizes
    (6-12, 12-22, 22-35 mm), lighter and darker grains, patches of finer and darker material."""
    rng = np.random.default_rng(SEED)
    mm = TILE_M * 1000 / n                                   # mm per pixel
    fine = noise(n, n, 0.7, rng)
    mid = noise(n, n, 5, rng)
    patch = noise(n, n, 50, rng)
    large = noise(n, n, 150, rng)
    hgt = 0.6 * fine + 1.2 * mid + 2.5 * patch                # mm, the matrix
    pal = np.array([[0.66, 0.65, 0.62], [0.70, 0.64, 0.54], [0.55, 0.55, 0.54], [0.42, 0.42, 0.41],
                    [0.78, 0.77, 0.74], [0.60, 0.55, 0.47]], np.float32)
    col = np.empty((n, n, 3), np.float32)
    col[:] = np.array([0.60, 0.58, 0.53]) * (1 + 0.10 * fine + 0.05 * mid)[..., None]
    # stones: count, radius (mm), height (mm)
    for count, (r0, r1), hmm in ((15000, (3.0, 6.0), 2.0), (1500, (6.0, 11.0), 4.0), (150, (11.0, 17.5), 7.0)):
        h, sid = _domes(n, rng, count, (r0 / mm, r1 / mm), aspect=(1.0, 1.8))
        on = sid >= 0
        tone = pal[rng.choice(len(pal), count, p=[0.3, 0.2, 0.2, 0.1, 0.1, 0.1])] * rng.uniform(0.88, 1.1, count)[:, None]
        sh = np.clip(lit(gaussian_filter(h, 1.0, mode="wrap"), 2.0), 0.7, 1.3)
        stone = tone[np.maximum(sid, 0)] * sh[..., None] * (1 + 0.06 * fine)[..., None]
        top = on & (hgt < 2.5 * patch + hmm * h)
        col[top] = stone[top]
        hgt = np.where(top, 2.5 * patch + hmm * h, hgt)
    col *= (1 - 0.05 * np.clip(patch, 0, None) + 0.04 * large)[..., None]
    col = _fit_mean(col, target("gravel"))
    _write(dst, "t_road_gravel", col, hgt, 1.6 / mm, 0.9 + 0.04 * fine, ao_r=3, ao_k=0.06)


def dirt(dst, n=N):
    """Earth of the paths and tracks: compacted soil with moisture patches, sparse pebbles, crumbs,
    leaf litter (chestnut and oak leaves) and a few twigs."""
    rng = np.random.default_rng(SEED + 1)
    mm = TILE_M * 1000 / n
    fine = noise(n, n, 0.8, rng)
    crumb = noise(n, n, 2.5, rng)
    mid = noise(n, n, 12, rng)
    patch = noise(n, n, 70, rng)
    hgt = 0.8 * fine + 1.5 * crumb + 3.0 * mid + 4.0 * patch
    earth = np.array([0.50, 0.42, 0.32], np.float32)
    col = earth * (1 + 0.08 * fine + 0.06 * crumb - 0.08 * np.clip(patch, 0, None) + 0.04 * mid)[..., None]
    # pebbles
    h, sid = _domes(n, rng, 220, (4 / mm, 11 / mm), aspect=(1.0, 1.7))
    on = sid >= 0
    tone = np.array([[0.52, 0.49, 0.44], [0.44, 0.42, 0.39], [0.56, 0.51, 0.43]], np.float32)[rng.integers(0, 3, 220)]
    sh = np.clip(lit(gaussian_filter(h, 1.0, mode="wrap"), 2.0), 0.7, 1.3)
    col[on] = (tone[np.maximum(sid, 0)] * sh[..., None])[on]
    hgt = np.where(on, hgt + 6.0 * h, hgt)
    # leaves: flat ellipses 3-7 cm long, brown, rust and dark
    g = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(g, g)
    leaf_c = np.array([[0.42, 0.31, 0.20], [0.48, 0.34, 0.20], [0.30, 0.23, 0.16], [0.45, 0.38, 0.26]], np.float32)
    for _ in range(110):
        cx, cy = rng.random(2)
        L = rng.uniform(30, 70) / (TILE_M * 1000)
        W = L * rng.uniform(0.28, 0.45)
        a = rng.uniform(0, np.pi)
        dx = (X - cx + 0.5) % 1.0 - 0.5
        dy = (Y - cy + 0.5) % 1.0 - 0.5
        u = (dx * np.cos(a) + dy * np.sin(a)) / L * 2
        v = (-dx * np.sin(a) + dy * np.cos(a)) / W * 2
        m = (np.abs(u) < 1.0) & (np.abs(v) < (1.0 - u * u) * (1.0 - 0.25 * u))   # pointed at both ends
        if not m.any():
            continue
        c = leaf_c[rng.integers(0, len(leaf_c))] * rng.uniform(0.85, 1.1)
        vein = np.abs(v[m]) < 0.08
        col[m] = c * (1 - 0.15 * vein)[:, None] * (1 + 0.05 * fine[m])[:, None]
        hgt[m] += 1.0
    # twigs: thin dark lines
    for _ in range(25):
        cx, cy = rng.random(2)
        L = rng.uniform(60, 180) / (TILE_M * 1000)
        a = rng.uniform(0, np.pi)
        t = np.linspace(-0.5, 0.5, 200) * L
        px = ((cx + t * np.cos(a)) % 1.0 * n).astype(int)
        py = ((cy + t * np.sin(a)) % 1.0 * n).astype(int)
        for o in (0, 1):
            col[(py + o) % n, px] = np.array([0.24, 0.18, 0.12])
            hgt[(py + o) % n, px] += 2.0
    col = _fit_mean(col, target("dirt"))
    _write(dst, "t_road_dirt", col, hgt, 1.2 / mm, 0.95 + 0.03 * fine, ao_r=4, ao_k=0.05)


def sett(dst, n=N):
    """Granite setts ("cubetti") in rows: about 10 cm stones of uneven width, bevelled edges, joints
    of dark sand; grey granite with black and white grains, a few stones darker or warmer."""
    rng = np.random.default_rng(SEED + 2)
    mm = TILE_M * 1000 / n
    rows = int(round(TILE_M / 0.10))
    joint = 9.0 / mm                                          # px
    bevel = 10.0 / mm
    stone_id = np.zeros((n, n), np.int32)
    edge = np.zeros((n, n), np.float32)
    ids = 0
    yy = np.arange(n)
    row_of = (yy * rows // n).astype(int)
    hgts = rng.uniform(0.9, 1.1, rows)
    row_edges = np.r_[0, np.cumsum(hgts)] / hgts.sum() * n
    tilt = []
    for r in range(rows):
        y0, y1 = row_edges[r], row_edges[r + 1]
        w = []
        while sum(w) < n:
            w.append(rng.uniform(0.08, 0.125) / TILE_M * n)
        w = np.array(w) * n / sum(w)
        x_edges = (np.r_[0, np.cumsum(w)] + rng.uniform(0, n)) % n
        sel = (yy >= y0) & (yy < y1)
        xs = np.arange(n)
        # stone of every column: the last edge at or before it (wrapped)
        order = np.argsort(x_edges[:-1])
        xe = x_edges[:-1][order]
        k = np.searchsorted(xe, xs, side="right") - 1
        k = np.where(k < 0, len(xe) - 1, k)
        left = xe[k]
        right = xe[(k + 1) % len(xe)]
        right = np.where(right <= left, right + n, right)
        xs_w = np.where(xs < left, xs + n, xs)
        dx = np.minimum(xs_w - left, right - xs_w)
        ys = yy[sel]
        dy = np.minimum(ys - y0, y1 - ys)
        e = np.minimum(dx[None, :], dy[:, None])
        stone_id[sel] = ids + order[k][None, :]
        edge[sel] = e
        ids += len(xe)
        tilt += list(rng.normal(0, 1, (len(xe), 2)))
    tilt = np.array(tilt)
    # outlines made irregular: the edge distance read through a small warp of the image
    from scipy.ndimage import map_coordinates
    wr, wc = 1.3 * noise(n, n, 10, rng), 1.3 * noise(n, n, 10, rng)
    rr, cc = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    edge = map_coordinates(edge, [(rr + wr) % n, (cc + wc) % n], order=1, mode="grid-wrap").astype(np.float32)
    stone_id = map_coordinates(stone_id, [(rr + wr) % n, (cc + wc) % n], order=0, mode="grid-wrap")
    inside = edge > joint / 2
    prof = np.clip((edge - joint / 2) / bevel, 0, 1)
    prof = prof * (2 - prof)                                  # rounded bevel
    fine = noise(n, n, 0.7, rng)
    grain = noise(n, n, 2.0, rng)
    # every stone a little higher or lower than its neighbours
    hgt = np.where(inside, (6.0 + 0.8 * tilt[stone_id, 0]) * prof + 0.5 * fine, -2.0 + 0.6 * fine)
    nst = ids
    tone = rng.uniform(0.80, 1.14, nst)
    warm = rng.random(nst) < 0.18
    base = np.array([0.55, 0.55, 0.54], np.float32)
    col = np.empty((n, n, 3), np.float32)
    col[:] = base * tone[stone_id][..., None]
    col[warm[stone_id]] *= np.array([1.06, 1.0, 0.92])
    mica = rng.random((n, n)) < 0.05
    feld = rng.random((n, n)) < 0.06
    col[mica] *= 0.55
    col[feld] = np.minimum(col[feld] * 1.35, 1.0)
    col *= (1 + 0.05 * grain)[..., None]
    # worn tops slightly darker and smoother, joints dark sand, a faint stain pattern
    wear = noise(n, n, 60, rng)
    col *= (1 - 0.06 * prof * np.clip(wear, 0, None))[..., None]
    sh = np.clip(lit(gaussian_filter(hgt, 1.2, mode="wrap"), 0.25), 0.75, 1.25)
    col *= sh[..., None]
    sand = np.array([0.36, 0.34, 0.30], np.float32) * (1 + 0.1 * fine[~inside])[:, None]
    col[~inside] = sand
    col *= (1 + 0.04 * noise(n, n, 160, rng))[..., None]
    rough = np.where(inside, 0.72 + 0.06 * fine - 0.05 * prof, 0.95)
    _write(dst, "t_road_sett", _fit_mean(np.clip(col, 0, 1), target("sett")), hgt, 0.9 / mm, rough, ao_r=5, ao_k=0.10)


def cobble(dst, n=N):
    """River cobbles ("acciottolato"): rounded stones 6-14 cm, elongated along their row, set close in
    earth and mortar; mostly grey gneiss and granite, some light, dark or ochre."""
    rng = np.random.default_rng(SEED + 3)
    mm = TILE_M * 1000 / n
    rows = int(round(TILE_M / 0.07))
    flat = 1.7
    pts = []
    for r in range(rows):
        k = int(round(TILE_M / (0.07 * flat) * rng.uniform(0.9, 1.1)))
        xs = (np.arange(k) + rng.uniform(0, 1) + rng.uniform(-0.25, 0.25, k)) / k
        ys = (r + 0.5 + rng.uniform(-0.22, 0.22, k)) / rows
        pts += list(zip(xs % 1.0, ys % 1.0))
    P = np.array(pts)
    k = len(P)
    tiles = np.concatenate([P + [dx, dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    S = tiles * [1.0, flat]
    t = cKDTree(S)
    nn, _ = t.query(S[4 * k:5 * k], k=2)                      # the middle copy: distance to the nearest stone
    rad = 0.5 * nn[:, 1] * rng.uniform(0.92, 1.08, k)
    g = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(g, g)
    wob = 0.003                                               # irregular outlines
    Xw = X + wob * noise(n, n, 12, rng)
    Yw = Y + wob * noise(n, n, 12, rng)
    d, i = t.query(np.column_stack([Xw.ravel(), Yw.ravel() * flat]), k=1)
    sid = (i % k).reshape(n, n)
    q = 1.0 - (d.reshape(n, n) / rad[sid]) ** 2
    inside = q > 0
    dome = np.sqrt(np.clip(q, 0, 1))
    fine = noise(n, n, 0.8, rng)
    hgt = np.where(inside, 12.0 * dome + 0.4 * fine, 0.8 * fine)
    pal = np.array([[0.56, 0.56, 0.54], [0.66, 0.65, 0.62], [0.60, 0.57, 0.51], [0.42, 0.42, 0.41],
                    [0.51, 0.52, 0.49], [0.58, 0.53, 0.46]], np.float32)
    pick = rng.choice(len(pal), k, p=[0.32, 0.16, 0.14, 0.16, 0.14, 0.08])
    tone = rng.uniform(0.9, 1.08, k)
    col = pal[pick][sid] * tone[sid][..., None]
    band = aniso_noise(n, n, 1.0, 10.0, rng)                  # veins of the gneiss
    col *= (1 + 0.05 * fine + 0.04 * band)[..., None]
    sh = np.clip(lit(gaussian_filter(hgt, 1.5, mode="wrap"), 0.12), 0.75, 1.25) * (0.80 + 0.20 * dome)
    col *= sh[..., None]
    earth = np.array([0.40, 0.37, 0.32], np.float32) * (1 + 0.1 * fine[~inside])[:, None]
    col[~inside] = earth
    moss = (noise(n, n, 18, rng) > 1.4) & ~inside
    col[moss] = np.array([0.31, 0.34, 0.24]) * (1 + 0.1 * fine[moss])[:, None]
    col *= (1 + 0.04 * noise(n, n, 150, rng))[..., None]
    rough = np.where(inside, 0.62 + 0.05 * fine, 0.95)
    _write(dst, "t_road_cobble", _fit_mean(np.clip(col, 0, 1), target("cobble")), hgt, 0.8 / mm, rough, ao_r=6, ao_k=0.09)


SURFACES = ("gravel", "dirt", "sett", "cobble")


def build(dst):
    """All the textures into dst (names t_road_<surface>_b.color.png ...)."""
    for f in (gravel, dirt, sett, cobble):
        f(dst)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    build(out)
    from PIL import Image
    ims = [Image.open(os.path.join(out, f"t_road_{s}_b.color.png")).resize((512, 512)) for s in SURFACES]
    sheet = Image.new("RGB", (512 * len(ims), 512))
    for k, im in enumerate(ims):
        sheet.paste(im.convert("RGB"), (512 * k, 0))
    sheet.save(os.path.join(out, "surfaces_preview.jpg"), quality=88)
