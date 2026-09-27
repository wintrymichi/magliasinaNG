"""Download the swisstopo open-data tiles covering the map (latest year per tile).

  swissALTI3D 0.5 m DTM, SWISSIMAGE 10 cm orthophoto, swissSURFACE3D 0.5 m DSM:
      every 1 km tile of the 4096 m terrain square
  swissSURFACE3D LiDAR (LAZ): only tiles within CORRIDOR m of the Street View route
  swissBUILDINGS3D 3.0 (FileGDB): all sheets touching the terrain square
  swissALTI3D 2 m: 16 km square for the distant backdrop
Re-runnable: finished files are skipped.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
from config import DATA, DATASET, E0, N0, TER_HALF, wgs_to_lv95, lv95_to_wgs

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/{}/items"
CORRIDOR = 250
BACKDROP_HALF = 8000


def stac_items(coll, e_min, n_min, e_max, n_max):
    la1, lo1 = lv95_to_wgs(e_min, n_min)
    la2, lo2 = lv95_to_wgs(e_max, n_max)
    url, params, out = STAC.format(coll), {"bbox": f"{lo1},{la1},{lo2},{la2}", "limit": 100}, []
    while url:
        j = requests.get(url, params=params, timeout=60).json()
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


def tile_ok(tile, e_rng, n_rng):
    e, n = (int(v) * 1000 for v in tile.split("-"))
    return e_rng[0] - 1000 < e < e_rng[1] and n_rng[0] - 1000 < n < n_rng[1]


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


def main():
    e_rng = (E0 - TER_HALF - 50, E0 + TER_HALF + 50)
    n_rng = (N0 - TER_HALF - 50, N0 + TER_HALF + 50)
    jobs = []

    def add(coll, suffix, sub, e_r=e_rng, n_r=n_rng, keep=lambda t: True):
        items = latest_per_tile(stac_items(coll, e_r[0], n_r[0], e_r[1], n_r[1]))
        n = 0
        for tile, f in sorted(items.items()):
            if "-" not in tile:      # nationwide releases (several GB), not a map sheet/tile
                continue
            if coll != "ch.swisstopo.swissbuildings3d_3_0" and not (tile_ok(tile, e_r, n_r) and keep(tile)):
                continue
            for name, a in f["assets"].items():
                if name.endswith(suffix):
                    jobs.append((a["href"], os.path.join(DATA, sub, name)))
                    n += 1
        print(f"{coll} {suffix}: {n} files", flush=True)

    # route points (LV95) for the LiDAR corridor
    panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
    route = np.array([wgs_to_lv95(p["lat"], p["lon"]) for p in panos])

    def near_route(tile):
        e, n = (int(v) * 1000 for v in tile.split("-"))
        cx = np.clip(route[:, 0], e, e + 1000)
        cy = np.clip(route[:, 1], n, n + 1000)
        return np.hypot(route[:, 0] - cx, route[:, 1] - cy).min() < CORRIDOR

    add("ch.swisstopo.swissalti3d", "_0.5_2056_5728.tif", "swissalti3d_05")
    add("ch.swisstopo.swisssurface3d-raster", "_0.5_2056_5728.tif", "dsm_05")
    add("ch.swisstopo.swissbuildings3d_3_0", ".gdb.zip", "buildings3d")
    add("ch.swisstopo.swissimage-dop10", "_0.1_2056.tif", "swissimage_010")
    add("ch.swisstopo.swisssurface3d", ".las.zip", "lidar", keep=near_route)
    add("ch.swisstopo.swissalti3d", "_2_2056_5728.tif", "swissalti3d_2",
        e_r=(E0 - BACKDROP_HALF, E0 + BACKDROP_HALF), n_r=(N0 - BACKDROP_HALF, N0 + BACKDROP_HALF))
    # Copernicus GLO-30 (covers the Italian side for the backdrop)
    for lat in (45, 46):
        for lon in (8, 9):
            name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"
            jobs.append((f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif",
                         os.path.join(DATA, "copdem30", name + ".tif")))
    print(len(jobs), "files queued", flush=True)
    with ThreadPoolExecutor(4) as ex:
        for dest, status in ex.map(lambda j: fetch(*j), jobs):
            print(status, os.path.relpath(dest, DATA), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
