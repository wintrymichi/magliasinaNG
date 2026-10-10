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
Also returns the footprints for the terrain: carve_terrain lowers every terrain vertex whose
triangles touch a wall to the wall base, so no terrain triangle spans a wall and pokes out of its
face (a 1.5 m terrain grid cannot hold a step inside a 0.3 m wall), and build_backfill covers the
trench this leaves behind a retaining wall with the ground as it was (a mesh on the terrain grid).
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
import argparse, json, os, re, struct, sys, tempfile, time, zipfile
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
                        zbot=zbot, samp=samp, dmax=dmax)

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
        feet.append((poly, allv, zlo, ztop))
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


def carve_terrain(feet, xs, ys, H, rec=None):
    """Terrain vertices around the cadastral walls (feet: (footprint, vertices, base, top) of every
    wall, from build): every vertex whose terrain triangles reach a face of a wall (the square of
    one terrain step around it meets the outline) drops 2 cm under the base of the wall there. No
    terrain triangle then spans a wall, so none rises across it and pokes out of the face on its
    low side; inside a wide footprint (a platform) the ground under its top stays.
    Behind a retaining wall this leaves a trench: rec (dict) collects the vertices lowered, their
    height before, whether they lie on the high side and the wall top, for build_backfill."""
    if not feet:
        return H
    sq = xs[1] - xs[0]
    nx = len(xs)
    Hf = H.reshape(-1)
    flat_l, h0_l, high_l, in_l, top_l = [], [], [], [], []
    for poly, allv, zlo, ztop in feet:
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
        zl, zt = zlo[j], ztop[j]
        flat = R * nx + C
        h0 = Hf[flat].copy()
        # a wall base far under the terrain is no measurement (a wall at the edge of the DTM)
        ok = np.isfinite(zl) & np.isfinite(zt) & (zl > h0 - 30.0)
        if not ok.all():
            C, R, X, Y, zl, zt, flat, h0 = C[ok], R[ok], X[ok], Y[ok], zl[ok], zt[ok], flat[ok], h0[ok]
            if not len(flat):
                continue
        inside = shapely.contains_xy(poly, X, Y)
        flat_l.append(flat); h0_l.append(h0); in_l.append(inside); top_l.append(zt)
        high_l.append((h0 > 0.5 * (zl + zt)) & ~inside)
        Hf[flat] = np.minimum(Hf[flat], zl - 0.02)
    if rec is not None and flat_l:
        flat = np.concatenate(flat_l)
        order = np.argsort(flat, kind="stable")                  # first record: the height before any wall
        flat, h0, high, inside, top = (flat[order], np.concatenate(h0_l)[order], np.concatenate(high_l)[order],
                                       np.concatenate(in_l)[order], np.concatenate(top_l)[order])
        first = np.r_[True, flat[1:] != flat[:-1]]
        grp = np.cumsum(first) - 1
        n = int(first.sum())
        any_high = np.zeros(n, bool); np.logical_or.at(any_high, grp, high)
        any_in = np.zeros(n, bool); np.logical_or.at(any_in, grp, inside)
        top_max = np.full(n, -np.inf); np.maximum.at(top_max, grp, top)
        rec.update(flat=flat[first], h0=h0[first], high=any_high & ~any_in, top=top_max)
    return Hf.reshape(H.shape)


BACKFILL_LIFT = 0.03   # m, the backfill over a lowered vertex stays this much over the ground it restores


FILL_MAX_OFF = 0.4     # m, a backfill vertex inside a terrain square stays this close to the ground before the carve
FILL_MIN_NZ = 0.25     # the backfill drops its triangles steeper than this (normal z): spikes, not ground


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def fill_material(layer, base):
    """The material of the backfill on the terrain layer `layer` (v2.8): the colour of the terrain itself, its base
    colour texture (base: the base_tex entry of build_level, "b" its path) at the terrain's detail size (texture
    coordinates of build_backfill), with the game's detail normal and ambient occlusion maps of the layer, fully
    rough like the ground. Up to v2.8 it was the flat base colour with no roughness, a pale, shiny sheet; the
    detail colour map tinted to the base colour came out brighter and greener than the terrain in the game
    (the terrain blends its detail at 45 %): lime green beside the walls."""
    import terrain
    gm, det, mac, dsize, msize = terrain.TERRAIN_MATS[layer]
    return bng.material("mp_fill_" + layer.lower(), base["b"], f"{det}_nm.png", None, f"{det}_ao.png",
                        roughness=1.0, ground_type=gm)


