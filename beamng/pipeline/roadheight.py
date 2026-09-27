"""Height of the paved surfaces (road meshes, markings, road furniture, AI roads, terrain carve).

v1.0 took the paved surfaces straight from the DTM (with the edges carried inwards): every road
had the lidar noise in it, the bridge over the valley 3.05 km from Magliaso sagged 7 m into it
(the DTM is the ground without bridges), and walls between a road and a yard or a road above it
were smeared into ramps across the carriageway. Now the surfaces are the idealised fit of
surface_fit.py over the paved polygons of the corridor (the ones meshed by build_level): smooth
roads with plane cross sections and a stiffer profile along the carriageway of the Strada
Cantonale (road_profile.npz), bridges over the gaps of the DTM, clean steps at the walls.
Output: work/road_surface.npz (surface_fit.Surface on a window of the 0.5 m DTM raster) and
work/road_surface.json (summary).
height_fn(): the paved surface on and within 2 m of the paved areas, the smoothed DTM beyond 4 m
(side roads leaving the corridor, the verge), blended in between.
polygon_key(poly): the surface of one paved polygon, for its mesh (vertices on its edge get the
height of that polygon even where another surface meets it at a step).
"""
import json, os, pickle
import numpy as np
import shapely
from scipy.ndimage import gaussian_filter, map_coordinates
from rasterio import features
from rasterio.transform import Affine
from config import WORK
from geo import Grid
import surface_fit

CLASSES = ("strada_sentiero", "altro_rivestimento_duro", "marciapiede", "spartitraffico")
CORRIDOR = 40.0                  # m around the Street View route: paved polygons that are meshed
NEAR, FAR = 2.0, 4.0             # height_fn: paved surface within NEAR m, DTM beyond FAR m
_cache = {}


def paved_polygons():
    """Cadastral paved surfaces within CORRIDOR m of the Street View route (the road meshes):
    [(geometry clipped to the corridor, class, properties)]."""
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    poses = json.load(open(os.path.join(WORK, "poses.json")))
    corridor = shapely.LineString([p["pos"][:2] for p in poses if p["main_run"]]).buffer(CORRIDOR)
    out = []
    for cls in CLASSES:
        for g, props in av["LCSF"].get(cls, []):
            if not g.intersects(corridor):
                continue
            gi = g.intersection(corridor)
            if gi.is_empty or gi.area < 0.5:
                continue
            out.append((gi, cls, props))
    return out


def build():
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    polys = paved_polygons()
    x0, y0, x1, y1 = shapely.union_all([g for g, _, _ in polys]).bounds
    res = dtm.res
    c0 = max(int(np.floor((x0 - 10 - dtm.x_min) / res)), 0)
    c1 = min(int(np.ceil((x1 + 10 - dtm.x_min) / res)), dtm.a.shape[1])
    r0 = max(int(np.floor((dtm.y_max - y1 - 10) / res)), 0)
    r1 = min(int(np.ceil((dtm.y_max - y0 + 10) / res)), dtm.a.shape[0])
    x_min, y_max = dtm.x_min + c0 * res, dtm.y_max - r0 * res
    tr = Affine(res, 0, x_min, 0, -res, y_max)                     # row 0 = north (geo.Grid)
    owner = features.rasterize([(g, i) for i, (g, _, _) in enumerate(polys)], out_shape=(r1 - r0, c1 - c0),
                               transform=tr, fill=-1, dtype=np.int32)
    D = dtm.a[r0:r1, c0:c1].astype(np.float64)
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    main = surface_fit.carriageway_mask(owner.shape, x_min, y_max, res, rp["C"], rp["N"], rp["tL"], rp["tR"])
    S, info = surface_fit.fit(owner, D, x_min, y_max, res, main=main & (owner >= 0))
    S.save(os.path.join(WORK, "road_surface.npz"))
    json.dump(info, open(os.path.join(WORK, "road_surface.json"), "w"), indent=1)
    _cache.pop("S", None)
    return S


def load():
    """The fitted surfaces (work/road_surface.npz, built on demand)."""
    if "S" not in _cache:
        f = os.path.join(WORK, "road_surface.npz")
        _cache["S"] = surface_fit.Surface.load(f) if os.path.exists(f) else build()
    return _cache["S"]


def polygon_key(poly, S=None):
    """Index of the fitted polygon under `poly` (majority of its cells), or None."""
    S = S or load()
    x0, y0, x1, y1 = poly.bounds
    c0 = max(int(np.floor((x0 - S.x_min) / S.res)), 0)
    r0 = max(int(np.floor((S.y_max - y1) / S.res)), 0)
    c1 = min(int(np.ceil((x1 - S.x_min) / S.res)) + 1, S.owner.shape[1])
    r1 = min(int(np.ceil((S.y_max - y0) / S.res)) + 1, S.owner.shape[0])
    if c1 <= c0 or r1 <= r0:
        return None
    tr = Affine(S.res, 0, S.x_min + c0 * S.res, 0, -S.res, S.y_max - r0 * S.res)
    m = features.rasterize([(poly, 1)], out_shape=(r1 - r0, c1 - c0), transform=tr, fill=0, dtype=np.uint8,
                           all_touched=True).astype(bool)
    o = S.owner[r0:r1, c0:c1][m]
    o = o[o >= 0]
    return int(np.bincount(o).argmax()) if len(o) else None


def height_fn():
    """Paved surface near the paved areas, smoothed DTM away from them (bilinear)."""
    S = load()
    if "base" not in _cache:
        dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
        _cache["base"] = Grid(gaussian_filter(dtm.a, 1.0), dtm.x_min, dtm.y_max, dtm.res)
    base = _cache["base"]

    def fn(x, y):
        shape = np.shape(x)
        x = np.atleast_1d(np.asarray(x, np.float64)).ravel()
        y = np.atleast_1d(np.asarray(y, np.float64)).ravel()
        r, c = base.rc(x, y)
        z = map_coordinates(base.a, [r, c], order=1, mode="nearest").astype(np.float64)
        w = np.clip((FAR - S.distance(x, y)) / (FAR - NEAR), 0.0, 1.0)
        m = w > 0
        if m.any():
            z[m] = w[m] * S.height(x[m], y[m]) + (1 - w[m]) * z[m]
        return z.reshape(shape)
    return fn


if __name__ == "__main__":
    build()
