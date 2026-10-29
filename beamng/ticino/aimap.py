"""The AI road graph of the Ticino level, made at build time (the game's own graph is useless here).

The game (lua/ge/map.lua, 0.40) builds its AI graph from the AI DecalRoads at load and at every map.reset(): it takes
their subdivided edges clipped to the TERRAIN, which exists only in the 3 km window round the car. Every node outside
it lies at z 0, map.findClosestRoad (3D, at most 200 m) finds nothing there, so 4,020 of the 4,065 signals and give-ways
failed ("Map node could not be set") and traffic ran only near the spawn; reading the 57,298 roads also cost 28-30 s
of map.reset and 1.7 + 1.8 s of DecalRoad re-clipping at the first jump (thread "Precalcolare la mappa IA del Ticino",
2026-10-29).

Here the graph is made from the roads' control points, which carry the true road heights (4 m apart, from the zone
builds), with the passes of map.lua's linkMap: road ends merged (mergeOverlappingNodes), road ends that stop on another
road joined to it (resolveTJunctions), straight runs thinned (optimizeNodes, the same tolerances). The game loads it
with map.loadMap(nodes) (ticino/aimap.lua), which skips linkMap, and the AI DecalRoads leave the scene.

    python aimap.py <level folder> [--out <file>]   (default <level>/ai/aimap.bin)

File (little endian): b"TAIM", u32 version, u32 nodes, u32 edges, u32 roads (types), then
    nodes  f32 x, y, z, radius                                   (16 bytes each)
    edges  u32 in node, u32 out node, u16 type, u16 flags       (12 bytes; flags bit0 oneWay, bit1 gated)
    types  json (utf-8, u32 length first): [[drivability, speedLimit, lanes], ...]
An edge's lanes run from its in node to its out node, as map.lua stores them.
"""
import argparse
import json
import os
import struct
import sys
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

VERSION = 1
MAGIC = b"TAIM"
END_MERGE = 0.1             # mergeOverlappingNodes(true): road ends this close (and radii within END_DR) are one node
END_DR = 0.1
T_JOIN = 1.5                # a road end this close (3D) to a node of another road joins it (resolveTJunctions)
T_JOIN_DZ = 1.0             # ... and never across more height than this (a road over or under another)
RDP_POS = 0.05              # optimizeNodes: a middle node stays if it lies more than 5 % of its radius off the line
RDP_RAD = 0.1               # ... or its radius differs more than 10 % from the line's
SPEED_AUTO = 13.9           # m/s where a road gives none
Z_MIN = -100.0              # control points under this lie outside the DTM (one road of ti_m3_9 at -700 m)


def log(*a):
    print(time.strftime("%H:%M:%S"), "aimap", *a, flush=True)


def flip_lanes(lanes):
    return "".join("-" if c == "+" else "+" if c == "-" else "0" for c in reversed(lanes))


