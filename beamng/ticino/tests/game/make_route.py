"""A driving route for the in-game autotest that needs no AI road graph: the shortest path over the level's AI roads
(main/MissionGroup/AIRoads) through a list of places, resampled every STEP m with the time of each point at the road's
speed limit (at most VMAX). autotest.lua hands it to the car's scriptai (ai.startFollowing with points {x, y, z, t}).
  python3 make_route.py <level folder> route.json
"""
import json, os, sys
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

PLACES = [(752, -1100), (545, -968), (-200, -215), (-240, 50), (-250, -1000), (-2250, -1060), (-1200, -2000),
          (783, -1143), (2090, 0)]          # Magliaso (on the cantonale: in run 9 the car started inside the
                                            # roundabout and hung there 26 s, then raced the late timeline), up the cantonale to Pura, down to Ponte Tresa, Caslano, Agno
A_LAT = 2.5                         # m/s2 in bends
STEP, VMAX, WELD = 8.0, 11.0, 1.0   # 40 km/h: scriptai catches up on a late timeline at any speed (run 9 flipped at 50)


def main(level, out):
    P, E, V, D = [], [], [], []
    for line in open(os.path.join(level, "main", "MissionGroup", "AIRoads", "items.level.json")):
        r = json.loads(line)
        if r.get("class") != "DecalRoad" or not r.get("drivability"):
            continue
        n = np.array(r["nodes"], float)[:, :3]
        v = min(float(r.get("speedLimit") or VMAX), VMAX)
        k0 = len(P)
        P.extend(n.tolist())
        for a in range(len(n) - 1):
            E.append((k0 + a, k0 + a + 1))
            V.append(v)
            D.append(float(r.get("drivability") or 1.0))
    P = np.array(P)
    tree = cKDTree(P[:, :2])
    pairs = tree.query_pairs(WELD, output_type="ndarray")
    E = np.concatenate([np.array(E), pairs])
    V = np.concatenate([np.array(V), np.full(len(pairs), VMAX)])
    D = np.concatenate([np.array(D), np.ones(len(pairs))])
    # weighted by drivability ** 4 (as races.py): the plain shortest path took a village lane under a retaining wall
    # north of the start, and the car fell 2 m off the road into it (laptop run 9)
    L = (np.linalg.norm(P[E[:, 0], :2] - P[E[:, 1], :2], axis=1) + 1e-3) / np.clip(D, 0.05, 1.0) ** 4
    n = len(P)
    G = coo_matrix((np.r_[L, L], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
    vmap = {}
    for (a, b), v in zip(E, V):
        vmap[(a, b)] = vmap[(b, a)] = v
    route = []
    for (x0, y0), (x1, y1) in zip(PLACES[:-1], PLACES[1:]):
        a, b = tree.query([x0, y0])[1], tree.query([x1, y1])[1]
        _, pred = dijkstra(G, indices=a, return_predecessors=True)
        if pred[b] < 0:
            print("no path", (x0, y0), "->", (x1, y1))
            continue
        seq = [b]
        while seq[-1] != a:
            seq.append(pred[seq[-1]])
        seq = seq[::-1]
        route.extend(seq if not route else seq[1:])
    pts, t, last = [], 0.0, None
    for i, k in enumerate(route):
        p = P[k]
        if last is not None:
            d = np.linalg.norm(p[:2] - last[:2])
            if d < STEP and i < len(route) - 1:
                continue
            t += d / vmap.get((route[i - 1], k), VMAX)
        pts.append({"x": round(p[0], 2), "y": round(p[1], 2), "z": round(p[2], 2), "t": round(t, 2),
                    "v": vmap.get((route[i - 1], k), VMAX) if i else VMAX})
        last = p
    # slower in bends (lateral acceleration A_LAT over the radius of three points): the hairpins at 40 km/h
    X = np.array([[q["x"], q["y"]] for q in pts])
    a, b, c = X[:-2], X[1:-1], X[2:]
    ab, bc, ca = (np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1))
    area = np.abs((b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]) / 2
    R = np.r_[np.inf, ab * bc * ca / np.maximum(4 * area, 1e-6), np.inf]
    vb = np.minimum(VMAX, np.sqrt(A_LAT * R))
    vb = np.minimum.reduce([vb, np.r_[vb[1:], VMAX], np.r_[VMAX, vb[:-1]]])      # slow a point before and after
    t = 0.0
    for i in range(1, len(pts)):
        v0 = min(pts[i]["v"], vb[i - 1], vb[i])
        t += np.linalg.norm(X[i] - X[i - 1]) / max(v0, 2.0)
        pts[i]["t"] = round(t, 2)
    for q in pts:
        q.pop("v", None)
    json.dump({"places": PLACES, "points": pts}, open(out, "w"))
    km = sum(np.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(pts, pts[1:])) / 1000
    print(len(pts), "points, %.1f km, %.0f s" % (km, t))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
