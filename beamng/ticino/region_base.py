"""The base of the Ticino streaming level: the files of levels/ticino/ that are not one zone's (region_slice.py).

From the zone zips (draft release ticino-zones), read by HTTP range (zipremote.py: only the scene, the small json files,
the material files, the terrain textures and the shared textures, never the shapes or the .ter):
    main/ (the scene)       the objects that are not streamed (AI roads cut at the cores and welded across the core
                            edges, water, sounds, spawn points, the sky...), each from the zone whose core holds it
    signals.json, city.sites.json, facilities.sites.json, main.decals.json     per core (region_net.py)
    art/... materials       every zone's materials merged by name; the shared textures (first zone of the plan wins)
    art/terrains/           the window's terrain materials (zones/ticino_plan.json layers)
    art/forest/managedItemData.json, info.json (every spawn point), the preview
From the slices (draft release ticino-all, or local folders): their slice.json, merged into stream.json and the
warm-up lists, and the terrain blocks of the start window (start.ter). A zone with no slice is left out of the level.

    python region_base.py --out <folder> [--slices <folder with <zone>/levels/ticino/>] [--dist <folder>]
                          [--zones z1 z2 ...] [--cache <folder>]
"""
import argparse
import collections
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blocks  # noqa: E402
import collision  # noqa: E402
import region  # noqa: E402
import zipremote  # noqa: E402
from blocks import LEVEL, log, wopen  # noqa: E402

PLAN = os.path.join(HERE, "zones", "ticino_plan.json")
ZONES_TAG, SLICES_TAG = "ticino-zones", "ticino-all"
START_ZONE = "ti_0_m1"                  # Magliaso: the level starts at its default spawn point
SMALL = ("theTerrain.terrain.json", "info.json", "art/forest/managedItemData.json", "signals.json",
         "signalControllerDefinitions.json", "city.sites.json", "facilities.sites.json", "main.decals.json")


# ------------------------------------------------------------------ the slices
class Slices:
    """slice.json and single files of every zone's slice, from local folders or the slice zips of a release."""

    def __init__(self, folder=None, tag=SLICES_TAG):
        self.folder, self.zips, self.where = folder, {}, {}
        if folder:
            return
        ids = zipremote.assets(tag)
        by_zone = collections.defaultdict(list)
        for n, i in ids.items():
            m = re.fullmatch(r"ticino_(ti_[m0-9]+_[m0-9]+)_(\d+)\.zip", n)
            if m:
                by_zone[m.group(1)].append(i)
        self.ids = by_zone

    def _open(self, zone):
        if zone not in self.zips:
            self.zips[zone] = [zipremote.open_zip(i) for i in self.ids.get(zone, [])]
            for zf in self.zips[zone]:
                for n in zf.namelist():
                    self.where[n] = zf
        return self.zips[zone]

    def read(self, zone, rel):
        """The bytes of levels/ticino/<rel> of the zone's slice, or None."""
        name = f"levels/{LEVEL}/{rel}"
        if self.folder:
            p = os.path.join(self.folder, zone, *name.split("/"))
            return open(p, "rb").read() if os.path.exists(p) else None
        self._open(zone)
        zf = self.where.get(name)
        return zf.read(name) if zf else None

    def slice(self, zone):
        b = self.read(zone, f"z/{zone}/slice.json")
        return json.loads(b) if b else None


# ------------------------------------------------------------------ the zones' small files
def fetch_small(zone, asset_id, cache):
    """Scene, small json, material files and terrain textures of a zone zip under cache/<zone>/levels/<zone>/; returns
    the zip's [(name, size, crc)]."""
    out = os.path.join(cache, zone)
    inv_p = os.path.join(out, "inventory.json")
    if os.path.exists(os.path.join(out, "done_small")):
        return json.load(open(inv_p))
    zf = zipremote.open_zip(asset_id)
    pre = f"levels/{zone}/"
    inv = [[i.filename, i.file_size, i.CRC] for i in zf.infolist() if not i.filename.endswith("/")]
    want = [n for n, _, _ in inv if n.startswith((pre + "main/", pre + "art/terrains/"))
            or n.endswith("materials.json") or n[len(pre):] in SMALL or n == f"{pre}{zone}_preview.jpg"]
    zipremote.extract(zf, want, out)
    with open(inv_p, "w") as f:
        json.dump(inv, f)
    open(os.path.join(out, "done_small"), "w").write("1")
    return inv


