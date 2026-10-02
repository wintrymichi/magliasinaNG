"""Lighter level for the game (v2.5): the same geometry in fewer objects, far detail culled.

Measured in BeamNG.drive on a 16 GB PC (v2.4): the level took 215-371 s to load and the game
wanted more memory than the PC had (paging, minutes on the loading screen, 4-8 fps). Partial
levels showed where it went: terrain + forest alone 7.1 GB and 100-140 fps; the meshes of the
roads, guard rails, rails, water and vineyards (4287 shapes of 128 m, about 650 MB in the game's
converted cache) another 3.1 GB, so the game's memory grows with the number of shapes and of
their materials much more than with their vertices.

This step rewrites the pipeline shapes of a built level (zip or folder):
- merged tiles: the 128 m shapes of a group (buildings, walls, road surfaces, ...) become one
  shape per MERGE x MERGE tiles, placed at the same origin: about 1/MERGE^2 as many objects and
  material instances. Collision and decal type stay those of the group.
- welded vertices (bng.weld_corners, also done by every build since v2.5): the meshes were
  triangle soups (3.0 vertices per triangle for walls, buildings, guard rails and rails, 2.0 for
  roads). Positions, triangles and texture coordinates do not change.
- road strips (mesh_strips): the steep faces of the road meshes (skirts, kerbs) along straight
  runs in fewer quads, within mesh_strips.TOL (4 mm).
- detail size: a shape is not drawn when it covers fewer pixels than it needs to be seen at the
  distance of its category (DRAW_DIST); shapes over the whole map are always drawn.
- terrain base textures at TER_BASE px instead of 2048 (as terrain.BASE_TEX in new builds): smooth
  colour noise seen from afar, 13 materials x 5 maps at 2048 px.
- sun shadows up to SHADOW_DIST m instead of 1600.
- the level's README.md is the pipeline's README_livello.md (as build_level.write_info writes it).
Shapes not written by the pipeline (vanilla, other authoring tools) are copied as they are.

Usage: python optimize_level.py <in.zip|level folder> <out.zip|level folder>
"""
import json, os, re, sys, time, zipfile
from multiprocessing import Pool
import numpy as np
import bng
import mesh_strips

MERGE = 3              # tiles per side merged into one shape (128 m tiles -> 384 m)
PIX_K = 1000.0         # pixels per (radius / distance): about a 1440 px high screen at a 70 degree field of view
SHADOW_DIST = 800
TER_BASE = 1024        # px, = terrain.BASE_TEX
# category (folder under art/shapes, or file prefix) -> distance (m) up to which it is drawn
DRAW_DIST = {
    "buildings": 3000, "roads/road_": 3000, "walls/backfill": 2500, "walls/walls_": 1200,
    "walls/rwalls": 1200, "railway": 1500, "water": 2500, "guardrails": 600, "fences": 400,
    "roads/markings": 500, "trees": 2000, "vineyards": 1000,
}
KEEP_DETAIL = ("backdrop", "props")   # whole-map shapes
MAX_TILE_RADIUS = 800.0               # m: a larger shape (one mesh over the whole map) is always drawn
# groups of tile shapes (MissionGroup/<group>/items.level.json) merged MERGE x MERGE
MERGE_GROUPS = ("buildings", "walls", "roads/surfaces", "roads/guardrails", "roads/fences", "railway",
                "level_objects/Water", "level_objects/vegetation/vineyards")
TILE = 128.0
LEVEL_README = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README_livello.md")


def _arr(s, i):
    m = re.search(r'<float_array id="%s" count="\d+">([^<]*)</float_array>' % i, s)
    return np.array(m.group(1).split(), np.float64) if m else None


