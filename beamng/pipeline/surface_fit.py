"""Idealised surface of the paved areas: a smooth fit of the terrain heights over the paved polygons.

The paved surfaces of v1.0 followed the DTM (swissALTI3D): the lidar noise made every road slightly
bumpy, bridges sagged into the valley below them (the DTM is the ground without bridges: 7 m at the
bridge 3.05 km from Magliaso), and where a road, yard or terrace lies a few metres above or below
the next one, the 0.5 m DTM smeared the wall between them into a ramp across the carriageway.

Here the height raster D (DTM) is fitted over the paved polygons (owner raster: polygon index per
cell, -1 = not paved):
1. Cliffs: paved cells steeper than CLIFF (45 %; no road, ramp or driveway is) are a wall smeared by
   the DTM or the ground under a bridge. They split the paved area into regions.
2. Every region gets its own smooth surface (robust thin plate, below). Where two polygons touch,
   their surfaces are compared cell by cell along the common edge: where they meet (gap < STEP)
   they are one surface (roads, junctions, sidewalks, driveways), elsewhere a step is kept.
3. Every band of cliff cells is crossed by the surfaces around it (planar extrapolation): surfaces
   that meet across the band (gap < STEP_BAND) are one surface and the band is part of it, without
   data (a bridge: the road on both sides of the valley). Otherwise the band is shared between the
   surfaces around it, each continued up to the middle of the band, where a step (a wall) remains.
4. Every connected surface gets the final fit; the smoothing does not act across the steps.
Thin plate: minimise  sum w (Z - D)^2 + a sum (Zxx^2 + 2 Zxy^2 + Zyy^2),  a = (LC / 2 pi)^4,  so
undulations shorter than about LC are removed while grades, cross slopes and the gentle curves of
the road pass unchanged (a thin plate has no cost for planes). A stiffer LC_MAIN can be given for
the carriageway of the main road. The fit is iteratively reweighted least squares with Tukey
weights whose threshold shrinks from 2 m to 0.3 m: what is far from the smooth surface (the edge
of a bridge gap, a parked car, the foot of a smeared wall) loses its weight.
The result is sampled per polygon: bilinear inside its surface, planar extrapolation (gradient of
the nearest cell) beyond, so a mesh vertex on the edge of a polygon gets the height of that
polygon's surface even where another surface meets it at a step.
"""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

LC_REGION = 12.0                # m, smoothing wavelength of the region fits (step tests)
LC = 12.0                       # m, final surfaces
LC_MAIN = 25.0                  # m, final surface on the carriageway of the main road
LC_STEEP = 4.0                  # m, steep surfaces kept as they are (stairs, steep paths)
CLIFF = 0.45                    # slope of a paved cell above which it is a wall or a bridge gap
STEP = 0.30                     # m, two polygons' surfaces further apart along their edge: a step
CREASE = 0.10                   # slope difference above which two polygons meet at a crease
W_CREASE = 50.0                 # weight of the height continuity across a crease
STEP_BAND = 0.40                # m, surfaces closer than this across a cliff band: one surface
BAND_REACH = 25.0               # m, extrapolation of a surface into a cliff band
POCKET = 150.0                  # m2, smaller regions enclosed by cliffs: the ground under a bridge
MIN_SURFACE = 4.0               # m2, smaller surfaces (cells cut off by cliffs) join the one around
TUKEY = (2.0, 1.0, 0.6, 0.4, 0.3, 0.3, 0.3, 0.3)     # IRLS thresholds (m), one per iteration
EDGE_W0, EDGE_RAMP = 0.2, 1.25  # data weight at an edge, distance (m) where it reaches 1
EXTRAP_MAX = 3.0                # m, planar extrapolation beyond a surface edge is clamped here
EXTRAP_SLOPE = 1.0              # steepest slope used for the extrapolation


# ------------------------------------------------------------------ links between cells
def link_same(owner, ok):
    """Links (LR: cell - right neighbour, LD: cell - lower neighbour) between `ok` cells of one polygon."""
    LR = np.zeros(owner.shape, bool)
    LD = np.zeros(owner.shape, bool)
    LR[:, :-1] = ok[:, :-1] & ok[:, 1:] & (owner[:, :-1] == owner[:, 1:])
    LD[:-1, :] = ok[:-1, :] & ok[1:, :] & (owner[:-1, :] == owner[1:, :])
    return LR, LD


def gradients(Z, LR, LD, res):
    """d/dcol, d/drow of Z using only linked neighbours (central, one-sided at edges and steps)."""
    out = []
    Zf = np.nan_to_num(Z)
    for L, ax in ((LR, 1), (LD, 0)):
        Lm = np.roll(L, 1, ax)                      # link to the -1 neighbour
        if ax == 1:
            Lm[:, 0] = False
        else:
            Lm[0, :] = False
        Zp, Zm = np.roll(Zf, -1, ax), np.roll(Zf, 1, ax)
        g = np.zeros(Z.shape)
        b = L & Lm
        g[b] = ((Zp - Zm) / (2 * res))[b]
        o = L & ~Lm
        g[o] = ((Zp - Zf) / res)[o]
        o = Lm & ~L
        g[o] = ((Zf - Zm) / res)[o]
        out.append(g)
    return out


