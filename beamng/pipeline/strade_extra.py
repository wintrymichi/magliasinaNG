"""Roads added to the area beyond the boundary drawn by the user (v2.0): the cantonal road from the
start of the Street View route at Magliaso along the lake to Agno and up the Vedeggio valley through
Bioggio and Manno to Gravesano, at the foot of the eastern slopes of the Malcantone.

The road is the shortest way over the roads of swissTLM3D (data/tlm/TLM_STRASSE.json, no motorways,
no tunnels) that counts the cantonal ones (owner 'Kanton') at their length and every other road at
OTHER times it, from the node nearest the start of the route to the node nearest the village of
Gravesano (swissNAMES3D).
Output: dati/cantonale_gravesano.json, the line in LV95 (E, N). area.py reads it, so the area (and
the downloads made from it) does not need swissTLM3D.
    python strade_extra.py
"""
import collections, heapq, json, os
import numpy as np
import shapely
from scipy.spatial import cKDTree
from config import DATA, lv95_to_local, local_to_lv95
import area
import network
import places

OUT = os.path.join(area.DATI, "cantonale_gravesano.json")
MOTORWAY = {"Autobahn", "Autostrasse", "Ausfahrt", "Einfahrt", "Raststaette"}
OTHER = 4.0              # weight of a road the canton does not own, per metre


def road_lines():
    """[(local (n, 2) line, props)] of the roads of swissTLM3D that a car may take."""
    d = json.load(open(os.path.join(DATA, "tlm", "TLM_STRASSE.json"), encoding="utf-8"))
    out = []
    for f in d["features"]:
        p = f["props"]
        c = p.get("OBJEKTART")
        if c not in network.CLASSES or network.CLASSES[c][1] != "road" or c in MOTORWAY:
            continue
        if p.get("KUNSTBAUTE") in network.SKIP:
            continue
        for part in f["parts"]:
            P = np.asarray(part, np.float64)
            if len(P) >= 2:
                x, y = lv95_to_local(P[:, 0], P[:, 1])
                out.append((np.column_stack([x, y]), p))
    return out


def shortest(lines, start, end):
    """Indices of the lines on the way from the node nearest `start` to the node nearest `end`."""
    n = len(lines)
    ends = np.array([L[0] for L, _ in lines] + [L[-1] for L, _ in lines])
    tree = cKDTree(ends)
    node = -np.ones(len(ends), int)
    k = 0
    for i in range(len(ends)):
        if node[i] < 0:
            node[tree.query_ball_point(ends[i], network.SNAP)] = k
            k += 1
    adj = collections.defaultdict(list)
    for i, (L, p) in enumerate(lines):
        w = float(np.sum(np.linalg.norm(np.diff(L, axis=0), axis=1)))
        w *= 1.0 if p.get("EIGENTUEME") == "Kanton" else OTHER
        adj[node[i]].append((node[n + i], w, i))
        adj[node[n + i]].append((node[i], w, i))
    src = node[tree.query(start)[1]]
    dst = node[tree.query(end)[1]]
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        c, u = heapq.heappop(pq)
        if u == dst:
            break
        if c > dist.get(u, np.inf):
            continue
        for v, w, i in adj[u]:
            if c + w < dist.get(v, np.inf):
                dist[v] = c + w
                prev[v] = (u, i)
                heapq.heappush(pq, (c + w, v))
    if dst not in prev:
        raise RuntimeError("no road from %s to %s" % (start, end))
    out, u = [], dst
    while u != src:
        u, i = prev[u]
        out.append(i)
    return out[::-1]


def main():
    lines = road_lines()
    start = np.asarray(area.route().coords[0])
    end = np.asarray(places.place("Gravesano"))
    way = shortest(lines, start, end)
    road = shapely.line_merge(shapely.union_all([shapely.LineString(lines[i][0]) for i in way]))
    if road.geom_type != "LineString":
        raise RuntimeError("the road is not one line: %s" % road.geom_type)
    if np.hypot(*(np.asarray(road.coords[0]) - start)) > np.hypot(*(np.asarray(road.coords[-1]) - start)):
        road = shapely.LineString(road.coords[::-1])
    C = np.asarray(road.coords)
    E, N = local_to_lv95(C[:, 0], C[:, 1])
    owner, names = collections.Counter(), collections.Counter()
    for i in way:
        L, p = lines[i]
        m = float(np.sum(np.linalg.norm(np.diff(L, axis=0), axis=1)))
        owner[p.get("EIGENTUEME") or "-"] += m
        names[p.get("STRNAME") or "-"] += m
    with open(OUT, "w", encoding="utf-8") as f:                    # one point per line
        f.write('{"name": "Strada cantonale Magliaso - Agno - Bioggio - Manno - Gravesano",\n'
                ' "source": "swissTLM3D, strade_extra.py",\n "length_m": %.1f,\n "lv95": [\n' % road.length)
        f.write(",\n".join("  [%.2f, %.2f]" % (e, n_) for e, n_ in zip(E, N)))
        f.write("\n ]}\n")
    print("road: %d pieces, %.0f m, from (%.0f, %.0f) to (%.0f, %.0f)" % (len(way), road.length, *C[0], *C[-1]))
    print("owners (m):", {k: round(v) for k, v in owner.most_common()})
    print("names (m):", {k: round(v) for k, v in names.most_common(8)})
    print("->", OUT)


if __name__ == "__main__":
    main()
