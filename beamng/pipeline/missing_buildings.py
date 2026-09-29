"""Buildings that swissBUILDINGS3D does not model, and swissBUILDINGS3D buildings that are gone (v2.2).

The cadastral survey (MU, 'edificio') is kept up to date by the municipalities; swissBUILDINGS3D is
derived from aerial surveys and leaves out many small buildings (garages, sheds, rustici under trees)
and the newest ones. Up to v2.1 the level had nothing where they stand: an empty patch of the terrain.
- Every MU building of at least MIN_AREA m2 that swissBUILDINGS3D covers for less than COVER of its
  area is checked on the surface model (swissSURFACE3D - swissALTI3D): where at least FILL of its
  footprint stands H_MIN m above the ground and the orthophoto there is not the green of a tree crown,
  the building is there. It is rebuilt from the footprint (walls from the ground up) with the heights
  of the surface model: a flat roof where the roof is level, a gable roof along the long side of the
  footprint otherwise (eaves and ridge from the low and high percentiles of the heights).
- Every swissBUILDINGS3D building (a house) with no MU building under it and nothing standing in the
  surface model (less than GONE of its footprint above H_MIN) is listed as gone and left out.
Output: WORK/buildings_added.pkl (same records as buildings.pkl) and dati/buildings_diff.json (every
case with its evidence, for the review); buildings_mesh.load_buildings() applies both.
    python missing_buildings.py
"""
import json, os, pickle
import numpy as np
import shapely
from config import WORK
from geo import Grid, ortho_sampler
import area

MIN_AREA = 12.0
COVER = 0.3
H_MIN = 1.8
FILL = 0.55
GONE = 0.15
NEW_YEAR = 2019          # built after the surface model (swissSURFACE3D 2020 / 2022 here)
DIFF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "buildings_diff.json")
ADDED = os.path.join(WORK, "buildings_added.pkl")


def sample_poly(poly, step=0.5):
    x0, y0, x1, y1 = poly.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    if not len(xs) or not len(ys):
        return np.zeros(0), np.zeros(0)
    X, Y = np.meshgrid(xs, ys)
    m = shapely.contains_xy(poly, X, Y)
    return X[m], Y[m]


def heights(poly, dsm, dtm):
    """Heights of the surface model above the ground inside the footprint (eroded 0.4 m)."""
    inner = poly.buffer(-0.4)
    if inner.is_empty or inner.area < 2.0:
        inner = poly
    x, y = sample_poly(inner)
    if not len(x):
        return None, None, None
    s, t = dsm.sample(x, y), dtm.sample(x, y)
    ok = np.isfinite(s) & np.isfinite(t)
    return x[ok], y[ok], (s - t)[ok]


def greenness(ortho, x, y):
    c = ortho(x, y).astype(np.float32)
    if c.ndim == 2 and c.shape[0] == 3 and c.shape[1] == len(x):
        c = c.T
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    return float(np.mean((g > r + 6) & (g > b + 6)))


