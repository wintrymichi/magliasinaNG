"""Tiene solo l'immagine 2022-10 (coerente); usa panorami piu' vecchi solo dove il 2022 ha buchi."""
import json, csv
from expand import proj
allp = json.load(open("panoramas.json"))
for d in allp:
    _, d["route_dist_m"], d["road_bearing_deg"] = proj(d["lat"], d["lon"])
    d["route_dist_m"] = round(float(d["route_dist_m"]), 1); d["road_bearing_deg"] = round(d["road_bearing_deg"], 1)
new = sorted([d for d in allp if d["date"] == "2022-10"], key=lambda d: d["route_dist_m"])
gaps = [(a["route_dist_m"], b["route_dist_m"]) for a, b in zip(new, new[1:]) if b["route_dist_m"] - a["route_dist_m"] > 20]
gaps += [(-1, new[0]["route_dist_m"])] if new[0]["route_dist_m"] > 20 else []
print("buchi 2022:", gaps)
fill = [d for d in allp if d["date"] != "2022-10" and any(g0 < d["route_dist_m"] < g1 for g0, g1 in gaps)]
# per ogni buco tieni una sola data (la piu' recente disponibile)
out = sorted(new + fill, key=lambda d: d["route_dist_m"])
for i, d in enumerate(out): d["index"] = i
json.dump(allp, open("panoramas_all_dates.json", "w"), indent=1)
json.dump(out, open("panoramas.json", "w"), indent=1)
with open("panoramas.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["index","id","date","lat","lon","elevation","heading_deg","pitch_deg","roll_deg","route_dist_m","road_bearing_deg"], extrasaction="ignore")
    w.writeheader(); w.writerows(out)
json.dump({"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[d["lon"],d["lat"]]},"properties":{k:d[k] for k in ("index","id","date","route_dist_m")}} for d in out]}, open("panoramas.geojson","w"))
g = [(a["route_dist_m"], b["route_dist_m"]) for a, b in zip(out, out[1:]) if b["route_dist_m"] - a["route_dist_m"] > 20]
print(len(new), "del 2022 +", len(fill), "vecchi per i buchi =", len(out), "; buchi rimasti:", g)
