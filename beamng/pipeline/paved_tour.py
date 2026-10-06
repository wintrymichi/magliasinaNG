"""The places and views of the check of patch_paved_edges.py (v2.8): paved edges flush with the ground.
    python paved_tour.py sites <zip before>                    -> verifica/v2.8/paved_edges/sites.json
    python paved_tour.py render <level before> <level after>  -> verifica/v2.8/paved_edges/render3d/
    python paved_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: near the spawn points of Magliaso, Agno and Cademario, the nearest outer edge of an asphalt road 60-700 m
away that stood 0.25-0.6 m over the terrain in v2.7, out of the keep-out zones of the patch (guard rails,
walls, buildings, ...), with road 3 m inside it; views: a driver 1.5 m over the road 12 m before it, and from 0.5 m
over the ground 4 m beyond the edge, looking along it.
render: before and after with render3d.py, side by side (compare_<site>_<view>.jpg).
views: the same views for the in-game tour of run_paved_screenshots.ps1 (bng_lua/magliaso_unpaved.lua), with
the frame rate of every view.
"""
import json, os, sys, zipfile
import numpy as np
import patch_lamps as pl
import patch_paved_edges as pp
import patch_unpaved as pu
import patch_wall_fill as pw
import road_mesh
import unpaved_tour
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "paved_edges")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"
SPAWNS = ("spawn_magliaso_paese", "spawn_agno", "spawn_cademario")


def sites(zp):
    zi = zipfile.ZipFile(zp)
    blk = next(o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))
    road = pl.faces(zi, LV, ["roads/surfaces"])
    asphalt = np.concatenate([road[m] for m in ("mp_road_asphalt",) if m in road])
    ALL = road_mesh.TriSurface(np.concatenate(list(road.values())))
    AS = road_mesh.TriSurface(asphalt)
    keep = pp.keep_out_cells(zi, LV)
    spawns = {o["name"]: o["position"] for o in pl.read_items(zi, f"{LV}/main/MissionGroup/PlayerDropPoints/items.level.json")}
    mid, t, n, ln = unpaved_tour.edges(asphalt)
    out = []
    for name in SPAWNS:
        s = np.asarray(spawns[name][:2])
        d = np.hypot(*(mid[:, :2] - s).T)
        c = np.flatnonzero((ln > 0.5) & (d > 60) & (d < 700))
        c = c[np.argsort(d[c])][:4000]
        m, tt, nn = mid[c, :2], t[c], n[c]
        ok = np.isnan(ALL.height(*(m + 0.1 * nn).T, "low")) & ~pu.in_cells(keep, m[:, 0], m[:, 1])
        for k in (3.0,):
            ok &= np.isfinite(AS.height(*(m - k * nn).T, "low"))
        for s8 in (-10.0, 10.0):
            ok &= np.isfinite(AS.height(*(m - 2.0 * nn + s8 * tt).T, "low"))
        gap = mid[c, 2] - pu.terrain_top(q, *(m + 0.3 * nn).T)
        ok &= (gap > 0.25) & (gap < 0.6)
        i = np.flatnonzero(ok)
        if not len(i):
            print(name, "no site")
            continue
        i = i[0]
        p, tv, nv = mid[c[i]], tt[i], nn[i]
        zg = float(pu.terrain_top(q, np.array([p[0] + 4 * nv[0]]), np.array([p[1] + 4 * nv[1]]))[0])
        cam, tgt = p[:2] - 2.5 * nv - 12 * tv, p[:2] - 1.0 * nv + 15 * tv
        zc, zt = (float(ALL.height([c[0]], [c[1]], "near", [p[2]])[0]) for c in (cam, tgt))
        drv = np.r_[cam, (zc if np.isfinite(zc) else p[2]) + 1.5]          # 1.5 m over the road where it is
        low = np.r_[p[:2] + 4.0 * nv - 3.0 * tv, zg + 0.5]
        out.append({"name": name.replace("spawn_", ""), "edge": [round(float(v), 2) for v in p], "gap_before": round(float(gap[i]), 2),
                    "views": [{"view": "driver", "cam": [round(float(v), 2) for v in drv],
                               "target": [round(float(v), 2) for v in np.r_[tgt, zt if np.isfinite(zt) else p[2]]], "fov": 65.0},
                              {"view": "low", "cam": [round(float(v), 2) for v in low],
                               "target": [round(float(v), 2) for v in np.r_[p[:2] + 6 * tv, p[2]]], "fov": 60.0}]})
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
                for v in s["views"]:
                    R.shot(render3d.Camera.look(v["cam"], v["target"], fov=v["fov"]),
                           os.path.join(out, f"{tag}_{s['name']}_{v['view']}.jpg"), near=200.0, far=2000.0)
    for s in S:
        for v in s["views"]:
            ims = [Image.open(os.path.join(out, f"{t}_{s['name']}_{v['view']}.jpg")) for t in ("before", "after")]
            w, h = ims[0].size
            im = Image.new("RGB", (2 * w + 8, h), "white")
            for k, (a, label) in enumerate(zip(ims, ("v2.7", "patch_paved_edges.py"))):
                im.paste(a, (k * (w + 8), 0))
                ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28, stroke_width=2,
                                        stroke_fill="black")
            f = os.path.join(out, f"compare_{s['name']}_{v['view']}.jpg")
            im.resize((w, h // 2)).save(f, quality=86)
            print(f, flush=True)


def views(zp, tag):
    out = [{"kind": "view", "name": f"{tag}_{s['name']}_{v['view']}", "cam": v["cam"], "target": v["target"],
            "fov": v["fov"], "wait": 8.0, "fps": True} for s in json.load(open(SITES)) for v in s["views"]]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views}[cmd](*args)
