"""Zip the built level as a BeamNG mod: D:/beamng_magliaso/dist/<name>.zip with levels/magliaso_pura/...

Development files of the validation tour are left out. The archive goes into the user's
mods folder (or is installed from the zip).
"""
import os, sys, zipfile
from config import LEVEL_DIR, LEVEL_NAME

SKIP = {"validation_views.json", "validation_route.json"}


def main(name):
    out_dir = r"D:\beamng_magliaso\dist"
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


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else LEVEL_NAME)
