"""Original procedural textures of the landmarks (v3.0.40): churches, chapels and bell towers. Like bld_textures.py,
nothing here comes from a photograph: the reference photos of the churches of the Malcantone (landmarks_pack.py) were
looked at for shapes, proportions and colours only.

Written by build(dst) next to the textures of the buildings:
- the landmarks atlas t_bld_landmark (2048 px, PPM px per metre), alpha-clipped like the openings atlas, with an
  emissive map (the clock faces are lit at night, as most church clocks of the area): the open bell chambers
  (one, two or three arches on granite columns, the bell in the dark behind), the clock faces, the portals of the
  churches (round-arched with a painted lunette, or square with a granite frame and a pediment), the oculus over the
  portal, tall round-arched windows, the arrow slits of the old towers and the quoins (cantonali: long and short
  granite blocks in turn along a corner, a strip that tiles upwards). index: bld_landmark.json;
- t_bld_ashlar: squared granite in courses (the cornices, string courses and plinths of the landmarks).
    python landmark_textures.py <folder>
"""
import json, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter
from bld_textures import Canvas, ao_map, emissive, normal_map, noise, save, to8, sill, GRANITE
import bld_textures

PPM = 128                     # atlas pixels per metre
ATLAS = (2048, 1024)
SEED = 40
BRONZE = (0.36, 0.27, 0.15)
DARK = (0.05, 0.045, 0.04)    # the inside of a bell chamber
DIAL = (0.93, 0.91, 0.84)
WOOD_DOOR = (0.36, 0.23, 0.13)


class LCanvas(Canvas):
    """A module of the landmarks atlas (its own pixels per metre)."""

    def __init__(self, w, h, rng):
        saved = bld_textures.PPM
        bld_textures.PPM = PPM
        try:
            super().__init__(w, h, rng)
        finally:
            bld_textures.PPM = saved

    def arch(self, x0, x1, y0, y1):
        """Mask of a round-arched opening from x0 to x1, its sides from y0 up to the springing, the top at y1."""
        r = (x1 - x0) / 2
        cx, cy = x0 + r, y1 - r
        return self.box(x0, y0, x1, cy) | (((self.X - cx) ** 2 + (self.Y - cy) ** 2 < r * r) & (self.Y >= cy))

    def ashlar(self, color=GRANITE, amp=0.05):
        """Dressed granite: fine speckle, a little tone between the blocks."""
        r = self.rng
        sp = r.standard_normal((self.H, self.W)).astype(np.float32)
        dark = (sp > 2.1) * -0.22 + (sp < -2.4) * 0.15
        mid = noise(self.H, self.W, 8, r, wrap=False) * amp
        return np.asarray(color, np.float32)[None, None] * (1 + dark + mid)[..., None]


