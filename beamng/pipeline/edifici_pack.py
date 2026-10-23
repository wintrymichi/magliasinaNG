"""Reference pack of the buildings made closer to the real ones (v3.1, edifici_veri.py): for every site of
verifica/edifici/sites.json (the ~20 buildings most seen from the main roads) the open street photos that look at it
and the 10 cm orthophoto around it.

Run on GitHub Actions (the cloud session cannot reach Mapillary, Panoramax or swisstopo); it writes OUT/:
  <site>/<n>.jpg        the photos (Mapillary, Panoramax; CC BY-SA 4.0), a 360 degree panorama cropped toward the site
  <site>/orto.jpg       SWISSIMAGE 10 cm, 70 x 70 m around the site, north up (swisstopo, free use with attribution)
  credits.json          author, licence, source, camera position and heading of every photo
The photos are derivatives under CC BY-SA and the repository is CC BY-NC: the workflow commits OUT to a branch of
its own (edifici_pack.yml), never to a branch that is merged.

    python edifici_pack.py SITES OUT
"""
import io, json, math, os, sys, time
import numpy as np
import requests
from config import local_to_lv95, lv95_to_wgs

UA = {"User-Agent": "MagliasinaNG-buildings/1.0 (https://github.com/wintrymichi/magliasinaNG)"}
MLY = "https://graph.mapillary.com/"
PMX = ("https://api.panoramax.xyz/api", "https://panoramax.openstreetmap.fr/api", "https://panoramax.ign.fr/api")
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissimage-dop10/items"
PHOTO_MAX = 10
ORTHO_PAD = 15.0          # m around the site's box


def get(url, params=None, json_=True, tries=4):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=90)
            if r.status_code == 200:
                return r.json() if json_ else r.content
            print("  http", r.status_code, url[:120], flush=True)
            if r.status_code in (400, 404):
                return None
        except Exception as e:
            print("  error", repr(e)[:200], flush=True)
        time.sleep(2 * (k + 1))
    return None


def mly_url(pid, tok):
    j = get(MLY + pid, {"fields": "thumb_2048_url,creator,captured_at", "access_token": tok})
    if not j:
        return None, ""
    return j.get("thumb_2048_url"), (j.get("creator") or {}).get("username", "")


def mly_near(lat, lon, tok, radius=45):
    """Mapillary photos around a point the catalogue may lack (live query)."""
    dlat = radius / 111320.0
    dlon = radius / (111320.0 * math.cos(math.radians(lat)))
    j = get(MLY + "images", {"access_token": tok, "bbox": f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}",
                             "limit": 300, "fields": "id,computed_geometry,geometry,computed_compass_angle,is_pano,captured_at"})
    out = []
    for r in (j or {}).get("data", []):
        g = (r.get("computed_geometry") or r.get("geometry"))["coordinates"]
        ang = r.get("computed_compass_angle")
        if ang is None and not r.get("is_pano"):
            continue
        out.append({"src": "mapillary", "id": r["id"], "lon": g[0], "lat": g[1], "angle": ang or 0.0,
                    "pano": bool(r.get("is_pano")), "date": time.strftime("%Y-%m-%d", time.gmtime(r.get("captured_at", 0) / 1000))})
    return out


def pmx_url(pid):
    for base in PMX:
        for size in ("sd", "hd"):
            url = f"{base}/pictures/{pid}/{size}.jpg"
            try:
                r = requests.get(url, headers=UA, timeout=90, allow_redirects=True)
                if r.status_code == 200 and r.content[:2] == b"\xff\xd8":
                    return r.content
            except Exception:
                pass
    return None


