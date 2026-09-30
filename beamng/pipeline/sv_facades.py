"""Plaster and shutter colours of the buildings seen from the streets, measured in the Street View
panoramas of the whole area (v2.2): the observation behind the procedural facades (facades.py).

Points on every facade of swissBUILDINGS3D (a grid of STEP m on each planar wall, from 1 m above the
ground to just under the eaves, 0.15 m in front of the wall) are projected into every panorama within
MAXD m (sv_fetch.py; camera CAM_H m above the DTM, the calibration of dati/camera_height.json, heading
and tilt from the metadata with the convention of dati/attitude_convention.json). A point counts when
the facade faces the camera, the line of sight does not pass under the surface model (swissSURFACE3D:
trees, other buildings, walls in between) and its pixel is not vegetation, sky, deep shadow or burnt
out. Per building: the median colour of its points over all the panoramas that see it (the plaster
tone), and the colour class of the shutters when enough of its upper points have a shutter colour
(green, brown, red, grey) clearly apart from the plaster.
Only numbers leave this step: dati/facade_colors.json {uuid: {rgb, n, panos, year, shutter}}.
    python sv_facades.py
"""
import colorsys, json, math, os, pickle, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from config import WORK
from geo import Grid
import camera

STEP = 0.75
MAXD = 45.0
MIND = 3.0
CAM_H = 2.2
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "facade_colors.json")
PANO = os.path.join(WORK, "sv", "pano")
MIN_N, MIN_PANOS = 25, 2


def facade_points(blds, dtm):
    """Sample points of all facades: (P (n, 3), outward normals (n, 3), building index (n,), height of
    the point above the ground (n,))."""
    import texturing
    import buildings_mesh
    import facades
    Ps, Ns, Bs, Hs = [], [], [], []
    for bi, b in enumerate(blds):
        if b["kind"] in ("Lagertank", "Treibhaus", "Flugdach", "Mauer gross") or not len(b["walls"]):
            continue
        walls = buildings_mesh.orient(b)["walls"]
        for idx, n, d0 in texturing.facade_groups(walls):
            a = np.array([-n[1], n[0], 0.0])
            F = facades.facade_polygon(walls[idx], a)
            if F is None:
                continue
            u0, z0, u1, z1 = F.bounds
            if u1 - u0 < 1.5:
                continue
            us = np.arange(u0 + 0.4, u1 - 0.3, STEP)
            zs = np.arange(z0 + 0.3, z1, STEP)
            if not len(us) or not len(zs):
                continue
            U, Z = np.meshgrid(us, zs)
            U, Z = U.ravel(), Z.ravel()
            import shapely
            inside = shapely.contains_xy(F.buffer(-0.25), U, Z)
            U, Z = U[inside], Z[inside]
            if not len(U):
                continue
            x = n[0] * d0 + U * a[0] + n[0] * 0.15
            y = n[1] * d0 + U * a[1] + n[1] * 0.15
            g = dtm.sample(x, y)
            keep = Z > g + 1.0
            if not keep.any():
                continue
            Ps.append(np.column_stack([x[keep], y[keep], Z[keep]]))
            Ns.append(np.repeat(np.asarray(n, float)[None], int(keep.sum()), 0))
            Bs.append(np.full(int(keep.sum()), bi, np.int32))
            Hs.append((Z - g)[keep])
    return np.concatenate(Ps), np.concatenate(Ns), np.concatenate(Bs), np.concatenate(Hs)


_G = {}


def _init(points_file, dsm_file, conv):
    d = np.load(points_file)
    _G["P"], _G["N"], _G["B"], _G["H"] = d["P"], d["N"], d["B"], d["H"]
    _G["tree"] = cKDTree(d["P"][:, :2])
    _G["dsm"] = Grid.load(dsm_file)
    _G["conv"] = conv


