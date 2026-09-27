"""Keeping the road clear, shared by the level build and patch_release.py.

clear_paved: vegetation off the paved surfaces (vegetation.py). The canopy model puts a tree
where its crown peaks, which over a road is often the middle of the carriageway, and the shrub
and hedge models are scaled wider than the gap between the road and the verge.
keep_to_surface: an AI line that stays on one surface (ai_roads.py).
"""
import numpy as np

TRUNK_CLEAR = 0.5      # m, trees with the trunk on a paved surface or closer than this are dropped
EDGE_OVERHANG = 0.2    # m, how far a shrub or hedge may reach over a paved edge
MAX_SHIFT = 1.5        # m, shrubs and hedges that would have to move farther are dropped


def clear_paved(entries, dist_dir):
    """Keep the vegetation off the paved surfaces. entries: list of dicts with x, y, kind ('tree',
    'bush', 'hedge'), r (half width across, m), L (half length along theta, hedges), theta.
    dist_dir(x, y) -> (signed distance to the paved areas, negative inside; unit vector away
    from them). Returns per entry None (dropped) or the (x, y) to use."""
    out = [None] * len(entries)
    if not entries:
        return out
    X = np.array([e["x"] for e in entries]); Y = np.array([e["y"] for e in entries])
    d0, _, _ = dist_dir(X, Y)
    for i, e in enumerate(entries):
        if e["kind"] == "tree":
            out[i] = (e["x"], e["y"]) if d0[i] >= TRUNK_CLEAR else None
            continue
        if d0[i] > e["r"] + e.get("L", 0.0):
            out[i] = (e["x"], e["y"])
            continue
        x, y = e["x"], e["y"]
        moved = 0.0
        for _ in range(3):
            if e["kind"] == "hedge":
                t = np.linspace(-e["L"], e["L"], max(3, int(np.ceil(2 * e["L"] / 0.5)) + 1))
                px, py = x + np.cos(e["theta"]) * t, y + np.sin(e["theta"]) * t
            else:
                px, py = np.array([x]), np.array([y])
            d, ux, uy = dist_dir(px, py)
            j = int(np.argmin(d))
            need = e["r"] - EDGE_OVERHANG - d[j]
            if need <= 0:
                out[i] = (x, y)
                break
            moved += need + 0.05
            if moved > MAX_SHIFT:
                break
            x, y = x + ux[j] * (need + 0.05), y + uy[j] * (need + 0.05)
    return out


def keep_to_surface(P, hfn, on_paved, max_off=5.0, step=0.5, max_rise=0.8):
    """Move the nodes of a line (P: (n,2), ~5 m apart) sideways by up to `max_off` m so that
    consecutive nodes do not jump between surfaces at different heights (Viterbi over the lateral
    offsets: cost = offset + 200 x height jump beyond `max_rise` + lateral change; off the paved
    area is excluded). Returns the moved nodes and their heights."""
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.column_stack([-T[:, 1], T[:, 0]])
    offs = np.arange(-max_off, max_off + 1e-6, step)
    Q = P[:, None, :] + N[:, None, :] * offs[None, :, None]           # (n, k, 2)
    Z = hfn(Q[..., 0].ravel(), Q[..., 1].ravel()).reshape(Q.shape[:2])
    ok = on_paved(Q[..., 0].ravel(), Q[..., 1].ravel()).reshape(Q.shape[:2])
    ok[:, offs == 0] = True                                          # the measured line is always allowed
    unary = 0.1 * np.abs(offs)[None, :] + np.where(ok, 0.0, 1e3)
    n, k = Z.shape
    cost = unary[0].copy()
    back = np.zeros((n, k), int)
    lat = 0.2 * np.abs(offs[:, None] - offs[None, :])
    for i in range(1, n):
        jump = np.abs(Z[i][None, :] - Z[i - 1][:, None])              # (prev, cur)
        tot = cost[:, None] + lat + 200.0 * np.maximum(jump - max_rise, 0.0)
        back[i] = np.argmin(tot, axis=0)
        cost = tot[back[i], np.arange(k)] + unary[i]
    j = np.zeros(n, int)
    j[-1] = int(np.argmin(cost))
    for i in range(n - 1, 0, -1):
        j[i - 1] = back[i, j[i]]
    return Q[np.arange(n), j], Z[np.arange(n), j], offs[j]


# ---------------------------------------------------------------------- v2.0: the whole network
ROAD_CLEAR = 1.0       # m, no tree trunk closer than this to a road, square or bridge deck
PATH_CLEAR = 0.5       # m, ... to a path
LOW_TREE = 6.0         # m, lower trees reach the road with their crown: kept off like shrubs
MOVE_TREE = 3.0        # m, trees that would have to move farther are dropped
TILE_D = 500.0


