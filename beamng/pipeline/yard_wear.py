"""v3.1 visual review: the big yards and car parks with wear, patches and edges (finish step after road_wear).

The cadastral 'other hard surface' (altro_rivestimento_duro: car parks, forecourts, industrial yards, squares) is the
mesh material mp_hard_asphalt, one tile of Italy's asphalt from edge to edge. road_wear.py dresses the carriageways
only (tracks, patches, dusty edges along the AI roads), so in the visual review of v3.1 the large yards were the
flattest things on the map: plains of one even grey with no edge, no patch, nothing (G5: 0175, 0232, 0233, 0235,
0241, 0257, 0290, 0294, 0355, 0358, 0382, 0385, 0386, 0412, 0531, 0544). On every yard of at least MIN_AREA m2
(the faces of mp_hard_asphalt joined by their corners), with the overlay materials road_wear.py has written:
- the light and dark blotches of Italy (mp_wear_variation) over the whole yard: its own faces lifted, the texture
  laid along the yard's long axis (VAR_ACROSS m across, VAR_ALONG along: the scale it has on a road);
- a dusty edge (mp_wear_edge, road_wear.edge_bands) where the yard ends against the ground, a kerb or a wall (not
  where it goes on flush into a road or another paved surface);
- patched asphalt (mp_wear_patch with its sealed seam, road_wear.patches), one about every PATCH_EVERY m2, and
  cracked stretches (mp_wear_cracks), one about every CRACK_EVERY m2, each PAD m inside the yard and only where the
  yard under it is whole and even (road_wear.top_height: less than 0.4 m of rise).
Every layer at its road_wear.LAYER height over the faces (road_wear.clear_of), one mesh per TILE m tile in
MissionGroup/roads/markings, no collision. Seeded (SEED): the same level gives the same yards.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish yard_wear
"""
import json, os, re, shutil, tempfile, time, zipfile
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import bng
import optimize_level
import road_wear as rw
from config import LEVEL_NAME
from markings_net import read_items, shape_tris, up_faces
from road_mesh import TriSurface

YARD = "mp_hard_asphalt"
MIN_AREA = 600.0             # m2: smaller yards (drives, forecourts of one house) stay as they are
VAR_ACROSS, VAR_ALONG = 6.0, 112.0    # m per repeat of Italy's blotches (road_wear.LAYER: 112 m on a 6 m road)
PATCH_EVERY = 900.0          # m2 of yard per patch, on average
CRACK_EVERY = 1500.0         # m2 of yard per cracked stretch, on average
PATCH_L, PATCH_W = (2.0, 7.0), (1.5, 4.0)    # m, along and across a patch
CRACK_L, CRACK_W = (6.0, 18.0), (2.5, 4.0)   # m, a cracked stretch
AXIS_JITTER = 3.0            # degrees off the yard's axes
PAD = 1.0                    # m: a patch or a crack this far inside the yard at least
SEED = 4141
TILE = 512.0
SHAPE = re.compile(r"art/shapes/roads/yard_wear_[-+]\d+_[-+]\d+\.dae$")
NEEDS = ("mp_wear_variation", "mp_wear_edge", "mp_wear_patch", "mp_wear_joint", "mp_wear_cracks")


def yards(A):
    """[(face indices, area m2)] of the yards: the faces A (k, 3, 3) joined where they share a corner."""
    V = A.reshape(-1, 3)
    key = np.round(V[:, :2] * 200).astype(np.int64)                    # 5 mm (road_wear.outer_edges)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    tri = vid.reshape(-1, 3)
    nt, nv = len(tri), int(vid.max()) + 1
    r = np.repeat(np.arange(nt), 3)
    g = coo_matrix((np.ones(3 * nt, np.int8), (r, tri.ravel() + nt)), shape=(nt + nv, nt + nv))
    _, lab = connected_components(g, directed=False)
    lab = lab[:nt]
    a = 0.5 * np.linalg.norm(np.cross(A[:, 1] - A[:, 0], A[:, 2] - A[:, 0]), axis=1)
    order = np.argsort(lab, kind="stable")
    cuts = np.flatnonzero(np.diff(lab[order])) + 1
    out = []
    for idx in np.split(order, cuts):
        area = float(a[idx].sum())
        if area >= MIN_AREA:
            out.append((idx, area))
    return out


