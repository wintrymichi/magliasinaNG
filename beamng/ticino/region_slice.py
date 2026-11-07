"""One zone's slice of the Ticino streaming level: everything of levels/ticino/ that lies in the zone's core, written
by one GitHub job per zone (ticino_all.yml) without seeing the other zones. What the slices must agree on is fixed in
zones/ticino_plan.json (region_plan.py): the height scale, the terrain layers, the forest types, the ground types and
the list of zones (which says who owns the terrain blocks beyond every core).

A slice holds, under levels/ticino/:
    blocks/terrain/t_<bx>_<by>.bin, blocks/base/<key>_<bx>_<by>.rgb   the zone's blocks (its core and the border
                                                                      blocks the plan gives it)
    far/f_<cx>_<cy>.cdae                                              the far ground of those blocks
    z/<zone>/...                                                      the zone's shapes, clipped to its core,
                                                                      compiled to .cdae (dae2cdae.py)
    tiles/o_<cx>_<cy>.json, tiles/t_<cx>_<cy>.trees.json             the streamed objects and trees of its core
    col/c_<i>_<j>.bin                                                 the collision cells of its core
    z/<zone>/slice.json                                               what region_base.py puts into stream.json
The scene, materials, info.json and the rest are the base's (region_base.py).

    python region_slice.py --zone ti_0_0 --src <folder with levels/ti_0_0/> --out <folder> [--workers 4]
"""
import argparse
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blocks  # noqa: E402
import dae2cdae  # noqa: E402
import region  # noqa: E402
from blocks import LEVEL, log, wopen  # noqa: E402

PLAN = os.path.join(HERE, "zones", "ticino_plan.json")
VERSION = 1


def zone_cfg(name):
    return json.load(open(os.path.join(region.ZONE_DIR, name + ".json")))


