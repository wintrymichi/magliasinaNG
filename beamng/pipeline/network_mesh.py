"""Drivable meshes of the whole road and path network (v2.0), on the heights of network_surface.py.

Drivable polygons (away from the Strada Cantonale corridor, which keeps the v1.1 meshes):
- the surveyed carriageways, sidewalks, islands (MU 'strada_sentiero', 'marciapiede',
  'spartitraffico') and the hard surfaces that touch them near the network ('altro_rivestimento_duro':
  yards, car parks, squares);
- a strip of the line's width along every swissTLM3D line outside those (forest roads, farm
  tracks, paths, mule tracks, stairs), asphalt or gravel after the line's surface;
- not the bridges: their decks are meshed by bridges.py.
Heights, per 0.5 m cell of a tile: every polygon belongs to the lines that run in it (a strip to
its own line and the lines at its ends); a cell takes the height of those lines at its projection
on them (linear between stations) and across the cross slope, blended between lines that agree
within BLEND_DZ (junctions); where they disagree (two roads at different levels, a wall between)
the nearest line wins and a step remains. Cells far from any line (squares, car parks) get the
smoothed DTM corrected harmonically to meet the roads around them.
The cells of a tile make a surface_fit.Surface, so the meshing, the skirts and stone faces at the
steps and the terrain carve are the ones of v1.1 (road_mesh.py). Tiles of TILE m (whole 128 m
chunks) with MARGIN m of context.
"""
import os, pickle
import numpy as np
import shapely
import scipy.sparse as sp
from scipy import ndimage as ndi
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from rasterio import features
from rasterio.transform import Affine
from config import WORK
from geo import Grid
import area
import network
import network_surface
import surface_fit

TILE = 512.0
MARGIN = 24.0
RES = 0.5
CHUNK = 128.0
STEP_Z = 0.30          # m, neighbouring cells further apart: a step (wall)
BLEND_DZ = 0.40        # m, lines whose heights at a cell agree within this are blended
REACH = 6.0            # m beyond its half width a station still gives heights (junction corners)
NEAR_NET = 25.0        # m, hard surfaces (yards, car parks) farther from any line are left out
FILL_OFF = 2.0         # m, largest offset of a square or car park from the smoothed ground
OFF_LINE = 1.5         # half widths from its line: beyond, a cell far from the ground keeps to the ground
FILLED = -2            # line code of the cells of squares and car parks (harmonic fill)
SUNK = 0.75            # m, deepest a survey surface may lie under the lowest bare ground within 1 m
AV_CLASSES = {"strada_sentiero": "road", "marciapiede": "sidewalk", "spartitraffico": "island",
              "altro_rivestimento_duro": "hard"}


