"""Tunnels and galleries (v3.2, issue #19): the swissTLM3D road and railway lines in a tunnel, built in the level.

Up to v3.1.1 network.py and railway.py left every tunnel out: a road or track ran into the hillside and stopped at the
portal. This finishing step builds them on the built level:
- the lines: swissTLM3D TLM_STRASSE / TLM_EISENBAHN with KUNSTBAUTE Tunnel or Galerie (data/tlm of the build, or the
  pack of beamng/ticino/dati/tunnels_tlm.json.gz that tunnels_ref.yml takes for all of Ticino), kept where at least
  one portal joins a road or track of the level (LIVE m): the swissTLM3D z of a road is its carriageway, of a track
  its rails; at a live portal the line is moved to the height of the mesh it joins, and the change faded along it;
- the tube: a deck (asphalt between kerbed walkways, or ballast, sleepers and rails), straight walls and a vault
  (PROFILE by kind), the inside faces turned in, an outer shell (SHELL m) near the portals and where the cover is
  thin, concrete of Italy; the vault's normals follow its curve (vault_normals: one normal a triangle drew its 12
  facets as bands of light and shade); a tube cut at the terrain's edge, or an end that joins nothing, is closed;
- galleries (KUNSTBAUTE Galerie: the avalanche and rock-fall galleries of the mountain roads): open on the valley
  side, a hill wall, a roof slab falling to the valley, pillars on a parapet and a foundation wall down to the ground
  (gallery()); the ground on the valley side is kept down to the parapet (valley_clear), the ground in a gallery's
  open end goes under the floor (end_clear: the DTM smears the roof into a ramp there), and the cap rises over the
  roof where the kept ground stands above it (cap(): no open step between the roof and the slope);
- a portal at every live end: a headwall HEAD m thick round the opening, standing one terrain square (PORTAL_OUT)
  out of the swissTLM3D portal, with a cornice and the tunnel's name;
- what a driver sees in a Swiss road tunnel: edge and centre lines (lane lines on a one-way tube of two lanes,
  travel_dir), lit escape signs every SIGN_STEP m, SOS niches, emergency exits, jet fans in long tubes, a lamp strip
  and lights twice as dense in the portal zone; a rail tunnel its catenary;
- the terrain: a heightfield cannot pass over a tube, so the samples whose square meets the tube's footprint where
  the ground stands between its floor and the top of its shell become holes (layer 255 of the .ter: neither drawn
  nor colliding); the parts of those squares beside the tube are closed by a cap at the ground's own heights with
  the terrain skin's earth in the terrain's colour, the shell closes the rest;
- the meshes in the way: triangles of the terrain skin, the walls, the fences and the road meshes (yards meshed on the
  DTM) inside the tube or in the opening's clearance in front of a portal, of the skin over a hole, of the skin, the
  walls and the fences over a gallery's footprint in plan (over_gallery), and the forest items standing in the
  footprint where the ground was lower than the shell, are taken out;
- two shapes a tube: the solid one with collision, and the decor (paint, lamps, wires, fans, signs) without;
- lights: a SpotLight every LIGHT_STEP m under the vault, on day and night as in a real tunnel;
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
# Twin tubes (one swissTLM3D line per carriageway, Ticino 2026-10-28): the Galleria della Collina d'Oro's lines run 10.5-18 m
# apart, and with 10.5 m of motorway carriageway each tube was 13.5 m wide over its shell and its headwall 16.7 m:
# the tubes ran into each other and each headwall closed half the other's opening. A motorway tube is now two lanes
# (8 m, 10 m inside the walls) and a headwall stops short of the twin's opening (twin_heads).
TWIN_GAP = 0.3          # m a headwall keeps from the twin tube's inside wall
# One tunnel in pieces (Galleria Vedeggio-Cassarate, Ticino 2026-10-29): swissTLM3D splits a tunnel's line wherever
# its class or a junction changes. The 29 m piece in the middle had no live portal and was never built (a gap in the
# tube), and the two one-way lanes of the Cassarate portal (Einfahrt 15 m, Ausfahrt 11 m, 4.6 m apart) were two tubes
# standing in each other's lane. chain() joins pieces end to end into one tube, makes the two short lanes of one
# portal one wider piece, and leaves a branch (a service access) as a tube of its own whose joined end opens into the
# tube it meets (open_junctions).
JOIN = 1.0              # m: line ends this close are one node
BRANCH_MAX = 60.0       # m: lanes of a portal this short (or shorter) that end at portals PORTAL_SPAN apart are one
PORTAL_SPAN = 15.0
CHAIN_TURN = 50.0       # deg: at a node of three or more lines, the pair turning less than this is chained
# carriageway width (m) by swissTLM3D class; the rest of the classes are paths, never in a tunnel of the level
CARRIAGEWAY = {"1m Weg": 1.6, "2m Weg": 2.6, "3m Strasse": 3.6, "4m Strasse": 4.6, "6m Strasse": 6.6,
               "8m Strasse": 8.0, "10m Strasse": 10.0, "Autostrasse": 8.0, "Autobahn": 8.0, "Ausfahrt": 4.6,
               "Einfahrt": 4.6, "Autozug": 4.6, "Verbindung": 4.6, "Zufahrt": 4.6}
DRIVABILITY = {"1m Weg": 0.3, "2m Weg": 0.4, "3m Strasse": 0.75, "4m Strasse": 0.9}
# (half width inside, height of the straight walls, crown over the floor) by kind
PROFILE = {"Schmalspur": (2.6, 2.0, 5.8), "Normalspur": (3.0, 2.2, 6.8)}
ROAD_WALL, ROAD_CLEARANCE = 2.2, 4.8
VAULT_N = 12
L = f"/levels/{LEVEL_NAME}"
SHAPE_REACH = 700.0     # m: a shape whose position is further from every tube is not read (merged tiles: 384 m)
CUT_GROUPS = ("terrain_skin", "walls", "fences", "roads")    # roads: the yards meshed on the DTM over a tube
# Galleries (Switzerland Builder, 2026-11-07): swissTLM3D KUNSTBAUTE Galerie, the avalanche and rock-fall galleries of
# the Axenstrasse, the Gotthard and the San Bernardino roads, were closed tubes like the tunnels, and mound() buried
# their valley side under a bank of earth. A gallery run is now open on the valley side: a hill wall, a roof slab
# falling to the valley, pillars on a parapet and a foundation wall down to the ground; its hill side is the higher
# ground HILL_OFF m out. Where it meets a tunnel a headwall stands as at a portal.
GAL_CLEAR = ROAD_CLEARANCE + 0.3    # m under a road gallery's roof (a rail gallery: its crown - 0.3)
GAL_ROOF = 0.9          # m of roof slab over the hill wall
GAL_FALL = 0.3          # m the roof's top falls towards the valley edge
GAL_WALL = 0.8          # m, thickness of the hill wall
GAL_OVER = 0.35         # m of roof beyond the pillars
GAL_MIN = 6.0           # m: a shorter gallery run between tunnel stations stays tunnel
PILLAR_STEP = 6.0       # m between the pillars
PILLAR_W, PILLAR_D = 0.7, 0.8   # m along and across the gallery
PARAPET_H, PARAPET_T = 1.0, 0.3
HILL_OFF = (12.0, 18.0, 24.0)
FOUND_MAX = 60.0        # m, deepest a gallery's foundation wall goes under its floor
BAND_H = 3.0            # m of light wall panels over a gallery's floor (the straight walls of a tunnel)
VALLEY_CLEAR = 4.5      # m beyond a gallery's roof edge on its valley side kept down to the parapet's top
VALLEY_RISE = 6.0       # m beyond that over which the ground may rise back 1:1
END_IN, END_OUT = 1.5, 2.0   # terrain squares inside / out of a gallery's open end where the ground goes under the floor
END_SIDE = 0.5          # m beyond the walkways
END_DROP = 0.08         # m under the floor
DECK_CLEAR = -0.03      # m: ground over a road tube's floor by more than this (under the deck: walkways) is in the way
ROOF_FILL_EPS = 0.02    # m: the cap over a gallery's roof stands this much over the roof's top where the fill ends
GAL_PLAN_MARGIN = 0.3   # m beyond a gallery's footprint where the skin and the walls are taken out whatever their height
GAL_PLAN_DOWN = 3.0     # m under the floor: walls further down (under the foundation) stay
GAL_LIGHT_STEP = 30.0
RAIL_LIGHT_STEP = 40.0
PORTAL_ZONE = 60.0      # m inside a live portal with lights twice as dense (the eye's adaptation zone)
# road tunnels: what a driver sees in a Swiss one (SIA 197/2, ASTRA 13001)
SIGN_STEP = 50.0        # m between the lit escape signs on each wall (distance to the next way out either way)
SOS_STEP = 150.0        # m between the SOS niches, on the two sides in turn
EXIT_STEP, EXIT_MIN = 300.0, 600.0   # m between the emergency exits of a tunnel run at least EXIT_MIN long
FAN_STEP, FAN_MIN = 150.0, 400.0     # m between the jet fan pairs of a road tunnel run at least FAN_MIN long
FAN_R, FAN_L, FAN_CW = 0.45, 3.6, 6.0  # m: fan radius and length; only in a carriageway this wide
PAINT_W, PAINT_IN, PAINT_Z = 0.15, 0.2, 0.01   # m: line width, inside the carriageway's edge, over the asphalt
LANE_DASH = (6.0, 12.0)  # m, dash and gap of a lane line (Swiss motorways, SSV 6.02)
CAT_STEP = 25.0         # m between the supports of a rail tunnel's catenary
EDGE_MARGIN = 30.0      # m: a tube is cut where it comes this close to the terrain's edge, and closed
BOX_UV = ("mp_tunnel_wall", "mp_tunnel_band", "mp_tunnel_portal", "mp_tunnel_walk", "mp_tunnel_niche", "mp_tunnel_door")
# no collision: the paint (1 cm over the asphalt, a step for the wheels), the lamps, the wires, the fans, the signs
DECOR = ("mp_tunnel_paint", "mp_tunnel_lamp", "mp_tunnel_wire", "mp_tunnel_steel", "mp_tunnel_fan", "mp_tunnel_fan_dark",
         "mp_tunnel_signs")


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


def chain(found):
    """[(kind, props, Q, joined [start, end], group)]: the lines of one tunnel joined end to end. A line's props get
    "_CW" (carriageway) when two lanes of a portal were made one; joined says which ends meet another tunnel line
    (no portal there), group numbers the lines that meet (a group is built if any of its lines has a live portal)."""
    out = []
    for kind in ("road", "rail"):
        L = [[props, np.asarray(Q, np.float64)] for k, props, Q in found if k == kind and len(Q) >= 2]
        if not L:
            continue
        nodes = []                                  # node of each end, by clustering the ends within JOIN

        def node_of(p):
            for k, q in enumerate(nodes):
                if np.hypot(*(q - p)) < JOIN:
                    return k
            nodes.append(np.asarray(p[:2], np.float64))
            return len(nodes) - 1
        E = [[node_of(Q[0, :2]), node_of(Q[-1, :2])] for _, Q in L]
        alive = [True] * len(L)

        def at(k):
            return [(j, e) for j in range(len(L)) if alive[j] for e in (0, 1) if E[j][e] == k]

        def length(Q):
            return float(np.linalg.norm(np.diff(Q[:, :2], axis=0), axis=1).sum())

        def away(j, e):                             # the line's points from the node out
            return L[j][1] if e == 0 else L[j][1][::-1]
        # two short lanes of one portal: one piece down their middle, as wide as both
        if kind == "road":
            for k in range(len(nodes)):
                ls = [(j, e) for j, e in at(k) if length(L[j][1]) <= BRANCH_MAX and len(at(E[j][1 - e])) == 1]
                done = False
                for a in range(len(ls)):
                    for b in range(a + 1, len(ls)):
                        (ja, ea), (jb, eb) = ls[a], ls[b]
                        A, B = away(ja, ea), away(jb, eb)
                        span = float(np.hypot(*(A[-1, :2] - B[-1, :2])))
                        if done or span > PORTAL_SPAN or ja == jb:
                            continue
                        t = np.linspace(0, 1, 12)

                        def res(Q):
                            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q[:, :2], axis=0), axis=1))]
                            return np.column_stack([np.interp(t * d[-1], d, Q[:, c]) for c in range(3)])
                        M = (res(A) + res(B)) / 2
                        props = dict(L[ja][0] if length(A) >= length(B) else L[jb][0])
                        cw = max(CARRIAGEWAY.get(L[ja][0].get("OBJEKTART", ""), 4.6),
                                 CARRIAGEWAY.get(L[jb][0].get("OBJEKTART", ""), 4.6))
                        props["_CW"] = cw + span
                        props["_TWOWAY"] = True          # an Einfahrt and an Ausfahrt: both directions
                        props["OBJEKTART"] = props.get("OBJEKTART", "")
                        L[ja] = [props, M]
                        E[ja] = [k, node_of(M[-1, :2])]
                        alive[jb] = False
                        done = True
        # groups and joints are those of the lines before chaining: lines meeting at a node
        deg = [len(at(k)) for k in range(len(nodes))]
        parent = list(range(len(L)))

        def find(j):
            while parent[j] != j:
                parent[j] = parent[parent[j]]
                j = parent[j]
            return j
        for k in range(len(nodes)):
            here = [j for j, _ in at(k)]
            for j in here[1:]:
                parent[find(j)] = find(here[0])
        # chaining: at a node of two lines, or the straightest pair of a node of more
        changed = True
        while changed:
            changed = False
            for k in range(len(nodes)):
                here = at(k)
                if len(here) < 2:
                    continue
                best = None
                for a in range(len(here)):
                    for b in range(a + 1, len(here)):
                        (ja, ea), (jb, eb) = here[a], here[b]
                        if ja == jb:
                            continue
                        A, B = away(ja, ea), away(jb, eb)
                        da = A[min(3, len(A) - 1), :2] - A[0, :2]
                        db = B[min(3, len(B) - 1), :2] - B[0, :2]
                        c = -float(da @ db) / max(np.linalg.norm(da) * np.linalg.norm(db), 1e-9)
                        turn = math.degrees(math.acos(np.clip(c, -1, 1)))
                        if (len(here) == 2 or turn < CHAIN_TURN) and (best is None or turn < best[0]):
                            best = (turn, ja, ea, jb, eb)
                if best is None:
                    continue
                _, ja, ea, jb, eb = best
                A, B = away(ja, ea), away(jb, eb)
                Q = np.vstack([A[::-1], B[1:]])            # from A's far end through the node to B's far end
                pa, pb = L[ja][0], L[jb][0]
                props = dict(pa if length(A) >= length(B) else pb)
                props["NAME"] = pa.get("NAME") or pb.get("NAME") or ""
                cws = [p.get("_CW", CARRIAGEWAY.get(p.get("OBJEKTART", ""), 4.6)) for p in (pa, pb)]
                if kind == "road":
                    props["_CW"] = max(cws)
                    if pa.get("_TWOWAY") or pb.get("_TWOWAY"):
                        props["_TWOWAY"] = True
                L[ja] = [props, Q]
                E[ja] = [E[ja][1 - ea], E[jb][1 - eb]]
                alive[jb] = False
                changed = True
        base = len(out) and max(o[4] for o in out) + 1 or 0
        for j in range(len(L)):
            if alive[j]:
                jn = [deg[E[j][e]] > 1 for e in (0, 1)]
                out.append((kind, L[j][0], L[j][1], jn, base + find(j)))
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

    def inside_xy(self, x, y, margin=0.0):
        """Points (arrays) at least margin m inside the terrain's edge."""
        c, r, g = (np.asarray(x) - self.x0) / self.sq, (np.asarray(y) - self.y0) / self.sq, margin / self.sq
        return (c >= g) & (c <= self.n - 1 - g) & (r >= g) & (r <= self.n - 1 - g)

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
    def __init__(self, kind, props, Q, joined=(False, False), group=None):
        self.kind, self.props = kind, props
        self.joined, self.group = list(joined), group
        art = props.get("OBJEKTART", "")
        if kind == "road":
            self.cw = float(props.get("_CW", CARRIAGEWAY.get(art, 4.6)))
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
        self.head_w = [{1: None, -1: None}, {1: None, -1: None}]   # per end, per side: headwall width (twin_heads)
        # the floor: the carriageway (road) or the top of the ballast (rail: swissTLM3D gives the rails)
        import railway
        self.rail_drop = 0.0 if kind == "road" else railway.RAIL_H + railway.SLEEPER_H
        self.floor = P[:, 2] - self.rail_drop
        # galleries (set_gallery, hill_sides), ends closed (clip_to), travel (travel_dir)
        self.gclear = GAL_CLEAR if kind == "road" else self.crown - 0.3
        self.gal = np.zeros(len(s), bool)
        self.ms = np.zeros(len(s), int)
        self.closed = [False, False]
        self.oneway, self.lanes, self.electric = 0, 1, False
        self._limits()

    # ---- galleries and the ends
    def _limits(self):
        """Half width of the footprint on the left (n > 0) and the right of every station: the shell of a tunnel,
        a gallery's hill wall on its hill side and its roof's edge on the valley side."""
        hill, valley = self.hw + GAL_WALL, self.hw + PILLAR_D + GAL_OVER
        self.wl = np.where(self.gal, np.where(self.ms > 0, hill, valley), self.hw_out)
        self.wr = np.where(self.gal, np.where(self.ms > 0, valley, hill), self.hw_out)

    def set_gallery(self, flags):
        """Gallery stations (swissTLM3D Galerie); a gallery run shorter than GAL_MIN stays tunnel."""
        gal = np.asarray(flags, bool).copy()
        for a, b in true_runs(gal):
            if self.s[b] - self.s[a] < GAL_MIN:
                gal[a:b + 1] = False
        self.gal = gal
        self._limits()

    def hill_sides(self, ter):
        """The hill side of every gallery run (+1 left, -1 right): the higher ground HILL_OFF m out of its walls."""
        self.ms = np.zeros(len(self.s), int)
        for a, b in true_runs(self.gal):
            k = np.arange(a, b + 1)
            d = 0.0
            if ter is not None:
                for o in HILL_OFF:
                    for sg in (1, -1):
                        q = self.P[k, :2] + self.N[k] * sg * (self.hw + o)
                        d += sg * float(np.mean(ter.sample(q[:, 0], q[:, 1])))
            self.ms[k] = 1 if d >= 0 else -1
        self._limits()

    def within(self, n, i, margin=0.0):
        """Points at n across of station i inside the footprint (+ margin)."""
        n = np.asarray(n, np.float64)
        return np.abs(n) <= np.where(n >= 0, self.wl[i], self.wr[i]) + margin

    def top(self, i, n):
        """Height over the floor of the top of the tube at n across (clamped in): its shell, a gallery's roof."""
        n = np.asarray(n, np.float64)
        t = self.extrados(np.minimum(np.abs(n), self.hw_out))
        g = self.gal[i]
        if np.any(g):
            hill = self.hw + GAL_WALL
            u = np.clip((hill - self.ms[i] * n) / (hill + self.hw + PILLAR_D + GAL_OVER), 0, 1)
            t = np.where(g, self.gclear + GAL_ROOF - GAL_FALL * u, t)
        return t

    def ceiling(self, i, n):
        """Height over the floor of the clear space at n across: the vault, a gallery's roof."""
        a = np.minimum(np.abs(np.asarray(n, np.float64)), self.hw)
        v = self.wall + (self.crown - self.wall) * np.sqrt(np.maximum(1 - (a / self.hw) ** 2, 0))
        return np.where(self.gal[i], self.gclear, v)

    def valley_cap(self, i, v):
        """Highest the ground may stand over the floor at v m across towards the valley side of gallery station(s) i:
        under the parapet's top from the carriageway's edge to VALLEY_CLEAR m beyond the roof's edge, then 1:1 up
        (inf where there is no limit: tunnel stations, the hill side, further out)."""
        v = np.asarray(v, np.float64)
        edge = self.hw + PILLAR_D + GAL_OVER
        cap = PARAPET_H - 0.1 + np.maximum(v - edge - VALLEY_CLEAR, 0.0)
        on = self.gal[i] & (self.ms[i] != 0) & (v > self.hw) & (v < edge + VALLEY_CLEAR + VALLEY_RISE)
        return np.where(on, cap, np.inf)

    def extend(self, ext):
        """A station ext[0] m before the first and ext[1] m after the last, every per-station array with them."""
        P = self.P
        pre = P[0] - np.r_[self.T[0] * ext[0], 0]
        post = P[-1] + np.r_[self.T[-1] * ext[1], 0]
        self.P = np.vstack([pre, P, post])
        self.s = np.r_[self.s[0] - ext[0], self.s, self.s[-1] + ext[1]]
        for k in ("T", "N"):
            a = getattr(self, k)
            setattr(self, k, np.vstack([a[0], a, a[-1]]))
        for k in ("floor", "gal", "ms", "wl", "wr"):
            a = getattr(self, k)
            setattr(self, k, np.r_[a[:1], a, a[-1:]])
        self._tree = None

    def trim(self, a, b):
        """Only the stations a..b."""
        for k in ("P", "T", "N", "floor", "gal", "ms", "wl", "wr", "s"):
            setattr(self, k, getattr(self, k)[a:b + 1])
        self.s = self.s - self.s[0]
        self.length = float(self.s[-1])
        self._tree = None

    def clip_to(self, ter, margin=None):
        """Where the tube comes within margin of the terrain's edge (the San Bernardino tunnel runs 4.5 km on beyond
        the terrain of its zone) it is cut, seen from its live (or joined) end, and the cut end closed: beyond the
        terrain there is nothing to drive out onto. An end that joins nothing is closed too. False: nothing left."""
        margin = EDGE_MARGIN if margin is None else margin
        ins = ter.inside_xy(self.P[:, 0], self.P[:, 1], margin)
        if not ins.all():
            anchor = next((e for e in (0, 1) if self.live[e] or self.joined[e]), None)
            if anchor is None or not ins[0 if anchor == 0 else -1]:
                return False
            if anchor == 0:
                j = int(np.argmin(ins)) - 1
                if j < 2:
                    return False
                self.trim(0, j)
                cut = 1
            else:
                j = len(ins) - int(np.argmin(ins[::-1]))
                if len(ins) - j < 3:
                    return False
                self.trim(j, len(ins) - 1)
                cut = 0
            self.live[cut] = self.joined[cut] = False
        self.closed = [not (self.live[e] or self.joined[e]) for e in (0, 1)]
        return True

    def frames(self, idx, NZ):
        """Level coordinates (k, 3) of (n across, z over the floor) NZ (k, 2) at stations idx (k,)."""
        idx = np.asarray(idx)
        return np.column_stack([self.P[idx, :2] + self.N[idx] * NZ[:, :1], self.floor[idx] + NZ[:, 1]])

    def at(self, s):
        """Station index and the point (2,) on the axis at s along."""
        i = int(np.clip(np.searchsorted(self.s, s), 0, len(self.s) - 1))
        if i > 0 and abs(self.s[i - 1] - s) < abs(self.s[i] - s):
            i -= 1
        return i, self.P[i, :2] + self.T[i] * (s - self.s[i])

    def join(self, tops):
        """Live portals: the line moved to the mesh it joins there, the change faded over FADE m."""
        dz = np.zeros(len(self.s))
        for e, (i, sgn) in enumerate(((0, -1), (len(self.s) - 1, 1))):
            if self.joined[e]:                  # another tunnel line goes on there: no portal
                continue
            p, t = self.P[i], self.T[i] * sgn
            zs = []
            # beside the axis too: the two lanes of a portal made one piece (chain) may have an island between them
            nrm = np.r_[-t[1], t[0]]
            for back in (1.5, 3.0, 4.5, 6.0):
                for off in (0.0, self.cw / 4, -self.cw / 4):
                    q = p[:2] + t * back + nrm * off
                    z = tops.height(q[0], q[1], self.kind, p[2])
                    if np.isfinite(z):
                        zs.append(z)
                        break
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
def build_tube(tb, mats=None, ter=None, atlas=None):
    """({material: triangles}, {sign material: (triangles, uvs)}) of the tube: its tunnel runs (straight walls, vault,
    the shell where it can be seen), its gallery runs (gallery()), the deck and its paint, the portals and the headwalls
    where a gallery meets a tunnel, the end walls of closed ends, and in a road tunnel its equipment (equipment())."""
    out, signs = {}, {}

    def add(m, T):
        if len(T):
            out.setdefault(m, []).append(np.asarray(T, np.float64).reshape(-1, 3, 3))

    def add_sign(m, T, UV):
        signs.setdefault(m, []).append((T, UV))
    # a live tunnel portal stands PORTAL_OUT + HEAD out of the swissTLM3D end; a joined end (another tunnel line goes
    # on), a closed end and the end of a gallery are no portal: a token station there
    headed = [bool(tb.live[e] and not tb.gal[0 if e == 0 else -1]) for e in (0, 1)]
    tb.extend([PORTAL_OUT + HEAD if headed[e] else 0.1 for e in (0, 1)])
    m = len(tb.s)
    i0, i1 = 1, m - 2
    gseg = tb.gal[:-1] | tb.gal[1:]                 # segment k (stations k and k + 1) belongs to a gallery
    truns, gruns = seg_runs(~gseg), seg_runs(gseg)
    # a headwall where a gallery meets a tunnel: on the tunnel's station at the joint, its face to the gallery
    trans = []
    for a, b in gruns:
        if a > 0 and not tb.gal[a]:
            trans.append((a, -1))
        if b < m - 1 and not tb.gal[b]:
            trans.append((b, 1))
    ring = tb.ring()
    for a, b in truns:
        add("mp_tunnel_band", tb.sweep(ring[:2], a, b, False))         # the straight walls, their faces in
        add("mp_tunnel_wall", tb.sweep(ring[1:-1], a, b, False))       # the vault
        add("mp_tunnel_band", tb.sweep(ring[-2:], a, b, False))
    # the outer shell near the ends and the joints with galleries, and where the cover is thin
    outer = np.column_stack([ring[1:-1, 0] * tb.hw_out / tb.hw,
                             tb.wall + (ring[1:-1, 1] - tb.wall) * (tb.crown + SHELL - tb.wall) / (tb.crown - tb.wall)])
    outer[0, 1] = outer[-1, 1] = tb.wall
    outer = np.vstack([[tb.hw_out, -0.6], outer, [-tb.hw_out, -0.6]])
    show = np.zeros(m, bool)
    if ter is not None:                    # thin cover: holes in the ground over the tube, the shell must close them
        for o in (-tb.hw_out, 0.0, tb.hw_out):
            g = ter.sample(tb.P[:, 0] + tb.N[:, 0] * o, tb.P[:, 1] + tb.N[:, 1] * o)
            show |= g < tb.floor + np.nan_to_num(tb.extrados(abs(o) * 0.999), nan=tb.wall) + COVER_THIN
        show = np.convolve(show, np.ones(5), "same") > 0
    for e in (0, 1):
        if not tb.joined[e]:
            show |= np.abs(tb.s - tb.s[0 if e == 0 else -1]) <= SHELL_NEAR
    for t, _ in trans:
        show |= np.abs(tb.s - tb.s[t]) <= SHELL_NEAR
    for a, b in truns:
        idx = np.where(show[a:b + 1])[0] + a
        if len(idx):
            for p, q in runs(idx):
                add("mp_tunnel_wall", tb.sweep(outer, p, q, True))     # turned: its faces out
    # the deck: inside the tube only (the road or track of the level runs up to the swissTLM3D portal)
    if tb.kind == "road":
        c = tb.cw / 2
        add("mp_road_asphalt", up(tb.sweep([(c, 0.0), (-c, 0.0)], i0, i1, False)))
        for sg in (1, -1):
            add("mp_tunnel_walk", up(tb.sweep([(sg * tb.hw, KERB), (sg * c, KERB)], i0, i1, False)))
            add("mp_tunnel_walk", ribbon(tb, i0, i1, const(m, sg * c, 0.0), const(m, sg * c, KERB), -sg, 0))
        paint(tb, i0, i1, add)
    else:
        add_track(tb, add, i0, i1)
        if tb.electric:
            catenary_wires(tb, i0, i1, add)
    # a floor under each portal's headwall and up to the swissTLM3D portal, 3 cm under the level's own track or road
    # there: the holes reach out to the headwall's face and one saw through them past the ballast (the lake under it)
    floor_mat = "mp_ballast" if tb.kind != "road" else "mp_road_asphalt"
    for e, (a, b) in enumerate(((0, i0), (i1, m - 1))):
        if headed[e]:
            add(floor_mat, up(tb.sweep([(tb.hw, -0.03), (-tb.hw, -0.03)], a, b, False)))
    # an apron APRON m out in front of each face, as wide as the headwall: the hole squares straddle the face and
    # beside the level's narrower track bed one saw the lake through them at the jamb feet (laptop run 7)
    W = tb.hw_out + HEAD_W
    for e, (st, way) in enumerate(((0, -1), (m - 1, 1))):
        if not headed[e]:
            continue
        d = np.r_[tb.T[st] * way * APRON, 0.0]
        a0, a1 = tb.frame(st, W, -0.03), tb.frame(st, -W, -0.03)
        add(floor_mat, up(np.array([[a0, a1, a1 + d], [a0, a1 + d, a0 + d]])))
        if ter is None:
            continue
        # its open edges go down FOOT under the lowest ground beside them, as the headwall's sides do: on the lake
        # side of the S portal the apron stood as a plate 1-1.5 m over the slope (laptop run 8)
        for p, q in ((a0, a0 + d), (a0 + d, a1 + d), (a1 + d, a1)):
            t = np.linspace(0, 1, 6)[:, None]
            Lq = p[:2] + (q[:2] - p[:2]) * t
            g = float(np.min(ter.sample(Lq[:, 0], Lq[:, 1])))
            if g < min(p[2], q[2]) - 0.1:
                z = g - FOOT
                p2, q2 = np.r_[p[:2], z], np.r_[q[:2], z]
                quad = np.array([[p, q, q2], [p, q2, p2]])
                add("mp_tunnel_portal", np.concatenate([quad, quad[:, ::-1]]))
    # lamp strips along both sides of the vault of the tunnel runs
    ang = math.radians(55)
    for a, b in truns:
        for sg in (1, -1):
            n0 = sg * tb.hw * math.cos(ang)
            z0 = tb.wall + (tb.crown - tb.wall) * math.sin(ang) - 0.06
            add("mp_tunnel_lamp", tb.orient(tb.sweep([(n0 + 0.12, z0), (n0 - 0.12, z0)], max(a, i0), min(b, i1), False), 0, True))
    # the gallery runs; their free ends (a portal, a closed end) get end faces, a joint with a tunnel the headwall
    for a, b in gruns:
        gallery(tb, a, b, ter, add, (a == 0 and not tb.joined[0], b == m - 1 and not tb.joined[1]))
    # headwalls at the live tunnel portals and at the joints of a gallery and a tunnel
    for e in (0, 1):
        if headed[e]:
            add("mp_tunnel_portal", headwall(tb, 0 if e == 0 else m - 1, 1 if e == 0 else -1, ter, tb.head_w[e]))
    for t, inward in trans:
        if 0 <= t + inward < m:
            add("mp_tunnel_portal", headwall(tb, t, inward, ter, None))
    for e in (0, 1):
        if tb.closed[e]:
            end_wall(tb, e, add)
    if atlas is not None:
        if tb.kind == "road":
            equipment(tb, truns, trans, headed, add, add_sign, atlas)
        for e in (0, 1):
            if headed[e]:
                name_plate(tb, e, add_sign, atlas)
    parts = {k: np.concatenate(v) for k, v in out.items()}
    sign_parts = {k: (np.concatenate([t for t, _ in v]), np.concatenate([u for _, u in v])) for k, v in signs.items()}
    return parts, sign_parts


