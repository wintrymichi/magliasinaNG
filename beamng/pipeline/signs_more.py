"""Road signs nobody mapped in OpenStreetMap (v2.8, issue #21): where they stand, by rules, for
signs_more.signs_more_step. The signs of v2.7 (signs_net.py) are the mapped ones and those the regulation
OSM records implies; these are the warning and parking signs a Swiss road has where nothing is
mapped, placed after the Swiss rules (OSStr art. 3-4 and 103: a danger signal 150-250 m before the
danger outside the villages, up to 50 m inside):
- curves (1.01 / 1.02): on the main roads (OSM primary, secondary, tertiary, trunk) outside the
  villages (a mapped limit of 60 or more, or no mapped limit and fewer than VILLAGE_N buildings of
  the Federal Register within VILLAGE_R m), before a curve sharper than SHARP_R m of radius turning
  more than SHARP_TURN degrees that comes after APPROACH m of nearly straight road (radius over
  STRAIGHT_R m) in the direction of travel: an unexpected curve, not every bend of a mountain road.
  Several sharp curves less than SERIES_GAP m apart are one winding stretch: 1.03 / 1.04 (double
  curve, first to the right / left) with its length under it (5.03) where it is longer than 300 m;
- level crossings (1.15 with barriers, 1.16 without, from crossing:barrier): on every road of the
  network over a railway=level_crossing node, both ways, 150 m before it outside the villages, 50 m
  inside (less where a junction comes first; none closer than 20 m);
- the hazards OSM records on a road (hazard=falling_rocks 1.13, animal_crossing 1.24, school_zone
  1.23, road_narrows 1.07): at both ends of the way, for the traffic going into it, with the length of
  the way under it (5.03) where it is longer than 100 m;
- parking (4.17): at the entrance of the public car parks (amenity=parking with a public access, PARK_MIN m2
  or 10 places or more; with no access recorded, PARK_BIG m2 or 40 places or more; not along the street;
  or a parking_entrance node): where the drive into it leaves a road of the network, for the traffic that
  has it on its right.
Only on the Swiss side; a sign is left out where v2.7 already has the same signal within DEDUP m for
the same direction (beamng/verifica/signs_v2.7.json), and where another one of these stands within
25 m for the same direction.

    plan() -> [signs_net.Sign]
(c) OpenStreetMap contributors, ODbL.
"""
import gzip, json, math, os
import numpy as np
import shapely
import osm
import signs_net as sn
from signs_net import Sign
import argparse, json, math, os, sys, tempfile, time, zipfile
from collections import Counter
import bng
import signs_net as ps
import signs_ch

DATI = sn.DATI
V27 = os.path.join(os.path.dirname(DATI), "verifica", "signs_v2.7.json")
STEP = 2.0                # m between the samples of a road
SMOOTH = 5                # samples on each side for the heading (a 22 m window)
SHARP_R, SHARP_TURN = 60.0, 45.0
CURVE_R = 150.0           # a curve: radius under this
STRAIGHT_R = 200.0
APPROACH = 150.0
SERIES_GAP = 200.0
VILLAGE_R, VILLAGE_N = 45.0, 6
DIST_OUT, DIST_IN, DIST_MIN = 150.0, 50.0, 20.0
PARK_MIN = 300.0          # m2, a public car park
PARK_BIG = 1000.0         # m2, a car park whose access OSM does not record
PUBLIC = ("yes", "public", "customers", "permissive")
DEDUP = 60.0
HAZARDS = {"falling_rocks": "1.13", "animal_crossing": "1.24", "school_zone": "1.23", "road_narrows": "1.07"}


def _buildings():
    from scipy.spatial import cKDTree
    g = json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz"), "rt", encoding="utf-8"))["buildings"]
    B = np.array([[b["x"], b["y"]] for b in g if b.get("gstat") == 1004 and (b.get("garea") or 0) >= 30])
    return cKDTree(B)


