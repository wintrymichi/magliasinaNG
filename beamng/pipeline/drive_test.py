"""Virtual drive test of every road and path of a built level (v2.2), without the game.

A car is driven along the right lane of every line of the network (network.py; both directions on
roads of two lanes, the middle of narrow roads and paths) at the speed of its class, over the surfaces
of the level as written: the top faces of the road and bridge meshes (the one nearest the profile of
network_surface.py where a bridge passes over a road) and the terrain (the higher of the two, as a
tyre would touch them).
Car: wheelbase 2.6 m, track 1.55 m; each wheel a quarter car (sprung 350 kg, unsprung 40 kg, spring
30 kN/m, damper 3 kN s/m, tyre 200 kN/m), its road input the highest point of the surface under the
tyre (a small patch around the contact point: a kerb is felt when the tyre reaches it). The linear
model is run with scipy (bilinear discretisation) and reports:
- STEP: a step under a tyre higher than STEP_M within 0.1 m (a kerb or a seam across the lane);
- LIFT: a wheel leaving the ground (the tyre would have to pull: dynamic deflection beyond the static);
- HARD: a vertical acceleration of the body above HARD_G;
- HOLE: a wheel inside the carriageway with no road face under it (it drops to the terrain);
- TWIST: a sudden change of roll or pitch of the car (cross slope or grade breaking within 1 m).
At a dead end the last DEAD_END m are not counted: the wheels ahead of the car are past the end of the
road there; nor are the last EDGE_MARGIN m before the edge of the map, where the lines end.
Output: beamng/verifica/drive_test.json with the counts per road class, the worst places and the
events per road; and a summary on the console.
    python drive_test.py [level folder]
"""
import json, os, sys, time
import numpy as np
from scipy import signal
import patch_release as pr
from road_mesh import TriSurface
from config import LEVEL_DIR
import network
import network_surface
from check_level import road_tops, terrain_top

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica", "drive_test.json")
DS = 0.10                                  # m between the samples of a wheel's path
WHEELBASE, TRACK = 2.6, 1.55
MS, MU, KS, CS, KT = 350.0, 40.0, 30000.0, 3000.0, 200000.0
STATIC = (MS + MU) * 9.81 / KT             # static tyre deflection (m)
STEP_M = 0.05
HARD_G = 0.45
TWIST_DEG = 3.0                            # deg of roll or pitch change within 1 m
SPEED = {"10m Strasse": 60, "8m Strasse": 60, "6m Strasse": 50, "Autostrasse": 80, "Autobahn": 80,
         "4m Strasse": 40, "3m Strasse": 30}
PATH_SPEED = 15
PATCH = [(0.0, 0.0), (0.09, 0.0), (-0.09, 0.0), (0.0, 0.07), (0.0, -0.07)]   # (along, across) m
DEAD_END = WHEELBASE / 2 + 0.3             # m at a dead end where the wheels may be past the end of the road
EDGE_MARGIN = 4.0                          # m before the end of the lines at the edge of the map not counted


def filters(v_kmh):
    """Discrete transfer functions (road height -> body acceleration, -> dynamic tyre deflection) of the
    quarter car at a speed (samples DS m apart)."""
    dt = DS / (v_kmh / 3.6)
    s2 = np.poly1d([1, 0, 0])
    Ds = np.poly1d([MS, CS, KS])
    Du = np.poly1d([MU, CS, KS + KT])
    Cs = np.poly1d([CS, KS])
    delta = Du * Ds - Cs * Cs
    zs_num = KT * Cs                              # body height
    acc_num = zs_num * s2                         # body acceleration
    tyre_num = KT * Ds - delta                    # z_u - z_r
    out = []
    for num in (acc_num, tyre_num):
        b, a, _ = signal.cont2discrete((num.coeffs, delta.coeffs), dt, method="bilinear")
        out.append((np.squeeze(b), a))
    return out


