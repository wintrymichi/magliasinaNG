"""Renders of the landmarks without the build (v3.0.40): a small level of one site of the development pack
(landmarks_pack.py) with its buildings drawn by buildings_mesh.build, its bare ground and orthophoto, shot by
render3d.py from around the site and from the street; --before draws them as v3.0 did (no landmarks.py).

    python landmarks_preview.py PACK_DIR SITE_ID OUT_DIR [--before] [--views N]
"""
import gzip, json, math, os, pickle, sys, tempfile
import numpy as np


def setup(pack, root):
    """WORK of a site: buildings.pkl, dtm05.npz, ortho.tif; returns the bounds and the ground grid."""
    from geo import Grid, save_geotiff
    work = os.path.join(root, "work")
    os.makedirs(work, exist_ok=True)
    pickle.dump(pack["buildings"], open(os.path.join(work, "buildings.pkl"), "wb"))
    x0, y0, x1, y1 = pack["bounds"]
    res = pack.get("dtm_res", 1.0)
    dtm = pack["dtm"].astype(np.float64) / 100.0 + pack["dtm_z0"]
    Grid(dtm.astype(np.float32), x0, y1, res).save(os.path.join(work, "dtm05.npz"))
    if pack.get("ortho") is not None:
        save_geotiff(os.path.join(work, "ortho.tif"), pack["ortho"], x0, y1, 1.0)
    return (x0, y0, x1, y1), dtm, res


def level(pack, root, before=False):
    """Build the buildings of the site into a level folder with a terrain under them."""
    import bng
    import buildings_mesh
    import facades
    import landmarks
    from config import LEVEL_NAME
    lv = os.path.join(root, "levels", LEVEL_NAME)
    os.makedirs(lv, exist_ok=True)
    gwr, parts, by_egid = pack["gwr"], pack["parts"], pack["by_egid"]
    import shapely
    facades.gwr_join = lambda blds, fps: gwr
    facades.mu_parts = lambda blds, fps: {k: [(shapely.from_wkb(p), e) for p, e in v] for k, v in parts.items()}
    facades.gwr_by_egid = lambda: by_egid
    import vanilla
    vanilla.have_game = lambda: True
    if before:
        landmarks.apply = lambda style, b, fp, measured=None: style
    tiles = buildings_mesh.build(lv, LEVEL_NAME, ways=None, net=None)
    scene = bng.Scene()
    for shape, origin, ntri in tiles:
        scene.add("MissionGroup/buildings", bng.tsstatic(shape, origin, collision=False))
    # the terrain: the ground of the site on a square grid of 1 m, row 0 south
    x0, y0, x1, y1 = pack["bounds"]
    dtm = pack["dtm"].astype(np.float64) / 100.0 + pack["dtm_z0"]
    n = max(dtm.shape)
    H = np.full((n, n), float(dtm.min()))
    H[:dtm.shape[0], :dtm.shape[1]] = dtm[::-1]
    z0 = float(H.min()) - 5.0
    maxh = float(H.max() - z0) + 10.0
    bng.write_ter(os.path.join(lv, "theTerrain.ter"), H, z0, maxh, np.zeros((n, n), np.uint8), ["grass"])
    scene.add("MissionGroup/level_objects/terrain", {"class": "TerrainBlock", "name": "theTerrain",
                                                     "position": [x0, y1 - (dtm.shape[0] - 1), z0], "maxHeight": maxh,
                                                     "squareSize": 1.0, "terrainFile": f"/levels/{LEVEL_NAME}/theTerrain.ter"})
    scene.write(lv)
    return lv


def views(pack, k=4):
    """Cameras round the site: k orbits at 45 degrees apart from the best side, and one from the ground."""
    from render3d import Camera
    blds = [b for b in pack["buildings"] if b["uuid"] in pack["members"]] or pack["buildings"]
    P = np.concatenate([np.concatenate([b["walls"], b["roofs"]]).reshape(-1, 3) for b in blds])
    lo, hi = P.min(0), P.max(0)
    c = 0.5 * (lo + hi)
    size = float(max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))
    tz = lo[2] + 0.45 * (hi[2] - lo[2])
    out = []
    for j in range(k):
        az = 225 + j * 90
        out.append((f"orbit{j}", Camera.orbit(c[0], c[1], tz, max(28.0, 2.1 * size), az, 18)))
    # from the ground, 25 m away, south-west
    gz = lo[2] + 1.6
    for j, az in enumerate((210, 40)):
        a = math.radians(az)
        d = max(22.0, 1.4 * size)
        out.append((f"street{j}", Camera.look((c[0] + d * math.sin(a), c[1] + d * math.cos(a), gz),
                                              (c[0], c[1], lo[2] + 0.55 * (hi[2] - lo[2])), fov=60)))
    return out


def main(pack_dir, site, out, before=False, k=4):
    pack = pickle.load(gzip.open(os.path.join(pack_dir, "sites", site + ".pkl.gz")))
    root = tempfile.mkdtemp(prefix="lm_")
    os.environ["MAGLIASO_ROOT"] = root
    import config
    config.WORK = os.path.join(root, "work")
    for mod in ("buildings_mesh", "facades", "render3d", "geo"):
        if mod in sys.modules:
            setattr(sys.modules[mod], "WORK", config.WORK)
    setup(pack, root)
    import buildings_mesh, facades, render3d
    for m in (buildings_mesh, facades, render3d):
        m.WORK = config.WORK
    three = os.environ.get("THREE_JS")
    if three:
        import shutil
        shutil.copy(three, render3d.THREE)
    lv = level(pack, root, before)
    os.makedirs(out, exist_ok=True)
    tag = "prima" if before else "dopo"
    with render3d.Renderer(lv, W=1280, H=860, textured=True) as r:
        for name, cam in views(pack, k):
            f = os.path.join(out, f"{site}_{name}_{tag}.jpg")
            r.shot(cam, f, trees=False, far=900.0)
            print(f, flush=True)
    stats = json.load(open(os.path.join(config.WORK, "buildings_stats.json")))
    print({k: stats.get(k) for k in ("landmarks", "openings", "use")})


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], a[2], before="--before" in sys.argv,
         k=int(sys.argv[sys.argv.index("--views") + 1]) if "--views" in sys.argv else 4)
