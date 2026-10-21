"""Why a road has a step at a place: the cells of network_mesh.Network.tile_surface around it (heights, the line
and polygon each cell takes its height from, which neighbours are linked) next to the top faces of the built
level, as pictures and numbers (v3.0 fix round, a development aid like fix_review.py).
For each place a 40 x 40 m window: <out>/<name>.png (the cells' heights before the seams are relaxed, after, the
lines, and the built level's top faces, the jumps over JUMP m between neighbours drawn on each) and <out>/probe.json
(the largest jumps: heights, lines, polygons, their classes, how far apart along the line the two cells project,
linked or not).
    python fix_probe.py <out folder> [--level <folder>] [--places name:x:y,...]
"""
import json, os, sys
import numpy as np
from config import LEVEL_DIR, WORK
from geo import Grid
import network_mesh as nm

PLACES = [("astano_hairpin", -3709.0, 2139.0), ("selva_bella", -1909.0, 2450.0), ("arosio", 2173.0, 6394.0),
          ("fescoggia", 504.0, 5412.0), ("breno", 8.0, 4595.0), ("mugena", 1558.0, 6361.0),
          ("vezio_hole", 1030.0, 6080.0), ("stradon_bridge", 806.0, 5928.0), ("castelrotto", -2400.0, 33.0),
          ("mugena_bridge", 1130.0, 6314.0)]
HALF = 20.0
JUMP = 0.08


