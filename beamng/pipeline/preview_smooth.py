"""Quick 3D preview of the smoothed survey curves (smooth_geom.py), without building the level.

Loads the cadastral survey twice (landcover.load_av, as it is and smoothed), measures what the smoothing does
to the land cover partition over the whole map (overlaps and gaps between neighbours, polygons that became
invalid) and renders the curviest spots of the roads before and after, in 3D (ground flat, walls raised), so a
change to the smoothing can be looked at in minutes instead of a two-hour build.

python preview_smooth.py OUT_DIR   (workflow v3_preview.yml)
"""
import json, os, sys, time
import numpy as np
import shapely
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import landcover
import smooth_geom


WIN = 60.0             # m, side of a rendered spot
SPOTS = 6
COL = {"strada_sentiero": "#5a5a5c", "altro_rivestimento_duro": "#6e6e70", "marciapiede": "#a9a6a0",
       "spartitraffico": "#c9c6bd", "edificio": "#b5674d", "giardino": "#6f9a4a", "campo_prato_pascolo": "#86a85a",
       "bosco_fitto": "#2f5a2a", "altro_bosco": "#3d6a33", "corso_acqua": "#4a78a8", "specchio_acqua": "#4a78a8"}
WALL_H = 1.4
BLD_H = 6.0


def polys(g):
    return [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and not p.is_empty]


def tris(p):
    t = shapely.constrained_delaunay_triangles(p)
    return [np.asarray(x.exterior.coords)[:3] for x in t.geoms]


def curvy_spots(av):
    """Centres of the SPOTS windows with the most faceted bends on road and pavement outlines: vertices
    turning by 6 to CORNER degrees between pieces at least 3 m long (where the survey's straight pieces show)."""
    pts = []
    for g, _ in av["LCSF"].get("strada_sentiero", []) + av["LCSF"].get("marciapiede", []):
        for p in polys(g):
            P = np.asarray(p.exterior.coords)[:-1, :2]
            if len(P) < 3:
                continue
            a = P - np.roll(P, 1, 0)
            b = np.roll(P, -1, 0) - P
            c = np.einsum("ij,ij->i", a, b) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
            t = np.degrees(np.arccos(np.clip(c, -1, 1)))
            la, lb = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
            pts.append(P[(t > 6) & (t < smooth_geom.CORNER) & (la > 3) & (lb > 3)])
    P = np.concatenate(pts)
    k = np.floor(P / WIN).astype(np.int64)
    u, n = np.unique(k, axis=0, return_counts=True)
    out = []
    for i in np.argsort(-n):
        c = (u[i] + 0.5) * WIN
        if all(np.hypot(*(c - o)) > 3 * WIN for o in out):
            out.append(c)
        if len(out) == SPOTS:
            break
    return out


def render(ax, av, c, title, gaps=None):
    box = shapely.box(c[0] - WIN / 2, c[1] - WIN / 2, c[0] + WIN / 2, c[1] + WIN / 2)
    faces, cols, edges = [], [], []
    for cls, lst in av["LCSF"].items():
        for g, _ in lst:
            if not g.intersects(box):
                continue
            for p in polys(g.intersection(box)):
                h = BLD_H if cls == "edificio" else 0.0
                col = COL.get(cls, "#8d9a6a")
                for t in tris(p):
                    faces.append(np.c_[t - c, np.full(3, h)])
                    cols.append(col)
                if cls != "edificio":
                    edges.append(np.c_[np.asarray(p.exterior.coords)[:, :2] - c, np.full(len(p.exterior.coords), 0.05)])
    for g, _ in av["SOSF"].get("muro", []):
        if not g.intersects(box):
            continue
        for p in polys(g.intersection(box)):
            for t in tris(p):
                faces.append(np.c_[t - c, np.full(3, WALL_H)])
                cols.append("#d8d2c4")
            R = np.asarray(p.exterior.coords)[:, :2] - c
            for a, b in zip(R[:-1], R[1:]):
                faces.append(np.array([[*a, 0], [*b, 0], [*b, WALL_H], [*a, WALL_H]]))
                cols.append("#9c968a")
    if gaps is not None:
        for p in polys(gaps.intersection(box)):
            for t in tris(p):
                faces.append(np.c_[t - c, np.full(3, 0.3)])
                cols.append("#ff1a1a")
    ax.add_collection3d(Poly3DCollection(faces, facecolors=cols, edgecolors=cols, linewidths=0.4))
    for E in edges:
        ax.plot(E[:, 0], E[:, 1], E[:, 2], color="k", lw=0.25)
    ax.set_xlim(-WIN / 2, WIN / 2); ax.set_ylim(-WIN / 2, WIN / 2); ax.set_zlim(0, 30)
    ax.view_init(elev=30, azim=-60)
    ax.set_box_aspect((1, 1, 0.27), zoom=1.45)
    ax.set_axis_off()
    ax.set_title(title, fontsize=9)


