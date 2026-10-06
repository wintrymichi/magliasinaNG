"""Paved roads, yards and pavements flush with the ground where nothing marks their edge (v2.8), in a built
level zip.

On v2.7 the outer edges of the paved surfaces (asphalt, setts, cobbles, pavements) stood over the terrain like a
slab with a trench beside it: the build carves the terrain 0.1 m under the lowest road face within one terrain
step (network_mesh.carve_tile), so that it stays under the road whatever the grade. The dirt and gravel tracks
were laid flush in v2.7 (patch_unpaved.py: the terrain raised to them and their edges lowered onto it); here the
terrain is raised to the paved surfaces with patch_unpaved.main, and the surfaces stay as they are:
- the terrain within 1.5 m of a paved top face raised to patch_unpaved.EPS m under its height (fading back to the
  ground at 4.5 m, only where the ground is lower, and not where it lies more than 1 m under the road: an
  embankment or a bridge stays as it is), never over a road face;
- the faces are not lowered (EDGE_DROP 0): lowering the outer edges tilts the last strip of a road, where the
  wheels of a car run, and drive_test.py counted 40-60 % more hard knocks on the roads (tried in the first
  version of this patch);
- the paved paths are left out: the drive test runs its car along them with the wheels on the ground beside
  them, which the raised terrain would change;
- none of it within KEEP_OUT m of a guard rail, a fence, a wall (and the backfill behind it), a building, the
  railway or a bridge parapet: there the step is the real one (an embankment behind a guard rail, a kerb
  against a wall, a plinth). The faces there raise no terrain, and the terrain vertices there stay as they were
  also where a face farther off would raise them (the first version left them to the fade of the faces up to
  4.5 m away: the ground rose against walls, fences and houses, up to 1 m).
The terrain gets the date of the patch; everything else is copied as it is. The report measures the edges
before and after.

Usage: python patch_paved_edges.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, json, os, sys, zipfile
import numpy as np
import optimize_level
import osm_surface
import patch_lamps as pl
import patch_unpaved as pu
import patch_wall_fill as pw
import road_mesh
from config import LEVEL_NAME

PAVED = tuple(m for g in osm_surface.MATS.values() for c, m in g.items()
              if c in ("hard", "sett", "cobble") and not m.startswith("mp_path_")) + ("mp_road_asphalt_fresh", "mp_sidewalk")
EDGE_DROP = 0.0             # m: the faces stay as they are
KEEP_OUT = 2.0              # m around guard rails, fences, walls, buildings, railway, parapets
SAMPLE = 0.5                # m between the samples along the edges of their faces
KEEP_GROUPS = ("roads/guardrails", "roads/fences", "walls", "buildings", "railway")
PARAPET = ("mp_bridge_parapet",)


def outline_samples(t):
    """Points every SAMPLE m along the edges of triangles (k, 3, 2+), and their centres."""
    t = t[:, :, :2]
    pts = [t.mean(1)]
    for a, b in ((0, 1), (1, 2), (2, 0)):
        L = np.linalg.norm(t[:, b] - t[:, a], axis=1)
        k = np.maximum(np.ceil(L / SAMPLE).astype(np.int64), 1)
        rep = np.repeat(np.arange(len(t)), k + 1)
        start = np.repeat(np.cumsum(k + 1) - (k + 1), k + 1)
        f = (np.arange(len(rep)) - start) / k[rep]
        pts.append(t[rep, a] + f[:, None] * (t[rep, b] - t[rep, a]))
    return np.concatenate(pts)


def keep_out_cells(zi, lv):
    """Sorted 1 m cell ids (patch_unpaved.cell_ids) within KEEP_OUT m of what marks a road's edge."""
    ids = []
    for g in KEEP_GROUPS:
        f = f"{lv}/main/MissionGroup/{g}/items.level.json"
        if f not in zi.NameToInfo:
            continue
        for o in pl.read_items(zi, f):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
                continue
            V, _, _, _, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            t = W[np.concatenate([idx[:, 0] for _, idx in parts])].reshape(-1, 3, 3)
            P = outline_samples(t)
            ids.append(np.unique(pu.cell_ids(P[:, 0], P[:, 1])))
    for m, t in pl.faces(zi, lv, ["roads/surfaces"]).items():
        if m in PARAPET:
            P = outline_samples(t)
            ids.append(np.unique(pu.cell_ids(P[:, 0], P[:, 1])))
    base = np.unique(np.concatenate(ids))
    from config import TER_SIZE, TER_SQUARE
    w = int(np.ceil(TER_SIZE * TER_SQUARE))
    r = int(np.ceil(KEEP_OUT))
    offs = [dy * w + dx for dy in range(-r, r + 1) for dx in range(-r, r + 1) if dx * dx + dy * dy <= KEEP_OUT ** 2]
    return np.unique(np.concatenate([base + o for o in offs]))


