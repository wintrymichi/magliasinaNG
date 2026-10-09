"""The places and views of the check of walls.wall_fill_step (v2.8): the ground behind the retaining walls
shaded like the terrain, and no game grass under it or over the walls.
    python wall_fill_tour.py sites <zip before the patch>        -> verifica/v2.8/wall_fill/sites.json
    python wall_fill_tour.py render <level before> <level after>  -> verifica/v2.8/wall_fill/render3d/
    python wall_fill_tour.py grass <zip before> <zip after>       -> verifica/v2.8/wall_fill/grass_<site>.png
    python wall_fill_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: the three places of the first in-game report (Ponte Tresa, the walls along the lake at Agno, the
cantonal road to Pura behind the guard rail): there, the backfill a driver sees (4-20 m from a road face,
from 2 m under it to 8 m over it; at Agno within 8 m of the lake level, on the cantonal road within 10 m of
its guard rails), the 10 m square with the most of it within 25 m that a driver sees with no roof or wall
top in the way; its views: a driver on the road 9-25 m along it from the road face most of it is seen
from, and a view from 16 m above, on the road side where that is clear.
render: per site the two views before and after, with render3d.py (no game textures; the DAE normals, as
in the game; the colour of the terrain layers where WORK has no orthophoto; the view from above without
the trees, which would hide the ground), and the two side by side (compare_<site>_<view>.jpg).
grass: per site a map 60 m wide of the terrain layers, the vertices that lose the game grass in magenta.
views: the same views for the in-game tour of run_wall_fill_screenshots.ps1 (bng_lua/magliaso_unpaved.lua).
"""
import json, os, sys, zipfile
import numpy as np
import optimize_level
import network_mesh as pu
import walls as pw
import road_mesh
from config import BEAMNG_USER, LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "wall_fill")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"
GUARDRAILS = os.path.join(HERE, "..", "dati", "guardrails_final.json")
# name: (spawn point the place is around, radius m)
PLACES = {"ponte_tresa": ("spawn_ponte_tresa", 500.0), "agno_lake": ("spawn_agno", 900.0),
          "cantonale_pura": ("spawn_mid", 1400.0)}
BIN = 10.0            # m, squares the backfill is counted in
NEAR = 25.0           # m around a square: the backfill seen from one place


def fill_triangles(zi):
    """Centroids (k, 3) and areas (k,) of the backfill triangles of a zip."""
    cen, area = [], []
    for o in pu.read_items(zi, f"{LV}/main/MissionGroup/walls/items.level.json"):
        sn = o.get("shapeName", "")
        if "/art/shapes/walls/backfill" not in sn:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn.lstrip("/")).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for _, idx in parts:
            t = W[idx[:, 0]].reshape(-1, 3, 3)
            cen.append(t.mean(1))
            area.append(0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1))
    return np.concatenate(cen), np.concatenate(area)


