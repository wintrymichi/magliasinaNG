"""Assemble the BeamNG level 'magliaso_pura' from the processed data.

Stages (each reads work/ products and writes into the level folder):
  terrain, sky/sun/water/level info, buildings, roads (+ markings, AI roads),
  walls, props (poles/signs/guardrails), vegetation, spawn points.
Run: python build_level.py [--reuse-roads] [stage ...]   (default: all)
  --reuse-roads: the road meshes of the previous build stay and stage_roads only reloads what the
  later stages need (work/roads_state.npz), to build the other stages again quickly.
"""
import json, math, os, shutil, sys, time
import numpy as np
from PIL import Image
from config import WORK, LEVEL_DIR, LEVEL_NAME, TER_SIZE, TER_SQUARE, TER_X0, TER_Y0
import bng

L = f"/levels/{LEVEL_NAME}"
Image.MAX_IMAGE_PIXELS = None


def level_path(*p):
    return os.path.join(LEVEL_DIR, *p)


# ------------------------------------------------------------------ helpers
def save_png(path, arr):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(arr).save(path, optimize=True)


def utility_textures():
    d = level_path("art", "terrains")
    # every base texture of the TerrainMaterialTextureSet must match its baseTexSize (2048)
    n = 2048
    save_png(os.path.join(d, "t_flat_nm.png"), np.full((n, n, 3), (128, 128, 255), np.uint8))
    save_png(os.path.join(d, "t_rough_r.png"), np.full((n, n), 210, np.uint8))
    save_png(os.path.join(d, "t_white_ao.png"), np.full((n, n), 255, np.uint8))
    save_png(os.path.join(d, "t_grey_h.png"), np.full((n, n), 128, np.uint8))


# ------------------------------------------------------------------ stages
def stage_terrain(scene, ctx):
    import terrain
    utility_textures()
    # per-material base colour measured from orthophoto / photos (terrain_colors.py); the
    # orthophoto itself is not used as base: canopy and shadows would be baked onto the ground
    colors = json.load(open(os.path.join(WORK, "terrain_colors.json")))
    base_tex = {}
    rng = np.random.default_rng(3)
    for m in terrain.TERRAIN_MATS:
        c = np.array(colors[m] if m in colors else colors[terrain.VERGE_OF[m]], np.float32)
        noise = rng.normal(0, 1, (64, 64)).astype(np.float32)
        from scipy.ndimage import gaussian_filter, zoom
        n = zoom(gaussian_filter(noise, 3, mode="wrap"), 32, order=1)
        n = n / (np.abs(n).max() + 1e-6)
        img = np.clip(c[None, None, :] * (1 + 0.08 * n[..., None]), 0, 255).astype(np.uint8)
        rel = f"art/terrains/t_base_{m.lower()}_b.png"
        save_png(level_path(*rel.split("/")), img)
        base_tex[m] = {"b": f"{L}/{rel}", "size": 256}
    override = ctx.get("terrain_override")
    posts = []
    if "wall_feet" in ctx:
        import walls
        rec = ctx.setdefault("wall_rec", {})
        posts.append(lambda H, xs, ys: walls.adjust_terrain_roadside(
            ctx.get("rwall_samples", np.zeros((0, 6))), xs, ys, walls.carve_terrain(ctx["wall_feet"], xs, ys, H, rec)))
    if "lake_grid" in ctx:
        import water
        posts.append(lambda H, xs, ys: water.lake_bed(H, xs, ys, ctx["lake_level"], ctx["wet_grid"]))
    if ctx.get("river_polys"):                           # v2.4: the beds of the rivers under their water
        import rivers
        posts.append(lambda H, xs, ys: rivers.carve_terrain(H, xs, ys, ctx["river_polys"]))
    if "railway" in ctx.get("stages", STAGES):
        import railway                                   # the ground under the tracks at their height
        keep = override[1] if override else None         # not the ground of the roads
        posts.append(lambda H, xs, ys: railway.carve_terrain(H, xs, ys, keep))

    def post(H, xs, ys):
        for fn in posts:
            H = fn(H, xs, ys)
        return H
    # v2.4: no grass (groundcover.py) within a terrain square of the carved road and path surfaces
    no_cover = None
    if override:
        from scipy.ndimage import binary_dilation
        no_cover = binary_dilation(override[1], iterations=1)
    z0, maxh, H = terrain.build_terrain(LEVEL_DIR, *(override or (None, None, None)), post_fn=post,
                                        cap=ctx.get("terrain_cap"), no_cover=no_cover)
    mats = terrain.terrain_materials(LEVEL_NAME, base_tex)
    os.makedirs(level_path("art", "terrains"), exist_ok=True)
    json.dump(mats, open(level_path("art", "terrains", "main.materials.json"), "w"), indent=1)
    if ctx.get("wall_rec"):
        stage_backfill(scene, ctx, H, base_tex)
    scene.add("MissionGroup/level_objects/terrain", {
        "name": "theTerrain", "class": "TerrainBlock", "persistentId": bng.pid(),
        "position": [TER_X0, TER_Y0, z0], "maxHeight": maxh, "squareSize": TER_SQUARE,
        "baseTexSize": 2048, "materialTextureSet": f"{LEVEL_NAME}TerrainMaterialTextureSet",
        "terrainFile": f"{L}/theTerrain.ter"})
    ctx["z0"], ctx["H"] = z0, H
    print("terrain z0", z0, "maxHeight", maxh)


TL = "/assets/materials/tileable"
ROAD_CLASSES = {  # cadastral class: (material, mesh cell m, uv tile m)
    "strada_sentiero": ("mp_road_asphalt", 1.0, 1.25),
    "altro_rivestimento_duro": ("mp_hard_asphalt", 2.0, 1.25),
    "marciapiede": ("mp_sidewalk", 1.0, 1.25),
    "spartitraffico": ("mp_island", 1.0, 2.5),
}
CHUNK = 128.0


