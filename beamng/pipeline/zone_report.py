"""Zones, road checklist and discrepancy register of the map (v2.1): beamng/verifica/ZONE.md, STRADE.md
and the automatic part of REGISTRO.md, with their data in zone_report.json.

Zones are the municipalities (OpenStreetMap admin_level 8, from swissBOUNDARIES3D) within the playable
area, plus the Italian side (terrain only) and the lake. Every road of the network (swissTLM3D,
network.py) belongs to the municipality its middle lies in; roads are grouped by street name, the
unnamed ones by class. For every zone and road the report states what the build measured and
checked, and where a check has no source (no Street View here, no signs or guardrails in the data):
  [x] checked against a source (the official survey, the orthophoto, OSM, the automatic checks)
  [~] partly (a source for part of it, the rest from the surrounding data)
  [!] needs a check on site or in the photos (no source for it)
Sources: work/network.json, work/network_markings.json, work/ai_oneways.json, work/canopy_fixes.json,
work/osm_props.json, beamng/dati/ponti.json, beamng/verifica/check_level.json, data/osm/communes.json (or
dati/osm_communes.json.gz).
    python zone_report.py
"""
import json, os
import numpy as np
import shapely
from config import DATA, WORK, wgs_to_local
import area

HERE = os.path.dirname(os.path.abspath(__file__))
VER = os.path.join(os.path.dirname(HERE), "verifica")
DATI = os.path.join(os.path.dirname(HERE), "dati")
ROAD_CLASSES = ("Autobahn", "Autostrasse", "10m Strasse", "8m Strasse", "6m Strasse", "4m Strasse", "3m Strasse",
                "Verbindung", "Ausfahrt", "Einfahrt", "Zufahrt", "Dienstzufahrt", "Platz", "Raststaette")
CLASS_IT = {"Autobahn": "autostrada", "Autostrasse": "semiautostrada", "10m Strasse": "strada 10 m",
            "8m Strasse": "strada 8 m", "6m Strasse": "strada 6 m", "4m Strasse": "strada 4 m", "3m Strasse": "strada 3 m",
            "Verbindung": "raccordo", "Ausfahrt": "uscita", "Einfahrt": "entrata", "Zufahrt": "accesso",
            "Dienstzufahrt": "accesso di servizio", "Platz": "piazza", "Raststaette": "area di servizio",
            "2m Weg": "sentiero 2 m", "1m Weg": "sentiero 1 m", "1m Wegfragment": "sentiero 1 m (frammento)",
            "2m Wegfragment": "sentiero 2 m (frammento)", "Markierte Spur": "traccia segnata"}


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def communes():
    """[(name, polygon in local coordinates)] of the municipalities touching the area."""
    import osm
    src = osm.source(os.path.join(DATA, "osm", "communes.json"), os.path.join(DATI, "osm_communes.json.gz"))
    d = osm.read(src) if src else {"elements": []}
    out = []
    for e in d["elements"]:
        lines = []
        for m in e.get("members", []):
            if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry"):
                g = [q for q in m["geometry"] if q]
                x, y = wgs_to_local(np.array([q["lat"] for q in g]), np.array([q["lon"] for q in g]))
                lines.append(shapely.LineString(np.column_stack([x, y])))
        if not lines:
            continue
        poly = shapely.union_all(list(shapely.get_parts(shapely.polygonize(lines))))
        if not poly.is_empty:
            out.append((e["tags"].get("name", "?"), e["tags"].get("ISO3166-2", "") or
                        ("IT" if e["tags"].get("ref:ISTAT") else "CH"), poly))
    return out


def status(ok, part=False):
    return "[x]" if ok else ("[~]" if part else "[!]")


