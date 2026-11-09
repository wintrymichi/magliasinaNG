"""Checks of the Switzerland Builder that need no download: python tests/test_builder.py (from beamng/builder, with the
app's Python: start-switzerland-builder.sh runs it as `micromamba run -p .runtime/env python ...`).

- app/zone.py keeps its own copy of the pipeline's local frame and terrain grid (the app must not import config.py,
  which makes folders when MAGLIASO_ROOT is not set): the copy must equal config.py;
- the checks of a picked area: a good box passes, a box outside Switzerland, too big or too small is refused, a box
  in a canton without an open cadastral survey gets the warning;
- a zone's terrain block lies on the pipeline's sample grid and holds the area with 2 km to spare (a small area gets
  the 4096 block), and the shift of recenter puts the middle of the block at the origin on the same grid.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.dirname(HERE)
sys.path.insert(0, BUILDER)

from app import zone  # noqa: E402

CONFIG = os.path.join(BUILDER, "..", "pipeline", "config.py")


def config_constants():
    """The module-level constants of config.py, read without running it."""
    out = {}
    for node in ast.parse(open(CONFIG, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign):
            try:
                val = ast.literal_eval(node.value)
            except ValueError:
                continue
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = val
                elif isinstance(t, ast.Tuple) and isinstance(val, tuple):
                    for n, v in zip(t.elts, val):
                        if isinstance(n, ast.Name):
                            out[n.id] = v
    return out


def test_frame():
    c = config_constants()
    for k in ("E0", "N0", "K", "TER_X0", "TER_Y0", "TER_SQUARE", "TER_SIZE"):
        assert getattr(zone, k) == c[k], f"zone.{k} = {getattr(zone, k)}, config.py {c[k]}"


def test_checks():
    sisikon = zone.check([46.915, 8.588, 46.983, 8.643])           # the test area of builder_test.yml
    assert sisikon["ok"], sisikon["errors"]
    assert sisikon["cantons"] == ["sz", "ur"], sisikon["cantons"]
    assert not sisikon["survey_closed"]
    milano = zone.check([45.44, 9.15, 45.48, 9.21])
    assert not milano["ok"] and "not in Switzerland" in milano["errors"][0]
    big = zone.check([46.0, 8.9, 46.2, 9.1])
    assert not big["ok"] and any("at most" in e for e in big["errors"])
    small = zone.check([46.000, 8.950, 46.002, 8.952])
    assert not small["ok"] and any("too small" in e for e in small["errors"])
    sion = zone.check([46.22, 7.33, 46.25, 7.38])                  # Valais: no open survey on geodienste.ch
    assert sion["ok"] and sion["survey_closed"] == ["Valais"], sion["survey_closed"]
    assert any("No open cadastral survey" in w for w in sion["warnings"])


def test_zone_grid():
    bbox = [46.915, 8.588, 46.983, 8.643]
    z = zone.make_zone("ch_test", "Test", bbox)
    for k in ("ter_x0", "ter_y0"):
        steps = (z[k] - getattr(zone, k.upper())) / zone.TER_SQUARE
        assert abs(steps - round(steps)) < 1e-9, (k, z[k])
    side = (z["ter_size"] - 1) * zone.TER_SQUARE
    x0, y0, x1, y1 = z["core_local"]
    for lo, hi, t0 in ((x0, x1, z["ter_x0"]), (y0, y1, z["ter_y0"])):
        assert lo - t0 >= 1900 and t0 + side - hi >= 1900, (lo, hi, t0)
    dx, dy = zone.recenter_shift(z)
    assert abs(dx / zone.TER_SQUARE - round(dx / zone.TER_SQUARE)) < 1e-9
    cx, cy = z["ter_x0"] + side / 2 + dx, z["ter_y0"] + side / 2 + dy
    assert abs(cx) <= zone.TER_SQUARE and abs(cy) <= zone.TER_SQUARE, (cx, cy)
    assert z["ter_size"] == zone.TER_SIZE                          # 7.6 km a side: the big block


def test_small_block():
    """A small area (Sisikon, 0.9 km2) gets the 4096 block, with TER_MARGIN round it and on the same grid."""
    z = zone.make_zone("ch_small", "Small", [46.945, 8.615, 46.954, 8.628])
    assert z["ter_size"] == zone.TER_SMALL, z["ter_size"]
    side = (z["ter_size"] - 1) * zone.TER_SQUARE
    x0, y0, x1, y1 = z["core_local"]
    for lo, hi, t0 in ((x0, x1, z["ter_x0"]), (y0, y1, z["ter_y0"])):
        assert lo - t0 >= zone.TER_MARGIN - 2 and t0 + side - hi >= zone.TER_MARGIN - 2, (lo, hi, t0)
        steps = (t0 - zone.TER_X0) / zone.TER_SQUARE if t0 == z["ter_x0"] else (t0 - zone.TER_Y0) / zone.TER_SQUARE
        assert abs(steps - round(steps)) < 1e-9
    chk = zone.check([46.945, 8.615, 46.954, 8.628])
    assert chk["terrain_km"] == 6.1, chk["terrain_km"]


def test_parallel_zip():
    """package.write_zip with 4 threads writes the same bytes as with one (switzerlandNG faster builds)."""
    import random
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp()
    lvl = os.path.join(tmp, "lv")
    rnd = random.Random(5)
    for k in range(40):
        d = os.path.join(lvl, "art", str(k % 4))
        os.makedirs(d, exist_ok=True)
        ext = (".dae", ".json", ".png", ".ter")[k % 4]
        body = bytes(rnd.randrange(0, 16) for _ in range(rnd.randrange(0, 300000)))
        open(os.path.join(d, f"f{k}{ext}"), "wb").write(body)
    code = (
        "import sys, zipfile; sys.path.insert(0, %r); import package as p\n"
        "it = [(s, s[len(%r):], zipfile.ZIP_STORED if s.endswith('.png') else zipfile.ZIP_DEFLATED)\n"
        "      for s in sorted(__import__('glob').glob(%r, recursive=True)) if not __import__('os').path.isdir(s)]\n"
        "p.IN_FLIGHT = 1 << 20\n"
        "p.write_zip(%r, it, (2026, 1, 1, 0, 0, 0), 1); p.write_zip(%r, it, (2026, 1, 1, 0, 0, 0), 4)\n") % (
        os.path.join(BUILDER, "..", "pipeline"), lvl + os.sep, os.path.join(lvl, "**"),
        os.path.join(tmp, "a.zip"), os.path.join(tmp, "b.zip"))
    env = dict(os.environ, MAGLIASO_ROOT=tmp, MAGLIASO_BEAMNG_USER=tmp, MAGLIASO_DATASET=tmp)
    env.pop("MAGLIASO_ZONE", None)
    subprocess.run([sys.executable, "-c", code], check=True, env=env)
    a, b = (open(os.path.join(tmp, f), "rb").read() for f in ("a.zip", "b.zip"))
    assert a == b and len(a) > 1000, (len(a), len(b))


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
