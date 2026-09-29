"""Visual review of the map against reality (v2.2): contact sheets that put side by side, for a place,
- the SWISSIMAGE orthophoto of swisstopo (WMTS, the latest flight), north up, with outlines drawn on it;
- the Street View panorama that sees the place best (nearest one with a clear line of sight over the
  surface model), as a perspective view looking at it;
- the map rendered from the same camera (render3d.py, with the textures of the level's materials).
The sheets are for the review only and stay in WORK/sv/review: no image of Street View or of the
orthophoto enters the level or the repository.
    python sv_review.py <places.json> [out folder]      places: [{x, y, z?, label, poly?}]
"""
import io, json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import WORK, local_to_lv95, lv95_to_wgs, wgs_to_local
import camera

WMTS = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg"
CACHE = os.path.join(WORK, "sv", "wmts")
PANO = os.path.join(WORK, "sv", "pano")
CAM_H = 2.2
_sel = None


def merc(lat, lon, z):
    n = 2 ** z
    return (lon + 180.0) / 360.0 * n * 256, (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n * 256


def tile(z, tx, ty):
    import requests
    f = os.path.join(CACHE, f"{z}_{tx}_{ty}.jpg")
    if not os.path.exists(f):
        os.makedirs(CACHE, exist_ok=True)
        r = requests.get(WMTS.format(z=z, x=tx, y=ty), timeout=30)
        if r.status_code != 200:
            return Image.new("RGB", (256, 256), (90, 90, 90))
        open(f, "wb").write(r.content)
    return Image.open(f).convert("RGB")


def ortho(x, y, half=40.0, px=480, z=19, polys=(), marks=()):
    """North-up orthophoto of the local square (x +- half, y +- half), outlines (local polygons) and marks."""
    import cv2
    corners = [(x - half, y + half), (x + half, y + half), (x + half, y - half), (x - half, y - half)]
    mc = []
    for cx, cy in corners:
        lat, lon = lv95_to_wgs(*local_to_lv95(cx, cy))
        mc.append(merc(lat, lon, z))
    mc = np.array(mc)
    tx0, ty0 = int(mc[:, 0].min() // 256), int(mc[:, 1].min() // 256)
    tx1, ty1 = int(mc[:, 0].max() // 256), int(mc[:, 1].max() // 256)
    big = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            big.paste(tile(z, tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    src = (mc - [tx0 * 256, ty0 * 256]).astype(np.float32)
    dst = np.array([[0, 0], [px, 0], [px, px], [0, px]], np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    out = Image.fromarray(cv2.warpPerspective(np.asarray(big), M, (px, px), flags=cv2.INTER_LINEAR))
    d = ImageDraw.Draw(out)
    s = px / (2 * half)
    to_px = lambda P: [((p[0] - (x - half)) * s, ((y + half) - p[1]) * s) for p in P]
    for P, col in polys:
        d.line(to_px(list(P) + [P[0]]), fill=col, width=2)
    for (mx, my), col in marks:
        u, v = to_px([(mx, my)])[0]
        d.ellipse([u - 5, v - 5, u + 5, v + 5], outline=col, width=2)
    return out


def selected():
    global _sel
    if _sel is None:
        _sel = [p for p in json.load(open(os.path.join(WORK, "sv", "selected.json")))
                if os.path.exists(os.path.join(PANO, p["id"] + ".jpg"))]
    return _sel


def best_panos(x, y, z, dsm=None, dtm=None, maxd=70.0, k=3, skip=0.0):
    """Panoramas that see (x, y, z): nearest first, with a clear line of sight over the surface model
    (the last `skip` m before the point left out: the building the point stands in)."""
    P = selected()
    xy = np.array([[p["x"], p["y"]] for p in P])
    d = np.hypot(xy[:, 0] - x, xy[:, 1] - y)
    order = np.argsort(d)
    out = []
    for i in order[:40]:
        if d[i] > maxd:
            break
        p = dict(P[i])
        g = float(dtm.sample(np.array([p["x"]]), np.array([p["y"]]))[0]) if dtm is not None else z
        p["cam"] = np.array([p["x"], p["y"], g + CAM_H])
        if dsm is not None:
            L = max(float(np.hypot(p["x"] - x, p["y"] - y)), 1e-6)
            T = np.linspace(0.05, max(0.06, 1.0 - max(skip, 0.07 * L) / L), 24)
            Q = p["cam"][None] + (np.array([x, y, z])[None] - p["cam"][None]) * T[:, None]
            zs = dsm.sample(Q[:, 0], Q[:, 1])
            if np.any(zs > Q[:, 2] + 0.5):
                continue
        out.append(p)
        if len(out) >= k:
            break
    return out


def pano_view(p, target, hfov=75.0, w=640, h=480):
    """Perspective view of panorama p looking at the world point target."""
    from scipy.ndimage import map_coordinates
    img = np.asarray(Image.open(os.path.join(PANO, p["id"] + ".jpg")).convert("RGB"))
    H, W = img.shape[:2]
    conv = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                                       "attitude_convention.json")))
    heading = p["heading_deg"] + camera.grid_convergence(p["lat"], p["lon"])
    R = camera.attitude_matrix(heading, p.get("pitch_deg", 0.0), p.get("roll_deg", 0.0), conv)
    fwd = np.asarray(target, float) - p["cam"]
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= max(np.linalg.norm(right), 1e-9)
    up = np.cross(right, fwd)
    f = (w / 2) / math.tan(math.radians(hfov) / 2)
    uu, vv = np.meshgrid(np.arange(w) - w / 2 + 0.5, np.arange(h) - h / 2 + 0.5)
    D = fwd[None, None] * f + right[None, None] * uu[..., None] - up[None, None] * vv[..., None]
    col, row = camera.dir_cam_to_pixel(D.reshape(-1, 3) @ R, W, H)
    out = np.stack([map_coordinates(img[..., c], [row, col % W], order=1, mode="nearest") for c in range(3)], -1)
    return Image.fromarray(out.reshape(h, w, 3).astype(np.uint8))


def map_view(renderer, p, target, hfov=75.0, w=640, h=480, out=None):
    from render3d import Camera
    vfov = math.degrees(2 * math.atan(math.tan(math.radians(hfov) / 2) * h / w))
    cam = Camera.look(p["cam"], target, fov=vfov, near=0.3, far=6000.0)
    f = out or os.path.join(WORK, "sv", "_view.jpg")
    renderer.W, renderer.H = w, h
    renderer.shot(cam, f, near=320.0)
    return Image.open(f).convert("RGB")


def label(img, text):
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    d.rectangle([0, 0, img.size[0], 22], fill=(0, 0, 0))
    d.text((6, 3), text, fill=(255, 255, 255), font=font)
    return img


def sheet(rows, path):
    """rows: [[img, ...], ...] -> one image, rows stacked."""
    W = max(sum(i.size[0] for i in r) for r in rows)
    H = sum(max(i.size[1] for i in r) for r in rows)
    out = Image.new("RGB", (W, H), (30, 30, 30))
    y = 0
    for r in rows:
        x = 0
        for i in r:
            out.paste(i, (x, y))
            x += i.size[0]
        y += max(i.size[1] for i in r)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path, quality=86)
    return path


def review(places, out_dir, level_dir=None, with_map=True, half=40.0):
    """One sheet row per place: orthophoto, Street View, map (from the same camera)."""
    from geo import Grid
    dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    r = None
    if with_map:
        from render3d import Renderer
        from config import LEVEL_DIR
        r = Renderer(level_dir or LEVEL_DIR, W=640, H=480, textured=True)
    paths = []
    try:
        for k, pl in enumerate(places):
            x, y = pl["x"], pl["y"]
            z = pl.get("z")
            if z is None:
                z = float(dtm.sample(np.array([x]), np.array([y]))[0]) + pl.get("dz", 3.0)
            polys = [(np.asarray(P), (255, 60, 60)) for P in pl.get("polys", [])]
            row = [label(ortho(x, y, half, polys=polys, marks=[((x, y), (255, 255, 0))]),
                         f"{pl.get('label', '')} ortofoto")]
            ps = best_panos(x, y, z, dsm, dtm, skip=pl.get("skip", 0.0))
            if ps:
                p = ps[0]
                target = np.array([x, y, z])
                row.append(label(pano_view(p, target), f"Street View {p.get('date', '')} {np.hypot(p['x'] - x, p['y'] - y):.0f} m"))
                if r is not None:
                    row.append(label(map_view(r, p, target), "mappa (stessa camera)"))
            else:
                row.append(label(Image.new("RGB", (640, 480), (40, 40, 40)), "nessuna panoramica vede il punto"))
            paths.append(sheet([row], os.path.join(out_dir, f"{k:04d}_{pl.get('label', 'p').replace(' ', '_')}.jpg")))
    finally:
        if r is not None:
            r.close()
    return paths


if __name__ == "__main__":
    pl = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(WORK, "sv", "review")
    for p in review(pl, out):
        print(p)


def village_places(n_per=2, maxd=30.0):
    """Review places in every village of the area (places.py): around its centre, the panoramas nearest to
    it and, for each, the facade of the building nearest to the camera it sees (a point 4 m above the
    ground on the facade's middle)."""
    import places
    import buildings_mesh
    from geo import Grid
    from scipy.spatial import cKDTree
    import shapely, shapely.ops
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    blds = buildings_mesh.load_buildings()
    fps = [buildings_mesh.footprint(b) for b in blds]
    cen = np.array([[f.centroid.x, f.centroid.y] if not f.is_empty else [1e9, 1e9] for f in fps])
    btree = cKDTree(cen)
    P = selected()
    xy = np.array([[p["x"], p["y"]] for p in P])
    ptree = cKDTree(xy)
    out = []
    for name, vx, vy, _ in places.villages():
        d, idx = ptree.query([vx, vy], k=12)
        got = 0
        for dd, i in zip(d, idx):
            if dd > 300 or got >= n_per:
                break
            p = P[i]
            bd, bj = btree.query([p["x"], p["y"]], k=6)
            for bdd, j in zip(bd, bj):
                if bdd > maxd:
                    break
                f = fps[j]
                # the point of the footprint's outline nearest to the camera, 4 m up
                q = shapely.ops.nearest_points(f.exterior if f.geom_type == "Polygon" else f, shapely.Point(p["x"], p["y"]))[0]
                z = float(dtm.sample(np.array([q.x]), np.array([q.y]))[0]) + 4.0
                out.append({"x": q.x, "y": q.y, "z": z, "label": f"{name} {got + 1}", "village": name, "pano": p["id"],
                            "building": blds[j]["uuid"], "skip": 1.5})
                got += 1
                break
    return out