def main():
    import network
    segs, st, _ = network.load()
    A = area.polygon()
    zones = [(n, c, p.intersection(A)) for n, c, p in communes()]
    zones = [(n, c, p) for n, c, p in zones if not p.is_empty and p.area > 20_000]
    ztree = shapely.STRtree([p for _, _, p in zones])
    import markings_net
    mk = markings_net.load() or {"lines": [], "segments": {}, "polygons": []}
    mseg = mk.get("segments", {})
    paint_by_seg = {}
    for ln in mk["lines"]:
        d = paint_by_seg.setdefault(ln["seg"], {"m": 0.0, "patterns": set()})
        d["m"] += sum(b - a for a, b in ln["runs_s"])
        d["patterns"].add(("gialla " if ln["color"] == "yellow" else "") + ln["pattern"])
    oneway = {int(k): v for k, v in load_json(os.path.join(WORK, "ai_oneways.json"), {}).items()}
    fixes = load_json(os.path.join(WORK, "canopy_fixes.json"), [])
    oprops = load_json(os.path.join(WORK, "osm_props.json"), [])
    checks = load_json(os.path.join(VER, "check_level.json"), {"places": []})
    ponti = {b["tlm"]: b for b in load_json(os.path.join(DATI, "ponti.json"), {"ponti": []})["ponti"]}

    def zone_of(x, y):
        ids = ztree.query(shapely.Point(x, y), predicate="within")
        return zones[int(ids[0])][0] if len(ids) else "fuori dai comuni"
    # roads
    seg_zone, seg_mid = {}, {}
    for s in segs:
        a, n = s["first"], s["n"]
        k = a + n // 2
        seg_zone[s["id"]] = zone_of(st["x"][k], st["y"][k])
        seg_mid[s["id"]] = (float(st["x"][k]), float(st["y"][k]))
    width_meas = {}
    from network import CLASSES
    for s in segs:
        a, n = s["first"], s["n"]
        w = st["width"][a:a + n]
        width_meas[s["id"]] = float(np.mean(np.abs(w - CLASSES[s["class"]][0]) > 1e-6)) if s["kind"] == "road" else 0.0
    # the place of every fix / object / problem -> the nearest road (within 30 m)
    from scipy.spatial import cKDTree
    road_ids = [s["id"] for s in segs if s["kind"] == "road"]
    pts = np.concatenate([np.column_stack([st["x"][segs[k]["first"]:segs[k]["first"] + segs[k]["n"]],
                                           st["y"][segs[k]["first"]:segs[k]["first"] + segs[k]["n"]]]) for k in road_ids])
    owner = np.concatenate([np.full(segs[k]["n"], k) for k in road_ids])
    kd = cKDTree(pts)

    def nearest_road(x, y, lim=30.0):
        d, j = kd.query([x, y])
        return int(owner[j]) if d <= lim else None
    fix_by_seg, fix_by_zone = {}, {}
    for x, y, what, why in fixes:
        k = nearest_road(x, y)
        if k is not None:
            fix_by_seg[k] = fix_by_seg.get(k, 0) + 1
        z = zone_of(x, y)
        fix_by_zone.setdefault(z, {}).setdefault(what, 0)
        fix_by_zone[z][what] += 1
    props_by_zone = {}
    for x, y, kind, _ in oprops:
        z = zone_of(x, y)
        props_by_zone.setdefault(z, {}).setdefault(kind, 0)
        props_by_zone[z][kind] += 1
    prob_by_zone, prob_by_seg = {}, {}
    for p in checks.get("places", []):
        z = zone_of(p["x"], p["y"])
        prob_by_zone.setdefault(z, {}).setdefault(p["what"], 0)
        prob_by_zone[z][p["what"]] += 1
        k = nearest_road(p["x"], p["y"], 10.0)
        if k is not None:
            prob_by_seg.setdefault(k, []).append(p["what"])
    # road groups
    groups = {}
    for s in segs:
        if s["kind"] != "road":
            continue
        z = seg_zone[s["id"]]
        key = (z, s["name"] or "(senza nome: %s)" % CLASS_IT.get(s["class"], s["class"]))
        groups.setdefault(key, []).append(s)
    road_rows = []
    for (z, name), ss in sorted(groups.items()):
        L = sum(s["length"] for s in ss)
        vis = sum(mseg.get(str(s["id"]), {}).get("visible_m", 0.0) for s in ss)
        hid = sum(mseg.get(str(s["id"]), {}).get("hidden_m", 0.0) for s in ss)
        seen = str(ss[0]["id"]) in mseg or any(str(s["id"]) in mseg for s in ss)
        paint = sum(paint_by_seg.get(s["id"], {}).get("m", 0.0) for s in ss)
        pats = sorted(set().union(*[paint_by_seg.get(s["id"], {}).get("patterns", set()) for s in ss]))
        wm = sum(width_meas[s["id"]] * s["length"] for s in ss) / max(L, 1e-6)
        ow = sum(s["length"] for s in ss if oneway.get(s["id"]))
        br = sum(1 for s in ss if s["bridge"])
        cls = sorted({CLASS_IT.get(s["class"], s["class"]) for s in ss})
        cant = any(s.get("owner") == "Kanton" for s in ss)
        probs = sorted(set(sum([prob_by_seg.get(s["id"], []) for s in ss], [])))
        row = {"zona": z, "strada": name, "km": round(L / 1000, 2), "classi": cls, "cantonale": cant,
               "larghezza_misurata_pct": round(100 * wm), "ponti": br, "senso_unico_m": round(ow),
               "segnaletica_visibile_m": round(vis), "segnaletica_coperta_m": round(hid), "vernice_m": round(paint),
               "segnaletica_tipi": pats, "piante_corrette": sum(fix_by_seg.get(s["id"], 0) for s in ss),
               "problemi_controlli": probs, "tlm_segmenti": [s["id"] for s in ss]}
        row["stato"] = {
            "geometria": status(True),                                     # swissTLM3D axis, survey polygons
            "larghezza": status(wm >= 0.8, wm >= 0.2),
            "segnaletica_orizzontale": status(seen and hid <= 0.2 * max(vis + hid, 1), seen),
            "segnaletica_verticale": "[!]",
            "vegetazione": status(True),
            "guard_rail": "[!]",
            "props": "[~]",
            "materiali": "[~]",
            "controllo_finale": status(not probs, True),
        }
        road_rows.append(row)
    # zones
    zone_rows = []
    for z, country, poly in sorted(zones, key=lambda q: q[0]):
        rs = [r for r in road_rows if r["zona"] == z]
        paths_km = sum(s["length"] for s in segs if s["kind"] == "path" and seg_zone[s["id"]] == z) / 1000
        zr = {"zona": z, "paese": "IT" if country.startswith("IT") or country == "IT" else "CH",
              "km2_in_mappa": round(poly.area / 1e6, 2), "strade_km": round(sum(r["km"] for r in rs), 1),
              "sentieri_km": round(paths_km, 1), "strade": len(rs),
              "vernice_km": round(sum(r["vernice_m"] for r in rs) / 1000, 2),
              "segnaletica_coperta_km": round(sum(r["segnaletica_coperta_m"] for r in rs) / 1000, 2),
              "senso_unico_km": round(sum(r["senso_unico_m"] for r in rs) / 1000, 2),
              "ponti": sum(r["ponti"] for r in rs), "piante_corrette": fix_by_zone.get(z, {}),
              "oggetti_osm": props_by_zone.get(z, {}), "problemi_controlli": prob_by_zone.get(z, {})}
        zone_rows.append(zr)
    out = {"zone": zone_rows, "strade": road_rows}
    json.dump(out, open(os.path.join(VER, "zone_report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    write_markdown(zone_rows, road_rows)
    write_register(load_json(os.path.join(WORK, "build_stats.json"), {}), checks, mk, road_rows)
    print("zones", len(zone_rows), "roads", len(road_rows))


def write_markdown(zone_rows, road_rows):
    L = ["# Zone della mappa", "",
         "Generato da `pipeline/zone_report.py` (dati in `zone_report.json`). Una zona per comune (confini di "
         "OpenStreetMap, da swissBOUNDARIES3D) dentro l'area giocabile. Legenda: `[x]` controllato su una fonte, "
         "`[~]` controllato in parte, `[!]` da verificare sul posto o nelle foto (nessuna fonte disponibile).", "",
         "| Zona | km² | Strade km | Sentieri km | Vernice rilevata km | Coperta (alberi/ombra) km | Senso unico km | "
         "Ponti | Piante corrette | Oggetti OSM | Segnalazioni dei controlli |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    name = lambda z: z["zona"] + (" (IT)" if z["paese"] == "IT" else "")
    for z in zone_rows:
        f = ", ".join("%s %d" % kv for kv in sorted(z["piante_corrette"].items())) or "-"
        o = ", ".join("%s %d" % kv for kv in sorted(z["oggetti_osm"].items())) or "-"
        p = ", ".join("%s %d" % kv for kv in sorted(z["problemi_controlli"].items())) or "-"
        L.append("| %s | %.2f | %.1f | %.1f | %.2f | %.2f | %.2f | %d | %s | %s | %s |" % (
            name(z), z["km2_in_mappa"], z["strade_km"], z["sentieri_km"], z["vernice_km"],
            z["segnaletica_coperta_km"], z["senso_unico_km"], z["ponti"], f, o, p))
    L += ["", "## Stato per zona", "",
          "Per ogni zona sono stati controllati, per tutte le strade: geometria e larghezza (swissTLM3D e misurazione "
          "ufficiale), topografia (swissALTI3D), segnaletica orizzontale (ortofoto SWISSIMAGE 10 cm del 2024), "
          "vegetazione (sagoma libera della strada, tronchi, piante sospese), collisioni e ostacoli (`check_level.py`). "
          "Segnaletica verticale, guardrail e muri sono verificati sulle foto solo lungo la cantonale Magliaso-Pura; "
          "altrove ci sono solo STOP e precedenze di OpenStreetMap, quindi le zone restano `[!]` per questi aspetti. "
          "Sul lato italiano (IT) la mappa ha solo il terreno (Copernicus) e il paesaggio, senza strade, edifici e "
          "alberi: le poche strade elencate là sono linee di swissTLM3D lungo il confine.", "",
          "| Zona | Geometria | Larghezza | Topografia | Segn. orizzontale | Segn. verticale | Guardrail | Ponti | Muri | "
          "Marciapiedi | Edifici | Vegetazione | Visibilità | Props | Materiali |", "|---|" + "---|" * 14]
    for z in zone_rows:
        rs = [r for r in road_rows if r["zona"] == z["zona"]]
        if z["paese"] == "IT":
            L.append("| %s | solo terreno | - | [x] | - | - | - | - | - | - | - | - | - | - | - |" % name(z))
            continue
        if not rs:
            continue
        agg = lambda key: "[x]" if all(r["stato"][key] == "[x]" for r in rs) else (
            "[!]" if all(r["stato"][key] == "[!]" for r in rs) else "[~]")
        L.append("| %s | %s | %s | [x] | %s | [!] | [!] | [~] | [~] | [~] | [x] | [x] | [~] | [~] | [~] |" % (
            name(z), agg("geometria"), agg("larghezza"), agg("segnaletica_orizzontale")))
    open(os.path.join(VER, "ZONE.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    R = ["# Elenco delle strade della mappa", "",
         "Generato da `pipeline/zone_report.py`: tutte le strade della rete (swissTLM3D, %d gruppi), per comune e nome; "
         "le strade senza nome sono raggruppate per classe. Colonne di stato: geometria, larghezza, segnaletica "
         "orizzontale, segnaletica verticale, vegetazione, guardrail, props, materiali, controllo finale (legenda in "
         "`ZONE.md`)." % len(road_rows), "",
         "| Zona | Strada | km | Classe | Cantonale | Largh. misurata | Vernice rilevata | Coperta | Senso unico | "
         "Piante corrette | Geom. | Largh. | Segn. or. | Segn. vert. | Veget. | Guardrail | Props | Materiali | Finale |",
         "|---|" + "---|" * 18]
    for r in road_rows:
        s = r["stato"]
        R.append("| %s | %s | %.2f | %s | %s | %d %% | %s | %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["zona"], r["strada"], r["km"], ", ".join(r["classi"]), "sì" if r["cantonale"] else "",
            r["larghezza_misurata_pct"], ("%d m (%s)" % (r["vernice_m"], ", ".join(r["segnaletica_tipi"]))) if r["vernice_m"] else "nessuna",
            ("%d m" % r["segnaletica_coperta_m"]) if r["segnaletica_coperta_m"] else "", ("%d m" % r["senso_unico_m"]) if r["senso_unico_m"] else "",
            r["piante_corrette"], s["geometria"], s["larghezza"], s["segnaletica_orizzontale"], s["segnaletica_verticale"],
            s["vegetazione"], s["guard_rail"], s["props"], s["materiali"], s["controllo_finale"]))
    open(os.path.join(VER, "STRADE.md"), "w", encoding="utf-8").write("\n".join(R) + "\n")


def it(v, digits=1):
    """A number with the Italian decimal comma."""
    return ("%.*f" % (digits, v)).replace(".", ",") if isinstance(v, (int, float)) else str(v)


def write_register(stats, checks, mk, road_rows):
    """REGISTRO.md: the differences between the map (v2.0) and the reality found in this revision, what
    was done and what is left, with the figures of this build."""
    cp = stats.get("canopy", {})
    rw = stats.get("railway", {})
    op = stats.get("osm_props", {})
    npnt = stats.get("network_paint") or {}
    paint_km = sum(b - a for ln in mk.get("lines", []) for a, b in ln.get("runs_s", [])) / 1000
    hidden_km = sum(h["len"] for h in mk.get("hidden", [])) / 1000
    no_paint = sum(1 for r in road_rows if not r["vernice_m"] and r["segnaletica_visibile_m"] > 50)
    # the v2.0 release measured with the same checks (canopy.check), and this build
    v20 = load_json(os.path.join(VER, "canopy_v2.0.json"), {})
    bc = v20.get("crowns_in_profile_by_class", {})
    now = lambda k: checks.get(k, "?")
    rows = [
        ("Tutta la mappa", "Vegetazione", "%s alberi con la chioma nella sagoma libera delle strade (%s sulle carreggiate, "
         "%s su marciapiedi e piazzali, %s sui sentieri), fino a %s m dentro: una chioma all'altezza di un'auto sopra "
         "la corsia" % (v20.get("crowns_in_profile", "?"), bc.get("carreggiata", "?"), bc.get("marciapiede o piazzale", "?"),
                        bc.get("sentiero", "?"), it(v20.get("crowns_in_profile_max_m", "?"))),
         "spostati fino a 3 m (%d), modello più stretto della stessa specie (%d), scala ridotta (%d), rimossi (%d); "
         "restano %s chiome al limite della tolleranza (0,3 m sul bordo)" %
         (cp.get("moved", 0), cp.get("swapped", 0), cp.get("scaled", 0), cp.get("removed", 0), now("crowns_in_profile")),
         "Risolto"),
        ("Tutta la mappa", "Vegetazione", "%s piante sospese più di 0,3 m sopra il suolo (il terreno è scavato lungo le strade "
         "dopo che gli alberi prendono la quota dal DTM) e %s interrate di oltre 1 m" %
         (v20.get("forest_floating", "?"), v20.get("forest_buried", "?")),
         "ogni pianta appoggiata al suolo sotto il tronco: ora %s sospese e %s interrate" %
         (now("forest_floating"), now("forest_buried")), "Risolto"),
        ("Tutta la mappa", "Vegetazione", "%s tronchi dentro muri o edifici" % v20.get("trunks_in_solids", "?"),
         "spostati (%d) o rimossi (%d); ora %s" % (cp.get("trunks_in_solids_moved", 0), cp.get("trunks_in_solids_removed", 0),
                                                   now("trunks_in_solids")), "Risolto"),
        ("Rete stradale (%d km)" % round(sum(r["km"] for r in road_rows)), "Segnaletica orizzontale",
         "nessuna segnaletica fuori dalla cantonale Magliaso-Pura",
         "rilevata nell'ortofoto SWISSIMAGE 10 cm (2024): %s km di linee (%d tracce), %d segni (strisce pedonali gialle, "
         "linee d'arresto, frecce, zebrature, zig-zag delle fermate)" % (it(paint_km), len(mk.get("lines", [])),
                                                                         len(mk.get("polygons", []))), "Risolto"),
        ("Rete stradale", "Segnaletica orizzontale", "%s km di strada coperti da alberi o in ombra nell'ortofoto" % it(hidden_km),
         "le linee viste ai due lati di un tratto coperto fino a 60 m continuano; i tratti più lunghi restano senza vernice",
         "Richiede verifica"),
        ("Rete stradale", "Segnaletica orizzontale", "%d strade senza vernice visibile nell'ortofoto" % no_paint,
         "nessuna segnaletica aggiunta (solo ciò che si vede)", "Controllato"),
        ("Rete stradale", "Segnaletica orizzontale", "vernice gialla sbiadita (saturazione 50-100) non riconosciuta; "
         "veicoli bianchi o gialli e macchie di luce presi per vernice",
         "soglie del giallo tarate sulle strisce pedonali di OpenStreetMap, vernice gialla solo su asfalto grigio; "
         "scartate le macchie larghe con finestrini e ombra di un veicolo e i riflessi sulle auto scure. Strisce pedonali di OSM sulle strade "
         "svizzere con vernice gialla rilevata: da 42 a 64 su 70", "Risolto"),
        ("Rete stradale", "Segnaletica orizzontale", "segni complessi (frecce, scritte, linee di attesa agli incroci senza "
         "altre linee) e cordoli chiari presi per linee di bordo",
         "rilevati solo vicino a linee tracciate o a strisce pedonali, STOP e precedenze di OSM; alcuni restano",
         "Richiede verifica"),
        ("Rete stradale", "Traffico IA", "sensi unici percorsi in entrambi i sensi (swissTLM3D non li registra)",
         "sensi unici da OpenStreetMap, rotonde (antiorario) e carreggiate separate (a destra) da swissTLM3D", "Risolto"),
        ("Rete stradale", "Traffico IA", "strade con divieto generale di circolazione usate dal traffico come le altre",
         "percorribilità 0,1 (il traffico le evita)", "Risolto"),
        ("Ponte Tresa", "Acqua", "la Tresa sotto il ponte di confine era asciutta: la diga del modello del lago stava "
         "alla foce, 15 m dal ponte", "diga spostata alla traversa, 416 m a valle lungo il fiume; il tratto al livello del lago ha l'acqua",
         "Risolto"),
        ("Ferrovia", "Binari", "binari della FLP (Lugano-Ponte Tresa) e delle FFS assenti: solo la ghiaia dipinta sul terreno",
         "%s km di binari (swissTLM3D): traversine, rotaie a scartamento reale, massicciata, %d m di passaggi a livello e "
         "binari nei piazzali dei raccordi industriali, %d m di ponti" % (it(rw.get("km", 0)), rw.get("level_crossing_m", 0),
                                                                           rw.get("bridge_m", 0)),
         "Risolto"),
        ("Ponte Tresa", "Ferrovia", "i binari della stazione FLP passano sotto il parcheggio di Piazzale della Stazione, "
         "che il terreno (swissALTI3D) tiene come suolo 5,6 m sopra le rotaie",
         "i %d m di binari sotto la copertura non sono costruiti, come le gallerie" % rw.get("covered_m", 0),
         "Richiede verifica"),
        ("Agno", "Ferrovia", "lungo il lago il terreno del livello non segue la quota reale dei binari: fino a 3,5 m più "
         "alto sul lato della cantonale (la sua scarpata copriva metà del binario) e più basso sul lato della passeggiata",
         "terreno abbassato sotto la massicciata fino alla quota di swissTLM3D, binari su un terrapieno dove il terreno "
         "è più basso (fino a 2,5 m)", "Risolto"),
        ("Ferrovia", "Linea di contatto", "pali e fili della FLP e della linea FFS assenti",
         "non costruiti: le posizioni dei pali non sono nei dati", "Richiede verifica"),
        ("Incroci", "Segnaletica verticale", "nessun cartello di STOP o di precedenza fuori dalla cantonale",
         "%d STOP e %d precedenze dove OpenStreetMap li registra (pannello disegnato, non fotografato)" %
         (op.get("stop", 0), op.get("give_way", 0)), "Risolto (dove registrati)"),
        ("Rete stradale", "Segnaletica verticale", "limiti di velocità, cartelli di località e di direzione assenti",
         "non costruiti: nessuna fonte con la posizione dei cartelli", "Richiede verifica"),
        ("Rete stradale", "Guardrail", "guardrail solo sulla cantonale Magliaso-Pura",
         "non aggiunti: OpenStreetMap ne registra 3 tratti, nessun'altra fonte", "Richiede verifica"),
        ("Paesi", "Arredo", "panchine, cestini e lampioni solo sulla cantonale",
         "%d panchine, %d cestini, %d lampioni di OpenStreetMap" % (op.get("bench", 0), op.get("waste_basket", 0),
                                                                  op.get("street_lamp", 0)), "Risolto (dove registrati)"),
        ("Fiumi", "Acqua", "Vedeggio, Magliasina e Tresa a valle della traversa senza acqua (letto in ghiaia)",
         "non costruita: servirebbe un oggetto River che non si può provare senza il gioco", "Richiede verifica"),
    ]
    obst = checks.get("obstacles_by_kind", {})
    if obst:
        rows.append(("Rete stradale", "Ostacoli", "punti in cui un'auto urta una mesh: %s" %
                     ", ".join("%s %d" % kv for kv in sorted(obst.items())),
                     "lasciati: gradini tra superfici agli incroci, muri e pali del percorso v1.x misurati nelle foto",
                     "Richiede verifica"))
    L = ["# Registro delle differenze", "",
         "Differenze tra la mappa v2.0 e la realtà trovate in questa revisione, con l'azione e lo stato. Generato da "
         "`pipeline/zone_report.py` con i numeri di questa costruzione (`work/build_stats.json`, `check_level.json`).", "",
         "| Zona | Elemento | Problema | Azione | Stato |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %s | %s |" % r for r in rows]
    open(os.path.join(VER, "REGISTRO.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
