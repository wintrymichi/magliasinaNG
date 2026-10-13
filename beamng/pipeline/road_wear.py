"""Wear of the asphalt: tyre tracks and dirty edges along the roads (v3.0), in the built level.

An asphalt road is never one even grey: where the wheels run, two bands per lane are darker and smoother
(the bitumen polished, oil and rubber), and along the edges, where nothing drives, dust, sand and leaves
gather in a lighter, browner band. Up to v2.8 the carriageways of the map were one texture from edge to
edge, the main reason they looked drawn rather than driven on.

Here, along the AI roads of the level (DecalRoad, their nodes with the width of the carriageway and the
lanes each way):
- tyre tracks: in every lane two tracks TRACK_W m wide, TRACK_GAP m apart about the middle of the lane, drawn
  together on one band (on a road narrower than NARROW m, one pair in the middle of the road: there cars
  drive in the middle);
- edges: a band EDGE_W m wide along each edge, EDGE_IN m in from it;
both as translucent strips (their own drawn textures: the opacity fades across the band and varies along
it, so no edge shows), LIFT m over the top faces of the paved carriageways of the level, never off them
(gravel and earth roads, bridges without a paved deck, the ends of a road beyond the mesh are left out).
One mesh per TILE m tile in MissionGroup/roads/markings, without collision; the textures in
art/shapes/roads. Everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish road_wear
"""
import json, os, re, shutil, tempfile, time, zipfile
import numpy as np
from PIL import Image
import bng
import optimize_level
from config import LEVEL_NAME
from bld_textures import aniso_noise, to8
from markings_net import read_items, shape_tris, up_faces, CARRIAGE_MATS
from road_mesh import TriSurface

TILE = 512.0
LIFT = 0.012                 # m over the road (the paint lies at 0.02)
TRACK_W = 0.75               # m, width of a tyre track
TRACK_GAP = 1.6              # m between the middles of the two tracks of a lane (a car's track width)
EDGE_W = 0.7
EDGE_IN = 0.35               # m from the edge to the middle of the edge band
NARROW = 5.2                 # m: on narrower carriageways one pair of tracks in the middle
MIN_W = 2.6                  # m: no wear on AI roads narrower than this (paths, ramps)
PAIR_W = TRACK_GAP + TRACK_W + 0.35   # m, the band that carries the two tracks of a lane
STEP = 2.0                   # m between the vertices of a strip
V_TILE = 16.0                # m of road per repeat of the textures along them
SHAPE = re.compile(r"art/shapes/roads/road_wear_[-+]\d+_[-+]\d+\.dae$")
TEX = ("t_wear_track", "t_wear_edge")


def textures(dst, n=(64, 512)):
    """The two strip textures (RGBA: colour and opacity; u across the band, v along it over V_TILE m)."""
    rng = np.random.default_rng(41)
    w, h = n
    u = (np.arange(w) + 0.5) / w
    c, sig = TRACK_GAP / 2 / PAIR_W, 0.26 * TRACK_W / PAIR_W
    across = np.exp(-((u - 0.5 + c) / sig) ** 2) + np.exp(-((u - 0.5 - c) / sig) ** 2)   # two soft tracks
    px = h / V_TILE                                                   # pixels per metre along the road
    along = aniso_noise(h, w, 2.5 * px, 3, rng)                       # metres-long patches, never dashes
    fine = aniso_noise(h, w, 0.15 * px, 1.5, rng)
    a = np.clip(across[None, :] * (0.8 + 0.15 * along + 0.06 * fine), 0, 1) * 0.36
    col = np.zeros((h, w, 3), np.float32) + np.array([0.15, 0.15, 0.155])
    col *= (1 + 0.06 * fine)[..., None]
    Image.fromarray(np.dstack([to8(col), to8(a)])).save(os.path.join(dst, "t_wear_track_b.color.png"))
    # the edge: dust and sand, browner and lighter than the asphalt, strongest at the outer side (u = 0)
    edge = np.clip(1.0 - u / 0.9, 0, 1) ** 0.8 * np.clip(u / 0.08, 0, 1)
    along2 = aniso_noise(h, w, 1.5 * px, 3, rng)
    speck = aniso_noise(h, w, 0.6, 0.6, rng)
    a2 = np.clip(edge[None, :] * (0.6 + 0.25 * along2 + 0.15 * speck), 0, 1) * 0.7
    col2 = np.zeros((h, w, 3), np.float32) + np.array([0.45, 0.42, 0.35])
    col2 *= (1 + 0.10 * speck + 0.05 * along2)[..., None]
    Image.fromarray(np.dstack([to8(col2), to8(a2)])).save(os.path.join(dst, "t_wear_edge_b.color.png"))


def materials():
    t = f"/levels/{LEVEL_NAME}/art/shapes/roads"
    out = []
    for name, rough in (("t_wear_track", 0.62), ("t_wear_edge", 0.95)):
        out.append(bng.material("mp_" + name[2:], f"{t}/{name}_b.color.png", roughness=rough,
                                extra={"translucent": True, "translucentBlendOp": "LerpAlpha",
                                       "translucentZWrite": False, "castShadows": False}))
    return out


def bands(road):
    """[(material, offsets (n,) m left of the axis, width m)] of an AI road's wear bands, from its nodes."""
    nodes = np.asarray(road["nodes"], np.float64)
    W = np.median(nodes[:, 3])
    if W < MIN_W:
        return nodes, []
    ll, lr = int(road.get("lanesLeft", 1) or 0), int(road.get("lanesRight", 1) or 0)
    lanes = max(ll + lr, 1)
    out = []
    half = nodes[:, 3] / 2
    if W < NARROW or lanes == 1:
        out.append(("mp_wear_track", np.zeros(len(nodes)), PAIR_W))
    else:
        lw = nodes[:, 3] / lanes
        for k in range(lanes):
            out.append(("mp_wear_track", -half + lw * (k + 0.5), PAIR_W))
    for s in (-1, 1):
        out.append(("mp_wear_edge" + ("_r" if s < 0 else ""), s * (half - EDGE_IN), EDGE_W))     # s < 0: the right edge
    return nodes, out


