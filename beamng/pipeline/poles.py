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
import argparse, gzip, json, math, os, re, sys, time, zipfile
import bng
import optimize_level
import lamps as pl
import network_mesh as pu
import walls as pw
import props
import road_mesh
from config import LEVEL_NAME

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


# --------------------------------------------------------------------------------------------------
# Delineator posts along the main roads outside the villages, and wooden poles along the country roads to
# the houses outside them (v2.8), in the built level.
#
# Up to v2.7 the 96 poles of the map (delineators, sign poles, three wooden poles) stood on the Magliaso-Pura
# cantonal road, where the panoramas show them; the roads between the villages had none. There are no open
# data on either, so a rule places them, not their real places (lamps.lamps_step tells the villages apart):
# - delineators: on the roads of the AI network of 6 m and more (drivability >= MAIN) outside the villages, on
#   both sides, every DELIN_STEP m on the straight and closer in the bends (DELIN_BENDS: radius -> step), as
#   the Swiss ones stand; DELIN_OFF m beyond the edge of the carriageway, on ground within DELIN_STEP_Z m of
#   its height; not where a guard rail, a fence, a wall, a building, the railway or another road is (the post
#   would stand in it or be needless), not within JUNCTION m of another road's axis. White posts with a black band, 1 m
#   over the ground, as props.py draws the delineators of the cantonal road; pipeline meshes in tiles of
#   TILE m, drawn up to DELIN_DRAW m, without collision (plastic posts a car knocks over, not a wall);
# - wooden poles: on the country roads (drivability COUNTRY: the 3 and 4 m roads) outside the villages
#   along houses (a building of the Federal Register within HOUSE_R m), on one side, every POLE_STEP m,
#   POLE_OFF m beyond the edge, in lines of MIN_LINE poles at least, the game's wooden pole of the cantonal road (electric_pole_wood_old_01.dae,
#   POLE_H m at scale 1, as its three poles there measure) at POLE_SCALE, with collision; one cable from the
#   top of a pole to the next of the same line (CABLE_DROP m under the top, sagging by CABLE_SAG of the span),
#   a thin black tube in the tiles of the delineators (the attachment points of the game model are not known
#   without the game: the cable starts at the pole's axis). A line ends where its cable would pass within
#   CABLE_CLEAR m of a street lamp (lamps.lamps_step runs before) or of a roof over or beside it, and goes on
#   from the next pole if MIN_LINE poles are left.
# - none along the panoramas' route (the cantonal road): the poles there are the measured ones.
# Everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish roadside
# --------------------------------------------------------------------------------------------------

MAIN = 0.9                  # drivability of the 6 m roads and more (ai_roads.TLM_DRIVE)
COUNTRY = (0.5, 0.8)        # drivability of the 3 and 4 m roads
DELIN_STEP = 50.0           # m between two delineators on the straight
DELIN_BENDS = ((100.0, 12.5), (300.0, 25.0))      # radius under which (m) -> step (m)
DELIN_OFF = 0.5             # m beyond the carriageway edge
DELIN_STEP_Z = 0.6          # m, ground under a post within this of the edge height
DELIN_DRAW = 300.0          # m up to which the delineators are drawn
JUNCTION = 12.0             # m from another road's axis
HOUSE_R = 60.0              # m, a house this near: a line along the road
POLE_STEP = 45.0            # m between two wooden poles
MIN_LINE = 4                # poles of a line at least (a lone pole or two carry nothing)
POLE_OFF = 1.5              # m beyond the carriageway edge
POLE_SCALE = 0.85           # 8.5 m poles
POLE_STEP_Z = 1.2           # m, ground under a pole within this of the edge height
POLE_H = 10.05              # m, height of the game's wooden pole at scale 1
CABLE_DROP, CABLE_SAG, CABLE_R = 0.25, 0.015, 0.012     # m under the top, share of the span, radius (m)
CABLE_CLEAR = 1.0           # m between a cable and a street lamp or a roof: else the line ends there (v2.8 chain)
TILE = 384.0                # m, tiles of the delineator meshes (as optimize_level's merged tiles)
WOODPOLE = props.WOODPOLE


def bend_radius(T, k=10):
    """Radius of the bend (m) at every point of an axis sampled every metre (from the turn of the tangent
    over 2k m)."""
    a = np.unwrap(np.arctan2(T[:, 1], T[:, 0]))
    d = np.abs(a[np.minimum(np.arange(len(a)) + k, len(a) - 1)] - a[np.maximum(np.arange(len(a)) - k, 0)])
    return (2 * k) / np.maximum(d, 1e-6)