def gallery(tb, a, b, ter, add, free):
    """The faces of a gallery run (stations a..b): the hill wall (its light band inside, its back down to the ground),
    the roof slab (underside, top falling to the valley, fascia), and on the valley side a parapet with a ledge, the
    foundation wall down FOOT under the ground (at most FOUND_MAX) and the pillars from the parapet to the roof; a lamp
    strip under the roof on the hill wall. free (start, end): the run ends at a portal or a closed end there, and its
    cross-section is closed by end faces (at a joint with a tunnel the headwall closes it)."""
    m = len(tb.s)
    ms = int(np.sign(tb.ms[a:b + 1][tb.gal[a:b + 1]].sum())) or 1
    h = tb.hw
    nh_in, nh_out = ms * h, ms * (h + GAL_WALL)
    nv_in, nv_par, nv_out = -ms * h, -ms * (h + PARAPET_T), -ms * (h + PILLAR_D)
    nv_edge = -ms * (h + PILLAR_D + GAL_OVER)
    zc = tb.gclear
    zt_h, zt_v = zc + GAL_ROOF, zc + GAL_ROOF - GAL_FALL
    zw = KERB if tb.kind == "road" else 0.0
    bot_h, bot_v = np.full(m, -0.6), np.full(m, -0.6)
    if ter is not None:
        k = np.arange(a, b + 1)
        for arr, n0, step in ((bot_h, nh_out, ms), (bot_v, nv_out, -ms)):
            g = np.minimum.reduce([ter.sample(*(tb.P[k, :2] + tb.N[k] * (n0 + step * o)).T) for o in (0.0, 0.5, 1.5)])
            arr[k] = np.clip(g - tb.floor[k] - FOOT, -FOUND_MAX, -0.6)

    def R(A, B, dn, dz, mat):
        add(mat, ribbon(tb, a, b, A, B, dn, dz))
    C = lambda n, z: const(m, n, z)
    # the hill wall: inside, the band and the wall over it; its back towards the hill, down to the ground
    R(C(nh_in, zw), C(nh_in, min(BAND_H, zc)), -ms, 0, "mp_tunnel_band")
    if zc > BAND_H:
        R(C(nh_in, BAND_H), C(nh_in, zc), -ms, 0, "mp_tunnel_wall")
    R(np.column_stack([np.full(m, nh_out), bot_h]), C(nh_out, zt_h), ms, 0, "mp_tunnel_portal")
    # the roof: underside from the hill wall to the edge, top falling to the valley, fascia
    R(C(nh_in, zc), C(nv_edge, zc), 0, -1, "mp_tunnel_wall")
    R(C(nh_out, zt_h), C(nv_edge, zt_v), 0, 1, "mp_tunnel_portal")
    R(C(nv_edge, zc), C(nv_edge, zt_v), -ms, 0, "mp_tunnel_portal")
    # the valley side: parapet (inside, top, outside), the ledge in front of it, the foundation wall
    R(C(nv_in, zw), C(nv_in, PARAPET_H), ms, 0, "mp_tunnel_portal")
    R(C(nv_in, PARAPET_H), C(nv_par, PARAPET_H), 0, 1, "mp_tunnel_portal")
    R(C(nv_par, 0.0), C(nv_par, PARAPET_H), -ms, 0, "mp_tunnel_portal")
    R(C(nv_par, 0.0), C(nv_out, 0.0), 0, 1, "mp_tunnel_portal")
    R(np.column_stack([np.full(m, nv_out), bot_v]), C(nv_out, 0.0), -ms, 0, "mp_tunnel_portal")
    # the lamp strip under the roof
    R(C(nh_in - ms * 0.02, zc - 0.35), C(nh_in - ms * 0.02, zc - 0.15), -ms, 0, "mp_tunnel_lamp")
    # the pillars, from the parapet up to the roof, at both ends of the run and every PILLAR_STEP between
    s0, s1 = tb.s[a], tb.s[b]
    count = max(1, int(round((s1 - s0) / PILLAR_STEP)))
    for sp in np.linspace(s0 + PILLAR_W / 2, s1 - PILLAR_W / 2, count + 1):
        i, c = tb.at(sp)
        cc = c + tb.N[i] * (-ms * (h + PILLAR_D / 2))
        add("mp_tunnel_portal", prism(cc, tb.T[i], tb.N[i], PILLAR_W / 2, PILLAR_D / 2 + 0.03, tb.floor[i] + 0.0,
                                      tb.floor[i] + zc))
    # the end faces of a free end
    for e, st, way in ((0, a, -1), (1, b, 1)):
        if not free[e]:
            continue
        d = np.r_[tb.T[st] * way, 0.0]
        lo = min(bot_h[st], bot_v[st])
        quads = [((nh_in, bot_h[st]), (nh_out, bot_h[st]), (nh_out, zc), (nh_in, zc)),          # the hill wall
                 ((nv_edge, zc), (nh_out, zc), (nh_out, zt_h), (nv_edge, zt_v)),               # the roof
                 ((nv_in, bot_v[st]), (nv_out, bot_v[st]), (nv_out, 0.0), (nv_in, 0.0)),       # the foundation
                 ((nv_in, 0.0), (nv_par, 0.0), (nv_par, PARAPET_H), (nv_in, PARAPET_H)),        # the parapet
                 ((nv_in, lo), (nh_in, lo), (nh_in, 0.0), (nv_in, 0.0))]                       # under the deck
        for q in quads:
            p = [tb.frame(st, n, z) for n, z in q]
            add("mp_tunnel_portal", facing(np.array([[p[0], p[1], p[2]], [p[0], p[2], p[3]]]), d))
        if tb.closed[e]:                        # a closed end: a wall across the clear space, seen from inside
            p = [tb.frame(st, n, z) for n, z in ((nv_out, 0.0), (nh_in, 0.0), (nh_in, zc), (nv_out, zc))]
            add("mp_tunnel_wall", facing(np.array([[p[0], p[1], p[2]], [p[0], p[2], p[3]]]), -d))


