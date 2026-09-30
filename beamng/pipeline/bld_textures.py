"""Original procedural textures of the buildings (v2.2): nothing here comes from a photograph.

The Street View panoramas were looked at for what the buildings of the Malcantone are made of (plastered
walls in light earthy tones, window surrounds lighter than the wall, wooden shutters with louvres,
mostly green, brown or grey, granite sills and door frames on the old houses, roller shutters and
aluminium windows on the newer ones, rubble-stone rustici, roofs of canal tiles "coppi", flat clay
tiles, stone slabs "piode", metal sheet and flat roofs); every texture below is drawn from scratch with
numpy from those observations: shapes, proportions and colours, never pixels of an image.

Textures (BeamNG texture cooker naming: *.color.png sRGB, *.normal.png OpenGL tangent space Y+,
*.data.png linear grey), written by build(dst):
- the openings atlas (4096 px, PPM px per metre): windows with open or closed shutters in several
  colours, roller shutters, modern windows with external blinds, French windows with a railing,
  doors, garage doors, shop fronts, ribbon windows of workshops, cellar windows, attic vents, church
  windows, barn openings; with opacity (alpha clip: the wall shows around them), normal, roughness and
  ambient occlusion. index: bld_openings.json (module -> rectangle in the atlas, size in metres);
- tiling: plaster (tinted with the vertex colour of each building), plinth band, rubble stone,
  roofs of coppi, flat tiles, piode, metal sheet and flat roofs (gravel); each with normal and
  roughness.
    python bld_textures.py <folder>        (writes the textures there, plus preview images)
"""
import json, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt

PPM = 136                     # atlas pixels per metre
ATLAS = (4096, 2048)          # width, height of the openings atlas
SEED = 22


# ------------------------------------------------------------------ noise and maps
def noise(h, w, sigma, rng, wrap=True):
    """Gaussian-filtered white noise, unit standard deviation (tileable with wrap)."""
    n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), sigma, mode="wrap" if wrap else "reflect")
    return n / max(float(n.std()), 1e-6)


def aniso_noise(h, w, sy, sx, rng, wrap=True):
    n = gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (sy, sx), mode="wrap" if wrap else "reflect")
    return n / max(float(n.std()), 1e-6)


def normal_map(height, strength, wrap=True):
    """RGB uint8 normal map of a height field (rows down), OpenGL convention (green = up the image)."""
    mode = "wrap" if wrap else "nearest"
    H = np.asarray(height, np.float32)
    dx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) * 0.5 if wrap else np.gradient(H, axis=1)
    drow = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) * 0.5 if wrap else np.gradient(H, axis=0)
    del mode
    nx, ny = -dx * strength, drow * strength                 # up the image = against the rows
    nz = np.ones_like(H)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack([nx / n, ny / n, nz / n], -1)
    return np.clip((rgb * 0.5 + 0.5) * 255 + 0.5, 0, 255).astype(np.uint8)


def ao_map(height, radius_px, strength, wrap=True):
    """Ambient occlusion from a height field: darker where the surface lies below its surroundings."""
    H = np.asarray(height, np.float32)
    blur = gaussian_filter(H, radius_px, mode="wrap" if wrap else "nearest")
    occ = np.clip(blur - H, 0, None) * strength
    return np.clip(255 * (1 - occ), 0, 255).astype(np.uint8)


def to8(a):
    return np.clip(np.asarray(a) * 255 + 0.5, 0, 255).astype(np.uint8)


def save(path, arr):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(arr).save(path, optimize=True)


# ------------------------------------------------------------------ colours (sRGB 0..1)
SHUTTER = {                                   # painted wooden shutters of the area
    "verde": (0.25, 0.38, 0.27), "verde_scuro": (0.15, 0.27, 0.19), "marrone": (0.37, 0.26, 0.18),
    "legno": (0.50, 0.36, 0.23), "grigio": (0.56, 0.57, 0.56), "bordeaux": (0.43, 0.18, 0.16),
    "bianco": (0.86, 0.86, 0.83), "azzurro": (0.44, 0.52, 0.57),
}
FRAME_WHITE = (0.90, 0.90, 0.88)
FRAME_WOOD = (0.42, 0.29, 0.19)
ALU = (0.27, 0.28, 0.29)
GRANITE = (0.63, 0.62, 0.59)
SURROUND = (0.93, 0.92, 0.89)                 # window surrounds painted lighter than the wall
GLASS = (0.10, 0.12, 0.14)
SKY = (0.52, 0.60, 0.68)


class Canvas:
    """One module of the atlas: colour, height, roughness, opacity; coordinates in metres from the
    bottom-left corner (x right, y up)."""

    def __init__(self, w, h, rng):
        self.w, self.h = w, h
        self.W, self.H = int(round(w * PPM)), int(round(h * PPM))
        self.rng = rng
        self.col = np.zeros((self.H, self.W, 3), np.float32)
        self.hgt = np.zeros((self.H, self.W), np.float32)
        self.rough = np.full((self.H, self.W), 0.85, np.float32)
        self.alpha = np.zeros((self.H, self.W), np.float32)
        self.metal = np.zeros((self.H, self.W), np.float32)
        ys = (self.H - 1 - np.arange(self.H) + 0.5) / PPM
        xs = (np.arange(self.W) + 0.5) / PPM
        self.X, self.Y = np.meshgrid(xs, ys)

    def box(self, x0, y0, x1, y1):
        return (self.X >= x0) & (self.X < x1) & (self.Y >= y0) & (self.Y < y1)

    def paint(self, m, color, height=None, rough=None, alpha=1.0, metal=None, add_height=None):
        c = np.asarray(color, np.float32)
        if c.ndim == 1:
            self.col[m] = c
        else:
            self.col[m] = c[m]
        if height is not None:
            self.hgt[m] = height if np.ndim(height) == 0 else height[m]
        if add_height is not None:
            self.hgt[m] += add_height if np.ndim(add_height) == 0 else add_height[m]
        if rough is not None:
            self.rough[m] = rough if np.ndim(rough) == 0 else rough[m]
        if metal is not None:
            self.metal[m] = metal
        self.alpha[m] = alpha

    # textures of materials over the whole canvas (sampled where painted)
    def wood(self, color, vertical=True, amp=0.10):
        r = self.rng
        n = aniso_noise(self.H, self.W, 40, 1.2, r, wrap=False) if vertical else aniso_noise(self.H, self.W, 1.2, 40, r, wrap=False)
        f = aniso_noise(self.H, self.W, 6, 0.6, r, wrap=False) if vertical else aniso_noise(self.H, self.W, 0.6, 6, r, wrap=False)
        return np.asarray(color, np.float32)[None, None] * (1 + amp * (0.6 * n + 0.4 * f))[..., None]

    def painted(self, color, amp=0.04):
        n = noise(self.H, self.W, 3, self.rng, wrap=False)
        m = noise(self.H, self.W, 25, self.rng, wrap=False)
        return np.asarray(color, np.float32)[None, None] * (1 + amp * (0.5 * n + 0.5 * m))[..., None]

    def granite(self):
        r = self.rng
        base = np.asarray(GRANITE, np.float32)
        speck = r.standard_normal((self.H, self.W)).astype(np.float32)
        dark = (speck > 2.0) * -0.25 + (speck < -2.3) * 0.18
        mid = noise(self.H, self.W, 10, r, wrap=False) * 0.04
        return base[None, None] * (1 + dark + mid)[..., None]

    def glass(self, x0, y0, x1, y1, curtain=0.0):
        """Glass of a pane: dark, a little of the sky reflected on its upper part, a light curtain
        behind it."""
        u = np.clip((self.X - x0) / max(x1 - x0, 1e-6), 0, 1)
        v = np.clip((self.Y - y0) / max(y1 - y0, 1e-6), 0, 1)
        refl = 0.28 * v ** 1.5 + 0.10 * (1 - u)
        band = 0.10 * np.exp(-((u + 0.5 * v - 0.95) / 0.10) ** 2)
        g = np.asarray(GLASS, np.float32)[None, None] * (1 - refl[..., None]) + \
            np.asarray(SKY, np.float32)[None, None] * (refl + band)[..., None]
        if curtain > 0:
            folds = 0.85 + 0.15 * np.sin(self.X * 40.0 + 1.3 * np.sin(self.Y * 3.0))
            cur = np.array([0.74, 0.72, 0.67], np.float32)[None, None] * folds[..., None]
            k = curtain * 0.45
            g = g * (1 - k) + cur * k
        return g


