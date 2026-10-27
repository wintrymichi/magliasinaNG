"""Emulation of the game's AI map build (lua/ge/map.lua, BeamNG 0.40.1) over the AI DecalRoads of a level, built
from their control points (useSubdivisions false), to find the edges that crash it.

map.lua's optimizeNodes removes a middle node between n1 and n2 and, when n1 already links n2, builds a new edge
with NO lanes and compares it with that edge (edgeCompare): if every field before `lanes` ties, `nil < string`
raises "attempt to compare nil with string" (L459) and the level load fails (laptop run 5, 2026-10-27). The passes
below follow map.lua's linkMap: loadJsonDecalMap, mergeOverlappingNodes(true), optimizeNodes,
mergeOverlappingNodes(), (resolveT/XJunctions and mergeNodesToLines are not emulated), mergeOverlappingNodes(),
optimizeNodes. Lua's pairs order is not known: each seed walks the nodes in another order.

    python3 aimap_check.py <AIRoads items.level.json> [seeds]
"""

import json
import random
import sys

import numpy as np
from scipy.spatial import cKDTree


SPEED_AUTO = 13.9


class Crash(Exception):
    pass


def flip_lanes(lanes):
    return "".join("-" if c == "+" else "+" if c == "-" else "0" for c in reversed(lanes))


def is_one_way(lanes):
    return "-" not in lanes or "+" not in lanes


def lanes_from_radius(r1, r2):
    return max(1, int(np.floor(min(r1, r2 if r2 is not None else np.inf) * 2 / 3.61 + 0.5)))


def edge_lanes(e):
    if e["oneWay"]:
        return "+" * lanes_from_radius(e["inRadius"], e["outRadius"])
    n = max(1, int(np.floor(lanes_from_radius(e["inRadius"], e["outRadius"]) * 0.5)))
    return "-" * n + "+" * n


def sort_ends(e):
    a = (e["inPos"], e["inRadius"])
    b = (e["outPos"], e["outRadius"])
    return (a, b) if (a[0], a[1]) <= (b[0], b[1]) else (b, a)


def edge_less(a, b):
    """map.lua edgeCompare; raises Crash where it would compare nil with a string."""
    (ap0, ar0), (ap1, ar1) = sort_ends(a)
    (bp0, br0), (bp1, br1) = sort_ends(b)
    if ap0 != bp0:
        return ap0 < bp0
    if ar0 != br0:
        return ar0 < br0
    if ap1 != bp1:
        return ap1 < bp1
    if ar1 != br1:
        return ar1 < br1
    if a["drivability"] != b["drivability"]:
        return a["drivability"] < b["drivability"]
    if a["oneWay"] != b["oneWay"]:
        return int(bool(a["oneWay"])) < int(bool(b["oneWay"]))
    if a.get("speedLimit") != b.get("speedLimit"):
        return (a.get("speedLimit") or 0) < (b.get("speedLimit") or 0)
    la, lb = a.get("lanes"), b.get("lanes")
    if la != lb:
        if la is None or lb is None:
            raise Crash((a, b))
        return la < lb
    if a.get("type") != b.get("type"):
        return (a.get("type") or "") < (b.get("type") or "")
    if bool(a.get("noMerge")) != bool(b.get("noMerge")):
        return int(bool(a.get("noMerge"))) < int(bool(b.get("noMerge")))
    return False


