"""Walls (retaining and free-standing) from the cadastral survey (MU 'muro').

Footprint: SOSF 'muro' polygons at their surveyed thickness; SOLI 'muro' lines
buffered to 0.30 m. Walls already modelled by swissBUILDINGS3D ('Mauer gross')
are skipped. For every footprint vertex (densified to <= 0.5 m):
  base z = lowest DTM ground within 1.2 m (minus 0.4 m foundation below ground)
  top  z = max(highest DTM ground within 1.2 m      -> retaining wall crest,
               LiDAR crest: 90th pct of non-vegetation points on the wall,
               without unclassified returns within 0.6 m of a guardrail)
Walls lower than 0.25 m above the lower ground are given 0.25 m (they exist in the
survey). Next to the road the top is capped at the road surface + 0.15 m where the panoramas
show no wall above the road (wall_caps.py: the LiDAR crest caught guardrails and shrubs).
Within 1 m of a paved surface (roadheight.py) a wall reaches from 0.4 m below it to at least
0.15 m above it: the idealised road can be higher (a bridge) or lower (a smeared ramp removed)
than the DTM the wall was measured on. v2.0: no wall stands more than FREE_OVER m above the way of a car
(drive_free: the surveyed roads of the network and a band around every line; the survey and the
swissTLM3D lines do not always agree, and a wall drawn across a street would close it).
v2.4: the walls the panoramas see as flat paving, with level ground around (markings_state.py
removed_walls: taken away when the street was rebuilt) are left out.
Output meshes: prism sides + triangulated top, per 128 m chunk.
Also returns the footprints for the terrain: carve_terrain lowers the terrain vertices whose
triangles touch a wall on its low side to the foot of the wall; on the high side the terrain keeps the
ground (a 1.5 m terrain grid cannot hold a step inside a 0.3 m wall: it rises across the wall within
one terrain step).
"""
import os, pickle
import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon
from scipy.ndimage import minimum_filter, maximum_filter, map_coordinates
from scipy.spatial import cKDTree
from config import WORK, NO_PHOTO
from geo import Grid
import bng
import argparse, json, os, re, struct, sys, time, zipfile
import groundcover
import optimize_level
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE
from terrain import VERGE

CHUNK = 128.0
R_SEARCH = 1.2
# m of wall per repeat of the texture of each material (bld_textures.py, v2.2: original textures)
WALL_TILE = {"mp_wall_stone": 3.0, "mp_wall_stone_top": 4.0, "mp_wall_concrete": 4.0, "mp_wall_concrete_top": 4.0,
             "mp_wall_plaster": 5.0}
WALL_MATERIALS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "wall_materials.json")
_wall_mat = {}


def wall_material(x, y, default):
    """(material, vertex colour or None) of the cadastral wall piece whose middle is at (x, y): what the
    panoramas showed (sv_walls.py -> dati/wall_materials.json, [[x, y, "stone" | "concrete" | "plaster", n,
    contrast, saturation, luminance, rgb], ...], matched within 1.5 m: the survey is downloaded at every
    build), otherwise the default."""
    if "tree" not in _wall_mat:
        rows = []
        if os.path.exists(WALL_MATERIALS):
            import json as _json
            rows = _json.load(open(WALL_MATERIALS)).get("walls", [])
        _wall_mat["tree"] = cKDTree(np.array([[r[0], r[1]] for r in rows])) if rows else None
        _wall_mat["rows"] = rows
    if _wall_mat["tree"] is None:
        return default, None
    d, j = _wall_mat["tree"].query([x, y])
    if d > 1.5:
        return default, None
    r = _wall_mat["rows"][j]
    if r[2] == "plaster":
        return "mp_wall_plaster", np.clip(np.asarray(r[7] if len(r) > 7 else (0.85, 0.82, 0.75), float) / 0.9, 0, 1)
    return {"stone": "mp_wall_stone", "concrete": "mp_wall_concrete"}.get(r[2], default), None


def removed():
    """Points of the survey walls the panoramas see as flat paving (markings_state.removed_walls, v2.4):
    {"remove": [points], "flush": [points]}: left out, or kept with their top at the paving."""
    import json
    f = os.path.join(WORK, "markings_state.json")
    rw = json.load(open(f)).get("removed_walls", []) if os.path.exists(f) else []
    out = {"remove": [], "flush": []}
    for w in rw:
        out[w.get("action", "remove")].append(shapely.Point(w["x"], w["y"]))
    return out


MIN_PIECE_AREA = 0.25     # m^2, smaller pieces left over by that are dropped
MIN_PIECE_WIDTH = 0.08    # m, half the least width of a piece kept


def wall_footprints(av, skip_polys, taken=None):
    """[(footprint, kind, properties)]: the surface walls of the survey, then the line walls (0.30 m), each
    without the ground a footprint before it covers (and `taken`: the roadside walls of the panoramas); a wall
    mostly inside one that swissBUILDINGS3D models (skip_polys) is left out. The survey has some walls twice (a
    line on a surface, two surfaces overlapping) and the game had two walls, one in the other: up to v2.8 the
    line was kept whole beside the surface, and a wall half along a roadside wall whole beside it."""
    src = [(g, "poly", p) for g, p in av["SOSF"].get("muro", [])] + \
          [(g.buffer(0.15, cap_style="flat", join_style="mitre"), "line", p) for g, p in av["SOLI"].get("muro", [])]
    if skip_polys:
        sk = shapely.union_all(skip_polys)
        src = [(g, k, p) for g, k, p in src if g.intersection(sk).area < 0.5 * g.area]
    cell = 32.0
    grid = {}

    def cells(g):
        x0, y0, x1, y1 = g.bounds
        return [(i, j) for i in range(int(np.floor(x0 / cell)), int(np.floor(x1 / cell)) + 1)
                for j in range(int(np.floor(y0 / cell)), int(np.floor(y1 / cell)) + 1)]

    def add(g):
        for c in cells(g):
            grid.setdefault(c, []).append(g)
    if taken is not None and not taken.is_empty:
        for q in polygons(taken):
            add(q)
    out = []
    for g, k, p in src:
        g = shapely.make_valid(g)
        if g.is_empty or g.area <= 0:
            continue
        near = {id(h): h for c in cells(g) for h in grid.get(c, ()) if h.intersects(g)}
        if near:
            rest = g.difference(shapely.union_all(list(near.values())))
            # what is left: the pieces wide and big enough to be a wall (not the sliver of a line beside a surface)
            rest = [q for q in polygons(rest) if q.area >= MIN_PIECE_AREA and not q.buffer(-MIN_PIECE_WIDTH).is_empty]
            if not rest:
                continue
            g = rest[0] if len(rest) == 1 else MultiPolygon(rest)
        out.append((g, k, p))
        add(g)
    return out


def polygons(g):
    """The polygons of a geometry, also inside nested collections (a cut wall can be one)."""
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [p for x in getattr(g, "geoms", []) for p in polygons(x)]


