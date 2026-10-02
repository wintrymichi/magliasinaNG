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
within BLEND_DZ; where they disagree (two roads at different levels, a wall between) the nearest
line wins and a step remains. v2.2: lines that meet at a node near the cell are one junction and
always blend (fading out between JUNCTION_R0 and JUNCTION_R1 m from the node), so a side road does
not end in a step against the road it joins. Cells far from any line (squares, car parks) get the
smoothed DTM corrected harmonically to meet the roads around them. v2.2: neighbouring cells of
different polygons (carriageway, sidewalk, yard) are one surface where their heights agree, and
where the height passes from one line to another, from a polygon to the next or to a filled
square, the cells within SEAM_R m of the seam are relaxed (Laplace over the linked cells), so the
passage is a ramp and not a kerb a car hits.
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
JUNCTION_R0 = 8.0      # m from the node where two lines meet: within, they blend whatever their heights
JUNCTION_R1 = 16.0     # m ... fading out up to here
SEAM_R = 4.0           # m around a seam between the heights of two lines or two polygons: relaxed
SEAM_DZ = 0.01         # m, a smaller difference between the heights of two lines or polygons is no seam
JUNCTION_BLEND = False # lines meeting at a node blend whatever their heights (JUNCTION_R0/R1)
JUNCTION_DZ = 1.0      # m, the cells of two lines meeting at a node within JUNCTION_R0 m are one surface up to this
MAIN_CLASSES = ("Autobahn", "Autostrasse", "10m Strasse", "8m Strasse", "6m Strasse")
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
        self.n0 = np.array([sg["nodes"][0] for sg in self.segs], np.int64)     # end nodes of every line
        self.n1 = np.array([sg["nodes"][-1] for sg in self.segs], np.int64)
        self.tree = cKDTree(np.column_stack([self.x, self.y]))
        self.bridge = np.array([s["bridge"] for s in self.segs])
        self.main = np.array([s["kind"] == "road" and s["class"] in MAIN_CLASSES for s in self.segs])
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

    def assign_surfaces(self):
        """v2.4: the surface of every polygon (osm_surface.py): the lines' strips that of their line,
        the survey roads that of the lines and OSM ways in them (in parts where they differ), the
        yards and squares that of the OSM areas over them; sidewalks and islands stay paved.
        p["surface"] is the main one, p["zones"] the parts [(surface, geometry)] where there are several."""
        import osm_surface
        self.line_cat, st = osm_surface.line_categories(self)
        area_by = {}
        for p in self.polys:
            zones = None
            if p["cls"].startswith("strip"):
                p["surface"] = self.line_cat[p["own"]]
            elif p["cls"] == "road":
                zones = osm_surface.polygon_zones(self, p, self.line_cat)
            elif p["cls"] == "hard":
                zones = osm_surface.area_zones(p)
            if zones is not None:
                p["surface"] = zones[-1][0]
                if len(zones) > 1:
                    p["zones"] = zones
            for c, g in p.get("zones") or [(p["surface"], p["geom"])]:
                area_by[(p["cls"], c)] = area_by.get((p["cls"], c), 0.0) + g.area / 1e4
        st["ha"] = {f"{k[0]}:{k[1]}": round(v, 2) for k, v in sorted(area_by.items())}
        st["polygons_in_parts"] = sum(1 for p in self.polys if "zones" in p)
        print("surfaces (OSM, swissTLM3D):", st, flush=True)
        return st

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
        # lines meeting the winning line at a node near the point: one junction, blended whatever their
        # heights (fading out from JUNCTION_R0 to JUNCTION_R1 m from the node); the others only where they
        # agree with it within BLEND_DZ (a road passing above or below)
        sw = seg_o[np.arange(n), best]
        a0, a1 = self.n0[sw][:, None], self.n1[sw][:, None]
        b0, b1 = self.n0[seg_o], self.n1[seg_o]
        shared = np.where((a0 == b0) | (a0 == b1), a0, np.where((a1 == b0) | (a1 == b1), a1, -1))
        sn = np.maximum(shared, 0)
        dn = np.where(shared >= 0, np.hypot(Xb - self.node_xy[sn, 0], Yb - self.node_xy[sn, 1]), np.inf)
        fj = np.clip((JUNCTION_R1 - dn) / (JUNCTION_R1 - JUNCTION_R0), 0.0, 1.0)
        agree = np.abs(np.nan_to_num(h_o) - zb[:, None]) <= BLEND_DZ
        wt = wt * np.where(agree, 1.0, fj if JUNCTION_BLEND else 0.0)
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

    def _junction_links(self, Ga, Gb, xs, ys):
        """Pairs of neighbouring cells (lines Ga, Gb) whose lines meet at a node within JUNCTION_R0 m of the
        pair (xs: x of the pairs' columns, ys: y of their rows)."""
        out = np.zeros(Ga.shape, bool)
        cand = (Ga >= 0) & (Gb >= 0) & (Ga != Gb)
        if not cand.any():
            return out
        r, c = np.nonzero(cand)
        a, b = Ga[r, c], Gb[r, c]
        a0, a1, b0, b1 = self.n0[a], self.n1[a], self.n0[b], self.n1[b]
        shared = np.where((a0 == b0) | (a0 == b1), a0, np.where((a1 == b0) | (a1 == b1), a1, -1))
        ok = shared >= 0
        px, py = xs[c], ys[r]
        sn = np.maximum(shared, 0)
        d = np.hypot(px - self.node_xy[sn, 0], py - self.node_xy[sn, 1])
        out[r[ok & (d < JUNCTION_R0)], c[ok & (d < JUNCTION_R0)]] = True
        return out

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
        # v2.2: cells of neighbouring polygons too (the carriageway and its sidewalk, a yard beside the road)
        LR = np.zeros(owner.shape, bool)
        LD = np.zeros(owner.shape, bool)
        LR[:, :-1] = m[:, :-1] & m[:, 1:]
        LD[:-1, :] = m[:-1, :] & m[1:, :]
        same_r = (G[:, :-1] == G[:, 1:]) & (G[:, :-1] != -1) & (owner[:, :-1] == owner[:, 1:])
        same_d = (G[:-1, :] == G[1:, :]) & (G[:-1, :] != -1) & (owner[:-1, :] == owner[1:, :])
        # two lines that meet at a node near the cells are one junction: their cells are linked up to
        # JUNCTION_DZ apart (the step between them is spread by relax_seams, not left as a kerb)
        jun_r = self._junction_links(G[:, :-1], G[:, 1:], x0 + (np.arange(W - 1) + 1.0) * RES,
                                     y1 - (np.arange(H) + 0.5) * RES)
        jun_d = self._junction_links(G[:-1, :], G[1:, :], x0 + (np.arange(W) + 0.5) * RES,
                                     y1 - (np.arange(H - 1) + 1.0) * RES)
        LR[:, :-1] &= same_r | (np.abs(Z[:, :-1] - Z[:, 1:]) < STEP_Z) | (jun_r & (np.abs(Z[:, :-1] - Z[:, 1:]) < JUNCTION_DZ))
        LD[:-1, :] &= same_d | (np.abs(Z[:-1, :] - Z[1:, :]) < STEP_Z) | (jun_d & (np.abs(Z[:-1, :] - Z[1:, :]) < JUNCTION_DZ))
        # the carriageways of the main roads keep their surface: the side roads, yards and paths meeting
        # them take up the difference (a main road does not bend to a side road)
        main_cell = (G >= 0) & self.main[np.maximum(G, 0)] & (U <= 1.0)
        Z = relax_seams(Z, G, owner, LR, LD, main_cell)
        return surface_fit.Surface(owner, np.nan_to_num(Z), LR, LD, x0, y1, RES), ids


