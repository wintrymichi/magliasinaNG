"""Hedges seen in the street photos (v3.0.40): which strips of low vegetation of the surface model are hedges.

The surface model (swissSURFACE3D) over the bare ground (swissALTI3D) shows every strip of something LOW m high and
narrower than THICK m along the streets: a hedge, but just as well a wall, a fence with a sheet on it, a row of
parked cars or a shed the cadastral survey does not draw. understory.py plants hedges on such strips along the old
Street View route only. Here the photos with a fitted pose (street_pose.py) tell them apart: every cell of a strip is
cast into each photo that sees it (the scene's own depth there no nearer than the strip) and the photo's class at
that pixel (Mapillary Vistas: vegetation; wall, fence, building, sky ...) is a vote. Cars, people and poles in front
vote for nothing.

    candidates(scene) -> dict(x, y, z, h, h0, theta) of the cells of the strips, every STEP m
    votes(cam, pano, classmap, names, cells) -> (n, 2) int: (vegetation, other) per cell
    verdicts(cells, votes) -> [[x, y, h, theta, veg, other], ...] of the cells some photo saw
"""
import numpy as np
from scipy import ndimage as ndi

LOW = (0.6, 4.0)              # m over the bare ground: how high a hedge stands
THICK = 3.0                   # m: a hedge is a strip narrower than this
COH = 0.55                    # coherence of the structure tensor: an elongated strip (as understory.py)
STEP = 1.0                    # m between the cells voted on
NEAR, FAR = 2.0, 30.0         # m from the camera
BEHIND = 1.2                  # m: the scene's depth along the ray may be this much nearer (the strip's own face)
VOTE_DOWN = 0.4               # m under the top of a cell: the point the photos vote on
VEG = {"Vegetation"}
OTHER = {"Wall", "Fence", "Barrier", "Guard Rail", "Building", "Bridge", "Billboard", "Banner", "Sky", "Road",
         "Sidewalk", "Parking", "Pedestrian Area", "Terrain"}


def candidates(scene, step=STEP):
    """The cells of the strips of low vegetation of a scene (street_scene.load): x, y (centres), h (m over the bare
    ground), theta (radians, direction of the strip in the local frame)."""
    dsm, dtm, bid, res = scene["dsm"], scene["dtm"], scene["bid"], scene["res"]
    chm = dsm - dtm
    low = (chm > LOW[0]) & (chm < LOW[1]) & (bid < 0)
    low = ndi.binary_opening(low, iterations=1)
    m = ndi.gaussian_filter(low.astype(np.float32), 1.0)
    gy, gx = np.gradient(m)                                  # rows run south: gy is -d/dy
    Jxx = ndi.gaussian_filter(gx * gx, 3)
    Jyy = ndi.gaussian_filter(gy * gy, 3)
    Jxy = ndi.gaussian_filter(gx * gy, 3)
    tr = Jxx + Jyy
    disc = np.sqrt(np.maximum(tr ** 2 / 4 - (Jxx * Jyy - Jxy * Jxy), 0))
    coh = 2 * disc / np.maximum(tr, 1e-9)
    thick = 2 * ndi.distance_transform_edt(low) * res
    strip = low & (coh > COH) & (ndi.maximum_filter(thick, 5) < THICK)
    # the strip runs across the dominant gradient; in the image frame (columns east, rows south)
    theta_img = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2
    k = max(1, int(round(step / res)))
    r, c = np.nonzero(strip)
    sel = (r % k == 0) & (c % k == 0)
    r, c = r[sel], c[sel]
    x = scene["x_min"] + (c + 0.5) * res
    y = scene["y_max"] - (r + 0.5) * res
    h = ndi.maximum_filter(chm, 3)[r, c]
    return {"x": x, "y": y, "z": dtm[r, c], "h": h.astype(np.float32), "h0": chm[r, c].astype(np.float32),
            "theta": (-theta_img[r, c]).astype(np.float32)}       # rows point south: the local angle is the opposite


def votes(cam, pano, classmap, names, cells):
    """(n, 2) votes of one photo for the cells: (vegetation, other); the cells it does not see vote for nothing."""
    n = len(cells["x"])
    out = np.zeros((n, 2), np.int32)
    # the point voted on: just under the cell's own top (not the 3 x 3 maximum, which may be a neighbour's eaves or
    # crown; not low down, where the bare ground of the 0.5 m model smooths the step of a wall under a hedge)
    P = np.column_stack([cells["x"], cells["y"], cells["z"] + cells["h0"] - np.minimum(VOTE_DOWN, 0.4 * cells["h0"])])
    dh = np.hypot(P[:, 0] - cam.pos[0], P[:, 1] - cam.pos[1])
    near = (dh >= NEAR) & (dh <= FAR)
    if not near.any():
        return out
    idx = np.nonzero(near)[0]
    u, v, dist, ok = cam.project(P[idx])
    H, W = classmap.shape
    c = np.floor((np.where(ok, u, -1) + 0.5) * W / cam.W).astype(int)
    r = np.floor((np.where(ok, v, -1) + 0.5) * H / cam.H).astype(int)
    ok &= (c >= 1) & (c < W - 1) & (r >= 1) & (r < H - 1)
    # the scene seen from the camera there: nothing (a building, a wall of trees) much nearer than the strip
    D = pano.lookup(P[idx] - cam.pos)[2]
    ok &= D >= dist - BEHIND
    veg = np.zeros(len(names) + 1, bool)
    oth = np.zeros(len(names) + 1, bool)
    for i, nm in names.items():
        veg[int(i)] = nm in VEG
        oth[int(i)] = nm in OTHER
    for j in np.nonzero(ok)[0]:
        blk = classmap[r[j] - 1:r[j] + 2, c[j] - 1:c[j] + 2].ravel()
        blk = blk[blk < len(veg)]
        nv, no = int(veg[blk].sum()), int(oth[blk].sum())
        if nv >= 5:
            out[idx[j], 0] += 1
        elif no >= 5:
            out[idx[j], 1] += 1
    return out


def verdicts(cells, vt):
    """The cells some photo saw: [x, y, h, theta, vegetation votes, other votes]."""
    seen = vt.sum(1) > 0
    return [[round(float(cells["x"][i]), 2), round(float(cells["y"][i]), 2), round(float(cells["h"][i]), 2),
             round(float(cells["theta"][i]), 3), int(vt[i, 0]), int(vt[i, 1])] for i in np.nonzero(seen)[0]]
