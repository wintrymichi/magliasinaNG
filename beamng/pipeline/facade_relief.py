"""v3.0: relief on the façades of the flat-roofed buildings (shops, offices, workshops, modern blocks).

Their walls were one flat plane of plaster from the plinth to the edge of the roof, the windows drawn on it: seen
from the road a supermarket or a workshop looked like a cardboard box (v3 screenshot 36, the Coop of Magliaso).
Along every edge of a flat roof that stands on a wall of the building (a wall top within EDGE_R m of it, at its
height within EDGE_DZ m: not where the roof meets a taller part of the building) it gets:
- a coping: a cap COPING_H m high from COPING_IN m over the roof to COPING_OUT m out of the wall, light concrete,
  with the underside of its overhang;
- a cornice: a band BAND_H m high, BAND_OUT m out of the wall, BAND_TOP m under the edge of the roof (in the
  strip the façades leave free above the upper windows: facades.EAVE_GAP), in a shade of the wall plaster.
Meshes in MissionGroup/buildings/relief, DETAIL_TILE m tiles, no collision.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish facade_relief
"""
import json, os, re, tempfile, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import optimize_level
from config import LEVEL_NAME
from markings_net import read_items

EDGE_R, EDGE_DZ = 0.45, 0.4
COPING_H, COPING_IN, COPING_OUT = 0.16, 0.30, 0.07
BAND_H, BAND_OUT, BAND_TOP = 0.18, 0.05, 0.38
MIN_EDGE = 0.8          # m: shorter roof edges get nothing
TILE = 512.0
D = "art/shapes/buildings/relief"
SHAPE = re.compile(r"art/shapes/buildings/relief/[^/]+$")
WALLS = ("bld_plaster", "bld_stone")


def materials():
    t = f"/levels/{LEVEL_NAME}/art/shapes/buildings"
    return [bng.material("mp_bld_coping", base_color=[0.72, 0.71, 0.68, 1], roughness=0.85, ground_type="CONCRETE"),
            bng.material("mp_bld_band", f"{t}/t_bld_plaster_b.color.png", base_color=[0.86, 0.85, 0.82, 1],
                         roughness=0.9, ground_type="CONCRETE")]