def auto_lanes(r1, r2, one_way):
    """map.lua with autoLanes: lanes from the narrower end (width / 3.61, rounded), half each way on a two-way road."""
    n = max(1, int(np.floor(min(r1, r2) * 2 / 3.61 + 0.5)))
    if one_way:
        return "+" * n
    k = max(1, n // 2)
    return "-" * k + "+" * k


def road_items(level):
    """Every DecalRoad of the scene with a drivability, as map.lua takes them: the AI roads and the tunnels' roads
    (main/MissionGroup/tunnels: without them the network fell apart at every tunnel, 396 pieces)."""
    for root, _, files in os.walk(os.path.join(level, "main")):
        if "items.level.json" not in files:
            continue
        with open(os.path.join(root, "items.level.json")) as f:
            for line in f:
                if '"DecalRoad"' in line and '"drivability"' in line:
                    o = json.loads(line)
                    if o.get("class") == "DecalRoad":
                        yield o


class Graph:
    def __init__(self):
        self.P = None          # (n, 3)
        self.R = None          # (n,)
        self.E = None          # (m, 2) in node, out node
        self.T = None          # (m,) type index
        self.F = None          # (m,) flags
        self.types = []
        self.end = None        # (n,) bool: a road's first or last node
        self.road = None       # (n,) road index of the node (before merging)

    # ------------------------------------------------------------------ loadJsonDecalMap
    def load(self, roads):
        P, R, E, T, F, end, rid = [], [], [], [], [], [], []
        tix = {}
        n0 = 0
        skipped = 0
        for k, o in enumerate(roads):
            if not o.get("drivability", 1) > 0 or len(o.get("nodes", ())) < 2:
                continue
            pts = np.asarray(o["nodes"], dtype=np.float64)
            if pts[:, 2].min() < Z_MIN:
                skipped += 1
                continue
            one_way = bool(o.get("oneWay", False))
            flip = bool(o.get("flipDirection", False))
            lanes = None
            if o.get("autoLanes", True) is False:
                lanes = "-" * max(0, int(o.get("lanesLeft", 0))) + "+" * max(0, int(o.get("lanesRight", 0)))
                if not lanes:
                    lanes = None
                else:
                    one_way = "-" not in lanes or "+" not in lanes
                    if one_way and lanes[0] == "-":
                        lanes = flip_lanes(lanes)
                        flip = not flip
            speed = float(o.get("speedLimit") or SPEED_AUTO)
            drv = float(o["drivability"])
            gated = bool(o.get("gatedRoad", False))
            n = len(pts)
            P.append(pts[:, :3])
            R.append(pts[:, 3] * 0.5)
            e = np.ones(n, bool)
            e[1:-1] = False
            end.append(e)
            rid.append(np.full(n, k, np.int32))
            a = np.arange(n0, n0 + n - 1)
            b = a + 1
            ins, outs = (b, a) if flip else (a, b)
            E.append(np.stack([ins, outs], 1))
            fl = (1 if one_way else 0) | (2 if gated else 0)
            F.append(np.full(n - 1, fl, np.uint16))
            if lanes is not None:
                key = (drv, round(speed, 3), lanes)
                t = tix.setdefault(key, len(tix))
                T.append(np.full(n - 1, t, np.int32))
            else:
                # lanes from the radii of each edge, as map.lua does for an edge with no lanes of its own
                r = pts[:, 3] * 0.5
                tt = np.empty(n - 1, np.int32)
                for i in range(n - 1):
                    key = (drv, round(speed, 3), auto_lanes(r[i], r[i + 1], one_way))
                    tt[i] = tix.setdefault(key, len(tix))
                T.append(tt)
            n0 += n
        self.P = np.concatenate(P)
        self.R = np.concatenate(R)
        self.E = np.concatenate(E).astype(np.int64)
        self.T = np.concatenate(T)
        self.F = np.concatenate(F)
        self.end = np.concatenate(end)
        self.road = np.concatenate(rid)
        self.types = [list(k) for k, _ in sorted(tix.items(), key=lambda kv: kv[1])]
        log("roads read: %d nodes, %d edges, %d edge types, %d roads outside the terrain left out"
            % (len(self.P), len(self.E), len(self.types), skipped))

    # ------------------------------------------------------------------ helpers
    def _collapse(self, labels, keep_pos=None):
        """Nodes with one label become one node (mean position and radius, or the position of keep_pos)."""
        uniq, inv = np.unique(labels, return_inverse=True)
        m = len(uniq)
        cnt = np.bincount(inv, minlength=m).astype(float)
        P = np.stack([np.bincount(inv, self.P[:, i], m) for i in range(3)], 1) / cnt[:, None]
        R = np.bincount(inv, self.R, m) / cnt
        if keep_pos is not None:
            sel = np.flatnonzero(keep_pos)
            P[inv[sel]] = self.P[sel]
            R[inv[sel]] = self.R[sel]
        end = np.zeros(m, bool)
        np.logical_or.at(end, inv, self.end)
        merged = cnt > 1
        end[merged] = False                # map.lua clears endNode on a merged node
        road = np.full(m, -1, np.int32)
        road[inv] = self.road
        road[merged] = -1
        self.P, self.R, self.end, self.road = P, R, end, road
        self.E = inv[self.E]
        self._clean_edges()
        return merged

    def _clean_edges(self):
        """No edge from a node to itself; of two edges between the same nodes the first stays (map.lua keeps one)."""
        ok = self.E[:, 0] != self.E[:, 1]
        self.E, self.T, self.F = self.E[ok], self.T[ok], self.F[ok]
        lo = np.minimum(self.E[:, 0], self.E[:, 1])
        hi = np.maximum(self.E[:, 0], self.E[:, 1])
        _, first = np.unique(lo * (len(self.P) + 1) + hi, return_index=True)
        first.sort()
        self.E, self.T, self.F = self.E[first], self.T[first], self.F[first]

    def _union(self, pairs, n):
        if len(pairs) == 0:
            return np.arange(n)
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
        return connected_components(g, directed=False)[1]

    def degree(self):
        return np.bincount(self.E.ravel(), minlength=len(self.P))

    # ------------------------------------------------------------------ mergeOverlappingNodes
    def merge_ends(self):
        ids = np.flatnonzero(self.end)
        P, R = self.P[ids], self.R[ids]
        pairs = cKDTree(P).query_pairs(END_MERGE, output_type="ndarray")
        if len(pairs):
            pairs = pairs[np.abs(R[pairs[:, 0]] - R[pairs[:, 1]]) < END_DR]
        lab = np.arange(len(self.P))
        comp = self._union(pairs, len(ids))
        lab[ids] = len(self.P) + comp
        n0 = len(self.P)
        merged = self._collapse(lab)
        log("road ends merged: %d -> %d nodes (%d junction nodes)" % (n0, len(self.P), merged.sum()))

    def merge_overlapping(self):
        """The second pass: merged nodes and road ends closer (3D) than the larger radius."""
        cand = np.flatnonzero(self.end | (self.road < 0))
        P, R = self.P[cand], self.R[cand]
        pairs = cKDTree(P).query_pairs(float(R.max()) if len(R) else 0.0, output_type="ndarray")
        if len(pairs):
            d2 = ((P[pairs[:, 0]] - P[pairs[:, 1]]) ** 2).sum(1)
            pairs = pairs[d2 < np.maximum(R[pairs[:, 0]], R[pairs[:, 1]]) ** 2]
        lab = np.arange(len(self.P))
        comp = self._union(pairs, len(cand))
        lab[cand] = len(self.P) + comp
        n0 = len(self.P)
        self._collapse(lab)
        log("overlapping nodes merged: %d -> %d nodes" % (n0, len(self.P)))

    # ------------------------------------------------------------------ resolveTJunctions
    def join_t(self):
        """A road end left alone (one link) on another road's node becomes that node: the welding (region_net)
        put a node into the other road wherever a road ends on it."""
        deg = self.degree()
        ends = np.flatnonzero(deg == 1)
        tree = cKDTree(self.P[:, :2])
        res = tree.query_ball_point(self.P[ends, :2], T_JOIN)
        lab = np.arange(len(self.P))
        keep = np.zeros(len(self.P), bool)
        neigh = {}
        for a, b in self.E:
            neigh.setdefault(a, set()).add(b)
            neigh.setdefault(b, set()).add(a)
        joined = 0
        for e, cand in zip(ends, res):
            best, bd = None, None
            near = neigh.get(e, set())
            for c in cand:
                if c == e or c in near or (self.road[c] >= 0 and self.road[c] == self.road[e]):
                    continue
                dz = abs(self.P[c, 2] - self.P[e, 2])
                if dz > T_JOIN_DZ:
                    continue
                d = float(((self.P[c] - self.P[e]) ** 2).sum())
                if bd is None or d < bd:
                    best, bd = c, d
            if best is not None and lab[best] == best:
                lab[e] = best
                keep[best] = True
                joined += 1
        self._collapse(lab, keep_pos=keep)
        log("road ends joined to another road: %d (dead ends left %d)" % (joined, int((self.degree() == 1).sum())))

    # ------------------------------------------------------------------ optimizeNodes
    def optimize(self):
        """Middle nodes of a run of two-link nodes with the same edge type go where the run stays within RDP_POS of
        their radius off the line (3D) and RDP_RAD in radius, as map.lua's optimizeNodes."""
        n = len(self.P)
        m = len(self.E)
        deg = self.degree()
        inc = [[] for _ in range(n)]
        for k, (a, b) in enumerate(self.E):
            inc[a].append(k)
            inc[b].append(k)

        def same(k1, k2, mid):
            if self.T[k1] != self.T[k2] or self.F[k1] != self.F[k2]:
                return False
            # the lanes keep their sense through the middle: one edge comes in, the other goes out
            a_in = self.E[k1, 1] == mid
            b_out = self.E[k2, 0] == mid
            return a_in == b_out

        mid_ok = np.zeros(n, bool)
        for v in np.flatnonzero(deg == 2):
            k1, k2 = inc[v]
            mid_ok[v] = same(k1, k2, v)
        seen_e = np.zeros(m, bool)
        drop = np.zeros(n, bool)
        new_edges = []
        for k0 in range(m):
            if seen_e[k0]:
                continue
            a, b = self.E[k0]
            if mid_ok[a] and mid_ok[b]:
                continue                   # inside a run: started from its end
            # walk from a non-middle end through middles
            start = b if mid_ok[a] else a
            path_n, path_e = [start], []
            cur, k = start, k0
            while True:
                seen_e[k] = True
                path_e.append(k)
                nxt = self.E[k, 1] if self.E[k, 0] == cur else self.E[k, 0]
                path_n.append(nxt)
                if not mid_ok[nxt] or nxt == start:
                    break
                k = inc[nxt][0] if inc[nxt][0] != k else inc[nxt][1]
                cur = nxt
            if len(path_n) < 3:
                continue
            idx = np.array(path_n)
            keep = self._rdp(idx)
            if keep.all():
                continue
            # the edges of the kept run: one edge between consecutive kept nodes, its sense from the first edge
            kn = idx[keep]
            ke = np.flatnonzero(keep)
            for i in range(len(kn) - 1):
                k_first = path_e[ke[i]]
                forward = self.E[k_first, 0] == idx[ke[i]]
                e = (kn[i], kn[i + 1]) if forward else (kn[i + 1], kn[i])
                new_edges.append((e, self.T[k_first], self.F[k_first]))
            for k in path_e:
                seen_e[k] = True
            drop[idx[~keep]] = True
            self._replaced = getattr(self, "_replaced", set())
            self._replaced.update(path_e)
        rep = np.zeros(m, bool)
        if getattr(self, "_replaced", None):
            rep[list(self._replaced)] = True
        self._replaced = set()
        E = [self.E[~rep]]
        T = [self.T[~rep]]
        F = [self.F[~rep]]
        if new_edges:
            E.append(np.array([e for e, _, _ in new_edges], np.int64))
            T.append(np.array([t for _, t, _ in new_edges], self.T.dtype))
            F.append(np.array([f for _, _, f in new_edges], self.F.dtype))
        self.E, self.T, self.F = np.concatenate(E), np.concatenate(T), np.concatenate(F)
        keepn = ~drop
        newid = np.cumsum(keepn) - 1
        self.P, self.R, self.end, self.road = self.P[keepn], self.R[keepn], self.end[keepn], self.road[keepn]
        self.E = newid[self.E]
        n0 = n
        self._clean_edges()
        log("straight runs thinned: %d -> %d nodes, %d edges" % (n0, len(self.P), len(self.E)))

    def _rdp(self, idx):
        P, R = self.P[idx], self.R[idx]
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        keep = np.zeros(len(idx), bool)
        keep[0] = keep[-1] = True
        stack = [(0, len(idx) - 1)]
        while stack:
            i, k = stack.pop()
            if k - i < 2:
                continue
            a, b = P[i], P[k]
            ab = b - a
            ll = float(ab @ ab)
            q = P[i + 1:k] - a
            t = np.clip((q @ ab) / ll, 0, 1) if ll > 0 else np.zeros(len(q))
            d = np.linalg.norm(q - t[:, None] * ab, axis=1)
            tl = (L[i + 1:k] - L[i]) / max(L[k] - L[i], 1e-12)
            dr = np.abs(R[i + 1:k] - (R[i] + (R[k] - R[i]) * tl))
            r = R[i + 1:k]
            bad = np.maximum(d / np.maximum(RDP_POS * r, 1e-6), dr / np.maximum(RDP_RAD * r, 1e-6))
            j = int(np.argmax(bad))
            if bad[j] > 1.0:
                keep[i + 1 + j] = True
                stack.append((i, i + 1 + j))
                stack.append((i + 1 + j, k))
        return keep

    # ------------------------------------------------------------------ report and file
    def report(self):
        deg = self.degree()
        g = coo_matrix((np.ones(len(self.E)), (self.E[:, 0], self.E[:, 1])), shape=(len(self.P),) * 2)
        nc, lab = connected_components(g, directed=False)
        sizes = np.bincount(lab)
        L = np.linalg.norm(self.P[self.E[:, 0]] - self.P[self.E[:, 1]], axis=1)
        return {"nodes": int(len(self.P)), "edges": int(len(self.E)), "km": round(float(L.sum()) / 1000, 1),
                "dead_ends": int((deg == 1).sum()), "junctions": int((deg >= 3).sum()),
                "pieces": int(nc), "largest_piece_nodes": int(sizes.max()) if nc else 0,
                "pieces_under_10_nodes": int((sizes < 10).sum()), "edge_types": len(self.types),
                "longest_edge_m": round(float(L.max()), 1) if len(L) else 0}

    def write(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        types = json.dumps(self.types, separators=(",", ":")).encode()
        nodes = np.empty((len(self.P), 4), "<f4")
        nodes[:, :3] = self.P
        nodes[:, 3] = self.R
        edges = np.zeros(len(self.E), dtype=[("a", "<u4"), ("b", "<u4"), ("t", "<u2"), ("f", "<u2")])
        edges["a"], edges["b"], edges["t"], edges["f"] = self.E[:, 0], self.E[:, 1], self.T, self.F
        assert len(self.types) < 65536
        with open(path + ".tmp", "wb") as f:
            f.write(MAGIC + struct.pack("<4I", VERSION, len(self.P), len(self.E), len(self.types)))
            f.write(nodes.tobytes())
            f.write(edges.tobytes())
            f.write(struct.pack("<I", len(types)))
            f.write(types)
        os.replace(path + ".tmp", path)


def read(path):
    """The file back as (nodes (n, 4) float32, edges structured array, types)."""
    with open(path, "rb") as f:
        b = f.read()
    assert b[:4] == MAGIC
    ver, n, m, nt = struct.unpack_from("<4I", b, 4)
    o = 20
    nodes = np.frombuffer(b, "<f4", n * 4, o).reshape(n, 4)
    o += n * 16
    edges = np.frombuffer(b, [("a", "<u4"), ("b", "<u4"), ("t", "<u2"), ("f", "<u2")], m, o)
    o += m * 12
    (ln,) = struct.unpack_from("<I", b, o)
    types = json.loads(b[o + 4:o + 4 + ln])
    return nodes, edges, types


def is_ai_road(o):
    return o.get("class") == "DecalRoad" and "drivability" in o


def build(level=None, out=None, roads=None):
    """The graph of the level folder's scene (or of `roads`, DecalRoad objects) into `out`; returns the report."""
    t0 = time.time()
    g = Graph()
    g.load(road_items(level) if roads is None else roads)
    g.merge_ends()
    g.merge_overlapping()
    g.join_t()
    g.optimize()
    rep = g.report()
    out = out or os.path.join(level, "ai", "aimap.bin")
    g.write(out)
    rep["seconds"] = round(time.time() - t0, 1)
    rep["bytes"] = os.path.getsize(out)
    log("graph:", json.dumps(rep))
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("level")
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.exit(0 if build(a.level, a.out) else 1)
