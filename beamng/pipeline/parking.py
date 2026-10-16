"""Parking spots for the game's parked cars (v3.1), in the built level.

Up to v3.0 the car parks of the map were empty asphalt: the game fills a level with parked cars (the "parked
vehicles" of its traffic) only on the parking spots of the level's city.sites.json, and the level had none.
Here every car park OpenStreetMap records on the map (amenity=parking: surface, street side, lane, or no kind
given; not underground, multi-storey or on a roof, whose decks the map does not have) and every single
parking space (amenity=parking_space) gets spots:
- a space mapped on its own: one spot, along its long side;
- a car park narrower than PARALLEL_MAX m (a strip along a street): one row of spots end to end along it,
  PARALLEL_LEN m each;
- a wider one: rows of spots across its long axis, SPOT_W m wide and SPOT_LEN m deep, in pairs back to back
  with an aisle of AISLE m between the pairs (as a car park is painted).
A spot is kept only inside its car park (EDGE m in from its outline), never on an AI road's lane (LANE_CLEAR m
beyond its half width), never on a building, a wall or a lamp post, and only on ground that is level enough
(MAX_TILT across the spot); its height that of the paved surface there, else the terrain. The spots go into
levels/<level>/city.sites.json as the vanilla levels have them (single spots, a probability each), where the
game's traffic finds them: with parked vehicles on in the traffic settings, it puts cars in the spots near the
player and moves them along as the player drives.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish parking
"""
import json, math, os, time, zipfile
import numpy as np
import shapely
from scipy.spatial import cKDTree
import bng
import osm
from config import LEVEL_NAME
from markings_net import read_items, shape_tris, up_faces
from road_mesh import TriSurface

KINDS = (None, "surface", "street_side", "lane", "layby", "sheds", "carports")   # amenity=parking kept
SPOT_W, SPOT_LEN, AISLE = 2.5, 5.0, 6.0     # m
PARALLEL_MAX = 4.2                          # m: narrower car parks are one row along their length
PARALLEL_LEN = 6.0                          # m of kerb per car parked along a street
EDGE = 0.2                                  # m in from the outline of the car park
LANE_CLEAR = 0.5                            # m beyond the half width of an AI road
OBST_GROUPS = ("buildings", "walls")        # MissionGroup groups whose meshes no spot may overlap
PROP_GROUPS = ("street_lights", "street_life", "osm/furniture", "country_poles", "fuel")
SHAPE_REACH = 300.0                         # m: the farthest a mesh reaches from its tile's origin
OBST_STEP = 0.4                             # m between the samples of their vertical faces
MAX_TILT = 0.12                             # rise over run across a spot at most
PROBABILITY = 0.6                           # of a spot being taken when the game fills the spots near the player
MIN_AREA = 25.0                             # m2: smaller car parks are left out
SITES = "city.sites.json"


def spot_rects(poly):
    """[(centre (2,), unit direction of the car's length (2,), length, width)] of the spots of a car park."""
    rect = poly.minimum_rotated_rectangle
    if rect.geom_type != "Polygon":
        return []
    R = np.asarray(rect.exterior.coords)[:4]
    e0, e1 = R[1] - R[0], R[2] - R[1]
    if np.hypot(*e0) < np.hypot(*e1):
        R = np.roll(R, -1, axis=0)
        e0, e1 = R[1] - R[0], R[2] - R[1]
    L, W = float(np.hypot(*e0)), float(np.hypot(*e1))
    u, v = e0 / max(L, 1e-9), e1 / max(W, 1e-9)              # u: the long axis, v: across
    out = []
    if W < PARALLEL_MAX:                                     # a strip along a street: end to end
        n = int((L - 2 * EDGE) // PARALLEL_LEN)
        s0 = (L - n * PARALLEL_LEN) / 2
        for k in range(n):
            out.append((R[0] + u * (s0 + (k + 0.5) * PARALLEL_LEN) + v * W / 2, u, PARALLEL_LEN - 0.6, 2.2))
        return out
    # rows across the long axis: spot, spot, aisle, spot, spot, aisle, ... from one long side
    offs, o = [], EDGE
    while o + SPOT_LEN <= W - EDGE + 1e-6:
        offs.append(o + SPOT_LEN / 2)
        o += SPOT_LEN
        if len(offs) % 2 == 0:
            o += AISLE
    n = int((L - 2 * EDGE) // SPOT_W)
    s0 = (L - n * SPOT_W) / 2
    for i, off in enumerate(offs):
        d = v if i % 2 == 0 else -v                          # the cars of a pair face the aisle between them
        for k in range(n):
            out.append((R[0] + u * (s0 + (k + 0.5) * SPOT_W) + v * off, d, SPOT_LEN - 0.4, SPOT_W - 0.3))
    return out


def spot_poly(c, d, length, width):
    n = np.array([-d[1], d[0]])
    return shapely.Polygon([c + d * a * length / 2 + n * b * width / 2 for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1))])


