"""The log of the visual review (v2.2): every place compared in the photos and in the map (sv_review.py
sheets), what was found and what was done. beamng/dati/qa_review.json, read by review_report.py.
    import qa_log; qa_log.add(zona, strada, x, y, panorama, esito, problema, azione, stato)
esito: "coincide" (map and photo agree) or "differenza"; stato: "risolto", "verificato", "da verificare".
qa_log.locate(x, y) gives the (zona, strada) of a place as review_report.py groups the roads: the
municipality of the nearest road and its name.
"""
import json, os

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "qa_review.json")


_where = {}


def locate(x, y):
    """(municipality, street) of the road nearest to (x, y), named as review_report.py names them."""
    import numpy as np
    import shapely
    from scipy.spatial import cKDTree
    import network, zone_report, area
    if not _where:
        segs, st, _ = network.load()
        road = np.array([segs[k]["kind"] == "road" for k in st["seg"]])
        idx = np.flatnonzero(road)
        _where["tree"] = cKDTree(np.column_stack([st["x"][idx], st["y"][idx]]))
        _where["idx"], _where["segs"], _where["st"] = idx, segs, st
        A = area.polygon()
        zones = [(n, pl.intersection(A)) for n, c, pl in zone_report.communes()]
        _where["zones"] = [(n, pl) for n, pl in zones if not pl.is_empty and pl.area > 20_000]
    segs, st = _where["segs"], _where["st"]
    _, j = _where["tree"].query([x, y])
    s = segs[st["seg"][_where["idx"][j]]]
    k = s["first"] + s["n"] // 2                    # the zone of a road: that of its middle station
    zona = next((n for n, pl in _where["zones"] if pl.contains(shapely.Point(st["x"][k], st["y"][k]))),
                "fuori dai comuni")
    strada = s["name"] or "(senza nome: %s)" % zone_report.CLASS_IT.get(s["class"], s["class"])
    return zona, strada


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
