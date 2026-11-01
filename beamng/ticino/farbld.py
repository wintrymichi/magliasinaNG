"""Far buildings: the houses beyond the streamed ones (buildings radius 6 tiles, ~2.3 km) as light static shapes, so
towns and villages stand on the far ground out to the horizon instead of ending in a ring round the car (michi
2026-11-01: "gli alberi devono vedersi sempre come anche le case", "ottimizza la mappa in modo che si possano fare
riprese aeree comunque dettagliate"). Two levels, as the far trees (fartrees.py, objects.lua far sets):
- fine (farbld/b_<cx>_<cy>.cdae, one per 384 m tile): each house's own roof planes with plain walls, near (to ~4 km);
- coarse (farbld/l2_<bx>_<by>.cdae, one per L2_TILES x L2_TILES tiles, 1,536 m): one box per house of L2_MIN_AREA or
  more (its footprint box, from its foot to its mean roof height, the roof's colour on top), beyond.

Made from the level's own building shapes (the slices' z/<zone>/art/shapes/buildings/bld*.cdae, the entries of the
buildings group of tiles/o_<cx>_<cy>.json), so a far house is the house the car finds when it gets there:
- the roof planes as they are (the bld_roof_* triangles facing up), without the rims, tile heads and ridge caps of
  roof_details (connected pieces under MIN_WIDTH across or MIN_AREA: thin strips at the eaves and on the ridges);
- walls straight down from every free edge of the roof planes (eaves, verges, steps) to the house's foot, the lowest
  wall vertex under it, SINK lower: gables come out of the verges by themselves, the eaves overhang is in the wall
  (0.3-1 m, nothing at 2 km), no windows, plinths or details;
- colours: each roof vertex its own colour times the mean of its covering's texture; the walls the median wall colour
  of the house times the plaster's (stone, ashlar) mean. Material tc_far_ground (vertex colours, no shadows).
A far building tile holds exactly the buildings of the o tile with the same key: objects.lua swaps a tile's real
buildings and its far ones at the buildings' radius.

Per building also one record (records(): centre, the two half axes of its footprint box, height of its roof and foot,
roof and wall colour, plan area): the coarse blocks are made from them.

    farbld.build(read_slices(sl, zones), origin, tile_m, out_dir) -> (fine keys, coarse keys)    (region_base.py)
    python farbld.py --level <a levels/ticino folder of local slices> --out <folder>             (a test)
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402

DIR = "farbld"
MAT = "tc_far_houses"            # white x vertex colours, no shadows (as the far ground: drawn beyond the shadows)
GROUP = "buildings"              # the scene group of the houses (not buildings/details, buildings/extras)
UP = 0.2                         # a roof face faces up: normal z over this
STEEP = 0.55                     # and a steeper face (the tile heads of the rims, ~60 degrees) is kept only from
STEEP_AREA = 2.0                 # this many m2 (towers, spires)
MIN_AREA = 1.0                   # m2: a smaller connected piece of roof is a detail (cap, rim, coping)
MIN_WIDTH = 0.7                  # m across (2 x sqrt(3) x the spread of its corners): thinner is a rim or a cap
MIN_HOUSE = 12.0                 # m2 in plan: smaller roofs (sheds, bins, canopies) are left out at 2 km
WELD_MM = 2                      # roof corners on the same mm grid are one
SINK = 2.0                       # m: the walls go this far under the lowest wall vertex (the far ground is coarser)
FOOT_REACH = 3.0                 # m: a wall vertex belongs to the house of the nearest roof corner within this
NO_WALL_DROP = 3.0               # m under the roof's lowest corner: the foot of a roof with no wall found under it
COLLINEAR = 0.02                 # sine: consecutive free edges this close to one line are one wall
MERGE_DZ = 0.15                  # m: and only while their top stays this close to the line between the two ends
# mean colour (sRGB 0..1) of the coverings' textures (art/shapes/buildings/t_*_b.color.png, measured 2026-11-01 on
# ticino_base_1.zip): the shapes' vertex colours multiply them (vertColor), the far material has no texture
TEX_MEAN = {
    "bld_roof_coppi": (156.5, 146.6, 138.6), "bld_roof_tegole": (187.0, 175.7, 167.1),
    "bld_roof_piode": (179.7, 172.4, 161.3), "bld_roof_flat": (210.6, 208.5, 202.3),
    "bld_roof_metal": (196.3, 196.3, 198.1),
    "bld_plaster": (227.3, 226.1, 223.9), "bld_stone": (109.9, 106.7, 96.4), "bld_ashlar": (156.1, 152.6, 143.4),
    "bld_landmark": (132.2, 127.0, 118.4), "bld_landmark_lit": (132.2, 127.0, 118.4),
}
TEX_FILE = {"bld_roof_coppi": "t_roof_coppi_b", "bld_roof_tegole": "t_roof_tegole_b",
            "bld_roof_piode": "t_roof_piode_b", "bld_roof_flat": "t_roof_flat_b", "bld_roof_metal": "t_roof_metal_b",
            "bld_plaster": "t_bld_plaster_b", "bld_stone": "t_bld_stone_b", "bld_ashlar": "t_bld_ashlar_b",
            "bld_landmark": "t_bld_landmark_b", "bld_landmark_lit": "t_bld_landmark_b"}
ROOF = re.compile(r"^bld_roof_")
WALL = re.compile(r"^bld_(plaster|stone|ashlar|landmark|landmark_lit)$")
WALL_DEFAULT = (0.82, 0.80, 0.76)
# a far tile's shape: kept under the engine's 16-bit vertex indices
VERTS_MAX = 65000
L2_TILES = 4                     # coarse blocks of 4 x 4 tiles (1,536 m), the far trees' blocks (objects.lua far sets)
L2_MIN_AREA = 40.0               # m2 in plan: smaller houses (garages, sheds: 2-3 px at 4 km) are not in the blocks
L2_MIN_HALF = 1.5                # m: the narrowest half side of a box


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def texture_means(level_dir):
    """TEX_MEAN, measured again from the level's own textures where they are there."""
    out = dict(TEX_MEAN)
    try:
        from PIL import Image
    except ImportError:
        return out
    d = os.path.join(level_dir, "art", "shapes", "buildings")
    for mat, base in TEX_FILE.items():
        p = os.path.join(d, base + ".color.png")
        if os.path.isfile(p):
            try:
                im = np.asarray(Image.open(p).convert("RGB"), np.float64)
                out[mat] = tuple(float(v) for v in im.reshape(-1, 3).mean(0))
            except OSError:
                pass
    return out


