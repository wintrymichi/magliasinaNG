"""The Ticino map (M key) and the spawn points' names.

The stock big map (freeroam/bigMapMode.lua) is a 3D camera over the loaded level: in Ticino it shows the ~3 km terrain
window round the car and nothing else. As BeamNG.Earth does (c) 2026 TecnaGamer, MIT licence
(github.com/TecnaGamer/BeamNG.Earth: settings.lua redirectBigMap, ui/ui-vue/mods/beamngEarth/EarthMap.vue), the mod
replaces it in the level ticino with a 2D map page of its own (mod/ui/ui-vue/mods/ticino/, lua ticino/worldmap.lua)
that draws image tiles from the level's files. Those tiles are made here, from what the level itself shows:
  - the ground: the far tiles' vertex colours (12 m, every zone; the same colours the far ground has in the game),
  - the roads: the AI roads of the base scene (DecalRoad nodes), drawn by class.
No imagery service is needed (the build and the game stay offline).

    map/map.json           { tile, x0, y1, mpp0, bg, levels: [{z, mpp, nx, ny, tiles: ["i_j", ...]}], places: [...] }
    map/<z>/<i>_<j>.jpg    tile (i, j) of level z (mpp0 * 2^z metres a pixel), (0, 0) the north-west corner

Spawn names (michi 2026-10-31: "voglio i nomi degli spawn accurati"): every zone's build put three spawn points on its
route and called them spawn_magliaso / spawn_mid / spawn_pura after the Malcantone level they came from (an
"ti_m3_7_spawn_magliaso" stands at Airolo), and one per village with an ASCII slug of its name. spawn_names() names each
point by the settlements of swissNAMES3D (swisstopo, OBJEKTART "Ort"): a village point keeps its village's name, a route
point takes the nearest place no other point has, a bigger place counting as nearer than a farm (_weight), within
NEAR_M its plain name, beyond it "<place> (2.3 km NE)". Without the gazetteer (no network) the
village slugs are turned back into words and the route points are named after the nearest village point.

    python worldmap.py --ground <ground.npz> --base <levels/ticino folder> --out <folder>     (a test on a base)
"""
import argparse
import csv
import io
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DIR = "map"
TILE = 512
SCALE0 = 2                  # the finest level has this many pixels per far-ground square (12 m -> 6 m a pixel)
BG = (38, 40, 42)           # outside the level (the page's background is the same)
QUALITY = 82
# LV95 of the level's local frame (beamng/pipeline/config.py)
E0, N0, K = 2710830.0, 1094360.0, 1.0001374973449562
NAMES_STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissnames3d/items"
NEAR_M = 1200.0             # a spawn point this close to a settlement takes its name (x its _weight)
FAR_M = 4000.0              # beyond it "<place> (5 km NE)" from the biggest place around
GENERIC = ("magliaso", "mid", "pura")   # the route points of every zone (build_level.stage_spawns)

# road styles: (min zoom level drawn up to, width px at level 0, colour, casing colour)
STYLES = {
    "motorway": (6, 4.0, (240, 150, 60), (90, 50, 20)),
    "main": (5, 3.0, (250, 220, 110), (80, 70, 30)),
    "secondary": (3, 2.2, (245, 245, 240), (60, 60, 60)),
    "minor": (2, 1.6, (225, 225, 220), None),
    "track": (1, 1.2, (190, 170, 130), None),
}


def log(*a):
    print(time.strftime("%H:%M:%S"), "worldmap:", *a, flush=True)


def lv95_to_local(e, n):
    return (e - E0) / K, (n - N0) / K


# ------------------------------------------------------------------ roads
def road_class(r):
    d = float(r.get("drivability", 1) or 0)
    v = float(r.get("speedLimit", 0) or 0)
    if v >= 27:
        return "motorway"
    if d >= 0.95:
        return "main"
    if d >= 0.75:
        return "secondary"
    if d >= 0.45:
        return "minor"
    return "track"


