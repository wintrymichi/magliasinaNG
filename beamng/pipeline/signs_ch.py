"""The Swiss road signs (Ordinanza sulla segnaletica stradale, OSStr / SSV) drawn as textures (v2.7).

Every plate is drawn here from its shapes and the colours of the Swiss standard (SN 640 871): no
photo, no image taken from elsewhere. A plate is described by its OSStr number and, where the
signal carries one, its value, as OpenStreetMap writes them (traffic_sign=CH:2.30[60]):
    plate("2.30", "60") -> Plate(image RGBA, width m, height m, shape)
Codes not in DRAW are not drawn (unknown() tells them apart), so a sign whose look is not known
for sure is left out instead of drawn wrong. The texts are in Italian, as in Ticino.

Sizes: round signals 60 cm, triangles 90 cm (sides), STOP 60 cm, squares 60 cm: the sizes of
roads inside villages and of minor roads; on the motorway and on the main roads outside the
villages the next size up (SIZE_UP, 80 / 120 / 90 cm) where the caller asks for it.
"""
import math, os
from collections import namedtuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# colours of SN 640 871 (RAL), as sRGB
RED = (193, 18, 28)          # RAL 3020 traffic red
BLUE = (0, 83, 135)          # RAL 5017 traffic blue
YELLOW = (247, 181, 0)       # RAL 1023 traffic yellow
GREEN = (0, 131, 81)         # RAL 6024 traffic green (motorway)
WHITE = (241, 240, 234)      # RAL 9016 traffic white
BLACK = (30, 30, 30)         # RAL 9017 traffic black
GREY = (140, 140, 140)       # the greyed symbols of the end signals
SS = 4                       # supersampling of the drawing

Plate = namedtuple("Plate", "img w h shape")


def _font(px, bold=True):
    names = (("DejaVuSans-Bold.ttf", "FreeSansBold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf") if bold else
             ("DejaVuSans.ttf", "FreeSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf"))
    dirs = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/freefont",
            "/usr/share/fonts/truetype/liberation", "C:/Windows/Fonts")
    for n in names:
        for d in dirs:
            f = os.path.join(d, n)
            if os.path.exists(f):
                return ImageFont.truetype(f, int(px))
    return ImageFont.load_default(size=int(px))


class Canvas:
    """A drawing at SS times the texture size; .done() returns the texture, downsampled."""

    def __init__(self, w, h=None):
        self.W, self.H = w, (h or w)
        self.img = Image.new("RGBA", (self.W * SS, self.H * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    # coordinates in units of the texture (0..W, 0..H)
    def _p(self, pts):
        return [(x * SS, y * SS) for x, y in pts]

    def poly(self, pts, fill):
        self.d.polygon(self._p(pts), fill=fill + (255,))

    def circle(self, cx, cy, r, fill):
        self.d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=fill + (255,))

    def rect(self, x0, y0, x1, y1, fill, radius=0):
        if radius:
            self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=radius * SS, fill=fill + (255,))
        else:
            self.d.rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill + (255,))

    def line(self, pts, fill, width):
        self.d.line(self._p(pts), fill=fill + (255,), width=max(1, int(width * SS)), joint="curve")

    def arc(self, cx, cy, r, a0, a1, fill, width):
        self.d.arc([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], a0, a1, fill=fill + (255,),
                   width=max(1, int(width * SS)))

    def text(self, cx, cy, s, height, fill, max_w=None, bold=True, squeeze=1.0):
        """s centred at (cx, cy), cap height about `height`, at most max_w wide (squeezed sideways)."""
        f = _font(height * 1.38 * SS, bold)
        l, t, r, b = f.getbbox(s)
        tw, th = r - l, b - t
        tile = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((4 - l, 4 - t), s, font=f, fill=fill + (255,))
        sx = squeeze
        if max_w is not None and tw * sx > max_w * SS:
            sx = max_w * SS / tw
        tile = tile.resize((max(1, int(tile.width * sx)), tile.height), Image.LANCZOS)
        self.img.alpha_composite(tile, (int(cx * SS - tile.width / 2), int(cy * SS - tile.height / 2)))

    def done(self):
        return self.img.resize((self.W, self.H), Image.LANCZOS)


