"""OpenStreetMap data of the playable area (Overpass API), for what swisstopo and the cadastral survey
do not record: one-way streets, street names, speed limits, pedestrian crossings, traffic signals,
stop / give-way points, traffic signs, bus stops, street lamps, guard rails and other barriers,
benches and the railway details.

One query over the bounding box of the area (area.py) + MARGIN m; output data/osm/osm_area.json
(Overpass JSON with the geometry of every way), and the municipalities (admin_level 8, their
boundaries come from swissBOUNDARIES3D) in data/osm/communes.json for the zones of zone_report.py.
Re-runnable: existing files are kept. The release is built with the extract kept in the repository
(dati/osm_area.json.gz, dati/osm_communes.json.gz), so that it does not change with OSM or depend on
the Overpass servers; --pin copies the downloaded files there.
    python download_osm.py [--pin]
(c) OpenStreetMap contributors, ODbL 1.0: the extracts in dati/ are under the ODbL.
"""
import gzip, json, os, shutil, sys, time
import requests
from config import DATA, local_to_lv95, lv95_to_wgs
import area

URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
MARGIN = 300.0
OUT = os.path.join(DATA, "osm", "osm_area.json")
COMMUNES = os.path.join(DATA, "osm", "communes.json")
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
PINNED = {OUT: os.path.join(DATI, "osm_area.json.gz"), COMMUNES: os.path.join(DATI, "osm_communes.json.gz")}
QUERY_COMMUNES = """[out:json][timeout:300];
relation["boundary"="administrative"]["admin_level"="8"]({bbox});
out body geom;
"""
QUERY = """[out:json][timeout:600][maxsize:1073741824];
(
  way["highway"]({bbox});
  way["railway"]({bbox});
  way["barrier"]({bbox});
  way["waterway"]({bbox});
  way["man_made"~"bridge|embankment|pier"]({bbox});
  way["amenity"~"parking|bench"]({bbox});
  way["public_transport"]({bbox});
  node["highway"]({bbox});
  node["railway"]({bbox});
  node["traffic_sign"]({bbox});
  node["public_transport"]({bbox});
  node["barrier"]({bbox});
  node["amenity"~"bench|waste_basket|post_box|telephone|drinking_water|fountain|parking_entrance|recycling|charging_station|fuel"]({bbox});
  node["man_made"~"street_cabinet|mast|flagpole|cross|water_tap"]({bbox});
  node["historic"~"wayside_shrine|wayside_cross|memorial"]({bbox});
  node["leisure"~"picnic_table"]({bbox});
  node["tourism"~"information|viewpoint"]({bbox});
);
out body geom qt;
"""


def bbox():
    x0, y0, x1, y1 = area.bounds(MARGIN)
    ll = [lv95_to_wgs(*local_to_lv95(x, y)) for x in (x0, x1) for y in (y0, y1)]
    return "%.6f,%.6f,%.6f,%.6f" % (min(p[0] for p in ll), min(p[1] for p in ll), max(p[0] for p in ll),
                                    max(p[1] for p in ll))


def overpass(q):
    for attempt in range(6):
        url = URLS[attempt % len(URLS)]
        try:
            r = requests.post(url, data={"data": q}, timeout=900,
                              headers={"User-Agent": "magliasinaNG BeamNG map pipeline (github.com/wintrymichi/magliasinaNG)"})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("retry", url, e, flush=True)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("Overpass failed")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path, query in ((OUT, QUERY), (COMMUNES, QUERY_COMMUNES)):
        if os.path.exists(path):
            print(path, "exists")
            continue
        d = overpass(query.replace("{bbox}", bbox()))
        d["bbox"] = bbox()
        json.dump(d, open(path + ".part", "w"))
        os.replace(path + ".part", path)
        n = {}
        for e in d["elements"]:
            n[e["type"]] = n.get(e["type"], 0) + 1
        print(os.path.basename(path), "OSM elements", n, "timestamp", d.get("osm3s", {}).get("timestamp_osm_base"))
    if "--pin" in sys.argv[1:]:
        for path, pinned in PINNED.items():
            with open(path, "rb") as src, gzip.open(pinned, "wb", compresslevel=9) as dst:
                shutil.copyfileobj(src, dst)
            print("kept in the repository:", pinned)


if __name__ == "__main__":
    main()
