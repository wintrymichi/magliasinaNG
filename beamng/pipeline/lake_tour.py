"""The views of the check of water.lake_step (v2.8): the piers of the lake and the boats moored at them.
    python lake_tour.py sites <zip before> <report>        -> verifica/v2.8/lake/sites.json
    python lake_tour.py render <level before> <level after>  -> verifica/v2.8/lake/render3d/
    python lake_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: the longest pier where boats moor, the longest fixed pier and the longest pier OSM maps as a mooring (the
report of water.lake_step), seen from the lake 28 m beside the pier and 3 m over the water, looking at its middle
(else from the shore behind its land end).
render: before and after with render3d.py (textured), side by side (compare_<site>.jpg).
views: the same views for the in-game tour of run_lake_screenshots.ps1 (bng_lua/magliaso_unpaved.lua), with the
frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import osm
import water as pk
import wall_fill_tour as wft
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "lake")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")


def sites(zp, report):
    zi = zipfile.ZipFile(zp)
    lv = f"levels/{LEVEL_NAME}"
    wl = pk.water_level(zi, lv)
    ground = pk.terrain(zi, lv)
    R = json.load(open(report))["built"]
    ways = {w["id"]: w for w in osm.load()[0]}
    lines = [b for b in R if not ways[b["osm"]]["nodes"][0] == ways[b["osm"]]["nodes"][-1]]
    pick = [("marina", max((b for b in lines if b["mooring"]), key=lambda b: b["length_m"])),
            ("fixed", max((b for b in lines if not b["floating"]), key=lambda b: b["length_m"])),
            ("boats", max((b for b in lines if b["mooring"] and ways[b["osm"]]["tags"].get("mooring") not in (None, "no")),
                          key=lambda b: b["length_m"], default=None))]
    out = []
    for name, b in pick:
        if b is None:
            continue
        line = ways[b["osm"]]["line"]
        xy = np.asarray(line.coords)
        zt = ground(xy[[0, -1], 0], xy[[0, -1], 1])
        a, e = (xy[0], xy[-1]) if zt[0] >= zt[1] else (xy[-1], xy[0])      # from the land end
        d = (e - a) / np.linalg.norm(e - a)
        n = np.array([-d[1], d[0]])
        c = np.asarray(line.interpolate(0.5, normalized=True).coords[0])
        tgt = np.r_[c, wl + 0.6]
        ob = wft.obstacles(zi, np.r_[c, wl])
        cams = [c + n * 28 * sd - d * 8 for sd in (1.0, -1.0)] + [a - d * 25 + n * 15 * sd for sd in (1.0, -1.0)]
        for k, cam2 in enumerate(cams):                     # from the lake beside it, else from the shore
            zg = float(ground([cam2[0]], [cam2[1]])[0])
            if k < 2 and zg > wl - 0.5:
                continue
            cam = np.r_[cam2, max(zg, wl) + 3.0]
            if wft.clear(ob, cam, tgt):
                break
        out.append({"name": name, "osm": b["osm"], "cam": [round(float(v), 2) for v in cam],
                    "target": [round(float(v), 2) for v in tgt], "fov": 55.0})
        print(out[-1])
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out, open(SITES, "w"), indent=1)


def render(before, after):
    import render3d
    from PIL import Image, ImageDraw
    out = os.path.join(OUT_DIR, "render3d")
    os.makedirs(out, exist_ok=True)
    S = json.load(open(SITES))
    for tag, lv in (("before", before), ("after", after)):
        with render3d.Renderer(lv, W=1280, H=720, textured=True, dae_normals=True) as R:
            for s in S:
                R.shot(render3d.Camera.look(s["cam"], s["target"], fov=s["fov"]), os.path.join(out, f"{tag}_{s['name']}.jpg"),
                       near=300.0, far=2500.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "water.lake_step"))):
            im.paste(a, (k * (w + 8), 0))
            ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28, stroke_width=2,
                                    stroke_fill="black")
        f = os.path.join(out, f"compare_{s['name']}.jpg")
        im.resize((w, h // 2)).save(f, quality=86)
        print(f, flush=True)


def views(zp, tag):
    out = [{"kind": "view", "name": f"{tag}_{s['name']}", "cam": s["cam"], "target": s["target"], "fov": s["fov"],
            "wait": 9.0, "fps": True} for s in json.load(open(SITES))]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views}[cmd](*args)
