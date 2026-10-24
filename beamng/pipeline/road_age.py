"""Older and newer asphalt, joints, patches and drains on the carriageways (v3.1, "asfalto meno uniforme"), for road_wear.py.

Up to v3.0.40 every carriageway of the map was the same asphalt with the same wear: tracks, light and dark
blotches, a cracked stretch now and then and a dusty edge, laid by rule along every road. A real road is
paved in campaigns: one stretch resurfaced three years ago, black and even, the next one twenty years old,
grey, ravelled and cracked, with a sealed joint where one meets the other; trenches of the pipes patched in
rectangles; a manhole on the axis, a gully at the kerb where the water runs to. Nothing of this is added
where the photos do not show it (cracks everywhere would make the map more detailed and less true):
- age: the 10 cm SWISSIMAGE straightened along every AI road (asphalt_survey.py, dati/asphalt_ortho.npz): per
  station and per half of the road the median luminance of the asphalt (not the shadows, the paint, the cars),
  against the median of all the roads in the same 1 km tile of the photo (one flight, one exposure). A road
  is split where that level jumps (binary segmentation, pieces at least MIN_SEG m), and a piece clearly darker
  is new asphalt (NEW_R), one clearly lighter is old (OLD_R); either half on its own (a lane resurfaced, a
  trench along it). New asphalt: a dark, even overlay over the carriageway (mp_wear_age_new), no cracks and
  no light blotches on it, a sealed joint across the road where it ends (mp_wear_joint) and along the axis
  where only one half is new. Old asphalt: a lighter, ravelled overlay (mp_wear_age_old), cracked stretches
  OLD_CRACKS times as often, a crumbled edge where no kerb holds it (mp_wear_frayed, drawn here).
  The contrast is kept low: the darker base material of the 2022 resurfacing read as black patches with
  sharp edges (build_level.road_materials).
- patches: compact darker spots of the same photo, rectangular in the road's frame (cut with a saw), 2 to
  60 m2, not where the road is new, not the size and darkness of a car: a rectangle of patch asphalt
  (mp_wear_patch) with sealed seams.
- drains: Mapillary's manholes and gullies (dati/asphalt_drains.json, from its photos), snapped onto the asphalt
  (a manhole) or to the nearest edge (a gully); and a gully at every low point of a kerbed edge, where the water
  of the road has to go (the photos cannot see every one, the slope of the road says where they are).
- transitions: a sealed joint along the edge where the carriageway meets a yard, a drive or setts at its own
  height (road_wear.outer_edges took these edges out of the dusty bands).
"""
import json, os
import numpy as np
from PIL import Image
from scipy.ndimage import label, median_filter, uniform_filter1d
from scipy.spatial import cKDTree
import bng
from config import LEVEL_NAME, local_to_lv95
from bld_textures import aniso_noise, noise, to8

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
ORTHO = os.path.join(DATI, "asphalt_ortho.npz")
DRAINS = os.path.join(DATI, "asphalt_drains.json")
NEW, OLD = 1, -1
INNER = 0.4                 # m inside the AI road's half width: the cells of the photo taken for the asphalt
AXIS = 0.3                  # m about the axis left out (the centre line)
SHADOW = 0.45               # of the asphalt of the photo's tile: darker cells are shadows or dark cars (new asphalt
                            # was 0.6 of the old in the 2024 photo, the shadows of the trees 0.15-0.4)
