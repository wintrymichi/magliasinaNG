"""Railings and fences standing on the walls along the road, found in the panoramas.

Candidates: the crest of every wall within 15 m of the road (cadastral walls: the edge of the
wall top facing the road; roadside retaining walls: their measured crest line), sampled every
0.5 m. Points 0.45 m and 0.85 m above the crest are checked in the segmented panoramas
(photo_votes.label_votes, panoramas 3-16 m away). A sample carries a barrier where 'Fence' (3)
or 'Guard Rail' (4) is >= 35 % of >= 3 votes; runs >= 3 m (gaps < 1.5 m closed) are kept, as a
chain-link fence (1.0 m, posts every 2.5 m) or, where guard-rail votes dominate, a W-beam rail
of an upper road. Samples within 1.2 m of a Strada Cantonale guardrail are skipped.
Output: work/fences.json [{kind, pts: [[x, y, z_crest], ...], support}]; build() meshes them.
"""
import json, os
import numpy as np
import shapely
from scipy.ndimage import binary_closing, label
from config import WORK
import walls, photo_votes

FENCE, RAIL = 3, 4
LEVELS = (0.45, 0.85)
NEAR_ROAD = 15.0


def crest_lines():
    """[(n,3) polyline] of wall crests facing the road."""
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    road = shapely.LineString(rp["center"])
    out = []
    for w in walls.wall_geometry():
        if w["poly"].distance(road) > NEAR_ROAD:
            continue
        ring = w["rings"][0]
        n = len(ring)
        zt = w["ztop"][:n]
        # keep the ring edges whose outward side faces the road (the crest edge seen from it)
        a = np.arange(n); b = (a + 1) % n
        mid = 0.5 * (ring[a] + ring[b])
        e = ring[b] - ring[a]
        nrm = np.column_stack([e[:, 1], -e[:, 0]]) / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)
        # exterior ring is counter-clockwise (orient(poly, 1.0)): outward normal = (dy, -dx)
        sv = shapely.line_locate_point(road, shapely.points(mid))
        C = shapely.get_coordinates(shapely.line_interpolate_point(road, sv))
        to_road = C - mid
        facing = np.einsum("ij,ij->i", nrm, to_road) > 0
        lab, k = label(facing)
        for q in range(1, k + 1):
            ii = np.where(lab == q)[0]
            idx = np.r_[ii, ii[-1] + 1] % n
            P = np.column_stack([ring[idx], zt[idx]])
            if np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1).sum() >= 2.0:
                out.append(P)
    for r in json.load(open(os.path.join(WORK, "roadside_walls.json"))):
        P = np.array(r["pts"])
        if len(P) > 1:
            out.append(np.column_stack([P[:, :2], P[:, 3]]))
    return out


def resample(P, step=0.5):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    s = np.arange(0, d[-1] + 1e-6, step)
    return np.column_stack([np.interp(s, d, P[:, k]) for k in range(3)])