def long_axis(P):
    """Unit vector (2,) of the long axis of the points P (k, 2)."""
    c = P - P.mean(0)
    w, v = np.linalg.eigh(c.T @ c)
    return v[:, np.argmax(w)]


def variation(t, axis):
    """The faces t (k, 3, 3) lifted to the blotches' height, with uvs along `axis`."""
    lift = rw.LAYER["mp_wear_variation"][0]
    n = np.array([-axis[1], axis[0]])
    xy = t[..., :2]
    uv = np.stack([xy @ n / VAR_ACROSS, xy @ axis / VAR_ALONG], -1)
    uv -= np.floor(uv.reshape(-1, 2).min(0))
    t = t.copy()
    t[..., 2] += lift
    return t, uv


def spots(t, area, every, L, W, rng, Sy, axis):
    """[(centre (2,), unit tangent (2,), length, width)] of rectangles on the yard faces t: about area / every of
    them, along or across the yard's long axis (as the yard was laid and dug up, a few degrees off), PAD m inside
    the yard (all corners and the middle on it, less than 0.4 m of rise)."""
    k = rng.poisson(area / every)
    if not k:
        return []
    a = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    out = []
    for _ in range(4 * k):
        if len(out) >= k:
            break
        f = rng.choice(len(t), p=a / a.sum())
        b = rng.dirichlet((1, 1, 1))
        c = (b[:, None] * t[f, :, :2]).sum(0)
        ang = np.arctan2(axis[1], axis[0]) + rng.integers(2) * np.pi / 2 + np.radians(rng.normal(0, AXIS_JITTER))
        tt = np.array([np.cos(ang), np.sin(ang)])
        nn = np.array([-tt[1], tt[0]])
        ln, wd = rng.uniform(*L), rng.uniform(*W)
        Q = np.array([c + tt * s * (ln / 2 + PAD) + nn * u * (wd / 2 + PAD) for s in (-1, 0, 1) for u in (-1, 0, 1)])
        z = rw.top_height(Sy, Q[[4] + [i for i in range(9) if i != 4]])
        if np.isfinite(z).all() and np.ptp(z) < 0.4:
            out.append((c, tt, ln, wd))
    return out


def cracks(sp, Sy):
    """[(material, triangles, uvs)] of cracked stretches at the rectangles sp (as road_wear.patches lays a patch)."""
    out = []
    lift, per_m = rw.LAYER["mp_wear_cracks"]
    for c, t, L, W in sp:
        n = np.array([-t[1], t[0]])
        k = max(int(np.ceil(L / 0.5)), 2)
        f = np.linspace(-L / 2, L / 2, k + 1)
        C = c[None, :] + t[None, :] * f[:, None]
        z0 = rw.top_height(Sy, np.array([c]))[0]
        zc = Sy.height(C[:, 0], C[:, 1], "near", zhint=np.full(len(C), z0))
        zc = np.where(np.isfinite(zc), zc, z0)
        tr, uv, _ = rw.strip(C, np.full(len(C), W), zc, np.repeat(n[None, :], len(C), 0), Sy,
                             np.ones(len(C), bool), lift, per_m * W, f - f[0], 2)
        if len(tr):
            out.append(("mp_wear_cracks", tr, uv))
    return out


class _Patches:
    """The rectangles in the form road_wear.patches reads (road_age.Survey.patches)."""
    def __init__(self, sp):
        self.patches = [{"xy": c, "t": t, "along": L, "across": W} for c, t, L, W in sp]


