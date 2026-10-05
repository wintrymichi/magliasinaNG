"""Put the far trees (far_trees.py, v2.7) into a built level zip, without rebuilding the level.

The trees of trees.npz (work/trees.npz of the build, every tree measured in the area) that the
level lacks come back as far trees: those more than NEAR + MARGIN m from a road surface and
NEAR_PATH + MARGIN m from a path surface of the zip (nearer, vegetation.thin kept every tree and
canopy.py may have moved it), with no forest item of the zip within MATCH m (the trees thin() kept
in the bands, at their measured place). The road and path surfaces are the top faces of the road
meshes of the zip. The far models, their textures and materials go into art/shapes/trees, the items
into forest/far_*.forest4.json, their types into art/forest/managedItemData.json. Far trees of an
earlier run are replaced. Everything else is copied as it is (same entries, same dates: the game
keeps its converted shapes).

Usage: python patch_far_trees.py <in.zip> <out.zip> [trees.npz]
"""
import json, os, re, shutil, sys, tempfile, zipfile
import numpy as np
from scipy.spatial import cKDTree
import bng
import osm_surface
import vegetation
from config import LEVEL_NAME, WORK
from landcover import CODE
from patch_markings import read_items, shape_tris, up_faces

MARGIN = 3.0       # m beyond vegetation.NEAR / NEAR_PATH: the distances here are to the meshes, not the lines
MATCH = 1.0        # m: a measured tree with a forest item this close is in the level already
FAR_FILE = re.compile(r"/(forest/far_[a-z]+_[a-z]\.forest4\.json|art/shapes/trees/far_[^/]+)$")


def surface_points(zi, lv):
    """(road points, path points) (n, 2): vertices and centres of the top faces of the road meshes."""
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    road, path = [], []
    for m, t in surf.items():
        t = up_faces(t)
        if not len(t):
            continue
        P = np.concatenate([t.reshape(-1, 3), t.mean(1)])[:, :2]
        (path if m in osm_surface.PATH_MATS else road).append(P)
    cat = lambda L: np.unique(np.round(np.concatenate(L), 1), axis=0) if L else np.zeros((0, 2))
    return cat(road), cat(path)


def main(src, dst, trees_f=None):
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    t = np.load(trees_f or os.path.join(WORK, "trees.npz"))
    t = {k: t[k] for k in t.files}
    ok = t["lc"] != CODE["none"]
    t = {k: v[ok] for k, v in t.items()}
    road, path = surface_points(zi, lv)
    xy = np.column_stack([t["x"], t["y"]])
    d_road = cKDTree(road).query(xy)[0] if len(road) else np.full(len(xy), 1e9)
    d_path = cKDTree(path).query(xy)[0] if len(path) else np.full(len(xy), 1e9)
    have = []
    for n in zi.namelist():
        if n.startswith(f"{lv}/forest/") and n.endswith(".forest4.json") and not FAR_FILE.search(n):
            have += [o["pos"][:2] for o in read_items(zi, n)]
    d_have = cKDTree(np.array(have)).query(xy)[0] if have else np.full(len(xy), 1e9)
    cand = (d_road > vegetation.NEAR + MARGIN) & (d_path > vegetation.NEAR_PATH + MARGIN) & (d_have > MATCH)
    print("trees measured %d: road and path surfaces %d / %d points, forest items %d; far tree candidates %d"
          % (len(xy), len(road), len(path), len(have), int(cand.sum())))
    far = {k: v[cand] for k, v in t.items()}
    far["dist_path"] = d_path[cand]
    tmp = tempfile.mkdtemp(prefix="magliaso_far_")
    try:
        items = vegetation.far_items(far, tmp, LEVEL_NAME)
        md_name = f"{lv}/art/forest/managedItemData.json"
        managed = json.loads(zi.read(md_name)) if md_name in zi.NameToInfo else {}
        managed = {k: v for k, v in managed.items() if not k.startswith("far_")}
        new_files = {}
        for (name, p), lst in items.items():
            managed[name] = {"name": name, "internalName": name, "class": "TSForestItemData", "persistentId": bng.pid(),
                             "radius": 0.5, "shapeFile": p}
            lines = [json.dumps({"ctxid": 1, "pos": [round(float(px), 3), round(float(py), 3), round(float(pz), 3)],
                                 "rotationMatrix": [round(v, 5) for v in bng.rot_local_x_to(yaw)], "scale": round(float(s), 4), "type": name},
                                separators=(",", ":")) for (px, py, pz, yaw, s, _) in lst]
            new_files[f"{lv}/forest/{name}.forest4.json"] = ("\n".join(lines) + "\n").encode("utf-8")
        new_files[md_name] = json.dumps(managed, indent=1).encode("utf-8")
        sd = os.path.join(tmp, "art", "shapes", "trees")
        for f in sorted(os.listdir(sd)):
            new_files[f"{lv}/art/shapes/trees/{f}"] = open(os.path.join(sd, f), "rb").read()
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
            for i in zi.infolist():
                if i.filename in new_files or FAR_FILE.search(i.filename):
                    continue
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                ctype = zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED
                zo.writestr(n, data, compress_type=ctype)
        counts = {k[0]: len(v) for k, v in items.items()}
        print("%s: %d far trees %s" % (dst, sum(counts.values()), counts))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
