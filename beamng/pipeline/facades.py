"""Facades of the buildings (v2.2): windows, doors, garage doors, shop fronts and plinths on every
wall of swissBUILDINGS3D, and the materials of walls and roofs.

Until v2.1 every building was a block of plaster in one tone without a window. Now:
- every building gets the attributes of the Federal Register of Buildings (GWR, download_gwr.py) whose
  reference point lies in its footprint: use (dwelling, industry, church, farm building, garage ...),
  year or period of construction, number of floors;
- a style follows from them and from the building (a hash of its id makes the choices repeatable):
  old houses with granite surrounds and wooden shutters, houses of the 1920s-1980s with painted
  surrounds and shutters or roller shutters, recent houses with aluminium windows and external blinds,
  rustici in rubble stone with boarded openings, workshops with ribbon windows and large doors,
  churches with arched windows; the shutter colours and plaster tones are drawn from the ones seen
  along the streets of the area (the tone measured in the Street View panoramas where the building
  was seen, sv_facades.py -> dati/facade_colors.json);
- every planar facade is divided into floors (from the eaves down, the floor height from the height
  of the building and its number of floors) and bays; an opening is placed only where it fits inside
  the wall, above the ground in front of it and not against a neighbouring building (party walls stay
  blank); the ground floor facing the nearest street gets the door (and a garage door or shop fronts
  where the building's use has them), lower floors appear where the ground falls away;
- a plinth band runs along the foot of the walls;
- balconies on many houses of the 1950s-2020s (a slab in the tone of the house, a railing of bars or
  frosted glass drawn in the atlas, the door onto it): one per bay, in pairs or along the whole facade,
  on the front and the sunny side (apartment blocks of four floors or more on every side but the north);
- roofs: flat roofs (gravel) below 8 degrees, pitched roofs in canal tiles (coppi), flat tiles, stone
  slabs (piode) or metal sheet after their colour in the orthophoto and the building's age and use.
The openings are quads 3 cm in front of the wall with the atlas of bld_textures.py (alpha clip); the
wall keeps its own triangles.
"""
import hashlib, json, os
import numpy as np
import shapely
from config import WORK

OFFSET = 0.03            # m, openings in front of the wall (no z-fighting, shutters stand out)
PLINTH_OFF = 0.015       # m, plinth band in front of the wall
PLINTH_STEP = 2.0        # m between the vertices of the plinth band
EAVE_GAP = 0.35          # m between the top of the upper windows' floor and the eaves
EAVE_RUN = 4.0           # m (and a fifth of the wall), least level part of a wall's top giving its eaves
EAVE_LEVEL = 0.15        # m of rise between the samples of the top (0.5 m apart) of a level part
MIN_FACADE = 1.4         # m, narrower facades stay blank
EDGE = 0.45              # m, openings keep this far from the corners
BLOCK_OUT = 0.7          # m in front of an opening: another building there hides it (party wall)
DARK_ROOF = 0.2          # luminance of a roof in the orthophoto under which its colour is the shade, not the roof
PART_MIN = 12.0          # m2, least house of the survey inside a block of swissBUILDINGS3D that gets its own facades
FLOOR_MIN = 2.6          # m, lowest floor height the register's number of floors may give (it counts attics too)
MAIN_FRONT = 8.0         # m: a main street at most this much farther than the nearest road is the front
BAL_SLAB = 0.16          # m, thickness of a balcony slab
BAL_RAIL = 1.05          # m, height of its railing
BAL_P = {"mid": 0.45, "late": 0.7, "new": 0.65}    # houses of these ages with balconies
BAL_MODE = {"mid": {"each": 60, "pair": 40}, "late": {"each": 30, "pair": 40, "run": 30},
            "new": {"each": 20, "pair": 30, "run": 50}}
BAL_RAILS = {"mid": {"dark": 50, "green": 20, "light": 30}, "late": {"dark": 40, "light": 40, "glass": 20},
             "new": {"glass": 50, "light": 30, "dark": 20}}
FACADE_COLORS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "facade_colors.json")

# plaster tones (sRGB) by age, from what is seen along the streets of the Malcantone
TONES = {
    "old": [(0.88, 0.81, 0.67), (0.86, 0.74, 0.53), (0.90, 0.85, 0.72), (0.85, 0.72, 0.62), (0.80, 0.78, 0.73),
            (0.92, 0.90, 0.85), (0.88, 0.79, 0.57), (0.79, 0.64, 0.54), (0.84, 0.80, 0.70)],
    "mid": [(0.93, 0.91, 0.86), (0.92, 0.87, 0.75), (0.90, 0.83, 0.63), (0.88, 0.80, 0.69), (0.87, 0.79, 0.73),
            (0.83, 0.83, 0.79), (0.91, 0.88, 0.80), (0.86, 0.76, 0.62)],
    "new": [(0.95, 0.95, 0.93), (0.86, 0.86, 0.84), (0.93, 0.90, 0.83), (0.70, 0.70, 0.69), (0.90, 0.87, 0.80)],
    "work": [(0.82, 0.82, 0.80), (0.72, 0.74, 0.74), (0.87, 0.86, 0.81), (0.60, 0.62, 0.64), (0.78, 0.76, 0.70)],
}
SHUTTER_MIX = {
    "old": {"verde": 30, "verde_scuro": 15, "marrone": 20, "legno": 15, "grigio": 12, "bordeaux": 5, "azzurro": 3},
    "interwar": {"verde": 30, "verde_scuro": 15, "marrone": 25, "grigio": 15, "legno": 10, "bordeaux": 5},
    "mid": {"verde": 20, "marrone": 25, "legno": 15, "grigio": 20, "bianco": 10, "azzurro": 5, "bordeaux": 5},
    "late": {"grigio": 30, "bianco": 25, "marrone": 20, "legno": 15, "verde": 10},
}
# window family by age: shutters, roller shutters, modern windows
FAMILY_MIX = {"old": {"granite": 75, "shutters": 25}, "interwar": {"shutters": 85, "roller": 15},
              "mid": {"shutters": 55, "roller": 45}, "late": {"shutters": 35, "roller": 40, "modern": 25},
              "new": {"modern": 80, "roller": 20}}