# ------------------------------------------------------------------ shapes of the signals
def _round(c, fill_inner, ring=RED, n=256):
    """Disk of the prohibition signals: thin white edge, red ring (1/10 of the diameter), inner field."""
    r = n / 2
    c.circle(r, r, r - 0.5, WHITE)
    if ring is not None:
        c.circle(r, r, r * 0.97, ring)
        c.circle(r, r, r * 0.97 - n * 0.10, fill_inner)
    else:
        c.circle(r, r, r * 0.97, fill_inner)


def _number(c, s, n=256, color=BLACK, scale=1.0):
    h = n * (0.36 if len(s) <= 2 else 0.30) * scale
    c.text(n / 2, n / 2, s, h, color, max_w=n * 0.62, squeeze=0.80)


def _end_bars(c, n, cx=None, cy=None, r=None, color=BLACK):
    """The diagonal band of the end signals: five thin parallel lines, lower left to upper right."""
    cx = n / 2 if cx is None else cx
    cy = n / 2 if cy is None else cy
    r = n * 0.46 if r is None else r
    u = np.array([math.cos(math.radians(45)), -math.sin(math.radians(45))])
    v = np.array([u[1], -u[0]])
    for k in range(-2, 3):
        o = np.array([cx, cy]) + v * k * r * 0.055
        a, b = o - u * r * 0.98, o + u * r * 0.98
        c.line([tuple(a), tuple(b)], color, r * 0.022)


def _triangle_up(c, n=256):
    """Danger signal: triangle point up, red border, white field (corners slightly rounded)."""
    h = n * math.sqrt(3) / 2
    top = (n - h) / 2
    P = lambda k: [(n / 2, top + (1 - k) * h * 2 / 3), (n / 2 - k * n / 2, top + h - (1 - k) * h / 3),
                   (n / 2 + k * n / 2, top + h - (1 - k) * h / 3)]
    c.poly(P(1.0), WHITE)
    c.poly(P(0.965), RED)
    c.poly(P(0.71), WHITE)
    return top, h


def _car_side(c, cx, cy, w, color):
    """A car seen from the side (the symbol of the prohibition signals), w wide."""
    h = w * 0.42
    x0, y0 = cx - w / 2, cy - h / 2
    c.poly([(x0, y0 + h * 0.48), (x0 + w * 0.18, y0 + h * 0.42), (x0 + w * 0.30, y0), (x0 + w * 0.72, y0),
            (x0 + w * 0.86, y0 + h * 0.42), (x0 + w, y0 + h * 0.50), (x0 + w, y0 + h * 0.80), (x0, y0 + h * 0.80)], color)
    for fx in (0.22, 0.78):
        c.circle(x0 + w * fx, y0 + h * 0.82, h * 0.20, color)


def _truck_side(c, cx, cy, w, color):
    h = w * 0.50
    x0, y0 = cx - w / 2, cy - h / 2
    c.rect(x0, y0, x0 + w * 0.68, y0 + h * 0.78, color)
    c.poly([(x0 + w * 0.71, y0 + h * 0.22), (x0 + w * 0.90, y0 + h * 0.22), (x0 + w, y0 + h * 0.48),
            (x0 + w, y0 + h * 0.78), (x0 + w * 0.71, y0 + h * 0.78)], color)
    for fx in (0.16, 0.48, 0.85):
        c.circle(x0 + w * fx, y0 + h * 0.84, h * 0.15, color)


def _bicycle(c, cx, cy, w, color):
    r = w * 0.21
    a, b = (cx - w * 0.29, cy + w * 0.12), (cx + w * 0.29, cy + w * 0.12)
    lw = w * 0.045
    for p in (a, b):
        c.arc(p[0], p[1], r, 0, 360, color, lw)
    seat, crank, head = (cx - w * 0.08, cy - w * 0.16), (cx, cy + w * 0.12), (cx + w * 0.20, cy - w * 0.17)
    c.line([a, crank, (cx + w * 0.17, cy - w * 0.10), a], color, lw)
    c.line([seat, crank], color, lw)
    c.line([b, head], color, lw)
    c.line([(head[0] - w * 0.06, head[1] - w * 0.03), (head[0] + w * 0.03, head[1] - w * 0.03)], color, lw)
    c.line([(seat[0] - w * 0.07, seat[1]), (seat[0] + w * 0.05, seat[1])], color, lw)