def bell_chamber(rng, n=2, w=None, h=2.7):
    """The open bell chamber of a tower face: n round arches (1, 2, 3) side by side, separated by granite colonnettes
    with capitals, a granite frame and a sill; the dark inside with the bell's outline hanging in the middle arch."""
    aw = {1: 1.05, 2: 0.82, 3: 0.72}[n]
    col_w = 0.18
    fw = 0.16
    W = w or (n * aw + (n - 1) * col_w + 2 * fw + 0.04)
    cv = LCanvas(W, h, rng)
    x = (W - (n * aw + (n - 1) * col_w)) / 2
    y0, y1 = 0.12, h - 0.06
    frame = cv.arch(x - fw, x + n * aw + (n - 1) * col_w + fw, 0.0, y1 + 0.05) if n == 1 else \
        cv.box(x - fw, 0.0, x + n * aw + (n - 1) * col_w + fw, y1 - 0.25) | \
        cv.arch(x - fw, x + n * aw + (n - 1) * col_w + fw, y1 - 0.25 - (n * aw + (n - 1) * col_w + 2 * fw) / 2, y1 + 0.05)
    cv.paint(frame, cv.ashlar(), height=0.04, rough=0.72)
    for k in range(n):
        xa = x + k * (aw + col_w)
        m = cv.arch(xa, xa + aw, y0, y1 - 0.12)
        depth = np.clip((cv.Y - y0) / (y1 - y0), 0, 1)
        inside = np.asarray(DARK, np.float32)[None, None] * (1.0 + 0.6 * (1 - depth))[..., None]
        cv.paint(m, inside, height=-0.25, rough=0.95)
        # the bell in the middle arch (or the first): a bronze bell shape with its shoulder lit from the front
        if k == n // 2:
            bx = xa + aw / 2
            top = y1 - 0.12 - aw / 2 - 0.05
            bh = min(0.75, aw * 0.85)
            yy = (top - cv.Y) / bh                                  # 0 at the crown, 1 at the lip
            half = np.where((yy >= 0) & (yy <= 1), aw * (0.17 + 0.16 * np.clip(yy, 0, 1) ** 1.6), 0)
            bell = (np.abs(cv.X - bx) < half) & (yy >= 0) & (yy <= 1)
            shade = 0.55 + 0.6 * np.clip(1 - np.abs(cv.X - bx) / np.maximum(half, 1e-3), 0, 1)
            cv.paint(bell & m, np.asarray(BRONZE, np.float32)[None, None] * shade[..., None], height=-0.12, rough=0.4)
            yoke = cv.box(bx - aw * 0.32, top, bx + aw * 0.32, top + 0.07) & m
            cv.paint(yoke, (0.12, 0.10, 0.08), height=-0.1, rough=0.8)
        # the colonnette and its capital between this arch and the next
        if k < n - 1:
            xc = xa + aw
            spring = y1 - 0.12 - aw / 2
            cv.paint(cv.box(xc + 0.04, y0, xc + col_w - 0.04, spring - 0.12), cv.ashlar(), height=0.05, rough=0.7)
            cv.paint(cv.box(xc, spring - 0.12, xc + col_w, spring), cv.ashlar((0.68, 0.67, 0.64)), height=0.06, rough=0.7)
            cv.paint(cv.box(xc - 0.01, y0 - 0.02, xc + col_w + 0.01, y0 + 0.08), cv.ashlar(), height=0.06, rough=0.7)
    sill(cv, x - fw, x + n * aw + (n - 1) * col_w + fw, 0.0, 0.12, "granite", over=0.04)
    return cv


def clock(rng, d=1.6):
    """A painted clock face: a light dial in a dark ring, the hour marks and Roman-style ticks, two black hands;
    round (transparent around it). The dial glows at night (emissive)."""
    cv = LCanvas(d, d, rng)
    c = d / 2
    r = np.hypot(cv.X - c, cv.Y - c)
    ang = np.arctan2(cv.X - c, cv.Y - c)                         # 0 up, clockwise
    ring = (r < c - 0.01) & (r >= c - 0.10)
    dial = r < c - 0.10
    cv.paint(ring, cv.ashlar((0.20, 0.19, 0.18)), height=0.03, rough=0.5)
    cv.paint(dial, cv.painted(DIAL, 0.03), height=0.0, rough=0.6, lit=1.0)
    # the hour marks: twelve bars between 0.68 and 0.86 of the dial's radius, thicker at 12, 3, 6, 9
    rd = c - 0.10
    for k in range(12):
        a = k * np.pi / 6
        wdt = 0.035 if k % 3 else 0.06
        dx, dy = np.sin(a), np.cos(a)
        along = (cv.X - c) * dx + (cv.Y - c) * dy
        across = np.abs((cv.X - c) * dy - (cv.Y - c) * dx)
        mark = (along > 0.68 * rd) & (along < 0.88 * rd) & (across < wdt / 2 * d / 1.6)
        cv.paint(mark & dial, (0.08, 0.08, 0.08), height=0.01, rough=0.5, lit=0.0)
    minute = (np.abs(((ang + 2 * np.pi) % (np.pi / 30)) - np.pi / 60) > np.pi / 60 - 0.012) & (r > 0.9 * rd) & (r < 0.95 * rd)
    cv.paint(minute & dial, (0.15, 0.15, 0.15), height=0.01, rough=0.5, lit=0.0)
    for a, ln, wdt in ((np.radians(305), 0.52, 0.05), (np.radians(60), 0.78, 0.03)):    # about ten past ten
        dx, dy = np.sin(a), np.cos(a)
        along = (cv.X - c) * dx + (cv.Y - c) * dy
        across = np.abs((cv.X - c) * dy - (cv.Y - c) * dx)
        hand = (along > -0.08 * rd) & (along < ln * rd) & (across < wdt / 2 * d / 1.6)
        cv.paint(hand, (0.05, 0.05, 0.05), height=0.02, rough=0.4, lit=0.0)
    cv.paint(r < 0.04 * d / 1.6, (0.05, 0.05, 0.05), height=0.03, rough=0.4, lit=0.0)
    return cv


