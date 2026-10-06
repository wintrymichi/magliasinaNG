"""The piers of the lake and the boats moored at them (v2.8), in a built level zip.

Up to v2.7 the shore of the Lake of Lugano had no pier: the lidos, the boat clubs and the landing stages
of the boats ended at the water. OpenStreetMap maps them (man_made=pier, lines and areas); here every pier
on the Swiss side is built over the water as the level has it (the WaterBlocks LagoDiLugano):
- a fixed pier (floating not set): a deck of planks DECK_FIXED m over the water, its beams, and square
  wooden posts every POST_STEP m on both sides down into the lake bed; a floating one (floating=yes):
  a deck DECK_FLOAT m over the water on dark floats reaching FLOAT_DRAFT m under it, held by steel guide
  piles every PILE_STEP m; width from the OSM width tag, else WIDTH_FIXED / WIDTH_FLOAT m;
- only where the ground is under the deck: a pier mapped from the shore starts where the bank drops
  under it (the part on land is a path or a lawn already);
- boats at the piers where boats moor (a mooring tag, or a floating pier of MOORING_MIN m or more): one
  every BOAT_STEP m on both sides, bow to the pier, a slot left empty now and then, where the water is
  BOAT_DEPTH m deep or more under the whole boat and nothing else stands; motor boats under a cover or
  open with an outboard, and some sailing boats with their mast, 4.5-8 m long, drawn here (low-poly,
  plain colours), the same every build (seeded by the OSM id of the pier).
Meshes in TILE m tiles (MissionGroup/props/lake): the piers with collision (drawn up to PIER_DRAW m), the boats
with collision (up to BOAT_DRAW m); the planks are a texture drawn here (no photo). Nothing on the
Italian side (outside the communes of the Swiss survey). Everything else is copied as it is.

Usage: python patch_lake.py <in.zip> <out.zip> [--report <json>]
(c) OpenStreetMap contributors, ODbL.
"""
import argparse, io, json, math, os, re, sys, time, zipfile
import numpy as np
import shapely
import shapely.ops
from PIL import Image
import bng
import optimize_level
import osm
import patch_lamps as pl
import patch_roadside as pr
import patch_unpaved as pu
import patch_wall_fill as pw
import signs_net as sn
from config import LEVEL_NAME

TILE = 512.0
DECK_FIXED, DECK_FLOAT = 0.75, 0.40       # m over the water
DECK_T = 0.22                             # m, planks and beams
WIDTH_FIXED, WIDTH_FLOAT = 2.0, 2.4       # m, where OSM has no width
POST_STEP, POST_W = 3.0, 0.16             # m
FLOAT_DRAFT, FLOAT_INSET = 0.30, 0.15     # m
PILE_STEP, PILE_R, PILE_UP = 12.0, 0.14, 1.6
MOORING_MIN = 40.0                        # m, a floating pier this long is a marina pontoon
BOAT_STEP, BOAT_FIRST, BOAT_DEPTH = 3.0, 6.0, 0.6
PIER_DRAW, BOAT_DRAW = 600.0, 400.0       # m
PLANK = 0.15                              # m, board width (the texture covers 1 m)


# ------------------------------------------------------------------ the level
def water_level(zi, lv):
    for f in zi.namelist():
        if f.startswith(f"{lv}/main/") and f.endswith("items.level.json"):
            for o in pl.read_items(zi, f):
                if o.get("class") == "WaterBlock" and str(o.get("name", "")).startswith("LagoDiLugano"):
                    return float(o["position"][2])
    raise SystemExit("no WaterBlock LagoDiLugano in the level")


def terrain(zi, lv):
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    return lambda x, y: pu.terrain_top(q, np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))


# ------------------------------------------------------------------ geometry
def prism(poly, z0, z1):
    """Triangles (k, 3, 3) of a polygon extruded from z0 to z1: top, bottom and sides."""
    tri = []
    for t in shapely.constrained_delaunay_triangles(poly).geoms:
        p = np.asarray(t.exterior.coords)[:3]
        if (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1]) < 0:
            p = p[::-1]                                       # counter-clockwise from above
        tri.append(np.column_stack([p, np.full(3, z1)]))
        tri.append(np.column_stack([p[::-1], np.full(3, z0)]))
    for ring in [poly.exterior] + list(poly.interiors):
        c = np.asarray(ring.coords)
        if not ring.is_ccw ^ (ring is not poly.exterior):
            c = c[::-1]
        for a, b in zip(c[:-1], c[1:]):
            A0, B0, A1, B1 = np.r_[a, z0], np.r_[b, z0], np.r_[a, z1], np.r_[b, z1]
            tri += [np.array([A0, B0, B1]), np.array([A0, B1, A1])]
    return np.array(tri)


