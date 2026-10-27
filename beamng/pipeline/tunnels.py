"""Tunnels and galleries (v3.2, issue #19): the swissTLM3D road and railway lines in a tunnel, built in the level.

Up to v3.1.1 network.py and railway.py left every tunnel out: a road or track ran into the hillside and stopped at the
portal. This finishing step builds them on the built level:
- the lines: swissTLM3D TLM_STRASSE / TLM_EISENBAHN with KUNSTBAUTE Tunnel or Galerie (data/tlm of the build, or the
  pack of beamng/ticino/dati/tunnels_tlm.json.gz that tunnels_ref.yml takes for all of Ticino), kept where at least
  one portal joins a road or track of the level (LIVE m): the swissTLM3D z of a road is its carriageway, of a track
  its rails; at a live portal the line is moved to the height of the mesh it joins, and the change faded along it;
- the tube: a deck (asphalt between kerbed walkways, or ballast, sleepers and rails), straight walls and a vault
  (PROFILE by kind), the inside faces turned in, an outer shell (SHELL m) near the portals and where the cover is
  thin, concrete of Italy;
- a portal at every live end: a headwall HEAD m thick round the opening, standing one terrain square (PORTAL_OUT)
  out of the swissTLM3D portal, with a cornice;
- the terrain: a heightfield cannot pass over a tube, so the samples whose square meets the tube's footprint where
  the ground stands between its floor and the top of its shell become holes (layer 255 of the .ter: neither drawn
  nor colliding); the parts of those squares beside the tube are closed by a cap at the ground's own heights with
  the terrain skin's earth in the terrain's colour, the shell closes the rest;
- the meshes in the way: triangles of the terrain skin, the walls, the fences and the road meshes (yards meshed on the
  DTM) inside the tube or in the opening's clearance in front of a portal, and of the skin over a hole,
  and the forest items standing in the footprint where the ground was lower than the shell, are taken out;
- lights: a SpotLight every LIGHT_STEP m under the vault, on day and night as in a real tunnel, and a lamp strip;
- the AI: a DecalRoad through every road tunnel, its ends on the AI roads at the portals.
A finishing step of build_level.py (FINISH, after vineyards_ground: the last step that changes the ground, so no step
after it reads a terrain layer 255 or rebuilds the skin over a hole); alone: python build_level.py --finish tunnels.
It also runs on a released level folder (not twice: the holes and cuts of a first run stay).
"""
import gzip, json, math, os, re, sys, time
import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates
from scipy.spatial import cKDTree

import bng
import italy_mats
from config import DATA, LEVEL_NAME, lv95_to_local

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "..", "ticino", "dati", "tunnels_tlm.json.gz")
KINDS = {"Tunnel", "Galerie"}
STEP = 2.0              # m between the stations of a tube
LIVE = 8.0              # m: a portal this close to a road or track mesh of the level (at the line's height) is live
LIVE_DZ = 3.0
FADE = 60.0             # m along which the height change of a live portal fades
SHELL = 0.5             # m of concrete round the tube
SHELL_NEAR = 30.0       # m from a portal where the outer shell is drawn (inside the hill nobody sees it)
COVER_THIN = 2.0        # m: where the ground stands less than this over the shell, the shell is drawn too
COVER_MIN = 0.5         # m of ground the mound keeps over the shell where the tube runs in the hill
MOUND_W = 8.0           # m beside the shell over which the mound falls back to the ground (1:1)
HEAD = 1.0              # m, thickness of a headwall
HEAD_W = 1.6            # m of headwall beside the shell
HEAD_UP = 1.4           # m of headwall over the shell
APRON = 1.6            # m of floor in front of a headwall's face (one terrain square and a bit)
FOOT = 0.4              # m a headwall's side goes under the lowest ground at its edge
PORTAL_OUT = 1.5        # m: the headwall stands this far out of the swissTLM3D portal (one terrain square)
CLEAR = 0.25            # m: ground this far over the floor is in the way
APPROACH = 10.0         # m out of a live portal where meshes in the opening's clearance are taken out
CAP_RES = 0.25          # m, grid of the cap over the holes
LIGHT_STEP = 20.0
WALK = 1.0              # m, walkway beside the carriageway
KERB = 0.15
# carriageway width (m) by swissTLM3D class; the rest of the classes are paths, never in a tunnel of the level
CARRIAGEWAY = {"1m Weg": 1.6, "2m Weg": 2.6, "3m Strasse": 3.6, "4m Strasse": 4.6, "6m Strasse": 6.6,
               "8m Strasse": 8.0, "10m Strasse": 10.0, "Autostrasse": 9.0, "Autobahn": 10.5, "Ausfahrt": 4.6,
               "Einfahrt": 4.6, "Autozug": 4.6, "Verbindung": 4.6, "Zufahrt": 4.6}
DRIVABILITY = {"1m Weg": 0.3, "2m Weg": 0.4, "3m Strasse": 0.75, "4m Strasse": 0.9}
# (half width inside, height of the straight walls, crown over the floor) by kind
PROFILE = {"Schmalspur": (2.6, 2.0, 5.8), "Normalspur": (3.0, 2.2, 6.8)}
ROAD_WALL, ROAD_CLEARANCE = 2.2, 4.8
VAULT_N = 12
L = f"/levels/{LEVEL_NAME}"
SHAPE_REACH = 700.0     # m: a shape whose position is further from every tube is not read (merged tiles: 384 m)
CUT_GROUPS = ("terrain_skin", "walls", "fences", "roads")    # roads: the yards meshed on the DTM over a tube


# ------------------------------------------------------------------ the data
def lines():
    """[(kind 'road' | 'rail', props, Q (n, 3) level coordinates)] of the tunnels and galleries."""
    src = {}
    for key, layer in (("roads", "TLM_STRASSE"), ("rail", "TLM_EISENBAHN")):
        p = os.path.join(DATA, "tlm", layer + ".json")
        if os.path.exists(p):
            src[key] = [f for f in json.load(open(p))["features"] if f["props"].get("KUNSTBAUTE") in KINDS]
    if len(src) < 2 and os.path.exists(PACK):
        pack = json.load(gzip.open(PACK, "rt"))
        for key in ("roads", "rail"):
            src.setdefault(key, [f for f in pack[key]["features"] if f["props"].get("KUNSTBAUTE") in KINDS])
    out = []
    for key, feats in src.items():
        for f in feats:
            for part in f["parts"]:
                p = np.asarray(part, np.float64)
                xy = np.array([lv95_to_local(e, n) for e, n in p[:, :2]])
                out.append(("road" if key == "roads" else "rail", f["props"], np.column_stack([xy, p[:, 2]])))
    return out


def read_items(path):
    return [json.loads(l) for l in open(path) if l.strip()]


