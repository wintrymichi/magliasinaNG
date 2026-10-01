"""Surfaces of the roads and paths after OpenStreetMap (v2.4): asphalt, gravel, dirt, setts, cobbles.

swissTLM3D only says hard or natural (BELAGSART), and the cadastral survey draws every road polygon
alike, so up to v2.3 a surveyed gravel road was asphalt. OSM tags the surface of many ways
(surface=*, else tracktype=* on tracks): the category of the nearest OSM way is taken where one is
tagged, the swissTLM3D surface of the nearest line where none is (hard -> asphalt, natural -> gravel
on roads, dirt on paths). The few OSM areas with a surface (car parks, squares) give theirs to the
yards and squares under them.

  line_categories(net)  -> category of every swissTLM3D line (network.py)
  polygon_zones(net, p) -> [(category, part)] of a survey road polygon: one part where the lines and
                           ways in it agree, else the parts nearest to each.
(c) OpenStreetMap contributors, ODbL.
"""
import numpy as np
import shapely
import osm

# OSM surface=* -> category; the values not listed (wood, metal: bridges and footbridges) keep
# the swissTLM3D surface. Local spellings seen in the area (terra, terreno_e_erba ...) included.
CATEGORY = {
    "asphalt": "hard", "paved": "hard", "concrete": "hard", "concrete:plates": "hard",
    "concrete:lanes": "hard", "cement": "hard", "chipseal": "hard",
    "gravel": "gravel", "fine_gravel": "gravel", "compacted": "gravel", "pebblestone": "gravel",
    "unpaved": "gravel", "terra_ghiaia": "gravel",
    "ground": "dirt", "dirt": "dirt", "earth": "dirt", "mud": "dirt", "sand": "dirt", "grass": "dirt",
    "rock": "dirt", "terra": "dirt", "sterrato": "dirt", "sterrato--": "dirt", "terreno_e_erba": "dirt",
    "terreno_erba": "dirt", "terreno_e_pebblestone": "dirt", "terreno_e_pobblestone": "dirt",
    "terra_pobblestone": "dirt", "stepping_stones": "dirt", "woodchips": "dirt",
    # granite setts and pavers: the squares, lanes and steps of the village cores
    "sett": "sett", "paving_stones": "sett", "grass_paver": "sett",
    # rounded river stones (acciottolato), the old paving of the nuclei; OSM 'cobblestone' is
    # ambiguous, in the area it is used on the lanes and steps of the nuclei like unhewn_cobblestone
    "unhewn_cobblestone": "cobble", "cobblestone": "cobble",
}
# material of every category on carriageways, on yards and squares, on paths (build_level.road_materials)
MATS = {
    "road": {"hard": "mp_road_asphalt", "gravel": "mp_road_gravel", "dirt": "mp_road_dirt",
             "sett": "mp_road_sett", "cobble": "mp_road_cobble"},
    "hard": {"hard": "mp_hard_asphalt", "gravel": "mp_hard_gravel", "dirt": "mp_hard_dirt",
             "sett": "mp_hard_sett", "cobble": "mp_hard_cobble"},
    "path": {"hard": "mp_path_paved", "gravel": "mp_path_gravel", "dirt": "mp_path_dirt",
             "sett": "mp_path_sett", "cobble": "mp_path_cobble"},
}
ROAD_MATS = tuple(MATS["road"].values())
HARD_MATS = tuple(MATS["hard"].values())
PATH_MATS = tuple(MATS["path"].values())
# tracks without surface: grade1 solid, grade2 gravel, grade3-5 mostly earth and grass
TRACKTYPE = {"grade1": "hard", "grade2": "gravel", "grade3": "dirt", "grade4": "dirt", "grade5": "dirt"}
NEAR_WAY = 6.0          # m, a line station takes the surface of an OSM way this close and running alike
NEAR_ZONE = 8.0         # m, a point of a survey polygon takes the surface of the nearest way this close
MIN_SHARE = 0.5         # of a line's length matched to tagged ways for the line to take their surface
CELL = 1.0              # m, grid of the points that split a survey polygon between its lines and ways
MIN_PIECE = 25.0        # m2, smaller pieces of a survey polygon join its main surface
# half width of the OSM ways (m), to tell the carriageway of a street from a path that meets it
HALF_WIDTH = {"motorway": 6.0, "trunk": 4.5, "primary": 4.0, "secondary": 3.5, "tertiary": 3.5,
              "unclassified": 3.0, "residential": 3.0, "living_street": 3.0, "road": 3.0,
              "pedestrian": 2.5, "service": 2.2, "track": 1.8}
