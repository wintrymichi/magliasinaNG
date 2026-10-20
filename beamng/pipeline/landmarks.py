"""Landmarks of the Malcantone (v3.0.40): the churches, chapels and bell towers drawn as such, not as plastered
houses (issue #11), and the Miglieglia - Monte Lema cable car.

Up to v3.0 a church was a house with a row of arched windows on the ground floor and a bell tower a plastered
block without an opening. Now, in buildings_mesh.build, for the buildings of the survey whose style is "church" or
"tower" (facades.style_of: swissBUILDINGS3D object kind, register class 1272) or that dati/landmarks.json names:
- the walls: plastered in the light tones of the churches of the area (CHURCH_TONES; the tone measured in the photos
  where there is one), or bare stone where dati/landmarks.json says so (the Romanesque churches and towers); the
  roof covering of the catalogue (piode, coppi) where it gives one;
- bell towers: the open bell chamber under the eaves on every face wide enough (one, two or three arches after the
  width of the face, the bell in the dark behind), a clock face under it on the faces turned to the village (lit at
  night), string courses of granite under the bell chamber and a cornice under the eaves, quoins (long and short
  granite blocks in turn) up every corner, arrow slits on the old stone towers, a small arched door at the foot;
- churches: on the gable facing the square or the street (the west where no street is near) the portal, round-arched
  with a painted lunette or square with a pediment, and an oculus over it; tall round-arched windows along the nave;
  the cornice under the eaves on every wall and across the gables, quoins at the corners, a granite plinth;
- chapels: the arched door on the gable, the cornice, quoins on the larger ones.
The openings, clock faces and quoins are quads OFFSET m in front of the walls with the landmarks atlas
(landmark_textures.py, material bld_landmark, clock faces bld_landmark_lit), the cornices, string courses and plinths
boxes of squared granite (bld_ashlar).
"""
import json, math, os
import numpy as np
import shapely

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
CATALOGUE = os.path.join(DATI, "landmarks.json")
USES = ("church", "tower", "chapel")
OFFSET = 0.03                 # m, the atlas quads in front of the wall
CHAPEL_AREA = 45.0            # m2: a church of the survey this small is a chapel
# plaster tones of the churches of the Malcantone (sRGB): white, cream, light ochre, warm grey, a pale salmon
CHURCH_TONES = [(0.93, 0.92, 0.88), (0.92, 0.88, 0.77), (0.90, 0.82, 0.64), (0.85, 0.83, 0.78), (0.91, 0.82, 0.74)]
ASHLAR_TILE = 2.0             # m, tile of the ashlar texture
CORNICE = (0.30, 0.16)        # m: height, projection of the cornice under the eaves
COURSE = (0.20, 0.09)         # m: the string courses
PLINTH = (0.60, 0.05)         # m: the granite plinth of the churches


# ------------------------------------------------------------------ catalogue and styles
_cat = None


def catalogue():
    """dati/landmarks.json: the landmarks known by name (from the reference photos): a point and a radius, and what
    differs from the defaults (walls, tone, roof, clock faces, bell chamber, portal)."""
    global _cat
    if _cat is None:
        _cat = json.load(open(CATALOGUE))["landmarks"] if os.path.exists(CATALOGUE) else []
    return _cat


def spec_of(fp):
    """The catalogue entry of a footprint (its point inside the footprint or within its radius), or {}."""
    best, bd = {}, 1e9
    for e in catalogue():
        d = shapely.distance(fp, shapely.Point(e["x"], e["y"]))
        if d <= e.get("r", 6.0) and d < bd:
            best, bd = e, d
    return best


SACRED = ("Sakrales Gebaeude", "Kapelle", "Sakraler Turm")
TOWER_NEAR = 25.0             # m: a tower of the survey ("Turm") this close to a church is its bell tower
_sacred = None


def prepare(blds, fps, gwr):
    """The footprints of the sacred buildings of the survey (object kind, register class 1272): a plain "Turm" near
    one of them is a bell tower, any other (a water tower, the control tower of the airfield) is not."""
    global _sacred
    keep = [fp for b, fp in zip(blds, fps) if b["kind"] in SACRED or gwr.get(b["uuid"], {}).get("gklas") == 1272]
    _sacred = shapely.STRtree(keep) if keep else None
    # the survey often keeps the roof of a church as an object of its own, without walls: the tower and the spire
    # are found on the roofs over the walls, whoever holds them
    global _lids
    lids = [(shapely.MultiPoint(b["roofs"].reshape(-1, 3)[:, :2]).convex_hull, b["roofs"]) for b in blds
            if not len(b["walls"]) and len(b["roofs"])]
    _lids = (shapely.STRtree([fp for fp, _ in lids]), [r for _, r in lids]) if lids else None


_lids = None


def roofs_of(fp, roofs):
    """The roof triangles over a building: its own, else those of the wall-less roof objects over its footprint."""
    if len(roofs) or _lids is None or fp is None:
        return roofs
    tree, rs = _lids
    got = [rs[j] for j in tree.query(fp) if tree.geometries[j].intersection(fp).area > 0.5 * min(fp.area, tree.geometries[j].area)]
    return np.concatenate(got) if got else roofs


def near_sacred(fp, b):
    if _sacred is None:
        return False
    for j in _sacred.query(fp.buffer(TOWER_NEAR)):
        g = _sacred.geometries[j]
        if not g.equals(fp):
            return True
    return False


def apply(style, b, fp, measured=None):
    """The style of a landmark: use (church, chapel, tower), walls, tone and roof after the catalogue; the style of
    any other building is returned as it is."""
    spec = spec_of(fp)
    use = spec.get("use") or style["use"]
    if use not in USES:
        return style
    if use == "tower" and b["kind"] not in SACRED and not spec and not near_sacred(fp, b):
        return style                          # a tower that is no bell tower
    if use == "church" and fp.area < CHAPEL_AREA and not spec.get("use"):
        use = "chapel"
    st = dict(style)
    st["use"] = use
    st["landmark"] = spec
    rng = np.random.default_rng(style["seed"])
    if measured is None:
        st["tone"] = np.clip(np.array(CHURCH_TONES[int(rng.integers(len(CHURCH_TONES)))]) * (1 + rng.normal(0, 0.015, 3)),
                             0, 1)
    if spec.get("tone"):
        st["tone"] = np.array(spec["tone"], float)
    st["stone"] = spec.get("walls") == "stone"
    st["plinth"] = False                      # the granite plinth of the landmarks instead
    if spec.get("roof"):
        st["roof"] = spec["roof"]
    return st