def vault_normals(tb, T, flat):
    """Normals (k * 3, 3) of the triangles T (k, 3, 3) of a tube's vault and shell bent to the vault's curve at every
    corner (one per triangle drew the 12 facets of the vault as bands of light and shade); the other faces (walls,
    headwalls, galleries) keep their flat ones."""
    if not len(T):
        return flat
    V = T.reshape(-1, 3)
    s, n, i = tb.local(V[:, :2])
    zr = V[:, 2] - tb.floor[i] - tb.wall
    inner = (n / tb.hw) ** 2 + (np.maximum(zr, 0) / (tb.crown - tb.wall)) ** 2 < 1.1
    a = np.where(inner, tb.hw, tb.hw_out)
    b = np.where(inner, tb.crown - tb.wall, tb.crown + SHELL - tb.wall)
    rn, rz = n / a ** 2, np.maximum(zr, 0) / b ** 2
    R = np.column_stack([tb.N[i] * rn[:, None], rz])
    R /= np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)
    F = flat.reshape(-1, 3, 3)[:, 0]
    Rk = R.reshape(-1, 3, 3)
    d = np.einsum("kj,kcj->kc", F, Rk)               # flat normal against the radial of every corner
    curved = (np.abs(d).min(1) > 0.85) & ~tb.gal[i.reshape(-1, 3)].any(1) & (zr.reshape(-1, 3) > -0.01).all(1)
    out = flat.reshape(-1, 3, 3).copy()
    sg = np.sign(d.mean(1))[:, None, None]
    out[curved] = (Rk * sg)[curved]
    return out.reshape(-1, 3)


