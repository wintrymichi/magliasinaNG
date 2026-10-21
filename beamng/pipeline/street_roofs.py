"""The roofs seen against the sky in the street photos (v3.0.40): how far the roof line of a building of the 3D model
(swissBUILDINGS3D) lies above or below the one the photos show. A roof raised, lowered or rebuilt since the survey,
an attic or a storey added, a roof drawn flat that is pitched: the photos see the true line wherever a building
stands against the sky.

In every column of a photo with a fitted pose where the scene (street_render: the surface model) shows a building
against the sky, the top of that building's mesh (swissBUILDINGS3D, the roofs and walls the game draws) is compared
with the photo's roof line there (its segmentation: building under, sky over); the difference of the two angles at the
distance of the roof is a height. Per building: the median over the columns and photos and how many saw it.

    residuals(cam, pano, lab, blds, step=4, detail=None) -> {scene building index: [dz, ...]}
    summary({bi: [dz]}) -> {bi: (median dz, count, spread)}
"""
from collections import defaultdict
import numpy as np
import street_render as sr

SEARCH = 5.0                  # m above and below the model's roof line where the photo's is looked for
NEAR = 8.0                    # m: nearer, a photo sees the underside of the eaves, not the roof line


def mesh_top(cam, b, W, H, px=0.4):
    """The top of a building's mesh (roofs and walls) as the camera sees it, in a label map of W x H: per column the
    row (float) and the distance of its highest point (NaN where the mesh is not in the column)."""
    T = np.concatenate([t for t in (b["roofs"], b["walls"]) if len(t)]) if len(b["roofs"]) or len(b["walls"]) else None
    top, dist = np.full(W, np.nan), np.full(W, np.nan)
    if T is None:
        return top, dist
    rad = np.radians(cam.deg_per_px() * cam.W / W)     # radians per column of the label map
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):                # points along every edge, px columns apart at most
        A, B = T[:, i], T[:, j]
        near = np.maximum(0.5, np.minimum.reduce([np.linalg.norm(Q - cam.pos, axis=1) for Q in (A, B, 0.5 * (A + B))]))
        n = np.clip(np.ceil(np.linalg.norm(B - A, axis=1) / (px * rad * near)), 1, 20000).astype(int)
        idx = np.repeat(np.arange(len(A)), n + 1)
        t = np.arange(len(idx)) - np.repeat(np.cumsum(n + 1) - (n + 1), n + 1)
        t = t / np.repeat(n, n + 1)
        pts.append(A[idx] + t[:, None] * (B - A)[idx])
    P = np.concatenate(pts)
    u, v, d, ok = cam.project(P)
    ok &= np.isfinite(u)
    c = np.floor((np.where(ok, u, -cam.W) + 0.5) * W / cam.W).astype(int)
    r = (v + 0.5) * H / cam.H - 0.5
    ok &= (c >= 0) & (c < W) & np.isfinite(r)
    c, r, d = c[ok], r[ok], d[ok]
    if not len(c):
        return top, dist
    o = np.lexsort((r, c))
    first = np.r_[True, c[o][1:] != c[o][:-1]]
    k = o[first]
    top[c[k]], dist[c[k]] = r[k], d[k]
    return top, dist


def residuals(cam, pano, lab, blds, step=4, far=80.0, detail=None):
    """Height differences (m, photo minus mesh) of the roof lines in the columns of a photo, per building; detail (a
    list) gets (building, column, mesh row, photo row, dz) of every column measured (rows of the label map)."""
    H, W = lab.shape
    sx, sy = cam.W / W, cam.H / H
    out = defaultdict(list)
    deg = cam.deg_per_px() * sx                         # degrees per pixel of the label map
    tops = {}
    for c in range(0, W, step):
        vs = np.arange(H)
        d = cam.dirs(np.full(H, (c + 0.5) * sx - 0.5), (vs + 0.5) * sy - 0.5)
        L, B, D = pano.lookup(d)
        # the scene's roof line: sky over a building, going down the column; the building the photo sees there
        sky = L == sr.SKY
        edge = np.nonzero(sky[:-1] & (L[1:] == sr.BUILDING))[0]
        if not len(edge):
            continue
        bi = int(B[int(edge[0]) + 1])
        if bi < 0:
            continue
        if bi not in tops:
            tops[bi] = mesh_top(cam, blds[bi], W, H)
        rm, dist = tops[bi][0][c], tops[bi][1][c]
        if not np.isfinite(rm) or not np.isfinite(dist) or not NEAR <= dist <= far or not 0 <= rm < H - 1:
            continue
        # the photo's roof line near the mesh's: the last sky row over the first building row in the window
        k = int(np.ceil(min(25.0, np.degrees(np.arctan(SEARCH / max(dist, 1.0)))) / deg))
        r = int(round(rm))
        r0, r1 = max(0, r - k), min(H - 1, r + k)
        col = lab[r0:r1 + 1, c]
        if (col == 255).mean() > 0.3:                   # a pole, a wire, a tree in front
            continue
        b = np.nonzero(col == sr.BUILDING)[0]
        if not len(b):
            continue
        rp = r0 + int(b[0])
        if rp <= r0 or lab[rp - 1, c] != sr.SKY:
            continue                                    # not sky over it: something else in front
        # rows -> angles -> height at the roof's distance; the boundary lies between the sky row and the building row
        dm = cam.dirs(np.array([(c + 0.5) * sx - 0.5]), np.array([(rm + 0.5) * sy - 0.5]))[0]
        dp = cam.dirs(np.array([(c + 0.5) * sx - 0.5]), np.array([rp * sy - 0.5]))[0]
        e_model = np.arcsin(np.clip(dm[2], -1, 1))
        e_photo = np.arcsin(np.clip(dp[2], -1, 1))
        horiz = dist * np.cos(e_model)
        out[bi].append(float(horiz * (np.tan(e_photo) - np.tan(e_model))))
        if detail is not None:
            detail.append((bi, c, float(rm), rp, out[bi][-1]))
    return out


def summary(res, least=6):
    """Per building: median height difference, number of columns, spread (interquartile range)."""
    out = {}
    for bi, v in res.items():
        if len(v) < least:
            continue
        v = np.asarray(v)
        q1, q2, q3 = np.percentile(v, [25, 50, 75])
        out[bi] = (float(q2), len(v), float(q3 - q1))
    return out
