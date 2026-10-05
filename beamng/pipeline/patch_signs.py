"""The Swiss road signs of the whole network in a built level zip (v2.7), without rebuilding the level.

Up to v2.6 the map had only the STOP and give-way signs that OpenStreetMap records (props_osm.py),
the bus stops, and on the Magliaso - Pura cantonal road the sign plates seen in the panoramas,
plain-coloured. This step adds every sign signs_net.plan() finds, drawn by signs_ch.py after the
Swiss standard:
- the signs mapped one by one in OSM, at the mapped point and facing the mapped direction;
- the signs the regulation OSM records implies (speed limits, 30 zones, one-way streets, zebra
  crossings, roundabouts, the beginning and end of the villages on the main roads).
Every sign is put on a grey steel pole beside the carriageway of the level, on the right of the
traffic that reads it (else on the left), EDGE_OUT m from the edge, on free ground: not on a
carriageway, a building or a wall; one that finds no place within 2 m is left out (counted).
Where a mapped sign stands within REPLACE m of a panorama sign of the cantonal road that faces the
same traffic, the panorama plates of that pole are removed and the sign goes where the panorama
measured it; a sign the rules imply does the same within REPLACE_RULE m. The plates of the STOP and
give-way signs of v2.6 are drawn again at the same place.

The sign plates written up to v2.6 (props.py, props_osm.py: the STOP and give-way signs, the bus
stops, the panorama plates) were wound clockwise as seen from the side they face. The game draws a
triangle only from the side it turns counter-clockwise to, so the traffic saw the grey back of the
plate and the picture faced the other way. Those plates are turned (rewrite, FLIP); the new ones
are written the right way (plate_quads).

What the level is read from (all in the zip): the terrain (theTerrain.ter), the road meshes
(carriageways and ground), the building and wall meshes (where no pole can stand), the poles of
props_poles.dae and props_osm.dae (no new pole on top of one). Everything else is copied as it is.

Usage: python patch_signs.py <in.zip> <out.zip> [--report report.json]
"""
import hashlib, io, json, math, os, re, struct, sys, tempfile, time, zipfile
from collections import Counter
import numpy as np
import shapely
from PIL import Image
import bng
import signs_ch
import signs_net
from road_mesh import TriSurface

LEVEL = "levels/magliaso_pura"
L = "/" + LEVEL
SIGN_DIR = f"{LEVEL}/art/shapes/signs/ch"
SHAPE = f"{LEVEL}/art/shapes/props/props_signs.dae"
MATERIALS = f"{LEVEL}/art/shapes/props/signs_ch.materials.json"
EDGE_OUT = 0.60           # m from the edge of the carriageway to the pole (OSStr: at least 0.5 m)
LOW_VILLAGE = 2.10        # m, underside of the lowest plate where the limit is 50 or less (over a pavement)
LOW_ROAD = 1.50           # m, elsewhere
GAP = 0.05                # m between plates on a pole
POLE_R = 0.030            # m, 60 mm steel tube
REPLACE = 8.0             # m: a mapped sign takes the place of a panorama sign this close
REPLACE_RULE = 5.0        # m: a sign the rules imply, of a panorama sign this close
CLEAR = 0.45              # m: no new pole this close to an existing one
ROAD_MATS = ("mp_road_asphalt", "mp_road_asphalt_fresh", "mp_road_gravel", "mp_road_dirt", "mp_road_sett",
             "mp_road_cobble")
GREY_BACK = (150, 152, 154)
LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")
# what the plates of the cantonal road (props_poles.dae, mp_sign_NNN_k) are, read on the crops of the
# panoramas (work/signs) on michi's PC: only the codes and notes, no image of the panoramas
PANO_SIGNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "signs_panorama.json")
PANO_TEX = re.compile(rf"{LEVEL}/art/shapes/signs/sign_\d{{3}}_\d\.png")
PROPS_MATERIALS = f"{LEVEL}/art/shapes/props/main.materials.json"
PANO_OFF = 0.06           # m: props.py put the panorama plates this far in front of their pole


