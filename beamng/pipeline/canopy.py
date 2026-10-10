"""Trees and shrubs of a built level against its roads, its ground and its solid meshes (v2.1).

trees.py puts a tree where the canopy model of swissSURFACE3D has a crown top, vegetation.py gives it
the vanilla model whose width best matches the crown measured there, and clearance.py keeps the
trunks off the drivable surfaces. The crowns themselves were never checked: a vanilla model scaled to
the measured height carries its foliage down to a third of it (broad-leaved trees) or a fifth
(conifers), and next to a road it hung into the carriageway at the height of a car. Real roads are
kept clear by pruning: in Switzerland nothing may hang into the clearance profile, 4.50 m over the
carriageway and 2.50 m over sidewalks and footpaths. The v2.0 release had 3733 trees with their
crown in the profile (up to 7.1 m into it), 14 430 forest items more than 0.3 m above the ground (the
terrain is carved along the roads after the trees get their height from the DTM), 1052 more than 1 m
under it and 144 trunks inside walls and buildings (check()).

This step reads everything from the level folder once the rest is built (build_level.py runs it after
writing the level; `python canopy.py <level folder>` runs it on any built level):
1. crowns: no foliage of a tree in the clearance profile of a drivable surface, CLEAR[class] m over
   its faces (EDGE_TOL m of overhang allowed at the edges). A tree that reaches in moves outwards,
   up to MOVE m, onto free ground (not onto a surface, a wall, a building, another trunk or into
   the lake); if that is not enough it takes the narrowest model of its kind at the same height,
   then a smaller scale; a tree that still reaches in is removed. Shrubs and hedges are kept off
   the surfaces by clearance.py already; they are checked here too and moved or removed alike.
2. trunks: none inside a wall, a building, a bridge parapet, a guardrail or a fence;
3. ground: every item stands on the ground under it (the terrain, or the ground mesh behind the
   retaining walls where that is higher), SINK m into it at the lowest point around its trunk.
Crown shapes are the ones render3d.py draws: broad-leaved crowns an ellipsoid from 0.34 h to the
top, conifers a cone from 0.18 h (full radius) to the top, shrubs from the ground, all measured from
the position of the item (the origin of the model, SINK m in the ground); the radius is half the mean
horizontal extent of the model (dati/asset_bounds.json) at its scale.
check_level.py measures the same things with crown_intrusion() and ground_offsets().
    python canopy.py [level folder]
"""
import glob, json, os, sys, time
import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine
from scipy.spatial import cKDTree
import guardrail_mesh
import osm_surface
import patch_release as pr
from road_mesh import TriSurface

HERE = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(os.path.dirname(HERE), "dati")
LEVEL_PREFIX = "/levels/"

# drivable surfaces: class 0 carriageways (and bridge decks), 1 sidewalks, yards and squares, 2 paths
SURFACE_CLASS = {"mp_road_asphalt_fresh": 0, "mp_sidewalk": 1,
                 # the railway bed (railway.py) is kept clear like a carriageway
                 "mp_ballast": 0, "mp_sleeper": 0, "mp_rail_head": 0, "mp_rail_deck": 0,
                 # every surface of the carriageways, yards and paths (v2.4: gravel, earth, setts, cobbles)
                 **{m: 0 for m in osm_surface.ROAD_MATS}, **{m: 1 for m in osm_surface.HARD_MATS},
                 **{m: 2 for m in osm_surface.PATH_MATS}}
CLASS_NAMES = ("carreggiata", "marciapiede o piazzale", "sentiero")
CLEAR = np.array([4.5, 2.5, 2.5])          # m of clearance profile over the faces of each class
EDGE_TOL = 0.3                              # m of crown allowed over the edge of a surface under the profile
TRUNK_CLEAR = np.array([1.0, 1.0, 0.5])     # m from a trunk to a surface of each class (clearance.py: 1 m roads, yards, sidewalks)
TRUNK_R = 0.3                               # m, trunk radius against walls, buildings, parapets, fences
TRUNK_GAP = 0.8                             # m between two trunks after a move
MOVE = 3.0                                  # m, farthest a tree moves (clearance.MOVE_TREE)
SHRUB_MOVE = 1.5                            # m, farthest a shrub or hedge moves (clearance.MAX_SHIFT)
SCALES = (0.85, 0.7)                        # smaller scales tried before a tree is removed
SINK = {"tree": 0.15, "bush": 0.10, "hedge": 0.10}
FLOAT_TOL = 0.3                             # m of an item's base above the ground (check_level)
PROP_R = 0.8                                # m from a trunk to a vanilla prop (street light, bench)
MAX_DROP = 0.5                              # m, lowest a base goes under the ground at the trunk
UNDER_WATER = 0.3                           # m under the lake surface: a trunk moved there is in the lake
BURY_TOL = 1.0                              # m of an item's base under the ground (check_level)
RES = 0.5
TILE = 256.0
MARGIN = 20.0                               # m of context around a tile: the widest crown and a move
MAX_R = 14.0                                # m, crowns wider than this are measured as this wide
SOLID_ROAD_MATS = ("mp_road_wall", "mp_bridge_parapet")
SOLID_GROUPS = ("walls", "buildings", "roads/guardrails", "roads/fences", "props")
SOLID_NAMES = ("parapetto o fianco della strada", "muro", "edificio", "guardrail", "recinzione", "palo o cartello",
               "lampione o arredo")
