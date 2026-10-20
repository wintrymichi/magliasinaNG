"""Label and depth panoramas of the scene seen from a point (v3.0.40): what the street photos are aligned to and
what tells which facade a pixel shows.

The scene is the surface model (swissSURFACE3D 0.5 m: buildings, trees, walls, cars of the flight) near the point and
the terrain (swissALTI3D 2 m) farther out, every cell with a label: a building (inside the footprint of a building of
swissBUILDINGS3D: its index), vegetation (the surface stands VEG_H m over the bare ground outside the buildings) or
ground. It is rendered as a height field, one column of the panorama at a time: along the ray of the column's azimuth
the cells are visited from near to far, and each one fills the rows between the highest elevation seen so far and its
own (the "voxel space" renderer: a cell is the top of a vertical face). Rows no cell reaches are sky.

The panorama is an equirectangular image in the grid frame (street_camera: column 0 at azimuth -180 degrees, the
centre column looking to grid north, row 0 at the zenith).
    render(scene, pos, W) -> Panorama (label, building index, distance per pixel)
"""
import math
import numpy as np
from scipy.ndimage import map_coordinates

SKY, GROUND, VEG, BUILDING = 0, 1, 2, 3
NAMES = {SKY: "sky", GROUND: "ground", VEG: "vegetation", BUILDING: "building"}
VEG_H = 1.2                   # m of surface over the bare ground that is vegetation (outside the buildings)
EARTH_R = 6371000.0
REFRACTION = 0.13             # coefficient of the atmospheric refraction (the curvature drop is 1 - k of the geometric)
START = 3.0                   # m: the cells over a camera this near are a roof over it, not a wall in front of it


def distances(near=250.0, far=8000.0):
    """Horizontal distances (m) of the samples along a ray: 0.2 m steps up to 30 m, then steps of a fixed angle
    (finer near, where the cells of the surface model are, than over the smooth far terrain)."""
    d0 = np.arange(0.3, 30.0, 0.2)
    d1 = np.exp(np.arange(math.log(30.0), math.log(near), 0.005))
    d2 = np.exp(np.arange(math.log(near), math.log(far), 0.01))
    return np.concatenate([d0, d1, d2]), len(d0) + len(d1)


class Scene:
    """The height fields around a place.
    near: (dsm, dtm, bid) arrays of the same 0.5 m grid (x_min, y_max, res); bid = building index or -1.
    far: (dtm2, x_min, y_max, res) of the coarse terrain, or None."""

    def __init__(self, dsm, dtm, bid, x_min, y_max, res, far=None):
        self.dsm, self.dtm, self.bid = np.asarray(dsm, np.float32), np.asarray(dtm, np.float32), np.asarray(bid)
        self.x_min, self.y_max, self.res = float(x_min), float(y_max), float(res)
        self.far = far
        lab = np.full(self.dsm.shape, GROUND, np.int8)
        lab[(self.dsm - self.dtm) > VEG_H] = VEG
        lab[self.bid >= 0] = BUILDING
        self.lab = lab

    def rc(self, x, y, x_min=None, y_max=None, res=None):
        x_min = self.x_min if x_min is None else x_min
        y_max = self.y_max if y_max is None else y_max
        res = self.res if res is None else res
        return (y_max - y) / res - 0.5, (x - x_min) / res - 0.5

    def inside(self, x, y, margin=1.0):
        h, w = self.dsm.shape
        r, c = self.rc(x, y)
        return (r >= margin) & (r < h - 1 - margin) & (c >= margin) & (c < w - 1 - margin)

    def ground(self, x, y):
        r, c = self.rc(np.atleast_1d(x), np.atleast_1d(y))
        return map_coordinates(self.dtm, [r, c], order=1, mode="nearest")

    def surface(self, x, y):
        r, c = self.rc(np.atleast_1d(x), np.atleast_1d(y))
        return map_coordinates(self.dsm, [r, c], order=1, mode="nearest")


class Panorama:
    """A rendered panorama: label (H, W) int8, bid (H, W) int32 (-1 off buildings), dist (H, W) float32 (m, inf for
    the sky) seen from pos."""

    def __init__(self, pos, label, bid, dist):
        self.pos = np.asarray(pos, float)
        self.label, self.bid, self.dist = label, bid, dist
        self.H, self.W = label.shape

    def dirs(self, rows=None, cols=None):
        """World directions of pixel centres (rows, cols: index arrays of the same shape)."""
        if rows is None:
            rows, cols = np.mgrid[0:self.H, 0:self.W]
        lon = (np.asarray(cols) + 0.5) / self.W * 2 * np.pi - np.pi
        lat = np.pi / 2 - (np.asarray(rows) + 0.5) / self.H * np.pi
        cl = np.cos(lat)
        return np.stack([cl * np.sin(lon), cl * np.cos(lon), np.sin(lat)], -1)

    def lookup(self, d):
        """(label, bid, dist) of the pixels the world directions d (..., 3) fall in (nearest pixel)."""
        d = np.asarray(d, float)
        lon = np.arctan2(d[..., 0], d[..., 1])
        lat = np.arcsin(np.clip(d[..., 2] / np.maximum(np.linalg.norm(d, axis=-1), 1e-12), -1, 1))
        c = np.clip(((lon + np.pi) / (2 * np.pi) * self.W).astype(int), 0, self.W - 1)
        r = np.clip(((np.pi / 2 - lat) / np.pi * self.H).astype(int), 0, self.H - 1)
        return self.label[r, c], self.bid[r, c], self.dist[r, c]


