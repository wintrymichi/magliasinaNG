"""Edge lines (and centre-line check) by multi-view voting of 'Lane Marking - General'.

Candidates: every 0.5 m station, both sides, offsets 0.10..0.70 m inside the surveyed
carriageway edge, on the road surface. Projected with the calibrated poses into the
horizon views of panoramas 3-15 m away; a vote when the pixel (3 px) is class 24.
Per station/side the best offset is kept; painted where support >= 0.5.
Output: work/markings_photo.json {edge_left, edge_right: {s, t, support}}
"""
import json, os
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates
from config import WORK, DATASET
from geo import Grid
import camera

LM = 24
OFFS = np.array([0.10, 0.25, 0.40, 0.55, 0.70])


def main():
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    s, C, N, tL, tR = rp["s"], rp["C"], rp["N"], rp["tL"], rp["tR"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zs = gaussian_filter(dtm.a, 1.0)
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    out = {}
    cache = {}
    for name, edge, sg in (("edge_left", tL, -1), ("edge_right", tR, 1)):
        cand = C[:, None, :] + N[:, None, :] * (edge[:, None] + sg * OFFS[None, :])[..., None]
        r, c = dtm.rc(cand[..., 0], cand[..., 1])
        cz = map_coordinates(zs, [r.ravel(), c.ravel()], order=1, mode="nearest").reshape(r.shape) + 0.02
        hit = np.zeros(cand.shape[:2]); vis = np.zeros(cand.shape[:2])
        P3all = np.concatenate([cand, cz[..., None]], -1)
        for p in poses:
            rec = D[p["index"]]
            d = np.hypot(cand[..., 0] - p["pos"][0], cand[..., 1] - p["pos"][1])
            near = (d > 3) & (d < 15)
            if not near.any():
                continue
            ii, jj = np.where(near)
            P3 = P3all[ii, jj]
            seen = np.zeros(len(P3), bool)
            for dn, rel in camera.VIEW_REL.items():
                cc, rr, ok = camera.world_to_view(P3, p["pos"], p["R"], rec, rel, 0)
                inb = ok & (cc >= 3) & (cc < 1597) & (rr >= 3) & (rr < 1197) & ~seen
                if not inb.any():
                    continue
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p00.png")
                if f not in cache:
                    if len(cache) > 48:
                        cache.clear()
                    cache[f] = np.asarray(Image.open(f)) if os.path.exists(f) else None
                sgm = cache[f]
                if sgm is None:
                    continue
                ci, ri = cc[inb].astype(int), rr[inb].astype(int)
                w = np.zeros(len(ci), bool)
                for du in (-3, 0, 3):
                    for dv in (-3, 0, 3):
                        w |= sgm[ri + dv, ci + du] == LM
                k = np.where(inb)[0]
                hit[ii[k], jj[k]] += w; vis[ii[k], jj[k]] += 1
                seen[k] = True
        sup = hit / np.maximum(vis, 1)
        best = np.argmax(np.where(vis >= 2, sup, -1), 1)
        bs = sup[np.arange(len(s)), best]
        bv = vis[np.arange(len(s)), best]
        t_line = edge + sg * OFFS[best]
        out[name] = {"s": s.round(2).tolist(), "t": t_line.round(3).tolist(), "support": bs.round(3).tolist(),
                     "visible": bv.astype(int).tolist()}
        print(name, "stations painted (support>=0.5): %.0f%%" % (100 * np.mean(bs[bv >= 2] >= 0.5)),
              "median offset inside edge %.2f m" % np.median(OFFS[best][bs >= 0.5]) if (bs >= 0.5).any() else "")
    json.dump(out, open(os.path.join(WORK, "markings_photo.json"), "w"))


if __name__ == "__main__":
    main()
