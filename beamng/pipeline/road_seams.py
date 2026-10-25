"""v3.1.1: no step between two pieces of carriageway (a finishing step of build_level.py, FINISH, on the built level;
alone: python build_level.py --finish road_seams).

The road surfaces are meshed piece by piece (the survey polygons, the Strada Cantonale corridor, the chunks), and
every piece hangs a vertical skirt under its outline (road_mesh.skirt_bands). Where two pieces of carriageway meet
at different heights the step between them is a sharp vertical lip with collision. After the hairpin of the
Magliaso - Pura road (about -176,-122 to -194,-104) the uphill lane was 22-26 cm lower than the rest for 40 m: the
player saw "a hole in the road on the right" (michi, 2026-10-25), and a lip like that, taken by a tyre at speed,
breaks a beam of the tyre: in BeamNG 0.40 (vehicle/beamstate.lua, beamBroken) a broken tyre beam deflates the tyre.

Here every outline edge of a carriageway piece with a higher carriageway face just beyond it (a seam, not an outer
edge) and a step between STEP_MIN and STEP_MAX m raises the lower piece into a ramp: its vertices within the ramp
length of the seam go up by the step times a cosine falloff (full at the seam, nothing at the end of the ramp), the
skirt corners at the same places with them. The paint, the wear, the islands, the pavements and the roundabouts
lying on a raised face go up with it (by the lift of the face under them). Steps over STEP_MAX are left: there the
pieces are different levels (a road under a deck, a road beside a wall). Only the vertex heights change."""
import json, os, re, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import optimize_level
from config import LEVEL_NAME
from road_mesh import TriSurface

CARRIAGEWAY = ("mp_road_asphalt", "mp_road_asphalt_fresh", "mp_road_sett", "mp_road_cobble")
STEP_MIN = 0.015       # m: a smaller step is a joint of the triangulation
STEP_MAX = 0.30        # m: a larger one is between two levels (network_mesh keeps surfaces this far apart separate)
PROBE = 0.05           # m beyond the edge where the face of the other piece is looked for
RAMP_PER_M = 12.0      # m of ramp per m of step ...
RAMP_MIN, RAMP_MAX = 0.75, 3.0   # ... within these
WELD = 0.002           # m: corners this near are one (the pieces of one surface)
SAMPLE = 0.25          # m between the samples of a seam edge
ON_FACE = (-0.05, 0.25)   # m: an overlay vertex this far over a face (paint, wear, kerbs) lies on it
OVERLAY_GROUPS = ("roads/markings", "roads/islands", "roads/sidewalks", "roads/roundabouts")


class Faces(TriSurface):
    """TriSurface that also tells which face is under each point (the one nearest a height)."""

    def face(self, x, y, zhint, lo=-np.inf, hi=np.inf):
        """Index of the face under each point whose height is within [zhint + lo, zhint + hi] and nearest zhint;
        -1 where none; and the barycentric weights (n, 3)."""
        x, y, zhint = (np.atleast_1d(np.asarray(a, np.float64)) for a in (x, y, zhint))
        out = np.full(len(x), -1, np.int64)
        w = np.zeros((len(x), 3))
        if not len(self.t) or not len(x):
            return out, w
        cx = np.floor((x - self.o[0]) / self.cell).astype(np.int64)
        cy = np.floor((y - self.o[1]) / self.cell).astype(np.int64)
        q = np.flatnonzero((cx >= 0) & (cx < self.W) & (cy >= 0) & (cy < self.H))
        key = cy[q] * self.W + cx[q]
        s = np.searchsorted(self.key, key, "left")
        cnt = np.searchsorted(self.key, key, "right") - s
        if not cnt.sum():
            return out, w
        rep = np.repeat(np.arange(len(q)), cnt)
        j = self.tid[np.repeat(s, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))]
        qi = q[rep]
        px, py = x[qi] - self.A[j, 0], y[qi] - self.A[j, 1]
        den = np.where(np.abs(self.den[j]) < 1e-12, 1e-12, self.den[j])
        l1 = (px * self.v1[j, 1] - self.v1[j, 0] * py) / den
        l2 = (self.v0[j, 0] * py - px * self.v0[j, 1]) / den
        z = self.a[j] + self.b[j] * x[qi] + self.c[j] * y[qi]
        d = z - zhint[qi]
        ok = (l1 >= -1e-6) & (l2 >= -1e-6) & (l1 + l2 <= 1 + 1e-6) & (d >= lo) & (d <= hi)
        qi, j, l1, l2, d = qi[ok], j[ok], l1[ok], l2[ok], d[ok]
        order = np.lexsort((np.abs(d), qi))
        qi, j, l1, l2 = qi[order], j[order], l1[order], l2[order]
        first = np.r_[True, qi[1:] != qi[:-1]] if len(qi) else np.zeros(0, bool)
        out[qi[first]] = j[first]
        w[qi[first]] = np.column_stack([1 - l1[first] - l2[first], l1[first], l2[first]])
        return out, w


