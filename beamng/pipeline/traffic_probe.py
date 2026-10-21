"""The AI network of v3.0.40 on the released level, without building it (a development aid like fix_review.py):
the AI roads made again from the network (network_mesh.Network, ai_roads.network_roads, ai_roads.traffic_ready)
with the main route of the level, written into the level folder; the road paint step run on it for the stop
and give-way points (markings_rules: signals.json); then the review (ai_roads.review) and close-ups of junctions
with the roads, their speed limits, the ends left and the signal points.
    python traffic_probe.py <level root (the folder holding levels/)> <out folder>
"""
import json, os, sys
import numpy as np
import shapely
from config import LEVEL_NAME
import ai_roads

ZOOMS = [("magliaso_rotonda", 767.0, -1115.0, 45.0), ("magliaso_paese", 1100.0, -960.0, 80.0),
         ("agno", 2330.0, 630.0, 90.0), ("miglieglia", -1000.0, 3560.0, 150.0), ("astano", -3700.0, 2150.0, 150.0),
         ("castelrotto", -2400.0, 33.0, 80.0), ("vezio", 960.0, 6070.0, 150.0), ("arosio", 2270.0, 6300.0, 150.0),
         ("breno", -60.0, 4600.0, 150.0), ("via_lugano", 3380.0, 2880.0, 100.0)]


def zoom(roads, sig, name, x0, y0, r, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.spatial import cKDTree
    P = np.concatenate([np.asarray(o["nodes"])[:, :2] for o in roads])
    t = cKDTree(P)
    fig, ax = plt.subplots(figsize=(10, 10))
    for o in roads:
        N = np.asarray(o["nodes"])
        if np.hypot(N[:, 0] - x0, N[:, 1] - y0).min() > r * 1.5:
            continue
        col = "C1" if o.get("oneWay") else ("C7" if o.get("gatedRoad") else "C0")
        ax.plot(N[:, 0], N[:, 1], ".-", lw=1.2, ms=2, color=col)
        if o.get("oneWay"):
            k = len(N) // 2
            ax.annotate("", N[min(k + 1, len(N) - 1), :2], N[k, :2], arrowprops=dict(arrowstyle="->", color="C1"))
        for e in (N[0], N[-1]):
            if len(t.query_ball_point(e[:2], 0.05)) == 1:
                ax.plot(e[0], e[1], "rx", ms=8)
        m = len(N) // 2
        ax.text(N[m, 0], N[m, 1], str(round(float(o.get("speedLimit", 0)) * 3.6)), fontsize=8)
    kind = {c["id"]: c["name"] for c in sig.get("controllers", [])}
    for i in sig.get("instances", []):
        p, d = i["pos"], i["dir"]
        ax.arrow(p[0], p[1], d[0] * 3, d[1] * 3, head_width=1.2, color="red" if kind[i["controllerId"]] == "stop" else "blue")
    ax.set_xlim(x0 - r, x0 + r)
    ax.set_ylim(y0 - r, y0 + r)
    ax.set_aspect("equal")
    ax.set_title(f"{name}: AI roads (orange one-way, grey private), km/h, x = dead end, arrows: STOP red, give way blue")
    fig.savefig(os.path.join(out, f"zoom_{name}.png"), dpi=80, bbox_inches="tight")
    plt.close(fig)


def main(root, out):
    import network_mesh
    os.makedirs(out, exist_ok=True)
    lv = os.path.join(root, "levels", LEVEL_NAME)
    f = os.path.join(lv, "main", "MissionGroup", "AIRoads", "items.level.json")
    old = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    json.dump(ai_roads.graph_report(old), open(os.path.join(out, "ai_network_v3.0.json"), "w"), indent=1)
    parent = next((o["__parent"] for o in old if "__parent" in o), None)
    main = next(o for o in old if o["name"] == "strada_cantonale")
    main["_class"] = "8m Strasse"
    net = network_mesh.Network()
    zone = shapely.LineString(np.asarray(main["nodes"])[:, :2]).buffer(4.0)
    roads = [main]
    ai_roads.network_roads(roads, net, zone)
    rep = ai_roads.traffic_ready(roads)
    json.dump(rep, open(os.path.join(out, "traffic_ready.json"), "w"), indent=1)
    for o in roads:
        if parent:
            o["__parent"] = parent
    open(f, "w", encoding="utf-8").write("\n".join(json.dumps(o, separators=(",", ":")) for o in roads) + "\n")
    import markings_rules
    markings_rules.markings_rules_step(root, report=os.path.join(out, "markings.json"))
    ai_roads.review(lv, out)
    sig = json.load(open(os.path.join(lv, "signals.json")))
    json.dump(sig, open(os.path.join(out, "signals.json"), "w"), indent=1)
    for z in ZOOMS:
        zoom(roads, sig, *z, out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
