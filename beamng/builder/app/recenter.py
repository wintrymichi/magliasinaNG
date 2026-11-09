"""Move a built level so the middle of its terrain block is at the origin of the game's world.

The pipeline builds every area in the Malcantone's local frame (config.py), so an area in the north of Switzerland
lies 100-200 km from the origin. BeamNG keeps positions in float32: there one step of a coordinate is 8-16 mm, the
car and the camera shake and thin paint flickers on the road. The level is shifted once it is finished, before it is
packed: every position, node and point of the scene files, of the forest, of the sites, signals and missions, and
the vertices of the few shapes written with absolute coordinates (an object at x = y = 0: the backdrop, the merged
props). Shapes placed by their object's position (nearly all) are not touched. Heights do not change.

    python -m app.recenter <level folder> <dx> <dy> [--missions <gameplay/missions/<level> folder>]

Safe to run once only: it writes recenter.json into the level and refuses a second run. A run stopped half way (a
crash, the app closed, the watchdog) goes on where it stopped: recenter.journal lists every file already moved.
"""
import json
import os
import re
import sys

POINT_KEYS = ("position", "pos")                 # a point [x, y, z, ...]
LIST_KEYS = ("nodes", "vertices", "points")      # a list of points [[x, y, z, ...], ...]
_PA = re.compile(r'(<float_array id="[^"]*-pa"[^>]*>)([^<]*)(</float_array>)')


def _is_point(v):
    return isinstance(v, list) and len(v) >= 3 and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in v[:3])


