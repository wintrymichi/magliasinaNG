"""Road markings as painted mesh strips (DecalRoads do not render on the road meshes).

Centre line: every dash measured in the orthophoto (markings.json) at its surveyed position
(Swiss broken line 3 m / 6 m; solid runs up to 60 m); inside canopy-occluded stretches the
measured rhythm (period, phase of the last visible dash) is continued. Edge lines: where the
multi-view photo vote says painted (markings_photo.json, support >= 0.5; gaps < 3 m closed,
runs >= 5 m). Transverse / special markings: orthophoto polygons (markings_raster.json) kept
unless the panoramas contradict them.
State of October 2022 (markings_state.json): nothing is painted in the stretches the panoramas
show unmarked (resurfacing works, village streets); the red edge bands near Pura are painted
as red bands and the white edge line is left out there; centre dashes the photos do not show
where the orthophoto puts them, but clearly show 0.5-2 m away, are moved onto the photo line.
"""
import json, os
import numpy as np
from scipy.ndimage import binary_closing, label
import bng
import copy_materials
from config import WORK

LINE_MAT = "italy_road_markings_line_thin"
WIDTH = 0.18


def decal(nodes, material=LINE_MAT, prio=23):
    n = [[round(float(x), 3), round(float(y), 3), round(float(z), 3), WIDTH] for x, y, z in nodes]
    return {"class": "DecalRoad", "persistentId": bng.pid(), "position": n[0][:3], "decalBias": 0.0015,
            "distanceFade": [90, 45], "improvedSpline": True, "material": material, "nodes": n,
            "renderPriority": prio, "startEndFade": [0.02, 0.02], "textureLength": 4, "drivability": -1}


def strip(mb, P, z, width=0.12, mat="mp_road_paint"):
    """Painted line as a thin quad strip following the surface (P: (n,2) centre line)."""
    if len(P) < 2:
        return
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nn = np.column_stack([-T[:, 1], T[:, 0]]) * width / 2
    L = np.column_stack([P + Nn, z]); R = np.column_stack([P - Nn, z])
    tri = np.stack([R[:-1], R[1:], L[1:], R[:-1], L[1:], L[:-1]], 1).reshape(-1, 3)
    t3 = tri.reshape(-1, 3, 3)
    if np.mean(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])[:, 2]) < 0:
        tri = t3[:, ::-1].reshape(-1, 3)
    mb.add(mat, tri, uvs=tri[:, :2], normals=np.repeat([[0, 0, 1.0]], len(tri), 0))


def densify_s(a, b, step=0.5):
    return np.linspace(a, b, max(2, int(np.ceil((b - a) / step)) + 1))


def load_state():
    f = os.path.join(WORK, "markings_state.json")
    st = json.load(open(f)) if os.path.exists(f) else {"unmarked": [], "red_bands": []}
    un = np.array(st["unmarked"]) if st["unmarked"] else np.zeros((0, 2))

    def unmarked(a, b=None):
        """fraction of [a, b] (or the point a) inside an unmarked stretch"""
        if b is None:
            return float(np.any((un[:, 0] <= a) & (un[:, 1] >= a))) if len(un) else 0.0
        if b <= a or not len(un):
            return 0.0
        ov = np.clip(np.minimum(un[:, 1], b) - np.maximum(un[:, 0], a), 0, None).sum()
        return float(ov / (b - a))
    return st, unmarked


