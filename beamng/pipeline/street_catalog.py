"""Street-level photos with an open licence that cover the area (v3.0.40): the catalogue of Mapillary, Panoramax and
KartaView, read by street_fetch.py (download) and street_reference.py (analysis).

Every photo of the three services inside the playable area (area.py) + MARGIN m is listed with its position, date,
compass angle and whether it is a 360 degree panorama:
- Mapillary (images CC BY-SA 4.0): the z14 vector tiles of its coverage (layer "image"), then the details of every
  image (the position and angle computed by Mapillary's own reconstruction, camera, thumbnail sizes) from the graph
  API; needs a client token in MAPILLARY_TOKEN (free, mapillary.com/dashboard/developers), without it Mapillary is
  skipped;
- Panoramax (CC BY-SA 4.0 or etalab-2.0, as each picture says): the STAC search of the federated catalogue;
- KartaView (CC BY-SA 4.0): the nearby-photos call of its API.
No image is downloaded here. How much of the street network the photos see is measured against the places of the
Google coverage metadata (dati/sv_coverage.json.gz: where a car drove), which are only used as a list of points.

Output: WORK/street/catalog.json.gz (every photo), beamng/verifica/street/coverage.json (counts and coverage) and
coverage.png (map).
    python street_catalog.py [--no-details]
"""
import gzip, json, math, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
import shapely
from config import WORK, local_to_lv95, lv95_to_wgs, wgs_to_local
import area

MARGIN = 40.0                    # m around the playable area
OUT_DIR = os.path.join(WORK, "street")
CATALOG = os.path.join(OUT_DIR, "catalog.json.gz")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(REPO, "verifica", "street")
SV_COVERAGE = os.path.join(REPO, "dati", "sv_coverage.json.gz")
UA = {"User-Agent": "MagliasinaNG map pipeline (github.com/wintrymichi/magliasinaNG)"}

MLY_TILES = "https://tiles.mapillary.com/maps/vtp/mly1_public/2/{z}/{x}/{y}?access_token={t}"
MLY_GRAPH = "https://graph.mapillary.com/images"
MLY_FIELDS = ("id,camera_type,camera_parameters,is_pano,width,height,computed_geometry,geometry,"
              "computed_compass_angle,compass_angle,computed_altitude,altitude,computed_rotation")
DETAILS_BUDGET = 900          # s for the details of the images: the graph API answers slowly or not at all for hours;
                              # the images without them get them one by one when a step downloads them
PANORAMAX = ["https://api.panoramax.xyz/api", "https://panoramax.openstreetmap.fr/api", "https://panoramax.ign.fr/api"]
KARTAVIEW = "https://api.openstreetcam.org/1.0/list/nearby-photos/"


def session():
    s = requests.Session()
    s.headers.update(UA)
    return s


class Health:
    """Consecutive failures of one service: after LIMIT of them in a row the service is given up."""
    LIMIT = 6

    def __init__(self, name):
        self.name, self.fails, self.calls, self.errors = name, 0, 0, Counter()

    @property
    def dead(self):
        return self.fails >= self.LIMIT

    def note(self, ok, err=None):
        self.calls += 1
        self.fails = 0 if ok else self.fails + 1
        if not ok:
            self.errors[str(err)[:120]] += 1

    def report(self):
        return {"calls": self.calls, "given_up": self.dead, "errors": dict(self.errors.most_common(5))}


def get_json(s, url, params=None, data=None, tries=3, timeout=40, health=None, pause=2.0):
    """GET (or POST with data) returning JSON, retried with a growing pause; None after the last try."""
    err = None
    if health is not None and health.dead:
        return None
    for k in range(tries):
        try:
            r = s.post(url, data=data, timeout=timeout) if data is not None else s.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                out = r.json()
                if health is not None:
                    health.note(True)
                return out
            err = "HTTP %d %s" % (r.status_code, r.text[:200])
            if r.status_code in (400, 401, 403, 404):
                break
        except Exception as e:                          # network hiccup, throttling
            err = repr(e)
        time.sleep(pause * (k + 1))
    print("  failed", url, err, flush=True)
    if health is not None:
        health.note(False, err)
    return None


def area_wgs(margin=MARGIN):
    """The area + margin as a (lon, lat) polygon."""
    g = area.polygon().buffer(margin)
    return shapely.transform(g, lambda c: np.array([lv95_to_wgs(*local_to_lv95(x, y))[::-1] for x, y in c]))


def grid(bounds, step_deg):
    """(lon0, lat0, lon1, lat1) cells of about step_deg degrees covering bounds."""
    lon0, lat0, lon1, lat1 = bounds
    nx = max(1, int(math.ceil((lon1 - lon0) / step_deg)))
    ny = max(1, int(math.ceil((lat1 - lat0) / (step_deg * 0.7))))
    xs, ys = np.linspace(lon0, lon1, nx + 1), np.linspace(lat0, lat1, ny + 1)
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1]) for i in range(nx) for j in range(ny)]


