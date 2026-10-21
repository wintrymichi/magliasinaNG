"""Camera models of the street-level photos (v3.0.40): 360 degree panoramas and ordinary photos, posed in the local
frame of the map.

Camera frame: x = right, y = forward, z = up (the frame of camera.py). The rotation R takes camera directions to the
local frame (x = east, y = north of the LV95 grid, z = up); the attitude is a compass heading of the forward axis on
the grid (clockwise from grid north), a pitch (positive up) and a roll (positive: the right side goes down):
    R = Rz(-heading) @ Rx(pitch) @ Ry(roll)
- equirectangular (W x H, W = 2 H): column u, row v of the centre of a pixel
      lon = (u + 0.5) / W * 2 pi - pi  (0 straight ahead, positive to the right),  lat = pi/2 - (v + 0.5) / H * pi
- perspective (the OpenSfM model Mapillary uses): normalised image coordinates (u + 0.5 - W/2) / S, (v + 0.5 - H/2) / S
  with S = max(W, H), focal f (of S), radial distortion 1 + k1 r^2 + k2 r^4.
Mapillary gives its own reconstruction's rotation (angle-axis, OpenSfM: world east-north-up -> camera x right,
y down, z forward), turned here onto the grid (the meridian convergence of the place, camera.grid_convergence).
"""
import math
import numpy as np


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def attitude(heading_deg, pitch_deg=0.0, roll_deg=0.0):
    """Rotation camera -> local frame of a heading, pitch and roll (degrees)."""
    return rot_z(-math.radians(heading_deg)) @ rot_x(math.radians(pitch_deg)) @ rot_y(math.radians(roll_deg))


def angles_of(R):
    """(heading, pitch, roll) in degrees of a rotation built by attitude()."""
    f = R[:, 1]                                       # the forward axis in the world
    heading = math.degrees(math.atan2(f[0], f[1])) % 360.0
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, f[2]))))
    R1 = rot_x(-math.radians(pitch)) @ rot_z(math.radians(heading)) @ R
    roll = math.degrees(math.atan2(R1[0, 2], R1[0, 0]))
    return heading, pitch, roll


# OpenSfM camera (x right, y down, z forward) from this camera frame (x right, y forward, z up)
SFM_FROM_CAM = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)


def rodrigues(r):
    r = np.asarray(r, float)
    t = float(np.linalg.norm(r))
    if t < 1e-12:
        return np.eye(3)
    k = r / t
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def from_opensfm(rotation, convergence_deg):
    """Rotation camera -> local grid frame of an OpenSfM angle-axis rotation (world ENU -> OpenSfM camera)."""
    R_cw = rodrigues(rotation).T                      # OpenSfM camera -> ENU
    return rot_z(-math.radians(convergence_deg)) @ R_cw @ SFM_FROM_CAM


class Camera:
    """A posed camera. kind 'equirect' or 'persp'; pos (3,) in the local frame; R camera -> local frame."""

    def __init__(self, kind, W, H, pos, R, f=None, k1=0.0, k2=0.0):
        self.kind, self.W, self.H = kind, int(W), int(H)
        self.pos = np.asarray(pos, float)
        self.R = np.asarray(R, float)
        self.f, self.k1, self.k2 = f, k1, k2
        self.S = float(max(W, H))

    def copy(self, pos=None, R=None):
        return Camera(self.kind, self.W, self.H, self.pos if pos is None else pos, self.R if R is None else R,
                      self.f, self.k1, self.k2)

    # -------------------------------------------------------------- camera directions <-> pixels
    def cam_dirs(self, u, v):
        u, v = np.asarray(u, float), np.asarray(v, float)
        if self.kind == "equirect":
            lon = (u + 0.5) / self.W * 2 * np.pi - np.pi
            lat = np.pi / 2 - (v + 0.5) / self.H * np.pi
            cl = np.cos(lat)
            return np.stack([cl * np.sin(lon), cl * np.cos(lon), np.sin(lat)], -1)
        xd = (u + 0.5 - self.W / 2) / self.S / self.f
        yd = (v + 0.5 - self.H / 2) / self.S / self.f
        x, y = xd.copy(), yd.copy()
        for _ in range(8):                            # undistort (fixed point)
            r2 = x * x + y * y
            d = 1 + self.k1 * r2 + self.k2 * r2 * r2
            x, y = xd / d, yd / d
        d = np.stack([x, np.ones_like(x), -y], -1)
        return d / np.linalg.norm(d, axis=-1, keepdims=True)

    def cam_to_pixel(self, d):
        """Pixel (u, v) of camera directions d (..., 3) and whether the camera sees them."""
        d = np.asarray(d, float)
        if self.kind == "equirect":
            lon = np.arctan2(d[..., 0], d[..., 1])
            lat = np.arcsin(np.clip(d[..., 2] / np.maximum(np.linalg.norm(d, axis=-1), 1e-12), -1, 1))
            u = (lon + np.pi) / (2 * np.pi) * self.W - 0.5
            v = (np.pi / 2 - lat) / np.pi * self.H - 0.5
            return u, v, np.ones(u.shape, bool)
        fw = d[..., 1]
        ok = fw > 1e-6
        fs = np.where(ok, fw, 1.0)
        x, y = d[..., 0] / fs, -d[..., 2] / fs
        r2 = x * x + y * y
        k = 1 + self.k1 * r2 + self.k2 * r2 * r2
        u = self.f * k * x * self.S + self.W / 2 - 0.5
        v = self.f * k * y * self.S + self.H / 2 - 0.5
        ok &= (u >= -0.5) & (u < self.W - 0.5) & (v >= -0.5) & (v < self.H - 0.5) & (r2 < 4.0)
        return u, v, ok

    # -------------------------------------------------------------- world
    def dirs(self, u, v):
        """World directions (unit) of pixels."""
        return self.cam_dirs(u, v) @ self.R.T

    def project(self, P):
        """Pixel (u, v), distance and visibility of world points P (..., 3)."""
        D = np.asarray(P, float) - self.pos
        dist = np.linalg.norm(D, axis=-1)
        u, v, ok = self.cam_to_pixel(D @ self.R)
        return u, v, dist, ok & (dist > 0.3)

    def deg_per_px(self):
        return 360.0 / self.W if self.kind == "equirect" else math.degrees(1.0 / (self.f * self.S))
