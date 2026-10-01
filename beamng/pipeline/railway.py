"""The railway lines of the area as tracks (v2.1): the Lugano - Ponte Tresa line (FLP, metre gauge) and the
standard-gauge tracks of the SBB near Manno and Lamone (the main line, the sidings of the industrial zones).

swissTLM3D (TLM_EISENBAHN) has every track as a 3D line; up to v2.0 the level only had their ballast
painted on the terrain (land cover 'binario'). Every line outside tunnels and buildings becomes:
- a bed: sleepers (concrete, SLEEPER_STEP m apart) and two rails at the gauge of the line (1000 mm
  Schmalspur, 1435 mm Normalspur), on a ballast shoulder that meets the terrain at its sides;
  the height is that of the line in swissTLM3D: the terrain build lowers the ground under the bed to
  it (carve_terrain: a cutting where the slope of a road above covers part of the bed, as beside the
  cantonal road along the lake at Agno) and where the terrain of the level is lower the bed stands
  on an embankment (up to RAISE m); never under the terrain across the whole bed, smoothed over
  SMOOTH m; where the line runs more than COVER m under the terrain across its whole bed (under the
  parking deck of the Ponte Tresa station) it is left out, like the tunnels;
- at level crossings (a road mesh under the track, within LEVEL_DZ m of its height) only the rails,
  their heads flush with the road surface;
- on the bridges of swissTLM3D (KUNSTBAUTE Bruecke) a deck (bridges.deck_geometry) at the height of the
  line, the track on it, with no pier on the roads under it.
The catenary of the electrified lines is not built (its masts are not in the data).
One mesh per 512 m tile in MissionGroup/railway, with collision.
"""
import json, os
import numpy as np
import shapely
from scipy.ndimage import gaussian_filter1d
import bng
from config import DATA, LEVEL_NAME, lv95_to_local
import area

GAUGE = {"Schmalspur": 1.000, "Normalspur": 1.435}
SLEEPER_LEN = {"Schmalspur": 1.90, "Normalspur": 2.60}
SLEEPER_STEP = 0.62
SLEEPER_W, SLEEPER_H = 0.26, 0.16
RAIL_W, RAIL_H = 0.07, 0.15
BALLAST_EXTRA = 0.35          # m of ballast beyond the sleepers on each side
BALLAST_SLOPE = 0.9           # m out, down to the terrain
SMOOTH = 6.0                  # m, smoothing of the bed along the line
STEP = 1.0                    # m between the stations of a track
LEVEL_DZ = 0.6                # m, a road mesh this close to the bed is a level crossing
RAISE = 2.5                   # m, the line may stand this far over the terrain of the level (on an embankment)
COVER = 1.0                   # m, a line this far under the terrain across its whole bed runs under a deck: left out
CARVE_W = 0.3                 # m of the terrain lowered beyond the ballast (carve_terrain)
CARVE_MAX = 4.0               # m, deepest the terrain is lowered under a track
CUT_SLOPE = 1.5               # m of rise per m of the sides of a cutting, beyond the flat bed
EMBANK = 1.5                  # horizontal m per m of height of the ballast embankment (at least BALLAST_SLOPE)
EMBANK_MAX = 3.0              # m, widest embankment beside the ballast
FLUSH = 0.008                 # m, heads of the rails over the road surface at a level crossing
DECK_HW = {"Schmalspur": 2.2, "Normalspur": 2.7}
TILE = 512.0
CLIP = 30.0                   # m, the tracks run this far beyond the playable area
SKIP = {"Tunnel", "in/auf Gebaeude", "Unterfuehrung"}
L = f"/levels/{LEVEL_NAME}"