def cell_components(mask, LR, LD):
    """Connected components of the cells of `mask` over the links; -1 outside."""
    idx = -np.ones(mask.shape, np.int64)
    rr, cc = np.nonzero(mask)
    idx[rr, cc] = np.arange(len(rr))
    e = [np.zeros((0, 2), np.int64)]
    for L, (dr, dc) in ((LR, (0, 1)), (LD, (1, 0))):
        a_r, a_c = np.nonzero(L & mask)
        ok = (a_r + dr < mask.shape[0]) & (a_c + dc < mask.shape[1])
        a_r, a_c = a_r[ok], a_c[ok]
        b = idx[a_r + dr, a_c + dc]
        ok = b >= 0
        e.append(np.column_stack([idx[a_r[ok], a_c[ok]], b[ok]]))
    e = np.concatenate(e)
    G = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(rr), len(rr)))
    _, lab = connected_components(G, directed=False)
    out = -np.ones(mask.shape, np.int64)
    out[rr, cc] = lab
    return out


# ------------------------------------------------------------------ thin plate
def thin_plate(mask, LR, LD, res, lc, CR=None, CD=None):
    """Normal matrix a (Dxx'Dxx + Dyy'Dyy + 2 Dxy'Dxy) over the cells of `mask`, stencils only
    over linked cells (LR/LD) that are not creases (CR/CD); across a crease only the heights of
    the two surfaces, each extrapolated to the common edge, are tied (W_CREASE), so their slopes
    may differ. lc: scalar or per-cell raster of smoothing wavelengths."""
    idx = -np.ones(mask.shape, np.int64)
    rr, cc = np.nonzero(mask)
    idx[rr, cc] = np.arange(len(rr))
    n = len(rr)
    pad = np.pad(idx, 2, constant_values=-1)
    right, down = np.zeros(mask.shape, bool), np.zeros(mask.shape, bool)
    right[:, :-1] = mask[:, :-1] & mask[:, 1:]
    down[:-1, :] = mask[:-1, :] & mask[1:, :]
    CR = np.zeros(mask.shape, bool) if CR is None else CR
    CD = np.zeros(mask.shape, bool) if CD is None else CD
    LRp = np.pad(LR & right & ~CR, 2)
    LDp = np.pad(LD & down & ~CD, 2)
    alpha = (np.broadcast_to(np.asarray(lc, np.float64), mask.shape)[rr, cc] / (2 * np.pi)) ** 4

    def nb(dr, dc):
        return pad[rr + 2 + dr, cc + 2 + dc]

    def lr(dr, dc):
        return LRp[rr + 2 + dr, cc + 2 + dc]

    def ld(dr, dc):
        return LDp[rr + 2 + dr, cc + 2 + dc]
    h2 = res * res
    blocks = []
    for (a, b, c), ok in (((nb(0, -1), nb(0, 0), nb(0, 1)), lr(0, -1) & lr(0, 0)),
                          ((nb(-1, 0), nb(0, 0), nb(1, 0)), ld(-1, 0) & ld(0, 0))):
        k = np.nonzero(ok)[0]
        rows = np.repeat(np.arange(len(k)), 3)
        cols = np.column_stack([a[k], b[k], c[k]]).ravel()
        vals = (np.array([1.0, -2.0, 1.0])[None, :] * np.sqrt(alpha[k])[:, None]).ravel() / h2
        blocks.append(sp.csr_matrix((vals, (rows, cols)), shape=(len(k), n)))
    ok = np.ones(n, bool)
    for dr in (-1, 0, 1):
        ok &= lr(dr, -1) & lr(dr, 0)
    for dc in (-1, 0, 1):
        ok &= ld(-1, dc) & ld(0, dc)
    k = np.nonzero(ok)[0]
    p, q, r_, s_ = nb(1, 1), nb(1, -1), nb(-1, 1), nb(-1, -1)
    rows = np.repeat(np.arange(len(k)), 4)
    cols = np.column_stack([p[k], q[k], r_[k], s_[k]]).ravel()
    vals = (np.array([1.0, -1.0, -1.0, 1.0])[None, :] * np.sqrt(2 * alpha[k])[:, None]).ravel() / (4 * h2)
    blocks.append(sp.csr_matrix((vals, (rows, cols)), shape=(len(k), n)))
    # creases: (1.5 za - 0.5 za') - (1.5 zb - 0.5 zb') = 0 at the edge between a and b
    CRp, CDp = np.pad(CR & right, 2), np.pad(CD & down, 2)
    for Cp, Lp, (dr, dc) in ((CRp, LRp, (0, 1)), (CDp, LDp, (1, 0))):
        k = np.nonzero(Cp[rr + 2, cc + 2])[0]
        if not len(k):
            continue
        a, b = np.arange(n)[k], nb(dr, dc)[k]
        a2, b2 = nb(-dr, -dc)[k], nb(2 * dr, 2 * dc)[k]
        # the inner neighbours count only if linked smoothly to a / b
        a_in = Lp[rr[k] + 2 - dr, cc[k] + 2 - dc] & (a2 >= 0)
        b_in = Lp[rr[k] + 2 + dr, cc[k] + 2 + dc] & (b2 >= 0)
        ca = np.where(a_in, 1.5, 1.0); cb = np.where(b_in, 1.5, 1.0)
        rows, cols, vals = [], [], []
        m = np.arange(len(k))
        rows += [m, m]; cols += [a, b]; vals += [ca, -cb]
        rows += [m[a_in], m[b_in]]; cols += [a2[a_in], b2[b_in]]; vals += [np.full(a_in.sum(), -0.5), np.full(b_in.sum(), 0.5)]
        blocks.append(np.sqrt(W_CREASE) * sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                                                         shape=(len(k), n)))
    Q = sum(B.T @ B for B in blocks)
    return Q.tocsc(), rr, cc


