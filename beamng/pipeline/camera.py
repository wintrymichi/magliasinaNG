"""Equirectangular panorama camera model.

Camera frame: x = right, y = forward (image centre column), z = up.
An image pixel (u, v) of a W x H equirectangular panorama maps to
    lon = (u + 0.5) / W * 2pi - pi       (0 at the centre column, positive to the right)
    lat = pi/2 - (v + 0.5) / H * pi      (positive up)
    d_cam = (cos(lat) sin(lon), cos(lat) cos(lon), sin(lat))
World frame (local map): x = east, y = north, z = up.
    d_world = R @ d_cam,  R = Rz(-heading_grid) @ Rx(pitch) @ Ry(roll)
heading_grid is the compass heading of the centre column converted to grid
north (LV95 meridian convergence); pitch/roll follow the sign convention fixed
by calibrate_attitude.py (stored in work/attitude_convention.json).
"""
import json, math, os
import numpy as np
from config import WORK, wgs_to_local, lv95_to_local, wgs_to_lv95


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def grid_convergence(lat, lon):
    """Angle (deg) to add to a true bearing to get the LV95 grid bearing."""
    e1, n1 = wgs_to_lv95(lat, lon)
    e2, n2 = wgs_to_lv95(lat + 1e-4, lon)
    return math.degrees(math.atan2(e2 - e1, n2 - n1))


def attitude_matrix(heading_grid_deg, pitch_deg, roll_deg, conv=None):
    """Rotation camera -> world. conv = dict(sp, sr, order) chosen by calibration."""
    if conv is None:
        conv = load_convention()
    h = math.radians(heading_grid_deg)
    p = math.radians(pitch_deg) * conv["sp"]
    r = math.radians(roll_deg) * conv["sr"]
    Rh = rot_z(-h)
    if conv["order"] == "pr":
        return Rh @ rot_x(p) @ rot_y(r)
    return Rh @ rot_y(r) @ rot_x(p)


def load_convention():
    f = os.path.join(WORK, "attitude_convention.json")
    if os.path.exists(f):
        return json.load(open(f))
    return {"sp": 1, "sr": 1, "order": "pr"}


def pixel_to_dir_cam(u, v, W, H):
    lon = (np.asarray(u) + 0.5) / W * 2 * np.pi - np.pi
    lat = np.pi / 2 - (np.asarray(v) + 0.5) / H * np.pi
    cl = np.cos(lat)
    return np.stack([cl * np.sin(lon), cl * np.cos(lon), np.sin(lat)], -1)


def dir_cam_to_pixel(d, W, H):
    d = np.asarray(d)
    lon = np.arctan2(d[..., 0], d[..., 1])
    lat = np.arcsin(np.clip(d[..., 2] / np.linalg.norm(d, axis=-1), -1, 1))
    u = (lon + np.pi) / (2 * np.pi) * W - 0.5
    v = (np.pi / 2 - lat) / np.pi * H - 0.5
    return u, v


class Pano:
    def __init__(self, rec, W=8192, H=4096, conv=None, pose=None):
        self.rec, self.W, self.H = rec, W, H
        self.id, self.index = rec["id"], rec["index"]
        x, y = wgs_to_local(rec["lat"], rec["lon"])
        self.conv_deg = grid_convergence(rec["lat"], rec["lon"])
        self.pos = np.array([x, y, rec["elevation"]], float)
        self.heading = rec["heading_deg"] + self.conv_deg
        self.pitch, self.roll = rec["pitch_deg"], rec["roll_deg"]
        if pose is not None:          # refined pose (local frame) overrides the raw metadata
            self.pos = np.array(pose["pos"], float)
            self.heading, self.pitch, self.roll = pose["heading"], pose["pitch"], pose["roll"]
        self.conv = conv or load_convention()
        self.R = attitude_matrix(self.heading, self.pitch, self.roll, self.conv)

    def pixel_to_world_dir(self, u, v):
        return pixel_to_dir_cam(u, v, self.W, self.H) @ self.R.T

    def world_to_pixel(self, P):
        d = (np.asarray(P) - self.pos) @ self.R          # world -> camera (R orthonormal)
        return dir_cam_to_pixel(d, self.W, self.H)

    def dir_to_pixel(self, d_world):
        return dir_cam_to_pixel(np.asarray(d_world) @ self.R, self.W, self.H)


# ---------------------------------------------------------------- dataset views
VIEW_W, VIEW_H, VIEW_FOV = 1600, 1200, 90.0
VIEW_REL = {"fwd": 0, "fwd_r": 45, "right": 90, "back_r": 135, "back": 180, "back_l": 225, "left": 270, "fwd_l": 315}


def view_img_yaw(rec, rel_deg):
    """Yaw of a dataset view relative to the panorama centre column, exactly as sv_capture.py made it."""
    world_yaw = (rec["road_bearing_deg"] + rel_deg) % 360
    return (world_yaw - rec["heading_deg"] + 540) % 360 - 180


def _view_rot(img_yaw_deg, pitch_deg):
    p, y = -math.radians(pitch_deg), math.radians(img_yaw_deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    return Ry @ Rx


def pano_lonlat_to_view(lon, lat, img_yaw_deg, pitch_deg, w=VIEW_W, h=VIEW_H, fov=VIEW_FOV):
    """Panorama image angles -> pixel (col,row) in a dataset perspective view; z>0 mask."""
    d_img = np.stack([np.cos(lat) * np.sin(lon), -np.sin(lat), np.cos(lat) * np.cos(lon)], -1)
    d_view = d_img @ _view_rot(img_yaw_deg, pitch_deg)
    f = (w / 2) / math.tan(math.radians(fov) / 2)
    z = d_view[..., 2]
    zs = np.where(z > 1e-6, z, np.nan)
    col = f * d_view[..., 0] / zs + w / 2 - 0.5
    row = f * d_view[..., 1] / zs + h / 2 - 0.5
    return col, row, z > 1e-6


def view_pixel_to_pano_lonlat(col, row, img_yaw_deg, pitch_deg, w=VIEW_W, h=VIEW_H, fov=VIEW_FOV):
    f = (w / 2) / math.tan(math.radians(fov) / 2)
    d = np.stack([np.asarray(col) - w / 2 + 0.5, np.asarray(row) - h / 2 + 0.5, np.full(np.shape(col), f)], -1)
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    d = d @ _view_rot(img_yaw_deg, pitch_deg).T
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(-d[..., 1], -1, 1))
    return lon, lat


def world_to_view(P, pos, R, rec, rel_deg, pitch_deg):
    """World points -> pixel in dataset view (calibrated pose pos/R of the panorama)."""
    dc = (np.asarray(P, float) - np.asarray(pos, float)) @ np.asarray(R)
    lon = np.arctan2(dc[..., 0], dc[..., 1])
    lat = np.arcsin(np.clip(dc[..., 2] / np.linalg.norm(dc, axis=-1), -1, 1))
    return pano_lonlat_to_view(lon, lat, view_img_yaw(rec, rel_deg), pitch_deg)


def view_pixel_to_world_dir(col, row, R, rec, rel_deg, pitch_deg):
    lon, lat = view_pixel_to_pano_lonlat(col, row, view_img_yaw(rec, rel_deg), pitch_deg)
    cl = np.cos(lat)
    d_cam = np.stack([cl * np.sin(lon), cl * np.cos(lon), np.sin(lat)], -1)
    return d_cam @ np.asarray(R).T
