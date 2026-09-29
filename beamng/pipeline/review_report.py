"""The review of the map against Street View, road by road (v2.2): beamng/verifica/REVISIONE.md and
revisione.json.

For every road of the network (grouped by municipality and street name, as zone_report.py does) it
states what was checked and with what:
- Street View: the share of the road within COVER_M m of a panorama of the coverage (sv_coverage.py) and
  the years of those panoramas; the panoramas used for the review (sv_fetch.py, one every 20 m);
- buildings along it whose facade tone was measured in the photos (sv_facades.py), walls whose material
  was seen (sv_walls.py), guard rails seen (sv_guardrails.py) and the share of its edges seen;
- the virtual drive test (drive_test.py): events per km before and after the fixes of this revision;
- the visual review: places compared photo against map (sv_review.py sheets), with the findings and
  what was done (dati/qa_review.json, written by hand during the review);
- the state: [x] checked on the photos and on the data, [~] on the data only for part of it (little or old
  coverage), [!] no Street View (forest roads, private roads): data and orthophoto only.
    python review_report.py
"""
import gzip, json, os
import numpy as np
from scipy.spatial import cKDTree
from config import WORK, wgs_to_local

HERE = os.path.dirname(os.path.abspath(__file__))
VER = os.path.join(os.path.dirname(HERE), "verifica")
DATI = os.path.join(os.path.dirname(HERE), "dati")
COVER_M = 15.0


def load(path, default):
    if not os.path.exists(path):
        return default
    if path.endswith(".gz"):
        return json.load(gzip.open(path, "rt", encoding="utf-8"))
    return json.load(open(path, encoding="utf-8"))