# ------------------------------------------------------------------ one shape
def shape_parts(data, pos, tex_mean=TEX_MEAN):
    """The roof faces (k, 3, 3) world, their corners' colours (k, 3, 3) 0..1, and the wall corners (m, 3) world with
    their colours (m, 3) of one building shape placed at pos (no rotation: the merged building shapes have none)."""
    s = cdae.decode(data)
    mats = [m["name"] for m in s["materials"]]
    m = next((mm for mm in s["meshes"] if mm.get("type") == 0), None)
    if m is None:
        return None
    a = cdae.mesh_arrays(m)
    V = a["verts"].astype(np.float64) + np.asarray(pos, np.float64)[:3]
    I = a["indices"]
    nC = m["colors"][0]
    C = (np.frombuffer(m["colors"][2], np.uint8).reshape(-1, 4)[:, :3].astype(np.float64) / 255.0
         if nC == len(V) else np.ones((len(V), 3)))
    roofT, roofC, wallP, wallC = [], [], [], []
    for start, count, mat in a["primitives"]:
        mi = int(mat) & 0x0FFFFFFF
        name = mats[mi] if 0 <= mi < len(mats) else ""
        if not (ROOF.match(name) or WALL.match(name)):
            continue
        T = I[start:start + count].reshape(-1, 3).astype(np.int64)
        tm = np.asarray(tex_mean.get(name, (200, 200, 200)), np.float64) / 255.0
        # some zones' meshes carry NaN corners (ti_0_m1, CLAUDE.md): never into a far house
        T = T[np.isfinite(V[T]).all(axis=(1, 2))]
        if ROOF.match(name):
            p0, p1, p2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
            n = np.cross(p2 - p0, p1 - p0)              # the engine's winding is clockwise seen from outside
            ln = np.linalg.norm(n, axis=1)
            nz = n[:, 2] / np.maximum(ln, 1e-12)
            up = (nz > UP) & ((nz >= STEEP) | (0.5 * ln >= STEEP_AREA))
            T = T[up]
            roofT.append(V[T])
            roofC.append(C[T] * tm)
        else:
            u = np.unique(T.ravel())
            wallP.append(V[u])
            wallC.append(C[u] * tm)
    if not roofT:
        return None
    return (np.concatenate(roofT), np.concatenate(roofC),
            np.concatenate(wallP) if wallP else np.zeros((0, 3)), np.concatenate(wallC) if wallC else np.zeros((0, 3)))