def robust_fit(d, w0, Q, schedule=TUKEY, protect=None):
    """IRLS thin-plate fit of the cell values d (weights w0); returns heights and final weights.
    `protect`: cells whose data always keeps its weight."""
    d = np.nan_to_num(d)
    wr = np.ones(len(d))
    z = d.copy()
    for c in (None,) + tuple(schedule):
        if c is not None:
            r = d - z
            wr = np.where(np.abs(r) < c, (1 - (r / c) ** 2) ** 2, 0.0)
            if protect is not None:
                wr[protect] = 1.0
        # a tiny pull to the data keeps a surface defined where the IRLS rejected all of it
        ww = np.maximum(w0 * wr, 1e-6)
        z = spsolve((Q + sp.diags(ww)).tocsc(), ww * d)
    return z, wr


def edge_weight(mask, LR, LD, res, nodata=None):
    """Data weight: EDGE_W0 on the edge of `mask`, on the rim of its steps (cells with an unlinked
    neighbour inside the mask) and next to `nodata` cells, rising linearly to 1 at EDGE_RAMP m."""
    rim = np.zeros(mask.shape, bool)
    cut = np.zeros(mask.shape, bool)
    cut[:, :-1] = mask[:, :-1] & mask[:, 1:] & ~LR[:, :-1]
    rim[:, :-1] |= cut[:, :-1]
    rim[:, 1:] |= cut[:, :-1]
    cut = np.zeros(mask.shape, bool)
    cut[:-1, :] = mask[:-1, :] & mask[1:, :] & ~LD[:-1, :]
    rim[:-1, :] |= cut[:-1, :]
    rim[1:, :] |= cut[:-1, :]
    inner = mask & ~rim
    if nodata is not None:
        inner &= ~nodata
    dist = ndi.distance_transform_edt(np.pad(inner, 1))[1:-1, 1:-1] * res - 0.5 * res
    w = np.clip(EDGE_W0 + (1 - EDGE_W0) * dist / EDGE_RAMP, EDGE_W0, 1.0)
    if nodata is not None:
        w[nodata] = 0.0
    return w


def restore_dead_ends(m, LR, LD, rr, cc, w0, wr):
    """Rejected data regions that are not held by accepted data around them (a steep path or a
    ramp at the end of a surface: the fit only extrapolates there) get their data back."""
    rej = np.zeros(m.shape, bool)
    rej[rr, cc] = (wr < 0.05) & (w0 > 0)
    if not rej.any():
        return wr, False
    acc = np.zeros(m.shape, bool)
    acc[rr, cc] = (wr >= 0.05) & (w0 > 0)
    lab, n = ndi.label(rej)
    held = np.zeros(n + 1)
    free = np.zeros(n + 1)
    for L, ax in ((LR, 1), (LD, 0)):
        sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
        sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
        for x, y in ((sa, sb), (sb, sa)):
            e = rej[x] & ~rej[y]
            lk = L[sa] & m[y]
            np.add.at(held, lab[x][e & lk & acc[y]], 1)
            np.add.at(free, lab[x][e & ~(lk & acc[y])], 1)
    open_ = held < 0.3 * (held + free)
    open_[0] = False
    back = open_[lab[rr, cc]] & (lab[rr, cc] > 0)
    if not back.any():
        return wr, False
    wr = wr.copy()
    wr[back] = 1.0
    return wr, True


def fit_components(D, LR, LD, labels, res, lc, nodata=None, CR=None, CD=None, protect=None, verbose=False):
    """Robust thin-plate fit of every region (labels == k); returns Z and the IRLS weights."""
    Z = np.full(D.shape, np.nan)
    WR = np.zeros(D.shape)
    lc_arr = np.broadcast_to(np.asarray(lc, np.float64), D.shape)
    for k, sl in enumerate(ndi.find_objects(labels + 1)):
        if sl is None:
            continue
        m = labels[sl] == k
        Q, rr, cc = thin_plate(m, LR[sl], LD[sl], res, lc_arr[sl],
                               None if CR is None else CR[sl], None if CD is None else CD[sl])
        nd = None if nodata is None else nodata[sl] & m
        w0 = edge_weight(m, LR[sl], LD[sl], res, nd)[rr, cc]
        if not (w0 > 0).any():
            w0 = np.full(len(rr), 1.0)
        d = D[sl][rr, cc]
        z, wr = robust_fit(d, w0, Q, protect=None if protect is None else protect[sl][rr, cc])
        wr, again = restore_dead_ends(m, LR[sl], LD[sl], rr, cc, w0, wr)
        if again:
            ww = np.maximum(w0 * wr, 1e-6)
            z = spsolve((Q + sp.diags(ww)).tocsc(), ww * np.nan_to_num(d))
        Z[sl[0].start + rr, sl[1].start + cc] = z
        WR[sl[0].start + rr, sl[1].start + cc] = wr * (w0 > 0)
        if verbose and m.sum() > 20000:
            print("    surface of %d cells: data rejected %.1f %%" % (m.sum(), 100 * np.mean(wr[w0 > 0] < 0.05)))
    return Z, WR


