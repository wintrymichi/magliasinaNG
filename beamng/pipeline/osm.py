"""OpenStreetMap data of the area in local coordinates: data/osm/osm_area.json where download_osm.py
has fetched it, else the extract the release is built with, dati/osm_area.json.gz (download_osm.py
--pin refreshes it), so the one-way streets and the signs of a release do not change with OSM.

OSM records what swisstopo and the cadastral survey do not: one-way streets, street names, speed
limits, pedestrian crossings, stop and give-way points, traffic signals, bus stops, street lamps,
guard rails. Everything taken from it is matched to the swissTLM3D network (network.py), which
stays the geometry of reference. (c) OpenStreetMap contributors, ODbL.
"""
import gzip, json, os
import numpy as np
import shapely
from config import DATA, wgs_to_local

PATH = os.path.join(DATA, "osm", "osm_area.json")
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
PINNED = os.path.join(DATI, "osm_area.json.gz")
# highway values a car drives on
DRIVE = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
         "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
         "service", "track", "road"}
_cache = {}


def source(path=PATH, pinned=PINNED):
    """The file to read: the download, else the extract kept in the repository; None without both. With
    MAGLIASO_OSM_PINNED=1 (build_level.py, the v2.8 workflows) always the extract: a level built on the PC is the one built
    on GitHub."""
    if os.environ.get("MAGLIASO_OSM_PINNED") == "1":
        return pinned if os.path.exists(pinned) else None
    return path if os.path.exists(path) else (pinned if os.path.exists(pinned) else None)


def read(path):
    return json.load(gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8"))


def available():
    return source() is not None


def load():
    """(ways, nodes): ways with 'xy' (n, 2) local coordinates and 'line', nodes with 'x', 'y'."""
    if "data" in _cache:
        return _cache["data"]
    d = read(source())
    ways, nodes = [], []
    for e in d["elements"]:
        if e["type"] == "way" and "geometry" in e:
            g = [q for q in e["geometry"] if q]
            if len(g) < 2:
                continue
            x, y = wgs_to_local(np.array([q["lat"] for q in g]), np.array([q["lon"] for q in g]))
            xy = np.column_stack([x, y])
            ways.append({"id": e["id"], "tags": e.get("tags", {}), "xy": xy, "line": shapely.LineString(xy),
                         "nodes": e.get("nodes", [])})
        elif e["type"] == "node":
            x, y = wgs_to_local(e["lat"], e["lon"])
            nodes.append({"id": e["id"], "tags": e.get("tags", {}), "x": float(x), "y": float(y)})
    _cache["data"] = (ways, nodes)
    return ways, nodes


POIS = os.path.join(DATA, "osm", "pois.json")
POIS_PINNED = os.path.join(DATI, "osm_pois.json.gz")
# points of interest whose building has a shop front on the ground floor (v2.2)
POI_KEYS = ("shop", "amenity", "craft", "office", "tourism")


def pois():
    """[(x, y, kind)] of the shops, bars, restaurants, offices, workshops and hotels of the area (download_osm.py
    POIS, else the extract kept in the repository); kind: 'shop=bakery', 'amenity=bar' ..."""
    src = source(POIS, POIS_PINNED)
    if src is None:
        return []
    out = []
    for e in read(src)["elements"]:
        c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        if c is None:
            continue
        t = e.get("tags", {})
        k = next((k for k in POI_KEYS if k in t), None)
        if k is None:
            continue
        x, y = wgs_to_local(c["lat"], c["lon"])
        out.append((float(x), float(y), "%s=%s" % (k, t[k])))
    return out


def oneway_dir(tags):
    """+1 one-way in the direction of the way, -1 against it, 0 both ways."""
    ow = tags.get("oneway")
    if ow in ("yes", "true", "1"):
        return 1
    if ow == "-1":
        return -1
    if ow in ("no", "false", "0", "reversible", "alternating"):
        return 0
    if tags.get("junction") in ("roundabout", "circular") or tags.get("highway") in ("motorway", "motorway_link"):
        return 1
    return 0


def match_lines(P, ways, max_d=6.0, max_angle=35.0, step=4.0):
    """For a polyline P (n, 2): per sample every `step` m, the index of the nearest way (of `ways`)
    within max_d m that runs the same way or the opposite (angle below max_angle), and the sign of
    the direction (+1 along P, -1 against it); -1 / 0 where none."""
    if not ways:
        return np.zeros(0, int), np.zeros(0, int)
    key = id(ways)
    if _cache.get("tree_key") != key:
        _cache["tree"] = shapely.STRtree([w["line"] for w in ways])
        _cache["tree_key"] = key
    tree = _cache["tree"]
    L = shapely.LineString(P)
    n = max(int(np.ceil(L.length / step)), 1)
    s = (np.arange(n) + 0.5) * L.length / n
    pts = shapely.line_interpolate_point(L, s)
    ahead = shapely.line_interpolate_point(L, np.minimum(s + 1.0, L.length))
    behind = shapely.line_interpolate_point(L, np.maximum(s - 1.0, 0.0))
    t = shapely.get_coordinates(ahead) - shapely.get_coordinates(behind)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    idx = np.full(n, -1)
    sgn = np.zeros(n, int)
    cos_max = np.cos(np.radians(max_angle))
    for k in range(n):
        cand = tree.query(pts[k], predicate="dwithin", distance=max_d)
        if not len(cand):
            continue
        dist = shapely.distance(pts[k], [ways[c]["line"] for c in cand])
        for c in cand[np.argsort(dist)]:
            line = ways[c]["line"]
            a = line.project(pts[k])
            p1 = line.interpolate(max(a - 1.0, 0.0))
            p2 = line.interpolate(min(a + 1.0, line.length))
            u = np.array([p2.x - p1.x, p2.y - p1.y])
            nu = np.hypot(*u)
            if nu < 1e-6:
                continue
            cs = float(u @ t[k]) / nu
            if abs(cs) >= cos_max:
                idx[k], sgn[k] = c, (1 if cs > 0 else -1)
                break
    return idx, sgn