def _context():
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    mauer = [shapely.MultiPoint(b["walls"].reshape(-1, 3)[:, :2]).convex_hull
             for b in blds if b["kind"] == "Mauer gross" and len(b["walls"])]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    k = int(round(2 * R_SEARCH / dtm.res)) | 1
    lf = os.path.join(WORK, "lidar_near.npz")
    # LiDAR crests along the route (lidar_extract.py); a build without the point clouds (v2.0 in the
    # cloud) takes the wall tops from the DTM and the photo caps only
    lid = np.load(lf) if os.path.exists(lf) else {"x": np.zeros(0), "y": np.zeros(0), "z": np.zeros(0),
                                                    "cls": np.zeros(0, int)}
    nonveg = np.isin(lid["cls"], [1, 2, 6])
    # unclassified returns on a guardrail are not the wall crest (a retaining wall under a
    # guardrail would otherwise get a 0.8 m parapet that does not exist)
    import json
    gr_file = os.path.join(WORK, "guardrails_final.json")
    if os.path.exists(gr_file):
        gr = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(0.6)
                                for r in json.load(open(gr_file)) if len(r["pts"]) > 1])
        shapely.prepare(gr)
        cand = np.where(nonveg & (lid["cls"] == 1))[0]
        nonveg[cand[shapely.contains_xy(gr, lid["x"][cand], lid["y"][cand])]] = False
    LP = np.column_stack([lid["x"][nonveg], lid["y"][nonveg]])
    import json
    rw_file = os.path.join(WORK, "roadside_walls.json")
    rw = json.load(open(rw_file)) if os.path.exists(rw_file) else []
    rw_zone = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(1.5) for r in rw
                                 if len(r["pts"]) > 1]) if rw else None
    caps_f = os.path.join(WORK, "wall_caps.json")
    caps = json.load(open(caps_f)) if os.path.exists(caps_f) else {}
    import roadheight
    near = None
    nf = os.path.join(WORK, "network.npz")
    if os.path.exists(nf):                         # v2.0: only the walls seen from a road or path
        import network
        segs, d, _ = network.load()
        path = np.array([segs[k]["kind"] == "path" for k in d["seg"]], bool)
        near = {kind: (cKDTree(np.column_stack([d["x"][m], d["y"][m]])), 0.5 * d["width"][m])
                for kind, m in (("road", ~path), ("path", path)) if m.any()}
    return dict(av=av, mauer=mauer, dtm=dtm, k=k, LP=LP, LZ=lid["z"][nonveg],
                tree=cKDTree(LP) if len(LP) else None, rw_zone=rw_zone, caps=caps, surface=roadheight.load(),
                near=near)


NEAR = {"road": 60.0, "path": 25.0}     # m, cadastral walls farther from every road and path are left out (v2.0)
FINE = {"road": 15.0, "path": 8.0}      # m, finer vertices on the walls this close to a road or path
STEP_FINE, STEP_COARSE = 1.0, 2.5       # m between the vertices of a wall outline (v1.x: 0.5 and 2)
# no cadastral wall on the way of a car (v2.0): the surveyed walls and the swissTLM3D lines do not always
# agree, and a wall drawn across a street or along the axis of a lane would close it
FREE_ERODE = 0.6                         # m, a wall may reach this far onto a surveyed road (a parapet at its edge)
FREE_BAND = {"road": 0.25, "path": 0.35}  # of the width of a line: the band around it kept free
FREE_MIN = {"road": 1.0, "path": 0.5}    # m, the least half width of that band (a car is 1.8-2 m wide)
FREE_OVER = 0.3                          # m, a wall is cut where it stands this much above the way
FREE_MARGIN = 0.15                       # m added to the band: no wall face left on its very edge


def drive_free(net, corridor=None):
    """[(polygon, stations (n, 3) of its lines)] of the ways no cadastral wall may stand on: the roads
    of the cadastral survey in the network (network_mesh.Network; eroded by FREE_ERODE: a wall may stand
    on their edge) and a band around every line outside the bridges (the way the AI and a car take;
    the strips of the lines without a survey polygon have the nominal width of swissTLM3D, often wider
    than the lane between its walls). Not inside `corridor` (the Strada Cantonale Magliaso - Pura, whose
    walls were checked on the panoramas)."""
    def stations(ks):
        ks = [k for k in ks if not net.segs[k]["bridge"]]
        if not ks:
            return np.zeros((0, 3))
        idx = np.concatenate([np.arange(net.segs[k]["first"], net.segs[k]["first"] + net.segs[k]["n"]) for k in ks])
        return np.column_stack([net.x[idx], net.y[idx], net.z[idx]])
    out = []
    for p in net.polys:
        if p["cls"] == "road":
            g = p["geom"].buffer(-FREE_ERODE)
            if not g.is_empty:
                out.append((g, stations(sorted(p["segs"]))))
    for s in net.segs:
        if s["bridge"]:
            continue
        a, n = s["first"], s["n"]
        line = shapely.LineString(np.column_stack([net.x[a:a + n], net.y[a:a + n]]))
        hw = max(FREE_BAND[s["kind"]] * float(np.median(net.w[a:a + n])), FREE_MIN[s["kind"]]) + FREE_MARGIN
        out.append((line.buffer(hw), stations([s["id"]])))          # round ends: no wedge where lines meet
    if corridor is not None and not corridor.is_empty:
        shapely.prepare(corridor)
        out = [(g.difference(corridor) if corridor.intersects(g) else g, Z) for g, Z in out]
    return [(g, Z) for g, Z in out if not g.is_empty and len(Z)]


def above_way(w, ctx):
    """Union of the drivable ways (ctx["free"], drive_free) on which the measured wall piece w stands
    more than FREE_OVER m above the way (nearest station of its lines), None where there is none: a
    retaining wall under a road stays."""
    free = ctx.get("free")
    if not free:
        return None
    cut = []
    V = w["allv"]
    for i in ctx["free_tree"].query(w["poly"], predicate="intersects"):
        F, Z = free[i]
        near = shapely.dwithin(F, shapely.points(V), 1.0)
        if not near.any():
            continue
        trees = ctx.setdefault("free_kd", {})
        if i not in trees:
            trees[i] = cKDTree(Z[:, :2])
        zway = Z[trees[i].query(V[near])[1], 2]
        if np.max(w["ztop"][near] - zway) > FREE_OVER:
            cut.append(F)
    return shapely.union_all(cut) if cut else None