def red_band_strips(mb, st, pt, hfn, gap=30.0):
    """Painted red bands between their inner and outer offsets; same-side bands closer than
    `gap` along the road are joined (cars and shadows interrupt them in the orthophoto)."""
    bands = sorted(st.get("red_bands", []), key=lambda b: (b["side"], b["s"][0]))
    merged = []
    for b in bands:
        if merged and merged[-1]["side"] == b["side"] and b["s"][0] - merged[-1]["s"][-1] < gap:
            m = merged[-1]
            for k in ("s", "t_in", "t_out"):
                m[k] = m[k] + b[k]
        else:
            merged.append({k: list(v) if isinstance(v, list) else v for k, v in b.items()})
    covered = []
    for b in merged:
        ss = np.arange(b["s"][0], b["s"][-1], 0.5)
        ti = np.interp(ss, b["s"], b["t_in"]); to = np.interp(ss, b["s"], b["t_out"])
        xi, yi = pt(ss, ti); xo, yo = pt(ss, to)
        I = np.column_stack([xi, yi, hfn(xi, yi) + 0.021]); O = np.column_stack([xo, yo, hfn(xo, yo) + 0.021])
        t3 = np.stack([I[:-1], O[:-1], O[1:], I[:-1], O[1:], I[1:]], 1).reshape(-1, 3, 3)
        down = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])[:, 2] < 0
        t3[down] = t3[down][:, ::-1]
        tri = t3.reshape(-1, 3)
        mb.add("mp_road_paint_red", tri, uvs=tri[:, :2], normals=np.repeat([[0, 0, 1.0]], len(tri), 0))
        covered.append((b["side"], ss[0], ss[-1]))
    return covered


def polygon_filter(polys, st_strip, unmarked):
    """Keep an orthophoto marking polygon unless the panoramas contradict it: the lane-marking
    vote (marking_votes.npz, tolerance +-0.25 m) over the polygon is < 0.25 (white) / < 0.1
    (yellow) where the panoramas see it, it lies in an unmarked stretch, or it is a small
    (< 0.3 m2) white blob nobody can confirm."""
    import shapely
    from scipy.ndimage import maximum_filter
    from scipy.spatial import cKDTree
    V = np.load(os.path.join(WORK, "marking_votes.npz"))
    vis = V["vis"]
    P = np.where(vis >= 2, V["hits"] / np.maximum(vis, 1), 0)
    Pm = maximum_filter(P, (5, 11)); Vm = maximum_filter(vis, (5, 11))
    s_all, t_all = st_strip["s"], st_strip["t"]
    tree = cKDTree(np.column_stack([st_strip["X"], st_strip["Y"]]))
    pv_f = os.path.join(WORK, "marking_poly_votes.json")
    pv = json.load(open(pv_f)) if os.path.exists(pv_f) else [None] * len(polys)
    keep = []
    stats = {"kept": 0, "contradicted": 0, "unmarked": 0, "small": 0}
    for m, v in zip(polys, pv):
        pg = shapely.Polygon(m["rings"][0])
        x0, y0, x1, y1 = pg.bounds
        gx, gy = np.meshgrid(np.arange(x0 + 0.05, x1, 0.1), np.arange(y0 + 0.05, y1, 0.1))
        ins = shapely.contains_xy(pg, gx, gy)
        Q = np.column_stack([gx[ins], gy[ins]]) if ins.any() else np.array([[pg.centroid.x, pg.centroid.y]])
        _, r = tree.query(Q)
        tq = (Q[:, 0] - st_strip["X"][r]) * st_strip["Nx"][r] + (Q[:, 1] - st_strip["Y"][r]) * st_strip["Ny"][r]
        on_strip = np.abs(tq) < t_all[-1] - 0.2
        if on_strip.mean() > 0.5 and unmarked(float(np.median(s_all[r]))):
            stats["unmarked"] += 1
            continue
        if on_strip.mean() > 0.5:
            c = np.clip(np.round((tq - t_all[0]) / (t_all[1] - t_all[0])).astype(int), 0, len(t_all) - 1)
            seen = Vm[r, c] >= 2
            seen_f = seen.mean()
            sup = float(Pm[r, c][seen].mean()) if seen.any() else 0.0
        elif v is not None:
            seen_f = 1.0 if v["panos"] >= 2 else 0.0
            sup = v["hit"] / max(v["vis"], 1)
        else:
            seen_f, sup = 0.0, 0.0
        if seen_f >= 0.5:
            if sup < (0.1 if m["color"] == "yellow" else 0.25):
                stats["contradicted"] += 1
                continue
        elif m["color"] == "white" and pg.area < 0.3:
            stats["small"] += 1
            continue
        keep.append(m)
        stats["kept"] += 1
    return keep, stats


