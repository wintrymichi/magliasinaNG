"""Textures of the vine rows (v3.0, vineyards.py), drawn here: nothing from a photograph.

Two atlases of 1024 x 1024 px, each with a colour map (sRGB), an opacity map (the game ignores the alpha of
the colour map: without an opacityMap the cards of v2.4 were drawn as full rectangles, the transparent black
texels as dark blotches) and, for the leaves, a normal map (OpenGL, green up the image). Rows of the image
from the bottom (v = 0, as the meshes' texture coordinates):

leaves (t_vine_leaf): Merlot leaves in October, palmate with five lobes, 12-18 cm, most of them green, some
yellowing, a few turning rust and red, every leaf its own tilt in the normal map, a slightly different
shade per vine (two vines a tile).
  FAR    v 0     - 0.125   the far wall: 4 m along the row, the colours of the side band blurred, almost solid
  CLUMP  v 0.125 - 0.375   four clumps of shoots (0.8 m x 1.25 m) for the cards crossing the wall
  TOP    v 0.375 - 0.5625  the top of the wall seen from above, 2 m x 0.6 m, ragged on both long edges
  SIDE   v 0.5625- 1       the face of the wall, 2 m x 1.1 m, ragged at the top (shoot tips) and bottom
wood (t_vine_wood):
  SOLID  v 0     - 0.25    chestnut wood (u 0-0.5), concrete (u 0.5-0.75), galvanised steel (u 0.75-1)
  STRIP  v 0.25  - 0.5     the bare earth under the row, 4 m x 0.8 m, grassy ragged edges
  BAND   v 0.5   - 1       one span between two posts, from 5 cm under the ground to 1.0 m: the post (at
                           u = 0), six twisted trunks with their cordon arms, the fruiting wire, shoots,
                           purple grape bunches, the lowest leaves of the wall
Each region holds PAD transparent texel rows at its edges; the meshes map inside them (REGION).
    python vine_textures.py <folder>      (writes the textures and a preview there)
"""
import os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt
from bld_textures import noise, to8, save

N = 1024
PAD = 4
SEED = 73
# region -> (v0, v1) of the atlas, with PAD rows inside
LEAF_REGIONS = {"far": (0, 128), "clump": (128, 384), "top": (384, 576), "side": (576, 1024)}
WOOD_REGIONS = {"solid": (0, 256), "strip": (256, 512), "band": (512, 1024)}
SIDE_M = (2.0, 1.1)        # m (along, up) of the SIDE tile
TOP_M = (2.0, 0.6)
FAR_M = (4.0, 1.15)
CLUMP_M = (0.8, 1.25)
STRIP_M = (4.0, 0.8)
BAND_Z = (-0.05, 1.0)      # m over the ground of the BAND tile; along it one span (vineyards.POST_GAP)
BAND_VINES = 6             # vines per span
SOLID_U = {"wood": (0.0, 0.5), "concrete": (0.5, 0.75), "steel": (0.75, 1.0)}
# leaf colours (sRGB) and their shares: October, most still green
LEAF_COLS = [((0.22, 0.34, 0.10), 0.32), ((0.27, 0.40, 0.12), 0.28), ((0.19, 0.29, 0.09), 0.18),
             ((0.40, 0.45, 0.14), 0.10), ((0.58, 0.52, 0.16), 0.06), ((0.55, 0.33, 0.11), 0.03),
             ((0.47, 0.17, 0.10), 0.02), ((0.40, 0.30, 0.17), 0.01)]
GRAPE = (0.16, 0.10, 0.21)
BLOOM = (0.42, 0.38, 0.52)


def region_v(regions, name):
    """(v0, v1) texture coordinates inside a region (without its padding)."""
    a, b = regions[name]
    return (a + PAD) / N, (b - PAD) / N