CONIFER = ("fir", "pine", "spruce", "larch", "cypress")


# ---------------------------------------------------------------------- crowns
def kind_of(name):
    n = name.lower()
    if "hedge" in n:
        return "hedge"
    if "bush" in n:
        return "bush"
    if any(c in n for c in CONIFER):
        return "conifer"
    return "broadleaf"


def crown_radius(kind, h, r, a, b):
    """Widest horizontal radius of crowns of kind ('broadleaf', 'conifer', 'bush', 'hedge'), height
    h and radius r (arrays or scalars) between the heights a and b over their base (arrays): 0 where
    the crown does not reach into [a, b]."""
    h, r, a, b = (np.asarray(v, np.float64) for v in (h, r, a, b))
    if kind == "conifer":
        zb, zt = 0.18 * h, 1.02 * h
        lo = np.maximum(a, zb)
        return np.where(lo <= np.minimum(b, zt), r * (1.0 - (lo - zb) / np.maximum(zt - zb, 1e-6)), 0.0)
    if kind == "broadleaf":
        hh = 0.33 * h
        zc = h - hh
    else:                                    # shrubs and hedges: from the ground to the top
        hh = 0.5 * h
        zc = hh
    zq = np.clip(zc, a, b)
    e = np.clip(1.0 - ((zq - zc) / np.maximum(hh, 1e-6)) ** 2, 0.0, None)
    return np.where((b < zc - hh) | (a > zc + hh), 0.0, r * np.sqrt(e))


def model_sizes():
    """name -> (height, crown radius, half length along local x, half width along local y) of every
    vanilla vegetation model at scale 1 (dati/asset_bounds.json)."""
    b = json.load(open(os.path.join(DATI, "asset_bounds.json")))
    out = {}
    for k, v in b.items():
        if k.startswith("_") or v is None:
            continue
        lo, hi = np.array(v[0], float), np.array(v[1], float)
        out[os.path.splitext(os.path.basename(k))[0]] = (hi[2] - max(lo[2], -0.5), 0.25 * ((hi[0] - lo[0]) + (hi[1] - lo[1])),
                                                         0.5 * (hi[0] - lo[0]), 0.5 * (hi[1] - lo[1]))
    return out


# ---------------------------------------------------------------------- the level
class Forest:
    """The forest items of a level: per type the objects of its file, and arrays over all of them."""

    def __init__(self, lv):
        self.lv = lv
        self.sizes = model_sizes()
        md = os.path.join(lv, "art", "forest", "managedItemData.json")
        self.managed = json.load(open(md)) if os.path.exists(md) else {}
        self.objs = {}
        for f in sorted(glob.glob(os.path.join(lv, "forest", "*.forest4.json"))):
            if guardrail_mesh.is_module(f):                 # v2.8: the guard rails, not plants
                continue
            self.objs[os.path.basename(f)[:-len(".forest4.json")]] = pr.items(f)
        self.types = sorted(self.objs)
        rows = []
        for ti, t in enumerate(self.types):
            for j, o in enumerate(self.objs[t]):
                rm = o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1])
                rows.append((o["pos"][0], o["pos"][1], o["pos"][2], float(o.get("scale", 1.0)), ti, j,
                             np.arctan2(rm[1], rm[0])))
        A = np.array(rows, np.float64).reshape(-1, 7)
        self.x, self.y, self.z, self.s = A[:, 0].copy(), A[:, 1].copy(), A[:, 2].copy(), A[:, 3].copy()
        self.t, self.j, self.theta = A[:, 4].astype(int), A[:, 5].astype(int), A[:, 6]
        self.kinds = np.array([kind_of(t) for t in self.types])
        self.alive = np.ones(len(self.x), bool)

    def kind(self, i):
        return self.kinds[self.t[i]]

    def size(self, i, t=None, s=None):
        """(height, crown radius) of item i (with type index t and scale s instead of its own)."""
        t = self.t[i] if t is None else t
        s = self.s[i] if s is None else s
        H0, R0, _, _ = self.sizes.get(self.types[t], (10.0, 3.0, 3.0, 3.0))
        return H0 * s, min(R0 * s, MAX_R)

    def sizes_all(self):
        H0 = np.array([self.sizes.get(t, (10.0, 3.0, 3.0, 3.0))[0] for t in self.types])
        R0 = np.array([self.sizes.get(t, (10.0, 3.0, 3.0, 3.0))[1] for t in self.types])
        return H0[self.t] * self.s, np.minimum(R0[self.t] * self.s, MAX_R)

    def type_index(self, name):
        if name not in self.objs:
            self.objs[name] = []
            self.types.append(name)
            self.kinds = np.array([kind_of(t) for t in self.types])
        return self.types.index(name)

    def write(self):
        """Forest files with the items that are left, at their new place, scale and model."""
        out = {t: [] for t in self.types}
        for i in np.flatnonzero(self.alive):
            src = self.types[self.t0[i]] if hasattr(self, "t0") else self.types[self.t[i]]
            o = dict(self.objs[src][self.j[i]])
            t = self.types[self.t[i]]
            o["pos"] = [round(float(self.x[i]), 3), round(float(self.y[i]), 3), round(float(self.z[i]), 3)]
            o["scale"] = round(float(self.s[i]), 4)
            o["type"] = t
            out[t].append(o)
        for t, lst in out.items():
            f = os.path.join(self.lv, "forest", t + ".forest4.json")
            if lst:
                pr.write_items(f, lst)
            elif os.path.exists(f):
                os.remove(f)
        return {t: len(v) for t, v in out.items()}