PERIOD_YEAR = {8011: 1880, 8012: 1932, 8013: 1953, 8014: 1965, 8015: 1975, 8016: 1983, 8017: 1988, 8018: 1993,
               8019: 1998, 8020: 2003, 8021: 2008, 8022: 2013, 8023: 2019}


def rng_of(key):
    return np.random.default_rng(int(hashlib.md5(key.encode()).hexdigest()[:12], 16))


def pick(rng, mix):
    k = list(mix)
    p = np.array([mix[i] for i in k], float)
    return k[int(rng.choice(len(k), p=p / p.sum()))]


# ------------------------------------------------------------------ register and styles
def footprint(b):
    import buildings_mesh
    return buildings_mesh.footprint(b)


def gwr_join(blds, fps):
    """GWR records of every building: {uuid: record}. First through the cadastral survey: the MU building
    that covers most of the footprint and its EGID (REA_EGID); otherwise the records whose reference
    point lies in the footprint (or within 2 m of it). Several records in one footprint (row houses
    surveyed as one building) are merged (most floors, oldest year)."""
    f = os.path.join(WORK, "gwr.json")
    if not os.path.exists(f):
        return {}
    recs = [r for r in json.load(open(f))["buildings"] if r.get("gstat", 1004) in (1004, 1003, 1005)]
    by_egid = {str(r["egid"]): r for r in recs if "egid" in r}
    out = {}

    def merge(uid, r):
        if uid not in out:
            out[uid] = dict(r)
            return
        o = out[uid]
        o["gastw"] = max(o.get("gastw", 0), r.get("gastw", 0)) or o.get("gastw")
        for k in ("gbauj", "gbaup"):
            if k in r:
                o[k] = min(o.get(k, 99999), r[k])
        o["n"] = o.get("n", 1) + 1
    # 1. through the survey's EGID
    avf = os.path.join(WORK, "av_local.pkl")
    if os.path.exists(avf):
        import pickle
        mu = [(g, p.get("REA_EGID")) for g, p in pickle.load(open(avf, "rb"))["LCSF"].get("edificio", [])]
        mtree = shapely.STRtree([g for g, _ in mu])
        for bi, fp in enumerate(fps):
            if fp.is_empty or fp.area < 1:
                continue
            best, share = None, 0.0
            for j in mtree.query(fp, predicate="intersects"):
                a = shapely.intersection(fp, mu[j][0]).area / fp.area
                if a > share:
                    best, share = mu[j][1], a
            if best and share > 0.3 and str(best) in by_egid:
                merge(blds[bi]["uuid"], by_egid[str(best)])
    # 2. the reference points of the register
    tree = shapely.STRtree(fps)
    pts = shapely.points([r["x"] for r in recs], [r["y"] for r in recs])
    hit_p, hit_b = tree.query(pts, predicate="dwithin", distance=2.0)
    best = {}
    for p, bi in zip(hit_p, hit_b):
        d = shapely.distance(fps[bi], pts[p])
        if p not in best or d < best[p][0]:
            best[p] = (d, bi)
    for p, (d, bi) in best.items():
        uid = blds[bi]["uuid"]
        if uid in out and str(recs[p].get("egid")) == str(out[uid].get("egid")):
            continue
        if uid not in out:
            merge(uid, recs[p])
    return out


def mu_parts(blds, fps):
    """The houses of the cadastral survey inside every building of swissBUILDINGS3D that holds several (a row of
    houses of a village core is one block there): {uuid: [(footprint of the house, its EGID or None), ...]},
    for the buildings with two or more; a house counts when the block covers half of it and PART_MIN m2."""
    avf = os.path.join(WORK, "av_local.pkl")
    if not os.path.exists(avf):
        return {}
    import pickle
    mu = [(g, p.get("REA_EGID")) for g, p in pickle.load(open(avf, "rb"))["LCSF"].get("edificio", [])]
    mtree = shapely.STRtree([g for g, _ in mu])
    out = {}
    for bi, fp in enumerate(fps):
        if fp.is_empty or fp.area < 2 * PART_MIN:
            continue
        parts = []
        for j in mtree.query(fp, predicate="intersects"):
            g, egid = mu[j]
            a = shapely.intersection(fp, g).area
            if a >= PART_MIN and a >= 0.5 * g.area:
                parts.append((shapely.intersection(fp, g), str(egid) if egid else None))
        if len(parts) >= 2:
            out[blds[bi]["uuid"]] = parts
    return out


def gwr_by_egid():
    """{EGID: record} of the register (download_gwr.py)."""
    f = os.path.join(WORK, "gwr.json")
    if not os.path.exists(f):
        return {}
    return {str(r["egid"]): r for r in json.load(open(f))["buildings"]
            if "egid" in r and r.get("gstat", 1004) in (1004, 1003, 1005)}


def year_of(rec):
    if rec.get("gbauj"):
        return int(rec["gbauj"])
    return PERIOD_YEAR.get(rec.get("gbaup"))


def age_class(year):
    if year is None:
        return None
    if year < 1919:
        return "old"
    if year < 1946:
        return "interwar"
    if year < 1981:
        return "mid"
    if year < 2001:
        return "late"
    return "new"


SV_SAT = 1.25          # the tones measured in the panoramas come out greyer than the facades (haze, shade)
SV_LIFT = 0.60         # ... and darker: the luminance L becomes 1 - (1 - L) SV_LIFT (a facade in the shade, the
                       # exposure of the camera against the sky), the hue and saturation stay
SV_SHUTTERS = ("verde", "verde_scuro", "bordeaux", "grigio")   # shutter colours the measurement tells apart
SV_BROWN = ("marrone", "legno")                                 # brown: also dark glass and shade, so more is needed
SHOP_FRONT = ("shop=", "craft=", "office=", "amenity=restaurant", "amenity=cafe", "amenity=bar", "amenity=pub",
              "amenity=bank", "amenity=pharmacy", "amenity=post_office", "amenity=fast_food", "amenity=ice_cream",
              "tourism=hotel", "tourism=guest_house")


def sv_tone(rgb):
    """A tone measured in the panoramas: its saturation brought back (SV_SAT around its luminance) and its
    luminance lifted (SV_LIFT)."""
    c = np.asarray(rgb, float)
    y = float(c @ np.array([0.2126, 0.7152, 0.0722]))
    c = y + (c - y) * SV_SAT
    y2 = 1.0 - (1.0 - y) * SV_LIFT
    return np.clip(c * (y2 / max(y, 1e-3)), 0, 1)