def yard_wear_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    have = json.loads(zi.read(mats_name))
    if any(m not in have for m in NEEDS):
        raise SystemExit("yard_wear: run road_wear first (no overlay materials in the level)")
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    if YARD not in surf:
        return 0
    import markings_net
    Y = up_faces(surf[YARD])
    Sall = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in markings_net.CARRIAGE_MATS]))
    flush = [up_faces(t) for m, t in surf.items() if m != YARD and (m in rw.PAVED or m in rw.ASPHALT)]
    Sp = TriSurface(np.concatenate(flush) if flush else np.zeros((0, 3, 3)))
    rng = np.random.default_rng(SEED)
    stats = {"yards": 0, "yard_ha": 0.0, "variation_faces": 0, "edge_m": 0.0, "patches": 0, "cracks": 0}
    pieces = {}

    def add(mat, t, uv):
        c = t.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(q) for q in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            pieces.setdefault(key, {}).setdefault(mat, []).append((t[m], uv[m]))
    for idx, area in yards(Y):
        t = Y[idx]
        stats["yards"] += 1
        stats["yard_ha"] += area / 1e4
        axis = long_axis(t[..., :2].reshape(-1, 2))
        tv, uv = variation(t, axis)
        add("mp_wear_variation", tv, uv)
        stats["variation_faces"] += len(tv)
        Syard = TriSurface(t)
        te, ue = rw.edge_bands(t, Syard, Sall, Sp, stats)
        if len(te):
            add("mp_wear_edge", te, ue)
        sp = spots(t, area, PATCH_EVERY, PATCH_L, PATCH_W, rng, Syard, axis)
        for mat, tr, uv in rw.patches(_Patches(sp), Syard, {}):
            add(mat, tr, uv)
        stats["patches"] += len(sp)
        sc = spots(t, area, CRACK_EVERY, CRACK_L, CRACK_W, rng, Syard, axis)
        for mat, tr, uv in cracks(sc, Syard):
            add(mat, tr, uv)
        stats["cracks"] += len(sc)
    print("yard_wear: %d yards laid (%.0f s)" % (stats["yards"], time.time() - t0), flush=True)
    builders = {}
    for key, by_mat in pieces.items():                    # the layers from the lowest up (road_wear_step)
        mb = builders[key] = bng.MeshBuilder()
        for mat in sorted(by_mat, key=lambda m: rw.LAYER[m][0]):
            for t, uv in by_mat[mat]:
                V = t.reshape(-1, 3)
                mb.add(mat, V, uvs=uv.reshape(-1, 2), normals=np.repeat([[0, 0, 1.0]], len(V), 0))
    tmp = tempfile.mkdtemp(prefix="magliaso_yard_")
    try:
        new_files, objs = {}, []
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/yard_wear_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(f, name=f"yard_wear_{tx}_{ty}", origin=origin)
            text = open(f, encoding="utf-8").read()
            out, _ = optimize_level.optimize_dae([(text, np.zeros(3))], rel.split("art/shapes/", 1)[1])
            new_files[f"{lv}/{rel}"] = (out or text).encode("utf-8")
            objs.append(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False))
        mk_items = f"{lv}/main/MissionGroup/roads/markings/items.level.json"
        mk = [o for o in read_items(zi, mk_items) if not SHAPE.search(o.get("shapeName", ""))]
        parent = next((o["__parent"] for o in mk if "__parent" in o), "markings")
        for o in objs:
            o["__parent"] = parent
        new_files[mk_items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in mk + objs) + "\n").encode("utf-8")
        with zi.writer() as zo:
            for i in zi.infolist():
                if i.filename in new_files or SHAPE.search(i.filename):
                    continue
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
            for n, data in sorted(new_files.items()):
                zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats.update(meshes=len(builders), seconds=round(time.time() - t0), yard_ha=round(stats["yard_ha"], 1))
    stats["edge_km"] = round(stats.pop("edge_m") / 1000, 1)
    print("yard_wear:", stats, flush=True)
    if report:
        json.dump(stats, open(report, "w"), indent=1)
    return 0
