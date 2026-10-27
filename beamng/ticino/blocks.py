"""Ticino a blocchi, phase 1: cut a built level into the files the streaming mod reads.

The level of today (one 8192 x 8192 TerrainBlock at 1.5 m, every object loaded at the start) becomes the level
`ticino` (beamng/ticino/README.md):
  - terrain blocks of BLOCK x BLOCK samples (1,280 = 1,920 m, 3.7 km2): heights (uint16, the zone's z0 and
    maxHeight) and layers (uint8), rows from the south, as in the .ter. The mod puts the 2048 x 2048 window around
    the car together from them (ter.lua) and moves it every CELL samples (256 = 384 m);
  - per block and base colour texture, the colour map at BASE_SPP samples a pixel (the window's base texture is
    put together the same way, png.lua);
  - the objects (TSStatic, SpotLight) in 384 m tiles, each with the radius in tiles it is shown within;
  - a coarse ground mesh per 384 m tile (far.dae), drawn where the window has no terrain;
  - the rest of the scene (sky, water planes, forest, ground cover, AI roads, spawn points) as a normal level.

Nothing is rebuilt: the blocks hold the released level's own samples, so the window must match the original
terrain sample for sample (tests/check_blocks.py).

    python blocks.py --zone zones/malcantone.json --src <folder with levels/magliaso_pura> --out <folder>

--out gets levels/ticino/... (hard links to the source where a file is copied unchanged); package.py zips it with
the mod's Lua. The source level is never written to.
"""
import argparse
import json
import math
import os
import re
import shutil
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
import bng  # noqa: E402  (writers only: bng imports nothing of the pipeline's config)
import cdae  # noqa: E402
import aimap_check  # noqa: E402