def shop_front(kind):
    """Whether a point of interest of OSM (osm.pois kind) has a shop front on the street."""
    return any(kind.startswith(k) for k in SHOP_FRONT)


def style_of(b, rec, area, height, roof_rgb, measured=None, shutter=None, shop=False, key=None):
    """What a building looks like: kind, age class, material, tone, window family, shutter colour.
    measured: the plaster tone seen in the photos; shutter: (colour, share of the facade) seen there;
    shop: a shop, bar, office ... of OSM in the building (a shop front on the ground floor); key: of the
    random choices (default the building's id; a house of a block has its own)."""
    rng = rng_of(key or b["uuid"])
    klass, cat = rec.get("gklas"), rec.get("gkat")
    kind = b["kind"]
    year = year_of(rec)
    age = age_class(year)
    if kind in ("Sakrales Gebaeude", "Kapelle") or klass == 1272:
        use = "church"
    elif kind in ("Sakraler Turm", "Turm"):
        use = "tower"
    elif kind in ("Lagertank", "Treibhaus", "Flugdach", "Mauer gross"):
        use = "none"
    elif (klass in (1251, 1252) or (cat == 1060 and klass is None)) and area < 60:
        # a small storage building or workshop: in the villages the old ones are rustici and sheds, not
        # workshops with ribbon windows
        use = "rural" if age in ("old", "interwar", "mid", None) and area >= 15 else "shed"
    elif klass in (1251, 1252) or (cat == 1060 and area > 400 and klass not in (1271, 1276, 1277, 1278)):
        use = "work"
    elif klass in (1220, 1230, 1231, 1241, 1261, 1262, 1263, 1264, 1265, 1211, 1212, 1130, 1275, 1273, 1274) and area > 60:
        use = "public"
    elif klass == 1242 or (cat == 1060 and area < 45):
        use = "garage"
    elif klass in (1271, 1276, 1277, 1278):
        use = "rural"
    elif cat in (1020, 1030, 1040) or klass in (1110, 1121, 1122):
        use = "house"
    elif not rec and height < 4.5 and 15 <= area < 250:   # no register entry, one low storey: garages
        use = "garage"
    elif not rec:                                      # no register entry: small sheds and rustici
        use = "shed" if area < 25 else ("rural" if area < 90 and height < 7.5 else "house")
    else:
        use = "house"
    if age is None:
        age = "old" if use == "rural" else ("mid" if use in ("house", "public", "garage") else "late")
    tone_set = {"old": "old", "interwar": "old", "mid": "mid", "late": "mid", "new": "new"}[age]
    if use in ("work", "garage", "shed"):
        tone_set = "work"
    tone = np.array(TONES[tone_set][int(rng.integers(len(TONES[tone_set])))], float)
    tone *= 1 + rng.normal(0, 0.025, 3)
    if measured is not None:                           # the tone seen in the panoramas
        tone = np.asarray(measured, float)
    stone = use in ("rural", "shed") and age in ("old", "interwar") and rng.random() < 0.8
    if use == "house" and age == "old" and rng.random() < 0.08:
        stone = True                                   # an old house left in bare stone
    fam = pick(rng, FAMILY_MIX[age if age != "interwar" else "interwar"])
    sh = pick(rng, SHUTTER_MIX["old" if age == "old" else ("interwar" if age == "interwar" else
                                                           ("mid" if age == "mid" else "late"))])
    older = age in ("old", "interwar", "mid")
    col, frac = shutter if shutter else (None, 0.0)
    if col in SV_SHUTTERS and frac >= 0.05:            # the shutters seen in the panoramas
        sh = col
        if fam in ("roller", "modern") and older:
            fam = "shutters"
    elif col in SV_BROWN and frac >= 0.10 and fam in ("shutters", "granite"):
        sh = col
    return {"use": use, "age": age, "year": year, "stone": stone, "tone": np.clip(tone, 0, 1), "family": fam,
            "shutter": sh, "closed": float(rng.uniform(0.0, 0.25)), "floors": rec.get("gastw"),
            "french": float(rng.uniform(0.1, 0.35)) if use == "house" and age in ("interwar", "mid", "late") else 0.0,
            "plinth": use in ("house", "public", "church") and not stone,
            "plinth_h": float(rng.uniform(0.45, 0.8)) if age in ("old", "interwar") else float(rng.uniform(0.3, 0.6)),
            # shop fronts on the ground floor: a shop of OSM in the building, or a building of the register
            # used in part for trade or offices (mixed use) on a main street
            "shop": bool(shop), "mixed": cat in (1030, 1040) or klass in (1220, 1230),
            # balconies (1950s-2020s houses): how many, how they run along the facade, the railing
            "balcony": use == "house" and not stone and age in BAL_P and rng.random() < BAL_P[age],
            "bal_mode": pick(rng, BAL_MODE[age]) if age in BAL_MODE else "each",
            "bal_rail": pick(rng, BAL_RAILS[age]) if age in BAL_RAILS else "dark",
            "bal_depth": float(rng.uniform(1.1, 1.5)),
            "seed": int(rng.integers(1 << 30))}


# ------------------------------------------------------------------ roofs
def roof_kind(style, slope_deg, rgb):
    """Covering of a roof face: flat, coppi, tegole, piode or metal. A roof darker than DARK_ROOF in the
    orthophoto (a small roof in the shade of its neighbours) tells nothing: its covering follows the age."""
    if slope_deg < 8.0:
        return "flat"
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    sat = (mx - mn) / max(mx, 1e-6)
    use, age = style["use"], style["age"]
    if 0.2126 * r + 0.7152 * g + 0.0722 * b < DARK_ROOF:
        if use in ("work", "garage") and slope_deg < 25:
            return "metal"
        if use in ("rural", "shed") and age in ("old", "interwar"):
            return "piode" if style["seed"] % 3 == 0 else "coppi"
        return "coppi" if age in ("old", "interwar") else "tegole"
    warm = r > b + 0.04 and sat > 0.12
    if use in ("work", "garage", "shed") and not warm and slope_deg < 25:
        return "metal"
    if not warm:
        if use in ("rural", "shed") or age in ("old", "interwar"):
            return "piode"
        return "tegole"                                # grey concrete tiles of the newer houses
    if age in ("old", "interwar") or use in ("church", "tower"):
        return "coppi"
    return "tegole" if age in ("late", "new") else ("coppi" if (style["seed"] % 3) else "tegole")


