"""Patch of the v3.1 zip (2026-10-23), without building it again: the wear of the roads laid again (road_wear.py) with
what the photos say about the asphalt (road_age.py: older and newer stretches, sealed joints, patches, crumbled edges,
manholes and gullies, the joints with yards and setts). The build has it since the same commit (finish step
road_wear). Only the parts of the level road_wear reads and writes are unpacked: the road surfaces and paint, the AI
roads and art/shapes/roads; road_wear runs on them, and the zip gets their new contents (the old road_wear_*.dae out).

Run: python patch_road_age.py <level zip>
"""
import os, shutil, sys, tempfile, time, zipfile
from config import LEVEL_NAME
import road_wear

PARTS = (f"levels/{LEVEL_NAME}/main/MissionGroup/roads/", f"levels/{LEVEL_NAME}/main/MissionGroup/AIRoads/",
         f"levels/{LEVEL_NAME}/art/shapes/roads/")


def patch(src):
    work = tempfile.mkdtemp(prefix="magliaso_age_", dir=os.path.dirname(os.path.abspath(src)))
    try:
        with zipfile.ZipFile(src) as z:
            names = [n for n in z.namelist() if n.startswith(PARTS) and not n.endswith("/")]
            for n in names:
                z.extract(n, work)
        before = {n: os.path.getmtime(os.path.join(work, n)) for n in names}
        road_wear.road_wear_step(work)
        now = set()
        for dp, _, fs in os.walk(os.path.join(work, "levels")):
            for f in fs:
                now.add(os.path.relpath(os.path.join(dp, f), work).replace(os.sep, "/"))
        changed = {n for n in now if n not in before or os.path.getmtime(os.path.join(work, n)) != before[n]}
        gone = {n for n in set(before) - now if road_wear.SHAPE.search(n)}   # only the wear's own meshes go
        assert gone == set(before) - now, "road_wear removed other files: %s" % sorted(set(before) - now - gone)[:5]
        fd, tmp = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(os.path.abspath(src)))
        os.close(fd)
        with zipfile.ZipFile(src) as zi, zipfile.ZipFile(tmp, "w") as zo:
            for i in zi.infolist():
                if i.filename in changed or i.filename in gone:
                    continue
                with zi.open(i) as a, zo.open(i, "w") as b:
                    shutil.copyfileobj(a, b, 1 << 24)
            for n in sorted(changed):                  # dated now: newer than any shape the game cached from it
                data = open(os.path.join(work, n), "rb").read()
                zo.writestr(zipfile.ZipInfo(n, time.localtime()[:6]), data,
                            compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
        os.replace(tmp, src)
        print("road age patch: %d files written, %d removed" % (len(changed), len(gone)))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    patch(sys.argv[1])