def road_materials():
    a = f"{TL}/concrete/italy_asphalt/t_asphalt"
    s = f"{TL}/concrete/sidewalk1/t_sidewalk1"
    st = f"{L}/art/shapes/buildings/t_bld_stone"          # v2.2: the rubble stone of the walls (bld_textures.py)
    return [
        bng.material("mp_road_asphalt", f"{a}_b.color.dds", f"{a}_nm.normal.dds", f"{a}_r.data.dds",
                     f"{a}_ao.data.dds", ground_type="ASPHALT"),
        bng.material("mp_hard_asphalt", f"{a}_b.color.dds", f"{a}_nm.normal.dds", f"{a}_r.data.dds",
                     f"{a}_ao.data.dds", base_color=[0.92, 0.92, 0.92, 1], ground_type="ASPHALT"),
        bng.material("mp_sidewalk", f"{a}_b.color.dds", f"{a}_nm.normal.dds", f"{a}_r.data.dds",
                     f"{a}_ao.data.dds", base_color=[1.05, 1.05, 1.05, 1], ground_type="ASPHALT"),
        bng.material("mp_island", f"{s}_b.color.dds", f"{s}_nm.normal.dds", f"{s}_r.data.dds",
                     ground_type="CONCRETE"),
        # 2022 resurfacing: new asphalt is about half as bright as the old surface in the photos
        bng.material("mp_road_asphalt_fresh", f"{a}_b.color.dds", f"{a}_nm.normal.dds", f"{a}_r.data.dds",
                     f"{a}_ao.data.dds", base_color=[0.5, 0.5, 0.52, 1], ground_type="ASPHALT"),
        # stone face under a paved edge high above the ground (bridge sides, walls at steps)
        bng.material("mp_road_wall", f"{st}_b.color.png", f"{st}_nm.normal.png", f"{st}_r.data.png",
                     f"{st}_ao.data.png", ground_type="ROCK"),
        # v2.0 network: paved paths, bridge parapets
        bng.material("mp_path_paved", f"{a}_b.color.dds", f"{a}_nm.normal.dds", f"{a}_r.data.dds",
                     f"{a}_ao.data.dds", base_color=[0.98, 0.97, 0.95, 1], ground_type="ASPHALT"),
        bng.material("mp_bridge_parapet", f"{s}_b.color.dds", f"{s}_nm.normal.dds", f"{s}_r.data.dds",
                     base_color=[0.85, 0.85, 0.83, 1], ground_type="CONCRETE"),
    ] + surface_materials()


def surface_materials():
    """v2.4: gravel, earth, granite setts and river cobbles (surface_textures.py) on carriageways,
    yards and paths (osm_surface.MATS); the ground type gives the grip and the sound in the game."""
    import osm_surface
    t = f"{L}/art/shapes/roads"
    ground = {"gravel": "GRAVEL", "dirt": "DIRT", "sett": "COBBLESTONE", "cobble": "COBBLESTONE"}
    out = []
    for group, mats in osm_surface.MATS.items():
        for surf, name in mats.items():
            if surf == "hard":
                continue
            out.append(bng.material(name, f"{t}/t_road_{surf}_b.color.png", f"{t}/t_road_{surf}_nm.normal.png",
                                    f"{t}/t_road_{surf}_r.data.png", f"{t}/t_road_{surf}_ao.data.png",
                                    ground_type=ground[surf]))
    return out


def road_textures():
    """Textures of the unpaved and stone surfaces (surface_textures.py, drawn procedurally)."""
    import surface_textures
    surface_textures.build(level_path("art", "shapes", "roads"))


def road_height_fn():
    """Paved-surface height (roadheight.py): the idealised surfaces of the paved areas, the
    smoothed DTM away from them."""
    import roadheight
    return roadheight.height_fn()


def ground_fn():
    """Terrain before the road carve (DTM smoothed on the window of each query), for the depth of
    the skirts."""
    from geo import Grid, smoothed_sampler
    return smoothed_sampler(Grid.load(os.path.join(WORK, "dtm05.npz")), 0.6)


