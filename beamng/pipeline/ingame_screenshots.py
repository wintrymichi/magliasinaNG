"""README screenshots taken inside BeamNG.drive, at the same views as screenshots.py (v2.6).
make : writes the camera tour (<user>/magliaso_readme_views.json) for bng_lua/magliaso_readme.lua:
       for every view of screenshots.py the camera and target position (x, y in the level frame) and the
       heights above the ground; the extension takes the ground height from the game itself (terrain,
       roads, bridges), so the views do not depend on a DTM of the pipeline's work folder.
The tour itself is run by run_readme_screenshots.ps1, which then converts the game's shots to the
README's JPGs (beamng/verifica/screenshots).
    python ingame_screenshots.py [view names...]        (default: all the views)
"""
import json, math, os, sys
from config import BEAMNG_USER, wgs_to_local
from screenshots import VIEWS, STREET

OUT = os.path.join(BEAMNG_USER, "magliaso_readme_views.json")
SNAP_ROAD = {"12_pura_cantonale", "13_agno_via"}


def main():
    views = []
    for name, (lat, lon, dist, az, el, fov, title) in VIEWS.items():
        x, y = wgs_to_local(lat, lon)
        a, e = math.radians(az), math.radians(el)
        cx, cy = x + dist * math.cos(e) * math.sin(a), y + dist * math.cos(e) * math.cos(a)
        # camera dist * sin(el) above the ground of the target, looking at the target on the ground
        views.append({"name": name, "cam": [round(cx, 2), round(cy, 2)], "target": [round(x, 2), round(y, 2)],
                      "cam_dz": round(dist * math.sin(e), 2), "target_dz": 0.0, "from_target": True,
                      "fov": fov, "wait": 20.0})
    for name, (la, lo, lb, lob, eye, fov, title) in STREET.items():
        x0, y0 = wgs_to_local(la, lo)
        x1, y1 = wgs_to_local(lb, lob)
        # eye height above the ground under the camera, looking slightly down; snap_road: the camera is moved
        # onto the closest road of the game's AI network and looks along it (the views of screenshots.py
        # that stand in a garden or beside the road)
        views.append({"name": name, "cam": [round(x0, 2), round(y0, 2)], "target": [round(x1, 2), round(y1, 2)],
                      "cam_dz": eye, "target_dz": eye, "from_target": False, "pitch": -3.0,
                      "snap_road": name in SNAP_ROAD, "fov": fov, "wait": 10.0})
    if sys.argv[1:]:
        views = [v for v in views if v["name"] in sys.argv[1:]]
    json.dump(views, open(OUT, "w"), indent=1)
    print(OUT, len(views), "views")


if __name__ == "__main__":
    main()
