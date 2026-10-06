"""Street lamps along the roads of the villages, and the lights of the street lamps (v2.8), in a built
level zip.

Up to v2.7 the map had 73 street lamps: 68 on the Magliaso-Pura cantonal road, where the panoramas show
them, and 5 elsewhere; the other ~225 km of roads had none. And none of them lit: the release builds
take the cantonal road's objects from the v1.1 zip (carryover.py), older than the lights of props.py
(v2.4), so the PointLights under the lamp heads never reached a release.

Here, with no official data on where the lamps stand (a plausible rule, not their real places):
- a point of a road is in a village where at least VILLAGE_N buildings of the Federal Register
  (dati/gwr_area.json.gz: existing, at least 30 m^2) stand within VILLAGE_R m;
- along every road of the AI network (the roads open to cars), in a village, a lamp every SPACING m,
  LATERAL m beyond the edge of the carriageway (the mp_road_* faces of the road meshes; the AI road's
  width where there are none), on the side of the previous lamp of that road where it can stand,
  otherwise on the other side. A lamp stands on a pavement, a yard or the ground within STEP m of the
  height of the road edge (not under a road on a bridge or a wall), not on a carriageway nor within
  half the width + LATERAL of the axis of another road of the AI network, not in a building or on a wall,
  at least CLEAR m from street furniture, sign poles, guard rails, fences and tree trunks, not within
  JUNCTION m of another road's axis (a junction) and at least MIN_GAP m from every other lamp;
- none on the cantonal road covered by the panoramas (within PANO_R m of their route): the lamps there
  are the ones the photos show;
- the model of the lamps already on the map (italy_light_single.dae of the game's Italy level, referred
  to, not copied), scale 1, its arm (local +x, as measured on the cantonal road) towards the road;
- a PointLight under the head of every lamp (the head measured in the panoramas for the cantonal road,
  dati/lamps.json; else HEAD: 1.2 m along the arm and 8.75 m up at scale 1, the median of those), warm,
  without shadows, as
  props.py: for the 73 lamps of v2.7 always, for the new ones only with --village-lights (thousands of
  lights; their cost in the game is to be measured).
The lamps are TSStatics with the game's own detail levels and instanced rendering, in the street_lights
group; everything else is copied as it is.

Usage: python patch_lamps.py <in.zip> <out.zip> [--village-lights] [--report <json>]
"""
import argparse, gzip, json, math, os, re, sys, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import optimize_level
import patch_unpaved as pu
import patch_wall_fill as pw
import props
import road_mesh
from config import LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(HERE, "..", "dati")
LIGHT = props.LIGHT
VILLAGE_R, VILLAGE_N = 45.0, 6          # m, buildings within it: a road point in a village
MIN_AREA = 30.0                         # m^2, smaller buildings (sheds, garages) do not count
SPACING = 30.0                          # m between two lamps along a road
LATERAL = 0.6                           # m beyond the edge of the carriageway
STEP = 0.6                              # m, the ground under a lamp at most this far from the road edge height
CLEAR = 1.0                             # m from furniture, poles, guard rails, fences, trunks
JUNCTION = 9.0                          # m from the axis of another road
MIN_GAP = 18.0                          # m between two lamps
PANO_R = 30.0                           # m around the route of the panoramas (cantonal road)
HEAD = (1.2, 8.75)                      # m, lamp head at scale 1: along the arm, up
CARRIAGEWAY = re.compile(r"^mp_road_(?!wall)")


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def faces(zi, lv, groups, keep=None):
    """{material: top faces (k, 3, 3)} of the pipeline shapes of the groups (faces turned up only)."""
    out = {}
    for g in groups:
        f = f"{lv}/main/MissionGroup/{g}/items.level.json"
        if f not in zi.NameToInfo:
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or (keep and not keep(sn)):
                continue
            V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            for mat, idx in parts:
                t = W[idx[:, 0]].reshape(-1, 3, 3)
                n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                up = n[:, 2] > 0.3 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
                out.setdefault(mat, []).append(t[up])
    return {m: np.concatenate(v) for m, v in out.items()}


def obstacle_points(zi, lv):
    """xy of what a lamp must keep clear of: the objects of the props groups (the position of a game
    model, the vertices of a pipeline mesh), guard rails, fences, and the trunks of the forest."""
    pts = []
    for f in zi.namelist():
        if not f.endswith("items.level.json") or not any(f"/MissionGroup/{g}/" in f for g in ("props", "roads/guardrails",
                                                                                              "roads/fences")):
            continue
        for o in read_items(zi, f):
            if o.get("class") != "TSStatic":
                continue
            sn = o.get("shapeName", "").lstrip("/")
            pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
            if sn in zi.NameToInfo:
                V = optimize_level.parse(zi.read(sn).decode("utf-8"))[0] + pos
                pts.append(np.unique(np.round(V[:, :2] * 10) / 10, axis=0))
            else:
                pts.append(pos[None, :2])
    for f in zi.namelist():
        if f.startswith(f"{lv}/forest/") and f.endswith(".forest4.json"):
            P = [json.loads(l)["pos"][:2] for l in zi.read(f).decode("utf-8").splitlines() if l.strip()]
            if P:
                pts.append(np.asarray(P, np.float64))
    return np.concatenate(pts)