def quad(a, b, c, d, out):
    t = np.array([a, b, c, a, c, d], np.float64).reshape(2, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    flip = (n @ np.asarray(out, np.float64)) < 0
    t[flip] = t[flip][:, ::-1]
    return t


def bar(a, b, o, z0, z1, w_in, w_out, ext):
    """The faces of a bar along a-b (x, y), o its outward unit normal, from w_in m inside to w_out m outside,
    z0 to z1, ext m beyond both ends: top, outer face, underside (of the part outside), inner face."""
    u = (b - a) / max(np.linalg.norm(b - a), 1e-9)
    a, b = a - u * ext, b + u * ext
    ai, bi, ao, bo = a - o * w_in, b - o * w_in, a + o * w_out, b + o * w_out
    o3 = np.r_[o, 0.0]
    T = [quad([*ai, z1], [*bi, z1], [*bo, z1], [*ao, z1], (0, 0, 1)),
         quad([*ao, z0], [*bo, z0], [*bo, z1], [*ao, z1], o3),
         quad([*a, z0], [*b, z0], [*bo, z0], [*ao, z0], (0, 0, -1))]
    if w_in > 0:
        T.append(quad([*ai, z0], [*bi, z0], [*bi, z1], [*ai, z1], -o3))
    return np.concatenate(T)


def wall_tops(W, parts):
    pts = []
    for m, idx in parts:
        if m not in WALLS:
            continue
        t = W[idx[:, 0]].reshape(-1, 3, 3)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        vert = np.abs(n[:, 2]) < 0.2 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
        for tri in t[vert]:
            o = np.argsort(-tri[:, 2])
            a, b = tri[o[0]], tri[o[1]]
            k = max(int(np.linalg.norm(b[:2] - a[:2]) / 0.4), 1) if abs(a[2] - b[2]) < 0.3 else 0
            f = np.linspace(0, 1, k + 1)[:, None]
            pts.append(a + f * (b - a))
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def roof_edges(W, idx):
    """Boundary edges of the flat roof faces: (a (k, 3), b (k, 3), outward normals (k, 2))."""
    t = W[idx[:, 0]].reshape(-1, 3, 3)
    key = np.round(t.reshape(-1, 3) * 200).astype(np.int64)
    _, vid = np.unique(key, axis=0, return_inverse=True)
    tri = vid.reshape(-1, 3)
    E = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    own = np.tile(np.arange(len(tri)), 3)
    ia = np.repeat([0, 1, 2], len(tri))
    _, inv, cnt = np.unique(np.sort(E, 1), axis=0, return_inverse=True, return_counts=True)
    b = cnt[inv.ravel()] == 1
    f, i = own[b], ia[b]
    A, B = t[f, i], t[f, (i + 1) % 3]
    c = t[f].mean(1)
    d = B[:, :2] - A[:, :2]
    L = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    n = np.column_stack([d[:, 1], -d[:, 0]]) / L[:, None]
    away = (((A[:, :2] + B[:, :2]) / 2 - c[:, :2]) * n).sum(1) > 0     # pointing away from its face
    n *= np.where(away, 1.0, -1.0)[:, None]
    return A, B, n, L


def facade_relief_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    rep = {"buildings": 0, "edges": 0, "coping_m": 0.0, "edges_without_wall": 0}
    tiles = {}
    for o in read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        flat = [idx for m, idx in parts if m == "bld_roof_flat"]
        if not flat:
            continue
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        tops = wall_tops(W, parts)
        if not len(tops):
            continue
        tree = cKDTree(tops[:, :2])
        A, B, N, L = roof_edges(W, np.concatenate(flat))
        for a, b, n, l in zip(A, B, N, L):
            if l < MIN_EDGE or abs(a[2] - b[2]) > 0.3:
                continue
            m = (a + b) / 2
            near = tree.query_ball_point(m[:2], EDGE_R)
            if not any(abs(tops[j, 2] - m[2]) < EDGE_DZ for j in near):
                rep["edges_without_wall"] += 1
                continue
            z = max(a[2], b[2])
            cop = bar(a[:2], b[:2], n, z - 0.02, z + COPING_H, COPING_IN, COPING_OUT, COPING_OUT)
            band = bar(a[:2], b[:2], n, z - BAND_TOP - BAND_H, z - BAND_TOP, 0.0, BAND_OUT, BAND_OUT)
            key = tuple(np.floor(m[:2] / TILE).astype(int))
            tiles.setdefault(key, {"mp_bld_coping": [], "mp_bld_band": []})
            tiles[key]["mp_bld_coping"].append(cop)
            tiles[key]["mp_bld_band"].append(band)
            rep["edges"] += 1
            rep["coping_m"] += float(l)
        rep["buildings"] += 1
    files, objs = {}, []
    tri = 0
    with tempfile.TemporaryDirectory() as tmp:
        for (tx, ty), mats in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            for mat, lst in mats.items():
                if not lst:
                    continue
                Vt = np.concatenate(lst).reshape(-1, 3)
                uv = bng.box_uvs_soup(Vt, 3.0)
                mb.add(mat, Vt, uvs=uv, normals=bng.flat_normals_soup(Vt))
            rel = f"{D}/relief_{tx:+03d}_{ty:+03d}.dae"
            f = os.path.join(tmp, "s.dae")
            mb.write_dae(f, name=f"relief_{tx}_{ty}", origin=origin)
            files[f"{lv}/{rel}"] = open(f, "rb").read()
            tri += mb.triangle_count()
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False)
            ob["__parent"] = "relief"
            objs.append(ob)
    files[f"{lv}/{D}/relief.materials.json"] = json.dumps({m["name"]: m for m in materials()}, indent=1).encode()
    files[f"{lv}/main/MissionGroup/buildings/relief/items.level.json"] = \
        ("\n".join(json.dumps(o, separators=(",", ":")) for o in objs) + "\n").encode("utf-8")
    grp = f"{lv}/main/MissionGroup/buildings/items.level.json"
    rows = read_items(zi, grp)
    if not any(r.get("name") == "relief" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "relief", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "buildings"})
    files[grp] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in files or SHAPE.search(i.filename):
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep["coping_km"] = round(rep.pop("coping_m") / 1000, 1)
    rep["triangles"] = tri
    rep["seconds"] = round(time.time() - t0)
    print("facade relief:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    import sys
    facade_relief_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