_cache = {}


def category(tags):
    """Category of an OSM way or area from its tags, None if it says nothing usable."""
    c = CATEGORY.get(tags.get("surface", ""))
    if c is None and tags.get("highway") == "track":
        c = TRACKTYPE.get(tags.get("tracktype", ""))
    return c


def fallback(seg):
    """Category of a swissTLM3D line without OSM: its own surface (BELAGSART)."""
    if seg["surface"] == "hard":
        return "hard"
    return "gravel" if seg["kind"] == "road" else "dirt"


def ways():
    """(lines, categories, tree) of the OSM highways (categories None where untagged) and
    [(category, polygon)] of the OSM areas with a surface."""
    if "ways" in _cache:
        return _cache["ways"]
    lines, cats, areas, hw = [], [], [], []
    if osm.available():
        W, _ = osm.load()
        for w in W:
            t = w["tags"]
            closed = len(w["xy"]) >= 4 and np.allclose(w["xy"][0], w["xy"][-1])
            c = category(t)
            if closed and (t.get("area") == "yes" or "highway" not in t):
                if c is not None and ("amenity" in t or "highway" in t or "area:highway" in t
                                      or set(t) <= {"surface", "name", "area", "note", "source"}):
                    poly = shapely.make_valid(shapely.Polygon(w["xy"]))
                    if not poly.is_empty and poly.area > 1.0:
                        areas.append((c, poly))
                continue
            if "highway" not in t:
                continue
            # crossings and sidewalks drawn as ways lie on the carriageway or beside it: their
            # surface is not the street's
            if t.get("footway") in ("crossing", "sidewalk") or t.get("path") == "crossing" \
                    or t.get("cycleway") == "crossing":
                c = None
            lines.append(w["line"])
            cats.append(c)
            hw.append(HALF_WIDTH.get(t["highway"], 1.0))
    tree = shapely.STRtree(lines) if lines else None
    _cache["hw"] = np.array(hw, np.float64)
    _cache["ways"] = (lines, np.array(cats, object), tree, areas)
    return _cache["ways"]


def _nearest(px, py, maxd):
    """Index of the nearest OSM highway within maxd of every point (-1 where none) and its distance."""
    lines, _, tree, _ = ways()
    idx = np.full(len(px), -1, np.int64)
    dist = np.full(len(px), np.inf)
    if tree is None or len(px) == 0:
        return idx, dist
    pts = shapely.points(px, py)
    (i_pt, i_way), d = tree.query_nearest(pts, max_distance=maxd, return_distance=True, all_matches=False)
    idx[i_pt], dist[i_pt] = i_way, d
    return idx, dist


