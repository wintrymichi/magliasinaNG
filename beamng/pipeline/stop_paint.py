"""Yellow paint at the bus stops and the marked crossings, as the orthophoto shows it (v3.1), in the built level.

The road paint of the level is drawn by the Swiss rules from the road geometry (markings_rules.py, v3.0): no traced
shape is laid. The rules have no bus stop markings, so the yellow zigzags, the BUS letters and the yellow kerb lines
of the stops were missing everywhere (17 of 265 Swiss stops had any yellow paint near them, and that only from a
crossing), and 60 of the 145 marked crossings of OSM got no bars (the node a few metres off the carriageway, an
unpaved or unmarked flag of the road). Those are the places a driver recognises.

measure (in the cloud session, from the 10 cm SWISSIMAGE crops luoghi_ref.py gialli commits round every Swiss bus
stop and marked crossing of OSM): the yellow paint of each crop as network_markings.py finds it (hue, saturation,
brightness, yellower than the grey asphalt around it, brighter than the road or saturated), with a lighter
cleaning (the zigzags are lines one or two pixels wide: an opening broke them into dust, which is why the v2 trace
had them in pieces), vehicles (yellow buses, compact blobs with dark windows) and blobs on beige ground left out.
Each blob becomes:
- a crossing bar (BAR_L long, BAR_S wide, filled): the bars of one crossing grouped (parallel, side by side) and
  laid again as clean ZEBRA_W m bars at their measured axis, phase and length (ZEBRA_L);
- a zigzag (longer than ZIG_L, thin: under ZIG_FILL of its rectangle, swinging left and right ZIG_TURNS times with
  legs of ZIG_LEG m): redrawn as straight legs LINE_W wide along its measured centre line (G9 review: the traced
  outline was a thick wavy band in the game, and frame corners taken for zigzags lay about as L shapes);
- a strip (a yellow kerb line, a no-parking line, the frame of a bus bay): a clean rectangle, kept only when at least
  STRIP_MIN_L long and within CONTEXT_R of a zigzag or a crossing (a lone bar in a lane was a sunlit shade edge);
- a mark (BUS, an arrow, a cross): measured but not laid; traced in 10 cm cells it came out as yellow blobs, stars
  and L shapes, and a yellow bus front or a motorcyclist's jacket in the lane passed as one (G9 review, 2026-10-25).
Output: dati/stop_paint.json.gz {"polygons": [{"ring", "kind", "src"}]}.

stop_paint_step (FINISH, before sidewalks: the crossings it adds get their kerbs lowered there): the polygons that
lie on the road meshes (ON_ROAD of their area on the carriageway or a yard) and are not painted yet (no yellow
paint of the level within NEAR_OLD m) are laid on the road surface LIFT m over it, in mp_road_paint_yellow, as
art/shapes/roads/stop_paint.dae in MissionGroup/roads/markings (no collision).
    python stop_paint.py measure          dati/stop_paint.json.gz from beamng/verifica/luoghi/gialli
    python stop_paint.py <level root>     the step on a level folder or zip
"""
import gzip, json, os, sys, tempfile, time
import numpy as np
import shapely
import bng
from config import LEVEL_NAME, lv95_to_local, local_to_lv95
from markings_net import read_items, shape_tris, up_faces, tops_of

HERE = os.path.dirname(os.path.abspath(__file__))
DATI = os.path.join(HERE, "..", "dati", "stop_paint.json.gz")
CROPS = os.path.join(HERE, "..", "verifica", "luoghi", "gialli")
POINTS = os.path.join(HERE, "..", "verifica", "luoghi", "gialli.json")
RES = 0.1                    # m, the orthophoto's cells
# yellow paint: network_markings.py (calibrated on the crossings of OSM)
YELLOW_H, YELLOW_S, YELLOW_V, YELLOW_B, YELLOW_TOP, YELLOW_BG = (18, 36), 45, 150, 60, 15, 16
FAINT_H, FAINT_S, FAINT_V, FAINT_Y, FAINT_TOP = 40, 24, 140, 35, 8   # faint yellow: over the ground round it
JOIN = 3                     # cells: pieces of one figure this close are one blob (a zigzag's thin legs; the gaps
                             # between crossing bars, 5 cells but 3 or 4 where the photo blurs them, stay)
