"""Distant terrain around the terrain block (visual only, no collision).

Heights: swissALTI3D 2 m (Swiss side, NEAR m around the block centre) and Copernicus GLO-30
(elsewhere, out to RMAX), resampled to a ring mesh: 40 m cells up to NEAR, 100 m beyond; the
terrain block is left out with a 30 m overlap skirt. Earth curvature
(with standard refraction k = 0.13) lowers far vertices so distant ridges keep their
true elevation angle. Lake areas (flat at the lake level) are pushed 3 m under the
water plane so the level's water shows there. Colours: forest green by default,
brighter on flat low ground, lake bed dark.
"""
import os
import numpy as np
from rasterio.warp import Resampling
from config import TER_SIZE, TER_SQUARE, TER_X0, TER_Y0, WORK
from geo import mosaic
import bng

RMAX = 24000.0                    # m from the block centre
NEAR = 10800.0                    # m, swissALTI3D 2 m (download_swisstopo.BACKDROP_HALF) ring
R_EARTH = 6371000.0
HALF = (TER_SIZE - 1) * TER_SQUARE / 2
CX, CY = TER_X0 + HALF, TER_Y0 + HALF


def grid_heights(x0, y0, x1, y1, res):
    swiss = mosaic("swissalti3d_2/*.tif", x0, y0, x1, y1, res, resampling=Resampling.average)[0]
    cop = mosaic("copdem30/*.tif", x0, y0, x1, y1, res, src_crs="EPSG:4326")[0]
    ok = ~np.isnan(swiss) & ~np.isnan(cop)
    off = np.nanmedian(swiss[ok] - cop[ok]) if ok.sum() > 100 else 0.0
    h = np.where(np.isnan(swiss), cop + off, swiss)
    return h


def ring_mesh(mb, H, x0, y1, res, inner, outer, lake_level, lake_grid=None, wet_grid=None):
    ny, nx = H.shape
    xs = x0 + (np.arange(nx) + 0.5) * res
    ys = y1 - (np.arange(ny) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    r = np.maximum(np.abs(X - CX), np.abs(Y - CY))
    d = np.hypot(X - CX, Y - CY)
    Z = H - 0.87 * d ** 2 / (2 * R_EARTH)
    if lake_grid is not None:            # the lake of water.py (not the Tresa valley below it)
        lake = lake_grid.sample(X.ravel(), Y.ravel(), order=0).reshape(X.shape) > 0
        wet = wet_grid.sample(X.ravel(), Y.ravel(), order=0).reshape(X.shape) > 0 if wet_grid is not None else lake
    else:
        lake = wet = (H < lake_level + 1.5)
    # under the water blocks the lake bed is 3 m down; farther away the mesh is the water itself
    Z = np.where(wet, lake_level - 3.0, np.where(lake, lake_level - 0.87 * d ** 2 / (2 * R_EARTH), Z))
    keep_cell = np.ones((ny - 1, nx - 1), bool)
    rc = np.maximum(np.maximum(r[:-1, :-1], r[1:, 1:]), np.maximum(r[:-1, 1:], r[1:, :-1]))
    rcmin = np.minimum(np.minimum(r[:-1, :-1], r[1:, 1:]), np.minimum(r[:-1, 1:], r[1:, :-1]))
    keep_cell &= (rc > inner) & (rcmin < outer) & ~np.isnan(Z[:-1, :-1]) & ~np.isnan(Z[1:, 1:]) \
        & ~np.isnan(Z[:-1, 1:]) & ~np.isnan(Z[1:, :-1])
    V = np.column_stack([X.ravel(), Y.ravel(), np.nan_to_num(Z.ravel(), nan=0.0)])
    idx = np.arange(nx * ny).reshape(ny, nx)
    a, b, c, dd = idx[:-1, :-1][keep_cell], idx[:-1, 1:][keep_cell], idx[1:, 1:][keep_cell], idx[1:, :-1][keep_cell]
    T = np.concatenate([np.stack([a, dd, c], 1), np.stack([a, c, b], 1)])
    # colours: forest by default, lighter on gentle slopes at low altitude, dark lake bed
    gy, gx = np.gradient(np.nan_to_num(H), res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).ravel()
    col = np.tile([0.16, 0.22, 0.11, 1.0], (len(V), 1))
    open_ground = (slope < 12) & (H.ravel() < 700)
    col[open_ground] = [0.36, 0.40, 0.26, 1.0]
    col[lake.ravel()] = [0.10, 0.12, 0.10, 1.0]
    col[(lake & ~wet).ravel()] = [0.12, 0.20, 0.24, 1.0]          # open water beyond the water blocks
    used = np.unique(T)
    remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
    mb.add("mp_backdrop", V[used], uvs=V[used, :2] / 100.0, tris=remap[T], colors=col[used])


def build(level_dir, level_name, scene, lake_level, lake_grid=None, wet_grid=None):
    mb = bng.MeshBuilder()
    inner = HALF - 30.0
    H1 = grid_heights(CX - NEAR, CY - NEAR, CX + NEAR, CY + NEAR, 40.0)
    ring_mesh(mb, H1, CX - NEAR, CY + NEAR, 40.0, inner, NEAR, lake_level, lake_grid, wet_grid)
    H2 = grid_heights(CX - RMAX, CY - RMAX, CX + RMAX, CY + RMAX, 100.0)
    ring_mesh(mb, H2, CX - RMAX, CY + RMAX, 100.0, NEAR - 50, RMAX, lake_level, lake_grid, wet_grid)
    rel = "art/shapes/backdrop/backdrop.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="backdrop", origin=(0, 0, 0))
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "backdrop", "main.materials.json"), [
        bng.material("mp_backdrop", "/assets/materials/terrain/forest/t_macro_forest/t_macro_forest_b.png",
                     roughness=0.95, vert_color=True)])
    scene.add("MissionGroup/level_objects/backdrop", bng.tsstatic(f"/levels/{level_name}/{rel}", (0, 0, 0),
                                                                  collision=False, decal=False))
    print("backdrop triangles", mb.triangle_count())