BRIGHT = 1.45               # lighter: paint, light cars, concrete
SHADOW_GROW = 2             # cells: the half shadow round a shadow is left out too (it reads as new asphalt)
BLUE = 25                   # blue minus red over the road's median: a shadow
VALID = 0.5                 # share of valid cells for a station to count
SMOOTH = 9                  # stations (m): running median of the level along the road
MIN_SEG = 30                # stations (m): the shortest piece of one age
SPLIT = 0.06                # least jump of the level between two pieces
NEW_R = 0.88                # level of a piece against its tile: new asphalt below
OLD_R = 1.10                # old above
OLD_MAX = 1.35              # lighter still: concrete, gravel, a square of setts, not old asphalt
HALF_DR = 0.06              # a half this close to the other's threshold takes its age
HALF_MIN = 40               # stations (m): the shortest stretch where one half alone is new or old
MIN_COVER = 0.6             # share of a piece's stations measured: less, no age
MATCH = 2.5                 # m: a station of a band takes the age of the survey's nearest station within this
OLD_CRACKS = 2.5            # times as many cracked stretches on old asphalt
PATCH_DARK = 0.86           # a cell this much darker than its stretch: a patch
PATCH_CELLS = (6, 120)      # cells (0.5 m2) of a patch
PATCH_FILL = 0.55           # of its bounding rectangle
PATCH_MIN = 0.55            # darker than this: not asphalt (a hole of the photo, a dark car, a shadow)
PATCH_RING = 0.95           # the road round a patch at least this bright against its stretch
CAR = ((3.5, 5.6), (1.4, 2.4), 0.72)   # m along, across, darkness: a parked car, not a patch
JOINT_W = 0.14              # m, width of a sealed joint
SEAM_W = 0.09               # m, of the joint with a yard, a drive or setts
DRAIN_SAG = 0.08            # m: a low point of a kerbed edge this far under the edge 10 m either side gets a gully
DRAIN_GAP = 4.0             # m: the least distance between two drains
GRATE = 0.5                 # m, side of a gully's grate
COVER = 0.62                # m, diameter of a manhole cover
SNAP = 4.0                  # m: a drain of Mapillary farther from the asphalt is left out
LIFT = {"mp_wear_age_new": 0.004, "mp_wear_age_old": 0.004, "mp_wear_patch": 0.005, "mp_wear_frayed": 0.011,
        "mp_wear_joint": 0.013, "mp_wear_seam": 0.013, "mp_wear_drain_grate": 0.014, "mp_wear_drain_cover": 0.014}
PER_M = {"mp_wear_age_new": 24.0, "mp_wear_age_old": 24.0, "mp_wear_patch": 6.0, "mp_wear_frayed": 12.0,
         "mp_wear_joint": 20.0, "mp_wear_seam": 20.0}  # m of road per repeat of the texture for a band 1 m wide (road_wear.LAYER)
TEX = {"frayed": (128, 1024), "new": (256, 1024), "old": (256, 1024), "patch": (256, 512), "joint": (32, 512), "grate": (128, 128),
       "cover": (128, 128)}


# ------------------------------------------------------------------ the survey
def segments(r, ok):
    """Pieces [(a, b)] of a profile r (n,) (NaN where not measured), split where its level jumps."""
    out = []

    def split(a, b):
        x = r[a:b]
        m = np.isfinite(x)
        if b - a < 2 * MIN_SEG or m.sum() < 2 * MIN_SEG * MIN_COVER:
            out.append((a, b))
            return
        xv = np.where(m, x, 0.0)
        cs, cn = np.cumsum(xv), np.cumsum(m)
        best, at = 0.0, None
        for k in range(MIN_SEG, b - a - MIN_SEG + 1):
            n1, n2 = cn[k - 1], cn[-1] - cn[k - 1]
            if n1 < MIN_SEG * MIN_COVER or n2 < MIN_SEG * MIN_COVER:
                continue
            d = abs(cs[k - 1] / n1 - (cs[-1] - cs[k - 1]) / n2)
            score = d * np.sqrt(n1 * n2 / (n1 + n2))
            if d >= SPLIT and score > best:
                best, at = score, k
        if at is None:
            out.append((a, b))
            return
        split(a, a + at)
        split(a + at, b)
    split(0, len(r))
    return out


