"""Direction signs at the exits of the roundabouts (v3.0) and before the junctions of the main roads (v3.0.40),
in the built level.

The roundabouts of the map had no direction signs; the one at Magliaso had the boards the panoramas measured,
which without their imagery were flat blobs of one colour (the user's screenshot 04: "the signs are all doubled
and make no sense") and are gone (signs_net.py). Here every roundabout OpenStreetMap maps on the Swiss side gets,
at each exit that leaves it for a public road, a pole with the direction pointers of the Swiss standard (signs_ch.py:
4.31, blue with white letters, on the main roads; 4.32, white with black letters, on the others) naming the first
DEST_N villages the road leads to: the road network of OSM walked from the exit (shortest ways, at most REACH m,
never back through the roundabout), a village (swissNAMES3D, places.py) reached where the walk passes within NEAR m
of its name; the village the roundabout stands in is not named. The pole stands beside the exit, on the right of
the traffic leaving the ring, on free ground (not on a carriageway), the pointers facing the traffic that comes
round the ring and pointing right, to the exit. v3.0.40: the junctions of the main roads get them too
(plan_junctions): the same walk from every road leaving the junction, the pointers before it, on the side they
point to.
Meshes in MissionGroup/props/direction_signs; the rest of the level is copied as it is.

A finishing step of build_level.py (FINISH), after the islands and the signs; alone: python build_level.py --finish direction_signs
"""
import heapq, json, os, tempfile, time
import numpy as np
import bng
import osm
import signs_ch
from config import LEVEL_NAME
from markings_net import read_items, shape_tris, up_faces, CARRIAGE_MATS
from road_mesh import TriSurface

REACH = 7000.0           # m of road walked from an exit
NEAR = 350.0             # m: a walk this near the name of a village reaches it
HOME = 300.0             # m: the village whose name is this near the roundabout is the one it stands in
DEST_N = 2               # villages named on an exit
JUNCTION_BEFORE = 20.0   # m before a junction (its node) to its pointers
STRAIGHT = 35.0          # degrees: a road turning off less than this goes straight on and gets no pointer
RING_CLEAR = 40.0        # m beyond a roundabout's ring where its exits' pointers already stand
DETOUR = 1.6             # a walk longer than this times the straight distance goes round the other way
RING_HALF = 4.0          # m from the mapped ring to the outer edge of the ring's carriageway
OUT = 6.0                # m along the exit from that edge to the pole
POLE_R = 0.035
BOTTOM = 1.6             # m, the lower edge of the lowest pointer over the ground
GAP = 0.04
MAIN = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
ROAD = MAIN | {"tertiary", "tertiary_link", "unclassified", "residential", "living_street", "road"}
JUNCTION_ROADS = MAIN | {"tertiary", "tertiary_link", "unclassified"}   # roads with pointers at their junctions
L = f"/levels/{LEVEL_NAME}"
DIR = f"levels/{LEVEL_NAME}/art/shapes/signs/dir"


def graph(ways):
    """Adjacency {node: [(node, length, way index)]} of the public roads of OSM, and node coordinates."""
    adj, xy = {}, {}
    for i, w in enumerate(ways):
        if w["tags"].get("highway") not in ROAD or len(w["nodes"]) != len(w["xy"]):
            continue
        ow = w["tags"].get("oneway") in ("yes", "1", "true")
        rev = w["tags"].get("oneway") == "-1"
        for a, b, pa, pb in zip(w["nodes"][:-1], w["nodes"][1:], w["xy"][:-1], w["xy"][1:]):
            d = float(np.hypot(*(pb - pa)))
            xy[a], xy[b] = pa, pb
            if not rev:
                adj.setdefault(a, []).append((b, d, i))
            if not ow:
                adj.setdefault(b, []).append((a, d, i))
    return adj, xy


