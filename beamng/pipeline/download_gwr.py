"""Building attributes of the Federal Register of Buildings and Dwellings (GWR/REA), public data
of the Swiss Federal Statistical Office (BFS/UST), for the facades of the buildings (facades.py).

swissBUILDINGS3D gives every building its EGID; the register gives, per EGID: category and class
(dwelling, industry, church, farm building ...), year or period of construction, number of floors
above ground, number of dwellings, footprint area and name. The public extract of the canton of
Ticino (public.madd.bfs.admin.ch/ti.zip, updated daily) is read and the buildings of the area are
kept.

    python download_gwr.py          -> WORK/gwr.json (from the pinned extract when there is one)
    python download_gwr.py --pin    -> downloads the register again and rewrites the pinned extract
                                       beamng/dati/gwr_area.json.gz, so a release does not change with
                                       the register and does not depend on its server
Source: BFS/UST, Registro federale degli edifici e delle abitazioni (open data, the source must be
cited).
"""
import csv, gzip, io, json, os, sys, time, zipfile
import numpy as np
import requests
import shapely
from config import DATA, WORK, lv95_to_local
import area

URL = "https://public.madd.bfs.admin.ch/ti.zip"
PINNED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "gwr_area.json.gz")
OUT = os.path.join(WORK, "gwr.json")
MARGIN = 150.0
FIELDS = {"EGID": int, "GKAT": int, "GKLAS": int, "GBAUJ": int, "GBAUP": int, "GASTW": int, "GANZWHG": int,
          "GAREA": int, "GSTAT": int, "GBEZ": str, "GGDENAME": str}


def fetch():
    dst = os.path.join(DATA, "gwr", "ti.zip")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for attempt in range(5):
        try:
            with requests.get(URL, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dst + ".part", "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(dst + ".part", dst)
            return dst
        except Exception as e:
            print("retry", e, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("GWR download failed")


def read(zpath):
    keep = area.polygon().buffer(MARGIN)
    shapely.prepare(keep)
    out = []
    with zipfile.ZipFile(zpath) as z:
        name = [n for n in z.namelist() if n.lower().startswith("gebaeude") and n.endswith(".csv")][0]
        rows = csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8"), delimiter="\t")
        for r in rows:
            try:
                e, n = float(r["GKODE"]), float(r["GKODN"])
            except ValueError:
                continue
            x, y = lv95_to_local(e, n)
            if not keep.contains(shapely.Point(x, y)):
                continue
            d = {"x": round(x, 2), "y": round(y, 2)}
            for k, t in FIELDS.items():
                v = (r.get(k) or "").strip()
                if v:
                    d[k.lower()] = t(v) if t is int else v
            out.append(d)
    return out


def main(pin=False):
    if pin or not os.path.exists(PINNED):
        rows = read(fetch())
        with gzip.open(PINNED, "wt", encoding="utf-8") as f:
            json.dump({"source": "BFS/UST, Registro federale degli edifici e delle abitazioni (GWR), dati pubblici",
                       "date": time.strftime("%Y-%m-%d"), "buildings": rows}, f, separators=(",", ":"))
    d = json.load(gzip.open(PINNED, "rt", encoding="utf-8"))
    json.dump(d, open(OUT, "w"))
    b = d["buildings"]
    print("GWR buildings in the area:", len(b), "extract of", d.get("date"),
          "with floors:", sum(1 for r in b if "gastw" in r), "with year or period:",
          sum(1 for r in b if "gbauj" in r or "gbaup" in r))


if __name__ == "__main__":
    main(pin="--pin" in sys.argv)
