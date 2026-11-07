"""Which open sources answer for each canton (run on GitHub: the cloud session cannot reach them).

For every canton, a 400 m box round its capital:
  - the cadastral survey (geodienste.ch WFS av_0, the Italian model the pipeline reads, and the German and French ones
    when the Italian one is empty): features of LCSF / SOSF and the land cover kinds (Genere) found;
  - the Register of Buildings zip (public.madd.bfs.admin.ch/<canton>.zip);
  - swisstopo STAC items of swissALTI3D, swissSURFACE3D, swissBUILDINGS3D, SWISSIMAGE.
Writes app/data/sources_probe.json (the app warns about an area in a canton with no open survey) and prints a table.
"""
import json
import os
import sys
import time

import requests
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "app", "data", "sources_probe.json")
UA = {"User-Agent": "SwitzerlandBuilder-probe/1.0 (github.com/wintrymichi/magliasinaNG)"}
CAPITALS = {
    "zh": ("Zürich", 47.3769, 8.5417), "be": ("Bern", 46.9480, 7.4474), "lu": ("Luzern", 47.0502, 8.3093),
    "ur": ("Altdorf", 46.8804, 8.6444), "sz": ("Schwyz", 47.0207, 8.6530), "ow": ("Sarnen", 46.8960, 8.2461),
    "nw": ("Stans", 46.9580, 8.3660), "gl": ("Glarus", 47.0404, 9.0679), "zg": ("Zug", 47.1662, 8.5155),
    "fr": ("Fribourg", 46.8065, 7.1619), "so": ("Solothurn", 47.2088, 7.5323), "bs": ("Basel", 47.5596, 7.5886),
    "bl": ("Liestal", 47.4841, 7.7346), "sh": ("Schaffhausen", 47.6973, 8.6349), "ar": ("Herisau", 47.3861, 9.2792),
    "ai": ("Appenzell", 47.3310, 9.4090), "sg": ("St. Gallen", 47.4245, 9.3767), "gr": ("Chur", 46.8508, 9.5320),
    "ag": ("Aarau", 47.3925, 8.0444), "tg": ("Frauenfeld", 47.5536, 8.8987), "ti": ("Bellinzona", 46.1946, 9.0244),
    "vd": ("Lausanne", 46.5197, 6.6323), "vs": ("Sion", 46.2331, 7.3606), "ne": ("Neuchâtel", 46.9900, 6.9293),
    "ge": ("Genève", 46.2044, 6.1432), "ju": ("Delémont", 47.3649, 7.3445),
}
WFS = "https://geodienste.ch/db/av_0/{}"
GENRE = {"ita": "Genere", "deu": "Art", "fra": "Genre"}
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/{}/items"
COLLECTIONS = ["ch.swisstopo.swissalti3d", "ch.swisstopo.swisssurface3d-raster", "ch.swisstopo.swissbuildings3d_3_0",
               "ch.swisstopo.swissimage-dop10"]
to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=120, **kw)
            return r
        except requests.RequestException as e:
            err = e
            time.sleep(3 * (attempt + 1))
    raise err


def wfs(lang, layer, box):
    p = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=f"ms:{layer}",
             OUTPUTFORMAT="application/json; subtype=geojson", SRSNAME="EPSG:2056",
             BBOX=",".join(f"{v:.1f}" for v in box) + ",urn:ogc:def:crs:EPSG::2056", COUNT="2000")
    try:
        r = get(WFS.format(lang), params=p)
        if r.status_code != 200:
            return {"status": r.status_code, "n": 0, "text": r.text[:200]}
        f = r.json().get("features", [])
        kinds = sorted({str(x["properties"].get(GENRE[lang])) for x in f})
        return {"status": 200, "n": len(f), "kinds": kinds[:40]}
    except Exception as e:            # a canton's answer that is no JSON, a timeout
        return {"status": "error", "n": 0, "text": str(e)[:200]}


def main():
    res = {"probed": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "cantons": {}}
    for ct, (town, lat, lon) in CAPITALS.items():
        e, n = to_lv95.transform(lon, lat)
        box = (e - 200, n - 200, e + 200, n + 200)
        d = {"town": town}
        d["survey"] = {"ita": {"LCSF": wfs("ita", "LCSF", box), "SOSF": wfs("ita", "SOSF", box)}}
        if d["survey"]["ita"]["LCSF"]["n"] == 0:
            for lang in ("deu", "fra"):
                d["survey"][lang] = {"LCSF": wfs(lang, "LCSF", box)}
        r = get(f"https://public.madd.bfs.admin.ch/{ct}.zip", stream=True)
        d["gwr"] = {"status": r.status_code, "bytes": int(r.headers.get("Content-Length") or 0)}
        r.close()
        bb = f"{lon - 0.003:.5f},{lat - 0.003:.5f},{lon + 0.003:.5f},{lat + 0.003:.5f}"
        d["stac"] = {}
        for c in COLLECTIONS:
            r = get(STAC.format(c), params={"bbox": bb, "limit": 100})
            d["stac"][c.split(".")[-1]] = len(r.json().get("features", [])) if r.status_code == 200 else r.status_code
        ita = d["survey"]["ita"]["LCSF"]
        d["survey_open"] = ita["n"] > 0
        res["cantons"][ct] = d
        print(f"{ct} {town:13s} survey ita LCSF {ita['n']:5d} SOSF {d['survey']['ita']['SOSF']['n']:5d}"
              f" {'' if ita['n'] else json.dumps({k: v['LCSF'].get('n') for k, v in d['survey'].items()})}"
              f" gwr {d['gwr']['status']} {d['gwr']['bytes'] / 2 ** 20:.0f} MB stac {d['stac']}", flush=True)
        if ita["n"]:
            print("   kinds:", ", ".join(ita["kinds"][:20]), flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("written", OUT)


if __name__ == "__main__":
    sys.exit(main())