def walk(adj, start, banned, reach=REACH):
    """{node: distance} of the shortest walks from `start` up to `reach` m, never through `banned` nodes."""
    dist = {start: 0.0}
    q = [(0.0, start)]
    while q:
        d, n = heapq.heappop(q)
        if d > dist.get(n, np.inf) or d > reach:
            continue
        for m, l, _ in adj.get(n, ()):
            if m in banned:
                continue
            nd = d + l
            if nd < dist.get(m, np.inf):
                dist[m] = nd
                heapq.heappush(q, (nd, m))
    return dist


def roundabouts(ways):
    """[(centre, mean radius, set of ring nodes)] of the roundabouts (their ways joined by shared nodes)."""
    ring_ways = [w for w in ways if w["tags"].get("junction") in ("roundabout", "circular")]
    groups = []
    for w in ring_ways:
        ns = set(w["nodes"])
        hit = [g for g in groups if g[0] & ns]
        merged = [ns, [w["xy"]]]
        for g in hit:
            merged[0] |= g[0]
            merged[1] += g[1]
            groups.remove(g)
        groups.append(merged)
    out = []
    for ns, xys in groups:
        P = np.concatenate(xys)
        c = P.mean(0)
        out.append((c, float(np.hypot(*(P - c).T).mean()), ns))
    return out


def plan(ways, villages):
    """[(pole xy, exit direction, facing normal, [(code, value)], ring centre)] of the pointers to put up."""
    adj, xy = graph(ways)
    vx = np.array([[v[1], v[2]] for v in villages]) if villages else np.zeros((0, 2))
    out = []
    for c, rad, ring in roundabouts(ways):
        if len(vx):
            dh = np.hypot(*(vx - c).T)
            home = {villages[int(np.argmin(dh))][0]} if dh.min() < HOME else set()
        else:
            home = set()
        exits = []                                             # (way, Q from the ring outwards, {village: distance})
        for w in ways:
            t = w["tags"]
            if t.get("highway") not in ROAD or t.get("junction") in ("roundabout", "circular"):
                continue
            nodes = w["nodes"]
            for end in (0, -1):
                if nodes[end] not in ring:
                    continue
                inward = (end == -1) == (t.get("oneway") != "-1")      # walked from the far end towards the ring
                if t.get("oneway") in ("yes", "1", "true", "-1") and inward:
                    continue                                          # an entry only
                Q = w["xy"] if end == 0 else w["xy"][::-1]            # from the ring outwards
                nxt = nodes[1] if end == 0 else nodes[-2]
                dist = walk(adj, nxt, ring)
                if not dist:
                    continue
                seen = np.array([xy[n] for n in dist if n in xy])
                dd = np.array([dist[n] for n in dist if n in xy])
                reach = {}
                for i, v in enumerate(villages):
                    if v[0] in home:
                        continue
                    d = np.hypot(*(seen - vx[i]).T)
                    k = int(np.argmin(d))
                    # reached, and not by a long way round (DETOUR times the distance as the crow flies)
                    if d[k] < NEAR and dd[k] < DETOUR * float(np.hypot(*(vx[i] - c))) + NEAR:
                        reach[v[0]] = float(dd[k])
                exits.append((w, Q, reach))
        # every village on the exit that reaches it first
        best = {}
        for k, (_, _, reach) in enumerate(exits):
            for name, d in reach.items():
                if name not in best or d < best[name][0]:
                    best[name] = (d, k)
        for k, (w, Q, reach) in enumerate(exits):
            found = [n for n, _ in sorted(((n, d) for n, d in reach.items() if best[n][1] == k), key=lambda q: q[1])][:DEST_N]
            if not found:
                continue
            t = w["tags"]
            # the exit's outward direction and the point OUT m beyond the ring's carriageway
            r_out = rad + RING_HALF + OUT
            d = np.hypot(*(Q - c).T)
            kk = np.flatnonzero((d[:-1] < r_out) & (d[1:] >= r_out))
            if len(kk):
                kk = int(kk[0])
                f = (r_out - d[kk]) / max(d[kk + 1] - d[kk], 1e-9)
                p = Q[kk] + (Q[kk + 1] - Q[kk]) * f
                u = Q[kk + 1] - Q[kk]
            else:
                u = Q[-1] - Q[0]
                p = c + (Q[0] - c) / max(np.hypot(*(Q[0] - c)), 1e-9) * r_out
            u = u / max(np.hypot(*u), 1e-9)
            th = np.arctan2(*(p - c)[::-1])
            tc = np.array([-np.sin(th), np.cos(th)])              # the traffic round the ring (anticlockwise)
            code = "4.31" if t.get("highway") in MAIN else "4.32"
            out.append((p, np.array([u[1], -u[0]]), -tc, [(code, "right|" + n) for n in found], c))
    return out


