"""The Street View side of the comparisons: for every `still` shot of shots.py, the panorama seen from the
same place, direction, pitch and field of view as the camera in the game, at the size of the game frames.
The panorama is reprojected through its own attitude (camera.Pano: heading, pitch and roll of the Google
car, refined poses of work/poses.json where the cantonal road has them), so its horizon is level like the
game's. Frames go to <out>/<shot>.png; they are a visual reference for the video only and never enter the
level or the repository. Needs the `streetlevel` package and access to Google's panorama tiles.
    python sv_frames.py <out dir> [width height]          (default 2560 x 1440)
"""
import gzip, json, math, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
from config import WORK                      # noqa: E402
from camera import Pano                      # noqa: E402
import shots as S                             # noqa: E402

FOV_VERTICAL = True


def view_dirs(yaw_deg, pitch_deg, hfov_deg, w, h):
    """World directions (x east, y north, z up) of every pixel of a pinhole camera."""
    f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    xs, ys = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
    yaw, pit = math.radians(yaw_deg), math.radians(pitch_deg)
    fwd = np.array([math.sin(yaw) * math.cos(pit), math.cos(yaw) * math.cos(pit), math.sin(pit)])
    right = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    up = np.cross(right, fwd)
    d = fwd * f + xs[..., None] * right - ys[..., None] * up
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def vfov_to_hfov(fov_v, w, h):
    return math.degrees(2 * math.atan(math.tan(math.radians(fov_v) / 2) * w / h))


def main():
    out = sys.argv[1]
    w, h = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (2560, 1440)
    os.makedirs(out, exist_ok=True)
    from streetlevel import streetview
    shots = [s for s in S.SHOTS if s["kind"] == "still"]
    S.resolve_panos(shots)
    recs = {p["id"]: p for p in json.load(gzip.open(os.path.join(WORK, "sv_coverage.json.gz")))["panoramas"]}
    poses = {}
    pf = os.path.join(WORK, "poses.json")
    if os.path.exists(pf):
        P = json.load(open(pf))
        poses = P if isinstance(P, dict) else {p["id"]: p for p in P if "id" in p}
    meta = {}
    for s in shots:
        rec = dict(recs[s["pano"]], index=0)
        pano = streetview.find_panorama_by_id(s["pano"])
        img = np.asarray(streetview.get_panorama(pano, zoom=4).convert("RGB"))
        H, W = img.shape[:2]
        P_ = Pano(rec, W=W, H=H)
        if "R" in poses.get(s["pano"], {}):          # refined attitude of the cantonal road's panoramas
            P_.R = np.array(poses[s["pano"]]["R"], float)
        # BeamNG's camera fov is taken as vertical (FOV_VERTICAL); check the match on the first scout frames
        hfov = vfov_to_hfov(s["fov"], w, h) if FOV_VERTICAL else s["fov"]
        u, v = P_.dir_to_pixel(view_dirs(s["yaw_deg"], s["pitch"], hfov, w, h))
        frame = np.stack([map_coordinates(img[..., c], [v, u % W], order=1, mode="wrap") for c in range(3)], -1)
        Image.fromarray(frame.astype(np.uint8)).save(os.path.join(out, s["name"] + ".png"))
        meta[s["name"]] = {"pano": s["pano"], "date": rec.get("date"), "yaw_deg": s["yaw_deg"], "hfov": round(hfov, 2)}
        print(s["name"], rec.get("date"), flush=True)
    json.dump(meta, open(os.path.join(out, "sv_frames.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