class Map:
    def __init__(self, roads, rng):
        self.rng = rng
        self.nodes = {}
        for road in roads:
            self.load_road(road)

    def keys(self, d):
        k = list(d)
        self.rng.shuffle(k)
        return k

    def load_road(self, road):
        if not road.get("drivability", 1) > 0 or len(road["nodes"]) < 2:
            return
        prefix = road["name"]
        one_way = bool(road.get("oneWay", False))
        flip = bool(road.get("flipDirection", False))
        no_merge = True if not road.get("autoJunction") else None
        # 0.40.1 does not read a DecalRoad's speedLimit from items.level.json (an in-game probe read nil on every
        # road, laptop run 6): createSpeedLimits fills one in, here the same for every road (the worst case)
        speed = SPEED_AUTO
        lanes = None
        if road.get("autoLanes", True) is False:
            lanes = "-" * max(0, road.get("lanesLeft", 0)) + "+" * max(0, road.get("lanesRight", 0))
            one_way = is_one_way(lanes)
            if one_way and lanes[:1] == "-":
                lanes = flip_lanes(lanes)
                flip = not flip
        pts = np.asarray(road["nodes"], dtype=np.float32).astype(float).tolist()   # the engine keeps float32
        prev = "%s_%d" % (prefix, 1)
        self.nodes[prev] = dict(pos=tuple(pts[0][:3]), radius=pts[0][3] * 0.5, links={}, noMerge=no_merge, endNode=True)
        for i in range(1, len(pts)):
            name = "%s_%d" % (prefix, i + 1)
            self.nodes[name] = dict(pos=tuple(pts[i][:3]), radius=pts[i][3] * 0.5, links={}, noMerge=no_merge)
            n_in = name if flip else prev
            n_out = prev if n_in == name else name
            e = dict(drivability=road["drivability"], oneWay=one_way, lanes=lanes, speedLimit=speed,
                     inNode=n_in, outNode=n_out, inPos=self.nodes[n_in]["pos"], outPos=self.nodes[n_out]["pos"],
                     inRadius=self.nodes[n_in]["radius"], outRadius=self.nodes[n_out]["radius"], type=None,
                     noMerge=no_merge, road=prefix)
            self.nodes[name]["links"][prev] = e
            self.nodes[prev]["links"][name] = e
            if e["lanes"] is None:
                e["lanes"] = edge_lanes(e)
            prev = name
        self.nodes[prev]["endNode"] = True

    def merge_links(self, n1id, n2id):
        n1, n2 = self.nodes[n1id], self.nodes[n2id]
        n1["links"].pop(n2id, None)
        n2["links"].pop(n1id, None)
        for lid in self.keys(n2["links"]):
            e = n2["links"][lid]
            ln = self.nodes.get(lid)
            if ln is None:
                continue
            if lid in n1["links"] and edge_less(n1["links"][lid], e):
                ln["links"].pop(n2id, None)
                n2["links"].pop(lid, None)
            else:
                e["inNode"] = n1id if e["inNode"] == n2id else lid
                e["outNode"] = lid if e["inNode"] == n1id else n1id
                ln["links"].pop(n2id, None)
                ln["links"][n1id] = e
                n1["links"][lid] = e
        del self.nodes[n2id]
        return n1id

    def merge_overlapping(self, end_only=False):
        ids = [k for k in self.keys(self.nodes)
               if not (self.nodes[k]["noMerge"] or end_only) or self.nodes[k].get("endNode")]
        if not ids:
            return
        P = np.array([self.nodes[k]["pos"] for k in ids])
        R = np.array([self.nodes[k]["radius"] for k in ids])
        par = list(range(len(ids)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i

        for a, b in cKDTree(P[:, :2]).query_pairs(2.0 * max(R.max(), 0.1) + 1e-6):
            if abs(P[a, 0] - P[b, 0]) > R[a] + R[b] or abs(P[a, 1] - P[b, 1]) > R[a] + R[b]:
                continue
            d2 = float(((P[a] - P[b]) ** 2).sum())
            ok = (d2 < 0.01 and abs(R[a] - R[b]) < 0.1) if end_only else d2 < max(R[a], R[b]) ** 2
            if ok:
                par[find(a)] = find(b)
        groups = {}
        for i in range(len(ids)):
            groups.setdefault(find(i), []).append(ids[i])
        for g in groups.values():
            if len(g) < 2:
                continue
            self.rng.shuffle(g)
            pos = [self.nodes[k]["pos"] for k in g]
            rad = [self.nodes[k]["radius"] for k in g]
            nid = g[0]
            for k in g[1:]:
                nid = self.merge_links(nid, k)
            n = self.nodes[nid]
            n["pos"] = tuple(np.mean(pos, axis=0).tolist())
            n["radius"] = float(np.mean(rad))
            n["noMerge"] = None
            n["endNode"] = None

    def two_seg_ok(self, mid, d1, d2):
        if d1.get("lanes") and d2.get("lanes"):
            if d1["inNode"] == d2["inNode"] or (d1["inNode"] != mid and d2["inNode"] != mid):
                return d1["lanes"] == flip_lanes(d2["lanes"])
            return d1["lanes"] == d2["lanes"]
        if not d1.get("lanes") and not d2.get("lanes"):
            if d1["oneWay"] == d2["oneWay"]:
                return d1["oneWay"] is False or not (
                    d1["inNode"] == d2["inNode"] or (d1["inNode"] != mid and d2["inNode"] != mid))
            return False
        return False

    def is_junction(self, nid):
        links = self.nodes[nid]["links"]
        if len(links) != 2:
            return True
        d1, d2 = list(links.values())
        return not (self.two_seg_ok(nid, d1, d2) and d1.get("type") == d2.get("type")
                    and d1["drivability"] == d2["drivability"] and d1.get("speedLimit") == d2.get("speedLimit"))

    def optimize(self, crashes):
        N = self.nodes
        junction = {k: self.is_junction(k) for k in N}
        visited = set()
        for nid in self.keys(N):
            if nid not in N or nid in visited or junction.get(nid, True):
                continue
            path = [nid]
            visited.add(nid)
            loop = False
            while True:
                links = list(N[path[-1]]["links"])
                prev = path[-2] if len(path) > 1 else None
                nxt = next((k for k in links if k != prev), links[0]) if links else None
                if nxt is None:
                    break
                if nxt == nid:
                    path.append(path[0])
                    loop = True
                    break
                path.append(nxt)
                visited.add(nxt)
                if junction.get(nxt, True):
                    if junction.get(path[0], True):
                        break
                    path.reverse()
            first, last = (path[0], path[-1]) if path[0] != path[-1] else (path[1], path[-2])
            if N[last]["pos"] < N[first]["pos"]:
                path.reverse()
            keep = set()
            pos = [np.array(N[k]["pos"]) for k in path]
            rad = [N[k]["radius"] for k in path]
            stack, i, k = [], 0, len(path) - 1
            while k is not None:
                best, bj = 0.0, None
                for j in range(i + 1, k):
                    d2 = seg_d2(pos[j], pos[i], pos[k])
                    if d2 > best:
                        best, bj = d2, j
                if bj is not None and best > (rad[bj] * 0.05) ** 2:
                    keep.add(bj)
                    stack.append(k)
                    k = bj
                else:
                    i = k
                    k = stack.pop() if stack else None
            plen = np.concatenate([[0.0], np.cumsum([np.linalg.norm(pos[j] - pos[j - 1]) for j in range(1, len(path))])])
            stack, i, k = [], 0, len(path) - 1
            while k is not None:
                best, bj = 0.0, None
                for j in range(i + 1, k):
                    t = (plen[j] - plen[i]) / max(plen[k] - plen[i], 1e-12)
                    dr = abs(rad[j] - (rad[i] + (rad[k] - rad[i]) * t))
                    if dr > best:
                        best, bj = dr, j
                if bj is not None and best > 0.1 * rad[bj]:
                    keep.add(bj)
                    stack.append(k)
                    k = bj
                else:
                    i = k
                    k = stack.pop() if stack else None
            prev_node = None
            for i in range(1, len(path) - 1):
                if i in keep:
                    prev_node = None
                    continue
                n1id = prev_node or path[i - 1]
                mid, n2id = path[i], path[i + 1]
                n1, n2 = N[n1id], N[n2id]
                d1, d2 = n1["links"].pop(mid), n2["links"].pop(mid)
                del N[mid]
                if n2id in n1["links"]:
                    e1 = n1["links"][n2id]
                    n_in = n2id if d1["inNode"] == mid else n1id
                    n_out = n2id if d1["outNode"] == mid else n1id
                    e2 = dict(drivability=min(d1["drivability"], d2["drivability"]),
                              speedLimit=min(d1["speedLimit"], d2["speedLimit"]), oneWay=d1["oneWay"],
                              inNode=n_in, outNode=n_out, type=d1.get("type"), road="e2")
                    e2["inPos"] = (d1["inPos" if d1["inNode"] == n1id else "outPos"] if n_in == n1id
                                   else d2["inPos" if d2["inNode"] == n2id else "outPos"])
                    e2["outPos"] = (d1["outPos" if d1["outNode"] == n1id else "inPos"] if n_out == n1id
                                    else d2["outPos" if d2["outNode"] == n2id else "inPos"])
                    e2["inRadius"] = (d1["inRadius" if d1["inNode"] == n1id else "outRadius"] if n_in == n1id
                                      else d2["inRadius" if d2["outNode"] == n2id else "outRadius"])
                    e2["outRadius"] = (d1["outRadius" if d1["outNode"] == n1id else "inRadius"] if n_out == n1id
                                       else d2["outRadius" if d2["outNode"] == n2id else "inRadius"])
                    prev_node = n1id
                    try:
                        less = edge_less(e2, e1)
                    except Crash:
                        crashes.append((n1id, mid, n2id, d1.get("road"), d2.get("road"), e1.get("road"), n1["pos"]))
                        less = False
                    if less:
                        n1["links"][n2id] = e2
                        n2["links"][n1id] = e2
                else:
                    d1["drivability"] = min(d1["drivability"], d2["drivability"])
                    d1["speedLimit"] = min(d1["speedLimit"], d2["speedLimit"])
                    d1["inNode"] = n2id if d1["inNode"] == mid else n1id
                    d1["outNode"] = n2id if d1["outNode"] == mid else n1id
                    d1["inPos"] = (d1["inPos" if d1["inNode"] == n1id else "outPos"] if d1["inNode"] == n1id
                                   else d2["inPos" if d2["inNode"] == n2id else "outPos"])
                    d1["outPos"] = (d1["outPos" if d1["outNode"] == n1id else "inPos"] if d1["outNode"] == n1id
                                    else d2["outPos" if d2["outNode"] == n2id else "inPos"])
                    d1["inRadius"] = (d1["inRadius" if d1["inNode"] == n1id else "outRadius"] if d1["inNode"] == n1id
                                      else d2["inRadius" if d2["inNode"] == n2id else "outRadius"])
                    d1["outRadius"] = (d1["outRadius" if d1["outNode"] == n1id else "inRadius"] if d1["outNode"] == n1id
                                       else d2["outRadius" if d2["outNode"] == n2id else "inRadius"])
                    d1["noMerge"] = None
                    n1["links"][n2id] = d1
                    n2["links"][n1id] = d1
                    prev_node = n1id


def seg_d2(p, a, b):
    ab = b - a
    L = float(ab @ ab)
    t = 0.0 if L == 0 else min(1.0, max(0.0, float((p - a) @ ab) / L))
    d = p - (a + t * ab)
    return float(d @ d)


def check(roads, seeds=8):
    """The crashes found over `seeds` node orders: [(seed, pass, n1, mid, n2, road d1, road d2, road e1, pos)]."""
    found = []
    for seed in range(seeds):
        rng = random.Random(seed)
        m = Map(roads, rng)
        steps = (("merge_end", lambda c: m.merge_overlapping(True)), ("optimize1", m.optimize),
                 ("merge", lambda c: m.merge_overlapping()), ("merge2", lambda c: m.merge_overlapping()),
                 ("optimize2", m.optimize))
        for name, fn in steps:
            crashes = []
            try:
                fn(crashes)
            except Crash as c:
                crashes.append(("mergeLinks",) + tuple(str(x)[:80] for x in c.args))
            found += [(seed, name) + tuple(c) for c in crashes]
    return found


if __name__ == "__main__":
    roads = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
    roads = [r for r in roads if r.get("class") == "DecalRoad"]
    res = check(roads, int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    print(len(res), "crashing compares")
    for r in res[:30]:
        print(r)
