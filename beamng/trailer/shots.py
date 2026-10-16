"""The shot list of the v3 trailer, written for bng_lua/magliaso_trailer.lua.

Every shot is a camera move in the level frame (x east, y north, metres; heights `agl` are over the game's
own surface, read by the extension at the start of the shot). Kinds:
  path    free camera through keyframes {pos, look}, centripetal Catmull-Rom, eased in and out
  orbit   around a centre: radius, height and azimuth from start to end (a drone arc)
  walk    eye height (1.7 m) along a road, from a point to a point, snapped to the game's AI road with a
          lateral offset (the pavement side); the eye follows the ground, smoothed
  still   a fixed camera (the Street View comparisons: at the panorama's place and height, 2.2 m)
  follow  an AI car driving a route; the camera rides a rig in the car's smoothed frame
          (chase_low, front34, side, heli, tele = a static camera on the roadside panning with a long lens)
  gameplay the same AI drive seen through the game's own orbit (chase) camera
Each shot has its time of day (`tod`, the game's 0..1 clock: 0 = noon, 0.25 = 18:00, 0.75 = 06:00),
its length in seconds (rendered with 1.5 s of handles at each end for the edit) and a `group` (the act of
the storyboard, beamng/trailer/STORYBOARD in the project files).
    python shots.py [names or groups...]         -> <user>/magliaso_trailer_shots.json
    python shots.py --scout [names or groups...] -> one still per keyframe (fast check of every framing)
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
from config import BEAMNG_USER, wgs_to_local   # noqa: E402

OUT = os.path.join(BEAMNG_USER, "magliaso_trailer_shots.json")
HANDLE = 1.5
EYE = 1.7          # on foot
SV_EYE = 2.2       # the Street View camera over the ground (work/camera_height.json)

# times of day (calibrate in the scout pass: the sun of the level is not the real one)
DAWN, MORNING, DAY, AFTERNOON, GOLDEN, SUNSET, DUSK = 0.77, 0.85, 0.02, 0.12, 0.24, 0.265, 0.29


def ll(lat, lon):
    x, y = wgs_to_local(lat, lon)
    return [round(x, 2), round(y, 2)]


def view_orbit(name, lat, lon, dist, az0, az1, el0, el1, secs, tod, group, fov=50, d1=None):
    """An overview of screenshots.VIEWS (lat, lon, dist, az, el) turned into a slow drone move."""
    return dict(name=name, kind="orbit", centre=ll(lat, lon), dist=[dist, d1 or dist], az=[az0, az1],
                el=[el0, el1], fov=fov, secs=secs, tod=tod, group=group)


SHOTS = [
    # ---- 1 opening: dawn over the lake
    view_orbit("a01_lago_alba", 45.9807, 8.8850, 640, 206, 196, 20, 23, 9, DAWN, "open", d1=500),
    view_orbit("a02_caslano_torrazza", 45.96664, 8.87381, 620, 255, 240, 22, 22, 7, MORNING, "open"),
    # ---- 2 landscapes from above
    view_orbit("a03_novaggio", 46.0100, 8.8530, 380, 128, 108, 26, 24, 6, MORNING, "land"),
    view_orbit("a04_penudria", 46.04195, 8.90913, 460, 150, 140, 40, 30, 7, DAY, "land", d1=400),
    view_orbit("a05_agno_nucleo", 45.9990, 8.9018, 240, 155, 175, 30, 28, 6, AFTERNOON, "land"),
    view_orbit("a06_ponte_tresa", 45.9678, 8.8570, 360, 225, 225, 24, 26, 6, AFTERNOON, "land", d1=290),
    view_orbit("a07_cademario", 46.0226, 8.8905, 340, 150, 165, 28, 26, 6, GOLDEN, "land"),
    dict(name="a08_tornante_top", kind="orbit", centre=[650, -960], dist=[45, 45], az=[0, 70], el=[60, 55],
         fov=55, secs=6, tod=DAY, group="land"),
    # ---- 3 on foot (driver's eye without the car, as if walking)
    dict(name="w01_magliaso_cantonale", kind="walk", start=[747, -1094], end=[747 - 0.6585 * 14, -1094 - 0.7526 * 14],
         side=4.2, secs=7, tod=MORNING, group="foot", fov=62),
    dict(name="w02_agno_nucleo", kind="walk", start=[2473, 728], end=[2473 - 0.56 * 10, 728 + 0.8285 * 10],
         side=0.0, secs=7, tod=AFTERNOON, group="foot", fov=62),
    dict(name="w03_bedigliora", kind="walk", start=[-2047, 1178], end=[-2047 + 0.6644 * 10, 1178 - 0.7474 * 10],
         side=0.0, secs=6, tod=GOLDEN, group="foot", fov=62),
    dict(name="w04_novaggio", kind="walk", start=[-1057, 2064], end=[-1057 + 0.5906 * 10, 2064 + 0.8069 * 10],
         side=2.5, secs=6, tod=AFTERNOON, group="foot", fov=62),
    dict(name="w05_breno", kind="walk", start=[-20, 4659], end=[-20 + 0.7313 * 10, 4659 - 0.682 * 10],
         side=2.5, secs=6, tod=GOLDEN, group="foot", fov=62),
    dict(name="w06_negozi_magliaso", kind="orbit", centre=[1658, -690], dist=[24, 22], az=[200, 160], el=[4, 4],
         look_dz=2.0, fov=60, secs=6, tod=AFTERNOON, group="foot"),
    dict(name="w07_benzinaio_eni", kind="orbit", centre=[1530, -888], dist=[26, 22], az=[120, 80], el=[5, 5],
         look_dz=2.0, fov=60, secs=6, tod=DUSK, group="foot", note="check the Eni canopy is in frame (scout)"),
    # ---- 4 reality vs game: the Street View panorama's place, direction and height (sv_frames.py)
    *[dict(name="c%02d_%s" % (i + 1, k), kind="still", pano=p, yaw=y, pitch=-2.0, fov=72, secs=4.5, tod=DAY,
           group="real")
      for i, (k, p, y) in enumerate([
          ("tornante_cantonale", "FZK_W5VIhAhWucqwaC91bQ", "fwd"),
          ("rotonda_magliaso", "HTc-dh-_Bma9-6FsTiOrdA", "fwd"),
          ("cantonale_magliaso", "FatLQx5eVlo_WOMd76rS3Q", "fwd"),
          ("cantonale_pura", "DnDK9VMDN8R-zbxzxZoniA", "fwd"),
          ("penudria", "ZiXC4KoAMxP_8LzDl1XOCQ", "fwd"),
          ("agno", "27Q6k3C8qh0APD1C9MclVg", "fwd"),
          ("magliaso_paese", "5Bek8_9Ou8MLlY6XGJQilA", "fwd"),
          ("negozi_magliaso", "_6-4SJnHkldFQXg7uOko9Q", "fwd")])],
    # ---- 5 driving: cinematics with an AI car, then a few seconds of gameplay
    dict(name="d01_cantonale_chase_low", kind="follow", rig="chase_low", car="etk800", route=[[747, -1094], [300, -700]],
         speed=14, secs=6, tod=GOLDEN, group="drive", fov=55),
    dict(name="d02_tornante_front34", kind="follow", rig="front34", car="etk800", route=[[700, -1010], [560, -880]],
         speed=10, secs=6, tod=GOLDEN, group="drive", fov=45),
    dict(name="d03_penudria_heli", kind="follow", rig="heli", car="etk800", route=[ll(46.0405, 8.9095), ll(46.0435, 8.9115)], speed=12, secs=8, tod=AFTERNOON, group="drive", fov=50),
    dict(name="d04_breno_side", kind="follow", rig="side", car="vivace", route=[[-20, 4659], [400, 4300]],
         speed=12, secs=5, tod=GOLDEN, group="drive", fov=50),
    dict(name="d05_mugena_tele", kind="follow", rig="tele", car="etk800", route=[[1395, 6440], [917, 6049]],
         speed=13, secs=6, tod=GOLDEN, group="drive", fov=22),
    dict(name="d06_lungolago_chase", kind="follow", rig="chase_low", car="vivace", route=[[1141, -2328], [1600, -1700]],
         speed=13, secs=5, tod=AFTERNOON, group="drive", fov=55, traffic=6),
    dict(name="g01_gameplay_cantonale", kind="gameplay", car="etk800", route=[[324, -1118], [-300, 225]],
         speed=16, secs=6, tod=DAY, group="drive"),
    dict(name="g02_gameplay_alto_malcantone", kind="gameplay", car="vivace", route=[[2280, 6304], [1395, 6440]],
         speed=14, secs=5, tod=AFTERNOON, group="drive"),
    # ---- 6 the end: sunset over the lake
    view_orbit("e01_finale_tramonto", 45.9807, 8.8850, 520, 200, 200, 22, 28, 9, SUNSET, "end", d1=850),
    view_orbit("e02_finale_tramonto_alt", 45.96664, 8.87381, 620, 250, 235, 20, 24, 7, SUNSET, "end", d1=760),
]

for s in SHOTS:
    s.setdefault("handle", HANDLE)
    if s["kind"] == "walk":
        s.setdefault("eye", EYE)
    if s["kind"] == "still":
        s.setdefault("eye", SV_EYE)


def resolve_panos(shots):
    """still shots: the panorama's position (level frame) and the yaw in the grid frame of the level."""
    need = {s["pano"] for s in shots if s["kind"] == "still"}
    if not need:
        return
    import gzip
    from config import WORK
    from camera import grid_convergence
    cov = os.path.join(WORK, "sv_coverage.json.gz")
    recs = {p["id"]: p for p in json.load(gzip.open(cov))["panoramas"] if p["id"] in need}
    pf = os.path.join(WORK, "poses.json")      # refined positions of the cantonal road's panoramas
    poses = {p["id"]: p for p in json.load(open(pf))} if os.path.exists(pf) else {}
    for s in shots:
        if s["kind"] != "still":
            continue
        r = recs[s["pano"]]
        s["cam"] = [round(v, 2) for v in poses[s["pano"]]["pos"][:2]] if s["pano"] in poses else ll(r["lat"], r["lon"])
        heading = r["heading_deg"] + grid_convergence(r["lat"], r["lon"])   # the car's direction, grid frame
        rel = {"fwd": 0.0, "back": 180.0, "left": -90.0, "right": 90.0}.get(s["yaw"], None)
        s["yaw_deg"] = round((heading + rel) % 360 if rel is not None else float(s["yaw"]), 2)


def main(args):
    scout = "--scout" in args
    names = [a for a in args if not a.startswith("--")]
    shots = [s for s in SHOTS if not names or s["name"] in names or s["group"] in names]
    resolve_panos(shots)
    json.dump({"scout": scout, "fps": 60, "shots": shots}, open(OUT, "w"), indent=1)
    print(OUT, len(shots), "shots", "(scout)" if scout else "")


if __name__ == "__main__":
    main(sys.argv[1:])