# ------------------------------------------------------------------ Mapillary
def tile_of(lat, lon, z):
    n = 2 ** z
    return int((lon + 180.0) / 360.0 * n), int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)


def tile_lonlat(x, y, z, px, py, extent):
    """(lon, lat) of the point (px, py) of a vector tile (y down from the tile's top)."""
    n = 2 ** z
    fx, fy = x + px / extent, y + py / extent
    return fx / n * 360.0 - 180.0, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy / n))))


def mapillary(token, poly, details=True):
    import mapbox_vector_tile
    s = session()
    z = 14
    lon0, lat0, lon1, lat1 = poly.bounds
    xa, ya = tile_of(lat1, lon0, z)
    xb, yb = tile_of(lat0, lon1, z)
    found = {}
    for x in range(xa, xb + 1):
        for y in range(ya, yb + 1):
            for k in range(5):
                try:
                    r = s.get(MLY_TILES.format(z=z, x=x, y=y, t=token), timeout=60)
                    break
                except Exception:
                    time.sleep(2.0 * (k + 1))
            else:
                print("  mapillary tile failed", x, y, flush=True)
                continue
            if r.status_code != 200:
                print("  mapillary tile", x, y, "HTTP", r.status_code, r.text[:200], flush=True)
                continue
            tile = mapbox_vector_tile.decode(r.content, default_options={"y_coord_down": True})
            lay = tile.get("image")
            if not lay:
                continue
            ext = lay.get("extent", 4096)
            for f in lay["features"]:
                px, py = f["geometry"]["coordinates"]
                lon, lat = tile_lonlat(x, y, z, px, py, ext)
                p = f["properties"]
                found[str(p["id"])] = {"src": "mapillary", "id": str(p["id"]), "lon": lon, "lat": lat,
                                       "date": time.strftime("%Y-%m-%d", time.gmtime(p.get("captured_at", 0) / 1000.0)),
                                       "angle": p.get("compass_angle"), "pano": bool(p.get("is_pano")),
                                       "seq": p.get("sequence_id"), "creator": p.get("creator_id")}
    shapely.prepare(poly)
    items = [v for v in found.values() if shapely.contains_xy(poly, v["lon"], v["lat"])]
    print("mapillary: %d images in the tiles, %d in the area" % (len(found), len(items)), flush=True)
    if details and items:
        by_id = {v["id"]: v for v in items}

        def batch(chunk):
            """The details of a batch of images; a batch the graph API refuses is split in two and tried again
            (it refuses a whole batch for one image it cannot serve: deleted, private, still processing)."""
            r = get_json(s, MLY_GRAPH, params={"image_ids": ",".join(chunk), "fields": MLY_FIELDS,
                                               "access_token": token}, tries=2 if len(chunk) > 1 else 3, pause=3.0)
            if r is None and len(chunk) > 1:
                h = len(chunk) // 2
                a, b = batch(chunk[:h]), batch(chunk[h:])
                return {"data": (a or {}).get("data", []) + (b or {}).get("data", [])}
            return r
        ids = [v["id"] for v in items if "camera" not in v]
        chunks = [ids[i:i + 40] for i in range(0, len(ids), 40)]
        t0 = time.time()

        def timed(chunk):
            return batch(chunk) if time.time() - t0 < DETAILS_BUDGET else None
        with ThreadPoolExecutor(4) as ex:
            for k, res in enumerate(ex.map(timed, chunks)):
                for d in (res or {}).get("data", []):
                    v = by_id.get(str(d["id"]))
                    if v is not None:
                        apply_details(v, d)
                if k % 25 == 0:
                    print("  details: %d batches of %d, %.0f s" % (k + 1, len(chunks), time.time() - t0), flush=True)
        print("mapillary details: %d of %d" % (sum("camera" in v for v in items), len(items)), flush=True)
    return items


def apply_details(v, d):
    """The details of the graph API (d) on a catalogue entry (v)."""
    g = d.get("computed_geometry") or d.get("geometry")
    if g:
        v["lon"], v["lat"] = g["coordinates"][:2]
    v["angle"] = d.get("computed_compass_angle", d.get("compass_angle", v.get("angle")))
    v["alt"] = d.get("computed_altitude", d.get("altitude"))
    v["camera"] = d.get("camera_type") or "unknown"
    v["cam_params"] = d.get("camera_parameters")
    v["rotation"] = d.get("computed_rotation")
    v["pano"] = bool(d.get("is_pano")) or d.get("camera_type") in ("spherical", "equirectangular")
    v["size"] = [d.get("width"), d.get("height")]
    v["computed"] = bool(d.get("computed_geometry"))
    return v


