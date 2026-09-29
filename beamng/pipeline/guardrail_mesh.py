"""Procedural W-beam guardrails along the measured polylines (work/guardrails_final.json).

Cross-section of the rail (A-profile, 0.31 m high, 0.08 m deep) swept along the path
with its face towards the carriageway, top at the measured height; C-posts every 2 m
behind the rail, 0.3 m into the ground. Galvanised-steel material. Collision on.
The foot of the rail is re-based on the road surface of roadheight.py as guardrails2.py
does: the ground, but never lower than the road edge next to it minus 0.1 m (rails on
valley-side walls and on the bridge stand at road level).
"""
import json, os
import numpy as np
from config import WORK
import bng

# (depth towards the road, height below the top) of the rail face, top -> bottom
PROFILE = np.array([[0.00, 0.00], [0.05, 0.035], [0.08, 0.07], [0.04, 0.155], [0.08, 0.24], [0.05, 0.275],
                    [0.00, 0.31]])
POST_W, POST_D, POST_STEP = 0.10, 0.06, 2.0


def resample(P, step=0.5):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    s = np.arange(0, d[-1] + 1e-6, step)
    return np.column_stack([np.interp(s, d, P[:, k]) for k in range(P.shape[1])]), s


def rail(mb, P, side):
    """P: (n, 4) x, y, z_ground, top height; side +1 = left of travel (road to the right)."""
    P, s = resample(P)
    if len(P) < 2:
        return
    T = np.gradient(P[:, :2], axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nl = np.column_stack([-T[:, 1], T[:, 0]])
    to_road = -side * Nl                                    # horizontal unit vector towards the road
    top = P[:, 2] + P[:, 3]
    rings = []
    for d, dz in PROFILE:
        rings.append(np.column_stack([P[:, :2] + to_road * d, top - dz]))
    rings = np.array(rings)                                 # (k, n, 3)
    k, n = rings.shape[:2]
    tris = []
    for a in range(k - 1):
        A0, A1 = rings[a, :-1], rings[a, 1:]
        B0, B1 = rings[a + 1, :-1], rings[a + 1, 1:]
        tris.append(np.stack([A0, B0, B1, A0, B1, A1], 1).reshape(-1, 3))
    # back plate (flat) so the rail is closed from behind
    back_top, back_bot = rings[0], rings[-1]
    tris.append(np.stack([back_top[1:], back_bot[1:], back_bot[:-1], back_top[1:], back_bot[:-1], back_top[:-1]],
                         1).reshape(-1, 3))
    V = np.concatenate(tris)
    mb.add("mp_guardrail", V, uvs=np.column_stack([V[:, 0] + V[:, 1], V[:, 2]]) / 2.0,
           normals=bng.flat_normals_soup(V))
    # posts
    for sp in np.arange(0.5, s[-1] - 0.2, POST_STEP):
        q = int(np.clip(np.searchsorted(s, sp), 0, n - 1))
        c = P[q, :2] - to_road[q] * 0.12                     # behind the rail (spacer)
        t = T[q]; nn = to_road[q]
        z0, z1 = P[q, 2] - 0.3, top[q] - 0.02
        corners = [c + t * POST_W / 2 + nn * POST_D / 2, c - t * POST_W / 2 + nn * POST_D / 2,
                   c - t * POST_W / 2 - nn * POST_D / 2, c + t * POST_W / 2 - nn * POST_D / 2]
        box = []
        for a in range(4):
            p0, p1 = corners[a], corners[(a + 1) % 4]
            q0b, q1b = np.r_[p0, z0], np.r_[p1, z0]
            q0t, q1t = np.r_[p0, z1], np.r_[p1, z1]
            box += [q0t, q0b, q1b, q0t, q1b, q1t]
        box += [np.r_[corners[0], z1], np.r_[corners[1], z1], np.r_[corners[2], z1],
                np.r_[corners[0], z1], np.r_[corners[2], z1], np.r_[corners[3], z1]]
        box = np.array(box)
        mb.add("mp_guardrail_post", box, uvs=np.column_stack([box[:, 0] + box[:, 1], box[:, 2]]),
               normals=bng.flat_normals_soup(box))


def foot_fn():
    """Foot of a rail: max(DTM, road surface continued to the rail - 0.1 m)."""
    from geo import Grid
    import roadheight
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    S = roadheight.load()

    def fn(x, y):
        return np.maximum(dtm.sample(x, y), S.height(x, y) - 0.1)
    return fn


SV_RUNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "guardrails_sv.json")


def sv_runs(existing):
    """Guard rails of the rest of the network seen in the Street View panoramas (sv_guardrails.py, v2.2):
    [{pts: [[x, y, z of the road edge, top height]], side}], without the ones along the rails of the
    original route (existing runs, within 1.5 m)."""
    if not os.path.exists(SV_RUNS):
        return []
    import shapely
    old = shapely.union_all([shapely.LineString(np.array(r["pts"])[:, :2]).buffer(1.5) for r in existing
                             if len(r["pts"]) > 1]) if existing else None
    out = []
    for r in json.load(open(SV_RUNS)):
        P = np.array(r["pts"], float)
        if len(P) < 2:
            continue
        if old is not None:
            keep = ~shapely.contains_xy(old, P[:, 0], P[:, 1])
            if keep.sum() < 3:
                continue
            P = P[keep]
        out.append({"pts": P, "side": r["side"]})
    return out


def build(level_dir, level_name, scene):
    runs = json.load(open(os.path.join(WORK, "guardrails_final.json")))
    foot = foot_fn()
    # galvanised steel looks light grey under the overcast sky of the photos; a high metallic
    # factor made the rails mirror the (blue) sky cubemap and read dark from a distance
    mats = [bng.material("mp_guardrail", base_color=[0.80, 0.81, 0.82, 1], roughness=0.55, metallic=0.25,
                         double_sided=True, ground_type="METAL"),
            bng.material("mp_guardrail_post", base_color=[0.72, 0.73, 0.74, 1], roughness=0.6, metallic=0.25,
                         ground_type="METAL")]
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "guardrails", "main.materials.json"), mats)
    CH = 128.0
    builders = {}
    for r in runs:
        P = np.array(r["pts"])
        P[:, 2] = foot(P[:, 0], P[:, 1])
        c = P[len(P) // 2, :2]
        key = (int(np.floor(c[0] / CH)), int(np.floor(c[1] / CH)))
        rail(builders.setdefault(key, bng.MeshBuilder()), P, r["side"])
    # the rest of the network: the rails seen in the panoramas, on the edge of the road as built
    extra = sv_runs(runs)
    for r in extra:
        P = r["pts"]
        c = P[len(P) // 2, :2]
        key = (int(np.floor(c[0] / CH)), int(np.floor(c[1] / CH)))
        rail(builders.setdefault(key, bng.MeshBuilder()), P, r["side"])
    if extra:
        print("guard rails seen in the panoramas:", len(extra), "runs,",
              round(sum(np.linalg.norm(np.diff(r["pts"][:, :2], axis=0), axis=1).sum() for r in extra) / 1000, 2), "km")
    for (tx, ty), mb in sorted(builders.items()):
        rel = f"art/shapes/guardrails/gr_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * CH, (ty + 0.5) * CH, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name="guardrail", origin=origin)
        scene.add("MissionGroup/roads/guardrails", bng.tsstatic(f"/levels/{level_name}/{rel}", origin,
                                                                 collision=True, decal=False))
    print("guardrails", len(runs), "runs in", len(builders), "chunks")
