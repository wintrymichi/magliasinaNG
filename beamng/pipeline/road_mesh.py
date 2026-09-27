"""Road-surface meshes from the cadastral (MU) paved polygons.

Every polygon is cut by a square grid (CELL m); each piece is triangulated with
GEOS constrained Delaunay (shapely), so the outline is exactly the surveyed one
and the surface follows the height field inside. Shared vertices are welded so
neighbouring cells meet without cracks. A polygon that spans several fitted
surfaces (a wall inside it, roadheight.py) is meshed per surface: each triangle
belongs to the surface under its centre and vertices are shared only within one
surface. The outline of every surface hangs a vertical skirt down to the ground
or to the surface below it (skirt_bands), so no gap shows at an edge or a step.
"""
import numpy as np
import shapely
from shapely.geometry import box, Polygon, MultiPolygon

SKIRT = 0.5            # m, kerb skirt under every paved edge
DEEP = 1.0             # m, edges this far above the ground or the next surface get a wall face down to it
# terrain carve: a vertex under a paved mesh drops below the lowest surface at these offsets (m)
CARVE_RING = ((0.8, 0), (-0.8, 0), (0, 0.8), (0, -0.8), (0.6, 0.6), (-0.6, 0.6), (0.6, -0.6), (-0.6, -0.6))


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


def triangles_2d(poly, cell):
    """Constrained Delaunay triangles (k,3,2) of `poly` cut by the grid, counter-clockwise (up)."""
    tris2d = [triangulate(p) for p in grid_pieces(poly, cell)]
    tris2d = np.concatenate([t for t in tris2d if len(t)]) if any(len(t) for t in tris2d) else np.zeros((0, 3, 2))
    if len(tris2d):
        a = tris2d[:, 1] - tris2d[:, 0]
        b = tris2d[:, 2] - tris2d[:, 0]
        cw = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) < 0
        tris2d[cw] = tris2d[cw][:, ::-1]
    return tris2d


def weld_2d(tris2d, weld):
    pts = tris2d.reshape(-1, 2)
    key = np.round(pts / weld).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    T = inv.reshape(-1, 3)
    good = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])
    return uniq * weld, T[good]


def mesh_polygon(poly, height_fn, cell=2.0, weld=0.002):
    """Triangulated surface of `poly`: vertices (n,3), triangles (m,3). Counter-clockwise (up)."""
    tris2d = triangles_2d(poly, cell)
    if len(tris2d) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    V2, T = weld_2d(tris2d, weld)
    V = np.column_stack([V2, height_fn(V2[:, 0], V2[:, 1])])
    return V, T


def polygonal(g):
    """The polygon parts of a geometry (overlays can leave lines and points)."""
    parts = [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and p.area > 0]
    if not parts:
        return Polygon()
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def split_by_surface(poly, S, pid, min_area=2.0, simplify=0.35):
    """Parts of `poly` on the different facets of polygon `pid` (S: surface_fit.Surface): every
    point goes to the facet of the nearest cell of the polygon, the cell staircase of the lines
    between facets is straightened by `simplify` m. Returns [(part, facet)]."""
    from rasterio import features
    from rasterio.transform import Affine
    from scipy import ndimage as ndi
    x0, y0, x1, y1 = poly.bounds
    c0 = max(int(np.floor((x0 - S.x_min) / S.res)) - 3, 0)
    r0 = max(int(np.floor((S.y_max - y1) / S.res)) - 3, 0)
    c1 = min(int(np.ceil((x1 - S.x_min) / S.res)) + 4, S.owner.shape[1])
    r1 = min(int(np.ceil((S.y_max - y0) / S.res)) + 4, S.owner.shape[0])
    own, fac = S.owner[r0:r1, c0:c1], S.facet[r0:r1, c0:c1]
    ks, n = np.unique(fac[own == pid], return_counts=True)
    ks = [int(k) for k, m in zip(ks, n) if m * S.res * S.res >= min_area]
    if len(ks) <= 1:
        return [(poly, ks[0] if ks else None)]
    lab = np.where((own == pid) & np.isin(fac, ks), fac, -1)
    _, (ir, ic) = ndi.distance_transform_edt(lab < 0, return_indices=True)
    full = lab[ir, ic].astype(np.int32)
    tr = Affine(S.res, 0, S.x_min + c0 * S.res, 0, -S.res, S.y_max - r0 * S.res)
    parts, taken = [], None
    for k in ks:
        m = (full == k).astype(np.uint8)
        g = shapely.union_all([shapely.geometry.shape(s) for s, v in features.shapes(m, mask=m > 0, transform=tr)])
        g = polygonal(shapely.make_valid(g.simplify(simplify)))
        g = polygonal(poly.intersection(g))
        if taken is not None:
            g = polygonal(g.difference(taken))
        taken = g if taken is None else polygonal(shapely.union_all([taken, g]))
        parts.append([k, g])
    # slivers left between the straightened lines go to the nearest part
    rest = polygonal(poly.difference(taken))
    for q in shapely.get_parts(rest):
        if q.is_empty or q.area < 1e-6:
            continue
        j = int(np.argmin([q.distance(g) if not g.is_empty else np.inf for _, g in parts]))
        parts[j][1] = polygonal(shapely.union_all([parts[j][1], q]))
    return [(g, k) for k, g in parts if not g.is_empty and g.area > 1e-4]


