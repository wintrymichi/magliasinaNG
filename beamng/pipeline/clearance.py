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
