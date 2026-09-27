"""State of the road markings at the time of the Street View capture (October 2022).

The longitudinal markings come from the orthophoto (markings.py), whose flight is older than
the panoramas. Two things are taken from the photos instead:

1. Unmarked stretches. Where the panoramas see the carriageway well but the multi-view vote
   of the lane-marking classes (marking_votes.npz) finds no marking anywhere across it (not
   even edge lines) for at least 25 m, the road carried no markings in 2022 (resurfacing
   works, fresh or milled asphalt, village streets). Nothing is painted there.
2. Red edge bands. The coloured (red/pink) bands along the edges near Pura are found where
   the orthophoto strip shows red chroma (CIELAB a* > 3.5 and b* < 1.5 a* + 3) inside the
   carriageway and the panorama strip (2022) is red too within 0.3 m at >= 50 % of the stations
   (>= 10 % when it continues an accepted band with a gap < 30 m). Bands (first red run met going outwards from the Street View car) >= 20 m long and
   0.25-0.9 m wide
   become painted bands (their inner/outer offsets per station); the white edge line is not
   painted over them.
3. Centre line seen by the panoramas: dynamic programming over the lane-marking vote in the
   band 0.5-3.5 m left of the Street View car (photo_centre). Where it is clear but the
   orthophoto centre line lies elsewhere with no photo support (junctions rebuilt after the
   orthophoto flight), markings_decals paints the photo line instead.
4. Fresh asphalt of the resurfacing works (dark in the panorama strip inside the unmarked
   stretches) -> separate darker road material; surveyed traffic islands the panoramas see as
   carriageway (removed when the start junction was rebuilt) are paved as road.
Output: work/markings_state.json {unmarked: [[s0, s1]], red_bands: [{s, t_in, t_out}], red_rgb,
        photo_centre: {s, t, support, seen}, fresh_asphalt: [ring], removed_islands: [{x, y}]}
"""
import json, os
import numpy as np
import cv2
from scipy.ndimage import uniform_filter, uniform_filter1d, label, binary_closing, binary_opening, median_filter
from config import WORK

MIN_UNMARKED = 25.0


def unmarked_stretches(s, t, tL, tR):
    V = np.load(os.path.join(WORK, "marking_votes.npz"))
    hits, vis = V["hits"].astype(np.float32), V["vis"].astype(np.float32)
    P = np.where(vis >= 3, hits / np.maximum(vis, 1), np.nan)
    inside = (t[None, :] >= tR[:, None] - 0.3) & (t[None, :] <= tL[:, None] + 0.3)
    Pin = np.where(inside, P, np.nan)
    seen = np.isfinite(Pin).sum(1) / np.maximum(inside.sum(1), 1)
    mx = np.nanmax(np.where(np.isfinite(Pin), Pin, -1.0), 1)
    known = seen > 0.4
    empty = known & (mx < 0.12)
    w = int(MIN_UNMARKED / 0.1)
    fk = uniform_filter1d(known.astype(float), w)
    fe = uniform_filter1d(empty.astype(float), w)
    cand = (fk > 0.6) & (fe / np.maximum(fk, 1e-6) > 0.8)
    # a window centre qualifies -> the whole window is unmarked
    cover = uniform_filter1d(cand.astype(float), w) > 0
    lab, n = label(cover)
    out = []
    for q in range(1, n + 1):
        ii = np.where(lab == q)[0]
        a, b = float(s[ii[0]]), float(s[ii[-1]])
        if b - a >= MIN_UNMARKED:
            out.append([round(a, 1), round(b, 1)])
    return out


