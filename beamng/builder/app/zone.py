"""An area picked on the map -> the zone file the pipeline builds (config.MAGLIASO_ZONE), with the checks and the
estimates the app shows before a build.

The pipeline works in one local frame for all of Switzerland (config.py: x = (E - E0) / K, y = (N - N0) / K, the
Malcantone's origin), as the Ticino zones do: the data measured for the Malcantone (photos, hand-made lists) stay
where they belong and are left out of any other area by its box. The finished level is moved to its own origin
afterwards (recenter.py). A zone is:
  - the playable area: the rectangle picked (axis-aligned in the local frame), at most MAX_SIDE m a side;
  - the terrain block: TER_SIZE samples TER_SQUARE m apart (12.3 km) centred on it, on the Malcantone's sample grid.
"""
import json
import math
import os
import re

from pyproj import Transformer

from . import HERE

# config.py of the pipeline (checked by beamng/builder/tests/test_builder.py): the local frame and the terrain grid
E0, N0 = 2710830.0, 1094360.0
K = 1.0001374973449562
TER_X0, TER_Y0 = -7230.0, -4731.0
TER_SQUARE = 1.5
TER_SIZE = 8192

MAX_SIDE = 8400.0           # m: a Ticino zone's core and its overlap (7,680 + 2 x 300), 2 km inside the terrain block
MIN_SIDE = 500.0
MARGIN_DEG = 0.012          # about 1 km: cantons and OpenStreetMap extracts are taken this far round the area
SWISS_OSM = "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf"

_to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
_regions = None


def regions():
    global _regions
    if _regions is None:
        import shapely
        from shapely.geometry import shape
        d = json.load(open(os.path.join(HERE, "data", "regions.json"), encoding="utf-8"))
        _regions = {
            "cantons": [(c["code"], c["name"], shape(c["geometry"])) for c in d["cantons"]],
            "neighbours": [(n["url"], n["name"], shape(n["geometry"])) for n in d["neighbours"]],
            "switzerland": shape(d["switzerland"]),
        }
        for k in ("cantons", "neighbours"):
            for _, _, g in _regions[k]:
                shapely.prepare(g)
    return _regions


_probe = None


def survey_open(code):
    """True / False: the canton's cadastral survey answered with features in the last probe (app/data/
    sources_probe.json, tools/probe_sources.py); None: not probed."""
    global _probe
    if _probe is None:
        p = os.path.join(HERE, "data", "sources_probe.json")
        try:
            _probe = json.load(open(p, encoding="utf-8")).get("cantons", {})
        except (OSError, ValueError):
            _probe = {}
    return _probe.get(code, {}).get("survey_open")


def to_local(lat, lon):
    e, n = _to_lv95.transform(lon, lat)
    return (e - E0) / K, (n - N0) / K


def to_wgs(x, y):
    lon, lat = _to_wgs.transform(E0 + x * K, N0 + y * K)
    return lat, lon


def slug(name, n=22):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower().encode("ascii", "ignore").decode()).strip("_")
    return (s or "area")[:n].strip("_")


