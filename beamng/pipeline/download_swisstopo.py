"""Download the swisstopo open-data tiles covering the map (latest year per tile).

  swissALTI3D 0.5 m DTM, swissSURFACE3D 0.5 m DSM: every 1 km tile touching the playable area
      (area.py) + 200 m
  swissBUILDINGS3D 3.0 (FileGDB): all sheets touching the area, unzipped
  SWISSIMAGE 2 m: the whole terrain block (colours of roofs, trees, bare rock)
  swissALTI3D 2 m: BACKDROP_HALF around the area (terrain block margins and the distant backdrop)
  Copernicus GLO-30: the Italian side
  swissNAMES3D: the names of the villages (places.py)
Optional: SWISSIMAGE 10 cm and swissSURFACE3D LiDAR within CORRIDOR m of the Street View route
(--route-extras; only the photo-based steps of the original route use them).
Re-runnable: finished files are skipped.
"""
import os, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
from config import DATA, local_to_lv95, lv95_to_wgs
import area

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/{}/items"
CORRIDOR = 250
BACKDROP_HALF = 11000


def stac_items(coll, e_min, n_min, e_max, n_max):
    """Items of a collection intersecting an LV95 rectangle (its WGS84 bounding box)."""
    ll = [lv95_to_wgs(e, n) for e in (e_min, e_max) for n in (n_min, n_max)]
    la1, la2 = min(p[0] for p in ll), max(p[0] for p in ll)
    lo1, lo2 = min(p[1] for p in ll), max(p[1] for p in ll)
    url, params, out = STAC.format(coll), {"bbox": f"{lo1},{la1},{lo2},{la2}", "limit": 100}, []
    while url:
        for attempt in range(5):
            try:
                j = requests.get(url, params=params, timeout=60).json()
                break
            except Exception as e:
                print("retry", url, e, flush=True)
                time.sleep(5 * (attempt + 1))
        out += j["features"]
        params = None
        url = next((l["href"] for l in j.get("links", []) if l["rel"] == "next"), None)
    return out


def latest_per_tile(items):
    best = {}
    for f in items:
        tile, year = f["id"].split("_")[-1], f["id"].split("_")[-2]
        if tile not in best or year > best[tile][0]:
            best[tile] = (year, f)
    return {t: f for t, (y, f) in best.items()}


def fetch(url, dest):
    if os.path.exists(dest):
        return dest, "skip"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(5):
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest + ".part", "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(dest + ".part", dest)
            return dest, "ok"
        except Exception as e:
            print("retry", url, e, flush=True)
            time.sleep(5 * (attempt + 1))
    return dest, "FAILED"


def unzip_gdb(path):
    """Unpack a swissBUILDINGS3D FileGDB next to the others (data/buildings3d/unz)."""
    out = os.path.join(os.path.dirname(path), "unz")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        top = names[0].split("/")[0]
        if not os.path.exists(os.path.join(out, top)):
            z.extractall(out)


def main(route_extras=False):
    ax0, ay0, ax1, ay1 = area.bounds(200.0)
    ae = [local_to_lv95(x, y) for x in (ax0, ax1) for y in (ay0, ay1)]
    e_rng = (min(p[0] for p in ae), max(p[0] for p in ae))
    n_rng = (min(p[1] for p in ae), max(p[1] for p in ae))
    area_tiles = set(area.tiles_1km(200.0))
    tx0, ty0, tx1, ty1 = area.terrain_bounds()
    te = [local_to_lv95(x, y) for x in (tx0 - 100, tx1 + 100) for y in (ty0 - 100, ty1 + 100)]
    block_tiles = set(area.lv95_rect_tiles(min(p[0] for p in te), min(p[1] for p in te),
                                           max(p[0] for p in te), max(p[1] for p in te)))
    ce, cn = local_to_lv95(0.5 * (ax0 + ax1), 0.5 * (ay0 + ay1))
    far = (ce - BACKDROP_HALF, cn - BACKDROP_HALF, ce + BACKDROP_HALF, cn + BACKDROP_HALF)
    far_tiles = set(area.lv95_rect_tiles(*far))
    jobs, gdbs = [], []

    def add(coll, suffix, sub, rect, keep=None):
        items = latest_per_tile(stac_items(coll, *rect))
        n = 0
        for tile, f in sorted(items.items()):
            if "-" not in tile:      # nationwide releases (several GB), not a map sheet/tile
                continue
            if keep is not None and tile not in keep:
                continue
            for name, a in f["assets"].items():
                if name.endswith(suffix):
                    jobs.append((a["href"], os.path.join(DATA, sub, name)))
                    if suffix.endswith(".gdb.zip"):
                        gdbs.append(os.path.join(DATA, sub, name))
                    n += 1
        print(f"{coll} {suffix}: {n} files", flush=True)

    rect = (e_rng[0], n_rng[0], e_rng[1], n_rng[1])
    add("ch.swisstopo.swissalti3d", "_0.5_2056_5728.tif", "swissalti3d_05", rect, area_tiles)
    add("ch.swisstopo.swisssurface3d-raster", "_0.5_2056_5728.tif", "dsm_05", rect, area_tiles)
    add("ch.swisstopo.swissbuildings3d_3_0", ".gdb.zip", "buildings3d", rect)
    blk = (min(p[0] for p in te), min(p[1] for p in te), max(p[0] for p in te), max(p[1] for p in te))
    add("ch.swisstopo.swissimage-dop10", "_2_2056.tif", "swissimage_2", blk, block_tiles)
    add("ch.swisstopo.swissalti3d", "_2_2056_5728.tif", "swissalti3d_2", far, far_tiles)
    if route_extras:
        import json
        from config import DATASET, wgs_to_lv95
        panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
        route = np.array([wgs_to_lv95(p["lat"], p["lon"]) for p in panos])

        def near_route(tile):
            e, n = (int(v) * 1000 for v in tile.split("-"))
            cx = np.clip(route[:, 0], e, e + 1000)
            cy = np.clip(route[:, 1], n, n + 1000)
            return np.hypot(route[:, 0] - cx, route[:, 1] - cy).min() < CORRIDOR
        near = {t for t in area_tiles if near_route(t)}
        add("ch.swisstopo.swissimage-dop10", "_0.1_2056.tif", "swissimage_010", rect, near)
        add("ch.swisstopo.swisssurface3d", ".las.zip", "lidar", rect, near)
    # swissNAMES3D: names of the villages (spawn points, places.py); one national CSV package
    items = stac_items("ch.swisstopo.swissnames3d", *rect)
    latest = sorted(items, key=lambda f: f["id"])[-1] if items else None
    if latest:
        for name, a in latest["assets"].items():
            if name.endswith("_2056.csv.zip"):
                jobs.append((a["href"], os.path.join(DATA, "names", name)))
    # Copernicus GLO-30 (covers the Italian side for the terrain margins and the backdrop)
    for lat in (45, 46):
        for lon in (8, 9):
            name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"
            jobs.append((f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif",
                         os.path.join(DATA, "copdem30", name + ".tif")))
    print(len(jobs), "files queued", flush=True)
    failed = 0
    with ThreadPoolExecutor(4) as ex:
        for dest, status in ex.map(lambda j: fetch(*j), jobs):
            if status != "skip":
                print(status, os.path.relpath(dest, DATA), flush=True)
            failed += status == "FAILED"
    for g in gdbs:
        if os.path.exists(g):
            unzip_gdb(g)
    print("DONE", "failed %d" % failed, flush=True)


if __name__ == "__main__":
    main(route_extras="--route-extras" in sys.argv)