class Ctx:
    def __init__(self):
        ways, self.nodes = osm.load()
        self.net = sn.Net(ways)
        self.ways = ways
        comm = sn.communes()
        self.swiss = shapely.union_all([g for _, g in comm]) if comm else None
        shapely.prepare(self.swiss)
        self.bt = _buildings()

    def in_ch(self, p):
        return self.swiss is not None and self.swiss.contains(shapely.Point(float(p[0]), float(p[1])))

    def village(self, p, lim):
        if lim is not None:
            return lim <= 50
        return len(self.bt.query_ball_point(np.asarray(p, float), VILLAGE_R)) >= VILLAGE_N


def _chains(net, keep):
    """Roads through the nodes where exactly two kept ways meet: [(seq [(way, +1/-1)], (n, 2) points)]."""
    ends = {}
    for i in keep:
        w = net.w[i]
        for nd in (w["nodes"][0], w["nodes"][-1]):
            ends.setdefault(nd, []).append(i)
    used, out = set(), []
    for i in keep:
        if i in used:
            continue
        used.add(i)
        seq = [(i, 1)]
        for direction in (1, -1):
            cur, sgn = i, direction
            while True:
                w = net.w[cur]
                nd = w["nodes"][-1] if sgn == 1 else w["nodes"][0]
                nxt = [j for j in ends.get(nd, []) if j != cur]
                if len(nxt) != 1 or nxt[0] in used:
                    break
                j = nxt[0]
                used.add(j)
                s2 = 1 if net.w[j]["nodes"][0] == nd else -1
                seq.append((j, s2)) if direction == 1 else seq.insert(0, (j, -s2))
                cur, sgn = j, s2
        pts = []
        for j, s in seq:
            xy = net.w[j]["xy"][::s]
            pts.extend(xy if not pts else xy[1:])
        out.append((seq, np.array(pts)))
    return out