def lane_path(P, w, side):
    """(n, 2) points of the lane at DS m: the line smoothed, moved to the right of the direction of
    travel by `side` (m), and its heading."""
    if len(P) < 2:
        return None, None
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if d[-1] < 4 * DS:
        return None, None
    s = np.arange(0, d[-1], DS)
    Q = np.column_stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])])
    k = max(1, int(round(1.5 / DS)))              # the 2 m polyline's kinks rounded over ~3 m
    if len(Q) > 2 * k + 2:
        ker = np.ones(2 * k + 1) / (2 * k + 1)
        Qs = np.column_stack([np.convolve(np.pad(Q[:, j], k, mode="edge"), ker, "valid") for j in range(2)])
        Q = Qs
    T = np.gradient(Q, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nr = np.column_stack([T[:, 1], -T[:, 0]])      # right of the direction of travel
    return Q + Nr * side, T


class Ground:
    """Height a tyre touches at (x, y): the road face nearest the profile, or the terrain; the higher."""

    def __init__(self, surf, ter):
        self.surf, self.ter = surf, ter

    def __call__(self, x, y, zhint):
        zr = self.surf.height(x, y, "near", zhint)
        zt = terrain_top(self.ter, x, y)
        on = np.isfinite(zr)
        return np.where(on, np.maximum(zr, zt), zt), on


def drive(ground, Q, T, zhint, v, filt, inside, skip0=1.0, skip1=0.0, valid=None):
    """Events of one run: (index along the path, kind, value) per event. The first skip0 m (the start
    transient) and the last skip1 m are left out: at a dead end the wheels ahead of or behind the car
    run past the end of the road, onto the ground beyond it."""
    L = np.column_stack([-T[:, 1], T[:, 0]])       # left
    wheels = [(WHEELBASE / 2, TRACK / 2), (WHEELBASE / 2, -TRACK / 2), (-WHEELBASE / 2, TRACK / 2),
              (-WHEELBASE / 2, -TRACK / 2)]
    ev = []
    Z = []
    for fa, fl in wheels:
        best = None
        onroad = None
        for pa, pl in PATCH:
            x = Q[:, 0] + T[:, 0] * (fa + pa) + L[:, 0] * (fl + pl)
            y = Q[:, 1] + T[:, 1] * (fa + pa) + L[:, 1] * (fl + pl)
            z, on = ground(x, y, zhint)
            best = z if best is None else np.fmax(best, z)
            onroad = on if onroad is None else (onroad | on)
        Z.append(best)
        zr = best - best[0]
        acc = signal.lfilter(filt[0][0], filt[0][1], zr)
        tyre = signal.lfilter(filt[1][0], filt[1][1], zr)
        n0 = int(round(skip0 / DS))
        n1 = len(best) - int(round(skip1 / DS))
        ok = np.ones(len(best), bool) if valid is None else valid
        stp = np.abs(np.diff(best))
        for i in np.flatnonzero(stp > STEP_M):
            if n0 <= i < n1 and ok[i]:
                ev.append((i, "STEP", float(stp[i])))
        for i in np.flatnonzero(tyre > STATIC):
            if n0 <= i < n1 and ok[i]:
                ev.append((i, "LIFT", float(tyre[i])))
        for i in np.flatnonzero(np.abs(acc) > HARD_G * 9.81):
            if n0 <= i < n1 and ok[i]:
                ev.append((i, "HARD", float(abs(acc[i]) / 9.81)))
        miss = inside & ~onroad
        for i in np.flatnonzero(miss):
            if n0 <= i < n1 and ok[i]:
                ev.append((i, "HOLE", 1.0))
    Z = np.array(Z)
    roll = np.degrees(np.arctan(((Z[0] + Z[2]) - (Z[1] + Z[3])) / 2 / TRACK))
    pitch = np.degrees(np.arctan(((Z[0] + Z[1]) - (Z[2] + Z[3])) / 2 / WHEELBASE))
    m = int(round(1.0 / DS))
    n0 = int(round(skip0 / DS))
    n1 = len(Q) - int(round(skip1 / DS))
    for a, name in ((roll, "TWIST"), (pitch, "TWIST")):
        if len(a) > m:
            ch = np.abs(a[m:] - a[:-m])
            for i in np.flatnonzero(ch > TWIST_DEG):
                if n0 <= i + m < n1 and (valid is None or valid[i + m]):
                    ev.append((i + m, name, float(ch[i])))
    return ev


def main(lv=None):
    lv = lv or LEVEL_DIR
    t0 = time.time()
    segs, st, _ = network.load()
    zs = network_surface.load()["z"]
    deg = np.bincount(np.array([q["nodes"][0] for q in segs] + [q["nodes"][-1] for q in segs]))
    # the lines go on CLIP m past the playable area and their surfaces end there: the last metres before
    # the edge of the map are not counted
    import area
    import shapely
    region = area.polygon().buffer(network.CLIP - EDGE_MARGIN)
    shapely.prepare(region)
    tri, is_path, chunk = road_tops(lv)
    surf = TriSurface(tri)
    ter = pr.Terrain(lv)
    ground = Ground(surf, ter)
    print("surfaces loaded: %d top faces, %.0f s" % (len(tri), time.time() - t0), flush=True)
    filt = {}
    places = {}
    per_road = []
    counts = {}
    km = {}
    for k, s in enumerate(segs):
        a, n = s["first"], s["n"]
        if n < 3 or s.get("stairs"):                  # the steps of a flight of stairs are real
            continue
        P = np.column_stack([st["x"][a:a + n], st["y"][a:a + n]])
        w = float(np.median(st["width"][a:a + n]))
        zline = zs[a:a + n]
        path = s["kind"] == "path"
        v = PATH_SPEED if path else SPEED.get(s["class"], 25)
        if v not in filt:
            filt[v] = filters(v)
        # past a dead end the wheels leave the road: DEAD_END m more left out there
        dead0, dead1 = deg[s["nodes"][0]] == 1, deg[s["nodes"][-1]] == 1
        e0, e1 = (1.0 + DEAD_END) if dead0 else 1.0, DEAD_END if dead1 else 0.0
        runs = [(P, zline, 0.25 * w, e0, e1)] if (not path and w >= 5.0) else [(P, zline, 0.0, e0, e1)]
        if not path and w >= 5.0:
            runs.append((P[::-1], zline[::-1], 0.25 * w, (1.0 + DEAD_END) if dead1 else 1.0, DEAD_END if dead0 else 0.0))
        cls = "path" if path else ("main" if s["class"] in ("10m Strasse", "8m Strasse", "6m Strasse") else "minor")
        nev = {}
        for Pr, zr_line, side, sk0, sk1 in runs:
            Q, T = lane_path(Pr, w, side)
            if Q is None:
                continue
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Pr, axis=0), axis=1))]
            sq = np.arange(len(Q)) * DS
            zh = np.interp(sq, d, zr_line)
            inside = np.full(len(Q), (w / 2 - abs(side) - TRACK / 2) > 0.25)
            km[cls] = km.get(cls, 0.0) + len(Q) * DS / 1000
            valid = shapely.contains_xy(region, Q[:, 0], Q[:, 1])
            for i, kind, val in drive(ground, Q, T, zh, v, filt[v], inside, sk0, sk1, valid):
                key = (kind, int(Q[i, 0] // 20), int(Q[i, 1] // 20))
                nev[kind] = nev.get(kind, 0) + 1
                counts.setdefault(cls, {}).setdefault(kind, 0)
                counts[cls][kind] += 1
                if key not in places or val > places[key]["value"]:
                    places[key] = {"what": kind, "x": round(float(Q[i, 0]), 1), "y": round(float(Q[i, 1]), 1),
                                   "z": round(float(zh[i]), 2), "value": round(val, 3), "seg": k, "class": s["class"],
                                   "name": s["name"], "cls": cls}
        if nev:
            per_road.append({"seg": k, "name": s["name"], "class": s["class"], "length": round(s["length"], 1),
                             "events": nev})
        if k % 2000 == 0:
            print("  segment %d/%d, %.0f s" % (k, len(segs), time.time() - t0), flush=True)
    pl = sorted(places.values(), key=lambda r: (r["cls"] == "path", r["what"] != "STEP", -r["value"]))
    res = {"km_driven": {k: round(v, 1) for k, v in km.items()}, "events": counts,
           "places_by_kind": {c: {k: sum(1 for p in pl if p["cls"] == c and p["what"] == k) for k in
                                  ("STEP", "LIFT", "HARD", "HOLE", "TWIST")} for c in ("main", "minor", "path")},
           "per_road": per_road, "places": pl}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: res[k] for k in ("km_driven", "events", "places_by_kind")}, indent=1))
    print("%.0f s" % (time.time() - t0))
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
