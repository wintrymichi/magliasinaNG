"""Collision cells of the Ticino streaming: lean collision meshes, apart from the meshes that are drawn.

Every be:reloadCollision rebuilds the whole static collision, and its cost grows with what collides: our merged
TSStatic shapes cost about 3 us a unique triangle (console test in game, 2026-10-26: the 3 x 3 tiles of 384 m round
the car 1.12 M triangles, 3.4 s of frozen physics at every tile; the car's tile alone 156 k, 0.54 s; the Forest's
274 k trees and the terrain cost nothing). EarthNG (github.com/Alezx311/earthng, MIT, docs/PERFORMANCE.md) measured a
ProceduralMesh at 0.27 ms per 1000 triangles + 30-40 us an object, ten times less. So the level's own merged shapes
(terrain skin, roads, walls, buildings...) no longer collide with their drawn mesh: their triangles go, welded and
(by group) simplified, into collision cells of CELL_M, which the mod makes as ProceduralMesh pieces of at most
PIECE_TRIS triangles, not drawn, only round the car (objects.lua). Nothing that is drawn changes.

The ground type (tyre grip, sounds, dust) comes from the material: every piece holds the triangles of one ground
type, and its material tc_col_<type> carries it (materials without one: tc_col_default).

A cell file col/c_<i>_<j>.bin, little endian:
    "TCC1", int32 z0 (cm), uint16 pieces; per piece: uint8 ground type (index into stream.json colGroundTypes),
    uint16 vertices, uint16 triangles, vertices as 3 x uint16 (x, y in cm from the cell corner + XY_OFF_CM, z in cm
    over z0), triangles as 3 x uint16, CLOCKWISE seen from outside (ProceduralMesh's order).

    collision.build(zone, tiles, level_dir, src_level, out_dir) -> (cell keys, ground types, stats)

tiles: {(cx, cy): [entries]} as blocks.stream_objects makes them; the entries whose shape moved into the cells get
collisionType "None". The shapes of the game (lamps, poles, benches) are instanced: they keep their own collision.
"""
import glob
import json
import os
import re
import struct
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

CELL_M = 64.0   # a rebuild costs ~0.15 us a cell triangle: 9 cells of 128 m in Lugano 60-110 ms, of 64 m 25-35 ms
PIECE_TRIS = 1200           # EarthNG: one ProceduralMesh of ~28 k hung the game; createMesh ~1.7 us a tri; Lua decode ~3 us
XY_OFF_CM = 16384           # x, y from -163.84 m to +491.51 m round a cell (triangles go to the cell of their centre)
WELD_M = 0.001
# share of the triangles REMOVED per scene group (the longest prefix wins); 0: kept as they are. What the wheels
# drive on (roads, sidewalks, islands, railway, bridges) stays exact: on a road mesh the quadric simplification left
# holes (1.2 % of the surface at 50 %) and moved the edges by up to 0.5 m. The terrain skin is 57 % of the colliding
# triangles and is hit only beside the roads; houses are boxes with details.
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


def ground_types(level_dir):
    """{material name: groundType} of every material file of the level (absent: the engine's default)."""
    out = {}
    for p in glob.glob(os.path.join(level_dir, "**", "*.materials.json"), recursive=True):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for k, m in d.items():
            if isinstance(m, dict) and m.get("groundType"):
                out[m.get("name", k)] = str(m["groundType"]).upper()
                out[m.get("mapTo", k)] = str(m["groundType"]).upper()
    return out


_GEOM = re.compile(rb"<geometry[ >]")
_TRI = re.compile(rb'<triangles material="([^"]*)"[^>]*>(.*?)</triangles>', re.S)
_INPUT = re.compile(rb'<input semantic="(\w+)" source="#([^"]+)" offset="(\d+)"')


