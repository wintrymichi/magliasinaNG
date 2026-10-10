"""What the level has twice (v2.8): road signs, guard rails and walls standing in the place of another.

- objects: TSStatics of the same shape at the same place, forest items of the same type at the same place;
- guard rails: modules of the game's Italy guard rail (forest items, guardrail_mesh.py) whose beam runs along
  the beam of another module (centre within RAIL_D m of its axis, overlapping along it, parallel), not the
  0.2 m overlap of two modules of the same run;
- signs: sign plates (two triangles of a sign material) facing the same way as a plate of the same signal
  within SIGN_D m;
- walls: steep wall triangles lying in the face of another wall triangle (within WALL_D m of its plane, the
  same way out, their centres within WALL_R m), the area of the second one.

    python doubles.py <mod zip | folder that holds levels/>      -> counts, and the places, as JSON
"""
import json, os, re, sys, zipfile
from collections import Counter, defaultdict
import numpy as np
from scipy.spatial import cKDTree

LEVEL = "levels/magliaso_pura"
RAIL_D, RAIL_ALONG = 0.6, 2.0       # m: a module this close to the axis of another, its centre this close along it
SIGN_D = 6.0                        # m
WALL_D, WALL_R, WALL_MIN = 0.06, 0.35, 0.02   # m, m, m^2
_FA = re.compile(rb'<float_array id="(g-[a-z]+)" count="\d+">([^<]*)</float_array>')
_TRI = re.compile(rb'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', re.S)
SIGN_MAT = re.compile(r"^mp_(ch_.*|sign_\d.*|osm_stop|osm_giveway)$")
WALL_MAT = re.compile(r"^mp_(wall_|rwall_|road_wall)")


class Files:
    def __init__(self, src):
        if os.path.isdir(src):
            self.root = src
            self.names = sorted(os.path.relpath(os.path.join(d, f), src).replace(os.sep, "/")
                                for d, _, fs in os.walk(os.path.join(src, "levels")) for f in fs)
            self.read = lambda n: open(os.path.join(src, *n.split("/")), "rb").read()
        else:
            z = zipfile.ZipFile(src)
            self.names = z.namelist()
            self.read = z.read


def read_dae(data):
    arr = {m.group(1): m.group(2) for m in _FA.finditer(data)}
    V = np.array(arr[b"g-pa"].split(), np.float64).reshape(-1, 3)
    parts = []
    for m in _TRI.finditer(data):
        nin = m.group(2).count(b"<input")
        idx = np.array(m.group(3).split(), np.int64).reshape(-1, nin)
        parts.append((m.group(1).decode(), V[idx[:, 0]].reshape(-1, 3, 3)))
    return parts


def statics(f):
    out = []
    for n in f.names:
        if n.startswith(f"{LEVEL}/main/") and n.endswith("items.level.json"):
            for l in f.read(n).decode("utf-8").splitlines():
                if l.strip():
                    o = json.loads(l)
                    if o.get("class") == "TSStatic":
                        out.append((n, o))
    return out


def forest(f):
    out = []
    for n in f.names:
        if n.startswith(f"{LEVEL}/forest/") and n.endswith(".forest4.json"):
            for l in f.read(n).decode("utf-8").splitlines():
                if l.strip():
                    out.append(json.loads(l))
    return out


def world_tris(f, objs, keep):
    """{material: [(k, 3, 3) world triangles, shape]} of the pipeline shapes, materials passing keep."""
    out = defaultdict(list)
    cache = {}
    for n, o in objs:
        s = o.get("shapeName", "")
        if not s.startswith("/" + LEVEL + "/") or not s.endswith(".dae"):
            continue
        if s not in cache:
            try:
                cache[s] = [(m, t) for m, t in read_dae(f.read(s[1:])) if keep(m)]
            except (KeyError, ValueError):
                cache[s] = []
        p = np.array(o.get("position", [0, 0, 0]), np.float64)
        R = np.array(o["rotationMatrix"], np.float64).reshape(3, 3) if "rotationMatrix" in o else np.eye(3)
        sc = np.array(o.get("scale", [1, 1, 1]), np.float64)
        for m, t in cache[s]:
            out[m].append((p + (t * sc) @ R, s))
    return out


def same_objects(objs, items):
    st = Counter((o["shapeName"], tuple(round(v, 2) for v in o.get("position", [0, 0, 0])),
                  tuple(round(v, 3) for v in o.get("rotationMatrix", []))) for _, o in objs if "shapeName" in o)
    fo = Counter((i["type"], tuple(round(v, 2) for v in i["pos"])) for i in items)
    return ({"tsstatic_copies": sum(c - 1 for c in st.values()),
             "tsstatic_shapes": sorted({k[0] for k, c in st.items() if c > 1})[:20],
             "forest_copies": sum(c - 1 for c in fo.values()),
             "forest_types": dict(Counter(k[0] for k, c in fo.items() if c > 1))})


def rail_doubles(items):
    """Modules (index) lying on another module's beam; returns (pairs, places)."""
    rails = [i for i in items if i["type"] == "italy_guardrails_basic"]
    if not rails:
        return {"modules": 0}
    P = np.array([i["pos"] for i in rails], np.float64)
    X = np.array([i["rotationMatrix"][:3] for i in rails], np.float64)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)
    tree = cKDTree(P[:, :2])
    dup = np.zeros(len(P), bool)
    for a, b in sorted(tree.query_pairs(3.2)):
        if dup[a] or dup[b]:
            continue
        if abs(float(X[a, :2] @ X[b, :2])) < 0.9:
            continue
        d = P[b] - P[a]
        along = abs(float(d[:2] @ X[a, :2]))
        across = abs(float(d[0] * X[a, 1] - d[1] * X[a, 0]))
        if across < RAIL_D and abs(d[2]) < 0.8 and along < RAIL_ALONG:
            dup[b] = True
    places = P[dup]
    return {"modules": len(P), "doubled": int(dup.sum()), "doubled_m": round(float(dup.sum()) * 2.8),
            "places": [[round(float(x), 1), round(float(y), 1)] for x, y, _ in places[:400]]}


