"""Building meshes from swissBUILDINGS3D 3.0 (LOD2), grouped into 256 m tiles.

Facades seen in the Street View panoramas of the original route carry their projected photo texture
in the personal build (texture_buildings.py -> work/facades, packed here into 4096 px atlases). All
other walls (all of them in the public build) use the original procedural textures of
bld_textures.py (v2.2): plaster tinted (vertex colour) with the building's own facade tone (measured
in the photos where the building was seen, otherwise the style of its age and use, facades.py) or
rubble stone, with windows, doors, garage doors, shop fronts and a plinth band laid out on every
facade (facades.py). Roofs: canal tiles, flat tiles, stone slabs, metal sheet or gravel after their
slope, colour and age, laid along the slope and tinted with the median SWISSIMAGE colour of the roof
(footprint eroded 1.5 m against relief displacement). Collision on (visible mesh).
v2.0: a passage is cut under every building that stands on a road or path of the network
(PASSAGE_CLEAR m high, closed by a ceiling and side walls; network_ways, passages).
"""
import json, os, pickle
import numpy as np
import cv2
import rasterio
import shapely
from PIL import Image
import bng
from config import NO_PHOTO, WORK
import argparse, gzip, hashlib, io, json, math, os, re, sys, time, zipfile
import optimize_level
import lamps as pl
import poles as pr
import network_mesh as pu
import walls as pw
from config import LEVEL_NAME

TILE = 256.0
V1_DEFAULT = np.array([0.84, 0.80, 0.72])        # plaster tone of v1.x buildings without photos
SHOP_NEAR = 3.0        # m, a shop of OSM this close to a building is in it (the point is often on the street side)
GROUND_AO = 0.14            # v2.4: darkening of the walls at the ground (vertex colour)
GROUND_AO_H = 4.0           # m above the foot of the building where it ends


# v2.8: the fields of the building TSStatics that light their windows at night (core_environment of the game sets
# the instance colour of every object with nightEmissive after sunset, black by day: bld_openings_lit glows in it)
NIGHT = {"nightEmissive": "1", "nightEmissiveColor": "255 214 160", "instanceColor": [0, 0, 0, 1]}


def wall_uvs(tris):
    t = tris.reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    horiz = np.stack([-n[:, 1], n[:, 0]], 1)
    ln = np.linalg.norm(horiz, axis=1, keepdims=True)
    ln[ln == 0] = 1
    horiz /= ln
    u = (t[..., 0] * horiz[:, None, 0] + t[..., 1] * horiz[:, None, 1])
    return np.stack([u, t[..., 2]], -1).reshape(-1, 2)


def roof_uvs(tris, tile=1.6):
    t = tris.reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    down = np.stack([n[:, 0], n[:, 1]], 1)                # horizontal direction of the fall line
    ln = np.linalg.norm(down, axis=1, keepdims=True)
    flat = ln[:, 0] < 0.05
    down = np.where(flat[:, None], [[0.0, 1.0]], down / np.maximum(ln, 1e-9))
    along = np.stack([-down[:, 1], down[:, 0]], 1)
    u = (t[..., :2] * along[:, None]).sum(-1)
    v = (t[..., :2] * down[:, None]).sum(-1) / np.maximum(np.abs(n[:, 2:3]), 0.3)
    return np.stack([u, v], -1).reshape(-1, 2) / tile


def _crossings(O, D, T, chunk=4096):
    """Number of triangles T (t, 3, 3) every ray O + s D (s > 0) of (m, 3) passes through
    (Moller-Trumbore)."""
    e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    out = np.zeros(len(O), np.int32)
    step = max(1, min(chunk, chunk * 64 // max(len(T), 1)))
    for a in range(0, len(O), step):
        o, d = O[a:a + step][:, None, :], D[a:a + step][:, None, :]
        p = np.cross(d, e2[None])
        det = (e1[None] * p).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - T[None, :, 0]
        u = (s * p).sum(-1) * inv
        q = np.cross(s, e1[None])
        v = (d * q).sum(-1) * inv
        t = (e2[None] * q).sum(-1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6)
        out[a:a + step] = hit.sum(1)
    return out


def _surface(b):
    """The building's own surface: walls, roofs and floors (k, 3, 3)."""
    fl = b.get("floors")
    return np.concatenate([x for x in (b["walls"], b["roofs"], fl if fl is not None else np.zeros((0, 3, 3)))
                           if len(x)])


def _votes(walls, surf):
    """+2 where two slightly turned horizontal rays from just in front of every wall triangle both cross
    the surface an odd number of times (the front is inside the building), -2 where both cross it an
    even number of times, 0 where they disagree (an open shell, a ray along an edge)."""
    n = np.cross(walls[:, 1] - walls[:, 0], walls[:, 2] - walls[:, 0])
    h = n.copy()
    h[:, 2] = 0.0
    ln = np.linalg.norm(h, axis=1)
    ok = ln > 1e-9
    h[ok] /= ln[ok, None]
    c = walls.mean(1)
    votes = np.zeros(len(walls), np.int32)
    for ang, dz in ((0.13, 0.011), (-0.17, -0.007)):        # off the edges of the mesh
        ca, sa = np.cos(ang), np.sin(ang)
        d = np.column_stack([ca * h[:, 0] - sa * h[:, 1], sa * h[:, 0] + ca * h[:, 1], np.zeros(len(h))])
        odd = _crossings(c + 0.01 * h + np.array([0.0, 0.0, dz]), d, surf) % 2 == 1
        votes += np.where(odd, 1, -1)
    votes[~ok] = 0
    return votes


# v2.8: the walls (plaster, stone, plinth, photo facades) are drawn from both sides, a back face lit like the
# front (no extra triangle): a wall the ray test turns inwards no longer leaves the house see-through
WALL_TWO_SIDED = {"doubleSided": True, "invertBackFaceNormals": True}


def orient(b):
    """Walls facing out of the building, roofs facing up (the game draws a face from its front only).
    v2.4: a wall faces in when a horizontal ray from just in front of it crosses the building's own
    surface an odd number of times (it starts inside); two slightly turned rays must agree, otherwise
    the old test decides (away from the building's centre). That test alone turned the walls of L- and U-shaped buildings, courtyards and
    rows of houses inwards (9 % of the wall area), and from those sides the houses were see-through.
    v2.8: the walls are drawn from both sides anyway (WALL_TWO_SIDED): the survey's open shells, rows of
    houses and blocks still had walls the rays turned the wrong way, and from that side the house was
    see-through."""
    walls, roofs = b["walls"].copy(), b["roofs"].copy()
    if len(roofs):
        n = np.cross(roofs[:, 1] - roofs[:, 0], roofs[:, 2] - roofs[:, 0])
        flip = n[:, 2] < 0
        roofs[flip] = roofs[flip][:, ::-1]
    if len(walls):
        votes = _votes(walls, _surface(b))
        n = np.cross(walls[:, 1] - walls[:, 0], walls[:, 2] - walls[:, 0])
        ctr = np.concatenate([walls.reshape(-1, 3), roofs.reshape(-1, 3)]).mean(0)
        o = walls.mean(1) - ctr
        o[:, 2] = 0
        flip = np.where(votes != 0, votes > 0, (n * o).sum(1) < 0)
        walls[flip] = walls[flip][:, ::-1]
    return {"walls": walls, "roofs": roofs}


def roof_height(roofs, P):
    """Height of the roof triangles (k, 3, 3) over the points P (n, 2): the highest triangle covering
    each point, the plane of the nearest triangle where none does (a point on the eave line)."""
    A, B, C = roofs[:, 0], roofs[:, 1], roofs[:, 2]
    n = np.cross(B - A, C - A)
    nz = np.where(np.abs(n[:, 2]) > 1e-9, n[:, 2], 1e-9)
    za = A[:, 2][None] - (n[:, 0][None] * (P[:, 0][:, None] - A[:, 0][None]) +
                          n[:, 1][None] * (P[:, 1][:, None] - A[:, 1][None])) / nz[None]
    v0, v1 = (B - A)[:, :2], (C - A)[:, :2]
    v2 = P[:, None, :] - A[None, :, :2]
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) > 1e-12, den, 1e-12)
    u = (v2[..., 0] * v1[None, :, 1] - v1[None, :, 0] * v2[..., 1]) / den[None]
    w = (v0[None, :, 0] * v2[..., 1] - v2[..., 0] * v0[None, :, 1]) / den[None]
    out = 1.0 - u - w
    dist = np.maximum(np.maximum(-u, -w), -out)            # how far outside the triangle (0 inside)
    z = np.where(dist <= 1e-6, za, -np.inf).max(1)
    near = np.argmin(dist, axis=1)
    return np.where(np.isfinite(z), z, za[np.arange(len(P)), near])