def measure(zp, keep_out):
    """The outer edges of the paved faces of a zip, out of the keep-out cells: their height over the terrain
    0.3 m beyond them (median, 75th and 90th percentiles, shares over 0.15 and 0.3 m), their length, and the
    terrain over the faces 0.15 and 0.5 m inside them (it should be nowhere)."""
    import unpaved_tour
    zi = zipfile.ZipFile(zp)
    lv = f"levels/{LEVEL_NAME}"
    blk = next(o for o in pl.read_items(zi, f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    z0, maxh = pu.Z0, pu.MAXH
    pu.Z0, pu.MAXH = float(blk["position"][2]), float(blk["maxHeight"])
    _, q, _, _ = pw.read_ter(zi.read(f"{lv}/theTerrain.ter"))
    road = pl.faces(zi, lv, ["roads/surfaces"])
    un = np.concatenate([road[m] for m in PAVED if m in road])
    ALL = road_mesh.TriSurface(np.concatenate(list(road.values())))
    mid, t, n, ln = unpaved_tour.edges(un)
    q_out = mid[:, :2] + 0.10 * n
    m = np.isnan(ALL.height(q_out[:, 0], q_out[:, 1], "low")) & (ln > 0.3) & ~pu.in_cells(keep_out, mid[:, 0], mid[:, 1])
    p = mid[m, :2] + 0.3 * n[m]
    gap = mid[m, 2] - pu.terrain_top(q, p[:, 0], p[:, 1])
    inside = []
    for k in (0.15, 0.5):
        p = mid[m, :2] - k * n[m]
        h = ALL.height(p[:, 0], p[:, 1], "near", mid[m, 2])
        ok = np.isfinite(h)
        inside.append(pu.terrain_top(q, p[ok, 0], p[ok, 1]) - h[ok])
    inside = np.concatenate(inside)
    pu.Z0, pu.MAXH = z0, maxh
    return {"edges_km": round(float(ln[m].sum()) / 1000, 1),
            "over_terrain_m": {k: round(float(np.percentile(gap, v)), 3) for k, v in (("p10", 10), ("median", 50),
                                                                                      ("p75", 75), ("p90", 90))},
            "share_over_0.15m": round(float((gap > 0.15).mean()), 3), "share_over_0.3m": round(float((gap > 0.3).mean()), 3),
            "terrain_over_the_faces_inside": {"share": round(float((inside > 0).mean()), 5),
                                              "max_m": round(float(inside.max()), 3)}}


def raised_vertices(src, dst, keep_out):
    """The terrain vertices dst raised over src: in all, by how much, and in the keep-out (none)."""
    lv = f"levels/{LEVEL_NAME}"
    q0, q1 = (pw.read_ter(zipfile.ZipFile(z).read(f"{lv}/theTerrain.ter"))[1] for z in (src, dst))
    blk = next(o for o in pl.read_items(zipfile.ZipFile(src), f"{lv}/main/MissionGroup/level_objects/terrain/items.level.json")
               if o.get("class") == "TerrainBlock")
    rr, cc = np.nonzero(q1 != q0)
    dz = (q1[rr, cc].astype(np.float64) - q0[rr, cc]) / 65535.0 * float(blk["maxHeight"])
    keep = pu.in_cells(keep_out, pu.TER_X0 + cc * pu.TER_SQUARE, pu.TER_Y0 + rr * pu.TER_SQUARE)
    return {"vertices": len(rr), "median_m": round(float(np.median(dz)), 3) if len(dz) else 0.0,
            "p95_m": round(float(np.percentile(dz, 95)), 3) if len(dz) else 0.0,
            "max_m": round(float(dz.max()), 3) if len(dz) else 0.0, "in_keep_out": int(keep.sum())}


def main(src, dst, report=None):
    zi = zipfile.ZipFile(src)
    lv = f"levels/{LEVEL_NAME}"
    keep = keep_out_cells(zi, lv)
    print("keep-out: %.1f km2 around guard rails, fences, walls, buildings, railway, parapets" % (len(keep) / 1e6),
          flush=True)
    before = measure(src, keep)
    print("before:", before, flush=True)
    pu.main(src, dst, mats=PAVED, edge_drop=EDGE_DROP, keep_out=keep)
    after = measure(dst, keep)
    print("after:", after, flush=True)
    raised = raised_vertices(src, dst, keep)
    print("terrain vertices raised:", raised, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump({"source": os.path.basename(src), "materials": list(PAVED), "edge_drop_m": EDGE_DROP,
                   "terrain_under_faces_m": pu.EPS, "keep_out_m": KEEP_OUT, "keep_out_km2": round(len(keep) / 1e6, 2),
                   "paved_outer_edges_before": before, "paved_outer_edges_after": after,
                   "terrain_vertices_raised": raised}, open(report, "w"), indent=1)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
