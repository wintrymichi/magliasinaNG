"""Scarica i panorami Street View lungo la Strada Cantonale tra due punti
e genera viste prospettiche (per fotogrammetria / ricostruzione 3D).

Uso:  python sv_capture.py discover   -> trova i panorami lungo il percorso
      python sv_capture.py download   -> scarica panorami + viste prospettiche
"""
import json, math, sys, csv, os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import numpy as np
import requests
from PIL import Image
from scipy.ndimage import map_coordinates
from streetlevel import streetview

A = (45.981686, 8.878474)
B = (46.001760, 8.860159)
STEP_M = 6          # passo di campionamento lungo la strada
SEARCH_R = 12       # raggio ricerca panorama (m)
PANO_ZOOM = 4       # 4 -> 6656x3328 equirettangolare
VIEW_W, VIEW_H, VIEW_FOV = 1600, 1200, 90
VIEW_YAWS = {"fwd": 0, "fwd_r": 45, "right": 90, "back_r": 135,
             "back": 180, "back_l": 225, "left": 270, "fwd_l": 315}
VIEW_PITCHES = [0, 25]   # orizzonte + leggermente in alto (facciate/tetti)

ROOT = os.path.dirname(os.path.abspath(__file__))
R_EARTH = 6371000.0


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def route():
    url = (f"https://router.project-osrm.org/route/v1/driving/{A[1]},{A[0]};{B[1]},{B[0]}"
           "?overview=full&geometries=geojson")
    coords = requests.get(url, timeout=30).json()["routes"][0]["geometry"]["coordinates"]
    return [(c[1], c[0]) for c in coords]


def resample(line, step):
    out, carry = [], 0.0
    dist_total = 0.0
    for p, q in zip(line, line[1:]):
        seg = haversine(p, q)
        brg = bearing(p, q)
        d = carry
        while d < seg:
            t = d / seg
            out.append(((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t), dist_total + d, brg))
            d += step
        carry = d - seg
        dist_total += seg
    return out


def discover():
    samples = resample(route(), STEP_M)
    print(f"{len(samples)} punti di campionamento")

    def look(s):
        (lat, lon), dist, brg = s
        try:
            return s, streetview.find_panorama(lat, lon, radius=SEARCH_R)
        except Exception as e:
            print("errore", e)
            return s, None

    seen = {}
    with ThreadPoolExecutor(6) as ex:
        for (pt, dist, brg), p in ex.map(look, samples):
            if p is None:   # search_third_party=False -> solo panorami ufficiali Google
                continue
            if p.id not in seen:
                seen[p.id] = dict(id=p.id, lat=p.lat, lon=p.lon, elevation=p.elevation,
                                  date=str(p.date), heading_deg=math.degrees(p.heading),
                                  pitch_deg=math.degrees(p.pitch or 0), roll_deg=math.degrees(p.roll or 0),
                                  source=p.source, route_dist_m=round(dist, 1), road_bearing_deg=round(brg, 1),
                                  max_size=[p.image_sizes[-1].x, p.image_sizes[-1].y])
    panos = sorted(seen.values(), key=lambda d: d["route_dist_m"])
    for i, d in enumerate(panos):
        d["index"] = i
    json.dump(panos, open(os.path.join(ROOT, "panoramas.json"), "w"), indent=1)
    with open(os.path.join(ROOT, "panoramas.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in panos[0] if k != "max_size"], extrasaction="ignore")
        w.writeheader(); w.writerows(panos)
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]},
         "properties": {k: d[k] for k in ("index", "id", "date", "route_dist_m")}} for d in panos]}
    json.dump(gj, open(os.path.join(ROOT, "panoramas.geojson"), "w"))
    dates = {}
    for d in panos:
        dates[d["date"]] = dates.get(d["date"], 0) + 1
    print(f"{len(panos)} panorami unici; date: {dates}")


def equirect_to_persp(eq, yaw_deg, pitch_deg, fov_deg, w, h):
    """eq: array HxWx3 equirettangolare con yaw=0 al centro immagine."""
    H, W = eq.shape[:2]
    f = (w / 2) / math.tan(math.radians(fov_deg) / 2)
    xs, ys = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
    # direzioni in camera: x destra, y giu', z avanti
    d = np.stack([xs, ys, np.full_like(xs, f)], -1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    p, y = -math.radians(pitch_deg), math.radians(yaw_deg)
    # pitch (su = positivo) attorno a x, poi yaw attorno a y
    Rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]])
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    d = d @ (Ry @ Rx).T
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(-d[..., 1], -1, 1))
    u = (lon / (2 * math.pi) + 0.5) * W - 0.5
    v = (0.5 - lat / math.pi) * H - 0.5
    out = np.empty((h, w, 3), np.uint8)
    for c in range(3):
        out[..., c] = map_coordinates(eq[..., c], [v, u % W], order=1, mode="wrap")
    return out


def process(d):
    pdir = os.path.join(ROOT, "panorami")
    vdir = os.path.join(ROOT, "viste")
    name = f"{d['index']:04d}_{d['id']}"
    ppath = os.path.join(pdir, name + ".jpg")
    cams = []
    try:
        if os.path.exists(ppath):
            img = Image.open(ppath).convert("RGB")
        else:
            pano = streetview.find_panorama_by_id(d["id"])
            img = streetview.get_panorama(pano, zoom=PANO_ZOOM).convert("RGB")
            img.save(ppath, quality=92)
        eq = np.asarray(img)
        for pitch in VIEW_PITCHES:
            for vname, rel in VIEW_YAWS.items():
                world_yaw = (d["road_bearing_deg"] + rel) % 360           # bussola
                img_yaw = (world_yaw - d["heading_deg"] + 540) % 360 - 180  # rispetto al centro pano
                vpath = os.path.join(vdir, f"{name}_{vname}_p{pitch:02d}.jpg")
                if not os.path.exists(vpath):
                    Image.fromarray(equirect_to_persp(eq, img_yaw, pitch, VIEW_FOV, VIEW_W, VIEW_H)).save(vpath, quality=92)
                cams.append(dict(file=os.path.relpath(vpath, ROOT).replace("\\", "/"), pano_id=d["id"],
                                 lat=d["lat"], lon=d["lon"], elevation=d["elevation"],
                                 yaw_compass_deg=round(world_yaw, 2), pitch_deg=pitch,
                                 hfov_deg=VIEW_FOV, width=VIEW_W, height=VIEW_H))
        print("ok", name, flush=True)
    except Exception as e:
        print("ERRORE", name, e, flush=True)
    return cams


def download():
    os.makedirs(os.path.join(ROOT, "panorami"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "viste"), exist_ok=True)
    panos = json.load(open(os.path.join(ROOT, "panoramas.json")))
    cams = []
    with ProcessPoolExecutor(max(2, (os.cpu_count() or 4) - 2)) as ex:
        for c in ex.map(process, panos):
            cams += c
    json.dump(cams, open(os.path.join(ROOT, "cameras.json"), "w"), indent=1)
    print(f"fatto: {len(panos)} panorami, {len(cams)} viste")


if __name__ == "__main__":
    {"discover": discover, "download": download}[sys.argv[1]]()