def plates(tris):
    """[(material, centre (3,), normal (3,), width)] of the sign plates: pairs of triangles."""
    out = []
    for m, lst in tris.items():
        if not SIGN_MAT.match(m) or m.endswith("_back"):
            continue
        for t, s in lst:
            for k in range(0, len(t) - 1, 2):
                q = np.concatenate([t[k], t[k + 1]])
                n = np.cross(t[k][1] - t[k][0], t[k][2] - t[k][0])
                nn = np.linalg.norm(n)
                if nn < 1e-9:
                    continue
                out.append((m, q.mean(0), n / nn, s))
    return out


def signal(mat):
    """The signal a plate material shows: the STOP and give-way of props_osm.py are 3.01 and 3.02."""
    m = {"mp_osm_stop": "ch_3_01", "mp_osm_giveway": "ch_3_02"}.get(mat, mat[3:])
    return re.sub(r"_[0-9a-f]{6}$", "", m)


def sign_doubles(pl):
    if not pl:
        return {"plates": 0}
    C = np.array([p[1] for p in pl])
    Nr = np.array([p[2] for p in pl])
    tree = cKDTree(C[:, :2])
    hist, kinds, places = Counter(), Counter(), []
    dup = np.zeros(len(pl), bool)
    for a, b in sorted(tree.query_pairs(SIGN_D)):
        if signal(pl[a][0]) != signal(pl[b][0]) or dup[a] or dup[b]:
            continue
        if float(Nr[a] @ Nr[b]) < 0.7:
            continue
        d = float(np.hypot(*(C[a, :2] - C[b, :2])))
        dup[b] = True
        hist["<0.5" if d < 0.5 else "<2" if d < 2 else "<4" if d < 4 else "<6"] += 1
        sa, sb = os.path.basename(pl[a][3]), os.path.basename(pl[b][3])
        kinds[" + ".join(sorted((sa, sb)))] += 1
        places.append({"mat": pl[a][0], "at": [round(float(C[b, 0]), 1), round(float(C[b, 1]), 1)], "d": round(d, 2),
                       "shapes": [sa, sb]})
    return {"plates": len(pl), "doubled": int(dup.sum()), "by_distance": dict(hist), "by_shapes": dict(kinds),
            "places": places[:400]}


def wall_doubles(tris):
    T, owner = [], []
    for m, lst in tris.items():
        if not WALL_MAT.match(m):
            continue
        for t, s in lst:
            T.append(t)
            owner += [f"{m}|{os.path.basename(s)}"] * len(t)
    if not T:
        return {"triangles": 0}
    T = np.concatenate(T)
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    n = n / np.maximum(2 * area, 1e-12)[:, None]
    steep = (np.abs(n[:, 2]) < 0.5) & (area > WALL_MIN)
    idx = np.flatnonzero(steep)
    C = T[idx].mean(1)
    tree = cKDTree(C)
    pr = tree.query_pairs(WALL_R, output_type="ndarray")
    keep = []
    for k in range(0, len(pr), 1000000):
        q = pr[k:k + 1000000]
        ia, ib = idx[q[:, 0]], idx[q[:, 1]]
        ok = (np.einsum("ij,ij->i", n[ia], n[ib]) > 0.95) & \
             (np.abs(np.einsum("ij,ij->i", C[q[:, 1]] - C[q[:, 0]], n[ia])) < WALL_D)
        q, ia, ib = q[ok], ia[ok], ib[ok]
        # not two triangles of one face: the two share no corner
        shared = (np.abs(T[ia][:, :, None, :] - T[ib][:, None, :, :]).max(-1) < 1e-3).any(2).sum(1)
        keep.append(q[shared == 0])
    pr = np.concatenate(keep) if keep else np.zeros((0, 2), int)
    dup = np.zeros(len(idx), bool)
    dup[pr[:, 1]] = True
    pairs = Counter()
    first = {}
    for a_, b_ in pr:
        first.setdefault(b_, a_)
    for b_, a_ in first.items():
        pairs[" + ".join(sorted((owner[idx[a_]].split("|")[0], owner[idx[b_]].split("|")[0])))] += float(area[idx[b_]])
    cells = Counter(tuple((np.floor(C[dup, :2] / 50.0) * 50).astype(int).tolist()[k]) for k in range(int(dup.sum())))
    return {"steep_triangles": int(len(idx)), "steep_m2": round(float(area[idx].sum())),
            "doubled_triangles": int(dup.sum()), "doubled_m2": round(float(area[idx][dup].sum())),
            "by_materials_m2": {k: round(v) for k, v in pairs.most_common()},
            "worst_50m_cells": [[x, y, c] for (x, y), c in cells.most_common(40)]}


def scan(src):
    f = Files(src)
    objs, items = statics(f), forest(f)
    tris = world_tris(f, objs, lambda m: bool(SIGN_MAT.match(m) or WALL_MAT.match(m)))
    return {"objects": same_objects(objs, items), "guard_rails": rail_doubles(items),
            "signs": sign_doubles(plates(tris)), "walls": wall_doubles(tris)}


if __name__ == "__main__":
    r = scan(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        json.dump(r, open(out, "w"), indent=1)

    def short(d):
        return {k: (v if not isinstance(v, list) else f"[{len(v)}]") for k, v in d.items()}
    for k, v in r.items():
        print(k, json.dumps(short(v)))
