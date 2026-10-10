"""The views of the check of poles.roadside_step (v2.8): delineators outside the villages, wooden pole lines.
    python roadside_tour.py sites <zip before> <report of poles.roadside_step>  -> verifica/v2.8/roadside/sites.json
    python roadside_tour.py render <level before> <level after>               -> verifica/v2.8/roadside/render3d/
    python roadside_tour.py views <zip> <tag>                                 -> <user>/magliaso_unpaved_views.json
sites: the 300 m squares with the most delineators in open country (fewer than 8 buildings of the Federal
Register within 150 m; two) and the most wooden poles outside the woods (under 30 % forest floor within 60 m;
two); a driver on the AI road nearest to the square's centre looking 60 m along it.
render: before and after with render3d.py (delineators and cables are pipeline meshes, drawn as they are;
the game's wooden pole is drawn as a grey post), side by side (compare_<site>.jpg).
views: the same views for the in-game tour of run_roadside_screenshots.ps1 (bng_lua/magliaso_unpaved.lua),
with the frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import lamps as pl
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "roadside")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"


def sites(zp, report):
    import gzip
    from scipy.spatial import cKDTree
    import walls as pw
    from config import TER_X0, TER_Y0, TER_SQUARE
    zi = zipfile.ZipFile(zp)
    rep = json.load(open(report))
    gwr = json.load(gzip.open(os.path.join(pl.DATI, "gwr_area.json.gz")))["buildings"]
    gtree = cKDTree(np.array([[b["x"], b["y"]] for b in gwr]))
    _, _, lay, names = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))
    forest_ids = [names.index(m) for m in names if m.startswith("ForestFloor")]

    def open_country(kind, c):
        if kind == "delineators":
            return gtree.query_ball_point(c, 150.0, return_length=True) < 8
        cc = int(round((c[0] - TER_X0) / TER_SQUARE))
        rr = int(round((c[1] - TER_Y0) / TER_SQUARE))
        return np.isin(lay[rr - 40:rr + 41, cc - 40:cc + 41], forest_ids).mean() < 0.3
    roads = [o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [s for s in (pl.sample(o["nodes"]) for o in roads) if s is not None]
    P, T = np.concatenate([s[0] for s in S]), np.concatenate([s[1] for s in S])
    ptree = cKDTree(P[:, :2])
    out = []
    for kind, key in (("delineators", "delineator_posts"), ("poles", "poles")):
        pts = np.array(rep[key])[:, :2]
        cells, cnt = np.unique(np.floor(pts / 300.0).astype(np.int64), axis=0, return_counts=True)
        chosen = []
        for c in cells[np.argsort(-cnt)]:
            m = np.all(np.floor(pts / 300.0).astype(np.int64) == c, axis=1)
            if open_country(kind, pts[m].mean(0)):
                chosen.append(c)
            if len(chosen) == 2:
                break
        for n_, c in enumerate(chosen):
            m = np.all(np.floor(pts / 300.0).astype(np.int64) == c, axis=1)
            ctr = pts[m].mean(0)
            j = ptree.query(ctr)[1]
            p, t = P[j], T[j]
            out.append({"name": f"{kind}_{n_ + 1}", "count": int(m.sum()),
                        "cam": [round(float(p[0] - 15 * t[0]), 2), round(float(p[1] - 15 * t[1]), 2), round(float(p[2] + 1.5), 2)],
                        "target": [round(float(p[0] + 60 * t[0]), 2), round(float(p[1] + 60 * t[1]), 2), round(float(p[2] + 1.0), 2)],
                        "fov": 40.0 if kind == "delineators" else 65.0})       # 1 m posts: a longer lens
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
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "poles.roadside_step"))):
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
