"""Patch of the v3.1 zip (2026-10-23), without building it again: the survey's wing walls at the four corners of the
Via Golf underpass under the FLP (Caslano - Magliaso, about 875, -1306) stood 0.4-0.9 m into the asphalt, because
walls.drive_free kept only a quarter of the road's width free of walls there (the survey has no road polygon in an
underpass). The build has this since 7a9530c (the whole width + walls.UNDER_FREE); this moves the wall vertices of the
built level within that band out to its edge, across the road's AI line (tlm_3630 in the zip): a wall end in the road
ends on the band's edge, the solid stays closed (only positions change, in the DAE's own position array).

Run: python patch_underpass_walls.py <level zip | level folder>
"""
import os, re, shutil, sys, tempfile, time, zipfile
import numpy as np
import shapely
from config import LEVEL_NAME
import walls

ROAD = "tlm_3630"          # the AI road of Via Golf under the railway (network.underpasses), v3.1 build
APPROACHES = ("tlm_4374", "tlm_3629")   # the AI roads of Via Golf on either side: their carriageway within MOUTH m
MOUTH = 5.0                # m of an end of ROAD: the wing walls' ends reach into the approaches' carriageway there
AT = (875.0, -1306.0)      # m, the underpass
NEAR = 30.0                # m round it: only walls here are touched
EXPECT = (20, 400)         # vertices moved: fewer or more means another level than the one this was measured on


class Files:
    """The level's files from a zip or a folder, by their name in the zip (levels/<level>/...)."""

    def __init__(self, src):
        self.src, self.zip = src, zipfile.ZipFile(src) if zipfile.is_zipfile(src) else None
        self.changed = {}

    def read(self, name):
        if self.zip:
            return self.zip.read(name).decode("utf-8")
        return open(os.path.join(self.src, *name.split("/")[2:]), encoding="utf-8").read()

    def write(self, name, text):
        self.changed[name] = text.encode("utf-8")

    def save(self):
        if not self.changed:
            return
        if not self.zip:
            for name, data in self.changed.items():
                path = os.path.join(self.src, *name.split("/")[2:])
                tmp = path + ".tmp"
                open(tmp, "wb").write(data)
                os.replace(tmp, path)          # a new file: a hard-linked copy of the level keeps the original
            return
        fd, tmp = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(os.path.abspath(self.src)))
        os.close(fd)
        with zipfile.ZipFile(tmp, "w") as zo:
            for i in self.zip.infolist():
                if i.filename in self.changed:       # dated now: newer than any shape the game cached from it
                    zo.writestr(zipfile.ZipInfo(i.filename, time.localtime()[:6]), self.changed[i.filename],
                                compress_type=zipfile.ZIP_DEFLATED)
                else:
                    with self.zip.open(i) as a, zo.open(i, "w") as b:
                        shutil.copyfileobj(a, b, 1 << 24)
        self.zip.close()
        os.replace(tmp, self.src)


def lines(text):
    import json
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def patch(src):
    f = Files(src)
    base = "levels/%s/main/MissionGroup/" % LEVEL_NAME
    ai = {o.get("name"): o for o in lines(f.read(base + "AIRoads/items.level.json")) if o.get("class") == "DecalRoad"}
    if ROAD not in ai:
        sys.exit("AI road %s not found" % ROAD)
    bands = []                                  # (axis, half width kept free, area where it holds)
    nd = np.array(ai[ROAD]["nodes"], np.float64)
    axis = shapely.LineString(nd[:, :2])
    bands.append((axis, 0.5 * float(np.median(nd[:, 3])) + walls.UNDER_FREE, None))
    mouths = shapely.MultiPoint([nd[0, :2], nd[-1, :2]]).buffer(MOUTH)
    for n in APPROACHES:
        if n in ai:
            q = np.array(ai[n]["nodes"], np.float64)
            bands.append((shapely.LineString(q[:, :2]), 0.5 * float(np.median(q[:, 3])), mouths))
    moved = 0
    for o in lines(f.read(base + "walls/items.level.json")):
        if o.get("class") != "TSStatic" or not o["shapeName"].startswith("/levels/"):
            continue
        pos = np.array(o["position"], np.float64)
        if o.get("rotationMatrix") not in (None, [1, 0, 0, 0, 1, 0, 0, 0, 1]) or o.get("scale") not in (None, [1, 1, 1]):
            continue
        name = o["shapeName"].lstrip("/")
        s = f.read(name)
        m = re.search(r'(<float_array id="g-pa" count="\d+">)([^<]*)(</float_array>)', s)
        V = np.array(m.group(2).split(), np.float64).reshape(-1, 3)
        W = V + pos
        sel = np.flatnonzero(np.hypot(W[:, 0] - AT[0], W[:, 1] - AT[1]) < NEAR)
        if not len(sel):
            continue
        n0 = 0
        for axis, hw, where in bands:
            P = shapely.points(W[sel, :2])
            d = shapely.distance(axis, P)
            inside = (d < hw - 1e-3) & (d > 0.05)
            if where is not None:
                inside &= shapely.contains(where, P)
            if not inside.any():
                continue
            k = sel[inside]
            F = shapely.get_coordinates(shapely.line_interpolate_point(axis, shapely.line_locate_point(axis, P[inside])))
            W[k, :2] = F + (W[k, :2] - F) / d[inside][:, None] * hw
            n0 += len(k)
            print("%s: %d vertices moved out to %.2f m from an axis of Via Golf (were %.2f-%.2f m)"
                  % (name, len(k), hw, d[inside].min(), d[inside].max()), flush=True)
        if not n0:
            continue
        V = W - pos
        txt = " ".join("%.3f" % v for v in V.ravel())
        f.write(name, s[:m.start(2)] + txt + s[m.end(2):])
        moved += n0
    if not EXPECT[0] <= moved <= EXPECT[1]:
        sys.exit("underpass walls: %d vertices moved, expected %d-%d: not saved" % (moved, *EXPECT))
    f.save()
    print("underpass walls: %d vertices moved in %d files of %s" % (moved, len(f.changed), src), flush=True)
    return moved


if __name__ == "__main__":
    patch(sys.argv[1])
