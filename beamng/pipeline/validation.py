"""Photo vs. game comparison at the calibrated Street View poses.

make  : writes <level>/validation_views.json (camera tour for magliaso_validate.lua)
        and the matching level perspective crops of the real panoramas
        (work/validation/photo/<name>.png), same position, heading, FOV and aspect.
compare: after the game run, pairs photo/game images, segments both with the
        same Mask2Former model and reports per-class IoU and the
        silhouette (sky line / building / vegetation) agreement per view.
"""
import json, math, os, sys, glob
import numpy as np
import cv2
from config import DATASET, WORK, LEVEL_DIR, BEAMNG_USER
from camera import Pano

VW, VH, HFOV = 1280, 720, 90.0
DIRS = {"fwd": 0, "right": 90, "back": 180, "left": 270}
OUT = os.path.join(WORK, "validation")


def photo_view(img, R, yaw_deg, pitch_deg=0.0, w=VW, h=VH, hfov=HFOV):
    f = w / 2 / math.tan(math.radians(hfov) / 2)
    ii, jj = np.meshgrid(np.arange(w) - w / 2 + 0.5, h / 2 - np.arange(h) - 0.5)
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    fwd = np.array([math.sin(y) * math.cos(p), math.cos(y) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(y), -math.sin(y), 0.0])
    up = np.cross(right, fwd)
    d = fwd * f + ii[..., None] * right + jj[..., None] * up
    dc = d @ R
    lon = np.arctan2(dc[..., 0], dc[..., 1])
    lat = np.arcsin(np.clip(dc[..., 2] / np.linalg.norm(dc, axis=-1), -1, 1))
    Hi, Wi = img.shape[:2]
    u = ((lon + np.pi) / (2 * np.pi) * Wi - 0.5).astype(np.float32)
    v = ((np.pi / 2 - lat) / np.pi * Hi - 0.5).astype(np.float32)
    return cv2.remap(img, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def make(indices, dirs=DIRS, fov_game=None, out=OUT, jpg=False, wait_first=2.5, wait_next=2.5):
    """Photo views (out/photo/<name>.png) and the in-game camera list for the tour. jpg: the game
    saves JPEG screenshots (full-dataset run); the first view of a panorama waits longer for
    streaming than the following ones (same position, camera only turns)."""
    panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    os.makedirs(os.path.join(out, "photo"), exist_ok=True)
    views = []
    for i in indices:
        rec, ps = panos[i], poses[i]
        img = cv2.imread(os.path.join(DATASET, "panorami", f"{rec['index']:04d}_{rec['id']}.jpg"))
        R = np.array(ps["R"])
        fwd = R @ np.array([0, 1.0, 0])
        heading = math.degrees(math.atan2(fwd[0], fwd[1]))
        for k, (dn, rel) in enumerate(dirs.items()):
            yaw = (heading + rel) % 360
            name = f"v{i:04d}_{dn}"
            cv2.imwrite(os.path.join(out, "photo", name + ".png"), photo_view(img, R, yaw))
            v = {"name": name, "pos": ps["pos"], "yaw": round(yaw, 3), "pitch": 0.0,
                 "fov": fov_game if fov_game else HFOV, "wait": wait_first if k == 0 else wait_next}
            if jpg:
                v["jpg"] = True
            views.append(v)
    json.dump(views, open(os.path.join(LEVEL_DIR, "validation_views.json"), "w"), indent=1)
    # route end points for the AI navgraph check (start / end of the surveyed road axis)
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    ends = [[float(rp["center"][k][0]), float(rp["center"][k][1]), float(rp["z_center"][k]) + 0.5] for k in (0, -1)]
    json.dump(ends, open(os.path.join(LEVEL_DIR, "validation_route.json"), "w"))
    print(len(views), "views; route length on the profile %.0f m" % float(rp["s"][-1] - rp["s"][0]))


def game_shots():
    d = os.path.join(BEAMNG_USER, "screenshots", "magliaso")
    return {os.path.splitext(os.path.basename(f))[0]: f for f in glob.glob(os.path.join(d, "*.png"))}


def to_view(game_img):
    """Game screenshot (any 16:9 size) -> VW x VH."""
    return cv2.resize(game_img, (VW, VH), interpolation=cv2.INTER_AREA)


def side_by_side(names, out_name):
    shots = game_shots()
    rows = []
    for n in names:
        p = cv2.imread(os.path.join(OUT, "photo", n + ".png"))
        g = cv2.imread(shots[n]) if n in shots else np.zeros_like(p)
        g = to_view(g)
        rows.append(np.concatenate([p, g], 1))
    cv2.imwrite(os.path.join(OUT, out_name), cv2.resize(np.concatenate(rows, 0), None, fx=0.5, fy=0.5))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "make":
        idx = [int(t) for t in sys.argv[2].split(",")]
        make(idx, fov_game=float(sys.argv[3]) if len(sys.argv) > 3 else None)
    elif cmd == "makefull":
        # every panorama of the dataset, four directions (final verification)
        n = len(json.load(open(os.path.join(DATASET, "panoramas.json"))))
        make(list(range(n)), fov_game=90.0, out=os.path.join(WORK, "validation_full"), jpg=True,
             wait_first=2.0, wait_next=1.0)
    elif cmd == "sbs":
        side_by_side(sys.argv[2].split(","), sys.argv[3])