# ------------------------------------------------------------------ pieces of the modules
def louvres(cv, x0, y0, x1, y1, color, pitch=0.045, stile=0.05, board=False):
    """A shutter leaf: stiles around, horizontal louvres (or vertical boards) inside."""
    m = cv.box(x0, y0, x1, y1)
    wood = cv.wood(color, vertical=True, amp=0.06)
    cv.paint(m, wood, height=0.03, rough=0.6)
    inner = cv.box(x0 + stile, y0 + stile, x1 - stile, y1 - stile)
    if board:                                          # solid boards ("scuri")
        ph = ((cv.X - x0) / 0.11) % 1.0
        shade = 0.93 + 0.07 * np.clip(ph * 4, 0, 1)
        cv.col[inner] = (wood * shade[..., None])[inner]
        cv.hgt[inner] = 0.025 - 0.004 * (ph[inner] < 0.06)
        return
    ph = ((cv.Y - y0) / pitch) % 1.0                    # 0 at the bottom of a louvre, 1 at its top
    shade = 0.62 + 0.45 * ph                           # lit from above: light top, shaded bottom
    cv.col[inner] = (wood * shade[..., None])[inner]
    cv.hgt[inner] = (0.012 + 0.012 * ph)[inner]
    # a middle rail on tall leaves
    if y1 - y0 > 1.2:
        ym = y0 + 0.5 * (y1 - y0)
        mr = cv.box(x0, ym - 0.03, x1, ym + 0.03)
        cv.paint(mr, wood, height=0.03, rough=0.6)


def casement(cv, x0, y0, x1, y1, frame_col, leaves=2, panes=2, curtain=0.0, bar=0.055, muntin=0.022):
    """Window frame with glass: `leaves` leaves side by side, `panes` panes on top of each other."""
    m = cv.box(x0, y0, x1, y1)
    fr = cv.painted(frame_col, 0.03)
    cv.paint(m, fr, height=0.01, rough=0.55)
    lw = (x1 - x0 - bar) / leaves
    for k in range(leaves):
        lx0 = x0 + bar / 2 + k * lw
        lx1 = lx0 + lw
        gx0, gx1 = lx0 + bar / 2, lx1 - bar / 2
        gy0, gy1 = y0 + bar, y1 - bar
        g = cv.box(gx0, gy0, gx1, gy1)
        cv.paint(g, cv.glass(gx0, gy0, gx1, gy1, curtain), height=-0.02, rough=0.06)
        for p in range(1, panes):
            yp = gy0 + p * (gy1 - gy0) / panes
            cv.paint(cv.box(gx0, yp - muntin / 2, gx1, yp + muntin / 2), fr, height=0.0, rough=0.55)


def surround(cv, x0, y0, x1, y1, width, kind, top=None):
    """The band around an opening: painted plaster ('plaster') or granite ('granite'); `top` a wider
    lintel."""
    top = top or width
    outer = cv.box(x0 - width, y0, x1 + width, y1 + top)
    inner = cv.box(x0, y0, x1, y1)
    band = outer & ~inner
    if kind == "granite":
        cv.paint(band, cv.granite(), height=0.02, rough=0.7)
    else:
        cv.paint(band, cv.painted(SURROUND, 0.02), height=0.012, rough=0.85)


def sill(cv, x0, x1, y0, h=0.06, kind="granite", over=0.05):
    m = cv.box(x0 - over, y0, x1 + over, y0 + h)
    col = cv.granite() if kind == "granite" else cv.painted((0.72, 0.72, 0.70), 0.02)
    cv.paint(m, col, height=0.035, rough=0.7)
    # the shadow under the sill: part of the wall, drawn as the lower rim of the sill
    cv.hgt[m & (cv.Y < y0 + 0.012)] = 0.015


def reveal_shadow(cv, x0, y0, x1, y1, depth=0.07):
    """The inner reveal of an opening seen from the front: a shaded band at the top and the left."""
    top = cv.box(x0, y1 - depth, x1, y1)
    left = cv.box(x0, y0, x0 + depth * 0.6, y1)
    for mm, k in ((top, 0.55), (left, 0.75)):
        cv.col[mm] *= k
        cv.hgt[mm] -= 0.03


# ------------------------------------------------------------------ modules
def m_shutters(rng, color, open_=True, frame="plaster", ww=1.0, wh=1.4, board=False, curtain=0.4, frame_col=FRAME_WHITE,
               panes=3):
    sw = 0.16 if frame == "granite" else 0.12
    leaf = ww / 2 + 0.02
    W = 2 * leaf + 2 * sw + ww + 0.06 if open_ else ww + 2 * sw + 0.12
    H = 0.07 + wh + sw + 0.03
    cv = Canvas(W, H, rng)
    ox = (W - ww) / 2
    y0 = 0.07
    surround(cv, ox, y0, ox + ww, y0 + wh, sw, frame)
    sill(cv, ox - sw, ox + ww + sw, 0.0, 0.07, "granite" if frame == "granite" else "stone", over=0.04)
    casement(cv, ox + 0.02, y0, ox + ww - 0.02, y0 + wh, frame_col, leaves=2, panes=panes, curtain=curtain)
    reveal_shadow(cv, ox, y0, ox + ww, y0 + wh)
    if open_:
        louvres(cv, ox - sw - leaf - 0.01, y0, ox - sw - 0.01, y0 + wh, color, board=board)
        louvres(cv, ox + ww + sw + 0.01, y0, ox + ww + sw + leaf + 0.01, y0 + wh, color, board=board)
    else:
        louvres(cv, ox + 0.01, y0, ox + ww / 2, y0 + wh, color, board=board)
        louvres(cv, ox + ww / 2, y0, ox + ww - 0.01, y0 + wh, color, board=board)
    return cv


