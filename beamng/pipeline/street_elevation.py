"""Elevations of facades as the game draws them, for the review of the street reference (v3.0.40): the wall in its
tone, the plinth and every opening with the atlas of bld_textures.py, flat on the facade's own plane (u along the
wall, z up), in the frame of the rectified facades of street_facades.py, so that a photo of a facade, the facade of a
built level and a new layout can be laid side by side.

- level(f, lv): the facade f (street_facades.Facade) as a built level has it (its building tiles: the openings, the
  plinth, the balconies and the wall triangles within a few metres in front of the plane);
- layout(f, openings, tone): a list of openings (atlas module, u centre, z bottom, width, height) drawn the same way.

    python street_elevation.py   (no command line: used by street_zone.py and the review)
"""
import json, os, re
import numpy as np

TILE = 256.0
ATLAS = os.environ.get("STREET_ATLAS", "")      # folder of t_bld_openings_b.color.png, _o.data.png, bld_openings.json
_cache = {}


def _atlas(folder):
    if folder not in _cache:
        from PIL import Image
        col = np.asarray(Image.open(os.path.join(folder, "t_bld_openings_b.color.png")).convert("RGB"))
        alpha = np.asarray(Image.open(os.path.join(folder, "t_bld_openings_o.data.png")).convert("L"))
        index = json.load(open(os.path.join(folder, "bld_openings.json")))["modules"] \
            if os.path.exists(os.path.join(folder, "bld_openings.json")) else None
        _cache[folder] = (col, alpha, index)
    return _cache[folder]


def _tile_list(lv):
    """The building tiles of a level: [(DAE path, position)] from its items.level.json (the optimizer of a released
    level merges the 256 m tiles into larger ones with other names), else the 256 m grid of buildings_mesh."""
    if ("tiles", lv) not in _cache:
        out = []
        items = os.path.join(lv, "main", "MissionGroup", "buildings", "items.level.json")
        if os.path.exists(items):
            for line in open(items):
                o = json.loads(line) if line.strip() else {}
                sn = o.get("shapeName", "")
                if o.get("class") == "TSStatic" and "/bld_" in sn:
                    rel = re.sub(r"^/?levels/[^/]+/", "", sn)
                    out.append((os.path.join(lv, rel), np.asarray(o.get("position", (0, 0, 0)), float)))
        else:
            for p in sorted(os.listdir(os.path.join(lv, "art", "shapes", "buildings"))):
                m = re.match(r"bld_([+-]\d+)_([+-]\d+)\.dae$", p)
                if m:
                    tx, ty = int(m.group(1)), int(m.group(2))
                    out.append((os.path.join(lv, "art", "shapes", "buildings", p),
                                np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])))
        _cache[("tiles", lv)] = out
    return _cache[("tiles", lv)]


def _tiles_of(f, lv, reach=800.0):
    """The building tiles (DAE paths and their positions) whose extent holds the facade."""
    import render3d
    pts = np.array([f.o + u * f.a for u in (f.u0, f.u1)])
    out = []
    for path, pos in _tile_list(lv):
        if np.hypot(*(pts.mean(0)[:2] - pos[:2])) > reach or not os.path.exists(path):
            continue
        if ("box", path) not in _cache:
            parts = _cache.get(path) or render3d._read_dae_parts(path)
            V = np.concatenate([t.reshape(-1, 3) for _, t, _, _ in parts]) + pos
            _cache[("box", path)] = (V.min(0), V.max(0))
        lo, hi = _cache[("box", path)]
        if ((pts[:, :2] >= lo[:2] - 2.0) & (pts[:, :2] <= hi[:2] + 2.0)).all(1).any():
            out.append((path, pos))
    return out


def _parts(path):
    if path not in _cache:
        import render3d
        _cache[path] = render3d._read_dae_parts(path)
    return _cache[path]