def quat_z(d):
    """Quaternion [x, y, z, w] of the turn about z that takes the local y axis to the direction d."""
    th = math.atan2(-d[0], d[1])
    return [0.0, 0.0, math.sin(th / 2), math.cos(th / 2)]


class Ground:
    """Height of the paved surfaces of the level, else of the terrain, at points (x, y)."""

    def __init__(self, zi, lv):
        import walls as pw
        blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
                   if o.get("class") == "TerrainBlock")
        self.z0, self.maxh = float(blk["position"][2]), float(blk["maxHeight"])
        self.x0, self.y0, self.sq = float(blk["position"][0]), float(blk["position"][1]), float(blk.get("squareSize", 1.0))
        self.n, self.q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
        surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
        self.S = TriSurface(np.concatenate([up_faces(t) for t in surf.values()]))

    def terrain(self, x, y):
        c = np.clip((np.asarray(x) - self.x0) / self.sq, 0, self.n - 1.001)
        r = np.clip((np.asarray(y) - self.y0) / self.sq, 0, self.n - 1.001)
        c0, r0 = c.astype(int), r.astype(int)
        fc, fr = c - c0, r - r0
        q = self.q.astype(np.float64)
        h = (q[r0, c0] * (1 - fc) * (1 - fr) + q[r0, c0 + 1] * fc * (1 - fr) + q[r0 + 1, c0] * (1 - fc) * fr
             + q[r0 + 1, c0 + 1] * fc * fr)
        return self.z0 + h / 65535.0 * self.maxh

    def height(self, x, y):
        zt = self.terrain(x, y)
        zs = self.S.height(x, y, "near", zhint=zt)
        return np.where(np.isfinite(zs) & (np.abs(zs - zt) < 1.5), zs, zt)


def obstacles(zi, lv, near_pts, near_r):
    """(tree of points every OBST_STEP m along the vertical faces of the building and wall meshes, the lamp
    posts among them), only within near_r m of the points near_pts (the car parks)."""
    import optimize_level
    ptree = cKDTree(near_pts)
    out = []
    for g in OBST_GROUPS:
        f = f"{lv}/main/MissionGroup/{g}/items.level.json"
        if f not in zi.NameToInfo:
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
                continue
            if ptree.query(o.get("position", [0, 0, 0])[:2])[0] > near_r + SHAPE_REACH:
                continue                                 # a tile of meshes far from every car park
            try:
                V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            except (AttributeError, ValueError):
                continue
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            for _, idx in parts:
                t = W[idx[:, 0]].reshape(-1, 3, 3)
                t = t[ptree.query(t.mean(1)[:, :2], distance_upper_bound=near_r)[0] < near_r]
                if not len(t):
                    continue
                cz = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                vert = np.abs(cz[:, 2]) < 0.05 * np.linalg.norm(cz, axis=1) + 1e-9
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    A, B = t[vert, a, :2], t[vert, b, :2]
                    n = np.clip(np.ceil(np.hypot(*(B - A).T) / OBST_STEP), 1, 200).astype(int)
                    for k in np.unique(n):
                        m = n == k
                        f_ = np.linspace(0, 1, k + 1)
                        out.append((A[m, None] + (B[m] - A[m])[:, None] * f_[None, :, None]).reshape(-1, 2))
    for g in PROP_GROUPS:                        # lamp posts, bins, benches, planters: by their position
        f = f"{lv}/main/MissionGroup/props/{g}/items.level.json"
        if f in zi.NameToInfo:
            out.append(np.array([o["position"][:2] for o in read_items(zi, f) if o.get("class") == "TSStatic"
                                 and "/levels/" + LEVEL_NAME + "/" not in o.get("shapeName", "")]).reshape(-1, 2))
    Q = np.concatenate(out) if out else np.zeros((1, 2)) + 1e9
    return cKDTree(Q), Q


