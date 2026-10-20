"""v3.0.40: villages that the area only cut through, made whole (issue #16). Up to v3.0 Caslano and Arosio were in
the map only within EXTRA_CORRIDOR m of the roads of dati/strade_extra_v22.json (strade_extra.py), so half of each
village was bare terrain at the edge of the area.
- Caslano: the whole municipality on land (its OSM boundary, dati/osm_communes.json.gz, reaches into the lake), with
  the lakeside, the Torrazza and the Monte Caslano peninsula, plus SHORE_WATER m of lake along the shore.
- Arosio: the village, i.e. the buildings of the register (GWR) of the municipality of Alto Malcantone whose nearest
  settlement of swissNAMES3D is Arosio, each widened by HOUSE m and closed over the gaps between them (CLOSE m).
Output: dati/paesi_interi.json (the polygons in LV95); area.py joins them to the area, so the build does not need the
data they are computed from.

    python paesi_interi.py               -> dati/paesi_interi.json (downloads what it needs: swissNAMES3D, the register,
                                            swissALTI3D 2 m around Caslano)
    python paesi_interi.py --preview DIR -> top and oblique views of the old and the new area over SWISSIMAGE 2 m
"""
import csv, gzip, io, json, os, sys, zipfile
import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from config import DATA, local_to_lv95, lv95_to_local, wgs_to_local
import area

OUT = os.path.join(area.DATI, area.VILLAGES)
# (key, name, municipality, settlement): settlement None = the whole municipality on land
VILLAGES = [
    ("caslano", "Caslano: tutto il comune, con il lungolago e il Monte Caslano", "Caslano", None),
    ("arosio", "Arosio: tutto il paese", "Alto Malcantone", "Arosio"),
]
SHORE_WATER = 30.0       # m of lake kept along the shore (the edge of the area is not the waterline)
LAND = 0.3               # m above the lake level: land in swissALTI3D 2 m (the lake is flat there)
HOUSE = 50.0             # m around every building of a settlement
CLOSE = 80.0             # m, gaps between the houses of a settlement closed up to twice this
REACH = 600.0            # m from the settlement's name point: farther buildings are left out
SIMPLIFY = 2.0           # m


def commune(name):
    """Local polygon of the municipality `name` (dati/osm_communes.json.gz, admin_level 8)."""
    d = json.load(gzip.open(os.path.join(area.DATI, "osm_communes.json.gz"), "rt", encoding="utf-8"))
    for e in d["elements"]:
        if e.get("tags", {}).get("name") == name:
            rings = [shapely.LineString([wgs_to_local(p["lat"], p["lon"]) for p in m["geometry"]])
                     for m in e["members"] if m["type"] == "way" and m.get("geometry")]
            return shapely.union_all(list(shapely.get_parts(shapely.polygonize(rings))))
    raise KeyError(name)


def _rect(g, margin):
    """LV95 rectangle (e0, n0, e1, n1) of the local geometry g + margin."""
    x0, y0, x1, y1 = g.bounds
    c = [local_to_lv95(x, y) for x in (x0 - margin, x1 + margin) for y in (y0 - margin, y1 + margin)]
    return min(p[0] for p in c), min(p[1] for p in c), max(p[0] for p in c), max(p[1] for p in c)


def fetch_tiles(coll, suffix, sub, rect):
    """The latest 1 km tiles of a swisstopo collection over an LV95 rectangle -> data/<sub>/."""
    import download_swisstopo as ds
    keep = set(area.lv95_rect_tiles(*rect))
    for tile, f in sorted(ds.latest_per_tile(ds.stac_items(coll, *rect)).items()):
        if tile in keep:
            for name, a in f["assets"].items():
                if name.endswith(suffix):
                    print(ds.fetch(a["href"], os.path.join(DATA, sub, name))[1], name, flush=True)