def _pedestrian(c, cx, cy, h, color):
    """A walking person, h high, facing right."""
    lw = h * 0.10
    c.circle(cx + h * 0.04, cy - h * 0.40, h * 0.09, color)
    hip, sh = (cx - h * 0.02, cy + h * 0.06), (cx + h * 0.03, cy - h * 0.24)
    c.line([sh, hip], color, lw)
    c.line([hip, (cx + h * 0.16, cy + h * 0.27), (cx + h * 0.20, cy + h * 0.47)], color, lw)
    c.line([hip, (cx - h * 0.12, cy + h * 0.26), (cx - h * 0.24, cy + h * 0.45)], color, lw)
    c.line([(sh[0], sh[1] + h * 0.03), (cx + h * 0.18, cy - h * 0.06), (cx + h * 0.26, cy + h * 0.06)], color, lw * 0.85)
    c.line([(sh[0], sh[1] + h * 0.03), (cx - h * 0.14, cy - h * 0.08), (cx - h * 0.18, cy + h * 0.08)], color, lw * 0.85)


def _arrow_up(c, cx, top, bottom, w, color):
    hw = w * 0.5
    head = w * 1.05
    c.rect(cx - hw * 0.42, top + head * 0.8, cx + hw * 0.42, bottom, color)
    c.poly([(cx, top), (cx - hw * 1.15, top + head), (cx + hw * 1.15, top + head)], color)


# ------------------------------------------------------------------ the signals
def s_prohibition(symbol=None, value=None):
    def draw(n=256):
        c = Canvas(n)
        _round(c, WHITE, n=n)
        if symbol == "car":
            _car_side(c, n / 2, n / 2, n * 0.56, BLACK)
        elif symbol == "bike":
            _bicycle(c, n / 2, n / 2, n * 0.60, BLACK)
        elif symbol == "number":
            _number(c, value, n)
        elif symbol in ("weight", "width", "height", "length"):
            s = value + ("t" if symbol == "weight" else "m")
            c.text(n / 2, n / 2, s, n * (0.24 if len(s) <= 3 else 0.19), BLACK, max_w=n * 0.56, squeeze=0.85)
            a = n * 0.05
            if symbol in ("width", "length"):
                for sx in (-1, 1):
                    x = n / 2 + sx * n * 0.33
                    c.poly([(x + sx * a, n / 2), (x - sx * a * 0.4, n / 2 - a * 1.2), (x - sx * a * 0.4, n / 2 + a * 1.2)], BLACK)
            if symbol == "height":
                for sy in (-1, 1):
                    y = n / 2 + sy * n * 0.27
                    c.poly([(n / 2, y - sy * a), (n / 2 - a * 1.2, y - sy * a * 2.2), (n / 2 + a * 1.2, y - sy * a * 2.2)], BLACK)
        elif symbol == "truck_overtake":
            _truck_side(c, n * 0.36, n / 2, n * 0.30, RED)
            _car_side(c, n * 0.66, n / 2 + n * 0.02, n * 0.27, BLACK)
        return c.done()
    return draw, "round"


def s_no_entry(n=256):
    c = Canvas(n)
    c.circle(n / 2, n / 2, n / 2 - 0.5, WHITE)
    c.circle(n / 2, n / 2, n / 2 * 0.97, RED)
    c.rect(n * 0.17, n * 0.42, n * 0.83, n * 0.58, WHITE)
    return c.done()


def s_end_limit(value, n=256):
    c = Canvas(n)
    c.circle(n / 2, n / 2, n / 2 - 0.5, BLACK)
    c.circle(n / 2, n / 2, n / 2 * 0.96, WHITE)
    _number(c, value, n, color=GREY)
    _end_bars(c, n)
    return c.done()


def s_roundabout(n=256):
    """2.41.1: blue disk, three white arrows turning anticlockwise around the centre."""
    c = Canvas(n)
    c.circle(n / 2, n / 2, n / 2 - 0.5, WHITE)
    c.circle(n / 2, n / 2, n / 2 * 0.97, BLUE)
    r, lw = n * 0.25, n * 0.085
    for k in range(3):
        a0 = k * 120 + 25
        c.arc(n / 2, n / 2, r + lw / 2, -(a0 + 72), -a0, WHITE, lw)       # PIL draws the width inwards
        t = math.radians(a0 + 70)                         # the head at the end of the arc, anticlockwise
        p = np.array([n / 2 + r * math.cos(t), n / 2 - r * math.sin(t)])
        d = np.array([-math.sin(t), -math.cos(t)])        # direction of travel at that point
        q = np.array([d[1], -d[0]])
        hs = n * 0.10
        c.poly([tuple(p + d * hs * 1.1), tuple(p - d * hs * 0.1 + q * hs), tuple(p - d * hs * 0.1 - q * hs)], WHITE)
    return c.done()


