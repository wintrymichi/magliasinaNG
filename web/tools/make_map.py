"""Draws web/map.svg, the map on the website: the playable area (area.polygon(), the same polygon
the level is built in), the road and trail network of OpenStreetMap (beamng/dati/osm_area.json.gz)
and the villages with a spawn point, labelled at their bus stops.

Needs shapely and pyproj (as the pipeline). Run from anywhere: python web/tools/make_map.py
"""
import gzip, json, os, statistics, sys
import shapely

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "beamng", "pipeline"))
import area                                    # noqa: E402
from config import wgs_to_local                # noqa: E402

OUT = os.path.join(ROOT, "web", "map.svg")
W = 900                                        # svg width in px; height follows the area
PAD = 500.0                                    # m of context around the area

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
         "primary_link", "secondary_link", "tertiary_link"}
MINOR = {"unclassified", "residential", "living_street", "service", "pedestrian"}
TRAIL = {"track", "path", "footway", "steps", "bridleway", "cycleway"}

# spawn point -> bus stop name in OSM (the part before the comma)
VILLAGES = {
    "Agno": "Agno", "Aranno": "Aranno", "Arosio": "Arosio", "Astano": "Astano", "Banco": "Banco",
    "Bedigliora": "Bedigliora", "Bioggio": "Bioggio", "Bosco Luganese": "Bosco Luganese", "Breno": "Breno",
    "Cademario": "Cademario", "Caslano": "Caslano", "Cassina d'Agno": "Cassina d'Agno",
    "Castelrotto": "Castelrotto", "Cimo": "Cimo", "Gravesano": "Gravesano", "Magliaso": "Magliaso",
    "Manno": "Manno Paese", "Miglieglia": "Miglieglia", "Molinazzo": "Molinazzo di Monteggio",
    "Monteggio": "Monteggio", "Neggio": "Neggio Paese", "Novaggio": "Novaggio", "Ponte Tresa": "Ponte Tresa",
    "Pura": "Pura", "Purasca": "Purasca", "Sessa": "Sessa", "Vernate": "Vernate Paese",
}
LAKE = (45.979, 8.906)                         # a point on the water of the gulf of Agno, for the label
BIG = {"Agno", "Bioggio", "Caslano", "Magliaso", "Ponte Tresa", "Pura", "Gravesano", "Novaggio"}


