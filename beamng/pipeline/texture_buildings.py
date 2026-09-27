"""Photo textures for the facades of buildings near the Strada Cantonale.

For every swissBUILDINGS3D building whose footprint is within NEAR m of the road,
the wall triangles are grouped into planar facades (texturing.facade_groups) and each
facade that faces a panorama is textured by projection (texturing.texture_planar):
3 cm texels within 20 m of the road, 5 cm beyond. Results per building are stored in
work/facades/<uuid>.npz (images + mapping); the level builder packs them into atlases.
Also stores per-building colours: facade median (photo) and roof median (orthophoto,
roof footprint eroded 1.5 m to limit relief displacement).
"""
import json, os, pickle, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import shapely
from config import WORK

NEAR = 40.0
OUT = os.path.join(WORK, "facades")


def oriented(b):
    allp = np.concatenate([b["walls"].reshape(-1, 3), b["roofs"].reshape(-1, 3)])
    ctr = allp.mean(0)
    w = b["walls"].copy()
    if len(w):
        n = np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0])
        out = w.mean(1) - ctr; out[:, 2] = 0
        flip = (n * out).sum(1) < 0
        w[flip] = w[flip][:, ::-1]
    return w


def job(args):
    b, dist_road = args
    import texturing
    from geo import Grid
    f = os.path.join(OUT, f"{b['uuid'].strip('{}')}.npz")
    if os.path.exists(f):
        return b["uuid"], "skip"
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    global _cache, _dsm
    if "_cache" not in globals():
        _cache = texturing.PanoCache(n=5)
        _dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    walls = oriented(b)
    out = {}
    if len(walls):
        groups = texturing.facade_groups(walls)
        k = 0
        for idx, nrm, d0 in groups:
            tris = walls[idx]
            area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1).sum()
            if area < 2.0:
                continue
            tex = 0.03 if dist_road < 20 else 0.05
            res, (u0, ul, v0, vl, axis) = texturing.texture_planar(tris, nrm, poses, _cache, _dsm, tex=tex)
            if res is None:
                continue
            img, cov = res
            if cov < 0.08:
                continue
            out[f"img{k}"] = img
            out[f"idx{k}"] = idx
            out[f"map{k}"] = np.array([u0, ul, v0, vl, axis[0], axis[1], axis[2], cov])
            k += 1
        out["n"] = np.array(k)
    np.savez_compressed(f, **out)
    return b["uuid"], f"{out.get('n', 0)} facades"


def main():
    os.makedirs(OUT, exist_ok=True)
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    road = shapely.LineString(rp["center"])
    todo = []
    for b in blds:
        if len(b["walls"]) == 0:
            continue
        fp = shapely.MultiPoint(b["walls"].reshape(-1, 3)[:, :2]).convex_hull
        d = fp.distance(road)
        if d < NEAR:
            todo.append((b, float(d)))
    print("buildings near the road:", len(todo), flush=True)
    todo.sort(key=lambda t: np.array(t[0]["bbox"][0][:2]) @ np.array([1.0, 0.3]))    # spatial order (cache)
    with ProcessPoolExecutor(6) as ex:
        for k, (uid, st) in enumerate(ex.map(job, todo, chunksize=4)):
            if k % 20 == 0:
                print(k, uid, st, flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