def delineator(c, to_road, z):
    """Triangles of one post (white, with the black band facing the road): (white, black) soups."""
    along = np.array([to_road[1], -to_road[0]])
    w = props.box(c, along, 0.12, 0.10, z - 0.2, z + 1.0)
    b = props.box(c + to_road * 0.052, along, 0.10, 0.004, z + 0.72, z + 0.90)
    return w, b


def cable(a, b, n=6):
    """Triangles of a cable from a to b (pole tops, 3D), sagging by CABLE_SAG of the span, a tube of n sides."""
    span = float(np.linalg.norm(b[:2] - a[:2]))
    k = max(int(span / 3.0), 2)
    t = np.linspace(0.0, 1.0, k + 1)
    C = a[None] + t[:, None] * (b - a)[None]
    C[:, 2] -= 4 * CABLE_SAG * span * t * (1 - t)
    d = np.gradient(C, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    u = np.cross(d, [0.0, 0.0, 1.0])
    u /= np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-9)
    v = np.cross(u, d)
    ang = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    R = C[:, None] + CABLE_R * (np.cos(ang)[None, :, None] * u[:, None] + np.sin(ang)[None, :, None] * v[:, None])
    tris = []
    for i in range(k):
        for j in range(n):
            p0, p1, q0, q1 = R[i, j], R[i, (j + 1) % n], R[i + 1, j], R[i + 1, (j + 1) % n]
            tris += [p0, q0, q1, p0, q1, p1]
    return np.array(tris)