def occluded(P, cam, dsm, margin=0.4, n=24, skip=1.2):
    d = P - cam
    L = np.linalg.norm(d[:, :2], axis=1)
    occ = np.zeros(len(P), bool)
    for t in np.linspace(0.04, 1.0, n):
        Q = cam + d * t
        near_end = L * (1 - t) < skip
        z = dsm.sample(Q[:, 0], Q[:, 1])
        occ |= (z > Q[:, 2] + margin) & ~near_end
    return occ


def measure(rec):
    """Colours of the facade points one panorama sees: (building index, rgb (k, 3), height above ground)."""
    f = os.path.join(PANO, rec["id"] + ".jpg")
    if not os.path.exists(f):
        return None
    P, N, B, Hg, tree, dsm = _G["P"], _G["N"], _G["B"], _G["H"], _G["tree"], _G["dsm"]
    x, y = rec["x"], rec["y"]
    idx = np.array(tree.query_ball_point([x, y], MAXD), np.int64)
    if not len(idx):
        return None
    cam_z = rec["ground"] + CAM_H
    cam = np.array([x, y, cam_z])
    Q, Nq = P[idx], N[idx]
    v = cam - Q
    dist = np.linalg.norm(v, axis=1)
    facing = (v * Nq).sum(1) > 0.35 * dist
    ok = facing & (dist > MIND) & (dist < MAXD)
    if not ok.any():
        return None
    idx, Q, dist = idx[ok], Q[ok], dist[ok]
    occ = occluded(Q, cam, dsm)
    idx, Q = idx[~occ], Q[~occ]
    if not len(idx):
        return None
    heading = rec["heading_deg"] + camera.grid_convergence(rec["lat"], rec["lon"])
    R = camera.attitude_matrix(heading, rec.get("pitch_deg", 0.0), rec.get("roll_deg", 0.0), _G["conv"])
    img = np.asarray(Image.open(f).convert("RGB"), np.float32) / 255.0
    Hh, Ww = img.shape[:2]
    dc = (Q - cam) @ R
    u, vv = camera.dir_cam_to_pixel(dc, Ww, Hh)
    lat = np.degrees(np.arcsin(np.clip(dc[:, 2] / np.linalg.norm(dc, axis=1), -1, 1)))
    good = lat > -30.0
    idx, u, vv = idx[good], u[good], vv[good]
    if not len(idx):
        return None
    rgb = np.stack([map_coordinates(img[..., c], [vv, u % Ww], order=1, mode="nearest") for c in range(3)], 1)
    return B[idx], rgb.astype(np.float32), Hg[idx].astype(np.float32)