def portal(rng, kind="arch", ww=1.7, wh=3.0):
    """The main door of a church: a wooden double door with panels in a granite frame; 'arch': round-arched, the
    lunette over the door painted (a fresco in warm faded colours); 'square': a square door, a frame with ears
    and a small pediment over it."""
    fw = 0.24
    if kind == "arch":
        W, H = ww + 2 * fw + 0.04, wh + ww / 2 + fw + 0.05
    else:
        W, H = ww + 2 * fw + 0.30, wh + fw + 0.55
    cv = LCanvas(W, H, rng)
    x0 = (W - ww) / 2
    x1 = x0 + ww
    if kind == "arch":
        outer = cv.arch(x0 - fw, x1 + fw, 0.0, wh + ww / 2 + fw)
        inner = cv.arch(x0, x1, 0.0, wh + ww / 2)
        cv.paint(outer & ~inner, cv.ashlar(), height=0.06, rough=0.7)
        # the voussoirs: radial joints in the frame of the arch
        c, cy = (x0 + x1) / 2, wh
        ang = np.arctan2(cv.Y - cy, cv.X - c)
        joints = (np.abs(((ang + np.pi) % (np.pi / 9)) - np.pi / 18) < 0.012) & (cv.Y > cy) & outer & ~inner
        cv.col[joints] *= 0.6
        lun = inner & (cv.Y >= wh + 0.05)
        t = noise(cv.H, cv.W, 10, rng, wrap=False)
        fresco = np.stack([0.72 + 0.10 * t, 0.58 + 0.08 * t, 0.42 + 0.06 * noise(cv.H, cv.W, 6, rng, wrap=False)], -1)
        halo = (np.hypot(cv.X - c, cv.Y - (wh + ww * 0.28)) < ww * 0.12)
        fresco[halo] = (0.80, 0.66, 0.30)
        robe = cv.box(c - ww * 0.12, wh + 0.05, c + ww * 0.12, wh + ww * 0.2)
        fresco[robe] = fresco[robe] * 0.5 + np.array([0.32, 0.38, 0.55]) * 0.5
        cv.paint(lun, fresco, height=-0.06, rough=0.9)
        cv.paint(cv.box(x0, wh - 0.02, x1, wh + 0.05), cv.ashlar(), height=0.0, rough=0.7)       # the lintel
    else:
        outer = cv.box(x0 - fw, 0.0, x1 + fw, wh + fw)
        ears = cv.box(x0 - fw - 0.10, wh - 0.10, x1 + fw + 0.10, wh + fw)
        cv.paint(outer | ears, cv.ashlar(), height=0.06, rough=0.7)
        # the pediment: a low triangle over the cornice
        c = (x0 + x1) / 2
        ped = (cv.Y >= wh + fw + 0.05) & (cv.Y < wh + fw + 0.05 + 0.45 * (1 - np.abs(cv.X - c) / (ww / 2 + fw + 0.15)))
        cv.paint(ped & cv.box(x0 - fw - 0.15, 0, x1 + fw + 0.15, H), cv.ashlar(), height=0.05, rough=0.7)
        cv.paint(cv.box(x0 - fw - 0.15, wh + fw - 0.02, x1 + fw + 0.15, wh + fw + 0.06), cv.ashlar((0.70, 0.69, 0.66)),
                 height=0.08, rough=0.7)
        inner = cv.box(x0, 0.0, x1, wh)
    door = cv.box(x0, 0.0, x1, wh)
    wood = cv.wood(WOOD_DOOR, vertical=True, amp=0.10)
    cv.paint(door, wood, height=-0.05, rough=0.75)
    # two leaves of three panels each, and the shadow of the reveal
    for k in range(2):
        lx0, lx1 = x0 + k * ww / 2, x0 + (k + 1) * ww / 2
        for p in range(3):
            py0 = 0.25 + p * (wh - 0.5) / 3
            py1 = py0 + (wh - 0.5) / 3 - 0.14
            pm = cv.box(lx0 + 0.12, py0, lx1 - 0.12, py1)
            cv.col[pm] *= 0.82
            cv.hgt[pm] -= 0.015
            cv.col[cv.box(lx0 + 0.12, py1 - 0.03, lx1 - 0.12, py1)] *= 1.25
    cv.col[cv.box(x0 + ww / 2 - 0.012, 0, x0 + ww / 2 + 0.012, wh)] *= 0.4
    cv.col[cv.box(x0, wh - 0.10, x1, wh) & door] *= 0.6
    cv.paint(cv.box(x0 - fw, 0.0, x1 + fw, 0.10), cv.ashlar(), height=0.04, rough=0.7)            # the step
    return cv


