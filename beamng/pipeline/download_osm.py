"""OpenStreetMap data of the playable area (Overpass API), for what swisstopo and the cadastral survey
do not record: one-way streets, street names, speed limits, pedestrian crossings, traffic signals,
stop / give-way points, traffic signs, bus stops, street lamps, guard rails and other barriers,
benches and the railway details; and (v2.2) the shops, bars, restaurants, offices and workshops, whose
buildings get shop fronts on the ground floor (facades.py).

One query over the bounding box of the area (area.py) + MARGIN m; output data/osm/osm_area.json
(Overpass JSON with the geometry of every way), the municipalities (admin_level 8, their
boundaries come from swissBOUNDARIES3D) in data/osm/communes.json for the zones of zone_report.py, and
the points of interest in data/osm/pois.json (their centre and tags).
Re-runnable: existing files are kept. The release is built with the extract kept in the repository
(dati/osm_area.json.gz, dati/osm_communes.json.gz, dati/osm_pois.json.gz), so that it does not change with OSM or depend on
the Overpass servers; --pin copies the downloaded files there.
    python download_osm.py [--pin]
    python download_osm.py --add  (v3.0.40) adds to the extracts kept in the repository only the elements over the whole
                                  villages of area.villages() (+ MARGIN) that they do not have yet; the rest stays as
                                  pinned
(c) OpenStreetMap contributors, ODbL 1.0: the extracts in dati/ are under the ODbL.
"""
import gzip, json, os, shutil, sys, time
import numpy as np
import requests
from config import DATA, local_to_lv95, lv95_to_wgs
import area

URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
MARGIN = 300.0
OUT = os.path.join(DATA, "osm", "osm_area.json")
COMMUNES = os.path.join(DATA, "osm", "communes.json")
POIS = os.path.join(DATA, "osm", "pois.json")
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
PINNED = {OUT: os.path.join(DATI, "osm_area.json.gz"), COMMUNES: os.path.join(DATI, "osm_communes.json.gz"),
          POIS: os.path.join(DATI, "osm_pois.json.gz")}
QUERY_COMMUNES = """[out:json][timeout:300];
relation["boundary"="administrative"]["admin_level"="8"]({bbox});
out body geom;
"""
QUERY_POIS = """[out:json][timeout:300];
(
  nwr["shop"]({bbox});
  nwr["amenity"~"restaurant|cafe|bar|pub|bank|pharmacy|post_office|fast_food|ice_cream|doctors|dentist|clinic|kindergarten|school|townhall|library|community_centre|police|fire_station|car_wash|car_rental|veterinary|childcare|marketplace"]({bbox});
  nwr["craft"]({bbox});
  nwr["office"]({bbox});
  nwr["tourism"~"hotel|guest_house|hostel|motel|apartment"]({bbox});
);
out center tags;
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


def bbox(bounds=None):
    x0, y0, x1, y1 = bounds or area.bounds(MARGIN)
    ll = [lv95_to_wgs(*local_to_lv95(x, y)) for x in (x0, x1) for y in (y0, y1)]
    return "%.6f,%.6f,%.6f,%.6f" % (min(p[0] for p in ll), min(p[1] for p in ll), max(p[0] for p in ll),
                                    max(p[1] for p in ll))


def overpass(q, attempts=6):
    for attempt in range(attempts):
        url = URLS[attempt % len(URLS)]
        try:
            ua = {"User-Agent": "magliasinaNG BeamNG map pipeline (github.com/wintrymichi/magliasinaNG)"}
            if attempt % 2:                      # some instances answer GET only
                r = requests.get(url, params={"data": q}, timeout=900, headers=ua)
            else:
                r = requests.post(url, data={"data": q}, timeout=900, headers=ua)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print("retry", url, e, flush=True)
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("Overpass failed")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path, query in ((OUT, QUERY), (COMMUNES, QUERY_COMMUNES), (POIS, QUERY_POIS)):
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
            if not os.path.exists(path):
                continue
            with open(path, "rb") as src, gzip.open(pinned, "wb", compresslevel=9) as dst:
                shutil.copyfileobj(src, dst)
            print("kept in the repository:", pinned)


ADD_TILE = 1000.0         # m, side of the boxes --add asks for (larger ones timed out on busy Overpass servers)


def add():
    """v3.0.40: the elements over each whole village (area.villages()) missing from the pinned extracts, asked for in
    boxes of ADD_TILE m."""
    for path, query in ((OUT, QUERY), (POIS, QUERY_POIS)):
        pinned = PINNED[path]
        d = json.load(gzip.open(pinned, "rt", encoding="utf-8"))
        have = {(e["type"], e["id"]) for e in d["elements"]}
        for key, _, g in area.villages():
            x0, y0, x1, y1 = g.buffer(MARGIN).bounds
            nx, ny = int(np.ceil((x1 - x0) / ADD_TILE)), int(np.ceil((y1 - y0) / ADD_TILE))
            n = 0
            for i in range(nx):
                for j in range(ny):
                    box = (x0 + i * (x1 - x0) / nx, y0 + j * (y1 - y0) / ny,
                           x0 + (i + 1) * (x1 - x0) / nx, y0 + (j + 1) * (y1 - y0) / ny)
                    b = bbox(box)
                    new = [e for e in overpass(query.replace("{bbox}", b), 12)["elements"]
                           if (e["type"], e["id"]) not in have]
                    have |= {(e["type"], e["id"]) for e in new}
                    d["elements"] += new
                    d.setdefault("added_bbox", []).append(b)
                    n += len(new)
            print(os.path.basename(pinned), key, "+%d elements in %d boxes" % (n, nx * ny), flush=True)
        with gzip.open(pinned, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(d, f)


if __name__ == "__main__":
    if "--add" in sys.argv[1:]:
        add()
    else:
        main()
