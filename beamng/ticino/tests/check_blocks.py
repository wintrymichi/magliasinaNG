"""Checks the blocks of a cut level against the level they were cut from: every window put together from the blocks
(blocks.window_ter, the same arithmetic as ter.lua) must hold the source terrain's own samples, heights and layers,
wherever the window lies on the source terrain.

    python tests/check_blocks.py --zone zones/malcantone.json --src <unpacked release> --out <blocks.py output>
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import blocks  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=12, help="random windows besides the corners")
    a = ap.parse_args()
    zone = blocks.Zone(json.load(open(a.zone)))
    src = os.path.join(a.src, "levels", zone.cfg["source_level"])
    dst = os.path.join(a.out, "levels", blocks.LEVEL)
    scene = blocks.scene_files(src)
    tb = next(o for objs in scene.values() for o in objs if o.get("class") == "TerrainBlock")
    n, H, L, mats = blocks.read_ter(src, tb)
    cfg = json.load(open(os.path.join(dst, "stream.json")))
    nb = cfg["blocksPerSide"]
    rng = np.random.default_rng(1)
    C, W = zone.C, zone.W
    nc = n // C
    spots = [(0, 0), (nc - W // C, nc - W // C), (-3, 5), (nc - 5, -2)]
    spots += [tuple(int(v) for v in rng.integers(-2, nc - W // C + 3, 2)) for _ in range(a.n)]
    bad = 0
    for wcx, wcy in spots:
        wx, wy = wcx * C, wcy * C
        data = blocks.window_ter(zone, os.path.join(dst, "blocks", "terrain"), nb, wx, wy, mats)
        ver, size = struct.unpack("<BI", data[:5])
        assert ver == 9 and size == W
        h = np.frombuffer(data, "<u2", W * W, 5).reshape(W, W)
        lay = np.frombuffer(data, "u1", W * W, 5 + 2 * W * W).reshape(W, W)
        # the part of the window on the source terrain must be its samples exactly
        r0, r1 = max(wy, 0), min(wy + W, n)
        c0, c1 = max(wx, 0), min(wx + W, n)
        if r0 >= r1 or c0 >= c1:
            continue
        hs, ls = H[r0:r1, c0:c1], L[r0:r1, c0:c1]
        hw, lw = h[r0 - wy:r1 - wy, c0 - wx:c1 - wx], lay[r0 - wy:r1 - wy, c0 - wx:c1 - wx]
        dh, dl = int((hs != hw).sum()), int((ls != lw).sum())
        bad += dh + dl
        print(f"window at tile ({wcx:3d}, {wcy:3d}): {(r1 - r0) * (c1 - c0):9d} samples on the source, "
              f"{dh} heights and {dl} layers differ")
        tail = data[5 + 3 * W * W:]
        k = struct.unpack("<I", tail[:4])[0]
        assert k == len(mats)
    print("OK" if bad == 0 else f"FAILED: {bad} samples differ")
    sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
