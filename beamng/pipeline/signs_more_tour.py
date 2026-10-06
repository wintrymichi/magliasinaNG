"""The views of the check of patch_signs_more.py (v2.8): the warning and parking signs nobody mapped.
    python signs_more_tour.py sites <zip before> <report>        -> verifica/v2.8/signs/sites.json
    python signs_more_tour.py render <level before> <level after>  -> verifica/v2.8/signs/render3d/
    python signs_more_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: one sign of every kind the patch put up (the report of patch_signs_more.py), seen by the traffic that
reads it: 15 m before it, 2.5 m to the left of its pole and 1.5 m over the road, looking at its plate.
render: before and after with render3d.py (textured, the plates as drawn), side by side (compare_<kind>.jpg).
views: the same views for the in-game tour of run_signs_more_screenshots.ps1 (bng_lua/magliaso_unpaved.lua),
with the frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import patch_signs as ps
import wall_fill_tour as wft
from road_mesh import TriSurface
from config import BEAMNG_USER

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "signs")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
KINDS = (("curve", ("1.03", "1.04", "1.01", "1.02")), ("barrier", ("1.15",)), ("level_crossing", ("1.16",)),
         ("falling_rocks", ("1.13",)), ("parking", ("4.17",)))


def sites(zp, report):
    z = zipfile.ZipFile(zp)
    _, allt = ps.road_tops(z)
    S = TriSurface(allt)
    signs = json.load(open(report))["signs"]
    out = []
    for name, codes in KINDS:
        cand = [s for s in signs if s["plates"][0][0] in codes]
        for s in cand:
            c = np.array([s["x"], s["y"]])
            f = np.array(s["facing"])                    # towards the traffic that reads it
            left = np.array([-f[1], f[0]]) * -1          # left of the travel direction -f
            cam2 = c + 15 * f + 2.5 * left
            zr = S.height([cam2[0]], [cam2[1]], "near", [s["z"]])[0]
            if not np.isfinite(zr):
                continue
            cam = np.r_[cam2, zr + 1.5]
            tgt = np.r_[c, s["z"] + 2.2]
            if not wft.clear(wft.obstacles(z, np.r_[c, s["z"]]), cam, tgt):
                continue
            out.append({"name": name, "code": s["plates"][0][0], "cam": [round(float(v), 2) for v in cam],
                        "target": [round(float(v), 2) for v in tgt], "fov": 30.0})
            print(out[-1])
            break
        else:
            print(name, "no clear view")
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
                R.shot(render3d.Camera.look(s["cam"], s["target"], fov=s["fov"]),
                       os.path.join(out, f"{tag}_{s['name']}.jpg"), near=200.0, far=2000.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "patch_signs_more.py"))):
            im.paste(a, (k * (w + 8), 0))
            ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28, stroke_width=2,
                                    stroke_fill="black")
        f = os.path.join(out, f"compare_{s['name']}.jpg")
        im.resize((w, h // 2)).save(f, quality=86)
        print(f, flush=True)


def views(zp, tag):
    out = [{"kind": "view", "name": f"{tag}_{s['name']}", "cam": s["cam"], "target": s["target"], "fov": s["fov"],
            "wait": 8.0, "fps": True} for s in json.load(open(SITES))]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views}[cmd](*args)
