"""Dirt and gravel roads and paths flush with the ground (v2.7), in a built level zip.

Up to v2.6 the terrain under every road mesh was carved 0.1 m under the lowest face within one
terrain step (1.5 m) of each vertex (network_mesh.carve_tile): the terrain stays under the faces
whatever the grade, but along a dirt track it leaves a trench 1.5 m wide on both sides and the
track stands on it like a slab, its edge face showing 0.3-0.4 m above the ground (median; asphalt
has kerbs and walls, an unpaved surface has none).

Here the terrain around the unpaved meshes (osm_surface: gravel and dirt on roads, paths, yards)
is raised to their surface instead:
- every terrain vertex within SHOULDER m of an unpaved top face aims at the height of the nearest
  point of the face, EPS under it; from there to BLEND m the aim fades back to the ground, only
  where the ground is lower (an uphill bank stays as it is); no vertex goes down;
- a vertex more than TALL m under that surface is left alone (a road on a wall or a bridge);
- then the aims are lowered as little as needed to keep every terrain triangle under every road
  face (unpaved by EPS, the others by EPS_PAVED), on the faces sampled SUB x SUB per terrain
  square, for both ways the square may be split into triangles: a few passes spread each excess
  on the corners by their weight, the last ones lower all three corners of an offending triangle
  by the whole excess (never under the terrain as it was, which was safe). The blocks are solved
  twice, the second time with the vertices of the neighbouring blocks as the first time left them.
Then the outer edges of the unpaved meshes go down onto the raised terrain (EDGE_UP over it, at
most EDGE_DROP m down), with the top of their edge faces: the edge between track and ground is
1-2 cm instead of 0.3 m. The edges against another surface (asphalt at a junction) and the seams
between two tiles or two polygons stay where they are. The materials and grip, the AI roads and
everything else are copied as they are.

Usage: python patch_unpaved.py <in.zip> <out.zip>
"""
import json, os, re, shutil, struct, sys, tempfile, time, zipfile
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy import ndimage as ndi
import optimize_level
import osm_surface
import road_mesh
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

UNPAVED = tuple(m for g in osm_surface.MATS.values() for c, m in g.items() if c in ("gravel", "dirt"))
EPS = 0.04            # m, terrain under an unpaved face (above the 2.2 cm height step of the .ter)
EPS_PAVED = 0.05      # m, under the other faces (they were carved 0.1 m under the lowest face near)
SHOULDER = 1.5        # m from an unpaved face: the terrain aims at its height
BLEND = 4.5           # m ... fading back to the ground up to here
TALL = 1.0            # m, ground further under the face: a wall or a bridge, not a trench
SUB = 5               # face samples per terrain step
PASSES = 12           # spreading passes before the last, safe one
EDGE_UP = 0.01        # m, an outer edge vertex of an unpaved face over the terrain
EDGE_DROP = 0.25      # m, deepest an edge vertex goes down; further over the terrain: a wall or a bridge
OUT = 0.10            # m beyond an edge: no road face there, the edge is the outer one
BLOCK = 256           # terrain vertices per block side
PAD = 4               # vertices of context around a block (BLEND / TER_SQUARE, rounded up)


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def top_faces(zi, objs, mats=None):
    """(faces of the materials `mats` (default UNPAVED), all) top faces (k, 3, 3) of the TSStatic shapes
    `objs` of the zip."""
    mats = UNPAVED if mats is None else mats
    un, al = [], []
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or not sn.startswith("/levels/"):
            continue
        name = sn.lstrip("/")
        if name not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(name).decode("utf-8"))
        V = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            t = V[idx[:, 0]].reshape(-1, 3, 3)
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            t = t[n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5]
            al.append(t)
            if mat in mats:
                un.append(t)
    return np.concatenate(un), np.concatenate(al)


def read_ter(data):
    n = struct.unpack("<I", data[1:5])[0]
    q = np.frombuffer(data[5:5 + 2 * n * n], "<u2").reshape(n, n)
    return n, q