def main(argv):
    out = argv[0]
    lv = argv[argv.index("--level") + 1] if "--level" in argv else LEVEL_DIR
    if "--places" in argv:                    # name:x:y,name:x:y ... instead of PLACES
        global PLACES
        PLACES = [(a, float(b), float(c)) for a, b, c in
                  (p.split(":") for p in argv[argv.index("--places") + 1].split(","))]
    os.makedirs(out, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from check_level import road_tops
    from road_mesh import TriSurface
    tri, is_path, _ = road_tops(lv)
    S = TriSurface(tri)
    net = nm.Network()
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    cap = {}
    orig = nm.relax_seams

    def spy(Z, G, owner, LR, LD, fixed_cells=None, folds=None, *rest):
        cap.update(Z=Z.copy(), G=G.copy(), owner=owner.copy(), LR=LR.copy(), LD=LD.copy(), folds=folds)
        return orig(Z, G, owner, LR, LD, fixed_cells, folds, *rest)
    nm.relax_seams = spy
    res = {}
    for name, x, y in PLACES:
        cap.clear()
        x0, y0, x1, y1 = x - HALF, y - HALF, x + HALF, y + HALF
        net.explain = True
        Sf, ids = net.tile_surface(x0, y0, x1, y1, dtm)
        net.explain = False
        tex = getattr(net, "tile_explained", None)
        if Sf is None or not cap:
            res[name] = "no surface"
            continue
        Z0, G, own, LR, LD = cap["Z"], cap["G"], cap["owner"], cap["LR"], cap["LD"]
        Z1 = np.where(own >= 0, np.asarray(Sf.Z), np.nan)
        n = Z0.shape[0]
        xs = x0 + (np.arange(Z0.shape[1]) + 0.5) * nm.RES
        ys = y1 - (np.arange(n) + 0.5) * nm.RES
        X, Y = np.meshgrid(xs, ys)
        Zl = S.height(X.ravel(), Y.ravel(), "high").reshape(X.shape)
        # the line's point each cell projects on (m along it), its distance in half widths, how far past the line's end
        Ag, Ug, Eg = (np.full(own.shape, np.nan) for _ in range(3))
        rr, cc = np.nonzero(own >= 0)
        _, _, u_, e_, a_ = net.heights(X[rr, cc], Y[rr, cc], own[rr, cc], with_seg=True, with_u=True)
        Ag[rr, cc], Ug[rr, cc], Eg[rr, cc] = a_, u_, e_
        # the cells and the strips together, as the level's mesh has them (strips: meshed apart at strip_height)
        import shapely as _sh
        from rasterio import features as _ft
        from rasterio.transform import Affine as _Af
        Zc = Z1.copy()
        sids = [int(i) for i in net.ptree.query(_sh.box(x0, y0, x1, y1), predicate="intersects")
                if net.polys[i]["cls"].startswith("strip")]
        if sids:
            sown = _ft.rasterize([(net.polys[i]["geom"], i) for i in sids], out_shape=own.shape,
                                 transform=_Af(nm.RES, 0, x0, 0, -nm.RES, y1), fill=-1, dtype=np.int32)
            for pid in sids:
                k = (sown == pid) & (own < 0)
                if k.any():
                    Zc[k] = net.strip_height(pid)(X[k], Y[k])
        jumps = []
        for axis, L in ((1, LR), (0, LD)):
            a = (slice(None), slice(0, -1)) if axis == 1 else (slice(0, -1), slice(None))
            b = (slice(None), slice(1, None)) if axis == 1 else (slice(1, None), slice(None))
            both = (own[a] >= 0) & (own[b] >= 0)
            for lab, Z in (("cells", Z0), ("relaxed", Z1), ("composite", Zc), ("level", Zl)):
                d = np.abs(Z[a] - Z[b])
                m = (both if lab in ("cells", "relaxed") else np.isfinite(d)) & (d > JUMP)
                for r, c in zip(*np.nonzero(m)):
                    r2, c2 = (r, c + 1) if axis == 1 else (r + 1, c)
                    g1, g2 = int(G[r, c]), int(G[r2, c2])
                    jumps.append({"what": lab, "x": round(float(xs[c]), 1), "y": round(float(ys[r]), 1),
                                  "dz": round(float(d[r, c]), 3), "z": [round(float(Z[r, c]), 2), round(float(Z[r2, c2]), 2)],
                                  "lines": [g1, g2],
                                  "line_names": [net.segs[g]["name"] if g >= 0 else str(g) for g in (g1, g2)],
                                  "line_classes": [net.segs[g]["class"] if g >= 0 else str(g) for g in (g1, g2)],
                                  "polys": [int(own[r, c]), int(own[r2, c2])],
                                  "poly_cls": [net.polys[int(own[r, c])]["cls"] if own[r, c] >= 0 else "-",
                                               net.polys[int(own[r2, c2])]["cls"] if own[r2, c2] >= 0 else "-"],
                                  "linked": bool(L[r, c]),
                                  "arc": [round(float(Ag[r, c]), 2), round(float(Ag[r2, c2]), 2)],
                                  "u": [round(float(Ug[r, c]), 2), round(float(Ug[r2, c2]), 2)],
                                  "past_end": [round(float(Eg[r, c]), 2), round(float(Eg[r2, c2]), 2)],
                                  "fold": bool(lab != "level" and cap.get("folds") is not None
                                               and cap["folds"][0 if axis == 1 else 1][r, c])})
        jumps.sort(key=lambda j: -j["dz"])
        # the candidate lines of the two cells of the largest jumps after relaxing: line, height, half widths, overrun, weight
        net.explain = True
        for j in [j for j in jumps if j["what"] == "relaxed"][:4] + \
                [j for j in jumps if j["what"] == "composite" and np.hypot(j["x"] - x, j["y"] - y) < 6.0][:3]:
            P = np.array([[j["x"], j["y"]]])
            j["candidates"] = []
            r0, c0 = int(round((y1 - j["y"]) / nm.RES - 0.5)), int(round((j["x"] - x0) / nm.RES - 0.5))
            if tex is not None:
                j["tile"] = {k: [v[r0, c0].item(), v[r0, min(c0 + 1, v.shape[1] - 1)].item(),
                                 v[min(r0 + 1, v.shape[0] - 1), c0].item()] for k, v in tex.items()}
            for rr_, cc_ in ((r0, c0), (r0, c0 + 1), (r0 + 1, c0)):
                if not (0 <= rr_ < own.shape[0] and 0 <= cc_ < own.shape[1]) or own[rr_, cc_] < 0:
                    continue
                net.heights(np.array([xs[cc_]]), np.array([ys[rr_]]), np.array([own[rr_, cc_]]), with_seg=True, with_u=True)
                ex = net.explained
                j["candidates"].append({"cell": [round(float(xs[cc_]), 2), round(float(ys[rr_]), 2)],
                                        "best": int(ex["best"][0]),
                                        "lines": [[int(ex["seg"][0, i]), net.segs[int(ex["seg"][0, i])]["class"],
                                                   net.segs[int(ex["seg"][0, i])]["kind"],
                                                   round(float(ex["h"][0, i]), 2), round(float(ex["u"][0, i]), 2),
                                                   round(float(ex["e"][0, i]), 2), round(float(ex["wt"][0, i]), 4)]
                                                  for i in range(ex["seg"].shape[1]) if ex["ok"][0, i]]})
        net.explain = False
        # the seams between the polygons' cells and the strips beside them (strips: meshed apart at their line's height)
        import shapely
        Zp = np.where(own >= 0, np.asarray(Sf.Z), np.nan)
        probe_pin = np.zeros(own.shape, bool)
        Zs = Zp.copy()
        net._pin_strips(shapely.box(x0, y0, x1, y1), x0, y1, own.shape[1], own.shape[0], own >= 0, Zs, G) \
            if hasattr(net, "_pin_strips") else None
        sd = np.abs(Zs - Zp)
        strip_seams = sd[np.isfinite(sd) & (sd > 1e-6)]
        res_strip = {"cells": int(len(strip_seams)), "max_m": round(float(strip_seams.max()), 3) if len(strip_seams) else 0.0,
                     "over_0.08": int((strip_seams > JUMP).sum())}
        res_folds = int(sum(f.sum() for f in cap["folds"])) if cap.get("folds") is not None else 0
        res[name] = {"cells": int((own >= 0).sum()), "fold_links": res_folds, "strip_seams": res_strip,
                     "composite_max_6m": max([j["dz"] for j in jumps if j["what"] == "composite"
                                              and np.hypot(j["x"] - x, j["y"] - y) < 6.0] or [0.0]),
                     "level_max_6m": max([j["dz"] for j in jumps if j["what"] == "level"
                                          and np.hypot(j["x"] - x, j["y"] - y) < 6.0] or [0.0]),
                     "jumps": [j for j in jumps if j["what"] in ("cells", "level")][:30] + [j for j in jumps if j["what"] == "relaxed"][:30]
                     + [j for j in jumps if j["what"] == "composite"][:20],
                     "n_jumps_cells": sum(1 for j in jumps if j["what"] == "cells"),
                     "n_jumps_relaxed": sum(1 for j in jumps if j["what"] == "relaxed"),
                     "n_jumps_composite": sum(1 for j in jumps if j["what"] == "composite"),
                     "n_jumps_level": sum(1 for j in jumps if j["what"] == "level")}
        fig, ax = plt.subplots(1, 4, figsize=(24, 6.4))
        ext = (x0, x1, y0, y1)
        for k, (Z, t) in enumerate(((Z0, "cells, before relax"), (Z1, "cells, after"), (Zc, "cells and strips"), (Zl, "level top faces"))):
            im = ax[k].imshow(Z, extent=ext, origin="upper", cmap="terrain", interpolation="nearest")
            plt.colorbar(im, ax=ax[k], fraction=0.046)
            ax[k].set_title(t)
            for j in jumps:
                if j["what"] == ("cells", "relaxed", None, "level")[k] or (k == 2 and j["what"] == "composite"):
                    ax[k].plot(j["x"], j["y"], ".", ms=3, color="lime" if j.get("fold") else ("red" if j["linked"] else "blue"))
            ax[k].plot(x, y, "k+", ms=14)
        fig.suptitle(f"{name} ({x:.0f}, {y:.0f}): red jumps between linked cells, blue unlinked, green folds of one line (> {JUMP} m)")
        fig.tight_layout()
        fig.savefig(os.path.join(out, f"{name}.png"), dpi=70)
        plt.close(fig)
        print(name, res[name]["n_jumps_cells"], res[name]["n_jumps_level"], flush=True)
    json.dump(res, open(os.path.join(out, "probe.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
