"""The camera tour of the v2.7 road-sign check in the game (run_signs_screenshots.ps1, bng_lua/magliaso_signs.lua).
Picks, closest to the Caslano / Magliaso boundary on the cantonal road, one sign of each kind to check:
from the report of signs_net.signs_step a roundabout entry (2.41.1 over 3.02), a zebra crossing 4.11, a 30 zone
entry, the two closest place signs and a no-entry 2.02; from the zip itself (props_osm.dae) a STOP, a
give-way and a bus stop plate of v2.6, turned in v2.7. Every sign is seen from the side it faces, 15 m
and 7 m away, the STOP also from behind (grey back expected). Heights are absolute (the game's probe from
above would also hit roofs, trees and the props): eye 1.6 m over the foot of the pole, looking at the plates.
Writes <user>/magliaso_signs_views.json.
    python signs_screenshots.py [zip] [report]
"""
import json, math, os, sys, zipfile
import numpy as np
from config import BEAMNG_USER, wgs_to_local
from signs_net import read_dae, LEVEL

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = r"D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip"
REPORT = os.path.join(HERE, "..", "verifica", "signs_v2.7.json")
OUT = os.path.join(BEAMNG_USER, "magliaso_signs_views.json")
EYE = 1.6                         # m over the foot of the pole
PLATE = 2.2                       # m, centre of the (first) plate over the foot of the pole
CENTRE = (45.98196, 8.87909)      # the Caslano / Magliaso boundary on the cantonal road


def osm_plates(z):
    """{material: [(centre (3,), normal (2,))]} of the STOP, give-way and bus stop plates of props_osm.dae."""
    V, N, T, C, parts = read_dae(z.read(f"{LEVEL}/art/shapes/props/props_osm.dae"))
    out = {}
    for mat, idx in parts:
        if mat not in ("mp_osm_stop", "mp_osm_giveway") and not mat.startswith("mp_osm_bus_"):
            continue
        t = V[idx[:, 0].reshape(-1, 3)]
        nrm = N[idx[:, 1]].reshape(-1, 3, 3).mean(1)
        for k in range(0, len(t) - 1, 2):
            c = (t[k].mean(0) + t[k + 1].mean(0)) / 2
            out.setdefault(mat, []).append((c, nrm[k][:2] / max(np.hypot(*nrm[k][:2]), 1e-9)))
    return out


def main():
    zp = sys.argv[1] if len(sys.argv) > 1 else ZIP
    signs = json.load(open(sys.argv[2] if len(sys.argv) > 2 else REPORT))["signs"]
    px, py = wgs_to_local(*CENTRE)
    dist = lambda x, y: math.hypot(x - px, y - py)
    codes = lambda s: "+".join(p[0] for p in s["plates"])

    picks = []
    for name, pred in (("roundabout", lambda c: c == "2.41.1+3.02"), ("crossing_4_11", lambda c: c == "4.11"),
                       ("zone30_entry", lambda c: c.startswith("2.59.1")), ("no_entry_2_02", lambda c: c == "2.02")):
        s = min((s for s in signs if pred(codes(s))), key=lambda s: dist(s["x"], s["y"]))
        picks.append((name, s["x"], s["y"], s["z"], s["facing"]))
    places = sorted((s for s in signs if any(p[0] in ("4.27", "4.28") for p in s["plates"])),
                    key=lambda s: dist(s["x"], s["y"]))
    for name, s in zip(("place_a", "place_b"), places):
        picks.append((name, s["x"], s["y"], s["z"], s["facing"]))
    plates = osm_plates(zipfile.ZipFile(zp))
    for name, pred in (("stop_3_01", lambda m: m == "mp_osm_stop"), ("giveway_3_02", lambda m: m == "mp_osm_giveway"),
                       ("bus_stop", lambda m: m.startswith("mp_osm_bus_"))):
        c, n = min((p for m, r in plates.items() if pred(m) for p in r), key=lambda p: dist(p[0][0], p[0][1]))
        picks.append((name, float(c[0]), float(c[1]), float(c[2]) - PLATE, [float(n[0]), float(n[1])]))

    views = []
    for name, x, y, z, f in picks:
        print(name, round(x, 2), round(y, 2), f)
        tours = [("far", 15.0, 25), ("near", 7.0, 32)] + ([("back", -10.0, 30)] if name == "stop_3_01" else [])
        for tag, d, fov in tours:
            views.append({"name": f"{name}_{tag}", "cam": [round(x + f[0] * d, 2), round(y + f[1] * d, 2)],
                          "target": [round(x, 2), round(y, 2)], "cam_dz": 1.6, "target_dz": PLATE,
                          "cam_z": round(z + EYE, 2), "target_z": round(z + PLATE, 2),
                          "from_target": False, "fov": fov, "wait": 8.0})
    json.dump(views, open(OUT, "w"), indent=1)
    print(OUT, len(views), "views")


if __name__ == "__main__":
    main()