def _items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()] \
        if name in zi.NameToInfo else []


def _shapes(zi, lv, group):
    """[(shape name, DAE text, position)] of the TSStatic pipeline shapes of a group."""
    out = []
    for o in _items(zi, f"{lv}/main/MissionGroup/{group}/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or not sn.endswith(".dae"):
            continue
        if o.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1]) != [1, 0, 0, 0, 1, 0, 0, 0, 1]:
            continue
        text = zi.read(sn).decode("utf-8")
        if "<triangles" in text and text.count("<geometry ") == 1:
            out.append((sn, text, np.asarray(o.get("position", [0, 0, 0]), np.float64)))
    return out


def _set_z(text, V):
    m = re.search(r'(<float_array id="g-pa" count="\d+">)([^<]*)(</float_array>)', text)
    num = " ".join(("%.4f" % v).rstrip("0").rstrip(".") for v in V.ravel()).replace("-0 ", "0 ")
    return text[:m.start(2)] + num + text[m.end(2):]


def _weld(P):
    """One id per group of points P closer than WELD (the corners of the faces of one surface)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pairs = cKDTree(P).query_pairs(WELD, output_type="ndarray")
    n = len(P)
    if not len(pairs):
        return np.arange(n)
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)),
                                directed=False)[1]


def seams(T, root, F):
    """Seam samples of every outline edge of the carriageway faces T (k, 3, 3) that has a higher carriageway face
    PROBE m beyond it: (m, 2) xy, outward normal (m, 2), step (m), ramp length (m) and the plane (m, 3: a, b, c of
    z = a + b x + c y) of that higher face."""
    k = len(T)
    R = root.reshape(k, 3)
    key = np.sort(np.stack([R, R[:, [1, 2, 0]]], 2).reshape(-1, 2), 1)      # edge i of face f: corners i, i + 1
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    open_ = (cnt[inv.ravel()] == 1).reshape(k, 3)
    fi, ei = np.nonzero(open_)
    a, b, c = T[fi, ei], T[fi, (ei + 1) % 3], T[fi, (ei + 2) % 3]
    L = np.linalg.norm(b[:, :2] - a[:, :2], axis=1)
    keep = L > 0.01
    fi, a, b, c, L = fi[keep], a[keep], b[keep], c[keep], L[keep]
    d = (b[:, :2] - a[:, :2]) / L[:, None]
    nrm = np.column_stack([d[:, 1], -d[:, 0]])
    flip = np.einsum("ij,ij->i", c[:, :2] - a[:, :2], nrm) > 0          # the normal points away from the face
    nrm[flip] *= -1
    m = np.maximum(1, np.ceil(L / SAMPLE)).astype(np.int64)
    ei = np.repeat(np.arange(len(L)), m)
    u = (np.arange(m.sum()) - np.repeat(np.cumsum(m) - m, m) + 0.5) / np.repeat(m, m)
    p = a[ei] + (b[ei] - a[ei]) * u[:, None]
    q = p[:, :2] + nrm[ei] * PROBE
    # the own face's plane continued to the probe, and the face of another piece over it there
    own = fi[ei]
    zs_own = F.a[own] + F.b[own] * q[:, 0] + F.c[own] * q[:, 1]
    j, _ = F.face(q[:, 0], q[:, 1], zs_own, STEP_MIN, STEP_MAX)
    ok = (j >= 0) & (j != own)
    j = np.maximum(j, 0)
    step = np.where(ok, F.a[j] + F.b[j] * q[:, 0] + F.c[j] * q[:, 1] - zs_own, 0.0)
    ok &= (step >= STEP_MIN) & (step <= STEP_MAX)
    return (p[ok, :2], nrm[ei[ok]], step[ok], np.clip(RAMP_PER_M * step[ok], RAMP_MIN, RAMP_MAX),
            np.column_stack([F.a[j[ok]], F.b[j[ok]], F.c[j[ok]]]))


SIDE_TOL = 0.02        # m: a corner this far beyond the seam (along its outward normal) is still on its low side


def lifts(P, sx, snrm, sdz, sR, splane):
    """Lift of every corner P (n, 3): the largest over the seam samples within their ramp length that it lies
    behind (on the low piece's side) and under (more than half the step below the higher face's plane, so the
    higher piece itself never moves): min(step, the depth under that plane) x (1 + cos(pi d / R)) / 2."""
    out = np.zeros(len(P))
    if not len(sx):
        return out
    tree = cKDTree(sx)
    for i, ii in enumerate(tree.query_ball_point(P[:, :2], r=RAMP_MAX)):
        if not ii:
            continue
        ii = np.asarray(ii)
        v = P[i, :2] - sx[ii]
        d = np.linalg.norm(v, axis=1)
        under = splane[ii, 0] + splane[ii, 1] * P[i, 0] + splane[ii, 2] * P[i, 1] - P[i, 2]
        ok = (d < sR[ii]) & (np.einsum("ij,ij->i", v, snrm[ii]) <= SIDE_TOL) & (under > 0.5 * sdz[ii])
        if not ok.any():
            continue
        f = 0.5 * (1 + np.cos(np.pi * d[ok] / sR[ii][ok]))
        out[i] = float((np.minimum(sdz[ii][ok], under[ok]) * f).max())
    return out


SAG_IN = 0.3           # m: the lane ends this far inside the AI road's half width
SAG_EPS = 0.08         # m under the middle of the road ...
SAG_SLOPE = 0.06       # ... plus this per m out from it (crossfall, superelevation) is no sag yet
SAG_MAX = 1.2          # m: a face further under is another level (a road beside, under a wall), not a sag
SAG_EDGE = 0.3         # m beyond the AI road's half width: the carriageway's own edge row is lifted too


def _ai_lines(zi, lv):
    """[(n, 4) nodes x, y, z, width] of the AI roads."""
    name = f"{lv}/main/MissionGroup/AIRoads/items.level.json"
    return [np.asarray(o["nodes"], np.float64) for o in _items(zi, name) if len(o.get("nodes", [])) > 1]


def sags(P, iscw, Tcw, lines):
    """Lift of every corner P (n, 3) of a road surface that lies inside an AI road's lane and further under the
    carriageway at the road's middle than a crossfall can explain: up to that floor. Where a track or a yard
    joins a road from below, its mesh pulled the road's edge down with it (Magliaso - Pura above the hairpins,
    545,-965: the uphill lane's edge 0.75 m down over 6.5 m, the "hole on the right", michi 2026-10-25)."""
    out = np.zeros(len(P))
    S = TriSurface(Tcw)
    X, Y, Z, Wd, L, D = [], [], [], [], [], []
    for n in lines:
        cum = np.r_[0, np.cumsum(np.hypot(*np.diff(n[:, :2], axis=0).T))]
        if cum[-1] < 1:
            continue
        s = np.arange(0, cum[-1], 0.5)
        x, y = np.interp(s, cum, n[:, 0]), np.interp(s, cum, n[:, 1])
        tx, ty = np.gradient(x), np.gradient(y)
        nn = np.maximum(np.hypot(tx, ty), 1e-9)
        X.append(x); Y.append(y); Z.append(np.interp(s, cum, n[:, 2])); Wd.append(np.interp(s, cum, n[:, 3]))
        D.append(np.column_stack([tx / nn, ty / nn])); L.append(np.column_stack([-ty / nn, tx / nn]))
    if not X:
        return out
    X, Y, Z, Wd = (np.concatenate(a) for a in (X, Y, Z, Wd))
    D, L = np.concatenate(D), np.concatenate(L)
    zc = S.height(X, Y, "near", zhint=Z)
    ok = np.isfinite(zc)
    X, Y, zc, Wd, D, L = X[ok], Y[ok], zc[ok], Wd[ok], D[ok], L[ok]
    tree = cKDTree(np.column_stack([X, Y]))
    dist, ii = tree.query(P[:, :2], k=6, distance_upper_bound=6.0)
    for c in range(ii.shape[1]):
        j = ii[:, c]
        has = np.isfinite(dist[:, c])
        j = np.where(has, j, 0)
        v = P[:, :2] - np.column_stack([X[j], Y[j]])
        along = np.abs(np.einsum("ij,ij->i", v, D[j]))
        off = np.abs(np.einsum("ij,ij->i", v, L[j]))
        floor = zc[j] - SAG_EPS - SAG_SLOPE * off
        depth = floor - P[:, 2]
        reach = np.where(iscw, Wd[j] / 2 + SAG_EDGE, Wd[j] / 2 - SAG_IN)
        hit = has & (along <= 0.4) & (off <= reach) & (depth > out) & (depth <= SAG_MAX)
        hit[hit] = _joined(S, np.column_stack([X[j[hit]], Y[j[hit]], zc[j[hit]]]), P[hit])
        out = np.where(hit, depth, out)
    # what joins the lifted edge from outside (the yard, the track, the next piece) ramps up to it
    up = np.flatnonzero(out > 0)
    if len(up):
        top = P[up, 2] + out[up]
        R = np.clip(RAMP_PER_M * out[up], RAMP_MIN, RAMP_MAX)
        tree = cKDTree(P[up, :2])
        for i, nb in enumerate(tree.query_ball_point(P[:, :2], r=RAMP_MAX)):
            if not nb or out[i] > 0:
                continue
            nb = np.asarray(nb)
            d = np.linalg.norm(P[i, :2] - P[up[nb], :2], axis=1)
            k = (d < R[nb]) & (top[nb] > P[i, 2])
            if k.any():
                f = 0.5 * (1 + np.cos(np.pi * d[k] / R[nb][k]))
                out[i] = float((np.minimum(out[up[nb[k]]], top[nb[k]] - P[i, 2]) * f).max())
    return out