def main():
    import network
    import zone_report
    import shapely
    import area
    segs, st, _ = network.load()
    A = area.polygon()
    zones = [(n, c, p.intersection(A)) for n, c, p in zone_report.communes()]
    zones = [(n, c, p) for n, c, p in zones if not p.is_empty and p.area > 20_000]
    ztree = shapely.STRtree([p for _, _, p in zones])

    def zone_of(x, y):
        ids = ztree.query(shapely.Point(x, y), predicate="within")
        return zones[int(ids[0])][0] if len(ids) else "fuori dai comuni"
    cov = load(os.path.join(DATI, "sv_coverage.json.gz"), {"panoramas": []})["panoramas"]
    cxy = np.array([wgs_to_local(p["lat"], p["lon"]) for p in cov]) if cov else np.zeros((0, 2))
    cyear = np.array([int((p.get("date") or "0")[:4] or 0) for p in cov])
    ctree = cKDTree(cxy) if len(cxy) else None
    sel = load(os.path.join(WORK, "sv", "selected.json"), [])
    sxy = np.array([[p["x"], p["y"]] for p in sel]) if sel else np.zeros((0, 2))
    stree = cKDTree(sxy) if len(sxy) else None
    rails = load(os.path.join(DATI, "guardrails_sv.json"), [])
    rail_by_seg = {}
    for r in rails:
        rail_by_seg[r["seg"]] = rail_by_seg.get(r["seg"], 0.0) + r["length"]
    gcov = load(os.path.join(WORK, "sv", "guardrail_coverage.json"), {}).get("seen_by_seg", {})
    walls = load(os.path.join(DATI, "wall_materials.json"), {"walls": []})["walls"]
    wtree = cKDTree(np.array([[w[0], w[1]] for w in walls])) if walls else None
    fac = load(os.path.join(DATI, "facade_colors.json"), {})
    import buildings_mesh
    blds = {b["uuid"]: b for b in buildings_mesh.load_buildings()}
    fxy = np.array([[(blds[u]["bbox"][0][0] + blds[u]["bbox"][1][0]) / 2, (blds[u]["bbox"][0][1] + blds[u]["bbox"][1][1]) / 2]
                    for u in fac if u in blds]) if fac else np.zeros((0, 2))
    ftree = cKDTree(fxy) if len(fxy) else None
    drive = load(os.path.join(VER, "drive_test.json"), {"per_road": []})
    drive0 = load(os.path.join(VER, "drive_test_v2.1.json"), {"per_road": []})
    ev = {r["seg"]: r["events"] for r in drive["per_road"]}
    ev0 = {r["seg"]: r["events"] for r in drive0["per_road"]}
    qa = load(os.path.join(DATI, "qa_review.json"), {"luoghi": []})["luoghi"]
    groups = {}
    for s in segs:
        if s["kind"] != "road":
            continue
        a, n = s["first"], s["n"]
        k = a + n // 2
        z = zone_of(st["x"][k], st["y"][k])
        key = (z, s["name"] or "(senza nome: %s)" % zone_report.CLASS_IT.get(s["class"], s["class"]))
        groups.setdefault(key, []).append(s)
    rows = []
    for (z, name), ss in sorted(groups.items()):
        idx = np.concatenate([np.arange(s["first"], s["first"] + s["n"]) for s in ss])
        P = np.column_stack([st["x"][idx], st["y"][idx]])
        L = sum(s["length"] for s in ss)
        covered, years, used = 0.0, [], 0
        if ctree is not None:
            d, j = ctree.query(P)
            m = d < COVER_M
            covered = float(m.mean())
            years = sorted(set(cyear[j[m]].tolist()) - {0})
        if stree is not None:
            used = len(set(i for lst in stree.query_ball_point(P, COVER_M) for i in lst))
        bld = len(set(i for lst in ftree.query_ball_point(P, 40.0) for i in lst)) if ftree is not None else 0
        wl = [walls[i][2] for i in set(i for lst in wtree.query_ball_point(P, 30.0) for i in lst)] if wtree is not None else []
        rail_m = sum(rail_by_seg.get(s["id"], 0.0) for s in ss)
        seen = sum(gcov.get(str(s["id"]), 0) for s in ss) / max(2 * len(idx), 1)
        e_now = {}
        e_old = {}
        for s in ss:
            for kk, v in ev.get(s["id"], {}).items():
                e_now[kk] = e_now.get(kk, 0) + v
            for kk, v in ev0.get(s["id"], {}).items():
                e_old[kk] = e_old.get(kk, 0) + v
        notes = [q for q in qa if q.get("zona") == z and q.get("strada") == name]
        state = "[x]" if covered >= 0.5 else ("[~]" if covered > 0.05 else "[!]")
        rows.append({"zona": z, "strada": name, "km": round(L / 1000, 2), "sv_copertura_pct": round(100 * covered),
                     "sv_anni": years, "panoramiche_usate": used, "edifici_misurati": bld,
                     "muri": {c: wl.count(c) for c in set(wl)}, "guardrail_m": round(rail_m),
                     "bordi_visti_pct": round(100 * min(seen, 1.0)), "guida": e_now, "guida_v2_1": e_old,
                     "luoghi_rivisti": len(notes), "problemi": [q["problema"] for q in notes if q.get("problema")],
                     "modifiche": [q["azione"] for q in notes if q.get("azione")], "stato": state})
    json.dump({"strade": rows}, open(os.path.join(VER, "revisione.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    write_md(rows)
    print("roads", len(rows), "with Street View >= 50 %", sum(r["stato"] == "[x]" for r in rows))


def fmt_events(e):
    if not e:
        return "0"
    return ", ".join("%s %d" % (k, v) for k, v in sorted(e.items()))


def write_md(rows):
    L = ["# Revisione della mappa su Street View (v2.2)", "",
         "Generato da `pipeline/review_report.py` (dati in `revisione.json`). Per ogni strada della rete: quanta parte "
         "è coperta dalle panoramiche Street View (entro %d m) e di che anni, quante panoramiche sono state usate nella "
         "revisione (una ogni 20 m, `sv_fetch.py`), gli edifici lungo la strada con il tono della facciata misurato "
         "nelle foto, i muri di cui le foto mostrano il materiale, i guardrail visti nelle foto e la quota dei bordi "
         "della strada osservata, gli eventi della prova di guida virtuale (`drive_test.py`: STEP gradino sotto una "
         "ruota, LIFT ruota staccata, HARD accelerazione verticale forte, HOLE ruota senza superficie, TWIST cambio "
         "brusco di rollio o beccheggio) prima (v2.1) e dopo questa revisione, e i luoghi confrontati a vista (foto e "
         "mappa dalla stessa camera). Stato: `[x]` verificata sulle foto e sui dati, `[~]` foto solo per una parte, "
         "`[!]` nessuna panoramica (strade forestali, private): verificata sui dati ufficiali e sull'ortofoto." % COVER_M, ""]
    zones = []
    for r in rows:
        if r["zona"] not in zones:
            zones.append(r["zona"])
    tot = {"km": sum(r["km"] for r in rows), "x": sum(r["km"] for r in rows if r["stato"] == "[x]"),
           "t": sum(r["km"] for r in rows if r["stato"] == "[~]")}
    L += ["Totale: %.1f km di strade, %.1f km verificati sulle foto (`[x]`), %.1f km in parte (`[~]`)." %
          (tot["km"], tot["x"], tot["t"]), ""]
    for z in zones:
        rs = [r for r in rows if r["zona"] == z]
        L += ["## %s" % z, "",
              "| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | "
              "Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rs:
            yrs = ("%d-%d" % (r["sv_anni"][0], r["sv_anni"][-1]) if len(r["sv_anni"]) > 1 else
                   (str(r["sv_anni"][0]) if r["sv_anni"] else ""))
            pm = "; ".join(r["problemi"][:2] + r["modifiche"][:2])
            L.append("| %s | %.2f | %d %% %s | %d | %d | %s | %s | %d %% | %s | %s | %d | %s | %s |" % (
                r["strada"], r["km"], r["sv_copertura_pct"], ("(" + yrs + ")") if yrs else "", r["panoramiche_usate"],
                r["edifici_misurati"], ", ".join("%s %d" % kv for kv in sorted(r["muri"].items())) or "-",
                ("%d m" % r["guardrail_m"]) if r["guardrail_m"] else "-", r["bordi_visti_pct"], fmt_events(r["guida_v2_1"]),
                fmt_events(r["guida"]), r["luoghi_rivisti"], pm or "-", r["stato"]))
        L.append("")
    open(os.path.join(VER, "REVISIONE.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
