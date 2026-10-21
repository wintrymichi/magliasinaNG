"""The tiles of the area the street reference analyses (v3.0.40), for the matrix of street_reference.yml: squares of
SIZE m with at least LEAST open photos near buildings (street_fetch.near_buildings), or with a fountain of OSM and
a photo near it; the busiest first, at most MAX.

    python street_tiles.py [MAX]   -> prints the JSON list [{"name", "rect"}] (rect "x0 y0 x1 y1")
"""
import json, sys
from collections import Counter
import street_fetch

SIZE = 400.0
LEAST = 15
MAX = 64


def tiles(most=MAX):
    import street_fountains
    cat = [p for p in street_fetch.catalog() if p["src"] in ("mapillary", "panoramax")]
    near = street_fetch.near_buildings(cat)
    key = lambda x, y: (int(x // SIZE), int(y // SIZE))
    n = Counter(key(p["x"], p["y"]) for p in near)
    pts = street_fountains.points((-1e9, -1e9, 1e9, 1e9))
    has_photo = set(key(p["x"], p["y"]) for p in cat)
    fnt = Counter(key(q["x"], q["y"]) for q in pts)
    pick = {k for k, c in n.items() if c >= LEAST} | {k for k in fnt if k in has_photo}
    ranked = sorted(pick, key=lambda k: (-(n[k] + 20 * fnt[k]), k))[:most]
    out = [{"name": "t%d_%d" % (i, j), "rect": "%g %g %g %g" % (i * SIZE, j * SIZE, (i + 1) * SIZE, (j + 1) * SIZE)}
           for i, j in ranked]
    print(len(pick), "tiles with photos,", len(out), "kept;", sum(n[k] for k in ranked), "photos near buildings,",
          sum(fnt[k] for k in ranked), "fountains", file=sys.stderr)
    return out


if __name__ == "__main__":
    print(json.dumps(tiles(int(sys.argv[1]) if len(sys.argv) > 1 else MAX)))
