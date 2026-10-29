"""The road network and the per-spot data of a Ticino region (region.py): DecalRoads cut at the zone cores and welded
across the core edges, the zones' traffic signals, sites (parking spots, fuel stations) and decals, each from the
zone whose core holds it.

Every zone is built from the same swissTLM3D lines in the same frame, so a road crossing a core edge has the same nodes
in both zones (measured on ti_0_m1, ti_1_m1, ti_0_0, ti_1_0: 122 of 123 edge crossings within 5 cm, the last 0.1 m).
A road is cut exactly at the edge (the crossing point interpolated on its segment) in both zones, and the two cut ends
are joined into one point: the game's AI graph links two roads only where they share a point.
"""
import collections
import json
import os

import numpy as np

SNAP_NODE = 0.5          # m: a cut point this close to the road's next node inside replaces that node
MIN_RUN = 1.0            # m: a run of a road inside a core shorter than this is left out (a corner clipped)
WELD_R = 1.0             # m: two cut ends of two zones this close (and facing each other) become one point
WELD_DZ = 0.5            # m: ... at about the same height (not an overpass)
WELD_COS = -0.7          # the two ends' outward directions must be about opposite
ONTO_R, ONTO_DZ = 1.5, 1.0   # m: an unmatched cut end is joined onto the nearest road of another zone this close
CANTONALE = "strada_cantonale"   # the Malcantone's Street View route (ai_roads.build)
LINK = 0.05              # m: the graph's link distance (ai_roads.graph_report)


# ------------------------------------------------------------------ cutting
def _clip(a, b, rect):
    """Liang-Barsky: the share (t0, t1) of the segment a -> b inside the closed rect, or None."""
    x0, y0, x1, y1 = rect
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return t0, t1


def _in(p, rect):
    return rect[0] <= p[0] < rect[2] and rect[1] <= p[1] < rect[3]


def cut_runs(nodes, rect):
    """The runs of a polyline inside the half-open rect, cut exactly on its edge: [(nodes, cut at start, cut at end)].
    All the node's fields (x, y, z, width) are interpolated along the segment."""
    N = np.asarray(nodes, np.float64)
    runs, cur = [], None
    for i in range(len(N) - 1):
        a, b = N[i], N[i + 1]
        seg = None
        if np.hypot(*(b[:2] - a[:2])) > 1e-9:
            seg = _clip(a, b, rect)
            if seg is not None and seg[1] - seg[0] > 1e-9:
                m = a + (b - a) * (0.5 * (seg[0] + seg[1]))
                if not _in(m, rect):         # along the edge itself: the zone on the other side has it
                    seg = None
            else:
                seg = None
        if seg is None:
            if cur is not None:
                runs.append(cur)
                cur = None
            continue
        t0, t1 = seg
        pa, pb = a + (b - a) * t0, a + (b - a) * t1
        if cur is None:
            cur = [[pa], t0 > 0 or not _in(a, rect), False]
        elif t0 > 0:                          # left and came back in on the same segment: never with t0 > 0 here
            runs.append(cur)
            cur = [[pa], True, False]
        cur[0].append(pb)
        if t1 < 1:
            cur[2] = True
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    out = []
    for pts, c0, c1 in runs:
        P = np.array(pts)
        if c0 and len(P) > 2 and np.hypot(*(P[1, :2] - P[0, :2])) < SNAP_NODE:
            P = np.delete(P, 1, 0)
        if c1 and len(P) > 2 and np.hypot(*(P[-2, :2] - P[-1, :2])) < SNAP_NODE:
            P = np.delete(P, -2, 0)
        if np.hypot(*np.diff(P[:, :2], axis=0).T).sum() < MIN_RUN:
            continue
        out.append((P, c0, c1))
    return out


def _round(P):
    return [[round(float(v), 4) for v in row] for row in P]


