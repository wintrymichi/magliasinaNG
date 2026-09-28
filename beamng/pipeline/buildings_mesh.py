"""Building meshes from swissBUILDINGS3D 3.0 (LOD2), grouped into 256 m tiles.

Facades seen in the Street View panoramas carry their projected photo texture
(texture_buildings.py -> work/facades, packed here into 4096 px atlases). All other
walls use a neutral plaster texture tinted (vertex colour) with the building's own
photographed facade colour, or a neutral plaster tone when the building was never
photographed. Roofs use a neutral clay-tile texture laid along the roof slope, tinted
with the median SWISSIMAGE colour of that roof (footprint eroded 1.5 m against relief
displacement). Collision on (visible mesh).
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
from config import NO_PHOTO, WORK, BEAMNG_GAME

TILE = 256.0
DEFAULT_WALL = np.array([0.84, 0.80, 0.72])


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


def neutral_texture(src_zip_path, dst, gain=0.95):
    """Grey-normalised copy of a vanilla texture (keeps pattern, colour comes from vertex colours)."""
    import zipfile, io
    p = src_zip_path.lstrip("/")
    if p.startswith("levels/"):
        z = zipfile.ZipFile(os.path.join(BEAMNG_GAME, "content", "levels", p.split("/")[1] + ".zip"))
    else:
        z = zipfile.ZipFile(os.path.join(BEAMNG_GAME, "content", "assets", "materials", "trim.zip"))
    names = {n.lower(): n for n in z.namelist()}
    im = np.asarray(Image.open(io.BytesIO(z.read(names[p.lower()]))).convert("RGB")).astype(np.float32)
    g = im.mean(-1, keepdims=True)
    g = g / max(g.mean(), 1) * 255 * gain
    out = np.clip(np.repeat(g, 3, -1), 0, 255).astype(np.uint8)
    Image.fromarray(out).save(dst)


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
        zt = float(S[near, 2].max()) + PASSAGE_CLEAR[kind]
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


def build(level_dir, level_name, keep=None, ways=None):
    """ways: network_ways, the passages to cut."""
    import texturing
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    shp_dir = os.path.join(level_dir, "art", "shapes", "buildings")
    os.makedirs(shp_dir, exist_ok=True)
    import vanilla
    v1_walls = None
    if vanilla.have_game():
        neutral_texture("/assets/materials/trim/plaster/t_highrise_plaster/t_highrise_plaster_b.color.dds",
                        os.path.join(shp_dir, "t_plaster_neutral.png"))
        neutral_texture("/levels/italy/art/shapes/buildings/Italy_bld_roof_tiles_d.dds",
                        os.path.join(shp_dir, "t_rooftiles_neutral.png"), gain=1.0)
    else:                    # the grey copies of the released level, and its measured facade tones
        for f in ("t_plaster_neutral.png", "t_rooftiles_neutral.png"):
            vanilla.copy(f"art/shapes/buildings/{f}", os.path.join(shp_dir, f))
        from scipy.spatial import cKDTree
        wp, wc = vanilla.wall_colors()
        v1_walls = (cKDTree(wp), wc) if len(wp) else None
    L = f"/levels/{level_name}/art/shapes/buildings"
    rcol = roof_colors(blds)
    atlas = texturing.Atlas(4096)
    tiles = {}
    for b in blds:
        if keep is not None and not keep(b):
            continue
        c = (np.array(b["bbox"][0]) + np.array(b["bbox"][1])) / 2
        tiles.setdefault((int(np.floor(c[0] / TILE)), int(np.floor(c[1] / TILE))), []).append(b)
    out, n_photo, n_pass = [], 0, 0
    wtree = shapely.STRtree([w[1] for w in ways]) if ways else None
    for (tx, ty), bl in sorted(tiles.items()):
        mb = bng.MeshBuilder()
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        for b in bl:
            ob = orient(b)
            walls, roofs = ob["walls"], ob["roofs"]
            assigned = np.zeros(len(walls), bool)
            wall_col = DEFAULT_WALL
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
            rest = walls[~assigned]
            rest, roofs, shell = passages(b, rest, roofs, ways, wtree)
            if len(shell):
                rest = np.concatenate([rest, shell])
                n_pass += 1
            if len(rest):
                V = rest.reshape(-1, 3)
                stored = np.clip(wall_col / 0.9, 0, 1)
                if v1_walls is not None and not os.path.exists(f):
                    dd, jj = v1_walls[0].query(V[::3][:50])
                    if (dd < 0.05).mean() > 0.5:           # the same building in the released level
                        stored = np.median(v1_walls[1][jj[dd < 0.05]], 0)
                mb.add("bld_plaster", V, uvs=wall_uvs(rest) / 2.5, normals=bng.flat_normals_soup(V),
                       colors=np.r_[stored, 1.0])
            if len(roofs):
                V = roofs.reshape(-1, 3)
                col = rcol.get(b["uuid"], np.array([0.55, 0.42, 0.36]))
                mb.add("bld_roof", V, uvs=roof_uvs(roofs), normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(col / 0.85, 0, 1), 1.0])
        if mb.empty():
            continue
        rel = f"art/shapes/buildings/bld_{tx:+03d}_{ty:+03d}.dae"
        mb.write_dae(os.path.join(level_dir, rel), name="bld", origin=origin)
        out.append((f"/levels/{level_name}/{rel}", origin, mb.triangle_count()))
    mats = [bng.material("bld_plaster", f"{L}/t_plaster_neutral.png", roughness=0.9, vert_color=True),
            bng.material("bld_roof", f"{L}/t_rooftiles_neutral.png", roughness=0.8, vert_color=True)]
    for i, page in enumerate(atlas.pages if n_photo else []):     # no empty page without photo facades
        rel = f"art/shapes/buildings/bld_photo_{i}.jpg"
        cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        mats.append(bng.material(f"mp_bld_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.85))
    bng.write_materials(os.path.join(shp_dir, "main.materials.json"), mats)
    print("building photo facades", n_photo, "atlas pages", len(atlas.pages) if n_photo else 0,
          "buildings with a passage", n_pass)
    return out
