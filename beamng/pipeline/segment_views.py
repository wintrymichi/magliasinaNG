"""Semantic segmentation (Mask2Former Swin-L, Mapillary Vistas, 65 classes) of the
Street View perspective views at native resolution on the GPU.

Input : dataset viste/ (1600x1200, FOV 90, known pose)
Output: work/seg/<view>.png  (uint8 class id per pixel, lossless)
Views: all p00 (horizon) and p25 (up) views of every panorama.
"""
import os, sys, time
import numpy as np
import torch
from PIL import Image
from config import DATASET, WORK

os.environ.setdefault("HF_HOME", r"D:\beamng_magliaso\hf")
from transformers import Mask2FormerForUniversalSegmentation

NAME = "facebook/mask2former-swin-large-mapillary-vistas-semantic"
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1) * 255
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1) * 255


def main():
    out_dir = os.path.join(WORK, "seg")
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(os.path.join(DATASET, "viste")) if f.endswith(".jpg"))
    todo = [f for f in files if not os.path.exists(os.path.join(out_dir, f[:-4] + ".png"))]
    print(len(files), "views,", len(todo), "to do", flush=True)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(NAME).cuda().eval().half()
    mean, std = MEAN.cuda().half(), STD.cuda().half()
    t0 = time.time()
    for k, f in enumerate(todo):
        img = np.asarray(Image.open(os.path.join(DATASET, "viste", f)).convert("RGB"))
        x = torch.from_numpy(img).cuda().permute(2, 0, 1)[None].half()
        x = (x - mean) / std
        with torch.no_grad():
            out = model(pixel_values=x)
            cls = out.class_queries_logits.softmax(-1)[..., :-1]          # (1, Q, C)
            masks = out.masks_queries_logits.sigmoid()                     # (1, Q, h, w)
            masks = torch.nn.functional.interpolate(masks, size=img.shape[:2], mode="bilinear",
                                                    align_corners=False)
            seg = torch.einsum("bqc,bqhw->bchw", cls, masks).argmax(1)[0].byte().cpu().numpy()
        Image.fromarray(seg).save(os.path.join(out_dir, f[:-4] + ".png"), optimize=False)
        if k % 100 == 0:
            el = time.time() - t0
            print(f"{k}/{len(todo)} {el / (k + 1):.2f}s/img", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