def cut_road(o, s):
    """A DecalRoad of zone s as its pieces in the core: [(object, cut at start, cut at end)]. A road wholly in the
    core keeps its nodes; names get the zone in front (two zones number their roads alike)."""
    nodes = o.get("nodes") or []
    if len(nodes) < 2:
        return []
    if all(s.in_core(n[0], n[1]) for n in nodes):
        return [(dict(o, name=f"{s.name}_{o.get('name', 'road')}"), False, False)]
    out = []
    for k, (P, c0, c1) in enumerate(cut_runs(nodes, s.core)):
        name = f"{s.name}_{o.get('name', 'road')}" + (f"_c{k}" if k else "")
        run = _round(P)
        out.append((dict(o, name=name, nodes=run, position=run[0][:3]), c0, c1))
    return out


def stale_cantonale(objs, s, grid):
    """True if the zone carries the Malcantone's Street View route (strada_cantonale and its pieces) beyond its
    own terrain: built before ai_roads.build left it out of such zones. Where the route lies wholly in the zone's
    terrain the zone has no swissTLM3D line along it (the route took their place): it stays there."""
    x0, y0 = s.cfg["ter_x0"], s.cfg["ter_y0"]
    ext = s.cfg.get("ter_size", s.n) * grid.sq
    P = [n for o in objs if o.get("class") == "DecalRoad" and is_cantonale(o.get("name", "")) for n in o["nodes"]]
    if not P:
        return False
    P = np.asarray(P)
    return not ((P[:, 0] >= x0) & (P[:, 0] <= x0 + ext) & (P[:, 1] >= y0) & (P[:, 1] <= y0 + ext)).all()


def is_cantonale(name):
    return name == CANTONALE or name.startswith(CANTONALE + "_")


# ------------------------------------------------------------------ welding
def _out_dir(nodes, end):
    """The unit direction a road leaves through its end (0 or -1), from a node at least 2 m back."""
    N = np.asarray(nodes, np.float64)
    e = N[end, :2]
    back = N[::-1] if end == -1 else N
    q = back[1, :2]
    for r in back[1:]:
        q = r[:2]
        if np.hypot(*(q - e)) >= 2.0:
            break
    d = e - q
    n = np.hypot(*d)
    return d / n if n > 1e-9 else d