class Terrain:
    """The level's .ter: heights (row 0 south), layers, and holes written back with save()."""

    def __init__(self, lv):
        blk = [o for o in read_items(os.path.join(lv, "main", "MissionGroup", "level_objects", "terrain", "items.level.json"))
               if o.get("class") == "TerrainBlock"][0]
        self.path = os.path.join(lv, os.path.basename(blk.get("terrainFile", "theTerrain.ter")))
        self.x0, self.y0, self.z0 = blk["position"]
        self.maxh = float(blk["maxHeight"])
        self.sq = float(blk.get("squareSize", 1))
        raw = open(self.path, "rb").read()
        self.n = n = int(np.frombuffer(raw[1:5], "<u4")[0])
        self.head = raw[:5]
        self.q = np.frombuffer(raw[5:5 + 2 * n * n], "<u2").reshape(n, n)
        self.lay = np.frombuffer(raw[5 + 2 * n * n:5 + 3 * n * n], "u1").reshape(n, n).copy()
        self.tail = raw[5 + 3 * n * n:]
        self.h = self.z0 + self.q.astype(np.float64) / 65535.0 * self.maxh

    def sample(self, x, y):
        return map_coordinates(self.h, [(np.asarray(y, np.float64) - self.y0) / self.sq,
                                        (np.asarray(x, np.float64) - self.x0) / self.sq], order=1, mode="nearest")

    def inside(self, x, y):
        c, r = (x - self.x0) / self.sq, (y - self.y0) / self.sq
        return 0 <= c < self.n - 1 and 0 <= r < self.n - 1

    def save(self):
        tmp = self.path + ".part"
        with open(tmp, "wb") as f:
            f.write(self.head)
            f.write(self.q.astype("<u2").tobytes())
            f.write(self.lay.astype("u1").tobytes())
            f.write(self.tail)
        os.replace(tmp, self.path)


_ARR = re.compile(r'<float_array id="([^"]+)-pa"[^>]*>([^<]*)</float_array>')
_GEOM = re.compile(r'<geometry id="([^"]+)"[^>]*>.*?</geometry>', re.S)
_TRIS = re.compile(r'(<triangles material="([^"]*)" count=")(\d+)(">)(.*?)(<p>)([^<]*)(</p>)', re.S)


def dae_triangles(text):
    """{geometry id: [(material, (k, 3, 3) corners)]} of every geometry of a DAE (positions of the shape)."""
    out = {}
    for g in _GEOM.finditer(text):
        body = g.group(0)
        m = _ARR.search(body)
        if not m:
            continue
        V = np.array(m.group(2).split(), np.float64).reshape(-1, 3)
        parts = []
        for t in _TRIS.finditer(body):
            nin = t.group(5).count("<input")
            idx = np.array(t.group(7).split(), np.int64).reshape(-1, 3, nin)
            parts.append((t.group(2), V[idx[:, :, 0]]))
        out[g.group(1)] = parts
    return out


def dae_drop(text, drop):
    """The DAE with the triangles drop(material, corners (k, 3, 3)) -> bool (k,) marks taken out of every <triangles>
    of every geometry (positions of the shape); the vertex arrays stay. Returns (text, triangles dropped)."""
    out, pos, n = [], 0, 0
    for g in _GEOM.finditer(text):
        body = g.group(0)
        m = _ARR.search(body)
        if not m:
            continue
        V = np.array(m.group(2).split(), np.float64).reshape(-1, 3)
        pieces, bpos = [], 0
        for t in _TRIS.finditer(body):
            nin = t.group(5).count("<input")
            idx = np.array(t.group(7).split(), np.int64).reshape(-1, 3, nin)
            d = drop(t.group(2), V[idx[:, :, 0]])
            if not d.any():
                continue
            n += int(d.sum())
            keep = idx[~d]
            pieces.append(body[bpos:t.start()])
            pieces.append(t.group(1) + str(len(keep)) + t.group(4) + t.group(5) + t.group(6)
                          + " ".join(map(str, keep.ravel())) + t.group(8))
            bpos = t.end()
        if pieces:
            pieces.append(body[bpos:])
            out.append(text[pos:g.start()])
            out.append("".join(pieces))
            pos = g.end()
    out.append(text[pos:])
    return "".join(out), n


def group_shapes(lv, group):
    """[(items file, item, shape path on disk)] of the TSStatics under main/MissionGroup/<group>/ (recursive)."""
    out = []
    base = os.path.join(lv, "main", "MissionGroup", *group.split("/"))
    for dp, _, fs in os.walk(base):
        if "items.level.json" not in fs:
            continue
        p = os.path.join(dp, "items.level.json")
        for o in read_items(p):
            if o.get("class") == "TSStatic" and o.get("shapeName", "").startswith("/levels/"):
                out.append((p, o, os.path.join(lv, *o["shapeName"].split("/")[3:])))
    return out


def find_shapes(lv, group_names):
    """Every TSStatic whose items file lies under a folder named like one of group_names."""
    out = []
    for dp, _, fs in os.walk(os.path.join(lv, "main", "MissionGroup")):
        if "items.level.json" in fs and any(g in dp.replace(os.sep, "/").split("/") for g in group_names):
            p = os.path.join(dp, "items.level.json")
            for o in read_items(p):
                if o.get("class") == "TSStatic" and o.get("shapeName", "").startswith("/levels/"):
                    out.append((p, o, os.path.join(lv, *o["shapeName"].split("/")[3:])))
    return out