def soffits(b, roofs, drop=0.03):
    """The undersides of the eaves (v2.4): the roof plan outside the building's ground plan, a few cm
    under the roof and facing down, one piece per roof plane. The game draws a face from its front only,
    so from the street the eaves of the survey (14 % of the roof plan) were see-through."""
    if not len(roofs):
        return np.zeros((0, 3, 3))
    fp = footprint(b)
    if fp.is_empty:
        return np.zeros((0, 3, 3))
    fp = fp.buffer(0.02)
    n = np.cross(roofs[:, 1] - roofs[:, 0], roofs[:, 2] - roofs[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ok = (ln > 1e-9) & (np.abs(n[:, 2]) > 1e-6 * np.maximum(ln, 1e-9))
    n[ok] /= ln[ok, None]
    d = (n * roofs[:, 0]).sum(1)
    key = np.column_stack([np.round(n[:, 0] / 0.02), np.round(n[:, 1] / 0.02), np.round(d / 0.05)]).astype(np.int64)
    out = []
    for k in np.unique(key[ok], axis=0):
        sel = ok & (key == k).all(1)
        plan = shapely.union_all([q for q in (shapely.Polygon(t[:, :2]) for t in roofs[sel]) if q.is_valid and q.area > 1e-6])
        o = shapely.make_valid(plan.difference(fp).simplify(0.05))
        if o.is_empty or o.area < 0.02:
            continue
        nn, dd = n[sel][0], d[sel][0]                     # n . p = d on the plane
        lift = lambda P, nn=nn, dd=dd: np.column_stack([P, (dd - nn[0] * P[:, 0] - nn[1] * P[:, 1]) / nn[2] - drop])
        out.append(_triangulate(o, lift))
    if not out:
        return np.zeros((0, 3, 3))
    tris = np.concatenate(out)
    up = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])[:, 2] > 0
    tris[up] = tris[up][:, ::-1]
    return tris


def roof_colors(blds):
    """Median orthophoto colour of every roof (footprint eroded 1.5 m against relief displacement)."""
    from geo import ortho_sampler
    ortho = ortho_sampler()
    cols = {}
    for b in blds:
        r = b["roofs"]
        if len(r) == 0:
            continue
        fp = shapely.MultiPoint(r.reshape(-1, 3)[:, :2]).convex_hull.buffer(-1.5)
        if fp.is_empty or fp.area < 1:
            fp = shapely.MultiPoint(r.reshape(-1, 3)[:, :2]).convex_hull
        x0, y0, x1, y1 = fp.bounds
        xs = np.arange(x0, x1, 1.0); ys = np.arange(y0, y1, 1.0)
        if len(xs) == 0 or len(ys) == 0:
            continue
        X, Y = np.meshgrid(xs, ys)
        inside = shapely.contains_xy(fp, X, Y)
        if not inside.any():
            continue
        c = ortho(X[inside], Y[inside])
        c = c[~np.isnan(c).any(1)]
        if len(c) < 3:
            continue
        cols[b["uuid"]] = np.median(c, 0) / 255.0
    return cols


# v2.0: a passage under every building that stands on a road or path of the network (a sottoportico,
# the customs canopy over the road at Ponte Tresa, a lane under a bell tower, or a line of swissTLM3D
# drawn a little into a house): the building is cut PASSAGE_CLEAR m high over the line along a band
# around it and the cut is closed by a ceiling and side walls, so no car runs into a solid block
PASSAGE_CLEAR = {"road": 4.2, "path": 3.0}                 # m of free height over the line
PASSAGE_LEAST = {"road": 3.0, "path": 2.2}                 # m, least free height under a roof kept over it (cars, vans)
# half width of the band cut (of the width of the line, at least m): the whole carriageway where the
# line runs through the building, the way of a car around the line where the building stands beside it
PASSAGE_HALF = {"road": (0.5, 1.2), "path": (0.5, 0.6)}
PASSAGE_SIDE = {"road": (0.3, 1.0), "path": (0.3, 0.5)}
PASSAGE_MARGIN = 0.15                                      # m added to the bands: no face left on their edge
PASSAGE_BELOW = 1.0                                        # m under the line the cut reaches (the walls' feet)


def network_ways(net, corridor=None):
    """[(line, band through, band beside, stations (n, 3), kind)] of every line of the network
    (network_mesh.Network) outside the Strada Cantonale corridor (its buildings were checked on the
    panoramas); the bridges too (the customs canopy of Ponte Tresa stands over the start of the bridge
    on the Tresa: the cut takes only the height of the deck). Round ends, so the bands of two lines
    that meet at an angle leave no wedge between them."""
    out = []
    for s in net.segs:
        a, n = s["first"], s["n"]
        P = np.column_stack([net.x[a:a + n], net.y[a:a + n], net.z[a:a + n]])
        line = shapely.LineString(P[:, :2])
        w = float(np.median(net.w[a:a + n]))
        bands = []
        for f, least in (PASSAGE_HALF[s["kind"]], PASSAGE_SIDE[s["kind"]]):
            band = line.buffer(max(f * w, least) + PASSAGE_MARGIN)
            if corridor is not None and corridor.intersects(band):
                band = band.difference(corridor)
            bands.append(band)
        if not bands[0].is_empty:
            out.append((line, bands[0], bands[1], P, s["kind"]))
    return out


def footprint(b):
    """Ground plan of a building: its floor triangles, the hull of its walls where it has none."""
    fl = b.get("floors")
    if fl is not None and len(fl):
        g = shapely.union_all([q for q in (shapely.Polygon(t[:, :2]) for t in fl) if q.is_valid and q.area > 1e-6])
        if not g.is_empty:
            return g
    return shapely.MultiPoint(b["walls"].reshape(-1, 3)[:, :2]).convex_hull


def _polys(g):
    return [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and q.area > 1e-5]


def _triangulate(g, to3):
    """Triangles (k, 3, 3) of the 2D polygons of g, lifted by to3((3, 2) -> (3, 3))."""
    out = [to3(np.asarray(t.exterior.coords)[:3]) for q in _polys(g)
           for t in shapely.constrained_delaunay_triangles(q).geoms]
    return np.array(out).reshape(-1, 3, 3)


