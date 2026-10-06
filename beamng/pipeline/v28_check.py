"""The check of the chained v2.8 build (patch_v2_8.py) against the nine patches run alone on the v2.7 zip.
    python v28_check.py <v2.7 zip> <v2.8 zip> <reports dir of patch_v2_8.py>   -> verifica/v2.8/build/check.json
- the counts of every patch's report in the chain and alone (beamng/verifica/v2.8/<topic>/report.json);
- the entries of the zip added and changed against v2.7;
- the new objects that stand on the ground (street lamps, delineators, wooden poles, signs): pairs of different
  kinds closer than 1 m;
- their feet against the v2.8 terrain (the terrain is 4 cm under the paved faces): the height of the foot over it at
  the object, for the chain and for the same patch alone (placed on the v2.7 terrain).
"""
import json, os, sys, zipfile
import numpy as np
from scipy.spatial import cKDTree
import patch_lamps as pl
import patch_unpaved as pu
import patch_wall_fill as pw
from config import LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
V28 = os.path.join(HERE, "..", "verifica", "v2.8")
LV = f"levels/{LEVEL_NAME}"
TOPIC = {"paved_edges": "paved_edges", "wall_fill": "wall_fill", "understory": "understory", "lamps": "lamps",
         "roadside": "roadside", "catenary": "catenary", "signs_more": "signs", "lake": "lake", "house_details": "houses"}


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


def main(z27, z28, reports):
    zi = zipfile.ZipFile(z28)
    blk = next(o for o in pl.read_items(zi, f"{LV}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    q = pw.read_ter(zi.read(f"{LV}/theTerrain.ter"))[1]
    a = {i.filename: i.CRC for i in zipfile.ZipFile(z27).infolist()}
    b = {i.filename: i.CRC for i in zi.infolist()}
    out = {"entries": {"v2.7": len(a), "v2.8": len(b), "added": len(set(b) - set(a)), "removed": len(set(a) - set(b)),
                       "changed": sum(1 for f in set(a) & set(b) if a[f] != b[f])}, "reports": {}, "feet": {}}
    chain_pts, alone_pts = {}, {}
    for name, topic in TOPIC.items():
        rc = json.load(open(os.path.join(reports, f"{name}_report.json")))
        ra = json.load(open(os.path.join(V28, topic, "report.json")))
        nc, na = numbers(rc), numbers(ra)
        out["reports"][name] = {k: [na.get(k), nc.get(k)] for k in sorted(set(nc) | set(na)) if nc.get(k) != na.get(k)}
        chain_pts.update(points(rc, name))
        alone_pts.update(points(ra, name))
    # pairs of different kinds closer than 1 m
    kinds = sorted(chain_pts)
    near = {}
    for i, k1 in enumerate(kinds):
        t = cKDTree(chain_pts[k1][:, :2])
        for k2 in kinds[i + 1:]:
            d, _ = t.query(chain_pts[k2][:, :2], distance_upper_bound=1.0)
            near[f"{k1}-{k2}"] = int(np.isfinite(d).sum())
    out["closer_than_1m"] = near
    # the feet over the v2.8 terrain
    for tag, P in (("chain", chain_pts), ("alone", alone_pts)):
        for k, X in P.items():
            dz = X[:, 2] - pu.terrain_top(q, X[:, 0], X[:, 1])
            out["feet"].setdefault(k, {})[tag] = {
                "n": len(X), "median_m": round(float(np.median(dz)), 3),
                "p05_m": round(float(np.percentile(dz, 5)), 3), "p95_m": round(float(np.percentile(dz, 95)), 3),
                "under_ground_by_5cm": int((dz < -0.05).sum()), "over_ground_by_50cm": int((dz > 0.5).sum())}
    os.makedirs(os.path.join(V28, "build"), exist_ok=True)
    json.dump(out, open(os.path.join(V28, "build", "check.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
