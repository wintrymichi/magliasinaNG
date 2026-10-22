"""The thickness and the ridges of the roofs (v3.1).

swissBUILDINGS3D models a roof as its surface alone: in the level every roof was a sheet with no thickness,
a blade seen edge-on at the eaves and gables, and its ridges and hips were plain folds of the tiles (michi
2026-10-22: a lake-shore house in the cinematic video, "aumenta il dettaglio nei tetti"). Here, from the roof
triangles of one building (buildings_mesh.build, after orient: facing up):
- rim: along every edge of the roof that no other roof face continues (eaves, verges, the step between two roof
  planes), chained into straight runs: the heads of the tiles in the roof's own covering, from the edge RIM_OUT m
  out and RIM_TILE m down, and under them a fascia board down to RIM_FASCIA m under the roof (flat roofs: a metal
  coping RIM_COPING m high, no board); 4 triangles a run. The soffits (buildings_mesh.soffits) close the eaves from below;
- ridge caps: along every convex fold between two pitched faces (ridges and hips; valleys are concave and get
  none), a row of half-round caps RIDGE_W m wide and RIDGE_H m high over the fold, in the covering of the roof
  (coppi caps on coppi and tegole, slabs on piode, a folded flashing on metal), closed at their free ends.
A finishing step of build_level.py (FINISH, after house_details and house_extras, which read the roofs as the
survey has them), on the built level: only triangles are added to the building shapes;
alone: python build_level.py --finish roof_details
"""
import json, os, re, tempfile, time, zipfile
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
import bng
import optimize_level
from bld_textures import ROOF_TILE
from config import LEVEL_NAME
from lamps import read_items

WELD = 0.02                     # m: roof corners closer than this are one
RIM_OUT = 0.03                  # m the heads stand out of the roof's edge (off the wall face under a flush eave)
RIM_TILE = 0.05                 # m: the heads of the tiles
RIM_FASCIA = 0.22               # m under the roof: the foot of the fascia board
RIM_COPING = 0.08               # m: the coping of a flat roof
RIM_MIN = 0.3                   # m: shorter runs of rim are left out
RIDGE_W, RIDGE_H = 0.15, 0.11   # m: half width of a ridge cap on each face, its height over the fold
RIDGE_SLOPE = 12.0              # degrees: both faces at least this steep
RIDGE_FOLD = 8.0                # degrees between the two faces at least
RIDGE_MIN = 0.4                 # m
COLLINEAR = 0.02                # sine of the angle under which two edges of a run continue each other
PITCHED = ("coppi", "tegole", "piode", "metal")


def weld(P, r=WELD):
    """Ids (n,) of the points P (n, 3) welded by distance (pairs within r, joined transitively)."""
    pairs = cKDTree(P).query_pairs(r, output_type="ndarray")
    n = len(P)
    if not len(pairs):
        return np.arange(n)
    M = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(M, directed=False)[1]


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _runs(A, B, side):
    """Straight runs of the edges A, B (k, 3) with their side vectors side (k, 3): consecutive edges that share an
    end, continue each other and have the same side are one run. Returns (A, B, side) of the runs."""
    k = len(A)
    if not k:
        return A, B, side
    ends = np.concatenate([A, B])
    eid = weld(ends, 1e-3)
    ea, eb = eid[:k], eid[k:]
    d = _unit(B - A)
    by_v = {}
    for i in range(k):
        by_v.setdefault(ea[i], []).append(i)
        by_v.setdefault(eb[i], []).append(i)
    rows, cols = [], []
    for v, es in by_v.items():
        if len(es) != 2:
            continue
        i, j = es
        if np.linalg.norm(np.cross(d[i], d[j])) < COLLINEAR and float(side[i] @ side[j]) > 0.95:
            rows.append(i)
            cols.append(j)
    if rows:
        lab = connected_components(coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(k, k)), directed=False)[1]
    else:
        lab = np.arange(k)
    oA, oB, oS = [], [], []
    for g in np.unique(lab):
        sel = np.flatnonzero(lab == g)
        dd = d[sel[0]]
        pts = np.concatenate([A[sel], B[sel]])
        t = (pts - pts[0]) @ dd
        oA.append(pts[np.argmin(t)])
        oB.append(pts[np.argmax(t)])
        oS.append(side[sel[0]])
    return np.array(oA), np.array(oB), np.array(oS)