def tracks():
    """[(props, (n, 3) local x, y, z of swissTLM3D)] of the railway lines in the area."""
    f = os.path.join(DATA, "tlm", "TLM_EISENBAHN.json")
    if not os.path.exists(f):
        return []
    keep = area.polygon().buffer(CLIP)
    out = []
    for ft in json.load(open(f))["features"]:
        p = ft["props"]
        if p.get("KUNSTBAUTE") in SKIP or p.get("OBJEKTART") not in GAUGE:
            continue
        for part in ft["parts"]:
            P = np.array(part, np.float64)
            if len(P) < 2:
                continue
            x, y = lv95_to_local(P[:, 0], P[:, 1])
            Q = np.column_stack([x, y, P[:, 2]])
            # the runs of the line inside the area (densified: the cut falls within a metre)
            Qd, _ = resample(Q, 1.0)
            ins = shapely.contains_xy(keep, Qd[:, 0], Qd[:, 1])
            e = np.flatnonzero(np.diff(np.r_[0, ins.astype(int), 0]))
            for a, b in zip(e[::2], e[1::2]):
                if b - a >= 3:
                    out.append((p, Qd[a:b]))
    return out


def carve_terrain(H, xs, ys, keep=None):
    """Terrain heights H (rows ys, columns xs) with the ground under the tracks (outside bridges) no
    higher than the line of swissTLM3D minus 0.05 m within half = SLEEPER_LEN / 2 + BALLAST_EXTRA +
    CARVE_W m of the axis, and beyond it no higher than a side of CUT_SLOPE (a cutting, smooth on the
    terrain grid); lowered by at most CARVE_MAX m, not at the vertices of keep (the ground carved for
    the roads, whose walls stand there), not where the ground is higher than the line by COVER m all
    across the bed (a deck over the tracks)."""
    from scipy.spatial import cKDTree
    from scipy.ndimage import maximum_filter1d, minimum_filter1d
    sq = xs[1] - xs[0]
    n = 0
    for props, Q in tracks():
        if props.get("KUNSTBAUTE") == "Bruecke":
            continue
        half = SLEEPER_LEN[props["OBJEKTART"]] / 2 + BALLAST_EXTRA + CARVE_W
        reach = half + CARVE_MAX / CUT_SLOPE
        P3, _ = resample(Q, 0.5)
        c0 = max(int(np.floor((P3[:, 0].min() - reach - xs[0]) / sq)), 0)
        c1 = min(int(np.ceil((P3[:, 0].max() + reach - xs[0]) / sq)) + 1, len(xs))
        r0 = max(int(np.floor((P3[:, 1].min() - reach - ys[0]) / sq)), 0)
        r1 = min(int(np.ceil((P3[:, 1].max() + reach - ys[0]) / sq)) + 1, len(ys))
        if c1 <= c0 or r1 <= r0:
            continue
        X, Y = np.meshgrid(xs[c0:c1], ys[r0:r1])
        d, j = cKDTree(P3[:, :2]).query(np.column_stack([X.ravel(), Y.ravel()]), distance_upper_bound=reach)
        inb = np.flatnonzero(np.isfinite(d))
        if not len(inb):
            continue
        sub = H[r0:r1, c0:c1].ravel()
        h, z, d = sub[inb], P3[j[inb], 2] - 0.05, d[inb]
        bed = d <= half
        # a deck: the ground over the line all across the bed, the lowest vertex of the bed within 3 m
        # along the line (the vertices nearest to one station may all lie on one side of it)
        low = np.full(len(P3), np.inf)
        np.minimum.at(low, j[inb][bed], (h - z)[bed])
        low = minimum_filter1d(low, 13)                                                          # +- 3 m
        deck = maximum_filter1d((np.isfinite(low) & (low > COVER)).astype(np.uint8), 13) > 0   # +- 3 m
        target = z + np.maximum(d - half, 0.0) * CUT_SLOPE
        cut = (h > target) & (h - target <= CARVE_MAX) & ~deck[j[inb]]
        if keep is not None:
            cut &= ~keep[r0:r1, c0:c1].ravel()[inb]
        sub[inb[cut]] = target[cut]
        H[r0:r1, c0:c1] = sub.reshape(r1 - r0, c1 - c0)
        n += int(cut.sum())
    print("railway: terrain lowered under the tracks at %d vertices" % n)
    return H