def mesh_polygon_surfaces(poly, height_fn, key_fn, cell=2.0, weld=0.002):
    """Like mesh_polygon for a polygon that may span several surfaces: key_fn(x, y) gives the
    surface under each triangle centre, height_fn(x, y, key) the height on that surface.
    Returns [(key, V, T)]."""
    tris2d = triangles_2d(poly, cell)
    if len(tris2d) == 0:
        return []
    cen = tris2d.mean(1)
    keys = np.asarray(key_fn(cen[:, 0], cen[:, 1]))
    out = []
    for k in np.unique(keys):
        V2, T = weld_2d(tris2d[keys == k], weld)
        if len(T):
            out.append((k, np.column_stack([V2, height_fn(V2[:, 0], V2[:, 1], k)]), T))
    return out


class MeshSampler:
    """Height of a set of top-face triangles (k,3,3) at any point: the plane of the triangle over
    the 0.5 m cell of the point (the highest one where triangles overlap); NaN off the mesh."""

    def __init__(self, tris, res=0.5):
        self.t = np.asarray(tris, np.float64)
        self.res = res
        lo, hi = self.t[:, :, :2].min((0, 1)) - 1, self.t[:, :, :2].max((0, 1)) + 1
        self.x0, self.y0 = lo
        self.W, self.H = (np.ceil((hi - lo) / res).astype(int) + 1)
        self.id = np.full((self.H, self.W), -1, np.int64)
        best = np.full((self.H, self.W), -np.inf)
        A, B, C = self.t[:, 0], self.t[:, 1], self.t[:, 2]
        v0, v1 = B[:, :2] - A[:, :2], C[:, :2] - A[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        self.plane = np.zeros((len(self.t), 3))                  # z = a + b x + c y
        n = np.cross(B - A, C - A)
        nz = np.where(np.abs(n[:, 2]) > 1e-12, n[:, 2], 1e-12)
        self.plane[:, 1], self.plane[:, 2] = -n[:, 0] / nz, -n[:, 1] / nz
        self.plane[:, 0] = A[:, 2] - self.plane[:, 1] * A[:, 0] - self.plane[:, 2] * A[:, 1]
        c0 = np.floor((np.minimum(np.minimum(A[:, 0], B[:, 0]), C[:, 0]) - self.x0) / res).astype(int)
        c1 = np.floor((np.maximum(np.maximum(A[:, 0], B[:, 0]), C[:, 0]) - self.x0) / res).astype(int)
        r0 = np.floor((np.minimum(np.minimum(A[:, 1], B[:, 1]), C[:, 1]) - self.y0) / res).astype(int)
        r1 = np.floor((np.maximum(np.maximum(A[:, 1], B[:, 1]), C[:, 1]) - self.y0) / res).astype(int)
        for w, h in set(zip((c1 - c0 + 1).tolist(), (r1 - r0 + 1).tolist())):
            sel = np.where(ok & (c1 - c0 + 1 == w) & (r1 - r0 + 1 == h))[0]
            if not len(sel):
                continue
            dc, dr = np.meshgrid(np.arange(w), np.arange(h))
            cc = c0[sel][:, None] + dc.ravel()[None]
            rr = r0[sel][:, None] + dr.ravel()[None]
            # a cell belongs to a triangle that covers any of its corners or its centre
            hit = np.zeros(cc.shape, bool)
            for fx, fy in ((0.5, 0.5), (0.05, 0.05), (0.95, 0.05), (0.05, 0.95), (0.95, 0.95)):
                px = self.x0 + (cc + fx) * res - A[sel, 0:1]
                py = self.y0 + (rr + fy) * res - A[sel, 1:2]
                l1 = (px * v1[sel, 1:2] - v1[sel, 0:1] * py) / den[sel, None]
                l2 = (v0[sel, 0:1] * py - px * v0[sel, 1:2]) / den[sel, None]
                hit |= (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
            z = self.plane[sel, 0:1] + self.plane[sel, 1:2] * (self.x0 + (cc + 0.5) * res) + \
                self.plane[sel, 2:3] * (self.y0 + (rr + 0.5) * res)
            tid = np.broadcast_to(sel[:, None], cc.shape)
            m = hit & (z > best[rr, cc])
            order = np.argsort(z[m])
            rr_, cc_, z_, t_ = rr[m][order], cc[m][order], z[m][order], tid[m][order]
            best[rr_, cc_] = z_
            self.id[rr_, cc_] = t_

    def __call__(self, x, y):
        x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64))
        c = np.floor((x - self.x0) / self.res).astype(int)
        r = np.floor((y - self.y0) / self.res).astype(int)
        ok = (c >= 0) & (c < self.W) & (r >= 0) & (r < self.H)
        t = np.full(len(x), -1)
        t[ok] = self.id[r[ok], c[ok]]
        out = np.full(len(x), np.nan)
        m = t >= 0
        p = self.plane[t[m]]
        out[m] = p[:, 0] + p[:, 1] * x[m] + p[:, 2] * y[m]
        return out


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


