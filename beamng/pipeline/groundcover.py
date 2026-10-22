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
import json, os, re, sys, zipfile

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


# v2.8 (understory.understory_step): the undergrowth of the woods, the game's own models on the forest floor layers,
# only around the camera: a GroundCover places them as it goes, without collision, nothing stored per plant, culled
# beyond its radius. Up to v3.0.40 it was one GroundCover of low bushes (600 within 60 m, about one per 30 m2 of
# wood) on a bare floor.
# v3.1: the layers of a wild wood of the Malcantone, where the chestnut coppice (the old selve) climbs to about
# 900-1000 m and the beech wood takes over above:
# - the field layer (to about 1.3 m): bracken and ferns, thin in the shade, a carpet in the light (ECA's lush_ferns);
#   fewer in the beech wood;
# - the shrub layer (1-4 m): hazel clumps, holly (the evergreen holm oak bush of Italy), young beech, oak and birch,
#   and brambles (Italy's scraggly and small generic bush, kept low); sparse under the crowns, thick where light
#   reaches the ground;
# - dead wood and stones: fallen beech trunks and logs, heaps of dead branches, the stumps of the coppice, gneiss
#   boulders half in the ground.
# The light: the edge of the wood (the mantle along meadows, roads, yards) and the gaps between the crowns are the
# twins FOREST_LIGHT of the forest floor layers (understory.understory_step); the shade is the plain layers.
# Every model is a vanilla one that ships its imposters (no bake in the session: the white squares of 0.40).
FOREST_LAYERS = ("ForestFloor", "ForestFloor2")
FOREST_LIGHT = {m: m + "Light" for m in FOREST_LAYERS}
SHADE, LIGHT = FOREST_LAYERS, tuple(FOREST_LIGHT.values())
CHESTNUT_TOP = 950.0        # m a.s.l. (the level's z): the chestnut belt below, the beech wood above
_EG = "/levels/east_coast_usa/art/shapes/groundcover/"
_EB = "/levels/east_coast_usa/art/shapes/trees/trees_beech/"
_EO = "/levels/east_coast_usa/art/shapes/trees/trees_oak/"
_EA = "/levels/east_coast_usa/art/shapes/trees/trees_aspen/"
_EF = "/levels/east_coast_usa/art/shapes/trees/trees_douglasfir/"
_ER = "/levels/east_coast_usa/art/shapes/rocks/"
_IT = "/levels/italy/art/shapes/trees/trees_italy/"
_LO, _HI = (-1000.0, CHESTNUT_TOP), (CHESTNUT_TOP, 5000.0)
_ALL = (-1000.0, 5000.0)
# (layers, model, probability, scale min, max, clump min, max, clump radius, max slope, elevation range)
# Sizes at scale 1 (dati/asset_bounds.json): ferns 0.9-1.3 m; beech_bush_a 1.0 m, _b 3.2 m, _d 6.3 m (a many-stemmed
# clump: hazel at 0.4-0.6); oak_bush_a 1.25 m, _c 3.0 m; aspen_bush_a/_b 2.0-2.3 m; holm_oak_bush 5.2 m;
# scraggly_bush 2.9 m and 5 m wide (brambles at 0.35-0.5); generibush_small 1.4 m; fluffy_bush 2.4 m;
# beech_dead_a a trunk 5.4 m long, _b a fallen beech 10 m long, fir_dead_branches a heap 0.9 m high and 4.7 m wide,
# douglasfir_chopped a stump 0.55 m; eca_rock_small_2/_3 0.4-0.7 m stones, half in the ground.
# In the light (the edge, along the roads) nothing reaches more than about 1.5 m from its foot; the big clumps and
# the fallen trees only in the shade, which begins EDGE_M (understory.py) from the edge.
UNDERSTORY_FERNS = ("understory_ferns", 45.0, 30.0, 8, 2200, 22, [
    (SHADE, _EG + "lush_ferns_01_a.dae", 0.55, 0.9, 1.4, 2, 4, 1.5, 35, _LO),
    (SHADE, _EG + "lush_ferns_01_b.dae", 0.35, 0.7, 1.0, 1, 3, 1.5, 35, _LO),
    (SHADE, _EG + "lush_ferns_02_a.dae", 0.12, 0.7, 1.1, 1, 3, 1.0, 40, _ALL),
    (SHADE, _EG + "lush_ferns_02_b.dae", 0.20, 0.7, 1.0, 1, 3, 1.0, 40, _HI),
    (LIGHT, _EG + "lush_ferns_01_a.dae", 1.00, 0.9, 1.4, 3, 6, 2.0, 40, _ALL),
    (LIGHT, _EG + "lush_ferns_01_b.dae", 0.70, 0.7, 1.0, 2, 4, 2.0, 40, _ALL),
    (LIGHT, _EG + "lush_ferns_02_a.dae", 0.40, 0.7, 1.1, 2, 4, 1.5, 40, _ALL),
    (LIGHT, _EG + "lush_ferns_02_b.dae", 0.30, 0.7, 1.0, 1, 3, 1.5, 40, _ALL),
])
UNDERSTORY = ("understory", 60.0, 40.0, 8, 2600, 21, [
    (SHADE, _EB + "tree_beech_bush_d.dae", 0.30, 0.40, 0.60, 1, 1, 1.0, 35, _ALL),     # hazel clumps
    (SHADE, _IT + "holm_oak_bush.dae", 0.22, 0.35, 0.55, 1, 1, 1.0, 35, _LO),          # holly
    (SHADE, _EB + "tree_beech_bush_a.dae", 0.30, 0.9, 1.6, 1, 3, 2.0, 40, _ALL),       # young beech
    (SHADE, _EB + "tree_beech_bush_b.dae", 0.18, 0.5, 0.9, 1, 2, 2.0, 40, _HI),
    (SHADE, _EO + "tree_oak_bush_a.dae", 0.20, 0.9, 1.5, 1, 2, 2.0, 40, _LO),
    (SHADE, _IT + "fluffy_bush.dae", 0.12, 0.30, 0.50, 1, 1, 1.0, 35, _LO),
    (SHADE, _IT + "scraggly_bush.dae", 0.08, 0.35, 0.45, 1, 1, 1.0, 35, _LO),          # brambles
    (LIGHT, _IT + "scraggly_bush.dae", 0.90, 0.35, 0.50, 1, 2, 2.5, 40, (-1000.0, 1100.0)),
    (LIGHT, _IT + "generibush_small.dae", 0.60, 0.50, 0.85, 1, 2, 2.0, 40, _ALL),
    (LIGHT, _EB + "tree_beech_bush_d.dae", 0.30, 0.35, 0.42, 1, 1, 1.0, 35, _ALL),     # hazel, kept narrow
    (LIGHT, _EB + "tree_beech_bush_a.dae", 0.40, 0.9, 1.6, 1, 3, 2.0, 40, _ALL),
    (LIGHT, _EB + "tree_beech_bush_c.dae", 0.25, 0.40, 0.55, 1, 1, 1.0, 40, _ALL),
    (LIGHT, _EO + "tree_oak_bush_a.dae", 0.30, 0.9, 1.5, 1, 2, 2.0, 40, _ALL),
    (LIGHT, _EO + "tree_oak_bush_c.dae", 0.20, 0.5, 0.7, 1, 1, 1.0, 40, _LO),
    (LIGHT, _EA + "tree_aspen_bush_a.dae", 0.25, 0.6, 1.1, 1, 2, 2.0, 40, _ALL),      # birch
    (LIGHT, _EA + "tree_aspen_bush_b.dae", 0.20, 0.6, 1.0, 1, 2, 2.0, 40, _ALL),
    (LIGHT, _IT + "fluffy_bush.dae", 0.20, 0.30, 0.50, 1, 1, 1.0, 35, _ALL),
])
UNDERSTORY_DEADWOOD = ("understory_deadwood", 80.0, 55.0, 6, 400, 23, [
    (SHADE, _EB + "tree_beech_dead_b.dae", 0.10, 0.75, 1.0, 1, 1, 1.0, 9, _ALL),       # a fallen beech, 10 m
    (SHADE, _EB + "tree_beech_dead_a.dae", 0.25, 0.8, 1.2, 1, 1, 1.0, 14, _ALL),       # a trunk, 5 m
    (SHADE, _EF + "fir_dead_branches.dae", 0.25, 0.6, 1.0, 1, 1, 1.0, 22, _ALL),
    (SHADE, _EF + "tree_douglasfir_chopped.dae", 0.35, 1.0, 1.8, 1, 3, 2.5, 35, _LO),  # coppice stumps
    (SHADE, _ER + "eca_rock_small_2.dae", 0.30, 0.8, 2.2, 1, 3, 2.0, 50, _ALL),
    (SHADE, _ER + "eca_rock_small_3.dae", 0.30, 0.8, 2.2, 1, 2, 2.0, 50, _ALL),
    (LIGHT, _EF + "tree_douglasfir_chopped.dae", 0.20, 1.0, 1.6, 1, 2, 2.0, 35, _ALL),
    (LIGHT, _ER + "eca_rock_small_2.dae", 0.15, 0.8, 1.6, 1, 2, 2.0, 50, _ALL),
    (LIGHT, _ER + "eca_rock_small_3.dae", 0.15, 0.8, 1.6, 1, 2, 2.0, 50, _ALL),
])
UNDERSTORY_COVERS = (UNDERSTORY_FERNS, UNDERSTORY, UNDERSTORY_DEADWOOD)
UNDERSTORY_MATS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                               "understory_materials.json")