# ------------------------------------------------------------------ the meshes they join
class Tops:
    """Up faces of the road and track meshes near the portals: height at (x, y) or nan."""

    def __init__(self, lv, near, radius=40.0):
        tree = cKDTree(near)
        tris, kinds = [], []
        for group, kind, mats in (("roads", "road", None), ("railway", "rail", ("mp_rail_head",))):
            for _, o, path in group_shapes(lv, group):
                if not os.path.exists(path):
                    continue
                pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
                if tree.query(pos[:2], distance_upper_bound=600.0)[0] == np.inf:
                    continue
                for parts in dae_triangles(open(path, encoding="utf-8").read()).values():
                    for mat, T in parts:
                        if mats and mat.replace("-mat", "") not in mats:
                            continue
                        if kind == "road" and not mat.startswith(("mp_road", "mp_hard", "mp_sidewalk", "mp_gravel")):
                            continue
                        T = T + pos
                        c = T.mean(1)
                        k = tree.query(c[:, :2], distance_upper_bound=radius)[0] < np.inf
                        nz = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
                        up = nz[:, 2] > 0.5 * np.linalg.norm(nz, axis=1)
                        T = T[k & up]
                        if len(T):
                            tris.append(T)
                            kinds += [kind] * len(T)
        self.T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        self.kind = np.array(kinds)
        self.tree = cKDTree(self.T.mean(1)[:, :2]) if len(self.T) else None

    def height(self, x, y, kind, zhint, dz=LIVE_DZ):
        """Height of the up face of `kind` over (x, y) nearest zhint, within dz of it (nan if none)."""
        if self.tree is None:
            return np.nan
        if kind == "rail":
            # the rail heads are 7 cm wide: the median of the heads within 2.5 m, less nothing (z of the rails)
            near = [i for i in self.tree.query_ball_point([x, y], 2.5) if self.kind[i] == "rail"]
            z = np.array([self.T[i, :, 2].mean() for i in near])
            z = z[np.abs(z - zhint) < dz]
            return float(np.median(z)) if len(z) else np.nan
        best = np.nan
        for i in self.tree.query_ball_point([x, y], 12.0):
            if self.kind[i] != kind:
                continue
            a, b, c = self.T[i]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            w0 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
            w1 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
            w2 = 1 - w0 - w1
            if min(w0, w1, w2) < -1e-6:
                continue
            z = w0 * a[2] + w1 * b[2] + w2 * c[2]
            if abs(z - zhint) < dz and (np.isnan(best) or abs(z - zhint) < abs(best - zhint)):
                best = z
        return best


# ------------------------------------------------------------------ one tunnel
class Tube:
    def __init__(self, kind, props, Q):
        self.kind, self.props = kind, props
        art = props.get("OBJEKTART", "")
        if kind == "road":
            self.cw = CARRIAGEWAY.get(art, 4.6)
            self.hw = self.cw / 2 + WALK
            self.wall, self.crown = ROAD_WALL, ROAD_CLEARANCE + 0.9
        else:
            self.hw, self.wall, self.crown = PROFILE.get(art, PROFILE["Normalspur"])
            self.cw = 0.0
        self.hw_out = self.hw + SHELL
        # stations every STEP m along the line (xy smoothed a little), its own z
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q[:, :2], axis=0), axis=1))]
        self.length = float(d[-1])
        s = np.linspace(0, d[-1], max(2, int(math.ceil(d[-1] / STEP)) + 1))
        P = np.column_stack([np.interp(s, d, Q[:, k]) for k in range(3)])
        if len(P) > 4:
            for k in (0, 1):
                inner = gaussian_filter1d(P[:, k], 1.0, mode="nearest")
                P[1:-1, k] = inner[1:-1]
        self.s, self.P = s, P
        T = np.gradient(P[:, :2], axis=0)
        self.T = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        self.N = np.column_stack([-self.T[:, 1], self.T[:, 0]])
        self.live = [False, False]
        # the floor: the carriageway (road) or the top of the ballast (rail: swissTLM3D gives the rails)
        import railway
        self.rail_drop = 0.0 if kind == "road" else railway.RAIL_H + railway.SLEEPER_H
        self.floor = P[:, 2] - self.rail_drop

    def join(self, tops):
        """Live portals: the line moved to the mesh it joins there, the change faded over FADE m."""
        dz = np.zeros(len(self.s))
        for e, (i, sgn) in enumerate(((0, -1), (len(self.s) - 1, 1))):
            p, t = self.P[i], self.T[i] * sgn
            zs = []
            for back in (1.5, 3.0, 4.5, 6.0):
                q = p[:2] + t * back
                z = tops.height(q[0], q[1], self.kind, p[2])
                if np.isfinite(z):
                    zs.append(z)
            if zs:
                self.live[e] = True
                change = (zs[0] - p[2])
                w = np.clip(1 - (self.s if e == 0 else self.s[-1] - self.s) / FADE, 0, 1)
                dz += change * w
        self.P[:, 2] += dz
        self.floor = self.P[:, 2] - self.rail_drop

    # ---- geometry
    def ring(self):
        """Inside outline of the cross-section: (n across, z over the floor), right floor corner to left floor corner."""
        a = np.linspace(0, math.pi, VAULT_N + 1)
        vault = np.column_stack([self.hw * np.cos(a), self.wall + (self.crown - self.wall) * np.sin(a)])
        return np.vstack([[self.hw, 0.0], vault, [-self.hw, 0.0]])

    def extrados(self, n):
        """Height of the top of the shell over the floor at n across (nan outside it)."""
        n = np.abs(np.asarray(n, np.float64))
        r = self.hw_out
        t = np.clip(n / r, 0, 1)
        z = self.wall + (self.crown + SHELL - self.wall) * np.sqrt(np.maximum(1 - t ** 2, 0))
        return np.where(n <= r, z, np.nan)

    def frame(self, i, n, z):
        """Level coordinates of (n across, z over the floor) at station i."""
        c = self.P[i, :2] + self.N[i] * n
        return np.r_[c, self.floor[i] + z]

    def sweep(self, outline, i0, i1, inward):
        """Triangles of an outline [(n, z)] swept from station i0 to i1."""
        tris = []
        for i in range(i0, i1):
            A = [self.frame(i, n, z) for n, z in outline]
            B = [self.frame(i + 1, n, z) for n, z in outline]
            for k in range(len(outline) - 1):
                q = [A[k], B[k], B[k + 1], A[k], B[k + 1], A[k + 1]]
                tris += q if not inward else [q[0], q[2], q[1], q[3], q[5], q[4]]
        return np.array(tris, np.float64).reshape(-1, 3, 3) if tris else np.zeros((0, 3, 3))

    def orient(self, T, i_mid, inside):
        """Turn triangles to face the axis (inside True) or away from it."""
        if not len(T):
            return T
        c = T.mean(1)
        # the axis point nearest each triangle: project on the station frame
        k = np.clip(np.searchsorted(self.s, self.s_of(c[:, :2])), 0, len(self.s) - 1)
        ax = np.column_stack([self.P[k, :2], self.floor[k] + self.crown * 0.45])
        nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        out = ((c - ax) * nrm).sum(1) > 0
        flip = out if inside else ~out
        T = T.copy()
        T[flip] = T[flip][:, ::-1]
        return T

    def s_of(self, xy):
        tree = getattr(self, "_tree", None)
        if tree is None:
            self._tree = tree = cKDTree(self.P[:, :2])
        return self.s[tree.query(xy)[1]]

    def local(self, xy):
        """(s along, n across, station index) of points (k, 2)."""
        tree = getattr(self, "_tree", None)
        if tree is None:
            self._tree = tree = cKDTree(self.P[:, :2])
        _, i = tree.query(xy)
        d = xy - self.P[i, :2]
        along = (d * self.T[i]).sum(1)
        return self.s[i] + along, (d * self.N[i]).sum(1), i


