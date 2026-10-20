"""The street photos of one zone fitted to the scene and its facades rectified (v3.0.40): the core of the analysis of
the street photos, run on a development pack (street_devpack.py) or on a zone of the full run.

1. every photo gets its first pose (street_photos.py) and its label map (Mapillary's segmentation);
2. the photos of one sequence of Mapillary's reconstruction are fitted to the scene together (street_pose.fit_group:
   their relative poses hold), each 360 degree panorama alone (street_pose.fit), then every photo once more alone
   from there, with a tight prior;
3. a photo whose fitted pose has not found the buildings of the scene (building_iou, accept) measures nothing;
4. every other photo once over the scene: the roof lines against the sky (street_roofs.py), the street furniture
   (street_objects.py), the votes on the strips that may be hedges (street_hedges.py), the fountains of OSM
   (street_fountains.py) and the facades it shows, resampled onto them; the views of a facade are fused and its
   openings found (street_facades.py, street_openings.py).
Output (out folder): poses.json, roofs.json (roof_columns.json: the columns measured in every photo), objects.json,
hedges.json, fountains.json, facades.json, facades/<key>.jpg (the fused facade; _det.jpg with the openings found), and
the check images: check/<photo>.jpg (the photo with the outlines of the scene's buildings at the fitted pose).
    python street_zone.py <pack folder> <out folder>
"""
import gzip, json, math, os, sys, time
from collections import defaultdict
import numpy as np
from PIL import Image
import street_camera as sc
import street_collect
import street_facades as sf
import street_openings as so
import street_photos
import street_pose as sp
import street_render as sr
import street_scene


def load_pack(d):
    scene = street_scene.load(os.path.join(d, "scene.npz"))
    photos = json.load(open(os.path.join(d, "photos.json")))
    names = os.path.join(d, "seg", "classes.json")
    names = {int(k): v for k, v in json.load(open(names)).items()} if os.path.exists(names) else None
    for p in photos:
        p["img_path"] = os.path.join(d, "photos", f"{p['id']}.jpg")
        f = os.path.join(d, "det", f"{p['id']}.json.gz")
        p["det"] = json.load(gzip.open(f)) if os.path.exists(f) else None
        f = os.path.join(d, "seg", f"{p['id']}.png")
        p["seg"] = f if names and os.path.exists(f) else None
        p["seg_names"] = names
    return scene, photos


def label_map(p, W, H):
    """The labels of a photo: the open model's segmentation (street_segment.py), else Mapillary's."""
    if p.get("seg"):
        import street_segment
        cm = np.asarray(Image.open(p["seg"]))
        lab = street_segment.labels(cm, p["seg_names"])
        if lab.shape != (H, W):
            lab = np.asarray(Image.fromarray(lab).resize((W, H), Image.NEAREST))
        return lab
    if p.get("det"):
        return sp.label_map(p["det"], W, H)
    return None


def groups(photos):
    """Photos fitted together: the perspective photos of one sequence within 60 m of each other (chunks of up to 8)."""
    by = defaultdict(list)
    for p in photos:
        if p["cam"].kind == "equirect" or not p.get("computed"):
            by[("single", p["id"])].append(p)
        else:
            by[("seq", p.get("seq"))].append(p)
    out = []
    for k, v in by.items():
        if k[0] == "single":
            out.append(v)
            continue
        v.sort(key=lambda p: (p.get("date") or "", p["id"]))
        # order along the sequence by position (the catalogue has no capture time per photo)
        xy = np.array([p["cam"].pos[:2] for p in v])
        order = [int(np.argmin(xy[:, 0] + xy[:, 1]))]
        left = set(range(len(v))) - set(order)
        while left:
            last = xy[order[-1]]
            j = min(left, key=lambda i: np.hypot(*(xy[i] - last)))
            order.append(j)
            left.remove(j)
        chunk = []
        for i in order:
            if chunk and (len(chunk) >= 8 or np.hypot(*(xy[i] - chunk[0]["cam"].pos[:2])) > 60):
                out.append(chunk)
                chunk = []
            chunk.append(v[i])
        if chunk:
            out.append(chunk)
    return out


