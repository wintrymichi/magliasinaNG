"""Rows of vines in the vineyards of the cadastral survey (v2.4; v3.0: vines on their wires, two detail levels).

Up to v2.3 the vineyards ('vigna' of the survey) were bare garden grass. Every vineyard within NEAR m of a
road or path gets its rows:
- direction: the orientation of the stripes on the 10 cm orthophoto (structure tensor of the
  brightness in a window of up to WIN m inside the vineyard), measured once (python vineyards.py ->
  dati/vineyard_rows.json, by the middle point of every vineyard); where the stripes are not clear
  (coherence under MIN_COHERENCE) or not measured, along the walls of the survey inside the vineyard
  (terraces, v3.0), else along the contour of the slope;
- spacing SPACING m (the usual distance of the rows; not measured), the rows keep EDGE m from the
  edge of the vineyard, CLEAR m from every road and path, and (v3.0) KEEP_OFF m from the buildings,
  walls, paths and stairs of the survey; no row on ground steeper than MAX_SLOPE degrees.

v3.0: in the game of v2.4-v2.8 every row was one band of quads from 0.45 to 1.7 m: hedges of paper floating
over the ground, drawn as full rectangles (the game ignores the alpha of a colour texture without an
opacityMap: the transparent black texels came out as dark blotches). Now a row is what stands in a
vineyard of the Malcantone in October (Merlot on wires, spur-pruned cordon), on the terrain of the level
(the heights of the terrain block itself, not the 0.5 m DTM: the rows floated up to 0.8 m or sank):
- a leaf wall 0.44 m thick from about 0.95 to 1.9 m: two faces and a top of cut-out cards (drawn leaves,
  vine_textures.py: normal map, a shade per vine, some yellow, rust and red leaves), cards of shoots
  crossing it every CLUMP_GAP m that break its outline, both ends closed; the shade of the leaves
  changes along every row (vertex colours);
- the trunks under it: a card in the plane of the row with six twisted trunks a span, their cordon arms
  on the fruiting wire, shoots, purple bunches, the post at each end of the span (in the texture);
- a strip of bare earth STRIP_W m wide under the row, on the terrain;
- where the camera can come near (rows within FULL_DIST m of a road or path): posts every span (about
  POST_GAP m, chestnut or concrete, the end posts thicker and taller, with their anchor wire) and the
  wires (thin quads). No collision: posts 8 cm thick would only snag the wheels, and at about 85,000
  posts the collision meshes would cost more than the rest of the vineyards together.
The ground under every row is followed within NEAR_TOL m (the profile along the row simplified).
Two detail levels in one shape per CHUNK m square: all this within about D_NEAR m of the shape, beyond
that only the leaf wall as a tent of two faces along a coarser profile (the far detail), nothing beyond
about D_FAR m (the terrain colour shows the vineyards). The detail sizes are those of optimize_level.PIX_K;
the shapes keep them (optimize_level leaves shapes with several detail levels as they are).
The terrain is changed after this stage by some finishing steps (tracks flush with the ground, ...): the
finishing step ground_step moves the rows by the change of the terrain under them.
"""
import json, os
import numpy as np
import shapely
from scipy import ndimage as ndi
import bng
import vine_textures as vt

NEAR = 150.0            # m from a road or path
WIN = 40.0              # m, side of the orthophoto window
MIN_COHERENCE = 0.25
SPACING = 2.2           # m between rows
EDGE = 0.8              # m from the edge of the vineyard
CLEAR = 1.5             # m from a road or path
# m from the objects of the cadastral survey (layer, kind): no row through a house, a wall, a path or stairs
KEEP_OFF = {("LCSF", "edificio"): 1.5, ("SOSF", "altra_parte_di_edificio"): 1.0, ("SOSF", "riparo"): 1.0,
            ("SOSF", "muro"): 0.6, ("SOLI", "muro"): 0.6, ("SOLI", "sentiero"): 1.2,
            ("SOLI", "scala_importante"): 1.0}