# ------------------------------------------------------------------ one tile
def _components(nv, T):
    """Connected component of every vertex of the triangles T (k, 3) over nv vertices."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    a = np.concatenate([T[:, 0], T[:, 1], T[:, 2]])
    b = np.concatenate([T[:, 1], T[:, 2], T[:, 0]])
    M = coo_matrix((np.ones(len(a), np.int8), (a, b)), shape=(nv, nv))
    return connected_components(M, directed=False)[1]


def houses(parts):
    """The far geometry of a tile's building shapes (shape_parts of each): a dict of
    roof: P (k, 3, 3) world, normal (k, 3), colours (k, 3, 3), house (k,) index;
    walls: quads (q, 4, 3) world (top a, top b, foot b, foot a), outward normals (q, 3), colour (q, 3), house (q,);
    rec: one row per house (records()); or None."""
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    R = np.concatenate([p[0] for p in parts])
    RC = np.concatenate([p[1] for p in parts])
    WP = np.concatenate([p[2] for p in parts])
    WC = np.concatenate([p[3] for p in parts])
    if not len(R):
        return None
    # weld the roof corners (the corners two faces share are the same floats; across two shapes nearly so)
    flat = R.reshape(-1, 3)
    keyq = np.round(flat * (1000.0 / WELD_MM)).astype(np.int64)
    _, vid, inv = np.unique(keyq, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    PV = flat[vid]
    T = inv.reshape(-1, 3)
    ok = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])
    T, R, RC = T[ok], R[ok], RC[ok]
    if not len(T):
        return None
    comp_v = _components(len(PV), T)
    comp = comp_v[T[:, 0]]
    ncomp = int(comp.max()) + 1
    # size of each connected piece: area, and the spread of its corners across (xy): rims and caps are thin strips
    e1, e2 = R[:, 1] - R[:, 0], R[:, 2] - R[:, 0]
    nrm = np.cross(e2, e1)
    area3 = 0.5 * np.linalg.norm(nrm, axis=1)
    area = np.bincount(comp, area3, ncomp)
    plan = np.bincount(comp, 0.5 * np.abs(nrm[:, 2]), ncomp)
    xy = R[:, :, :2].reshape(-1, 2)
    cc = np.repeat(comp, 3)
    cnt = np.bincount(cc, minlength=ncomp).astype(np.float64)
    mx = np.bincount(cc, xy[:, 0], ncomp) / np.maximum(cnt, 1)
    my = np.bincount(cc, xy[:, 1], ncomp) / np.maximum(cnt, 1)
    dx, dy = xy[:, 0] - mx[cc], xy[:, 1] - my[cc]
    sxx = np.bincount(cc, dx * dx, ncomp) / np.maximum(cnt, 1)
    syy = np.bincount(cc, dy * dy, ncomp) / np.maximum(cnt, 1)
    sxy = np.bincount(cc, dx * dy, ncomp) / np.maximum(cnt, 1)
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    minor = np.maximum(0.0, tr / 2 - np.sqrt(np.maximum(0.0, tr * tr / 4 - det)))
    width = 2 * np.sqrt(3 * minor)
    keep_c = (area >= MIN_AREA) & (width >= MIN_WIDTH) & (plan >= MIN_HOUSE)
    kt = keep_c[comp]
    T, R, RC, comp, nrm = T[kt], R[kt], RC[kt], comp[kt], nrm[kt]
    if not len(T):
        return None
    # the houses are the kept pieces, numbered from 0
    used_c = np.unique(comp)
    hmap = np.full(ncomp, -1, np.int64)
    hmap[used_c] = np.arange(len(used_c))
    house = hmap[comp]
    nh = len(used_c)
    # foot and wall colour of each house: the wall corners under its roof corners
    from scipy.spatial import cKDTree
    used_v = np.unique(T.ravel())
    vh = np.full(len(PV), -1, np.int64)
    vh[T[:, 0]], vh[T[:, 1]], vh[T[:, 2]] = house, house, house
    roofmin = np.full(nh, np.inf)
    np.minimum.at(roofmin, house, R[:, :, 2].min(1))
    foot = np.full(nh, np.inf)
    wsum = np.zeros((nh, 3))
    wn = np.zeros(nh)
    if len(WP):
        tree = cKDTree(PV[used_v, :2])
        d, j = tree.query(WP[:, :2], distance_upper_bound=FOOT_REACH)
        hit = np.isfinite(d)
        hw = vh[used_v[j[hit]]]
        zw = WP[hit, 2]
        # a wall corner over the roof's lowest corner is no foot (a dormer's wall, an upper storey)
        low = zw <= roofmin[hw] + 0.5
        np.minimum.at(foot, hw[low], zw[low])
        np.add.at(wsum, hw, WC[hit])
        np.add.at(wn, hw, 1)
    nofoot = ~np.isfinite(foot)
    foot[nofoot] = roofmin[nofoot] - NO_WALL_DROP
    foot = np.maximum(foot, roofmin - 60.0) - SINK
    wcol = np.where(wn[:, None] > 0, wsum / np.maximum(wn, 1)[:, None], np.array(WALL_DEFAULT))
    # free edges of the roof planes: an edge of one face only
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    opp = np.concatenate([T[:, 2], T[:, 0], T[:, 1]])
    tri = np.tile(np.arange(len(T)), 3)
    Es = np.sort(E, 1)
    _, einv, ecnt = np.unique(Es, axis=0, return_inverse=True, return_counts=True)
    free = ecnt[einv.reshape(-1)] == 1
    E, opp, tri = E[free], opp[free], tri[free]
    A, B, O = PV[E[:, 0]], PV[E[:, 1]], PV[opp]
    d2 = B[:, :2] - A[:, :2]
    right = np.stack([d2[:, 1], -d2[:, 0]], 1)
    # each free edge turned so that its face is on its left: the outside (the wall's face) is on the right of a -> b
    flip = np.einsum("ij,ij->i", right, O[:, :2] - A[:, :2]) > 0
    A, B = np.where(flip[:, None], B, A), np.where(flip[:, None], A, B)
    d2 = B[:, :2] - A[:, :2]
    out = np.stack([d2[:, 1], -d2[:, 0]], 1)
    ln = np.linalg.norm(out, axis=1)
    good = ln > 1e-3
    out = out / np.maximum(ln, 1e-9)[:, None]
    A, B, out, tri = A[good], B[good], out[good], tri[good]
    hq = house[tri]
    A, B, out, hq = merge_runs(A, B, out, hq)
    fz = foot[hq]
    quads = np.stack([A, B, np.c_[B[:, :2], fz], np.c_[A[:, :2], fz]], 1)
    normals = np.c_[out, np.zeros(len(out))]
    # the records of the houses (farlod's coarse tiles)
    rec = records(R, RC, nrm, house, nh, foot, wcol)
    return {"roof": (R, nrm, RC, house), "walls": (quads, normals, wcol[hq], hq), "rec": rec}


def merge_runs(A, B, out, h):
    """Free edges that continue each other (same house, same outward side, end to start, on one line in plan and in
    height) as one wall: the roofs' outlines have many corners in a line (the survey's polygons, the 192 m cuts)."""
    if len(A) < 2:
        return A, B, out, h
    ka = [tuple(v) for v in np.round(A * 1000).astype(np.int64)]
    kb = [tuple(v) for v in np.round(B * 1000).astype(np.int64)]
    starts = collections.defaultdict(list)
    for i, k in enumerate(ka):
        starts[k].append(i)
    nxt = np.full(len(A), -1, np.int64)
    prv = np.full(len(A), -1, np.int64)
    for i, k in enumerate(kb):
        for j in starts.get(k, ()):
            if j != i and h[j] == h[i] and prv[j] < 0 and float(out[i] @ out[j]) > 1 - COLLINEAR:
                nxt[i], prv[j] = j, i
                break
    seen = np.zeros(len(A), bool)
    oA, oB, oO, oH = [], [], [], []

    def flush(chain):
        # split the chain where the top bends: greedy, from its start
        s = 0
        while s < len(chain):
            e = s
            while e + 1 < len(chain):
                a0, b1 = A[chain[s]], B[chain[e + 1]]
                ok = True
                L = b1 - a0
                L2 = float(L @ L)
                for q in range(s, e + 2):
                    p = B[chain[q]] if q <= e else None
                    if p is None:
                        continue
                    t = float((p - a0) @ L) / max(L2, 1e-12)
                    if np.linalg.norm(a0 + t * L - p) > MERGE_DZ:
                        ok = False
                        break
                if not ok:
                    break
                e += 1
            oA.append(A[chain[s]]); oB.append(B[chain[e]]); oO.append(out[chain[s]]); oH.append(h[chain[s]])
            s = e + 1

    for i in range(len(A)):
        if seen[i] or prv[i] >= 0:
            continue
        chain = [i]
        seen[i] = True
        j = nxt[i]
        while j >= 0 and not seen[j]:
            chain.append(j)
            seen[j] = True
            j = nxt[j]
        flush(chain)
    for i in range(len(A)):                       # closed loops with no start: cut at any edge
        if seen[i]:
            continue
        chain = [i]
        seen[i] = True
        j = nxt[i]
        while j >= 0 and not seen[j]:
            chain.append(j)
            seen[j] = True
            j = nxt[j]
        flush(chain)
    return np.array(oA), np.array(oB), np.array(oO), np.array(oH, np.int64)


REC_FIELDS = ("x", "y", "ux", "uy", "a", "b", "top", "foot", "rr", "rg", "rb", "wr", "wg", "wb", "area")


def records(R, RC, nrm, house, nh, foot, wcol):
    """(nh, len(REC_FIELDS)) float32: centre, the unit axis of the footprint box and its two half lengths, the roof's
    height (area weighted mean of its faces), the foot, roof colour, wall colour, roof area in plan."""
    xyA = np.abs(nrm[:, 2]) * 0.5                       # plan area of each face
    cen = R.mean(1)
    w = np.bincount(house, xyA, nh)
    cx = np.bincount(house, cen[:, 0] * xyA, nh) / np.maximum(w, 1e-9)
    cy = np.bincount(house, cen[:, 1] * xyA, nh) / np.maximum(w, 1e-9)
    top = np.bincount(house, cen[:, 2] * xyA, nh) / np.maximum(w, 1e-9)
    rc = np.stack([np.bincount(house, RC[:, :, k].mean(1) * xyA, nh) for k in range(3)], 1) / np.maximum(w, 1e-9)[:, None]
    # the box: axes of the corners' spread, half lengths their extent
    P = R[:, :, :2].reshape(-1, 2)
    hh = np.repeat(house, 3)
    dx, dy = P[:, 0] - cx[hh], P[:, 1] - cy[hh]
    n = np.bincount(hh, minlength=nh).astype(np.float64)
    sxx = np.bincount(hh, dx * dx, nh) / np.maximum(n, 1)
    syy = np.bincount(hh, dy * dy, nh) / np.maximum(n, 1)
    sxy = np.bincount(hh, dx * dy, nh) / np.maximum(n, 1)
    ang = 0.5 * np.arctan2(2 * sxy, sxx - syy)
    ux, uy = np.cos(ang), np.sin(ang)
    pu = dx * ux[hh] + dy * uy[hh]
    pv = -dx * uy[hh] + dy * ux[hh]
    amax = np.zeros(nh)
    bmax = np.zeros(nh)
    np.maximum.at(amax, hh, np.abs(pu))
    np.maximum.at(bmax, hh, np.abs(pv))
    # the box of the same plan area as the roof (an L-shaped house is not its bounding box)
    fill = np.clip(w / np.maximum(4 * amax * bmax, 1e-9), 0.3, 1.0)
    a, b = amax * np.sqrt(fill), bmax * np.sqrt(fill)
    return np.stack([cx, cy, ux, uy, a, b, top, foot, rc[:, 0], rc[:, 1], rc[:, 2],
                     wcol[:, 0], wcol[:, 1], wcol[:, 2], w], 1).astype(np.float32)


def tile_mesh(g, x0, y0):
    """positions (n, 3) from the tile's corner (x0, y0), triangles (counter-clockwise from outside), normals, colours
    (n, 4) uint8 of the houses g (houses())."""
    R, nrm, RC, house = g["roof"]
    quads, qn, qc, _ = g["walls"]
    # roof faces: one vertex per corner and plane of a house (flat planes, shared corners inside a plane)
    un = nrm / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)[:, None]
    plane = np.round(un * 40).astype(np.int64)
    flat = R.reshape(-1, 3)
    key = np.c_[np.repeat(house, 3), np.repeat(plane, 3, axis=0), np.round(flat * 500).astype(np.int64)]
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    Pr = flat[first]
    Nr = np.repeat(un, 3, axis=0)[first]
    Cr = RC.reshape(-1, 3)[first]
    Tr = inv.reshape(-1, 3)[:, ::-1]                    # counter-clockwise seen from above (up normals)
    # walls: 4 corners each
    nq = len(quads)
    Pw = quads.reshape(-1, 3)
    Nw = np.repeat(qn, 4, axis=0)
    Cw = np.repeat(qc, 4, axis=0)
    b = len(Pr) + 4 * np.arange(nq)
    # (top a, top b, foot b, foot a) with the outside to the right of a -> b: counter-clockwise from outside is
    # top a, foot a, foot b and top a, foot b, top b
    Tw = np.concatenate([np.stack([b, b + 3, b + 2], 1), np.stack([b, b + 2, b + 1], 1)])
    P = np.concatenate([Pr, Pw]) - [x0, y0, 0.0]
    N = np.concatenate([Nr, Nw])
    C = np.concatenate([Cr, Cw])
    T = np.concatenate([Tr, Tw])
    C8 = np.c_[np.clip(np.round(C * 255), 0, 255), np.full(len(C), 255)].astype(np.uint8)
    return P, T, N, C8


def check_winding(P, T, N):
    """Share of triangles whose counter-clockwise normal agrees with their vertices' normal (should be ~1)."""
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    n = np.cross(b - a, c - a)
    return float(np.mean(np.einsum("ij,ij->i", n, N[T[:, 0]]) > 0))


