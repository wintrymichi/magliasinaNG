"""Forest on the rest of the terrain block (v3.0): the woods outside the cadastral survey.

Every tree of the map came from the canopy model of swissSURFACE3D inside the cadastral survey
(trees.py), so outside it the terrain block had no tree at all: the slopes beyond the playable area,
the Collina d'Oro, the Italian side of the Tresa and of the lake were meadow from the roads up to the
ridges, and from the valley the mountains around the map looked bald, with the edge of the survey
drawn across them.

Here the woods there come back as far trees (far_trees.py: the drawn models the game shows as a
picture, two triangles a tree), on the forest of ESA WorldCover 2021 (download_worldcover.py, 10 m,
both sides of the border):
- where: every terrain cell of the block outside the survey (no cadastral land cover under it) that
  WorldCover calls tree cover, not within EDGE m of the block's edge, not in the lake (WorldCover water
  or the ground under LAKE_GAP m over the lake level) nor on rock steeper than MAX_SLOPE;
- how many: one tree on a jittered grid of SPACING m (the measured forest has about one tree every
  9-10 m; these are seen from 500 m and more, so fewer and wider trees close the canopy for a fraction
  of the count);
- heights and colours: drawn from the trees measured in the forest of the area (their heights, their
  orthophoto colours), so the woods outside look like the woods inside; the crown is at least
  CROWN_FILL times the spacing, so neighbouring crowns meet;
- conifers: a share that grows with the altitude (chestnut and beech woods below about 900 m, more
  spruce and larch on the ridges of the Malcantone).
fill(...) returns the trees as the fields of trees.npz (plus 'conifer'), for vegetation.far_items.
"""
import os
import numpy as np
from rasterio import features
from scipy import ndimage as ndi
from config import WORK, TER_SIZE, TER_SQUARE, TER_X0, TER_Y0, TER_X1, TER_Y1
from geo import Grid, mosaic, local_grid

RES = 5.0                  # m, the grid the land cover is read on
SPACING = 14.0             # m between the trees of the fill (jittered grid)
JITTER = 0.42              # of the spacing, each way
EDGE = 20.0                # m from the edge of the terrain block
SURVEY_GAP = 6.0           # m from the cadastral survey (its own trees reach to its edge)
LAKE_GAP = 1.0             # m over the lake level
MAX_SLOPE = 55.0           # degrees
CROWN_FILL = 1.15          # crown diameter at least this times the spacing
MIN_H = 8.0                # m, heights drawn from the measured forest trees at least this high
CONIFER_Z = (850.0, 1500.0, 0.05, 0.45)   # altitude (m) at which the conifer share starts and ends rising, shares
SEED = 23
TREE_COVER = 10
WATER, BUILT = 80, 50


def worldcover_grid():
    """WorldCover classes on a RES m local grid over the terrain block (Grid, uint8, 0 = none)."""
    a = mosaic("worldcover/*.tif", TER_X0, TER_Y0, TER_X1, TER_Y1, RES, src_crs="EPSG:4326",
               dtype=np.uint8, nodata=0)[0]
    return Grid(a, TER_X0, TER_Y1, RES)


def survey_mask(shape):
    """Cells of the RES m block grid inside the cadastral survey (landcover05 not 'none'), grown by SURVEY_GAP."""
    from landcover import CODE
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    a, x_min, y_max, res = lc["a"], float(lc["x_min"]), float(lc["y_max"]), float(lc["res"])
    f = int(round(RES / res))
    h, w = a.shape[0] // f, a.shape[1] // f
    has = (a[:h * f, :w * f] != CODE["none"]).reshape(h, f, w, f).any((1, 3))
    out = np.zeros(shape, bool)
    c0 = int(round((x_min - TER_X0) / RES)); r0 = int(round((TER_Y1 - y_max) / RES))
    rs, cs = max(r0, 0), max(c0, 0)
    re, ce = min(r0 + h, shape[0]), min(c0 + w, shape[1])
    if re > rs and ce > cs:
        out[rs:re, cs:ce] = has[rs - r0:re - r0, cs - c0:ce - c0]
    return ndi.binary_dilation(out, iterations=max(1, int(np.ceil(SURVEY_GAP / RES))))