def bearing(la1, lo1, la2, lo2):
    p = math.pi / 180
    y = math.sin((lo2 - lo1) * p) * math.cos(la2 * p)
    x = math.cos(la1 * p) * math.sin(la2 * p) - math.sin(la1 * p) * math.cos(la2 * p) * math.cos((lo2 - lo1) * p)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dist(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def pano_crop(img, yaw, fov=90):
    """The view of an equirectangular panorama toward yaw (degrees off its centre), fov wide, 4:3."""
    from PIL import Image
    w, h = img.size
    tiled = Image.new("RGB", (3 * w, h))
    for k in range(3):
        tiled.paste(img, (k * w, 0))
    cx = w + (0.5 + yaw / 360.0) * w
    hw = fov / 360.0 * w / 2
    top = max(0, int(h / 2 - hw * 0.75))
    return tiled.crop((int(cx - hw), top, int(cx + hw), min(h, top + int(hw * 1.5))))


def ortho(site, path):
    """SWISSIMAGE 10 cm around the site (windowed read of the cloud-optimised tiles), north up."""
    import rasterio
    from rasterio.windows import from_bounds
    from PIL import Image
    x0, y0, x1, y1 = site["bbox"]
    x0, y0, x1, y1 = x0 - ORTHO_PAD, y0 - ORTHO_PAD, x1 + ORTHO_PAD, y1 + ORTHO_PAD
    e0, n0 = local_to_lv95(x0, y0)
    e1, n1 = local_to_lv95(x1, y1)
    la0, lo0 = lv95_to_wgs(e0, n0)
    la1, lo1 = lv95_to_wgs(e1, n1)
    j = get(STAC, {"bbox": f"{min(lo0, lo1)},{min(la0, la1)},{max(lo0, lo1)},{max(la0, la1)}", "limit": 20})
    hrefs = {}
    for it in (j or {}).get("features", []):
        for a in it["assets"].values():
            if a["href"].endswith("_0.1_2056.tif"):
                key = a["href"].rsplit("/", 1)[1].split("_")[2]           # the tile, of the newest year
                hrefs[key] = max(hrefs.get(key, ""), a["href"])
    W, H = int(round((e1 - e0) / 0.1)), int(round((n1 - n0) / 0.1))
    out = np.zeros((H, W, 3), np.uint8)
    for href in hrefs.values():
        try:
            with rasterio.open("/vsicurl/" + href) as s:
                win = from_bounds(e0, n0, e1, n1, s.transform)
                a = s.read([1, 2, 3], window=win, boundless=True, fill_value=0, out_shape=(3, H, W))
                a = np.moveaxis(a, 0, -1)
                m = a.sum(-1) > 0
                out[m] = a[m]
        except Exception as e:
            print("  ortho", href[-40:], repr(e)[:160], flush=True)
    if out.any():
        Image.fromarray(out).save(path, quality=88)
        return True
    return False


def main(sites_path, out):
    from PIL import Image
    tok = os.environ.get("MAPILLARY_TOKEN", "").strip()
    sites = json.load(open(sites_path))["sites"]
    credits = []
    os.makedirs(out, exist_ok=True)
    for s in sites:
        d = os.path.join(out, s["id"])
        os.makedirs(d, exist_ok=True)
        ok = ortho(s, os.path.join(d, "orto.jpg"))
        photos = list(s["photos"])
        have = {p["id"] for p in photos}
        if len(photos) < 6 and tok:
            extra = []
            for p in mly_near(s["lat"], s["lon"], tok):
                if p["id"] in have:
                    continue
                dd = dist(p["lat"], p["lon"], s["lat"], s["lon"])
                brg = bearing(p["lat"], p["lon"], s["lat"], s["lon"])
                off = (brg - p["angle"] + 540) % 360 - 180
                if not 6 <= dd <= 50 or (not p["pano"] and abs(off) > 30):
                    continue
                p["yaw_to"] = round(brg, 1)
                extra.append((abs(dd - 20) / 10 + abs(off) / 30 - int(p["date"][:4]) / 5, p))
            extra.sort(key=lambda t: t[0])
            photos += [p for _, p in extra[:PHOTO_MAX - len(photos)]]
        n = 0
        for p in photos[:PHOTO_MAX]:
            author, data = "", None
            if p["src"] == "mapillary":
                if not tok:
                    continue
                url, author = mly_url(p["id"], tok)
                data = get(url, json_=False) if url else None
            elif p["src"] == "panoramax":
                data = pmx_url(p["id"])
            if not data:
                print("  no photo", p["src"], p["id"], flush=True)
                continue
            im = Image.open(io.BytesIO(data)).convert("RGB")
            yaw = None
            if p.get("pano"):
                yaw = (p["yaw_to"] - p.get("angle", 0) + 540) % 360 - 180
                im = pano_crop(im, yaw)
            im.thumbnail((2048, 2048))
            n += 1
            im.save(os.path.join(d, f"{n}.jpg"), quality=86)
            credits.append({"site": s["id"], "n": n, "src": p["src"], "id": p["id"], "author": author or p.get("producer", ""),
                            "license": "CC BY-SA 4.0", "date": p.get("date"), "lat": p.get("lat"), "lon": p.get("lon"),
                            "x": p.get("x"), "y": p.get("y"), "angle": p.get("angle"), "pano": p.get("pano"),
                            "yaw_to": p.get("yaw_to"), "size": list(im.size),
                            "page": f"https://www.mapillary.com/app/?pKey={p['id']}" if p["src"] == "mapillary" else
                            f"https://api.panoramax.xyz/#focus=pic&pic={p['id']}"})
        print(s["id"], s["comm"], s["road"], "ortho" if ok else "NO ortho", n, "photos", flush=True)
    json.dump({"photos": credits}, open(os.path.join(out, "credits.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