def rect(c, u, half):
    """The rectangle centred at c (2,), its long axis u, half sizes (along, across)."""
    n = np.array([-u[1], u[0]])
    return shapely.Polygon([c + u * half[0] + n * half[1], c - u * half[0] + n * half[1],
                            c - u * half[0] - n * half[1], c + u * half[0] - n * half[1]])


def box(c, u, half, z0, z1):
    """A box centred at c (2,), its long axis u, half sizes (along, across), from z0 to z1."""
    return prism(rect(c, u, half), z0, z1)


def tube(c, r, z0, z1, n=8):
    a = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    return prism(shapely.Polygon(c + r * np.column_stack([np.cos(a), np.sin(a)])), z0, z1)


def plank_texture(size=256):
    """Weathered boards across the deck, PLANK m wide over 1 m of texture, drawn here (no photo)."""
    rng = np.random.default_rng(7)
    img = np.zeros((size, size, 3), np.float32)
    nb = int(round(1.0 / PLANK))
    edges = np.linspace(0, size, nb + 1).astype(int)
    base = np.array([128, 112, 92], np.float32)
    for a, b in zip(edges[:-1], edges[1:]):
        tone = base * rng.uniform(0.86, 1.10) + rng.uniform(-6, 6, 3)
        grain = rng.normal(0, 5, (size, 1)) * np.ones((1, b - a))
        img[:, a:b] = tone + grain[:, :, None] + rng.normal(0, 3, (size, b - a, 3))
        img[:, a:a + 2] *= 0.45                              # the gap between two boards
        for y in rng.integers(0, size, 2):                   # board ends
            img[y:y + 2, a:b] *= 0.55
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


# ------------------------------------------------------------------ boats
WHITE, BLUE, GREY, BEIGE, DARK, METAL, INSIDE = ("mp_boat_white", "mp_boat_blue", "mp_boat_grey", "mp_boat_beige",
                                                 "mp_boat_dark", "mp_boat_metal", "mp_boat_inside")


def hull(L, W):
    """(hull triangles, gunwale points (k, 2, 3) left / right) of a boat along +x (stern at -L/2), y across."""
    t = np.array([0.0, 0.15, 0.55, 0.80, 0.93, 1.0])
    hw = np.array([0.92, 1.0, 1.0, 0.80, 0.45, 0.04]) * W / 2
    zg = np.array([0.55, 0.56, 0.60, 0.66, 0.72, 0.78])
    zc = np.array([0.00, 0.00, 0.02, 0.10, 0.25, 0.55])
    zk = np.array([-0.22, -0.25, -0.25, -0.18, -0.05, 0.45])
    x = -L / 2 + t * L
    S = [np.array([[x[i], hw[i], zg[i]], [x[i], 0.9 * hw[i], zc[i]], [x[i], 0, zk[i]],
                   [x[i], -0.9 * hw[i], zc[i]], [x[i], -hw[i], zg[i]]]) for i in range(len(t))]
    tri = []
    for a, b in zip(S[:-1], S[1:]):
        for j in range(4):
            tri += [np.array([a[j], b[j + 1], a[j + 1]]), np.array([a[j], b[j], b[j + 1]])]      # facing out
    s0 = S[0]
    for j in range(1, 4):                                    # the transom
        tri.append(np.array([s0[0], s0[j], s0[j + 1]]))
    G = np.array([[s[0], s[4]] for s in S])
    return np.array(tri), G


