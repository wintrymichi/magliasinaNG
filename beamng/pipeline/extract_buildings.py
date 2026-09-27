"""Extract swissBUILDINGS3D 3.0 (LOD2 TIN walls/roofs/floors) into the local frame.

Output work/buildings.pkl: list of dicts
  uuid, egid, kind (OBJEKTART), name, walls/roofs/floors: (n,3,3) float arrays (local x,y,z),
  bbox, footprint centroid.
Only buildings whose bounding box intersects the terrain square are kept.
"""
import glob, os, pickle
import numpy as np
from osgeo import ogr
from config import DATA, WORK, TER_HALF, lv95_to_local

ogr.UseExceptions()


def tin_triangles(geom):
    tris = []
    for i in range(geom.GetGeometryCount()):
        t = geom.GetGeometryRef(i)            # Triangle
        ring = t.GetGeometryRef(0)
        pts = ring.GetPoints()
        if len(pts) >= 3:
            tris.append(pts[:3])
    return tris


def main():
    gdbs = sorted(glob.glob(os.path.join(DATA, "buildings3d", "unz", "*.gdb")))
    blds = {}
    for g in gdbs:
        ds = ogr.Open(g)
        for lname, key in (("Wall", "walls"), ("Roof", "roofs"), ("Floor", "floors")):
            lay = ds.GetLayerByName(lname)
            for f in lay:
                geom = f.GetGeometryRef()
                if geom is None:
                    continue
                tris = np.array(tin_triangles(geom), float)
                if len(tris) == 0:
                    continue
                x, y = lv95_to_local(tris[..., 0], tris[..., 1])
                tris = np.stack([x, y, tris[..., 2]], -1)
                if (tris[..., 0].max() < -TER_HALF or tris[..., 0].min() > TER_HALF or
                        tris[..., 1].max() < -TER_HALF or tris[..., 1].min() > TER_HALF):
                    continue
                uid = f.GetField("UUID")
                b = blds.setdefault(uid, dict(uuid=uid, egid=f.GetField("EGID"), kind=f.GetField("OBJEKTART"),
                                              name=f.GetField("NAME_KOMPLETT"), walls=[], roofs=[], floors=[],
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
    print(len(out), "buildings in the terrain square;", kinds)
    pickle.dump(out, open(os.path.join(WORK, "buildings.pkl"), "wb"))


if __name__ == "__main__":
    main()