def terrain_sampler():
    """Heights of the built terrain (work/terrain_heights.npy, written by terrain.build_terrain) at local points."""
    H = np.load(os.path.join(WORK, "terrain_heights.npy"), mmap_mode="r")

    def fn(x, y):
        c = np.clip((np.asarray(x) - TER_X0) / TER_SQUARE, 0, TER_SIZE - 1.001)
        r = np.clip((np.asarray(y) - TER_Y0) / TER_SQUARE, 0, TER_SIZE - 1.001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        z = (H[r0, c0] * (1 - fc) * (1 - fr) + H[r0, c0 + 1] * fc * (1 - fr)
             + H[r0 + 1, c0] * (1 - fc) * fr + H[r0 + 1, c0 + 1] * fc * fr)
        return np.asarray(z, np.float64)
    return fn


def fill(measured, lake_level=None, spacing=SPACING):
    """Far trees for the forest outside the survey. measured: the fields of trees.npz (the measured trees,
    whose heights, crowns and colours are drawn from). Returns a dict of arrays (x, y, z, h, d, sharp,
    rgb, lc, dist_path, conifer)."""
    from landcover import CODE
    wc = worldcover_grid()
    a = np.asarray(wc.a)
    forest = a == TREE_COVER
    forest &= ~survey_mask(a.shape)
    water = ndi.binary_dilation(a == WATER, iterations=2)
    forest &= ~water
    e = int(np.ceil(EDGE / RES))
    forest[:e], forest[-e:], forest[:, :e], forest[:, -e:] = False, False, False, False
    rng = np.random.default_rng(SEED)
    gx = np.arange(TER_X0 + EDGE, TER_X1 - EDGE, spacing)
    gy = np.arange(TER_Y0 + EDGE, TER_Y1 - EDGE, spacing)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.uniform(-JITTER, JITTER, X.size) * spacing
    y = Y.ravel() + rng.uniform(-JITTER, JITTER, X.size) * spacing
    r, c = wc.rc(x, y)
    r, c = np.round(r).astype(int), np.round(c).astype(int)
    ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
    ok[ok] = forest[r[ok], c[ok]]
    x, y = x[ok], y[ok]
    zf = terrain_sampler()
    z = zf(x, y)
    # no tree on the lake or on its shore, nor on a cliff
    if lake_level is not None:
        keep = z > lake_level + LAKE_GAP
        x, y, z = x[keep], y[keep], z[keep]
    dzx = (zf(x + 3.0, y) - zf(x - 3.0, y)) / 6.0
    dzy = (zf(x, y + 3.0) - zf(x, y - 3.0)) / 6.0
    keep = np.degrees(np.arctan(np.hypot(dzx, dzy))) < MAX_SLOPE
    x, y, z = x[keep], y[keep], z[keep]
    n = len(x)
    # heights, crowns and colours drawn from the measured forest trees
    woods = np.isin(measured["lc"], [CODE["bosco_fitto"], CODE["altro_bosco"], CODE["pascolo_boscato_fitto"]]) \
        & (measured["h"] >= MIN_H)
    if woods.sum() < 100:
        woods = measured["h"] >= MIN_H
    pick = rng.choice(np.flatnonzero(woods), n)
    h = measured["h"][pick] * rng.uniform(0.9, 1.1, n)
    d = np.maximum(measured["d"][pick], CROWN_FILL * spacing)
    rgb = measured["rgb"][pick].astype(np.float32)
    z0, z1, p0, p1 = CONIFER_Z
    p_con = p0 + (p1 - p0) * np.clip((z - z0) / (z1 - z0), 0, 1)
    conifer = rng.uniform(0, 1, n) < p_con
    print("forest fill: %d far trees on %.1f km2 of forest outside the survey (one every %.0f m), %d conifers"
          % (n, forest.sum() * RES * RES / 1e6, spacing, int(conifer.sum())))
    return {"x": x, "y": y, "z": z, "h": h, "d": d, "sharp": np.where(conifer, 0.3, 0.05),
            "rgb": rgb, "lc": np.full(n, CODE["none"], measured["lc"].dtype),
            "dist_path": np.full(n, 1e9), "conifer": conifer}


GAP_SPACING = 8.0          # m: the jittered grid of the gap fill (v3.0)
GAP_FREE = 5.5             # m: no tree (measured, in the level or far) this close to a tree of the gap fill
GAP_ROAD = 10.0            # m from a road surface
GAP_PATH = 4.0             # m from a path surface
GAP_LC = ("bosco_fitto", "altro_bosco", "pascolo_boscato_fitto")


def gap_fill(measured, trees_xy, road_xy, path_xy, lake_level=None, spacing=GAP_SPACING):
    """v3.0: far trees in the gaps of the woods inside the survey. The trees there are the tops found in the
    canopy model, and near the roads and paths (where vegetation.thin keeps them all and no far tree is
    added) they stood a crown or two apart on bare forest floor, a sparse band along every road and path
    through the woods with the dense far trees beyond it (screenshot 42). Here a tree goes on every point of
    a jittered grid of `spacing` m in the forest of the cadastral land cover (GAP_LC) with no tree within
    GAP_FREE m (trees_xy: every tree measured, in the level or far), GAP_ROAD m from the road surfaces and
    GAP_PATH m from the path surfaces; its height, crown and colour are those of the nearest measured tree.
    Returns the fields of fill()."""
    from scipy.spatial import cKDTree
    from landcover import CODE
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    a, x_min, y_max, res = lc["a"], float(lc["x_min"]), float(lc["y_max"]), float(lc["res"])
    rng = np.random.default_rng(SEED + 1)
    gx = np.arange(TER_X0 + EDGE, TER_X1 - EDGE, spacing)
    gy = np.arange(TER_Y0 + EDGE, TER_Y1 - EDGE, spacing)
    X, Y = np.meshgrid(gx, gy)
    x = X.ravel() + rng.uniform(-JITTER, JITTER, X.size) * spacing
    y = Y.ravel() + rng.uniform(-JITTER, JITTER, X.size) * spacing
    r = np.floor((y_max - y) / res).astype(np.int64)
    c = np.floor((x - x_min) / res).astype(np.int64)
    ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
    ok[ok] = np.isin(a[r[ok], c[ok]], [CODE[k] for k in GAP_LC])
    x, y = x[ok], y[ok]
    P = np.column_stack([x, y])
    keep = cKDTree(trees_xy).query(P)[0] > GAP_FREE if len(trees_xy) else np.ones(len(P), bool)
    if len(road_xy):
        keep &= cKDTree(road_xy).query(P)[0] > GAP_ROAD
    if len(path_xy):
        keep &= cKDTree(path_xy).query(P)[0] > GAP_PATH
    x, y = x[keep], y[keep]
    zf = terrain_sampler()
    z = zf(x, y)
    keep = np.ones(len(x), bool) if lake_level is None else z > lake_level + LAKE_GAP
    dzx = (zf(x + 3.0, y) - zf(x - 3.0, y)) / 6.0
    dzy = (zf(x, y + 3.0) - zf(x, y - 3.0)) / 6.0
    keep &= np.degrees(np.arctan(np.hypot(dzx, dzy))) < MAX_SLOPE
    x, y, z = x[keep], y[keep], z[keep]
    n = len(x)
    woods = np.flatnonzero(np.isin(measured["lc"], [CODE[k] for k in GAP_LC]) & (measured["h"] >= MIN_H))
    if len(woods) < 100:
        woods = np.flatnonzero(measured["h"] >= MIN_H)
    near = woods[cKDTree(np.column_stack([measured["x"][woods], measured["y"][woods]])).query(np.column_stack([x, y]))[1]]
    h = measured["h"][near] * rng.uniform(0.85, 1.05, n)
    d = np.maximum(measured["d"][near], spacing)
    rgb = measured["rgb"][near].astype(np.float32)
    z0, z1, p0, p1 = CONIFER_Z
    conifer = rng.uniform(0, 1, n) < p0 + (p1 - p0) * np.clip((z - z0) / (z1 - z0), 0, 1)
    print("forest gap fill: %d far trees in the gaps of the woods of the survey (grid %.0f m)" % (n, spacing))
    return {"x": x, "y": y, "z": z, "h": h, "d": d, "sharp": np.where(conifer, 0.3, 0.05),
            "rgb": rgb, "lc": np.full(n, CODE["none"], measured["lc"].dtype),
            "dist_path": np.full(n, 1e9), "conifer": conifer}


def layer_classes(X, Y):
    """WorldCover class at local points X, Y (any shape; 0 where there is none), for the terrain layers."""
    wc = worldcover_grid()
    return wc.sample(np.ravel(X), np.ravel(Y), order=0).reshape(np.shape(X)).astype(np.uint8)
