"""Trajectory-level pose solution from the per-panorama NCC volumes.

Each volume V_i(dh, dy, dx) scores heading offset and planar shift of panorama i
against the orthophoto. Along a straight road the score is a ridge (cross-track
well defined, along-track free), so corrections are solved jointly: the GPS/INS
error of one capture drives slowly, hence a Viterbi pass over the ordered
panoramas of the main capture run maximises sum_i V_i(state_i) with the state
allowed to change by at most MAX_STEP_XY / MAX_STEP_H per 10 m of travel.
Curves (ridges in other directions) then pin down the along-track error.
Panoramas of other runs (other date / direction) are solved locally with the
main-run solution as prior.
Writes work/poses.json and work/pose_corrections.png.
"""
import json, math, os
import numpy as np
from config import DATASET, WORK
from camera import rot_z
from geo import Grid

MAX_STEP_XY = 0.25      # m per 10 m of travel
MAX_STEP_H = 0.5        # deg per 10 m of travel
LOCAL_XY, LOCAL_H = 1.0, 1.0


def load():
    panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
    V, meta = [], []
    for p in panos:
        d = np.load(os.path.join(WORK, "ncc_vol", f"{p['index']:04d}.npz"))
        v = np.nan_to_num(d["vol"].astype(np.float32), nan=-1.0, posinf=-1.0, neginf=-1.0)
        V.append(v)
        meta.append(dict(heads=d["heads"], R=d["R_att"], pos0=d["pos0"], att=json.loads(str(d["att"]))))
    return panos, np.array(V), meta


def score(v):
    """Evidence volume: NCC above the panorama's own typical level, weighted by its contrast."""
    med = np.median(v)
    top = v.max()
    w = np.clip(top - 0.1, 0, None)
    return np.clip(v - med, 0, None) * (w / max(top - med, 1e-3))


SIGMA_XY = 0.10         # m, typical change of the GPS error per 10 m of travel
SIGMA_H = 0.25          # deg, typical change of the heading error per 10 m
BETA = 0.03             # NCC units charged for a 1-sigma change


def maxplus(C, axis, a):
    """M[..., j, ...] = max_k C[..., k, ...] - a (j-k)^2 along `axis` (exact, brute force)."""
    C = np.moveaxis(C, axis, -1)
    n = C.shape[-1]
    j = np.arange(n)
    pen = a * (j[:, None] - j[None, :]) ** 2            # (j, k)
    M = (C[..., None, :] - pen).max(-1)
    return np.moveaxis(M, -1, axis)


def argmaxplus(line, j, a):
    k = np.arange(len(line))
    return int(np.argmax(line - a * (j - k) ** 2))


def viterbi(E, steps, res, hstep):
    """Max-sum over the chain with quadratic smoothness (separable exact transforms)."""
    n = len(E)
    C = E[0].astype(np.float32)
    hist = [C.astype(np.float16)]
    coef = []
    for i in range(1, n):
        d = max(steps[i] / 10.0, 0.5)
        ax_ = BETA * (res / SIGMA_XY) ** 2 / d          # per squared cell
        ah = BETA * (hstep / SIGMA_H) ** 2 / d
        M = maxplus(C, 2, ax_)
        M = maxplus(M, 1, ax_)
        M = maxplus(M, 0, ah)
        C = (M + E[i]).astype(np.float32)
        C -= C.max()
        hist.append(C.astype(np.float16))
        coef.append((ax_, ah))
    state = np.unravel_index(np.argmax(C), C.shape)
    path = [state]
    for i in range(n - 1, 0, -1):
        Cp = hist[i - 1].astype(np.float32)
        ax_, ah = coef[i - 1]
        h, y, x = state
        Mx = maxplus(Cp, 2, ax_)
        My = maxplus(Mx, 1, ax_)
        h2 = argmaxplus(My[:, y, x], h, ah)
        y2 = argmaxplus(Mx[h2, :, x], y, ax_)
        x2 = argmaxplus(Cp[h2, y2, :], x, ax_)
        state = (h2, y2, x2)
        path.append(state)
    return path[::-1]


