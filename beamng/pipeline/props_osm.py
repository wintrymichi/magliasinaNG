"""Signs and street furniture of the network from OpenStreetMap (v2.1), beyond the Strada Cantonale
Magliaso - Pura, whose objects are measured in the panoramas (props.py, carried over in the cloud
build by carryover.py).

Only objects that OSM records at a place are built, and only with models the level already uses:
- STOP (highway=stop) and give-way (highway=give_way) signs: the Swiss signals 3.01 and 3.02 on a grey
  steel pole at the right-hand edge of the road that has to stop or give way, facing the traffic that
  comes to the junction (the OSM direction tag where there is one, else towards the nearest junction
  of the way). The plates are drawn here (a red octagon with STOP, a white triangle with a red
  border), not taken from photos;
- benches (amenity=bench) and litter bins (amenity=waste_basket): the vanilla bench and bin of
  props.py, turned along the nearest road or path;
- street lights (highway=street_lamp): the Italian single-arm light of props.py, the arm over the
  nearest road;
- bus stops (highway=bus_stop, v2.2): a grey pole beside the road with the yellow stop sign across it
  (a bus and the name of the stop in black, drawn here as the signs along the streets of the area look)
  and a timetable board; where OSM records a shelter, a steel and glass shelter with a bench behind it.
- v3.0.40: the benches, litter bins, fire hydrants and junction boxes the open street photos show
  (street_objects.py, dati/street_objects.json) where OSM has none of the kind within PHOTO_NEAR m: the same
  models (a junction box a grey cabinet), turned like the furniture of OSM.
- v3.0.40: the fountains and drinking water points of OSM: a granite basin (Italy's kerb stone) with its water and a
  pillar with a spout at one end, along the road, as long as the street photos show it (street_fountains.py,
  dati/street_fountains.json); the small ones (drinking water, bubblers) a stone bowl at the foot of the pillar;
  none where several photos see the place and no fountain.
Nothing is placed on the Italian side (outside the land of the cadastral survey), on a carriageway,
inside a building or a wall, in the middle of a road of the network (blocked, build_level.stage_props)
or within CORRIDOR m of the Street View route; a sign that does not find free ground beside the road
within 1.5 m is left out.
    build(level_dir, scene, ground, on_carriageway, blocked, corridor_line) -> counts
"""
import math, os
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont
import bng
from config import LEVEL_NAME
import osm

LIGHT = "/levels/italy/art/shapes/buildings/italy_light_single.dae"      # arm along the local +x axis
BENCH = "/levels/east_coast_usa/art/shapes/clutter/clutter_city_bench_wood.dae"
BIN = "/levels/italy/art/shapes/buildings/italy_clutter_metal_bin.DAE"
HYDRANT = "/levels/italy/art/shapes/buildings/italy_clutter_fire_hydrant.DAE"
CORRIDOR = 60.0
PHOTO_OBJECTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "street_objects.json")
PHOTO_KINDS = {"bench": "bench", "trash_can": "waste_basket", "hydrant": "hydrant", "junction_box": "junction_box"}
PHOTO_NEAR = 3.0          # m: furniture of OSM of the same kind this near is the one the photos show
PHOTO_FOUNTAINS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                               "street_fountains.json")
FOUNTAIN = (1.8, 0.75, 0.7)         # m: length, width, height of the granite basin of a village fountain
FOUNTAIN_SMALL = (0.5, 0.36, 0.45)  # m: the stone bowl at the foot of a small drinking fountain
FOUNTAIN_SMALL_TAGS = {"bubbler", "drinking", "nozzle", "bottle_refill"}
RIM = 0.12                # m: the basin's walls
WATER_DOWN = 0.08         # m: the water under the rim
PILLAR = 0.32             # m: side of the pillar at the end of the basin (its spout over the water)
STOP_SIZE = 0.60          # m across the octagon (Swiss sizes 60 / 90 / 110 cm; 60 cm on local roads)
GIVEWAY_SIZE = 0.90       # m, side of the triangle (60 / 90 / 120 cm)
PLATE_LOW = 1.50          # m, underside of a plate over the ground
EDGE_OUT = 0.60           # m from the edge of the carriageway to the pole
RED = (193, 18, 28)       # RAL 3020 traffic red
L = f"/levels/{LEVEL_NAME}"


