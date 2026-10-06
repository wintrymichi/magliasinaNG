"""The views of the check of patch_understory.py (v2.8): a darker forest floor, undergrowth in the woods.
    python understory_tour.py sites <zip before>                  -> verifica/v2.8/understory/sites.json
    python understory_tour.py render <level before> <level after>  -> verifica/v2.8/understory/render3d/
    python understory_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: a driver on the forest road with the most forest floor within 30 m on both sides near Arosio (the
Penudria); the pass above Gravesano from the village; the Malcantone from the lake off Agno.
render: before and after with render3d.py (the ground in the median colour of its layer's base texture; the
game's undergrowth is a GroundCover, which the renderer does not draw; trees and meshes within 400 m of the
far views, the coarse terrain beyond), side by side (compare_<site>.jpg).
views: the same views for the in-game tour of run_understory_screenshots.ps1 (bng_lua/magliaso_unpaved.lua),
with the frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import patch_lamps as pl
import patch_wall_fill as pw
from config import BEAMNG_USER, LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "understory")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"


def sites(zp):
    zi = zipfile.ZipFile(zp)
    n, q, lay, names = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))
    blk = next(o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    zat = lambda x, y: Z0 + q[int(round((y - TER_Y0) / TER_SQUARE)), int(round((x - TER_X0) / TER_SQUARE))] / 65535.0 * MAXH
    forest = np.isin(lay, [names.index(m) for m in ("ForestFloor", "ForestFloor2")])
    spawns = {o["name"]: o["position"] for o in pl.read_items(zi, f"{LV}/main/MissionGroup/PlayerDropPoints/items.level.json")}
    roads = [o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/AIRoads/items.level.json") if o.get("class") == "DecalRoad"]
    S = [s for s in (pl.sample(o["nodes"], 5.0) for o in roads) if s is not None]
    P, T = np.concatenate([s[0] for s in S]), np.concatenate([s[1] for s in S])
    near = np.hypot(*(P[:, :2] - np.asarray(spawns["spawn_arosio"][:2])).T) < 1500
    best, score = None, -1
    for k in np.flatnonzero(near):
        nrm = np.array([T[k][1], -T[k][0]])
        pts = P[k, :2] + np.outer(np.r_[np.arange(-30, -4, 3), np.arange(5, 31, 3)], nrm)
        c = np.round((pts[:, 0] - TER_X0) / TER_SQUARE).astype(int)
        r = np.round((pts[:, 1] - TER_Y0) / TER_SQUARE).astype(int)
        f = forest[r, c].mean()
        if f > score:
            best, score = k, f
    p, t = P[best], T[best]
    out = [{"name": "forest_road", "forest_share": round(float(score), 2),
            "cam": [round(float(p[0] - 10 * t[0]), 2), round(float(p[1] - 10 * t[1]), 2), round(float(p[2] + 1.5), 2)],
            "target": [round(float(p[0] + 40 * t[0]), 2), round(float(p[1] + 40 * t[1]), 2), round(float(p[2] + 1.0), 2)],
            "fov": 65.0}]
    g, a = np.asarray(spawns["spawn_gravesano"][:3]), np.asarray(spawns["spawn_arosio"][:3])
    d = (a[:2] - g[:2]) / np.linalg.norm(a[:2] - g[:2])
    tg = g[:2] + 1200 * d
    out.append({"name": "pass_gravesano", "cam": [round(float(g[0]), 2), round(float(g[1]), 2), round(float(g[2] + 25), 2)],
                "target": [round(float(tg[0]), 2), round(float(tg[1]), 2), round(float(zat(*tg)), 2)], "fov": 60.0})
    ag = np.asarray(spawns["spawn_agno"][:2])
    cam = ag + np.array([350.0, -500.0])                                  # over the lake, south-east of Agno
    out.append({"name": "lake_malcantone", "cam": [round(float(cam[0]), 2), round(float(cam[1]), 2), 285.0],
                "target": [round(float(cam[0] - 2500), 2), round(float(cam[1] + 600), 2), 420.0], "fov": 60.0})
    for s in out:
        print(s)
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
                near = 300.0 if s["name"] == "forest_road" else 400.0      # beyond: the coarse terrain only
                R.shot(render3d.Camera.look(s["cam"], s["target"], fov=s["fov"]), os.path.join(out, f"{tag}_{s['name']}.jpg"),
                       near=near, far=3500.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "patch_understory.py"))):
            im.paste(a, (k * (w + 8), 0))
            ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28, stroke_width=2,
                                    stroke_fill="black")
        f = os.path.join(out, f"compare_{s['name']}.jpg")
        im.resize((w, h // 2)).save(f, quality=86)
        print(f, flush=True)


def views(zp, tag):
    out = [{"kind": "view", "name": f"{tag}_{s['name']}", "cam": s["cam"], "target": s["target"], "fov": s["fov"],
            "wait": 12.0, "fps": True} for s in json.load(open(SITES))]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views}[cmd](*args)