class Survey:
    """The asphalt of the photos along the AI roads: age per station and half (NEW, OLD, 0), the patches."""

    def __init__(self, roads, path=ORTHO):
        self.ok = os.path.exists(path)
        self.patches = []
        if not self.ok:
            return
        d = np.load(path)
        names, start, xy = d["names"], d["start"], d["xy"].astype(np.float64)
        L, BR = d["L"].astype(np.float32), d["BR"].astype(np.float32)
        cell, cols = float(d["cell"]), L.shape[1]
        off = (np.arange(cols) - (cols - 1) / 2) * cell
        half = {r.get("name"): float(np.median(np.asarray(r["nodes"])[:, 3])) / 2 for r in roads}
        n = len(xy)
        lev = np.full((2, n), np.nan)                                 # left, right: median luminance
        self.T = np.zeros((n, 2))
        sides = []
        # the asphalt of every 1 km tile of the photo (one flight, one exposure): the median of the cells of its
        # roads that are neither shadows nor paint, against which every station is measured
        E, N = local_to_lv95(xy[:, 0], xy[:, 1])
        tile = np.floor(E / 1000).astype(np.int64) * 10000 + np.floor(N / 1000).astype(np.int64)
        core = np.abs(off) <= 1.5
        g = float(np.median(L[:, core][L[:, core] > 0]))
        tref = {}
        for t in np.unique(tile):
            v = L[tile == t][:, core]
            v = v[(v > SHADOW * g) & (v < BRIGHT * g)]
            tref[t] = float(np.median(v)) if len(v) > 200 else g
        R = np.array([tref[t] for t in tile], np.float32)
        from scipy.ndimage import binary_dilation
        for i, nm in enumerate(names):
            a, b = int(start[i]), int(start[i + 1])
            h = half.get(str(nm))
            if h is None or b - a < 3:
                continue
            Tg = np.gradient(xy[a:b], axis=0)
            self.T[a:b] = Tg / np.maximum(np.linalg.norm(Tg, axis=1, keepdims=True), 1e-9)
            inner = np.abs(off) <= h - INNER
            Lr, Br = L[a:b], BR[a:b]
            vals = Lr[:, inner & (np.abs(off) > AXIS)]
            vals = vals[vals > 0]
            if not len(vals):
                continue
            Rr = R[a:b, None]
            ref, bref = float(np.median(vals)), float(np.median(Br[:, inner]))
            shade = binary_dilation((Lr < SHADOW * Rr) | (Br > bref + BLUE), np.ones((3, 3)), SHADOW_GROW)
            valid = ~shade & (Lr < BRIGHT * Rr)
            for si, side in enumerate((inner & (off > AXIS), inner & (off < -AXIS))):
                if not side.any():
                    continue
                v = np.where(valid[:, side], Lr[:, side], np.nan)
                cnt = np.isfinite(v).sum(1)
                with np.errstate(all="ignore"):
                    m = np.nanmedian(v, axis=1)
                lev[si, a:b] = np.where(cnt >= VALID * side.sum(), m, np.nan)
            sides.append((i, a, b, inner, ref, bref, valid))
        rel = lev / R[None, :]
        self.age = np.zeros((2, n), np.int8)
        self.level = np.full((2, n), np.nan)
        for i, a, b, inner, ref, bref, valid in sides:
            for si in range(2):
                r = rel[si, a:b]
                if not np.isfinite(r).any():
                    continue
                rs = np.where(np.isfinite(r), median_filter(np.where(np.isfinite(r), r, np.nanmedian(r)), SMOOTH,
                                                            mode="nearest"), np.nan)
                for p, q in segments(rs, np.isfinite(rs)):
                    x = r[p:q]
                    if np.isfinite(x).mean() < MIN_COVER:
                        continue
                    lv = float(np.nanmedian(x))
                    self.level[si, a + p:a + q] = lv
                    self.age[si, a + p:a + q] = NEW if lv < NEW_R else OLD if OLD_R < lv < OLD_MAX else 0
            self._halves(a, b)
            self._patches(str(names[i]), xy[a:b], self.T[a:b], L[a:b], BR[a:b], off, inner, ref, bref, valid,
                          self.age[:, a:b], float(np.median(R[a:b])))
        self.xy = xy
        self.tree = cKDTree(xy)
        s = self.stats = {"stations": int(n), "new_m": int((self.age == NEW).sum()), "old_m": int((self.age == OLD).sum()),
                          "patches": len(self.patches)}
        print("road age: survey", s, flush=True)

    def _halves(self, a, b):
        """One age for both halves where the photo does not tell them apart: a half next to a new one that is
        not measured (a shadow) or nearly as dark is new too (a road is mostly resurfaced whole); a stretch
        where only one half is new or old stays one only when longer than HALF_MIN m (a lane, a trench)."""
        A, Lv = self.age[:, a:b], self.level[:, a:b]
        for x, y in ((0, 1), (1, 0)):
            m = (A[x] == NEW) & (A[y] != NEW) & (~np.isfinite(Lv[y]) | (Lv[y] < NEW_R + HALF_DR))
            A[y, m] = NEW
            m = (A[x] == OLD) & (A[y] == 0) & (~np.isfinite(Lv[y]) | (Lv[y] > OLD_R - HALF_DR))
            A[y, m] = OLD
        diff = A[0] != A[1]
        lab, k = label(diff)
        for j in range(1, k + 1):
            m = lab == j
            if m.sum() < HALF_MIN:                                    # too short for a lane of its own: the
                both = A[:, m]                                        # age of both, the newer one winning
                v = np.where((both == NEW).any(0), NEW, np.where((both == OLD).all(0), OLD, 0))
                A[:, m] = v

    def _patches(self, name, xy, T, L, BR, off, inner, ref, bref, valid, age, R0):
        """Compact darker rectangles of one road: [(centre xy, tangent, along m, across m)]."""
        Nl = np.column_stack([-T[:, 1], T[:, 0]])
        bg = np.full(L.shape, np.nan, np.float32)
        for side in (off > 0, off <= 0):
            v = np.where(valid & inner[None, :] & side[None, :], L, np.nan)
            with np.errstate(all="ignore"):
                m = np.nanmedian(v, axis=1)
            m = np.where(np.isfinite(m), m, ref)
            bg[:, side] = median_filter(m, 25, mode="nearest")[:, None]
        rel = L / np.maximum(bg, 1)
        newst = (age == NEW).any(0)
        dark = (rel < PATCH_DARK) & valid & inner[None, :] & ~newst[:, None]
        lab, k = label(dark, structure=np.ones((3, 3)))
        if not k:
            return
        cell = float(abs(off[1] - off[0]))
        for j, sl in enumerate(__import__("scipy.ndimage", fromlist=["find_objects"]).find_objects(lab), 1):
            if sl is None:
                continue
            m = lab[sl] == j
            cnt = int(m.sum())
            if not PATCH_CELLS[0] <= cnt <= PATCH_CELLS[1] or cnt / m.size < PATCH_FILL:
                continue
            along, across = (sl[0].stop - sl[0].start) * 1.0, (sl[1].stop - sl[1].start) * cell
            darkness = float(np.mean(rel[sl][m]))
            if CAR[0][0] <= along <= CAR[0][1] and CAR[1][0] <= across <= CAR[1][1] and darkness < CAR[2]:
                continue
            if along < 1.0 or across < 0.75 or darkness < PATCH_MIN:
                continue
            # a patch has road round it: the ring of cells about its rectangle on the asphalt, out of the shadows
            # and of the road's own brightness (not the edge of the road, a shadow's fringe, a car's shadow)
            r0, r1 = max(sl[0].start - 2, 0), min(sl[0].stop + 2, len(L))
            c0, c1 = sl[1].start - 1, sl[1].stop + 1
            if c0 < 0 or c1 > len(off) or not inner[c0:c1].all():
                continue
            ring = np.ones((r1 - r0, c1 - c0), bool)
            ring[sl[0].start - r0:sl[0].stop - r0, 1:-1] = False
            vr, rr = valid[r0:r1, c0:c1][ring], rel[r0:r1, c0:c1][ring]
            if vr.mean() < 0.85 or np.median(rr[vr]) < PATCH_RING:
                continue
            if (L[r0:r1, c0:c1][ring] > BRIGHT * R0).any():              # a light car beside its own shadow
                continue
            i0, i1 = sl[0].start, sl[0].stop - 1
            ic = (i0 + i1) // 2
            oc = 0.5 * (off[sl[1].start] + off[sl[1].stop - 1])
            c = xy[ic] + Nl[ic] * oc
            self.patches.append({"road": name, "xy": c, "t": T[ic], "along": along, "across": across + 0.2,
                                 "dark": darkness})

    def query(self, P, T, bound=MATCH):
        """Age (2, n) int8 (left, right as seen along the tangents T) of the points P (n, 2) of a band."""
        out = np.zeros((2, len(P)), np.int8)
        if not self.ok or not len(P):
            return out
        d, j = self.tree.query(P, distance_upper_bound=bound)
        hit = np.isfinite(d)
        jj = np.where(hit, j, 0)
        same = (self.T[jj] * T).sum(1) >= 0
        out[0] = np.where(hit, np.where(same, self.age[0, jj], self.age[1, jj]), 0)
        out[1] = np.where(hit, np.where(same, self.age[1, jj], self.age[0, jj]), 0)
        return out