# ------------------------------------------------------------------ facades
class Context:
    """What the layout needs around a building: ground heights, the other buildings (party walls), the
    streets (which side is the front, shop fronts on the main streets)."""

    def __init__(self, blds, fps, ground, streets=None):
        self.ground = ground                                   # (x, y) -> z of the bare ground
        tops = np.array([max(b["walls"][..., 2].max() if len(b["walls"]) else -1e9,
                             b["roofs"][..., 2].max() if len(b["roofs"]) else -1e9) for b in blds])
        self.fps, self.tops = fps, tops
        self.tree = shapely.STRtree(fps)
        self.index = {b["uuid"]: i for i, b in enumerate(blds)}
        self.streets = streets                                 # (cKDTree of stations, is_main per station)

    def blocked(self, uid, x, y, z):
        """Points (x, y, z) inside another building (its footprint, under its top)."""
        me = self.index.get(uid, -1)
        pts = shapely.points(x, y)
        out = np.zeros(len(pts), bool)
        pi, bi = self.tree.query(pts, predicate="within")
        for p, bb in zip(pi, bi):
            if bb != me and z[p] < self.tops[bb] - 0.2:
                out[p] = True
        return out

    def street_dir(self, cx, cy):
        """Unit vector from (cx, cy) towards the nearest street station, its distance and whether that
        street is a main one."""
        if self.streets is None:
            return None, 1e9, False
        tree, main = self.streets
        dd, jj = tree.query([cx, cy], k=24)
        ok = np.isfinite(dd)
        dd, jj = dd[ok], jj[ok]
        if not len(dd):
            return None, 1e9, False
        # a main street not much farther than the nearest road is the front (the square of a village core
        # rather than the alley behind the house)
        m = main[jj] & (dd < dd[0] + MAIN_FRONT)
        k = int(np.argmax(m)) if m.any() else 0
        d, j = float(dd[k]), int(jj[k])
        v = tree.data[j] - np.array([cx, cy])
        return v / max(np.linalg.norm(v), 1e-9), d, bool(main[j])


def facade_polygon(tris, a):
    """The facade (triangles in their plane) as a valid polygon in (u, z)."""
    polys = shapely.polygons([np.column_stack([t @ a, t[:, 2]]) for t in tris])
    polys = shapely.make_valid(shapely.set_precision(polys, 0.001))
    polys = [q for g in polys for q in shapely.get_parts(g) if q.geom_type == "Polygon" and q.area > 1e-5]
    if not polys:
        return None
    F = shapely.union_all(polys).buffer(0.02, join_style="mitre").buffer(-0.02, join_style="mitre")
    F = shapely.make_valid(shapely.set_precision(F, 0.001))
    parts = [q for q in shapely.get_parts(F) if q.geom_type == "Polygon" and q.area > 1e-4]
    if not parts:
        return None
    return shapely.union_all(parts)


def top_profile(F, us):
    """Highest z of the facade polygon over every u (NaN where the facade has none)."""
    x0, z0, x1, z1 = F.bounds
    lines = shapely.linestrings([[[u, z0 - 1], [u, z1 + 1]] for u in us])
    try:
        inter = shapely.intersection(lines, F)
    except shapely.errors.GEOSException:
        inter = shapely.intersection(lines, F.buffer(0))
    out = np.full(len(us), np.nan)
    for k, g in enumerate(inter):
        if not g.is_empty:
            out[k] = shapely.bounds(g)[3]
    return out