def s_stop(n=256):
    """3.01: red octagon, white edge, white STOP."""
    c = Canvas(n)
    a = math.pi / 8 + np.arange(8) * math.pi / 4
    oct_ = lambda r: [(n / 2 + r * math.cos(t), n / 2 + r * math.sin(t)) for t in a]
    R = n / 2 / math.cos(math.pi / 8)
    c.poly(oct_(R * 0.999), WHITE)
    c.poly(oct_(R * 0.94), RED)
    c.text(n / 2, n / 2, "STOP", n * 0.25, WHITE, max_w=n * 0.74, squeeze=0.92)
    return c.done()


def s_give_way(n=256):
    """3.02: triangle point down, red border, white field."""
    c = Canvas(n)
    h = n * math.sqrt(3) / 2
    top = (n - h) / 2
    P = lambda k: [(n / 2 - k * n / 2, top + (1 - k) * h / 3), (n / 2 + k * n / 2, top + (1 - k) * h / 3),
                   (n / 2, top + h - (1 - k) * 2 * h / 3)]
    c.poly(P(1.0), WHITE)
    c.poly(P(0.965), RED)
    c.poly(P(0.71), WHITE)
    return c.done()


def s_priority(end=False, n=256):
    """3.03 main road: yellow square on its corner with a white border and a black edge; 3.04 the same
    with the end band."""
    c = Canvas(n)
    D = lambda r: [(n / 2, n / 2 - r), (n / 2 + r, n / 2), (n / 2, n / 2 + r), (n / 2 - r, n / 2)]
    c.poly(D(n / 2 - 0.5), BLACK)
    c.poly(D(n / 2 * 0.96), WHITE)
    c.poly(D(n / 2 * 0.70), YELLOW if not end else (200, 200, 200))
    if end:
        _end_bars(c, n, r=n * 0.47)
    return c.done()


def s_narrowing(n=256):
    """1.07 narrowing: danger triangle, the two edges of the road closing in."""
    c = Canvas(n)
    top, h = _triangle_up(c, n)
    y0, y1 = top + h * 0.45, top + h * 0.86
    w = n * 0.035
    for sx in (-1, 1):
        x_lo, x_mid, x_hi = n / 2 + sx * n * 0.15, n / 2 + sx * n * 0.15, n / 2 + sx * n * 0.065
        c.line([(x_lo, y1), (x_mid, top + h * 0.70), (x_hi, top + h * 0.58), (x_hi, y0)], BLACK, w)
    return c.done()


def s_zone(value, end=False, w=256, h=320):
    """2.59.1 zone (ZONA over the limit), 2.59.2 the end of the zone (greyed, end band)."""
    c = Canvas(w, h)
    c.rect(0, 0, w, h, BLACK, radius=w * 0.05)
    c.rect(w * 0.025, w * 0.025, w - w * 0.025, h - w * 0.025, WHITE, radius=w * 0.04)
    col = GREY if end else BLACK
    c.text(w / 2, h * 0.14, "ZONA", h * 0.10, col, max_w=w * 0.8)
    cx, cy, r = w / 2, h * 0.58, w * 0.36
    if end:
        c.circle(cx, cy, r, GREY)
        c.circle(cx, cy, r * 0.90, WHITE)
    else:
        c.circle(cx, cy, r, RED)
        c.circle(cx, cy, r * 0.80, WHITE)
    c.text(cx, cy, value, r * 0.80, col, max_w=r * 1.3, squeeze=0.8)
    if end:
        _end_bars(c, w, cx=w / 2, cy=h / 2, r=h * 0.50)
    return c.done()


