"""Rows of vines in the vineyards of the cadastral survey (v2.4).

Up to v2.3 the vineyards ('vigna' of the survey) were bare garden grass. Here every vineyard within
NEAR m of a road or path gets its rows:
- direction: the orientation of the stripes on the 10 cm orthophoto (structure tensor of the
  brightness in a window of up to WIN m inside the vineyard), measured once (python vineyards.py ->
  dati/vineyard_rows.json, by the middle point of every vineyard); where the stripes are not clear
  (coherence under MIN_COHERENCE) or not measured, the rows follow the contour of the slope (terraces);
- spacing SPACING m (the usual distance of the rows; not measured), the rows keep EDGE m from the
  edge of the vineyard and CLEAR m from every road and path;
- every row is a band of foliage from 0.45 to 1.7 m over the ground (a drawn cut-out texture of vine
  leaves on their wires with a post every 2 m, nothing from a photograph), one double-sided quad
  per STEP m following the ground; no collision (plants), meshes of CHUNK m with a level of detail
  that drops them beyond about a kilometre.
"""
import os
import numpy as np
import shapely
from scipy import ndimage as ndi
import bng
from bld_textures import noise, to8, save

NEAR = 150.0            # m from a road or path
WIN = 40.0              # m, side of the orthophoto window
MIN_COHERENCE = 0.25
SPACING = 2.2           # m between rows
EDGE = 0.8              # m from the edge of the vineyard
CLEAR = 1.5             # m from a road or path
STEP = 4.0              # m, longest piece of a row
Z0, Z1 = 0.45, 1.7      # m, bottom and top of the foliage
CHUNK = 128.0
DETAIL = 120            # pixel size of the meshes' detail level: smaller on screen, not drawn
SEED = 71


