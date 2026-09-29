"""The 10 cm SWISSIMAGE orthophoto of the whole area, read window by window from the swisstopo
cloud-optimised GeoTIFFs (no local copy of the 70 tiles, about 5.5 GB).

sample(X, Y) -> RGB at local points (bilinear), for the straightened strips of network_markings.py.
The tiles are found once with the STAC API (download_swisstopo.stac_items, the latest year per 1 km
tile) and cached in data/swissimage_010_cog.json. Local files in data/swissimage_010/ (the route
extras of download_swisstopo.py) are used first where they exist.
"""
import glob, json, os, threading
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.ndimage import map_coordinates
from config import DATA, local_to_lv95

INDEX = os.path.join(DATA, "swissimage_010_cog.json")
RES = 0.1
PAD = 8                       # pixels read around a window (bilinear sampling at its edge)
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("VSI_CACHE_SIZE", str(256 * 2 ** 20))
for _ca in (os.environ.get("SSL_CERT_FILE"), os.environ.get("REQUESTS_CA_BUNDLE")):   # GDAL reads CURL_CA_BUNDLE
    if _ca and os.path.exists(_ca):
        os.environ.setdefault("CURL_CA_BUNDLE", _ca)
        break
_local = threading.local()


def tile_index():
    """{'EEEE-NNNN': url or local path} of every 1 km tile of the area (+200 m)."""
    if os.path.exists(INDEX):
        return json.load(open(INDEX))
    import area
    from download_swisstopo import stac_items, latest_per_tile
    x0, y0, x1, y1 = area.bounds(200.0)
    ce = [local_to_lv95(x, y) for x in (x0, x1) for y in (y0, y1)]
    items = latest_per_tile(stac_items("ch.swisstopo.swissimage-dop10", min(p[0] for p in ce), min(p[1] for p in ce),
                                       max(p[0] for p in ce), max(p[1] for p in ce)))
    keep = set(area.tiles_1km(200.0))
    out = {}
    for t, f in items.items():
        if t not in keep:
            continue
        for name, a in f["assets"].items():
            if name.endswith("_0.1_2056.tif"):
                out[t] = a["href"]
    json.dump(out, open(INDEX, "w"), indent=0, sort_keys=True)
    return out


def _source(tile):
    """Opened dataset of a tile (one per thread): a local file of the route extras, or the COG."""
    cache = getattr(_local, "ds", None)
    if cache is None:
        cache = _local.ds = {}
    if tile not in cache:
        loc = glob.glob(os.path.join(DATA, "swissimage_010", f"*_{tile}_0.1_2056.tif"))
        url = tile_index().get(tile)
        path = loc[0] if loc else ("/vsicurl/" + url if url else None)
        cache[tile] = rasterio.open(path) if path else None
    return cache[tile]


def sample(X, Y):
    """RGB (n, 3) float32 of the orthophoto at local points X, Y (n,) (NaN outside the tiles)."""
    X = np.asarray(X, np.float64).ravel()
    Y = np.asarray(Y, np.float64).ravel()
    E, N = local_to_lv95(X, Y)
    out = np.full((len(X), 3), np.nan, np.float32)
    te, tn = np.floor(E / 1000).astype(int), np.floor(N / 1000).astype(int)
    for ke, kn in set(zip(te.tolist(), tn.tolist())):
        m = np.flatnonzero((te == ke) & (tn == kn))
        ds = _source(f"{ke}-{kn}")
        if ds is None:
            continue
        col = (E[m] - ds.transform.c) / RES - 0.5
        row = (ds.transform.f - N[m]) / RES - 0.5
        c0, r0 = int(max(np.floor(col.min()) - PAD, 0)), int(max(np.floor(row.min()) - PAD, 0))
        c1, r1 = int(min(np.ceil(col.max()) + PAD, ds.width)), int(min(np.ceil(row.max()) + PAD, ds.height))
        if c1 <= c0 or r1 <= r0:
            continue
        a = ds.read(window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float32)
        for k in range(3):
            out[m, k] = map_coordinates(a[k], [row - r0, col - c0], order=1, mode="nearest")
    return out