MAX_SLOPE = 38.0        # degrees of the terrain (over 3 m) under a row
MIN_ROW = 2.5           # m, shortest piece of a row
# the vines (m)
POST_GAP = 5.5          # m, about: every row is split into equal spans
POST = (0.08, 1.95)     # width, height over the ground of the posts
END_POST = (0.11, 2.05)
POST_FOOT = 0.15        # m into the ground
WIRES = (0.80, 1.45)    # m, the wires drawn as quads: the fruiting wire and a catch wire
WIRE_W = 0.012
ANCHOR = 1.1            # m beyond the end post, where its anchor wire reaches the ground
WALL_INSET = 0.35       # m from the end posts to the ends of the leaf wall
WALL_B = (0.80, 0.22)   # height, half width of the bottom of the faces
WALL_T = (1.90, 0.20)   # and of their top (the side tile is 1.1 m high)
WALL_TOP = (1.88, 0.30) # the top card
CLUMP_GAP = 3.0         # m between the cards of shoots crossing the wall
CLUMP = (0.85, 2.05, 0.8)   # bottom, top, length
BAND_Z = vt.BAND_Z
STRIP_W = vt.STRIP_M[1]
STRIP_LIFT = 0.05
FAR_B = (0.95, 0.24)    # the far tent: height, half width of its feet; its ridge at FAR_R
FAR_R = 1.95
PROFILE_STEP = 1.5      # m, the terrain squares
NEAR_TOL, NEAR_SEG = 0.03, 8.0     # m: the profile of the near detail, its longest piece
FAR_TOL, FAR_SEG = 0.12, 16.0
FULL_DIST = 40.0        # m from a road or path line: posts and wires
CHUNK = 96.0            # m, side of the square of a shape
D_NEAR, D_FAR = 200.0, 1000.0      # m from the centre of a shape: near detail, far detail, nothing
PIX_K = 1000.0          # = optimize_level.PIX_K
SEED = 71
GROUP = "MissionGroup/level_objects/vegetation/vineyards"
LEAF, WOOD = "mp_vine_leaf", "mp_vine_wood"
UP = np.array([0.0, 0.0, 1.0])


def materials(level_name):
    t = f"/levels/{level_name}/art/shapes/vineyards"
    return [bng.material(LEAF, f"{t}/t_vine_leaf_b.color.png", normal_map=f"{t}/t_vine_leaf_nm.normal.png",
                         alpha_test=100, double_sided=True, roughness=0.8, metallic=0.0, vert_color=True,
                         detail={"opacityMap": f"{t}/t_vine_leaf_o.data.png"}),
            bng.material(WOOD, f"{t}/t_vine_wood_b.color.png", alpha_test=100, double_sided=True, roughness=0.9,
                         metallic=0.0, vert_color=True, detail={"opacityMap": f"{t}/t_vine_wood_o.data.png"})]