class Emitter:
    """Collects the quads of the openings and of the plinth bands."""

    def __init__(self, index):
        self.index = index
        self.V, self.UV = [], []                # openings: triangles (k, 3, 3), uvs (k, 3, 2)
        self.PV, self.PUV, self.PC = [], [], []  # plinth
        self.BV, self.BC = [], []                # balcony slabs (k, 2, 3, 3), colour of each

    def quad(self, o, a, n, u0, u1, z0, z1, uv, off):
        """A quad of the facade plane point o + u a + z up, off in front of it, uv (u0, v0, u1, v1)."""
        def P(u, z):
            return o + u * a + np.array([0, 0, z]) + n * off
        c = [P(u0, z0), P(u1, z0), P(u1, z1), P(u0, z1)]
        t = [(uv[0], uv[1]), (uv[2], uv[1]), (uv[2], uv[3]), (uv[0], uv[3])]
        return np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]]), np.array([[t[0], t[1], t[2]], [t[0], t[2], t[3]]])

    def opening(self, name, o, a, n, uc, zb):
        m = self.index[name]
        V, T = self.quad(o, a, n, uc - m["w"] / 2, uc + m["w"] / 2, zb, zb + m["h"], m["uv"], OFFSET)
        self.V.append(V)
        self.UV.append(T)

    def balcony(self, o, a, n, u0, u1, zf, depth, rail, color):
        """A balcony on the facade plane (o, a along it, n out): a slab with its top at zf, depth m out from
        the wall between u0 and u1, and the railing module `rail` on its three free sides (both faces)."""
        z0, z1 = zf - BAL_SLAB, zf
        P = lambda u, dd, z: o + u * a + n * dd + np.array([0.0, 0.0, z])
        quads = [(P(u0, 0.02, z1), P(u0, depth, z1), P(u1, depth, z1), P(u1, 0.02, z1)),          # top
                 (P(u0, 0.02, z0), P(u1, 0.02, z0), P(u1, depth, z0), P(u0, depth, z0)),          # bottom
                 (P(u0, depth, z0), P(u1, depth, z0), P(u1, depth, z1), P(u0, depth, z1)),        # front
                 (P(u1, 0.02, z0), P(u1, 0.02, z1), P(u1, depth, z1), P(u1, depth, z0)),          # side u1
                 (P(u0, 0.02, z0), P(u0, depth, z0), P(u0, depth, z1), P(u0, 0.02, z1))]          # side u0
        for q in quads:
            self.BV.append(np.array([[q[0], q[1], q[2]], [q[0], q[2], q[3]]]))
            self.BC.append(color)
        m = self.index[rail]
        uv = m["uv"]
        top = z1 + BAL_RAIL
        # front: segments of about the module's width, textured facing out and facing in
        nseg = max(1, int(round((u1 - u0) / m["w"])))
        edges = np.linspace(u0 + 0.02, u1 - 0.02, nseg + 1)
        for ua, ub in zip(edges[:-1], edges[1:]):
            c = [P(ua, depth - 0.02, z1), P(ub, depth - 0.02, z1), P(ub, depth - 0.02, top), P(ua, depth - 0.02, top)]
            self._rail(c, uv)
        for u, sgn in ((u0 + 0.02, 1), (u1 - 0.02, -1)):
            c = [P(u, depth - 0.02, z1), P(u, 0.05, z1), P(u, 0.05, top), P(u, depth - 0.02, top)]
            if sgn < 0:
                c = [c[1], c[0], c[3], c[2]]
            self._rail(c, uv)

    def _rail(self, c, uv):
        t = [(uv[0], uv[1]), (uv[2], uv[1]), (uv[2], uv[3]), (uv[0], uv[3])]
        for cc, tt in ((c, t), ([c[1], c[0], c[3], c[2]], [t[1], t[0], t[3], t[2]])):
            self.V.append(np.array([[cc[0], cc[1], cc[2]], [cc[0], cc[2], cc[3]]]))
            self.UV.append(np.array([[tt[0], tt[1], tt[2]], [tt[0], tt[2], tt[3]]]))

    def plinth(self, o, a, n, us, zlo, zhi, color):
        for k in range(len(us) - 1):
            if not (np.isfinite(zlo[k]) and np.isfinite(zlo[k + 1])):
                continue
            P = lambda u, z: o + u * a + np.array([0, 0, z]) + n * PLINTH_OFF
            c = [P(us[k], zlo[k]), P(us[k + 1], zlo[k + 1]), P(us[k + 1], zhi[k + 1]), P(us[k], zhi[k])]
            v0 = 0.0
            # v: 0 at the bottom of the band's texture, 1 at its top edge; u every 4 m
            t = [(us[k] / 4.0, v0), (us[k + 1] / 4.0, v0), (us[k + 1] / 4.0, 1.0), (us[k] / 4.0, 1.0)]
            self.PV.append(np.array([[c[0], c[1], c[2]], [c[0], c[2], c[3]]]))
            self.PUV.append(np.array([[t[0], t[1], t[2]], [t[0], t[2], t[3]]]))
            self.PC.append(color)


def window_name(style, rng, floor_k):
    fam, sh = style["family"], style["shutter"]
    if fam == "granite":
        return f"win_{sh}_granite"
    if fam == "shutters":
        if rng.random() < style["closed"]:
            return f"win_{sh}_closed"
        return f"win_{sh}"
    if fam == "roller":
        col = {"bianco": "white", "grigio": "grey", "marrone": "brown", "legno": "brown"}.get(sh, "white")
        return "roller_white_down" if rng.random() < style["closed"] * 0.6 else f"roller_{col}"
    return "modern_blind_down" if rng.random() < style["closed"] * 0.6 else \
        ("modern_open" if rng.random() < 0.3 else "modern_blind")


def door_name(style, rng):
    age = style["age"]
    if style["stone"]:
        return "door_boards_granite"
    if age == "old":
        return "door_wood_granite" if rng.random() < 0.7 else "door_boards_granite"
    if age in ("interwar", "mid"):
        return ["door_brown", "door_green", "door_grey", "door_wood_granite"][int(rng.integers(4))]
    return "door_modern" if rng.random() < 0.7 else "door_grey"


SILL = {"win": 0.9, "roller": 0.9, "modern": 0.7, "french": 0.0, "modern_tall": 0.05}


