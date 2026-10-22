"""Posts under the roofs that still hang in the air (v3.1).

buildings_mesh gives the roofs without walls of swissBUILDINGS3D their posts (canopy) and the closed ones their walls
(close_roofs). The v3.1 test build still had roofs over nothing, of two kinds:
- the Flugdach records of swissBUILDINGS3D (the platform canopies of the stations of Magliaso and Caslano, the
  forecourt roof of the fuel station at Magliaso, one at Sessa): the survey draws them as a slab whose four "walls"
  are its 10 cm edges, so buildings_mesh took them for buildings with walls and gave them no posts (all 5 roofs
  check_level counted as floating);
- the parts of a house's roof that reach far out over a porch, a lean-to or a carport beside the house: swissBUILDINGS3D
  keeps them in the record of the house, with no wall under them; the soffits close them from below, nothing holds
  them up (a slab several metres out from a hut in a field, a roof along a yellow house). check_level could not see
  them, the house's walls touch the roof.
Here, on the built level, the roof plan of every building (its roof faces joined where they touch) minus what holds
it: FREE_WALL m around every tall face of the buildings (a wall, the walls of the house) and FREE_POST m around the
short ones (posts: buildings_mesh puts them POST_STEP m apart). What is left at the edge of the roof (a piece of at
least FREE_MIN m2 touching its outline, more than POST_MIN m over the ground) gets posts like the canopies: at the
corners of the overhanging part of the roof, POST_INSET m in, and every POST_STEP m along it, none within POST_ATTACH m
of a wall or a post (the house carries that side; no post doubled) nor on the carriageway of a road or path or on the
railway (KEEP_RAIL m round its faces), and off the sidewalks, yards and parking unless that leaves none. Where the
carriageway and the railway leave no post, the posts move off them (at most SNAP m), under the roof. The posts stand
POST_SINK m in the ground and end under the roof's underside (the rims of roof_details are outside them); they are
part of the building shapes, so cars collide with them.
A finishing step of build_level.py (FINISH, after roof_details); only triangles are added to the building shapes:
    python build_level.py --finish roof_posts
"""
import json, os, re, tempfile, time, zipfile
import numpy as np
import shapely
import bng
import optimize_level
import road_mesh
from config import LEVEL_NAME
from lamps import read_items, faces

FREE_WALL = 1.8          # m round a wall face: what a roof reaches out over a wall is eaves (the soffits; the
                         # eaves of the stone roofs and the lake-side houses reach out up to 1.5 m)
FREE_POST = 3.0          # m round a post (a tall face shorter than POST_FACE m along the ground)
POST_FACE = 0.5
TALL = 0.35              # m: a face this high or more holds the roof (walls between the windows, posts; not the
                         # fascias of roof_details, 0.27 m, nor the 10 cm edges of a slab)
ROOF_GAP = 0.6           # m: the face reaches this much under the roof's eaves (not the 10 cm edge of a slab)
FREE_MIN = 2.0           # m2
EDGE = 0.3               # m from the outline of the roof: a piece left there hangs out
POST_MIN = 0.6           # m of the roof over the ground (buildings_mesh.POST_MIN)
POST_INSET = 0.30
POST_STEP = 5.0
POST_SINK = 0.5
POST_ATTACH = 1.0
POST_W = 0.20
POST_TONE = np.array([0.50, 0.50, 0.49])
KEEP_RAIL = 1.5          # m round the faces of the railway (rails, sleepers, ballast)
SNAP = 2.0               # m a post may move off the carriageway
HARD = re.compile(r"^mp_(road_(?!wall)|path_|bridge_(?!parapet))")       # carriageways: never a post
SOFT = re.compile(r"^mp_(sidewalk|hard_|parking)")    # sidewalks, yards, parking: a post only where none stands else
NEAR_ROAD = 2.0          # m: the posts this close to a carriageway are counted in the report


def _polys(g):
    return [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and q.area > 1e-5]


