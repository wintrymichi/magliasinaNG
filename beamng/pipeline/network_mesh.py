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
AV_CLASSES = {"strada_sentiero": "road", "marciapiede": "sidewalk", "spartitraffico": "island",
              "altro_rivestimento_duro": "hard"}


class Network:
    """Stations with their heights, and the drivable polygons with the lines they belong to."""

    def __init__(self, exclude=None):
        self.segs, st, _ = network.load()
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
        self._build_polygons(exclude)

    # ------------------------------------------------------------------ polygons
    def _build_polygons(self, exclude):
        segs = self.segs
        keep = area.polygon().buffer(network.CLIP)
        # bridge decks (bridges.py, as wide as the deck; survey polygons 1 m wider, so no sliver of
        # them is left beside a deck without a line to take its height from) and the corridor stay out
        import bridges
        decks, decks_av, node_decks = [], [], {}
        for s in segs:
            if not s["bridge"]:
                continue
            L = shapely.LineString(np.column_stack([self.x[s["first"]:s["first"] + s["n"]],
                                                    self.y[s["first"]:s["first"] + s["n"]]]))
            hw = bridges.half_width({"width": self.w}, s)
            for nd in s["nodes"]:
                node_decks.setdefault(nd, []).append(len(decks))
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
            # the decks of the bridges it leads onto, not the ones that pass over it
            adj = sorted({i for nd in s["nodes"] for i in node_decks.get(nd, [])})
            for hole in [decks[i] for i in adj] + ([ex_geom] if not ex_geom.is_empty else []):
                if strip.intersects(hole):
                    strip = strip.difference(hole)
            strip = strip.intersection(keep)
            own = {s["id"]} | node_segs.get(s["nodes"][0], set()) | node_segs.get(s["nodes"][1], set())
            for p in shapely.get_parts(strip):
                if p.geom_type == "Polygon" and p.area >= 0.5:
                    self.polys.append({"geom": p, "cls": "strip_" + s["kind"], "surface": s["surface"], "segs": own})
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
    def heights(self, X, Y, P, with_seg=False):
        """Heights at points (X, Y) inside polygons P (index into self.polys); NaN where no line
        of the polygon is near (squares, car parks). with_seg: also the line that gave each height
        (-1 for none).
        Every line near a point gives the height of its surface there: the point projected on the
        line (between two stations, linear), plus the cross slope times the offset; beyond the end
        of a line it carries on along the end's grade. The line nearest the point (relative to its
        half width) wins; lines that agree with it within BLEND_DZ are blended (junctions)."""
        n = len(X)
        out = np.full(n, np.nan)
        segs_out = np.full(n, -1, np.int64)
        if n == 0:
            return (out, segs_out) if with_seg else out
        X = np.asarray(X, np.float64)
        Y = np.asarray(Y, np.float64)
        k = 12
        _, j = self.tree.query(np.column_stack([X, Y]), k=k, distance_upper_bound=12.0 + REACH)
        valid = j < len(self.x)
        jj = np.where(valid, j, 0)
        seg = self.seg[jj]
        ok = valid & np.asarray(self.assoc[np.repeat(P, k), seg.ravel()]).reshape(n, k)
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
        ok &= np.isfinite(h) & (np.abs(off) <= hw + REACH)
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
        return (out, segs_out) if with_seg else out

    def strip_height(self, pid):
        """Height function of a strip polygon: its lines' surface (nearest station where the
        blend finds none)."""
        def fn(x, y, *_):
            x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64))
            z = self.heights(x, y, np.full(len(x), pid))
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
        owner = features.rasterize([(self.polys[i]["geom"], int(i)) for i in ids], out_shape=(H, W), transform=tr,
                                   fill=-1, dtype=np.int32)
        m = owner >= 0
        if not m.any():
            return None, ids
        rr, cc = np.nonzero(m)
        X = x0 + (cc + 0.5) * RES
        Y = y1 - (rr + 0.5) * RES
        Z = np.full((H, W), np.nan)
        G = np.full((H, W), -1, np.int64)                   # line that gave the height
        Z[rr, cc], G[rr, cc] = self.heights(X, Y, owner[rr, cc], with_seg=True)
        # squares and car parks: smoothed DTM, corrected to meet the roads around
        hole = m & np.isnan(Z)
        if hole.any():
            sub, _, _ = dtm.window(x0, y0, x1, y1, pad=0)
            Ds = ndi.gaussian_filter(np.asarray(sub.a, np.float64), 4.0)
            Ds = pad_to(Ds, H, W)
            Z = harmonic_fill(Z, m, Ds)
        # neighbouring cells of a polygon are one surface when their heights come from the same line
        # (continuous however steep the line: stairs, mule tracks) or agree within STEP_Z (junctions,
        # squares); a step (a wall) is left between lines at different heights
        LR, LD = surface_fit.link_same(owner, m)
        same_r = (G[:, :-1] == G[:, 1:]) & (G[:, :-1] >= 0)
        same_d = (G[:-1, :] == G[1:, :]) & (G[:-1, :] >= 0)
        LR[:, :-1] &= same_r | (np.abs(Z[:, :-1] - Z[:, 1:]) < STEP_Z)
        LD[:-1, :] &= same_d | (np.abs(Z[:-1, :] - Z[1:, :]) < STEP_Z)
        return surface_fit.Surface(owner, np.nan_to_num(Z), LR, LD, x0, y1, RES), ids


