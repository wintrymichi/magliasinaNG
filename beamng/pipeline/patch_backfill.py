"""The ground behind the walls without visible triangles (v2.8), in a built level zip.

Behind every retaining wall the terrain is lowered to the wall base (walls.carve_terrain: a 1.5 m
grid cannot hold a step inside a 0.3 m wall) and a mesh on the terrain grid puts the ground back
(walls.build_backfill, materials mp_fill_<layer>). Up to v2.7 that mesh had one normal per
triangle: every triangle took its own light, unlike the smooth terrain around it, and the ground
behind the walls showed as a field of triangles and a saw along the walls. Here:

- A. Smooth light: every vertex of the backfill gets the mean of the normals of the backfill faces
  around it (within RADIUS m, weighted by area and by distance), the same at every copy of a
  position (also across chunks), so the light runs smoothly over the triangles. Where a vertex
  lies on the terrain (the outer edges of the mesh), the normal fades into the terrain's own
  (central differences of the .ter), so the mesh and the terrain take the same light along the
  seam. Positions, triangles and texture coordinates stay as they are.
- C. No groundcover clumps at the walls: the terrain vertices within one terrain square of a wall
  or of the backfill on the Grass and GardenGrass layers go to their verge layers (terrain.VERGE:
  the same look, no clumps), as the verges of the roads since v2.4. On the steep ground the carve
  leaves at a wall the billboards of the game's grass stood out of the slope as pale blades.

Only the backfill shapes and theTerrain.ter change (with a new date, so the game converts them
again); everything else is copied as it is.

Usage: python patch_backfill.py <in.zip> <out.zip>
"""
import json, re, struct, sys, time, zipfile
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import optimize_level
import terrain
from config import LEVEL_NAME, TER_X0, TER_Y0, TER_SQUARE

RADIUS = 1.5        # m, faces whose centres are this close to a vertex shade it
ON_TERRAIN = 0.30   # m: a vertex this close to the terrain takes its normal (fading out to here)
EDGE_STEP = 0.75    # m between the points sampled along the edges of the wall faces (C)


def read_items(zi, name):
    return [json.loads(l) for l in zi.read(name).decode("utf-8").splitlines() if l.strip()]


def read_ter(data):
    n = struct.unpack("<I", data[1:5])[0]
    q = np.frombuffer(data[5:5 + 2 * n * n], "<u2").reshape(n, n)
    lay = np.frombuffer(data[5 + 2 * n * n:5 + 3 * n * n], np.uint8).reshape(n, n)
    k = struct.unpack("<I", data[5 + 3 * n * n:9 + 3 * n * n])[0]
    names, o = [], 9 + 3 * n * n
    for _ in range(k):
        ln = data[o]
        names.append(data[o + 1:o + 1 + ln].decode("utf-8"))
        o += 1 + ln
    return n, q, lay, names


class Terrain:
    def __init__(self, q, z0, maxh):
        self.H = z0 + q.astype(np.float64) / 65535.0 * maxh
        n = len(self.H)
        gy, gx = np.gradient(self.H, TER_SQUARE)                 # row 0 = south: rows along +y
        N = np.stack([-gx, -gy, np.ones_like(gx)], -1)
        self.N = (N / np.linalg.norm(N, axis=-1, keepdims=True)).astype(np.float32)
        self.n = n

    def _bil(self, A, x, y):
        c = np.clip((x - TER_X0) / TER_SQUARE, 0, self.n - 1.001)
        r = np.clip((y - TER_Y0) / TER_SQUARE, 0, self.n - 1.001)
        c0, r0 = np.floor(c).astype(np.int64), np.floor(r).astype(np.int64)
        fc, fr = c - c0, r - r0
        if A.ndim == 3:
            fc, fr = fc[:, None], fr[:, None]
        return (A[r0, c0] * (1 - fc) * (1 - fr) + A[r0, c0 + 1] * fc * (1 - fr)
                + A[r0 + 1, c0] * (1 - fc) * fr + A[r0 + 1, c0 + 1] * fc * fr)

    def height(self, x, y):
        return self._bil(self.H, x, y)

    def normal(self, x, y):
        N = self._bil(self.N, x, y)
        return N / np.linalg.norm(N, axis=1, keepdims=True)