def shift_obj(o, dx, dy, stats):
    """Shift every point under the known keys of a JSON value, in place."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in POINT_KEYS and _is_point(v):
                v[0] = round(v[0] + dx, 6)
                v[1] = round(v[1] + dy, 6)
                stats["points"] += 1
            elif k in LIST_KEYS and isinstance(v, list) and v and all(_is_point(p) for p in v):
                for p in v:
                    p[0] = round(p[0] + dx, 6)
                    p[1] = round(p[1] + dy, 6)
                stats["points"] += len(v)
            else:
                shift_obj(v, dx, dy, stats)
    elif isinstance(o, list):
        for v in o:
            shift_obj(v, dx, dy, stats)


def _rewrite(path, text):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)          # a new file: the level may be a hard-linked copy


def shift_json_file(path, dx, dy, stats, absolute_shapes=None, write=True):
    raw = open(path, encoding="utf-8").read()
    lines = [l for l in raw.splitlines() if l.strip()]
    try:
        docs, per_line = [json.loads(raw)], False
    except json.JSONDecodeError:
        docs, per_line = [json.loads(l) for l in lines], True
    if os.path.basename(path) == "main.decals.json":
        inst = docs[0].get("instances") if docs and isinstance(docs[0], dict) else None
        if inst:
            raise SystemExit(f"recenter: {path} has decal instances, whose format is not known here")
        return
    n0 = stats["points"]
    for d in docs:
        if per_line and isinstance(d, dict) and d.get("class") == "TSStatic" and absolute_shapes is not None:
            p = d.get("position", [0, 0, 0])
            if abs(p[0]) < 1e-6 and abs(p[1]) < 1e-6:
                rot = d.get("rotationMatrix", [1, 0, 0, 0, 1, 0, 0, 0, 1])
                scale = d.get("scale", [1, 1, 1])
                plain = all(abs(a - b) < 1e-9 for a, b in zip(rot, [1, 0, 0, 0, 1, 0, 0, 0, 1])) and \
                    all(abs(s - 1) < 1e-9 for s in scale)
                if plain and d.get("shapeName", "").startswith("/levels/"):
                    absolute_shapes.setdefault(d["shapeName"], []).append(path)
                    continue                      # its vertices move instead (shift_dae)
        shift_obj(d, dx, dy, stats)
    if stats["points"] == n0 or not write:
        return
    if per_line:
        text = "\n".join(json.dumps(d, separators=(",", ":")) for d in docs) + "\n"
    else:
        text = json.dumps(docs[0], indent=1 if raw.lstrip().startswith("{\n") else None)
    _rewrite(path, text)
    stats["files"] += 1


def _fmt(vals):
    out = []
    for v in vals:
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        out.append("0" if s in ("-0", "") else s)
    return " ".join(out)


def shift_dae(path, dx, dy):
    """The position arrays (g-pa, g1-pa, ...) of a shape written in level coordinates, shifted; returns vertices."""
    text = open(path, encoding="utf-8").read()
    n = [0]

    def sub(m):
        vals = [float(v) for v in m.group(2).split()]
        for i in range(0, len(vals) - 2, 3):
            vals[i] += dx
            vals[i + 1] += dy
        n[0] += len(vals) // 3
        return m.group(1) + _fmt(vals) + m.group(3)
    new = _PA.sub(sub, text)
    if n[0]:
        _rewrite(path, new)
    return n[0]


def shape_users(level):
    """{shapeName: number of TSStatics} over the whole level."""
    users = {}
    for dp, _, fs in os.walk(os.path.join(level, "main")):
        for f in fs:
            if f == "items.level.json":
                for l in open(os.path.join(dp, f), encoding="utf-8"):
                    if '"TSStatic"' in l:
                        d = json.loads(l)
                        users[d.get("shapeName", "")] = users.get(d.get("shapeName", ""), 0) + 1
    return users


def recenter(level, dx, dy, missions=None):
    level = os.path.abspath(level)
    mark = os.path.join(level, "recenter.json")
    if os.path.exists(mark):
        raise SystemExit(f"recenter: {level} was moved already ({json.load(open(mark))})")
    stats = {"points": 0, "files": 0, "dae_vertices": 0, "dae_files": 0}
    # the files moved so far ("<phase> <path>" a line, appended right after each file is replaced): a second run
    # after a stop skips them (2026-11-09: a kill half way through and a retry moved the first files twice)
    jpath = os.path.join(level, "recenter.journal")
    done = set()
    if os.path.exists(jpath):
        done = {l.rstrip("\n") for l in open(jpath, encoding="utf-8") if l.endswith("\n")}
        print(f"recenter: going on after a stop, {len(done)} files moved already", flush=True)
    journal = open(jpath, "a", encoding="utf-8")

    def did(key):
        journal.write(key + "\n")
        journal.flush()
        os.fsync(journal.fileno())
    absolute = {}
    users = shape_users(level)
    name = os.path.basename(level)
    files = []
    for dp, _, fs in os.walk(level):
        for f in fs:
            if f.endswith(".json") and not f.endswith(("materials.json", ".asset.json", "terrain.json", "info.json",
                                                         "managedItemData.json", "recenter.json")):
                files.append(os.path.join(dp, f))
    for p in sorted(files):
        key = "json " + os.path.relpath(p, level)
        # a file done before still tells which shapes are in level coordinates (nothing written)
        shift_json_file(p, dx, dy, stats if key not in done else dict(stats), absolute, write=key not in done)
        if key not in done:
            did(key)
    # shapes in level coordinates: their vertices move, their objects stay at 0 (one shape used by an object placed
    # elsewhere as well would move twice there: then the object at 0 is moved instead)
    for shape, where in absolute.items():
        path = os.path.join(level, *shape.split("/")[3:]) if shape.startswith(f"/levels/{name}/") else None
        if path and os.path.exists(path) and users.get(shape, 0) == len(where):
            key = "dae " + os.path.relpath(path, level)
            if key not in done:
                stats["dae_vertices"] += shift_dae(path, dx, dy)
                stats["dae_files"] += 1
                did(key)
        else:
            for items in sorted(set(where)):
                key = "pos " + shape + " " + os.path.relpath(items, level)
                if key in done:
                    continue
                rows = [json.loads(l) for l in open(items, encoding="utf-8") if l.strip()]
                for d in rows:
                    if d.get("class") == "TSStatic" and d.get("shapeName") == shape:
                        d["position"][0] += dx
                        d["position"][1] += dy
                        stats["points"] += 1
                _rewrite(items, "\n".join(json.dumps(d, separators=(",", ":")) for d in rows) + "\n")
                did(key)
    if missions and os.path.isdir(missions):
        for dp, _, fs in os.walk(missions):
            for f in fs:
                if f.endswith(".json"):
                    q = os.path.join(dp, f)
                    key = "mis " + os.path.relpath(q, missions)
                    if key not in done:
                        shift_json_file(q, dx, dy, stats)
                        did(key)
    stats.update(dx=dx, dy=dy)
    journal.close()
    with open(mark + ".part", "w") as f:
        json.dump(stats, f, indent=1)
    os.replace(mark + ".part", mark)
    os.remove(jpath)
    print("recenter:", stats, flush=True)
    return stats


if __name__ == "__main__":
    a = sys.argv[1:]
    miss = None
    if "--missions" in a:
        i = a.index("--missions")
        miss = a[i + 1]
        a = a[:i] + a[i + 2:]
    recenter(a[0], float(a[1]), float(a[2]), miss)
