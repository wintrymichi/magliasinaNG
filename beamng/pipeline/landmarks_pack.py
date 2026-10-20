"""Development pack of the landmarks (v3.0.40): the churches, chapels and bell towers of the area and the cable car
of Monte Lema, with what the work on their models needs outside the build: their buildings of swissBUILDINGS3D, the
register records, the bare ground and the orthophoto around them, and reference photos with an open licence
(Wikimedia Commons, Mapillary) on one contact sheet per site.

Run on GitHub Actions (the cloud session that writes the pipeline cannot reach swisstopo, Commons or Mapillary)
after extract_buildings.py; it writes OUT/:
  sacred.json           every church, chapel and tower of the survey: uuid, kind, name, centre, height, area, register
  sites/<id>.pkl.gz     the buildings of a site (walls, roofs, floors), register records, survey parts, ground, ortho
  sheets/<id>.jpg       the reference photos of a site, with sheets/credits.json (author, licence, source of each)
  cableway.json         the lines of swissTLM3D TLM_UEBRIGE_BAHN in the area (cable cars, chair lifts) in local metres

    python landmarks_pack.py OUT
"""
import glob, gzip, io, json, math, os, pickle, sys, time
import numpy as np
import shapely
import requests
from config import DATA, WORK, local_to_lv95, lv95_to_local, lv95_to_wgs

SACRED = ("Sakrales Gebaeude", "Kapelle", "Sakraler Turm", "Turm")
SITE_JOIN = 45.0           # m: sacred buildings this close are one site (a church and its bell tower)
SITE_PAD = 40.0            # m of neighbours and ground around a site
PHOTO_MAX = 6              # reference photos a site
UA = {"User-Agent": "MagliasinaNG-landmarks/1.0 (https://github.com/wintrymichi/magliasinaNG)"}
# the stations of the Miglieglia - Monte Lema cable car (OSM aerialway=station), WGS84
STATIONS = {"lema_miglieglia": (46.023776, 8.856202), "lema_vetta": (46.040782, 8.834707)}


def footprint(b):
    fl = b.get("floors")
    if fl is not None and len(fl):
        g = shapely.union_all([q for q in (shapely.Polygon(t[:, :2]) for t in fl) if q.is_valid and q.area > 1e-6])
        if not g.is_empty:
            return g
    return shapely.MultiPoint(b["walls"].reshape(-1, 3)[:, :2]).convex_hull


def extract_near(points, radius):
    """The buildings of the survey's FileGDBs within radius m of local points (also outside the area)."""
    import extract_buildings as eb
    zone = shapely.union_all([shapely.Point(p).buffer(radius) for p in points])
    blds = {}
    for g in sorted(glob.glob(os.path.join(DATA, "buildings3d", "unz", "*.gdb"))):
        for lname, key in (("Wall", "walls"), ("Roof", "roofs"), ("Floor", "floors")):
            for props, tris in eb.features(g, lname):
                if len(tris) == 0:
                    continue
                x, y = lv95_to_local(tris[..., 0], tris[..., 1])
                if not zone.intersects(shapely.box(x.min(), y.min(), x.max(), y.max())):
                    continue
                tris = np.stack([x, y, tris[..., 2]], -1)
                b = blds.setdefault(props["UUID"], dict(uuid=props["UUID"], egid=props["EGID"], kind=props["OBJEKTART"],
                                                        name=props["NAME_KOMPLETT"], walls=[], roofs=[], floors=[]))
                b[key].append(tris)
    out = []
    for b in blds.values():
        for k in ("walls", "roofs", "floors"):
            b[k] = np.concatenate(b[k], 0) if b[k] else np.zeros((0, 3, 3))
        allp = np.concatenate([b["walls"], b["roofs"], b["floors"]], 0).reshape(-1, 3)
        b["bbox"] = [allp.min(0).tolist(), allp.max(0).tolist()]
        out.append(b)
    return out


def raster(pattern, x0, y0, x1, y1, res, dtype=np.float32):
    from geo import mosaic
    try:
        a = mosaic(pattern, x0, y0, x1, y1, res, dtype=dtype, nodata=np.nan if dtype == np.float32 else 0)
    except FileNotFoundError:
        return None
    return a


