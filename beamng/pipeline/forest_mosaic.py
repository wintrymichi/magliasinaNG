"""v3.1: the forest floor as a mosaic, not as bands (finish step after understory.understory_step).

Up to the first v3.1 nightly the undergrowth of understory.py had two states on the forest floor: the light (the
light twins, a carpet of ferns and brambles) in a band exactly EDGE_M wide along every edge of the wood and in the
gaps between the measured crowns, and the shade (sparse shrubs, dead wood) everywhere else, the same on a sunny
chestnut slope above Caslano as in a north-facing beech wood under Monte Lema. What a wood of the Malcantone shows
from the road is the change: thickets where the sun reaches the ground, bare leaf litter under the closed beech
crowns, stones and outcrops on the steep slopes, a ragged mantle where the wood meets a meadow and almost none
where a narrow road runs under the crowns. This step makes that mosaic from the terrain itself, with the layers
and models the level has already (only two terrain twins and five GroundCovers more, nothing stored per plant):

- the sun: the heat index of every forest vertex (its slope turned to the sun of the afternoon, SUN_AZ/SUN_EL,
  heights smoothed over SMOOTH_M): south and south-west slopes warm, north slopes cold;
- the beech belt: above BEECH_Z (lower on the cold slopes, higher on the warm ones, BEECH_ASPECT_M), fading over
  BEECH_FADE_M;
- the edge (light twins): as wide as the opening beside it lets the light in (OPEN_BOX_M around: a meadow EDGE_MAX,
  a narrow road under the crowns EDGE_MIN), wider on the warm side, ragged (noise, EDGE_RAGGED);
- the gaps of the canopy (light twins): no measured trunk within GAP_M (ragged by GAP_RAGGED) and one within
  GAP_WOOD_M, as understory.light_vertices;
- thickets (light twins) in blobs of about BLOB_M inside the wood: most on warm slopes in the chestnut belt;
- bare leaf litter (the forest verge twins, the floor without undergrowth) in blobs inside the wood: most under
  the beech crowns and on cold slopes;
- outcrops: the forest floor between ROCK_SLOPE and terrain.STEEP_BANK degrees, inside the wood, in small blobs,
  goes to ForestRock (the Rock material, a twin) with gneiss stones of the game standing on it;
- the steep banks (Bank, over terrain.STEEP_BANK degrees: bare up to now) inside the wood (a measured trunk within
  BANK_TREE_M, nothing solid, no terrain skin and no verge within BANK_CLEAR squares) go to BankWood (the Bank
  material, a twin) with stones, dead branches, ferns and small bushes;
- the light gets tufts of woodland grass (the game's long grass billboards), sparse and in clumps.
Nothing is placed within a terrain square of a road, path, wall, building, the railway or the terrain skin: the
verge twins mark those (understory.py), and BankWood keeps BANK_CLEAR squares from all of them. Random fields are
seeded (SEED): the same level gives the same mosaic.

python build_level.py --finish forest_mosaic; patch of a built zip: patch_forest_mosaic.py
"""
import json, os, struct, time, zipfile
import numpy as np
from scipy import ndimage as ndi
from scipy.special import ndtr
import bng
import groundcover
import understory
import walls as pw
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

