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
import argparse, json, math, os, re, sys, time, zipfile
from scipy.spatial import cKDTree
import optimize_level
import lamps as pl
import poles as pr
import walls as pw
import osm
import road_mesh
from config import LEVEL_NAME

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
        # v2.4: the gravel texture of the roads (surface_textures.py), greyer and darker for the ballast
        bng.material("mp_ballast", f"{L}/art/shapes/roads/t_road_gravel_b.color.png",
                     f"{L}/art/shapes/roads/t_road_gravel_nm.normal.png", base_color=[0.68, 0.69, 0.71, 1],
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


# --------------------------------------------------------------------------------------------------
# The overhead line of the electrified railway (v2.8), in the built level.
#
# Up to v2.7 the tracks of the FLP (Lugano - Ponte Tresa, metre gauge, 1500 V DC) and of the SBB ran without
# their catenary (railway.py: "its masts are not in the data", issue #21). The masts are still not in the open
# data, so a rule places them, on the tracks as the level has them:
# - the axes of the tracks: the sleepers of the railway meshes (the centre of the top of every sleeper box, its
#   length telling the gauge: 1.90 m metre gauge, 2.60 m standard gauge), chained where they lie less than
#   CHAIN m apart, the chains joined across the gaps of the level crossings (no sleepers there) up to JOIN m;
#   electrified: a chain whose points lie, for the most part, within OSM_NEAR m of an OpenStreetMap railway
#   tagged electrified=contact_line (osm.py, the extract of dati/); where OSM has no track within OSM_NEAR m of
#   most of it, by its gauge: metre gauge (the FLP) yes, standard gauge no. The first version took every
#   standard-gauge chain longer than 400 m for the SBB line: they are the yards and spurs of the industrial
#   zones, electrified=no in OSM;
# - a mast every SPAN m (closer in the bends: BENDS), MAST_OFF m from the axis on the outside of the bend (or
#   the side where it can stand: not on a carriageway, in a building or on a wall, not within MAST_CLEAR m of
#   another track's axis; tried again 5 m further on); a steel mast (MAST_W m square) to MAST_TOP m over the rails, a cantilever to over the track;
# - a contact wire CONTACT m over the rails, staggered +-STAGGER m from mast to mast, under a messenger wire from
#   MESSENGER m at the masts down to SAG m over the contact wire mid-span, droppers every DROPPER m; no wires
#   over a gap of more than MAX_SPAN m between two masts;
# - meshes in tiles of CAT_TILE m in MissionGroup/railway: the masts with collision (drawn up to MAST_DRAW m), the
#   wires without (up to WIRE_DRAW m).
# Everything else is copied as it is.
#
# A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish catenary
# --------------------------------------------------------------------------------------------------

CHAIN = 1.5                 # m between neighbouring sleepers of one chain (1 m apart in the level; tracks >= 3.5 m apart)
JOIN = 30.0                 # m, a gap of a chain (a level crossing) joined up to this
OSM_NEAR = 4.0              # m from an OSM railway: the same track
SPAN = 50.0                 # m between two masts on the straight
BENDS = ((150.0, 30.0), (400.0, 40.0))      # radius under which (m) -> span (m)
MAST_OFF = {1.90: 2.6, 2.60: 3.1}           # m from the axis, by sleeper length
MAST_CLEAR = 2.0            # m from the axis of another track
MAST_W = 0.22               # m, side of the mast
MAST_TOP = 7.2              # m over the rails
CONTACT = 5.5               # m, contact wire over the rails
MESSENGER = 6.7             # m, messenger wire at the masts
SAG = 0.35                  # m, messenger over the contact wire at mid-span
STAGGER = 0.2               # m, zig-zag of the contact wire
DROPPER = 9.0               # m between droppers
MAX_SPAN = 75.0             # m, no wire over a longer gap between two masts (the line stops there)
WIRE_R = 0.007              # m, radius of the wires (drawn)
CAT_TILE = 512.0                # m, tiles (as railway.py)
MAST_DRAW, WIRE_DRAW = 800.0, 400.0


def sleepers(zi, lv):
    """Centres (k, 3) of the tops of the sleepers of the railway meshes and their lengths (k,)."""
    C, Ls = [], []
    for o in pl.read_items(zi, f"{lv}/main/MissionGroup/railway/items.level.json"):
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
        W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
        for mat, idx in parts:
            if mat != "mp_sleeper":
                continue
            t = W[idx[:, 0]].reshape(-1, 3, 3)
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            t = t[n[:, 2] > 0.9 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)]
            # the same sleeper twice (overlapping lines of swissTLM3D at the switches): once
            r3 = np.round(t * 1000).astype(np.int64)                   # (k, 3 corners, xyz) in mm
            o3 = np.lexsort((r3[:, :, 2], r3[:, :, 1], r3[:, :, 0]), axis=-1)
            ck = np.take_along_axis(r3, o3[:, :, None], axis=1).reshape(len(t), 9)
            _, first = np.unique(ck, axis=0, return_index=True)
            t = t[np.sort(first)]
            # the two triangles of a top share its diagonal: pair them by their shared corners
            key = np.round(t * 1000).astype(np.int64).reshape(-1, 3)
            _, vid = np.unique(key, axis=0, return_inverse=True)
            vid = vid.reshape(-1, 3)
            E = np.sort(np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]]), 1)
            F = np.tile(np.arange(len(t)), 3)
            ek = E[:, 0] * (vid.max() + 1) + E[:, 1]
            order = np.argsort(ek, kind="stable")
            same = ek[order][1:] == ek[order][:-1]
            a, b = F[order][:-1][same], F[order][1:][same]
            Q = np.concatenate([t[a], t[b]], 1)                        # (k, 6, 3): both triangles
            C.append(Q.mean(1))
            d = np.linalg.norm(Q[:, :, None, :2] - Q[:, None, :, :2], axis=3).max((1, 2))
            Ls.append(d)
    return np.concatenate(C), np.concatenate(Ls)