def relax_seams(Z, G, owner, LR, LD, fixed_cells=None):
    """Z with the jumps at the seams spread over SEAM_R m. A seam is a link between two cells whose heights
    come from different lines, or that lie in different polygons, and differ by more than SEAM_DZ. Around
    the seams (cells within SEAM_R m, linked) the heights are solved again keeping the height difference
    of every link but the seams', which becomes zero (a gradient-domain edit: the crown, the grade and
    the vertical curves of the roads stay, only the jump is spread smoothly over the zone); the cells
    outside the zone keep their heights, and so do fixed_cells (the carriageways of the main roads) unless
    the seam is between two of them."""
    jr = LR[:, :-1] & ((G[:, :-1] != G[:, 1:]) | (owner[:, :-1] != owner[:, 1:])) & \
        (np.abs(Z[:, :-1] - Z[:, 1:]) > SEAM_DZ)
    jd = LD[:-1, :] & ((G[:-1, :] != G[1:, :]) | (owner[:-1, :] != owner[1:, :])) & \
        (np.abs(Z[:-1, :] - Z[1:, :]) > SEAM_DZ)
    seam = np.zeros(Z.shape, bool)
    seam[:, :-1] |= jr
    seam[:, 1:] |= jr
    seam[:-1, :] |= jd
    seam[1:, :] |= jd
    if not seam.any():
        return Z
    linked = np.zeros(Z.shape, bool)
    linked[:, :-1] |= LR[:, :-1]
    linked[:, 1:] |= LR[:, :-1]
    linked[:-1, :] |= LD[:-1, :]
    linked[1:, :] |= LD[:-1, :]
    zone = ndi.binary_dilation(seam, iterations=int(round(SEAM_R / RES))) & linked & np.isfinite(Z)
    if fixed_cells is not None:
        both = np.zeros(Z.shape, bool)                  # seams between two fixed cells
        fr = jr & fixed_cells[:, :-1] & fixed_cells[:, 1:]
        fd = jd & fixed_cells[:-1, :] & fixed_cells[1:, :]
        both[:, :-1] |= fr
        both[:, 1:] |= fr
        both[:-1, :] |= fd
        both[1:, :] |= fd
        free = ndi.binary_dilation(both, iterations=int(round(SEAM_R / RES))) if both.any() else both
        zone &= ~fixed_cells | free
        if not zone.any():
            return Z
    ur, uc = np.nonzero(zone)
    idx = -np.ones(Z.shape, np.int64)
    idx[ur, uc] = np.arange(len(ur))
    H, W = Z.shape
    rows, cols, vals = [], [], []
    b = np.zeros(len(ur))
    diag = np.zeros(len(ur))
    # the four links of every cell of the zone: (neighbour offset, link present, target difference z_i - z_j)
    Zc = np.nan_to_num(Z)
    for dr_, dc_ in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        r2, c2 = ur + dr_, uc + dc_
        ok = (r2 >= 0) & (r2 < H) & (c2 >= 0) & (c2 < W)
        r2c, c2c = np.clip(r2, 0, H - 1), np.clip(c2, 0, W - 1)
        if dc_ == 1:
            lk, jump = LR[ur, uc], _pad(jr, 1)[ur, uc]
        elif dc_ == -1:
            lk, jump = LR[ur, np.maximum(uc - 1, 0)] & (uc > 0), _pad(jr, 1)[ur, np.maximum(uc - 1, 0)] & (uc > 0)
        elif dr_ == 1:
            lk, jump = LD[ur, uc], _pad(jd, 0)[ur, uc]
        else:
            lk, jump = LD[np.maximum(ur - 1, 0), uc] & (ur > 0), _pad(jd, 0)[np.maximum(ur - 1, 0), uc] & (ur > 0)
        lk = lk & ok
        g = np.where(jump, 0.0, Zc[ur, uc] - Zc[r2c, c2c])            # keep the difference, but not a jump
        diag += lk
        b += np.where(lk, g, 0.0)
        nb_unk = lk & zone[r2c, c2c]
        rows.append(np.flatnonzero(nb_unk))
        cols.append(idx[r2c, c2c][nb_unk])
        vals.append(-np.ones(int(nb_unk.sum())))
        nb_kn = lk & ~zone[r2c, c2c]
        b[nb_kn] += Zc[r2c, c2c][nb_kn]
    fixed = diag == 0                                   # a cell without links keeps its height
    diag = np.where(fixed, 1.0, diag + 1e-4)            # (a weak pull to its own height: no free piece)
    b = np.where(fixed, Zc[ur, uc], b + 1e-4 * Zc[ur, uc])
    A = sp.csr_matrix((np.concatenate(vals + [diag]), (np.concatenate(rows + [np.arange(len(ur))]),
                                                        np.concatenate(cols + [np.arange(len(ur))]))),
                      shape=(len(ur), len(ur)))
    out = Z.copy()
    out[ur, uc] = spsolve(A.tocsc(), b)
    return out