def m_french(rng, color, ww=1.0, wh=2.25, frame="plaster"):
    cv = m_shutters(rng, color, True, frame, ww, wh, curtain=0.3, panes=4)
    ox = (cv.w - ww) / 2
    # wrought-iron railing across the lower part
    iron = np.array([0.16, 0.16, 0.17], np.float32)
    top = 0.07 + 0.95
    cv.paint(cv.box(ox - 0.02, top - 0.035, ox + ww + 0.02, top), iron, height=0.06, rough=0.5, metal=0.6)
    cv.paint(cv.box(ox - 0.02, 0.10, ox + ww + 0.02, 0.13), iron, height=0.06, rough=0.5, metal=0.6)
    for x in np.arange(ox + 0.06, ox + ww - 0.03, 0.11):
        cv.paint(cv.box(x - 0.008, 0.10, x + 0.008, top), iron, height=0.06, rough=0.5, metal=0.6)
    return cv


def m_roller(rng, slat_col, down=0.5, ww=1.2, wh=1.45, frame_col=FRAME_WHITE):
    sw = 0.10
    W, H = ww + 2 * sw + 0.1, 0.07 + wh + sw + 0.03
    cv = Canvas(W, H, rng)
    ox, y0 = (W - ww) / 2, 0.07
    surround(cv, ox, y0, ox + ww, y0 + wh, sw, "plaster")
    sill(cv, ox - sw, ox + ww + sw, 0.0, 0.07, "stone", over=0.03)
    casement(cv, ox + 0.02, y0, ox + ww - 0.02, y0 + wh, frame_col, leaves=2, panes=1, curtain=0.35)
    reveal_shadow(cv, ox, y0, ox + ww, y0 + wh)
    yb = y0 + wh * (1 - down)
    m = cv.box(ox + 0.02, yb, ox + ww - 0.02, y0 + wh)
    ph = ((cv.Y - yb) / 0.05) % 1.0
    col = cv.painted(slat_col, 0.03) * (0.80 + 0.22 * ph)[..., None]
    cv.paint(m, col, height=(0.004 + 0.008 * ph), rough=0.5)
    cv.paint(cv.box(ox + 0.02, yb - 0.02, ox + ww - 0.02, yb + 0.012), cv.painted(slat_col, 0.02) * 0.8, height=0.012)
    return cv


def m_modern(rng, blind=0.35, ww=1.6, wh=1.5, blind_col=(0.70, 0.71, 0.72)):
    W, H = ww + 0.14, 0.05 + wh + 0.06
    cv = Canvas(W, H, rng)
    ox, y0 = 0.07, 0.05
    cv.paint(cv.box(ox - 0.04, 0.0, ox + ww + 0.04, 0.05), cv.painted((0.55, 0.56, 0.57), 0.02), height=0.03,
             rough=0.4, metal=0.5)
    casement(cv, ox, y0, ox + ww, y0 + wh, ALU, leaves=2, panes=1, curtain=0.2, bar=0.07)
    reveal_shadow(cv, ox, y0, ox + ww, y0 + wh, 0.05)
    if blind > 0:
        yb = y0 + wh * (1 - blind)
        m = cv.box(ox, yb, ox + ww, y0 + wh)
        ph = ((cv.Y - yb) / 0.08) % 1.0
        cv.paint(m, cv.painted(blind_col, 0.02) * (0.72 + 0.35 * ph)[..., None], height=0.01 + 0.01 * ph, rough=0.4,
                 metal=0.4)
        # guide rails at the sides
        for gx in (ox - 0.035, ox + ww):
            cv.paint(cv.box(gx, y0, gx + 0.035, y0 + wh), np.array(ALU, np.float32), height=0.02, rough=0.4,
                     metal=0.5)
    return cv


def m_door(rng, color, kind="wood", frame="plaster", ww=1.05, wh=2.15):
    sw = 0.18 if frame == "granite" else 0.12
    W, H = ww + 2 * sw + 0.2, wh + sw + 0.18
    cv = Canvas(W, H, rng)
    ox, y0 = (W - ww) / 2, 0.15
    surround(cv, ox, y0, ox + ww, y0 + wh, sw, frame, top=sw + (0.08 if frame == "granite" else 0.0))
    # step
    cv.paint(cv.box(ox - sw - 0.05, 0.0, ox + ww + sw + 0.05, 0.15), cv.granite(), height=0.04, rough=0.7)
    m = cv.box(ox, y0, ox + ww, y0 + wh)
    if kind == "modern":
        cv.paint(m, cv.painted(ALU, 0.02), height=0.01, rough=0.4, metal=0.5)
        gx0, gx1, gy0, gy1 = ox + 0.12, ox + ww - 0.12, y0 + 0.25, y0 + wh - 0.15
        cv.paint(cv.box(gx0, gy0, gx1, gy1), cv.glass(gx0, gy0, gx1, gy1, 0.0), height=-0.01, rough=0.06)
        cv.paint(cv.box(ox + ww - 0.2, y0 + 0.8, ox + ww - 0.17, y0 + 1.4), np.array([0.75, 0.75, 0.76]),
                 height=0.03, rough=0.3, metal=0.9)
        return cv
    wood = cv.wood(color, vertical=True, amp=0.09)
    cv.paint(m, wood, height=0.015, rough=0.6)
    if kind == "boards":                              # old boarded door with iron straps
        ph = ((cv.X - ox) / 0.13) % 1.0
        cv.col[m] *= (0.88 + 0.12 * (ph > 0.05))[m][:, None]
        for yy in (y0 + 0.35, y0 + wh - 0.4):
            cv.paint(cv.box(ox + 0.04, yy, ox + ww - 0.3, yy + 0.05), np.array([0.14, 0.13, 0.13]), height=0.025,
                     rough=0.6, metal=0.5)
    else:                                             # framed panels, two leaves
        for lx0 in (ox, ox + ww / 2):
            for (py0, py1) in ((y0 + 0.15, y0 + 0.95), (y0 + 1.1, y0 + wh - 0.15)):
                p = cv.box(lx0 + 0.09, py0, lx0 + ww / 2 - 0.09, py1)
                edge = p & ~cv.box(lx0 + 0.12, py0 + 0.03, lx0 + ww / 2 - 0.12, py1 - 0.03)
                cv.hgt[p] = 0.022
                cv.hgt[edge] = 0.008
                cv.col[edge] *= 0.8
        cv.paint(cv.box(ox + ww / 2 - 0.006, y0, ox + ww / 2 + 0.006, y0 + wh), wood * 0.6, height=0.005)
    cv.paint(cv.box(ox + ww / 2 - 0.12, y0 + 1.0, ox + ww / 2 - 0.07, y0 + 1.06), np.array([0.62, 0.55, 0.35]),
             height=0.04, rough=0.3, metal=0.9)
    return cv


