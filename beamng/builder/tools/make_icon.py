"""The switzerlandNG icon (web/icon.svg): the Swiss cross built as a node-and-beam truss, like the soft-body vehicles
of BeamNG.drive. python tools/make_icon.py [out.svg]

The cross keeps the official proportions (arms one sixth longer than wide, 20/32 of the square). It is the cross of
the Swiss flag on its red square, not the Swiss coat of arms: the shield with the cross may only be used by the
Confederation (Wappenschutzgesetz, SR 232.21), the cross and the flag may be used by anyone where it does not mislead.
web/icon-32.png is a 32 px copy for browsers without SVG icons (rendered from the SVG in a browser)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "web", "icon.svg")
S = 64.0                    # the tile
EDGE = 2.4                  # the white beam along the outline (it widens the cross by half of it on every side)
W = 12.0 - EDGE             # arm width of the outline, so that the cross is 12 wide with its beam (6 of 32)
L = 14.0                    # arm length (7 of 32): 40 of 64 from end to end with the beam
ORANGE = "#ff6a13"          # the nodes
BRACE = "#d9d4d3"           # the beams inside the cross

c = S / 2
a, b = c - W / 2, c + W / 2
lo, hi = a - L, b + L
OUTLINE = [(a, lo), (b, lo), (b, a), (hi, a), (hi, b), (b, b), (b, hi), (a, hi), (a, b), (lo, b), (lo, a), (a, a)]
BOXES = [((a, lo), (b, a)), ((b, a), (hi, b)), ((a, b), (b, hi)), ((lo, a), (a, b)), ((a, a), (b, b))]
MIDDLES = [((x0 + x1) / 2, (y0 + y1) / 2) for (x0, y0), (x1, y1) in BOXES]
BEAMS = [e for (x0, y0), (x1, y1) in BOXES for e in (((x0, y0), (x1, y1)), ((x1, y0), (x0, y1)))]
BEAMS += [((a, a), (b, a)), ((b, a), (b, b)), ((b, b), (a, b)), ((a, b), (a, a))]


def f(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def lines(E, color, width):
    return "".join(f'<line x1="{f(p[0])}" y1="{f(p[1])}" x2="{f(q[0])}" y2="{f(q[1])}" stroke="{color}" '
                   f'stroke-width="{f(width)}" stroke-linecap="round"/>' for p, q in E)


def dots(P, r, fill):
    return "".join(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill="{fill}"/>' for x, y in P)


cross = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in OUTLINE) + " Z"
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
<title>switzerlandNG</title>
<defs>
<linearGradient id="red" x1="0" y1="0" x2=".4" y2="1"><stop offset="0" stop-color="#ee3124"/><stop offset="1" stop-color="#b8140b"/></linearGradient>
<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".16"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="1.1" stdDeviation="1.1" flood-color="#5a0700" flood-opacity=".45"/></filter>
</defs>
<rect width="64" height="64" rx="14" fill="url(#red)"/>
<rect width="64" height="64" rx="14" fill="url(#gloss)"/>
<g filter="url(#shadow)"><path d="{cross}" fill="#fff" stroke="#fff" stroke-width="{f(EDGE)}" stroke-linejoin="round"/>{dots(OUTLINE, 2.5, "#fff")}</g>
{lines(BEAMS, BRACE, 0.85)}
{dots(OUTLINE, 1.35, ORANGE)}{dots(MIDDLES, 1.0, "#c9c2c0")}
</svg>
"""
open(OUT, "w", encoding="utf-8").write(svg)
print("icon", os.path.abspath(OUT), len(svg), "bytes")