class Drivable:
    """Signed distance (negative inside) and outward direction to the drivable surfaces, roads and
    paths apart, from exact geometry merged per TILE_D m tile."""

    def __init__(self, roads, paths):
        import shapely
        self.shapely = shapely
        self.sets = {"road": list(roads), "path": list(paths)}
        self.trees = {k: shapely.STRtree(v) if v else None for k, v in self.sets.items()}
        self.cache = {}

    def _tile(self, kind, tx, ty):
        key = (kind, tx, ty)
        if key not in self.cache:
            sh = self.shapely
            box = sh.box(tx * TILE_D - 30, ty * TILE_D - 30, (tx + 1) * TILE_D + 30, (ty + 1) * TILE_D + 30)
            tree = self.trees[kind]
            g = sh.Polygon()
            if tree is not None:
                ids = tree.query(box, predicate="intersects")
                if len(ids):
                    g = sh.union_all([self.sets[kind][i] for i in ids]).intersection(box.buffer(10))
            if not g.is_empty:
                sh.prepare(g)
            self.cache[key] = (g, g.boundary if not g.is_empty else None)
            if len(self.cache) > 64:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[key]

    def dist_dir(self, kind, x, y):
        """(d, ux, uy) for the surfaces of `kind`: d signed (m, 99 far away), u away from them."""
        sh = self.shapely
        x = np.atleast_1d(np.asarray(x, float)); y = np.atleast_1d(np.asarray(y, float))
        d = np.full(len(x), 99.0)
        u = np.tile([1.0, 0.0], (len(x), 1))
        tx, ty = np.floor(x / TILE_D).astype(int), np.floor(y / TILE_D).astype(int)
        for key in set(zip(tx.tolist(), ty.tolist())):
            m = np.flatnonzero((tx == key[0]) & (ty == key[1]))
            g, edge = self._tile(kind, *key)
            if edge is None:
                continue
            pts = sh.points(x[m], y[m])
            inside = sh.contains_xy(g, x[m], y[m])
            dist = sh.distance(edge, pts)
            near = dist < 20.0
            lines = sh.shortest_line(pts[near], edge)
            c = sh.get_coordinates(lines).reshape(-1, 2, 2)
            v = c[:, 1] - c[:, 0]                          # from the point to the outline
            nrm = np.linalg.norm(v, axis=1, keepdims=True)
            v = v / np.maximum(nrm, 1e-9)
            v[~inside[near]] *= -1                         # outside: away from the outline
            dd = np.where(inside, -dist, dist)
            d[m] = np.minimum(dd, 99.0)
            uu = u[m]
            uu[near] = v
            u[m] = uu
        return d, u[:, 0], u[:, 1]


def clear_network(entries, drv):
    """Keep the vegetation off every drivable surface (v2.0 rules). entries: dicts x, y, kind
    ('tree', 'bush', 'hedge'), r (crown / half width m), L, theta (hedges), h (height m).
    A tree trunk must stay ROAD_CLEAR m from roads and PATH_CLEAR m from paths; trees lower than
    LOW_TREE m and shrubs must not reach over them (EDGE_OVERHANG); what is too close moves
    outwards (trees up to MOVE_TREE m, shrubs MAX_SHIFT m) or is dropped.
    Returns per entry None (dropped) or the (x, y) to use."""
    out = [None] * len(entries)
    if not entries:
        return out
    X = np.array([e["x"] for e in entries]); Y = np.array([e["y"] for e in entries])
    need = {}
    for kind, clear in (("road", ROAD_CLEAR), ("path", PATH_CLEAR)):
        d, _, _ = drv.dist_dir(kind, X, Y)
        need[kind] = d
    for i, e in enumerate(entries):
        low = e["kind"] != "tree" or e.get("h", 99.0) < LOW_TREE
        reach = (e["r"] + e.get("L", 0.0) - EDGE_OVERHANG) if low else 0.0
        req = {"road": max(ROAD_CLEAR, reach), "path": max(PATH_CLEAR, reach)}
        if need["road"][i] >= req["road"] and need["path"][i] >= req["path"]:
            out[i] = (e["x"], e["y"])
            continue
        limit = MOVE_TREE if e["kind"] == "tree" else MAX_SHIFT
        x, y, moved = e["x"], e["y"], 0.0
        for _ in range(4):
            worst, step, ux, uy = None, 0.0, 0.0, 0.0
            for kind in ("road", "path"):
                if e["kind"] == "hedge":
                    t = np.linspace(-e["L"], e["L"], max(3, int(np.ceil(2 * e["L"] / 0.5)) + 1))
                    px, py = x + np.cos(e["theta"]) * t, y + np.sin(e["theta"]) * t
                    reqk = max(PATH_CLEAR if kind == "path" else ROAD_CLEAR, e["r"] - EDGE_OVERHANG)
                else:
                    px, py = np.array([x]), np.array([y])
                    reqk = req[kind]
                d, vx, vy = drv.dist_dir(kind, px, py)
                j = int(np.argmin(d))
                if reqk - d[j] > step:
                    step, ux, uy = reqk - d[j], vx[j], vy[j]
            if step <= 0:
                out[i] = (x, y)
                break
            moved += step + 0.05
            if moved > limit:
                break
            x, y = x + ux * (step + 0.05), y + uy * (step + 0.05)
    return out