def cut_passage(tris, P, zb, zt):
    """The triangles tris (k, 3, 3) without their parts inside the passage: polygon P (plan) between
    heights zb and zt; the pieces keep the facing of the triangle they come from."""
    out = []
    pb = P.bounds
    for tri in tris:
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        nn = np.linalg.norm(n)
        lo, hi = tri[:, :2].min(0), tri[:, :2].max(0)
        if (nn < 1e-9 or hi[0] < pb[0] or lo[0] > pb[2] or hi[1] < pb[1] or lo[1] > pb[3]
                or tri[:, 2].min() >= zt or tri[:, 2].max() <= zb):
            out.append(tri[None])
            continue
        if abs(n[2]) < 0.05 * nn:                  # a wall: cut in its own plane (u along it, z)
            h = np.array([-n[1], n[0]]) / np.hypot(n[0], n[1])
            o = tri[0, :2]
            u = (tri[:, :2] - o) @ h
            inter = shapely.LineString([o + u.min() * h, o + u.max() * h]).intersection(P)
            boxes = [shapely.box(uu.min(), zb, uu.max(), zt)
                     for g in getattr(inter, "geoms", [inter]) if g.geom_type == "LineString" and g.length > 1e-3
                     for uu in [(np.asarray(g.coords) - o) @ h]]
            if not boxes:
                out.append(tri[None])
                continue
            whole = shapely.Polygon(np.column_stack([u, tri[:, 2]]))
            rest = whole.difference(shapely.union_all(boxes))
            to3 = lambda c, o=o, h=h: np.column_stack([o + c[:, :1] * h, c[:, 1]])
        else:                                      # a roof or a floor: seen from above, where under zt
            below = []
            for i in range(3):
                p, q = tri[i], tri[(i + 1) % 3]
                if p[2] < zt:
                    below.append(p[:2])
                if (p[2] < zt) != (q[2] < zt):
                    below.append((p + (zt - p[2]) / (q[2] - p[2]) * (q - p))[:2])
            if len(below) < 3:
                out.append(tri[None])
                continue
            R = shapely.Polygon(below).buffer(0).intersection(P)
            if R.area < 1e-4:
                out.append(tri[None])
                continue
            whole = shapely.Polygon(tri[:, :2])
            rest = whole.difference(R)
            to3 = lambda c, t0=tri[0], n=n: np.column_stack(                 # on the plane of the triangle
                [c, t0[2] - ((c[:, 0] - t0[0]) * n[0] + (c[:, 1] - t0[1]) * n[1]) / n[2]])
        if rest.is_empty:
            continue
        if rest.equals(whole):
            out.append(tri[None])
            continue
        T = _triangulate(rest, to3)
        if len(T):
            flip = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]) @ n < 0
            T[flip] = T[flip][:, ::-1]
            out.append(T)
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def passage_shell(C, fp, zb, zt, top):
    """Ceiling of the passage C (plan, inside the footprint fp) at zt, facing down, where the building
    rises above it (top: its highest point), and its side walls from zb along the edges of C inside the
    building, facing the passage."""
    out = []
    if top > zt + 0.2:
        T = _triangulate(C, lambda c: np.column_stack([c, np.full(3, zt)]))
        up = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, 2] > 0
        T[up] = T[up][:, ::-1]
        out.append(T)
    zc = min(zt, top)
    if zc < zb + 0.1:
        return np.concatenate(out) if out else np.zeros((0, 3, 3))
    inner = fp.buffer(-0.05)
    for q in _polys(C):
        q = shapely.geometry.polygon.orient(q, 1.0)            # the passage on the left of every edge
        for ring in [q.exterior] + list(q.interiors):
            c = np.asarray(ring.coords)
            for a, b in zip(c[:-1], c[1:]):
                if np.hypot(*(b - a)) < 0.02 or not inner.contains(shapely.Point(0.5 * (a + b))):
                    continue
                left = np.array([a[1] - b[1], b[0] - a[0], 0.0])
                T = np.array([[np.r_[a, zb], np.r_[b, zb], np.r_[b, zc]], [np.r_[a, zb], np.r_[b, zc], np.r_[a, zc]]])
                flip = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]) @ left < 0
                T[flip] = T[flip][:, ::-1]
                out.append(T)
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def passages(b, walls, roofs, ways, tree):
    """walls, roofs of building b with the passages of the ways (network_ways) that cross it cut out,
    and the triangles closing them (ceilings and side walls, plastered)."""
    if tree is None:
        return walls, roofs, np.zeros((0, 3, 3))
    fp = footprint(b)
    hit = tree.query(fp, predicate="intersects")
    if not len(hit):
        return walls, roofs, np.zeros((0, 3, 3))
    top = max(walls[:, :, 2].max() if len(walls) else -1e9, roofs[:, :, 2].max() if len(roofs) else -1e9)
    cs, zbs, zts = [], [], []
    for i in hit:
        line, through, beside, S, kind = ways[i]
        band = through if fp.intersects(line) else beside
        C = band.intersection(fp)
        if C.area < 0.05:
            continue
        near = shapely.contains_xy(C.buffer(2.0), S[:, 0], S[:, 1])
        if not near.any():
            near = np.zeros(len(S), bool)
            near[np.argmin(shapely.distance(C, shapely.points(S[:, :2])))] = True
        zb = float(S[near, 2].min()) - PASSAGE_BELOW
        zr = float(S[near, 2].max())
        zt = zr + PASSAGE_CLEAR[kind]
        # the roof over the passage stays where the passage fits under it (a canopy just over the road)
        if len(roofs):
            rings = np.concatenate([roofs[:, :, :2], roofs[:, :1, :2]], axis=1)
            over = roofs[shapely.intersects(C, shapely.polygons(rings))]
            if len(over):
                low = float(over[:, :, 2].min()) - 0.3
                if zr + PASSAGE_LEAST[kind] <= low < zt:
                    zt = low
        if top <= zb + 0.1:                        # a deck high over the building: nothing to cut
            continue
        walls = cut_passage(walls, band, zb, zt)
        roofs = cut_passage(roofs, band, zb, zt)
        cs.append(C)
        zbs.append(zb)
        zts.append(zt)
    if not cs:
        return walls, roofs, np.zeros((0, 3, 3))
    # one ceiling and one set of side walls for all the passages of the building: lines that meet or
    # cross under it (the customs canopy of Ponte Tresa) keep each other's way free
    return walls, roofs, passage_shell(shapely.union_all(cs), fp, min(zbs), max(zts), top)


def split_u(tris, a, cuts):
    """Triangles (k, 3, 3) of a vertical facade cut by the vertical planes u = c (u = p . a) for every c
    of cuts: (m, 3, 3)."""
    out = []
    for t in tris:
        polys = [t]
        for c in cuts:
            nxt = []
            for P in polys:
                u = P @ a - c
                if (u >= -1e-6).all() or (u <= 1e-6).all():
                    nxt.append(P)
                    continue
                lo, hi = [], []
                for i in range(len(P)):
                    A, B, ua, ub = P[i], P[(i + 1) % len(P)], u[i], u[(i + 1) % len(P)]
                    if ua <= 0:
                        lo.append(A)
                    if ua >= 0:
                        hi.append(A)
                    if (ua < 0 < ub) or (ub < 0 < ua):
                        X = A + (B - A) * (ua / (ua - ub))
                        lo.append(X)
                        hi.append(X)
                nxt += [np.array(Q) for Q in (lo, hi) if len(Q) >= 3]
            polys = nxt
        for P in polys:
            for i in range(1, len(P) - 1):
                out.append([P[0], P[i], P[i + 1]])
    out = np.array(out, float).reshape(-1, 3, 3)
    area = 0.5 * np.linalg.norm(np.cross(out[:, 1] - out[:, 0], out[:, 2] - out[:, 0]), axis=1)
    return out[area > 1e-6]


def houses(b, rest, style, rec, height, roof_rgb, wall_col, sv, pp, by_egid, shop_pts):
    """(walls, [(mask of the wall triangles, style)]) of a building: one group, or one per house of the
    survey (pp: facades.mu_parts): the facades are cut where one house ends and the next begins (seen 0.3 m
    inside the wall), every piece goes to its house, which has its own record of the register (by EGID),
    style, shop front and a tone a little different from its neighbours'."""
    import facades
    import texturing
    if not pp or not len(rest):
        return rest, [(np.ones(len(rest), bool), style)]
    polys = [poly for poly, _ in pp]

    def owner(xy):
        P = shapely.points(xy)
        return np.argmin(np.column_stack([shapely.distance(poly, P) for poly in polys]), axis=1)
    pieces, owners = [], []
    for idx, n, d0 in texturing.facade_groups(rest):
        tris = rest[idx]
        a = np.array([-n[1], n[0], 0.0])
        o = np.array([n[0] * d0, n[1] * d0])
        u = tris.reshape(-1, 3) @ a
        us = np.arange(u.min(), u.max() + 0.25, 0.25)
        ow = owner(o[None] + us[:, None] * a[None, :2] - np.asarray(n)[None, :2] * 0.3)
        cuts = [0.5 * (us[i] + us[i + 1]) for i in range(len(us) - 1) if ow[i] != ow[i + 1]]
        if cuts:
            tris = split_u(tris, a, cuts)
        cu = tris.mean(1) @ a
        pieces.append(tris)
        owners.append(owner(o[None] + cu[:, None] * a[None, :2] - np.asarray(n)[None, :2] * 0.3))
    rest = np.concatenate(pieces)
    own = np.concatenate(owners)
    out = []
    for k, (poly, egid) in enumerate(pp):
        sel = own == k
        if not sel.any():
            continue
        prec = by_egid.get(egid, {}) if egid else {}
        ptone = None
        if wall_col is not None:                           # the block's tone, a little different per house
            prng = facades.rng_of(b["uuid"] + str(k))
            ptone = np.clip(np.asarray(wall_col) * (1 + prng.normal(0, 0.045)) + prng.normal(0, 0.02, 3), 0, 1)
        shop = bool(shapely.intersects(poly.buffer(SHOP_NEAR), shop_pts)) if shop_pts is not None else False
        pst = facades.style_of(b, prec or rec, poly.area, height, roof_rgb, measured=ptone,
                               shutter=(sv["shutter"], sv.get("shutter_frac", 0.0)) if sv.get("shutter") else None,
                               shop=shop, key=b["uuid"] + "/" + (egid or str(k)))
        out.append((sel, pst))
    return rest, out


