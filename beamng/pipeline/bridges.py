"""Bridges of the road and path network (v2.0): decks over the gaps, reviewed one by one.

The DTM is the ground without bridges, so a road that follows it drops into every valley it
crosses. Every swissTLM3D line marked as a bridge (network.BRIDGE) outside the Strada Cantonale
corridor (which keeps its v1.1 surface) gets:
- a deck: the stations of the line at the heights of network_surface.py (no DTM data on a bridge:
  the smooth curve between the two approaches), flat across, as wide as the carriageway;
- a slab SLAB m thick under it, parapets on both sides (road bridges PARAPET m, footbridges RAIL
  m), piers down to the ground every PIER m where the deck is more than PIER_H m above it;
- where the deck is less than LOW m above the ground along the whole span (a culvert, a small
  stream under a road) the sides reach down to the ground instead.
The ground under a bridge is not filled: only where it rises above the underside of the slab is it
lowered to it.
beamng/dati/ponti.json lists every bridge (swissTLM3D id, place, length, height above the ground,
the check flags) and holds the manual corrections, read back at every build:
  "z0" / "z1": deck height at the first / last end (m), "profile": "straight" (a straight deck
  between the ends), "type": "open" | "culvert", "skip": true (no deck: the road follows the
  ground). bridge_report.py draws the profile and a view of every bridge for the review.
"""
import json, os
import numpy as np
from config import WORK
import network

HERE = os.path.dirname(os.path.abspath(__file__))
PONTI = os.path.join(os.path.dirname(HERE), "dati", "ponti.json")
SLAB = 0.6
PARAPET = 1.0
RAIL = 1.0
PARAPET_W = 0.3
PIER = 25.0
PIER_H = 4.0
PIER_W = 1.2
LOW = 1.5
EXTRA_W = 0.3          # m of deck beyond the carriageway on each side


def load_overrides():
    if not os.path.exists(PONTI):
        return {}
    return {b["tlm"]: b for b in json.load(open(PONTI, encoding="utf-8"))["ponti"]}


def half_width(st, s):
    a, n = s["first"], s["n"]
    return 0.5 * float(np.median(st["width"][a:a + n])) + EXTRA_W


def _quad(a, b, c, d, out):
    """Two triangles of the quad a-b-c-d facing `out`."""
    t = np.array([a, b, c, a, c, d], np.float64).reshape(2, 3, 3)
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    flip = (nrm @ np.asarray(out, np.float64)) < 0
    t[flip] = t[flip][:, ::-1]
    return t


