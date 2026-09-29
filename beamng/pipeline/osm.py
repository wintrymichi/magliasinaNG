"""OpenStreetMap data of the area (download_osm.py -> data/osm/osm_area.json) in local coordinates.

OSM records what swisstopo and the cadastral survey do not: one-way streets, street names, speed
limits, pedestrian crossings, stop and give-way points, traffic signals, bus stops, street lamps,
guard rails. Everything taken from it is matched to the swissTLM3D network (network.py), which
stays the geometry of reference. (c) OpenStreetMap contributors, ODbL.
"""
import json, os
import numpy as np
import shapely
from config import DATA, wgs_to_local

PATH = os.path.join(DATA, "osm", "osm_area.json")
# highway values a car drives on
DRIVE = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
         "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
         "service", "track", "road"}
_cache = {}


def available():
    return os.path.exists(PATH)


def load():
    """(ways, nodes): ways with 'xy' (n, 2) local coordinates and 'line', nodes with 'x', 'y'."""
    if "data" in _cache:
        return _cache["data"]
    d = json.load(open(PATH, encoding="utf-8"))
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
