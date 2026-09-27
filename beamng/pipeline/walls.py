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
show no wall above the road (wall_caps.py: the LiDAR crest caught guardrails and shrubs). Output meshes: prism sides + triangulated top, per 128 m chunk.
Also returns a terrain carve (vertices on the low side within 1.1 m drop to the
wall base) so no slope pokes out of the wall face.
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
PIECE = 3800          # px: longest photo-texture piece of a wall (atlas pages are 4096 px)


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
    lid = np.load(os.path.join(WORK, "lidar_near.npz"))
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
    return dict(av=av, mauer=mauer, dtm=dtm, dmin=minimum_filter(dtm.a, size=k), dmax=maximum_filter(dtm.a, size=k),
                LP=LP, LZ=lid["z"][nonveg], tree=cKDTree(LP), rw_zone=rw_zone, caps=caps)


def wall_geometry(ctx=None):
    """Yield every cadastral wall polygon with its per-vertex base/top heights (see module doc)."""
    ctx = ctx or _context()
    dtm = ctx["dtm"]

    def samp(a, x, y):
        r, c = dtm.rc(x, y)
        return map_coordinates(a, [r, c], order=1, mode="nearest")
    import json as _json
    road = shapely.LineString(np.load(os.path.join(WORK, "road_profile.npz"))["center"])
    for wi, (g, kind, props) in enumerate(wall_footprints(ctx["av"], ctx["mauer"])):
        for pj, poly in enumerate(polygons(g)):
            if poly.area < 0.05:
                continue
            if ctx["rw_zone"] is not None and poly.intersection(ctx["rw_zone"]).area > 0.5 * poly.area:
                continue                                  # replaced by a photo-verified roadside wall
            # fine vertex spacing where the walls are seen from the road, coarse far away
            step = 0.5 if poly.distance(road) < 60 else 2.0
            poly = shapely.segmentize(shapely.geometry.polygon.orient(poly, 1.0), step)
            rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(r.coords)[:-1] for r in poly.interiors]
            allv = np.concatenate(rings)
            zlo = samp(ctx["dmin"], allv[:, 0], allv[:, 1])
            zhi = samp(ctx["dmax"], allv[:, 0], allv[:, 1])
            crest = np.full(len(allv), -1e9)
            inner = poly.buffer(0.05)
            idx = ctx["tree"].query_ball_point(allv, r=0.6)
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
            yield dict(key=f"w{wi}_{pj}", poly=poly, rings=rings, allv=allv, zlo=zlo, ztop=ztop,
                       zbot=zlo - 0.4, samp=samp, dmax=ctx["dmax"])


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


def build(level_dir, level_name, scene, material="mp_wall_stone"):
    import cv2
    import texturing
    builders = {}
    carve = []
    nwall = ntex = 0
    atlas = texturing.Atlas(4096)
    for w in wall_geometry():
        poly, rings, allv, zbot, ztop, zlo = w["poly"], w["rings"], w["allv"], w["zbot"], w["ztop"], w["zlo"]
        samp, dmax = w["samp"], w["dmax"]
        key = {tuple(np.round(v, 3)): (b, t) for v, b, t in zip(allv, zbot, ztop)}
        cx, cy = poly.centroid.x, poly.centroid.y
        ck = (int(np.floor(cx / CHUNK)), int(np.floor(cy / CHUNK)))
        mb = builders.setdefault(ck, bng.MeshBuilder())
        tex = None
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
                mb.add(material, tris, uvs=np.column_stack([U, tris[:, 2]]) / 1.6,
                       normals=bng.flat_normals_soup(tris))
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
            mb.add(material + "_top", top, uvs=top[:, :2] / 1.6, normals=bng.flat_normals_soup(top))
        carve.append(np.column_stack([allv, zlo, ztop]))
        nwall += 1
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/walls/walls_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="walls", origin=origin)
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
    return np.concatenate(carve) if carve else np.zeros((0, 4))


def carve_terrain(samples, xs, ys, H, radius=1.1):
    """Terrain vertices within `radius` of a wall that lie below the wall's mid height
    are lowered to the local wall base, so the terrain slope does not stick out of the face."""
    if len(samples) == 0:
        return H
    tree = cKDTree(samples[:, :2])
    X, Y = np.meshgrid(xs, ys)
    pts = np.column_stack([X.ravel(), Y.ravel()])
    d, j = tree.query(pts, k=1, distance_upper_bound=radius)
    ok = np.isfinite(d)
    Hf = H.ravel().copy()
    zlo = samples[j[ok], 2]
    zmid = 0.5 * (samples[j[ok], 2] + samples[j[ok], 3])
    low_side = Hf[ok] < zmid
    idx = np.where(ok)[0][low_side]
    Hf[idx] = np.minimum(Hf[idx], zlo[low_side] - 0.02)
    return Hf.reshape(H.shape)


def build_roadside(level_dir, level_name, scene, material="mp_wall_stone", thick=1.5, photo=True):
    """Retaining walls detected along the route (roadside_walls.json): vertical face from
    0.3 m below road level to the measured top, capped (1.5 m) over the terrain step.
    The face is textured from the panoramas (texturing.texture_ribbon)."""
    import json
    import cv2
    runs = json.load(open(os.path.join(WORK, "roadside_walls.json")))
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
        zb, zt = P[:, 2] - 0.3, P[:, 3]
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
        mat, uv = material, np.column_stack([uu, tri[:, 2]]) / 1.6
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
        mb.add(material + "_top", cap, uvs=cap[:, :2] / 1.6, normals=bng.flat_normals_soup(cap))
        for k in range(len(P)):
            samples.append([face[k, 0], face[k, 1], away[k, 0], away[k, 1], P[k, 2], P[k, 3]])
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
        mb.write_dae(os.path.join(level_dir, rel), name="rwall", origin=origin)
        scene.add("MissionGroup/walls", bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=True, decal=False))
    print("roadside walls", len(runs), "chunks", len(builders), "atlas pages", len(atlas.pages) if atlas else 0)
    return np.array(samples)


def adjust_terrain_roadside(samples, xs, ys, H, behind=2.8, front=1.6, hidden=1.0):
    """In front of a roadside wall the terrain drops to the wall base (road level),
    behind it (up to 2.2 m) it rises to the wall top: the DTM smears walls into slopes."""
    if len(samples) == 0:
        return H
    tree = cKDTree(samples[:, :2])
    X, Y = np.meshgrid(xs, ys)
    pts = np.column_stack([X.ravel(), Y.ravel()])
    d, j = tree.query(pts, k=1, distance_upper_bound=max(behind, front) + 0.5)
    ok = np.isfinite(d)
    Hf = H.ravel().copy()
    idx = np.where(ok)[0]
    S = samples[j[ok]]
    off = ((pts[idx] - S[:, :2]) * S[:, 2:4]).sum(1)          # + behind the face, - in front
    # vertices up to `hidden` m behind the face stay at road level (under the 1.5 m wide cap),
    # further back they rise to the crest: the terrain step is always hidden by the wall
    fr = (off < hidden) & (off > -front)
    bh = (off >= hidden) & (off <= behind)
    Hf[idx[fr]] = np.minimum(Hf[idx[fr]], S[fr, 4] - 0.02)
    Hf[idx[bh]] = np.maximum(Hf[idx[bh]], S[bh, 5] - 0.05)
    return Hf.reshape(H.shape)