def weld(pieces):
    """Joins the cut ends of roads of different zones: pieces [(object, zone, cut at start, cut at end)]; the
    objects' nodes are changed in place. Returns the counts."""
    from scipy.spatial import cKDTree
    ends = []                                    # (piece index, 0 / -1)
    for i, (o, z, c0, c1) in enumerate(pieces):
        if c0:
            ends.append((i, 0))
        if c1:
            ends.append((i, -1))
    stats = collections.Counter(cut_ends=len(ends))
    if not ends:
        return dict(stats)
    P = np.array([pieces[i][0]["nodes"][e] for i, e in ends], np.float64)
    D = np.array([_out_dir(pieces[i][0]["nodes"], e) for i, e in ends])
    cand = []
    for a, b in cKDTree(P[:, :2]).query_pairs(WELD_R):
        if pieces[ends[a][0]][1] == pieces[ends[b][0]][1]:
            continue
        if abs(P[a, 2] - P[b, 2]) > WELD_DZ or D[a] @ D[b] > WELD_COS:
            continue
        cand.append((float(np.hypot(*(P[a, :2] - P[b, :2]))), a, b))
    used = set()
    for d, a, b in sorted(cand):
        if a in used or b in used:
            continue
        used.update((a, b))
        m = [round(float(v), 4) for v in (P[a] + P[b]) / 2]
        for k in (a, b):
            i, e = ends[k]
            pieces[i][0]["nodes"][e] = list(m)
            if e == 0:
                pieces[i][0]["position"] = m[:3]
        stats["welded"] += 2
        stats["moved_over_5cm"] += int(d > LINK)
    # what is left: onto the nearest segment of a road of another zone (a node added there)
    left = [k for k in range(len(ends)) if k not in used]
    if left:
        segs = []
        for i, (o, z, _, _) in enumerate(pieces):
            N = np.asarray(o["nodes"], np.float64)
            for j in range(len(N) - 1):
                segs.append((i, j, N[j], N[j + 1]))
        A = np.array([s[2][:2] for s in segs])
        B = np.array([s[3][:2] for s in segs])
        mid = (A + B) / 2
        half = np.hypot(*(B - A).T) / 2
        t = cKDTree(mid)
        r_max = float(half.max()) + ONTO_R if len(half) else ONTO_R
        inserts = collections.defaultdict(list)
        for k in left:
            i, e = ends[k]
            zk = pieces[i][1]
            p = P[k]
            best = None
            for si in t.query_ball_point(p[:2], r_max):
                pi, j, a, b = segs[si]
                if pieces[pi][1] == zk:
                    continue
                ab = b[:2] - a[:2]
                L2 = ab @ ab
                f = 0.0 if L2 < 1e-12 else float(np.clip((p[:2] - a[:2]) @ ab / L2, 0, 1))
                q = a + (b - a) * f
                d = float(np.hypot(*(q[:2] - p[:2])))
                if d > ONTO_R or abs(q[2] - p[2]) > ONTO_DZ:
                    continue
                if best is None or d < best[0]:
                    best = (d, pi, j, f, q)
            if best is None:
                stats["unmatched"] += 1
                continue
            d, pi, j, f, q = best
            qq = [round(float(v), 4) for v in q]
            pieces[i][0]["nodes"][e] = list(qq[:2]) + [qq[2]] + list(pieces[i][0]["nodes"][e][3:])
            if e == 0:
                pieces[i][0]["position"] = qq[:3]
            inserts[pi].append((j, f, qq))
            stats["onto_road"] += 1
        for pi, lst in inserts.items():
            nodes = pieces[pi][0]["nodes"]
            for j, f, qq in sorted(lst, key=lambda v: (v[0], v[1]), reverse=True):
                if f <= 1e-6:
                    nodes[j] = qq[:3] + list(nodes[j][3:])
                elif f >= 1 - 1e-6:
                    nodes[j + 1] = qq[:3] + list(nodes[j + 1][3:])
                else:
                    w = [round(float(a + (b - a) * f), 4) for a, b in zip(nodes[j][3:], nodes[j + 1][3:])]
                    nodes.insert(j + 1, qq[:3] + w)
            pieces[pi][0]["position"] = nodes[0][:3]
    return dict(stats)


