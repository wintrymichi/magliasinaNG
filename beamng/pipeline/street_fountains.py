"""The village fountains in the street photos (v3.0.40): whether the fountains and drinking water points of OSM
(amenity=fountain, amenity=drinking_water) are a stone fountain with a basin, and how big it is.

Every photo with a fitted pose (street_pose.py) that sees such a point within NEAR-FAR m is resampled onto a vertical
window across the line of sight through it (WIDTH x HEIGHT m from the ground, RES m per pixel, like the rectified
facades of street_facades.py): an object there has its size in metres in the window. The open-vocabulary detector
of street_openings.py (Grounding DINO) looks in it for a fountain, a stone basin or a trough; a box whose foot is on
the ground and whose middle is within SLACK m of the point is the fountain, seen from that side. The photos that see
the point vote; the boxes give its width (the widest side seen) and the height of the basin.

    points(rect) -> [{id, x, y, kind, tags}] of OSM in the local rectangle
    window(cam, pano, rgb, x, y, z) -> (image, seen mask, plane axis) or None
    look(cam, pano, rgb, pts, ground) -> [{id, photo, dist, found, width, height, du, score}]
    gather(observations) -> {id: {found, seen, width, height, dx, dy}}
"""
import math
import numpy as np

WIDTH, HEIGHT = 6.0, 3.0      # m: the window around a point (OSM places a fountain within a few metres)
BELOW = 0.4                   # m of the window under the ground (the ground at the point is not exact)
RES = 0.02                    # m per pixel of the window
NEAR, FAR = 2.5, 25.0         # m from the camera
SLACK = 2.0                   # m from the point: the middle of a box that is this fountain
PHRASES = ("fountain", "stone basin", "water trough")
SIZES = (0.4, 4.5, 0.3, 2.5)  # m: least and most width, least and most height of a box that is a fountain


def points(rect):
    """The fountains and drinking water points of the pinned OSM extract in the local rectangle (x0, y0, x1, y1)."""
    import osm
    _, nodes = osm.load()
    return [{"id": n["id"], "x": n["x"], "y": n["y"], "kind": n["tags"]["amenity"], "tags": n["tags"]}
            for n in nodes if n["tags"].get("amenity") in ("fountain", "drinking_water")
            and rect[0] <= n["x"] <= rect[2] and rect[1] <= n["y"] <= rect[3]]


