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


def wall_footprints(av, skip_polys):
    out = []
    for g, p in av["SOSF"].get("muro", []):
        out.append((g, "poly", p))
    for g, p in av["SOLI"].get("muro", []):
        out.append((g.buffer(0.15, cap_style="flat", join_style="mitre"), "line", p))
    if skip_polys:
        sk = shapely.union_all(skip_polys)
        out = [(g, k, p) for g, k, p in out if g.intersection(sk).area < 0.5 * g.area]
    return out


def polygons(g):
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [x for x in getattr(g, "geoms", []) if isinstance(x, Polygon)]


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
    for wi, (g, kind, props) in enumerate(wall_footprints(ctx["av"], ctx["mauer"])):
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
            if ctx["rw_zone"] is not None and poly.intersection(ctx["rw_zone"]).area > 0.5 * poly.area:
                continue                                  # replaced by a photo-verified roadside wall
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
    n_tri = 0
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
        if dtree is not None:
            roads_here = dtree.query(cell, predicate="intersects")
            if len(roads_here):
                cut = cut.difference(shapely.union_all([drivable[i] for i in roads_here]).buffer(0.02))
        if cut.is_empty or cut.area < 0.01:
            continue
        pieces = [g for g in getattr(cut, "geoms", [cut]) if g.geom_type == "Polygon" and g.area >= 0.01]
        if len(walls_here):                              # only the pieces on the high side of the wall
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
        V = np.column_stack([V2, Z]).reshape(-1, 3, 3)
        up = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])[:, 2] < 0
        V[up] = V[up][:, ::-1]                           # counter-clockwise from above
        mat = "mp_fill_" + names[int(layers[r, c])].lower()
        key = (int(np.floor(X0 / CHUNK)), int(np.floor(Y0 / CHUNK)))
        mb = builders.setdefault(key, {}).setdefault(mat, [])
        mb.append(V.reshape(-1, 3))
        n_tri += len(V)
    for (tx, ty), mats in sorted(builders.items()):
        mb = bng.MeshBuilder()
        for mat, parts in mats.items():
            T = np.concatenate(parts)
            mb.add(mat, T, uvs=T[:, :2] / 4.0, normals=bng.flat_normals_soup(T))
        rel = f"art/shapes/walls/backfill_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="backfill", origin=origin)
        scene.add("MissionGroup/walls", bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=True,
                                                     decal=False))
    print("backfill behind the walls: %d squares, %d triangles, %d chunks" % (len(cells), n_tri, len(builders)))
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
