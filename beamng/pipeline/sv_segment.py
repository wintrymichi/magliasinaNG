"""Semantic segmentation of the Street View panoramas of the review (v2.2): guard rails, walls, fences,
street lights, signs, buildings, vegetation, road ... (Mask2Former Swin-L trained on Mapillary Vistas,
the model of the original route's segmentation, segment_views.py).

Only the band of each panorama where the roadside is (elevation BAND_TOP to BAND_BOTTOM degrees, all
around) is segmented, at WIDTH px for the 360 degrees: a guard rail 20 m away is still ~5 px high.
Labels go to WORK/sv/seg/<id>.png (uint8, Mapillary class ids), with the band in seg/band.json; the
consumers (sv_guardrails.py, sv_walls.py) project world points into them.
    python sv_segment.py [ids.json]       (default: every downloaded panorama)
Needs torch, torchvision and transformers (CPU is enough: a few seconds per panorama).
"""
import json, os, sys, time
import numpy as np
from PIL import Image

WORK = os.path.join(os.environ.get("MAGLIASO_ROOT") or r"D:\beamng_magliaso", "work")
PANO = os.path.join(WORK, "sv", "pano")
SEG = os.path.join(WORK, "sv", "seg")
MODEL = "facebook/mask2former-swin-large-mapillary-vistas-semantic"
WIDTH = 1280
BAND_TOP, BAND_BOTTOM = 20.0, -40.0          # degrees of elevation
CLASSES = {"curb": 2, "fence": 3, "guard_rail": 4, "barrier": 5, "wall": 6, "road": 13, "sidewalk": 15,
           "building": 17, "terrain": 29, "vegetation": 30, "street_light": 44, "pole": 45, "sign": 50, "car": 55}


def band_rows(H):
    r0 = int(round((90.0 - BAND_TOP) / 180.0 * H))
    r1 = int(round((90.0 - BAND_BOTTOM) / 180.0 * H))
    return r0, r1


def main(ids=None):
    import torch
    from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation
    torch.set_num_threads(int(os.environ.get("SEG_THREADS", "4")))
    bf16 = os.environ.get("SEG_BF16") == "1"
    os.makedirs(SEG, exist_ok=True)
    json.dump({"width": WIDTH, "top": BAND_TOP, "bottom": BAND_BOTTOM, "classes": CLASSES},
              open(os.path.join(SEG, "band.json"), "w"))
    proc = AutoImageProcessor.from_pretrained(MODEL)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(MODEL).eval()
    if ids is None:
        ids = sorted(f[:-4] for f in os.listdir(PANO) if f.endswith(".jpg"))
    todo = [i for i in ids if not os.path.exists(os.path.join(SEG, i + ".png"))
            and os.path.exists(os.path.join(PANO, i + ".jpg"))]
    print(len(todo), "panoramas to segment", flush=True)
    t0 = time.time()
    for k, pid in enumerate(todo):
        img = Image.open(os.path.join(PANO, pid + ".jpg")).convert("RGB")
        W, H = img.size
        r0, r1 = band_rows(H)
        band = img.crop((0, r0, W, r1))
        h = int(round(WIDTH * (r1 - r0) / W))
        band = band.resize((WIDTH, h), Image.BILINEAR)
        with torch.inference_mode():
            inp = proc(images=band, return_tensors="pt", do_resize=False)
            if bf16:                                   # about twice as fast on CPUs with AMX, 96-98 % same labels
                with torch.autocast("cpu", dtype=torch.bfloat16):
                    out = model(**inp)
            else:
                out = model(**inp)
            lab = proc.post_process_semantic_segmentation(out, target_sizes=[(h, WIDTH)])[0].numpy().astype(np.uint8)
        Image.fromarray(lab).save(os.path.join(SEG, pid + ".png"), optimize=True)
        if k % 25 == 0:
            el = time.time() - t0
            print("  %d/%d  %.1f s each, %.1f h left" % (k + 1, len(todo), el / (k + 1), el / (k + 1) * (len(todo) - k - 1) / 3600),
                  flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main(json.load(open(sys.argv[1])) if len(sys.argv) > 1 else None)