def resample(Q, step=STEP):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q[:, :2], axis=0).T))]
    n = max(int(np.ceil(d[-1] / step)), 1)
    s = np.linspace(0, d[-1], n + 1)
    return np.column_stack([np.interp(s, d, Q[:, k]) for k in range(Q.shape[1])]), s


def under_bridge(road_surface, P, hw):
    """The road faces under a bridge along P (2D union), where its piers must not stand; None
    where there are none."""
    t = getattr(road_surface, "t", np.zeros((0, 3, 3)))
    if not len(t):
        return None
    foot = shapely.LineString(P).buffer(hw + 3.0)
    x0, y0, x1, y1 = foot.bounds
    c = t[:, :, :2].mean(1)
    m = (c[:, 0] > x0 - 10) & (c[:, 0] < x1 + 10) & (c[:, 1] > y0 - 10) & (c[:, 1] < y1 + 10)
    if not m.any():
        return None
    faces = shapely.polygons(t[m][:, :, :2])
    faces = faces[shapely.intersects(faces, foot)]
    return shapely.union_all(faces) if len(faces) else None


def _box(a, b, half_w, z0, z1, nrm):
    """Triangles of a box from a to b (2D), half width half_w across (nrm), heights z0..z1 (arrays of
    2): top and the two long sides and the two ends."""
    A0, A1 = a + nrm * half_w, a - nrm * half_w
    B0, B1 = b + nrm * half_w, b - nrm * half_w
    t = lambda p, z: np.r_[p, z]
    q = []
    q += [t(A0, z1[0]), t(A1, z1[0]), t(B1, z1[1]), t(A0, z1[0]), t(B1, z1[1]), t(B0, z1[1])]      # top
    q += [t(A0, z0[0]), t(A0, z1[0]), t(B0, z1[1]), t(A0, z0[0]), t(B0, z1[1]), t(B0, z0[1])]      # side +
    q += [t(A1, z0[0]), t(B1, z0[1]), t(B1, z1[1]), t(A1, z0[0]), t(B1, z1[1]), t(A1, z1[0])]      # side -
    q += [t(A0, z0[0]), t(A1, z0[0]), t(A1, z1[0]), t(A0, z0[0]), t(A1, z1[0]), t(A0, z1[0])]      # end a
    q += [t(B0, z0[1]), t(B0, z1[1]), t(B1, z1[1]), t(B0, z0[1]), t(B1, z1[1]), t(B1, z0[1])]      # end b
    T = np.array(q).reshape(-1, 3, 3)
    c = np.r_[(a + b) / 2, (z0.mean() + z1.mean()) / 2]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    inward = ((T.mean(1) - c) * n).sum(1) < 0
    T[inward] = T[inward][:, ::-1]
    return T