def parse(s):
    V = _arr(s, "g-pa").reshape(-1, 3)
    N = _arr(s, "g-na").reshape(-1, 3)
    T = _arr(s, "g-ta").reshape(-1, 2)
    C = _arr(s, "g-ca")
    C = C.reshape(-1, 4) if C is not None else None
    parts = []
    for m in re.finditer(r'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', s, re.S):
        nin = m.group(2).count("<input")
        parts.append((m.group(1), np.array(m.group(3).split(), np.int64).reshape(-1, nin)))
    node = re.search(r'<node id="([^"]+)" name="[^"]+" type="NODE"><instance_geometry', s).group(1)
    return V, N, T, C, parts, node


def category_dist(rel):
    """rel: path under art/shapes ('roads/road_+01_+02.dae'); None: keep the detail size."""
    if rel.startswith(KEEP_DETAIL):
        return None
    for k in sorted(DRAW_DIST, key=len, reverse=True):
        if rel.startswith(k):
            return DRAW_DIST[k]
    return None


def is_pipeline(text):
    return "magliaso_pura pipeline" in text[:400] and "<triangles" in text


def optimize_dae(members, rel):
    """members: [(DAE text, offset (3,) of its origin from the new origin)]. Returns (text, stats)."""
    mb = bng.MeshBuilder()
    nv0 = 0
    detail = None
    for text, off in members:
        V, N, UV, C, parts, node = parse(text)
        V = V + np.asarray(off, np.float64)
        nv0 += len(V)
        base, d = re.match(r"(.*)_a(\d+)$", node).groups()
        detail = d if detail is None else detail
        for mat, idx in parts:
            vi, ni, ti = idx[:, 0], idx[:, 1], idx[:, 2]
            ci = idx[:, 3] if idx.shape[1] > 3 and C is not None else None
            Vm, Nm, Um = V[vi], N[ni], UV[ti]
            Cm = C[ci] if ci is not None else None
            if rel.startswith("roads/road_") and Cm is None:
                Tm = np.arange(len(Vm)).reshape(-1, 3)
                fn, area = mesh_strips._face_normals(Vm, Tm)
                steep = (np.abs(fn[:, 2]) < mesh_strips.STEEP_NZ) & (area > 1e-10)
                if steep.sum() >= 16:
                    keep = np.repeat(~steep, 3)
                    if keep.any():
                        mb.add(mat, Vm[keep], uvs=Um[keep], normals=Nm[keep])
                    pieces, _ = mesh_strips.simplify_strips(Vm, Um, Tm[steep])
                    for Vp, Up, Tp in pieces:
                        S = Vp[Tp].reshape(-1, 3)
                        mb.add(mat, S, uvs=Up[Tp].reshape(-1, 2), normals=bng.flat_normals_soup(S))
                    continue
            mb.add(mat, Vm, uvs=Um, normals=Nm, colors=Cm)
    if mb.empty():
        return None, None
    allv = np.concatenate([np.concatenate(p[0]) for p in mb.parts.values()])
    radius = 0.5 * float(np.linalg.norm(np.ptp(allv, axis=0)))
    dist = category_dist(rel)
    if dist is not None and radius <= MAX_TILE_RADIUS:
        detail = max(2, int(round(radius * PIX_K / dist)))
    tmp = os.path.join(os.environ.get("TEMP", "."), f"opt_{os.getpid()}.dae")
    mb.write_dae(tmp, name=base, origin=(0, 0, 0), detail=int(detail))
    with open(tmp, encoding="utf-8") as f:
        out = f.read()
    os.remove(tmp)
    nv1 = sum(len(p[0][0]) for p in mb.parts.values())          # welded by write_dae
    nt = sum(len(p[3][0]) for p in mb.parts.values())
    return out, (nv0, nv1, nt, int(detail), len(members))


def _job(args):
    name, members = args                       # members: [(bytes, offset)]
    rel = name.split("/art/shapes/", 1)[1] if "/art/shapes/" in name else name
    texts = [(m.decode("utf-8"), off) for m, off in members]
    if not all(is_pipeline(t) for t, _ in texts):
        if len(members) > 1:
            raise ValueError(f"{name}: merged tiles must be pipeline shapes")
        return name, members[0][0], None
    try:
        out, st = optimize_dae(texts, rel)
    except Exception as e:                       # leave a shape we cannot read as it was
        if len(members) > 1:
            raise
        print("skip", name, e, flush=True)
        return name, members[0][0], None
    return name, (out.encode("utf-8") if out is not None else members[0][0]), st