LEVEL = "ticino"
FAR_MAT = "tc_far_ground"
# text files whose level paths are rewritten (/levels/<source>/ -> /levels/ticino/); everything else is linked
TEXT_EXT = (".json", ".lua", ".cs", ".txt", ".md")
# object classes the mod streams; the others stay in the scene
STREAMED = ("TSStatic", "SpotLight", "PointLight")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ zone grid
class Zone:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = cfg["name"]
        self.x0, self.y0, self.sq = float(cfg["origin_x"]), float(cfg["origin_y"]), float(cfg["square"])
        self.B = int(cfg["block_samples"])
        self.C = int(cfg["cell_samples"])
        self.W = int(cfg["window_samples"])
        self.SPP = int(cfg["base_samples_per_px"])
        assert self.B % self.C == 0 and self.W % self.C == 0 and self.C % self.SPP == 0
        assert self.W & (self.W - 1) == 0, "the window must be a power of two"
        self.cell_m = self.C * self.sq

    def cell_of(self, x, y):
        return int(math.floor((x - self.x0) / self.cell_m)), int(math.floor((y - self.y0) / self.cell_m))

    def window_for(self, x, y):
        """Window origin (samples) with the car's cell the 4th of 8 (as the mod's first window)."""
        cx, cy = self.cell_of(x, y)
        n = self.W // self.C
        return (cx - (n // 2 - 1)) * self.C, (cy - (n // 2 - 1)) * self.C


# ------------------------------------------------------------------ source level
def read_ndjson(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def scene_files(level_dir):
    """{group path relative to main/ ('MissionGroup/props/street_life'): [objects]} of the level."""
    out = {}
    root = os.path.join(level_dir, "main")
    for dp, _, fs in os.walk(root):
        if "items.level.json" in fs:
            rel = os.path.relpath(dp, root).replace(os.sep, "/")
            out[rel] = read_ndjson(os.path.join(dp, "items.level.json"))
    return out


def read_ter(level_dir, tb):
    tj = json.load(open(os.path.join(level_dir, "theTerrain.terrain.json")))
    n = int(tj["size"])
    path = os.path.join(level_dir, os.path.basename(tb["terrainFile"]))
    with open(path, "rb") as f:
        ver, size = struct.unpack("<BI", f.read(5))
    assert ver == 9 and size == n, (ver, size, n)
    H = np.memmap(path, "<u2", "r", 5, (n, n))
    L = np.memmap(path, "u1", "r", 5 + 2 * n * n, (n, n))
    return n, H, L, tj["materials"]


# ------------------------------------------------------------------ terrain blocks
def write_blocks(zone, H, L, out_dir):
    """Blocks of zone.B x zone.B samples covering the source terrain; samples past its edge repeat the edge.
    Returns {"bx_by": [bx, by]} of the blocks written."""
    n = H.shape[0]
    nb = -(-n // zone.B)
    os.makedirs(out_dir, exist_ok=True)
    blocks = {}
    for by in range(nb):
        for bx in range(nb):
            r = np.clip(np.arange(by * zone.B, (by + 1) * zone.B), 0, n - 1)
            c = np.clip(np.arange(bx * zone.B, (bx + 1) * zone.B), 0, n - 1)
            h = np.ascontiguousarray(H[r][:, c]).astype("<u2")
            lay = np.ascontiguousarray(L[r][:, c]).astype("u1")
            with wopen(os.path.join(out_dir, f"t_{bx}_{by}.bin"), "wb") as f:
                f.write(h.tobytes())
                f.write(lay.tobytes())
            blocks[f"{bx}_{by}"] = [bx, by]
    log("terrain blocks:", len(blocks), "of", zone.B, "samples,", nb, "x", nb)
    return blocks, nb


def window_ter(zone, blocks_dir, nb, wx, wy, materials, z0=None):
    """The window .ter bytes at sample origin (wx, wy), put together from the blocks exactly as ter.lua does
    (the reference for tests/check_blocks.py and the level's start window)."""
    W, B = zone.W, zone.B
    H = np.zeros((W, W), "<u2")
    Lr = np.zeros((W, W), "u1")
    cache = {}

    def block(bx, by):
        k = (bx, by)
        if k not in cache:
            p = os.path.join(blocks_dir, f"t_{bx}_{by}.bin")
            if 0 <= bx < nb and 0 <= by < nb and os.path.exists(p):
                raw = np.fromfile(p, "u1")
                cache[k] = (raw[:2 * B * B].view("<u2").reshape(B, B), raw[2 * B * B:].reshape(B, B))
            else:
                cache[k] = None
        return cache[k]

    for r in range(W):
        gy = wy + r
        by, br = gy // B, gy % B
        c = 0
        while c < W:
            gx = wx + c
            bx, bc = gx // B, gx % B
            k = min(B - bc, W - c)
            b = block(bx, by)
            if b is not None:
                H[r, c:c + k] = b[0][br, bc:bc + k]
                Lr[r, c:c + k] = b[1][br, bc:bc + k]
            c += k
    out = bytearray(struct.pack("<BI", 9, W))
    out += H.tobytes()
    out += Lr.tobytes()
    out += struct.pack("<I", len(materials))
    for m in materials:
        b = m.encode("utf-8")
        out += struct.pack("<B", len(b)) + b
    return bytes(out)


# ------------------------------------------------------------------ base colour maps
def load_png_rgb(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))


def base_maps(zone, level_dir, src_mats, n_src, nb, out_dir, src_level):
    """Per block, the colour map of every terrain base texture that spans the whole terrain (the open-ground
    maps from the orthophoto, terrain.base_color_maps), at zone.SPP samples a pixel, rows from the SOUTH.
    The tiling ones (forest floor noise, 256 m) stay as they are. Returns ({texture key: level path}, the
    materials list for the level)."""
    from scipy.ndimage import map_coordinates
    os.makedirs(out_dir, exist_ok=True)
    extent_m = n_src * zone.sq            # the pipeline gives the global maps BASE_SIZE_M = TER_SIZE * TER_SQUARE
    keys = {}
    for name, m in src_mats.items():
        if m.get("class") != "TerrainMaterial":
            continue
        if float(m.get("baseColorBaseTexSize", 0)) < 2048:
            continue
        tex = m["baseColorBaseTex"]
        keys.setdefault(tex, os.path.splitext(os.path.basename(tex))[0])
    nb_px = zone.B // zone.SPP
    for tex, key in keys.items():
        img = load_png_rgb(os.path.join(level_dir, *tex.split(f"/levels/{src_level}/")[1].split("/")))
        img = img[::-1].astype(np.float32)          # row 0 = south (BASE_FLIP: the PNG's row 0 is the north)
        npx = img.shape[0]
        px_m = extent_m / npx
        for by in range(nb):
            for bx in range(nb):
                # pixel centres of the block's map in metres from the grid origin, then in source pixels
                xs = (bx * zone.B + (np.arange(nb_px) + 0.5) * zone.SPP) * zone.sq
                ys = (by * zone.B + (np.arange(nb_px) + 0.5) * zone.SPP) * zone.sq
                u = np.clip(xs / px_m - 0.5, 0, npx - 1)
                v = np.clip(ys / px_m - 0.5, 0, npx - 1)
                V, U = np.meshgrid(v, u, indexing="ij")
                out = np.stack([map_coordinates(img[..., k], [V, U], order=1, mode="nearest") for k in range(3)], -1)
                np.clip(np.round(out), 0, 255).astype("u1").tofile(os.path.join(out_dir, f"{key}_{bx}_{by}.rgb"))
        log("base map", key, "->", nb * nb, "blocks of", nb_px, "px")
    return keys


# ------------------------------------------------------------------ objects
_PA = re.compile(rb'<float_array id="[^"]*-pa" count="(\d+)">')


def dae_center(path, cache):
    """Centre (x, y) of the bounding box of the first geometry of a DAE (the merged shapes keep their position at
    a corner of their chunk, optimize_level), or None."""
    if path in cache:
        return cache[path]
    res = None
    try:
        with open(path, "rb") as f:
            data = f.read()
        m = _PA.search(data)
        if m:
            end = data.index(b"<", m.end())
            v = np.array(data[m.end():end].split(), np.float64).reshape(-1, 3)
            if len(v):
                lo, hi = v.min(0), v.max(0)
                res = [float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)]
    except (OSError, ValueError):
        res = None
    cache[path] = res
    return res


def quat_conj_from_rows(rows):
    """setPosRot's quaternion (the conjugate form BeamNG.Earth found, farfield.lua) of a level rotationMatrix
    (its ROWS are the object's x, y, z axes: bng.rot_local_x_to)."""
    M = np.asarray(rows, np.float64).reshape(3, 3)
    R = M.T                                   # columns = the object's axes in the world: local -> world
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    q = np.array([x, y, z, w])
    q /= np.linalg.norm(q)
    return [round(float(-q[0]), 7), round(float(-q[1]), 7), round(float(-q[2]), 7), round(float(q[3]), 7)]


def group_radius(zone, rel):
    """Radius (tiles) of a scene group path relative to MissionGroup: the longest configured prefix."""
    best, r = -1, None
    for g, v in zone.cfg["groups"].items():
        if (rel == g or rel.startswith(g + "/")) and len(g) > best:
            best, r = len(g), int(v["radius"])
    return r


def is_static(zone, rel):
    return any(rel == g or rel.startswith(g + "/") for g in zone.cfg.get("static_groups", []))


def stream_objects(zone, scene, level_dir, src_level, out_dir, col_dir=None, workers=4):
    """Splits the scene: streamed objects go into tiles/<cx>_<cy>.json, the others stay. col_dir: the level's own
    shapes collide through the collision cells written there (collision.py). Returns the scene without them,
    {tile key: object count} and (cell keys, ground types, stats) of the collision cells (None without col_dir)."""
    os.makedirs(out_dir, exist_ok=True)
    tiles, kept, cache = {}, {}, {}
    prefix = f"/levels/{src_level}/"
    n_obj = 0
    for path, objs in scene.items():
        rel = path.split("/", 1)[1] if "/" in path else ""
        r = None if is_static(zone, rel) else group_radius(zone, rel)
        keep = []
        for o in objs:
            if r is None or o.get("class") not in STREAMED:
                keep.append(o)
                continue
            x, y = o["position"][0], o["position"][1]
            shape = o.get("shapeName", "")
            if shape.startswith(prefix):
                p = os.path.join(level_dir, *shape[len(prefix):].split("/"))
                if os.path.exists(p) and os.path.getsize(p) > 100_000:
                    c = dae_center(p, cache)
                    if c is not None:
                        x, y = x + c[0], y + c[1]
            cx, cy = zone.cell_of(x, y)
            e = {k: v for k, v in o.items() if k not in ("persistentId", "__parent", "position", "rotationMatrix",
                                                         "scale")}
            e["p"] = [round(float(v), 4) for v in o["position"]]
            if "rotationMatrix" in o:
                e["q"] = quat_conj_from_rows(o["rotationMatrix"])
            if "scale" in o:
                e["s"] = [round(float(v), 5) for v in o["scale"]]
            if "shapeName" in e:
                e["shapeName"] = e["shapeName"].replace(prefix, f"/levels/{LEVEL}/")
            e["g"] = rel
            e["r"] = r
            tiles.setdefault((cx, cy), []).append(e)
            n_obj += 1
        kept[path] = keep
    cells = None
    if col_dir:
        import collision
        cells = collision.build(zone, tiles, level_dir, src_level, col_dir, workers=workers)
    for (cx, cy), objs in tiles.items():
        with wopen(os.path.join(out_dir, f"o_{cx}_{cy}.json"), "w") as f:
            json.dump(objs, f, separators=(",", ":"))
    log("streamed objects:", n_obj, "in", len(tiles), "tiles;", len(cache), "shape bounds read")
    return kept, {f"{cx}_{cy}": len(v) for (cx, cy), v in tiles.items()}, cells


# ------------------------------------------------------------------ far ground
def layer_colors(level_dir, src_mats, src_level):
    """Mean colour (0..1) of every terrain material's base texture: the far ground's colour where no global map."""
    out = {}
    for name, m in src_mats.items():
        if m.get("class") != "TerrainMaterial":
            continue
        tex = m["baseColorBaseTex"]
        p = os.path.join(level_dir, *tex.split(f"/levels/{src_level}/")[1].split("/"))
        out[m["internalName"]] = load_png_rgb(p).reshape(-1, 3).mean(0) / 255.0
    return out


def write_far(zone, H, L, z0, maxh, materials, level_dir, src_mats, src_level, out_dir):
    """One coarse ground mesh per 384 m cell (.cdae) (every far_step samples, a 4 m skirt down along its edges), coloured by
    the layer under each vertex (the global base map where the layer has one). Returns the cell keys."""
    step = int(zone.cfg.get("far_step_samples", 8))
    n = H.shape[0]
    C = zone.C
    nc = n // C
    os.makedirs(out_dir, exist_ok=True)
    mean = layer_colors(level_dir, src_mats, src_level)
    gmaps = {}
    for name, m in src_mats.items():
        if m.get("class") == "TerrainMaterial" and float(m.get("baseColorBaseTexSize", 0)) >= 2048:
            tex = m["baseColorBaseTex"]
            gmaps[m["internalName"]] = load_png_rgb(
                os.path.join(level_dir, *tex.split(f"/levels/{src_level}/")[1].split("/")))[::-1] / 255.0
    lut = np.array([mean.get(mn, np.array([0.4, 0.45, 0.3])) for mn in materials])
    k = C // step + 1
    keys = []
    for cy in range(nc):
        for cx in range(nc):
            r = np.clip(cy * C + np.arange(k) * step, 0, n - 1)
            c = np.clip(cx * C + np.arange(k) * step, 0, n - 1)
            h = H[r][:, c].astype(np.float64) / 65535.0 * maxh + z0
            lay = L[r][:, c].astype(np.int64)
            lay = np.where(lay < len(lut), lay, 0)
            col = lut[lay]
            for li, mn in enumerate(materials):
                if mn in gmaps:
                    sel = lay == li
                    if sel.any():
                        g = gmaps[mn]
                        f = g.shape[0] / n
                        rr, cc = np.meshgrid((r * f).astype(int), (c * f).astype(int), indexing="ij")
                        col[sel] = g[np.clip(rr, 0, g.shape[0] - 1), np.clip(cc, 0, g.shape[1] - 1)][sel]
            X, Y = np.meshgrid(np.arange(k) * step * zone.sq, np.arange(k) * step * zone.sq)
            V = np.stack([X, Y, h], -1).reshape(-1, 3)
            cols = np.concatenate([col.reshape(-1, 3), np.ones((k * k, 1))], 1)
            ii = np.arange(k * k).reshape(k, k)
            a, b, c2, d = ii[:-1, :-1].ravel(), ii[:-1, 1:].ravel(), ii[1:, :-1].ravel(), ii[1:, 1:].ravel()
            T = np.concatenate([np.stack([a, b, d], 1), np.stack([a, d, c2], 1)])
            # skirt: the border ring again 4 m lower, so no crack shows against the window or a coarser tile
            ring = np.concatenate([ii[0, :], ii[1:, -1], ii[-1, -2::-1], ii[-2:0:-1, 0]])
            Vs = V[ring] - [0, 0, 4.0]
            base = len(V)
            nr = len(ring)
            j = np.arange(nr)
            A, Bn = ring[j], ring[(j + 1) % nr]
            As, Bs = base + j, base + (j + 1) % nr
            Ts = np.concatenate([np.stack([A, As, Bs], 1), np.stack([A, Bs, Bn], 1)])
            # written compiled (.cdae, as BeamNG.Earth writes its far tiles): the game converted every far .dae the
            # first time it was shown, part of the 40 s of a quick travel into a new zone (2026-10-26)
            C8 = np.clip(np.round(np.concatenate([cols, cols[ring]]) * 255), 0, 255).astype(np.uint8)
            cdae.write(os.path.join(out_dir, f"f_{cx}_{cy}.cdae"), np.concatenate([V, Vs]), np.concatenate([T, Ts]),
                       uvs=np.zeros((base + nr, 2)), material=FAR_MAT, colors=C8, object_name="farground")
            keys.append(f"{cx}_{cy}")
    mats = [bng.material(FAR_MAT, base_color=[1, 1, 1, 1], vert_color=True, roughness=0.95,
                         extra={"castShadows": False})]
    bng.write_materials(os.path.join(out_dir, "far.materials.json"), mats)
    log("far ground:", len(keys), "cells,", k - 1, "x", k - 1, "squares of", step * zone.sq, "m each")
    return keys


# ------------------------------------------------------------------ level copy
def wopen(path, mode="w", **kw):
    """open() for writing a NEW file: the output level is mostly hard links to the source level, and writing into a
    linked path changes the source too (info.json of v3.1.1 got the "Streaming test" prefix once per run)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.lexists(path):
        os.remove(path)
    return open(path, mode, **kw)


def link_or_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def copy_level(src_dir, dst_dir, src_level, skip):
    """The source level's files under the new name: text files with their level paths rewritten, the rest
    hard-linked. skip(rel) leaves a file out."""
    old, new = f"/levels/{src_level}/".encode(), f"/levels/{LEVEL}/".encode()
    old2, new2 = f"levels/{src_level}/".encode(), f"levels/{LEVEL}/".encode()
    n_txt = n_link = 0
    for dp, _, fs in os.walk(src_dir):
        for fn in fs:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, src_dir).replace(os.sep, "/")
            if skip(rel):
                continue
            q = os.path.join(dst_dir, *rel.split("/"))
            if fn.lower().endswith(TEXT_EXT):
                data = open(p, "rb").read()
                if old in data or old2 in data:
                    data = data.replace(old, new).replace(old2, new2)
                    os.makedirs(os.path.dirname(q), exist_ok=True)
                    with wopen(q, "wb") as f:
                        f.write(data)
                    n_txt += 1
                    continue
            link_or_copy(p, q)
            n_link += 1
    log("level copy:", n_txt, "text files rewritten,", n_link, "linked")


AI_SPEED_STEP = 1e-5       # m/s added per AI road (3,451 roads: at most +0.035 m/s)


def ai_roads(objs, n_ai):
    """The AI DecalRoads of a scene file as the streamed level needs them: useSubdivisions off and a speed limit of
    their own. Without subdivisions two roads that join the same two nodes (the two one-way halves round a splitter
    island) tie in every field map.lua's edgeCompare reads before `lanes`, and its node reduction compares them with
    a new edge that has no lanes: "attempt to compare nil with string", the level load crashed (laptop run 5). A speed
    limit that differs by AI_SPEED_STEP per road ends the compare before `lanes` (aimap_check.py emulates it)."""
    out = []
    for o in objs:
        if o.get("class") == "DecalRoad":
            n_ai[0] += 1
            o = dict(o, useSubdivisions=False)
            if o.get("speedLimit"):
                o["speedLimit"] = round(float(o["speedLimit"]) + n_ai[0] * AI_SPEED_STEP, 6)
        out.append(o)
    return out


def write_scene(kept, dst_dir, tb_new, src_level):
    main = os.path.join(dst_dir, "main")
    if os.path.isdir(main):
        shutil.rmtree(main)
    n_ai, roads = [0], []
    for path, objs in kept.items():
        if path.endswith("level_objects/terrain"):
            objs = [tb_new if o.get("class") == "TerrainBlock" else o for o in objs]
        # the AI roads: map.lua builds the AI graph from a DecalRoad's subdivided edges when useSubdivisions is on,
        # and those are clipped to the terrain, which exists only in the streamed window: 14-19 k of the 20,810
        # nodes lay at z 0 (laptop runs 2-4). Off, it takes the control points with their own heights. (A
        # map.reset() after every window move fixed the nodes near the car but froze the laptop 2-2.5 s each time.)
        objs = ai_roads(objs, n_ai)
        roads += [o for o in objs if o.get("class") == "DecalRoad"]
        d = os.path.join(main, *path.split("/")) if path != "." else main
        os.makedirs(d, exist_ok=True)
        with wopen(os.path.join(d, "items.level.json"), "w", encoding="utf-8") as f:
            for o in objs:
                f.write(json.dumps(o, separators=(",", ":")).replace(f"/levels/{src_level}/", f"/levels/{LEVEL}/")
                        + "\n")
    crashes = aimap_check.check(roads, seeds=2)
    print(f"  AI map check (map.lua emulated, 2 node orders): {len(roads)} roads, {len(crashes)} crashing compares")
    if crashes:
        raise SystemExit(f"AI roads would crash the game's map.lua: {crashes[:5]}")


def terrain_materials(src_mats, base_keys, zone, src_level):
    """The terrain materials of the window: the global base maps become the window's (a file the mod rewrites,
    its size the window in samples: BeamNG.Earth measured the size in samples, terrain.lua), the base texture set
    zone.W / zone.SPP pixels a side (its sizes must match every base texture)."""
    px = zone.W // zone.SPP
    out = {}
    for k, m in src_mats.items():
        m = json.loads(json.dumps(m).replace(f"/levels/{src_level}/", f"/levels/{LEVEL}/"))
        if m.get("class") == "TerrainMaterialTextureSet":
            m["baseTexSize"] = [px, px]
        elif m.get("class") == "TerrainMaterial":
            src_tex = src_mats[k]["baseColorBaseTex"]
            for f in ("normal", "roughness", "ao", "height"):
                tex = m.get(f + "BaseTex", "")
                if tex:
                    m[f + "BaseTex"] = f"/levels/{LEVEL}/art/terrains/w/{os.path.splitext(os.path.basename(tex))[0]}.png"
            if src_tex in base_keys:
                m["baseColorBaseTex"] = f"/levels/{LEVEL}/art/terrains/w/{base_keys[src_tex]}.png"
                size = zone.W if zone.cfg.get("base_size_unit", "samples") == "samples" else zone.W * zone.sq
            else:
                m["baseColorBaseTex"] = f"/levels/{LEVEL}/art/terrains/w/" + \
                    os.path.splitext(os.path.basename(src_tex))[0] + ".png"
                size = m.get("baseColorBaseTexSize", 256)
            for f in ("baseColor", "normal", "roughness", "ao", "height"):
                if f + "BaseTexSize" in m:
                    m[f + "BaseTexSize"] = size
        out[k] = m
    return out


def resized_textures(level_dir, src_mats, base_keys, zone, src_level, dst):
    """Every base texture of the terrain at the window's texture set size (art/terrains/w/): the flat normal,
    roughness, ao and height maps and the tiling noise maps scaled, the global maps as a neutral start image
    (the mod writes the window's own one before the first frame)."""
    from PIL import Image
    px = zone.W // zone.SPP
    os.makedirs(dst, exist_ok=True)
    done = set()
    for m in src_mats.values():
        if m.get("class") != "TerrainMaterial":
            continue
        for f in ("baseColor", "normal", "roughness", "ao", "height"):
            tex = m.get(f + "BaseTex")
            if not tex or tex in done:
                continue
            done.add(tex)
            src = os.path.join(level_dir, *tex.split(f"/levels/{src_level}/")[1].split("/"))
            img = Image.open(src)
            if tex in base_keys:
                img = Image.new("RGB", (px, px), tuple(int(v) for v in np.asarray(img.convert("RGB")).reshape(-1, 3).mean(0)))
            else:
                img = img.resize((px, px), Image.LANCZOS)
            with wopen(os.path.join(dst, os.path.splitext(os.path.basename(tex))[0] + ".png"), "wb") as f:
                img.save(f, "PNG")
    log("terrain base textures at", px, "px:", len(done))


def collision_cell_m():
    import collision
    return collision.CELL_M


def collision_piece_tris():
    import collision
    return collision.PIECE_TRIS


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--src", required=True, help="folder that holds levels/<source_level>/ (an unpacked release)")
    ap.add_argument("--out", required=True, help="folder that gets levels/ticino/ (on the PC: the 6 TB disk)")
    ap.add_argument("--no-far", action="store_true", help="skip the far ground meshes (quick tests)")
    ap.add_argument("--no-collision-cells", action="store_true",
                    help="the level's shapes collide with their drawn meshes, as in the first test (comparisons)")
    ap.add_argument("--workers", type=int, default=4, help="processes reading the shapes for the collision cells")
    a = ap.parse_args()
    zone = Zone(json.load(open(a.zone)))
    src_level = zone.cfg["source_level"]
    src = os.path.join(a.src, "levels", src_level)
    dst = os.path.join(a.out, "levels", LEVEL)
    t0 = time.time()

    scene = scene_files(src)
    tb = next(o for objs in scene.values() for o in objs if o.get("class") == "TerrainBlock")
    assert abs(tb["position"][0] - zone.x0) < 1e-6 and abs(tb["position"][1] - zone.y0) < 1e-6 \
        and abs(tb["squareSize"] - zone.sq) < 1e-9, "the zone grid must be the source terrain's"
    z0, maxh = float(tb["position"][2]), float(tb["maxHeight"])
    n, H, L, materials = read_ter(src, tb)
    src_mats = json.load(open(os.path.join(src, "art", "terrains", "main.materials.json")))

    # the level copy first (it clears what blocks.py writes below on a rerun)
    stream_dirs = ("blocks/", "tiles/", "col/", "art/terrains/w/", "main/") + (() if a.no_far else ("far/",))
    skip = lambda rel: rel.startswith(stream_dirs) or rel in ("theTerrain.ter", "theTerrain.terrain.json") \
        or rel.endswith(".terrainheightmap.png")
    for d in stream_dirs:
        shutil.rmtree(os.path.join(dst, *d.strip("/").split("/")), ignore_errors=True)
    copy_level(src, dst, src_level, skip)
    gm_src = os.path.join(a.src, "gameplay", "missions", src_level)
    if os.path.isdir(gm_src):
        copy_level(gm_src, os.path.join(a.out, "gameplay", "missions", LEVEL), src_level, lambda rel: False)

    blocks, nb = write_blocks(zone, H, L, os.path.join(dst, "blocks", "terrain"))
    base_keys = base_maps(zone, src, src_mats, n, nb, os.path.join(dst, "blocks", "base"), src_level)
    kept, tiles, cells = stream_objects(zone, scene, src, src_level, os.path.join(dst, "tiles"),
                                        None if a.no_collision_cells else os.path.join(dst, "col"), a.workers)
    if cells:
        with wopen(os.path.join(dst, "col", "stats.json")) as f:
            json.dump(cells[2], f, indent=1)
    far_dir = os.path.join(dst, "far")
    far = sorted(os.path.splitext(f)[0][2:] for f in os.listdir(far_dir) if f.startswith("f_")) if a.no_far and os.path.isdir(far_dir) \
        else [] if a.no_far else write_far(zone, H, L, z0, maxh, materials, src, src_mats, src_level,
                                        os.path.join(dst, "far"))

    mats = terrain_materials(src_mats, base_keys, zone, src_level)
    with wopen(os.path.join(dst, "art", "terrains", "main.materials.json")) as f:
        json.dump(mats, f, indent=1)
    resized_textures(src, src_mats, base_keys, zone, src_level, os.path.join(dst, "art", "terrains", "w"))

    # the start window: around the default spawn point (the mod moves it to the real spawn before physics runs)
    info = json.load(open(os.path.join(src, "info.json")))
    sp = next((o for objs in scene.values() for o in objs
               if o.get("class") == "SpawnSphere" and o.get("name") == info.get("defaultSpawnPointName")), None)
    sx, sy = (sp["position"][0], sp["position"][1]) if sp else (0.0, 0.0)
    wx, wy = zone.window_for(sx, sy)
    with wopen(os.path.join(dst, "start.ter"), "wb") as f:
        f.write(window_ter(zone, os.path.join(dst, "blocks", "terrain"), nb, wx, wy, materials))
    tb_new = dict(tb)
    tb_new["position"] = [zone.x0 + wx * zone.sq, zone.y0 + wy * zone.sq, z0]
    tb_new["terrainFile"] = f"/levels/{LEVEL}/start.ter"
    bng.write_terrain_json(os.path.join(dst, "start.terrain.json"), LEVEL, "start", zone.W, materials)
    write_scene(kept, dst, tb_new, src_level)

    info["title"] = "Ticino (" + zone.name + ")"
    info["description"] = "Streaming test of the Ticino level: " + info.get("description", "")
    info["size"] = [zone.W, zone.W]
    with wopen(os.path.join(dst, "info.json")) as f:
        json.dump(info, f, indent=2)

    stream = {
        "version": 1, "zone": zone.name, "level": LEVEL,
        "origin": [zone.x0, zone.y0], "square": zone.sq, "z0": z0, "maxHeight": maxh,
        "block": zone.B, "cell": zone.C, "window": zone.W, "basePx": zone.SPP,
        "blocksPerSide": nb, "materials": materials,
        "baseTextures": sorted(base_keys.values()),
        # the terrain materials whose base colour is the window's map: [object name, internalName, texture key]
        "baseMaterials": [[k, m["internalName"], base_keys[m["baseColorBaseTex"]]] for k, m in src_mats.items()
                          if m.get("class") == "TerrainMaterial" and m["baseColorBaseTex"] in base_keys],
        "baseSizeUnit": zone.cfg.get("base_size_unit", "samples"),
        "tiles": tiles, "far": far, "farRadius": int(zone.cfg.get("far_radius", 16)),
        "collisionRadius": int(zone.cfg.get("collision_radius", 1)),
        # the collision cells (collision.py): cell size in m, the cells that exist, how many round the car's collide
        "colCell": collision_cell_m() if cells else None, "colCells": cells[0] if cells else [],
        "colGroundTypes": cells[1] if cells else [], "colPieceTris": collision_piece_tris(),
        "colRadius": int(zone.cfg.get("col_radius", 1)),
        "maxRadius": max(int(v["radius"]) for v in zone.cfg["groups"].values()),
        "start": [wx, wy],
    }
    with wopen(os.path.join(dst, "stream.json")) as f:
        json.dump(stream, f, indent=1)
    log("done in %.0f s ->" % (time.time() - t0), dst)


if __name__ == "__main__":
    main()
