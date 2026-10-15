"""v3.0: the terrain brought up to the edges of the roads (no step from the road down to the ground).

The road meshes lie on a terrain carved under them (build_level.stage_roads), but beside them the terrain kept its
own height: where the ground is lower than the edge of the road (a road on a low fill, the DTM smoothed across a
road cut into a slope) the road stood on it like a kerb, its side face showing (v3 screenshots 15, 17, 49).

Here every terrain vertex beside the edge of a road surface (asphalt, pavements, gravel and dirt roads and paths:
the boundary of their top faces that has no other road surface right beyond it) and lower than the edge is raised
to a shoulder: SHOULDER_DZ under the edge out to FLAT m from it, then a slope of SLOPE down to the ground it had.
Left as they were: the vertices under a road surface (carved already), the terrain squares a wall, building,
fence or railway mesh passes through, and the edges standing more than MAX_DROP over the ground (embankments,
bridge decks: a slope that high would bury what stands below them).

Beside an embankment (the ground TRIM_DROP m under the edge TRIM_REACH m out) the vertices that the carving of
the road set to its height one square beyond its edge stood out of the slope as a row of teeth (along the lake
at Magliaso, screenshot 37): they come down to a slope of TRIM_SLOPE from the edge, never under the ground beyond.

Where a paved road still stands FACE_MIN or more over the ground beside it after that (a lane above another, a
road on a fill), its side face showed as a black band floating over the grass (screenshot 17): a stone retaining
face goes from the edge down into the ground there (art/shapes/walls/shoulder_walls_*.dae, in the walls group),
except on bridges and where a wall, building or fence already stands at the edge.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish shoulders
"""
import json, os, re, tempfile, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import optimize_level
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE
from markings_net import read_items, shape_tris, up_faces
from road_mesh import TriSurface
from road_wear import chains, resample
from walls import read_ter

NOT_GROUND = ("mp_road_wall", "mp_bridge_parapet")    # side faces and parapets: not the top of a road
UNPAVED = ("mp_road_dirt", "mp_road_gravel", "mp_path_dirt", "mp_path_gravel", "mp_hard_gravel")   # no stone faces
SHOULDER_DZ = 0.04     # m under the edge: the shoulder at the edge of the road
FLAT = 0.8             # m out from the edge at the height of the edge
SLOPE = 0.6            # m down per m beyond FLAT
MAX_DROP = 1.2         # m: an edge standing higher over the ground beside it is an embankment, left as it is
MIN_LIFT = 0.02        # m: smaller changes are not made
OUT_TEST = 0.30        # m beyond an edge: another road surface within JOINT_DZ there, the edge is a joint
JOINT_DZ = 0.25
STEP = 0.25            # m between the samples along the edges
DROP_AT = 1.5          # m out from the edge where the drop to the ground is measured
INNER = 2.5            # m: the vertices under a road this near its edge come up under it (the side face hidden)
MARGIN = 0.08          # m: a raised vertex under the lowest road surface over its four terrain squares
FLOOR_STEP = 0.5       # m between the samples of the road surfaces over the four squares
FACE_MIN = 0.30        # m: an edge still this high over the ground beside it gets a stone face under it
FACE_MAX = 4.0         # m: higher is a viaduct or a cliff, not a road wall
FACE_GAP = 4           # samples: shorter gaps between faces closed
FACE_RUN = 12          # samples: shorter faces left out (3 m)
FACE_SINK = 0.25       # m the foot of a face goes into the ground
FACE_TILE = 3.0        # m: the stone texture (walls.WALL_TILE)
FACE_TILE_M = 512.0    # m: the size of the DAE tiles of the faces
BATTER = 0.10          # m out per m down
PARAPET_R = 3.0        # m: edges this near a bridge parapet are bridges
FACE_SHAPE = re.compile(r"art/shapes/walls/shoulder_walls_[^/]+\.dae$")
TRIM_DROP = 1.5        # m: the ground this far under the edge TRIM_REACH m out: an embankment, where
TRIM_REACH = 3.0       # the ground carved for the road beyond its edge is trimmed to a slope of TRIM_SLOPE
TRIM_SLOPE = 1.5       # (never under the ground out there)
REACH = FLAT + MAX_DROP / SLOPE + 0.5                 # m: the farthest vertex a shoulder can raise
SAMPLE = 0.25          # m between the samples along the triangles of the meshes that keep their ground
KEEP = ("/art/shapes/walls/", "/art/shapes/buildings/", "/art/shapes/fences/")      # their feet may be buried
HARD = ("/art/shapes/railway/",)                                                    # never
STANDS = 0.5           # m: a wall, building or fence must stand this much over the new ground there


