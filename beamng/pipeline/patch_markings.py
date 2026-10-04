"""Put the redrawn road paint of the network (markings_clean.py) into a built level zip (v2.7),
without rebuilding the level.

The paint meshes of the network (art/shapes/roads/markings_net_*.dae and their objects in
MissionGroup/roads/markings) are built again by markings_net.build from the paint kept in the
repository (dati/network_markings.json.gz), cleaned by markings_clean.py, on the road meshes of the
zip: the carriageways for the width of the pedestrian crossings, every top face for the heights,
and the old paint as the height hint where a road passes under a bridge. The new shapes get the
detail size of optimize_level.py (v2.5). The paint of the Street View route (markings.dae) and
everything else is copied as it is (same entries, same dates: the game keeps its converted shapes).

Usage: python patch_markings.py <in.zip> <out.zip>
"""
import json, os, re, shutil, sys, tempfile, zipfile
import numpy as np
import markings_net
import optimize_level
from config import LEVEL_NAME

NET_SHAPE = re.compile(r"art/shapes/roads/markings_net_[-+]\d+_[-+]\d+\.dae$")


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def shape_tris(zi, lv, objs, keep=None):
    """{material: (k, 3, 3) world triangles} of the TSStatic shapes `objs` of the zip."""
    out = {}
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or not sn.startswith("/levels/") or keep is not None and not keep(sn):
            continue
        name = sn.lstrip("/")
        if name not in zi.NameToInfo:
            continue
        V, N, T, C, parts, _ = optimize_level.parse(zi.read(name).decode("utf-8"))
        Vw = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            out.setdefault(mat, []).append(Vw[idx[:, 0]].reshape(-1, 3, 3))
    return {m: np.concatenate(v) for m, v in out.items()}


def up_faces(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return t[n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5]


class Collector:
    def __init__(self):
        self.objs = []

    def add(self, path, obj):
        self.objs.append((path, obj))


def main(src, dst):
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    tops = np.concatenate([up_faces(t) for m, t in surf.items() if m in markings_net.ROAD_MATS])
    carriage = np.concatenate([up_faces(t) for m, t in surf.items() if m in markings_net.CARRIAGE_MATS])
    mk_items = f"{lv}/main/MissionGroup/roads/markings/items.level.json"
    mk = read_items(zi, mk_items)
    old_net = shape_tris(zi, lv, mk, keep=lambda sn: NET_SHAPE.search(sn) is not None)
    old_sv = shape_tris(zi, lv, mk, keep=lambda sn: NET_SHAPE.search(sn) is None)
    sv_pts = np.concatenate([t.reshape(-1, 3) for t in old_sv.values()]) if old_sv else np.zeros((0, 3))
    old_pts = np.concatenate([t.reshape(-1, 3) for t in list(old_net.values()) + list(old_sv.values())])
    # where faces overlap (a road under a bridge) the paint stays at the height it had
    from scipy.spatial import cKDTree
    kd = cKDTree(old_pts[::3, :2])
    hint = lambda P: old_pts[::3, 2][kd.query(np.asarray(P)[:, :2])[1]]
    print("road faces %d (carriageways %d), old paint vertices %d" % (len(tops), len(carriage), len(old_pts)))
    tmp = tempfile.mkdtemp(prefix="magliaso_mk_")
    try:
        col = Collector()
        markings_net.build(tmp, col, tops=tops, hint=hint, carriage_tops=carriage, painted=sv_pts[:, :2])
        new_files = {}
        for path, o in col.objs:
            rel = o["shapeName"].split(f"/levels/{LEVEL_NAME}/", 1)[1]
            text = open(os.path.join(tmp, *rel.split("/")), encoding="utf-8").read()
            out, _ = optimize_level.optimize_dae([(text, np.zeros(3))], rel.split("art/shapes/", 1)[1])
            new_files[f"{lv}/{rel}"] = (out or text).encode("utf-8")
        parent = next((o["__parent"] for o in mk if "__parent" in o), "markings")
        keep = [o for o in mk if NET_SHAPE.search(o.get("shapeName", "")) is None]
        for _, o in col.objs:
            o = dict(o)
            o["__parent"] = parent
            keep.append(o)
        items = ("\n".join(json.dumps(o, separators=(",", ":")) for o in keep) + "\n").encode("utf-8")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
            for i in zi.infolist():
                n = i.filename
                if NET_SHAPE.search(n):
                    continue
                data = items if n == mk_items else zi.read(i)
                zo.writestr(i, data, compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
        print("%s: %d network paint shapes (were %d)" % (dst, len(new_files),
                                                         sum(1 for n in zi.namelist() if NET_SHAPE.search(n))))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
