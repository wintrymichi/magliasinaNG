"""Copies the in-game screenshots the website shows into web/img/, resized for the web:
<name>.jpg (at most 1600 px wide) and <name>_s.jpg (800 px wide, for the grid).

Run from anywhere: python web/tools/make_images.py
"""
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "beamng", "verifica", "screenshots")
OUT = os.path.join(ROOT, "web", "img")
FILES = [
    "v2.8/overview-novaggio-miglieglia-malcantone.jpg",
    "14_passo_tornante.jpg", "12_pura_cantonale.jpg", "13_agno_via.jpg", "11_magliaso_strada.jpg",
    "01_magliaso_lago.jpg", "05_ponte_tresa.jpg", "09_passo_arosio.jpg", "10_caslano_torrazza.jpg",
    "02_agno_nucleo.jpg", "03_cademario.jpg", "08_sessa.jpg",
    "v2.7/signs_roundabout.jpg", "v2.7/signs_cantonale_pointer.jpg", "v2.7/markings_crossing.jpg",
    "v2.7/signs_village50.jpg", "v2.7/unpaved_arosio.jpg", "v2.7/unpaved_cademario.jpg",
    "v2.7/fartrees_gravesano_pass.jpg", "v2.7/markings_roundabout.jpg",
]


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