def _mesh_items(lv, group):
    """TSStatic objects of a group (and its subgroups) with their DAE in the level folder, unrotated."""
    out = []
    base = os.path.join(lv, "main", "MissionGroup", *group.split("/"))
    for dp, _, fs in os.walk(base):
        if "items.level.json" not in fs:
            continue
        for o in pr.items(os.path.join(dp, "items.level.json")):
            if o.get("class") != "TSStatic" or o.get("collisionType") == "None":
                continue
            shape = o.get("shapeName", "")
            path = os.path.join(lv, *shape.split("/")[3:]) if shape.startswith(LEVEL_PREFIX) else None
            out.append((o, path))
    return out


def level_faces(lv):
    """Triangles of the level: drivable top faces and their class, solid faces a trunk may not stand
    in, the ground mesh behind the walls, and the vanilla props (points)."""
    tops, cls, solid, fill, props, sgrp = [], [], [], [], [], []
    for o, path in _mesh_items(lv, "roads/surfaces") + _mesh_items(lv, "railway"):
        V, N, T, C, parts = pr.read_dae(path)
        Vw = V + np.array(o["position"], float)
        for mat, idx in parts:
            t = Vw[idx[:, 0].reshape(-1, 3)]
            if mat in SOLID_ROAD_MATS:
                solid.append(t)
                sgrp.append(np.full(len(t), 0, np.int8))
                continue
            if mat not in SURFACE_CLASS:
                continue
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
            tops.append(t[up])
            cls.append(np.full(int(up.sum()), SURFACE_CLASS[mat], np.int8))
    for gi, g in enumerate(SOLID_GROUPS):
        for o, path in _mesh_items(lv, g):
            if path is None or not os.path.exists(path):
                if "position" in o and o["position"] != [0.0, 0.0, 0.0]:
                    props.append(o["position"])                      # a vanilla prop: its place
                continue
            if o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1]) != [1, 0, 0, 0, 1, 0, 0, 0, 1]:
                continue
            V, N, T, C, parts = pr.read_dae(path)
            Vw = V * np.array(o.get("scale", [1, 1, 1]), float) + np.array(o.get("position", [0, 0, 0]), float)
            for mat, idx in parts:
                t = Vw[idx[:, 0].reshape(-1, 3)]
                if mat.startswith("mp_fill_"):
                    fill.append(t)
                else:
                    solid.append(t)
                    sgrp.append(np.full(len(t), gi + 1, np.int8))
    gr = guardrail_mesh.module_faces(lv)                # v2.8: the guard rails are forest items
    if len(gr):
        solid.append(gr)
        sgrp.append(np.full(len(gr), SOLID_GROUPS.index("roads/guardrails") + 1, np.int8))
    cat = lambda L: np.concatenate(L) if L else np.zeros((0, 3, 3))
    solid_all = cat(solid)
    return (cat(tops), np.concatenate(cls) if cls else np.zeros(0, np.int8),
            (solid_all, np.concatenate(sgrp) if sgrp else np.zeros(0, np.int8)), cat(fill),
            np.array(props, float).reshape(-1, 3))


def water_blocks(lv):
    """(x0, y0, x1, y1, surface z) of every water block."""
    wf = os.path.join(lv, "main", "MissionGroup", "level_objects", "Water", "items.level.json")
    out = []
    for o in (pr.items(wf) if os.path.exists(wf) else []):
        if o.get("class") == "WaterBlock":
            (bx, by, bz), (sx, sy, _) = o["position"], o.get("scale", [1, 1, 1])
            out.append((bx - sx / 2, by - sy / 2, bx + sx / 2, by + sy / 2, bz))
    return out


def terrain_low(ter, x, y):
    """Height of the terrain surface: the lower of the two ways a terrain square can be split into
    triangles (an item set on it does not float whichever way the engine splits it)."""
    c = (np.asarray(x) - ter.x0) / ter.sq
    r = (np.asarray(y) - ter.y0) / ter.sq
    c0 = np.clip(np.floor(c).astype(np.int64), 0, ter.n - 2)
    r0 = np.clip(np.floor(r).astype(np.int64), 0, ter.n - 2)
    fc, fr = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
    z00, z10, z01, z11 = ter.h[r0, c0], ter.h[r0, c0 + 1], ter.h[r0 + 1, c0], ter.h[r0 + 1, c0 + 1]
    a = np.where(fc >= fr, z00 + fc * (z10 - z00) + fr * (z11 - z10), z00 + fr * (z01 - z00) + fc * (z11 - z01))
    b = np.where(fc + fr <= 1, z00 + fc * (z10 - z00) + fr * (z01 - z00),
                 z11 + (1 - fc) * (z01 - z11) + (1 - fr) * (z10 - z11))
    return np.minimum(a, b)


