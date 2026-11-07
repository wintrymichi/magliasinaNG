"""AI / traffic road network as invisible DecalRoads (BeamNG builds its navgraph from them).

Main route: the measured carriageway centre line and width (road_profile.npz); where that line
runs along a wall between two paved surfaces (the Street View track left the carriageway, e.g.
~1.25 km from Magliaso), its nodes move sideways onto one surface (keep_to_surface).
Other roads: OSM drivable ways (topology, one-way, class) whose nodes are moved to the
centre of the surveyed carriageway (MU 'strada_sentiero'): a perpendicular ray pair
finds both edges within 8 m; width = edge distance. Ways duplicating the main route are
skipped. Heights follow the road surface.
"""
import json, os, pickle
import numpy as np
import shapely
from scipy.ndimage import gaussian_filter1d, median_filter
from config import DATA, WORK, ZONE, wgs_to_local, TER_X0, TER_Y0, TER_X1, TER_Y1
import bng
import osm
from clearance import keep_to_surface

DRIVE = {"secondary": 1.0, "secondary_link": 1.0, "tertiary": 1.0, "tertiary_link": 1.0, "unclassified": 0.8,
         "residential": 0.8, "living_street": 0.6, "service": 0.4, "track": 0.2}
DEFAULT_W = {"secondary": 6.5, "tertiary": 6.0, "unclassified": 5.0, "residential": 5.0, "living_street": 4.0,
             "service": 3.5, "track": 3.0}


def densify(P, step):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if d[-1] < 1e-6:
        return P
    s = np.linspace(0, d[-1], max(2, int(np.ceil(d[-1] / step)) + 1))
    return np.column_stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])])


def recentre(P, road, maxw=8.0):
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.column_stack([-T[:, 1], T[:, 0]])
    tt = np.arange(0, maxw, 0.1)
    out, W = P.copy(), np.full(len(P), np.nan)
    for sg in (1, -1):
        pts = P[:, None, :] + sg * N[:, None, :] * tt[None, :, None]
        inside = shapely.contains_xy(road, pts[..., 0], pts[..., 1])
        first_out = np.argmax(~inside, axis=1).astype(float)
        first_out[inside.all(1)] = np.nan
        first_out[~inside[:, 0]] = np.nan                     # node not on the carriageway at all
        if sg == 1:
            eL = first_out * 0.1
        else:
            eR = first_out * 0.1
    ok = ~np.isnan(eL) & ~np.isnan(eR)
    mid = np.where(ok, (eL - eR) / 2, 0.0)
    W[ok] = (eL + eR)[ok]
    mid = median_filter(mid, 5, mode="nearest")
    out = P + N * mid[:, None]
    return out, W


# swissTLM3D class -> drivability for the AI (v2.0 network)
TLM_DRIVE = {"10m Strasse": 1.0, "8m Strasse": 1.0, "6m Strasse": 1.0, "Autostrasse": 1.0, "Ausfahrt": 0.9,
             "Einfahrt": 0.9, "Verbindung": 0.9, "4m Strasse": 0.8, "Platz": 0.5, "Raststaette": 0.5,
             "3m Strasse": 0.5, "Zufahrt": 0.4, "Dienstzufahrt": 0.3}
# The motorways (swissTLM3D Autobahn, one line per carriageway) had no AI road: none crossed the Malcantone, and in the
# Ticino zones their carriageways stood without traffic, paint (markings_rules draws on the AI roads) or guard rails
# (2026-10-28). Only in a zone, so the Malcantone's own build does not change.
MOTORWAY = {"Autobahn": 120, "Autostrasse": 100}       # km/h, the Swiss limits
if ZONE:
    TLM_DRIVE["Autobahn"] = 1.0
MOTORWAY_LANE_W, MOTORWAY_SHOULDER = 3.75, 2.5    # m: lanes of a carriageway beside its hard shoulder


BANNED = 0.1           # drivability of the roads closed to general traffic (swissTLM3D)
OSM_SHARE = 0.6        # share of a line's samples that must lie along OSM roads to take their direction
OSM_AGREE = 0.7        # share of those that must agree on it


def roundabout_dir(net, s):
    """+1 when the stations of segment s run counter-clockwise around the middle of its roundabout
    (swissTLM3D KREISEL; Swiss roundabouts turn counter-clockwise), -1 when they run clockwise."""
    ring = [q for q in net.segs if q.get("roundabout")]
    a, n = s["first"], s["n"]
    P = np.column_stack([net.x[a:a + n], net.y[a:a + n]])
    # the other pieces of the same roundabout: the roundabout segments within 60 m
    pts = np.concatenate([np.column_stack([net.x[q["first"]:q["first"] + q["n"]], net.y[q["first"]:q["first"] + q["n"]]])
                          for q in ring])
    near = pts[np.hypot(pts[:, 0] - P[:, 0].mean(), pts[:, 1] - P[:, 1].mean()) < 60.0]
    c = near.mean(0)
    v = P - c
    t = np.gradient(P, axis=0)
    turn = np.sum(v[:, 0] * t[:, 1] - v[:, 1] * t[:, 0])
    return 1 if turn > 0 else -1