# ------------------------------------------------------------------ what is drawn
class Emitter:
    """The quads of the landmarks atlas and the boxes of squared granite of one tile."""

    def __init__(self, index):
        self.index = index
        self.V, self.UV = [], []              # atlas quads
        self.LV, self.LUV = [], []            # the clock faces (lit at night)
        self.AV, self.AUV, self.AC = [], [], []   # ashlar: triangles, uvs, colour of each quad
        self.XV = []                          # wrought iron: the crosses on the spires and gables

    def empty(self):
        return not (self.V or self.LV or self.AV or self.XV)

    def cross(self, p, facing, h=1.6):
        """An iron cross standing on the point p, its arms across `facing` (a horizontal unit vector)."""
        f = np.array([facing[0], facing[1], 0.0])
        f /= max(np.linalg.norm(f), 1e-9)
        s = np.array([-f[1], f[0], 0.0])
        t = 0.05
        bars = [(p, p + np.array([0, 0, h])), (p + np.array([0, 0, 0.62 * h]) - s * 0.32 * h,
                                               p + np.array([0, 0, 0.62 * h]) + s * 0.32 * h)]
        for a, b in bars:
            d = (b - a) / np.linalg.norm(b - a)
            u = np.cross(d, f)
            u /= max(np.linalg.norm(u), 1e-9)
            c = [u * t + f * t, -u * t + f * t, -u * t - f * t, u * t - f * t]
            for k in range(4):
                p0, p1 = c[k], c[(k + 1) % 4]
                self.XV.append(np.array([[a + p0, b + p0, b + p1], [a + p0, b + p1, a + p1]]))

    def clear(self):
        self.__init__(self.index)

    def module(self, name, o, a, n, uc, zb, scale=1.0, lit=False, flip=False, v=(0.0, 1.0)):
        """The atlas module `name` on the facade plane (o, a along it, n out), centred at uc, its foot at zb;
        flip mirrors it; v: the part of its height drawn (0..1 from the foot)."""
        m = self.index[name]
        w, h = m["w"] * scale, m["h"] * scale
        u0, v0, u1, v1 = m["uv"]
        if flip:
            u0, u1 = u1, u0
        tv0, tv1 = v0 + (v1 - v0) * v[0], v0 + (v1 - v0) * v[1]
        P = lambda u, z: o + u * a + np.array([0.0, 0.0, z]) + n * OFFSET
        z0, z1 = zb, zb + h * (v[1] - v[0])
        c = [P(uc - w / 2, z0), P(uc + w / 2, z0), P(uc + w / 2, z1), P(uc - w / 2, z1)]
        t = [(u0, tv0), (u1, tv0), (u1, tv1), (u0, tv1)]
        V = np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]])
        T = np.array([[t[0], t[1], t[2]], [t[0], t[2], t[3]]])
        (self.LV if lit else self.V).append(V)
        (self.LUV if lit else self.UV).append(T)

    def box(self, o, a, n, ua, ub, z0, z1, out, color, back=0.02):
        """A band of squared granite along the facade from ua to ub, z0 to z1, projecting `out` m: front, top,
        bottom and both ends."""
        P = lambda u, d, z: o + u * a + n * d + np.array([0.0, 0.0, z])
        f = [(P(ua, out, z0), P(ub, out, z0), P(ub, out, z1), P(ua, out, z1)),
             (P(ua, -back, z1), P(ua, out, z1), P(ub, out, z1), P(ub, -back, z1)),
             (P(ua, -back, z0), P(ub, -back, z0), P(ub, out, z0), P(ua, out, z0)),
             (P(ua, -back, z0), P(ua, out, z0), P(ua, out, z1), P(ua, -back, z1)),
             (P(ub, out, z0), P(ub, -back, z0), P(ub, -back, z1), P(ub, out, z1))]
        for q in f:
            q = np.array(q)
            d = q[1] - q[0]
            e = q[3] - q[0]
            # uvs in metres over the tile: along the band and up (the top and bottom: along and across)
            s = [0.0, np.linalg.norm(d), np.linalg.norm(d), 0.0]
            tt = [0.0, 0.0, np.linalg.norm(e), np.linalg.norm(e)]
            base = q[0] @ a
            uv = np.array([[base + s[k], q[k][2] if abs(e[2]) > 1e-6 else tt[k]] for k in range(4)]) / ASHLAR_TILE
            self.AV.append(np.array([[q[0], q[1], q[2]], [q[0], q[2], q[3]]]))
            self.AUV.append(np.array([[uv[0], uv[1], uv[2]], [uv[0], uv[2], uv[3]]]))
            self.AC.append(color)


def faces(b, walls, ctx):
    """The planar facades of a building: dicts with the triangles, outward normal n, axis a, origin o, the facade
    polygon F in (u, z), the samples us along it, the ground g and the top of the wall over them."""
    import texturing
    import facades
    out = []
    for idx, n, d0 in texturing.facade_groups(walls):
        tris = walls[idx]
        n = np.asarray(n, float)
        a = np.array([-n[1], n[0], 0.0])
        F = facades.facade_polygon(tris, a)
        if F is None:
            continue
        # a slot under half a metre in the wall (a recess, a downpipe of the survey) does not split the facade
        F = F.buffer(0.3, join_style="mitre").buffer(-0.3, join_style="mitre")
        if F.is_empty:
            continue
        u0, z0, u1, z1 = F.bounds
        if u1 - u0 < 0.8:
            continue
        o = np.array([n[0] * d0, n[1] * d0, 0.0])
        us = np.linspace(u0, u1, max(3, int(np.ceil((u1 - u0) / 0.5)) + 1))
        g = ctx.ground(o[0] + us * a[0] + n[0] * 0.4, o[1] + us * a[1] + n[1] * 0.4)
        top = facades.top_profile(F, us)
        if not np.isfinite(top).any():
            continue
        g = np.where(np.isfinite(g), g, z0)
        out.append({"tris": tris, "n": n, "a": a, "o": o, "F": F, "us": us, "g": np.asarray(g, float), "top": top,
                    "u0": u0, "u1": u1, "W": u1 - u0, "zmin": z0, "zmax": z1})
    return out