def load_buildings():
    """The buildings of the level: swissBUILDINGS3D (buildings.pkl) without the ones gone from the ground
    and with the ones of the cadastral survey it does not model (missing_buildings.py, v2.2)."""
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    diff = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "buildings_diff.json")
    added = os.path.join(WORK, "buildings_added.pkl")
    if os.path.exists(diff):
        gone = {r["uuid"] for r in json.load(open(diff)).get("gone", [])}
        blds = [b for b in blds if b["uuid"] not in gone]
    if os.path.exists(added):
        blds += pickle.load(open(added, "rb"))
    return blds


def street_index(net):
    """(cKDTree of the stations of the roads of the network, main street per station) for the facades
    (which side of a building faces the street, shop fronts on the main streets)."""
    if net is None:
        return None
    from scipy.spatial import cKDTree
    main_cls = {"10m Strasse", "8m Strasse", "6m Strasse", "Autostrasse", "Autobahn"}
    road = np.array([net.segs[k]["kind"] == "road" for k in net.seg], bool)
    main = np.array([net.segs[k]["class"] in main_cls or net.segs[k].get("owner") == "Kanton" for k in net.seg], bool)
    return cKDTree(np.column_stack([net.x[road], net.y[road]])), main[road]


def build(level_dir, level_name, keep=None, ways=None, net=None):
    """ways: network_ways, the passages to cut; net: the network (network_mesh.Network) for the
    facades' streets."""
    import texturing
    import facades
    import bld_textures
    from geo import Grid
    blds = load_buildings()
    shp_dir = os.path.join(level_dir, "art", "shapes", "buildings")
    os.makedirs(shp_dir, exist_ok=True)
    import vanilla
    v1_walls = None
    if not vanilla.have_game():              # the facade tones of the released level (measured in the photos)
        from scipy.spatial import cKDTree
        wp, wc = vanilla.wall_colors()
        v1_walls = (cKDTree(wp), wc) if len(wp) else None
    # v2.2: original procedural textures (bld_textures.py): plaster, stone, plinth, openings, roofs
    index, means = bld_textures.build(shp_dir)
    L = f"/levels/{level_name}/art/shapes/buildings"
    rcol = roof_colors(blds)
    fps = [footprint(b) for b in blds]
    pos = {b["uuid"]: i for i, b in enumerate(blds)}
    gwr = facades.gwr_join(blds, fps)
    measured = {}
    if os.path.exists(facades.FACADE_COLORS):
        measured = json.load(open(facades.FACADE_COLORS))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    ctx = facades.Context(blds, fps, lambda x, y: dtm.sample(x, y), street_index(net))
    # the buildings with a shop, bar, office ... of OSM (within SHOP_NEAR m of the footprint): shop fronts
    import osm
    pts = [(x, y) for x, y, k in osm.pois() if facades.shop_front(k)]
    with_shop = set()
    shop_pts = shapely.multipoints(pts) if pts else None
    if pts:
        hit_p, hit_b = shapely.STRtree(fps).query(shapely.points(pts), predicate="dwithin", distance=SHOP_NEAR)
        with_shop = {blds[i]["uuid"] for i in hit_b}
    # the houses of the survey inside the blocks of swissBUILDINGS3D, and the register by EGID
    parts = facades.mu_parts(blds, fps)
    by_egid = facades.gwr_by_egid()
    print("blocks of several houses", len(parts), "houses", sum(len(v) for v in parts.values()), flush=True)
    em = facades.Emitter(index)
    atlas = texturing.Atlas(4096)
    tiles = {}
    for b in blds:
        if keep is not None and not keep(b):
            continue
        c = (np.array(b["bbox"][0]) + np.array(b["bbox"][1])) / 2
        tiles.setdefault((int(np.floor(c[0] / TILE)), int(np.floor(c[1] / TILE))), []).append(b)
    out, n_photo, n_pass = [], 0, 0
    stats = {"openings": 0, "gwr": 0, "measured": 0, "roofs": {}, "use": {}, "stone": 0}
    wtree = shapely.STRtree([w[1] for w in ways]) if ways else None
    mean = lambda k: np.array(means[k], float)
    for (tx, ty), bl in sorted(tiles.items()):
        mb = bng.MeshBuilder()
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        for b in bl:
            ob = orient(b)
            walls, roofs = ob["walls"], ob["roofs"]
            assigned = np.zeros(len(walls), bool)
            wall_col = None
            f = os.path.join(WORK, "facades", f"{b['uuid'].strip('{}')}.npz")
            if len(walls) and os.path.exists(f):
                d = np.load(f)
                meds = []
                for k in range(int(d["n"]) if "n" in d else 0):
                    img, idx, mp = d[f"img{k}"], d[f"idx{k}"], d[f"map{k}"]
                    if NO_PHOTO:                               # keep only the measured facade tone
                        meds.append(np.median(img.reshape(-1, 3), 0))
                        continue
                    u0, ul, v0, vl = mp[:4]; axis = mp[4:7]
                    page, (ax, ay, aw, ah) = atlas.add(img)
                    t = walls[idx].reshape(-1, 3)
                    U = ax + ((t @ axis) - u0) / max(ul, 1e-6) * aw
                    V = ay + ((v0 + vl) - t[:, 2]) / max(vl, 1e-6) * ah
                    mb.add(f"mp_bld_photo_{page}", t, uvs=np.column_stack([U, 1.0 - V]),
                           normals=bng.flat_normals_soup(t))
                    assigned[idx] = True
                    meds.append(np.median(img.reshape(-1, 3), 0))
                    n_photo += 1
                if meds:
                    wall_col = np.median(np.array(meds), 0) / 255.0
            if wall_col is None and v1_walls is not None and len(walls):
                V0 = walls.reshape(-1, 3)
                dd, jj = v1_walls[0].query(V0[::3][:50])
                if (dd < 0.05).mean() > 0.5:               # the same building in the released level
                    c1 = np.median(v1_walls[1][jj[dd < 0.05]], 0)
                    # the default tone of the buildings never photographed is no measurement
                    if np.abs(c1 - V1_DEFAULT / 0.9).max() > 0.01:
                        wall_col = np.clip(c1 * 0.9, 0, 1)
            sv = measured.get(b["uuid"], {})
            if wall_col is None and sv:                     # the tone seen in the panoramas (sv_facades.py)
                wall_col = facades.sv_tone(sv["rgb"])
            rec = gwr.get(b["uuid"], {})
            fp = fps[pos[b["uuid"]]]
            height = float(b["bbox"][1][2] - b["bbox"][0][2])
            style = facades.style_of(b, rec, fp.area, height, rcol.get(b["uuid"]), measured=wall_col,
                                     shutter=(sv["shutter"], sv.get("shutter_frac", 0.0)) if sv.get("shutter") else None,
                                     shop=b["uuid"] in with_shop)
            stats["gwr"] += bool(rec)
            stats["measured"] += wall_col is not None
            stats["use"][style["use"]] = stats["use"].get(style["use"], 0) + 1
            rest = walls[~assigned]
            # the passages of the ways under the building first: the openings and the plinth go on the walls
            # that are left (none hangs in a passage over a road)
            rest, roofs, shell = passages(b, rest, roofs, ways, wtree)
            # the houses of the survey in a block of swissBUILDINGS3D: every one with the walls nearest to it,
            # its own record of the register, style, floors, door and tone (a row of houses of a village core)
            rest, groups = houses(b, rest, style, rec, height, rcol.get(b["uuid"]), wall_col, sv, parts.get(b["uuid"]),
                                  by_egid, shop_pts)
            if len(groups) > 1:
                stats["parts"] = stats.get("parts", 0) + len(groups)
            # windows, doors and plinth on the walls of the building (of every house of a block)
            if len(rest) and style["use"] != "none":
                for sel, pst in groups:
                    if pst["use"] != "none":
                        stats["openings"] += facades.layout_building(b, rest[sel], pst, ctx, em)
                    stats["shops"] = stats.get("shops", 0) + int(pst["shop"])
            if len(shell):
                rest = np.concatenate([rest, shell])
                groups = [(np.r_[sel, np.zeros(len(shell), bool)], pst) for sel, pst in groups]
                groups[0][0][-len(shell):] = True               # the passage's ceiling and sides: the first house
                n_pass += 1
            # v2.8: the walls are drawn from both sides by their materials (WALL_TWO_SIDED); up to v2.7 only the
            # walls whose side the rays could not tell got a back face (undecided_walls), a copy of each triangle
            z_foot = float(rest[:, :, 2].min()) if len(rest) else 0.0
            for sel, pst in groups:
                if not sel.any():
                    continue
                part = rest[sel]
                V = part.reshape(-1, 3)
                # v2.4: darker towards the foot of the wall (ambient occlusion and splashes), in the colour of
                # the vertices: GROUND_AO at the ground, none from GROUND_AO_H m up
                ao = 1.0 - GROUND_AO * np.clip(1.0 - (V[:, 2] - z_foot) / GROUND_AO_H, 0.0, 1.0)
                if pst["stone"]:
                    stats["stone"] += 1
                    tone = np.clip(0.97 + 0.03 * (pst["tone"] - pst["tone"].mean()), 0, 1)
                    mb.add("bld_stone", V, uvs=wall_uvs(part) / 3.0, normals=bng.flat_normals_soup(V),
                           colors=np.column_stack([tone[None, :] * ao[:, None], np.ones(len(V))]))
                else:
                    tone = np.clip(pst["tone"] / mean("t_bld_plaster"), 0, 1)
                    mb.add("bld_plaster", V, uvs=wall_uvs(part) / 5.0, normals=bng.flat_normals_soup(V),
                           colors=np.column_stack([tone[None, :] * ao[:, None], np.ones(len(V))]))
            # chimneys: plastered stacks with a concrete cap
            stack, cap = facades.chimneys(b, roofs, style)
            if len(stack):
                V = stack.reshape(-1, 3)
                mb.add("bld_plaster", V, uvs=wall_uvs(stack) / 5.0, normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(style["tone"] / mean("t_bld_plaster"), 0, 1), 1.0])
                V = cap.reshape(-1, 3)
                mb.add("bld_roof_flat", V, uvs=V[:, :2] / 4.0, normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(np.array([0.62, 0.62, 0.60]) / mean("t_roof_flat"), 0, 1), 1.0])
                stats["chimneys"] = stats.get("chimneys", 0) + len(stack) // 8
            sof = soffits(b, roofs)
            if len(sof):
                V = sof.reshape(-1, 3)
                mb.add("bld_plaster", V, uvs=V[:, :2] / 5.0, normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(0.8 * style["tone"] / mean("t_bld_plaster"), 0, 1), 1.0])
                stats["soffit_m2"] = stats.get("soffit_m2", 0.0) + float(
                    0.5 * np.linalg.norm(np.cross(sof[:, 1] - sof[:, 0], sof[:, 2] - sof[:, 0]), axis=1).sum())
            if len(roofs):
                col = rcol.get(b["uuid"], np.array([0.55, 0.42, 0.36]))
                nrm = np.cross(roofs[:, 1] - roofs[:, 0], roofs[:, 2] - roofs[:, 0])
                slope = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12),
                                                     0, 1)))
                kinds = np.array([facades.roof_kind(style, sl, col) for sl in slope])
                for kind in np.unique(kinds):
                    rt = roofs[kinds == kind]
                    V = rt.reshape(-1, 3)
                    stats["roofs"][kind] = stats["roofs"].get(kind, 0) + 1
                    mb.add(f"bld_roof_{kind}", V, uvs=roof_uvs(rt, bld_textures.ROOF_TILE[kind]),
                           normals=bng.flat_normals_soup(V),
                           colors=np.r_[np.clip(col / mean(f"t_roof_{kind}"), 0, 1), 1.0])
        # the openings and plinths of the tile's buildings
        if em.V:
            V = np.concatenate(em.V).reshape(-1, 3)
            mb.add("bld_openings", V, uvs=np.concatenate(em.UV).reshape(-1, 2), normals=bng.flat_normals_soup(V))
        if em.LV:                                        # v2.8: the same openings, lit at night
            V = np.concatenate(em.LV).reshape(-1, 3)
            mb.add("bld_openings_lit", V, uvs=np.concatenate(em.LUV).reshape(-1, 2), normals=bng.flat_normals_soup(V))
            stats["lit_windows"] = stats.get("lit_windows", 0) + len(em.LV)
        if em.PV:
            V = np.concatenate(em.PV).reshape(-1, 3)
            C = np.repeat(np.array([np.r_[np.clip(c / mean("t_bld_plinth"), 0, 1), 1.0] for c in em.PC]), 6, 0)
            mb.add("bld_plinth", V, uvs=np.concatenate(em.PUV).reshape(-1, 2), normals=bng.flat_normals_soup(V),
                   colors=C)
        if em.BV:                                        # balcony slabs, plastered in the tone of the house
            V = np.concatenate(em.BV).reshape(-1, 3)
            C = np.repeat(np.array([np.r_[np.clip(c / mean("t_bld_plaster"), 0, 1), 1.0] for c in em.BC]), 6, 0)
            mb.add("bld_plaster", V, uvs=np.column_stack([V[:, 0] + V[:, 1], V[:, 2]]) / 5.0,
                   normals=bng.flat_normals_soup(V), colors=C)
            stats["balconies"] = stats.get("balconies", 0) + len(em.BC) // 5
        em.LV, em.LUV = [], []
        em.V, em.UV, em.PV, em.PUV, em.PC, em.BV, em.BC = [], [], [], [], [], [], []
        if mb.empty():
            continue
        rel = f"art/shapes/buildings/bld_{tx:+03d}_{ty:+03d}.dae"
        mb.write_dae(os.path.join(level_dir, rel), name="bld", origin=origin)
        out.append((f"/levels/{level_name}/{rel}", origin, mb.triangle_count()))
    T = lambda n, k: f"{L}/{n}_{k}"
    mats = [bng.material("bld_plaster", T("t_bld_plaster", "b.color.png"), T("t_bld_plaster", "nm.normal.png"),
                         T("t_bld_plaster", "r.data.png"), T("t_bld_plaster", "ao.data.png"), vert_color=True, extra=WALL_TWO_SIDED),
            bng.material("bld_stone", T("t_bld_stone", "b.color.png"), T("t_bld_stone", "nm.normal.png"),
                         T("t_bld_stone", "r.data.png"), T("t_bld_stone", "ao.data.png"), vert_color=True, extra=WALL_TWO_SIDED),
            bng.material("bld_plinth", T("t_bld_plinth", "b.color.png"), T("t_bld_plinth", "nm.normal.png"),
                         T("t_bld_plinth", "r.data.png"), T("t_bld_plinth", "ao.data.png"), vert_color=True, extra=WALL_TWO_SIDED),
            bng.material("bld_openings", T("t_bld_openings", "b.color.png"), T("t_bld_openings", "nm.normal.png"),
                         T("t_bld_openings", "r.data.png"), T("t_bld_openings", "ao.data.png"), alpha_test=110,
                         detail={"opacityMap": T("t_bld_openings", "o.data.png")}),
            # v2.8: the lit windows, the light of the room shows through the glass at night: the game sets the
            # instance colour of the building (NIGHT) after sunset and the emissive map glows in that colour
            bng.material("bld_openings_lit", T("t_bld_openings", "b.color.png"), T("t_bld_openings", "nm.normal.png"),
                         T("t_bld_openings", "r.data.png"), T("t_bld_openings", "ao.data.png"), alpha_test=110,
                         detail={"opacityMap": T("t_bld_openings", "o.data.png"),
                                 "emissiveMap": T("t_bld_openings", "e.color.png"), "emissiveFactor": [1, 1, 1],
                                 "instanceEmissive": True})]
    for kind in bld_textures.ROOF_TILE:
        n = f"t_roof_{kind}"
        ao = T(n, "ao.data.png") if kind != "flat" else None              # v2.4
        mats.append(bng.material(f"bld_roof_{kind}", T(n, "b.color.png"), T(n, "nm.normal.png"), T(n, "r.data.png"),
                                 ao, vert_color=True, metallic=0.3 if kind == "metal" else None))
    for i, page in enumerate(atlas.pages if n_photo else []):     # no empty page without photo facades
        rel = f"art/shapes/buildings/bld_photo_{i}.jpg"
        cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        mats.append(bng.material(f"mp_bld_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.85, extra=WALL_TWO_SIDED))
    bng.write_materials(os.path.join(shp_dir, "main.materials.json"), mats)
    # the atlas index and the texture means are for this build only (not level files)
    for fn in ("bld_openings.json", "bld_textures.json"):
        if os.path.exists(os.path.join(shp_dir, fn)):
            os.replace(os.path.join(shp_dir, fn), os.path.join(WORK, fn))
    stats["photo_facades"] = n_photo
    stats["passages"] = n_pass
    json.dump(stats, open(os.path.join(WORK, "buildings_stats.json"), "w"), indent=1)
    print("building photo facades", n_photo, "atlas pages", len(atlas.pages) if n_photo else 0,
          "buildings with a passage", n_pass, "stats", {k: v for k, v in stats.items()})
    return out


# --------------------------------------------------------------------------------------------------
# Details of the houses (v2.8): gutters and downpipes, TV aerials, satellite dishes and solar panels, in a
# built level.
#
# The buildings of the level are the swissBUILDINGS3D roofs and walls (buildings.py), with the windows, doors and
# balconies drawn on the façades: no gutter, no downpipe, nothing on the roofs. Here, from the meshes of the
# level and the Federal Register of Buildings (dati/gwr_area.json.gz), by rules (no open data has them):
# - gutters along the eaves of every pitched roof: the boundary edges of the roof faces that are level (within
#   EAVE_DZ m) and lower than the roof beside them, chained into runs and joined where they run on straight; a
#   channel GUTTER_W m wide and GUTTER_H m deep just outside the wall, zinc grey or copper (the same for a roof);
# - downpipes (DOWNPIPE m square, down to the ground) at both ends of the runs of eaves of PIPE_RUN m or more,
#   the longest runs first, PIPES_MAX a roof at most;
# - on the roofs of the houses (GWR residential categories): a TV aerial on the ridge of AERIAL_SHARE of those built
#   before 1991 (a mast and two cross-arms), a satellite dish on DISH_SHARE of them (turned to the satellites
#   over the equator at 13 degrees east, as most dishes in Ticino), solar panels on PV_SHARE of those with a roof
#   face turned within PV_AZ degrees of south, PV_MIN m2 or more: a rectangle of panels PV_INSET m inside it;
# - which house gets what: the same every build (a hash of its place);
# - meshes in MissionGroup/buildings/details, no collision: gutters, downpipes, aerials and dishes in DETAIL_TILE m tiles
#   drawn up to NEAR_DRAW m, the panels in PV_TILE m tiles up to PV_DRAW m (the game measures the drawing distance
#   from the centre of a shape: the draw distance over the radius of the tile, so that the details of a house are
#   there when the camera is near it, and the tiles no smaller, so that they add few objects to the level).
# Everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish house_details
# --------------------------------------------------------------------------------------------------

DETAIL_TILE, PV_TILE = 512.0, 1024.0             # m
EAVE_DZ, EAVE_MIN = 0.05, 0.5             # m
GUTTER_W, GUTTER_H, GUTTER_DROP = 0.12, 0.10, 0.03
DOWNPIPE = 0.08
PIPE_RUN, PIPES_MAX = 4.0, 4               # m of eaves for a downpipe; downpipes a roof at most
AERIAL_SHARE, DISH_SHARE, PV_SHARE = 0.30, 0.20, 0.20
PV_AZ, PV_MIN, PV_INSET = 50.0, 12.0, 0.5
NEAR_DRAW, PV_DRAW = 450.0, 1100.0
DISH_AZ, DISH_EL = 174.0, 36.0            # degrees: the satellites at 13 E seen from Lugano
RESIDENTIAL = {1020, 1021, 1025, 1030, 1040}
OLD = 8017                                # GWR period code: built in 1990 or before


def share(key, salt, p):
    """True for a share p of the keys, the same every build."""
    h = hashlib.md5(f"{salt}:{key}".encode()).digest()
    return int.from_bytes(h[:4], "little") / 2 ** 32 < p


def quad(a, b, c, d):
    return [np.array([a, b, c]), np.array([a, c, d])]


def boxv(c, u, half, z0, z1):
    """The four sides and the top of an upright box (k, 3, 3): centre c (2,), axis u, half sizes."""
    n = np.array([-u[1], u[0]])
    P = [c + u * half[0] + n * half[1], c - u * half[0] + n * half[1], c - u * half[0] - n * half[1],
         c + u * half[0] - n * half[1]]
    tri = []
    for a, b in zip(P, P[1:] + P[:1]):
        tri += quad(np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z1])
    tri += quad(*[np.r_[p, z1] for p in P])
    return tri


def beam(a, b, w):
    """A thin square bar from a to b (3,), w across."""
    d = b - a
    L = np.linalg.norm(d)
    d = d / L
    s = np.cross(d, [0, 0, 1.0])
    if np.linalg.norm(s) < 1e-6:
        s = np.array([1.0, 0, 0])
    s = s / np.linalg.norm(s) * w / 2
    t = np.cross(d, s)
    t = t / np.linalg.norm(t) * w / 2
    C = [s + t, -s + t, -s - t, s - t]
    tri = []
    for p, q in zip(C, C[1:] + C[:1]):
        tri += quad(a + p, a + q, b + q, b + p)
    return tri


def dish(c, z):
    """A dish of 0.6 m on a short arm at c (2,) z, facing DISH_AZ / DISH_EL."""
    az, el = math.radians(DISH_AZ), math.radians(DISH_EL)
    f = np.array([math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])
    u = np.cross(f, [0, 0, 1.0])
    u /= np.linalg.norm(u)
    v = np.cross(u, f)
    o = np.r_[c, z + 0.55]
    rim = [o + 0.30 * (math.cos(a) * u + math.sin(a) * v) - 0.06 * f for a in np.linspace(0, 2 * np.pi, 11)[:-1]]
    tri = [np.array([o, rim[k], rim[(k + 1) % 10]]) for k in range(10)]
    tri += beam(np.r_[c, z], o - 0.05 * f, 0.04)
    tri += beam(o, o + 0.35 * f, 0.025)
    return tri


def strip(a, b, w, up=(0, 0, 1.0)):
    """A thin flat bar from a to b (3,), w wide across `up` (two triangles; a double-sided material)."""
    s = np.cross(b - a, up)
    s = s / max(np.linalg.norm(s), 1e-9) * w / 2
    return quad(a - s, b - s, b + s, a + s)


def aerial(c, z):
    """A TV aerial: a 2.2 m mast and two cross-arms with their elements, at c (2,) on the ridge z."""
    top = np.r_[c, z + 2.2]
    tri = beam(np.r_[c, z - 0.2], top, 0.04)
    for h, L in ((2.0, 1.2), (1.5, 0.9)):
        a, b = np.r_[c[0] - L / 2, c[1], z + h], np.r_[c[0] + L / 2, c[1], z + h]
        tri += strip(a, b, 0.025, up=(0, 1.0, 0))
        for x in np.linspace(-L / 2 + 0.1, L / 2 - 0.1, 4):
            tri += strip(np.r_[c[0] + x, c[1] - 0.25, z + h], np.r_[c[0] + x, c[1] + 0.25, z + h], 0.015, up=(1.0, 0, 0))
    return tri


def pv_texture(size=256):
    """Solar cells: dark blue, thin light lines between them and a frame (one panel 1 x 1.7 m)."""
    img = np.zeros((size, size, 3), np.uint8)
    img[:] = (22, 30, 52)
    for k in range(0, size, size // 6):
        img[:, k:k + 1] = (70, 78, 96)
    for k in range(0, size, size // 10):
        img[k:k + 1, :] = (70, 78, 96)
    img[:3, :] = img[-3:, :] = (150, 152, 156)
    img[:, :3] = img[:, -3:] = (150, 152, 156)
    b = io.BytesIO()
    Image.fromarray(img).save(b, "PNG", optimize=True)
    return b.getvalue()


def roof_parts(V, parts):
    """(pitched roof triangles as vertex ids (k, 3), flat roof faces) of a building shape."""
    pitched = [idx[:, 0].reshape(-1, 3) for m, idx in parts if "roof" in m and "flat" not in m]
    return np.concatenate(pitched) if pitched else np.zeros((0, 3), np.int64)


def components(P):
    """Connected components of triangles (k, 3) of welded vertex ids: label per triangle."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    k = len(P)
    rows = np.repeat(np.arange(k), 3)
    cols = P.ravel()
    n = cols.max() + 1
    M = coo_matrix((np.ones(len(rows)), (rows, cols + k)), shape=(k + n, k + n))
    _, lab = connected_components(M, directed=False)
    return lab[:k]


def house_details(W, T, ground, gwr, rep):
    """{material: [triangles]} of the details of the houses of one building shape (world coordinates W)."""
    out = {}

    def add(m, tris):
        if tris:
            out.setdefault(m, []).extend(tris)
    if not len(T):
        return out
    key = np.round(W * 1000).astype(np.int64)
    _, pid = np.unique(key, axis=0, return_inverse=True)
    pid = pid.ravel()
    rep_v = np.zeros(pid.max() + 1, np.int64)
    rep_v[pid] = np.arange(len(pid))
    P = pid[T]
    X = W[rep_v]                                           # one position per welded vertex
    t3 = X[P]
    nrm = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
    area = 0.5 * np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    nrm *= np.where(nrm[:, 2] < 0, -1.0, 1.0)[:, None]
    lab = components(P)
    # eaves: level boundary edges lower than their face
    E = np.concatenate([P[:, [0, 1]], P[:, [1, 2]], P[:, [2, 0]]])
    F = np.tile(np.arange(len(P)), 3)
    _, inv, cnt = np.unique(np.sort(E, 1), axis=0, return_inverse=True, return_counts=True)
    b = cnt[inv.ravel()] == 1
    E, F = E[b], F[b]
    A, B = X[E[:, 0]], X[E[:, 1]]
    L = np.linalg.norm(B[:, :2] - A[:, :2], axis=1)
    cz = t3[F].mean(1)
    ok = (np.abs(B[:, 2] - A[:, 2]) < EAVE_DZ) & (L > EAVE_MIN) & (cz[:, 2] > (A[:, 2] + B[:, 2]) / 2 + 0.1)
    E, F, A, B, L, cz = E[ok], F[ok], A[ok], B[ok], L[ok], cz[ok]
    d = (B[:, :2] - A[:, :2]) / L[:, None]
    out_n = np.column_stack([d[:, 1], -d[:, 0]])
    side = (((A[:, :2] + B[:, :2]) / 2 - cz[:, :2]) * out_n).sum(1)
    out_n *= np.where(side < 0, -1.0, 1.0)[:, None]                         # away from the roof
    copper = {c: share(tuple(np.round(t3[lab == c].reshape(-1, 3)[:, :2].mean(0)).astype(int)), "copper", 0.35)
              for c in np.unique(lab)}
    # runs of eaves: the edges chained through the vertices they share, cut where the run turns
    at = {}
    for k, e in enumerate(E):
        for v in e:
            at.setdefault(int(v), []).append(k)
    seen = np.zeros(len(E), bool)
    chains = []
    starts = [v for v, ks in at.items() if len(ks) == 1] + [int(e[0]) for e in E]
    for v0 in starts:
        ks = [k for k in at[v0] if not seen[k]]
        if not ks:
            continue
        verts, edges, v = [v0], [], v0
        while True:
            nxt = [k for k in at[v] if not seen[k]]
            if not nxt:
                break
            k = nxt[0]
            seen[k] = True
            edges.append(k)
            v = int(E[k][1] if E[k][0] == v else E[k][0])
            verts.append(v)
            if len(at[v]) > 2:
                break
        chains.append((verts, edges))
    pipes = {}
    for verts, edges in chains:
        f = F[edges[0]]
        m = "mp_house_copper" if copper[lab[f]] else "mp_house_zinc"
        run = [0]
        for i in range(1, len(edges) + 1):
            end = i == len(edges)
            if not end:
                d0, d1 = d[edges[run[0]]], d[edges[i]]
                d1 = d1 * (1 if np.dot(X[verts[i + 1], :2] - X[verts[i], :2], d1) > 0 else -1)
                d0 = d0 * (1 if np.dot(X[verts[run[0] + 1], :2] - X[verts[run[0]], :2], d0) > 0 else -1)
                if np.dot(d0, d1) > math.cos(math.radians(5)) and abs(X[verts[i], 2] - X[verts[run[0]], 2]) < 0.03:
                    continue
            a, bb, o = X[verts[run[0]]], X[verts[i]], out_n[edges[run[0]]]
            z = (a[2] + bb[2]) / 2 - GUTTER_DROP
            p0, p1 = a[:2], bb[:2]
            i0, i1 = np.r_[p0, z], np.r_[p1, z]                                  # at the wall, top
            ib0, ib1 = np.r_[p0, z - GUTTER_H], np.r_[p1, z - GUTTER_H]
            ob0, ob1 = np.r_[p0 + o * GUTTER_W, z - GUTTER_H], np.r_[p1 + o * GUTTER_W, z - GUTTER_H]
            ot0, ot1 = np.r_[p0 + o * GUTTER_W, z], np.r_[p1 + o * GUTTER_W, z]
            add(m, quad(ib0, ob0, ob1, ib1) + quad(ob0, ot0, ot1, ob1) + quad(i0, ib0, ib1, i1))
            rep["gutter_m"] += float(np.linalg.norm(p1 - p0))
            run = [i]
        length = float(L[edges].sum())
        if length < PIPE_RUN:
            continue
        ends = [(verts[0], edges[0], verts[1]), (verts[-1], edges[-1], verts[-2])]
        if verts[0] == verts[-1]:                       # a ring of eaves: two corners across
            h = len(verts) // 2
            ends = [(verts[0], edges[0], verts[1]), (verts[h], edges[h], verts[h + 1])]
        pipes.setdefault(lab[f], []).append((length, ends, m))
    # downpipes: at both ends of the longest runs, PIPES_MAX a roof at most, none closer than 1.5 m
    for c, runs in pipes.items():
        put = []
        for length, ends, m in sorted(runs, key=lambda r: -r[0]):
            for v, k, w in ends:
                if len(put) >= PIPES_MAX:
                    break
                o = out_n[k]
                q = X[v, :2] + o * (DOWNPIPE / 2 + 0.01) + (X[w, :2] - X[v, :2]) / max(
                    np.linalg.norm(X[w, :2] - X[v, :2]), 1e-9) * 0.15
                if any(np.hypot(*(q - p)) < 1.5 for p in put):
                    continue
                zt = float(ground([q[0]], [q[1]])[0])
                ztop = X[v, 2] - GUTTER_DROP - GUTTER_H
                if ztop - zt < 1.5 or ztop - zt > 30:
                    continue
                sides = boxv(q, np.array([o[1], -o[0]]), (DOWNPIPE / 2, DOWNPIPE / 2), zt - 0.1, ztop)[:8]
                n_out = [k2 for k2 in range(0, 8, 2) if np.dot(np.cross(sides[k2][1] - sides[k2][0],
                                                                   sides[k2][2] - sides[k2][0])[:2], o) > -1e-9]
                add(m, [t for k2 in n_out for t in sides[k2:k2 + 2]])              # not the side against the wall
                put.append(q)
                rep["downpipes"] += 1
    # the roofs of the houses: aerial, dish, solar panels
    for c in np.unique(lab):
        sel = lab == c
        tri = t3[sel]
        foot = shapely.union_all([shapely.Polygon(t[:, :2]) for t in tri if abs(np.cross(t[1, :2] - t[0, :2], t[2, :2] - t[0, :2])) > 1e-6])
        if foot.is_empty or foot.area < 30:
            continue
        hit = gwr.query(foot, predicate="contains")
        if not len(hit):
            continue
        g = gwr.meta[hit[0]]
        if g["gkat"] not in RESIDENTIAL:
            continue
        hkey = f"{g['egid']}"
        rep["houses"] += 1
        V3 = tri.reshape(-1, 3)
        top = V3[np.argmax(V3[:, 2])]
        if (g["gbaup"] or 9999) <= OLD and share(hkey, "aerial", AERIAL_SHARE):
            add("mp_house_metal", aerial(top[:2], top[2]))
            rep["aerials"] += 1
        # roof faces by orientation: planes of similar normals
        n_c = nrm[sel]
        az = np.degrees(np.arctan2(n_c[:, 0], n_c[:, 1])) % 360         # where the face looks
        slope = np.degrees(np.arccos(np.clip(n_c[:, 2], -1, 1)))
        south = (np.abs(az - 180) < PV_AZ) & (slope > 10) & (slope < 50)
        if share(hkey, "dish", DISH_SHARE):
            ix = np.flatnonzero(south) if south.any() else np.arange(len(tri))
            t = tri[ix[np.argmax(area[sel][ix])]]
            cpt = t.mean(0)
            add("mp_house_dish", dish(cpt[:2], cpt[2]))
            rep["dishes"] += 1
        if south.any() and share(hkey, "pv", PV_SHARE):
            # the largest south face plane: its faces with a normal within 3 degrees of the largest one
            ix = np.flatnonzero(south)
            n0 = n_c[ix[np.argmax(area[sel][ix])]]
            plane = ix[np.degrees(np.arccos(np.clip(n_c[ix] @ n0, -1, 1))) < 3]
            pts = tri[plane].reshape(-1, 3)
            o = pts[np.argmin(pts[:, 2])]
            u = np.cross([0, 0, 1.0], n0)
            u /= np.linalg.norm(u)                               # level, along the eave
            v = np.cross(n0, u)                                  # up the slope
            Q = lambda p: np.column_stack([(p - o) @ u, (p - o) @ v])
            poly = shapely.union_all([shapely.Polygon(Q(t)) for t in tri[plane]]).buffer(-PV_INSET, join_style="mitre")
            if poly.is_empty or poly.area < PV_MIN:
                continue
            x0, y0, x1, y1 = poly.bounds
            for _ in range(40):                                  # shrink the box until it lies inside
                r = shapely.box(x0, y0, x1, y1)
                if poly.buffer(1e-6).contains(r):
                    break
                x0, x1, y0, y1 = x0 + 0.15, x1 - 0.15, y0 + 0.1, y1 - 0.1
                if x1 - x0 < 2 or y1 - y0 < 1.7:
                    break
            else:
                continue
            if not poly.buffer(1e-6).contains(shapely.box(x0, y0, x1, y1)) or (x1 - x0) * (y1 - y0) < PV_MIN:
                continue
            lift = n0 * 0.10
            C = [o + u * x + v * y + lift for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            tris = quad(*C)
            uv = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y0], [x1, y1], [x0, y1]]) / np.array([1.0, 1.7])
            out.setdefault("mp_house_pv", []).append((tris, uv))
            rep["pv_m2"] += (x1 - x0) * (y1 - y0)
            rep["pv"] += 1
    return out


class Gwr:
    def __init__(self, path):
        g = json.load(gzip.open(path, "rt", encoding="utf-8"))["buildings"]
        g = [b for b in g if b.get("gstat") == 1004]
        self.meta = g
        self.tree = shapely.STRtree([shapely.Point(b["x"], b["y"]) for b in g])

    def query(self, poly, predicate):
        return self.tree.query(poly, predicate=predicate)


def house_details_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    ground = lambda x, y: pu.terrain_top(q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))
    gwr = Gwr(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "gwr_area.json.gz"))
    rep = {k: 0 for k in ("shapes", "houses", "downpipes", "aerials", "dishes", "pv")}
    rep.update(gutter_m=0.0, pv_m2=0.0)
    near, far = {}, {}
    for o in pl.read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        T = roof_parts(V, parts)
        det = house_details(W, T, ground, gwr, rep)
        rep["shapes"] += 1
        for m, tris in det.items():
            if not tris:
                continue
            if m == "mp_house_pv":
                for tr, uv in tris:
                    c = tr[0].mean(0)
                    k = (int(math.floor(c[0] / PV_TILE)), int(math.floor(c[1] / PV_TILE)))
                    far.setdefault(k, []).append((m, np.array(tr), uv))
            else:
                arr = np.array(tris)
                ks = np.floor(arr.mean(1)[:, :2] / DETAIL_TILE).astype(int)
                for k in {tuple(x) for x in ks}:
                    sel = (ks[:, 0] == k[0]) & (ks[:, 1] == k[1])
                    near.setdefault(k, []).append((m, arr[sel], None))
        if rep["shapes"] % 50 == 0:
            print("%d building shapes, %.0f s" % (rep["shapes"], time.time() - t0), flush=True)
    print("houses %d: gutters %.0f km, %d downpipes, %d aerials, %d dishes, %d roofs with panels (%.0f m2)"
          % (rep["houses"], rep["gutter_m"] / 1000, rep["downpipes"], rep["aerials"], rep["dishes"], rep["pv"],
             rep["pv_m2"]), flush=True)
    new_files, items, ntri = {}, [], 0

    def write(tiles, name, draw, size):
        nonlocal ntri
        for (tx, ty), ps in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * size, (ty + 0.5) * size, 0.0])
            for m, T, uv in ps:
                Vv = T.reshape(-1, 3)
                mb.add(m, Vv, uvs=uv if uv is not None else Vv[:, :2], normals=bng.flat_normals_soup(Vv))
                ntri += len(T)
            allv = np.concatenate([T.reshape(-1, 3) for _, T, _ in ps])
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / draw)))
            rel = f"art/shapes/buildings/details/{name}_{tx:+03d}_{ty:+03d}.dae"
            tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"{name}_{os.getpid()}.dae")
            mb.write_dae(tmp, name=name, origin=origin, detail=detail)
            new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
            os.remove(tmp)
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False)
            ob["__parent"] = "details"
            items.append(ob)
        return len(tiles)
    nt_n = write(near, "house_details", NEAR_DRAW, DETAIL_TILE)
    nt_f = write(far, "house_pv", PV_DRAW, PV_TILE)
    tex = f"/levels/{LEVEL_NAME}/art/shapes/buildings/details/t_pv_b.color.png"
    new_files[f"{lv}/art/shapes/buildings/details/t_pv_b.color.png"] = pv_texture()
    mats = [bng.material("mp_house_zinc", base_color=[0.60, 0.61, 0.60, 1], roughness=0.45, metallic=0.6, double_sided=True),
            bng.material("mp_house_copper", base_color=[0.47, 0.30, 0.20, 1], roughness=0.5, metallic=0.6,
                         double_sided=True),
            bng.material("mp_house_metal", base_color=[0.70, 0.71, 0.72, 1], roughness=0.35, metallic=0.8,
                         double_sided=True),
            bng.material("mp_house_dish", base_color=[0.86, 0.86, 0.84, 1], roughness=0.4, double_sided=True),
            bng.material("mp_house_pv", tex, roughness=0.15, metallic=0.3)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"details_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/buildings/details/details.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    grp = f"{lv}/main/MissionGroup/buildings/items.level.json"
    group = {"name": "details", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "buildings"}
    root = pl.read_items(zi, grp)
    if any(o.get("name") == "details" for o in root):
        raise SystemExit("the level has a buildings/details group already: the v2.8 house details are placed once")
    new_files[grp] = pr.pl_write(root + [group])
    new_files[f"{lv}/main/MissionGroup/buildings/details/items.level.json"] = pr.pl_write(items)
    with zi.writer() as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            ni.external_attr = 0o644 << 16
            zo.writestr(ni, data)
    print("written in %.0f s: %d detail tiles, %d panel tiles, %d triangles" % (time.time() - t0, nt_n, nt_f, ntri),
          flush=True)
    if report:
        rep.update({"gutter_km": round(rep.pop("gutter_m") / 1000, 1),
                    "pv_m2": round(rep["pv_m2"]), "detail_tiles": nt_n, "panel_tiles": nt_f, "triangles": ntri})
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return 0
