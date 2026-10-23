"""Patch of the v3.1 nightly zip (2026-10-23), without building it again: the keep-right poles of the traffic islands
get the black and yellow sleeve of the Swiss island posts at their foot, and the short white beacon with its yellow
reflector that stood beside each pole goes (islands.py does this in the build since v3.1; no island of the area has a
white beacon, the street photos show the banded sleeve). Only the islands' shapes, the sleeve's texture and the
materials change.

Run: python patch_island_bollards.py <folder that holds levels/>
"""
import json, os, re, sys, tempfile
import numpy as np
import bng
import islands
import optimize_level
from config import LEVEL_NAME
from markings_net import read_items

SHAPE = re.compile(r"art/shapes/roads/islands_[-+]\d+_[-+]\d+\.dae$")
GONE = ("mp_island_beacon", "mp_island_reflector")
POLE = "mp_island_pole"


def poles(W):
    """[(centre xy, unit direction of a side, island top)] of the pole boxes in the world triangles W (k, 3, 3) of
    one shape: boxes 0.06 m wide from 0.3 m under the island's top."""
    P = W.reshape(-1, 3)
    key = np.round(P[:, :2] / 0.25).astype(np.int64)
    out = []
    seen = set()
    for k in np.unique(key, axis=0):
        kk = tuple(k)
        if kk in seen:
            continue
        m = (np.abs(key - k) <= 1).all(1)                    # the pole's corners, all within 0.06 m
        for a in np.unique(key[m], axis=0):
            seen.add(tuple(a))
        Q = P[m]
        c = Q[:, :2].mean(0)
        if np.hypot(*(Q[:, :2] - c).T).max() > 0.1:
            continue
        e = Q[1, :2] - Q[0, :2] if np.hypot(*(Q[1, :2] - Q[0, :2])) > 0.01 else Q[2, :2] - Q[0, :2]
        corners = Q[:, :2] - c
        d = corners[np.argmax(np.hypot(*corners.T))]
        d = np.array([d[0] - d[1], d[0] + d[1]])           # a corner's direction turned 45 deg: a side's
        out.append((c, d / max(np.hypot(*d), 1e-9), float(Q[:, 2].min()) + 0.3))
    return out


def main(root):
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    items = read_items(zi, f"{lv}/main/MissionGroup/roads/islands/items.level.json")
    new, n_poles, n_gone = {}, 0, 0
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if not SHAPE.search(sn) or sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        V, N, UV, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        mb = bng.MeshBuilder()
        pole_w = []
        for mat, idx in parts:
            if mat in GONE:
                n_gone += len(idx) // 3
                continue
            if mat == POLE:
                pole_w.append((V[idx[:, 0]] + pos).reshape(-1, 3, 3))
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[idx[:, 0]] + pos, uvs=UV[idx[:, 2]], normals=N[idx[:, 1]],
                   tris=np.arange(len(idx)).reshape(-1, 3), colors=col)
        if pole_w:
            for c, d, zt in poles(np.concatenate(pole_w)):
                T, uv = islands.bollard(c, d, zt)
                Vt = T.reshape(-1, 3)
                mb.add("mp_island_bollard", Vt, uvs=uv, normals=bng.flat_normals_soup(Vt))
                n_poles += 1
        m = re.match(r"(.*)_a(\d+)$", node)
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "s.dae")
            if m:
                mb.write_dae(p, name=m.group(1), origin=pos, detail=int(m.group(2)))
            else:
                mb.write_dae(p, name=node, origin=pos)
            new[sn] = open(p, "rb").read()
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    for k in GONE:
        mats.pop(k, None)
    for mm in islands.materials():
        if mm["name"] == "mp_island_bollard":
            mats[mm["name"]] = mm
    new[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    new[f"{islands.TEX_DIR}/{islands.BOLLARD_TEX}"] = islands.bollard_png()
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename in new:
                continue
            zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(new.items()):
            zo.writestr(n, data)
    print(f"island bollards: {n_poles} poles sleeved, {n_gone} beacon triangles removed", flush=True)
    return n_poles, n_gone


if __name__ == "__main__":
    main(sys.argv[1])
