"""Windows, doors, shop fronts, garage doors and balconies on the facades seen in the street photos (v3.0.40).

The rectified facades of street_facades.py (u along the wall, z up, RES m per pixel) go through an open-vocabulary
detector (Grounding DINO, the tiny Swin-T model: a phrase per kind of opening); its boxes become openings in the
facade's own metres. A facade is a grid: the openings are then grouped in rows (floors) and columns (bays), and an
opening seen on part of a row or a column but hidden elsewhere (a tree, a car, the edge of the photo) is not made up:
only what the photos show counts, with the rows and columns as the frame the layout of facades.py fits them to.

The detector: the transformers model IDEA-Research/grounding-dino-tiny (on GitHub Actions), or the same weights
converted from the original checkpoint of the GitHub release (STREET_DINO: a folder with config.json,
model.safetensors and the processor; for a computer that cannot reach Hugging Face).

    detect(img, weight, u0, z1, res) -> [Opening]
    grid(openings) -> floors, columns
"""
import os
import numpy as np

MODEL = os.environ.get("STREET_DINO", "IDEA-Research/grounding-dino-tiny")
# phrase -> kind; the detector's text: the phrases joined by " . "
PHRASES = {"window": "window", "door": "door", "garage door": "garage", "shop window": "shop",
           "balcony": "balcony"}
BOX_THR = 0.30
TEXT_THR = 0.25
SIZES = {                      # kind: (least width, most width, least height, most height) in m
    "window": (0.35, 3.2, 0.45, 3.0),
    "door": (0.7, 2.6, 1.7, 3.2),
    "garage": (2.0, 6.0, 1.8, 3.4),
    "shop": (1.2, 9.0, 1.6, 4.0),
    "balcony": (0.9, 12.0, 0.6, 2.2),
}
SEEN = 0.6                     # share of an opening's box the photos must show (the rest: hidden, out of frame)

_model = None


class Opening:
    def __init__(self, kind, u0, u1, z0, z1, score):
        self.kind, self.u0, self.u1, self.z0, self.z1, self.score = kind, u0, u1, z0, z1, score

    @property
    def uc(self):
        return 0.5 * (self.u0 + self.u1)

    @property
    def w(self):
        return self.u1 - self.u0

    @property
    def h(self):
        return self.z1 - self.z0

    def as_list(self):
        return [self.kind] + [round(float(v), 2) for v in (self.u0, self.u1, self.z0, self.z1)] + \
            [round(float(self.score), 3)]


def model():
    global _model
    if _model is None:
        import torch
        from transformers import GroundingDinoForObjectDetection, GroundingDinoProcessor
        # STREET_THREADS: fewer threads when several zones run side by side on one computer
        torch.set_num_threads(int(os.environ.get("STREET_THREADS", 0)) or max(1, (os.cpu_count() or 2)))
        proc = GroundingDinoProcessor.from_pretrained(MODEL)
        net = GroundingDinoForObjectDetection.from_pretrained(MODEL).eval()
        _model = (proc, net)
    return _model


def _raw(img, phrases=tuple(PHRASES)):
    """Boxes (x0, y0, x1, y1 pixels), scores and phrases the detector finds in an RGB image."""
    import torch
    from PIL import Image
    proc, net = model()
    im = Image.fromarray(img)
    text = " . ".join(phrases) + " ."
    inp = proc(images=im, text=text, return_tensors="pt")
    with torch.no_grad():
        out = net(**inp)
    r = proc.post_process_grounded_object_detection(out, inp.input_ids, threshold=BOX_THR, text_threshold=TEXT_THR,
                                                    target_sizes=[im.size[::-1]])[0]
    labels = r.get("text_labels", r.get("labels"))
    return [(np.asarray(b, float), float(s), str(l)) for b, s, l in zip(r["boxes"], r["scores"], labels)]


def _kind(label):
    """The kind of the phrase the detector names (it may join phrases: 'window door')."""
    label = label.strip().lower()
    if label in PHRASES:
        return PHRASES[label]
    for p in sorted(PHRASES, key=len, reverse=True):
        if p in label:
            return PHRASES[p]
    return None