def end_wall(tb, e, add):
    """A wall closing a tunnel's end (the tube cut at the terrain's edge, or an end that joins nothing), seen from
    inside; a gallery's closed end is closed by gallery()."""
    st = 0 if e == 0 else len(tb.s) - 1
    if tb.gal[st]:
        return
    ring = tb.ring()
    c = tb.frame(st, 0.0, tb.wall)
    pts = [tb.frame(st, n, z) for n, z in ring]
    T = np.array([[c, pts[k], pts[k + 1]] for k in range(len(pts) - 1)] + [[c, pts[-1], pts[0]]])
    add("mp_tunnel_wall", facing(T, np.r_[tb.T[st] * (1 if e == 0 else -1), 0.0]))


def paint(tb, i0, i1, add):
    """The road paint of a road tube: solid edge lines, a solid centre line when both ways, the dashed lane lines of
    a one-way tube of two lanes (Swiss motorway, 6 m dashes and 12 m gaps)."""
    e = tb.cw / 2 - PAINT_IN - PAINT_W / 2
    if e < 1.0:
        return
    lines = [(e, None), (-e, None)]
    if not tb.oneway:
        lines.append((0.0, None))
    else:
        for k in range(1, tb.lanes):
            lines.append((-e + 2 * e * k / tb.lanes, LANE_DASH))
    for n0, dash in lines:
        out = [(n0 - PAINT_W / 2, PAINT_Z), (n0 + PAINT_W / 2, PAINT_Z)]
        if dash is None:
            add("mp_tunnel_paint", up(tb.sweep(out, i0, i1, False)))
            continue
        L_, G_ = dash
        for s0 in np.arange(tb.s[i0] + G_ / 2, tb.s[i1] - L_, L_ + G_):
            j0 = int(np.searchsorted(tb.s, s0))
            j1 = int(np.searchsorted(tb.s, s0 + L_))
            if j1 > j0:
                add("mp_tunnel_paint", up(tb.sweep(out, j0, j1, False)))


def catenary_wires(tb, i0, i1, add):
    """The catenary through a rail tube of an electrified line: a contact wire zig-zagging STAGGER m about the axis,
    the messenger over it with droppers, and a support from the vault every CAT_STEP m."""
    import railway as rw
    over = tb.rail_drop                                  # the rails' top over the floor (the ballast)
    zc = over + min(rw.CONTACT, tb.crown - over - 0.8)
    zm = min(zc + 0.45, tb.crown - 0.3)
    sup = np.arange(tb.s[i0] + 3.0, tb.s[i1] - 2.0, CAT_STEP)
    if len(sup) < 2:
        return
    sup = np.r_[sup, tb.s[i1] - 1.0]
    cw, mw, rods = [], [], []
    for k, (sa, sb) in enumerate(zip(sup[:-1], sup[1:])):
        for f in np.linspace(0, 1, max(2, int((sb - sa) / 3)) + 1)[:-1]:
            s = sa + f * (sb - sa)
            i, c = tb.at(s)
            st = rw.STAGGER * (1 - 2 * f) * (1 if k % 2 == 0 else -1)
            cw.append(np.r_[c + tb.N[i] * st, tb.floor[i] + zc])
            mw.append(np.r_[c, tb.floor[i] + zm])
    i, c = tb.at(sup[-1])
    st = rw.STAGGER * (-1 if (len(sup) - 2) % 2 == 0 else 1)
    cw.append(np.r_[c + tb.N[i] * st, tb.floor[i] + zc])
    mw.append(np.r_[c, tb.floor[i] + zm])
    cw, mw = np.array(cw), np.array(mw)
    add("mp_tunnel_wire", rw.polyline_tube(cw))
    add("mp_tunnel_wire", rw.polyline_tube(mw))
    for j in range(1, len(cw) - 1, 3):
        add("mp_tunnel_wire", rw.tube(cw[j], mw[j], rw.WIRE_R * 0.6, 4))
    for s in sup:
        i, c = tb.at(s)
        top = tb.floor[i] + float(tb.ceiling(i, 0.0)) - 0.02           # the vault, a gallery's roof
        k = int(np.argmin(np.linalg.norm(mw[:, :2] - c, axis=1)))
        rods.append(rw.tube(np.r_[c, top], np.r_[c, tb.floor[i] + zm - 0.05], 0.04, 6))
        rods.append(rw.tube(np.r_[c, tb.floor[i] + zm - 0.05], cw[k] + np.r_[0, 0, 0.05], 0.025, 6))
    add("mp_tunnel_steel", np.concatenate(rods))


def equipment(tb, truns, trans, headed, add, add_sign, atlas):
    """What a road tunnel run holds: SOS niches every SOS_STEP m on its two sides in turn (an orange cabinet, a lit SOS
    sign over it), emergency exits every EXIT_STEP m in a run of EXIT_MIN m or more (a green door, a lit sign), lit
    escape signs every SIGN_STEP m on both walls with the distance to the way out either way (a portal, a gallery, an
    exit), jet fan pairs under the vault every FAN_STEP m in a run of FAN_MIN m or more."""
    m = len(tb.s)
    opens = [tb.s[0 if e == 0 else -1] for e in (0, 1) if tb.live[e]] + [tb.s[t] for t, _ in trans]
    plan = []                                       # (s, kind, side)
    for a, b in truns:
        sa, sb = tb.s[max(a, 1)], tb.s[min(b, m - 2)]
        if sb - sa >= EXIT_MIN:
            for k, s in enumerate(np.arange(sa + EXIT_STEP, sb - EXIT_STEP / 2, EXIT_STEP)):
                plan.append((s, "exit", 1))
                opens.append(s)
        for k, s in enumerate(np.arange(sa + SOS_STEP / 2, sb - 30.0, SOS_STEP)):
            plan.append((s, "sos", 1 if k % 2 else -1))
        busy = [s for s, _, _ in plan]
        for s in np.arange(sa + SIGN_STEP / 2, sb - 10.0, SIGN_STEP):
            if all(abs(s - q) > 4.0 for q in busy):
                plan.append((s, "sign", 1))
                plan.append((s, "sign", -1))
        if sb - sa >= FAN_MIN and tb.cw >= FAN_CW:
            for s in np.arange(sa + 100.0, sb - 100.0, FAN_STEP):
                plan.append((s, "fan", 0))
    opens = np.array(sorted(opens))
    count = {"sos": 0, "exit": 0, "sign": 0, "fan": 0}
    for s, kind, sg in plan:
        i, c = tb.at(s)
        w = c + tb.N[i] * sg * tb.hw                 # on the wall
        nrm = -sg * tb.N[i]                         # facing into the tube
        z = tb.floor[i]
        if kind == "sos":
            add("mp_tunnel_niche", prism(w + nrm * 0.08, tb.T[i], nrm, 0.8, 0.08, z + KERB, z + 2.15))
            mat, uv = atlas.uv(("sos",), 1, draw_sos)
            add_sign(mat, *plate(w, nrm, z + 2.45, 0.8, 0.2, uv))
        elif kind == "exit":
            add("mp_tunnel_door", prism(w + nrm * 0.05, tb.T[i], nrm, 0.7, 0.05, z + KERB, z + 2.2))
            mat, uv = atlas.uv(("exit",), 1, draw_exit)
            add_sign(mat, *plate(w, nrm, z + 2.5, 1.0, 0.25, uv))
        elif kind == "sign":
            back = opens[opens < s - 1.0]
            fwd = opens[opens > s + 1.0]
            dl = int(round((s - back[-1]) / 10.0) * 10) if len(back) else None
            dr = int(round((fwd[0] - s) / 10.0) * 10) if len(fwd) else None
            # on the left wall the reader's right is along the stations, on the right wall against them
            left, right = (dl, dr) if sg > 0 else (dr, dl)
            mat, uv = atlas.uv(("esc", left, right), 1, draw_escape(left, right))
            add_sign(mat, *plate(w, nrm, z + 1.05, 1.0, 0.25, uv))
        else:
            zf = tb.crown - 0.25 - FAN_R
            for side in (1, -1):
                q = c + tb.N[i] * side * (FAN_R + 0.3)
                a3 = np.r_[q - tb.T[i] * FAN_L / 2, z + zf]
                b3 = np.r_[q + tb.T[i] * FAN_L / 2, z + zf]
                S, E = cylinder(a3, b3, FAN_R)
                add("mp_tunnel_fan", S)
                add("mp_tunnel_fan_dark", E)
                top = z + float(tb.ceiling(i, side * (FAN_R + 0.3))) + 0.05
                add("mp_tunnel_fan", prism(q, tb.T[i], tb.N[i], 0.6, 0.05, z + zf + FAN_R - 0.05, top))
        count[kind] += 1
    tb.equipment = count


def name_plate(tb, e, add_sign, atlas):
    """A blue plate with the tunnel's name and length over the opening of a live portal (swissTLM3D NAME, its first
    language; an unnamed tunnel has none)."""
    name = (tb.props.get("NAME") or "").split("|")[0].strip()
    if not name:
        return
    text = "%s  %d m" % (name, int(round(tb.length)))
    st, way = (0, -1) if e == 0 else (len(tb.s) - 1, 1)
    nrm = tb.T[st] * way
    w = min(2 * (tb.hw_out + HEAD_W) - 1.0, 6.0)
    mat, uv = atlas.uv(("name", text), 2, draw_name(text))
    c = tb.P[st, :2]
    add_sign(mat, *plate(c, nrm, tb.floor[st] + tb.crown + SHELL + 0.55, w, w / 8, uv))