def wall_geometry(ctx=None):
    """Yield every cadastral wall polygon with its per-vertex base/top heights (see module doc)."""
    ctx = ctx or _context()
    dtm = ctx["dtm"]
    k = ctx["k"]

    def local(poly):
        """Lowest and highest DTM ground within R_SEARCH of the wall (window of the wall only)."""
        x0, y0, x1, y1 = poly.bounds
        sub, _, _ = dtm.window(x0, y0, x1, y1, pad=k + 2)
        a = np.asarray(sub.a, np.float32)
        return (Grid(minimum_filter(a, size=k), sub.x_min, sub.y_max, sub.res),
                Grid(maximum_filter(a, size=k), sub.x_min, sub.y_max, sub.res))

    def samp(g, x, y):
        return g.sample(x, y)
    import json as _json
    road = shapely.LineString(np.load(os.path.join(WORK, "road_profile.npz"))["center"])
    # the walls beyond the 0.5 m DTM (outside the area) have no ground to be measured on
    gx0, gy0, gx1, gy1 = dtm.bounds()
    on_dtm = shapely.box(gx0, gy0, gx1, gy1).buffer(-(R_SEARCH + 1.0), join_style="mitre")
    seen = removed()
    gone_tree = shapely.STRtree(seen["remove"]) if seen["remove"] else None
    flush_tree = shapely.STRtree(seen["flush"]) if seen["flush"] else None
    for wi, (g, kind, props) in enumerate(wall_footprints(ctx["av"], ctx["mauer"], ctx["rw_zone"])):
        if not on_dtm.contains(g):
            continue
        if gone_tree is not None and len(gone_tree.query(g, predicate="dwithin", distance=0.05)):
            continue                                      # no longer there (markings_state.removed_walls)
        flush = flush_tree is not None and len(flush_tree.query(g, predicate="dwithin", distance=0.05)) > 0
        if ctx.get("near") is not None:
            c = g.representative_point()
            dist = {}
            for kind, (tree, hw) in ctx["near"].items():
                d, j = tree.query([c.x, c.y])
                dist[kind] = d - hw[j]
            if all(dist[k] > NEAR[k] for k in dist):
                continue
            fine = any(dist[k] < FINE[k] for k in dist) or g.distance(road) < 60
        else:
            fine = g.distance(road) < 60

        def measure(poly, key):
            """The wall piece poly with the heights of its outline."""
            # fine vertex spacing where the walls are seen from the road, coarse far away
            step = (0.5 if ctx.get("near") is None else STEP_FINE) if fine else STEP_COARSE
            poly = shapely.segmentize(shapely.geometry.polygon.orient(poly, 1.0), step)
            if poly.geom_type != "Polygon":                  # never one here, kept safe: its largest piece
                poly = max(polygons(poly), key=lambda q: q.area)
            rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in poly.interiors]
            allv = np.concatenate(rings)
            dmin, dmax = local(poly)
            zlo = samp(dmin, allv[:, 0], allv[:, 1])
            zhi = samp(dmax, allv[:, 0], allv[:, 1])
            crest = np.full(len(allv), -1e9)
            inner = poly.buffer(0.05)
            idx = ctx["tree"].query_ball_point(allv, r=0.6) if ctx["tree"] is not None else [[] for _ in allv]
            LP, LZ = ctx["LP"], ctx["LZ"]
            for j, ii in enumerate(idx):
                if len(ii) >= 3:
                    ii = np.array(ii)
                    on = shapely.contains_xy(inner, LP[ii, 0], LP[ii, 1])
                    if on.sum() >= 3:
                        crest[j] = np.percentile(LZ[ii][on], 90)
            ztop = np.maximum(zhi, crest)
            thick = max(0.35, min(1.5, 2 * poly.area / max(poly.length, 1e-6) + 0.2))
            vt = cKDTree(allv)
            nb = vt.query_ball_point(allv, r=thick)
            ztop = np.array([ztop[ii].max() for ii in nb])
            zlo = np.array([zlo[ii].min() for ii in nb])
            nb1 = vt.query_ball_point(allv, r=1.0)
            ztop = np.array([np.median(ztop[ii]) for ii in nb1])
            ztop = np.maximum(ztop, zlo + 0.25)
            ztop = np.minimum(ztop, zlo + 12.0)
            # no parapet where the panoramas see none above the road (wall_caps.py)
            if ctx.get("caps"):
                cap = np.array([ctx["caps"].get("%.2f,%.2f" % (v[0], v[1]), np.inf) for v in allv])
                ztop = np.minimum(ztop, cap)
                # one top across the thickness: a cap measured on one face holds for the other
                capped = np.isfinite(cap)
                if capped.any():
                    across = np.array([np.min(np.where(capped[ii], ztop[ii], np.inf)) for ii in nb])
                    ztop = np.minimum(ztop, across)
            zbot = zlo - 0.4
            # next to a paved surface the wall meets the (idealised) road surface
            S = ctx.get("surface")
            zr_all = None
            if S is not None:
                near = S.distance(allv[:, 0], allv[:, 1]) < 1.25
                if near.any():
                    zr = S.height(allv[near, 0], allv[near, 1])
                    zbot[near] = np.minimum(zbot[near], zr - 0.4)
                    ztop[near] = np.maximum(ztop[near], zr + 0.15)
                    zr_all = np.where(near, 0.0, np.nan)
                    zr_all[near] = zr
            # v2.4: the panoramas see the paving over it (a retaining wall under the edge of a street):
            # the top flush with the paving (the road surface, else the ground), not above it
            if flush:
                zp = np.where(np.isfinite(zr_all), zr_all, zhi) if zr_all is not None else zhi
                ztop = np.maximum(np.minimum(ztop, zp - 0.02), zbot + 0.05)
            return dict(key=key, poly=poly, rings=rings, allv=allv, zlo=zlo, ztop=ztop,
                        zbot=zbot, zhi=zhi, samp=samp, dmax=dmax)

        for pj, poly in enumerate(polygons(g)):
            if poly.area < 0.05:
                continue
            w = measure(poly, f"w{wi}_{pj}")
            # no wall standing on the way of a car: the parts on a drivable way that rise above it are cut
            # away, the rest measured again
            cut = above_way(w, ctx)
            if cut is None:
                yield w
                continue
            for pq, part in enumerate(polygons(w["poly"].difference(cut))):
                if part.area >= 0.05:
                    yield measure(part, f"w{wi}_{pj}_{pq}")


def add_photo_pieces(mb, atlas, prefix, tex, T6, U6, u_lo, u_hi, z_lo, z_hi):
    """Map ribbon quads (T6: (n, 6, 3) vertices, U6: (n, 6) arc length) onto the photo
    texture tex = (img, L, v0, vlen) of the whole ribbon. The image is cut into pieces of
    <= PIECE px along the ribbon, each cropped to the heights its quads use, so long walls keep
    the projected resolution instead of being shrunk to one 4096 px atlas page."""
    img, L, v0, vlen = tex
    Hh, Ww = img.shape[:2]
    du, dv = L / Ww, vlen / Hh
    v1 = v0 + vlen
    piece = (0.5 * (u_lo + u_hi) / (PIECE * du)).astype(int)
    for q in np.unique(piece):
        sel = np.where(piece == q)[0]
        c0 = int(np.clip(np.floor(u_lo[sel].min() / du), 0, Ww - 1))
        c1 = int(np.clip(np.ceil(u_hi[sel].max() / du), c0 + 1, Ww))
        r0 = int(np.clip(np.floor((v1 - (z_hi[sel].max() + 0.05)) / dv), 0, Hh - 1))
        r1 = int(np.clip(np.ceil((v1 - (z_lo[sel].min() - 0.05)) / dv), r0 + 1, Hh))
        page, (ax, ay, aw, ah) = atlas.add(np.ascontiguousarray(img[r0:r1, c0:c1]))
        T = T6[sel].reshape(-1, 3); UQ = U6[sel].ravel()
        UU = ax + (UQ - c0 * du) / ((c1 - c0) * du) * aw
        VV = ay + ((v1 - r0 * dv) - T[:, 2]) / ((r1 - r0) * dv) * ah
        mb.add(f"{prefix}_{page}", T, uvs=np.column_stack([UU, 1.0 - VV]), normals=bng.flat_normals_soup(T))


