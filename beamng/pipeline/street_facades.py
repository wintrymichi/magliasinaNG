"""The facades seen in the street photos (v3.0.40): every planar facade of the buildings of swissBUILDINGS3D that a
photo with a fitted pose (street_pose.py) sees, resampled onto the facade's own plane: a rectified image with RES m
per pixel, u along the wall (the axis of facades.py: a = (-n_y, n_x, 0) for the outward normal n), z up (absolute
height), so that what is found in it (windows, doors, shop fronts) has the coordinates the facade layout uses.

A pixel of the facade counts in a photo when the camera is in front of the facade, the label panorama of the scene
(street_render.py) shows this building in that direction (another building, a tree, a wall or the ground in between
hide it) and the photo's own segmentation sees a building there (not a car, a person, a pole or a plant in front).
Its weight is the detail the photo has there: the obliquity (cosine of the angle to the facade's normal) over the size
of a photo pixel on the wall. The views of a facade are fused per pixel (weighted mean of the best ones).

    facades_of(b) -> [Facade]
    observe(cam, pano, rgb, lab, bi, f) -> (image (h, w, 3) uint8, weight (h, w) float32) or None
    fuse([(image, weight), ...]) -> (image, weight)
"""
import math
import numpy as np
import shapely
import street_render as sr

RES = 0.04                    # m per pixel of the rectified facades
FRONT = 0.03                  # m in front of the wall: the points sampled
OWN = 1.6                     # m: the building itself may stand this much in front of a facade in the scene (eaves)
MIN_COS = 0.17                # facades seen at more than ~80 degrees from their normal are left out
MAX_DIST = 60.0               # m


class Facade:
    """A planar facade: wall triangles, outward normal n, axis a, a point o of its plane, polygon F in (u, z)."""

    def __init__(self, uuid, k, n, a, o, F):
        self.uuid, self.k = uuid, k
        self.n, self.a, self.o, self.F = n, a, o, F
        self.u0, self.z0, self.u1, self.z1 = F.bounds

    @property
    def key(self):
        """A key that finds the facade again in the layout: building, azimuth of the normal, offset of the plane."""
        az = math.degrees(math.atan2(self.n[0], self.n[1])) % 360
        return f"{self.uuid}|{az:.0f}|{float(self.o @ self.n):.1f}"

    def grid(self, res=RES):
        """(U, Z) of the pixel centres (rows from the top) and the mask of the pixels inside the facade."""
        us = np.arange(self.u0 + res / 2, self.u1, res)
        zs = np.arange(self.z1 - res / 2, self.z0, -res)
        U, Z = np.meshgrid(us, zs)
        return U, Z, shapely.contains_xy(self.F, U, Z)

    def points(self, U, Z, front=FRONT):
        return (self.o[None, None, :] + U[..., None] * self.a[None, None, :]
                + Z[..., None] * np.array([0, 0, 1.0]) + front * self.n[None, None, :])


def facades_of(b, min_width=1.4):
    """The planar facades of a building (record of buildings.pkl), outward."""
    import buildings_mesh
    import facades
    import texturing
    walls = buildings_mesh.orient(b)["walls"]
    out = []
    if not len(walls):
        return out
    for k, (idx, n, d0) in enumerate(texturing.facade_groups(walls)):
        n = np.array([n[0], n[1], 0.0])
        n /= max(np.linalg.norm(n), 1e-9)
        a = np.array([-n[1], n[0], 0.0])
        F = facades.facade_polygon(walls[idx], a)
        if F is None:
            continue
        if F.bounds[2] - F.bounds[0] < min_width or F.bounds[3] - F.bounds[1] < 1.5:
            continue
        out.append(Facade(b["uuid"], k, n, a, n * d0, F))
    return out


def observe(cam, pano, rgb, lab, bi, f, res=RES, max_dist=MAX_DIST):
    """The facade f of the building with scene index bi as the photo (rgb (H, W, 3), its label map lab at any size
    with the photo's aspect) shows it: (image uint8 (h, w, 3), weight float32 (h, w)); None if it does not."""
    import cv2
    U, Z, inside = f.grid(res)
    P = f.points(U, Z)
    V = P - cam.pos
    dist = np.linalg.norm(V, axis=-1)
    cosv = -(V @ f.n) / np.maximum(dist, 1e-9)              # the camera in front: the ray goes into the wall
    ok = inside & (cosv > MIN_COS) & (dist < max_dist) & (dist > 1.0)
    if ok.sum() < 200:
        return None
    # what the scene shows in each direction: this building (its own eaves may stand in front), or something nearer
    L, B, D = pano.lookup(V)
    hidden = (B != bi) & (D < dist - 0.5 - 0.02 * dist)         # another building, a tree, the ground nearer
    hidden |= (B == bi) & (D < dist - OWN - 0.03 * dist)        # another wing of the same building in front
    ok &= ~hidden
    if ok.sum() < 200:
        return None
    u, v, vis = cam.cam_to_pixel(V @ cam.R)
    ok &= vis & (u >= 0) & (u <= cam.W - 1) & (v >= 0) & (v <= cam.H - 1)
    # the photo's own segmentation: a building there
    sx, sy = lab.shape[1] / cam.W, lab.shape[0] / cam.H
    li = lab[np.clip((v * sy).astype(int), 0, lab.shape[0] - 1), np.clip((u * sx).astype(int), 0, lab.shape[1] - 1)]
    ok &= li == sr.BUILDING
    if ok.sum() < 200:
        return None
    ih, iw = rgb.shape[:2]
    mu = np.where(ok, u * iw / cam.W, -10).astype(np.float32)
    mv = np.where(ok, v * ih / cam.H, -10).astype(np.float32)
    img = cv2.remap(rgb, mu, mv, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # detail: metres of wall per photo pixel (the pixel's angle times the distance, stretched by the obliquity)
    px = math.radians(cam.deg_per_px()) * cam.W / iw
    m_per_px = px * dist / np.maximum(cosv, 1e-3)
    w = np.where(ok, cosv * np.minimum(1.0, res / np.maximum(m_per_px, 1e-6)), 0.0).astype(np.float32)
    return img, w


def fuse(views, keep=3):
    """Per pixel the weighted mean of the `keep` best views (a sharp, frontal one wins over many oblique ones)."""
    if not views:
        return None
    imgs = np.stack([v[0] for v in views]).astype(np.float32)
    W = np.stack([v[1] for v in views])
    if len(views) > keep:
        thr = -np.sort(-W, axis=0)[keep - 1]
        W = np.where(W >= thr[None], W, 0.0)
    tot = W.sum(0)
    img = (imgs * W[..., None]).sum(0) / np.maximum(tot, 1e-6)[..., None]
    return np.clip(img, 0, 255).astype(np.uint8), tot.astype(np.float32)
