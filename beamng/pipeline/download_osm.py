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
                                  villages of area.villages() (+ MARGIN) that they do not have yet, from the Geofabrik
                                  extract of Switzerland (needs osmium-tool and pyosmium); the rest stays as pinned
(c) OpenStreetMap contributors, ODbL 1.0: the extracts in dati/ are under the ODbL.
"""
import gzip, json, os, shutil, sys, time
import requests
from config import DATA, ZONE, local_to_lv95, lv95_to_wgs
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


def zone_main():
    """A Ticino zone (config.ZONE): the elements over the area + MARGIN from the Geofabrik extracts (Overpass is not
    fit for 60 zones in parallel), Switzerland and, where the zone reaches over the border, the north-west of Italy.
    The Swiss municipalities touching the box come from the Swiss extract (pbf_communes). The extracts in dati are
    replaced by the zone's: run zone builds only in a scratch checkout (the workflow), never in a working copy."""
    import download_swisstopo as ds
    b = bbox()
    box = tuple(float(v) for v in b.split(","))
    got = [[], []]
    seen = [set(), set()]
    for url in ZONE_PBFS:
        pbf = ds.fetch(url, os.path.join(DATA, "osm", os.path.basename(url)))[0]
        for k, els in enumerate(pbf_elements(pbf, box)):
            for e in els:
                if (e["type"], e["id"]) not in seen[k]:
                    seen[k].add((e["type"], e["id"]))
                    got[k].append(e)
    comm = pbf_communes(ds.fetch(PBF, os.path.join(DATA, "osm", os.path.basename(PBF)))[0], box)
    src = "Geofabrik " + ", ".join(map(os.path.basename, ZONE_PBFS)) + time.strftime(" %Y-%m-%d")
    for path, els in ((OUT, got[0]), (POIS, got[1]), (COMMUNES, comm)):
        d = {"elements": els, "bbox": b, "source": src}
        json.dump(d, open(path + ".part", "w"))
        os.replace(path + ".part", path)
        # many steps read the extracts in dati directly: in a zone build (a scratch checkout) they become the zone's
        os.remove(PINNED[path]) if os.path.exists(PINNED[path]) else None
        with gzip.open(PINNED[path], "wt", encoding="utf-8") as f:
            json.dump(d, f, separators=(",", ":"))
        print(os.path.basename(path), len(els), "OSM elements over", b, flush=True)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if ZONE:
        return zone_main()
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


PBF = "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf"
ZONE_PBFS = (PBF, "https://download.geofabrik.de/europe/italy/nord-ovest-latest.osm.pbf")
# the filters of QUERY and QUERY_POIS: key -> None (any value) or a regex of values
WAY_TAGS = {"highway": None, "railway": None, "barrier": None, "waterway": None,
            "man_made": "bridge|embankment|pier", "amenity": "parking|bench", "public_transport": None}
NODE_TAGS = {"highway": None, "railway": None, "traffic_sign": None, "public_transport": None, "barrier": None,
             "amenity": "bench|waste_basket|post_box|telephone|drinking_water|fountain|parking_entrance|recycling|"
                        "charging_station|fuel",
             "man_made": "street_cabinet|mast|flagpole|cross|water_tap",
             "historic": "wayside_shrine|wayside_cross|memorial", "leisure": "picnic_table",
             "tourism": "information|viewpoint"}
POI_TAGS = {"shop": None, "craft": None, "office": None,
            "amenity": QUERY_POIS.split('amenity"~"')[1].split('"')[0],
            "tourism": "hotel|guest_house|hostel|motel|apartment"}


def _match(tags, want):
    import re
    return any(k in tags and (v is None or re.search(v, tags[k])) for k, v in want.items())


