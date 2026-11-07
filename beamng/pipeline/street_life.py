"""Street life (v3.0): the small things of a lived-in village, placed by rules where nobody mapped them.

Up to v2.8 the furniture of the map was what OpenStreetMap records (props_osm.py: about 160 benches and 20
bins) and what the panoramas of the cantonal road show (props.py): the villages off that road had street
lights and nothing else, and looked like a model before the people move in. Here the vanilla models of the
game (Italy's clutter, installed with every copy of BeamNG.drive) go where a village of the Malcantone has
them, by rules, on the built level:
- litter bins along the village roads, one every BIN_SPACING m (the sides taken in turn), and one beside
  every bus stop OSM records;
- fire hydrants along the village roads, one every HYDRANT_SPACING m;
- the recycling points OSM records (amenity=recycling): a row of sorting bins and a big bin along the
  road, a few rubbish bags beside some;
- the post boxes (amenity=post_box) and picnic tables (leisure=picnic_table) OSM records;
- terraces: in front of the bars, cafes, restaurants and ice-cream shops OSM records, TERRACE_TABLES
  round tables with two chairs each and an umbrella, on free flat ground between the building and the
  road;
- planters along the pedestrian streets and squares (highway=pedestrian), one every PLANTER_SPACING m;
- convex traffic mirrors where a village road ends on another road between buildings (a blind exit),
  on a grey pole (drawn here) on the far side of the other road, turned to the road that ends;
- at the houses: one or two bins between YARD_BIN_SHARE of them and the road, a letter box on its stand
  at the edge of the road for POST_BOX_SHARE (the Swiss letter boxes stand at the gate), a table with
  chairs and an umbrella in the garden of GARDEN_SHARE; pallets (some stacked) and drums beside
  YARD_STUFF_SHARE of the other buildings (sheds, barns, workshops);
- a bench at the viewpoints OSM records (tourism=viewpoint).
- the squares, car parks and yards (the cadastral hard ground, YARD_MIN m2 and more): props along their
  edges, by what is around (benches, planters, bins on the village squares; pallets, drums, skips beside
  the sheds and workshops), the middle left free for the cars.
A village road point: VILLAGE_N buildings of the Federal Register within VILLAGE_R m (as lamps.py).
Nothing stands on a carriageway, on the line of an AI road (its half width and LANE_CLEAR m: v3.1 had 432 props,
156 of them pallets, inside it, on yards, squares and junctions the road crosses with no carriageway mesh), a railway, in or under a building (its roof outline and CLEAR m), on a
wall, within CLEAR m of the other props, guard rails, fences and trunks, or on ground steeper than
MAX_STEP m over its footprint; what does not find such ground is left out. Every choice is drawn from a
seeded generator, so a build gives the same street life every time.

The objects are TSStatics of the game's own models (instanced rendering, their own detail levels and
collision), in MissionGroup/props/street_life, their material definitions (taken from the game once,
dati/vanilla_props_materials.json, so a build without the game has them) in
art/shapes/props/street_life.materials.json; everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish street_life
"""
import gzip, json, math, os, re, time
import numpy as np
from scipy.spatial import cKDTree
import bng
import network_mesh as pu
import walls as pw
import road_mesh
import osm
import props
from config import LEVEL_NAME
from lamps import read_items, faces, obstacle_points, sample, CARRIAGEWAY, VILLAGE_R, VILLAGE_N, MIN_AREA, DATI

