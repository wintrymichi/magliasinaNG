"""Checks of the Switzerland Builder that need no download: python tests/test_builder.py (from beamng/builder, with the
app's Python: start-switzerland-builder.sh runs it as `micromamba run -p .runtime/env python ...`).

- app/zone.py keeps its own copy of the pipeline's local frame and terrain grid (the app must not import config.py,
  which makes folders when MAGLIASO_ROOT is not set): the copy must equal config.py;
- the checks of a picked area: a good box passes, a box outside Switzerland, too big or too small is refused, a box
  in a canton without an open cadastral survey gets the warning;
- a zone's terrain block lies on the pipeline's sample grid and holds the area with 2 km to spare, and the shift of
  recenter puts the middle of the block at the origin on the same grid.
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
