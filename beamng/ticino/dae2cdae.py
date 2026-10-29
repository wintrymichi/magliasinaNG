"""Our own Collada files (bng.write_dae: one node per detail level, named <name><size>, triangles with POSITION /
NORMAL / TEXCOORD / COLOR inputs at their own offsets) to the engine's binary shape (.cdae, cdae.py), so the game
loads a shape without parsing XML or compiling it in its own cache first.

    python dae2cdae.py <in.dae> [<out.cdae>]        one file
    python dae2cdae.py --tree <dir>                 every .dae under dir (writes <name>.cdae beside it)
"""
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdae  # noqa: E402

_ATTR = re.compile(r'(\w+)="([^"]*)"')


def _attrs(tag):
    return dict(_ATTR.findall(tag))


def _floats(text):
    return np.array(text.split(), np.float64) if text.strip() else np.zeros(0)


def parse(s):
    """{geometry id: {name, materials [(symbol, triangles idx (k, ninp*3) int, offsets {sem: (off, src)})], sources}}
    plus the visual scene's [(node name, geometry id, {symbol: material name})] in file order."""
    mats = {}
    for m in re.finditer(r'<material ([^>]*)>', s):
        a = _attrs(m.group(1))
        mats[a["id"]] = a.get("name", a["id"])
    geoms = {}
    for g in re.finditer(r'<geometry ([^>]*)>(.*?)</geometry>', s, re.S):
        ga = _attrs(g.group(1))
        body = g.group(2)
        src = {}
        for so in re.finditer(r'<source id="([^"]+)">\s*<float_array[^>]*>([^<]*)</float_array>.*?stride="(\d+)"', body, re.S):
            src[so.group(1)] = _floats(so.group(2)).reshape(-1, int(so.group(3)))
        verts = {}
        for v in re.finditer(r'<vertices id="([^"]+)">(.*?)</vertices>', body, re.S):
            p = re.search(r'semantic="POSITION" source="#([^"]+)"', v.group(2))
            verts[v.group(1)] = p.group(1)
        prims = []
        for t in re.finditer(r'<triangles ([^>]*)>(.*?)</triangles>', body, re.S):
            ta = _attrs(t.group(1))
            offs = {}
            for i in re.finditer(r'<input ([^/]*)/>', t.group(2)):
                a = _attrs(i.group(1))
                sid = a["source"][1:]
                sem = a["semantic"]
                if sem == "VERTEX":
                    sem, sid = "POSITION", verts[sid]
                if sem == "TEXCOORD" and int(a.get("set", 0)) > 0:
                    sem = "TEXCOORD2"
                offs[sem] = (int(a["offset"]), sid)
            n = max(o for o, _ in offs.values()) + 1
            p = np.array(re.search(r'<p>([^<]*)</p>', t.group(2)).group(1).split(), np.int64).reshape(-1, n)
            prims.append((ta.get("material", ""), p, offs))
        geoms[ga["id"]] = dict(name=ga.get("name", ga["id"]), prims=prims, src=src)
    nodes = []
    for n in re.finditer(r'<node id="[^"]*" name="([^"]+)"[^>]*>\s*<instance_geometry url="#([^"]+)"[^>]*>(.*?)</instance_geometry>', s, re.S):
        bind = {}
        for im in re.finditer(r'<instance_material symbol="([^"]+)" target="#([^"]+)"', n.group(3)):
            bind[im.group(1)] = mats.get(im.group(2), im.group(2))
        nodes.append((n.group(1), n.group(2), bind))
    return geoms, nodes


def mesh(g, bind, matlist):
    """One geometry as cdae.encode's arrays: one vertex per distinct corner (position, normal, uv, colour)."""
    corners, tm = [], []
    for sym, p, offs in g["prims"]:
        name = bind.get(sym, sym)
        if name not in matlist:
            matlist.append(name)
        corners.append((p, offs))
        tm.append(np.full(len(p) // 3, matlist.index(name), np.int64))
    sems = ["POSITION", "NORMAL", "TEXCOORD", "TEXCOORD2", "COLOR"]
    have = [s for s in sems if all(s in o for _, o in corners)]
    keys = np.concatenate([p[:, [o[s][0] for s in have]] for p, o in corners])
    uniq, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    rank = np.empty(len(first), np.int64)             # vertices in the order the file first uses them, as the engine
    rank[np.argsort(first, kind="stable")] = np.arange(len(first))
    uniq = uniq[np.argsort(first, kind="stable")]
    inv = rank[inv.reshape(-1)]
    srcid = {s: corners[0][1][s][1] for s in have}
    out = dict(tris=inv.reshape(-1, 3), tri_materials=np.concatenate(tm))
    col = dict(zip(have, range(len(have))))
    out["positions"] = g["src"][srcid["POSITION"]][uniq[:, col["POSITION"]]]
    if "NORMAL" in col:
        out["normals"] = g["src"][srcid["NORMAL"]][uniq[:, col["NORMAL"]]]
    if "TEXCOORD" in col:
        out["uvs"] = g["src"][srcid["TEXCOORD"]][uniq[:, col["TEXCOORD"]]][:, :2]
    if "TEXCOORD2" in col:
        out["uvs2"] = g["src"][srcid["TEXCOORD2"]][uniq[:, col["TEXCOORD2"]]][:, :2]
    if "COLOR" in col:
        c = g["src"][srcid["COLOR"]][uniq[:, col["COLOR"]]]
        if c.shape[1] == 3:
            c = np.concatenate([c, np.ones((len(c), 1))], 1)
        out["colors"] = np.clip(np.floor(c * 255 + COLOR_ROUND), 0, 255).astype(np.uint8)
    return out


COLOR_ROUND = 0.0
_SIZE = re.compile(r'^(.*?)(-?\d+)$')


def convert(text):
    geoms, nodes = parse(text)
    details = []
    matlist = []
    for name, gid, bind in nodes:
        m = _SIZE.match(name)
        base, size = (m.group(1), int(m.group(2))) if m else (name, 0)
        details.append((size, base, mesh(geoms[gid], bind, matlist)))
    details.sort(key=lambda d: -d[0])
    if len({d[1] for d in details}) > 1:
        raise ValueError("more than one object: %s" % sorted({d[1] for d in details}))
    size0, base, top = details[0]
    lods = [(d[0], d[2]) for d in details[1:]]
    return cdae.encode(top["positions"], top["tris"], normals=top.get("normals"), uvs=top.get("uvs"),
                       uvs2=top.get("uvs2"), material=matlist, tri_materials=top["tri_materials"],
                       colors=top.get("colors"), object_name=base, lods=lods or None,
                       detail_sizes=[float(d[0]) for d in details])


def main():
    if sys.argv[1] == "--tree":
        n = b0 = b1 = 0
        t0 = time.time()
        for d, _, fs in os.walk(sys.argv[2]):
            for f in fs:
                if f.endswith(".dae"):
                    p = os.path.join(d, f)
                    data = convert(open(p, encoding="utf-8").read())
                    open(p[:-4] + ".cdae", "wb").write(data)
                    n += 1
                    b0 += os.path.getsize(p)
                    b1 += len(data)
        print("%d files, dae %.1f MB -> cdae %.1f MB, %.1f s" % (n, b0 / 1e6, b1 / 1e6, time.time() - t0))
        return
    data = convert(open(sys.argv[1], encoding="utf-8").read())
    out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1][:-4] + ".cdae"
    open(out, "wb").write(data)


if __name__ == "__main__":
    main()