def layout_building(b, walls, style, ctx, em):
    """Openings and plinth of one building (walls: its wall triangles, outward)."""
    import texturing
    if style["use"] == "none" or not len(walls):
        return 0
    rng = np.random.default_rng(style["seed"])
    groups = texturing.facade_groups(walls)
    cx, cy = walls[..., :2].reshape(-1, 2).mean(0)
    sdir, sdist, main = ctx.street_dir(cx, cy)
    facs = []
    for idx, n, d0 in groups:
        tris = walls[idx]
        a = np.array([-n[1], n[0], 0.0])
        F = facade_polygon(tris, a)
        if F is None:
            continue
        u0, _, u1, _ = F.bounds
        if u1 - u0 < MIN_FACADE:
            continue
        o = np.array([n[0] * d0, n[1] * d0, 0.0])
        us = np.arange(u0, u1 + 1e-6, 0.5)
        if us[-1] < u1 - 0.05:
            us = np.r_[us, u1]
        px = o[0] + us * a[0] + n[0] * 0.4
        py = o[1] + us * a[1] + n[1] * 0.4
        g = ctx.ground(px, py)
        top = top_profile(F, us)
        if not np.isfinite(top).any() or not np.isfinite(g).any():
            continue
        facs.append((tris, np.asarray(n, float), a, o, F, us, g, top))
    if not facs:
        return 0
    # the floors of the building, from the eaves down
    gs = np.concatenate([f[6] for f in facs])
    gs = gs[np.isfinite(gs)]
    if not len(gs):
        return 0
    g_hi = float(np.percentile(gs, 80))

    def eave_of(f):
        us_, top_ = f[5], f[7]
        mid = (us_ > us_[0] + 0.3) & (us_ < us_[-1] - 0.3) & np.isfinite(top_)
        vals = top_[mid] if mid.any() else top_[np.isfinite(top_)]
        if not len(vals):
            return np.nan
        e = float(np.percentile(vals, 10))
        # v2.2: a wall of parts of different heights (a lower wing flush with the house): the eaves of its
        # highest level part at least EAVE_RUN m long, not those of the wing (a gable has no level part)
        t = np.where(mid, top_, np.nan)
        lvl = np.abs(np.diff(t)) < EAVE_LEVEL
        best, j = e, 0
        while j < len(lvl):
            if lvl[j]:
                j1 = j
                while j1 + 1 < len(lvl) and lvl[j1 + 1]:
                    j1 += 1
                if us_[j1 + 1] - us_[j] >= max(EAVE_RUN, 0.2 * (us_[-1] - us_[0])):
                    best = max(best, float(np.percentile(t[j:j1 + 2], 10)))
                j = j1 + 1
            else:
                j += 1
        return best
    eaves = [eave_of(f) for f in facs]
    widths = np.array([f[5][-1] - f[5][0] for f in facs])
    eaves = np.array(eaves, float)
    good = np.isfinite(eaves)
    if not good.any():
        return 0
    wide = good & (widths >= 3.0)
    use = style["use"]
    count = 0
    # the front: the facade facing the nearest street
    front = -1
    if sdir is not None:
        score = [float(f[1][:2] @ sdir) * (f[5][-1] - f[5][0]) ** 0.3 for f in facs]
        front = int(np.argmax(score)) if max(score) > 0.2 else -1
    # the eaves of the floors: those of the front (the facade seen from the street: an annex or a lower wing
    # at the back must not lower the floors of the house), else the median of the wide facades
    if front >= 0 and good[front]:
        z_e = float(eaves[front])
    else:
        z_e = float(np.median(eaves[wide])) if wide.any() else float(np.median(eaves[good]))
    # v2.2: the floors start at the ground in front of the front (the street side), or of the lowest wide
    # facade where no street is near: on a slope every floor is seen there, from the ground floor up, and
    # uphill the lower floors are under the ground (their openings do not fit). The number of floors of
    # the register holds when it gives floors of a plausible height, counted from the front or from the
    # uphill side (a house on a slope: the register counts the floors above the uphill ground)
    med_g = np.array([float(np.nanmedian(f[6])) if np.isfinite(f[6]).any() else np.nan for f in facs])
    if front >= 0 and np.isfinite(med_g[front]):
        g0 = float(med_g[front])
    else:
        cand = np.where(wide & np.isfinite(med_g), med_g, np.nan)
        g0 = float(np.nanmin(cand)) if np.isfinite(cand).any() else float(np.nanmin(med_g))
    g0 = min(g0, g_hi)
    H = z_e - EAVE_GAP - g0
    if not np.isfinite(H) or H < 1.9:
        return 0
    n_reg = style["floors"]
    h_f = None
    for Hc in (H, z_e - EAVE_GAP - g_hi):
        if n_reg and Hc >= 1.9 and FLOOR_MIN <= Hc / n_reg <= 3.9:
            h_f = Hc / n_reg
            break
    if h_f is None:
        h_f = 3.0 if style["age"] in ("mid", "late", "new") else 3.2
    n_f = max(1, int(round(H / h_f)))
    h_f = float(np.clip(H / n_f, 2.4, 3.9))
    fb0 = z_e - EAVE_GAP - n_f * h_f                   # bottom of the ground floor (at the front)
    # shop fronts on the ground floor of the front: a shop of OSM in the building, a mixed-use building of
    # the register on a main street, a public building (offices, trade) on a main street
    shops = style.get("shop") or (main and sdist < 15.0 and (use == "public" or (use == "house" and style.get("mixed"))))
    door_done = False
    for fi, (tris, n, a, o, F, us, g, top) in enumerate(facs):
        W = us[-1] - us[0]
        inner = F.buffer(-0.12)
        if inner.is_empty:
            continue
        shapely.prepare(inner)
        gl = lambda u: float(np.interp(u, us, g))

        def fits(uc, w, zb, h, ground_gap=0.15):
            ua, ub = uc - w / 2, uc + w / 2
            # openings at the foot of the wall (doors, garages) reach the ground: the wall may end there
            lift = 0.25 if ground_gap < 0 else 0.0
            if not inner.contains(shapely.box(ua, zb + lift, ub, zb + h)):
                return False
            if zb < max(gl(ua), gl(uc), gl(ub)) + ground_gap:
                return False
            # not against another building
            xs = o[0] + np.array([ua + 0.1, uc, ub - 0.1]) * a[0] + n[0] * BLOCK_OUT
            ys = o[1] + np.array([ua + 0.1, uc, ub - 0.1]) * a[1] + n[1] * BLOCK_OUT
            zs = np.full(3, zb + 0.5 * h)
            return not ctx.blocked(b["uuid"], xs, ys, zs).any()

        # bays
        if use in ("work",):
            bay = 3.0
        elif use == "church":
            bay = 4.5
        elif style["age"] in ("new",):
            bay = 3.8
        elif style["age"] in ("old",):
            bay = 2.9
        else:
            bay = 3.2
        nb = int(max(1, np.floor((W - 2 * EDGE) / bay + 0.35)))
        span = W - 2 * EDGE
        ucs = us[0] + EDGE + (np.arange(nb) + 0.5) * span / nb if span > 0.8 else np.array([0.5 * (us[0] + us[-1])])
        side = fi != front
        # blank bays: fewer windows on the sides and back of houses, none on some narrow gable walls
        keep = rng.random(len(ucs)) > (0.35 if side and use == "house" else 0.1)
        if use in ("garage", "shed"):
            keep[:] = False
            if use == "garage" and not side:            # a row of garage doors on the street side
                gname = ["garage_grey", "garage_white", "garage_brown"][int(style["seed"] % 3)]
                m = em.index[gname]
                pitch = m["w"] + 0.35
                ng = int(max(0, np.floor((W - 2 * 0.3 + 0.35) / pitch)))
                for j in range(ng):
                    uc = us[0] + 0.3 + (W - 2 * 0.3 - ng * pitch + 0.35) / 2 + j * pitch + m["w"] / 2
                    if fits(uc, m["w"], gl(uc) - 0.03, m["h"], ground_gap=-0.4):
                        em.opening(gname, o, a, n, uc, gl(uc) - 0.03)
                        count += 1
        # lower floors where the ground falls away along this facade; upper floors where this part of the
        # building rises over the eaves of the rest
        glo = np.nanmin(g) if np.isfinite(g).any() else fb0
        k_min = -int(max(0, np.floor((fb0 - glo - 0.4) / h_f)))
        e_f = eave_of((tris, n, a, o, F, us, g, top))
        k_max = n_f
        if np.isfinite(e_f) and use not in ("church", "tower"):
            k_max = max(n_f, int(np.floor((e_f - EAVE_GAP - fb0) / h_f + 0.25)))
        n_shop = 0
        # balconies: on the front and the sunny side of a house that has them, on bays chosen once for the
        # facade (every floor the same)
        bal_bays = np.zeros(len(ucs), bool)
        # (the front and the south; apartment blocks of four floors or more on every side but the north)
        sunny = n[1] < (0.3 if n_f >= 4 else -0.3)
        if style.get("balcony") and W >= 5.0 and len(ucs) >= 2 and (not side or sunny):
            mode = style["bal_mode"]
            if mode == "run":
                bal_bays[:] = True
            elif mode == "pair":
                start = int(rng.integers(2))
                for j in range(start, len(ucs) - 1, 3):
                    bal_bays[j:j + 2] = True
            else:
                bal_bays = rng.random(len(ucs)) < 0.7
        bay_w = (ucs[1] - ucs[0]) if len(ucs) > 1 else W
        runs = []                                        # (first, last) bays of every balcony
        j = 0
        while j < len(ucs):
            if bal_bays[j]:
                j1 = j
                while j1 + 1 < len(ucs) and bal_bays[j1 + 1] and style["bal_mode"] != "each":
                    j1 += 1
                runs.append((j, j1))
                j = j1 + 1
            else:
                j += 1
        for k in range(k_min, k_max):
            fb = fb0 + k * h_f
            done_bal = set()
            if k >= 1 and runs and h_f >= 2.6:
                for j0, j1 in runs:
                    ua = ucs[j0] - bay_w / 2 + 0.15
                    ub = ucs[j1] + bay_w / 2 - 0.15
                    ua, ub = max(ua, us[0] + 0.25), min(ub, us[-1] - 0.25)
                    depth = style["bal_depth"]
                    if ub - ua < 1.2:
                        continue
                    # the railing inside the wall's outline, nothing in front (another building)
                    if not inner.contains(shapely.box(ua, fb - BAL_SLAB, ub, fb + BAL_RAIL + 0.3)):
                        continue
                    xs = o[0] + np.array([ua, 0.5 * (ua + ub), ub]) * a[0] + n[0] * (depth + 0.3)
                    ys = o[1] + np.array([ua, 0.5 * (ua + ub), ub]) * a[1] + n[1] * (depth + 0.3)
                    if ctx.blocked(b["uuid"], xs, ys, np.full(3, fb + 0.5)).any():
                        continue
                    if fb - BAL_SLAB < max(gl(ua), gl(ub)) + 2.2:          # well above the ground
                        continue
                    em.balcony(o, a, n, ua, ub, fb, depth, "railing_" + style["bal_rail"],
                               np.clip(np.asarray(style["tone"]) * 1.04, 0, 1))
                    count += 1
                    for jj in range(j0, j1 + 1):
                        done_bal.add(jj)
            for j, uc in enumerate(ucs):
                if j in done_bal:                        # the door onto the balcony
                    fam = style["family"]
                    if fam in ("shutters", "granite"):
                        nm = "bal_" + style["shutter"]
                    elif fam == "roller":
                        nm = "bal_roller_" + {"bianco": "white", "grigio": "grey", "marrone": "brown",
                                              "legno": "brown"}.get(style["shutter"], "white")
                    else:
                        nm = "modern_tall"
                    m = em.index[nm]
                    if fits(uc, m["w"], fb + 0.02, m["h"]):
                        em.opening(nm, o, a, n, uc, fb + 0.02)
                        count += 1
                    continue
                if not keep[j] and not (k == 0 and fi == front and not door_done):
                    continue
                name = None
                zb = None
                ground_floor = abs(fb - gl(uc)) < 0.6 or k < 0 and abs(fb - gl(uc)) < 1.2
                # ground floor of the front: door, garage, shop
                if use in ("house", "public", "rural") and k <= 0 and fi == front and ground_floor and not door_done:
                    nm = door_name(style, rng) if use != "rural" else "barn_door"
                    m = em.index[nm]
                    zg = gl(uc)
                    if fits(uc, m["w"], zg - 0.03, m["h"], ground_gap=-0.4):
                        em.opening(nm, o, a, n, uc, zg - 0.03)
                        door_done = True
                        count += 1
                        continue
                if k <= 0 and ground_floor and fi == front and shops and use in ("house", "public") and \
                        (n_shop == 0 or rng.random() < 0.75):
                    nm = "shop" if rng.random() < 0.6 else "shop_light"
                    m = em.index[nm]
                    zg = gl(uc)
                    if h_f >= 2.9 and fits(uc, m["w"], zg - 0.03, m["h"], ground_gap=-0.4):
                        em.opening(nm, o, a, n, uc, zg - 0.03)
                        count += 1
                        n_shop += 1
                        continue
                if k <= 0 and ground_floor and fi == front and use == "house" and nb >= 3 and not shops and \
                        rng.random() < 0.25:
                    nm = ["garage_white", "garage_grey", "garage_brown", "garage_wood"][
                        int(rng.integers(4)) if style["age"] not in ("old", "interwar") else 3]
                    m = em.index[nm]
                    zg = gl(uc)
                    if fits(uc, m["w"], zg - 0.03, m["h"], ground_gap=-0.4):
                        em.opening(nm, o, a, n, uc, zg - 0.03)
                        count += 1
                        continue
                if use == "work":
                    if k == 0 and ground_floor and rng.random() < 0.35:
                        nm = "garage_grey" if rng.random() < 0.7 else "garage_white"
                        m = em.index[nm]
                        if fits(uc, m["w"], gl(uc) - 0.03, m["h"], ground_gap=-0.4):
                            em.opening(nm, o, a, n, uc, gl(uc) - 0.03)
                            count += 1
                            continue
                    name, zb = ("ribbon" if style["seed"] % 2 else "ribbon_dark"), fb + 1.3
                elif use == "church":
                    name, zb = "church", fb + 2.2
                    if k > 0:
                        continue
                elif use == "tower":
                    continue
                elif use == "rural":
                    name, zb = ("small" if k <= 0 else "barn"), fb + (1.0 if k <= 0 else 0.6)
                    if rng.random() < 0.4:
                        continue
                elif k < 0 and fb < gl(uc) - 0.3:
                    # a floor partly under the ground here: a basement window
                    name, zb = "small_grille", fb + 1.0
                else:
                    name = window_name(style, rng, k)
                    if k > 0 and style["french"] and rng.random() < style["french"] and name.startswith("win_") \
                            and "granite" not in name and "closed" not in name and h_f >= 2.6:
                        name = "french_" + style["shutter"]
                    kind = "french" if name.startswith("french") else ("roller" if name.startswith("roller") else
                                                                      ("modern" if name.startswith("modern") else "win"))
                    if name == "modern_blind" and k > 0 and rng.random() < 0.25 and h_f >= 2.6:
                        name, kind = "modern_tall", "modern_tall"
                    zb = fb + SILL[kind]
                m = em.index[name]
                if fits(uc, m["w"], zb, m["h"]):
                    em.opening(name, o, a, n, uc, zb)
                    count += 1
                elif name.startswith("french_") or name == "modern_tall":
                    alt = f"win_{style['shutter']}" if name.startswith("french_") else "modern_blind"
                    m = em.index[alt]
                    zb = fb + SILL["win" if alt.startswith("win") else "modern"]
                    if fits(uc, m["w"], zb, m["h"]):
                        em.opening(alt, o, a, n, uc, zb)
                        count += 1
        # attic window in a tall gable (over the eaves of this part of the building)
        z_a = e_f if np.isfinite(e_f) else z_e
        if use == "house" and np.isfinite(top).any() and np.nanmax(top) - z_a > 2.2:
            uc = us[int(np.nanargmax(top))]
            m = em.index["vent"]
            zb = z_a + 0.6
            if fits(uc, m["w"], zb, m["h"]):
                em.opening("vent", o, a, n, uc, zb)
        # plinth along the foot of the wall (every PLINTH_STEP m: the ground varies slowly)
        if style["plinth"]:
            up = np.r_[np.arange(us[0], us[-1], PLINTH_STEP), us[-1]]
            gp = np.interp(up, us, g)
            zlo = gp - 0.25
            zhi = gp + style["plinth_h"]
            ok = shapely.contains_xy(F.buffer(0.05), up, gp + 0.5 * style["plinth_h"])
            xs = o[0] + up * a[0] + n[0] * BLOCK_OUT
            ys = o[1] + up * a[1] + n[1] * BLOCK_OUT
            ok &= ~ctx.blocked(b["uuid"], xs, ys, gp + 0.3)
            zlo = np.where(ok, zlo, np.nan)
            tone = np.clip(style["tone"] * 0.78, 0, 1) if style["age"] in ("mid", "late", "new") else \
                np.array([0.66, 0.65, 0.62])
            em.plinth(o, a, n, up, zlo, zhi, tone)
    return count