def _cover_types(rows):
    """GroundCover Types of rows (layers, model, p, scale min, max, clump min, max, clump radius, slope, (zmin, zmax))."""
    types = []
    for layers, shape, p, smin, smax, cmin, cmax, crad, slope, (zmin, zmax) in rows:
        for layer in layers:
            t = _t(layer, [0, 0, 1, 1], p, smin, smax, cmin, cmax, crad, 0.0)
            t.update(shapeFilename=shape, maxSlope=slope, minElevation=zmin, maxElevation=zmax)
            types.append(t)
    return types


def density(cover, layer, z=500.0, slope=0.0):
    """Plants per m2 the GroundCover `cover` puts on `layer` at height z and slope: it draws maxElements over the
    square of its radius, each a type picked by probability among all its types, then dropped where the type's
    layer, elevation or slope does not fit; a kept one is a clump of min-max plants (their mean)."""
    _, radius, _, _, max_el, _, rows = cover
    tot = sum(r[2] * len(r[0]) for r in rows)
    ok = sum(r[2] * (r[5] + r[6]) / 2 for r in rows if layer in r[0] and r[9][0] <= z < r[9][1] and slope <= r[8])
    return max_el / (2 * radius) ** 2 * ok / tot


def understory_objects():
    """The GroundCovers of the undergrowth (UNDERSTORY_COVERS on the forest floor layers and their light twins)."""
    out = []
    for name, radius, dissolve, grid, max_el, seed, rows in UNDERSTORY_COVERS:
        o = {"name": name, "class": "GroundCover", "persistentId": bng.pid(), "position": [0, 0, 0],
             "material": "mp_gc_grass_short", "radius": radius, "dissolveRadius": dissolve, "gridSize": grid,
             "zOffset": 0, "seed": seed, "maxElements": max_el, "maxBillboardTiltAngle": 40, "shapeCullRadius": radius,
             "shapesCastShadows": False, "Types": _cover_types(rows)}
        o.update(WIND)
        out.append(o)
    return out


