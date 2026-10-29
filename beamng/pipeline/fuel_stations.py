"""Petrol stations (v3.0): canopies on pillars, pump islands with their dispensers, and price totems.

Up to the first v3 test build a petrol station of the map was what swissBUILDINGS3D has of it: the canopy over the
pumps is a roof without walls in the survey (LOD2 has no pillars), and the building meshes drew it as a slab of roof
hanging in the air, tilted with the survey's heights, over an empty forecourt: no pillar, no pump, nothing that says
petrol station. Here, on the built level, for every station OpenStreetMap records on the map's roads (amenity=fuel,
a point or an area, within STATION_ROAD m of an AI road; a pump at a marina, farther, is left out):
- the canopy of the survey: the pieces of roof of the building meshes (connected through their edges) within
  CANOPY_R m of the station's point that hang more than CANOPY_HAG m over the ground and have no wall under them
  (no wall face that reaches the ground ends at their edge or stands inside them: WALL_SHARE of their outline at
  most) are cut out of the building tiles: their triangles, and the faces hanging from their edge, are dropped from
  the <triangles> lists of the DAE, every other byte of the file as it was. The gutters and flower boxes of the
  finishing steps before (buildings/details, buildings/extras) inside them go too;
- in their place a canopy as they are built: the outline of the survey (its rectangle where it is one), level,
  its ceiling CLEAR_H m over the forecourt (MIN_CLEAR m over its highest point at least), a slab with a fascia band
  FASCIA_H m high all around in the brand's colours with its logo and name on every side, a white ceiling with
  recessed lights; where the survey has none, one of NEW_CANOPY m on the paved ground beside the road nearest the
  station's point that has room for it (no building, wall, tree, lamp or carriageway under it);
- pump islands under it, along the road: one row every ROW_PITCH m across the canopy (1-3), one or two islands per
  row: raised concrete ISLAND_H m with round ends, a yellow and black bollard at both ends, the canopy's square
  clad steel pillars on them (two an island, one when there are four), and one or two dispensers each: a cabinet
  with the brand's header, the price display of the grades on both faces, a screen and keypad, a nozzle in its
  holster for every grade with its hose. No island on a carriageway, an AI road's lane, a wall or under a roof;
- a price totem (TOTEM) beside the road at the station's entrance, never on the carriageway: logo on top, the grades
  and their prices below, on both faces, turned to the traffic of both directions;
- the canopy's lights at night (PointLights, nightLight as the street lamps).
No real brand: parodies only (BRANDS: similar colours and shapes, altered names); the stations without a name get
the local brand. Fuel grades from OSM (fuel:octane_95/98, fuel:diesel, fuel:lpg; else 95, 98 and diesel), prices
about those of Switzerland in 2026, a few centimes apart from station to station (the same every build).
The meshes are TSStatics in MissionGroup/props/fuel, three a station: the canopy (no collision: cars pass under it),
the islands, pillars, dispensers and totem (collision), the hoses and nozzles (no collision); a texture atlas per
station drawn here (logo, fascia, totem, dispenser faces, colour swatches) and the ceiling, with their materials in
art/shapes/props/fuel. street_life (after this step) keeps clear of them.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish fuel_stations
"""
import hashlib, json, math, os, re, tempfile, time, zipfile
import numpy as np
import shapely
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
import bng
import optimize_level
import osm
import road_mesh
import street_life
from lamps import read_items
from signs_ch import _font
from config import LEVEL_NAME, TER_X0, TER_X1, TER_Y0, TER_Y1

D = "art/shapes/props/fuel"
SHAPE = re.compile(r"art/shapes/props/fuel/[^/]+$")
STATION_ROAD = 30.0             # m: a station farther from every AI road is not on the map's roads
AREA_R = 90.0                   # m around a station: the part of the level read
SAME_STATION = 25.0             # m: OSM points and areas this close are one station
CANOPY_R = 25.0                 # m from the station's point to a piece of roof that may be its canopy
CANOPY_NEAR = 20.0              # m: a second canopy of the same station is this near the first
CANOPY_HAG = (2.5, 9.0)         # m over the ground (a tenth of its corners may be lower: where it meets a roof)
CANOPY_AREA = (25.0, 650.0)     # m2
CANOPY_ROOFS = ("bld_roof_flat", "bld_roof_metal")    # the roofs of buildings_mesh a canopy may have (not tiles)
CANOPY_SLOPE = 0.2              # rise over run of its faces at most
WALL_SHARE = 0.15               # of its outline with a wall under it: more, a building
NEAR = 0.3                      # m: a wall this near the edge of a roof stands under it
CLEAR_H, MIN_CLEAR = 4.8, 4.5   # m: the ceiling over the forecourt (median), over its highest point at least
SLAB, FASCIA_H, FASCIA_DROP, FASCIA_T = 0.2, 0.8, 0.06, 0.1   # m
STRIP_M = FASCIA_H * 1024 / 128  # m of fascia the logo strip of the atlas covers (6.4)
CONTENT_M = 4.4                 # m of it the logo and name take, in the middle
NEW_CANOPY = ((14.0, 9.0), (12.0, 8.5), (10.0, 8.0))   # m: along the road, across, of a canopy built new
PAVED_SHARE = 0.5               # of the ground under a new canopy paved at least
ROW_PITCH = 7.0                 # m between the rows of islands
ISLAND_W, ISLAND_H = 1.2, 0.15  # m
ISLAND_LEN = (4.4, 7.0)         # m
TWO_PUMPS = 5.4                 # m: an island this long has two dispensers
PILLAR = 0.36                   # m: the square cladding of a pillar
DISP = (1.1, 0.5, 1.6, 0.3)     # m: along the island, across, body height, header height
TOTEM = (2.0, 0.4, 5.5, 1.0)    # m: width, depth, height, plinth
TOTEM_GAP = 0.7                 # m from the edge of the carriageway to the totem
TOTEM_SEARCH = 25.0             # m along the road from the canopy
CHARGING_ONLY = "magliaso:from_charging_station"   # tag of a station found by its charging point
PUMP_OFF = 1.0                  # m from the face of a dispenser to the middle of its refuelling area
PUMP_AREA = [2.0, 0.5, 1.0]     # the scale of the area (as the vanilla gas stations)
LANE_CLEAR = 0.4                # m from an AI road's lane
OBST_CLEAR = 0.4                # m from lamps, poles, trunks, furniture
MAX_STEP = 0.6                  # m of ground under an island, the totem
DRAW = {"canopy": 1500.0, "solid": 600.0, "small": 200.0}     # m: drawn up to
LIGHT = {"radius": 12.0, "intensity": 4500.0, "color": [0.95, 0.97, 1.0, 1.0]}
PRICES = {"95": 1.84, "98": 1.95, "diesel": 1.92, "lpg": 0.99}    # CHF a litre
GRADES = {   # label, second language, colour of the grade (sRGB)
    "95": ("Bleifrei 95", "Sans plomb 95", (0, 140, 70)),
    "98": ("Bleifrei 98", "Sans plomb 98", (20, 80, 170)),
    "diesel": ("Diesel", "Gasolio", (25, 25, 25)),
    "lpg": ("GPL / LPG", "Autogas", (230, 120, 0)),
}
# parody brands: the colours and the kind of shape of the real ones, never their logo or their name.
# key: (regex on brand / name / operator, name shown, background, lettering, accent, emblem)
BRANDS = {
    "ene": (r"\beni\b|\bagip\b", "Ene", (255, 205, 0), (25, 25, 25), (215, 40, 25), "creature"),
    "asso": (r"\besso\b", "Asso", (255, 255, 255), (220, 30, 45), (25, 55, 145), "oval"),
    "sokar": (r"\bsocar\b|emil frey", "SOKAR", (255, 255, 255), (10, 70, 150), (220, 35, 40), "flame"),
    "avya": (r"\bavia\b", "Avya", (215, 25, 35), (255, 255, 255), (255, 255, 255), "wing"),
    "migrolini": (r"migrolino", "migrolini", (255, 255, 255), (245, 110, 0), (245, 110, 0), "m"),
    "migrul": (r"\bmigrol\b", "Migrul", (250, 115, 0), (255, 255, 255), (0, 125, 70), "drop"),
    "coup": (r"\bcoop\b", "Coup Pronto", (255, 255, 255), (235, 95, 0), (35, 35, 35), "c"),
    "piccadolly": (r"piccadilly", "Piccadolly", (20, 45, 110), (255, 205, 30), (215, 30, 40), "p"),
    "quik": (r"quick ?service", "QuikServis", (0, 120, 60), (255, 255, 255), (255, 210, 0), "bolt"),
    "local": (None, "Benzina Malcantone", (30, 85, 55), (255, 255, 255), (240, 190, 40), "drop"),
}
# the texture atlas of a station (px of a 1024 x 1024 image, x0 y0 x1 y1, y down)
ATLAS = 1024
R_STRIP = (0, 0, 1024, 128)       # fascia: logo and name in the middle, plain at both ends
R_TOTEM = (0, 128, 384, 992)      # 2.0 x 4.5 m
R_FRONT = (384, 128, 714, 698)    # dispenser face 1.1 x 1.9 m: header 90 px, body 480
R_SIDE = (714, 128, 864, 698)     # dispenser side 0.5 x 1.9 m
R_BANDS = (384, 896, 448, 1024)   # yellow and black bands of the bollards
SWATCH = (768, 768, 64)           # 4 x 4 colours of 64 px from (768, 768)
SW = {"bg": 0, "fg": 1, "accent": 2, "white": 3, "light": 4, "dark": 5, "black": 6, "steel": 7, "95": 8, "98": 9,
      "diesel": 10, "yellow": 11, "concrete": 12, "kerb": 13, "roof": 14, "lpg": 15}
