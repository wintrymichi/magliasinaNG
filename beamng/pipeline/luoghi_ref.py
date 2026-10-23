"""Reference pictures of recognisable places (v3.1, thread "Punti riconoscibili come dal vero"): for every point of
beamng/verifica/luoghi/punti.json (local x, y; cam: where the game view stands) a crop of the 10 cm SWISSIMAGE
(swisstopo, free geodata) SIDE m round it, and the open street-level photos (Mapillary, CC BY-SA) taken nearest the
camera and looking at the point. Runs on GitHub (luoghi_ref.yml): the cloud session reaches neither host.
Output: beamng/verifica/luoghi/ref/<name>_ortho.jpg, <name>_mly_<k>.jpg, ref.json (ids, authors, dates for credits).
The photos are only a check: they never go into the level or into main (see CLAUDE.md, Street photo reference).
"""
import json, math, os, sys
import numpy as np
import requests
import rasterio
from rasterio.windows import from_bounds
from PIL import Image
from config import local_to_lv95, lv95_to_wgs

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "verifica", "luoghi", "ref")
SIDE = 70.0             # m, the orthophoto crop
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissimage-dop10/items"
MLY = "https://graph.mapillary.com/images"
NEAR = 60.0             # m round the camera: photos looked for
PHOTOS = 3


def ortho(e, n, path):
    """The crop from every 1 km tile it touches, the newest flight of each (a point near a tile's edge came out
    half white when only one tile was read)."""
    h = SIDE / 2
    lat0, lon0 = lv95_to_wgs(e - h, n - h)
    lat1, lon1 = lv95_to_wgs(e + h, n + h)
    r = requests.get(STAC, params={"bbox": f"{lon0},{lat0},{lon1},{lat1}", "limit": 100}, timeout=60).json()
    tiles = {}
    for it in r.get("features", []):
        for a in it["assets"].values():
            if a["href"].endswith("_0.1_2056.tif"):
                tile = a["href"].split("/")[-1].split("_")[-3]          # swissimage-dop10_<year>_<e>-<n>_0.1_2056.tif
                d = it["properties"].get("datetime", "")
                if d >= tiles.get(tile, ("", ""))[0]:
                    tiles[tile] = (d, a["href"])
    if not tiles:
        return None
    out = None
    for _, url in tiles.values():
        with rasterio.open("/vsicurl/" + url) as s:
            a = s.read(window=from_bounds(e - h, n - h, e + h, n + h, s.transform), boundless=True, fill_value=0)[:3]
        if out is None:
            out = np.full_like(a, 255)
        m = a.max(0) > 0
        out[:, m] = a[:, m]
    Image.fromarray(np.moveaxis(out, 0, -1)).save(path, quality=88)
    return [u.split("/")[-1] for _, u in tiles.values()]


def photos(cam, pt, tok):
    e, n = local_to_lv95(*cam)
    lat, lon = lv95_to_wgs(e, n)
    dl = NEAR / 111000.0
    do = dl / math.cos(math.radians(lat))
    r = requests.get(MLY, params={"access_token": tok, "bbox": f"{lon - do},{lat - dl},{lon + do},{lat + dl}",
                                  "fields": "id,computed_geometry,geometry,compass_angle,computed_compass_angle,"
                                            "captured_at,is_pano,creator,thumb_2048_url", "limit": 200},
                     timeout=90).json()
    pe, pn = local_to_lv95(*pt)
    out = []
    from config import wgs_to_lv95
    for im in r.get("data", []):
        g = (im.get("computed_geometry") or im.get("geometry") or {}).get("coordinates")
        if not g:
            continue
        ie, iN = wgs_to_lv95(g[1], g[0])
        d = math.hypot(ie - pe, iN - pn)
        if d > NEAR or d < 4:
            continue
        brg = math.degrees(math.atan2(pe - ie, pn - iN)) % 360
        ang = im.get("computed_compass_angle", im.get("compass_angle"))
        off = 0.0 if im.get("is_pano") else abs((brg - (ang or 0) + 180) % 360 - 180)
        if off > 35:
            continue
        out.append((d / 10 + off / 10 - (im.get("captured_at", 0) / 3.15e10 - 50) / 2, d, off, brg, im))
    out.sort(key=lambda t: t[0])
    return out[:PHOTOS]


def main():
    tok = os.environ.get("MAPILLARY_TOKEN", "")
    os.makedirs(OUT, exist_ok=True)
    pts = json.load(open(os.path.join(HERE, "..", "verifica", "luoghi", "punti.json")))
    ref = {}
    for p in pts:
        e, n = local_to_lv95(p["x"], p["y"])
        rec = {"ortho": None, "photos": []}
        try:
            rec["ortho"] = ortho(e, n, os.path.join(OUT, f"{p['name']}_ortho.jpg"))
        except Exception as ex:
            print("ortho", p["name"], ex)
        if tok:
            try:
                for k, (_, d, off, brg, im) in enumerate(photos(p["cam"], (p["x"], p["y"]), tok)):
                    img = requests.get(im["thumb_2048_url"], timeout=90).content
                    open(os.path.join(OUT, f"{p['name']}_mly_{k}.jpg"), "wb").write(img)
                    rec["photos"].append({"id": im["id"], "dist_m": round(d, 1), "bearing": round(brg),
                                          "pano": bool(im.get("is_pano")), "captured_at": im.get("captured_at"),
                                          "creator": (im.get("creator") or {}).get("username"),
                                          "compass": im.get("computed_compass_angle", im.get("compass_angle"))})
            except Exception as ex:
                print("mapillary", p["name"], ex)
        ref[p["name"]] = rec
        print(p["name"], rec["ortho"], len(rec["photos"]), flush=True)
    json.dump(ref, open(os.path.join(OUT, "ref.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