def exterior_ribbon(w):
    """Closed exterior ring (n+1, 2) and its base/top heights for texturing."""
    n = len(w["rings"][0])
    ring = np.vstack([w["rings"][0], w["rings"][0][:1]])
    zb = np.r_[w["zbot"][:n], w["zbot"][:1]]
    zt = np.r_[w["ztop"][:n], w["ztop"][:1]]
    return ring, zb, zt


def build(level_dir, level_name, scene, material="mp_wall_stone", free=None):
    """free: polygons no wall may stand in (drive_free)."""
    import cv2
    import texturing
    builders = {}
    carve, feet = [], []
    nwall = ntex = 0
    atlas = texturing.Atlas(4096)
    ctx = _context()
    if free:
        ctx["free"], ctx["free_tree"] = free, shapely.STRtree([f[0] for f in free])
    for w in wall_geometry(ctx):
        poly, rings, allv, zbot, ztop, zlo = w["poly"], w["rings"], w["allv"], w["zbot"], w["ztop"], w["zlo"]
        samp, dmax = w["samp"], w["dmax"]
        key = {tuple(np.round(v, 3)): (b, t) for v, b, t in zip(allv, zbot, ztop)}
        cx, cy = poly.centroid.x, poly.centroid.y
        ck = (int(np.floor(cx / CHUNK)), int(np.floor(cy / CHUNK)))
        mb = builders.setdefault(ck, bng.MeshBuilder())
        tex = None
        wmat, wcol = wall_material(poly.representative_point().x, poly.representative_point().y, material)
        tf = os.path.join(WORK, "wall_tex", f"{w['key']}.npz")
        if os.path.exists(tf) and not NO_PHOTO:
            d = np.load(tf)
            if "img" in d:
                tex = (d["img"], float(d["L"]), float(d["v0"]), float(d["vlen"]))
                ntex += 1
        off = 0
        for ri, ring in enumerate(rings):
            n = len(ring)
            zb, zt = zbot[off:off + n], ztop[off:off + n]
            off += n
            a = np.arange(n)
            b = (a + 1) % n
            A_t = np.column_stack([ring[a], zt[a]])
            A_b = np.column_stack([ring[a], zb[a]])
            B_t = np.column_stack([ring[b], zt[b]])
            B_b = np.column_stack([ring[b], zb[b]])
            tris = np.stack([A_t, A_b, B_b, A_t, B_b, B_t], 1).reshape(-1, 3)
            seg = np.linalg.norm(ring[b] - ring[a], axis=1)
            u0 = np.concatenate([[0], np.cumsum(seg)[:-1]])
            u1 = u0 + seg
            U = np.stack([u0, u0, u1, u0, u1, u1], 1).ravel()
            if tex is not None and ri == 0:
                add_photo_pieces(mb, atlas, "mp_wall_photo", tex, tris.reshape(n, 6, 3), U.reshape(n, 6), u0, u1,
                                 np.minimum(zb[a], zb[b]), np.maximum(zt[a], zt[b]))
            else:
                mb.add(wmat, tris, uvs=np.column_stack([U, tris[:, 2]]) / WALL_TILE.get(wmat, 1.6),
                       normals=bng.flat_normals_soup(tris), colors=None if wcol is None else np.r_[wcol, 1.0])
        tri = shapely.constrained_delaunay_triangles(poly)
        top = []
        for t in tri.geoms:
            c = np.asarray(t.exterior.coords)[:3]
            zz = [key.get(tuple(np.round(p, 3)), (0, samp(dmax, [p[0]], [p[1]])[0]))[1] for p in c]
            v3 = np.column_stack([c, zz])
            if np.cross(v3[1] - v3[0], v3[2] - v3[0])[2] < 0:
                v3 = v3[::-1]
            top.append(v3)
        if top:
            top = np.concatenate(top)
            tmat = "mp_wall_concrete_top" if wmat == "mp_wall_plaster" else wmat + "_top"
            mb.add(tmat, top, uvs=top[:, :2] / WALL_TILE.get(tmat, 1.6), normals=bng.flat_normals_soup(top))
        carve.append(np.column_stack([allv, zlo, ztop]))
        feet.append((poly, allv, zlo, ztop, np.minimum(w["zhi"], ztop)))
        nwall += 1
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/walls/walls_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="walls", origin=origin, orient=True)
        ntri += mb.triangle_count()
        scene.add("MissionGroup/walls", bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=True,
                                                     decal=False))
    if ntex:
        mats = []
        for i, page in enumerate(atlas.pages):
            rel = f"art/shapes/walls/wall_photo_{i}.jpg"
            cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
            mats.append(bng.material(f"mp_wall_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.9,
                                     ground_type="ROCK"))
        bng.write_materials(os.path.join(level_dir, "art", "shapes", "walls", "photo_av.materials.json"), mats)
    print("walls", nwall, "photo-textured", ntex, "chunks", len(builders), "triangles", ntri)
    return (np.concatenate(carve) if carve else np.zeros((0, 4))), feet


