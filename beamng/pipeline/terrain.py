"""BeamNG terrain: 4096 x 4096 vertices at 1 m from swissALTI3D, material layers
from the cadastral land cover (MU) with slope-based rock, optional carving
(road surfaces etc.) supplied as a height override raster.

build_terrain(level_dir, override=None) writes <level>/theTerrain.ter + .terrain.json
and art/terrains/main.materials.json; returns (z0, max_height).
"""
import json, os
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, TER_SIZE, TER_SQUARE, TER_HALF, LEVEL_NAME
from geo import Grid
from landcover import CODE
import bng

A = "/assets/materials/terrain"
# name: (groundmodel, detail set dir/prefix, macro set, detail size m, macro size m)
TERRAIN_MATS = {
    "Grass":        ("GRASS",   f"{A}/grass/t_grass_01/t_grass_01",               f"{A}/grass/t_macro_grass/t_macro_grass", 4, 40),
    "GardenGrass":  ("GRASS",   f"{A}/grass/t_dirt_vegetation/t_dirt_vegetation", f"{A}/grass/macro_grass/t_macro_grass", 4, 40),
    "ForestFloor":  ("DIRT",    f"{A}/forest/t_forest_ground/t_forest_ground",    f"{A}/forest/t_macro_forest/t_macro_forest", 4, 50),
    "ForestFloor2": ("DIRT",    f"{A}/forest/t_forest_ground_02/t_forest_ground_02", f"{A}/forest/t_macro_dirt_forest/t_macro_dirt_forest", 4, 50),
    "Asphalt":      ("ASPHALT", f"{A}/asphalt/t_asphalt_02/t_asphalt_02",         f"{A}/asphalt/macro_asphalt/t_macro_asphalt", 3, 60),
    "Concrete":     ("ASPHALT", f"{A}/concrete/concrete/t_concrete_damaged",      f"{A}/asphalt/macro_asphalt/t_macro_asphalt", 3, 60),
    "Gravel":       ("GRAVEL",  f"{A}/soil/t_gravel/t_gravel",                    f"{A}/rock/macro_rocky/t_macro_rocky", 3, 50),
    "Rock":         ("ROCK",    f"{A}/rock/t_dirt_rocky/t_dirt_rocky",            f"{A}/rock/macro_rocky/t_macro_rocky", 5, 60),
    "Mud":          ("MUD",     f"{A}/mud/mud/t_mud",                             f"{A}/forest/t_macro_dirt_forest/t_macro_dirt_forest", 4, 50),
    "Moss":         ("GRASS",   f"{A}/forest/t_moss/t_moss",                      f"{A}/forest/t_macro_forest/t_macro_forest", 4, 50),
}
MAT_ORDER = list(TERRAIN_MATS)
MAT_ID = {m: i for i, m in enumerate(MAT_ORDER)}

LC_TO_MAT = {
    "none": "Grass", "edificio": "Concrete", "altro_rivestimento_duro": "Asphalt", "giardino": "GardenGrass",
    "campo_prato_pascolo": "Grass", "strada_sentiero": "Asphalt", "bacino_idrico": "Concrete",
    "bosco_fitto": "ForestFloor", "corso_acqua": "Gravel", "vigna": "GardenGrass", "marciapiede": "Asphalt",
    "altro_bosco": "ForestFloor2", "altro_humus": "GardenGrass", "spartitraffico": "GardenGrass",
    "pietraia_sabbia": "Gravel", "specchio_acqua": "Mud", "canneti": "Moss", "ferrovia": "Gravel",
    "altra_coltura_intensiva": "GardenGrass", "cava_di_ghiaia_discarica": "Gravel",
    "altra_senza_vegetazione": "Gravel", "torbiera": "Moss",
}