SS = 2                            # supersampling of the drawing
CEIL_TILE = 2.5                   # m of ceiling per tile of the ceiling texture (one recessed light)


def _unit(key, salt):
    """A number in [0, 1) from the key, the same every build."""
    return int.from_bytes(hashlib.md5(f"{salt}:{key}".encode()).digest()[:4], "little") / 2 ** 32


def _perp(t):
    return np.array([t[1], -t[0]])


# ------------------------------------------------------------------ the stations
def brand_of(tags):
    text = " ".join(str(tags.get(k, "")) for k in ("brand", "name", "operator")).lower()
    for key, (rx, *_) in BRANDS.items():
        if rx and re.search(rx, text):
            return key
    return "local"


def grades_of(tags):
    yes = [g for g, k in (("95", "fuel:octane_95"), ("98", "fuel:octane_98"), ("diesel", "fuel:diesel"),
                          ("lpg", "fuel:lpg")) if tags.get(k) == "yes"]
    if not yes:
        return ["95", "98", "diesel"]
    if "95" not in yes:
        yes.insert(0, "95")
    if "diesel" not in yes:
        yes.insert(len([g for g in yes if g in ("95", "98")]), "diesel")
    return yes


def prices_of(sid, grades):
    off = (round(_unit(sid, "price") * 8) - 4) / 100.0          # -0.04 .. +0.04 CHF, the same for every grade
    return {g: PRICES[g] + off + (round(_unit(sid, g) * 2) - 1) / 100.0 for g in grades}


def stations(roads):
    """The petrol stations OSM records on the map's roads: [{id, x, y, tags, brand, grades, prices}], and the count
    of those left out (off the terrain, away from the roads)."""
    ways, nodes = osm.load()
    pts = [(n["id"], n["x"], n["y"], n["tags"]) for n in nodes if n["tags"].get("amenity") == "fuel"]
    # v3.0 review: a charging point a fuel company runs stands at its petrol station, which OpenStreetMap may not map
    # (the Eni of Magliaso, by the FLP stop Magliaso Paese, is only its charging point): a station of its own,
    # built only where the survey has its canopy (CHARGING_ONLY)
    for n in nodes:
        t = n["tags"]
        if t.get("amenity") == "charging_station" and brand_of(t) != "local":
            pts.append((n["id"], n["x"], n["y"], dict(t, amenity="fuel", **{CHARGING_ONLY: "yes"})))
    for w in ways:
        if w["tags"].get("amenity") == "fuel":
            xy = w["xy"]
            c = shapely.Polygon(xy).centroid if len(xy) >= 4 and np.allclose(xy[0], xy[-1]) else w["line"].centroid
            pts.append((w["id"], c.x, c.y, w["tags"]))
    out, why = [], {"osm": len(pts), "off_terrain": 0, "off_road": 0, "same_station": 0}
    pts.sort(key=lambda p: CHARGING_ONLY in p[3])                  # the mapped stations first
    for sid, x, y, tags in pts:
        if not (TER_X0 < x < TER_X1 and TER_Y0 < y < TER_Y1):
            why["off_terrain"] += 1
            continue
        d, _ = roads.tree.query([x, y])
        if d > STATION_ROAD:
            why["off_road"] += 1
            continue
        same = [s for s in out if math.hypot(s["x"] - x, s["y"] - y) < SAME_STATION]
        if same and CHARGING_ONLY in tags:                         # the station is mapped: the charger is its
            why["same_station"] += 1
            continue
        if same:
            for k, v in tags.items():
                same[0]["tags"].setdefault(k, v)
            why["same_station"] += 1
            continue
        out.append({"id": sid, "x": float(x), "y": float(y), "tags": dict(tags)})
    for s in out:
        s["brand"] = brand_of(s["tags"])
        s["grades"] = grades_of(s["tags"])
        s["prices"] = prices_of(s["id"], s["grades"])
    return out, why


# ------------------------------------------------------------------ the building meshes around them
TRI_RE = re.compile(r'<triangles material="([^"]*)-mat" count="(\d+)">(.*?)<p>([^<]*)</p></triangles>', re.S)


class Meshes:
    """The triangles of the tile shapes of some groups (buildings, their details and extras) near some points,
    in world coordinates, with where each comes from: (shape, list of its <triangles>, triangle in the list)."""

    def __init__(self, zi, lv, groups, pts, r):
        self.shapes, self.text = [], {}
        T, M, ref = [], [], []
        P = np.asarray(pts, np.float64).reshape(-1, 2)
        for g in groups:
            f = f"{lv}/main/MissionGroup/{g}/items.level.json"
            if f not in zi.NameToInfo:
                continue
            for o in read_items(zi, f):
                sn = o.get("shapeName", "").lstrip("/")
                if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or "rotationMatrix" in o or "scale" in o:
                    continue
                pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
                if not len(P) or not np.any(np.all(np.abs(P - pos[:2]) < 1200.0, axis=1)):
                    continue
                text = zi.read(sn).decode("utf-8")
                if not optimize_level.is_pipeline(text):
                    continue
                V, _, _, _, parts, _ = optimize_level.parse(text)
                W = V + pos
                si = len(self.shapes)
                for pi, (mat, idx) in enumerate(parts):
                    t = W[idx[:, 0]].reshape(-1, 3, 3)
                    lo, hi = t.min(1)[:, :2], t.max(1)[:, :2]
                    m = np.zeros(len(t), bool)
                    for p in P:
                        m |= np.all((lo - r < p) & (hi + r > p), axis=1)
                    if m.any():
                        k = np.flatnonzero(m)
                        T.append(t[k])
                        M += [mat] * len(k)
                        ref.append(np.column_stack([np.full(len(k), si), np.full(len(k), pi), k]))
                self.shapes.append(sn)
                self.text[sn] = text
        self.t = np.concatenate(T) if T else np.zeros((0, 3, 3))
        self.mat = np.array(M, dtype=object)
        self.ref = np.concatenate(ref) if ref else np.zeros((0, 3), np.int64)
        n = np.cross(self.t[:, 1] - self.t[:, 0], self.t[:, 2] - self.t[:, 0])
        self.nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
def drop_triangles(text, drop):
    """The DAE text without the triangles of `drop` ({index of its <triangles> list: indices of triangles}), every
    other byte as it was; a list left empty goes."""
    out, last = [], 0
    for pi, m in enumerate(TRI_RE.finditer(text)):
        if pi not in drop:
            continue
        nin = m.group(3).count("<input")
        idx = np.array(m.group(4).split(), np.int64).reshape(-1, 3 * nin)
        keep = np.ones(len(idx), bool)
        keep[sorted(drop[pi])] = False
        out.append(text[last:m.start()])
        if keep.any():
            out.append(f'<triangles material="{m.group(1)}-mat" count="{int(keep.sum())}">{m.group(3)}'
                       f'<p>{" ".join(map(str, idx[keep].ravel()))}</p></triangles>')
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def _pieces(T):
    """Connected pieces (through shared edges, positions to 2 cm) of the triangles T (k, 3, 3): labels (k,)."""
    if not len(T):
        return 0, np.zeros(0, np.int64)
    _, vid = np.unique(np.round(T.reshape(-1, 3) * 50).astype(np.int64), axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    e = np.sort(np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]]), axis=1)
    ek = e[:, 0] * (int(vid.max()) + 1) + e[:, 1]
    tri = np.tile(np.arange(len(T)), 3)
    order = np.argsort(ek, kind="stable")
    same = ek[order][1:] == ek[order][:-1]
    A = coo_matrix((np.ones(int(same.sum())), (tri[order][:-1][same], tri[order][1:][same])), shape=(len(T), len(T)))
    return connected_components(A, directed=False)