def corner_weights(u, v):
    """Corners (00, 01, 10, 11 as 0..3: row offset * 2 + column offset) and barycentric weights of
    the points (u along x, v along y, 0..1 in a square) in the triangles of both splits:
    two (k, 3) index and weight arrays per split."""
    out = []
    a = u >= v                                       # split 00-11
    ia = np.where(a[:, None], [0, 1, 3], [0, 2, 3])
    wa = np.where(a[:, None], np.column_stack([1 - u, u - v, v]), np.column_stack([1 - v, v - u, u]))
    out.append((ia, wa))
    b = u + v <= 1                                   # split 01-10
    ib = np.where(b[:, None], [0, 1, 2], [3, 1, 2])
    wb = np.where(b[:, None], np.column_stack([1 - u - v, u, v]), np.column_stack([u + v - 1, 1 - v, 1 - u]))
    out.append((ib, wb))
    return out


# faces of the whole level, set in main() and in every worker (pool(): Windows spawns the workers)
UN = ALL = None
Z0 = MAXH = None
WORKERS = int(os.environ.get("PATCH_WORKERS", min(os.cpu_count(), 4)))   # each holds the faces of the level (~1.5 GB)


def block(args):
    """New heights of the vertices of one block: (rows, cols, z) of the vertices that change.
    Q: the heights as they were (block with PAD vertices around); QA: heights to check instead of
    the aims (the second pass, on the blocks merged: a block only knows its own vertices)."""
    r0, c0, Q, QA = args
    sq, f = TER_SQUARE, TER_SQUARE / SUB
    H = Z0 + Q.astype(np.float64) / 65535.0 * MAXH
    nr, nc = H.shape
    xs = TER_X0 + (c0 - PAD + np.arange(nc)) * sq
    ys = TER_Y0 + (r0 - PAD + np.arange(nr)) * sq
    # face samples at the centres of SUB x SUB cells of every terrain square
    fx = xs[0] + (np.arange((nc - 1) * SUB) + 0.5) * f
    fy = ys[0] + (np.arange((nr - 1) * SUB) + 0.5) * f
    FX, FY = np.meshgrid(fx, fy)
    hu = UN.height(FX.ravel(), FY.ravel(), "low").reshape(FX.shape)
    U = np.isfinite(hu)
    if not U.any():
        return None
    ha = ALL.height(FX.ravel(), FY.ravel(), "low").reshape(FX.shape)
    # aim of every vertex: the nearest unpaved sample (distance from the vertex)
    d, (ir, ic) = ndi.distance_transform_edt(~U, sampling=f, return_indices=True)
    vr = np.clip(np.arange(nr) * SUB - 1, 0, U.shape[0] - 1)       # a sample next to every vertex
    vc = np.clip(np.arange(nc) * SUB - 1, 0, U.shape[1] - 1)
    D = d[np.ix_(vr, vc)] - 0.5 * f * np.sqrt(2)
    R = hu[ir[np.ix_(vr, vc)], ic[np.ix_(vr, vc)]] - EPS
    w = np.clip((BLEND - D) / (BLEND - SHOULDER), 0.0, 1.0)
    aim = np.where(w > 0, H + w * (R - H), H)
    aim = np.where((R - H < TALL) & (D < BLEND), np.maximum(aim, H), H)
    if QA is not None:
        aim = Z0 + QA.astype(np.float64) / 65535.0 * MAXH
    moved = aim > H + 1e-4
    if not moved.any():
        return None
    # the constraints: samples on a face, in a square with a corner that moved
    sqm = moved[:-1, :-1] | moved[:-1, 1:] | moved[1:, :-1] | moved[1:, 1:]
    near = np.repeat(np.repeat(sqm, SUB, 0), SUB, 1) & np.isfinite(ha)
    sr, sc = np.nonzero(near)
    lim = ha[sr, sc] - np.where(U[sr, sc] & (np.abs(hu[sr, sc] - ha[sr, sc]) < 1e-6), EPS, EPS_PAVED)
    qr, qc = sr // SUB, sc // SUB                                 # square of every sample
    u = (sc % SUB + 0.5) / SUB
    v = (sr % SUB + 0.5) / SUB
    flat = lambda k: (qr + k // 2) * nc + (qc + k % 2)
    corners = [flat(k) for k in range(4)]
    splits = []
    for idx, wt in corner_weights(u, v):
        vid = np.stack([np.choose(idx[:, j], corners) for j in range(3)], 1)
        splits.append((vid, wt))
    Z = aim.ravel().copy()
    Hf = H.ravel()

    def excess():
        for vid, wt in splits:
            ex = (Z[vid] * wt).sum(1) - lim
            bad = (ex > 0) & (Z[vid] > Hf[vid] + 1e-6).any(1)     # a square as it was is safe
            yield vid[bad], wt[bad], ex[bad]
    for p in range(PASSES):                     # least change of the corners for every sample
        drop = np.zeros_like(Z)
        for vid, wt, ex in excess():
            corr = ex[:, None] * wt / (wt ** 2).sum(1)[:, None]
            np.maximum.at(drop, vid.ravel(), corr.ravel())
        if not drop.any():
            break
        Z = np.maximum(Z - drop, Hf)            # never under the ground as it was (it was safe)
    for p in range(50):                         # safe: the whole excess on every corner
        drop = np.zeros_like(Z)
        for vid, wt, ex in excess():
            np.maximum.at(drop, vid.ravel(), np.repeat(ex, 3))
        if not drop.any():
            break
        Z = np.maximum(Z - drop, Hf)
    else:                                       # still crossing: those corners back where they were
        for vid, wt, ex in excess():
            Z[vid.ravel()] = Hf[vid.ravel()]
    Z = Z.reshape(nr, nc)
    core = (slice(PAD, nr - PAD), slice(PAD, nc - PAD))
    ch = Z[core] > H[core] + 1e-4
    if not ch.any():
        return None
    rr, cc = np.nonzero(ch)
    return r0 + rr, c0 + cc, Z[core][rr, cc]


def terrain_top(Zt, x, y):
    """Height of the terrain at points, the higher of the two ways a square may be split."""
    c = (x - TER_X0) / TER_SQUARE
    r = (y - TER_Y0) / TER_SQUARE
    ci, ri = np.floor(c).astype(np.int64), np.floor(r).astype(np.int64)
    u, v = c - ci, r - ri
    z00, z01, z10, z11 = (Zt[ri + i, ci + j].astype(np.float64) for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
    a = np.where(u >= v, z00 + u * (z01 - z00) + v * (z11 - z01), z00 + v * (z10 - z00) + u * (z11 - z10))
    b = np.where(u + v <= 1, z00 + u * (z01 - z00) + v * (z10 - z00), z11 + (1 - u) * (z10 - z11) + (1 - v) * (z01 - z11))
    return Z0 + np.maximum(a, b) / 65535.0 * MAXH


QT = None             # the patched terrain (uint16): main() and terrain() in the workers


def init(files, z0, maxh):
    global UN, ALL, Z0, MAXH
    if UN is None:                    # spawned: not a fork of main()
        UN, ALL = (road_mesh.TriSurface(np.load(files[k])) for k in ("un", "al"))
    Z0, MAXH = z0, maxh


def pool(tmp, un, al):
    """Workers with the faces of the whole level: through .npy files in `tmp`, too big for the pipe
    of a spawned worker."""
    files = {k: os.path.join(tmp, k + ".npy") for k in ("un", "al")}
    np.save(files["un"], un)
    np.save(files["al"], al)
    return ProcessPoolExecutor(max_workers=WORKERS, initializer=init, initargs=(files, Z0, MAXH))


def terrain(path):
    """The patched terrain in a worker (written by main() after the workers started)."""
    global QT
    if QT is None:
        QT = np.load(path, mmap_mode="r")
    return QT


def taper(args):
    """The outer edges of the unpaved faces of one shape down onto the terrain: new DAE text, or None.
    An edge vertex goes down to EDGE_UP over the terrain where that is at most EDGE_DROP m down, with
    the top of the edge face under it; the vertices of the faces of another surface, and those on
    an edge with a road face beyond it (a seam between two tiles or two polygons), stay.
    v2.8: args may add the materials (default UNPAVED) and the deepest drop (default EDGE_DROP)."""
    name, text, pos, qpath = args[:4]
    mats = args[4] if len(args) > 4 else UNPAVED
    edge_drop = args[5] if len(args) > 5 else EDGE_DROP
    qt = terrain(qpath)
    V, _, _, _, parts, _ = optimize_level.parse(text)
    W = V + pos
    key = np.round(W * 1000).astype(np.int64)
    _, pid = np.unique(key, axis=0, return_inverse=True)
    pid = pid.ravel()
    tops, kinds, steep = [], [], []
    for mat, idx in parts:
        T = idx[:, 0].reshape(-1, 3)
        t = W[T]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
        tops.append(T[up])
        kinds.append(np.full(up.sum(), mat in mats))
        if mat in mats:
            steep.append(T[~up].ravel())
    T = np.concatenate(tops)
    un = np.concatenate(kinds)
    if not un.any():
        return None
    P = pid[T]
    blocked = np.zeros(pid.max() + 1, bool)
    blocked[P[~un].ravel()] = True
    E = np.concatenate([P[:, [0, 1]], P[:, [1, 2]], P[:, [2, 0]]])
    F = np.tile(np.arange(len(T)), 3)
    Es = np.sort(E, 1)
    _, inv, cnt = np.unique(Es, axis=0, return_inverse=True, return_counts=True)
    b = (cnt[inv.ravel()] == 1) & un[F]
    Eb, Fb = E[b], F[b]
    rep = np.zeros(pid.max() + 1, np.int64)               # one vertex of every position
    rep[pid] = np.arange(len(pid))
    A, B = W[rep[Eb[:, 0]]], W[rep[Eb[:, 1]]]
    mid = 0.5 * (A + B)
    d = B[:, :2] - A[:, :2]
    nrm = np.column_stack([d[:, 1], -d[:, 0]]) / np.maximum(np.linalg.norm(d, axis=1), 1e-9)[:, None]
    cen = W[T[Fb]].mean(1)
    nrm *= np.where(((mid[:, :2] - cen[:, :2]) * nrm).sum(1) < 0, -1.0, 1.0)[:, None]
    q = mid[:, :2] + OUT * nrm
    outer = np.isnan(ALL.height(q[:, 0], q[:, 1], "low"))
    on_edge = np.zeros(len(blocked), bool)
    inner_edge = np.zeros(len(blocked), bool)
    on_edge[Eb.ravel()] = True
    inner_edge[Eb[~outer].ravel()] = True
    move = np.flatnonzero(on_edge & ~inner_edge & ~blocked)
    if not len(move):
        return None
    X = W[rep[move]]
    drop = X[:, 2] - (terrain_top(qt, X[:, 0], X[:, 1]) + EDGE_UP)
    ok = (drop > 0.002) & (drop <= edge_drop)
    move, drop, X = move[ok], drop[ok], X[ok]
    if not len(move):
        return None
    dz = np.zeros(len(blocked))
    dz[move] = drop
    V2 = V.copy()
    V2[:, 2] -= dz[pid]
    # the tops of the edge faces (the strips of optimize_level moved them by up to 4 mm)
    sv = np.unique(np.concatenate(steep)) if steep else np.zeros(0, np.int64)
    sv = sv[dz[pid[sv]] == 0]
    if len(sv):
        from scipy.spatial import cKDTree
        dist, j = cKDTree(X).query(W[sv], distance_upper_bound=0.01)
        hit = np.isfinite(dist)
        V2[sv[hit], 2] -= drop[j[hit]]
    fmt = " ".join(("%.3f" % v).rstrip("0").rstrip(".") for v in V2.ravel())
    out = re.sub(r'(<float_array id="g-pa" count="\d+">)[^<]*(</float_array>)',
                 lambda m: m.group(1) + fmt + m.group(2), text, count=1)
    return name, out, len(move)


def cell_ids(x, y):
    """Ids of the 1 m cells (over the terrain block) of points."""
    from config import TER_SIZE
    w = int(np.ceil(TER_SIZE * TER_SQUARE))
    return np.floor(np.asarray(y) - TER_Y0).astype(np.int64) * w + np.floor(np.asarray(x) - TER_X0).astype(np.int64)


def in_cells(cells, x, y):
    """Points in the sorted cell ids `cells`."""
    c = cell_ids(x, y)
    i = np.clip(np.searchsorted(cells, c), 0, max(len(cells) - 1, 0))
    return (cells[i] == c) if len(cells) else np.zeros(len(c), bool)


def main(src, dst, mats=None, edge_drop=EDGE_DROP, keep_out=None):
    """mats: the materials whose surroundings are raised and whose outer edges go down (default UNPAVED);
    edge_drop: the deepest an edge goes down (0: the faces stay as they are, only the terrain is raised);
    keep_out: sorted 1 m cell ids (cell_ids) whose faces raise no terrain and whose terrain vertices stay as they
    were (v2.8, patch_paved_edges.py)."""
    global UN, ALL, Z0, MAXH, QT
    mats = UNPAVED if mats is None else tuple(mats)
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    objs = read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json")
    un, al = top_faces(zi, objs, mats)
    if keep_out is not None:                    # no terrain raised to the faces there
        c = un.mean(1)
        un = un[~in_cells(keep_out, c[:, 0], c[:, 1])]
    print("top faces: %d of %s, %d in all" % (len(un), "the unpaved" if mats == UNPAVED else "these", len(al)))
    UN, ALL = road_mesh.TriSurface(un), road_mesh.TriSurface(al)
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q = read_ter(data)
    q = q.copy()
    # blocks with an unpaved face
    cr = np.floor((un[:, :, 1].mean(1) - TER_Y0) / TER_SQUARE / BLOCK).astype(int)
    cc = np.floor((un[:, :, 0].mean(1) - TER_X0) / TER_SQUARE / BLOCK).astype(int)
    keys = sorted(set(zip(cr.tolist(), cc.tolist())))
    q0 = q.copy()
    tmp = tempfile.mkdtemp(prefix="patch_unpaved_")

    ex = pool(tmp, un, al)

    def run(qa):
        jobs = []
        for br, bc in keys:
            r0, c0 = br * BLOCK, bc * BLOCK
            ra, rb, ca, cb = r0 - PAD, r0 + BLOCK + PAD + 1, c0 - PAD, c0 + BLOCK + PAD + 1
            if ra < 0 or ca < 0 or rb > n or cb > n:
                continue                                # the edge of the terrain: no roads there
            jobs.append((r0, c0, q0[ra:rb, ca:cb], None if qa is None else qa[ra:rb, ca:cb]))
        out = q0.copy()
        for res in ex.map(block, jobs, chunksize=2):
            if res is not None:
                rr, cc, z = res
                qn = np.floor((z - Z0) / MAXH * 65535.0).astype(np.int64)    # down: never over a face
                up = qn > q0[rr, cc]
                out[rr[up], cc[up]] = qn[up].astype(np.uint16)
        return out
    print("%d blocks with unpaved faces" % len(keys))
    q = run(None)
    q = run(q)          # the vertices along the edges of the blocks, checked with both sides known
    if keep_out is not None:                    # the ground there as it was, also where a face farther off raised it
        rr, cc = np.nonzero(q != q0)
        back = in_cells(keep_out, TER_X0 + cc * TER_SQUARE, TER_Y0 + rr * TER_SQUARE)
        q[rr[back], cc[back]] = q0[rr[back], cc[back]]
        print("terrain vertices in the keep-out left as they were: %d" % back.sum())
    ch = q != q0
    lift = (q[ch].astype(np.float64) - q0[ch]) / 65535.0 * MAXH
    print("terrain vertices raised: %d, by median %.2f m, 95th percentile %.2f m, at most %.2f m"
          % (ch.sum(), np.median(lift), np.percentile(lift, 95), lift.max()))
    QT = q
    qpath = os.path.join(tmp, "qt.npy")
    np.save(qpath, q)
    jobs = []
    for o in objs if edge_drop > 0 else ():             # edge_drop 0: the faces stay as they are
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") == "TSStatic" and sn in zi.NameToInfo:
            text = zi.read(sn).decode("utf-8")
            if any(f'material="{m}-mat"' in text for m in mats):
                jobs.append((sn, text, np.asarray(o.get("position", [0, 0, 0]), np.float64), qpath, mats, edge_drop))
    shapes, nmove = {}, 0
    with ex:
        for res in ex.map(taper, jobs, chunksize=1):
            if res is not None:
                shapes[res[0]] = res[1].encode("utf-8")
                nmove += res[2]
    print("edge vertices lowered onto the terrain: %d, in %d shapes" % (nmove, len(shapes)))
    new_ter = data[:5] + q.astype("<u2").tobytes() + data[5 + 2 * n * n:]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename == ter_name or i.filename in shapes:
                # a new date: the game converts the shapes again instead of taking its cached ones
                ni = zipfile.ZipInfo(i.filename, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_ter if i.filename == ter_name else shapes[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    shutil.rmtree(tmp, ignore_errors=True)
    print("%s written" % dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