# ------------------------------------------------------------------ Panoramax
def panoramax(poly, status):
    s = session()
    for base in PANORAMAX:
        items, ok = {}, True
        health = Health("panoramax " + base)
        for cell in grid(poly.bounds, 0.01):
            if not poly.intersects(shapely.box(*cell)):
                continue
            url, params = base + "/search", {"bbox": ",".join("%.6f" % v for v in cell), "limit": 1000}
            pages = 0
            while url and pages < 50:
                res = get_json(s, url, params=params, health=health)
                if res is None:
                    ok = False
                    break
                for f in res.get("features", []):
                    lon, lat = f["geometry"]["coordinates"][:2]
                    pr = f.get("properties", {})
                    fov = (pr.get("pers:interior_orientation") or {}).get("field_of_view")
                    a = f.get("assets", {})
                    items[f["id"]] = {"src": "panoramax", "id": f["id"], "lon": lon, "lat": lat,
                                      "date": (pr.get("datetime") or "")[:10], "angle": pr.get("view:azimuth"),
                                      "pano": fov == 360, "fov": fov, "collection": f.get("collection"),
                                      "license": pr.get("license"),
                                      "producer": pr.get("geovisio:producer") or (f.get("providers") or [{}])[0].get("name"),
                                      "hd": (a.get("hd") or {}).get("href"), "sd": (a.get("sd") or {}).get("href"),
                                      "camera": " ".join(str(pr.get(k) or "") for k in ("pers:interior_orientation",))[:200],
                                      "api": base}
                nxt = [l["href"] for l in res.get("links", []) if l.get("rel") == "next"]
                url, params = (nxt[0], None) if nxt else (None, None)
                pages += 1
            if not ok:
                break
        status["panoramax " + base] = health.report()
        if ok:
            shapely.prepare(poly)
            out = [v for v in items.values() if shapely.contains_xy(poly, v["lon"], v["lat"])]
            print("panoramax (%s): %d pictures in the area" % (base, len(out)), flush=True)
            return out
        print("panoramax: %s did not answer, next catalogue" % base, flush=True)
    return []