def sites(zp):
    zi = zipfile.ZipFile(zp)
    spawns = {o["name"]: o["position"] for o in pu.read_items(zi, f"{LV}/main/MissionGroup/PlayerDropPoints/items.level.json")}
    lake = max(o["position"][2] for o in pu.read_items(zi, f"{LV}/main/MissionGroup/level_objects/Water/items.level.json")
               if o.get("class") == "WaterBlock" and o.get("name", "").startswith("LagoDiLugano"))
    cen, area = fill_triangles(zi)
    _, al = pu.top_faces(zi, pu.read_items(zi, f"{LV}/main/MissionGroup/roads/surfaces/items.level.json"))
    road = al.mean(1)
    rails = np.concatenate([np.asarray(g["pts"])[:, :3] for g in json.load(open(GUARDRAILS))])
    from scipy.spatial import cKDTree
    rtree, gtree = cKDTree(road[:, :2]), cKDTree(rails[:, :2])
    ALLS = road_mesh.TriSurface(al)
    height = lambda q: ALLS.height([q[0]], [q[1]], "high")[0]
    out = []
    # backfill a driver sees: 4-20 m from a road face, from 2 m under it to 8 m over it
    d, j = rtree.query(cen[:, :2], distance_upper_bound=20.0)
    ok = np.isfinite(d)
    dz = np.full(len(cen), np.nan)
    dz[ok] = cen[ok, 2] - road[j[ok], 2]
    seen = ok & (d >= 4.0) & (dz > -2.0) & (dz < 8.0)
    for name, (spawn, radius) in PLACES.items():
        s = np.asarray(spawns[spawn][:2])
        m = seen & (np.hypot(*(cen[:, :2] - s).T) < radius)
        if name == "agno_lake":
            m &= cen[:, 2] < lake + 8.0
        if name == "cantonale_pura":
            m &= np.isfinite(gtree.query(cen[:, :2], distance_upper_bound=10.0)[0])
        c, a, jr = cen[m], area[m], j[m]
        u = np.unique(np.floor(c[:, :2] / BIN).astype(np.int64), axis=0)
        near = cKDTree(c[:, :2]).query_ball_point((u + 0.5) * BIN, NEAR)
        score = np.array([a[k].sum() for k in near])
        best = None
        for i in np.argsort(-score)[:40]:
            k = near[i]
            p = np.average(c[k], axis=0, weights=a[k])
            r = road[np.bincount(jr[k], a[k]).argmax()]              # the road face most of it is seen from
            # the road's direction there: the main axis of its faces within 15 m
            R = road[rtree.query_ball_point(r[:2], 15.0)][:, :2]
            t = np.linalg.svd(R - R.mean(0), full_matrices=False)[2][0]
            v = cameras(p, r, t, height, obstacles(zi, p))
            if v is None:
                continue
            best = {"name": name, "fill": [round(float(x), 2) for x in p], "road": [round(float(x), 2) for x in r],
                    "road_dir": [round(float(x), 4) for x in t], "fill_m2_within_25m": round(float(score[i]), 1),
                    "spawn": spawn,
                    "views": [{"view": n_, "cam": [round(float(x), 2) for x in cam], "target": [round(float(x), 2) for x in p],
                               "fov": fov} for n_, cam, fov in v]}
            break
        print(best)
        if best:
            out.append(best)
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out, open(SITES, "w"), indent=1)
    print(SITES, len(out), "sites")


_UP = {}               # shape -> its faces turned up, in the level's frame


def obstacles(zi, p, radius=120.0):
    """The faces turned up (roofs, wall tops) of the buildings and walls within radius m of p."""
    tris = []
    for g in ("buildings", "walls"):
        for o in pu.read_items(zi, f"{LV}/main/MissionGroup/{g}/items.level.json"):
            sn = o.get("shapeName", "").lstrip("/")
            pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
            if (o.get("class") != "TSStatic" or "/backfill" in sn or sn not in zi.NameToInfo
                    or np.hypot(*(pos[:2] - p[:2])) > radius + 600.0):     # tiles of up to 384 m
                continue
            if sn not in _UP:
                V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
                t = (V + pos)[np.concatenate([idx[:, 0] for _, idx in parts])].reshape(-1, 3, 3)
                n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                _UP[sn] = t[n[:, 2] > 0.3 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)]
            t = _UP[sn]
            tris.append(t[np.hypot(*(t.mean(1)[:, :2] - p[:2]).T) < radius])
    return road_mesh.TriSurface(np.concatenate(tris) if tris else np.zeros((0, 3, 3)))


def clear(obst, cam, tgt):
    """No roof or wall top over the line of sight from cam to 1 m before tgt."""
    v = tgt - cam
    k = max(int(np.linalg.norm(v) / 0.5), 3)
    P = cam + np.linspace(0.0, 1.0, k)[:k - 2, None] * v
    h = obst.height(P[:, 0], P[:, 1], "high")
    return not (np.isfinite(h) & (h > P[:, 2] + 0.05)).any()