def terrain_materials(level, base_tex):
    """TerrainMaterial dicts. base_tex: {material: path of its base colour texture (level art)}."""
    mats = {}
    for name, (gm, det, mac, dsize, msize) in TERRAIN_MATS.items():
        base = base_tex[name]
        m = {
            "internalName": name, "class": "TerrainMaterial", "persistentId": bng.pid(),
            "groundmodelName": gm,
            "baseColorBaseTex": base["b"], "baseColorBaseTexSize": base["size"],
            "normalBaseTex": f"/levels/{level}/art/terrains/t_flat_nm.png", "normalBaseTexSize": base["size"],
            "roughnessBaseTex": f"/levels/{level}/art/terrains/t_rough_r.png", "roughnessBaseTexSize": base["size"],
            "aoBaseTex": f"/levels/{level}/art/terrains/t_white_ao.png", "aoBaseTexSize": base["size"],
            "heightBaseTex": f"/levels/{level}/art/terrains/t_grey_h.png", "heightBaseTexSize": base["size"],
            "baseColorDetailTex": f"{det}_b.png", "normalDetailTex": f"{det}_nm.png",
            "roughnessDetailTex": f"{det}_r.png", "aoDetailTex": f"{det}_ao.png", "heightDetailTex": f"{det}_h.png",
            "baseColorDetailTexSize": dsize, "normalDetailTexSize": dsize, "roughnessDetailTexSize": dsize,
            "aoDetailTexSize": dsize, "heightDetailTexSize": dsize,
            "baseColorDetailStrength": [0.45, 0.2], "normalDetailStrength": [0.8, 0.3],
            "roughnessDetailStrength": [0.5, 0.3], "aoDetailStrength": [0.7, 0.2],
            "baseColorMacroTex": f"{mac}_b.png", "normalMacroTex": f"{mac}_nm.png",
            "roughnessMacroTex": f"{mac}_r.png", "aoMacroTex": f"{mac}_ao.png", "heightMacroTex": f"{mac}_h.png",
            "baseColorMacroTexSize": msize, "normalMacroTexSize": msize, "roughnessMacroTexSize": msize,
            "aoMacroTexSize": msize, "heightMacroTexSize": msize,
            "baseColorMacroStrength": [0.15, 0.1], "normalMacroStrength": [0.3, 0.3],
            "roughnessMacroStrength": [0.3, 0.3], "aoMacroStrength": [0.3, 0.2],
            "detailDistances": [0, 0, 40, 80], "macroDistances": [0, 10, 150, 3000],
        }
        mats[f"{name}-{m['persistentId']}"] = m
    mats["TextureSet"] = {"name": f"{level}TerrainMaterialTextureSet", "class": "TerrainMaterialTextureSet",
                          "baseTexSize": [2048, 2048], "detailTexSize": [1024, 1024], "macroTexSize": [1024, 1024]}
    return mats


def vertex_coords():
    xs = -TER_HALF + np.arange(TER_SIZE) * TER_SQUARE
    return xs, xs.copy()          # x of columns, y of rows (row 0 = south)


def build_terrain(level_dir, override=None, override_mask=None, layer_override=None, post_fn=None):
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    a = gaussian_filter(dtm.a, 0.6)                      # anti-alias 0.5 m -> 1 m vertices
    xs, ys = vertex_coords()
    X, Y = np.meshgrid(xs, ys)                           # row 0 = south
    r, c = dtm.rc(X, Y)
    H = map_coordinates(a, [r, c], order=1, mode="nearest").astype(np.float64)
    if override is not None:
        H = np.where(override_mask, override, H)
    if post_fn is not None:
        H = post_fn(H, xs, ys)
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    lcg = Grid(lc["a"], float(lc["x_min"]), float(lc["y_max"]), float(lc["res"]))
    r2, c2 = lcg.rc(X, Y)
    L = map_coordinates(lcg.a, [r2, c2], order=0, mode="nearest")
    from landcover import CLASSES
    lut = np.array([MAT_ID[LC_TO_MAT[cname]] for cname in CLASSES], np.uint8)
    layers = lut[L]
    # steep bare slopes -> rock, but only where the orthophoto is not green (vegetated / ivy slopes
    # along the road stay vegetated, as in the photos)
    gy, gx = np.gradient(H, TER_SQUARE)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    import rasterio
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        o = s.read().astype(np.float32)
        otr = s.transform
    oc = ((X - otr.c) / otr.a).astype(int).clip(0, o.shape[2] - 1)
    orr = ((Y - otr.f) / otr.e).astype(int).clip(0, o.shape[1] - 1)
    R_, G_, B_ = o[0][orr, oc], o[1][orr, oc], o[2][orr, oc]
    green = (G_ > R_ + 4) & (G_ > B_ + 4)
    layers[(slope > 50) & ~green & np.isin(layers, [MAT_ID["Grass"], MAT_ID["ForestFloor"], MAT_ID["ForestFloor2"],
                                                    MAT_ID["GardenGrass"]])] = MAT_ID["Rock"]
    if layer_override is not None:
        m = layer_override >= 0
        layers[m] = layer_override[m]
    z0 = float(np.floor(H.min() - 2.0))
    max_h = float(np.ceil(H.max() - z0 + 2.0))
    bng.write_ter(os.path.join(level_dir, "theTerrain.ter"), H, z0, max_h, layers, MAT_ORDER)
    bng.write_terrain_json(os.path.join(level_dir, "theTerrain.terrain.json"), LEVEL_NAME, "theTerrain",
                           TER_SIZE, MAT_ORDER)
    np.save(os.path.join(WORK, "terrain_heights.npy"), H.astype(np.float32))
    np.save(os.path.join(WORK, "terrain_layers.npy"), layers)
    return z0, max_h, H