def roadside_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    terrain = lambda x, y: float(pu.terrain_top(q, np.atleast_1d(x), np.atleast_1d(y))[0])
    road = pl.faces(zi, lv, ["roads/surfaces"])
    CARR = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if pl.CARRIAGEWAY.match(m)]))
    GROUND = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if not pl.CARRIAGEWAY.match(m)]))
    ROOF = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["buildings"]).values())))
    WALL = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["walls"], keep=lambda sn: "backfill" not in sn).values())))
    RAIL = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["railway"]).values()) or [np.zeros((0, 3, 3))]))
    obst = cKDTree(pl.obstacle_points(zi, lv))
    # the street lamps (lamps.lamps_step runs before): no cable through one
    lamp_xy = np.array([o["position"][:2] for f in zi.namelist() if f.endswith("street_lights/items.level.json")
                        for o in pl.read_items(zi, f) if o.get("class") == "TSStatic"], np.float64).reshape(-1, 2)
    ltree = cKDTree(lamp_xy) if len(lamp_xy) else None
    gwr = json.load(gzip.open(os.path.join(pl.DATI, "gwr_area.json.gz")))["buildings"]
    G = np.array([[b["x"], b["y"]] for b in gwr if b.get("gstat") == 1004 and (b.get("garea") or pl.MIN_AREA) >= pl.MIN_AREA])
    gtree = cKDTree(G)
    pano = cKDTree(np.array([p["pos"][:2] for p in json.load(open(os.path.join(pl.DATI, "poses.json")))]))
    roads = [o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [pl.sample(o["nodes"]) for o in roads]
    ids = np.concatenate([np.full(len(s[0]), i) for i, s in enumerate(S) if s is not None])
    allp = np.concatenate([s[0][:, :2] for s in S if s is not None])
    allw = np.concatenate([s[2] for s in S if s is not None])
    atree = cKDTree(allp)
    why = {"tried": 0, "carriageway": 0, "step": 0, "building": 0, "wall": 0, "railway": 0, "clear": 0, "cable": 0}

    def spot(c, t, w, side, off, clear, step_z, road):
        """A free place beside the axis point c (tangent t, width w) of road `road`, `off` m beyond the
        carriageway on side +-1: (x, y, z, unit vector to the road) or None."""
        n = side * np.array([t[1], -t[0]])
        d = np.arange(0.5, w / 2 + 6.0, 0.25)
        Q = c[:2] + d[:, None] * n
        on = np.isfinite(CARR.height(Q[:, 0], Q[:, 1], "high")) & (d < w / 2 + 3.0)
        edge = d[np.flatnonzero(on).max()] if on.any() else w / 2
        p = c[:2] + (edge + off) * n
        why["tried"] += 1
        ring = p + 0.25 * np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]])
        if np.isfinite(CARR.height(ring[:, 0], ring[:, 1], "high")).any():
            why["carriageway"] += 1
            return None
        k = [x for x in atree.query_ball_point(p, 8.0) if ids[x] != road]
        if k and np.any(np.hypot(*(allp[k] - p).T) < allw[k] / 2 + off):
            why["carriageway"] += 1
            return None
        ze = CARR.height([c[0] + (edge - 0.3) * n[0]], [c[1] + (edge - 0.3) * n[1]], "high")[0]
        ze = c[2] if not np.isfinite(ze) else ze
        zg = GROUND.height([p[0]], [p[1]], "high")[0]
        zt = terrain(p[0], p[1])
        z = zg if np.isfinite(zg) and zg > zt - 0.3 else zt
        if not (-step_z <= z - ze <= step_z * 0.7):
            why["step"] += 1
            return None
        if np.isfinite(ROOF.height([p[0]], [p[1]], "high")[0]):
            why["building"] += 1
            return None
        if np.isfinite(WALL.height(ring[:, 0], ring[:, 1], "high")).any():
            why["wall"] += 1
            return None
        if np.isfinite(RAIL.height(ring[:, 0], ring[:, 1], "high")).any():
            why["railway"] += 1
            return None
        if obst.query_ball_point(p, clear, return_length=True) > 0:
            why["clear"] += 1
            return None
        return float(p[0]), float(p[1]), float(z), -n

    top = lambda p: np.array([p[0], p[1], p[2] + POLE_H * POLE_SCALE - CABLE_DROP])

    def cable_free(a, b):
        """No street lamp within CABLE_CLEAR m (xy) of the cable between the poles a and b, and no roof over it
        or within CABLE_CLEAR m under it."""
        A, B = top(a), top(b)
        span = float(np.linalg.norm(B[:2] - A[:2]))
        t = np.linspace(0.0, 1.0, max(int(span / 0.25), 2) + 1)
        C = A[None] + t[:, None] * (B - A)[None]
        C[:, 2] -= 4 * CABLE_SAG * span * t * (1 - t)
        if ltree is not None and any(ltree.query_ball_point(C[:, :2], CABLE_CLEAR)):
            return False
        u = (B[:2] - A[:2]) / max(span, 1e-9)
        side = np.array([-u[1], u[0]])
        for off in (0.0, -0.5, 0.5, -1.0, 1.0):                     # over the cable and up to CABLE_CLEAR beside it
            Q = C[:, :2] + off * CABLE_CLEAR * side
            h = ROOF.height(Q[:, 0], Q[:, 1], "high")
            if (np.isfinite(h) & (h > C[:, 2] - CABLE_CLEAR)).any():
                return False
        return True

    delins, poles, lines = [], [], []
    for i, (o, s) in enumerate(zip(roads, S)):
        if s is None:
            continue
        P, T, W, dist = s
        drv = float(o.get("drivability", 0))
        main_road = drv >= MAIN
        country = COUNTRY[0] <= drv <= COUNTRY[1]
        if not (main_road or country):
            continue
        out = gtree.query_ball_point(P[:, :2], pl.VILLAGE_R, return_length=True) < pl.VILLAGE_N
        out &= ~np.isfinite(pano.query(P[:, :2], distance_upper_bound=pl.PANO_R)[0])
        near = atree.query_ball_point(P[:, :2], JUNCTION)
        out &= np.array([not np.any(ids[k] != i) for k in near])
        if main_road:
            R = bend_radius(T)
            next_s = None
            for j in np.flatnonzero(out):
                step = next((st for r, st in DELIN_BENDS if R[j] < r), DELIN_STEP)
                if next_s is None:
                    next_s = dist[j] + step / 2
                if dist[j] < next_s:
                    continue
                for side in (1, -1):
                    r = spot(P[j], T[j], W[j], side, DELIN_OFF, 0.5, DELIN_STEP_Z, i)
                    if r is not None:
                        delins.append(r)
                next_s = dist[j] + step
        else:
            houses = gtree.query_ball_point(P[:, :2], HOUSE_R, return_length=True) > 0
            side, next_s, run = 1, None, []

            def keep(run):
                if len(run) >= MIN_LINE:
                    k0 = len(poles)
                    poles.extend(r for r, _ in run)
                    lines.extend((k0 + m, k0 + m + 1) for m in range(len(run) - 1))
                why["short_line"] = why.get("short_line", 0) + (len(run) if len(run) < MIN_LINE else 0)

            def flush(run):
                """The run as lines, broken where a cable would pass through a lamp or a house."""
                piece = []
                for r in run:
                    if piece and not cable_free(piece[-1][0], r[0]):
                        why["cable"] += 1
                        keep(piece)
                        piece = []
                    piece.append(r)
                keep(piece)
            for j in np.flatnonzero(out & houses):
                if next_s is None:
                    next_s = dist[j] + 10.0
                if dist[j] < next_s:
                    continue
                r = spot(P[j], T[j], W[j], side, POLE_OFF, 1.5, POLE_STEP_Z, i) or \
                    spot(P[j], T[j], W[j], -side, POLE_OFF, 1.5, POLE_STEP_Z, i)
                if r is None:
                    continue
                if run and dist[j] - run[-1][1] > 1.5 * POLE_STEP:                    # a gap: another line
                    flush(run)
                    run = []
                run.append((r + (math.atan2(T[j][1], T[j][0]),), dist[j]))
                side = 1 if np.array([T[j][1], -T[j][0]]) @ (np.array(r[:2]) - P[j][:2]) > 0 else -1
                next_s = dist[j] + POLE_STEP
            flush(run)
    print("delineators: %d, wooden poles: %d in %d spans (%s)" % (len(delins), len(poles), len(lines), why), flush=True)

    # ---- the meshes of the delineators and the cables, one per tile; the poles
    new_files, items = {}, []
    tiles = {}
    key = lambda x, y: (int(math.floor(x / TILE)), int(math.floor(y / TILE)))
    for x, y, z, to_road in delins:
        w, b = delineator(np.array([x, y]), np.asarray(to_road), z)
        tiles.setdefault(key(x, y), []).append(("mp_delineator_white", w, True))
        tiles[key(x, y)].append(("mp_delineator_black", b, True))
    for a, b in lines:
        c = cable(top(poles[a]), top(poles[b]))
        m = 0.5 * (np.asarray(poles[a][:2]) + np.asarray(poles[b][:2]))
        tiles.setdefault(key(*m), []).append(("mp_cable", c, False))
    for (tx, ty), parts in sorted(tiles.items()):
        mb = bng.MeshBuilder()
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        for mat, V, flat in parts:
            mb.add(mat, V, uvs=V[:, :2], normals=bng.flat_normals_soup(V) if flat else None)
        allv = np.concatenate([V for _, V, _ in parts])
        radius = 0.5 * float(np.linalg.norm(np.ptp(allv, axis=0)))
        detail = max(2, int(round(radius * optimize_level.PIX_K / DELIN_DRAW)))
        rel = f"art/shapes/props/roadside_{tx:+03d}_{ty:+03d}.dae"
        tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"roadside_{os.getpid()}.dae")
        mb.write_dae(tmp, name="roadside", origin=origin, detail=detail, orient=True)
        new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
        os.remove(tmp)
        o = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False)
        o["__parent"] = "delineators"
        items.append(o)
    mats = [bng.material("mp_cable", base_color=[0.05, 0.05, 0.05, 1], roughness=0.6, metallic=0.3, double_sided=True)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"roadside_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/props/roadside.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    for x, y, z, to_road, th in poles:
        o = bng.tsstatic(WOODPOLE, (x, y, z), rot=bng.rot_local_x_to(th), scale=(POLE_SCALE,) * 3, collision=True)
        o["__parent"] = "country_poles"
        items.append(o)
    props_items = f"{lv}/main/MissionGroup/props/items.level.json"
    groups = pl.read_items(zi, props_items)
    have = {g.get("name") for g in groups}
    for name in ("delineators", "country_poles"):
        if name not in have:
            groups.append({"name": name, "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    new_files[props_items] = pl_write(groups)
    new_files[f"{lv}/main/MissionGroup/props/delineators/items.level.json"] = pl_write([o for o in items if o["__parent"] == "delineators"])
    new_files[f"{lv}/main/MissionGroup/props/country_poles/items.level.json"] = pl_write([o for o in items if o["__parent"] == "country_poles"])

    with zi.writer() as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):                     # the new files
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zo.writestr(ni, data)
    print("written in %.0f s" % (time.time() - t0), flush=True)
    if report:
        res = {"delineators": len(delins), "tiles": len(tiles),
               "wooden_poles": len(poles), "cable_spans": len(lines), "rejected": why,
               "poles": [[round(p[0], 2), round(p[1], 2), round(p[2], 2)] for p in poles],
               "delineator_posts": [[round(d[0], 2), round(d[1], 2), round(d[2], 2)] for d in delins]}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0


def pl_write(objs):
    return ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