def roads_of(objects):
    """[(class, points (n, 2))] of the scene's AI roads (DecalRoad with nodes)."""
    out = []
    for o in objects:
        if o.get("class") != "DecalRoad" or not o.get("nodes"):
            continue
        p = np.array([[float(n[0]), float(n[1])] for n in o["nodes"]], np.float64)
        if len(p) >= 2:
            out.append((road_class(o), p))
    return out


# ------------------------------------------------------------------ tiles
class Canvas:
    """The far ground's colours on the map's pixel grid. Pixel (px, py) of level z covers x0 + px * mpp ..., with
    y from y1 down; the ground's vertex (r, c) stands at (gx0 + c * sq, gy0 + r * sq)."""

    def __init__(self, H, C, gx0, gy0, sq):
        self.ok = np.isfinite(H)
        self.C = np.where(self.ok[..., None], C, np.array(BG, np.float32)).astype(np.uint8)
        self.gx0, self.gy0, self.sq = gx0, gy0, sq
        self.nr, self.nc = H.shape
        self.x0 = gx0 - sq / 2
        self.y1 = gy0 + (self.nr - 0.5) * sq
        self.mpp0 = sq / SCALE0

    def level_size(self, z):
        mpp = self.mpp0 * (1 << z)
        w = math.ceil(self.nc * self.sq / mpp)
        h = math.ceil(self.nr * self.sq / mpp)
        return mpp, math.ceil(w / TILE), math.ceil(h / TILE)

    def tile(self, z, i, j):
        """RGB array (TILE, TILE, 3) of tile (i, j) of level z and whether any ground is in it."""
        mpp = self.mpp0 * (1 << z)
        # the tile's corners in ground columns / rows (rows of the ground run north, the image's south)
        xa = self.x0 + i * TILE * mpp
        yb = self.y1 - j * TILE * mpp                      # the tile's top edge
        ca = (xa - self.gx0) / self.sq
        rb = (yb - self.gy0) / self.sq
        span = TILE * mpp / self.sq                        # ground squares across the tile
        c0, c1 = int(math.floor(ca)) - 1, int(math.ceil(ca + span)) + 1
        r1, r0 = int(math.ceil(rb)) + 1, int(math.floor(rb - span)) - 1
        cc0, cc1 = max(c0, 0), min(c1, self.nc - 1)
        rr0, rr1 = max(r0, 0), min(r1, self.nr - 1)
        if cc0 > cc1 or rr0 > rr1 or not self.ok[rr0:rr1 + 1, cc0:cc1 + 1].any():
            return None
        # the crop c0..c1 x r0..r1, BG beyond the ground
        crop = np.empty((r1 - r0 + 1, c1 - c0 + 1, 3), np.uint8)
        crop[:] = BG
        crop[rr0 - r0:rr1 - r0 + 1, cc0 - c0:cc1 - c0 + 1] = self.C[rr0:rr1 + 1, cc0:cc1 + 1]
        img = Image.fromarray(np.ascontiguousarray(crop[::-1]))            # north up
        # the crop's pixel centres are the ground vertices; the tile's box in crop pixels
        left = ca - c0 + 0.5
        top = r1 - rb + 0.5
        box = (left, top, left + span, top + span)
        resample = Image.BILINEAR if span < TILE else Image.BOX
        return img.resize((TILE, TILE), resample, box=box)


def draw_roads(img, roads, z, xa, yb, mpp):
    """The roads of level z on tile image img whose top-left corner is world (xa, yb)."""
    d = ImageDraw.Draw(img)
    k = 1.0 / (1 << z) ** 0.5                     # lines thin out slower than the map
    x1, y0 = xa + TILE * mpp, yb - TILE * mpp
    for cls in ("track", "minor", "secondary", "main", "motorway"):
        zmax, w0, col, casing = STYLES[cls]
        if z > zmax:
            continue
        w = max(1.0, w0 * k)
        sel = []
        for c, p in roads:
            if c != cls:
                continue
            if p[:, 0].max() < xa - 20 or p[:, 0].min() > x1 + 20 or p[:, 1].max() < y0 - 20 or p[:, 1].min() > yb + 20:
                continue
            sel.append([((x - xa) / mpp, (yb - y) / mpp) for x, y in p])
        if casing is not None:
            for pts in sel:
                d.line(pts, fill=casing, width=int(round(w + 2)), joint="curve")
        for pts in sel:
            d.line(pts, fill=col, width=int(round(w)), joint="curve")


