"""The results of the zones of the street reference (v3.0.40) gathered into the files the build reads:

- dati/street_facades.json: {building uuid: {"facades": [record of street_zone.record ...]}} (facades.py lays out the
  openings the photos show where they see the wall); a facade two zones measured keeps the record that sees more;
- dati/street_roofs.json: {building uuid: {"dz", "n", "iqr"}} the roof line of the photos over the game's (street_roofs),
  where enough columns of two photos or more agree (n, iqr, photos, spread) on a difference of ROOF_MIN m or more;
- dati/street_objects.json: [{cls, x, y, n, width}] the street furniture several photos show (street_objects);
- dati/street_hedges.json: {"cells": [[x, y, h, theta, vegetation, other], ...]} the cells of the low strips the photos
  saw (street_hedges; understory.py plants a hedge where vegetation wins), the votes of two zones on a cell added;
- dati/street_fountains.json: {OSM id: {seen, found, width, height, dx, dy}} (street_fountains; props_osm.py), a
  point two zones saw keeps the one with more photos.

    python street_collect.py <zone result folder> [...]
"""
import json, os, sys

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
ROOF_N = 12                   # columns of photos at least
ROOF_IQR = 0.8                # m: their spread at most
ROOF_MIN = 0.5                # m: a smaller difference is left as it is
ROOF_PHOTOS = 2               # photos that measured a roof at least, their medians at most ROOF_IQR m apart
MIN_COVER = 0.15              # share of a facade the photos see at least


def collect(folders, dati=DATI):
    facades, cover, roofs, objects, hedges, fountains = {}, {}, {}, [], {}, {}
    for d in folders:
        f = os.path.join(d, "facades.json")
        if os.path.exists(f):
            for key, v in json.load(open(f)).items():
                rec = v.get("record")
                if not rec or v.get("coverage", 0) < MIN_COVER:
                    continue
                uid = key.split("|")[0]
                facade = key.split("|", 1)[1]
                if v["coverage"] > cover.get((uid, facade), -1):
                    cover[(uid, facade)] = v["coverage"]
                    facades.setdefault(uid, {})[facade] = rec
        f = os.path.join(d, "roofs.json")
        if os.path.exists(f):
            for uid, r in json.load(open(f)).items():
                if r["n"] >= ROOF_N and r["iqr"] <= ROOF_IQR and r.get("photos", 0) >= ROOF_PHOTOS and \
                        r.get("spread", 0.0) <= ROOF_IQR and r["n"] > roofs.get(uid, {}).get("n", 0):
                    roofs[uid] = r
        f = os.path.join(d, "objects.json")
        if os.path.exists(f):
            for o in json.load(open(f))["objects"]:
                # one object two zones saw: the one more photos show
                same = [q for q in objects if q["cls"] == o["cls"] and (q["x"] - o["x"]) ** 2 + (q["y"] - o["y"]) ** 2 < 1.0]
                if same:
                    if o["n"] > same[0]["n"]:
                        objects[objects.index(same[0])] = o
                    continue
                objects.append({k: o[k] for k in ("cls", "x", "y", "n", "width")})
        f = os.path.join(d, "hedges.json")
        if os.path.exists(f):
            for x, y, h, th, veg, oth in json.load(open(f))["cells"]:
                k = (round(x, 2), round(y, 2))
                if k in hedges:
                    hedges[k][4] += veg
                    hedges[k][5] += oth
                else:
                    hedges[k] = [x, y, h, th, veg, oth]
        f = os.path.join(d, "fountains.json")
        if os.path.exists(f):
            for pid, r in json.load(open(f)).get("fountains", {}).items():
                if r["seen"] > fountains.get(pid, {}).get("seen", 0):
                    fountains[pid] = r
    json.dump({"cells": [hedges[k] for k in sorted(hedges)]}, open(os.path.join(dati, "street_hedges.json"), "w"),
              separators=(",", ":"))
    json.dump(dict(sorted(fountains.items())), open(os.path.join(dati, "street_fountains.json"), "w"), indent=0)
    out = {uid: {"facades": list(fs.values())} for uid, fs in sorted(facades.items())}
    json.dump(out, open(os.path.join(dati, "street_facades.json"), "w"), separators=(",", ":"))
    roofs = {uid: r for uid, r in roofs.items() if abs(r["dz"]) >= ROOF_MIN}
    json.dump(dict(sorted(roofs.items())), open(os.path.join(dati, "street_roofs.json"), "w"), indent=0)
    json.dump(sorted(objects, key=lambda o: (o["cls"], o["x"], o["y"])), open(os.path.join(dati, "street_objects.json"), "w"),
              indent=0)
    print("facades of", len(out), "buildings,", sum(len(v["facades"]) for v in out.values()), "facades;", len(roofs),
          "roofs;", len(objects), "objects;", len(hedges), "hedge cells;", len(fountains), "fountains", flush=True)
    return out, roofs, objects


if __name__ == "__main__":
    collect(sys.argv[1:])
