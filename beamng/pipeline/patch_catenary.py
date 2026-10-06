"""The overhead line of the electrified railway (v2.8), in a built level zip.

Up to v2.7 the tracks of the FLP (Lugano - Ponte Tresa, metre gauge, 1500 V DC) and of the SBB ran without
their catenary (railway.py: "its masts are not in the data", issue #21). The masts are still not in the open
data, so a rule places them, on the tracks as the level has them:
- the axes of the tracks: the sleepers of the railway meshes (the centre of the top of every sleeper box, its
  length telling the gauge: 1.90 m metre gauge, 2.60 m standard gauge), chained where they lie less than
  CHAIN m apart, the chains joined across the gaps of the level crossings (no sleepers there) up to JOIN m;
  electrified: a chain whose points lie, for the most part, within OSM_NEAR m of an OpenStreetMap railway
  tagged electrified=contact_line (osm.py, the extract of dati/); where OSM has no track within OSM_NEAR m of
  most of it, by its gauge: metre gauge (the FLP) yes, standard gauge no. The first version took every
  standard-gauge chain longer than 400 m for the SBB line: they are the yards and spurs of the industrial
  zones, electrified=no in OSM;
- a mast every SPAN m (closer in the bends: BENDS), MAST_OFF m from the axis on the outside of the bend (or
  the side where it can stand: not on a carriageway, in a building or on a wall, not within MAST_CLEAR m of
  another track's axis; tried again 5 m further on); a steel mast (MAST_W m square) to MAST_TOP m over the rails, a cantilever to over the track;
- a contact wire CONTACT m over the rails, staggered +-STAGGER m from mast to mast, under a messenger wire from
  MESSENGER m at the masts down to SAG m over the contact wire mid-span, droppers every DROPPER m; no wires
  over a gap of more than MAX_SPAN m between two masts;
- meshes in tiles of TILE m in MissionGroup/railway: the masts with collision (drawn up to MAST_DRAW m), the
  wires without (up to WIRE_DRAW m).
Everything else is copied as it is.

Usage: python patch_catenary.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, json, math, os, re, sys, time, zipfile
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d
import bng
import optimize_level
import patch_lamps as pl
import patch_roadside as pr
import patch_wall_fill as pw
import osm
import road_mesh
from config import LEVEL_NAME

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
TILE = 512.0                # m, tiles (as railway.py)
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


def main(src, dst, report=None):
    t0 = time.time()
    zi = zipfile.ZipFile(src)
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
            key = (int(math.floor(p[0] / TILE)), int(math.floor(p[1] / TILE)))
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
            key = (int(math.floor(A[m, 0] / TILE)), int(math.floor(A[m, 1] / TILE)))
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
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
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

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
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
    print("%s written in %.0f s: %d mast tiles, %d wire tiles" % (dst, time.time() - t0, nt_m, nt_w), flush=True)
    if report:
        res = {"source": os.path.basename(src), "sleepers": int(len(C)), "electrified_km": round(km, 2),
               "chains": chain_rep,
               "masts": n_masts, "skipped_places": skipped, "skipped_why": why,
               "span_m": {"median": float(np.median(spans)), "max": int(spans.max()),
                          "over_max_without_wires": int((spans > MAX_SPAN).sum())},
               "mast_tiles": nt_m, "wire_tiles": nt_w}
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
