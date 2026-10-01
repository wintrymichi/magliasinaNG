"""Bounding boxes of BeamNG vanilla DAE shapes (read straight from the game zips).

Used to scale vegetation and props to measured sizes. Only the highest LOD /
visible geometry is considered (collision and LOD<-1 nodes are ignored roughly by
taking all <float_array> POSITION data of the file, which is what the engine
bounds use anyway)."""
import json, os, re, zipfile
import numpy as np
from config import BEAMNG_GAME, WORK

ZIPS = {
    "/assets/": os.path.join(BEAMNG_GAME, "content", "assets", "meshes.zip"),
    "/art/": os.path.join(BEAMNG_GAME, "content", "art_shapes.zip"),
}


def zip_for(path):
    p = path.lstrip("/")
    if p.startswith("levels/"):
        lvl = p.split("/")[1]
        return os.path.join(BEAMNG_GAME, "content", "levels", f"{lvl}.zip")
    if p.startswith("assets/meshes/"):
        return ZIPS["/assets/"]
    if p.startswith("art/"):
        return ZIPS["/art/"]
    return None


def dae_bounds(path):
    zp = zip_for(path)
    z = zipfile.ZipFile(zp)
    name = path.lstrip("/")
    names = {n.lower(): n for n in z.namelist()}
    t = z.read(names[name.lower()]).decode("utf-8", "ignore")
    up = re.search(r"<up_axis>(\w+)</up_axis>", t)
    unit = re.search(r"<unit[^>]*meter=[\"']([0-9.eE+-]+)[\"']", t)
    scale = float(unit.group(1)) if unit else 1.0
    pts = []
    # only POSITION arrays (ids usually end with -positions-array / -pa)
    for m in re.finditer(r"<float_array[^>]*id=[\"']([^\"']+)[\"'][^>]*>([^<]+)</float_array>", t):
        fid = m.group(1).lower()
        if "position" not in fid:
            continue
        a = np.array(m.group(2).split(), float)
        if a.size % 3 == 0 and a.size:
            pts.append(a.reshape(-1, 3))
    P = np.concatenate(pts) * scale
    if up and up.group(1).upper() == "Y_UP":
        P = P[:, [0, 2, 1]]
    return P.min(0).tolist(), P.max(0).tolist()


def cached(paths):
    f = os.path.join(WORK, "asset_bounds.json")
    d = json.load(open(f)) if os.path.exists(f) else {}
    for p in paths:
        if p not in d:
            try:
                d[p] = dae_bounds(p)
            except Exception as e:
                d[p] = None
                print("bounds failed", p, e)
    json.dump(d, open(f, "w"), indent=1)
    return d


def register(path, mn, mx):
    """Bounds of a shape drawn by the pipeline (v2.4: palms.py), into the cache."""
    f = os.path.join(WORK, "asset_bounds.json")
    d = json.load(open(f)) if os.path.exists(f) else {}
    d[path] = [list(map(float, mn)), list(map(float, mx))]
    json.dump(d, open(f, "w"), indent=1)


def dae_material_names(path):
    """Material names referenced by a vanilla DAE (the names BeamNG maps to Material 'mapTo')."""
    z = zipfile.ZipFile(zip_for(path))
    names = {n.lower(): n for n in z.namelist()}
    t = z.read(names[path.lstrip("/").lower()]).decode("utf-8", "ignore")
    return sorted(set(re.findall(r"<material[^>]*name=[\"']([^\"']+)[\"']", t)))