def stage_roads(scene, ctx):
    """Collision meshes of every road and path of the area:
    - the cadastral paved surfaces within roadheight.CORRIDOR m of the Street View route (the Strada
      Cantonale and what touches it) on the idealised surfaces of roadheight.py (v1.1);
    - the rest of the network (swissTLM3D lines, surveyed carriageways, squares, paths) on the
      heights of network_surface.py, meshed per tile by network_mesh.py;
    - the bridge decks (bridges.py, corrected by hand in dati/ponti.json).
    Terrain: carved 0.1 m under the lowest surface nearby; under bridge decks only lowered where it
    rises above the slab."""
    import shapely
    import road_mesh
    import roadheight
    import network_mesh
    import bridges
    import terrain
    from geo import Grid
    from rasterio import features
    from rasterio.transform import Affine
    S = roadheight.load()
    hfn = road_height_fn()
    ground = ground_fn()
    road_textures()
    import bld_textures
    bld_textures.stone_wall(level_path("art", "shapes", "buildings"))     # the stone faces (mp_road_wall)
    bng.write_materials(level_path("art", "shapes", "roads", "main.materials.json"), road_materials())
    builders = {}
    meshed = []
    # state of October 2022 (markings_state.py): traffic islands removed when the start junction
    # was rebuilt are paved as road, fresh asphalt of the resurfacing works is darker
    sf = os.path.join(WORK, "markings_state.json")
    state = json.load(open(sf)) if os.path.exists(sf) else {}
    gone = [shapely.Point(i["x"], i["y"]) for i in state.get("removed_islands", [])]
    # v2.4: and the sidewalk pieces across them (the walkway of the old crossing)
    gone_sw = [shapely.Point(i["x"], i["y"]) for i in state.get("removed_sidewalks", [])]
    fresh = shapely.union_all([shapely.Polygon(r) for r in state.get("fresh_asphalt", [])]) \
        if state.get("fresh_asphalt") else None
    items = []
    for gi, cls, props in roadheight.paved_polygons():
        mat, cell, uvt = ROAD_CLASSES[cls]
        pid = roadheight.polygon_key(gi, S)
        if (cls == "spartitraffico" and any(gi.contains(q) for q in gone)) or \
                (cls == "marciapiede" and any(gi.contains(q) for q in gone_sw)):
            mat, cell, uvt = ROAD_CLASSES["strada_sentiero"]
        if cls == "strada_sentiero" and fresh is not None and gi.intersects(fresh):
            items.append((gi.intersection(fresh), "mp_road_asphalt_fresh", cell, uvt, pid))
            gi = gi.difference(fresh)
        items.append((gi, mat, cell, uvt, pid))

    def key_fn(pid):
        return lambda x, y: S.surfaces_at_polygon(x, y, pid)

    # no corridor surface under the ground either (an edge extrapolated from far cells of the v1.1
    # surfaces, where a side street leaves the corridor): at most SUNK under the lowest bare ground
    # within 1 m, as on the rest of the network (network_mesh.py)
    from scipy import ndimage as ndi
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    bb = np.array([it[0].bounds for it in items if not it[0].is_empty])
    win, _, _ = dtm.window(bb[:, 0].min() - 5, bb[:, 1].min() - 5, bb[:, 2].max() + 5, bb[:, 3].max() + 5, pad=4)
    lo = Grid(ndi.minimum_filter(np.asarray(win.a, np.float32), size=5) - network_mesh.SUNK, win.x_min, win.y_max,
              win.res)
    del win

    def z_fn(pid):
        return lambda x, y, comp: np.maximum(S.height(x, y, pid=pid, comp=int(comp)), lo.sample(x, y))

    def h_fn(x, y):
        return np.maximum(hfn(x, y), lo.sample(x, y))

    stats = {"stone faces": 0}

    def add_surface(tx, ty, mat, uvt, V, T, S_, ground_, tops=None):
        mb = builders.setdefault((tx, ty), bng.MeshBuilder())
        mb.add(mat, V, uvs=V[:, :2] / uvt, tris=T)
        if tops is not None:
            tops.append(V[T])
        kerb, wall = road_mesh.skirt_bands(V, T, road_mesh.skirt_depth(V, T, S_, ground_))
        mb.add(mat, kerb, uvs=np.column_stack([kerb[:, 0] + kerb[:, 1], kerb[:, 2]]) / uvt,
               normals=bng.flat_normals_soup(kerb))
        if len(wall):
            mb.add("mp_road_wall", wall, uvs=np.column_stack([wall[:, 0] + wall[:, 1], wall[:, 2]]) / 1.6,
                   normals=bng.flat_normals_soup(wall))
            stats["stone faces"] += len(wall) // 6

    tops = []
    for gi, mat, cell, uvt, pid in items:
        if gi.is_empty or gi.area < 0.05:
            continue
        meshed.append(gi)
        x0, y0, x1, y1 = gi.bounds
        for tx in range(int(np.floor(x0 / CHUNK)), int(np.floor(x1 / CHUNK)) + 1):
            for ty in range(int(np.floor(y0 / CHUNK)), int(np.floor(y1 / CHUNK)) + 1):
                piece = gi.intersection(shapely.box(tx * CHUNK, ty * CHUNK, (tx + 1) * CHUNK, (ty + 1) * CHUNK))
                if piece.is_empty or piece.area < 0.05:
                    continue
                if pid is None:                  # a sliver without cells of its own: the height function
                    V, T = road_mesh.mesh_polygon(piece, h_fn, cell=cell)
                    parts = [(None, V, T)]
                else:                            # one mesh per surface of the polygon (walls inside it)
                    parts = []
                    for sub, comp in road_mesh.split_by_surface(piece, S, pid):
                        kf = key_fn(pid) if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                        parts += road_mesh.mesh_polygon_surfaces(sub, z_fn(pid), kf, cell=cell)
                for comp, V, T in parts:
                    if len(T):
                        add_surface(tx, ty, mat, uvt, V, T, S, ground, tops)
    print("corridor: %d chunks" % len(builders), flush=True)
    # terrain carve of the corridor: the vertices whose triangles reach a paved mesh drop 10 cm
    # below the lowest paved face within one terrain step (road_mesh.carve_window), so the terrain
    # never reaches over a face, between the vertices and at the lower side of a step
    xs, ys = terrain.vertex_coords()
    sq = xs[1] - xs[0]
    ov = np.full((len(ys), len(xs)), np.nan, np.float32)            # carve height, NaN = none
    cap = np.full((len(ys), len(xs)), np.inf, np.float32)           # highest ground (under decks)
    corridor = shapely.union_all(meshed)
    union = shapely.union_all([m.buffer(sq) for m in meshed])
    bx0, by0, bx1, by1 = union.bounds
    c0, c1 = max(int(np.searchsorted(xs, bx0)) - 1, 0), min(int(np.searchsorted(xs, bx1)) + 1, len(xs))
    r0, r1 = max(int(np.searchsorted(ys, by0)) - 1, 0), min(int(np.searchsorted(ys, by1)) + 1, len(ys))
    tr = Affine(sq, 0, xs[c0] - 0.5 * sq, 0, sq, ys[r0] - 0.5 * sq)  # row 0 = south
    mask = features.rasterize([(union, 1)], out_shape=(r1 - r0, c1 - c0), transform=tr, fill=0,
                              dtype=np.uint8, all_touched=True).astype(bool)
    rr, cc = np.nonzero(mask)
    csurf = road_mesh.TriSurface(np.concatenate(tops))
    zc = road_mesh.carve_window(csurf, xs, ys, r0 + rr, c0 + cc)
    ok = np.isfinite(zc)
    ov[r0 + rr[ok], c0 + cc[ok]] = zc[ok] - 0.10
    ctx["road_mesh_fn"] = road_mesh.MeshSampler(np.concatenate(tops))
    # the rest of the network, tile by tile
    net = network_mesh.Network(exclude=corridor)
    ctx["surfaces"] = net.assign_surfaces()

    def on_carve(r, c, z):
        ov[r, c] = np.fmin(ov[r, c], z)
    t0 = time.time()
    tiles = network_mesh.tiles()
    ntri = 0
    chunk_tops = {}

    def on_tops(cx, cy, tri):
        chunk_tops.setdefault((cx, cy), []).append(tri)
    for k, (X0, Y0) in enumerate(tiles):
        ntri += network_mesh.mesh_tile(net, dtm, X0, Y0, xs, ys, add_surface, on_tops)
        if k % 25 == 0:
            print("  network tiles %d/%d, %d triangles, %.0f s" % (k + 1, len(tiles), ntri, time.time() - t0), flush=True)
    # the carve once all the meshes exist (a vertex at a tile edge sees the meshes on both sides)
    per = int(round(network_mesh.TILE / CHUNK))
    for X0, Y0 in tiles:
        cx0, cy0 = int(round(X0 / CHUNK)), int(round(Y0 / CHUNK))
        near = [t for cx in range(cx0 - 1, cx0 + per + 1) for cy in range(cy0 - 1, cy0 + per + 1)
                for t in chunk_tops.get((cx, cy), [])]
        if near:
            network_mesh.carve_tile(net, X0, Y0, xs, ys, road_mesh.TriSurface(np.concatenate(near)), on_carve)
    print("  network carve done, %.0f s" % (time.time() - t0), flush=True)

    def on_deck(x, y, mat, uvt, soup, kind):
        tx, ty = int(np.floor(x / CHUNK)), int(np.floor(y / CHUNK))
        mb = builders.setdefault((tx, ty), bng.MeshBuilder())
        V = soup.reshape(-1, 3)
        uv = V[:, :2] / uvt if kind == "top" else np.column_stack([V[:, 0] + V[:, 1], V[:, 2]]) / uvt
        mb.add(mat, V, uvs=uv, normals=bng.flat_normals_soup(V))

    def on_cap(r, c, z):
        cap[r, c] = np.minimum(cap[r, c], z)
    recs = bridges.build(net, lambda x, y: dtm.sample(x, y), on_deck, on_cap, xs, ys, exclude=corridor)
    bridges.save_records(recs)
    print("chunk seams stitched:", stitch_chunks(builders), flush=True)
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/roads/road_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(level_path(rel), name=f"road_{tx}_{ty}", origin=origin)
        ntri += mb.triangle_count()
        scene.add("MissionGroup/roads/surfaces", bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=True))
    m = np.isfinite(ov)
    ctx["terrain_override"] = (np.nan_to_num(ov), m, None)
    ctx["terrain_cap"] = cap
    ctx["network"] = net
    ctx["corridor"] = corridor
    k = np.isfinite(cap)
    feet = shapely.to_wkb([f for _, f in net.deck_feet]) if net.deck_feet else np.zeros(0, object)
    np.savez(ROADS_STATE, shape=np.array(ov.shape), ov_i=np.flatnonzero(m), ov_v=ov[m], cap_i=np.flatnonzero(k),
             cap_v=cap[k], tops=np.concatenate(tops), chunks=np.array(sorted(builders), np.int32).reshape(-1, 2),
             corridor=np.frombuffer(shapely.to_wkb(corridor), np.uint8),
             deck_kind=np.array([kd for kd, _ in net.deck_feet], dtype="U4"),
             deck_foot=np.array([np.frombuffer(w, np.uint8) for w in feet] + [None], dtype=object)[:-1])
    print("road chunks", len(builders), "triangles", ntri, "stone faces", stats["stone faces"], "bridges", len(recs),
          "carved vertices", int(m.sum()), flush=True)


