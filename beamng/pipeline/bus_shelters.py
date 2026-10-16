"""Bus shelters with their bench (v3.1), in the built level.

Up to v3.0 a bus stop of the map was its pole with the yellow sign (props_osm.py); only the 38 stops where
OpenStreetMap records a shelter (shelter=yes) had one, drawn there. Most stops of the area have no shelter tag at
all, and in the villages they looked like a pole on an empty verge. Here every bus stop OpenStreetMap does not mark
as without a shelter (shelter=no) and that has none yet gets the game's own shelter (Italy's: a steel frame,
glazed back and sides, the bench inside, SHELTER_LEN x SHELTER_DEPTH m) beside the road:
- its back to the land, its open side to the road, set back FRONT_GAP m from the edge of the asphalt, along the
  road, a few metres from the pole (ALONG m on either side, the first place that fits);
- only where it fits: not on an AI road's lane, a building, a wall, a lamp, a bin or a bench (parking.obstacles),
  on ground no steeper than MAX_TILT across it, never on the Italian side (outside the cadastral survey: stops
  there are left as they are).
TSStatics in MissionGroup/props/bus_shelters (collision: a car hits it). The stops with shelter=yes keep the
shelter props_osm.py drew. Everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish bus_shelters
"""
import json, math, os, time
import numpy as np
import shapely
from scipy.spatial import cKDTree
import bng
import osm
import parking
from config import LEVEL_NAME
from markings_net import read_items, shape_tris, up_faces
from road_mesh import TriSurface

MODEL = "/levels/italy/art/shapes/buildings/italy_city_busstop.dae"   # open side to local -y, x along
SHELTER_LEN, SHELTER_DEPTH = 6.2, 2.6        # m, its footprint (x -3.05..3.05, y -1.53..1.03)
MODEL_Y0 = -1.53                             # m: the front edge of its roof, local y
FRONT_GAP = 0.5                              # m from the edge of the asphalt to the front edge of the roof
ALONG = (4.0, -4.0, 7.0, -7.0, 0.0)          # m along the road from the stop: the places tried, in order
MAX_TILT = 0.10                              # rise over run across the footprint at most
STOP_ROAD = 25.0                             # m: a stop farther from every AI road is not on the map's roads
GROUP = "bus_shelters"


def bus_shelters_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    _, nodes = osm.load()
    stops = [n for n in nodes if n["tags"].get("highway") == "bus_stop" and n["tags"].get("shelter") not in ("no", "yes")]
    rep = {"stops": len(stops), "shelters": 0, "left_out": {"off_road": 0, "no_room": 0, "italy": 0}}
    swiss = None
    try:
        import shopfronts
        swiss = shopfronts.swiss_area()
    except Exception:                                    # no survey outline: every stop
        swiss = None
    # AI roads: axis points, their tangents and half widths
    pts, half, tng = [], [], []
    for road in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json"):
        nd = np.asarray(road.get("nodes", []), np.float64)
        if len(nd) < 2:
            continue
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(nd[:, :2], axis=0).T))]
        sd = np.linspace(0, s[-1], max(int(s[-1]), 1) + 1)
        P = np.column_stack([np.interp(sd, s, nd[:, 0]), np.interp(sd, s, nd[:, 1])])
        T = np.gradient(P, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        pts.append(P)
        tng.append(T)
        half.append(np.interp(sd, s, nd[:, 3]) / 2)
    P, T, H = np.concatenate(pts), np.concatenate(tng), np.concatenate(half)
    lanes = cKDTree(P)
    ground = parking.Ground(zi, lv)
    carr = ground.S
    xy = np.array([[n["x"], n["y"]] for n in stops]).reshape(-1, 2)
    otree, opts = parking.obstacles(zi, lv, xy if len(xy) else np.zeros((1, 2)), 20.0) if len(xy) else (None, None)
    objs = []
    for n in stops:
        p = np.array([n["x"], n["y"]])
        if swiss is not None and not shapely.contains_xy(swiss, p[0], p[1]):
            rep["left_out"]["italy"] += 1
            continue
        d, j = lanes.query(p)
        if d > STOP_ROAD:
            rep["left_out"]["off_road"] += 1
            continue
        t = T[j]
        out = p - P[j]
        if np.hypot(*out) < 0.5:
            out = np.array([t[1], -t[0]])                 # on the axis: the right of the road's direction
        out = out / np.hypot(*out)
        if out @ np.array([-t[1], t[0]]) < 0:
            t = -t                                        # x along the road with the land on the shelter's back
        placed = False
        for s_ in ALONG:
            q = P[j] + T[j] * s_
            jj = lanes.query(q)[1]
            # the edge of the asphalt outwards from the axis there
            edge = float(H[jj])
            for off in np.arange(0.0, 8.0, 0.25):
                z = carr.height([P[jj][0] + out[0] * off], [P[jj][1] + out[1] * off], "near",
                                zhint=ground.terrain([P[jj][0]], [P[jj][1]]))
                if not np.isfinite(z[0]):
                    edge = max(edge, off)
                    break
            front = P[jj] + out * (edge + FRONT_GAP)
            c = front + out * (-MODEL_Y0)                 # the model's origin: its roof's front edge at `front`
            ny = out
            nx = np.array([ny[1], -ny[0]])               # x, y, z right-handed: x = y x z
            corners = [c + nx * sx * SHELTER_LEN / 2 + ny * sy for sx in (-1, 1) for sy in (MODEL_Y0, MODEL_Y0 + SHELTER_DEPTH)]
            fp = shapely.Polygon([corners[0], corners[2], corners[3], corners[1]])
            near = lanes.query_ball_point(c, float(H.max()) + SHELTER_LEN)
            if near and (shapely.distance(fp, shapely.points(P[near])) < H[near] + 0.3).any():
                continue
            oi = otree.query_ball_point(c, SHELTER_LEN / 2 + SHELTER_DEPTH)
            if oi and shapely.contains_xy(fp.buffer(0.2), opts[oi, 0], opts[oi, 1]).any():
                continue
            cz = np.asarray(fp.exterior.coords)[:4]
            zc = ground.height(cz[:, 0], cz[:, 1])
            if (zc.max() - zc.min()) / SHELTER_LEN > MAX_TILT:
                continue
            z = float(np.min(zc))
            theta = math.atan2(nx[1], nx[0])
            ob = bng.tsstatic(MODEL, (float(c[0]), float(c[1]), z), rot=bng.rot_local_x_to(theta), collision=True)
            ob["__parent"] = GROUP
            objs.append(ob)
            placed = True
            break
        if placed:
            rep["shelters"] += 1
        else:
            rep["left_out"]["no_room"] += 1
    files = {f"{lv}/main/MissionGroup/props/{GROUP}/items.level.json":
             ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")}
    p_items = f"{lv}/main/MissionGroup/props/items.level.json"
    rows = read_items(zi, p_items)
    if not any(r.get("name") == GROUP and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": GROUP, "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    files[p_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    import zipfile
    now = time.localtime()[:6]
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename not in files:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("bus shelters:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