class Network:
    """Stations with their heights, and the drivable polygons with the lines they belong to."""

    def __init__(self, exclude=None):
        self.segs, st, node_pos = network.load()
        self.node_xy = np.asarray(node_pos, np.float64)
        ns = network_surface.load()
        self.x, self.y, self.w = st["x"], st["y"], st["width"]
        self.z_tlm = st["z_tlm"]
        self.seg = st["seg"]
        self.z, self.g, self.c = ns["z"], ns["g"], ns["c"]
        self.nx, self.ny = ns["nx"], ns["ny"]
        self.tree = cKDTree(np.column_stack([self.x, self.y]))
        self.bridge = np.array([s["bridge"] for s in self.segs])
        self.polys = []                       # dicts: geom, cls, surface, segs
        self.deck_tops = []                   # bridge deck top triangles (bridges.py)
        self.deck_feet = []                   # (kind, footprint) of every deck built (bridges.py)
        self._build_polygons(exclude)

    # ------------------------------------------------------------------ polygons
    def _build_polygons(self, exclude):
        segs = self.segs
        keep = area.polygon().buffer(network.CLIP)
        # bridge decks (bridges.py, as wide as the deck; survey polygons 1 m wider, so no sliver of
        # them is left beside a deck without a line to take its height from) and the corridor stay out
        import bridges
        decks, decks_av, node_decks, deck_hw = [], [], {}, []
        for s in segs:
            if not s["bridge"]:
                continue
            L = shapely.LineString(np.column_stack([self.x[s["first"]:s["first"] + s["n"]],
                                                    self.y[s["first"]:s["first"] + s["n"]]]))
            hw = bridges.half_width({"width": self.w}, s)
            for nd in s["nodes"]:
                node_decks.setdefault(nd, []).append(len(decks))
            deck_hw.append(hw)
            decks.append(L.buffer(hw, cap_style="flat"))
            decks_av.append(L.buffer(hw + 1.0, cap_style="flat"))
        ex = [exclude] if exclude is not None else []
        holes_av = shapely.union_all(decks_av + ex) if decks_av or ex else shapely.Polygon()
        ex_geom = shapely.union_all(ex) if ex else shapely.Polygon()
        shapely.prepare(ex_geom)
        # lines as strips (for the association and the parts without survey)
        lines = []
        for s in segs:
            a, n = s["first"], s["n"]
            lines.append(shapely.LineString(np.column_stack([self.x[a:a + n], self.y[a:a + n]])))
        ltree = shapely.STRtree(lines)
        av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
        road_like = []
        for cls, kind in AV_CLASSES.items():
            for g, _ in av["LCSF"].get(cls, []):
                if not g.intersects(keep):
                    continue
                g = g.intersection(keep)
                if kind == "hard" and ltree.query(g, predicate="dwithin", distance=NEAR_NET).size == 0:
                    continue
                g = g.difference(holes_av) if not holes_av.is_empty and g.intersects(holes_av) else g
                for p in shapely.get_parts(g):
                    if p.geom_type == "Polygon" and p.area >= 0.5:
                        road_like.append((p, kind))
        av_tree = shapely.STRtree([p for p, _ in road_like]) if road_like else None
        for p, kind in road_like:
            near = ltree.query(p, predicate="dwithin", distance=1.0)
            self.polys.append({"geom": p, "cls": kind, "surface": "hard", "segs": set(int(i) for i in near)})
        # strips of the lines outside the survey
        node_segs = {}
        for s in segs:
            for nd in s["nodes"]:
                node_segs.setdefault(nd, set()).add(s["id"])
        for s, L in zip(segs, lines):
            if s["bridge"]:
                continue
            a, n = s["first"], s["n"]
            hw = 0.5 * float(np.median(self.w[a:a + n]))
            strip = L.buffer(hw, cap_style="round", quad_segs=4)
            if av_tree is not None:
                near = av_tree.query(strip, predicate="intersects")
                if len(near):
                    strip = strip.difference(shapely.union_all([road_like[i][0] for i in near]))
            # the decks of the bridges it leads onto, where the two overlap at the junction only (a
            # path that starts on a bridge and goes down under it keeps its way under), not the
            # decks that pass over it
            holes = []
            for nd in s["nodes"]:
                for i in node_decks.get(nd, []):
                    near_node = shapely.Point(self.node_xy[nd]).buffer(deck_hw[i] + hw + 0.5)
                    holes.append(decks[i].intersection(near_node))
            for hole in holes + ([ex_geom] if not ex_geom.is_empty else []):
                if not hole.is_empty and strip.intersects(hole):
                    strip = strip.difference(hole)
            strip = strip.intersection(keep)
            own = {s["id"]} | node_segs.get(s["nodes"][0], set()) | node_segs.get(s["nodes"][1], set())
            for p in shapely.get_parts(strip):
                if p.geom_type == "Polygon" and p.area >= 0.5:
                    self.polys.append({"geom": p, "cls": "strip_" + s["kind"], "surface": s["surface"], "segs": own,
                                       "own": s["id"]})
        # polygons of the lines of the survey polygons must not be blended with bridges' lines
        for p in self.polys:
            p["segs"] = {k for k in p["segs"] if not segs[k]["bridge"]}
        self.ptree = shapely.STRtree([p["geom"] for p in self.polys])
        n_seg = len(segs)
        rows = np.concatenate([np.full(len(p["segs"]), i) for i, p in enumerate(self.polys)]) if self.polys else []
        cols = np.concatenate([np.array(sorted(p["segs"]), int) for p in self.polys]) if self.polys else []
        self.assoc = sp.csr_matrix((np.ones(len(rows), bool), (rows, cols)), shape=(len(self.polys), n_seg))
        area_by = {}
        for p in self.polys:
            area_by[p["cls"]] = area_by.get(p["cls"], 0) + p["geom"].area / 1e4
        print("drivable polygons %d, ha %s" % (len(self.polys), {k: round(v, 1) for k, v in area_by.items()}), flush=True)

    # ------------------------------------------------------------------ heights
    def heights(self, X, Y, P, with_seg=False, own=None, with_u=False):
        """Heights at points (X, Y) inside polygons P (index into self.polys); NaN where no line
        of the polygon is near (squares, car parks). with_seg: also the line that gave each height
        (-1 for none).
        Every line near a point gives the height of its surface there: the point projected on the
        line (between two stations, linear), plus the cross slope times the offset; beyond the end
        of a line it carries on along the end's grade. The line nearest the point (relative to its
        half width) wins; lines that agree with it within BLEND_DZ are blended (junctions).
        own: only this line (a strip along its line: a path beside a higher road keeps its own
        height up to its edges). with_u: also the distance of each point from the winning line in
        half widths (0 on the axis, 1 at the edge of its carriageway) and how far past the end of
        that line the point lies (m, 0 alongside it).
        A line gives heights only within REACH m of its carriageway, measured as the true distance:
        the offset across the line alone would let a point far ahead of a bend, or far beyond the
        end, take the height of a line it is nowhere near (a square beside a steep path)."""
        n = len(X)
        out = np.full(n, np.nan)
        segs_out = np.full(n, -1, np.int64)
        u_out = np.full(n, np.inf)
        e_out = np.zeros(n)
        if n == 0:
            return (out, segs_out, u_out, e_out) if with_u else ((out, segs_out) if with_seg else out)
        X = np.asarray(X, np.float64)
        Y = np.asarray(Y, np.float64)
        k = 12
        _, j = self.tree.query(np.column_stack([X, Y]), k=k, distance_upper_bound=12.0 + REACH)
        valid = j < len(self.x)
        jj = np.where(valid, j, 0)
        seg = self.seg[jj]
        ok = valid & np.asarray(self.assoc[np.repeat(P, k), seg.ravel()]).reshape(n, k)
        if own is not None:
            ok &= seg == own
        N = len(self.x)
        Xb, Yb = X[:, None], Y[:, None]
        best_d = np.full((n, k), np.inf)
        h = np.full((n, k), np.nan)
        off = np.zeros((n, k))
        ext = np.zeros((n, k))
        hw = np.ones((n, k))
        for da, db in ((-1, 0), (0, 1)):
            a = np.clip(jj + da, 0, N - 1)
            b = np.clip(jj + db, 0, N - 1)
            good = ok & (self.seg[a] == seg) & (self.seg[b] == seg) & (a != b)
            vx, vy = self.x[b] - self.x[a], self.y[b] - self.y[a]
            L2 = np.maximum(vx * vx + vy * vy, 1e-9)
            s_raw = ((Xb - self.x[a]) * vx + (Yb - self.y[a]) * vy) / L2
            s = np.clip(s_raw, 0.0, 1.0)
            qx, qy = self.x[a] + s * vx, self.y[a] + s * vy
            nx = self.nx[a] + s * (self.nx[b] - self.nx[a])
            ny = self.ny[a] + s * (self.ny[b] - self.ny[a])
            nn = np.maximum(np.hypot(nx, ny), 1e-9)
            nx, ny = nx / nn, ny / nn
            t = (Xb - qx) * nx + (Yb - qy) * ny
            along = (Xb - qx) * ny - (Yb - qy) * nx            # tangent (Ny, -Nx)
            # past the first / last station of the line: carry on along its grade
            a_first = (a == 0) | (self.seg[np.clip(a - 1, 0, N - 1)] != seg)
            b_last = (b == N - 1) | (self.seg[np.clip(b + 1, 0, N - 1)] != seg)
            before, after = (s_raw < 0) & a_first, (s_raw > 1) & b_last
            e = np.where(before | after, along, 0.0)
            ge = np.where(s_raw < 0, self.g[a], self.g[b])
            z = self.z[a] + s * (self.z[b] - self.z[a]) + (self.c[a] + s * (self.c[b] - self.c[a])) * t + ge * e
            d = np.hypot(Xb - qx, Yb - qy)
            # a clamp at a middle station: the neighbouring piece has the same point, let it win
            d = np.where(((s_raw < 0) & ~a_first) | ((s_raw > 1) & ~b_last), d + 1e-3, d)
            take = good & (d < best_d)
            best_d = np.where(take, d, best_d)
            h = np.where(take, z, h)
            off = np.where(take, t, off)
            ext = np.where(take, e, ext)
            hw = np.where(take, 0.5 * (self.w[a] + s * (self.w[b] - self.w[a])), hw)
        ok &= np.isfinite(h) & (np.abs(off) <= hw + REACH) & (best_d <= hw + REACH)
        # one entry per line and point (neighbouring stations of a line give the same projection)
        order = np.argsort(np.where(ok, best_d, np.inf), axis=1)
        seg_o = np.take_along_axis(seg, order, 1)
        ok_o = np.take_along_axis(ok, order, 1)
        dup = np.zeros((n, k), bool)
        for c in range(1, k):
            dup[:, c] = (seg_o[:, :c] == seg_o[:, c:c + 1]).any(1)
        ok_o &= ~dup
        h_o = np.take_along_axis(h, order, 1)
        u = np.abs(np.take_along_axis(off, order, 1)) / np.maximum(np.take_along_axis(hw, order, 1), 0.3)
        e_o = np.abs(np.take_along_axis(ext, order, 1))
        score = np.where(ok_o, u + 0.05 * e_o, np.inf)
        best = np.argmin(score, axis=1)
        has = ok_o.any(1)
        zb = h_o[np.arange(n), best]
        wt = np.where(ok_o, np.exp(-2.0 * u ** 2) / (1.0 + e_o), 0.0)
        wt = np.where(np.abs(np.nan_to_num(h_o) - zb[:, None]) <= BLEND_DZ, wt, 0.0)
        wt[np.arange(n), best] = np.where(has, np.maximum(wt[np.arange(n), best], 1e-12), 0.0)
        ws = wt.sum(1)
        good = has & (ws > 0)
        out[good] = (wt * np.nan_to_num(h_o)).sum(1)[good] / ws[good]
        segs_out[good] = seg_o[np.arange(n), best][good]
        u_out[good] = u[np.arange(n), best][good]
        e_out[good] = e_o[np.arange(n), best][good]
        if with_u:
            return out, segs_out, u_out, e_out
        return (out, segs_out) if with_seg else out

    def strip_height(self, pid):
        """Height function of a strip polygon: the surface of its own line (nearest station of its
        lines where that finds none)."""
        own = self.polys[pid].get("own")

        def fn(x, y, *_):
            x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64))
            z = self.heights(x, y, np.full(len(x), pid), own=own)
            bad = np.isnan(z)
            if bad.any():
                segs = np.array(sorted(self.polys[pid]["segs"]), int)
                _, j = self.tree.query(np.column_stack([x[bad], y[bad]]), k=8)
                j = np.minimum(j, len(self.x) - 1)
                allowed = np.isin(self.seg[j], segs)
                first = np.where(allowed.any(1), allowed.argmax(1), 0)
                z[bad] = self.z[j[np.arange(len(j)), first]]
            return z
        return fn

    # ------------------------------------------------------------------ tiles
    def tile_surface(self, x0, y0, x1, y1, dtm):
        """surface_fit.Surface of the drivable cells of the window, and the polygon indices in it."""
        box = shapely.box(x0, y0, x1, y1)
        ids = self.ptree.query(box, predicate="intersects")
        ids = np.array([i for i in ids if not self.polys[i]["cls"].startswith("strip")], int)
        W, H = int(round((x1 - x0) / RES)), int(round((y1 - y0) / RES))
        if len(ids) == 0:
            return None, ids
        tr = Affine(RES, 0, x0, 0, -RES, y1)
        shapes = [(self.polys[i]["geom"], int(i)) for i in ids]
        owner = features.rasterize(shapes, out_shape=(H, W), transform=tr, fill=-1, dtype=np.int32)
        # a thin polygon at an angle is a chain of cells touching only at their corners: the cells
        # it merely touches join it (where no other polygon has them), so its cells are linked
        touched = features.rasterize(shapes, out_shape=(H, W), transform=tr, fill=-1, dtype=np.int32,
                                     all_touched=True)
        free = (owner < 0) & (touched >= 0)
        owner[free] = touched[free]
        m = owner >= 0
        if not m.any():
            return None, ids
        rr, cc = np.nonzero(m)
        X = x0 + (cc + 0.5) * RES
        Y = y1 - (rr + 0.5) * RES
        Z = np.full((H, W), np.nan)
        G = np.full((H, W), -1, np.int64)                   # line that gave the height
        U = np.full((H, W), np.inf)
        E = np.zeros((H, W))
        Z[rr, cc], G[rr, cc], U[rr, cc], E[rr, cc] = self.heights(X, Y, owner[rr, cc], with_seg=True, with_u=True)
        # the smoothed DTM on the cells of the window (sampled: the window may reach past the edge
        # of the DTM raster, near the corners of the area)
        Xc = x0 + (np.arange(W) + 0.5) * RES
        Yc = y1 - (np.arange(H) + 0.5) * RES
        Ds = dtm.sample(np.tile(Xc, H), np.repeat(Yc, W)).reshape(H, W).astype(np.float64)
        if np.isnan(Ds).any():
            Ds = np.where(np.isnan(Ds), np.nanmean(Ds), Ds)
        Dlo = ndi.minimum_filter(Ds, size=5) - SUNK             # lowest bare ground within 1 m
        Ds = ndi.gaussian_filter(Ds, 4.0)
        # a survey polygon reaching beyond the carriageway of its line onto ground far above or
        # below it (a terrace, a yard behind a wall), or past the end of its line where the line's
        # grade carried on leaves the ground: that part keeps to the ground
        off = m & ((U > OFF_LINE) | (E > 1.0)) & (np.abs(Z - Ds) > FILL_OFF)
        Z[off] = np.nan
        G[off] = -1
        # squares and car parks: smoothed DTM, corrected to meet the roads around
        hole = m & np.isnan(Z)
        if hole.any():
            Z = harmonic_fill(Z, m, Ds)
            G[hole] = FILLED                  # one smooth field: its cells are one surface however steep
        # no paved surface under the ground: a cell given a height far below the bare ground (a line
        # of the polygon that runs lower, a hairpin's lower leg, the fill pulled down by it) comes up
        # to SUNK under it, as a surface of its own with a step to the rest
        low = m & (Z < Dlo)
        Z[low] = Dlo[low]
        G[low] = FILLED
        # neighbouring cells of a polygon are one surface when their heights come from the same line
        # (continuous however steep the line: stairs, mule tracks) or agree within STEP_Z (junctions,
        # squares); a step (a wall) is left between lines at different heights
        LR, LD = surface_fit.link_same(owner, m)
        same_r = (G[:, :-1] == G[:, 1:]) & (G[:, :-1] != -1)
        same_d = (G[:-1, :] == G[1:, :]) & (G[:-1, :] != -1)
        LR[:, :-1] &= same_r | (np.abs(Z[:, :-1] - Z[:, 1:]) < STEP_Z)
        LD[:-1, :] &= same_d | (np.abs(Z[:-1, :] - Z[1:, :]) < STEP_Z)
        return surface_fit.Surface(owner, np.nan_to_num(Z), LR, LD, x0, y1, RES), ids