MIN_AREA = 0.08              # m2, a smaller blob is a speck (a 1 m dash of a bus yard is 0.12)
VEHICLE_W, VEHICLE_FILL = 1.0, 0.35   # a blob this wide that fills this much of its rectangle is a vehicle
VEHICLE_DARK, VEHICLE_SHARE = 55, 0.12   # network_markings: a mark with this share of dark cells round it is a car
BAR_L, BAR_S, BAR_FILL = (0.8, 4.8), (0.15, 0.8), 0.45
ZEBRA_W = 0.5                # m, crossing bars and the gaps between them (markings_rules bar_w, bar_gap)
ZEBRA_L = (2.5, 3.0, 4.0)    # m, bar lengths along the road
GROUP_R = 4.5                # m, bars of one crossing
MIN_BARS = 3                 # a crossing has at least this many bars seen (two parallel dashes are not one)
ZIG_L, ZIG_FILL = 4.0, 0.45
ZIG_BIN = 0.2                # m, stations along a zigzag where its centre line is measured
ZIG_SIMPLIFY = 0.15          # m, the legs of a zigzag: its centre line simplified to straight pieces
ZIG_TURN, ZIG_TURNS = 35.0, 3   # a zigzag turns at least ZIG_TURNS times, by more than ZIG_TURN degrees, left and
                             # right in turn (the corner of a bay frame, an L or a U, turns once or twice one way)
ZIG_LEG, ZIG_SWING = 1.0, 0.6   # m: a zigzag has ZIG_TURNS legs this long and swings this far across (a traced
                             # arrow turns as often, with short legs)
LINE_W = 0.15                # m, the width a zigzag is drawn with
STRIP_S, STRIP_FILL = 0.45, 0.5
STRIP_MIN_L = 2.0            # m: a shorter strip is a fragment (a piece of a faded bay frame, a parking dash)
CONTEXT_R = 15.0             # m: a strip is laid only this close to a zigzag or a crossing of the stop
MARK_AREA, MARK_L = 0.2, 3.5
ON_ROAD = 0.7                # share of a polygon's area on the road meshes
NEAR_OLD = 0.8               # m: paint of the level this close means the place is painted already
LIFT = 0.02                  # m over the road surface (markings_net.LIFT)
MAT = "mp_road_paint_yellow"
SHAPE = "art/shapes/roads/stop_paint.dae"
ROAD_MATS = ("mp_road_asphalt", "mp_road_asphalt_fresh", "mp_hard_asphalt", "mp_path_paved", "mp_road_sett", "mp_hard_sett")
                             # paint lies on these faces of roads/surfaces (not on wall tops, gravel, pavements)