# ------------------------------------------------------------------ reading the level
_FA = re.compile(rb'<float_array id="(g-[a-z]+)" count="\d+">([^<]*)</float_array>')
_TRI = re.compile(rb'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', re.S)


def read_dae(data):
    """(V, N, parts) of a pipeline COLLADA: positions, normals, [(material, vertex index (k, 3))]."""
    arr = {m.group(1): m.group(2) for m in _FA.finditer(data)}
    V = np.array(arr[b"g-pa"].split(), np.float64).reshape(-1, 3)
    N = np.array(arr[b"g-na"].split(), np.float64).reshape(-1, 3)
    T = np.array(arr[b"g-ta"].split(), np.float64).reshape(-1, 2)
    C = np.array(arr[b"g-ca"].split(), np.float64).reshape(-1, 4) if b"g-ca" in arr else None
    parts = []
    for m in _TRI.finditer(data):
        nin = m.group(2).count(b"<input")
        idx = np.array(m.group(3).split(), np.int64).reshape(-1, nin)
        parts.append((m.group(1).decode(), idx))
    return V, N, T, C, parts


def scene_shapes(z, group):
    """[(shape path in the zip, position)] of the TSStatics of a scene group."""
    f = f"{LEVEL}/main/MissionGroup/{group}/items.level.json"
    out = []
    for line in z.read(f).decode("utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("class") == "TSStatic" and o.get("shapeName", "").startswith(L + "/"):
            out.append((o["shapeName"][1:], np.array(o.get("position", [0, 0, 0]), np.float64)))
    return out


class Terrain:
    def __init__(self, z):
        info = [json.loads(l) for l in z.read(f"{LEVEL}/main/MissionGroup/level_objects/terrain/items.level.json")
                .decode().splitlines() if l.strip()][0]
        b = z.read(f"{LEVEL}/theTerrain.ter")
        n = struct.unpack("<I", b[1:5])[0]
        q = np.frombuffer(b, "<u2", n * n, 5).reshape(n, n)
        self.h = info["position"][2] + q.astype(np.float32) / 65535.0 * info["maxHeight"]
        self.x0, self.y0 = info["position"][0], info["position"][1]
        self.sq = info["squareSize"]
        self.n = n

    def __call__(self, x, y):
        x = np.atleast_1d(np.asarray(x, np.float64))
        y = np.atleast_1d(np.asarray(y, np.float64))
        c = np.clip((x - self.x0) / self.sq, 0, self.n - 1.001)
        r = np.clip((y - self.y0) / self.sq, 0, self.n - 1.001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        h = self.h
        return (h[r0, c0] * (1 - fc) * (1 - fr) + h[r0, c0 + 1] * fc * (1 - fr) + h[r0 + 1, c0] * (1 - fc) * fr +
                h[r0 + 1, c0 + 1] * fc * fr)


def road_tops(z):
    """(carriageway top faces, all road top faces), (k, 3, 3) world coordinates."""
    carr, allt = [], []
    for path, pos in scene_shapes(z, "roads/surfaces"):
        V, N, T, C, parts = read_dae(z.read(path))
        Vw = V + pos
        for mat, idx in parts:
            t = Vw[idx[:, 0].reshape(-1, 3)]
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
            allt.append(t[up])
            if mat in ROAD_MATS:
                carr.append(t[up])
    return np.concatenate(carr), np.concatenate(allt)


def solids(z, near, cell=32.0):
    """Shapely geometries (buffered 0.3 m) of the building and wall triangles near the points `near`
    (n, 2): a pole cannot stand inside them."""
    keys = set(map(tuple, np.floor(near / cell).astype(np.int64)))
    keys = {(a + i, b + j) for a, b in keys for i in (-1, 0, 1) for j in (-1, 0, 1)}
    geoms = []
    for group in ("buildings", "walls"):
        for path, pos in scene_shapes(z, group):
            V, N, T, C, parts = read_dae(z.read(path))
            Vw = V + pos
            for mat, idx in parts:
                t = Vw[idx[:, 0].reshape(-1, 3)][:, :, :2]
                c = np.floor(t.mean(1) / cell).astype(np.int64)
                keep = np.fromiter(((a, b) in keys for a, b in c), bool, len(c))
                for tri in t[keep]:
                    area = abs((tri[1, 0] - tri[0, 0]) * (tri[2, 1] - tri[0, 1]) - (tri[2, 0] - tri[0, 0]) * (tri[1, 1] - tri[0, 1]))
                    g = shapely.Polygon(tri) if area > 1e-4 else shapely.LineString(tri)
                    geoms.append(g)
    if not geoms:
        return None
    return shapely.STRtree(shapely.buffer(np.array(geoms, dtype=object), 0.3, quad_segs=2))


def existing_props(z):
    """Poles already in the level [(x, y)], the STOP / give-way plates of props_osm.py
    [(material, centre (3,), normal (2,))] and the panorama sign plates of props_poles.dae
    [(material, centre (3,), normal (2,))]."""
    poles, osm_plates, pano_plates = [], [], []
    for f, plates in ((f"{LEVEL}/art/shapes/props/props_osm.dae", osm_plates),
                      (f"{LEVEL}/art/shapes/props/props_poles.dae", pano_plates)):
        if f not in z.namelist():
            continue
        V, N, T, C, parts = read_dae(z.read(f))
        for mat, idx in parts:
            t = V[idx[:, 0].reshape(-1, 3)]
            if mat in ("mp_osm_pole", "mp_pole_steel"):
                # tubes: cluster their vertices on a 0.25 m grid
                xy = np.unique(np.round(t.reshape(-1, 3)[:, :2] * 4) / 4, axis=0)
                poles.append(xy)
            elif mat in ("mp_osm_stop", "mp_osm_giveway") or mat.startswith("mp_sign_0"):
                nrm = N[idx[:, 1]].reshape(-1, 3, 3).mean(1)
                tri_c = t.mean(1)
                # every plate is two triangles: pair them by position
                for k in range(0, len(t) - 1, 2):
                    c = (tri_c[k] + tri_c[k + 1]) / 2
                    n2 = nrm[k][:2] / max(np.hypot(*nrm[k][:2]), 1e-9)
                    plates.append((mat, c, n2))
    P = np.concatenate(poles) if poles else np.zeros((0, 2))
    return P, osm_plates, pano_plates


# ------------------------------------------------------------------ geometry
def tube(c, z0, z1, r=POLE_R, n=8):
    a = np.linspace(0, 2 * np.pi, n + 1)
    ring = np.column_stack([np.cos(a), np.sin(a)]) * r + c
    out = []
    for k in range(n):
        p0, p1 = ring[k], ring[k + 1]
        out += [np.r_[p0, z0], np.r_[p1, z0], np.r_[p1, z1], np.r_[p0, z0], np.r_[p1, z1], np.r_[p0, z1]]
    cap = [np.r_[ring[k], z1] for k in range(n)]
    for k in range(1, n - 1):
        out += [cap[0], cap[k], cap[k + 1]]
    return np.array(out)


def plate_quads(c, nrm, zc, w, h, off=0.035):
    """Front quad (6, 3) of a plate centred at (c, zc) facing nrm (2D), and its texture coordinates:
    counter-clockwise seen from the side it faces (the game culls the other side), the image read
    left to right by whoever looks at it, upright (COLLADA: v = 0 at the bottom of the image)."""
    r = np.array([-nrm[1], nrm[0]])                    # left to right for whoever faces the plate
    p = c + nrm * off
    A = np.r_[p - r * w / 2, zc - h / 2]
    B = np.r_[p + r * w / 2, zc - h / 2]
    C = np.r_[p + r * w / 2, zc + h / 2]
    D = np.r_[p - r * w / 2, zc + h / 2]
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]], float)
    return np.array([A, B, C, A, C, D]), uv