def cameras(f, r, t, height, obst):
    """[(name, camera position, fov)] of the views of the backfill at f seen from the road face r (road
    direction t): a driver on the road 9-25 m along it, and a view from 16 m above, on the road side if
    that is clear; None when no driver sees it (a roof or a wall top in the way)."""
    drv = None
    for dist in (15.0, 12.0, 20.0, 9.0, 25.0):
        for sgn in (-1.0, 1.0):
            c = r[:2] + sgn * dist * t
            z = height(c)
            if not np.isfinite(z) or abs(z - r[2]) > 3.0:
                continue
            cam = np.r_[c, z + 1.5]
            if clear(obst, cam, f):
                drv = cam
                break
        if drv is not None:
            break
    if drv is None:
        return None
    d = f[:2] - r[:2]
    d /= max(np.linalg.norm(d), 1e-9)
    above = None
    for ang in (0, 45, -45, 90, -90, 180):
        a = np.radians(ang)
        e = np.array([d[0] * np.cos(a) - d[1] * np.sin(a), d[0] * np.sin(a) + d[1] * np.cos(a)])
        cam = np.r_[f[:2] - 14.0 * e, max(f[2], r[2]) + 16.0]
        if clear(obst, cam, f):
            above = cam
            break
    if above is None:
        above = np.r_[f[:2] - 14.0 * d, max(f[2], r[2]) + 16.0]
    return [("driver", drv, 65.0), ("above", above, 60.0)]


def render(before, after):
    import render3d
    out = os.path.join(OUT_DIR, "render3d")
    os.makedirs(out, exist_ok=True)
    S = json.load(open(SITES))
    for tag, lv in (("before", before), ("after", after)):
        with render3d.Renderer(lv, W=1280, H=720, dae_normals=True) as R:
            for s in S:
                for v in s["views"]:
                    f = os.path.join(out, f"{tag}_{s['name']}_{v['view']}.jpg")
                    R.shot(render3d.Camera.look(v["cam"], v["target"], fov=v["fov"]), f, near=300.0, far=2500.0,
                           trees=v["view"] != "above")
                    print(f, flush=True)
    # before | after side by side, labelled, for the pull request and the README
    from PIL import Image, ImageDraw
    for s in S:
        for v in s["views"]:
            ims = [Image.open(os.path.join(out, f"{t}_{s['name']}_{v['view']}.jpg")) for t in ("before", "after")]
            w, h = ims[0].size
            im = Image.new("RGB", (2 * w + 8, h), "white")
            for k, (a, label) in enumerate(zip(ims, ("v2.7", "walls.wall_fill_step"))):
                im.paste(a, (k * (w + 8), 0))
                ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28,
                                        stroke_width=2, stroke_fill="black")
            f = os.path.join(out, f"compare_{s['name']}_{v['view']}.jpg")
            im.resize((w, h // 2)).save(f, quality=86)
            print(f, flush=True)


def grass(zb, za):
    """A map of the terrain layers around every site, the vertices that lose the game grass in magenta."""
    from PIL import Image
    import render3d
    S = json.load(open(SITES))
    L = {}
    for tag, zp in (("before", zb), ("after", za)):
        zi = zipfile.ZipFile(zp)
        n, q, lay, names = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))
        L[tag] = (lay, names)
    lay0, names = L["before"]
    lay1, _ = L["after"]
    lut = np.array([[round(255 * v) for v in render3d.LAYER_COLORS.get(m, (0.4, 0.45, 0.3))] for m in names], np.uint8)
    half = 30.0
    for s in S:
        x, y = s["fill"][:2]
        c0, c1 = int((x - half - TER_X0) / TER_SQUARE), int((x + half - TER_X0) / TER_SQUARE)
        r0, r1 = int((y - half - TER_Y0) / TER_SQUARE), int((y + half - TER_Y0) / TER_SQUARE)
        a, b = lay0[r0:r1, c0:c1], lay1[r0:r1, c0:c1]
        img = lut[a].copy()
        img[a != b] = (230, 40, 200)
        im = Image.fromarray(img[::-1]).resize((8 * (c1 - c0), 8 * (r1 - r0)), Image.NEAREST)
        f = os.path.join(OUT_DIR, f"grass_{s['name']}.png")
        im.save(f)
        print(f, int((a != b).sum()), "vertices")


def views(zp, tag):
    """The views of sites.json for the game (the patch moves no road; zp: the zip the game runs)."""
    out = [{"kind": "view", "name": f"{tag}_{s['name']}_{v['view']}", "cam": v["cam"], "target": v["target"],
            "fov": v["fov"], "wait": 9.0} for s in json.load(open(SITES)) for v in s["views"]]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "grass": grass, "views": views}[cmd](*args)
