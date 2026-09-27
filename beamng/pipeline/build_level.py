"""Assemble the BeamNG level 'magliaso_pura' from the processed data.

Stages (each reads work/ products and writes into the level folder):
  terrain, sky/sun/water/level info, buildings, roads (+ markings, AI roads),
  walls, props (poles/signs/guardrails), vegetation, spawn points.
Run: python build_level.py [stage ...]   (default: all)
"""
import json, math, os, shutil, sys
import numpy as np
from PIL import Image
from config import WORK, LEVEL_DIR, LEVEL_NAME, TER_SIZE, TER_HALF, DATASET
import bng
from road_mesh import CARVE_RING

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


def ortho_base_texture(size=2048):
    """Orthophoto of the terrain square (north-up) as terrain base colour."""
    import rasterio
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        a = s.read().transpose(1, 2, 0)
        tr = s.transform
    # crop exactly the terrain extent [-TER_HALF, TER_HALF]
    c0 = int(round((-TER_HALF - tr.c) / tr.a))
    r0 = int(round((tr.f - TER_HALF) / -tr.e))
    n = int(round(2 * TER_HALF / tr.a))
    crop = a[r0:r0 + n, c0:c0 + n]
    img = Image.fromarray(crop).resize((size, size), Image.LANCZOS)
    p = level_path("art", "terrains", "t_ortho_base_b.png")
    img.save(p, optimize=True)
    return f"{L}/art/terrains/t_ortho_base_b.png"


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
        c = np.array(colors[m], np.float32)
        noise = rng.normal(0, 1, (64, 64)).astype(np.float32)
        from scipy.ndimage import gaussian_filter, zoom
        n = zoom(gaussian_filter(noise, 3, mode="wrap"), 32, order=1)
        n = n / (np.abs(n).max() + 1e-6)
        img = np.clip(c[None, None, :] * (1 + 0.08 * n[..., None]), 0, 255).astype(np.uint8)
        rel = f"art/terrains/t_base_{m.lower()}_b.png"
        save_png(level_path(*rel.split("/")), img)
        base_tex[m] = {"b": f"{L}/{rel}", "size": 256}
    override = ctx.get("terrain_override")
    post = None
    if "wall_samples" in ctx:
        import walls
        post = lambda H, xs, ys: walls.adjust_terrain_roadside(
            ctx.get("rwall_samples", np.zeros((0, 6))), xs, ys, walls.carve_terrain(ctx["wall_samples"], xs, ys, H))
    z0, maxh, H = terrain.build_terrain(LEVEL_DIR, *(override or (None, None, None)), post_fn=post)
    mats = terrain.terrain_materials(LEVEL_NAME, base_tex)
    os.makedirs(level_path("art", "terrains"), exist_ok=True)
    json.dump(mats, open(level_path("art", "terrains", "main.materials.json"), "w"), indent=1)
    scene.add("MissionGroup/level_objects/terrain", {
        "name": "theTerrain", "class": "TerrainBlock", "persistentId": bng.pid(),
        "position": [-TER_HALF, -TER_HALF, z0], "maxHeight": maxh, "squareSize": 1,
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
    st = f"{TL}/brick/stone_brick_regular/t_stone_brick_regular"
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
        bng.material("mp_road_wall", f"{st}_b.color.dds", f"{st}_nm.normal.dds", f"{st}_r.data.dds",
                     f"{st}_ao.data.dds", ground_type="ROCK"),
    ]


def road_height_fn():
    """Paved-surface height (roadheight.py): the idealised surfaces of the paved areas, the
    smoothed DTM away from them."""
    import roadheight
    return roadheight.height_fn()


def ground_fn():
    """Terrain before the road carve (smoothed DTM), for the depth of the skirts."""
    from geo import Grid
    from scipy.ndimage import gaussian_filter, map_coordinates
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    a = gaussian_filter(dtm.a, 0.6)

    def fn(x, y):
        r, c = dtm.rc(np.asarray(x), np.asarray(y))
        return map_coordinates(a, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")
    return fn


def stage_roads(scene, ctx):
    """Cadastral paved surfaces within roadheight.CORRIDOR m of the Street View route as collision
    meshes, on the idealised surfaces of roadheight.py."""
    import shapely
    import road_mesh
    import roadheight
    from rasterio import features
    from rasterio.transform import Affine
    S = roadheight.load()
    hfn = road_height_fn()
    ground = ground_fn()
    bng.write_materials(level_path("art", "shapes", "roads", "main.materials.json"), road_materials())
    builders = {}
    meshed = []
    # state of October 2022 (markings_state.py): traffic islands removed when the start junction
    # was rebuilt are paved as road, fresh asphalt of the resurfacing works is darker
    sf = os.path.join(WORK, "markings_state.json")
    state = json.load(open(sf)) if os.path.exists(sf) else {}
    gone = [shapely.Point(i["x"], i["y"]) for i in state.get("removed_islands", [])]
    fresh = shapely.union_all([shapely.Polygon(r) for r in state.get("fresh_asphalt", [])]) \
        if state.get("fresh_asphalt") else None
    items = []
    for gi, cls, props in roadheight.paved_polygons():
        mat, cell, uvt = ROAD_CLASSES[cls]
        pid = roadheight.polygon_key(gi, S)
        if cls == "spartitraffico" and any(gi.contains(q) for q in gone):
            mat, cell, uvt = ROAD_CLASSES["strada_sentiero"]
        if cls == "strada_sentiero" and fresh is not None and gi.intersects(fresh):
            items.append((gi.intersection(fresh), "mp_road_asphalt_fresh", cell, uvt, pid))
            gi = gi.difference(fresh)
        items.append((gi, mat, cell, uvt, pid))

    def key_fn(pid):
        return lambda x, y: S.surfaces_at_polygon(x, y, pid)

    def z_fn(pid):
        return lambda x, y, comp: S.height(x, y, pid=pid, comp=int(comp))
    n_wall = 0
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
                    V, T = road_mesh.mesh_polygon(piece, hfn, cell=cell)
                    parts = [(None, V, T)]
                else:                            # one mesh per surface of the polygon (walls inside it)
                    parts = []
                    for sub, comp in road_mesh.split_by_surface(piece, S, pid):
                        kf = key_fn(pid) if comp is None else (lambda x, y, c=comp: np.full(np.shape(x), c))
                        parts += road_mesh.mesh_polygon_surfaces(sub, z_fn(pid), kf, cell=cell)
                for comp, V, T in parts:
                    if len(T) == 0:
                        continue
                    mb = builders.setdefault((tx, ty), bng.MeshBuilder())
                    mb.add(mat, V, uvs=V[:, :2] / uvt, tris=T)
                    tops.append(V[T])
                    kerb, wall = road_mesh.skirt_bands(V, T, road_mesh.skirt_depth(V, T, S, ground))
                    mb.add(mat, kerb, uvs=np.column_stack([kerb[:, 0] + kerb[:, 1], kerb[:, 2]]) / uvt,
                           normals=bng.flat_normals_soup(kerb))
                    if len(wall):
                        mb.add("mp_road_wall", wall, uvs=np.column_stack([wall[:, 0] + wall[:, 1], wall[:, 2]]) / 1.6,
                               normals=bng.flat_normals_soup(wall))
                        n_wall += len(wall) // 6
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/roads/road_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(level_path(rel), name=f"road_{tx}_{ty}", origin=origin)
        ntri += mb.triangle_count()
        scene.add("MissionGroup/roads/surfaces", bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=True))
    # terrain carve: vertices under the paved meshes drop 10 cm below the lowest paved surface
    # within 0.8 m (so the terrain between two vertices never cuts through the lower side of a step)
    import terrain
    xs, ys = terrain.vertex_coords()
    tr = Affine(1.0, 0, xs[0] - 0.5, 0, 1.0, ys[0] - 0.5)          # row 0 = south
    union = shapely.union_all([m.buffer(0.35) for m in meshed])
    mask = features.rasterize([(union, 1)], out_shape=(len(ys), len(xs)), transform=tr, fill=0,
                              dtype=np.uint8, all_touched=True).astype(bool)
    X, Y = np.meshgrid(xs, ys)
    ov = np.zeros(X.shape, np.float64)
    Xm, Ym = X[mask], Y[mask]
    zc = hfn(Xm, Ym)
    for dx, dy in CARVE_RING:
        zc = np.minimum(zc, hfn(Xm + dx, Ym + dy))
    ov[mask] = zc - 0.10
    ctx["terrain_override"] = (ov, mask, None)
    ctx["paved_union"] = union
    ctx["road_mesh_fn"] = road_mesh.MeshSampler(np.concatenate(tops))
    print("road chunks", len(builders), "triangles", ntri, "wall faces", n_wall, "carved vertices", int(mask.sum()))


def stage_walls(scene, ctx):
    import walls
    st = f"{TL}/brick/stone_brick_regular/t_stone_brick_regular"
    cc = f"{TL}/concrete/t_italy_bld_old_concrete/t_italy_bld_old_concrete"
    bng.write_materials(level_path("art", "shapes", "walls", "main.materials.json"), [
        bng.material("mp_wall_stone", f"{st}_b.color.dds", f"{st}_nm.normal.dds", f"{st}_r.data.dds",
                     f"{st}_ao.data.dds", ground_type="ROCK"),
        bng.material("mp_wall_stone_top", f"{cc}_b.color.dds", f"{cc}_nm.normal.dds", f"{cc}_r.data.dds",
                     ground_type="CONCRETE")])
    ctx["wall_samples"] = walls.build(LEVEL_DIR, LEVEL_NAME, scene)
    from config import NO_PHOTO
    ctx["rwall_samples"] = walls.build_roadside(LEVEL_DIR, LEVEL_NAME, scene, photo=not NO_PHOTO)


def stage_guardrails(scene, ctx):
    import guardrail_mesh
    guardrail_mesh.build(LEVEL_DIR, LEVEL_NAME, scene)


def stage_fences(scene, ctx):
    import fences
    fences.build(LEVEL_DIR, LEVEL_NAME, scene)


def stage_markings(scene, ctx):
    """Road paint on the road meshes themselves (their triangles, where they are built in the same
    run), elsewhere on the road height function."""
    import markings_decals
    hfn = road_height_fn()
    mesh = ctx.get("road_mesh_fn")

    def on_road(x, y):
        z = hfn(x, y)
        if mesh is not None:
            zm = mesh(x, y).reshape(np.shape(z))
            z = np.where(np.isfinite(zm), zm, z)
        return z
    markings_decals.build(LEVEL_DIR, scene, on_road)


def stage_ai(scene, ctx):
    import ai_roads
    ai_roads.build(scene, road_height_fn())


def stage_props(scene, ctx):
    import props
    props.build(LEVEL_DIR, LEVEL_NAME, scene, road_height_fn())


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
    scene.add(g, {"name": "theLevelInfo", "class": "LevelInfo", "persistentId": bng.pid(),
                  "canvasClearColor": [1, 1, 1, 255], "enabled": "1", "fogAtmosphereHeight": 1200,
                  "fogColor": [0.78, 0.81, 0.86, 1], "fogDensity": 1.1e-04,
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
    """Lago di Lugano: water surface = median DTM height over the surveyed lake area."""
    from geo import Grid
    lc = np.load(os.path.join(WORK, "landcover05.npz"))
    from landcover import CODE
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    lake = lc["a"] == CODE["specchio_acqua"]
    level = float(np.median(dtm.a[lake])) if lake.any() else 270.5
    ctx["lake_level"] = level
    scene.add("MissionGroup/level_objects/Water", {
        "name": "LagoDiLugano", "class": "WaterPlane", "persistentId": bng.pid(), "position": [0, 0, level],
        "baseColor": [30, 70, 80, 255], "clarity": 0.35, "cubemap": "cubemap_italy_reflection",
        "depthGradientMax": 30, "depthGradientTex": "/assets/materials/tileable/water/depthcolor_ramp/depthcolor_ramp_italy_muddy_b.png",
        "foamTex": "/assets/materials/tileable/water/water_effects/foam2_b.color.dds",
        "rippleTex": "/assets/materials/tileable/water/water_effects/ripple_nm.normal.dds",
        "fresnelBias": 0.12, "fresnelPower": 6, "fullReflect": False, "gridElementSize": 0.8, "gridSize": 200,
        "overallRippleMagnitude": 0.4, "overallWaveMagnitude": 0.02, "reflectivity": 0.6,
        "specularPower": 200, "waterFogDensity": 0.4, "wetDarkening": 0.4, "wetDepth": 0.5,
        "Ripples (texture animation)": [{"rippleDir": [-1, -1], "rippleMagnitude": 0.2, "rippleSpeed": 0.0025, "rippleTexScale": [120, 120]},
                                         {"rippleDir": [1, -1], "rippleMagnitude": 0.3, "rippleSpeed": 0.015, "rippleTexScale": [10, 10]},
                                         {"rippleDir": [-1, 1], "rippleMagnitude": 0.3, "rippleSpeed": 0.05, "rippleTexScale": [2, 2]}],
        "Waves (vertex undulation)": [{"waveDir": [0, -1], "waveMagnitude": 0.05, "waveSpeed": 1},
                                       {"waveDir": [0.3, -1.2], "waveMagnitude": 0.03, "waveSpeed": -1},
                                       {"waveDir": [-0.3, -0.8], "waveMagnitude": 0.03, "waveSpeed": 1}]})
    print("lake level", level)


def stage_backdrop(scene, ctx):
    import backdrop
    backdrop.build(LEVEL_DIR, LEVEL_NAME, scene, ctx.get("lake_level", 270.5))


def stage_buildings(scene, ctx):
    import buildings_mesh
    tiles = buildings_mesh.build(LEVEL_DIR, LEVEL_NAME)
    for shape, origin, ntri in tiles:
        scene.add("MissionGroup/buildings", bng.tsstatic(shape, origin, collision=True, decal=False,
                                                          annotation="BUILDINGS"))
    print("building tiles", len(tiles), "triangles", sum(t[2] for t in tiles))


def stage_vegetation(scene, ctx):
    import vegetation
    vegetation.build(LEVEL_DIR, LEVEL_NAME, scene)


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


PUBLIC_README = [
    ("facciate viste dalla strada con la texture delle foto",
     "intonaco neutro nel colore misurato nelle foto (versione pubblica: nessuna texture fotografica)"),
    ("; texture fotografiche a circa 3 cm/px", "; texture di pietra vanilla"),
    ("le targhe riportano l'immagine vista nella foto, nessun testo inventato",
     "targhe nella forma e nel colore misurati nelle foto (versione pubblica: senza l'immagine del cartello)"),
    ("- Le texture fotografiche delle facciate e dei muri e le targhe dei cartelli derivano da immagini Google "
     "Street View e sono solo per uso personale. Per pubblicare la mod bisogna costruire la versione senza di esse "
     "(`MAGLIASO_NO_PHOTO_TEXTURES=1`).",
     "- Questa è la **versione pubblica**: non contiene immagini tratte da Google Street View. Le panoramiche sono "
     "servite solo come riferimento per misure, posizioni e colori."),
]


def write_info(ctx):
    spawns = ctx.get("spawns", [])
    info = {
        "title": "Strada Cantonale Magliaso - Pura",
        "description": "Ricostruzione in scala 1:1 della Strada Cantonale da Magliaso a Pura (Ticino, CH), "
                       "da 366 panoramiche Street View (ottobre 2022) con dati ufficiali swisstopo "
                       "(swissALTI3D, SWISSIMAGE, swissBUILDINGS3D, swissSURFACE3D) e della misurazione "
                       "ufficiale del Cantone Ticino. Fonti: (c) swisstopo; Ufficio del catasto e dei riordini "
                       "fondiari, Cantone Ticino; (c) OpenStreetMap contributors (ODbL).",
        "previews": [f"{LEVEL_NAME}_preview.jpg"],
        "size": [TER_SIZE, TER_SIZE],
        "authors": "michi (pipeline: Claude)",
        "biome": "Prealpi ticinesi, bosco di castagni", "roads": "Strada cantonale, strade comunali",
        "suitablefor": "Guida su strada di montagna", "features": "Scala reale 1:1, terreno LiDAR",
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
    # preview from the orthophoto around the route
    import rasterio
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        a = s.read(out_shape=(3, 1024, 1024)).transpose(1, 2, 0)
    Image.fromarray(a).save(level_path(f"{LEVEL_NAME}_preview.jpg"), quality=88)
    json.dump({"header": {"name": "DecalData File", "comments": "", "version": 2}, "instances": {}},
              open(level_path("main.decals.json"), "w"))


STAGES = ["roads", "walls", "terrain", "sky", "water", "backdrop", "buildings", "guardrails", "fences", "markings", "ai",
          "props", "vegetation", "spawns"]


def main():
    stages = sys.argv[1:] or STAGES
    if set(stages) == set(STAGES) and os.path.exists(LEVEL_DIR):
        shutil.rmtree(LEVEL_DIR)
    os.makedirs(LEVEL_DIR, exist_ok=True)
    scene, ctx = bng.Scene(), {}
    for st in stages:
        globals()[f"stage_{st}"](scene, ctx)
    scene.write(LEVEL_DIR)
    write_info(ctx)
    print("level written to", LEVEL_DIR)


if __name__ == "__main__":
    main()
