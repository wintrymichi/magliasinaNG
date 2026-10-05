"""The camera tour of the final v2.7 check in the game (beamng/verifica/v2.7/final_test_plan.md, step 4), for
bng_lua/magliaso_signs.lua (run_final_screenshots.ps1). From a driver's or a low point of view:
- signs: zone 30, roundabout, the 50 "generale" with the village name, a crossing sign, STOP and the redrawn
  plates of the cantonal road (2.33, zone 30 with 16 t, the 4.32 pointer to Caslano / Pura), the ones closest
  to the Caslano / Magliaso boundary in the report of patch_signs.py, seen by the traffic they face;
- markings: the cantonal road's centre line, a crossing and a roundabout, seen from the lane of the traffic
  that meets the crossing sign / the roundabout sign there (a sign faces its traffic: the lane runs against
  'facing', ~2 m left of the pole);
- unpaved tracks: the driver views of Arosio and Cademario (unpaved_tour.py, verifica/v2.7/unpaved/sites.json);
- far trees: the pass above Gravesano from Gravesano, the Malcantone from the lake off Magliaso.
Every height is absolute, from the zip (road surface, else terrain; the lake's water level over the lake).
Writes <user>/magliaso_signs_views.json.
    python final_screenshots.py <zip> [report]
"""
import json, math, os, sys
import numpy as np
import road_mesh
import unpaved_tour as ut
from config import BEAMNG_USER, wgs_to_local

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "..", "verifica", "signs_v2.7.json")
SITES = os.path.join(HERE, "..", "verifica", "v2.7", "unpaved", "sites.json")
OUT = os.path.join(BEAMNG_USER, "magliaso_signs_views.json")
CENTRE = (45.98196, 8.87909)      # the Caslano / Magliaso boundary on the cantonal road
EYE = 1.3                         # m, a driver's eyes over the road
WAIT = 10.0
V26 = r"D:\beamng_magliaso\dist\magliaso_pura_v2.6.zip"   # the panorama plates as measured