def block_owners(grid, plan):
    """{(bx, by): zone name} of every block of the level: the cores, then the blocks of each zone's terrain no core
    covers, to the first zone of the plan whose terrain holds the whole block (region.write_blocks' rule)."""
    B = grid.B
    owner = {}
    cfgs = [(z, zone_cfg(z)) for z in plan["zones"]]
    for z, c in cfgs:
        bx0, by0, nb = c["core_blocks"]
        for i in range(nb):
            for j in range(nb):
                owner[(bx0 + i, by0 + j)] = z
    for z, c in cfgs:
        ox = int(round((c["ter_x0"] - grid.x0) / grid.sq))
        oy = int(round((c["ter_y0"] - grid.y0) / grid.sq))
        n = int(c["ter_size"])
        for by in range(-(-oy // B), (oy + n) // B):
            for bx in range(-(-ox // B), (ox + n) // B):
                owner.setdefault((bx, by), z)
    return owner


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--dist", help="pack the slice into <dist>/ticino_<zone>_<n>.zip (pack_region.pack)")
    a = ap.parse_args()
    t0 = time.time()
    plan = json.load(open(a.plan))
    assert a.zone in plan["zones"], f"{a.zone} is not in the plan"
    grid = blocks.Zone(json.load(open(region.GRID_CFG)))
    s = region.Src(a.zone, a.src, grid)
    assert (s.ox, s.oy) == (int(round((s.cfg["ter_x0"] - grid.x0) / grid.sq)),
                            int(round((s.cfg["ter_y0"] - grid.y0) / grid.sq))), "terrain not where the zone says"
    unknown = [m for m in s.materials if m not in plan["layers"]]
    assert not unknown, f"terrain layers {unknown} are not in the plan: run region_plan.py --add"
    dst = os.path.join(a.out, "levels", LEVEL)
    Z0, MAXH, layers = float(plan["z0"]), float(plan["maxHeight"]), plan["layers"]
    stats = collections.Counter()

    owner = {k: s for k, z in block_owners(grid, plan).items() if z == s.name}
    if s.H is not None:
        h = s.H
        lo, hi = float(h.min()) / 65535 * s.maxh + s.z0, float(h.max()) / 65535 * s.maxh + s.z0
        if lo < Z0 or hi > Z0 + MAXH:
            log(f"heights {lo:.1f}..{hi:.1f} m clipped to the plan's {Z0:.0f}..{Z0 + MAXH:.0f}")
    region.write_blocks(grid, [s], Z0, MAXH, layers, os.path.join(dst, "blocks", "terrain"), owner=owner)
    base_keys = region.write_base_maps(grid, owner, [s], os.path.join(dst, "blocks", "base"))
    far = region.write_far(grid, owner, [s], layers, os.path.join(dst, "far"))
    os.remove(os.path.join(dst, "far", "far.materials.json"))           # the base's

    tiles, kept, roads = {}, {}, []
    region.stream_zone(grid, s, dst, tiles, kept, stats, roads)
    log("objects:", dict(stats))
    types = {t: i for i, t in enumerate(plan["forestTypes"])}
    ftiles = {}
    nf = region.forest_zone(grid, s, types, ftiles, {}, fixed=True)
    for (cx, cy), rows in ftiles.items():
        with wopen(os.path.join(dst, "tiles", f"t_{cx}_{cy}.trees.json"), "w") as f:
            json.dump(rows, f, separators=(",", ":"))
    log("forest items:", nf, "in", len(ftiles), "tiles")

    import collision
    keys, _, cstats = collision.build(grid, tiles, dst, LEVEL, os.path.join(dst, "col"), workers=a.workers,
                                      types=plan["groundTypes"], gtypes_dir=s.dir, bounds=s.core)
    os.remove(os.path.join(dst, "col", "col.materials.json"))           # the base's
    # the zone's shapes compiled to .cdae (dae2cdae.py), after the collision cells were read from the .dae: the game
    # loads them as it loads its own cache, with no Collada import while driving; the shared shapes the base compiles
    # by the same test (dae2cdae.compilable on the zone's copy)
    cstat, compiled, dae_kept = dae2cdae.compile_level(os.path.join(dst, "z", s.name), f"/levels/{LEVEL}/z/{s.name}",
                                                       workers=a.workers, rewrite=False, log=log)
    shared = {}
    for objs in tiles.values():
        for o in objs:
            sh = str(o.get("shapeName", ""))
            if not sh.lower().endswith(".dae"):
                continue
            if sh in compiled:
                o["shapeName"] = compiled[sh]
            elif not sh.startswith(f"/levels/{LEVEL}/z/"):
                if sh not in shared:
                    src = s.path(s.prefix + sh[len(f"/levels/{LEVEL}/"):])
                    shared[sh] = src is not None and os.path.exists(src) and dae2cdae.compilable(src)
                if shared[sh]:
                    o["shapeName"] = sh[:-4] + ".cdae"
    for (cx, cy), objs in tiles.items():
        with wopen(os.path.join(dst, "tiles", f"o_{cx}_{cy}.json"), "w") as f:
            json.dump(objs, f, separators=(",", ":"))
    shapes = sorted({o["shapeName"] for objs in tiles.values() for o in objs
                     if str(o.get("shapeName", "")).lower().endswith(".dae")})
    slice_ = {
        "version": VERSION, "zone": s.name, "level": s.level, "z0": Z0, "maxHeight": MAXH,
        "layers": len(layers), "forestTypes": len(plan["forestTypes"]), "groundTypes": len(plan["groundTypes"]),
        "blocks": sorted(f"{bx}_{by}" for bx, by in owner), "baseTextures": base_keys, "far": far,
        "tiles": {f"{cx}_{cy}": len(v) for (cx, cy), v in tiles.items()},
        "forestTiles": {f"{cx}_{cy}": len(v) for (cx, cy), v in ftiles.items()},
        "colCells": keys, "colStats": cstats, "warmupShapes": shapes, "objects": dict(stats),
        "cdae": {"version": dae2cdae.VERSION, "stats": cstat, "kept": dae_kept},
        "seconds": round(time.time() - t0),
    }
    with wopen(os.path.join(dst, "z", s.name, "slice.json"), "w") as f:
        json.dump(slice_, f, indent=1)
    log("slice of %s: %d blocks, %d tiles, %d forest tiles, %d collision cells, %d far cells in %.0f s" % (
        s.name, len(owner), len(tiles), len(ftiles), len(keys), len(far), time.time() - t0))
    if a.dist:
        import pack_region
        pack_region.pack(level_files(a.out), a.dist, f"ticino_{s.name}")


def level_files(out):
    """(path, name in the mod) of every file under out/levels/ticino/."""
    for dp, _, fs in os.walk(os.path.join(out, "levels", LEVEL)):
        for f in sorted(fs):
            p = os.path.join(dp, f)
            yield p, os.path.relpath(p, out).replace(os.sep, "/")


if __name__ == "__main__":
    main()
