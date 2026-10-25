"""v3.1 visual review: no bare 'Concrete' terrain where nothing stands on it (finish step).

The terrain layer Concrete is the cadastral class 'edificio' (buildings) and 'bacino_idrico' (pools, fountain basins,
reservoirs): under a house it is never seen. Where the survey draws a building the level has no mesh for (a house
built into the slope whose back is a garden, a building gone since the survey, an underground garage under a yard)
and on every basin it was the ground the player saw: a flat pale grey-blue sheet with sharp edges, its base colour
measured on the water of the pools (terrain_colors.py, 151,165,165), on yards, on slopes above walls, inside the
stone walls of a basin (visual review G5: 0205, 0207, 0410, 0473, 0485, 0493).

Here every Concrete vertex that no solid mesh (SOLID: buildings, roads, walls, railway...) touches takes the layer
of the nearest vertex that is not Concrete: the yard, the garden, the meadow around it. Concrete is kept under and
one terrain square around the meshes (the foot of a wall). Heights are not changed.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish bare_concrete
"""
import json, os, time, zipfile
import numpy as np
from scipy import ndimage as ndi
import bng
import understory
import walls as pw
from config import LEVEL_NAME

CONCRETE = "Concrete"
# what stands on the ground: Concrete under or beside a face of these stays
SOLID = ("buildings", "buildings/veri", "buildings/details", "buildings/extras", "landmarks", "props/fuel",
         "roads/surfaces", "roads/sidewalks", "roads/roundabouts", "roads/islands", "walls", "railway")


def relabel(lay, names, covered):
    """(new layers (n, n) uint8, statistics): the Concrete vertices not in `covered` (n, n) bool with the layer of
    the nearest vertex that is not Concrete."""
    ci = names.index(CONCRETE)
    conc = lay == ci
    bare = conc & ~covered
    out = np.array(lay)
    if bare.any():
        # nearest non-Concrete vertex, in windows round the bare patches (a whole-block transform needs 1 GB)
        lab, k = ndi.label(bare, np.ones((3, 3), bool))
        for sl in ndi.find_objects(lab):
            r0, r1 = max(sl[0].start - 64, 0), min(sl[0].stop + 64, lay.shape[0])
            c0, c1 = max(sl[1].start - 64, 0), min(sl[1].stop + 64, lay.shape[1])
            w = conc[r0:r1, c0:c1]
            if w.all():
                continue
            _, (ir, ic) = ndi.distance_transform_edt(w, return_indices=True)
            b = bare[r0:r1, c0:c1]
            sub = out[r0:r1, c0:c1]
            sub[b] = lay[r0:r1, c0:c1][ir[b], ic[b]]
    stats = {"concrete_vertices": int(conc.sum()), "bare_vertices": int(bare.sum()),
             "bare_ha": round(float(bare.sum()) * 1.5 * 1.5 / 1e4, 1),
             "left_concrete": int((out == ci).sum())}
    return out, stats


def changes(zi, report=None):
    t0 = time.time()
    lv = f"levels/{LEVEL_NAME}"
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = pw.read_ter(data)
    if CONCRETE not in names:
        return {}, {"concrete_vertices": 0}
    cells = understory.face_cells(zi, lv, n, groups=SOLID)
    covered = ndi.binary_dilation(pw.corners_of(cells), np.ones((3, 3), bool))   # and one square round them
    del cells
    print("bare_concrete: solid meshes read (%.0f s)" % (time.time() - t0), flush=True)
    new_lay, stats = relabel(lay, names, covered)
    after = {m: int(c) for m, c in zip(names, np.bincount(new_lay[(lay != new_lay)].ravel(), minlength=len(names)))
             if c}
    stats["became"] = after
    tail = data[5 + 3 * n * n:]
    new_ter = data[:5 + 2 * n * n] + np.ascontiguousarray(new_lay).tobytes() + tail
    stats["seconds"] = round(time.time() - t0)
    print("bare_concrete:", json.dumps(stats), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(stats, open(report, "w"), indent=1)
    return {ter_name: new_ter}, stats


def bare_concrete_step(root, report=None):
    zi = bng.LevelFiles(root)
    new, _ = changes(zi, report)
    if not new:
        return 0
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new:
                ni = zipfile.ZipInfo(i.filename, now)                     # converted again by the game
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    return 0