class Canvas:
    """An elevation image: pixel (row, col) is u = u0 + (col + 0.5) res, z = z1 - (row + 0.5) res."""

    def __init__(self, f, res=0.02, bg=(40, 40, 40)):
        self.f, self.res = f, res
        self.u0, self.z1 = f.u0, f.z1
        self.W = int(np.ceil((f.u1 - f.u0) / res))
        self.H = int(np.ceil((f.z1 - f.z0) / res))
        self.img = np.zeros((self.H, self.W, 3), np.float32)
        self.img[:] = np.asarray(bg, np.float32)

    def px(self, u, z):
        return (np.asarray(u) - self.u0) / self.res - 0.5, (self.z1 - np.asarray(z)) / self.res - 0.5

    def polygon(self, F, rgb):
        """Fill the facade polygon (shapely, in u, z) with a colour."""
        import cv2
        mask = np.zeros((self.H, self.W), np.uint8)
        for g in getattr(F, "geoms", [F]):
            if g.is_empty:
                continue
            x, y = self.px(*np.asarray(g.exterior.coords).T)
            cv2.fillPoly(mask, [np.round(np.c_[x, y] * 8).astype(np.int32)], 1, shift=3)
            for r in g.interiors:
                x, y = self.px(*np.asarray(r.coords).T)
                cv2.fillPoly(mask, [np.round(np.c_[x, y] * 8).astype(np.int32)], 0, shift=3)
        self.img[mask > 0] = np.asarray(rgb, np.float32)
        return mask

    def textured_tri(self, uz, uv, tex, alpha=None, tint=None):
        """A triangle with corners uz (3, 2) in metres and uv (3, 2) texture coordinates (t up the image)."""
        import cv2
        th, tw = tex.shape[:2]
        x, y = self.px(uz[:, 0], uz[:, 1])
        c0, c1 = int(max(0, np.floor(x.min()))), int(min(self.W, np.ceil(x.max()) + 1))
        r0, r1 = int(max(0, np.floor(y.min()))), int(min(self.H, np.ceil(y.max()) + 1))
        if c1 <= c0 or r1 <= r0:
            return
        # affine map pixel -> texture pixel
        A = np.c_[x, y, np.ones(3)]
        tx = uv[:, 0] * tw - 0.5
        ty = (1.0 - uv[:, 1]) * th - 0.5
        try:
            mx = np.linalg.solve(A, tx)
            my = np.linalg.solve(A, ty)
        except np.linalg.LinAlgError:
            return
        yy, xx = np.mgrid[r0:r1, c0:c1].astype(np.float32)
        # inside the triangle (barycentric)
        T = np.array([[x[0] - x[2], x[1] - x[2]], [y[0] - y[2], y[1] - y[2]]])
        try:
            Ti = np.linalg.inv(T)
        except np.linalg.LinAlgError:
            return
        dx, dy = xx - x[2], yy - y[2]
        l1 = Ti[0, 0] * dx + Ti[0, 1] * dy
        l2 = Ti[1, 0] * dx + Ti[1, 1] * dy
        inside = (l1 >= -1e-3) & (l2 >= -1e-3) & (l1 + l2 <= 1 + 1e-3)
        if not inside.any():
            return
        mapx = (mx[0] * xx + mx[1] * yy + mx[2]).astype(np.float32)
        mapy = (my[0] * xx + my[1] * yy + my[2]).astype(np.float32)
        col = cv2.remap(tex, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
        a = np.ones(inside.shape, np.float32) if alpha is None else \
            cv2.remap(alpha, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).astype(np.float32) / 255.0
        if tint is not None:
            col = col * np.asarray(tint, np.float32)[None, None]
        a = np.where(inside, np.clip((a - 0.35) / 0.3, 0, 1), 0.0)[..., None]
        sub = self.img[r0:r1, c0:c1]
        self.img[r0:r1, c0:c1] = sub * (1 - a) + col * a

    def flat_tri(self, uz, rgb):
        import cv2
        x, y = self.px(uz[:, 0], uz[:, 1])
        mask = np.zeros((self.H, self.W), np.uint8)
        cv2.fillPoly(mask, [np.round(np.c_[x, y] * 8).astype(np.int32)], 1, shift=3)
        self.img[mask > 0] = np.asarray(rgb, np.float32)

    def image(self):
        return np.clip(self.img, 0, 255).astype(np.uint8)


def _facade_frame(f, P):
    """(u, z, d) of points P (..., 3): along the wall, up, out from the plane."""
    rel = P - f.o
    return rel @ f.a, P[..., 2], rel @ f.n


def level(f, lv, atlas_dir=None, res=0.02, depth=(-0.05, 2.5)):
    """The facade as the built level lv draws it (None if no tile of the level holds it)."""
    atlas_dir = atlas_dir or ATLAS or os.path.join(lv, "art", "shapes", "buildings")
    col, alpha, _ = _atlas(atlas_dir)
    cv = Canvas(f, res)
    wall = []
    items = []                                          # (distance, kind, uz, uv, rgb)
    for path, pos in _tiles_of(f, lv):
        for mat, tris, uvs, cols in _parts(path):
            T = tris.astype(np.float64) + pos
            u, z, d = _facade_frame(f, T)
            # the triangles flat on (or parallel to) the facade, within its extent
            e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
            nn = np.cross(e1, e2)
            nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
            par = np.abs(nn @ f.n) > 0.9
            inside = (u.min(1) > f.u0 - 0.3) & (u.max(1) < f.u1 + 0.3) & (z.min(1) > f.z0 - 0.5) & (z.max(1) < f.z1 + 0.5)
            near = (d.min(1) > depth[0]) & (d.max(1) < depth[1])
            sel = np.nonzero(par & inside & near)[0]
            for i in sel:
                uz = np.c_[u[i], z[i]]
                dist = float(d[i].mean())
                if "openings" in mat:
                    # a built level's texture coordinates of the atlas lie whole tiles away from it (the texture
                    # repeats): back into it by the triangle's centre
                    uv = uvs[i] - np.floor(uvs[i].mean(0)) if uvs is not None else None
                    items.append((dist, "atlas", uz, uv, None))
                elif "plaster" in mat or "stone" in mat:
                    if abs(dist) < 0.05:
                        wall.append(cols[i].mean(0) if cols is not None else np.array([0.85, 0.82, 0.76]))
                    else:
                        items.append((dist, "flat", uz, None, (cols[i].mean(0) if cols is not None else
                                                               np.array([0.85, 0.82, 0.76])) * 255 * 0.92))
                elif "plinth" in mat:
                    items.append((dist, "flat", uz, None, (cols[i].mean(0) * 255 if cols is not None else
                                                           np.array([150, 148, 140]))))
    tone = np.median(np.array(wall), 0) * 255 if wall else np.array([200, 196, 186])
    cv.polygon(f.F, tone * 0.92)
    for dist, kind, uz, uv, rgb in sorted(items, key=lambda t: t[0]):
        if kind == "atlas" and uv is not None:
            cv.textured_tri(uz, uv, col, alpha)
        elif kind == "flat":
            cv.flat_tri(uz, rgb)
    return cv.image(), tone


def layout(f, openings, tone, atlas_dir, res=0.02):
    """A new layout drawn the same way: openings [(module, u centre, z bottom, width or None, height or None)]."""
    col, alpha, index = _atlas(atlas_dir)
    cv = Canvas(f, res)
    cv.polygon(f.F, np.asarray(tone, float) * 0.92)
    for name, uc, zb, w, h in openings:
        m = index[name]
        w = w or m["w"]
        h = h or m["h"]
        u0, v0, u1, v1 = m["uv"]
        q = np.array([[uc - w / 2, zb], [uc + w / 2, zb], [uc + w / 2, zb + h], [uc - w / 2, zb + h]])
        t = np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]])
        cv.textured_tri(q[[0, 1, 2]], t[[0, 1, 2]], col, alpha)
        cv.textured_tri(q[[0, 2, 3]], t[[0, 2, 3]], col, alpha)
    return cv.image()


