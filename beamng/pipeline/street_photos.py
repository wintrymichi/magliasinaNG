"""The street photos of the catalogue as posed cameras (v3.0.40): the first pose each service gives, and how much
to trust it, for the fit to the scene (street_pose.py).

- Mapillary: the camera of its own reconstruction (OpenSfM): a 360 degree panorama (spherical, equirectangular) or a
  perspective camera with its focal length and radial distortion (camera_parameters: focal of the larger side, k1,
  k2), the rotation (computed_rotation, world east-north-up -> camera) and the position of the reconstruction.
  Without a reconstruction: the GPS and the compass, the camera level.
- Panoramax: the GPS, the compass (view:azimuth) and the field of view of the phone, the camera level.
The height of the camera is unknown (a car roof, a dashboard, a bicycle, a walker): MOUNT m over the bare ground to
start with; the fit finds it.

    camera_of(p, W, H, ground) -> (Camera, trust) or None, trust = {"prior": (m, deg), "heading_search": deg}
"""
import math
import numpy as np
from config import wgs_to_local
import camera as cam_mod
import street_camera as sc

MOUNT = 2.0


def camera_of(p, W, H, ground):
    """The first pose of photo p (an entry of the catalogue) for an image of W x H pixels."""
    x, y = wgs_to_local(p["lat"], p["lon"])
    z = float(ground(np.array([x]), np.array([y]))[0]) + MOUNT
    pos = np.array([x, y, z])
    conv = cam_mod.grid_convergence(p["lat"], p["lon"])
    kind = (p.get("camera") or "").lower()
    pano = bool(p.get("pano")) or kind in ("spherical", "equirectangular")
    if p["src"] == "mapillary":
        rot = p.get("rotation")
        computed = bool(p.get("computed")) and rot is not None
        if pano:
            model = dict(kind="equirect")
        elif kind in ("perspective", "unknown", "") and p.get("cam_params"):
            f, k1, k2 = (list(p["cam_params"]) + [0.0, 0.0, 0.0])[:3]
            if not f or f <= 0:
                return None
            model = dict(kind="persp", f=float(f), k1=float(k1 or 0.0), k2=float(k2 or 0.0))
        else:
            return None                      # fisheye and cameras without a calibration
        if computed:
            R = sc.from_opensfm(rot, conv)
            trust = {"prior": (4.0, 6.0), "heading_search": 0.0}
        else:
            if p.get("angle") is None:
                return None
            R = sc.attitude(float(p["angle"]) + conv, 0.0, 0.0)
            trust = {"prior": (8.0, 25.0), "heading_search": 25.0}
    elif p["src"] == "panoramax":
        if pano or p.get("angle") is None:
            return None
        fov = p.get("fov") or 70.0
        f = 0.5 * W / math.tan(math.radians(float(fov)) / 2) / max(W, H)
        model = dict(kind="persp", f=f, k1=0.0, k2=0.0)
        R = sc.attitude(float(p["angle"]) + conv, 0.0, 0.0)
        trust = {"prior": (8.0, 25.0), "heading_search": 25.0}
    else:
        return None
    c = sc.Camera(model["kind"], W, H, pos, R, f=model.get("f"), k1=model.get("k1", 0.0), k2=model.get("k2", 0.0))
    return c, trust
