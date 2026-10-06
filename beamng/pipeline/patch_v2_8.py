"""The v2.8 zip from the v2.7 zip: the nine v2.8 patch scripts one after the other, as release_v2.8.yml runs them.

    python patch_v2_8.py magliaso_pura_v2.7.zip magliaso_pura_v2.8.zip [--reports <dir>] [--village-lights]

Each patch reads the zip the one before wrote (next to the output, deleted once the next one is written):
1. patch_paved_edges.py   the ground raised to the edges of the paved surfaces: first, the terrain the others
                          stand on;
2. patch_wall_fill.py     the ground behind the retaining walls shaded like the terrain, no grass through it;
3. patch_understory.py    darker forest floor, its verge without grass, the undergrowth;
4. patch_lamps.py         street lamps in the villages (their lights only with --village-lights, whose frame
                          rate is still to be measured; the release has them on the 73 lamps of v2.7 only);
5. patch_roadside.py      delineators and wooden pole lines between the villages;
6. patch_catenary.py      the overhead line of the railway;
7. patch_signs_more.py    warning and parking signs nobody mapped;
8. patch_lake.py          piers and boats;
9. patch_house_details.py gutters, downpipes, aerials, dishes, solar panels.
The ground first (1-3), then what stands on it (4-9), so that it stands on the ground of v2.8. Every patch writes
its report (--report) in <dir> if given. At the end: the entries of the zip, and a digest of their names, sizes
and CRC-32 that does not depend on the dates in the zip (the same patches on the same v2.7 zip give the same
digest: the test workflow and the release can be compared).
"""
import argparse, hashlib, os, subprocess, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ("paved_edges", "wall_fill", "understory", "lamps", "roadside", "catenary", "signs_more", "lake",
         "house_details")


def digest(path):
    """(entries, sha256 of the sorted lines "name size crc") of a zip."""
    with zipfile.ZipFile(path) as z:
        rows = sorted((i.filename, i.file_size, i.CRC) for i in z.infolist())
    h = hashlib.sha256()
    for name, size, crc in rows:
        h.update(f"{name}\t{size}\t{crc:08x}\n".encode("utf-8"))
    return len(rows), h.hexdigest()


def main(src, dst, reports=None, village_lights=False):
    out_dir = os.path.dirname(os.path.abspath(dst))
    os.makedirs(out_dir, exist_ok=True)
    if reports:
        os.makedirs(reports, exist_ok=True)
    print("in: %s, %d entries, digest %s" % ((os.path.basename(src),) + digest(src)), flush=True)
    cur, t_all = src, time.time()
    for k, name in enumerate(STEPS, 1):
        nxt = dst if k == len(STEPS) else os.path.join(out_dir, f"v28_{k}_{name}.zip")
        cmd = [sys.executable, "-u", os.path.join(HERE, f"patch_{name}.py"), cur, nxt]
        if name == "lamps" and village_lights:
            cmd.append("--village-lights")
        if reports:
            cmd += ["--report", os.path.join(reports, f"{name}_report.json")]
        print(f"\n== {k}/{len(STEPS)} patch_{name}.py", flush=True)
        t = time.time()
        subprocess.run(cmd, check=True, cwd=HERE)
        if cur != src:
            os.remove(cur)
        with zipfile.ZipFile(nxt) as z:
            n = len(z.namelist())
        print("== patch_%s.py: %.0f s, %d entries, %.1f MB" % (name, time.time() - t, n, os.path.getsize(nxt) / 1e6),
              flush=True)
        cur = nxt
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
