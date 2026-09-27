"""Completa la copertura seguendo i link 'neighbors' tra panorami entro MAXD m dalla strada."""
import json, math
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from streetlevel import streetview
import sv_capture as s

MAXD = 15
line = s.route()
lat0 = line[0][0]
def xy(lat, lon): return np.array([(lon - line[0][1]) * 111320 * math.cos(math.radians(lat0)), (lat - lat0) * 110540])
P = np.array([xy(*p) for p in line])
cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
def proj(lat, lon):
    q = xy(lat, lon); a, b = P[:-1], P[1:]; ab = b - a
    t = np.clip(((q - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
    c = a + ab * t[:, None]; d = np.linalg.norm(q - c, axis=1); i = d.argmin()
    brg = (math.degrees(math.atan2(ab[i][0], ab[i][1])) + 360) % 360
    return d[i], cum[i] + t[i] * np.linalg.norm(ab[i]), brg

def main():
    panos = {d["id"]: d for d in json.load(open("panoramas.json"))}
    frontier = list(panos)
    done = set()
    while frontier:
        batch = [f for f in frontier if f not in done]; done.update(batch); frontier = []
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(lambda i: streetview.find_panorama_by_id(i), batch))
        for p in res:
            if not p: continue
            for n in p.neighbors or []:
                if n.id in panos: continue
                d, dist, brg = proj(n.lat, n.lon)
                if d <= MAXD:
                    panos[n.id] = dict(id=n.id, lat=n.lat, lon=n.lon, route_dist_m=round(dist, 1), road_bearing_deg=round(brg, 1), _new=True)
                    frontier.append(n.id)
        print("nuovi in coda:", len(frontier))

    # completa metadati dei nuovi
    new = [d for d in panos.values() if d.get("_new")]
    def fill(d):
        p = streetview.find_panorama_by_id(d["id"])
        d.update(elevation=p.elevation, date=str(p.date), heading_deg=math.degrees(p.heading),
                 pitch_deg=math.degrees(p.pitch or 0), roll_deg=math.degrees(p.roll or 0), source=p.source,
                 max_size=[p.image_sizes[-1].x, p.image_sizes[-1].y]); d.pop("_new")
    with ThreadPoolExecutor(6) as ex: list(ex.map(fill, new))
    out = sorted(panos.values(), key=lambda d: d["route_dist_m"])
    for i, d in enumerate(out): d["index"] = i
    json.dump(out, open("panoramas.json", "w"), indent=1)
    gaps = [(a["route_dist_m"], b["route_dist_m"]) for a, b in zip(out, out[1:]) if b["route_dist_m"] - a["route_dist_m"] > 20]
    from collections import Counter
    print(len(out), "panorami; aggiunti", len(new), "; date", Counter(d["date"] for d in out), "; buchi >20m:", gaps)


if __name__ == "__main__":
    main()