def _post(c, z0, z1, w=POST_W):
    """The four sides (8, 3, 3) of a square post centred on c from z0 to z1 (buildings_mesh._post)."""
    h = w / 2
    q = np.array([[-h, -h], [h, -h], [h, h], [-h, h]]) + c
    out = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        A0, B0, A1, B1 = [a[0], a[1], z0], [b[0], b[1], z0], [a[0], a[1], z1], [b[0], b[1], z1]
        out += [[A0, B0, B1], [A0, B1, A1]]
    return np.array(out)


def _ring_points(g):
    """Points along the rings of g, POST_INSET m in: its corners and every POST_STEP m."""
    pts = []
    for poly in _polys(g):
        for r in _polys(poly.buffer(-POST_INSET, join_style="mitre").simplify(0.3)):
            c = np.asarray(r.exterior.coords)[:-1]
            for i in range(len(c)):
                a, b = c[i], c[(i + 1) % len(c)]
                n = max(int(np.ceil(np.linalg.norm(b - a) / POST_STEP)), 1)
                pts += [a + (b - a) * k / n for k in range(n)]
        if not pts:                                     # narrower than two insets
            pts.append(np.asarray(poly.representative_point().coords[0]))
    return np.array(pts).reshape(-1, 2)


def post_color(zi, lv):
    """RGBA vertex colour of the posts (buildings_mesh: POST_TONE over the mean colour of the plaster texture)."""
    mean = np.array([0.5, 0.5, 0.5])
    tex = f"{lv}/art/shapes/buildings/t_bld_plaster_b.color.png"
    if tex in zi.NameToInfo:                              # the vertex colour multiplies the texture (bld_textures)
        import io
        from PIL import Image
        mean = np.asarray(Image.open(io.BytesIO(zi.read(tex))).convert("RGB"), np.float64).reshape(-1, 3).mean(0) / 255
    return np.r_[np.clip(POST_TONE / mean, 0, 1), 1.0]


class Level:
    """The building faces of the level (world coordinates), the terrain, the carriageways and the railway."""

    def __init__(self, zi, lv):
        import network_mesh as pu
        import walls as pw
        blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
                   if o.get("class") == "TerrainBlock")
        pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
        self.pu, self.q = pu, pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))[1]
        self.shapes = []                # (shape name, position, roof faces (k, 3, 3)) of the buildings group
        roofs, held, posts = [], [], []
        pc = post_color(zi, lv)
        for g in ("buildings", "buildings/details", "buildings/extras"):
            f = f"{lv}/main/MissionGroup/{g}/items.level.json"
            if f not in zi.NameToInfo:
                continue
            for o in read_items(zi, f):
                sn = o.get("shapeName", "").lstrip("/")
                if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or not sn.endswith(".dae"):
                    continue
                pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
                V, _, _, C, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
                W = V + pos
                r = []
                for mat, idx in parts:
                    t = W[idx[:, 0]].reshape(-1, 3, 3)
                    if mat.startswith("bld_roof"):
                        r.append(t)
                        continue
                    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                    vert = np.abs(n[:, 2]) < 0.3 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
                    tall = (t[:, :, 2].max(1) - t[:, :, 2].min(1)) >= TALL
                    held.append(t[vert & tall])
                    if mat == "bld_plaster" and C is not None and idx.shape[1] > 3:     # the posts of the canopies
                        k = (np.abs(C[idx[:, 3]] - pc).max(1) < 0.02).reshape(-1, 3).all(1)
                        posts.append(t[k].mean(1)[:, :2])
                r = np.concatenate(r) if r else np.zeros((0, 3, 3))
                roofs.append(r)
                if g == "buildings":
                    self.shapes.append((sn, pos, r))
        self.R = np.concatenate(roofs) if roofs else np.zeros((0, 3, 3))
        self.H = np.concatenate(held) if held else np.zeros((0, 3, 3))
        P = np.concatenate(posts) if posts else np.zeros((0, 2))
        self.ptree = shapely.STRtree(shapely.points(P)) if len(P) else None
        self.n_post_faces = len(P)
        none = [np.zeros((0, 3, 3))]
        road = faces(zi, lv, ["roads/surfaces"])
        self.hard = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if HARD.match(m)] or none))
        self.soft = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if SOFT.match(m)] or none))
        rail = faces(zi, lv, ["railway"])
        self.rail = road_mesh.TriSurface(np.concatenate(list(rail.values()) or none))
        self.roof = road_mesh.TriSurface(self.R) if len(self.R) else None
        lines = shapely.linestrings(self.H[:, :, :2]) if len(self.H) else []
        self.htree = shapely.STRtree(lines) if len(self.H) else None
        self.hlines = lines
        self.hlen = shapely.length(lines) if len(self.H) else np.zeros(0)

    def ground(self, x, y):
        return self.pu.terrain_top(self.q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))

    def on(self, surf, P, r=POST_W):
        """(n,) True where a post at P (n, 2) would stand on the faces of surf (within r m)."""
        hit = np.zeros(len(P), bool)
        for dx, dy in [(0, 0)] + [(np.cos(a) * r, np.sin(a) * r) for a in np.arange(8) * np.pi / 4]:
            hit |= ~np.isnan(surf.height(P[:, 0] + dx, P[:, 1] + dy))
        return hit

    def on_hard(self, P):
        """(n,) True where a post at P (n, 2) would stand on a carriageway or near the railway."""
        hit = self.on(self.hard, P)
        for a in np.arange(8) * np.pi / 4:
            for d in (0.0, KEEP_RAIL / 2, KEEP_RAIL):
                hit |= ~np.isnan(self.rail.height(P[:, 0] + d * np.cos(a), P[:, 1] + d * np.sin(a)))
        return hit