def build(level_dir, scene, hfn):
    mk = json.load(open(os.path.join(WORK, "markings.json")))
    state, unmarked = load_state()
    st = np.load(os.path.join(WORK, "road_strip.npz"))
    s_all, X, Y, Nx, Ny = st["s"], st["X"], st["Y"], st["Nx"], st["Ny"]

    def pt(s, t):
        x = np.interp(s, s_all, X) + np.interp(s, s_all, Nx) * t
        y = np.interp(s, s_all, Y) + np.interp(s, s_all, Ny) * t
        return x, y

    found, _ = copy_materials.collect([LINE_MAT])
    bng.write_materials(os.path.join(level_dir, "art", "road", "main.materials.json"), list(found.values()))
    g = "MissionGroup/roads/markings"
    n_obj = 0
    centre = [tr for tr in mk["tracks"] if tr["kind"] == "centre"][0]
    ts, tt = np.array(centre["s"]), np.array(centre["t"])
    segs = [tuple(x) for x in centre["segments"] if 1.2 <= x[1] - x[0] <= 60.0]
    # fill occluded stretches with the measured rhythm
    period = (centre["dash_len_median"] or 3.0) + (centre["gap_median"] or 6.0)
    dash = centre["dash_len_median"] or 3.0
    filled = list(segs)
    for a, b in mk["occluded"]:
        before = [x for x in segs if x[1] <= a + 0.5]
        after = [x for x in segs if x[0] >= b - 0.5]
        if not before or not after or b - a > 200:
            continue
        last = before[-1]
        k = last[0] + period
        while k + dash < min(b, after[0][0] - 1.0):
            if k > a - 0.5:
                filled.append((k, k + dash))
            k += period
    mb = bng.MeshBuilder()
    n_skip = n_moved = 0
    # centre line seen by the panoramas (markings_state.photo_centre): a dash with no photo
    # support where the orthophoto puts it, while the photos show a clear centre line elsewhere
    # (0.5-2 m away), is painted on the photo line (junctions rebuilt after the flight, dashes
    # of the orthophoto track that followed a crack sealing or a shadow)
    pc = state.get("photo_centre")
    if pc:
        from scipy.ndimage import maximum_filter1d, uniform_filter1d
        V = np.load(os.path.join(WORK, "marking_votes.npz"))
        Pm = maximum_filter1d(np.where(V["vis"] >= 2, V["hits"] / np.maximum(V["vis"], 1), 0), 15, axis=1)
        t_grid = V["t"]
        pc_s, pc_t = np.array(pc["s"]), np.array(pc["t"])
        pc_sup, pc_seen = np.array(pc["support"]), np.array(pc["seen"])

    def displaced(a, b):
        if not pc:
            return False
        ss = np.arange(a, b + 1e-6, 0.1)
        to = np.interp(ss, ts, tt); tp = np.interp(ss, pc_s, pc_t)
        r = np.clip(np.round(ss / 0.1).astype(int), 0, len(Pm) - 1)
        c = np.clip(np.round((to - t_grid[0]) / (t_grid[1] - t_grid[0])).astype(int), 0, len(t_grid) - 1)
        here = np.median(uniform_filter1d(Pm[r, c], 3))
        return (np.median(np.interp(ss, pc_s, pc_seen)) > 0.5 and np.median(np.interp(ss, pc_s, pc_sup)) >= 0.45
                and 0.5 < np.median(np.abs(to - tp)) < 2.0 and here < 0.15)
    for a, b in sorted(filled):
        if unmarked(a, b) > 0.5:
            n_skip += 1
            continue
        ss = densify_s(a, b)
        t = np.interp(ss, ts, tt)
        if displaced(a, b):
            t = np.interp(ss, pc_s, pc_t)
            n_moved += 1
        x, y = pt(ss, t)
        strip(mb, np.column_stack([x, y]), hfn(x, y) + 0.02)
        n_obj += 1
    # edge lines from the photo vote
    ph = json.load(open(os.path.join(WORK, "markings_photo.json")))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    red_cov = red_band_strips(mb, state, pt, hfn)
    for side in ("edge_left", "edge_right"):
        s = np.array(ph[side]["s"]); t = np.array(ph[side]["t"]); sup = np.array(ph[side]["support"])
        vis = np.array(ph[side]["visible"])
        on = (sup >= 0.5) & (vis >= 2)
        on = binary_closing(on, structure=np.ones(7))
        on &= np.array([not unmarked(x) for x in s])
        for sd, a, b in red_cov:
            if sd == side.split("_")[1]:
                on &= ~((s >= a - 1.0) & (s <= b + 1.0))
        lab, n = label(on)
        for q in range(1, n + 1):
            ii = np.where(lab == q)[0]
            if s[ii[-1]] - s[ii[0]] < 5.0:
                continue
            C = rp["C"][ii]; N = rp["N"][ii]
            from scipy.ndimage import median_filter as _mf
            P = C + N * _mf(t[ii], 7, mode="nearest")[:, None]
            strip(mb, P, hfn(P[:, 0], P[:, 1]) + 0.02)
            n_obj += 1
    # transverse / special markings vectorised from the orthophoto (markings_raster.py)
    mr_f = os.path.join(WORK, "markings_raster.json")
    n_poly = 0
    if os.path.exists(mr_f):
        import shapely
        polys, pstats = polygon_filter(json.load(open(mr_f)), st, unmarked)
        print("raster polygons", pstats)
        for m in polys:
            poly = shapely.Polygon(m["rings"][0])
            if not poly.is_valid:
                poly = shapely.make_valid(poly)
            for pg in getattr(poly, "geoms", [poly]):
                if not isinstance(pg, shapely.Polygon) or pg.area < 0.05:
                    continue
                tri = shapely.constrained_delaunay_triangles(pg)
                V = []
                for t in tri.geoms:
                    c = np.asarray(t.exterior.coords)[:3]
                    if (c[1, 0] - c[0, 0]) * (c[2, 1] - c[0, 1]) - (c[1, 1] - c[0, 1]) * (c[2, 0] - c[0, 0]) < 0:
                        c = c[::-1]
                    V.append(c)
                if not V:
                    continue
                V = np.concatenate(V)
                V3 = np.column_stack([V, hfn(V[:, 0], V[:, 1]) + 0.021])
                mb.add("mp_road_paint_yellow" if m["color"] == "yellow" else "mp_road_paint", V3, uvs=V,
                       normals=np.repeat([[0, 0, 1.0]], len(V3), 0))
                n_poly += 1
    print("raster marking polygons", n_poly)
    bng.write_materials(os.path.join(level_dir, "art", "road", "paint.materials.json"), [
        bng.material("mp_road_paint", base_color=[0.86, 0.86, 0.84, 1], roughness=0.65),
        bng.material("mp_road_paint_yellow", base_color=[0.88, 0.72, 0.12, 1], roughness=0.65),
        # red edge bands: panorama colour of the band pixels (median sRGB 162/138/140), a little
        # more saturated than the hazy photos
        bng.material("mp_road_paint_red", base_color=[0.66, 0.46, 0.46, 1], roughness=0.7)])
    rel = "art/shapes/roads/markings.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="markings", origin=(0, 0, 0))
    from config import LEVEL_NAME
    scene.add(g, bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", (0, 0, 0), collision=False, decal=False))
    print("marking strips", n_obj, "(centre dashes", len(filled) - n_skip, "; moved to the photo line", n_moved,
          "; skipped in unmarked stretches", n_skip,
          "; red bands", len(red_cov), ")")