def near_vertices(samples, xs, ys, radius):
    """Flat indices (into the terrain rows x cols) of the terrain vertices within `radius` of the
    sample points, and the (distance, index) of the nearest sample of each (the terrain is a regular
    grid: only the vertices around every sample are looked at)."""
    sq = xs[1] - xs[0]
    k = int(np.ceil(radius / sq)) + 1
    c = np.round((samples[:, 0] - xs[0]) / sq).astype(np.int64)
    r = np.round((samples[:, 1] - ys[0]) / sq).astype(np.int64)
    dc, dr = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1))
    cc = (c[:, None] + dc.ravel()[None]).ravel()
    rr = (r[:, None] + dr.ravel()[None]).ravel()
    ok = (cc >= 0) & (cc < len(xs)) & (rr >= 0) & (rr < len(ys))
    flat = np.unique(rr[ok] * len(xs) + cc[ok])
    pts = np.column_stack([xs[flat % len(xs)], ys[flat // len(xs)]])
    d, j = cKDTree(samples[:, :2]).query(pts, k=1, distance_upper_bound=radius)
    m = np.isfinite(d)
    return flat[m], pts[m], j[m]


LOW_SIDE = 0.25        # a vertex lower than this fraction of the wall height over the wall foot is on its low side


def carve_terrain(feet, xs, ys, H):
    """Terrain vertices around the cadastral walls (feet: (footprint, vertices, foot, top, ground behind)
    of every wall, from build), those whose terrain triangles reach a face of a wall (the square of one
    terrain step around them meets the outline):
    - on the low side of the wall, or inside its footprint: 2 cm under the foot of the wall there (the
      lowest ground beside it);
    - on the high side: at least 5 cm under the ground behind the wall there (the highest ground beside
      it, not over the top): the DTM smears the walls into slopes, which left a dip behind them.
    The terrain square across a retaining wall then rises from its foot to the ground behind it within
    one terrain step: inside the wall, and as a short bank of earth at its foot. A vertex on the low side
    of one wall and the high side of another goes down.
    v2.8: up to here the vertices on the high side dropped to the foot too, so that no terrain triangle
    rose across the wall, and a mesh in the colours of the terrain (build_backfill, about 1.1 million
    triangles on 78 ha) covered the trench this left behind every retaining wall: in the game it showed
    as flat, pale facets with stepped edges, holes and loose pieces beside the walls, unlike the terrain
    around it. Now the ground behind a wall is the terrain itself, and nothing covers it."""
    if not feet:
        return H
    sq = xs[1] - xs[0]
    nx = len(xs)
    Hf = H.reshape(-1)
    H0 = Hf.copy()                                       # the ground as it was: one wall's carve is not another's side
    lo = np.full(Hf.shape, np.inf)
    hi = np.full(Hf.shape, -np.inf)
    for poly, allv, zlo, ztop, zgr in feet:
        x0, y0, x1, y1 = poly.bounds
        c0, c1 = max(int(np.floor((x0 - sq - xs[0]) / sq)), 0), min(int(np.ceil((x1 + sq - xs[0]) / sq)), nx - 1)
        r0, r1 = max(int(np.floor((y0 - sq - ys[0]) / sq)), 0), min(int(np.ceil((y1 + sq - ys[0]) / sq)), len(ys) - 1)
        if c1 < c0 or r1 < r0:
            continue
        C, R = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
        C, R = C.ravel(), R.ravel()
        X, Y = xs[C], ys[R]
        hit = shapely.intersects(shapely.box(X - sq, Y - sq, X + sq, Y + sq), poly.boundary)
        if not hit.any():
            continue
        C, R, X, Y = C[hit], R[hit], X[hit], Y[hit]
        j = cKDTree(allv).query(np.column_stack([X, Y]))[1]
        zl, zt, zg = zlo[j], ztop[j], zgr[j]
        flat = R * nx + C
        h0 = H0[flat]
        # a wall base far under the terrain is no measurement (a wall at the edge of the DTM)
        ok = np.isfinite(zl) & np.isfinite(zt) & np.isfinite(zg) & (zl > h0 - 30.0)
        inside = shapely.contains_xy(poly, X, Y)
        low = (h0 < zl + LOW_SIDE * np.maximum(zt - zl, 0.0)) | inside
        d, u = ok & low, ok & ~low
        np.minimum.at(lo, flat[d], zl[d] - 0.02)
        np.maximum.at(hi, flat[u], zg[u] - 0.05)
    down = np.isfinite(lo)
    Hf[down] = np.minimum(Hf[down], lo[down])
    up = np.isfinite(hi) & ~down
    Hf[up] = np.maximum(Hf[up], hi[up])
    return Hf.reshape(H.shape)


def build_roadside(level_dir, level_name, scene, material="mp_wall_stone", thick=1.75, photo=True):
    """Retaining walls detected along the route (roadside_walls.json): vertical face from
    0.3 m below road level to the measured top, capped (1.75 m, more than a terrain step) over the
    terrain step.
    The face is textured from the panoramas (texturing.texture_ribbon)."""
    import json
    import cv2
    runs = json.load(open(os.path.join(WORK, "roadside_walls.json")))
    import roadheight
    S = roadheight.load()
    CH = 128.0
    builders = {}
    samples = []
    atlas = cache = dsm = poses = None
    if photo:
        import texturing
        atlas = texturing.Atlas(4096)
        cache = texturing.PanoCache()
        dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
        poses = json.load(open(os.path.join(WORK, "poses.json")))
    for r in runs:
        P = np.array(r["pts"])
        if len(P) < 2:
            continue
        side = r["side"]
        T = np.gradient(P[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        away = side * Nl                                     # from the road into the wall/hill
        face = P[:, :2]
        back = face + away * thick
        zr = S.height(face[:, 0], face[:, 1])                  # idealised road next to the face
        zb, zt = np.minimum(P[:, 2], zr) - 0.3, np.maximum(P[:, 3], zr + 0.15)
        c = face[len(face) // 2]
        mb = builders.setdefault((int(np.floor(c[0] / CH)), int(np.floor(c[1] / CH))), bng.MeshBuilder())
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(face, axis=0), axis=1))]
        F_b = np.column_stack([face, zb]); F_t = np.column_stack([face, zt])
        K_t = np.column_stack([back, zt])
        tri = np.stack([F_b[:-1], F_t[:-1], F_t[1:], F_b[:-1], F_t[1:], F_b[1:]], 1).reshape(-1, 3)
        uu = np.stack([s[:-1], s[:-1], s[1:], s[:-1], s[1:], s[1:]], 1).ravel()
        flip = False
        t3 = tri.reshape(-1, 3, 3)
        nrm = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
        if np.mean((nrm[:, :2] * (-away[:-1].repeat(2, 0))).sum(1)) < 0:
            flip = True
            tri = t3[:, ::-1].reshape(-1, 3)
            uu = uu.reshape(-1, 3)[:, ::-1].ravel()
        mat, uv = material, np.column_stack([uu, tri[:, 2]]) / WALL_TILE.get(material, 1.6)
        img = None
        if photo:
            img, (L, v0, vlen) = texturing.texture_ribbon(face, zb, zt, -side, poses, cache, dsm)
        if img is not None:
            ns = len(face) - 1
            add_photo_pieces(mb, atlas, "mp_rwall_photo", (img, L, v0, vlen), tri.reshape(ns, 6, 3),
                             uu.reshape(ns, 6), s[:-1], s[1:], np.minimum(zb[:-1], zb[1:]), np.maximum(zt[:-1], zt[1:]))
        else:
            mb.add(mat, tri, uvs=uv, normals=bng.flat_normals_soup(tri))
        cap = np.stack([F_t[:-1], K_t[:-1], K_t[1:], F_t[:-1], K_t[1:], F_t[1:]], 1).reshape(-1, 3)
        t3 = cap.reshape(-1, 3, 3)
        if np.mean(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])[:, 2]) < 0:
            cap = t3[:, ::-1].reshape(-1, 3)
        mb.add(material + "_top", cap, uvs=cap[:, :2] / WALL_TILE.get(material + "_top", 1.6), normals=bng.flat_normals_soup(cap))
        for k in range(len(P)):
            samples.append([face[k, 0], face[k, 1], away[k, 0], away[k, 1], zb[k] + 0.3, zt[k]])
    if photo:
        mats = []
        for i, page in enumerate(atlas.pages):
            rel = f"art/shapes/walls/rwall_photo_{i}.jpg"
            cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
            mats.append(bng.material(f"mp_rwall_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.9,
                                     ground_type="ROCK"))
        bng.write_materials(os.path.join(level_dir, "art", "shapes", "walls", "photo.materials.json"), mats)
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/walls/rwalls_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CH, (ty + 0.5) * CH, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="rwall", origin=origin, orient=True)
        scene.add("MissionGroup/walls", bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=True, decal=False))
    print("roadside walls", len(runs), "chunks", len(builders), "atlas pages", len(atlas.pages) if atlas else 0)
    return np.array(samples)