def land(g):
    """Local polygon of the land around g (swissALTI3D 2 m higher than LAND m over the lake level)."""
    from geo import mosaic
    from rasterio import features
    x0, y0, x1, y1 = (np.floor(v / 2.0) * 2.0 for v in g.buffer(300.0).bounds)
    fetch_tiles("ch.swisstopo.swissalti3d", "_2_2056_5728.tif", "swissalti3d_2", _rect(g, 400.0))
    h = mosaic("swissalti3d_2/*.tif", x0, y0, x1, y1, 2.0)[0]
    v = h[np.isfinite(h) & (h < 300.0)]
    level = float(np.bincount(np.round(v * 10).astype(int)).argmax()) / 10.0     # the flat lake
    dry = ndi.binary_opening(np.nan_to_num(h, nan=level) > level + LAND, iterations=2)
    lab, n = ndi.label(dry)
    sizes = ndi.sum(dry, lab, range(1, n + 1))
    dry = np.isin(lab, 1 + np.flatnonzero(sizes * 4.0 >= 2000.0))
    from rasterio.transform import Affine
    tr = Affine(2.0, 0, x0, 0, -2.0, y1)              # local, north-up
    polys = [shapely.geometry.shape(s) for s, val in features.shapes(dry.astype(np.uint8), transform=tr) if val]
    print("lake level %.2f m, land %.2f km2" % (level, sum(p.area for p in polys) / 1e6), flush=True)
    return shapely.union_all(polys)


def settlement(commune_poly, name):
    """Local polygon of the settlement `name`: its buildings of the register, widened and closed."""
    import download_gwr
    import places
    pts = [(n, x, y) for n, x, y, _ in places.settlements()
           if commune_poly.buffer(1000.0).contains(shapely.Point(x, y))]
    me = [i for i, p in enumerate(pts) if p[0] == name][0]
    tree = cKDTree([(x, y) for _, x, y in pts])
    centre = np.array(pts[me][1:])
    houses = []
    with zipfile.ZipFile(download_gwr.fetch()) as z:
        f = [n for n in z.namelist() if n.lower().startswith("gebaeude") and n.endswith(".csv")][0]
        for r in csv.DictReader(io.TextIOWrapper(z.open(f), encoding="utf-8"), delimiter="\t"):
            if r.get("GSTAT") != "1004":                     # existing buildings
                continue
            try:
                x, y = lv95_to_local(float(r["GKODE"]), float(r["GKODN"]))
            except ValueError:
                continue
            if np.hypot(x - centre[0], y - centre[1]) < REACH and tree.query((x, y))[1] == me \
                    and commune_poly.contains(shapely.Point(x, y)):
                houses.append((x, y))
    g = shapely.union_all([shapely.Point(p).buffer(HOUSE, 8) for p in houses])
    g = g.buffer(CLOSE, 8).buffer(-CLOSE, 8)
    parts = sorted(shapely.get_parts(g), key=lambda p: p.distance(shapely.Point(centre)))
    print("%s: %d buildings, %d pieces" % (name, len(houses), len(parts)), flush=True)
    return parts[0] if parts else shapely.Point(centre).buffer(HOUSE)


def compute():
    out = []
    for key, name, com, sett in VILLAGES:
        C = commune(com)
        g = C.intersection(land(C).buffer(SHORE_WATER)) if sett is None else settlement(C, sett)
        g = shapely.Polygon(max(shapely.get_parts(g), key=lambda p: p.area).exterior) if sett is None else g
        g = g.simplify(SIMPLIFY)
        new = g.difference(area._polygon(whole=False))
        print("%s: %.2f km2, %.2f km2 new to the area" % (key, g.area / 1e6, new.area / 1e6), flush=True)
        rings = [np.asarray(g.exterior.coords)] + [np.asarray(r.coords) for r in g.interiors]
        out.append({"key": key, "name": name, "area_m2": round(g.area),
                    "rings": [[[round(float(e), 2), round(float(n_), 2)] for e, n_ in zip(*local_to_lv95(R[:, 0], R[:, 1]))]
                              for R in rings]})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "OSM municipalities (ODbL), swissALTI3D, GWR (BFS), swissNAMES3D; paesi_interi.py",
                   "villages": out}, f, ensure_ascii=False)
    print("->", OUT)


