"""The playable area of the map (v2.0): the boundary drawn by the user, widened by AREA_MARGIN,
joined with the Street View route (ROUTE_MARGIN around it, so the whole original road stays in) and
with the cantonal road from Magliaso along the lake to Agno and up the Vedeggio valley to Gravesano
(dati/cantonale_gravesano.json, strade_extra.py): EXTRA_ROAD_MARGIN around it and the strip between
it and the side P1-P2 of the boundary, so no bare slope is left between the map and the road.

Everything that is generated only where it can be seen or driven (roads, buildings, trees, raster
data at 0.5 m) uses this polygon; the terrain block (config.TER_*) is a square around it and the
distant backdrop starts at the edge of that square.
"""
import json, os
import numpy as np
import shapely
from config import (AREA_MARGIN, BOUNDARY, EXTRA_ROAD_MARGIN, K, ROUTE_MARGIN, TER_SIZE, TER_SQUARE, TER_X0,
                    TER_X1, TER_Y0, TER_Y1, local_to_lv95, lv95_to_local, wgs_to_local)

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
_cache = {}


def boundary():
    """The quadrilateral drawn by the user (local coordinates)."""
    return shapely.Polygon([wgs_to_local(lat, lon) for lat, lon in BOUNDARY])


def route():
    """The Street View route (main run of the calibrated poses)."""
    if "route" not in _cache:
        poses = json.load(open(os.path.join(DATI, "poses.json")))
        _cache["route"] = shapely.LineString([p["pos"][:2] for p in poses if p["main_run"]])
    return _cache["route"]


EXTRA_ROADS = ("cantonale_gravesano.json",)


def extra_roads():
    """The roads added beyond the boundary (dati/<file> of EXTRA_ROADS, strade_extra.py), as local
    lines."""
    if "extra" not in _cache:
        out = []
        for name in EXTRA_ROADS:
            f = os.path.join(DATI, name)
            if os.path.exists(f):
                E, N = np.array(json.load(open(f, encoding="utf-8"))["lv95"], np.float64).T
                out.append(shapely.LineString(np.column_stack(lv95_to_local(E, N))))
        _cache["extra"] = out
    return _cache["extra"]


def polygon():
    """The playable area (local coordinates)."""
    if "area" not in _cache:
        parts = [boundary().buffer(AREA_MARGIN, join_style="mitre"), route().buffer(ROUTE_MARGIN)]
        p1, p2 = np.asarray(boundary().exterior.coords)[:2]
        for road in extra_roads():
            # the strip between the road and the side P1-P2 (the road runs from its south end, near
            # P1, to its north end, near P2), and the road with its margin
            parts.append(shapely.Polygon(list(road.coords) + [tuple(p2), tuple(p1)]).buffer(0))
            parts.append(road.buffer(EXTRA_ROAD_MARGIN))
        _cache["area"] = shapely.union_all(parts)
    return _cache["area"]


def bounds(margin=0.0):
    """(x_min, y_min, x_max, y_max) of the area, widened by `margin` m."""
    x0, y0, x1, y1 = polygon().bounds
    return x0 - margin, y0 - margin, x1 + margin, y1 + margin


def raster_bounds(res=0.5, margin=60.0):
    """Bounds of the 0.5 m data grids (dtm05, dsm05, landcover05): the area + margin, snapped to res."""
    x0, y0, x1, y1 = bounds(margin)
    return (np.floor(x0 / res) * res, np.floor(y0 / res) * res, np.ceil(x1 / res) * res, np.ceil(y1 / res) * res)


def block_bounds(res=2.0, margin=100.0):
    """Bounds of the coarse grids covering the whole terrain block (dtm2, ortho), snapped to res."""
    x0, y0, x1, y1 = TER_X0 - margin, TER_Y0 - margin, TER_X1 + margin, TER_Y1 + margin
    return (np.floor(x0 / res) * res, np.floor(y0 / res) * res, np.ceil(x1 / res) * res, np.ceil(y1 / res) * res)


def terrain_bounds():
    """(x_min, y_min, x_max, y_max) of the terrain vertices."""
    return TER_X0, TER_Y0, TER_X1, TER_Y1


def lv95_polygon(margin=0.0):
    """The area in LV95 (E, N), widened by `margin` m."""
    g = polygon().buffer(margin) if margin else polygon()
    return shapely.transform(g, lambda c: np.column_stack(local_to_lv95(c[:, 0], c[:, 1])))


def tiles_1km(margin=200.0):
    """LV95 kilometre tiles ('EEEE-NNNN', south-west corner in km) that touch the area + margin."""
    g = lv95_polygon(margin)
    shapely.prepare(g)
    e0, n0, e1, n1 = g.bounds
    out = []
    for e in range(int(np.floor(e0 / 1000)), int(np.floor(e1 / 1000)) + 1):
        for n in range(int(np.floor(n0 / 1000)), int(np.floor(n1 / 1000)) + 1):
            if g.intersects(shapely.box(e * 1000, n * 1000, (e + 1) * 1000, (n + 1) * 1000)):
                out.append(f"{e}-{n}")
    return out


def lv95_rect_tiles(e0, n0, e1, n1):
    """LV95 kilometre tiles covering the rectangle [e0, e1] x [n0, n1]."""
    return [f"{e}-{n}" for e in range(int(np.floor(e0 / 1000)), int(np.floor(e1 / 1000)) + 1)
            for n in range(int(np.floor(n0 / 1000)), int(np.floor(n1 / 1000)) + 1)]


def check():
    """The terrain block covers the area with room to spare."""
    x0, y0, x1, y1 = bounds()
    tx0, ty0, tx1, ty1 = terrain_bounds()
    m = min(x0 - tx0, y0 - ty0, tx1 - x1, ty1 - y1)
    return {"area_km2": polygon().area / 1e6, "bounds": [round(v, 1) for v in (x0, y0, x1, y1)],
            "terrain": [tx0, ty0, tx1, ty1], "terrain_side_m": (TER_SIZE - 1) * TER_SQUARE,
            "min_margin_m": round(m, 1), "K": K}


if __name__ == "__main__":
    print(check())
    print(len(tiles_1km()), "km tiles")
