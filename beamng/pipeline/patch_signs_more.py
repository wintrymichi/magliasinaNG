"""The warning and parking signs nobody mapped in OpenStreetMap (v2.8, issue #21) in a built level zip.

v2.7 (patch_signs.py) put up the signs mapped one by one in OSM and those the regulation OSM records
implies. signs_more.plan() adds, by the Swiss rules: curve warnings before the unexpected sharp curves of
the main roads outside the villages (1.01-1.04), the warnings of the level crossings (1.15 / 1.16), the
hazards OSM records on a road (1.13, 1.23, 1.24, 1.07) and the parking signs at the entrance of the
public car parks (4.17). They are drawn by signs_ch.py and put up as patch_signs.py does: a grey steel
pole beside the carriageway, on the right of the traffic that reads them (else on the left), on free
ground (not on a carriageway, a building or a wall, not within patch_signs.CLEAR m of a pole already
there); one with no room within 2 m is left out (counted). A sign within SPACING m of one the same traffic
already reads goes BACK m further back, so that one plate does not hide the other. Their mesh is a new shape
(art/shapes/props/props_signs_v28.dae, one object in the props/osm group, collision like the other
poles) with its own materials file for the plates v2.7 does not have; everything else is copied as it is.

Usage: python patch_signs_more.py <in.zip> <out.zip> [--report <json>]
"""
import argparse, json, math, os, sys, tempfile, time, zipfile
from collections import Counter
import numpy as np
import bng
import patch_signs as ps
import signs_ch
import signs_more

LEVEL = ps.LEVEL
SHAPE = f"{LEVEL}/art/shapes/props/props_signs_v28.dae"
MATERIALS = f"{LEVEL}/art/shapes/props/signs_ch_v28.materials.json"
SPACING = 10.0            # m: a new sign this close to one the same traffic reads already goes back
BACK = 12.0               # m, by this much (once), so that one plate does not hide the other


def existing_poles(z):
    """[(x, y)] of the poles already in the level: those patch_signs.existing_props knows and the poles of
    the v2.7 signs (props_signs.dae, mp_ch_pole)."""
    P, _, _ = ps.existing_props(z)
    f = f"{LEVEL}/art/shapes/props/props_signs.dae"
    if f in z.namelist():
        V, N, T, C, parts = ps.read_dae(z.read(f))
        for mat, idx in parts:
            if mat == "mp_ch_pole":
                P = np.concatenate([P, np.unique(np.round(V[idx[:, 0]][:, :2] * 4) / 4, axis=0)])
    return P