# ------------------------------------------------------------------ chimneys
CHIMNEY = {"old": (0.60, 0.50), "interwar": (0.55, 0.45), "mid": (0.45, 0.40), "late": (0.40, 0.40), "new": (0.35, 0.35)}


def chimneys(b, roofs, style):
    """Chimney stacks on the pitched roof of a house: (stack triangles, cap triangles). One near the
    ridge (two on long roofs), up to 0.9 m above the ridge, plastered like the walls, with a cap."""
    if style["use"] not in ("house", "public") or not len(roofs):
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 3))
    nrm = np.cross(roofs[:, 1] - roofs[:, 0], roofs[:, 2] - roofs[:, 0])
    ln = np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    slope = np.degrees(np.arccos(np.clip(np.abs(nrm[:, 2]) / ln, 0, 1)))
    area = 0.5 * ln
    if area[slope > 12].sum() < 0.7 * area.sum() or area.sum() < 45:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 3))
    rng = np.random.default_rng(style["seed"] + 7)
    if rng.random() < 0.15:                                    # a few houses without one visible
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 3))
    from road_mesh import TriSurface
    surf = TriSurface(roofs[slope > 12])
    P = roofs.reshape(-1, 3)
    ridge = P[:, 2].max()
    top_pts = P[P[:, 2] > ridge - 0.25][:, :2]
    c = top_pts.mean(0)
    # along the ridge
    if len(top_pts) >= 2:
        d = top_pts - c
        ax = np.linalg.svd(d, full_matrices=False)[2][0] if np.abs(d).max() > 0.3 else np.array([1.0, 0.0])
    else:
        ax = np.array([1.0, 0.0])
    span = float(np.ptp(top_pts @ ax)) if len(top_pts) >= 2 else 4.0
    n = 2 if span > 12 and rng.random() < 0.6 else 1
    w, dpt = CHIMNEY[style["age"]]
    stacks, caps = [], []
    for k in range(n):
        along = rng.uniform(-0.35, 0.35) * span if n == 1 else (-0.3 + 0.6 * k) * span
        side = np.array([-ax[1], ax[0]]) * rng.uniform(0.3, 1.2) * (1 if rng.random() < 0.5 else -1)
        q = c + ax * along + side
        corners = np.array([q + [sx * w / 2, sy * dpt / 2] for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        zr = surf.height(corners[:, 0], corners[:, 1], "high")
        if not np.isfinite(zr).all():
            continue
        zb = float(zr.min()) - 0.1
        zt = max(ridge + rng.uniform(0.4, 0.9), float(zr.max()) + 0.8)
        for i in range(4):
            a_, b_ = corners[i], corners[(i + 1) % 4]
            A, B = np.r_[a_, zb], np.r_[b_, zb]
            C, D = np.r_[b_, zt], np.r_[a_, zt]
            stacks += [[A, B, C], [A, C, D]]
        cc = np.array([q + [sx * (w / 2 + 0.07), sy * (dpt / 2 + 0.07)] for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        lo, hi = zt, zt + 0.08
        for i in range(4):
            a_, b_ = cc[i], cc[(i + 1) % 4]
            caps += [[np.r_[a_, lo], np.r_[b_, lo], np.r_[b_, hi]], [np.r_[a_, lo], np.r_[b_, hi], np.r_[a_, hi]]]
        caps += [[np.r_[cc[0], hi], np.r_[cc[1], hi], np.r_[cc[2], hi]], [np.r_[cc[0], hi], np.r_[cc[2], hi], np.r_[cc[3], hi]]]
    return np.array(stacks, float).reshape(-1, 3, 3), np.array(caps, float).reshape(-1, 3, 3)