# ---------------------------------------------------------------------------------------------- photos
def get_json(url, params, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            if r.status_code == 200:
                return r.json()
            print("  http", r.status_code, url, flush=True)
        except Exception as e:
            print("  error", e, flush=True)
        time.sleep(2 * (k + 1))
    return None


def get_image(url):
    from PIL import Image
    for k in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=90)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:
            print("  image error", e, flush=True)
        time.sleep(2 * (k + 1))
    return None


def commons(lat, lon, radius=160):
    d = get_json("https://commons.wikimedia.org/w/api.php",
                 {"action": "query", "generator": "geosearch", "ggscoord": f"{lat}|{lon}", "ggsradius": radius,
                  "ggsnamespace": 6, "ggslimit": 30, "prop": "imageinfo|coordinates",
                  "iiprop": "url|extmetadata|size", "iiurlwidth": 900, "format": "json"})
    out = []
    for p in (d or {}).get("query", {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii.get("thumburl") or not p["title"].lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        md = ii.get("extmetadata", {})
        c = (p.get("coordinates") or [{}])[0]
        dist = haversine(lat, lon, c.get("lat", lat), c.get("lon", lon))
        out.append({"src": "commons", "title": p["title"], "url": ii["thumburl"], "dist": dist,
                    "author": strip_html(md.get("Artist", {}).get("value", "")),
                    "license": md.get("LicenseShortName", {}).get("value", ""),
                    "page": ii.get("descriptionurl", "")})
    out.sort(key=lambda r: r["dist"])
    return out


def mapillary(lat, lon, radius=140):
    tok = os.environ.get("MAPILLARY_TOKEN")
    if not tok:
        return []
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat)))
    d = get_json("https://graph.mapillary.com/images",
                 {"access_token": tok, "bbox": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}", "limit": 400,
                  "fields": "id,geometry,computed_compass_angle,compass_angle,captured_at,is_pano,thumb_2048_url,"
                            "thumb_1024_url,creator"})
    out = []
    for r in (d or {}).get("data", []):
        plon, plat = r["geometry"]["coordinates"]
        dist = haversine(lat, lon, plat, plon)
        if not 12 <= dist <= radius:
            continue
        brg = bearing(plat, plon, lat, lon)
        ang = r.get("computed_compass_angle", r.get("compass_angle"))
        if ang is None:
            continue
        off = (brg - ang + 540) % 360 - 180
        if not r.get("is_pano") and abs(off) > 28:
            continue
        out.append({"src": "mapillary", "id": r["id"], "dist": dist, "yaw": off, "dir": bearing(lat, lon, plat, plon), "pano": bool(r.get("is_pano")),
                    "url": r.get("thumb_2048_url") if r.get("is_pano") else r.get("thumb_1024_url"),
                    "date": time.strftime("%Y-%m-%d", time.gmtime(r.get("captured_at", 0) / 1000)),
                    "author": (r.get("creator") or {}).get("username", ""), "license": "CC BY-SA 4.0",
                    "page": f"https://www.mapillary.com/app/?pKey={r['id']}"})
    # nearer than 25 m sees only the foot of a tower; the most recent and a spread of directions
    out.sort(key=lambda r: (abs(r["dist"] - 60) / 40 + (0 if not r["pano"] else 0.3) - int(r["date"][:4]) / 20))
    picked, dirs = [], []
    for r in out:
        b = round(r["dir"] / 45) % 8
        if dirs.count(b) >= 1 and len(out) > 6:
            continue
        picked.append(r)
        dirs.append(b)
        if len(picked) >= 4:
            break
    return picked


def pano_crop(img, yaw, fov=80):
    """The view of an equirectangular panorama toward yaw (degrees off its centre), fov wide, 3:4 high."""
    from PIL import Image
    w, h = img.size
    tiled = Image.new("RGB", (3 * w, h))
    for k in range(3):
        tiled.paste(img, (k * w, 0))
    cx = w + (0.5 + yaw / 360.0) * w
    hw = fov / 360.0 * w / 2
    top = max(0, int(h / 2 - hw * 1.0))
    return tiled.crop((int(cx - hw), top, int(cx + hw), min(h, top + int(hw * 1.5))))