def gable(poly, zb, z_eave, z_ridge):
    """Walls, roofs and floor (triangles) of a building on footprint `poly`: walls from zb, a gable roof
    along the long side of the footprint (ridge through the middle of its minimum rectangle)."""
    mrr = shapely.minimum_rotated_rectangle(poly)
    c = np.asarray(mrr.exterior.coords)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    if np.linalg.norm(e1) < np.linalg.norm(e2):
        e1, e2 = e2, e1
    ax = e1 / np.linalg.norm(e1)                          # along the ridge
    nrm = np.array([-ax[1], ax[0]])
    ctr = np.asarray(mrr.centroid.coords[0])
    half = 0.5 * np.linalg.norm(e2)
    flat = z_ridge - z_eave < 0.5

    def zroof(p):
        if flat:
            return np.full(len(p), z_ridge)
        d = np.abs((p - ctr) @ nrm)
        return z_ridge - (z_ridge - z_eave) * np.clip(d / max(half, 1e-6), 0, 1)
    poly = shapely.geometry.polygon.orient(poly.simplify(0.1), 1.0)
    ridge = shapely.LineString([ctr - ax * 1e4, ctr + ax * 1e4])
    walls = []
    for ring in [poly.exterior] + list(poly.interiors):
        pts = np.asarray(ring.coords)
        for a, b in zip(pts[:-1], pts[1:]):
            seg = shapely.LineString([a, b])
            q = [a]
            if not flat and seg.intersects(ridge):
                x = seg.intersection(ridge)
                if x.geom_type == "Point":
                    q.append(np.asarray(x.coords[0]))
            q.append(b)
            q = np.array(q)
            zt = zroof(q)
            for i in range(len(q) - 1):
                p0, p1 = q[i], q[i + 1]
                A, B = np.r_[p0, zb], np.r_[p1, zb]
                C, D = np.r_[p1, zt[i + 1]], np.r_[p0, zt[i]]
                walls += [[A, B, C], [A, C, D]]
    halves = [poly] if flat else [poly.intersection(shapely.Polygon([ctr - ax * 1e4, ctr + ax * 1e4,
                                                                     ctr + ax * 1e4 + nrm * 1e4, ctr - ax * 1e4 + nrm * 1e4])),
                                  poly.intersection(shapely.Polygon([ctr - ax * 1e4, ctr + ax * 1e4,
                                                                     ctr + ax * 1e4 - nrm * 1e4, ctr - ax * 1e4 - nrm * 1e4]))]
    roofs, floors = [], []
    for h in halves:
        for part in getattr(h, "geoms", [h]):
            if part.geom_type != "Polygon" or part.area < 0.05:
                continue
            for t in shapely.constrained_delaunay_triangles(part).geoms:
                p = np.asarray(t.exterior.coords)[:3]
                z = zroof(p)
                roofs.append(np.column_stack([p, z]))
                floors.append(np.column_stack([p, np.full(3, zb)]))
    return (np.array(walls, float).reshape(-1, 3, 3), np.array(roofs, float).reshape(-1, 3, 3),
            np.array(floors, float).reshape(-1, 3, 3))


