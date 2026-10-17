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

# times of day of the level's clock (scouted: 0.79 a pink dawn, 0.24 golden, 0.256 the sun on the western ridge,
# 0.265 already after sunset)
DAWN, MORNING, DAY, AFTERNOON, GOLDEN, SUNSET, DUSK = 0.79, 0.85, 0.02, 0.12, 0.24, 0.256, 0.29


def ll(lat, lon):
    x, y = wgs_to_local(lat, lon)
    return [round(x, 2), round(y, 2)]


def view_orbit(name, lat, lon, dist, az0, az1, el0, el1, secs, tod, group, fov=50, d1=None):
    """An overview of screenshots.VIEWS (lat, lon, dist, az, el) turned into a slow drone move."""
    return dict(name=name, kind="orbit", centre=ll(lat, lon), dist=[dist, d1 or dist], az=[az0, az1],
                el=[el0, el1], fov=fov, secs=secs, tod=tod, group=group)


def cantonale(d0, d1, step=60.0):
    """Waypoints along the cantonal road (Magliaso roundabout -> Pura -> Curio), from the Street View track of
    work/poses.json: its points between route distances d0 and d1 (m), one every `step` metres."""
    from config import WORK
    P = sorted((p for p in json.load(open(os.path.join(WORK, "poses.json"))) if p.get("main_run")),
               key=lambda p: p["route_dist"])
    out, nxt = [], d0
    for p in P:
        if d0 <= p["route_dist"] <= d1 and p["route_dist"] >= nxt:
            out.append([round(p["pos"][0], 1), round(p["pos"][1], 1)])
            nxt = p["route_dist"] + step
    return out


def road(name, start, end, dist, secs, tod, group, side=2.5, skip=0, fov=62, ahead=25):
    """A walk at eye height along the game's AI road from `start` towards `end` (map.getPath), `dist` metres
    after `skip`, `side` metres right of the road's centre line, looking `ahead` metres down the road."""
    return dict(name=name, kind="road", start=start, end=end, dist=dist, skip=skip, side=side, ahead=ahead,
                secs=secs, tod=tod, group=group, fov=fov)


