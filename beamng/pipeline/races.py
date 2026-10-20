"""Time trials (v3.0.40): hillclimbs and village stages with checkpoints and the game's own leaderboard.

Up to v3.0 the map was free roam only. Here every route of RACES becomes a mission of the game of type timeTrial
(gameplay/missions/<level>/timeTrial/<id>/: info.json and the race path race.race.json), as the vanilla levels
have them: in free roam the start shows on the map and the big map, the checkpoints are gates of two posts, and
the game keeps the times of every run in the mission's leaderboard. Each route can also be driven the other way
(the descent of a hillclimb): the game offers "reverse" when the race has a reverse start position.

A route follows the AI roads of the level as built (MissionGroup/AIRoads, ai_roads.py), so the races stay on the
roads the game's traffic drives:
- a route given as the name of an AI road (the measured Strada Cantonale Magliaso - Pura) is that road;
- a route given as waypoints (village spawn points or local coordinates) is the chain of shortest ways between
  them over the AI roads, where a road costs its length / drivability**ROUTE_POWER (so the cantonal roads are
  taken over the village lanes) and two roads meet where their nodes lie within JOIN m (and JOIN_DZ m in height).
The checkpoints are every CP_STEP m along the route (at least CP_MIN_GAP m before the finish), as wide as the
road there plus CP_MARGIN m, gates across the direction of travel; the car starts START_BACK m before the start
line. The mission's preview is the level's preview (the orthophoto) cut around the route, the route drawn on it.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish races
"""
import io, json, math, os, shutil, time
import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
import bng
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_X1, TER_Y1
from markings_net import read_items

# (id, name, description, route: the name of an AI road or a list of waypoints, difficulty)
RACES = [
    ("magliaso_pura", "Cronoscalata Magliaso - Pura",
     "La Strada Cantonale da Magliaso su fino a Pura, 240 m di dislivello tra muri in pietra e tornanti: la strada "
     "ricostruita dalle panoramiche. Al contrario e' la discesa.", "strada_cantonale", 35),
    ("penudria", "Cronoscalata della Penudria",
     "Il passo sopra Gravesano: dalla valle del Vedeggio su per la Penudria fino ad Arosio, quasi 500 m di "
     "dislivello in una serie di tornanti nel bosco.", ["spawn_gravesano", "spawn_arosio"], 50),
    ("astano_banco", "Tornanti Astano - Banco",
     "Da Astano giu' per i tornanti fino a Banco, tra prati e castagni.", ["spawn_astano", "spawn_banco"], 40),
    ("giro_villaggi", "Giro dei villaggi: Novaggio - Miglieglia - Breno",
     "Prova speciale nell'Alto Malcantone: da Novaggio per Miglieglia fino a Breno sulla cantonale stretta che "
     "attraversa i nuclei.", ["spawn_novaggio", "spawn_miglieglia", "spawn_breno"], 45),
]

MISSION_TYPE = "timeTrial"
ROUTE_POWER = 4.0            # a road costs length / drivability**ROUTE_POWER
JOIN, JOIN_DZ = 1.5, 3.0     # m: nodes of two AI roads that close are one junction
CP_STEP = 300.0              # m between checkpoints
CP_MIN_GAP = 120.0           # m: no checkpoint closer than this to the finish
CP_MARGIN = 2.0              # m beyond the half width of the road
CP_RADIUS = (5.0, 10.0)      # m, smallest and largest checkpoint radius
TRIM = 60.0                  # m: a route's ends are cut after a turn back within this distance
START_BACK = 8.0             # m from the start position to the start line
TRIGGER_RADIUS = 4.0         # m: the circle that offers the mission in free roam
PREVIEW = (512, 288)         # px of the mission preview
AI_ROADS = "main/MissionGroup/AIRoads/items.level.json"
DROPS = "main/MissionGroup/PlayerDropPoints/items.level.json"


def mission_dir(root, rid):
    return os.path.join(root, "gameplay", "missions", LEVEL_NAME, MISSION_TYPE, rid)


