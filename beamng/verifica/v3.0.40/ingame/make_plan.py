"""Plans of the v3.0.40 in-game test (magliaso_v3040.lua): the frame-rate places, the README screenshots, the traffic.

    python make_plan.py LEVEL_DIR OUT_DIR

LEVEL_DIR is the unpacked level of the zip under test (levels/magliaso_pura: its spawn points and terrain give the
places, the time trials their start positions). Writes OUT_DIR/plan_fps.json (the frame rate only, for the same
places in v3.0 and v3.0.40) and OUT_DIR/plan_v3040.json (frame rate, screenshots, traffic). Places are in the level
frame; heights the Lua takes from the game where a plan leaves them out.
"""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "pipeline"))


def items(f):
    return [json.loads(l) for l in open(f) if l.strip()]


class Ground:
    def __init__(self, lv):
        import patch_release as pr
        self.t = pr.Terrain(lv)

    def z(self, x, y):
        t = self.t
        c, r = (x - t.x0) / t.sq, (y - t.y0) / t.sq
        return float(t.h[int(round(r)), int(round(c))])


def aerial(g, name, x, y, dist, az, el, fov=50):
    a, e = math.radians(az), math.radians(el)
    tz = g.z(x, y)
    cx, cy = x + dist * math.cos(e) * math.sin(a), y + dist * math.cos(e) * math.cos(a)
    return {"name": name, "cam": [round(cx, 1), round(cy, 1), round(tz + dist * math.sin(e), 1)],
            "target": [x, y, round(tz, 1)], "fov": fov}


