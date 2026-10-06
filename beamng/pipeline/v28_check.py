"""The check of the chained v2.8 build (patch_v2_8.py): the nine patches together, against each other and against
the same patches run alone on the v2.7 zip.
    python v28_check.py <v2.7 zip> <v2.8 zip> <reports dir of patch_v2_8.py>   -> verifica/v2.8/build/check.json
- reports: the numbers of every patch's report that differ between the chain and alone
  (beamng/verifica/v2.8/<topic>/report.json);
- entries: the entries of the zip added and changed against v2.7;
- feet: the new objects that stand on the ground (street lamps, delineators, wooden poles, signs), the height of their
  foot over the v2.8 terrain (the terrain is 4 cm under the paved faces), for the chain and for the same patch alone
  (placed on the v2.7 terrain); and the 73 street lamps of v2.7, over the v2.7 and the v2.8 terrain;
- clearances, on the v2.8 zip: feet of two kinds closer than 1 m; feet within 0.5 m of the steel of a catenary mast;
  feet on the ballast of the railway (within half a sleeper and 0.35 m of the nearest sleeper); lamp columns (foot to
  head, 8.75 m) with a wooden pole's cable or a gutter or downpipe within 0.3 m; cables under a roof (through a house).
"""
import json, os, sys, zipfile
import numpy as np
from scipy.spatial import cKDTree
import optimize_level
import patch_catenary as pc
import patch_lamps as pl
import patch_unpaved as pu
import patch_wall_fill as pw
import road_mesh
from config import LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
V28 = os.path.join(HERE, "..", "verifica", "v2.8")
LV = f"levels/{LEVEL_NAME}"
MG = f"{LV}/main/MissionGroup"
TOPIC = {"paved_edges": "paved_edges", "wall_fill": "wall_fill", "understory": "understory", "lamps": "lamps",
         "roadside": "roadside", "catenary": "catenary", "signs_more": "signs", "lake": "lake", "house_details": "houses"}
COLUMN = pl.HEAD[1]           # m, lamp head over the foot