class RoadGraph:
    """The AI roads of the level as one graph of their nodes."""

    def __init__(self, roads):
        self.roads = roads
        P, W, R, rows, cols, cost = [], [], [], [], [], []
        off = 0
        for k, r in enumerate(roads):
            N = np.asarray(r["nodes"], float)
            P.append(N[:, :3])
            W.append(N[:, 3] if N.shape[1] > 3 else np.full(len(N), 5.0))
            R.append(np.full(len(N), k))
            seg = np.linalg.norm(np.diff(N[:, :2], axis=0), axis=1)
            d = max(float(r.get("drivability", 1.0)), 0.05)
            i = np.arange(off, off + len(N) - 1)
            rows += [i, i + 1]
            cols += [i + 1, i]
            cost += [seg / d ** ROUTE_POWER] * 2
            off += len(N)
        self.P, self.W, self.R = np.concatenate(P), np.concatenate(W), np.concatenate(R)
        self.tree = cKDTree(self.P[:, :2])
        pairs = self.tree.query_pairs(JOIN, output_type="ndarray")
        pairs = pairs[(self.R[pairs[:, 0]] != self.R[pairs[:, 1]])
                      & (np.abs(self.P[pairs[:, 0], 2] - self.P[pairs[:, 1], 2]) < JOIN_DZ)]
        rows += [pairs[:, 0], pairs[:, 1]]
        cols += [pairs[:, 1], pairs[:, 0]]
        cost += [np.full(len(pairs), 0.01)] * 2
        n = len(self.P)
        self.G = coo_matrix((np.concatenate(cost) + 1e-6, (np.concatenate(rows), np.concatenate(cols))),
                            shape=(n, n)).tocsr()

    def nearest(self, xy):
        """The node nearest xy on the best road within 60 m (the cantonal road rather than a lane beside it)."""
        idx = self.tree.query_ball_point(xy, 60.0)
        if not idx:
            return int(self.tree.query(xy)[1])
        drive = np.array([self.roads[self.R[i]].get("drivability", 1.0) for i in idx])
        d = np.hypot(*(self.P[idx, :2] - np.asarray(xy)).T)
        best = np.flatnonzero(drive >= drive.max() - 1e-6)
        return int(idx[best[np.argmin(d[best])]])

    def path(self, a, b):
        dist, pred = dijkstra(self.G, indices=a, return_predecessors=True)
        if not np.isfinite(dist[b]):
            raise ValueError(f"no way over the AI roads from node {a} to {b}")
        out = [b]
        while out[-1] != a:
            out.append(int(pred[out[-1]]))
        return out[::-1]


def route_line(graph, route, places):
    """(n, 4) x, y, z, width along the route."""
    if isinstance(route, str):
        k = [i for i, r in enumerate(graph.roads) if r.get("name") == route]
        if not k:
            raise ValueError(f"no AI road {route}")
        m = graph.R == k[0]
        return np.column_stack([graph.P[m], graph.W[m]])
    pts = [places[w] if isinstance(w, str) else w for w in route]
    nodes = []
    for a, b in zip(pts, pts[1:]):
        p = graph.path(graph.nearest(a), graph.nearest(b))
        nodes += p if not nodes else p[1:]
    nodes = [n for i, n in enumerate(nodes) if i == 0 or np.hypot(*(graph.P[n, :2] - graph.P[nodes[i - 1], :2])) > 0.05]
    return np.column_stack([graph.P[nodes], graph.W[nodes]])


def resample(L, step=1.0):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L[:, :2], axis=0), axis=1))]
    t = np.arange(0, s[-1], step)
    t = np.r_[t, s[-1]] if s[-1] - t[-1] > 1e-6 else t
    return np.column_stack([np.interp(t, s, L[:, j]) for j in range(L.shape[1])]), t