def pbf_elements(pbf, box):
    """Elements of the Geofabrik extract inside the WGS84 box (s, w, n, e) that QUERY and QUERY_POIS would return,
    in the Overpass JSON form ("out body geom" ways, "out center tags" POIs); relations are left out."""
    import subprocess, tempfile
    import osmium
    s_, w_, n_, e_ = box
    cut = os.path.join(tempfile.mkdtemp(), "cut.osm.pbf")
    subprocess.run(["osmium", "extract", "-b", "%f,%f,%f,%f" % (w_, s_, e_, n_), "-s", "complete_ways",
                    "--overwrite", "-o", cut, pbf], check=True)
    inside = lambda la, lo: s_ <= la <= n_ and w_ <= lo <= e_
    area_el, pois = [], []
    for o in osmium.FileProcessor(cut).with_locations():
        tags = {t.k: t.v for t in o.tags}
        if not tags:
            continue
        if o.is_node():
            if not o.location.valid() or not inside(o.location.lat, o.location.lon):
                continue
            d = {"type": "node", "id": o.id, "lat": o.location.lat, "lon": o.location.lon, "tags": tags}
            if _match(tags, NODE_TAGS):
                area_el.append(d)
            if _match(tags, POI_TAGS):
                pois.append(d)
        elif o.is_way():
            geom = [{"lat": n.location.lat, "lon": n.location.lon} for n in o.nodes if n.location.valid()]
            if not geom or not any(inside(g["lat"], g["lon"]) for g in geom):
                continue
            if _match(tags, WAY_TAGS):
                area_el.append({"type": "way", "id": o.id, "nodes": [n.ref for n in o.nodes], "geometry": geom,
                                "tags": tags})
            if _match(tags, POI_TAGS):
                pois.append({"type": "way", "id": o.id, "tags": tags,
                             "center": {"lat": sum(g["lat"] for g in geom) / len(geom),
                                        "lon": sum(g["lon"] for g in geom) / len(geom)}})
    return area_el, pois


def pbf_communes(pbf, box):
    """The municipalities (admin_level 8 boundaries) of the extract that reach into the WGS84 box (s, w, n, e), in the
    Overpass "out body geom" form QUERY_COMMUNES returns (members with their geometry): signs_net.communes() reads
    them (the Swiss ones by their BFS number)."""
    import subprocess, tempfile
    import osmium
    s_, w_, n_, e_ = box
    adm = os.path.join(tempfile.mkdtemp(), "adm.osm.pbf")
    subprocess.run(["osmium", "tags-filter", pbf, "r/boundary=administrative", "--overwrite", "-o", adm], check=True)
    rels, ways = [], {}
    for o in osmium.FileProcessor(adm).with_locations():
        if o.is_way():
            ways[o.id] = [{"lat": n.location.lat, "lon": n.location.lon} for n in o.nodes if n.location.valid()]
        elif o.is_relation():
            tags = {t.k: t.v for t in o.tags}
            if tags.get("admin_level") == "8":
                rels.append((o.id, tags, [(m.type, m.ref, m.role) for m in o.members]))
    out = []
    for rid, tags, members in rels:
        mem = [{"type": "way", "ref": ref, "role": role, "geometry": ways.get(ref, [])}
               for t, ref, role in members if t == "w"]
        pts = [g for m in mem for g in m["geometry"]]
        if not pts:
            continue
        la = [g["lat"] for g in pts]
        lo = [g["lon"] for g in pts]
        if min(la) <= n_ and max(la) >= s_ and min(lo) <= e_ and max(lo) >= w_:
            out.append({"type": "relation", "id": rid, "members": mem, "tags": tags})
    print("municipalities over the zone:", len(out), flush=True)
    return out


def add():
    """v3.0.40: the elements over each whole village (area.villages() + MARGIN) missing from the pinned extracts, read
    from the Geofabrik extract of Switzerland (the Overpass servers answered 502/504 to every query, even 1 km
    boxes)."""
    import shapely
    import download_swisstopo as ds
    pbf = ds.fetch(PBF, os.path.join(DATA, "osm", "switzerland-latest.osm.pbf"))[0]
    pinned = [PINNED[OUT], PINNED[POIS]]
    ds_ = [json.load(gzip.open(f, "rt", encoding="utf-8")) for f in pinned]
    have = [{(e["type"], e["id"]) for e in d["elements"]} for d in ds_]
    for key, _, g in area.villages():
        x0, y0, x1, y1 = g.buffer(MARGIN).bounds
        b = bbox((x0, y0, x1, y1))
        box = tuple(float(v) for v in b.split(","))
        for d, h, new, what in zip(ds_, have, pbf_elements(pbf, box), ("area", "pois")):
            new = [e for e in new if (e["type"], e["id"]) not in h]
            h |= {(e["type"], e["id"]) for e in new}
            d["elements"] += new
            d.setdefault("added_bbox", []).append(b)
            print(key, what, "+%d elements over" % len(new), b, flush=True)
    for f, d in zip(pinned, ds_):
        d.setdefault("added_source", "Geofabrik switzerland-latest.osm.pbf, %s" % time.strftime("%Y-%m-%d"))
        with gzip.open(f, "wt", encoding="utf-8", compresslevel=9) as fh:
            json.dump(d, fh)


if __name__ == "__main__":
    if "--add" in sys.argv[1:]:
        add()
    else:
        main()
