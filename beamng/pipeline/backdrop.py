"""Distant terrain around the playable square (visual only, no collision).

Heights: swissALTI3D 2 m (Swiss side, +-8 km) and Copernicus GLO-30 (elsewhere, out
to +-RMAX), resampled to a ring mesh: 40 m cells up to 8 km, 100 m beyond; the inner
square (playable terrain) is left out with a 30 m overlap skirt. Earth curvature
(with standard refraction k = 0.13) lowers far vertices so distant ridges keep their
true elevation angle. Lake areas (flat at the lake level) are pushed 3 m under the
water plane so the level's water shows there. Colours: forest green by default,
brighter on flat low ground, lake bed dark.
"""
import os
import numpy as np
from rasterio.warp import Resampling
from config import TER_HALF, WORK
from geo import mosaic
import bng

RMAX = 20000.0
R_EARTH = 6371000.0


def grid_heights(x0, y0, x1, y1, res):
    swiss = mosaic("swissalti3d_2/*.tif", x0, y0, x1, y1, res, resampling=Resampling.average)[0]
    cop = mosaic("copdem30/*.tif", x0, y0, x1, y1, res, src_crs="EPSG:4326")[0]
    ok = ~np.isnan(swiss) & ~np.isnan(cop)
    off = np.nanmedian(swiss[ok] - cop[ok]) if ok.sum() > 100 else 0.0
    h = np.where(np.isnan(swiss), cop + off, swiss)
    return h


def ring_mesh(mb, H, x0, y1, res, inner, outer, lake_level):
    ny, nx = H.shape
    xs = x0 + (np.arange(nx) + 0.5) * res
    ys = y1 - (np.arange(ny) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    r = np.maximum(np.abs(X), np.abs(Y))
    d = np.hypot(X, Y)
    Z = H - 0.87 * d ** 2 / (2 * R_EARTH)
    lake = (H < lake_level + 1.5)
    Z = np.where(lake, lake_level - 3.0, Z)
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
    used = np.unique(T)
    remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
    mb.add("mp_backdrop", V[used], uvs=V[used, :2] / 100.0, tris=remap[T], colors=col[used])


def build(level_dir, level_name, scene, lake_level):
    mb = bng.MeshBuilder()
    inner = TER_HALF - 30.0
    H1 = grid_heights(-8000, -8000, 8000, 8000, 40.0)
    ring_mesh(mb, H1, -8000, 8000, 40.0, inner, 8000, lake_level)
    H2 = grid_heights(-RMAX, -RMAX, RMAX, RMAX, 100.0)
    ring_mesh(mb, H2, -RMAX, RMAX, 100.0, 7950, RMAX, lake_level)
    rel = "art/shapes/backdrop/backdrop.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="backdrop", origin=(0, 0, 0))
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "backdrop", "main.materials.json"), [
        bng.material("mp_backdrop", "/assets/materials/terrain/forest/t_macro_forest/t_macro_forest_b.png",
                     roughness=0.95, vert_color=True)])
    scene.add("MissionGroup/level_objects/backdrop", bng.tsstatic(f"/levels/{level_name}/{rel}", (0, 0, 0),
                                                                  collision=False, decal=False))
    print("backdrop triangles", mb.triangle_count())
