"""Download Ticino cadastral survey (Misurazione ufficiale, MOpublic) layers for the map
from the geodienste.ch WFS (open data, attribution required):
  LCSF  copertura del suolo (road, sidewalk, island, building, garden, forest, water ...)
  SOSF / SOLI / SOPT  oggetti singoli as surfaces / lines / points (walls, stairs, fountains ...)
Saved as GeoJSON (LV95) in data/av/.
"""
import json, os, time
import requests
from config import DATA, E0, N0, TER_HALF, K

WFS = "https://geodienste.ch/db/av_0/ita"
LAYERS = ["LCSF", "SOSF", "SOLI", "SOPT"]
TILE = 1024.0


def fetch(layer, bbox):
    params = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=f"ms:{layer}",
                  OUTPUTFORMAT="application/json; subtype=geojson", SRSNAME="EPSG:2056",
                  BBOX=",".join(f"{v:.1f}" for v in bbox) + ",urn:ogc:def:crs:EPSG::2056")
    for attempt in range(5):
        try:
            r = requests.get(WFS, params=params, timeout=180)
            r.raise_for_status()
            return r.json()["features"]
        except Exception as e:
            print("retry", layer, bbox, e, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed {layer} {bbox}")


def main():
    out_dir = os.path.join(DATA, "av")
    os.makedirs(out_dir, exist_ok=True)
    h = TER_HALF * K + 20
    for layer in LAYERS:
        feats, seen = [], set()
        e = E0 - h
        while e < E0 + h:
            n = N0 - h
            while n < N0 + h:
                for f in fetch(layer, (e, n, min(e + TILE, E0 + h), min(n + TILE, N0 + h))):
                    fid = f.get("id") or json.dumps(f["properties"], sort_keys=True) + str(f["geometry"])[:200]
                    if fid not in seen:
                        seen.add(fid)
                        feats.append(f)
                n += TILE
            e += TILE
        json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(out_dir, f"{layer}.geojson"), "w"))
        print(layer, len(feats), "features", flush=True)


if __name__ == "__main__":
    main()