IT = "/levels/italy/art/shapes/buildings"
IM = "/levels/italy/art/shapes/misc"
OBJ = "/art/shapes/objects"
FRONT_Y = -math.pi / 2          # the models with a front (chairs, benches, mirrors, post boxes) face their local -y
# key: (shape, footprint radius m, the model's front in its own frame (radians from +x), collision); sizes measured
# on the game's models (bounding boxes of their finest detail level)
MODELS = {
    "bin": (f"{IT}/italy_clutter_metal_bin.DAE", 0.2, 0.0, True),                 # 0.34 x 0.34 x 0.74 m
    "sorting_bin": (f"{IT}/italy_clutter_sorting_bin.DAE", 0.33, FRONT_Y, True),   # 0.56 x 0.62 x 0.97
    "dumpster": (f"{IT}/italy_clutter_dumpster.DAE", 0.85, FRONT_Y, True),         # 1.57 x 0.83 x 1.20
    "house_bin": (f"{IT}/italy_clutter_big_dustbin.DAE", 0.32, FRONT_Y, True),     # 0.60 x 0.60 x 0.68
    "trashbags": (f"{OBJ}/s_trashbag_pile_01.dae", 0.75, 0.0, False),               # 1.38 x 1.21 x 1.04
    "hydrant": (f"{IT}/italy_clutter_fire_hydrant.DAE", 0.2, FRONT_Y, True),       # 0.37 x 0.31 x 0.79
    "post_box": (f"{IT}/italy_clutter_mailboxstand.DAE", 0.33, FRONT_Y, True),     # 0.66 x 0.29 x 1.60
    "picnic": (f"{IT}/italy_clutter_pwood_table.DAE", 1.0, 0.0, True),             # 1.80 x 1.34 x 0.71
    "table": (f"{IT}/italy_clutter_round_mtable.DAE", 0.3, 0.0, True),             # 0.60 x 0.60 x 0.74
    "chair": (f"{IT}/italy_clutter_metal_chair.DAE", 0.31, FRONT_Y, True),         # 0.62 x 0.63 x 0.87
    "umbrella": (f"{IT}/italy_clutter_bar_umbrella.DAE", 0.76, 0.0, False),        # 1.50 x 1.52 x 2.32
    "garden_table": (f"{IT}/italy_clutter_round_ptable.DAE", 0.36, 0.0, True),     # 0.72 x 0.72 x 0.74
    "garden_chair": (f"{IT}/italy_clutter_plastic_chair_a.DAE", 0.29, FRONT_Y, True),
    "planter": (f"{IT}/italy_city_tree_pot_wplant.dae", 0.95, 0.0, True),          # 1.88 x 0.86 x 1.54
    "planter_round": (f"{IM}/italy_planter_round_1.dae", 0.29, 0.0, True),          # 0.56 x 0.56 x 0.51
    "planter_square": (f"{IM}/italy_planter_square_2.dae", 0.79, 0.0, True),        # 1.56 x 0.56 x 0.51
    "mirror": (f"{IT}/italy_clutter_convexmirror.DAE", 0.3, FRONT_Y, True),        # 0.50 x 0.09 x 0.50, no pole
    "pallet": (f"{IT}/italy_clutter_pallet.DAE", 0.8, 0.0, True),                  # 1.37 x 0.91 x 0.20
    "drum": (f"{IT}/italy_clutter_metal_drum.DAE", 0.36, 0.0, True),               # 0.71 x 0.71 x 1.00
    "bench": (f"{IT}/italy_clutter_pwood_bench.DAE", 0.8, FRONT_Y, True),          # 1.58 x 0.61 x 0.79
}
VANILLA_MATS = os.path.join(DATI, "vanilla_props_materials.json")
MIRROR_H = 2.3                  # m, the middle of a mirror over the ground (its own pole drawn here)
SEED = 61
BIN_SPACING = 75.0              # m along a village road between two litter bins
HYDRANT_SPACING = 120.0         # m between two hydrants
LATERAL = 0.55                  # m beyond the carriageway edge to the middle of a roadside object
CLEAR = 0.8                     # m from the other props, guard rails, fences, trunks
ROOF_CLEAR = 0.4                # m from the outline of a roof
MAX_STEP = 0.35                 # m of height over an object's footprint, and from the road edge
JUNCTION = 9.0                  # m from the axis of another road: no roadside object there
LANE_CLEAR = 0.1                # m beyond the half width of an AI road: the cars drive there, mesh or not (the
                                # hydrants and letter boxes at the edge of the carriageway stand just outside it)
TERRACE_R = (2.5, 14.0)         # m from the place's point to its terrace
TERRACE_TABLES = (2, 4)
TERRACE_PITCH = 2.4             # m between two tables
PLANTER_SPACING = 18.0
MIRROR_BLIND = 7.0              # m: a roof this near the end of the road makes the exit blind
YARD_BIN_SHARE = 0.2
POST_BOX_SHARE = 0.12          # of the houses: a letter box on a stand by the road (the Swiss boxes stand at the gate)
GARDEN_SHARE = 0.07            # of the houses: a table, chairs and an umbrella in the garden
VIEW_BENCH = True              # a bench at the viewpoints OSM records (tourism=viewpoint)
YARD_STUFF_SHARE = 0.08
BAGS_SHARE = 0.35
HOUSE = (1020, 1030, 1040)      # GWR categories with homes
TERRACE_PLACES = {"cafe", "bar", "restaurant", "ice_cream", "pub", "fast_food"}
YARD_MATS = ("mp_hard_asphalt",)  # the cadastral 'other hard surface': squares, car parks, forecourts, yards
YARD_CELL = 1.0                 # m, grid of the yards
YARD_MIN = 120.0                # m2: smaller hard ground is a drive, left as it is
YARD_EDGE = (0.9, 1.9)          # m from the edge of a yard to the middle of the props along it
YARD_PITCH = 7.0                # m along the edge between two props of a yard
YARD_FILL = 0.55                # share of the edge places of a yard that get a prop
RING = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [0.7, 0.7], [-0.7, 0.7], [0.7, -0.7], [-0.7, -0.7]])