def _outline_edges(T):
    """Edges (m, 2, 3) of the triangles T used by one of them only: the outline of the piece."""
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    k = np.round(E * 50).astype(np.int64).reshape(len(E), 6)
    a, b = k[:, :3], k[:, 3:]
    first = (a[:, 0] < b[:, 0]) | ((a[:, 0] == b[:, 0]) & ((a[:, 1] < b[:, 1]) | ((a[:, 1] == b[:, 1]) & (a[:, 2] <= b[:, 2]))))
    key = np.where(first[:, None], k, np.concatenate([b, a], 1))
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return E[cnt[inv.ravel()] == 1]


# ------------------------------------------------------------------ the ground and what stands on it
def _near(P, lo, hi, r):
    """True for the boxes (lo, hi: (k, 2)) within r m of one of the points P (m, 2)."""
    m = np.zeros(len(lo), bool)
    for p in P:
        m |= np.all((lo - r < p) & (hi + r > p), axis=1)
    return m


class Site:
    """The built level around some points (AREA_R m): the terrain, the top faces of the carriageways, the other
    paved ground, the roofs, the wall tops and the railway, and the objects to keep clear of (as street_life.Site
    and lamps.obstacle_points have them), read from the tiles near the points only."""

    def __init__(self, zi, lv, pts, r=None):
        import network_mesh as pu
        import walls as pw
        import guardrail_mesh
        r = AREA_R if r is None else r
        self.P = np.asarray(pts, np.float64).reshape(-1, 2)
        blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
                   if o.get("class") == "TerrainBlock")
        pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
        self.pu = pu
        self.q = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))[1]
        none = [np.zeros((0, 3, 3))]
        road = self._faces(zi, lv, ["roads/surfaces"], r)
        self.carr = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if street_life.CARRIAGEWAY.match(m)] or none))
        self.paved = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if not street_life.CARRIAGEWAY.match(m)] or none))
        self.roof = road_mesh.TriSurface(np.concatenate(list(self._faces(zi, lv, ["buildings"], r).values()) or none))
        self.wall = road_mesh.TriSurface(np.concatenate(list(self._faces(zi, lv, ["walls"], r, lambda sn: "backfill" not in sn)
                                                             .values()) or none))
        self.rail = road_mesh.TriSurface(np.concatenate(list(self._faces(zi, lv, ["railway"], r).values()) or none))
        pts = []
        for f in zi.namelist():
            if f.endswith("items.level.json") and any(f"/MissionGroup/{g}/" in f for g in ("props", "roads/guardrails",
                                                                                            "roads/fences")):
                for o in read_items(zi, f):
                    sn = o.get("shapeName", "").lstrip("/")
                    pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
                    if o.get("class") != "TSStatic" or not _near(self.P, pos[None, :2], pos[None, :2], 1500.0)[0]:
                        continue
                    if sn in zi.NameToInfo:
                        V = optimize_level.parse(zi.read(sn).decode("utf-8"))[0][:, :2] + pos[:2]
                        pts.append(np.unique(np.round(V[_near(self.P, V, V, r)] * 10) / 10, axis=0))
                    elif _near(self.P, pos[None, :2], pos[None, :2], r)[0]:
                        pts.append(pos[None, :2])
            elif f.startswith(f"{lv}/forest/") and f.endswith(".forest4.json") and not guardrail_mesh.is_module(f):
                Q = np.array([json.loads(l)["pos"][:2] for l in zi.read(f).decode("utf-8").splitlines() if l.strip()]
                             ).reshape(-1, 2)
                pts.append(Q[_near(self.P, Q, Q, r)])
        gr = np.asarray(guardrail_mesh.module_points(zi), np.float64).reshape(-1, 2)
        pts.append(gr[_near(self.P, gr, gr, r)])
        self.obst = cKDTree(np.concatenate(pts + [np.full((1, 2), 1e7)]))

    def _faces(self, zi, lv, groups, r, keep=None):
        """{material: top faces} of the pipeline shapes of the groups within r m of the points (lamps.faces)."""
        out = {}
        for g in groups:
            f = f"{lv}/main/MissionGroup/{g}/items.level.json"
            if f not in zi.NameToInfo:
                continue
            for o in read_items(zi, f):
                sn = o.get("shapeName", "").lstrip("/")
                pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
                if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or (keep and not keep(sn)) \
                        or not _near(self.P, pos[None, :2], pos[None, :2], 1500.0)[0]:
                    continue
                V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
                W = V + pos
                for mat, idx in parts:
                    t = W[idx[:, 0]].reshape(-1, 3, 3)
                    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                    up = n[:, 2] > 0.3 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
                    t = t[up]
                    t = t[_near(self.P, t.min(1)[:, :2], t.max(1)[:, :2], r)]
                    if len(t):
                        out.setdefault(mat, []).append(t)
        return {m: np.concatenate(v) for m, v in out.items()}

    def terrain(self, x, y):
        return self.pu.terrain_top(self.q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))


class Ground:
    """The Site and the AI roads as the ground a station stands on; the canopies cut out of the survey are no roof
    any more."""

    def __init__(self, site, roads):
        self.site, self.roads = site, roads
        self.roof = site.roof

    def height(self, x, y):
        """Height of what one stands on: the road surfaces (carriageway or paved) near the terrain, else the terrain."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        zt = self.site.terrain(x, y)
        best = np.full(len(x), np.nan)
        for S in (self.site.carr, self.site.paved):
            zs = S.height(x, y, "near", zhint=zt)
            ok = np.isfinite(zs) & (np.abs(zs - zt) < 2.0) & ~(np.isfinite(best) & (best >= zs))
            best = np.where(ok, zs, best)
        return np.where(np.isfinite(best), best, zt)

    def without(self, polys):
        """The roofs of the level less the faces inside the polygons (the canopies cut out)."""
        if not polys:
            return
        u = shapely.union_all([p.buffer(NEAR) for p in polys])
        c = self.site.roof.t.mean(1)
        x0, y0, x1, y1 = u.bounds
        k = np.flatnonzero((c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1))
        drop = np.zeros(len(c), bool)
        drop[k[shapely.contains_xy(u, c[k, 0], c[k, 1])]] = True
        self.roof = road_mesh.TriSurface(self.site.roof.t[~drop])

    def lane(self, P, clear=LANE_CLEAR):
        """True where a point is within an AI road's half width + clear of its axis."""
        P = np.asarray(P, float).reshape(-1, 2)
        if not len(P):
            return np.zeros(0, bool)
        d, k = self.roads.tree.query(P, k=24, distance_upper_bound=12.0)
        ok = np.isfinite(d)
        W = np.where(ok, self.roads.W[np.minimum(k, len(self.roads.W) - 1)], 0.0)
        return np.any(ok & (d < W / 2 + clear), axis=1)

    def blocked(self, poly, clear=OBST_CLEAR, step=0.3, carriage=True, roof=True):
        """Why a footprint may not hold something solid (None: it may): a carriageway, an AI road's lane, a roof,
        a wall, the railway, an object within `clear` m."""
        P = grid_in(poly.buffer(0.15), step)
        if not len(P):
            return "empty"
        x, y = P[:, 0], P[:, 1]
        if carriage and np.isfinite(self.site.carr.height(x, y, "high")).any():
            return "carriageway"
        if self.lane(P).any():
            return "lane"
        if roof and np.isfinite(self.roof.height(x, y, "high")).any():
            return "building"
        if np.isfinite(self.site.wall.height(x, y, "high")).any():
            return "wall"
        if np.isfinite(self.site.rail.height(x, y, "high")).any():
            return "railway"
        c = poly.centroid
        k = self.site.obst.query_ball_point([c.x, c.y], math.sqrt(poly.area) + poly.length / 4 + clear)
        if k:
            Q = self.site.obst.data[k]
            if shapely.contains_xy(poly.buffer(clear), Q[:, 0], Q[:, 1]).any():
                return "objects"
        return None


