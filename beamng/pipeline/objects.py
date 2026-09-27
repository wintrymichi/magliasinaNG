"""Small street furniture from the segmented Street View views.

Classes (Mapillary Vistas): Bench 33, Trash Can 51, Mailbox 40, Fire Hydrant 38,
Junction Box 39, Bike Rack 34, Phone Booth 42. For each component in the horizon
views whose lowest pixel touches ground classes, the bottom centre is cast onto the
ground (calibrated pose) -> x, y. Observations are clustered across panoramas
(radius 0.8 m, >= 2 panoramas). Orientation: facing the carriageway.
Output: work/objects.json [{cls, x, y, z, n, width}]
"""
import json, math, os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import cKDTree
from config import WORK, DATASET
from geo import Grid
import camera
from poles import GROUND, ground_hit

CLS = {33: "bench", 51: "trash_can", 40: "mailbox", 38: "hydrant", 39: "junction_box", 34: "bike_rack", 42: "booth"}


def main():
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)

    def zfn(x, y):
        r, c = dtm.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(zs, [r, c], order=1, mode="nearest")

    obs = []
    for p in poses:
        rec = D[p["index"]]
        pos = np.array(p["pos"])
        for dn, rel in camera.VIEW_REL.items():
            f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
            if not os.path.exists(f):
                continue
            seg = np.asarray(Image.open(f))
            m = np.isin(seg, list(CLS)).astype(np.uint8)
            n, lab, st, cen = cv2.connectedComponentsWithStats(m, connectivity=8)
            for k in range(1, n):
                x0, y0, w, h, area = st[k]
                if area < 150 or y0 + h >= 1195 or x0 <= 2 or x0 + w >= 1598:
                    continue
                ys, xs = np.where(lab[y0:y0 + h, x0:x0 + w] == k)
                ys += y0; xs += x0
                ybot = ys.max()
                xb = int(np.median(xs[ys >= ybot - 3]))
                if seg[min(1199, ybot + 3), xb] not in GROUND:
                    continue
                cls = int(np.bincount(seg[ys, xs], minlength=65)[list(CLS)].argmax())
                cls = list(CLS)[cls]
                d = camera.view_pixel_to_world_dir(np.array([xb]), np.array([ybot]), p["R"], rec, rel, 0)[0]
                hit = ground_hit(pos, d, zfn, max_dist=25)
                if hit is None:
                    continue
                dist = float(np.hypot(*(hit[:2] - pos[:2])))
                if dist < 2 or dist > 22:
                    continue
                # width from the pixel extent at that distance (f = 800 px)
                obs.append(dict(x=float(hit[0]), y=float(hit[1]), cls=cls, dist=dist, pano=p["index"],
                                width=float(w * dist / 800.0)))
    P = np.array([[o["x"], o["y"]] for o in obs]) if obs else np.zeros((0, 2))
    tree = cKDTree(P) if len(P) else None
    used = np.zeros(len(obs), bool)
    out = []
    for i in np.argsort([o["dist"] for o in obs]):
        if used[i]:
            continue
        ii = [j for j in tree.query_ball_point(P[i], 0.8) if not used[j] and obs[j]["cls"] == obs[i]["cls"]]
        if len({obs[j]["pano"] for j in ii}) < 2:
            continue
        used[ii] = True
        w = np.array([1 / max(obs[j]["dist"], 1) for j in ii])
        x = float(np.average([obs[j]["x"] for j in ii], weights=w)); y = float(np.average([obs[j]["y"] for j in ii], weights=w))
        out.append(dict(cls=CLS[obs[i]["cls"]], x=x, y=y, z=float(zfn([x], [y])[0]), n=len(ii),
                        width=float(np.median([obs[j]["width"] for j in ii]))))
    json.dump(out, open(os.path.join(WORK, "objects.json"), "w"), indent=1)
    import collections
    print("observations", len(obs), "objects", len(out), dict(collections.Counter(o["cls"] for o in out)))


if __name__ == "__main__":
    main()
