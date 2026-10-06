"""Grass and meadow flowers on the terrain: BeamNG GroundCover objects around the camera, on the terrain
layers of the meadows and the gardens (terrain.py).

v2.6: the game's own grass and flower textures (/assets/materials/foliage, with colour, opacity,
normal, roughness and ambient occlusion maps and subsurface light), laid out like the game's Italy
level: short grass close to the camera (50 m), short and longer grass up to 120 m, meadow flowers
(daisies, buttercups, geraniums, poppies) up to 50 m. Up to v2.5 the clumps were cut from one atlas
drawn with numpy, a flat wall of identical blades without normal or ambient occlusion maps, drawn
only up to 50 m.

The materials reference the textures where the game keeps them (nothing is copied into the level),
under names of this level so they don't depend on another level being installed. The billboard
rectangles of the textures and the sizes are those of the Italy level; the densities are lower on the
gardens (mown lawns) and there are no flowers in the gardens. No grass within a terrain square of the
roads and paths (terrain.NO_COVER: the verges keep the look of the meadow without the clumps, which
would stand through the road meshes).
"""
import os
import bng

F = "/assets/materials/foliage"
# material -> (colour, the other maps' texture set, alphaRef)
MATERIALS = {
    "mp_gc_grass_short": (f"{F}/grass/t_grass_green_short_02/t_grass_green_short_02",
                          f"{F}/grass/t_grass_green_short_01/t_grass_green_short_01", 60),
    "mp_gc_grass_long": (f"{F}/grass/t_grass_green_long_03/t_grass_green_long_03",
                         f"{F}/grass/t_grass_green_long_01/t_grass_green_long_01", 25),
    "mp_gc_flowers": (f"{F}/groundcover/t_flowers_01/t_flowers_01", f"{F}/groundcover/t_flowers_01/t_flowers_01", 5),
}
SHORT_TOP, SHORT_BOTTOM = [0, 0.0078125, 1, 0.464844], [0, 0.505125, 1, 0.472656]
SHORT_HALF_L, SHORT_HALF_R = [0, 0.515625, 0.5, 0.476563], [0.496094, 0.515625, 0.503906, 0.484375]
LONG_TOP, LONG_BOTTOM, LONG_HALF = [0, 0, 1, 0.491806], [0, 0.511718, 1, 0.488282], [0.5, 0.519531, 0.5, 0.480469]
FLOWERS = [[0.391768, 0.386836, 0.150037, 0.226648], [0.542877, 0.323836, 0.092376, 0.288212],
           [0.906522, 0.262987, 0.093478, 0.351979], [0.635661, 0.330551, 0.272889, 0.279477],
           [0.219938, 0.352744, 0.167908, 0.258597], [0, 0.229238, 0.390785, 0.37884],
           [0.742843, 0.624264, 0.257157, 0.371297], [0, 0, 0.431691, 0.215004]]
FLOWER_P = [0.5, 0.5, 0.25, 0.25, 0.4, 0.03, 0.03, 0.05]   # half of the Italy shares: a hay meadow in autumn
WIND = {"windGustFrequency": 0.1, "windGustLength": 0.5, "windGustStrength": 0.2,
        "windTurbulenceFrequency": 0.6, "windTurbulenceStrength": 0.1}


def _t(layer, uvs, p, smin, smax, cmin, cmax, crad, wind=0.1):
    return {"layer": layer, "invertLayer": False, "probability": p, "shapeFilename": "", "billboardUVs": uvs,
            "sizeMin": smin, "sizeMax": smax, "sizeExponent": 1, "windScale": wind, "maxSlope": 45,
            "minElevation": -1000, "maxElevation": 5000, "minClumpCount": cmin, "maxClumpCount": cmax,
            "clumpExponent": 1, "clumpRadius": crad}


# name: (material, radius, dissolve radius, grid size, max elements, seed, types)
COVERS = {
    "grass_close": ("mp_gc_grass_short", 50.0, 30.0, 8, 160000, 4, [
        _t("Grass", SHORT_TOP, 0.7, 0.15, 0.30, 1, 6, 1.0),
        _t("Grass", SHORT_BOTTOM, 0.4, 0.15, 0.30, 2, 4, 0.3),
        _t("Grass", SHORT_HALF_L, 0.5, 0.25, 0.40, 3, 4, 0.3, 0.2),
        _t("Grass", SHORT_HALF_R, 0.5, 0.25, 0.40, 3, 6, 0.5, 0.2),
        _t("GardenGrass", SHORT_TOP, 0.8, 0.10, 0.18, 2, 6, 0.6),
        _t("GardenGrass", SHORT_BOTTOM, 0.5, 0.10, 0.18, 2, 4, 0.4),
        _t("GardenGrass", SHORT_HALF_R, 0.3, 0.14, 0.22, 2, 4, 0.3),
    ]),
    "grass_mid": ("mp_gc_grass_short", 120.0, 80.0, 6, 150000, 5, [
        _t("Grass", SHORT_TOP, 0.8, 0.20, 0.35, 2, 6, 1.0),
        _t("Grass", SHORT_HALF_R, 0.4, 0.25, 0.40, 3, 6, 0.6, 0.2),
        _t("GardenGrass", SHORT_TOP, 0.5, 0.10, 0.18, 2, 4, 0.6),
    ]),
    "grass_far": ("mp_gc_grass_long", 120.0, 80.0, 8, 150000, 9, [
        _t("Grass", LONG_TOP, 1.0, 0.35, 0.60, 2, 3, 2.0),
        _t("Grass", LONG_BOTTOM, 0.5, 0.35, 0.60, 2, 3, 2.0),
        _t("Grass", LONG_HALF, 0.3, 0.50, 0.80, 2, 3, 2.0),
    ]),
    "flowers": ("mp_gc_flowers", 50.0, 30.0, 3, 30000, 10,
                [_t("Grass", uv, p, 0.15, 0.25, 2, 4, 0.25, 0.2) for uv, p in zip(FLOWERS, FLOWER_P)]),
}


