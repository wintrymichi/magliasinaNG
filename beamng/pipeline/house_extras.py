"""Flower boxes and woodpiles (v3.0): the houses lived in, on the built level.

The houses of the level have their windows, shutters, doors and balconies drawn on the façades (bld_textures.py
openings atlas, buildings_mesh.py) and, since v2.8, gutters, downpipes, aerials, dishes and solar panels
(house_details): seen from the road a village still looked unlived in, with not a geranium at a window. Here,
by rules, on the meshes of the level:
- flower boxes: under FLOWER_SHARE of the windows with shutters, ROLLER_SHARE of those with roller shutters and
  MODERN_SHARE of the modern ones, and along BALCONY_SHARE of the balcony railings; a box (terracotta, painted
  wood or white) on the sill as wide as the glass, the plants in it (leaves and flowers, geraniums red, pink or
  white: drawn here, cut out with alpha) leaning out of it. Which window: from the openings of the façade
  (their module in the atlas, from the texture coordinates of each quad), the outside of the wall where the
  roof is not, the same every build (a hash of the place);
- woodpiles: against WOODPILE_SHARE of the walls of the stone houses (the rustici) that stand on the ground and
  are WOOD_MIN m long or more, under the eaves: logs stacked WOOD_DEPTH m deep, their cut ends drawn on the
  front, not on a carriageway.
Meshes in MissionGroup/buildings/extras (DETAIL_TILE m tiles drawn up to NEAR_DRAW m, as the house details), no
collision for the flowers, collision for the woodpiles; their textures drawn here in art/shapes/buildings/extras.
Everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish house_extras
"""
import hashlib, json, math, os, re, tempfile, time, shutil, zipfile
import numpy as np
from PIL import Image
import bng
import optimize_level
import bld_textures as bt
import lamps as pl
import road_mesh
from buildings_mesh import share, quad, DETAIL_TILE, NEAR_DRAW
from config import LEVEL_NAME

FLOWER_SHARE, ROLLER_SHARE, MODERN_SHARE, CLOSED_SHARE, BALCONY_SHARE = 0.22, 0.10, 0.03, 0.04, 0.12
BOX_H, BOX_D, BOX_OUT = 0.17, 0.20, 0.02     # m: height, depth of a box; gap from the wall
PLANT_H = 0.34                                # m of plants over the box
WOODPILE_SHARE, WOOD_MIN, WOOD_DEPTH = 0.6, 2.5, 0.42
WOOD_H = (1.0, 1.7)
OUT_TEST = 2.5                                # m from the wall: the side without a roof there is the outside
SHAPE = re.compile(r"art/shapes/buildings/extras/house_extras_[-+]\d+_[-+]\d+\.dae$")
D = "art/shapes/buildings/extras"
# colours of the boxes as seen (sRGB); the material takes them linear (baseColorFactor): in the first v3 build
# they were given as sRGB and the white boxes showed as glowing white rectangles
BOXES = (("mp_fbox_terracotta", (0.56, 0.30, 0.20)), ("mp_fbox_wood", (0.27, 0.33, 0.24)),
         ("mp_fbox_white", (0.72, 0.71, 0.68)))
FLOWERS = ((0.80, 0.10, 0.10), (0.92, 0.38, 0.62), (0.95, 0.95, 0.93), (0.70, 0.18, 0.55))   # rows of the plant texture


def _unit(key, salt):
    """A number in [0, 1) from the key, the same every build."""
    return int.from_bytes(hashlib.md5(f"{salt}:{key}".encode()).digest()[:4], "little") / 2 ** 32


def glass_width(name, W):
    """Width (m, at the module's own size W) of the glass of a window module: where the box goes."""
    if name.startswith("win_legno_boards") or name.startswith("win_verde_scuro_boards"):
        return 0.8
    if name.startswith("win_"):
        return 0.9 if name.endswith("_granite") else 1.0
    if name.startswith("roller_") or name.startswith("bal_roller"):
        return 1.2
    if name.startswith("modern_"):
        return 1.4 if name == "modern_tall" else 1.6
    if name.startswith("railing_"):
        return 0.85 * W
    return None


def kind_share(name):
    if name.startswith("railing_"):
        return BALCONY_SHARE
    if name.startswith("win_"):
        return CLOSED_SHARE if "closed" in name else FLOWER_SHARE
    if name.startswith("roller_"):
        return 0.0 if name.endswith("_down") else ROLLER_SHARE
    if name.startswith("modern_") and name != "modern_tall":
        return MODERN_SHARE
    return 0.0


