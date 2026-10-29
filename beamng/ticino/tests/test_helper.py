"""ticino_helper.py against the streamer: the window the Lua makes at the first jump (tests/sim_stream.lua, helper
off) must equal the helper's, the .ter byte for byte and the base map pixel for pixel. Needs lupa (no luajit in the
cloud), numpy, PIL and a level folder with levels/ticino/stream.json and the blocks of the start (e.g. the base zip
and the ti_0_0 zone zip extracted).

    python tests/test_helper.py <folder with levels/ticino/>
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    root = os.path.abspath(sys.argv[1])
    shutil.rmtree(os.path.join(root, "temp"), ignore_errors=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "luajit.py"), os.path.join(HERE, "sim_stream.lua"), root,
                        "1"], capture_output=True, text=True, cwd=os.path.join(HERE, ".."))
    assert r.returncode == 0, r.stderr[-2000:]
    perf = open(os.path.join(root, "temp", "ticino_perf_sim.csv")).read().splitlines()
    cols = perf[0].split(",")
    jump = dict(zip(cols, perf[1].split(",")))
    assert jump["kind"] == "jump" and jump["helper"] == "0.00", jump
    wx, wy = int(float(jump["wx"])), int(float(jump["wy"]))
    t = os.path.join(root, "temp", "ticino")
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "helper", "ticino_helper.py"), "--user", root,
                            "--once", str(wx), str(wy), "--out", td], capture_output=True, text=True)
        print(r.stdout.strip())
        assert r.returncode == 0, r.stderr[-2000:]
        same_ter = open(os.path.join(t, "w1.ter"), "rb").read() == open(os.path.join(td, "w.ter"), "rb").read()
        a = np.asarray(Image.open(os.path.join(t, "base_1.png")))
        b = np.asarray(Image.open(os.path.join(td, "base.png")))
        same_png = a.shape == b.shape and bool((a == b).all())
    print("window %d,%d: .ter %s, base map %s" % (wx, wy, "same" if same_ter else "DIFFERENT",
                                                   "same" if same_png else "DIFFERENT"))
    sys.exit(0 if same_ter and same_png else 1)


if __name__ == "__main__":
    main()