# ---------------------------------------------------------------------- drawing helpers
class Canvas:
    """RGBA float canvas (rows from the top), with a height field for the normal map and a tilt per leaf."""

    def __init__(self, w, h, wrap_x=True):
        self.w, self.h, self.wrap = w, h, wrap_x
        self.rgb = np.zeros((h, w, 3), np.float32)
        self.a = np.zeros((h, w), np.float32)
        self.nx = np.zeros((h, w), np.float32)
        self.ny = np.zeros((h, w), np.float32)

    def stamp(self, cx, cy, half, fn):
        """fn(dx, dy) -> (mask, rgb (k, 3), nx, ny) on the window around (cx, cy); wraps in x."""
        for off in ((-self.w, 0, self.w) if self.wrap else (0,)):
            x0, x1 = int(np.floor(cx + off - half)), int(np.ceil(cx + off + half)) + 1
            y0, y1 = int(np.floor(cy - half)), int(np.ceil(cy + half)) + 1
            x0c, x1c, y0c, y1c = max(x0, 0), min(x1, self.w), max(y0, 0), min(y1, self.h)
            if x1c <= x0c or y1c <= y0c:
                continue
            yy, xx = np.mgrid[y0c:y1c, x0c:x1c].astype(np.float32)
            m, col, nx, ny = fn(xx - (cx + off), yy - cy)
            if not m.any():
                continue
            sub = (slice(y0c, y1c), slice(x0c, x1c))
            self.rgb[sub][m] = np.broadcast_to(np.asarray(col, np.float32), m.shape + (3,))[m]
            self.a[sub][m] = 1.0
            self.nx[sub][m] = np.broadcast_to(np.asarray(nx, np.float32), m.shape)[m]
            self.ny[sub][m] = np.broadcast_to(np.asarray(ny, np.float32), m.shape)[m]

    def line(self, pts, width, col, alpha=1.0):
        """A polyline (pixels), width in pixels (array per point allowed), flat colour (callable(t) allowed)."""
        pts = np.asarray(pts, np.float32)
        wid = np.broadcast_to(np.asarray(width, np.float32), (len(pts),))
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            L = max(float(np.hypot(*(q - p))), 1e-3)
            n = int(np.ceil(L / 0.7)) + 1
            for t in np.linspace(0, 1, n):
                c = p + (q - p) * t
                r = 0.5 * (wid[i] + (wid[i + 1] - wid[i]) * t)
                cc = col(t) if callable(col) else col

                def fn(dx, dy, r=r, cc=cc):
                    d = np.hypot(dx, dy)
                    m = d <= max(r, 0.5)
                    # round shading across the stroke
                    k = np.clip(1.0 - (dx / max(r, 0.5)) * 0.35, 0.6, 1.3)
                    return m, np.asarray(cc, np.float32)[None, None] * k[..., None], dx / max(r, 0.5) * 0.6, 0.0
                self.stamp(c[0], c[1], r + 1, fn)

    def bleed(self):
        """Colours of the transparent texels from the nearest opaque one (no dark fringes in the mipmaps)."""
        if self.a.min() > 0.5:
            return
        _, (iy, ix) = distance_transform_edt(self.a < 0.5, return_indices=True)
        self.rgb = self.rgb[iy, ix]


def leaf_fn(R, col, rng, tilt=None):
    """A vine leaf of radius R px: five lobes, sinuses, serrated, the petiole sinus at the base, midribs."""
    th0 = rng.uniform(0, 2 * np.pi)
    sq = rng.uniform(0.45, 1.0)                          # foreshortening
    sq_a = rng.uniform(0, np.pi)
    tx, ty = tilt if tilt is not None else rng.normal(0, 0.45, 2)
    lob = rng.uniform(0.18, 0.32)
    shade = rng.uniform(0.86, 1.10)
    col = np.asarray(col, np.float32)

    def fn(dx, dy):
        # undo the foreshortening: stretch along sq_a
        c, s = np.cos(sq_a), np.sin(sq_a)
        u = dx * c + dy * s
        v = (-dx * s + dy * c) / sq
        r = np.hypot(u, v)
        th = np.arctan2(v, u) - th0
        rim = R * (1.0 - lob * np.abs(np.sin(2.5 * th)) ** 0.7 + 0.035 * np.sin(31 * th))
        base = np.cos(th) < -0.93                       # the petiole sinus
        m = (r <= rim) & ~(base & (r > 0.35 * R))
        # veins: five midribs from the centre
        vein = np.abs(np.sin(2.5 * th)) < 0.06 * R / np.maximum(r, 1)
        k = shade * (0.92 + 0.12 * (r / R)) * np.where(vein, 0.86, 1.0)
        rgb = col[None, None] * k[..., None]
        nx = tx + 0.3 * dx / R                         # tilted, domed
        ny = ty + 0.3 * dy / R
        return m, rgb, nx, ny
    return fn


