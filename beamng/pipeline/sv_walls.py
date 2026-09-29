"""What the walls of the cadastral survey are made of, seen in the Street View panoramas (v2.2).

Until v2.1 every wall of the survey had the same regular stone-brick texture. Along the streets of the
Malcantone the retaining and garden walls are rubble stone (dry or mortared), board-formed concrete or
plastered. Here every survey wall ('muro' polygons and lines) within NEAR m of a road is sampled on
its outline, 0.1 m outside it, at mid height, and the samples are projected into the panoramas that
see them (sv_fetch.py; line of sight over the surface model). A sample counts where the segmentation
(sv_segment.py) labels the pixel as wall. Per wall piece, from the photo pixels of the samples:
- local contrast (the standard deviation of the luminance in a 7 x 7 window of the full panorama:
  the joints and the stones of a rubble wall) and colour (saturation, luminance);
- stone: high local contrast; concrete: low contrast and grey; plaster: low contrast and a colour.
Only the class leaves this step: dati/wall_materials.json {walls: [[x, y, class, n], ...]} (the middle
of the survey wall), read by walls.py.
    python sv_walls.py
"""
import json, os, pickle
import numpy as np
import shapely
from PIL import Image
from scipy.ndimage import uniform_filter
from scipy.spatial import cKDTree
from config import WORK
from geo import Grid
import camera

NEAR = 30.0
MAXD = 25.0
STEP = 1.0
CAM_H = 2.2
WALL = 6
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "wall_materials.json")


