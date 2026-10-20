"""One file for each texture of the level (v3.0.40).

Several steps draw their textures one per object, and many come out the same: the opacity of the 112 bus stop
signs (one plate shape, one map each), the opacity of the direction signs of one shape, plates of the same text.
Each file is a texture of its own for the game: it converts every PNG to DDS when the level loads (BeamNG 0.40
again at every start, it clears its cache of the level) and keeps one copy of each in video memory. On a laptop with
512 MB of video memory the released v3.0 ran out of it while the game was converting the bus stop signs
(2026-10-20, BeamNG 0.40, twice).

Here the textures of the level with the same contents become one file: the json files of the level (the materials)
point at the first of them by name and the others are removed. A copy named anywhere else than in a whole json
string (a shape, a relative path) is kept as it is.

A finishing step of build_level.py (FINISH); alone: python build_level.py --finish same_textures
"""
import hashlib, json, os, re, time, zipfile
import bng
from config import LEVEL_NAME

EXT = (".png", ".dds", ".jpg", ".jpeg")


def same_textures_step(root, report=None):
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}/"
    first, dup = {}, {}
    for name in sorted(zi.namelist()):
        if name.startswith(lv) and name.lower().endswith(EXT):
            h = hashlib.md5(zi.read(name)).hexdigest()
            if h in first:
                dup[name] = first[h]
            else:
                first[h] = name
    texts = [n for n in zi.namelist() if n.startswith(lv) and n.lower().endswith((".json", ".dae", ".cs", ".lua"))]
    new_files, per_file = {}, {}
    if dup:
        # a json string that is exactly the path of a copy, with or without the leading slash
        rx = re.compile(r'"(/?)(' + "|".join(re.escape(k) for k in sorted(dup, key=len, reverse=True)) + r')"')
        for n in texts:
            if not n.endswith(".json"):
                continue
            text = zi.read(n).decode("utf-8")
            out, k = rx.subn(lambda m: '"%s%s"' % (m.group(1), dup[m.group(2)]), text)
            if k:
                new_files[n] = out
                per_file[n[len(lv):]] = k
    # a copy still named somewhere (by its file name, without its folder or extension) stays
    keep = set()
    if dup:
        stems = {os.path.splitext(os.path.basename(d))[0]: d for d in dup}
        rs = re.compile("|".join(re.escape(s) for s in sorted(stems, key=len, reverse=True)))
        for n in texts:
            text = new_files.get(n) if n in new_files else zi.read(n).decode("utf-8", errors="replace")
            keep |= {stems[m.group(0)] for m in rs.finditer(text)}
    gone = sorted(set(dup) - keep)
    now = time.localtime()[:6]
    with zi.writer() as zo:
        for i in zi.infolist():
            if i.filename not in new_files and i.filename not in gone:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for nm, text in sorted(new_files.items()):
            zo.writestr(zipfile.ZipInfo(nm, now), text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
    rep = {"textures": len(first) + len(dup), "copies": len(dup), "removed": len(gone), "kept_named_elsewhere": len(keep),
           "references": sum(per_file.values()), "per_file": per_file, "seconds": round(time.time() - t0, 1)}
    print("same textures: %d of %d texture files were copies, %d removed (%d references now on the first), %d kept"
          % (len(dup), rep["textures"], len(gone), rep["references"], len(keep)), flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
