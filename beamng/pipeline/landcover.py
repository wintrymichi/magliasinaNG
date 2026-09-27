"""Rasterise the cadastral land cover (MU / AV LCSF) and single objects onto the
0.5 m local grid shared with dtm05/dsm05.

work/landcover05.npz : uint8 class codes (see CLASSES), 0 = not covered by the survey
work/av_local.pkl    : AV polygons/lines in local coordinates, by class (shapely)
"""
import json, os, pickle
import numpy as np
import shapely
from shapely.geometry import shape
from rasterio import features
from rasterio.transform import Affine
from config import DATA, WORK, lv95_to_local
from geo import Grid

CLASSES = ["none", "edificio", "altro_rivestimento_duro", "giardino", "campo_prato_pascolo",
           "strada_sentiero", "bacino_idrico", "bosco_fitto", "corso_acqua", "vigna", "marciapiede",
           "altro_bosco", "altro_humus", "spartitraffico", "pietraia_sabbia", "specchio_acqua",
           "canneti", "ferrovia", "altra_coltura_intensiva", "cava_di_ghiaia_discarica",
           "altra_senza_vegetazione", "torbiera",
           # classes of the survey that only appear in the v2.0 area (appended: codes stay stable)
           "pascolo_boscato_fitto", "pascolo_boscato_aperto", "roccia", "ghiacciaio_nevaio",
           "binario", "pista_aerea", "altro"]
CODE = {c: i for i, c in enumerate(CLASSES)}


def code(cls):
    """Class code; unknown survey classes count as 'altro' (reported by main)."""
    return CODE.get(cls, CODE["altro"])


def to_local(geom):
    return shapely.transform(geom, lambda c: np.stack(lv95_to_local(c[:, 0], c[:, 1]), 1))


def load_av():
    out = {"LCSF": {}, "SOSF": {}, "SOLI": {}, "SOPT": {}}
    for layer in out:
        for f in json.load(open(os.path.join(DATA, "av", f"{layer}.geojson")))["features"]:
            g = to_local(shape(f["geometry"]))
            if not g.is_valid:
                g = shapely.make_valid(g)
            out[layer].setdefault(f["properties"]["Genere"], []).append((g, f["properties"]))
    return out


def main():
    av = load_av()
    pickle.dump(av, open(os.path.join(WORK, "av_local.pkl"), "wb"))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    h, w = dtm.a.shape
    tr = Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, dtm.y_max)
    shapes = []
    unknown = sorted({cls for cls in av["LCSF"] if cls not in CODE})
    if unknown:
        print("survey classes not in CLASSES (as 'altro'):", unknown)
    for cls, items in av["LCSF"].items():
        for g, p in items:
            shapes.append((g, code(cls)))
    lc = np.zeros((h, w), np.uint8)
    B = 2048                                             # row bands: the v2.0 grid is ~22 000 x 18 000
    for r0 in range(0, h, B):
        r1 = min(r0 + B, h)
        y_top = dtm.y_max - r0 * dtm.res
        box = shapely.box(dtm.x_min, dtm.y_max - r1 * dtm.res, dtm.x_min + w * dtm.res, y_top)
        sub = [(g, c) for g, c in shapes if g.intersects(box)]
        if sub:
            lc[r0:r1] = features.rasterize(sub, out_shape=(r1 - r0, w), fill=0, dtype=np.uint8, all_touched=False,
                                           transform=Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, y_top))
    np.savez_compressed(os.path.join(WORK, "landcover05.npz"), a=lc, x_min=dtm.x_min, y_max=dtm.y_max, res=dtm.res)
    u, c = np.unique(lc, return_counts=True)
    for k, n in zip(u, c):
        print(f"{CLASSES[k]:28s} {n * dtm.res ** 2 / 1e4:8.2f} ha")


if __name__ == "__main__":
    main()