def oculus(rng, d=1.2):
    """The round window over the portal: a granite ring, leaded glass in a star of radial bars."""
    cv = LCanvas(d, d, rng)
    c = d / 2
    r = np.hypot(cv.X - c, cv.Y - c)
    ang = np.arctan2(cv.Y - c, cv.X - c)
    ring = (r < c - 0.01) & (r >= c - 0.16)
    glass = r < c - 0.16
    cv.paint(ring, cv.ashlar(), height=0.05, rough=0.7)
    t = noise(cv.H, cv.W, 6, rng, wrap=False)
    g = np.stack([0.20 + 0.04 * t, 0.24 + 0.05 * t, 0.26 + 0.04 * t], -1)
    cv.paint(glass, g, height=-0.06, rough=0.15, lit=0.6)
    bars = ((np.abs(((ang + np.pi) % (np.pi / 4)) - np.pi / 8) < 0.04) | (np.abs(r - 0.42 * c) < 0.015)) & glass
    cv.paint(bars, (0.10, 0.10, 0.10), height=-0.04, rough=0.5, lit=0.0)
    return cv


def tall_window(rng, ww=0.95, wh=3.2):
    """A tall round-arched window of a nave, granite frame, leaded glass in small diamonds."""
    fw = 0.15
    W, H = ww + 2 * fw + 0.04, wh + fw + 0.12
    cv = LCanvas(W, H, rng)
    x0, y0 = (W - ww) / 2, 0.10
    outer = cv.arch(x0 - fw, x0 + ww + fw, y0, y0 + wh + fw)
    inner = cv.arch(x0, x0 + ww, y0, y0 + wh)
    cv.paint(outer & ~inner, cv.ashlar(), height=0.04, rough=0.7)
    u, v = cv.X * 6.5, cv.Y * 4.6
    lattice = (np.abs(((u + v) % 1.0) - 0.5) < 0.05) | (np.abs(((u - v) % 1.0) - 0.5) < 0.05)
    tint = 1 + 0.15 * noise(cv.H, cv.W, 14, rng, wrap=False)
    gl = np.array([0.26, 0.30, 0.31], np.float32)[None, None] * tint[..., None]
    gl = np.where(lattice[..., None], np.array([0.10, 0.10, 0.10], np.float32), gl)
    cv.paint(inner, gl, height=-0.05, rough=0.15, lit=0.5)
    sill(cv, x0 - fw, x0 + ww + fw, 0.0, 0.10, "granite", over=0.03)
    return cv


