"""Zip the built level as a BeamNG mod: <ROOT>/dist/<name>.zip with levels/magliaso_pura/...

Development files of the validation tour are left out. The archive goes into the user's
mods folder (or is installed from the zip).
"""
import hashlib, os, re, sys, zipfile
from config import LEVEL_DIR, LEVEL_NAME, ROOT

SKIP = {"validation_views.json", "validation_route.json"}


UUID = re.compile(rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def digest(path):
    """(entries, sha256 of the sorted lines "name size crc"): for a .json entry the size and CRC-32 of its
    text with every uuid (the persistentIds and the keys made of them, random at every build) replaced. Two
    builds of the same commit on the same system give the same digest (PYTHONHASHSEED=0, MAGLIASO_OSM_PINNED=1):
    the zip of the build test and the one of the release can be compared."""
    rows = []
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.filename.endswith(".json"):
                b = UUID.sub(b"<id>", z.read(i))
                rows.append((i.filename, len(b), zipfile.crc32(b)))
            else:
                rows.append((i.filename, i.file_size, i.CRC))
    h = hashlib.sha256()
    for name, size, crc in sorted(rows):
        h.update(f"{name}\t{size}\t{crc:08x}\n".encode("utf-8"))
    return len(rows), h.hexdigest()


def main(name):
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, name + ".zip")
    n = size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, files in os.walk(LEVEL_DIR):
            for f in files:
                if f in SKIP:
                    continue
                src = os.path.join(root, f)
                arc = os.path.join("levels", LEVEL_NAME, os.path.relpath(src, LEVEL_DIR)).replace("\\", "/")
                # already compressed formats are stored
                ctype = zipfile.ZIP_STORED if f.lower().endswith((".jpg", ".png", ".dds")) else zipfile.ZIP_DEFLATED
                z.write(src, arc, compress_type=ctype)
                n += 1; size += os.path.getsize(src)
    print(out, n, "files, %.0f MB level -> %.0f MB zip" % (size / 2**20, os.path.getsize(out) / 2**20))
    print("%s: %d entries, digest %s" % ((os.path.basename(out),) + digest(out)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else LEVEL_NAME)
