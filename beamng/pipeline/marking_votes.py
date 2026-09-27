"""Photo evidence for road markings: multi-view vote of the 'Lane Marking' classes.

1. Road strip grid (road_strip.npz: s every 0.1 m x t every 0.05 m). Every cell 3-16 m
   from a panorama is projected with the calibrated pose into that panorama's horizon
   views (Mask2Former labels). The panorama 'sees' the cell when the pixel is a ground
   class (a parked car or a wall in front hides it). It is a 'hit' when a lane-marking
   class (23 crosswalk, 24 general) lies within +-2 px.
   -> work/marking_votes.npz {hits, vis (uint16, strip shape)}
2. The same test for sample points (5 cm grid) inside every polygon of markings_raster.json.
   -> work/marking_poly_votes.json [{hit, vis, panos}] (same order as the polygons)
"""
import json, os
import numpy as np
import cv2
import shapely
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, DATASET
from geo import Grid
import camera

MARK = (23, 24)
GROUND = (2, 7, 8, 9, 10, 11, 13, 14, 15, 23, 24, 36, 41, 43)
D_MIN, D_MAX = 3.0, 16.0
VW, VH = 1600, 1200


class Views:
    """Label images of the horizon views of one panorama: ground mask and dilated marking mask."""
    def __init__(self, rec):
        self.v = {}
        for dn in camera.VIEW_REL:
            f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
            if not os.path.exists(f):
                continue
            seg = np.asarray(Image.open(f))
            ground = np.isin(seg, GROUND)
            mark = cv2.dilate(np.isin(seg, MARK).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            self.v[dn] = (ground, mark)

    def vote(self, P3, pos, R, rec):
        """-> (seen, hit) boolean arrays for world points P3 (n,3)."""
        seen = np.zeros(len(P3), bool); hit = np.zeros(len(P3), bool)
        for dn, rel in camera.VIEW_REL.items():
            if dn not in self.v:
                continue
            cc, rr, ok = camera.world_to_view(P3, pos, R, rec, rel, 0)
            inb = ok & (cc >= 0) & (cc < VW - 0.5) & (rr >= 0) & (rr < VH - 0.5) & ~seen
            if not inb.any():
                continue
            k = np.where(inb)[0]
            ci = np.clip(np.round(cc[k]).astype(int), 0, VW - 1); ri = np.clip(np.round(rr[k]).astype(int), 0, VH - 1)
            ground, mark = self.v[dn]
            g = ground[ri, ci] | mark[ri, ci]
            seen[k[g]] = True
            hit[k[g]] = mark[ri[g], ci[g]]
        return seen, hit


def main():
    st = np.load(os.path.join(WORK, "road_strip.npz"))
    s, t, X, Y, Nx, Ny = st["s"], st["t"], st["X"], st["Y"], st["Nx"], st["Ny"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)

    def zfn(x, y):
        r, c = dtm.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(zs, [r, c], order=1, mode="nearest")

    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    hits = np.zeros((len(s), len(t)), np.uint16); vis = np.zeros((len(s), len(t)), np.uint16)
    polys = json.load(open(os.path.join(WORK, "markings_raster.json")))
    samples = []
    for m in polys:
        pg = shapely.Polygon(m["rings"][0])
        x0, y0, x1, y1 = pg.bounds
        gx, gy = np.meshgrid(np.arange(x0 + 0.025, x1, 0.05), np.arange(y0 + 0.025, y1, 0.05))
        inside = shapely.contains_xy(pg, gx, gy)
        P = np.column_stack([gx[inside], gy[inside]])
        if len(P) == 0:
            c = pg.representative_point(); P = np.array([[c.x, c.y]])
        if len(P) > 400:
            P = P[np.linspace(0, len(P) - 1, 400).astype(int)]
        samples.append(np.column_stack([P, zfn(P[:, 0], P[:, 1]) + 0.02]))
    cent = np.array([S[:, :2].mean(0) for S in samples])
    pv = [{"hit": 0, "vis": 0, "panos": 0} for _ in polys]
    for n, p in enumerate(poses):
        rec = D[p["index"]]
        pos = np.array(p["pos"]); R = np.array(p["R"])
        rows = np.where(np.hypot(X - pos[0], Y - pos[1]) < D_MAX + 7.5)[0]
        views = Views(rec)
        if len(rows):
            r0, r1 = rows.min(), rows.max() + 1
            WX = X[r0:r1, None] + Nx[r0:r1, None] * t[None, :]
            WY = Y[r0:r1, None] + Ny[r0:r1, None] * t[None, :]
            d = np.hypot(WX - pos[0], WY - pos[1])
            ii, jj = np.where((d > D_MIN) & (d < D_MAX))
            if len(ii):
                P3 = np.column_stack([WX[ii, jj], WY[ii, jj], zfn(WX[ii, jj], WY[ii, jj]) + 0.02])
                seen, hit = views.vote(P3, pos, R, rec)
                vis[r0 + ii[seen], jj[seen]] += 1
                hits[r0 + ii[hit], jj[hit]] += 1
        near = np.where(np.hypot(cent[:, 0] - pos[0], cent[:, 1] - pos[1]) < D_MAX + 2)[0]
        for q in near:
            S = samples[q]
            d = np.hypot(S[:, 0] - pos[0], S[:, 1] - pos[1])
            ok = (d > D_MIN) & (d < D_MAX)
            if not ok.any():
                continue
            seen, hit = views.vote(S[ok], pos, R, rec)
            if seen.sum() >= max(1, 0.3 * ok.sum()):
                pv[q]["vis"] += int(seen.sum()); pv[q]["hit"] += int(hit.sum()); pv[q]["panos"] += 1
        if n % 50 == 0:
            print("pano", n, "/", len(poses), flush=True)
    np.savez_compressed(os.path.join(WORK, "marking_votes.npz"), hits=hits, vis=vis, s=s, t=t)
    json.dump(pv, open(os.path.join(WORK, "marking_poly_votes.json"), "w"))
    sup = hits / np.maximum(vis, 1)
    print("strip cells seen by >= 2 panoramas: %.0f%%" % (100 * np.mean(vis >= 2)),
          "marking cells (support >= 0.5, vis >= 2): %.2f%%" % (100 * np.mean((sup >= 0.5) & (vis >= 2))))
    ps = np.array([v["hit"] / max(v["vis"], 1) for v in pv]); pn = np.array([v["panos"] for v in pv])
    print("polygons seen by >= 2 panoramas", int((pn >= 2).sum()), "/", len(pv),
          "supported (>= 0.3)", int(((ps >= 0.3) & (pn >= 2)).sum()),
          "contradicted (< 0.1)", int(((ps < 0.1) & (pn >= 2)).sum()))


if __name__ == "__main__":
    main()