def _quad(a, b, c, d):
    return [(a, b, c), (a, c, d)]


def _facing(tris, want):
    """The triangles (list of 3-tuples) turned to face along `want` (3,)."""
    out = []
    for t in tris:
        t = np.array(t)
        n = np.cross(t[1] - t[0], t[2] - t[0])
        out.append(t[::-1] if float(n @ want) < 0 else t)
    return out


def _edges(roofs):
    """Welded edge table of roof triangles (k, 3, 3): (vertex ids (k, 3), unique edges (m, 2), the faces of each
    edge as a list)."""
    ids = weld(roofs.reshape(-1, 3)).reshape(-1, 3)
    E = np.sort(np.concatenate([ids[:, [0, 1]], ids[:, [1, 2]], ids[:, [2, 0]]]), 1)
    F = np.tile(np.arange(len(ids)), 3)
    U, inv = np.unique(E, axis=0, return_inverse=True)
    faces = [[] for _ in range(len(U))]
    for e, f in zip(inv.ravel(), F):
        faces[e].append(f)
    return ids, U, faces


def details(roofs, kinds):
    """[(kind, tris (k, 3, 3), uvs (k * 3, 2))] of the rim and the ridge caps of one building's roofs (k, 3, 3),
    kinds (k,) the covering of each face (facades.roof_kind); kind "fascia" is the board under the rim (plaster)."""
    out = []
    if not len(roofs):
        return out
    roofs = np.asarray(roofs, np.float64)
    kinds = np.asarray(kinds)
    ids, U, faces = _edges(roofs)
    P = np.zeros((ids.max() + 1, 3))
    P[ids.ravel()] = roofs.reshape(-1, 3)
    nrm = np.cross(roofs[:, 1] - roofs[:, 0], roofs[:, 2] - roofs[:, 0])
    area2 = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.maximum(area2, 1e-12)[:, None]
    slope = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]), 0, 1)))
    ctr = roofs.mean(1)

    # ---- rim: edges of one face
    rim = [(e, fs[0]) for e, fs in enumerate(faces) if len(fs) == 1 and area2[fs[0]] > 1e-6]
    groups = {}
    for e, f in rim:
        a, b = P[U[e, 0]], P[U[e, 1]]
        h = b[:2] - a[:2]
        if np.linalg.norm(h) < 0.05:                      # an upright edge: nothing to hang under it
            continue
        o = np.array([-h[1], h[0]]) / np.linalg.norm(h)
        if float(o @ (ctr[f, :2] - a[:2])) > 0:
            o = -o
        groups.setdefault(kinds[f], []).append((a, b, np.r_[o, 0.0]))
    for kind, es in groups.items():
        A, B, S = _runs(*(np.array(x) for x in zip(*es)))
        flat = kind not in PITCHED
        cover, board = [], []
        for a, b, s in zip(A, B, S):
            if np.linalg.norm(b - a) < RIM_MIN:
                continue
            g = s * RIM_OUT
            dz = np.array([0, 0, RIM_COPING if flat else RIM_TILE])
            # the heads of the tiles: from the roof's edge out and down (a lip off a flush wall, no slit above it)
            cover += _facing(_quad(a, b, b + g - dz, a + g - dz), s + np.array([0, 0, 0.5]))
            if not flat:
                fz = np.array([0, 0, RIM_FASCIA])
                board += _facing(_quad(a + g - dz, b + g - dz, b + g - fz, a + g - fz), s)
        mat = "metal" if flat else kind
        if cover:
            out.append((mat, np.array(cover), _uv_along(np.array(cover))))
        if board:
            out.append(("fascia", np.array(board), _uv_along(np.array(board))))

    # ---- ridge caps: convex folds between two pitched faces
    caps = {}
    for e, fs in enumerate(faces):
        if len(fs) != 2:
            continue
        f1, f2 = fs
        if min(slope[f1], slope[f2]) < RIDGE_SLOPE or kinds[f1] not in PITCHED:
            continue
        n1, n2 = nrm[f1], nrm[f2]
        if float(n1 @ n2) > np.cos(np.radians(RIDGE_FOLD)):
            continue
        a, b = P[U[e, 0]], P[U[e, 1]]
        if np.linalg.norm(b - a) < 0.05:
            continue
        # convex: each face's far corner below the other face's plane
        if float(n1 @ (ctr[f2] - a)) > -0.01 or float(n2 @ (ctr[f1] - a)) > -0.01:
            continue
        caps.setdefault(kinds[f1], []).append((a, b, _unit(n1 + n2), n1, n2, ctr[f1], ctr[f2]))
    for kind, es in caps.items():
        tris = []
        A = np.array([x[0] for x in es])
        B = np.array([x[1] for x in es])
        S = np.array([x[2] for x in es])
        A, B, S = _runs(A, B, S)
        ends = weld(np.concatenate([A, B]), 0.05)
        cnt = np.bincount(ends)
        for i, (a, b, bis) in enumerate(zip(A, B, S)):
            L = np.linalg.norm(b - a)
            if L < RIDGE_MIN:
                continue
            _, _, _, n1, n2, c1, c2 = min(es, key=lambda x: float(np.linalg.norm(x[2] - bis)))
            d = (b - a) / L
            w1, w2 = _unit(np.cross(n1, d)), _unit(np.cross(n2, d))
            if float(w1 @ (c1 - a)) < 0:
                w1 = -w1
            if float(w2 @ (c2 - a)) < 0:
                w2 = -w2
            flat_cap = kind == "metal"
            h = RIDGE_H * (0.35 if flat_cap else 1.0)
            prof = [w1 * RIDGE_W + n1 * 0.004, w1 * RIDGE_W * 0.45 + bis * h, w2 * RIDGE_W * 0.45 + bis * h,
                    w2 * RIDGE_W + n2 * 0.004]
            for p, q in zip(prof, prof[1:]):
                mid = (p + q) / 2
                tris += _facing(_quad(a + p, b + p, b + q, a + q), mid - bis * h * 0.3)
            for end, P0, out_d in ((0, a, -d), (1, b, d)):
                if cnt[ends[i + end * len(A)]] > 1:
                    continue                                   # the cap goes on into the next run (a hip)
                for p, q in zip(prof, prof[1:]):
                    tris += _facing([(P0, P0 + p, P0 + q)], out_d)
        if tris:
            T = np.array(tris)
            out.append((kind, T, _uv_along(T)))
    return out