def trim_ends(L, s, reach=TRIM):
    """Without a turn back on itself within the first and last `reach` m (an AI road that starts with a hook
    inside a junction, as the measured cantonal road at Magliaso)."""
    d = np.diff(L[:, :2], axis=0)
    h = np.arctan2(d[:, 1], d[:, 0])
    turn = np.degrees(np.abs((h[9:] - h[:-9] + np.pi) % (2 * np.pi) - np.pi))     # over ~10 m
    back = np.flatnonzero(turn > 150) + 5
    a = max([i for i in back if s[i] < reach], default=0)
    b = min([i for i in back if s[-1] - s[i] < reach], default=len(L) - 1)
    a = a + 10 if a else 0
    b = b - 10 if b < len(L) - 1 else b
    return L[a:b + 1], s[a:b + 1] - s[a]


def direction(L, i, reach=6):
    a, b = L[max(i - reach, 0), :2], L[min(i + reach, len(L) - 1), :2]
    d = b - a
    return d / max(np.hypot(*d), 1e-9)


def yaw_quat(d):
    """[x, y, z, w]: the rotation about the vertical that turns +Y to the 2D direction d (a start position of the
    game faces its +Y; the game turns a vehicle, which faces its -Y, half a turn onto it)."""
    a = math.atan2(-d[0], d[1])
    return [0.0, 0.0, round(math.sin(a / 2), 6), round(math.cos(a / 2), 6)]


def r3(v):
    return [round(float(c), 3) for c in v]


def race_path(rid, name, desc, L, s, difficulty):
    """The race path (race.race.json) along the resampled route L at arc lengths s: start line, checkpoints, finish
    line, a start position at each end (the second one for the reverse direction)."""
    total = s[-1]
    at = list(np.arange(0.0, total - CP_MIN_GAP, CP_STEP)) + [total]
    idx = [int(np.argmin(np.abs(s - a))) for a in at]
    nodes, segs = [], []
    for k, i in enumerate(idx):
        d = direction(L, i)
        rad = float(np.clip(L[i, 3] / 2 + CP_MARGIN, *CP_RADIUS))
        nodes.append({"name": "Start" if k == 0 else "Finish" if k == len(idx) - 1 else f"Checkpoint {k}",
                      "oldId": k + 1, "pos": r3(L[i, :3]), "radius": round(rad, 2),
                      "normal": r3([d[0], d[1], 0.0]), "useNormal": True, "visible": True,
                      "recovery": -1, "reverseRecovery": -1})
    for k in range(len(nodes) - 1):
        segs.append({"name": f"Segment {k + 1}", "oldId": 100 + k + 1, "from": k + 1, "to": k + 2})

    def start(i, sign):
        d = direction(L, i) * sign
        j = int(np.argmin(np.abs(s - (s[i] - sign * START_BACK))))
        p = L[j, :3] + np.array([0, 0, 0.3])
        return p, yaw_quat(d)
    p0, q0 = start(idx[0], 1)
    p1, q1 = start(idx[-1], -1)
    starts = [{"name": "Partenza", "oldId": 201, "pos": r3(p0), "rot": q0},
              {"name": "Partenza al contrario", "oldId": 202, "pos": r3(p1), "rot": q1}]
    race = {"name": name, "description": desc, "authors": "michi (pipeline: Claude)", "difficulty": difficulty,
            "date": 0, "defaultLaps": 1, "closed": False, "startNode": 1, "endNode": len(nodes),
            "defaultStartPosition": 201, "reverseStartPosition": 202,
            "rollingStartPosition": -1, "rollingReverseStartPosition": -1,
            "prefabs": [], "forwardPrefabs": [], "reversePrefabs": [], "hotlap": False,
            "pathnodes": nodes, "segments": segs, "startPositions": starts, "pacenotes": []}
    return race, (p0, q0)


def mission_info(rid, name, desc, start, difficulty):
    p, q = start
    return {"name": name, "description": desc, "missionType": MISSION_TYPE, "author": "michi (pipeline: Claude)",
            "date": 0, "devMission": False,
            "startTrigger": {"type": "coordinates", "level": LEVEL_NAME, "pos": r3(p), "rot": q,
                             "radius": TRIGGER_RADIUS},
            "visibleCondition": {}, "startCondition": {},
            "missionTypeData": {"closed": False, "defaultLaps": 1, "allowFlip": False, "allowRollingStart": True,
                                "allowReverse": True, "mapPreviewMode": "navgraph", "prefabs": []},
            "careerSetup": {"showInCareer": False, "showInFreeroam": True},
            "additionalAttributes": {"difficulty": "medium" if difficulty < 45 else "hard"},
            "retryBehaviour": "infiniteRetries",
            "previewFile": "preview.jpg", "thumbnailFile": "thumbnail.jpg"}