# v2.8 (patch_understory.py): the undergrowth of the woods, low shrubs of the game's own models (the bushes the
# level already uses, verified in the game) on the forest floor layers, only around the camera: a GroundCover
# places them as it goes, without collision, nothing stored per shrub, culled beyond the radius.
# (model, probability, scale min, max): about 0.6-1.5 m tall
UNDERSTORY_SHAPES = [
    ("/levels/italy/art/shapes/trees/trees_italy/generibush.dae", 1.0, 0.30, 0.55),
    ("/levels/italy/art/shapes/trees/trees_italy/fluffy_bush.dae", 0.7, 0.30, 0.50),
    ("/levels/east_coast_usa/art/shapes/trees/trees_beech/tree_beech_bush_c.dae", 0.4, 0.25, 0.40),
    ("/levels/east_coast_usa/art/shapes/trees/trees_oak/tree_oak_bush_b.dae", 0.3, 0.22, 0.35),
]
FOREST_LAYERS = ("ForestFloor", "ForestFloor2")
# name, radius (m), dissolve radius, grid size, max elements, seed
UNDERSTORY = ("understory", 60.0, 40.0, 8, 600, 21)


def understory_object():
    """The GroundCover of the undergrowth (UNDERSTORY_SHAPES on FOREST_LAYERS)."""
    name, radius, dissolve, grid, max_el, seed = UNDERSTORY
    types = []
    for layer in FOREST_LAYERS:
        for shape, p, smin, smax in UNDERSTORY_SHAPES:
            t = _t(layer, [0, 0, 1, 1], p, smin, smax, 1, 2, 1.0, 0.0)
            t.update(shapeFilename=shape, maxSlope=40)
            types.append(t)
    o = {"name": name, "class": "GroundCover", "persistentId": bng.pid(), "position": [0, 0, 0],
         "material": "mp_gc_grass_short", "radius": radius, "dissolveRadius": dissolve, "gridSize": grid, "zOffset": 0,
         "seed": seed, "maxElements": max_el, "maxBillboardTiltAngle": 40, "shapeCullRadius": radius,
         "shapesCastShadows": False, "Types": types}
    o.update(WIND)
    return o


def materials():
    out = []
    for name, (color, maps, alpha_ref) in MATERIALS.items():
        out.append({"name": name, "mapTo": name, "class": "Material", "version": 1.5,
                    "Stages": [{"baseColorMap": f"{color}_b.color.png", "opacityMap": f"{maps}_o.data.png",
                                "normalMap": f"{maps}_nm.normal.png", "roughnessMap": f"{maps}_r.data.png",
                                "ambientOcclusionMap": f"{maps}_ao.data.png"}, {}, {}, {}],
                    "alphaTest": True, "alphaRef": alpha_ref, "doubleSided": True, "dynamicCubemap": True,
                    "subSurface": True, "subSurfaceIntensity": 1, "invertBackFaceNormals": name == "mp_gc_flowers"})
    return out


def objects():
    objs = []
    for name, (mat, radius, dissolve, grid, max_el, seed, types) in COVERS.items():
        o = {"name": name, "class": "GroundCover", "persistentId": bng.pid(), "position": [0, 0, 0],
             "material": mat, "radius": radius, "dissolveRadius": dissolve, "gridSize": grid, "zOffset": 0,
             "seed": seed, "maxElements": max_el, "maxBillboardTiltAngle": 40, "shapeCullRadius": radius * 0.9,
             "shapesCastShadows": False, "Types": types}
        o.update(WIND)
        objs.append(o)
    return objs


def build(level_dir, level_name, scene, group="MissionGroup/level_objects/vegetation"):
    """Materials and the GroundCover objects; returns the counts for the log."""
    import json
    d = os.path.join(level_dir, "art", "shapes", "groundcover")
    os.makedirs(d, exist_ok=True)
    json.dump({m["name"]: m for m in materials()}, open(os.path.join(d, "main.materials.json"), "w"), indent=1)
    for o in objects():
        scene.add(group, o)
    return {"covers": len(COVERS), "max_elements": sum(c[4] for c in COVERS.values()),
            "radius_m": max(c[1] for c in COVERS.values()), "triangles_per_clump": 2}