def tile_bytes(g, x0, y0):
    P, T, N, C8 = tile_mesh(g, x0, y0)
    if len(P) > VERTS_MAX:
        raise ValueError(f"{len(P)} vertices")
    return cdae.encode(P, T, normals=N, uvs=np.zeros((len(P), 2)), material=MAT, colors=C8, object_name="farbld")


def block_mesh(rec, x0, y0):
    """positions (n, 3) from the block's corner (x0, y0), triangles (counter-clockwise from outside), normals, colours
    (n, 4) uint8 of the coarse boxes of the records rec (records() of the block's tiles; the houses of L2_MIN_AREA or
    more): the top (4 corners, normal up) in the roof colour, the walls (8 corners shared: their normals point out of
    the corners, plain enough at 4 km and more) in the wall colour. None if no house is left."""
    f = {k: i for i, k in enumerate(REC_FIELDS)}
    r = rec[rec[:, f["area"]] >= L2_MIN_AREA].astype(np.float64)
    if len(r) * 12 > VERTS_MAX:                       # a dense block: its largest houses
        r = r[np.argsort(-r[:, f["area"]])[:VERTS_MAX // 12]]
    n = len(r)
    if not n:
        return None
    c = r[:, [f["x"], f["y"]]] - [x0, y0]
    u = r[:, [f["ux"], f["uy"]]]
    v = np.stack([-u[:, 1], u[:, 0]], 1)
    a = np.maximum(r[:, f["a"]], L2_MIN_HALF)[:, None]
    b = np.maximum(r[:, f["b"]], L2_MIN_HALF)[:, None]
    sa = np.array([1.0, 1.0, -1.0, -1.0])             # counter-clockwise seen from above
    sb = np.array([-1.0, 1.0, 1.0, -1.0])
    xy = c[:, None, :] + sa[None, :, None] * a[:, None, :] * u[:, None, :] + sb[None, :, None] * b[:, None, :] * v[:, None, :]
    top = r[:, f["top"]]
    foot = np.minimum(r[:, f["foot"]], top - 1.0)
    P = np.empty((n, 12, 3))
    P[:, 0:4, :2], P[:, 0:4, 2] = xy, top[:, None]
    P[:, 4:8, :2], P[:, 4:8, 2] = xy, top[:, None]
    P[:, 8:12, :2], P[:, 8:12, 2] = xy, foot[:, None]
    N = np.zeros((n, 12, 3))
    N[:, 0:4, 2] = 1.0
    d = sa[None, :, None] * u[:, None, :] + sb[None, :, None] * v[:, None, :]
    d /= np.linalg.norm(d, axis=2, keepdims=True)
    N[:, 4:8, :2] = d
    N[:, 8:12, :2] = d
    rc = r[:, [f["rr"], f["rg"], f["rb"]]]
    wc = r[:, [f["wr"], f["wg"], f["wb"]]]
    C = np.concatenate([np.repeat(rc[:, None], 4, 1), np.repeat(wc[:, None], 8, 1)], 1)
    base = 12 * np.arange(n)[:, None]
    tt = [[0, 1, 2], [0, 2, 3]]
    for k in range(4):                                 # wall k: top k, foot k, foot k+1 / top k, foot k+1, top k+1
        k1 = (k + 1) % 4
        tt += [[4 + k, 8 + k, 8 + k1], [4 + k, 8 + k1, 4 + k1]]
    T = (base[:, None, :] + np.array(tt)[None]).reshape(-1, 3)
    C8 = np.c_[np.clip(np.round(C.reshape(-1, 3) * 255), 0, 255), np.full(12 * n, 255)].astype(np.uint8)
    return P.reshape(-1, 3), T, N.reshape(-1, 3), C8


def material():
    from blocks import bng
    return bng.material(MAT, base_color=[1, 1, 1, 1], vert_color=True, roughness=0.9, extra={"castShadows": False})


# ------------------------------------------------------------------ the whole level
def tile_entries(tiles):
    """{key: [(shape path, position)]} of the buildings group's TSStatics of every o tile ({key: entries})."""
    out = {}
    for key, entries in tiles.items():
        lst = [(e["shapeName"], e["p"]) for e in entries
               if e.get("g") == GROUP and e.get("class") == "TSStatic" and "q" not in e and "s" not in e
               and re.search(r"/bld[^/]*\.c?dae$", e.get("shapeName", ""))]
        if lst:
            out[key] = lst
    return out


_W = {}


def _init(origin, tile_m, out_dir, tex_mean):
    _W.update(origin=origin, tile_m=tile_m, out_dir=out_dir, tex_mean=tex_mean)


def _one(item):
    """One tile: (key, [(shape bytes, position)]) -> (key, houses, triangles, bytes, records) or None. A tile that
    fails is left out with a log line (one bad tile must not stop the base)."""
    try:
        return _one_tile(item)
    except Exception as ex:                         # noqa: BLE001
        log("far buildings: tile %s left out (%s: %s)" % (item[0], type(ex).__name__, ex))
        return None


def _one_tile(item):
    key, shapes = item
    parts = []
    for data, pos in shapes:
        try:
            parts.append(shape_parts(data, pos, _W["tex_mean"]))
        except (cdae.CdaeError, ValueError, IndexError) as ex:
            log("far buildings: shape skipped (%s)" % ex)
    g = houses(parts)
    if g is None:
        return None
    cx, cy = (int(v) for v in key.split("_"))
    o, tm = _W["origin"], _W["tile_m"]
    x0, y0 = o[0] + cx * tm, o[1] + cy * tm
    try:
        data = tile_bytes(g, x0, y0)
    except ValueError as ex:
        log("far buildings: tile %s left out (%s)" % (key, ex))
        return None
    p = os.path.join(_W["out_dir"], f"b_{key}.cdae")
    if os.path.lexists(p):
        os.remove(p)
    with open(p, "wb") as f:
        f.write(data)
    rec = g["rec"]
    ntri = len(g["roof"][0]) + 2 * len(g["walls"][0])
    return key, len(rec), ntri, len(data), rec


def build(tiles, origin, tile_m, out_dir, tex_mean=TEX_MEAN, workers=1, records_path=None):
    """tiles: iterable of (key "cx_cy", [(shape bytes, position)]). Writes out_dir/b_<key>.cdae (fine),
    out_dir/l2_<bx>_<by>.cdae (coarse) and out_dir/farbld.materials.json (records_path: the houses' records too, for
    tests); returns (sorted fine keys, sorted coarse keys)."""
    os.makedirs(out_dir, exist_ok=True)
    keys, recs = [], {}
    nh = ntri = nbytes = 0
    t0 = time.time()
    if workers > 1:
        import multiprocessing as mp
        pool = mp.Pool(workers, _init, (origin, tile_m, out_dir, tex_mean))
        results = pool.imap_unordered(_one, tiles, chunksize=4)
    else:
        pool = None
        _init(origin, tile_m, out_dir, tex_mean)
        results = map(_one, tiles)
    for r in results:
        if r is None:
            continue
        key, n, nt, nb, rec = r
        keys.append(key)
        recs[key] = rec
        nh += n
        ntri += nt
        nbytes += nb
        if len(keys) % 1000 == 0:
            log("far buildings: %d tiles, %d houses, %.1f M triangles, %.0f MB (%.0f s)" % (
                len(keys), nh, ntri / 1e6, nbytes / 1e6, time.time() - t0))
    if pool:
        pool.close()
        pool.join()
    if records_path:
        save_records(records_path, recs)
    log("far buildings: %d tiles, %d houses, %.1f M triangles, %.0f MB in %.0f s" % (
        len(keys), nh, ntri / 1e6, nbytes / 1e6, time.time() - t0))
    keys2 = build_blocks(recs, origin, tile_m, out_dir)
    from blocks import bng
    p = os.path.join(out_dir, "farbld.materials.json")
    if os.path.lexists(p):
        os.remove(p)
    bng.write_materials(p, [material()])
    return sorted(keys), keys2


def build_blocks(recs, origin, tile_m, out_dir):
    """The coarse blocks (l2_<bx>_<by>.cdae) of the records {tile key: records}; returns their sorted keys."""
    by_block = collections.defaultdict(list)
    for key, rec in recs.items():
        cx, cy = (int(v) for v in key.split("_"))
        by_block[(cx // L2_TILES, cy // L2_TILES)].append(rec)
    keys2, nh, ntri, nbytes, cut = [], 0, 0, 0, 0
    bm = tile_m * L2_TILES
    for (bx, by), lst in sorted(by_block.items()):
        rec = np.concatenate(lst)
        m = block_mesh(rec, origin[0] + bx * bm, origin[1] + by * bm)
        if m is None:
            continue
        P, T, N, C8 = m
        kept = len(P) // 12
        cut += int((rec[:, REC_FIELDS.index("area")] >= L2_MIN_AREA).sum()) - kept
        data = cdae.encode(P, T, normals=N, uvs=np.zeros((len(P), 2)), material=MAT, colors=C8,
                           object_name="farbld2")
        k = f"{bx}_{by}"
        p = os.path.join(out_dir, f"l2_{k}.cdae")
        if os.path.lexists(p):
            os.remove(p)
        with open(p, "wb") as f:
            f.write(data)
        keys2.append(k)
        nh += kept
        ntri += len(T)
        nbytes += len(data)
    log("far buildings, coarse: %d blocks, %d houses (%d of dense blocks left out), %.1f M triangles, %.0f MB" % (
        len(keys2), nh, cut, ntri / 1e6, nbytes / 1e6))
    return keys2


def save_records(path, recs):
    keys = sorted(recs)
    arr = np.concatenate([recs[k] for k in keys]) if keys else np.zeros((0, len(REC_FIELDS)), np.float32)
    idx = np.repeat(np.arange(len(keys)), [len(recs[k]) for k in keys]) if keys else np.zeros(0, np.int64)
    np.savez_compressed(path, keys=np.array(keys), idx=idx, rec=arr)


def load_records(path):
    d = np.load(path)
    keys, idx, arr = list(d["keys"]), d["idx"], d["rec"]
    return {str(k): arr[idx == i] for i, k in enumerate(keys)}


def read_folder(level_dir, tiles):
    """(key, [(bytes, position)]) of every tile from a level folder (levels/ticino of local slices)."""
    for key, lst in sorted(tile_entries(tiles).items()):
        shapes = []
        for path, pos in lst:
            rel = path.split("/levels/ticino/", 1)[-1]
            p = os.path.join(level_dir, *rel.split("/"))
            if not os.path.exists(p) and p.endswith(".dae") and os.path.exists(p[:-4] + ".cdae"):
                p = p[:-4] + ".cdae"
            if os.path.exists(p) and p.endswith(".cdae"):
                shapes.append((open(p, "rb").read(), pos))
        if shapes:
            yield key, shapes


def read_slices(sl, zones, workers=12):
    """(key, [(bytes, position)]) of every tile with buildings of the zones' slices (region_base's Slices: local
    folders or the release by HTTP range), zone by zone."""
    if sl.folder:
        for z in zones:
            d = os.path.join(sl.folder, z, "levels", "ticino")
            tiles = {}
            for p in glob.glob(os.path.join(d, "tiles", "o_*.json")):
                tiles[re.search(r"o_(-?\d+_-?\d+)\.json$", p).group(1)] = json.load(open(p))
            yield from read_folder(d, tiles)
        return
    import zipremote
    from concurrent.futures import ThreadPoolExecutor
    t0, n = time.time(), 0
    for zi, z in enumerate(zones):
        zips = [zipremote.open_zip(aid) for aid in sl.ids.get(z, [])]
        where = {}
        for zf in zips:
            for nm in zf.namelist():
                where[nm] = zf
        tiles = {}
        for nm, zf in where.items():
            m = re.search(r"/tiles/o_(-?\d+_-?\d+)\.json$", nm)
            if m:
                tiles[m.group(1)] = json.loads(zf.read(nm))
        ent = tile_entries(tiles)
        want = []
        for key, lst in ent.items():
            for path, pos in lst:
                nm = path.lstrip("/")
                if nm not in where and nm.endswith(".dae"):
                    nm = nm[:-4] + ".cdae"
                if nm in where and nm.endswith(".cdae"):
                    want.append((key, nm, pos))
        # one zip object per thread (a ZipFile over one range reader is not thread safe)
        by_zip = collections.defaultdict(list)
        for w in want:
            by_zip[id(where[w[1]])].append(w)
        aid_of = {id(zf): aid for zf, aid in zip(zips, sl.ids.get(z, []))}

        def batch(args):
            aid, items = args
            zf = zipremote.open_zip(aid)
            return [(k, zf.read(nm), pos) for k, nm, pos in items]
        jobs = []
        for zid, items in by_zip.items():
            for i in range(workers):
                part = items[i::workers]
                if part:
                    jobs.append((aid_of[zid], part))
        got = collections.defaultdict(list)
        with ThreadPoolExecutor(workers) as ex:
            for res in ex.map(batch, jobs):
                for k, data, pos in res:
                    got[k].append((data, pos))
        n += len(want)
        log("far buildings: zone %s (%d of %d): %d shapes of %d tiles, %d in all (%.0f s)" % (
            z, zi + 1, len(zones), len(want), len(got), n, time.time() - t0))
        for k in sorted(got):
            yield k, got[k]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", required=True, help="a levels/ticino folder (tiles/, z/)")
    ap.add_argument("--stream", help="stream.json (origin, cell, square); default: the Ticino plan's")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", help="regex of tile keys")
    a = ap.parse_args()
    if a.stream:
        st = json.load(open(a.stream))
        origin, tile_m = st["origin"], st["cell"] * st["square"]
    else:
        plan = json.load(open(os.path.join(HERE, "zones", "ticino_plan.json")))
        origin, tile_m = plan.get("origin", [0.0, 0.0]), 384.0
    tiles = {}
    for p in glob.glob(os.path.join(a.level, "tiles", "o_*.json")):
        k = re.search(r"o_(-?\d+_-?\d+)\.json$", p).group(1)
        if not a.only or re.fullmatch(a.only, k):
            tiles[k] = json.load(open(p))
    keys, keys2 = build(read_folder(a.level, tiles), origin, tile_m, a.out, texture_means(a.level), a.workers,
                        records_path=os.path.join(a.out, "records.npz"))
    print(len(keys), "fine tiles,", len(keys2), "coarse blocks")


if __name__ == "__main__":
    main()
