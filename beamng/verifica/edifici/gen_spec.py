"""Writes beamng/dati/edifici_veri.json from the hand notes below (facade ids of the inventory, /home/claude/work/inv)."""
import json, math
import numpy as np, shapely

INV = json.load(open("/home/claude/work/inv/facades.json"))
SITES = {s["id"]: s for s in json.load(open("/home/claude/magliasinaNG/beamng/verifica/edifici/sites.json"))["sites"]}
# the houses next to a site that its photos show too (e01b, e03b, e18b)
for k, v in json.load(open("/home/claude/work/inv/extra.json")).items():
    if k == "e01b":
        continue
    INV[k] = v["facades"]
    base = SITES[k[:3]]
    SITES[k] = dict(base, id=k, outline=v["outline"])
OUT = "/home/claude/magliasinaNG/beamng/dati/edifici_veri.json"

WHITE = [0.92, 0.91, 0.88]
LGREY = [0.87, 0.86, 0.83]
CREAM = [0.91, 0.86, 0.74]
BEIGE = [0.88, 0.80, 0.66]
YELLOW = [0.95, 0.80, 0.47]
OCHRE = [0.85, 0.73, 0.45]
ORANGE = [0.89, 0.57, 0.34]
SALMON = [0.87, 0.62, 0.52]
LPINK = [0.95, 0.76, 0.71]
HPINK = [0.79, 0.49, 0.44]
RED = [0.79, 0.40, 0.30]
GREY_BEIGE = [0.73, 0.71, 0.66]


def fac(sid, fid):
    f = next(x for x in INV[sid] if x["id"] == fid)
    az = math.radians(f["az"])
    n = np.array([math.sin(az), math.cos(az)])
    a = np.array([-n[1], n[0]])
    left = np.array(f["p"]) - a * f["len"] / 2
    return f, n, a, left


def F(sid, fid, **kw):
    f, *_ = fac(sid, fid)
    return dict(id=fid, az=f["az"], p=f["p"], **kw)


def line_off(sid, fid, u0, u1, d):
    """A line parallel to a facade, d m in front of it, from u0 to u1 (m from its left end)."""
    f, n, a, left = fac(sid, fid)
    return [[round(float(v), 2) for v in left + a * u + n * d] for u in (u0, u1)]


def rect_in(sid, fid, u0, u1, d0, d1):
    """A rectangle on the roof behind a facade: u0..u1 along it, d0..d1 m inward."""
    f, n, a, left = fac(sid, fid)
    return [[round(float(v), 2) for v in left + a * u - n * d] for u, d in ((u0, d0), (u1, d0), (u1, d1), (u0, d1))]


def shutters(col, u=None, z=None):
    r = {"map": {"win_*_closed": f"win_{col}_closed", "win_*": f"win_{col}", "french_*": f"french_{col}",
                 "bal_*": f"bal_{col}"}}
    if col in ("marrone", "verde", "grigio", "bianco", "bordeaux", "azzurro", "legno"):
        r["map"]["win_*_granite"] = f"win_{col}_granite"
    r["map"] = dict(sorted(r["map"].items(), key=lambda kv: -len(kv[0])))
    if u:
        r["u"] = u
    if z:
        r["z"] = z
    return r


def plain(u=None, z=None):
    r = {"map": {"win_*": "modern_open", "french_*": "modern_tall", "bal_*": "modern_tall"}}
    if u:
        r["u"] = u
    if z:
        r["z"] = z
    return r


S = []
# e01 Agno, Piazza Vicari: the pharmacy at the north end of the block toward the cantonal road (photos 1-2, 4-7: white,
# red shutters, iron balconies, shop windows); on the north side a yellow house with green shutters and an orange one
# (photo 3)
S.append(dict(id="e01", facades=[
    F("e01", "f1", tones=[[0, 12, WHITE]], swap=[
        {"u": [0, 12], "z": [-1, 2.2], "map": {"win_*": "shop_light", "french_*": "shop_light", "roller_*": "shop_light"}},
        shutters("bordeaux", u=[0, 12])],
      signs=[{"text": "FARMACIA", "u": 6.0, "z": 3.1, "h": 0.5, "color": [0.05, 0.5, 0.25], "bg": [0.97, 0.97, 0.95]}]),
    F("e01", "f13", tones=[[0, 10, YELLOW]], swap=[shutters("verde")]),
    F("e01", "f8", tones=[[0, 11, ORANGE]], swap=[shutters("verde")])]))
