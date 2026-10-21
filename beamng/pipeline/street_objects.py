"""Street furniture seen in the open street photos (v3.0.40): benches, litter bins, letter boxes, fire hydrants,
junction boxes, bike racks and phone booths, where the photos with a fitted pose (street_pose.py) and their
segmentation (street_segment.py, classes of Mapillary Vistas) show them. The step of objects.py (the Street View route
of v2) for every photo of the area.

Every connected region of one of these classes whose lowest pixels stand on the ground (a ground class just below
them) is cast from the camera onto the bare ground: the foot of the object. The observations of several photos
within RADIUS m of each other and of the same class are one object (at least MIN_PHOTOS photos see it), at the mean
of their feet weighted by the nearness of the camera.

    observe(cam, classmap, names, ground, photo_id) -> [observation]
    cluster(observations) -> [{cls, x, y, n, width}]
"""
import numpy as np

FURNITURE = {"bench": "bench", "trash can": "trash_can", "mailbox": "mailbox", "fire hydrant": "hydrant",
             "junction box": "junction_box", "bike rack": "bike_rack", "phone booth": "booth"}
RADIUS = 0.8                  # m: observations of one object
MIN_PHOTOS = 2
MIN_AREA = 60                 # px of a region in a photo of 2048 px
NEAR, FAR = 1.5, 25.0         # m from the camera


def ground_hit(pos, d, ground, far=FAR, step=0.1):
    """The point where the ray pos + t d meets the bare ground (None within far m)."""
    t = np.arange(0.3, far, step)
    P = pos[None, :] + t[:, None] * d[None, :]
    g = ground(P[:, 0], P[:, 1])
    below = np.nonzero(P[:, 2] <= g)[0]
    if not len(below):
        return None
    i = below[0]
    if i == 0:
        return P[0]
    # between the last sample above and the first below
    a = P[i - 1, 2] - g[i - 1]
    b = P[i, 2] - g[i]
    s = a / max(a - b, 1e-9)
    return P[i - 1] + s * (P[i] - P[i - 1])


def observe(cam, classmap, names, ground, photo_id):
    """The feet of the furniture a photo shows: [{cls, x, y, dist, width, photo}]."""
    import cv2
    import street_segment
    ids = {i: FURNITURE[n.lower()] for i, n in names.items() if n.lower() in FURNITURE}
    gnd = np.array([i for i, n in names.items() if n.lower() in street_segment.GROUND_N], int)
    if not ids:
        return []
    H, W = classmap.shape
    sx, sy = cam.W / W, cam.H / H
    out = []
    for cid, cls in ids.items():
        m = (classmap == cid).astype(np.uint8)
        if not m.any():
            continue
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for k in range(1, n):
            x0, y0, w, h, area = st[k]
            if area < MIN_AREA * (W / 2048.0) ** 2 or y0 + h >= H - 1:
                continue
            if cam.kind != "equirect" and (x0 <= 1 or x0 + w >= W - 1):
                continue
            ys, xs = np.nonzero(lab[y0:y0 + h, x0:x0 + w] == k)
            ys, xs = ys + y0, xs + x0
            ybot = int(ys.max())
            xb = int(np.median(xs[ys >= ybot - 3]))
            below = classmap[min(H - 1, ybot + 3), xb]
            if below not in gnd:
                continue
            d = cam.dirs(np.array([(xb + 0.5) * sx - 0.5]), np.array([(ybot + 0.5) * sy - 0.5]))[0]
            hit = ground_hit(cam.pos, d, ground)
            if hit is None:
                continue
            dist = float(np.hypot(*(hit[:2] - cam.pos[:2])))
            if not NEAR <= dist <= FAR:
                continue
            width = float(np.radians(cam.deg_per_px()) * w * sx * dist)
            out.append({"cls": cls, "x": float(hit[0]), "y": float(hit[1]), "dist": dist, "width": width,
                        "photo": photo_id})
    return out


def cluster(obs, radius=RADIUS, min_photos=MIN_PHOTOS):
    """One object per group of observations of the same class within radius m, seen by min_photos photos."""
    from scipy.spatial import cKDTree
    if not obs:
        return []
    P = np.array([[o["x"], o["y"]] for o in obs])
    tree = cKDTree(P)
    used = np.zeros(len(obs), bool)
    out = []
    for i in np.argsort([o["dist"] for o in obs]):
        if used[i]:
            continue
        ii = [j for j in tree.query_ball_point(P[i], radius) if not used[j] and obs[j]["cls"] == obs[i]["cls"]]
        if len({obs[j]["photo"] for j in ii}) < min_photos:
            continue
        used[ii] = True
        w = np.array([1.0 / max(obs[j]["dist"], 1.0) for j in ii])
        out.append({"cls": obs[i]["cls"], "x": round(float(np.average(P[ii, 0], weights=w)), 2),
                    "y": round(float(np.average(P[ii, 1], weights=w)), 2), "n": len(ii),
                    "photos": sorted({obs[j]["photo"] for j in ii}),
                    "width": round(float(np.median([obs[j]["width"] for j in ii])), 2)})
    return out
