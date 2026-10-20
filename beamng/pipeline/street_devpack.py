"""A development pack of one zone for the analysis of the street photos (v3.0.40): what the cloud session that writes
the analysis needs and cannot download itself (it reaches neither Mapillary nor swisstopo). Run by the street
reference workflow; it commits the pack to beamng/verifica/street/devpack/<zone>/ on the development branch only:
- scene.npz + scene_buildings.pkl.gz: the 3D scene of the zone (street_scene.py);
- photos/<id>.jpg: up to N photos of the zone that see buildings (the 2048 px copies, JPEG), photos.json: their
  catalogue entries (pose, camera), det/<id>.json.gz: Mapillary's segmentation of each (when the graph API serves it),
  seg/<id>.png: the classes of Mapillary Vistas of every pixel by the open model of street_segment.py (and
  seg/classes.json, their names);
- ATTRIBUTION.md: the photos are CC BY-SA 4.0 (Mapillary contributors, Panoramax contributors).
    python street_devpack.py name x0 y0 x1 y1 [N]
"""
import gzip, io, json, os, shutil, sys
from collections import defaultdict
import numpy as np
from PIL import Image
import street_fetch, street_scene

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "verifica", "street", "devpack")


def spread(photos, n):
    """Up to n photos spread over their sequences, every k-th along each one."""
    by_seq = defaultdict(list)
    for p in photos:
        by_seq[p.get("seq") or p.get("collection") or p["id"]].append(p)
    for v in by_seq.values():
        v.sort(key=lambda p: (p.get("date") or "", p["id"]))
    ranked = sorted(by_seq.values(), key=lambda v: -len(v))
    quota = max(1, n // max(1, len(ranked)))
    out, ids = [], set()
    for v in ranked:
        idx = np.linspace(0, len(v) - 1, min(len(v), quota)).round().astype(int)
        for i in sorted(set(idx)):
            out.append(v[i])
            ids.add(v[i]["id"])
    out += [p for v in ranked for p in v if p["id"] not in ids][: max(0, n - len(out))]
    return out[:n]


def pick(photos, n):
    """Up to n photos: half of them 360 degree panoramas where the zone has them (they see every facade around)."""
    panos = [p for p in photos if p.get("pano")]
    flat = [p for p in photos if not p.get("pano")]
    a = spread(panos, min(len(panos), n // 2))
    return a + spread(flat, n - len(a))


def main(name, rect, n=40, seg=True):
    x0, y0, x1, y1 = rect
    cat = street_fetch.catalog()
    inside = [p for p in cat if x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1 and p["src"] in ("mapillary", "panoramax")]
    near = street_fetch.near_buildings(inside)
    sel = pick(near, n)
    print(name, "photos in the zone", len(inside), "near buildings", len(near), "picked", len(sel), flush=True)
    d = os.path.join(OUT, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "photos"))
    os.makedirs(os.path.join(d, "det"))
    os.makedirs(os.path.join(d, "seg"))
    kept = []
    # spare photos for the ones that cannot be downloaded (the graph API of Mapillary fails at times)
    ids = {p["id"] for p in sel}
    spare = [p for p in pick(near, 3 * n) if p["id"] not in ids]
    for p in sel + spare:
        if len(kept) >= n:
            break
        pid, st = street_fetch.fetch(p, "sd")
        if st not in ("ok", "skip"):
            print("  ", pid, st, flush=True)
            continue
        im = Image.open(street_fetch.path_of(p)).convert("RGB")
        p = dict(p, img_size=list(im.size))
        if max(im.size) > 2048:
            im.thumbnail((2048, 2048), Image.LANCZOS)
        im.save(os.path.join(d, "photos", f"{p['id']}.jpg"), quality=82)
        if seg:
            import street_segment
            Image.fromarray(street_segment.segment(np.asarray(im))).save(os.path.join(d, "seg", f"{p['id']}.png"))
        det = street_fetch.detections(p)
        if det is not None:
            with gzip.open(os.path.join(d, "det", f"{p['id']}.json.gz"), "wt", encoding="utf-8") as f:
                json.dump(det, f, separators=(",", ":"))
        kept.append(p)
    json.dump(kept, open(os.path.join(d, "photos.json"), "w"), indent=0)
    if seg:
        import street_segment
        json.dump(street_segment.classes(), open(os.path.join(d, "seg", "classes.json"), "w"), indent=0)
    sc = street_scene.build(rect)
    street_scene.save(sc, os.path.join(d, "scene.npz"))
    creators = sorted({str(p.get("creator") or p.get("producer") or "?") for p in kept})
    with open(os.path.join(d, "ATTRIBUTION.md"), "w") as f:
        f.write("# Photos of this folder\n\nStreet-level photos from Mapillary (www.mapillary.com) and Panoramax "
                "(panoramax.fr), licensed CC BY-SA 4.0 by their contributors (Mapillary creator ids / Panoramax "
                "producers: %s). Reduced copies for the development of the analysis on the development branch only; "
                "they are not part of the level.\n" % ", ".join(creators))
    print(name, "pack", len(kept), "photos", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], [float(v) for v in a[1:5]], int(a[5]) if len(a) > 5 else 40)
