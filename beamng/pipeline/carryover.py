"""Objects of the Street View route taken over from the released level (config.REFERENCE_ZIP).

The road paint, the street lights, poles, signs and furniture of the original route come from the
panoramas (markings*.py, lamps.py, poles.py, objects.py, props.py). A build without the panoramas and
their intermediate results (road_strip.npz, the sign plates of work/signs; a cloud build of v2.0)
takes them from the released level and sets them on the new surfaces as patch_release.py does:
- road paint: on the new road meshes, at the height it had over the old ones (1.5-4 cm);
- objects: moved up or down with the ground under them (the higher of road and terrain, old and new).
Used by build_level.stage_markings / stage_props when their inputs are missing.
"""
import json, os, shutil, tempfile, zipfile
import numpy as np
import bng
import patch_release as pr
import road_mesh
from config import LEVEL_NAME, REFERENCE_ZIP

LEVEL = f"levels/{LEVEL_NAME}"
FILES = ("art/road/", "art/shapes/roads/markings.dae", "art/shapes/props/", "art/shapes/signs/")
GROUPS = ("main/MissionGroup/roads/markings/", "main/MissionGroup/props/")
NEEDED = ("theTerrain.ter", "main/MissionGroup/level_objects/terrain/", "main/MissionGroup/roads/surfaces/",
          "art/shapes/roads/road_")


class Reference:
    """The released level unpacked (only what is needed) with its ground: max(road meshes, terrain)."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="magliaso_ref_")
        with zipfile.ZipFile(REFERENCE_ZIP) as z:
            for n in z.namelist():
                rel = n[len(LEVEL) + 1:]
                if n.startswith(LEVEL + "/") and rel.startswith(FILES + GROUPS + NEEDED):
                    z.extract(n, self.dir)
        self.lv = os.path.join(self.dir, LEVEL)
        self.ter = pr.Terrain(self.lv)
        pieces = pr.road_pieces(self.lv)
        self.road = road_mesh.MeshSampler(np.concatenate([p["tri"] for p in pieces]))

    def ground(self, x, y):
        zt = self.ter.sample(x, y)
        zr = self.road(x, y)
        return np.where(np.isfinite(zr), np.maximum(zr, zt), zt)

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def items_of(lv, prefix):
    """(group path, object) of every non-group object in the items files under `prefix`."""
    out = []
    base = os.path.join(lv, *prefix.rstrip("/").split("/"))
    for dp, _, fs in os.walk(base):
        if "items.level.json" not in fs:
            continue
        rel = os.path.relpath(dp, os.path.join(lv, "main")).replace(os.sep, "/")
        for o in pr.items(os.path.join(dp, "items.level.json")):
            if o.get("class") == "SimGroup":
                continue
            o = dict(o)
            o.pop("__parent", None)
            out.append((rel, o))
    return out


def copy_files(ref, level_dir, prefix):
    src = os.path.join(ref.lv, *prefix.rstrip("/").split("/"))
    dst = os.path.join(level_dir, *prefix.rstrip("/").split("/"))
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)


def markings(level_dir, scene, new_road, new_ground, ref=None):
    """Road paint of the released level on the new road meshes."""
    own = ref is None
    ref = ref or Reference()
    try:
        copy_files(ref, level_dir, "art/road/")
        copy_files(ref, level_dir, "art/shapes/roads/markings.dae")
        mk = os.path.join(level_dir, "art", "shapes", "roads", "markings.dae")

        def on_road(V):
            lift = np.clip(np.nan_to_num(V[:, 2] - ref.road(V[:, 0], V[:, 1]), nan=0.02), 0.015, 0.04)
            zn = new_road(V[:, 0], V[:, 1]) + lift
            zs = V[:, 2] + (new_ground(V[:, 0], V[:, 1]) - ref.ground(V[:, 0], V[:, 1]))
            return np.column_stack([V[:, :2], np.where(np.isfinite(zn), zn, zs)])
        pr.rewrite_dae(mk, "markings", (0, 0, 0), on_road)
        n = 0
        for grp, o in items_of(ref.lv, "main/MissionGroup/roads/markings/"):
            scene.add(grp, o)
            n += 1
        print("road paint taken over from the reference level:", n, "objects")
    finally:
        if own:
            ref.close()


def props(level_dir, scene, new_ground, ref=None):
    """Street lights, poles, signs and furniture of the released level on the new ground."""
    own = ref is None
    ref = ref or Reference()
    try:
        for p in ("art/shapes/props/", "art/shapes/signs/"):
            copy_files(ref, level_dir, p)
        lift = lambda x, y: new_ground(x, y) - ref.ground(x, y)
        pp = os.path.join(level_dir, "art", "shapes", "props", "props_poles.dae")
        if os.path.exists(pp):
            pr.rewrite_dae(pp, "props", (0, 0, 0),
                           lambda V: V + np.column_stack([np.zeros((len(V), 2)), lift(V[:, 0], V[:, 1])]))
        n = 0
        for grp, o in items_of(ref.lv, "main/MissionGroup/props/"):
            if o.get("class") == "TSStatic" and "position" in o and o["position"] != [0.0, 0.0, 0.0]:
                x, y, z = o["position"]
                o["position"] = [x, y, z + float(lift([x], [y])[0])]
            scene.add(grp, o)
            n += 1
        print("route objects taken over from the reference level:", n)
    finally:
        if own:
            ref.close()
