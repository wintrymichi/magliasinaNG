"""The review images of the street reference (v3.0.40), the renders the step is judged by:

- for every facade the photos of a zone measured: the photos rectified onto it with the openings found, the facade as
  a built level draws it (the released v3.0) and the facade the layout makes with the measurements, side by side at
  one scale (street_elevation.py);
- the photos with the outlines of the model at the first and at the fitted pose (the check images of street_zone.py)
  on contact sheets;
- for every roof the photos measured: crops of the photos with the top of the game's building and the photo's roof
  line (roof_review).

The layout runs as buildings_mesh.build runs it for one building, with what is at hand outside a build: the register
of dati/gwr_area.json.gz by its reference points, the roads and the shops of OSM (the extracts in dati), the shutters
seen in the panoramas (dati/facade_colors.json); a block of several houses of the cadastral survey is one house here.
Every facade is also laid out without the measurements and compared with the level's (agree: the share of the
openings of either drawn on both), which tells where the reconstruction is not the level's.

    python street_review.py <pack folder> <zone result folder> <level folder> <out folder> [zone name]
"""
import glob, gzip, json, math, os, sys
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont

import buildings_mesh
import facades
import osm
import street_elevation as se
import street_facades as sf
import street_scene

DATI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati")
MAIN = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
        "secondary_link", "tertiary", "tertiary_link"}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SIDES = ("nord", "nord-est", "est", "sud-est", "sud", "sud-ovest", "ovest", "nord-ovest")


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def streets(step=2.0):
    """(cKDTree of stations every step m along the roads of OSM, main road per station), as buildings_mesh.street_index
    gives them from the network in a build."""
    from scipy.spatial import cKDTree
    ways, _ = osm.load()
    pts, main = [], []
    for w in ways:
        h = w["tags"].get("highway")
        if h not in osm.DRIVE or h == "track":
            continue
        for s in np.arange(0.0, w["line"].length + 1e-6, step):
            p = w["line"].interpolate(s)
            pts.append((p.x, p.y))
            main.append(h in MAIN)
    return cKDTree(np.array(pts)), np.array(main, bool)


def register(blds, fps):
    """{uuid: record of the register}: the reference points within 2 m of a footprint, several in one footprint
    merged as facades.gwr_join merges them (most floors, oldest year)."""
    recs = [r for r in json.load(gzip.open(os.path.join(DATI, "gwr_area.json.gz"), "rt", encoding="utf-8"))["buildings"]
            if r.get("gstat", 1004) in (1004, 1003, 1005)]
    pts = shapely.points([r["x"] for r in recs], [r["y"] for r in recs])
    hit_p, hit_b = shapely.STRtree(fps).query(pts, predicate="dwithin", distance=2.0)
    best = {}
    for p, bi in zip(hit_p, hit_b):
        d = shapely.distance(fps[bi], pts[p])
        if p not in best or d < best[p][0]:
            best[p] = (d, bi)
    out = {}
    for p, (d, bi) in best.items():
        uid, r = blds[bi]["uuid"], recs[p]
        if uid not in out:
            out[uid] = dict(r)
            continue
        o = out[uid]
        o["gastw"] = max(o.get("gastw", 0), r.get("gastw", 0)) or o.get("gastw")
        for k in ("gbauj", "gbaup"):
            if k in r:
                o[k] = min(o.get(k, 99999), r[k])
    return out


def shops(blds, fps):
    """The buildings with a shop, bar, office ... of OSM (within buildings_mesh.SHOP_NEAR m)."""
    pts = [(x, y) for x, y, k in osm.pois() if facades.shop_front(k)]
    if not pts:
        return set()
    _, hit_b = shapely.STRtree(fps).query(shapely.points(pts), predicate="dwithin", distance=buildings_mesh.SHOP_NEAR)
    return {blds[i]["uuid"] for i in hit_b}


def layout(b, style, ctx, index, records):
    """The facades.Emitter of the layout of one building, with its measured facades (records) or without (None)."""
    keep = facades._street
    facades._street = {b["uuid"]: {"facades": records}} if records else {}
    try:
        em = facades.Emitter(index)
        facades.layout_building(b, buildings_mesh.orient(b)["walls"], style, ctx, em)
    finally:
        facades._street = keep
    return em


def openings_mask(img, tone, tol=14.0):
    """The pixels of an elevation that are not the plain wall (openings, plinth, balconies)."""
    return np.abs(img.astype(np.float32) - np.asarray(tone, np.float32)[None, None] * 0.92).max(-1) > tol


def agree(a, b):
    """Share of the pixels of the openings of either elevation drawn on both (1: the same layout)."""
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def triptych(panels, title, width=1800):
    """Images of one height side by side under their captions, a title over them, scaled to width px."""
    gap, cap, head = 14, 34, 40
    h = max(p.shape[0] for p, _ in panels)
    w = sum(p.shape[1] for p, _ in panels) + gap * (len(panels) - 1)
    s = min(1.0, (width - 2 * gap) / w)
    ims = [(Image.fromarray(p).resize((max(1, int(p.shape[1] * s)), max(1, int(p.shape[0] * s)))), t) for p, t in panels]
    H = int(h * s)
    out = Image.new("RGB", (width, head + cap + H + gap), (24, 24, 24))
    d = ImageDraw.Draw(out)
    d.text((gap, 8), title, fill=(240, 240, 240), font=font(22))
    x = gap
    for im, t in ims:
        d.text((x, head + 4), t, fill=(200, 200, 200), font=font(18))
        out.paste(im, (x, head + cap))
        x += im.size[0] + gap
    return out