# ------------------------------------------------------------------ building the surfaces
def smooth_paved(D, paved, sigma):
    w = ndi.gaussian_filter(paved.astype(np.float64), sigma)
    return np.where(paved, ndi.gaussian_filter(np.where(paved, D, 0.0), sigma) / np.maximum(w, 1e-9), np.nan)


def step_links(owner, Zr, LR, LD, ok, res, step=STEP):
    """Link `ok` cells of different polygons where their surfaces Zr (each extrapolated half a
    cell towards the other) meet within `step`: smoothly where their slopes agree, at a crease
    (CR/CD) where they differ by more than CREASE (a steep path or driveway off a road)."""
    LR, LD = LR.copy(), LD.copy()
    CR, CD = np.zeros(LR.shape, bool), np.zeros(LD.shape, bool)
    gc, gr = gradients(Zr, LR, LD, res)
    Zf = np.nan_to_num(Zr)
    n_join = n_step = n_crease = 0
    for L, C, ax, g in ((LR, CR, 1, gc), (LD, CD, 0, gr)):
        sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
        sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
        a, b = owner[sa], owner[sb]
        pair = ok[sa] & ok[sb] & (a != b)
        gap = np.abs((Zf[sa] + g[sa] * res / 2) - (Zf[sb] - g[sb] * res / 2))
        dg = np.hypot(gc[sa] - gc[sb], gr[sa] - gr[sb])
        j = pair & (gap < step)
        L[sa] |= j
        C[sa] |= j & (dg > CREASE)
        n_join += int(j.sum())
        n_crease += int((j & (dg > CREASE)).sum())
        n_step += int((pair & ~j).sum())
    return LR, LD, CR, CD, n_join, n_step, n_crease


class _Plane:
    """Plane through a surface near a band (cells 1.5-10 m from it), for the band tests; the
    nearest cell of the surface gives the distance."""

    def __init__(self, Zr, cells, dband, res):
        rr, cc = cells
        self.rr, self.cc = rr, cc
        self.tree = cKDTree(np.column_stack(cells))
        d = dband[rr, cc] * res
        sel = (d >= 1.5) & (d <= 10.0)
        if sel.sum() < 12:
            sel = d <= 10.0
        if sel.sum() < 3:
            sel = np.ones(len(rr), bool)
        A = np.column_stack([np.ones(sel.sum()), rr[sel], cc[sel]])
        z = Zr[rr[sel], cc[sel]]
        self.p = np.linalg.lstsq(A, z, rcond=None)[0] if sel.sum() >= 3 else np.array([np.median(z), 0, 0])

    def __call__(self, r, c):
        d, _ = self.tree.query(np.column_stack([r, c]))
        return self.p[0] + self.p[1] * r + self.p[2] * c, d


def pockets(comp, cliff, paved, res):
    """Small regions (< POCKET m2) enclosed by cliffs: their paved neighbours are all cliff cells
    and cliffs make up at least a third of their outline (not a path hanging off a steep end)."""
    out = np.zeros(comp.shape, bool)
    for k, sl in enumerate(ndi.find_objects(comp + 1)):
        if sl is None:
            continue
        rs = slice(max(sl[0].start - 1, 0), sl[0].stop + 1)
        cs = slice(max(sl[1].start - 1, 0), sl[1].stop + 1)
        m = comp[rs, cs] == k
        if m.sum() * res * res >= POCKET:
            continue
        rim = ndi.binary_dilation(m) & ~m
        rim_paved = rim & paved[rs, cs]
        if rim_paved.any() and cliff[rs, cs][rim_paved].all() and rim_paved.sum() >= rim.sum() / 3:
            out[rs, cs] |= m
    return out