def line_categories(net):
    """Category of every swissTLM3D line of the network (network_mesh.Network): the OSM ways that run
    along it within NEAR_WAY m, where tagged ones cover MIN_SHARE of it (the category covering most of
    it), else its swissTLM3D surface. Also the counts of the changes, for the build log."""
    lines, cats, tree, _ = ways()
    segs = net.segs
    out = [fallback(s) for s in segs]
    stats = {"lines": len(segs), "osm": 0, "changed": {}}
    if tree is None:
        return out, stats
    x, y, seg = net.x, net.y, net.seg
    idx, _ = _nearest(x, y, NEAR_WAY)
    # direction of the line at every station against the way's: a crossing street is not its surface
    tx = np.gradient(x)
    ty = np.gradient(y)
    first = np.r_[True, seg[1:] != seg[:-1]]
    last = np.r_[seg[1:] != seg[:-1], True]
    tx[first] = (np.roll(x, -1) - x)[first]; ty[first] = (np.roll(y, -1) - y)[first]
    tx[last] = (x - np.roll(x, 1))[last]; ty[last] = (y - np.roll(y, 1))[last]
    nt = np.maximum(np.hypot(tx, ty), 1e-9)
    ok = idx >= 0
    k = np.flatnonzero(ok)
    L = np.array(lines, object)[idx[k]]
    s = shapely.line_locate_point(L, shapely.points(x[k], y[k]))
    a = shapely.get_coordinates(shapely.line_interpolate_point(L, np.maximum(s - 1.0, 0.0)))
    b = shapely.get_coordinates(shapely.line_interpolate_point(L, s + 1.0))
    d = b - a
    cosang = np.abs(d[:, 0] * tx[k] + d[:, 1] * ty[k]) / (np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9) * nt[k])
    good = np.zeros(len(x), bool)
    good[k] = cosang > 0.7
    cat = np.full(len(x), None, object)
    cat[good] = cats[idx[good]]
    for sid in range(len(segs)):
        a0, n = segs[sid]["first"], segs[sid]["n"]
        c = cat[a0:a0 + n]
        known = [v for v in c if v is not None]
        if n == 0 or len(known) < MIN_SHARE * n:
            continue
        vals, counts = np.unique(np.array(known, object).astype(str), return_counts=True)
        best = str(vals[np.argmax(counts)])
        stats["osm"] += 1
        if best != out[sid]:
            key = f"{out[sid]}->{best}"
            stats["changed"][key] = stats["changed"].get(key, 0) + 1
        out[sid] = best
    return out, stats


def _polygons(g, min_area=0.5):
    """The polygons of a geometry (an intersection may leave lines and points) above min_area m2."""
    parts = [q for q in shapely.get_parts(g) if q.geom_type == "Polygon" and q.area > min_area] if not g.is_empty else []
    return shapely.union_all(parts) if parts else shapely.Polygon()


def _weighted_nearest(px, py, maxd):
    """For every point, the OSM highway within maxd whose line is nearest in units of its half width
    (HALF_WIDTH: a street's carriageway is its own up to its edge, a path only along its line);
    -1 where none."""
    lines, _, tree, _ = ways()
    best = np.full(len(px), -1, np.int64)
    if tree is None or len(px) == 0:
        return best
    pts = shapely.points(px, py)
    i_pt, i_way = tree.query(pts, predicate="dwithin", distance=maxd)
    if len(i_pt) == 0:
        return best
    d = shapely.distance(pts[i_pt], np.array(lines, object)[i_way]) / _half_width()[i_way]
    o = np.lexsort((d, i_pt))
    i_pt, i_way = i_pt[o], i_way[o]
    first = np.r_[True, i_pt[1:] != i_pt[:-1]]
    best[i_pt[first]] = i_way[first]
    return best


def _half_width():
    ways()
    return _cache["hw"]


