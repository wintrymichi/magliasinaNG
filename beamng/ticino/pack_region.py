"""Ticino region: the mod zips of a level joined by region.py, each under the 2 GB a release asset (and a comfortable
zip) may be. BeamNG mounts every zip in mods/ into one file system, so the parts of levels/ticino/ may lie in any zip:

    ticino_region_1.zip   the streaming Lua, THIRD_PARTY.md and everything of the level outside z/ (scene, terrain
                          blocks, far tiles, collision cells, forest tiles, shared materials and textures, ...)
    ticino_region_2.zip   the clipped shapes z/<zone>/ of the zones, in zone order, a new zip whenever one reaches LIMIT
    ...

    python pack_region.py --out <region.py output> --dist <folder> [--limit-gb 1.9] [--level 6]

Every zip is complete on its own terms (no file split across two); all of them go into mods/ together.
"""
import argparse
import os
import time
import zipfile

import package

LIMIT_GB = 1.9


def ordered(out):
    """(path, name) of every file of the mod: the base first, then z/<zone>/ zone by zone."""
    base, zones = [], {}
    for p, name in package.entries(out):
        parts = name.split("/")
        if len(parts) > 3 and parts[0] == "levels" and parts[2] == "z":
            zones.setdefault(parts[3], []).append((p, name))
        else:
            base.append((p, name))
    return base, [zones[z] for z in sorted(zones)]


def pack(files, dist, name, limit_gb=LIMIT_GB, level=6):
    """files [(path, name in the mod)] into dist/<name>_<n>.zip, a new zip whenever one would pass the limit.
    Returns the zips made (region_slice / region_base: one set per zone and one for the base)."""
    os.makedirs(dist, exist_ok=True)
    limit = limit_gb * 1e9
    made, z, path = [], None, None
    for p, n in files:
        if z is None or z.fp.tell() + os.path.getsize(p) > limit:
            if z:
                z.close()
                os.replace(path + ".part", path)
                made.append(path)
            path = os.path.join(dist, "%s_%d.zip" % (name, len(made) + 1))
            z = zipfile.ZipFile(path + ".part", "w", zipfile.ZIP_DEFLATED, compresslevel=level, allowZip64=True)
        z.write(p, n, compress_type=zipfile.ZIP_STORED if n.lower().endswith(package.STORED) or "/blocks/" in n
                else None)
    if z:
        z.close()
        os.replace(path + ".part", path)
        made.append(path)
    for p in made:
        print("%s %.2f GB" % (os.path.basename(p), os.path.getsize(p) / 1e9), flush=True)
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dist", required=True)
    ap.add_argument("--name", default="ticino_region")
    ap.add_argument("--limit-gb", type=float, default=LIMIT_GB)
    ap.add_argument("--level", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.dist, exist_ok=True)
    limit = a.limit_gb * 1e9
    base, zones = ordered(a.out)
    t0 = time.time()
    made = []
    state = {"z": None, "path": None}

    def start():
        if state["z"]:
            state["z"].close()
            os.replace(state["path"] + ".part", state["path"])
            made.append(state["path"])
        state["path"] = os.path.join(a.dist, "%s_%d.zip" % (a.name, len(made) + 1))
        state["z"] = zipfile.ZipFile(state["path"] + ".part", "w", zipfile.ZIP_DEFLATED, compresslevel=a.level,
                                     allowZip64=True)

    def add(p, name):
        # the bytes written so far (the open zip's file) + this file uncompressed: never over the limit
        if state["z"].fp.tell() + os.path.getsize(p) > limit:
            start()
        state["z"].write(p, name, compress_type=zipfile.ZIP_STORED if name.lower().endswith(package.STORED) or "/blocks/" in name else None)

    start()
    for p, name in base:
        add(p, name)
    for files in zones:
        start()                                          # a zone's shapes start a zip of their own: one zip per zone
        for p, name in files:
            add(p, name)
    start()
    os.remove(state["path"] + ".part")
    for p in made:
        print("%s %.2f GB" % (os.path.basename(p), os.path.getsize(p) / 1e9))
    print("%d zips in %.0f s" % (len(made), time.time() - t0))


if __name__ == "__main__":
    main()