def _uv_along(T, tile=2.0):
    """Texture coordinates of thin strips (k, 3, 3): u along the longest side of each triangle, v across (m / tile)."""
    T = np.asarray(T, np.float64)
    e = np.stack([T[:, 1] - T[:, 0], T[:, 2] - T[:, 1], T[:, 0] - T[:, 2]], 1)
    d = _unit(e[np.arange(len(T)), np.argmax(np.linalg.norm(e, axis=2), 1)])
    u = (T * d[:, None]).sum(-1)
    rel = T - T[:, :1]
    v = np.linalg.norm(rel - (rel * d[:, None]).sum(-1)[..., None] * d[:, None], axis=-1)
    return (np.stack([u, v], -1) / tile).reshape(-1, 2)


# ------------------------------------------------------------------ the finishing step
ROOF_MAT = re.compile(r"^bld_roof_(coppi|tegole|piode|flat|metal)$")
FASCIA_TONE = 0.8               # the board in the wall's plaster, darker (as the soffits)


def shape_details(V, UV, C, parts):
    """{material: (triangles (k, 3, 3), uvs, colours (k * 3, 4))} to add to one building shape (V in its own frame)."""
    roofs, kinds, rcol = [], [], []
    for m, idx in parts:
        g = ROOF_MAT.match(m)
        if not g:
            continue
        t = V[idx[:, 0]].reshape(-1, 3, 3)
        roofs.append(t)
        kinds += [g.group(1)] * len(t)
        rcol.append(C[idx[0::3, 3]] if C is not None and idx.shape[1] > 3 else np.ones((len(t), 4)))
    if not roofs:
        return {}
    roofs, kinds, rcol = np.concatenate(roofs), np.array(kinds), np.concatenate(rcol)
    rtree = cKDTree(roofs.mean(1))
    wall = [(V[idx[:, 0]].reshape(-1, 3, 3).mean(1), C[idx[0::3, 3]] if C is not None and idx.shape[1] > 3
             else np.ones((len(idx) // 3, 4))) for m, idx in parts if m == "bld_plaster"]
    wtree = cKDTree(np.concatenate([w[0] for w in wall])) if wall else None
    wcol = np.concatenate([w[1] for w in wall]) if wall else None
    out = {}
    for kind, T, uv in details(roofs, kinds):
        if kind == "fascia":
            mat = "bld_plaster"
            if wtree is not None:
                c = wcol[wtree.query(T.mean(1))[1]].copy()
                c[:, :3] *= FASCIA_TONE
            else:
                c = np.tile([0.7, 0.68, 0.64, 1.0], (len(T), 1))
        else:
            mat = f"bld_roof_{kind}"
            c = rcol[rtree.query(T.mean(1))[1]]
            uv = _uv_along(T, ROOF_TILE[kind])
        a = out.setdefault(mat, ([], [], []))
        a[0].append(T)
        a[1].append(uv)
        a[2].append(np.repeat(c, 3, axis=0))
    return {m: (np.concatenate(a[0]), np.concatenate(a[1]), np.concatenate(a[2])) for m, a in out.items()}


def roof_details_step(root, report=None):
    """The rim and the ridge caps added to the roofs of every building shape of the level (details): only
    triangles are added, in the materials of the roofs (and the plaster for the fascia board)."""
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    res = {"shapes": 0, "shapes_rewritten": 0, "triangles_before": 0, "triangles_added": 0, "by_material": {}}
    new_dae = {}
    tmp = tempfile.mkdtemp()
    for o in read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or not sn.endswith(".dae"):
            continue
        text = zi.read(sn).decode("utf-8")
        if "<triangles" not in text or "bld_roof_" not in text:
            continue
        V, N, UV, C, parts, node = optimize_level.parse(text)
        res["shapes"] += 1
        res["triangles_before"] += sum(len(idx) // 3 for _, idx in parts)
        add = shape_details(V, UV, C, parts)
        if not add:
            continue
        mb = bng.MeshBuilder()
        for mat, idx in parts:
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[idx[:, 0]], uvs=UV[idx[:, 2]], normals=N[idx[:, 1]], colors=col)
        for mat, (T, uv, col) in add.items():
            W = T.reshape(-1, 3)
            mb.add(mat, W, uvs=uv, normals=bng.flat_normals_soup(W), colors=col)
            res["triangles_added"] += len(T)
            res["by_material"][mat] = res["by_material"].get(mat, 0) + len(T)
        base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
        path = os.path.join(tmp, "s.dae")
        mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
        new_dae[sn] = open(path, "rb").read()
        os.remove(path)
        if res["shapes"] % 50 == 0:
            print("roof details: %d shapes, %.0f s" % (res["shapes"], time.time() - t0), flush=True)
    os.rmdir(tmp)
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new_dae:
                ni = zipfile.ZipInfo(i.filename, now)          # a new date: the game converts the shape again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    res["shapes_rewritten"] = len(new_dae)
    res["seconds"] = round(time.time() - t0)
    print("roof details:", res, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res