MIN_IOU = 0.45               # agreement of the buildings of a photo and of the scene at its fitted pose to measure with it
RESCUE = (8.0, 25.0)         # m, degrees: the prior of the second fit of a photo whose first did not find the buildings
MIN_BUILDINGS = 0.01         # share of a photo's pixels that are buildings: under it the photo is not fitted
TURN = 12.0                  # degrees: a fit that turns the camera further than the services' compass errors ...
MIN_IOU_TURNED = 0.6         # ... has to agree this well (a wide search finds false matches: a dashcam photo turned 31)


def accept(iou, dheading):
    """Whether a photo measures with its fitted pose: the buildings agree, and better when the fit turned it far."""
    return iou >= MIN_IOU and (abs(dheading) <= TURN or iou >= MIN_IOU_TURNED)


def building_iou(cam, scene_r, lab, label_w=720):
    """Intersection over union of the photo's building pixels and the scene's at the camera's pose (the pixels of the
    labels the scene has), and the photo's share of building pixels: a pose that has not found the buildings (a
    camera on the ground among trees, a photo of a meadow) measures nothing."""
    import street_pose
    lab = street_pose._labels_at(lab, label_w)
    H, W = lab.shape
    pano = sr.render(scene_r, cam.pos, W=2880)
    v, u = np.mgrid[0:H, 0:W]
    d = cam.dirs((u.ravel() + 0.5) * cam.W / W - 0.5, (v.ravel() + 0.5) * cam.H / H - 0.5)
    L = pano.lookup(d)[0].reshape(H, W)
    known = lab != 255
    pb, sb = (lab == sr.BUILDING) & known, (L == sr.BUILDING) & known
    n = (pb | sb).sum()
    return (float((pb & sb).sum() / n) if n else 0.0), float(pb.sum() / max(known.sum(), 1))


def outline_check(p, cam, scene_r, rgb, path, cam0=None, blds=None):
    """The photo with the edges of the scene's labels drawn at the fitted pose (yellow: buildings, cyan: sky line)
    and, thin red, at the first pose; with blds, magenta: the top of the game's building (its mesh) wherever the
    scene shows that building against the sky."""
    import cv2
    h, w = rgb.shape[:2]
    sW = 960
    s = sW / w
    img = cv2.resize(rgb, (sW, int(round(h * s))), interpolation=cv2.INTER_AREA)
    pano = sr.render(scene_r, cam.pos, W=2880)
    for c, col, thick in (((cam0, (255, 40, 40), 1) if cam0 is not None else (None, None, 0)), (cam, None, 2)):
        if c is None:
            continue
        pn = pano if c is cam else sr.render(scene_r, c.pos, W=2880)
        v, u = np.mgrid[0:img.shape[0], 0:img.shape[1]]
        d = c.dirs(u.ravel() / s, v.ravel() / s)
        L, B, _ = pn.lookup(d)
        L = L.reshape(img.shape[:2])
        B = B.reshape(img.shape[:2])
        edge_b = np.zeros(L.shape, bool)
        edge_b[:, 1:] |= B[:, 1:] != B[:, :-1]
        edge_b[1:, :] |= B[1:, :] != B[:-1, :]
        edge_s = np.zeros(L.shape, bool)
        sky = L == sr.SKY
        edge_s[:, 1:] |= sky[:, 1:] != sky[:, :-1]
        edge_s[1:, :] |= sky[1:, :] != sky[:-1, :]
        if thick == 2:
            k = np.ones((2, 2), np.uint8)
            edge_b = cv2.dilate(edge_b.astype(np.uint8), k) > 0
            edge_s = cv2.dilate(edge_s.astype(np.uint8), k) > 0
            img[edge_s] = (40, 230, 255)
            img[edge_b & (B >= 0) | edge_b & np.roll(B >= 0, 1, 0)] = (255, 220, 0)
            if blds is not None:
                import street_roofs
                H, W = L.shape
                tops = {}
                for col_ in range(W):
                    e = np.nonzero(sky[:-1, col_] & (L[1:, col_] == sr.BUILDING))[0]
                    if not len(e) or B[e[0] + 1, col_] < 0:
                        continue
                    bi = int(B[e[0] + 1, col_])
                    if bi not in tops:
                        tops[bi] = street_roofs.mesh_top(cam, blds[bi], W, H)[0]
                    r = tops[bi][col_]
                    if np.isfinite(r) and 0 <= r < H - 1:
                        img[int(round(r)):int(round(r)) + 2, col_] = (255, 40, 255)
        else:
            img[edge_b | edge_s] = col
    Image.fromarray(img).save(path, quality=85)