def leaf_colour(rng, vine_tint):
    cols, p = zip(*LEAF_COLS)
    c = np.array(cols[rng.choice(len(cols), p=np.array(p) / sum(p))], np.float32)
    return np.clip(c * vine_tint * rng.uniform(0.9, 1.1, 3), 0, 1)


def vine_tints(rng, n):
    """A shade per vine: some greener, some yellower."""
    out = []
    for _ in range(n):
        y = rng.uniform(-1, 1)
        out.append(np.array([1.0 + 0.10 * y, 1.0 + 0.03 * y, 1.0 - 0.12 * y], np.float32) * rng.uniform(0.92, 1.06))
    return out


def foliage(cv, rng, cover, R, rows, vines, darker_low=0.25, light=1.0):
    """Leaves over the canvas, about `cover` layers deep: rows(rng, x) -> the row of a leaf at column x
    (pixels from the top); deeper leaves first (darker), sunlit front leaves last. vines: the tint of each
    vine across the width."""
    tints = vine_tints(rng, vines)
    n = int(cover * cv.w * cv.h / (0.55 * np.pi * R * R))
    for k in range(n):
        depth = k / n                                     # 0: back, 1: front
        cx = rng.uniform(0, cv.w)
        cy = rows(rng, cx)
        if cy is None:
            continue
        vine = int(cx / cv.w * vines) % vines
        col = leaf_colour(rng, tints[vine]) * (0.55 + 0.5 * depth) * light
        col = col * (1.0 - darker_low * np.clip(cy / cv.h, 0, 1))
        r = R * rng.uniform(0.75, 1.2)
        cv.stamp(cx, cy, r * 1.2, leaf_fn(r, np.clip(col, 0, 1), rng))


def ragged(rng, w, amp, scale):
    """A wavy edge profile (pixels), tileable along the width."""
    return amp * noise(1, w, scale, rng)[0]


def band_rows(top, bot, spread=0.0):
    """rows(rng, x) between the edge profiles top(x) and bot(x) (pixels), a few leaves `spread` beyond them."""
    def rows(rng, x):
        i = int(x) % len(top)
        t, b = top[i], bot[i]
        return rng.uniform(t - spread, b + spread)
    return rows


# ---------------------------------------------------------------------- leaf atlas
def side_tile(rng, w, h):
    """The face of the leaf wall (h px = 1.1 m): dense leaves, a ragged top with shoot tips, a ragged
    bottom where a few bunches show."""
    cv = Canvas(w, h)
    R = 0.075 / SIDE_M[1] * h                            # 15 cm leaves
    top = 0.12 * h + ragged(rng, w, 0.05 * h, 40)
    bot = 0.86 * h + ragged(rng, w, 0.05 * h, 30)
    for _ in range(int(w / 260)):                         # bunches behind the lowest leaves
        bunch(cv, rng, rng.uniform(0, w), 0.80 * h, 0.14 / SIDE_M[1] * h)
    foliage(cv, rng, 2.6, R, band_rows(top, bot, 0.3 * R), vines=2)
    # shoot tips over the top: thin canes with small leaves
    for _ in range(int(w / 45)):
        x = rng.uniform(0, w)
        y0 = top[int(x) % w] + 0.04 * h
        y1 = y0 - rng.uniform(0.08, 0.15) * h
        xs = x + np.cumsum(rng.normal(0, 1.5, 6))
        cv.line(np.column_stack([xs, np.linspace(y0, y1, 6)]), 3.0, (0.36, 0.40, 0.15))
        for t in (0.55, 1.0):
            cv.stamp(xs[-1] + rng.normal(0, 4), y0 + (y1 - y0) * t, R,
                     leaf_fn(R * rng.uniform(0.45, 0.65), leaf_colour(rng, np.ones(3)) * 1.05, rng))
    # a few holes through the wall
    holes = gaussian_filter(rng.uniform(0, 1, (h, w)).astype(np.float32), 6, mode="wrap")
    cv.a[holes > np.quantile(holes, 0.99)] = 0.0
    return cv