def harmonic_fill(Z, m, D):
    """Fill the NaN cells of Z inside m: D plus the harmonic interpolation of Z - D from the known
    cells (4-neighbour Laplace over m)."""
    unk = m & np.isnan(Z)
    known = m & ~np.isnan(Z)
    # at most FILL_OFF m off the smoothed ground: a yard beside a road in a deep cutting stays on
    # the ground with a step (a wall) to the road, not in a pit
    R = np.where(known, np.clip(Z - D, -FILL_OFF, FILL_OFF), 0.0)
    idx = -np.ones(Z.shape, np.int64)
    ur, uc = np.nonzero(unk)
    idx[ur, uc] = np.arange(len(ur))
    rows, cols, vals = [], [], []
    b = np.zeros(len(ur))
    diag = np.zeros(len(ur))
    H, W = Z.shape
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        r2, c2 = ur + dr, uc + dc
        ok = (r2 >= 0) & (r2 < H) & (c2 >= 0) & (c2 < W)
        r2c, c2c = np.clip(r2, 0, H - 1), np.clip(c2, 0, W - 1)
        inm = ok & m[r2c, c2c]
        diag += inm
        nb_unk = inm & unk[r2c, c2c]
        rows.append(np.flatnonzero(nb_unk)); cols.append(idx[r2c, c2c][nb_unk]); vals.append(-np.ones(nb_unk.sum()))
        nb_kn = inm & known[r2c, c2c]
        b[nb_kn] += R[r2c, c2c][nb_kn]
    diag = np.maximum(diag, 1) + 1e-6
    A = sp.csr_matrix((np.concatenate(vals + [diag]), (np.concatenate(rows + [np.arange(len(ur))]),
                                                        np.concatenate(cols + [np.arange(len(ur))]))),
                      shape=(len(ur), len(ur)))
    r = spsolve(A.tocsc(), b) if len(ur) else np.zeros(0)
    out = Z.copy()
    out[ur, uc] = D[ur, uc] + r
    return out