def haversine(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def bearing(la1, lo1, la2, lo2):
    p = math.pi / 180
    y = math.sin((lo2 - lo1) * p) * math.cos(la2 * p)
    x = math.cos(la1 * p) * math.sin(la2 * p) - math.sin(la1 * p) * math.cos(la2 * p) * math.cos((lo2 - lo1) * p)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def strip_html(s):
    import re
    return re.sub(r"<[^>]+>", "", s).strip()[:120]


def sheet(photos, title, path):
    """Up to PHOTO_MAX photos on one contact sheet, 3 columns, each 600 px wide, numbered."""
    from PIL import Image, ImageDraw
    imgs = []
    for p in photos:
        im = get_image(p["url"])
        if im is None:
            continue
        if p.get("pano"):
            im = pano_crop(im, p["yaw"])
        im.thumbnail((600, 600))
        imgs.append((im, p))
    if not imgs:
        return []
    cols = min(3, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    W, H = 600, 600
    out = Image.new("RGB", (cols * W, rows * H + 40), (30, 30, 30))
    dr = ImageDraw.Draw(out)
    dr.text((10, 10), title, fill=(255, 255, 255))
    for k, (im, p) in enumerate(imgs):
        x, y = (k % cols) * W, 40 + (k // cols) * H
        out.paste(im, (x + (W - im.size[0]) // 2, y + (H - im.size[1]) // 2))
        dr.rectangle((x, y, x + 210, y + 22), fill=(0, 0, 0))
        dr.text((x + 5, y + 5), f"{k + 1} {p['src']} {int(p['dist'])} m {p.get('date', '')}", fill=(255, 255, 0))
    out.save(path, quality=82)
    return [p for _, p in imgs]


# ---------------------------------------------------------------------------------------------- main
def main(out):
    import facades
    os.makedirs(os.path.join(out, "sites"), exist_ok=True)
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    # the cable car's stations, also outside the area (the top station at 1620 m)
    st_local = {k: lv95_to_local(*__import__("config").wgs_to_lv95(*v)) for k, v in STATIONS.items()}
    known = {b["uuid"] for b in blds}
    extra = [b for b in extract_near(list(st_local.values()), SITE_PAD + 40) if b["uuid"] not in known]
    print(len(extra), "buildings near the stations outside buildings.pkl", flush=True)
    blds += extra
    fps = [footprint(b) for b in blds]
    gwr = facades.gwr_join(blds, fps)
    parts = facades.mu_parts(blds, fps)
    by_egid = facades.gwr_by_egid()
    rows = []
    for i, b in enumerate(blds):
        if b["kind"] in SACRED or gwr.get(b["uuid"], {}).get("gklas") == 1272:
            fp = fps[i]
            c = fp.centroid
            rec = gwr.get(b["uuid"], {})
            rows.append({"i": i, "uuid": b["uuid"], "kind": b["kind"], "name": b.get("name"), "x": round(c.x, 1),
                         "y": round(c.y, 1), "z0": round(b["bbox"][0][2], 1), "h": round(b["bbox"][1][2] - b["bbox"][0][2], 1),
                         "area": round(fp.area, 1), "gklas": rec.get("gklas"), "gbauj": rec.get("gbauj"),
                         "gbaup": rec.get("gbaup"), "egid": rec.get("egid")})
    print(len(rows), "sacred buildings", flush=True)
    # sites: sacred buildings within SITE_JOIN m of each other, and the two stations
    pts = shapely.points([[r["x"], r["y"]] for r in rows])
    groups = list(shapely.union_all([p.buffer(SITE_JOIN / 2) for p in pts]).geoms) if rows else []
    sites = []
    for g in groups:
        members = [r for r, p in zip(rows, pts) if g.contains(p)]
        sites.append({"members": members, "geom": g})
    for k, (x, y) in st_local.items():
        sites.append({"id": k, "members": [], "geom": shapely.Point(x, y).buffer(25)})
    # by the boxes of the buildings: the roofs the survey keeps as objects of their own (no walls, no floor) too
    tree = shapely.STRtree([shapely.box(b["bbox"][0][0], b["bbox"][0][1], b["bbox"][1][0], b["bbox"][1][1]) for b in blds])
    nw = sum(1 for b in blds if not len(b["walls"]))
    nr = sum(1 for b in blds if not len(b["roofs"]))
    print(len(blds), "buildings,", nw, "without walls,", nr, "without roofs", flush=True)
    credits = {}
    index = []
    for s in sites:
        mem = s["members"]
        big = max(mem, key=lambda r: r["area"] * max(r["h"], 1)) if mem else None
        c = s["geom"].centroid
        sid = s.get("id") or f"{int(round(c.x)):+06d}_{int(round(c.y)):+06d}"
        x0, y0, x1, y1 = s["geom"].buffer(SITE_PAD).bounds
        near = tree.query(shapely.box(x0, y0, x1, y1))
        sb = [blds[j] for j in near]
        dtm = raster("swissalti3d_05/*.tif", x0, y0, x1, y1, 1.0)
        if dtm is None or np.isnan(dtm).mean() > 0.5:         # outside the area: the 2 m grid of the far terrain
            dtm = raster("swissalti3d_2/*.tif", x0, y0, x1, y1, 1.0)
        ortho = raster("swissimage_2/*.tif", x0, y0, x1, y1, 1.0)
        pack = {"id": sid, "bounds": (x0, y0, x1, y1), "members": [r["uuid"] for r in mem], "buildings": sb,
                "gwr": {b["uuid"]: gwr[b["uuid"]] for b in sb if b["uuid"] in gwr},
                "parts": {b["uuid"]: [(shapely.to_wkb(p), e) for p, e in parts[b["uuid"]]] for b in sb if b["uuid"] in parts},
                "by_egid": {e: by_egid[e] for b in sb for _, e in parts.get(b["uuid"], []) if e and e in by_egid},
                "dtm_res": 1.0, "dtm_z0": None if dtm is None else float(np.nanmin(dtm)),
                "dtm": None if dtm is None else np.round((np.nan_to_num(dtm[0], nan=np.nanmin(dtm)) - np.nanmin(dtm)) * 100).astype(np.uint16), "ortho": None if ortho is None else
                np.nan_to_num(ortho).clip(0, 255).astype(np.uint8)}
        with gzip.open(os.path.join(out, "sites", sid + ".pkl.gz"), "wb") as f:
            pickle.dump(pack, f)
        e, n = local_to_lv95(c.x, c.y)
        lat, lon = lv95_to_wgs(e, n)
        entry = {"id": sid, "x": round(c.x, 1), "y": round(c.y, 1), "lat": round(lat, 6), "lon": round(lon, 6),
                 "members": mem, "buildings": len(sb)}
        # reference photos of the larger sites (churches, towers, the stations), not of every wayside chapel
        if big is None or big["kind"] != "Kapelle" or big["area"] > 60 or big["h"] > 9:
            ph = commons(lat, lon)[:4] + mapillary(lat, lon)
            ph = ph[:PHOTO_MAX]
            title = f"{sid}  {big['kind'] + ' ' + str(big.get('name') or '') if big else sid}  ({lat:.5f}, {lon:.5f})"
            used = sheet(ph, title, os.path.join(out, "sheets", sid + ".jpg")) if ph else []
            credits[sid] = [{k: p.get(k) for k in ("src", "title", "id", "author", "license", "page", "date", "dist")}
                            for p in used]
            entry["photos"] = len(used)
            print(sid, len(mem), "members", len(sb), "buildings", len(used), "photos", flush=True)
        index.append(entry)
    json.dump({"sacred": rows, "sites": index}, open(os.path.join(out, "sacred.json"), "w"), indent=1)
    json.dump(credits, open(os.path.join(out, "sheets", "credits.json"), "w"), indent=1)
    # the cable cars of swissTLM3D
    f = os.path.join(DATA, "tlm", "TLM_UEBRIGE_BAHN.json")
    if os.path.exists(f):
        d = json.load(open(f))
        lines = []
        for ft in d["features"]:
            parts_l = []
            for p in ft["parts"]:
                P = np.array(p, float)
                x, y = lv95_to_local(P[:, 0], P[:, 1])
                parts_l.append(np.round(np.column_stack([x, y, P[:, 2]]), 2).tolist())
            lines.append({"props": ft["props"], "parts": parts_l})
        json.dump({"fields": d["fields"], "lines": lines}, open(os.path.join(out, "cableway.json"), "w"), indent=1)
        print(len(lines), "cable lines", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