SHOTS = [
    # ---- 1 opening: morning over the lake
    view_orbit("a01_lago_alba", 45.9807, 8.8850, 640, 206, 196, 20, 23, 9, DAWN, "open", d1=500),
    view_orbit("a02_caslano_torrazza", 45.96664, 8.87381, 620, 255, 240, 22, 22, 7, MORNING, "open"),
    # ---- 2 landscapes from above
    view_orbit("a03_novaggio", 46.0100, 8.8530, 380, 128, 108, 26, 24, 6, MORNING, "land"),
    view_orbit("a04_penudria", 46.04195, 8.90913, 430, 150, 135, 32, 26, 7, DAY, "land", d1=380),
    view_orbit("a07_cademario", 46.0226, 8.8905, 340, 150, 165, 28, 26, 6, GOLDEN, "land"),
    dict(name="a09_breno", kind="orbit", centre=[40, 4540], dist=[300, 260], az=[200, 180], el=[28, 24],
         fov=50, secs=6, tod=AFTERNOON, group="land"),
    # ---- 3 on foot: eye height along the village streets (the AI road, pavement side)
    dict(name="w01_magliaso_cantonale", kind="walk", start=[747, -1094], end=[747 - 0.6585 * 14, -1094 - 0.7526 * 14],
         side=4.2, secs=7, tod=MORNING, group="foot", fov=62),
    road("r01_magliaso_paese", [1000, -965], [1500, -890], 16, 6, MORNING, "foot", side=4.0),
    road("r05_magliaso_tramonto", [1450, -897], [1000, -965], 16, 6, GOLDEN, "foot", side=4.0),
    road("r04_magliaso_negozi", [1560, -880], [1700, -620], 9, 6, AFTERNOON, "foot", side=3.0),
    dict(name="w03_bedigliora", kind="walk", start=[-2047, 1178], end=[-2047 + 0.6644 * 10, 1178 - 0.7474 * 10],
         side=0.0, secs=6, tod=GOLDEN, group="foot", fov=62),
    dict(name="w06_negozi_magliaso", kind="orbit", centre=[1658, -690], dist=[24, 22], az=[200, 160], el=[4, 4],
         look_dz=2.0, fov=60, secs=6, tod=AFTERNOON, group="foot"),
    # ---- 4 reality vs game: the Street View panorama's place, direction and height (sv_frames.py)
    *[dict(name="c%02d_%s" % (i + 1, k), kind="still", pano=p, yaw=y, pitch=-2.0, fov=72, secs=0.5, handle=0.0,
           tod=DAY, group="real")
      for i, (k, p, y) in enumerate([
          ("tornante_cantonale", "FZK_W5VIhAhWucqwaC91bQ", "fwd"),
          ("rotonda_magliaso", "HTc-dh-_Bma9-6FsTiOrdA", "fwd"),
          ("cantonale_magliaso", "FatLQx5eVlo_WOMd76rS3Q", "fwd"),
          ("cantonale_pura", "DnDK9VMDN8R-zbxzxZoniA", "fwd"),
          ("penudria", "ZiXC4KoAMxP_8LzDl1XOCQ", "fwd"),
          ("agno", "27Q6k3C8qh0APD1C9MclVg", "fwd"),
          ("magliaso_paese", "5Bek8_9Ou8MLlY6XGJQilA", "fwd"),
          ("negozi_magliaso", "_6-4SJnHkldFQXg7uOko9Q", "fwd")])],
    # ---- 5 driving: cinematics with an AI car (ETK 800, constant speed along waypoints), then gameplay
    dict(name="d01_cantonale_chase_low", kind="follow", rig="chase_low", car="etk800", route=cantonale(140, 560),
         speed=10, secs=6, tod=GOLDEN, group="drive", fov=55),
    dict(name="d02_magliaso_front34", kind="follow", rig="front34", car="etk800",
         route=[[1450, -897], [1250, -930], [1000, -965]], speed=11, secs=6, tod=GOLDEN, group="drive", fov=45),
    dict(name="d03_penudria_heli", kind="follow", rig="heli", car="etk800", route=[ll(46.0405, 8.9095), ll(46.0435, 8.9115)], speed=12, secs=8, tod=AFTERNOON, group="drive", fov=50),
    dict(name="d04_cantonale_heli", kind="follow", rig="heli", car="etk800", route=cantonale(1380, 2100),
         speed=13, secs=7, tod=GOLDEN, group="drive", fov=50),
    dict(name="d06_magliaso_side", kind="follow", rig="side", car="etk800", route=[[1000, -965], [1250, -930], [1500, -890]],
         speed=12, secs=5, tod=AFTERNOON, group="drive", fov=50),
    dict(name="g01_gameplay_cantonale", kind="gameplay", car="etk800", route=cantonale(1300, 2100),
         speed=14, secs=6, tod=DAY, group="drive"),
    dict(name="g02_gameplay_magliaso", kind="gameplay", car="etk800", route=[[1000, -965], [1250, -930], [1500, -890]],
         speed=12, secs=5, tod=AFTERNOON, group="drive"),
    # ---- 6 the end: sunset over the lake (camera over the water, looking west into the sun)
    dict(name="e01_finale_tramonto", kind="orbit", centre=[-200, -2300], dist=[1000, 850], az=[120, 112],
         el=[11, 13], fov=55, secs=9, tod=SUNSET, group="end"),
    dict(name="e02_tramonto_magliaso", kind="orbit", centre=[900, -1250], dist=[1100, 935], az=[105, 97],
         el=[9, 11], fov=55, secs=9, tod=SUNSET, group="end"),
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
    if "--todtest" in args:      # the level's own clock: the first and the last shot at a few times of day
        base = {s["name"]: s for s in SHOTS}
        for n, tods in (("a01_lago_alba", (0.78, 0.79, 0.80)), ("e01_finale_tramonto", (0.25, 0.262))):
            shots += [dict(base[n], name="t_%s_%03d" % (n[:3], round(t * 1000)), tod=t, group="todtest") for t in tods]
    resolve_panos(shots)
    json.dump({"scout": scout, "fps": 60, "video": [2560, 1440], "preroll": 6,
               "timescale": 0.25 if scout else 0.02, "shots": shots}, open(OUT, "w"), indent=1)
    print(OUT, len(shots), "shots", "(scout)" if scout else "")


if __name__ == "__main__":
    main(sys.argv[1:])
