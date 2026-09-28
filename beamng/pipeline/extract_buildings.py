"""Extract swissBUILDINGS3D 3.0 (LOD2 TIN walls/roofs/floors) into the local frame.

Output work/buildings.pkl: list of dicts
  uuid, egid, kind (OBJEKTART), name, walls/roofs/floors: (n,3,3) float arrays (local x,y,z),
  bbox, footprint centroid.
Only buildings whose bounding box meets the playable area (area.py) + MARGIN are kept.
The FileGDB is read with osgeo.ogr where the GDAL bindings are installed, otherwise with the
GDAL library bundled with pyogrio (ogr_tin.py).
"""
import glob, os, pickle
import numpy as np
import shapely
from config import DATA, WORK, lv95_to_local
import area

MARGIN = 100.0
FIELDS = ["UUID", "EGID", "OBJEKTART", "NAME_KOMPLETT"]


def tin_triangles(geom):
    tris = []
    for i in range(geom.GetGeometryCount()):
        t = geom.GetGeometryRef(i)            # Triangle
        ring = t.GetGeometryRef(0)
        pts = ring.GetPoints()
        if len(pts) >= 3:
            tris.append(pts[:3])
    return tris


def features(g, lname):
    """(fields, triangles (n, 3, 3) LV95) of a layer of a swissBUILDINGS3D FileGDB."""
    try:
        from osgeo import ogr
    except ImportError:
        from ogr_tin import read_tin_layer
        yield from read_tin_layer(g, lname, FIELDS)
        return
    ogr.UseExceptions()
    ds = ogr.Open(g)
    for f in ds.GetLayerByName(lname):
        geom = f.GetGeometryRef()
        if geom is not None:
            yield {k: f.GetField(k) for k in FIELDS}, np.array(tin_triangles(geom), float).reshape(-1, 3, 3)


def main():
    gdbs = sorted(glob.glob(os.path.join(DATA, "buildings3d", "unz", "*.gdb")))
    keep_area = area.polygon().buffer(MARGIN)
    shapely.prepare(keep_area)
    blds = {}
    for g in gdbs:
        for lname, key in (("Wall", "walls"), ("Roof", "roofs"), ("Floor", "floors")):
            for props, tris in features(g, lname):
                if len(tris) == 0:
                    continue
                x, y = lv95_to_local(tris[..., 0], tris[..., 1])
                tris = np.stack([x, y, tris[..., 2]], -1)
                if not keep_area.intersects(shapely.box(tris[..., 0].min(), tris[..., 1].min(),
                                                        tris[..., 0].max(), tris[..., 1].max())):
                    continue
                uid = props["UUID"]
                b = blds.setdefault(uid, dict(uuid=uid, egid=props["EGID"], kind=props["OBJEKTART"],
                                              name=props["NAME_KOMPLETT"], walls=[], roofs=[], floors=[],
                                              sheet=os.path.basename(g)))
                b[key].append(tris)
        print(g, len(blds), flush=True)
    out = []
    for b in blds.values():
        for k in ("walls", "roofs", "floors"):
            b[k] = np.concatenate(b[k], 0) if b[k] else np.zeros((0, 3, 3))
        allp = np.concatenate([b["walls"], b["roofs"], b["floors"]], 0).reshape(-1, 3)
        b["bbox"] = [allp.min(0).tolist(), allp.max(0).tolist()]
        out.append(b)
    kinds = {}
    for b in out:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    print(len(out), "buildings in the area;", kinds)
    pickle.dump(out, open(os.path.join(WORK, "buildings.pkl"), "wb"))


if __name__ == "__main__":
    main()