def round_faces(walls, ctx, k=4):
    """The faces of a round tower (the survey draws it as many narrow facets, none wide enough for a module):
    k planes touching the drum, as faces() gives them; None when the walls are not a drum."""
    P = walls.reshape(-1, 3)
    hull = shapely.MultiPoint(P[:, :2]).convex_hull
    if hull.area < 3.0:
        return None
    c = np.array(hull.centroid.coords[0])
    d = np.hypot(P[:, 0] - c[0], P[:, 1] - c[1])
    r = float(np.median(d))
    if r < 1.2 or np.std(d) > 0.08 * r or abs(hull.area - math.pi * r * r) > 0.12 * hull.area:
        return None
    W = 1.15 * r
    z0, z1 = float(P[:, 2].min()), float(P[:, 2].max())
    out = []
    for j in range(k):
        t = 2 * math.pi * j / k + math.pi / 4
        n = np.array([math.cos(t), math.sin(t), 0.0])
        a = np.array([-n[1], n[0], 0.0])
        o = np.array([c[0], c[1], 0.0]) + r * n
        # the top of the drum on this side
        side = (P[:, :2] - c) @ n[:2] > 0.7 * r
        top = float(P[side, 2].max()) if side.any() else z1
        F = shapely.box(-W / 2, z0, W / 2, top)
        us = np.linspace(-W / 2, W / 2, 5)
        g = ctx.ground(o[0] + us * a[0] + n[0] * 0.4, o[1] + us * a[1] + n[1] * 0.4)
        g = np.where(np.isfinite(g), g, z0)
        tris = walls[((walls.mean(1)[:, :2] - c) @ n[:2]) > 0.7 * r]
        out.append({"tris": tris if len(tris) else walls, "n": n, "a": a, "o": o, "F": F, "us": us,
                    "g": np.asarray(g, float), "top": np.full(len(us), top), "u0": -W / 2, "u1": W / 2, "W": W,
                    "zmin": z0, "zmax": top, "round": True})
    return out


def fits(f, uc, w, zb, h, pad=0.08):
    """Whether a module (centre uc, width w, foot zb, height h) lies on the wall of the facade."""
    inner = f["F"].buffer(-pad)
    return not inner.is_empty and inner.contains(shapely.box(uc - w / 2, zb, uc + w / 2, zb + h))


def eave_of(f):
    """The height of the eaves of a facade: the lower tenth of its top away from the corners (a gable: its foot)."""
    us, top = f["us"], f["top"]
    mid = (us > us[0] + 0.3) & (us < us[-1] - 0.3) & np.isfinite(top)
    vals = top[mid] if mid.any() else top[np.isfinite(top)]
    return float(np.percentile(vals, 5)) if len(vals) else np.nan


def is_gable(f):
    """A gable: the top of the wall rises to a peak away from both ends (more than 1 m over its ends)."""
    t = f["top"]
    ok = np.isfinite(t)
    if ok.sum() < 3:
        return False
    tt = t[ok]
    k = int(np.argmax(tt))
    return 0 < k < len(tt) - 1 and tt[k] - max(tt[0], tt[-1]) > 1.0


def front_of(fs, ctx, cand):
    """The facade among cand that faces the street (or the square) in front of the building, else the one facing
    west (most churches of the area turn their front to the west or to the village)."""
    if not cand:
        return -1
    c = np.concatenate([f["tris"].reshape(-1, 3) for f in fs])[:, :2].mean(0)
    sdir, sdist, _ = ctx.street_dir(c[0], c[1]) if ctx is not None else (None, 1e9, False)
    best, bs = -1, -1e9
    for i in cand:
        f = fs[i]
        s = 0.25 * float(-f["n"][0]) + 0.08 * f["W"] ** 0.5
        if sdir is not None and sdist < 60:
            s += float(f["n"][:2] @ sdir)
        if s > bs:
            best, bs = i, s
    return best


def quoins(lem, f, zlo, zhi, start, ends=True):
    """Quoins up the corners of a facade from zlo to zhi: the strip at u0 (going in along a) and the mirrored one
    at u1; `start` (0 or 1) shifts the strip by one block so that a corner has long blocks over short ones."""
    from landmark_textures import QUOIN_H
    m = lem.index["quoins"]
    H = m["h"]
    for at_end in ((False, True) if ends else (False,)):
        off = QUOIN_H * ((start + int(at_end)) % 2)
        z = zlo - off
        while z < zhi - 0.05:
            v0 = max(0.0, (zlo - z) / H)
            v1 = min(1.0, (zhi - z) / H)
            if v1 > v0 + 1e-3:
                w = m["w"]
                uc = f["u1"] - w / 2 if at_end else f["u0"] + w / 2
                lem.module("quoins", f["o"], f["a"], f["n"], uc, z + v0 * H, flip=at_end, v=(v0, v1))
            z += H


def band_all(lem, fs, z, height, out, color):
    """A string course (or cornice) of granite at z round every facade that reaches that height."""
    for f in fs:
        if f["zmax"] < z + height * 0.5 or f["zmin"] > z:
            continue
        sec = f["F"].intersection(shapely.box(f["u0"] - 1, z, f["u1"] + 1, z + height))
        if sec.is_empty:
            continue
        ua, _, ub, _ = sec.bounds
        if ub - ua < 0.3:
            continue
        lem.box(f["o"], f["a"], f["n"], ua - out, ub + out, z, z + height, out, color)


TOWER_PLAN = (5.0, 110.0)     # m2: plan of a bell tower inside a church building of the survey
TOWER_OVER = 4.0              # m its roof rises at least over the rest of the roofs