def sample(nodes, step=1.0):
    """A road's axis every `step` m: points (k, 3), unit tangents (k, 2), widths (k,), distances (k,)."""
    N = np.asarray(nodes, np.float64)
    seg = np.linalg.norm(np.diff(N[:, :2], axis=0), axis=1)
    s = np.r_[0.0, np.cumsum(seg)]
    if s[-1] < step:
        return None
    q = np.arange(0.0, s[-1], step)
    P = np.column_stack([np.interp(q, s, N[:, k]) for k in range(3)])
    w = np.interp(q, s, N[:, 3])
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    return P, T, w, q


def main(src, dst, village_lights=False, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    terrain = lambda x, y: pu.terrain_top(q, np.atleast_1d(x), np.atleast_1d(y))

    road = faces(zi, lv, ["roads/surfaces"])
    CARR = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if CARRIAGEWAY.match(m)]))
    GROUND = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if not CARRIAGEWAY.match(m)]))
    ROOF = road_mesh.TriSurface(np.concatenate(list(faces(zi, lv, ["buildings"]).values())))
    WALL = road_mesh.TriSurface(np.concatenate(list(faces(zi, lv, ["walls"], keep=lambda sn: "backfill" not in sn).values())))
    obst = cKDTree(obstacle_points(zi, lv))
    print("faces: %d carriageway, %d other road, %d roofs, %d wall tops; %d obstacle points"
          % (len(CARR.t), len(GROUND.t), len(ROOF.t), len(WALL.t), obst.n), flush=True)

    gwr = json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz")))["buildings"]
    G = np.array([[b["x"], b["y"]] for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or MIN_AREA) >= MIN_AREA])
    gtree = cKDTree(G)
    commune = [b.get("ggdename", "") for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or MIN_AREA) >= MIN_AREA]
    pano = cKDTree(np.array([p["pos"][:2] for p in json.load(open(os.path.join(DATI, "poses.json")))]))

    lights_f = f"{lv}/main/MissionGroup/props/street_lights/items.level.json"
    old = read_items(zi, lights_f)
    old_lamps = [o for o in old if o.get("class") == "TSStatic" and o.get("shapeName") == LIGHT]
    have_light = any(o.get("class") == "PointLight" for o in old)

    # the axes of the AI roads every metre, which road each point is on
    roads = [o for o in read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [sample(o["nodes"]) for o in roads]
    ids = np.concatenate([np.full(len(s[0]), i) for i, s in enumerate(S) if s is not None])
    allp = np.concatenate([s[0][:, :2] for s in S if s is not None])
    allw = np.concatenate([s[2] for s in S if s is not None])
    atree = cKDTree(allp)

    lamps = np.array([o["position"][:2] for o in old_lamps], np.float64).reshape(-1, 2)
    new, why = [], {"tried": 0, "carriageway": 0, "step": 0, "building": 0, "wall": 0, "clear": 0, "gap": 0}

    def try_place(c, t, w, side, road):
        """Lamp beside the axis point c (tangent t, width w) of the AI road `road` on side +1 (right) or -1:
        (x, y, z, theta) or None."""
        n = side * np.array([t[1], -t[0]])
        d = np.arange(0.5, w / 2 + 6.0, 0.25)
        Q = c[:2] + d[:, None] * n
        on = np.isfinite(CARR.height(Q[:, 0], Q[:, 1], "high")) & (d < w / 2 + 3.0)
        edge = d[np.flatnonzero(on).max()] if on.any() else w / 2         # the farthest carriageway point
        p = c[:2] + (edge + LATERAL) * n
        why["tried"] += 1
        ring = p + 0.35 * np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]])
        if np.isfinite(CARR.height(ring[:, 0], ring[:, 1], "high")).any():
            why["carriageway"] += 1
            return None
        ze = CARR.height([c[0] + (edge - 0.3) * n[0]], [c[1] + (edge - 0.3) * n[1]], "high")[0]
        ze = c[2] if not np.isfinite(ze) else ze
        zg = GROUND.height([p[0]], [p[1]], "high")[0]
        zt = float(terrain(p[0], p[1])[0])
        z = zg if np.isfinite(zg) and zg > zt - 0.3 else zt
        if not (-0.4 <= z - ze <= STEP):
            why["step"] += 1
            return None
        if np.isfinite(ROOF.height([p[0]], [p[1]], "high")[0]):
            why["building"] += 1
            return None
        if np.isfinite(WALL.height(ring[:, 0], ring[:, 1], "high")).any():
            why["wall"] += 1
            return None
        k = [x for x in atree.query_ball_point(p, 8.0) if ids[x] != road]     # in the way on another road
        if k and np.any(np.hypot(*(allp[k] - p).T) < allw[k] / 2 + LATERAL - 0.05):
            why["carriageway"] += 1
            return None
        if obst.query_ball_point(p, CLEAR, return_length=True) > 0:
            why["clear"] += 1
            return None
        if len(lamps) and np.min(np.hypot(*(lamps - p).T)) < MIN_GAP:
            why["gap"] += 1
            return None
        return float(p[0]), float(p[1]), float(z), math.atan2(-n[1], -n[0])

    for i, s in enumerate(S):
        if s is None:
            continue
        P, T, W, dist = s
        village = gtree.query_ball_point(P[:, :2], VILLAGE_R, return_length=True) >= VILLAGE_N
        village &= ~np.isfinite(pano.query(P[:, :2], distance_upper_bound=PANO_R)[0])
        # a junction: a point of another road within JUNCTION m
        near = atree.query_ball_point(P[:, :2], JUNCTION)
        village &= np.array([not np.any(ids[k] != i) for k in near])
        side, next_s = 1, None
        for j in np.flatnonzero(village):                 # the first lamp 5 m into the village, then every SPACING
            if next_s is None:
                next_s = dist[j] + 5.0
            if dist[j] < next_s:
                continue
            r = try_place(P[j], T[j], W[j], side, i) or try_place(P[j], T[j], W[j], -side, i)
            if r is None:                                 # tried again a metre further on
                continue
            new.append(r)
            p = np.array(r[:2])
            lamps = np.vstack([lamps, p])
            side = 1 if (np.array([T[j][1], -T[j][0]]) @ (p - P[j][:2])) > 0 else -1
            next_s = dist[j] + SPACING
    print("new street lamps: %d (%s)" % (len(new), why), flush=True)

    # the objects: the lamps, the lights under their heads
    out_items = list(old)
    lights = 0

    def light(x, y, z, theta, sz=1.0):
        a, h = HEAD
        return {"class": "PointLight", "persistentId": bng.pid(),
                "position": [x + a * math.cos(theta), y + a * math.sin(theta), z + h * sz - 0.35],
                "radius": props.LAMP_RADIUS, "intensity": props.LAMP_LUMEN, "intensityUnit": "lm",
                "brightness": props.LAMP_BRIGHTNESS, "color": [1.0, 0.82, 0.58, 1.0], "castShadows": False,
                "isEnabled": True, "__parent": "street_lights"}
    if not have_light:
        measured = json.load(open(os.path.join(DATI, "lamps.json")))
        feet = cKDTree(np.array([m["foot"][:2] for m in measured]))
        for o in old_lamps:
            R = o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1])
            x, y, z = o["position"]
            o_l = light(x, y, z, math.atan2(R[1], R[0]), o.get("scale", [1, 1, 1])[2])
            d, j = feet.query([x, y])
            if d < 0.2:                                   # the head measured in the panoramas (lamps.py)
                hx, hy, hz = measured[j]["head"]
                o_l["position"] = [hx, hy, hz - 0.35]
            out_items.append(o_l)
            lights += 1
    for x, y, z, th in new:
        o = bng.tsstatic(LIGHT, (x, y, z), rot=bng.rot_local_x_to(th), collision=True)
        o["__parent"] = "street_lights"
        out_items.append(o)
        if village_lights:
            out_items.append(light(x, y, z, th))
            lights += 1
    data = ("\n".join(json.dumps(o, separators=(",", ":")) for o in out_items) + "\n").encode("utf-8")

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for inf in zi.infolist():
            if inf.filename == lights_f:
                zo.writestr(inf, data, compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
    print("%s written in %.0f s: %d lamps (%d new), %d lights" % (dst, time.time() - t0, len(old_lamps) + len(new),
                                                                  len(new), lights), flush=True)
    if report:
        by = {}
        if new:
            _, k = gtree.query(np.array([n[:2] for n in new]))
            for j in k:
                by[commune[j]] = by.get(commune[j], 0) + 1
        res = {"source": os.path.basename(src), "lamps_before": len(old_lamps), "lamps_new": len(new),
               "lights_added": lights, "village_lights": village_lights, "rejected": why,
               "new_by_commune": dict(sorted(by.items(), key=lambda kv: -kv[1])),
               "lamps": [[round(x, 2), round(y, 2), round(z, 2), round(math.degrees(th), 1)] for x, y, z, th in new]}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--village-lights", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.village_lights, a.report))