# e02 Agno, the coloured row along the cantonal road (photos 1-7): from the north-east corner an orange house with green
# shutters and a jeweller's, salmon, yellow with green shutters, white-grey, orange, and a grey-beige one at the end
S.append(dict(id="e02", facades=[
    F("e02", "f1", tones=[[0, 9, ORANGE], [9, 20, SALMON], [20, 30, YELLOW], [30, 40, LGREY], [40, 50, ORANGE],
                          [50, 59, GREY_BEIGE]],
      swap=[shutters("verde", u=[0, 9]), shutters("verde", u=[20, 30]), shutters("grigio", u=[30, 40]),
            {"u": [50, 59], "map": {"win_*": "small_grille", "french_*": "small_grille"}, "z": [-1, 2.5]},
            plain(u=[40, 59])]),
    # its south-west end on the square: orange, green shutters, a jeweller's (photos 1-2)
    F("e02", "f6", tones=[[0, 18, ORANGE]], swap=[shutters("verde")],
      signs=[{"text": "GIOIELLERIA", "u": 3.0, "z": 2.8, "h": 0.4, "color": [0.95, 0.95, 0.92], "bg": [0.12, 0.12, 0.12]}]),
    F("e02", "f7", tones=[[0, 25, ORANGE]], swap=[shutters("verde")])]))
# e03 Agno, Contrada San Marco: the yellow corner house with brown shutters and shops (south), salmon and pink houses
# with brown shutters north of it, a hairdresser's at the north end (photos 1-6)
S.append(dict(id="e03", facades=[
    F("e03", "f3", tones=[[0, 24, YELLOW]], swap=[{"z": [-1, 2.2], "map": {"win_*": "shop", "french_*": "shop"}},
                                                    shutters("marrone")]),
    F("e03", "f2", tones=[[0, 24, SALMON]], swap=[shutters("marrone")]),
    F("e03", "f1", tones=[[0, 26, [0.89, 0.75, 0.64]]], swap=[shutters("marrone")],
      signs=[{"text": "COIFFEUR", "u": 4.0, "z": 2.7, "h": 0.45, "color": [0.97, 0.97, 0.97], "bg": [0.12, 0.3, 0.68]}])]))
# e03b, the yellow corner house south of the row (e03 photos 1-2): brown shutters, shops on the ground floor
S.append(dict(id="e03b", tone=YELLOW, facades=[
    F("e03b", f, swap=[{"z": [-1, 2.2], "map": {"win_*": "shop", "french_*": "shop"}}, shutters("marrone")])
    for f in ("f1", "f3")] + [F("e03b", "f2", swap=[shutters("marrone")])]))
# e04 Magliaso, the long ochre building on the cantonal road (photos 5-7: plain yellow walls, chain-link fence)
S.append(dict(id="e04", tone=OCHRE, aerial=False, dish=False,
              fences=[{"line": line_off("e04", "f1", 3, 71, 4.0), "h": 1.6}]))
# e05 Magliaso, the houses at the Eni station: cream plaster (photos 1-2)
S.append(dict(id="e05", tone=CREAM))
# e06 Magliaso, the small supermarket: white, one row of shop windows, no house windows above (photos 1-3)
S.append(dict(id="e06", tone=WHITE, aerial=False, dish=False, facades=[
    F("e06", "f3", openings=[{"row": "shop", "z": 0.0, "from": 2.0, "to": 9.0, "n": 3}],
      signs=[{"text": "ALIMENTARI", "u": 5.5, "z": 2.9, "h": 0.55, "color": [0.92, 0.4, 0.08], "bg": [0.98, 0.98, 0.98]}])]))
# e08 Ponte Tresa, the hotel on the lake: pink, plain windows without shutters (photos 1-2)
S.append(dict(id="e08", tone=HPINK, aerial=False, dish=False, facades=[
    F("e08", f, swap=[plain()]) for f in ("f1", "f3", "f4", "f5", "f7")]))
# e09 Breno, the village shop: orange walls, solar panels on the north-east roof (orthophoto, photos 1-2)
S.append(dict(id="e09", tone=[0.93, 0.66, 0.33], aerial=False, dish=False, pv_add=[rect_in("e09", "f1", 2.5, 17.5, 5.0, 8.3)]))
# e10 Breno, the houses on the main street: white plaster, brown shutters (photos 1-4)
S.append(dict(id="e10", tone=[0.9, 0.88, 0.82], facades=[F("e10", f, swap=[shutters("marrone")]) for f in ("f7", "f2", "f8")]))
# e12 Vezio, the inn: yellow walls, green shutters (photos 1-2)
S.append(dict(id="e12", facades=[
    F("e12", "f1", tones=[[0, 22, [0.92, 0.83, 0.54]]], swap=[shutters("verde")],
      signs=[{"text": "OSTERIA", "u": 6.0, "z": 3.0, "h": 0.5, "color": [0.55, 0.1, 0.08], "bg": [0.96, 0.92, 0.8]}]),
    F("e12", "f3", tones=[[0, 12, [0.92, 0.83, 0.54]]], swap=[shutters("verde")])]))
