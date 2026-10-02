"""Fewer triangles in the steep strips of the road meshes (v2.5), within a few millimetres.

More than half of the road triangles are steep: skirts down to the ground along every edge of a
paved area, kerb faces, stone faces. They follow the edges of the paved polygons, sampled every
metre or so also along straight runs. Here the steep triangles of every material are welded and
simplified along straight runs: a strip is a chain of columns (a top and a bottom vertex at the
same x, y) joined by quads, and consecutive quads become one where the top line and the bottom
line both stay within TOL of straight. The result is accepted only if every original vertex and
triangle centre lies within TOL of the new strip and every new vertex and triangle centre
within TOL of the old one; otherwise the piece is kept as it was. Texture
coordinates come from the linear map (x, y, z) -> uv of the piece (the pipeline wraps these faces
with u = (x + y) / tile, v = z / tile); a piece whose map is not linear is kept as it was.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

STEEP_NZ = 0.5        # |normal z| under which a triangle is a strip face
TOL = 0.004           # m
UV_TOL = 2e-3


def _face_normals(V, T):
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(ln == 0, 1, ln), ln.ravel() / 2


def _closest_on_tri(p, a, b, c):
    """Closest points on triangles (a, b, c) to points p, all (k, 3) (Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-30, 1e-30, den)
    v, w = vb / den, vc / den
    r = a + ab * v[:, None] + ac * w[:, None]                        # inside the face
    sel = (vb <= 0) & (d2 - d6 >= 0) & (d5 - d6 >= 0)                 # edge ca  (cases in reverse priority)
    t = d2 / np.where(np.abs(d2 - d6) < 1e-30, 1e-30, d2 - d6)
    r[sel] = (a + ac * t[:, None])[sel]
    sel = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)                 # edge bc
    t = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-30, 1e-30, (d4 - d3) + (d5 - d6))
    r[sel] = (b + (c - b) * t[:, None])[sel]
    sel = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                           # edge ab
    t = d1 / np.where(np.abs(d1 - d3) < 1e-30, 1e-30, d1 - d3)
    r[sel] = (a + ab * t[:, None])[sel]
    r[(d6 >= 0) & (d5 <= d6)] = c[(d6 >= 0) & (d5 <= d6)]             # vertex regions
    r[(d3 >= 0) & (d4 <= d3)] = b[(d3 >= 0) & (d4 <= d3)]
    r[(d1 <= 0) & (d2 <= 0)] = a[(d1 <= 0) & (d2 <= 0)]
    return r


def _point_tri_dist(P, V, T):
    """Distance from points P (k,3) to the triangle mesh (V, T)."""
    from scipy.spatial import cKDTree
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    ctr = (A + B + C) / 3
    rad = np.sqrt(np.max([((X - ctr) ** 2).sum(1) for X in (A, B, C)], 0))
    d0, _ = cKDTree(ctr).query(P)                                     # upper bound: nearest centre + its radius
    cand = cKDTree(ctr).query_ball_point(P, d0 + rad.max() + 1e-9)
    pi = np.repeat(np.arange(len(P)), [len(c) for c in cand])
    ti = np.concatenate([np.asarray(c, np.int64) for c in cand]) if len(pi) else np.zeros(0, np.int64)
    q = _closest_on_tri(P[pi], A[ti], B[ti], C[ti])
    d = np.linalg.norm(P[pi] - q, axis=1)
    out = np.full(len(P), np.inf)
    np.minimum.at(out, pi, d)
    return out


def simplify_strips(V, UV, T, tol=TOL):
    """V (n,3), UV (n,2) per corner/vertex, T (m,3). Returns (V, UV, T) of the steep triangles
    simplified (plus the others unchanged) and the number of triangles saved."""
    fn, area = _face_normals(V, T)
    steep = (np.abs(fn[:, 2]) < STEEP_NZ) & (area > 1e-10)
    if steep.sum() < 16:
        return [(V, UV, T)], 0
    out = [(V, UV, T[~steep])] if (~steep).any() else []
    Ts = T[steep]
    key = np.round(V * 1000).astype(np.int64)
    u, inv = np.unique(key[Ts.ravel()], axis=0, return_inverse=True)
    inv = inv.ravel()
    P = np.zeros((len(u), 3)); np.add.at(P, inv, V[Ts.ravel()]); P /= np.bincount(inv)[:, None]
    Q = np.zeros((len(u), 2)); Q[inv] = UV[Ts.ravel()]
    Tw = inv.reshape(-1, 3)
    good = (Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])
    Tw = Tw[good]
    e = np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]])
    nc, comp = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(P), len(P))), directed=False)
    tcomp = comp[Tw[:, 0]]
    saved = 0
    for c in np.unique(tcomp):
        Tc = Tw[tcomp == c]
        used = np.unique(Tc)
        remap = np.full(len(P), -1); remap[used] = np.arange(len(used))
        Vc, Qc, Tc = P[used], Q[used], remap[Tc]
        res = _simplify_piece(Vc, Qc, Tc, tol) if len(Tc) >= 6 else None
        if res is None:
            out.append((Vc, Qc, Tc))
            continue
        out.append(res)
        saved += len(Tc) - len(res[2])
    return out, saved