def arms(ways):
    """{node: [(way index, step +1/-1 along the way, polyline from the node outwards)]} of the public roads."""
    out = {}
    for i, w in enumerate(ways):
        t = w["tags"]
        if t.get("highway") not in ROAD or t.get("junction") in ("roundabout", "circular") or len(w["nodes"]) != len(w["xy"]):
            continue
        n = w["nodes"]
        for k, node in enumerate(n):
            if k > 0:
                out.setdefault(node, []).append((i, -1, w["xy"][k::-1]))
            if k < len(n) - 1:
                out.setdefault(node, []).append((i, 1, w["xy"][k:]))
    return out


def along(Q, s):
    """The point s m along the polyline Q (its end if shorter), and whether Q is that long."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
    if d[-1] < s:
        return Q[-1], False
    k = int(np.searchsorted(d, s)) - 1
    f = (s - d[k]) / max(d[k + 1] - d[k], 1e-9)
    return Q[k] + (Q[k + 1] - Q[k]) * f, True


def plan_junctions(ways, villages, rings=()):
    """[(pole xy, side to put the pole on, facing normal, [(code, value)], junction xy)] of the pointers before
    the junctions of the roads between the villages (v3.0.40): at a node where three or more public roads meet,
    at least one of them a main road (MAIN or tertiary), every road leaving it (JUNCTION_ROADS) gets the villages
    it reaches first among the junction's roads (the walk of the roundabouts, never back through the junction);
    a driver coming in on one of those roads sees, JUNCTION_BEFORE m before the junction, the pointers to the
    roads that turn off (more than STRAIGHT degrees), the ones to the right on a pole on the right of the road,
    the ones to the left on a pole on its left."""
    adj, xy = graph(ways)
    vx = np.array([[v[1], v[2]] for v in villages]) if villages else np.zeros((0, 2))
    A = arms(ways)
    ring_c = [(c, r) for c, r, _ in rings]
    out = []
    for node, am in A.items():
        if len(am) < 3 or node not in xy:
            continue
        J = xy[node]
        cls = [ways[i]["tags"].get("highway") for i, _, _ in am]
        if not any(c in MAIN or c == "tertiary" for c in cls):
            continue
        if any(np.hypot(*(J - c)) < r + RING_CLEAR for c, r in ring_c):
            continue
        if len(vx):
            dh = np.hypot(*(vx - J).T)
            home = {villages[int(np.argmin(dh))][0]} if dh.min() < HOME else set()
        else:
            home = set()
        reach = []
        for i, step, Q in am:
            t = ways[i]["tags"]
            ow = t.get("oneway")
            leaves = not ((ow in ("yes", "1", "true") and step < 0) or (ow == "-1" and step > 0))
            r = {}
            if leaves and t.get("highway") in JUNCTION_ROADS and len(Q) > 1:
                nodes = ways[i]["nodes"]
                k = nodes.index(node)
                nxt = nodes[k + step]
                first = float(np.hypot(*(Q[1] - Q[0])))
                dist = walk(adj, nxt, {node})
                seen = np.array([xy[n] for n in dist if n in xy])
                dd = np.array([dist[n] for n in dist if n in xy]) + first
                for vi, v in enumerate(villages):
                    if v[0] in home or not len(seen):
                        continue
                    d = np.hypot(*(seen - vx[vi]).T)
                    kk = int(np.argmin(d))
                    if d[kk] < NEAR and dd[kk] < DETOUR * float(np.hypot(*(vx[vi] - J))) + NEAR:
                        r[v[0]] = float(dd[kk])
            reach.append(r)
        best = {}
        for k, r in enumerate(reach):
            for name, d in r.items():
                if name not in best or d < best[name][0]:
                    best[name] = (d, k)
        dest = [[n for n, _ in sorted(((n, d) for n, d in r.items() if best[n][1] == k), key=lambda q: q[1])][:DEST_N]
                for k, r in enumerate(reach)]
        heads = []
        for i, step, Q in am:
            e, _ = along(Q, 25.0)
            h = e - J
            heads.append(h / max(np.hypot(*h), 1e-9))
        for a, (i, step, Q) in enumerate(am):
            t = ways[i]["tags"]
            if t.get("highway") not in JUNCTION_ROADS:
                continue
            ow = t.get("oneway")
            if (ow in ("yes", "1", "true") and step > 0) or (ow == "-1" and step < 0):
                continue                                          # no traffic comes in on it
            p, long_enough = along(Q, JUNCTION_BEFORE)
            if not long_enough:
                continue
            u = -heads[a]                                         # the incoming traffic's heading
            right, left = [], []
            for b in range(len(am)):
                if b == a or not dest[b]:
                    continue
                turn = np.degrees(np.arctan2(u[0] * heads[b][1] - u[1] * heads[b][0], u @ heads[b]))
                if abs(turn) < STRAIGHT:
                    continue
                code = "4.31" if ways[am[b][0]]["tags"].get("highway") in MAIN else "4.32"
                (left if turn > 0 else right).extend((code, ("left|" if turn > 0 else "right|") + n) for n in dest[b])
            if right:
                out.append((p, np.array([u[1], -u[0]]), -u, right, J))
            if left:
                out.append((p, np.array([-u[1], u[0]]), -u, left, J))
    return out


def direction_signs_step(root, report=None):
    import places
    import signs_net
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    ways, _ = osm.load()
    villages = [v for v in places.villages()]
    signs = plan(ways, villages)
    n_ring = len(signs)
    signs += plan_junctions(ways, villages, roundabouts(ways))
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    carr = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS]))
    tops = [up_faces(t) for t in surf.values()]
    hard = [t for m, t in surf.items() if m.startswith("mp_hard_")]
    yards = TriSurface(np.concatenate([up_faces(t) for t in hard])) if hard else None
    isl = f"{lv}/main/MissionGroup/roads/islands/items.level.json"
    if isl in zi.NameToInfo:
        tops += [up_faces(t) for t in shape_tris(zi, lv, read_items(zi, isl)).values()]
    allt = TriSurface(np.concatenate(tops))
    del surf
    ter = signs_net.Terrain(zi)
    mb = bng.MeshBuilder()
    files, mats, made = {}, {}, {}
    rep = {"roundabouts_exits": n_ring, "junction_poles": len(signs) - n_ring, "placed": 0, "no_room": 0, "pointers": 0}
    for k, (p, right, nrm, plates, c) in enumerate(signs):
        at_junction = k >= n_ring
        if at_junction and not np.isfinite(carr.height([p[0]], [p[1]], "high")[0]):
            rep["off_mesh"] = rep.get("off_mesh", 0) + 1         # a road of OSM the level has no carriageway for
            continue
        # beside the road on the given side (the right of the traffic leaving a roundabout), off the carriageway
        # and, before a junction, not in a yard or square either (a pole the cars there would hit)
        spot = None
        for off in np.arange(2.0, 12.0, 0.25):
            q = p + right * off
            if not np.isfinite(carr.height([q[0]], [q[1]], "high")[0]):
                spot = q + right * 0.6
                if at_junction and yards is not None and np.isfinite(yards.height([spot[0]], [spot[1]], "high")[0]):
                    spot = None
                break
        if spot is None:
            rep["no_room"] += 1
            continue
        zr = allt.height([spot[0]], [spot[1]], "high")[0]
        z0 = float(zr) if np.isfinite(zr) else float(ter([spot[0]], [spot[1]])[0])
        heights = []
        for code, val in plates:
            pl = signs_ch.plate(code, val)
            key = signs_net.slug(code, val)
            if key not in made:
                col, op = signs_net.rgba_files(pl.img)
                files[f"{DIR}/{key}_b.color.png"] = col
                files[f"{DIR}/{key}_o.data.png"] = op
                mats[f"mp_{key}"] = bng.material(f"mp_{key}", f"/{DIR}/{key}_b.color.png", roughness=0.35, alpha_test=100,
                                                ground_type="METAL", detail={"opacityMap": f"/{DIR}/{key}_o.data.png"})
                mats[f"mp_{key}_back"] = bng.material(f"mp_{key}_back", base_color=[0.59, 0.6, 0.6, 1], roughness=0.5,
                                                      metallic=0.5, alpha_test=100, ground_type="METAL",
                                                      detail={"opacityMap": f"/{DIR}/{key}_o.data.png"})
                made[key] = pl
            heights.append((key, made[key]))
        zc = z0 + BOTTOM + sum(pl.h + GAP for _, pl in heights)
        # the pointer's root at the pole, its tip towards the exit (right of the face as seen by the driver)
        rt = np.array([-nrm[1], nrm[0]])
        for (key, pl), (code, val) in zip(heights, plates):
            zc -= pl.h / 2 + GAP / 2
            tip = -rt if val.startswith("left|") else rt
            centre = spot + tip * (pl.w / 2 - 0.05)
            F, uv = signs_net.plate_quads(centre, nrm, zc, pl.w, pl.h, off=0.05)
            mb.add(f"mp_{key}", F, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
            Bk = F[::-1] - np.r_[nrm * 0.006, 0]
            mb.add(f"mp_{key}_back", Bk, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))
            zc -= pl.h / 2 + GAP / 2
            rep["pointers"] += 1
        top = z0 + BOTTOM + sum(pl.h + GAP for _, pl in heights) + 0.05
        T = signs_net.tube(spot, z0 - 0.3, top, r=POLE_R)
        mb.add("mp_dir_pole", T, normals=bng.flat_normals_soup(T))
        rep["placed"] += 1
    mats["mp_dir_pole"] = bng.material("mp_dir_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6)
    rel = "art/shapes/signs/dir/direction_signs.dae"
    with tempfile.TemporaryDirectory() as tmp:
        if not mb.empty():
            f = os.path.join(tmp, "d.dae")
            mb.write_dae(f, name="direction_signs")
            files[f"{lv}/{rel}"] = open(f, "rb").read()
        files[f"{DIR}/direction.materials.json"] = json.dumps(mats, indent=1).encode("utf-8")
    g_items = f"{lv}/main/MissionGroup/props/direction_signs/items.level.json"
    obj = bng.tsstatic(f"{L}/{rel}", (0, 0, 0), collision=True)
    obj["__parent"] = "direction_signs"
    files[g_items] = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8") if not mb.empty() else b""
    p_items = f"{lv}/main/MissionGroup/props/items.level.json"
    rows = read_items(zi, p_items)
    if not any(r.get("name") == "direction_signs" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "direction_signs", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
    files[p_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename in files or i.filename.startswith(DIR + "/"):
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(n, data)
    rep["seconds"] = round(time.time() - t0)
    print("direction signs:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