def _pad(J, axis):
    """A link mask (H, W-1) or (H-1, W) padded with False to (H, W)."""
    if axis == 1:
        return np.concatenate([J, np.zeros((J.shape[0], 1), bool)], axis=1)
    return np.concatenate([J, np.zeros((1, J.shape[1]), bool)], axis=0)


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
# class -> (material group of osm_surface.MATS, mesh cell m, uv tile m of the asphalt); the unpaved and
# stone surfaces (v2.4) tile over surface_textures.TILE_M m
CLASS_MESH = {"road": ("road", 3.0, 1.25), "strip_road": ("road", 3.0, 1.25), "hard": ("hard", 2.0, 1.25),
              "strip_path": ("path", 2.0, 1.25)}
FIXED = {"sidewalk": ("mp_sidewalk", 2.0, 1.25), "island": ("mp_island", 2.0, 2.5)}


def material(cls, surface):
    """(material, mesh cell m, uv tile m) of a polygon class with a surface of osm_surface."""
    if cls in FIXED:
        return FIXED[cls]
    import osm_surface
    import surface_textures
    group, cell, uvt = CLASS_MESH[cls]
    if surface == "natural":                         # swissTLM3D's own, before assign_surfaces
        surface = "gravel" if group == "road" else "dirt"
    surface = surface if surface in osm_surface.MATS[group] else "hard"
    return osm_surface.MATS[group][surface], cell, (uvt if surface == "hard" else surface_textures.TILE_M)


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
                # v2.4: the parts of the polygon with another surface (osm_surface.py) are meshed apart,
                # on the same heights: the facets of the whole piece, then each cut into the zones
                zones = p.get("zones") or [(p["surface"], None)]
                if p["cls"].startswith("strip"):                 # on its line, no raster
                    for surf, zg in zones:
                        zpiece = piece if zg is None else road_mesh.polygonal(piece.intersection(zg))
                        if zpiece.is_empty or zpiece.area < 1e-3:
                            continue
                        mat, cell, uvt = material(p["cls"], surf)
                        V, T = road_mesh.mesh_polygon(zpiece, net.strip_height(int(pid)), cell=cell)
                        if len(T) and np.isfinite(V[:, 2]).all():
                            emit(cx, cy, mat, uvt, V, T)
                            n_tri += len(T)
                    continue
                # the vertices too: no deeper than SUNK under the bare ground (an edge extrapolated
                # from far cells of its surface)
                zf = (lambda pid_: (lambda x, y, comp: np.maximum(S.height(x, y, pid=pid_, comp=int(comp)),
                                                                  lo.sample(x, y))))(int(pid))
                kf_all = (lambda pid_: (lambda x, y: S.surfaces_at_polygon(x, y, pid_)))(int(pid))
                for part, comp in road_mesh.split_by_surface(piece, S, int(pid), cut=cbox.exterior):
                    kf = kf_all if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                    for surf, zg in zones:
                        zpart = part if zg is None else road_mesh.polygonal(part.intersection(zg))
                        if zpart.is_empty or zpart.area < 1e-3:
                            continue
                        mat, cell, uvt = material(p["cls"], surf)
                        for comp_, V, T in road_mesh.mesh_polygon_surfaces(zpart, zf, kf, cell=cell):
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
