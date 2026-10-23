"""What the photos say about the asphalt of the roads (v3.1, "asfalto meno uniforme"): the raw measurements that
road_wear.py turns into older and newer stretches, joints, patches and drains. Run on GitHub Actions
(asphalt_survey.yml): swisstopo and Mapillary are blocked from the cloud sessions.

- ortho: the 10 cm SWISSIMAGE (ortho10.sample) along every AI road of the built level, straightened: a station
  every STEP m along its axis, COLS cells across it (CELL m apart, the axis in the middle), each the mean of
  SUB x SUB points of the photo; per cell the luminance (uint8) and blue minus red (int8, the shadows are bluish).
  Written to dati/asphalt_ortho.npz: names (the AI roads), start (their first station), xy (float32), L, BR,
  and the year of the photo of every 1 km tile (years: "EEEE-NNNN" -> year as text, in the JSON beside it).
- mapillary: the manholes and the gullies (catch basins) Mapillary found in its photos (map features
  object--manhole, object--catch-basin), local x, y: dati/asphalt_drains.json. Needs MAPILLARY_TOKEN.

Run: python asphalt_survey.py <level zip | folder> [ortho] [mapillary]
"""
import json, os, re, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from config import LEVEL_NAME, local_to_lv95, lv95_to_wgs, wgs_to_local

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
OUT = os.path.join(DATI, "asphalt_ortho.npz")
YEARS = os.path.join(DATI, "asphalt_ortho_years.json")
DRAINS = os.path.join(DATI, "asphalt_drains.json")
STEP = 1.0                  # m between stations
CELL = 0.5                  # m between cells across
COLS = 25                   # cells across: +-6 m about the axis
SUB = 3                     # points per cell each way (about the 10 cm pixels of the photo)
MIN_W = 2.6                 # m: narrower AI roads (paths, ramps) are left out
MLY = "https://graph.mapillary.com/map_features"
MLY_VALUES = ("object--manhole", "object--catch-basin")
MLY_TILE = 0.01             # degrees


def ai_roads(src):
    name = f"levels/{LEVEL_NAME}/main/MissionGroup/AIRoads/items.level.json"
    if zipfile.is_zipfile(src):
        text = zipfile.ZipFile(src).read(name).decode("utf-8")
    else:
        text = open(os.path.join(src, *name.split("/")), encoding="utf-8").read()
    out = []
    for line in text.splitlines():
        if line.strip():
            o = json.loads(line)
            if o.get("class") == "DecalRoad" and len(o.get("nodes", [])) >= 2:
                out.append(o)
    return out


def stations(nodes):
    """Axis points (n, 2) every STEP m and the unit normals to their left (n, 2)."""
    P = np.asarray(nodes, np.float64)[:, :2]
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    sd = np.arange(0.0, s[-1] + 1e-6, STEP)
    Q = np.column_stack([np.interp(sd, s, P[:, 0]), np.interp(sd, s, P[:, 1])])
    T = np.gradient(Q, axis=0) if len(Q) > 1 else np.array([[1.0, 0.0]])
    if len(T) >= 5:
        from scipy.ndimage import uniform_filter1d
        T = uniform_filter1d(T, 5, axis=0, mode="nearest")
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    return Q, np.column_stack([-T[:, 1], T[:, 0]]), np.column_stack([T[:, 0], T[:, 1]])


def strip(road):
    """L (n, COLS) uint8, BR (n, COLS) int8 and the stations (n, 2) of one AI road."""
    import ortho10
    Q, Nl, T = stations(road["nodes"])
    off = (np.arange(COLS) - (COLS - 1) / 2) * CELL
    sub = (np.arange(SUB) + 0.5) / SUB - 0.5
    a = sub * STEP                                   # along
    c = sub * CELL                                   # across
    da, dc = np.meshgrid(a, c, indexing="ij")
    da, dc = da.ravel(), dc.ravel()
    # (n, COLS, SUB*SUB) points
    X = Q[:, None, None, 0] + Nl[:, None, None, 0] * (off[None, :, None] + dc[None, None, :]) + T[:, None, None, 0] * da
    Y = Q[:, None, None, 1] + Nl[:, None, None, 1] * (off[None, :, None] + dc[None, None, :]) + T[:, None, None, 1] * da
    rgb = ortho10.sample(X.ravel(), Y.ravel()).reshape(len(Q), COLS, SUB * SUB, 3)
    m = np.nanmean(rgb, axis=2)
    L = np.nan_to_num(m.mean(2), nan=0.0)
    BR = np.nan_to_num(m[..., 2] - m[..., 0], nan=0.0)
    return Q.astype(np.float32), np.clip(np.round(L), 0, 255).astype(np.uint8), \
        np.clip(np.round(BR), -127, 127).astype(np.int8)