def tower_part(walls, roofs):
    """The bell tower inside a church of the survey (most churches of the area are one building with their tower):
    the separate piece of roof that is small (TOWER_PLAN) and rises TOWER_OVER m over every other roof. Returns
    (mask of the wall triangles of the tower, its roof triangles) or None."""
    if roofs is None or len(roofs) < 2:
        return None
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    V = np.round(roofs.reshape(-1, 3), 2)
    _, ids = np.unique(V, axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    k = len(ids)
    rows = np.repeat(np.arange(k), 3)
    M = coo_matrix((np.ones(3 * k), (rows, ids.ravel() + k)), shape=(k + ids.max() + 1, k + ids.max() + 1))
    _, lab = connected_components(M, directed=False)
    lab = lab[:k]
    best = None
    comps = np.unique(lab)
    plans = {c: shapely.MultiPoint(roofs[lab == c].reshape(-1, 3)[:, :2]).convex_hull for c in comps}
    # over the roof of the nave (the largest piece), not over every piece: a terrace or a landing of the tower
    # is a piece of roof of its own
    nave = max(comps, key=lambda c: plans[c].area)
    top = roofs[lab == nave][..., 2].max()
    for c in comps:
        R = roofs[lab == c]
        P = R.reshape(-1, 3)
        plan = plans[c]
        if c == nave or not TOWER_PLAN[0] <= plan.area <= TOWER_PLAN[1]:
            continue
        if P[:, 2].max() < top + TOWER_OVER or P[:, 2].min() < top - 1.0:
            continue
        if best is None or P[:, 2].max() > best[2]:
            best = (plan, R, P[:, 2].max())
    if best is None:
        return None
    plan, R, _ = best
    zone = plan.buffer(0.35)
    shapely.prepare(zone)
    W = walls.reshape(-1, 3)
    inside = shapely.contains_xy(zone, W[:, 0], W[:, 1]).reshape(-1, 3).all(1)
    if inside.sum() < 4:
        return None
    return inside, R


def layout(b, walls, style, ctx, em, lem, roofs=None):
    """The landmark details of one building (walls: its wall triangles, outward); the number of modules placed."""
    use = style["use"]
    if use == "church" and roofs is not None:
        tp = tower_part(walls, roofs)
        if tp is not None:                    # the church and its bell tower, each with its own details
            mask, troofs = tp
            n = layout(b, walls[mask], dict(style, use="tower"), ctx, em, lem, troofs)
            return n + layout(b, walls[~mask], style, ctx, em, lem, None)
    fs = (use == "tower" and round_faces(walls, ctx)) or faces(b, walls, ctx)
    if not fs:
        return 0
    spec = style.get("landmark") or {}
    rng = np.random.default_rng(style["seed"])
    stone_col = np.array(spec.get("trim", (0.66, 0.65, 0.62)), float)
    g_all = np.concatenate([f["g"] for f in fs])
    g_lo = float(np.nanmin(g_all))
    eaves = np.array([eave_of(f) for f in fs])
    good = np.isfinite(eaves)
    if not good.any():
        return 0
    Ws = np.array([f["W"] for f in fs])
    # a tower: the eaves of its shaft (its widest faces), not of a lantern or a drum on top of it
    wide = Ws >= (max(1.6, 0.6 * Ws.max()) if use == "tower" else 1.6)
    z_e = float(np.median(eaves[good & wide])) if (good & wide).any() else float(np.median(eaves[good]))
    if use == "tower":
        n = tower(fs, z_e, g_lo, style, spec, ctx, lem, rng, stone_col)
        # the cross on the spire: on the highest point of the roof over the tower's walls
        if roofs is not None and len(roofs) and spec.get("cross", True):
            R = roofs.reshape(-1, 3)
            xy = walls.reshape(-1, 3)[:, :2]
            inside = (R[:, 0] >= xy[:, 0].min() - 0.5) & (R[:, 0] <= xy[:, 0].max() + 0.5) & \
                     (R[:, 1] >= xy[:, 1].min() - 0.5) & (R[:, 1] <= xy[:, 1].max() + 0.5)
            if inside.any():
                top = R[inside][np.argmax(R[inside][:, 2])]
                if top[2] > z_e + 1.0:
                    lem.cross(top - np.array([0, 0, 0.05]), fs[0]["n"][:2], h=float(np.clip(0.07 * (z_e - g_lo), 1.2, 2.4)))
        return n
    return church(fs, z_e, g_lo, style, spec, ctx, lem, rng, stone_col, chapel=use == "chapel")


def tower(fs, z_e, g_lo, style, spec, ctx, lem, rng, trim):
    count = 0
    H = z_e - g_lo
    if H < 5.0:
        return 0
    faces_ok = [i for i, f in enumerate(fs) if f["W"] >= 0.9 and f["zmax"] > z_e - 0.5]
    front = front_of(fs, ctx, faces_ok)
    # the cornice under the eaves, the bell chamber under it
    cz = z_e - CORNICE[0]
    drum = bool(fs[0].get("round"))
    if not drum:
        band_all(lem, fs, cz, CORNICE[0], CORNICE[1], trim)
    nb = spec.get("bells")
    zb_min = z_e
    for i in faces_ok:
        f = fs[i]
        W = f["W"]
        k = nb or (1 if W < 2.6 else (2 if W < 4.0 else 3))
        name = f"bells_{k}"
        m = lem.index[name]
        s = min(1.15, (W - 0.7) / m["w"], max(0.6, 0.20 * H / m["h"]))
        if s < 0.45:
            continue
        uc = 0.5 * (f["u0"] + f["u1"])
        zb = cz - 0.12 - m["h"] * s
        if zb < g_lo + 0.45 * H:
            continue
        if not fits(f, uc, m["w"] * s, zb, m["h"] * s):
            continue
        lem.module(name, f["o"], f["a"], f["n"], uc, zb, s)
        zb_min = min(zb_min, zb)
        count += 1
    if count and not drum:
        band_all(lem, fs, zb_min - COURSE[0] - 0.05, COURSE[0], COURSE[1], trim)
    # the clock faces under the bell chamber, on the front and the faces turned the most like it
    n_clock = spec.get("clock", 2 if H >= 11 else 0)
    if n_clock and front >= 0 and count:
        order = sorted(faces_ok, key=lambda i: -float(fs[i]["n"][:2] @ fs[front]["n"][:2]))
        placed = 0
        for i in order:
            if placed >= n_clock:
                break
            f = fs[i]
            d = float(np.clip(0.45 * f["W"], 0.9, 2.4))
            s = d / lem.index["clock"]["w"]
            uc = 0.5 * (f["u0"] + f["u1"])
            zb = zb_min - COURSE[0] - 0.35 - d
            if zb < g_lo + 0.4 * H or not fits(f, uc, d, zb, d):
                continue
            lem.module("clock", f["o"], f["a"], f["n"], uc, zb, s, lit=True)
            placed += 1
            count += 1
    # quoins up the corners, slits on the stone towers, the door at the foot of the front
    # (none on a round or polygonal tower: more than six faces)
    if spec.get("quoins", True) and not drum and len([f for f in fs if f["W"] >= 0.8]) <= 6:
        for i, f in enumerate(fs):
            if f["W"] >= 1.6:
                quoins(lem, f, float(np.nanmin(f["g"])) - 0.3, (zb_min - COURSE[0] - 0.05) if count else z_e - CORNICE[0],
                       i % 2)
    if front >= 0 and not drum:                # (a drum stands in the church: its foot is in the nave)
        f = fs[front]
        uc = 0.5 * (f["u0"] + f["u1"])
        gc = float(np.interp(uc, f["us"], f["g"]))
        if style.get("stone") or spec.get("slits"):
            m = lem.index["slit"]
            for frac in (0.35, 0.58):
                zb = g_lo + frac * H
                if fits(f, uc, m["w"], zb, m["h"]):
                    lem.module("slit", f["o"], f["a"], f["n"], uc, zb)
                    count += 1
        m = lem.index["chapel_door"]
        s = min(1.0, (f["W"] - 0.9) / m["w"])
        if s >= 0.75 and gc - g_lo < 1.0 and fits(f, uc, m["w"] * s, gc - 0.05, m["h"] * s, pad=-0.1):
            lem.module("chapel_door", f["o"], f["a"], f["n"], uc, gc - 0.05, s)
            count += 1
    return count


def church(fs, z_e, g_lo, style, spec, ctx, lem, rng, trim, chapel=False):
    count = 0
    gables = [i for i, f in enumerate(fs) if is_gable(f) and f["W"] >= 2.0]
    front = front_of(fs, ctx, gables or [i for i, f in enumerate(fs) if f["W"] >= 2.0])
    # the cornice under the eaves (across the gables too) and the plinth
    band_all(lem, fs, z_e - CORNICE[0], CORNICE[0], CORNICE[1] * (0.7 if chapel else 1.0), trim)
    if not chapel:
        for f in fs:
            if f["W"] < 1.0:
                continue
            gm = float(np.nanmin(f["g"]))
            lem.box(f["o"], f["a"], f["n"], f["u0"], f["u1"], gm - 0.4, float(np.nanmax(f["g"])) + PLINTH[0] - 0.2,
                    PLINTH[1], trim)
    if front >= 0:
        f = fs[front]
        uc = 0.5 * (f["u0"] + f["u1"])
        gc = float(np.interp(uc, f["us"], f["g"]))
        apex = float(np.nanmax(f["top"]))
        if chapel:
            name = "chapel_door"
            m = lem.index[name]
            s = float(np.clip((f["W"] - 0.8) / m["w"], 0.55, 1.0))
        else:
            name = spec.get("portal") or ("portal_arch" if rng.random() < 0.6 else "portal_square")
            m = lem.index[name]
            s = float(np.clip(0.32 * f["W"] / m["w"], 0.7, 1.15))
        top = gc
        if fits(f, uc, m["w"] * s, gc - 0.05, m["h"] * s, pad=-0.1):
            lem.module(name, f["o"], f["a"], f["n"], uc, gc - 0.05, s)
            top = gc - 0.05 + m["h"] * s
            count += 1
        k = int(np.nanargmax(f["top"]))
        if apex > z_e + 1.0 and spec.get("cross", True):
            p = f["o"] + f["us"][k] * f["a"] + np.array([0.0, 0.0, apex - 0.05]) - f["n"] * 0.3
            lem.cross(p, f["n"][:2], h=1.0 if chapel else 1.5)
        if not chapel and f["W"] >= 5.0:
            d = float(np.clip(0.16 * f["W"], 0.8, 1.8))
            zc = min(max(top + 0.7 + d / 2, z_e - 0.2), apex - 1.0 - d / 2)
            if zc - d / 2 > top + 0.3 and fits(f, uc, d, zc - d / 2, d):
                lem.module("oculus", f["o"], f["a"], f["n"], uc, zc - d / 2, d / lem.index["oculus"]["w"])
                count += 1
    # the windows of the nave: tall and round-arched, on the long walls
    if not chapel:
        m = lem.index["tall_window"]
        for i, f in enumerate(fs):
            if i == front or i in gables or f["W"] < 4.0:
                continue
            gm = float(np.nanmax(f["g"]))
            room = z_e - CORNICE[0] - 0.5 - (gm + 2.0)
            s = min(1.0, room / m["h"])
            if s < 0.45:
                continue
            nwin = int(max(1, np.floor((f["W"] - 2.0) / 4.5 + 0.3)))
            span = f["W"] - 2.4
            for k in range(nwin):
                uc = f["u0"] + 1.2 + (k + 0.5) * span / nwin
                zb = z_e - CORNICE[0] - 0.5 - m["h"] * s
                if fits(f, uc, m["w"] * s, zb, m["h"] * s):
                    lem.module("tall_window", f["o"], f["a"], f["n"], uc, zb, s)
                    count += 1
    if not chapel or sum(f["W"] for f in fs) > 22:
        for i, f in enumerate(fs):
            if f["W"] >= 2.5:
                quoins(lem, f, float(np.nanmin(f["g"])) - 0.3, z_e - CORNICE[0], i % 2)
    return count


# ------------------------------------------------------------------ the cable car
# The Miglieglia - Monte Lema cable car, from the line of swissTLM3D (TLM_UEBRIGE_BAHN, download_tlm.py): its
# vertices are the stations and the pylons. Drawn in MissionGroup/landmarks/cableway, collision on the pylons only:
# - the ropes: CABLE_GAUGE m apart, sagging between the supports (a parabola, CABLE_SAG of the span), from the
#   station hall CABLE_STATION_H m over the ground at either end over the saddles of the pylons;
# - the pylons: steel lattice towers (four legs tapering to the head, cross bracing, a cross beam with the
#   saddles), as high as the ropes over them;
# - the cabins hanging on the ropes, CABIN_EVERY m apart, the colours of the line.
CABLE_KINDS = ("Luftseilbahn", "Gondelbahn", "Kabinenbahn", "Pendelbahn", "Umlaufbahn")
CABLE_GAUGE = 5.4
CABLE_SAG = 0.025
CABLE_STATION_H = 5.5
CABLE_R = 0.03
CABIN_EVERY = 72.0
CABIN = (1.7, 1.5, 1.9)            # m: length (along the line), width, height of a cabin (four seats)
CABIN_COLOR = (0.08, 0.30, 0.62)   # linear: the blue cabins of the Monte Lema line, a green band under the windows
CABIN_BAND = (0.20, 0.55, 0.10)
STEEL = (0.42, 0.44, 0.45)


def cable_lines(near=None, dist=400.0):
    """[(props, (n, 3) local points)] of the cable cars of swissTLM3D (within dist m of `near` when given)."""
    from config import DATA, lv95_to_local
    f = os.path.join(DATA, "tlm", "TLM_UEBRIGE_BAHN.json")
    if not os.path.exists(f):
        return []
    out = []
    for ft in json.load(open(f))["features"]:
        if not any(k in str(ft["props"].get("OBJEKTART", "")) for k in CABLE_KINDS):
            continue
        for p in ft["parts"]:
            P = np.array(p, float)
            x, y = lv95_to_local(P[:, 0], P[:, 1])
            Q = np.column_stack([x, y, P[:, 2]])
            if near is not None and np.hypot(Q[:, 0] - near[0], Q[:, 1] - near[1]).min() > dist:
                continue
            out.append((ft["props"], Q))
    return out


def _tube(a, b, r):
    """A square tube of half-width r from a to b (8 triangles, open at the ends)."""
    d = b - a
    ln = np.linalg.norm(d)
    if ln < 1e-6:
        return np.zeros((0, 3, 3))
    d = d / ln
    u = np.cross(d, [0.0, 0.0, 1.0])
    if np.linalg.norm(u) < 1e-6:
        u = np.array([1.0, 0.0, 0.0])
    u = u / np.linalg.norm(u)
    v = np.cross(u, d)
    c = [u * r + v * r, -u * r + v * r, -u * r - v * r, u * r - v * r]
    tris = []
    for k in range(4):
        p0, p1 = c[k], c[(k + 1) % 4]
        tris += [[a + p0, b + p0, b + p1], [a + p0, b + p1, a + p1]]
    return np.array(tris)


def _box(c, ax, ay, hz, sx, sy, z0):
    """A box centred at c (x, y), axes ax, ay (unit, horizontal), half sizes sx, sy, from z0 to z0 + hz."""
    P = lambda i, j, z: np.array([c[0] + i * sx * ax[0] + j * sy * ay[0], c[1] + i * sx * ax[1] + j * sy * ay[1], z])
    q = [P(-1, -1, z0), P(1, -1, z0), P(1, 1, z0), P(-1, 1, z0)]
    t = [P(-1, -1, z0 + hz), P(1, -1, z0 + hz), P(1, 1, z0 + hz), P(-1, 1, z0 + hz)]
    tris = [[t[0], t[1], t[2]], [t[0], t[2], t[3]], [q[0], q[2], q[1]], [q[0], q[3], q[2]]]
    for k in range(4):
        a, b = q[k], q[(k + 1) % 4]
        A, B = t[k], t[(k + 1) % 4]
        tris += [[a, b, B], [a, B, A]]
    return np.array(tris)


def rope(p0, p1, sag, n=24):
    """Points of a rope from p0 to p1 sagging `sag` m at its middle."""
    s = np.linspace(0, 1, n)
    P = p0[None] + (p1 - p0)[None] * s[:, None]
    P[:, 2] -= 4 * sag * s * (1 - s)
    return P


def pylon(base, top, axis, legs=1.4, head=0.5):
    """A lattice pylon from the ground point `base` up to the saddle height top (z), its cross beam across axis."""
    import itertools
    across = np.array([-axis[1], axis[0], 0.0])
    h = top - base[2]
    tris = []
    corners = lambda w, z: [base[:2] + w * (i * axis[:2] + j * across[:2]) for i, j in itertools.product((-1, 1), (-1, 1))]
    lo = corners(legs, 0)
    hi = corners(head, 0)
    for a, b in zip(lo, hi):
        tris.append(_tube(np.r_[a, base[2] - 0.5], np.r_[b, top - 0.6], 0.09))
    # bracing every 3 m: the four sides, crossing
    nz = max(2, int(h / 3.0))
    zs = np.linspace(base[2], top - 0.6, nz + 1)
    w = lambda z: legs + (head - legs) * (z - base[2]) / max(top - 0.6 - base[2], 1e-3)
    order = [0, 1, 3, 2]
    for z0, z1 in zip(zs[:-1], zs[1:]):
        c0, c1 = corners(w(z0), 0), corners(w(z1), 0)
        for k in range(4):
            i, j = order[k], order[(k + 1) % 4]
            tris.append(_tube(np.r_[c0[i], z0], np.r_[c1[j], z1], 0.035))
            tris.append(_tube(np.r_[c0[j], z0], np.r_[c1[i], z1], 0.035))
            tris.append(_tube(np.r_[c1[i], z1], np.r_[c1[j], z1], 0.035))
    # the cross beam carrying the saddles of both tracks
    half = CABLE_GAUGE / 2 + 0.6
    tris.append(_box(base[:2], across[:2], axis[:2], 0.6, half, 0.35, top - 0.6))
    for sgn in (-1, 1):
        c = base[:2] + sgn * CABLE_GAUGE / 2 * across[:2]
        tris.append(_box(c, axis[:2], across[:2], 0.25, 1.6, 0.18, top))
    return np.concatenate(tris)


def cabin(p, axis):
    """A cabin hanging from the rope point p: the carriage on the rope, the hanger, the body with its windows
    (body: CABIN_COLOR, glazing: dark)."""
    across = np.array([-axis[1], axis[0], 0.0])
    L, W, H = CABIN
    body_top = p[2] - 2.4
    body = _box(p[:2], axis[:2], across[:2], H - 1.0, L / 2, W / 2, body_top - H)
    band = _box(p[:2], axis[:2], across[:2], 0.22, L / 2 + 0.01, W / 2 + 0.01, body_top - H + 0.5)
    roof = _box(p[:2], axis[:2], across[:2], 0.12, L / 2 + 0.05, W / 2 + 0.05, body_top)
    glass = [_box(p[:2], axis[:2], across[:2], 0.75, L / 2 + 0.01, W / 2 + 0.01, body_top - 1.05)]
    hanger = _tube(np.r_[p[:2], body_top + 0.1], np.r_[p[:2], p[2] - 0.1], 0.05)
    carriage = _box(p[:2], axis[:2], across[:2], 0.25, 0.6, 0.12, p[2] - 0.2)
    top = _box(p[:2], axis[:2], across[:2], 0.25, L / 2, W / 2, body_top - 0.25)
    return np.concatenate([body, top]), np.concatenate([roof, hanger, carriage]), np.concatenate(glass), band


def cableway(level_dir, level_name, ground, near):
    """The cable car near `near` (local x, y of its valley station): [(shape, origin, triangles)]."""
    import bng
    lines = cable_lines(near)
    if not lines:
        print("cableway: no line of swissTLM3D near", near)
        return []
    props, P = max(lines, key=lambda l: np.linalg.norm(l[1][-1, :2] - l[1][0, :2]))
    if np.hypot(*(P[-1, :2] - np.asarray(near))) < np.hypot(*(P[0, :2] - np.asarray(near))):
        P = P[::-1]                                         # from the valley station up
    g = np.array([float(ground(np.array([x]), np.array([y]))[0]) for x, y in P[:, :2]])
    # the supports: the stations at either end, the pylons at the vertices between (the rope over their saddles)
    sup = []
    for k, (x, y, z) in enumerate(P):
        end = k in (0, len(P) - 1)
        # the line's height over the ground where it is a plausible height of the rope (the survey draws it on the
        # saddles of the pylons and at the stations' wheels), else the defaults
        h = z - g[k] if np.isfinite(z) and 3.0 <= z - g[k] <= 45.0 else (CABLE_STATION_H if end else 14.0)
        sup.append((np.array([x, y, g[k]]), g[k] + h, end))
    axis_all = (P[-1, :2] - P[0, :2]) / np.linalg.norm(P[-1, :2] - P[0, :2])
    origin = np.array([P[0, 0], P[0, 1], 0.0])
    mb = bng.MeshBuilder()              # the ropes
    mp = bng.MeshBuilder()              # the pylons (collision)
    mc = bng.MeshBuilder()              # the cabins
    span_len = 0.0
    cab_at = CABIN_EVERY / 2
    for (b0, t0, e0), (b1, t1, e1) in zip(sup[:-1], sup[1:]):
        d = b1[:2] - b0[:2]
        L = float(np.linalg.norm(d))
        ax = np.r_[d / max(L, 1e-6), 0.0]
        across = np.array([-ax[1], ax[0], 0.0])
        for sgn in (-1, 1):
            off = sgn * CABLE_GAUGE / 2 * across
            p0 = np.r_[b0[:2], t0 + 0.3] + off
            p1 = np.r_[b1[:2], t1 + 0.3] + off
            R = rope(p0, p1, CABLE_SAG * L)
            for a, b in zip(R[:-1], R[1:]):
                mb.add("lm_cable_rope", _tube(a, b, CABLE_R).reshape(-1, 3))
            # cabins along this span, at their place along the whole line (up on one track, down on the other)
            s = cab_at
            while s < span_len + L:
                if s > span_len + 15 and s < span_len + L - 15:
                    f = (s - span_len) / L
                    q = p0 + (p1 - p0) * f
                    q[2] -= 4 * CABLE_SAG * L * f * (1 - f)
                    body, rest, glass, band = cabin(q, ax)
                    mc.add("lm_cabin_band", band.reshape(-1, 3))
                    mc.add("lm_cabin", body.reshape(-1, 3))
                    mc.add("lm_cabin_steel", rest.reshape(-1, 3))
                    mc.add("lm_cabin_glass", glass.reshape(-1, 3))
                s += CABIN_EVERY
        span_len += L
    for k, (b, t, end) in enumerate(sup):
        if end:
            continue
        mp.add("lm_pylon", pylon(b, t, axis_all).reshape(-1, 3))
    out = []
    os.makedirs(os.path.join(level_dir, "art", "shapes", "landmarks"), exist_ok=True)
    for m, name, coll in ((mb, "cableway_ropes", False), (mp, "cableway_pylons", True), (mc, "cableway_cabins", False)):
        if m.empty():
            continue
        rel = f"art/shapes/landmarks/{name}.dae"
        m.write_dae(os.path.join(level_dir, rel), name=name.replace("_", ""), origin=origin)
        out.append((f"/levels/{level_name}/{rel}", origin, m.triangle_count(), coll))
    mats = [bng.material("lm_cable_rope", base_color=(0.12, 0.12, 0.12, 1), roughness=0.5, metallic=0.8),
            bng.material("lm_pylon", base_color=STEEL + (1,), roughness=0.6, metallic=0.6, double_sided=True),
            bng.material("lm_cabin", base_color=CABIN_COLOR + (1,), roughness=0.35, metallic=0.2),
            bng.material("lm_cabin_band", base_color=CABIN_BAND + (1,), roughness=0.35, metallic=0.2),
            bng.material("lm_cabin_steel", base_color=(0.3, 0.31, 0.32, 1), roughness=0.5, metallic=0.7),
            bng.material("lm_cabin_glass", base_color=(0.12, 0.15, 0.17, 1), roughness=0.08, metallic=0.1)]
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "landmarks", "main.materials.json"), mats)
    print("cableway:", props.get("NAME") or props.get("OBJEKTART"), len(P), "vertices,", len(sup) - 2, "pylons,",
          round(span_len), "m")
    return out