def adjust_terrain_roadside(samples, xs, ys, H, behind=3.4, front=1.6, hidden=1.6):
    """In front of a roadside wall the terrain drops to the wall base (road level),
    behind it (up to `behind` m) it rises to the wall top: the DTM smears walls into slopes.
    `hidden` is more than one terrain step (1.5 m), so every line of vertices across the wall has a
    lowered vertex behind the face and no terrain triangle rises across the face."""
    if len(samples) == 0:
        return H
    flat, pts, j = near_vertices(samples, xs, ys, max(behind, front) + 0.5)
    Hf = H.ravel()
    S = samples[j]
    off = ((pts - S[:, :2]) * S[:, 2:4]).sum(1)              # + behind the face, - in front
    # vertices up to `hidden` m behind the face stay at road level (under the 1.75 m wide cap),
    # further back they rise to the crest: the terrain step is always hidden by the wall
    fr = (off < hidden) & (off > -front)
    bh = (off >= hidden) & (off <= behind)
    Hf[flat[fr]] = np.minimum(Hf[flat[fr]], S[fr, 4] - 0.02)
    Hf[flat[bh]] = np.maximum(Hf[flat[bh]], S[bh, 5] - 0.05)
    return Hf.reshape(H.shape)


# --------------------------------------------------------------------------------------------------
# No game grass over the top of the walls (v2.8), in the built level.
#
# The grass of groundcover.py grows on the terrain layers Grass and GardenGrass, also on the vertices
# walls.carve_terrain drops to the foot of a wall: from there clumps up to GRASS_TALL m stand over the top of
# the walls lower than that. The terrain vertices of the squares a wall passes through from which the tallest
# grass would reach over the wall top there go from Grass and GardenGrass to their twins GrassVerge and
# GardenGrassVerge (terrain.VERGE): the same material, without the grass, as along the roads since v2.4. At the
# foot of a wall taller than the grass, and on the rest of the meadows (maxSlope 45 degrees), the grass stays.
# Up to the v2.8 build test this step also smoothed the normals of the backfill mesh behind the walls; there is
# no backfill any more (carve_terrain).
# The heights of the terrain are not changed; the terrain gets the date of the build step (the game converts it
# again instead of taking its cached copy); everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish wall_fill
# --------------------------------------------------------------------------------------------------

GRASS_TALL = max(t["sizeMax"] for c in groundcover.COVERS.values() for t in c[6])   # m, the tallest grass clump
SAMPLE = 0.25         # m between the samples along the edges of the wall triangles
LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def read_ter(data):
    """(n, heights (n, n) uint16, layers (n, n) uint8, layer names) of a .ter (bng.write_ter)."""
    n = struct.unpack("<I", data[1:5])[0]
    q = np.frombuffer(data, "<u2", n * n, 5).reshape(n, n)
    lay = np.frombuffer(data, np.uint8, n * n, 5 + 2 * n * n).reshape(n, n)
    o = 5 + 3 * n * n
    names = []
    for _ in range(struct.unpack("<I", data[o:o + 4])[0]):
        k = data[o + 4]
        names.append(data[o + 5:o + 5 + k].decode("utf-8"))
        o += 1 + k
    return n, q, lay, names