def unheld(L, roofs):
    """[(piece, part of the roof over it, eaves)] of the roof faces of one shape (k, 3, 3) that nothing holds."""
    polys = shapely.polygons(np.concatenate([roofs[:, :, :2], roofs[:, :1, :2]], 1))
    ok = shapely.area(polys) > 1e-4
    if not ok.any():
        return []
    U = shapely.union_all(shapely.buffer(polys[ok], 0.15, join_style="mitre"))
    rt = shapely.STRtree(polys)
    out = []
    for c in _polys(U):
        if c.area < FREE_MIN:
            continue
        if L.ptree is not None and len(L.ptree.query(c, predicate="intersects")):
            continue                    # on posts already (buildings_mesh.canopy, or a build that ran this step)
        eave = float(roofs[rt.query(c, predicate="intersects")][:, :, 2].min())
        near = L.htree.query(c.buffer(FREE_POST), predicate="intersects") if L.htree is not None else []
        near = [i for i in near if L.H[i][:, 2].min() < eave - ROOF_GAP]          # not the edge of a slab
        if near:
            hold = shapely.union_all([L.hlines[i].buffer(FREE_POST if L.hlen[i] < POST_FACE else FREE_WALL)
                                      for i in near])
            free = c.difference(hold)
        else:
            free = c
        edge = c.exterior.buffer(EDGE)
        for p in _polys(free):
            if p.area < FREE_MIN or not p.intersects(edge):
                continue
            depth = FREE_WALL
            if near:
                Q = np.asarray(p.exterior.coords)
                depth += float(shapely.distance(hold, shapely.points(Q)).max())
            out.append((p, c.intersection(p.buffer(FREE_WALL + 0.2)), eave, near, depth))
    return out


def posts_for(L, piece, part, near):
    """Posts (m, 3, 3) under the part of a roof over the piece nothing holds; (posts, snapped)."""
    pts = _ring_points(part)
    if not len(pts):
        return np.zeros((0, 3, 3)), 0
    if near:                            # none beside a wall (the house carries that side) nor beside a post
        wt = shapely.STRtree([L.hlines[i] for i in near])
        far = np.array([not len(wt.query(shapely.Point(p), predicate="dwithin", distance=POST_ATTACH)) for p in pts])
        pts = pts[far]
    if not len(pts):
        return np.zeros((0, 3, 3)), 0
    bad = L.on_hard(pts)
    snapped = 0
    if bad.all():                       # move them off the carriageway, under the roof
        inner = part.buffer(-POST_INSET)
        moved = []
        for p in pts:
            for d in np.arange(0.25, SNAP + 1e-6, 0.25):
                cand = p + d * np.stack([np.cos(np.arange(16) * np.pi / 8), np.sin(np.arange(16) * np.pi / 8)], 1)
                cand = cand[shapely.contains_xy(inner, cand[:, 0], cand[:, 1])]
                if len(cand):
                    cand = cand[~L.on_hard(cand)]
                if len(cand):
                    moved.append(cand[0])
                    break
        pts = np.array(moved).reshape(-1, 2)
        snapped = len(pts)
    else:
        pts = pts[~bad]
        soft = L.on(L.soft, pts)
        if not soft.all():              # off the sidewalks and yards unless that leaves none
            pts = pts[~soft]
    out = []
    for p in pts:
        top = float(L.roof.height(p[0:1], p[1:2], mode="low")[0]) if L.roof is not None else np.nan
        if not np.isfinite(top):
            continue
        g = float(L.ground(p[0:1], p[1:2])[0])
        if top - g < POST_MIN:
            continue
        out.append(_post(p, g - POST_SINK, top - 0.02))
    return (np.concatenate(out) if out else np.zeros((0, 3, 3))), snapped