def pad_to(a, H, W):
    out = np.full((H, W), np.nan)
    h, w = min(H, a.shape[0]), min(W, a.shape[1])
    out[:h, :w] = a[:h, :w]
    return np.where(np.isnan(out), np.nanmean(a), out)


def harmonic_fill(Z, m, D):
    """Fill the NaN cells of Z inside m: D plus the harmonic interpolation of Z - D from the known
    cells (4-neighbour Laplace over m)."""
    unk = m & np.isnan(Z)
    known = m & ~np.isnan(Z)
    R = np.where(known, Z - D, 0.0)
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
    ("hard", "hard"): ("mp_hard_asphalt", 4.0, 1.25),
    ("strip_road", "hard"): ("mp_road_asphalt", 3.0, 1.25), ("strip_road", "natural"): ("mp_road_gravel", 3.0, 2.0),
    ("strip_path", "hard"): ("mp_path_paved", 2.0, 1.25), ("strip_path", "natural"): ("mp_path_dirt", 2.0, 2.0),
}


def tiles():
    """South-west corners of the TILE m tiles over the network (multiples of TILE)."""
    x0, y0, x1, y1 = area.bounds(network.CLIP + 5)
    return [(tx * TILE, ty * TILE) for tx in range(int(np.floor(x0 / TILE)), int(np.floor(x1 / TILE)) + 1)
            for ty in range(int(np.floor(y0 / TILE)), int(np.floor(y1 / TILE)) + 1)]


def mesh_tile(net, dtm, X0, Y0, xs, ys, on_mesh, on_carve):
    """Meshes of the chunks of one tile -> on_mesh(tx, ty, material, uv tile, V, T, S, ground);
    terrain carve of its vertices -> on_carve(rows, cols, z)."""
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
    sub.a = ndi.gaussian_filter(np.asarray(sub.a, np.float32), 0.6)
    ground = lambda x, y: sub.sample(x, y)
    n_tri = 0
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
                        on_mesh(cx, cy, mat, uvt, V, T, S, ground)
                        n_tri += len(T)
                    continue
                zf = (lambda pid_: (lambda x, y, comp: S.height(x, y, pid=pid_, comp=int(comp))))(int(pid))
                kf_all = (lambda pid_: (lambda x, y: S.surfaces_at_polygon(x, y, pid_)))(int(pid))
                for part, comp in road_mesh.split_by_surface(piece, S, int(pid)):
                    kf = kf_all if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                    for comp_, V, T in road_mesh.mesh_polygon_surfaces(part, zf, kf, cell=cell):
                        if len(T) and np.isfinite(V[:, 2]).all():
                            on_mesh(cx, cy, mat, uvt, V, T, S, ground)
                            n_tri += len(T)
    # terrain carve: vertices under the meshes drop 0.1 m under the lowest surface nearby
    c0 = int(np.searchsorted(xs, X0)); c1 = int(np.searchsorted(xs, X1))
    r0 = int(np.searchsorted(ys, Y0)); r1 = int(np.searchsorted(ys, Y1))
    if c1 > c0 and r1 > r0:
        sq = xs[1] - xs[0]
        tr = Affine(sq, 0, xs[c0] - 0.5 * sq, 0, sq, ys[r0] - 0.5 * sq)          # row 0 = south
        ring = [(dx * sq, dy * sq) for dx, dy in road_mesh.CARVE_RING]
        survey = [i for i in ids if not net.polys[i]["cls"].startswith("strip")]
        strips = [i for i in ids if net.polys[i]["cls"].startswith("strip")]
        if survey:
            mask = features.rasterize([(net.polys[i]["geom"].buffer(0.35), 1) for i in survey], out_shape=(r1 - r0, c1 - c0),
                                      transform=tr, fill=0, dtype=np.uint8, all_touched=True).astype(bool)
            rr, cc = np.nonzero(mask)
            if len(rr):
                Xv, Yv = xs[c0 + cc], ys[r0 + rr]
                zc = S.height(Xv, Yv)
                for dx, dy in ring:                     # NaN off the surface: no vote
                    zc = np.fmin(zc, S.height(Xv + dx, Yv + dy))
                ok = np.isfinite(zc)
                on_carve(r0 + rr[ok], c0 + cc[ok], zc[ok] - 0.10)
        if strips:
            sid = features.rasterize([(net.polys[i]["geom"].buffer(0.35), int(i)) for i in strips], out_shape=(r1 - r0, c1 - c0),
                                     transform=tr, fill=-1, dtype=np.int32, all_touched=True)
            rr, cc = np.nonzero(sid >= 0)
            for pid in np.unique(sid[rr, cc]):
                k = sid[rr, cc] == pid
                Xv, Yv = xs[c0 + cc[k]], ys[r0 + rr[k]]
                fz = net.strip_height(int(pid))
                zc = fz(Xv, Yv)
                for dx, dy in ring:
                    zc = np.fmin(zc, fz(Xv + dx, Yv + dy))
                ok = np.isfinite(zc)
                on_carve(r0 + rr[k][ok], c0 + cc[k][ok], zc[ok] - 0.10)
    return n_tri