# ------------------------------------------------------------------ KartaView
def kartaview(poly, status):
    s = session()
    items = {}
    shapely.prepare(poly)
    health = Health("kartaview")

    def cell_query(cell, depth=0):
        lon0, lat0, lon1, lat1 = cell
        if not poly.intersects(shapely.box(*cell)):
            return
        lat, lon = 0.5 * (lat0 + lat1), 0.5 * (lon0 + lon1)
        r = 0.5 * math.hypot((lon1 - lon0) * 111320 * math.cos(math.radians(lat)), (lat1 - lat0) * 110540)
        res = get_json(s, KARTAVIEW, data={"coordinate": "%.6f,%.6f" % (lat, lon), "radius": int(r) + 1}, health=health)
        if res is None:
            return
        got = res.get("currentPageItems") or []
        for o in got:
            try:
                la, lo = float(o["lat"]), float(o["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            # "storage13/files/photo/..." -> https://storage13.openstreetcam.org/files/photo/...
            url = {k: re.sub(r"^(storage[0-9]+)/", r"https://\1.openstreetcam.org/", o.get(k) or "")
                   for k in ("name", "lth_name")}
            items[str(o.get("id"))] = {"src": "kartaview", "id": str(o.get("id")), "lon": lo, "lat": la,
                                       "date": time.strftime("%Y-%m-%d", time.gmtime(int(o.get("timestamp") or 0))),
                                       "angle": float(o["heading"]) if o.get("heading") not in (None, "") else None,
                                       "pano": False, "seq": o.get("sequence_id"), "seq_index": o.get("sequence_index"),
                                       "url": url["name"], "url_large": url["lth_name"]}
        # a full page: the cell holds more, split it
        if len(got) >= 900 and depth < 5:
            mx, my = 0.5 * (lon0 + lon1), 0.5 * (lat0 + lat1)
            for c in ((lon0, lat0, mx, my), (mx, lat0, lon1, my), (lon0, my, mx, lat1), (mx, my, lon1, lat1)):
                cell_query(c, depth + 1)

    cells = grid(poly.bounds, 0.01)
    for k, cell in enumerate(cells):
        if health.dead:
            print("kartaview: given up after %d failures in a row" % health.fails, flush=True)
            break
        cell_query(cell)
        if k % 20 == 0:
            print("  kartaview cell %d/%d: %d photos" % (k + 1, len(cells), len(items)), flush=True)
    status["kartaview"] = health.report()
    out = [v for v in items.values() if shapely.contains_xy(poly, v["lon"], v["lat"])]
    print("kartaview: %d photos in the area" % len(out), flush=True)
    return out


# ------------------------------------------------------------------ coverage
def coverage(items):
    """Counts, years and the share of the places of the Google coverage (where a car drove) with an open photo
    within 10 / 25 m (any photo, 360 degree panoramas)."""
    rep = {"sources": {}}
    for src in ("mapillary", "panoramax", "kartaview"):
        it = [v for v in items if v["src"] == src]
        rep["sources"][src] = {"photos": len(it), "panoramas_360": sum(bool(v.get("pano")) for v in it),
                               "years": dict(sorted(Counter((v.get("date") or "?")[:4] for v in it).items()))}
    if not os.path.exists(SV_COVERAGE):
        return rep
    from scipy.spatial import cKDTree
    G = json.load(gzip.open(SV_COVERAGE))["panoramas"]
    gxy = np.array([wgs_to_local(p["lat"], p["lon"]) for p in G])
    rep["places"] = len(gxy)

    def share(sel):
        if not sel:
            return {"10m": 0.0, "25m": 0.0}
        xy = np.array([wgs_to_local(v["lat"], v["lon"]) for v in sel])
        d, _ = cKDTree(xy).query(gxy)
        return {"10m": round(float((d <= 10).mean()), 4), "25m": round(float((d <= 25).mean()), 4)}
    rep["share_of_places"] = {"any": share(items), "360": share([v for v in items if v.get("pano")])}
    for src in ("mapillary", "panoramax", "kartaview"):
        sel = [v for v in items if v["src"] == src]
        rep["share_of_places"][src] = share(sel)
        rep["share_of_places"][src + "_360"] = share([v for v in sel if v.get("pano")])
    return rep


def plot(items, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    poly = area.polygon()
    fig, ax = plt.subplots(figsize=(16, 13), dpi=110)
    for g in shapely.get_parts(poly):
        ax.plot(*g.exterior.xy, color="black", lw=0.8)
    if os.path.exists(SV_COVERAGE):
        G = json.load(gzip.open(SV_COVERAGE))["panoramas"]
        gxy = np.array([wgs_to_local(p["lat"], p["lon"]) for p in G])
        ax.scatter(gxy[:, 0], gxy[:, 1], s=0.6, color="#cccccc", label="streets with a car-mounted camera (places)")
    colours = {"mapillary": "#05cb63", "panoramax": "#ff6f00", "kartaview": "#2f6fdf"}
    for src, c in colours.items():
        sel = [v for v in items if v["src"] == src]
        if not sel:
            continue
        xy = np.array([wgs_to_local(v["lat"], v["lon"]) for v in sel])
        pano = np.array([bool(v.get("pano")) for v in sel])
        ax.scatter(xy[~pano, 0], xy[~pano, 1], s=1.5, color=c, alpha=0.6, label="%s (%d)" % (src, (~pano).sum()))
        if pano.any():
            ax.scatter(xy[pano, 0], xy[pano, 1], s=3.0, color=c, marker="s", label="%s 360 (%d)" % (src, pano.sum()))
    ax.set_aspect("equal")
    ax.legend(loc="upper left", markerscale=6)
    ax.set_title("Open street-level photos in the map area")
    fig.tight_layout()
    fig.savefig(path)


def main(details=True):
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    poly = area_wgs()
    items, status = [], {}
    token = os.environ.get("MAPILLARY_TOKEN", "").strip()
    if token:
        try:
            items += mapillary(token, poly, details)
            status["mapillary"] = "ok"
        except Exception as e:                          # one service down must not lose the others
            status["mapillary"] = "failed: %r" % e
    else:
        print("mapillary: no MAPILLARY_TOKEN, skipped", flush=True)
        status["mapillary"] = "skipped: no token"
    for name, fn in (("panoramax", panoramax), ("kartaview", kartaview)):
        try:
            items += fn(poly, status)
        except Exception as e:
            status[name] = "failed: %r" % e
            print(name, "failed", repr(e), flush=True)
    for v in items:
        v["x"], v["y"] = [round(c, 2) for c in wgs_to_local(v["lat"], v["lon"])]
    with gzip.open(CATALOG, "wt", encoding="utf-8") as f:
        json.dump({"photos": items}, f, separators=(",", ":"))
    rep = coverage(items)
    rep["status"] = status
    json.dump(rep, open(os.path.join(REPORT_DIR, "coverage.json"), "w"), indent=1)
    plot(items, os.path.join(REPORT_DIR, "coverage.png"))
    print(json.dumps(rep, indent=1), flush=True)


if __name__ == "__main__":
    main(details="--no-details" not in sys.argv)