def main():
    zp = sys.argv[1]
    signs = json.load(open(sys.argv[2] if len(sys.argv) > 2 else REPORT))["signs"]
    zi, un, al, q, _ = ut.load(zp)
    ALLS = road_mesh.TriSurface(al)
    wf = f"{ut.LV}/main/MissionGroup/level_objects/Water/items.level.json"
    water = [json.loads(l) for l in zi.read(wf).decode().splitlines() if l.strip()] if wf in zi.namelist() else []
    lake = max((o["position"][2] for o in water if o.get("class") == "WaterBlock"), default=-1e9)

    def h(x, y):
        z = ALLS.height([x], [y], "high")[0]
        return float(z) if np.isfinite(z) else float(ut.pu.terrain_top(q, np.array([x]), np.array([y]))[0])

    views = []

    def view(name, cam, target, cdz, tdz, fov):
        cz, tz = max(h(*cam), lake) + cdz, max(h(*target), lake) + tdz
        views.append({"name": name, "cam": [round(cam[0], 2), round(cam[1], 2)], "target": [round(target[0], 2), round(target[1], 2)],
                      "cam_dz": cdz, "target_dz": tdz, "cam_z": round(cz, 2), "target_z": round(tz, 2),
                      "from_target": False, "fov": fov, "wait": WAIT})

    px, py = wgs_to_local(*CENTRE)
    codes = lambda s: "+".join(p[0] for p in s["plates"])
    vals = lambda s: "+".join(str(p[1]) for p in s["plates"])

    def nearest(pred, src=None):
        c = [s for s in signs if pred(s) and (src is None or s["src"] == src)]
        return min(c, key=lambda s: math.hypot(s["x"] - px, s["y"] - py)) if c else None

    def sign_view(name, s, d=9.0, fov=40):
        # d m from the plates along the side they face (a 2 m step into the lane put some cameras into walls)
        if s is None:
            print("no sign for", name)
            return
        f = np.array(s["facing"])
        c = np.array([s["x"], s["y"]])
        view(name, c + f * d, c, EYE, 2.3, fov)
        print(name, codes(s), vals(s), s["src"], round(s["x"]), round(s["y"]))

    from signs_screenshots import osm_plates
    osm = osm_plates(zi)
    # the roundabout east of Magliaso (give-way plate of v2.6 at ~(1098, -971)): open ground, a zebra crossing
    # before the entry; the one at the Caslano boundary stands under a bridge ramp
    gc, gn = min(osm["mp_osm_giveway"], key=lambda p: math.hypot(p[0][0] - 1098.0, p[0][1] + 971.0))
    ax, ay = float(gc[0]), float(gc[1])
    near_a = lambda pred: min((s for s in signs if pred(s)), key=lambda s: math.hypot(s["x"] - ax, s["y"] - ay))
    # a warm-up first: on a cold load the game is still converting shapes and textures
    view("_warmup", gc[:2] + gn[:2] * 15, gc[:2], EYE, 1.0, 60)
    views[-1]["wait"] = 90.0
    sign_view("signs_zone30", nearest(lambda s: codes(s) == "2.59.1"))
    sign_view("signs_roundabout", near_a(lambda s: codes(s) == "2.41.1+3.02"))
    sign_view("signs_village50", nearest(lambda s: "4.27" in codes(s) and "Magliaso" in vals(s)), d=8, fov=45)
    sign_view("signs_crossing", near_a(lambda s: codes(s) == "4.11"))
    stop = nearest(lambda s: codes(s).startswith("3.01"))
    if stop is None:                                   # the STOP plates of v2.6 (props_osm.dae), not in the report
        c, n = min(osm["mp_osm_stop"], key=lambda p: math.hypot(p[0][0] - px, p[0][1] - py))
        stop = {"x": float(c[0]), "y": float(c[1]), "facing": [float(n[0]), float(n[1])], "plates": [["3.01", None]],
                "src": "osm v2.6"}
    sign_view("signs_stop", stop)
    # the panorama plates patch_signs.py draws: their place and side in props_poles.dae of the v2.6 zip,
    # their code in dati/signs_panorama.json
    import zipfile
    from patch_signs import existing_props, PANO_SIGNS
    codes_p = json.load(open(PANO_SIGNS, encoding="utf-8"))
    pano = []
    for mat, c, n in existing_props(zipfile.ZipFile(V26))[2]:
        info = codes_p.get(mat[3:])
        if info:
            pano.append({"x": float(c[0]), "y": float(c[1]), "facing": [float(n[0]), float(n[1])], "src": "panorama",
                         "plates": [[info["code"], info.get("value")]], "note": info.get("note", ""), "mat": mat})
    for name, pred in (("signs_cantonale_233", lambda s: codes(s) == "2.33"),
                       ("signs_cantonale_zone30_16t", lambda s: codes(s) == "2.59.1" and "16" in s["note"]),
                       ("signs_cantonale_pointer", lambda s: codes(s) == "4.32" and "Caslano" in vals(s))):
        c = [s for s in pano if pred(s)]
        s = min(c, key=lambda s: math.hypot(s["x"] - px, s["y"] - py)) if c else None
        sign_view(name, s, d=10, fov=40)
        if s:
            print("  ", s["mat"])

    # markings: a dashed line (2 m dashes, 6 m period, in the network paint of the zip, ~170 m from CENTRE),
    # seen from the lane beside it; the zebra crossing and the roundabout east of Magliaso
    p, t = np.array([718.0, -1237.4]), np.array([0.445, 0.895])
    r = np.array([t[1], -t[0]])
    view("markings_dashed_line", p - 12 * t + 1.7 * r, p + 40 * t + 0.8 * r, EYE, 0.0, 60)
    view("markings_crossing", gc[:2] + gn[:2] * 15, gc[:2] - gn[:2] * 5, EYE, 0.0, 60)
    view("markings_roundabout", gc[:2] + gn[:2] * 25, gc[:2] - gn[:2] * 20, 4.5, 0.0, 60)

    # unpaved tracks: the driver views of unpaved_tour.py
    for st in json.load(open(SITES)):
        if st["name"] not in ("arosio", "cademario"):
            continue
        p, t, n = (np.asarray(st[k]) for k in ("p", "t", "n"))
        view(f"unpaved_{st['name']}", p - 1.8 * n - 9 * t, p - 0.3 * n + 6 * t, 1.5, 0.0, 65)

    # far trees: low views from the valley
    g, pas = wgs_to_local(46.0425, 8.9235), wgs_to_local(46.0468, 8.9040)
    view("fartrees_gravesano_pass", g, pas, 25.0, 0.0, 55)
    l, mal = wgs_to_local(45.9725, 8.8935), wgs_to_local(45.9980, 8.8590)   # on the lake off Magliaso
    view("fartrees_lake_malcantone", l, mal, 2.0, 0.0, 55)

    json.dump(views, open(OUT, "w"), indent=1)
    print(OUT, len(views), "views; lake level", lake)


if __name__ == "__main__":
    main()