def skirt_depth(V, T, S, ground):
    """Depth of the skirt at every vertex of a surface piece: SKIRT, or down to the lowest of the
    ground and the paved surfaces (S, surface_fit.Surface) 0.6 m around an edge vertex where that
    is more than DEEP below it (a bridge side, the wall of a step). ground(x, y): terrain height."""
    E = boundary_edges(T)
    depth = np.full(len(V), SKIRT)
    if not len(E):
        return depth
    idx = np.unique(E.ravel())
    P = V[idx]
    low = np.asarray(ground(P[:, 0], P[:, 1]), np.float64).copy()
    for dx, dy in ((0.6, 0), (-0.6, 0), (0, 0.6), (0, -0.6)):
        q = P[:, :2] + [dx, dy]
        near = S.distance(q[:, 0], q[:, 1]) < 0.4
        if near.any():
            low[near] = np.minimum(low[near], S.height(q[near, 0], q[near, 1]))
    drop = P[:, 2] - low
    depth[idx] = np.where(drop > DEEP, drop + 0.15, SKIRT)
    # a face does not end at every other vertex along a jagged edge: the depth spreads two
    # vertices along the outline (a face reaching below the ground is hidden in it)
    for _ in range(2):
        d = depth.copy()
        np.maximum.at(d, E[:, 0], depth[E[:, 1]])
        np.maximum.at(d, E[:, 1], depth[E[:, 0]])
        depth = d
    return depth


def skirt_bands(V, T, depth, top=SKIRT):
    """Vertical faces below the outline, `depth` m deep at every vertex (array over V): the
    first `top` m as a kerb face, the rest (a bridge side, the wall of a step) separately.
    Returns two triangle soups (kerb, wall)."""
    E = boundary_edges(T)
    if not len(E):
        return np.zeros((0, 3)), np.zeros((0, 3))
    a, b = V[E[:, 0]], V[E[:, 1]]
    da, db = depth[E[:, 0]], depth[E[:, 1]]
    ka, kb = np.minimum(da, top), np.minimum(db, top)

    def band(z0a, z0b, z1a, z1b, sel):
        A0, B0 = a[sel].copy(), b[sel].copy()
        A1, B1 = a[sel].copy(), b[sel].copy()
        A0[:, 2] -= z0a[sel]; B0[:, 2] -= z0b[sel]
        A1[:, 2] -= z1a[sel]; B1[:, 2] -= z1b[sel]
        return np.stack([A0, A1, B1, A0, B1, B0], 1).reshape(-1, 3)
    kerb = band(np.zeros(len(E)), np.zeros(len(E)), ka, kb, np.ones(len(E), bool))
    deep = (da > top + 0.01) | (db > top + 0.01)
    wall = band(ka, kb, da, db, deep) if deep.any() else np.zeros((0, 3))
    return kerb, wall