def m_garage(rng, color, kind="sectional", ww=2.5, wh=2.15):
    W, H = ww + 0.2, wh + 0.14
    cv = Canvas(W, H, rng)
    ox, y0 = 0.1, 0.0
    cv.paint(cv.box(ox - 0.08, y0, ox + ww + 0.08, y0 + wh + 0.08), cv.painted((0.60, 0.60, 0.59), 0.03), height=0.015,
             rough=0.6)
    m = cv.box(ox, y0, ox + ww, y0 + wh)
    if kind == "sectional":
        ph = ((cv.Y - y0) / (wh / 4)) % 1.0
        col = cv.painted(color, 0.025) * (0.93 + 0.07 * (ph > 0.04))[..., None]
        rib = ((cv.Y - y0) / 0.13) % 1.0
        cv.paint(m, col, height=0.01 - 0.008 * (ph < 0.04) + 0.002 * (rib < 0.12), rough=0.45, metal=0.3)
    else:                                             # wooden swing doors, vertical boards
        wood = cv.wood(color, vertical=True, amp=0.1)
        ph = ((cv.X - ox) / 0.12) % 1.0
        cv.paint(m, wood * (0.86 + 0.14 * (ph > 0.06))[..., None], height=0.012 - 0.006 * (ph < 0.06), rough=0.65)
        cv.paint(cv.box(ox + ww / 2 - 0.01, y0, ox + ww / 2 + 0.01, y0 + wh), wood * 0.5, height=0.0)
    return cv


def m_shop(rng, fascia=(0.30, 0.32, 0.33), ww=3.0, wh=2.6):
    W, H = ww + 0.1, wh + 0.55
    cv = Canvas(W, H, rng)
    ox = 0.05
    cv.paint(cv.box(ox - 0.05, wh, ox + ww + 0.05, wh + 0.5), cv.painted(fascia, 0.03), height=0.03, rough=0.5)
    cv.paint(cv.box(ox, 0.0, ox + ww, 0.25), cv.granite(), height=0.02, rough=0.7)
    fr = np.array(ALU, np.float32)
    cv.paint(cv.box(ox, 0.25, ox + ww, wh), fr, height=0.01, rough=0.4, metal=0.5)
    door_x = ox + ww - 1.0
    for (a, b) in ((ox + 0.06, door_x - 0.03), (door_x + 0.06, ox + ww - 0.06)):
        top = wh - 0.06
        y0 = 0.31 if a < door_x else 0.02
        g = cv.box(a, y0, b, top)
        glass = cv.glass(a, y0, b, top, 0.0)
        # something of the shop behind the glass: shelves and light
        shelves = 0.85 + 0.15 * (((cv.Y - y0) / 0.45) % 1.0 > 0.9)
        glass = glass * shelves[..., None]
        cv.paint(g, glass, height=-0.02, rough=0.06)
    cv.paint(cv.box(door_x + 0.12, 1.0, door_x + 0.15, 1.6), np.array([0.75, 0.75, 0.76]), height=0.03, rough=0.3,
             metal=0.9)
    return cv


def m_ribbon(rng, ww=3.0, wh=1.2, frame_col=(0.55, 0.57, 0.58)):
    W, H = ww, wh + 0.08
    cv = Canvas(W, H, rng)
    fr = np.array(frame_col, np.float32)
    cv.paint(cv.box(0, 0, ww, wh + 0.08), fr, height=0.01, rough=0.4, metal=0.5)
    for k in range(3):
        a, b = 0.05 + k * ww / 3, (k + 1) * ww / 3 - 0.02
        for (y0, y1) in ((0.08, 0.08 + 0.35), (0.08 + 0.39, wh + 0.03)):
            g = cv.box(a, y0, b, y1)
            cv.paint(g, cv.glass(a, y0, b, y1, 0.0) * 1.25, height=-0.015, rough=0.05)
    return cv


def m_small(rng, ww=0.6, wh=0.55, grille=True):
    sw = 0.08
    W, H = ww + 2 * sw + 0.04, wh + sw + 0.09
    cv = Canvas(W, H, rng)
    ox, y0 = (W - ww) / 2, 0.05
    surround(cv, ox, y0, ox + ww, y0 + wh, sw, "plaster")
    sill(cv, ox - sw, ox + ww + sw, 0.0, 0.05, "stone", over=0.02)
    casement(cv, ox + 0.02, y0, ox + ww - 0.02, y0 + wh, FRAME_WHITE, leaves=1, panes=1, curtain=0.0)
    reveal_shadow(cv, ox, y0, ox + ww, y0 + wh, 0.05)
    if grille:
        iron = np.array([0.15, 0.15, 0.16], np.float32)
        for x in np.arange(ox + 0.08, ox + ww - 0.04, 0.1):
            cv.paint(cv.box(x - 0.008, y0, x + 0.008, y0 + wh), iron, height=0.05, rough=0.5, metal=0.6)
        for y in (y0 + 0.12, y0 + wh - 0.12):
            cv.paint(cv.box(ox, y - 0.008, ox + ww, y + 0.008), iron, height=0.05, rough=0.5, metal=0.6)
    return cv


def m_vent(rng, ww=0.55, wh=0.4):
    W, H = ww + 0.16, wh + 0.16
    cv = Canvas(W, H, rng)
    ox, y0 = 0.08, 0.08
    surround(cv, ox, y0, ox + ww, y0 + wh, 0.07, "plaster")
    m = cv.box(ox, y0, ox + ww, y0 + wh)
    ph = ((cv.Y - y0) / 0.05) % 1.0
    cv.paint(m, np.array([0.22, 0.2, 0.18], np.float32)[None, None] * (0.6 + 0.8 * ph)[..., None], height=-0.02 + 0.01 * ph)
    sill(cv, ox - 0.07, ox + ww + 0.07, 0.03, 0.05, "stone", over=0.0)
    return cv


def m_church(rng, ww=1.1, wh=2.9):
    sw = 0.18
    r = ww / 2
    W, H = ww + 2 * sw + 0.04, wh + sw + 0.1
    cv = Canvas(W, H, rng)
    ox, y0 = (W - ww) / 2, 0.08
    cx, cyy = ox + r, y0 + wh - r
    inside = (cv.box(ox, y0, ox + ww, cyy)) | (((cv.X - cx) ** 2 + (cv.Y - cyy) ** 2 < r * r) & (cv.Y >= cyy))
    outside = (cv.box(ox - sw, y0, ox + ww + sw, cyy)) | (((cv.X - cx) ** 2 + (cv.Y - cyy) ** 2 < (r + sw) ** 2) &
                                                          (cv.Y >= cyy))
    cv.paint(outside & ~inside, cv.granite(), height=0.03, rough=0.7)
    u, v = cv.X * 7.0, cv.Y * 5.0
    lattice = (np.abs(((u + v) % 1.0) - 0.5) < 0.05) | (np.abs(((u - v) % 1.0) - 0.5) < 0.05)
    tint = 1 + 0.15 * noise(cv.H, cv.W, 14, rng, wrap=False)
    glass = np.array([0.28, 0.33, 0.33], np.float32)[None, None] * tint[..., None]
    glass = np.where(lattice[..., None], np.array([0.12, 0.12, 0.12], np.float32), glass)
    cv.paint(inside, glass, height=-0.03, rough=0.15)
    cv.paint(cv.box(ox - sw, 0.0, ox + ww + sw, y0), cv.granite(), height=0.03, rough=0.7)
    return cv