def understory_shapes():
    return sorted({r[1] for c in UNDERSTORY_COVERS for r in c[6]})


def understory_materials(have=()):
    """The material definitions the undergrowth models need and the level does not define (`have`), from the game
    (dati/understory_materials.json, taken once from BeamNG.drive 0.40; forest_vegetation of the ferns is not in
    East Coast USA, it is the one of driver_training's ground cover)."""
    d = json.load(open(UNDERSTORY_MATS))
    need = {m for s in understory_shapes() for m in d["_shapes"][s]}
    missing = sorted(m for m in need if m not in d)
    if missing:
        raise SystemExit("understory: no material definition for %s" % missing)
    return {m: {k: v for k, v in d[m].items() if not k.startswith("_")} for m in sorted(need) if m not in have}


# v3.0 (understory.understory_step): life on the open meadows and lawns, which up to v3.0 were bare grass between
# the houses (the big lawns of Agno): now and then a shrub of the game's own models along the meadows, a few
# more on the gardens, placed around the camera like the undergrowth (nothing stored per shrub, no collision).
# (layer, model, probability, scale min, max)
MEADOW_SHAPES = [
    ("Grass", "/levels/italy/art/shapes/trees/trees_italy/generibush.dae", 0.5, 0.30, 0.60),
    ("Grass", "/levels/east_coast_usa/art/shapes/trees/trees_beech/tree_beech_bush_c.dae", 0.3, 0.25, 0.45),
    ("GardenGrass", "/levels/italy/art/shapes/trees/trees_italy/fluffy_bush.dae", 1.0, 0.30, 0.55),
    ("GardenGrass", "/levels/italy/art/shapes/trees/trees_italy/generibush.dae", 0.6, 0.25, 0.45),
    ("GardenGrass", "/levels/east_coast_usa/art/shapes/trees/trees_oak/tree_oak_bush_b.dae", 0.3, 0.22, 0.35),
]
MEADOW = ("meadow_life", 80.0, 55.0, 8, 260, 33)


