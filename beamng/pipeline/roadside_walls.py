"""Retaining walls along the Strada Cantonale that the cadastral survey does not contain.

Geometry (DTM): at every road-profile station and side, the swissALTI3D profile beyond
the carriageway edge is scanned for a steep rise (> 55 deg over >= 0.6 m); the face
position is where the rise starts, the crest where the slope falls below 30 deg.
Photos: points on that face (0.4 m .. min(crest, 3 m) above road level) are projected
into the dataset views (horizon + 25 deg up) of the panoramas 3-20 m away; a station
is a wall when >= 35 % of its visible samples are labelled 'Wall' (rock cuttings are
'Terrain'/'Mountain', banks 'Vegetation'). Runs shorter than 3 m are dropped, gaps
< 3 m bridged. Stations already covered by a cadastral wall are skipped.
Output: work/roadside_walls.json [{side, pts: [[x, y, z_base, z_top], ...]}]
"""
import json, os, pickle
import numpy as np
import shapely
from PIL import Image
from scipy.ndimage import binary_closing, label, median_filter
from config import WORK, DATASET
from geo import Grid
import camera

WALL, MOUNT, TERR, VEG = 6, 25, 29, 30
LEVELS = [0.4, 0.9, 1.5, 2.2, 3.0, 4.0, 5.0, 6.0]
D_STEP = 0.25


