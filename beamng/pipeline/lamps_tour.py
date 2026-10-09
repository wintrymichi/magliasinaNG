"""The places and views of the check of lamps.lamps_step (v2.8): street lamps along the roads of the villages.
    python lamps_tour.py sites <zip before> <report of lamps.lamps_step>  -> verifica/v2.8/lamps/sites.json
    python lamps_tour.py render <level before> <level after>            -> verifica/v2.8/lamps/render3d/
    python lamps_tour.py views <zip> <tag>                              -> <user>/magliaso_unpaved_views.json
sites: in the villages of the communes with the most new lamps (Tresa, Lema, Agno, Caslano), the 100 m
square with the most of them; its views: a driver on the AI road nearest to the square's centre looking
40 m along it, and the square from above (240 m) with the lamps marked.
render: before and after with render3d.py (the game's lamp model is drawn as a grey post: the check is of
where the lamps stand), side by side (compare_<site>_<view>.jpg); on the views from above the new lamps
are yellow dots, those of v2.7 white.
views: the driver views for the in-game tour of run_lamps_screenshots.ps1 (bng_lua/magliaso_unpaved.lua),
by day and at night.
"""
import json, os, sys, zipfile
import numpy as np
import lamps as pl
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "lamps")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"
COMMUNES = ("Tresa", "Lema", "Agno", "Caslano")
TOP = 240.0           # m, side of the view from above


def sites(zp, report):
    zi = zipfile.ZipFile(zp)
    rep = json.load(open(report))
    new = np.array(rep["lamps"])[:, :2]
    roads = [o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [s for s in (pl.sample(o["nodes"]) for o in roads) if s is not None]
    P = np.concatenate([s[0] for s in S])
    T = np.concatenate([s[1] for s in S])
    import gzip
    from scipy.spatial import cKDTree
    gwr = json.load(gzip.open(os.path.join(pl.DATI, "gwr_area.json.gz")))["buildings"]
    G = np.array([[b["x"], b["y"]] for b in gwr])
    com = np.array([b.get("ggdename", "") for b in gwr])
    of = com[cKDTree(G).query(new)[1]]
    ptree = cKDTree(P[:, :2])
    out = []
    for c in COMMUNES:
        L = new[of == c]
        if not len(L):
            continue
        key = np.floor(L / 100.0).astype(np.int64)
        u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
        ctr = (u[cnt.argmax()] + 0.5) * 100.0
        j = ptree.query(ctr)[1]
        p, t = P[j], T[j]
        cam = [round(float(p[0] - 12 * t[0]), 2), round(float(p[1] - 12 * t[1]), 2), round(float(p[2] + 1.5), 2)]
        tgt = [round(float(p[0] + 40 * t[0]), 2), round(float(p[1] + 40 * t[1]), 2), round(float(p[2] + 1.0), 2)]
        out.append({"name": c.lower().replace(" ", "_"), "commune": c, "centre": [round(float(v), 1) for v in ctr],
                    "lamps_in_square": int(cnt.max()),
                    "views": [{"view": "driver", "cam": cam, "target": tgt, "fov": 65.0}]})
        print(out[-1])
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out, open(SITES, "w"), indent=1)


def render(before, after):
    import render3d
    from PIL import Image, ImageDraw
    out = os.path.join(OUT_DIR, "render3d")
    os.makedirs(out, exist_ok=True)
    S = json.load(open(SITES))
    lamps = {}
    for tag, lv in (("before", before), ("after", after)):
        f = os.path.join(lv, "main", "MissionGroup", "props", "street_lights", "items.level.json")
        lamps[tag] = np.array([json.loads(l)["position"] for l in open(f) if l.strip() and pl.LIGHT in l])
        with render3d.Renderer(lv, W=1280, H=720) as R:
            for s in S:
                for v in s["views"]:
                    R.shot(render3d.Camera.look(v["cam"], v["target"], fov=v["fov"]),
                           os.path.join(out, f"{tag}_{s['name']}_{v['view']}.jpg"), near=300.0, far=2500.0)
                x, y = s["centre"]
                R.shot(render3d.Camera.top(x - TOP / 2, y - TOP / 2, x + TOP / 2, y + TOP / 2, px_per_m=4.0),
                       os.path.join(out, f"{tag}_{s['name']}_top.jpg"), trees=False)
    old = {tuple(np.round(p[:2], 2)) for p in lamps["before"]}
    for s in S:
        x0, y1 = s["centre"][0] - TOP / 2, s["centre"][1] + TOP / 2
        for tag in ("before", "after"):
            f = os.path.join(out, f"{tag}_{s['name']}_top.jpg")
            im = Image.open(f).convert("RGB")
            d = ImageDraw.Draw(im)
            for p in lamps[tag]:
                u, v = (p[0] - x0) * 4.0, (y1 - p[1]) * 4.0
                if 0 <= u < im.width and 0 <= v < im.height:
                    col = "white" if tuple(np.round(p[:2], 2)) in old else (255, 214, 0)
                    d.ellipse([u - 5, v - 5, u + 5, v + 5], fill=col, outline="black", width=2)
            im.save(f, quality=86)
        for v in [w["view"] for w in s["views"]] + ["top"]:
            ims = [Image.open(os.path.join(out, f"{t}_{s['name']}_{v}.jpg")) for t in ("before", "after")]
            w, h = ims[0].size
            im = Image.new("RGB", (2 * w + 8, h), "white")
            for k, (a, label) in enumerate(zip(ims, ("v2.7", "lamps.lamps_step"))):
                im.paste(a, (k * (w + 8), 0))
                ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28 if v != "top" else 40,
                                        stroke_width=2, stroke_fill="black")
            f = os.path.join(out, f"compare_{s['name']}_{v}.jpg")
            im.resize((w, h // 2)).save(f, quality=86)
            print(f, flush=True)


def views(zp, tag):
    """By day, then the same at night (tod 0.5: midnight, as the game counts the time of day)."""
    S = json.load(open(SITES))
    out = [{"kind": "view", "name": f"{tag}_{s['name']}_{v['view']}{suffix}", "cam": v["cam"], "target": v["target"],
            "fov": v["fov"], "wait": 9.0, "tod": tod, "fps": True} for tod, suffix in ((0.0, ""), (0.5, "_night"))
           for s in S for v in s["views"]]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views}[cmd](*args)
