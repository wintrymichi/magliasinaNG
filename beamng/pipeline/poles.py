"""Poles, street lights, utility poles and traffic signs from the segmented Street View views.

Observation: a connected component of a pole class (Street Light 44, Pole 45,
Traffic Sign Frame 46, Utility Pole 47) in a horizon view whose lowest pixel sits on
ground-like classes. Its ground contact pixel is cast (calibrated pose) onto the
ground surface -> x, y; the top pixel (also searched in the 25 deg view) gives the
height. Observations are clustered across panoramas (radius 0.9 m); a pole needs
>= 2 observations from >= 2 different panoramas. Its position is the distance-
weighted median, its class the majority, its height the median.
Signs (Traffic Sign Front 50 / Back 49): components are attached to the pole whose
bearing matches (<= 1.5 deg) in the same view; plate centre height from the
elevation angle at the pole distance; best frontal crop saved to work/signs/.
Output: work/poles.json
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

POLE_CLS = {44: "street_light", 45: "pole", 46: "sign_frame", 47: "utility_pole"}
SIGN_CLS = {50: "sign_front", 49: "sign_back"}
GROUND = {2, 7, 9, 10, 11, 13, 14, 15, 23, 24, 29, 36, 41}


def ground_hit(pos, d, zfn, max_dist=35.0):
    """March along ray d from pos until it drops below the ground surface."""
    t = np.arange(0.5, max_dist, 0.05)
    P = pos[None, :] + t[:, None] * d[None, :]
    z = zfn(P[:, 0], P[:, 1])
    below = np.where(P[:, 2] <= z)[0]
    if len(below) == 0:
        return None
    k = below[0]
    return P[k]


def main():
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)

    def zfn(x, y):
        r, c = dtm.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(zs, [r, c], order=1, mode="nearest")

    obs = []
    signs = []
    for p in poses:
        rec = D[p["index"]]
        pos = np.array(p["pos"])
        for dn, rel in camera.VIEW_REL.items():
            f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
            if not os.path.exists(f):
                continue
            seg = np.asarray(Image.open(f))
            polemask = np.isin(seg, list(POLE_CLS)).astype(np.uint8)
            n, lab, st, cen = cv2.connectedComponentsWithStats(polemask, connectivity=8)
            for k in range(1, n):
                x0, y0, w, h, area = st[k]
                if h < 35 or area < 60 or h < 2.5 * w:
                    continue
                ys, xs = np.where(lab[y0:y0 + h, x0:x0 + w] == k)
                ys += y0; xs += x0
                ybot = ys.max()
                if ybot >= 1195:
                    continue
                xb = int(np.median(xs[ys >= ybot - 4]))
                below = seg[min(1199, ybot + 3), max(0, min(1599, xb))]
                if below not in GROUND:
                    continue
                cls = np.bincount(seg[ys, xs], minlength=65)[list(POLE_CLS)].argmax()
                cls = list(POLE_CLS)[cls]
                dvec = camera.view_pixel_to_world_dir(np.array([xb]), np.array([ybot]), p["R"], rec, rel, 0)[0]
                hit = ground_hit(pos, dvec, zfn)
                if hit is None:
                    continue
                dist = float(np.hypot(*(hit[:2] - pos[:2])))
                if dist > 30 or dist < 1.5:
                    continue
                # top: highest pixel of the component; if it touches the top border look in p25
                ytop = ys.min()
                xt = int(np.median(xs[ys <= ytop + 4]))
                top_dir = camera.view_pixel_to_world_dir(np.array([xt]), np.array([ytop]), p["R"], rec, rel, 0)[0]
                clipped = ytop <= 2
                if clipped:
                    f25 = f.replace("_p00.png", "_p25.png")
                    if os.path.exists(f25):
                        s25 = np.asarray(Image.open(f25))
                        c, r, ok = camera.world_to_view(hit[None], pos, p["R"], rec, rel, 25)
                        if ok[0] and 0 <= c[0] < 1600:
                            col = int(c[0])
                            band = np.isin(s25[:, max(0, col - 6):col + 7], list(POLE_CLS)).any(1)
                            rows = np.where(band)[0]
                            if len(rows):
                                top_dir = camera.view_pixel_to_world_dir(np.array([col]), np.array([rows.min()]),
                                                                          p["R"], rec, rel, 25)[0]
                                clipped = rows.min() <= 2
                horiz = np.hypot(top_dir[0], top_dir[1])
                ztop = pos[2] + top_dir[2] / max(horiz, 1e-6) * dist
                obs.append(dict(x=float(hit[0]), y=float(hit[1]), z=float(hit[2]), cls=int(cls), dist=dist,
                                h=float(ztop - hit[2]), clipped=bool(clipped), pano=p["index"], view=dn,
                                wpx=int(w), bearing=float(math.degrees(math.atan2(dvec[0], dvec[1])))))
            # signs in this view
            smask = np.isin(seg, list(SIGN_CLS)).astype(np.uint8)
            n2, lab2, st2, cen2 = cv2.connectedComponentsWithStats(smask, connectivity=8)
            for k in range(1, n2):
                x0, y0, w, h, area = st2[k]
                if area < 80 or w < 8 or h < 8:
                    continue
                cx, cy = cen2[k]
                ys, xs = np.where(lab2 == k)
                front = np.mean(seg[ys, xs] == 50) > 0.5
                dvec = camera.view_pixel_to_world_dir(np.array([cx]), np.array([cy]), p["R"], rec, rel, 0)[0]
                signs.append(dict(pano=p["index"], view=dn, cx=float(cx), cy=float(cy), w=int(w), h=int(h),
                                  area=int(area), front=bool(front), dir=dvec.tolist(), pos=pos.tolist()))
    print("pole observations", len(obs), "sign observations", len(signs))
    # cluster poles
    P = np.array([[o["x"], o["y"]] for o in obs])
    tree = cKDTree(P)
    used = np.zeros(len(obs), bool)
    poles = []
    order = np.argsort([o["dist"] for o in obs])
    for i in order:
        if used[i]:
            continue
        ii = [j for j in tree.query_ball_point(P[i], r=0.9) if not used[j]]
        grp = [obs[j] for j in ii]
        if len({g["pano"] for g in grp}) < 2:
            continue
        used[ii] = True
        wts = np.array([1.0 / max(g["dist"], 1.0) for g in grp])
        x = float(np.average([g["x"] for g in grp], weights=wts))
        y = float(np.average([g["y"] for g in grp], weights=wts))
        cls = int(np.bincount([g["cls"] for g in grp]).argmax())
        hs = [g["h"] for g in grp if not g["clipped"] and g["dist"] < 20]
        poles.append(dict(x=x, y=y, z=float(zfn([x], [y])[0]), cls=POLE_CLS[cls], n=len(grp),
                          npanos=len({g["pano"] for g in grp}), h=float(np.median(hs)) if hs else None,
                          spread=float(np.std([g["x"] for g in grp]) + np.std([g["y"] for g in grp]))))
    print("poles", len(poles), {c: sum(1 for p in poles if p["cls"] == c) for c in POLE_CLS.values()})
    # attach signs to poles by bearing agreement
    PP = np.array([[p["x"], p["y"], p["z"]] for p in poles]) if poles else np.zeros((0, 3))
    os.makedirs(os.path.join(WORK, "signs"), exist_ok=True)
    for sgn in signs:
        pos = np.array(sgn["pos"]); d = np.array(sgn["dir"])
        if len(PP) == 0:
            break
        v = PP[:, :2] - pos[:2]
        dist = np.hypot(v[:, 0], v[:, 1])
        bdir = d[:2] / max(np.hypot(d[0], d[1]), 1e-9)
        cosang = (v @ bdir) / np.maximum(dist, 1e-6)
        ok = (dist < 25) & (cosang > math.cos(math.radians(1.5)))
        if not ok.any():
            continue
        j = int(np.argmin(np.where(ok, dist, np.inf)))
        horiz = np.hypot(d[0], d[1])
        zc = pos[2] + d[2] / max(horiz, 1e-6) * dist[j]
        sgn["pole"] = j
        sgn["zc"] = float(zc)
        sgn["dist"] = float(dist[j])
        poles[j].setdefault("signs", []).append(sgn)
    # per pole: group sign observations by plate height and keep the best frontal crop
    for j, pl in enumerate(poles):
        if "signs" not in pl:
            continue
        obs_s = pl.pop("signs")
        plates = []
        for so in sorted(obs_s, key=lambda o: o["zc"]):
            if plates and abs(so["zc"] - plates[-1]["zc_list"][-1]) < 0.35:
                plates[-1]["obs"].append(so); plates[-1]["zc_list"].append(so["zc"])
            else:
                plates.append({"obs": [so], "zc_list": [so["zc"]]})
        out = []
        for q, pt in enumerate(plates):
            best = max(pt["obs"], key=lambda o: (o["front"], o["area"] / max(o["dist"], 1)))
            rec = D[best["pano"]]
            img = cv2.imread(os.path.join(DATASET, "viste", f"{rec['index']:04d}_{rec['id']}_{best['view']}_p00.jpg"))
            pad = int(0.25 * max(best["w"], best["h"])) + 4
            x0 = int(best["cx"] - best["w"] / 2 - pad); y0 = int(best["cy"] - best["h"] / 2 - pad)
            crop = img[max(0, y0):y0 + best["h"] + 2 * pad, max(0, x0):x0 + best["w"] + 2 * pad]
            name = f"sign_{j:03d}_{q}.png"
            if crop.size:
                cv2.imwrite(os.path.join(WORK, "signs", name), cv2.resize(crop, None, fx=3, fy=3,
                                                                          interpolation=cv2.INTER_CUBIC))
            # RGBA plate: exact component pixels (segmentation mask as alpha)
            seg = np.asarray(Image.open(os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{best['view']}_p00.png")))
            bx0, by0 = int(round(best["cx"] - best["w"] / 2)), int(round(best["cy"] - best["h"] / 2))
            bx0, by0 = max(0, bx0 - 1), max(0, by0 - 1)
            bx1, by1 = bx0 + best["w"] + 2, by0 + best["h"] + 2
            m = (np.isin(seg[by0:by1, bx0:bx1], [49, 50]).astype(np.uint8) * 255)
            m = cv2.dilate(m, np.ones((2, 2), np.uint8))
            rgba = np.dstack([cv2.cvtColor(img[by0:by1, bx0:bx1], cv2.COLOR_BGR2RGB), m])
            plate_name = f"plate_{j:03d}_{q}.png"
            if rgba.size:
                Image.fromarray(rgba).save(os.path.join(WORK, "signs", plate_name))
            facing = (np.array(best["pos"][:2]) - np.array([pl["x"], pl["y"]]))
            out.append(dict(z=float(np.median(pt["zc_list"])), n=len(pt["obs"]), crop=name, plate=plate_name,
                            front=bool(best["front"]), dist=float(best["dist"]), wpx=int(best["w"]), hpx=int(best["h"]),
                            face_bearing=float(math.degrees(math.atan2(facing[0], facing[1]))) if best["front"]
                            else float(math.degrees(math.atan2(-facing[0], -facing[1])))))
        pl["signs"] = out
    json.dump(poles, open(os.path.join(WORK, "poles.json"), "w"), indent=1)
    print("poles with signs", sum(1 for p in poles if p.get("signs")),
          "plates", sum(len(p.get("signs", [])) for p in poles))


if __name__ == "__main__":
    main()