def m_barn(rng, color=(0.36, 0.27, 0.19), ww=1.6, wh=1.6):
    W, H = ww + 0.16, wh + 0.16
    cv = Canvas(W, H, rng)
    ox, y0 = 0.08, 0.08
    wood = cv.wood(color, vertical=True, amp=0.14)
    cv.paint(cv.box(ox - 0.08, y0 - 0.08, ox + ww + 0.08, y0 + wh + 0.08), wood * 0.9, height=0.03, rough=0.8)
    m = cv.box(ox, y0, ox + ww, y0 + wh)
    ph = ((cv.X - ox) / 0.13) % 1.0
    gap = ph < 0.22
    col = np.where(gap[..., None], np.array([0.04, 0.035, 0.03], np.float32), wood)
    cv.paint(m, col, height=np.where(gap, -0.03, 0.02), rough=0.85)
    return cv


def m_railing(rng, kind="dark", ww=2.0, wh=1.05):
    """The railing of a balcony, seen from the street: a top rail, a bottom rail and bars (metal), or a
    frosted glass panel in a metal frame; transparent between the bars."""
    cv = Canvas(ww, wh, rng)
    metal = {"dark": (0.20, 0.21, 0.22), "light": (0.82, 0.82, 0.80), "green": (0.18, 0.28, 0.21),
             "glass": (0.62, 0.63, 0.64)}[kind]
    col = np.array(metal, np.float32)
    if kind == "glass":
        m = cv.box(0.03, 0.06, ww - 0.03, wh - 0.06)
        frost = cv.painted((0.74, 0.77, 0.78), 0.03) * (0.92 + 0.10 * cv.Y / wh)[..., None]
        cv.paint(m, frost, height=0.01, rough=0.15)
    else:
        for x in np.arange(0.06, ww - 0.03, 0.11):
            cv.paint(cv.box(x - 0.009, 0.06, x + 0.009, wh - 0.05), col, height=0.02, rough=0.45, metal=0.5)
    cv.paint(cv.box(0.0, wh - 0.05, ww, wh), col, height=0.03, rough=0.4, metal=0.5)          # top rail
    cv.paint(cv.box(0.0, 0.04, ww, 0.07), col, height=0.02, rough=0.45, metal=0.5)             # bottom rail
    for x in (0.0, ww - 0.04):                                                                # posts
        cv.paint(cv.box(x, 0.0, x + 0.04, wh), col, height=0.03, rough=0.45, metal=0.5)
    return cv


def modules(rng):
    """Every module of the atlas: name -> Canvas."""
    out = {}
    for name, col in SHUTTER.items():
        out[f"win_{name}"] = m_shutters(rng, col)
        out[f"win_{name}_granite"] = m_shutters(rng, col, frame="granite", ww=0.9, wh=1.3, frame_col=FRAME_WOOD,
                                                panes=3)
        out[f"win_{name}_closed"] = m_shutters(rng, col, open_=False)
        out[f"french_{name}"] = m_french(rng, col)
    out["win_legno_boards_granite"] = m_shutters(rng, SHUTTER["legno"], frame="granite", ww=0.8, wh=1.1, board=True,
                                                 frame_col=FRAME_WOOD, panes=2)
    out["win_verde_scuro_boards_closed"] = m_shutters(rng, SHUTTER["verde_scuro"], open_=False, ww=0.8, wh=1.1,
                                                      board=True)
    for name, col, down in (("roller_white", (0.88, 0.88, 0.86), 0.45), ("roller_grey", (0.60, 0.61, 0.62), 0.6),
                            ("roller_brown", (0.40, 0.30, 0.22), 0.35), ("roller_white_down", (0.88, 0.88, 0.86), 0.95)):
        out[name] = m_roller(rng, col, down)
    out["modern_blind"] = m_modern(rng, 0.35)
    out["modern_open"] = m_modern(rng, 0.0)
    out["modern_blind_down"] = m_modern(rng, 0.85)
    out["modern_tall"] = m_modern(rng, 0.2, ww=1.4, wh=2.3)
    for name, col, kind, frame in (("door_wood_granite", (0.40, 0.27, 0.17), "panel", "granite"),
                                   ("door_green", SHUTTER["verde_scuro"], "panel", "plaster"),
                                   ("door_brown", (0.33, 0.22, 0.15), "panel", "plaster"),
                                   ("door_boards_granite", (0.38, 0.30, 0.22), "boards", "granite"),
                                   ("door_modern", ALU, "modern", "plaster"),
                                   ("door_grey", (0.52, 0.53, 0.53), "panel", "plaster")):
        out[name] = m_door(rng, col, kind, frame)
    for name, col, kind in (("garage_white", (0.86, 0.86, 0.84), "sectional"), ("garage_grey", (0.55, 0.56, 0.57), "sectional"),
                            ("garage_brown", (0.38, 0.28, 0.20), "sectional"), ("garage_wood", (0.40, 0.30, 0.21), "wood")):
        out[name] = m_garage(rng, col, kind)
    out["shop"] = m_shop(rng)
    out["shop_light"] = m_shop(rng, fascia=(0.78, 0.76, 0.70))
    out["ribbon"] = m_ribbon(rng)
    out["ribbon_dark"] = m_ribbon(rng, frame_col=(0.25, 0.26, 0.27))
    out["small_grille"] = m_small(rng)
    out["small"] = m_small(rng, 0.5, 0.7, grille=False)
    out["vent"] = m_vent(rng)
    out["church"] = m_church(rng)
    out["barn"] = m_barn(rng)
    out["barn_door"] = m_door(rng, (0.34, 0.26, 0.19), "boards", "granite", ww=1.4, wh=2.0)
    # v2.2 balconies: the door onto the balcony (shutters or roller shutter) and the railings
    for name, col in SHUTTER.items():
        out[f"bal_{name}"] = m_shutters(rng, col, True, "plaster", ww=0.95, wh=2.2, curtain=0.3, panes=4)
    for name, col, down in (("bal_roller_white", (0.88, 0.88, 0.86), 0.3), ("bal_roller_grey", (0.60, 0.61, 0.62), 0.4),
                            ("bal_roller_brown", (0.40, 0.30, 0.22), 0.25)):
        out[name] = m_roller(rng, col, down, ww=1.2, wh=2.2)
    for kind in ("dark", "light", "green", "glass"):
        out[f"railing_{kind}"] = m_railing(rng, kind)
    return out