# ------------------------------------------------------------------ textures and materials
def slug(code, val):
    s = f"{code}_{val or ''}"
    return "ch_" + re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:24] + "_" + hashlib.md5(s.encode()).hexdigest()[:6]


def png(img):
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


def pot(img):
    """The image stretched to power-of-two sides: the game does not load a plate texture of other sizes
    (the log says 'skip cooking ... not power of 2' and the plate shows 'IMPORT FAILED'). The plate's
    texture coordinates run 0..1, so the stretch is undone on the plate."""
    w, h = (1 << max(0, (v - 1).bit_length()) for v in img.size)
    return img if (w, h) == img.size else img.resize((w, h), Image.LANCZOS)


def rgba_files(img):
    """(colour png, opacity png) of an RGBA image, as props_osm.save_rgba writes them."""
    img = pot(img.convert("RGBA"))
    rgb = Image.new("RGB", img.size, (128, 128, 128))
    rgb.paste(img.convert("RGB"), (0, 0), img.split()[3])
    return png(rgb), png(img.split()[3])


# ------------------------------------------------------------------ placement
class World:
    def __init__(self, z, near):
        t0 = time.time()
        self.ter = Terrain(z)
        carr, allt = road_tops(z)
        self.carr = TriSurface(carr)
        self.surf = TriSurface(allt)
        print(f"roads {len(carr)} carriageway faces, {len(allt)} faces ({time.time() - t0:.0f} s)")
        self.solid = solids(z, near)
        print(f"buildings and walls near the signs ({time.time() - t0:.0f} s)")

    def on_carriageway(self, x, y):
        return np.isfinite(self.carr.height(x, y, "high"))

    def blocked(self, x, y):
        if self.solid is None:
            return np.zeros(len(np.atleast_1d(x)), bool)
        pts = shapely.points(np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float)))
        out = np.zeros(len(pts), bool)
        i, _ = self.solid.query(pts, predicate="within")
        out[i] = True
        return out

    def ground(self, x, y):
        zr = self.surf.height(x, y, "high")
        zt = self.ter(x, y)
        return np.where(np.isfinite(zr), np.maximum(zr, zt), zt)


