"""Transverse and special road markings vectorised from the 10 cm SWISSIMAGE.

Inside the surveyed carriageway / sidewalks within CORRIDOR m of the route:
  yellow paint (Swiss crossings, bus stops, parking bans): HSV hue 15-35, sat > 90, val > 120
  white paint (stop / give-way lines, triangles, arrows, text): white top-hat of the luminance
     (1.2 m kernel) on low-saturation pixels, excluding 0.35 m around the centre and edge
     lines that are modelled separately.
Components are cleaned (open/close), filtered by area (0.08-80 m2) and vectorised
(contours simplified to 3 cm). Output: work/markings_raster.json [{color, rings}].
"""
import json, os, pickle
import numpy as np
import cv2
import shapely
from config import WORK
import ortho

CORRIDOR = 40.0
RES = 0.1
BLOCK = 120.0


def main():
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    track = shapely.LineString(rp["center"])
    corr = track.buffer(CORRIDOR)
    paved = shapely.union_all([g for cls in ("strada_sentiero", "marciapiede", "altro_rivestimento_duro")
                               for g, _ in av["LCSF"].get(cls, []) if g.intersects(corr)]).intersection(corr)
    paved_in = paved.buffer(-0.15)
    # white paint only on the carriageway interior (edges, kerbs, driveways give false positives)
    carriage = shapely.union_all([g for g, _ in av["LCSF"].get("strada_sentiero", []) if g.intersects(corr)])
    carriage_in = carriage.intersection(corr).buffer(-0.6)
    # already modelled longitudinal lines
    mk = json.load(open(os.path.join(WORK, "markings.json")))
    st = np.load(os.path.join(WORK, "road_strip.npz"))
    lines = []
    for tr in mk["tracks"]:
        s = np.array(tr["s"]); t = np.array(tr["t"])
        for a, b in tr["segments"]:
            ss = np.linspace(a, b, max(2, int((b - a) / 0.5) + 1))
            tt = np.interp(ss, s, t)
            x = np.interp(ss, st["s"], st["X"]) + np.interp(ss, st["s"], st["Nx"]) * tt
            y = np.interp(ss, st["s"], st["Y"]) + np.interp(ss, st["s"], st["Ny"]) * tt
            lines.append(shapely.LineString(np.column_stack([x, y])))
    ph = json.load(open(os.path.join(WORK, "markings_photo.json")))
    for side in ("edge_left", "edge_right"):
        s = np.array(ph[side]["s"]); t = np.array(ph[side]["t"]); sup = np.array(ph[side]["support"])
        on = sup >= 0.5
        idx = np.where(on)[0]
        if len(idx) > 1:
            P = rp["C"][idx] + rp["N"][idx] * t[idx][:, None]
            for part in np.split(np.arange(len(idx)), np.where(np.diff(idx) > 3)[0] + 1):
                if len(part) > 1:
                    lines.append(shapely.LineString(P[part]))
    known = shapely.union_all([l.buffer(0.35) for l in lines]) if lines else shapely.Polygon()
    x0, y0, x1, y1 = paved.bounds
    out = []
    for bx in np.arange(x0, x1, BLOCK):
        for by in np.arange(y0, y1, BLOCK):
            box = shapely.box(bx, by, bx + BLOCK, by + BLOCK)
            region = paved_in.intersection(box)
            if region.is_empty or region.area < 5:
                continue
            img = ortho.patch(bx, by, bx + BLOCK, by + BLOCK, RES)
            H, W = img.shape[:2]
            ys, xs = np.mgrid[0:H, 0:W]
            X = bx + (xs + 0.5) * RES; Y = by + BLOCK - (ys + 0.5) * RES
            inside = shapely.contains_xy(region, X, Y)
            inside_c = shapely.contains_xy(carriage_in.intersection(box), X, Y)
            near_known = shapely.contains_xy(known, X, Y)
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            L = img.astype(np.float32).mean(-1)
            yellow = (hsv[..., 0] >= 15) & (hsv[..., 0] <= 35) & (hsv[..., 1] > 90) & (hsv[..., 2] > 120) & inside
            top = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
            white = (top > 28) & (hsv[..., 1] < 60) & (L > 150) & inside_c & ~near_known & ~yellow
            for color, m in (("yellow", yellow), ("white", white)):
                m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
                m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                n, lab, stt, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
                for k in range(1, n):
                    area = stt[k][4] * RES * RES
                    if area < 0.08 or area > 80:
                        continue
                    if color == "white" and (area < 0.1 or area > 4.0 or max(stt[k][2], stt[k][3]) * RES > 5.0):
                        continue
                    if color == "white" and area > 1.0:
                        # compact, well-filled blobs are vehicles seen from above, not paint
                        comp_pts = np.column_stack(np.where(lab == k)).astype(np.float32)
                        (cx_, cy_), (w_, h_), _ = cv2.minAreaRect(comp_pts)
                        aspect = max(w_, h_) / max(min(w_, h_), 1)
                        fill = stt[k][4] / max(w_ * h_, 1)
                        if aspect < 3.0 and fill > 0.55:
                            continue
                    comp = (lab == k).astype(np.uint8)
                    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for c in cnts:
                        if len(c) < 3:
                            continue
                        pts = c[:, 0, :].astype(float)
                        wx = bx + (pts[:, 0] + 0.5) * RES; wy = by + BLOCK - (pts[:, 1] + 0.5) * RES
                        poly = shapely.Polygon(np.column_stack([wx, wy])).buffer(0.02).simplify(0.03)
                        if poly.is_empty or poly.area < 0.06:
                            continue
                        # thin, very long white blobs are usually not paint (kerbs, sunlit edges)
                        if color == "white":
                            mrr = poly.minimum_rotated_rectangle
                            ex = np.asarray(mrr.exterior.coords)
                            e1, e2 = np.linalg.norm(ex[1] - ex[0]), np.linalg.norm(ex[2] - ex[1])
                            if max(e1, e2) > 12 and min(e1, e2) < 0.35:
                                continue
                        for pg in getattr(poly, "geoms", [poly]):
                            out.append({"color": color, "rings": [np.asarray(pg.exterior.coords).round(3).tolist()]})
    json.dump(out, open(os.path.join(WORK, "markings_raster.json"), "w"))
    print("marking polygons", len(out), {c: sum(1 for o in out if o["color"] == c) for c in ("yellow", "white")},
          "area %.0f m2" % sum(shapely.Polygon(o["rings"][0]).area for o in out))


if __name__ == "__main__":
    main()