def stack(images, path, gap=6):
    W = max(im.size[0] for im in images)
    out = Image.new("RGB", (W, sum(im.size[1] for im in images) + gap * (len(images) - 1)), (12, 12, 12))
    y = 0
    for im in images:
        out.paste(im, (0, y))
        y += im.size[1] + gap
    out.save(path, quality=86)


def review(pack, res_dir, lv, out, zone="", atlas_dir=None, per_sheet=4, least_cover=0.25):
    os.makedirs(out, exist_ok=True)
    atlas_dir = atlas_dir or se.ATLAS or os.path.join(lv, "art", "shapes", "buildings")
    index = json.load(open(os.path.join(atlas_dir, "bld_openings.json")))["modules"]
    scene = street_scene.load(os.path.join(pack, "scene.npz"))
    blds = scene["buildings"]
    scene_r = street_scene.scene_of(scene)
    fps = [buildings_mesh.footprint(b) for b in blds]
    ctx = facades.Context(blds, fps, lambda x, y: scene_r.ground(np.atleast_1d(np.asarray(x, float)),
                                                                 np.atleast_1d(np.asarray(y, float))), streets())
    gwr = register(blds, fps)
    with_shop = shops(blds, fps)
    sv = json.load(open(facades.FACADE_COLORS)) if os.path.exists(facades.FACADE_COLORS) else {}
    meas = json.load(open(os.path.join(res_dir, "facades.json")))
    by_uuid = {}
    for key, v in meas.items():
        by_uuid.setdefault(key.split("|")[0], []).append((key, v))
    pos = {b["uuid"]: i for i, b in enumerate(blds)}
    rows, stats = [], []
    for uid, items in by_uuid.items():
        if uid not in pos:
            continue
        b = blds[pos[uid]]
        fs = {f.key: f for f in sf.facades_of(b)}
        s = sv.get(uid, {})
        style = facades.style_of(b, gwr.get(uid, {}), fps[pos[uid]].area, float(b["bbox"][1][2] - b["bbox"][0][2]),
                                 None, shutter=(s["shutter"], s.get("shutter_frac", 0.0)) if s.get("shutter") else None,
                                 shop=uid in with_shop)
        records = [v["record"] for _, v in items if v.get("record")]
        em0 = layout(b, style, ctx, index, None)
        em1 = layout(b, style, ctx, index, records)
        for key, v in items:
            f = fs.get(key)
            if f is None or v["coverage"] < least_cover:
                continue
            game, tone = se.level(f, lv, atlas_dir)
            rec0 = se.emitted(f, em0, tone, atlas_dir)
            new = se.emitted(f, em1, tone, atlas_dir)
            det = os.path.join(res_dir, "facades", v["file"].replace(".jpg", "_det.jpg"))
            if not os.path.exists(det):
                det = os.path.join(res_dir, "facades", v["file"])
            photo = np.asarray(Image.open(det).convert("RGB").resize((game.shape[1], game.shape[0])))
            a = agree(openings_mask(game, tone), openings_mask(rec0, tone))
            n_ops = len(v["openings"])
            side = SIDES[int(round(float(key.split("|")[1]) / 45.0)) % 8]
            title = "%s  facciata verso %s, %d m: %d foto, vista al %d%%, %d aperture trovate" % (
                zone, side, round(f.u1 - f.u0), len(v["photos"]), round(100 * v["coverage"]), n_ops)
            # the layout rebuilt here without the photos next to the one with them: their difference is the photos'
            # alone (the rebuild differs from the released level where the code changed since v3.0)
            panels = [(photo, "Foto raddrizzate (blu finestre, rosso porte)"), (game, "Gioco v3.0 oggi"),
                      (rec0, "Nuovo build senza foto"), (new, "Nuovo build con le foto")]
            im = triptych(panels, title.strip())
            name = v["file"].replace(".jpg", "")
            im.save(os.path.join(out, f"facciata_{name}.jpg"), quality=88)
            rows.append((v["coverage"] * min(n_ops, 8), im, name))
            stats.append({"key": key, "coverage": v["coverage"], "openings": n_ops, "agree_rebuilt": round(a, 3),
                          "photos": len(v["photos"]), "use": style["use"], "family": style["family"]})
            print("  %s cover %.2f openings %d agreement of the rebuilt layout with the level %.2f" % (
                key, v["coverage"], n_ops, a), flush=True)
    rows.sort(key=lambda r: -r[0])
    sheets = []
    for k in range(0, len(rows), per_sheet):
        p = os.path.join(out, "facciate_%s_%02d.jpg" % (zone or "zona", k // per_sheet + 1))
        stack([r[1] for r in rows[k:k + per_sheet]], p)
        sheets.append(p)
    # the photos with the outlines of the model at the fitted pose
    import street_zone
    checks = sorted(glob.glob(os.path.join(res_dir, "check", "*.jpg")))
    poses = json.load(open(os.path.join(res_dir, "poses.json"))) if os.path.exists(os.path.join(res_dir, "poses.json")) else {}

    def caption(path):
        q = poses.get(os.path.basename(path)[:-4], {})
        if "iou" not in q:
            return "%s" % q.get("kind", "")
        return "%s  spostata %.1f m  edifici %.0f%%  %s" % ("360" if q.get("kind") == "equirect" else "foto", q["shift"],
                                                         100 * q["iou"], "ok" if q.get("ok") else "SCARTATA")
    for k in range(0, len(checks), 9):
        p = os.path.join(out, "allineamento_%s_%02d.jpg" % (zone or "zona", k // 9 + 1))
        part = checks[k:k + 9]
        street_zone.contact_sheet(part, p, cols=3, width=640, captions=[caption(c) for c in part])
        sheets.append(p)
    json.dump(stats, open(os.path.join(out, "review.json"), "w"), indent=1)
    return sheets, stats


def roof_review(pack, res_dir, out, zone="", per_sheet=4, views=2, height=300):
    """Crops of the photos where the roof line of a building was measured: magenta the top of the game's building (its
    mesh), green the photo's roof line, per building with what the build does with it (street_collect)."""
    import street_collect
    import street_zone
    f = os.path.join(res_dir, "roof_columns.json")
    if not os.path.exists(f):
        return []
    roofs = json.load(open(os.path.join(res_dir, "roofs.json")))
    cols = json.load(open(f))
    paths = {p["id"]: p["img_path"] for p in street_zone.load_pack(pack)[1]}
    by = {}
    for pid, v in cols.items():
        per = {}
        for uid, c, rm, rp, dz in v["cols"]:
            per.setdefault(uid, []).append((c, rm, rp, dz))
        for uid, lst in per.items():
            by.setdefault(uid, []).append((pid, v["size"], lst))
    rows = []
    for uid, r in sorted(roofs.items(), key=lambda kv: -abs(kv[1]["dz"])):
        if r["n"] < street_collect.ROOF_N:
            continue
        crops = []
        for pid, (W, H), lst in sorted(by.get(uid, []), key=lambda t: -len(t[2]))[:views]:
            c = np.array([q[0] for q in lst], float)
            if c.max() - c.min() > W / 2:                       # across the seam of a panorama
                continue
            rr = np.array([[q[1], q[2]] for q in lst], float)
            im = Image.open(paths[pid]).convert("RGB")
            s = im.size[0] / W
            pad = max(30.0, 0.25 * (c.max() - c.min()))
            x0, x1 = max(0, (c.min() - pad) * s), min(im.size[0], (c.max() + pad) * s)
            y0, y1 = max(0, (rr.min() - pad) * s), min(im.size[1], (rr.max() + pad) * s)
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            k = height / (y1 - y0)
            crop = im.crop((int(x0), int(y0), int(x1), int(y1))).resize((max(1, int((x1 - x0) * k)), height))
            d = ImageDraw.Draw(crop)
            for cc, rm, rp, dz in lst:
                u = ((cc + 0.5) * s - x0) * k
                for row, col in ((rm, (255, 40, 255)), (rp, (40, 255, 80))):
                    v = ((row + 0.5) * s - y0) * k
                    d.ellipse((u - 3, v - 3, u + 3, v + 3), fill=col)
            crops.append((np.asarray(crop), "foto %s" % pid))
        if not crops:
            continue
        if abs(r["dz"]) < street_collect.ROOF_MIN:
            verdict = "uguale entro %.1f m: resta com'e'" % street_collect.ROOF_MIN
        elif r["iqr"] > street_collect.ROOF_IQR:
            verdict = "misura incerta (le colonne non concordano): resta com'e'"
        elif r.get("photos", 0) < street_collect.ROOF_PHOTOS:
            verdict = "una foto sola: resta com'e'"
        elif r.get("spread", 0.0) > street_collect.ROOF_IQR:
            verdict = "le foto non concordano: resta com'e'"
        else:
            verdict = "il build lo %s di %.1f m" % ("alza" if r["dz"] > 0 else "abbassa", abs(r["dz"]))
        title = "%s  tetto: foto %+.2f m rispetto al gioco, %d foto, %d colonne -> %s" % (
            zone, r["dz"], r.get("photos", 1), r["n"], verdict)
        rows.append(triptych(crops, title.strip()))
    sheets = []
    for k in range(0, len(rows), per_sheet):
        p = os.path.join(out, "tetti_%s_%02d.jpg" % (zone or "zona", k // per_sheet + 1))
        stack(rows[k:k + per_sheet], p)
        sheets.append(p)
    return sheets


if __name__ == "__main__":
    a = sys.argv[1:]
    review(a[0], a[1], a[2], a[3], a[4] if len(a) > 4 else "")
    roof_review(a[0], a[1], a[3], a[4] if len(a) > 4 else "")
