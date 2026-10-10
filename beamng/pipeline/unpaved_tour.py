"""The camera tour and the drives of the in-game check of the unpaved tracks (network_mesh.unpaved_step, v2.7;
run_unpaved_screenshots.ps1, bng_lua/magliaso_unpaved.lua).
    python unpaved_tour.py sites <zip before the patch>         -> verifica/v2.7/unpaved/sites.json
    python unpaved_tour.py views <zip> <tag>                     -> <user>/magliaso_unpaved_views.json
sites: near the spawn points above Pura, Bedigliora, Cademario and Arosio, the closest outer edge of an
unpaved track (a dirt or gravel road at least 3 m wide, straight for 8 m both ways, on gentle ground)
where the edge stood 0.2-0.6 m over the ground; near Cademario also an edge between gravel and asphalt.
views: per site the view of a driver on the track, one from 3.5 m over the ground beside it and one
at 0.4 m over the ground looking at the edge, and a drive (sites with an outer edge) across the edge
at 35 degrees; heights from the zip itself (track or terrain under the camera).
"""
import json, math, os, sys, zipfile
import numpy as np
import network_mesh as pu
import road_mesh
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
SITES = os.path.join(HERE, "..", "verifica", "v2.7", "unpaved", "sites.json")
OUT = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"
SPAWNS = ("spawn_pura", "spawn_bedigliora", "spawn_cademario", "spawn_arosio")