# ------------------------------------------------------------------ drains of the photos
def mapillary_drains():
    if not os.path.exists(DRAINS):
        return []
    return json.load(open(DRAINS))


# ------------------------------------------------------------------ textures and materials
def _rgba_save(dst, name, col, a):
    Image.fromarray(to8(col)).save(os.path.join(dst, f"t_{name}_b.color.png"))
    Image.fromarray(to8(a)).save(os.path.join(dst, f"t_{name}_o.data.png"))


def textures(dst):
    """The textures of the layers here (all drawn here, nothing of the game): colour and a separate opacity map
    (the game draws a colour map's own alpha opaque, road_wear.textures)."""
    rng = np.random.default_rng(57)
    # new asphalt: dark, even, a little mottled along the road (the roller's passes); u across, v along
    w, h = TEX["new"]
    lo = aniso_noise(h, w, h / 24, w / 3, rng)
    fine = noise(h, w, 0.7, rng)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.20, 0.20, 0.21])
    col *= (1 + 0.05 * lo + 0.04 * fine)[..., None]
    _rgba_save(dst, "age_new", col, np.clip(0.42 + 0.05 * lo + 0.03 * fine, 0, 1))
    # old asphalt: lighter, browner, the fine aggregate showing (speckle), patchy
    w, h = TEX["old"]
    lo = aniso_noise(h, w, h / 16, w / 4, rng)
    speck = noise(h, w, 0.6, rng)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.60, 0.58, 0.54])
    col *= (1 + 0.10 * speck + 0.04 * lo)[..., None]
    _rgba_save(dst, "age_old", col, np.clip(0.20 + 0.06 * lo + 0.10 * np.clip(speck, 0, None), 0, 0.45))
    # patch: newer and darker than the road round it, the roller marks across it
    w, h = TEX["patch"]
    lo = aniso_noise(h, w, h / 10, w / 6, rng)
    fine = noise(h, w, 0.7, rng)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.18, 0.18, 0.19])
    col *= (1 + 0.06 * lo + 0.05 * fine)[..., None]
    _rgba_save(dst, "patch", col, np.clip(0.46 + 0.06 * lo, 0, 1))
    # sealed joint: a strip of bitumen poured over the cut, its sides ragged where it was smeared
    w, h = TEX["joint"]
    u = (np.arange(w) + 0.5) / w
    rag = 0.28 + 0.035 * aniso_noise(h, 2, h / 20, 0.5, rng)          # sawn straight, the bitumen a little uneven
    left, right = rag[:, :1], 1 - rag[:, 1:2]
    a = np.clip((u[None, :] - left) / 0.08, 0, 1) * np.clip((right - u[None, :]) / 0.08, 0, 1)
    a *= np.clip(0.8 + 0.15 * aniso_noise(h, w, h / 30, w, rng), 0, 1)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.09, 0.09, 0.10]) * (1 + 0.1 * noise(h, w, 0.8, rng))[..., None]
    _rgba_save(dst, "joint", col, a * 0.75)
    _rgba_save(dst, "seam", col * 1.6, a * 0.45)                     # the joint with a yard, a drive, setts: fainter
    # crumbled edge: broken asphalt and grit at u = 0, the broken line ragged towards the road (drawn here: Italy's
    # t_thin_damaged_edge was never used by the level, so its place in 0.40 is not known, game_paths.py)
    w, h = TEX["frayed"]
    u = (np.arange(w) + 0.5) / w
    lim = 0.40 + 0.20 * aniso_noise(h, 1, h / 50, 0.5, rng) + 0.05 * noise(h, w, 1.5, rng)
    a = np.clip((lim - u[None, :]) / 0.06, 0, 1) * np.clip(0.75 + 0.25 * aniso_noise(h, w, h / 30, w / 4, rng), 0, 1)
    col = np.zeros((h, w, 3), np.float32) + np.array([0.47, 0.45, 0.41])
    col *= (1 + 0.14 * noise(h, w, 0.7, rng))[..., None]
    _rgba_save(dst, "frayed", col, a * 0.8)
    # gully: a cast iron grate in its frame, bars across the flow, dirt in the slots
    n = TEX["grate"][0]
    yy, xx = (np.mgrid[0:n, 0:n] + 0.5) / n
    frame = (np.minimum(np.minimum(xx, 1 - xx), np.minimum(yy, 1 - yy)) < 0.09)
    bars = ((xx * 9) % 1 < 0.45) | frame
    col = np.where(bars[..., None], np.array([0.20, 0.19, 0.18]), np.array([0.05, 0.045, 0.04]))
    col = col * (1 + 0.12 * noise(n, n, 1.0, rng))[..., None]
    col[frame] *= 1.15
    _rgba_save(dst, "drain_grate", col, np.ones((n, n)) * 0.97)
    # manhole cover: a round lid with a raised pattern, the ring of its frame
    r = np.hypot(xx - 0.5, yy - 0.5) * 2
    ang = np.arctan2(yy - 0.5, xx - 0.5)
    ring = (r > 0.86) & (r < 1.0)
    rib = (np.cos(ang * 16) > 0.6) & (r < 0.82) & (r > 0.25) | ((r % 0.2) < 0.04) & (r < 0.82)
    col = np.where(rib[..., None], np.array([0.27, 0.26, 0.25]), np.array([0.17, 0.165, 0.16]))
    col = np.where(ring[..., None], np.array([0.30, 0.29, 0.28]), col)
    col = col * (1 + 0.1 * noise(n, n, 1.0, rng))[..., None]
    a = np.clip((1.0 - r) / 0.03, 0, 1) * 0.97
    _rgba_save(dst, "drain_cover", col, a)
    return [f"t_{k}_{s}" for k in ("age_new", "age_old", "patch", "joint", "seam", "frayed", "drain_grate", "drain_cover")
            for s in ("b.color.png", "o.data.png")]