def grid_in(poly, step):
    """Points every `step` m inside a polygon, and on its outline."""
    x0, y0, x1, y1 = poly.bounds
    X, Y = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    P = np.column_stack([X.ravel(), Y.ravel()])
    P = P[shapely.contains_xy(poly, P[:, 0], P[:, 1])] if len(P) else P.reshape(-1, 2)
    ring = poly.exterior
    B = np.array([ring.interpolate(s).coords[0] for s in np.arange(0, ring.length, step)]).reshape(-1, 2)
    return np.concatenate([P, B])


def _samples(T, step=0.25):
    """Points every `step` m on the triangles T."""
    out = []
    for t in T:
        e1, e2 = t[1] - t[0], t[2] - t[0]
        n = int(np.ceil(max(np.linalg.norm(e1), np.linalg.norm(e2), np.linalg.norm(t[2] - t[1])) / step)) + 1
        u, v = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
        ok = u + v <= 1 + 1e-9
        out.append(t[0] + u[ok][:, None] * e1 + v[ok][:, None] * e2)
    return np.concatenate(out) if out else np.zeros((0, 3))


def _poly(T):
    P = [shapely.Polygon(t[:, :2]) for t in T]
    return shapely.union_all([p for p in P if p.area > 1e-6]).buffer(0.01).buffer(-0.01)


def find_canopies(M, ground, p):
    """The canopy (one or more pieces) of the survey of the station at p: [{"poly", "faces": indices into M, "z"}],
    the nearest piece of roof that hangs over the ground with no wall under it, and the others like it within
    CANOPY_NEAR m of it; and what the pieces of roof near p were taken for."""
    lo, hi = M.t.min(1), M.t.max(1)
    near = np.all((lo[:, :2] - CANOPY_R - 40 < p) & (hi[:, :2] + CANOPY_R + 40 > p), axis=1)
    roofmat = np.array([str(m) in CANOPY_ROOFS for m in M.mat], bool)
    ri = np.flatnonzero(near & roofmat & (M.nz > 0.3))
    wi = np.flatnonzero(near & (np.abs(M.nz) < 0.3))
    WS = _samples(M.t[wi])
    wtree = cKDTree(WS[:, :2]) if len(WS) else None
    R = M.t[ri]
    n, lab = _pieces(R)
    cands, seen = [], {"pieces": 0, "size": 0, "height": 0, "walls": 0, "canopy": 0}
    for c in range(n):
        T = R[lab == c]
        poly = _poly(T)
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        d = poly.distance(shapely.Point(p))
        if d > CANOPY_R:
            continue
        seen["pieces"] += 1
        if not CANOPY_AREA[0] <= poly.area <= CANOPY_AREA[1]:
            seen["size"] += 1
            continue
        V = T.reshape(-1, 3)
        hag = V[:, 2] - ground.height(V[:, 0], V[:, 1])
        nz = M.nz[ri[lab == c]]
        if np.quantile(hag, 0.1) < CANOPY_HAG[0] or hag.max() > CANOPY_HAG[1] or nz.min() < 1 / math.hypot(1, CANOPY_SLOPE):
            seen["height"] += 1
            continue
        if wall_share(T, poly, WS, wtree, ground) > WALL_SHARE:
            seen["walls"] += 1
            continue
        cands.append((d, poly, T, ri[lab == c]))
    if not cands:
        return [], seen
    cands.sort(key=lambda c: c[0])
    z0 = cands[0][2][:, :, 2].mean()
    chosen = [cands[0]] + [c for c in cands[1:] if c[1].distance(cands[0][1]) < CANOPY_NEAR
                            and abs(c[2][:, :, 2].mean() - z0) < 1.5]
    out = []
    for d, poly, T, idx in chosen:
        out.append({"poly": poly, "faces": np.r_[idx, hanging(M, near, poly, T, idx, ground)],
                    "z": (float(T[:, :, 2].min()), float(T[:, :, 2].max()))})
    seen["canopy"] = len(out)
    return out, seen


def wall_share(T, poly, WS, wtree, ground):
    """Share of the outline of a piece of roof with a wall under it: the wall faces that reach the ground and end at
    its edge (a flat roof), or stand under it within its outline (a roof with eaves)."""
    if wtree is None:
        return 0.0
    sup = 0.0
    for a, b in _outline_edges(T):
        L = float(np.linalg.norm(b[:2] - a[:2]))
        for f in np.arange(0.25, L, 0.5) / max(L, 1e-9):
            q = a + (b - a) * f
            k = wtree.query_ball_point(q[:2], NEAR)
            if not k:
                continue
            zz = WS[k, 2]
            if abs(zz.max() - q[2]) < 0.5 and zz.min() < ground.height([q[0]], [q[1]])[0] + 1.0:
                sup += 0.5
    inner = poly.buffer(-0.5)
    if not inner.is_empty:
        x0, y0, x1, y1 = inner.bounds
        k = wtree.query_ball_point([(x0 + x1) / 2, (y0 + y1) / 2], math.hypot(x1 - x0, y1 - y0) / 2 + 0.1)
        if k:
            Q = WS[k]
            Q = Q[shapely.contains_xy(inner, Q[:, 0], Q[:, 1])]
            if len(Q):
                # a wall that reaches the ground and ends under this roof (one that passes it is another building's)
                _, first, inv = np.unique(np.floor(Q[:, :2] / 0.5).astype(np.int64), axis=0, return_index=True,
                                          return_inverse=True)
                inv = inv.ravel()
                zmin, zmax = np.full(len(first), np.inf), np.full(len(first), -np.inf)
                np.minimum.at(zmin, inv, Q[:, 2])
                np.maximum.at(zmax, inv, Q[:, 2])
                g = ground.height(Q[first, 0], Q[first, 1])
                zr = road_mesh.TriSurface(T).height(Q[first, 0], Q[first, 1], "high")
                sup += 0.5 * int(np.sum((zmin < g + 1.0) & (np.abs(zmax - zr) < 0.6)))
    return sup / max(poly.exterior.length, 1e-6)


def hanging(M, near, poly, T, idx, ground):
    """The faces hanging from a canopy of the survey (a skirt along its edge, its underside): the faces over its
    outline that neither reach the ground nor rise above it, joined to it through their edges."""
    zmax = T[:, :, 2].max()
    zone = poly.buffer(NEAR)
    lo, hi = M.t.min(1), M.t.max(1)
    x0, y0, x1, y1 = zone.bounds
    k = np.flatnonzero(near & (lo[:, 0] > x0) & (lo[:, 1] > y0) & (hi[:, 0] < x1) & (hi[:, 1] < y1) & (hi[:, 2] < zmax + 0.3))
    k = k[~np.isin(k, idx)]
    if not len(k):
        return np.zeros(0, np.int64)
    V = M.t[k]
    inside = np.all(shapely.contains_xy(zone, V[:, :, 0].ravel(), V[:, :, 1].ravel()).reshape(-1, 3), axis=1)
    c = V.mean(1)
    up = V[:, :, 2].min(1) > ground.height(c[:, 0], c[:, 1]) + 1.0
    k = k[inside & up]
    if not len(k):
        return k
    _, lab = _pieces(np.concatenate([T, M.t[k]]))
    return k[np.isin(lab[len(T):], np.unique(lab[:len(T)]))]


# ------------------------------------------------------------------ the AI roads
class Roads:
    """The AI roads of the level: points every metre with the width of the road there (tree, P, W, T)."""

    def __init__(self, zi, lv):
        P, W, T = [], [], []
        for r in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json"):
            n = np.asarray(r.get("nodes", []), np.float64)
            if len(n) < 2:
                continue
            s = np.r_[0, np.cumsum(np.hypot(*np.diff(n[:, :2], axis=0).T))]
            sd = np.linspace(0, s[-1], max(int(np.ceil(s[-1])), 1) + 1)
            q = np.column_stack([np.interp(sd, s, n[:, 0]), np.interp(sd, s, n[:, 1])])
            t = np.gradient(q, axis=0)
            P.append(q)
            W.append(np.interp(sd, s, n[:, 3]))
            T.append(t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9))
        self.P, self.W, self.T = np.concatenate(P), np.concatenate(W), np.concatenate(T)
        self.tree = cKDTree(self.P)