def pack(mods, size=ATLAS, pad=4):
    """Shelf packing, tallest first: name -> (x, y, w, h) pixels (y from the top)."""
    order = sorted(mods, key=lambda k: -mods[k].H)
    x = y = shelf = 0
    rects = {}
    for k in order:
        w, h = mods[k].W, mods[k].H
        if x + w + pad > size[0]:
            x, y, shelf = 0, y + shelf + pad, 0
        if y + h + pad > size[1]:
            raise ValueError("atlas full at " + k)
        rects[k] = (x + pad, y + pad, w, h)
        x += w + pad
        shelf = max(shelf, h + pad)
    return rects


def openings_atlas(dst):
    rng = np.random.default_rng(SEED)
    mods = modules(rng)
    rects = pack(mods)
    AW, AH = ATLAS
    col = np.zeros((AH, AW, 3), np.float32)
    col[:] = 0.5
    hgt = np.zeros((AH, AW), np.float32)
    rough = np.full((AH, AW), 0.85, np.float32)
    alpha = np.zeros((AH, AW), np.float32)
    index = {}
    for k, (x, y, w, h) in rects.items():
        cv = mods[k]
        col[y:y + h, x:x + w] = cv.col
        hgt[y:y + h, x:x + w] = cv.hgt
        rough[y:y + h, x:x + w] = cv.rough
        alpha[y:y + h, x:x + w] = cv.alpha
        # uv rectangle (texture coordinates: t up the image) and the size in metres
        index[k] = {"uv": [x / AW, 1 - (y + h) / AH, (x + w) / AW, 1 - y / AH], "w": round(cv.w, 4),
                    "h": round(cv.h, 4)}
    # colour bleeds a little outside the opaque pixels (mip maps of the cut-out stay clean)
    a = alpha > 0.5
    if (~a).any():
        idx = distance_transform_edt(~a, return_distances=False, return_indices=True)
        col = col[idx[0], idx[1]]
    ao = ao_map(hgt * PPM, 6, 0.12, wrap=False)
    save(os.path.join(dst, "t_bld_openings_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_openings_o.data.png"), to8(alpha))
    save(os.path.join(dst, "t_bld_openings_nm.normal.png"), normal_map(hgt * PPM, 1.2, wrap=False))
    save(os.path.join(dst, "t_bld_openings_r.data.png"), to8(rough))
    save(os.path.join(dst, "t_bld_openings_ao.data.png"), ao)
    json.dump({"ppm": PPM, "size": list(ATLAS), "modules": index}, open(os.path.join(dst, "bld_openings.json"), "w"), indent=1)
    return index


# ------------------------------------------------------------------ tiling textures
def plaster(dst, n=1024):
    """Plastered wall, neutral light grey (the vertex colour of each building gives the tone): fine
    grain of the render, patches of repair and weathering, faint vertical streaks of rain water."""
    rng = np.random.default_rng(SEED + 1)
    grain = noise(n, n, 0.8, rng)
    fine = noise(n, n, 3, rng)
    patch = noise(n, n, 40, rng)
    large = noise(n, n, 120, rng)
    streak = aniso_noise(n, n, 90, 2.5, rng)
    v = 0.90 * (1 + 0.018 * grain + 0.012 * fine + 0.014 * patch + 0.016 * large - 0.015 * np.clip(streak, 0, None))
    col = np.stack([v * 1.0, v * 0.995, v * 0.985], -1)
    save(os.path.join(dst, "t_bld_plaster_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_plaster_nm.normal.png"), normal_map(0.6 * grain + 0.4 * fine, 0.35))
    save(os.path.join(dst, "t_bld_plaster_r.data.png"), to8(0.88 + 0.05 * patch))


