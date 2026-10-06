"""The views of the check of patch_catenary.py (v2.8): the overhead line of the railway.
    python catenary_tour.py sites <zip before>                    -> verifica/v2.8/catenary/sites.json
    python catenary_tour.py render <level before> <level after>  -> verifica/v2.8/catenary/render3d/
    python catenary_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: the middle of the three longest metre-gauge track chains (patch_catenary.chains/join): a view from 7 m
beside the track (the side with no roof or wall top in the way) and 3 m up, 30 m back, looking 70 m along it.
render: before and after with render3d.py (masts and wires are pipeline meshes, drawn as they are), side by
side (compare_<site>.jpg).
views: the same views for the in-game tour of run_catenary_screenshots.ps1 (bng_lua/magliaso_unpaved.lua), with
the frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import patch_catenary as pc
import wall_fill_tour as wft
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "catenary")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"


def sites(zp):
    zi = zipfile.ZipFile(zp)
    C, Ls = pc.sleepers(zi, LV)
    P = C[Ls < 2.25]
    lines = pc.join([P[c] for c in pc.chains(P)])
    lines.sort(key=lambda l: -np.linalg.norm(np.diff(l[:, :2], axis=0), axis=1).sum())
    out = []
    for k, l in enumerate(lines[:3]):
        m = len(l) // 2
        t = l[min(m + 5, len(l) - 1), :2] - l[max(m - 5, 0), :2]
        t /= np.linalg.norm(t)
        n = np.array([t[1], -t[0]])
        c = l[m]
        tgt = np.r_[c[:2] + 70 * t, c[2] + 3.0]
        ob = wft.obstacles(zi, c)
        for side in (1.0, -1.0):                        # the side with no roof or wall top in the way
            cam = np.r_[c[:2] - 30 * t + side * 7 * n, c[2] + 3.0]
            if wft.clear(ob, cam, tgt):
                break
        out.append({"name": f"flp_{k + 1}", "cam": [round(float(v), 2) for v in cam],
                    "target": [round(float(v), 2) for v in tgt], "fov": 60.0})
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
        with render3d.Renderer(lv, W=1280, H=720, dae_normals=True) as R:
            for s in S:
                R.shot(render3d.Camera.look(s["cam"], s["target"], fov=s["fov"]), os.path.join(out, f"{tag}_{s['name']}.jpg"),
                       near=300.0, far=2500.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "patch_catenary.py"))):
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