def boat(L, W, kind, cover):
    """[(material, triangles)] of a boat in its own frame (x along it, bow at +L/2, z from the water)."""
    H, G = hull(L, W)
    parts = [(WHITE, H)]
    top = []
    if kind == "covered":                                   # a cover over the cockpit, raised in the middle
        mid = np.column_stack([G[:, 0, 0], np.zeros(len(G)), G[:, 0, 2] + 0.22])
        for i in range(len(G) - 1):
            l0, r0, l1, r1, m0, m1 = G[i, 0], G[i, 1], G[i + 1, 0], G[i + 1, 1], mid[i], mid[i + 1]
            top += [np.array([l0, m1, l1]), np.array([l0, m0, m1]), np.array([m0, r1, m1]), np.array([m0, r0, r1])]
        parts.append((cover, np.array(top)))
    else:                                                   # open: the floor of the cockpit, its sides inside
        fl = G.copy()
        fl[:, :, 2] -= 0.30
        fl[:, :, 1] *= 0.92
        for i in range(len(G) - 1):
            top += [np.array([fl[i, 1], fl[i + 1, 0], fl[i, 0]]), np.array([fl[i, 1], fl[i + 1, 1], fl[i + 1, 0]])]
            for s in (0, 1):
                a, b, c_, d = G[i, s], G[i + 1, s], fl[i + 1, s], fl[i, s]
                top += [np.array([a, c_, b]), np.array([a, d, c_])] if s == 0 else [np.array([a, b, c_]), np.array([a, c_, d])]
        parts.append((INSIDE, np.array(top)))
        if kind == "sail":                                  # a cabin, the mast and the boom
            parts.append((WHITE, box(np.array([0.05 * L, 0.0]), np.array([1.0, 0.0]), (0.22 * L, 0.32 * W),
                                     G[2, 0, 2] - 0.2, G[2, 0, 2] + 0.45)))
            parts.append((METAL, tube(np.array([0.30 * L, 0.0]), 0.05, G[2, 0, 2], G[2, 0, 2] + 1.25 * L, 6)))
            parts.append((cover, box(np.array([0.05 * L, 0.0]), np.array([1.0, 0.0]), (0.24 * L, 0.06),
                                     G[2, 0, 2] + 0.85, G[2, 0, 2] + 1.05)))
        else:                                               # an outboard motor on the transom
            parts.append((DARK, box(np.array([-L / 2 - 0.10, 0.0]), np.array([1.0, 0.0]), (0.10, 0.13),
                                    -0.30, G[0, 0, 2] + 0.22)))
    return parts


def place(parts, c, u, z):
    """The parts of a boat turned to u (2,) and moved to c (2,), at the water level z."""
    n = np.array([-u[1], u[0]])
    R = np.array([[u[0], n[0]], [u[1], n[1]]])
    out = []
    for mat, T in parts:
        V = T.reshape(-1, 3).copy()
        V[:, :2] = V[:, :2] @ R.T + c
        V[:, 2] += z
        out.append((mat, V.reshape(-1, 3, 3)))
    return out


# ------------------------------------------------------------------ the piers
def piers(cx_swiss):
    ways, _ = osm.load()
    out = []
    for w in ways:
        t = w["tags"]
        if t.get("man_made") != "pier" or not cx_swiss.contains(w["line"].centroid):
            continue
        closed = w["nodes"][0] == w["nodes"][-1] and len(w["xy"]) >= 4
        floating = t.get("floating") == "yes"
        width = None
        try:
            width = float(str(t.get("width", "")).replace("m", "").strip())
        except ValueError:
            pass
        width = width or (WIDTH_FLOAT if floating else WIDTH_FIXED)
        moor = t.get("mooring") not in (None, "no") or (floating and not closed and w["line"].length >= MOORING_MIN)
        out.append({"id": w["id"], "xy": np.asarray(w["xy"]), "closed": closed, "floating": floating, "width": width,
                    "mooring": moor, "line": w["line"]})
    return out


