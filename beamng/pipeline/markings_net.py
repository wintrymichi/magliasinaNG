"""Road paint of the network (network_markings.py) as painted meshes on the road surfaces (v2.1),
redrawn as Swiss road markings by markings_clean.py (v2.7).

Lines: quad strips of their painted width along every painted run; the other paint (crossings,
stop and give-way lines, arrows, hatched areas, text): its polygons triangulated. Heights: the top
face of the road meshes of the level under every vertex (the face nearest to the line's profile
where a bridge passes over a road), LIFT m above it; paint that does not lie on a road face (a
swissTLM3D line away from the carriageway the survey has) is left out. One mesh per TILE m tile,
without collision, in MissionGroup/roads/markings, with the paint materials of markings_decals.py.
"""
import json, os
import numpy as np
import shapely
import bng
import osm_surface
from config import WORK, LEVEL_NAME
from road_mesh import TriSurface

TILE = 512.0
LIFT = 0.02
STEP = 0.5                    # m between the vertices of a strip
MATS = {"white": "mp_road_paint", "yellow": "mp_road_paint_yellow"}
SRC = os.path.join(WORK, "network_markings.json")      # or .json.gz (the copy kept in dati/)
DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "network_markings.json.gz")


def load():
    """The result of network_markings.py: work/network_markings.json, or the compressed copy of the
    repository (dati/network_markings.json.gz, seeded into work by prepare_work.py, or read from
    dati/ directly); None if neither."""
    import gzip
    if os.path.exists(SRC):
        return json.load(open(SRC))
    for f in (SRC + ".gz", DATI):
        if os.path.exists(f):
            return json.load(gzip.open(f, "rt"))
    return None


def paint_materials(level_dir):
    """The paint materials (the same as markings_decals.py writes) where the level has none yet."""
    f = os.path.join(level_dir, "art", "road", "paint.materials.json")
    have = json.load(open(f)) if os.path.exists(f) else {}
    need = [m for m in (bng.material("mp_road_paint", base_color=[0.86, 0.86, 0.84, 1], roughness=0.65),
                        bng.material("mp_road_paint_yellow", base_color=[0.88, 0.72, 0.12, 1], roughness=0.65))
            if m["name"] not in have]
    if need:
        bng.write_materials(f, need)


def densify(P, step=STEP):
    P = np.asarray(P, np.float64)
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(int(np.ceil(np.hypot(*(b - a)) / step)), 1)
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.concatenate(out)


def strip_tris(P, z, width):
    """Triangles (k, 3, 3) of a flat strip of `width` along P (n, 2) at heights z, facing up."""
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.column_stack([-T[:, 1], T[:, 0]]) * width / 2
    L = np.column_stack([P + N, z])
    R = np.column_stack([P - N, z])
    t = np.stack([R[:-1], R[1:], L[1:], R[:-1], L[1:], L[:-1]], 1).reshape(-1, 3, 3)
    down = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 2] < 0
    t[down] = t[down][:, ::-1]
    return t


# v2.7: not the gravel and dirt surfaces, which have no paint: what the orthophoto traced there (light
# stones, puddles, tyre tracks) is left out like paint off the road
UNPAVED_MATS = tuple(m for g in osm_surface.MATS.values() for c, m in g.items() if c in ("gravel", "dirt"))
ROAD_MATS = tuple(m for m in osm_surface.ROAD_MATS + osm_surface.HARD_MATS + ("mp_road_asphalt_fresh", "mp_sidewalk", "mp_island")
                  if m not in UNPAVED_MATS)
CHUNK = 128.0


def road_tops(level_dir, mats=ROAD_MATS):
    """Top faces (k, 3, 3) of the road meshes of the level (art/shapes/roads/road_<tx>_<ty>.dae, the
    origin of each is the middle of its 128 m chunk) with the materials `mats`: read from the files,
    so it works while the level is being built (the scene files are written at the end)."""
    import glob, re
    import patch_release as pr
    out = []
    for f in glob.glob(os.path.join(level_dir, "art", "shapes", "roads", "road_*.dae")):
        m = re.search(r"road_([+-]\d+)_([+-]\d+)\.dae$", f)
        if not m:
            continue
        origin = np.array([(int(m.group(1)) + 0.5) * CHUNK, (int(m.group(2)) + 0.5) * CHUNK, 0.0])
        V, N, T, C, parts = pr.read_dae(f)
        Vw = V + origin
        for mat, idx in parts:
            if mat not in mats:
                continue
            t = Vw[idx[:, 0].reshape(-1, 3)]
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            up = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12) > 0.5
            out.append(t[up])
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


CARRIAGE_MATS = tuple(m for m in osm_surface.ROAD_MATS + ("mp_road_asphalt_fresh",) if m not in UNPAVED_MATS)