def preview(out_dir):
    """Top and oblique views of each village: the area before (white line) and after (the new part in orange)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from geo import mosaic
    os.makedirs(out_dir, exist_ok=True)
    old, new = area._polygon(whole=False), area.polygon()
    stats = {"area_km2_before": round(old.area / 1e6, 2), "area_km2_after": round(new.area / 1e6, 2)}
    for key, name, g in area.villages():
        res = 4.0
        x0, y0, x1, y1 = (np.floor(v / res) * res for v in g.buffer(350.0).bounds)
        rect = _rect(shapely.box(x0, y0, x1, y1), 100.0)
        fetch_tiles("ch.swisstopo.swissimage-dop10", "_2_2056.tif", "swissimage_2", rect)
        fetch_tiles("ch.swisstopo.swissalti3d", "_2_2056_5728.tif", "swissalti3d_2", rect)
        rgb = np.moveaxis(mosaic("swissimage_2/*.tif", x0, y0, x1, y1, res, dtype=np.float32), 0, -1)[..., :3] / 255.0
        h = mosaic("swissalti3d_2/*.tif", x0, y0, x1, y1, res)[0]
        rgb = np.nan_to_num(rgb)
        h = np.where(np.isfinite(h), h, np.nanmin(h))
        from rasterio import features
        from rasterio.transform import Affine
        tr = Affine(res, 0, x0, 0, -res, y1)
        shape = h.shape
        m_old = features.rasterize([old], out_shape=shape, transform=tr).astype(bool)
        m_new = features.rasterize([new], out_shape=shape, transform=tr).astype(bool)
        added = m_new & ~m_old
        col = rgb.copy()
        col[~m_new] = 0.35 * col[~m_new] + 0.65 * np.array([0.12, 0.12, 0.14])     # outside the map: dimmed
        col[added] = 0.6 * col[added] + 0.4 * np.array([1.0, 0.55, 0.1])           # new: orange
        stats[key] = {"village_km2": round(g.area / 1e6, 2),
                      "added_km2": round(added.sum() * res * res / 1e6, 2)}
        # top view
        fig, ax = plt.subplots(figsize=(12, 12 * shape[0] / shape[1]))
        ax.imshow(col, extent=(x0, x1, y0, y1))
        for p in shapely.get_parts(old.intersection(shapely.box(x0, y0, x1, y1))):
            ax.plot(*p.exterior.xy, color="white", lw=1.2)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_axis_off()
        ax.set_title("%s: area v3.0 (white line), added (orange), outside the map (dark)" % name, fontsize=10)
        fig.savefig(os.path.join(out_dir, key + "_alto.jpg"), dpi=110, bbox_inches="tight")
        plt.close(fig)
        # oblique view from the south
        step = 2
        H, C = h[::step, ::step], col[::step, ::step]
        ls = LightSource(azdeg=315, altdeg=45)
        C = np.clip(C * (0.55 + 0.6 * ls.hillshade(H, dx=res * step, dy=res * step))[..., None], 0, 1)
        X, Y = np.meshgrid(x0 + (np.arange(H.shape[1]) + 0.5) * res * step, y1 - (np.arange(H.shape[0]) + 0.5) * res * step)
        fig = plt.figure(figsize=(14, 9))
        ax = fig.add_subplot(projection="3d", computed_zorder=False)
        ax.plot_surface(X, Y, H, facecolors=C, rstride=1, cstride=1, linewidth=0, antialiased=False, shade=False)
        ax.set_box_aspect((x1 - x0, y1 - y0, 1.6 * (H.max() - H.min())))
        ax.view_init(elev=32, azim=-75)
        ax.set_axis_off()
        ax.set_title("%s (orange: added to the map)" % name, fontsize=10)
        fig.savefig(os.path.join(out_dir, key + "_obliquo.jpg"), dpi=110, bbox_inches="tight")
        plt.close(fig)
    json.dump(stats, open(os.path.join(out_dir, "stats.json"), "w"), indent=1)
    print(stats)


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview(sys.argv[sys.argv.index("--preview") + 1])
    else:
        compute()