def main():
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    s, C, N, tL, tR = rp["s"], rp["C"], rp["N"], rp["tL"], rp["tR"]
    openL, openR = rp["openL"], rp["openR"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    av_walls = shapely.union_all([g.buffer(0.6) for g, _ in av["SOSF"].get("muro", [])] +
                                 [g.buffer(0.6) for g, _ in av["SOLI"].get("muro", [])])
    dd = np.arange(0, 4.01, D_STEP)
    cand = []                                   # (side_idx, station, face_offset, z_edge, crest_h)
    for k, (edge, sg, opn) in enumerate(((tL, 1, openL), (tR, -1, openR))):
        xy = C[:, None, :] + N[:, None, :] * (edge[:, None] + sg * dd[None, :])[..., None]
        z = dtm.sample(xy[..., 0].ravel(), xy[..., 1].ravel()).reshape(xy.shape[:2])
        ze = z[:, 0]
        rise = z - ze[:, None]
        slope = np.gradient(z, D_STEP, axis=1)
        for i in range(len(s)):
            if opn[i]:
                continue
            steep = slope[i] > np.tan(np.radians(55))
            if not steep[:9].any():                      # the rise must start within 2 m of the edge
                continue
            j0 = int(np.argmax(steep))
            j1 = j0
            while j1 + 1 < len(dd) and slope[i, j1 + 1] > np.tan(np.radians(45)):
                j1 += 1
            h = rise[i, j1] - rise[i, j0]
            if h < 0.6:
                continue
            face_xy = C[i] + N[i] * (edge[i] + sg * dd[j0])
            if av_walls.contains(shapely.Point(face_xy)):
                continue
            cand.append((k, i, dd[j0], ze[i] + rise[i, j0], min(h, 8.0)))
    print("DTM step candidates", len(cand))
    votes = {}
    by_station = {}
    for c in cand:
        by_station.setdefault((c[0], c[1]), c)
    keys = list(by_station)
    pts, meta = [], []
    for (k, i) in keys:
        _, _, dface, zb, h = by_station[(k, i)]
        sg = 1 if k == 0 else -1
        edge = tL[i] if k == 0 else tR[i]
        xy = C[i] + N[i] * (edge + sg * (dface + 0.15))
        for li, hh in enumerate(LEVELS):
            if hh > h + 0.3:
                break
            pts.append([xy[0], xy[1], zb + hh]); meta.append((k, i, li))
    pts = np.array(pts)
    meta = np.array(meta, dtype=int)
    hit = np.zeros(len(pts)); vis = np.zeros(len(pts))
    cache = {}
    for p in poses:
        rec = D[p["index"]]
        d = np.hypot(pts[:, 0] - p["pos"][0], pts[:, 1] - p["pos"][1])
        near = np.where((d > 3) & (d < 20))[0]
        if len(near) == 0:
            continue
        seen = np.zeros(len(near), bool)
        for pitch in (0, 25):
            for dn, rel in camera.VIEW_REL.items():
                c, r, ok = camera.world_to_view(pts[near], p["pos"], p["R"], rec, rel, pitch)
                inb = ok & (c >= 6) & (c < 1594) & (r >= 6) & (r < 1194) & ~seen
                if not inb.any():
                    continue
                f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p{pitch:02d}.png")
                if f not in cache:
                    if len(cache) > 48:
                        cache.clear()
                    cache[f] = np.asarray(Image.open(f)) if os.path.exists(f) else None
                sgm = cache[f]
                if sgm is None:
                    continue
                ci, ri = c[inb].astype(int), r[inb].astype(int)
                w = np.zeros(len(ci), bool)
                for du in (-5, 0, 5):
                    for dv in (-5, 0, 5):
                        w |= sgm[ri + dv, ci + du] == WALL
                idx = near[inb]
                hit[idx] += w; vis[idx] += 1
                seen[np.where(inb)[0]] = True
    sup = {}
    lev = {}
    for (k, i, li), hv, vv in zip(map(tuple, meta), hit, vis):
        if li <= 1:                                        # presence decided on the lower part
            a = sup.setdefault((k, i), [0, 0])
            a[0] += hv; a[1] += vv
        if vv >= 2 and hv / vv >= 0.3:
            lev[(k, i)] = max(lev.get((k, i), 0.0), LEVELS[li])
    walls = []
    for k in (0, 1):
        flag = np.zeros(len(s), bool)
        for (kk, i), (hv, vv) in sup.items():
            if kk == k and vv >= 3 and hv / vv >= 0.35:
                flag[i] = True
        flag = binary_closing(flag, structure=np.ones(7))
        lab, n = label(flag)
        sg = 1 if k == 0 else -1
        edge = tL if k == 0 else tR
        for q in range(1, n + 1):
            ii = np.where(lab == q)[0]
            if s[ii[-1]] - s[ii[0]] < 3.0:
                continue
            face = np.array([by_station.get((k, i), (0, 0, 0.0, np.nan, np.nan))[2] for i in ii])
            zb = np.array([by_station.get((k, i), (0, 0, 0, np.nan, np.nan))[3] for i in ii])
            h = np.array([by_station.get((k, i), (0, 0, 0, np.nan, np.nan))[4] for i in ii])
            ok = ~np.isnan(zb)
            if ok.sum() < 3:
                continue
            face = np.interp(s[ii], s[ii][ok], face[ok]); zb = np.interp(s[ii], s[ii][ok], zb[ok])
            h = np.interp(s[ii], s[ii][ok], h[ok])
            ptop = np.array([lev.get((k, i), np.nan) for i in ii])
            if (~np.isnan(ptop)).sum() >= 2:
                ptop = np.interp(s[ii], s[ii][~np.isnan(ptop)], ptop[~np.isnan(ptop)])
                h = np.minimum(h, ptop + 0.35)             # photo: highest level still seen as wall
            face = median_filter(face, 7, mode="nearest")
            h = median_filter(h, 9, mode="nearest")
            h = median_filter(h, 17, mode="nearest")                    # 8 m: crest follows the wall, not noise
            from scipy.ndimage import gaussian_filter1d as _g
            h = _g(h, 3, mode="nearest")
            xy = C[ii] + N[ii] * (edge[ii] + sg * face)[:, None]
            walls.append({"side": sg, "s0": float(s[ii[0]]), "s1": float(s[ii[-1]]),
                          "pts": np.column_stack([xy, zb, zb + h]).round(3).tolist(),
                          "support": float(np.mean([sup[(k, i)][0] / max(sup[(k, i)][1], 1) for i in ii if (k, i) in sup]))})
    json.dump(walls, open(os.path.join(WORK, "roadside_walls.json"), "w"))
    print("roadside walls", len(walls), "length %.0f m" % sum(w["s1"] - w["s0"] for w in walls),
          "| mean height %.2f m" % np.mean([np.mean(np.array(w["pts"])[:, 3] - np.array(w["pts"])[:, 2]) for w in walls]))


if __name__ == "__main__":
    main()