def _quad(a, b, c, d, want):
    """Two triangles of the quad a b c d (in order round it), wound so that their normal points along want."""
    if np.cross(b - a, c - a) @ want < 0:
        b, d = d, b
    return [a, b, c, a, c, d]


def fountain(c, t, L, W, z0, zt, pillar_h):
    """Triangles (stone, water, metal) of a village fountain: a basin L x W (along the unit direction t and across
    it) from z0 to its rim at zt, the water WATER_DOWN m under the rim, and a pillar at its +t end, pillar_h m over
    the rim, with a spout over the water."""
    t3, n3, up = np.array([t[0], t[1], 0.0]), np.array([-t[1], t[0], 0.0]), np.array([0.0, 0.0, 1.0])
    C = np.array([c[0], c[1], 0.0])
    P = lambda a, b, z: C + a * t3 + b * n3 + z * up
    o = [(L / 2, W / 2), (-L / 2, W / 2), (-L / 2, -W / 2), (L / 2, -W / 2)]
    i = [(a - np.sign(a) * RIM, b - np.sign(b) * RIM) for a, b in o]
    zw = zt - WATER_DOWN
    stone = []
    for k in range(4):
        (a0, b0), (a1, b1) = o[k], o[(k + 1) % 4]
        (i0, j0), (i1, j1) = i[k], i[(k + 1) % 4]
        out = 0.5 * (a0 + a1) * t3 + 0.5 * (b0 + b1) * n3
        stone += _quad(P(a0, b0, z0), P(a1, b1, z0), P(a1, b1, zt), P(a0, b0, zt), out)              # outside
        stone += _quad(P(a0, b0, zt), P(a1, b1, zt), P(i1, j1, zt), P(i0, j0, zt), up)              # rim
        stone += _quad(P(i0, j0, zw - 0.05), P(i1, j1, zw - 0.05), P(i1, j1, zt), P(i0, j0, zt), -out)  # inside
    water = _quad(*(P(a, b, zw) for a, b in i), up)
    metal = []
    if pillar_h > 0:
        t2, n2 = np.asarray(t, float), np.array([-t[1], t[0]], float)
        pc = np.asarray(c) + t2 * (L / 2 + PILLAR / 2 - 0.02)
        stone += list(box(pc, t2, n2, PILLAR, PILLAR, z0, zt + pillar_h))
        stone += list(box(pc, t2, n2, PILLAR + 0.06, PILLAR + 0.06, zt + pillar_h, zt + pillar_h + 0.07))   # its cap
        zs = zt + 0.45 * pillar_h
        metal = list(box(np.asarray(c) + t2 * (L / 2 - 0.16), t2, n2, 0.30, 0.035, zs, zs + 0.035))
    return np.array(stone), np.array(water), np.array(metal).reshape(-1, 3)


def _font(px):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, px)
    return ImageFont.load_default(size=px)


def stop_texture(n=256):
    """RGBA of the Swiss STOP signal (3.01): red octagon, narrow white border, white STOP."""
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = np.pi / 8 + np.arange(8) * np.pi / 4
    oct_ = lambda r: [(n / 2 + r * np.cos(t), n / 2 + r * np.sin(t)) for t in a]
    R = n / 2 / np.cos(np.pi / 8) - 1
    d.polygon(oct_(R), fill=(255, 255, 255, 255))
    d.polygon(oct_(R * 0.93), fill=RED + (255,))
    f = _font(int(n * 0.30))
    w = d.textlength("STOP", font=f)
    d.text(((n - w) / 2, n * 0.34), "STOP", font=f, fill=(255, 255, 255, 255))
    return img


def giveway_texture(n=256):
    """RGBA of the Swiss give-way signal (3.02): white triangle pointing down, red border."""
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    h = n * np.sqrt(3) / 2
    top = (n - h) / 2
    tri = lambda k: [(n / 2 - k * n / 2, top + (1 - k) * h / 3), (n / 2 + k * n / 2, top + (1 - k) * h / 3),
                     (n / 2, top + h - (1 - k) * 2 * h / 3)]
    d.polygon(tri(1.0), fill=RED + (255,))
    d.polygon(tri(0.62), fill=(255, 255, 255, 255))
    return img


