"""Rasterise the cadastral land cover (MU / AV LCSF) and single objects onto the
0.5 m local grid shared with dtm05/dsm05.

work/landcover05.npz : uint8 class codes (see CLASSES), 0 = not covered by the survey
work/av_local.pkl    : AV polygons/lines in local coordinates, by class (shapely)

Switzerland Builder: where the survey has nothing in Switzerland (the cantons whose survey is not open on
geodienste.ch), the land cover of swissTLM3D and ESA WorldCover stands in for it (tlm_cover).
"""
import gzip, json, os, pickle
import numpy as np
import shapely
from shapely.geometry import shape
from rasterio import features
from rasterio.transform import Affine
from config import DATA, WORK, ZONE, lv95_to_local, wgs_to_local
from geo import Grid

CLASSES = ["none", "edificio", "altro_rivestimento_duro", "giardino", "campo_prato_pascolo",
           "strada_sentiero", "bacino_idrico", "bosco_fitto", "corso_acqua", "vigna", "marciapiede",
           "altro_bosco", "altro_humus", "spartitraffico", "pietraia_sabbia", "specchio_acqua",
           "canneti", "ferrovia", "altra_coltura_intensiva", "cava_di_ghiaia_discarica",
           "altra_senza_vegetazione", "torbiera",
           # classes of the survey that only appear in the v2.0 area (appended: codes stay stable)
           "pascolo_boscato_fitto", "pascolo_boscato_aperto", "roccia", "ghiacciaio_nevaio",
           "binario", "pista_aerea", "altro"]
CODE = {c: i for i, c in enumerate(CLASSES)}
CHANNEL_SHARE = 0.3     # v3.1: the share of a hard surface's outline along a stream for it to be its bank
CHANNEL_SLOPE = 0.15    # and the median slope of its ground (the yards and quays by the water are flat)
CHANNEL_GAP = 0.5       # m between the two outlines that still counts as along
# Switzerland Builder (2026-11-07): in the cantons whose cadastral survey is not open on geodienste.ch (LU, OW, NW, VD,
# VS, NE, JU) this raster was 'none' everywhere, which the pipeline reads as "not Switzerland": no tree within reach of
# the roads (vegetation.build keeps only the trees on surveyed land, forest_fill drew the woods as far trees), no lake
# (water.lake_level measures the surveyed lake), no river water (rivers.py draws the surveyed rivers). There, the land
# cover polygons of swissTLM3D (download_tlm.py) are laid by these classes (first match of the start of OBJEKTART),
# also into the survey's polygons (rivers, lakes), and the rest of the Swiss land (meadows, fields and built-up land,
# which swissTLM3D leaves out) takes a class from ESA WorldCover (WC_CLASS). Switzerland is the union of the OSM
# municipalities with a BFS number (download_osm.zone_main), so the land over the border stays 'none' as before.
TLM_CLASSES = (("Wald offen", "pascolo_boscato_aperto"), ("Wald", "bosco_fitto"), ("Gebueschwald", "altro_bosco"),
               ("Gehoelz", "altro_bosco"), ("Felsbloecke", "pietraia_sabbia"), ("Fels", "roccia"),
               ("Lockergestein", "pietraia_sabbia"), ("Gletscher", "ghiacciaio_nevaio"),
               ("Schneefeld", "ghiacciaio_nevaio"), ("Stehende", "specchio_acqua"), ("Fliess", "corso_acqua"),
               ("Feucht", "torbiera"), ("Sumpf", "torbiera"))
WC_CLASS = {10: "altro_bosco", 20: "altro_bosco", 30: "campo_prato_pascolo", 40: "campo_prato_pascolo",
            50: "giardino", 60: "altra_senza_vegetazione", 70: "ghiacciaio_nevaio", 80: "campo_prato_pascolo",
            90: "torbiera", 95: "altro_bosco", 100: "campo_prato_pascolo"}
WC_DEFAULT = "campo_prato_pascolo"
TLM_MIN_M2 = 50.0       # m2: smaller pieces of a swissTLM3D polygon cut by the survey's edge are left out


def code(cls):
    """Class code; unknown survey classes count as 'altro' (reported by main)."""
    return CODE.get(cls, CODE["altro"])


def to_local(geom):
    return shapely.transform(geom, lambda c: np.stack(lv95_to_local(c[:, 0], c[:, 1]), 1))


