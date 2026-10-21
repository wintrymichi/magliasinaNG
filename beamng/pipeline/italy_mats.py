"""Materials of the level on the textures of the game's Italy level (v3.0: "it must look vanilla").

Up to v3.0's test builds the asphalt, the walls and the wear of the roads were drawn by the pipeline
(surface_textures.py, bld_textures.py, road_wear.py): believable, but not the look of the game. Now they
use the textures of Italy (levels/italy/art, part of every installation of the game), with the detail and
overlay settings Italy gives them (dati/italy_materials.json, read from the installed game). A level may
point at another level's texture files, never at its materials: so every material here is the level's own,
with Italy's texture paths.
"""
import json
import os
import bng

HERE = os.path.dirname(os.path.abspath(__file__))
ITALY = json.load(open(os.path.join(HERE, "..", "dati", "italy_materials.json")))
ASPHALT_TILE = 4.0      # m of road per repeat of Italy's asphalt (its macro detail map repeats every 40 m)
STONE_TILE = 3.0        # m of wall per repeat of Italy's medieval stone wall
KEYS = {"d": "detailMap", "dn": "detailNormalMap", "o": "opacityMap"}
VALUES = ("detailScale", "detailNormalMapStrength", "opacityFactor", "roughnessFactor")
# the overlays of the road (road_wear.py) with the flags Italy gives the same textures: translucent WITH depth
# writes. Without them (the first v3.0) the game drew the overlays in a pass that takes no shadows: the cracked
# stretches, tracks and dusty edges stayed bright under the cars, trees and walls (checked in the game,
# 2026-10-18: the same patch with these flags takes the car's shadow, 103 against 203 of luma)
OVERLAY = {"translucent": True, "translucentZWrite": True, "castShadows": False}


def material(name, src, ground_type=None, tint=None, overlay=False, base_color=None):
    """Material `name` of the level on the textures of Italy's material `src`; tint multiplies Italy's
    colour factor (linear), base_color replaces it."""
    m = ITALY[src]
    stage = {KEYS[k]: m[k] for k in KEYS if k in m}
    stage.update({k: m[k] for k in VALUES if k in m})
    col = base_color if base_color is not None else m.get("baseColorFactor")
    if tint is not None:
        c = col or [1, 1, 1, 1]
        col = [c[0] * tint[0], c[1] * tint[1], c[2] * tint[2], c[3] * (tint[3] if len(tint) > 3 else 1)]
    return bng.material(name, m["b"], m.get("n"), m.get("r"), m.get("ao"), base_color=col,
                        ground_type=ground_type, detail=stage, extra=OVERLAY if overlay else None)