def smooth_normals(shapes, ter):
    """shapes: {zip name: (DAE text, origin)} of the backfill. Returns {zip name: new normals (n, 3)}
    and the number of vertices."""
    verts, cents, fns = {}, [], []
    for name, (text, org) in shapes.items():
        V, N, T, C, parts, _ = optimize_level.parse(text)
        Vw = V + org
        verts[name] = Vw
        for mat, idx in parts:
            t = Vw[idx[:, 0]].reshape(-1, 3, 3)
            cents.append(t.mean(1))
            fns.append(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]))     # length = 2 x area
    cents, fns = np.concatenate(cents), np.concatenate(fns)
    tree = cKDTree(cents)
    out, nv = {}, 0
    for name, Vw in verts.items():
        P, inv = np.unique(np.round(Vw, 3), axis=0, return_inverse=True)   # one normal per position
        inv = inv.ravel()
        S = cKDTree(P).sparse_distance_matrix(tree, RADIUS, output_type="coo_matrix")
        w = 1.0 - S.data / RADIUS
        acc = np.zeros((len(P), 3))
        np.add.at(acc, S.row, fns[S.col] * w[:, None])
        ln = np.linalg.norm(acc, axis=1, keepdims=True)
        Ns = np.where(ln > 1e-9, acc / np.maximum(ln, 1e-12), [0.0, 0.0, 1.0])
        wt = np.clip(1.0 - np.abs(P[:, 2] - ter.height(P[:, 0], P[:, 1])) / ON_TERRAIN, 0.0, 1.0)[:, None]
        Nn = (1.0 - wt) * Ns + wt * ter.normal(P[:, 0], P[:, 1])
        Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
        out[name] = Nn[inv]
        nv += len(Vw)
    return out, nv


def wall_vertices(zi, lv, objs, n):
    """(n, n) bool: the terrain vertices within one terrain square of a face of a wall shape."""
    hit = np.zeros((n, n), bool)
    for o in objs:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        V = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            t = V[idx[:, 0]].reshape(-1, 3, 3)[:, :, :2]
            pts = [t.mean(1)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                L = np.linalg.norm(t[:, b] - t[:, a], axis=1)
                k = np.maximum(np.ceil(L / EDGE_STEP).astype(np.int64), 1)
                rep = np.repeat(np.arange(len(t)), k)
                f = (np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)) / np.repeat(k, k)
                pts.append(t[rep, a] + (t[rep, b] - t[rep, a]) * f[:, None])
            P = np.concatenate(pts)
            c = np.round((P[:, 0] - TER_X0) / TER_SQUARE).astype(np.int64)
            r = np.round((P[:, 1] - TER_Y0) / TER_SQUARE).astype(np.int64)
            ok = (c >= 0) & (c < n) & (r >= 0) & (r < n)
            hit[r[ok], c[ok]] = True
    return ndi.binary_dilation(hit, np.ones((3, 3), bool))


def set_normals(text, N):
    fmt = " ".join(f"{v:.3f}" for v in N.ravel())
    fmt = re.sub(r"(?<![\d])-0\.000\b", "0.000", fmt)
    return re.sub(r'(<float_array id="g-na" count=")\d+(">)[^<]*(</float_array>)',
                  lambda m: f"{m.group(1)}{N.size}{m.group(2)}{fmt}{m.group(3)}", text, count=1)


def main(src, dst):
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    z0, maxh = float(blk["position"][2]), float(blk["maxHeight"])
    ter_name = f"{lv}/theTerrain.ter"
    data = zi.read(ter_name)
    n, q, lay, names = read_ter(data)
    ter = Terrain(q, z0, maxh)
    objs = read_items(zi, f"{lv}/main/MissionGroup/walls/items.level.json")
    shapes = {}
    for o in objs:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") == "TSStatic" and sn in zi.NameToInfo:
            text = zi.read(sn).decode("utf-8")
            if 'material="mp_fill_' in text:
                shapes[sn] = (text, np.asarray(o.get("position", [0, 0, 0]), np.float64))
    t0 = time.time()
    normals, nv = smooth_normals(shapes, ter)
    print("A: smooth normals on %d vertices of %d backfill shapes (%.0f s)" % (nv, len(shapes), time.time() - t0))
    new = {sn: set_normals(text, normals[sn]).encode("utf-8") for sn, (text, _) in shapes.items()}

    near = wall_vertices(zi, lv, objs, n)
    lay = lay.copy()
    moved = 0
    for a, b in terrain.VERGE.items():
        m = near & (lay == names.index(a))
        lay[m] = names.index(b)
        moved += int(m.sum())
    print("C: terrain vertices at the walls moved to the verge layers (no groundcover): %d" % moved)
    new[ter_name] = data[:5 + 2 * n * n] + lay.tobytes() + data[5 + 3 * n * n:]

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            if i.filename in new:
                # a new date: the game converts the shapes again instead of taking its cached ones
                ni = zipfile.ZipInfo(i.filename, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new[i.filename])
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
    print("%s written" % dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
