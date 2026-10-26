"""Collision cells of the Ticino streaming: lean collision meshes, apart from the meshes that are drawn.

Every be:reloadCollision rebuilds the whole static collision, and its cost grows with the unique triangles that
collide: about 3 us each, the terrain itself nothing (console test in game, 2026-10-26: the 3 x 3 tiles of 384 m
round the car 1.12 M triangles, 3.4 s of frozen physics at every tile; the car's tile alone 156 k, 0.54 s; the
Forest's 274 k trees share ~30 meshes and cost nothing). So the level's own merged shapes (terrain skin, roads,
walls, buildings...) no longer collide with their drawn mesh: their triangles go, welded and (by group) simplified,
into one collision-only shape per CELL_M cell (col/c_<i>_<j>.cdae, cdae.encode collision_only), and the mod makes
only the cells round the car collide (objects.lua). The shapes of the game (lamps, poles, benches) are instanced:
they keep their own collision.

    collision.build(zone, tiles, level_dir, src_level, out_dir) -> (cell keys, stats)

tiles: {(cx, cy): [entries]} as blocks.stream_objects makes them; the entries whose shape moved into the cells get
collisionType "None".
"""
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import cdae

CELL_M = 128.0
WELD_M = 0.001
# share of the triangles REMOVED per scene group (the longest prefix wins); 0: kept as they are. What the wheels
# drive on (roads, sidewalks, islands, railway, bridges) stays exact; the terrain skin is the bulk (57 % of the
# colliding triangles) and is hit only beside the roads; houses are boxes with details.
SIMPLIFY = {
    "level_objects/terrain_skin": 0.93,
    "buildings": 0.6,
    "walls": 0.3,
    "props": 0.3,
    "level_objects/vegetation": 0.6,
}
MIN_SIMPLIFY_TRIS = 200


def log(*a):
    print(time.strftime("%H:%M:%S"), "collision:", *a, flush=True)


def reduction(group):
    best, r = -1, 0.0
    for g, v in SIMPLIFY.items():
        if (group == g or group.startswith(g + "/")) and len(g) > best:
            best, r = len(g), v
    return r


_GEOM = re.compile(rb"<geometry[ >]")
_TRI = re.compile(rb"<triangles[^>]*>(.*?)</triangles>", re.S)
_INPUT = re.compile(rb'<input semantic="(\w+)" source="#([^"]+)" offset="(\d+)"')


def read_top(path):
    """Positions (n, 3) and triangles (m, 3) of the first geometry of a DAE (the finest detail level: the merged
    shapes' coarser levels are geometries g1, g2 ... after it). (None, None) when it has none."""
    with open(path, "rb") as f:
        data = f.read()
    m = _GEOM.search(data)
    if not m:
        return None, None
    end = data.find(b"</geometry>", m.start())
    seg = data[m.start():end if end > 0 else len(data)]
    vm = re.search(rb'<vertices id="([^"]+)">\s*<input semantic="POSITION" source="#([^"]+)"', seg)
    if not vm:
        return None, None
    src = vm.group(2)
    sm = re.search(rb'<source id="' + re.escape(src) + rb'">\s*<float_array[^>]*>([^<]*)</float_array>', seg)
    if not sm:
        return None, None
    P = np.array(sm.group(1).split(), np.float64).reshape(-1, 3)
    Ts = []
    for tm in _TRI.finditer(seg):
        body = tm.group(1)
        inputs = _INPUT.findall(body)
        stride = max(int(o) for _, _, o in inputs) + 1
        voff = next(int(o) for s, _, o in inputs if s == b"VERTEX")
        pm = re.search(rb"<p>([^<]*)</p>", body)
        if not pm:
            continue
        idx = np.array(pm.group(1).split(), np.int64)
        Ts.append(idx.reshape(-1, stride)[:, voff].reshape(-1, 3))
    if not Ts:
        return None, None
    return P, np.concatenate(Ts)


def weld(P, T):
    """Vertices within WELD_M merged, unused ones and degenerate triangles dropped."""
    key = np.round(P / WELD_M).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    T = inv[T]
    ok = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])
    T = T[ok]
    used, T2 = np.unique(T, return_inverse=True)
    return P[first][used], T2.reshape(-1, 3)


def quat_matrix(q):
    """Rotation matrix (local -> world) of an entry's setPosRot quaternion (blocks.quat_conj_from_rows: the conjugate
    of the rotation's own)."""
    x, y, z, w = -q[0], -q[1], -q[2], q[3]
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def object_mesh(job):
    """One entry's collision triangles in the world: (P, T, tris before, tris after) or None."""
    path, p, q, s, red = job
    try:
        P, T = read_top(path)
    except (OSError, ValueError) as ex:
        return None, str(ex)
    if P is None or not len(T):
        return None, None
    if s is not None:
        P = P * np.asarray(s, np.float64)
    if q is not None:
        P = P @ quat_matrix(q).T
    P = P + np.asarray(p, np.float64)
    P, T = weld(P, T)
    n0 = len(T)
    if red > 0 and n0 >= MIN_SIMPLIFY_TRIS:
        import fast_simplification
        P2, T2 = fast_simplification.simplify(P, T.astype(np.int32), target_reduction=red, agg=5,
                                              preserve_border=True)
        if len(T2):
            P, T = np.asarray(P2, np.float64), np.asarray(T2, np.int64)
    return (P.astype(np.float64), T.astype(np.int64), n0, len(T)), None


