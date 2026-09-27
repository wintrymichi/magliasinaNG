"""Lago di Lugano as water blocks that stop at its shore (v2.0).

v1.0 used one infinite WaterPlane at the lake level. The v2.0 area reaches down the Tresa valley
west of Ponte Tresa, where the ground is up to 40 m below the lake (the river leaves the lake at
270.5 m and is at 232 m where it leaves the area): an infinite plane would flood the valley.

Lake mask on a GRID m grid around the terrain block (out to the backdrop radius):
- swissALTI3D 2 m: the lake surface is flat at the lake level (median DTM over the surveyed lake);
- Copernicus (Italian side): flat cells at the Copernicus height of the Swiss part of the lake;
- only cells connected to the largest lake body, with the Tresa outlet at Ponte Tresa closed
  (DAM m around the first point of the river in swissTLM3D).
The lake within NEAR m of the terrain block is covered by a few axis-aligned rectangles that contain
no dry land lower than the lake (they may cover higher land, where the water stays under the
ground); every rectangle becomes a WaterBlock of THICK m whose middle is at the lake level (+/-
THICK/4 whichever way the engine takes the box), with a coarse surface grid (GRID_ELEMENT m).
The lake bed of the terrain and of the near backdrop is lowered under the water (lake_bed); the
lake farther away is drawn by the backdrop mesh itself, flat and dark at the lake level.
"""
import json, os
import numpy as np
from scipy import ndimage as ndi
from rasterio.warp import Resampling
from config import DATA, WORK, lv95_to_local
from geo import Grid, mosaic
import bng

GRID = 25.0
RADIUS = 24000.0
NEAR = 2000.0
DAM = 60.0
THICK = 1.0
GRID_ELEMENT = 25.0
LOW = 0.5            # m, dry land this far below the lake must not be covered


def lake_level():
    """Median swissALTI3D height over the surveyed lake (cells not filled from Copernicus)."""
    from landcover import CODE
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    nod = np.load(os.path.join(WORK, "dtm05_nodata.npy"), mmap_mode="r")
    vals = []
    a = lc["a"]
    for r0 in range(0, a.shape[0], 2048):
        m = (a[r0:r0 + 2048] == CODE["specchio_acqua"]) & ~np.asarray(nod[r0:r0 + 2048])
        if m.any():
            vals.append(np.asarray(dtm.a[r0:r0 + 2048])[m])
    v = np.concatenate(vals) if vals else np.array([])
    return float(np.median(v)) if len(v) else 270.5


def tresa_outlet():
    """First point (upstream end) of the Tresa in swissTLM3D (local x, y)."""
    f = os.path.join(DATA, "tlm", "TLM_FLIESSGEWAESSER.json")
    if not os.path.exists(f):
        return None
    best = None
    for ft in json.load(open(f))["features"]:
        if (ft["props"].get("NAME") or "") != "Tresa":
            continue
        P = np.array(ft["parts"][0])
        if best is None or P[0, 2] > best[2]:
            best = P[0]
    if best is None:
        return None
    x, y = lv95_to_local(best[0], best[1])
    return float(x), float(y)


def lake_mask(level, cx, cy):
    """(mask, heights, x0, y1) on a GRID m grid of +-RADIUS around (cx, cy)."""
    x0, y0, x1, y1 = cx - RADIUS, cy - RADIUS, cx + RADIUS, cy + RADIUS
    hs = mosaic("swissalti3d_2/*.tif", x0, y0, x1, y1, GRID, resampling=Resampling.average)[0]
    hc = mosaic("copdem30/*.tif", x0, y0, x1, y1, GRID, src_crs="EPSG:4326")[0]
    swiss = np.abs(hs - level) < 0.25
    rng = ndi.maximum_filter(np.nan_to_num(hc, nan=-1e4), 3) - ndi.minimum_filter(np.nan_to_num(hc, nan=1e4), 3)
    lc_cop = float(np.nanmedian(hc[swiss])) if swiss.any() else level
    cop = np.isnan(hs) & (np.abs(hc - lc_cop) < 0.6) & (rng < 0.6)
    water = ndi.binary_closing(swiss | cop, iterations=1) & (swiss | cop | np.isnan(hs))
    out = tresa_outlet()
    dam = np.zeros(water.shape, bool)
    if out is not None:
        X = x0 + (np.arange(water.shape[1]) + 0.5) * GRID
        Y = y1 - (np.arange(water.shape[0]) + 0.5) * GRID
        dam = np.hypot(X[None, :] - out[0], Y[:, None] - out[1]) < DAM
    lab, n = ndi.label(water & ~dam)
    if n == 0:
        return np.zeros(water.shape, bool), hs, x0, y1
    sizes = ndi.sum(np.ones(water.shape), lab, range(1, n + 1))
    lake = lab == (int(np.argmax(sizes)) + 1)
    # the dam cells that touch the lake belong to it (the lake side of the outlet)
    lake |= dam & water & ndi.binary_dilation(lake, iterations=1)
    h = np.where(np.isnan(hs), hc - lc_cop + level, hs)
    print("lake: level %.2f m, Copernicus lake height %.2f, %.1f km2 within %.0f km" %
          (level, lc_cop, lake.sum() * GRID ** 2 / 1e6, RADIUS / 1000), flush=True)
    return lake, h, x0, y1