def shared_wanted(zones, invs, shapes):
    """{zone: [zip names]}: the files of the level copied once (copy_shared), each from the first zone of the plan that
    has it; the zones' shapes, scene, forest, terrain and per-zone files are not."""
    seen, out = set(), collections.defaultdict(list)
    for z in zones:
        pre = f"levels/{z}/"
        for n, _, _ in invs[z]:
            rel = n[len(pre):]
            if (rel.startswith(("main/", "forest/", "art/terrains/")) or "/" + rel in shapes[z] or rel in SMALL
                    or rel in region.SKIP_FILES or rel.endswith((".ter", ".jpg", "materials.json"))):
                continue
            if rel in seen:
                continue
            seen.add(rel)
            out[z].append(n)
    return out


def fetch_shared(zone, asset_id, names, cache):
    out = os.path.join(cache, zone)
    if os.path.exists(os.path.join(out, "done_shared")):
        return 0
    zf = zipremote.open_zip(asset_id)
    zipremote.extract(zf, names, out)
    open(os.path.join(out, "done_shared"), "w").write("1")
    return len(names)


def level_shapes(zone, cache):
    """The level paths of the zone's own shapes, relative to its level ("/art/shapes/...")."""
    sc = blocks.scene_files(os.path.join(cache, zone, "levels", zone))
    pre = f"/levels/{zone}"
    return {o["shapeName"][len(pre):] for objs in sc.values() for o in objs
            if o.get("class") == "TSStatic" and str(o.get("shapeName", "")).startswith(pre + "/")}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slices", help="folder with <zone>/levels/ticino/ of every slice (default: release ticino-all)")
    ap.add_argument("--zones", nargs="*", help="only these zones of the plan (a test)")
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "ticino_base_cache"))
    ap.add_argument("--dist", help="pack the base into <dist>/ticino_base_<n>.zip")
    ap.add_argument("--plan", default=PLAN)
    a = ap.parse_args()
    t0 = time.time()
    plan = json.load(open(a.plan))
    grid = blocks.Zone(json.load(open(region.GRID_CFG)))
    Z0, MAXH, layers = float(plan["z0"]), float(plan["maxHeight"]), plan["layers"]
    zones = [z for z in plan["zones"] if not a.zones or z in a.zones]

    sl = Slices(a.slices)
    slices = {}
    for z in zones:
        d = sl.slice(z)
        if d is None:
            log("no slice of", z, ": left out")
        else:
            slices[z] = d
    zones = [z for z in zones if z in slices]
    log(len(zones), "zones with a slice")

    src_ids = zipremote.assets(ZONES_TAG)
    cache = os.path.join(a.cache, "src")
    with ThreadPoolExecutor(8) as ex:
        invs = dict(zip(zones, ex.map(lambda z: fetch_small(z, src_ids[z + ".zip"], cache), zones)))
    shapes = {z: level_shapes(z, cache) for z in zones}
    want = shared_wanted(zones, invs, shapes)
    with ThreadPoolExecutor(8) as ex:
        n = sum(ex.map(lambda z: fetch_shared(z, src_ids[z + ".zip"], want[z], cache), zones))
    log("zone files read: small of", len(zones), "zones, shared", n, "files", "(%.0f s)" % (time.time() - t0))

    srcs = [region.Src(z, os.path.join(cache, z), grid, light=True) for z in zones]
    dst = os.path.join(a.out, "levels", LEVEL)
    for d in ("main", "art", "blocks", "far", "col", "z", "tiles"):
        shutil.rmtree(os.path.join(dst, d), ignore_errors=True)

    kept_by_zone, roads, stats = [], [], collections.Counter()
    for s in srcs:
        kept = {}
        region.stream_zone(grid, s, dst, {}, kept, stats, roads, shapes=False)
        kept_by_zone.append(kept)
    report = region.net_report(srcs, roads)
    for path, o, z, _, _ in roads:
        kept_by_zone[zones.index(z)].setdefault(path, []).append(o)
    log("scene objects:", dict(stats))

    item_data = {}
    for s in srcs:
        p = os.path.join(s.dir, "art", "forest", "managedItemData.json")
        if os.path.exists(p):
            for k, v in json.load(open(p)).items():
                if k not in item_data:
                    item_data[k] = json.loads(json.dumps(v).replace(s.prefix, f"/levels/{LEVEL}/"))
    missing = [t for t in plan["forestTypes"] if t not in item_data]
    if missing:
        log("WARNING forest types without item data:", missing)
    with wopen(os.path.join(dst, "art", "forest", "managedItemData.json"), "w") as f:
        json.dump(item_data, f, indent=1)

    region.copy_shared(srcs, dst, {})
    report.update(region.write_spots(srcs, dst))
    with wopen(os.path.join(a.out, "region_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    with wopen(os.path.join(dst, "col", "col.materials.json"), "w") as f:
        json.dump(collision.materials(plan["groundTypes"]), f, indent=1)
    blocks.bng.write_materials(os.path.join(dst, "far", "far.materials.json"), [blocks.far_material()])

    # stream.json and the warm-up list: the slices' lists together
    tiles, ftiles, far, cells, shp, base_keys = {}, {}, [], [], set(), set()
    owner = {}
    for z in zones:
        d = slices[z]
        assert (d["z0"], d["maxHeight"], d["layers"]) == (Z0, MAXH, len(layers)), f"slice of {z} made with another plan"
        tiles.update(d["tiles"])
        ftiles.update(d["forestTiles"])
        far += d["far"]
        cells += d["colCells"]
        shp.update(d["warmupShapes"])
        base_keys.update(d["baseTextures"])
        for k in d["blocks"]:
            owner[k] = z
    base_keys = sorted(base_keys)
    # the warm-up lists per zone: all Ticino's shapes at 0.1 s each would take hours; warmup.lua takes the zones near
    # the car (stream.json zoneCores)
    for z in zones:
        with wopen(os.path.join(dst, "warmup", z + ".json"), "w") as f:
            json.dump(slices[z]["warmupShapes"], f)

    mats, frm = region.terrain_mats(srcs, layers)
    wm = region.window_materials(grid, mats, frm, set(base_keys), os.path.join(dst, "art", "terrains", "w"))
    with wopen(os.path.join(dst, "art", "terrains", "main.materials.json"), "w") as f:
        json.dump(wm, f, indent=1)

    kept = region.merge_kept(kept_by_zone)
    s0 = next((s for s in srcs if s.name == START_ZONE), srcs[0])
    info = json.load(open(os.path.join(s0.dir, "info.json")))
    spawns = [o for objs in kept.values() for o in objs if o.get("class") == "SpawnSphere"]
    want_sp = f"{s0.name}_{info.get('defaultSpawnPointName')}"
    sp = next((o for o in spawns if o.get("name") == want_sp), next((o for o in spawns if o["name"].startswith(s0.name)),
                                                                      spawns[0] if spawns else None))
    sx, sy = (sp["position"][0], sp["position"][1]) if sp else ((s0.core[0] + s0.core[2]) / 2,
                                                                 (s0.core[1] + s0.core[3]) / 2)
    wx, wy = grid.window_for(sx, sy)
    # the start window's blocks, from their slices (not packed: the slices carry them)
    tmp_blocks = os.path.join(a.cache, "start_blocks")
    os.makedirs(tmp_blocks, exist_ok=True)
    B = grid.B
    for by in range(wy // B, (wy + grid.W - 1) // B + 1):
        for bx in range(wx // B, (wx + grid.W - 1) // B + 1):
            z = owner.get(f"{bx}_{by}")
            data = sl.read(z, f"blocks/terrain/t_{bx}_{by}.bin") if z else None
            if data:
                with open(os.path.join(tmp_blocks, f"t_{bx}_{by}.bin"), "wb") as f:
                    f.write(data)
    with wopen(os.path.join(dst, "start.ter"), "wb") as f:
        f.write(blocks.window_ter(grid, tmp_blocks, 0, wx, wy, layers))
    tb_new = dict(s0.tb)
    tb_new.pop("persistentId", None)
    tb_new["position"] = [grid.x0 + wx * grid.sq, grid.y0 + wy * grid.sq, Z0]
    tb_new["maxHeight"] = MAXH
    tb_new["terrainFile"] = f"/levels/{LEVEL}/start.ter"
    tb_new["materialTextureSet"] = LEVEL + "TerrainMaterialTextureSet"
    blocks.bng.write_terrain_json(os.path.join(dst, "start.terrain.json"), LEVEL, "start", grid.W, layers)
    region.write_scene(kept, dst, tb_new)

    info["title"] = "Ticino"
    info["description"] = "All of Canton Ticino streamed round the car (%d zones)." % len(zones)
    info["size"] = [grid.W, grid.W]
    if sp:
        info["defaultSpawnPointName"] = sp["name"]
    info["spawnPoints"] = [{"objectname": o["name"], "translationId": o["name"]} for o in spawns]
    info["previews"] = []
    pv = os.path.join(s0.dir, s0.level + "_preview.jpg")
    if os.path.isfile(pv):
        with open(pv, "rb") as fi, wopen(os.path.join(dst, f"{LEVEL}_preview.jpg"), "wb") as fo:
            fo.write(fi.read())
        info["previews"] = [f"{LEVEL}_preview.jpg"]
    with wopen(os.path.join(dst, "info.json"), "w") as f:
        json.dump(info, f, indent=2)

    stream = {
        "version": 2, "zone": "ticino:%d zones" % len(zones), "level": LEVEL,
        "origin": [grid.x0, grid.y0], "square": grid.sq, "z0": Z0, "maxHeight": MAXH,
        "block": grid.B, "cell": grid.C, "window": grid.W, "basePx": grid.SPP,
        "blocksPerSide": 0, "materials": layers,
        "baseTextures": base_keys,
        "baseMaterials": [[k, m["internalName"], os.path.splitext(os.path.basename(m["baseColorBaseTex"]))[0]]
                          for k, m in mats.items() if m.get("class") == "TerrainMaterial"
                          and os.path.splitext(os.path.basename(m["baseColorBaseTex"]))[0] in base_keys],
        "baseSizeUnit": grid.cfg.get("base_size_unit", "samples"),
        "tiles": tiles, "forestTiles": ftiles, "forestTypes": plan["forestTypes"],
        "far": sorted(far), "farRadius": int(grid.cfg.get("far_radius", 16)),
        "collisionRadius": int(grid.cfg.get("collision_radius", 1)),
        "colCell": blocks.collision_cell_m(), "colCells": sorted(cells),
        "colGroundTypes": plan["groundTypes"], "colPieceTris": blocks.collision_piece_tris(),
        "colRadius": int(grid.cfg.get("col_radius", 1)),
        "maxRadius": max(int(v["radius"]) for v in grid.cfg["groups"].values()),
        "start": [wx, wy], "zones": zones,
        "zoneCores": {s.name: [round(v, 3) for v in s.core] for s in srcs},
    }
    with wopen(os.path.join(dst, "stream.json"), "w") as f:
        json.dump(stream, f, separators=(",", ":"))
    log("base of %d zones: %d spawn points, %d tiles, %d forest tiles, %d far cells, %d collision cells, %d warm-up "
        "shapes in %.0f s" % (len(zones), len(spawns), len(tiles), len(ftiles), len(far), len(cells), len(shp),
                              time.time() - t0))
    if a.dist:
        import package
        import pack_region
        pack_region.pack(package.entries(a.out), a.dist, "ticino_base")


if __name__ == "__main__":
    main()