# e13 Novaggio, the bank: light pink, brown shutters, solar panels on the south-east roof (photos 1-8, orthophoto)
S.append(dict(id="e13", tone=LPINK, aerial=False, dish=False, pv_add=[rect_in("e13", "f2", 1.0, 12.5, 0.8, 4.5)],
              facades=[F("e13", "f1", swap=[{"z": [-1, 2.2], "map": {"win_*": "shop_light", "french_*": "shop_light"}},
                                            shutters("marrone")],
                         signs=[{"text": "BANCA", "u": 6.5, "z": 3.0, "h": 0.45, "color": [0.85, 0.08, 0.12],
                                 "bg": [0.98, 0.98, 0.98]}])] +
              [F("e13", f, swap=[shutters("marrone")]) for f in ("f2", "f4", "f7")]))
# e14 Curio, the row houses: white with salmon entrance bays, roller blinds (photos 1-7)
S.append(dict(id="e14", tone=WHITE, aerial=False, facades=[
    F("e14", "f1", tones=[[6, 9, SALMON], [16, 19, SALMON], [27, 30, SALMON], [37, 40, SALMON]],
      swap=[{"map": {"win_*": "roller_white", "french_*": "roller_white", "bal_*": "bal_roller_white"}}])]))
# e15 Lema, the restaurant: cream walls (photos 1, 3)
S.append(dict(id="e15", tone=CREAM, facades=[
    F("e15", "f1", signs=[{"text": "RISTORANTE", "u": 9.5, "z": 2.2, "h": 0.5, "color": [0.15, 0.15, 0.15],
                           "bg": [0.95, 0.92, 0.82]}])]))
# e16 Pura, beige houses with brown shutters (photos 3, 5)
S.append(dict(id="e16", tone=BEIGE, facades=[F("e16", f, swap=[shutters("marrone")]) for f in ("f3", "f4", "f1")]))
# e17 Pura, cream houses (photos 1, 3)
S.append(dict(id="e17", tone=CREAM))
# e18 Pura, the white house with the long balconies on the bend, and the red-orange one behind it (photos 1, 5)
S.append(dict(id="e18", tone=[0.92, 0.89, 0.82]))
S.append(dict(id="e18b", tone=RED))
# e19 Bioggio, the pale yellow building at the junction (photo 1)
S.append(dict(id="e19", tone=[0.93, 0.87, 0.64], aerial=False, dish=False, facades=[
    F("e19", "f1", signs=[{"text": "BIRRERIA", "u": 12.0, "z": 3.2, "h": 0.55, "color": [0.4, 0.2, 0.05],
                           "bg": [0.97, 0.93, 0.8]}])]))
# e20 Arosio, the orange house (photo 2)
S.append(dict(id="e20", facades=[F("e20", f, tones=[[0, 20, [0.93, 0.7, 0.42]]]) for f in ("f1", "f4")]))

for s in S:
    g = shapely.Polygon(SITES[s["id"]]["outline"]).simplify(0.1)
    s["outline"] = [[round(x, 2), round(y, 2)] for x, y in g.exterior.coords]
    s["name"] = f"{SITES[s['id']]['comm']}, {SITES[s['id']]['road']}"
    s = {k: s[k] for k in ["id", "name", "outline"] + [k for k in s if k not in ("id", "name", "outline")]}
json.dump({"about": "Buildings closer to the real ones (edifici_veri.py): checked by hand against the open street "
                    "photos and the 10 cm orthophoto (verifica/edifici). Facades by outward azimuth and a point on them; "
                    "u in m from the facade's left end seen from outside, z over the ground; tones sRGB.",
           "sites": [{k: s[k] for k in ["id", "name", "outline"] + [k for k in s if k not in ("id", "name", "outline")]}
                     for s in S]}, open(OUT, "w"), indent=None, separators=(",", ":"))
txt = open(OUT).read().replace('{"id"', '\n{"id"')
open(OUT, "w").write(txt)
print(len(S), "sites")
