"""Copies the in-game screenshots the website shows into web/img/, resized for the web:
<name>.jpg (at most 1600 px wide) and <name>_s.jpg (800 px wide, for the grid).

Run from anywhere: python web/tools/make_images.py
"""
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "beamng", "verifica", "screenshots")
OUT = os.path.join(ROOT, "web", "img")
FILES = ["v3.0/" + f + ".jpg" for f in [
    "overview-novaggio-miglieglia", "cockpit-cantonale-guardrail", "chase-cantonale", "cockpit-penudria",
    "cockpit-miglieglia-novaggio", "cockpit-agno-lakeside", "overview-magliaso-lake", "new-eni-magliaso-paese",
    "new-eni-and-parking-bays", "new-parking-bays-flp-magliaso", "new-wear-hairpin", "overview-cantonale-hairpins",
    "cockpit-roundabout-magliaso", "cockpit-cantonale-stone-wall", "cockpit-novaggio-miglieglia", "cockpit-caslano",
    "overview-caslano-lake", "overview-pura", "overview-magliaso-paese", "overview-agno-lake", "overview-ponte-tresa",
    "cockpit-cantonale-down-to-magliaso", "new-wear-hairpin-2", "cockpit-roundabout-magliaso-2",
]]


def save(im, path, width):
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(path, quality=80, optimize=True, progressive=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in FILES:
        im = Image.open(os.path.join(SRC, f)).convert("RGB")
        name = os.path.splitext(os.path.basename(f))[0]
        save(im, os.path.join(OUT, name + ".jpg"), 1600)
        save(im, os.path.join(OUT, name + "_s.jpg"), 800)
    print(len(FILES), "images in", OUT)


if __name__ == "__main__":
    main()
