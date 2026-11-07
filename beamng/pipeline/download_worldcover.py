"""ESA WorldCover 2021 (10 m land cover, CC BY 4.0) around the map (v3.0).

The cadastral survey and SWISSIMAGE stop at the border, swissALTI3D at the Swiss edge of the backdrop:
the Italian side of the terrain block and most of the distant backdrop had no land cover at all, so
they were painted as meadow without a tree and the mountains around the map looked bald. WorldCover
says where the forest, the meadows, the villages and the bare rock are, on both sides of the border.

The global map is a set of 3 x 3 degree Cloud Optimised GeoTIFFs on a public S3 bucket; only the
window around the map is read (HTTP range requests through GDAL's /vsicurl/) and written to
data/worldcover/worldcover.tif (EPSG:4326, uint8 classes: 10 tree cover, 20 shrubland, 30 grassland,
40 cropland, 50 built-up, 60 bare / sparse vegetation, 70 snow and ice, 80 water, 90 wetland,
95 mangroves, 100 moss and lichen).
    python download_worldcover.py
"""
import math, os, time
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from config import DATA, local_to_lv95, lv95_to_wgs, TER_X0, TER_Y0, TER_SIZE, TER_SQUARE

URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
       "ESA_WorldCover_10m_2021_v200_{}_Map.tif")
RMAX = 26000.0                    # m from the block centre (backdrop.RMAX and a margin)
OUT = os.path.join(DATA, "worldcover", "worldcover.tif")

TREES, SHRUB, GRASS, CROP, BUILT, BARE, SNOW, WATER, WETLAND, MOSS = 10, 20, 30, 40, 50, 60, 70, 80, 90, 100


def tile_name(lat, lon):
    la, lo = 3 * math.floor(lat / 3), 3 * math.floor(lon / 3)
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def bbox_wgs():
    half = (TER_SIZE - 1) * TER_SQUARE / 2
    cx, cy = TER_X0 + half, TER_Y0 + half
    pts = [lv95_to_wgs(*local_to_lv95(cx + dx, cy + dy)) for dx in (-RMAX, RMAX) for dy in (-RMAX, RMAX)]
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return min(lons), min(lats), max(lons), max(lats)


def main():
    if os.path.exists(OUT):
        print("worldcover: skip", OUT)
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lo0, la0, lo1, la1 = bbox_wgs()
    res = 1 / 12000.0                     # the native 10 m grid (0.3 arc seconds)
    w = int(round((lo1 - lo0) / res)) + 1
    h = int(round((la1 - la0) / res)) + 1
    out = np.zeros((h, w), np.uint8)
    tr = rasterio.transform.from_origin(lo0, la1, res, res)
    tiles = {tile_name(la, lo) for la in (la0, la1) for lo in (lo0, lo1)}
    for t in sorted(tiles):
        for attempt in range(6):
            try:
                with rasterio.open("/vsicurl/" + URL.format(t)) as s:
                    b = s.bounds
                    x0, y0, x1, y1 = max(lo0, b.left), max(la0, b.bottom), min(lo1, b.right), min(la1, b.top)
                    if x1 <= x0 or y1 <= y0:
                        break
                    win = from_bounds(x0, y0, x1, y1, s.transform).round_offsets().round_lengths()
                    a = s.read(1, window=win)
                    wt = s.window_transform(win)
                    c0 = int(round((wt.c - lo0) / res)); r0 = int(round((la1 - wt.f) / res))
                    # the rounded window can start a cell before the box (a negative slice start is an empty slice)
                    a = a[max(0, -r0):, max(0, -c0):]
                    c0, r0 = max(c0, 0), max(r0, 0)
                    hh, ww = min(a.shape[0], h - r0), min(a.shape[1], w - c0)
                    dst = out[r0:r0 + hh, c0:c0 + ww]
                    m = a[:hh, :ww] > 0
                    dst[m] = a[:hh, :ww][m]
                print("worldcover tile", t, "read", flush=True)
                break
            except Exception as e:
                print("retry", t, e, flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"WorldCover tile {t} could not be read")
    with rasterio.open(OUT, "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8", crs="EPSG:4326",
                       transform=tr, compress="deflate", tiled=True, nodata=0) as d:
        d.write(out, 1)
    vals, cnt = np.unique(out, return_counts=True)
    print("worldcover", OUT, w, "x", h, {int(v): round(100 * c / out.size, 1) for v, c in zip(vals, cnt)})


if __name__ == "__main__":
    main()
