"""The fixed plan of the Ticino streaming level (zones/ticino_plan.json): what every zone slice (region_slice.py) and
the base (region_base.py) must agree on without seeing each other.

    z0, maxHeight     one height scale for every terrain block (uint16 over [z0, z0 + maxHeight])
    layers            the terrain materials by internalName, in the order of the blocks' layer bytes
    forestTypes       the forest item types, in the order of the forest tiles' type numbers
    groundTypes       the collision cells' ground types, in the order of their type bytes
    zones             the zones of the level (their zip on the draft release ticino-zones; the zones that failed to
                      build, Italy without roads, are not there)

The lists only grow (--add): a new zone's new layer goes to the end, so the slices already built stay valid. Changing
z0 / maxHeight or the order of a list means building every slice again.

    python region_plan.py [--add] [--cache <folder>]       (reads the zone zips by HTTP range, about a minute)
"""
import argparse
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blocks  # noqa: E402
import zipremote  # noqa: E402

PLAN = os.path.join(HERE, "zones", "ticino_plan.json")
TAG = "ticino-zones"
# Lake Maggiore lies at 193 m and Lake Lugano at 271: a lake bed under 150 m is clipped there (out of sight under the
# water). Two zones carve far lower (ti_1_2 -116 m, ti_m3_9 -704 m: not real ground). The zones' terrains reach the
# peaks round the canton (3,633 m): 150 + 3,500 m. One step is 5.3 cm (the Malcantone level alone had 1 cm).
Z0, MAXH = 150.0, 3500.0
SMALL = ("theTerrain.terrain.json", "art/forest/managedItemData.json")


def zone_names(names):
    return sorted(n[:-4] for n in names if re.fullmatch(r"ti_[m0-9]+_[m0-9]+\.zip", n))


def fetch(zone, asset_id, cache):
    """The zone's scene, terrain json, forest item data and material files under cache/<zone>/levels/<zone>/."""
    out = os.path.join(cache, zone)
    if os.path.exists(os.path.join(out, "done")):
        return zone
    zf = zipremote.open_zip(asset_id)
    pre = f"levels/{zone}/"
    want = [i.filename for i in zf.infolist() if not i.filename.endswith("/") and (
        i.filename.startswith(pre + "main/") or i.filename.endswith("materials.json")
        or i.filename[len(pre):] in SMALL)]
    zipremote.extract(zf, want, out)
    open(os.path.join(out, "done"), "w").write("1")
    return zone


def scan(zone, cache):
    ld = os.path.join(cache, zone, "levels", zone)
    sc = blocks.scene_files(ld)
    tb = next(o for objs in sc.values() for o in objs if o.get("class") == "TerrainBlock")
    z0 = float(tb["position"][2])
    lay = json.load(open(os.path.join(ld, "theTerrain.terrain.json")))["materials"]
    p = os.path.join(ld, "art", "forest", "managedItemData.json")
    ft = sorted(json.load(open(p))) if os.path.exists(p) else []
    gt = set()
    for p in glob.glob(os.path.join(ld, "**", "*materials.json"), recursive=True):
        for m in json.load(open(p, encoding="utf-8")).values():
            if isinstance(m, dict) and m.get("groundType"):
                gt.add(str(m["groundType"]).upper())
    return {"z0": z0, "top": z0 + float(tb["maxHeight"]), "layers": lay, "forest": ft, "ground": sorted(gt)}


def grow(lst, new):
    for v in new:
        if v not in lst:
            lst.append(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", action="store_true", help="keep the plan's lists and append what is new")
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "ticino_plan_cache"))
    a = ap.parse_args()
    ids = zipremote.assets(TAG)
    zones = zone_names(ids)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda z: fetch(z, ids[z + ".zip"], a.cache), zones))
    old = json.load(open(PLAN)) if a.add and os.path.exists(PLAN) else {}
    plan = {"z0": old.get("z0", Z0), "maxHeight": old.get("maxHeight", MAXH), "layers": list(old.get("layers", [])),
            "forestTypes": list(old.get("forestTypes", [])), "groundTypes": list(old.get("groundTypes", ["default"])),
            "zones": list(old.get("zones", []))}
    heights = {}
    for z in zones:
        r = scan(z, a.cache)
        heights[z] = [r["z0"], r["top"]]
        grow(plan["layers"], r["layers"])
        grow(plan["forestTypes"], r["forest"])
        grow(plan["groundTypes"], r["ground"])
        grow(plan["zones"], [z])
    assert len(plan["layers"]) < 255 and len(plan["groundTypes"]) < 256
    top = plan["z0"] + plan["maxHeight"]
    over = {z: h for z, h in heights.items() if h[1] > top}
    assert not over, f"zones higher than the plan's top {top}: {over}"
    plan["zoneHeights"] = {z: heights.get(z) for z in plan["zones"]}
    with open(PLAN, "w") as f:
        json.dump(plan, f, indent=1)
    print(len(plan["zones"]), "zones,", len(plan["layers"]), "layers,", len(plan["forestTypes"]), "forest types,",
          len(plan["groundTypes"]), "ground types; clipped at", plan["z0"], ":",
          {z: h[0] for z, h in heights.items() if h[0] < plan["z0"]})


if __name__ == "__main__":
    main()