SEED = 3131
SUN_AZ, SUN_EL = 215.0, 38.0        # degrees: the sun of the early afternoon, south-south-west
SMOOTH_M = 6.0                      # m, the heights smoothed before the slope and the sun
HEAT_SCALE = 0.30                   # cos of incidence above the flat ground's that counts as fully warm (about 25 deg S)
BEECH_Z, BEECH_FADE_M, BEECH_ASPECT_M = 950.0, 160.0, 90.0   # m: the beech belt (groundcover.CHESTNUT_TOP)
OPEN_BOX_M = 51.0                   # m, the side of the square the opening beside an edge is measured in
EDGE_MIN, EDGE_MAX = 3.0, 15.0      # m: the light along a narrow road under the crowns, along a meadow
EDGE_WARM = 3.0                     # m more on a fully warm slope (less on a cold one)
EDGE_RAGGED = 0.40                  # the edge width varies by this share (noise of about BLOB_M)
GAP_M, GAP_RAGGED, GAP_WOOD_M = understory.GAP_M, 2.5, understory.GAP_WOOD_M
BLOB_M = 12.0                       # m, the size (sigma) of the thickets and the bare patches
THICKET = (0.06, 0.12, 0.6)         # share of the inner wood: base, + per warm unit, x (1 - this) in the beech belt
BARE = (0.10, 0.08, 0.20, 0.03, 0.40)   # base, - per warm unit, + in the beech belt, min, max
STEEP_BANK = 40.0                   # degrees: terrain.STEEP_BANK, steeper is Bank already
ROCK_SLOPE = 28.0                   # degrees: steeper forest floor may break into outcrops
ROCK_BLOB_M = 5.0                   # m, the size (sigma) of the outcrops
ROCK_SHARE = 0.18                   # share of the steepest floor (up to STEEP_BANK) that is outcrop
SHADE_CLEAR_M = understory.EDGE_M   # m: the shade (fallen trees, big clumps) begins this far from a road, path, wall,
                                    # building, the railway or the skin; nearer, what is not light is bare litter
BANK_TREE_M = 8.0                   # m: a steep bank with a measured trunk this near is in the wood
BANK_CLEAR = 3                      # terrain squares from anything solid, the skin, the verge twins and the light
SKIN = "level_objects/terrain_skin"   # steep_skin.py: its triangles are a terrain square or less, its vertices mark it
FOREST_ROCK, BANK_WOOD = "ForestRock", "BankWood"
TWIN_OF = {FOREST_ROCK: "Rock", BANK_WOOD: "Bank"}

_EG, _EB, _EF, _ER, _IT = groundcover._EG, groundcover._EB, groundcover._EF, groundcover._ER, groundcover._IT
_ALL = groundcover._ALL
# GroundCovers: name, material, radius, dissolve, grid, seed, maxElements per layer, layers, rows. Billboard rows:
# (uvs, probability, size min, max, clump min, max, clump radius); model rows as groundcover.UNDERSTORY_COVERS.
WOOD_GRASS = ("understory_grass", "mp_gc_grass_long", 50.0, 30.0, 6, 31, 3600, groundcover.LIGHT, [
    (groundcover.LONG_TOP, 1.0, 0.30, 0.55, 2, 5, 0.6),
    (groundcover.LONG_HALF, 0.5, 0.40, 0.70, 1, 3, 0.5),
    (groundcover.SHORT_HALF_R, 0.4, 0.25, 0.40, 2, 4, 0.4)])
# the stones of an outcrop, half in the ground; the Rock layer of the land cover keeps its own look
ROCKS = ("understory_rocks", "mp_gc_grass_short", 70.0, 50.0, 6, 37, 420, (FOREST_ROCK,), [
    (_ER + "eca_rock_small_2.dae", 0.50, 1.0, 3.2, 1, 4, 2.5, 70, _ALL),
    (_ER + "eca_rock_small_3.dae", 0.50, 1.0, 3.0, 1, 3, 2.5, 70, _ALL),
    (_EG + "lush_ferns_02_a.dae", 0.30, 0.6, 0.9, 1, 3, 1.0, 70, _ALL),
    (_IT + "generibush_small.dae", 0.15, 0.5, 0.8, 1, 1, 1.0, 70, _ALL)])
