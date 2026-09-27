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
from config import DATA, WORK, wgs_to_local, TER_HALF
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


def build(scene, hfn):
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
        if np.abs(P).max() > TER_HALF - 5:
            P = P[(np.abs(P) < TER_HALF - 5).all(1)]
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