def ortho(src):
    import ortho10
    roads = [r for r in ai_roads(src) if float(np.median(np.asarray(r["nodes"])[:, 3])) >= MIN_W]
    print("asphalt survey: %d AI roads" % len(roads), flush=True)
    idx = ortho10.tile_index()
    t0 = time.time()
    res = [None] * len(roads)

    def one(i):
        for k in range(4):
            try:
                res[i] = strip(roads[i])
                return
            except Exception as e:                    # a read of the COG that failed: again
                print("retry", roads[i].get("name"), e, flush=True)
                time.sleep(5 * (k + 1))
        raise RuntimeError("ortho read failed: %s" % roads[i].get("name"))
    with ThreadPoolExecutor(8) as ex:
        for j, _ in enumerate(ex.map(one, range(len(roads)))):
            if j % 200 == 0:
                print("  %d / %d roads (%.0f s)" % (j, len(roads), time.time() - t0), flush=True)
    names = np.array([r.get("name", "") for r in roads])
    start = np.r_[0, np.cumsum([len(r[0]) for r in res])].astype(np.int64)
    np.savez_compressed(OUT, names=names, start=start, xy=np.concatenate([r[0] for r in res]),
                        L=np.concatenate([r[1] for r in res]), BR=np.concatenate([r[2] for r in res]),
                        step=STEP, cell=CELL)
    years = {t: (re.findall(r"_(\d{4})_", os.path.basename(u)) or [""])[0] for t, u in idx.items()}
    json.dump(years, open(YEARS, "w"), indent=0, sort_keys=True)
    print("asphalt survey: %d stations, %.1f MB, %.0f s" % (start[-1], os.path.getsize(OUT) / 1e6, time.time() - t0))


def mapillary(src):
    import requests
    token = os.environ.get("MAPILLARY_TOKEN", "").strip()
    if not token:
        sys.exit("MAPILLARY_TOKEN missing")
    P = np.concatenate([np.asarray(r["nodes"])[:, :2] for r in ai_roads(src)])
    x0, y0 = P.min(0) - 50
    x1, y1 = P.max(0) + 50
    ll = [lv95_to_wgs(*local_to_lv95(x, y)) for x in (x0, x1) for y in (y0, y1)]
    la0, la1 = min(p[0] for p in ll), max(p[0] for p in ll)
    lo0, lo1 = min(p[1] for p in ll), max(p[1] for p in ll)
    s = requests.Session()
    seen, out = set(), []

    def box(a, b, c, d, depth=0):
        params = {"access_token": token, "fields": "id,object_value,geometry,first_seen_at,last_seen_at",
                  "bbox": f"{a},{b},{c},{d}", "object_values": ",".join(MLY_VALUES), "limit": 2000}
        j = None
        for k in range(5):
            try:
                r = s.get(MLY, params=params, timeout=90)
                if r.status_code == 200:
                    j = r.json()
                    break
                print("mapillary", r.status_code, r.text[:200], flush=True)
            except Exception as e:
                print("mapillary retry", e, flush=True)
            time.sleep(4 * (k + 1))
        if j is None:
            raise RuntimeError("mapillary failed")
        data = j.get("data", [])
        if len(data) >= 1900 and depth < 4:          # the answer was cut: the four quarters
            mx, my = (a + c) / 2, (b + d) / 2
            for q in ((a, b, mx, my), (mx, b, c, my), (a, my, mx, d), (mx, my, c, d)):
                box(*q, depth + 1)
            return
        for f in data:
            if f["id"] in seen or f.get("object_value") not in MLY_VALUES:
                continue
            seen.add(f["id"])
            lon, lat = f["geometry"]["coordinates"]
            x, y = wgs_to_local(lat, lon)
            out.append({"id": f["id"], "v": f["object_value"].split("--")[1], "x": round(float(x), 2),
                        "y": round(float(y), 2), "first": f.get("first_seen_at"), "last": f.get("last_seen_at")})
    for a in np.arange(lo0, lo1, MLY_TILE):
        for b in np.arange(la0, la1, MLY_TILE):
            box(round(a, 6), round(b, 6), round(min(a + MLY_TILE, lo1), 6), round(min(b + MLY_TILE, la1), 6))
    out.sort(key=lambda o: (o["v"], o["x"], o["y"]))
    json.dump(out, open(DRAINS, "w"), indent=0)
    from collections import Counter
    print("mapillary drains:", dict(Counter(o["v"] for o in out)))


if __name__ == "__main__":
    src, what = sys.argv[1], set(sys.argv[2:]) or {"ortho", "mapillary"}
    if "mapillary" in what:
        mapillary(src)
    if "ortho" in what:
        ortho(src)