def partition_stats(raw, sm):
    def flat(av):
        return [p for lst in av["LCSF"].values() for g, _ in lst for p in polys(g)]
    a, b = flat(raw), flat(sm)
    ua, ub = shapely.union_all(a), shapely.union_all(b)
    gaps = ua.difference(ub)
    big = sorted((p for p in polys(gaps) if p.area > 0.01), key=lambda p: -p.area)[:15]
    return gaps, {"largest_gaps": [[round(p.area, 2), round(p.centroid.x), round(p.centroid.y)] for p in big],"polygons_raw": len(a), "polygons_smoothed": len(b),
            "invalid_smoothed": int(sum(not p.is_valid for p in b)),
            "area_raw_m2": round(ua.area), "area_smoothed_m2": round(ub.area),
            "overlap_m2": round(sum(p.area for p in b) - ub.area, 1),
            "overlap_raw_m2": round(sum(p.area for p in a) - ua.area, 1),
            "gaps_m2": round(gaps.area, 1),
            "vertices_raw": int(sum(len(p.exterior.coords) for p in a)),
            "vertices_smoothed": int(sum(len(p.exterior.coords) for p in b))}


def main(out):
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    raw = landcover.load_av(smooth=False)
    t1 = time.time()
    sm = landcover.load_av()
    t2 = time.time()
    gaps, stats = partition_stats(raw, sm)
    stats["kept_as_surveyed"] = len(smooth_geom.KEPT)
    stats["kept_examples"] = smooth_geom.KEPT[:20]
    flat = [(c, p) for c, lst in raw["LCSF"].items() for g, _ in lst for p in polys(g)]
    tree = shapely.STRtree([p for _, p in flat])
    stats["gap_neighbours"] = []
    # the survey polygons at the three largest gaps, as they are, snapped and smoothed (for debugging elsewhere)
    dbg = {}
    for area, x, y in stats["largest_gaps"][:3]:
        for j in tree.query(shapely.Point(x, y).buffer(5)):
            p = flat[j][1]
            if p.area < 5e6:
                dbg[str(j)] = {"cls": flat[j][0], "raw": shapely.to_wkt(p, rounding_precision=3),
                               "smoothed": shapely.to_wkt(smooth_geom.smooth_partition([p], [False])[0], rounding_precision=3)}
    json.dump(dbg, open(os.path.join(out, "gap_polygons.json"), "w"))
    for area, x, y in stats["largest_gaps"][:8]:
        near = tree.query(shapely.Point(x, y).buffer(5))
        stats["gap_neighbours"].append([[flat[j][0], round(flat[j][1].area), len(flat[j][1].interiors),
                                         len(flat[j][1].exterior.coords)] for j in near[:6]])
    stats.update(load_s=round(t1 - t0), smooth_s=round(t2 - t1 - (t1 - t0)))
    print("smoothing:", stats, flush=True)
    json.dump(stats, open(os.path.join(out, "smooth_stats.json"), "w"), indent=1)
    for i, c in enumerate(curvy_spots(raw)):
        fig = plt.figure(figsize=(14, 7.2), dpi=110)
        for j, (av, name) in enumerate(((raw, "survey as it is (v2.8 - run 4)"), (sm, "smoothed (smooth_geom.py)"))):
            render(fig.add_subplot(1, 2, j + 1, projection="3d"), av, c, f"{name}  ·  spot {i + 1}  ({c[0]:.0f}, {c[1]:.0f})",
                   gaps if j else None)
        fig.subplots_adjust(0, 0, 1, 0.96, 0, 0)
        fig.savefig(os.path.join(out, f"smooth_spot{i + 1}.png"))
        plt.close(fig)
        print("rendered spot", i + 1, c, flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "preview")