def is_plaster(rgb):
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    mx, mn = rgb.max(1), rgb.min(1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    veg = (g > r + 0.02) & (g > b + 0.01) & (sat > 0.10)
    sky = (b > r + 0.06) & (mx > 0.55)
    return ~veg & ~sky & (mx > 0.28) & (mx < 0.985)


def shutter_class(rgb, plaster):
    """Colour class of the pixels that look like shutters (apart from the plaster)."""
    far = np.linalg.norm(rgb - plaster[None], axis=1) > 0.16
    hsv = np.array([colorsys.rgb_to_hsv(*c) for c in rgb[far]]) if far.any() else np.zeros((0, 3))
    if not len(hsv):
        return None, 0.0
    h, s, v = hsv[:, 0] * 360, hsv[:, 1], hsv[:, 2]
    cls = {
        "verde": ((h > 85) & (h < 170) & (s > 0.18) & (v > 0.25) & (v < 0.65)).sum(),
        "verde_scuro": ((h > 85) & (h < 170) & (s > 0.18) & (v <= 0.25) & (v > 0.08)).sum(),
        "marrone": ((h > 12) & (h < 45) & (s > 0.3) & (v > 0.12) & (v < 0.45)).sum(),
        "legno": ((h > 20) & (h < 45) & (s > 0.35) & (v >= 0.45) & (v < 0.7)).sum(),
        "bordeaux": (((h < 12) | (h > 340)) & (s > 0.35) & (v > 0.12) & (v < 0.5)).sum(),
        "grigio": ((s < 0.08) & (v > 0.3) & (v < 0.65) & (np.abs(v - plaster.max()) > 0.2)).sum(),
    }
    k = max(cls, key=cls.get)
    return k, cls[k] / max(len(rgb), 1)


def main(summary_only=False):
    import buildings_mesh
    blds = buildings_mesh.load_buildings()
    obs_f = os.path.join(WORK, "sv", "facade_obs.pkl")
    if summary_only and os.path.exists(obs_f):         # the projections of a previous run
        per = pickle.load(open(obs_f, "rb"))
        out = summarise(per, blds)
        json.dump(out, open(OUT, "w"), separators=(",", ":"))
        print("buildings measured", len(out))
        return
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    pf = os.path.join(WORK, "sv", "facade_points.npz")
    if not os.path.exists(pf):
        P, N, B, H = facade_points(blds, dtm)
        np.savez(pf, P=P, N=N, B=B, H=H)
        print("facade points", len(P), flush=True)
    sel = json.load(open(os.path.join(WORK, "sv", "selected.json")))
    sel = [p for p in sel if os.path.exists(os.path.join(PANO, p["id"] + ".jpg"))]
    for p in sel:
        p["ground"] = float(dtm.sample(np.array([p["x"]]), np.array([p["y"]]))[0])
    conv = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                                       "attitude_convention.json")))
    print(len(sel), "panoramas", flush=True)
    per = {}
    with ProcessPoolExecutor(int(os.environ.get("SV_PROCS", "3")), initializer=_init, initargs=(pf, os.path.join(WORK, "dsm05.npz"), conv)) as ex:
        for k, (rec, res) in enumerate(zip(sel, ex.map(measure, sel, chunksize=8))):
            if res is not None:
                Bk, rgb, hg = res
                for bi in np.unique(Bk):
                    m = Bk == bi
                    per.setdefault(int(bi), []).append((rec["id"], (rec.get("date") or "")[:4], rgb[m], hg[m]))
            if k % 500 == 0:
                print("  %d/%d panoramas, %d buildings seen" % (k + 1, len(sel), len(per)), flush=True)
    import pickle as _pk
    # the observations by building id (the list of buildings may change: missing_buildings.py)
    per = {blds[int(k)]["uuid"]: v for k, v in per.items()}
    _pk.dump({k: [(o[0], o[1], o[2].astype(np.float16), o[3].astype(np.float16)) for o in v] for k, v in per.items()},
             open(os.path.join(WORK, "sv", "facade_obs.pkl"), "wb"))
    out = summarise(per, blds)
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    from collections import Counter
    print("buildings measured", len(out), "of", len(blds), "shutters",
          Counter(r.get("shutter") for r in out.values()).most_common())


def summarise(per, blds):
    """{uuid: record} from the observations {uuid: [(pano, year, rgb, height above ground)]}."""
    out = {}
    known = {b["uuid"] for b in blds}
    for uid, obs in per.items():
        if uid not in known:
            continue
        rgb = np.concatenate([o[2] for o in obs]).astype(np.float32)
        hg = np.concatenate([o[3] for o in obs]).astype(np.float32)
        keep = is_plaster(rgb)
        n = int(keep.sum())
        npan = len({o[0] for o in obs})
        if n < MIN_N or (npan < MIN_PANOS and n < 2 * MIN_N):
            continue
        # the plaster is the brightest large part of a facade: windows, shutters, the plinth and the shade
        # of the eaves are darker. The lit plaster: the pixels in the upper part of the luminance range
        px = rgb[keep]
        lum = px @ np.array([0.2126, 0.7152, 0.0722])
        lit = lum >= np.percentile(lum, 60)
        med = np.median(px[lit], 0)
        sh, frac = shutter_class(rgb[hg > 2.0], med)
        rec = {"rgb": [round(float(c), 3) for c in med], "n": n, "panos": npan,
               "year": max(o[1] for o in obs)}
        if sh is not None and frac >= 0.03:
            rec["shutter"], rec["shutter_frac"] = sh, round(float(frac), 3)
        out[uid] = rec
    return out


if __name__ == "__main__":
    main(summary_only="--summary" in sys.argv)
