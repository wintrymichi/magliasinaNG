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
CHANNEL_SHARE = 0.3     # v3.1: the share of a hard surface's outline along a stream for it to be its bank
CHANNEL_SLOPE = 0.15    # and the median slope of its ground (the yards and quays by the water are flat)
CHANNEL_GAP = 0.5       # m between the two outlines that still counts as along


def code(cls):
    """Class code; unknown survey classes count as 'altro' (reported by main)."""
    return CODE.get(cls, CODE["altro"])


def to_local(geom):
    return shapely.transform(geom, lambda c: np.stack(lv95_to_local(c[:, 0], c[:, 1]), 1))


def load_av(smooth=True):
    out = {"LCSF": {}, "SOSF": {}, "SOLI": {}, "SOPT": {}}
    for layer in out:
        for f in json.load(open(os.path.join(DATA, "av", f"{layer}.geojson")))["features"]:
            g = to_local(shape(f["geometry"]))
            if not g.is_valid:
                g = shapely.make_valid(g)
            out[layer].setdefault(f["properties"]["Genere"], []).append((g, f["properties"]))
    if smooth:
        smooth_curves(out)
    return out


def smooth_curves(av):
    """v3.0: the curves of the survey smoothed (smooth_geom.py): the land cover as one partition (the
    buildings kept as they are), the walls' footprints and axes on their own."""
    import smooth_geom
    items = [(cls, k) for cls, lst in av["LCSF"].items() for k in range(len(lst))]
    geoms = [av["LCSF"][c][k][0] for c, k in items]
    new = smooth_geom.smooth_partition(geoms, [c == "edificio" for c, _ in items])
    for (c, k), g in zip(items, new):
        av["LCSF"][c][k] = (g, av["LCSF"][c][k][1])
    av["SOSF"]["muro"] = [(smooth_geom.smooth_polygon(g), p) for g, p in av["SOSF"].get("muro", [])]
    av["SOLI"]["muro"] = [(smooth_geom.smooth_line(g), p) for g, p in av["SOLI"].get("muro", [])]
    print("survey curves smoothed: %d land cover polygons, %d + %d walls"
          % (len(geoms), len(av["SOSF"]["muro"]), len(av["SOLI"]["muro"])), flush=True)


def channel_linings(av, dtm):
    """v3.1: the 'altro_rivestimento_duro' of the survey that lines a stream (CHANNEL_SHARE of its outline along a
    'corso_acqua', its ground steeper than CHANNEL_SLOPE in the median: the stone banks of the Magliasina, an
    abutment's face) are stones and gravel ('pietraia_sabbia'), not a yard: up to v3.0.40 they were grey asphalt
    meshes sloping down into the river bed under the bridges and along it, without trees. The yards and quays by a
    river are flat. Returns how many."""
    hard = av["LCSF"].get("altro_rivestimento_duro", [])
    water = [g for g, _ in av["LCSF"].get("corso_acqua", [])]
    if not hard or not water:
        return 0
    wtree = shapely.STRtree(water)
    keep, moved = [], []
    for g, p in hard:
        near = wtree.query(g.buffer(CHANNEL_GAP))
        share = 0.0
        if len(near):
            wb = shapely.union_all([water[i] for i in near]).buffer(CHANNEL_GAP)
            share = g.boundary.intersection(wb).length / max(g.boundary.length, 1e-9)
        if share >= CHANNEL_SHARE:
            win, _, _ = dtm.window(*g.bounds, pad=2)
            a = np.asarray(win.a, np.float64)
            if a.shape[0] > 2 and a.shape[1] > 2:
                gy, gx = np.gradient(a, win.res)
                hh, ww = a.shape
                X, Y = np.meshgrid(win.x_min + (np.arange(ww) + 0.5) * win.res, win.y_max - (np.arange(hh) + 0.5) * win.res)
                m = shapely.contains_xy(g, X, Y)
                if m.sum() >= 4 and np.median(np.hypot(gx, gy)[m]) >= CHANNEL_SLOPE:
                    moved.append((g, p))
                    continue
        keep.append((g, p))
    av["LCSF"]["altro_rivestimento_duro"] = keep
    av["LCSF"].setdefault("pietraia_sabbia", []).extend(moved)
    print("stream banks of the survey as stones, not paved: %d (%.2f ha)" % (len(moved), sum(g.area for g, _ in moved) / 1e4),
          flush=True)
    return len(moved)


def main():
    av = load_av()
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    channel_linings(av, dtm)
    pickle.dump(av, open(os.path.join(WORK, "av_local.pkl"), "wb"))
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
