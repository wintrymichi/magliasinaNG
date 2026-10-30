"""The level's Collada shapes compiled to BeamNG's binary shape format (.cdae) at build time, so the game never imports
a .dae while the car drives (HANDOFF 2026-10-28, point 3: 13,707 .dae, about 27 GB of XML, imported on first sight,
0.1 s each and up to 46 s: 30 s of stutter in every new zone, or a warm-up of 968 s for one region).

Only the shapes bng.write_dae writes are compiled (one node per detail level '<name>_a<size>' under base00/start01, one
<triangles> list per material, VERTEX/NORMAL/TEXCOORD and optional COLOR inputs, no transforms, metres, Z up): every
shape of the zones is one. Anything else (the trees' imposter billboards, a transform, polylists, skins) raises
Unsupported and stays a .dae for the game to import as before.

The shape written is the one the game writes into its cache for the same .dae (cdae.py: vertices numbered by first use,
winding reversed, v flipped, one primitive per material, tangents by Lengyel), checked against the game's own cache
files (tests/test_dae2cdae.py).

    python dae2cdae.py <level folder> [--workers 4] [--keep-dae]   compile every .dae under it, rewrite the references
    python dae2cdae.py --one in.dae out.cdae
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402


VERSION = 1


class Unsupported(ValueError):
    pass


_NODE = re.compile(rb'<node id="[^"]*" name="([^"]*)"[^>]*>\s*<instance_geometry url="#([^"]+)"[^>]*>(.*?)'
                   rb'</instance_geometry>', re.S)
_BIND = re.compile(rb'<instance_material symbol="([^"]+)" target="#([^"]+)"')
_MAT = re.compile(rb'<material id="([^"]+)" name="([^"]*)"')
_GEOM = re.compile(rb'<geometry id="([^"]+)"[^>]*>(.*?)</geometry>', re.S)
_SRC = re.compile(rb'<source id="([^"]+)">\s*<float_array id="[^"]*" count="(\d+)">([^<]*)</float_array>\s*'
                  rb'<technique_common>\s*<accessor source="[^"]*" count="(\d+)" stride="(\d+)"', re.S)
_VERTS = re.compile(rb'<vertices id="([^"]+)">\s*<input semantic="POSITION" source="#([^"]+)"/>\s*</vertices>')
_TRIS = re.compile(rb'<triangles material="([^"]+)" count="(\d+)">(.*?)<p>([^<]*)</p>\s*</triangles>', re.S)
_INPUT = re.compile(rb'<input semantic="([A-Z]+)" source="#([^"]+)" offset="(\d+)"(?: set="(\d+)")?/>')
_DIGITS = re.compile(rb"^(.*?)(\d+)$")
# anything of these and the shape is not one bng.write_dae writes: left to the game's importer
_REFUSE = (b"bb_autobillboard", b"<polylist", b"<polygons", b"<lines", b"<tristrips", b"<trifans", b"<matrix",
           b"<translate", b"<rotate", b"<scale", b"<controller", b"<instance_node", b"<instance_controller")


def _floats(text, count):
    a = np.fromstring(text, dtype=np.float64, sep=" ") if text.strip() else np.zeros(0)
    if a.size != count:
        raise Unsupported(f"float array of {a.size} values, count says {count}")
    return a


def parse(data):
    """(materials [name], details [(size, mesh dict)], object name) of a bng.write_dae shape."""
    for bad in _REFUSE:
        if bad in data:
            raise Unsupported(bad.decode())
    if b"<up_axis>Z_UP</up_axis>" not in data or not re.search(rb'<unit [^>]*meter="1"', data):
        raise Unsupported("not metres / Z up")
    mat_name = {m.group(1): m.group(2).decode() for m in _MAT.finditer(data)}
    geoms = {m.group(1): m.group(2) for m in _GEOM.finditer(data)}
    nodes = list(_NODE.finditer(data))
    if not nodes or len(nodes) != data.count(b"<instance_geometry"):
        raise Unsupported("no geometry node")
    materials, mindex, details, obj = [], {}, [], None
    for nm in nodes:
        dm = _DIGITS.match(nm.group(1))
        if not dm:
            raise Unsupported("node name without a detail size")
        base = dm.group(1).decode()
        if obj is None:
            obj = base
        elif base != obj:
            raise Unsupported("several objects")
        binds = {s: t for s, t in _BIND.findall(nm.group(3))}
        geo = geoms.get(nm.group(2))
        if geo is None:
            raise Unsupported("missing geometry")
        details.append((int(dm.group(2)), _mesh(geo, binds, mat_name, materials, mindex)))
    if len({s for s, _ in details}) != len(details):
        raise Unsupported("two meshes of one detail size")
    return materials, details, obj


def _mesh(geo, binds, mat_name, materials, mindex):
    src = {}
    for m in _SRC.finditer(geo):
        stride = int(m.group(5))
        a = _floats(m.group(3), int(m.group(2)))
        if a.size != int(m.group(4)) * stride:
            raise Unsupported("accessor count")
        src[m.group(1)] = a.reshape(-1, stride)
    vm = _VERTS.search(geo)
    if not vm:
        raise Unsupported("vertices")
    vid, pos_src = vm.group(1), vm.group(2)
    tris = list(_TRIS.finditer(geo))
    if not tris or len(tris) != geo.count(b"<triangles"):
        raise Unsupported("triangles")
    kinds = None
    corner_rows, tri_mat = [], []
    for tm in tris:
        inputs = _INPUT.findall(tm.group(3))
        if len(inputs) != tm.group(3).count(b"<input"):
            raise Unsupported("input")
        sem = {}
        for s, sid, off, st in inputs:
            if s in sem or (st and st != b"0"):
                raise Unsupported("second set of " + s.decode())
            if s == b"VERTEX" and sid != vid:
                raise Unsupported("VERTEX input of other vertices")
            sem[s] = (pos_src if s == b"VERTEX" else sid, int(off))
        if b"VERTEX" not in sem or sem[b"VERTEX"][0] != pos_src or set(sem) - {b"VERTEX", b"NORMAL", b"TEXCOORD",
                                                                               b"COLOR"}:
            raise Unsupported("inputs " + ",".join(s.decode() for s in sem))
        if kinds is None:
            kinds = sem
        elif {k: v[0] for k, v in kinds.items()} != {k: v[0] for k, v in sem.items()}:
            raise Unsupported("triangle lists read different sources")
        stride = max(o for _, o in sem.values()) + 1
        n = int(tm.group(2))
        idx = np.fromstring(tm.group(4), dtype=np.int64, sep=" ") if tm.group(4).strip() else np.zeros(0, np.int64)
        if idx.size != n * 3 * stride:
            raise Unsupported("index count")
        idx = idx.reshape(-1, stride)
        corner_rows.append(np.stack([idx[:, sem[k][1]] for k in (b"VERTEX", b"NORMAL", b"TEXCOORD", b"COLOR")
                                     if k in sem], 1))
        target = binds.get(tm.group(1), tm.group(1))
        name = mat_name.get(target)
        if name is None:
            raise Unsupported("unbound material")
        if name not in mindex:
            mindex[name] = len(materials)
            materials.append(name)
        tri_mat.append(np.full(n, mindex[name], np.int64))
    order = [k for k in (b"VERTEX", b"NORMAL", b"TEXCOORD", b"COLOR") if k in kinds]
    for k in order:
        if kinds[k][0] not in src:
            raise Unsupported("source " + kinds[k][0].decode())
    corners = np.concatenate(corner_rows)
    for j, k in enumerate(order):
        if corners[:, j].min() < 0 or corners[:, j].max() >= len(src[kinds[k][0]]):
            raise Unsupported("index out of range")
    # one vertex per distinct corner tuple (the importer's vertex tuples); the writer numbers them by first use
    uniq, inv = np.unique(corners, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    col = {k: uniq[:, j] for j, k in enumerate(order)}
    mesh = {"positions": src[kinds[b"VERTEX"][0]][col[b"VERTEX"]][:, :3],
            "tris": inv.reshape(-1, 3), "tri_materials": np.concatenate(tri_mat)}
    if b"NORMAL" in col:
        mesh["normals"] = src[kinds[b"NORMAL"][0]][col[b"NORMAL"]][:, :3]
    mesh["uvs"] = src[kinds[b"TEXCOORD"][0]][col[b"TEXCOORD"]][:, :2] if b"TEXCOORD" in col else None
    if b"COLOR" in col:
        c = src[kinds[b"COLOR"][0]][col[b"COLOR"]]
        if c.shape[1] == 3:
            c = np.concatenate([c, np.ones((len(c), 1))], 1)
        # truncated, as the game does (its cache files of the same .dae: floor, never round)
        mesh["colors"] = np.clip(np.floor(c[:, :4] * 255), 0, 255).astype(np.uint8)
    return mesh


def compile_bytes(data):
    materials, details, obj = parse(data)
    return cdae.encode_details(details, materials, object_name=obj)


def convert(src, dst):
    """src (.dae) compiled to dst (.cdae). Returns the bytes written; raises Unsupported (nothing written)."""
    with open(src, "rb") as f:
        out = compile_bytes(f.read())
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, dst)
    return len(out)


def _job(args):
    src, dst, keep = args
    try:
        n = convert(src, dst)
    except Unsupported as e:
        return src, None, str(e)
    if not keep:
        os.remove(src)
    return src, n, None


def compilable(path):
    """Would compile_level compile this .dae? (the same test: parse succeeds and no file of the game's own beside it)"""
    if _has_companions(path):
        return False
    try:
        with open(path, "rb") as f:
            parse(f.read())
    except (OSError, Unsupported):
        return False
    return True


def forest_shapes(level_dir):
    """The shapeFile of every forest item type (art/forest/managedItemData.json), lower case: left as .dae (the forest
    and its imposters were tested with .dae only)."""
    out = set()
    for dp, _, fs in os.walk(level_dir):
        for f in fs:
            if f == "managedItemData.json":
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    out |= {str(v.get("shapeFile", "")).lower() for v in json.load(fh).values() if isinstance(v, dict)}
    return out


def _has_companions(path):
    """A shape with files of the game's beside it (x.dae.imposter.dds, x.dae.asset.json: the prebaked far trees) is
    found by those names: compiled, the game would look for x.cdae.imposter.dds and bake the imposters itself."""
    d, f = os.path.split(path)
    try:
        return any(n.startswith(f + ".") for n in os.listdir(d or "."))
    except OSError:
        return False


def compile_level(level_dir, mod_prefix, workers=4, keep_dae=False, rewrite=True, log=print):
    """Every .dae under level_dir compiled beside it (x.dae -> x.cdae, the .dae removed unless keep_dae), and, with
    rewrite, every reference to a compiled one ('<mod_prefix>/<rel path>.dae' in the level's .json files) changed to the
    .cdae. mod_prefix: the path of level_dir in the game ('/levels/ticino'). Returns (stats, {game path of the .dae:
    game path of the .cdae}, [game paths of the .dae left as they were])."""
    t0 = time.time()
    jobs, kept = [], []
    size_dae = 0
    game = lambda p: f"{mod_prefix}/{os.path.relpath(p, level_dir).replace(os.sep, '/')}"
    forest = forest_shapes(level_dir)
    for dp, _, fs in os.walk(level_dir):
        for f in sorted(fs):
            if f.lower().endswith(".dae"):
                p = os.path.join(dp, f)
                size_dae += os.path.getsize(p)
                if _has_companions(p) or game(p).lower() in forest:
                    kept.append(p)
                else:
                    jobs.append((p, p[:-4] + ".cdae", keep_dae))
    done, refused, size_c = {}, {"forest shapes / files of the game beside it": len(kept)} if kept else {}, 0
    with ProcessPoolExecutor(max(1, workers)) as ex:
        for k, (src, n, err) in enumerate(ex.map(_job, jobs, chunksize=8)):
            if n is None:
                refused[err] = refused.get(err, 0) + 1
                kept.append(src)
            else:
                size_c += n
                done[game(src)] = game(src)[:-4] + ".cdae"
            if (k + 1) % 2000 == 0:
                log(f"compiled {k + 1} of {len(jobs)} shapes in {time.time() - t0:.0f} s")
    nref = rewrite_refs(level_dir, done) if rewrite else 0
    stats = {"compiled": len(done), "kept": len(kept), "refused": refused, "bytes_dae": size_dae,
             "bytes_cdae": size_c, "references": nref, "seconds": round(time.time() - t0)}
    log("shapes compiled to .cdae:", json.dumps(stats))
    return stats, done, sorted(game(p) for p in kept)


_REF = re.compile(r'"(/levels/[^"]+?\.[dD][aA][eE])"')


def rewrite_refs(level_dir, done):
    """Every "<path>.dae" string in the level's .json files that names a compiled shape -> its .cdae. done: {game path
    of the .dae: game path of the .cdae}, or a function of the game path giving the new path or None. Returns the
    number of references changed."""
    if not done:
        return 0
    if callable(done):
        new_path = done
    else:
        low = {k.lower(): v for k, v in done.items()}
        new_path = lambda p: low.get(p.lower())
    n = 0
    for dp, _, fs in os.walk(level_dir):
        for f in fs:
            if not f.endswith(".json"):
                continue
            p = os.path.join(dp, f)
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
            if ".dae" not in text.lower():
                continue
            k = [0]

            def sub(m):
                v = new_path(m.group(1))
                if v is None:
                    return m.group(0)
                k[0] += 1
                return f'"{v}"'
            new = _REF.sub(sub, text)
            if k[0]:
                os.remove(p)                  # a new file: the source may be a hard link (cp -al)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(new)
                n += k[0]
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("level", nargs="?")
    ap.add_argument("--prefix", default="/levels/ticino")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep-dae", action="store_true")
    ap.add_argument("--one", nargs=2, metavar=("DAE", "CDAE"))
    a = ap.parse_args()
    if a.one:
        print(convert(*a.one), "bytes")
        return
    compile_level(a.level, a.prefix, a.workers, a.keep_dae)


if __name__ == "__main__":
    main()
