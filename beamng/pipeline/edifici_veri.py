"""Buildings closer to the real ones (v3.1): the ~20 buildings most seen from the main roads, as the photos show them.

The facades of the level are drawn by rules (facades.py): the openings of a house follow its age, use and floors, the
shutters and the plaster are drawn from the tones of the area, and aerials, dishes and solar panels sit on the roofs
by a hash of the register's EGID (buildings_mesh.house_details). Seen from the road most buildings are generic, also
the ones every driver knows (a supermarket got the roller shutters of a house; michi 2026-10-23: "meglio venti
edifici riconoscibili e accurati che centinaia di edifici generici"). Here, on the built level, for the sites of
dati/edifici_veri.json, each checked by hand against the open street photos (Mapillary, Panoramax) and the 10 cm
orthophoto of the place (edifici_pack.py, verifica/edifici):
- facades: the openings of a facade replaced by the ones the photos show (the modules of the openings atlas,
  bld_textures.py, stretched to their size), or a facade left blank where the real wall has none; the flower boxes
  of the replaced windows (house_extras) go with them;
- the plaster tone of the walls (the vertex colours, the ground's darkening kept) and the tone of the roofs;
- the roof details placed by rule (aerials, dishes, solar panels) taken off where the orthophoto shows none, and
  solar panels laid where it shows them (roof face under a drawn rectangle, as house_details lays them);
- boundary walls, fences and hedges along the lines drawn on the orthophoto, and lettering on the facades of the
  shops (their name in plain capitals; no brand logos), in MissionGroup/buildings/veri.
Facades are matched by their outward azimuth and a point on them, so the step does not depend on the survey's ids.
A finishing step of build_level.py (FINISH, after house_details, before house_extras, which then dresses the new
windows); it also runs on a built zip that has the later steps (nightly patch): then it takes off the flower boxes of
the facades it changes. Alone: python build_level.py --finish edifici_veri

    python edifici_veri.py inventory LEVEL_DIR SITES.json PACK OUT      facades of every site on its orthophoto
"""
import hashlib, json, math, os, re, sys, tempfile, time, zipfile
import numpy as np
import shapely
import bng
import optimize_level
from config import LEVEL_NAME

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO, "dati", "edifici_veri.json")
WALL_MATS = ("bld_plaster", "bld_stone")
OPEN_MATS = ("bld_openings", "bld_openings_lit")
EXTRA_MATS = ("mp_plants", "mp_bark", "mp_fbox_terracotta", "mp_fbox_wood", "mp_fbox_white")
SITE_PAD = 0.8            # m around the roof plan of a site: its walls
FAC_AZ, FAC_OFF = 10.0, 0.8   # degrees, m: a facade of the spec is the level's one within these
OFFSET = 0.03             # m, the openings in front of the wall (facades.OFFSET)
PLANE_TOL = 0.12          # m off the openings' plane: an opening quad of the facade
FRONT = 1.2               # m in front of a facade: its flower boxes
SIGN_OFF = 0.06           # m, lettering in front of the wall
PV_LIFT = 0.10            # m over the roof (house_details)
FAC_GAP = 0.8             # m along a plane between two facades
OUT_TEST = 1.6            # m off a wall: beyond the eaves of the roof plan
ROAD_CLEAR = 1.5          # m beyond the side of an AI road kept free of the boundary walls, fences and hedges


# ------------------------------------------------------------------ the atlas of the openings
_atlas = None


def atlas():
    """name -> {"uv": (u0, v0, u1, v1), "w", "h"} of the openings atlas, as bld_textures.openings_atlas lays it out."""
    global _atlas
    if _atlas is None:
        import bld_textures as bt
        mods = bt.modules(np.random.default_rng(bt.SEED))
        rects = bt.pack(mods)
        AW, AH = bt.ATLAS
        _atlas = {k: {"uv": (x / AW, 1 - (y + h) / AH, (x + w) / AW, 1 - y / AH), "w": mods[k].w, "h": mods[k].h,
                      "lit": float((mods[k].lit > 0).mean())} for k, (x, y, w, h) in rects.items()}
    return _atlas