def atlas_index():
    """name -> (u0, v0, u1, v1, w) of the openings atlas, as bld_textures.openings_atlas lays it out."""
    rng = np.random.default_rng(bt.SEED)
    mods = bt.modules(rng)
    rects = bt.pack(mods)
    AW, AH = bt.ATLAS
    return {k: (x / AW, 1 - (y + h) / AH, (x + w) / AW, 1 - y / AH, mods[k].w) for k, (x, y, w, h) in rects.items()}


def textures(dst):
    """Plants (RGBA, cut out: rows of the four flower colours) and the woodpile (log ends; bark)."""
    rng = np.random.default_rng(71)
    w, h = 512, 512
    rows = len(FLOWERS)
    img = np.zeros((h, w, 4), np.float32)
    rh = h // rows
    Y, X = np.mgrid[0:rh, 0:w].astype(np.float32)
    for r, fc in enumerate(FLOWERS):
        # leaves: a mound of round leaf clusters, denser low down (the texture wraps across u)
        leaf = np.zeros((rh, w), bool)
        for _ in range(170):
            cx, cy, rr = rng.uniform(0, w), rh - rng.uniform(0, 0.75) ** 1.5 * rh, rng.uniform(9, 22)
            for ox in (-w, 0, w):
                leaf |= (X - cx - ox) ** 2 + (Y - cy) ** 2 < rr ** 2
        leaf &= bt.noise(rh, w, 1.5, rng) > -1.3
        shade = 0.75 + 0.3 * bt.noise(rh, w, 2.5, rng) + 0.25 * (Y / rh)
        col = np.array([0.15, 0.29, 0.10])[None, None] * shade[..., None]
        # flowers: heads of small florets over the top of the leaves
        f = np.zeros((rh, w), bool)
        for _ in range(55):
            cx, cy = rng.uniform(0, w), rng.uniform(0.12, 0.55) * rh
            for _k in range(9):
                fx, fy, fr = cx + rng.normal(0, 6), cy + rng.normal(0, 5), rng.uniform(2.5, 4.5)
                for ox in (-w, 0, w):
                    f |= (X - fx - ox) ** 2 + (Y - fy) ** 2 < fr ** 2
        fcol = np.asarray(fc)[None, None] * (0.8 + 0.3 * rng.uniform(size=(rh, w, 1)))
        col = np.where(f[..., None], fcol, col)
        y0 = r * rh
        img[y0:y0 + rh, :, :3] = col
        img[y0:y0 + rh, :, 3] = (leaf | f).astype(np.float32)
    Image.fromarray(np.dstack([bt.to8(img[..., :3]), bt.to8(img[..., 3])])).save(os.path.join(dst, "t_plants_b.color.png"))
    # log ends: rows of logs (tileable), light wood with rings and a dark bark rim, dark gaps between them
    n = 512
    Y, X = np.mgrid[0:n, 0:n].astype(np.float32)
    col = np.zeros((n, n, 3), np.float32) + 0.08
    rmean = 22.0
    nrow = int(n / (2 * rmean * 0.88))
    for i in range(nrow):
        cy = (i + 0.5) * n / nrow
        ncol = int(n / (2 * rmean))
        shift = rng.uniform(0, n)
        for j in range(ncol):
            cx = (j + 0.5) * n / ncol + shift + rng.normal(0, 3)
            r = rmean * rng.uniform(0.75, 1.05)
            yy = cy + rng.normal(0, 2.5)
            base = np.array([0.66, 0.52, 0.36]) * rng.uniform(0.75, 1.1)
            for ox in (-n, 0, n):
                for oy in (-n, 0, n):
                    d = np.hypot(X - (cx % n) - ox, Y - yy - oy)
                    m = d < r
                    if not m.any():
                        continue
                    rings = 0.9 + 0.1 * np.sin(d[m] / r * 9.0 * np.pi)
                    rim = np.clip((r - d[m]) / 3.5, 0, 1)
                    col[m] = base[None] * (rings * (0.5 + 0.5 * rim))[:, None] + np.array([0.18, 0.13, 0.09]) * (1 - rim)[:, None]
    Image.fromarray(bt.to8(col)).save(os.path.join(dst, "t_logs_b.color.png"))
    bark = np.array([0.30, 0.24, 0.18])[None, None] * (0.75 + 0.3 * bt.aniso_noise(n, n, 1.5, 30, rng))[..., None]
    Image.fromarray(bt.to8(bark)).save(os.path.join(dst, "t_bark_b.color.png"))