def slit(rng, ww=0.16, wh=0.95):
    """An arrow slit of an old tower: a narrow opening in a granite frame."""
    fw = 0.12
    cv = LCanvas(ww + 2 * fw, wh + 2 * fw, rng)
    cv.paint(cv.box(0, 0, ww + 2 * fw, wh + 2 * fw), cv.ashlar(), height=0.03, rough=0.75)
    cv.paint(cv.box(fw, fw, fw + ww, fw + wh), DARK, height=-0.2, rough=0.95)
    return cv


QUOIN_H = 0.36          # m, height of one block of the quoins
QUOIN_LONG, QUOIN_SHORT = 0.62, 0.36


def quoins(rng, n=8):
    """A strip of quoins for one face of a corner: n blocks of QUOIN_H m, long and short in turn, the corner at
    x = 0 (the next face takes the strip one block higher, so that a long block there meets a short one here);
    the wall shows beside the short blocks (transparent)."""
    W, H = QUOIN_LONG + 0.02, n * QUOIN_H
    cv = LCanvas(W, H, rng)
    base = cv.ashlar(amp=0.07)
    for k in range(n):
        y0 = k * QUOIN_H
        w = QUOIN_LONG if k % 2 == 0 else QUOIN_SHORT
        blk = cv.box(0.0, y0 + 0.012, w, y0 + QUOIN_H - 0.012)
        tone = 1 + 0.06 * rng.standard_normal()
        edge = np.clip(np.minimum.reduce([cv.X - 0.0, w - cv.X, cv.Y - y0, y0 + QUOIN_H - cv.Y]) / 0.03, 0, 1)
        cv.paint(blk, base * tone * (0.82 + 0.18 * edge)[..., None], height=0.03, rough=0.72)
        cv.paint(cv.box(0.0, y0, w + 0.01, y0 + 0.012) | cv.box(0.0, y0 + QUOIN_H - 0.012, w + 0.01, y0 + QUOIN_H),
                 (0.42, 0.41, 0.39), height=0.0, rough=0.9)
    return cv


def modules(rng):
    out = {"bells_1": bell_chamber(rng, 1), "bells_2": bell_chamber(rng, 2), "bells_3": bell_chamber(rng, 3),
           "clock": clock(rng), "portal_arch": portal(rng, "arch"), "portal_square": portal(rng, "square"),
           "oculus": oculus(rng), "tall_window": tall_window(rng), "slit": slit(rng), "quoins": quoins(rng),
           "chapel_door": portal(rng, "arch", ww=1.1, wh=2.1)}
    return out


def atlas(dst):
    rng = np.random.default_rng(SEED)
    mods = modules(rng)
    rects = bld_textures.pack(mods, size=ATLAS)
    AW, AH = ATLAS
    col = np.full((AH, AW, 3), 0.5, np.float32)
    hgt = np.zeros((AH, AW), np.float32)
    rough = np.full((AH, AW), 0.85, np.float32)
    alpha = np.zeros((AH, AW), np.float32)
    glow = np.zeros((AH, AW), np.float32)
    index = {}
    for k, (x, y, w, h) in rects.items():
        cv = mods[k]
        col[y:y + h, x:x + w] = cv.col
        hgt[y:y + h, x:x + w] = cv.hgt
        rough[y:y + h, x:x + w] = cv.rough
        alpha[y:y + h, x:x + w] = cv.alpha
        glow[y:y + h, x:x + w] = cv.lit if k == "clock" else 0.0        # only the clock faces light up at night
        index[k] = {"uv": [x / AW, 1 - (y + h) / AH, (x + w) / AW, 1 - y / AH], "w": round(cv.w, 4), "h": round(cv.h, 4)}
    a = alpha > 0.5
    if (~a).any():
        idx = distance_transform_edt(~a, return_distances=False, return_indices=True)
        col = col[idx[0], idx[1]]
    save(os.path.join(dst, "t_bld_landmark_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_landmark_o.data.png"), to8(alpha))
    save(os.path.join(dst, "t_bld_landmark_nm.normal.png"), normal_map(hgt * PPM, 1.2, wrap=False))
    save(os.path.join(dst, "t_bld_landmark_r.data.png"), to8(rough))
    save(os.path.join(dst, "t_bld_landmark_ao.data.png"), ao_map(hgt * PPM, 6, 0.12, wrap=False))
    save(os.path.join(dst, "t_bld_landmark_e.color.png"), emissive(glow))
    json.dump({"ppm": PPM, "size": list(ATLAS), "modules": index}, open(os.path.join(dst, "bld_landmark.json"), "w"), indent=1)
    return index


