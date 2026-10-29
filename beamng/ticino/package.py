"""Ticino a blocchi: the mod zip (or an unpacked mod folder) of a level cut by blocks.py, with the streaming Lua.

    python package.py --out <blocks.py output> --zip <path>/ticino_test.zip
    python package.py --out <blocks.py output> --folder <mods>/unpacked/ticino     (hard links where possible)

The zip holds levels/ticino/, gameplay/missions/ticino/ (if any), lua/ge/extensions/ticino/, scripts/ticino/ and
THIRD_PARTY.md. It never contains levels/magliaso_pura: the Malcantone mod stays as it is, the two are installed side by
side. Test files of the mod go under the user folder's temp/ticino/ and ticino_perf.csv (README.md, after a test).
"""
import argparse
import os
import shutil
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "mod")
# already compressed or small gain: stored
STORED = (".png", ".jpg", ".dds", ".ogg", ".zip")


def entries(out):
    """(path on disk, name in the mod) of every file."""
    for top in (os.path.join(out, "levels", "ticino"), os.path.join(out, "gameplay", "missions", "ticino")):
        if os.path.isdir(top):
            for dp, _, fs in os.walk(top):
                for f in sorted(fs):
                    p = os.path.join(dp, f)
                    yield p, os.path.relpath(p, out).replace(os.sep, "/")
    for dp, _, fs in os.walk(MOD):
        for f in sorted(fs):
            p = os.path.join(dp, f)
            yield p, os.path.relpath(p, MOD).replace(os.sep, "/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="the folder blocks.py wrote (holds levels/ticino)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--zip")
    g.add_argument("--folder")
    ap.add_argument("--level", type=int, default=1, help="deflate level (1 fast, 6 as the releases)")
    a = ap.parse_args()
    t0 = time.time()
    n = size = 0
    if a.zip:
        tmp = a.zip + ".part"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=a.level, allowZip64=True) as z:
            for p, name in entries(a.out):
                z.write(p, name, compress_type=zipfile.ZIP_STORED if name.lower().endswith(STORED) else None)
                n += 1
                size += os.path.getsize(p)
        os.replace(tmp, a.zip)
        print("%d files, %.2f GB -> %s (%.2f GB) in %.0f s" % (n, size / 1e9, a.zip, os.path.getsize(a.zip) / 1e9,
                                                                time.time() - t0))
    else:
        for p, name in entries(a.out):
            q = os.path.join(a.folder, *name.split("/"))
            os.makedirs(os.path.dirname(q), exist_ok=True)
            if os.path.exists(q):
                os.remove(q)
            try:
                os.link(p, q)
            except OSError:
                shutil.copy2(p, q)
            n += 1
        print("%d files -> %s in %.0f s" % (n, a.folder, time.time() - t0))


if __name__ == "__main__":
    main()