def wall_samples(av, roads, dtm):
    """Sample points of the survey walls near the roads: (P (n, 3), outward normals (n, 2), wall id (n,)),
    and the middle point of every wall."""
    walls = [g for g, _ in av["SOSF"].get("muro", [])] + \
            [g.buffer(0.15, cap_style="flat", join_style="mitre") for g, _ in av["SOLI"].get("muro", [])]
    rtree = cKDTree(roads)
    P, N, W, mids = [], [], [], []
    for wi, g in enumerate(walls):
        c = g.representative_point()
        mids.append((c.x, c.y))
        if rtree.query([c.x, c.y])[0] > NEAR:
            continue
        for poly in getattr(g, "geoms", [g]):
            if poly.geom_type != "Polygon":
                continue
            poly = shapely.geometry.polygon.orient(poly, 1.0)           # exterior counter-clockwise
            ring = shapely.segmentize(poly.exterior, STEP)
            pts = np.asarray(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            nxt = np.roll(pts, -1, 0)
            t = nxt - pts
            t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            nrm = np.column_stack([t[:, 1], -t[:, 0]])              # outward: right of a counter-clockwise ring
            pts = 0.5 * (pts + nxt)                                   # middle of each piece of the outline
            q = pts + nrm * 0.1
            lo = dtm.sample(q[:, 0], q[:, 1])
            hi = dtm.sample(pts[:, 0] - nrm[:, 0] * 1.0, pts[:, 1] - nrm[:, 1] * 1.0)
            top = np.maximum(hi, lo + 0.6)
            z = 0.5 * (lo + np.minimum(top, lo + 2.5))
            P.append(np.column_stack([q, z]))
            N.append(nrm)
            W.append(np.full(len(q), wi))
    return np.concatenate(P), np.concatenate(N), np.concatenate(W), np.array(mids)


def main():
    import network
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    segs, st, _ = network.load()
    road = np.array([segs[k]["kind"] == "road" for k in st["seg"]], bool)
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    P, N, Wid, mids = wall_samples(av, np.column_stack([st["x"][road], st["y"][road]]), dtm)
    print("wall samples", len(P), "walls", len(np.unique(Wid)), flush=True)
    tree = cKDTree(P[:, :2])
    info = json.load(open(os.path.join(WORK, "sv", "seg", "band.json")))
    conv = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                                       "attitude_convention.json")))
    sel = [p for p in json.load(open(os.path.join(WORK, "sv", "selected.json")))
           if os.path.exists(os.path.join(WORK, "sv", "seg", p["id"] + ".png"))]
    print(len(sel), "segmented panoramas", flush=True)
    feats = {}
    for k, p in enumerate(sel):
        idx = np.array(tree.query_ball_point([p["x"], p["y"]], MAXD), np.int64)
        if not len(idx):
            continue
        cam = np.array([p["x"], p["y"], float(dtm.sample(np.array([p["x"]]), np.array([p["y"]]))[0]) + CAM_H])
        v = cam[:2] - P[idx, :2]
        dist = np.linalg.norm(v, axis=1)
        facing = (v * N[idx]).sum(1) > 0.3 * dist
        idx = idx[facing & (dist > 2.0)]
        if not len(idx):
            continue
        Q = P[idx]
        d = Q - cam
        L = np.linalg.norm(d[:, :2], axis=1)
        occ = np.zeros(len(Q), bool)
        for t in np.linspace(0.05, 1.0, 16):
            R_ = cam + d * t
            occ |= (dsm.sample(R_[:, 0], R_[:, 1]) > R_[:, 2] + 0.35) & (L * (1 - t) > 0.8)
        idx, Q = idx[~occ], Q[~occ]
        if not len(idx):
            continue
        heading = p["heading_deg"] + camera.grid_convergence(p["lat"], p["lon"])
        R = camera.attitude_matrix(heading, p.get("pitch_deg", 0.0), p.get("roll_deg", 0.0), conv)
        dc = (Q - cam) @ R
        lab = np.asarray(Image.open(os.path.join(WORK, "sv", "seg", p["id"] + ".png")))
        Wl = info["width"]
        u, vv = camera.dir_cam_to_pixel(dc, Wl, Wl // 2)
        r0 = int(round((90.0 - info["top"]) / 180.0 * (Wl // 2)))
        rr, cc = np.round(vv).astype(int) - r0, np.round(u).astype(int) % Wl
        ok = (rr >= 0) & (rr < lab.shape[0])
        is_wall = np.zeros(len(Q), bool)
        is_wall[ok] = lab[rr[ok], cc[ok]] == WALL
        if not is_wall.any():
            continue
        img = np.asarray(Image.open(os.path.join(WORK, "sv", "pano", p["id"] + ".jpg")).convert("RGB"), np.float32) / 255.0
        H_, W_ = img.shape[:2]
        uf, vf = camera.dir_cam_to_pixel(dc[is_wall], W_, H_)
        lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        m1 = uniform_filter(lum, 7)
        m2 = uniform_filter(lum * lum, 7)
        sd = np.sqrt(np.clip(m2 - m1 * m1, 0, None))
        ri = np.clip(np.round(vf).astype(int), 0, H_ - 1)
        ci = np.round(uf).astype(int) % W_
        rgb = img[ri, ci]
        con = sd[ri, ci]
        for wi, c_, s_ in zip(Wid[idx[is_wall]], rgb, con):
            feats.setdefault(int(wi), []).append(np.r_[c_, s_])
        if k % 500 == 0:
            print("  %d/%d panoramas, %d walls seen" % (k + 1, len(sel), len(feats)), flush=True)
    out = []
    from collections import Counter
    cnt = Counter()
    for wi, F in feats.items():
        F = np.array(F)
        if len(F) < 6:
            continue
        rgb, con = F[:, :3], F[:, 3]
        mx, mn = rgb.max(1), rgb.min(1)
        sat = np.median((mx - mn) / np.maximum(mx, 1e-6))
        lum = np.median(rgb @ np.array([0.2126, 0.7152, 0.0722]))
        c50 = float(np.median(con))
        if c50 > 0.075:
            cls = "stone"
        elif sat < 0.10:
            cls = "concrete"
        else:
            cls = "plaster"
        cnt[cls] += 1
        med = np.median(rgb[(rgb @ np.array([0.2126, 0.7152, 0.0722])) >= np.percentile(rgb @ np.array([0.2126, 0.7152, 0.0722]), 50)], 0)
        out.append([round(float(mids[wi][0]), 2), round(float(mids[wi][1]), 2), cls, int(len(F)),
                    round(float(c50), 3), round(float(sat), 3), round(float(lum), 3), [round(float(v), 3) for v in med]])
    json.dump({"source": "Street View panoramas (classes only, no images)", "walls": out}, open(OUT, "w"),
              separators=(",", ":"))
    print("walls classified", len(out), dict(cnt))


if __name__ == "__main__":
    main()