def save_rgba(img, folder, name):
    """An RGBA sign image as <name>_b.color.png (RGB) and <name>_o.data.png (opacity)."""
    img = img.convert("RGBA")
    rgb = Image.new("RGB", img.size, (128, 128, 128))
    rgb.paste(img.convert("RGB"), (0, 0), img.split()[3])
    rgb.save(os.path.join(folder, f"{name}_b.color.png"))
    img.split()[3].save(os.path.join(folder, f"{name}_o.data.png"))


BUS_YELLOW = (250, 200, 30)


def bus_texture(name, w=256, h=320):
    """RGBA of a bus stop sign as seen along the streets of the area: a yellow plate with a black rim,
    a bus drawn in black and the name of the stop (from OpenStreetMap). Drawn here, not photographed."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, w - 3, h - 3], radius=14, fill=BUS_YELLOW + (255,), outline=(20, 20, 20, 255), width=6)
    # the bus: body, windows, wheels
    bx0, by0, bx1, by1 = w * 0.16, h * 0.14, w * 0.84, h * 0.55
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=12, fill=(20, 20, 20, 255))
    ww = (bx1 - bx0 - 30) / 3
    for k in range(3):
        x0 = bx0 + 10 + k * (ww + 5)
        d.rectangle([x0, by0 + 12, x0 + ww, by0 + (by1 - by0) * 0.5], fill=BUS_YELLOW + (255,))
    for cx in (bx0 + (bx1 - bx0) * 0.24, bx0 + (bx1 - bx0) * 0.76):
        d.ellipse([cx - 16, by1 - 12, cx + 16, by1 + 20], fill=(20, 20, 20, 255), outline=BUS_YELLOW + (255,), width=4)
    # the name of the stop, split on its comma (village, stop)
    parts = [q.strip() for q in (name or "").split(",") if q.strip()][:2]
    y = h * 0.66
    for q in parts:
        px = 30
        f = _font(px)
        while d.textlength(q, font=f) > w - 30 and px > 12:
            px -= 2
            f = _font(px)
        d.text(((w - d.textlength(q, font=f)) / 2, y), q, font=f, fill=(20, 20, 20, 255))
        y += px + 8
    return img


def timetable_texture(w=128, h=192):
    """A timetable board: white paper behind a frame, lines of print (no real text)."""
    img = Image.new("RGBA", (w, h), (235, 235, 230, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=(40, 40, 40, 255), width=5)
    d.rectangle([8, 8, w - 9, 30], fill=BUS_YELLOW + (255,))
    rng = np.random.default_rng(4)
    for y in range(40, h - 12, 7):
        x1 = int(rng.uniform(0.45, 0.9) * (w - 16)) + 8
        d.line([12, y, x1, y], fill=(90, 90, 90, 255), width=2)
    return img


def box(c, t, n, w, dpt, z0, z1):
    """Triangles of a box centred at c (2D), w along t, dpt along n, from z0 to z1."""
    corners = [c + t * sx * w / 2 + n * sy * dpt / 2 for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    out = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        out += [np.r_[a, z0], np.r_[b, z0], np.r_[b, z1], np.r_[a, z0], np.r_[b, z1], np.r_[a, z1]]
    top = [np.r_[corners[i], z1] for i in (0, 1, 2)] + [np.r_[corners[i], z1] for i in (0, 2, 3)]
    return np.array(out + top)


def bus_stop(mb, scene, g, node, x, y, ground, on_carriageway, blocked, wtree, drive, sign_dir, textures, mats):
    """A bus stop at an OSM node: the pole with the yellow sign across the road (both faces) and the
    timetable, off the carriageway; a shelter with a bench behind it where OSM records one. Returns
    (x, y, shelter) or None."""
    t = node["tags"]
    base = np.array([x, y])
    # the road it serves: the nearest drivable way
    lines = [w["line"] for w in drive]
    if not lines:
        return None
    if "_tree" not in textures:
        textures["_tree"] = shapely.STRtree(lines)
    j = textures["_tree"].nearest(shapely.Point(x, y))
    line = lines[j]
    q = np.asarray(shapely.shortest_line(line, shapely.Point(x, y)).coords)[0]
    s_ = line.project(shapely.Point(q))
    a_ = np.asarray(line.interpolate(max(s_ - 2, 0)).coords[0])
    b_ = np.asarray(line.interpolate(min(s_ + 2, line.length)).coords[0])
    tng = (b_ - a_) / max(np.hypot(*(b_ - a_)), 1e-9)
    out = base - q
    if np.hypot(*out) < 0.5:                              # on the axis: the right of the way's direction
        out = np.array([tng[1], -tng[0]])
    out = out / max(np.hypot(*out), 1e-9)
    # off the carriageway: from the road outwards, the first free ground
    c = None
    for dist in np.arange(0.0, 8.0, 0.25):
        p = q + out * dist
        if not on_carriageway([p[0]], [p[1]])[0]:
            for extra in (0.4, 0.8, 1.2):
                cand = q + out * (dist + extra)
                if not on_carriageway([cand[0]], [cand[1]])[0] and not blocked([cand[0]], [cand[1]])[0]:
                    c = cand
                    break
            break
    if c is None:
        return None
    name = t.get("name", "")
    import hashlib
    key = "bus_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
    if key not in textures:
        save_rgba(bus_texture(name), sign_dir, key)
        S_ = f"{L}/art/shapes/signs"
        mats.append(bng.material(f"mp_osm_{key}", f"{S_}/{key}_b.color.png", roughness=0.35, alpha_test=100,
                                 ground_type="METAL", detail={"opacityMap": f"{S_}/{key}_o.data.png"}))
        textures[key] = True
    z = float(ground([c[0]], [c[1]])[0])
    top = z + 2.75
    V = tube(c, z - 0.3, top + 0.05, r=0.035)
    mb.add("mp_osm_pole", V, uvs=V[:, :2] + V[:, 2:3], normals=bng.flat_normals_soup(V))
    for nrm in (tng, -tng):                              # the sign faces both ways along the road
        plate(mb, f"mp_osm_{key}", c, nrm, top - 0.25, 0.40, 0.50)
    tt = c - out * 0.0 + out * 0.05
    plate(mb, "mp_osm_timetable", tt, -out, z + 1.35, 0.30, 0.45)
    shelter = t.get("shelter") == "yes"
    if shelter:
        sc = c + out * 1.6 - tng * 2.0
        pts = [sc + tng * u + out * v for u in (-1.6, 1.6) for v in (-0.8, 0.8)]
        if any(on_carriageway([p[0]], [p[1]])[0] or blocked([p[0]], [p[1]])[0] for p in pts):
            shelter = False
        else:
            zs = float(ground([sc[0]], [sc[1]])[0])
            for u in (-1.5, 1.5):
                for v in (-0.65, 0.65):
                    P = box(sc + tng * u + out * v, tng, out, 0.08, 0.08, zs, zs + 2.35)
                    mb.add("mp_osm_shelter_frame", P, uvs=P[:, :2], normals=bng.flat_normals_soup(P))
            R = box(sc, tng, out, 3.3, 1.7, zs + 2.35, zs + 2.45)
            mb.add("mp_osm_shelter_roof", R, uvs=R[:, :2], normals=bng.flat_normals_soup(R))
            Gb = box(sc + out * 0.66, tng, out, 3.0, 0.02, zs + 0.15, zs + 2.3)
            mb.add("mp_osm_shelter_glass", Gb, uvs=Gb[:, :2], normals=bng.flat_normals_soup(Gb))
            for u in (-1.48, 1.48):
                Gs = box(sc + tng * u, tng, out, 0.02, 1.2, zs + 0.15, zs + 2.3)
                mb.add("mp_osm_shelter_glass", Gs, uvs=Gs[:, :2], normals=bng.flat_normals_soup(Gs))
            theta = math.atan2(-out[1], -out[0])
            scene.add(g + "/furniture", bng.tsstatic(BENCH, (sc[0] + out[0] * 0.3, sc[1] + out[1] * 0.3, zs),
                                                      rot=bng.rot_local_x_to(theta + math.pi / 2), collision=True))
    return float(c[0]), float(c[1]), shelter


def tube(c, z0, z1, r=0.03, n=8):
    a = np.linspace(0, 2 * np.pi, n + 1)
    ring = np.column_stack([np.cos(a), np.sin(a)]) * r + c
    out = []
    for k in range(n):
        p0, p1 = ring[k], ring[k + 1]
        out += [np.r_[p0, z0], np.r_[p1, z0], np.r_[p1, z1], np.r_[p0, z0], np.r_[p1, z1], np.r_[p0, z1]]
    return np.array(out)


def plate(mb, mat, c, nrm, zc, w, h):
    """A flat plate w x h m centred at (c, zc) facing nrm (2D), with a grey back."""
    tng = np.array([nrm[1], -nrm[0]])
    p = c + nrm * 0.035
    A = np.r_[p - tng * w / 2, zc - h / 2]
    B = np.r_[p + tng * w / 2, zc - h / 2]
    C = np.r_[p + tng * w / 2, zc + h / 2]
    D = np.r_[p - tng * w / 2, zc + h / 2]
    front = np.array([A, B, C, A, C, D])
    uv = np.array([[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]], float)
    mb.add(mat, front, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
    back = front[::-1] - np.r_[nrm * 0.008, 0]
    mb.add("mp_osm_sign_back", back, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))


def approach(way_nodes, way_xy, k, branches, direction):
    """Unit vector of the traffic that comes to the stop at vertex k of a way: the OSM direction
    (forward / backward along the way); without one, towards the junction the node is on (at an end
    of the way) or the nearest junction along the way. None when it cannot be told."""
    def step(sgn):
        j = k + sgn
        if 0 <= j < len(way_xy):
            v = way_xy[j] - way_xy[k]
        elif 0 <= k - sgn < len(way_xy):
            v = way_xy[k] - way_xy[k - sgn]
        else:
            return None
        n = np.hypot(*v)
        return v / n if n > 1e-9 else None
    if direction in ("forward", "backward"):
        return step(1 if direction == "forward" else -1)
    if branches.get(way_nodes[k], 0) >= 3:            # the node is the junction: traffic arrives at it
        if k == len(way_nodes) - 1:
            return step(1)
        if k == 0:
            return step(-1)
        return None
    junctions = [i for i, nd in enumerate(way_nodes) if branches.get(nd, 0) >= 3 and i != k]
    if not junctions:
        return None
    j = min(junctions, key=lambda i: abs(i - k))
    return step(1 if j > k else -1)


def build(level_dir, scene, ground, on_carriageway, blocked, corridor_line):
    """ground(x, y) -> z of the surface (road or terrain); on_carriageway(x, y) -> bool array;
    blocked(x, y) -> bool array (building, wall, middle of a road); corridor_line: the Street View route."""
    if not osm.available():
        print("no OSM data (download_osm.py): no signs and furniture from OSM")
        return {}
    ways, nodes = osm.load()
    drive = [w for w in ways if w["tags"].get("highway") in osm.DRIVE]
    walk = [w for w in ways if w["tags"].get("highway") in osm.DRIVE | {"footway", "path", "pedestrian", "cycleway",
                                                                         "steps", "living_street"}]
    branches = {}                                     # roads leaving every node: 3 or more at a junction
    for w in drive:
        for k, nd in enumerate(w["nodes"]):
            branches[nd] = branches.get(nd, 0) + (1 if k in (0, len(w["nodes"]) - 1) else 2)
    node_ways = {}
    for wi, w in enumerate(drive):
        for k, nd in enumerate(w["nodes"]):
            node_ways.setdefault(nd, []).append((wi, k))
    wtree = shapely.STRtree([w["line"] for w in walk])
    near_route = lambda x, y: corridor_line is not None and corridor_line.distance(shapely.Point(x, y)) < CORRIDOR
    import area
    import pickle
    from config import WORK
    playable = area.polygon()
    shapely.prepare(playable)
    inside = lambda x, y: shapely.contains_xy(playable, x, y)
    # only on the Swiss side, the land of the cadastral survey: the Italian side of the map has its
    # terrain and landscape only, no streets or buildings for the furniture of OSM to stand by
    lcsf = shapely.STRtree([g for geoms in pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))["LCSF"].values()
                            for g, _ in geoms])
    swiss = lambda x, y: len(lcsf.query(shapely.Point(x, y), predicate="within")) > 0
    counts = {"stop": 0, "give_way": 0, "bench": 0, "waste_basket": 0, "street_lamp": 0, "bus_stop": 0, "shelter": 0,
              "left_out": 0}
    import italy_mats as it
    sign_dir = os.path.join(level_dir, "art", "shapes", "signs")
    os.makedirs(sign_dir, exist_ok=True)
    # v2.2: RGB colour and a separate opacity map, the naming of the BeamNG texture cooker
    save_rgba(stop_texture(), sign_dir, "osm_stop")
    save_rgba(giveway_texture(), sign_dir, "osm_giveway")
    save_rgba(timetable_texture(), sign_dir, "osm_timetable")
    S_ = f"{L}/art/shapes/signs"
    mats = [bng.material("mp_osm_stop", f"{S_}/osm_stop_b.color.png", roughness=0.35, alpha_test=100,
                         ground_type="METAL", detail={"opacityMap": f"{S_}/osm_stop_o.data.png"}),
            bng.material("mp_osm_giveway", f"{S_}/osm_giveway_b.color.png", roughness=0.35, alpha_test=100,
                         ground_type="METAL", detail={"opacityMap": f"{S_}/osm_giveway_o.data.png"}),
            bng.material("mp_osm_timetable", f"{S_}/osm_timetable_b.color.png", roughness=0.4, ground_type="METAL"),
            bng.material("mp_osm_sign_back", base_color=[0.55, 0.56, 0.57, 1], roughness=0.5, metallic=0.5),
            bng.material("mp_osm_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.5, metallic=0.6),
            bng.material("mp_osm_shelter_frame", base_color=[0.30, 0.32, 0.34, 1], roughness=0.45, metallic=0.7),
            bng.material("mp_osm_shelter_glass", base_color=[0.55, 0.62, 0.66, 1], roughness=0.08, metallic=0.1),
            bng.material("mp_osm_shelter_roof", base_color=[0.70, 0.71, 0.72, 1], roughness=0.5, metallic=0.4),
            bng.material("mp_osm_cabinet", base_color=[0.62, 0.63, 0.60, 1], roughness=0.6, metallic=0.2),
            it.material("mp_osm_fountain_stone", "italy_curb_concrete", ground_type="ROCK"),
            bng.material("mp_osm_fountain_water", base_color=[0.10, 0.13, 0.13, 1], roughness=0.03, metallic=0.3)]
    bus_textures = {}
    mb = bng.MeshBuilder()
    g = "MissionGroup/props/osm"
    placed_list = []

    def facing(x, y):
        """Heading (radians, of the local +x axis) towards the nearest road or path within 30 m."""
        near = wtree.query(shapely.Point(x, y), predicate="dwithin", distance=30.0)
        if not len(near):
            return 0.0
        lines = [walk[i]["line"] for i in near]
        j = int(np.argmin(shapely.distance(shapely.Point(x, y), lines)))
        q = np.asarray(shapely.shortest_line(lines[j], shapely.Point(x, y)).coords)[0]
        to = np.array([q[0] - x, q[1] - y])
        return math.atan2(to[1], to[0]) if np.hypot(*to) > 1e-6 else 0.0
    for n in nodes:
        t = n["tags"]
        kind = t.get("highway") if t.get("highway") in ("stop", "give_way", "street_lamp", "bus_stop") else t.get("amenity")
        if kind not in ("stop", "give_way", "street_lamp", "bench", "waste_basket", "bus_stop"):
            continue
        x, y = n["x"], n["y"]
        if near_route(x, y) or not inside(x, y) or not swiss(x, y):
            continue
        if kind in ("stop", "give_way"):
            placed = False
            for wi, k in node_ways.get(n["id"], []):
                w = drive[wi]
                u = approach(w["nodes"], w["xy"], k, branches, t.get("direction"))
                if u is None:
                    continue
                right = np.array([u[1], -u[0]])                       # traffic keeps right
                # the stop on the road as built: the nearest point of a carriageway within 6 m
                base = np.array([x, y])
                if not on_carriageway([x], [y])[0]:
                    ring = [base + r_ * np.array([np.cos(a_), np.sin(a_)]) for r_ in (1, 2, 3, 4, 5, 6)
                            for a_ in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
                    ring = np.array(ring)
                    hit = on_carriageway(ring[:, 0], ring[:, 1])
                    if not hit.any():
                        continue
                    base = ring[np.flatnonzero(hit)[0]]
                # the edge of the carriageway to the right (else to the left, where houses stand at the
                # edge of a village street): the first point off it, then free ground beside it
                for side in (right, -right):
                    offs = np.arange(0.25, 14.0, 0.25)
                    P = base + side[None, :] * offs[:, None]
                    on = on_carriageway(P[:, 0], P[:, 1])
                    if on.all():
                        continue
                    edge = float(offs[np.argmin(on)])
                    for extra in (0.0, 0.5, 1.0, 1.5):
                        c = base + side * (edge + EDGE_OUT + extra)
                        if on_carriageway([c[0]], [c[1]])[0] or blocked([c[0]], [c[1]])[0]:
                            continue
                        z = float(ground([c[0]], [c[1]])[0])
                        size = STOP_SIZE if kind == "stop" else GIVEWAY_SIZE
                        ph = size if kind == "stop" else size * np.sqrt(3) / 2
                        top = z + PLATE_LOW + ph
                        V = tube(c, z - 0.3, top + 0.05)
                        mb.add("mp_osm_pole", V, uvs=V[:, :2] + V[:, 2:3], normals=bng.flat_normals_soup(V))
                        plate(mb, "mp_osm_stop" if kind == "stop" else "mp_osm_giveway", c, -u,
                              z + PLATE_LOW + ph / 2, size, size)
                        counts[kind] += 1
                        placed_list.append([round(float(c[0]), 2), round(float(c[1]), 2), kind, n["id"]])
                        placed = True
                        break
                    if placed:
                        break
                if placed:
                    break
            if not placed:
                counts["left_out"] += 1
            continue
        if kind == "bus_stop":
            c = bus_stop(mb, scene, g, n, x, y, ground, on_carriageway, blocked, wtree, drive, sign_dir, bus_textures, mats)
            if c is None:
                counts["left_out"] += 1
            else:
                counts["bus_stop"] = counts.get("bus_stop", 0) + 1
                counts["shelter"] = counts.get("shelter", 0) + int(c[2])
                placed_list.append([round(float(c[0]), 2), round(float(c[1]), 2), "bus_stop", n["id"]])
            continue
        # furniture and lamps: off the carriageway, not in a building or wall
        if on_carriageway([x], [y])[0] or blocked([x], [y])[0]:
            counts["left_out"] += 1
            continue
        theta = facing(x, y)
        z = float(ground([x], [y])[0])
        if kind == "street_lamp":
            scene.add(g + "/street_lights", bng.tsstatic(LIGHT, (x, y, z), rot=bng.rot_local_x_to(theta), collision=True))
        else:
            mdl = BENCH if kind == "bench" else BIN
            scene.add(g + "/furniture", bng.tsstatic(mdl, (x, y, z), rot=bng.rot_local_x_to(theta + math.pi / 2),
                                                      collision=True))
        counts[kind] += 1
        placed_list.append([round(float(x), 2), round(float(y), 2), kind, n["id"]])
    # v3.0.40: the furniture of the street photos where OSM records none of its kind
    import json
    photo = json.load(open(PHOTO_OBJECTS)) if os.path.exists(PHOTO_OBJECTS) else []
    for o in photo:
        kind = PHOTO_KINDS.get(o["cls"])
        x, y = float(o["x"]), float(o["y"])
        if kind is None or near_route(x, y) or not inside(x, y) or not swiss(x, y):
            continue
        if any(k == kind and (px - x) ** 2 + (py - y) ** 2 < PHOTO_NEAR ** 2 for px, py, k, _ in placed_list):
            continue
        if on_carriageway([x], [y])[0] or blocked([x], [y])[0]:
            counts["left_out"] += 1
            continue
        theta = facing(x, y)
        z = float(ground([x], [y])[0])
        if kind == "junction_box":
            t = np.array([-math.sin(theta), math.cos(theta)])         # along the road, the door towards it
            V = box(np.array([x, y]), t, np.array([-t[1], t[0]]), float(np.clip(o.get("width", 0.8), 0.5, 1.6)), 0.35,
                    z - 0.1, z + 1.2)
            mb.add("mp_osm_cabinet", V, uvs=V[:, :2] + V[:, 2:3], normals=bng.flat_normals_soup(V))
        else:
            mdl = {"bench": BENCH, "waste_basket": BIN, "hydrant": HYDRANT}[kind]
            scene.add(g + "/furniture", bng.tsstatic(mdl, (x, y, z), rot=bng.rot_local_x_to(theta + math.pi / 2),
                                                      collision=True))
        counts["photo_" + kind] = counts.get("photo_" + kind, 0) + 1
        placed_list.append([round(x, 2), round(y, 2), kind, "photo"])
    # v3.0.40: the fountains of OSM, a granite basin with its pillar (the small ones a bowl at the foot of the
    # pillar), as long as the street photos show it; where several photos see the place and none a fountain (a tap
    # on a wall, a fountain gone) nothing
    fseen = json.load(open(PHOTO_FOUNTAINS)) if os.path.exists(PHOTO_FOUNTAINS) else {}
    for n in nodes:
        t = n["tags"]
        if t.get("amenity") not in ("fountain", "drinking_water"):
            continue
        ph = fseen.get(str(n["id"]), {})
        if ph.get("seen", 0) >= 2 and not ph.get("found"):
            counts["fountain_not_in_photos"] = counts.get("fountain_not_in_photos", 0) + 1
            continue
        x, y = n["x"] + ph.get("dx", 0.0), n["y"] + ph.get("dy", 0.0)
        if not inside(x, y) or not swiss(x, y):
            continue
        if ph.get("found"):
            small = ph["width"] < 1.0
        else:
            small = t.get("amenity") == "drinking_water" or t.get("fountain") in FOUNTAIN_SMALL_TAGS
        L_, W_, H_ = FOUNTAIN_SMALL if small else FOUNTAIN
        if ph.get("found") and not small:
            L_ = float(np.clip(ph["width"], 1.0, 4.0))
            W_ = float(np.clip(0.42 * L_, 0.6, 1.2))
        theta = facing(x, y)
        tt = np.array([-math.sin(theta), math.cos(theta)])          # along the road
        to = np.array([math.cos(theta), math.sin(theta)])           # towards it
        for off in (0.0, -0.5, 0.5, -1.0, 1.0, -1.5):
            c = np.array([x, y]) + off * to
            pts = np.array([c + sa * tt * (L_ / 2 + (PILLAR if sa > 0 else 0)) + sb * to * W_ / 2
                            for sa in (-1, 1) for sb in (-1, 1)] + [c])
            if not on_carriageway(pts[:, 0], pts[:, 1]).any() and not blocked(pts[:, 0], pts[:, 1]).any():
                break
        else:
            counts["left_out"] += 1
            continue
        zg = ground(pts[:, 0], pts[:, 1])
        stone, water, metal = fountain(c, tt, L_, W_, float(np.min(zg)) - 0.15, float(np.max(zg)) + H_,
                                       0.65 if small else 0.75)
        mb.add("mp_osm_fountain_stone", stone, uvs=bng.box_uvs_soup(stone, 1.0), normals=bng.flat_normals_soup(stone))
        mb.add("mp_osm_fountain_water", water, uvs=water[:, :2], normals=bng.flat_normals_soup(water))
        if len(metal):
            mb.add("mp_osm_pole", metal, uvs=metal[:, :2] + metal[:, 2:3], normals=bng.flat_normals_soup(metal))
        k = "fountain_small" if small else "fountain"
        counts[k] = counts.get(k, 0) + 1
        placed_list.append([round(float(c[0]), 2), round(float(c[1]), 2), k, n["id"]])
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "props", "osm.materials.json"), mats)
    from config import WORK
    json.dump(placed_list, open(os.path.join(WORK, "osm_props.json"), "w"))
    rel = "art/shapes/props/props_osm.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="props_osm", origin=(0, 0, 0), orient=True)
    scene.add(g, bng.tsstatic(f"{L}/{rel}", (0, 0, 0), collision=True))
    print("OSM signs and furniture:", counts)
    return counts