# a wooded steep bank: what holds on a slope over 40 degrees (upright, the GroundCover does not lean them)
BANK = ("understory_bank", "mp_gc_grass_short", 60.0, 40.0, 6, 41, 520, (BANK_WOOD,), [
    (_EG + "lush_ferns_01_b.dae", 0.40, 0.6, 0.9, 1, 3, 1.0, 80, _ALL),
    (_EG + "lush_ferns_02_a.dae", 0.30, 0.6, 1.0, 1, 3, 1.0, 80, _ALL),
    (_IT + "generibush_small.dae", 0.30, 0.5, 0.8, 1, 2, 1.0, 80, _ALL),
    (_IT + "scraggly_bush.dae", 0.20, 0.30, 0.42, 1, 1, 1.0, 80, (-1000.0, 1100.0)),
    (_EF + "fir_dead_branches.dae", 0.15, 0.5, 0.9, 1, 1, 1.0, 80, _ALL),
    (_ER + "eca_rock_small_2.dae", 0.35, 0.8, 2.4, 1, 3, 2.0, 80, _ALL),
    (_ER + "eca_rock_small_3.dae", 0.30, 0.8, 2.2, 1, 2, 2.0, 80, _ALL)])
COVERS = (WOOD_GRASS, ROCKS, BANK)


def _field(shape, sigma_m, rng):
    """A random field, uniform in 0..1 (by its normal CDF): gaussian noise blurred to sigma_m, with a third of it
    blurred to sigma_m / 3 on top (one scale alone thresholds into round blobs with smooth outlines)."""
    out = np.zeros(shape, np.float32)
    for s, wgt in ((sigma_m, 1.0), (sigma_m / 3, 0.55)):
        a = rng.standard_normal(shape, dtype=np.float32)
        ndi.gaussian_filter(a, s / TER_SQUARE, output=a, mode="reflect", truncate=3.0)
        a *= wgt / max(float(a[::7, ::7].std()), 1e-6)
        out += a
        del a
    out /= max(float(out[::7, ::7].std()), 1e-6)
    return ndtr(out).astype(np.float32)


def _smoothstep(a, lo, hi):
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def sun_and_slope(H):
    """(heat index -1..1, slope in degrees) of every vertex, float32 (n, n); H the heights (n, n) in m."""
    Hs = ndi.gaussian_filter(H.astype(np.float32), SMOOTH_M / TER_SQUARE / 2, mode="nearest")
    gy, gx = np.gradient(Hs, TER_SQUARE)             # rows run north (understory.trunks: r = (y - Y0) / square)
    del Hs
    az, el = np.radians(SUN_AZ), np.radians(SUN_EL)
    norm = np.sqrt(1 + gx * gx + gy * gy)
    inc = (-gx * np.sin(az) * np.cos(el) - gy * np.cos(az) * np.cos(el) + np.sin(el)) / norm
    heat = np.clip((inc - np.sin(el)) / HEAT_SCALE, -1, 1).astype(np.float32)
    slope = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy))).astype(np.float32)
    return heat, slope