def main(src, dst, report=None):
    t0 = time.time()
    signs = signs_more.plan()
    print(f"{len(signs)} signs planned: {Counter(s.kind for s in signs)}", flush=True)
    z = zipfile.ZipFile(src)
    old_mats = json.loads(z.read(ps.MATERIALS)) if ps.MATERIALS in z.namelist() else {}
    world = ps.World(z, np.array([[s.x, s.y] for s in signs]))
    from scipy.spatial import cKDTree
    pole_xy = [tuple(p) for p in existing_poles(z)]
    tree = cKDTree(np.array(pole_xy)) if pole_xy else None
    mb = bng.MeshBuilder()
    files, mats, made = {}, {}, set()
    rep = {"placed": Counter(), "left_out": Counter(), "outside": Counter(), "signs": []}

    def material_for(code, val):
        key = ps.slug(code, val)
        name = f"mp_{key}"
        if name in old_mats or key in made:
            return name
        p = signs_ch.plate(code, val)
        col, op = ps.rgba_files(p.img)
        files[f"{ps.SIGN_DIR}/{key}_b.color.png"] = col
        files[f"{ps.SIGN_DIR}/{key}_o.data.png"] = op
        S_ = f"/{ps.SIGN_DIR}"
        for m in (bng.material(name, f"{S_}/{key}_b.color.png", roughness=0.35, alpha_test=100, ground_type="METAL",
                               detail={"opacityMap": f"{S_}/{key}_o.data.png"}),
                  bng.material(name + "_back", base_color=[c / 255 for c in ps.GREY_BACK] + [1], roughness=0.5,
                               metallic=0.5, alpha_test=100, ground_type="METAL",
                               detail={"opacityMap": f"{S_}/{key}_o.data.png"})):
            mats[m["name"]] = m
        made.add(key)
        return name

    if "mp_ch_pole" not in old_mats:
        m = bng.material("mp_ch_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6)
        mats[m["name"]] = m
    seen = []                                              # (x, y, travel direction) of the signs up
    if os.path.exists(signs_more.V27):
        for o in json.load(open(signs_more.V27, encoding="utf-8")).get("signs", []):
            seen.append((o["x"], o["y"], -np.asarray(o["facing"], float)))
    rep["moved_back"] = 0
    for s in signs:
        if any(math.hypot(x - s.x, y - s.y) < SPACING and np.dot(u, s.u) > 0.5 for x, y, u in seen):
            s = s._replace(x=s.x - s.u[0] * BACK, y=s.y - s.u[1] * BACK)
            rep["moved_back"] += 1
        p = np.array([s.x, s.y])
        ring = p + np.array([[r * math.cos(a), r * math.sin(a)] for r in (0, 1, 2, 4, 6)
                             for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)])
        if not world.on_carriageway(ring[:, 0], ring[:, 1]).any():
            rep["outside"][s.kind] += 1                    # a road the map does not build
            continue
        c = ps.place(world, s, tree, pole_xy)
        if c is None:
            rep["left_out"][s.kind] += 1
            continue
        z0 = float(world.ground([c[0]], [c[1]])[0])
        low = ps.LOW_VILLAGE if (s.limit or 50) <= 50 else ps.LOW_ROAD
        nrm = -s.u
        plates = [(code, val, signs_ch.plate(code, val, big=s.big)) for code, val in s.plates]
        plates = [q for q in plates if q[2] is not None]
        if not plates:
            continue
        zb = z0 + low
        layout = []
        for code, val, pl in reversed(plates):                 # stacked from the lowest
            layout.append((code, val, pl, zb + pl.h / 2))
            zb += pl.h + ps.GAP
        top = zb - ps.GAP
        Vt = ps.tube(c, z0 - 0.3, top - 0.02)
        mb.add("mp_ch_pole", Vt, uvs=np.zeros((len(Vt), 2)), normals=bng.flat_normals_soup(Vt))
        for code, val, pl, zc in layout:
            mat = material_for(code, val)
            F, uv = ps.plate_quads(c, nrm, zc, pl.w, pl.h)
            mb.add(mat, F, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
            Bk = F[::-1] - np.r_[nrm * 0.006, 0]
            mb.add(mat + "_back", Bk, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))
        pole_xy.append((float(c[0]), float(c[1])))
        tree = cKDTree(np.array(pole_xy))
        seen.append((float(c[0]), float(c[1]), np.asarray(s.u, float)))
        rep["placed"][s.kind] += 1
        rep["signs"].append({"x": round(float(c[0]), 2), "y": round(float(c[1]), 2), "z": round(z0, 2),
                             "facing": [round(float(nrm[0]), 3), round(float(nrm[1]), 3)],
                             "plates": [[a, b] for a, b in s.plates], "kind": s.kind, "osm": s.osm_id})
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "props_signs_v28.dae")
        mb.write_dae(f, name="props_signs_v28")
        files[SHAPE] = open(f, "rb").read()
    files[MATERIALS] = json.dumps(mats, indent=1).encode("utf-8")
    group_file = f"{LEVEL}/main/MissionGroup/props/osm/items.level.json"
    obj = bng.tsstatic(f"/{SHAPE}", (0, 0, 0), collision=True)
    obj["__parent"] = "osm"
    now = time.localtime()[:6]
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zo:
        for i in z.infolist():
            n = i.filename
            if n in files:
                raise SystemExit(f"{n} is already in {src}: run on a zip without the v2.8 signs")
            data = z.read(i)
            if n == group_file:
                lines = [l for l in data.decode("utf-8").splitlines() if l.strip()]
                data = ("\n".join(lines + [json.dumps(obj, separators=(",", ":"))]) + "\n").encode("utf-8")
                zo.writestr(zipfile.ZipInfo(n, date_time=now), data, compress_type=i.compress_type)
                continue
            zo.writestr(i, data, compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            # PNGs stored (patch_signs.py: a deflated PNG can come out its own size and the game misreads it)
            zo.writestr(zipfile.ZipInfo(n, date_time=now), data,
                        compress_type=zipfile.ZIP_STORED if n.endswith(".png") else zipfile.ZIP_DEFLATED)
    out = {"source": os.path.basename(src), "planned": dict(Counter(s.kind for s in signs)),
           "placed": dict(rep["placed"]), "placed_total": sum(rep["placed"].values()),
           "left_out": dict(rep["left_out"]), "outside_map": dict(rep["outside"]), "moved_back": rep["moved_back"],
           "new_textures": len(made), "signs": rep["signs"]}
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(out, open(report, "w"), indent=1)
    print({k: v for k, v in out.items() if k != "signs"})
    print(f"{dst} ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.report))