def window(cam, pano, rgb, x, y, z, res=RES):
    """The photo resampled onto the vertical window through (x, y) across the line of sight, z the ground there:
    (image (h, w, 3) uint8, seen (h, w) bool, axis a (3,)); None where the camera does not see it."""
    import cv2
    to = np.array([cam.pos[0] - x, cam.pos[1] - y])
    dh = float(np.hypot(*to))
    if not NEAR <= dh <= FAR:
        return None
    n = np.array([to[0] / dh, to[1] / dh, 0.0])
    a = np.array([-n[1], n[0], 0.0])
    us = np.arange(-WIDTH / 2 + res / 2, WIDTH / 2, res)
    zs = np.arange(z + HEIGHT - res / 2, z - BELOW, -res)
    U, Z = np.meshgrid(us, zs)
    P = np.array([x, y, 0.0])[None, None, :] + U[..., None] * a[None, None, :] + Z[..., None] * np.array([0, 0, 1.0])
    V = P - cam.pos
    dist = np.linalg.norm(V, axis=-1)
    D = pano.lookup(V)[2]
    seen = D >= dist - 1.5                                   # nothing of the scene (a building, a hedge) much nearer
    u, v, vis = cam.cam_to_pixel(V @ cam.R)
    seen &= vis & (u >= 0) & (u <= cam.W - 1) & (v >= 0) & (v <= cam.H - 1)
    if seen.mean() < 0.5:
        return None
    ih, iw = rgb.shape[:2]
    mu = np.where(seen, u * iw / cam.W, -10).astype(np.float32)
    mv = np.where(seen, v * ih / cam.H, -10).astype(np.float32)
    img = cv2.remap(rgb, mu, mv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # a photo far away gives a blurred window: at most as sharp as the photo (its pixel on the window)
    px = math.radians(cam.deg_per_px()) * cam.W / iw * dh
    if px > 3 * res:
        k = int(round(px / res))
        img = cv2.resize(cv2.resize(img, (max(1, img.shape[1] // k), max(1, img.shape[0] // k)),
                                    interpolation=cv2.INTER_AREA), (img.shape[1], img.shape[0]),
                         interpolation=cv2.INTER_LINEAR)
    return img, seen, a


def look(cam, pano, rgb, pts, ground, photo_id="", save=None):
    """What one photo shows at the points: per point it sees, the best fountain box near it (found) or none; save: a
    folder for the windows with the boxes drawn (green the one taken, grey the others), for the review."""
    import street_openings as so
    out = []
    for p in pts:
        z = float(ground(np.array([p["x"]]), np.array([p["y"]]))[0])
        w = window(cam, pano, rgb, p["x"], p["y"], z)
        if w is None:
            continue
        img, seen, a = w
        best = None
        boxes = so._raw(img, PHRASES)
        for box, s, label in boxes:
            x0, y0, x1, y1 = box
            u0, u1 = -WIDTH / 2 + x0 * RES, -WIDTH / 2 + x1 * RES
            zt, zb = HEIGHT - y0 * RES, HEIGHT - y1 * RES           # over the ground at the point
            wd, ht = u1 - u0, zt - zb
            if not (SIZES[0] <= wd <= SIZES[1] and SIZES[2] <= ht <= SIZES[3]):
                continue
            if abs(0.5 * (u0 + u1)) > SLACK or not -BELOW <= zb <= 0.6:
                continue
            if best is None or s > best[0]:
                best = (s, wd, ht, 0.5 * (u0 + u1), box)
        dist = float(np.hypot(cam.pos[0] - p["x"], cam.pos[1] - p["y"]))
        if save:
            import os
            from PIL import Image, ImageDraw
            im = Image.fromarray(np.where(seen[..., None], img, 90).astype(np.uint8))
            d = ImageDraw.Draw(im)
            x = img.shape[1] / 2
            d.line((x, 0, x, img.shape[0]), fill=(255, 210, 0), width=1)          # the point of OSM
            zg = int(round(HEIGHT / RES))
            d.line((0, zg, img.shape[1], zg), fill=(255, 210, 0), width=1)        # the ground there
            for box, s, label in boxes:
                taken = best is not None and box is best[4]
                d.rectangle(tuple(float(v) for v in box), outline=(40, 255, 80) if taken else (170, 170, 170),
                            width=3 if taken else 1)
                d.text((float(box[0]) + 3, float(box[1]) + 2), "%s %.2f" % (label, s),
                       fill=(40, 255, 80) if taken else (200, 200, 200))
            im.save(os.path.join(save, "fontana_%s_%s.jpg" % (p["id"], photo_id)), quality=88)
        o = {"id": p["id"], "photo": photo_id, "dist": round(dist, 2), "found": best is not None}
        if best:
            o.update(score=round(best[0], 3), width=round(best[1], 2), height=round(best[2], 2),
                     du=round(best[3], 2), ax=[round(float(a[0]), 4), round(float(a[1]), 4)])
        out.append(o)
    return out


def gather(obs):
    """Per point: how many photos saw it and found the fountain, the widest box (the long side), the median height
    of the boxes and the mean shift of their middles from the point (x, y)."""
    by = {}
    for o in obs:
        by.setdefault(o["id"], []).append(o)
    out = {}
    for pid, lst in by.items():
        hits = [o for o in lst if o["found"]]
        r = {"seen": len(lst), "found": len(hits)}
        if hits:
            r["width"] = round(max(o["width"] for o in hits), 2)
            r["height"] = round(float(np.median([o["height"] for o in hits])), 2)
            d = np.mean([np.array(o["ax"]) * o["du"] for o in hits], axis=0)
            r["dx"], r["dy"] = round(float(d[0]), 2), round(float(d[1]), 2)
        out[str(pid)] = r
    return out
