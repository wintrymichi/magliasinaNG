"""Copy vanilla Material definitions (by name / mapTo) into a level materials file.

Vanilla shapes (trees, props) reference materials defined in the materials.json of
the level that ships them; a new level must carry those definitions itself. Texture
paths are made absolute so they keep pointing into the original level/asset zips.
"""
import glob, json, os, re, zipfile
from config import BEAMNG_GAME, WORK

PREFER = ["east_coast_usa", "italy", "west_coast_usa", "small_island", "jungle_rock_island", "Utah", "johnson_valley"]
_INDEX = None


def index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    cache = os.path.join(WORK, "material_index.json")
    if os.path.exists(cache):
        _INDEX = json.load(open(cache))
        return _INDEX
    idx = {}
    zips = glob.glob(os.path.join(BEAMNG_GAME, "content", "**", "*.zip"), recursive=True)
    for zp in zips:
        if os.sep + "vehicles" + os.sep in zp:
            continue
        try:
            z = zipfile.ZipFile(zp)
        except Exception:
            continue
        for n in z.namelist():
            if not n.endswith("materials.json"):
                continue
            try:
                d = json.loads(z.read(n).decode("utf-8", "ignore"))
            except Exception:
                continue
            for k, v in d.items():
                if not isinstance(v, dict) or v.get("class") != "Material":
                    continue
                for key in {k, v.get("name"), v.get("mapTo")}:
                    if key:
                        idx.setdefault(key, []).append({"file": n, "def": v})
    json.dump(idx, open(cache, "w"))
    _INDEX = idx
    return idx


def absolutize(v, src_file):
    base = "/" + os.path.dirname(src_file) + "/"

    def fix(s):
        if not isinstance(s, str) or not re.search(r"\.(png|dds|jpg|jpeg|tga)$", s, re.I):
            return s
        if s.startswith("/"):
            return s
        if s.startswith(("levels/", "assets/", "art/", "core/", "vehicles/")):
            return "/" + s
        return base + s
    out = json.loads(json.dumps(v))
    for st in out.get("Stages", []) or []:
        if isinstance(st, dict):
            for k in list(st):
                st[k] = fix(st[k])
    for k in list(out):
        out[k] = fix(out[k]) if isinstance(out[k], str) else out[k]
    return out


def collect(names):
    idx = index()
    found, missing = {}, []
    for nm in names:
        cands = idx.get(nm)
        if not cands:
            missing.append(nm)
            continue
        cands = sorted(cands, key=lambda c: next((i for i, p in enumerate(PREFER) if f"levels/{p}/" in c["file"]), 99))
        c = cands[0]
        d = absolutize(c["def"], c["file"])
        d["name"] = nm
        d["mapTo"] = nm
        found[nm] = d
    return found, missing
