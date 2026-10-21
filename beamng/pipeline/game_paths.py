"""The game's files where BeamNG.drive 0.40 keeps them (v3.0.40).

The level draws many of its surfaces and models on the game's own textures (Italy's asphalt, stone walls,
cobbles, road overlays and props, a few of East Coast USA and Jungle Rock Island). 0.40 cleaned up duplicate
materials and textures and moved 73 of the files the v3.0 level refers to from the level folders
(/levels/italy/art/...) to /assets/materials/...: 70 left a redirect behind, 3 did not (the medieval stone wall's
colour and normal maps, italy_plastic_d), and those showed as missing textures in 0.40. The table of the moves is
dati/game_paths_0.40.json (old path -> new path, checked in an installed 0.40).

The material definitions come from several places (dati/*.json, copied from the installed game by
copy_materials.py, carried over from a released level): this last finishing step points every string of the
level's json files that names a moved file at its new place, whatever wrote it. Only whole string values that
are exactly an old path (with or without the leading /, any case) change; everything else is copied as it is.

A finishing step of build_level.py (FINISH), on the built level; alone: python build_level.py --finish game_paths
"""
import json, os, re, time
import bng
from config import LEVEL_NAME

TABLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "game_paths_0.40.json")
MOVED = {k.lower(): v for k, v in json.load(open(TABLE))["moved"].items()}
# a json string that is exactly one of the old paths, with or without the leading slash
_STRING = re.compile(r'"(/?)(' + "|".join(re.escape(k) for k in sorted(MOVED, key=len, reverse=True)) + r')"', re.I)


def fix(path):
    """The path where 0.40 keeps the file `path` names (the same path if it did not move)."""
    if not isinstance(path, str):
        return path
    new = MOVED.get(path.lstrip("/").lower())
    return path if new is None else ("/" if path.startswith("/") else "") + new


def fix_text(text):
    """json text with every string naming a moved file pointed at its new place; (text, count)."""
    return _STRING.subn(lambda m: '"%s%s"' % (m.group(1), MOVED[m.group(2).lower()]), text)


def game_paths_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}/"
    new_files, per_file = {}, {}
    for name in zi.namelist():
        if not (name.startswith(lv) and name.endswith(".json")):
            continue
        text = zi.read(name).decode("utf-8")
        out, n = fix_text(text)
        if n:
            new_files[name] = out.encode("utf-8")
            per_file[name[len(lv):]] = n
    import zipfile
    now = time.localtime()[:6]
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename not in new_files:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, data in sorted(new_files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), data, compress_type=zipfile.ZIP_DEFLATED)
    rep = {"files": len(per_file), "strings": sum(per_file.values()), "per_file": per_file,
           "seconds": round(time.time() - t0, 1)}
    print("game paths: %d strings in %d files pointed at where the game 0.40 keeps them"
          % (rep["strings"], rep["files"]), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