def preview(root, L, size):
    """The level's preview (the orthophoto over the whole terrain) cut around the route, the route drawn on it."""
    src = os.path.join(root, "levels", LEVEL_NAME, f"{LEVEL_NAME}_preview.jpg")
    w, h = size
    if not os.path.exists(src):
        return None
    img = Image.open(src).convert("RGB")
    W, H = img.size

    def px(x, y):
        return (x - TER_X0) / (TER_X1 - TER_X0) * W, (TER_Y1 - y) / (TER_Y1 - TER_Y0) * H
    X, Y = px(L[:, 0], L[:, 1])
    cx, cy = (X.min() + X.max()) / 2, (Y.min() + Y.max()) / 2
    span = max((X.max() - X.min()) * 1.25, (Y.max() - Y.min()) * 1.25 * w / h, 40.0)
    box = (cx - span / 2, cy - span * h / w / 2, cx + span / 2, cy + span * h / w / 2)
    k = 4                                       # drawn large, then scaled down: smooth lines
    crop = img.resize((w * k, h * k), Image.LANCZOS, box=box)
    dr = ImageDraw.Draw(crop)
    pts = [((x - box[0]) / (box[2] - box[0]) * w * k, (y - box[1]) / (box[3] - box[1]) * h * k) for x, y in zip(X, Y)]
    dr.line(pts, fill=(255, 255, 255), width=7 * k, joint="curve")
    dr.line(pts, fill=(226, 32, 40), width=4 * k, joint="curve")
    for (x, y), c in ((pts[0], (40, 200, 70)), (pts[-1], (20, 20, 20))):
        dr.ellipse([x - 7 * k, y - 7 * k, x + 7 * k, y + 7 * k], fill=c, outline=(255, 255, 255), width=2 * k)
    return crop.resize((w, h), Image.LANCZOS)


def races_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    roads = [r for r in read_items(zi, f"{lv}/{AI_ROADS}") if r.get("class") == "DecalRoad" and len(r.get("nodes", [])) > 1]
    places = {o["name"]: o["position"][:2] for o in read_items(zi, f"{lv}/{DROPS}") if "name" in o}
    graph = RoadGraph(roads)
    base = os.path.join(root, "gameplay", "missions", LEVEL_NAME, MISSION_TYPE)
    shutil.rmtree(base, ignore_errors=True)
    rep = {"races": []}
    for rid, name, desc, route, diff in RACES:
        L, s = trim_ends(*resample(route_line(graph, route, places)))
        z = L[:, 2]
        climb = float(np.clip(np.diff(z), 0, None).sum())
        race, start = race_path(rid, name, desc, L, s, diff)
        info = mission_info(rid, name, desc, start, diff)
        d = mission_dir(root, rid)
        os.makedirs(d, exist_ok=True)
        json.dump(race, open(os.path.join(d, "race.race.json"), "w", encoding="utf-8"), indent=1)
        json.dump(info, open(os.path.join(d, "info.json"), "w", encoding="utf-8"), indent=1)
        im = preview(root, L, PREVIEW)
        if im is not None:
            im.save(os.path.join(d, "preview.jpg"), quality=88)
            im.resize((PREVIEW[0] // 2, PREVIEW[1] // 2), Image.LANCZOS).save(os.path.join(d, "thumbnail.jpg"), quality=88)
        rep["races"].append({"id": rid, "length_m": round(float(s[-1])), "climb_m": round(climb),
                             "rise_m": round(float(z[-1] - z[0])), "checkpoints": len(race["pathnodes"]) - 2,
                             "start": r3(L[0, :3]), "finish": r3(L[-1, :3])})
    rep["seconds"] = round(time.time() - t0)
    print("races:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