def ashlar(dst, n=1024, tile=2.0):
    """Squared granite in courses (tile m square): blocks 0.30-0.45 m high and 0.5-1.1 m long, thin joints, the faces
    a little dished and speckled, some blocks warmer, some darker."""
    rng = np.random.default_rng(SEED + 1)
    px = n / tile
    ids = np.zeros((n, n), np.int32)
    joint = np.zeros((n, n), bool)
    y, k = 0, 0
    while y < n:
        h = int(round(rng.uniform(0.30, 0.45) * px))
        h = min(h, n - y) if n - y - h > 0.25 * px else n - y
        x = int(rng.integers(0, int(0.6 * px)))
        while x < n + int(1.2 * px):
            w = int(round(rng.uniform(0.5, 1.1) * px))
            xs = np.arange(x, x + w) % n
            ids[y:y + h][:, xs] = k
            joint[y:y + h][:, xs[:3]] = True
            k += 1
            x += w
        joint[y:y + 3] = True
        y += h
    tone = rng.uniform(0.88, 1.08, k)
    warm = rng.random(k) < 0.25
    base = np.asarray(GRANITE, np.float32)[None, None] * tone[ids][..., None]
    base[warm[ids]] *= np.array([1.04, 1.0, 0.93], np.float32)
    g1 = noise(n, n, 0.7, rng); g2 = noise(n, n, 5, rng); g3 = noise(n, n, 30, rng)
    sp = rng.standard_normal((n, n)).astype(np.float32)
    dist = distance_transform_edt(~joint)
    dome = np.clip(dist / (0.03 * px), 0, 1) ** 0.5
    col = base * (1 + 0.04 * g1 + 0.05 * g2 + 0.04 * g3 + (sp > 2.1) * -0.2)[..., None] * (0.85 + 0.15 * dome)[..., None]
    col[joint] = np.array([0.52, 0.51, 0.48]) * (0.9 + 0.1 * g2[joint, None])
    hgt = dome * 2.0 + 0.4 * g1
    hgt[joint] = -1.0
    save(os.path.join(dst, "t_bld_ashlar_b.color.png"), to8(col))
    save(os.path.join(dst, "t_bld_ashlar_nm.normal.png"), normal_map(hgt, 0.8))
    save(os.path.join(dst, "t_bld_ashlar_r.data.png"), to8(np.where(joint, 0.95, 0.74 + 0.04 * g1)))
    save(os.path.join(dst, "t_bld_ashlar_ao.data.png"), ao_map(hgt, 4, 0.10))


def build(dst):
    """The landmark textures in dst; returns the atlas index and the mean colour of the ashlar."""
    os.makedirs(dst, exist_ok=True)
    idx = atlas(dst)
    ashlar(dst)
    a = np.asarray(Image.open(os.path.join(dst, "t_bld_ashlar_b.color.png")).convert("RGB"), np.float32) / 255.0
    return idx, [round(float(v), 4) for v in a.reshape(-1, 3).mean(0)]


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "landmark_textures_preview"
    idx, mean = build(d)
    print(len(idx), "modules", mean)
