"""Renders and numbers of the places reported after the v3.0 release, on a built level, without the game
(render3d.py): steps on the narrow roads (Vezio, Arosio, Mugena ...), the step below Astano after the big
hairpin down to Banco, far trees near and on the road at Vezio.

- steps: the STEP events of the drive test (beamng/verifica/drive_test.json, drive_test.py) in each AREAS box,
  the worst STEPS_PER_AREA of each, and the worst WORST_MINOR steps on the minor roads of the whole map; for
  each the driver's view towards it from VIEW_BACK m before it, and a view from above at an angle;
- trees: the forest items with the trunk on a road top face or within TREE_GAP m of one, per forest file
  (far_* are the far trees, far_trees.py / forest_fill.py), and a view of the worst cluster of each area;
- summary.json with the counts, and a contact sheet sheet_NN.jpg of the views.
Run it on the level before and after a fix with the same arguments: the views are the same.
    python fix_review.py <out folder> [--level <folder>] [--drive <drive_test.json>]
"""
import glob, json, math, os, sys
import numpy as np
from config import LEVEL_DIR
import patch_release as pr
from road_mesh import TriSurface
from check_level import road_tops, terrain_top

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.join(os.path.dirname(HERE), "verifica", "drive_test.json")
# (name, centre x, y, half size m): the boxes of the places reported (centres at the villages' bus stops)
AREAS = [("astano_banco", -2650.0, 2050.0, 750.0), ("vezio", 960.0, 6070.0, 450.0), ("mugena", 1670.0, 6250.0, 300.0),
         ("arosio", 2270.0, 6300.0, 400.0), ("fescoggia", 480.0, 5370.0, 350.0), ("breno", -60.0, 4600.0, 400.0),
         ("miglieglia", -1000.0, 3560.0, 400.0)]
STEPS_PER_AREA = 6
WORST_MINOR = 12
TREE_GAP = 1.0           # m from the edge of a road top face
VIEW_BACK = 9.0          # m before a step, the driver's eye
EDGE_OUT = 0.3           # m beyond the outer edge of a road face: the terrain the edge is measured against


def items_on_roads(lv, S):
    """{forest file: count} of the items with the trunk on a road top face or within TREE_GAP m of one, and the
    items themselves (x, y, z, file)."""
    per, hits = {}, []
    ang = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    for f in sorted(glob.glob(os.path.join(lv, "forest", "*.forest4.json"))):
        name = os.path.basename(f).replace(".forest4.json", "")
        if name.startswith("italy_guardrails"):
            continue
        P = np.array([o["pos"] for o in pr.items(f)], float).reshape(-1, 3)
        if not len(P):
            continue
        near = np.isfinite(S.height(P[:, 0], P[:, 1], "high"))
        for a in ang:
            near |= np.isfinite(S.height(P[:, 0] + TREE_GAP * math.cos(a), P[:, 1] + TREE_GAP * math.sin(a), "high"))
        if near.any():
            per[name] = int(near.sum())
            hits += [(float(x), float(y), float(z), name) for x, y, z in P[near]]
    return per, hits


def edge_steps(tri, S, ter, box):
    """The outer edges of the road top faces in a box (x0, y0, x1, y1): their height over the terrain EDGE_OUT m
    beyond them. {km, median, p90, share over 0.15 m, share over 0.3 m} and the worst places."""
    import unpaved_tour
    x0, y0, x1, y1 = box
    c = tri.mean(1)
    t = tri[(c[:, 0] >= x0 - 5) & (c[:, 0] <= x1 + 5) & (c[:, 1] >= y0 - 5) & (c[:, 1] <= y1 + 5)]
    if not len(t):
        return {}, []
    mid, _, n, ln = unpaved_tour.edges(t)
    q = mid[:, :2] + 0.10 * n
    m = np.isnan(S.height(q[:, 0], q[:, 1], "low")) & (ln > 0.2) & (mid[:, 0] >= x0) & (mid[:, 0] <= x1) \
        & (mid[:, 1] >= y0) & (mid[:, 1] <= y1)
    p = mid[m, :2] + EDGE_OUT * n[m]
    gap = mid[m, 2] - terrain_top(ter, p[:, 0], p[:, 1])
    real = gap < 1.0                                   # higher: a wall or a bridge, not a step to drive over
    g, L, P = gap[real], ln[m][real], mid[m][real]
    if not len(g):
        return {}, []
    res = {"edges_km": round(float(L.sum()) / 1000, 2), "median_m": round(float(np.median(g)), 3),
           "p90_m": round(float(np.percentile(g, 90)), 3),
           "share_over_0.15m": round(float(L[g > 0.15].sum() / L.sum()), 3),
           "share_over_0.3m": round(float(L[g > 0.3].sum() / L.sum()), 3)}
    worst = [(float(P[i, 0]), float(P[i, 1]), float(g[i])) for i in np.argsort(-g)[:200]]
    out = []
    for w in worst:                                     # one per 30 m
        if all(math.hypot(w[0] - o[0], w[1] - o[1]) > 30 for o in out):
            out.append(w)
    return res, out[:3]