def build(H, C, gx0, gy0, sq, roads, out_dir, places=()):
    """Every tile of every level into out_dir/<z>/<i>_<j>.jpg and out_dir/map.json; returns the json dict."""
    cv = Canvas(H, C, gx0, gy0, sq)
    levels, nbytes, t0 = [], 0, time.time()
    z = 0
    while True:
        mpp, nx, ny = cv.level_size(z)
        os.makedirs(os.path.join(out_dir, str(z)), exist_ok=True)
        have = []
        for j in range(ny):
            for i in range(nx):
                img = cv.tile(z, i, j)
                if img is None:
                    continue
                draw_roads(img, roads, z, cv.x0 + i * TILE * mpp, cv.y1 - j * TILE * mpp, mpp)
                p = os.path.join(out_dir, str(z), f"{i}_{j}.jpg")
                if os.path.lexists(p):
                    os.remove(p)
                img.save(p, quality=QUALITY, optimize=True)
                nbytes += os.path.getsize(p)
                have.append(f"{i}_{j}")
        levels.append({"z": z, "mpp": mpp, "nx": nx, "ny": ny, "tiles": have})
        log("level %d (%.0f m a pixel): %d tiles" % (z, mpp, len(have)))
        if nx <= 1 and ny <= 1:
            break
        z += 1
    info = {"version": 1, "tile": TILE, "x0": cv.x0, "y1": cv.y1, "mpp0": cv.mpp0, "bg": list(BG),
            "width_m": cv.nc * sq, "height_m": cv.nr * sq, "levels": levels, "places": list(places),
            "credits": "Map from the level's own ground and AI roads (swisstopo, OpenStreetMap contributors)"}
    with open(os.path.join(out_dir, "map.json"), "w") as f:
        json.dump(info, f, separators=(",", ":"))
    log("%d tiles, %.1f MB in %.0f s" % (sum(len(lv["tiles"]) for lv in levels), nbytes / 1e6, time.time() - t0))
    return info


# ------------------------------------------------------------------ spawn names
def fetch_settlements(cache_dir=None, timeout=60):
    """[(name, x, y)] of every swissNAMES3D settlement ("Ort") in local metres, or [] without the network."""
    try:
        path = None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            got = [f for f in os.listdir(cache_dir) if f.startswith("swissnames3d") and f.endswith("_2056.csv.zip")]
            path = os.path.join(cache_dir, sorted(got)[-1]) if got else None
        if not path:
            items = json.load(urllib.request.urlopen(NAMES_STAC + "?limit=100", timeout=timeout))["features"]
            item = sorted(items, key=lambda f: f["id"])[-1]
            href, name = next((a["href"], n) for n, a in item["assets"].items() if n.endswith("_2056.csv.zip"))
            data = urllib.request.urlopen(href, timeout=600).read()
            path = os.path.join(cache_dir or ".", name)
            with open(path, "wb") as f:
                f.write(data)
        out = []
        with zipfile.ZipFile(path) as z:
            member = next(n for n in z.namelist() if n.endswith("_PKT.csv"))
            r = csv.reader(io.TextIOWrapper(z.open(member), encoding="utf-8-sig"), delimiter=";")
            head = next(r)
            log("swissNAMES3D columns: %s" % ";".join(head))
            seen, cats = set(), {}
            for row in r:
                d = dict(zip(head, row))
                if d.get("OBJEKTART") != "Ort":
                    continue
                x, y = lv95_to_local(float(d["E"]), float(d["N"]))
                key = (d["NAME"], round(x), round(y))
                if key in seen:                  # the same name of the same place listed twice
                    continue
                seen.add(key)
                cat = d.get("EINWOHNERKATEGORIE", "")
                cats[cat] = cats.get(cat, 0) + 1
                out.append((d["NAME"], x, y, population(cat)))
        log("swissNAMES3D: %d settlements (%s), population classes %s" % (
            len(out), os.path.basename(path), json.dumps(cats, ensure_ascii=False)))
        return out
    except Exception as e:                       # the cloud sessions have no swisstopo: the fallback names
        log("swissNAMES3D not available (%s): spawn names from the village points" % e)
        return []