# ---------------------------------------------------------------------- meshes and carve
# (class, surface) -> (material, mesh cell m, uv tile m)
MATERIAL = {
    ("road", "hard"): ("mp_road_asphalt", 3.0, 1.25), ("road", "natural"): ("mp_road_asphalt", 3.0, 1.25),
    ("sidewalk", "hard"): ("mp_sidewalk", 2.0, 1.25), ("island", "hard"): ("mp_island", 2.0, 2.5),
    ("hard", "hard"): ("mp_hard_asphalt", 2.0, 1.25),      # yards on steep ground: 2 m follows them
    ("strip_road", "hard"): ("mp_road_asphalt", 3.0, 1.25), ("strip_road", "natural"): ("mp_road_gravel", 3.0, 2.0),
    ("strip_path", "hard"): ("mp_path_paved", 2.0, 1.25), ("strip_path", "natural"): ("mp_path_dirt", 2.0, 2.0),
}


def tiles():
    """South-west corners of the TILE m tiles over the network (multiples of TILE)."""
    x0, y0, x1, y1 = area.bounds(network.CLIP + 5)
    return [(tx * TILE, ty * TILE) for tx in range(int(np.floor(x0 / TILE)), int(np.floor(x1 / TILE)) + 1)
            for ty in range(int(np.floor(y0 / TILE)), int(np.floor(y1 / TILE)) + 1)]


