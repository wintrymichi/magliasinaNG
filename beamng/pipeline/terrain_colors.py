"""Measured base colours of the terrain materials.

Open ground (grass, gardens, gravel, paved, rock): median SWISSIMAGE colour over
the cadastral classes mapped to the material, excluding canopy (nDSM > 0.5 m) and
shadows. Forest floor is hidden from the air: its colour is the median of the
pixels segmented as 'Terrain' in the lower half of the side views of panoramas
taken in forest stretches (land cover under the camera = forest).
Writes work/terrain_colors.json {material: [r, g, b]}.
"""
import json, os
import numpy as np
import rasterio
from PIL import Image
from config import WORK, DATASET
from geo import Grid
from landcover import CLASSES, CODE
from terrain import LC_TO_MAT, TERRAIN_MATS


def main():
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        o = s.read().transpose(1, 2, 0)
    lc = np.load(os.path.join(WORK, "landcover05.npz"))["a"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    open_ground = (dsm.a - dtm.a) < 0.5
    v = o.max(-1)
    lit = (v > 70) & (v < 250)
    colors = {}
    for mat in TERRAIN_MATS:
        cls = [CODE[c] for c, m in LC_TO_MAT.items() if m == mat]
        m = np.isin(lc, cls) & open_ground & lit
        if m.sum() > 2000:
            colors[mat] = np.median(o[m], 0).astype(int).tolist()
    # forest floor from the photos
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    lcg = Grid(lc, dtm.x_min, dtm.y_max, dtm.res)
    px = []
    for p in poses:
        c = int(lcg.sample([p["pos"][0]], [p["pos"][1]], order=0)[0])
        # forest on either side: look 8 m left/right of the camera
        R = np.array(p["R"])
        right = R @ np.array([1.0, 0, 0])
        sides = [int(lcg.sample([p["pos"][0] + s * 8 * right[0]], [p["pos"][1] + s * 8 * right[1]], order=0)[0])
                 for s in (-1, 1)]
        for s, side in zip((-1, 1), ("left", "right")):
            if sides[(s + 1) // 2] not in (CODE["bosco_fitto"], CODE["altro_bosco"]):
                continue
            name = f"{p['index']:04d}_{p['id']}_{side}_p00"
            f_img = os.path.join(DATASET, "viste", name + ".jpg")
            f_seg = os.path.join(WORK, "seg", name + ".png")
            if not (os.path.exists(f_img) and os.path.exists(f_seg)):
                continue
            im = np.asarray(Image.open(f_img))
            sg = np.asarray(Image.open(f_seg))
            m = sg == 29                                  # Mapillary 'Terrain'
            m[: im.shape[0] // 2] = False
            if m.sum() > 500:
                px.append(im[m][:: max(1, m.sum() // 2000)])
    if px:
        allpx = np.concatenate(px)
        ff = np.median(allpx, 0).astype(int).tolist()
        colors["ForestFloor"] = ff
        colors["ForestFloor2"] = ff
        colors["Moss"] = colors.get("Moss", ff)
        colors["Mud"] = colors.get("Mud", [int(c * 0.8) for c in ff])
        print("forest floor from", len(px), "photo views:", ff)
    for mat in TERRAIN_MATS:
        colors.setdefault(mat, [110, 110, 100])
    json.dump(colors, open(os.path.join(WORK, "terrain_colors.json"), "w"), indent=1)
    print(colors)


if __name__ == "__main__":
    main()
