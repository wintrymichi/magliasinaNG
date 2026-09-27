"""Quantitative photo <-> game agreement at the calibrated Street View poses.

Both images of every validation view (work/validation/photo/<name>.png and the game
screenshot) are segmented with the same Mask2Former (Mapillary Vistas) model; classes
are merged into groups; pixels showing vehicles/people in the photo are ignored.
Reports pixel agreement and per-group IoU per view and overall, ranks the worst
views, and writes a colour-coded comparison sheet for them.
"""
import glob, json, os, sys
import numpy as np
import cv2
import torch
from config import WORK, BEAMNG_USER

os.environ.setdefault("HF_HOME", r"D:\beamng_magliaso\hf")
from transformers import Mask2FormerForUniversalSegmentation

GROUPS = {
    "sky": [27],
    "building": [17, 16, 18],
    "vegetation": [30],
    "road": [13, 7, 8, 9, 10, 11, 14, 15, 23, 24, 36, 41, 43, 2],
    "wall": [6],
    "rail_fence": [4, 3, 5],
    "terrain": [29, 25, 26, 28, 31],
    "pole_sign": [44, 45, 46, 47, 48, 49, 50, 35, 32],
}
IGNORE = [19, 20, 21, 22, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 0, 1]
COLORS = {"sky": (235, 206, 135), "building": (70, 70, 180), "vegetation": (35, 140, 35), "road": (128, 128, 128),
          "wall": (60, 110, 200), "rail_fence": (0, 200, 255), "terrain": (60, 120, 160), "pole_sign": (0, 0, 255)}


def group_map(seg):
    g = np.full(seg.shape, -1, np.int8)
    for k, (name, ids) in enumerate(GROUPS.items()):
        g[np.isin(seg, ids)] = k
    g[np.isin(seg, IGNORE)] = -2
    return g


def segment(model, img_rgb):
    mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1).half() * 255
    std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1).half() * 255
    x = torch.from_numpy(np.ascontiguousarray(img_rgb)).cuda().permute(2, 0, 1)[None].half()
    with torch.no_grad():
        out = model(pixel_values=(x - mean) / std)
        cls = out.class_queries_logits.softmax(-1)[..., :-1]
        masks = torch.nn.functional.interpolate(out.masks_queries_logits.sigmoid(), size=img_rgb.shape[:2],
                                                mode="bilinear", align_corners=False)
        return torch.einsum("bqc,bqhw->bchw", cls, masks).argmax(1)[0].byte().cpu().numpy()


def main(tag="run", vdir=None, shots_dir=None, save_seg=False):
    vdir = vdir or os.path.join(WORK, "validation")
    photos = sorted(glob.glob(os.path.join(vdir, "photo", "*.png")))
    shots_dir = shots_dir or os.path.join(BEAMNG_USER, "screenshots", "magliaso")
    model = Mask2FormerForUniversalSegmentation.from_pretrained(
        "facebook/mask2former-swin-large-mapillary-vistas-semantic").cuda().eval().half()
    rows, per_view = [], {}
    inter = np.zeros(len(GROUPS)); union = np.zeros(len(GROUPS))
    for f in photos:
        name = os.path.splitext(os.path.basename(f))[0]
        gf = os.path.join(shots_dir, name + ".png")
        if not os.path.exists(gf):
            gf = os.path.join(shots_dir, name + ".jpg")
            if not os.path.exists(gf):
                continue
        ph = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB)
        gm = cv2.cvtColor(cv2.resize(cv2.imread(gf), (ph.shape[1], ph.shape[0]), interpolation=cv2.INTER_AREA),
                          cv2.COLOR_BGR2RGB)
        raw_p, raw_g = segment(model, ph), segment(model, gm)
        sp, sg = group_map(raw_p), group_map(raw_g)
        if save_seg:                                   # raw Vistas labels, for the correction step
            for sub, lab in (("seg_photo", raw_p), ("seg_game", raw_g)):
                os.makedirs(os.path.join(vdir, sub), exist_ok=True)
                cv2.imwrite(os.path.join(vdir, sub, name + ".png"), lab)
        valid = (sp != -2) & (sg != -2)
        agree = float(((sp == sg) & valid).sum() / max(valid.sum(), 1))
        ious = {}
        for k, gname in enumerate(GROUPS):
            a, b = (sp == k) & valid, (sg == k) & valid
            i, u = (a & b).sum(), (a | b).sum()
            inter[k] += i; union[k] += u
            if u > 500:
                ious[gname] = round(float(i / u), 3)
        per_view[name] = {"agreement": round(agree, 3), "iou": ious}
        rows.append((agree, name, ph, gm, sp, sg))
        rows.sort(key=lambda r: r[0])
        del rows[6:]                                   # keep the images of the six worst views only
    overall = {g: round(float(inter[k] / max(union[k], 1)), 3) for k, g in enumerate(GROUPS)}
    mean_agree = float(np.mean([v["agreement"] for v in per_view.values()])) if per_view else 0
    res = {"tag": tag, "views": len(per_view), "mean_pixel_agreement": round(mean_agree, 3),
           "iou_overall": overall, "per_view": per_view}
    json.dump(res, open(os.path.join(vdir, f"metrics_{tag}.json"), "w"), indent=1)
    print("views", len(per_view), "mean pixel agreement %.3f" % mean_agree)
    print("IoU per group:", overall)
    rows.sort(key=lambda r: r[0])
    worst = rows[:6]
    tiles = []
    for agree, name, ph, gm, sp, sg in worst:
        def colorize(g):
            out = np.zeros((*g.shape, 3), np.uint8)
            for k, gname in enumerate(GROUPS):
                out[g == k] = COLORS[gname]
            return out
        row = np.concatenate([ph, gm, colorize(sp)[..., ::-1], colorize(sg)[..., ::-1]], 1)
        row = cv2.resize(row, None, fx=0.35, fy=0.35)
        cv2.putText(row, f"{name} agree {agree:.2f}", (8, 22), 0, 0.6, (255, 255, 0), 2)
        tiles.append(row)
    if tiles:
        cv2.imwrite(os.path.join(vdir, f"worst_{tag}.jpg"),
                    cv2.cvtColor(np.concatenate(tiles, 0), cv2.COLOR_RGB2BGR))
    print("worst views:", [(r[1], round(r[0], 3)) for r in worst])


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "run"
    if len(sys.argv) > 2 and sys.argv[2] == "full":
        main(tag, os.path.join(WORK, "validation_full"), os.path.join(WORK, "validation_full", "game"), save_seg=True)
    else:
        main(tag)
