"""Correction step: shrubs that the photos show and the game does not (full-dataset comparison).

Input: the segmentations saved by `validate_metrics.py <tag> full` for every view of every
panorama (photo and game screenshot at the same calibrated pose, world-aligned pinhole,
90 deg, 1280 x 720).
For every 4th image column the lowest vegetation pixel of the photo that stands on ground
(road, terrain, sidewalk... right below it) is the foot of a plant. Its ray is intersected
with the terrain -> position; the top of the same vegetation run at that distance -> height.
The foot counts as missing when the game shows no vegetation around that pixel. Feet 1.5-20 m
from the camera, not inside the paved areas (0.5 m from their edge), walls or buildings, are
pooled on a 1 m grid; cells confirmed by >= 3 panoramas become shrubs (height = median,
0.5-5 m), at most one per 1.2 m.
Output: work/photo_shrubs.npz (x, y, z, h) -> planted by vegetation.py like the understory.
"""
import json, math, os, pickle
import numpy as np
import cv2
import shapely
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, DATASET, LEVEL_DIR
from geo import Grid

VEG = 30
GROUND = (2, 7, 8, 9, 10, 11, 13, 14, 15, 23, 24, 29, 36, 41, 43)
W, H, HFOV = 1280, 720, 90.0
CELL = 1.0


def main():
    vdir = os.path.join(WORK, "validation_full")
    views = json.load(open(os.path.join(LEVEL_DIR, "validation_views.json")))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)

    def zfn(x, y):
        r, c = dtm.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(zs, [r, c], order=1, mode="nearest")
    f = W / 2 / math.tan(math.radians(HFOV) / 2)
    feet = []                                             # x, y, z, h, pano
    for v in views:
        fp = os.path.join(vdir, "seg_photo", v["name"] + ".png")
        fg = os.path.join(vdir, "seg_game", v["name"] + ".png")
        if not (os.path.exists(fp) and os.path.exists(fg)):
            continue
        sp = cv2.imread(fp, cv2.IMREAD_UNCHANGED); sg = cv2.imread(fg, cv2.IMREAD_UNCHANGED)
        y_ = math.radians(v["yaw"])
        fwd = np.array([math.sin(y_), math.cos(y_), 0.0]); right = np.array([math.cos(y_), -math.sin(y_), 0.0])
        up = np.array([0.0, 0.0, 1.0])
        pos = np.array(v["pos"])
        pano = int(v["name"][1:5])
        game_veg = cv2.dilate((sg == VEG).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        for u in range(2, W - 2, 4):
            col = sp[:, u]
            veg = col == VEG
            if not veg[H // 2 + 4:].any():
                continue
            # vegetation runs whose bottom stands on ground
            d = np.diff(np.r_[0, veg.astype(np.int8), 0])
            starts, ends = np.where(d == 1)[0], np.where(d == -1)[0] - 1
            for a, b in zip(starts, ends):
                if b <= H // 2 + 4 or b >= H - 4:
                    continue
                below = col[b + 1:b + 4]
                if not np.isin(below, GROUND).all():
                    continue
                if game_veg[b, u]:
                    continue                              # the game has vegetation there
                ray = f * fwd + (u - W / 2 + 0.5) * right + (H / 2 - b - 0.5) * up
                ray /= np.linalg.norm(ray)
                # march to the terrain
                t = np.arange(1.0, 24.0, 0.25)
                P = pos[None, :] + t[:, None] * ray[None, :]
                under = P[:, 2] <= zfn(P[:, 0], P[:, 1])
                if not under.any():
                    continue
                k = int(np.argmax(under))
                if k == 0:
                    continue
                g = P[k]
                r = float(np.hypot(*(g[:2] - pos[:2])))
                if r < 1.5 or r > 20:
                    continue
                # height from the top of the run, at the same horizontal distance
                elev_top = math.atan2(H / 2 - a - 0.5, f / max(abs(math.cos(math.atan2(u - W / 2 + 0.5, f))), 1e-6))
                ztop = pos[2] + r * math.tan(elev_top)
                h = float(np.clip(ztop - g[2], 0.3, 8.0))
                feet.append((g[0], g[1], g[2], h, pano))
    feet = np.array(feet)
    print("vegetation feet missing in the game:", len(feet))
    if not len(feet):
        np.savez(os.path.join(WORK, "photo_shrubs.npz"), x=[], y=[], z=[], h=[])
        return
    # exclusions: the paved interior (feet on the road are depth errors), walls, buildings
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    blocked = [g.buffer(-0.5) for c in ("strada_sentiero", "altro_rivestimento_duro", "marciapiede", "spartitraffico")
               for g, _ in av["LCSF"].get(c, [])]
    blocked += [g for g, _ in av["LCSF"].get("edificio", [])]
    blocked += [g.buffer(0.2) for g, _ in av["SOSF"].get("muro", [])]
    blocked = [g for g in blocked if not g.is_empty]
    tree = shapely.STRtree(blocked)
    pts = shapely.points(feet[:, :2])
    hit = np.zeros(len(feet), bool)
    for i, j in zip(*tree.query(pts, predicate="intersects")):
        hit[i] = True
    feet = feet[~hit]
    # pool on a grid, need >= 3 panoramas
    key = np.floor(feet[:, :2] / CELL).astype(np.int64)
    cells = {}
    for (cx, cy), row in zip(map(tuple, key), feet):
        cells.setdefault((cx, cy), []).append(row)
    out = []
    for (cx, cy), rows in cells.items():
        rows = np.array(rows)
        if len(set(rows[:, 4].astype(int))) < 3:
            continue
        out.append(((cx + 0.5) * CELL, (cy + 0.5) * CELL, float(np.median(rows[:, 2])), float(np.clip(np.median(rows[:, 3]), 0.5, 5.0)),
                    len(rows)))
    out = np.array(out) if out else np.zeros((0, 5))
    # thin: at most one shrub per 1.5 m (keep the best supported)
    keep = []
    if len(out):
        order = np.argsort(-out[:, 4])
        from scipy.spatial import cKDTree
        kd = cKDTree(out[:, :2]); taken = np.zeros(len(out), bool)
        for i in order:
            if taken[i]:
                continue
            keep.append(i)
            taken[kd.query_ball_point(out[i, :2], 1.2)] = True
    out = out[keep]
    np.savez(os.path.join(WORK, "photo_shrubs.npz"), x=out[:, 0], y=out[:, 1], z=out[:, 2], h=out[:, 3])
    print("shrubs to add:", len(out), "| median height %.1f m" % (np.median(out[:, 3]) if len(out) else 0))


if __name__ == "__main__":
    main()