def s_meeting_zone(end=False, w=256, h=320):
    """2.59.3 meeting zone (zona d'incontro): a blue field with a person, a child with a ball, a
    house and a car, the 20 limit above; 2.59.4 its end, greyed with the end band."""
    c = Canvas(w, h)
    c.rect(0, 0, w, h, BLACK, radius=w * 0.05)
    c.rect(w * 0.025, w * 0.025, w - w * 0.025, h - w * 0.025, WHITE, radius=w * 0.04)
    col = GREY if end else BLACK
    cx, cy, r = w / 2, h * 0.19, w * 0.15
    c.circle(cx, cy, r, GREY if end else RED)
    c.circle(cx, cy, r * 0.80, WHITE)
    c.text(cx, cy, "20", r * 0.85, col, max_w=r * 1.3, squeeze=0.8)
    x0, y0, x1, y1 = w * 0.10, h * 0.38, w * 0.90, h * 0.80
    c.rect(x0, y0, x1, y1, GREY if end else BLUE)
    fw = WHITE
    c.poly([(x0 + (x1 - x0) * 0.62, y0 + (y1 - y0) * 0.40), (x0 + (x1 - x0) * 0.78, y0 + (y1 - y0) * 0.22),
            (x0 + (x1 - x0) * 0.94, y0 + (y1 - y0) * 0.40), (x0 + (x1 - x0) * 0.94, y0 + (y1 - y0) * 0.62),
            (x0 + (x1 - x0) * 0.62, y0 + (y1 - y0) * 0.62)], fw)
    _pedestrian(c, x0 + (x1 - x0) * 0.22, y0 + (y1 - y0) * 0.50, (y1 - y0) * 0.70, fw)
    _pedestrian(c, x0 + (x1 - x0) * 0.42, y0 + (y1 - y0) * 0.62, (y1 - y0) * 0.45, fw)
    c.circle(x0 + (x1 - x0) * 0.53, y0 + (y1 - y0) * 0.86, (y1 - y0) * 0.05, fw)
    _car_side(c, x0 + (x1 - x0) * 0.76, y0 + (y1 - y0) * 0.82, (x1 - x0) * 0.32, fw)
    c.text(w / 2, h * 0.89, "ZONA D'INCONTRO", h * 0.05, col, max_w=w * 0.85)
    if end:
        _end_bars(c, w, cx=w / 2, cy=h / 2, r=h * 0.50)
    return c.done()


def s_one_way(w=192, h=256):
    """4.08 one-way street: blue panel, white arrow up."""
    c = Canvas(w, h)
    c.rect(0, 0, w, h, WHITE, radius=w * 0.05)
    c.rect(w * 0.03, w * 0.03, w - w * 0.03, h - w * 0.03, BLUE, radius=w * 0.04)
    _arrow_up(c, w / 2, h * 0.14, h * 0.86, w * 0.42, WHITE)
    return c.done()


def s_dead_end(n=256):
    """4.09 dead end: blue square, a white road ending at a red bar."""
    c = Canvas(n)
    c.rect(0, 0, n, n, WHITE, radius=n * 0.05)
    c.rect(n * 0.03, n * 0.03, n * 0.97, n * 0.97, BLUE, radius=n * 0.04)
    c.rect(n * 0.39, n * 0.30, n * 0.61, n * 0.86, WHITE)
    c.rect(n * 0.22, n * 0.16, n * 0.78, n * 0.30, RED)
    return c.done()


def s_crossing(n=256):
    """4.11 pedestrian crossing: blue square, white triangle, a black person on the stripes."""
    c = Canvas(n)
    c.rect(0, 0, n, n, WHITE, radius=n * 0.05)
    c.rect(n * 0.03, n * 0.03, n * 0.97, n * 0.97, BLUE, radius=n * 0.04)
    c.poly([(n / 2, n * 0.10), (n * 0.08, n * 0.86), (n * 0.92, n * 0.86)], WHITE)
    for k in range(5):
        x = n * 0.22 + k * n * 0.12
        c.rect(x, n * 0.74, x + n * 0.07, n * 0.80, BLACK)
    _pedestrian(c, n / 2, n * 0.50, n * 0.40, BLACK)
    return c.done()


def s_parking(n=256):
    c = Canvas(n)
    c.rect(0, 0, n, n, WHITE, radius=n * 0.05)
    c.rect(n * 0.03, n * 0.03, n * 0.97, n * 0.97, BLUE, radius=n * 0.04)
    c.text(n / 2, n / 2, "P", n * 0.62, WHITE)
    return c.done()


