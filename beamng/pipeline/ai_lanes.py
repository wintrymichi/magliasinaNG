"""Finish step ai_lanes: no AI lane over a drop.

Where two roads at different levels run side by side, the AI road of the upper one can be as wide as both: the
cantonale above Magliaso (690,-1046) has a lower lane 1.2-1.6 m down inside its AI road's width, and the car the
autotest drove along that AI road (scriptai, laptop runs 9 and 10 of the Ticino level; the span AI in runs 7 and 8)
went over the edge on the east side and landed on its roof in the lane below. The same place is in the known issues
of the map ("the AI road drops 4 m from the lower road to the upper one").

Each node of every AI road reads the road surfaces across its width (every QSTEP m out from the middle, the face
nearest the last height); a step over DROP between two samples is a drop. Where one lies inside the width, the
node moves away from it and the width shrinks so that the lane ends CLEAR m before it, never under MIN_W. The moves
are spread over the neighbouring nodes and fade to nothing at the road's ends (the junctions stay welded).

The street lamps are then kept out of the (fixed) AI roads: 17 of 2,108 stood inside an AI road's width, one 2.2 m
in the cantonale north of Pura (58.7,-748.7), where the autotest's car hit it and stood 40 s (laptop run 11), and the
known one at Pura (287,-892) the AI hit twice in the piano video. Each moves out to the road's half width + LAMP_CLEAR
with its lights; where the ground there is more than LAMP_DZ off the old foot (a wall, a bank) the lamp goes.

    python ai_lanes.py <root: the folder that holds levels/<name>/> [report.json]
"""
import json
import os
import sys
import time

import numpy as np

import bng
import optimize_level
from config import LEVEL_NAME
from road_mesh import TriSurface
from road_seams import _shapes

QSTEP = 0.25            # m between the samples across
CONT = 0.25             # m: a larger change between two samples is not the same surface
DROP = 0.5              # m: a change this large is a drop (kerbs, islands, crossfall stay under it)
CLEAR = 0.3             # m between the lane's edge and the drop
MIN_W = 3.0             # m: no AI road narrower
SEARCH = 2.5            # m further out on the free side, where the surface may go on beyond the old width
END_FADE = 6.0          # m from each end over which the move fades to 0
SPREAD = 2              # nodes either side that take a node's move too (the largest one wins)
ITEMS = "main/MissionGroup/AIRoads/items.level.json"
LAMPS = "main/MissionGroup/props/street_lights/items.level.json"
LAMP_CLEAR = 0.6        # m from the AI road's edge to a lamp post
LAMP_DZ = 0.8           # m: a new foot further from the old one in height is no place for the lamp
LIGHT_R = 3.0           # m: the lights of a lamp (its head) within this of the post


def surfaces(zi, lv):
    """TriSurface of the up faces of the road surfaces (no walls, no skirts)."""
    T = []
    for sn, text, pos in _shapes(zi, lv, "roads/surfaces"):
        V, N, UV, C, parts, node = optimize_level.parse(text)
        W = V + pos
        for mat, idx in parts:
            if mat == "mp_road_wall":
                continue
            t = W[idx[:, 0].reshape(-1, 3)]
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
            T.append(t[up])
    return TriSurface(np.concatenate(T)) if T else None


def walk(S, x, y, z, nx, ny, reach):
    """Per node, from the middle out along (nx, ny) every QSTEP up to reach: the distance of the first drop (inf if
    none) and how far the surface goes on without a step (the last continuous sample; a sample with no surface
    ends it without a drop)."""
    k = len(x)
    drop = np.full(k, np.inf)
    free = np.zeros(k)
    prev = z.copy()
    alive = np.isfinite(z)
    for o in np.arange(QSTEP, reach.max() + 1e-9, QSTEP):
        a = alive & (o <= reach)
        if not a.any():
            break
        h = np.full(k, np.nan)
        h[a] = S.height(x[a] + nx[a] * o, y[a] + ny[a] * o, "near", zhint=prev[a])
        same = a & np.isfinite(h) & (np.abs(h - prev) <= CONT)
        fell = a & np.isfinite(h) & (np.abs(h - prev) >= DROP)
        drop[fell] = o
        free[same] = o
        prev = np.where(same, h, prev)
        alive &= same
    return drop, free


