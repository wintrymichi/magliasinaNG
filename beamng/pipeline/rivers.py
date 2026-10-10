"""Water in the rivers (v2.4): the Magliasina, the Vedeggio, the Tresa below its weir and the other
streams the cadastral survey draws as surfaces ('corso_acqua').

Up to v2.3 the riverbeds were dry ground (terrain layer Gravel). Here every surveyed river surface
at least MIN_WIDTH m wide gets a thin, partly transparent water mesh (no collision: a car drives
into the bed as before):
- height: the lowest bare ground (swissALTI3D) within LOW_R m, smoothed, plus OVER m: on the larger
  rivers the laser model is the water surface itself (flat from bank to bank), on the stony torrents
  the water lies in the lowest channel;
- the terrain (a 1.5 m grid, smoother than the bed) is lowered DEPTH m under the water inside the river
  surfaces where it is at most CARVE_MAX m above the water (carve_terrain), else it would stand over
  most of it; not within FORD_KEEP m of the roads and paths at the level of the ground (a car on a
  1 m path across a stream has its wheels beside the path, on the terrain: there it stays as it was);
- not over the roads and paths that cross at the level of the water (fords), not over the lake (its
  water blocks, water.py); under the bridges it goes on;
- a material of its own: a dark green tint with LerpAlpha transparency, smooth (the sky reflects
  in it), ripples in a drawn normal map (nothing from a photograph).
The transparency and the look in the game could not be checked here.
v2.8: the water is written once the terrain is final (write) and cut to where it stands more than SHORE m
over it, on a 1.5 m mesh: on the torrents it ran in and out of the banks in triangles.
"""
import os
import numpy as np
import shapely
from scipy import ndimage as ndi
import bng
from bld_textures import noise, aniso_noise, normal_map, to8, save

MIN_WIDTH = 2.5         # m, mean width of a river surface (area / half perimeter) to get water
LOW_R = 3.0             # m, radius of the lowest ground under the water
OVER = 0.12             # m of water over that ground
CELL = 1.5              # m, mesh cell (v2.8: the terrain step, was 3 m; the water is cut where the terrain is over it)
SHORE = 0.06            # m, the water is left out where it is less than this over the terrain (v2.8)
FORD = 1.5              # m, a road surface less than this above the water crosses it at its level
DEPTH = 0.35            # m of terrain under the water
CARVE_MAX = 1.5         # m, terrain higher than this over the water (a bank in a gorge) is not lowered
FORD_KEEP = 2.5         # m around the roads and paths at the level of the ground: the terrain is not lowered
CHUNK = 128.0


def textures(dst, n=512):
    """Colour (flat tint) and normal (ripples) of the water; tiles over TILE_M m."""
    rng = np.random.default_rng(61)
    col = np.zeros((n, n, 3), np.float32)
    col[:] = (0.16, 0.22, 0.19)
    col *= (1 + 0.04 * noise(n, n, 40, rng))[..., None]
    save(os.path.join(dst, "t_river_b.color.png"), to8(np.clip(col, 0, 1)))
    h = 0.6 * noise(n, n, 6, rng) + 0.4 * aniso_noise(n, n, 2.0, 9.0, rng) + 0.2 * noise(n, n, 1.5, rng)
    save(os.path.join(dst, "t_river_nm.normal.png"), normal_map(h, 0.25))


TILE_M = 4.0


def material(level_name):
    t = f"/levels/{level_name}/art/shapes/water"
    # opacity both in the alpha of the base colour and as opacityFactor (materials v1.5)
    return bng.material("mp_river_water", f"{t}/t_river_b.color.png", f"{t}/t_river_nm.normal.png",
                        base_color=[1.0, 1.0, 1.0, 0.62], roughness=0.06, detail={"opacityFactor": 0.62},
                        extra={"translucent": True, "translucentBlendOp": "LerpAlpha", "translucentZWrite": False,
                               "castShadows": False})


