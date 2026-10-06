"""The v2.8 zip from the v2.7 zip: the nine v2.8 patch scripts one after the other, as release_v2.8.yml runs them.

    python patch_v2_8.py magliaso_pura_v2.7.zip magliaso_pura_v2.8.zip [--reports <dir>] [--village-lights]

Each patch reads the zip the one before wrote (in a temporary folder next to the output, deleted as it goes):
1. patch_paved_edges.py   the ground raised to the edges of the paved surfaces: first, the terrain the others
                          stand on;
2. patch_wall_fill.py     the ground behind the retaining walls shaded like the terrain, no grass through it
                          (its normals and its grass from the heights of 1);
3. patch_understory.py    darker forest floor, its verge without grass, the undergrowth;
4. patch_lamps.py         street lamps in the villages (their lights only with --village-lights, whose frame
                          rate is still to be measured; the release has them on the 73 lamps of v2.7 only);
5. patch_roadside.py      delineators and wooden pole lines between the villages (clear of the lamps of 4);
6. patch_catenary.py      the overhead line of the railway;
7. patch_signs_more.py    warning and parking signs nobody mapped;
8. patch_lake.py          piers and boats;
9. patch_house_details.py gutters, downpipes, aerials, dishes, solar panels (the downpipes down to the ground of 1).
The ground first (1-3), then what stands on it (4-9): the objects stand on the v2.8 ground (placed on the v2.7
ground, 693 of the new lamps and 383 of the wooden poles would stand more than 5 cm under it; v28_check.py).
The patches read the zip and the files of beamng/dati, nothing downloaded: OpenStreetMap from the extract kept
there (MAGLIASO_OSM_PINNED), as on GitHub. Every patch writes its report (--report) in <dir> if given.
At the end: the entries of the zip, and a digest of their names, sizes and CRC-32, with the persistent ids
left out of the .json entries (random, new at every run) and not the dates. Two builds of the same patches from
the same v2.7 zip on the same system give the same digest: the v2.8 build test and the release can be compared
(on Windows the text of a few plates is drawn in another font: signs_ch._font).
"""
import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ("paved_edges", "wall_fill", "understory", "lamps", "roadside", "catenary", "signs_more", "lake",
         "house_details")
UUID = re.compile(rb"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def digest(path):
    """(entries, sha256 of the sorted lines "name size crc"): for a .json entry the size and CRC-32 of its
    text with every uuid (the persistentIds and the keys made of them) replaced."""
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


def main(src, dst, reports=None, village_lights=False):
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    reports = os.path.abspath(reports) if reports else None
    out_dir = os.path.dirname(dst)
    os.makedirs(out_dir, exist_ok=True)
    if reports:
        os.makedirs(reports, exist_ok=True)
    env = dict(os.environ, MAGLIASO_OSM_PINNED="1", PYTHONHASHSEED="0")
    print("in: %s, %d entries, digest %s" % ((os.path.basename(src),) + digest(src)), flush=True)
    tmp = tempfile.mkdtemp(prefix="patch_v2_8_", dir=out_dir)
    cur, t_all = src, time.time()
    try:
        for k, name in enumerate(STEPS, 1):
            nxt = dst if k == len(STEPS) else os.path.join(tmp, f"{k}_{name}.zip")
            cmd = [sys.executable, "-u", os.path.join(HERE, f"patch_{name}.py"), cur, nxt]
            if name == "lamps" and village_lights:
                cmd.append("--village-lights")
            if reports:
                cmd += ["--report", os.path.join(reports, f"{name}_report.json")]
            print(f"\n== {k}/{len(STEPS)} patch_{name}.py", flush=True)
            t = time.time()
            subprocess.run(cmd, check=True, cwd=HERE, env=env)
            if cur != src:
                os.remove(cur)
            with zipfile.ZipFile(nxt) as z:
                n = len(z.namelist())
            print("== patch_%s.py: %.0f s, %d entries, %.1f MB" % (name, time.time() - t, n, os.path.getsize(nxt) / 1e6),
                  flush=True)
            cur = nxt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n, d = digest(dst)
    print("\nout: %s, %d entries, %.1f MB, digest %s, %.0f min" % (os.path.basename(dst), n, os.path.getsize(dst) / 1e6,
                                                                   d, (time.time() - t_all) / 60), flush=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--reports")
    ap.add_argument("--village-lights", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.src, a.dst, a.reports, a.village_lights))