def rect(bbox):
    """(x0, y0, x1, y1) local of a WGS84 box (south, west, north, east): the box of its four corners."""
    s, w, n, e = bbox
    pts = [to_local(la, lo) for la in (s, n) for lo in (w, e)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def terrain_origin(x0, y0, x1, y1):
    """South-west sample of the terrain block centred on the rectangle, on the pipeline's sample grid."""
    half = (TER_SIZE - 1) * TER_SQUARE / 2
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tx = TER_X0 + round((cx - half - TER_X0) / TER_SQUARE) * TER_SQUARE
    ty = TER_Y0 + round((cy - half - TER_Y0) / TER_SQUARE) * TER_SQUARE
    return tx, ty


def check(bbox):
    """What the app shows for a picked box: sizes, cantons, extracts, estimates, and what stops a build."""
    import shapely
    s, w, n, e = [float(v) for v in bbox]
    out = {"errors": [], "warnings": []}
    if not (s < n and w < e):
        out["errors"].append("The box is empty.")
        return out
    x0, y0, x1, y1 = rect((s, w, n, e))
    sx, sy = x1 - x0, y1 - y0
    out.update(side_x_m=round(sx), side_y_m=round(sy), km2=round(sx * sy / 1e6, 1))
    if max(sx, sy) > MAX_SIDE:
        out["errors"].append("The area is %.1f x %.1f km: at most %.1f km a side (the terrain block is 12.3 km and needs "
                             "2 km round the area)." % (sx / 1000, sy / 1000, MAX_SIDE / 1000))
    if min(sx, sy) < MIN_SIDE:
        out["errors"].append("The area is too small: at least %.1f km a side." % (MIN_SIDE / 1000))
    R = regions()
    box = shapely.box(w, s, e, n)
    inside = box.intersection(R["switzerland"]).area / box.area
    out["swiss_share"] = round(inside, 3)
    if not R["switzerland"].buffer(0.003).contains(box.centroid):
        out["errors"].append("The middle of the area is not in Switzerland: the pipeline needs the Swiss survey and "
                             "swisstopo's terrain there.")
    elif inside < 0.5:
        out["errors"].append("Only %d %% of the area lies in Switzerland: at least half of it must." % round(100 * inside))
    elif inside < 0.97:
        out["warnings"].append("%d %% of the area lies outside Switzerland: there it gets only Copernicus terrain, "
                               "OpenStreetMap and land cover (no Swiss survey, no buildings in 3D)." % round(100 * (1 - inside)))
    wide = box.buffer(MARGIN_DEG)
    out["cantons"] = [c for c, _, g in R["cantons"] if g.intersects(wide)]
    out["canton_names"] = [nm for c, nm, g in R["cantons"] if g.intersects(wide)]
    # cantons whose cadastral survey is not open on geodienste.ch (tools/probe_sources.py): there the roads come from
    # swissTLM3D's lines alone, with no yards, pavements, traffic islands or survey walls
    closed = [nm for c, nm, g in R["cantons"] if g.intersects(box) and survey_open(c) is False]
    out["survey_closed"] = closed
    if closed:
        out["warnings"].append("No open cadastral survey in %s: there the roads are drawn from swissTLM3D's lines alone "
                               "(no yards, pavements, traffic islands or survey walls), with less detail than in the "
                               "Malcantone." % ", ".join(closed))
    out["osm_extracts"] = [SWISS_OSM] + [u for u, _, g in R["neighbours"] if g.intersects(wide)]
    km2 = sx * sy / 1e6
    # GitHub runner (4 cores): a dense 64 km2 Ticino zone took 1 h 46 min of stages and about 3 h of finishing steps
    out["estimate_hours"] = round(1.2 + 0.065 * km2, 1)
    out["estimate_disk_gb"] = round(12 + 0.45 * km2)
    tx, ty = terrain_origin(x0, y0, x1, y1)
    side = (TER_SIZE - 1) * TER_SQUARE
    out["terrain_wgs"] = [list(to_wgs(tx, ty)), list(to_wgs(tx + side, ty)), list(to_wgs(tx + side, ty + side)),
                          list(to_wgs(tx, ty + side))]
    out["area_wgs"] = [list(to_wgs(x0, y0)), list(to_wgs(x1, y0)), list(to_wgs(x1, y1)), list(to_wgs(x0, y1))]
    d = math.hypot((x0 + x1) / 2, (y0 + y1) / 2)
    out["km_from_frame_origin"] = round(d / 1000, 1)
    out["ok"] = not out["errors"]
    return out


def make_zone(name, title, bbox):
    """The zone file of a build (config.ZONE) for the WGS84 box (south, west, north, east)."""
    x0, y0, x1, y1 = rect(bbox)
    tx, ty = terrain_origin(x0, y0, x1, y1)
    a = [(E0 + x0 * K, N0 + y0 * K), (E0 + x1 * K, N0 + y1 * K)]
    return {
        "name": name, "level": name, "title": title,
        "builder": True, "bbox_wgs": [float(v) for v in bbox],
        "core_local": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        "area_lv95": [round(a[0][0], 2), round(a[0][1], 2), round(a[1][0], 2), round(a[1][1], 2)],
        "ter_size": TER_SIZE, "ter_x0": tx, "ter_y0": ty,
        "biome": "Switzerland",
    }


def recenter_shift(zone):
    """(dx, dy) that moves the finished level so the middle of its terrain block is at the origin, on the terrain grid
    (BeamNG keeps positions in float32: at 100-200 km from the frame's origin one step is 8-16 mm, and the cars
    shake; near the origin it is under a tenth of a mm)."""
    half = (zone["ter_size"] - 1) * TER_SQUARE / 2
    cx, cy = zone["ter_x0"] + half, zone["ter_y0"] + half
    return -round(cx / TER_SQUARE) * TER_SQUARE, -round(cy / TER_SQUARE) * TER_SQUARE
