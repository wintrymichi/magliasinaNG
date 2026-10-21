"""The 3D scene of a zone for the analysis of the street photos (v3.0.40): the buildings of swissBUILDINGS3D, the
swissALTI3D (bare ground) and swissSURFACE3D (surface) 0.5 m grids around them and the Copernicus GLO-30 terrain for
the far horizon. A zone is a local rectangle; its scene reaches PAD m beyond it (what the photos taken in the zone
see). The data come from the build (WORK/buildings.pkl, dtm05, dsm05) where it exists, otherwise only the tiles of
the zone are downloaded (the same folders as download_swisstopo.py).

    build(rect) -> dict(dtm, dsm, bid, x_min, y_max, res, far, far_x_min, far_y_max, far_res, buildings)
    python street_scene.py x0 y0 x1 y1 out.npz
"""
import glob, gzip, os, pickle, sys
import numpy as np
import shapely
from config import DATA, WORK, local_to_lv95, lv95_to_local

PAD = 260.0                 # m of scene around the zone
RES = 0.5
FAR = 8000.0                # m of far terrain around the zone (horizon)
FAR_RES = 30.0


def lv95_bounds(rect, pad=0.0):
    x0, y0, x1, y1 = rect
    pts = [local_to_lv95(x, y) for x in (x0 - pad, x1 + pad) for y in (y0 - pad, y1 + pad)]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def km_tiles(e0, n0, e1, n1):
    return {f"{e}-{n}" for e in range(int(e0 // 1000), int(e1 // 1000) + 1) for n in range(int(n0 // 1000), int(n1 // 1000) + 1)}


def download(rect, pad=PAD):
    """The swisstopo tiles of the zone + pad and the Copernicus tiles (skipped when on disk)."""
    import download_swisstopo as ds
    from concurrent.futures import ThreadPoolExecutor
    e0, n0, e1, n1 = lv95_bounds(rect, pad)
    tiles = km_tiles(e0, n0, e1, n1)
    jobs, gdbs = [], []
    for coll, suffix, sub, keep in (("ch.swisstopo.swissalti3d", "_0.5_2056_5728.tif", "swissalti3d_05", tiles),
                                    ("ch.swisstopo.swisssurface3d-raster", "_0.5_2056_5728.tif", "dsm_05", tiles),
                                    ("ch.swisstopo.swissbuildings3d_3_0", ".gdb.zip", "buildings3d", None)):
        items = ds.latest_per_tile(ds.stac_items(coll, e0, n0, e1, n1))
        for tile, f in sorted(items.items()):
            if "-" not in tile or (keep is not None and tile not in keep):
                continue
            for name, a in f["assets"].items():
                if name.endswith(suffix):
                    jobs.append((a["href"], os.path.join(DATA, sub, name)))
                    if suffix.endswith(".gdb.zip"):
                        gdbs.append(os.path.join(DATA, sub, name))
    for lat in (45, 46):
        for lon in (8, 9):
            name = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"
            jobs.append((f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif",
                         os.path.join(DATA, "copdem30", name + ".tif")))
    with ThreadPoolExecutor(4) as ex:
        for dest, status in ex.map(lambda j: ds.fetch(*j), jobs):
            if status != "skip":
                print(" ", status, os.path.relpath(dest, DATA), flush=True)
    for g in gdbs:
        if os.path.exists(g):
            ds.unzip_gdb(g)
    return len(jobs)


def buildings(rect, pad=PAD):
    """The buildings (records of buildings.pkl) whose bounding box meets the zone + pad."""
    box = shapely.box(rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)
    pk = os.path.join(WORK, "buildings.pkl")
    if os.path.exists(pk):
        import buildings_mesh
        blds = buildings_mesh.load_buildings()
        return [b for b in blds if box.intersects(shapely.box(b["bbox"][0][0], b["bbox"][0][1], b["bbox"][1][0],
                                                               b["bbox"][1][1]))]
    import extract_buildings
    out = {}
    for g in sorted(glob.glob(os.path.join(DATA, "buildings3d", "unz", "*.gdb"))):
        for lname, key in (("Wall", "walls"), ("Roof", "roofs"), ("Floor", "floors")):
            for props, tris in extract_buildings.features(g, lname):
                if len(tris) == 0:
                    continue
                x, y = lv95_to_local(tris[..., 0], tris[..., 1])
                if not box.intersects(shapely.box(x.min(), y.min(), x.max(), y.max())):
                    continue
                tris = np.stack([x, y, tris[..., 2]], -1)
                uid = props["UUID"]
                b = out.setdefault(uid, dict(uuid=uid, egid=props["EGID"], kind=props["OBJEKTART"],
                                             name=props["NAME_KOMPLETT"], walls=[], roofs=[], floors=[],
                                             sheet=os.path.basename(g)))
                b[key].append(tris)
    blds = []
    for b in out.values():
        for k in ("walls", "roofs", "floors"):
            b[k] = np.concatenate(b[k], 0) if b[k] else np.zeros((0, 3, 3))
        allp = np.concatenate([b["walls"], b["roofs"], b["floors"]], 0).reshape(-1, 3)
        b["bbox"] = [allp.min(0).tolist(), allp.max(0).tolist()]
        blds.append(b)
    return blds


def plan(b):
    """The plan of a building as the photos see it from the street: its roofs (eaves overhang included), else its
    floors, else the hull of its walls."""
    for key in ("roofs", "floors"):
        t = b.get(key)
        if t is not None and len(t):
            polys = [q for q in shapely.polygons(t[:, :, :2]) if q.is_valid and q.area > 1e-4]
            if polys:
                return shapely.union_all(polys)
    return shapely.MultiPoint(b["walls"].reshape(-1, 3)[:, :2]).convex_hull


def grids(rect, pad=PAD):
    """(dtm, dsm, x_min, y_max) on the 0.5 m grid of the zone + pad."""
    x0, y0 = np.floor((rect[0] - pad) / RES) * RES, np.floor((rect[1] - pad) / RES) * RES
    x1, y1 = np.ceil((rect[2] + pad) / RES) * RES, np.ceil((rect[3] + pad) / RES) * RES
    if os.path.exists(os.path.join(WORK, "dtm05.npy")) or os.path.exists(os.path.join(WORK, "dtm05.npz")):
        from geo import Grid
        out = []
        for name in ("dtm05.npz", "dsm05.npz"):
            g = Grid.load(os.path.join(WORK, name))
            sub, r0, c0 = g.window(x0, y0, x1, y1)
            if abs(sub.x_min - x0) < 1e-6 and abs(sub.y_max - y1) < 1e-6 and sub.a.shape == (round((y1 - y0) / RES), round((x1 - x0) / RES)):
                out.append(np.asarray(sub.a, np.float32))
        if len(out) == 2:
            return out[0], out[1], x0, y1
    from geo import mosaic
    dtm = mosaic("swissalti3d_05/*.tif", x0, y0, x1, y1, RES)[0]
    dsm = mosaic("dsm_05/*.tif", x0, y0, x1, y1, RES)[0]
    dsm = np.where(np.isfinite(dsm), dsm, dtm)
    return dtm.astype(np.float32), np.maximum(dsm, dtm).astype(np.float32), x0, y1


def far_terrain(rect):
    """Copernicus GLO-30 (a surface model: the forest on the ridges is in it) around the zone, FAR_RES m."""
    from geo import mosaic
    cx, cy = 0.5 * (rect[0] + rect[2]), 0.5 * (rect[1] + rect[3])
    x0, y0 = np.floor((cx - FAR) / FAR_RES) * FAR_RES, np.floor((cy - FAR) / FAR_RES) * FAR_RES
    x1, y1 = x0 + 2 * FAR, y0 + 2 * FAR
    g = mosaic("copdem30/*.tif", x0, y0, x1, y1, FAR_RES, src_crs="EPSG:4326")[0]
    g = np.where(np.isfinite(g), g, np.nanmin(g) if np.isfinite(g).any() else 0.0).astype(np.float32)
    return g, x0, y1


def rasterize_buildings(blds, shape, x_min, y_max):
    """Index of the building over every cell of the grid (-1: none)."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    tr = from_origin(x_min, y_max, RES, RES)
    shapes = []
    for i, b in enumerate(blds):
        g = plan(b)
        if not g.is_empty:
            shapes.append((g, i))
    if not shapes:
        return np.full(shape, -1, np.int32)
    return rasterize(shapes, out_shape=shape, transform=tr, fill=-1, dtype="int32", all_touched=False)


def build(rect, pad=PAD, fetch=True):
    if fetch:
        download(rect, pad)
    blds = buildings(rect, pad)
    dtm, dsm, x_min, y_max = grids(rect, pad)
    bid = rasterize_buildings(blds, dtm.shape, x_min, y_max)
    far, fx, fy = far_terrain(rect)
    print("scene", rect, "buildings", len(blds), "grid", dtm.shape, flush=True)
    return dict(dtm=dtm, dsm=dsm, bid=bid, x_min=x_min, y_max=y_max, res=RES, far=far, far_x_min=fx, far_y_max=fy,
                far_res=FAR_RES, buildings=blds, rect=list(rect))


def save(sc, path):
    """npz of the grids (heights as cm: the ground over its lowest point, the surface over the ground) + a gzip
    pickle of the buildings next to it."""
    base = float(np.floor(np.nanmin(sc["dtm"])))
    np.savez_compressed(path, dtm_cm=np.clip(np.rint((sc["dtm"] - base) * 100), 0, 65535).astype(np.uint16), dtm_base=base,
                        dsm_cm=np.clip(np.rint((sc["dsm"] - sc["dtm"]) * 100), 0, 65535).astype(np.uint16),
                        bid=sc["bid"], x_min=sc["x_min"], y_max=sc["y_max"], res=sc["res"], far=sc["far"],
                        far_x_min=sc["far_x_min"], far_y_max=sc["far_y_max"], far_res=sc["far_res"], rect=np.array(sc["rect"]))
    keep = ("uuid", "egid", "kind", "name", "walls", "roofs", "floors", "bbox")
    with gzip.open(path.replace(".npz", "_buildings.pkl.gz"), "wb") as f:
        pickle.dump([{k: b[k] for k in keep if k in b} for b in sc["buildings"]], f, protocol=4)


def load(path):
    d = np.load(path)
    sc = {k: d[k] for k in d.files}
    sc["dtm"] = float(sc.pop("dtm_base")) + sc.pop("dtm_cm").astype(np.float32) / 100.0
    sc["dsm"] = sc["dtm"] + sc.pop("dsm_cm").astype(np.float32) / 100.0
    for k in ("x_min", "y_max", "res", "far_x_min", "far_y_max", "far_res"):
        sc[k] = float(sc[k])
    with gzip.open(path.replace(".npz", "_buildings.pkl.gz"), "rb") as f:
        sc["buildings"] = pickle.load(f)
    return sc


ALLEY = 2.0                   # m from a building: the cells of the surface model there as high as its roof
ALLEY_DROP = 2.0              # (within this many m) are its eaves or the smoothing of the model over a narrow alley


def open_alleys(dsm, dtm, bid, res=RES):
    """The surface model with the cells next to a building that stand about as high as its roof (eaves over an
    alley, the 0.5 m model smoothed over a passage two or three metres wide) brought down to the ground: a camera in
    the alley sees the walls, not a roof over its head."""
    from scipy.ndimage import distance_transform_edt
    out = dsm.copy()
    if not (bid >= 0).any():
        return out
    dist, (ri, ci) = distance_transform_edt(bid < 0, return_indices=True)
    near = (bid < 0) & (dist * res <= ALLEY) & (dsm - dtm > 1.2)
    roof = dsm[ri, ci]
    lid = near & (dsm >= roof - ALLEY_DROP)
    out[lid] = dtm[lid]
    return out


def scene_of(sc):
    """The street_render.Scene of a scene dict."""
    import street_render
    return street_render.Scene(open_alleys(sc["dsm"], sc["dtm"], sc["bid"], sc["res"]), sc["dtm"], sc["bid"],
                               sc["x_min"], sc["y_max"], sc["res"],
                               far=(sc["far"], sc["far_x_min"], sc["far_y_max"], sc["far_res"]))


if __name__ == "__main__":
    r = [float(v) for v in sys.argv[1:5]]
    save(build(r), sys.argv[5])
