"""The segmentation of the street photos with an open model (v3.0.40): every pixel one of the 65 classes of Mapillary
Vistas (building, sky, vegetation, road, car, pole, bench ...), Mask2Former (Swin-L) trained on Vistas, the street-level
photos of Mapillary itself. It runs where the photos are downloaded (GitHub Actions); what it writes is a class map
per photo (PNG of class ids) and the names of the classes.

Mapillary's own segmentation of a photo (street_fetch.detections) holds the same classes, but the graph API that
serves it fails for hours at times and has none for Panoramax: this one is always there.

    segment(rgb) -> (H, W) uint8 class ids;  CLASSES: id -> name (e.g. "Building")
    labels(classmap, names) -> (H, W) uint8 of street_render's labels (sky, ground, vegetation, building; 255 other)
    python street_segment.py <photo.jpg> <out.png>
"""
import os, sys
import numpy as np

MODEL = os.environ.get("STREET_SEG", "facebook/mask2former-swin-large-mapillary-vistas-semantic")
SHORT = 1024                  # px of the shorter side the model sees (a 360 degree panorama: 1024 x 2048)
_model = None

# Vistas class names -> labels of the scene (street_render: 0 sky, 1 ground, 2 vegetation, 3 building)
SKY_N = ("sky",)
BUILDING_N = ("building",)
VEG_N = ("vegetation",)
GROUND_N = ("terrain", "road", "sidewalk", "parking", "bike lane", "crosswalk - plain", "curb cut", "pedestrian area",
            "rail track", "service lane", "lane marking - crosswalk", "lane marking - general", "manhole", "pothole",
            "catch basin", "sand", "snow", "water", "mountain", "curb")


def model():
    global _model
    if _model is None:
        import torch
        from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation
        torch.set_num_threads(max(1, os.cpu_count() or 2))
        proc = AutoImageProcessor.from_pretrained(MODEL)
        net = Mask2FormerForUniversalSegmentation.from_pretrained(MODEL).eval()
        _model = (proc, net)
    return _model


def classes():
    """id -> class name of the model."""
    _, net = model()
    return {int(k): v for k, v in net.config.id2label.items()}


def segment(rgb):
    """(H, W) uint8 class ids of an RGB photo (H, W, 3)."""
    import torch
    from PIL import Image
    proc, net = model()
    h, w = rgb.shape[:2]
    s = SHORT / min(h, w)
    im = Image.fromarray(rgb)
    if s < 1:
        im = im.resize((int(round(w * s)), int(round(h * s))), Image.LANCZOS)
    inp = proc(images=im, size={"shortest_edge": min(im.size), "longest_edge": max(im.size)}, return_tensors="pt")
    with torch.no_grad():
        out = net(**inp)
    seg = proc.post_process_semantic_segmentation(out, target_sizes=[(h, w)])[0]
    return seg.numpy().astype(np.uint8)


def labels(classmap, names):
    """The labels of the scene (0 sky, 1 ground, 2 vegetation, 3 building, 255 not modelled) of a class map."""
    lut = np.full(256, 255, np.uint8)
    for i, n in names.items():
        n = n.lower()
        lab = 0 if n in SKY_N else 3 if n in BUILDING_N else 2 if n in VEG_N else 1 if n in GROUND_N else 255
        lut[int(i)] = lab
    return lut[classmap]


if __name__ == "__main__":
    from PIL import Image
    rgb = np.asarray(Image.open(sys.argv[1]).convert("RGB"))
    Image.fromarray(segment(rgb)).save(sys.argv[2])