def build(level_dir, scene, terrain_top, road_surface, ground):
    """terrain_top(x, y): the terrain surface (the higher way a square is split); road_surface: a
    road_mesh.TriSurface of the road top faces; ground(x, y): the bare ground (DTM) for the piers."""
    import bridges
    lines = tracks()
    if not lines:
        print("no railway data (download_tlm.py TLM_EISENBAHN)")
        return {}
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "railway", "main.materials.json"), [
        bng.material("mp_rail_steel", base_color=[0.33, 0.30, 0.28, 1], roughness=0.55, metallic=0.8, ground_type="METAL"),
        bng.material("mp_rail_head", base_color=[0.62, 0.62, 0.63, 1], roughness=0.3, metallic=0.9, ground_type="METAL"),
        bng.material("mp_sleeper", base_color=[0.55, 0.54, 0.51, 1], roughness=0.85, ground_type="CONCRETE"),
        bng.material("mp_ballast", f"{L}/art/shapes/roads/t_gravel_b.png",
                     "/assets/materials/terrain/soil/t_gravel/t_gravel_nm.png", base_color=[0.78, 0.76, 0.74, 1],
                     roughness=0.95, ground_type="GRAVEL"),
        bng.material("mp_rail_deck", base_color=[0.70, 0.69, 0.66, 1], roughness=0.8, ground_type="CONCRETE")])
    tiles = {}
    stats = {"tracks": 0, "km": 0.0, "level_crossing_m": 0.0, "bridge_m": 0.0, "covered_m": 0.0, "sleepers": 0}

    def add(mat, T, uvs=None):
        c = T.mean(1)
        keys = np.floor(c[:, :2] / TILE).astype(int)
        for key in {tuple(k) for k in keys.tolist()}:
            m = (keys[:, 0] == key[0]) & (keys[:, 1] == key[1])
            V = T[m].reshape(-1, 3)
            tiles.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=V[:, :2] + V[:, 2:3] if uvs is None else uvs,
                                                         normals=bng.flat_normals_soup(V))
    for props, Q in lines:
        kind = props["OBJEKTART"]
        gauge, sl_len = GAUGE[kind], SLEEPER_LEN[kind]
        P3, s = resample(Q)
        P = P3[:, :2]
        if len(P) < 3:
            continue
        T = np.gradient(P, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        N = np.column_stack([-T[:, 1], T[:, 0]])
        bridge = props.get("KUNSTBAUTE") == "Bruecke"
        half = sl_len / 2 + BALLAST_EXTRA
        if bridge:
            # swissTLM3D gives the top of the rails on a bridge: the sleepers lie on the deck
            base = gaussian_filter1d(P3[:, 2], 2.0, mode="nearest") - (SLEEPER_H + RAIL_H)
            top, sides, par, piers = bridges.deck_geometry(P, N, base, DECK_HW[kind], ground, "path", "open",
                                                           under_bridge(road_surface, P, DECK_HW[kind]))
            for part in (top, sides, par, piers):
                if len(part):
                    add("mp_rail_deck", part)
            stats["bridge_m"] += s[-1]
            crossing = np.zeros(len(P), bool)
            covered = np.zeros(len(P), bool)
            top_t = base
        else:
            # the bed: on top of the terrain across its whole width, smoothed along the line
            offs = np.linspace(-half + 0.2, half - 0.2, 7)
            Z = np.stack([terrain_top(P[:, 0] + N[:, 0] * o, P[:, 1] + N[:, 1] * o) for o in offs], 1)
            top_t = Z.max(1)
            covered = gaussian_filter1d((P3[:, 2] < Z.min(1) - COVER).astype(float), 2.0, mode="nearest") > 0.2
            bed = gaussian_filter1d(top_t + np.clip(P3[:, 2] - top_t, 0.0, RAISE), SMOOTH / STEP / 2, mode="nearest")
            bed = np.maximum(bed, top_t - 0.02)
            stats["covered_m"] += float(covered.sum() * STEP)
            # level crossings: a road top face within LEVEL_DZ of the bed under the axis
            zr = road_surface.height(P[:, 0], P[:, 1], "near", bed)
            crossing = np.isfinite(zr) & (np.abs(zr - bed) < LEVEL_DZ)
            # at a level crossing the heads of the rails are flush with the road (FLUSH m over it)
            base = np.where(crossing, zr - SLEEPER_H - RAIL_H + FLUSH, bed)
            stats["level_crossing_m"] += float(crossing.sum() * STEP)
        # ballast shoulder and sleepers (not on the road, not on a deck)
        if not bridge:
            # the shoulders down to the terrain: wider where the bed stands over it (an embankment)
            out = half + np.clip(EMBANK * (base - top_t), BALLAST_SLOPE, EMBANK_MAX)
            gL = terrain_top(P[:, 0] + N[:, 0] * out, P[:, 1] + N[:, 1] * out)
            gR = terrain_top(P[:, 0] - N[:, 0] * out, P[:, 1] - N[:, 1] * out)
            q = []
            for i in range(len(P) - 1):
                if crossing[i] or crossing[i + 1] or covered[i] or covered[i + 1]:
                    continue
                Lc0, Lc1 = P[i] + N[i] * half, P[i + 1] + N[i + 1] * half
                Rc0, Rc1 = P[i] - N[i] * half, P[i + 1] - N[i + 1] * half
                Lo0, Lo1 = P[i] + N[i] * out[i], P[i + 1] + N[i + 1] * out[i + 1]
                Ro0, Ro1 = P[i] - N[i] * out[i], P[i + 1] - N[i + 1] * out[i + 1]
                z0, z1 = base[i], base[i + 1]
                l0, l1 = min(gL[i], z0) - 0.2, min(gL[i + 1], z1) - 0.2
                r0, r1 = min(gR[i], z0) - 0.2, min(gR[i + 1], z1) - 0.2
                q += [np.r_[Rc0, z0], np.r_[Lc0, z0], np.r_[Lc1, z1], np.r_[Rc0, z0], np.r_[Lc1, z1], np.r_[Rc1, z1]]
                q += [np.r_[Lc0, z0], np.r_[Lo0, l0], np.r_[Lo1, l1], np.r_[Lc0, z0], np.r_[Lo1, l1], np.r_[Lc1, z1]]
                q += [np.r_[Ro0, r0], np.r_[Rc0, z0], np.r_[Rc1, z1], np.r_[Ro0, r0], np.r_[Rc1, z1], np.r_[Ro1, r1]]
            if q:
                Tq = np.array(q).reshape(-1, 3, 3)
                up = np.cross(Tq[:, 1] - Tq[:, 0], Tq[:, 2] - Tq[:, 0])[:, 2] < 0
                Tq[up] = Tq[up][:, ::-1]
                add("mp_ballast", Tq, uvs=Tq.reshape(-1, 3)[:, :2] / 2.0)
        sl = []
        for si in np.arange(SLEEPER_STEP / 2, s[-1], SLEEPER_STEP):
            i = int(min(np.searchsorted(s, si), len(P) - 1))
            if crossing[i] or covered[i]:
                continue
            c, t_, n_ = P[i], T[i], N[i]
            z = base[i]
            sl.append(_box(c - t_ * SLEEPER_W / 2, c + t_ * SLEEPER_W / 2, sl_len / 2, np.array([z - 0.05] * 2),
                           np.array([z + SLEEPER_H] * 2), n_))
        if sl:
            add("mp_sleeper", np.concatenate(sl))
            stats["sleepers"] += len(sl)
        # rails
        for side in (1, -1):
            off = side * (gauge / 2 + RAIL_W / 2)
            R = P + N * off
            zb = base + SLEEPER_H
            tops, flanks = [], []
            for i in range(len(P) - 1):
                if covered[i] or covered[i + 1]:
                    continue
                n_ = N[i]
                B = _box(R[i], R[i + 1], RAIL_W / 2, np.array([zb[i], zb[i + 1]]), np.array([zb[i], zb[i + 1]]) + RAIL_H, n_)
                nz = np.cross(B[:, 1] - B[:, 0], B[:, 2] - B[:, 0])[:, 2]
                tops.append(B[nz > 0.5 * np.abs(nz).max()] if (nz > 0).any() else B[:0])
                flanks.append(B[~(nz > 0.5 * np.abs(nz).max())])
            if tops:
                add("mp_rail_head", np.concatenate(tops))
                add("mp_rail_steel", np.concatenate(flanks))
        stats["tracks"] += 1
        stats["km"] += (s[-1] - covered.sum() * STEP) / 1000
    g = "MissionGroup/railway"
    for (tx, ty), mb in sorted(tiles.items()):
        rel = f"art/shapes/railway/rail_{tx:+03d}_{ty:+03d}.dae"
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        mb.write_dae(os.path.join(level_dir, rel), name=f"rail_{tx}_{ty}", origin=origin, orient=True)
        scene.add(g, bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=False))
    stats = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()}
    print("railway:", stats, "meshes", len(tiles))
    return stats
