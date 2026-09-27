"""Road-surface meshes from the cadastral (MU) paved polygons.

Every polygon is cut by a square grid (CELL m); each piece is triangulated with
GEOS constrained Delaunay (shapely), so the outline is exactly the surveyed one
and the surface follows the height field inside. Shared vertices are welded so
neighbouring cells/polygons meet without cracks. Surfaces of different classes
(road, sidewalk, island) are fitted separately; where their heights differ at a
common edge a vertical curb face is added.
"""
import numpy as np
import shapely
from shapely.geometry import box, Polygon, MultiPolygon


def grid_pieces(poly, cell):
    """Intersections of `poly` with the grid cells overlapping its bounds."""
    x0, y0, x1, y1 = poly.bounds
    xs = np.arange(np.floor(x0 / cell) * cell, x1 + cell, cell)
    ys = np.arange(np.floor(y0 / cell) * cell, y1 + cell, cell)
    X, Y = np.meshgrid(xs[:-1], ys[:-1])
    cells = shapely.box(X.ravel(), Y.ravel(), X.ravel() + cell, Y.ravel() + cell)
    hit = shapely.intersects(cells, poly)
    pieces = shapely.intersection(cells[hit], poly, grid_size=0.001)
    return [p for p in pieces if not p.is_empty]


def triangulate(geom):
    """Constrained Delaunay triangles (n,3,2) of a (multi)polygon, holes respected."""
    out = []
    polys = [geom] if isinstance(geom, Polygon) else [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    for p in polys:
        if p.area < 1e-4:
            continue
        tri = shapely.constrained_delaunay_triangles(p)
        for t in tri.geoms:
            c = np.asarray(t.exterior.coords)[:3]
            out.append(c)
    return np.array(out).reshape(-1, 3, 2) if out else np.zeros((0, 3, 2))


def mesh_polygon(poly, height_fn, cell=2.0, weld=0.002):
    """Triangulated surface of `poly`: vertices (n,3), triangles (m,3). Counter-clockwise (up)."""
    tris2d = [triangulate(p) for p in grid_pieces(poly, cell)]
    tris2d = np.concatenate([t for t in tris2d if len(t)]) if any(len(t) for t in tris2d) else np.zeros((0, 3, 2))
    if len(tris2d) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    # orient counter-clockwise (normal up)
    a = tris2d[:, 1] - tris2d[:, 0]
    b = tris2d[:, 2] - tris2d[:, 0]
    cw = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) < 0
    tris2d[cw] = tris2d[cw][:, ::-1]
    pts = tris2d.reshape(-1, 2)
    key = np.round(pts / weld).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    V2 = uniq * weld
    Z = height_fn(V2[:, 0], V2[:, 1])
    V = np.column_stack([V2, Z])
    T = inv.reshape(-1, 3)
    good = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])
    return V, T[good]


def boundary_edges(T):
    """Edges used by exactly one triangle (the outline), as (k,2) vertex index pairs, oriented."""
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    s = np.sort(e, 1)
    uniq, inv, cnt = np.unique(s, axis=0, return_inverse=True, return_counts=True)
    return e[cnt[inv] == 1]


def skirt(V, T, depth=0.6):
    """Vertical faces hanging below the outline (hide gaps against the terrain)."""
    E = boundary_edges(T)
    a, b = V[E[:, 0]], V[E[:, 1]]
    a2, b2 = a - [0, 0, depth], b - [0, 0, depth]
    quads = np.stack([a, a2, b2, a, b2, b], 1).reshape(-1, 3, 3)
    return quads.reshape(-1, 3)
