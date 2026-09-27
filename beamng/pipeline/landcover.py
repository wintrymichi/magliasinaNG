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
           "altra_senza_vegetazione", "torbiera"]
CODE = {c: i for i, c in enumerate(CLASSES)}


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
    for cls, items in av["LCSF"].items():
        for g, p in items:
            shapes.append((g, CODE[cls]))
    lc = features.rasterize(shapes, out_shape=(h, w), transform=tr, fill=0, dtype=np.uint8, all_touched=False)
    np.savez_compressed(os.path.join(WORK, "landcover05.npz"), a=lc, x_min=dtm.x_min, y_max=dtm.y_max, res=dtm.res)
    u, c = np.unique(lc, return_counts=True)
    for k, n in zip(u, c):
        print(f"{CLASSES[k]:28s} {n * dtm.res ** 2 / 1e4:8.2f} ha")


if __name__ == "__main__":
    main()