def cross_bands(owner, D, cliff, LR, LD, CR, CD, comp, Zr, res, grad, verbose=False):
    """Decide every band of cliff cells (module doc, step 3). A band whose data slopes one way
    along it (grad: data gradient per row/col) is a real steep surface (a stair, a steep path)
    and keeps its data, joined to all the surfaces around it. Otherwise the paved cells around the
    band are 'upper' or 'lower' against the band next to them (median of the band data within
    3 m): only upper cells around it -> a dip (the ground under a bridge, a hole), only lower -> a
    bump, both -> a wall, whose two sides are never joined. Sides of different surfaces are joined
    when their planes meet across the band. Returns the updated links and the cells carried by a
    surface without their data."""
    H, W = owner.shape
    paved = owner >= 0
    pocket = pockets(comp, cliff, paved, res)
    bands, nb = ndi.label(cliff | pocket, np.ones((3, 3)))
    LR, LD, CR, CD = LR.copy(), LD.copy(), CR.copy(), CD.copy()
    nodata = np.zeros(owner.shape, bool)
    steep = np.zeros(owner.shape, bool)
    wall_side = np.full(owner.shape, -1, np.int32)                     # sides of the walls (see Surface)
    n_side = 0
    stats = {"crossed": 0, "filled": 0, "wall": 0, "slope": 0}
    reach = BAND_REACH / res
    near = int(round(3.0 / res))
    for b, sl in enumerate(ndi.find_objects(bands), start=1):
        pad = int(reach) + 2
        rs = slice(max(sl[0].start - pad, 0), min(sl[0].stop + pad, H))
        cs = slice(max(sl[1].start - pad, 0), min(sl[1].stop + pad, W))
        band = bands[rs, cs] == b
        pk = band & pocket[rs, cs]
        cl = band & ~pk
        cmp_w, cliff_w, own_w = comp[rs, cs], cliff[rs, cs] | pocket[rs, cs], owner[rs, cs]
        Dw = D[rs, cs]
        ring = ndi.binary_dilation(band, iterations=2) & ~cliff_w & (cmp_w >= 0)
        if not ring.any():
            # a steep patch on its own: one surface with its data
            for L, ax in ((LR[rs, cs], 1), (LD[rs, cs], 0)):
                sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
                sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
                L[sa] |= band[sa] & band[sb]
            continue
        br, bc = np.nonzero(band)
        # a real steep surface: the data slope keeps one direction, along the band (not across
        # an elongated band, which is a wall)
        g = np.column_stack([grad[0][rs, cs][br, bc], grad[1][rs, cs][br, bc]])
        gm = g.mean(0)
        kappa = np.linalg.norm(gm) / max(np.linalg.norm(g, axis=1).mean(), 1e-9)
        if len(br) >= 3:
            ev, evec = np.linalg.eigh(np.cov(np.column_stack([br, bc]).T.astype(float)))
            aspect = np.sqrt(max(ev[1], 1e-9) / max(ev[0], 1e-9))
            along = abs(evec[:, 1] @ gm) / max(np.linalg.norm(gm), 1e-9)
        else:
            aspect, along = 1.0, 1.0
        if kappa > 0.5 and not (aspect > 2.0 and along < 0.5):
            for L, C, ax in ((LR[rs, cs], CR[rs, cs], 1), (LD[rs, cs], CD[rs, cs], 0)):
                sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
                sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
                inner = band[sa] & band[sb]
                edge = (band[sa] & ring[sb]) | (ring[sa] & band[sb])
                L[sa] |= inner | edge
                C[sa] |= edge                        # the steep surface meets the flat ones at a crease
            steep[rs, cs] |= band
            stats["slope"] += 1
            continue
        # upper / lower cells around the band
        btree = cKDTree(np.column_stack([br, bc]))
        rr, rc = np.nonzero(ring)
        nbh = btree.query_ball_point(np.column_stack([rr, rc]), near)
        ref = np.array([np.median(Dw[br[i], bc[i]]) if len(i) else np.nan for i in map(np.array, nbh)])
        diff = np.nan_to_num(Dw[rr, rc] - ref)
        up = diff >= 0
        n_up, n_lo = int((diff > STEP_BAND / 2).sum()), int((diff < -STEP_BAND / 2).sum())
        wall = min(n_up, n_lo) >= 0.2 * len(rr)
        # sides: (surface, upper/lower) for a wall, surface only otherwise
        side = np.zeros(band.shape, np.int64) - 1
        keys = {}
        for i in range(len(rr)):
            k = (int(cmp_w[rr[i], rc[i]]), bool(up[i]) if wall else True)
            side[rr[i], rc[i]] = keys.setdefault(k, len(keys))
        # the rest of each surface near the band joins the side of its nearest ring cell
        dband = ndi.distance_transform_edt(~band)
        zone = (dband * res <= 10.0) & ~cliff_w & (cmp_w >= 0) & (side < 0)
        zr, zc = np.nonzero(zone)
        if len(zr):
            rt = cKDTree(np.column_stack([rr, rc]))
            _, j = rt.query(np.column_stack([zr, zc]))
            same = cmp_w[zr, zc] == cmp_w[rr[j], rc[j]]
            side[zr[same], zc[same]] = side[rr[j[same]], rc[j[same]]]
        pl = {v: _Plane(Zr[rs, cs], np.nonzero(side == v), dband, res) for v in keys.values()}
        # join the sides of different surfaces that meet across the band
        parent = {v: v for v in keys.values()}

        def find(a):
            while parent[a] != a:
                a = parent[a]
            return a
        kv = list(keys.items())
        zd = {v: pl[v](br, bc) for _, v in kv}
        for i, (ka, va) in enumerate(kv):
            for kb, vb in kv[i + 1:]:
                if ka[0] == kb[0]:
                    continue                            # the two sides of one wall
                (za, da), (zb, db) = zd[va], zd[vb]
                m = (da <= reach) & (db <= reach)
                if m.sum() >= 4 and np.median(np.abs(za[m] - zb[m])) < STEP_BAND:
                    parent[find(va)] = find(vb)
        groups = {}
        for _, v in kv:
            groups.setdefault(find(v), []).append(v)
        glist = list(groups.values())
        crossed = any(len(g) > 1 for g in glist)
        # enclosed regions: carried, unless they are another polygon than the one around them
        # (a yard below a wall) and nothing crosses the band
        ring_own = set(np.unique(own_w[ring]).tolist())
        carried = cl.copy()
        for k in np.unique(cmp_w[pk]):
            m = pk & (cmp_w == k)
            if crossed or not wall or int(np.bincount(own_w[m]).argmax()) in ring_own:
                carried |= m
            else:
                v = len(pl)
                side[m] = v
                pl[v] = _Plane(Zr[rs, cs], np.nonzero(m), dband, res)
                glist.append([v])
        # carried cells go to the nearest side group
        cr, cc_ = np.nonzero(carried)
        dist = np.full(len(cr), np.inf)
        gidx = np.zeros(len(cr), int)
        for gi, vs in enumerate(glist):
            d = np.min([pl[v].tree.query(np.column_stack([cr, cc_]))[0] for v in vs], axis=0)
            better = d < dist
            dist[better] = d[better]
            gidx[better] = gi
        lab = np.full(band.shape, -1)
        for gi, vs in enumerate(glist):
            lab[np.isin(side, vs) & ~carried] = gi
        lab[cr, cc_] = gidx
        # links: carried cell - carried cell or carried cell - side cell of the same group
        for L, ax in ((LR[rs, cs], 1), (LD[rs, cs], 0)):
            sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
            sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
            touch = carried[sa] | carried[sb]
            L[sa] &= ~touch
            L[sa] |= touch & (lab[sa] >= 0) & (lab[sa] == lab[sb])
        CR[rs, cs] &= LR[rs, cs]
        CD[rs, cs] &= LD[rs, cs]
        nodata[rs, cs] |= carried
        if len(glist) > 1:
            sw = wall_side[rs, cs]
            sw[lab >= 0] = n_side + lab[lab >= 0]
            n_side += len(glist)
        stats["crossed"] += crossed
        stats["wall"] += wall
        stats["filled"] += not wall and not crossed
    if verbose:
        print("  cliff bands %d: bridged %d, holes/bumps filled %d, walls kept %d, steep surfaces kept %d"
              % (nb, stats["crossed"], stats["filled"], stats["wall"], stats["slope"]))
    return LR, LD, CR, CD, nodata, steep, wall_side