def boundary(A, S):
    """Boundary edges (k, 2, 3) of the top faces A, turned with the faces on their left, that have no road
    surface (TriSurface S) right beyond them."""
    V = A.reshape(-1, 3)
    key = np.round(V[:, :2] * 200).astype(np.int64)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    tri = vid.reshape(-1, 3)
    E = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    own = np.tile(np.arange(len(tri)), 3)
    corner = np.concatenate([np.full(len(tri), 2), np.full(len(tri), 0), np.full(len(tri), 1)])
    lo, hi = E.min(1), E.max(1)
    _, first, cnt = np.unique(lo * (int(vid.max()) + 1) + hi, return_index=True, return_counts=True)
    b = first[cnt == 1]
    t, ia = own[b], b // len(tri)
    a3, b3, c3 = A[t, ia], A[t, (ia + 1) % 3], A[t, corner[b]]
    d = b3[:, :2] - a3[:, :2]
    left = d[:, 0] * (c3[:, 1] - a3[:, 1]) - d[:, 1] * (c3[:, 0] - a3[:, 0]) > 0
    a3, b3 = np.where(left[:, None], a3, b3), np.where(left[:, None], b3, a3)
    d = b3[:, :2] - a3[:, :2]
    L = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    nout = np.column_stack([d[:, 1], -d[:, 0]]) / L[:, None]
    m = 0.5 * (a3 + b3)
    q = m[:, :2] + nout * OUT_TEST
    zc = S.height(q[:, 0], q[:, 1], "near", zhint=m[:, 2])
    keep = ~(np.isfinite(zc) & (np.abs(zc - m[:, 2]) < JOINT_DZ)) & (L > 1e-3)
    return np.stack([a3[keep], b3[keep]], 1)


def samples(E):
    """Points (k, 3) every STEP m along the edges, their outward normals (k, 2) and the edge chain of each (k,)."""
    P, N, I = [], [], []
    for C in chains(E):
        R = resample(C, STEP)
        if len(R) < 2:
            continue
        d = np.gradient(R[:, :2], axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1), 1e-9)[:, None]
        P.append(R)
        N.append(np.column_stack([d[:, 1], -d[:, 0]]))
        I.append(np.full(len(R), len(I)))
    if not P:
        return np.zeros((0, 3)), np.zeros((0, 2)), np.zeros(0, np.int64)
    return np.concatenate(P), np.concatenate(N), np.concatenate(I)