def load_av(smooth=True):
    out = {"LCSF": {}, "SOSF": {}, "SOLI": {}, "SOPT": {}}
    for layer in out:
        for f in json.load(open(os.path.join(DATA, "av", f"{layer}.geojson")))["features"]:
            g = to_local(shape(f["geometry"]))
            if not g.is_valid:
                g = shapely.make_valid(g)
            out[layer].setdefault(f["properties"]["Genere"], []).append((g, f["properties"]))
    if smooth:
        smooth_curves(out)
    return out


def smooth_curves(av):
    """v3.0: the curves of the survey smoothed (smooth_geom.py): the land cover as one partition (the
    buildings kept as they are), the walls' footprints and axes on their own."""
    import smooth_geom
    items = [(cls, k) for cls, lst in av["LCSF"].items() for k in range(len(lst))]
    geoms = [av["LCSF"][c][k][0] for c, k in items]
    new = smooth_geom.smooth_partition(geoms, [c == "edificio" for c, _ in items])
    for (c, k), g in zip(items, new):
        av["LCSF"][c][k] = (g, av["LCSF"][c][k][1])
    av["SOSF"]["muro"] = [(smooth_geom.smooth_polygon(g), p) for g, p in av["SOSF"].get("muro", [])]
    av["SOLI"]["muro"] = [(smooth_geom.smooth_line(g), p) for g, p in av["SOLI"].get("muro", [])]
    print("survey curves smoothed: %d land cover polygons, %d + %d walls"
          % (len(geoms), len(av["SOSF"]["muro"]), len(av["SOLI"]["muro"])), flush=True)


def channel_linings(av, dtm):
    """v3.1: the 'altro_rivestimento_duro' of the survey that lines a stream (CHANNEL_SHARE of its outline along a
    'corso_acqua', its ground steeper than CHANNEL_SLOPE in the median: the stone banks of the Magliasina, an
    abutment's face) are stones and gravel ('pietraia_sabbia'), not a yard: up to v3.0.40 they were grey asphalt
    meshes sloping down into the river bed under the bridges and along it, without trees. The yards and quays by a
    river are flat. Returns how many."""
    hard = av["LCSF"].get("altro_rivestimento_duro", [])
    water = [g for g, _ in av["LCSF"].get("corso_acqua", [])]
    if not hard or not water:
        return 0
    wtree = shapely.STRtree(water)
    keep, moved = [], []
    for g, p in hard:
        near = wtree.query(g.buffer(CHANNEL_GAP))
        share = 0.0
        if len(near):
            wb = shapely.union_all([water[i] for i in near]).buffer(CHANNEL_GAP)
            share = g.boundary.intersection(wb).length / max(g.boundary.length, 1e-9)
        if share >= CHANNEL_SHARE:
            win, _, _ = dtm.window(*g.bounds, pad=2)
            a = np.asarray(win.a, np.float64)
            if a.shape[0] > 2 and a.shape[1] > 2:
                gy, gx = np.gradient(a, win.res)
                hh, ww = a.shape
                X, Y = np.meshgrid(win.x_min + (np.arange(ww) + 0.5) * win.res, win.y_max - (np.arange(hh) + 0.5) * win.res)
                m = shapely.contains_xy(g, X, Y)
                if m.sum() >= 4 and np.median(np.hypot(gx, gy)[m]) >= CHANNEL_SLOPE:
                    moved.append((g, p))
                    continue
        keep.append((g, p))
    av["LCSF"]["altro_rivestimento_duro"] = keep
    av["LCSF"].setdefault("pietraia_sabbia", []).extend(moved)
    print("stream banks of the survey as stones, not paved: %d (%.2f ha)" % (len(moved), sum(g.area for g, _ in moved) / 1e4),
          flush=True)
    return len(moved)


def tlm_class(objektart):
    o = str(objektart or "")
    for start, cls in TLM_CLASSES:
        if o.startswith(start):
            return cls
    return None