def build(zone, tiles, level_dir, src_level, out_dir, workers=4):
    """Moves the collision of the level's own shapes into the cells; returns (sorted cell keys "i_j", stats)."""
    os.makedirs(out_dir, exist_ok=True)
    prefix = "/levels/ticino/"
    jobs, owners = [], []
    for objs in tiles.values():
        for e in objs:
            if e.get("class") != "TSStatic" or e.get("collisionType") == "None":
                continue
            shape = e.get("shapeName", "")
            if not shape.startswith(prefix):
                continue                      # a shape of the game: instanced, keeps its own collision
            path = os.path.join(level_dir, *shape[len(prefix):].split("/"))
            if not os.path.exists(path):
                continue
            jobs.append((path, e["p"], e.get("q"), e.get("s"), reduction(e.get("g", ""))))
            owners.append(e)
    log(len(jobs), "shapes of the level to read")
    cells = {}
    stats = {"shapes": 0, "tris_in": 0, "tris_out": 0, "failed": 0, "by_group": {}}
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for k, (e, (res, err)) in enumerate(zip(owners, ex.map(object_mesh, jobs, chunksize=4))):
            if err:
                stats["failed"] += 1
                log("not read:", e.get("shapeName"), err)
            if res is None:
                continue
            P, T, n0, n1 = res
            e["collisionType"] = "None"
            stats["shapes"] += 1
            stats["tris_in"] += n0
            stats["tris_out"] += n1
            g = stats["by_group"].setdefault(e.get("g", ""), [0, 0])
            g[0] += n0
            g[1] += n1
            c = P[T].mean(1)
            ci = np.floor((c[:, 0] - zone.x0) / CELL_M).astype(np.int64)
            cj = np.floor((c[:, 1] - zone.y0) / CELL_M).astype(np.int64)
            key = (ci + 50000) * 100000 + (cj + 50000)
            order = np.argsort(key, kind="stable")
            ks, starts = np.unique(key[order], return_index=True)
            ends = np.append(starts[1:], len(order))
            for kk, a, b in zip(ks, starts, ends):
                sel = T[order[a:b]]
                used, inv = np.unique(sel, return_inverse=True)
                i, j = int(kk // 100000) - 50000, int(kk % 100000) - 50000
                cells.setdefault((i, j), []).append((P[used], inv.reshape(-1, 3)))
            if (k + 1) % 200 == 0:
                log(f"{k + 1}/{len(jobs)} shapes, {stats['tris_in'] / 1e6:.1f} M -> {stats['tris_out'] / 1e6:.1f} M "
                    f"triangles, {time.time() - t0:.0f} s")
    # the cells' one material: never drawn, defined so the game does not report it missing
    import bng
    bng.write_materials(os.path.join(out_dir, "col.materials.json"),
                        [bng.material("tc_collision", base_color=[1, 0, 1, 1], extra={"castShadows": False})])
    keys, per = [], {}
    for (i, j), parts in cells.items():
        off, Ps, Ts = 0, [], []
        for P, T in parts:
            Ps.append(P)
            Ts.append(T + off)
            off += len(P)
        P = np.concatenate(Ps) - [zone.x0 + i * CELL_M, zone.y0 + j * CELL_M, 0.0]
        T = np.concatenate(Ts)
        # normals (and so tangents) all the same: a collision mesh is never drawn, and constant arrays pack small
        cdae.write(os.path.join(out_dir, f"c_{i}_{j}.cdae"), P, T, collision_only=True, material="tc_collision",
                   normals=np.tile([0.0, 0.0, 1.0], (len(P), 1)))
        keys.append(f"{i}_{j}")
        per[(i, j)] = len(T)
    # the worst 3 x 3 cells (what collides round the car at once)
    worst = max((sum(per.get((i + a, j + b), 0) for a in (-1, 0, 1) for b in (-1, 0, 1)), (i, j)) for (i, j) in per) \
        if per else (0, None)
    v = sorted(per.values())
    stats.update(cells=len(keys), cell_tris_median=int(v[len(v) // 2]) if v else 0, cell_tris_max=v[-1] if v else 0,
                 worst_3x3_tris=int(worst[0]), worst_3x3_at=worst[1], seconds=round(time.time() - t0))
    log("cells:", len(keys), "of", CELL_M, "m;", {k: v for k, v in stats.items() if k != "by_group"})
    for g, (a, b) in sorted(stats["by_group"].items(), key=lambda kv: -kv[1][0]):
        log(f"  {g:36s} {a / 1e6:7.2f} M -> {b / 1e6:7.2f} M")
    return sorted(keys), stats