class Site:
    """The built level as the ground a prop stands on: carriageways, other paved ground, roofs, walls, railway,
    the terrain, the objects to keep clear of (the props placed here join them)."""

    def __init__(self, zi, lv):
        blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
                   if o.get("class") == "TerrainBlock")
        pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
        _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
        self.q = q
        road = faces(zi, lv, ["roads/surfaces"])
        none = [np.zeros((0, 3, 3))]
        self.carr = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if CARRIAGEWAY.match(m)] or none))
        self.paved = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if not CARRIAGEWAY.match(m)] or none))
        self.hard = [t for m, t in road.items() if m in YARD_MATS]      # squares, car parks, yards
        self.roof = road_mesh.TriSurface(np.concatenate(list(faces(zi, lv, ["buildings"]).values()) or none))
        self.wall = road_mesh.TriSurface(np.concatenate(list(faces(zi, lv, ["walls"], keep=lambda sn: "backfill" not in sn)
                                                             .values()) or none))
        self.rail = road_mesh.TriSurface(np.concatenate(list(faces(zi, lv, ["railway"]).values()) or none))
        self.obst = cKDTree(obstacle_points(zi, lv))
        self.placed = np.zeros((0, 2))
        self.placed_r = np.zeros(0)
        self.lanes = None                   # Roads, once read: the lines the AI cars drive
        self.why = {}

    def terrain(self, x, y):
        return pu.terrain_top(self.q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))

    def ground(self, x, y):
        """Height of what one stands on: the paved ground beside the roads where there is, else the terrain."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        zt = self.terrain(x, y)
        zg = self.paved.height(x, y, "high")
        return np.where(np.isfinite(zg) & (zg > zt - 0.3), zg, zt)

    def on_carriageway(self, x, y):
        return np.isfinite(self.carr.height(np.atleast_1d(x), np.atleast_1d(y), "high"))

    def _no(self, why):
        self.why[why] = self.why.get(why, 0) + 1
        return None

    def free(self, p, r, carriage_ok=False):
        """Ground z at p for an object of footprint radius r, or None where it may not stand."""
        P = p + max(r, 0.15) * RING
        if not carriage_ok and self.on_carriageway(P[:, 0], P[:, 1]).any():
            return self._no("carriageway")
        if not carriage_ok and self.lanes is not None and self.lanes.in_lane(P, LANE_CLEAR).any():
            return self._no("lane")
        E = p + (max(r, 0.15) + ROOF_CLEAR) * RING
        if np.isfinite(self.roof.height(E[:, 0], E[:, 1], "high")).any():
            return self._no("building")
        if np.isfinite(self.wall.height(P[:, 0], P[:, 1], "high")).any():
            return self._no("wall")
        if np.isfinite(self.rail.height(P[:, 0], P[:, 1], "high")).any():
            return self._no("railway")
        if self.obst.query_ball_point(p, r + CLEAR, return_length=True) > 0:
            return self._no("clear")
        if len(self.placed):
            d = np.hypot(*(self.placed - p).T)
            if np.any(d < self.placed_r + r + 0.25):
                return self._no("props")
        z = self.ground(P[:, 0], P[:, 1])
        if not np.all(np.isfinite(z)) or z.max() - z.min() > MAX_STEP:
            return self._no("slope")
        return float(self.ground([p[0]], [p[1]])[0])

    def take(self, p, r):
        self.placed = np.vstack([self.placed, p[None, :2]])
        self.placed_r = np.r_[self.placed_r, r]


class Roads:
    """The axes of the AI roads every metre: which road each point is on, its width, the village points."""

    def __init__(self, zi, lv, houses):
        roads = [o for o in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
        self.roads = roads
        self.S = [sample(o["nodes"]) for o in roads]
        ok = [s for s in self.S if s is not None]
        self.ids = np.concatenate([np.full(len(s[0]), i) for i, s in enumerate(self.S) if s is not None])
        self.P = np.concatenate([s[0] for s in ok])
        self.T = np.concatenate([s[1] for s in ok])
        self.W = np.concatenate([s[2] for s in ok])
        self.tree = cKDTree(self.P[:, :2])
        self.gtree = cKDTree(houses)

    def village(self, P):
        return self.gtree.query_ball_point(P[:, :2], VILLAGE_R, return_length=True) >= VILLAGE_N

    def near_junction(self, P, road):
        near = self.tree.query_ball_point(P[:, :2], JUNCTION)
        return np.array([np.any(self.ids[k] != road) for k in near])

    def nearest(self, p):
        _, k = self.tree.query(p[:2])
        return k

    def in_lane(self, P, clear):
        """For each point (k, 2): within the half width + clear of the axis of an AI road (the yards, squares and
        junctions it crosses have no carriageway mesh, the cars drive there all the same)."""
        P = np.atleast_2d(P)[:, :2]
        near = self.tree.query_ball_point(P, float(self.W.max()) / 2 + clear)
        return np.array([bool(k) and bool(np.any(np.hypot(*(self.P[k, :2] - p).T) < self.W[k] / 2 + clear))
                         for p, k in zip(P, near)])


def roadside(site, roads, c, t, w, side, r, lateral=LATERAL):
    """(x, y, z, theta to the road) of an object of radius r beside the axis point c (tangent t, width w) on
    side +1 (right) or -1, beyond the carriageway edge; None where it may not stand."""
    n = side * np.array([t[1], -t[0]])
    d = np.arange(0.5, w / 2 + 6.0, 0.25)
    Q = c[:2] + d[:, None] * n
    on = site.on_carriageway(Q[:, 0], Q[:, 1]) & (d < w / 2 + 3.0)
    edge = d[np.flatnonzero(on).max()] if on.any() else w / 2
    p = c[:2] + (edge + lateral + r) * n
    z = site.free(p, r)
    if z is None:
        return None
    ze = site.carr.height([c[0] + (edge - 0.3) * n[0]], [c[1] + (edge - 0.3) * n[1]], "high")[0]
    ze = c[2] if not np.isfinite(ze) else ze
    if not (-0.4 <= z - ze <= MAX_STEP + 0.25):
        return site._no("step")
    k = roads.tree.query_ball_point(p, 8.0)                       # in the way of another road
    if k and np.any(np.hypot(*(roads.P[k, :2] - p).T) < roads.W[k] / 2 + lateral - 0.05):
        return site._no("carriageway")
    return float(p[0]), float(p[1]), z, math.atan2(-n[1], -n[0])


class Out:
    def __init__(self, site, rng):
        self.items, self.counts, self.site, self.rng = [], {}, site, rng
        self.poles = []                                    # triangles of the mirrors' poles

    def add(self, key, x, y, z, facing, r=None, count=True):
        shape, rad, front, coll = MODELS[key]
        o = bng.tsstatic(shape, (x, y, z), rot=bng.rot_local_x_to(facing - front), collision=coll)
        o["__parent"] = "street_life"
        self.items.append(o)
        self.site.take(np.array([x, y]), rad if r is None else r)
        if count:
            self.counts[key] = self.counts.get(key, 0) + 1


def along_villages(site, roads, out, rng, key, spacing, lateral=LATERAL):
    """One `key` every `spacing` m along the village stretches of the roads, the sides in turn."""
    r = MODELS[key][1]
    for i, s in enumerate(roads.S):
        if s is None:
            continue
        P, T, W, dist = s
        vil = roads.village(P) & ~roads.near_junction(P, i)
        side, next_s = (1 if rng.uniform() < 0.5 else -1), None
        for j in np.flatnonzero(vil):
            if next_s is None:
                next_s = dist[j] + rng.uniform(0.2, 0.8) * spacing
            if dist[j] < next_s:
                continue
            res = roadside(site, roads, P[j], T[j], W[j], side, r, lateral) or \
                roadside(site, roads, P[j], T[j], W[j], -side, r, lateral)
            if res is None:
                continue
            x, y, z, th = res
            out.add(key, x, y, z, th)
            side = -side
            next_s = dist[j] + spacing * rng.uniform(0.8, 1.2)


def near_road_point(roads, p):
    k = roads.nearest(p)
    return roads.P[k], roads.T[k], roads.W[k], roads.ids[k]


def at_node(site, roads, out, key, p, rng, max_shift=4.0):
    """`key` at the OSM point p, or the nearest free point within max_shift m, facing the nearest road."""
    r = MODELS[key][1]
    c, t, w, _ = near_road_point(roads, p)
    for d in np.arange(0.0, max_shift + 0.01, 0.5):
        for a in (np.linspace(0, 2 * np.pi, 8, endpoint=False) if d else [0.0]):
            q = p + d * np.array([math.cos(a), math.sin(a)])
            z = site.free(q, r)
            if z is not None:
                to = c[:2] - q
                out.add(key, q[0], q[1], z, math.atan2(to[1], to[0]))
                return q
    return None


def recycling(site, roads, out, rng, p):
    """A row of three sorting bins and a big bin along the nearest road, at the OSM point or beside the road."""
    c, t, w, rid = near_road_point(roads, p)
    n = np.array([t[1], -t[0]])
    side = 1 if n @ (p - c[:2]) > 0 else -1
    # the middle of the row: the OSM point if the row fits there, else beside the road
    for base in (p, c[:2] + side * n * (w / 2 + LATERAL + 0.8)):
        row = [("sorting_bin", -2.3), ("sorting_bin", -1.6), ("sorting_bin", -0.9), ("dumpster", 0.45)]
        pts = [base + t * off for _, off in row]
        zs = [site.free(q, MODELS[k][1]) for (k, _), q in zip(row, pts)]
        if all(z is not None for z in zs):
            face = math.atan2(c[1] - base[1], c[0] - base[0])
            for (k, _), q, z in zip(row, pts, zs):
                out.add(k, q[0], q[1], z, face, count=False)
            out.counts["recycling"] = out.counts.get("recycling", 0) + 1
            if rng.uniform() < BAGS_SHARE:
                q = base + t * (2.3 + rng.uniform(0, 0.4))
                z = site.free(q, MODELS["trashbags"][1])
                if z is not None:
                    out.add("trashbags", q[0], q[1], z, rng.uniform(0, 2 * np.pi))
            return True
    return False


def terrace(site, roads, out, rng, p):
    """Tables, chairs and umbrellas on free flat ground near the place p, in a row along the nearest road."""
    c, t, w, _ = near_road_point(roads, p)
    best = None
    for rad in np.arange(TERRACE_R[0], TERRACE_R[1] + 0.01, 1.0):
        for a in np.linspace(0, 2 * np.pi, int(2 * np.pi * rad / 1.2), endpoint=False):
            q = p + rad * np.array([math.cos(a), math.sin(a)])
            if site.free(q, 1.3) is not None:
                best = q
                break
        if best is not None:
            break
    if best is None:
        return False
    n_t = int(rng.integers(TERRACE_TABLES[0], TERRACE_TABLES[1] + 1))
    placed = 0
    for k in range(n_t):
        off = (k - (n_t - 1) / 2) * TERRACE_PITCH
        q = best + t[:2] * off
        z = site.free(q, 1.1)
        if z is None:
            continue
        out.add("table", q[0], q[1], z, rng.uniform(0, 2 * np.pi), r=1.1)
        out.add("umbrella", q[0], q[1], z, rng.uniform(0, 2 * np.pi), r=0.0)
        for s in (-1, 1):
            a = math.atan2(t[1], t[0]) + math.pi / 2 + rng.uniform(-0.3, 0.3)
            cq = q + s * 0.72 * np.array([math.cos(a), math.sin(a)])
            zc = float(site.ground([cq[0]], [cq[1]])[0])
            out.add("chair", cq[0], cq[1], zc, math.atan2(q[1] - cq[1], q[0] - cq[0]) + rng.uniform(-0.25, 0.25), r=0.0)
        placed += 1
    if placed:
        out.counts["terraces"] = out.counts.get("terraces", 0) + 1
    return placed > 0


def planters(site, roads, out, rng, ways):
    for wy in ways:
        if wy["tags"].get("highway") != "pedestrian":
            continue
        line = wy["line"]
        if line.length < 8:
            continue
        side = 1
        for s in np.arange(rng.uniform(2, PLANTER_SPACING / 2), line.length, PLANTER_SPACING):
            a, b = np.asarray(line.interpolate(s).coords[0]), np.asarray(line.interpolate(min(s + 1, line.length)).coords[0])
            t = (b - a) / max(np.linalg.norm(b - a), 1e-9)
            n = np.array([t[1], -t[0]])
            for sd in (side, -side):
                for off in (1.8, 2.6, 3.4):
                    q = a + sd * off * n
                    key = ("planter", "planter_round", "planter_square")[int(rng.choice(3, p=[0.45, 0.3, 0.25]))]
                    z = site.free(q, MODELS[key][1])
                    if z is not None:
                        out.add(key, q[0], q[1], z, math.atan2(t[1], t[0]) + (math.pi / 2 if key != "planter_round" else rng.uniform(0, 6.3)))
                        break
                else:
                    continue
                break
            side = -side


def mirrors(site, roads, out, rng):
    """A convex mirror across the road at every blind end of a village road on another road."""
    for i, o in enumerate(roads.roads):
        s = roads.S[i]
        if s is None:
            continue
        P, T, W, dist = s
        for end, inward in ((0, 1), (-1, -1)):
            e = P[end]
            k = [x for x in roads.tree.query_ball_point(e[:2], 6.0) if roads.ids[x] != i]
            if not k:
                continue
            j = k[int(np.argmin(np.hypot(*(roads.P[k, :2] - e[:2]).T)))]
            c, t, w = roads.P[j], roads.T[j], roads.W[j]
            if not roads.village(c[None])[0]:
                continue
            # the road that ends must meet the other one across, not run on into it
            d_in = T[end] * inward                                  # pointing into the road that ends
            if abs(d_in @ t[:2]) > 0.6:
                continue
            # blind: roofs close to the end on both sides of the road that ends
            nrm = np.array([d_in[1], -d_in[0]])
            probe = e[:2] + d_in * 4.0
            blind = 0
            for sd in (1, -1):
                Q = probe + sd * nrm * np.arange(W[end] / 2 + 0.5, MIRROR_BLIND, 0.5)[:, None]
                blind += int(np.isfinite(site.roof.height(Q[:, 0], Q[:, 1], "high")).any() or
                             np.isfinite(site.wall.height(Q[:, 0], Q[:, 1], "high")).any())
            if blind == 0:
                continue
            n_o = np.array([t[1], -t[0]])
            far = -1 if n_o @ (e[:2] - c[:2]) > 0 else 1                # the side of the other road away from the end
            res = roadside(site, roads, c, t, w, far, MODELS["mirror"][1], lateral=0.4)
            if res is None:
                continue
            x, y, z, _ = res
            face = math.atan2(e[1] - y, e[0] - x)
            back = -np.array([math.cos(face), math.sin(face)]) * 0.06
            out.add("mirror", x, y, z + MIRROR_H, face)
            out.poles.append(props.tube(np.array([x, y]) + back, z - 0.3, z + MIRROR_H + 0.32, r=0.038, n=8))


def houses_props(site, roads, out, rng, gwr):
    """Bins, letter boxes and garden tables at the houses, pallets and drums beside the other buildings."""
    for b in gwr:
        p = np.array([b["x"], b["y"]], float)
        home = b.get("gkat") in HOUSE
        u = rng.uniform(size=4)
        if home:
            _, j = _carr_tree(site).query(p)
            to = _carr_pts(site)[j] - p
            dist = float(np.linalg.norm(to))
            if 1e-6 < dist < 30:
                to /= dist
                if u[0] < YARD_BIN_SHARE:                      # one or two bins between the house and the road
                    q = _past_eaves(site, p, to)
                    if q is not None:
                        side = np.array([to[1], -to[0]]) * rng.choice([-1, 1])
                        for k in range(1 + int(u[3] < 0.4)):
                            qq = q + side * 0.68 * k
                            z = site.free(qq, MODELS["house_bin"][1])
                            if z is None:
                                break
                            out.add("house_bin", qq[0], qq[1], z, math.atan2(to[1], to[0]) + rng.uniform(-0.2, 0.2))
                if u[1] < POST_BOX_SHARE:                      # the letter box at the edge of the road
                    c, t, w, rid = near_road_point(roads, p)
                    side = 1 if np.array([t[1], -t[0]]) @ (p - c[:2]) > 0 else -1
                    res = roadside(site, roads, c, t, w, side, MODELS["post_box"][1], lateral=0.4)
                    if res:
                        out.add("post_box", *res)
            if u[2] < GARDEN_SHARE:                            # a table in the garden, away from the road
                back = -to if 1e-6 < dist < 30 else np.array([1.0, 0.0])
                q = _past_eaves(site, p, back, extra=1.6)
                if q is not None and site.free(q, 1.3) is not None:
                    z = site.free(q, MODELS["garden_table"][1])
                    if z is not None:
                        out.add("garden_table", q[0], q[1], z, rng.uniform(0, 2 * np.pi), r=1.3)
                        out.add("umbrella", q[0], q[1], z, rng.uniform(0, 2 * np.pi), r=0.0, count=False)
                        for a in rng.uniform(0, 2 * np.pi) + np.array([0, math.pi * rng.uniform(0.6, 1.4)]):
                            cq = q + 0.75 * np.array([math.cos(a), math.sin(a)])
                            zc = float(site.ground([cq[0]], [cq[1]])[0])
                            out.add("garden_chair", cq[0], cq[1], zc, a + math.pi + rng.uniform(-0.3, 0.3), r=0.0)
        elif u[1] < YARD_STUFF_SHARE:                          # a shed, a barn, a workshop: pallets or drums
            a = rng.uniform(0, 2 * np.pi)
            q = _past_eaves(site, p, np.array([math.cos(a), math.sin(a)]))
            if q is None:
                continue
            want = "pallet" if u[2] < 0.5 else "drum"
            for k in range(1 + int(rng.integers(0, 3))):
                qq = q + np.array([math.cos(a + 1.57), math.sin(a + 1.57)]) * (1.5 if want == "pallet" else 0.75) * k
                z = site.free(qq, MODELS[want][1])
                if z is None:
                    break
                out.add(want, qq[0], qq[1], z, a + rng.uniform(-0.3, 0.3))
                if want == "pallet" and rng.uniform() < 0.5:   # stacked
                    out.add(want, qq[0], qq[1], z + 0.2, a + rng.uniform(-0.15, 0.15), r=0.0, count=False)


def yards(site, roads, out, rng, gwr):
    """The squares, car parks and yards (the cadastral hard ground beside the roads, YARD_MIN m2 and more):
    along their edges, inside, one prop every YARD_PITCH m for YARD_FILL of the places, by what is around:
    in a village benches facing the square, planters, bins, a picnic table on the big ones, a recycling
    corner on some; beside sheds, barns and workshops pallets (some stacked), drums, a skip, rubbish bags;
    out of the villages bins and planters. The middle stays free for the cars."""
    from scipy import ndimage
    if not site.hard:
        return
    T = np.concatenate(site.hard)
    S = road_mesh.TriSurface(T)
    other = np.array([[b["x"], b["y"]] for b in gwr if b.get("gkat") not in HOUSE] or np.zeros((0, 2)))
    otree = cKDTree(other) if len(other) else None
    c = T.mean(1)[:, :2]
    tiles = {tuple(k) for k in np.floor(c / 256.0).astype(int).tolist()}
    n = int(256 / YARD_CELL)
    for tx, ty in sorted(tiles):
        g = (np.arange(n) + 0.5) * YARD_CELL
        X, Y = np.meshgrid(tx * 256.0 + g, ty * 256.0 + g)
        m = np.isfinite(S.height(X.ravel(), Y.ravel(), "high")).reshape(n, n)
        if not m.any():
            continue
        # the edge of a yard where it meets the grass, a wall, a house: not where it goes on as road or
        # pavement (the first v3 test build put pallets in the middle of the paved squares)
        xr, yr = X.ravel(), Y.ravel()
        paved = (m.ravel() | np.isfinite(site.carr.height(xr, yr, "high")) |
                 np.isfinite(site.paved.height(xr, yr, "high"))).reshape(n, n)
        open_dist = ndimage.distance_transform_edt(paved) * YARD_CELL
        lab, k = ndimage.label(m)
        if not k:
            continue
        area = ndimage.sum(m, lab, np.arange(1, k + 1)) * YARD_CELL ** 2
        dist = ndimage.distance_transform_edt(m) * YARD_CELL
        gy, gx = np.gradient(dist)                               # pointing into the yard
        for i in np.flatnonzero(area >= YARD_MIN):
            cells = np.flatnonzero((lab.ravel() == i + 1) & (dist.ravel() >= YARD_EDGE[0]) & (dist.ravel() <= YARD_EDGE[1])
                                   & (open_dist.ravel() <= YARD_EDGE[1] + 0.3))
            if not len(cells):
                continue
            P = np.column_stack([X.ravel()[cells], Y.ravel()[cells]])
            ctr = P.mean(0)
            vil = bool(roads.village(ctr[None])[0])
            work = otree is not None and len(otree.query_ball_point(ctr, 25.0 + math.sqrt(area[i]) / 2)) > 0
            kind = "work" if work and (not vil or rng.uniform() < 0.5) else "square" if vil else "plain"
            big = area[i] >= 600
            chosen = []
            if kind == "square" and big and rng.uniform() < 0.25:     # a recycling corner on some squares
                j = int(rng.integers(len(P)))
                if recycling(site, roads, out, rng, P[j]):
                    chosen.append(P[j])
            for j in rng.permutation(len(P)):
                q = P[j]
                if chosen and np.min(np.hypot(*(np.asarray(chosen) - q).T)) < YARD_PITCH:
                    continue
                chosen.append(q)
                if rng.uniform() > YARD_FILL:
                    continue
                inward = math.atan2(gy.ravel()[cells[j]], gx.ravel()[cells[j]])
                along = inward + math.pi / 2
                u = rng.uniform()
                if kind == "square":
                    key = "bench" if u < 0.35 else "planter_square" if u < 0.55 else "planter_round" if u < 0.7 else \
                        "planter" if u < 0.8 else "bin" if u < 0.95 else ("picnic" if big else "bench")
                elif kind == "work":
                    key = "pallet" if u < 0.4 else "drum" if u < 0.65 else "dumpster" if u < 0.78 else \
                        "trashbags" if u < 0.88 else "house_bin"
                else:
                    key = "bin" if u < 0.4 else "planter_round" if u < 0.7 else "planter_square" if u < 0.85 else "bench"
                r = MODELS[key][1]
                qq = q + (r - 0.3) * np.array([math.cos(inward), math.sin(inward)])     # its back to the edge
                z = site.free(qq, r)
                if z is None:
                    continue
                face = {"bench": inward, "dumpster": inward, "house_bin": inward, "planter_square": along,
                        "planter": along, "picnic": along}.get(key, rng.uniform(0, 2 * np.pi))
                out.add(key, qq[0], qq[1], z, face)
                out.counts["yard_props"] = out.counts.get("yard_props", 0) + 1
                if key == "pallet" and rng.uniform() < 0.5:
                    for h in range(1, 1 + int(rng.integers(1, 4))):
                        out.add("pallet", qq[0], qq[1], z + 0.2 * h, face + rng.uniform(-0.1, 0.1), r=0.0, count=False)
                elif key == "drum" and rng.uniform() < 0.6:              # drums stand in twos and threes
                    for h in range(1, 1 + int(rng.integers(1, 3))):
                        d = qq + 0.74 * h * np.array([math.cos(along), math.sin(along)])
                        zd = site.free(d, MODELS["drum"][1])
                        if zd is None:
                            break
                        out.add("drum", d[0], d[1], zd, rng.uniform(0, 2 * np.pi))
            out.counts["yards"] = out.counts.get("yards", 0) + 1


def _past_eaves(site, p, d, extra=0.0):
    """The first point from the building point p along d beyond its roof (and ROOF_CLEAR, a little more)."""
    for s in np.arange(1.0, 18.0, 0.5):
        q = p + d * s
        if np.isfinite(site.roof.height([q[0]], [q[1]], "high")[0]):
            continue
        return q + d * (ROOF_CLEAR + 0.35 + extra)
    return None


_cache = {}
SL_SHAPE = re.compile(r"art/shapes/props/street_life_poles_[-+]\d+_[-+]\d+\.dae$")


def _tmpdir():
    if "tmp" not in _cache:
        import tempfile
        _cache["tmp"] = tempfile.mkdtemp(prefix="magliaso_sl_")
    return _cache["tmp"]


def _carr_pts(site):
    if "pts" not in _cache:
        _cache["pts"] = site.carr.t.mean(1)[:, :2]
    return _cache["pts"]


def _carr_tree(site):
    if "tree" not in _cache:
        _cache["tree"] = cKDTree(_carr_pts(site))
    return _cache["tree"]


def street_life_step(root, report=None):
    t0 = time.time()
    _cache.clear()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    rng = np.random.default_rng(SEED)
    site = Site(zi, lv)
    gwr = [b for b in json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz")))["buildings"] if b.get("gstat") == 1004]
    houses = np.array([[b["x"], b["y"]] for b in gwr if (b.get("garea") or MIN_AREA) >= MIN_AREA])
    roads = Roads(zi, lv, houses)
    site.lanes = roads
    out = Out(site, rng)
    ways, nodes = osm.load()
    inside = lambda p: len(roads.tree.query_ball_point(p, 60.0)) > 0     # on the map's network, not beyond it

    # first what OSM records, then the rules
    for nd in nodes:
        tg, p = nd["tags"], np.array([nd["x"], nd["y"]])
        if not tg or not inside(p):
            continue
        if tg.get("amenity") == "recycling":
            recycling(site, roads, out, rng, p)
        elif tg.get("amenity") == "post_box":
            at_node(site, roads, out, "post_box", p, rng)
        elif tg.get("leisure") == "picnic_table":
            at_node(site, roads, out, "picnic", p, rng)
        elif tg.get("tourism") == "viewpoint" and VIEW_BENCH:
            at_node(site, roads, out, "bench", p, rng, max_shift=6.0)
        elif tg.get("highway") == "bus_stop":
            c, t, w, rid = near_road_point(roads, p)
            side = 1 if np.array([t[1], -t[0]]) @ (p - c[:2]) > 0 else -1
            for shift in (3.0, -3.0, 5.0, -5.0):
                k = roads.nearest(c[:2] + t * shift)
                res = roadside(site, roads, roads.P[k], roads.T[k], roads.W[k], side, MODELS["bin"][1])
                if res:
                    out.add("bin", *res)
                    break
    for x, y, kind in osm.pois():
        if kind.split("=", 1)[-1] in TERRACE_PLACES and inside(np.array([x, y])):
            terrace(site, roads, out, rng, np.array([x, y]))
    planters(site, roads, out, rng, ways)
    mirrors(site, roads, out, rng)
    along_villages(site, roads, out, rng, "bin", BIN_SPACING)
    along_villages(site, roads, out, rng, "hydrant", HYDRANT_SPACING, lateral=0.35)
    houses_props(site, roads, out, rng, gwr)
    yards(site, roads, out, rng, gwr)
    print("street life: %s; left out: %s" % (out.counts, site.why), flush=True)

    grp = f"{lv}/main/MissionGroup/props/items.level.json"
    gitems = [o for o in read_items(zi, grp) if o.get("name") != "street_life"]
    gitems.append({"name": "street_life", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    sl = f"{lv}/main/MissionGroup/props/street_life/items.level.json"
    enc = lambda objs: ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
    new_files = {grp: enc(gitems)}
    pole_mat = f"{lv}/art/shapes/props/street_life.materials.json"
    if out.poles:
        T = np.concatenate(out.poles).reshape(-1, 3, 3)
        keys = np.floor(T.mean(1)[:, :2] / 512.0).astype(int)
        for key in sorted({tuple(k) for k in keys.tolist()}):
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            V = T[m].reshape(-1, 3)
            mb = bng.MeshBuilder()
            mb.add("mp_sl_pole", V, uvs=V[:, :2] * 0 + V[:, 2:3] * [0, 1], normals=bng.flat_normals_soup(V))
            rel = f"art/shapes/props/street_life_poles_{key[0]:+03d}_{key[1]:+03d}.dae"
            origin = np.array([(key[0] + 0.5) * 512.0, (key[1] + 0.5) * 512.0, 0.0])
            tmp = os.path.join(_tmpdir(), os.path.basename(rel))
            mb.write_dae(tmp, name=os.path.basename(rel)[:-4], origin=origin)
            new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
            o = bng.tsstatic(f"/{lv}/{rel}", origin, collision=True)
            o["__parent"] = "street_life"
            out.items.append(o)
    mats = {"mp_sl_pole": bng.material("mp_sl_pole", base_color=[0.55, 0.56, 0.57, 1], roughness=0.45, metallic=0.7)}
    # the materials of the game's models, measured from the game (dati/vanilla_props_materials.json), unless the
    # level defines them already (art/shapes/props/vanilla.materials.json of props.py)
    have = set()
    for n in zi.namelist():
        if n.startswith(f"{lv}/") and n.endswith("materials.json") and n != pole_mat:
            try:
                have |= set(json.loads(zi.read(n)))
            except ValueError:
                pass
    if os.path.exists(VANILLA_MATS):
        for k, v in json.load(open(VANILLA_MATS)).items():
            if k not in have and not k.startswith("_"):
                mats[k] = v
    new_files[pole_mat] = json.dumps(mats, indent=1).encode("utf-8")
    new_files[sl] = enc(out.items)
    with zi.writer() as zo:
        for inf in zi.infolist():
            if inf.filename in new_files or SL_SHAPE.search(inf.filename):
                continue
            zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        for n, data in new_files.items():
            zo.writestr(n, data)
    if "tmp" in _cache:
        import shutil
        shutil.rmtree(_cache["tmp"], ignore_errors=True)
    print("written in %.0f s: %d objects" % (time.time() - t0, len(out.items)), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump({"counts": out.counts, "objects": len(out.items), "left_out": site.why,
                   "seconds": round(time.time() - t0)}, open(report, "w"), indent=1)
    return 0