def fix_road(S, N):
    """New nodes (n, 4) of one AI road, and how many were moved."""
    n = len(N)
    x, y, z, w = N[:, 0], N[:, 1], N[:, 2], N[:, 3]
    tx = np.gradient(x) if n > 2 else np.full(n, x[-1] - x[0])
    ty = np.gradient(y) if n > 2 else np.full(n, y[-1] - y[0])
    tl = np.maximum(np.hypot(tx, ty), 1e-9)
    lx, ly = -ty / tl, tx / tl                       # left of the direction of the nodes
    zc = S.height(x, y, "near", zhint=z)
    hw = w / 2
    dl, fl = walk(S, x, y, zc, lx, ly, hw + SEARCH)
    dr, fr = walk(S, x, y, zc, -lx, -ly, hw + SEARCH)
    shift = np.zeros(n)                              # along the left normal
    neww = w.copy()
    bad_l = dl < hw - CLEAR + 1e-9
    bad_r = dr < hw - CLEAR + 1e-9
    one = (bad_l ^ bad_r) & np.isfinite(zc)
    for i in np.flatnonzero(one):
        if bad_l[i]:                                 # the drop on the left: the span is [-fr, dl - CLEAR]
            hi, lo = dl[i] - CLEAR, -min(fr[i], hw[i] + SEARCH)
        else:
            hi, lo = min(fl[i], hw[i] + SEARCH), -(dr[i] - CLEAR)
        h = max(min(hw[i], (hi - lo) / 2), MIN_W / 2)
        c = hi - h if bad_l[i] else lo + h
        shift[i], neww[i] = c, 2 * h
    if not one.any():
        return N, 0
    # spread each move over SPREAD nodes either side (the largest wins), fade it out towards the ends
    big = np.zeros(n)
    wid = w.copy()
    for i in np.flatnonzero(one):
        for j in range(max(0, i - SPREAD), min(n, i + SPREAD + 1)):
            if abs(shift[i]) > abs(big[j]):
                big[j] = shift[i]
            wid[j] = min(wid[j], neww[i])
    cum = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    fade = np.clip(np.minimum(cum, cum[-1] - cum) / END_FADE, 0, 1)
    out = N.copy()
    out[:, 0] = x + lx * big * fade
    out[:, 1] = y + ly * big * fade
    out[:, 3] = w - (w - wid) * fade
    return out, int((np.abs(big * fade) > 0.05).sum())


def _write(zi, name, objs):
    p = zi.path(name)
    os.remove(p)                                     # a hard-linked copy of a released level stays as it was
    with open(p, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(o, separators=(",", ":")) + "\n" for o in objs))


