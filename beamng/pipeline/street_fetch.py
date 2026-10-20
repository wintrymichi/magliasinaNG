"""Downloads the open street-level photos of the catalogue (street_catalog.py) into WORK/street/img/<service>/<id>.jpg
(v3.0.40), for the analysis of street_reference.py. Only photos with an open licence (Mapillary, Panoramax, KartaView:
CC BY-SA 4.0 or etalab-2.0); they stay in WORK and never enter the level or the repository.

A photo of Mapillary comes in its original size (or the largest thumbnail), one of Panoramax in its full size ("hd") or
its 2048 px copy ("sd"), one of KartaView in its processed full size. A photo already on disk is kept.
    python street_fetch.py [--size hd|sd] [--near-buildings] [--limit N] [ids...]
"""
import gzip, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
from config import WORK

CATALOG = os.path.join(WORK, "street", "catalog.json.gz")
IMG = os.path.join(WORK, "street", "img")
DET = os.path.join(WORK, "street", "det")
UA = {"User-Agent": "MagliasinaNG map pipeline (github.com/wintrymichi/magliasinaNG)"}
MLY_GRAPH = "https://graph.mapillary.com/"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def catalog():
    return json.load(gzip.open(CATALOG))["photos"]


def path_of(p):
    return os.path.join(IMG, p["src"], f"{p['id']}.jpg")


def url_of(p, size="hd", session=None):
    if p["src"] == "panoramax":
        return p.get(size) or p.get("hd") or p.get("sd")
    if p["src"] == "kartaview":
        return p.get("url") if size == "hd" else (p.get("url_large") or p.get("url"))
    if p["src"] == "mapillary":
        # the image's details come with its address when the catalogue has none (the graph API refused them)
        import street_catalog
        from config import wgs_to_local
        token = os.environ.get("MAPILLARY_TOKEN", "").strip()
        field = "thumb_original_url" if size == "hd" else "thumb_2048_url"
        fields = field + ",thumb_2048_url" + ("" if "camera" in p else "," + street_catalog.MLY_FIELDS)
        s = session or requests
        r = s.get(MLY_GRAPH + p["id"], params={"fields": fields, "access_token": token}, timeout=60)
        if r.status_code != 200:
            return None
        j = r.json()
        if "camera" not in p:
            street_catalog.apply_details(p, j)
            p["x"], p["y"] = [round(c, 2) for c in wgs_to_local(p["lat"], p["lon"])]
        return j.get(field) or j.get("thumb_2048_url")
    return None


def fetch(p, size="hd", session=None):
    """Downloads one photo; (id, 'ok' | 'skip' | 'failed ...')."""
    dst = path_of(p)
    if os.path.exists(dst):
        return p["id"], "skip"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    s = session or requests.Session()
    s.headers.update(UA)
    err = None
    for k in range(4):
        try:
            url = url_of(p, size, s)
            if not url:                                  # the graph API refused: once more after a pause
                err = "no url"
                time.sleep(4.0 * (k + 1))
                continue
            r = s.get(url, timeout=120)
            if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                with open(dst + ".part", "wb") as f:
                    f.write(r.content)
                os.replace(dst + ".part", dst)
                return p["id"], "ok"
            err = "HTTP %d" % r.status_code
        except Exception as e:
            err = repr(e)
        time.sleep(2.0 * (k + 1))
    return p["id"], "failed " + str(err)


def detections(p, session=None):
    """The segmentation Mapillary made of a photo with its own model (the classes of Mapillary Vistas, e.g.
    construction--structure--building, nature--sky, object--bench): [{"value", "polys": [[[x, y], ...], ...]}] with
    x, y in 0..1 of the image width and height, saved as WORK/street/det/<id>.json.gz (None: none, or not Mapillary)."""
    if p["src"] != "mapillary":
        return None
    dst = os.path.join(DET, f"{p['id']}.json.gz")
    if os.path.exists(dst):
        return json.load(gzip.open(dst))
    import base64
    import mapbox_vector_tile
    token = os.environ.get("MAPILLARY_TOKEN", "").strip()
    s = session or requests.Session()
    s.headers.update(UA)
    j = None
    for k in range(5):
        try:
            r = s.get(MLY_GRAPH + p["id"] + "/detections", params={"fields": "value,geometry", "access_token": token},
                      timeout=60)
            if r.status_code == 200:
                j = r.json()
                break
        except Exception:
            pass
        time.sleep(3.0 * (k + 1))
    if j is None:
        return None
    out = []
    for d in j.get("data", []):
        try:
            tile = mapbox_vector_tile.decode(base64.b64decode(d["geometry"]), default_options={"y_coord_down": True})
        except Exception:
            continue
        polys = []
        for lay in tile.values():
            ext = float(lay.get("extent", 4096))
            for f in lay.get("features", []):
                g = f["geometry"]
                parts = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]] if g["type"] == "Polygon" else []
                for poly in parts:
                    if poly and len(poly[0]) >= 3:
                        polys.append([[round(x / ext, 5), round(y / ext, 5)] for x, y in poly[0]])
        if polys:
            out.append({"value": d.get("value"), "polys": polys})
    os.makedirs(DET, exist_ok=True)
    with gzip.open(dst, "wt", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    return out


def near_buildings(photos, radius=35.0, least=3):
    """The photos with at least `least` buildings of the Federal Register within `radius` m (dati/gwr_area.json.gz):
    where facades can be seen."""
    from scipy.spatial import cKDTree
    g = json.load(gzip.open(os.path.join(REPO, "dati", "gwr_area.json.gz")))
    recs = g["buildings"] if isinstance(g, dict) else g
    xy = np.array([[r["x"], r["y"]] for r in recs if "x" in r], float)
    tree = cKDTree(xy)
    cnt = np.array([len(tree.query_ball_point([p["x"], p["y"]], radius)) for p in photos])
    return [p for p, c in zip(photos, cnt) if c >= least]


def main(args):
    size = "hd"
    if "--size" in args:
        size = args[args.index("--size") + 1]
    photos = catalog()
    ids = [a for a in args if not a.startswith("--") and a not in ("hd", "sd") and not a.isdigit()]
    if ids:
        photos = [p for p in photos if p["id"] in set(ids)]
    if "--near-buildings" in args:
        photos = near_buildings(photos)
    if "--limit" in args:
        n = int(args[args.index("--limit") + 1])
        # spread over the photos (every k-th in catalogue order: along the sequences)
        if len(photos) > n:
            photos = [photos[i] for i in np.linspace(0, len(photos) - 1, n).round().astype(int)]
    print(len(photos), "photos to fetch,", size, flush=True)
    stats = {}
    with ThreadPoolExecutor(6) as ex:
        for k, (pid, st) in enumerate(ex.map(lambda p: fetch(p, size), photos)):
            stats[st.split()[0]] = stats.get(st.split()[0], 0) + 1
            if st.startswith("failed"):
                print("  ", pid, st, flush=True)
            if k % 100 == 0:
                print("  %d/%d %s" % (k + 1, len(photos), stats), flush=True)
    print("done", stats, flush=True)
    return photos


if __name__ == "__main__":
    main(sys.argv[1:])