def numbers(d, p=""):
    """The numbers of a report (not the lists), flattened."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(numbers(v, p + k + "."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[p + k] = v
    return out


def points(r, name):
    """{kind: (k, 3)} of the objects on the ground in the report of patch `name`."""
    if name == "lamps":
        return {"lamp": np.array([p[:3] for p in r["lamps"]], float).reshape(-1, 3)}
    if name == "roadside":
        return {"delineator": np.array(r["delineator_posts"], float).reshape(-1, 3),
                "wooden_pole": np.array(r["poles"], float).reshape(-1, 3)}
    if name == "signs_more":
        return {"sign": np.array([[s["x"], s["y"], s["z"]] for s in r["signs"]], float).reshape(-1, 3)}
    return {}


def edge_samples(zi, group, mats, step=0.1, shape=None):
    """Points every `step` m along the triangle edges of the materials `mats` of the pipeline shapes of a group."""
    f = f"{MG}/{group}/items.level.json"
    out = []
    if f not in zi.NameToInfo:
        return np.zeros((0, 3))
    for o in pl.read_items(zi, f):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or (shape and shape not in sn):
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for m, idx in parts:
            if m not in mats:
                continue
            t = W[idx[:, 0]].reshape(-1, 3, 3)
            for a, b in ((0, 1), (1, 2), (2, 0)):
                k = np.maximum(np.ceil(np.linalg.norm(t[:, b] - t[:, a], axis=1) / step).astype(int), 1)
                for kk in np.unique(k):
                    s = k == kk
                    u = np.linspace(0, 1, kk + 1)
                    out.append((t[s, a][:, None] + u[None, :, None] * (t[s, b] - t[s, a])[:, None]).reshape(-1, 3))
    return np.unique(np.round(np.concatenate(out), 2), axis=0) if out else np.zeros((0, 3))


def columns_hit(feet, P, r, lo=0.3, hi=COLUMN + 0.2):
    """Indices of the feet with a point of P within r (xy) between lo and hi m over the foot."""
    if not len(P):
        return []
    near = cKDTree(P[:, :2]).query_ball_point(feet[:, :2], r)
    return [k for k, j in enumerate(near) if j and ((P[j, 2] - feet[k, 2] > lo) & (P[j, 2] - feet[k, 2] < hi)).any()]


def places(P, cell=10.0):
    return len({(int(x // cell), int(y // cell)) for x, y in P[:, :2]})


def terrain_of(zi):
    blk = next(o for o in pl.read_items(zi, f"{MG}/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    q = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))[1]
    return lambda x, y: pu.terrain_top(q, np.atleast_1d(x), np.atleast_1d(y))


def feet_stats(dz):
    return {"n": len(dz), "median_m": round(float(np.median(dz)), 3), "p05_m": round(float(np.percentile(dz, 5)), 3),
            "p95_m": round(float(np.percentile(dz, 95)), 3), "under_ground_by_5cm": int((dz < -0.05).sum()),
            "under_ground_by_15cm": int((dz < -0.15).sum()), "over_ground_by_50cm": int((dz > 0.5).sum())}


def main(z27, z28, reports):
    za, zi = zipfile.ZipFile(z27), zipfile.ZipFile(z28)
    a = {i.filename: i.CRC for i in za.infolist()}
    b = {i.filename: i.CRC for i in zi.infolist()}
    out = {"entries": {"v2.7": len(a), "v2.8": len(b), "added": len(set(b) - set(a)), "removed": len(set(a) - set(b)),
                       "changed": sum(1 for f in set(a) & set(b) if a[f] != b[f])}, "reports": {}, "feet": {},
           "clearances": {}}
    chain_pts, alone_pts = {}, {}
    for name, topic in TOPIC.items():
        rc = json.load(open(os.path.join(reports, f"{name}_report.json")))
        ra = json.load(open(os.path.join(V28, topic, "report.json")))
        nc, na = numbers(rc), numbers(ra)
        out["reports"][name] = {k: [na.get(k), nc.get(k)] for k in sorted(set(nc) | set(na)) if nc.get(k) != na.get(k)}
        chain_pts.update(points(rc, name))
        alone_pts.update(points(ra, name))

    # the feet over the terrain
    t27, t28 = terrain_of(za), terrain_of(zi)
    for tag, P in (("chain", chain_pts), ("alone", alone_pts)):
        for k, X in P.items():
            out["feet"].setdefault(k, {})[tag] = feet_stats(X[:, 2] - t28(X[:, 0], X[:, 1]))
    old = np.array([o["position"] for o in pl.read_items(za, f"{MG}/props/street_lights/items.level.json")
                    if o.get("class") == "TSStatic" and o.get("shapeName") == pl.LIGHT], float).reshape(-1, 3)
    out["feet"]["lamp_v2.7"] = {"v2.7_terrain": feet_stats(old[:, 2] - t27(old[:, 0], old[:, 1])),
                                "v2.8_terrain": feet_stats(old[:, 2] - t28(old[:, 0], old[:, 1]))}

    # clearances
    cl = out["clearances"]
    kinds = sorted(chain_pts)
    for i, k1 in enumerate(kinds):
        t = cKDTree(chain_pts[k1][:, :2])
        for k2 in kinds[i + 1:]:
            d, _ = t.query(chain_pts[k2][:, :2], distance_upper_bound=1.0)
            cl[f"feet_closer_than_1m.{k1}-{k2}"] = int(np.isfinite(d).sum())
    masts = edge_samples(zi, "railway", {"mp_catenary_steel"}, shape="catenary_masts")
    C, Ls = pc.sleepers(zi, LV)
    half, st = np.where(Ls < 2.25, 0.95, 1.30), cKDTree(C[:, :2])
    for k, X in chain_pts.items():
        cl[f"feet_near_mast_steel_0.5m.{k}"] = len(columns_hit(X, masts, 0.5, lo=-1.0, hi=12.0))
        d, j = st.query(X[:, :2])
        cl[f"feet_on_the_ballast.{k}"] = int((d < half[j] + 0.35).sum())
    lamps = chain_pts["lamp"]
    cables = edge_samples(zi, "props/delineators", {"mp_cable"}, step=0.5)
    gutters = edge_samples(zi, "buildings/details", {"mp_house_zinc", "mp_house_copper"})
    for r in (0.2, 0.5):
        cl[f"lamp_columns_with_a_cable_within_{r}m"] = len(columns_hit(lamps, cables, r))
    for r in (0.15, 0.3):
        cl[f"lamp_columns_with_a_gutter_or_downpipe_within_{r}m"] = len(columns_hit(lamps, gutters, r))
    roof = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, LV, ["buildings"]).values())))
    h = roof.height(cables[:, 0], cables[:, 1], "high")
    under = cables[np.isfinite(h) & (h > cables[:, 2])]
    cl["cable_points_under_a_roof"] = len(under)
    cl["cable_places_under_a_roof"] = places(under)
    cl["cable_points"] = len(cables)

    os.makedirs(os.path.join(V28, "build"), exist_ok=True)
    json.dump(out, open(os.path.join(V28, "build", "check.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("entries", "clearances")}, indent=1))
    print(json.dumps(out["feet"]))


if __name__ == "__main__":
    main(*sys.argv[1:4])
