"""The views of the check of buildings_mesh.house_details_step (v2.8): gutters, downpipes, aerials, dishes, solar panels.
    python houses_tour.py sites <zip after>                     -> verifica/v2.8/houses/sites.json
    python houses_tour.py render <level before> <level after>  -> verifica/v2.8/houses/render3d/
    python houses_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: near the spawn points of Gravesano, Magliaso and Caslano, the nearest TV aerial and the nearest solar panels
the patch put up (the details in the patched zip), seen from 24 m away and a few metres over the roof (the
aerials: the nearest one seen from 30 m with no roof within 2 m under the line of sight); and a driver
on the street nearest the spawn of Magliaso, looking along it past the houses.
render: before and after with render3d.py (textured), side by side (compare_<site>.jpg).
views: the same views for the in-game tour of run_houses_screenshots.ps1 (bng_lua/magliaso_unpaved.lua), with the
frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import optimize_level
import lamps as pl
import wall_fill_tour as wft
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "houses")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"


def details(zi):
    """{material: (k, 3) world vertices} of the house details of a patched zip."""
    out = {}
    for o in pl.read_items(zi, f"{LV}/main/MissionGroup/buildings/details/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o["position"], float)
        for m, idx in parts:
            out.setdefault(m, []).append(W[idx[:, 0]])
    return {m: np.concatenate(v) for m, v in out.items()}


def sites(zp):
    zi = zipfile.ZipFile(zp)
    D = details(zi)
    spawns = {o["name"]: np.asarray(o["position"], float)
              for o in pl.read_items(zi, f"{LV}/main/MissionGroup/PlayerDropPoints/items.level.json")}
    out = []
    for name, mat, kind in (("gravesano_aerial", "mp_house_metal", "aerial"), ("gravesano_pv", "mp_house_pv", "pv"),
                            ("caslano_pv", "mp_house_pv", "pv")):
        s = spawns["spawn_" + name.split("_")[0]]
        P = D[mat]
        order = np.argsort(np.hypot(*(P[:, :2] - s[:2]).T))
        seen, found = [], None
        for i in order:
            if any(np.hypot(*(P[i, :2] - q)) < 6 for q in seen):
                continue
            seen.append(P[i, :2])
            near = P[np.hypot(*(P[:, :2] - P[i, :2]).T) < 4]
            c, top = near.mean(0), near[:, 2].max()
            if kind == "pv":                                     # the panels face south: look from the south
                found = (np.r_[c[:2] + [6, -24], top + 10.0], np.r_[c[:2], top])
                break
            tgt = np.r_[c[:2], top - 1.5]
            ob = wft.obstacles(zi, tgt)
            for a in np.radians(np.arange(225, 225 + 360, 45)):  # no roof within 2 m under the line of sight
                cam = np.r_[c[:2] + 30 * np.array([np.cos(a), np.sin(a)]), top + 4.0]
                v = tgt - cam
                Q = cam + np.linspace(0, 0.85, 40)[:, None] * v
                h = ob.height(Q[:, 0], Q[:, 1], "high")
                if not (np.isfinite(h) & (h > Q[:, 2] - 2.0)).any():
                    found = (cam, tgt)
                    break
            if found is not None or len(seen) >= 30:
                break
        cam, tgt = found
        out.append({"name": name, "cam": [round(float(v), 2) for v in cam], "target": [round(float(v), 2) for v in tgt],
                    "fov": 40.0 if kind == "aerial" else 55.0})
        print(out[-1])
    # a street in Magliaso: the AI road node nearest the spawn, looking along the road
    s = spawns["spawn_magliaso_paese"]
    best = None
    for f in zi.namelist():
        if f.startswith(f"{LV}/main/MissionGroup/AIRoads") and f.endswith("items.level.json"):
            for o in pl.read_items(zi, f):
                if o.get("class") != "DecalRoad" or len(o.get("nodes", [])) < 4:
                    continue
                N = np.asarray(o["nodes"], float)
                d = np.hypot(*(N[1:-2, :2] - s[:2]).T)
                k = int(np.argmin(d)) + 1
                if best is None or d[k - 1] < best[0]:
                    best = (d[k - 1], N, k)
    _, N, k = best
    t = (N[k + 1, :2] - N[k, :2]) / np.linalg.norm(N[k + 1, :2] - N[k, :2])
    out.append({"name": "magliaso_street", "cam": [round(float(v), 2) for v in np.r_[N[k, :2] - t * 6, N[k, 2] + 1.5]],
                "target": [round(float(v), 2) for v in np.r_[N[k, :2] + t * 40, N[k + 1, 2] + 3.0]], "fov": 65.0})
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
                       near=250.0, far=3000.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "buildings_mesh.house_details_step"))):
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