# ------------------------------------------------------------------ geometry of a site
def facade_groups(tris, ang_tol=6.0, off_tol=0.35):
    """Wall triangles (n, 3, 3) into planar facades: [(indices, outward horizontal normal, plane offset)]
    (texturing.facade_groups)."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    nh = n.copy()
    nh[:, 2] = 0
    nh /= np.maximum(np.linalg.norm(nh, axis=1, keepdims=True), 1e-12)
    ctr = tris.mean(1)
    used = np.zeros(len(tris), bool)
    out = []
    for i in np.argsort(-area):
        if used[i] or area[i] < 1e-4:
            continue
        d0 = float(ctr[i] @ nh[i])
        same = (~used) & ((nh @ nh[i]) > math.cos(math.radians(ang_tol))) & (np.abs(ctr @ nh[i] - d0) < off_tol)
        idx = np.flatnonzero(same)
        used[idx] = True
        out.append((idx, nh[i].copy(), d0))
    return out


class Facade:
    def __init__(self, tris, n, d0):
        self.n = np.array([n[0], n[1], 0.0])
        self.a = np.array([-n[1], n[0], 0.0])           # along the facade: to the right of one who looks at it
        self.d0 = d0
        P = tris.reshape(-1, 3)
        u = P @ self.a
        self.u0, self.u1 = float(u.min()), float(u.max())
        self.z0, self.z1 = float(P[:, 2].min()), float(P[:, 2].max())
        self.o = self.n * d0
        self.az = float(np.degrees(np.arctan2(n[0], n[1])) % 360)
        self.area = float(0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1).sum())
        self.tris = tris

    def point(self, u, z=0.0, off=0.0):
        return self.o + u * self.a + np.array([0, 0, z]) + self.n * off

    def mid(self):
        return self.point(0.5 * (self.u0 + self.u1))[:2]

    def match(self, az, p):
        """Whether the facade of the spec (outward azimuth az, a point p on it) is this one."""
        if abs((az - self.az + 180) % 360 - 180) > FAC_AZ:
            return False
        p = np.array([p[0], p[1], 0.0])
        return abs(p @ self.n - self.d0) < FAC_OFF and self.u0 - 1.0 <= p @ self.a <= self.u1 + 1.0

    def on(self, P, front=(-0.05, PLANE_TOL + OFFSET)):
        """Mask of the points (k, 3) in the slab in front of the facade and within its length."""
        d = P @ self.n - self.d0
        u = P @ self.a
        return (d >= front[0]) & (d <= front[1]) & (u >= self.u0 - 0.1) & (u <= self.u1 + 0.1)


# ------------------------------------------------------------------ the level's shapes
class Shape:
    """A building shape of the level as triangle soups by material (positions in level coordinates)."""

    def __init__(self, name, item, text):
        V, N, T, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(item.get("position", [0, 0, 0]), np.float64)
        self.name, self.item, self.pos = name, item, pos
        m = re.match(r"(.*)_a(\d+)$", node)
        self.base, self.detail = (m.group(1), int(m.group(2))) if m else (node, 2)
        self.parts = {}
        for mat, p in parts:
            tri = p.reshape(-1, 3, p.shape[1])
            soup = dict(V=V[tri[..., 0]] + pos, N=N[tri[..., 1]], T=T[tri[..., 2]],
                        C=C[tri[..., 3]] if C is not None and p.shape[1] > 3 else np.ones(tri.shape[:2] + (4,)))
            self.parts[mat] = soup
        self.changed = False
        allv = np.concatenate([s["V"].reshape(-1, 3) for s in self.parts.values()]) if self.parts else np.zeros((1, 3))
        self.box = shapely.box(*allv[:, :2].min(0), *allv[:, :2].max(0))

    def add(self, mat, V, T, C=None, N=None):
        V = np.asarray(V, float).reshape(-1, 3, 3)
        T = np.asarray(T, float).reshape(-1, 3, 2)
        if N is None:
            n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            N = np.repeat(n[:, None], 3, 1)
        C = np.ones(V.shape[:2] + (4,)) if C is None else np.broadcast_to(np.asarray(C, float), V.shape[:2] + (4,))
        s = self.parts.setdefault(mat, dict(V=np.zeros((0, 3, 3)), N=np.zeros((0, 3, 3)), T=np.zeros((0, 3, 2)),
                                            C=np.zeros((0, 3, 4))))
        for k, a in (("V", V), ("N", N), ("T", T), ("C", C)):
            s[k] = np.concatenate([s[k], a])
        self.changed = True

    def drop(self, mat, mask):
        if mask.any():
            s = self.parts[mat]
            for k in s:
                s[k] = s[k][~mask]
            self.changed = True

    def dae(self):
        mb = bng.MeshBuilder()
        for mat, s in self.parts.items():
            if not len(s["V"]):
                continue
            mb.add(mat, s["V"].reshape(-1, 3), uvs=s["T"].reshape(-1, 2), normals=s["N"].reshape(-1, 3),
                   colors=s["C"].reshape(-1, 4))
        tmp = os.path.join(tempfile.gettempdir(), f"veri_{os.getpid()}.dae")
        mb.write_dae(tmp, name=self.base, origin=self.pos, detail=self.detail)
        data = open(tmp, "rb").read()
        os.remove(tmp)
        return data


def site_walls(shapes, outline):
    """(walls (k, 3, 3), [(shape, material, mask)]) of a site: the wall triangles inside its padded roof plan."""
    zone = outline.buffer(SITE_PAD)
    tris, where = [], []
    for sh in shapes:
        if not sh.box.intersects(zone):
            continue
        for mat in WALL_MATS:
            s = sh.parts.get(mat)
            if s is None or not len(s["V"]):
                continue
            V = s["V"]
            inside = np.all(shapely.contains_xy(zone, V[..., 0], V[..., 1]), axis=1)
            n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
            vert = np.abs(n[:, 2]) < 0.3 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
            m = inside & vert
            if m.any():
                tris.append(V[m])
                where.append((sh, mat, m))
    return (np.concatenate(tris) if tris else np.zeros((0, 3, 3))), where


def site_facades(shapes, outline, min_len=1.4):
    walls, _ = site_walls(shapes, outline)
    if not len(walls):
        return []
    facs = []
    groups = []
    for idx, n, d0 in facade_groups(walls):
        # one plane can hold the walls of houses apart along the street: a facade is a run without gaps
        a = np.array([-n[1], n[0], 0.0])
        U = walls[idx] @ a
        lo, hi = U.min(1), U.max(1)
        order = np.argsort(lo)
        run, end = [order[0]], hi[order[0]]
        for i in order[1:]:
            if lo[i] > end + FAC_GAP:
                groups.append((idx[run], n, d0))
                run, end = [], -np.inf
            run.append(i)
            end = max(end, hi[i])
        groups.append((idx[run], n, d0))
    for idx, n, d0 in groups:
        f = Facade(walls[idx], n, d0)
        if f.u1 - f.u0 < min_len or f.z1 - f.z0 < 1.5:
            continue
        # the walls are drawn from both sides (buildings_mesh.WALL_TWO_SIDED): their winding does not tell the
        # outside. Outside is where the roof plan is not; a wall with the plan on both sides is inside the block
        ahead = shapely.contains(outline, shapely.points(f.mid() + f.n[:2] * OUT_TEST))
        behind = shapely.contains(outline, shapely.points(f.mid() - f.n[:2] * OUT_TEST))
        if ahead and behind:
            continue
        if ahead:
            f = Facade(walls[idx], -np.asarray(n), -d0)
        facs.append(f)
    facs.sort(key=lambda f: (-f.area))
    return facs


# ------------------------------------------------------------------ the changes
def tone_walls(shapes, outline, rgb, mean_plaster):
    """The walls of a site in the plaster tone rgb (sRGB 0..1), their darkening at the ground kept."""
    _, where = site_walls(shapes, outline)
    target = np.clip(np.asarray(rgb, float) / mean_plaster, 0, 1)
    for sh, mat, m in where:
        if mat != "bld_plaster":
            continue
        C = sh.parts[mat]["C"]
        lum = C[m][..., :3].sum(-1)
        ref = np.percentile(lum, 95) if lum.size else 1.0
        ao = np.clip(lum / max(ref, 1e-6), 0.5, 1.0)
        C[m, :, :3] = target[None, None, :] * ao[..., None]
        sh.changed = True


def tone_facade(shapes, f, ranges, mean_plaster):
    """The walls in the plane of facade f in their own tones: ranges [[u0, u1, rgb], ...] along it (m from its left
    end), as the houses of a row each have theirs; the corners turning off the facade keep the site's tone."""
    for sh in shapes:
        s = sh.parts.get("bld_plaster")
        if s is None or not len(s["V"]) or not sh.box.intersects(
                shapely.LineString([f.point(f.u0)[:2], f.point(f.u1)[:2]]).buffer(3)):
            continue
        on = f.on(s["V"].reshape(-1, 3), (-0.05, 0.05)).reshape(-1, 3).all(1)
        if not on.any():
            continue
        u = (s["V"].mean(1) @ f.a) - f.u0
        lum = s["C"][..., :3].sum(-1)
        ref = np.percentile(lum[on], 95)
        for u0, u1, rgb in ranges:
            m = on & (u >= u0) & (u < u1)
            if m.any():
                ao = np.clip(lum[m] / max(ref, 1e-6), 0.5, 1.0)
                s["C"][m, :, :3] = np.clip(np.asarray(rgb, float) / mean_plaster, 0, 1)[None, None, :] * ao[..., None]
                sh.changed = True