def strip(P, off, width, S, middle=True):
    """Triangles and texture coordinates of a band at `off` m left of the polyline P (n, 2) on surface S."""
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nl = np.column_stack([-T[:, 1], T[:, 0]])
    C = P + Nl * off[:, None]
    z = S.height(C[:, 0], C[:, 1], "high")
    ok = np.isfinite(z)
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(C, axis=0).T))]
    tris, uvs = [], []
    e = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
    for a, b in zip(e[::2], e[1::2]):
        if b - a < 3:
            continue
        Pa, za, sa, Na = C[a:b], z[a:b], s[a:b], Nl[a:b]
        rows = []
        for k in ((1, 0, -1) if middle else (1, -1)):                # left side, (middle,) right side of the band
            Q = np.column_stack([Pa + Na * k * width / 2, za + LIFT])
            if k:
                zq = S.height(Q[:, 0], Q[:, 1], "high")
                Q[:, 2] = np.where(np.isfinite(zq), zq + LIFT, Q[:, 2])
            rows.append(Q)
        v = sa / V_TILE
        n1 = b - a - 1
        ts, us = [], []
        pairs = (((rows[1], 0.5), (rows[2], 1.0)), ((rows[0], 0.0), (rows[1], 0.5))) if middle else (((rows[0], 0.0), (rows[1], 1.0)),)
        for (L, uL), (R, uR) in pairs:
            ts.append(np.stack([R[:-1], R[1:], L[1:], R[:-1], L[1:], L[:-1]], 1))
            us.append(np.stack([np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uR), v[1:]], np.c_[np.full(n1, uL), v[1:]],
                                np.c_[np.full(n1, uR), v[:-1]], np.c_[np.full(n1, uL), v[1:]], np.c_[np.full(n1, uL), v[:-1]]], 1))
        t = np.concatenate(ts, 1).reshape(-1, 3, 3)
        uv = np.concatenate(us, 1).reshape(-1, 3, 2)
        down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
        t[down] = t[down][:, ::-1]
        uv[down] = uv[down][:, ::-1]
        tris.append(t)
        uvs.append(uv)
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 2))
    return np.concatenate(tris), np.concatenate(uvs)


def road_wear_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    carriage = [up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS]
    S = TriSurface(np.concatenate(carriage))
    roads = read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json")
    builders = {}
    stats = {"roads": 0, "track_m": 0.0, "edge_m": 0.0}
    for road in roads:
        nodes, bl = bands(road)
        if not bl or len(nodes) < 2:
            continue
        P = nodes[:, :2]
        # densify, carrying the offsets along
        seg = np.hypot(*np.diff(P, axis=0).T)
        s = np.r_[0, np.cumsum(seg)]
        if s[-1] < 2 * STEP:
            continue
        sd = np.linspace(0, s[-1], int(np.ceil(s[-1] / STEP)) + 1)
        Pd = np.column_stack([np.interp(sd, s, P[:, 0]), np.interp(sd, s, P[:, 1])])
        stats["roads"] += 1
        for mat, off, width in bl:
            od = np.interp(sd, s, off)
            t, uv = strip(Pd, od, width, S, middle="track" in mat)    # the narrow edge bands are flat
            if not len(t):
                continue
            if mat == "mp_wear_edge_r":                      # the band of the right edge: its outer side is u = 1
                mat, uv = "mp_wear_edge", uv.copy()
                uv[..., 0] = 1.0 - uv[..., 0]
            stats["track_m" if "track" in mat else "edge_m"] += float(len(t) / (4 if "track" in mat else 2) * STEP)
            c = t.mean(1)
            keys = np.floor(c[:, :2] / TILE).astype(int)
            for key in {tuple(k) for k in keys.tolist()}:
                m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
                V = t[m].reshape(-1, 3)
                builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=uv[m].reshape(-1, 2),
                                                                normals=np.repeat([[0, 0, 1.0]], len(V), 0))
    tmp = tempfile.mkdtemp(prefix="magliaso_wear_")
    try:
        new_files = {}
        objs = []
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/road_wear_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(f, name=f"road_wear_{tx}_{ty}", origin=origin)
            text = open(f, encoding="utf-8").read()
            out, _ = optimize_level.optimize_dae([(text, np.zeros(3))], rel.split("art/shapes/", 1)[1])
            new_files[f"{lv}/{rel}"] = (out or text).encode("utf-8")
            objs.append(bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False))
        textures(tmp)
        for name in TEX:
            new_files[f"{lv}/art/shapes/roads/{name}_b.color.png"] = open(os.path.join(tmp, f"{name}_b.color.png"), "rb").read()
        mats_name = f"{lv}/art/shapes/roads/main.materials.json"
        mats = json.loads(zi.read(mats_name))
        for m in materials():
            mats[m["name"]] = m
        new_files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
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
                zo.writestr(n, data, compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats.update(meshes=len(builders), seconds=round(time.time() - t0))
    stats["track_km"] = round(stats.pop("track_m") / 1000, 1)
    stats["edge_km"] = round(stats.pop("edge_m") / 1000, 1)
    print("road wear:", stats, flush=True)
    if report:
        json.dump(stats, open(report, "w"), indent=1)
    return 0