# ------------------------------------------------------------------ merging plan
def plan_merge(items_files):
    """items_files: {zip name: text} of the MissionGroup items. Returns (new items texts,
    {new shape entry: [(old shape entry, offset)]}, set of old shape entries merged away)."""
    new_items, jobs, merged = {}, {}, set()
    for fname, text in items_files.items():
        group = fname.split("/MissionGroup/", 1)[1].rsplit("/items.level.json", 1)[0]
        lines = [l for l in text.splitlines() if l.strip()]
        if group not in MERGE_GROUPS:
            continue
        objs = [json.loads(l) for l in lines]
        keep, buckets = [], {}
        for o in objs:
            sn = o.get("shapeName", "")
            ok = (o.get("class") == "TSStatic" and "rotationMatrix" not in o and "scale" not in o
                  and sn.startswith("/levels/") and "/art/shapes/" in sn and sn.endswith(".dae"))
            if not ok:
                keep.append(o)
                continue
            m = re.match(r"(.*/)([a-z_]+?)_[-+]\d+_[-+]\d+\.dae$", sn)
            if not m:
                keep.append(o)
                continue
            x, y = o["position"][0], o["position"][1]
            ix, iy = int(np.floor(x / (TILE * MERGE))), int(np.floor(y / (TILE * MERGE)))
            key = (m.group(1), m.group(2), o.get("collisionType"), o.get("decalType"), o.get("annotation"), ix, iy)
            buckets.setdefault(key, []).append(o)
        for (d, prefix, _, _, _, ix, iy), os_ in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            if len(os_) == 1:
                keep.append(os_[0])
                continue
            p0 = np.min([o["position"] for o in os_], axis=0)
            new_sn = f"{d}{prefix}_m{MERGE}_{ix:+03d}_{iy:+03d}.dae"
            entry = new_sn.lstrip("/")
            members = []
            for o in os_:
                old = o["shapeName"].lstrip("/")
                members.append((old, np.asarray(o["position"], np.float64) - p0))
                merged.add(old)
            jobs[entry] = members
            n = dict(os_[0])
            n["shapeName"] = new_sn
            n["position"] = [float(v) for v in p0]
            keep.append(n)
        new_items[fname] = "\n".join(json.dumps(o, separators=(",", ":")) for o in keep) + "\n"
    return new_items, jobs, merged


# ------------------------------------------------------------------ other files
def patch_sky(text):
    out = []
    for line in text.splitlines():
        if line.strip():
            o = json.loads(line)
            if o.get("class") == "ScatterSky" and o.get("shadowDistance", 0) > SHADOW_DIST:
                o["shadowDistance"] = SHADOW_DIST
            line = json.dumps(o, separators=(",", ":"))
        out.append(line)
    return "\n".join(out) + "\n"


def patch_terrain_json(name, text):
    """baseTexSize of the TerrainBlock (items.level.json) and of the texture set (materials)."""
    if name.endswith("art/terrains/main.materials.json"):
        d = json.loads(text)
        for v in d.values():
            if v.get("class") == "TerrainMaterialTextureSet" and v.get("baseTexSize", [0])[0] > TER_BASE:
                v["baseTexSize"] = [TER_BASE, TER_BASE]
        return json.dumps(d, indent=1)
    out = []
    for line in text.splitlines():
        if line.strip():
            o = json.loads(line)
            if o.get("class") == "TerrainBlock" and o.get("baseTexSize", 0) > TER_BASE:
                o["baseTexSize"] = TER_BASE
            line = json.dumps(o, separators=(",", ":"))
        out.append(line)
    return "\n".join(out) + "\n"


