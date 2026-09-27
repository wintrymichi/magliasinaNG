"""Download Ticino cadastral survey (Misurazione ufficiale, MOpublic) layers for the map
from the geodienste.ch WFS (open data, attribution required):
  LCSF  copertura del suolo (road, sidewalk, island, building, garden, forest, water ...)
  SOSF / SOLI / SOPT  oggetti singoli as surfaces / lines / points (walls, stairs, bridges ...)
over the playable area (area.py) + MARGIN, in TILE m requests paged by COUNT features.
Saved as GeoJSON (LV95) in data/av/.
"""
import json, os, time
import numpy as np
import requests
import shapely
from config import DATA
import area

WFS = "https://geodienste.ch/db/av_0/ita"
LAYERS = ["LCSF", "SOSF", "SOLI", "SOPT"]
TILE = 1024.0
MARGIN = 100.0
COUNT = 5000


def fetch(layer, bbox, start=0):
    params = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=f"ms:{layer}",
                  OUTPUTFORMAT="application/json; subtype=geojson", SRSNAME="EPSG:2056",
                  BBOX=",".join(f"{v:.1f}" for v in bbox) + ",urn:ogc:def:crs:EPSG::2056",
                  COUNT=str(COUNT), STARTINDEX=str(start))
    for attempt in range(6):
        try:
            r = requests.get(WFS, params=params, timeout=300)
            r.raise_for_status()
            return r.json()["features"]
        except Exception as e:
            print("retry", layer, bbox, start, e, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed {layer} {bbox}")


def main():
    out_dir = os.path.join(DATA, "av")
    os.makedirs(out_dir, exist_ok=True)
    g = area.lv95_polygon(MARGIN)
    shapely.prepare(g)
    e0, n0, e1, n1 = g.bounds
    boxes = [(e, n, min(e + TILE, e1), min(n + TILE, n1)) for e in np.arange(e0, e1, TILE) for n in np.arange(n0, n1, TILE)]
    boxes = [b for b in boxes if g.intersects(shapely.box(*b))]
    for layer in LAYERS:
        dest = os.path.join(out_dir, f"{layer}.geojson")
        if os.path.exists(dest):
            print(layer, "exists", flush=True)
            continue
        feats, seen = [], set()
        for b in boxes:
            start = 0
            while True:
                page = fetch(layer, b, start)
                for f in page:
                    fid = f.get("id") or json.dumps(f["properties"], sort_keys=True) + str(f["geometry"])[:200]
                    if fid not in seen:
                        seen.add(fid)
                        feats.append(f)
                if len(page) < COUNT:
                    break
                start += COUNT
        json.dump({"type": "FeatureCollection", "features": feats}, open(dest + ".part", "w"))
        os.replace(dest + ".part", dest)
        print(layer, len(feats), "features", flush=True)


if __name__ == "__main__":
    main()