# ------------------------------------------------------------------ Monte Lema
# The summit of Monte Lema (1621 m) over the top station, seen from the whole map: the weather radar of MeteoSwiss,
# a white dome on a short concrete tower, and the tall slender mast of the transmitter beside it; on the highest
# ground within SUMMIT_SEARCH m of the top station (the DTM). The buildings of the summit (the top station, the
# Ristorante-Ostello Vetta) come from swissBUILDINGS3D (extract_buildings.py keeps FAR_SITES too).
LEMA_TOP = (46.040782, 8.834707)      # WGS84 of the top station (OSM aerialway=station)
LEMA_BOTTOM = (46.023776, 8.856202)   # the valley station at Miglieglia
FAR_SITES = [(LEMA_TOP, 250.0)]       # (WGS84, radius m): buildings kept outside the area
SUMMIT_SEARCH = 260.0
RADAR = (7.0, 5.0)                    # m: diameter of the dome, height of its tower
MAST = (48.0, 1.1, 0.45)              # m: height, base and top diameter of the transmitter mast


def far_zones():
    """Local shapely zones of FAR_SITES."""
    from config import wgs_to_local
    return [shapely.Point(*wgs_to_local(*ll)).buffer(r) for ll, r in FAR_SITES]


def _cyl(c, z0, z1, r0, r1, n=16, cap=True):
    a = np.linspace(0, 2 * np.pi, n + 1)
    P0 = np.column_stack([c[0] + r0 * np.cos(a), c[1] + r0 * np.sin(a), np.full(n + 1, z0)])
    P1 = np.column_stack([c[0] + r1 * np.cos(a), c[1] + r1 * np.sin(a), np.full(n + 1, z1)])
    tris = []
    for k in range(n):
        tris += [[P0[k], P0[k + 1], P1[k + 1]], [P0[k], P1[k + 1], P1[k]]]
        if cap:
            tris.append([P1[k], P1[k + 1], np.array([c[0], c[1], z1])])
    return np.array(tris)


