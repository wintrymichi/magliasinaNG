"""dae2cdae.py checked two ways.

    python tests/test_dae2cdae.py <folder of .dae>              each .dae compiled and read back: every triangle of
                                                                  every detail level with the same corners, normals,
                                                                  uvs, colours and material as the Collada file
    python tests/test_dae2cdae.py --golden <folder>             pairs x.dae + x.cdae the GAME wrote for it (its
                                                                  temp cache): our file against the game's

The golden check compares what is drawn, not the bytes: per detail level its size and triangle count, and the
triangles (positions, uvs, normals, colours, tangents, material name) as sets, since the order of the triangles in a
primitive does not change the picture.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cdae  # noqa: E402
import dae2cdae  # noqa: E402


def drawn(shape):
    """[(size, {material: array (k, 3 corners, 3 pos + 2 uv + 3 normal + 4 colour + 4 tangent)})] of a decoded shape,
    the triangles of each primitive in the winding stored (the engine's)."""
    det = np.frombuffer(shape["details"][2], dtype=np.dtype([
        ("name", "<i4"), ("ss", "<i4"), ("od", "<i4"), ("size", "<f4"), ("ae", "<f4"), ("me", "<f4"),
        ("poly", "<i4"), ("bb", "<i4", 4), ("pa", "<f4"), ("ip", "<u4")]))
    objs = np.frombuffer(shape["objects"][2], "<i4").reshape(-1, 6)
    out = []
    for d in det:
        if d["size"] < 0:
            continue
        mats = {}
        for o in objs:
            if d["od"] >= o[1]:
                continue
            m = shape["meshes"][o[2] + d["od"]]
            if m["type"] == 4:
                continue
            a = cdae.mesh_arrays(m)
            n = len(a["verts"])
            col = np.frombuffer(m["colors"][2], np.uint8).reshape(-1, 4).astype(np.float64) if m["colors"][0] \
                else np.full((n, 4), 255.0)
            row = np.concatenate([a["verts"], a["tverts"], a["norms"], col, a["tangents"]], 1).astype(np.float64)
            for start, count, mi in a["primitives"]:
                name = shape["materials"][mi & cdae.PRIM_MATERIAL_MASK]["name"]
                I = a["indices"][start:start + count].reshape(-1, 3)
                mats.setdefault(name, []).append(row[I])
        out.append((float(d["size"]), {k: np.concatenate(v) for k, v in mats.items()}))
    return out


def canon(T, cols):
    """Triangles as sorted tuples of rounded corner rows, each triangle rotated to start at its smallest corner."""
    R = np.round(T[:, :, cols], 4)
    keys = []
    for t in R:
        rows = [tuple(r) for r in t]
        k = rows.index(min(rows))
        keys.append(tuple(rows[k:] + rows[:k]))
    return sorted(keys)


def self_check(paths):
    bad = 0
    for p in paths:
        data = open(p, "rb").read()
        try:
            mats, details, _ = dae2cdae.parse(data)
        except dae2cdae.Unsupported as e:
            print("refused", os.path.basename(p), e)
            continue
        got = drawn(cdae.decode(dae2cdae.compile_bytes(data)))
        want = sorted(details, key=lambda d: -d[0])
        ok = len(got) == len(want)
        for (gs, gm), (ws, wd) in zip(got, want):
            ok &= gs == ws
            P, T = np.asarray(wd["positions"]), np.asarray(wd["tris"])
            for k, name in enumerate(mats):
                sel = wd["tri_materials"] == k
                if not sel.any():
                    ok &= name not in gm
                    continue
                n = len(P)
                uv = np.float32(wd["uvs"])
                uv = np.stack([uv[:, 0], np.float32(1.0) - uv[:, 1]], 1).astype(np.float64)   # flipped in float32
                col = wd["colors"].astype(np.float64) if "colors" in wd else np.full((n, 4), 255.0)
                row = np.concatenate([P, uv, wd["normals"], col], 1)[T[sel][:, ::-1]]      # engine winding
                row = np.float32(row).astype(np.float64)
                ok &= name in gm and canon(row, slice(0, 12)) == canon(gm[name], slice(0, 12))
        print(os.path.basename(p), "ok" if ok else "DIFFERS")
        bad += not ok
    return bad


def golden(folder):
    bad = 0
    for dp, _, fs in os.walk(folder):
        for f in sorted(fs):
            if not f.endswith(".dae") or not os.path.exists(os.path.join(dp, f[:-4] + ".cdae")):
                continue
            p = os.path.join(dp, f)
            g = cdae.read(p[:-4] + ".cdae")
            o = cdae.decode(dae2cdae.compile_bytes(open(p, "rb").read()))
            gd, od = drawn(g), drawn(o)
            msg = []
            if [s for s, _ in gd] != [s for s, _ in od]:
                msg.append(f"detail sizes game {[s for s, _ in gd]} ours {[s for s, _ in od]}")
            for (s, gm), (_, om) in zip(gd, od):
                if sorted(gm) != sorted(om):
                    msg.append(f"materials {sorted(gm)} vs {sorted(om)}")
                    continue
                for name in gm:
                    a, b = gm[name], om[name]
                    if len(a) != len(b):
                        msg.append(f"{s:g} {name}: {len(a)} vs {len(b)} triangles")
                        continue
                    for label, cols, tol in (("pos/uv", slice(0, 5), 1e-4), ("normal", slice(5, 8), 2e-3),
                                             ("colour", slice(8, 12), 0.5), ("tangent", slice(12, 16), 2e-2)):
                        ca, cb = canon(a, cols), canon(b, cols)
                        diff = np.abs(np.array(ca) - np.array(cb)).max() if ca else 0.0
                        if diff > tol:
                            msg.append(f"{s:g} {name} {label} differs by {diff:.4g}")
            nv = (sum(m["verts"][0] for m in g["meshes"] if m["type"] == 0),
                  sum(m["verts"][0] for m in o["meshes"] if m["type"] == 0))
            print(os.path.relpath(p, folder), "ok" if not msg else "DIFFERS", f"verts game/ours {nv[0]}/{nv[1]}",
                  "; ".join(msg[:4]))
            bad += bool(msg)
    return bad


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--golden":
        sys.exit(1 if golden(sys.argv[2]) else 0)
    paths = []
    for root in sys.argv[1:]:
        for dp, _, fs in os.walk(root):
            paths += [os.path.join(dp, f) for f in sorted(fs) if f.endswith(".dae")]
    sys.exit(1 if self_check(paths) else 0)


if __name__ == "__main__":
    main()
