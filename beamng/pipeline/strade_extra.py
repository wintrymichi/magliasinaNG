"""Roads added to the area beyond the boundary drawn by the user (v2.0): the cantonal road from the
start of the Street View route at Magliaso along the lake to Agno and up the Vedeggio valley through
Bioggio and Manno to Gravesano, at the foot of the eastern slopes of the Malcantone.

The road is the shortest way over the roads of swissTLM3D (data/tlm/TLM_STRASSE.json, no motorways,
no tunnels) that counts the cantonal ones (owner 'Kanton') at their length and every other road at
OTHER times it, from the node nearest the start of the route to the node nearest the village of
Gravesano (swissNAMES3D).
Output: dati/cantonale_gravesano.json, the line in LV95 (E, N). area.py reads it, so the area (and
the downloads made from it) does not need swissTLM3D.

v2.2: the roads the user found missing, each a chain of shortest ways (as above) between waypoints:
- the pass above Gravesano, the "Penudria" (Stradón da Rós through Penodra), from Gravesano to Arosio;
- the cantonal road from Ponte Tresa along the lake through Caslano to Magliaso;
- from the station of Caslano through the village to the road along the lake to the Torrazza
  (Via Torrazza), opposite Ponte Tresa.
v2.8: the cantonal road from Arosio through Mugena, Vezio, Fescoggia and Breno down to Miglieglia and
Novaggio, so that from Arosio the round over the Alto Malcantone closes back to Novaggio.
Output: dati/strade_extra_v22.json (the lines in LV95); area.py joins a corridor of EXTRA_CORRIDOR m
around them to the area.
    python strade_extra.py               (both files)
    python strade_extra.py --corridors   (only dati/strade_extra_v22.json)
The roads already in dati/strade_extra_v22.json are kept; --again computes them all again.
"""
import collections, heapq, json, os, sys
import numpy as np
import shapely
from scipy.spatial import cKDTree
from config import DATA, lv95_to_local, local_to_lv95
import area
import network
import places

OUT = os.path.join(area.DATI, "cantonale_gravesano.json")
OUT_V22 = os.path.join(area.DATI, area.CORRIDORS)
# v2.2: (key, name, waypoints): settlements of swissNAMES3D or LV95 points (E, N)
CORRIDORS = [
    ("passo_arosio", "Passo sopra Gravesano (Penudria, Stradón da Rós): Gravesano - Arosio", ["Gravesano", "Arosio"]),
    ("cantonale_caslano", "Strada cantonale Ponte Tresa - Caslano - Magliaso", ["Ponte Tresa", "Magliaso"]),
    ("caslano_torrazza", "Caslano: dalla stazione alla Torrazza (Via Torrazza)",
     [(2711420.0, 1092813.0), "Caslano", (2711080.0, 1090964.0)]),       # station, village, Torrazza
    ("arosio_miglieglia", "Strada cantonale Arosio - Mugena - Vezio - Fescoggia - Breno - Miglieglia - Novaggio",
     ["Arosio", "Mugena", "Breno", "Miglieglia", "Novaggio"]),
]
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


def waypoint(w):
    if isinstance(w, str):
        return np.asarray(places.place(w), np.float64)
    return np.asarray(lv95_to_local(*w), np.float64).ravel()


def corridors(again=False):
    """v2.2: the lines of CORRIDORS -> dati/strade_extra_v22.json. A road already in the file is kept as it is
    (newer swissTLM3D or swissNAMES3D would move the area of the released versions), unless `again`."""
    lines = road_lines()
    kept = {}
    if not again and os.path.exists(OUT_V22):
        kept = {r["key"]: r for r in json.load(open(OUT_V22, encoding="utf-8"))["roads"]}
    roads = []
    for key, name, wps in CORRIDORS:
        if key in kept:
            roads.append(kept[key])
            print("%s: kept, %.0f m" % (key, kept[key]["length_m"]))
            continue
        pts = [waypoint(w) for w in wps]
        way = []
        for a, b in zip(pts[:-1], pts[1:]):
            way += [i for i in shortest(lines, a, b) if i not in way]
        merged = shapely.line_merge(shapely.union_all([shapely.LineString(lines[i][0]) for i in way]))
        parts = list(shapely.get_parts(merged))
        names = collections.Counter()
        for i in way:
            L, p = lines[i]
            names[p.get("STRNAME") or "-"] += float(np.sum(np.linalg.norm(np.diff(L, axis=0), axis=1)))
        length = sum(g.length for g in parts)
        roads.append({"key": key, "name": name, "length_m": round(length, 1),
                      "streets": {k: round(v) for k, v in names.most_common()},
                      "parts": [[[round(float(e), 2), round(float(n_), 2)] for e, n_ in
                                 zip(*local_to_lv95(*np.asarray(g.coords)[:, :2].T))] for g in parts]})
        print("%s: %d pieces, %.0f m, %d parts; streets (m): %s" % (key, len(way), length, len(parts),
                                                                  {k: round(v) for k, v in names.most_common(6)}))
    with open(OUT_V22, "w", encoding="utf-8") as f:
        json.dump({"source": "swissTLM3D, strade_extra.py (v2.2)", "roads": roads}, f, ensure_ascii=False)
    print("->", OUT_V22)


if __name__ == "__main__":
    if "--corridors" not in sys.argv:
        main()
    corridors(again="--again" in sys.argv)
