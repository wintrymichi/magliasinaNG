"""cdae.py against shapes the game itself compiled (fixtures from BeamNG.Earth, server/tests/fixtures, MIT): the
writer must give the engine's file for the same Collada geometry.

    python tests/test_cdae.py
"""
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import cdae  # noqa: E402

NS = "{http://www.collada.org/2005/11/COLLADASchema}"


def load(path):
    root = ET.parse(path).getroot()
    arrs = {fa.get("id"): np.array(fa.text.split(), float) for fa in root.iter(NS + "float_array")}
    tri = root.find(f".//{NS}triangles")
    ninp = len(tri.findall(NS + "input"))
    T = np.array(tri.find(NS + "p").text.split(), int).reshape(-1, ninp)[:, 0].reshape(-1, 3)
    nrm = arrs.get("g0-nrm-a")
    return (arrs["g0-pos-a"].reshape(-1, 3), T, arrs["g0-uv-a"].reshape(-1, 2),
            None if nrm is None else nrm.reshape(-1, 3), root.find(f".//{NS}material").get("name"))


def canon(T):
    k = np.argmin(T, 1)
    return sorted(tuple(np.roll(t, -s)) for t, s in zip(T.tolist(), k))


def main():
    bad = 0
    for name, exact_tangents in (("lodtest_16_0", True), ("far_7_0_0_3", False)):
        P, T, UV, N, mat = load(os.path.join(HERE, "fixtures", name + ".dae"))
        ours = cdae.encode(P, T, normals=N, uvs=UV, material=mat)
        gold = open(os.path.join(HERE, "fixtures", name + ".cdae"), "rb").read()
        o, g = cdae.decode(ours), cdae.decode(gold)
        oa, ga = cdae.mesh_arrays(o["meshes"][0]), cdae.mesh_arrays(g["meshes"][0])
        ok = (len(ours) == len(gold) and o["header"] == g["header"] and o["names"] == g["names"]
              and np.array_equal(oa["verts"], ga["verts"]) and np.array_equal(oa["tverts"], ga["tverts"])
              and np.abs(oa["norms"] - ga["norms"]).max() < 2e-7
              and canon(oa["indices"].reshape(-1, 3)) == canon(ga["indices"].reshape(-1, 3))
              and (not exact_tangents or np.abs(oa["tangents"] - ga["tangents"]).max() < 1e-6))
        print(name, "ok" if ok else "DIFFERS")
        bad += not ok
    c = cdae.decode(cdae.encode(P, T, collision_only=True))
    ok = c["names"] == ["Colmesh", "detail2", "Collision-1"] and c["meshes"][0]["type"] == 4
    print("collision only", "ok" if ok else "DIFFERS")
    bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
