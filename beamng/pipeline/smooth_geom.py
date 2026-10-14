"""Curves of the cadastral survey smoothed (v3.0).

The survey draws a curved road edge, kerb or wall as a chain of straight pieces a few metres long, and
the meshes built on it (roads, pavements, walls) showed every piece: a bend looked faceted, "squared". Here
every chain of gently turning vertices is replaced by a centripetal Catmull-Rom curve THROUGH the surveyed
vertices (so nothing moves where the survey measured it, only the corners between the pieces are rounded),
a point every STEP m. A vertex where the outline turns by CORNER degrees or more stays a sharp corner.

The land cover (LCSF) is a partition: a road and the pavement beside it share their edge. The curve of a
piece depends only on the piece and its two neighbours along the chain, and is the same read either way,
so both polygons of a shared edge get the same curve, provided the chain ends at the same vertices for both:
a vertex is fixed (the end of a chain) where it is a corner, where three or more polygons meet, or where it
belongs to a polygon kept as it is (buildings: their outlines are straight walls).
"""
import numpy as np
import shapely

CORNER = 35.0          # degrees of turn: a corner, kept sharp
STRAIGHT = 0.5         # degrees: a vertex this straight needs no curve on its pieces
STEP = 0.75            # m between the points of a curve
MIN_PIECE = 1.0        # m: shorter pieces stay straight
MAX_SUB = 12           # points per piece at most
KEY = 1000.0           # vertices within 1 mm are one


def _turn(prev, p, nxt):
    """Turning angle (degrees) at p between prev -> p -> nxt."""
    a, b = p - prev, nxt - p
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 180.0
    return float(np.degrees(np.arccos(np.clip(a @ b / (na * nb), -1.0, 1.0))))


def _cr(p0, p1, p2, p3, n):
    """n - 1 inner points of the centripetal Catmull-Rom curve from p1 to p2 (p0, p3 its neighbours)."""
    def tj(ti, a, b):
        return ti + max(np.linalg.norm(b - a), 1e-6) ** 0.5
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    t = np.linspace(t1, t2, n + 1)[1:-1][:, None]
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2


def _smooth_chain(P, fixed, closed):
    """Points of the outline P (n, 2) with its curves: pieces between vertices, each with the inner points
    of its curve unless both its ends are fixed or straight. fixed (n,) bool."""
    n = len(P)
    if n < 3:
        return P
    turn = np.array([_turn(P[i - 1], P[i], P[(i + 1) % n]) if (closed or 0 < i < n - 1) else 180.0
                     for i in range(n)])
    fix = fixed | (turn >= CORNER)
    if not closed:
        fix[0] = fix[-1] = True
    out = []
    last = n if closed else n - 1
    for i in range(last):
        j = (i + 1) % n
        out.append(P[i])
        a, b = P[i], P[j]
        L = float(np.linalg.norm(b - a))
        if L < MIN_PIECE or (fix[i] and fix[j]) or (turn[i] < STRAIGHT and turn[j] < STRAIGHT):
            continue
        # the neighbours along the chain; at a fixed end the piece itself goes on straight (a phantom point)
        p0 = 2 * a - b if fix[i] else P[i - 1]
        p3 = 2 * b - a if fix[j] else P[(j + 1) % n]
        k = int(min(MAX_SUB, max(2, np.ceil(L / STEP))))
        out.extend(_cr(p0, a, b, p3, k))
    if not closed:
        out.append(P[-1])
    return np.asarray(out)


def _keys(P):
    return [tuple(k) for k in np.round(P * KEY).astype(np.int64).tolist()]


def _rings(poly):
    return [poly.exterior] + list(poly.interiors)


def _polys(g):
    return list(g.geoms) if hasattr(g, "geoms") else [g]


def smooth_partition(geoms, rigid):
    """The polygons geoms (shapely Polygon / MultiPolygon, a partition sharing their edges) with their curves
    smoothed; rigid[i]: geoms[i] stays as it is and fixes its vertices for the others."""
    owners = {}
    for i, g in enumerate(geoms):
        for p in _polys(g):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            for r in _rings(p):
                for k in set(_keys(np.asarray(r.coords)[:-1, :2])):
                    owners.setdefault(k, set()).add(i)
    rigid_set = {i for i, r in enumerate(rigid) if r}
    out = []
    for i, g in enumerate(geoms):
        if i in rigid_set:
            out.append(g)
            continue
        parts = []
        for p in _polys(g):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            rings = []
            for r in _rings(p):
                P = np.asarray(r.coords)[:-1, :2]
                ks = _keys(P)
                fixed = np.array([len(owners.get(k, ())) >= 3 or bool(owners.get(k, set()) & rigid_set) for k in ks])
                rings.append(_smooth_chain(P, fixed, True))
            q = shapely.Polygon(rings[0], rings[1:])
            if not q.is_valid:
                q = shapely.make_valid(q)
            parts += [x for x in _polys(q) if x.geom_type == "Polygon" and not x.is_empty]
        out.append(parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts) if parts else g)
    return out


def smooth_polygon(g):
    """A polygon on its own (a wall's footprint) with its curves smoothed."""
    return smooth_partition([g], [False])[0]


def smooth_line(g):
    """A line or multiline on its own (a wall's axis) with its curves smoothed."""
    if g.geom_type == "MultiLineString":
        return shapely.MultiLineString([smooth_line(x) for x in g.geoms])
    if g.geom_type != "LineString" or len(g.coords) < 3:
        return g
    P = np.asarray(g.coords)[:, :2]
    closed = bool(np.allclose(P[0], P[-1]))
    if closed:
        Q = _smooth_chain(P[:-1], np.zeros(len(P) - 1, bool), True)
        return shapely.LineString(np.vstack([Q, Q[:1]]))
    return shapely.LineString(_smooth_chain(P, np.zeros(len(P), bool), False))