class Surface:
    """Fitted paved surfaces on a north-up raster window (row 0 = y_max): Z on every paved cell,
    polygon of every cell (owner), the links between neighbouring cells of one surface and the
    creases among them. A facet is a connected surface (comp), or one side of a wall inside it
    (side: a road climbing away from the one below it inside one polygon stays one surface, joined
    where the wall ends, but its two sides must not borrow heights from each other)."""

    def __init__(self, owner, Z, LR, LD, x_min, y_max, res, CR=None, CD=None, side=None):
        self.owner, self.Z = np.asarray(owner, np.int32), np.asarray(Z, np.float64)
        self.LR, self.LD = np.asarray(LR, bool), np.asarray(LD, bool)
        self.CR = np.zeros(self.LR.shape, bool) if CR is None else np.asarray(CR, bool)
        self.CD = np.zeros(self.LD.shape, bool) if CD is None else np.asarray(CD, bool)
        self.side = np.full(self.owner.shape, -1, np.int32) if side is None else np.asarray(side, np.int32)
        self.x_min, self.y_max, self.res = float(x_min), float(y_max), float(res)
        mask = self.owner >= 0
        self.comp = cell_components(mask, self.LR, self.LD)
        self.facet = np.full(self.owner.shape, -1, np.int64)
        pairs = np.column_stack([self.comp[mask], self.side[mask]])
        _, inv = np.unique(pairs, axis=0, return_inverse=True)
        self.facet[mask] = inv.ravel()
        # slopes for the extrapolation: not across creases (a steep path next to a road)
        gc, gr = gradients(self.Z, self.LR & ~self.CR, self.LD & ~self.CD, self.res)
        g = np.hypot(gc, gr)
        f = np.minimum(1.0, EXTRAP_SLOPE / np.maximum(g, 1e-9))
        self.gc, self.gr = (gc * f).astype(np.float32), (gr * f).astype(np.float32)
        # nearest paved cell of every window cell (for points off the paved area)
        _, (self.nr, self.nc) = ndi.distance_transform_edt(~mask, return_indices=True)
        self._trees = {}

    # ---------------------------------------------------------------- io
    def save(self, path):
        np.savez_compressed(path, owner=self.owner, Z=self.Z.astype(np.float32), LR=self.LR, LD=self.LD,
                            CR=self.CR, CD=self.CD, side=self.side, x_min=self.x_min, y_max=self.y_max, res=self.res)

    @classmethod
    def load(cls, path):
        d = np.load(path)
        get = lambda k: d[k] if k in d.files else None
        return cls(d["owner"], d["Z"].astype(np.float64), d["LR"], d["LD"], float(d["x_min"]),
                   float(d["y_max"]), float(d["res"]), get("CR"), get("CD"), get("side"))

    # ---------------------------------------------------------------- sampling
    def _rc(self, x, y):
        return (self.y_max - y) / self.res - 0.5, (x - self.x_min) / self.res - 0.5

    def _tree(self, key):
        if key not in self._trees:
            pid, facet = key
            m = self.owner >= 0
            if pid is not None:
                m &= self.owner == pid
            if facet is not None:
                m &= self.facet == facet
            rr, cc = np.nonzero(m)
            self._trees[key] = (cKDTree(np.column_stack([rr, cc])) if len(rr) else None, rr, cc)
        return self._trees[key]

    def cell_at(self, x, y):
        """(row, col) of the nearest paved cell (-1 outside the window)."""
        r, c = self._rc(np.asarray(x, np.float64), np.asarray(y, np.float64))
        ri, ci = np.round(r).astype(int), np.round(c).astype(int)
        ok = (ri >= 0) & (ri < self.Z.shape[0]) & (ci >= 0) & (ci < self.Z.shape[1])
        nr = np.full(np.shape(ri), -1)
        nc = np.full(np.shape(ri), -1)
        nr[ok], nc[ok] = self.nr[ri[ok], ci[ok]], self.nc[ri[ok], ci[ok]]
        return nr, nc

    def polygons_at(self, x, y):
        """Polygon of the nearest paved cell (-1 outside the window)."""
        nr, nc = self.cell_at(x, y)
        return np.where(nr >= 0, self.owner[np.maximum(nr, 0), np.maximum(nc, 0)], -1)

    def surfaces_at(self, x, y):
        """Facet of the nearest paved cell (-1 outside the window)."""
        nr, nc = self.cell_at(x, y)
        return np.where(nr >= 0, self.facet[np.maximum(nr, 0), np.maximum(nc, 0)], -1)

    def surfaces_at_polygon(self, x, y, pid):
        """Facet of the nearest cell of polygon `pid` (-1 if the polygon has no cell)."""
        tree, rr, cc = self._tree((int(pid), None))
        if tree is None:
            return np.full(np.shape(x), -1)
        r, c = self._rc(np.asarray(x, np.float64), np.asarray(y, np.float64))
        _, j = tree.query(np.column_stack([np.ravel(r), np.ravel(c)]))
        return self.facet[rr[j], cc[j]].reshape(np.shape(x))

    def distance(self, x, y):
        """Distance (m) from (x, y) to the nearest paved cell centre (inf outside the window)."""
        r, c = self._rc(np.asarray(x, np.float64), np.asarray(y, np.float64))
        nr, nc = self.cell_at(x, y)
        return np.where(nr >= 0, np.hypot(nr - r, nc - c) * self.res, np.inf)

    def height(self, x, y, pid=None, comp=None):
        """Height at (x, y) of the surface of polygon `pid` and/or facet `comp` (default: those of
        the nearest paved cell): bilinear where the four cells around the point are linked cells of
        that facet, planar extrapolation from the nearest cells of it elsewhere."""
        x = np.atleast_1d(np.asarray(x, np.float64)); y = np.atleast_1d(np.asarray(y, np.float64))
        shape = x.shape
        x, y = x.ravel(), y.ravel()
        out = np.full(len(x), np.nan)
        r, c = self._rc(x, y)
        if pid is None and comp is None:
            nr, nc = self.cell_at(x, y)
            okc = nr >= 0
            P = np.where(okc, self.owner[np.maximum(nr, 0), np.maximum(nc, 0)], -1).astype(np.int64)
            C = np.where(okc, self.facet[np.maximum(nr, 0), np.maximum(nc, 0)], -1).astype(np.int64)
            key = np.where(okc, P * (int(self.facet.max()) + 2) + C, -1)
            uk, inv = np.unique(key, return_inverse=True)
            groups = {}
            for j, kv in enumerate(uk):
                if kv < 0:
                    continue
                i = np.where(inv == j)[0]
                groups[(int(P[i[0]]), int(C[i[0]]))] = i
        else:
            groups = {(pid, comp): np.arange(len(x))}
        H, W = self.Z.shape
        for key, k in groups.items():
            tree, rr, cc = self._tree(key)
            if tree is None:
                continue
            kq = min(4, len(rr))
            dd, jj = tree.query(np.column_stack([r[k], c[k]]), k=kq)
            dd, jj = dd.reshape(len(k), kq), jj.reshape(len(k), kq)
            nr, nc = rr[jj[:, 0]], cc[jj[:, 0]]
            fac = self.facet[nr, nc]
            r0 = np.floor(r[k]).astype(int); c0 = np.floor(c[k]).astype(int)
            ok = (r0 >= 0) & (r0 < H - 1) & (c0 >= 0) & (c0 < W - 1)
            r0c, c0c = np.clip(r0, 0, H - 2), np.clip(c0, 0, W - 2)
            for a in (0, 1):
                for b in (0, 1):
                    ok &= self.facet[r0c + a, c0c + b] == fac
            ok &= self.LR[r0c, c0c] & self.LR[r0c + 1, c0c] & self.LD[r0c, c0c] & self.LD[r0c, c0c + 1]
            fr, fc = r[k] - r0c, c[k] - c0c
            z00 = self.Z[r0c, c0c]; z01 = self.Z[r0c, c0c + 1]
            z10 = self.Z[r0c + 1, c0c]; z11 = self.Z[r0c + 1, c0c + 1]
            bil = (1 - fr) * ((1 - fc) * z00 + fc * z01) + fr * ((1 - fc) * z10 + fc * z11)
            # planar extrapolation from the nearest cells of the facet (inverse distance weights)
            ext = np.zeros(len(k))
            wsum = np.zeros(len(k))
            for q in range(kq):
                nr_, nc_ = rr[jj[:, q]], cc[jj[:, q]]
                same = self.facet[nr_, nc_] == fac
                dr, dc = r[k] - nr_, c[k] - nc_
                dist = np.hypot(dr, dc) * self.res
                f = np.minimum(1.0, EXTRAP_MAX / np.maximum(dist, 1e-9))
                zq = self.Z[nr_, nc_] + (self.gc[nr_, nc_] * dc + self.gr[nr_, nc_] * dr) * self.res * f
                w = np.where(same, 1.0 / (dd[:, q] * self.res + 0.25) ** 2, 0.0)
                ext += w * zq
                wsum += w
            out[k] = np.where(ok, bil, ext / np.maximum(wsum, 1e-12))
        return out.reshape(shape)