def module_at(uv):
    """The atlas modules of opening triangles from their uv centroids (k, 2): names, None off every module."""
    idx = atlas()
    names = list(idx)
    R = np.array([idx[k]["uv"] for k in names])
    out = []
    for c in np.asarray(uv) - np.floor(uv):       # the shapes shift their uvs by whole tiles (bng.write_dae)
        h = np.nonzero((R[:, 0] <= c[0]) & (c[0] <= R[:, 2]) & (R[:, 1] <= c[1]) & (c[1] <= R[:, 3]))[0]
        out.append(names[h[0]] if len(h) else None)
    return out


def swap_openings(shapes, f, rules, ground, rep):
    """The openings of facade f changed in place, as the photos show them: rules [{"map": {pattern: module}, "u":
    [u0, u1], "z": [z0, z1]}] (fnmatch patterns of the atlas modules; u from the facade's left end, z of the opening's
    foot over the ground; both optional). Each opening keeps its place (the middle of its foot) and takes the size of
    the new module; module "" takes it off."""
    import fnmatch
    idx = atlas()
    for sh in shapes:
        for mat in OPEN_MATS:
            s = sh.parts.get(mat)
            if s is None or not len(s["V"]) or s.get("T") is None:
                continue
            on = f.on(s["V"].reshape(-1, 3)).reshape(-1, 3).all(1)
            if not on.any():
                continue
            mods = module_at(s["T"].mean(1))
            drop = np.zeros(len(s["V"]), bool)
            for i in np.nonzero(on)[0]:
                m0 = mods[i]
                if m0 is None:
                    continue
                V, T = s["V"][i], s["T"][i] - np.floor(s["T"][i].mean(0))
                shift = np.floor(s["T"][i].mean(0))
                # the affine map uv -> position of this triangle
                A = np.linalg.lstsq(np.c_[T, np.ones(3)], V, rcond=None)[0]       # (3, 3): rows du, dv, origin
                r0 = idx[m0]["uv"]
                foot = np.array([0.5 * (r0[0] + r0[2]), r0[1], 1.0]) @ A
                u = foot @ f.a - f.u0
                z = foot[2] - float(ground(*foot[:2])[0])
                new = None
                for r in rules:
                    if "u" in r and not r["u"][0] <= u <= r["u"][1]:
                        continue
                    if "z" in r and not r["z"][0] <= z <= r["z"][1]:
                        continue
                    for pat, tgt in r["map"].items():
                        if fnmatch.fnmatch(m0, pat):
                            new = tgt
                            break
                    if new is not None:
                        break
                if new is None or new == m0:
                    continue
                if new == "":
                    drop[i] = True
                    continue
                if new not in idx:
                    raise SystemExit(f"edifici_veri: no module {new} in the openings atlas")
                r1 = idx[new]["uv"]
                eu = A[0] / np.linalg.norm(A[0])
                ev = A[1] / np.linalg.norm(A[1])
                t = (T - [r0[0], r0[1]]) / [r0[2] - r0[0], r0[3] - r0[1]]
                s["V"][i] = foot + (t[:, :1] - 0.5) * idx[new]["w"] * eu + t[:, 1:] * idx[new]["h"] * ev
                s["T"][i] = shift + [r1[0], r1[1]] + t * [r1[2] - r1[0], r1[3] - r1[1]]
                sh.changed = True
                rep["swapped"] = rep.get("swapped", 0) + 0.5
            if drop.any():
                sh.drop(mat, drop)
                rep["swapped"] = rep.get("swapped", 0) + 0.5 * int(drop.sum())