def main():
    panos, V, meta = load()
    h_cam = json.load(open(os.path.join(WORK, "camera_height.json")))["h_cam"]
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    heads = meta[0]["heads"]
    hstep = float(heads[1] - heads[0])
    m = V.shape[-1]
    lim = (m - 1) // 2
    res = 2 * 5.0 / (m - 1)
    s = np.array([p["route_dist_m"] for p in panos])
    rel = np.array([(p["heading_deg"] - p["road_bearing_deg"] + 180) % 360 - 180 for p in panos])
    main_run = np.where((np.abs(rel) < 45) & (np.array([p["date"] for p in panos]) == "2022-10"))[0]
    main_run = main_run[np.argsort(s[main_run])]
    E = np.array([score(V[i]) for i in main_run])
    pos0 = np.array([meta[i]["pos0"][:2] for i in main_run])
    steps = np.r_[0, np.hypot(*np.diff(pos0, axis=0).T)]
    path = viterbi(E, steps, res, hstep)
    sol = {}
    for i, st in zip(main_run, path):
        sol[i] = (float(heads[st[0]]), (st[2] - lim) * res, -(st[1] - lim) * res)
    # other runs: local search around the main-run correction interpolated at the same route distance
    ms = s[main_run]
    for i in range(len(panos)):
        if i in sol:
            continue
        j = main_run[np.argmin(np.abs(ms - s[i]))]
        dh0, dx0, dy0 = sol[j]
        hh = np.abs(heads - dh0) <= LOCAL_H + 1e-6
        yy, xx = np.mgrid[:m, :m]
        near = np.hypot((xx - lim) * res - dx0, -(yy - lim) * res - dy0) <= LOCAL_XY
        own = np.where(hh[:, None, None] & near[None], V[i], -9)
        kh, ky, kx = np.unravel_index(np.argmax(own), own.shape)
        sol[i] = (float(heads[kh]), (kx - lim) * res, -(ky - lim) * res) if own.max() > 0.15 else (dh0, dx0, dy0)
    out = []
    for i, p in enumerate(panos):
        dh, dx, dy = sol[i]
        kh = int(np.argmin(np.abs(heads - dh)))
        kx, ky = int(round(dx / res + lim)), int(round(-dy / res + lim))
        pos0 = meta[i]["pos0"]
        x, y = pos0[0] + dx, pos0[1] + dy
        z = float(dtm.sample([x], [y])[0]) + h_cam
        R = rot_z(-math.radians(dh)) @ meta[i]["R"]
        out.append(dict(index=p["index"], id=p["id"], date=p["date"], main_run=bool(i in set(main_run)),
                        pos=[x, y, z], R=R.tolist(), dx=dx, dy=dy, dh=dh, ncc_own=float(V[i, kh, ky, kx]),
                        ncc_max=float(V[i].max()), tilt=meta[i]["att"].get("tilt"),
                        heading_raw=p["heading_deg"], elevation_raw=p["elevation"],
                        dz_raw=float(p["elevation"] - z), route_dist=float(s[i])))
    json.dump(out, open(os.path.join(WORK, "poses.json"), "w"), indent=1)
    dx = np.array([o["dx"] for o in out]); dy = np.array([o["dy"] for o in out]); dh = np.array([o["dh"] for o in out])
    nc = np.array([o["ncc_own"] for o in out]); nm = np.array([o["ncc_max"] for o in out])
    print("corrections dx: mean %.2f sd %.2f | dy: mean %.2f sd %.2f | dh: mean %.2f sd %.2f" %
          (dx.mean(), dx.std(), dy.mean(), dy.std(), dh.mean(), dh.std()))
    print("NCC at solution: median %.3f (own max median %.3f); solution/max >= 0.8 for %d of %d" %
          (np.median(nc), np.median(nm), (nc >= 0.8 * nm).sum(), len(nc)))
    print("raw elevation - camera z: mean %.2f sd %.2f" % (np.mean([o["dz_raw"] for o in out]),
                                                           np.std([o["dz_raw"] for o in out])))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    mr = np.array([o["main_run"] for o in out])
    for a, val, lab in zip(ax, (dx, dy, dh), ("dx east (m)", "dy north (m)", "dheading (deg)")):
        a.plot(s[mr], val[mr], ".-", label="main run"); a.plot(s[~mr], val[~mr], "rx", label="other")
        a.set_ylabel(lab); a.grid(alpha=0.3)
    ax[3].plot(s, nm, "k.", ms=3, label="best NCC"); ax[3].plot(s, nc, "g.", ms=3, label="NCC at solution")
    ax[3].legend(); ax[3].grid(alpha=0.3); ax[3].set_xlabel("route distance (m)")
    fig.tight_layout(); fig.savefig(os.path.join(WORK, "pose_corrections.png"), dpi=90)


if __name__ == "__main__":
    main()