def main():
    import buildings_mesh
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    mu = av["LCSF"].get("edificio", [])
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    fps = [buildings_mesh.footprint(b) for b in blds]
    tree = shapely.STRtree(fps)
    keep = area.polygon()
    shapely.prepare(keep)
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    ortho = ortho_sampler()
    import facades
    gwr = {}
    gf = os.path.join(WORK, "gwr.json")
    if os.path.exists(gf):
        gwr = {str(r["egid"]): r for r in json.load(open(gf))["buildings"] if "egid" in r}
    added, diff = [], {"added": [], "not_added": [], "gone": [], "kept": []}
    for k, (g, props) in enumerate(mu):
        if g.area < MIN_AREA or not keep.contains(g.representative_point()):
            continue
        hits = tree.query(g, predicate="intersects")
        cov = sum(shapely.intersection(g, fps[i]).area for i in hits) / g.area
        if cov >= COVER:
            continue
        if cov > 0.02:                                   # only the part not modelled
            g = g.difference(shapely.union_all([fps[i] for i in hits]).buffer(0.3))
            g = max(getattr(g, "geoms", [g]), key=lambda q: q.area) if not g.is_empty else g
            if g.is_empty or g.area < MIN_AREA or g.geom_type != "Polygon":
                continue
        x, y, h = heights(g, dsm, dtm)
        cx, cy = g.representative_point().coords[0]
        rec = {"x": round(cx, 1), "y": round(cy, 1), "area": round(g.area, 1), "egid": props.get("REA_EGID")}
        if h is None or len(h) < 8:
            diff["not_added"].append({**rec, "why": "no surface data"})
            continue
        fill = float(np.mean(h > H_MIN))
        green = greenness(ortho, x, y)
        p10, p90 = float(np.percentile(h, 10)), float(np.percentile(h, 90))
        rec.update(fill=round(fill, 2), green=round(green, 2), h50=round(float(np.median(h)), 1))
        gw = gwr.get(str(props.get("REA_EGID") or ""))
        year = facades.year_of(gw) if gw else None
        bx, by = np.asarray(g.exterior.coords)[:, 0], np.asarray(g.exterior.coords)[:, 1]
        zg = dtm.sample(bx, by)
        zb = float(np.nanmin(zg)) - 0.3
        g_ref = float(np.nanmedian(zg))
        # a low compact structure among trees (a garden house, a greenhouse, a shed): the 2 m orthophoto
        # mixes its roof with the crowns around; a crown is higher and uneven
        low_shed = fill >= 0.75 and p90 < 6.5 and p90 - p10 < 2.5
        new = fill < FILL and year is not None and year >= NEW_YEAR and g.area >= 25
        if new:                                            # built after the surface model: the register's floors
            fl = int(gw.get("gastw") or 2)
            z_eave = z_ridge = g_ref + 3.0 * fl + 0.4
            rec["why"] = "new building (register %d, %d floors)" % (year, fl)
        elif fill < FILL or (green > 0.45 and not low_shed) or p90 > 40:
            diff["not_added"].append({**rec, "why": "not standing in the surface model" if fill < FILL else
                                      ("tree crowns" if green > 0.45 else "implausible height")})
            continue
        else:
            top = h[h > H_MIN]
            z_ridge = g_ref + float(np.percentile(top, 97))
            z_eave = g_ref + float(np.percentile(top, 8))
            if z_ridge - z_eave < 0.8:                     # a level roof
                z_eave = z_ridge = g_ref + float(np.percentile(top, 60))
        z_eave = max(z_eave, g_ref + 2.2)
        z_ridge = max(z_ridge, z_eave)
        walls, roofs, floors = gable(g, zb, z_eave, z_ridge)
        if not len(walls) or not len(roofs):
            continue
        allp = np.concatenate([walls, roofs]).reshape(-1, 3)
        added.append({"uuid": f"MU-{k}", "egid": props.get("REA_EGID"), "kind": "Gebaeude Einzelhaus", "name": "",
                      "walls": walls, "roofs": roofs, "floors": floors, "sheet": "MU",
                      "bbox": [allp.min(0).tolist(), allp.max(0).tolist()]})
        diff["added"].append({**rec, "uuid": f"MU-{k}", "eave": round(z_eave - g_ref, 1), "ridge": round(z_ridge - g_ref, 1)})
    # swissBUILDINGS3D houses with no MU building and nothing in the surface model
    mtree = shapely.STRtree([g for g, _ in mu])
    for b, f in zip(blds, fps):
        if b["kind"] != "Gebaeude Einzelhaus" or f.area < MIN_AREA or not keep.contains(f.representative_point()):
            continue
        hits = mtree.query(f, predicate="intersects")
        cov = sum(shapely.intersection(f, mu[i][0]).area for i in hits) / max(f.area, 1e-6)
        if cov >= 0.2:
            continue
        x, y, h = heights(f, dsm, dtm)
        cx, cy = f.representative_point().coords[0]
        rec = {"uuid": b["uuid"], "x": round(cx, 1), "y": round(cy, 1), "area": round(f.area, 1)}
        if h is None or len(h) < 8:
            continue
        fill = float(np.mean(h > H_MIN))
        rec["fill"] = round(fill, 2)
        (diff["gone"] if fill < GONE else diff["kept"]).append(rec)
    pickle.dump(added, open(ADDED, "wb"))
    json.dump(diff, open(DIFF, "w"), indent=0)
    print("MU buildings missing in swissBUILDINGS3D: added %d, not added %d; swissBUILDINGS3D houses without MU "
          "building: gone %d, kept %d" % (len(diff["added"]), len(diff["not_added"]), len(diff["gone"]), len(diff["kept"])))
    from collections import Counter
    print(Counter(r["why"] for r in diff["not_added"]))


if __name__ == "__main__":
    main()