def inside_inner(tb, P, margin=0.05):
    """Points (k, 3) inside the tube's clear space (walls and vault, over the floor), between its end stations."""
    s, n, i = tb.local(P[:, :2])
    z = P[:, 2] - tb.floor[i]
    return (s >= tb.s[0]) & (s <= tb.s[-1]) & (np.abs(n) < tb.hw - margin) & (z > margin) & \
        (z < tb.ceiling(i, n) - margin)


def open_junction(tb, parts, tubes):
    """Where a branch meets the tube it opens into (joined ends), the faces of either standing in the other's clear
    space go: the branch's walls across the tube's carriageway, the tube's wall across the branch's opening. A branch
    (the shorter) also loses its deck over the other's carriageway. Changes parts in place; returns the count."""
    mates = [ot for ot in tubes if ot is not tb and ot.group == tb.group]
    gone = 0
    for m in list(parts):
        T = parts[m]
        c = T.mean(1)
        drop = np.zeros(len(T), bool)
        for ot in mates:
            box = (c[:, 0] > ot.P[:, 0].min() - ot.hw_out) & (c[:, 0] < ot.P[:, 0].max() + ot.hw_out) & \
                  (c[:, 1] > ot.P[:, 1].min() - ot.hw_out) & (c[:, 1] < ot.P[:, 1].max() + ot.hw_out)
            if not box.any():
                continue
            k = np.where(box)[0]
            hit = inside_inner(ot, c[k])
            if tb.length < ot.length and m in ("mp_road_asphalt", "mp_ballast", "mp_tunnel_walk"):
                s, n, i = ot.local(c[k, :2])
                z = c[k, 2] - ot.floor[i]
                hit |= (s >= ot.s[0]) & (s <= ot.s[-1]) & (np.abs(n) < max(ot.cw / 2, ot.hw - 1.0)) & (np.abs(z) < 0.5)
            drop[k[hit]] = True
        if drop.any():
            gone += int(drop.sum())
            parts[m] = T[~drop]
            if not len(parts[m]):
                del parts[m]
    return gone


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


def true_runs(flags):
    """(first, last) index of every run of True."""
    out, k, n = [], 0, len(flags)
    while k < n:
        if flags[k]:
            j = k
            while j + 1 < n and flags[j + 1]:
                j += 1
            out.append((k, j))
            k = j + 1
        else:
            k += 1
    return out


def seg_runs(mask):
    """(first station, last station) of every run of True segments (segment k joins stations k and k + 1)."""
    return [(a, b + 1) for a, b in true_runs(mask)]


def facing(T, d):
    """Triangles (k, 3, 3) turned so that their normal (counter-clockwise, as up()) looks along d ((3,) or (k, 3))."""
    if not len(T):
        return T
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    flip = (nrm * d).sum(-1) < 0
    T = T.copy()
    T[flip] = T[flip][:, ::-1]
    return T


def ribbon(tb, i0, i1, A, B, dn, dz):
    """Triangles of the band between two lines A and B ((m, 2): (n across, z over the floor) at every station)
    from station i0 to i1, facing (dn across, dz up) in the stations' frame."""
    k = np.arange(i0, i1)
    if not len(k):
        return np.zeros((0, 3, 3))
    a0, a1, b0, b1 = tb.frames(k, A[k]), tb.frames(k + 1, A[k + 1]), tb.frames(k, B[k]), tb.frames(k + 1, B[k + 1])
    T = np.stack([a0, a1, b1, a0, b1, b0], 1).reshape(-1, 3, 3)
    d = np.column_stack([tb.N[k] * dn, np.full(len(k), float(dz))])
    return facing(T, np.repeat(d, 2, 0))


def const(m, n, z):
    return np.tile(np.array([n, z], np.float64), (m, 1))


def prism(c, t, nrm, a, b, z0, z1):
    """A closed box: centre c (2,), half a along t (2,), half b along nrm (2,), from z0 to z1; faces out."""
    q = [c - t * a - nrm * b, c + t * a - nrm * b, c + t * a + nrm * b, c - t * a + nrm * b]
    lo = [np.r_[p, z0] for p in q]
    hi = [np.r_[p, z1] for p in q]
    tris = []
    for k in range(4):
        p, r = k, (k + 1) % 4
        tris += [lo[p], lo[r], hi[r], lo[p], hi[r], hi[p]]
    tris += [hi[0], hi[1], hi[2], hi[0], hi[2], hi[3], lo[0], lo[2], lo[1], lo[0], lo[3], lo[2]]
    T = np.array(tris).reshape(-1, 3, 3)
    return facing(T, T.mean(1) - np.r_[c, (z0 + z1) / 2])


def cylinder(a, b, r, n=12):
    """Sides (faces out) and the two end discs (faces out) of a cylinder from a to b (3,)."""
    d = b - a
    d = d / max(np.linalg.norm(d), 1e-9)
    u = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.95 else np.cross(d, [1.0, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(u, d)
    ang = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    ring = r * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v)
    side, ends = [], []
    for j in range(n):
        k = (j + 1) % n
        side += [a + ring[j], b + ring[j], b + ring[k], a + ring[j], b + ring[k], a + ring[k]]
        ends += [a, a + ring[k], a + ring[j], b, b + ring[j], b + ring[k]]
    S = np.array(side).reshape(-1, 3, 3)
    E = np.array(ends).reshape(-1, 3, 3)
    axis_pt = a + np.outer(((S.mean(1) - a) @ d), d)
    S = facing(S, S.mean(1) - axis_pt)
    E = facing(E, np.outer(np.sign((E.mean(1) - (a + b) / 2) @ d), d))      # the disc at a looks back, at b on
    return S, E


def plate(c, nrm, zc, w, h, uvbox, off=0.03):
    """A sign plate centred at (c (2,), zc) facing nrm (2,): triangles (2, 3, 3) counter-clockwise seen from the
    side it faces, and their texture coordinates (2, 3, 2) of the cell uvbox (u0, v0, u1, v1: v0 at the bottom)."""
    r = np.array([-nrm[1], nrm[0]])                 # left to right for whoever faces the plate
    p = c + nrm * off
    A, B = np.r_[p - r * w / 2, zc - h / 2], np.r_[p + r * w / 2, zc - h / 2]
    C, D = np.r_[p + r * w / 2, zc + h / 2], np.r_[p - r * w / 2, zc + h / 2]
    u0, v0, u1, v1 = uvbox
    return np.array([[A, B, C], [A, C, D]]), np.array([[[u0, v0], [u1, v0], [u1, v1]], [[u0, v0], [u1, v1], [u0, v1]]])


# ------------------------------------------------------------------ lit signs
_FONTS = {}


def _font(px):
    """DejaVu Sans Bold of matplotlib (the same on every machine), else the system's, else Pillow's own."""
    from PIL import ImageFont
    if px in _FONTS:
        return _FONTS[px]
    dirs = []
    try:
        import matplotlib
        dirs.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"))
    except ImportError:
        pass
    dirs += ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "C:/Windows/Fonts"]
    f = None
    for d in dirs:
        p = os.path.join(d, "DejaVuSans-Bold.ttf")
        if os.path.exists(p):
            f = ImageFont.truetype(p, px)
            break
    _FONTS[px] = f or ImageFont.load_default(size=px)
    return _FONTS[px]


GREEN, BLUE, WHITE = (0, 122, 61), (0, 76, 151), (255, 255, 255)


class SignAtlas:
    """The lit signs of the tunnels on pages of PAGE x PAGE px in rows CELL_H high: every sign drawn once."""
    PAGE, CELL_H = 2048, 128

    def __init__(self):
        self.pages, self.cells, self.x, self.y = [], {}, 0, 0

    def uv(self, key, cells, draw):
        """(material, (u0, v0, u1, v1)) of the sign `key`, `cells` x 512 px wide, drawn by draw(image, box)."""
        if key not in self.cells:
            w = 512 * cells
            if not self.pages or self.x + w > self.PAGE:
                self.x, self.y = 0, self.y + self.CELL_H
            if not self.pages or self.y + self.CELL_H > self.PAGE:
                from PIL import Image
                self.pages.append(Image.new("RGB", (self.PAGE, self.PAGE), (40, 40, 40)))
                self.x, self.y = 0, 0
            box = (self.x, self.y, self.x + w, self.y + self.CELL_H)
            draw(self.pages[-1], box)
            self.cells[key] = (len(self.pages) - 1, box)
            self.x += w
        p, (x0, y0, x1, y1) = self.cells[key]
        S = float(self.PAGE)
        return f"mp_tunnel_signs{p}", ((x0 + 1) / S, 1 - (y1 - 1) / S, (x1 - 1) / S, 1 - (y0 + 1) / S)


def _panel(img, box, colour):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=WHITE)
    d.rectangle([x0 + 6, y0 + 6, x1 - 7, y1 - 7], fill=colour)
    return d


def _runner(d, x, y, s, flip=False):
    """A running man (ISO 7010 E001 in spirit) in a box of s px at (x, y), facing right (left when flip)."""
    def P(u, v):
        return (x + (s - u * s if flip else u * s), y + v * s)
    w = max(3, int(s * 0.09))
    d.ellipse([P(0.62, 0.02)[0] - s * 0.09, y + s * 0.02, P(0.62, 0.02)[0] + s * 0.09, y + s * 0.2], fill=WHITE)
    for a, b in (((0.55, 0.25), (0.42, 0.6)), ((0.53, 0.32), (0.78, 0.45)), ((0.53, 0.32), (0.3, 0.42)),
                 ((0.42, 0.6), (0.62, 0.78)), ((0.62, 0.78), (0.58, 0.98)), ((0.42, 0.6), (0.28, 0.8)),
                 ((0.28, 0.8), (0.08, 0.84))):
        d.line([P(*a), P(*b)], fill=WHITE, width=w)


