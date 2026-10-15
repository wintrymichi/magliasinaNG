"""Direction signs at the exits of the roundabouts (v3.0), in the built level.

The roundabouts of the map had no direction signs; the one at Magliaso had the boards the panoramas measured,
which without their imagery were flat blobs of one colour (the user's screenshot 04: "the signs are all doubled
and make no sense") and are gone (signs_net.py). Here every roundabout OpenStreetMap maps on the Swiss side gets,
at each exit that leaves it for a public road, a pole with the direction pointers of the Swiss standard (signs_ch.py:
4.31, blue with white letters, on the main roads; 4.32, white with black letters, on the others) naming the first
DEST_N villages the road leads to: the road network of OSM walked from the exit (shortest ways, at most REACH m,
never back through the roundabout), a village (swissNAMES3D, places.py) reached where the walk passes within NEAR m
of its name; the village the roundabout stands in is not named. The pole stands beside the exit, on the right of
the traffic leaving the ring, on free ground (not on a carriageway), the pointers facing the traffic that comes
round the ring and pointing right, to the exit.
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
DETOUR = 1.6             # a walk longer than this times the straight distance goes round the other way
RING_HALF = 4.0          # m from the mapped ring to the outer edge of the ring's carriageway
OUT = 6.0                # m along the exit from that edge to the pole
POLE_R = 0.035
BOTTOM = 1.6             # m, the lower edge of the lowest pointer over the ground
GAP = 0.04
MAIN = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
ROAD = MAIN | {"tertiary", "tertiary_link", "unclassified", "residential", "living_street", "road"}
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
            out.append((p, u, -tc, [(code, "right|" + n) for n in found], c))
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
    surf = shape_tris(zi, lv, read_items(zi, f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"))
    carr = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS]))
    tops = [up_faces(t) for t in surf.values()]
    isl = f"{lv}/main/MissionGroup/roads/islands/items.level.json"
    if isl in zi.NameToInfo:
        tops += [up_faces(t) for t in shape_tris(zi, lv, read_items(zi, isl)).values()]
    allt = TriSurface(np.concatenate(tops))
    del surf
    ter = signs_net.Terrain(zi)
    mb = bng.MeshBuilder()
    files, mats, made = {}, {}, {}
    rep = {"roundabouts_exits": len(signs), "placed": 0, "no_room": 0, "pointers": 0}
    for p, u, nrm, plates, c in signs:
        # beside the exit on the right of the leaving traffic, off the carriageway
        right = np.array([u[1], -u[0]])
        spot = None
        for off in np.arange(2.0, 12.0, 0.25):
            q = p + right * off
            if not np.isfinite(carr.height([q[0]], [q[1]], "high")[0]):
                spot = q + right * 0.6
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
        for key, pl in heights:
            zc -= pl.h / 2 + GAP / 2
            centre = spot + rt * (pl.w / 2 - 0.05)
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
