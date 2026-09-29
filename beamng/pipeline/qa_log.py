"""The log of the visual review (v2.2): every place compared in the photos and in the map (sv_review.py
sheets), what was found and what was done. beamng/dati/qa_review.json, read by review_report.py.
    import qa_log; qa_log.add(zona, strada, x, y, panorama, esito, problema, azione, stato)
esito: "coincide" (map and photo agree) or "differenza"; stato: "risolto", "verificato", "da verificare".
"""
import json, os

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "qa_review.json")


def load():
    if os.path.exists(LOG):
        return json.load(open(LOG, encoding="utf-8"))
    return {"luoghi": []}


def add(zona, strada, x, y, panorama, esito, problema="", azione="", stato="verificato", data=""):
    d = load()
    d["luoghi"].append({"zona": zona, "strada": strada, "x": round(float(x), 1), "y": round(float(y), 1),
                        "panorama": panorama, "data": data, "esito": esito, "problema": problema,
                        "azione": azione, "stato": stato})
    json.dump(d, open(LOG, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return len(d["luoghi"])
