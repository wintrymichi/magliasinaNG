"""The ground behind the retaining walls shaded like the terrain, and no game grass under it or along the
walls (v2.8), in a built level zip.

The terrain is a 1.5 m grid and cannot hold a step inside a 0.3 m wall: walls.carve_terrain lowers every
terrain vertex whose triangles touch a wall to the foot of the wall, and walls.build_backfill covers the
trench this leaves on the high side with a mesh at the height of the ground as it was (about 784,000
triangles, 63 ha in v2.7, in art/shapes/walls/backfill_*.dae). Two things showed it in the game:
- the backfill had one normal per triangle (bng.flat_normals_soup): every triangle lit on its own, flat
  facets and saw teeth where its corners alternate between the wall top and the meadow, beside a terrain
  that is shaded smoothly;
- the grass of groundcover.py grows on the terrain layers Grass and GardenGrass, also on the vertices
  lowered under the backfill: 29 % of them are less than 0.8 m under it, and the grass clumps (0.15 to
  0.8 m) stand through the mesh; along the walls they grow on the vertices dropped to the foot of the
  wall, and over the top of the walls lower than the grass.

Here, with the geometry as it is (positions, triangles and texture coordinates of every mesh, terrain
heights; checked at the end):
- normals (A): every backfill vertex takes the normal of the ground it restores, as the terrain computes
  its own (central differences over one terrain step): the heights of the backfill on the terrain
  vertices, of the terrain elsewhere; the vertices under a wall or lowered beside it and not covered
  (their height is the foot of the wall) are left out and the difference is taken on the other side.
  Where the backfill meets the visible terrain its edge takes the normal the terrain has there, so the
  light does not jump at the seam. Vertices between the terrain vertices (where a square is cut at a
  wall or a road) interpolate the normals of the corners of their square that the backfill covers (on
  the edge of a square with none: the normal of the nearest backfill terrain vertex). The vertices are
  welded again (bng.weld_corners): with one normal per position the mesh has about 40 % fewer vertices.
- grass (C): the terrain vertices of the squares under the backfill, and those of the squares a wall
  passes through from which the tallest grass (GRASS_TALL) would reach over the wall top there, go from
  the layers Grass and GardenGrass to their twins GrassVerge and GardenGrassVerge (terrain.VERGE): the
  same material, without the grass of groundcover.py, as along the roads since v2.4. At the foot of a
  wall taller than the grass, and on the rest of the meadows (maxSlope 45 degrees), the grass stays.
The changed files get the date of the patch (the game converts the shapes again instead of taking its
cached ones); everything else is copied as it is.

Usage: python patch_wall_fill.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, json, os, re, struct, sys, tempfile, time, zipfile
import numpy as np
import bng
import groundcover
import optimize_level
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE
from terrain import VERGE

GRASS_TALL = max(t["sizeMax"] for c in groundcover.COVERS.values() for t in c[6])   # m, the tallest grass clump
ON_NODE = 2e-3        # m, a vertex this close to a terrain vertex (in x and y) is on it
SEAM_TOL = 0.02       # m, a backfill vertex this close to the terrain height on a terrain vertex lies on the terrain
SAMPLE = 0.25         # m between the samples along the edges of the wall triangles
LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def read_ter(data):
    """(n, heights (n, n) uint16, layers (n, n) uint8, layer names) of a .ter (bng.write_ter)."""
    n = struct.unpack("<I", data[1:5])[0]
    q = np.frombuffer(data, "<u2", n * n, 5).reshape(n, n)
    lay = np.frombuffer(data, np.uint8, n * n, 5 + 2 * n * n).reshape(n, n)
    o = 5 + 3 * n * n
    names = []
    for _ in range(struct.unpack("<I", data[o:o + 4])[0]):
        k = data[o + 4]
        names.append(data[o + 5:o + 5 + k].decode("utf-8"))
        o += 1 + k
    return n, q, lay, names


def canonical(V, UV, idx):
    """The non-degenerate triangles of a part, for the check that the geometry did not change: positions
    in mm and texture coordinates in 1e-4 of their corners, every triangle starting at its smallest
    corner (keeping its winding), sorted."""
    P = np.round(V[idx[:, 0]] * 1000).astype(np.int64).reshape(-1, 3, 3)
    U = np.round(UV[idx[:, 2]] * 1e4).astype(np.int64).reshape(-1, 3, 2)
    ok = ~((P[:, 0] == P[:, 1]).all(1) | (P[:, 1] == P[:, 2]).all(1) | (P[:, 0] == P[:, 2]).all(1))
    P, U = P[ok], U[ok]
    corner = np.concatenate([P, U], 2)                                   # (k, 3, 5)
    # rank of every corner within its triangle, lexicographic over its 5 numbers
    flat = corner.reshape(-1, 5)
    order = np.lexsort(flat.T[::-1])
    rank = np.empty(len(flat), np.int64)
    rank[order] = np.arange(len(flat))
    s = np.argmin(rank.reshape(-1, 3), 1)
    ar = np.arange(len(corner))
    rot = np.stack([corner[ar, (s + j) % 3] for j in range(3)], 1)          # (k, 3, 5)
    rot = np.concatenate([rot[:, :, :3].reshape(len(rot), 9), rot[:, :, 3:].reshape(len(rot), 6)], 1)
    return rot[np.lexsort(rot.T[::-1])]                                     # 9 coordinates, then 6 texture


def wall_cells(zi, objs, n):
    """(n - 1, n - 1) float32: the top of the wall meshes in every terrain square they pass through
    (the highest of samples every SAMPLE m along the edges of their triangles, and their centres),
    -inf in the others."""
    top = np.full((n - 1, n - 1), -np.inf, np.float32)
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or "/art/shapes/walls/" not in sn or "backfill" in sn:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn.lstrip("/")).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for _, idx in parts:
            t = W[idx[:, 0]].reshape(-1, 3, 3)
            pts = [t.mean(1)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                L = np.linalg.norm(t[:, b] - t[:, a], axis=1)
                k = np.maximum(np.ceil(L / SAMPLE).astype(np.int64), 1)
                rep = np.repeat(np.arange(len(t)), k + 1)
                start = np.repeat(np.cumsum(k + 1) - (k + 1), k + 1)
                f = (np.arange(len(rep)) - start) / k[rep]               # 0, 1/k, ..., 1 along every edge
                pts.append(t[rep, a] + f[:, None] * (t[rep, b] - t[rep, a]))
            P = np.concatenate(pts)
            c = np.floor((P[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
            r = np.floor((P[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
            ok = (r >= 0) & (r < n - 1) & (c >= 0) & (c < n - 1)
            np.maximum.at(top, (r[ok], c[ok]), P[ok, 2].astype(np.float32))
    return top


def corners_of(cells):
    """(n, n) bool: the terrain vertices at the corners of the squares `cells` (n - 1, n - 1)."""
    m = np.zeros((cells.shape[0] + 1, cells.shape[1] + 1), bool)
    m[:-1, :-1] |= cells
    m[1:, :-1] |= cells
    m[:-1, 1:] |= cells
    m[1:, 1:] |= cells
    return m


def main(src, dst, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    Z0, MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = read_ter(data)
    sq = TER_SQUARE
    Ht = (Z0 + q.astype(np.float64) / 65535.0 * MAXH)
    objs = read_items(zi, f"{lv}/main/MissionGroup/walls/items.level.json")

    # ---- the backfill shapes: vertices on the terrain vertices, squares covered
    shapes = []
    fill_cells = np.zeros((n - 1, n - 1), bool)
    node_z = np.full(n * n, -np.inf)
    for o in objs:
        sn = o.get("shapeName", "")
        if o.get("class") != "TSStatic" or "/art/shapes/walls/backfill" not in sn:
            continue
        name = sn.lstrip("/")
        text = zi.read(name).decode("utf-8")
        V, N, UV, C, parts, node = optimize_level.parse(text)
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        cf, rf = (W[:, 0] - TER_X0) / sq, (W[:, 1] - TER_Y0) / sq
        ci, ri = np.round(cf).astype(np.int64), np.round(rf).astype(np.int64)
        on = (np.abs(cf - ci) * sq < ON_NODE) & (np.abs(rf - ri) * sq < ON_NODE)
        flat = np.where(on, ri * n + ci, -1)
        np.maximum.at(node_z, flat[on], W[on, 2])
        for _, idx in parts:
            m = W[idx[:, 0]].reshape(-1, 3, 3).mean(1)
            fill_cells[np.floor((m[:, 1] - TER_Y0) / sq).astype(np.int64),
                       np.floor((m[:, 0] - TER_X0) / sq).astype(np.int64)] = True
        shapes.append(dict(name=name, V=V, N=N, UV=UV, C=C, parts=parts, node=node, W=W, flat=flat,
                           cf=cf, rf=rf))
    print("backfill: %d shapes, %d triangles, %d vertices, %d squares"
          % (len(shapes), sum(len(i) // 3 for s in shapes for _, i in s["parts"]), sum(len(s["V"]) for s in shapes),
             fill_cells.sum()), flush=True)

    # ---- (A) normals at the terrain vertices of the backfill
    is_fill = np.isfinite(node_z).reshape(n, n)
    covered = corners_of(fill_cells)
    valid = ~covered | is_fill                   # a height of the ground: the backfill's or the visible terrain's
    G = Ht.copy()
    G[is_fill] = node_z.reshape(n, n)[is_fill]
    nodes = np.flatnonzero(is_fill)
    r, c = np.divmod(nodes, n)
    rm, rp, cm, cp = np.maximum(r - 1, 0), np.minimum(r + 1, n - 1), np.maximum(c - 1, 0), np.minimum(c + 1, n - 1)

    def diff(ra, ca, rb, cb):
        va, vb = valid[ra, ca], valid[rb, cb]
        ga, gb, g0 = G[ra, ca], G[rb, cb], G[r, c]
        return np.where(va & vb, (gb - ga) / (2 * sq), np.where(vb, (gb - g0) / sq, np.where(va, (g0 - ga) / sq, 0.0)))
    nr = np.column_stack([-diff(r, cm, r, cp), -diff(rm, c, rp, c), np.ones(len(nodes))])
    # the terrain's own normal (the heights as they are, the lowered vertices too): at the seam
    nt = np.column_stack([-(Ht[r, cp] - Ht[r, cm]) / (2 * sq), -(Ht[rp, c] - Ht[rm, c]) / (2 * sq), np.ones(len(nodes))])
    open_cell = np.ones((n + 1, n + 1), bool)    # squares around a vertex, padded: True where no backfill
    open_cell[1:-1, 1:-1] = ~fill_cells
    seam = open_cell[r, c] | open_cell[r, c + 1] | open_cell[r + 1, c] | open_cell[r + 1, c + 1]
    seam &= np.abs(G[r, c] - Ht[r, c]) < SEAM_TOL
    nn = np.where(seam[:, None], nt, nr)
    nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    print("normals: %d terrain vertices of the backfill, %d of them on the seam with the terrain"
          % (len(nodes), int(seam.sum())), flush=True)

    def node_normal(flat):
        """Normals of terrain vertices (flat indices, all backfill vertices); NaN for the others."""
        j = np.searchsorted(nodes, flat)
        j = np.clip(j, 0, len(nodes) - 1)
        hit = nodes[j] == flat
        out = np.full((len(flat), 3), np.nan)
        out[hit] = nn[j[hit]]
        return out

    # ---- new DAEs: the same triangles with the new normals, welded again
    new_dae = {}
    st = dict(vertices_before=0, vertices_after=0, triangles=0, by_corner_interp=0, by_nearest_node=0)
    from scipy.spatial import cKDTree
    node_tree = cKDTree(np.column_stack([TER_X0 + c * sq, TER_Y0 + r * sq]))
    dev_face, dev_old = [], []
    tmp = tempfile.mkdtemp(prefix="patch_wall_fill_")
    for s in shapes:
        V, W, flat = s["V"], s["W"], s["flat"]
        Nn = np.full((len(V), 3), np.nan)
        on = flat >= 0
        Nn[on] = node_normal(flat[on])
        # vertices between the terrain vertices: the corners of their square, weighted bilinearly
        off = np.flatnonzero(np.isnan(Nn[:, 0]))
        if len(off):
            c0 = np.floor(s["cf"][off]).astype(np.int64)
            r0 = np.floor(s["rf"][off]).astype(np.int64)
            fx, fy = s["cf"][off] - c0, s["rf"][off] - r0
            acc, wsum = np.zeros((len(off), 3)), np.zeros(len(off))
            for dr, dc, w in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
                k = node_normal((r0 + dr) * n + (c0 + dc))
                ok = np.isfinite(k[:, 0]) & (w > 1e-9)
                acc[ok] += w[ok, None] * k[ok]
                wsum[ok] += w[ok]
            good = wsum > 1e-6
            Nn[off[good]] = acc[good] / wsum[good, None]
            st["by_corner_interp"] += int(good.sum())
            rest = off[~good]
            if len(rest):                         # no corner of its square on the backfill (a vertex on the
                Nn[rest] = nn[node_tree.query(W[rest, :2])[1]]      # edge of the next one): the nearest one's
                st["by_nearest_node"] += len(rest)
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
        mb = bng.MeshBuilder()
        for mat, idx in s["parts"]:
            vi, ni, ti = idx[:, 0], idx[:, 1], idx[:, 2]
            col = s["C"][idx[:, 3]] if s["C"] is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[vi], uvs=s["UV"][ti], normals=Nn[vi], colors=col)
            P = W[vi].reshape(-1, 3, 3)
            fn = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            a = np.linalg.norm(fn, axis=1)
            fn = fn[a > 1e-9] / a[a > 1e-9, None]
            nv = Nn[vi].reshape(-1, 3, 3)[a > 1e-9]
            no = s["N"][ni].reshape(-1, 3, 3)[a > 1e-9]
            dev_face.append(np.degrees(np.arccos(np.clip((nv * fn[:, None]).sum(2), -1, 1))).ravel())
            dev_old.append(np.degrees(np.arccos(np.clip((nv * no).sum(2), -1, 1))).ravel())
            st["triangles"] += len(idx) // 3
        base, detail = re.match(r"(.*)_a(\d+)$", s["node"]).groups()
        path = os.path.join(tmp, "s.dae")
        mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
        out = open(path, encoding="utf-8").read()
        # the check: the same triangles (positions, texture coordinates), material by material; the
        # writer may move all the texture coordinates of a shape by whole tiles (bng.MeshBuilder.write_dae:
        # their mean changes with the welded vertices), which draws the same
        V2, N2, UV2, C2, parts2, node2 = optimize_level.parse(out)
        assert node2 == s["node"], (s["name"], node2)
        p1, p2 = dict(s["parts"]), dict(parts2)
        assert sorted(p1) == sorted(p2), s["name"]
        shifts = set()
        for mat in p1:
            a, b = canonical(V, s["UV"], p1[mat]), canonical(V2, UV2, p2[mat])
            assert a.shape == b.shape and (a[:, :9] == b[:, :9]).all(), (s["name"], mat)
            d = b[:, 9:] - a[:, 9:]
            assert (d == np.tile(d[:1, :2], 3)).all() and not (d[:1] % 10000).any(), (s["name"], mat)
            shifts.add(tuple(d[0, :2].tolist()) if len(d) else None)
        assert len(shifts - {None}) <= 1, s["name"]
        st["vertices_before"] += len(V)
        st["vertices_after"] += len(V2)
        new_dae[s["name"]] = out.encode("utf-8")
    os.remove(os.path.join(tmp, "s.dae"))
    os.rmdir(tmp)
    dev_face, dev_old = np.concatenate(dev_face), np.concatenate(dev_old)
    print("backfill shapes rewritten: %d, the same triangles; vertices %d -> %d" %
          (len(new_dae), st["vertices_before"], st["vertices_after"]), flush=True)
    print("normal against the face: median %.1f, 95th percentile %.1f degrees (before: flat); new against old: "
          "median %.1f, 95th percentile %.1f degrees" % (np.median(dev_face), np.percentile(dev_face, 95),
                                                         np.median(dev_old), np.percentile(dev_old, 95)), flush=True)

    # ---- (C) no game grass under the backfill, nor where it would stand over the top of a wall: on the
    # vertices of the squares a wall passes through (lowered to its foot by walls.carve_terrain) less than
    # the tallest grass under the wall top there
    wtop = wall_cells(zi, objs, n)
    wcells = np.isfinite(wtop)
    pad = np.full((n + 1, n + 1), -np.inf, np.float32)
    pad[1:-1, 1:-1] = wtop
    near_top = np.maximum(np.maximum(pad[:-1, :-1], pad[:-1, 1:]), np.maximum(pad[1:, :-1], pad[1:, 1:]))
    del pad, wtop
    under = corners_of(fill_cells)
    over = corners_of(wcells) & (Ht > near_top - GRASS_TALL) & ~under
    del near_top
    grassy = np.isin(lay, [names.index(a) for a in VERGE])
    new_lay = lay.copy()
    changed = {}
    for a, b in VERGE.items():
        ia, ib = names.index(a), names.index(b)
        m = (under | over) & (lay == ia)
        new_lay[m] = ib
        changed[f"{a} -> {b}"] = int(m.sum())
    why = {"under_backfill": int((under & grassy).sum()), "over_wall_top": int((over & grassy).sum())}
    print("terrain vertices without game grass: %s, %s (squares under the backfill %d, crossed by a wall %d)"
          % (changed, why, int(fill_cells.sum()), int(wcells.sum())), flush=True)
    assert set(np.unique(lay[new_lay != lay])) <= {names.index(a) for a in VERGE}
    new_ter = data[:5 + 2 * n * n] + new_lay.tobytes() + data[5 + 3 * n * n:]
    assert len(new_ter) == len(data) and new_ter[:5 + 2 * n * n] == data[:5 + 2 * n * n]     # heights as they were

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm == ter_name or nm in new_dae:
                # a new date: the game converts the shapes again instead of taking its cached ones
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_ter if nm == ter_name else new_dae[nm])
            elif re.fullmatch(r"levels/[^/]+/README\.md", nm) and os.path.exists(LEVEL_README):
                zo.writestr(i, open(LEVEL_README, "rb").read(), compress_type=i.compress_type)
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    print("%s written in %.0f s" % (dst, time.time() - t0), flush=True)
    if report:
        res = {"source": os.path.basename(src), "backfill_shapes": len(new_dae), "backfill_triangles": st["triangles"],
               "backfill_squares": int(fill_cells.sum()), "backfill_area_ha": round(float(fill_cells.sum()) * sq * sq / 1e4, 1),
               "vertices_before": st["vertices_before"], "vertices_after": st["vertices_after"],
               "terrain_vertices_with_normal": int(len(nodes)), "seam_vertices_terrain_normal": int(seam.sum()),
               "vertices_interpolated_in_square": st["by_corner_interp"], "vertices_nearest_node": st["by_nearest_node"],
               "normal_vs_face_deg": {"median": round(float(np.median(dev_face)), 2),
                                      "p95": round(float(np.percentile(dev_face, 95)), 2)},
               "normal_new_vs_old_deg": {"median": round(float(np.median(dev_old)), 2),
                                         "p95": round(float(np.percentile(dev_old, 95)), 2)},
               "wall_squares": int(wcells.sum()), "grass_tall_m": GRASS_TALL, "grass_removed_vertices": changed,
               "grass_removed_why": why,
               "geometry_unchanged": True, "terrain_heights_unchanged": True}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