def red_bands(s, t, tL, tR):
    o = np.load(os.path.join(WORK, "road_strip.npz"))
    p = np.load(os.path.join(WORK, "pano_strip.npz"))
    lab_o = cv2.cvtColor(o["rgb"], cv2.COLOR_RGB2LAB).astype(np.float32)
    n2 = 2 * (len(p["s"]) // 2)
    pr = p["rgb"][:n2].reshape(-1, 2, len(p["t"]), 3).mean(1).astype(np.uint8)
    pv = (p["src"][:n2] >= 0).reshape(-1, 2, len(p["t"])).all(1)
    lab_p = cv2.cvtColor(pr, cv2.COLOR_RGB2LAB).astype(np.float32)
    n = min(len(lab_o), len(lab_p))

    def resample(a):                                            # panorama strip t grid -> ortho t grid
        return np.stack([np.interp(t, p["t"], row) for row in a[:n]])
    a_o = uniform_filter(lab_o[:n, :, 1] - 128, (10, 3)); b_o = uniform_filter(lab_o[:n, :, 2] - 128, (10, 3))
    a_p = uniform_filter(resample(lab_p[..., 1] - 128), (10, 3)); b_p = uniform_filter(resample(lab_p[..., 2] - 128), (10, 3))
    valid_p = resample(pv.astype(np.float32)) > 0.99
    # colour from the orthophoto (cleanest chroma); presence in 2022 confirmed by the panoramas
    # (the segmentation labels the bands as lane markings; or red chroma in the panorama strip)
    V = np.load(os.path.join(WORK, "marking_votes.npz"))
    vis = V["vis"][:n]
    Pv = np.where(vis >= 2, V["hits"][:n] / np.maximum(vis, 1), 0)
    from scipy.ndimage import maximum_filter
    red_p = (a_p > 3.0) & (b_p < 1.5 * a_p + 3) & valid_p
    # a white edge line next to reddish dirt also gets lane-marking votes: the 2022 colour must
    # be red in the panorama strip as well
    conf = maximum_filter(red_p, (5, 7))
    seen = maximum_filter(valid_p, (5, 7))
    red_o = binary_closing((a_o > 3.5) & (b_o < 1.5 * a_o + 3), structure=np.ones((5, 3)))
    # search outwards from the Street View car (always on the carriageway, right lane): the
    # surveyed edges are too irregular in the villages to give the road centre
    import json as _json
    from scipy.spatial import cKDTree
    poses = [q for q in _json.load(open(os.path.join(WORK, "poses.json"))) if q.get("main_run", True)]
    Pc = np.array([q["pos"][:2] for q in poses])
    _, ri = cKDTree(np.column_stack([o["X"], o["Y"]])).query(Pc)
    tcam = (Pc[:, 0] - o["X"][ri]) * o["Nx"][ri] + (Pc[:, 1] - o["Y"][ri]) * o["Ny"][ri]
    order = np.argsort(s[ri])
    tc = median_filter(np.interp(s[:n], s[ri][order], tcam[order]), 101, mode="nearest")
    dt = t[1] - t[0]
    bands, rgb_samples, cands = [], [], []
    for side, sg, dmax in (("left", 1, 5.5), ("right", -1, 3.5)):
        t_in = np.full(n, np.nan); t_out = np.full(n, np.nan); ok_c = np.zeros(n); ok_s = np.zeros(n)
        for r in range(n):
            # first red run met going outwards from the car (0.5 m .. dmax)
            d = np.arange(0.5, dmax, dt)
            cols = np.round((tc[r] + sg * d - t[0]) / dt).astype(int)
            cols = cols[(cols >= 0) & (cols < len(t))]
            m = red_o[r, cols]
            if not m.any():
                continue
            i0 = int(np.argmax(m)); i1 = i0
            while i1 + 1 < len(m) and m[i1 + 1] and (i1 - i0) * dt < 1.2:
                i1 += 1
            if (i1 - i0 + 1) * dt < 0.2:
                continue
            t_in[r], t_out[r] = t[cols[i0]], t[cols[i1]] + sg * dt
            seg = cols[i0:i1 + 1]
            ok_s[r] = seen[r, seg].any(); ok_c[r] = conf[r, seg].any()
        on = np.isfinite(t_in)
        on = binary_opening(binary_closing(on, structure=np.ones(31)), structure=np.ones(21))
        lab, k = label(on)
        for q in range(1, k + 1):
            rows = np.where(lab == q)[0]
            if len(rows) * 0.1 < 20.0:
                continue
            good = np.isfinite(t_in[rows])
            ti = np.interp(rows, rows[good], t_in[rows][good]); to = np.interp(rows, rows[good], t_out[rows][good])
            ti = median_filter(ti, 31, mode="nearest"); to = median_filter(to, 31, mode="nearest")
            w = np.abs(to - ti)
            frac_c = ok_c[rows].sum() / max(ok_s[rows].sum(), 1)
            if not (0.25 <= np.median(w) <= 0.9) or ok_s[rows].mean() < 0.3:
                continue
            step = 5                                              # 0.5 m stations
            cc = np.round((0.5 * (ti + to) - t[0]) / dt).astype(int)
            cands.append({"s": s[rows][::step].round(2).tolist(), "t_in": ti[::step].round(3).tolist(),
                          "t_out": to[::step].round(3).tolist(), "side": side, "confirmed": round(float(frac_c), 2),
                          "rgb": o["rgb"][rows, cc],
                          "rgb_p": pr[rows, np.clip(np.round((t[cc] - p["t"][0]) / (p["t"][1] - p["t"][0])).astype(int),
                                                    0, len(p["t"]) - 1)][valid_p[rows, cc]]})
    # accept clearly red bands, then weaker ones that continue an accepted band (< 30 m gap)
    acc = [c["confirmed"] >= 0.5 for c in cands]
    for _ in range(3):
        for i, c in enumerate(cands):
            if acc[i] or c["confirmed"] < 0.1:
                continue
            for j, d in enumerate(cands):
                if acc[j] and d["side"] == c["side"] and                         min(abs(c["s"][0] - d["s"][-1]), abs(d["s"][0] - c["s"][-1])) < 30:
                    acc[i] = True
    for c, a in zip(cands, acc):
        print("   candidate %s %.0f-%.0f red in panoramas %.2f -> %s" % (c["side"], c["s"][0], c["s"][-1],
                                                                        c["confirmed"], "band" if a else "no"))
        rgb_o, rgb_p = c.pop("rgb"), c.pop("rgb_p")
        if a:
            rgb_samples.append(rgb_p); bands.append(c)
    rgb = np.median(np.concatenate(rgb_samples), 0).tolist() if rgb_samples else None
    return bands, rgb


def camera_offset(o, n):
    """Lateral position of the Street View car in strip coordinates, per strip row."""
    from scipy.spatial import cKDTree
    poses = [q for q in json.load(open(os.path.join(WORK, "poses.json"))) if q.get("main_run", True)]
    Pc = np.array([q["pos"][:2] for q in poses])
    _, ri = cKDTree(np.column_stack([o["X"], o["Y"]])).query(Pc)
    tcam = (Pc[:, 0] - o["X"][ri]) * o["Nx"][ri] + (Pc[:, 1] - o["Y"][ri]) * o["Ny"][ri]
    order = np.argsort(o["s"][ri])
    return median_filter(np.interp(o["s"][:n], o["s"][ri][order], tcam[order]), 101, mode="nearest")


def photo_centre(o):
    """Centre line as the panoramas saw it: dynamic programming over the lane-marking vote in
    the band 0.5-3.5 m left of the Street View car (it drives in the right lane)."""
    from markings import track
    V = np.load(os.path.join(WORK, "marking_votes.npz"))
    vis = V["vis"]
    P = np.where(vis >= 2, V["hits"] / np.maximum(vis, 1), 0).astype(np.float32)
    s, t = o["s"], o["t"]
    n = len(P)
    tc = camera_offset(o, n)
    lo, hi = tc + 0.5, tc + 3.5
    E = uniform_filter1d(P, 5, axis=0) * 40.0                    # track() smooths 2 m along itself
    path = track(E, t, lo, hi, smooth_px=1)
    tt = median_filter(t[path].astype(float), 31, mode="nearest")
    cols = np.clip(np.round((tt - t[0]) / (t[1] - t[0])).astype(int), 0, len(t) - 1)
    from scipy.ndimage import maximum_filter1d
    Pm = maximum_filter1d(P, 5, axis=1)
    sup = uniform_filter1d(Pm[np.arange(n), cols], 31)
    seen = uniform_filter1d((maximum_filter1d(vis, 5, axis=1)[np.arange(n), cols] >= 2).astype(float), 31)
    step = 5
    return {"s": s[::step].round(2).tolist(), "t": tt[::step].round(3).tolist(),
            "support": sup[::step].round(3).tolist(), "seen": seen[::step].round(2).tolist()}


def fresh_asphalt(o, unmarked, tL, tR):
    """New (dark) asphalt of the 2022 resurfacing works: inside the unmarked stretches (+-5 m),
    carriageway cells of the panorama strip darker than CIELAB L 95 (normal asphalt ~140),
    cleaned (closing 1 m, opening 0.5 m), components >= 4 m2 -> world polygons."""
    import shapely
    p = np.load(os.path.join(WORK, "pano_strip.npz"))
    s, t = o["s"], o["t"]
    n2 = 2 * (len(p["s"]) // 2)
    pr = p["rgb"][:n2].reshape(-1, 2, len(p["t"]), 3).mean(1).astype(np.uint8)
    pv = (p["src"][:n2] >= 0).reshape(-1, 2, len(p["t"])).all(1)
    n = min(len(pr), len(s))
    Lp = cv2.cvtColor(pr[:n], cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32)
    L = np.stack([np.interp(t, p["t"], row) for row in Lp])
    V = np.stack([np.interp(t, p["t"], row.astype(np.float32)) for row in pv[:n]]) > 0.99
    rows = np.zeros(n, bool)
    for a, b in unmarked:
        rows[max(0, int((a - 5) / 0.1)):min(n, int((b + 5) / 0.1))] = True
    inside = (t[None, :] >= tR[:n, None]) & (t[None, :] <= tL[:n, None])
    dark = (uniform_filter(L, (5, 5)) < 95) & V & inside & rows[:, None]
    dark = binary_opening(binary_closing(dark, structure=np.ones((11, 21))), structure=np.ones((5, 11)))
    lab, k = label(dark)
    polys = []
    for q in range(1, k + 1):
        m = (lab == q).astype(np.uint8)
        if m.sum() * 0.1 * 0.05 < 4.0:
            continue
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if len(c) < 4:
                continue
            rr = c[:, 0, 1].astype(float); cc = c[:, 0, 0].astype(float)
            ss = np.interp(rr, np.arange(n), s[:n]); tt = np.interp(cc, np.arange(len(t)), t)
            X = np.interp(ss, s, o["X"]) + np.interp(ss, s, o["Nx"]) * tt
            Y = np.interp(ss, s, o["Y"]) + np.interp(ss, s, o["Ny"]) * tt
            pg = shapely.Polygon(np.column_stack([X, Y])).buffer(0).simplify(0.08)
            for g in getattr(pg, "geoms", [pg]):
                if g.area >= 4.0:
                    polys.append(np.asarray(g.exterior.coords).round(3).tolist())
    return polys


def removed_islands(unmarked):
    """Surveyed traffic islands the panoramas show as carriageway (label vote road + lane
    marking >= 70 % of >= 30 votes): removed when the junction was rebuilt."""
    import pickle
    import shapely
    import photo_votes
    from build_level import road_height_fn
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    line = shapely.LineString(rp["center"])
    hfn = road_height_fn()
    out = []
    for g, _ in av["LCSF"].get("spartitraffico", []):
        if g.distance(line) > 15:
            continue
        x0, y0, x1, y1 = g.bounds
        gx, gy = np.meshgrid(np.arange(x0, x1, 0.25), np.arange(y0, y1, 0.25))
        ins = shapely.contains_xy(g.buffer(-0.15), gx, gy)
        Q = np.column_stack([gx[ins], gy[ins]])
        if not len(Q):
            continue
        H = photo_votes.label_votes(np.column_stack([Q, hfn(Q[:, 0], Q[:, 1]) + 0.1])).sum(0)
        tot = int(H.sum()); road = int(H[13] + H[23] + H[24])
        if tot >= 30 and road >= 0.7 * tot:
            c = g.representative_point()
            out.append({"x": round(c.x, 2), "y": round(c.y, 2), "area": round(g.area, 1),
                        "road_votes": round(road / tot, 2)})
    return out


def main():
    o = np.load(os.path.join(WORK, "road_strip.npz"))
    s, t = o["s"], o["t"]
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    tL = np.interp(s, rp["s"], rp["tL"]); tR = np.interp(s, rp["s"], rp["tR"])
    un = unmarked_stretches(s, t, tL, tR)
    bands, rgb = red_bands(s, t, tL, tR)
    pc = photo_centre(o)
    fresh = fresh_asphalt(o, un, tL, tR)
    isl = removed_islands(un)
    json.dump({"unmarked": un, "red_bands": bands, "red_rgb": rgb, "photo_centre": pc,
               "fresh_asphalt": fresh, "removed_islands": isl},
              open(os.path.join(WORK, "markings_state.json"), "w"))
    import shapely
    print("fresh asphalt polygons", len(fresh), "%.0f m2" % sum(shapely.Polygon(r).area for r in fresh),
          "| islands removed since the survey:", [(i["x"], i["y"], i["area"]) for i in isl])
    print("photo centre line: support >= 0.45 on %.0f%% of the seen stations"
          % (100 * np.mean(np.array(pc["support"])[np.array(pc["seen"]) > 0.5] >= 0.45)))
    print("unmarked stretches:", ", ".join("%.0f-%.0f" % tuple(x) for x in un),
          "(%.0f m)" % sum(b - a for a, b in un))
    print("red bands:", len(bands), ["%s %.0f-%.0f w %.2f" % (b["side"], b["s"][0], b["s"][-1],
                                                              np.median(np.abs(np.array(b["t_in"]) - np.array(b["t_out"]))))
                                     for b in bands], "colour", rgb)


if __name__ == "__main__":
    main()
