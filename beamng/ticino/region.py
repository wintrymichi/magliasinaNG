"""Ticino region: several zone levels (zones/ti/<zone>.json, each built in full by zone_build.yml) joined into the
streaming level `ticino` (the same layout as blocks.py makes from one level, README.md).

Every zone was built over its core (4 x 4 blocks of 1,920 m) + 300 m, on an 8,192 terrain round it; the cores tile
the Malcantone's grid without gaps. So each zone gives only what lies in its core:
  - its terrain blocks (heights put on one height scale for all, layers on one list of terrain materials), and the
    blocks of its terrain beyond its core where no zone of the region has a core (the region's border);
  - the objects in the core: a shape used by one object only (the merged shapes of 384 / 1,152 m chunks, which reach
    across the core's edge) keeps the triangles whose centre lies in the core (clip_dae), copied under z/<zone>/;
    a shape used by several objects and the game's own shapes go by the object's position;
  - its forest items, per 384 m tile (tiles/t_<cx>_<cy>.forest.json): the mod makes them round the car (forest.lua)
    instead of one Forest of millions of items;
  - its roads (DecalRoads) cut exactly at the core's edge and welded to the neighbour's (region_net.py), its water
    blocks cut to the core, its sounds, spawn points, signals, parking spots and fuel stations in the core.
The files every zone has alike (materials, textures, the game's sky, ground cover) are taken once.

    python region.py --zones ti_0_0 ti_1_0 ... --src <folder with levels/<zone>/ of each> --out <folder>

--out gets levels/ticino/ (hard links to the sources where a file is copied unchanged); pack_region.py splits it into
mod zips under 2 GB. The sources are never written to.
"""
import argparse
import collections
import json
import math
import os
import re
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blocks  # noqa: E402
import region_net  # noqa: E402
from blocks import LEVEL, STREAMED, log, wopen, link_or_copy, read_ndjson, scene_files, quat_conj_from_rows  # noqa: E402

GRID_CFG = os.path.join(HERE, "zones", "malcantone.json")     # the grid, the window and the groups' radii
ZONE_DIR = os.path.join(HERE, "zones", "ti")
DROP_GROUPS = ("level_objects/backdrop",)     # each zone's far backdrop: the far ground tiles stand for it
FOREST_ROW_DIGITS = 2
SKIP_FILES = ("theTerrain.ter", "theTerrain.terrain.json", "signals.json", "signalControllerDefinitions.json",
              "city.sites.json", "facilities.sites.json", "main.decals.json")


# ------------------------------------------------------------------ the zones
class Src:
    """One built zone: its level folder, its terrain, its core."""

    def __init__(self, name, root, grid):
        self.name = name
        self.cfg = json.load(open(os.path.join(ZONE_DIR, name + ".json")))
        self.dir = os.path.join(root, "levels", self.cfg["level"])
        self.level = self.cfg["level"]
        self.scene = scene_files(self.dir)
        self.tb = next(o for objs in self.scene.values() for o in objs if o.get("class") == "TerrainBlock")
        self.z0, self.maxh = float(self.tb["position"][2]), float(self.tb["maxHeight"])
        self.n, self.H, self.L, self.materials = blocks.read_ter(self.dir, self.tb)
        self.mats = json.load(open(os.path.join(self.dir, "art", "terrains", "main.materials.json")))
        x0, y0, x1, y1 = self.cfg["core_local"]
        self.core = (x0, y0, x1, y1)
        bx0, by0, nbk = self.cfg["core_blocks"]
        self.core_blocks = {(bx0 + i, by0 + j) for i in range(nbk) for j in range(nbk)}
        # the zone's terrain in global samples
        self.ox = int(round((float(self.tb["position"][0]) - grid.x0) / grid.sq))
        self.oy = int(round((float(self.tb["position"][1]) - grid.y0) / grid.sq))
        assert abs(self.ox * grid.sq + grid.x0 - float(self.tb["position"][0])) < 1e-3, "off the grid"
        self.prefix = f"/levels/{self.level}/"
        self.grid = grid

    def in_core(self, x, y):
        x0, y0, x1, y1 = self.core
        return x0 <= x < x1 and y0 <= y < y1

    def path(self, level_path):
        """The file of a level path of this zone (None if not one of its own)."""
        if not level_path.startswith(self.prefix):
            return None
        return os.path.join(self.dir, *level_path[len(self.prefix):].split("/"))


# ------------------------------------------------------------------ terrain
def height_scale(srcs):
    z0 = math.floor(min(s.z0 for s in srcs))
    top = math.ceil(max(s.z0 + s.maxh for s in srcs))
    return float(z0), float(top - z0)


