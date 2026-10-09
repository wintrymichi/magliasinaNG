"""BeamNG terrain: TER_SIZE x TER_SIZE vertices TER_SQUARE m apart (config: 8192 at 1.5 m, a
12.3 km square around the playable area). Heights: swissALTI3D 0.5 m (dtm05) over the playable area,
swissALTI3D 2 m (dtm2) around it, blended; Copernicus where neither exists (Italy). Material layers
from the cadastral land cover (MU) with slope-based rock; outside the survey a rough class from the
orthophoto colour. Optional carving (road surfaces etc.) as a height override raster.
The block is processed in row bands (67 M vertices).

build_terrain(level_dir, override=None) writes <level>/theTerrain.ter + .terrain.json
and art/terrains/main.materials.json; returns (z0, max_height).
"""
import json, os
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates, zoom
from config import WORK, TER_SIZE, TER_SQUARE, TER_X0, TER_Y0, LEVEL_NAME
from geo import Grid, ortho_sampler
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
# v2.4: the meadows and lawns within a terrain square of the roads and paths: the same look, another
# layer, so the grass of groundcover.py (on Grass and GardenGrass) does not stand through the road meshes
VERGE = {"Grass": "GrassVerge", "GardenGrass": "GardenGrassVerge"}
for _m, _v in VERGE.items():
    TERRAIN_MATS[_v] = TERRAIN_MATS[_m]
VERGE_OF = {v: m for m, v in VERGE.items()}
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
    "pascolo_boscato_fitto": "ForestFloor2", "pascolo_boscato_aperto": "Grass", "roccia": "Rock",
    "ghiacciaio_nevaio": "Rock", "binario": "Gravel", "pista_aerea": "Asphalt", "altro": "Grass",
}


# v2.8: mean sRGB of the game's terrain detail colour maps (measured in the game's terrain.zip on michi's PC,
# 2026-10-09): near-neutral grey, the detail modulates the base colour. The backfill behind the walls uses the
# detail map as its colour map with the base colour divided by this mean (walls.fill_material).
DETAIL_MEAN = {"t_grass_01": 0.486, "t_dirt_vegetation": 0.512, "t_forest_ground": 0.555,
               "t_forest_ground_02": 0.460, "t_asphalt_02": 0.498, "t_concrete_damaged": 0.498,
               "t_gravel": 0.514, "t_dirt_rocky": 0.475, "t_mud": 0.498, "t_moss": 0.498}

# pixel size of the base textures (the TerrainMaterialTextureSet baseTexSize). 1024 since v2.5:
# 13 materials x 5 maps at 2048 took about 1 GB of the game's memory, for smooth colour noise
# that is only seen from afar (the detail textures cover it near the camera)
BASE_TEX = 1024


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
                          "baseTexSize": [BASE_TEX, BASE_TEX], "detailTexSize": [1024, 1024], "macroTexSize": [1024, 1024]}
    return mats


def vertex_coords():
    xs = TER_X0 + np.arange(TER_SIZE) * TER_SQUARE
    ys = TER_Y0 + np.arange(TER_SIZE) * TER_SQUARE
    return xs, ys                 # x of columns, y of rows (row 0 = south)


BAND = 256                        # terrain rows per band
BLEND = 40.0                      # m, fine DTM -> coarse DTM transition at the edge of the fine grid