def materials(overlay):
    t = f"/levels/{LEVEL_NAME}/art/shapes/roads"
    out = []
    for name, tex, rough in (("mp_wear_age_new", "age_new", 0.80), ("mp_wear_age_old", "age_old", 0.95),
                             ("mp_wear_patch", "patch", 0.80), ("mp_wear_joint", "joint", 0.55),
                             ("mp_wear_seam", "seam", 0.70), ("mp_wear_frayed", "frayed", 0.95),
                             ("mp_wear_drain_grate", "drain_grate", 0.60), ("mp_wear_drain_cover", "drain_cover", 0.55)):
        m = bng.material(name, f"{t}/t_{tex}_b.color.png", roughness=rough, extra=overlay)
        m["Stages"][0]["opacityMap"] = f"{t}/t_{tex}_o.data.png"
        out.append(m)
    return out


# ------------------------------------------------------------------ small pieces of mesh
def quad(c, t, along, across, z, kind="square"):
    """Two triangles (2, 3, 3) of a rectangle centred on c (2,) along the unit tangent t, and their uvs."""
    n = np.array([-t[1], t[0]])
    P = [c - t * along / 2 - n * across / 2, c + t * along / 2 - n * across / 2,
         c + t * along / 2 + n * across / 2, c - t * along / 2 + n * across / 2]
    V = np.array([[p[0], p[1], zz] for p, zz in zip(P, z)])
    uv = np.array([[0, 0], [0, 1], [1, 1], [1, 0]], float)
    return np.stack([V[[0, 1, 2]], V[[0, 2, 3]]]), np.stack([uv[[0, 1, 2]], uv[[0, 2, 3]]])