def kept_cells(zi, lv, n):
    """(n - 1, n - 1) float32: the top of the wall, building and fence meshes in the terrain squares they pass
    through (-inf in the others, +inf where a railway mesh passes)."""
    cells = np.full((n - 1, n - 1), -np.inf, np.float32)
    for f in zi.namelist():
        if not f.startswith(f"{lv}/main/MissionGroup/") or not f.endswith("items.level.json"):
            continue
        for o in read_items(zi, f):
            sn = o.get("shapeName", "")
            hard = any(k in sn for k in HARD)
            if o.get("class") != "TSStatic" or not (hard or any(k in sn for k in KEEP)) \
                    or sn.lstrip("/") not in zi.NameToInfo:
                continue
            V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn.lstrip("/")).decode("utf-8"))
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            for _, idx in parts:
                t = W[idx[:, 0]].reshape(-1, 3, 3)
                pts = [t.mean(1)]
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    L = np.linalg.norm(t[:, b] - t[:, a], axis=1)
                    k = np.maximum(np.ceil(L / SAMPLE).astype(np.int64), 1)
                    rep = np.repeat(np.arange(len(t)), k + 1)
                    start = np.repeat(np.cumsum(k + 1) - (k + 1), k + 1)
                    fr = (np.arange(len(rep)) - start) / k[rep]
                    pts.append(t[rep, a] + fr[:, None] * (t[rep, b] - t[rep, a]))
                P = np.concatenate(pts)
                c = np.floor((P[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
                r = np.floor((P[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
                ok = (r >= 0) & (r < n - 1) & (c >= 0) & (c < n - 1)
                np.maximum.at(cells, (r[ok], c[ok]), np.float32(np.inf) if hard else P[ok, 2].astype(np.float32))
    return cells


def road_floor(S, V):
    """The lowest road surface (TriSurface S) over the four terrain squares around each vertex V (k, 2); +inf
    where there is none."""
    o = np.arange(-TER_SQUARE, TER_SQUARE + 1e-6, FLOOR_STEP)
    ox, oy = [a.ravel() for a in np.meshgrid(o, o)]
    out = np.full(len(V), np.inf)
    for i in range(0, len(V), 20000):
        B = V[i:i + 20000]
        z = S.height((B[:, 0, None] + ox).ravel(), (B[:, 1, None] + oy).ravel(), "low").reshape(len(B), -1)
        out[i:i + 20000] = np.where(np.isfinite(z), z, np.inf).min(1)
    return out


def terrain_at(H, x, y):
    """Bilinear height of the terrain vertices H at (x, y) (close enough to its triangles for a drop)."""
    n = H.shape[0]
    fx, fy = (x - TER_X0) / TER_SQUARE, (y - TER_Y0) / TER_SQUARE
    c = np.clip(np.floor(fx).astype(np.int64), 0, n - 2)
    r = np.clip(np.floor(fy).astype(np.int64), 0, n - 2)
    u, v = np.clip(fx - c, 0, 1), np.clip(fy - r, 0, 1)
    return (H[r, c] * (1 - u) * (1 - v) + H[r, c + 1] * u * (1 - v) + H[r + 1, c] * (1 - u) * v
            + H[r + 1, c + 1] * u * v)


def faces(P, N, I, H, top, par, on_paved, rep):
    """Stone faces under the edges still standing FACE_MIN or more over the (new) ground beside them: the DAE
    files {name: bytes} and their TSStatics in the walls group."""
    n = H.shape[0]
    o1 = P[:, :2] + N * 0.4
    g = terrain_at(H, o1[:, 0], o1[:, 1])                            # right beside the edge (not a slope further out)
    h = P[:, 2] - g
    c = np.clip(np.floor((o1[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64), 0, n - 2)
    r = np.clip(np.floor((o1[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64), 0, n - 2)
    want = on_paved & (h > FACE_MIN) & (h < FACE_MAX) & np.isneginf(top[r, c]) & np.isneginf(top[r + 1, c + 1])
    if len(par):
        want &= cKDTree(par).query(P[:, :2], distance_upper_bound=PARAPET_R)[0] > PARAPET_R    # not a bridge
    builders = {}
    km = 0.0
    for ch in np.unique(I[want]):
        k = np.flatnonzero(I == ch)
        w = want[k].astype(np.int8)
        # gaps of up to FACE_GAP samples closed, runs shorter than FACE_RUN samples dropped
        edges = np.flatnonzero(np.diff(np.r_[0, w, 0]))
        runs = list(zip(edges[0::2], edges[1::2]))
        merged = []
        for a, b in runs:
            if merged and a - merged[-1][1] <= FACE_GAP:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        for a, b in merged:
            if b - a < FACE_RUN:
                continue
            a, b = max(a - 1, 0), min(b + 1, len(k))                 # half a step beyond the ends
            Q, M = P[k[a:b]], N[k[a:b]]
            zt = Q[:, 2] - 0.02
            ht = np.maximum(zt - g[k[a:b]], 0.3)
            xy_t = Q[:, :2] + M * 0.03
            xy_b = Q[:, :2] + M * (0.03 + BATTER * ht)[:, None]
            zb = terrain_at(H, xy_b[:, 0], xy_b[:, 1]) - FACE_SINK
            s = np.r_[0, np.cumsum(np.hypot(*np.diff(Q[:, :2], axis=0).T))]
            T = np.column_stack([xy_t, zt]); B = np.column_stack([xy_b, zb])
            tri = np.concatenate([np.stack([T[:-1], B[:-1], B[1:]], 1), np.stack([T[:-1], B[1:], T[1:]], 1)])
            uv = np.concatenate([np.stack([np.column_stack([s[:-1], zt[:-1]]), np.column_stack([s[:-1], zb[:-1]]),
                                           np.column_stack([s[1:], zb[1:]])], 1),
                                 np.stack([np.column_stack([s[:-1], zt[:-1]]), np.column_stack([s[1:], zb[1:]]),
                                           np.column_stack([s[1:], zt[1:]])], 1)]) / FACE_TILE
            # facing out of the road (the edge has the road on its left)
            nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            flip = (nrm[:, :2] * np.r_[M[:-1], M[:-1]]).sum(1) < 0
            tri[flip] = tri[flip][:, [0, 2, 1]]
            uv[flip] = uv[flip][:, [0, 2, 1]]
            key = tuple(np.floor(Q[len(Q) // 2, :2] / FACE_TILE_M).astype(int))
            V = tri.reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add("mp_wall_stone", V, uvs=uv.reshape(-1, 2),
                                                            normals=bng.flat_normals_soup(V))
            km += s[-1] / 1000
    files, objs = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/walls/shoulder_walls_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * FACE_TILE_M, (ty + 0.5) * FACE_TILE_M, 0.0])
            f = os.path.join(tmp, "s.dae")
            mb.write_dae(f, name=f"shoulder_walls_{tx}_{ty}", origin=origin)
            files[f"levels/{LEVEL_NAME}/{rel}"] = open(f, "rb").read()
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True, decal=False)
            ob["__parent"] = "walls"
            objs.append(ob)
    rep["faces_km"] = round(km, 2)
    return files, objs


def shoulders_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, _, _ = read_ter(data)
    H = Z0 + q.astype(np.float64) / 65535.0 * MAXH

    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    A = np.concatenate([up_faces(t) for m, t in surf.items() if m not in NOT_GROUND])
    paved = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m not in NOT_GROUND + UNPAVED]))
    par = surf.get("mp_bridge_parapet", np.zeros((0, 3, 3))).mean(1)[:, :2] if "mp_bridge_parapet" in surf \
        else np.zeros((0, 2))
    del surf
    S = TriSurface(A)
    P, N, I = samples(boundary(A, S))
    del A
    rep = {"edge_km": round(len(P) * STEP / 1000, 1)}
    # the drop from each edge sample to the ground beside it
    out = P[:, :2] + N * DROP_AT
    drop = P[:, 2] - terrain_at(H, out[:, 0], out[:, 1])
    low = (drop > MIN_LIFT) & (drop <= MAX_DROP)
    rep["edge_km_lower_ground"] = round(float((drop > MIN_LIFT).sum()) * STEP / 1000, 1)
    rep["edge_km_embankment"] = round(float((drop > MAX_DROP).sum()) * STEP / 1000, 1)
    rep["drop_p50_p90"] = [round(float(v), 2) for v in np.percentile(drop[low], [50, 90])] if low.any() else []
    out3 = P[:, :2] + N * TRIM_REACH
    g3 = terrain_at(H, out3[:, 0], out3[:, 1])
    emb = P[:, 2] - g3 > TRIM_DROP
    tree = cKDTree(P[:, :2])

    # the terrain vertices within REACH of an edge
    xs = TER_X0 + np.arange(n) * TER_SQUARE
    ys = TER_Y0 + np.arange(n) * TER_SQUARE
    top = kept_cells(zi, lv, n)
    pad = np.full((n + 1, n + 1), -np.inf, np.float32)
    pad[1:-1, 1:-1] = top
    top = np.maximum(np.maximum(pad[:-1, :-1], pad[:-1, 1:]), np.maximum(pad[1:, :-1], pad[1:, 1:]))   # per vertex
    del pad
    new = H.copy()
    trim = np.full(H.shape, np.inf)
    lifted, metres = 0, 0.0
    band = 512
    for r0 in range(0, n, band):
        for c0 in range(0, n, band):
            gx, gy = np.meshgrid(xs[c0:c0 + band], ys[r0:r0 + band])
            V = np.column_stack([gx.ravel(), gy.ravel()])
            d, k = tree.query(V, distance_upper_bound=REACH)
            ok = np.isfinite(d)
            if not ok.any():
                continue
            idx = np.flatnonzero(ok)
            k = k[idx]
            rr, cc = np.unravel_index(idx, gx.shape)
            rr, cc = rr + r0, cc + c0
            side = ((V[idx] - P[k, :2]) * N[k]).sum(1) > 0               # beyond the edge, not on the road side
            under = np.isfinite(S.height(V[idx, 0], V[idx, 1], "low"))
            outer = side & ~under & low[k]
            inner = under & (d[idx] <= INNER) & low[k]                     # carved deeper than it needs, at the edge
            target = np.where(outer, P[k, 2] - SHOULDER_DZ - SLOPE * np.maximum(d[idx] - FLAT, 0.0), np.inf)
            cand = np.flatnonzero(outer | inner)
            # under every road surface over the four terrain squares of the vertex
            target[cand] = np.minimum(target[cand], road_floor(S, V[idx[cand]]) - MARGIN)
            lift = target - H[rr, cc]
            sel = np.isfinite(target) & (lift > MIN_LIFT) & (lift <= MAX_DROP)   # not a slope falling away
            tv = top[rr, cc]                                              # -inf: nothing there, +inf: railway
            sel &= np.isneginf(tv) | ((tv >= target + STANDS) & ~np.isposinf(tv))
            # beside an embankment: no tooth of the ground carved for the road standing out at road level
            tv = top[rr, cc]
            tsel = side & ~under & emb[k] & (d[idx] <= TRIM_REACH) & ~np.isfinite(tv)
            bound = np.maximum(P[k, 2] - SHOULDER_DZ - TRIM_SLOPE * np.maximum(d[idx] - 0.3, 0.0), g3[k])
            tsel &= H[rr, cc] > bound + MIN_LIFT
            np.minimum.at(trim, (rr[tsel], cc[tsel]), bound[tsel])
            rr, cc, target = rr[sel], cc[sel], target[sel]
            np.maximum.at(new, (rr, cc), target)
    cut = trim < H - MIN_LIFT
    new = np.where(cut, trim, new)
    rep["vertices_trimmed"] = int(cut.sum())
    dz = new - H
    lifted = int((dz > MIN_LIFT).sum())
    metres = float(dz[dz > MIN_LIFT].sum()) if lifted else 0.0
    rep.update({"vertices_raised": lifted, "mean_lift": round(metres / max(lifted, 1), 2),
                "max_lift": round(float(dz.max()), 2)})
    inside = P[:, :2] - N * 0.3
    on_paved = np.isfinite(paved.height(inside[:, 0], inside[:, 1], "near", zhint=P[:, 2]))
    del paved
    files, objs = faces(P, N, I, new, top, par, on_paved, rep)
    q2 = np.clip(np.round((new - Z0) / MAXH * 65535.0), 0, 65535).astype("<u2")
    q2 = np.where(np.abs(dz) > MIN_LIFT, q2, q)                          # the others exactly as they were
    new_ter = data[:5] + q2.tobytes() + data[5 + 2 * n * n:]
    assert len(new_ter) == len(data)
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in files or FACE_SHAPE.search(i.filename):
                continue
            if i.filename == ter_name:
                ni = zipfile.ZipInfo(i.filename, now)      # a new date: the game converts the terrain again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_ter)
            elif i.filename == f"{lv}/main/MissionGroup/walls/items.level.json":
                rows = [o for o in read_items(zi, i.filename) if not FACE_SHAPE.search(o.get("shapeName", ""))]
                zo.writestr(i, ("\n".join(json.dumps(o, separators=(",", ":")) for o in rows + objs) + "\n")
                            .encode("utf-8"), compress_type=i.compress_type)
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, b in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), b, compress_type=zipfile.ZIP_DEFLATED)
    rep["seconds"] = round(time.time() - t0)
    print("road shoulders:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    import sys
    shoulders_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