def mosaic(H, lay, names, trees, near_solid):
    """The new layer map (n, n) uint8 and the names with the twins, and counts. H the heights (n, n) m, lay and
    names the layers after understory.understory_step, trees (k, 2) the trunks, near_solid (n, n) bool the vertices
    within a square of a solid mesh or the terrain skin."""
    import cv2
    n = lay.shape[0]
    rng = np.random.default_rng(SEED)
    ids = {m: names.index(m) for m in names}
    shade_ids = [ids[m] for m in groundcover.FOREST_LAYERS]
    light_ids = [ids[m] for m in groundcover.LIGHT]
    wood = np.isin(lay, shade_ids + light_ids)
    base = lay.copy()                                    # the plain layer of every forest vertex (no light twin)
    for m, t in groundcover.FOREST_LIGHT.items():
        base[lay == ids[t]] = ids[m]
    stats = {"wood_vertices": int(wood.sum()),
             "before": {m: int((lay == ids[m]).sum()) for m in groundcover.FOREST_LAYERS + groundcover.LIGHT}}

    heat, slope = sun_and_slope(H)
    beech = _smoothstep(H - BEECH_ASPECT_M * heat, BEECH_Z - BEECH_FADE_M / 2, BEECH_Z + BEECH_FADE_M / 2)
    del H

    # the edge: specks of another layer inside the wood are no edge (understory.light_vertices), nor are the steep
    # banks (Bank: the cut slopes of a road in the wood are wood, its opening is the road)
    bank = lay == ids["Bank"]
    _, comp, st, _ = cv2.connectedComponentsWithStats((~(wood | bank)).view(np.uint8), connectivity=8)
    speck = st[:, cv2.CC_STAT_AREA] * TER_SQUARE ** 2 < understory.SPECK_M2
    speck[0] = False
    inner = wood | bank | speck[comp]
    del comp
    d = cv2.distanceTransform(inner.view(np.uint8), cv2.DIST_L2, 5) * TER_SQUARE
    k = int(round(OPEN_BOX_M / TER_SQUARE)) | 1
    opening = cv2.blur((~inner).astype(np.float32), (k, k))
    del inner
    # a narrow road under the crowns opens some 10 % of the box, a meadow beside the wood half of it
    w = EDGE_MIN + (EDGE_MAX - EDGE_MIN) * np.clip((opening - 0.08) / 0.40, 0, 1)
    del opening
    w += EDGE_WARM * heat
    w *= 1 + EDGE_RAGGED * (2 * _field((n, n), BLOB_M, rng) - 1)
    edge = wood & (d <= np.maximum(w, 1.5))
    interior = wood & (d > w + 3.0)
    del d, w

    c = np.round((trees[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
    r = np.round((trees[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
    ok = (r >= 0) & (r < n) & (c >= 0) & (c < n)
    free = np.full((n, n), 255, np.uint8)
    free[r[ok], c[ok]] = 0
    dt = cv2.distanceTransform(free, cv2.DIST_L2, 5) * TER_SQUARE      # to the nearest trunk
    del free
    gap = wood & ~edge & (dt > GAP_M + GAP_RAGGED * (2 * _field((n, n), BLOB_M, rng) - 1)) & (dt <= GAP_WOOD_M)
    bank_trees = dt <= BANK_TREE_M
    del dt

    warm = np.clip(heat, 0, 1)
    p_thicket = (THICKET[0] + THICKET[1] * heat) * (1 - THICKET[2] * beech)
    thicket = interior & ~gap & (_field((n, n), BLOB_M, rng) < np.clip(p_thicket, 0, 0.25))
    del p_thicket
    light = edge | gap | thicket
    # near a solid mesh no shade (its fallen trunks reach 10 m): light or bare litter, in patches
    import cv2 as _cv2
    solid = near_solid | np.isin(lay, [ids[t] for t in understory.TWIN.values()])
    dsol = _cv2.distanceTransform((~solid).view(np.uint8), _cv2.DIST_L2, 5) * TER_SQUARE
    del solid
    roadside = wood & ~light & (dsol <= SHADE_CLEAR_M)
    del dsol
    road_light = roadside & (_field((n, n), BLOB_M / 2, rng) < 0.5)
    light |= road_light
    p_bare = np.clip(BARE[0] - BARE[1] * heat + BARE[2] * beech, BARE[3], BARE[4])
    bare = (interior & ~light & (_field((n, n), BLOB_M, rng) < p_bare)) | (roadside & ~road_light)
    del p_bare, warm, beech
    steep = np.clip((slope - ROCK_SLOPE) / (STEEP_BANK - ROCK_SLOPE), 0, 1)
    rock = interior & (slope >= ROCK_SLOPE) & (_field((n, n), ROCK_BLOB_M, rng) < ROCK_SHARE * steep)
    del steep, heat

    names2 = list(names) + [FOREST_ROCK, BANK_WOOD]
    out = lay.copy()
    out[wood] = base[wood]
    for m, t in groundcover.FOREST_LIGHT.items():
        out[light & (base == ids[m])] = ids[t]
    for m, t in understory.TWIN.items():
        out[bare & (base == ids[m])] = ids[t]
    out[rock] = names2.index(FOREST_ROCK)
    # the wooded steep banks, clear of everything that is not wood or bank
    keep_off = near_solid | ~(wood | bank) | np.isin(lay, [ids[t] for t in understory.TWIN.values()])
    keep_off = ndi.binary_dilation(keep_off, np.ones((2 * BANK_CLEAR + 1,) * 2, bool))
    bankwood = bank & bank_trees & ~keep_off
    out[bankwood] = names2.index(BANK_WOOD)
    del keep_off, bank_trees, base
    stats.update({
        "roadside_light": int(road_light.sum()), "roadside_bare": int((roadside & ~road_light).sum()),
        "edge": int(edge.sum()), "gap": int((gap & ~edge).sum()), "thicket": int(thicket.sum()),
        "bare": int(bare.sum()), "outcrop": int(rock.sum()), "bank": int(bank.sum()), "bank_wood": int(bankwood.sum()),
        "after": {m: int((out == names2.index(m)).sum()) for m in
                  groundcover.FOREST_LAYERS + groundcover.LIGHT + tuple(understory.TWIN.values()) + (FOREST_ROCK, BANK_WOOD)}})
    stats["light_share_before"] = round(sum(stats["before"][m] for m in groundcover.LIGHT) / max(1, stats["wood_vertices"]), 3)
    stats["light_share_after"] = round(sum(stats["after"][m] for m in groundcover.LIGHT) / max(1, stats["wood_vertices"]), 3)
    return out, names2, stats


def objects():
    """The GroundCovers of COVERS, one per layer (at most 8 Types each)."""
    out = []
    for name, mat, radius, dissolve, grid, seed, max_el, layers, rows in COVERS:
        assert len(rows) <= 8, name
        for k, layer in enumerate(layers):
            types = []
            for row in rows:
                if isinstance(row[0], str):                  # a model
                    shape, p, smin, smax, cmin, cmax, crad, slope, (zmin, zmax) = row
                    t = groundcover._t(layer, [0, 0, 1, 1], p, smin, smax, cmin, cmax, crad, 0.0)
                    t.update(shapeFilename=shape, maxSlope=slope, minElevation=zmin, maxElevation=zmax)
                else:                                        # a billboard of the material
                    uvs, p, smin, smax, cmin, cmax, crad = row
                    t = groundcover._t(layer, uvs, p, smin, smax, cmin, cmax, crad, 0.15)
                types.append(t)
            o = {"name": f"{name}_{layer}", "class": "GroundCover", "persistentId": bng.pid(),
                 "position": [0, 0, 0], "material": mat, "radius": radius, "dissolveRadius": dissolve,
                 "gridSize": grid, "zOffset": 0, "seed": seed + 7 * k, "maxElements": max_el,
                 "maxBillboardTiltAngle": 40, "shapeCullRadius": radius, "shapesCastShadows": False, "Types": types}
            o.update(groundcover.WIND)
            out.append(o)
    return out


def check_light_reach():
    """The light along the roads begins 1.5 m from a road mesh: the grass there is low anyway; the models of
    ROCKS and BANK stand only BANK_CLEAR squares or EDGE_MIN + 3 m inside the wood."""
    b = json.load(open(groundcover.BOUNDS))
    for name, _, _, _, _, _, _, _, rows in (ROCKS, BANK):
        for shape, _, _, smax, *_ in rows:
            lo, hi = b[shape]
            reach = smax * max(abs(lo[0]), abs(lo[1]), hi[0], hi[1])
            assert reach < min(BANK_CLEAR, (EDGE_MIN + 3.0) / TER_SQUARE) * TER_SQUARE + 1.0, (name, shape, reach)


def skin_cells(zi, lv, n):
    """(n, n) bool: the terrain vertices under a vertex of the terrain skin (steep_skin.py). Its triangles are
    about a terrain square: the vertices alone mark it, far faster than understory.face_cells over 4 GB of DAE."""
    import optimize_level
    out = np.zeros((n, n), bool)
    f = f"{lv}/main/MissionGroup/{SKIN}/items.level.json"
    if f not in zi.NameToInfo:
        return out
    for o in understory.read_items(zi, f):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V = optimize_level._arr(zi.read(sn).decode("utf-8"), "g-pa").reshape(-1, 3)[:, :2]
        V = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)[:2]
        c = np.round((V[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
        r = np.round((V[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
        ok = (r >= 0) & (r < n) & (c >= 0) & (c < n)
        out[r[ok], c[ok]] = True
    return out


def changes(zi, report=None):
    """{name: bytes} of the files this step rewrites, from zi (bng.LevelFiles or a zipfile.ZipFile of the level)."""
    t0 = time.time()
    lv = f"levels/{LEVEL_NAME}"
    check_light_reach()
    blk = next(o for o in understory.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = pw.read_ter(data)
    if FOREST_ROCK in names or BANK_WOOD in names:
        raise SystemExit("forest_mosaic: the level has the mosaic already")
    if not all(m in names for m in groundcover.LIGHT):
        raise SystemExit("forest_mosaic: run understory first (no light twins in the level)")
    near = pw.corners_of(understory.face_cells(zi, lv, n)) | skin_cells(zi, lv, n)
    near = ndi.binary_dilation(near, np.ones((3, 3), bool))
    print("forest_mosaic: solid meshes and skin read (%.0f s)" % (time.time() - t0), flush=True)
    H = (Z0 + q.astype(np.float32) / np.float32(65535.0) * np.float32(MAXH))
    new_lay, names2, stats = mosaic(H, lay, names, understory.trunks(zi, lv), near)
    del H, near
    print("forest_mosaic: %s (%.0f s)" % (json.dumps(stats), time.time() - t0), flush=True)
    tail = struct.pack("<I", len(names2)) + b"".join(struct.pack("<B", len(s.encode())) + s.encode() for s in names2)
    new_ter = data[:5 + 2 * n * n] + np.ascontiguousarray(new_lay).tobytes() + tail
    assert new_ter[:5 + 2 * n * n] == data[:5 + 2 * n * n]               # heights as they were
    new = {ter_name: new_ter}
    tj_name = f"{lv}/theTerrain.terrain.json"
    tj = json.loads(zi.read(tj_name))
    tj["materials"] = names2
    new[tj_name] = json.dumps(tj, indent=2).encode("utf-8")
    mats_name = f"{lv}/art/terrains/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    for twin, of in TWIN_OF.items():
        m = next(v for v in mats.values() if v.get("class") == "TerrainMaterial" and v.get("internalName") == of)
        tw = dict(m, internalName=twin, persistentId=bng.pid())
        mats[f"{twin}-{tw['persistentId']}"] = tw
    new[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    veg_name = f"{lv}/main/MissionGroup/level_objects/vegetation/items.level.json"
    veg = understory.read_items(zi, veg_name)
    ours = {o["name"] for o in objects()}
    veg = [o for o in veg if o.get("name") not in ours]
    parent = next((o["__parent"] for o in veg if o.get("class") == "GroundCover"), "vegetation")
    for o in objects():
        o["__parent"] = parent
        veg.append(o)
    new[veg_name] = understory.write_items(veg)
    if report:
        stats["groundcovers"] = sorted(ours)
        stats["terrain_heights_unchanged"] = True
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(stats, open(report, "w"), indent=1)
    return new, stats


def forest_mosaic_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    new, _ = changes(zi, report)
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new:
                ni = zipfile.ZipInfo(i.filename, now)                     # converted again by the game
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    print("forest_mosaic: written in %.0f s" % (time.time() - t0), flush=True)
    return 0
