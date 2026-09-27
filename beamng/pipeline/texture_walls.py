"""Photo textures for the cadastral walls near the Strada Cantonale.

Same wall list and heights as walls.build (wall_geometry); every wall outline within
NEAR m of the road is textured as a ribbon (texturing.texture_ribbon, outward side) at
3 cm. Stored in work/wall_tex/<key>.npz with the ribbon mapping (L, v0, vlen).
"""
import json, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import shapely
from config import WORK

NEAR = 25.0
OUT = os.path.join(WORK, "wall_tex")


def job(args):
    key, ring, zb, zt = args
    f = os.path.join(OUT, f"{key}.npz")
    if os.path.exists(f):
        return key, "skip"
    import texturing
    from geo import Grid
    global _c, _d, _p
    if "_c" not in globals():
        _c = texturing.PanoCache(n=5)
        _d = Grid.load(os.path.join(WORK, "dsm05.npz"))
        _p = json.load(open(os.path.join(WORK, "poses.json")))
    img, (L, v0, vlen) = texturing.texture_ribbon(ring, zb, zt, -1, _p, _c, _d, tex=0.03)
    if img is None:
        np.savez_compressed(f, none=np.array(1))
        return key, "none"
    np.savez_compressed(f, img=img, L=L, v0=v0, vlen=vlen)
    return key, img.shape


def main():
    import walls
    os.makedirs(OUT, exist_ok=True)
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    road = shapely.LineString(rp["center"])
    todo = []
    for w in walls.wall_geometry():
        if w["poly"].distance(road) < NEAR:
            ring, zb, zt = walls.exterior_ribbon(w)
            todo.append((w["key"], ring, zb, zt))
    print("walls near the road:", len(todo), flush=True)
    todo.sort(key=lambda t: t[1][0] @ np.array([1.0, 0.3]))
    with ProcessPoolExecutor(6) as ex:
        for k, (key, st) in enumerate(ex.map(job, todo, chunksize=4)):
            if k % 40 == 0:
                print(k, key, st, flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