def lamps_clear(zi, lv, S, roads, res):
    """Street lamps out of the AI roads' widths (see the module's docstring)."""
    name = f"{lv}/{LAMPS}"
    if name not in zi.NameToInfo:
        return
    from tunnels import Terrain
    ter = Terrain(os.path.join(zi.path(lv)))
    A, B, H = [], [], []
    for o in roads:
        N = np.asarray(o["nodes"], np.float64)
        A.append(N[:-1, :2]); B.append(N[1:, :2]); H.append(np.minimum(N[:-1, 3], N[1:, 3]) / 2)
    A, B, H = np.concatenate(A), np.concatenate(B), np.concatenate(H)
    D = B - A
    DD = np.maximum((D * D).sum(1), 1e-9)

    def deficit(p):
        """How far p lies inside the widest-reaching AI road near it, and the way out of it."""
        t = np.clip(((p - A) * D).sum(1) / DD, 0, 1)
        q = A + D * t[:, None]
        d = np.hypot(*(p - q).T)
        k = int(np.argmin(d - H))
        out = (p - q[k]) / d[k] if d[k] > 1e-6 else np.array([-D[k, 1], D[k, 0]]) / np.sqrt(DD[k])
        return H[k] + LAMP_CLEAR - d[k], out

    def ground(x, y, z):
        h = S.height([x], [y], "near", zhint=[z])[0]
        return h if np.isfinite(h) and abs(h - z) < 2 * LAMP_DZ else float(ter.sample([x], [y])[0])

    objs = [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]
    posts = [i for i, o in enumerate(objs) if o.get("class") == "TSStatic"]
    lights = [i for i, o in enumerate(objs) if o.get("class") != "TSStatic" and o.get("position")]
    LP = np.array([objs[i]["position"][:2] for i in lights]) if lights else np.zeros((0, 2))
    drop = set()
    for i in posts:
        p0 = np.asarray(objs[i]["position"], np.float64)
        p = p0[:2].copy()
        if deficit(p)[0] <= LAMP_CLEAR:              # beyond the edge already: the lamps stand there on purpose
            continue
        for _ in range(3):                           # out of one road can be into the next
            need, out = deficit(p)
            if need <= 0:
                break
            p = p + out * (need + 0.01)
        if np.allclose(p, p0[:2]):
            continue
        mine = [lights[j] for j in np.flatnonzero(np.hypot(*(LP - p0[:2]).T) < LIGHT_R)] if lights else []
        z = ground(p[0], p[1], p0[2] - 0.0)
        if deficit(p)[0] > 0 or abs(z - p0[2]) > LAMP_DZ:
            drop.update([i] + mine)
            res["lamps_removed"] += 1
            print(f"ai_lanes: lamp at {p0[0]:.1f},{p0[1]:.1f} removed (no room beside the road)", flush=True)
            continue
        v = np.r_[p - p0[:2], z - p0[2]]
        for j in [i] + mine:
            objs[j]["position"] = [float(a + b) for a, b in zip(objs[j]["position"], v)]
        res["lamps_moved"] += 1
        res["lamp_move_m_max"] = round(max(res["lamp_move_m_max"], float(np.hypot(*v[:2]))), 2)
        print(f"ai_lanes: lamp at {p0[0]:.1f},{p0[1]:.1f} moved {np.hypot(*v[:2]):.2f} m out, dz {v[2]:+.2f}", flush=True)
    if res["lamps_moved"] or res["lamps_removed"]:
        _write(zi, name, [o for k, o in enumerate(objs) if k not in drop])


def ai_lanes_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    res = {"roads": 0, "roads_moved": 0, "nodes_moved": 0, "move_m_max": 0.0, "lamps_moved": 0, "lamps_removed": 0,
           "lamp_move_m_max": 0.0}
    name = f"{lv}/{ITEMS}"
    if name not in zi.NameToInfo:
        print("ai_lanes: no AI roads", flush=True)
        return res
    S = surfaces(zi, lv)
    if S is None:
        print("ai_lanes: no road surfaces", flush=True)
        return res
    lines = [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]
    for o in lines:
        if o.get("class") != "DecalRoad" or len(o.get("nodes", [])) < 2:
            continue
        res["roads"] += 1
        N = np.asarray(o["nodes"], np.float64)
        M, k = fix_road(S, N)
        if k:                                        # once more: a moved node can meet the next drop
            M = fix_road(S, M)[0]
        if k:
            res["roads_moved"] += 1
            res["nodes_moved"] += k
            res["move_m_max"] = round(max(res["move_m_max"], float(np.hypot(*(M[:, :2] - N[:, :2]).T).max())), 2)
            o["nodes"] = [[round(float(v), 4) for v in r] for r in M]
            if res["roads_moved"] <= 20:
                i = int(np.argmax(np.hypot(*(M[:, :2] - N[:, :2]).T)))
                print(f"ai_lanes: {o.get('name')} {k} nodes moved, the most at {N[i, 0]:.0f},{N[i, 1]:.0f} "
                      f"by {np.hypot(*(M[i, :2] - N[i, :2])):.2f} m, width {N[i, 3]:.1f} -> {M[i, 3]:.1f}", flush=True)
    if res["roads_moved"]:
        _write(zi, name, lines)
    lamps_clear(zi, lv, S, [o for o in lines if o.get("class") == "DecalRoad" and len(o.get("nodes", [])) >= 2], res)
    res["seconds"] = round(time.time() - t0, 1)
    print("ai_lanes:", res, flush=True)
    if report:
        with open(report, "w") as f:
            json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    ai_lanes_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