def ring_polygons(parts):
    """Polygons (local) of a shapefile polygon's rings: the outer rings run clockwise, the holes counter-clockwise."""
    rings = []
    for q in parts:
        q = np.asarray(q, np.float64)
        if len(q) < 4:
            continue
        x, y = lv95_to_local(q[:, 0], q[:, 1])
        rings.append(np.column_stack([x, y]))
    if not rings:
        return []
    ccw = [shapely.LinearRing(r).is_ccw for r in rings]
    outers = [r for r, c in zip(rings, ccw) if not c] or rings
    holes = [r for r, c in zip(rings, ccw) if c] if len(outers) < len(rings) else []
    polys = [shapely.Polygon(o) for o in outers]
    inner = [[] for _ in polys]
    for hr in holes:
        pt = shapely.Point(hr[0])
        for k, g in enumerate(polys):
            if g.contains(pt):
                inner[k].append(hr)
                break
    out = []
    for o, hs in zip(outers, inner):
        g = shapely.Polygon(o, hs)
        if not g.is_valid:
            g = shapely.make_valid(g)
        out += [q for q in shapely.get_parts(g) if q.geom_type == "Polygon" and q.area > 0]
    return out


def swiss_land():
    """Switzerland over the area (local): the union of the OSM municipalities with a BFS number, None without them."""
    f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "osm_communes.json.gz")
    if not os.path.exists(f):
        return None
    polys = []
    for e in json.load(gzip.open(f, "rt", encoding="utf-8")).get("elements", []):
        t = e.get("tags", {})
        if not (t.get("ref:bfs_Gemeindenummer") or t.get("swisstopo:BFS_NUMMER")):
            continue
        lines = []
        for m in e.get("members", []):
            if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry"):
                lat = np.array([q["lat"] for q in m["geometry"]])
                lon = np.array([q["lon"] for q in m["geometry"]])
                x, y = wgs_to_local(lat, lon)
                lines.append(shapely.LineString(np.column_stack([x, y])))
        if lines:
            polys += list(shapely.get_parts(shapely.polygonize(lines)))
    return shapely.union_all(polys) if polys else None


def tlm_cover(av, lc, x_min, y_max, res):
    """Switzerland Builder: the Swiss land the survey left empty, from swissTLM3D's land cover and ESA WorldCover (see
    TLM_CLASSES). Writes into lc (cells still 0) and adds the swissTLM3D polygons to av["LCSF"]; returns a report."""
    rep = {}
    p = os.path.join(DATA, "tlm", "TLM_BODENBEDECKUNG.json")
    h, w = lc.shape
    raster_box = shapely.box(x_min, y_max - h * res, x_min + w * res, y_max)
    tlm = []
    if os.path.exists(p):
        unknown = {}
        for f in json.load(open(p))["features"]:
            cls = tlm_class(f["props"].get("OBJEKTART"))
            if cls is None:
                o = str(f["props"].get("OBJEKTART"))
                unknown[o] = unknown.get(o, 0) + 1
                continue
            for g in ring_polygons(f["parts"]):
                if g.intersects(raster_box):
                    tlm.append((g.intersection(raster_box), cls, f["props"]))
        if unknown:
            print("swissTLM3D land cover classes left out:", unknown, flush=True)
    else:
        print("no swissTLM3D land cover (data/tlm/TLM_BODENBEDECKUNG.json)", flush=True)
    survey = [g for items in av["LCSF"].values() for g, _ in items]
    stree = shapely.STRtree(survey) if survey else None
    added = {}
    for g, cls, props in tlm:
        if stree is not None:
            near = stree.query(g, predicate="intersects")
            if len(near):
                g = g.difference(shapely.union_all([survey[i] for i in near]))
        for q in shapely.get_parts(g):
            if q.geom_type == "Polygon" and q.area >= TLM_MIN_M2:
                av["LCSF"].setdefault(cls, []).append((q, {"Genere": cls, "source": "swissTLM3D",
                                                           "OBJEKTART": props.get("OBJEKTART")}))
                added[cls] = added.get(cls, 0.0) + q.area
    rep["tlm_ha"] = {k: round(v / 1e4, 1) for k, v in sorted(added.items())}
    swiss = swiss_land()
    rep["swiss_municipalities"] = swiss is not None
    if swiss is not None:
        swiss = swiss.intersection(raster_box.buffer(res))
    wc = None
    try:
        import forest_fill
        wc = forest_fill.worldcover_grid()
    except Exception as e:                     # no WorldCover: the rest of the Swiss land is meadow
        print("no WorldCover for the land cover:", e, flush=True)
    shapes = [(g, CODE[cls]) for cls, items in av["LCSF"].items() for g, p in items if p.get("source") == "swissTLM3D"]
    B = 2048
    for r0 in range(0, h, B):
        r1 = min(r0 + B, h)
        y_top = y_max - r0 * res
        tr = Affine(res, 0, x_min, 0, -res, y_top)
        band = lc[r0:r1]
        free = band == 0
        if not free.any():
            continue
        box = shapely.box(x_min, y_max - r1 * res, x_min + w * res, y_top)
        sub = [(g, c) for g, c in shapes if g.intersects(box)]
        if sub:
            t = features.rasterize(sub, out_shape=(r1 - r0, w), fill=0, dtype=np.uint8, transform=tr)
            m = free & (t > 0)
            band[m] = t[m]
            free &= ~m
        if swiss is None or not free.any():
            continue
        inside = features.rasterize([(swiss, 1)], out_shape=(r1 - r0, w), fill=0, dtype=np.uint8, transform=tr) > 0
        rest = free & inside
        if not rest.any():
            continue
        if wc is not None:
            xs = x_min + (np.arange(w) + 0.5) * res
            ys = y_top - (np.arange(r1 - r0) + 0.5) * res
            ci = np.floor((xs - wc.x_min) / wc.res).astype(np.int64)
            ri = np.floor((wc.y_max - ys) / wc.res).astype(np.int64)
            okc, okr = (ci >= 0) & (ci < wc.a.shape[1]), (ri >= 0) & (ri < wc.a.shape[0])
            W = np.zeros((r1 - r0, w), np.uint8)
            W[np.ix_(okr, okc)] = np.asarray(wc.a)[np.ix_(ri[okr], ci[okc])]
            lut = np.full(256, CODE[WC_DEFAULT], np.uint8)
            for k, cls in WC_CLASS.items():
                lut[k] = CODE[cls]
            band[rest] = lut[W[rest]]
        else:
            band[rest] = CODE[WC_DEFAULT]
    print("land cover with swissTLM3D where the survey has none: polygons %s ha; Swiss municipalities %s"
          % (rep["tlm_ha"], "yes" if rep["swiss_municipalities"] else "no (the rest of the land stays 'none')"), flush=True)
    return rep


