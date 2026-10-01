"""Water in the rivers (v2.4): the Magliasina, the Vedeggio, the Tresa below its weir and the other
streams the cadastral survey draws as surfaces ('corso_acqua').

Up to v2.3 the riverbeds were dry ground (terrain layer Gravel). Here every surveyed river surface
at least MIN_WIDTH m wide gets a thin, partly transparent water mesh (no collision: a car drives
into the bed as before):
- height: the lowest bare ground (swissALTI3D) within LOW_R m, smoothed, plus OVER m: on the larger
  rivers the laser model is the water surface itself (flat from bank to bank), on the stony torrents
  the water lies in the lowest channel;
- the terrain (a 1.5 m grid, smoother than the bed) is lowered DEPTH m under the water inside the river
  surfaces (carve_terrain), else it would stand over most of it;
- not over the roads and paths that cross at the level of the water (fords), not over the lake (its
  water blocks, water.py); under the bridges it goes on;
- a material of its own: a dark green tint with LerpAlpha transparency, smooth (the sky reflects
  in it), ripples in a drawn normal map (nothing from a photograph).
The transparency and the look in the game could not be checked here.
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
CELL = 3.0              # m, mesh cell
FORD = 1.5              # m, a road surface less than this above the water crosses it at its level
DEPTH = 0.35            # m of terrain under the water
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
    return bng.material("mp_river_water", f"{t}/t_river_b.color.png", f"{t}/t_river_nm.normal.png",
                        base_color=[1.0, 1.0, 1.0, 0.62], roughness=0.06,
                        extra={"translucent": True, "translucentBlendOp": "LerpAlpha", "translucentZWrite": False,
                               "castShadows": False})


def surfaces(av, lake_boxes, at_grade, crossings, road_z):
    """The water polygons: (list of polygons, statistics).
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
    cut = [shapely.union_all(lake_boxes).buffer(5.0)] if lake_boxes else []
    cut += [g.buffer(0.3) for g in at_grade + low]
    if cut:
        tree = shapely.STRtree(cut)
        near = tree.query(water, predicate="intersects")
        if len(near):
            water = water.difference(shapely.union_all([cut[i] for i in near]))
    out = [q for q in shapely.get_parts(water) if q.geom_type == "Polygon" and q.area > 5]
    stats.update(polygons=len(out), ha=round(sum(p.area for p in out) / 1e4, 1),
                 under_bridges_m2=round(float(fill.area), 0), fords=len(low))
    return out, stats


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
    at the vertices inside the river surfaces."""
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
        z = water_z(X[ins], Y[ins]) - DEPTH
        H[r0 + rr, c0 + cc] = np.minimum(H[r0 + rr, c0 + cc], z)
        n += len(rr)
    print("rivers: terrain lowered under the water at %d vertices" % n, flush=True)
    return H


def build(level_dir, level_name, scene, av, lake_boxes, at_grade, crossings, road_z,
          group="MissionGroup/level_objects/Water"):
    """Meshes of the river water per CHUNK m chunk, textures and material; returns (statistics, polygons)."""
    import road_mesh
    polys, stats = surfaces(av, lake_boxes, at_grade, crossings, road_z)
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
                mb = builders.setdefault((tx, ty), bng.MeshBuilder())
                mb.add("mp_river_water", V, uvs=V[:, :2] / TILE_M, normals=np.repeat([[0.0, 0.0, 1.0]], len(V), 0),
                       tris=T)
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/water/river_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name=f"river_{tx}_{ty}", origin=origin)
        ntri += mb.triangle_count()
        scene.add(group, bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=False))
    stats.update(chunks=len(builders), triangles=ntri)
    return stats, polys