def tone_roofs(shapes, outline, rgb):
    """The roof faces over a site in the vertex tone rgb (multiplies the roof textures)."""
    for sh in shapes:
        if not sh.box.intersects(outline):
            continue
        for mat, s in sh.parts.items():
            if not mat.startswith("bld_roof") or not len(s["V"]):
                continue
            c = s["V"].mean(1)
            m = shapely.contains_xy(outline, c[:, 0], c[:, 1])
            if m.any():
                s["C"][m, :, :3] = np.asarray(rgb, float)[None, None, :]
                sh.changed = True


def clear_facade(shapes, f, balconies=False):
    """Takes the openings off a facade (and, with balconies, the slabs and railings in front of it)."""
    n = 0
    for sh in shapes:
        if not sh.box.intersects(shapely.LineString([f.point(f.u0)[:2], f.point(f.u1)[:2]]).buffer(3)):
            continue
        for mat in OPEN_MATS + (("bld_plaster",) if balconies else ()):
            s = sh.parts.get(mat)
            if s is None or not len(s["V"]):
                continue
            P = s["V"].reshape(-1, 3)
            if mat == "bld_plaster":       # balcony slabs: off the wall, above the foot
                ok = f.on(P, (0.015, 2.2)).reshape(-1, 3).all(1) & (s["V"][..., 2].min(1) > f.z0 + 1.5)
            else:
                ok = f.on(P, (-0.05, 2.2 if balconies else PLANE_TOL + OFFSET)).reshape(-1, 3).all(1)
            sh.drop(mat, ok)
            n += int(ok.sum())
    return n


def roads_zone(zi, lv, near):
    """The AI roads near the sites, as wide as they are plus ROAD_CLEAR: no boundary wall, fence or hedge goes there."""
    import lamps as pl
    f = f"{lv}/main/MissionGroup/AIRoads/items.level.json"
    polys = []
    if f in zi.NameToInfo:
        for o in pl.read_items(zi, f):
            nd = np.asarray(o.get("nodes", []), float)
            if o.get("class") != "DecalRoad" or len(nd) < 2:
                continue
            for a, b in zip(nd[:-1], nd[1:]):
                seg = shapely.LineString([a[:2], b[:2]])
                if seg.distance(near) < 60:
                    polys.append(seg.buffer(0.5 * max(a[3], b[3]) + ROAD_CLEAR))
    return shapely.union_all(polys) if polys else shapely.Polygon()


def clear_of(line, zone):
    """The pieces of a polyline out of the zone, at least 1 m long."""
    g = shapely.LineString(line).difference(zone)
    return [list(p.coords) for p in getattr(g, "geoms", [g]) if not p.is_empty and p.length >= 1.0]


def ground_fn(zi, lv):
    import lamps as pl
    import network_mesh as pu
    import walls as pw
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    return lambda x, y: pu.terrain_top(q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))


def openings_of(fs):
    """The openings of a facade of the spec: [(module, u from the left end, bottom over the ground, w, h)];
    rows {"row": module, "z": bottom, "from": u, "to": u, "n": count[, "w", "h"]} spread evenly."""
    out = []
    for o in fs.get("openings", []):
        if isinstance(o, dict):
            n = int(o["n"])
            step = (o["to"] - o["from"]) / max(n - 1, 1) if n > 1 else 0.0
            for k in range(n):
                out.append((o["row"], o["from"] + k * step, o["z"], o.get("w"), o.get("h")))
        else:
            mod, u, z = o[:3]
            out.append((mod, u, z, o[3] if len(o) > 3 else None, o[4] if len(o) > 4 else None))
    return out


def place_openings(target, f, fs, ground, rep):
    """The openings of the spec on facade f, as quads OFFSET m in front of it, in the shape `target`.
    u: m from the facade's left end as one sees it from outside; z: m over the ground in front of the opening."""
    idx = atlas()
    lit_v, lit_t, v, t = [], [], [], []
    for mod, u, z, w, h in openings_of(fs):
        m = idx.get(mod)
        if m is None:
            raise SystemExit(f"edifici_veri: no module {mod} in the openings atlas")
        w, h = w or m["w"], h or m["h"]
        uc = f.u0 + u
        if uc - w / 2 < f.u0 - 0.05 or uc + w / 2 > f.u1 + 0.05:
            rep.setdefault("off_facade", []).append(f"{fs.get('id', '?')}:{mod}@{u}")
        g = float(ground(*f.point(uc, off=0.6)[:2])[0])
        zb = g + z
        c = [f.point(uc - w / 2, zb, OFFSET), f.point(uc + w / 2, zb, OFFSET), f.point(uc + w / 2, zb + h, OFFSET),
             f.point(uc - w / 2, zb + h, OFFSET)]
        u0, v0, u1, v1 = m["uv"]
        tt = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        V = [[c[0], c[1], c[2]], [c[0], c[2], c[3]]]
        T = [[tt[0], tt[1], tt[2]], [tt[0], tt[2], tt[3]]]
        lit = m["lit"] > 0.02 and int(hashlib.md5(f"{uc:.1f}{zb:.1f}".encode()).hexdigest()[:4], 16) % 100 < 35
        (lit_v if lit else v).extend(V)
        (lit_t if lit else t).extend(T)
        rep["openings"] += 1
    N = np.repeat(f.n[None, None], 3, 1)
    if v:
        target.add("bld_openings", v, t, N=np.repeat(N, len(v), 0))
    if lit_v:
        target.add("bld_openings_lit", lit_v, lit_t, N=np.repeat(N, len(lit_v), 0))