def wall_cells(zi, objs, n):
    """(n - 1, n - 1) float32: the top of the wall meshes in every terrain square they pass through
    (the highest of samples every SAMPLE m along the edges of their triangles, and their centres),
    -inf in the others."""
    top = np.full((n - 1, n - 1), -np.inf, np.float32)
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or "/art/shapes/walls/" not in sn or "backfill" in sn:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn.lstrip("/")).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for _, idx in parts:
            t = W[idx[:, 0]].reshape(-1, 3, 3)
            pts = [t.mean(1)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                L = np.linalg.norm(t[:, b] - t[:, a], axis=1)
                k = np.maximum(np.ceil(L / SAMPLE).astype(np.int64), 1)
                rep = np.repeat(np.arange(len(t)), k + 1)
                start = np.repeat(np.cumsum(k + 1) - (k + 1), k + 1)
                f = (np.arange(len(rep)) - start) / k[rep]               # 0, 1/k, ..., 1 along every edge
                pts.append(t[rep, a] + f[:, None] * (t[rep, b] - t[rep, a]))
            P = np.concatenate(pts)
            c = np.floor((P[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
            r = np.floor((P[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
            ok = (r >= 0) & (r < n - 1) & (c >= 0) & (c < n - 1)
            np.maximum.at(top, (r[ok], c[ok]), P[ok, 2].astype(np.float32))
    return top


def corners_of(cells):
    """(n, n) bool: the terrain vertices at the corners of the squares `cells` (n - 1, n - 1)."""
    m = np.zeros((cells.shape[0] + 1, cells.shape[1] + 1), bool)
    m[:-1, :-1] |= cells
    m[1:, :-1] |= cells
    m[:-1, 1:] |= cells
    m[1:, 1:] |= cells
    return m


def wall_fill_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = read_ter(data)
    Ht = (Z0 + q.astype(np.float64) / 65535.0 * MAXH)
    objs = read_items(zi, f"{lv}/main/MissionGroup/walls/items.level.json")
    fills = sum(1 for o in objs if "/art/shapes/walls/backfill" in o.get("shapeName", ""))
    assert not fills, "%d backfill shapes: walls.carve_terrain leaves no trench to fill any more" % fills

    # no game grass where it would stand over the top of a wall: on the vertices of the squares a wall passes
    # through (lowered to its foot by walls.carve_terrain) less than the tallest grass under the wall top there
    wtop = wall_cells(zi, objs, n)
    wcells = np.isfinite(wtop)
    pad = np.full((n + 1, n + 1), -np.inf, np.float32)
    pad[1:-1, 1:-1] = wtop
    near_top = np.maximum(np.maximum(pad[:-1, :-1], pad[:-1, 1:]), np.maximum(pad[1:, :-1], pad[1:, 1:]))
    del pad, wtop
    over = corners_of(wcells) & (Ht > near_top - GRASS_TALL)
    del near_top
    grassy = np.isin(lay, [names.index(a) for a in VERGE])
    new_lay = lay.copy()
    changed = {}
    for a, b in VERGE.items():
        ia, ib = names.index(a), names.index(b)
        m = over & (lay == ia)
        new_lay[m] = ib
        changed[f"{a} -> {b}"] = int(m.sum())
    why = {"over_wall_top": int((over & grassy).sum())}
    print("terrain vertices without game grass: %s, %s (squares crossed by a wall %d)"
          % (changed, why, int(wcells.sum())), flush=True)
    assert set(np.unique(lay[new_lay != lay])) <= {names.index(a) for a in VERGE}
    new_ter = data[:5 + 2 * n * n] + new_lay.tobytes() + data[5 + 3 * n * n:]
    assert len(new_ter) == len(data) and new_ter[:5 + 2 * n * n] == data[:5 + 2 * n * n]     # heights as they were

    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm == ter_name:
                # a new date: the game converts the terrain again instead of taking its cached one
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_ter)
            elif re.fullmatch(r"levels/[^/]+/README\.md", nm) and os.path.exists(LEVEL_README):
                zo.writestr(i, open(LEVEL_README, "rb").read(), compress_type=i.compress_type)
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    print("written in %.0f s" % (time.time() - t0), flush=True)
    if report:
        res = {"backfill_shapes": 0, "wall_squares": int(wcells.sum()), "grass_tall_m": GRASS_TALL,
               "grass_removed_vertices": changed, "grass_removed_why": why, "terrain_heights_unchanged": True}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0


# --------------------------------------------------------------------------------------------------
# v2.8: no wall face twice. A finishing step of build_level.py (FINISH, after wall_fill), on the built level.
#
# Two meshes drew some wall faces in the same plane, and the game showed them flickering into each other: the
# stone faces of the road meshes (mp_road_wall, the side of a paved edge high above the ground,
# build_level.stage_roads) in front of a retaining wall at the edge of the road (5,400 m2 on the v2.8 build
# test), and walls of the survey overlapping (7,800 m2, wall_footprints cuts them now). A steep triangle that
# lies whole in the face of others (every sample of it within FACE_D m of their plane, inside them, the same
# way out) goes: first the road faces in front of a wall, then the wall faces in front of a road face, then
# a wall face in front of an earlier one.
# --------------------------------------------------------------------------------------------------

FACE_D = 0.06          # m from the plane of the other face
FACE_IN = 0.01         # m, how far outside the other triangle a sample may be
FACE_CELL = 1.0        # m, the grid of the lookup
FACE_MATS = re.compile(r"^mp_(wall_|rwall_photo)")
ROAD_FACE = "mp_road_wall"


def _steep(W, idx):
    t = W[idx[:, 0]].reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.linalg.norm(n, axis=1)
    n = n / np.maximum(a, 1e-12)[:, None]
    return t, n, (np.abs(n[:, 2]) < 0.5) & (a > 1e-6)


class FaceSet:
    """Steep triangles with a lookup by the grid cells their footprint covers."""

    def __init__(self, T, Nn):
        self.T, self.N = T, Nn
        self.alive = np.ones(len(T), bool)
        lo = np.floor((T[:, :, :2].min(1) - FACE_D) / FACE_CELL).astype(np.int64)
        hi = np.floor((T[:, :, :2].max(1) + FACE_D) / FACE_CELL).astype(np.int64)
        self.grid = {}
        for k in range(len(T)):
            for i in range(lo[k, 0], hi[k, 0] + 1):
                for j in range(lo[k, 1], hi[k, 1] + 1):
                    self.grid.setdefault((i, j), []).append(k)

    def near(self, p):
        return self.grid.get((int(np.floor(p[0] / FACE_CELL)), int(np.floor(p[1] / FACE_CELL))), ())


def _samples(t):
    """Corners and edge middles pulled 3 cm towards the centre, and the centre."""
    c = t.mean(0)
    pts = list(t) + [(t[0] + t[1]) / 2, (t[1] + t[2]) / 2, (t[2] + t[0]) / 2]
    out = [c]
    for p in pts:
        d = c - p
        L = np.linalg.norm(d)
        out.append(p + d * min(0.03 / max(L, 1e-9), 1.0))
    return np.array(out)


def _inside(p, n, fs, cand):
    """Whether p (with the face normal n) lies in one of the triangles cand of the FaceSet fs."""
    if not len(cand):
        return False
    cand = np.asarray(cand)
    cand = cand[fs.alive[cand]]
    if not len(cand):
        return False
    Nb = fs.N[cand]
    ok = Nb @ n > 0.95
    if not ok.any():
        return False
    cand, Nb = cand[ok], Nb[ok]
    Tb = fs.T[cand]
    dist = np.einsum("ij,ij->i", p[None] - Tb[:, 0], Nb)
    ok = np.abs(dist) < FACE_D
    if not ok.any():
        return False
    Tb, Nb, dist = Tb[ok], Nb[ok], dist[ok]
    q = p[None] - dist[:, None] * Nb                     # p on the plane of each triangle
    # distance of q inside every edge (positive inside), in metres
    inside = np.ones(len(Tb), bool)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        e = Tb[:, b] - Tb[:, a]
        out = np.cross(e, Nb)                            # in the plane, away from the inside (counter-clockwise)
        out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
        s = np.einsum("ij,ij->i", q - Tb[:, a], out)
        c3 = Tb[:, 3 - a - b]
        side = np.sign(np.einsum("ij,ij->i", c3 - Tb[:, a], out))       # the inside, whatever the winding
        inside &= s * side >= -FACE_IN
    return bool(inside.any())


def covered(T, Nn, fs, before=None):
    """Mask of the triangles T (k, 3, 3), normals Nn, lying whole in faces of fs; before: for each triangle the
    number of first triangles of fs it may lie in (a set against itself: only earlier ones, still there)."""
    out = np.zeros(len(T), bool)
    for k in range(len(T)):
        ok = True
        for p in _samples(T[k]):
            cand = fs.near(p)
            if before is not None:
                cand = [j for j in cand if j < before[k]]
            if not _inside(p, Nn[k], fs, cand):
                ok = False
                break
        out[k] = ok
        if before is not None and ok:
            fs.alive[before[k]] = False                  # the set against itself: this one is gone
    return out


def double_faces_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    shapes = []
    for group, kind in (("walls", "wall"), ("roads/surfaces", "road")):
        f = f"{lv}/main/MissionGroup/{group}/items.level.json"
        if f not in zi.NameToInfo:
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "")
            if o.get("class") != "TSStatic" or not sn.endswith(".dae") or "backfill" in sn:
                continue
            text = zi.read(sn.lstrip("/")).decode("utf-8")
            if "<triangles" not in text:
                continue
            V, N, UV, C, parts, node = optimize_level.parse(text)
            shapes.append(dict(name=sn.lstrip("/"), kind=kind, V=V, N=N, UV=UV, C=C, parts=parts, node=node,
                               W=V + np.asarray(o.get("position", [0, 0, 0]), np.float64)))
    # every steep face triangle: (shape, part, triangle) and its corners
    keys, tris, nrms = {"wall": [], "road": []}, {"wall": [], "road": []}, {"wall": [], "road": []}
    for si, s in enumerate(shapes):
        for pi, (mat, idx) in enumerate(s["parts"]):
            want = ROAD_FACE if s["kind"] == "road" else None
            if (want and mat != want) or (not want and not FACE_MATS.match(mat)):
                continue
            t, n, st = _steep(s["W"], idx)
            k = np.flatnonzero(st)
            keys[s["kind"]].append(np.column_stack([np.full(len(k), si), np.full(len(k), pi), k]))
            tris[s["kind"]].append(t[k])
            nrms[s["kind"]].append(n[k])
    K = {g: np.concatenate(keys[g]) if keys[g] else np.zeros((0, 3), np.int64) for g in keys}
    Tw, Nw = (np.concatenate(tris["wall"]), np.concatenate(nrms["wall"])) if tris["wall"] else (np.zeros((0, 3, 3)), np.zeros((0, 3)))
    Tr, Nr = (np.concatenate(tris["road"]), np.concatenate(nrms["road"])) if tris["road"] else (np.zeros((0, 3, 3)), np.zeros((0, 3)))
    del keys, tris, nrms
    print("steep faces: %d of walls, %d of roads" % (len(Tw), len(Tr)), flush=True)
    drop = set()
    res = {"road_faces": len(Tr), "wall_faces": len(Tw)}

    def area(T):
        return float(0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum()) if len(T) else 0.0

    if len(Tw) and len(Tr):
        # (1) the road faces in front of a wall
        fw = FaceSet(Tw, Nw)
        # only the triangles with a wall face near their centre are tested
        near = [k for k in range(len(Tr)) if fw.near(Tr[k].mean(0))]
        m = covered(Tr[near], Nr[near], fw)
        gone_r = [near[k] for k in np.flatnonzero(m)]
        drop |= {tuple(K["road"][k]) for k in gone_r}
        res["road_faces_in_a_wall"], res["road_faces_in_a_wall_m2"] = len(gone_r), round(area(Tr[gone_r]))
        # (2) the wall faces in front of the road faces left
        keep_r = np.setdiff1d(np.arange(len(Tr)), gone_r)
        fr = FaceSet(Tr[keep_r], Nr[keep_r])
        near = [k for k in range(len(Tw)) if fr.near(Tw[k].mean(0))]
        m = covered(Tw[near], Nw[near], fr)
        gone_w = [near[k] for k in np.flatnonzero(m)]
        drop |= {tuple(K["wall"][k]) for k in gone_w}
        res["wall_faces_in_a_road_face"], res["wall_faces_in_a_road_face_m2"] = len(gone_w), round(area(Tw[gone_w]))
    if len(Tw):
        # (3) a wall face in an earlier one (two walls of the survey in one place)
        left = np.array([k for k in range(len(Tw)) if tuple(K["wall"][k]) not in drop], np.int64)
        fs = FaceSet(Tw[left], Nw[left])
        # only those with an earlier face in their plane near their centre, no corner shared (not the next
        # triangle of the same face) are tested
        C = Tw[left].mean(1)
        pr = cKDTree(C).query_pairs(1.0, output_type="ndarray")
        cand = set()
        for q in np.array_split(pr, max(1, len(pr) // 1000000)):
            a, b = q[:, 0], q[:, 1]
            ia, ib = left[a], left[b]
            ok = (np.einsum("ij,ij->i", Nw[ia], Nw[ib]) > 0.95) & \
                 (np.abs(np.einsum("ij,ij->i", C[b] - C[a], Nw[ia])) < FACE_D)
            Ta, Tb = Tw[ia[ok]], Tw[ib[ok]]
            shared = (np.abs(Ta[:, :, None, :] - Tb[:, None, :, :]).max(-1) < 1e-3).any(2).sum(1)
            cand |= set(np.maximum(a[ok], b[ok])[shared == 0].tolist())
        near = sorted(cand)
        m = covered(Tw[left[near]], Nw[left[near]], fs, before=np.array(near, np.int64))
        gone = [int(left[near[k]]) for k in np.flatnonzero(m)]
        drop |= {tuple(K["wall"][k]) for k in gone}
        res["wall_faces_in_a_wall"], res["wall_faces_in_a_wall_m2"] = len(gone), round(area(Tw[gone]))
    print(res, flush=True)
    new_dae = {}
    tmp = tempfile.mkdtemp()
    touched = {int(d[0]) for d in drop}
    drop = {tuple(int(v) for v in d) for d in drop}
    for si, s in enumerate(shapes):
        if si not in touched:
            continue
        mb = bng.MeshBuilder()
        for pi, (mat, idx) in enumerate(s["parts"]):
            tris = np.arange(len(idx)).reshape(-1, 3)
            gone = [k for k in range(len(tris)) if (si, pi, k) in drop]
            if gone:
                tris = np.delete(tris, gone, axis=0)
            col = s["C"][idx[:, 3]] if s["C"] is not None and idx.shape[1] > 3 else None
            mb.add(mat, s["V"][idx[:, 0]], uvs=s["UV"][idx[:, 2]], normals=s["N"][idx[:, 1]], tris=tris, colors=col)
        if mb.empty():                                   # nothing left of it: the shape and its object go
            new_dae[s["name"]] = None
            continue
        base, detail = re.match(r"(.*)_a(\d+)$", s["node"]).groups()
        path = os.path.join(tmp, "s.dae")
        mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
        new_dae[s["name"]] = open(path, "rb").read()
        os.remove(path)
    os.rmdir(tmp)
    gone_shapes = {"/" + n for n, d in new_dae.items() if d is None}
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in new_dae and new_dae[nm] is None:
                continue
            if gone_shapes and nm.endswith("items.level.json") and "/main/MissionGroup/" in nm:
                data = zi.read(i)
                lines = [l for l in data.decode("utf-8").splitlines()
                         if l.strip() and json.loads(l).get("shapeName") not in gone_shapes]
                if len(lines) < len([l for l in data.decode("utf-8").splitlines() if l.strip()]):
                    data = ("\n".join(lines) + "\n").encode("utf-8")
                zo.writestr(i, data, compress_type=i.compress_type)
                continue
            if nm in new_dae:
                ni = zipfile.ZipInfo(nm, now)          # a new date: the game converts the shape again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[nm])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    res["shapes_rewritten"] = len(new_dae)
    print("shapes rewritten: %d, written in %.0f s" % (len(new_dae), time.time() - t0), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res
