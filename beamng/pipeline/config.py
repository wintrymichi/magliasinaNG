"""Shared paths and the single coordinate system used by every pipeline step.

World frame (BeamNG): x = east, y = north, z = up, metres, true ground scale.
  x = (E - E0) / K,  y = (N - N0) / K,  z = orthometric height (LN02, m a.s.l.)
where (E, N) are Swiss LV95 (EPSG:2056) coordinates and K is the LV95 point
scale factor at the map centre, so 1 m in BeamNG is 1 m on the ground.
"""
import os
from pyproj import Transformer

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# every path can be moved with an environment variable (e.g. a build on another machine)
DATASET = os.environ.get("MAGLIASO_DATASET") or r"C:\Users\michi\Documents\magliasinaNG"   # Street View images + poses
ROOT = os.environ.get("MAGLIASO_ROOT") or r"D:\beamng_magliaso"                         # heavy data / cache
DATA = os.path.join(ROOT, "data")
WORK = os.path.join(ROOT, "work")
LEVEL_NAME = "magliaso_pura"
BEAMNG_USER = os.environ.get("MAGLIASO_BEAMNG_USER") or r"C:\Users\michi\AppData\Local\BeamNG\BeamNG.drive\current"
BEAMNG_GAME = os.environ.get("MAGLIASO_BEAMNG_GAME") or r"C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive"
# the released level (zip) whose copies of vanilla files stand in for the game install when
# BEAMNG_GAME does not exist (textures, forest materials; see vanilla.py)
REFERENCE_ZIP = os.environ.get("MAGLIASO_REFERENCE_ZIP") or os.path.join(ROOT, "dist", "magliaso_pura_v1.1.zip")
# MAGLIASO_LEVEL_DIR builds the level somewhere else (e.g. the public variant next to the
# personal one installed in the game)
LEVEL_DIR = os.environ.get("MAGLIASO_LEVEL_DIR") or os.path.join(BEAMNG_USER, "levels", LEVEL_NAME)

# map origin (LV95) = centre of the Street View route, rounded to the metre
E0, N0 = 2710830.0, 1094360.0
K = 1.0001374973449562          # LV95 scale factor at the origin (pyproj get_factors)
# playable area (v2.0, Malcantone): the boundary drawn by the user (WGS84 lat, lon), widened by
# AREA_MARGIN m and joined with the Street View route (ROUTE_MARGIN m around it) and with the
# cantonal road Magliaso - Agno - Bioggio - Manno - Gravesano (dati/cantonale_gravesano.json,
# strade_extra.py: EXTRA_ROAD_MARGIN m around it and the strip between it and the side P1-P2 of the
# boundary); v2.2: with a corridor of EXTRA_CORRIDOR m around the roads of dati/strade_extra_v22.json (the
# pass above Gravesano to Arosio, the cantonal road Ponte Tresa - Caslano - Magliaso, Caslano - Torrazza;
# v2.8: Arosio - Mugena - Breno - Miglieglia - Novaggio);
# see area.py
BOUNDARY = [(45.967056, 8.858833), (46.041250, 8.923417), (46.018500, 8.803833), (45.993111, 8.788028)]
AREA_MARGIN = 150.0
ROUTE_MARGIN = 60.0
EXTRA_ROAD_MARGIN = 150.0
EXTRA_CORRIDOR = 100.0
# terrain block: TER_SIZE x TER_SIZE vertices TER_SQUARE m apart, vertex (0, 0) (south-west) at
# (TER_X0, TER_Y0); it covers the area with ~0.6-2 km to spare
TER_SIZE = 8192                 # terrain samples per side
TER_SQUARE = 1.5                # metres per terrain sample
TER_X0, TER_Y0 = -7230.0, -4731.0
TER_X1 = TER_X0 + (TER_SIZE - 1) * TER_SQUARE
TER_Y1 = TER_Y0 + (TER_SIZE - 1) * TER_SQUARE

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


# No imagery taken from the Street View panoramas goes into the level (facade/wall photo textures,
# sign plates): the photos are a reference only, what they show is redrawn (bld_textures.py,
# props_osm.py) and only numbers measured in them (facade tone, shutter colour, wall material,
# guard rails) are used. v2.2: this is the default; MAGLIASO_NO_PHOTO_TEXTURES=0 brings back the
# photo textures of the local v1.x builds, for private study only.
NO_PHOTO = os.environ.get("MAGLIASO_NO_PHOTO_TEXTURES", "1") != "0"