def _simplify_piece(V, Q, T, tol):
    """One connected strip piece, welded: (V, Q, T) -> simplified (V, Q, T) or None."""
    X = np.column_stack([V, np.ones(len(V))])
    coef, *_ = np.linalg.lstsq(X, Q, rcond=None)
    if np.abs(X @ coef - Q).max() > UV_TOL:
        return None
    # columns: exactly two vertices at the same x, y (mm)
    xy = np.round(V[:, :2] * 1000).astype(np.int64)
    ucol, col = np.unique(xy, axis=0, return_inverse=True)
    col = col.ravel()
    ncol = len(ucol)
    if np.bincount(col, minlength=ncol).max() != 2 or np.bincount(col, minlength=ncol).min() != 2:
        return None
    order = np.argsort(col * 2 + 0, kind="stable")
    pair = order.reshape(ncol, 2)                           # vertex ids of every column
    zc = V[pair, 2]
    top = np.where(zc[:, 0] >= zc[:, 1], pair[:, 0], pair[:, 1])
    bot = np.where(zc[:, 0] >= zc[:, 1], pair[:, 1], pair[:, 0])
    # every triangle spans exactly two columns; quads = column pairs with two triangles
    tc = col[T]
    pairs = {}
    for t, (a, b, c) in enumerate(tc):
        cs = sorted({a, b, c})
        if len(cs) != 2:
            return None
        pairs.setdefault((cs[0], cs[1]), []).append(t)
    if any(len(v) != 2 for v in pairs.values()):
        return None
    nbr = [[] for _ in range(ncol)]
    for a, b in pairs:
        nbr[a].append(b); nbr[b].append(a)
    if max(len(n) for n in nbr) > 2:
        return None
    # chains of columns (paths; a closed ring is opened at its first column)
    seen = np.zeros(ncol, bool)
    chains = []
    ends = [c for c in range(ncol) if len(nbr[c]) == 1] + list(range(ncol))
    for s0 in ends:
        if seen[s0]:
            continue
        chain = [s0]; seen[s0] = True
        cur = s0
        while True:
            nxt = [n for n in nbr[cur] if not seen[n]]
            if not nxt:
                break
            cur = nxt[0]; seen[cur] = True; chain.append(cur)
        if len(chain) > 1 and len(nbr[s0]) == 2 and s0 in nbr[chain[-1]]:
            chain.append(s0)                                # ring
        chains.append(chain)
    fn, _ = _face_normals(V, T)
    newV, newT = [], []

    def straight(P, i, j):
        a, b = P[i], P[j]
        d = b - a
        L = np.dot(d, d)
        if L == 0:
            return False
        t = np.clip(((P[i:j + 1] - a) @ d) / L, 0, 1)
        return np.linalg.norm(P[i:j + 1] - (a + t[:, None] * d), axis=1).max() <= tol * 0.5
    for chain in chains:
        if len(chain) < 2:
            continue
        TP, BP = V[top[chain]], V[bot[chain]]
        i = 0
        while i < len(chain) - 1:
            j = i + 1
            while j + 1 < len(chain) and straight(TP, i, j + 1) and straight(BP, i, j + 1):
                j += 1
            # the quad (i, j) facing like the old faces of the span
            span = [t for k in range(i, j) for t in pairs[tuple(sorted((chain[k], chain[k + 1])))]]
            nrm = fn[span].sum(0)
            base = sum(len(v) for v in newV)
            q = np.array([TP[i], TP[j], BP[j], BP[i]])
            newV.append(q)
            t1, t2 = [base, base + 1, base + 2], [base, base + 2, base + 3]
            f = np.cross(q[1] - q[0], q[2] - q[0])
            if np.dot(f, nrm) < 0:
                t1, t2 = t1[::-1], t2[::-1]
            newT += [t1, t2]
            i = j
    if not newV:
        return None
    V2 = np.concatenate(newV); T2 = np.asarray(newT, np.int64)
    if len(T2) >= len(T) * 0.9:
        return None
    # the same shape within tol, both ways
    C = V[T].mean(1)
    if _point_tri_dist(np.concatenate([V, C]), V2, T2).max() > tol:
        return None
    C2 = V2[T2].mean(1)
    if _point_tri_dist(np.concatenate([V2, C2]), V, T).max() > tol:
        return None
    Q2 = np.column_stack([V2, np.ones(len(V2))]) @ coef
    return V2, Q2, T2