def build_pier(p, wl, ground):
    """[(material, triangles)], footprint polygon, kept axis (LineString or None) of one pier."""
    deck = wl + (DECK_FLOAT if p["floating"] else DECK_FIXED)
    if p["closed"]:
        poly, axis = shapely.Polygon(p["xy"]).buffer(0), None
    else:
        line = p["line"]
        # from the land end: the pier starts where the bank drops under the deck
        s = np.arange(0.0, line.length + 0.01, 0.5)
        Q = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
        zt = ground(Q[:, 0], Q[:, 1])
        if zt[0] < zt[-1]:
            line = shapely.LineString(np.asarray(line.coords)[::-1])
            zt = zt[::-1]
        low = np.flatnonzero(zt < deck - 0.10)
        if not len(low):
            return [], None, None
        a = max(float(s[low[0]]) - 0.5, 0.0)
        if line.length - a < 2.0:
            return [], None, None
        axis = shapely.ops.substring(line, a, line.length)
        poly = axis.buffer(p["width"] / 2, cap_style="flat", join_style="mitre")
    if poly.is_empty or poly.area < 2.0:
        return [], None, None
    poly = shapely.simplify(poly, 0.02)
    parts = []
    T = prism(poly, deck - DECK_T, deck)
    up = (np.abs(T[:, :, 2] - deck) < 1e-9).all(1)
    # the deck's texture in the pier's frame: the boards across it
    if axis is not None:
        d = np.asarray(axis.coords[-1]) - np.asarray(axis.coords[0])
    else:
        r = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)
        e = np.diff(r[:3], axis=0)
        d = e[np.argmax(np.linalg.norm(e, axis=1))]
    d = d / max(np.linalg.norm(d), 1e-9)
    V = T[up].reshape(-1, 3)[:, :2]
    uv = np.column_stack([V @ d, V @ np.array([-d[1], d[0]])])
    parts.append(("mp_pier_deck", T[up], uv))
    parts.append(("mp_pier_beam", T[~up]))
    if p["floating"]:
        inner = poly.buffer(-FLOAT_INSET, join_style="mitre")
        if not inner.is_empty:
            for g in getattr(inner, "geoms", [inner]):
                parts.append(("mp_pier_float", prism(g, wl - FLOAT_DRAFT, deck - DECK_T)))
        if axis is not None:
            for k, s in enumerate(np.arange(PILE_STEP / 2, axis.length, PILE_STEP)):
                c = np.asarray(axis.interpolate(s).coords[0])
                d = np.asarray(axis.interpolate(min(s + 1, axis.length)).coords[0]) - c
                n = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-9)
                q = c + n * (p["width"] / 2 + PILE_R + 0.05) * (1 if k % 2 else -1)
                zb = float(ground([q[0]], [q[1]])[0])
                if zb < wl:
                    parts.append(("mp_pier_pile", tube(q, PILE_R, zb - 0.3, wl + PILE_UP)))
    elif axis is not None:
        for s in np.arange(0.3, axis.length, POST_STEP):
            c = np.asarray(axis.interpolate(s).coords[0])
            d = np.asarray(axis.interpolate(min(s + 1, axis.length)).coords[0]) - c
            d = d / max(np.linalg.norm(d), 1e-9)
            n = np.array([-d[1], d[0]])
            for side in (1, -1):
                q = c + n * side * (p["width"] / 2 - POST_W)
                zb = float(ground([q[0]], [q[1]])[0])
                if zb < deck - DECK_T - 0.05:
                    parts.append(("mp_pier_beam", box(q, d, (POST_W / 2, POST_W / 2), zb - 0.3, deck - DECK_T)))
    return parts, poly, axis


def boats_at(p, axis, wl, ground, blocked):
    """[(material, triangles)] of the boats moored at one pier, and their number."""
    rng = np.random.default_rng(p["id"] % (2 ** 32))
    out, n_b = [], 0
    for s in np.arange(BOAT_FIRST, axis.length - 1.0, BOAT_STEP):
        c = np.asarray(axis.interpolate(s).coords[0])
        d = np.asarray(axis.interpolate(min(s + 1, axis.length)).coords[0]) - c
        d = d / max(np.linalg.norm(d), 1e-9)
        n = np.array([-d[1], d[0]])
        for side in (1, -1):
            if rng.random() < 0.25:
                continue                                     # an empty berth
            r = rng.random()
            kind = "covered" if r < 0.55 else ("open" if r < 0.88 else "sail")
            L = rng.uniform(6.5, 8.0) if kind == "sail" else rng.uniform(4.5, 6.5)
            W = L * rng.uniform(0.36, 0.40)
            u = -n * side                                    # bow to the pier
            ctr = c + n * side * (p["width"] / 2 + 0.5 + L / 2)
            fp = rect(ctr, u, (L / 2 + 0.2, W / 2 + 0.2))
            P = np.array(fp.exterior.coords)
            P = np.vstack([P, ctr])
            if (ground(P[:, 0], P[:, 1]) > wl - BOAT_DEPTH).any() or blocked.intersects(fp):
                continue
            cover = (BLUE, GREY, BEIGE)[int(rng.integers(0, 3))]
            out += place(boat(L, W, kind, cover), ctr, u, wl)
            blocked = blocked.union(fp)
            n_b += 1
    return out, n_b, blocked


