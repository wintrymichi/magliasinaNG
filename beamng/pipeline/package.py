"""Zip the built level as a BeamNG mod: <ROOT>/dist/<name>.zip with levels/magliaso_pura/... and the level's
missions (v3.0.40, races.py): gameplay/missions/magliaso_pura/... beside the level folder.

Development files of the validation tour are left out. The archive goes into the user's
mods folder (or is installed from the zip).
"""
import hashlib, os, re, shutil, sys, zipfile, zlib
from concurrent.futures import ThreadPoolExecutor
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


def add(z, src, arc, ctype, when, packed=None):
    """src into z as arc, dated `when` (the packaging time), not the file's own time: the game keeps compiled shapes
    (.cdae) and uses one as long as it is newer than its .dae, so a .dae changed by a later build or patch but dated
    by an earlier step lost to a cache made from the version before (v3.1 test: the island poles of the previous
    nightly, beacon and reflector included, 30 missing materials each).
    packed: (data, deflated) made beforehand by deflate() in a thread: the same bytes zipfile would write (one
    compressobj over the whole file), written in place of its own compressor."""
    zi = zipfile.ZipInfo.from_file(src, arc)
    zi.date_time = when
    zi.compress_type = ctype
    with z.open(zi, "w", force_zip64=True) as w:
        if packed is not None and ctype == zipfile.ZIP_DEFLATED and hasattr(w, "_compressor"):
            data, comp = packed
            w._compressor = _Ready(comp)
            w.write(data)
            return
        with open(src, "rb") as f:
            shutil.copyfileobj(f, w, 1 << 22)


class _Ready:
    """A compressor whose output is ready: nothing while the data is written (zipfile takes its size and CRC-32),
    the whole deflate stream at the flush."""
    def __init__(self, comp):
        self.comp = comp

    def compress(self, data):
        return b""

    def flush(self):
        return self.comp


LEVEL = 6
# v3.2 (switzerlandNG, faster builds): the files are deflated in threads (zlib lets go of the GIL), ZIP_WORKERS of them,
# and written in the same order as before: the zip is byte for byte the one of one thread (builder/tests,
# test_parallel_zip; the Axenstrasse's level: same sizes, CRCs and offsets, 170 s -> 31 s)
WORKERS = max(1, int(os.environ.get("ZIP_WORKERS", min(4, os.cpu_count() or 1))))
IN_FLIGHT = 1 << 30            # bytes of files read and deflated ahead of the writer, at most (one file over it alone)


def deflate(src):
    data = open(src, "rb").read()
    c = zlib.compressobj(LEVEL, zlib.DEFLATED, -15)
    return data, c.compress(data) + c.flush()


def entries():
    """(src, arc, ctype) of every file of the zip, in the order of the zip."""
    out = []
    for root, _, files in os.walk(LEVEL_DIR):
        for f in files:
            if f in SKIP:
                continue
            src = os.path.join(root, f)
            arc = os.path.join("levels", LEVEL_NAME, os.path.relpath(src, LEVEL_DIR)).replace("\\", "/")
            # already compressed formats are stored
            ctype = zipfile.ZIP_STORED if f.lower().endswith((".jpg", ".png", ".dds")) else zipfile.ZIP_DEFLATED
            out.append((src, arc, ctype))
    missions = os.path.join(os.path.dirname(os.path.dirname(LEVEL_DIR)), "gameplay", "missions", LEVEL_NAME)
    for root, _, files in os.walk(missions):
        for f in sorted(files):
            src = os.path.join(root, f)
            arc = os.path.join("gameplay", "missions", LEVEL_NAME, os.path.relpath(src, missions)).replace("\\", "/")
            ctype = zipfile.ZIP_STORED if f.lower().endswith((".jpg", ".png")) else zipfile.ZIP_DEFLATED
            out.append((src, arc, ctype))
    return out


def write_zip(out, items, when, workers=WORKERS):
    """items (src, arc, ctype) into the zip out, in their order; the deflating in `workers` threads.
    Returns (files, bytes of the files)."""
    n = size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=LEVEL) as z:
        if workers <= 1:
            for src, arc, ctype in items:
                add(z, src, arc, ctype, when)
                n += 1; size += os.path.getsize(src)
            return n, size
        with ThreadPoolExecutor(workers) as pool:
            futs, ahead, i = [], 0, 0
            for k, (src, arc, ctype) in enumerate(items):
                # read and deflate ahead while the bytes in flight stay under IN_FLIGHT (always the next file)
                while i < len(items) and (i <= k or ahead < IN_FLIGHT):
                    s_, _, c_ = items[i]
                    sz = os.path.getsize(s_) if c_ == zipfile.ZIP_DEFLATED else 0
                    ahead += sz
                    futs.append((pool.submit(deflate, s_) if c_ == zipfile.ZIP_DEFLATED else None, sz))
                    i += 1
                fut, sz = futs[k]
                add(z, src, arc, ctype, when, fut.result() if fut is not None else None)
                futs[k] = (None, 0)
                ahead -= sz
                n += 1; size += os.path.getsize(src)
    return n, size


def main(name):
    import time
    when = time.localtime()[:6]
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, name + ".zip")
    t0 = time.time()
    n, size = write_zip(out, entries(), when)
    print(out, n, "files, %.0f MB level -> %.0f MB zip in %.0f s (%d threads)" % (
        size / 2**20, os.path.getsize(out) / 2**20, time.time() - t0, WORKERS))
    print("%s: %d entries, digest %s" % ((os.path.basename(out),) + digest(out)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else LEVEL_NAME)