def top_tile(rng, w, h):
    """The top of the wall from above (h px = 0.6 m across), ragged on both edges, lighter (sunlit)."""
    cv = Canvas(w, h)
    R = 0.07 / TOP_M[1] * h
    e0 = 0.16 * h + ragged(rng, w, 0.05 * h, 30)
    e1 = 0.84 * h + ragged(rng, w, 0.05 * h, 30)
    foliage(cv, rng, 2.6, R, band_rows(e0, e1, 0.2 * R), vines=2, darker_low=0.0, light=1.08)
    return cv


def clump_tile(rng, w, h):
    """A clump of shoots (0.8 m x 1.25 m): leaves round two canes, dense in the middle, open at the edges,
    a shoot tip over the top."""
    cv = Canvas(w, h, wrap_x=False)
    R = 0.075 / CLUMP_M[0] * w
    for _ in range(2):
        x0 = rng.uniform(0.35, 0.65) * w
        xs = x0 + np.cumsum(rng.normal(0, 2.0, 12))
        cv.line(np.column_stack([xs, np.linspace(h * 0.98, h * 0.05, 12)]), 3.0, (0.38, 0.33, 0.20))

    def rows(r, x):
        e = 1.0 - ((x / w - 0.5) / 0.42) ** 2
        if e <= 0:
            return None
        half = 0.46 * np.sqrt(e) * h
        return r.uniform(0.52 * h - half, 0.52 * h + half)
    foliage(cv, rng, 2.2, R, rows, vines=1, darker_low=0.15)
    return cv


