"""The zone grid of the whole Ticino: one pipeline build per zone (config.MAGLIASO_ZONE), cut into blocks afterwards.

A zone's core is ZONE_BLOCKS x ZONE_BLOCKS terrain blocks (4 x 1,920 m = 7,680 m, about the Malcantone level's size: the
full build of that took 4 h 45 min on a GitHub runner, under the 6 h limit). The grid is the Malcantone level's own
terrain grid (vertex (0, 0) at TER_X0, TER_Y0, 1.5 m, blocks of 1,280 samples), so every zone's blocks line up with the
Malcantone's sample for sample; the cores start at block GRID_OFFSET + 4 i, which puts Lugano in one core.
Each zone builds:
  - the playable area: the core + OVERLAP m (roads, walls and buildings crossing the core's edge are built whole in
    both neighbours; the blocks keep only their core);
  - the terrain block: 8,192 samples centred on the core (2,304 m round it), as the Malcantone level has.
The local frame (config.E0, N0) is the same for every zone, so the zones' coordinates fit together as they are.

    python zones.py [--bbox-wgs S W N E] [--out zones/ti]      (default: the canton's bounding box)
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline"))
os.environ.setdefault("MAGLIASO_ROOT", os.path.join(HERE, ".zones_root"))   # config makes data folders under it
os.environ.pop("MAGLIASO_ZONE", None)
import config  # noqa: E402

BLOCK = 1280                    # samples a block (blocks.py, zones/malcantone.json)
SQ = config.TER_SQUARE
ZONE_BLOCKS = 4
GRID_OFFSET = 2                 # cores start at block 2 + 4 i of the Malcantone grid (Lugano in one core)
OVERLAP = 300.0                 # m of playable area beyond the core on every side
TER_SIZE = 8192
TICINO_WGS = (45.81, 8.37, 46.64, 9.17)      # S, W, N, E: the canton with a little room


def zone(i, j):
    B = BLOCK * SQ
    cx0 = config.TER_X0 + (GRID_OFFSET + ZONE_BLOCKS * i) * B
    cy0 = config.TER_Y0 + (GRID_OFFSET + ZONE_BLOCKS * j) * B
    side = ZONE_BLOCKS * B
    pad = ((TER_SIZE - 1) * SQ - side) / 2
    pad = math.floor(pad / SQ) * SQ                # on the sample grid
    a = [config.local_to_lv95(cx0 - OVERLAP, cy0 - OVERLAP), config.local_to_lv95(cx0 + side + OVERLAP, cy0 + side + OVERLAP)]
    name = f"ti_{i}_{j}".replace("-", "m")
    return {
        "name": name, "level": name,
        "core_local": [cx0, cy0, cx0 + side, cy0 + side],
        "core_blocks": [GRID_OFFSET + ZONE_BLOCKS * i, GRID_OFFSET + ZONE_BLOCKS * j, ZONE_BLOCKS],
        "area_lv95": [round(a[0][0], 2), round(a[0][1], 2), round(a[1][0], 2), round(a[1][1], 2)],
        "ter_size": TER_SIZE, "ter_x0": cx0 - pad, "ter_y0": cy0 - pad,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox-wgs", nargs=4, type=float, default=TICINO_WGS)
    ap.add_argument("--out", default=os.path.join(HERE, "zones", "ti"))
    a = ap.parse_args()
    s, w, n, e = a.bbox_wgs
    pts = [config.wgs_to_local(la, lo) for la in (s, n) for lo in (w, e)]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    B = BLOCK * SQ * ZONE_BLOCKS
    i0 = math.floor((x0 - config.TER_X0 - GRID_OFFSET * BLOCK * SQ) / B)
    i1 = math.floor((x1 - config.TER_X0 - GRID_OFFSET * BLOCK * SQ) / B)
    j0 = math.floor((y0 - config.TER_Y0 - GRID_OFFSET * BLOCK * SQ) / B)
    j1 = math.floor((y1 - config.TER_Y0 - GRID_OFFSET * BLOCK * SQ) / B)
    os.makedirs(a.out, exist_ok=True)
    names = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            z = zone(i, j)
            with open(os.path.join(a.out, z["name"] + ".json"), "w") as f:
                json.dump(z, f, indent=1)
            names.append(z["name"])
    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump({"i": [i0, i1], "j": [j0, j1], "zones": names}, f, indent=1)
    print(len(names), "zones,", i1 - i0 + 1, "x", j1 - j0 + 1)


if __name__ == "__main__":
    main()