def s_place(name, main=True, end=False, w=512, h=192):
    """4.27 / 4.29 beginning of a place (main road: blue, white letters; minor road: white, black
    letters), 4.28 / 4.30 its end (a red bar across the name)."""
    c = Canvas(w, h)
    bg, fg = (BLUE, WHITE) if main else (WHITE, BLACK)
    c.rect(0, 0, w, h, fg if main else BLACK, radius=h * 0.06)
    c.rect(h * 0.03, h * 0.03, w - h * 0.03, h - h * 0.03, bg, radius=h * 0.05)
    import re
    m = re.match(r"(.*?)\s+(\d+(?:[.,]\d+)?\s*km)$", name.strip())
    lines = [m.group(1), m.group(2)] if m else [name]        # a name with a distance: the distance below
    if len(lines) == 1:
        c.text(w / 2, h / 2, lines[0], h * 0.36, fg, max_w=w * 0.88)
    else:
        c.text(w / 2, h * 0.36, lines[0], h * 0.28, fg, max_w=w * 0.88)
        c.text(w / 2, h * 0.72, lines[1], h * 0.18, fg, max_w=w * 0.88)
    if end:
        c.line([(w * 0.10, h * 0.86), (w * 0.90, h * 0.14)], RED, h * 0.09)
    return c.done()


def s_text_plate(text, w=256, h=96, arrows=False):
    """5.xx supplementary plate: white, thin black edge, black text (a distance, an exception);
    arrows: 5.03 the length of a section (arrows up and down beside the text)."""
    c = Canvas(w, h)
    c.rect(0, 0, w, h, BLACK, radius=h * 0.06)
    c.rect(h * 0.04, h * 0.04, w - h * 0.04, h - h * 0.04, WHITE, radius=h * 0.05)
    words = text.split()
    if len(text) > 18 and len(words) > 1:                # two lines
        cut = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
        c.text(w / 2, h * 0.33, " ".join(words[:cut]), h * 0.22, BLACK, max_w=w * 0.9, bold=False)
        c.text(w / 2, h * 0.68, " ".join(words[cut:]), h * 0.22, BLACK, max_w=w * 0.9, bold=False)
    else:
        c.text(w / 2 + (h * 0.15 if arrows else 0), h / 2, text, h * 0.42, BLACK, max_w=w * (0.62 if arrows else 0.88))
    if arrows:
        x = w * 0.16
        c.line([(x, h * 0.20), (x, h * 0.80)], BLACK, h * 0.05)
        for y, s in ((h * 0.16, 1), (h * 0.84, -1)):
            c.poly([(x, y), (x - h * 0.10, y + s * h * 0.16), (x + h * 0.10, y + s * h * 0.16)], BLACK)
    return c.done()


def s_pass_obstacle(right=True, n=256):
    """2.33 / 2.34 pass the obstacle on the right / left: blue disk, a white arrow pointing down
    to that side (45 degrees)."""
    c = Canvas(n)
    c.circle(n / 2, n / 2, n / 2 - 0.5, WHITE)
    c.circle(n / 2, n / 2, n / 2 * 0.97, BLUE)
    img = c.done()
    a = Canvas(n)
    _arrow_up(a, n / 2, n * 0.18, n * 0.82, n * 0.30, WHITE)
    arrow = a.done().rotate(-135 if right else 135, resample=Image.BICUBIC)   # PIL turns anticlockwise
    img.alpha_composite(arrow)
    return img


def s_curve(right=True, n=256):
    """1.01 / 1.02 curve to the right / left: danger triangle, a black road bending to that side."""
    c = Canvas(n)
    top, h = _triangle_up(c, n)
    s = 1 if right else -1
    w = n * 0.07
    x0 = n / 2 - s * n * 0.05
    pts = [(x0, top + h * 0.88), (x0, top + h * 0.66)]
    for k in range(1, 7):                                  # a quarter circle to the side
        t = k / 6 * math.pi / 3
        r = n * 0.16
        pts.append((x0 + s * r * (1 - math.cos(t)), top + h * 0.66 - r * math.sin(t)))
    c.line(pts, BLACK, w)
    (xa, ya), (xb, yb) = pts[-2], pts[-1]
    d = np.array([xb - xa, yb - ya]); d /= np.linalg.norm(d)
    q = np.array([d[1], -d[0]])
    tip = np.array([xb, yb]) + d * w * 1.6
    c.poly([tuple(tip), tuple(np.array([xb, yb]) + q * w * 1.1), tuple(np.array([xb, yb]) - q * w * 1.1)], BLACK)
    return c.done()