# ---------------------------------------------------------------------- where the rows are
def row_direction(poly, dtm, ortho_sample):
    """Angle (radians, of the rows) and coherence: the stripes of the orthophoto, else the contour."""
    c = poly.representative_point()
    half = WIN / 2
    res = 0.2
    xs = c.x - half + (np.arange(int(WIN / res)) + 0.5) * res
    ys = c.y + half - (np.arange(int(WIN / res)) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(poly.buffer(-1.0), X, Y)
    coh, ang = 0.0, None
    if inside.mean() > 0.25 and ortho_sample is not None:
        try:
            rgb = ortho_sample(X.ravel(), Y.ravel()).reshape(X.shape + (3,))
        except Exception:
            rgb = None
        if rgb is not None and np.isfinite(rgb).all():
            L = rgb.mean(-1)
            L = np.where(inside, L, np.nanmean(L[inside]))
            gy, gx = np.gradient(ndi.gaussian_filter(L, 1.0))
            gy = -gy                                         # rows go south: y up is minus
            Jxx = ndi.gaussian_filter(gx * gx, 6)[inside].mean()
            Jyy = ndi.gaussian_filter(gy * gy, 6)[inside].mean()
            Jxy = ndi.gaussian_filter(gx * gy, 6)[inside].mean()
            tr = Jxx + Jyy
            if tr > 1e-9:
                coh = float(np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / tr)
                ang = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2   # across the strongest gradient
    if ang is None or coh < MIN_COHERENCE:
        z = dtm.sample(np.array([c.x - 5, c.x + 5, c.x, c.x]), np.array([c.y, c.y, c.y - 5, c.y + 5]))
        sx, sy = (z[1] - z[0]) / 10, (z[3] - z[2]) / 10
        ang = np.arctan2(sy, sx) + np.pi / 2 if np.hypot(sx, sy) > 0.02 else 0.0
    return float(ang), coh


def wall_direction(poly, walls):
    """Mean direction (radians, length weighted, modulo pi) of the survey's wall lines inside a vineyard
    (its terraces), None if they are less than 15 m."""
    if walls is None:
        return None
    tree, geoms = walls
    segs = []
    for i in tree.query(poly, predicate="intersects"):
        g = geoms[i].intersection(poly)
        for part in shapely.get_parts(g):
            if part.geom_type == "LineString":
                P = np.asarray(part.coords)[:, :2]
                segs.append(np.diff(P, axis=0))
    if not segs:
        return None
    D = np.concatenate(segs)
    w = np.hypot(D[:, 0], D[:, 1])
    if w.sum() < 15.0:
        return None
    a2 = 2 * np.arctan2(D[:, 1], D[:, 0])
    return float(0.5 * np.arctan2((w * np.sin(a2)).sum(), (w * np.cos(a2)).sum()))


def rows(poly, ang, avoid):
    """Row lines of a vineyard polygon (clipped to its inside, off the roads)."""
    inner = poly.buffer(-EDGE)
    if avoid is not None and not avoid.is_empty:
        inner = inner.difference(avoid)
    if inner.is_empty:
        return []
    d = np.array([np.cos(ang), np.sin(ang)])
    n = np.array([-d[1], d[0]])
    c = np.array(inner.centroid.coords[0])
    P = np.asarray(inner.exterior.coords) if inner.geom_type == "Polygon" else shapely.get_coordinates(inner)
    t = (P - c) @ n
    s = (P - c) @ d
    out = []
    L = s.max() - s.min() + 10
    for k in np.arange(np.floor(t.min() / SPACING), np.ceil(t.max() / SPACING) + 1):
        o = c + n * k * SPACING
        line = shapely.LineString([o + d * (s.min() - 5), o + d * (s.min() - 5 + L)])
        cut = line.intersection(inner)
        for g in shapely.get_parts(cut):
            if g.geom_type == "LineString" and g.length > 2.0:
                out.append(g)
    return out


def flat_enough(line, ground):
    """Pieces (start, end) of a straight row (A, B) on ground no steeper than MAX_SLOPE."""
    A, B = np.asarray(line.coords[0])[:2], np.asarray(line.coords[-1])[:2]
    L = float(np.hypot(*(B - A)))
    s = np.linspace(0, L, max(2, int(np.ceil(L / PROFILE_STEP)) + 1))
    P = A + (B - A) * (s / L)[:, None]
    e = 1.5
    gx = (ground(P[:, 0] + e, P[:, 1]) - ground(P[:, 0] - e, P[:, 1])) / (2 * e)
    gy = (ground(P[:, 0], P[:, 1] + e) - ground(P[:, 0], P[:, 1] - e)) / (2 * e)
    ok = np.degrees(np.arctan(np.hypot(gx, gy))) <= MAX_SLOPE
    out = []
    k = 0
    while k < len(s):
        if not ok[k]:
            k += 1
            continue
        j = k
        while j + 1 < len(s) and ok[j + 1]:
            j += 1
        a = 0.0 if k == 0 else 0.5 * (s[k - 1] + s[k])
        b = L if j == len(s) - 1 else 0.5 * (s[j] + s[j + 1])
        if b - a >= MIN_ROW:
            out.append((A + (B - A) * a / L, A + (B - A) * b / L))
        k = j + 1
    return out, L


DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
ROWS = os.path.join(DATI, "vineyard_rows.json")


def vineyards(av, net_lines):
    """The vineyard polygons within NEAR m of the network (net_lines: (n, 2) points of its lines)."""
    from scipy.spatial import cKDTree
    import area
    keep = area.polygon()
    kd = cKDTree(net_lines)
    polys = []
    for g, _ in av["LCSF"].get("vigna", []):
        if not g.intersects(keep) or g.area < 150:
            continue
        for p in shapely.get_parts(g.intersection(keep)):
            if p.geom_type != "Polygon" or p.area < 150:
                continue
            if kd.query(shapely.get_coordinates(p.exterior))[0].min() <= NEAR:
                polys.append(p)
    return polys


def survey_obstacles(av, polys):
    """STRtree and buffered geometries of the survey's objects (KEEP_OFF) near the vineyards."""
    region = shapely.union_all([p.envelope for p in polys]).buffer(5.0) if polys else None
    geoms = []
    for (layer, kind), buf in KEEP_OFF.items():
        for g, _ in av.get(layer, {}).get(kind, []):
            if region is not None and g.intersects(region):
                geoms.append(g.buffer(buf))
    return shapely.STRtree(geoms), geoms


def survey_walls(av):
    g = [g for g, _ in av.get("SOLI", {}).get("muro", [])]
    return (shapely.STRtree(g), g) if g else None


def measure():
    """Row directions on the orthophoto -> dati/vineyard_rows.json [[x, y, angle, coherence], ...]."""
    import pickle
    import network
    import ortho10
    from geo import Grid
    from config import WORK
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    _, st, _ = network.load()
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    out = []
    polys = vineyards(av, np.column_stack([st["x"], st["y"]]))
    for k, p in enumerate(polys):
        ang, coh = row_direction(p, dtm, ortho10.sample)
        c = p.representative_point()
        out.append([round(c.x, 2), round(c.y, 2), round(ang, 4), round(coh, 3)])
        if k % 50 == 0:
            print("  %d/%d" % (k + 1, len(polys)), flush=True)
    json.dump({"source": "SWISSIMAGE 10 cm (stripes only, no image)", "rows": out}, open(ROWS, "w"),
              separators=(",", ":"))
    print("vineyards measured", len(out), "clear stripes", sum(r[3] >= MIN_COHERENCE for r in out))


# ---------------------------------------------------------------------- the ground
def terrain_sampler(H=None):
    """(x, y) -> height of the terrain block (bilinear between its vertices); H: its heights (TER_SIZE
    squared, row 0 south) or None for work/terrain_heights.npy, as stage_terrain left it."""
    from config import TER_X0, TER_Y0, TER_SQUARE, WORK
    if H is None:
        H = np.load(os.path.join(WORK, "terrain_heights.npy"), mmap_mode="r")
    return grid_sampler(H, TER_X0, TER_Y0, TER_SQUARE)


def grid_sampler(H, x0, y0, sq):
    n0, n1 = H.shape

    def fn(x, y):
        c = np.clip((np.asarray(x, np.float64) - x0) / sq, 0, n1 - 1.001)
        r = np.clip((np.asarray(y, np.float64) - y0) / sq, 0, n0 - 1.001)
        c0, r0 = np.floor(c).astype(np.int64), np.floor(r).astype(np.int64)
        fc, fr = c - c0, r - r0
        return (H[r0, c0] * (1 - fc) * (1 - fr) + H[r0, c0 + 1] * fc * (1 - fr) + H[r0 + 1, c0] * (1 - fc) * fr
                + H[r0 + 1, c0 + 1] * fc * fr).astype(np.float64)
    return fn


def simplify(s, z, tol, longest):
    """Indices of the points of a profile (s, z) kept: none of the others more than tol from the line
    between its neighbours kept, no piece longer than `longest`."""
    keep = {0, len(s) - 1}
    stack = [(0, len(s) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        t = (s[i + 1:j] - s[i]) / max(s[j] - s[i], 1e-9)
        dev = np.abs(z[i + 1:j] - (z[i] + (z[j] - z[i]) * t))
        k = int(np.argmax(dev))
        if dev[k] > tol:
            m = i + 1 + k
        elif s[j] - s[i] > longest:
            m = (i + j) // 2
        else:
            continue
        keep.add(m)
        stack += [(i, m), (m, j)]
    return np.array(sorted(keep))


# ---------------------------------------------------------------------- the vines
class Quads:
    """Quads (corners counter-clockwise) by detail level and material: corners (n, 4, 3), texture
    coordinates (n, 4, 2), normals (n, 4, 3), colours (n, 4, 4)."""

    def __init__(self):
        self.q = {}

    def add(self, lod, mat, P, UV, N, C=None):
        P = np.asarray(P, np.float64).reshape(-1, 4, 3)
        n = len(P)
        if not n:
            return
        UV = np.broadcast_to(np.asarray(UV, np.float64), (n, 4, 2))
        N = np.broadcast_to(np.asarray(N, np.float64), (n, 4, 3))
        C = np.ones((n, 4, 4)) if C is None else np.broadcast_to(np.asarray(C, np.float64), (n, 4, 4))
        self.q.setdefault((lod, mat), []).append((P, UV, N, C))

    def items(self):
        for k, v in self.q.items():
            yield k, [np.concatenate(a) for a in zip(*v)]


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def strip_quads(P0, P1, U0, U1, V0, V1):
    """Quads between two polylines (k, 3): (P0[i], P0[i+1], P1[i+1], P1[i]) with texture coordinates u along
    the lines (U0, U1: (k,)), v = V0 on the first, V1 on the second."""
    P = np.stack([P0[:-1], P0[1:], P1[1:], P1[:-1]], 1)
    UV = np.stack([np.column_stack([U0[:-1], np.full(len(P), V0)]), np.column_stack([U0[1:], np.full(len(P), V0)]),
                   np.column_stack([U1[1:], np.full(len(P), V1)]), np.column_stack([U1[:-1], np.full(len(P), V1)])], 1)
    return P, UV


def per_corner(a):
    """Per-point values (k, m) of a polyline as per-corner values of its strip quads (k-1, 4, m)."""
    a = np.asarray(a, np.float64)
    return np.stack([a[:-1], a[1:], a[1:], a[:-1]], 1)


def row_vines(q, A, B, ground, rng, full_of, post_kind):
    """The quads of one row from A to B (x, y): near detail (lod 0) and far detail (lod 1).
    full_of(points (k, 2)) -> bool (k,): spans whose middle is near a road or path get posts and wires."""
    A, B = np.asarray(A, np.float64), np.asarray(B, np.float64)
    L = float(np.hypot(*(B - A)))
    d = (B - A) / L
    n = np.array([-d[1], d[0]])
    d3, n3 = np.array([d[0], d[1], 0.0]), np.array([n[0], n[1], 0.0])
    s = np.linspace(0, L, max(2, int(np.ceil(L / PROFILE_STEP)) + 1))
    z = ground(A[0] + d[0] * s, A[1] + d[1] * s)
    at = lambda ss: np.column_stack([A[0] + d[0] * ss, A[1] + d[1] * ss, np.interp(ss, s, z)])
    near = s[simplify(s, z, NEAR_TOL, NEAR_SEG)]
    far = s[simplify(s, z, FAR_TOL, FAR_SEG)]
    spans = max(1, int(round(L / POST_GAP)))
    span = L / spans
    # the leaf wall between the insets, the shade of the leaves changing along the row
    w0, w1 = (WALL_INSET, L - WALL_INSET) if L > 2 * WALL_INSET + 0.6 else (0.25 * L, 0.75 * L)
    sw = np.concatenate([[w0], near[(near > w0) & (near < w1)], [w1]])
    W = at(sw)
    base = np.array([1.0, 1.0, 1.0]) + rng.normal(0, 0.035) * np.array([1.0, 0.4, -1.2])
    walk = np.cumsum(rng.normal(0, 0.03, (len(sw), 1)), 0)
    tint = np.clip(base[None] * (1 + walk * np.array([[1.0, 0.35, -0.9]])) * rng.uniform(0.94, 1.04, (len(sw), 1)),
                   0.75, 1.2)
    col = np.column_stack([tint, np.ones(len(sw))])
    ph = rng.uniform(0, 1, 4)
    sv0, sv1 = vt.region_v(vt.LEAF_REGIONS, "side")
    for sgn, k in ((1, 0), (-1, 1)):
        bot = W + sgn * n3 * WALL_B[1] + UP * WALL_B[0]
        top = W + sgn * n3 * WALL_T[1] + UP * WALL_T[0]
        u = sgn * sw / vt.SIDE_M[0] + ph[k]
        P, UV = strip_quads(bot, top, u, u, sv0, sv1)
        q.add(0, LEAF, P, UV, unit(sgn * n3 * 0.6 + UP * 0.8), per_corner(col))
    tv0, tv1 = vt.region_v(vt.LEAF_REGIONS, "top")
    u = sw / vt.TOP_M[0] + ph[2]
    P, UV = strip_quads(W - n3 * WALL_TOP[1] + UP * WALL_TOP[0], W + n3 * WALL_TOP[1] + UP * WALL_TOP[0], u, u, tv0, tv1)
    q.add(0, LEAF, P, UV, UP, per_corner(col) * np.array([1.06, 1.06, 1.0, 1.0]))
    # the ends of the wall: a card across the row
    for i, sgn in ((0, -1), (-1, 1)):
        c = W[i]
        ua = rng.uniform(0, 0.8)
        P = [c - n3 * WALL_B[1] + UP * WALL_B[0], c + n3 * WALL_B[1] + UP * WALL_B[0],
             c + n3 * WALL_T[1] + UP * WALL_T[0], c - n3 * WALL_T[1] + UP * WALL_T[0]]
        UV = [(ua, sv0), (ua + 0.22, sv0), (ua + 0.22, sv1), (ua, sv1)]
        q.add(0, LEAF, P, UV, unit(sgn * d3 * 0.6 + UP * 0.8), col[i])
    # cards of shoots crossing the wall
    nc = max(1, int((w1 - w0) / CLUMP_GAP))
    sc = w0 + (np.arange(nc) + 0.5) * (w1 - w0) / nc + rng.uniform(-0.3, 0.3, nc) * min(CLUMP_GAP, (w1 - w0) / nc)
    cv0, cv1 = vt.region_v(vt.LEAF_REGIONS, "clump")
    for k, sk in enumerate(sc):
        c = at([sk])[0]
        a = np.radians(rng.uniform(30, 55)) * (1 if k % 2 else -1)
        e = d3 * np.cos(a) + n3 * np.sin(a)
        h = 0.5 * CLUMP[2] * rng.uniform(0.85, 1.15)
        top = CLUMP[1] + rng.uniform(-0.1, 0.05)
        v = rng.integers(4)
        u0, u1 = v / 4 + 0.01, (v + 1) / 4 - 0.01
        P = [c - e * h + UP * CLUMP[0], c + e * h + UP * CLUMP[0], c + e * h + UP * top, c - e * h + UP * top]
        nrm = unit(np.cross(e, UP) * 0.7 + UP * 0.7)
        cc = np.append(np.clip(np.interp(sk, sw, tint[:, 0]) * rng.uniform(0.92, 1.08) * np.array([1, 1, 1]), 0.7, 1.2), 1)
        q.add(0, LEAF, P, [(u0, cv0), (u1, cv0), (u1, cv1), (u0, cv1)], nrm, cc)
    # the trunks: a card in the plane of the row, one span a tile (its post at u = 0)
    R = at(near)
    bv0, bv1 = vt.region_v(vt.WOOD_REGIONS, "band")
    u = near / span
    P, UV = strip_quads(R + UP * BAND_Z[0], R + UP * BAND_Z[1], u, u, bv0, bv1)
    q.add(0, WOOD, P, UV, unit(n3 * 0.8 + UP * 0.6))
    # the bare earth under the row, on the terrain on both edges
    gv0, gv1 = vt.region_v(vt.WOOD_REGIONS, "strip")
    E = []
    for sgn in (-1, 1):
        xy = R[:, :2] + sgn * n * STRIP_W / 2
        E.append(np.column_stack([xy, ground(xy[:, 0], xy[:, 1]) + STRIP_LIFT]))
    u = near / vt.STRIP_M[0] + ph[3]
    P, UV = strip_quads(E[0], E[1], u, u, gv0, gv1)
    q.add(0, WOOD, P, UV, UP)
    # posts and wires where the camera can come near
    sp = np.arange(spans + 1) * span
    mids = at((np.arange(spans) + 0.5) * span)[:, :2]
    full = np.asarray(full_of(mids), bool)
    nfull = int(full.sum())
    if nfull:
        has_post = np.zeros(spans + 1, bool)
        has_post[:-1] |= full
        has_post[1:] |= full
        Pp = at(sp)
        ov0, ov1 = vt.region_v(vt.WOOD_REGIONS, "solid")
        su0, su1 = vt.SOLID_U[post_kind]
        for j in np.flatnonzero(has_post):
            end = j in (0, spans)
            wdt, hgt = END_POST if end else POST
            c = Pp[j]
            r = wdt / 2
            corners = [c + (-d3 - n3) * r, c + (d3 - n3) * r, c + (d3 + n3) * r, c + (-d3 + n3) * r]
            for f in range(4):
                a, b = corners[f], corners[(f + 1) % 4]
                out = unit(a + b - 2 * c)
                fu0 = su0 + (su1 - su0) * f / 4
                fu1 = fu0 + (su1 - su0) / 4
                P = [a - UP * POST_FOOT, b - UP * POST_FOOT, b + UP * hgt, a + UP * hgt]
                vt_ = ov0 + (ov1 - ov0) * min(1.0, (hgt + POST_FOOT) / 2.2)
                q.add(0, WOOD, P, [(fu0, ov0), (fu1, ov0), (fu1, vt_), (fu0, vt_)], out)
        steel = ((vt.SOLID_U["steel"][0] + 0.05, ov0 + 0.02), (vt.SOLID_U["steel"][1] - 0.05, ov1 - 0.02))
        wuv = [steel[0], (steel[1][0], steel[0][1]), steel[1], (steel[0][0], steel[1][1])]
        wn = unit(n3 + UP)
        for j in np.flatnonzero(full):
            for h in WIRES:
                a, b = Pp[j] + UP * h, Pp[j + 1] + UP * h
                P = [a - wn * WIRE_W / 2, b - wn * WIRE_W / 2, b + wn * WIRE_W / 2, a + wn * WIRE_W / 2]
                q.add(0, WOOD, P, wuv, UP)
        for j, sgn in ((0, -1), (spans, 1)):              # anchor wires of the end posts
            if (j == 0 and full[0]) or (j == spans and full[-1]):
                top = Pp[j] + UP * (END_POST[1] - 0.1)
                fxy = Pp[j, :2] + sgn * d * ANCHOR
                foot = np.array([fxy[0], fxy[1], float(ground(fxy[0:1], fxy[1:2])[0]) - 0.05])
                P = [top - n3 * WIRE_W / 2, foot - n3 * WIRE_W / 2, foot + n3 * WIRE_W / 2, top + n3 * WIRE_W / 2]
                q.add(0, WOOD, P, wuv, UP)
    # far detail: the leaf wall as a tent along a coarser profile
    sf = np.concatenate([[w0], far[(far > w0) & (far < w1)], [w1]])
    F = at(sf)
    fv0, fv1 = vt.region_v(vt.LEAF_REGIONS, "far")
    for sgn in (1, -1):
        u = sgn * sf / vt.FAR_M[0] + ph[0]
        P, UV = strip_quads(F + sgn * n3 * FAR_B[1] + UP * FAR_B[0], F + UP * FAR_R, u, u, fv0, fv1)
        q.add(1, LEAF, P, UV, unit(sgn * n3 * 0.5 + UP * 0.87),
              per_corner(np.column_stack([np.interp(sf, sw, tint[:, i]) for i in range(3)] + [np.ones(len(sf))])))
    return {"spans": spans, "full_spans": nfull, "posts": int(nfull and has_post.sum()), "length": L}


# ---------------------------------------------------------------------- the shapes
def chunks(q):
    """{(tx, ty): Quads} of the quads of q by the CHUNK square of their centres."""
    out = {}
    for (lod, mat), (P, UV, N, C) in q.items():
        key = np.floor(P.mean(1)[:, :2] / CHUNK).astype(np.int64)
        u, inv = np.unique(key, axis=0, return_inverse=True)
        inv = inv.ravel()
        for i, k in enumerate(map(tuple, u)):
            m = inv == i
            out.setdefault(k, Quads()).add(lod, mat, P[m], UV[m], N[m], C[m])
    return out


def builders(q, origin):
    """(near MeshBuilder, far MeshBuilder) of the quads of one shape."""
    mbs = (bng.MeshBuilder(), bng.MeshBuilder())
    tri = np.array([[0, 1, 2], [0, 2, 3]])
    for (lod, mat), (P, UV, N, C) in q.items():
        k = len(P)
        T = (np.arange(k)[:, None, None] * 4 + tri[None]).reshape(-1, 3)
        mbs[lod].add(mat, P.reshape(-1, 3), uvs=UV.reshape(-1, 2), normals=N.reshape(-1, 3), tris=T,
                     colors=C.reshape(-1, 4))
    return mbs


def detail_sizes(radius):
    """Pixel sizes of the near and far detail of a shape of that radius (m)."""
    near = max(3, int(round(radius * PIX_K / D_NEAR)))
    far = min(near - 1, max(1, int(round(radius * PIX_K / D_FAR))))
    return near, far


def write_shapes(level_dir, level_name, scene, q, group=GROUP):
    """The shapes (art/shapes/vineyards/vines_<tx>_<ty>.dae) and their items; returns statistics."""
    st = {"chunks": 0, "triangles_near": 0, "triangles_far": 0, "vertices": 0, "detail_near": [], "detail_far": []}
    for (tx, ty), cq in sorted(chunks(q).items()):
        allp = np.concatenate([P.reshape(-1, 3) for (lod, _), (P, _, _, _) in cq.items() if lod == 0] or
                              [P.reshape(-1, 3) for _, (P, _, _, _) in cq.items()])
        lo, hi = allp.min(0), allp.max(0)
        origin = np.round(0.5 * (lo + hi), 2)             # the game measures the distance from the shape's place
        radius = 0.5 * float(np.linalg.norm(hi - lo))
        dn, df = detail_sizes(radius)
        near, far = builders(cq, origin)
        rel = f"art/shapes/vineyards/vines_{tx:+03d}_{ty:+03d}.dae"
        st["triangles_near"] += near.triangle_count()
        st["triangles_far"] += far.triangle_count()
        near.write_dae(os.path.join(level_dir, rel), name="vines", origin=origin, detail=dn,
                       lods=[(df, far)] if not far.empty() else None)
        st["vertices"] += sum(p[4] for p in near.parts.values()) + sum(p[4] for p in far.parts.values())
        st["chunks"] += 1
        st["detail_near"].append(dn)
        st["detail_far"].append(df)
        scene.add(group, bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=False))
    for k in ("detail_near", "detail_far"):
        v = st.pop(k)
        st[k] = [int(min(v)), int(max(v))] if v else []
    return st


def build(level_dir, level_name, scene, av, net_lines, drivable, group=GROUP, ground=None):
    """Rows of every vineyard near a road or path; returns statistics. ground: (x, y) -> terrain height
    (default: terrain_sampler(), the terrain block as stage_terrain wrote it)."""
    from geo import Grid
    from config import WORK
    from scipy.spatial import cKDTree
    if ground is None:
        if os.path.exists(os.path.join(WORK, "terrain_heights.npy")):
            ground = terrain_sampler()
        else:
            dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
            ground = lambda x, y: dtm.sample(np.asarray(x), np.asarray(y))
    meas = json.load(open(ROWS))["rows"] if os.path.exists(ROWS) else []
    mk = cKDTree(np.array([[r[0], r[1]] for r in meas])) if meas else None
    polys = vineyards(av, net_lines)
    polys.sort(key=lambda p: (round(p.representative_point().x, 1), round(p.representative_point().y, 1)))
    dtree = shapely.STRtree(drivable) if drivable else None
    otree, ogeoms = survey_obstacles(av, polys)
    walls = survey_walls(av)
    kd_net = cKDTree(net_lines)
    full_of = lambda P: kd_net.query(P)[0] <= FULL_DIST
    d = os.path.join(level_dir, "art", "shapes", "vineyards")
    os.makedirs(d, exist_ok=True)
    vt.build(d, POST_GAP)
    bng.write_materials(os.path.join(d, "vineyards.materials.json"), materials(level_name))
    q = Quads()
    stats = {"vineyards": 0, "rows": 0, "rows_km": 0.0, "from_photo": 0, "from_walls": 0, "steep_km": 0.0,
             "full_km": 0.0, "posts": 0}
    for k, p in enumerate(polys):
        rng = np.random.default_rng(SEED + k)
        c = p.representative_point()
        ang, coh = None, 0.0
        if mk is not None:
            dd, j = mk.query([c.x, c.y])
            if dd < 0.5:
                ang, coh = meas[j][2], meas[j][3]
        src = "photo"
        if ang is None or coh < MIN_COHERENCE:
            wa = wall_direction(p, walls)
            if wa is not None:
                ang, src = wa, "walls"
            else:
                zc = ground(np.array([c.x - 5, c.x + 5, c.x, c.x]), np.array([c.y, c.y, c.y - 5, c.y + 5]))
                sx, sy = (zc[1] - zc[0]) / 10, (zc[3] - zc[2]) / 10
                ang = float(np.arctan2(sy, sx) + np.pi / 2) if np.hypot(sx, sy) > 0.02 else 0.0
                src = "contour"
        avoid = []
        if dtree is not None:
            avoid += [drivable[i].buffer(CLEAR) for i in dtree.query(p.buffer(CLEAR), predicate="intersects")]
        avoid += [ogeoms[i] for i in otree.query(p, predicate="intersects")]
        lines = rows(p, ang, shapely.union_all(avoid) if avoid else None)
        post_kind = "concrete" if rng.uniform() < 0.35 else "wood"
        n_rows = 0
        for line in lines:
            pieces, L = flat_enough(line, ground)
            kept = 0.0
            for A, B in pieces:
                r = row_vines(q, A, B, ground, rng, full_of, post_kind)
                kept += r["length"]
                n_rows += 1
                stats["rows_km"] += r["length"] / 1000
                stats["full_km"] += r["full_spans"] * r["length"] / r["spans"] / 1000
                stats["posts"] += r["posts"]
            stats["steep_km"] += (L - kept) / 1000
        if not n_rows:
            continue
        stats["vineyards"] += 1
        stats["rows"] += n_rows
        stats["from_photo"] += int(src == "photo")
        stats["from_walls"] += int(src == "walls")
    stats.update(write_shapes(level_dir, level_name, scene, q, group))
    for k in ("rows_km", "steep_km", "full_km"):
        stats[k] = round(stats[k], 1)
    stats["triangles"] = stats["triangles_near"] + stats["triangles_far"]
    return stats


# --------------------------------------------------------------------------------------------------
# The rows on the terrain of the finished level (v3.0), a finishing step of build_level.py (FINISH, after
# every step that changes the terrain): every vertex of the vineyard shapes moves up or down by the change
# of the terrain under it since stage_terrain (work/terrain_heights.npy, what build() put the rows on).
#   alone: python build_level.py --finish vineyards_ground
# --------------------------------------------------------------------------------------------------
import re

_POS = re.compile(r'(<float_array id="(g\d*)-pa" count="\d+">)([^<]*)(</float_array>)')


def level_terrain(zi, lv):
    """(x, y) -> height of the level's terrain block as it is now."""
    import struct
    blk = [json.loads(l) for l in zi.read(f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
           .decode("utf-8").splitlines() if l.strip()]
    blk = [o for o in blk if o.get("class") == "TerrainBlock"][0]
    path = zi.path(f"{lv}/theTerrain.ter")
    with open(path, "rb") as f:
        n = struct.unpack("<I", f.read(5)[1:5])[0]
    q = np.memmap(path, "<u2", "r", offset=5, shape=(n, n))
    H = blk["position"][2] + np.asarray(q, np.float32) / 65535.0 * float(blk["maxHeight"])
    return grid_sampler(H, blk["position"][0], blk["position"][1], float(blk.get("squareSize", 1.0)))


def reseat(text, pos, delta):
    """The DAE text with every position array moved by delta(x, y) (world), and the largest move."""
    moved = [0.0]

    def fix(m):
        V = np.array(m.group(3).split(), np.float64).reshape(-1, 3)
        dz = delta(V[:, 0] + pos[0], V[:, 1] + pos[1])
        if np.abs(dz).max() < 0.01:
            return m.group(0)
        moved[0] = max(moved[0], float(np.abs(dz).max()))
        V[:, 2] += dz
        return m.group(1) + " ".join(f"{v:.3f}".rstrip("0").rstrip(".") for v in V.ravel()) + m.group(4)
    return _POS.sub(fix, text), moved[0]


def ground_step(root, report=None):
    from config import LEVEL_NAME, WORK
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    built_f = os.path.join(WORK, "terrain_heights.npy")
    items_f = f"{lv}/main/{GROUP}/items.level.json"
    out = {"shapes": 0, "moved": 0, "max_move_m": 0.0}
    if not os.path.exists(built_f) or items_f not in zi.NameToInfo:
        print("vineyards: no rows or no terrain of the build, nothing to do")
        return out
    built = terrain_sampler(np.load(built_f, mmap_mode="r"))
    now = level_terrain(zi, lv)
    delta = lambda x, y: now(x, y) - built(x, y)
    pos = {}
    for l in zi.read(items_f).decode("utf-8").splitlines():
        if l.strip():
            o = json.loads(l)
            if o.get("class") == "TSStatic":
                pos[o["shapeName"].lstrip("/")] = np.asarray(o["position"], np.float64)
    with zi.writer() as zo:
        for i in zi.infolist():
            data = zi.read(i)
            if i.filename in pos:
                text, mv = reseat(data.decode("utf-8"), pos[i.filename], delta)
                out["shapes"] += 1
                if mv > 0:
                    out["moved"] += 1
                    out["max_move_m"] = round(max(out["max_move_m"], mv), 3)
                data = text.encode("utf-8")
            zo.writestr(i, data)
    print("vineyards on the terrain:", out)
    if report:
        json.dump(out, open(report, "w"), indent=1)
    return out


if __name__ == "__main__":
    measure()