def main():
    A = area.polygon()
    x0, y0, x1, y1 = A.bounds
    x0, y0, x1, y1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
    s = W / (x1 - x0)
    H = round((y1 - y0) * s)
    frame = shapely.box(x0, y0, x1, y1)
    Ab = A.buffer(30)

    def pt(x, y):
        return f"{(x - x0) * s:.1f},{(y1 - y) * s:.1f}"

    def path(line):
        out = []
        for g in getattr(line, "geoms", [line]):
            if g.geom_type == "LineString" and len(g.coords) > 1:
                c = list(g.coords)
                out.append("M" + " ".join(pt(*p) for p in c))
        return "".join(out)

    osm = json.load(gzip.open(os.path.join(ROOT, "beamng", "dati", "osm_area.json.gz")))
    inside = {"major": [], "minor": [], "trail": []}
    outside = {"major": [], "minor": [], "trail": []}
    stops = {}
    for e in osm["elements"]:
        t = e.get("tags", {})
        if e["type"] == "node" and t.get("highway") == "bus_stop" and t.get("name"):
            stops.setdefault(t["name"].split(",")[0].strip(), []).append(wgs_to_local(e["lat"], e["lon"]))
        if e["type"] != "way" or "geometry" not in e or "highway" not in t or t.get("area") == "yes":
            continue
        hw = t["highway"]
        cls = "major" if hw in MAJOR else "minor" if hw in MINOR else "trail" if hw in TRAIL else None
        if cls is None or len(e["geometry"]) < 2:
            continue
        line = shapely.LineString([wgs_to_local(p["lat"], p["lon"]) for p in e["geometry"]])
        line = line.intersection(frame)
        if line.is_empty:
            continue
        ins = line.intersection(Ab)
        outs = line.difference(Ab)
        if not ins.is_empty:
            inside[cls].append(path(ins.simplify(2.0)))
        if not outs.is_empty:
            outside[cls].append(path(outs.simplify(4.0)))

    outline = A.simplify(5.0)
    ring = "M" + " ".join(pt(*p) for p in outline.exterior.coords) + "Z"

    labels = []
    for name, stop in VILLAGES.items():
        P = stops.get(stop)
        if not P:
            print("no bus stop for", name)
            continue
        x = statistics.median(p[0] for p in P)
        y = statistics.median(p[1] for p in P)
        labels.append((name, x, y))

    lx, ly = wgs_to_local(*LAKE)
    out_lake = (f'<text class="w" x="{(lx - x0) * s:.1f}" y="{(y1 - ly) * s:.1f}">Lake Lugano</text>')

    # scale bar: 2 km
    sb = 2000 * s
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-labelledby="t"><title id="t">Map of the playable area: roads, trails and the 27 '
           f'villages with a spawn point</title>',
           '<style>.o{fill:none;stroke:#b9b3a4}.i{fill:none;stroke:#2a2b27}.t{stroke-dasharray:3 2}'
           '.l{font:600 13px Archivo,system-ui,sans-serif;fill:#1c1d1a;paint-order:stroke;stroke:#f3f0e8;'
           'stroke-width:4px;stroke-linejoin:round}.l.b{font-size:15px;font-weight:700}'
           '.d{fill:#c2410c;stroke:#f3f0e8;stroke-width:1.5}'
           '.w{font:italic 500 14px Archivo,system-ui,sans-serif;fill:#3f6f8a;letter-spacing:.04em}'
           '.s{font:12px "IBM Plex Mono",ui-monospace,monospace;fill:#5d5f58}</style>',
           f'<path d="{ring}" fill="#e7e2d4" stroke="none"/>']
    for cls, w in (("trail", 0.5), ("minor", 0.6), ("major", 1.1)):
        extra = " t" if cls == "trail" else ""
        out.append(f'<path class="o{extra}" stroke-width="{w}" d="{"".join(outside[cls])}"/>')
    for cls, w in (("trail", 0.6), ("minor", 0.9), ("major", 2.0)):
        extra = " t" if cls == "trail" else ""
        out.append(f'<path class="i{extra}" stroke-width="{w}" d="{"".join(inside[cls])}"/>')
    out.append(f'<path d="{ring}" fill="none" stroke="#c2410c" stroke-width="1.5"/>')
    out.append(out_lake)
    for name, x, y in labels:
        X, Y = (x - x0) * s, (y1 - y) * s
        b = " b" if name in BIG else ""
        out.append(f'<circle class="d" cx="{X:.1f}" cy="{Y:.1f}" r="{4 if b else 3}"/>'
                   f'<text class="l{b}" x="{X + 7:.1f}" y="{Y + 4:.1f}">{name.replace("&", "&amp;")}</text>')
    out.append(f'<g transform="translate(24,{H - 28})"><path d="M0,0h{sb:.1f}" stroke="#1c1d1a" stroke-width="2"/>'
               f'<path d="M0,-5v10M{sb / 2:.1f},-3v6M{sb:.1f},-5v10" stroke="#1c1d1a" stroke-width="1.5"/>'
               f'<text class="s" x="0" y="20">0</text><text class="s" x="{sb - 22:.1f}" y="20">2 km</text></g>')
    out.append(f'<g transform="translate({W - 30},40)"><path d="M0,14L0,-14M-6,-6L0,-14L6,-6" fill="none" '
               f'stroke="#1c1d1a" stroke-width="1.5"/><text class="s" x="-4" y="30">N</text></g>')
    out.append("</svg>")
    open(OUT, "w", encoding="utf-8").write("\n".join(out))
    print(OUT, W, H, os.path.getsize(OUT) // 1024, "kB", len(labels), "villages")


if __name__ == "__main__":
    main()