def load(zp):
    zi = zipfile.ZipFile(zp)
    objs = pu.read_items(zi, f"{LV}/main/MissionGroup/roads/surfaces/items.level.json")
    un, al = pu.top_faces(zi, objs)
    blk = next(o for o in pu.read_items(zi, f"{LV}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q = pu.read_ter(zi.read(f"{LV}/theTerrain.ter"))
    spawns = {o["name"]: o["position"] for o in pu.read_items(zi, f"{LV}/main/MissionGroup/PlayerDropPoints/items.level.json")}
    return zi, un, al, q, spawns


def edges(un):
    """Boundary edges of the unpaved top faces: midpoints (k, 3), unit direction (k, 2), outward normal (k, 2), length."""
    P = un.reshape(-1, 3)
    key = np.round(P[:, :2] * 1000).astype(np.int64)
    _, pid = np.unique(key, axis=0, return_inverse=True)
    pid = pid.reshape(-1, 3)
    E = np.concatenate([pid[:, [0, 1]], pid[:, [1, 2]], pid[:, [2, 0]]])
    V = np.concatenate([un[:, [0, 1]], un[:, [1, 2]], un[:, [2, 0]]])
    F = np.tile(np.arange(len(un)), 3)
    _, inv, cnt = np.unique(np.sort(E, 1), axis=0, return_inverse=True, return_counts=True)
    b = cnt[inv.ravel()] == 1
    A, B, F = V[b, 0], V[b, 1], F[b]
    mid = 0.5 * (A + B)
    d = B[:, :2] - A[:, :2]
    ln = np.linalg.norm(d, axis=1)
    t = d / np.maximum(ln, 1e-9)[:, None]
    n = np.column_stack([t[:, 1], -t[:, 0]])
    cen = un[F].mean(1)
    n *= np.where(((mid[:, :2] - cen[:, :2]) * n).sum(1) < 0, -1.0, 1.0)[:, None]
    return mid, t, n, ln


def sites(zp):
    zi, un, al, q, spawns = load(zp)
    UN, ALL = road_mesh.TriSurface(un), road_mesh.TriSurface(al)
    mid, t, n, ln = edges(un)
    out = []
    at = lambda S, p: S.height(p[:, 0], p[:, 1], "low")
    for name in SPAWNS:
        s = np.asarray(spawns[name][:2])
        dist = np.hypot(*(mid[:, :2] - s).T)
        c = np.flatnonzero((ln > 0.5) & (dist > 60) & (dist < 700))
        c = c[np.argsort(dist[c])]
        m, tt, nn = mid[c, :2], t[c], n[c]
        ok = np.isnan(at(ALL, m + 0.1 * nn))                           # ground beyond the edge
        for k in (1.5, 3.0):
            ok &= np.isfinite(at(UN, m - k * nn))                      # 3 m of track inside
        for s8 in (-8.0, 8.0):
            ok &= np.isfinite(at(UN, m - 1.5 * nn + s8 * tt))          # straight 8 m both ways
        g1 = pu.terrain_top(q, *(m + 0.3 * nn).T)
        g3 = pu.terrain_top(q, *(m + 3.0 * nn).T)
        gap = mid[c, 2] - g1
        ok &= (gap > 0.2) & (gap < 0.6) & (np.abs(g3 - g1) < 0.8)
        dr = tt * math.cos(math.radians(35)) + nn * math.sin(math.radians(35))
        ok &= np.isfinite(at(UN, m - 6.0 * dr)) & np.isfinite(at(UN, m - 3.0 * dr))
        i = np.flatnonzero(ok)
        if not len(i):
            print(name, "no site"); continue
        i = i[0]
        out.append({"name": name.replace("spawn_", ""), "kind": "edge", "p": m[i].tolist(), "t": tt[i].tolist(),
                    "n": nn[i].tolist(), "gap_before": round(float(gap[i]), 2), "spawn_dist": round(float(dist[c[i]]), 1)})
        print(out[-1])
    # gravel / dirt against asphalt near Cademario
    s = np.asarray(spawns["spawn_cademario"][:2])
    dist = np.hypot(*(mid[:, :2] - s).T)
    c = np.flatnonzero((ln > 0.5) & (dist < 1500))
    c = c[np.argsort(dist[c])]
    m, nn, tt = mid[c, :2], n[c], t[c]
    ok = np.isfinite(at(ALL, m + 1.0 * nn)) & np.isnan(at(UN, m + 1.0 * nn)) & np.isfinite(at(UN, m - 6.0 * nn))
    i = np.flatnonzero(ok)
    if len(i):
        i = i[0]
        out.append({"name": "junction_cademario", "kind": "junction", "p": m[i].tolist(), "t": tt[i].tolist(),
                    "n": nn[i].tolist(), "spawn_dist": round(float(dist[c[i]]), 1)})
        print(out[-1])
    os.makedirs(os.path.dirname(SITES), exist_ok=True)
    json.dump(out, open(SITES, "w"), indent=1)
    print(SITES, len(out), "sites")


def views(zp, tag):
    zi, un, al, q, _ = load(zp)
    UN = road_mesh.TriSurface(un)
    ALLS = road_mesh.TriSurface(al)

    def h(p):
        """Track (any road face) under p, else the terrain."""
        z = ALLS.height([p[0]], [p[1]], "high")[0]
        return float(z) if np.isfinite(z) else float(pu.terrain_top(q, np.array([p[0]]), np.array([p[1]]))[0])
    out = []
    for s in json.load(open(SITES)):
        p, t, n = (np.asarray(s[k]) for k in ("p", "t", "n"))
        nm = f"{tag}_{s['name']}"
        P = lambda v, dz: [round(float(v[0]), 2), round(float(v[1]), 2), round(h(v) + dz, 2)]
        if s["kind"] == "edge":
            out.append({"kind": "view", "name": nm + "_driver", "cam": P(p - 1.8 * n - 9 * t, 1.5),
                        "target": P(p - 0.3 * n + 6 * t, 0.0), "fov": 65, "wait": 9.0})
            out.append({"kind": "view", "name": nm + "_above", "cam": P(p + 5 * n - 4 * t, 3.5),
                        "target": P(p, 0.0), "fov": 55, "wait": 6.0})
            out.append({"kind": "view", "name": nm + "_low", "cam": P(p + 2.5 * n - 1.0 * t, 0.4),
                        "target": P(p - 0.6 * n + 1.0 * t, 0.0), "fov": 50, "wait": 6.0})
            dr = t * math.cos(math.radians(35)) + n * math.sin(math.radians(35))
            st = p - 6.0 * dr
            out.append({"kind": "drive", "name": nm + "_drive", "pos": P(st, 0.6), "dir": [round(float(x), 4) for x in dr],
                        "throttle": 0.35, "time": 4.0, "cam": P(p + 7 * n - 6 * t, 4.0), "target": P(p, 0.0), "fov": 60})
        else:
            out.append({"kind": "view", "name": nm + "_driver", "cam": P(p - 9 * n, 1.5),
                        "target": P(p + 6 * n, 0.0), "fov": 65, "wait": 9.0})
            out.append({"kind": "view", "name": nm + "_above", "cam": P(p - 4 * n + 5 * t, 3.5),
                        "target": P(p, 0.0), "fov": 55, "wait": 6.0})
    json.dump(out, open(OUT, "w"), indent=1)
    print(OUT, len(out), "entries")


if __name__ == "__main__":
    if sys.argv[1] == "sites":
        sites(sys.argv[2])
    else:
        views(sys.argv[2], sys.argv[3])