def s_pointer(text, right=True, main=False, w=512, h=128):
    """4.31 / 4.32 direction sign of a main road (blue, white letters) / a minor road (white, black
    letters): a plate with an arrow point on the side it shows; 'A / B' puts two places on two lines."""
    lines = [t.strip() for t in text.split("/") if t.strip()]
    h = h * max(1, len(lines)) * (0.75 if len(lines) > 1 else 1)
    h = int(h)
    c = Canvas(w, h)
    bg, fg = (BLUE, WHITE) if main else (WHITE, BLACK)
    tip = h * 0.45
    def shape(e):
        if right:
            return [(e, e), (w - tip, e), (w - e * 1.4, h / 2), (w - tip, h - e), (e, h - e)]
        return [(w - e, e), (tip, e), (e * 1.4, h / 2), (tip, h - e), (w - e, h - e)]
    c.poly(shape(0.5), fg if main else BLACK)
    c.poly(shape(h * 0.035), bg)
    cx = (w - tip) / 2 + (0 if right else tip)
    step = h / len(lines)
    for k, t in enumerate(lines):
        c.text(cx, step * (k + 0.5), t, min(step * 0.48, h * 0.40), fg, max_w=(w - tip) * 0.86)
    return c.done()


# ------------------------------------------------------------------ catalogue
# code -> (drawer(value) -> RGBA, shape, (width, height) m at the normal size)
R60, T90, Q60 = (0.60, 0.60), (0.90, 0.90 * math.sqrt(3) / 2), (0.60, 0.60)
SIZE_UP = {"round": 0.80 / 0.60, "triangle": 1.20 / 0.90, "octagon": 0.90 / 0.60, "diamond": 0.90 / 0.60}


def _with(fn, *a):
    return lambda v: fn(*a)


DRAW = {
    "1.01": (lambda v: s_curve(right=True), "triangle", T90),
    "1.02": (lambda v: s_curve(right=False), "triangle", T90),
    "1.07": (lambda v: s_narrowing(), "triangle", T90),
    "2.01": (lambda v: s_prohibition()[0](), "round", R60),
    "2.02": (lambda v: s_no_entry(), "round", R60),
    "2.03": (lambda v: s_prohibition("car")[0](), "round", R60),
    "2.05": (lambda v: s_prohibition("bike")[0](), "round", R60),
    "2.16": (lambda v: s_prohibition("weight", v)[0](), "round", R60),
    "2.18": (lambda v: s_prohibition("width", v)[0](), "round", R60),
    "2.19": (lambda v: s_prohibition("height", v)[0](), "round", R60),
    "2.20": (lambda v: s_prohibition("length", v)[0](), "round", R60),
    "2.30": (lambda v: s_prohibition("number", v)[0](), "round", R60),
    "2.45": (lambda v: s_prohibition("truck_overtake")[0](), "round", R60),
    "2.53": (lambda v: s_end_limit(v), "round", R60),
    "2.33": (lambda v: s_pass_obstacle(right=True), "round", R60),
    "2.34": (lambda v: s_pass_obstacle(right=False), "round", R60),
    "2.41.1": (lambda v: s_roundabout(), "round", R60),
    "2.59.1": (lambda v: s_zone(v or "30"), "rect", (0.60, 0.75)),
    "2.59.2": (lambda v: s_zone(v or "30", end=True), "rect", (0.60, 0.75)),
    "2.59.3": (lambda v: s_meeting_zone(), "rect", (0.60, 0.75)),
    "2.59.4": (lambda v: s_meeting_zone(end=True), "rect", (0.60, 0.75)),
    "3.01": (lambda v: s_stop(), "octagon", R60),
    "3.02": (lambda v: s_give_way(), "triangle_down", T90),
    "3.03": (lambda v: s_priority(), "diamond", R60),
    "3.04": (lambda v: s_priority(end=True), "diamond", R60),
    "4.08": (lambda v: s_one_way(), "rect", (0.45, 0.60)),
    "4.09": (lambda v: s_dead_end(), "rect", Q60),
    "4.11": (lambda v: s_crossing(), "rect", Q60),
    "4.17": (lambda v: s_parking(), "rect", Q60),
    "4.27": (lambda v: s_place(v, main=True), "rect", (1.20, 0.45)),
    "4.28": (lambda v: s_place(v, main=True, end=True), "rect", (1.20, 0.45)),
    "4.29": (lambda v: s_place(v, main=False), "rect", (1.20, 0.45)),
    "4.30": (lambda v: s_place(v, main=False, end=True), "rect", (1.20, 0.45)),
    # direction signs: the value is 'right|Place' or 'left|Place A / Place B'
    "4.31": (lambda v: _pointer(v, True), "pointer", None),
    "4.32": (lambda v: _pointer(v, False), "pointer", None),
    "5.01": (lambda v: s_text_plate(v), "plate", (0.60, 0.225)),
    "5.03": (lambda v: s_text_plate(v, arrows=True), "plate", (0.60, 0.225)),
    "text": (lambda v: s_text_plate(v), "plate", (0.60, 0.225)),
}
# 2.30.1 / 2.53.1, the general limit of the villages, are the 2.30 / 2.53 signal over a plate
# with the word "generale"
GENERAL = {"2.30.1": "2.30", "2.53.1": "2.53"}
# codes that need a value to be drawn
NEEDS_VALUE = {"4.31", "4.32", "2.16", "2.18", "2.19", "2.20", "2.30", "2.53", "4.27", "4.28", "4.29", "4.30", "5.01", "5.03", "text"}