def place(world, s, poles_tree, pole_xy):
    """(pole x, y) for a sign, None when there is no free ground beside the road."""
    def free(c):
        if world.on_carriageway([c[0]], [c[1]])[0] or world.blocked([c[0]], [c[1]])[0]:
            return False
        if len(pole_xy):
            d, _ = poles_tree.query(c)
            if d < CLEAR:
                return False
        return True
    p = np.array([s.x, s.y])
    if s.mapped and free(p):
        # the mapper put the node where the sign stands: keep it when it is beside a carriageway
        ring = p + np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)]) * 4.0
        if world.on_carriageway(ring[:, 0], ring[:, 1]).any():
            return p
    base = p
    if not world.on_carriageway([p[0]], [p[1]])[0]:
        ring = np.array([p + r * np.array([math.cos(a), math.sin(a)]) for r in (0.5, 1, 2, 3, 4, 5, 6)
                         for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)])
        hit = world.on_carriageway(ring[:, 0], ring[:, 1])
        if not hit.any():
            return None
        base = ring[np.flatnonzero(hit)[0]]
    right = np.array([s.u[1], -s.u[0]])
    for side in (right, -right):
        offs = np.arange(0.25, 16.0, 0.25)
        P = base + side[None, :] * offs[:, None]
        on = world.on_carriageway(P[:, 0], P[:, 1])
        if on.all():
            continue
        edge = float(offs[np.argmin(on)])
        for along in (0.0, 1.0, -1.0, 2.0, -2.0):
            for extra in (0.0, 0.4, 0.8, 1.2):
                c = base + side * (edge + EDGE_OUT + extra) + s.u * along
                if free(c):
                    return c
    return None