def main():
    av = load_av()
    dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    channel_linings(av, dtm)
    h, w = dtm.a.shape
    tr = Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, dtm.y_max)
    shapes = []
    unknown = sorted({cls for cls in av["LCSF"] if cls not in CODE})
    if unknown:
        print("survey classes not in CLASSES (as 'altro'):", unknown)
    for cls, items in av["LCSF"].items():
        for g, p in items:
            shapes.append((g, code(cls)))
    lc = np.zeros((h, w), np.uint8)
    B = 2048                                             # row bands: the v2.0 grid is ~22 000 x 18 000
    for r0 in range(0, h, B):
        r1 = min(r0 + B, h)
        y_top = dtm.y_max - r0 * dtm.res
        box = shapely.box(dtm.x_min, dtm.y_max - r1 * dtm.res, dtm.x_min + w * dtm.res, y_top)
        sub = [(g, c) for g, c in shapes if g.intersects(box)]
        if sub:
            lc[r0:r1] = features.rasterize(sub, out_shape=(r1 - r0, w), fill=0, dtype=np.uint8, all_touched=False,
                                           transform=Affine(dtm.res, 0, dtm.x_min, 0, -dtm.res, y_top))
    if ZONE and ZONE.get("builder"):
        surveyed = int((lc != 0).sum())
        tlm_cover(av, lc, dtm.x_min, dtm.y_max, dtm.res)
        print("cells of the survey %.1f %%, after swissTLM3D and WorldCover %.1f %%"
              % (100 * surveyed / lc.size, 100 * (lc != 0).sum() / lc.size), flush=True)
    pickle.dump(av, open(os.path.join(WORK, "av_local.pkl"), "wb"))
    np.savez_compressed(os.path.join(WORK, "landcover05.npz"), a=lc, x_min=dtm.x_min, y_max=dtm.y_max, res=dtm.res)
    u, c = np.unique(lc, return_counts=True)
    for k, n in zip(u, c):
        print(f"{CLASSES[k]:28s} {n * dtm.res ** 2 / 1e4:8.2f} ha")


if __name__ == "__main__":
    main()