def _dome(c, z, r, n=24, m=10):
    """A sphere of radius r on the point (c, z) (its foot), cut a little at the bottom."""
    out = []
    th = np.linspace(-0.35 * np.pi, 0.5 * np.pi, m + 1)
    ph = np.linspace(0, 2 * np.pi, n + 1)
    P = lambda i, j: np.array([c[0] + r * np.cos(th[i]) * np.cos(ph[j]), c[1] + r * np.cos(th[i]) * np.sin(ph[j]),
                               z + r * np.sin(0.35 * np.pi) + r * np.sin(th[i])])
    for i in range(m):
        for j in range(n):
            out += [[P(i, j), P(i, j + 1), P(i + 1, j + 1)], [P(i, j), P(i + 1, j + 1), P(i + 1, j)]]
    return np.array(out)


def summit(level_dir, level_name, ground):
    """The radar and the mast on the summit of Monte Lema: [(shape, origin, triangles)]. ground: (x, y) -> z of the
    terrain."""
    import bng
    from config import wgs_to_local
    tx, ty = wgs_to_local(*LEMA_TOP)
    g = np.arange(-SUMMIT_SEARCH, SUMMIT_SEARCH + 1, 2.0)
    X, Y = np.meshgrid(tx + g, ty + g)
    Z = np.asarray(ground(X.ravel(), Y.ravel()), float)
    if not np.isfinite(Z).any():
        return []
    k = int(np.nanargmax(Z))
    x, y, z = float(X.ravel()[k]), float(Y.ravel()[k]), float(Z[k])
    origin = np.array([x, y, z])
    mb = bng.MeshBuilder()
    rd, rh = RADAR
    mb.add("lm_concrete", (_cyl((0, 0), -1.0, rh, 2.6, 2.4, 8) ).reshape(-1, 3))
    mb.add("lm_concrete", (_cyl((0, 0), rh - 0.2, rh + 0.4, 3.4, 3.4, 16)).reshape(-1, 3))
    mb.add("lm_radome", _dome((0, 0), rh + 0.2, rd / 2).reshape(-1, 3))
    # the mast 18 m down the ridge towards the station, with a few panels of antennas
    d = np.array([tx - x, ty - y])
    d = d / max(np.linalg.norm(d), 1e-6) * 18.0
    gm = float(np.asarray(ground(np.array([x + d[0]]), np.array([y + d[1]])))[0]) - z
    h, b0, b1 = MAST
    mb.add("lm_mast", _cyl(d, gm - 1.0, gm + h, b0 / 2, b1 / 2, 12).reshape(-1, 3))
    for k, zz in enumerate((0.55, 0.7, 0.85)):
        for ang in (0, 2.1, 4.2):
            c = d + 0.6 * np.array([np.cos(ang + k), np.sin(ang + k)])
            mb.add("lm_mast", _box(c, (np.cos(ang + k), np.sin(ang + k)), (-np.sin(ang + k), np.cos(ang + k)), 2.2,
                                   0.08, 0.3, gm + zz * h).reshape(-1, 3))
    mb.add("lm_mast_red", _cyl(d, gm + h - 0.6, gm + h + 0.3, 0.3, 0.2, 8).reshape(-1, 3))
    os.makedirs(os.path.join(level_dir, "art", "shapes", "landmarks"), exist_ok=True)
    rel = "art/shapes/landmarks/lema_summit.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="lemasummit", origin=np.zeros(3))
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "landmarks", "main.materials.json"), [
        bng.material("lm_concrete", base_color=(0.55, 0.55, 0.53, 1), roughness=0.9),
        bng.material("lm_radome", base_color=(0.85, 0.85, 0.84, 1), roughness=0.45),
        bng.material("lm_mast", base_color=(0.70, 0.71, 0.72, 1), roughness=0.5, metallic=0.5),
        bng.material("lm_mast_red", base_color=(0.6, 0.03, 0.02, 1), roughness=0.5)])
    print("Monte Lema: radar and mast at", np.round(origin, 1))
    return [(f"/levels/{level_name}/{rel}", origin, mb.triangle_count(), True)]