def mesh_tile(net, dtm, X0, Y0, xs, ys, on_mesh, on_tops):
    """Meshes of the chunks of one tile -> on_mesh(tx, ty, material, uv tile, V, T, S, ground);
    their top faces -> on_tops(tx, ty, triangles) (for carve_tile, once every tile is meshed)."""
    import road_mesh
    X1, Y1 = X0 + TILE, Y0 + TILE
    core = shapely.box(X0, Y0, X1, Y1)
    ids = net.ptree.query(core, predicate="intersects")
    if len(ids) == 0:
        return 0
    S, _ = net.tile_surface(X0 - MARGIN, Y0 - MARGIN, X1 + MARGIN, Y1 + MARGIN, dtm)
    if S is None:                    # only strips here: an empty surface for the skirts
        own = -np.ones((4, 4), np.int32)
        S = surface_fit.Surface(own, np.zeros((4, 4)), np.zeros((4, 4), bool), np.zeros((4, 4), bool),
                                X0 - MARGIN, Y0 - MARGIN + 2.0, RES)
    sub, _, _ = dtm.window(X0 - MARGIN, Y0 - MARGIN, X1 + MARGIN, Y1 + MARGIN, pad=4)
    lo = Grid(ndi.minimum_filter(np.asarray(sub.a, np.float32), size=5) - SUNK, sub.x_min, sub.y_max, sub.res)
    sub.a = ndi.gaussian_filter(np.asarray(sub.a, np.float32), 0.6)
    ground = lambda x, y: sub.sample(x, y)
    n_tri = 0

    def emit(cx, cy, mat, uvt, V, T):
        on_mesh(cx, cy, mat, uvt, V, T, S, ground)
        tri = V[T]
        nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        on_tops(cx, cy, tri[nrm[:, 2] / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12) > 0.5])
    for cx in range(int(round(X0 / CHUNK)), int(round(X1 / CHUNK))):
        for cy in range(int(round(Y0 / CHUNK)), int(round(Y1 / CHUNK))):
            cbox = shapely.box(cx * CHUNK, cy * CHUNK, (cx + 1) * CHUNK, (cy + 1) * CHUNK)
            for pid in net.ptree.query(cbox, predicate="intersects"):
                p = net.polys[pid]
                piece = road_mesh.polygonal(p["geom"].intersection(cbox))
                if piece.is_empty or piece.area < 0.05:
                    continue
                mat, cell, uvt = MATERIAL[(p["cls"], p["surface"])]
                if p["cls"].startswith("strip"):             # on its line, no raster
                    V, T = road_mesh.mesh_polygon(piece, net.strip_height(int(pid)), cell=cell)
                    if len(T) and np.isfinite(V[:, 2]).all():
                        emit(cx, cy, mat, uvt, V, T)
                        n_tri += len(T)
                    continue
                # the vertices too: no deeper than SUNK under the bare ground (an edge extrapolated
                # from far cells of its surface)
                zf = (lambda pid_: (lambda x, y, comp: np.maximum(S.height(x, y, pid=pid_, comp=int(comp)),
                                                                  lo.sample(x, y))))(int(pid))
                kf_all = (lambda pid_: (lambda x, y: S.surfaces_at_polygon(x, y, pid_)))(int(pid))
                for part, comp in road_mesh.split_by_surface(piece, S, int(pid)):
                    kf = kf_all if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                    for comp_, V, T in road_mesh.mesh_polygon_surfaces(part, zf, kf, cell=cell):
                        if len(T) and np.isfinite(V[:, 2]).all():
                            emit(cx, cy, mat, uvt, V, T)
                            n_tri += len(T)
    return n_tri


