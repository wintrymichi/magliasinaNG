"""Street-light heads triangulated from several panoramas (class 'Street Light' = 44).

Every lamp-head component in the horizon and 25 deg views gives a ray (calibrated pose).
Rays of different panoramas within 45 m of each other are intersected pairwise
(closest points); a pair is kept when the rays pass within 0.5 m of each other, the
point is 3-13 m above the ground, in front of both cameras. Intersections are clustered
(1.2 m); a lamp needs >= 3 supporting pairs. The pole foot is the detected pole within
2.5 m of the head's ground point if any, else the head position moved 1.2 m away from
the carriageway (single-arm luminaires). Output: work/lamps.json
"""
import json, os, itertools
import numpy as np
import cv2
from PIL import Image
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, DATASET
from geo import Grid
import camera

SL = 44


def main():
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    rays = []                                               # (pano, origin, dir)
    dets = {}                                               # (pano, view, pitch) -> (k,2) head centres
    for p in poses:
        rec = D[p["index"]]
        for pitch in (0, 25):
            for dn, rel in camera.VIEW_REL.items():
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p{pitch:02d}.png")
                if not os.path.exists(f):
                    continue
                seg = np.asarray(Image.open(f))
                n, lab, st, cen = cv2.connectedComponentsWithStats((seg == SL).astype(np.uint8), connectivity=8)
                for k in range(1, n):
                    if st[k][4] < 25:
                        continue
                    cx, cy = cen[k]
                    if cx < 20 or cx > 1580:
                        continue
                    d = camera.view_pixel_to_world_dir(np.array([cx]), np.array([cy]), p["R"], rec, rel, pitch)[0]
                    rays.append((p["index"], np.array(p["pos"]), d / np.linalg.norm(d)))
                    dets.setdefault((p["index"], dn, pitch), []).append((cx, cy))
    print("lamp-head rays", len(rays))
    O = np.array([r[1] for r in rays]); Dd = np.array([r[2] for r in rays]); P = np.array([r[0] for r in rays])
    tree = cKDTree(O[:, :2])
    pts = []
    for i, j in tree.query_pairs(r=45.0):
        if P[i] == P[j]:
            continue
        w0 = O[i] - O[j]
        a, b, c = Dd[i] @ Dd[i], Dd[i] @ Dd[j], Dd[j] @ Dd[j]
        d, e = Dd[i] @ w0, Dd[j] @ w0
        den = a * c - b * b
        if den < 1e-4:
            continue
        s = (b * e - c * d) / den
        t = (a * e - b * d) / den
        if s < 2 or t < 2 or s > 40 or t > 40:
            continue
        p1, p2 = O[i] + s * Dd[i], O[j] + t * Dd[j]
        if np.linalg.norm(p1 - p2) > 0.5:
            continue
        m = (p1 + p2) / 2
        hag = m[2] - dtm.sample([m[0]], [m[1]])[0]
        if 3.0 < hag < 13.0:
            pts.append(m)
    pts = np.array(pts)
    print("valid intersections", len(pts))
    lamps = []
    if len(pts):
        t2 = cKDTree(pts)
        used = np.zeros(len(pts), bool)
        dens = np.array([len(t2.query_ball_point(q, 1.2)) for q in pts])
        for i in np.argsort(-dens):
            if used[i]:
                continue
            ii = [k for k in t2.query_ball_point(pts[i], 1.2) if not used[k]]
            if len(ii) < 2:
                continue
            used[ii] = True
            lamps.append(np.median(pts[ii], 0))
    # verification by reprojection: the head must be detected where it projects
    pmap = {p["index"]: p for p in poses}
    verified = []
    for h in lamps:
        vis = conf = 0
        for p in poses:
            dd = np.hypot(p["pos"][0] - h[0], p["pos"][1] - h[1])
            if dd < 3 or dd > 35:
                continue
            rec = D[p["index"]]
            seen = False
            for pitch in (0, 25):
                for dn, rel in camera.VIEW_REL.items():
                    c, r, ok = camera.world_to_view(h[None], p["pos"], p["R"], rec, rel, pitch)
                    if not (ok[0] and 25 <= c[0] < 1575 and 25 <= r[0] < 1175):
                        continue
                    seen = True
                    dl = dets.get((p["index"], dn, pitch))
                    if dl is not None and np.min(np.hypot(np.array(dl)[:, 0] - c[0], np.array(dl)[:, 1] - r[0])) < 20:
                        conf += 1
                        break
                if seen:
                    break
            vis += seen
        if conf >= 3 and conf >= 0.5 * vis:
            verified.append((conf, h))
    verified.sort(key=lambda t: -t[0])
    lamps = []
    for conf, h in verified:
        if all(np.hypot(*(h[:2] - q[:2])) > 4.0 for q in lamps):
            lamps.append(h)
    poles = json.load(open(os.path.join(WORK, "poles.json")))
    PP = np.array([[q["x"], q["y"]] for q in poles]) if poles else np.zeros((0, 2))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    C = rp["center"]
    out = []
    for h in lamps:
        k = int(np.argmin(np.hypot(C[:, 0] - h[0], C[:, 1] - h[1])))
        away = h[:2] - C[k]
        away /= max(np.linalg.norm(away), 1e-6)
        foot = h[:2] + away * 1.2
        src = "arm_prior"
        if len(PP):
            dd = np.hypot(PP[:, 0] - h[0], PP[:, 1] - h[1])
            j = int(np.argmin(dd))
            if dd[j] < 2.5 and not poles[j].get("signs"):
                foot = PP[j]; src = "pole_detection"
        zg = float(dtm.sample([foot[0]], [foot[1]])[0])
        out.append({"head": h.round(3).tolist(), "foot": [float(foot[0]), float(foot[1]), zg],
                    "height": float(h[2] - zg), "src": src})
    json.dump(out, open(os.path.join(WORK, "lamps.json"), "w"), indent=1)
    print("lamps", len(out), "with detected pole", sum(1 for o in out if o["src"] == "pole_detection"),
          "height median %.1f m" % (np.median([o["height"] for o in out]) if out else 0))


if __name__ == "__main__":
    main()