def build(z, signs):
    """Mesh, textures and materials of the signs; returns (MeshBuilder, {zip path: bytes},
    materials, report, panorama materials to remove)."""
    ex_poles, osm_plates, pano_plates = existing_props(z)
    print(f"existing: {len(ex_poles)} pole points, {len(osm_plates)} STOP/give-way plates, {len(pano_plates)} panorama plates")
    near = np.array([[s.x, s.y] for s in signs])
    world = World(z, near)
    from scipy.spatial import cKDTree
    pole_xy = [tuple(p) for p in ex_poles]
    tree = cKDTree(np.array(pole_xy)) if pole_xy else None
    mb = bng.MeshBuilder()
    files, mats, made = {}, [], {}
    rep = {"placed": Counter(), "left_out": Counter(), "outside": Counter(), "replaced_panorama": 0, "signs": []}
    drop_pano = set()
    pano_c = np.array([p[1][:2] for p in pano_plates]) if pano_plates else np.zeros((0, 2))

    def material_for(code, val):
        key = slug(code, val)
        if key not in made:
            p = signs_ch.plate(code, val)
            col, op = rgba_files(p.img)
            files[f"{SIGN_DIR}/{key}_b.color.png"] = col
            files[f"{SIGN_DIR}/{key}_o.data.png"] = op
            S_ = f"/{SIGN_DIR}"
            mats.append(bng.material(f"mp_{key}", f"{S_}/{key}_b.color.png", roughness=0.35, alpha_test=100,
                                     ground_type="METAL", detail={"opacityMap": f"{S_}/{key}_o.data.png"}))
            # the grey back has the outline of the plate: the same opacity map
            mats.append(bng.material(f"mp_{key}_back", base_color=[c / 255 for c in GREY_BACK] + [1], roughness=0.5,
                                     metallic=0.5, alpha_test=100, ground_type="METAL",
                                     detail={"opacityMap": f"{S_}/{key}_o.data.png"}))
            made[key] = p
        return f"mp_{key}", made[key]

    mats.append(bng.material("mp_ch_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6))
    for s in signs:
        c = None
        # a mapped sign that the panoramas measured: in its measured place, instead of the plain plates
        if len(pano_c):
            d = np.hypot(*(pano_c - [s.x, s.y]).T)
            reach = REPLACE if s.src == "osm" else REPLACE_RULE
            for j in np.argsort(d)[:6]:
                if d[j] < reach and np.dot(pano_plates[j][2], -s.u) > 0.5 and pano_plates[j][0] not in drop_pano:
                    mat_j, cj, nj = pano_plates[j]
                    pc = cj[:2] - nj * 0.035
                    # every plate of that pole goes
                    for m2, c2, n2 in pano_plates:
                        if np.hypot(*(c2[:2] - n2 * 0.035 - pc)) < 0.3:
                            drop_pano.add(m2)
                    c = pc
                    rep["replaced_panorama"] += 1
                    break
        if c is None:
            p = np.array([s.x, s.y])
            ring = p + np.array([[r * math.cos(a), r * math.sin(a)] for r in (0, 1, 2, 4, 6)
                                 for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)])
            if not world.on_carriageway(ring[:, 0], ring[:, 1]).any():
                rep["outside"][s.kind] += 1                # a road the map does not build (beyond its edge)
                continue
            c = place(world, s, tree, pole_xy)
        if c is None:
            rep["left_out"][s.kind] += 1
            continue
        z0 = float(world.ground([c[0]], [c[1]])[0])
        low = LOW_VILLAGE if (s.limit or 50) <= 50 else LOW_ROAD
        nrm = -s.u
        plates = []
        for code, val in s.plates:
            p = signs_ch.plate(code, val, big=s.big)
            if p is not None:
                plates.append((code, val, p))
        if not plates:
            continue
        # top to bottom: stack from the lowest
        zb = z0 + low
        layout = []
        for code, val, p in reversed(plates):
            layout.append((code, val, p, zb + p.h / 2))
            zb += p.h + GAP
        top = zb - GAP
        wmax = max(p.w for _, _, p, _ in layout)
        tng = np.array([nrm[1], -nrm[0]])
        legs = [c - tng * wmax * 0.3, c + tng * wmax * 0.3] if wmax > 0.95 else [c]
        for lc in legs:
            Vt = tube(lc, z0 - 0.3, top - 0.02)
            # plain colour: texture coordinates near 0, so write_dae does not shift the plates' ones
            mb.add("mp_ch_pole", Vt, uvs=np.zeros((len(Vt), 2)), normals=bng.flat_normals_soup(Vt))
        for code, val, p, zc in layout:
            mat, _ = material_for(code, val)
            F, uv = plate_quads(c, nrm, zc, p.w, p.h)
            mb.add(mat, F, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
            Bk = F[::-1] - np.r_[nrm * 0.006, 0]
            mb.add(mat + "_back", Bk, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))
        pole_xy.append((float(c[0]), float(c[1])))
        tree = cKDTree(np.array(pole_xy))
        rep["placed"][s.kind] += 1
        rep["signs"].append({"x": round(float(c[0]), 2), "y": round(float(c[1]), 2), "z": round(z0, 2),
                             "facing": [round(float(nrm[0]), 3), round(float(nrm[1]), 3)],
                             "plates": [[a, b] for a, b in s.plates], "src": s.src, "osm": s.osm_id})
    # the plates of the cantonal road seen in the panoramas: drawn as the signals they are, the size of
    # the standard, in the place and at the height the panoramas measured; the ones that are no sign go
    pano = json.load(open(PANO_SIGNS, encoding="utf-8")) if os.path.exists(PANO_SIGNS) else {}
    rep["panorama"] = Counter()
    poles = []                                             # [pole centre, [(zc, stack, normal)]]
    for mat, cc, n2 in pano_plates:
        info = pano.get(mat[3:])
        if mat in drop_pano or info is None:
            continue
        if info["code"] == "not_a_sign":
            drop_pano.add(mat)
            rep["panorama"]["removed_not_a_sign"] += 1
            continue
        stack = [(info["code"], info["value"])] + [tuple(b) for b in info.get("below", [])]
        if not all(signs_ch.known(c_, v_) for c_, v_ in stack):
            rep["panorama"]["kept_" + info["code"]] += 1     # backs, bus stops, boards: as measured
            continue
        drop_pano.add(mat)
        rep["panorama"]["drawn_" + info["code"]] += 1
        pc = cc[:2] - n2 * PANO_OFF
        for q in poles:
            if np.hypot(*(q[0] - pc)) < 0.3:
                q[1].append((float(cc[2]), stack, n2))
                break
        else:
            poles.append([pc, [(float(cc[2]), stack, n2)]])
    for pc, items in poles:
        # top to bottom; a plate drawn bigger than the one measured pushes the ones under it down
        floor = None
        for zc, stack, n2 in sorted(items, key=lambda t: -t[0]):
            for k, (code, val) in enumerate(stack):
                p = signs_ch.plate(code, val)
                if k:                                      # the plates under the signal: right under it
                    zc = floor - GAP - p.h / 2
                elif floor is not None:
                    zc = min(zc, floor - GAP - p.h / 2)
                mat, _ = material_for(code, val)
                F, uv = plate_quads(pc, n2, zc, p.w, p.h, off=PANO_OFF)
                mb.add(mat, F, uvs=uv, normals=np.repeat(np.r_[n2, 0][None], 6, 0))
                Bk = F[::-1] - np.r_[n2 * 0.006, 0]
                mb.add(mat + "_back", Bk, uvs=uv[::-1], normals=np.repeat(np.r_[-n2, 0][None], 6, 0))
                floor = zc - p.h / 2
    # the grey backs (mp_sign_back) of the panorama plates that go
    rep["drop_backs"] = [c2 - np.r_[n2 * 0.01, 0] for m2, c2, n2 in pano_plates if m2 in drop_pano]
    # the STOP and give-way plates of v2.6, drawn again
    for name, code in (("osm_stop", "3.01"), ("osm_giveway", "3.02")):
        col, op = rgba_files(signs_ch.plate(code).img)
        files[f"{LEVEL}/art/shapes/signs/{name}_b.color.png"] = col
        files[f"{LEVEL}/art/shapes/signs/{name}_o.data.png"] = op
    return mb, files, mats, rep, drop_pano


# plates written up to v2.6 (props.py, props_osm.py) wound clockwise as seen from the side they face:
# the game culls that side, so the traffic saw the grey back (or the image mirrored)
FLIP = re.compile(r"mp_sign_\d|mp_sign_back$|mp_osm_(stop|giveway|timetable|sign_back|bus_)")


def rewrite(z, path, drop=(), drop_backs=()):
    """A props mesh (bytes) without the materials `drop` (and the grey backs mp_sign_back centred at
    `drop_backs`) and with the old sign plates (FLIP) turned to face their traffic: winding reversed
    and the image turned upright and read left to right."""
    data = z.read(path)
    node = re.search(rb'<node id="([^"]+)" name="[^"]+" type="NODE"><instance_geometry', data).group(1).decode()
    V, N, T, C, parts = read_dae(data)
    mb = bng.MeshBuilder()
    flipped = 0
    for mat, idx in parts:
        if mat in drop:
            continue
        uv, cols = T[idx[:, 2]], (C[idx[:, 3]] if (C is not None and idx.shape[1] > 3) else None)
        tris = np.arange(len(idx)).reshape(-1, 3)
        if mat == "mp_sign_back" and len(drop_backs):
            # every back is two triangles: drop the pairs centred on a plate that goes
            t = V[idx[:, 0]].reshape(-1, 3, 3).mean(1)
            pc = (t[0::2] + t[1::2]) / 2
            DB = np.array(drop_backs)
            gone = np.min(np.linalg.norm(pc[:, None, :] - DB[None], axis=2), axis=1) < 0.03
            tris = tris.reshape(-1, 2, 3)[~gone].reshape(-1, 3)
        if FLIP.match(mat):
            tris = tris[:, ::-1]
            uv = uv.copy()
            uv[:, 0] = 1.0 - uv[:, 0]
            uv[:, 1] = 1.0 - uv[:, 1]       # they had v = 0 at the top too: upside down in the game
            flipped += len(tris)
        mb.add(mat, V[idx[:, 0]], uvs=uv, normals=N[idx[:, 1]], tris=tris, colors=cols)
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "m.dae")
        mb.write_dae(f, name=node.rsplit("_a", 1)[0], detail=int(node.rsplit("_a", 1)[1]))
        return open(f, "rb").read(), flipped