def _iou(a, b):
    w = min(a.u1, b.u1) - max(a.u0, b.u0)
    h = min(a.z1, b.z1) - max(a.z0, b.z0)
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / (a.w * a.h + b.w * b.h - i)


def detect(img, weight, u0, z1, res, min_weight=0.02):
    """The openings of a rectified facade: img (h, w, 3) uint8 with its weight (the detail the photos give, 0 where no
    photo sees the wall); pixel (row, col) is the point u = u0 + (col + 0.5) res, z = z1 - (row + 0.5) res."""
    seen = weight > min_weight
    if seen.mean() < 0.05:
        return []
    out = []
    for box, s, label in _raw(img):
        kind = _kind(label)
        if kind is None:
            continue
        x0, y0, x1, y1 = box
        c0, c1 = int(max(0, np.floor(x0))), int(min(img.shape[1], np.ceil(x1)))
        r0, r1 = int(max(0, np.floor(y0))), int(min(img.shape[0], np.ceil(y1)))
        if c1 <= c0 or r1 <= r0 or seen[r0:r1, c0:c1].mean() < SEEN:
            continue
        o = Opening(kind, u0 + x0 * res, u0 + x1 * res, z1 - y1 * res, z1 - y0 * res, s)
        lo_w, hi_w, lo_h, hi_h = SIZES[kind]
        if not (lo_w <= o.w <= hi_w and lo_h <= o.h <= hi_h):
            continue
        out.append(o)
    # one opening per place: the best box of overlapping ones (a window found as window and as door)
    out.sort(key=lambda o: -o.score)
    keep = []
    for o in out:
        if all(_iou(o, k) < 0.5 for k in keep):
            keep.append(o)
    return keep


def grid(openings, tol=0.35):
    """Rows and columns of the windows of a facade: the floors as (z bottom, z top) of their windows, the columns as
    their u centres (an opening joins a row whose bottom and top are within tol m, a column within tol m)."""
    wins = [o for o in openings if o.kind in ("window", "door", "shop", "garage")]
    rows = []
    for o in sorted(wins, key=lambda o: o.z0):
        for r in rows:
            if abs(np.median([x.z1 for x in r]) - o.z1) < tol and o.kind == "window" and r[0].kind == "window":
                r.append(o)
                break
        else:
            rows.append([o])
    floors = [(float(np.median([x.z0 for x in r])), float(np.median([x.z1 for x in r])), len(r)) for r in rows]
    cols = []
    for o in sorted(wins, key=lambda o: o.uc):
        for c in cols:
            if abs(np.median([x.uc for x in c]) - o.uc) < tol:
                c.append(o)
                break
        else:
            cols.append([o])
    columns = [(float(np.median([x.uc for x in c])), len(c)) for c in cols]
    return floors, columns


COLORS = {"window": (0, 200, 255), "door": (255, 80, 40), "garage": (255, 200, 0), "shop": (200, 60, 255),
          "balcony": (60, 255, 90)}


def sheet(img, weight, openings, u0, z1, res, scale=2, min_weight=0.02):
    """The rectified facade with the openings found drawn on it (the parts no photo shows hatched), for the review."""
    import cv2
    h, w = img.shape[:2]
    out = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    unseen = cv2.resize((weight <= min_weight).astype(np.uint8), (w * scale, h * scale),
                        interpolation=cv2.INTER_NEAREST) > 0
    yy, xx = np.mgrid[0:h * scale, 0:w * scale]
    hatch = ((xx + yy) // 6) % 2 == 0
    out[unseen] = np.where(hatch[unseen][:, None], [70, 70, 70], [110, 110, 110]).astype(np.uint8)
    for o in openings:
        x0 = int(round((o.u0 - u0) / res * scale))
        x1 = int(round((o.u1 - u0) / res * scale))
        y0 = int(round((z1 - o.z1) / res * scale))
        y1 = int(round((z1 - o.z0) / res * scale))
        cv2.rectangle(out, (x0, y0), (x1, y1), COLORS.get(o.kind, (255, 255, 255)), 2)
    return out