def surfaces(av, lake_boxes, at_grade, crossings, road_z):
    """The water polygons: (list of polygons, statistics, the ground within FORD_KEEP m of the roads and
    paths that meet the water, where the terrain keeps its height).
    lake_boxes: polygons of the lake's water blocks (no river water over them); at_grade: road and
    path polygons at the level of the ground (the network outside the bridges: a ford or a culvert
    crossing, no water over them); crossings: polygons of the bridge decks and of the corridor's paved
    surfaces, where the survey's river stops (the land cover shows the deck): the water goes on under
    them unless the road there is less than FORD m above it (road_z: their surface height, NaN off)."""
    import area
    keep = area.polygon()
    polys = []
    for g, _ in av["LCSF"].get("corso_acqua", []):
        if not g.intersects(keep):
            continue
        for p in shapely.get_parts(g.intersection(keep)):
            if p.geom_type == "Polygon" and p.area > 20 and p.area / max(0.5 * p.length, 1e-6) >= MIN_WIDTH:
                polys.append(p)
    stats = {"surveyed": len(polys), "ha_surveyed": round(sum(p.area for p in polys) / 1e4, 1)}
    river = shapely.union_all(polys)
    # under the bridges: the gaps of the survey's river closed (up to 16 m), within the decks
    gaps = river.buffer(8.0, quad_segs=4).buffer(-8.0, quad_segs=4).difference(river)
    fill = gaps.intersection(shapely.union_all(crossings)) if crossings and not gaps.is_empty else shapely.Polygon()
    # the corridor's surfaces at the level of the water are fords: no water there
    low = []
    for c in crossings:
        x = c.intersection(river.union(fill))
        if x.is_empty or x.area < 0.5:
            continue
        q = x.representative_point()
        zr = road_z(np.array([q.x]), np.array([q.y]))[0]
        if np.isfinite(zr) and zr - water_z(np.array([q.x]), np.array([q.y]))[0] < FORD:
            low.append(c)
    water = river.union(fill)
    ground = at_grade + low
    cut = [shapely.union_all(lake_boxes).buffer(5.0)] if lake_boxes else []
    k0 = len(cut)
    cut += [g.buffer(0.3) for g in ground]
    keep = shapely.Polygon()
    if cut:
        tree = shapely.STRtree(cut)
        near = tree.query(water, predicate="intersects")
        if len(near):
            water = water.difference(shapely.union_all([cut[i] for i in near]))
            meet = [ground[i - k0] for i in near if i >= k0]
            if meet:
                keep = shapely.union_all([g.buffer(FORD_KEEP, quad_segs=4) for g in meet])
    out = [q for q in shapely.get_parts(water) if q.geom_type == "Polygon" and q.area > 5]
    stats.update(polygons=len(out), ha=round(sum(p.area for p in out) / 1e4, 1),
                 under_bridges_m2=round(float(fill.area), 0), fords=len(low))
    return out, stats, keep


_water = {}


def water_z(x, y):
    """Height of the water surface at points: the lowest bare ground within LOW_R m (on a 1 m grid
    around them, smoothed) + OVER."""
    from geo import Grid
    from config import WORK
    if "dtm" not in _water:
        _water["dtm"] = Grid.load(os.path.join(WORK, "dtm05.npz"))
    dtm = _water["dtm"]
    x = np.atleast_1d(np.asarray(x, np.float64))
    y = np.atleast_1d(np.asarray(y, np.float64))
    out = np.empty(len(x))
    # windows of 64 m: the low-ground field of each, cached
    kx, ky = np.floor(x / 64.0).astype(int), np.floor(y / 64.0).astype(int)
    for key in set(zip(kx.tolist(), ky.tolist())):
        m = (kx == key[0]) & (ky == key[1])
        if key not in _water:
            x0, y0 = key[0] * 64.0 - 8, key[1] * 64.0 - 8
            sub, _, _ = dtm.window(x0, y0, x0 + 80, y0 + 80, pad=2)
            a = np.asarray(sub.a, np.float32)
            k = int(round(2 * LOW_R / sub.res)) | 1
            lo = ndi.minimum_filter(a, size=k)
            lo = ndi.gaussian_filter(lo, 1.5 / sub.res)
            _water[key] = Grid(lo, sub.x_min, sub.y_max, sub.res)
            if len(_water) > 400:
                for kk in [k_ for k_ in _water if k_ != "dtm"][:200]:
                    del _water[kk]
        out[m] = _water[key].sample(x[m], y[m]) + OVER
    return out