# ------------------------------------------------------------------ the step
def build_tube(tb, mats, ter=None):
    """{material: triangles} of the tube, its portals and its deck."""
    out = {}

    def add(m, T):
        if len(T):
            out.setdefault(m, []).append(T)
    m = len(tb.s)
    # the portals stand PORTAL_OUT out of the swissTLM3D ends: stations added before the first and after the last
    ext = PORTAL_OUT + HEAD
    P = tb.P
    pre = P[0] - np.r_[tb.T[0] * ext, 0]
    post = P[-1] + np.r_[tb.T[-1] * ext, 0]
    tb.P = np.vstack([pre, P, post])
    tb.s = np.r_[-ext, tb.s, tb.s[-1] + ext]
    tb.T = np.vstack([tb.T[0], tb.T, tb.T[-1]])
    tb.N = np.vstack([tb.N[0], tb.N, tb.N[-1]])
    tb.floor = np.r_[tb.floor[0], tb.floor, tb.floor[-1]]
    tb._tree = None
    m = len(tb.s)
    ring = tb.ring()
    add("mp_tunnel_wall", tb.orient(tb.sweep(ring, 0, m - 1, False), 0, True))
    # outer shell near the portals
    outer = np.column_stack([ring[1:-1, 0] * tb.hw_out / tb.hw,
                             tb.wall + (ring[1:-1, 1] - tb.wall) * (tb.crown + SHELL - tb.wall) / (tb.crown - tb.wall)])
    outer[0, 1] = outer[-1, 1] = tb.wall
    outer = np.vstack([[tb.hw_out, -0.6], outer, [-tb.hw_out, -0.6]])
    thin = np.zeros(m, bool)
    if ter is not None:                    # thin cover: holes in the ground over the tube, the shell must close them
        for o in (-tb.hw_out, 0.0, tb.hw_out):
            g = ter.sample(tb.P[:, 0] + tb.N[:, 0] * o, tb.P[:, 1] + tb.N[:, 1] * o)
            thin |= g < tb.floor + np.nan_to_num(tb.extrados(abs(o) * 0.999), nan=tb.wall) + COVER_THIN
        thin = np.convolve(thin, np.ones(5), "same") > 0
    near = np.where((tb.s <= SHELL_NEAR) | (tb.s >= tb.s[-1] - SHELL_NEAR) | thin)[0]
    if len(near):
        for a, b in runs(near):
            add("mp_tunnel_wall", tb.orient(tb.sweep(outer, a, b, False), 0, False))
    # the deck: inside the tube only (the road or track of the level runs up to the swissTLM3D portal)
    i0, i1 = 1, m - 2
    if tb.kind == "road":
        c = tb.cw / 2
        add("mp_road_asphalt", up(tb.sweep([(c, 0.0), (-c, 0.0)], i0, i1, False)))
        for sg in (1, -1):
            add("mp_tunnel_walk", up(tb.sweep([(sg * tb.hw, KERB), (sg * c, KERB)], i0, i1, False)))
            add("mp_tunnel_walk", tb.orient(tb.sweep([(sg * c, KERB), (sg * c, 0.0)], i0, i1, False), 0, True))
    else:
        add_track(tb, add, i0, i1)
    # a floor under the headwall and up to the swissTLM3D portal, 3 cm under the level's own track or road there:
    # the holes reach out to the headwall's face and one saw through them past the ballast (the lake under it)
    for a, b in ((0, i0), (i1, m - 1)):
        add("mp_ballast" if tb.kind != "road" else "mp_road_asphalt",
            up(tb.sweep([(tb.hw, -0.03), (-tb.hw, -0.03)], a, b, False)))
    # an apron APRON m out in front of each face, as wide as the headwall: the hole squares straddle the face and
    # beside the level's narrower track bed one saw the lake through them at the jamb feet (laptop run 7)
    W = tb.hw_out + HEAD_W
    for st, way in ((0, -1), (m - 1, 1)):
        d = np.r_[tb.T[st] * way * APRON, 0.0]
        a0, a1 = tb.frame(st, W, -0.03), tb.frame(st, -W, -0.03)
        add("mp_ballast" if tb.kind != "road" else "mp_road_asphalt", up(np.array([[a0, a1, a1 + d], [a0, a1 + d, a0 + d]])))
        if ter is None:
            continue
        # its open edges go down FOOT under the lowest ground beside them, as the headwall's sides do: on the lake
        # side of the S portal the apron stood as a plate 1-1.5 m over the slope (laptop run 8)
        for p, q in ((a0, a0 + d), (a0 + d, a1 + d), (a1 + d, a1)):
            t = np.linspace(0, 1, 6)[:, None]
            L = p[:2] + (q[:2] - p[:2]) * t
            g = float(np.min(ter.sample(L[:, 0], L[:, 1])))
            if g < min(p[2], q[2]) - 0.1:
                z = g - FOOT
                p2, q2 = np.r_[p[:2], z], np.r_[q[:2], z]
                quad = np.array([[p, q, q2], [p, q2, p2]])
                add("mp_tunnel_portal", np.concatenate([quad, quad[:, ::-1]]))
    # lamp strips along both sides of the vault
    a = math.radians(55)
    for sg in (1, -1):
        n0 = sg * tb.hw * math.cos(a)
        z0 = tb.wall + (tb.crown - tb.wall) * math.sin(a) - 0.06
        add("mp_tunnel_lamp", tb.orient(tb.sweep([(n0 + 0.12, z0), (n0 - 0.12, z0)], i0, i1, False), 0, True))
    # headwalls at the live portals
    for e, live in enumerate(tb.live):
        if live:
            add("mp_tunnel_portal", headwall(tb, 0 if e == 0 else m - 1, 1 if e == 0 else -1, ter))
    return {k: np.concatenate(v) for k, v in out.items()}


def runs(idx):
    """Consecutive runs of sorted station indices as (first, last) pairs (at least 2 stations)."""
    out, a = [], idx[0]
    for p, q in zip(idx[:-1], idx[1:]):
        if q != p + 1:
            if p > a:
                out.append((a, p))
            a = q
    if idx[-1] > a:
        out.append((a, idx[-1]))
    return out


def up(T):
    nz = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, 2]
    T = T.copy()
    T[nz < 0] = T[nz < 0][:, ::-1]
    return T