def _pointer(v, main):
    side, _, text = v.partition("|")
    return s_pointer(text, right=(side == "right"), main=main)


def known(code, value=None):
    code = GENERAL.get(code, code)
    return code in DRAW and (code not in NEEDS_VALUE or bool(value))


def plate(code, value=None, big=False):
    """Plate(img, w, h, shape) of a signal, None when it is not drawn here."""
    if not known(code, value):
        return None
    fn, shape, size = DRAW[GENERAL.get(code, code)]
    img = fn(value)
    if size is None:                                     # a pointer: 1.00 m long, as high as its lines
        size = (1.00, 1.00 * img.height / img.width)
    k = SIZE_UP.get(shape, 1.0) if big else 1.0
    return Plate(img, size[0] * k, size[1] * k, shape)


def parse(tag):
    """The plates of an OSM traffic_sign value, top to bottom: 'CH:2.59.1[30];2.02,5.01[100 m]' ->
    [[('2.59.1', '30')], [('2.02', None), ('5.01', '100 m')]]: ';' separates the signs of one pole,
    ',' a signal from the plates under it. Codes of other countries -> []."""
    tag = tag.strip()
    if not tag.startswith("CH:"):
        return []
    out = []
    for sign in _split(tag[3:], ";"):
        group = []
        for part in _split(sign, ","):
            part = part.strip()
            if part.startswith("CH:"):
                part = part[3:]
            code, val = part, None
            if "[" in part and part.endswith("]"):
                code, val = part[:part.index("[")], part[part.index("[") + 1:-1]
            group.append((code.strip(), val))
        out.append(group)
    return out


def _split(s, sep):
    """Split on sep outside brackets."""
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch == "[") - (ch == "]")
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [q for q in out if q.strip()]


def sheet(path, items, cell=200):
    """A contact sheet of plates [(code, value)] for review."""
    cols = 6
    rows = (len(items) + cols - 1) // cols
    W = Image.new("RGB", (cols * cell, rows * (cell + 24)), (120, 140, 120))
    d = ImageDraw.Draw(W)
    for i, (code, val) in enumerate(items):
        p = plate(code, val)
        x, y = (i % cols) * cell, (i // cols) * (cell + 24)
        if p is None:
            d.text((x + 8, y + 8), f"{code} not drawn", fill=(0, 0, 0))
            continue
        img = p.img
        s = (cell - 16) / max(p.w, p.h)
        img = img.resize((max(1, int(p.w * s)), max(1, int(p.h * s))), Image.LANCZOS)
        W.paste(img, (x + (cell - img.width) // 2, y + (cell - img.height) // 2), img)
        d.text((x + 6, y + cell + 4), f"{code} {val or ''}"[:30], fill=(0, 0, 0))
    W.save(path)