def carve_terrain(H, xs, ys, polys):
    """The terrain heights H (rows ys, columns xs: the vertex grid) lowered to DEPTH m under the water
    at the vertices inside the river surfaces, but those more than CARVE_MAX m above the water (the
    steep banks of a gorge that the surveyed surface takes in)."""
    n = 0
    for p in polys:
        x0, y0, x1, y1 = p.bounds
        c0, c1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
        r0, r1 = np.searchsorted(ys, y0), np.searchsorted(ys, y1)
        if c1 <= c0 or r1 <= r0:
            continue
        X, Y = np.meshgrid(xs[c0:c1], ys[r0:r1])
        ins = shapely.contains_xy(p, X, Y)
        if not ins.any():
            continue
        rr, cc = np.nonzero(ins)
        zw = water_z(X[ins], Y[ins])
        cur = H[r0 + rr, c0 + cc]
        # a vertex on a steep bank inside the surveyed surface (a gorge) stays: only the bed goes down
        ok = cur - zw <= CARVE_MAX
        H[r0 + rr[ok], c0 + cc[ok]] = np.minimum(cur[ok], zw[ok] - DEPTH)
        n += int(ok.sum())
    print("rivers: terrain lowered under the water at %d vertices" % n, flush=True)
    return H


def build(level_dir, level_name, scene, av, lake_boxes, at_grade, crossings, road_z,
          group="MissionGroup/level_objects/Water"):
    """Meshes of the river water per CHUNK m chunk, textures and material; returns (statistics, the
    polygons where the terrain goes under the water: the water's but within FORD_KEEP m of the roads)."""
    import road_mesh
    polys, stats, keep = surfaces(av, lake_boxes, at_grade, crossings, road_z)
    d = os.path.join(level_dir, "art", "shapes", "water")
    os.makedirs(d, exist_ok=True)
    textures(d)
    bng.write_materials(os.path.join(d, "rivers.materials.json"), [material(level_name)])
    builders = {}
    zf = lambda x, y, *_: water_z(x, y)
    for p in polys:
        x0, y0, x1, y1 = p.bounds
        for tx in range(int(np.floor(x0 / CHUNK)), int(np.floor(x1 / CHUNK)) + 1):
            for ty in range(int(np.floor(y0 / CHUNK)), int(np.floor(y1 / CHUNK)) + 1):
                piece = road_mesh.polygonal(p.intersection(shapely.box(tx * CHUNK, ty * CHUNK, (tx + 1) * CHUNK,
                                                                      (ty + 1) * CHUNK)))
                if piece.is_empty or piece.area < 1.0:
                    continue
                V, T = road_mesh.mesh_polygon(piece, zf, cell=CELL)
                if not len(T) or not np.isfinite(V[:, 2]).all():
                    continue
                builders.setdefault((tx, ty), []).append(V[T])
    meshes = {k: np.concatenate(v) for k, v in builders.items()}
    stats.update(chunks=len(meshes), triangles_before_trim=int(sum(len(m) for m in meshes.values())))
    bed = [q for p in polys for q in shapely.get_parts(p.difference(keep) if not keep.is_empty else p)
           if q.geom_type == "Polygon" and q.area > 1.0]
    stats["ha_bed_lowered"] = round(sum(q.area for q in bed) / 1e4, 1)
    return stats, bed, meshes