def read_top(path):
    """Positions (n, 3), triangles (m, 3) and their material names (m,) of the first geometry of a DAE (the finest
    detail level: the merged shapes' coarser levels are geometries g1, g2 ... after it). (None, None, None) if none."""
    with open(path, "rb") as f:
        data = f.read()
    m = _GEOM.search(data)
    if not m:
        return None, None, None
    end = data.find(b"</geometry>", m.start())
    seg = data[m.start():end if end > 0 else len(data)]
    vm = re.search(rb'<vertices id="([^"]+)">\s*<input semantic="POSITION" source="#([^"]+)"', seg)
    if not vm:
        return None, None, None
    sm = re.search(rb'<source id="' + re.escape(vm.group(2)) + rb'">\s*<float_array[^>]*>([^<]*)</float_array>', seg)
    if not sm:
        return None, None, None
    P = np.array(sm.group(1).split(), np.float64).reshape(-1, 3)
    Ts, Ms = [], []
    for tm in _TRI.finditer(seg):
        mat, body = tm.group(1).decode("utf-8", "replace"), tm.group(2)
        inputs = _INPUT.findall(body)
        stride = max(int(o) for _, _, o in inputs) + 1
        voff = next(int(o) for s, _, o in inputs if s == b"VERTEX")
        pm = re.search(rb"<p>([^<]*)</p>", body)
        if not pm:
            continue
        T = np.array(pm.group(1).split(), np.int64).reshape(-1, stride)[:, voff].reshape(-1, 3)
        Ts.append(T)
        Ms += [mat[:-4] if mat.endswith("-mat") else mat] * len(T)
    if not Ts:
        return None, None, None
    return P, np.concatenate(Ts), np.array(Ms, object)


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
    """One entry's collision triangles in the world, per ground type: ([(type, P, T)], tris before, tris after)."""
    path, p, q, s, red, gtypes = job
    try:
        P, T, M = read_top(path)
    except (OSError, ValueError) as ex:
        return None, str(ex)
    if P is None or not len(T):
        return None, None
    if s is not None:
        P = P * np.asarray(s, np.float64)
    if q is not None:
        P = P @ quat_matrix(q).T
    P = P + np.asarray(p, np.float64)
    G = np.array([gtypes.get(m, "default") for m in M], object)
    out, n0, n1 = [], 0, 0
    for g in sorted(set(G.tolist())):
        Pg, Tg = weld(P, T[G == g])
        n0 += len(Tg)
        if red > 0 and len(Tg) >= MIN_SIMPLIFY_TRIS:
            import fast_simplification
            P2, T2 = fast_simplification.simplify(Pg, Tg.astype(np.int32), target_reduction=red, agg=5,
                                                  preserve_border=True)
            if len(T2):
                Pg, Tg = np.asarray(P2, np.float64), np.asarray(T2, np.int64)
        n1 += len(Tg)
        if len(Tg):
            out.append((g, Pg, Tg))
    return (out, n0, n1), None


def pieces(P, T):
    """Splits a cell's triangles of one ground type into pieces of at most PIECE_TRIS, near ones together (sorted
    along a Z-order of 4 m squares). [(P, T)] with local vertex numbers."""
    c = P[T].mean(1)
    q = np.clip(((c[:, :2] - c[:, :2].min(0)) / 4.0).astype(np.int64), 0, 1023)
    z = np.zeros(len(T), np.int64)
    for b in range(10):
        z |= ((q[:, 0] >> b) & 1) << (2 * b) | ((q[:, 1] >> b) & 1) << (2 * b + 1)
    order = np.argsort(z, kind="stable")
    out = []
    for a in range(0, len(T), PIECE_TRIS):
        sel = T[order[a:a + PIECE_TRIS]]
        used, inv = np.unique(sel, return_inverse=True)
        out.append((P[used], inv.reshape(-1, 3)))
    return out


DROPPED = [0]