def chains(P):
    """Index chains along the tracks: the points within CHAIN m of each other, walked end to end."""
    tree = cKDTree(P[:, :2])
    nb = tree.query_ball_point(P[:, :2], CHAIN)
    seen = np.zeros(len(P), bool)
    out = []
    deg = np.array([len(x) - 1 for x in nb])
    for start in list(np.flatnonzero(deg <= 1)) + list(range(len(P))):
        if seen[start]:
            continue
        ch = [start]
        seen[start] = True
        cur = start
        while True:
            nxt = [j for j in nb[cur] if not seen[j]]
            if not nxt:
                break
            if len(ch) > 1:                                         # straight on, not back
                d0 = P[cur, :2] - P[ch[-2], :2]
                nxt.sort(key=lambda j: -np.dot(P[j, :2] - P[cur, :2], d0))
            cur = nxt[0]
            seen[cur] = True
            ch.append(cur)
        if len(ch) >= 5:
            out.append(np.array(ch))
    return out


def osm_contact_line():
    """f(polyline (n, 3)) -> (share of its points every 5 m within OSM_NEAR m of an OSM railway, share of those on
    one tagged electrified=contact_line)."""
    pts, flag = [np.zeros((0, 2))], [np.zeros(0, bool)]
    if osm.available():
        ways, _ = osm.load()
        for w in ways:
            if "railway" not in w["tags"]:
                continue
            xy = np.asarray(w["xy"], np.float64)
            for a, b in zip(xy[:-1], xy[1:]):
                n = max(int(np.hypot(*(b - a)) / 2.0), 1)
                pts.append(a + np.linspace(0, 1, n + 1)[:, None] * (b - a))
                flag.append(np.full(n + 1, w["tags"].get("electrified") == "contact_line"))
    P, F = np.concatenate(pts), np.concatenate(flag)
    tree = cKDTree(P) if len(P) else None

    def f(l):
        if tree is None:
            return 0.0, 0.0
        d, j = tree.query(l[::5, :2], distance_upper_bound=OSM_NEAR)
        m = np.isfinite(d)
        return float(m.mean()), float(F[j[m]].mean()) if m.any() else 0.0
    return f