def deck_geometry(P, N, z, hw, ground, kind, typ):
    """Triangles (k, 3, 3) of a deck along stations P (n, 2) with normals N and deck heights z:
    (top, sides and underside, parapets, piers), each facing outwards."""
    n = len(P)
    L = P + N * hw
    R = P - N * hw
    up, down = np.array([0, 0, 1.0]), np.array([0, 0, -1.0])
    top = [_quad(np.r_[L[i], z[i]], np.r_[R[i], z[i]], np.r_[R[i + 1], z[i + 1]], np.r_[L[i + 1], z[i + 1]], up)
           for i in range(n - 1)]
    gL, gR = ground(L[:, 0], L[:, 1]), ground(R[:, 0], R[:, 1])
    if typ == "culvert":                               # sides down to the ground
        botL, botR = np.minimum(gL, z - SLAB), np.minimum(gR, z - SLAB)
    else:
        botL, botR = z - SLAB, z - SLAB
    sides = []
    for E, bot, sign in ((L, botL, 1.0), (R, botR, -1.0)):
        for i in range(n - 1):
            out = np.r_[N[i] * sign, 0.0]
            sides.append(_quad(np.r_[E[i], z[i]], np.r_[E[i + 1], z[i + 1]], np.r_[E[i + 1], bot[i + 1]],
                               np.r_[E[i], bot[i]], out))
    for i in range(n - 1):
        sides.append(_quad(np.r_[L[i], botL[i]], np.r_[R[i], botR[i]], np.r_[R[i + 1], botR[i + 1]],
                           np.r_[L[i + 1], botL[i + 1]], down))
    ph = PARAPET if kind == "road" else RAIL
    rise = np.array([0, 0, ph])
    par = []
    T = np.column_stack([N[:, 1], -N[:, 0]])
    for E, sign in ((L, 1.0), (R, -1.0)):
        inner = E - N * sign * PARAPET_W
        for i in range(n - 1):
            o0, o1 = np.r_[E[i], z[i]], np.r_[E[i + 1], z[i + 1]]
            i0, i1 = np.r_[inner[i], z[i]], np.r_[inner[i + 1], z[i + 1]]
            par.append(_quad(o0, o1, o1 + rise, o0 + rise, np.r_[N[i] * sign, 0.0]))
            par.append(_quad(i0, i1, i1 + rise, i0 + rise, np.r_[-N[i] * sign, 0.0]))
            par.append(_quad(o0 + rise, o1 + rise, i1 + rise, i0 + rise, up))
        for i, s_ in ((0, -1.0), (n - 1, 1.0)):
            o, ii = np.r_[E[i], z[i]], np.r_[inner[i], z[i]]
            par.append(_quad(o, ii, ii + rise, o + rise, np.r_[T[i] * s_, 0.0]))
    piers = []
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if typ != "culvert" and s[-1] > PIER:
        k = int(s[-1] // PIER)
        for j in range(1, k + 1):
            sj = s[-1] * j / (k + 1)
            i = int(np.clip(np.searchsorted(s, sj), 1, n - 1))
            f = (sj - s[i - 1]) / max(s[i] - s[i - 1], 1e-9)
            c = P[i - 1] + (P[i] - P[i - 1]) * f
            zc = z[i - 1] + (z[i] - z[i - 1]) * f - SLAB
            g = float(ground([c[0]], [c[1]])[0])
            if zc - g < PIER_H:
                continue
            Nn, Tt = N[i], T[i]
            hw_p, ht = hw * 0.8, PIER_W / 2
            cs = [c + Nn * hw_p + Tt * ht, c - Nn * hw_p + Tt * ht, c - Nn * hw_p - Tt * ht, c + Nn * hw_p - Tt * ht]
            for q in range(4):
                a_, b_ = cs[q], cs[(q + 1) % 4]
                mid = 0.5 * (a_ + b_) - c
                piers.append(_quad(np.r_[a_, g - 0.5], np.r_[b_, g - 0.5], np.r_[b_, zc], np.r_[a_, zc], np.r_[mid, 0.0]))
    cat = lambda L_: np.concatenate(L_) if L_ else np.zeros((0, 3, 3))
    return cat(top), cat(sides), cat(par), cat(piers)


def build(net, ground, on_mesh, on_carve_min, xs, ys, exclude=None):
    """Deck meshes of every bridge (on_mesh(x, y, material, uv tile, soup, kind)), the ground
    under them lowered where it rises above the slab (on_carve_min(rows, cols, z)), the record of
    every bridge in ponti.json. `exclude`: polygon of the cantonale corridor (its bridges stay)."""
    import shapely
    from rasterio import features
    from rasterio.transform import Affine
    segs = net.segs
    st_x, st_y = net.x, net.y
    over = load_overrides()
    records = []
    sq = xs[1] - xs[0]
    for s in segs:
        if not s["bridge"]:
            continue
        a, n = s["first"], s["n"]
        P = np.column_stack([st_x[a:a + n], st_y[a:a + n]])
        if exclude is not None and shapely.LineString(P).within(exclude.buffer(1.0)):
            continue
        N = np.column_stack([net.nx[a:a + n], net.ny[a:a + n]])
        z = net.z[a:a + n].copy()
        o = over.get(s["tlm"], {})
        if o.get("skip"):
            continue
        if o.get("profile") == "straight" or "z0" in o or "z1" in o:
            z0 = float(o.get("z0", z[0])); z1 = float(o.get("z1", z[-1]))
            ss = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
            z = z0 + (z1 - z0) * ss / max(ss[-1], 1e-9)
        hw = half_width({"width": net.w}, s)
        g = ground(P[:, 0], P[:, 1])
        clear = z - SLAB - g
        typ = o.get("type") or ("culvert" if clear.max() < LOW else "open")
        top, sides, par, piers = deck_geometry(P, N, z, hw, ground, s["kind"], typ)
        mat_top = "mp_road_asphalt" if s["surface"] == "hard" else ("mp_road_gravel" if s["kind"] == "road" else "mp_path_dirt")
        cxy = P.mean(0)
        on_mesh(cxy[0], cxy[1], mat_top, 1.25, top, "top")
        on_mesh(cxy[0], cxy[1], "mp_road_wall", 1.6, sides, "side")
        if len(par):
            on_mesh(cxy[0], cxy[1], "mp_bridge_parapet", 1.6, par, "side")
        if len(piers):
            on_mesh(cxy[0], cxy[1], "mp_road_wall", 1.6, piers, "side")
        net.deck_tops.append(top)
        # ground under the deck no higher than the underside of the slab
        foot = shapely.LineString(P).buffer(hw, cap_style="flat")
        x0, y0, x1, y1 = foot.bounds
        c0, c1 = int(np.searchsorted(xs, x0)) - 1, int(np.searchsorted(xs, x1)) + 1
        r0, r1 = int(np.searchsorted(ys, y0)) - 1, int(np.searchsorted(ys, y1)) + 1
        c0, r0 = max(c0, 0), max(r0, 0)
        c1, r1 = min(c1, len(xs)), min(r1, len(ys))
        if c1 > c0 and r1 > r0:
            tr = Affine(sq, 0, xs[c0] - 0.5 * sq, 0, sq, ys[r0] - 0.5 * sq)
            m = features.rasterize([(foot, 1)], out_shape=(r1 - r0, c1 - c0), transform=tr, fill=0, dtype=np.uint8,
                                   all_touched=True).astype(bool)
            rr, cc = np.nonzero(m)
            if len(rr):
                from scipy.spatial import cKDTree
                j = cKDTree(P).query(np.column_stack([xs[c0 + cc], ys[r0 + rr]]))[1]
                on_carve_min(r0 + rr, c0 + cc, z[j] - SLAB - 0.15)
        # checks for the review: deck against the 3D line of swissTLM3D (on a bridge its height is the
        # deck's), steepest grade, grade change where the deck meets the approaches
        ztlm = net.z_tlm[a:a + n] if getattr(net, "z_tlm", None) is not None else np.full(n, np.nan)
        ss = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        grade = np.gradient(z, ss) if n > 1 else np.zeros(n)
        g_in = net.g[a - 1] if a > 0 and net.seg[a - 1] != s["id"] else np.nan
        flags = []
        dtlm = float(np.nanmax(np.abs(z - ztlm))) if np.isfinite(ztlm).any() else np.nan
        if np.isfinite(dtlm) and dtlm > 1.0:
            flags.append("tlm")
        if np.abs(grade).max() > (0.15 if s["kind"] == "road" else 0.3):
            flags.append("ripido")
        if clear.min() < -0.5 and typ == "open":
            flags.append("terreno")
        records.append({"tlm": s["tlm"], "seg": s["id"], "class": s["class"], "name": s["name"],
                        "dz_tlm_m": round(dtlm, 2) if np.isfinite(dtlm) else None,
                        "max_grade": round(float(np.abs(grade).max()), 3), "flags": flags,
                        "x": round(float(cxy[0]), 1), "y": round(float(cxy[1]), 1),
                        "length_m": round(s["length"], 1), "width_m": round(2 * hw, 1),
                        "z_ends": [round(float(z[0]), 2), round(float(z[-1]), 2)],
                        "max_height_m": round(float(clear.max() + SLAB), 1), "auto_type": typ,
                        "override": {k: v for k, v in o.items() if k in ("z0", "z1", "profile", "type", "skip")}})
    return records


def save_records(records, reviewed=None):
    """ponti.json: the bridge list with the manual corrections kept."""
    old = load_overrides()
    out = []
    for r in sorted(records, key=lambda r: -r["length_m"]):
        o = old.get(r["tlm"], {})
        e = dict(r)
        e.pop("override", None)
        for k in ("z0", "z1", "profile", "type", "skip", "note", "checked"):
            if k in o:
                e[k] = o[k]
        out.append(e)
    json.dump({"note": "Bridges of the v2.0 network (bridges.py). Manual corrections: z0/z1 (deck height at "
                       "the ends, m), profile 'straight', type 'open'|'culvert', skip true; note, checked.",
               "ponti": out}, open(PONTI, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