def population(cat):
    """The lower bound of a swissNAMES3D population class ("100 bis 499", "1'000 bis 1'999", "< 20", ""): 0 unknown."""
    nums = re.findall(r"\d+", (cat or "").replace("'", "").replace("\u2019", ""))
    if not nums or cat.strip().startswith("<") or "unter" in cat.lower():
        return 0
    return int(nums[0])


def _unslug(s):
    """'vira__gambarogno' -> 'Vira (Gambarogno)', 'cassina_d_agno' -> "Cassina d'Agno", 's__nazzaro' -> 'S. Nazzaro'."""
    s = re.sub(r"^s__", "s. ", s)
    s = re.sub(r"^sta__", "sta. ", s)
    m = re.fullmatch(r"(.+?)__(.+)", s)
    if m:
        s = "%s (%s)" % (m.group(1), m.group(2))
    s = re.sub(r"_(d|l)_", r" \1'", s).replace("_", " ")
    small = {"di", "in", "d'", "sopra", "del", "della", "al", "da"}
    words = [w if w in small else w[:1].upper() + w[1:] for w in s.split(" ")]
    words = [w[:2].upper() + w[2:] if w.startswith("(") else w for w in words]
    return re.sub(r"(d|l)' ", r"\1'", " ".join(words))


def _slug(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_")


DIRS = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")


def _away(x, y, px, py):
    d = math.hypot(x - px, y - py)
    a = math.degrees(math.atan2(y - py, x - px)) % 360
    return d, DIRS[int((a + 22.5) // 45) % 8]


def _weight(pop, village):
    """How much farther a bigger place may be than a hamlet and still name a point (village: a village point's name)."""
    w = 1.0 + (pop >= 50) * 0.3 + (pop >= 200) * 0.5 + (pop >= 1000) * 0.7
    return max(w, 2.0) if village else w


def _with_dist(lab, d, dirn):
    return "%s (%s km %s)" % (lab, ("%.1f" % (d / 1000)) if d < 1950 else "%.0f" % (d / 1000), dirn)


def spawn_names(spawns, settlements):
    """{objectname: label} for the SpawnSphere objects (name, position) of the base, from the settlements.

    A village point (spawn_<slug>) takes its village's name. A route point (GENERIC) takes the name of the place that
    is nearest when a bigger place counts as nearer (_weight: a village 1.2 km off beats a farm 0.6 km off) and
    no other point has: within NEAR_M x weight the plain name, else "<place> (2.3 km NE)" from the best place within
    FAR_M, else from the biggest near place. A name still given twice gets a number."""
    pts = [(o["name"], float(o["position"][0]), float(o["position"][1])) for o in spawns]
    slugs = {}
    for name, x, y in pts:
        m = re.fullmatch(r"ti_[m0-9]+_[m0-9]+_spawn_(.+)", name) or re.fullmatch(r"spawn_(.+)", name)
        slug = m.group(1) if m else name
        slugs[name] = slug                       # spawn_magliaso_paese: the village Magliaso, not a route point
    village_of = {n: s[:-6] if s.endswith("_paese") else s for n, s in slugs.items()}
    villages = {village_of[n] for n, s in slugs.items() if s not in GENERIC}
    out, used = {}, set()
    if settlements:
        S = np.array([[s[1], s[2]] for s in settlements])
        W = np.array([_weight(s[3] if len(s) > 3 else 0, _slug(s[0]) in villages) for s in settlements])
        by_slug = {}
        for k, s in enumerate(settlements):
            by_slug.setdefault(_slug(s[0]), []).append(k)
        # the village points first: their own name (the nearest place of that name)
        for name, x, y in pts:
            if slugs[name] in GENERIC:
                continue
            slug = village_of[name]
            ks = [q for q in by_slug.get(slug, ()) if math.hypot(S[q, 0] - x, S[q, 1] - y) <= 3 * NEAR_M]
            if ks:
                k = min(ks, key=lambda q: (S[q, 0] - x) ** 2 + (S[q, 1] - y) ** 2)
            else:
                k = int(np.argmin(((S - [x, y]) ** 2).sum(1) / W ** 2))
            d, dirn = _away(x, y, S[k, 0], S[k, 1])
            out[name] = settlements[k][0] if d <= NEAR_M * W[k] else _with_dist(settlements[k][0], d, dirn)
            used.add(settlements[k][0])
        for name, x, y in sorted(pts):
            if slugs[name] not in GENERIC:
                continue
            d = np.hypot(S[:, 0] - x, S[:, 1] - y)
            order = np.argsort(d / W)
            lab = None
            for k in order[:60]:
                if d[k] > FAR_M or settlements[k][0] in used:
                    continue
                lab = settlements[k][0] if d[k] <= NEAR_M * W[k] else _with_dist(settlements[k][0], *_away(x, y, *S[k]))
                break
            if lab is None:                      # nothing free near: the best place, with distance and direction
                k = int(order[0])
                lab = _with_dist(settlements[k][0], *_away(x, y, *S[k]))
            out[name] = lab
            used.add(settlements[k][0])
    else:                                        # no gazetteer: the village slugs as words, route points after them
        named = [(_unslug(village_of[n]), x, y) for n, x, y in pts if slugs[n] not in GENERIC]
        for name, x, y in pts:
            if slugs[name] not in GENERIC:
                out[name] = _unslug(village_of[name])
            elif named:
                lab, px, py = min(named, key=lambda q: (q[1] - x) ** 2 + (q[2] - y) ** 2)
                d, dirn = _away(x, y, px, py)
                out[name] = lab if d <= NEAR_M else _with_dist(lab, d, dirn)
            else:
                out[name] = name
    # a label still given twice: a number (the village points keep the plain name)
    count = {}
    for name in sorted(out, key=lambda n: (slugs[n] in GENERIC, n)):
        lab = out[name]
        n = 2
        while lab in count:
            lab = "%s %d" % (out[name], n)
            n += 1
        out[name] = lab
        count[lab] = 1
    return out


def places_of(spawns, labels):
    """[{name, label, x, y}] for the map page, sorted by label."""
    out = [{"name": o["name"], "label": labels.get(o["name"], o["name"]),
            "x": round(float(o["position"][0]), 1), "y": round(float(o["position"][1]), 1)} for o in spawns]
    return sorted(out, key=lambda p: unicodedata.normalize("NFKD", p["label"]).lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ground", required=True, help="npz of farlod.Ground.save")
    ap.add_argument("--base", required=True, help="levels/ticino of a base (stream.json, main/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", help="folder with the swissNAMES3D csv zip (cache)")
    a = ap.parse_args()
    s = json.load(open(os.path.join(a.base, "stream.json")))
    d = np.load(a.ground)
    cx0, cy0, ncx, ncy, tm = d["o"]
    sq = float(tm) / 32
    objs = []
    for dp, _, fs in os.walk(os.path.join(a.base, "main")):
        for f in fs:
            if f == "items.level.json":
                objs += [json.loads(l) for l in open(os.path.join(dp, f)) if l.strip()]
    spawns = [o for o in objs if o.get("class") == "SpawnSphere"]
    labels = spawn_names(spawns, fetch_settlements(a.names))
    for k in sorted(labels)[:400]:
        print(k, "->", labels[k])
    build(d["H"], d["C"].astype(np.float32), s["origin"][0] + int(cx0) * float(tm), s["origin"][1] + int(cy0) * float(tm),
          sq, roads_of(objs), a.out, places_of(spawns, labels))


if __name__ == "__main__":
    main()
