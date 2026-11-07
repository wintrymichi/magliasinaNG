"""The Lua side outside the game: terwin.lua's window (.ter) must equal blocks.window_ter byte for byte, and its
base PNGs must decode (PIL) to the blocks' colour maps, rows from the north. Needs luajit.

    python tests/test_lua.py --out <blocks.py output> [--zone zones/malcantone.json]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import blocks  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--zone", default=os.path.join(HERE, "..", "zones", "malcantone.json"))
    a = ap.parse_args()
    zone = blocks.Zone(json.load(open(a.zone)))
    lv = os.path.join(a.out, "levels", blocks.LEVEL)
    cfg = json.load(open(os.path.join(lv, "stream.json")))
    nb, P = cfg["blocksPerSide"], cfg["basePx"]
    bad = 0
    for wcx, wcy in [(10, 12), (-2, 3), (24, 25)]:
        wx, wy = wcx * zone.C, wcy * zone.C
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(["luajit", os.path.join(HERE, "terwin_cli.lua"), lv, str(wx), str(wy), td],
                               capture_output=True, text=True)
            print(r.stdout.strip(), r.stderr.strip())
            if r.returncode:
                bad += 1
                continue
            got = open(os.path.join(td, "w.ter"), "rb").read()
            want = blocks.window_ter(zone, os.path.join(lv, "blocks", "terrain"), nb, wx, wy, cfg["materials"])
            same = got == want
            bad += not same
            for key in cfg["baseTextures"]:
                img = np.asarray(Image.open(os.path.join(td, key + ".png")).convert("RGB"))
                Bp, Wp = zone.B // P, zone.W // P
                exp = np.full((Wp, Wp, 3), 128, np.uint8)
                # expected map: rows from the south assembled from the .rgb blocks, then flipped
                for bx in range(-1, nb + 1):
                    for by in range(-1, nb + 1):
                        p = os.path.join(lv, "blocks", "base", f"{key}_{bx}_{by}.rgb")
                        if not os.path.exists(p):
                            continue
                        blk = np.fromfile(p, np.uint8).reshape(Bp, Bp, 3)
                        x0, y0 = bx * Bp - wx // P, by * Bp - wy // P
                        xa, ya = max(x0, 0), max(y0, 0)
                        xb, yb = min(x0 + Bp, Wp), min(y0 + Bp, Wp)
                        if xa < xb and ya < yb:
                            exp[ya:yb, xa:xb] = blk[ya - y0:yb - y0, xa - x0:xb - x0]
                ok = np.array_equal(img, exp[::-1])
                bad += not ok
                if not ok:
                    print("  base", key, "differs")
            print(f"window at tile ({wcx}, {wcy}): .ter {'identical' if same else 'DIFFERENT'}, "
                  f"{len(cfg['baseTextures'])} base PNGs checked")
    print("OK" if bad == 0 else f"FAILED ({bad})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