ON_WALL = 0.03         # m, a backfill vertex this close to the outline of a wall lies on it


def wall_top_at(V2, Z, polys, trees, tops):
    """The heights Z of the vertices V2 (k, 2), with those on the outline of one of the walls (polys, cKDTree of
    the outline vertices, the top at each) at the top of that wall there."""
    Z = Z.copy()
    for poly, tree, top in zip(polys, trees, tops):
        d = shapely.distance(poly.boundary, shapely.points(V2))
        on = np.flatnonzero(d < ON_WALL)
        if len(on):
            t = top[tree.query(V2[on])[1]]
            ok = np.isfinite(t)
            Z[on[ok]] = t[ok]
    return Z


def build_backfill(level_dir, level_name, scene, rec, H, xs, ys, feet, drivable, layers, ground):
    """Mesh restoring the ground behind the retaining walls where carve_terrain lowered it: the
    terrain squares around every vertex lowered on the high side of a wall, cut at the walls and at
    the drivable surfaces (drivable: polygons), with the heights of the ground before the carve at
    those vertices, the wall top at the vertices under or in front of the wall and the terrain as
    built at the others, so the mesh meets the terrain along the edges of the squares. The material
    of every square is that of its terrain layer (mp_fill_<layer>); layers: terrain layer per vertex,
    ground(x, y): the bare ground (to tell the high side of a wall from the low one)."""
    import terrain
    if not rec or not len(rec.get("flat", [])):
        return 0
    sq = xs[1] - xs[0]
    nx, ny = len(xs), len(ys)
    Hf = H.reshape(-1)
    flat, h0, high, top = rec["flat"], rec["h0"], rec["high"], rec["top"]
    sunk = high & (h0 - Hf[flat] > 0.02)
    B, Tw = {}, {}          # vertex -> backfill height on the high side / wall top under or before a wall
    for f, a, hg, t, sk in zip(flat.tolist(), h0.tolist(), high.tolist(), top.tolist(), sunk.tolist()):
        if hg:
            B[f] = a + BACKFILL_LIFT if sk else a
        else:
            Tw[f] = t
    r_s, c_s = np.divmod(flat[sunk], nx)
    cells = set()
    for dr in (-1, 0):
        for dc in (-1, 0):
            rr, cc = r_s + dr, c_s + dc
            ok = (rr >= 0) & (rr < ny - 1) & (cc >= 0) & (cc < nx - 1)
            cells.update(zip(rr[ok].tolist(), cc[ok].tolist()))
    if not cells:
        return 0
    cells = sorted(cells)
    fp = [f[0] for f in feet]
    ftree = shapely.STRtree(fp)
    zmid = [0.5 * (f[2] + f[3]) for f in feet]
    vt = [cKDTree(f[1]) for f in feet]
    dtree = shapely.STRtree(drivable) if drivable else None
    names = list(terrain.TERRAIN_MATS)
    builders = {}
    n_tri = n_steep = n_road = 0
    for r, c in cells:
        X0, Y0 = xs[c], ys[r]
        cell = shapely.box(X0, Y0, X0 + sq, Y0 + sq)
        corner = [r * nx + c, r * nx + c + 1, (r + 1) * nx + c, (r + 1) * nx + c + 1]    # 00, 10, 01, 11
        walls_here = ftree.query(cell, predicate="intersects")
        # a corner under or before the wall: the wall top where the square is cut at the wall (the
        # backfill meets the top), the terrain past the end of a wall
        z = np.array([B[k] if k in B else (Tw[k] if (k in Tw and len(walls_here)) else Hf[k]) for k in corner])
        cut = cell
        if len(walls_here):
            cut = cut.difference(shapely.union_all([fp[i] for i in walls_here]))
        # v2.8: also under the roads, paths and yards beside the wall, where the carve dug under their edges and
        # left them hanging over a hole (map-wide: about one triangle in ten of the roads within 2 m of a
        # wall); there the backfill stays under the surface (no corner above the restored ground)
        under = shapely.Polygon()
        if dtree is not None:
            roads_here = dtree.query(cell, predicate="intersects")
            if len(roads_here):
                road_u = shapely.union_all([drivable[i] for i in roads_here]).buffer(0.02)
                under = cut.intersection(road_u)
                cut = cut.difference(road_u)
        zb = [B[k] for k in corner if k in B]
        sets = [(cut, False)] + ([(under, True)] if zb and not under.is_empty else [])
        for geom, on_road in sets:
            if geom.is_empty or geom.area < 0.01:
                continue
            pieces = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and g.area >= 0.01]
            if len(walls_here):                          # only the pieces on the high side of the wall
                keep = []
                for g in pieces:
                    q = g.representative_point()
                    best, zm = np.inf, None
                    for i in walls_here:
                        d, j = vt[i].query([q.x, q.y])
                        if d < best:
                            best, zm = d, zmid[i][j]
                    if ground(np.array([q.x]), np.array([q.y]))[0] > zm:
                        keep.append(g)
                pieces = keep
            if not pieces:
                continue
            if len(pieces) == 1 and pieces[0].equals(cell):
                # the terrain square itself, split along the diagonal of the terrain (Torque: alternating)
                P = np.array([[X0, Y0], [X0 + sq, Y0], [X0, Y0 + sq], [X0 + sq, Y0 + sq]])
                tri = [(0, 1, 3), (0, 3, 2)] if (r ^ c) & 1 == 0 else [(0, 1, 2), (1, 3, 2)]
                V2 = np.concatenate([P[list(t)] for t in tri])
            else:
                V2 = np.concatenate([np.asarray(t.exterior.coords)[:3]
                                     for g in pieces for t in shapely.constrained_delaunay_triangles(g).geoms])
            fx, fy = np.clip((V2[:, 0] - X0) / sq, 0, 1), np.clip((V2[:, 1] - Y0) / sq, 0, 1)
            Z = (z[0] * (1 - fx) * (1 - fy) + z[1] * fx * (1 - fy) + z[2] * (1 - fx) * fy + z[3] * fx * fy)
            if on_road:
                # under a road: never over the restored ground of the square's corners (that ground is the road's
                # own carve, 10 cm under its surface), not up to the wall top
                Z = np.minimum(Z, max(zb))
            else:
                # v2.8: inside the square (not on its edges, which the terrain beside shares) no vertex far from
                # the ground as it was: a corner under a taller wall (stacked walls, a road in a cut) tilted whole
                # pieces upright
                inner = np.flatnonzero((fx > 1e-6) & (fx < 1 - 1e-6) & (fy > 1e-6) & (fy < 1 - 1e-6))
                if len(inner):
                    g = ground(V2[inner, 0], V2[inner, 1])
                    Z[inner] = np.clip(Z[inner], g - FILL_MAX_OFF, g + FILL_MAX_OFF)
                if len(walls_here):
                    # v2.8: the vertices where the square is cut at a wall take the wall top there (the nearest
                    # vertex of its outline), not the mix of the corners: no saw teeth between wall top and meadow
                    Z = wall_top_at(V2, Z, [fp[i] for i in walls_here], [vt[i] for i in walls_here],
                                    [feet[i][3] for i in walls_here])
            V = np.column_stack([V2, Z]).reshape(-1, 3, 3)
            nrm = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
            up = nrm[:, 2] < 0
            V[up] = V[up][:, ::-1]                       # counter-clockwise from above
            steep = np.abs(nrm[:, 2]) < FILL_MIN_NZ * np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
            if steep.any():
                n_steep += int(steep.sum())
                V = V[~steep]
                if not len(V):
                    continue
            n_road += len(V) if on_road else 0
            mat = "mp_fill_" + names[int(layers[r, c])].lower()
            key = (int(np.floor(X0 / CHUNK)), int(np.floor(Y0 / CHUNK)))
            builders.setdefault(key, {}).setdefault(mat, []).append(V.reshape(-1, 3))
            n_tri += len(V)
    for (tx, ty), mats in sorted(builders.items()):
        mb = bng.MeshBuilder()
        for mat, parts in mats.items():
            T = np.concatenate(parts)
            dsize = terrain.TERRAIN_MATS[names[[n.lower() for n in names].index(mat[len("mp_fill_"):])]][3]
            mb.add(mat, T, uvs=T[:, :2] / dsize, normals=bng.flat_normals_soup(T))     # v2.8: the detail size
        rel = f"art/shapes/walls/backfill_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="backfill", origin=origin)
        scene.add("MissionGroup/walls", bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=True,
                                                     decal=False))
    print("backfill behind the walls: %d squares, %d triangles (%d under roads), %d chunks, %d steep triangles left out"
          % (len(cells), n_tri, n_road, len(builders), n_steep))
    return n_tri


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
# The ground behind the retaining walls shaded like the terrain, and no game grass under it or along the
# walls (v2.8), in the built level.
#
# The terrain is a 1.5 m grid and cannot hold a step inside a 0.3 m wall: walls.carve_terrain lowers every
# terrain vertex whose triangles touch a wall to the foot of the wall, and walls.build_backfill covers the
# trench this leaves on the high side with a mesh at the height of the ground as it was (about 784,000
# triangles, 63 ha in v2.7, in art/shapes/walls/backfill_*.dae). Two things showed it in the game:
# - the backfill had one normal per triangle (bng.flat_normals_soup): every triangle lit on its own, flat
#   facets and saw teeth where its corners alternate between the wall top and the meadow, beside a terrain
#   that is shaded smoothly;
# - the grass of groundcover.py grows on the terrain layers Grass and GardenGrass, also on the vertices
#   lowered under the backfill: 29 % of them are less than 0.8 m under it, and the grass clumps (0.15 to
#   0.8 m) stand through the mesh; along the walls they grow on the vertices dropped to the foot of the
#   wall, and over the top of the walls lower than the grass.
#
# Here, with the geometry as it is (positions, triangles and texture coordinates of every mesh, terrain
# heights; checked at the end):
# - normals (A): every backfill vertex takes the normal of the ground it restores, as the terrain computes
#   its own (central differences over one terrain step): the heights of the backfill on the terrain
#   vertices, of the terrain elsewhere; the vertices under a wall or lowered beside it and not covered
#   (their height is the foot of the wall) are left out and the difference is taken on the other side.
#   Where the backfill meets the visible terrain its edge takes the normal the terrain has there, so the
#   light does not jump at the seam. Vertices between the terrain vertices (where a square is cut at a
#   wall or a road) interpolate the normals of the corners of their square that the backfill covers (on
#   the edge of a square with none: the normal of the nearest backfill terrain vertex). The vertices are
#   welded again (bng.weld_corners): with one normal per position the mesh has about 40 % fewer vertices.
# - grass (C): the terrain vertices of the squares under the backfill, and those of the squares a wall
#   passes through from which the tallest grass (GRASS_TALL) would reach over the wall top there, go from
#   the layers Grass and GardenGrass to their twins GrassVerge and GardenGrassVerge (terrain.VERGE): the
#   same material, without the grass of groundcover.py, as along the roads since v2.4. At the foot of a
#   wall taller than the grass, and on the rest of the meadows (maxSlope 45 degrees), the grass stays.
# The changed files get the date of the build step (the game converts the shapes again instead of taking its
# cached ones); everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish wall_fill
# --------------------------------------------------------------------------------------------------

