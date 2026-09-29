"""Where the events of the virtual drive test happen (v2.2): the context of every place of
verifica/drive_test.json, to find what in the road meshes makes a car jump.

Context of a place: at a junction (a node where 3 or more lines meet, within JUNCTION m), at the seam of
two 128 m road chunks, at the end of a bridge deck, at the edge of the corridor of the Strada Cantonale
(the v1.1 surfaces), on a surveyed polygon or on a strip of a line without survey, near the border of
two surveyed polygons; the step between the surfaces there.
    python drive_context.py
"""
import json, os
import numpy as np
import shapely
from scipy.spatial import cKDTree
from config import WORK
import network

VER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica")
JUNCTION = 10.0
CHUNK = 128.0


def main():
    d = json.load(open(os.path.join(VER, "drive_test.json")))
    segs, st, node_pos = network.load()
    deg = np.bincount(np.array([s["nodes"] for s in segs]).ravel(), minlength=len(node_pos))
    jtree = cKDTree(node_pos[deg >= 3])
    bridge_ends = np.array([node_pos[n] for s in segs if s["bridge"] for n in s["nodes"]]).reshape(-1, 2)
    btree = cKDTree(bridge_ends) if len(bridge_ends) else None
    st_ = np.load(os.path.join(WORK, "roads_state.npz"), allow_pickle=True)
    corridor = shapely.from_wkb(st_["corridor"].tobytes())
    edge = corridor.boundary
    shapely.prepare(edge)
    import pickle
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    polys = [g for k in ("strada_sentiero", "marciapiede", "altro_rivestimento_duro", "spartitraffico")
             for g, _ in av["LCSF"].get(k, [])]
    ptree = shapely.STRtree(polys)
    rows = []
    for p in d["places"]:
        x, y = p["x"], p["y"]
        pt = shapely.Point(x, y)
        ctx = []
        if jtree.query([x, y])[0] < JUNCTION:
            ctx.append("incrocio")
        fx, fy = x / CHUNK, y / CHUNK
        if min(abs(fx - round(fx)), abs(fy - round(fy))) * CHUNK < 1.0:
            ctx.append("giunzione_chunk")
        if btree is not None and btree.query([x, y])[0] < 10.0:
            ctx.append("fine_ponte")
        if shapely.distance(edge, pt) < 4.0:
            ctx.append("bordo_corridoio")
        near = ptree.query(pt.buffer(1.5), predicate="intersects")
        if len(near) == 0:
            ctx.append("striscia")
        elif len(near) >= 2:
            ctx.append("bordo_poligoni")
        rows.append({**p, "contesto": ctx})
    from collections import Counter
    by = Counter()
    for r in rows:
        for c in (r["contesto"] or ["altro"]):
            by[(r["what"], r["cls"], c)] += 1
    json.dump(rows, open(os.path.join(WORK, "drive_context.json"), "w"))
    for (w, c, k), n in sorted(by.items(), key=lambda kv: -kv[1])[:40]:
        print("%-6s %-6s %-18s %d" % (w, c, k, n))


if __name__ == "__main__":
    main()