def terrain_at(H, xs, ys, x, y):
    """Height of the terrain (vertex heights H, rows ys, columns xs) at points, on its triangles: the
    diagonal of every square alternates as the game splits them (walls.build_backfill)."""
    sq = xs[1] - xs[0]
    c, r = (x - xs[0]) / sq, (y - ys[0]) / sq
    c0 = np.clip(np.floor(c).astype(np.int64), 0, len(xs) - 2)
    r0 = np.clip(np.floor(r).astype(np.int64), 0, len(ys) - 2)
    fx, fy = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
    h00, h10, h01, h11 = H[r0, c0], H[r0, c0 + 1], H[r0 + 1, c0], H[r0 + 1, c0 + 1]
    even = ((r0 ^ c0) & 1) == 0
    # even squares split along 00-11, odd ones along 10-01
    a = np.where(fx >= fy, h00 + fx * (h10 - h00) + fy * (h11 - h10), h00 + fy * (h01 - h00) + fx * (h11 - h01))
    b = np.where(fx + fy <= 1, h00 + fx * (h10 - h00) + fy * (h01 - h00),
                 h11 + (1 - fx) * (h01 - h11) + (1 - fy) * (h10 - h11))
    return np.where(even, a, b)


def clip_above(T, d):
    """The parts of the triangles T (k, 3, 3) where the linear field d (k, 3, at their corners) is positive:
    (m, 3, 3) triangles, the shore cut straight across every triangle (marching triangles)."""
    pos = d > 0
    n = pos.sum(1)
    out = [T[n == 3]]
    for want in (1, 2):
        sel = np.flatnonzero(n == want)
        if not len(sel):
            continue
        t, dd, pp = T[sel], d[sel], pos[sel]
        # rotate every triangle so that its odd corner (the single positive one, or the single negative one)
        # comes first, keeping the winding
        odd = np.argmax(pp if want == 1 else ~pp, axis=1)
        idx = (odd[:, None] + np.arange(3)[None]) % 3
        ar = np.arange(len(sel))[:, None]
        t, dd = t[ar, idx], dd[ar, idx]
        f1 = (dd[:, 0] / (dd[:, 0] - dd[:, 1]))[:, None]
        f2 = (dd[:, 0] / (dd[:, 0] - dd[:, 2]))[:, None]
        p1 = t[:, 0] + f1 * (t[:, 1] - t[:, 0])
        p2 = t[:, 0] + f2 * (t[:, 2] - t[:, 0])
        if want == 1:
            out.append(np.stack([t[:, 0], p1, p2], 1))
        else:
            out.append(np.stack([p1, t[:, 1], t[:, 2]], 1))
            out.append(np.stack([p1, t[:, 2], p2], 1))
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def write(level_dir, level_name, scene, meshes, H, xs, ys, group="MissionGroup/level_objects/Water"):
    """The river meshes (build) written once the terrain is final (v2.8): every triangle cut to the part
    more than SHORE m over the terrain. Up to v2.8 the whole surface was drawn: on the banks of the
    torrents (the Magliasina) the water ran in and out of the terrain in triangles, a fifth of it under the
    ground and much of the rest within a few centimetres of it."""
    ntri, kept_m2, cut_m2 = 0, 0.0, 0.0
    for (tx, ty), T in sorted(meshes.items()):
        d = T[:, :, 2] - terrain_at(H, xs, ys, T[:, :, 0].ravel(), T[:, :, 1].ravel()).reshape(-1, 3) - SHORE
        area = lambda A: float(0.5 * np.linalg.norm(np.cross(A[:, 1] - A[:, 0], A[:, 2] - A[:, 0]), axis=1).sum())
        a0 = area(T)
        T = clip_above(T, d)
        T = T[0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) > 1e-3]
        a1 = area(T) if len(T) else 0.0
        kept_m2 += a1
        cut_m2 += a0 - a1
        if not len(T):
            continue
        V = T.reshape(-1, 3)
        mb = bng.MeshBuilder()
        mb.add("mp_river_water", V, uvs=V[:, :2] / TILE_M, normals=np.repeat([[0.0, 0.0, 1.0]], len(V), 0))
        rel = f"art/shapes/water/river_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name=f"river_{tx}_{ty}", origin=origin)
        ntri += mb.triangle_count()
        scene.add(group, bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=False))
    print("rivers: %d triangles, %.1f ha of water, %.1f ha under or at the terrain left out"
          % (ntri, kept_m2 / 1e4, cut_m2 / 1e4), flush=True)
    return ntri
