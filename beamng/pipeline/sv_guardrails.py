"""Guard rails of the whole road network seen in the Street View panoramas (v2.2).

Until v2.1 only the Strada Cantonale Magliaso - Pura had guard rails (the photos of the original
route); OpenStreetMap records 3 of them in the area. Here every edge of every road of the network is
looked at in the panoramas (sv_fetch.py) segmented by sv_segment.py:
- along both edges of every road line, every 2 m (the stations of network.py), the points where a rail
  would be (0.25 and 0.6 m outside the edge of the carriageway, 0.45 to 0.75 m above it) are projected
  into every panorama within MAXD m that sees them (line of sight over the surface model);
- each panorama votes: guard rail (the label under one of the points), or not;
- an edge station has a rail when at least 2 panoramas saw it (1 where only one did) and at least half
  of them voted for a rail; runs of rails with gaps up to GAP m are joined and runs shorter than
  MIN_RUN m dropped (a rail seen across a junction, a car's rim).
The rails are built on the road surface (guardrail_mesh.py) at 0.75 m, the Swiss standard height.
Output: dati/guardrails_sv.json ([{pts: [[x, y, z, top]], side, seg, votes}]; side +1 = left of the
direction of the line) and the counts per road for the review.
    python sv_guardrails.py
"""
import json, os
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from config import WORK
from geo import Grid
import camera
import network, network_surface

MAXD = 25.0
MIND = 2.5
CAM_H = 2.2
GAP = 8.0
MIN_RUN = 10.0
TOP = 0.75
OFFS = (0.25, 0.6)
HEIGHTS = (0.45, 0.6, 0.75)
GR = 4                                         # Mapillary Vistas: Guard Rail
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "guardrails_sv.json")


class Band:
    """The segmented band of one panorama (sv_segment.py) and its camera."""

    def __init__(self, p, info, conv, ground):
        self.lab = np.asarray(Image.open(os.path.join(WORK, "sv", "seg", p["id"] + ".png")))
        self.W = info["width"]
        self.Hf = self.W // 2
        self.r0 = int(round((90.0 - info["top"]) / 180.0 * self.Hf))
        self.cam = np.array([p["x"], p["y"], ground + CAM_H])
        heading = p["heading_deg"] + camera.grid_convergence(p["lat"], p["lon"])
        self.R = camera.attitude_matrix(heading, p.get("pitch_deg", 0.0), p.get("roll_deg", 0.0), conv)

    def labels(self, P):
        d = (P - self.cam) @ self.R
        u, v = camera.dir_cam_to_pixel(d, self.W, self.Hf)
        r = np.round(v).astype(int) - self.r0
        c = np.round(u).astype(int) % self.W
        ok = (r >= 0) & (r < self.lab.shape[0])
        out = np.full(len(P), 255, np.uint8)
        out[ok] = self.lab[r[ok], c[ok]]
        return out


def visible(cam, P, dsm, skip=1.0, margin=0.35, n=20):
    d = P - cam
    L = np.linalg.norm(d[:, :2], axis=1)
    occ = np.zeros(len(P), bool)
    for t in np.linspace(0.05, 1.0, n):
        Q = cam + d * t
        occ |= (dsm.sample(Q[:, 0], Q[:, 1]) > Q[:, 2] + margin) & (L * (1 - t) > skip)
    return ~occ


