"""Delineator posts along the main roads outside the villages, and wooden poles along the country roads to
the houses outside them (v2.8), in a built level zip.

Up to v2.7 the 96 poles of the map (delineators, sign poles, three wooden poles) stood on the Magliaso-Pura
cantonal road, where the panoramas show them; the roads between the villages had none. There are no open
data on either, so a rule places them, not their real places (patch_lamps.py tells the villages apart):
- delineators: on the roads of the AI network of 6 m and more (drivability >= MAIN) outside the villages, on
  both sides, every DELIN_STEP m on the straight and closer in the bends (DELIN_BENDS: radius -> step), as
  the Swiss ones stand; DELIN_OFF m beyond the edge of the carriageway, on ground within DELIN_STEP_Z m of
  its height; not where a guard rail, a fence, a wall, a building, the railway or another road is (the post
  would stand in it or be needless), not within JUNCTION m of another road's axis. White posts with a black band, 1 m
  over the ground, as props.py draws the delineators of the cantonal road; pipeline meshes in tiles of
  TILE m, drawn up to DELIN_DRAW m, without collision (plastic posts a car knocks over, not a wall);
- wooden poles: on the country roads (drivability COUNTRY: the 3 and 4 m roads) outside the villages
  along houses (a building of the Federal Register within HOUSE_R m), on one side, every POLE_STEP m,
  POLE_OFF m beyond the edge, in lines of MIN_LINE poles at least, the game's wooden pole of the cantonal road (electric_pole_wood_old_01.dae,
  POLE_H m at scale 1, as its three poles there measure) at POLE_SCALE, with collision; one cable from the
  top of a pole to the next of the same line (CABLE_DROP m under the top, sagging by CABLE_SAG of the span),
  a thin black tube in the tiles of the delineators (the attachment points of the game model are not known
  without the game: the cable starts at the pole's axis). A line ends where its cable would pass within
  CABLE_CLEAR m of a street lamp (patch_lamps.py runs before) or of a roof over or beside it, and goes on
  from the next pole if MIN_LINE poles are left.
- none along the panoramas' route (the cantonal road): the poles there are the measured ones.
Everything else is copied as it is.

Usage: python patch_roadside.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, gzip, json, math, os, re, sys, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import optimize_level
import patch_lamps as pl
import patch_unpaved as pu
import patch_wall_fill as pw
import props
import road_mesh
from config import LEVEL_NAME

MAIN = 0.9                  # drivability of the 6 m roads and more (ai_roads.TLM_DRIVE)
COUNTRY = (0.5, 0.8)        # drivability of the 3 and 4 m roads
DELIN_STEP = 50.0           # m between two delineators on the straight
DELIN_BENDS = ((100.0, 12.5), (300.0, 25.0))      # radius under which (m) -> step (m)
DELIN_OFF = 0.5             # m beyond the carriageway edge
DELIN_STEP_Z = 0.6          # m, ground under a post within this of the edge height
DELIN_DRAW = 300.0          # m up to which the delineators are drawn
JUNCTION = 12.0             # m from another road's axis
HOUSE_R = 60.0              # m, a house this near: a line along the road
POLE_STEP = 45.0            # m between two wooden poles
MIN_LINE = 4                # poles of a line at least (a lone pole or two carry nothing)
POLE_OFF = 1.5              # m beyond the carriageway edge
POLE_SCALE = 0.85           # 8.5 m poles
POLE_STEP_Z = 1.2           # m, ground under a pole within this of the edge height
POLE_H = 10.05              # m, height of the game's wooden pole at scale 1
CABLE_DROP, CABLE_SAG, CABLE_R = 0.25, 0.015, 0.012     # m under the top, share of the span, radius (m)
CABLE_CLEAR = 1.0           # m between a cable and a street lamp or a roof: else the line ends there (v2.8 chain)
TILE = 384.0                # m, tiles of the delineator meshes (as optimize_level's merged tiles)
WOODPOLE = props.WOODPOLE


def bend_radius(T, k=10):
    """Radius of the bend (m) at every point of an axis sampled every metre (from the turn of the tangent
    over 2k m)."""
    a = np.unwrap(np.arctan2(T[:, 1], T[:, 0]))
    d = np.abs(a[np.minimum(np.arange(len(a)) + k, len(a) - 1)] - a[np.maximum(np.arange(len(a)) - k, 0)])
    return (2 * k) / np.maximum(d, 1e-6)


def delineator(c, to_road, z):
    """Triangles of one post (white, with the black band facing the road): (white, black) soups."""
    along = np.array([to_road[1], -to_road[0]])
    w = props.box(c, along, 0.12, 0.10, z - 0.2, z + 1.0)
    b = props.box(c + to_road * 0.052, along, 0.10, 0.004, z + 0.72, z + 0.90)
    return w, b


def cable(a, b, n=6):
    """Triangles of a cable from a to b (pole tops, 3D), sagging by CABLE_SAG of the span, a tube of n sides."""
    span = float(np.linalg.norm(b[:2] - a[:2]))
    k = max(int(span / 3.0), 2)
    t = np.linspace(0.0, 1.0, k + 1)
    C = a[None] + t[:, None] * (b - a)[None]
    C[:, 2] -= 4 * CABLE_SAG * span * t * (1 - t)
    d = np.gradient(C, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    u = np.cross(d, [0.0, 0.0, 1.0])
    u /= np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-9)
    v = np.cross(u, d)
    ang = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    R = C[:, None] + CABLE_R * (np.cos(ang)[None, :, None] * u[:, None] + np.sin(ang)[None, :, None] * v[:, None])
    tris = []
    for i in range(k):
        for j in range(n):
            p0, p1, q0, q1 = R[i, j], R[i, (j + 1) % n], R[i + 1, j], R[i + 1, (j + 1) % n]
            tris += [p0, q0, q1, p0, q1, p1]
    return np.array(tris)


def main(src, dst, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    terrain = lambda x, y: float(pu.terrain_top(q, np.atleast_1d(x), np.atleast_1d(y))[0])
    road = pl.faces(zi, lv, ["roads/surfaces"])
    CARR = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if pl.CARRIAGEWAY.match(m)]))
    GROUND = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if not pl.CARRIAGEWAY.match(m)]))
    ROOF = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["buildings"]).values())))
    WALL = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["walls"], keep=lambda sn: "backfill" not in sn).values())))
    RAIL = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["railway"]).values()) or [np.zeros((0, 3, 3))]))
    obst = cKDTree(pl.obstacle_points(zi, lv))
    # the street lamps (patch_lamps.py runs before): no cable through one
    lamp_xy = np.array([o["position"][:2] for f in zi.namelist() if f.endswith("street_lights/items.level.json")
                        for o in pl.read_items(zi, f) if o.get("class") == "TSStatic"], np.float64).reshape(-1, 2)
    ltree = cKDTree(lamp_xy) if len(lamp_xy) else None
    gwr = json.load(gzip.open(os.path.join(pl.DATI, "gwr_area.json.gz")))["buildings"]
    G = np.array([[b["x"], b["y"]] for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or pl.MIN_AREA) >= pl.MIN_AREA])
    gtree = cKDTree(G)
    pano = cKDTree(np.array([p["pos"][:2] for p in json.load(open(os.path.join(pl.DATI, "poses.json")))]))
    roads = [o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [pl.sample(o["nodes"]) for o in roads]
    ids = np.concatenate([np.full(len(s[0]), i) for i, s in enumerate(S) if s is not None])
    allp = np.concatenate([s[0][:, :2] for s in S if s is not None])
    allw = np.concatenate([s[2] for s in S if s is not None])
    atree = cKDTree(allp)
    why = {"tried": 0, "carriageway": 0, "step": 0, "building": 0, "wall": 0, "railway": 0, "clear": 0, "cable": 0}

    def spot(c, t, w, side, off, clear, step_z, road):
        """A free place beside the axis point c (tangent t, width w) of road `road`, `off` m beyond the
        carriageway on side +-1: (x, y, z, unit vector to the road) or None."""
        n = side * np.array([t[1], -t[0]])
        d = np.arange(0.5, w / 2 + 6.0, 0.25)
        Q = c[:2] + d[:, None] * n
        on = np.isfinite(CARR.height(Q[:, 0], Q[:, 1], "high")) & (d < w / 2 + 3.0)
        edge = d[np.flatnonzero(on).max()] if on.any() else w / 2
        p = c[:2] + (edge + off) * n
        why["tried"] += 1
        ring = p + 0.25 * np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]])
        if np.isfinite(CARR.height(ring[:, 0], ring[:, 1], "high")).any():
            why["carriageway"] += 1
            return None
        k = [x for x in atree.query_ball_point(p, 8.0) if ids[x] != road]
        if k and np.any(np.hypot(*(allp[k] - p).T) < allw[k] / 2 + off):
            why["carriageway"] += 1
            return None
        ze = CARR.height([c[0] + (edge - 0.3) * n[0]], [c[1] + (edge - 0.3) * n[1]], "high")[0]
        ze = c[2] if not np.isfinite(ze) else ze
        zg = GROUND.height([p[0]], [p[1]], "high")[0]
        zt = terrain(p[0], p[1])
        z = zg if np.isfinite(zg) and zg > zt - 0.3 else zt
        if not (-step_z <= z - ze <= step_z * 0.7):
            why["step"] += 1
            return None
        if np.isfinite(ROOF.height([p[0]], [p[1]], "high")[0]):
            why["building"] += 1
            return None
        if np.isfinite(WALL.height(ring[:, 0], ring[:, 1], "high")).any():
            why["wall"] += 1
            return None
        if np.isfinite(RAIL.height(ring[:, 0], ring[:, 1], "high")).any():
            why["railway"] += 1
            return None
        if obst.query_ball_point(p, clear, return_length=True) > 0:
            why["clear"] += 1
            return None
        return float(p[0]), float(p[1]), float(z), -n

    top = lambda p: np.array([p[0], p[1], p[2] + POLE_H * POLE_SCALE - CABLE_DROP])

    def cable_free(a, b):
        """No street lamp within CABLE_CLEAR m (xy) of the cable between the poles a and b, and no roof over it
        or within CABLE_CLEAR m under it."""
        A, B = top(a), top(b)
        span = float(np.linalg.norm(B[:2] - A[:2]))
        t = np.linspace(0.0, 1.0, max(int(span / 0.25), 2) + 1)
        C = A[None] + t[:, None] * (B - A)[None]
        C[:, 2] -= 4 * CABLE_SAG * span * t * (1 - t)
        if ltree is not None and any(ltree.query_ball_point(C[:, :2], CABLE_CLEAR)):
            return False
        u = (B[:2] - A[:2]) / max(span, 1e-9)
        side = np.array([-u[1], u[0]])
        for off in (0.0, -0.5, 0.5, -1.0, 1.0):                     # over the cable and up to CABLE_CLEAR beside it
            Q = C[:, :2] + off * CABLE_CLEAR * side
            h = ROOF.height(Q[:, 0], Q[:, 1], "high")
            if (np.isfinite(h) & (h > C[:, 2] - CABLE_CLEAR)).any():
                return False
        return True

    delins, poles, lines = [], [], []
    for i, (o, s) in enumerate(zip(roads, S)):
        if s is None:
            continue
        P, T, W, dist = s
        drv = float(o.get("drivability", 0))
        main_road = drv >= MAIN
        country = COUNTRY[0] <= drv <= COUNTRY[1]
        if not (main_road or country):
            continue
        out = gtree.query_ball_point(P[:, :2], pl.VILLAGE_R, return_length=True) < pl.VILLAGE_N
        out &= ~np.isfinite(pano.query(P[:, :2], distance_upper_bound=pl.PANO_R)[0])
        near = atree.query_ball_point(P[:, :2], JUNCTION)
        out &= np.array([not np.any(ids[k] != i) for k in near])
        if main_road:
            R = bend_radius(T)
            next_s = None
            for j in np.flatnonzero(out):
                step = next((st for r, st in DELIN_BENDS if R[j] < r), DELIN_STEP)
                if next_s is None:
                    next_s = dist[j] + step / 2
                if dist[j] < next_s:
                    continue
                for side in (1, -1):
                    r = spot(P[j], T[j], W[j], side, DELIN_OFF, 0.5, DELIN_STEP_Z, i)
                    if r is not None:
                        delins.append(r)
                next_s = dist[j] + step
        else:
            houses = gtree.query_ball_point(P[:, :2], HOUSE_R, return_length=True) > 0
            side, next_s, run = 1, None, []

            def keep(run):
                if len(run) >= MIN_LINE:
                    k0 = len(poles)
                    poles.extend(r for r, _ in run)
                    lines.extend((k0 + m, k0 + m + 1) for m in range(len(run) - 1))
                why["short_line"] = why.get("short_line", 0) + (len(run) if len(run) < MIN_LINE else 0)

            def flush(run):
                """The run as lines, broken where a cable would pass through a lamp or a house."""
                piece = []
                for r in run:
                    if piece and not cable_free(piece[-1][0], r[0]):
                        why["cable"] += 1
                        keep(piece)
                        piece = []
                    piece.append(r)
                keep(piece)
            for j in np.flatnonzero(out & houses):
                if next_s is None:
                    next_s = dist[j] + 10.0
                if dist[j] < next_s:
                    continue
                r = spot(P[j], T[j], W[j], side, POLE_OFF, 1.5, POLE_STEP_Z, i) or \
                    spot(P[j], T[j], W[j], -side, POLE_OFF, 1.5, POLE_STEP_Z, i)
                if r is None:
                    continue
                if run and dist[j] - run[-1][1] > 1.5 * POLE_STEP:                    # a gap: another line
                    flush(run)
                    run = []
                run.append((r + (math.atan2(T[j][1], T[j][0]),), dist[j]))
                side = 1 if np.array([T[j][1], -T[j][0]]) @ (np.array(r[:2]) - P[j][:2]) > 0 else -1
                next_s = dist[j] + POLE_STEP
            flush(run)
    print("delineators: %d, wooden poles: %d in %d spans (%s)" % (len(delins), len(poles), len(lines), why), flush=True)

    # ---- the meshes of the delineators and the cables, one per tile; the poles
    new_files, items = {}, []
    tiles = {}
    key = lambda x, y: (int(math.floor(x / TILE)), int(math.floor(y / TILE)))
    for x, y, z, to_road in delins:
        w, b = delineator(np.array([x, y]), np.asarray(to_road), z)
        tiles.setdefault(key(x, y), []).append(("mp_delineator_white", w, True))
        tiles[key(x, y)].append(("mp_delineator_black", b, True))
    for a, b in lines:
        c = cable(top(poles[a]), top(poles[b]))
        m = 0.5 * (np.asarray(poles[a][:2]) + np.asarray(poles[b][:2]))
        tiles.setdefault(key(*m), []).append(("mp_cable", c, False))
    for (tx, ty), parts in sorted(tiles.items()):
        mb = bng.MeshBuilder()
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        for mat, V, flat in parts:
            mb.add(mat, V, uvs=V[:, :2], normals=bng.flat_normals_soup(V) if flat else None)
        allv = np.concatenate([V for _, V, _ in parts])
        radius = 0.5 * float(np.linalg.norm(np.ptp(allv, axis=0)))
        detail = max(2, int(round(radius * optimize_level.PIX_K / DELIN_DRAW)))
        rel = f"art/shapes/props/roadside_{tx:+03d}_{ty:+03d}.dae"
        tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"roadside_{os.getpid()}.dae")
        mb.write_dae(tmp, name="roadside", origin=origin, detail=detail, orient=True)
        new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
        os.remove(tmp)
        o = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False)
        o["__parent"] = "delineators"
        items.append(o)
    mats = [bng.material("mp_cable", base_color=[0.05, 0.05, 0.05, 1], roughness=0.6, metallic=0.3, double_sided=True)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"roadside_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/props/roadside.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    for x, y, z, to_road, th in poles:
        o = bng.tsstatic(WOODPOLE, (x, y, z), rot=bng.rot_local_x_to(th), scale=(POLE_SCALE,) * 3, collision=True)
        o["__parent"] = "country_poles"
        items.append(o)
    props_items = f"{lv}/main/MissionGroup/props/items.level.json"
    groups = pl.read_items(zi, props_items)
    have = {g.get("name") for g in groups}
    for name in ("delineators", "country_poles"):
        if name not in have:
            groups.append({"name": name, "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    new_files[props_items] = pl_write(groups)
    new_files[f"{lv}/main/MissionGroup/props/delineators/items.level.json"] = pl_write([o for o in items if o["__parent"] == "delineators"])
    new_files[f"{lv}/main/MissionGroup/props/country_poles/items.level.json"] = pl_write([o for o in items if o["__parent"] == "country_poles"])

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):                     # the new files
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zo.writestr(ni, data)
    print("%s written in %.0f s" % (dst, time.time() - t0), flush=True)
    if report:
        res = {"source": os.path.basename(src), "delineators": len(delins), "tiles": len(tiles),
               "wooden_poles": len(poles), "cable_spans": len(lines), "rejected": why,
               "poles": [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in poles],
               "delineator_posts": [[round(d[0], 2), round(d[1], 2), round(d[2], 2)] for d in delins]}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0


def pl_write(objs):
    return ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
