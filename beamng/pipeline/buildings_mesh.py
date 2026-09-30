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

TILE = 256.0
V1_DEFAULT = np.array([0.84, 0.80, 0.72])        # plaster tone of v1.x buildings without photos
SHOP_NEAR = 3.0        # m, a shop of OSM this close to a building is in it (the point is often on the street side)


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


def orient(b):
    allp = np.concatenate([b["walls"].reshape(-1, 3), b["roofs"].reshape(-1, 3)])
    ctr = allp.mean(0)
    out = {}
    for part in ("walls", "roofs"):
        t = b[part].copy()
        if len(t):
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            if part == "walls":
                o = t.mean(1) - ctr; o[:, 2] = 0
                flip = (n * o).sum(1) < 0
            else:
                flip = n[:, 2] < 0
            t[flip] = t[flip][:, ::-1]
        out[part] = t
    return out


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
            for sel, pst in groups:
                if not sel.any():
                    continue
                part = rest[sel]
                V = part.reshape(-1, 3)
                if pst["stone"]:
                    stats["stone"] += 1
                    mb.add("bld_stone", V, uvs=wall_uvs(part) / 3.0, normals=bng.flat_normals_soup(V),
                           colors=np.r_[np.clip(0.97 + 0.03 * (pst["tone"] - pst["tone"].mean()), 0, 1), 1.0])
                else:
                    tone = np.clip(pst["tone"] / mean("t_bld_plaster"), 0, 1)
                    mb.add("bld_plaster", V, uvs=wall_uvs(part) / 5.0, normals=bng.flat_normals_soup(V),
                           colors=np.r_[tone, 1.0])
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
        if em.PV:
            V = np.concatenate(em.PV).reshape(-1, 3)
            C = np.repeat(np.array([np.r_[np.clip(c / mean("t_bld_plinth"), 0, 1), 1.0] for c in em.PC]), 6, 0)
            mb.add("bld_plinth", V, uvs=np.concatenate(em.PUV).reshape(-1, 2), normals=bng.flat_normals_soup(V),
                   colors=C)
        em.V, em.UV, em.PV, em.PUV, em.PC = [], [], [], [], []
        if mb.empty():
            continue
        rel = f"art/shapes/buildings/bld_{tx:+03d}_{ty:+03d}.dae"
        mb.write_dae(os.path.join(level_dir, rel), name="bld", origin=origin)
        out.append((f"/levels/{level_name}/{rel}", origin, mb.triangle_count()))
    T = lambda n, k: f"{L}/{n}_{k}"
    mats = [bng.material("bld_plaster", T("t_bld_plaster", "b.color.png"), T("t_bld_plaster", "nm.normal.png"),
                         T("t_bld_plaster", "r.data.png"), vert_color=True),
            bng.material("bld_stone", T("t_bld_stone", "b.color.png"), T("t_bld_stone", "nm.normal.png"),
                         T("t_bld_stone", "r.data.png"), T("t_bld_stone", "ao.data.png"), vert_color=True),
            bng.material("bld_plinth", T("t_bld_plinth", "b.color.png"), T("t_bld_plinth", "nm.normal.png"),
                         T("t_bld_plinth", "r.data.png"), vert_color=True),
            bng.material("bld_openings", T("t_bld_openings", "b.color.png"), T("t_bld_openings", "nm.normal.png"),
                         T("t_bld_openings", "r.data.png"), T("t_bld_openings", "ao.data.png"), alpha_test=110,
                         detail={"opacityMap": T("t_bld_openings", "o.data.png")})]
    for kind in bld_textures.ROOF_TILE:
        n = f"t_roof_{kind}"
        mats.append(bng.material(f"bld_roof_{kind}", T(n, "b.color.png"), T(n, "nm.normal.png"), T(n, "r.data.png"),
                                 vert_color=True, metallic=0.3 if kind == "metal" else None))
    for i, page in enumerate(atlas.pages if n_photo else []):     # no empty page without photo facades
        rel = f"art/shapes/buildings/bld_photo_{i}.jpg"
        cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        mats.append(bng.material(f"mp_bld_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.85))
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