def main():
    segs, st, _ = network.load()
    ns = network_surface.load()
    z, c, nx, ny = ns["z"], ns["c"], ns["nx"], ns["ny"]
    w = st["width"]
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    info = json.load(open(os.path.join(WORK, "sv", "seg", "band.json")))
    conv = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                                       "attitude_convention.json")))
    sel = [p for p in json.load(open(os.path.join(WORK, "sv", "selected.json")))
           if os.path.exists(os.path.join(WORK, "sv", "seg", p["id"] + ".png"))]
    print(len(sel), "segmented panoramas", flush=True)
    road = np.array([segs[k]["kind"] == "road" for k in st["seg"]], bool)
    bridge = np.array([segs[k]["bridge"] for k in st["seg"]], bool)
    idx = np.flatnonzero(road & ~bridge)
    votes = {1: np.zeros((len(z), 2), np.int32), -1: np.zeros((len(z), 2), np.int32)}   # (seen, rail)
    tree = cKDTree(np.column_stack([st["x"][idx], st["y"][idx]]))
    for k, p in enumerate(sel):
        near = idx[tree.query_ball_point([p["x"], p["y"]], MAXD)]
        if not len(near):
            continue
        g = float(dtm.sample(np.array([p["x"]]), np.array([p["y"]]))[0])
        band = Band(p, info, conv, g)
        for side in (1, -1):
            seen_any = np.zeros(len(near), bool)
            rail_any = np.zeros(len(near), bool)
            for off in OFFS:
                t = side * (0.5 * w[near] + off)
                ex, ey = st["x"][near] + nx[near] * t, st["y"][near] + ny[near] * t
                ez = z[near] + c[near] * np.clip(t, -0.5 * w[near], 0.5 * w[near])
                for h in HEIGHTS:
                    P = np.column_stack([ex, ey, ez + h])
                    dist = np.linalg.norm(P - band.cam, axis=1)
                    ok = (dist > MIND) & (dist < MAXD)
                    if not ok.any():
                        continue
                    vis = np.zeros(len(P), bool)
                    vis[ok] = visible(band.cam, P[ok], dsm)
                    lab = band.labels(P)
                    seen = vis & (lab != 255)
                    seen_any |= seen
                    rail_any |= seen & (lab == GR)
            votes[side][near[seen_any], 0] += 1
            votes[side][near[rail_any], 1] += 1
        if k % 500 == 0:
            print("  %d/%d panoramas" % (k + 1, len(sel)), flush=True)
    runs = []
    for s_i, s in enumerate(segs):
        if s["kind"] != "road" or s["bridge"] or s["n"] < 2:
            continue
        a, n = s["first"], s["n"]
        for side in (1, -1):
            v = votes[side][a:a + n]
            rail = (v[:, 1] >= 1) & (((v[:, 0] >= 2) & (v[:, 1] * 2 >= v[:, 0]) & (v[:, 1] >= 2)) | (v[:, 0] == 1))
            if not rail.any():
                continue
            ss = st["s"][a:a + n]
            # join gaps up to GAP m
            on = np.flatnonzero(rail)
            groups, cur = [], [on[0]]
            for i in on[1:]:
                if ss[i] - ss[cur[-1]] <= GAP:
                    cur.append(i)
                else:
                    groups.append(cur)
                    cur = [i]
            groups.append(cur)
            for gi in groups:
                i0, i1 = gi[0], gi[-1]
                if ss[i1] - ss[i0] < MIN_RUN:
                    continue
                j = np.arange(a + i0, a + i1 + 1)
                t = side * (0.5 * w[j] + 0.35)
                P = np.column_stack([st["x"][j] + nx[j] * t, st["y"][j] + ny[j] * t,
                                     z[j] + c[j] * np.clip(t, -0.5 * w[j], 0.5 * w[j]), np.full(len(j), TOP)])
                runs.append({"pts": np.round(P, 3).tolist(), "side": int(side), "seg": s_i,
                             "name": s["name"], "length": round(float(ss[i1] - ss[i0]), 1),
                             "votes": [int(votes[side][j, 0].sum()), int(votes[side][j, 1].sum())]})
    json.dump(runs, open(OUT, "w"), separators=(",", ":"))
    seen = sum(int((votes[s][:, 0] > 0).sum()) for s in (1, -1))
    print("edge stations seen", seen, "of", 2 * len(idx), "; guard rail runs", len(runs), "km",
          round(sum(r["length"] for r in runs) / 1000, 2))
    json.dump({"stations_seen": seen, "stations": 2 * int(len(idx)),
               "seen_by_seg": {int(k): int(v) for k, v in zip(*np.unique(st["seg"][np.flatnonzero(
                   (votes[1][:, 0] > 0) | (votes[-1][:, 0] > 0))], return_counts=True))}},
              open(os.path.join(WORK, "sv", "guardrail_coverage.json"), "w"))


if __name__ == "__main__":
    main()