def parking_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    ways, _ = osm.load()
    parks = []
    for w in ways:
        t = w["tags"]
        a = t.get("amenity")
        if a not in ("parking", "parking_space") or len(w["xy"]) < 4 or not np.allclose(w["xy"][0], w["xy"][-1]):
            continue
        if a == "parking" and t.get("parking") not in KINDS:
            continue
        if t.get("access") in ("private", "no") and a == "parking":
            continue
        p = shapely.Polygon(w["xy"]).buffer(0)
        if p.is_empty or p.area < (8.0 if a == "parking_space" else MIN_AREA):
            continue
        parks.append((a, w["id"], p))
    # the AI lanes: their axis points and half widths
    pts, half = [], []
    for road in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json"):
        nd = np.asarray(road.get("nodes", []), np.float64)
        if len(nd) < 2:
            continue
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(nd[:, :2], axis=0).T))]
        sd = np.linspace(0, s[-1], max(int(s[-1]), 1) + 1)
        pts.append(np.column_stack([np.interp(sd, s, nd[:, 0]), np.interp(sd, s, nd[:, 1])]))
        half.append(np.interp(sd, s, nd[:, 3]) / 2)
    P, H = np.concatenate(pts), np.concatenate(half)
    lanes = cKDTree(P)
    hmax = float(H.max())
    ground = Ground(zi, lv)
    cent = np.array([p.centroid.coords[0] for _, _, p in parks]).reshape(-1, 2)
    rmax = max((math.hypot(*np.ptp(np.asarray(p.exterior.coords), axis=0)) / 2 for _, _, p in parks), default=0)
    otree, opts = obstacles(zi, lv, cent, rmax + 2.0)
    rep = {"car_parks": len(parks), "spots": 0, "left_out": {"lane": 0, "obstacle": 0, "outside": 0, "tilt": 0}}
    spots = []
    for a, wid, poly in parks:
        inner = poly.buffer(-EDGE + 0.05)
        cands = []
        if a == "parking_space":
            r = poly.minimum_rotated_rectangle
            R = np.asarray(r.exterior.coords)[:4]
            e0, e1 = R[1] - R[0], R[2] - R[1]
            d = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
            d = d / max(np.hypot(*d), 1e-9)
            cands = [(np.asarray(poly.centroid.coords[0]), d, 4.6, 2.2)]
        else:
            cands = spot_rects(poly)
        for c, d, L, W in cands:
            sp = spot_poly(c, d, L, W)
            if a != "parking_space" and not inner.contains(sp):
                rep["left_out"]["outside"] += 1
                continue
            near = lanes.query_ball_point(sp.centroid.coords[0], hmax + LANE_CLEAR + max(L, W))
            if near:
                near = np.asarray(near)
                dd = shapely.distance(sp, shapely.points(P[near]))
                if (dd < H[near] + LANE_CLEAR).any():
                    rep["left_out"]["lane"] += 1
                    continue
            oi = otree.query_ball_point(c, math.hypot(L, W) / 2 + 0.3)
            if oi and shapely.contains_xy(sp.buffer(0.2), opts[oi, 0], opts[oi, 1]).any():
                rep["left_out"]["obstacle"] += 1
                continue
            corners = np.asarray(sp.exterior.coords)[:4]
            zc = ground.height(corners[:, 0], corners[:, 1])
            if (zc.max() - zc.min()) / max(L, W) > MAX_TILT:
                rep["left_out"]["tilt"] += 1
                continue
            z = float(ground.height([c[0]], [c[1]])[0])
            spots.append({"name": f"parking_{wid}_{len(spots)}", "pos": [round(float(c[0]), 3), round(float(c[1]), 3), round(z, 3)],
                          "rot": [round(v, 6) for v in quat_z(d)], "scl": [round(W + 0.3, 2), round(L + 0.4, 2), 3],
                          "isMultiSpot": False, "color": [1, 1, 1],
                          "customFields": {"names": ["probability"], "tags": {}, "types": {"probability": "number"},
                                           "values": {"probability": PROBABILITY}}})
    rep["spots"] = len(spots)
    sites = {"description": "Parking spots of the map's car parks (parking.py)", "dir": f"/levels/{LEVEL_NAME}/",
             "filename": SITES, "name": SITES, "locations": {}, "zones": [], "parkingSpots": spots}
    name = f"{lv}/{SITES}"
    if name in zi.NameToInfo:                                 # keep the zones and locations of an earlier file
        old = json.loads(zi.read(name))
        sites["zones"], sites["locations"] = old.get("zones", []), old.get("locations", {})
    data = json.dumps(sites, indent=1).encode("utf-8")
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename != name:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        zo.writestr(zipfile.ZipInfo(name, time.localtime()[:6]), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("parking:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