def main():
    lines = [resample(P) for P in crest_lines()]
    gr = json.load(open(os.path.join(WORK, "guardrails_final.json")))
    gzone = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(1.2) for r in gr])
    pts, owner = [], []
    for i, L in enumerate(lines):
        for j, p in enumerate(L):
            for h in LEVELS:
                pts.append([p[0], p[1], p[2] + h]); owner.append((i, j))
    pts = np.array(pts)
    print("crest lines", len(lines), "samples", len(pts) // len(LEVELS))
    H = photo_votes.label_votes(pts)
    owner = np.array(owner)
    fences = []
    for i, L in enumerate(lines):
        m = owner[:, 0] == i
        h = H[m].reshape(len(L), len(LEVELS), -1).sum(1)
        tot = h.sum(1)
        frac = (h[:, FENCE] + h[:, RAIL]) / np.maximum(tot, 1)
        on = (tot >= 3) & (frac >= 0.35) & ~shapely.contains_xy(gzone, L[:, 0], L[:, 1])
        on = binary_closing(on, structure=np.ones(4))
        lab, k = label(on)
        for q in range(1, k + 1):
            ii = np.where(lab == q)[0]
            if len(ii) < 7:                                   # >= 3 m
                continue
            kind = "rail" if h[ii, RAIL].sum() > h[ii, FENCE].sum() else "fence"
            fences.append({"kind": kind, "pts": L[ii].round(3).tolist(), "support": round(float(frac[ii].mean()), 2)})
    json.dump(fences, open(os.path.join(WORK, "fences.json"), "w"))
    tot_len = sum(np.linalg.norm(np.diff(np.array(f["pts"])[:, :2], axis=0), axis=1).sum() for f in fences)
    print("fences", len(fences), "length %.0f m" % tot_len, "| rails", sum(1 for f in fences if f["kind"] == "rail"))


CH = "/assets/materials/tileable/metal/chainlink/t_chainlink_fence"
HEIGHT, POST_STEP = 1.0, 2.5


def _box(c0, c1, t, n, w):
    """Box between the centres c0 (bottom) and c1 (top), cross-section w x w along t/n."""
    q = [t * w / 2 + n * w / 2, -t * w / 2 + n * w / 2, -t * w / 2 - n * w / 2, t * w / 2 - n * w / 2]
    out = []
    for a in range(4):
        p0, p1 = q[a], q[(a + 1) % 4]
        out += [c1 + p0, c0 + p0, c0 + p1, c1 + p0, c0 + p1, c1 + p1]
    out += [c1 + q[0], c1 + q[1], c1 + q[2], c1 + q[0], c1 + q[2], c1 + q[3]]
    return np.array(out)


def fence_mesh(mb, P):
    import bng
    P = resample(np.asarray(P, float), 0.5)
    if len(P) < 2:
        return
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    base = P[:, 2] + 0.02
    top = base + HEIGHT
    B = np.column_stack([P[:, :2], base]); U = np.column_stack([P[:, :2], top])
    quads = np.stack([B[:-1], B[1:], U[1:], B[:-1], U[1:], U[:-1]], 1).reshape(-1, 3)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    u = np.stack([d[:-1], d[1:], d[1:], d[:-1], d[1:], d[:-1]], 1).ravel()
    v = np.stack([np.zeros(len(d) - 1), np.zeros(len(d) - 1), np.full(len(d) - 1, HEIGHT),
                  np.zeros(len(d) - 1), np.full(len(d) - 1, HEIGHT), np.full(len(d) - 1, HEIGHT)], 1).ravel()
    mb.add("mp_chainlink", quads, uvs=np.column_stack([u, v]), normals=bng.flat_normals_soup(quads))
    parts = []
    for sp in np.arange(0.0, d[-1] + 1e-6, POST_STEP):
        q = int(np.clip(np.searchsorted(d, sp), 0, len(P) - 1))
        t = np.r_[T[q], 0]; n = np.r_[-T[q][1], T[q][0], 0]
        parts.append(_box(np.r_[P[q, :2], base[q] - 0.25], np.r_[P[q, :2], top[q] + 0.03], t, n, 0.045))
    for k in range(len(P) - 1):                              # top rail
        a = np.r_[P[k, :2], top[k]]; b = np.r_[P[k + 1, :2], top[k + 1]]
        t = (b - a) / max(np.linalg.norm(b - a), 1e-9); n = np.r_[-t[1], t[0], 0]
        up = np.array([0, 0, 0.02])
        seg = [a - n * 0.015 - up, b - n * 0.015 - up, b + n * 0.015 - up, a + n * 0.015 - up]
        seg_t = [x + 2 * up for x in seg]
        for i in range(4):
            j = (i + 1) % 4
            parts.append(np.array([seg[i], seg[j], seg_t[j], seg[i], seg_t[j], seg_t[i]]))
    V = np.concatenate(parts)
    mb.add("mp_fence_post", V, uvs=V[:, :2], normals=bng.flat_normals_soup(V))


def build(level_dir, level_name, scene):
    import bng, guardrail_mesh
    f = os.path.join(WORK, "fences.json")
    if not os.path.exists(f):
        return
    items = json.load(open(f))
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "fences", "main.materials.json"), [
        bng.material("mp_chainlink", f"{CH}_b.color.dds", f"{CH}_nm.normal.dds", f"{CH}_r.data.dds",
                     alpha_test=40, double_sided=True, metallic=0.6, ground_type="METAL",
                     detail={"opacityMap": f"{CH}_o.data.dds"}),
        bng.material("mp_fence_post", base_color=[0.55, 0.56, 0.55, 1], roughness=0.6, metallic=0.4,
                     ground_type="METAL")])                # rails reuse the guardrail materials
    CHK = 128.0
    builders = {}
    for it in items:
        P = np.array(it["pts"])
        c = P[len(P) // 2, :2]
        key = (int(np.floor(c[0] / CHK)), int(np.floor(c[1] / CHK)))
        mb = builders.setdefault(key, bng.MeshBuilder())
        if it["kind"] == "rail":
            # W-beam of an upper road: the rail faces away from the wall edge (towards the upper road)
            guardrail_mesh.rail(mb, np.column_stack([P, np.full(len(P), 0.75)]), side=1)
        else:
            fence_mesh(mb, P)
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/fences/fence_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CHK, (ty + 0.5) * CHK, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="fence", origin=origin, orient=True)
        scene.add("MissionGroup/roads/fences", bng.tsstatic(f"/levels/{level_name}/{rel}", origin,
                                                             collision=True, decal=False))
    print("fences", len(items), "in", len(builders), "chunks")


if __name__ == "__main__":
    main()