# ------------------------------------------------------------------ textures
def _rgb(c):
    return tuple(int(v) for v in c)


def emblem(d, kind, box, fg, accent):
    """A simple emblem of the parody brand in the box (x0, y0, x1, y1) of the drawing d."""
    x0, y0, x1, y1 = box
    cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, min(x1 - x0, y1 - y0) / 2
    if kind == "creature":                                          # a six-legged beast breathing fire
        d.ellipse([cx - r * 0.7, cy - r * 0.45, cx + r * 0.5, cy + r * 0.25], fill=_rgb(fg))
        for k in range(6):
            lx = cx - r * 0.55 + k * r * 0.2
            d.line([lx, cy + r * 0.2, lx - r * 0.08, cy + r * 0.7], fill=_rgb(fg), width=max(2, int(r * 0.09)))
        d.polygon([(cx + r * 0.5, cy - r * 0.2), (cx + r * 0.95, cy - r * 0.45), (cx + r * 0.8, cy - r * 0.05)],
                  fill=_rgb(accent))
    elif kind == "oval":
        d.ellipse([x0 + 2, cy - r * 0.6, x1 - 2, cy + r * 0.6], outline=_rgb(accent), width=max(3, int(r * 0.12)))
    elif kind == "flame":
        d.polygon([(cx, y0 + 2), (cx + r * 0.6, cy + r * 0.3), (cx, y1 - 2), (cx - r * 0.6, cy + r * 0.3)],
                  fill=_rgb(accent))
        d.polygon([(cx, cy - r * 0.2), (cx + r * 0.3, cy + r * 0.45), (cx, y1 - 6), (cx - r * 0.3, cy + r * 0.45)],
                  fill=_rgb(fg))
    elif kind == "wing":
        d.polygon([(x0 + 2, cy + r * 0.4), (cx, y0 + 4), (x1 - 2, cy - r * 0.1), (cx, cy + r * 0.2)], fill=_rgb(fg))
    elif kind == "drop":
        d.ellipse([cx - r * 0.55, cy - r * 0.1, cx + r * 0.55, cy + r * 0.9], fill=_rgb(accent))
        d.polygon([(cx, y0 + 2), (cx + r * 0.52, cy + r * 0.2), (cx - r * 0.52, cy + r * 0.2)], fill=_rgb(accent))
    elif kind == "bolt":
        d.polygon([(cx + r * 0.2, y0), (cx - r * 0.5, cy + r * 0.1), (cx, cy + r * 0.1), (cx - r * 0.2, y1),
                   (cx + r * 0.5, cy - r * 0.1), (cx, cy - r * 0.1)], fill=_rgb(accent))
    else:                                                          # a letter in a disk ("m", "c", "p")
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_rgb(accent))
        f = _font(r * 1.3)
        d.text((cx, cy), kind.upper(), font=f, fill=(255, 255, 255), anchor="mm")


def fascia_image(brand):
    """1024 x 128: the brand's band, its emblem and name in the middle."""
    _, name, bg, fg, accent, kind = BRANDS[brand]
    W, H = 1024 * SS, 128 * SS
    im = Image.new("RGB", (W, H), _rgb(bg))
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 14 * SS, W, H], fill=_rgb(accent))
    f = _font(78 * SS)
    tw = d.textlength(name, font=f)
    x = (W - tw) / 2 + 50 * SS
    emblem(d, kind, (x - 120 * SS, 10 * SS, x - 20 * SS, H - 22 * SS), fg, accent)
    d.text((x, H / 2 - 6 * SS), name, font=f, fill=_rgb(fg), anchor="lm")
    return im.resize((1024, 128), Image.LANCZOS)


def prices_image(st, w=512, h=1024, header=0.32):
    """The totem's face (w x h): the brand on top, the grades and their prices under it."""
    _, name, bg, fg, accent, kind = BRANDS[st["brand"]]
    W, H = w * SS, h * SS
    im = Image.new("RGB", (W, H), (245, 245, 242))
    d = ImageDraw.Draw(im)
    hh = int(H * header)
    d.rectangle([0, 0, W, hh], fill=_rgb(bg))
    emblem(d, kind, (W * 0.3, hh * 0.08, W * 0.7, hh * 0.62), fg, accent)
    f = _font(min(H * 0.07, W / max(len(name), 4) * 1.5))
    d.text((W / 2, hh * 0.82), name, font=f, fill=_rgb(fg), anchor="mm")
    rows = st["grades"]
    rh = (H - hh) / max(len(rows), 3)
    fl, fp = _font(rh * 0.24, bold=True), _font(rh * 0.5, bold=True)
    for i, g in enumerate(rows):
        y = hh + i * rh
        label, label2, col = GRADES[g]
        d.rectangle([W * 0.04, y + rh * 0.12, W * 0.18, y + rh * 0.88], fill=col)
        d.text((W * 0.22, y + rh * 0.32), label, font=fl, fill=(30, 30, 30), anchor="lm")
        d.text((W * 0.22, y + rh * 0.66), label2, font=_font(rh * 0.16, bold=False), fill=(80, 80, 80), anchor="lm")
        d.rectangle([W * 0.58, y + rh * 0.14, W * 0.97, y + rh * 0.86], fill=(20, 20, 22))
        d.text((W * 0.955, y + rh * 0.5), "%.2f" % st["prices"][g], font=fp, fill=(255, 70, 40), anchor="rm")
    return im.resize((w, h), Image.LANCZOS)


def pump_image(st, w=256, h=512):
    """A dispenser's face: the brand's header, the litres and francs counter, the grade buttons, the keypad."""
    _, name, bg, fg, accent, kind = BRANDS[st["brand"]]
    W, H = w * SS, h * SS
    im = Image.new("RGB", (W, H), (232, 233, 230))
    d = ImageDraw.Draw(im)
    hh = int(H * 0.16)
    d.rectangle([0, 0, W, hh], fill=_rgb(bg))
    d.text((W / 2, hh / 2), name, font=_font(hh * 0.38), fill=_rgb(fg), anchor="mm")
    d.rectangle([W * 0.1, H * 0.2, W * 0.9, H * 0.42], fill=(25, 28, 30))
    fm = _font(H * 0.045)
    d.text((W * 0.85, H * 0.25), "CHF  58.40", font=fm, fill=(120, 230, 120), anchor="ra")
    d.text((W * 0.85, H * 0.32), "LT   31.74", font=fm, fill=(120, 230, 120), anchor="ra")
    for i, g in enumerate(st["grades"][:4]):
        col = GRADES[g][2]
        y = H * (0.47 + i * 0.07)
        d.rectangle([W * 0.1, y, W * 0.32, y + H * 0.05], fill=col)
        d.text((W * 0.36, y + H * 0.025), GRADES[g][0], font=_font(H * 0.03), fill=(30, 30, 30), anchor="lm")
        d.text((W * 0.9, y + H * 0.025), "%.2f" % st["prices"][g], font=_font(H * 0.035), fill=(30, 30, 30), anchor="rm")
    for r_ in range(4):
        for c_ in range(3):
            x, y = W * (0.3 + c_ * 0.14), H * (0.78 + r_ * 0.045)
            d.rectangle([x, y, x + W * 0.1, y + H * 0.035], fill=(70, 72, 75))
    d.rectangle([0, H * 0.96, W, H], fill=_rgb(accent))
    return im.resize((w, h), Image.LANCZOS)