def record(f, w, ops, cell=0.5, min_weight=0.05, share=0.5):
    """The facade as dati/street_facades.json keeps it (facades.Measured): the plane, the openings and the mask of
    the cells of `cell` m the photos see (at least `share` of the cell's pixels), rows from the top."""
    k = max(1, int(round(cell / sf.RES)))
    h, wd = w.shape
    rows = int(np.ceil(h / k))
    cols = int(np.ceil(wd / k))
    seen = np.zeros((rows, cols), bool)
    good = w > min_weight
    for r in range(rows):
        for c in range(cols):
            blk = good[r * k:(r + 1) * k, c * k:(c + 1) * k]
            seen[r, c] = blk.size > 0 and blk.mean() >= share
    az = float(np.degrees(np.arctan2(f.n[0], f.n[1])) % 360)
    return {"az": round(az, 2), "off": round(float(f.o @ f.n), 3), "u0": round(float(f.u0), 3),
            "z1": round(float(f.z1), 3), "cell": round(k * sf.RES, 4),
            "seen": ["".join("1" if v else "0" for v in row) for row in seen],
            "openings": [o.as_list() for o in ops]}


def contact_sheet(paths, out_path, cols=3, width=640, captions=None):
    """The images side by side in a grid (each width px wide), a caption over each, for the review."""
    from PIL import ImageDraw
    ims = []
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im = im.resize((width, max(1, int(round(im.size[1] * width / im.size[0])))))
        if captions:
            from PIL import ImageFont
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            except OSError:
                font = ImageFont.load_default()
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, width, 24), fill=(0, 0, 0))
            d.text((6, 3), captions[i], fill=(255, 255, 255), font=font)
        ims.append(im)
    if not ims:
        return
    rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
    H = sum(max(im.size[1] for im in r) for r in rows) + 4 * (len(rows) - 1)
    sheet = Image.new("RGB", (cols * width + 4 * (cols - 1), H), (30, 30, 30))
    y = 0
    for r in rows:
        for j, im in enumerate(r):
            sheet.paste(im, (j * (width + 4), y))
        y += max(im.size[1] for im in r) + 4
    sheet.save(out_path, quality=85)