def voronoi_stones(n, rng, rows, jitter=0.35, flat=1.8):
    """Rubble stones of a wall on a tileable n x n grid: (cell id, distance to the edge of the cell)."""
    pts = []
    for r in range(rows):
        k = int(rows * flat * rng.uniform(0.7, 1.3))
        xs = (np.arange(k) + rng.uniform(0, 1) + rng.uniform(-jitter, jitter, k)) / k
        ys = (r + 0.5 + rng.uniform(-jitter, jitter, k) * 0.7) / rows
        pts += list(zip(xs % 1.0, ys % 1.0))
    P = np.array(pts)
    tiles = np.concatenate([P + [dx, dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    from scipy.spatial import cKDTree
    t = cKDTree(tiles * [1.0, flat])
    g = (np.arange(n) + 0.5) / n
    X, Y = np.meshgrid(g, g)
    # a wobble of the sample points makes the stones rounder and their outlines irregular
    wob = 0.005
    Xw = X + wob * noise(n, n, 30, rng)
    Yw = Y + wob * noise(n, n, 30, rng)
    d, i = t.query(np.column_stack([Xw.ravel(), Yw.ravel() * flat]), k=2)
    edge = (d[:, 1] - d[:, 0]).reshape(n, n)
    cell = (i[:, 0] % len(P)).reshape(n, n)
    return cell, edge


def lit(h, k=1.0):
    """Shading of a height field lit from the upper left (rows down): 1 + k * slope towards the light."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    return 1.0 + k * (-dx - dy)


def stone_wall(dst, n=1024):
    """Rubble-stone masonry of the rustici (gneiss and granite, grey to ochre, lime mortar joints)."""
    rng = np.random.default_rng(SEED + 2)
    cell, edge = voronoi_stones(n, rng, rows=8, jitter=0.35, flat=2.0)
    k = cell.max() + 1
    palette = np.array([[0.56, 0.56, 0.54], [0.60, 0.57, 0.52], [0.52, 0.47, 0.40], [0.63, 0.56, 0.44],
                        [0.44, 0.44, 0.43], [0.66, 0.65, 0.62]])
    pick = rng.choice(len(palette), k, p=[0.3, 0.2, 0.15, 0.1, 0.15, 0.1])
    tone = rng.uniform(0.85, 1.12, k)
    base = palette[pick][cell] * tone[cell][..., None]
    grain = noise(n, n, 0.9, rng)
    mica = (rng.random((n, n)) > 0.995).astype(np.float32)
    ew = 0.03
    mortar = edge < 0.010
    dome = np.sqrt(np.clip((edge - 0.012) / ew, 0, 1))
    hgt = dome * 6.0 + 0.4 * grain
    hgt[mortar] = -1.0 + 0.3 * grain[mortar]
    shade = np.clip(lit(gaussian_filter(hgt, 1.5, mode="wrap"), 0.6), 0.55, 1.35) * (0.62 + 0.38 * dome)
    col = base * (1 + 0.07 * grain + 0.15 * mica)[..., None] * shade[..., None]
    mcol = np.array([0.63, 0.61, 0.57]) * (1 + 0.06 * grain[mortar, None])
    col[mortar] = mcol * 0.55
    save(os.path.join(dst, "t_bld_stone_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_stone_nm.normal.png"), normal_map(hgt, 1.2))
    save(os.path.join(dst, "t_bld_stone_r.data.png"), to8(np.where(mortar, 0.95, 0.78 + 0.05 * grain)))
    save(os.path.join(dst, "t_bld_stone_ao.data.png"), ao_map(hgt, 6, 0.10))


def plinth(dst, w=1024, h=256):
    """The plinth band at the foot of the walls: coarse render ("strollato"), with a small
    projecting edge at the top (v = 1 at the top of the band)."""
    rng = np.random.default_rng(SEED + 3)
    coarse = noise(h, w, 1.2, rng)
    blot = noise(h, w, 18, rng)
    v = 0.84 * (1 + 0.05 * coarse + 0.03 * blot)
    rows = np.arange(h)[:, None] / h
    edge = rows < 0.06
    v = np.where(edge, 0.95 * (1 + 0.02 * coarse), v)
    splash = np.clip(rows - 0.75, 0, None) * 0.3               # darker near the ground
    v = v * (1 - splash)
    col = np.stack([v, v * 0.99, v * 0.97], -1)
    hgt = 1.2 * coarse + np.where(edge, 4.0, 0.0)
    save(os.path.join(dst, "t_bld_plinth_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_plinth_nm.normal.png"), normal_map(hgt, 0.8))
    save(os.path.join(dst, "t_bld_plinth_r.data.png"), to8(0.9 + 0.03 * blot))


def roof_coppi(dst, n=1024, tile_m=2.0):
    """Canal tiles ("coppi"): rows of caps (convex) and channels (concave) running down the slope,
    each course overlapping the next one; the image's up is down the slope (roof_uvs), so the lower
    edge of every tile is towards the top of the image."""
    rng = np.random.default_rng(SEED + 4)
    px = n / tile_m
    X, Y = np.meshgrid(np.arange(n) / px, np.arange(n) / px)
    period = tile_m / 5                                # a channel and a cap: 0.4 m
    ph = (X / period) % 1.0
    col_i = np.floor(X / period * 2).astype(int)       # half columns: caps and channels
    cap = (np.floor(X / period * 2).astype(int) % 2) == 0
    prof = 0.5 * np.cos(2 * np.pi * ph)                # +0.5 on the caps, -0.5 in the channels
    course = tile_m / 5                                # 0.4 m exposed length
    off = np.where(cap, 0.0, 0.5 * course) + (col_i % 5) * 0.013
    f = ((Y + off) / course) % 1.0                     # 0 at the upper end of the exposed tile
    ci = np.floor((Y + off) / course).astype(int)
    step = np.where(f > 0.93, (1 - f) / 0.07 * 0.1, 0.1 * f)
    hgt = prof * 0.9 + step * 0.8
    hsh = np.sin(col_i * 12.9898 + ci * 78.233) * 43758.5453
    hsh = hsh - np.floor(hsh)
    tone = 0.82 + 0.20 * (hsh - 0.5)
    old = ((hsh * 7.31) % 1.0) > 0.88                  # a few darker, weathered tiles
    grain = noise(n, n, 1.2, rng)
    blot = noise(n, n, 60, rng)
    # caps catch the light on their crest and on the side towards the sun, channels are in shade
    shade = 0.62 + 0.42 * (prof + 0.5) + 0.16 * np.sin(2 * np.pi * ph)
    v = tone * (1 - 0.22 * old) * shade * (1 + 0.05 * grain + 0.03 * blot)
    lip = f > 0.95
    v = np.where(lip, v * 0.55, v)
    col = np.stack([v * 1.03, v * 0.97, v * 0.93], -1)
    save(os.path.join(dst, "t_roof_coppi_b.color.png"), to8(col))
    save(os.path.join(dst, "t_roof_coppi_nm.normal.png"), normal_map(hgt * 14 + 0.3 * grain, 1.0))
    save(os.path.join(dst, "t_roof_coppi_r.data.png"), to8(0.72 + 0.06 * blot))


def roof_tegole(dst, n=1024, tile_m=2.0):
    """Flat interlocking clay tiles (from the 1950s): rectangular tiles with a raised rib and two
    small grooves, in straight rows."""
    rng = np.random.default_rng(SEED + 5)
    px = n / tile_m
    X, Y = np.meshgrid(np.arange(n) / px, np.arange(n) / px)
    tw, th = tile_m / 8, tile_m / 5
    u, v = (X / tw) % 1.0, (Y / th) % 1.0
    ti = np.floor(X / tw).astype(int) * 13 + np.floor(Y / th).astype(int) * 7
    tone = 0.84 + 0.10 * (((ti * 0.61803) % 1.0) - 0.5)
    rib = 0.8 * np.exp(-((u - 0.30) / 0.10) ** 2) + 0.8 * np.exp(-((u - 0.72) / 0.10) ** 2) - \
        0.5 * np.exp(-((u - 0.51) / 0.05) ** 2) - 0.6 * np.exp(-((u - 0.03) / 0.03) ** 2)
    hgt = rib + np.where(v > 0.92, (1 - v) / 0.08, v) * 0.6
    grain = noise(n, n, 1.3, rng)
    shade = np.clip(lit(hgt * 5, 0.3), 0.6, 1.3) * np.where(v > 0.93, 0.62, 1.0)
    val = tone * shade * (1 + 0.04 * grain)
    col = np.stack([val * 1.03, val * 0.97, val * 0.93], -1)
    save(os.path.join(dst, "t_roof_tegole_b.color.png"), to8(col))
    save(os.path.join(dst, "t_roof_tegole_nm.normal.png"), normal_map(hgt * 10 + 0.3 * grain, 1.0))
    save(os.path.join(dst, "t_roof_tegole_r.data.png"), to8(0.7 + 0.03 * grain))


def roof_piode(dst, n=1024, tile_m=3.0):
    """Stone slabs ("piode") of the old roofs: irregular gneiss slabs in overlapping courses, joints
    between the slabs of a course, grey with rust and lichen."""
    rng = np.random.default_rng(SEED + 6)
    px = n / tile_m
    X, Y = np.meshgrid(np.arange(n) / px, np.arange(n) / px)
    rows = 8
    course = tile_m / rows
    edge_w = aniso_noise(n, n, 3, 30, rng) * 0.045 + aniso_noise(n, n, 2, 8, rng) * 0.01
    yy = (Y + edge_w) / course
    r_i = np.floor(yy).astype(int) % rows
    f = yy % 1.0                                       # 0 upslope end, 1 at the lower edge of the slab
    slab = np.zeros((n, n), np.int64)
    joint = np.zeros((n, n), np.float32)
    for r in range(rows):
        m = r_i == r
        cuts = np.sort(rng.uniform(0, tile_m, max(3, int(tile_m / rng.uniform(0.38, 0.62)))))
        xs = (X[m] + 0.025 * aniso_noise(n, n, 40, 6, rng)[m]) % tile_m
        idx = np.searchsorted(cuts, xs) % len(cuts)
        slab[m] = r * 1000 + idx
        ext = np.r_[cuts - tile_m, cuts, cuts + tile_m]
        d = np.min(np.abs(xs[:, None] - ext[None, :]), axis=1)
        joint[m] = np.clip(1 - d / 0.015, 0, 1)
    ids, inv = np.unique(slab, return_inverse=True)
    tone = rng.uniform(0.66, 1.08, len(ids))[inv].reshape(n, n)
    rust = (rng.random(len(ids)) > 0.8)[inv].reshape(n, n)
    grain = noise(n, n, 1.0, rng)
    mica = (rng.random((n, n)) > 0.996).astype(np.float32)
    lichen = np.clip(noise(n, n, 5, rng) - 1.6, 0, 1)
    hgt = f * 2.5 + 0.3 * grain - 2.0 * joint
    shade = np.clip(lit(gaussian_filter(hgt, 1.0, mode="wrap") * 4, 0.3), 0.6, 1.3)
    v = 0.86 * tone * (1 + 0.07 * grain + 0.2 * mica) * shade
    lower = f > 0.9
    v = np.where(lower, v * (0.45 + 0.4 * (1 - (f - 0.9) / 0.1)), v)
    v = v * (1 - 0.6 * joint)
    col = np.stack([v, v * 0.985, v * 0.96], -1)
    col[rust] *= np.array([1.08, 0.98, 0.86])
    col = col * (1 - 0.5 * lichen[..., None]) + np.array([0.70, 0.70, 0.55]) * 0.5 * lichen[..., None]
    save(os.path.join(dst, "t_roof_piode_b.color.png"), to8(col))
    save(os.path.join(dst, "t_roof_piode_nm.normal.png"), normal_map(hgt * 3, 1.2))
    save(os.path.join(dst, "t_roof_piode_r.data.png"), to8(0.85 + 0.05 * grain))


def roof_flat(dst, n=1024):
    """Flat roofs: gravel ballast over the membrane."""
    rng = np.random.default_rng(SEED + 7)
    peb = noise(n, n, 1.3, rng)
    blot = noise(n, n, 50, rng)
    v = 0.82 * (1 + 0.10 * peb + 0.05 * blot)
    col = np.stack([v, v * 0.99, v * 0.96], -1)
    save(os.path.join(dst, "t_roof_flat_b.color.png"), to8(col))
    save(os.path.join(dst, "t_roof_flat_nm.normal.png"), normal_map(peb * 2, 0.9))
    save(os.path.join(dst, "t_roof_flat_r.data.png"), to8(0.93 + 0.03 * blot))


def roof_metal(dst, n=1024, tile_m=2.0):
    """Metal sheet (standing seams down the slope every 0.5 m) of sheds and farm buildings."""
    rng = np.random.default_rng(SEED + 8)
    px = n / tile_m
    X, Y = np.meshgrid(np.arange(n) / px, np.arange(n) / px)
    u = (X / 0.5) % 1.0
    seam = np.exp(-((u - 0.5) / 0.018) ** 2)
    streak = aniso_noise(n, n, 60, 2, rng)
    v = 0.80 * (1 + 0.03 * streak) * (1 - 0.25 * seam) + 0.1 * np.exp(-((u - 0.47) / 0.01) ** 2)
    col = np.stack([v, v * 1.0, v * 1.01], -1)
    save(os.path.join(dst, "t_roof_metal_b.color.png"), to8(col))
    save(os.path.join(dst, "t_roof_metal_nm.normal.png"), normal_map(seam * 8, 1.0))
    save(os.path.join(dst, "t_roof_metal_r.data.png"), to8(0.45 + 0.05 * streak))


def concrete_wall(dst, n=1024, tile_m=4.0):
    """Board-formed concrete of the retaining walls along the roads: the prints of the formwork
    boards (0.25 m) and panels (2 m), tie holes, rain streaks and a darker, mossy foot (v = 0 at the
    bottom of the tile)."""
    rng = np.random.default_rng(SEED + 9)
    px = n / tile_m
    X, Y = np.meshgrid(np.arange(n) / px, np.arange(n) / px)
    Yup = tile_m - Y                                   # height in the tile (image rows go down)
    board = (Yup / 0.25) % 1.0
    bi = np.floor(Yup / 0.25).astype(int)
    panel = (X / 2.0) % 1.0
    pi_ = np.floor(X / 2.0).astype(int)
    tone = 0.66 + 0.035 * np.sin(bi * 12.9898 + pi_ * 78.233) * 1.0
    grain = noise(n, n, 1.0, rng)
    pores = (rng.random((n, n)) > 0.992).astype(np.float32)
    blot = noise(n, n, 45, rng)
    streak = np.clip(aniso_noise(n, n, 160, 10, rng), 0, None)
    v = tone * (1 + 0.035 * grain + 0.05 * blot - 0.035 * streak - 0.12 * pores)
    joint_b = np.minimum(board, 1 - board) < 0.012
    joint_p = np.minimum(panel, 1 - panel) < 0.004
    v = np.where(joint_b, v * 0.88, v)
    v = np.where(joint_p, v * 0.85, v)
    ties = (np.hypot(((X + 0.25) % 0.5) - 0.25, ((Yup + 0.25) % 0.75) - 0.375) < 0.012)
    v = np.where(ties, v * 0.6, v)
    col = np.stack([v * 1.0, v * 1.0, v * 0.985], -1)
    hgt = 0.4 * grain - 1.5 * joint_b - 2.0 * joint_p - 3.0 * ties - 1.0 * pores
    save(os.path.join(dst, "t_wall_concrete_b.color.png"), to8(col))
    save(os.path.join(dst, "t_wall_concrete_nm.normal.png"), normal_map(hgt, 0.6))
    save(os.path.join(dst, "t_wall_concrete_r.data.png"), to8(0.88 + 0.04 * blot))


def walls(dst):
    """The textures of the walls (walls.py): board-formed concrete; the rubble stone of the buildings is
    shared (art/shapes/buildings)."""
    os.makedirs(dst, exist_ok=True)
    concrete_wall(dst)


# roof textures: name -> tile size m (roof_uvs)
ROOF_TILE = {"coppi": 2.0, "tegole": 2.0, "piode": 3.0, "flat": 4.0, "metal": 2.0}


def build(dst):
    """All the textures of the buildings in dst; returns the openings index and the mean colour of
    every tiling texture (the vertex colour that gives a wall or roof a measured tone divides by it)."""
    os.makedirs(dst, exist_ok=True)
    plaster(dst)
    stone_wall(dst)
    plinth(dst)
    roof_coppi(dst)
    roof_tegole(dst)
    roof_piode(dst)
    roof_flat(dst)
    roof_metal(dst)
    idx = openings_atlas(dst)
    means = {}
    for name in ("t_bld_plaster", "t_bld_stone", "t_bld_plinth", "t_roof_coppi", "t_roof_tegole", "t_roof_piode",
                 "t_roof_flat", "t_roof_metal"):
        a = np.asarray(Image.open(os.path.join(dst, name + "_b.color.png")).convert("RGB"), np.float32) / 255.0
        means[name] = [round(float(v), 4) for v in a.reshape(-1, 3).mean(0)]
    json.dump(means, open(os.path.join(dst, "bld_textures.json"), "w"), indent=1)
    return idx, means


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "bld_textures_preview"
    idx, means = build(d)
    print(len(idx), "modules in the atlas", means)
