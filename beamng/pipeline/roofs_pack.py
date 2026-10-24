"""Development pack of the floating roofs (v3.1): the buildings of swissBUILDINGS3D with roofs and no walls,
for the cloud session that writes the posts under them and cannot reach swisstopo.

Writes to the folder given:
  summary.json   every building of buildings.pkl: uuid, kind, name, faces of walls/roofs/floors, bbox
  wallless.npz   roofs and floors of the ones without walls (r_<i>, f_<i>), with the DTM and DSM 0.5 m
                 under them (dtm_<i>, dsm_<i>, window origin o_<i> = x_min, y_max) and their uuids
  ortho/<i>.jpg  SWISSIMAGE 10 cm (WMS) over each of them, 4 m around the roof
    python roofs_pack.py <out folder>
"""
import io, json, os, pickle, sys
import numpy as np
import shapely
import requests
from config import WORK, local_to_lv95
from geo import Grid

WMS = "https://wms.geo.admin.ch/"
PAD = 4.0


def ortho(x0, y0, x1, y1, path):
    e0, n0 = local_to_lv95(x0, y0)
    e1, n1 = local_to_lv95(x1, y1)
    w = int(min(max((x1 - x0) / 0.1, 64), 1200))
    h = int(min(max((y1 - y0) / 0.1, 64), 1200))
    p = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "ch.swisstopo.swissimage",
         "CRS": "EPSG:2056", "BBOX": f"{min(e0, e1)},{min(n0, n1)},{max(e0, e1)},{max(n0, n1)}",
         "WIDTH": w, "HEIGHT": h, "FORMAT": "image/jpeg", "STYLES": ""}
    for _ in range(3):
        try:
            r = requests.get(WMS, params=p, timeout=60)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                open(path, "wb").write(r.content)
                return True
        except Exception as e:
            print("retry", e, flush=True)
    return False


def main(out):
    os.makedirs(os.path.join(out, "ortho"), exist_ok=True)
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    added = os.path.join(WORK, "buildings_added.pkl")
    if os.path.exists(added):
        blds += pickle.load(open(added, "rb"))
    summ, kinds = [], {}
    for b in blds:
        summ.append({"uuid": b["uuid"], "kind": b["kind"], "name": b.get("name"), "w": len(b["walls"]),
                     "r": len(b["roofs"]), "f": len(b.get("floors", [])), "bbox": b["bbox"]})
        k = (b["kind"], len(b["walls"]) == 0)
        kinds[str(k)] = kinds.get(str(k), 0) + 1
    json.dump({"kinds": kinds, "buildings": summ}, open(os.path.join(out, "summary.json"), "w"))
    print(kinds, flush=True)
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    arrs, uu = {}, []
    import buildings_mesh
    fps = [buildings_mesh.footprint(b) for b in blds]
    ids = buildings_mesh.canopies(blds, fps)
    print("canopies", len(ids), flush=True)
    sel = [b for b in blds if b["uuid"] in ids]
    # the cadastral survey over each: buildings (LCSF edificio) and single objects (SOSF), share of the roof plan
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    layers = [("LCSF", "edificio")] + [("SOSF", k) for k in av.get("SOSF", {})]
    trees = {k: shapely.STRtree([g for g, _ in av[k[0]][k[1]]]) for k in layers if av.get(k[0], {}).get(k[1])}
    cover = []
    for b in sel:
        plan = buildings_mesh.roof_plan(b["roofs"])
        row = {}
        for k, t in trees.items():
            hit = t.query(plan, predicate="intersects")
            if len(hit):
                row["/".join(k)] = round(shapely.union_all(t.geometries.take(hit)).intersection(plan).area / plan.area, 3)
        cover.append(row)
    json.dump({"uuids": [b["uuid"] for b in sel], "cover": cover}, open(os.path.join(out, "cover.json"), "w"))
    for i, b in enumerate(sel):
        (x0, y0, _), (x1, y1, _) = b["bbox"]
        x0, y0, x1, y1 = x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD
        arrs[f"r_{i}"] = np.asarray(b["roofs"], np.float32)
        arrs[f"f_{i}"] = np.asarray(b.get("floors", np.zeros((0, 3, 3))), np.float32)
        for name, g in (("dtm", dtm), ("dsm", dsm)):
            sub, r0, c0 = g.window(x0, y0, x1, y1)
            arrs[f"{name}_{i}"] = np.asarray(sub.a, np.float32)
            arrs[f"o{name}_{i}"] = np.array([sub.x_min, sub.y_max, sub.res])
        uu.append(b["uuid"])
        if not os.path.exists(os.path.join(out, "ortho", f"{i}.jpg")):
            ortho(x0, y0, x1, y1, os.path.join(out, "ortho", f"{i}.jpg"))
        if i % 50 == 0:
            print(i, len(sel), flush=True)
    np.savez_compressed(os.path.join(out, "wallless.npz"), uuids=np.array(uu), **arrs)


if __name__ == "__main__":
    main(sys.argv[1])