def join(lines):
    """Polylines (n, 3) joined end to end across gaps up to JOIN m going on the same way."""
    lines = [l for l in lines]
    changed = True
    while changed:
        changed = False
        for i in range(len(lines)):
            for j in range(len(lines)):
                if i == j or lines[i] is None or lines[j] is None:
                    continue
                a, b = lines[i], lines[j]
                for A, B in ((a, b), (a, b[::-1]), (a[::-1], b), (a[::-1], b[::-1])):
                    gap = B[0, :2] - A[-1, :2]
                    g = np.linalg.norm(gap)
                    if g > JOIN or g < 1e-6:
                        continue
                    da = A[-1, :2] - A[-min(6, len(A)), :2]
                    db = B[min(5, len(B) - 1), :2] - B[0, :2]
                    da, db = da / max(np.linalg.norm(da), 1e-9), db / max(np.linalg.norm(db), 1e-9)
                    if da @ (gap / g) > 0.9 and db @ (gap / g) > 0.9:
                        lines[i], lines[j] = np.concatenate([A, B]), None
                        changed = True
                        break
                if changed:
                    break
            if changed:
                break
    return [l for l in lines if l is not None]


def tube(a, b, r=WIRE_R, n=5):
    """Triangles of a tube from a to b."""
    d = b - a
    L = np.linalg.norm(d)
    if L < 1e-6:
        return np.zeros((0, 3))
    d = d / L
    u = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.95 else np.cross(d, [1.0, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(u, d)
    ang = np.linspace(0, 2 * np.pi, n + 1)[:-1]
    ra = a + r * (np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * v)
    rb = ra + (b - a)
    tris = []
    for j in range(n):
        k = (j + 1) % n
        tris += [ra[j], rb[j], rb[k], ra[j], rb[k], ra[k]]
    return np.array(tris)


def polyline_tube(Q, r=WIRE_R):
    return np.concatenate([tube(Q[i], Q[i + 1], r) for i in range(len(Q) - 1)])


def catenary_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    C, Ls = sleepers(zi, lv)
    kind = np.where(Ls < 2.25, 1.90, 2.60)
    print("sleepers: %d (%d metre gauge)" % (len(C), int((kind < 2).sum())), flush=True)
    raw = []
    for k in (1.90, 2.60):
        P = C[kind == k]
        for ch in chains(P):
            raw.append((k, P[ch]))
    lines, chain_rep = [], []
    contact = osm_contact_line()
    for k in (1.90, 2.60):
        for l in join([p for kk, p in raw if kk == k]):
            length = float(np.linalg.norm(np.diff(l[:, :2], axis=0), axis=1).sum())
            matched, share = contact(l)
            on = share >= 0.5 if matched >= 0.5 else k == 1.90
            chain_rep.append({"gauge_sleeper_m": k, "length_m": round(length, 1), "osm_matched": round(matched, 2),
                              "osm_contact_line": round(share, 2), "electrified": bool(on)})
            if on:
                lines.append((k, l, length))
    print("electrified track chains: %d, %.1f km (%s)" % (len(lines), sum(x[2] for x in lines) / 1000,
          ", ".join("%.0f m %s" % (x[2], "FLP" if x[0] < 2 else "SBB") for x in sorted(lines, key=lambda x: -x[2])[:8])), flush=True)

    road = pl.faces(zi, lv, ["roads/surfaces"])
    ROAD = road_mesh.TriSurface(np.concatenate([t for m, t in road.items() if pl.CARRIAGEWAY.match(m)]))
    ROOF = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["buildings"]).values())))
    WALL = road_mesh.TriSurface(np.concatenate(list(pl.faces(zi, lv, ["walls"], keep=lambda sn: "backfill" not in sn).values())))
    axes = cKDTree(C[:, :2])
    rail_top = 0.15                                                  # railway.RAIL_H over the sleeper tops

    masts, wires = [], []                                            # (tile key, triangles)
    n_masts, km = 0, 0.0
    skipped = 0
    why = {"road": 0, "building": 0, "wall": 0, "track": 0}
    spans = []
    for k, l, length in lines:
        # resampled every metre, smoothed
        d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(l[:, :2], axis=0), axis=1))]
        s = np.arange(0.0, d[-1], 1.0)
        A = np.column_stack([gaussian_filter1d(np.interp(s, d, l[:, i]), 2.0, mode="nearest") for i in range(3)])
        T = np.gradient(A[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        R = pr.bend_radius(T)
        turn = np.sign(np.gradient(np.unwrap(np.arctan2(T[:, 1], T[:, 0]))))
        km += d[-1] / 1000
        sup = []                                                     # support points: (index, side)
        i = 0
        while i < len(A):
            span = next((sp for r, sp in BENDS if R[i] < r), SPAN)
            outside = -1.0 if turn[i] > 0 else 1.0                   # right of the track on a left bend...
            placed = None
            for side in (outside, -outside):
                n = side * np.array([T[i][1], -T[i][0]])
                p = A[i, :2] + MAST_OFF[k] * n
                ring = p + 0.3 * np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]])
                if np.isfinite(ROAD.height(ring[:, 0], ring[:, 1], "high")).any():
                    why["road"] += 1
                    continue
                if np.isfinite(ROOF.height([p[0]], [p[1]], "high")[0]):
                    why["building"] += 1
                    continue
                if np.isfinite(WALL.height(ring[:, 0], ring[:, 1], "high")).any():
                    why["wall"] += 1
                    continue
                if axes.query_ball_point(p, MAST_CLEAR, return_length=True) > 0:
                    why["track"] += 1
                    continue
                placed = (side, p)
                break
            if placed is None:
                skipped += 1
                i += 5                                               # try a little further on
                continue
            side, p = placed
            zr = A[i, 2] + rail_top
            foot = np.r_[p, zr - 0.6]
            top = np.r_[p, zr + MAST_TOP]
            n = side * np.array([T[i][1], -T[i][0]])
            stag = STAGGER * (1 if len(sup) % 2 == 0 else -1)
            over = A[i, :2] + stag * n                               # the contact wire's point over the track
            key = (int(math.floor(p[0] / CAT_TILE)), int(math.floor(p[1] / CAT_TILE)))
            mast = pr.props.box(p, np.array([T[i][0], T[i][1]]), MAST_W, MAST_W, foot[2], top[2])
            arm1 = tube(np.r_[p, zr + MESSENGER + 0.1], np.r_[A[i, :2] - 0.3 * n, zr + MESSENGER], 0.03)
            arm2 = tube(np.r_[p, zr + CONTACT + 0.3], np.r_[over, zr + CONTACT], 0.025)
            masts.append((key, "mp_catenary_steel", mast))
            masts.append((key, "mp_catenary_steel", np.concatenate([arm1, arm2])))
            sup.append((i, over, zr))
            n_masts += 1
            i += int(span)
        # the wires from support to support
        for (i0, o0, z0), (i1, o1, z1) in zip(sup[:-1], sup[1:]):
            spans.append(i1 - i0)
            if i1 - i0 > MAX_SPAN:
                continue
            m = (i0 + i1) // 2
            key = (int(math.floor(A[m, 0] / CAT_TILE)), int(math.floor(A[m, 1] / CAT_TILE)))
            f = np.linspace(0, 1, max(int((i1 - i0) / 3), 2) + 1)
            # contact wire: straight from stagger to stagger, over the track axis between
            cw = np.column_stack([o0[0] + f * (o1[0] - o0[0]), o0[1] + f * (o1[1] - o0[1]),
                                  z0 + CONTACT + f * (z1 - z0)])
            idx = np.clip(np.round(i0 + f * (i1 - i0)).astype(int), 0, len(A) - 1)
            cw[:, :2] += A[idx, :2] - (A[i0, :2] + f[:, None] * (A[i1, :2] - A[i0, :2]))   # follow the bend
            mw = cw.copy()
            mw[:, 2] = cw[:, 2] + (MESSENGER - CONTACT) - 4 * (MESSENGER - CONTACT - SAG) * f * (1 - f)
            parts = [polyline_tube(cw), polyline_tube(mw)]
            for fd in np.arange(DROPPER / 2, i1 - i0, DROPPER) / max(i1 - i0, 1):
                j = min(int(round(fd * (len(f) - 1))), len(f) - 1)
                parts.append(tube(cw[j], mw[j], WIRE_R * 0.6, 4))
            wires.append((key, "mp_catenary_wire", np.concatenate(parts)))
    spans = np.array(spans)
    print("masts: %d over %.1f km of track; spans median %.0f m, %d over %.0f m without wires; places skipped: %s"
          % (n_masts, km, np.median(spans), int((spans > MAX_SPAN).sum()), MAX_SPAN, why), flush=True)

    new_files, items = {}, []

    def write(parts, name, draw, collision):
        tiles = {}
        for key, mat, V in parts:
            tiles.setdefault(key, []).append((mat, V))
        for (tx, ty), ps in sorted(tiles.items()):
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * CAT_TILE, (ty + 0.5) * CAT_TILE, 0.0])
            for mat, V in ps:
                mb.add(mat, V, uvs=V[:, :2], normals=bng.flat_normals_soup(V) if mat == "mp_catenary_steel" else None)
            allv = np.concatenate([V for _, V in ps])
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / draw)))
            rel = f"art/shapes/railway/{name}_{tx:+03d}_{ty:+03d}.dae"
            tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"{name}_{os.getpid()}.dae")
            mb.write_dae(tmp, name=name, origin=origin, detail=detail, orient=collision)
            new_files[f"{lv}/{rel}"] = open(tmp, "rb").read()
            os.remove(tmp)
            o = bng.tsstatic(f"/levels/{LEVEL_NAME}/{rel}", origin, collision=collision)
            o["__parent"] = "railway"
            items.append(o)
        return len(tiles)
    nt_m = write(masts, "catenary_masts", MAST_DRAW, True)
    nt_w = write(wires, "catenary_wires", WIRE_DRAW, False)
    mats = [bng.material("mp_catenary_steel", base_color=[0.55, 0.57, 0.58, 1], roughness=0.5, metallic=0.7,
                         ground_type="METAL"),
            bng.material("mp_catenary_wire", base_color=[0.20, 0.17, 0.12, 1], roughness=0.45, metallic=0.8,
                         double_sided=True)]
    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), f"catenary_{os.getpid()}.json")
    bng.write_materials(tmp, mats)
    new_files[f"{lv}/art/shapes/railway/catenary.materials.json"] = open(tmp, "rb").read()
    os.remove(tmp)
    rail_items = f"{lv}/main/MissionGroup/railway/items.level.json"
    new_files[rail_items] = pr.pl_write(pl.read_items(zi, rail_items) + items)

    with zi.writer() as zo:
        for inf in zi.infolist():
            if inf.filename in new_files:
                zo.writestr(inf, new_files.pop(inf.filename), compress_type=inf.compress_type)
            elif re.fullmatch(r"levels/[^/]+/README\.md", inf.filename) and os.path.exists(pw.LEVEL_README):
                zo.writestr(inf, open(pw.LEVEL_README, "rb").read(), compress_type=inf.compress_type)
            else:
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
        now = time.localtime()[:6]
        for name, data in sorted(new_files.items()):
            ni = zipfile.ZipInfo(name, now)
            ni.compress_type, ni.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            zo.writestr(ni, data)
    print("written in %.0f s: %d mast tiles, %d wire tiles" % (time.time() - t0, nt_m, nt_w), flush=True)
    if report:
        res = {"sleepers": int(len(C)), "electrified_km": round(km, 2),
               "chains": chain_rep,
               "masts": n_masts, "skipped_places": skipped, "skipped_why": why,
               "span_m": {"median": float(np.median(spans)), "max": int(spans.max()),
                          "over_max_without_wires": int((spans > MAX_SPAN).sum())},
               "mast_tiles": nt_m, "wire_tiles": nt_w}
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(res, open(report, "w"), indent=1)
    return 0