class Ground:
    """The ground a plant stands on: the terrain, or the ground mesh behind a retaining wall where
    that is higher (the terrain is lowered at the foot of the wall)."""
    RING = np.array([[0.0, 0.0]] + [[np.cos(a), np.sin(a)] for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)])

    def __init__(self, ter, fill):
        self.ter = ter
        self.fill = TriSurface(fill) if len(fill) else None

    def height(self, x, y):
        z = terrain_low(self.ter, x, y)
        if self.fill is not None:
            zf = self.fill.height(x, y, "high")
            z = np.where(np.isfinite(zf), np.maximum(zf, z), z)
        return z

    def base(self, x, y, r):
        """Lowest ground within r of every point (x, y) (the centre and 8 points around it), at most
        MAX_DROP m under the ground at the centre (at the top of a retaining wall the terrain beside
        the ground mesh behind it is the foot of the wall)."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        r = np.broadcast_to(np.asarray(r, float), x.shape)
        X = x[:, None] + r[:, None] * self.RING[None, :, 0]
        Y = y[:, None] + r[:, None] * self.RING[None, :, 1]
        Z = self.height(X.ravel(), Y.ravel()).reshape(X.shape)
        return np.maximum(Z.min(1), Z[:, 0] - MAX_DROP)


def raster_max_heights(tri, x_min, y_max, shape, res=RES):
    """Height of the highest triangle (k,3,3) over every cell centre of a north-up raster (NaN
    where there is none)."""
    Hh, Ww = shape
    out = np.full(shape, np.nan)
    if not len(tri):
        return out
    A, B, Cc = tri[:, 0], tri[:, 1], tri[:, 2]
    lo = np.minimum(np.minimum(A, B), Cc)
    hi = np.maximum(np.maximum(A, B), Cc)
    c0 = np.maximum(np.ceil((lo[:, 0] - x_min) / res - 0.5).astype(int), 0)
    c1 = np.minimum(np.floor((hi[:, 0] - x_min) / res - 0.5).astype(int), Ww - 1)
    r0 = np.maximum(np.ceil((y_max - hi[:, 1]) / res - 0.5).astype(int), 0)
    r1 = np.minimum(np.floor((y_max - lo[:, 1]) / res - 0.5).astype(int), Hh - 1)
    nc_, nr_ = np.maximum(c1 - c0 + 1, 0), np.maximum(r1 - r0 + 1, 0)
    for w, h in set(zip(nc_.tolist(), nr_.tolist())):
        if w == 0 or h == 0:
            continue
        sel = np.flatnonzero((nc_ == w) & (nr_ == h))
        dc, dr = np.meshgrid(np.arange(w), np.arange(h))
        cc = c0[sel][:, None] + dc.ravel()[None]
        rr = r0[sel][:, None] + dr.ravel()[None]
        px = x_min + (cc + 0.5) * res
        py = y_max - (rr + 0.5) * res
        a, b, c = A[sel], B[sel], Cc[sel]
        v0 = b[:, :2] - a[:, :2]; v1 = c[:, :2] - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1.0)
        qx, qy = px - a[:, 0:1], py - a[:, 1:2]
        l1 = (qx * v1[:, 1:2] - v1[:, 0:1] * qy) / den[:, None]
        l2 = (v0[:, 0:1] * qy - qx * v0[:, 1:2]) / den[:, None]
        l0 = 1 - l1 - l2
        ins = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & ok[:, None]
        z = l0 * a[:, 2:3] + l1 * b[:, 2:3] + l2 * c[:, 2:3]
        rr, cc, z = rr[ins], cc[ins], z[ins]
        order = np.argsort(z)                               # the highest face written last wins
        out[rr[order], cc[order]] = np.fmax(out[rr[order], cc[order]], z[order])
    return out


class Bins:
    """Triangles (k,3,3) sorted into TILE m bins by their centre, for the tiles with a margin."""

    def __init__(self, tri, extra=None):
        self.tri = tri
        self.extra = extra
        c = tri[:, :, :2].mean(1) if len(tri) else np.zeros((0, 2))
        self.key = np.floor(c / TILE).astype(np.int64)
        k = self.key[:, 0] * 100_003 + self.key[:, 1]
        self.order = np.argsort(k, kind="stable")
        self.k = k[self.order]

    def near(self, tx, ty):
        """Indices of the triangles whose centre lies in the tile (tx, ty) or one around it."""
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                kk = (tx + dx) * 100_003 + (ty + dy)
                a, b = np.searchsorted(self.k, kk, "left"), np.searchsorted(self.k, kk, "right")
                out.append(self.order[a:b])
        return np.concatenate(out) if out else np.zeros(0, int)


class TileRasters:
    """Rasters of one tile and its margin: the class and height of the top-most drivable face of
    every cell, the cells a trunk may not stand in (walls, buildings, parapets, guardrails, fences,
    props) and the lake."""

    def __init__(self, tx, ty, roads, solids, props, water):
        self.x_min, self.y_max = tx * TILE - MARGIN, (ty + 1) * TILE + MARGIN
        n = int(round((TILE + 2 * MARGIN) / RES))
        self.n = n
        self.cls = np.full((n, n), -1, np.int8)
        self.z = np.full((n, n), np.nan)
        tr = Affine(RES, 0, self.x_min, 0, -RES, self.y_max)
        box = shapely.box(self.x_min, self.y_max - n * RES, self.x_min + n * RES, self.y_max)
        idx = roads.near(tx, ty)
        self.exact = {}                                      # the faces themselves, per class (near_surface)
        if len(idx):
            T, K = roads.tri[idx], roads.extra[idx]
            for c in (2, 1, 0):                              # carriageways win over the rest
                sel = K == c
                if not sel.any():
                    continue
                self.exact[c] = TriSurface(T[sel])
                zc = raster_max_heights(T[sel], self.x_min, self.y_max, (n, n))
                m = np.isfinite(zc)
                self.cls[m] = c
                self.z[m] = np.where(np.isfinite(self.z[m]), np.maximum(self.z[m], zc[m]), zc[m])
        self.solid = np.zeros((n, n), bool)
        self.sol = np.zeros((0, 3, 3))
        self.sol_grp = np.zeros(0, np.int8)
        idx = solids.near(tx, ty)
        if len(idx):
            T = solids.tri[idx]
            geoms = shapely.polygons(T[:, :, :2])
            inb = shapely.intersects(geoms, box)
            geoms, self.sol = geoms[inb], T[inb]
            self.sol_grp = solids.extra[idx][inb]
            area = shapely.area(geoms)
            shp = [(g, 1) for g in geoms[area > 1e-4]] + [(g, 1) for g in shapely.get_exterior_ring(geoms)]
            if shp:
                self.solid = features.rasterize(shp, out_shape=(n, n), transform=tr, fill=0, dtype=np.uint8,
                                                all_touched=True).astype(bool)
        self.sol_lo, self.sol_hi = self.sol[:, :, :2].min(1), self.sol[:, :, :2].max(1)
        self.sol_z0, self.sol_z1 = self.sol[:, :, 2].min(1), self.sol[:, :, 2].max(1)
        self.props = np.zeros((0, 2))
        if len(props):
            m = (props[:, 0] > self.x_min - 2) & (props[:, 0] < self.x_min + n * RES + 2) & \
                (props[:, 1] < self.y_max + 2) & (props[:, 1] > self.y_max - n * RES - 2)
            self.props = props[m, :2]
            for px, py in self.props:
                c, r = self.cell(px, py)
                self.solid[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2] = True
        self.water = water

    def cell(self, x, y):
        return int((x - self.x_min) / RES), int((self.y_max - y) / RES)

    def window(self, x, y, rad):
        """Cells within rad of (x, y): (rows, cols, distances, cell x, cell y)."""
        k = int(np.ceil(rad / RES)) + 1
        c0, r0 = self.cell(x, y)
        cc, rr = np.meshgrid(np.arange(c0 - k, c0 + k + 1), np.arange(r0 - k, r0 + k + 1))
        cc, rr = cc.ravel(), rr.ravel()
        ok = (cc >= 0) & (cc < self.n) & (rr >= 0) & (rr < self.n)
        cc, rr = cc[ok], rr[ok]
        X = self.x_min + (cc + 0.5) * RES
        Y = self.y_max - (rr + 0.5) * RES
        d = np.hypot(X - x, Y - y)
        m = d <= rad
        return rr[m], cc[m], d[m], X[m], Y[m]

    def intrusion(self, x, y, zb, kind, h, r):
        """How far the crown of a plant at (x, y) with its base at zb reaches into the clearance
        profile of the drivable faces beyond EDGE_TOL (m, <= 0 when it does not), the class of the
        surface and the unit vector away from where it reaches in."""
        rr, cc, d, X, Y = self.window(x, y, r + RES)
        k = self.cls[rr, cc]
        on = k >= 0
        if not on.any():
            return -9.0, -1, 0.0, 0.0
        rr, cc, d, X, Y, k = rr[on], cc[on], d[on], X[on], Y[on], k[on]
        a = self.z[rr, cc] - zb
        rad = crown_radius(kind, h, r, a, a + CLEAR[k])
        over = rad - d - EDGE_TOL
        j = int(np.argmax(over))
        if over[j] <= 0:
            return float(over[j]), int(k[j]), 0.0, 0.0
        w = np.clip(over, 0, None)
        v = np.column_stack([x - X, y - Y]) / np.maximum(d, 1e-6)[:, None]
        u = (v * w[:, None]).sum(0)
        nu = np.hypot(*u)
        if nu < 1e-9:
            u, nu = np.array([1.0, 0.0]), 1.0
        return float(over[j]), int(k[j]), float(u[0] / nu), float(u[1] / nu)

    def solid_near(self, x, y, z0, z1, rad):
        """What stands within rad m of (x, y) (seen from above) with its heights in [z0, z1]: the index
        of SOLID_NAMES of the nearest solid face, or of a vanilla prop within PROP_R m; None."""
        if len(self.props) and (np.hypot(self.props[:, 0] - x, self.props[:, 1] - y) < PROP_R).any():
            return len(SOLID_NAMES) - 1
        m = (self.sol_lo[:, 0] <= x + rad) & (self.sol_hi[:, 0] >= x - rad) & (self.sol_lo[:, 1] <= y + rad) & \
            (self.sol_hi[:, 1] >= y - rad) & (self.sol_z1 >= z0) & (self.sol_z0 <= z1)
        if not m.any():
            return None
        T = self.sol[m][:, :, :2]
        G = self.sol_grp[m]
        P = np.array([x, y])
        A, B, C = T[:, 0], T[:, 1], T[:, 2]
        v0, v1 = B - A, C - A
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-9
        q = P - A
        l1 = (q[:, 0] * v1[:, 1] - v1[:, 0] * q[:, 1]) / np.where(ok, den, 1.0)
        l2 = (v0[:, 0] * q[:, 1] - q[:, 0] * v0[:, 1]) / np.where(ok, den, 1.0)
        d = np.where(ok & (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1), 0.0, np.inf)
        for a, b in ((A, B), (B, C), (C, A)):
            ab = b - a
            t = np.clip(((P - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
            d = np.minimum(d, np.hypot(*(a + t[:, None] * ab - P).T))
        j = int(np.argmin(d))
        return int(G[j]) if d[j] < rad else None

    def blocked(self, x, y, zb, top):
        """Why a trunk at (x, y), base zb, may not stand there: 'solid' (a wall, a building, a parapet,
        a guardrail, a fence or a street light within TRUNK_R / PROP_R m), else None."""
        rr, cc, d, _, _ = self.window(x, y, TRUNK_R)
        if len(rr) and self.solid[rr, cc].any():
            g = self.solid_near(x, y, zb - 0.3, zb + min(top, 4.0), TRUNK_R)
            if g is not None:
                return SOLID_NAMES[g]
        return None

    def near_surface(self, x, y, clear=TRUNK_CLEAR):
        """A drivable face on the trunk or within clear[class] - 0.05 m of it, on the faces themselves
        and in plan, as check_level.py measures it (12 points around the trunk)."""
        a = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        for c, S in self.exact.items():
            rad = clear[c] - 0.05
            if np.isfinite(S.height(np.r_[x, x + rad * np.cos(a)], np.r_[y, y + rad * np.sin(a)], "high")).any():
                return True
        return False

    def trunk_free(self, x, y, zb, top, clear=TRUNK_CLEAR):
        """A place a trunk may be moved to: not blocked, clear of the drivable faces at its level
        (clear[class] m), and of all of them in plan (near_surface), and not in the lake."""
        rr, cc, d, _, _ = self.window(x, y, max(clear.max(), TRUNK_R))
        if not len(rr) or self.blocked(x, y, zb, top):
            return False
        k = self.cls[rr, cc]
        on = k >= 0
        if on.any():
            zz = self.z[rr[on], cc[on]]
            near = (d[on] <= clear[k[on]]) & (zz > zb - 2.0) & (zz < zb + top)
            if near.any():
                return False
        for x0, y0, x1, y1, wz in self.water:
            if x0 < x < x1 and y0 < y < y1 and zb < wz - UNDER_WATER:
                return False
        return not self.near_surface(x, y, clear)


# ---------------------------------------------------------------------- the step
def plant_intrusion(T, F, i, x, y, zb, kind, h, r):
    """TileRasters.intrusion for plant i at (x, y): a hedge is measured as three circles of its
    half width along its length."""
    if kind != "hedge":
        return T.intrusion(x, y, zb, kind, h, r)
    _, _, L0, W0 = F.sizes.get(F.types[F.t[i]], (1.7, 1.05, 1.5, 0.6))
    L, w = L0 * F.s[i], W0 * F.s[i]
    c, sn = np.cos(F.theta[i]), np.sin(F.theta[i])
    best = (-9.0, -1, 0.0, 0.0)
    for t in ((-(L - w), 0.0, L - w) if L > w else (0.0,)):
        res = T.intrusion(x + c * t, y + sn * t, zb, kind, h, w)
        if res[0] > best[0]:
            best = res
    return best


def families(forest):
    """For every model type the types of its family (broad-leaved trees, conifers), narrowest first,
    among the types of vegetation.py present in the level (a swap never brings in a new model)."""
    import vegetation
    fam = {"broadleaf": [], "conifer": []}
    names = lambda lst: [os.path.splitext(os.path.basename(p))[0] for p in lst]
    for key, lst in vegetation.MODELS.items():
        for n in names(lst):
            if n in forest.objs and n in forest.sizes:
                if key.startswith("deciduous"):
                    fam["broadleaf"].append(n)
                elif key == "conifer":
                    fam["conifer"].append(n)
    for k in fam:
        fam[k] = sorted(set(fam[k]), key=lambda n: forest.sizes[n][1] / forest.sizes[n][0])
    return fam


def run(lv, verbose=True, record=None):
    """Apply the three rules to the level folder `lv`; returns the counts. record: a JSON file for the
    list of the plants changed ([x, y, what, why], zone_report.py)."""
    t0 = time.time()
    F = Forest(lv)
    F.t0 = F.t.copy()
    tops, cls, solid, fill, props = level_faces(lv)
    ter = pr.Terrain(lv)
    ground = Ground(ter, fill)
    water = water_blocks(lv)
    roads, solids = Bins(tops, cls), Bins(*solid)
    fam = families(F)
    kinds = F.kinds[F.t]
    stats = {"items": int(len(F.x)), "moved": 0, "swapped": 0, "scaled": 0, "removed": 0,
             "in_profile_before": [0, 0, 0], "trunks_in_solids_before": 0, "trunks_in_solids_moved": 0,
             "trunks_in_solids_removed": 0, "trunks_near_roads_before": 0}
    if verbose:
        print("canopy: %d forest items, %d drivable faces, %d solid faces, %d faces of ground behind walls "
              "(%.0f s)" % (len(F.x), len(tops), len(solid[0]), len(fill), time.time() - t0), flush=True)
    # every item on the ground first (the crown test needs the base heights)
    is_tree = np.isin(kinds, ("broadleaf", "conifer"))
    sink = np.where(is_tree, SINK["tree"], np.array([SINK.get(k, 0.1) for k in kinds]))
    zb = ground.base(F.x, F.y, np.where(is_tree, TRUNK_R, 0.2))
    before = F.z - (zb - sink)
    stats["floating_before"] = int((before > FLOAT_TOL).sum())
    stats["buried_before"] = int((before < -BURY_TOL).sum())
    F.z = zb - sink
    H, R = F.sizes_all()
    changes = []
    tree_ids = np.flatnonzero(is_tree)
    tree_kd = cKDTree(np.column_stack([F.x[tree_ids], F.y[tree_ids]]))
    tx_all, ty_all = np.floor(F.x / TILE).astype(int), np.floor(F.y / TILE).astype(int)
    tiles = sorted(set(zip(tx_all.tolist(), ty_all.tolist())))
    for n_tile, (tx, ty) in enumerate(tiles):
        moved_to = []                                     # trunks placed in this tile
        items = np.flatnonzero((tx_all == tx) & (ty_all == ty))
        if not len(roads.near(tx, ty)) and not len(solids.near(tx, ty)):
            continue
        T = TileRasters(tx, ty, roads, solids, props, water)
        for i in items:
            kind = kinds[i]
            tree = kind in ("broadleaf", "conifer")
            h, r = H[i], R[i]
            base = F.z[i] + sink[i]                         # the ground; the model (and its crown) from F.z
            over, k, ux, uy = plant_intrusion(T, F, i, F.x[i], F.y[i], F.z[i], kind, h, r)
            in_solid = tree and T.blocked(F.x[i], F.y[i], base, h) is not None
            # a trunk closer to a drivable face than clearance.py allows (a tree of a later edit)
            near_road = tree and not in_solid and over <= 0 and T.near_surface(F.x[i], F.y[i])
            if over <= 0 and not in_solid and not near_road:
                continue
            if over > 0:
                stats["in_profile_before"][k] += 1
            if near_road:
                stats["trunks_near_roads_before"] += 1          # away from the surface cells around it
                rr, cc, d, X, Y = T.window(F.x[i], F.y[i], 1.5)
                s_ = T.cls[rr, cc] >= 0
                if s_.any():
                    v = np.array([F.x[i] - X[s_].mean(), F.y[i] - Y[s_].mean()])
                    nv = np.hypot(*v)
                    ux, uy = (v / nv) if nv > 1e-6 else (1.0, 0.0)
            if in_solid:
                stats["trunks_in_solids_before"] += 1
                if over <= 0:                                   # away from the solid cells around it
                    rr, cc, d, X, Y = T.window(F.x[i], F.y[i], 1.5)
                    s_ = T.solid[rr, cc]
                    if s_.any():
                        v = np.array([F.x[i] - X[s_].mean(), F.y[i] - Y[s_].mean()])
                        nv = np.hypot(*v)
                        ux, uy = (v / nv) if nv > 1e-6 else (1.0, 0.0)
            limit = MOVE if tree else SHRUB_MOVE
            x_old, y_old, t_old, s_old = F.x[i], F.y[i], F.t[i], F.s[i]
            done = _fix(F, T, ground, (tree_kd, tree_ids), moved_to, i, kind, ux, uy, limit, fam if tree else None,
                        sink[i], stats)
            why = CLASS_NAMES[k] if over > 0 else ("tronco in un oggetto solido" if in_solid else "tronco a bordo strada")
            if done is None:
                F.alive[i] = False
                stats["removed"] += 1
                if in_solid:
                    stats["trunks_in_solids_removed"] += 1
                changes.append([round(float(x_old), 1), round(float(y_old), 1), "rimosso", why])
            else:
                if in_solid:
                    stats["trunks_in_solids_moved"] += 1
                what = "sostituito" if F.t[i] != t_old else ("ridotto" if F.s[i] != s_old else "spostato")
                changes.append([round(float(x_old), 1), round(float(y_old), 1), what, why])
        if verbose and n_tile % 100 == 0:
            print("  tile %d/%d, moved %d, swapped %d, scaled %d, removed %d (%.0f s)" %
                  (n_tile + 1, len(tiles), stats["moved"], stats["swapped"], stats["scaled"], stats["removed"],
                   time.time() - t0), flush=True)
    counts = F.write()
    if record:
        json.dump(changes, open(record, "w"))
    stats["items_after"] = int(F.alive.sum())
    stats["types"] = counts
    if verbose:
        print("canopy: %s (%.0f s)" % ({k: v for k, v in stats.items() if k != "types"}, time.time() - t0), flush=True)
    return stats


def _fix(F, T, ground, trees, moved_to, i, kind, ux, uy, limit, fam, sink, stats):
    """Move, swap, scale down: the first option that clears the crown and puts the trunk on free
    ground, the least change first; None when none does. Updates F in place."""
    tree_kd, tree_ids = trees
    x0, y0 = F.x[i], F.y[i]
    t0_, s0 = F.t[i], F.s[i]
    h0, r0 = F.size(i)
    options = [(t0_, s0, "keep")]
    if fam is not None:
        swaps = []
        for name in fam.get(kind, []):
            t = F.types.index(name)
            H0, R0, _, _ = F.sizes[name]
            s = h0 / H0
            if t != t0_ and 0.5 <= s <= 2.0 and min(R0 * s, MAX_R) < r0 - 0.05:
                swaps.append((t, s, "swap"))
        swaps.sort(key=lambda o: -F.size(i, o[0], o[1])[1])          # the widest that fits first
        options += swaps
        tn, sn_, _ = min(options, key=lambda o: F.size(i, o[0], o[1])[1])
        options += [(tn, sn_ * f, "scale") for f in SCALES]
    steps = np.r_[0.0, np.arange(0.25, limit + 1e-6, 0.25)]
    tree = fam is not None
    for t, s, how in options:
        h, r = F.size(i, t, s)
        for d in steps:
            for rot in ((0.0,) if d == 0 else (0.0, 0.6, -0.6)):
                c, sn = np.cos(rot), np.sin(rot)
                vx, vy = c * ux - sn * uy, sn * ux + c * uy
                x, y = x0 + d * vx, y0 + d * vy
                zb = float(ground.base([x], [y], TRUNK_R if tree else 0.2)[0])
                if d > 0:
                    if not T.trunk_free(x, y, zb, h, clear=TRUNK_CLEAR if tree else np.zeros(3)):
                        continue
                    if tree:
                        near = tree_ids[tree_kd.query_ball_point([x, y], TRUNK_GAP)]
                        if any(j != i and F.alive[j] for j in near):
                            continue
                        if any(np.hypot(x - mx, y - my) < TRUNK_GAP for mx, my in moved_to):
                            continue
                elif tree and T.blocked(x, y, zb, h):
                    continue
                F.t[i], F.s[i] = t, s
                over, _, _, _ = plant_intrusion(T, F, i, x, y, zb - sink, kind, h, r)
                if over > 0:
                    F.t[i], F.s[i] = t0_, s0
                    continue
                F.x[i], F.y[i], F.z[i] = x, y, zb - sink
                if d > 0:
                    stats["moved"] += 1
                    if tree:
                        moved_to.append((x, y))
                if how == "swap":
                    stats["swapped"] += 1
                elif how == "scale":
                    stats["scaled"] += 1
                return x, y
    return None


# ---------------------------------------------------------------------- checks (check_level.py)
def check(lv, places=None):
    """The rules measured on a built level, without changing it: crowns in the clearance profile
    (per class of surface), trunks in solid meshes, items floating over or buried in the ground."""
    F = Forest(lv)
    tops, cls, solid, fill, props = level_faces(lv)
    ter = pr.Terrain(lv)
    ground = Ground(ter, fill)
    water = water_blocks(lv)
    roads, solids = Bins(tops, cls), Bins(*solid)
    kinds = F.kinds[F.t]
    tree = np.isin(kinds, ("broadleaf", "conifer"))
    sink = np.where(tree, SINK["tree"], 0.1)
    off = F.z - ground.height(F.x, F.y)
    res = {"forest_floating": int((off > FLOAT_TOL).sum()), "forest_buried": int((off < -BURY_TOL).sum()),
           "crowns_in_profile": 0, "crowns_in_profile_by_class": {c: 0 for c in CLASS_NAMES},
           "crowns_in_profile_max_m": 0.0, "trunks_in_solids": 0, "trunks_in_solids_by_kind": {}}
    if places is not None:
        for m, what in ((off > FLOAT_TOL, "pianta sospesa"), (off < -BURY_TOL, "pianta interrata")):
            if m.any():
                places.add(what, F.x[m], F.y[m], F.z[m], np.abs(off[m]))
    H, R = F.sizes_all()
    tx_all, ty_all = np.floor(F.x / TILE).astype(int), np.floor(F.y / TILE).astype(int)
    for tx, ty in sorted(set(zip(tx_all.tolist(), ty_all.tolist()))):
        if not len(roads.near(tx, ty)) and not len(solids.near(tx, ty)):
            continue
        T = TileRasters(tx, ty, roads, solids, props, water)
        for i in np.flatnonzero((tx_all == tx) & (ty_all == ty)):
            base = F.z[i] + sink[i]
            over, k, _, _ = plant_intrusion(T, F, i, F.x[i], F.y[i], F.z[i], kinds[i], H[i], R[i])
            if over > 0:
                res["crowns_in_profile"] += 1
                res["crowns_in_profile_by_class"][CLASS_NAMES[k]] += 1
                res["crowns_in_profile_max_m"] = max(res["crowns_in_profile_max_m"], round(over + EDGE_TOL, 2))
                if places is not None:
                    places.add("chioma nella sagoma della strada", F.x[i], F.y[i], F.z[i], over + EDGE_TOL,
                               cosa=CLASS_NAMES[k])
            why = T.blocked(F.x[i], F.y[i], base, H[i]) if tree[i] else None
            if why:
                res["trunks_in_solids"] += 1
                res["trunks_in_solids_by_kind"][why] = res["trunks_in_solids_by_kind"].get(why, 0) + 1
                if places is not None:
                    places.add("tronco dentro un oggetto solido", F.x[i], F.y[i], F.z[i], 1.0, cosa=why)
    return res


if __name__ == "__main__":
    from config import LEVEL_DIR
    lv = sys.argv[1] if len(sys.argv) > 1 else LEVEL_DIR
    print(json.dumps(run(lv), indent=1))