def fine_weight(dtm):
    """Weight of dtm05 against dtm2 on a 5 m grid: 1 on swissALTI3D 0.5 m data, 0 on cells filled
    from Copernicus and at the grid edge, smooth in between."""
    nod = np.load(os.path.join(WORK, "dtm05_nodata.npy"), mmap_mode="r")
    h, w = nod.shape
    f = 10                                               # 0.5 m cells per 5 m cell
    hc, wc = h // f, w // f
    valid = np.zeros((hc, wc), np.float32)
    for r0 in range(0, hc, 256):
        blk = np.asarray(nod[r0 * f:min(r0 + 256, hc) * f, :wc * f])
        valid[r0:r0 + blk.shape[0] // f] = 1.0 - blk.reshape(-1, f, wc, f).mean((1, 3))
    valid[:2], valid[-2:], valid[:, :2], valid[:, -2:] = 0, 0, 0, 0
    wgt = np.clip((gaussian_filter(valid, BLEND / 5.0 / 2.0) - 0.5) * 2.0, 0.0, 1.0)
    return Grid(wgt.astype(np.float32), dtm.x_min, dtm.y_max, dtm.res * f)


def heights_band(xs, ys, dtm, dtm2, wgrid):
    """Terrain heights (len(ys), len(xs)) for one band of rows."""
    X, Y = np.meshgrid(xs, ys)
    H = dtm2.sample(X.ravel(), Y.ravel()).reshape(X.shape).astype(np.float64)
    w = wgrid.sample(X.ravel(), Y.ravel()).reshape(X.shape)
    # outside the 0.5 m raster the samplers repeat its edge: no weight there
    bx0, by0, bx1, by1 = dtm.bounds()
    w[(X < bx0 + 1) | (X > bx1 - 1) | (Y < by0 + 1) | (Y > by1 - 1)] = 0.0
    m = w > 0
    if m.any():
        x0, x1 = X[m].min(), X[m].max()
        y0, y1 = Y[m].min(), Y[m].max()
        sub, _, _ = dtm.window(x0, y0, x1, y1, pad=6)
        sub.a = gaussian_filter(sub.a.astype(np.float32), 0.4 * TER_SQUARE / dtm.res)   # anti-alias
        H[m] = w[m] * sub.sample(X[m], Y[m]) + (1 - w[m]) * H[m]
    return H


def build_terrain(level_dir, override=None, override_mask=None, layer_override=None, post_fn=None, cap=None,
                  no_cover=None):
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dtm2 = Grid.load(os.path.join(WORK, "dtm2.npz"))
    wgrid = fine_weight(dtm)
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    lcg = Grid(lc["a"], float(lc["x_min"]), float(lc["y_max"]), float(lc["res"]))
    ortho = ortho_sampler()
    xs, ys = vertex_coords()
    from landcover import CLASSES
    lut = np.array([MAT_ID[LC_TO_MAT[cname]] for cname in CLASSES], np.uint8)
    H = np.zeros((TER_SIZE, TER_SIZE), np.float64)
    layers = np.zeros((TER_SIZE, TER_SIZE), np.uint8)
    for r0 in range(0, TER_SIZE, BAND):
        r1 = min(r0 + BAND, TER_SIZE)
        H[r0:r1] = heights_band(xs, ys[r0:r1], dtm, dtm2, wgrid)
    if override is not None:
        H = np.where(override_mask, override, H)
    if cap is not None:                                  # under bridge decks: no higher than the slab
        H = np.minimum(H, cap)
    if post_fn is not None:
        H = post_fn(H, xs, ys)
        if override is not None:                         # walls may lower it, nothing may raise it over a road
            H = np.where(override_mask, np.minimum(H, override), H)
        if cap is not None:
            H = np.minimum(H, cap)
    gy, gx = np.gradient(H, TER_SQUARE)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    del gx, gy
    grassy = [MAT_ID["Grass"], MAT_ID["ForestFloor"], MAT_ID["ForestFloor2"], MAT_ID["GardenGrass"]]
    for r0 in range(0, TER_SIZE, BAND):
        r1 = min(r0 + BAND, TER_SIZE)
        X, Y = np.meshgrid(xs, ys[r0:r1])
        L = lcg.sample(X.ravel(), Y.ravel(), order=0).astype(np.int64).reshape(X.shape)
        lx0, ly0, lx1, ly1 = lcg.bounds()
        L[(X < lx0) | (X >= lx1) | (Y <= ly0) | (Y > ly1)] = 0          # outside the survey raster
        lay = lut[L]
        rgb = ortho(X.ravel(), Y.ravel()).reshape(X.shape + (3,))
        R_, G_, B_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        green = (G_ > R_ + 4) & (G_ > B_ + 4)
        # outside the survey (L == 0): a rough class from the orthophoto colour
        out = L == 0
        dark = np.nan_to_num((R_ + G_ + B_) / 3.0, nan=100.0) < 85
        lay[out & green & dark] = MAT_ID["ForestFloor"]
        lay[out & green & ~dark] = MAT_ID["Grass"]
        lay[out & ~green & (slope[r0:r1] > 35)] = MAT_ID["Rock"]
        # steep bare slopes -> rock, but only where the orthophoto is not green (vegetated / ivy slopes
        # along the road stay vegetated, as in the photos)
        lay[(slope[r0:r1] > 50) & ~green & np.isin(lay, grassy)] = MAT_ID["Rock"]
        layers[r0:r1] = lay
    del slope
    if layer_override is not None:
        m = layer_override >= 0
        layers[m] = layer_override[m]
    if no_cover is not None:                             # v2.4: the verges of the roads (VERGE)
        for a, b in VERGE.items():
            layers[no_cover & (layers == MAT_ID[a])] = MAT_ID[b]
    z0 = float(np.floor(H.min() - 2.0))
    max_h = float(np.ceil(H.max() - z0 + 2.0))
    bng.write_ter(os.path.join(level_dir, "theTerrain.ter"), H, z0, max_h, layers, MAT_ORDER)
    bng.write_terrain_json(os.path.join(level_dir, "theTerrain.terrain.json"), LEVEL_NAME, "theTerrain",
                           TER_SIZE, MAT_ORDER)
    np.save(os.path.join(WORK, "terrain_heights.npy"), H.astype(np.float32))
    np.save(os.path.join(WORK, "terrain_layers.npy"), layers)
    return z0, max_h, H