ROADS_STATE = os.path.join(WORK, "roads_state.npz")


def stitch_chunks(builders, tol=0.3, snap=0.005):
    """Road mesh vertices on the lines between chunks: where neighbouring chunks have a vertex at
    the same place with heights less than `tol` apart (surfaces are resolved per 512 m tile and
    per facet, so the two sides can differ by a few cm), all of them take the mean height.
    Returns the number of vertices moved."""
    refs, P = [], []
    for key, mb in builders.items():
        for mat, p in mb.parts.items():
            for ai, V in enumerate(p[0]):
                f = V[:, :2] / CHUNK
                on = (np.abs(f - np.round(f)) < 1e-5).any(1)
                idx = np.flatnonzero(on)
                if len(idx):
                    refs.append((V, idx))
                    P.append(np.column_stack([V[idx], np.full(len(idx), len(refs) - 1)]))
    if not P:
        return 0
    P = np.concatenate(P)
    k = np.round(P[:, :2] / snap).astype(np.int64)
    order = np.lexsort((P[:, 2], k[:, 1], k[:, 0]))
    k, Z = k[order], P[order, 2]
    link = (k[1:] == k[:-1]).all(1) & (Z[1:] - Z[:-1] < tol)
    grp = np.r_[0, np.cumsum(~link)]
    mean = np.bincount(grp, weights=Z) / np.bincount(grp)
    newz = mean[grp]
    moved = np.abs(newz - Z) > 1e-4
    zfull = np.empty(len(P))
    zfull[order] = newz
    off = 0
    for V, idx in refs:
        V[idx, 2] = zfull[off:off + len(idx)]
        off += len(idx)
    return int(moved.sum())


def stage_roads_reuse(scene, ctx):
    """stage_roads without meshing again: the road meshes of the previous build (still in the level
    folder) and what the later stages need from work/roads_state.npz."""
    import shapely
    import road_mesh
    import network_mesh
    st = np.load(ROADS_STATE, allow_pickle=True)
    shape = tuple(int(v) for v in st["shape"])
    ov = np.full(shape, np.nan, np.float32)
    ov.reshape(-1)[st["ov_i"]] = st["ov_v"]
    cap = np.full(shape, np.inf, np.float32)
    cap.reshape(-1)[st["cap_i"]] = st["cap_v"]
    for tx, ty in st["chunks"].tolist():
        rel = f"art/shapes/roads/road_{tx:+03d}_{ty:+03d}.dae"
        assert os.path.exists(level_path(rel)), rel
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        scene.add("MissionGroup/roads/surfaces", bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=True))
    m = np.isfinite(ov)
    ctx["terrain_override"] = (np.nan_to_num(ov), m, None)
    ctx["terrain_cap"] = cap
    ctx["road_mesh_fn"] = road_mesh.MeshSampler(st["tops"])
    ctx["corridor"] = shapely.from_wkb(st["corridor"].tobytes())
    ctx["network"] = network_mesh.Network(exclude=ctx["corridor"])
    if "deck_kind" in st.files:
        ctx["network"].deck_feet = [(str(kd), shapely.from_wkb(w.tobytes()))
                                    for kd, w in zip(st["deck_kind"], st["deck_foot"])]
    print("road meshes of the previous build:", len(st["chunks"]), "chunks, carved vertices", int(m.sum()), flush=True)


def stage_walls(scene, ctx):
    import walls
    import bld_textures
    # v2.2: original procedural textures (bld_textures.py): rubble stone (shared with the rustici) and
    # board-formed concrete, instead of the vanilla regular stone bricks
    bdir, wdir = level_path("art", "shapes", "buildings"), level_path("art", "shapes", "walls")
    os.makedirs(bdir, exist_ok=True)
    bld_textures.stone_wall(bdir)
    bld_textures.plaster(bdir)
    bld_textures.walls(wdir)
    st, cc = f"{L}/art/shapes/buildings/t_bld_stone", f"{L}/art/shapes/walls/t_wall_concrete"
    bng.write_materials(level_path("art", "shapes", "walls", "main.materials.json"), [
        bng.material("mp_wall_stone", f"{st}_b.color.png", f"{st}_nm.normal.png", f"{st}_r.data.png",
                     f"{st}_ao.data.png", ground_type="ROCK"),
        bng.material("mp_wall_stone_top", f"{cc}_b.color.png", f"{cc}_nm.normal.png", f"{cc}_r.data.png",
                     ground_type="CONCRETE"),
        bng.material("mp_wall_concrete", f"{cc}_b.color.png", f"{cc}_nm.normal.png", f"{cc}_r.data.png",
                     ground_type="CONCRETE"),
        bng.material("mp_wall_concrete_top", f"{cc}_b.color.png", f"{cc}_nm.normal.png", f"{cc}_r.data.png",
                     ground_type="CONCRETE"),
        bng.material("mp_wall_plaster", f"{L}/art/shapes/buildings/t_bld_plaster_b.color.png",
                     f"{L}/art/shapes/buildings/t_bld_plaster_nm.normal.png",
                     f"{L}/art/shapes/buildings/t_bld_plaster_r.data.png", vert_color=True, ground_type="CONCRETE")])
    # no cadastral wall across a road or along the way of a line (v2.0 network)
    free = walls.drive_free(ctx["network"], ctx.get("corridor")) if ctx.get("network") is not None else None
    ctx["wall_samples"], ctx["wall_feet"] = walls.build(LEVEL_DIR, LEVEL_NAME, scene, free=free)
    from config import NO_PHOTO
    ctx["rwall_samples"] = walls.build_roadside(LEVEL_DIR, LEVEL_NAME, scene, photo=not NO_PHOTO)


def stage_guardrails(scene, ctx):
    import guardrail_mesh
    guardrail_mesh.build(LEVEL_DIR, LEVEL_NAME, scene, road_fn=ctx.get("road_mesh_fn"))


def stage_fences(scene, ctx):
    import fences
    fences.build(LEVEL_DIR, LEVEL_NAME, scene)