def owner(shapes, f):
    """The shape that holds most of a facade's walls (the new openings go there)."""
    best, nb = None, -1
    for sh in shapes:
        k = 0
        for mat in WALL_MATS:
            s = sh.parts.get(mat)
            if s is not None and len(s["V"]):
                k += int(f.on(s["V"].mean(1), (-0.1, 0.1)).sum())
        if k > nb:
            best, nb = sh, k
    return best


# ------------------------------------------------------------------ extras: walls, fences, hedges, lettering
def wall_run(add, line, h, w, z_of, mat, top):
    """A boundary wall w m thick along a polyline, from below the ground to h m over it, with its top."""
    pts = np.asarray(line, float)
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        L = float(np.hypot(*d))
        if L < 0.05:
            continue
        nrm = np.array([-d[1], d[0]]) / L * w / 2
        za, zb = z_of(*a), z_of(*b)
        A0, A1, B0, B1 = a + nrm, a - nrm, b + nrm, b - nrm
        lo_a, lo_b = za - 0.4, zb - 0.4
        hi_a, hi_b = za + h, zb + h
        P = lambda p, z: [p[0], p[1], z]
        for p, q in ((A0, B0), (B1, A1)):          # the two faces
            zp = hi_a if p is A0 or p is A1 else hi_b
            zq = hi_b if q is B0 or q is B1 else hi_a
            lp = lo_a if zp == hi_a else lo_b
            lq = lo_b if zq == hi_b else lo_a
            c = [P(p, lp), P(q, lq), P(q, zq), P(p, zp)]
            add(mat, [[c[0], c[1], c[2]], [c[0], c[2], c[3]]], [[(0, lp), (L, lq), (L, zq)], [(0, lp), (L, zq), (0, zp)]])
        for p, q, z1, z0 in ((A1, A0, hi_a, lo_a), (B0, B1, hi_b, lo_b)):   # the ends
            c = [P(p, z0), P(q, z0), P(q, z1), P(p, z1)]
            add(mat, [[c[0], c[1], c[2]], [c[0], c[2], c[3]]], [[(0, 0), (w, 0), (w, h)], [(0, 0), (w, h), (0, h)]])
        c = [P(A0, hi_a), P(B0, hi_b), P(B1, hi_b), P(A1, hi_a)]          # the top
        add(top, [[c[0], c[1], c[2]], [c[0], c[2], c[3]]], [[(0, 0), (L, 0), (L, w)], [(0, 0), (L, w), (0, w)]])