def main(src, dst, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    wl = water_level(zi, lv)
    ground = terrain(zi, lv)
    comm = sn.communes()
    swiss = shapely.union_all([g for _, g in comm])
    P = piers(swiss)
    print("water level %.2f m, %d piers mapped on the Swiss side" % (wl, len(P)), flush=True)
    built, rep = [], {"piers": 0, "piers_m": 0.0, "floating": 0, "fixed": 0, "not_over_water": 0, "boats": 0}
    pier_parts, boat_parts, polys = [], [], []
    for p in P:
        parts, poly, axis = build_pier(p, wl, ground)
        if not parts:
            rep["not_over_water"] += 1
            continue
        pier_parts.append(parts)
        polys.append(poly)
        built.append((p, poly, axis))
        rep["piers"] += 1
        rep["floating" if p["floating"] else "fixed"] += 1
        rep["piers_m"] += axis.length if axis is not None else poly.length / 2
    blocked = shapely.union_all(polys) if polys else shapely.GeometryCollection()
    for p, poly, axis in built:
        if p["mooring"] and axis is not None:
            b, nb, blocked = boats_at(p, axis, wl, ground, blocked)
            boat_parts.append(b)
            rep["boats"] += nb
    print("piers: %d (%d fixed, %d floating, %.0f m), %d not over the water; boats: %d"
          % (rep["piers"], rep["fixed"], rep["floating"], rep["piers_m"], rep["not_over_water"], rep["boats"]), flush=True)

    new_files, items = {}, []

    def write(groups, name, draw):
        tiles = {}
        for parts in groups:
            allv = np.concatenate([q[1].reshape(-1, 3) for q in parts])
            c = allv[:, :2].mean(0)
            key = (int(math.floor(c[0] / TILE)), int(math.floor(c[1] / TILE)))
            tiles.setdefault(key, []).extend(parts)
        for (tx, ty), ps in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            for q in ps:
                mat, V = q[0], q[1].reshape(-1, 3)
                uv = q[2] if len(q) > 2 else V[:, :2]
                mb.add(mat, V, uvs=uv, normals=bng.flat_normals_soup(V))
            allv = np.concatenate([q[1].reshape(-1, 3) for q in ps])
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / draw)))
            rel = f"art/shapes/lake/{name}_{tx:+03d}_{ty:+03d}.dae"
            tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"{name}_{os.getpid()}.dae")
            mb.write_dae(tmp, name=name, origin=origin, detail=detail, orient=True)
            new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
            os.remove(tmp)
            o = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=True)
            o["__parent"] = "lake"
            items.append(o)
        return len(tiles)
    nt_p = write(pier_parts, "lake_piers", PIER_DRAW)
    nt_b = write([b for b in boat_parts if b], "lake_boats", BOAT_DRAW)
    tex = f"/levels/{LEVEL_NAME}/art/shapes/lake/t_pier_planks_b.color.png"
    new_files[f"{lv}/art/shapes/lake/t_pier_planks_b.color.png"] = plank_texture()
    mats = [bng.material("mp_pier_deck", tex, roughness=0.85, ground_type="WOOD"),
            bng.material("mp_pier_beam", base_color=[0.30, 0.25, 0.19, 1], roughness=0.85, ground_type="WOOD"),
            bng.material("mp_pier_float", base_color=[0.16, 0.17, 0.17, 1], roughness=0.6),
            bng.material("mp_pier_pile", base_color=[0.42, 0.43, 0.44, 1], roughness=0.5, metallic=0.6,
                         ground_type="METAL"),
            bng.material(WHITE, base_color=[0.90, 0.90, 0.88, 1], roughness=0.35),
            bng.material(BLUE, base_color=[0.08, 0.16, 0.32, 1], roughness=0.7),
            bng.material(GREY, base_color=[0.50, 0.52, 0.54, 1], roughness=0.7),
            bng.material(BEIGE, base_color=[0.72, 0.66, 0.54, 1], roughness=0.7),
            bng.material(DARK, base_color=[0.08, 0.08, 0.09, 1], roughness=0.4),
            bng.material(METAL, base_color=[0.75, 0.76, 0.77, 1], roughness=0.3, metallic=0.9),
            bng.material(INSIDE, base_color=[0.78, 0.78, 0.76, 1], roughness=0.6, double_sided=True)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"lake_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/lake/lake.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    mg = f"{lv}/main/MissionGroup/props/items.level.json"
    group = {"name": "lake", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"}
    new_files[f"{lv}/main/MissionGroup/props/lake/items.level.json"] = pr.pl_write(items)
    root = pl.read_items(zi, mg)
    if any(o.get("name") == "lake" for o in root):
        raise SystemExit(f"{src} has a props/lake group already: run on a zip without the v2.8 lake")
    new_files[mg] = pr.pl_write(root + [group])
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type = zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            ni.external_attr = 0o644 << 16
            zo.writestr(ni, data)
    print("%s written in %.0f s: %d pier tiles, %d boat tiles" % (dst, time.time() - t0, nt_p, nt_b), flush=True)
    if report:
        rep.update({"source": os.path.basename(src), "water_level_m": round(wl, 3), "piers_m": round(rep["piers_m"]),
                    "pier_tiles": nt_p, "boat_tiles": nt_b,
                    "built": [{"osm": p["id"], "floating": p["floating"], "width_m": p["width"], "mooring": p["mooring"],
                               "centre": [round(v, 1) for v in poly.centroid.coords[0]],
                               "length_m": round(axis.length if axis is not None else poly.length / 2, 1)}
                              for p, poly, axis in built]})
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