def layer_list(srcs):
    out = []
    for s in srcs:
        for m in s.materials:
            if m not in out:
                out.append(m)
    assert len(out) < 255, "too many terrain materials"
    return out


def write_blocks(grid, srcs, Z0, MAXH, layers, out_dir):
    """The blocks of every zone's core, then the border blocks of their terrains no core covers. {(bx, by): src}."""
    os.makedirs(out_dir, exist_ok=True)
    B = grid.B
    owner = {}
    for s in srcs:
        for k in s.core_blocks:
            owner[k] = s
    for s in srcs:                           # the border: whole blocks inside the zone's terrain
        for by in range(math.ceil(s.oy / B), (s.oy + s.n) // B):
            for bx in range(math.ceil(s.ox / B), (s.ox + s.n) // B):
                owner.setdefault((bx, by), s)
    for (bx, by), s in sorted(owner.items()):
        r = by * B - s.oy + np.arange(B)
        c = bx * B - s.ox + np.arange(B)
        h = np.asarray(s.H[r[0]:r[-1] + 1, c[0]:c[-1] + 1], np.float64) / 65535.0 * s.maxh + s.z0
        q = np.clip(np.round((h - Z0) / MAXH * 65535.0), 0, 65535).astype("<u2")
        lut = np.full(256, 255, np.uint8)
        for i, m in enumerate(s.materials):
            lut[i] = layers.index(m)
        lay = lut[np.asarray(s.L[r[0]:r[-1] + 1, c[0]:c[-1] + 1])]
        with wopen(os.path.join(out_dir, f"t_{bx}_{by}.bin"), "wb") as f:
            f.write(q.tobytes())
            f.write(np.ascontiguousarray(lay).tobytes())
    log("terrain blocks:", len(owner), "(cores %d)" % sum(len(s.core_blocks) for s in srcs))
    return owner


def global_maps(s):
    """{texture key: (material internalName, level path)} of the zone's terrain maps that span its whole terrain."""
    out = {}
    for m in s.mats.values():
        if m.get("class") == "TerrainMaterial" and float(m.get("baseColorBaseTexSize", 0)) >= 2048:
            tex = m["baseColorBaseTex"]
            out[os.path.splitext(os.path.basename(tex))[0]] = tex
    return out


def write_base_maps(grid, owner, srcs, out_dir):
    """Per block, the colour map of each global base texture of its zone (blocks.base_maps, with the zone's terrain
    offset). Returns the texture keys."""
    from scipy.ndimage import map_coordinates
    os.makedirs(out_dir, exist_ok=True)
    nb_px = grid.B // grid.SPP
    keys = set()
    by_src = collections.defaultdict(list)
    for k, s in owner.items():
        by_src[s.name].append(k)
    for s in srcs:
        extent_m = s.n * grid.sq
        for key, tex in global_maps(s).items():
            keys.add(key)
            img = blocks.load_png_rgb(s.path(tex))[::-1].astype(np.float32)
            npx = img.shape[0]
            px_m = extent_m / npx
            for bx, by in by_src[s.name]:
                xs = ((bx * grid.B - s.ox) + (np.arange(nb_px) + 0.5) * grid.SPP) * grid.sq
                ys = ((by * grid.B - s.oy) + (np.arange(nb_px) + 0.5) * grid.SPP) * grid.sq
                u = np.clip(xs / px_m - 0.5, 0, npx - 1)
                v = np.clip(ys / px_m - 0.5, 0, npx - 1)
                V, U = np.meshgrid(v, u, indexing="ij")
                out = np.stack([map_coordinates(img[..., k], [V, U], order=1, mode="nearest") for k in range(3)], -1)
                p = os.path.join(out_dir, f"{key}_{bx}_{by}.rgb")
                if os.path.lexists(p):
                    os.remove(p)
                np.clip(np.round(out), 0, 255).astype("u1").tofile(p)
        log("base maps of", s.name)
    return sorted(keys)


def write_far(grid, owner, srcs, layers, out_dir):
    """blocks.write_far over the cells of the written blocks, each from its zone. Returns the cell keys."""
    step = int(grid.cfg.get("far_step_samples", 8))
    C = grid.C
    k = C // step + 1
    os.makedirs(out_dir, exist_ok=True)
    per_block = grid.B // C
    keys = []
    for s in srcs:
        mean = layer_colors(s)
        gmaps = {}
        for m in s.mats.values():
            if m.get("class") == "TerrainMaterial" and float(m.get("baseColorBaseTexSize", 0)) >= 2048:
                gmaps[m["internalName"]] = blocks.load_png_rgb(s.path(m["baseColorBaseTex"]))[::-1] / 255.0
        lut = np.array([mean.get(mn, np.array([0.4, 0.45, 0.3])) for mn in s.materials])
        for (bx, by), o in owner.items():
            if o is not s:
                continue
            for j in range(per_block):
                for i in range(per_block):
                    gcx, gcy = bx * per_block + i, by * per_block + j
                    r = np.clip(gcy * C - s.oy + np.arange(k) * step, 0, s.n - 1)
                    c = np.clip(gcx * C - s.ox + np.arange(k) * step, 0, s.n - 1)
                    h = s.H[r][:, c].astype(np.float64) / 65535.0 * s.maxh + s.z0
                    lay = s.L[r][:, c].astype(np.int64)
                    lay = np.where(lay < len(lut), lay, 0)
                    col = lut[lay]
                    for li, mn in enumerate(s.materials):
                        if mn in gmaps:
                            sel = lay == li
                            if sel.any():
                                g = gmaps[mn]
                                f = g.shape[0] / s.n
                                rr, cc = np.meshgrid((r * f).astype(int), (c * f).astype(int), indexing="ij")
                                col[sel] = g[np.clip(rr, 0, g.shape[0] - 1), np.clip(cc, 0, g.shape[1] - 1)][sel]
                    blocks.far_cell(os.path.join(out_dir, f"f_{gcx}_{gcy}.cdae"), h, col, k, step, grid.sq)
                    keys.append(f"{gcx}_{gcy}")
        log("far ground of", s.name)
    blocks.bng.write_materials(os.path.join(out_dir, "far.materials.json"), [blocks.far_material()])
    return keys


def layer_colors(s):
    out = {}
    for m in s.mats.values():
        if m.get("class") == "TerrainMaterial":
            p = s.path(m["baseColorBaseTex"])
            if p and os.path.exists(p):
                out[m["internalName"]] = blocks.load_png_rgb(p).reshape(-1, 3).mean(0) / 255.0
    return out


def terrain_mats(srcs, layers):
    """{object name: material} of every terrain layer (the first zone that has it) with the zone it came from."""
    out, frm = {}, {}
    for name in layers:
        for s in srcs:
            hit = next(((k, m) for k, m in s.mats.items() if m.get("class") == "TerrainMaterial"
                        and m.get("internalName") == name), None)
            if hit:
                out[hit[0]] = hit[1]
                frm[hit[0]] = s
                break
    s0 = srcs[0]
    for k, m in s0.mats.items():
        if m.get("class") == "TerrainMaterialTextureSet":
            out[k] = m
            frm[k] = s0
    return out, frm


def window_materials(grid, mats, frm, base_keys, dst):
    """blocks.terrain_materials + blocks.resized_textures for materials taken from several zones."""
    from PIL import Image
    px = grid.W // grid.SPP
    out = {}
    done = set()
    os.makedirs(dst, exist_ok=True)
    for k, m in mats.items():
        s = frm[k]
        m = json.loads(json.dumps(m).replace(s.prefix, f"/levels/{LEVEL}/"))
        if m.get("class") == "TerrainMaterialTextureSet":
            m["baseTexSize"] = [px, px]
            m["name"] = LEVEL + "TerrainMaterialTextureSet"
            out[m["name"]] = m
            continue
        src_m = mats[k]
        for f in ("baseColor", "normal", "roughness", "ao", "height"):
            tex = src_m.get(f + "BaseTex")
            if not tex:
                continue
            key = os.path.splitext(os.path.basename(tex))[0]
            m[f + "BaseTex"] = f"/levels/{LEVEL}/art/terrains/w/{key}.png"
            if key in done:
                continue
            done.add(key)
            img = Image.open(s.path(tex))
            if f == "baseColor" and key in base_keys:
                img = Image.new("RGB", (px, px),
                                tuple(int(v) for v in np.asarray(img.convert("RGB")).reshape(-1, 3).mean(0)))
            else:
                img = img.resize((px, px), Image.LANCZOS)
            with wopen(os.path.join(dst, key + ".png"), "wb") as fo:
                img.save(fo, "PNG")
        key = os.path.splitext(os.path.basename(src_m["baseColorBaseTex"]))[0]
        size = (grid.W if grid.cfg.get("base_size_unit", "samples") == "samples" else grid.W * grid.sq) \
            if key in base_keys else src_m.get("baseColorBaseTexSize", 256)
        for f in ("baseColor", "normal", "roughness", "ao", "height"):
            if f + "BaseTexSize" in m:
                m[f + "BaseTexSize"] = size
        out[k] = m
    log("terrain materials:", len(out), "textures at", px, "px:", len(done))
    return out


# ------------------------------------------------------------------ shapes
_GEOM = re.compile(rb"<geometry[ >].*?</geometry>", re.S)
_TRI = re.compile(rb'(<triangles[^>]*count=")(\d+)("[^>]*>)(.*?)(<p>)([^<]*)(</p>\s*</triangles>)', re.S)
_INPUT = re.compile(rb'<input semantic="([A-Z]+)" source="#([^"]+)" offset="(\d+)"')


def clip_dae(src, dst, pos, q, scale, rect):
    """Writes src to dst with the triangles whose centre (in the world, the object at pos / q / scale) lies in rect
    (x0, y0, x1, y1). Returns the share kept (1.0: dst is a link to src; 0: nothing written)."""
    data = open(src, "rb").read()
    R = blocks_rot(q)
    sc = np.asarray(scale if scale is not None else [1, 1, 1], np.float64)
    p0 = np.asarray(pos, np.float64)
    x0, y0, x1, y1 = rect
    total = kept = 0
    out, last = [], 0
    for gm in _GEOM.finditer(data):
        geo = gm.group(0)
        vm = re.search(rb'<vertices id="[^"]+">\s*<input semantic="POSITION" source="#([^"]+)"', geo)
        if not vm:
            continue
        sm = re.search(rb'<source id="' + re.escape(vm.group(1)) + rb'">\s*<float_array[^>]*>([^<]*)</float_array>', geo)
        if not sm:
            continue
        P = np.array(sm.group(1).split(), np.float64).reshape(-1, 3) * sc
        if R is not None:
            P = P @ R.T
        P = P + p0
        parts, glast = [], 0
        for tm in _TRI.finditer(geo):
            inputs = _INPUT.findall(tm.group(4) + tm.group(0))
            stride = max(int(o) for _, _, o in inputs) + 1
            voff = next(int(o) for s, _, o in inputs if s == b"VERTEX")
            idx = np.array(tm.group(6).split(), np.int64).reshape(-1, 3, stride)
            c = P[idx[:, :, voff]].mean(1)
            ok = (c[:, 0] >= x0) & (c[:, 0] < x1) & (c[:, 1] >= y0) & (c[:, 1] < y1)
            total += len(ok)
            kept += int(ok.sum())
            if ok.all():
                continue
            sel = idx[ok]
            if not len(sel):
                sel = idx[:1].copy()            # a geometry needs a triangle: one of no area
                sel[:, :, :] = sel[:, :1, :]
            body = " ".join(map(str, sel.reshape(-1).tolist())).encode()
            parts.append(geo[glast:tm.start()])
            parts.append(tm.group(1) + str(len(sel)).encode() + tm.group(3) + tm.group(4) + tm.group(5) + body
                         + tm.group(7))
            glast = tm.end()
        if parts:
            parts.append(geo[glast:])
            out.append(data[last:gm.start()])
            out.append(b"".join(parts))
            last = gm.end()
    if total == 0 or kept == 0:
        return 0.0
    if kept == total:
        link_or_copy(src, dst)
        return 1.0
    out.append(data[last:])
    with wopen(dst, "wb") as f:
        f.write(b"".join(out))
    return kept / total


def blocks_rot(q):
    if q is None:
        return None
    import collision
    return collision.quat_matrix(q)


def entry(o, rel, r, level_path):
    """An object as a tile entry (blocks.stream_objects)."""
    e = {k: v for k, v in o.items() if k not in ("persistentId", "__parent", "position", "rotationMatrix", "scale")}
    e["p"] = [round(float(v), 4) for v in o["position"]]
    if "rotationMatrix" in o:
        e["q"] = quat_conj_from_rows(o["rotationMatrix"])
    if "scale" in o:
        e["s"] = [round(float(v), 5) for v in o["scale"]]
    if level_path:
        e["shapeName"] = level_path
    e["g"] = rel
    e["r"] = r
    return e


def stream_zone(grid, s, dst, tiles, kept, stats, roads):
    """The zone's objects in its core: streamed ones into tiles, the others into kept {group path: [objects]}, the
    DecalRoads cut to the core into roads [(group path, object, zone, cut at start, cut at end)] (welded later)."""
    stale = region_net.stale_cantonale([o for objs in s.scene.values() for o in objs], s, grid)
    if stale:
        log(s.name, "carries the Malcantone's Street View route beyond its terrain: left out")
    uses = collections.Counter(o.get("shapeName", "") for objs in s.scene.values() for o in objs
                               if o.get("class") == "TSStatic")
    cache = {}
    own_shapes = set()
    for path, objs in s.scene.items():
        rel = path.split("/", 1)[1] if "/" in path else ""
        if any(rel == g or rel.startswith(g + "/") for g in DROP_GROUPS):
            continue
        r = None if blocks.is_static(grid, rel) else blocks.group_radius(grid, rel)
        for o in objs:
            cls = o.get("class")
            if cls in ("TerrainBlock", "Forest", "SimGroup"):
                continue
            pos = o.get("position", [0, 0, 0])
            shape = o.get("shapeName", "")
            lp = None
            x, y = pos[0], pos[1]
            if cls == "TSStatic" and shape.startswith(s.prefix):
                relp = shape[len(s.prefix):]
                if uses[shape] > 1:
                    if not s.in_core(x, y):
                        continue
                    lp = f"/levels/{LEVEL}/{relp}"
                else:
                    q = quat_conj_from_rows(o["rotationMatrix"]) if "rotationMatrix" in o else None
                    out = os.path.join(dst, "z", s.name, *relp.split("/"))
                    share = clip_dae(s.path(shape), out, pos, q, o.get("scale"), s.core)
                    stats["clipped" if 0 < share < 1 else "whole" if share else "outside"] += 1
                    if share == 0:
                        continue
                    own_shapes.add(shape)
                    lp = f"/levels/{LEVEL}/z/{s.name}/{relp}"
                    if os.path.getsize(out) > 100_000:
                        cc = blocks.dae_center(out, cache)
                        if cc is not None:
                            x, y = x + cc[0], y + cc[1]
            elif cls in ("WaterBlock",):
                o = clip_box(o, s.core)
                if o is None:
                    continue
            elif cls == "DecalRoad":
                if stale and region_net.is_cantonale(o.get("name", "")):
                    stats["stale_cantonale"] += 1
                    continue
                for piece, c0, c1 in region_net.cut_road(o, s):
                    roads.append((path, piece, s.name, c0, c1))
                continue
            elif cls in ("SpawnSphere",):
                if not s.in_core(x, y):
                    continue
                o = dict(o, name=f"{s.name}_{o.get('name', 'spawn')}")
            elif "position" in o and cls not in ("LevelInfo", "ScatterSky", "TimeOfDay", "CloudLayer",
                                                  "GroundCover", "ForestWindEmitter"):
                if not s.in_core(x, y):
                    continue
            if r is not None and cls in STREAMED:
                cx, cy = grid.cell_of(x, y)
                tiles.setdefault((cx, cy), []).append(entry(o, rel, r, lp or (
                    shape.replace(s.prefix, f"/levels/{LEVEL}/") if shape else None)))
                stats["streamed"] += 1
            else:
                if lp:
                    o = dict(o, shapeName=lp)
                kept.setdefault(path, []).append(o)
    return own_shapes


def clip_box(o, core):
    """A WaterBlock (position = centre, scale = size, no rotation) cut to the core; None if nothing is left."""
    if o.get("rotationMatrix") not in (None, [1, 0, 0, 0, 1, 0, 0, 0, 1]):
        return o
    (cx, cy, cz), (sx, sy, sz) = o["position"], o["scale"]
    x0, y0, x1, y1 = max(cx - sx / 2, core[0]), max(cy - sy / 2, core[1]), min(cx + sx / 2, core[2]), min(cy + sy / 2, core[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return dict(o, position=[round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3), cz],
                scale=[round(x1 - x0, 3), round(y1 - y0, 3), sz])


# ------------------------------------------------------------------ forest
def forest_zone(grid, s, types, tiles, item_data):
    """The zone's forest items in its core into tiles {(cx, cy): [rows]}; rows [type, x, y, z, yaw deg, scale]."""
    p = os.path.join(s.dir, "art", "forest", "managedItemData.json")
    if os.path.exists(p):
        for k, v in json.load(open(p)).items():
            if k not in item_data:
                item_data[k] = json.loads(json.dumps(v).replace(s.prefix, f"/levels/{LEVEL}/"))
    fdir = os.path.join(s.dir, "forest")
    n = 0
    if not os.path.isdir(fdir):
        return 0
    for fn in sorted(os.listdir(fdir)):
        if not fn.endswith(".forest4.json"):
            continue
        for it in read_ndjson(os.path.join(fdir, fn)):
            x, y, z = it["pos"]
            if not s.in_core(x, y):
                continue
            t = it["type"]
            if t not in types:
                types[t] = len(types)
            R = it.get("rotationMatrix") or [1, 0, 0, 0, 1, 0, 0, 0, 1]
            yaw = math.degrees(math.atan2(R[1], R[0]))
            sc = it.get("scale", 1)
            sc = sc[0] if isinstance(sc, list) else sc
            cx, cy = grid.cell_of(x, y)
            tiles.setdefault((cx, cy), []).append([types[t], round(x, 2), round(y, 2), round(z, 3), round(yaw, 1),
                                                   round(float(sc), 3)])
            n += 1
    return n


# ------------------------------------------------------------------ the level's shared files
def copy_shared(srcs, dst, skip_shapes):
    """art/ and the other files of every zone (the first zone's copy of a path wins; material files merged by name),
    level paths rewritten; the shapes in skip_shapes (written under z/) and the per-zone files left out."""
    seen = set()
    mats = collections.defaultdict(dict)
    n = 0
    for s in srcs:
        skip = {s.path(p) for p in skip_shapes.get(s.name, ())}
        for dp, dns, fs in os.walk(s.dir):
            rel_dir = os.path.relpath(dp, s.dir).replace(os.sep, "/")
            if rel_dir == ".":
                dns[:] = [d for d in dns if d not in ("main", "forest")]
            for fn in fs:
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, s.dir).replace(os.sep, "/")
                if p in skip or rel in SKIP_FILES or rel.startswith("art/terrains/") or fn.endswith((".ter", ".jpg")) \
                        or rel == "art/forest/managedItemData.json" or rel == "info.json":
                    continue
                if fn.endswith(".materials.json") or fn == "materials.json":
                    for k, v in json.load(open(p, encoding="utf-8")).items():
                        mats[rel].setdefault(k, json.loads(json.dumps(v).replace(s.prefix, f"/levels/{LEVEL}/")))
                    continue
                if rel in seen:
                    continue
                seen.add(rel)
                q = os.path.join(dst, *rel.split("/"))
                if fn.lower().endswith(blocks.TEXT_EXT):
                    data = open(p, "rb").read()
                    if s.prefix.encode() in data:
                        with wopen(q, "wb") as f:
                            f.write(data.replace(s.prefix.encode(), f"/levels/{LEVEL}/".encode()))
                        n += 1
                        continue
                link_or_copy(p, q)
                n += 1
    for rel, d in mats.items():
        with wopen(os.path.join(dst, *rel.split("/")), "w") as f:
            json.dump(d, f, indent=1)
    log("shared files:", n, "material files:", len(mats))


def merge_kept(kept_by_zone):
    """{group path: [objects]}: every zone's objects; the ones each zone has alike (sky, ground cover, wind) once."""
    out = {}
    names = collections.defaultdict(set)
    for kept in kept_by_zone:
        for path, objs in kept.items():
            lst = out.setdefault(path, [])
            for o in objs:
                cls = o.get("class")
                if cls in ("LevelInfo", "ScatterSky", "TimeOfDay", "CloudLayer", "GroundCover", "ForestWindEmitter",
                           "SimGroup"):
                    if o.get("name") in names[path]:
                        continue
                    names[path].add(o.get("name"))
                lst.append(o)
    return out


def write_scene(kept, dst, tb_new):
    main = os.path.join(dst, "main")
    shutil.rmtree(main, ignore_errors=True)
    groups = set(kept) | {".", "MissionGroup", "MissionGroup/level_objects", "MissionGroup/level_objects/terrain"}
    for p in list(groups):
        parts = p.split("/")
        for i in range(1, len(parts)):
            groups.add("/".join(parts[:i]))
    for path in sorted(groups):
        objs = [o for o in kept.get(path, []) if o.get("class") != "SimGroup"]
        if path.endswith("level_objects/terrain"):
            objs = [tb_new] + [o for o in objs if o.get("class") != "TerrainBlock"]
        children = sorted({g.split("/")[len(path.split("/"))] for g in groups
                           if g.startswith(path + "/") and g != path}) if path != "." else ["MissionGroup"]
        lines = [{"name": c, "class": "SimGroup", "__parent": path.split("/")[-1]} for c in children
                 if path != "."]
        d = os.path.join(main, *path.split("/")) if path != "." else main
        with wopen(os.path.join(d, "items.level.json"), "w", encoding="utf-8") as f:
            if path == ".":
                f.write(json.dumps({"name": "MissionGroup", "class": "SimGroup", "enabled": "1"}) + "\n")
            for o in lines + objs:
                f.write(json.dumps(o, separators=(",", ":")) + "\n")


# ------------------------------------------------------------------ roads, signals, sites
def net_report(srcs, roads):
    """Welds the cut roads across the core edges (region_net.weld) and returns the AI network as the traffic sees
    it before (region.py's first cut: one node beyond the edge) and after."""
    before = []
    for s in srcs:
        stale = region_net.stale_cantonale([o for objs in s.scene.values() for o in objs], s, s.grid)
        for path, objs in s.scene.items():
            for o in objs:
                if region_net.is_ai(o) and not (stale and region_net.is_cantonale(o.get("name", ""))):
                    before.extend(region_net.old_cut(o, s))
    rep = {"ai_before": region_net.graph_report(before)}
    rep["weld"] = region_net.weld([(o, z, c0, c1) for _, o, z, c0, c1 in roads])
    rep["ai_after"] = region_net.graph_report([o for _, o, _, _, _ in roads if region_net.is_ai(o)])
    for k in ("ai_before", "weld", "ai_after"):
        log(k, rep[k])
    return rep


def write_spots(srcs, dst):
    """signals.json, the sites files and main.decals.json of the region, each spot from its zone's core."""
    rep = {}
    sig, rep["signals"] = region_net.merge_signals(srcs)
    with wopen(os.path.join(dst, "signals.json"), "w") as f:
        json.dump(sig, f, indent=1)
    defs = next((os.path.join(s.dir, "signalControllerDefinitions.json") for s in srcs
                 if os.path.exists(os.path.join(s.dir, "signalControllerDefinitions.json"))), None)
    if defs:
        link_or_copy(defs, os.path.join(dst, "signalControllerDefinitions.json"))
    for fn in ("city.sites.json", "facilities.sites.json"):
        d, rep[fn] = region_net.merge_sites(srcs, fn, LEVEL)
        if d is not None:
            with wopen(os.path.join(dst, fn), "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1)
    dec, rep["decals"] = region_net.merge_decals(srcs)
    with wopen(os.path.join(dst, "main.decals.json"), "w") as f:
        json.dump(dec, f)
    for k in ("signals", "city.sites.json", "facilities.sites.json", "decals"):
        log(k, rep[k])
    return rep


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zones", nargs="+", required=True)
    ap.add_argument("--src", required=True, help="folder with levels/<zone>/ of every zone (unpacked zone zips)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-collision-cells", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    grid = blocks.Zone(json.load(open(GRID_CFG)))
    srcs = [Src(z, a.src, grid) for z in a.zones]
    dst = os.path.join(a.out, "levels", LEVEL)
    for d in ("blocks", "tiles", "col", "far", "z", "main", "art/terrains/w"):
        shutil.rmtree(os.path.join(dst, *d.split("/")), ignore_errors=True)
    Z0, MAXH = height_scale(srcs)
    layers = layer_list(srcs)
    log("zones:", [s.name for s in srcs], "heights %.0f + %.0f m," % (Z0, MAXH), len(layers), "terrain layers")

    owner = write_blocks(grid, srcs, Z0, MAXH, layers, os.path.join(dst, "blocks", "terrain"))
    base_keys = write_base_maps(grid, owner, srcs, os.path.join(dst, "blocks", "base"))

    tiles, kept_by_zone, own = {}, [], {}
    stats = collections.Counter()
    roads = []
    for s in srcs:
        kept, zs = {}, collections.Counter()
        own[s.name] = stream_zone(grid, s, dst, tiles, kept, zs, roads)
        kept_by_zone.append(kept)
        stats.update(zs)
        log("objects of", s.name, dict(zs))
    report = net_report(srcs, roads)
    for path, o, z, _, _ in roads:
        kept_by_zone[[s.name for s in srcs].index(z)].setdefault(path, []).append(o)
    ftypes, ftiles, item_data = {}, {}, {}
    nf = sum(forest_zone(grid, s, ftypes, ftiles, item_data) for s in srcs)
    for (cx, cy), rows in ftiles.items():
        with wopen(os.path.join(dst, "tiles", f"t_{cx}_{cy}.forest.json"), "w") as f:
            json.dump(rows, f, separators=(",", ":"))
    with wopen(os.path.join(dst, "art", "forest", "managedItemData.json"), "w") as f:
        json.dump(item_data, f, indent=1)
    log("forest items:", nf, "in", len(ftiles), "tiles,", len(ftypes), "types")

    copy_shared(srcs, dst, own)
    report.update(write_spots(srcs, dst))
    with wopen(os.path.join(a.out, "region_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    cells = None
    if not a.no_collision_cells:
        import collision
        cells = collision.build(grid, tiles, dst, LEVEL, os.path.join(dst, "col"), workers=a.workers)
        with wopen(os.path.join(dst, "col", "stats.json"), "w") as f:
            json.dump(cells[2], f, indent=1)
    for (cx, cy), objs in tiles.items():
        with wopen(os.path.join(dst, "tiles", f"o_{cx}_{cy}.json"), "w") as f:
            json.dump(objs, f, separators=(",", ":"))
    far = write_far(grid, owner, srcs, layers, os.path.join(dst, "far"))

    mats, frm = terrain_mats(srcs, layers)
    wm = window_materials(grid, mats, frm, set(base_keys), os.path.join(dst, "art", "terrains", "w"))
    with wopen(os.path.join(dst, "art", "terrains", "main.materials.json"), "w") as f:
        json.dump(wm, f, indent=1)

    kept = merge_kept(kept_by_zone)
    s0 = srcs[0]
    info = json.load(open(os.path.join(s0.dir, "info.json")))
    spawns = [o for objs in kept.values() for o in objs if o.get("class") == "SpawnSphere"]
    want = f"{s0.name}_{info.get('defaultSpawnPointName')}"
    sp = next((o for o in spawns if o.get("name") == want), spawns[0] if spawns else None)
    sx, sy = (sp["position"][0], sp["position"][1]) if sp else ((s0.core[0] + s0.core[2]) / 2, (s0.core[1] + s0.core[3]) / 2)
    wx, wy = grid.window_for(sx, sy)
    with wopen(os.path.join(dst, "start.ter"), "wb") as f:
        f.write(blocks.window_ter(grid, os.path.join(dst, "blocks", "terrain"), 0, wx, wy, layers))
    tb_new = dict(s0.tb)
    tb_new.pop("persistentId", None)
    tb_new["position"] = [grid.x0 + wx * grid.sq, grid.y0 + wy * grid.sq, Z0]
    tb_new["maxHeight"] = MAXH
    tb_new["terrainFile"] = f"/levels/{LEVEL}/start.ter"
    tb_new["materialTextureSet"] = LEVEL + "TerrainMaterialTextureSet"
    blocks.bng.write_terrain_json(os.path.join(dst, "start.terrain.json"), LEVEL, "start", grid.W, layers)
    write_scene(kept, dst, tb_new)

    info["title"] = "Ticino (" + ", ".join(s.name for s in srcs) + ")"
    info["description"] = "Ticino region test: " + ", ".join(s.name for s in srcs)
    info["size"] = [grid.W, grid.W]
    if sp:
        info["defaultSpawnPointName"] = sp["name"]
    with wopen(os.path.join(dst, "info.json"), "w") as f:
        json.dump(info, f, indent=2)

    stream = {
        "version": 2, "zone": "region:" + ",".join(s.name for s in srcs), "level": LEVEL,
        "origin": [grid.x0, grid.y0], "square": grid.sq, "z0": Z0, "maxHeight": MAXH,
        "block": grid.B, "cell": grid.C, "window": grid.W, "basePx": grid.SPP,
        "blocksPerSide": 0, "materials": layers,
        "baseTextures": base_keys,
        "baseMaterials": [[k, m["internalName"], os.path.splitext(os.path.basename(m["baseColorBaseTex"]))[0]]
                          for k, m in mats.items() if m.get("class") == "TerrainMaterial"
                          and os.path.splitext(os.path.basename(m["baseColorBaseTex"]))[0] in base_keys],
        "baseSizeUnit": grid.cfg.get("base_size_unit", "samples"),
        "tiles": {f"{cx}_{cy}": len(v) for (cx, cy), v in tiles.items()},
        "forestTiles": {f"{cx}_{cy}": len(v) for (cx, cy), v in ftiles.items()},
        "forestTypes": sorted(ftypes, key=ftypes.get),
        "far": far, "farRadius": int(grid.cfg.get("far_radius", 16)),
        "collisionRadius": int(grid.cfg.get("collision_radius", 1)),
        "colCell": blocks.collision_cell_m() if cells else None, "colCells": cells[0] if cells else [],
        "colGroundTypes": cells[1] if cells else [], "colPieceTris": blocks.collision_piece_tris(),
        "colRadius": int(grid.cfg.get("col_radius", 1)),
        "maxRadius": max(int(v["radius"]) for v in grid.cfg["groups"].values()),
        "start": [wx, wy],
    }
    with wopen(os.path.join(dst, "stream.json"), "w") as f:
        json.dump(stream, f, indent=1)
    log("done in %.0f s ->" % (time.time() - t0), dst, dict(stats))


if __name__ == "__main__":
    main()
