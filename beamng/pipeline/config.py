"""Shared paths and the single coordinate system used by every pipeline step.

World frame (BeamNG): x = east, y = north, z = up, metres, true ground scale.
  x = (E - E0) / K,  y = (N - N0) / K,  z = orthometric height (LN02, m a.s.l.)
where (E, N) are Swiss LV95 (EPSG:2056) coordinates and K is the LV95 point
scale factor at the map centre, so 1 m in BeamNG is 1 m on the ground.
"""
import os
from pyproj import Transformer

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = r"C:\Users\michi\Documents\magliasinaNG"          # Street View images + poses
ROOT = r"D:\beamng_magliaso"                               # heavy data / cache
DATA = os.path.join(ROOT, "data")
WORK = os.path.join(ROOT, "work")
LEVEL_NAME = "magliaso_pura"
BEAMNG_USER = r"C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
BEAMNG_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
# MAGLIASO_LEVEL_DIR builds the level somewhere else (e.g. the public variant next to the
# personal one installed in the game)
LEVEL_DIR = os.environ.get("MAGLIASO_LEVEL_DIR") or os.path.join(BEAMNG_USER, "levels", LEVEL_NAME)

# map origin (LV95) = centre of the Street View route, rounded to the metre
E0, N0 = 2710830.0, 1094360.0
K = 1.0001374973449562          # LV95 scale factor at the origin (pyproj get_factors)
TER_SIZE = 4096                 # terrain samples per side
TER_SQUARE = 1.0                # metres per terrain sample
TER_HALF = TER_SIZE * TER_SQUARE / 2   # terrain spans [-TER_HALF, TER_HALF] in x and y

_to_lv95 = Transformer.from_crs("EPSG:4326", "EPSG:2056", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)


def wgs_to_lv95(lat, lon):
    e, n = _to_lv95.transform(lon, lat)
    return e, n


def lv95_to_wgs(e, n):
    lon, lat = _to_wgs.transform(e, n)
    return lat, lon


def lv95_to_local(e, n):
    return (e - E0) / K, (n - N0) / K


def local_to_lv95(x, y):
    return E0 + x * K, N0 + y * K


def wgs_to_local(lat, lon):
    return lv95_to_local(*wgs_to_lv95(lat, lon))


for _d in (DATA, WORK):
    os.makedirs(_d, exist_ok=True)


# MAGLIASO_NO_PHOTO_TEXTURES=1 builds a level without imagery taken from the Street View
# panoramas (facade/wall photo textures, sign plates): for public distribution. Colours
# measured in the photos (facade tone, terrain) are kept.
NO_PHOTO = os.environ.get("MAGLIASO_NO_PHOTO_TEXTURES") == "1"