def carve_tile(net, X0, Y0, xs, ys, surf, on_carve):
    """Terrain carve of one tile: every vertex whose terrain triangles reach a network mesh drops
    0.1 m under the lowest top face within one terrain step of it (road_mesh.carve_window; surf:
    road_mesh.TriSurface of the meshes as built, those of the neighbouring tiles too), so the terrain
    stays under every face, between its vertices too -> on_carve(rows, cols, z)."""
    import road_mesh
    X1, Y1 = X0 + TILE, Y0 + TILE
    ids = net.ptree.query(shapely.box(X0, Y0, X1, Y1), predicate="intersects")
    c0 = int(np.searchsorted(xs, X0)); c1 = int(np.searchsorted(xs, X1))
    r0 = int(np.searchsorted(ys, Y0)); r1 = int(np.searchsorted(ys, Y1))
    if len(ids) == 0 or c1 <= c0 or r1 <= r0:
        return
    sq = xs[1] - xs[0]
    tr = Affine(sq, 0, xs[c0] - 0.5 * sq, 0, sq, ys[r0] - 0.5 * sq)          # row 0 = south
    # the vertices within one step (in x and in y) of a mesh: their triangles can reach over it
    mask = features.rasterize([(net.polys[i]["geom"].buffer(sq), 1) for i in ids], out_shape=(r1 - r0, c1 - c0),
                              transform=tr, fill=0, dtype=np.uint8, all_touched=True).astype(bool)
    rr, cc = np.nonzero(mask)
    if not len(rr):
        return
    zc = road_mesh.carve_window(surf, xs, ys, r0 + rr, c0 + cc)
    ok = np.isfinite(zc)
    on_carve(r0 + rr[ok], c0 + cc[ok], zc[ok] - 0.10)