# ---------------------------------------------------------------------- measure (cloud session)
def yellow_mask(img):
    """Yellow paint: network_markings.py's test, or a fainter yellow measured against the ground round it (thin
    lines blend with the grey asphalt in a 10 cm cell: the dashes of a bus yard read saturation 26-50)."""
    import cv2
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    L = img.astype(np.float32).mean(-1)
    top = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    c = img.astype(np.int16)
    Y = c[..., 0] + c[..., 1] - 2 * c[..., 2]
    Ybg = cv2.medianBlur(np.clip(Y + 128, 0, 255).astype(np.uint8), 31).astype(np.int16) - 128
    hue = (hsv[..., 0] >= YELLOW_H[0]) & (hsv[..., 0] <= FAINT_H)
    strong = ((hsv[..., 0] >= YELLOW_H[0]) & (hsv[..., 0] <= YELLOW_H[1]) & (hsv[..., 1] > YELLOW_S)
              & (hsv[..., 2] > YELLOW_V) & (Y > YELLOW_B) & ((top > YELLOW_TOP) | (hsv[..., 1] > 90)))
    faint = hue & (hsv[..., 1] > FAINT_S) & (hsv[..., 2] > FAINT_V) & (Y - Ybg > FAINT_Y) & (top > FAINT_TOP)
    m = cv2.morphologyEx((strong | faint).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return m.astype(bool), L, c


def rect_of(q):
    ex = np.asarray(q.minimum_rotated_rectangle.exterior.coords)[:4]
    e1, e2 = ex[1] - ex[0], ex[2] - ex[1]
    l1, l2 = np.linalg.norm(e1), np.linalg.norm(e2)
    if l1 >= l2:
        return ex.mean(0), e1 / max(l1, 1e-9), l1, l2
    return ex.mean(0), e2 / max(l2, 1e-9), l2, l1


def rect_poly(c, ax, length, width):
    n = np.array([-ax[1], ax[0]])
    h, w = ax * length / 2, n * width / 2
    return np.array([c - h - w, c + h - w, c + h + w, c - h + w, c - h - w])


def blobs(img, x0, y1):
    """[(kind, shapely polygon in local coordinates)] of the yellow paint of a crop whose top left corner is local
    (x0, y1)."""
    import cv2
    m, L, c = yellow_mask(img)
    n_, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m.astype(np.uint8), np.ones((JOIN, JOIN), np.uint8)),
                                                      connectivity=8)
    lab = np.where(m, lab, 0)
    out = []
    H, W = m.shape
    for k in range(1, n_):
        bx, by, bw, bh = st[k][:4]
        if (lab[by:by + bh, bx:bx + bw] == k).sum() * RES * RES < MIN_AREA:
            continue
        r0, r1, c0, c1 = max(by - 12, 0), min(by + bh + 12, H), max(bx - 12, 0), min(bx + bw + 12, W)
        comp = lab[r0:r1, c0:c1] == k
        ring = (cv2.dilate(comp.astype(np.uint8), np.ones((21, 21), np.uint8)) > 0) & \
            ~(cv2.dilate(comp.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~m[r0:r1, c0:c1]
        bg = c[r0:r1, c0:c1][ring]
        if len(bg) < 20 or np.median(bg[:, 0] + bg[:, 1] - 2 * bg[:, 2]) >= YELLOW_BG:
            continue                                        # beige ground, a facade, dry grass: not on asphalt
        # the outline of the figure: its pieces joined across the gaps the photo left
        comp_j = cv2.morphologyEx(comp.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((JOIN, JOIN), np.uint8))
        cnts, _ = cv2.findContours(comp_j, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for q in cnts:
            if len(q) < 3:
                continue
            q = q[:, 0, :].astype(float)
            poly = shapely.Polygon(np.column_stack([x0 + (c0 + q[:, 0] + 0.5) * RES, y1 - (r0 + q[:, 1] + 0.5) * RES]))
            poly = poly.buffer(RES / 2, join_style="mitre")
            if poly.is_empty or poly.area < MIN_AREA:
                continue
            for g in getattr(poly, "geoms", [poly]):
                cc, ax, Ln, S = rect_of(g)
                fill = g.area / max(Ln * S, 1e-6)
                if S >= VEHICLE_W and fill >= VEHICLE_FILL and g.area > 2.0:
                    continue                                # a yellow vehicle
                if BAR_L[0] <= Ln <= BAR_L[1] and BAR_S[0] <= S <= BAR_S[1] and fill >= BAR_FILL:
                    out.append(("bar", g))
                elif S <= STRIP_S and fill >= STRIP_FILL and Ln >= 0.6:
                    out.append(("strip", g))
                elif Ln >= ZIG_L and fill < ZIG_FILL and S <= 3.0:
                    line = zigzag_line(g, cc, ax)
                    if line is not None:                    # an L, a U, a frame corner: not a zigzag
                        out.append(("zigzag", line))
                elif g.area >= MARK_AREA and Ln <= MARK_L:
                    # a yellow car or a flower bed reads like a letter: dark windows, shade or leaves round it
                    ring_d = (L[r0:r1, c0:c1] < VEHICLE_DARK) & ring
                    if ring.sum() and ring_d.sum() / ring.sum() > VEHICLE_SHARE:
                        continue
                    out.append(("mark", g))
    return out


def zigzag_line(g, cc, ax):
    """The clean centre line of a traced zigzag (straight legs, LINE_W wide, as a polygon), or None when the figure
    does not swing left and right at least ZIG_TURNS times: the traced outline drawn as it was came out as a thick
    wavy line in the game, and the corners of the bay frames it took for zigzags as scattered L shapes."""
    n = np.array([-ax[1], ax[0]])
    x0, y0, x1, y1 = g.bounds
    X, Y = np.meshgrid(np.arange(x0, x1, RES / 2), np.arange(y0, y1, RES / 2))
    X, Y = X.ravel(), Y.ravel()
    inside = shapely.contains_xy(g, X, Y)
    if inside.sum() < 10:
        return None
    P = np.column_stack([X[inside], Y[inside]]) - cc
    s, t = P @ ax, P @ n
    k = np.floor((s - s.min()) / ZIG_BIN).astype(int)
    st = [(float(np.median(s[k == i])), float(np.median(t[k == i]))) for i in range(k.max() + 1) if (k == i).any()]
    if len(st) < 4:
        return None
    pl = shapely.LineString(st).simplify(ZIG_SIMPLIFY)
    c = np.asarray(pl.coords)
    d = np.diff(c, axis=0)
    turns = []
    for a, b in zip(d[:-1], d[1:]):
        ang = np.degrees(np.arctan2(a[0] * b[1] - a[1] * b[0], a @ b))
        if abs(ang) > ZIG_TURN:
            turns.append(np.sign(ang))
    alt = 1 + sum(1 for a, b in zip(turns[:-1], turns[1:]) if a != b) if turns else 0
    if alt < ZIG_TURNS or (np.hypot(d[:, 0], d[:, 1]) >= ZIG_LEG).sum() < ZIG_TURNS or np.ptp(c[:, 1]) < ZIG_SWING:
        return None
    xy = cc + np.outer(c[:, 0], ax) + np.outer(c[:, 1], n)
    return shapely.LineString(xy).buffer(LINE_W / 2, cap_style="flat", join_style="mitre", mitre_limit=3.0)


def zebras(bars):
    """The bars grouped into crossings, each laid again as clean bars: [ring]."""
    from scipy.spatial import cKDTree
    if not bars:
        return [], []
    R = [rect_of(g) for g in bars]
    C = np.array([r[0] for r in R])
    kd = cKDTree(C)
    used = np.zeros(len(bars), bool)
    out, single = [], []
    for i in range(len(bars)):
        if used[i]:
            continue
        grp, todo = [i], [i]
        used[i] = True
        while todo:
            k = todo.pop()
            for j in kd.query_ball_point(C[k], GROUP_R):
                if used[j] or abs(R[j][1] @ R[k][1]) < np.cos(np.radians(12)) or abs((C[j] - C[k]) @ R[k][1]) > 1.5:
                    continue
                used[j] = True
                grp.append(j)
                todo.append(j)
        if len(grp) < MIN_BARS:
            single += [bars[k] for k in grp]
            continue
        ax = np.array([R[k][1] if R[k][1] @ R[grp[0]][1] >= 0 else -R[k][1] for k in grp]).mean(0)
        ax /= np.linalg.norm(ax)
        cross = np.array([-ax[1], ax[0]])
        cc = C[grp].mean(0)
        t = np.sort((C[grp] - cc) @ cross)
        lng = min(ZEBRA_L, key=lambda v: abs(v - float(np.median([R[k][2] for k in grp]))))
        # the bars at the measured phase, from the first measured to the last (one hidden between them put back)
        p = 2 * ZEBRA_W
        k0 = np.round((t - t[0]) / p)
        phase = float(np.median(t - k0 * p))
        for kk in range(int(k0.max()) + 1):
            out.append(rect_poly(cc + cross * (phase + kk * p), ax, lng, ZEBRA_W))
    return out, single


def measure():
    from PIL import Image
    pts = {p["name"]: p for p in json.load(open(POINTS))}
    polys, stats = [], {"crops": 0, "bar": 0, "strip": 0, "zigzag": 0, "mark": 0, "crossings": 0}
    for name, p in sorted(pts.items()):
        f = os.path.join(CROPS, name + ".jpg")
        if not os.path.exists(f):
            continue
        img = np.asarray(Image.open(f).convert("RGB"))
        stats["crops"] += 1
        # the crop: side m round the point in LV95, north up
        e, n = local_to_lv95(p["x"], p["y"])
        x0, y1 = lv95_to_local(e - p["side"] / 2, n + p["side"] / 2)
        bars = []
        for kind, g in blobs(img, x0, y1):
            stats[kind] += 1
            if kind == "bar":
                bars.append(g)
                continue
            if kind == "strip":
                cc, ax, Ln, S = rect_of(g)
                g = shapely.Polygon(rect_poly(cc, ax, Ln, min(max(S, 0.12), 0.3)))
            elif kind == "mark":
                # BUS letters, arrows, crosses traced in 10 cm cells: in the game they were yellow blobs, stars and
                # L shapes (and a yellow bus front, a motorcyclist's jacket in the lane): none is laid
                continue
            for gg in getattr(g, "geoms", [g]):
                if isinstance(gg, shapely.Polygon) and gg.area >= 0.06:
                    polys.append({"ring": np.asarray(gg.exterior.coords).round(3).tolist(), "kind": kind, "src": name})
        rings, single = zebras(bars)
        if rings:
            stats["crossings"] += 1
        for r in rings:
            polys.append({"ring": np.asarray(r).round(3).tolist(), "kind": "crossing", "src": name})
        for g in single:                                    # a lone bar: a stop line of a bus bay, a short strip
            cc, ax, Ln, S = rect_of(g)
            polys.append({"ring": rect_poly(cc, ax, Ln, S).round(3).tolist(), "kind": "strip", "src": name})
    # strips only where the stop is: long, and near a zigzag or a crossing (a lone yellow bar in the lane was the
    # sunlit edge of a tree's shade, short pieces the fragments of faded frames)
    anchors = [shapely.Polygon(q["ring"]) for q in polys if q["kind"] in ("zigzag", "crossing")]
    tree_a = shapely.STRtree(anchors) if anchors else None
    kept = []
    for q in polys:
        if q["kind"] == "strip":
            g = shapely.Polygon(q["ring"])
            if rect_of(g)[2] < STRIP_MIN_L or tree_a is None or \
                    not len(tree_a.query(g, predicate="dwithin", distance=CONTEXT_R)):
                stats["strip_dropped"] = stats.get("strip_dropped", 0) + 1
                continue
        kept.append(q)
    polys = kept
    # crops overlap (stops on both sides of a road): one copy of each polygon
    keep, seen = [], []
    tree_g = []
    for q in polys:
        g = shapely.Polygon(q["ring"])
        if any(g.intersection(h).area > 0.5 * min(g.area, h.area) for h in tree_g if h.distance(g) < 0.01):
            continue
        tree_g.append(g)
        keep.append(q)
    stats["polygons"] = len(keep)
    with gzip.open(DATI, "wt") as fo:
        json.dump({"polygons": keep, "stats": stats}, fo, separators=(",", ":"))
    print("stop paint measured:", stats, flush=True)
    return stats


# ---------------------------------------------------------------------- the step
def stop_paint_step(root, report=None):
    from road_mesh import TriSurface
    from scipy.spatial import cKDTree
    t0 = time.time()
    if not os.path.exists(DATI):
        print("stop paint: no", DATI, flush=True)
        return {}
    d = json.load(gzip.open(DATI, "rt"))
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    L = f"/levels/{LEVEL_NAME}"
    S = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    T = tops_of(S, lambda m: m in ROAD_MATS)
    surf = TriSurface(T)
    mk_items = f"{lv}/main/MissionGroup/roads/markings/items.level.json"
    mk = [o for o in read_items(zi, mk_items) if not o.get("shapeName", "").endswith(SHAPE)]
    M = shape_tris(zi, lv, mk)
    old = M.get(MAT, np.zeros((0, 3, 3)))
    kd_old = cKDTree(old.reshape(-1, 3)[:, :2]) if len(old) else None
    rep = {"in": len(d["polygons"]), "laid": 0, "painted_already": 0, "off_road": 0, "kinds": {}}
    mb = bng.MeshBuilder()
    # the crossings of one place go or stay together
    by_src = {}
    for q in d["polygons"]:
        by_src.setdefault((q["src"], q["kind"] == "crossing"), []).append(q)
    for (src, is_cross), qs in by_src.items():
        groups = [qs] if is_cross else [[q] for q in qs]
        for grp in groups:
            G = [shapely.Polygon(q["ring"]) for q in grp]
            G = [g if g.is_valid else shapely.make_valid(g) for g in G]
            if kd_old is not None:
                P = np.concatenate([np.asarray(g.exterior.coords if g.geom_type == "Polygon" else
                                               g.convex_hull.exterior.coords) for g in G])
                if any(len(r) for r in kd_old.query_ball_point(P, NEAR_OLD)):
                    rep["painted_already"] += len(grp)
                    continue
            tris = []
            for g in G:
                part_tris, ok = [], True
                for part in getattr(g, "geoms", [g]):
                    if not isinstance(part, shapely.Polygon) or part.area < 0.05:
                        continue
                    V = []
                    for t in shapely.constrained_delaunay_triangles(part).geoms:
                        c = np.asarray(t.exterior.coords)[:3]
                        if (c[1, 0] - c[0, 0]) * (c[2, 1] - c[0, 1]) - (c[1, 1] - c[0, 1]) * (c[2, 0] - c[0, 0]) < 0:
                            c = c[::-1]
                        V.append(c)
                    if not V:
                        continue
                    V = np.concatenate(V)
                    z = surf.height(V[:, 0], V[:, 1], "high")
                    on = np.isfinite(z).reshape(-1, 3).all(1)
                    e1, e2 = V[1::3] - V[0::3], V[2::3] - V[0::3]
                    a = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])     # numpy 2: no 2D np.cross
                    if a[on].sum() < ON_ROAD * a.sum():
                        ok = False
                        break
                    part_tris.append(np.column_stack([V, z + LIFT]).reshape(-1, 3, 3)[on])
                if ok and part_tris:
                    tris.append(np.concatenate(part_tris))
            if len(tris) < (MIN_BARS if is_cross else 1):
                rep["off_road"] += len(grp)
                continue
            rep["off_road"] += len(grp) - len(tris)
            Tt = np.concatenate(tris)
            Vv = Tt.reshape(-1, 3)
            mb.add(MAT, Vv, uvs=Vv[:, :2], normals=np.repeat([[0, 0, 1.0]], len(Vv), 0))
            rep["laid"] += len(tris)
            rep["kinds"][grp[0]["kind"]] = rep["kinds"].get(grp[0]["kind"], 0) + (1 if is_cross else len(tris))
    files = {}
    if not mb.empty():
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "s.dae")
            mb.write_dae(p, name="stop_paint", origin=(0.0, 0.0, 0.0))
            files[f"{lv}/{SHAPE}"] = open(p, "rb").read()
        parent = next((o["__parent"] for o in mk if "__parent" in o), "markings")
        ob = bng.tsstatic(f"{L}/{SHAPE}", (0, 0, 0), collision=False, decal=False)
        ob["__parent"] = parent
        mk.append(ob)
    files[mk_items] = ("\n".join(json.dumps(o, separators=(",", ":")) for o in mk) + "\n").encode()
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename in files or i.filename == f"{lv}/{SHAPE}":
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(n, data)
    rep["seconds"] = round(time.time() - t0)
    print("stop paint:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep


if __name__ == "__main__":
    if sys.argv[1:2] == ["measure"]:
        measure()
    else:
        stop_paint_step(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