def curves(cx):
    net = cx.net
    keep = [i for i, w in enumerate(net.w) if w["tags"].get("highway") in sn.MAIN - {"primary_link", "secondary_link",
            "tertiary_link", "trunk_link"} and w["tags"].get("junction") != "roundabout"]
    out = []
    for seq, P in _chains(net, keep):
        line = shapely.LineString(P)
        if line.length < 2 * APPROACH:
            continue
        s = np.arange(0.0, line.length, STEP)
        Q = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
        th = np.unwrap(np.arctan2(*np.diff(Q, axis=0).T[::-1]))
        th = np.r_[th, th[-1]]
        k = 2 * SMOOTH + 1
        ths = np.convolve(np.pad(th, SMOOTH, mode="edge"), np.ones(k) / k, mode="valid")
        kap = np.gradient(ths, STEP)
        # the way of every sample, for its tags
        acc = np.cumsum([net.w[j]["line"].length for j, _ in seq])
        wi = np.minimum(np.searchsorted(acc, s), len(seq) - 1)
        tags = [net.w[seq[q][0]]["tags"] for q in wi]
        # sharp curves: runs of one sign of curvature over 1/CURVE_R
        cs, i, n = [], 0, len(s)
        bend = np.abs(kap) > 1 / CURVE_R
        while i < n:
            if not bend[i]:
                i += 1
                continue
            j = i
            while j < n and bend[j] and np.sign(kap[j]) == np.sign(kap[i]):
                j += 1
            j = min(j, n - 1)
            if 1 / np.abs(kap[i:j + 1]).max() < SHARP_R and math.degrees(abs(ths[j] - ths[i])) > SHARP_TURN:
                cs.append((i, j, float(np.sign(kap[i]))))
            i = j + 1
        series = []
        for a, b, sg in cs:
            if series and s[a] - s[series[-1][1]] < SERIES_GAP:
                series[-1][1] = b
                series[-1][2].append(sg)
            else:
                series.append([a, b, [sg]])
        for a, b, sgs in series:
            mid = Q[(a + b) // 2]
            lim = sn._limit(tags[a])
            if not cx.in_ch(mid) or cx.village(mid, lim):
                continue
            length = s[b] - s[a]
            for fwd in (True, False):
                start, first = (a, sgs[0]) if fwd else (b, -sgs[-1])
                d0 = s[start] - APPROACH if fwd else s[start] + APPROACH
                if d0 < 0 or d0 > s[-1]:
                    continue
                lo, hi = sorted((int(np.searchsorted(s, d0)), start))
                lo, hi = (lo, hi - 3) if fwd else (lo + 3, hi)
                if hi > lo and (np.abs(kap[lo:hi]) > 1 / STRAIGHT_R).any():
                    continue                                      # not an unexpected curve
                q = int(np.searchsorted(s, d0))
                q = min(q, n - 1)
                u = Q[min(q + 1, n - 1)] - Q[max(q - 1, 0)]
                u = u / np.linalg.norm(u) * (1 if fwd else -1)
                # curvature > 0 turns left (anticlockwise) along the samples
                right = first < 0
                if len(sgs) == 1:
                    plates = [("1.01" if right else "1.02", None)]
                else:
                    plates = [("1.03" if right else "1.04", None)]
                    if length > 300:
                        plates.append(("5.03", _km(length)))
                lim2 = lim or 80
                out.append(Sign(float(Q[q][0]), float(Q[q][1]), u, plates, "rule", None, plates[0][0], lim2,
                                lim2 >= 80, False))
    return out


def _km(m):
    return f"{m / 1000:.1f} km".replace(".0 km", " km") if m >= 950 else f"{int(round(m / 50.0) * 50)} m"


def _walk(net, i, k, sgn, dist):
    """The point `dist` m from vertex k of way i going along (+1) / against (-1) it, through the nodes where
    the road goes on alone (two drivable ways); (point, direction of travel towards the start, reached m)."""
    gone, cur_i, cur_k, cur_s = 0.0, i, k, sgn
    while True:
        w = net.w[cur_i]
        line = w["line"]
        s0 = line.project(shapely.Point(w["xy"][cur_k]))
        room = (line.length - s0) if cur_s > 0 else s0
        if gone + room >= dist:
            s1 = s0 + cur_s * (dist - gone)
            p = np.asarray(line.interpolate(s1).coords[0])
            q = np.asarray(line.interpolate(s1 - cur_s * 3.0).coords[0])
            return p, sn._unit(q - p), dist
        gone += room
        nd = w["nodes"][-1] if cur_s > 0 else w["nodes"][0]
        nxt = [(j, kk) for j, kk in net.at.get(nd, []) if j != cur_i]
        if net.degree(nd) != 2 or len(nxt) != 1:
            p = w["xy"][-1] if cur_s > 0 else w["xy"][0]
            q = np.asarray(line.interpolate((line.length - 3.0) if cur_s > 0 else 3.0).coords[0])
            return np.asarray(p), sn._unit(q - p), gone
        cur_i, cur_k = nxt[0]
        cur_s = 1 if cur_k == 0 else -1


def level_crossings(cx):
    net, out = cx.net, []
    for n in cx.nodes:
        t = n["tags"]
        if t.get("railway") != "level_crossing" or not cx.in_ch((n["x"], n["y"])):
            continue
        barrier = t.get("crossing:barrier", "no") not in ("no", "none")
        code = "1.15" if barrier else "1.16"
        for i, k in net.at.get(n["id"], []):
            w = net.w[i]
            if w["tags"].get("highway") not in sn.SIGN_ROADS:
                continue
            lim = sn._limit(w["tags"])
            for sgn in (1, -1):                        # the traffic arriving from that side of the node
                if not net.can_drive(i, -sgn):
                    continue
                inside = cx.village((n["x"], n["y"]), lim)
                want = DIST_IN if inside else DIST_OUT
                p, u, got = _walk(net, i, k, sgn, want)
                got = min(got, want) if got >= want else got - 8.0     # short of the junction
                if got < DIST_MIN or u is None:
                    continue
                if got < want:
                    p, u, _ = _walk(net, i, k, sgn, got)
                out.append(Sign(float(p[0]), float(p[1]), u, [(code, None)], "rule", n["id"], code, lim or 50,
                                False, False))
    return out


def hazards(cx):
    net, out = cx.net, []
    for i, w in enumerate(net.w):
        hz = w["tags"].get("hazard")
        if hz not in HAZARDS or w["tags"].get("highway") not in sn.SIGN_ROADS:
            continue
        code = HAZARDS[hz]
        n = len(w["nodes"])
        L = w["line"].length
        for k, sgn in ((0, 1), (n - 1, -1)):           # entering the way at that end
            if not net.can_drive(i, sgn):
                continue
            p = net.point(i, k, sgn, 3.0)
            if not cx.in_ch(p):
                continue
            u = net.dir_at(i, k, sgn)
            if u is None:
                continue
            plates = [(code, None)] + ([("5.03", _km(L))] if L > 100 else [])
            out.append(Sign(float(p[0]), float(p[1]), u, plates, "rule", w["id"], code,
                            sn._limit(w["tags"]) or 50, False, False))
    return out


def parkings(cx):
    net, out = cx.net, []
    roads = [i for i, w in enumerate(net.w) if w["tags"].get("highway") in sn.SIGN_ROADS]
    rtree = shapely.STRtree([net.w[i]["line"] for i in roads])
    drives = [w for w in net.w if w["tags"].get("highway") in ("service",)]
    dtree = shapely.STRtree([w["line"] for w in drives])
    lots = []
    for w in cx.ways:
        t = w["tags"]
        if t.get("amenity") != "parking" or len(w["xy"]) < 4:
            continue
        if t.get("access") in ("private", "permit", "no", "delivery") or t.get("parking") in ("street_side", "lane",
                                                                                                "on_kerb", "half_on_kerb"):
            continue
        poly = shapely.Polygon(w["xy"])
        cap = sn._num(t.get("capacity")) or 0
        if not poly.is_valid or poly.area < PARK_MIN and cap < 10:
            continue
        if t.get("access") not in PUBLIC and poly.area < PARK_BIG and cap < 40:
            continue                                     # most likely the car park of a block of flats
        lots.append((w["id"], poly))
    for n in cx.nodes:
        if n["tags"].get("amenity") == "parking_entrance" and n["tags"].get("access") not in ("private", "no"):
            lots.append((n["id"], shapely.Point(n["x"], n["y"]).buffer(2.0)))
    for oid, poly in lots:
        if not cx.in_ch(np.asarray(poly.centroid.coords[0])):
            continue
        # the entrance: a drive from the lot to a road of the network, else the lot's edge nearest a road
        ent = None
        for j in dtree.query(poly.buffer(2.0), predicate="intersects"):
            d = drives[j]["line"]
            for end in (d.coords[0], d.coords[-1]):
                pe = shapely.Point(end)
                if poly.buffer(2.0).contains(pe):
                    continue
                r = rtree.query(pe.buffer(1.0), predicate="intersects")
                if len(r):
                    ent = (np.asarray(end), roads[r[0]])
                    break
            if ent:
                break
        if ent is None:
            j = rtree.nearest(poly)
            line = net.w[roads[j]]["line"]
            if line.distance(poly) > 12.0:
                continue
            a, _ = shapely.shortest_line(line, poly).coords
            ent = (np.asarray(a), roads[j])
        p, i = ent
        line = net.w[i]["line"]
        s = line.project(shapely.Point(p))
        a = np.asarray(line.interpolate(max(s - 3, 0)).coords[0])
        b = np.asarray(line.interpolate(min(s + 3, line.length)).coords[0])
        tng = sn._unit(b - a)
        if tng is None:
            continue
        c = np.asarray(poly.centroid.coords[0]) - p
        # the traffic that has the lot on its right: lot side = right of u
        u = tng if np.dot(c, [tng[1], -tng[0]]) > 0 else -tng
        if not net.can_drive(i, 1 if np.dot(u, tng) > 0 else -1) and net.oneway(i):
            u = -u
        q = np.asarray(line.interpolate(s).coords[0])
        out.append(Sign(float(q[0]), float(q[1]), u, [("4.17", None)], "rule", oid, "4.17",
                        sn._limit(net.w[i]["tags"]) or 50, False, False))
    return out


def _dedup(signs):
    """Left out where v2.7 has the same signal within DEDUP m for the same direction, or another of these
    of the same kind stands within 25 m for the same direction."""
    old = []
    if os.path.exists(V27):
        for o in json.load(open(V27, encoding="utf-8")).get("signs", []):
            f = np.asarray(o["facing"], float)
            old.append((o["x"], o["y"], -f, {c for c, _ in o["plates"]}))
    keep = []
    for s in signs:
        codes = {c for c, _ in s.plates} - {"text", "5.01", "5.03"}
        if any(math.hypot(x - s.x, y - s.y) < DEDUP and np.dot(u, s.u) > 0.5 and codes & c for x, y, u, c in old):
            continue
        if any(o.kind == s.kind and math.hypot(o.x - s.x, o.y - s.y) < 25 and np.dot(o.u, s.u) > 0.5 for o in keep):
            continue
        keep.append(s)
    return keep


def plan():
    cx = Ctx()
    return _dedup(curves(cx) + level_crossings(cx) + hazards(cx) + parkings(cx))


if __name__ == "__main__":
    from collections import Counter
    S = plan()
    print(len(S), Counter(s.kind for s in S).most_common())


# --------------------------------------------------------------------------------------------------
# The warning and parking signs nobody mapped in OpenStreetMap (v2.8, issue #21) in the built level.
#
# v2.7 (signs_net.signs_step) put up the signs mapped one by one in OSM and those the regulation OSM records
# implies. signs_more.plan() adds, by the Swiss rules: curve warnings before the unexpected sharp curves of
# the main roads outside the villages (1.01-1.04), the warnings of the level crossings (1.15 / 1.16), the
# hazards OSM records on a road (1.13, 1.23, 1.24, 1.07) and the parking signs at the entrance of the
# public car parks (4.17). They are drawn by signs_ch.py and put up as signs_net.signs_step does: a grey steel
# pole beside the carriageway, on the right of the traffic that reads them (else on the left), on free
# ground (not on a carriageway, a building or a wall, not within signs_net.CLEAR m of a pole already
# there, the street lamps, delineators, wooden poles and catenary masts of v2.8 included); one with no room
# within 2 m is left out (counted). A sign within SPACING m of one the same traffic
# already reads goes BACK m further back, so that one plate does not hide the other. Their mesh is a new shape
# (art/shapes/props/props_signs_v28.dae, one object in the props/osm group, collision like the other
# poles) with its own materials file for the plates v2.7 does not have; everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish signs_more
# --------------------------------------------------------------------------------------------------

LEVEL = ps.LEVEL
SHAPE = f"{LEVEL}/art/shapes/props/props_signs_v28.dae"
MATERIALS = f"{LEVEL}/art/shapes/props/signs_ch_v28.materials.json"
SPACING = 10.0            # m: a new sign this close to one the same traffic reads already goes back
BACK = 12.0               # m, by this much (once), so that one plate does not hide the other


def existing_poles(z):
    """[(x, y)] of the poles already in the level: those signs_net.existing_props knows, the poles of
    the v2.7 signs (props_signs.dae, mp_ch_pole), and what the v2.8 patches before this one put up (v2_8_posts)."""
    P, _, _ = ps.existing_props(z)
    f = f"{LEVEL}/art/shapes/props/props_signs.dae"
    if f in z.namelist():
        V, N, T, C, parts = ps.read_dae(z.read(f))
        for mat, idx in parts:
            if mat == "mp_ch_pole":
                P = np.concatenate([P, np.unique(np.round(V[idx[:, 0]][:, :2] * 4) / 4, axis=0)])
    return np.concatenate([P, v2_8_posts(z)])


def v2_8_posts(z):
    """(k, 2) of the street lamps and wooden poles (the position of the game model) and of the delineators and
    catenary masts (the vertices of their meshes) that the lamps, roadside and catenary steps put up."""
    import optimize_level
    items = lambda f: [json.loads(l) for l in z.read(f).decode("utf-8").splitlines() if l.strip()]
    mg = f"{LEVEL}/main/MissionGroup"
    out = [np.zeros((0, 2))]
    for g in ("props/street_lights", "props/country_poles"):
        f = f"{mg}/{g}/items.level.json"
        if f in z.NameToInfo:
            out.append(np.array([o["position"][:2] for o in items(f) if o.get("class") == "TSStatic"], float).reshape(-1, 2))
    for g, mat in (("props/delineators", "mp_delineator_white"), ("railway", "mp_catenary_steel")):
        f = f"{mg}/{g}/items.level.json"
        for o in items(f) if f in z.NameToInfo else []:
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in z.NameToInfo:
                continue
            V, _, _, _, parts, _ = optimize_level.parse(z.read(sn).decode("utf-8"))
            W = V[:, :2] + np.asarray(o.get("position", [0, 0, 0]), float)[:2]
            for m, idx in parts:
                if m == mat:
                    out.append(np.unique(np.round(W[idx[:, 0]] * 4) / 4, axis=0))
    return np.concatenate(out)


def signs_more_step(root, report=None):
    t0 = time.time()
    signs = plan()
    print(f"{len(signs)} signs planned: {Counter(s.kind for s in signs)}", flush=True)
    z = bng.LevelFiles(root)
    old_mats = json.loads(z.read(ps.MATERIALS)) if ps.MATERIALS in z.namelist() else {}
    world = ps.World(z, np.array([[s.x, s.y] for s in signs]))
    from scipy.spatial import cKDTree
    pole_xy = [tuple(p) for p in existing_poles(z)]
    tree = cKDTree(np.array(pole_xy)) if pole_xy else None
    mb = bng.MeshBuilder()
    files, mats, made = {}, {}, set()
    rep = {"placed": Counter(), "left_out": Counter(), "outside": Counter(), "signs": []}

    def material_for(code, val):
        key = ps.slug(code, val)
        name = f"mp_{key}"
        if name in old_mats or key in made:
            return name
        p = signs_ch.plate(code, val)
        col, op = ps.rgba_files(p.img)
        files[f"{ps.SIGN_DIR}/{key}_b.color.png"] = col
        files[f"{ps.SIGN_DIR}/{key}_o.data.png"] = op
        S_ = f"/{ps.SIGN_DIR}"
        for m in (bng.material(name, f"{S_}/{key}_b.color.png", roughness=0.35, alpha_test=100, ground_type="METAL",
                               detail={"opacityMap": f"{S_}/{key}_o.data.png"}),
                  bng.material(name + "_back", base_color=[c / 255 for c in ps.GREY_BACK] + [1], roughness=0.5,
                               metallic=0.5, alpha_test=100, ground_type="METAL",
                               detail={"opacityMap": f"{S_}/{key}_o.data.png"})):
            mats[m["name"]] = m
        made.add(key)
        return name

    if "mp_ch_pole" not in old_mats:
        m = bng.material("mp_ch_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6)
        mats[m["name"]] = m
    seen = []                                              # (x, y, travel direction) of the signs up
    if os.path.exists(V27):
        for o in json.load(open(V27, encoding="utf-8")).get("signs", []):
            seen.append((o["x"], o["y"], -np.asarray(o["facing"], float)))
    rep["moved_back"] = 0
    for s in signs:
        if any(math.hypot(x - s.x, y - s.y) < SPACING and np.dot(u, s.u) > 0.5 for x, y, u in seen):
            s = s._replace(x=s.x - s.u[0] * BACK, y=s.y - s.u[1] * BACK)
            rep["moved_back"] += 1
        p = np.array([s.x, s.y])
        ring = p + np.array([[r * math.cos(a), r * math.sin(a)] for r in (0, 1, 2, 4, 6)
                             for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)])
        if not world.on_carriageway(ring[:, 0], ring[:, 1]).any():
            rep["outside"][s.kind] += 1                    # a road the map does not build
            continue
        c = ps.place(world, s, tree, pole_xy)
        if c is None:
            rep["left_out"][s.kind] += 1
            continue
        z0 = float(world.ground([c[0]], [c[1]])[0])
        low = ps.LOW_VILLAGE if (s.limit or 50) <= 50 else ps.LOW_ROAD
        nrm = -s.u
        plates = [(code, val, signs_ch.plate(code, val, big=s.big)) for code, val in s.plates]
        plates = [q for q in plates if q[2] is not None]
        if not plates:
            continue
        zb = z0 + low
        layout = []
        for code, val, pl in reversed(plates):                 # stacked from the lowest
            layout.append((code, val, pl, zb + pl.h / 2))
            zb += pl.h + ps.GAP
        top = zb - ps.GAP
        Vt = ps.tube(c, z0 - 0.3, top - 0.02)
        mb.add("mp_ch_pole", Vt, uvs=np.zeros((len(Vt), 2)), normals=bng.flat_normals_soup(Vt))
        for code, val, pl, zc in layout:
            mat = material_for(code, val)
            F, uv = ps.plate_quads(c, nrm, zc, pl.w, pl.h)
            mb.add(mat, F, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
            Bk = F[::-1] - np.r_[nrm * 0.006, 0]
            mb.add(mat + "_back", Bk, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))
        pole_xy.append((float(c[0]), float(c[1])))
        tree = cKDTree(np.array(pole_xy))
        seen.append((float(c[0]), float(c[1]), np.asarray(s.u, float)))
        rep["placed"][s.kind] += 1
        rep["signs"].append({"x": round(float(c[0]), 2), "y": round(float(c[1]), 2), "z": round(z0, 2),
                             "facing": [round(float(nrm[0]), 3), round(float(nrm[1]), 3)],
                             "plates": [[a, b] for a, b in s.plates], "kind": s.kind, "osm": s.osm_id})
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "props_signs_v28.dae")
        mb.write_dae(f, name="props_signs_v28")
        files[SHAPE] = open(f, "rb").read()
    files[MATERIALS] = json.dumps(mats, indent=1).encode("utf-8")
    group_file = f"{LEVEL}/main/MissionGroup/props/osm/items.level.json"
    obj = bng.tsstatic(f"/{SHAPE}", (0, 0, 0), collision=True)
    obj["__parent"] = "osm"
    now = time.localtime()[:6]
    with z.writer() as zo:
        for i in z.infolist():
            n = i.filename
            if n in files:
                raise SystemExit(f"{n} is already in the level: the v2.8 signs are placed once")
            data = z.read(i)
            if n == group_file:
                lines = [l for l in data.decode("utf-8").splitlines() if l.strip()]
                data = ("\n".join(lines + [json.dumps(obj, separators=(",", ":"))]) + "\n").encode("utf-8")
                zo.writestr(zipfile.ZipInfo(n, date_time=now), data, compress_type=i.compress_type)
                continue
            zo.writestr(i, data, compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            # PNGs stored (signs_net.signs_step: a deflated PNG can come out its own size and the game misreads it)
            zo.writestr(zipfile.ZipInfo(n, date_time=now), data,
                        compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
    out = {"planned": dict(Counter(s.kind for s in signs)),
           "placed": dict(rep["placed"]), "placed_total": sum(rep["placed"].values()),
           "left_out": dict(rep["left_out"]), "outside_map": dict(rep["outside"]), "moved_back": rep["moved_back"],
           "new_textures": len(made), "signs": rep["signs"]}
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(out, open(report, "w"), indent=1)
    print({k: v for k, v in out.items() if k != "signs"})
    print(f"written in {time.time() - t0:.0f} s")
    return 0