def leaf_atlas(dst):
    rng = np.random.default_rng(SEED)
    col = np.zeros((N, N, 3), np.float32)
    alpha = np.zeros((N, N), np.float32)
    nrm = np.zeros((N, N, 2), np.float32)

    def put(name, cv, x0=0, w=N):
        a, b = LEAF_REGIONS[name]
        r0, r1 = N - b + PAD, N - a - PAD                   # image rows (from the top) inside the padding
        h = r1 - r0
        cv.bleed()
        rgb = np.asarray(Image.fromarray(to8(cv.rgb)).resize((w, h), Image.LANCZOS), np.float32) / 255
        al = np.asarray(Image.fromarray(to8(cv.a)).resize((w, h), Image.BILINEAR), np.float32) / 255
        nx = np.asarray(Image.fromarray(cv.nx.astype(np.float32)).resize((w, h), Image.BILINEAR))
        ny = np.asarray(Image.fromarray(cv.ny.astype(np.float32)).resize((w, h), Image.BILINEAR))
        col[r0:r1, x0:x0 + w] = rgb
        alpha[r0:r1, x0:x0 + w] = al
        nrm[r0:r1, x0:x0 + w, 0] = nx
        nrm[r0:r1, x0:x0 + w, 1] = ny
    ppm = 512                                              # canvas pixels per metre
    side = side_tile(rng, int(SIDE_M[0] * ppm), int(SIDE_M[1] * ppm))
    put("side", side)
    put("top", top_tile(rng, int(TOP_M[0] * ppm), int(TOP_M[1] * ppm)))
    for k in range(4):
        put("clump", clump_tile(rng, int(CLUMP_M[0] * 400), int(CLUMP_M[1] * 400)), x0=k * N // 4, w=N // 4)
    # far wall: the side band repeated twice over 4 m, blurred, almost solid, with a ragged top
    a, b = LEAF_REGIONS["far"]
    r0, r1 = N - b + PAD, N - a - PAD
    s = np.asarray(Image.fromarray(to8(side.rgb)).resize((N // 2, r1 - r0), Image.LANCZOS), np.float32) / 255
    s = np.concatenate([s, s[:, ::-1]], 1)
    s = gaussian_filter(s, (1.5, 3, 0), mode="wrap")
    col[r0:r1] = s * 0.97
    yy = np.arange(r1 - r0)[:, None].astype(np.float32)
    top = 0.12 * (r1 - r0) + ragged(rng, N, 0.07 * (r1 - r0), 6)
    bot = 0.93 * (r1 - r0) + ragged(rng, N, 0.04 * (r1 - r0), 8)
    alpha[r0:r1] = ((yy > top[None]) & (yy < bot[None])).astype(np.float32)
    # colours: no dark fringes; the normal map from the leaf tilts
    _, (iy, ix) = distance_transform_edt(alpha < 0.5, return_indices=True)
    col = col[iy, ix]
    n3 = np.dstack([nrm[..., 0], -nrm[..., 1], np.ones((N, N), np.float32)])
    n3 /= np.linalg.norm(n3, axis=2, keepdims=True)
    save(os.path.join(dst, "t_vine_leaf_b.color.png"), to8(col))
    save(os.path.join(dst, "t_vine_leaf_o.data.png"), to8(alpha > 0.5))
    save(os.path.join(dst, "t_vine_leaf_nm.normal.png"), to8(n3 * 0.5 + 0.5))
    return col, alpha


# ---------------------------------------------------------------------- wood atlas
def bunch(cv, rng, x, y, L):
    """A grape bunch hanging from (x, y) (pixels), L px long: a cone of berries, dark purple with bloom."""
    br = max(1.6, L * 0.075)
    cv.line([(x, y - 0.12 * L), (x + rng.normal(0, 1), y + 0.05 * L)], max(1.2, br * 0.4), (0.33, 0.30, 0.16))
    n = int(28 + 14 * rng.uniform())
    for _ in range(n):
        t = rng.uniform(0, 1) ** 0.8                       # along the bunch, more berries at the shoulders
        half = (1 - t) * 0.42 * L + br
        bx = x + rng.uniform(-half, half) * 0.8
        by = y + t * L
        c = np.array(GRAPE, np.float32) * rng.uniform(0.75, 1.25)
        hl = rng.uniform(0, 1) < 0.5

        def fn(dx, dy, c=c, hl=hl):
            d = np.hypot(dx, dy)
            m = d <= br
            k = (1.15 - 0.45 * (d / br))
            rgb = c[None, None] * k[..., None]
            if hl:                                          # the dusty bloom on the lit side
                rgb = np.where(((dx < -0.2 * br) & (dy < -0.2 * br))[..., None], np.asarray(BLOOM)[None, None], rgb)
            return m, rgb, dx / br * 0.8, dy / br * 0.8
        cv.stamp(bx, by, br + 1, fn)


def band_tile(rng, w, h, span):
    """One span between two posts (w px = span m, h px = BAND_Z): post, trunks, cordon, wire, grapes."""
    cv = Canvas(w, h)
    ppm_x, ppm_y = w / span, h / (BAND_Z[1] - BAND_Z[0])
    zr = lambda z: (BAND_Z[1] - z) * ppm_y                  # row of a height over the ground
    # weeds at the foot
    for _ in range(int(w / 14)):
        x = rng.uniform(0, w)
        hgt = rng.uniform(0.03, 0.12) * ppm_y
        lean = rng.normal(0, 0.3) * hgt
        cv.line([(x, zr(-0.02)), (x + lean, zr(-0.02) - hgt)], 2.0,
                np.array((0.30, 0.38, 0.14)) * rng.uniform(0.7, 1.2))
    wire_z = 0.80
    xs_v = (np.arange(BAND_VINES) + 0.5) / BAND_VINES * w + rng.normal(0, 0.04 * ppm_x, BAND_VINES)
    for xv in xs_v:
        top_z = rng.uniform(0.68, 0.76)
        thick = rng.uniform(0.055, 0.085)
        # the old twisted trunk: a gnarled line from the ground to the cordon, thicker at the foot and
        # at the head, grey-brown shaggy bark
        zs = np.linspace(BAND_Z[0], top_z, 12)
        xs = xv + np.cumsum(rng.normal(0, 0.008 * ppm_x, 12)) + 0.025 * ppm_x * np.sin(zs * rng.uniform(5, 9) + rng.uniform(0, 6))
        wid = thick * (1.0 + 0.25 * np.exp(-((zs - BAND_Z[0]) / 0.1) ** 2) + 0.35 * np.exp(-((zs - top_z) / 0.06) ** 2)
                       + 0.12 * rng.standard_normal(12)) * ppm_x
        tone = rng.uniform(0.85, 1.1)
        bark = lambda t: np.array((0.29, 0.25, 0.21)) * tone * (0.8 + 0.3 * rng.uniform())
        cv.line(np.column_stack([xs, zr(zs)]), wid, bark)
        # cordon arms along the wire, both ways
        for sgn in (-1, 1):
            L = rng.uniform(0.38, 0.48)
            n = 8
            ax = xs[-1] + sgn * np.linspace(0, L, n) * ppm_x
            az = top_z + (wire_z - 0.015 - top_z) * np.sqrt(np.linspace(0, 1, n)) + rng.normal(0, 0.006, n)
            cv.line(np.column_stack([ax, zr(az)]), np.linspace(thick * 0.8, 0.025, n) * ppm_x,
                    lambda t: np.array((0.33, 0.27, 0.20)) * (0.9 + 0.2 * t))
            # shoots from the spurs, up into the wall
            for k in range(1, n, 2):
                sx = ax[k] + rng.normal(0, 0.01 * ppm_x)
                sz = np.linspace(az[k], BAND_Z[1] + 0.05, 5)
                cv.line(np.column_stack([sx + np.cumsum(rng.normal(0, 0.006 * ppm_x, 5)), zr(sz)]), 0.012 * ppm_x,
                        (0.42, 0.36, 0.20))
            # bunches under the arm
            for _ in range(rng.poisson(1.1)):
                bx = xs[-1] + sgn * rng.uniform(0.08, 0.4) * ppm_x
                bunch(cv, rng, bx, zr(wire_z - 0.02), rng.uniform(0.12, 0.2) * ppm_y)
    # the fruiting wire over the whole span
    cv.line([(0, zr(wire_z)), (w, zr(wire_z))], max(1.5, 0.004 * ppm_y), (0.62, 0.63, 0.64))
    # the lowest leaves of the wall at the top of the band
    R = 0.075 * ppm_y

    foliage(cv, rng, 0.35, R, lambda r, x: zr(r.uniform(0.88, 1.06)), vines=BAND_VINES, darker_low=0.0)
    # the post at u = 0 (half at each edge), a weathered chestnut post
    pw = 0.09 * ppm_x
    for x0 in (0, w):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        m = np.abs(xx - x0) <= pw / 2
        grain = 0.85 + 0.15 * np.sin(xx * 0.9 + noise(h, w, 3, rng) * 2)
        cv.rgb[m] = (np.array((0.42, 0.37, 0.31), np.float32)[None] * grain[m][:, None])
        cv.a[m] = 1.0
    return cv


def strip_tile(rng, w, h):
    """The bare earth under the row (h px = 0.8 m across): clods, stones, fallen leaves, grassy edges."""
    cv = Canvas(w, h)
    n1 = noise(h, w, 2.0, rng)
    n2 = noise(h, w, 12, rng)
    earth = np.array((0.31, 0.25, 0.18), np.float32)
    cv.rgb[:] = earth[None, None] * (0.85 + 0.08 * n1 + 0.10 * n2)[..., None]
    cv.a[:] = 1.0
    for _ in range(int(w * h / 900)):                     # small stones
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(1.2, 3.5)
        c = np.array((0.52, 0.49, 0.44)) * rng.uniform(0.8, 1.15)
        cv.stamp(x, y, r + 1, lambda dx, dy, r=r, c=c: (np.hypot(dx, dy * 1.3) <= r, np.asarray(c, np.float32)[None, None]
                                                        * np.ones((1, 1, 1), np.float32), 0.0, 0.0))
    for _ in range(int(w / 25)):                          # fallen leaves
        x, y = rng.uniform(0, w), rng.uniform(0.15, 0.85) * h
        cv.stamp(x, y, 10, leaf_fn(7, leaf_colour(rng, np.array((1.15, 1.0, 0.8))) * 0.9, rng))
    # grass at the edges: tufts of blades over the earth, then nothing
    yy = np.arange(h)[:, None].astype(np.float32)
    e0 = 0.20 * h + ragged(rng, w, 0.04 * h, 25)
    e1 = 0.80 * h + ragged(rng, w, 0.04 * h, 25)
    for e, sgn in ((e0, -1), (e1, 1)):
        for _ in range(int(w / 3)):
            x = rng.uniform(0, w)
            y = e[int(x) % w] + sgn * rng.uniform(-0.06, 0.02) * h
            L = rng.uniform(0.04, 0.10) * h / STRIP_M[1] * 0.8
            cv.line([(x, y), (x + rng.normal(0, 0.4) * L, y + sgn * L)], 1.6,
                    np.array((0.30, 0.40, 0.15)) * rng.uniform(0.75, 1.2))
    out = (yy < e0[None] - 0.07 * h) | (yy > e1[None] + 0.07 * h)
    cv.a[out] = 0.0
    # and the blades: alpha only where drawn beyond the earth
    earth_edge = (yy < e0[None]) | (yy > e1[None])
    drawn = np.abs(cv.rgb[..., 1] - cv.rgb[..., 0]) > 0.06
    cv.a[earth_edge & ~drawn] = 0.0
    return cv


def solid_tile(rng, w, h):
    """Wood (u 0-0.5), concrete (0.5-0.75), galvanised steel (0.75-1); h px = 2 m of a post."""
    cv = Canvas(w, h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grain = noise(h, w // 2, 1.0, rng) * 0.5 + aniso(h, w // 2, rng)
    wood = np.array((0.42, 0.37, 0.31), np.float32)[None, None] * (0.88 + 0.1 * grain)[..., None]
    cv.rgb[:, :w // 2] = wood
    conc = np.array((0.62, 0.61, 0.58), np.float32)[None, None] * (0.92 + 0.05 * noise(h, w // 4, 1.0, rng))[..., None]
    cv.rgb[:, w // 2:3 * w // 4] = conc
    cv.rgb[:, 3 * w // 4:] = np.array((0.66, 0.67, 0.68), np.float32)[None, None] * \
        (0.95 + 0.04 * noise(h, w // 4, 3.0, rng))[..., None]
    cv.a[:] = 1.0
    return cv


def aniso(h, w, rng):
    n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (12, 0.8), mode="wrap")
    return n / max(float(n.std()), 1e-6)


def wood_atlas(dst, span):
    rng = np.random.default_rng(SEED + 1)
    col = np.zeros((N, N, 3), np.float32)
    alpha = np.zeros((N, N), np.float32)

    def put(name, cv):
        a, b = WOOD_REGIONS[name]
        r0, r1 = N - b + PAD, N - a - PAD
        cv.bleed()
        col[r0:r1] = np.asarray(Image.fromarray(to8(cv.rgb)).resize((N, r1 - r0), Image.LANCZOS), np.float32) / 255
        alpha[r0:r1] = np.asarray(Image.fromarray(to8(cv.a)).resize((N, r1 - r0), Image.BILINEAR), np.float32) / 255
    put("band", band_tile(rng, int(span * 400), int((BAND_Z[1] - BAND_Z[0]) * 400), span))
    put("strip", strip_tile(rng, int(STRIP_M[0] * 300), int(STRIP_M[1] * 300)))
    put("solid", solid_tile(rng, N, 256))
    _, (iy, ix) = distance_transform_edt(alpha < 0.5, return_indices=True)
    col = col[iy, ix]
    save(os.path.join(dst, "t_vine_wood_b.color.png"), to8(col))
    save(os.path.join(dst, "t_vine_wood_o.data.png"), to8(alpha > 0.5))
    return col, alpha


def build(dst, span=5.5):
    """Both atlases into dst."""
    os.makedirs(dst, exist_ok=True)
    return leaf_atlas(dst), wood_atlas(dst, span)


def preview(dst, path):
    """Colour over a checker where transparent, both atlases side by side."""
    tiles = []
    for name in ("t_vine_leaf", "t_vine_wood"):
        c = np.asarray(Image.open(os.path.join(dst, f"{name}_b.color.png")).convert("RGB"), np.float32)
        a = np.asarray(Image.open(os.path.join(dst, f"{name}_o.data.png")).convert("L"), np.float32)[..., None] / 255
        yy, xx = np.mgrid[0:N, 0:N]
        chk = np.where(((yy // 16 + xx // 16) % 2)[..., None] == 0, 200.0, 235.0)
        tiles.append(c * a + chk * (1 - a))
    Image.fromarray(np.concatenate(tiles, 1).astype(np.uint8)).save(path, quality=90)


if __name__ == "__main__":
    build(sys.argv[1])
    preview(sys.argv[1], os.path.join(sys.argv[1], "vine_textures_preview.jpg"))