def _joined(S, A, B, n=24):
    """Whether the carriageway runs from A to B (both (m, 3)) without a step over STEP_MAX: a sag slopes down to
    the edge; a road beside, under a wall or a skirt, is another level (the cantonale above Magliaso, 690,-1046,
    has a lower lane 1.2 m down inside the AI road's width)."""
    ok = np.ones(len(A), bool)
    z = A[:, 2].copy()
    for k in range(1, n + 1):
        u = k / n
        x, y = A[:, 0] + (B[:, 0] - A[:, 0]) * u, A[:, 1] + (B[:, 1] - A[:, 1]) * u
        h = S.height(x, y, "near", zhint=z)
        ok &= np.isfinite(h) & (np.abs(h - z) <= STEP_MAX * 0.5)
        z = np.where(np.isfinite(h), h, z)
    return ok & (np.abs(z - B[:, 2]) <= 0.1)


def road_seams_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    roads = _shapes(zi, lv, "roads/surfaces")
    # the top faces of the road surfaces (carriageway, yards, paths), every shape's corners in world coordinates
    Tw, owner, cw = [], [], []
    for si, (sn, text, pos) in enumerate(roads):
        V, N, UV, C, parts, node = optimize_level.parse(text)
        W = V + pos
        for mat, idx in parts:
            if mat == "mp_road_wall":
                continue
            vi = idx[:, 0].reshape(-1, 3)
            t = W[vi]
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
            Tw.append(t[up])
            owner.append(np.column_stack([np.full(int(up.sum()), si), vi[up]]))
            cw.append(np.full(int(up.sum()), mat in CARRIAGEWAY))
    res = {"faces": 0, "sag_corners": 0, "sag_cm_max": 0.0, "seam_m": 0.0, "step_cm_p50": 0.0, "step_cm_max": 0.0,
           "shapes": 0, "corners_raised": 0, "overlay_corners_raised": 0, "lift_cm_max": 0.0}
    if not Tw:
        print("road seams: no road surfaces", flush=True)
        return res
    Tall = np.concatenate(Tw)
    owner = np.concatenate(owner)                      # (k, 4): shape, three corner indices
    cw = np.concatenate(cw)
    Pall = Tall.reshape(-1, 3)
    # 1. no sag across a lane
    sag = sags(Pall, np.repeat(cw, 3), Tall[cw], _ai_lines(zi, lv))
    res["sag_corners"] = int((sag > 0).sum())
    res["sag_cm_max"] = round(float(sag.max(initial=0)) * 100, 1)
    # 2. no step between two pieces of carriageway (after the sags are lifted)
    T = (Pall + np.column_stack([np.zeros((len(Pall), 2)), sag])).reshape(-1, 3, 3)[cw]
    res["faces"] = len(T)
    P = T.reshape(-1, 3)
    root_ = _weld(P)
    F = Faces(T)
    sx, snrm, sdz, sR, splane = seams(T, root_, F)
    res["seam_m"] = round(len(sx) * SAMPLE, 1)
    if len(sdz):
        res["step_cm_p50"], res["step_cm_max"] = round(float(np.median(sdz)) * 100, 1), round(float(sdz.max()) * 100, 1)
    # one pass: a second one (seams left at corners where three pieces meet) took 217 -> 121 m of steps over 8 cm
    # and stacked ramps up to 78 cm high
    lift_cw = lifts(P, sx, snrm, sdz, sR, splane)
    # what is left (corners, a ramp ending on a third piece), for the report
    Pi = P + np.column_stack([np.zeros((len(P), 2)), lift_cw])
    left = seams(Pi.reshape(-1, 3, 3), root_, Faces(Pi.reshape(-1, 3, 3)))[2]
    res["seam_m_left"] = round(len(left) * SAMPLE, 1)
    res["seam_m_left_over_8cm"] = round(float((left >= 0.08).sum()) * SAMPLE, 1)
    lift = sag.copy()
    lift[np.repeat(cw, 3)] += lift_cw
    F = Faces(Tall)                                    # what lies on the road surfaces, before the lifts
    new = {}
    if lift.max(initial=0) > 0:
        res["lift_cm_max"] = round(float(lift.max()) * 100, 1)
        # per shape: the lift of each of its vertices that is a corner of a raised face, and every other vertex at
        # the same place (the skirt's upper corners, the corners of the neighbouring faces of the piece)
        corner_shape = np.repeat(owner[:, 0], 3)
        corner_vi = owner[:, 1:].ravel()
        for si, (sn, text, pos) in enumerate(roads):
            sel = (corner_shape == si) & (lift > 0)
            if not sel.any():
                continue
            V, N, UV, C, parts, node = optimize_level.parse(text)
            key = np.round(V * 1000).astype(np.int64)
            _, g = np.unique(key, axis=0, return_inverse=True)
            g = g.ravel()
            gl = np.zeros(g.max() + 1)
            np.maximum.at(gl, g[corner_vi[sel]], lift[sel])
            dz = gl[g]
            V2 = V.copy()
            V2[:, 2] += dz
            new[sn] = _set_z(text, V2).encode("utf-8")
            res["shapes"] += 1
            res["corners_raised"] += int((dz > 0).sum())
        # what lies on the raised faces: by the lift of the face under it
        flift = lift.reshape(-1, 3)
        for grp in OVERLAY_GROUPS:
            for sn, text, pos in _shapes(zi, lv, grp):
                V, N, UV, C, parts, node = optimize_level.parse(text)
                W = V + pos
                j, w = F.face(W[:, 0], W[:, 1], W[:, 2], -ON_FACE[1], -ON_FACE[0])
                dz = np.where(j >= 0, (flift[np.maximum(j, 0)] * w).sum(1), 0.0)
                if not (dz > 1e-4).any():
                    continue
                V2 = V.copy()
                V2[:, 2] += dz
                new[sn] = _set_z(text, V2).encode("utf-8")
                res["overlay_corners_raised"] += int((dz > 1e-4).sum())
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new:
                ni = zipfile.ZipInfo(i.filename, now)          # a new date: the game converts the shape again
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    res["seconds"] = round(time.time() - t0)
    print("road seams:", res, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return res


if __name__ == "__main__":
    import sys
    road_seams_step(sys.argv[1], report=sys.argv[2] if len(sys.argv) > 2 else None)