def stage_markings(scene, ctx):
    """Road paint on the road meshes themselves (their triangles, where they are built in the same
    run), elsewhere on the road height function. The Strada Cantonale keeps the paint measured for
    v1.x; the rest of the network gets the paint measured in the orthophoto (network_markings.py,
    markings_net.py)."""
    import markings_decals
    import markings_net
    hfn = road_height_fn()
    mesh = ctx.get("road_mesh_fn")

    def on_road(x, y):
        z = hfn(x, y)
        if mesh is not None:
            zm = mesh(x, y).reshape(np.shape(z))
            z = np.where(np.isfinite(zm), zm, z)
        return z
    if not os.path.exists(os.path.join(WORK, "road_strip.npz")):      # no photo data here: take them over
        import carryover
        carryover.markings(LEVEL_DIR, scene, mesh, new_ground(ctx))
    else:
        markings_decals.build(LEVEL_DIR, scene, on_road)
    ctx["network_paint"] = markings_net.build(LEVEL_DIR, scene, ctx.get("network"))


def new_ground(ctx):
    """Ground of this build: the higher of the corridor road meshes and the terrain (ctx['H'])."""
    import terrain
    from scipy.ndimage import map_coordinates
    H = ctx["H"]
    xs, ys = terrain.vertex_coords()
    sq = xs[1] - xs[0]
    mesh = ctx.get("road_mesh_fn")

    def fn(x, y):
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        zt = map_coordinates(H, [(y - ys[0]) / sq, (x - xs[0]) / sq], order=1, mode="nearest")
        if mesh is None:
            return zt
        zr = mesh(x, y)
        return np.where(np.isfinite(zr), np.maximum(zr, zt), zt)
    return fn


def terrain_top_fn(ctx):
    """The terrain surface of this build at (x, y): the higher of the two ways a square can be split."""
    import terrain
    H = ctx["H"]
    xs, ys = terrain.vertex_coords()
    sq = xs[1] - xs[0]

    def fn(x, y):
        c = (np.asarray(x, float) - xs[0]) / sq
        r = (np.asarray(y, float) - ys[0]) / sq
        c0 = np.clip(np.floor(c).astype(np.int64), 0, len(xs) - 2)
        r0 = np.clip(np.floor(r).astype(np.int64), 0, len(ys) - 2)
        fc, fr = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
        z00, z10, z01, z11 = H[r0, c0], H[r0, c0 + 1], H[r0 + 1, c0], H[r0 + 1, c0 + 1]
        a = np.where(fc >= fr, z00 + fc * (z10 - z00) + fr * (z11 - z10), z00 + fr * (z01 - z00) + fc * (z11 - z01))
        b = np.where(fc + fr <= 1, z00 + fc * (z10 - z00) + fr * (z01 - z00),
                     z11 + (1 - fc) * (z01 - z11) + (1 - fr) * (z10 - z11))
        return np.maximum(a, b)
    return fn


def stage_railway(scene, ctx):
    """Tracks of the railway lines (railway.py) on the terrain of this build, flush with the roads at
    the level crossings."""
    import railway
    import markings_net
    from road_mesh import TriSurface
    from geo import Grid
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    ctx["railway"] = railway.build(LEVEL_DIR, scene, terrain_top_fn(ctx), TriSurface(markings_net.road_tops(LEVEL_DIR)),
                                   lambda x, y: dtm.sample(x, y))


def stage_ai(scene, ctx):
    import ai_roads
    ai_roads.build(scene, road_height_fn(), ctx.get("network"))


def stage_props(scene, ctx):
    """Objects of the Street View route (props.py, or taken over from the released level), then the
    signs and furniture OpenStreetMap records on the rest of the network (props_osm.py)."""
    if not os.path.isdir(os.path.join(WORK, "signs")):              # no photo data here: take them over
        import carryover
        carryover.props(LEVEL_DIR, scene, new_ground(ctx))
    else:
        import props
        props.build(LEVEL_DIR, LEVEL_NAME, scene, road_height_fn())
    import pickle
    import shapely
    import area
    import markings_net
    import props_osm
    from road_mesh import TriSurface
    tops = markings_net.road_tops(LEVEL_DIR)
    import osm_surface
    carr = TriSurface(markings_net.road_tops(LEVEL_DIR, osm_surface.ROAD_MATS + ("mp_road_asphalt_fresh",)))
    surf = TriSurface(tops)
    terrain_z = new_ground(ctx)

    def ground(x, y):
        zr = surf.height(x, y, "high")
        zt = terrain_z(x, y)
        return np.where(np.isfinite(zr), np.maximum(zr, zt), zt)
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    solid = [g.buffer(0.3) for g, _ in av["LCSF"].get("edificio", [])] + \
            [g.buffer(0.3) for layer in ("SOSF", "SOLI") for g, _ in av[layer].get("muro", [])]
    # nor in the middle of a road of the network (the half of its width a car drives through, as
    # check_level.py sweeps it, + 0.5 m), where a junction or a yard is not surveyed as carriageway
    net = ctx.get("network")
    for s in (net.segs if net is not None else []):
        a, n = s["first"], s["n"]
        if s["kind"] == "road" and n >= 2:
            solid.append(shapely.LineString(np.column_stack([net.x[a:a + n], net.y[a:a + n]])).buffer(
                0.25 * float(np.median(net.w[a:a + n])) + 0.5, cap_style="flat"))
    stree = shapely.STRtree(solid)

    def blocked(x, y):
        pts = shapely.points(np.asarray(x, float), np.asarray(y, float))
        out = np.zeros(len(pts), bool)
        i, _ = stree.query(pts, predicate="within")
        out[i] = True
        return out
    ctx["osm_props"] = props_osm.build(LEVEL_DIR, scene, ground, lambda x, y: np.isfinite(carr.height(x, y, "high")),
                                       blocked, area.route())