def emitted(f, em, tone, atlas_dir, res=0.02, depth=(-0.05, 2.5)):
    """The facade f with the openings, balconies and plinth a facades.Emitter collected (a layout of facades.py
    before it becomes a mesh), drawn the same way."""
    col, alpha, _ = _atlas(atlas_dir)
    cv = Canvas(f, res)
    cv.polygon(f.F, np.asarray(tone, float) * 0.92)
    items = []
    for quads, uvs in ((em.V, em.UV), (em.LV, em.LUV)):
        for V, T in zip(quads, uvs):
            for t, uv in zip(np.asarray(V), np.asarray(T)):
                u, z, d = _facade_frame(f, t)
                if d.min() > depth[0] and d.max() < depth[1] and u.max() > f.u0 and u.min() < f.u1:
                    items.append((float(d.mean()), "atlas", np.c_[u, z], uv, None))
    for V, C in zip(em.PV, em.PC):
        for t in np.asarray(V):
            u, z, d = _facade_frame(f, t)
            if d.min() > depth[0] and d.max() < depth[1] and u.max() > f.u0 and u.min() < f.u1:
                items.append((float(d.mean()), "flat", np.c_[u, z], None, np.asarray(C) * 255))
    for V, C in zip(em.BV, em.BC):
        for t in np.asarray(V):
            u, z, d = _facade_frame(f, t)
            nn = np.cross(t[1] - t[0], t[2] - t[0])
            if abs(nn @ f.n) < 0.9 * np.linalg.norm(nn):
                continue
            if d.min() > depth[0] and d.max() < depth[1] and u.max() > f.u0 and u.min() < f.u1:
                items.append((float(d.mean()), "flat", np.c_[u, z], None, np.asarray(C) * 255 * 0.85))
    for dist, kind, uz, uv, rgb in sorted(items, key=lambda t: t[0]):
        if kind == "atlas":
            cv.textured_tri(uz, uv, col, alpha)
        else:
            cv.flat_tri(uz, rgb)
    return cv.image()
