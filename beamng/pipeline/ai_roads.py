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
from config import DATA, WORK, wgs_to_local, TER_X0, TER_Y0, TER_X1, TER_Y1
import bng
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


def network_roads(scene, g, net, main_zone):
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
        if s.get("ban"):
            drive = min(drive, BANNED)
            n_ban += 1
        width = np.clip(net.w[a + idx], 2.5, 12.0)
        nodes = [[float(net.x[a + i]), float(net.y[a + i]), float(net.z[a + i]) + 0.1, float(w_)]
                 for i, w_ in zip(idx, width)]
        o = {"name": f"tlm_{s['id']}", "class": "DecalRoad", "persistentId": bng.pid(), "position": nodes[0][:3],
             "drivability": round(drive, 2), "improvedSpline": True, "material": "road_invisible", "nodes": nodes}
        d = ow.get(s["id"], 0)
        if d:                                        # one-way: the nodes in the direction of travel
            if d < 0:
                o["nodes"] = nodes[::-1]
                o["position"] = o["nodes"][0][:3]
            o["oneWay"] = True
            o["lanesLeft"], o["lanesRight"] = 0, 1
        scene.add(g, o)
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
    scene.add(g, {"name": "strada_cantonale", "class": "DecalRoad", "persistentId": bng.pid(),
                  "position": nodes[0][:3], "drivability": 1, "improvedSpline": True, "material": "road_invisible",
                  "nodes": nodes, "lanesLeft": 1, "lanesRight": 1})
    main_line = shapely.LineString(np.column_stack([cx, cy]))
    main_zone = main_line.buffer(4.0)
    if net is not None:                       # v2.0: the swissTLM3D network of the whole area
        print("AI roads", 1 + network_roads(scene, g, net, main_zone))
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