def write_cell(path, x0, y0, parts, types):
    """parts {ground type: [(P, T)]} -> the cell file (module doc). Returns (triangles, pieces). A triangle that does
    not fit the cell's range (x, y -163..491 m from its corner, z 655 m over z0) is left out (DROPPED counts them):
    zone ti_0_5 has one with a corner 561 m from its cell (2026-10-29), and one such triangle stopped the whole slice."""
    zs = np.concatenate([P[:, 2] for lst in parts.values() for P, _ in lst])
    z0 = int(np.floor(max(zs.min(), np.median(zs) - 300.0) * 100))
    fitted = {}
    for g, lst in parts.items():
        for P, T in lst:
            V = np.stack([np.round((P[:, 0] - x0) * 100) + XY_OFF_CM, np.round((P[:, 1] - y0) * 100) + XY_OFF_CM,
                          np.round(P[:, 2] * 100) - z0], 1)
            okv = (V >= 0).all(1) & (V <= 65535).all(1)
            okt = okv[T].all(1)
            if not okt.all():
                DROPPED[0] += int((~okt).sum())
                T = T[okt]
            if len(T):
                fitted.setdefault(g, []).append((P, T))
    parts = fitted
    body, n_tri, n_piece = bytearray(), 0, 0
    for g in sorted(parts):
        P = np.concatenate([P for P, _ in parts[g]])
        off = np.cumsum([0] + [len(p) for p, _ in parts[g]])[:-1]
        T = np.concatenate([t + o for (_, t), o in zip(parts[g], off)])
        for Pp, Tp in pieces(P, T):
            V = np.stack([np.round((Pp[:, 0] - x0) * 100) + XY_OFF_CM, np.round((Pp[:, 1] - y0) * 100) + XY_OFF_CM,
                          np.round(Pp[:, 2] * 100) - z0], 1)
            if V.min() < 0 or V.max() > 65535:
                raise ValueError(f"{path}: a vertex out of the cell's range ({V.min()}, {V.max()})")
            body += struct.pack("<BHH", types.index(g), len(V), len(Tp))
            body += V.astype("<u2").tobytes()
            body += Tp[:, [0, 2, 1]].astype("<u2").tobytes()        # counter-clockwise (DAE) -> clockwise
            n_tri += len(Tp)
            n_piece += 1
    if os.path.lexists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.write(b"TCC1" + struct.pack("<iH", z0, n_piece) + bytes(body))
    return n_tri, n_piece


def materials(types):
    """tc_col_<type>: the pieces' materials. Never drawn (the mod turns rendering off); fully transparent anyway."""
    out = {}
    for g in types:
        name = "tc_col_" + g.lower()
        m = {"name": name, "mapTo": name, "class": "Material", "version": 1.5, "translucent": True,
             "translucentZWrite": False, "castShadows": False,
             "Stages": [{"baseColorFactor": [0, 0, 0, 0], "opacityFactor": 0}, {}, {}, {}]}
        if g != "default":
            m["groundType"] = g
        out[name] = m
    return out


