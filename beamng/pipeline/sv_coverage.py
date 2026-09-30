"""Street View coverage of the whole playable area (v2.2 review), for the comparison of the map with
the real roads.

Every Google Street View panorama (official coverage, most recent capture of each place) inside the
area (area.py) + MARGIN m is listed from the coverage tiles of Google Maps (XYZ tiles at zoom 17,
the call the map makes for the blue lines), then completed one by one with its capture date.
The panoramas are only a visual reference: their images are downloaded by sv_fetch.py into WORK and
never enter the level or the repository.

Output: WORK/sv/coverage.json and beamng/dati/sv_coverage.json.gz (metadata only: id, position,
elevation, orientation, date, links; the same kind of data as panoramas.json of the dataset).
    python sv_coverage.py [--dates]
Needs the `streetlevel` package (see sv_fetch.py).
"""
import gzip, json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import shapely
from config import WORK, local_to_lv95, lv95_to_wgs, wgs_to_local
import area

MARGIN = 40.0
ZOOM = 17
OUT = os.path.join(WORK, "sv", "coverage.json")
DATI_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "sv_coverage.json.gz")


def tile_of(lat, lon, z=ZOOM):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def tile_box(x, y, z=ZOOM):
    """(lat_min, lon_min, lat_max, lon_max) of an XYZ tile."""
    n = 2 ** z
    lon0, lon1 = x / n * 360.0 - 180.0, (x + 1) / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat0 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lat0, lon0, lat1, lon1


def area_wgs(margin):
    g = area.polygon().buffer(margin)
    return shapely.transform(g, lambda c: np.array([lv95_to_wgs(*local_to_lv95(x, y))[::-1] for x, y in c]))


def tiles():
    g = area_wgs(MARGIN + 50.0)                        # lon, lat
    shapely.prepare(g)
    lon0, lat0, lon1, lat1 = g.bounds
    xa, ya = tile_of(lat1, lon0)
    xb, yb = tile_of(lat0, lon1)
    out = []
    for x in range(xa, xb + 1):
        for y in range(ya, yb + 1):
            la0, lo0, la1, lo1 = tile_box(x, y)
            if g.intersects(shapely.box(lo0, la0, lo1, la1)):
                out.append((x, y))
    return out


def fetch_tile(xy):
    from streetlevel import streetview
    for attempt in range(5):
        try:
            return xy, streetview.get_coverage_tile(*xy)
        except Exception as e:                         # network hiccup or throttling: wait and retry
            time.sleep(2 * (attempt + 1))
            err = e
    print("tile failed", xy, err, flush=True)
    return xy, None


def fetch_date(pid):
    from streetlevel import streetview
    for attempt in range(4):
        try:
            p = streetview.find_panorama_by_id(pid)
            if p is None:
                return pid, None
            return pid, {"date": str(p.date) if p.date else None,
                         "historical": [[h.id, str(h.date)] for h in (p.historical or [])],
                         "address": " ".join(str(a.value) for a in (p.address or []))[:120]
                         if getattr(p, "address", None) else ""}
        except Exception:
            time.sleep(2 * (attempt + 1))
    return pid, None


def main(dates=False):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tl = tiles()
    print(len(tl), "coverage tiles", flush=True)
    keep = area.polygon().buffer(MARGIN)
    shapely.prepare(keep)
    panos, failed = {}, []
    with ThreadPoolExecutor(8) as ex:
        for k, (xy, res) in enumerate(ex.map(fetch_tile, tl)):
            if res is None:
                failed.append(xy)
                continue
            for p in res:
                x, y = wgs_to_local(p.lat, p.lon)
                if not keep.contains(shapely.Point(x, y)):
                    continue
                panos[p.id] = {"id": p.id, "lat": p.lat, "lon": p.lon, "x": round(x, 2), "y": round(y, 2),
                               "elevation": p.elevation, "heading_deg": round(math.degrees(p.heading), 2),
                               # the coverage tiles give the tilt of the camera 90 degrees apart from
                               # the single panorama call (dataset panoramas.json): same convention here
                               "pitch_deg": round(math.degrees(p.pitch or 0) - 90.0, 2),
                               "roll_deg": round(math.degrees(p.roll or 0), 2),
                               "links": [l.pano.id for l in (p.links or [])]}
            if k % 100 == 0:
                print("  tiles %d/%d, %d panoramas" % (k + 1, len(tl), len(panos)), flush=True)
    old = {}
    if os.path.exists(OUT):
        old = {p["id"]: p for p in json.load(open(OUT))["panoramas"]}
    for pid, p in panos.items():
        for k in ("date", "historical", "address"):
            if k in old.get(pid, {}):
                p[k] = old[pid][k]
    if dates:
        todo = [pid for pid, p in panos.items() if "date" not in p]
        print(len(todo), "dates to fetch", flush=True)
        with ThreadPoolExecutor(8) as ex:
            for k, (pid, info) in enumerate(ex.map(fetch_date, todo)):
                if info:
                    panos[pid].update(info)
                if k % 500 == 0:
                    print("  dates %d/%d" % (k + 1, len(todo)), flush=True)
    res = {"tiles": len(tl), "failed_tiles": failed, "panoramas": sorted(panos.values(), key=lambda p: p["id"])}
    json.dump(res, open(OUT, "w"))
    with gzip.open(DATI_OUT, "wt", encoding="utf-8") as f:
        json.dump({"source": "Google Street View coverage (metadata only, no images)",
                   "panoramas": [{k: p.get(k) for k in ("id", "lat", "lon", "elevation", "heading_deg", "pitch_deg",
                                                        "roll_deg", "date", "links")} for p in res["panoramas"]]},
                  f, separators=(",", ":"))
    from collections import Counter
    years = Counter((p.get("date") or "?")[:4] for p in panos.values())
    print("panoramas", len(panos), "failed tiles", len(failed), "years", dict(sorted(years.items())))


if __name__ == "__main__":
    main(dates="--dates" in sys.argv)