def add_track(tb, add, i0, i1):
    import railway as rw
    gauge = rw.GAUGE.get(tb.props.get("OBJEKTART"), 1.435)
    sl_len = rw.SLEEPER_LEN.get(tb.props.get("OBJEKTART"), 2.6)
    add("mp_ballast", up(tb.sweep([(tb.hw, 0.0), (-tb.hw, 0.0)], i0, i1, False)))
    s0, s1 = tb.s[i0], tb.s[i1]
    sl = []
    for si in np.arange(s0 + rw.SLEEPER_STEP / 2, s1, rw.SLEEPER_STEP):
        i = int(min(np.searchsorted(tb.s, si), len(tb.s) - 1))
        c = tb.P[i, :2] + tb.T[i] * (si - tb.s[i])
        z = tb.floor[i]
        sl.append(rw._box(c - tb.T[i] * rw.SLEEPER_W / 2, c + tb.T[i] * rw.SLEEPER_W / 2, sl_len / 2,
                          np.array([z - 0.05] * 2), np.array([z + rw.SLEEPER_H] * 2), tb.N[i]))
    if sl:
        add("mp_sleeper", np.concatenate(sl))
    for sg in (1, -1):
        off = sg * (gauge / 2 + rw.RAIL_W / 2)
        tops, flanks = [], []
        for i in range(i0, i1):
            a, b = tb.P[i, :2] + tb.N[i] * off, tb.P[i + 1, :2] + tb.N[i + 1] * off
            zb = np.array([tb.floor[i], tb.floor[i + 1]]) + rw.SLEEPER_H
            B = rw._box(a, b, rw.RAIL_W / 2, zb, zb + rw.RAIL_H, tb.N[i])
            nz = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0])[:, 2]
            top = nz > 0.5 * np.abs(nz).max()
            tops.append(B[top])
            flanks.append(B[~top])
        add("mp_rail_head", np.concatenate(tops))
        add("mp_rail_steel", np.concatenate(flanks))


def headwall(tb, i, inward, ter=None):
    """A headwall HEAD m thick from station i inwards (inward +1 / -1 along the stations), round the opening. Each
    side goes down to FOOT under the lowest ground at its outer edge: on the lake side of the Vallone d'Agno the
    ground falls away beside the track and the wall stood on nothing, a gap under it (laptop run 4)."""
    ring = tb.ring()
    W = tb.hw_out + HEAD_W
    top = tb.crown + SHELL + HEAD_UP
    j = i + inward
    bot = {1: -0.6, -1: -0.6}
    if ter is not None:
        for sg in (1, -1):
            g = [float(ter.sample([tb.frame(st, sg * W * f, 0.0)[0]], [tb.frame(st, sg * W * f, 0.0)[1]])[0])
                 for st in (i, j) for f in (0.6, 1.0)]
            bot[sg] = min(-0.6, min(g) - tb.floor[i] - FOOT)
    # the face: the outer rectangle minus the opening, as a fan of quads between the opening and the rectangle
    frame = []
    k = len(ring)
    # rectangle points matched to every ring point: same n clipped to the rectangle, on its top or sides
    rect = []
    for n, z in ring:
        if z <= tb.wall + 1e-6:
            rect.append((math.copysign(W, n), bot[1 if n > 0 else -1] if z == 0.0 else z))
        else:
            rect.append((n * W / tb.hw, top))
    rect[0] = (W, bot[1])
    rect[-1] = (-W, bot[-1])
    tris = []
    for st, face_out in ((i, True), (j, False)):
        for a in range(k - 1):
            p0, p1 = tb.frame(st, *ring[a]), tb.frame(st, *ring[a + 1])
            q0, q1 = tb.frame(st, *rect[a]), tb.frame(st, *rect[a + 1])
            tris += [p0, q0, q1, p0, q1, p1]
        # under the floor's edge down to the side's foot (the fan joins the floor corner to the foot diagonally)
        for sg in (1, -1):
            if bot[sg] < -0.6 + 1e-6:
                tris += [tb.frame(st, sg * tb.hw, 0.0), tb.frame(st, sg * tb.hw, bot[sg]), tb.frame(st, sg * W, bot[sg])]
        # the corners of the rectangle above the vault's sides
        for sg in (1, -1):
            a0 = tb.frame(st, sg * W, tb.wall)
            a1 = tb.frame(st, sg * W, top)
            a2 = tb.frame(st, sg * tb.hw * 0.92, top)
            tris += [a0, a1, a2]
    # the outer sides and the top of the block
    for (n0, z0), (n1, z1) in (((W, bot[1]), (W, top)), ((W, top), (-W, top)), ((-W, top), (-W, bot[-1]))):
        A0, A1 = tb.frame(i, n0, z0), tb.frame(i, n1, z1)
        B0, B1 = tb.frame(j, n0, z0), tb.frame(j, n1, z1)
        tris += [A0, B0, B1, A0, B1, A1]
    # the cornice: a lip 0.25 m out over the face
    for st, sgn in ((i, -inward),):
        c0 = tb.frame(st, W + 0.2, top) + np.r_[tb.T[st] * sgn * 0.25, 0]
        c1 = tb.frame(st, -W - 0.2, top) + np.r_[tb.T[st] * sgn * 0.25, 0]
        d0 = tb.frame(j, W + 0.2, top)
        d1 = tb.frame(j, -W - 0.2, top)
        lift = np.r_[0, 0, 0.3]
        tris += [c0 + lift, d0 + lift, d1 + lift, c0 + lift, d1 + lift, c1 + lift]
        tris += [c0, c0 + lift, c1 + lift, c0, c1 + lift, c1]
        tris += [c0, c1, d1, c0, d1, d0]
    T = np.array(tris, np.float64).reshape(-1, 3, 3)
    # out of the block: away from its centre
    c = (tb.frame(i, 0, top / 2) + tb.frame(j, 0, top / 2)) / 2
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    # faces of the opening's rim look into the opening: the face polygons are turned by their station
    cen = T.mean(1)
    toward = ((cen - c) * nrm).sum(1) < 0
    T[toward] = T[toward][:, ::-1]
    return T