def draw_escape(left, right):
    """Green sign: the running man in the middle, the way out either way with its distance (m; None: none that way),
    the text as large as fits beside him (54 px of a 128 px row overlapped him on the first atlas)."""
    def draw(img, box):
        d = _panel(img, box, GREEN)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        s, margin, gap = 92, 22, 10
        texts = ["\u2190 %d m" % left if left is not None else "", "%d m \u2192" % right if right is not None else ""]
        room = (x1 - x0) / 2 - s / 2 - margin - gap
        px = 54
        while px > 24 and max(d.textlength(t, font=_font(px)) for t in texts) > room:
            px -= 2
        f = _font(px)
        _runner(d, cx - s // 2, y0 + 18, s)
        if texts[0]:
            d.text((x0 + margin, cy), texts[0], font=f, fill=WHITE, anchor="lm")
        if texts[1]:
            d.text((x1 - margin, cy), texts[1], font=f, fill=WHITE, anchor="rm")
    return draw


def draw_sos(img, box):
    d = _panel(img, box, BLUE)
    x0, y0, x1, y1 = box
    d.text(((x0 + x1) // 2, (y0 + y1) // 2), "SOS", font=_font(84), fill=WHITE, anchor="mm")


def draw_exit(img, box):
    """Green sign of an emergency exit: the running man at a door."""
    d = _panel(img, box, GREEN)
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    _runner(d, cx - 120, y0 + 18, 92)
    d.rectangle([cx + 10, y0 + 20, cx + 80, y1 - 20], outline=WHITE, width=9)
    d.rectangle([cx + 42, y0 + 30, cx + 70, y1 - 30], fill=WHITE)


def draw_name(text):
    """Blue plate with the name of a tunnel in white, as large as it fits."""
    def draw(img, box):
        d = _panel(img, box, BLUE)
        x0, y0, x1, y1 = box
        px = 78
        while px > 20 and d.textlength(text, font=_font(px)) > (x1 - x0) - 60:
            px -= 4
        d.text(((x0 + x1) // 2, (y0 + y1) // 2), text, font=_font(px), fill=WHITE, anchor="mm")
    return draw


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


def twin_heads(tubes, reach=40.0):
    """Per live end of every tube and per side, how far its headwall may reach: short of the inside wall of another
    tube beside it (a twin of the other carriageway) near that end. None: the full HEAD_W."""
    for tb in tubes:
        for e in (0, 1):
            if not tb.live[e]:
                continue
            i = 0 if e == 0 else len(tb.s) - 1
            p, nrm = tb.P[i, :2], tb.N[i]
            for ot in tubes:
                if ot is tb:
                    continue
                d = np.linalg.norm(ot.P[:, :2] - p, axis=1)
                near = d < reach
                if not near.any():
                    continue
                n = (ot.P[near, :2] - p) @ nrm                  # across this tube's axis
                for sg in (1, -1):
                    side = n[np.sign(n) == sg]
                    if not len(side):
                        continue
                    lim = float(np.min(np.abs(side))) - ot.hw - TWIN_GAP
                    cur = tb.head_w[e][sg]
                    tb.head_w[e][sg] = lim if cur is None else min(cur, lim)


def headwall(tb, i, inward, ter=None, widths=None):
    """A headwall HEAD m thick from station i inwards (inward +1 / -1 along the stations), round the opening. Each
    side goes down to FOOT under the lowest ground at its outer edge: on the lake side of the Vallone d'Agno the
    ground falls away beside the track and the wall stood on nothing, a gap under it (laptop run 4)."""
    ring = tb.ring()
    Wf = tb.hw_out + HEAD_W
    # each side as wide as the twin beside it leaves (never narrower than the shell round the opening)
    Ws = {sg: Wf if not widths or widths.get(sg) is None else float(np.clip(widths[sg], tb.hw + 0.2, Wf))
          for sg in (1, -1)}
    top = tb.crown + SHELL + HEAD_UP
    j = i + inward
    bot = {1: -0.6, -1: -0.6}
    if ter is not None:
        for sg in (1, -1):
            g = [float(ter.sample([tb.frame(st, sg * Ws[sg] * f, 0.0)[0]], [tb.frame(st, sg * Ws[sg] * f, 0.0)[1]])[0])
                 for st in (i, j) for f in (0.6, 1.0)]
            bot[sg] = min(-0.6, min(g) - tb.floor[i] - FOOT)
    # the face: the outer rectangle minus the opening, as a fan of quads between the opening and the rectangle
    frame = []
    k = len(ring)
    # rectangle points matched to every ring point: same n clipped to the rectangle, on its top or sides
    rect = []
    for n, z in ring:
        sg = 1 if n > 0 else -1
        if z <= tb.wall + 1e-6:
            rect.append((sg * Ws[sg], bot[sg] if z == 0.0 else z))
        else:
            rect.append((n * Ws[sg] / tb.hw, top))
    rect[0] = (Ws[1], bot[1])
    rect[-1] = (-Ws[-1], bot[-1])
    tris = []
    for st, face_out in ((i, True), (j, False)):
        for a in range(k - 1):
            p0, p1 = tb.frame(st, *ring[a]), tb.frame(st, *ring[a + 1])
            q0, q1 = tb.frame(st, *rect[a]), tb.frame(st, *rect[a + 1])
            tris += [p0, q0, q1, p0, q1, p1]
        # under the floor's edge down to the side's foot (the fan joins the floor corner to the foot diagonally)
        for sg in (1, -1):
            if bot[sg] < -0.6 + 1e-6:
                tris += [tb.frame(st, sg * tb.hw, 0.0), tb.frame(st, sg * tb.hw, bot[sg]), tb.frame(st, sg * Ws[sg], bot[sg])]
        # the corners of the rectangle above the vault's sides
        for sg in (1, -1):
            a0 = tb.frame(st, sg * Ws[sg], tb.wall)
            a1 = tb.frame(st, sg * Ws[sg], top)
            a2 = tb.frame(st, sg * tb.hw * 0.92 * Ws[sg] / Wf, top)
            tris += [a0, a1, a2]
    # the outer sides and the top of the block
    Wp, Wn = Ws[1], Ws[-1]
    for (n0, z0), (n1, z1) in (((Wp, bot[1]), (Wp, top)), ((Wp, top), (-Wn, top)), ((-Wn, top), (-Wn, bot[-1]))):
        A0, A1 = tb.frame(i, n0, z0), tb.frame(i, n1, z1)
        B0, B1 = tb.frame(j, n0, z0), tb.frame(j, n1, z1)
        tris += [A0, B0, B1, A0, B1, A1]
    # the cornice: a lip 0.25 m out over the face
    for st, sgn in ((i, -inward),):
        c0 = tb.frame(st, Wp + 0.2, top) + np.r_[tb.T[st] * sgn * 0.25, 0]
        c1 = tb.frame(st, -Wn - 0.2, top) + np.r_[tb.T[st] * sgn * 0.25, 0]
        d0 = tb.frame(j, Wp + 0.2, top)
        d1 = tb.frame(j, -Wn - 0.2, top)
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
    vertices raised. Never beside a gallery: its valley side is open (the mound buried it up to v3.2)."""
    ok = ~tb.gal
    if not ok.any():
        return 0
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


def valley_clear(tb, ter):
    """Lower the ground in front of a gallery's open side: swissALTI3D smears the roof down the slope, and the ground
    a terrain square beyond the roof's edge stood in the openings (the cap of the hole squares with it). Within
    VALLEY_CLEAR m of the edge no vertex stands over the parapet's top, then 1:1 up (Tube.valley_cap); never raised.
    Returns the number of vertices lowered."""
    if not (tb.gal & (tb.ms != 0)).any():
        return 0
    # what the ground does in front of the open side (the report: is the smear of the roof there?)
    k = np.where(tb.gal & (tb.ms != 0))[0]
    edge = tb.hw + PILLAR_D + GAL_OVER
    for d in (1.0, 3.0):
        q = tb.P[k, :2] - tb.N[k] * (tb.ms[k] * (edge + d))[:, None]
        dz = ter.sample(q[:, 0], q[:, 1]) - tb.floor[k]
        tb.valley_ground = getattr(tb, "valley_ground", {})
        tb.valley_ground[f"{d:.0f}m"] = [round(float(np.percentile(dz, p)), 2) for p in (10, 50, 90)]
    ext = tb.hw + PILLAR_D + GAL_OVER + VALLEY_CLEAR + VALLEY_RISE
    g = tb.gal
    xs, ys = tb.P[g, 0], tb.P[g, 1]
    c0 = int(max(0, math.floor((xs.min() - ext - ter.x0) / ter.sq)))
    c1 = int(min(ter.n - 1, math.ceil((xs.max() + ext - ter.x0) / ter.sq)))
    r0 = int(max(0, math.floor((ys.min() - ext - ter.y0) / ter.sq)))
    r1 = int(min(ter.n - 1, math.ceil((ys.max() + ext - ter.y0) / ter.sq)))
    R, C = np.mgrid[r0:r1 + 1, c0:c1 + 1]
    R, C = R.ravel(), C.ravel()
    x, y = ter.x0 + C * ter.sq, ter.y0 + R * ter.sq
    s, n, i = tb.local(np.column_stack([x, y]))
    k = (s >= tb.s[0]) & (s <= tb.s[-1])
    want = tb.floor[i] + tb.valley_cap(i, -tb.ms[i] * n)
    k &= ter.h[R, C] > want
    R, C, w = R[k], C[k], want[k]
    ter.h[R, C] = w
    ter.q = ter.q.copy() if not ter.q.flags.writeable else ter.q
    ter.q[R, C] = np.clip(np.round((w - ter.z0) / ter.maxh * 65535.0), 0, 65535).astype(np.uint16)
    return int(k.sum())


def end_clear(tb, ter):
    """Lower the ground at a gallery's open ends (a live end with no headwall): swissALTI3D draws the roof and its fill
    as ground sloping down from the roof to the road out of the gallery, and the hole squares across the end were capped
    on that slope, a ramp 2-5 m high standing in the opening (Switzerland Builder, San Bernardino zone). Across the
    opening (+ END_SIDE) from END_IN squares inside the end to END_OUT squares out the ground goes under the floor
    (END_DROP); never raised. Returns the number of vertices lowered."""
    done = 0
    for e in (0, 1):
        st = 0 if e == 0 else len(tb.s) - 1
        if not (tb.live[e] and tb.gal[st]):
            continue
        way = -1.0 if e == 0 else 1.0
        p, t, nrm = tb.P[st, :2], tb.T[st] * way, tb.N[st]
        ext = tb.hw + END_SIDE + (END_IN + END_OUT + 1) * ter.sq
        c0 = int(max(0, math.floor((p[0] - ext - ter.x0) / ter.sq)))
        c1 = int(min(ter.n - 1, math.ceil((p[0] + ext - ter.x0) / ter.sq)))
        r0 = int(max(0, math.floor((p[1] - ext - ter.y0) / ter.sq)))
        r1 = int(min(ter.n - 1, math.ceil((p[1] + ext - ter.y0) / ter.sq)))
        R, C = np.mgrid[r0:r1 + 1, c0:c1 + 1]
        R, C = R.ravel(), C.ravel()
        q = np.column_stack([ter.x0 + C * ter.sq, ter.y0 + R * ter.sq]) - p
        d, n = q @ t, q @ nrm
        want = tb.floor[st] - END_DROP
        k = (d >= -END_IN * ter.sq) & (d <= END_OUT * ter.sq) & (np.abs(n) <= tb.hw + END_SIDE) & (ter.h[R, C] > want)
        if not k.any():
            continue
        R, C = R[k], C[k]
        ter.h[R, C] = want
        ter.q = ter.q.copy() if not ter.q.flags.writeable else ter.q
        ter.q[R, C] = np.uint16(np.clip(np.round((want - ter.z0) / ter.maxh * 65535.0), 0, 65535))
        done += int(k.sum())
    return done


def holes(tb, ter):
    """Terrain samples to hole: squares (lower-left sample) meeting the footprint of the tube from the headwall in,
    where the ground stands between the floor + CLEAR and the shell's top. Returns (rows, cols)."""
    ext = max(tb.wl.max(), tb.wr.max(), tb.hw_out) + HEAD_W
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
            inside = (s >= tb.s[0]) & (s <= tb.s[-1]) & tb.within(n, i, 0.1)
            if not inside.any():
                continue
            g = ter.sample(x, y)
            z = g - tb.floor[i]
            # under a road's deck any ground over it is in the way (the asphalt is a face at the floor: ground up to
            # CLEAR over it showed through); elsewhere (a wall, a rail tube's ballast) CLEAR
            low = np.where((np.abs(n) <= tb.hw) & (tb.kind == "road"), DECK_CLEAR, CLEAR)
            hit |= inside & (z > low) & (z < tb.top(i, n) + 0.3)
    return R[hit], C[hit]


def cap(tb, ter, R, C, colours):
    """Triangles (and vertex colours) closing the hole squares outside the tube at the ground's own heights. Over a
    gallery's roof the ground also stands where it is higher than the roof (its fill: swissALTI3D has it): left open
    there, the ground kept over the roof ended a metre over the roof's top, open to the sky seen from the valley."""
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
        s, n, ii = tb.local(np.column_stack([xc.ravel(), yc.ravel()]))
        taken = ((s >= tb.s[0]) & (s <= tb.s[-1]) & tb.within(n, ii, -0.05)).reshape(k, k)
        fill = np.zeros((k, k), bool)
        zr = z
        if (taken & tb.gal[ii].reshape(k, k)).any():
            # over a gallery's roof: a taken cell with a corner whose ground is over the roof's top is drawn, its
            # corners at the ground or just over the roof (continuous with the ground kept beyond the hole square)
            sq_, nq, iq = tb.local(np.column_stack([x.ravel(), y.ravel()]))
            roof = (tb.floor[iq] + tb.top(iq, nq)).reshape(k + 1, k + 1) + ROOF_FILL_EPS
            over = z > roof
            anyc = over[:-1, :-1] | over[1:, :-1] | over[:-1, 1:] | over[1:, 1:]
            fill = taken & tb.gal[ii].reshape(k, k) & anyc
            zr = np.maximum(z, roof)
        col = colours(r, c)
        if not (taken & ~fill).any() and (not fill.any() or np.array_equal(zr, z)):
            # the whole square at the ground's heights: its two triangles as the game splits it (the fine cells lie in
            # their planes; 72 triangles a square made 177k on San Bernardino's galleries)
            P = [(x[i, j], y[i, j], z[i, j]) for i, j in ((0, 0), (0, k), (k, k), (k, 0))]
            tris += [P[0], P[1], P[2], P[0], P[2], P[3]]
            cols += [col] * 6
            continue
        for a in range(k):
            for b in range(k):
                if taken[a, b] and not fill[a, b]:
                    continue
                zz = zr if fill[a, b] else z
                p00 = (x[a, b], y[a, b], zz[a, b])
                p10 = (x[a, b + 1], y[a, b + 1], zz[a, b + 1])
                p01 = (x[a + 1, b], y[a + 1, b], zz[a + 1, b])
                p11 = (x[a + 1, b + 1], y[a + 1, b + 1], zz[a + 1, b + 1])
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


def gallery_index(found):
    """{kind: (KD tree of points every 0.5 m along every line, gallery flag of each)}: the stations of a chained tube
    take the flag of the nearest line (a tube may be tunnel and gallery in turn, and a flag carried through chain()
    belongs to the segments, not to the points)."""
    idx = {}
    for kind in ("road", "rail"):
        pts, fl = [], []
        for k, props, Q in found:
            if k != kind or len(Q) < 2:
                continue
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q[:, :2], axis=0), axis=1))]
            s = np.arange(0.0, d[-1] + 0.25, 0.5)
            pts.append(np.column_stack([np.interp(s, d, Q[:, c]) for c in range(3)]))
            fl.append(np.full(len(s), props.get("KUNSTBAUTE") == "Galerie"))
        if pts:
            idx[kind] = (cKDTree(np.concatenate(pts)), np.concatenate(fl))
    return idx


def gallery_flags(idx, kind, P):
    if kind not in idx:
        return np.zeros(len(P), bool)
    tree, fl = idx[kind]
    return fl[tree.query(P[:, :3])[1]]


def ai_ends(lv):
    """[(first, second, second last and last node (4, 3), one-way)] of the level's AI roads."""
    out = []
    p = os.path.join(lv, "main", "MissionGroup", "AIRoads", "items.level.json")
    if os.path.exists(p):
        for o in read_items(p):
            if o.get("class") == "DecalRoad" and len(o.get("nodes") or []) >= 2:
                N = np.asarray([q[:3] for q in o["nodes"]], np.float64)
                out.append((N[[0, 1, -2, -1]], bool(o.get("oneWay"))))
    return out


def portal_flow(tb, roads, e, reach=15.0):
    """Which way the one-way AI road nearest the live portal e runs: +1 along the stations, -1 against, 0 none.
    Its direction of travel at the end that comes to the portal (into the tube or out of it) against the tube's."""
    i = 0 if e == 0 else -1
    p, t = tb.P[i], tb.T[i]
    best = (reach, 0)
    for N, one in roads:
        if not one:
            continue
        for q, v in ((N[3], N[3, :2] - N[2, :2]), (N[0], N[1, :2] - N[0, :2])):
            d = float(np.hypot(*(q[:2] - p[:2])))
            if d >= best[0] or abs(q[2] - p[2]) > 5.0:
                continue
            c = float(v @ t) / max(float(np.linalg.norm(v)), 1e-9)
            if abs(c) > 0.7:
                best = (d, 1 if c > 0 else -1)
    return best[1]


def travel_dir(tb, tubes, roads, twin=60.0):
    """+1 / -1: the tube is one carriageway of a road drawn as two lines (swissTLM3D RICHTUNGSG Wahr), one-way along /
    against its stations; 0: both ways. The one-way AI roads at its live portals say which way; else traffic keeps to
    the right, the other carriageway's tube on the left (ai_roads.separated_dir). Two lanes of a portal made one piece
    (chain) carry both directions."""
    if tb.kind != "road" or tb.props.get("RICHTUNGSG") != "Wahr" or tb.props.get("_TWOWAY"):
        return 0
    vote = sum(portal_flow(tb, roads, e) for e in (0, 1) if tb.live[e])
    if vote:
        return int(np.sign(vote))
    votes = []
    for k in range(0, len(tb.s), max(1, len(tb.s) // 8)):
        p, t = tb.P[k, :2], tb.T[k]
        for ot in tubes:
            if ot is tb or ot.kind != "road" or ot.props.get("RICHTUNGSG") != "Wahr":
                continue
            d = np.linalg.norm(ot.P[:, :2] - p, axis=1)
            j = int(np.argmin(d))
            if d[j] > twin or abs(float(ot.T[j] @ t)) < math.cos(math.radians(30)):
                continue
            v = ot.P[j, :2] - p
            votes.append((float(d[j]), 1 if t[0] * v[1] - t[1] * v[0] > 0 else -1))
    if not votes:
        return 0
    votes.sort()
    return 1 if sum(v for _, v in votes[:max(3, len(votes) // 3)]) > 0 else -1


def catenary_near(lv, tubes, reach=150.0):
    """Rail tubes of an electrified line: the level's catenary wires (railway.catenary_step) come within reach m of a
    live portal."""
    rail = [tb for tb in tubes if tb.kind == "rail"]
    if not rail:
        return
    pts = []
    for _, o, path in group_shapes(lv, "railway"):
        if "catenary_wires" not in path or not os.path.exists(path):
            continue
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for parts in dae_triangles(open(path, encoding="utf-8").read()).values():
            for _, T in parts:
                pts.append(T.reshape(-1, 3)[::15, :2] + pos[:2])
    if not pts:
        return
    tree = cKDTree(np.concatenate(pts))
    for tb in rail:
        tb.electric = any(tb.live[e] and tree.query(tb.P[0 if e == 0 else -1, :2])[0] < reach for e in (0, 1))


def plan(lv, ter):
    """(candidates, tubes to build, Tops, AI road ends): the lines chained, their gallery stations, live portals; the
    tubes cut where they leave the terrain and closed where they join nothing; the hill side of their galleries,
    their direction of travel and lanes, the twins' headwalls, the electrified rail tubes."""
    found = lines()
    gidx = gallery_index(found)
    cand = []
    for kind, props, Q, joined, group in chain(found):
        if len(Q) < 2:
            continue
        if not (ter.inside(*Q[0, :2]) or ter.inside(*Q[-1, :2])):
            continue
        tb = Tube(kind, props, Q, joined, group)
        tb.set_gallery(gallery_flags(gidx, kind, tb.P))
        cand.append(tb)
    if not cand:
        return cand, [], None, []
    ends = np.array([tb.P[i, :2] for tb in cand for i in (0, -1)])
    tops = Tops(lv, ends)
    for tb in cand:
        tb.join(tops)
    # a line is built when it or a line it meets (a branch, the tube a branch opens into) has a live portal
    live_groups = {tb.group for tb in cand if any(tb.live)}
    tubes = [tb for tb in cand if any(tb.live) or (any(tb.joined) and tb.group in live_groups)]
    tubes = [tb for tb in tubes if tb.clip_to(ter)]
    roads = ai_ends(lv)
    for tb in tubes:
        tb.hill_sides(ter)
        tb.oneway = travel_dir(tb, cand, roads)
        tb.lanes = 2 if tb.oneway and tb.cw >= 7.0 else 1
    twin_heads(tubes)
    catenary_near(lv, tubes)
    return cand, tubes, tops, roads


def tunnels_step(root, report=None):
    t0 = time.time()
    lv = os.path.join(root, "levels", LEVEL_NAME)
    ter = Terrain(lv)
    cand, tubes, tops, roads = plan(lv, ter)
    res = {"candidates": len(cand), "tunnels": 0, "km": 0.0, "gallery_km": 0.0, "portals": 0, "closed_ends": 0,
           "one_way": 0, "holes": 0, "cap_triangles": 0, "cut_triangles": 0, "forest_removed": 0, "lights": 0,
           "ai_roads": 0, "sos": 0, "exits": 0, "signs": 0, "fans": 0, "list": []}
    if not cand:
        print("tunnels: none in the level", flush=True)
        return res
    print("tunnels: %d lines, %d to build (%.0f s)" % (len(cand), len(tubes), time.time() - t0), flush=True)
    if not tubes:                                       # lines in the zone, none joins a road or track (ti_m2_3)
        return res
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
    items, hole_sq, volumes, ais = [], [], [], []
    shp_dir = os.path.join(lv, "art", "shapes", "tunnels")
    os.makedirs(shp_dir, exist_ok=True)
    atlas = SignAtlas()
    for k, tb in enumerate(tubes):
        res["mound_vertices"] = res.get("mound_vertices", 0) + mound(tb, ter, tops)
        res["valley_vertices"] = res.get("valley_vertices", 0) + valley_clear(tb, ter)
        res["end_vertices"] = res.get("end_vertices", 0) + end_clear(tb, ter)
        parts, sign_parts = build_tube(tb, None, ter, atlas)
        if any(ot is not tb and ot.group == tb.group for ot in tubes):
            res["junction_cut_triangles"] = res.get("junction_cut_triangles", 0) + open_junction(tb, parts, tubes)
        R, C = holes(tb, ter)
        capT, capC = cap(tb, ter, R, C, colours)
        origin = np.r_[tb.P[len(tb.P) // 2, :2], 0.0]
        solid, decor = bng.MeshBuilder(), bng.MeshBuilder()
        for mat, T in parts.items():
            V = T.reshape(-1, 3)
            uv = bng.box_uvs_soup(V, 2.0) if mat in BOX_UV else V[:, :2] / 4.0
            nrm = bng.flat_normals_soup(V)
            if mat in ("mp_tunnel_wall", "mp_tunnel_band"):
                nrm = vault_normals(tb, T, nrm)
            (decor if mat.startswith(DECOR) else solid).add(mat, V, uvs=uv, normals=nrm)
        for mat, (T, UV) in sign_parts.items():
            V = T.reshape(-1, 3)
            decor.add(mat, V, uvs=UV.reshape(-1, 2), normals=bng.flat_normals_soup(V))
        if len(capT):
            V = capT.reshape(-1, 3)
            solid.add("mp_steep_bank", V, uvs=V[:, :2] / 6.0, colors=capC.reshape(-1, 4))
        name = f"tunnel_{k:03d}"
        for mb, nm, coll in ((solid, name, True), (decor, name + "_decor", False)):
            if not mb.parts:
                continue
            path = os.path.join(shp_dir, nm + ".dae")
            if os.path.exists(path):                    # a new file: the level may be a hard-linked copy
                os.remove(path)
            mb.write_dae(path, name=nm, origin=origin)
            items.append(dict(bng.tsstatic(f"{L}/art/shapes/tunnels/{nm}.dae", origin, collision=coll), __parent="tunnels"))
        # lights: under the vault, twice as dense near a live portal; on the hill side of a gallery's roof; sparse
        # in a rail tunnel
        si = tb.s[1] + 5.0
        while si < tb.s[-2]:
            i, _ = tb.at(si)
            near = (tb.live[0] and si - tb.s[1] < PORTAL_ZONE) or (tb.live[1] and tb.s[-2] - si < PORTAL_ZONE)
            if tb.gal[i]:
                ms = tb.ms[i] or 1
                items.append(tunnel_light(tb.frame(i, ms * (tb.hw - 0.6), tb.gclear - 0.3)))
                step = GAL_LIGHT_STEP
            else:
                items.append(tunnel_light(tb.frame(i, 0.0, tb.crown - 0.4)))
                step = RAIL_LIGHT_STEP if tb.kind == "rail" else LIGHT_STEP / 2 if near else LIGHT_STEP
            res["lights"] += 1
            si += step
        hole_sq.append((R, C))
        volumes.append(tb)
        eq = getattr(tb, "equipment", {})
        for key, name_ in (("sos", "sos"), ("exit", "exits"), ("sign", "signs"), ("fan", "fans")):
            res[name_] += eq.get(key, 0)
        gal_m = float(np.sum(np.diff(tb.s)[(tb.gal[:-1] & tb.gal[1:])]))
        res["tunnels"] += 1
        res["km"] += tb.length / 1000
        res["gallery_km"] += gal_m / 1000
        res["portals"] += sum(tb.live)
        res["closed_ends"] += sum(tb.closed)
        res["one_way"] += bool(tb.oneway)
        res["holes"] += len(R)
        res["cap_triangles"] += len(capT)
        res["list"].append({"name": tb.props.get("NAME") or "", "kind": tb.props.get("OBJEKTART"), "length_m": round(tb.length),
                            "gallery_m": round(gal_m), "live": tb.live, "closed": tb.closed, "one_way": tb.oneway,
                            "lanes": tb.lanes, "electric": tb.electric, "from": tb.P[1, :2].round(1).tolist(),
                            "to": tb.P[-2, :2].round(1).tolist(), "holes": len(R), "equipment": eq,
                            "valley_ground": getattr(tb, "valley_ground", None)})
        if tb.kind == "road" and not any(tb.closed):     # a dead end gets no AI road (traffic would be stuck in it)
            ais.append(ai_road(tb, roads, k))
    res["ai_joints"] = link_joints(ais)
    res["ai_roads"] = len(ais)
    items += ais
    # the lit signs and the materials
    for k, img in enumerate(atlas.pages):
        p = os.path.join(shp_dir, f"t_tunnel_signs{k}.color.png")
        if os.path.exists(p):
            os.remove(p)
        img.save(p)
    mp = os.path.join(shp_dir, "main.materials.json")
    if os.path.exists(mp):
        os.remove(mp)
    bng.write_materials(mp, materials(len(atlas.pages)))
    res["sign_pages"] = len(atlas.pages)
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
    gi = os.path.join(g, "items.level.json")
    with open(gi + ".part", "w") as f:
        for o in items:
            f.write(json.dumps(o, separators=(",", ":")) + "\n")
    os.replace(gi + ".part", gi)
    mg = os.path.join(lv, "main", "MissionGroup", "items.level.json")
    groups = read_items(mg)
    if not any(o.get("name") == "tunnels" for o in groups):
        groups.append({"name": "tunnels", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "MissionGroup"})
        with open(mg + ".part", "w") as f:              # a new file: the level may be a hard-linked copy
            for o in groups:
                f.write(json.dumps(o, separators=(",", ":")) + "\n")
        os.replace(mg + ".part", mg)
    res["km"] = round(res["km"], 2)
    res["gallery_km"] = round(res["gallery_km"], 2)
    res["seconds"] = round(time.time() - t0)
    print("tunnels:", {k: v for k, v in res.items() if k != "list"}, flush=True)
    for t in res["list"]:
        print("  ", t, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res


def materials(sign_pages=0):
    t = f"{L}/art/shapes/tunnels"
    out = [italy_mats.material("mp_tunnel_wall", "m_concrete_old", "CONCRETE", base_color=[0.78, 0.77, 0.74, 1]),
           italy_mats.material("mp_tunnel_band", "m_concrete_old", "CONCRETE", base_color=[0.95, 0.95, 0.93, 1]),
           italy_mats.material("mp_tunnel_portal", "m_concrete_old", "CONCRETE", base_color=[0.86, 0.85, 0.82, 1]),
           italy_mats.material("mp_tunnel_walk", "m_concrete_old", "CONCRETE", base_color=[0.70, 0.70, 0.68, 1]),
           bng.material("mp_tunnel_lamp", base_color=[1.0, 0.86, 0.62, 1], roughness=0.4,
                        detail={"emissiveFactor": [1.0, 0.82, 0.55], "instanceEmissive": True}),
           bng.material("mp_tunnel_paint", base_color=[0.86, 0.86, 0.84, 1], roughness=0.65),
           bng.material("mp_tunnel_niche", base_color=[0.80, 0.30, 0.08, 1], roughness=0.5, metallic=0.2,
                        ground_type="METAL"),
           bng.material("mp_tunnel_door", base_color=[0.05, 0.40, 0.21, 1], roughness=0.45, metallic=0.3,
                        ground_type="METAL"),
           bng.material("mp_tunnel_fan", base_color=[0.62, 0.64, 0.66, 1], roughness=0.35, metallic=0.8),
           bng.material("mp_tunnel_fan_dark", base_color=[0.03, 0.03, 0.035, 1], roughness=0.8),
           bng.material("mp_tunnel_wire", base_color=[0.20, 0.17, 0.12, 1], roughness=0.45, metallic=0.8,
                        double_sided=True),
           bng.material("mp_tunnel_steel", base_color=[0.55, 0.57, 0.58, 1], roughness=0.5, metallic=0.7)]
    for k in range(sign_pages):
        n = f"{t}/t_tunnel_signs{k}.color.png"
        out.append(bng.material(f"mp_tunnel_signs{k}", n, roughness=0.4,
                                extra={"Stages": [{"baseColorMap": n, "roughnessFactor": 0.4, "emissiveMap": n,
                                                   "emissiveFactor": [0.9, 0.9, 0.9], "instanceEmissive": True},
                                                  {}, {}, {}]}))
    return out


def tunnel_light(p):
    return {"class": "SpotLight", "persistentId": bng.pid(), "position": [float(v) for v in p],
            "rotationMatrix": [1, 0, 0, 0, 0, -1, 0, 1, 0], "range": 14.0, "innerAngle": 110.0, "outerAngle": 150.0,
            "intensity": 1200.0, "intensityUnit": "lm", "brightness": 0.24, "color": [1.0, 0.78, 0.5, 1.0],
            "castShadows": False, "isEnabled": True, "__parent": "tunnels"}


def ai_road(tb, roads, k):
    """A DecalRoad along the carriageway (its nodes in the direction of travel of a one-way tube, one lane each way
    else), each end at a live portal on the nearest AI road end (the game links roads that share a point)."""
    idx = np.unique(np.r_[np.arange(1, len(tb.s) - 1, max(1, int(10 / STEP))), len(tb.s) - 2])
    nodes = [[float(tb.P[i, 0]), float(tb.P[i, 1]), float(tb.floor[i]) + 0.1, float(tb.cw)] for i in idx]
    linked = [False, False]
    if roads:
        E = np.array([q for N, _ in roads for q in (N[0], N[3])])
        tree = cKDTree(E[:, :2])
        for e in (0, 1):
            if not tb.live[e]:
                continue
            j = 0 if e == 0 else len(nodes) - 1
            d, kk = tree.query(nodes[j][:2])
            if d < 15.0 and abs(E[kk, 2] - nodes[j][2]) < 5.0:
                q = [float(E[kk, 0]), float(E[kk, 1]), float(E[kk, 2]), float(tb.cw)]
                if e == 0:
                    nodes.insert(0, q)
                else:
                    nodes.append(q)
                linked[e] = True
    if tb.oneway < 0:
        nodes, linked = nodes[::-1], linked[::-1]
    art = tb.props.get("OBJEKTART", "")
    slug = re.sub(r"\W+", "_", (tb.props.get("NAME") or art).split("|")[0]).strip("_").lower()
    o = {"name": f"tunnel_{k:03d}_{slug}"[:60], "class": "DecalRoad", "persistentId": bng.pid(),
         "position": nodes[0][:3], "drivability": DRIVABILITY.get(art, 1), "improvedSpline": True,
         "material": "road_invisible", "nodes": nodes, "autoLanes": False, "__parent": "tunnels", "_linked": linked}
    if tb.oneway:
        o.update(oneWay=True, lanesLeft=0, lanesRight=int(tb.lanes),
                 speedLimit=27.78 if art in ("Autobahn", "Autostrasse") else 22.22)
    else:
        o.update(lanesLeft=1, lanesRight=1, speedLimit=13.89 if tb.cw < 6 else 22.22)
    return o


def link_joints(ais, reach=12.0):
    """The ends of tunnel AI roads that no portal linked (a branch where it opens into the tube it meets, inside the
    hill) moved onto the nearest node of another tunnel's AI road: the game links roads only where they share a
    point. Returns the number of ends linked."""
    n = 0
    for a in ais:
        for e, j in ((0, 0), (1, -1)):
            if a["_linked"][e]:
                continue
            p = np.array(a["nodes"][j][:2])
            best = None
            for b in ais:
                if b is a:
                    continue
                N = np.array([q[:2] for q in b["nodes"]])
                d = np.hypot(*(N - p).T)
                m = int(np.argmin(d))
                if d[m] < reach and (best is None or d[m] < best[0]):
                    best = (float(d[m]), b["nodes"][m])
            if best:
                a["nodes"][j] = [*best[1][:3], a["nodes"][j][3]]
                n += 1
    for a in ais:
        a["position"] = a["nodes"][0][:3]
        a.pop("_linked", None)
    return n


def in_volume(tb, P, margin=0.05):
    """Points (k, 3) inside the tube's body (shell included) from its headwalls in."""
    s, n, i = tb.local(P[:, :2])
    z = P[:, 2] - tb.floor[i]
    body = (s >= tb.s[0]) & (s <= tb.s[-1]) & tb.within(n, i, margin) & (z > -0.7) & (z < tb.top(i, n) + margin)
    # in front of a live portal: the opening's clearance, APPROACH m out (a bank or skin standing in the way)
    vault = tb.ceiling(i, n)
    out = np.zeros(len(P), bool)
    for e, live in enumerate(tb.live):
        if live:
            a = (s < tb.s[0]) & (s >= tb.s[0] - APPROACH) if e == 0 else (s > tb.s[-1]) & (s <= tb.s[-1] + APPROACH)
            out |= a
    # in front of a gallery's open side: over the ground valley_clear() lowered (the skin laid on the old ground)
    front = (s >= tb.s[0]) & (s <= tb.s[-1]) & (z > tb.valley_cap(i, -tb.ms[i] * n) + 0.3) & \
        (z < tb.gclear + GAL_ROOF + VALLEY_RISE)
    return body | front | (out & (np.abs(n) <= tb.hw) & (z > CLEAR + 0.15) & (z < vault))


def over_gallery(tb, P, margin=GAL_PLAN_MARGIN):
    """Points (k, 3) over (or in) a gallery's footprint seen from above, down to GAL_PLAN_DOWN under its floor: the
    skin and the survey's walls there stand on swissALTI3D's smear of the gallery (rock skin draped over the roof's edge
    as curtains, the survey's lines of the gallery's own walls as stone walls on its roof); the gallery and the ground
    kept over its roof take their place."""
    s, n, i = tb.local(P[:, :2])
    z = P[:, 2] - tb.floor[i]
    return (s >= tb.s[0]) & (s <= tb.s[-1]) & tb.gal[i] & tb.within(n, i, margin) & (z > -GAL_PLAN_DOWN)


def cut_meshes(lv, tubes, ter, hole_sq):
    """Triangles of the skin, the walls and the fences inside a tube, and of the skin over a hole, taken out."""
    holes = set()
    for R, C in hole_sq:
        holes.update(zip(R.tolist(), C.tolist()))
    boxes = []
    for tb in tubes:
        e = max(tb.wl.max(), tb.wr.max(), tb.hw_out) + HEAD_W + APPROACH + 2 + (VALLEY_CLEAR + VALLEY_RISE) * tb.gal.any()
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
        plan = skin or "/walls/" in path.replace(os.sep, "/") or "/fences/" in path.replace(os.sep, "/")

        def drop(mat, T, pos=pos, skin=skin, plan=plan):
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
                if plan and tb.gal.any():
                    for k in range(3):
                        d[m] |= over_gallery(tb, T[m, k] + pos)
                    d[m] |= over_gallery(tb, c[m])
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
            e = max(tb.wl.max(), tb.wr.max(), tb.hw_out) + HEAD_W + 2 + (VALLEY_CLEAR + VALLEY_RISE) * tb.gal.any()
            m = (P[:, 0] > tb.P[:, 0].min() - e) & (P[:, 0] < tb.P[:, 0].max() + e) & \
                (P[:, 1] > tb.P[:, 1].min() - e) & (P[:, 1] < tb.P[:, 1].max() + e)
            if not m.any():
                continue
            s, n, i = tb.local(P[m, :2])
            z = P[m, 2] - tb.floor[i]
            hit = (s >= tb.s[0] - 1) & (s <= tb.s[-1] + 1) & tb.within(n, i, 1.0) & (z < tb.top(i, n) + 1.0)
            hit |= (s >= tb.s[0]) & (s <= tb.s[-1]) & (z > tb.valley_cap(i, -tb.ms[i] * n) + 0.3)
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