def cleaned(d, carriage_tops, painted=None):
    """The paint of network_markings.py redrawn as Swiss markings (markings_clean.py) on the
    carriageways carriage_tops (k, 3, 3), with the junctions and crossings of OSM where available.
    painted: points (n, 2) of the paint built from the panoramas (no OSM crossing is added there)."""
    import markings_clean
    import osm
    ways = nodes = None
    if osm.available():
        ways, nodes = osm.load()
    out = markings_clean.clean(d, markings_clean.Carriage(carriage_tops) if len(carriage_tops) else None,
                               ways, nodes, osm.DRIVE, painted)
    print("network paint cleaned:", out["clean"])
    return out


def sv_paint_points(level_dir):
    """Points (n, 2) of the paint of the Street View route (art/shapes/roads/markings.dae), if built."""
    f = os.path.join(level_dir, "art", "shapes", "roads", "markings.dae")
    if not os.path.exists(f):
        return None
    import patch_release as pr
    return pr.read_dae(f)[0][:, :2]


def build(level_dir, scene, net=None, tops=None, hint=None, carriage_tops=None, painted=None, clean=True):
    """Paint meshes of work/network_markings.json on the road meshes of the level. tops: the top
    faces (k, 3, 3) of the road meshes (default: read from the level's road meshes); hint: heights
    (n,) at points (n, 2) near the road the paint lies on, where faces overlap (default: the profile
    of the network `net`); carriage_tops: the carriageways (default: the road meshes of the level
    with the materials CARRIAGE_MATS); painted: see cleaned(); clean: redraw the paint (v2.7)."""
    d = load()
    if d is None:
        print("no network markings (network_markings.py): the network stays without paint")
        return
    road_tops_ = road_tops(level_dir) if tops is None else tops
    S = TriSurface(road_tops_)
    if clean:
        if carriage_tops is None:
            carriage_tops = road_tops(level_dir, CARRIAGE_MATS)
        if painted is None:
            painted = sv_paint_points(level_dir)
        d = cleaned(d, carriage_tops, painted)
    # the profile of the network as the height hint where a road passes under a bridge
    if hint is None and net is not None:
        from scipy.spatial import cKDTree
        kd = cKDTree(np.column_stack([net.x, net.y]))
        hint = lambda P: net.z[kd.query(P)[1]]
    paint_materials(level_dir)
    builders = {}
    stats = {"strips": 0, "strip_m": 0.0, "polygons": 0, "off_road": 0}

    def add(tris, mat):
        c = tris.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(k) for k in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            V = tris[m].reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=V[:, :2],
                                                            normals=np.repeat([[0, 0, 1.0]], len(V), 0))
    for ln in d["lines"]:
        mat = MATS.get(ln["color"], "mp_road_paint")
        for run in ln["runs"]:
            if len(run) < 2:
                continue
            P = densify(run)
            z = S.height(P[:, 0], P[:, 1], "near" if hint else "high", hint(P) if hint else None)
            ok = np.isfinite(z)
            stats["off_road"] += int((~ok).sum())
            e = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
            for a, b in zip(e[::2], e[1::2]):
                if b - a < 2:
                    continue
                add(strip_tris(P[a:b], z[a:b] + LIFT, ln["width"]), mat)
                stats["strips"] += 1
                stats["strip_m"] += float(np.sum(np.hypot(*np.diff(P[a:b], axis=0).T)))
    for pg in d["polygons"]:
        poly = shapely.Polygon(pg["ring"])
        if not poly.is_valid:
            poly = shapely.make_valid(poly)
        for part in getattr(poly, "geoms", [poly]):
            if not isinstance(part, shapely.Polygon) or part.area < 0.05:
                continue
            tri = shapely.constrained_delaunay_triangles(part)
            V = []
            for t in tri.geoms:
                c = np.asarray(t.exterior.coords)[:3]
                if (c[1, 0] - c[0, 0]) * (c[2, 1] - c[0, 1]) - (c[1, 1] - c[0, 1]) * (c[2, 0] - c[0, 0]) < 0:
                    c = c[::-1]
                V.append(c)
            if not V:
                continue
            V = np.concatenate(V)
            z = S.height(V[:, 0], V[:, 1], "near" if hint else "high", hint(V) if hint else None)
            t3 = np.column_stack([V, z + LIFT]).reshape(-1, 3, 3)
            ok = np.isfinite(t3[:, :, 2]).all(1)
            stats["off_road"] += int((~ok).sum())
            if ok.any():
                add(t3[ok], MATS.get(pg["color"], "mp_road_paint"))
                stats["polygons"] += 1
    g = "MissionGroup/roads/markings"
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/roads/markings_net_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name=f"markings_net_{tx}_{ty}", origin=origin)
        scene.add(g, bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=False, decal=False))
    print("network paint: %d strips (%.1f km), %d polygons, %d vertices off the road left out, %d meshes" %
          (stats["strips"], stats["strip_m"] / 1000, stats["polygons"], stats["off_road"], len(builders)))
    return stats