def heading_at(S, x, y):
    """Direction (radians) of the road at (x, y): the axis along which the road top faces reach farthest."""
    best, hb = -1.0, 0.0
    for h in np.linspace(0, np.pi, 24, endpoint=False):
        d = np.arange(1.0, 15.0, 1.0)
        n = int(np.isfinite(S.height(x + d * math.cos(h), y + d * math.sin(h), "high")).sum()
                + np.isfinite(S.height(x - d * math.cos(h), y - d * math.sin(h), "high")).sum())
        if n > best:
            best, hb = n, h
    return hb


def main(argv):
    out = argv[0]
    lv = argv[argv.index("--level") + 1] if "--level" in argv else LEVEL_DIR
    drive_f = argv[argv.index("--drive") + 1] if "--drive" in argv else DRIVE
    os.makedirs(out, exist_ok=True)
    tri, is_path, _ = road_tops(lv)
    S = TriSurface(tri[~is_path])
    places = json.load(open(drive_f))["places"] if os.path.exists(drive_f) else []
    steps = [p for p in places if p["what"] in ("STEP", "HOLE") and p.get("cls") != "path"]
    boxes = {}
    for name, cx, cy, half in AREAS:
        boxes[name] = (cx - half, cy - half, cx + half, cy + half)
    ter = pr.Terrain(lv)
    per, hits = items_on_roads(lv, S)
    H = np.array([(x, y) for x, y, _, _ in hits]).reshape(-1, 2)
    far = np.array([n.startswith("far_") for *_, n in hits], bool)
    summary = {"trees_on_or_by_roads": per, "trees_total": len(hits), "far_trees": int(far.sum()), "areas": {}}
    views = []
    for name, (x0, y0, x1, y1) in boxes.items():
        inb = [p for p in steps if x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1]
        inb.sort(key=lambda p: -p["value"])
        m = (H[:, 0] >= x0) & (H[:, 0] <= x1) & (H[:, 1] >= y0) & (H[:, 1] <= y1) if len(H) else np.zeros(0, bool)
        edges, edge_worst = edge_steps(tri[~is_path], S, ter, (x0, y0, x1, y1))
        summary["areas"][name] = {"edges": edges, "edge_worst": edge_worst,
                                  "steps": len([p for p in inb if p["what"] == "STEP"]),
                                  "holes": len([p for p in inb if p["what"] == "HOLE"]),
                                  "worst": inb[:STEPS_PER_AREA], "trees": int(m.sum()),
                                  "far_trees": int((m & far).sum()) if len(H) else 0}
        for k, p in enumerate(inb[:STEPS_PER_AREA]):
            views.append((f"{name}_step{k}", p["x"], p["y"], f"{name}: {p['what']} {100 * p['value']:.0f} cm "
                                                             f"{p.get('name') or ''} ({p['x']:.0f}, {p['y']:.0f})", False))
        for k, (ex, ey, eg) in enumerate(edge_worst[:2]):
            views.append((f"{name}_edge{k}", ex, ey, f"{name}: road edge {100 * eg:.0f} cm over the ground "
                                                    f"({ex:.0f}, {ey:.0f})", False))
        if m.any():
            P = H[m]
            cnt = [(int((np.hypot(*(P - q).T) < 40).sum()), tuple(q)) for q in P]
            c, q = max(cnt)
            views.append((f"{name}_trees", q[0], q[1], f"{name}: {c} trees on / by the road within 40 m "
                                                       f"({q[0]:.0f}, {q[1]:.0f})", True))
    minor = [p for p in steps if p["what"] == "STEP" and p.get("cls") == "minor"]
    minor.sort(key=lambda p: -p["value"])
    summary["worst_minor"] = minor[:WORST_MINOR]
    for k, p in enumerate(minor[:WORST_MINOR]):
        views.append((f"minor_step{k:02d}", p["x"], p["y"], f"minor: STEP {100 * p['value']:.0f} cm "
                                                           f"{p.get('name') or ''} ({p['x']:.0f}, {p['y']:.0f})", False))
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("areas", "worst_minor")}, indent=1))
    from render3d import Renderer, Camera
    from review_map import contact_sheets
    import review_map
    entries = []
    with Renderer(lv, textured=True) as r:
        for key, x, y, cap, trees in views:
            z = S.height([x], [y], "high")[0]
            if not np.isfinite(z):
                z = float(terrain_top(ter, np.array([x]), np.array([y]))[0])
            h = heading_at(S, x, y)
            for side, hh in (("a", h), ("b", h + np.pi)):
                ex, ey = x - VIEW_BACK * math.cos(hh), y - VIEW_BACK * math.sin(hh)
                ez = S.height([ex], [ey], "high")[0]
                ez = z if not np.isfinite(ez) else ez
                p = os.path.join(out, f"{key}_{side}.jpg")
                r.shot(Camera.driver(ex, ey, ez, hh, eye=1.3, pitch=-6.0), p, trees=True)
                entries.append((p, f"{cap} [{side}]"))
            p = os.path.join(out, f"{key}_top.jpg")
            r.shot(Camera.orbit(x, y, z, 28.0, (90 - math.degrees(h)) % 360 + 90, 40.0), p, near=150, far=1500,
                   trees=trees)
            entries.append((p, f"{cap} [top]"))
    review_map.OUT = out
    contact_sheets(entries, "sheet", cols=3, per=12, title="fix_review")


if __name__ == "__main__":
    main(sys.argv[1:])