def mound(tb, ter, tops=None):
    """Raise the ground over the tube where it runs in the hill but its side or top stands out of the slope (laptop
    run 3 of the Ticino test, 2026-10-26: the lake side of the Vallone d'Agno vault stood out as a grey hump; the
    DTM there is the slope smeared over a tube that is in rock, and the portal cuttings of the DTM reach 4-8 m into
    the swissTLM3D tube, so the vault stood bare behind the headwalls). From the swissTLM3D portals in, COVER_MIN
    over the shell, then 1:1 down over MOUND_W. Never under a road or track face. Returns the number of terrain
    vertices raised."""
    ok = np.ones(len(tb.s), bool)
    ext = tb.hw_out + MOUND_W
    xs, ys = tb.P[ok, 0], tb.P[ok, 1]
    c0 = int(max(0, math.floor((xs.min() - ext - ter.x0) / ter.sq)))
    c1 = int(min(ter.n - 1, math.ceil((xs.max() + ext - ter.x0) / ter.sq)))
    r0 = int(max(0, math.floor((ys.min() - ext - ter.y0) / ter.sq)))
    r1 = int(min(ter.n - 1, math.ceil((ys.max() + ext - ter.y0) / ter.sq)))
    R, C = np.mgrid[r0:r1 + 1, c0:c1 + 1]
    R, C = R.ravel(), C.ravel()
    x, y = ter.x0 + C * ter.sq, ter.y0 + R * ter.sq
    s, n, i = tb.local(np.column_stack([x, y]))
    an = np.abs(n)
    # from the swissTLM3D portal in, one square behind the headwall's face: a vertex raised nearer to it made the
    # terrain (and the hole caps) in front of the face slope up into the opening (spikes on the track in the renders)
    k = ok[i] & (an <= ext) & (s >= tb.s[0]) & (s <= tb.s[-1])
    # the terrain is flat between its vertices 1.5 m apart: each vertex takes the highest shell within one square
    near = np.maximum(an - ter.sq, 0.0)
    want = tb.floor[i] + np.nan_to_num(tb.extrados(np.minimum(near, tb.hw_out)), nan=tb.wall) + COVER_MIN \
        - np.maximum(near - tb.hw_out, 0.0)
    h = ter.h[R, C]
    k &= want > h
    if tops is not None:
        for j in np.where(k & (an > tb.hw_out))[0]:      # over the tube the level's own track goes into it anyway
            for kind in ("road", "rail"):
                if np.isfinite(tops.height(x[j], y[j], kind, want[j], dz=30.0)):
                    k[j] = False
    R, C, w = R[k], C[k], want[k]
    ter.h[R, C] = w
    ter.q = ter.q.copy() if not ter.q.flags.writeable else ter.q
    ter.q[R, C] = np.clip(np.round((w - ter.z0) / ter.maxh * 65535.0), 0, 65535).astype(np.uint16)
    return int(k.sum())


def holes(tb, ter):
    """Terrain samples to hole: squares (lower-left sample) meeting the footprint of the tube from the headwall in,
    where the ground stands between the floor + CLEAR and the shell's top. Returns (rows, cols)."""
    ext = tb.hw_out + HEAD_W
    xs, ys = tb.P[:, 0], tb.P[:, 1]
    c0 = int(max(0, math.floor((xs.min() - ext - ter.x0) / ter.sq) - 2))
    c1 = int(min(ter.n - 2, math.ceil((xs.max() + ext - ter.x0) / ter.sq) + 2))
    r0 = int(max(0, math.floor((ys.min() - ext - ter.y0) / ter.sq) - 2))
    r1 = int(min(ter.n - 2, math.ceil((ys.max() + ext - ter.y0) / ter.sq) + 2))
    if c1 <= c0 or r1 <= r0:
        return np.zeros(0, int), np.zeros(0, int)
    R, C = np.mgrid[r0:r1 + 1, c0:c1 + 1]
    R, C = R.ravel(), C.ravel()
    # only the squares along the tube: the box of a long tube (the Ceneri base tunnel from a Lugano zone) held millions
    import shapely
    band = shapely.LineString(tb.P[:, :2]).buffer(ext + 2 * STEP + 3 * ter.sq)
    shapely.prepare(band)
    near = shapely.contains_xy(band, ter.x0 + (C + 0.5) * ter.sq, ter.y0 + (R + 0.5) * ter.sq)
    R, C = R[near], C[near]
    hit = np.zeros(len(R), bool)
    # every square tested on a 4 x 4 grid of points in it
    for u in (0.1, 0.37, 0.63, 0.9):
        for v in (0.1, 0.37, 0.63, 0.9):
            x = ter.x0 + (C + u) * ter.sq
            y = ter.y0 + (R + v) * ter.sq
            s, n, i = tb.local(np.column_stack([x, y]))
            inside = (s >= tb.s[0]) & (s <= tb.s[-1]) & (np.abs(n) <= tb.hw_out + 0.1)
            if not inside.any():
                continue
            g = ter.sample(x, y)
            z = g - tb.floor[i]
            top = np.nan_to_num(tb.extrados(np.minimum(np.abs(n), tb.hw_out)), nan=0.0)
            hit |= inside & (z > CLEAR) & (z < top + 0.3)
    return R[hit], C[hit]


def cap(tb, ter, R, C, colours):
    """Triangles (and vertex colours) closing the hole squares outside the tube at the ground's own heights."""
    if not len(R):
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 4))
    k = int(round(ter.sq / CAP_RES))
    f = (np.arange(k) + 0.5) / k
    tris, cols = [], []
    for r, c in zip(R, C):
        u, v = np.meshgrid(np.arange(k + 1) / k, np.arange(k + 1) / k)
        x = ter.x0 + (c + u) * ter.sq
        y = ter.y0 + (r + v) * ter.sq
        z = square_height(ter, r, c, u, v)
        # the fine cells taken by the tube (from the headwall's face in) are left open
        uc, vc = np.meshgrid(f, f)
        xc, yc = ter.x0 + (c + uc) * ter.sq, ter.y0 + (r + vc) * ter.sq
        s, n, _ = tb.local(np.column_stack([xc.ravel(), yc.ravel()]))
        taken = ((s >= tb.s[0]) & (s <= tb.s[-1]) & (np.abs(n) <= tb.hw_out - 0.05)).reshape(k, k)
        col = colours(r, c)
        for a in range(k):
            for b in range(k):
                if taken[a, b]:
                    continue
                p00 = (x[a, b], y[a, b], z[a, b])
                p10 = (x[a, b + 1], y[a, b + 1], z[a, b + 1])
                p01 = (x[a + 1, b], y[a + 1, b], z[a + 1, b])
                p11 = (x[a + 1, b + 1], y[a + 1, b + 1], z[a + 1, b + 1])
                tris += [p00, p10, p11, p00, p11, p01]
                cols += [col] * 6
    T = np.array(tris, np.float64).reshape(-1, 3, 3)
    return up(T), np.array(cols, np.float64).reshape(-1, 3, 4)


def square_height(ter, r, c, u, v):
    """Height inside the terrain square (r, c) at fractions (u along x, v along y): the two triangles of the square
    split from its lower-left to its upper-right corner, as the game splits them (when not, the cap is off by the
    difference of the two splits, a few cm on a slope)."""
    h00, h10 = ter.h[r, c], ter.h[r, c + 1]
    h01, h11 = ter.h[r + 1, c], ter.h[r + 1, c + 1]
    lower = u >= v
    return np.where(lower, h00 + u * (h10 - h00) + v * (h11 - h10), h00 + v * (h01 - h00) + u * (h11 - h01))