def stage_sky(scene, ctx):
    g = "MissionGroup/level_objects/sky_and_sun"
    scene.add(g, {"name": "sunsky", "class": "ScatterSky", "persistentId": bng.pid(),
                  "position": [0, 0, 400], "ambientScale": [1, 0.894, 0.78, 1],
                  "ambientScaleGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                  "colorize": [0.2157, 0.349, 0.6039, 1],
                  "colorizeGradientFile": "art/sky_gradients/default/gradient_colorize.png",
                  "fogScale": [0.396, 0.667, 1, 1], "fogScaleGradientFile": "art/sky_gradients/default/gradient_fog.png",
                  "flareType": "BNG_Sunflare_3", "flareScale": 5, "mieScattering": 0.0005,
                  "moonMat": "Moon_Glow_Mat", "nightCubemap": "nightCubemap",
                  "nightGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                  "nightFogGradientFile": "art/sky_gradients/default/gradient_fog.png",
                  "shadowDistance": 1600, "skyBrightness": 40,
                  "sunScale": [0.996, 0.831, 0.729, 1],
                  "sunScaleGradientFile": "art/sky_gradients/default/gradient_sunscale.png"})
    # Street View capture: October 2022, late morning
    scene.add(g, {"name": "tod", "class": "TimeOfDay", "persistentId": bng.pid(), "position": [0, 0, 400],
                  "axisTilt": 23.44, "day": 280, "dstRule": "eu", "latitude": 45.9917, "longitude": 8.8690,
                  "utcOffset": "1", "play": False, "startTime": 0.07, "time": 0.07, "version": 2})
    # v2.4: a little more haze, kept lower over the lake valley (density 1.1e-4 -> 1.3e-4, height
    # 1200 -> 1000 m, a touch bluer): the slopes across the lake fade with the distance as on hazy days
    scene.add(g, {"name": "theLevelInfo", "class": "LevelInfo", "persistentId": bng.pid(),
                  "canvasClearColor": [1, 1, 1, 255], "enabled": "1", "fogAtmosphereHeight": 1000,
                  "fogColor": [0.76, 0.80, 0.86, 1], "fogDensity": 1.3e-04,
                  "globalEnviromentMap": "BNG_Sky_02_cubemap", "gravity": -9.81, "visibleDistance": 12000,
                  "temperatureCurveC": [0, 12, 0.25, 11, 0.5, 18, 0.75, 14, 1, 12]})
    scene.add(g, {"name": "clouds", "class": "CloudLayer", "persistentId": bng.pid(), "position": [0, 0, 0],
                  "Textures": [{"texDirection": None, "texScale": None, "texSpeed": 0.002},
                               {"texDirection": [0.8, 0.2], "texScale": 2, "texSpeed": 0.025},
                               {"texDirection": [0.2, 0.5], "texScale": 0.5, "texSpeed": 0.035}],
                  # hazy, mostly overcast sky of the capture day (exposure 0 renders no clouds;
                  # vanilla Utah/Italy use 1.4-1.5 with coverage 1.23)
                  "baseColor": [0.93, 0.93, 0.94, 0.996], "coverage": 1.1, "exposure": 1.4, "height": 7,
                  "texture": "levels/Utah/art/skies/clouds_fluffy.dds", "windSpeed": 0.03})


def stage_water(scene, ctx):
    """Lago di Lugano: water blocks over the lake only (water.py; the Tresa valley west of Ponte
    Tresa lies below the lake), surface at the median DTM height over the surveyed lake."""
    import water
    params = {
        "baseColor": [30, 70, 80, 255], "clarity": 0.35, "cubemap": "cubemap_italy_reflection",
        "depthGradientMax": 30, "depthGradientTex": "/assets/materials/tileable/water/depthcolor_ramp/depthcolor_ramp_italy_muddy_b.png",
        "foamTex": "/assets/materials/tileable/water/water_effects/foam2_b.color.dds",
        "rippleTex": "/assets/materials/tileable/water/water_effects/ripple_nm.normal.dds",
        "fresnelBias": 0.12, "fresnelPower": 6, "fullReflect": False, "gridElementSize": 0.8,
        "overallRippleMagnitude": 0.4, "overallWaveMagnitude": 0.02, "reflectivity": 0.6,
        "specularPower": 200, "waterFogDensity": 0.4, "wetDarkening": 0.4, "wetDepth": 0.5,
        "Ripples (texture animation)": [{"rippleDir": [-1, -1], "rippleMagnitude": 0.2, "rippleSpeed": 0.0025, "rippleTexScale": [120, 120]},
                                         {"rippleDir": [1, -1], "rippleMagnitude": 0.3, "rippleSpeed": 0.015, "rippleTexScale": [10, 10]},
                                         {"rippleDir": [-1, 1], "rippleMagnitude": 0.3, "rippleSpeed": 0.05, "rippleTexScale": [2, 2]}],
        "Waves (vertex undulation)": [{"waveDir": [0, -1], "waveMagnitude": 0.05, "waveSpeed": 1},
                                       {"waveDir": [0.3, -1.2], "waveMagnitude": 0.03, "waveSpeed": -1},
                                       {"waveDir": [-0.3, -0.8], "waveMagnitude": 0.03, "waveSpeed": 1}]}
    import backdrop
    from config import TER_X1, TER_Y1
    level, lake, wet = water.build(scene, backdrop.CX, backdrop.CY, params, (TER_X0, TER_Y0, TER_X1, TER_Y1))
    ctx["lake_level"], ctx["lake_grid"], ctx["wet_grid"] = level, lake, wet
    print("lake level", level)
    # v2.4: water in the rivers (rivers.py), not over the lake's blocks nor the fords, on under the bridges
    net = ctx.get("network")
    if net is not None:
        import pickle
        import shapely
        import rivers
        import roadheight
        av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
        boxes = [shapely.box(o["position"][0] - o["scale"][0] / 2, o["position"][1] - o["scale"][1] / 2,
                             o["position"][0] + o["scale"][0] / 2, o["position"][1] + o["scale"][1] / 2)
                 for o in scene.groups.get("MissionGroup/level_objects/Water", []) if o.get("class") == "WaterBlock"]
        at_grade = [p["geom"] for p in net.polys]
        crossings = [f for _, f in getattr(net, "deck_feet", [])] + [g for g, _, _ in roadheight.paved_polygons()]
        fn = ctx.get("road_mesh_fn")
        road_z = (lambda x, y: fn(x, y)) if fn is not None else (lambda x, y: np.full(len(x), np.nan))
        ctx["rivers"], ctx["river_polys"] = rivers.build(LEVEL_DIR, LEVEL_NAME, scene, av, boxes, at_grade,
                                                         crossings, road_z)
        print("rivers:", ctx["rivers"], flush=True)


def stage_backdrop(scene, ctx):
    import backdrop
    backdrop.build(LEVEL_DIR, LEVEL_NAME, scene, ctx.get("lake_level", 270.5), ctx.get("lake_grid"), ctx.get("wet_grid"))


def stage_buildings(scene, ctx):
    import buildings_mesh
    net = ctx.get("network")
    ways = buildings_mesh.network_ways(net, ctx.get("corridor")) if net is not None else None
    tiles = buildings_mesh.build(LEVEL_DIR, LEVEL_NAME, ways=ways, net=net)
    for shape, origin, ntri in tiles:
        scene.add("MissionGroup/buildings", bng.tsstatic(shape, origin, collision=True, decal=False,
                                                          annotation="BUILDINGS"))
    print("building tiles", len(tiles), "triangles", sum(t[2] for t in tiles))