def run(pack, out, limit=None, detect=True, reuse=False):
    """reuse: the poses of an earlier run in out/poses.json are kept (only the photos without one are fitted)."""
    os.makedirs(os.path.join(out, "check"), exist_ok=True)
    os.makedirs(os.path.join(out, "facades"), exist_ok=True)
    os.makedirs(os.path.join(out, "fountains"), exist_ok=True)
    scene, photos = load_pack(pack)
    scene_r = street_scene.scene_of(scene)
    ground = lambda x, y: scene_r.ground(x, y)
    usable, bare = [], 0
    for p in photos[:limit] if limit else photos:
        im = Image.open(p["img_path"])
        W, H = im.size
        lab = label_map(p, W, H)
        r = street_photos.camera_of(p, W, H, ground)
        if r is None or lab is None:
            continue
        if (lab == sr.BUILDING).mean() < MIN_BUILDINGS:     # no building to fit to nor to measure
            bare += 1
            continue
        p["cam0"], p["trust"] = r
        p["cam"] = p["cam0"]
        p["lab"] = lab
        usable.append(p)
    print(len(usable), "photos with a pose and a segmentation of", len(photos), "(%d show no buildings)" % bare,
          flush=True)
    poses = {}
    old = {}
    if reuse and os.path.exists(os.path.join(out, "poses.json")):
        old = json.load(open(os.path.join(out, "poses.json")))
    for grp in groups(usable):
        t0 = time.time()
        if all(p["id"] in old for p in grp):
            for p in grp:
                q = old[p["id"]]
                R = np.array(q["R"]) if "R" in q else sc.attitude(*q["angles"])
                p["cam"] = p["cam0"].copy(pos=np.array(q["pos"], float), R=R)
                iou, share = building_iou(p["cam"], scene_r, p["lab"])
                p["ok"] = accept(iou, q.get("dheading", 0.0))
                poses[p["id"]] = dict(q, iou=round(iou, 3), buildings=round(share, 3), ok=p["ok"])
                print("  %s kept: buildings %.2f iou %.2f%s" % (p["id"], share, iou, "" if p["ok"] else " REJECTED"),
                      flush=True)
                rgb = np.asarray(Image.open(p["img_path"]).convert("RGB"))
                outline_check(p, p["cam"], scene_r, rgb, os.path.join(out, "check", f"{p['id']}.jpg"), cam0=p["cam0"],
                              blds=scene["buildings"])
            continue
        if len(grp) > 1:
            cams, s, log = sp.fit_group([p["cam0"] for p in grp], [p["lab"] for p in grp], scene_r, ground,
                                        prior=grp[0]["trust"]["prior"])
            for p, c in zip(grp, cams):
                p["cam"] = c
        for p in grp:
            F = sp.fit(p["cam"], p["lab"], scene_r, ground, heading_search=p["trust"]["heading_search"] if len(grp) == 1 else 0.0,
                       prior=(1.0, 2.0) if len(grp) > 1 else p["trust"]["prior"])
            iou, share = building_iou(F.cam, scene_r, p["lab"])
            if iou < MIN_IOU:
                # once more alone from the first pose, the compass and the position trusted less (a sequence that
                # held it, a wrong reconstruction)
                F2 = sp.fit(p["cam0"], p["lab"], scene_r, ground, heading_search=RESCUE[1], prior=RESCUE)
                iou2, share2 = building_iou(F2.cam, scene_r, p["lab"])
                if iou2 > iou:
                    F, iou, share = F2, iou2, share2
            p["cam"] = F.cam
            p["fit"] = F
            sh, dz, dh = F.offsets(p["cam0"])
            p["ok"] = accept(iou, dh)
            poses[p["id"]] = {"pos": F.cam.pos.round(3).tolist(), "angles": [round(a, 3) for a in sc.angles_of(F.cam.R)],
                              "R": F.cam.R.round(7).tolist(),
                              "iou": round(iou, 3), "buildings": round(share, 3), "ok": p["ok"],
                              "score": round(F.score, 4), "agreement": round(F.agreement, 4), "shift": round(sh, 2),
                              "dz": round(dz, 2), "dheading": round(dh, 2), "kind": F.cam.kind,
                              "height": round(float(F.cam.pos[2] - ground(F.cam.pos[0], F.cam.pos[1])[0]), 2)}
            print("  %s %s shift %.2f m dz %.2f dheading %.2f score %.3f buildings %.2f iou %.2f%s (%.0fs)" % (
                p["id"], F.cam.kind, sh, dz, dh, F.score, share, iou, "" if p["ok"] else " REJECTED", time.time() - t0),
                flush=True)
            rgb = np.asarray(Image.open(p["img_path"]).convert("RGB"))
            outline_check(p, F.cam, scene_r, rgb, os.path.join(out, "check", f"{p['id']}.jpg"), cam0=p["cam0"],
                          blds=scene["buildings"])
    json.dump(poses, open(os.path.join(out, "poses.json"), "w"), indent=1)
    good = [p for p in usable if p.get("ok", True)]
    print(len(good), "photos found the buildings of the scene", flush=True)
    # every photo once over the scene: the roof lines against the sky, the street furniture, the hedges, the
    # fountains and the facades it shows
    import street_fountains
    import street_hedges
    import street_objects
    import street_roofs
    blds = scene["buildings"]
    allres = defaultdict(list)
    roof_photos = defaultdict(list)                   # per building: the median of every photo that measured it
    roof_cols = {}
    obs, fobs = [], []
    cells = street_hedges.candidates(scene)
    hv = np.zeros((len(cells["x"]), 2), np.int32)
    fpts = street_fountains.points(scene["rect"])
    seen = defaultdict(list)
    fcache = {}
    for p in good:
        pano = sr.render(scene_r, p["cam"].pos, W=2880)
        rgb = np.asarray(Image.open(p["img_path"]).convert("RGB"))
        det = []
        for bi, v in street_roofs.residuals(p["cam"], pano, p["lab"], blds, detail=det).items():
            allres[bi] += v
            roof_photos[bi].append(float(np.median(v)))
        if det:
            roof_cols[p["id"]] = {"size": [p["lab"].shape[1], p["lab"].shape[0]],
                                  "cols": [[blds[b]["uuid"], c, round(rm, 1), rp, round(dz, 2)] for b, c, rm, rp, dz in det]}
        if p.get("seg"):
            cm = np.asarray(Image.open(p["seg"]))
            obs += street_objects.observe(p["cam"], cm, p["seg_names"], ground, p["id"])
            hv += street_hedges.votes(p["cam"], pano, cm, p["seg_names"], cells)
        if detect and fpts:
            fobs += street_fountains.look(p["cam"], pano, rgb, fpts, ground, p["id"], save=os.path.join(out, "fountains"))
        for bi in np.unique(pano.bid[pano.bid >= 0]):
            if bi not in fcache:
                fcache[bi] = sf.facades_of(blds[bi])
            for f in fcache[bi]:
                r = sf.observe(p["cam"], pano, rgb, p["lab"], int(bi), f)
                if r is not None and r[1].max() > 0.05:
                    seen[f.key].append((p["id"], f, r))
    roofs = {blds[bi]["uuid"]: {"dz": round(m, 2), "n": n, "iqr": round(q, 2), "photos": len(roof_photos[bi]),
                                "spread": round(float(np.ptp(roof_photos[bi])), 2)}
             for bi, (m, n, q) in street_roofs.summary(allres).items()}
    json.dump(roofs, open(os.path.join(out, "roofs.json"), "w"), indent=1)
    json.dump(roof_cols, open(os.path.join(out, "roof_columns.json"), "w"))
    print(len(roofs), "roof lines measured;", sum(abs(v["dz"]) > 0.8 for v in roofs.values()), "off by more than 0.8 m",
          flush=True)
    objs = street_objects.cluster(obs)
    json.dump({"observations": obs, "objects": objs}, open(os.path.join(out, "objects.json"), "w"), indent=1)
    print(len(obs), "observations of street furniture,", len(objs), "objects", flush=True)
    hed = street_hedges.verdicts(cells, hv)
    json.dump({"cells": hed}, open(os.path.join(out, "hedges.json"), "w"))
    print(len(cells["x"]), "cells of low strips,", len(hed), "seen:", sum(c[4] > c[5] for c in hed), "hedge,",
          sum(c[5] >= c[4] for c in hed), "not", flush=True)
    fnt = street_fountains.gather(fobs)
    json.dump({"points": [{k: v for k, v in q.items() if k != "tags"} for q in fpts], "observations": fobs,
               "fountains": fnt}, open(os.path.join(out, "fountains.json"), "w"), indent=1)
    print(len(fpts), "fountains of OSM,", sum(1 for v in fnt.values() if v["found"]), "found in the photos", flush=True)
    # the facades
    index = {}
    for key, views in seen.items():
        img, w = sf.fuse([v[2] for v in views])
        name = key.replace("|", "_").replace("{", "").replace("}", "")
        Image.fromarray(img).save(os.path.join(out, "facades", name + ".jpg"), quality=88)
        f = views[0][1]
        cover = float((w > 0.05).mean())
        # the openings of the facades the build may use (street_collect.MIN_COVER): the detector is the slow part
        ops = so.detect(img, w, f.u0, f.z1, sf.RES) if detect and cover >= street_collect.MIN_COVER else []
        if detect:
            Image.fromarray(so.sheet(img, w, ops, f.u0, f.z1, sf.RES)).save(
                os.path.join(out, "facades", name + "_det.jpg"), quality=88)
        index[key] = {"file": name + ".jpg", "photos": [v[0] for v in views], "u0": f.u0, "z1": f.z1, "res": sf.RES,
                      "coverage": round(cover, 3), "size": [img.shape[1], img.shape[0]],
                      "openings": [o.as_list() for o in ops], "record": record(f, w, ops)}
        print("  facade %s: %d views, %.0f%% seen, %d openings" % (key, len(views), 100 * index[key]["coverage"],
                                                                  len(ops)), flush=True)
    json.dump(index, open(os.path.join(out, "facades.json"), "w"), indent=1)
    print(len(index), "facades seen", flush=True)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    run(a[0], a[1], int(a[2]) if len(a) > 2 else None, reuse="--reuse" in sys.argv)