def tunnels_step(root, report=None):
    t0 = time.time()
    lv = os.path.join(root, "levels", LEVEL_NAME)
    ter = Terrain(lv)
    cand = []
    for kind, props, Q in lines():
        if len(Q) < 2:
            continue
        if not (ter.inside(*Q[0, :2]) or ter.inside(*Q[-1, :2])):
            continue
        cand.append(Tube(kind, props, Q))
    res = {"candidates": len(cand), "tunnels": 0, "km": 0.0, "portals": 0, "holes": 0, "cap_triangles": 0,
           "cut_triangles": 0, "forest_removed": 0, "lights": 0, "ai_roads": 0, "list": []}
    if not cand:
        print("tunnels: none in the level", flush=True)
        return res
    ends = np.array([tb.P[i, :2] for tb in cand for i in (0, -1)])
    tops = Tops(lv, ends)
    tubes = []
    for tb in cand:
        tb.join(tops)
        if any(tb.live):
            tubes.append(tb)
    print("tunnels: %d lines, %d with a live portal (%.0f s)" % (len(cand), len(tubes), time.time() - t0), flush=True)
    mats = materials()
    bng.write_materials(os.path.join(lv, "art", "shapes", "tunnels", "main.materials.json"), mats)
    sys.path.insert(0, HERE)
    try:
        import steep_skin
        names = json.load(open(os.path.join(lv, "theTerrain.terrain.json")))["materials"]
        zi = bng.LevelFiles(root)
        base = steep_skin.BaseColours(zi, f"levels/{LEVEL_NAME}", names, ter.n)

        def colours(r, c):
            col = base(np.array([ter.lay[r, c]]), np.array([r]), np.array([c]))[0]
            col = steep_skin.earth_colour(col[None])[0]
            return np.r_[col, 1.0]
    except Exception as e:                     # no colour maps: a neutral earth
        print("tunnels: terrain colours not read:", e, flush=True)
        colours = lambda r, c: np.array([0.5, 0.45, 0.38, 1.0])
    items, hole_sq, volumes = [], [], []
    shp_dir = os.path.join(lv, "art", "shapes", "tunnels")
    os.makedirs(shp_dir, exist_ok=True)
    for k, tb in enumerate(tubes):
        res["mound_vertices"] = res.get("mound_vertices", 0) + mound(tb, ter, tops)
        parts = build_tube(tb, mats, ter)
        R, C = holes(tb, ter)
        capT, capC = cap(tb, ter, R, C, colours)
        origin = np.r_[tb.P[len(tb.P) // 2, :2], 0.0]
        mb = bng.MeshBuilder()
        for m, T in parts.items():
            V = T.reshape(-1, 3)
            uv = bng.box_uvs_soup(V, 2.0) if m in ("mp_tunnel_wall", "mp_tunnel_portal", "mp_tunnel_walk") \
                else V[:, :2] / 4.0
            mb.add(m, V, uvs=uv, normals=bng.flat_normals_soup(V))
        if len(capT):
            V = capT.reshape(-1, 3)
            mb.add("mp_steep_bank", V, uvs=V[:, :2] / 6.0, colors=capC.reshape(-1, 4))
        name = f"tunnel_{k:03d}"
        mb.write_dae(os.path.join(shp_dir, name + ".dae"), name=name, origin=origin)
        items.append(dict(bng.tsstatic(f"{L}/art/shapes/tunnels/{name}.dae", origin, collision=True), __parent="tunnels"))
        # lights under the vault
        for si in np.arange(tb.s[1] + LIGHT_STEP / 2, tb.s[-2], LIGHT_STEP):
            i = int(np.searchsorted(tb.s, si))
            p = tb.frame(i, 0.0, tb.crown - 0.4)
            items.append(tunnel_light(p))
            res["lights"] += 1
        hole_sq.append((R, C))
        volumes.append(tb)
        res["tunnels"] += 1
        res["km"] += tb.length / 1000
        res["portals"] += sum(tb.live)
        res["holes"] += len(R)
        res["cap_triangles"] += len(capT)
        res["list"].append({"name": tb.props.get("NAME") or "", "kind": tb.props.get("OBJEKTART"), "length_m": round(tb.length),
                            "live": tb.live, "from": tb.P[1, :2].round(1).tolist(), "to": tb.P[-2, :2].round(1).tolist(),
                            "holes": len(R)})
        if tb.kind == "road":
            items.append(ai_road(tb, lv))
            res["ai_roads"] += 1
    # the terrain: holes
    for R, C in hole_sq:
        ter.lay[R, C] = 255
    ter.save()
    # the meshes in the way and the forest
    res["cut_triangles"] = cut_meshes(lv, volumes, ter, hole_sq)
    res["forest_removed"] = cut_forest(lv, volumes, ter)
    # the scene
    g = os.path.join(lv, "main", "MissionGroup", "tunnels")
    os.makedirs(g, exist_ok=True)
    with open(os.path.join(g, "items.level.json"), "w") as f:
        for o in items:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")
    mg = os.path.join(lv, "main", "MissionGroup", "items.level.json")
    groups = read_items(mg)
    if not any(o.get("name") == "tunnels" for o in groups):
        groups.append({"name": "tunnels", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "MissionGroup"})
        with open(mg + ".part", "w") as f:              # a new file: the level may be a hard-linked copy
            for o in groups:
                f.write(json.dumps(o, separators=(",", ":")) + "\n")
        os.replace(mg + ".part", mg)
    res["km"] = round(res["km"], 2)
    res["seconds"] = round(time.time() - t0)
    print("tunnels:", {k: v for k, v in res.items() if k != "list"}, flush=True)
    for t in res["list"]:
        print("  ", t, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res


def materials():
    return [italy_mats.material("mp_tunnel_wall", "m_concrete_old", "CONCRETE", base_color=[0.78, 0.77, 0.74, 1]),
            italy_mats.material("mp_tunnel_portal", "m_concrete_old", "CONCRETE", base_color=[0.86, 0.85, 0.82, 1]),
            italy_mats.material("mp_tunnel_walk", "m_concrete_old", "CONCRETE", base_color=[0.70, 0.70, 0.68, 1]),
            bng.material("mp_tunnel_lamp", base_color=[1.0, 0.86, 0.62, 1], roughness=0.4,
                         detail={"emissiveFactor": [1.0, 0.82, 0.55], "instanceEmissive": True})]


def tunnel_light(p):
    return {"class": "SpotLight", "persistentId": bng.pid(), "position": [float(v) for v in p],
            "rotationMatrix": [1, 0, 0, 0, 0, -1, 0, 1, 0], "range": 14.0, "innerAngle": 110.0, "outerAngle": 150.0,
            "intensity": 1200.0, "intensityUnit": "lm", "brightness": 0.24, "color": [1.0, 0.78, 0.5, 1.0],
            "castShadows": False, "isEnabled": True, "__parent": "tunnels"}


def ai_road(tb, lv):
    """A DecalRoad along the carriageway, its ends on the nearest AI road ends at the portals."""
    idx = np.unique(np.r_[np.arange(1, len(tb.s) - 1, max(1, int(10 / STEP))), len(tb.s) - 2])
    nodes = [[float(tb.P[i, 0]), float(tb.P[i, 1]), float(tb.floor[i]), float(tb.cw)] for i in idx]
    ends = []
    for o in read_items(os.path.join(lv, "main", "MissionGroup", "AIRoads", "items.level.json")):
        if o.get("class") == "DecalRoad" and o.get("nodes"):
            ends += [o["nodes"][0][:3], o["nodes"][-1][:3]]
    if ends:
        E = np.array(ends)
        tree = cKDTree(E[:, :2])
        for j in (0, -1):
            d, k = tree.query(nodes[j][:2])
            if d < 15.0:
                nodes.insert(0 if j == 0 else len(nodes), [float(E[k, 0]), float(E[k, 1]), float(E[k, 2]), float(tb.cw)])
    art = tb.props.get("OBJEKTART", "")
    return {"name": "tunnel_" + re.sub(r"\W+", "_", tb.props.get("NAME") or art).strip("_").lower(), "class": "DecalRoad",
            "persistentId": bng.pid(), "position": nodes[0][:3], "drivability": DRIVABILITY.get(art, 1),
            "improvedSpline": True, "material": "road_invisible", "nodes": nodes, "speedLimit": 13.89 if tb.cw < 6 else 22.22,
            "autoLanes": False, "lanesLeft": 1, "lanesRight": 1, "__parent": "tunnels"}


def in_volume(tb, P, margin=0.05):
    """Points (k, 3) inside the tube's body (shell included) from its headwalls in."""
    s, n, i = tb.local(P[:, :2])
    z = P[:, 2] - tb.floor[i]
    top = np.nan_to_num(tb.extrados(np.minimum(np.abs(n), tb.hw_out)), nan=-1.0)
    body = (s >= tb.s[0]) & (s <= tb.s[-1]) & (np.abs(n) <= tb.hw_out + margin) & (z > -0.7) & (z < top + margin)
    # in front of a live portal: the opening's clearance, APPROACH m out (a bank or skin standing in the way)
    vault = np.nan_to_num(tb.wall + (tb.crown - tb.wall) * np.sqrt(np.maximum(1 - (n / tb.hw) ** 2, 0)), nan=0.0)
    out = np.zeros(len(P), bool)
    for e, live in enumerate(tb.live):
        if live:
            a = (s < tb.s[0]) & (s >= tb.s[0] - APPROACH) if e == 0 else (s > tb.s[-1]) & (s <= tb.s[-1] + APPROACH)
            out |= a
    return body | (out & (np.abs(n) <= tb.hw) & (z > CLEAR + 0.15) & (z < vault))


def cut_meshes(lv, tubes, ter, hole_sq):
    """Triangles of the skin, the walls and the fences inside a tube, and of the skin over a hole, taken out."""
    holes = set()
    for R, C in hole_sq:
        holes.update(zip(R.tolist(), C.tolist()))
    boxes = []
    for tb in tubes:
        e = tb.hw_out + HEAD_W + APPROACH + 2
        boxes.append((tb.P[:, 0].min() - e, tb.P[:, 1].min() - e, tb.P[:, 0].max() + e, tb.P[:, 1].max() + e))
    total = 0
    near = cKDTree(np.concatenate([tb.P[:, :2] for tb in tubes]))
    for _, o, path in find_shapes(lv, CUT_GROUPS):
        if not os.path.exists(path):
            continue
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        if pos.any() and near.query(pos[:2], distance_upper_bound=SHAPE_REACH)[0] == np.inf:
            continue
        text = open(path, encoding="utf-8").read()
        skin = "terrain_skin" in path

        def drop(mat, T, pos=pos, skin=skin):
            c = T.mean(1) + pos
            d = np.zeros(len(T), bool)
            for (x0, y0, x1, y1), tb in zip(boxes, tubes):
                m = (c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1)
                if not m.any():
                    continue
                for k in range(3):
                    d[m] |= in_volume(tb, T[m, k] + pos)
                    d[m] |= in_volume(tb, 0.7 * T[m, k] + 0.3 * T[m].mean(1) + pos)
                d[m] |= in_volume(tb, c[m])
                if skin and holes:
                    r = np.floor((c[m, 1] - ter.y0) / ter.sq).astype(int)
                    cc = np.floor((c[m, 0] - ter.x0) / ter.sq).astype(int)
                    d[np.where(m)[0][[(a, b) in holes for a, b in zip(r, cc)]]] = True
            return d
        new, n = dae_drop(text, drop)
        if n:
            tmp = path + ".part"
            open(tmp, "w", encoding="utf-8").write(new)
            os.replace(tmp, path)
            total += n
    return total


def cut_forest(lv, tubes, ter):
    """Forest items standing in a tube's footprint where the ground was lower than its shell."""
    removed = 0
    fdir = os.path.join(lv, "forest")
    if not os.path.isdir(fdir):
        return 0
    for f in sorted(os.listdir(fdir)):
        if not f.endswith(".forest4.json"):
            continue
        p = os.path.join(fdir, f)
        rows = [json.loads(l) for l in open(p) if l.strip()]
        if not rows:
            continue
        P = np.array([r["pos"] for r in rows], np.float64)
        bad = np.zeros(len(rows), bool)
        for tb in tubes:
            e = tb.hw_out + HEAD_W + 2
            m = (P[:, 0] > tb.P[:, 0].min() - e) & (P[:, 0] < tb.P[:, 0].max() + e) & \
                (P[:, 1] > tb.P[:, 1].min() - e) & (P[:, 1] < tb.P[:, 1].max() + e)
            if not m.any():
                continue
            s, n, i = tb.local(P[m, :2])
            z = P[m, 2] - tb.floor[i]
            top = np.nan_to_num(tb.extrados(np.minimum(np.abs(n), tb.hw_out)), nan=0.0)
            hit = (s >= tb.s[0] - 1) & (s <= tb.s[-1] + 1) & (np.abs(n) <= tb.hw_out + 1.0) & (z < top + 1.0)
            bad[np.where(m)[0][hit]] = True
        if bad.any():
            removed += int(bad.sum())
            tmp = p + ".part"
            with open(tmp, "w") as fo:
                for r, b in zip(rows, bad):
                    if not b:
                        fo.write(json.dumps(r, separators=(",", ":")) + "\n")
            os.replace(tmp, p)
    return removed


if __name__ == "__main__":
    tunnels_step(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.join(DATA, ".."))),
                 report=sys.argv[2] if len(sys.argv) > 2 else None)