def ceiling_image(n=256):
    """The canopy's ceiling: white panels, a recessed light in the middle of the tile."""
    im = Image.new("RGB", (n, n), (236, 237, 235))
    d = ImageDraw.Draw(im)
    for k in range(0, n, n // 4):
        d.line([k, 0, k, n], fill=(214, 215, 213), width=2)
    d.rectangle([n * 0.36, n * 0.42, n * 0.64, n * 0.58], fill=(255, 255, 250), outline=(180, 180, 178), width=3)
    return im


def bands_image(n=64):
    im = Image.new("RGB", (n, n * 2), (240, 200, 0))
    d = ImageDraw.Draw(im)
    for k in range(0, n * 2, n // 2):
        d.rectangle([0, k, n, k + n // 4], fill=(25, 25, 25))
    return im


def _png(im):
    import io
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


# ------------------------------------------------------------------ geometry
def quad(a, b, c, d, out, uv=None):
    """Two triangles a-b-c-d facing `out`, with texture coordinates (4, 2) or none."""
    t = np.array([a, b, c, a, c, d], np.float64)
    u = None if uv is None else np.array([uv[0], uv[1], uv[2], uv[0], uv[2], uv[3]], np.float64)
    n = np.cross(t[1] - t[0], t[2] - t[0])
    if float(n @ np.asarray(out, float)) < 0:
        t = t[[0, 2, 1, 3, 5, 4]]
        if u is not None:
            u = u[[0, 2, 1, 3, 5, 4]]
    return t, u


def box(c, u, half, z0, z1):
    """Triangles (36, 3) of a box about c (2,), axis u, half sizes (along, across), from z0 to z1."""
    u = np.asarray(u, float) / max(np.hypot(*u), 1e-9)
    v = np.array([-u[1], u[0]])
    q = [c + u * half[0] + v * half[1], c - u * half[0] + v * half[1], c - u * half[0] - v * half[1],
         c + u * half[0] - v * half[1]]
    out = []
    for k in range(4):
        a, b = q[k], q[(k + 1) % 4]
        m = (a + b) / 2 - c
        out.append(quad(np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z1], np.r_[m, 0])[0])
    out.append(quad(*[np.r_[p, z1] for p in q], (0, 0, 1))[0])
    out.append(quad(*[np.r_[p, z0] for p in q], (0, 0, -1))[0])
    return np.concatenate(out)


class Builder:
    """Mesh builders of one station: canopy (no collision), solid (collision), small (no collision)."""

    def __init__(self):
        self.mb = {k: bng.MeshBuilder() for k in ("canopy", "solid", "small")}

    def add(self, kind, mat, V, uv=None):
        V = np.asarray(V, np.float64).reshape(-1, 3)
        self.mb[kind].add(mat, V, uvs=uv if uv is not None else V[:, :2] / 2.0, normals=bng.flat_normals_soup(V))


def canopy_mesh(B, rect, z_ceil, mats):
    """The slab, the fascia all round (its strip textured, the logo in the middle of each side), the ceiling."""
    P = np.asarray(rect.exterior.coords)[:4]
    c = P.mean(0)
    zt = z_ceil + SLAB
    # ceiling (faces down), top (up)
    uvs = P / CEIL_TILE
    t, u = quad(*[np.r_[p, z_ceil] for p in P], (0, 0, -1), uvs)
    B.add("canopy", mats["ceiling"], t, u)
    t, _ = quad(*[np.r_[p, zt + 0.02] for p in P], (0, 0, 1))
    B.add("canopy", mats["roof"], t)
    for k in range(4):
        a, b = P[k], P[(k + 1) % 4]
        L = float(np.hypot(*(b - a)))
        out = (a + b) / 2 - c
        out = out / max(np.hypot(*out), 1e-9)
        if (b - a) @ np.array([-out[1], out[0]]) < 0:      # a on the left of someone looking at the side: the name reads
            a, b = b, a
        a2, b2 = a + out * FASCIA_T, b + out * FASCIA_T
        z0, z1 = z_ceil - FASCIA_DROP, zt + FASCIA_H - SLAB - FASCIA_DROP
        # u: the logo strip centred on the side, the plain ends of the strip beyond it
        u0 = 0.5 - (L / 2) / STRIP_M
        u1 = 0.5 + (L / 2) / STRIP_M
        if u1 - u0 > 1:
            u0, u1 = 0.5 - CONTENT_M / STRIP_M / 2 - (L - CONTENT_M) / 2 / STRIP_M, 0.5 + CONTENT_M / STRIP_M / 2 + (L - CONTENT_M) / 2 / STRIP_M
        t, uv = quad(np.r_[a2, z0], np.r_[b2, z0], np.r_[b2, z1], np.r_[a2, z1], np.r_[out, 0],
                     [(u0, 0), (u1, 0), (u1, 1), (u0, 1)])
        B.add("canopy", mats["fascia"], t, np.clip(uv, -0.5, 1.5))
        t, _ = quad(np.r_[a2, z0], np.r_[b2, z0], np.r_[b, z0], np.r_[a, z0], (0, 0, -1))
        B.add("canopy", mats["white"], t)
        t, _ = quad(np.r_[a2, z1], np.r_[b2, z1], np.r_[b, z1], np.r_[a, z1], (0, 0, 1))
        B.add("canopy", mats["white"], t)


def island_mesh(B, c, u, length, zg, pillars, n_disp, z_ceil, mats):
    """A pump island with round-ended kerb, its bollards, pillars up to the canopy, dispensers, nozzles, hoses."""
    u = np.asarray(u, float) / max(np.hypot(*u), 1e-9)
    v = np.array([-u[1], u[0]])
    zt = zg + ISLAND_H
    B.add("solid", mats["concrete"], box(c, u, (length / 2 - ISLAND_W / 2, ISLAND_W / 2), zg - 0.1, zt))
    for s in (-1, 1):                                               # the round ends
        e = c + u * s * (length / 2 - ISLAND_W / 2)
        ang = np.linspace(-np.pi / 2, np.pi / 2, 9)
        ring = [e + (u * s * math.cos(a) + v * math.sin(a)) * ISLAND_W / 2 for a in ang]
        for p, q in zip(ring[:-1], ring[1:]):
            m = (p + q) / 2 - e
            B.add("solid", mats["concrete"], quad(np.r_[p, zg - 0.1], np.r_[q, zg - 0.1], np.r_[q, zt], np.r_[p, zt],
                                                  np.r_[m, 0])[0])
            B.add("solid", mats["concrete"], quad(np.r_[e, zt], np.r_[p, zt], np.r_[q, zt], np.r_[q, zt], (0, 0, 1))[0][:3])
        bc = c + u * s * (length / 2 - 0.25)                         # yellow and black bollard
        ang = np.linspace(0, 2 * np.pi, 13)
        ring = [bc + (u * math.cos(a) + v * math.sin(a)) * 0.08 for a in ang]
        for k in range(12):
            t, uv = quad(np.r_[ring[k], zt], np.r_[ring[k + 1], zt], np.r_[ring[k + 1], zt + 1.0],
                         np.r_[ring[k], zt + 1.0], np.r_[(ring[k] + ring[k + 1]) / 2 - bc, 0],
                         [(k / 12, 0), ((k + 1) / 12, 0), ((k + 1) / 12, 1), (k / 12, 1)])
            B.add("solid", mats["bands"], t, uv)
    for f in pillars:                                               # clad steel pillars
        B.add("solid", mats["steel"], box(c + u * f * (length / 2), u, (PILLAR / 2, PILLAR / 2), zt, z_ceil))
    spots = [0.0] if n_disp == 1 else [-0.25, 0.25]
    dw, dd, dh, hh = DISP
    for f in spots:
        p = c + u * f * length
        B.add("solid", mats["disp_body"], box(p, u, (dw / 2, dd / 2), zt, zt + dh))
        B.add("solid", mats["header"], box(p, u, (dw / 2 + 0.02, dd / 2 + 0.02), zt + dh, zt + dh + hh))
        for s in (-1, 1):                                           # the faces with the prices, both sides
            n = v * s
            a, b = p - u * dw / 2 * s + n * (dd / 2 + 0.005), p + u * dw / 2 * s + n * (dd / 2 + 0.005)
            t, uv = quad(np.r_[a, zt + 0.15], np.r_[b, zt + 0.15], np.r_[b, zt + dh + hh - 0.02],
                         np.r_[a, zt + dh + hh - 0.02], np.r_[n, 0], [(0, 0), (1, 0), (1, 1), (0, 1)])
            B.add("solid", mats["pump"], t, uv)
            for k in range(3):                                      # nozzles in their holsters, hoses down
                h = p + u * (k - 1) * 0.3 + n * (dd / 2 + 0.06)
                B.add("small", mats["black"], box(h, u, (0.04, 0.06), zt + 1.05, zt + 1.3))
                B.add("small", mats["nozzle_" + str(k % 3)], box(h + n * 0.03, u, (0.03, 0.05), zt + 1.25, zt + 1.4))
                B.add("small", mats["black"], box(h + n * 0.08, u, (0.02, 0.02), zt + 0.4, zt + 1.06))


def totem_mesh(B, c, u, zg, mats):
    """The price totem: a plinth, the post with both faces showing the prices."""
    w, d, h, plinth = TOTEM
    u = np.asarray(u, float) / max(np.hypot(*u), 1e-9)
    n = np.array([-u[1], u[0]])
    B.add("solid", mats["concrete"], box(c, u, (w / 2 + 0.1, d / 2 + 0.1), zg - 0.1, zg + 0.25))
    B.add("solid", mats["header"], box(c, u, (w / 2, d / 2), zg + 0.25, zg + plinth))
    for s in (-1, 1):
        nn = n * s
        a, b = c - u * w / 2 * s + nn * d / 2, c + u * w / 2 * s + nn * d / 2
        t, uv = quad(np.r_[a, zg + plinth], np.r_[b, zg + plinth], np.r_[b, zg + h], np.r_[a, zg + h], np.r_[nn, 0],
                     [(0, 0), (1, 0), (1, 1), (0, 1)])
        B.add("solid", mats["totem"], t, uv)
    for s in (-1, 1):
        e = c + u * s * w / 2
        a, b = e + n * d / 2, e - n * d / 2
        B.add("solid", mats["white"], quad(np.r_[a, zg + plinth], np.r_[b, zg + plinth], np.r_[b, zg + h], np.r_[a, zg + h],
                                           np.r_[u * s, 0])[0])
    q = [c + u * w / 2 + n * d / 2, c - u * w / 2 + n * d / 2, c - u * w / 2 - n * d / 2, c + u * w / 2 - n * d / 2]
    B.add("solid", mats["white"], quad(*[np.r_[p, zg + h] for p in q], (0, 0, 1))[0])


# ------------------------------------------------------------------ the step
def materials(sid_keys):
    import italy_mats as it
    t = f"/levels/{LEVEL_NAME}/{D}"
    m = [it.material("mp_fuel_concrete", "m_concrete_old", ground_type="CONCRETE"),
         bng.material("mp_fuel_steel", base_color=[0.82, 0.83, 0.84, 1], roughness=0.35, metallic=0.7, ground_type="METAL"),
         bng.material("mp_fuel_white", base_color=[0.93, 0.93, 0.92, 1], roughness=0.5),
         bng.material("mp_fuel_roof", base_color=[0.45, 0.46, 0.47, 1], roughness=0.8),
         bng.material("mp_fuel_black", base_color=[0.05, 0.05, 0.05, 1], roughness=0.6),
         bng.material("mp_fuel_disp", base_color=[0.86, 0.87, 0.86, 1], roughness=0.4, metallic=0.3, ground_type="METAL"),
         bng.material("mp_fuel_ceiling", f"{t}/t_fuel_ceiling_b.color.png", roughness=0.4),
         bng.material("mp_fuel_bands", f"{t}/t_fuel_bands_b.color.png", roughness=0.5)]
    for g, col in (("0", (0, 140, 70)), ("1", (20, 80, 170)), ("2", (25, 25, 25))):
        m.append(bng.material(f"mp_fuel_nozzle_{g}", base_color=[c / 255 for c in col] + [1], roughness=0.4))
    for key, (_, name, bg, fg, accent, kind) in BRANDS.items():
        if key not in sid_keys["brands"]:
            continue
        m.append(bng.material(f"mp_fuel_{key}_fascia", f"{t}/t_fuel_{key}_fascia_b.color.png", roughness=0.4))
        m.append(bng.material(f"mp_fuel_{key}_header", base_color=[c / 255 for c in bg] + [1], roughness=0.4))
    for sid in sid_keys["stations"]:
        m.append(bng.material(f"mp_fuel_{sid}_totem", f"{t}/t_fuel_{sid}_totem_b.color.png", roughness=0.35))
        m.append(bng.material(f"mp_fuel_{sid}_pump", f"{t}/t_fuel_{sid}_pump_b.color.png", roughness=0.35))
    return m


def new_canopy(ground, roads, p):
    """A canopy built new on the paved ground beside the road nearest the station's point, or None."""
    d, k = roads.tree.query(p)
    a = roads.T[k]
    v = p - roads.P[k]
    side = np.sign(float(a[0] * v[1] - a[1] * v[0])) or 1.0          # numpy 2: no 2D np.cross
    nrm = np.array([-a[1], a[0]]) * side                            # from the road towards the station
    for along, across in NEW_CANOPY:
        for push in np.arange(roads.W[k] / 2 + 2.0, roads.W[k] / 2 + 14.0, 1.0):
            for shift in (0.0, -5.0, 5.0):
                c = roads.P[k] + nrm * (push + across / 2) + a * shift
                poly = shapely.Polygon([c + a * sa * along / 2 + nrm * sb * across / 2
                                        for sa, sb in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
                if ground.blocked(poly, carriage=True) is None:
                    G = grid_in(poly, 1.0)
                    paved = np.isfinite(ground.site.paved.height(G[:, 0], G[:, 1], "high"))
                    if paved.mean() >= PAVED_SHARE:
                        return poly
    return None


_VILLAGES = {}


def village_of(zi, lv, x, y):
    """Name of the village nearest (x, y): the spawn points of the level, one per village."""
    if lv not in _VILLAGES:
        pts = [(o["name"][6:].replace("_", " ").title().replace(" D ", " d'").replace("Paese", "").strip(), o["position"][:2])
               for o in read_items(zi, f"{lv}/main/MissionGroup/PlayerDropPoints/items.level.json")
               if o.get("name", "").startswith("spawn_") and o["name"] not in ("spawn_mid", "spawn_pura", "spawn_magliaso")]
        _VILLAGES[lv] = pts
    pts = _VILLAGES[lv]
    if not pts:
        return ""
    return min(pts, key=lambda p: math.hypot(p[1][0] - x, p[1][1] - y))[0]


def refuel_points(facilities, files, lv, zi):
    """v3.0 review: the stations as gas stations of the game (freeroam_facilities): for every side of every dispenser
    a BeamNGGameplayArea where the car stops and a BeamNGPointOfInterest over it (the pump icon), named as
    facilities/facilities.facilities.json lists them; the station's outline as a zone of facilities.sites.json.
    Up to v3.0 the game found no gas station on the map, and a car could not be refuelled there."""
    objs, gas, zones = [], [], []
    for st, sid, rect, pumps in facilities:
        node = f"fuel_{sid}"
        pl = []
        for k, (p, u, z) in enumerate(pumps, 1):
            rot = [round(v, 6) for v in bng.rot_local_x_to(math.atan2(u[1], u[0]))]
            area, icon = f"{node}_pump_area_{k}", f"{node}_pump_icon_{k}"
            objs.append({"name": icon, "class": "BeamNGPointOfInterest", "persistentId": bng.pid(), "__parent": "fuel",
                         "position": [round(float(p[0]), 3), round(float(p[1]), 3), round(float(z) + 1.75, 3)],
                         "rotationMatrix": rot, "scale": [0.1, 0.1, 0.1]})
            objs.append({"name": area, "class": "BeamNGGameplayArea", "persistentId": bng.pid(), "__parent": "fuel",
                         "position": [round(float(p[0]), 3), round(float(p[1]), 3), round(float(z), 3)],
                         "rotationMatrix": rot, "scale": PUMP_AREA})
            pl.append([area, icon])
        # the parody brand and the village (never the real name of OSM)
        # (the game shows the name: "Gas Station <name>")
        title = BRANDS[st["brand"]][1] + " " + village_of(zi, lv, st["x"], st["y"])
        gas.append({"name": title.strip() or node, "description": "Benzina, diesel" if "diesel" in st["grades"]
                    else "Benzina", "preview": "fuel.jpg", "energyTypes": ["gasoline", "diesel", "unknown"], "pumps": pl})
        Z = float(np.median([z for _, _, z in pumps]))
        zones.append({"name": node, "oldId": len(zones) + 1, "color": [1, 1, 1], "customFields": {"values": {}, "names": {}, "tags": {}, "types": {}},
                      "bot": {"active": False, "normal": [0, 0, -1], "pos": [0, 0, -10]},
                      "top": {"active": False, "normal": [0, 0, 1], "pos": [0, 0, 10]},
                      "vertices": [[round(float(x), 3), round(float(y), 3), round(Z, 3)]
                                   for x, y in list(rect.exterior.coords)[:4]]})
    if gas:
        files[f"{lv}/facilities/facilities.facilities.json"] = json.dumps({"gasStations": gas}, indent=1).encode("utf-8")
        files[f"{lv}/facilities.sites.json"] = json.dumps(
            {"description": "The petrol stations of the map (fuel_stations.py)", "dir": f"/levels/{LEVEL_NAME}/",
             "filename": "facilities.sites.json", "name": "facilities.sites.json", "locations": {},
             "parkingSpots": [], "zones": zones}, indent=1).encode("utf-8")
        import io
        b = io.BytesIO()                                            # the picture of the stations: a price totem
        prices_image(facilities[0][0]).convert("RGB").save(b, "JPEG", quality=85)
        files[f"{lv}/facilities/fuel.jpg"] = b.getvalue()
    return objs


def fuel_stations_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    roads = Roads(zi, lv)
    sts, why = stations(roads)
    rep = {"stations": len(sts), "from_chargers": sum(CHARGING_ONLY in s["tags"] for s in sts), "left_out": why, "canopies_replaced": 0, "canopies_new": 0, "no_canopy": 0,
           "islands": 0, "dispensers": 0, "totems": 0, "triangles": 0}
    if not sts:
        print("fuel stations: none", flush=True)
        return rep
    pts = np.array([[s["x"], s["y"]] for s in sts])
    site = Site(zi, lv, pts)
    ground = Ground(site, roads)
    M = Meshes(zi, lv, ["buildings", "buildings/details", "buildings/extras"], pts, CANOPY_R + 40.0)
    drop = {}                                                       # shape -> {list index: triangles}
    facilities = []                                                 # v3.0 review: the game's gas stations
    files, objs, used_brands, done = {}, [], set(), []
    for st in sts:
        p = np.array([st["x"], st["y"]])
        cans, seen = find_canopies(M, ground, p)
        polys = [c["poly"] for c in cans]
        for c in cans:
            for si, pi, ti in M.ref[c["faces"]]:
                drop.setdefault(M.shapes[si], {}).setdefault(int(pi), set()).add(int(ti))
        ground.without(polys)
        if cans:
            rect = shapely.union_all(polys).minimum_rotated_rectangle
            rep["canopies_replaced"] += 1
        elif CHARGING_ONLY in st["tags"]:                           # a charger alone, no petrol station there
            rep["chargers_without_canopy"] = rep.get("chargers_without_canopy", 0) + 1
            continue
        else:
            rect = new_canopy(ground, roads, p)
            if rect is None:
                rep["no_canopy"] += 1
                continue
            rep["canopies_new"] += 1
        R = np.asarray(rect.exterior.coords)[:4]
        e0, e1 = R[1] - R[0], R[2] - R[1]
        u = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
        Lc, Wc = max(np.hypot(*e0), np.hypot(*e1)), min(np.hypot(*e0), np.hypot(*e1))
        u = u / max(np.hypot(*u), 1e-9)
        v = np.array([-u[1], u[0]])
        c = R.mean(0)
        G = grid_in(rect, 1.0)
        zg_all = ground.height(G[:, 0], G[:, 1])
        z_ceil = max(float(np.median(zg_all)) + CLEAR_H, float(zg_all.max()) + MIN_CLEAR)
        sid = re.sub(r"[^a-z0-9]", "", str(st["id"]).lower())[-10:]
        mats = {"ceiling": "mp_fuel_ceiling", "roof": "mp_fuel_roof", "white": "mp_fuel_white",
                "fascia": f"mp_fuel_{st['brand']}_fascia", "concrete": "mp_fuel_concrete", "steel": "mp_fuel_steel",
                "bands": "mp_fuel_bands", "disp_body": "mp_fuel_disp", "header": f"mp_fuel_{st['brand']}_header",
                "pump": f"mp_fuel_{sid}_pump", "totem": f"mp_fuel_{sid}_totem", "black": "mp_fuel_black",
                "nozzle_0": "mp_fuel_nozzle_0", "nozzle_1": "mp_fuel_nozzle_1", "nozzle_2": "mp_fuel_nozzle_2"}
        B = Builder()
        pumps = []
        canopy_mesh(B, rect, z_ceil, mats)
        # the islands: rows across the canopy, each along its long side
        n_rows = int(np.clip(round(Wc / ROW_PITCH), 1, 3))
        length = float(np.clip(Lc * 0.5, *ISLAND_LEN))
        for i in range(n_rows):
            off = (i - (n_rows - 1) / 2) * (Wc / n_rows)
            ci = c + v * off
            poly = shapely.Polygon([ci + u * a * length / 2 + v * b * ISLAND_W / 2 for a, b in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
            if ground.blocked(poly, clear=0.1) not in (None, "objects"):
                continue
            zg = float(np.median(ground.height(*grid_in(poly, 0.5).T)))
            nd = 2 if length >= TWO_PUMPS else 1
            island_mesh(B, ci, u, length, zg, (-0.5, 0.5), nd, z_ceil, mats)
            for f in ([0.0] if nd == 1 else [-0.25, 0.25]):            # v3.0 review: where a car stops to refuel
                for sg in (-1, 1):
                    pumps.append((ci + u * f * length + v * sg * (DISP[1] / 2 + PUMP_OFF), u, zg + ISLAND_H))
            rep["islands"] += 1
            rep["dispensers"] += nd
        # the totem beside the road, at the side of the canopy nearest it
        d, k = roads.tree.query(c)
        for shift in np.arange(0, TOTEM_SEARCH, 2.0):
            done_t = False
            for sg in (1, -1):
                kk = roads.tree.query(roads.P[k] + roads.T[k] * shift * sg)[1]
                a = roads.T[kk]
                v = c - roads.P[kk]
                side = np.sign(float(a[0] * v[1] - a[1] * v[0])) or 1.0
                nrm = np.array([-a[1], a[0]]) * side
                q = roads.P[kk] + nrm * (roads.W[kk] / 2 + TOTEM_GAP + TOTEM[1] / 2 + 0.3)
                poly = shapely.Polygon([q + a * s1 * TOTEM[0] / 2 + nrm * s2 * TOTEM[1] / 2
                                        for s1, s2 in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
                if rect.buffer(0.5).intersects(poly) or ground.blocked(poly) is not None:
                    continue
                totem_mesh(B, q, a, float(ground.height([q[0]], [q[1]])[0]), mats)
                rep["totems"] += 1
                done_t = True
                break
            if done_t:
                break
        used_brands.add(st["brand"])
        done.append(sid)
        if pumps:
            facilities.append((st, sid, rect, pumps))
        files[f"{lv}/{D}/t_fuel_{sid}_totem_b.color.png"] = _png(prices_image(st))
        files[f"{lv}/{D}/t_fuel_{sid}_pump_b.color.png"] = _png(pump_image(st))
        with tempfile.TemporaryDirectory() as tmp:
            for kind, mb in B.mb.items():
                if mb.empty():
                    continue
                f = os.path.join(tmp, "s.dae")
                origin = np.r_[c, 0.0]
                mb.write_dae(f, name=f"fuel_{sid}_{kind}", origin=origin)
                rel = f"{D}/fuel_{sid}_{kind}.dae"
                files[f"{lv}/{rel}"] = open(f, "rb").read()
                rep["triangles"] += mb.triangle_count()
                ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=(kind == "solid"), decal=False)
                ob["__parent"] = "fuel"
                objs.append(ob)
    for brand in used_brands:
        files[f"{lv}/{D}/t_fuel_{brand}_fascia_b.color.png"] = _png(fascia_image(brand))
    files[f"{lv}/{D}/t_fuel_ceiling_b.color.png"] = _png(ceiling_image())
    files[f"{lv}/{D}/t_fuel_bands_b.color.png"] = _png(bands_image())
    files[f"{lv}/{D}/fuel.materials.json"] = json.dumps({m["name"]: m for m in materials(
        {"brands": used_brands, "stations": done})}, indent=1).encode("utf-8")
    objs += refuel_points(facilities, files, lv, zi)
    files[f"{lv}/main/MissionGroup/props/fuel/items.level.json"] = \
        ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
    rep["refuel_stations"] = len(facilities)
    p_items = f"{lv}/main/MissionGroup/props/items.level.json"
    rows = read_items(zi, p_items)
    if not any(r.get("name") == "fuel" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "fuel", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    files[p_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    for sn, dr in drop.items():                                     # the survey's canopies out of the building tiles
        files[sn] = drop_triangles(M.text[sn], dr).encode("utf-8")
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in files or SHAPE.search(nm):
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(n, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("fuel stations:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