def polygon_zones(net, p, line_cat):
    """[(category, part)] of a survey polygon of a road (network_mesh polygon dict p) on a CELL m grid:
    every cell takes the category of the nearest of the polygon's lines (line_cat, from
    line_categories), or of the OSM way it lies on (nearest in units of the way's half width, within
    NEAR_ZONE m) where that way is tagged: the lanes of a nucleus the survey draws as one polygon with
    the main street. Pieces under MIN_PIECE m2 join the polygon's main category; one part where all
    agree."""
    from scipy import ndimage as ndi
    from scipy.spatial import cKDTree
    from rasterio import features
    from rasterio.transform import Affine
    from shapely.geometry import shape
    g = p["geom"]
    segs = sorted(p["segs"])
    own = np.flatnonzero(np.isin(net.seg, np.array(segs, int))) if segs else np.zeros(0, int)
    if len(own) == 0:
        return [("hard", g)]
    x0, y0, x1, y1 = g.bounds
    W, H = max(1, int(np.ceil((x1 - x0) / CELL))), max(1, int(np.ceil((y1 - y0) / CELL)))
    tr = Affine(CELL, 0, x0, 0, -CELL, y0 + H * CELL)
    inside = features.rasterize([(g, 1)], out_shape=(H, W), transform=tr, fill=0, all_touched=True, dtype=np.uint8) > 0
    rr, cc = np.nonzero(inside)
    if len(rr) == 0:
        return [(line_cat[int(net.seg[own[0]])], g)]
    X = x0 + (cc + 0.5) * CELL
    Y = y0 + H * CELL - (rr + 0.5) * CELL
    _, nn = cKDTree(np.column_stack([net.x[own], net.y[own]])).query(np.column_stack([X, Y]))
    cat = np.array([line_cat[int(s)] for s in net.seg[own[nn]]], object)
    _, cats, _, _ = ways()
    w = _weighted_nearest(X, Y, NEAR_ZONE)
    wc = np.full(len(X), None, object)
    wc[w >= 0] = cats[w[w >= 0]]
    tagged = np.array([c is not None for c in wc], bool)
    cat[tagged] = wc[tagged]
    names = sorted(set(cat.tolist()))
    if len(names) == 1:
        return [(names[0], g)]
    code = np.full((H, W), -1, np.int16)
    code[rr, cc] = [names.index(c) for c in cat]
    main = int(np.argmax(np.bincount(code[rr, cc], minlength=len(names))))
    # strips one cell wide and small pieces (a path's end on the street, a corner) go to the main
    # category
    min_cells = MIN_PIECE / CELL ** 2
    for k in range(len(names)):
        if k == main:
            continue
        m = code == k
        code[m & ~ndi.binary_opening(m, structure=np.ones((2, 2), bool))] = main
        lab, n = ndi.label(code == k)
        if n:
            size = np.bincount(lab.ravel())
            small = np.flatnonzero(size < min_cells)
            small = small[small > 0]
            code[np.isin(lab, small)] = main
    present = sorted(set(code[rr, cc].tolist()))
    if len(present) == 1:
        return [(names[present[0]], g)]
    out, rest = [], g
    for k in present:
        if k == main:
            continue
        shp = [shape(geom) for geom, v in
               features.shapes(code, mask=code == k, transform=tr) if v == k]
        # the cell outline smoothed: closed and opened by 0.7 m, simplified
        zone = shapely.union_all(shp).buffer(0.7, quad_segs=2).buffer(-1.4, quad_segs=2).buffer(0.7, quad_segs=2) \
            .simplify(0.4) if shp else shapely.Polygon()
        part = _polygons(rest.intersection(zone), 1.0)
        if part.is_empty:
            continue
        out.append((names[k], part))
        rest = _polygons(rest.difference(part), 0.0)
    if not rest.is_empty:
        out.append((names[main], rest))
    return out


def area_zones(p):
    """[(category, part)] of a yard or square (network_mesh polygon of class 'hard') under the OSM
    areas with a surface (car parks, squares); the rest stays 'hard'."""
    _, _, _, areas = ways()
    g = p["geom"]
    out, rest = [], g
    for c, a in areas:
        if c == "hard" or not a.intersects(rest):
            continue
        part = _polygons(rest.intersection(a))
        if part.is_empty:
            continue
        out.append((c, part))
        rest = _polygons(rest.difference(part), 0.0)
    if not out:
        return [("hard", g)]
    if not rest.is_empty:
        out.append(("hard", rest))
    return out