def render(scene, pos, W=1440, H=None, near=250.0, far=8000.0):
    """The label panorama of the scene from pos (x, y, z), W columns (H = W / 2 rows)."""
    H = H or W // 2
    cx, cy, cz = (float(v) for v in pos)
    d, n_near = distances(near, far if scene.far is not None else near)
    lon = (np.arange(W) + 0.5) / W * 2 * np.pi - np.pi
    sx, sy = np.sin(lon), np.cos(lon)
    X = cx + sx[:, None] * d[None, :]                        # (W, K)
    Y = cy + sy[:, None] * d[None, :]
    K = len(d)
    hgt = np.full((W, K), -1e4, np.float32)
    lab = np.full((W, K), GROUND, np.int8)
    bid = np.full((W, K), -1, np.int32)
    # near: the surface model and the labels of its cells, the cell a sample falls in (a building is a block of
    # cells with vertical faces at their edges: the face and its label agree); outside the grid nothing, the far
    # terrain takes over
    r, c = scene.rc(X[:, :n_near], Y[:, :n_near])
    h, w = scene.dsm.shape
    ok = (r >= -0.5) & (r < h - 0.5) & (c >= -0.5) & (c < w - 0.5)
    ri = np.clip(np.rint(r).astype(np.int32), 0, h - 1)
    ci = np.clip(np.rint(c).astype(np.int32), 0, w - 1)
    hgt[:, :n_near] = np.where(ok, scene.dsm[ri, ci], -1e4)
    lab[:, :n_near] = np.where(ok, scene.lab[ri, ci], GROUND)
    bid[:, :n_near] = np.where(ok, scene.bid[ri, ci], -1)
    # a camera under a roof or a balcony (an arcade, the eaves over an alley): the cells over it up to START m away
    # are no walls for its rays, which pass under them until the first cell lower than the camera
    start = d < START
    over = (hgt[:, :start.sum()] > cz) & start[None, :start.sum()]
    if over[:, 0].any():
        free = np.cumprod(over, axis=1).astype(bool)           # the run of cells over the camera from the first on
        hgt[:, :start.sum()] = np.where(free, -1e4, hgt[:, :start.sum()])
    if scene.far is not None and K > n_near:
        g2, x0, y1, res = scene.far
        r2, c2 = scene.rc(X[:, n_near:], Y[:, n_near:], x0, y1, res)
        h2, w2 = g2.shape
        ok2 = (r2 >= 0) & (r2 <= h2 - 1) & (c2 >= 0) & (c2 <= w2 - 1)
        hf = map_coordinates(g2, [r2.ravel(), c2.ravel()], order=1, mode="nearest").reshape(r2.shape)
        drop = (1 - REFRACTION) * d[n_near:] ** 2 / (2 * EARTH_R)
        hgt[:, n_near:] = np.where(ok2, hf - drop[None, :], -1e4)
    e = np.arctan2(hgt - cz, d[None, :])                     # elevation of every sample
    M = np.maximum.accumulate(e, axis=1)
    lat = np.pi / 2 - (np.arange(H) + 0.5) / H * np.pi       # row elevations, descending
    # first sample whose running maximum reaches the row's elevation; one searchsorted for every column at once
    # (each column's maxima shifted by a constant larger than any elevation range keeps the whole array sorted)
    off = (np.arange(W) * 10.0)[:, None]
    flat = (M + off).ravel()
    q = (lat[::-1][None, :] + off).ravel()                   # ascending elevations within each column
    k = np.searchsorted(flat, q, side="left").reshape(W, H) - (np.arange(W) * K)[:, None]
    k = k[:, ::-1]                                           # back to rows from the zenith down
    sky = k >= K
    kk = np.minimum(k, K - 1)
    cols = np.arange(W)[:, None]
    L = np.where(sky, SKY, lab[cols, kk]).astype(np.int8).T
    B = np.where(sky, -1, bid[cols, kk]).astype(np.int32).T
    D = np.where(sky, np.inf, d[kk] / np.maximum(np.cos(lat)[None, :], 1e-6)).astype(np.float32).T
    # below the first sample the ray meets the ground under the camera, not a face at its distance
    low = (k == 0) & (lat[None, :] < e[:, :1]) & (hgt[:, :1] > -9e3)
    under = np.maximum(cz - hgt[:, :1], 0.05) / np.maximum(np.sin(-lat)[None, :], 1e-3)
    D = np.where(low.T, under.T, D).astype(np.float32)
    # the samples below the horizon of no data (outside every grid) are sky too
    D[(L != SKY) & (np.take_along_axis(hgt, kk, 1).T < -9e3)] = np.inf
    L[~np.isfinite(D)] = SKY
    B[~np.isfinite(D)] = -1
    return Panorama(pos, L, B, D)