def fence_run(add, line, h, z_of):
    """A chain-link fence along a polyline: posts every 2.5 m, the mesh both sides (fences.py materials)."""
    pts = np.asarray(line, float)
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        L = float(np.hypot(*d))
        if L < 0.05:
            continue
        za, zb = z_of(*a), z_of(*b)
        c = [[a[0], a[1], za], [b[0], b[1], zb], [b[0], b[1], zb + h], [a[0], a[1], za + h]]
        for cc in (c, [c[1], c[0], c[3], c[2]]):
            add("mp_chainlink", [[cc[0], cc[1], cc[2]], [cc[0], cc[2], cc[3]]],
                [[(0, 0), (L / 1.0, 0), (L / 1.0, h)], [(0, 0), (L / 1.0, h), (0, h)]] if cc is c else
                [[(L, 0), (0, 0), (0, h)], [(L, 0), (0, h), (L, h)]])
        for k in range(int(L // 2.5) + 2):
            s = min(k * 2.5, L) / L
            p = a + s * d
            z = za + s * (zb - za)
            r = 0.03
            for (dx0, dy0), (dx1, dy1) in (((-r, -r), (r, -r)), ((r, -r), (r, r)), ((r, r), (-r, r)), ((-r, r), (-r, -r))):
                q0, q1 = p + (dx0, dy0), p + (dx1, dy1)
                cc = [[q0[0], q0[1], z - 0.3], [q1[0], q1[1], z - 0.3], [q1[0], q1[1], z + h + 0.05], [q0[0], q0[1], z + h + 0.05]]
                add("mp_fence_post", [[cc[0], cc[1], cc[2]], [cc[0], cc[2], cc[3]]],
                    [[(0, 0), (0.06, 0), (0.06, h)], [(0, 0), (0.06, h), (0, h)]])


def hedge_run(add, line, h, w, z_of):
    """A clipped hedge: a box of leaves along a polyline (the game's hedge material)."""
    wall_run(add, line, h, w, z_of, "mp_veri_hedge", "mp_veri_hedge")


def lettering(texts, size=(2048, 1024)):
    """The shops' lettering on one texture: [(text, colour, background)] -> (RGBA PNG bytes, uv boxes, aspect)."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    rows = max(1, len(texts))
    rh = H // rows if rows else H
    rh = min(rh, 160)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if os.path.exists(p):
            font = ImageFont.truetype(p, int(rh * 0.72))
            break
    if font is None:
        font = ImageFont.load_default(size=int(rh * 0.72))
    boxes = []
    for k, (txt, col, bg) in enumerate(texts):
        y0 = k * rh
        bb = dr.textbbox((0, 0), txt, font=font)
        tw = min(W - 8, bb[2] - bb[0] + int(rh * 0.5))
        if bg:
            dr.rectangle((0, y0 + 2, tw, y0 + rh - 2), fill=tuple(int(255 * c) for c in bg) + (255,))
        dr.text((int(rh * 0.25) - bb[0], y0 + (rh - (bb[3] - bb[1])) // 2 - bb[1]), txt, font=font,
                fill=tuple(int(255 * c) for c in col) + (255,))
        boxes.append(((0, 1 - (y0 + rh) / H, tw / W, 1 - y0 / H), tw / rh))
    import io
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue(), boxes


# ------------------------------------------------------------------ the step
def edifici_veri_step(root, report=None, spec_path=SPEC):
    import lamps as pl
    import poles as pr
    t0 = time.time()
    spec = json.load(open(spec_path))["sites"]
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    grp = f"{lv}/main/MissionGroup/buildings/items.level.json"
    items = pl.read_items(zi, grp)
    if any(o.get("name") == "veri" for o in items):
        raise SystemExit("the level has a buildings/veri group already: edifici_veri runs once")
    ground = ground_fn(zi, lv)
    z_of = lambda x, y: float(ground(x, y)[0])
    rep = {"sites": 0, "facades": 0, "openings": 0, "openings_off": 0, "toned": 0, "details_off": 0, "pv": 0,
           "flower_boxes_off": 0, "walls_m": 0.0, "fences_m": 0.0, "hedges_m": 0.0, "signs": 0, "unmatched": []}
    outlines = [shapely.Polygon(s["outline"]) for s in spec]
    every = shapely.union_all([o.buffer(4) for o in outlines])
    roads = roads_zone(zi, lv, every)
    # the building shapes near the sites
    shapes = []
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or "/details/" in sn or "/extras/" in sn:
            continue
        sh = Shape(sn, o, zi.read(sn).decode("utf-8"))
        if sh.box.intersects(every):
            shapes.append(sh)
    # the house details and extras near the sites
    def group_shapes(sub):
        f = f"{lv}/main/MissionGroup/buildings/{sub}/items.level.json"
        out = []
        if f not in zi.NameToInfo:
            return out
        for o in pl.read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") == "TSStatic" and sn in zi.NameToInfo:
                sh = Shape(sn, o, zi.read(sn).decode("utf-8"))
                if sh.box.intersects(every):
                    out.append(sh)
        return out
    details, extras = group_shapes("details"), group_shapes("extras")
    import bld_textures as bt
    from PIL import Image
    tex = Image.open(io_bytes(zi.read(f"{lv}/art/shapes/buildings/t_bld_plaster_b.color.png"))).convert("RGB")
    mean_plaster = np.asarray(tex, np.float32).reshape(-1, 3).mean(0) / 255.0
    adds = {}                                   # site -> MeshBuilder parts of the extras
    signs = []
    for s, outline in zip(spec, outlines):
        rep["sites"] += 1
        facs = site_facades(shapes, outline)
        if s.get("tone"):
            tone_walls(shapes, outline, s["tone"], mean_plaster)
            rep["toned"] += 1
        if s.get("roof_tone"):
            tone_roofs(shapes, outline, s["roof_tone"])
        for fs in s.get("facades", []):
            hit = [f for f in facs if f.match(fs["az"], fs["p"])]
            if not hit:
                rep["unmatched"].append(f"{s['id']}:{fs.get('id', fs['az'])}")
                continue
            f = min(hit, key=lambda f: abs(np.array([*fs["p"], 0.0]) @ f.n - f.d0))
            rep["facades"] += 1
            if fs.get("tones"):
                tone_facade(shapes, f, fs["tones"], mean_plaster)
            if fs.get("swap"):
                swap_openings(shapes, f, fs["swap"], ground, rep)
            if "openings" not in fs:             # a facade only toned or lettered keeps its openings
                for sg in fs.get("signs", []):
                    signs.append((s["id"], f, sg))
                continue
            rep["openings_off"] += clear_facade(shapes, f, balconies=fs.get("clear_balconies", False))
            for sh in extras:                      # the flower boxes of the windows taken off
                for mat in EXTRA_MATS:
                    x = sh.parts.get(mat)
                    if x is not None and len(x["V"]):
                        m = f.on(x["V"].reshape(-1, 3), (-0.05, FRONT)).reshape(-1, 3).all(1)
                        rep["flower_boxes_off"] += int(m.sum())
                        sh.drop(mat, m)
            place_openings(owner(shapes, f), f, fs, ground, rep)
            for sg in fs.get("signs", []):
                signs.append((s["id"], f, sg))
        # roof details: off where the orthophoto shows none
        off = [k for k in ("aerial", "dish", "pv") if s.get(k) is False]
        mats = {"aerial": ("mp_house_metal",), "dish": ("mp_house_dish",), "pv": ("mp_house_pv",)}
        zone = outline.buffer(0.5)
        for k in off:
            for sh in details:
                for mat in mats[k]:
                    x = sh.parts.get(mat)
                    if x is not None and len(x["V"]):
                        c = x["V"].mean(1)
                        m = shapely.contains_xy(zone, c[:, 0], c[:, 1])
                        if k == "aerial":           # the masts of the aerials, not the gutters' metal: over the roof
                            m &= x["V"][..., 2].max(1) > 0
                        rep["details_off"] += int(m.sum())
                        sh.drop(mat, m)
        # solar panels where the orthophoto shows them
        for pv in s.get("pv_add", []):
            tris, uv = pv_on_roof(shapes, shapely.Polygon(pv))
            if tris is not None:
                adds.setdefault(s["id"], []).append(("mp_house_pv", tris, uv))
                rep["pv"] += 1
        parts = adds.setdefault(s["id"], [])
        add = lambda m, V, T: parts.append((m, np.asarray(V, float), np.asarray(T, float)))
        for w in s.get("walls", []):
            mat = {"stone": "mp_wall_stone", "concrete": "mp_wall_concrete", "plaster": "mp_wall_plaster"}[w.get("kind", "stone")]
            for line in clear_of(w["line"], roads):
                wall_run(add, line, w.get("h", 1.0), w.get("w", 0.3), z_of, mat, mat.replace("_plaster", "_concrete") +
                         "_top" if mat != "mp_wall_plaster" else "mp_wall_concrete_top")
                rep["walls_m"] += shapely.LineString(line).length
        for fe in s.get("fences", []):
            for line in clear_of(fe["line"], roads):
                fence_run(add, line, fe.get("h", 1.2), z_of)
                rep["fences_m"] += shapely.LineString(line).length
        for he in s.get("hedges", []):
            for line in clear_of(he["line"], roads):
                hedge_run(add, line, he.get("h", 1.4), he.get("w", 0.7), z_of)
                rep["hedges_m"] += shapely.LineString(line).length
    # lettering: one texture for all
    new_files = {}
    if signs:
        png, boxes = lettering([(sg["text"], sg.get("color", (0.15, 0.15, 0.15)), sg.get("bg")) for _, _, sg in signs])
        new_files[f"{lv}/art/shapes/buildings/veri/t_veri_signs_b.color.png"] = png
        for (sid, f, sg), (uv, aspect) in zip(signs, boxes):
            h = sg.get("h", 0.6)
            w = h * aspect
            uc = f.u0 + sg["u"]
            zb = z_of(*f.point(uc, off=0.6)[:2]) + sg["z"]
            c = [f.point(uc - w / 2, zb, SIGN_OFF), f.point(uc + w / 2, zb, SIGN_OFF), f.point(uc + w / 2, zb + h, SIGN_OFF),
                 f.point(uc - w / 2, zb + h, SIGN_OFF)]
            u0, v0, u1, v1 = uv
            adds.setdefault(sid, []).append(("mp_veri_signs", np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]]),
                                             np.array([[(u0, v0), (u1, v0), (u1, v1)], [(u0, v0), (u1, v1), (u0, v1)]])))
            rep["signs"] += 1
    # write
    for sh in shapes + details + extras:
        if sh.changed:
            new_files[sh.name] = sh.dae()
    vitems = []
    for sid, parts in sorted(adds.items()):
        if not parts:
            continue
        mb = bng.MeshBuilder()
        allv = np.concatenate([V.reshape(-1, 3) for _, V, _ in parts])
        origin = np.round(allv.mean(0), 1)
        for m, V, T in parts:
            Vv = V.reshape(-1, 3)
            mb.add(m, Vv, uvs=T.reshape(-1, 2), normals=bng.flat_normals_soup(Vv))
        rel = f"art/shapes/buildings/veri/veri_{sid}.dae"
        tmp = os.path.join(tempfile.gettempdir(), f"veri_{sid}_{os.getpid()}.dae")
        mb.write_dae(tmp, name="veri", origin=origin, detail=2)
        new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
        os.remove(tmp)
        ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True)
        ob["__parent"] = "veri"
        vitems.append(ob)
    t = f"/levels/{LEVEL_NAME}/art/shapes/buildings/veri"
    mats = [bng.material("mp_veri_signs", f"{t}/t_veri_signs_b.color.png", roughness=0.5, alpha_test=80, double_sided=False),
            bng.material("mp_veri_hedge", base_color=[0.16, 0.25, 0.11, 1], roughness=0.95, ground_type="GRASS")]
    tmp = os.path.join(tempfile.gettempdir(), f"veri_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/buildings/veri/veri.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    if any(sh.changed for sh in details) and not any(n.endswith("t_pv_b.color.png") for n in zi.NameToInfo):
        pass
    if vitems:
        new_files[grp] = pr.pl_write(items + [{"name": "veri", "class": "SimGroup", "persistentId": bng.pid(),
                                               "__parent": "buildings"}])
        new_files[f"{lv}/main/MissionGroup/buildings/veri/items.level.json"] = pr.pl_write(vitems)
    with zi.writer() as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            ni.external_attr = 0o644 << 16
            zo.writestr(ni, data)
    rep["walls_m"], rep["fences_m"], rep["hedges_m"] = (round(rep[k], 1) for k in ("walls_m", "fences_m", "hedges_m"))
    print("edifici_veri: %d sites, %d facades (%d opening triangles off, %d openings on), %d toned, %d detail "
          "triangles off, %d panels, %.0f m walls, %.0f m fences, %.0f m hedges, %d signs, unmatched %s; %.0f s"
          % (rep["sites"], rep["facades"], rep["openings_off"], rep["openings"], rep["toned"], rep["details_off"],
             rep["pv"], rep["walls_m"], rep["fences_m"], rep["hedges_m"], rep["signs"], rep["unmatched"],
             time.time() - t0), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


def io_bytes(b):
    import io
    return io.BytesIO(b)


def pv_on_roof(shapes, poly):
    """Solar panels over the roof face under a rectangle drawn on the orthophoto: (triangles, uvs) or (None, None)."""
    c = poly.centroid
    best = None
    for sh in shapes:
        if not sh.box.intersects(poly):
            continue
        for mat, s in sh.parts.items():
            if not mat.startswith("bld_roof") or not len(s["V"]):
                continue
            V = s["V"]
            for t in V[shapely.intersects(shapely.polygons(V[..., :2]), c)]:
                n = np.cross(t[1] - t[0], t[2] - t[0])
                if n[2] <= 0:
                    n = -n
                n /= np.linalg.norm(n)
                z = t[0, 2] - ((c.x - t[0, 0]) * n[0] + (c.y - t[0, 1]) * n[1]) / n[2]
                if best is None or z > best[0]:
                    best = (z, t[0], n)
    if best is None:
        return None, None
    _, p0, n = best
    zf = lambda x, y: p0[2] - ((x - p0[0]) * n[0] + (y - p0[1]) * n[1]) / n[2]
    pts = np.array(poly.exterior.coords[:4])
    C = [np.array([x, y, zf(x, y)]) + n * PV_LIFT for x, y in pts]
    w = float(np.linalg.norm(C[1] - C[0]))
    h = float(np.linalg.norm(C[2] - C[1]))
    tris = np.array([[C[0], C[1], C[2]], [C[0], C[2], C[3]]])
    if np.cross(C[1] - C[0], C[2] - C[0]) @ n < 0:
        tris = tris[:, ::-1]
        uv = np.array([[[w, h], [w, 0], [0, 0]], [[0, h], [w, h], [0, 0]]]) / np.array([1.0, 1.7])
    else:
        uv = np.array([[[0, 0], [w, 0], [w, h]], [[0, 0], [w, h], [0, h]]]) / np.array([1.0, 1.7])
    return tris, uv


# ------------------------------------------------------------------ inventory for the hand check
def inventory(level_dir, sites_path, pack, out):
    """Every facade of the sites, drawn and numbered on the site's orthophoto (pack/<site>/orto.jpg) and listed
    (out/facades.json: id, outward azimuth, a point on it, length, height, openings now)."""
    from PIL import Image, ImageDraw, ImageFont
    import glob
    sites = json.load(open(sites_path))["sites"]
    os.makedirs(out, exist_ok=True)
    zone = shapely.union_all([shapely.Polygon(s["outline"]).buffer(4) for s in sites])
    lv = os.path.join(level_dir)
    items = [json.loads(l) for l in open(os.path.join(lv, "main/MissionGroup/buildings/items.level.json"))]
    shapes = []
    for o in items:
        sn = o.get("shapeName", "")
        if not sn.endswith(".dae") or "/details/" in sn or "/extras/" in sn:
            continue
        f = os.path.join(lv, sn.split(f"/levels/{LEVEL_NAME}/", 1)[1])
        txt = open(f).read()
        sh = Shape(sn, o, txt)
        if sh.box.intersects(zone):
            shapes.append(sh)
    res = {}
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    except Exception:
        font = ImageFont.load_default()
    for s in sites:
        outline = shapely.Polygon(s["outline"])
        facs = site_facades(shapes, outline)
        rows = []
        for k, f in enumerate(facs):
            n_open = 0
            for sh in shapes:
                for mat in OPEN_MATS:
                    x = sh.parts.get(mat)
                    if x is not None and len(x["V"]):
                        n_open += int(f.on(x["V"].reshape(-1, 3)).reshape(-1, 3).all(1).sum()) // 2
            rows.append({"id": f"f{k + 1}", "az": round(f.az, 1), "p": [round(v, 2) for v in f.mid()],
                         "len": round(f.u1 - f.u0, 2), "h": round(f.z1 - f.z0, 2), "openings": n_open})
        res[s["id"]] = rows
        op = os.path.join(pack, s["id"], "orto.jpg")
        if not os.path.exists(op):
            continue
        im = Image.open(op).convert("RGB")
        x0, y0, x1, y1 = s["bbox"]
        X0, Y1 = x0 - 15.0, y1 + 15.0
        px = lambda x, y: ((x - X0) / 0.1, (Y1 - y) / 0.1)
        dr = ImageDraw.Draw(im)
        dr.line([px(*p) for p in s["outline"]], fill=(255, 255, 0), width=2)
        for k, f in enumerate(facs):
            a, b = f.point(f.u0)[:2], f.point(f.u1)[:2]
            dr.line([px(*a), px(*b)], fill=(255, 40, 40), width=5)
            m = f.mid() + f.n[:2] * 2.2
            dr.text(px(*m), f"f{k + 1}", fill=(255, 255, 255), font=font, stroke_width=3, stroke_fill=(0, 0, 0))
            # the left end, as one sees the facade from outside
            dr.ellipse([px(*a)[0] - 7, px(*a)[1] - 7, px(*a)[0] + 7, px(*a)[1] + 7], fill=(0, 255, 255))
        # a 10 m scale bar and north
        dr.line([(20, im.size[1] - 30), (120, im.size[1] - 30)], fill=(255, 255, 255), width=6)
        dr.text((20, im.size[1] - 70), "10 m  N up", fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        im.save(os.path.join(out, f"{s['id']}_facciate.jpg"), quality=85)
    json.dump(res, open(os.path.join(out, "facades.json"), "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "inventory":
        inventory(*sys.argv[2:6])