GRASS_TALL = max(t["sizeMax"] for c in groundcover.COVERS.values() for t in c[6])   # m, the tallest grass clump
ON_NODE = 2e-3        # m, a vertex this close to a terrain vertex (in x and y) is on it
SEAM_TOL = 0.02       # m, a backfill vertex this close to the terrain height on a terrain vertex lies on the terrain
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


def canonical(V, UV, idx):
    """The non-degenerate triangles of a part, for the check that the geometry did not change: positions
    in mm and texture coordinates in 1e-4 of their corners, every triangle starting at its smallest
    corner (keeping its winding), sorted."""
    P = np.round(V[idx[:, 0]] * 1000).astype(np.int64).reshape(-1, 3, 3)
    U = np.round(UV[idx[:, 2]] * 1e4).astype(np.int64).reshape(-1, 3, 2)
    ok = ~((P[:, 0] == P[:, 1]).all(1) | (P[:, 1] == P[:, 2]).all(1) | (P[:, 0] == P[:, 2]).all(1))
    P, U = P[ok], U[ok]
    corner = np.concatenate([P, U], 2)                                   # (k, 3, 5)
    # rank of every corner within its triangle, lexicographic over its 5 numbers
    flat = corner.reshape(-1, 5)
    order = np.lexsort(flat.T[::-1])
    rank = np.empty(len(flat), np.int64)
    rank[order] = np.arange(len(flat))
    s = np.argmin(rank.reshape(-1, 3), 1)
    ar = np.arange(len(corner))
    rot = np.stack([corner[ar, (s + j) % 3] for j in range(3)], 1)          # (k, 3, 5)
    rot = np.concatenate([rot[:, :, :3].reshape(len(rot), 9), rot[:, :, 3:].reshape(len(rot), 6)], 1)
    return rot[np.lexsort(rot.T[::-1])]                                     # 9 coordinates, then 6 texture


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
    sq = TER_SQUARE
    Ht = (Z0 + q.astype(np.float64) / 65535.0 * MAXH)
    objs = read_items(zi, f"{lv}/main/MissionGroup/walls/items.level.json")

    # ---- the backfill shapes: vertices on the terrain vertices, squares covered
    shapes = []
    fill_cells = np.zeros((n - 1, n - 1), bool)
    node_z = np.full(n * n, -np.inf)
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or "/art/shapes/walls/backfill" not in sn:
            continue
        name = sn.lstrip("/")
        text = zi.read(name).decode("utf-8")
        V, N, UV, C, parts, node = optimize_level.parse(text)
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        cf, rf = (W[:, 0] - TER_X0) / sq, (W[:, 1] - TER_Y0) / sq
        ci, ri = np.round(cf).astype(np.int64), np.round(rf).astype(np.int64)
        on = (np.abs(cf - ci) * sq < ON_NODE) & (np.abs(rf - ri) * sq < ON_NODE)
        flat = np.where(on, ri * n + ci, -1)
        np.maximum.at(node_z, flat[on], W[on, 2])
        for _, idx in parts:
            m = W[idx[:, 0]].reshape(-1, 3, 3).mean(1)
            fill_cells[np.floor((m[:, 1] - TER_Y0) / sq).astype(np.int64),
                       np.floor((m[:, 0] - TER_X0) / sq).astype(np.int64)] = True
        shapes.append(dict(name=name, V=V, N=N, UV=UV, C=C, parts=parts, node=node, W=W, flat=flat,
                           cf=cf, rf=rf))
    print("backfill: %d shapes, %d triangles, %d vertices, %d squares"
          % (len(shapes), sum(len(i) // 3 for s in shapes for _, i in s["parts"]), sum(len(s["V"]) for s in shapes),
             fill_cells.sum()), flush=True)

    # ---- (A) normals at the terrain vertices of the backfill
    is_fill = np.isfinite(node_z).reshape(n, n)
    covered = corners_of(fill_cells)
    valid = ~covered | is_fill                   # a height of the ground: the backfill's or the visible terrain's
    G = Ht.copy()
    G[is_fill] = node_z.reshape(n, n)[is_fill]
    nodes = np.flatnonzero(is_fill)
    r, c = np.divmod(nodes, n)
    rm, rp, cm, cp = np.maximum(r - 1, 0), np.minimum(r + 1, n - 1), np.maximum(c - 1, 0), np.minimum(c + 1, n - 1)

    def diff(ra, ca, rb, cb):
        va, vb = valid[ra, ca], valid[rb, cb]
        ga, gb, g0 = G[ra, ca], G[rb, cb], G[r, c]
        return np.where(va & vb, (gb - ga) / (2 * sq), np.where(vb, (gb - g0) / sq, np.where(va, (g0 - ga) / sq, 0.0)))
    nr = np.column_stack([-diff(r, cm, r, cp), -diff(rm, c, rp, c), np.ones(len(nodes))])
    # the terrain's own normal (the heights as they are, the lowered vertices too): at the seam
    nt = np.column_stack([-(Ht[r, cp] - Ht[r, cm]) / (2 * sq), -(Ht[rp, c] - Ht[rm, c]) / (2 * sq), np.ones(len(nodes))])
    open_cell = np.ones((n + 1, n + 1), bool)    # squares around a vertex, padded: True where no backfill
    open_cell[1:-1, 1:-1] = ~fill_cells
    seam = open_cell[r, c] | open_cell[r, c + 1] | open_cell[r + 1, c] | open_cell[r + 1, c + 1]
    seam &= np.abs(G[r, c] - Ht[r, c]) < SEAM_TOL
    nn = np.where(seam[:, None], nt, nr)
    nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    print("normals: %d terrain vertices of the backfill, %d of them on the seam with the terrain"
          % (len(nodes), int(seam.sum())), flush=True)

    def node_normal(flat):
        """Normals of terrain vertices (flat indices, all backfill vertices); NaN for the others."""
        j = np.searchsorted(nodes, flat)
        j = np.clip(j, 0, len(nodes) - 1)
        hit = nodes[j] == flat
        out = np.full((len(flat), 3), np.nan)
        out[hit] = nn[j[hit]]
        return out

    # ---- new DAEs: the same triangles with the new normals, welded again
    new_dae = {}
    st = dict(vertices_before=0, vertices_after=0, triangles=0, by_corner_interp=0, by_nearest_node=0)
    from scipy.spatial import cKDTree
    node_tree = cKDTree(np.column_stack([TER_X0 + c * sq, TER_Y0 + r * sq]))
    dev_face, dev_old = [], []
    tmp = tempfile.mkdtemp(prefix="wall_fill_")
    for s in shapes:
        V, W, flat = s["V"], s["W"], s["flat"]
        Nn = np.full((len(V), 3), np.nan)
        on = flat >= 0
        Nn[on] = node_normal(flat[on])
        # vertices between the terrain vertices: the corners of their square, weighted bilinearly
        off = np.flatnonzero(np.isnan(Nn[:, 0]))
        if len(off):
            c0 = np.floor(s["cf"][off]).astype(np.int64)
            r0 = np.floor(s["rf"][off]).astype(np.int64)
            fx, fy = s["cf"][off] - c0, s["rf"][off] - r0
            acc, wsum = np.zeros((len(off), 3)), np.zeros(len(off))
            for dr, dc, w in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
                k = node_normal((r0 + dr) * n + (c0 + dc))
                ok = np.isfinite(k[:, 0]) & (w > 1e-9)
                acc[ok] += w[ok, None] * k[ok]
                wsum[ok] += w[ok]
            good = wsum > 1e-6
            Nn[off[good]] = acc[good] / wsum[good, None]
            st["by_corner_interp"] += int(good.sum())
            rest = off[~good]
            if len(rest):                         # no corner of its square on the backfill (a vertex on the
                Nn[rest] = nn[node_tree.query(W[rest, :2])[1]]      # edge of the next one): the nearest one's
                st["by_nearest_node"] += len(rest)
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
        mb = bng.MeshBuilder()
        for mat, idx in s["parts"]:
            vi, ni, ti = idx[:, 0], idx[:, 1], idx[:, 2]
            col = s["C"][idx[:, 3]] if s["C"] is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[vi], uvs=s["UV"][ti], normals=Nn[vi], colors=col)
            P = W[vi].reshape(-1, 3, 3)
            fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            a = np.linalg.norm(fn, axis=1)
            fn = fn[a > 1e-9] / a[a > 1e-9, None]
            nv = Nn[vi].reshape(-1, 3, 3)[a > 1e-9]
            no = s["N"][ni].reshape(-1, 3, 3)[a > 1e-9]
            dev_face.append(np.degrees(np.arccos(np.clip((nv * fn[:, None]).sum(2), -1, 1))).ravel())
            dev_old.append(np.degrees(np.arccos(np.clip((nv * no).sum(2), -1, 1))).ravel())
            st["triangles"] += len(idx) // 3
        base, detail = re.match(r"(.*)_a(\d+)$", s["node"]).groups()
        path = os.path.join(tmp, "s.dae")
        mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
        out = open(path, encoding="utf-8").read()
        # the check: the same triangles (positions, texture coordinates), material by material; the
        # writer may move all the texture coordinates of a shape by whole tiles (bng.MeshBuilder.write_dae:
        # their mean changes with the welded vertices), which draws the same
        V2, N2, UV2, C2, parts2, node2 = optimize_level.parse(out)
        assert node2 == s["node"], (s["name"], node2)
        p1, p2 = dict(s["parts"]), dict(parts2)
        assert sorted(p1) == sorted(p2), s["name"]
        shifts = set()
        for mat in p1:
            a, b = canonical(V, s["UV"], p1[mat]), canonical(V2, UV2, p2[mat])
            assert a.shape == b.shape and (a[:, :9] == b[:, :9]).all(), (s["name"], mat)
            d = b[:, 9:] - a[:, 9:]
            assert (d == np.tile(d[:1, :2], 3)).all() and not (d[:1] % 10000).any(), (s["name"], mat)
            shifts.add(tuple(d[0, :2].tolist()) if len(d) else None)
        assert len(shifts - {None}) <= 1, s["name"]
        st["vertices_before"] += len(V)
        st["vertices_after"] += len(V2)
        new_dae[s["name"]] = out.encode("utf-8")
    os.remove(os.path.join(tmp, "s.dae"))
    os.rmdir(tmp)
    dev_face, dev_old = np.concatenate(dev_face), np.concatenate(dev_old)
    print("backfill shapes rewritten: %d, the same triangles; vertices %d -> %d" %
          (len(new_dae), st["vertices_before"], st["vertices_after"]), flush=True)
    print("normal against the face: median %.1f, 95th percentile %.1f degrees (before: flat); new against old: "
          "median %.1f, 95th percentile %.1f degrees" % (np.median(dev_face), np.percentile(dev_face, 95),
                                                         np.median(dev_old), np.percentile(dev_old, 95)), flush=True)

    # ---- (C) no game grass under the backfill, nor where it would stand over the top of a wall: on the
    # vertices of the squares a wall passes through (lowered to its foot by walls.carve_terrain) less than
    # the tallest grass under the wall top there
    wtop = wall_cells(zi, objs, n)
    wcells = np.isfinite(wtop)
    pad = np.full((n + 1, n + 1), -np.inf, np.float32)
    pad[1:-1, 1:-1] = wtop
    near_top = np.maximum(np.maximum(pad[:-1, :-1], pad[:-1, 1:]), np.maximum(pad[1:, :-1], pad[1:, 1:]))
    del pad, wtop
    under = corners_of(fill_cells)
    over = corners_of(wcells) & (Ht > near_top - GRASS_TALL) & ~under
    del near_top
    grassy = np.isin(lay, [names.index(a) for a in VERGE])
    new_lay = lay.copy()
    changed = {}
    for a, b in VERGE.items():
        ia, ib = names.index(a), names.index(b)
        m = (under | over) & (lay == ia)
        new_lay[m] = ib
        changed[f"{a} -> {b}"] = int(m.sum())
    why = {"under_backfill": int((under & grassy).sum()), "over_wall_top": int((over & grassy).sum())}
    print("terrain vertices without game grass: %s, %s (squares under the backfill %d, crossed by a wall %d)"
          % (changed, why, int(fill_cells.sum()), int(wcells.sum())), flush=True)
    assert set(np.unique(lay[new_lay != lay])) <= {names.index(a) for a in VERGE}
    new_ter = data[:5 + 2 * n * n] + new_lay.tobytes() + data[5 + 3 * n * n:]
    assert len(new_ter) == len(data) and new_ter[:5 + 2 * n * n] == data[:5 + 2 * n * n]     # heights as they were

    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm == ter_name or nm in new_dae:
                # a new date: the game converts the shapes again instead of taking its cached ones
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_ter if nm == ter_name else new_dae[nm])
            elif re.fullmatch(r"levels/[^/]+/README\.md", nm) and os.path.exists(LEVEL_README):
                zo.writestr(i, open(LEVEL_README, "rb").read(), compress_type=i.compress_type)
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    print("written in %.0f s" % (time.time() - t0), flush=True)
    if report:
        res = {"backfill_shapes": len(new_dae), "backfill_triangles": st["triangles"],
               "backfill_squares": int(fill_cells.sum()), "backfill_area_ha": round(float(fill_cells.sum()) * sq * sq / 1e4, 1),
               "vertices_before": st["vertices_before"], "vertices_after": st["vertices_after"],
               "terrain_vertices_with_normal": int(len(nodes)), "seam_vertices_terrain_normal": int(seam.sum()),
               "vertices_interpolated_in_square": st["by_corner_interp"], "vertices_nearest_node": st["by_nearest_node"],
               "normal_vs_face_deg": {"median": round(float(np.median(dev_face)), 2),
                                      "p95": round(float(np.percentile(dev_face, 95)), 2)},
               "normal_new_vs_old_deg": {"median": round(float(np.median(dev_old)), 2),
                                         "p95": round(float(np.percentile(dev_old, 95)), 2)},
               "wall_squares": int(wcells.sum()), "grass_tall_m": GRASS_TALL, "grass_removed_vertices": changed,
               "grass_removed_why": why,
               "geometry_unchanged": True, "terrain_heights_unchanged": True}
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