def carriageway_mask(shape, x_min, y_max, res, C, N, tL, tR, half_max=6.0):
    """Cells of the carriageway strip [tR, tL] along a centre line C (normals N), every 0.25 m."""
    m = np.zeros(shape, bool)
    s_step = np.linalg.norm(np.diff(C, axis=0), axis=1).mean() if len(C) > 1 else 0.5
    reps = max(1, int(np.ceil(s_step / 0.25)))
    for k in range(reps):
        f = k / reps
        Ck = C[:-1] + (C[1:] - C[:-1]) * f
        Nk = N[:-1] + (N[1:] - N[:-1]) * f
        lo = np.maximum(tR[:-1], -half_max)
        hi = np.minimum(tL[:-1], half_max)
        for t in np.arange(-half_max, half_max + 1e-6, 0.25):
            ok = (t >= lo) & (t <= hi)
            P = Ck[ok] + Nk[ok] * t
            r = np.floor((y_max - P[:, 1]) / res).astype(int)
            c = np.floor((P[:, 0] - x_min) / res).astype(int)
            v = (r >= 0) & (r < shape[0]) & (c >= 0) & (c < shape[1])
            m[r[v], c[v]] = True
    return m


def fit(owner, D, x_min, y_max, res, main=None, verbose=True):
    """Fit the paved surfaces. owner: polygon index per cell (-1 = none), D: data heights on the
    same north-up raster, main: optional mask of the main carriageway (stiffer smoothing).
    Returns (Surface, info dict)."""
    owner = np.asarray(owner, np.int32)
    paved = owner >= 0
    # 1. cliffs: slope of the lightly smoothed data (differences between paved cells only)
    Ds = smooth_paved(D, paved, 1.0)
    gx, gy = gradients(Ds, *link_same(np.where(paved, 0, -1), paved), res)   # per col / per row
    slope = np.hypot(gx, gy)
    cliff = paved & (slope > CLIFF)
    cliff = ndi.binary_dilation(cliff) & paved
    # 2. regions and their surfaces; polygons joined where their surfaces meet
    flat = paved & ~cliff
    LR, LD = link_same(owner, flat)
    reg = cell_components(flat, LR, LD)
    Zr, _ = fit_components(D, LR, LD, reg, res, LC_REGION)
    LR, LD, CR, CD, n_join, n_step, n_crease = step_links(owner, Zr, LR, LD, flat, res)
    comp = cell_components(flat, LR, LD)
    Zr, _ = fit_components(D, LR, LD, comp, res, LC_REGION, CR=CR, CD=CD)
    # 3. cliff bands: crossed (bridges), filled (holes, bumps), shared out (walls) or kept (stairs)
    LR, LD, CR, CD, nodata, steep, side = cross_bands(owner, D, cliff, LR, LD, CR, CD, comp, Zr, res, (gy, gx),
                                                      verbose=verbose)
    # 4. final fit of every connected surface; steep surfaces follow their data
    comp = cell_components(paved, LR, LD)
    size = np.bincount(comp[paved]) * res * res
    tiny = paved & (size[np.maximum(comp, 0)] < MIN_SURFACE)
    for L, ax in ((LR, 1), (LD, 0)):
        sa = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None))
        sb = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
        j = (tiny[sa] | tiny[sb]) & paved[sa] & paved[sb]
        L[sa] |= j
        nodata[sa] |= j & tiny[sa]
        nodata[sb] |= j & tiny[sb]
    comp = cell_components(paved, LR, LD)
    lc = np.full(owner.shape, LC) if main is None else np.where(main, LC_MAIN, LC)
    lc[steep] = LC_STEEP
    Z, WR = fit_components(D, LR, LD, comp, res, lc, nodata=nodata, CR=CR, CD=CD, protect=steep, verbose=verbose)
    data = paved & ~nodata
    info = {"polygons": int(owner.max()) + 1, "surfaces": int(comp.max()) + 1,
            "edge_joined_m": n_join * res, "edge_step_m": n_step * res, "edge_crease_m": n_crease * res,
            "cliff_frac": float(cliff.sum() / max(paved.sum(), 1)),
            "rejected_frac": float(np.mean(WR[data] < 0.05)),
            "change_p50": float(np.nanmedian(np.abs(Z - D)[data])),
            "change_p99": float(np.nanpercentile(np.abs(Z - D)[data], 99))}
    if verbose:
        print("paved surfaces: %d polygons -> %d surfaces; polygon edges %.0f m joined (%.0f m at a crease), "
              "%.0f m steps; cliff cells %.1f %%; data rejected %.1f %%; |surface - DTM| p50 %.3f m, p99 %.2f m"
              % (info["polygons"], info["surfaces"], info["edge_joined_m"], info["edge_crease_m"], info["edge_step_m"],
                 100 * info["cliff_frac"], 100 * info["rejected_frac"], info["change_p50"], info["change_p99"]))
    return Surface(owner, Z, LR, LD, x_min, y_max, res, CR, CD, side), info