def meadow_object():
    """The GroundCover of the shrubs on the meadows and lawns (MEADOW_SHAPES)."""
    name, radius, dissolve, grid, max_el, seed = MEADOW
    types = []
    for layer, shape, p, smin, smax in MEADOW_SHAPES:
        t = _t(layer, [0, 0, 1, 1], p, smin, smax, 1, 1, 1.0, 0.0)
        t.update(shapeFilename=shape, maxSlope=35)
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


# --------------------------------------------------------------------------------------------------
# Put the grass of groundcover.py into the built level (v2.6), a finishing step of build_level.py.
#
# The GroundCover objects of the vegetation group are replaced with groundcover.objects(), the
# materials of art/shapes/groundcover with groundcover.materials(); the textures drawn by the
# v2.4-v2.5 pipeline (gc_atlas_*) are left out, and the level's README.md is the pipeline's
# README_livello.md. Everything else is copied as it is (same entries,
# same dates: the game keeps its converted shapes).
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish grass
# --------------------------------------------------------------------------------------------------

LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")


def grass_step(root):
    """The grass of groundcover.py in the built level (root: the folder that holds levels/<name>/)."""
    zi = bng.LevelFiles(root)
    with zi.writer() as zo:
        for i in zi.infolist():
            n = i.filename
            if "/art/shapes/groundcover/gc_atlas" in n:
                continue
            data = zi.read(i)
            if re.fullmatch(r"levels/[^/]+/README\.md", n):
                data = open(LEVEL_README, "rb").read()
            elif n.endswith("/art/shapes/groundcover/main.materials.json"):
                data = json.dumps({m["name"]: m for m in materials()}, indent=1).encode("utf-8")
            elif n.endswith("level_objects/vegetation/items.level.json"):
                objs = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
                parent = next((o["__parent"] for o in objs if o.get("class") == "GroundCover"), "vegetation")
                objs = [o for o in objs if o.get("class") != "GroundCover"]
                for o in objects():
                    o["__parent"] = parent
                    objs.append(o)
                data = ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
            zo.writestr(i, data, compress_type=i.compress_type)
    print("groundcover: GroundCover objects and materials written")