def texture(dst, w=512, h=256):
    """Cut-out band of vine foliage (2 m along the row, Z1 - Z0 m high) with its post and wires."""
    rng = np.random.default_rng(SEED)
    img = np.zeros((h, w, 4), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # leaves: palmate blobs, denser in the middle of the band; some yellowing (October)
    greens = np.array([[0.22, 0.34, 0.12], [0.30, 0.40, 0.14], [0.36, 0.42, 0.16], [0.52, 0.48, 0.18]], np.float32)
    for _ in range(900):
        cx, cy = rng.uniform(0, w), rng.uniform(0.05, 0.95) * h
        r = rng.uniform(5, 11)
        lob = 1 + 0.25 * np.cos(5 * np.arctan2(yy - cy, (xx - cx + w / 2) % w - w / 2))
        d = np.hypot((xx - cx + w / 2) % w - w / 2, yy - cy)
        m = d < r * lob
        if not m.any():
            continue
        c = greens[rng.choice(4, p=[0.35, 0.35, 0.2, 0.1])] * rng.uniform(0.85, 1.15)
        img[m, :3] = c * (0.85 + 0.15 * (1 - d[m] / (r * 1.25)))[:, None]
        img[m, 3] = 1.0
    # gaps: thinner foliage at the bottom
    gap = (noise(h, w, 6, rng) > 0.6) & (yy > 0.7 * h)
    img[gap, 3] = 0.0
    # wires and the post (u = 0)
    for v in (0.22, 0.55, 0.88):
        r0 = int(v * h)
        img[r0:r0 + 2, :, :3] = [0.45, 0.45, 0.45]
        img[r0:r0 + 2, :, 3] = 1.0
    img[:, 0:5, :3] = [0.42, 0.36, 0.28]
    img[:, 0:5, 3] = 1.0
    save(os.path.join(dst, "t_vine_b.color.png"), to8(np.clip(img, 0, 1)))


def material(level_name):
    t = f"/levels/{level_name}/art/shapes/vineyards"
    return bng.material("mp_vine", f"{t}/t_vine_b.color.png", alpha_test=100, double_sided=True, roughness=0.85)


def row_direction(poly, dtm, ortho_sample):
    """Angle (radians, of the rows) and coherence: the stripes of the orthophoto, else the contour."""
    c = poly.representative_point()
    half = WIN / 2
    res = 0.2
    xs = c.x - half + (np.arange(int(WIN / res)) + 0.5) * res
    ys = c.y + half - (np.arange(int(WIN / res)) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(poly.buffer(-1.0), X, Y)
    coh, ang = 0.0, None
    if inside.mean() > 0.25 and ortho_sample is not None:
        try:
            rgb = ortho_sample(X.ravel(), Y.ravel()).reshape(X.shape + (3,))
        except Exception:
            rgb = None
        if rgb is not None and np.isfinite(rgb).all():
            L = rgb.mean(-1)
            L = np.where(inside, L, np.nanmean(L[inside]))
            gy, gx = np.gradient(ndi.gaussian_filter(L, 1.0))
            gy = -gy                                         # rows go south: y up is minus
            Jxx = ndi.gaussian_filter(gx * gx, 6)[inside].mean()
            Jyy = ndi.gaussian_filter(gy * gy, 6)[inside].mean()
            Jxy = ndi.gaussian_filter(gx * gy, 6)[inside].mean()
            tr = Jxx + Jyy
            if tr > 1e-9:
                coh = float(np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / tr)
                ang = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2   # across the strongest gradient
    if ang is None or coh < MIN_COHERENCE:
        z = dtm.sample(np.array([c.x - 5, c.x + 5, c.x, c.x]), np.array([c.y, c.y, c.y - 5, c.y + 5]))
        sx, sy = (z[1] - z[0]) / 10, (z[3] - z[2]) / 10
        ang = np.arctan2(sy, sx) + np.pi / 2 if np.hypot(sx, sy) > 0.02 else 0.0
    return float(ang), coh


def rows(poly, ang, avoid):
    """Row lines of a vineyard polygon (clipped to its inside, off the roads)."""
    inner = poly.buffer(-EDGE)
    if avoid is not None and not avoid.is_empty:
        inner = inner.difference(avoid)
    if inner.is_empty:
        return []
    d = np.array([np.cos(ang), np.sin(ang)])
    n = np.array([-d[1], d[0]])
    c = np.array(inner.centroid.coords[0])
    P = np.asarray(inner.exterior.coords) if inner.geom_type == "Polygon" else shapely.get_coordinates(inner)
    t = (P - c) @ n
    s = (P - c) @ d
    out = []
    L = s.max() - s.min() + 10
    for k in np.arange(np.floor(t.min() / SPACING), np.ceil(t.max() / SPACING) + 1):
        o = c + n * k * SPACING
        line = shapely.LineString([o + d * (s.min() - 5), o + d * (s.min() - 5 + L)])
        cut = line.intersection(inner)
        for g in shapely.get_parts(cut):
            if g.geom_type == "LineString" and g.length > 2.0:
                out.append(g)
    return out


DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
ROWS = os.path.join(DATI, "vineyard_rows.json")


def vineyards(av, net_lines):
    """The vineyard polygons within NEAR m of the network (net_lines: (n, 2) points of its lines)."""
    from scipy.spatial import cKDTree
    import area
    keep = area.polygon()
    kd = cKDTree(net_lines)
    polys = []
    for g, _ in av["LCSF"].get("vigna", []):
        if not g.intersects(keep) or g.area < 150:
            continue
        for p in shapely.get_parts(g.intersection(keep)):
            if p.geom_type != "Polygon" or p.area < 150:
                continue
            if kd.query(shapely.get_coordinates(p.exterior))[0].min() <= NEAR:
                polys.append(p)
    return polys


def measure():
    """Row directions on the orthophoto -> dati/vineyard_rows.json [[x, y, angle, coherence], ...]."""
    import json, pickle
    import network
    import ortho10
    from geo import Grid
    from config import WORK
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    _, st, _ = network.load()
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    out = []
    polys = vineyards(av, np.column_stack([st["x"], st["y"]]))
    for k, p in enumerate(polys):
        ang, coh = row_direction(p, dtm, ortho10.sample)
        c = p.representative_point()
        out.append([round(c.x, 2), round(c.y, 2), round(ang, 4), round(coh, 3)])
        if k % 50 == 0:
            print("  %d/%d" % (k + 1, len(polys)), flush=True)
    json.dump({"source": "SWISSIMAGE 10 cm (stripes only, no image)", "rows": out}, open(ROWS, "w"),
              separators=(",", ":"))
    print("vineyards measured", len(out), "clear stripes", sum(r[3] >= MIN_COHERENCE for r in out))


def build(level_dir, level_name, scene, av, net_lines, drivable, group="MissionGroup/level_objects/vegetation/vineyards"):
    """Rows of every vineyard near a road or path; returns statistics."""
    import json
    from geo import Grid
    from config import WORK
    from scipy.spatial import cKDTree
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    meas = json.load(open(ROWS))["rows"] if os.path.exists(ROWS) else []
    mk = cKDTree(np.array([[r[0], r[1]] for r in meas])) if meas else None
    polys = vineyards(av, net_lines)
    dtree = shapely.STRtree(drivable) if drivable else None
    d = os.path.join(level_dir, "art", "shapes", "vineyards")
    os.makedirs(d, exist_ok=True)
    texture(d)
    bng.write_materials(os.path.join(d, "vineyards.materials.json"), [material(level_name)])
    builders = {}
    stats = {"vineyards": 0, "rows_km": 0.0, "from_photo": 0}
    for p in polys:
        c = p.representative_point()
        ang, coh = None, 0.0
        if mk is not None:
            dd, j = mk.query([c.x, c.y])
            if dd < 0.5:
                ang, coh = meas[j][2], meas[j][3]
        if ang is None or coh < MIN_COHERENCE:
            ang, coh = row_direction(p, dtm, None)
        avoid = None
        if dtree is not None:
            near = dtree.query(p.buffer(CLEAR), predicate="intersects")
            if len(near):
                avoid = shapely.union_all([drivable[i] for i in near]).buffer(CLEAR)
        lines = rows(p, ang, avoid)
        if not lines:
            continue
        stats["vineyards"] += 1
        stats["from_photo"] += int(coh >= MIN_COHERENCE)
        for line in lines:
            stats["rows_km"] += line.length / 1000
            n = max(1, int(np.ceil(line.length / STEP)))
            s = np.linspace(0, line.length, n + 1)
            P = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
            z = dtm.sample(P[:, 0], P[:, 1])
            mid = P.mean(0)
            key = (int(np.floor(mid[0] / CHUNK)), int(np.floor(mid[1] / CHUNK)))
            V, UV = [], []
            for i in range(n):
                a, b = P[i], P[i + 1]
                za, zb = z[i], z[i + 1]
                q = [(a[0], a[1], za + Z0), (b[0], b[1], zb + Z0), (b[0], b[1], zb + Z1), (a[0], a[1], za + Z1)]
                u0, u1 = s[i] / 2.0, s[i + 1] / 2.0
                uv = [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)]
                for j in (0, 1, 2, 0, 2, 3):
                    V.append(q[j])
                    UV.append(uv[j])
            V = np.array(V)
            nrm = np.repeat([[0.0, 0.0, 1.0]], len(V), 0)            # lit like the canopy above
            builders.setdefault(key, bng.MeshBuilder()).add("mp_vine", V, uvs=np.array(UV), normals=nrm)
    ntri = 0
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/vineyards/vines_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHUNK, (ty + 0.5) * CHUNK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name=f"vines_{tx}_{ty}", origin=origin, detail=DETAIL)
        ntri += mb.triangle_count()
        scene.add(group, bng.tsstatic(f"/levels/{level_name}/{rel}", origin, collision=False))
    stats.update(rows_km=round(stats["rows_km"], 1), chunks=len(builders), triangles=ntri)
    return stats


if __name__ == "__main__":
    measure()