def graph_report(roads):
    """ai_roads.graph_report without shapely: roads linked where they share a point (within 5 cm); the pieces,
    the km off the largest one, the dead ends."""
    from scipy.spatial import cKDTree
    roads = [o for o in roads if len(o.get("nodes") or []) >= 2]
    if not roads:
        return {"roads": 0}
    P = np.concatenate([np.asarray(o["nodes"], np.float64)[:, :2] for o in roads])
    own = np.concatenate([np.full(len(o["nodes"]), i) for i, o in enumerate(roads)])
    par = list(range(len(roads)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    t = cKDTree(P)
    for a, b in t.query_pairs(LINK):
        ra, rb = find(own[a]), find(own[b])
        if ra != rb:
            par[ra] = rb
    L = np.array([np.hypot(*np.diff(np.asarray(o["nodes"], np.float64)[:, :2], axis=0).T).sum() for o in roads])
    comp = np.array([find(i) for i in range(len(roads))])
    km = collections.defaultdict(float)
    for c, l in zip(comp, L):
        km[c] += l / 1000
    main = max(km, key=km.get)
    ends = np.array([np.asarray(o["nodes"], np.float64)[e, :2] for o in roads for e in (0, -1)])
    dead = sum(1 for p in ends if len(t.query_ball_point(p, LINK)) == 1)
    drv = np.array([float(o.get("drivability", 1)) for o in roads])
    return {"roads": len(roads), "km": round(L.sum() / 1000, 1), "pieces": len(km),
            "km_main_piece": round(km[main], 1),
            "km_off_main": round(sum(v for c, v in km.items() if c != main), 1),
            "km_off_main_drivable": round(L[(comp != main) & (drv >= 0.5)].sum() / 1000, 1),
            "pieces_off_main_over_500m": sum(1 for c, v in km.items() if c != main and v > 0.5),
            "dead_ends": dead}


def old_cut(o, s):
    """region.py's first cut (the runs in the core, one node beyond on each side): for the report only."""
    nodes = o.get("nodes") or []
    inside = [s.in_core(n[0], n[1]) for n in nodes]
    out, i = [], 0
    while i < len(nodes):
        if not inside[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(nodes) and inside[j + 1]:
            j += 1
        a, b = max(i - 1, 0), min(j + 1, len(nodes) - 1)
        if b > a:
            out.append(dict(o, nodes=nodes[a:b + 1]))
        i = j + 1
    return out


def is_ai(o):
    return o.get("class") == "DecalRoad" and "drivability" in o


# ------------------------------------------------------------------ signals
def merge_signals(srcs):
    """The zones' signals.json as one: every id renumbered, names given the zone in front; a simple sign (stop,
    give way) from the zone whose core holds it, a group of traffic lights (one sequence) from the zone whose core
    holds the middle of its lights, the plain sign controllers once."""
    out = {"instances": [], "controllers": [], "sequences": []}
    simple = {}                                   # (name, type) -> new controller id
    nid = [0]

    def new_id():
        nid[0] += 1
        return nid[0]
    stats = collections.Counter()
    for s in srcs:
        p = os.path.join(s.dir, "signals.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        ctrl = {c["id"]: c for c in d.get("controllers", [])}
        seqs = d.get("sequences") or []
        if isinstance(seqs, dict):
            seqs = list(seqs.values())
        # a sequence's lights decide where it goes
        seq_of = {}
        for q in seqs:
            ids = {c for ph in q.get("phases", []) for c in ph.get("controllerIds", [])}
            insts = [i for i in d.get("instances", []) if i.get("controllerId") in ids]
            if insts:
                m = np.mean([i["pos"][:2] for i in insts], axis=0)
                seq_of[q["id"]] = s.in_core(m[0], m[1])
            else:
                seq_of[q["id"]] = False
        cmap = {}

        def ctrl_id(cid):
            if cid in cmap:
                return cmap[cid]
            c = ctrl.get(cid)
            if c is None:
                return None
            if c.get("isSimple"):
                key = (c.get("name"), c.get("type"))
                if key not in simple:
                    simple[key] = new_id()
                    out["controllers"].append(dict(c, id=simple[key]))
                cmap[cid] = simple[key]
            else:
                cmap[cid] = new_id()
                out["controllers"].append(dict(c, id=cmap[cid], name=f"{s.name}_{c.get('name', cid)}"))
            return cmap[cid]
        lights_ctrl = {c for q in seqs if seq_of[q["id"]] for ph in q.get("phases", [])
                       for c in ph.get("controllerIds", [])}
        any_seq = {c for q in seqs for ph in q.get("phases", []) for c in ph.get("controllerIds", [])}
        seq_new = {}
        for q in seqs:
            if not seq_of[q["id"]]:
                continue
            seq_new[q["id"]] = len(out["sequences"]) + 1
            out["sequences"].append(dict(q, id=seq_new[q["id"]], name=f"{s.name}_{q.get('name', q['id'])}",
                                         phases=[dict(ph, controllerIds=[ctrl_id(c) for c in ph.get("controllerIds", [])
                                                                         if ctrl_id(c) is not None])
                                                 for ph in q.get("phases", [])]))
        for i in d.get("instances", []):
            in_seq = i.get("controllerId") in lights_ctrl
            if i.get("controllerId") in any_seq:
                if not in_seq:                    # lights of a group the neighbour zone has
                    continue
            elif not s.in_core(i["pos"][0], i["pos"][1]):
                continue
            e = dict(i, id=new_id(), name=f"{s.name}_{i.get('name', i.get('id'))}")
            cid = ctrl_id(i.get("controllerId"))
            if cid is not None:
                e["controllerId"] = cid
            if "sequenceId" in i and i["sequenceId"] in seq_new:
                e["sequenceId"] = seq_new[i["sequenceId"]]
            elif "sequenceId" in i and i["sequenceId"]:
                e["sequenceId"] = 0
            if i.get("group"):
                e["group"] = f"{s.name}_{i['group']}"
            out["instances"].append(e)
            stats["lights" if in_seq else "signs"] += 1
    stats["sequences"] = len(out["sequences"])
    stats["controllers"] = len(out["controllers"])
    return out, dict(stats)


# ------------------------------------------------------------------ sites, decals
def _site_xy(e):
    if "pos" in e:
        return e["pos"][0], e["pos"][1]
    V = e.get("vertices")
    if V:
        m = np.mean(np.asarray(V, np.float64)[:, :2], axis=0)
        return m[0], m[1]
    return None


# BeamNG 0.40 freezes in the first frame of the level (one core at 100 %, minutes, then Windows closes it) when
# city.sites.json holds all 122,111 parking spots of Ticino; the 5-zone region with a few thousand ran. Keep at most
# this many, an even share of every zone's (michi's PC, 2026-10-29).
MAX_PARKING = 6000


def thin_spots(spots, limit=MAX_PARKING):
    """Every k-th spot (the list runs zone by zone, so every zone keeps its share), oldIds renumbered."""
    if len(spots) <= limit:
        return spots
    step = len(spots) / limit
    out = [dict(spots[int(i * step)]) for i in range(limit)]
    for i, e in enumerate(out):
        e["oldId"] = i + 1
    return out


def merge_sites(srcs, fname, level):
    """A sites file (city.sites.json, facilities.sites.json) of every zone as one: the spots, zones and locations
    whose position (a zone's: the middle of its vertices) lies in their zone's core, renumbered (the game wants an
    oldId on every spot and zone, CLAUDE.md), names unique."""
    out, n = None, collections.Counter()
    seen = collections.defaultdict(set)
    for s in srcs:
        p = os.path.join(s.dir, fname)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        if out is None:
            out = {k: v for k, v in d.items() if not isinstance(v, (list, dict))}
            out["dir"] = f"/levels/{level}/"
            out["locations"], out["zones"], out["parkingSpots"] = {}, [], []
        for key in ("parkingSpots", "zones"):
            for e in d.get(key, []) or []:
                xy = _site_xy(e)
                if xy is not None and not s.in_core(*xy):
                    continue
                e = dict(e, oldId=len(out[key]) + 1)
                name = e.get("name", key)
                if name in seen[key]:
                    name = f"{s.name}_{name}"
                seen[key].add(name)
                e["name"] = name
                out[key].append(e)
                n[key] += 1
        locs = d.get("locations") or {}
        for name, e in (locs.items() if isinstance(locs, dict) else enumerate(locs)):
            xy = _site_xy(e) if isinstance(e, dict) else None
            if xy is not None and not s.in_core(*xy):
                continue
            k = str(name) if str(name) not in out["locations"] else f"{s.name}_{name}"
            out["locations"][k] = e
            n["locations"] += 1
    if out is not None and len(out["parkingSpots"]) > MAX_PARKING:
        out["parkingSpots"] = thin_spots(out["parkingSpots"])
        n["parkingSpots_kept"] = len(out["parkingSpots"])
    return out, dict(n)


def merge_decals(srcs):
    """main.decals.json of every zone: the instances whose position (fields 3, 4 of a v2 instance row) lies in their
    zone's core. The pipeline writes none today (build_level), so this keeps an empty file empty."""
    out = {"header": {"name": "DecalData File", "comments": "", "version": 2}, "instances": {}}
    n = 0
    for s in srcs:
        p = os.path.join(s.dir, "main.decals.json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        for name, rows in (d.get("instances") or {}).items():
            for r in rows:
                if len(r) > 4 and not s.in_core(r[3], r[4]):
                    continue
                out["instances"].setdefault(name, []).append(r)
                n += 1
    return out, n