def main(src, dst, report=None):
    t0 = time.time()
    signs = signs_net.plan()
    print(f"{len(signs)} signs planned: {Counter(s.src for s in signs)}")
    zi = zipfile.ZipFile(src)
    mb, files, mats, rep, drop = build(zi, signs)
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "props_signs.dae")
        mb.write_dae(f, name="props_signs")
        files[SHAPE] = open(f, "rb").read()
    rep["flipped_triangles"] = 0
    backs = rep.pop("drop_backs")
    for name, dr, db in (("props_poles", drop, backs), ("props_osm", (), ())):
        path = f"{LEVEL}/art/shapes/props/{name}.dae"
        if path in zi.namelist():
            files[path], k = rewrite(zi, path, dr, db)
            rep["flipped_triangles"] += k
    files[MATERIALS] = json.dumps({m["name"]: m for m in mats}, indent=1).encode("utf-8")
    group_file = f"{LEVEL}/main/MissionGroup/props/osm/items.level.json"
    obj = bng.tsstatic(f"{L}/art/shapes/props/props_signs.dae", (0, 0, 0), collision=True)
    obj["__parent"] = "osm"
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for i in zi.infolist():
            n = i.filename
            if n in files:
                # today's date: the game keeps a converted copy of every shape and texture (<user>/temp) and
                # converts again only a file newer than that copy, so with the old date it showed v2.6
                zo.writestr(zipfile.ZipInfo(n, date_time=time.localtime()[:6]), files.pop(n),
                            compress_type=i.compress_type)
                continue
            data = zi.read(i)
            if n == group_file:
                lines = [l for l in data.decode("utf-8").splitlines() if l.strip() and "props_signs.dae" not in l]
                data = ("\n".join(lines + [json.dumps(obj, separators=(",", ":"))]) + "\n").encode("utf-8")
            elif re.fullmatch(r"levels/[^/]+/README\.md", n) and os.path.exists(LEVEL_README):
                data = open(LEVEL_README, "rb").read()
            elif PANO_TEX.fullmatch(n):
                # the panorama plates kept as measured: their outline was in the alpha channel of the colour
                # texture, which the game does not test, so with the plates facing the traffic it saw a dark
                # rectangle around them; the outline goes into an opacity map like the drawn plates
                col, op = rgba_files(Image.open(io.BytesIO(data)))
                zo.writestr(zipfile.ZipInfo(n, date_time=time.localtime()[:6]), col, compress_type=i.compress_type)
                files[n[:-4] + "_o.data.png"] = op
                rep["panorama_opacity"] = rep.get("panorama_opacity", 0) + 1
                continue
            elif n == PROPS_MATERIALS:
                m = json.loads(data)
                for k, v in m.items():
                    st = v.get("Stages", [{}])[0]
                    if re.fullmatch(r"mp_sign_\d{3}_\d", k) and st.get("baseColorMap", "").endswith(".png"):
                        st["opacityMap"] = st["baseColorMap"][:-4] + "_o.data.png"
                data = json.dumps(m, indent=1).encode("utf-8")
                zo.writestr(zipfile.ZipInfo(n, date_time=time.localtime()[:6]), data, compress_type=i.compress_type)
                continue
            elif n.startswith(f"{LEVEL}/art/shapes/signs/") and n.endswith(".png"):
                # the bus stop flags and timetables of v2.6: power-of-two sides too, with today's date
                img = Image.open(io.BytesIO(data))
                big = pot(img)
                if big is not img:
                    zo.writestr(zipfile.ZipInfo(n, date_time=time.localtime()[:6]), png(big),
                                compress_type=i.compress_type)
                    rep["textures_resized"] = rep.get("textures_resized", 0) + 1
                    continue
            zo.writestr(i, data, compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(zipfile.ZipInfo(n, date_time=time.localtime()[:6]), data, compress_type=zipfile.ZIP_DEFLATED)
    out = {"placed": dict(rep["placed"]), "left_out": dict(rep["left_out"]), "outside_map": dict(rep["outside"]),
           "outside_map_total": sum(rep["outside"].values()),
           "replaced_panorama": rep["replaced_panorama"], "old_plate_triangles_turned": rep["flipped_triangles"], "panorama_plates_removed": len(drop),
           "old_textures_resized": rep.get("textures_resized", 0),
           "panorama_plates": dict(rep["panorama"]), "panorama_opacity_maps": rep.get("panorama_opacity", 0),
           "placed_total": sum(rep["placed"].values()), "left_out_total": sum(rep["left_out"].values()),
           "signs": rep["signs"]}
    if report:
        json.dump(out, open(report, "w"), indent=1)
    print({k: v for k, v in out.items() if k != "signs"})
    print(f"{dst} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    a = sys.argv[1:]
    rp = None
    if "--report" in a:
        k = a.index("--report")
        rp = a[k + 1]
        a = a[:k] + a[k + 2:]
    main(a[0], a[1], rp)
