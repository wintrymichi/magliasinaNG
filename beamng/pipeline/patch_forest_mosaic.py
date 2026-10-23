"""Patch of a built v3.1 zip (2026-10-23) without building it again: the forest floor as a mosaic (forest_mosaic.py:
ragged edges as wide as the opening beside them, thickets and bare leaf litter by the sun and the beech belt,
outcrops with stones, the wooded steep banks, woodland grass in the light). The build has it as the finish step
forest_mosaic after steep_skin.

Run: python patch_forest_mosaic.py <level zip | level folder>
"""
import os, shutil, sys, tempfile, time, zipfile
import forest_mosaic


def patch_zip(src):
    zi = zipfile.ZipFile(src)
    new, stats = forest_mosaic.changes(zi)
    fd, tmp = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(os.path.abspath(src)))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as zo:
        for i in zi.infolist():
            if i.filename in new:                    # dated now: the game converts the terrain again
                zo.writestr(zipfile.ZipInfo(i.filename, time.localtime()[:6]), new[i.filename],
                            compress_type=zipfile.ZIP_DEFLATED)
            else:
                with zi.open(i) as a, zo.open(i, "w") as b:
                    shutil.copyfileobj(a, b, 1 << 24)
    zi.close()
    os.replace(tmp, src)
    return new, stats


def main(src):
    t0 = time.time()
    if zipfile.is_zipfile(src):
        new, stats = patch_zip(src)
        print("forest mosaic patched: %d files rewritten, %.0f s; bank_wood %d, outcrop %d" % (
            len(new), time.time() - t0, stats["bank_wood"], stats["outcrop"]), flush=True)
    else:
        forest_mosaic.forest_mosaic_step(src)


if __name__ == "__main__":
    main(sys.argv[1])