def main(lv, out):
    g = Ground(lv)
    sp = {o["name"]: o for o in items(os.path.join(lv, "main", "MissionGroup", "PlayerDropPoints", "items.level.json"))
          if o.get("name")}
    races = {}
    mroot = os.path.join(lv, "..", "..", "gameplay", "missions", "magliaso_pura", "timeTrial")
    for r in sorted(os.listdir(mroot)) if os.path.isdir(mroot) else []:
        races[r[:3]] = json.load(open(os.path.join(mroot, r, "race.race.json")))

    def street(name, spawn):
        o = sp[spawn]
        m = o["rotationMatrix"]
        f = np.array([-m[3], -m[4]])                       # the car's front (-Y) of the spawn point
        f = f / np.linalg.norm(f)
        x, y, z = o["position"]
        return {"name": name, "cam": [x, y, round(z + 1.7, 2)],
                "target": [round(x + 100 * f[0], 1), round(y + 100 * f[1], 1), round(z - 0.3, 2)], "fov": 60}

    pn = {k: r["pathnodes"] for k, r in races.items()}
    hp = pn["001"][5]["pos"], pn["001"][6]["pos"]
    fps = [street("Magliaso junction", "spawn_magliaso"), street("Pura", "spawn_pura"),
           street("Magliaso Paese", "spawn_magliaso_paese"), street("Agno lakeside", "spawn_agno"),
           street("Caslano", "spawn_caslano"), street("Novaggio", "spawn_novaggio"),
           street("Bedigliora", "spawn_bedigliora"), street("Arosio", "spawn_arosio"),
           street("Ponte Tresa", "spawn_ponte_tresa"), street("Breno", "spawn_breno"),
           aerial(g, "over Magliaso and the lake", 877.0, -1640.0, 520, 200, 24),
           aerial(g, "over Novaggio", -1045.0, 2100.0, 360, 120, 26),
           {"name": "cantonal road", "cam": [hp[0][0], hp[0][1], round(hp[0][2] + 1.7, 2)],
            "target": [hp[1][0], hp[1][1], round(hp[1][2] + 1.0, 2)], "fov": 60}]
    base = {"start_wait": 60.0, "fps_seconds": 5.0, "fps_warm": 8.0, "wait": 20.0, "quit": True}
    json.dump(dict(base, phases=["fps"], fps=fps), open(os.path.join(out, "plan_fps.json"), "w"), indent=1)

    def car(name, at, look, camera="driver", **kw):
        return dict({"name": name, "kind": "car", "at": list(at[:2]), "look": list(look[:2]), "camera": camera,
                     "fov": 62 if camera == "driver" else None}, **kw)

    def start(name, race, which=0, camera="orbit"):
        s = races[race]["startPositions"][which]
        return {"name": name, "kind": "car", "pos": s["pos"], "rot": s["rot"], "camera": camera}

    def look(name, x, y, dz, rmin, rmax, ideal, **kw):
        return dict({"name": name, "kind": "road_look", "target": [x, y], "target_dz": dz, "rmin": rmin,
                     "rmax": rmax, "ideal": ideal, "eye": 1.7, "fov": 55}, **kw)

    def free(v):
        return dict(v, kind="free")

    r1, r2, r3, r4 = pn["001"], pn["002"], pn["003"], pn["004"]
    wall0, wall1 = (-256.4, -19.4), (-298.1, 6.7)                  # roadside wall of the cantonal road
    d = np.subtract(wall1, wall0) / np.linalg.norm(np.subtract(wall1, wall0))
    shots = [
        # from the driver's seat (ETK 800, right-hand lane)
        car("cockpit-stone-walls-040", np.add(wall0, -35 * d), wall1),
        car("cockpit-wear-shadows", r4[3]["pos"], r4[4]["pos"]),
        car("cockpit-wear-shadows-2", r1[7]["pos"], r1[8]["pos"]),
        car("cockpit-wear-junction", r1[1]["pos"], r1[0]["pos"]),
        car("cockpit-direction-signs", (-967.0, 1971.0), (-995.4, 2000.1)),
        car("cockpit-direction-signs-2", (-1025.0, 2031.0), (-995.4, 2000.1)),
        car("cockpit-direction-signs-3", (720.0, -1060.0), (759.5, -1097.5)),
        car("cockpit-astano-banco", r3[2]["pos"], r3[3]["pos"]),
        car("cockpit-astano-banco-2", r3[3]["pos"], r3[4]["pos"]),
        car("cockpit-caslano-lakeside", (391.1, -2783.4), (181.1, -2984.4)),
        start("cockpit-arosio", "002", 1, camera="driver"),
        # time trials, behind the car
        start("race-magliaso-pura-start", "001", 0),
        car("race-penudria", r2[7]["pos"], r2[8]["pos"], camera="orbit"),
        car("race-astano-banco", r3[5]["pos"], r3[6]["pos"], camera="orbit"),
        car("race-novaggio-breno", r4[9]["pos"], r4[10]["pos"], camera="orbit"),
        # churches, bell towers and the cable car, from the roads around them
        look("church-novaggio", -1052.0, 2044.0, 18.0, 35, 110, 60),
        look("church-agno", 2210.0, 708.0, 22.0, 45, 140, 80),
        look("church-miglieglia", -990.0, 3735.0, 9.0, 30, 120, 55),
        look("church-bedigliora-night", -2085.0, 1148.0, 25.0, 35, 120, 65, tod=0.5, wait=25.0),
        look("church-bedigliora-dusk", -2085.0, 1148.0, 25.0, 35, 120, 65, tod=0.4, wait=25.0),
        look("lema-cable-car", -1399.0, 3917.0, 25.0, 150, 600, 300, clear=30.0, fov=50),
        free(aerial(g, "lema-cable-car-2", -1229.0, 3731.0, 380, 135, 12, fov=50)),
        free(aerial(g, "lema-summit", -2910.0, 5377.0, 150, 110, 14, fov=50)),
        # villages, walls and the view from above
        look("fountain-village", -506.6, 1162.0, 0.6, 6, 25, 12, clear=1.5, fov=60),
        dict(look("wall-closed-end", wall1[0], wall1[1], 0, 8, 25, 14, clear=1.0, fov=60), target=[*wall1, 454.3]),
        free(aerial(g, "overview-monte-caslano", 900.0, -3100.0, 1100, 30, 20)),
        free(aerial(g, "overview-arosio", 2300.0, 6282.0, 420, 150, 28)),
        free(aerial(g, "overview-far-trees-040", -1700.0, 2900.0, 1300, 160, 14)),
    ]
    for v in shots:
        if v.get("fov") is None:
            v.pop("fov", None)
    traffic = {"at": {"at": [-169.3, -196.0], "look": [-223.2, -58.2]}, "cars": 12, "parked": 30, "settle": 40.0,
               "shot": "chase-cantonale-traffic", "duration": 300, "every": 2.0}
    json.dump(dict(base, phases=["fps", "shots", "traffic"], fps=fps, shots=shots, traffic=traffic),
              open(os.path.join(out, "plan_v3040.json"), "w"), indent=1)
    print(len(fps), "places,", len(shots), "shots")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
