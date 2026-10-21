"""swisstopo and cadastral open data of a window around the Via Cantonale bridges over the Magliasina (Magliaso
roundabout), for ponte_ref.yml: usage rif_fetch.py <download dir> <output dir>.

Output (LV95 / LN02, window of HALF m around the bridges):
  ortho.jpg + ortho.json     SWISSIMAGE 10 cm, north up (bounds in the json)
  dsm05.npy, dtm05.npy       swissSURFACE3D raster and swissALTI3D 0.5 m, same window, row 0 = north
  lidar.npz                  swissSURFACE3D points (E, N, Z, classification) within LIDAR_HALF m
  tlm_*.json                 swissTLM3D roads and streams in the window (download_tlm.py format)
  av_*.json                  cadastral survey (MOpublic) LCSF / SOSF / SOLI in the window (GeoJSON)
"""
import io, json, os, sys, zipfile
import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "pipeline"))
os.environ.setdefault("MAGLIASO_ROOT", os.path.join(sys.argv[1], "bm"))
from config import lv95_to_wgs                       # noqa: E402

CE, CN = 2711622.0, 1093273.0                        # between the two decks (ponti.json, segments 39 and 238)
HALF = 120.0
LIDAR_HALF = 70.0
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/{}/items"


def stac_asset(coll, suffix):
    la, lo = lv95_to_wgs(CE, CN)
    j = requests.get(STAC.format(coll), params={"bbox": f"{lo - 1e-4},{la - 1e-4},{lo + 1e-4},{la + 1e-4}",
                                                "limit": 100}, timeout=60).json()
    best = None
    for f in j["features"]:
        for name, a in f["assets"].items():
            if name.endswith(suffix) and (best is None or f["id"] > best[0]):
                best = (f["id"], a["href"], name)
    print(coll, best, flush=True)
    return best[1], best[2]


def get(url, dest):
    if not os.path.exists(dest):
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for c in r.iter_content(1 << 20):
                    f.write(c)
    return dest


def cut(path, half=HALF):
    import rasterio
    from rasterio.windows import from_bounds
    with rasterio.open(path) as ds:
        w = from_bounds(CE - half, CN - half, CE + half, CN + half, ds.transform)
        return ds.read(window=w, boundless=True)


def main(dl, out):
    os.makedirs(dl, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    from PIL import Image
    bounds = [CE - HALF, CN - HALF, CE + HALF, CN + HALF]
    u, n = stac_asset("ch.swisstopo.swissimage-dop10", "_0.1_2056.tif")
    a = cut(get(u, os.path.join(dl, n)))
    Image.fromarray(np.moveaxis(a[:3], 0, -1)).save(os.path.join(out, "ortho.jpg"), quality=90)
    json.dump({"bounds_lv95": bounds, "res": 0.1, "source": n}, open(os.path.join(out, "ortho.json"), "w"))
    for coll, key in (("ch.swisstopo.swisssurface3d-raster", "dsm05"), ("ch.swisstopo.swissalti3d", "dtm05")):
        u, n = stac_asset(coll, "_0.5_2056_5728.tif")
        np.save(os.path.join(out, key + ".npy"), cut(get(u, os.path.join(dl, n)))[0].astype(np.float32))
    u, n = stac_asset("ch.swisstopo.swisssurface3d", ".las.zip")
    z = zipfile.ZipFile(get(u, os.path.join(dl, n)))
    import laspy
    las = laspy.read(io.BytesIO(z.read(z.namelist()[0])))
    E, N, Z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
    m = (np.abs(E - CE) < LIDAR_HALF) & (np.abs(N - CN) < LIDAR_HALF)
    np.savez_compressed(os.path.join(out, "lidar.npz"), E=E[m], N=N[m], Z=Z[m].astype(np.float32),
                        cls=np.asarray(las.classification)[m].astype(np.uint8),
                        ret=np.asarray(las.return_number)[m].astype(np.uint8))
    print("lidar points", int(m.sum()), flush=True)
    # swissTLM3D (download_tlm.py streams the national package)
    import download_tlm as T
    zt = zipfile.ZipFile(io.BufferedReader(T.RangeFile(T.URL), buffer_size=1 << 22))
    names = {nm.replace("/", "\\"): nm for nm in zt.namelist()}
    for layer in ("TLM_STRASSE", "TLM_FLIESSGEWAESSER"):
        stem = T.LAYERS[layer]
        with zt.open(names[stem + ".shp"]) as f:
            geoms = dict(T.shp_records(io.BufferedReader(f, 1 << 22), bounds))
        with zt.open(names[stem + ".dbf"]) as f:
            fields, props = T.dbf_records(io.BufferedReader(f, 1 << 22), geoms.keys())
        feats = [{"props": props.get(i, {}), "parts": [np.round(p, 3).tolist() for p in parts]}
                 for i, parts in sorted(geoms.items())]
        json.dump({"fields": fields, "features": feats}, open(os.path.join(out, f"tlm_{layer}.json"), "w"))
        print(layer, len(feats), flush=True)
    # cadastral survey
    import download_av as A
    for layer in ("LCSF", "SOSF", "SOLI"):
        try:
            feats = A.fetch(layer, bounds)
        except Exception as e:                      # the WFS is optional for the review
            print("av", layer, e, flush=True)
            continue
        json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(out, f"av_{layer}.json"), "w"))
        print("av", layer, len(feats), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