def materials():
    t = f"/levels/{LEVEL_NAME}/{D}"
    lin = lambda c: [float(((v + 0.055) / 1.055) ** 2.4) for v in c]
    out = [bng.material(m, base_color=lin(c) + [1], roughness=0.8, double_sided=True) for m, c in BOXES]   # either winding
    out.append(bng.material("mp_plants", f"{t}/t_plants_b.color.png", roughness=0.9, alpha_test=60, double_sided=True))
    out.append(bng.material("mp_logs", f"{t}/t_logs_b.color.png", roughness=0.9, ground_type="WOOD", double_sided=True))
    out.append(bng.material("mp_bark", f"{t}/t_bark_b.color.png", roughness=0.95, ground_type="WOOD", double_sided=True))
    return out


def outward(roof, c, n):
    """+1 if n points out of the building at the wall point c (no roof OUT_TEST m that way, a roof the other way),
    -1 the other way round, 0 where it cannot tell."""
    a = np.isfinite(roof.height([c[0] + n[0] * OUT_TEST], [c[1] + n[1] * OUT_TEST], "high")[0])
    b = np.isfinite(roof.height([c[0] - n[0] * OUT_TEST], [c[1] - n[1] * OUT_TEST], "high")[0])
    return 1 if b and not a else (-1 if a and not b else 0)


def box_tris(c, u, n, half_w, depth, z0, z1):
    """A box on the wall, open at the top and at the back (against the wall): c the middle of its back edge at
    the wall, u along the wall, n out."""
    P = [c - u * half_w, c + u * half_w, c + u * half_w + n * depth, c - u * half_w + n * depth]
    tris = []
    for a, b in zip(P[1:], P[2:] + P[:1]):
        tris += quad(np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z1])
    tris += quad(*[np.r_[p, z0] for p in P])
    return tris


def flower_box(add, key, c, u, n, half_w, zb, rng_u):
    """The box and its plants: c the middle of the sill at the wall, zb the top of the sill."""
    m = BOXES[int(rng_u[0] * len(BOXES))][0]
    cb = c + n * BOX_OUT
    z0, z1 = zb, zb + BOX_H
    for t in box_tris(cb, u, n, half_w, BOX_D, z0, z1):
        add(m, t, None)
    # the soil
    add("mp_bark", np.array([np.r_[cb - u * half_w + n * 0.02, z1 - 0.03], np.r_[cb + u * half_w + n * 0.02, z1 - 0.03],
                             np.r_[cb + u * half_w + n * (BOX_D - 0.02), z1 - 0.03]]), None)
    row = int(rng_u[1] * len(FLOWERS))
    v0, v1 = 1 - (row + 1) / len(FLOWERS), 1 - row / len(FLOWERS)
    ur = half_w * 2 / 1.6                                      # the texture over 1.6 m (as tall as its row)
    u0 = rng_u[2] * 3
    for off, lean in ((0.07, 0.10), (0.14, 0.22)):            # two rows of plants, the front one leaning out
        b0 = cb + n * off
        A, B = np.r_[b0 - u * (half_w + 0.03), z1 - 0.06], np.r_[b0 + u * (half_w + 0.03), z1 - 0.06]
        top = n * lean
        C, Dd = np.r_[b0 + u * (half_w + 0.05) + top, z1 + PLANT_H], np.r_[b0 - u * (half_w + 0.05) + top, z1 + PLANT_H]
        add("mp_plants", np.array([A, B, C]), np.array([[u0, v0], [u0 + ur, v0], [u0 + ur, v1]]))
        add("mp_plants", np.array([A, C, Dd]), np.array([[u0, v0], [u0 + ur, v1], [u0, v1]]))


def woodpile(add, c, u, n, half_w, z, height):
    """Logs against the wall: c the middle of the pile's back at the wall, on the ground at z."""
    P = [c - u * half_w, c + u * half_w, c + u * half_w + n * WOOD_DEPTH, c - u * half_w + n * WOOD_DEPTH]
    z0, z1 = z - 0.05, z + height
    # front and the two ends: log ends; top: bark
    for a, b, mat in ((P[2], P[3], "mp_logs"), (P[1], P[2], "mp_logs"), (P[3], P[0], "mp_logs")):
        L = float(np.linalg.norm(b - a))
        T = quad(np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z1])
        uv = [np.array([[0, 0], [L, 0], [L, z1 - z0]]) / 0.9, np.array([[0, 0], [L, z1 - z0], [0, z1 - z0]]) / 0.9]
        for t, w in zip(T, uv):
            add(mat, t, w)
    T = quad(*[np.r_[p, z1] for p in P])
    for t in T:
        add("mp_bark", t, t[:, :2] / 1.2)