def separated_dir(net, s, reach=40.0):
    """Direction of one carriageway of a road drawn as two lines (swissTLM3D RICHTUNGSG): traffic
    keeps to the right, so the other carriageway lies on the left of the direction of travel. +1
    when the nearest parallel line of the pair lies on the left of the stations' direction, -1 when
    on the right, 0 when there is none within `reach` m."""
    import shapely
    a, n = s["first"], s["n"]
    P = np.column_stack([net.x[a:a + n], net.y[a:a + n]])
    if "_sep" not in net.__dict__:
        ids = [q["id"] for q in net.segs if q.get("separated")]
        net._sep = (ids, shapely.STRtree([shapely.LineString(np.column_stack(
            [net.x[net.segs[k]["first"]:net.segs[k]["first"] + net.segs[k]["n"]],
             net.y[net.segs[k]["first"]:net.segs[k]["first"] + net.segs[k]["n"]]])) for k in ids]))
    ids, tree = net._sep
    votes = []
    T = np.gradient(P, axis=0)
    for k in range(0, n, max(1, n // 8)):
        p = shapely.Point(P[k])
        for j in tree.query(p, predicate="dwithin", distance=reach):
            q = net.segs[ids[j]]
            if q["id"] == s["id"]:
                continue
            Q = np.column_stack([net.x[q["first"]:q["first"] + q["n"]], net.y[q["first"]:q["first"] + q["n"]]])
            m = int(np.argmin(np.hypot(*(Q - P[k]).T)))
            tq = Q[min(m + 1, len(Q) - 1)] - Q[max(m - 1, 0)]
            cs = abs(tq @ T[k]) / max(np.hypot(*tq) * np.hypot(*T[k]), 1e-9)
            if cs < np.cos(np.radians(30)):
                continue
            v = Q[m] - P[k]
            votes.append((np.hypot(*v), 1 if T[k, 0] * v[1] - T[k, 1] * v[0] > 0 else -1))
    if not votes:
        return 0
    votes.sort()
    near = [v for d, v in votes[:max(3, len(votes) // 3)]]
    return 1 if sum(near) > 0 else -1


def one_ways(net):
    """Direction of travel of every drivable line: +1 along its stations, -1 against, 0 both ways.
    Roundabouts from swissTLM3D (counter-clockwise); roads drawn as two carriageways (swissTLM3D
    RICHTUNGSG) by keeping to the right; the rest from the OSM roads along the line (oneway=*,
    roundabouts, motorways): at least OSM_SHARE of its samples within 6 m of OSM roads running the
    same way, OSM_AGREE of those one-way in the same direction."""
    import osm
    out = {}
    if not osm.available():
        print("no OSM data (download_osm.py): every AI road runs both ways")
        ways = []
    else:
        ways = [w for w in osm.load()[0] if w["tags"].get("highway") in osm.DRIVE]
    stats = {"roundabout": 0, "separated": 0, "osm": 0}
    for s in net.segs:
        if s["kind"] != "road" or s["class"] not in TLM_DRIVE:
            continue
        if s.get("roundabout"):
            out[s["id"]] = roundabout_dir(net, s)
            stats["roundabout"] += 1
            continue
        if s.get("separated"):
            d = separated_dir(net, s)
            if d:
                out[s["id"]] = d
                stats["separated"] += 1
                continue
        if not ways:
            continue
        a, n = s["first"], s["n"]
        P = np.column_stack([net.x[a:a + n], net.y[a:a + n]])
        idx, sgn = osm.match_lines(P, ways)
        m = idx >= 0
        if m.sum() < max(1, OSM_SHARE * len(idx)):
            continue
        d = np.array([osm.oneway_dir(ways[i]["tags"]) for i in idx[m]]) * sgn[m]
        vals, cnt = np.unique(d, return_counts=True)
        best = vals[np.argmax(cnt)]
        if best != 0 and cnt.max() >= OSM_AGREE * m.sum():
            out[s["id"]] = int(best)
            stats["osm"] += 1
    print("one-way AI roads:", stats)
    return out


def network_roads(out, net, main_zone):
    """Every drivable swissTLM3D line of the network (not paths) as an AI road on the network
    surface (bridge decks included); lines along the main route are left to it. One-way roads
    (one_ways) run in their direction of travel; roads closed to general traffic (swissTLM3D:
    general traffic ban, not passable by car) keep a low drivability, so the traffic avoids them."""
    n = 0
    ow = one_ways(net)
    json.dump({str(k): v for k, v in ow.items()}, open(os.path.join(WORK, "ai_oneways.json"), "w"))
    n_ban = 0
    for s in net.segs:
        if s["kind"] != "road" or s["class"] not in TLM_DRIVE:
            continue
        a, k = s["first"], s["n"]
        P = np.column_stack([net.x[a:a + k], net.y[a:a + k]])
        line = shapely.LineString(P)
        # short links stay (a junction of two 3 m pieces would break the AI network otherwise)
        if k < 2 or line.intersection(main_zone).length > 0.8 * line.length:
            continue
        step = max(1, int(round(4.0 / 2.0)))                   # every ~4 m, ends kept
        idx = np.unique(np.r_[np.arange(0, k, step), k - 1])
        drive = TLM_DRIVE[s["class"]] * (0.6 if s["surface"] == "natural" else 1.0)
        gated = bool(s.get("ban"))
        if gated:
            drive = min(drive, BANNED)
            n_ban += 1
        width = np.clip(net.w[a + idx], 2.5, 12.0)
        nodes = [[float(net.x[a + i]), float(net.y[a + i]), float(net.z[a + i]) + 0.1, float(w_)]
                 for i, w_ in zip(idx, width)]
        o = {"name": f"tlm_{s['id']}", "class": "DecalRoad", "persistentId": bng.pid(), "position": nodes[0][:3],
             "drivability": round(drive, 2), "improvedSpline": True, "material": "road_invisible", "nodes": nodes}
        if gated:                                    # the traffic keeps out (map.lua: a private road)
            o["gatedRoad"] = True
        d = ow.get(s["id"], 0)
        if d:                                        # one-way: the nodes in the direction of travel
            if d < 0:
                o["nodes"] = nodes[::-1]
                o["position"] = o["nodes"][0][:3]
            o["oneWay"] = True
            o["lanesLeft"], o["lanesRight"] = 0, 1
            if ZONE and s["class"] in MOTORWAY:          # a carriageway of two (or more) lanes
                o["lanesRight"] = int(np.clip(round((np.median(width) - MOTORWAY_SHOULDER) / MOTORWAY_LANE_W), 1, 3))
                o["autoLanes"] = False
        o["_class"], o["_natural"], o["_banned"] = s["class"], s["surface"] == "natural", bool(s.get("ban"))
        o["_ring"] = bool(s.get("roundabout"))
        out.append(o)
        n += 1
    print("AI roads closed to general traffic (drivability %.1f): %d" % (BANNED, n_ban))
    return n


def build(scene, hfn, net=None):
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    road = shapely.union_all([g for g, _ in av["LCSF"].get("strada_sentiero", [])]).buffer(0.05)
    shapely.prepare(road)
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    g = "MissionGroup/AIRoads"
    # main route
    C = rp["center"]
    cx, cy = gaussian_filter1d(C[:, 0], 3), gaussian_filter1d(C[:, 1], 3)
    idx = np.arange(0, len(cx), 10)                            # every 5 m
    w = np.clip(median_filter(rp["width"], 21)[idx], 4.5, 9.0)
    import roadheight
    S = roadheight.load()
    Pm, z, off = keep_to_surface(np.column_stack([cx[idx], cy[idx]]), hfn, lambda x, y: S.distance(x, y) < 0.4)
    print("main route: %d nodes moved sideways onto one surface (max %.1f m)" % (int((off != 0).sum()), np.abs(off).max()))
    nodes = [[float(a), float(b), float(c) + 0.1, float(d)] for (a, b), c, d in zip(Pm, z, w)]
    out = [{"name": "strada_cantonale", "class": "DecalRoad", "persistentId": bng.pid(),
            "position": nodes[0][:3], "drivability": 1, "improvedSpline": True, "material": "road_invisible",
            "nodes": nodes, "lanesLeft": 1, "lanesRight": 1, "_class": "6m Strasse"}]
    main_line = shapely.LineString(np.column_stack([cx, cy]))
    main_zone = main_line.buffer(4.0)
    if ZONE and not ((cx >= TER_X0) & (cx <= TER_X1) & (cy >= TER_Y0) & (cy <= TER_Y1)).all():
        # the Malcantone's Street View route is no road of a zone (it stood km out of every zone's terrain and
        # poles.roadside_step crashed on it): the network's own lines take its place
        out, main_zone = [], shapely.Polygon()
    if net is not None:                       # v2.0: the swissTLM3D network of the whole area
        print("AI roads", 1 + network_roads(out, net, main_zone))
        if not out:                           # a zone with no road at all (ti_m3_1): an empty group for the readers
            scene.group(g)
            json.dump({}, open(os.path.join(WORK, "ai_network.json"), "w"))
            return
        rep = traffic_ready(out)
        json.dump(rep, open(os.path.join(WORK, "ai_network.json"), "w"), indent=1)
        for o in out:
            scene.add(g, o)
        return
    osm = json.load(open(os.path.join(DATA, "osm", "osm.json")))
    n_roads = 1
    for e in osm["elements"]:
        if e["type"] != "way":
            continue
        tags = e.get("tags", {})
        hw = tags.get("highway")
        if hw not in DRIVE or "geometry" not in e:
            continue
        if tags.get("access") in ("no", "private") and hw in ("service", "track"):
            continue
        P = np.array([wgs_to_local(q["lat"], q["lon"]) for q in e["geometry"]])
        inside = (P[:, 0] > TER_X0 + 5) & (P[:, 0] < TER_X1 - 5) & (P[:, 1] > TER_Y0 + 5) & (P[:, 1] < TER_Y1 - 5)
        P = P[inside]
        if len(P) < 2:
            continue
        line = shapely.LineString(P)
        if line.length < 8 or line.intersection(main_zone).length > 0.8 * line.length:
            continue
        P = densify(P, 4.0)
        Pc, W = recentre(P, road)
        width = np.where(np.isnan(W), DEFAULT_W.get(hw.split("_")[0], 4.0), np.clip(W, 2.5, 12.0))
        width = median_filter(width, 5, mode="nearest")
        z = hfn(Pc[:, 0], Pc[:, 1])
        nodes = [[float(a), float(b), float(c) + 0.1, float(d)] for (a, b), c, d in zip(Pc, z, width)]
        o = {"name": f"osm_{e['id']}", "class": "DecalRoad", "persistentId": bng.pid(), "position": nodes[0][:3],
             "drivability": DRIVE[hw], "improvedSpline": True, "material": "road_invisible", "nodes": nodes}
        if tags.get("oneway") == "yes":
            o["oneWay"] = True
            o["lanesLeft"], o["lanesRight"] = 0, 1
        scene.add(g, o)
        n_roads += 1
    print("AI roads", n_roads)


# ---------------------------------------------------------------------------------------------- traffic
# v3.0.40: the network as the game's traffic reads it. BeamNG builds its AI graph (map.lua) from the edges
# of the DecalRoads and links two roads only where they share a point; a road that ends a few metres short
# of the road it meets (a short swissTLM3D link left out, a line kept off the main route) is a dead end for
# the traffic, which then turns round or never reaches the villages behind it.
JOIN = 0.5                 # m: road ends this close are one junction already
WELD_GAP = 8.0             # m: the widest gap a road end is joined across to the road it heads to
WELD_SNAP, NODE_SNAP = 1.5, 0.5   # m: a joint this close to the other road's end / one of its nodes takes it
WELD_ANGLE = 50.0          # deg: a road end outside the other carriageway joins it only heading towards it
WELD_DZ, WELD_GRADE = 1.0, 0.15   # m + share of the gap: the height difference allowed (not an overpass)
BACKTRACK = 120.0          # deg: a node turning back on its road this sharply is dropped (spline loop)
MIN_SEG = 0.3              # m: nodes closer than this to the previous one are dropped
W_STEP = 0.5               # m of width change per 4 m at most (the traffic keeps its lane where widths jump)
# Swiss speed limits (km/h) where OSM has none: inside villages 50, outside 80, lower on the narrow and
# service roads; a 30 zone or a mapped limit (OSM maxspeed) wins. The road is split where the limit changes.
LIMIT_VILLAGE, LIMIT_OUT = 50, 80
LIMIT_CLASS = {"4m Strasse": 60, "3m Strasse": 40, "Platz": 20, "Raststaette": 20, "Zufahrt": 30,
               "Dienstzufahrt": 30, "Verbindung": 50, "Ausfahrt": 60, "Einfahrt": 60}
LIMIT_NATURAL, LIMIT_BANNED = 30, 30
LIMIT_RING = 40           # km/h on the ring of a roundabout
LIMIT_MIN_RUN = 100.0      # m: a limit holding for less than this along a road takes its neighbours'
VILLAGE_R, VILLAGE_N = 150.0, 25   # a road point is inside a village (signed 50) with 25 buildings within 150 m
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v * 0


def clean_nodes(o):
    """Drop nodes that repeat the previous one or turn back on the road (a loop of the spline the AI
    graph would follow); a road keeps its two ends."""
    N = np.asarray(o["nodes"], float)
    keep = [0]
    for i in range(1, len(N)):
        if np.hypot(*(N[i, :2] - N[keep[-1], :2])) < MIN_SEG and i < len(N) - 1:
            continue
        keep.append(i)
    changed = True
    while changed and len(keep) > 2:
        changed = False
        for j in range(1, len(keep) - 1):
            a, b, c = N[keep[j - 1], :2], N[keep[j], :2], N[keep[j + 1], :2]
            u, v = _unit(b - a), _unit(c - b)
            if u @ v < np.cos(np.radians(BACKTRACK)):
                del keep[j]
                changed = True
                break
    # a hook at an end (the road's first metres turning back on it): the end goes
    for _ in range(2):
        keep = keep[::-1]
        while len(keep) >= 3:
            a, b = N[keep[0], :2], N[keep[1], :2]
            far = next((N[k, :2] for k in keep[2:] if np.hypot(*(N[k, :2] - b)) >= 6.0), N[keep[-1], :2])
            if _unit(b - a) @ _unit(far - b) < -0.3:
                del keep[0]
            else:
                break
    n = len(N) - len(keep)
    o["nodes"] = [list(map(float, N[i])) for i in keep]
    o["position"] = o["nodes"][0][:3]
    return n


def smooth_widths(o):
    """Widths without the jumps of the survey (a junction's mouth, a lay-by): median over 5 nodes, then at
    most W_STEP of change per 4 m, both ways."""
    N = np.asarray(o["nodes"], float)
    if len(N) < 3:
        return 0
    w0 = N[:, 3].copy()
    w = median_filter(w0, 5, mode="nearest")
    d = np.r_[0, np.linalg.norm(np.diff(N[:, :2], axis=0), axis=1)]
    lim = W_STEP * np.maximum(d, 0.5) / 4.0
    for _ in range(2):
        for i in range(1, len(w)):
            w[i] = min(w[i], w[i - 1] + lim[i])
        for i in range(len(w) - 2, -1, -1):
            w[i] = min(w[i], w[i + 1] + lim[i + 1])
    w = np.maximum(w, 2.5)
    N[:, 3] = np.round(w, 2)
    o["nodes"] = [list(map(float, r)) for r in N]
    return int((np.abs(np.diff(w0)) > 2).sum())


def _nearest_on(N, p):
    """Nearest point of the polyline N (n, >=2) to p: (distance, segment index, fraction along it)."""
    A, B = N[:-1, :2], N[1:, :2]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    t = np.clip(((p - A) * AB).sum(1) / L2, 0, 1)
    Q = A + AB * t[:, None]
    d = np.hypot(*(Q - p).T)
    i = int(np.argmin(d))
    return float(d[i]), i, float(t[i])


def weld(roads):
    """Join every road end that no other road shares to the road it heads to, within WELD_GAP m and at its
    height: onto that road's end or node within WELD_SNAP m, else onto a node added to it there. The end
    moves onto the joint when it is within 1 m of it, otherwise the road gets one more node there."""
    from scipy.spatial import cKDTree
    lines = [shapely.LineString(np.asarray(o["nodes"])[:, :2]) for o in roads]
    tree = shapely.STRtree(lines)

    def node_tree():
        P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
        own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
        return cKDTree(P), own
    nt, nown = node_tree()
    stats = {"snap_end": 0, "snap_node": 0, "new_node": 0, "moved": 0, "extended": 0, "dead": 0}
    gaps = []
    for ia, oa in enumerate(roads):
        for end in (0, -1):
            NA = np.asarray(oa["nodes"], float)
            e = NA[end]
            shared = [k for k in nt.query_ball_point(e[:2], JOIN) if nown[k] != ia]
            if shared:
                continue
            # the direction the road leaves its end, from a node at least 3 m back
            back = NA[::-1] if end == -1 else NA
            far = back[min(len(back) - 1, 1)]
            for q in back[1:]:
                far = q
                if np.hypot(*(q[:2] - e[:2])) >= 3.0:
                    break
            t = _unit(e[:2] - far[:2])
            best = None
            for jb in tree.query(shapely.Point(e[:2]).buffer(WELD_GAP)):
                if jb == ia:
                    continue
                NB = np.asarray(roads[jb]["nodes"], float)
                d, si, fr = _nearest_on(NB, e[:2])
                if d > WELD_GAP:
                    continue
                q = NB[si] + (NB[si + 1] - NB[si]) * fr
                if abs(q[2] - e[2]) > WELD_DZ + WELD_GRADE * d:
                    continue
                if d > q[3] / 2 + 0.5 and t @ _unit(q[:2] - e[:2]) < np.cos(np.radians(WELD_ANGLE)):
                    continue
                if best is None or d < best[0]:
                    best = (d, jb, si, fr, q)
            if best is None:
                stats["dead"] += 1
                continue
            d, jb, si, fr, q = best
            NB = roads[jb]["nodes"]
            # onto the other road's end, or one of its nodes, when close; else a new node of that road
            cand = [(np.hypot(*(np.asarray(NB[k][:2]) - q[:2])), k) for k in (si, si + 1)]
            dk, k = min(cand)
            # B's end when the nearest point is that end (the two roads meet end to end); otherwise a T onto B
            # and B's stub past it is cut back if it leads nowhere (cut_spurs)
            at_end = (si == 0 and fr < 1e-6) or (si == len(NB) - 2 and fr > 1 - 1e-6)
            if dk <= (WELD_SNAP if at_end else NODE_SNAP):
                tgt = list(NB[k])
                stats["snap_end" if k in (0, len(NB) - 1) else "snap_node"] += 1
            else:
                tgt = [float(v) for v in q]
                NB.insert(si + 1, tgt)
                stats["new_node"] += 1
            joint = [tgt[0], tgt[1], tgt[2], float(e[3])]
            gaps.append(float(np.hypot(*(np.asarray(tgt[:2]) - e[:2]))))
            if gaps[-1] <= 1.0 or len(oa["nodes"]) < 2:
                oa["nodes"][end] = joint
                stats["moved"] += 1
            elif end == -1:
                oa["nodes"].append(joint)
                stats["extended"] += 1
            else:
                oa["nodes"].insert(0, joint)
                stats["extended"] += 1
            oa["position"] = oa["nodes"][0][:3]
            lines[ia] = shapely.LineString(np.asarray(oa["nodes"])[:, :2])
            nt, nown = node_tree()
    stats["gap_max"] = round(max(gaps), 2) if gaps else 0
    return stats


SPUR = 12.0               # m: a dead end this short past a junction of its road is cut back to the junction


def cut_spurs(roads):
    """Cut a road's dead end back to its last junction when it runs on at most SPUR m past it (a road
    joined a few metres before its end by weld(), the main route past its roundabout): the traffic would
    drive into the stub and turn round there."""
    from scipy.spatial import cKDTree
    P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
    t = cKDTree(P)
    n = 0
    for i, o in enumerate(roads):
        for end in (0, -1):
            N = np.asarray(o["nodes"], float)
            if len(N) < 3 or any(own[k] != i for k in t.query_ball_point(N[end, :2], 0.05)):
                continue
            seq = range(1, len(N) - 1) if end == 0 else range(len(N) - 2, 0, -1)
            run = 0.0
            prev = N[end, :2]
            for k in seq:
                run += np.hypot(*(N[k, :2] - prev))
                prev = N[k, :2]
                if run > SPUR:
                    break
                if any(own[j] != i for j in t.query_ball_point(N[k, :2], 0.05)):
                    o["nodes"] = o["nodes"][k:] if end == 0 else o["nodes"][:k + 1]
                    o["position"] = o["nodes"][0][:3]
                    n += 1
                    break
    return n


def pieces(roads):
    """Piece of the network of every road (roads linked where they share a point within 5 cm) and the
    largest piece."""
    from scipy.spatial import cKDTree
    P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
    par = list(range(len(roads)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in cKDTree(P).query_pairs(0.05):
        ra, rb = find(own[a]), find(own[b])
        if ra != rb:
            par[ra] = rb
    comp = np.array([find(i) for i in range(len(roads))])
    L = np.array([shapely.LineString(np.asarray(o["nodes"])[:, :2]).length for o in roads])
    km = {c: L[comp == c].sum() / 1000 for c in set(comp)}
    return comp, max(km, key=km.get), km, L


def gate_cut_off(roads):
    """The roads of the pieces the traffic cannot reach from the rest (a farm road met only by a path) as
    private (gatedRoad): the traffic does not start there and loop on them; an AI sent there still drives them."""
    comp, main, _, _ = pieces(roads)
    n = 0
    for i, o in enumerate(roads):
        if comp[i] != main and not o.get("gatedRoad"):
            o["gatedRoad"] = True
            n += 1
    return n


def graph_report(roads):
    """The network as the traffic sees it: roads linked where they share a point (within 5 cm); the
    pieces that do not reach the largest one, the dead ends left, the km of each piece."""
    from scipy.spatial import cKDTree
    P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
    par = list(range(len(roads)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in cKDTree(P).query_pairs(0.05):
        ra, rb = find(own[a]), find(own[b])
        if ra != rb:
            par[ra] = rb
    L = np.array([shapely.LineString(np.asarray(o["nodes"])[:, :2]).length for o in roads])
    comp = np.array([find(i) for i in range(len(roads))])
    km = {c: L[comp == c].sum() / 1000 for c in set(comp)}
    main = max(km, key=km.get)
    ends = np.array([np.asarray(o["nodes"])[e, :2] for o in roads for e in (0, -1)])
    t = cKDTree(P)
    dead = sum(1 for p in ends if len(t.query_ball_point(p, 0.05)) == 1)
    drv = np.array([o["drivability"] for o in roads])
    return {"roads": len(roads), "km": round(L.sum() / 1000, 1), "pieces": len(km),
            "km_main_piece": round(km[main], 1),
            "km_off_main": round(sum(v for c, v in km.items() if c != main), 1),
            "km_off_main_drivable": round(L[(comp != main) & (drv >= 0.5)].sum() / 1000, 1),
            "pieces_off_main_over_500m": sum(1 for c, v in km.items() if c != main and v > 0.5),
            "dead_ends": dead}


def _limits_along(o, cls, natural, banned, ring, ways, gtree):
    """Speed limit (km/h) per node of a road."""
    import signs_net
    N = np.asarray(o["nodes"], float)
    P = N[:, :2]
    lim = np.full(len(P), float(LIMIT_OUT))
    if ZONE and cls in MOTORWAY:                   # no village on a motorway: its own limit, OSM may lower it
        lim[:] = MOTORWAY[cls]
    elif gtree is not None:
        village = gtree.query_ball_point(P, VILLAGE_R, return_length=True) >= VILLAGE_N
        lim[village] = LIMIT_VILLAGE
    cap = LIMIT_CLASS.get(cls)
    if cap:
        lim = np.minimum(lim, cap)
    if natural:
        lim = np.minimum(lim, LIMIT_NATURAL)
    if banned:
        lim = np.minimum(lim, LIMIT_BANNED)
    if ring:
        lim = np.minimum(lim, LIMIT_RING)
    if ways and len(P) >= 2 and shapely.LineString(P).length > 1:
        idx, _ = osm.match_lines(P, ways)
        if len(idx):
            L = shapely.LineString(P)
            d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
            s = (np.arange(len(idx)) + 0.5) * L.length / len(idx)
            k = np.clip(np.searchsorted(s, d), 0, len(idx) - 1)
            for i in range(len(P)):
                j = idx[k[i]]
                if j < 0:
                    continue
                tg = ways[j]["tags"]
                v = signs_net._limit(tg)
                if signs_net._zone(tg) == "30":
                    v = 30
                if v and 5 <= v <= 120:
                    lim[i] = max(v, 20)          # walking pace and 10 km/h signs: the traffic at 20
    # short runs take the neighbours' limit
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    for _ in range(3):
        runs, a = [], 0
        for i in range(1, len(lim) + 1):
            if i == len(lim) or lim[i] != lim[a]:
                runs.append((a, i))
                a = i
        if len(runs) < 2:
            break
        for r, (a, b) in enumerate(runs):
            if d[b - 1] - d[a] < LIMIT_MIN_RUN:
                nb = runs[r - 1] if r > 0 else runs[r + 1]
                lim[a:b] = lim[nb[0]]
    return lim


def speed_limits(roads, classes):
    """Every road its Swiss speed limit (DecalRoad field speedLimit, m/s; the traffic drives at it), split
    where the limit changes (the pieces share their end node)."""
    import gzip
    try:
        ways = [w for w in osm.load()[0] if w["tags"].get("highway") in osm.DRIVE] if osm.available() else []
    except Exception:
        ways = []
    from scipy.spatial import cKDTree
    gwr = json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz")))["buildings"]
    G = np.array([[b["x"], b["y"]] for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or 30) >= 30])
    gtree = cKDTree(G) if len(G) else None
    out, km = [], {}
    for o, (cls, natural, banned, ring) in zip(roads, classes):
        lim = _limits_along(o, cls, natural, banned, ring, ways, gtree)
        N = o["nodes"]
        cut = [0] + [i for i in range(1, len(N)) if lim[i] != lim[i - 1]] + [len(N) - 1]
        cut = sorted(set(cut))
        for p, (a, b) in enumerate(zip(cut[:-1], cut[1:])):
            q = dict(o) if p == 0 else {**o, "name": "%s_%d" % (o["name"], p), "persistentId": bng.pid()}
            q["nodes"] = [list(n) for n in N[a:b + 1]]
            q["position"] = q["nodes"][0][:3]
            v = int(lim[a])
            q["speedLimit"] = round(v / 3.6, 2)
            L = shapely.LineString(np.asarray(q["nodes"])[:, :2]).length
            km[v] = km.get(v, 0) + L / 1000
            out.append(q)
    return out, {str(k): round(v, 1) for k, v in sorted(km.items())}


TWO_LANES = 4.5    # m: a two-way road this wide (most of its length) has a lane each way; narrower: one lane


def lanes(roads):
    """The lanes of the two-way roads. Left to the game (autoLanes), a road gets one lane until 5.4 m
    (numLanes = floor(width / 3.61 + 0.5), map.lua of 0.40), so on 4.5-5.4 m roads two cars meeting
    each other drive in the middle; from TWO_LANES they keep to their own lane."""
    n = 0
    for o in roads:
        if o.get("oneWay") or "lanesLeft" in o and o.get("autoLanes") is False:
            continue
        w = np.asarray(o["nodes"], float)[:, 3]
        if len(w) and np.percentile(w, 20) >= TWO_LANES:
            o["autoLanes"], o["lanesLeft"], o["lanesRight"] = False, 1, 1
            n += 1
    return n


def traffic_ready(roads):
    """Clean, weld and limit the AI roads in place (the list is replaced); the report of the network."""
    rep = {"before": graph_report(roads)}
    rep["dropped_nodes"] = sum(clean_nodes(o) for o in roads)
    rep["width_jumps_smoothed"] = sum(smooth_widths(o) for o in roads)
    rep["weld"] = weld(roads)
    rep["spurs_cut"] = cut_spurs(roads)
    rep["two_lane_roads"] = lanes(roads)
    classes = [(o.pop("_class", None), o.pop("_natural", False), o.pop("_banned", False), o.pop("_ring", False))
               for o in roads]
    new, rep["km_per_limit"] = speed_limits(roads, classes)
    roads[:] = new
    rep["cut_off_gated"] = gate_cut_off(roads)
    rep["after"] = graph_report(roads)
    print("AI network for the traffic:", json.dumps(rep))
    return rep


def review(level, out_dir):
    """Report and map of the AI network of a built level (the roads, the pieces the traffic cannot leave, the
    dead ends, the speed limits, the stop and give-way points): out_dir/ai_network.json and .png.
        python ai_roads.py --review <level folder> <out dir>"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    f = os.path.join(level, "main", "MissionGroup", "AIRoads", "items.level.json")
    roads = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    rep = graph_report(roads)
    lim = {}
    for o in roads:
        v = round(float(o.get("speedLimit", 0)) * 3.6)
        lim[v] = lim.get(v, 0) + shapely.LineString(np.asarray(o["nodes"])[:, :2]).length / 1000
    rep["km_per_limit"] = {str(k): round(v, 1) for k, v in sorted(lim.items())}
    rep["one_way"] = sum(1 for o in roads if o.get("oneWay"))
    rep["gated"] = sum(1 for o in roads if o.get("gatedRoad"))
    sig = os.path.join(level, "signals.json")
    S = json.load(open(sig)) if os.path.exists(sig) else {"instances": [], "controllers": []}
    kind = {c["id"]: c["name"] for c in S["controllers"]}
    rep["signals"] = {}
    for i in S["instances"]:
        rep["signals"][kind[i["controllerId"]]] = rep["signals"].get(kind[i["controllerId"]], 0) + 1
    # every signal point within 3 m of an AI road (map.lua matches it to the nearest road)
    lines = [shapely.LineString(np.asarray(o["nodes"])[:, :2]) for o in roads]
    tree = shapely.STRtree(lines)
    far = 0
    for i in S["instances"]:
        p = shapely.Point(i["pos"][:2])
        j = tree.nearest(p)
        far += lines[j].distance(p) > 3.0
    rep["signals_off_road"] = int(far)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(rep, open(os.path.join(out_dir, "ai_network.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
    # the map: roads by speed limit, the pieces off the main one in red, signals as dots
    from scipy.spatial import cKDTree
    P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
    par = list(range(len(roads)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in cKDTree(P).query_pairs(0.05):
        ra, rb = find(own[a]), find(own[b])
        if ra != rb:
            par[ra] = rb
    comp = np.array([find(i) for i in range(len(roads))])
    L = np.array([l.length for l in lines])
    km = {c: L[comp == c].sum() for c in set(comp)}
    main = max(km, key=km.get)
    col = {20: "#7b3294", 30: "#c2a5cf", 40: "#a6dba0", 50: "#008837", 60: "#fdb863", 70: "#e66101", 80: "#b2182b"}
    fig, ax = plt.subplots(figsize=(18, 18))
    segs = [np.asarray(o["nodes"])[:, :2] for o in roads]
    c = [("red" if comp[i] != main else col.get(round(float(o.get("speedLimit", 0)) * 3.6), "#888"))
         for i, o in enumerate(roads)]
    ax.add_collection(LineCollection(segs, colors=c, linewidths=[2.5 if comp[i] != main else 0.8 for i in range(len(roads))]))
    for i in S["instances"]:
        ax.plot(i["pos"][0], i["pos"][1], "o", ms=2.5, color="black" if kind[i["controllerId"]] == "stop" else "blue")
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title("AI roads by speed limit (km/h: purple 20, lilac 30, light green 40, green 50, orange 60/70, dark red 80), "
                 "red = cut off from the network; dots: STOP black, give way blue", fontsize=10)
    fig.savefig(os.path.join(out_dir, "ai_network.png"), dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--review"]:
        review(sys.argv[2], sys.argv[3])