def stage_vegetation(scene, ctx):
    """Trees and shrubs; nothing on or next to the roads and paths (clearance.py). v2.0: the
    drivable surfaces of the whole network (ctx['network'] from stage_roads) and the corridor."""
    import vegetation
    drv, net_xy = None, None
    net = ctx.get("network")
    if net is not None:
        import clearance
        import shapely
        import roadheight
        import bridges
        roads = [p["geom"] for p in net.polys if not p["cls"].startswith("strip_path")]
        paths = [p["geom"] for p in net.polys if p["cls"].startswith("strip_path")]
        roads += [g for g, _, _ in roadheight.paved_polygons()]
        if net.deck_feet:                          # the decks as built (carried on to the ground)
            for kind, deck in net.deck_feet:
                (roads if kind == "road" else paths).append(deck)
        else:
            for s in net.segs:
                if s["bridge"]:
                    a, n = s["first"], s["n"]
                    deck = shapely.LineString(np.column_stack([net.x[a:a + n], net.y[a:a + n]])).buffer(
                        bridges.half_width({"width": net.w}, s), cap_style="flat")
                    (roads if s["kind"] == "road" else paths).append(deck)
        drv = clearance.Drivable(roads, paths)
        net_xy = (np.column_stack([net.x, net.y]), 0.5 * net.w,
                  np.array([net.segs[k]["kind"] == "path" for k in net.seg], bool))
    counts = vegetation.build(LEVEL_DIR, LEVEL_NAME, scene, drivable=drv, net_xy=net_xy)
    ctx["n_forest"] = sum(counts.values())
    # v2.4: rows of vines in the vineyards near the roads (vineyards.py)
    if net is not None:
        import pickle
        import vineyards
        av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
        ctx["vineyards"] = vineyards.build(LEVEL_DIR, LEVEL_NAME, scene, av, net_xy[0], roads + paths)
        print("vineyards:", ctx["vineyards"], flush=True)


def stage_backfill(scene, ctx, H, base_tex):
    """The ground behind the retaining walls, where the terrain was lowered so that no terrain
    triangle spans a wall (walls.carve_terrain): a mesh with the ground as it was, in the material
    of the terrain layer there, cut at the roads, paths, bridge decks and railway tracks."""
    import terrain
    import walls
    import roadheight
    from geo import Grid
    xs, ys = terrain.vertex_coords()
    bng.write_materials(level_path("art", "shapes", "walls", "backfill.materials.json"), [
        bng.material("mp_fill_" + m.lower(), base_tex[m]["b"], f"{det}_nm.png", ground_type=gm)
        for m, (gm, det, mac, dsize, msize) in terrain.TERRAIN_MATS.items()])
    drv = [g for g, _, _ in roadheight.paved_polygons()]
    net = ctx.get("network")
    if net is not None:
        drv += [p["geom"] for p in net.polys]
        drv += [foot for _, foot in getattr(net, "deck_feet", [])]
    # nor over the railway (railway.py): the bed of every track with its shoulders
    if "railway" in ctx.get("stages", STAGES):
        import railway
        import shapely
        drv += [shapely.LineString(Q[:, :2]).buffer(railway.SLEEPER_LEN[p["OBJEKTART"]] / 2 + railway.BALLAST_EXTRA +
                                                     railway.EMBANK_MAX, cap_style="flat")
                for p, Q in railway.tracks() if p.get("KUNSTBAUTE") != "Bruecke"]
    drv = [g for g in drv if g is not None and not g.is_empty]
    layers = np.load(os.path.join(WORK, "terrain_layers.npy"), mmap_mode="r")
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    walls.build_backfill(LEVEL_DIR, LEVEL_NAME, scene, ctx["wall_rec"], H, xs, ys, ctx["wall_feet"], drv, layers,
                         dtm.sample)


def stage_groundcover(scene, ctx):
    """v2.4: grass and meadow flowers around the camera (groundcover.py)."""
    import groundcover
    ctx["groundcover"] = groundcover.build(LEVEL_DIR, LEVEL_NAME, scene)
    print("groundcover:", ctx["groundcover"], flush=True)