def house_extras_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    idx = atlas_index()
    names = list(idx)
    R = np.array([idx[k][:4] for k in names])
    import street_life
    site = street_life.Site(zi, lv)
    rep = {"windows": 0, "flower_boxes": 0, "balcony_boxes": 0, "woodpiles": 0, "unknown_side": 0}
    tiles = {}

    def add_to(key):
        def add(m, t, uv):
            k = (int(math.floor(t[:, 0].mean() / DETAIL_TILE)), int(math.floor(t[:, 1].mean() / DETAIL_TILE)))
            tiles.setdefault(k, {}).setdefault(m, []).append((np.asarray(t, float), None if uv is None else np.asarray(uv, float)))
        return add
    add = add_to(None)          # noqa
    for o in pl.read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or "/details/" in sn:
            continue
        V, N, T, C, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        pm = dict(parts)
        ops = [pm[m] for m in ("bld_openings", "bld_openings_lit") if m in pm]     # the lit windows too (v2.8)
        if not ops:
            continue
        roofs = [W[i[:, 0]].reshape(-1, 3, 3) for m, i in parts if m.startswith("bld_roof")]
        if not roofs:
            continue
        roof = road_mesh.TriSurface(np.concatenate(roofs))
        tri = np.concatenate([W[ix[:, 0]].reshape(-1, 3, 3) for ix in ops])
        uv = np.concatenate([T[ix[:, 2 if ix.shape[1] > 2 else 1]].reshape(-1, 3, 2) for ix in ops])
        for k in range(0, len(tri) - 1, 2):
            q = np.concatenate([tri[k], tri[k + 1]])
            zb, zt = q[:, 2].min(), q[:, 2].max()
            xy = q[:, :2]
            if zt - zb < 0.4:
                continue
            uc = uv[k:k + 2].reshape(-1, 2).mean(0) % 1.0
            j = np.flatnonzero((R[:, 0] <= uc[0]) & (uc[0] <= R[:, 2]) & (R[:, 1] <= uc[1]) & (uc[1] <= R[:, 3]))
            if not len(j):
                continue
            name = names[j[0]]
            p_share = kind_share(name)
            rep["windows"] += name.startswith(("win_", "roller_", "modern_"))
            if p_share <= 0:
                continue
            # the bottom edge of the quad: the two lowest corners
            low = q[np.argsort(q[:, 2])[:2]]
            a, b = low[0, :2], low[1, :2]
            if np.linalg.norm(b - a) < 0.3:
                # degenerate pair (the two low corners the same): take the extreme corners in plan
                d = np.linalg.norm(xy[:, None] - xy[None], axis=2)
                i1, i2 = np.unravel_index(np.argmax(d), d.shape)
                a, b = xy[i1], xy[i2]
            width = float(np.linalg.norm(b - a))
            if width < 0.4:
                continue
            c = (a + b) / 2
            key = f"{c[0]:.1f},{c[1]:.1f},{zb:.1f}"
            if not share(key, "flowers", p_share):
                continue
            u = (b - a) / width
            n = np.array([-u[1], u[0]])
            s = outward(roof, c, n)
            if s == 0:
                rep["unknown_side"] += 1
                continue
            n = n * s
            h = [_unit(key, s_) for s_ in ("box", "row", "u")]
            if name.startswith("railing_"):
                # boxes hung on the outside of the railing, below its top
                half = min(glass_width(name, idx[name][4]) * width / idx[name][4], 2.4) / 2
                flower_box(add, key, c, u, n, half, zt - BOX_H - 0.03, h)
                rep["balcony_boxes"] += 1
            else:
                if zb - float(site.ground([c[0]], [c[1]])[0]) < 0.5:     # a ground-floor window at the pavement: none
                    continue
                gw = glass_width(name, idx[name][4])
                half = min(gw * width / idx[name][4], 1.8) / 2 + 0.03
                flower_box(add, key, c, u, n, half, zb + 0.065, h)
                rep["flower_boxes"] += 1
        # woodpiles: the stone walls on the ground of a rustico
        if "bld_stone" in pm:
            ix = pm["bld_stone"]
            st = W[ix[:, 0]].reshape(-1, 3, 3)
            nrm = np.cross(st[:, 1] - st[:, 0], st[:, 2] - st[:, 0])
            vert = np.abs(nrm[:, 2]) < 0.1 * np.maximum(np.linalg.norm(nrm, axis=1), 1e-9)
            seen = set()
            for t in st[vert]:
                low = t[np.argsort(t[:, 2])[:2]]
                a, b = low[0, :2], low[1, :2]
                L = float(np.linalg.norm(b - a))
                if L < WOOD_MIN or abs(low[0, 2] - low[1, 2]) > 0.3:
                    continue
                c = (a + b) / 2
                key = f"{c[0]:.0f},{c[1]:.0f}"
                if key in seen or not share(key, "woodpile", WOODPILE_SHARE):
                    continue
                seen.add(key)
                u = (b - a) / L
                n = np.array([-u[1], u[0]])
                s = outward(roof, c, n)
                if s == 0:
                    continue
                n = n * s
                zg = float(site.ground([c[0]], [c[1]])[0])
                if abs(zg - low[:, 2].min()) > 0.6:
                    continue
                half = min(L * 0.35, 1.6)
                fp = np.array([c + n * (WOOD_DEPTH / 2 + 0.05) + u * f * half for f in (-1, 0, 1)])
                if site.on_carriageway(fp[:, 0], fp[:, 1]).any():
                    continue
                zs = site.ground(fp[:, 0], fp[:, 1])
                if zs.max() - zs.min() > 0.3:
                    continue
                hh = WOOD_H[0] + (WOOD_H[1] - WOOD_H[0]) * _unit(key, "wood_h")
                woodpile(add, c + n * 0.03, u, n, half, float(zs.min()), hh)
                rep["woodpiles"] += 1
    print("house extras: %s" % rep, flush=True)

    tmp = tempfile.mkdtemp(prefix="magliaso_extras_")
    try:
        new_files, items, ntri = {}, [], 0
        for (tx, ty), mats in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * DETAIL_TILE, (ty + 0.5) * DETAIL_TILE, 0.0])
            allv = []
            for m, lst in mats.items():
                # a building with NaN corners (zone ti_0_m1) gives NaN extras: leave those out
                lst = [(t, w) for t, w in lst if np.isfinite(t).all()]
                if not lst:
                    continue
                Tm = np.array([t for t, _ in lst])
                Vv = Tm.reshape(-1, 3)
                if all(w is None for _, w in lst):
                    UV = Vv[:, :2] + Vv[:, 2:3]
                else:
                    UV = np.concatenate([w if w is not None else t[:, :2] for t, w in lst]).reshape(-1, 2)
                mb.add(m, Vv, uvs=UV, normals=bng.flat_normals_soup(Vv))
                ntri += len(Tm)
                allv.append(Vv)
            if not allv:
                continue
            allv = np.concatenate(allv)
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / NEAR_DRAW)))
            rel = f"{D}/house_extras_{tx:+03d}_{ty:+03d}.dae"
            f = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(f, name="house_extras", origin=origin, detail=detail)
            new_files[f"{lv}/{rel}"] = open(f, "rb").read()
            ob = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True)
            ob["__parent"] = "extras"
            items.append(ob)
        textures(tmp)
        for name in ("t_plants_b.color.png", "t_logs_b.color.png", "t_bark_b.color.png"):
            new_files[f"{lv}/{D}/{name}"] = open(os.path.join(tmp, name), "rb").read()
        mf = os.path.join(tmp, "m.json")
        bng.write_materials(mf, materials())
        new_files[f"{lv}/{D}/extras.materials.json"] = open(mf, "rb").read()
        grp = f"{lv}/main/MissionGroup/buildings/items.level.json"
        gitems = [g for g in pl.read_items(zi, grp) if g.get("name") != "extras"]
        gitems.append({"name": "extras", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "buildings"})
        enc = lambda objs: ("\n".join(json.dumps(x, separators=(",", ":")) for x in objs) + "\n").encode("utf-8")
        new_files[grp] = enc(gitems)
        new_files[f"{lv}/main/MissionGroup/buildings/extras/items.level.json"] = enc(items)
        with zi.writer() as zo:
            for inf in zi.infolist():
                if inf.filename in new_files or SHAPE.search(inf.filename):
                    continue
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
            for name, data in sorted(new_files.items()):
                zo.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rep.update(tiles=len(tiles), triangles=ntri, seconds=round(time.time() - t0))
    print("written in %.0f s: %d tiles, %d triangles" % (time.time() - t0, len(tiles), ntri), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return 0