def roof_posts_step(root, report=None):
    """The posts under the roofs of the building shapes that nothing holds (only triangles are added)."""
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    L = Level(zi, lv)
    print("roof posts: level read, %d roof faces, %d tall faces, %d post faces (%.0f s)" % (len(L.R), len(L.H), L.n_post_faces, time.time() - t0),
          flush=True)
    col = post_color(zi, lv)
    res = {"roofs_unheld": 0, "roofs_with_posts": 0, "roofs_without_posts": 0, "posts": 0, "posts_snapped": 0, "posts_near_road": 0, "posts_on_soft": 0,
           "depth_hist_m": {},
           "unheld_m2": 0.0, "places": []}
    new_dae = {}
    tmp = tempfile.mkdtemp()
    for sn, pos, roofs in L.shapes:
        if not len(roofs):
            continue
        add = []
        for piece, part, eave, near, depth in unheld(L, roofs):
            P = np.asarray(piece.exterior.coords)
            if eave - float(L.ground(P[:, 0], P[:, 1]).max()) < POST_MIN:       # a roof on the ground
                continue
            res["roofs_unheld"] += 1
            res["unheld_m2"] += piece.area
            posts, snapped = posts_for(L, piece, part, near)
            c = piece.centroid
            res["places"].append({"x": round(c.x, 1), "y": round(c.y, 1), "m2": round(piece.area, 1),
                                  "depth_m": round(depth, 1), "posts": len(posts) // 8})
            if len(posts):
                feet = posts.reshape(-1, 8, 3, 3)[:, :, :, :2].mean((1, 2))
                res["posts_near_road"] += int(L.on(L.hard, feet, NEAR_ROAD).sum())
                res["posts_on_soft"] += int(L.on(L.soft, feet).sum())
                d = min(int(depth), 10)
                res["depth_hist_m"][d] = res["depth_hist_m"].get(d, 0) + 1
            if len(posts):
                res["roofs_with_posts"] += 1
                res["posts"] += len(posts) // 8
                res["posts_snapped"] += snapped
                add.append(posts)
            else:
                res["roofs_without_posts"] += 1
        if not add:
            continue
        text = zi.read(sn).decode("utf-8")
        V, N, UV, C, parts, node = optimize_level.parse(text)
        mb = bng.MeshBuilder()
        for mat, idx in parts:
            cc = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[idx[:, 0]], uvs=UV[idx[:, 2]], normals=N[idx[:, 1]], colors=cc)
        T = np.concatenate(add) - pos
        W = T.reshape(-1, 3)
        mb.add("bld_plaster", W, uvs=np.column_stack([W[:, 0] + W[:, 1], W[:, 2]]) / 5.0,
               normals=bng.flat_normals_soup(W), colors=col)
        base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
        path = os.path.join(tmp, "s.dae")
        mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
        new_dae[sn] = open(path, "rb").read()
        os.remove(path)
    os.rmdir(tmp)
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new_dae:
                ni = zipfile.ZipInfo(i.filename, now)          # a new date: the game converts the shape again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    res["shapes_rewritten"] = len(new_dae)
    res["unheld_m2"] = round(res["unheld_m2"])
    res["seconds"] = round(time.time() - t0)
    print("roof posts:", {k: v for k, v in res.items() if k != "places"}, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res
