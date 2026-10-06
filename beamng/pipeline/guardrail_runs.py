"""The guard rails of a built level zip (v2.7) read back from its meshes, as polylines: the start of the
work to replace the procedural W-beam rails (guardrail_mesh.py) with the guard rail models of the game's
Italy level, placed along the same lines.

Every rail of guardrail_mesh.py is the A-profile swept along its line: the top of its back has a vertex
exactly 0.31 m straight below it (the foot of the back), which no other pair of the profile has; the
vertex 0.035 m lower and 0.05 m out from the top gives the side the road is on. The tops are chained into
lines (0.5 m apart, as resampled). Result on v2.7: 330 runs, 11.56 km.

Usage: python guardrail_runs.py <level.zip> [out.json]
"""
import json, sys, zipfile
import numpy as np
from scipy.spatial import cKDTree
from patch_signs import read_dae, scene_shapes


def rails(z):
    out = []
    for path, pos in scene_shapes(z, "roads/guardrails"):
        V, N, T, C, parts = read_dae(z.read(path))
        for mat, idx in parts:
            if mat != "mp_guardrail": continue
            P = np.unique(np.round(V[idx[:, 0]] + pos, 3), axis=0)
            tree = cKDTree(P)
            # top of the face: a vertex with one 0.31 m straight below it
            lo = P - [0, 0, 0.31]
            d, j = tree.query(lo)
            top = P[d < 0.004]
            # towards the road: the vertex 0.035 m lower and 0.05 m out
            d1, j1 = tree.query(top - [0, 0, 0.035], k=6)
            road = np.zeros((len(top), 2))
            for i in range(len(top)):
                for dd, jj in zip(d1[i], j1[i]):
                    q = P[jj]
                    if abs(q[2] - (top[i, 2] - 0.035)) < 0.003 and abs(np.hypot(*(q[:2] - top[i, :2])) - 0.05) < 0.004:
                        road[i] = (q[:2] - top[i, :2]) / 0.05; break
            # chain
            t2 = cKDTree(top[:, :2])
            used = np.zeros(len(top), bool)
            nb = t2.query_ball_point(top[:, :2], 0.62)
            deg = np.array([len(n) - 1 for n in nb])
            for s in list(np.flatnonzero(deg <= 1)) + list(range(len(top))):
                if used[s]: continue
                line = [s]; used[s] = True
                while True:
                    c = [k for k in nb[line[-1]] if not used[k]]
                    if not c: break
                    k = min(c, key=lambda k: np.hypot(*(top[k, :2] - top[line[-1], :2])))
                    used[k] = True; line.append(k)
                if len(line) >= 2:
                    out.append({"pts": top[line], "road": road[line], "chunk": path})
    return out

if __name__ == "__main__":
    z = zipfile.ZipFile(sys.argv[1])
    R = rails(z)
    L = [np.linalg.norm(np.diff(r["pts"][:, :2], axis=0), axis=1).sum() for r in R]
    print(len(R), "runs", round(sum(L) / 1000, 2), "km")
    if len(sys.argv) > 2:
        json.dump([{"pts": np.round(r["pts"], 3).tolist(), "road": np.round(r["road"], 3).tolist(),
                    "chunk": r["chunk"]} for r in R], open(sys.argv[2], "w"))