def _greedy(todo, region):
    """Rectangles over `region` cells covering every `todo` cell: from the first uncovered cell
    the larger of right-then-down and down-then-right growth."""
    todo = todo.copy()
    region = region.copy()               # free cells: rectangles never overlap (coplanar water would flicker)
    out = []
    H, W = todo.shape
    while todo.any():
        r0, c0 = (int(v) for v in np.argwhere(todo)[0])
        best = None
        for first in ("right", "down"):
            c1, r1 = c0, r0
            if first == "right":
                while c1 + 1 < W and region[r0, c1 + 1]:
                    c1 += 1
                while r1 + 1 < H and region[r1 + 1, c0:c1 + 1].all():
                    r1 += 1
            else:
                while r1 + 1 < H and region[r1 + 1, c0]:
                    r1 += 1
                while c1 + 1 < W and region[r0:r1 + 1, c1 + 1].all():
                    c1 += 1
            gain = int(todo[r0:r1 + 1, c0:c1 + 1].sum())
            if best is None or gain > best[0]:
                best = (gain, (r0, r1 + 1, c0, c1 + 1))
        r0_, r1_, c0_, c1_ = best[1]
        out.append(best[1])
        todo[r0_:r1_, c0_:c1_] = False
        region[r0_:r1_, c0_:c1_] = False
    return out


def rectangles(lake, forbidden, coarse=4, reach=3):
    """Axis-aligned rectangles (r0, r1, c0, c1) on the lake grid covering every lake cell and no
    forbidden cell (dry land lower than the lake). They may cover higher dry land near the lake
    (invisible under the ground), which keeps them few: first on blocks of `coarse` x `coarse`
    cells without forbidden cells, then the lake cells left (next to forbidden land) cell by cell."""
    H, W = lake.shape
    hc, wc = -(-H // coarse), -(-W // coarse)
    pad = lambda a, v: np.pad(a, ((0, hc * coarse - H), (0, wc * coarse - W)), constant_values=v)
    lk = pad(lake, False).reshape(hc, coarse, wc, coarse).any((1, 3))
    fb = pad(forbidden, True).reshape(hc, coarse, wc, coarse).any((1, 3))
    ok_c = lk & ~fb
    region_c = ndi.binary_dilation(lk, iterations=reach) & ~fb
    out = [(r0 * coarse, min(r1 * coarse, H), c0 * coarse, min(c1 * coarse, W))
           for r0, r1, c0, c1 in _greedy(ok_c, region_c)]
    covered = np.zeros(lake.shape, bool)
    for r0, r1, c0, c1 in out:
        covered[r0:r1, c0:c1] = True
    rest = lake & ~covered
    if rest.any():
        region = ndi.binary_dilation(lake, iterations=2) & ~forbidden & ~covered
        out += _greedy(rest, region)
    return out


def build(scene, cx, cy, params, block):
    """Water blocks over the lake near the terrain block (x0, y0, x1, y1); returns (level, lake
    mask grid, covered mask grid) for the lake beds and the backdrop."""
    level = lake_level()
    lake, h, x0, y1 = lake_mask(level, cx, cy)
    low = ~lake & (np.nan_to_num(h, nan=level + 10) < level - LOW)
    lab, n = ndi.label(low)
    if n:
        sizes = ndi.sum(np.ones(low.shape), lab, range(1, n + 1))
        low = np.isin(lab, np.where(sizes >= 4)[0] + 1)
    X = x0 + (np.arange(lake.shape[1]) + 0.5) * GRID
    Y = y1 - (np.arange(lake.shape[0]) + 0.5) * GRID
    bx0, by0, bx1, by1 = block
    near = ((X[None, :] > bx0 - NEAR) & (X[None, :] < bx1 + NEAR) & (Y[:, None] > by0 - NEAR) & (Y[:, None] < by1 + NEAR))
    rects = rectangles(lake & near, low, coarse=8, reach=40)
    covered = np.zeros(lake.shape, bool)
    p = dict(params, gridElementSize=GRID_ELEMENT)
    for i, (r0, r1, c0, c1) in enumerate(rects):
        covered[r0:r1, c0:c1] = True
        obj = {"name": f"LagoDiLugano_{i:02d}", "class": "WaterBlock", "persistentId": bng.pid(),
               "position": [round(x0 + 0.5 * (c0 + c1) * GRID, 2), round(y1 - 0.5 * (r0 + r1) * GRID, 2), round(level, 3)],
               "scale": [round((c1 - c0) * GRID, 2), round((r1 - r0) * GRID, 2), THICK]}
        obj.update(p)
        scene.add("MissionGroup/level_objects/Water", obj)
    flooded = int((covered & ~lake & (np.nan_to_num(h, nan=999) < level - LOW)).sum())
    print("water blocks %d over %.0f km2 (lake %.1f km2), dry land below the lake covered: %d cells" %
          (len(rects), covered.sum() * GRID ** 2 / 1e6, (lake & near).sum() * GRID ** 2 / 1e6, flooded), flush=True)
    return level, Grid(lake.astype(np.uint8), x0, y1, GRID), Grid((lake & covered).astype(np.uint8), x0, y1, GRID)


def lake_bed(H, xs, ys, level, lake_grid):
    """Terrain under the lake: at least 1 m under the water, deeper away from the shore (max 6 m)."""
    X, Y = np.meshgrid(xs, ys)
    inside = lake_grid.sample(X.ravel(), Y.ravel(), order=0).reshape(X.shape) > 0
    if not inside.any():
        return H
    step = xs[1] - xs[0]
    d = ndi.distance_transform_edt(inside) * step
    bed = level - np.minimum(1.0 + 0.1 * d, 6.0)
    return np.where(inside, np.minimum(H, bed), H)