def stage_spawns(scene, ctx):
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    main = [p for p in poses if p.get("main_run", True)]
    g = "MissionGroup/PlayerDropPoints"
    hfn = road_height_fn()
    for k, idx in enumerate([2, len(main) // 2, len(main) - 3]):
        p, q = main[idx], main[idx + 1]
        x, y = p["pos"][0], p["pos"][1]
        z = float(hfn([x], [y])[0]) + 0.8                          # 0.8 m above the road surface
        yaw = math.atan2(q["pos"][0] - x, q["pos"][1] - y)      # bearing of travel
        theta = math.atan2(q["pos"][1] - y, q["pos"][0] - x)    # travel direction, math angle
        name = ["spawn_magliaso", "spawn_mid", "spawn_pura"][k]
        # vehicles face their local -Y: local +x must point 90 deg counter-clockwise of the travel direction
        scene.add(g, {"name": name, "class": "SpawnSphere", "persistentId": bng.pid(),
                      "position": [x, y, z], "dataBlock": "SpawnSphereMarker", "enabled": "1",
                      "radius": 1, "rotationMatrix": bng.rot_local_x_to(theta + math.pi / 2),
                      "homingCount": "0", "indoorWeight": "1", "isAIControlled": "0", "lockCount": "0",
                      "outdoorWeight": "1", "sphereWeight": "1"})
        ctx.setdefault("spawns", []).append((name, x, y, z, yaw))
    # v2.0: one spawn point in every village of the area (swissNAMES3D), on its nearest main road
    net = ctx.get("network")
    if net is None:
        return
    import places
    import unicodedata
    main_cls = {"10m Strasse", "8m Strasse", "6m Strasse", "4m Strasse"}
    ok = np.array([net.segs[k]["class"] in main_cls and not net.segs[k]["bridge"] for k in net.seg])
    idx = np.flatnonzero(ok)
    from scipy.spatial import cKDTree
    tree = cKDTree(np.column_stack([net.x[idx], net.y[idx]]))
    taken = [(s[1], s[2]) for s in ctx["spawns"]]
    for vname, vx, vy, people in places.villages():
        d, j = tree.query([vx, vy])
        i = idx[j]
        if d > 250 or any(np.hypot(i_x - net.x[i], i_y - net.y[i]) < 400 for i_x, i_y in taken):
            continue
        a, n = net.segs[net.seg[i]]["first"], net.segs[net.seg[i]]["n"]
        k = min(max(i, a + 1), a + n - 1)
        theta = math.atan2(net.y[k] - net.y[k - 1], net.x[k] - net.x[k - 1])
        x, y, z = float(net.x[i]), float(net.y[i]), float(net.z[i]) + 0.8
        slug = unicodedata.normalize("NFKD", vname).encode("ascii", "ignore").decode().lower()
        name = "spawn_" + "".join(c if c.isalnum() else "_" for c in slug).strip("_")
        if any(s[0] == name for s in ctx["spawns"]):     # e.g. the village of Pura, the route ends there too
            name += "_paese"
        scene.add(g, {"name": name, "class": "SpawnSphere", "persistentId": bng.pid(),
                      "position": [x, y, z], "dataBlock": "SpawnSphereMarker", "enabled": "1",
                      "radius": 1, "rotationMatrix": bng.rot_local_x_to(theta + math.pi / 2),
                      "homingCount": "0", "indoorWeight": "1", "isAIControlled": "0", "lockCount": "0",
                      "outdoorWeight": "1", "sphereWeight": "1"})
        ctx["spawns"].append((name, x, y, z, math.atan2(math.cos(theta), math.sin(theta))))
        taken.append((x, y))
    print("spawn points", [s[0] for s in ctx["spawns"]])


# v2.2: the level's README describes the level as built by default (no imagery from the panoramas); the
# replacements of the public variant of v2.x are not needed any more
PUBLIC_README = []


def write_info(ctx):
    import area
    import bridges
    spawns = ctx.get("spawns", [])
    # the figures of the description, from what this build made
    km2 = area.polygon().area / 1e6
    n_bridges = sum(1 for b in json.load(open(bridges.PONTI, encoding="utf-8"))["ponti"] if not b.get("skip"))
    import buildings_mesh
    n_buildings = len(buildings_mesh.load_buildings())
    n_trees = int(round(ctx.get("n_forest", 0) / 1000.0))
    n_villages = sum(1 for s in spawns if s[0] not in ("spawn_magliaso", "spawn_mid", "spawn_pura"))
    info = {
        "title": "Malcantone - Magliaso, Pura e dintorni",
        "description": ("Ricostruzione in scala 1:1 di circa %d km2 del Malcantone (Ticino, CH) tra Ponte Tresa, "
                        "Caslano, Magliaso, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio e Sessa: "
                        "ogni strada e "
                        "sentiero guidabile, %d ponti, %d edifici con facciate, balconi e vetrine, guardrail su tutta "
                        "la rete, circa %d 000 alberi, traffico IA. La Strada "
                        "Cantonale Magliaso - Pura e' ricostruita da 366 panoramiche Street View (ottobre 2022); "
                        "ci sono anche la cantonale Magliaso - Agno - Bioggio - Manno - Gravesano, il passo sopra "
                        "Gravesano fino ad Arosio, la cantonale Ponte Tresa - Caslano e Via Torrazza. Dati ufficiali "
                        "swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D) e della "
                        "misurazione ufficiale del Cantone Ticino. Fonti: (c) swisstopo; Ufficio del catasto e dei "
                        "riordini fondiari, Cantone Ticino; Registro federale degli edifici (UST); (c) OpenStreetMap "
                        "contributors (ODbL); Copernicus DEM GLO-30 (c) DLR e.V. / Airbus."
                        % (round(km2), n_bridges, n_buildings, n_trees)),
        "previews": [f"{LEVEL_NAME}_preview.jpg"],
        "size": [TER_SIZE, TER_SIZE],
        "authors": "michi (pipeline: Claude)",
        "biome": "Prealpi ticinesi, bosco di castagni, Lago di Lugano, valle del Vedeggio",
        "roads": "Strade cantonali, strade comunali, strade forestali, sentieri e mulattiere",
        "suitablefor": "Guida su strada di montagna, fuoristrada su sentieri",
        "features": "Scala reale 1:1, terreno LiDAR, 12 x 12 km, %d paesi" % n_villages,
        "isAuxiliary": False, "supportsTraffic": True, "supportsTimeOfDay": True,
        "defaultSpawnPointName": spawns[0][0] if spawns else None,
        "spawnPoints": [{"objectname": s[0], "translationId": s[0]} for s in spawns],
    }
    json.dump(info, open(level_path("info.json"), "w"), indent=2)
    # player-facing documentation (sources, attribution, what differs from the older survey)
    here = os.path.dirname(os.path.abspath(__file__))
    readme = open(os.path.join(here, "README_livello.md"), encoding="utf-8").read()
    from config import NO_PHOTO
    if NO_PHOTO:
        # public variant: no imagery from the Street View panoramas in the level
        for a, b in PUBLIC_README:
            assert a in readme, a
            readme = readme.replace(a, b)
    open(level_path("README.md"), "w", encoding="utf-8").write(readme)
    ver = os.path.join(WORK, "validation_full", "VERIFICA.md")
    if os.path.exists(ver):
        shutil.copy(ver, level_path("VERIFICA.md"))
    # preview from the orthophoto (the terrain block; ortho05.tif in builds before v2.0)
    import rasterio
    op = os.path.join(WORK, "ortho.tif")
    with rasterio.open(op if os.path.exists(op) else os.path.join(WORK, "ortho05.tif")) as s:
        a = s.read(out_shape=(3, 1024, 1024)).transpose(1, 2, 0)
    Image.fromarray(a).save(level_path(f"{LEVEL_NAME}_preview.jpg"), quality=88)
    json.dump({"header": {"name": "DecalData File", "comments": "", "version": 2}, "instances": {}},
              open(level_path("main.decals.json"), "w"))


STAGES = ["roads", "walls", "water", "terrain", "railway", "sky", "backdrop", "buildings", "guardrails", "fences",
          "markings", "ai", "props", "vegetation", "groundcover", "spawns"]


def main():
    reuse = "--reuse-roads" in sys.argv[1:]
    stages = [a for a in sys.argv[1:] if not a.startswith("--")] or STAGES
    if set(stages) == set(STAGES) and os.path.exists(LEVEL_DIR):
        roads, keep = level_path("art", "shapes", "roads"), LEVEL_DIR + "_roads"
        if reuse:                                   # everything goes except the road meshes
            shutil.rmtree(keep, ignore_errors=True)
            shutil.move(roads, keep)
        shutil.rmtree(LEVEL_DIR)
        if reuse:
            os.makedirs(os.path.dirname(roads))
            shutil.move(keep, roads)
    os.makedirs(LEVEL_DIR, exist_ok=True)
    scene, ctx = bng.Scene(), {"stages": stages}
    for st in stages:
        t0 = time.time()
        globals()["stage_roads_reuse" if st == "roads" and reuse else f"stage_{st}"](scene, ctx)
        print(f"[stage {st}: {time.time() - t0:.0f} s]", flush=True)
    scene.write(LEVEL_DIR)
    if "vegetation" in stages:
        # crowns out of the clearance profile of the roads, trunks out of walls and buildings, every
        # plant on the ground: on the level as written, with all its meshes (canopy.py)
        import canopy
        t0 = time.time()
        ctx["canopy"] = canopy.run(LEVEL_DIR, record=os.path.join(WORK, "canopy_fixes.json"))
        ctx["n_forest"] = ctx["canopy"]["items_after"]
        print(f"[stage canopy: {time.time() - t0:.0f} s]", flush=True)
    write_info(ctx)
    # what the v2.1 steps did, for the reports (zone_report.py)
    stats = {k: ctx[k] for k in ("canopy", "railway", "osm_props", "network_paint", "surfaces", "groundcover",
                                 "rivers", "vineyards") if k in ctx}
    if stats:
        json.dump(stats, open(os.path.join(WORK, "build_stats.json"), "w"), indent=1, default=float)
    print("level written to", LEVEL_DIR)


if __name__ == "__main__":
    main()
