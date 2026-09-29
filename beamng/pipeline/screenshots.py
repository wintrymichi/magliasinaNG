"""Screenshots of the built level for the README and the release notes (v2.2), rendered without the
game by render3d.py (three.js in Chromium) with the textures of the level's own materials: facades,
roofs, walls, road paint. The terrain is draped with the orthophoto (the game's terrain materials
are vanilla textures that are not in the level folder).
Views are given in the local frame (x east, y north, metres; see config.py) or as lat/lon.
    python screenshots.py [out folder]        (default: beamng/verifica/screenshots)
"""
import math, os, sys
import numpy as np
from config import LEVEL_DIR, WORK, wgs_to_local
from geo import Grid

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica", "screenshots")

# name: (target lat, lon, distance m, compass azimuth the camera looks from, elevation deg, fov, title)
VIEWS = {
    "01_magliaso_lago": (45.9807, 8.8850, 520, 200, 24, 50, "Magliaso e il Lago di Lugano"),
    "02_agno_nucleo": (45.9990, 8.9018, 230, 160, 30, 50, "Agno, il nucleo e la Collegiata"),
    "03_cademario": (46.0226, 8.8905, 330, 150, 28, 50, "Cademario"),
    "04_novaggio": (46.0100, 8.8530, 360, 120, 26, 50, "Novaggio"),
    "05_ponte_tresa": (45.9678, 8.8570, 260, 60, 28, 50, "Ponte Tresa, il ponte di confine"),
    "06_bioggio_manno": (46.0215, 8.9075, 600, 200, 25, 50, "Bioggio e Manno, piano del Vedeggio"),
    "07_astano": (45.9890, 8.8215, 300, 140, 28, 50, "Astano"),
    "08_sessa": (45.9990, 8.8140, 300, 220, 26, 50, "Sessa"),
}
# street level: (camera lat, lon, look-at lat, lon, eye height, fov, title)
STREET = {
    "11_magliaso_strada": (45.98183, 8.88135, 45.98247, 8.88040, 1.6, 64, "Magliaso, via verso il nucleo"),
    "12_pura_cantonale": (45.99440, 8.86660, 45.99530, 8.86560, 1.6, 64, "La cantonale verso Pura"),
    "13_agno_via": (45.99870, 8.90160, 45.99950, 8.90120, 1.6, 64, "Agno, una via del nucleo"),
}


def main(out=None):
    from render3d import Renderer, Camera
    out = out or OUT
    os.makedirs(out, exist_ok=True)
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    zat = lambda x, y: float(dtm.sample(np.array([x]), np.array([y]))[0])
    with Renderer(LEVEL_DIR, W=1600, H=900, quality=0.9, textured=True) as r:
        for name, (lat, lon, dist, az, el, fov, title) in VIEWS.items():
            x, y = wgs_to_local(lat, lon)
            cam = Camera.orbit(x, y, zat(x, y), dist, az, el, fov=fov)
            f = r.shot(cam, os.path.join(out, name + ".jpg"), near=min(900.0, 1.6 * dist))
            print(f, "-", title, flush=True)
        for name, (la, lo, lb, lob, eye, fov, title) in STREET.items():
            x0, y0 = wgs_to_local(la, lo)
            x1, y1 = wgs_to_local(lb, lob)
            z0, z1 = zat(x0, y0), zat(x1, y1)
            cam = Camera.look((x0, y0, z0 + eye), (x1, y1, z1 + eye), fov=fov, near=0.2)
            f = r.shot(cam, os.path.join(out, name + ".jpg"), near=350.0)
            print(f, "-", title, flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