def shrink_png(data, size):
    """A terrain base texture larger than size px, resampled to size x size."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if im.size[0] <= size:
        return data
    buf = io.BytesIO()
    im.resize((size, size), Image.LANCZOS).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def iter_input(src):
    if os.path.isdir(src):
        # a level folder (levels/<name>) is written as in the mod zip: levels/<name>/...
        prefix = f"levels/{os.path.basename(os.path.normpath(src))}/" if os.path.isfile(os.path.join(src, "info.json")) else ""
        for root, _, files in os.walk(src):
            for f in files:
                p = os.path.join(root, f)
                yield prefix + os.path.relpath(p, src).replace("\\", "/"), (lambda p=p: open(p, "rb").read())
    else:
        z = zipfile.ZipFile(src)
        for i in z.infolist():
            if not i.is_dir():
                yield i.filename, (lambda n=i.filename: z.read(n))


def main(src, dst, workers=None):
    t0 = time.time()
    entries = dict(iter_input(src))
    to_zip = dst.lower().endswith(".zip")
    zout = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) if to_zip else None

    def put(name, data):
        if to_zip:
            ctype = zipfile.ZIP_STORED if name.lower().endswith((".jpg", ".png", ".dds")) else zipfile.ZIP_DEFLATED
            zout.writestr(name, data, compress_type=ctype)
        else:
            p = os.path.join(dst, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)

    items = {n: r().decode("utf-8") for n, r in entries.items() if "/MissionGroup/" in n and n.endswith("items.level.json")}
    new_items, merge_jobs, merged = plan_merge(items)
    for n, r in entries.items():
        if n.lower().endswith(".dae"):
            continue
        if n in new_items:
            data = new_items[n].encode("utf-8")
        else:
            data = r()
        if n.endswith("sky_and_sun/items.level.json"):
            data = patch_sky(data.decode("utf-8")).encode("utf-8")
        elif n.endswith(("level_objects/terrain/items.level.json", "art/terrains/main.materials.json")):
            data = patch_terrain_json(n, data.decode("utf-8")).encode("utf-8")
        elif "/art/terrains/" in n and n.lower().endswith(".png"):
            data = shrink_png(data, TER_BASE)
        elif re.fullmatch(r"levels/[^/]+/README\.md", n) and os.path.exists(LEVEL_README):
            data = open(LEVEL_README, "rb").read()
        put(n, data)
    # shape jobs: merged groups, then every other shape on its own
    jobs = [(n, [(m, off) for m, off in members]) for n, members in merge_jobs.items()]
    jobs += [(n, [(n, np.zeros(3))]) for n in entries if n.lower().endswith(".dae") and n not in merged]
    tot = np.zeros(3)
    by_cat = {}
    with Pool(workers or max(1, os.cpu_count() - 2)) as pool:
        k = 0
        for b in range(0, len(jobs), 64):             # in batches: the input is gigabytes of text
            batch = [(n, [(entries[m](), off) for m, off in members]) for n, members in jobs[b:b + 64]]
            for n, out, st in pool.imap_unordered(_job, batch, chunksize=1):
                put(n, out)
                k += 1
                if st is None:
                    continue
                tot += st[:3]
                cat = n.split("/art/shapes/", 1)[-1].split("/")[0]
                c = by_cat.setdefault(cat, [0, 0, 0, 0, set()])
                c[0] += st[0]; c[1] += st[1]; c[2] += 1; c[3] += st[4]; c[4].add(st[3])
            print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    if zout:
        zout.close()
    for cat, (a, b, n, n0, d) in sorted(by_cat.items()):
        print(f"{cat:12} {n0:5} -> {n:4} shapes  vertices {a:>10,} -> {b:>10,} ({100 * b / max(a, 1):.0f}%)  detail {min(d)}-{max(d)}")
    print(f"vertices {int(tot[0]):,} -> {int(tot[1]):,}  triangles {int(tot[2]):,}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