def build(zone, tiles, level_dir, src_level, out_dir, workers=4, types=None, gtypes_dir=None, bounds=None):
    """Moves the collision of the level's own shapes into the cells; returns (sorted cell keys "i_j", ground types,
    stats). types: a fixed list of ground types (the plan's, region_slice.py: the cells of every zone index one list);
    gtypes_dir: the folder whose material files give the ground types (default level_dir); bounds (x0, y0, x1, y1):
    a triangle goes to the nearest cell inside them (a zone writes the cells of its own core only)."""
    os.makedirs(out_dir, exist_ok=True)
    gtypes = ground_types(gtypes_dir or level_dir)
    if bounds is not None:
        lo_i, lo_j = int(np.floor((bounds[0] - zone.x0) / CELL_M + 1e-9)), int(np.floor((bounds[1] - zone.y0) / CELL_M + 1e-9))
        hi_i, hi_j = int(np.ceil((bounds[2] - zone.x0) / CELL_M - 1e-9)) - 1, int(np.ceil((bounds[3] - zone.y0) / CELL_M - 1e-9)) - 1
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
            jobs.append((path, e["p"], e.get("q"), e.get("s"), reduction(e.get("g", "")), gtypes))
            owners.append(e)
    log(len(jobs), "shapes of the level to read;", len(gtypes), "materials with a ground type")
    cells = {}
    stats = {"shapes": 0, "tris_in": 0, "tris_out": 0, "failed": 0, "by_group": {}, "by_ground": {}}
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for k, (e, (res, err)) in enumerate(zip(owners, ex.map(object_mesh, jobs, chunksize=4))):
            if err:
                stats["failed"] += 1
                log("not read:", e.get("shapeName"), err)
            if res is None:
                continue
            parts, n0, n1 = res
            e["collisionType"] = "None"
            stats["shapes"] += 1
            stats["tris_in"] += n0
            stats["tris_out"] += n1
            gs = stats["by_group"].setdefault(e.get("g", ""), [0, 0])
            gs[0] += n0
            gs[1] += n1
            for g, P, T in parts:
                stats["by_ground"][g] = stats["by_ground"].get(g, 0) + len(T)
                c = P[T].mean(1)
                ci = np.floor((c[:, 0] - zone.x0) / CELL_M).astype(np.int64)
                cj = np.floor((c[:, 1] - zone.y0) / CELL_M).astype(np.int64)
                if bounds is not None:
                    far = (ci < lo_i - 1) | (ci > hi_i + 1) | (cj < lo_j - 1) | (cj > hi_j + 1)
                    if far.any():               # more than 64 m beyond the core: maybe out of a cell's range
                        stats["tris_dropped_far"] = stats.get("tris_dropped_far", 0) + int(far.sum())
                        keep = np.nonzero(~far)[0]
                        T = T[keep]
                        c, ci, cj = c[keep], ci[keep], cj[keep]
                        if not len(T):
                            continue
                    ci, cj = np.clip(ci, lo_i, hi_i), np.clip(cj, lo_j, hi_j)
                key = (ci + 50000) * 100000 + (cj + 50000)
                order = np.argsort(key, kind="stable")
                ks, starts = np.unique(key[order], return_index=True)
                ends = np.append(starts[1:], len(order))
                for kk, a, b in zip(ks, starts, ends):
                    sel = T[order[a:b]]
                    used, inv = np.unique(sel, return_inverse=True)
                    i, j = int(kk // 100000) - 50000, int(kk % 100000) - 50000
                    cells.setdefault((i, j), {}).setdefault(g, []).append((P[used], inv.reshape(-1, 3)))
            if (k + 1) % 200 == 0:
                log(f"{k + 1}/{len(jobs)} shapes, {stats['tris_in'] / 1e6:.1f} M -> {stats['tris_out'] / 1e6:.1f} M "
                    f"triangles, {time.time() - t0:.0f} s")
    have = sorted({g for parts in cells.values() for g in parts})
    if types is None:
        types = have
    else:
        missing = [g for g in have if g not in types]
        if missing:
            raise KeyError(f"ground types {missing} are not in the plan: run region_plan.py --add")
    with open(os.path.join(out_dir, "col.materials.json"), "w") as f:
        json.dump(materials(types), f, indent=1)
    keys, per, npieces = [], {}, []
    for (i, j), parts in cells.items():
        n, npc = write_cell(os.path.join(out_dir, f"c_{i}_{j}.bin"), zone.x0 + i * CELL_M, zone.y0 + j * CELL_M,
                            parts, types)
        keys.append(f"{i}_{j}")
        per[(i, j)] = n
        npieces.append(npc)
    # the worst 3 x 3 cells (what collides round the car at once)
    worst = max((sum(per.get((i + a, j + b), 0) for a in (-1, 0, 1) for b in (-1, 0, 1)), (i, j)) for (i, j) in per) \
        if per else (0, None)
    v = sorted(per.values())
    stats.update(cells=len(keys), pieces=int(sum(npieces)), cell_tris_median=int(v[len(v) // 2]) if v else 0,
                 cell_tris_max=v[-1] if v else 0, worst_3x3_tris=int(worst[0]), worst_3x3_at=worst[1],
                 seconds=round(time.time() - t0))
    stats["tris_out_of_cell_range"] = DROPPED[0]
    log("cells:", len(keys), "of", CELL_M, "m;", {k: v for k, v in stats.items() if not k.startswith("by_")})
    log("ground types:", stats["by_ground"])
    for g, (a, b) in sorted(stats["by_group"].items(), key=lambda kv: -kv[1][0]):
        log(f"  {g:36s} {a / 1e6:7.2f} M -> {b / 1e6:7.2f} M")
    return sorted(keys), types, stats
