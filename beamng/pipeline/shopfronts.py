"""Shop fronts (v3.0): the shops, bars, restaurants and hotels of the villages with their signs, awnings and what
stands outside them, on the built level.

Up to here a shop of OpenStreetMap was a row of shop windows on the ground floor of its building (facades.py) and a
bar or restaurant had a few of Italy's tables in front (street_life.py): the village centres looked as empty as the
houses round them, and the big stores (the Coop of Magliaso, the malls of Grancia) were plain boxes. Here, for every
point of interest of OSM on the Swiss side (dati/osm_pois.json.gz with its names and brands: shops, bars,
restaurants, cafés, pharmacies, banks, post offices, hotels...; KIND_OF):
- its façade: the buildings of the level are its roofs joined on a grid (ROOF_CELL m); the building is the one under
  the point or the nearest (BUILDING_NEAR m), its façades the walls of its mesh that reach the ground with the
  outside where the roof ends first; of those the one that faces a public road (the AI roads) with no other building
  in between and is nearest the point, for a big store its longest street façade (Facades.choose);
- a sign over the ground-floor openings of that façade, between their tops and the windows above (SIGN_Z): a board
  or a light box KINDS[kind][0] m high, as long as the shop windows facades.py drew there or the kind's length,
  shifted along the façade where another place's sign is; on it the name and a logo drawn here: the chains as
  parodies (BRANDS: Coop -> Coup, Migros -> Migrus, Denner -> Dinner, La Posta -> La Pasta, UBS -> UBZ ..., in
  similar colours, never their logos), the other places with their OSM name slightly changed (parody_name) or a
  name of their kind, in the colours and lettering of their kind (STYLES);
- projecting signs: the green cross of the pharmacies, the yellow sign of the post offices, the banks' signs, a
  blade sign at the bars and cafés, flags over the door of the hotels;
- an awning over the shop windows of KINDS[kind][3] of the shops, bars and restaurants, in their colours, plain or
  striped (the name on the valance of the bars and restaurants), AWNING_D m deep at most and never over a
  carriageway: shortened to the pavement and to the posts, lamps and trunks in front;
- by kind, on free ground in front (street_life.Site: not on a carriageway, a wall, the railway, under a roof, near
  the other props, lamps, signs, guard rails, fences or trunks, nor on steep ground): tables with tablecloths, chairs,
  umbrellas, a menu board and plant pots at the restaurants; small tables, chairs and a coffee-brand umbrella at the
  bars and cafés; a trolley shelter with its trolleys, a fruit stand, crates, a gas bottle cage, an ice chest and a
  bin at the food shops; flower buckets at the florists, a newspaper stand at the kiosks, a barber pole and a board at
  the hairdressers, a clothes rack, bikes on a rack, feather flags and price boards at the car dealers, an entrance
  canopy, flags and plant pots at the hotels (the props_* functions);
- the big stores (supermarkets, malls, furniture, car and sports stores with a street façade BIG_L m long or more):
  an entrance canopy with the brand on its edge and its posts, glazed sliding doors under it, a band of the brand's
  colour with its light box high on the façade, pilasters every PILASTER_PITCH m and a cornice along a level top,
  so that they are no longer flat boxes (big_store).
Everything is drawn here: low-poly meshes and their textures (art/shapes/props/shopfronts: the signs packed in
SIGN_PAGE px pages, the props' colours and prints in one page, the leaves and flowers cut out in another), the same
every build (each place seeded by its OSM id). Meshes in MissionGroup/props/shopfronts: the fronts (signs, awnings,
canopies, relief) in FRONT_TILE m tiles drawn up to FRONT_DRAW m, the props in PROP_TILE m tiles drawn up to PROP_DRAW
m; collision for the solid things only (not for the awnings, umbrella canopies, flags, flowers and projecting
signs); the light boxes and projecting signs lit at night like the windows (buildings_mesh.NIGHT). Everything else is
copied as it is.

A finishing step of build_level.py (FINISH), after street_life; alone: python build_level.py --finish shopfronts
"""
import hashlib, json, math, os, re, shutil, tempfile, time, zipfile
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.spatial import cKDTree
import bng
import optimize_level
import osm
import house_extras
import facades as fc
import lamps as pl
import street_life
from buildings_mesh import NIGHT
from config import LEVEL_NAME, wgs_to_local

SEED = 83
D = "art/shapes/props/shopfronts"
SHAPE = re.compile(r"art/shapes/props/shopfronts/shop_[a-z]+_[-+]\d+_[-+]\d+\.dae$")
FRONT_TILE, PROP_TILE = 512.0, 256.0       # m
FRONT_DRAW, PROP_DRAW = 900.0, 320.0       # m up to which they are drawn (the detail size of their tiles)
# the parts of a tile: (tile size, drawing distance, collision, lit at night)
CATS = {"front": (FRONT_TILE, FRONT_DRAW, True, True), "awning": (FRONT_TILE, FRONT_DRAW, False, True),
        "prop": (PROP_TILE, PROP_DRAW, True, False), "soft": (PROP_TILE, PROP_DRAW, False, False)}
SEARCH_R = 32.0            # m from the place to the walls of its building
BUILDING_NEAR = 16.0       # m: a place off the roofs is in the nearest building this far
ROOF_CELL = 0.5            # m, grid of the roofs that make the buildings
ROOF_MIN_H = 1.8           # m over the terrain: lower top faces are no roof
ROAD_R = 45.0              # m from a façade to the road it faces
EAVES_MAX = 3.2            # m: the roof beyond a façade (its eaves) at most this deep
GROUND_GAP = 0.6           # m: a façade reaches the ground within this
MIN_FACADE = 2.4           # m
SIGN_OUT = 0.05            # m from the wall to the back of a sign
SIGN_Z = (2.5, 0.08)       # m: least height of a sign's foot over the ground; gap to the openings round it
FIRST_FLOOR = 2.3          # m over the ground: openings above are on the upper floors
AWNING_D = (1.2, 2.4)      # m deep
AWNING_SLOPE = 0.36        # m of drop per m of depth
AWNING_CLEAR = 2.15        # m over the ground at its front edge
BIG_KINDS = {"supermarket", "mall", "furniture", "car", "electronics", "sports", "garden"}
BIG_L = 14.0               # m of façade: a big store
PILASTER_PITCH = 6.5       # m
CANOPY_D = (1.8, 3.4)      # m deep, entrance canopy of a big store
PROP_S = (0.5, 7.0)        # m from the wall: where the props of a place go
SIGN_PAGE, PROP_PAGE, LEAF_PAGE = 2048, 2048, 1024     # px
SIGN_H = 128               # px, height of a fascia sign's texture
SS = 2                     # the drawings at twice their size, then reduced

# kind: (sign height m, sign length m (least, most), lit, share with an awning, projecting sign, props)
KINDS = {
    "restaurant": (0.70, (3.0, 6.5), False, 0.55, None, "terrace"),
    "pizzeria": (0.70, (3.0, 6.0), False, 0.6, None, "terrace"),
    "grotto": (0.65, (2.5, 5.0), False, 0.25, None, "terrace"),
    "bar": (0.65, (2.5, 5.0), True, 0.6, "blade", "cafe"),
    "cafe": (0.62, (2.5, 5.0), True, 0.6, "blade", "cafe"),
    "ice_cream": (0.60, (2.2, 4.0), True, 0.7, None, "gelato"),
    "fast_food": (0.85, (3.5, 7.0), True, 0.0, None, "fast_food"),
    "supermarket": (1.05, (5.0, 12.0), True, 0.0, None, "market"),
    "convenience": (0.80, (3.0, 7.0), True, 0.35, None, "grocer"),
    "greengrocer": (0.70, (2.5, 5.0), False, 0.8, None, "grocer"),
    "bakery": (0.62, (2.5, 5.0), False, 0.6, None, "bakery"),
    "butcher": (0.62, (2.5, 5.0), False, 0.5, None, "board"),
    "florist": (0.60, (2.5, 5.0), False, 0.6, None, "florist"),
    "kiosk": (0.55, (2.0, 4.0), False, 0.4, None, "kiosk"),
    "pharmacy": (0.65, (3.0, 6.0), True, 0.0, "cross", "board"),
    "hairdresser": (0.60, (2.5, 4.5), False, 0.4, None, "hair"),
    "beauty": (0.55, (2.2, 4.0), False, 0.3, None, "board"),
    "clothes": (0.65, (3.0, 6.0), True, 0.4, None, "clothes"),
    "optician": (0.60, (2.5, 5.0), True, 0.0, None, "board"),
    "wine": (0.62, (2.5, 5.0), False, 0.35, None, "wine"),
    "bicycle": (0.70, (3.0, 6.0), False, 0.0, None, "bikes"),
    "car": (1.00, (5.0, 12.0), True, 0.0, None, "dealer"),
    "garage": (0.80, (3.0, 7.0), False, 0.0, None, None),
    "hotel": (0.70, (3.0, 7.0), True, 0.0, "hotel", "hotel"),
    "bank": (0.70, (3.0, 6.0), True, 0.0, "bank", None),
    "post": (0.70, (3.0, 6.0), True, 0.0, "post", "post"),
    "mall": (1.15, (6.0, 14.0), True, 0.0, None, "market"),
    "furniture": (1.15, (6.0, 14.0), True, 0.0, None, None),
    "electronics": (0.90, (4.0, 10.0), True, 0.0, None, None),
    "sports": (0.95, (4.0, 10.0), True, 0.0, None, None),
    "garden": (0.85, (4.0, 9.0), False, 0.0, None, "florist"),
    "pet": (0.65, (3.0, 6.0), False, 0.3, None, "board"),
    "shop": (0.60, (2.5, 5.0), False, 0.35, None, "board"),
    "office": (0.45, (1.6, 3.2), False, 0.0, None, None),
}
SHOP_KIND = {"supermarket": "supermarket", "convenience": "convenience", "deli": "convenience", "greengrocer":
             "greengrocer", "bakery": "bakery", "pastry": "bakery", "confectionery": "cafe", "coffee": "cafe",
             "butcher": "butcher", "florist": "florist", "garden_centre": "garden", "kiosk": "kiosk", "newsagent": "kiosk",
             "tobacco": "kiosk", "stationery": "kiosk", "books": "kiosk", "hairdresser": "hairdresser", "beauty": "beauty",
             "cosmetics": "beauty", "perfumery": "beauty", "massage": "beauty", "tattoo": "beauty", "clothes": "clothes",
             "shoes": "clothes", "boutique": "clothes", "bag": "clothes", "baby_goods": "clothes", "jewelry": "clothes",
             "optician": "optician", "wine": "wine", "alcohol": "wine", "beverages": "wine", "bicycle": "bicycle",
             "motorcycle": "bicycle", "car": "car", "car_repair": "garage", "mall": "mall", "furniture": "furniture",
             "interior_decoration": "furniture", "bathroom_furnishing": "furniture", "doityourself": "furniture",
             "electronics": "electronics", "computer": "electronics", "mobile_phone": "electronics", "sports": "sports",
             "pet": "pet", "gift": "shop", "art": "shop", "games": "shop", "power_tools": "shop", "paint": "shop",
             "tool_hire": "shop", "yes": "shop", "travel_agency": "shop", "gas": "shop", "boat": "shop",
             "hardware": "shop", "toys": "shop"}
AMENITY_KIND = {"restaurant": "restaurant", "bar": "bar", "pub": "bar", "cafe": "cafe", "ice_cream": "ice_cream",
                "fast_food": "fast_food", "pharmacy": "pharmacy", "bank": "bank", "post_office": "post",
                "veterinary": "shop"}
OFFICES = {"insurance", "estate_agent", "travel_agent", "notary", "architect", "advertising_agency"}

# the chains as parodies: what they are found by (in the brand, name or operator of OSM), their parody's name and
# second line, colours as seen (sRGB): board, letters, accent; lettering; logo (drawn by sign_logo, never theirs)
BRANDS = {
    "coop_pronto": (r"coop ?pronto", "Coup", "Pronto", (255, 255, 255), (232, 96, 22), (20, 70, 150), "sans", None),
    "coop": (r"^coop\b", "Coup", "", (255, 255, 255), (232, 96, 22), (232, 96, 22), "sans", "bar"),
    "migrolino": (r"migrolino", "migrulino", "", (255, 255, 255), (255, 110, 10), (90, 170, 60), "sans", "dot"),
    "migros": (r"^migros", "MIGRUS", "", (255, 255, 255), (255, 102, 0), (255, 102, 0), "sans", "M"),
    "denner": (r"denner", "DINNER", "", (210, 16, 30), (255, 255, 255), (255, 206, 0), "sans_it", "swoosh"),
    "lidl": (r"lidl", "LIDAL", "", (0, 72, 160), (255, 214, 0), (226, 0, 26), "sans", "ring"),
    "aldi": (r"aldi", "ALDA", "", (0, 30, 95), (255, 255, 255), (255, 140, 0), "sans", "stripes"),
    "manor": (r"manor", "MANOIR", "", (255, 255, 255), (220, 0, 30), (220, 0, 30), "serif", None),
    "volg": (r"volg", "Valg", "", (255, 206, 0), (205, 20, 35), (205, 20, 35), "sans", None),
    "spar": (r"\bspar\b", "SPARR", "", (255, 255, 255), (225, 30, 40), (0, 130, 60), "sans", "tree"),
    "crai": (r"\bcrai\b", "CRAU", "supermercato", (255, 255, 255), (210, 20, 40), (0, 140, 70), "sans", "dot"),
    "jumbo": (r"jumbo", "JUMBU", "", (255, 214, 0), (230, 70, 10), (230, 70, 10), "sans", None),
    "postfinance": (r"postfinance", "PastFinance", "", (255, 204, 0), (20, 20, 20), (220, 0, 20), "sans", "fork"),
    "posta": (r"\bpost[ae]?\b|la posta", "LA PASTA", "", (255, 204, 0), (20, 20, 20), (220, 0, 20), "sans", "fork"),
    "ubs": (r"\bubs\b", "UBZ", "", (255, 255, 255), (20, 20, 20), (210, 0, 0), "serif", "keys"),
    "raiffeisen": (r"raiffeisen", "RAIFFBEISEN", "", (255, 255, 255), (20, 20, 20), (225, 0, 25), "sans", "gable"),
    "bancastato": (r"banca ?stato", "BancaStata", "", (255, 255, 255), (200, 16, 46), (200, 16, 46), "sans", "square"),
    "mcdonalds": (r"mcdonald", "McDonnell's", "", (205, 10, 20), (255, 196, 30), (255, 196, 30), "sans", "humps"),
    "ikea": (r"ikea", "IKAE", "", (0, 81, 186), (0, 81, 186), (255, 218, 26), "sans", "oval"),
    "mediamarkt": (r"media ?markt", "Media Murkt", "", (223, 0, 0), (255, 255, 255), (255, 255, 255), "sans_it", None),
    "decathlon": (r"decathlon", "DECATHLAN", "", (0, 125, 190), (255, 255, 255), (255, 255, 255), "sans_it", None),
    "conforama": (r"conforama", "Comforama", "", (225, 0, 30), (255, 255, 255), (255, 255, 255), "sans", None),
    "poltronesofa": (r"poltronesof", "Poltronasofà", "", (200, 20, 30), (255, 255, 255), (255, 255, 255), "sans_it", None),
    "zara": (r"\bzara\b", "ZARRA", "", (255, 255, 255), (15, 15, 15), (15, 15, 15), "serif", None),
    "hm": (r"h&m", "H&N", "", (255, 255, 255), (225, 0, 20), (225, 0, 20), "script", None),
    "lahalle": (r"la halle", "La Hall", "", (200, 0, 40), (255, 255, 255), (255, 255, 255), "sans", None),
    "tigota": (r"tigot", "Tigatà", "", (0, 150, 90), (255, 255, 255), (255, 120, 170), "sans", None),
    "hilti": (r"hilti", "HILTY", "", (210, 5, 30), (255, 255, 255), (255, 255, 255), "sans", None),
    "salt": (r"^salt$", "sald.", "", (15, 15, 15), (255, 255, 255), (255, 255, 255), "sans", None),
    "qualipet": (r"qualipet", "Qualipat", "", (0, 140, 70), (255, 255, 255), (255, 210, 0), "sans", "paw"),
    "mcoptik": (r"mcoptik", "McOptic", "", (90, 30, 120), (255, 255, 255), (255, 255, 255), "sans", "glasses"),
    "brico": (r"brico", "BRICKO", "", (240, 120, 0), (255, 255, 255), (255, 255, 255), "sans", None),
    "pangas": (r"pangas", "PenGas", "Gas & More", (0, 90, 170), (255, 255, 255), (255, 255, 255), "sans", None),
    "emilfrey": (r"emil[y]? frey", "Emil Fray", "Autocentro", (0, 50, 120), (255, 255, 255), (220, 220, 220), "sans", "car"),
    "mercedes": (r"mercedes", "Mercedez", "Autosalone", (30, 30, 34), (220, 222, 226), (170, 172, 176), "serif", "star3"),
    "bmw": (r"\bbmw\b", "BMV", "Garage", (255, 255, 255), (20, 60, 140), (20, 120, 210), "sans", "quarters"),
    "porsche": (r"porsche", "PORSHE", "Centro", (20, 20, 20), (215, 175, 90), (215, 175, 90), "serif", None),
    "jeep": (r"\bjeep\b", "Jeepp", "4x4", (50, 70, 45), (255, 255, 255), (255, 255, 255), "sans", "car"),
    "toyota": (r"toyota", "TOYODA", "", (235, 10, 30), (255, 255, 255), (255, 255, 255), "sans", "oval"),
}
OPERATOR_KINDS = {"post", "bank"}              # an operator names the chain only for these
# coffee, beer and ice cream as parodies, on the umbrellas: (name, canopy, second panel colour, print letters)
COFFEE = (("Chicco d'Oru", (95, 50, 25), (205, 160, 70), (240, 210, 130)), ("Lavazzo", (20, 35, 90), (240, 240, 240), (255, 255, 255)),
          ("Ully", (200, 20, 30), (240, 240, 240), (255, 255, 255)), ("Segafreddo", (25, 25, 25), (200, 20, 30), (255, 255, 255)))
BEER = (("Feldschlössken", (190, 20, 30), (240, 240, 240), (255, 255, 255)), ("Birra Moretta", (235, 225, 200), (150, 30, 30), (150, 30, 30)),
        ("Heinekin", (0, 110, 50), (240, 240, 240), (255, 255, 255)), ("Birra Bianchetti", (240, 240, 240), (20, 70, 150), (20, 70, 150)))
GELATO = (("Gelati Mutta", (240, 120, 160), (255, 255, 255), (255, 255, 255)), ("Algidu", (220, 20, 40), (255, 255, 255), (255, 255, 255)))

# the other places by kind: colours (board, letters, accent: one of them by place), lettering, logo, the word of the
# kind under the name when the name lacks it, and names for the places OSM has without one
STYLES = {
    "restaurant": ([((30, 70, 45), (240, 230, 200), (210, 180, 90)), ((110, 25, 35), (240, 225, 180), (220, 180, 90)),
                    ((245, 240, 225), (120, 30, 30), (40, 90, 50))], "serif", "cutlery", "RISTORANTE",
                   ("Ristorante Al Grotto", "Trattoria del Ponte", "Ristorante Da Mario", "Osteria del Borgo")),
    "pizzeria": ([((255, 255, 255), (200, 30, 30), (0, 140, 70)), ((30, 90, 50), (255, 255, 255), (220, 40, 40))],
                 "serif_it", "slice", "PIZZERIA", ("Pizzeria Bella Tresa", "Pizzeria Da Gino")),
    "grotto": ([((95, 60, 35), (245, 230, 200), (210, 170, 100)), ((70, 70, 65), (240, 235, 220), (200, 170, 110))],
               "serif_it", "bottle", "GROTTO", ("Grotto del Sasso", "Grotto ai Castagni")),
    "bar": ([((25, 40, 85), (255, 255, 255), (230, 190, 60)), ((150, 20, 30), (255, 255, 255), (255, 210, 80)),
             ((20, 20, 22), (240, 200, 90), (240, 200, 90))], "sans_it", "glass", "BAR", ("Bar Sport", "Bar Centrale")),
    "cafe": ([((85, 52, 30), (245, 230, 205), (215, 175, 110)), ((240, 232, 215), (90, 50, 30), (170, 110, 60))],
             "serif_it", "cup", "CAFFÈ", ("Caffè Centrale", "Caffè della Piazza")),
    "ice_cream": ([((245, 160, 190), (255, 255, 255), (120, 60, 40)), ((150, 210, 220), (255, 255, 255), (230, 80, 120))],
                  "script", "cone", "GELATERIA", ("Gelateria Dolce Vita", "Gelateria")),
    "fast_food": ([((230, 120, 20), (255, 255, 255), (255, 230, 120))], "sans", "slice", "TAKE AWAY", ("Take Away",)),
    "supermarket": ([((40, 120, 60), (255, 255, 255), (255, 210, 60))], "sans", "apple", "ALIMENTARI", ("Alimentari",)),
    "convenience": ([((40, 120, 60), (255, 255, 255), (255, 210, 60)), ((240, 235, 220), (40, 100, 50), (200, 60, 40))],
                    "sans", "apple", "ALIMENTARI", ("Alimentari", "Negozio del Villaggio")),
    "greengrocer": ([((50, 130, 50), (255, 255, 255), (255, 200, 40))], "sans", "apple", "FRUTTA E VERDURA", ("Frutta e Verdura",)),
    "bakery": ([((245, 230, 200), (120, 70, 30), (190, 130, 60)), ((120, 70, 35), (250, 235, 205), (230, 190, 120))],
               "serif", "bread", "PANETTERIA", ("Panetteria", "Panetteria Pasticceria")),
    "butcher": ([((140, 20, 25), (255, 255, 255), (240, 220, 200))], "serif", "cleaver", "MACELLERIA", ("Macelleria",)),
    "florist": ([((255, 255, 255), (185, 35, 115), (60, 140, 60)), ((60, 110, 60), (255, 255, 255), (250, 170, 200))],
                "script", "flower", "FIORI", ("Fiori e Piante", "Il Giardino Fiorito")),
    "kiosk": ([((20, 60, 140), (255, 255, 255), (255, 210, 0))], "sans", "paper", "EDICOLA · TABACCHI", ("Edicola",)),
    "pharmacy": ([((255, 255, 255), (0, 140, 65), (0, 140, 65)), ((0, 140, 65), (255, 255, 255), (255, 255, 255))],
                 "sans", "cross", "FARMACIA", ("Farmacia",)),
    "hairdresser": ([((20, 20, 22), (255, 255, 255), (215, 180, 110)), ((255, 255, 255), (30, 30, 30), (200, 40, 110))],
                    "script", "scissors", "PARRUCCHIERE", ("Parrucchiera Elena", "Coiffeur Sandro")),
    "beauty": ([((250, 235, 240), (160, 40, 100), (160, 40, 100))], "script", "flower", "ESTETICA", ("Istituto di Bellezza",)),
    "clothes": ([((20, 20, 20), (255, 255, 255), (255, 255, 255)), ((255, 255, 255), (20, 20, 20), (180, 30, 40))],
                "serif", "hanger", "MODA", ("Boutique Moda", "Abbigliamento")),
    "optician": ([((255, 255, 255), (20, 50, 110), (20, 50, 110))], "sans", "glasses", "OTTICA", ("Ottica",)),
    "wine": ([((90, 20, 35), (235, 205, 130), (235, 205, 130))], "serif_it", "bottle", "ENOTECA", ("Enoteca", "Vini del Ticino")),
    "bicycle": ([((240, 110, 20), (255, 255, 255), (30, 30, 30)), ((30, 110, 60), (255, 255, 255), (255, 220, 60))],
                "sans_it", "bike", "CICLI", ("Cicli e Moto",)),
    "car": ([((30, 60, 120), (255, 255, 255), (200, 210, 230))], "sans", "car", "AUTOSALONE", ("Autosalone",)),
    "garage": ([((60, 60, 65), (255, 255, 255), (230, 60, 40))], "sans", "car", "GARAGE", ("Garage", "Carrozzeria")),
    "hotel": ([((25, 40, 80), (225, 195, 120), (225, 195, 120)), ((120, 25, 35), (240, 215, 150), (240, 215, 150))],
              "serif", "stars", "HOTEL", ("Albergo", "Hotel Bellavista")),
    "bank": ([((40, 50, 70), (255, 255, 255), (200, 170, 90))], "serif", "square", "BANCA", ("Banca Popolare",)),
    "post": ([((255, 204, 0), (20, 20, 20), (220, 0, 20))], "sans", "fork", "", ("LA PASTA",)),
    "mall": ([((60, 60, 70), (255, 255, 255), (240, 160, 40))], "sans", None, "", ("Centro Commerciale",)),
    "furniture": ([((90, 70, 55), (255, 255, 255), (230, 200, 150))], "sans", None, "ARREDAMENTI", ("Mobili",)),
    "electronics": ([((30, 30, 35), (255, 255, 255), (60, 170, 230))], "sans", None, "", ("Elettronica",)),
    "sports": ([((20, 90, 160), (255, 255, 255), (255, 255, 255))], "sans_it", None, "SPORT", ("Sport",)),
    "garden": ([((50, 120, 50), (255, 255, 255), (255, 220, 80))], "sans", "flower", "GIARDINAGGIO", ("Garden Center",)),
    "pet": ([((0, 140, 160), (255, 255, 255), (255, 210, 0))], "sans", "paw", "ANIMALI", ("Tutto per gli Animali",)),
    "shop": ([((60, 62, 68), (255, 255, 255), (230, 190, 90)), ((240, 236, 225), (40, 40, 45), (170, 40, 40)),
              ((30, 70, 110), (255, 255, 255), (255, 255, 255))], "sans", None, "", ("Negozio",)),
    "office": ([((235, 235, 232), (40, 45, 60), (40, 45, 60))], "sans", None, "", ("Studio",)),
}
# words left as they are in a name; in the others one vowel changes (parody_name)
COMMON = {"ristorante", "osteria", "grotto", "bar", "caffè", "cafè", "cafe", "café", "farmacia", "albergo", "hotel",
          "pizzeria", "panetteria", "macelleria", "gelateria", "agriturismo", "al", "alla", "alle", "ai", "da", "del",
          "della", "dei", "di", "la", "il", "lo", "le", "san", "santa", "casa", "villa", "b&b", "tea-room", "sport",
          "centro", "centrale", "stazione", "posta", "piazza", "piazzetta", "ponte", "lago", "unione", "concordia",
          "elvezia", "bivio", "giardino", "bellavista", "bella", "vista", "fiori", "pizza", "salone", "studio",
          "ristorante-ostello", "bar-ristorante", "e", "&", "-", "sa", "sagl", "con", "alloggio", "club", "tennis",
          "golf", "circolo", "sociale", "taverna", "pescatori", "trattoria", "pension", "pensione", "monte", "vetta",
          "guesthouse", "auto", "garage", "centro", "the", "and", "lugano", "ticino", "caslano", "magliaso", "agno"}
STYLE_SUB = {"grotto": ("grotto",), "restaurant": ("ristorante", "osteria", "trattoria", "taverna", "grotto", "pizzeria"),
             "pizzeria": ("pizzeria",), "bar": ("bar", "pub", "osteria"), "cafe": ("caff", "cafe", "café", "cafè", "tea-room", "bar", "gelat"),
             "ice_cream": ("gelat",), "pharmacy": ("farmacia",), "bakery": ("panett", "panific", "pasticc"),
             "butcher": ("macell",), "hotel": ("hotel", "albergo", "b&b", "guest", "casa", "villa", "pension"),
             "kiosk": ("edicola", "chiosco"), "optician": ("ottic", "optik"), "hairdresser": ("parrucch", "coiff", "hair", "salone"),
             "florist": ("fior",), "wine": ("vin", "enoteca", "birr"), "bicycle": ("bike", "cicl", "moto")}
# the colours of things as seen (sRGB 0-255)
WOOD, DARK_WOOD, METAL, DARK_METAL, WHITE = (150, 105, 65), (95, 65, 40), (175, 178, 182), (70, 72, 76), (238, 238, 234)
TERRACOTTA, GREEN_PAINT, CREAM = (170, 90, 60), (40, 80, 55), (235, 225, 200)


def _unit(key, salt):
    """A number in [0, 1) from the key, the same every build."""
    return int.from_bytes(hashlib.md5(f"{salt}:{key}".encode()).digest()[:4], "little") / 2 ** 32


def _pick(seq, key, salt):
    return seq[int(_unit(key, salt) * len(seq)) % len(seq)]


# ------------------------------------------------------------------ the places
def swiss_area():
    import signs_net
    comm = signs_net.communes()
    g = shapely.union_all([p for _, p in comm]) if comm else None
    if g is not None:
        shapely.prepare(g)
    return g


def kind_of(tags):
    """The kind of a place (KINDS) from its OSM tags; None for what has no shop front."""
    name = (tags.get("name") or "").lower()
    if "shop" in tags:
        return SHOP_KIND.get(tags["shop"])
    a = tags.get("amenity")
    if a in AMENITY_KIND:
        k = AMENITY_KIND[a]
        if k == "restaurant" or (k == "cafe" and "grotto" in name):
            if "grotto" in name:
                return "grotto"
            if "pizz" in name:
                return "pizzeria"
        return k
    t = tags.get("tourism")
    if t in ("hotel", "guest_house", "hostel", "motel"):
        return "hotel"
    if tags.get("craft") in ("winery", "brewery"):
        return "wine"
    if tags.get("office") in OFFICES:
        return "office"
    return None


def brand_of(tags, kind):
    """The chain (BRANDS) a place belongs to, or None."""
    keys = ["brand", "name"] + (["operator"] if kind in OPERATOR_KINDS else [])
    for k in keys:
        v = (tags.get(k) or "").lower()
        if not v:
            continue
        for b, spec in BRANDS.items():
            if re.search(spec[0], v):
                if b == "posta" and kind not in ("post",):
                    continue
                return b
    if kind == "post":
        return "posta"
    return None


def parody_name(name, key):
    """The name of an independent place slightly changed: the last vowel of its most particular word turned."""
    words = name.split()
    cand = [i for i, w in enumerate(words) if w.lower().strip(".,'") not in COMMON and len(w) >= 4 and w.isalpha()]
    if not cand:
        return name
    i = max(cand, key=lambda j: (len(words[j]), -j))
    w = words[i]
    swap = {"a": "o", "o": "a", "e": "i", "i": "e", "u": "o"}
    for k in range(len(w) - 1, 0, -1):
        if w[k].lower() in swap:
            c = swap[w[k].lower()]
            words[i] = w[:k] + (c.upper() if w[k].isupper() else c) + w[k + 1:]
            break
    return " ".join(words)


class Place:
    def __init__(self, oid, x, y, kind, tags):
        self.id, self.p, self.kind, self.tags = oid, np.array([x, y], float), kind, tags
        self.brand = brand_of(tags, kind)
        self.big = kind in BIG_KINDS
        name = (tags.get("name") or "").strip()
        st = STYLES[kind]
        if self.brand:
            b = BRANDS[self.brand]
            self.title, self.sub = b[1], b[2]
            self.colours, self.font, self.logo = (b[3], b[4], b[5]), b[6], b[7]
        else:
            self.title = parody_name(name, oid) if name else _pick(st[4], oid, "name")
            low = self.title.lower()
            self.sub = "" if any(w in low for w in STYLE_SUB.get(kind, ())) or not st[3] else st[3]
            self.colours, self.font, self.logo = _pick(st[0], oid, "colours"), st[1], st[2]
        self.title = self.title[:34]

    def rng(self, salt=""):
        return np.random.default_rng(int.from_bytes(hashlib.md5(f"{SEED}:{self.id}:{salt}".encode()).digest()[:8], "little"))


def load_places(swiss):
    """[Place] of the points of interest of OSM on the Swiss side with a shop front, by their OSM id."""
    src = osm.source(osm.POIS, osm.POIS_PINNED)
    if src is None:
        return [], {}
    out, why = [], {}
    for e in osm.read(src)["elements"]:
        c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        t = e.get("tags", {})
        k = kind_of(t)
        if c is None or k is None:
            why["no shop front"] = why.get("no shop front", 0) + 1
            continue
        x, y = wgs_to_local(c["lat"], c["lon"])
        if swiss is None or not swiss.contains(shapely.Point(float(x), float(y))):
            why["Italy"] = why.get("Italy", 0) + 1
            continue
        out.append(Place(f"{e['type'][0]}{e['id']}", float(x), float(y), k, t))
    return sorted(out, key=lambda p: p.id), why


# ------------------------------------------------------------------ the buildings and their façades
class Facade:
    """A wall of a building that reaches the ground: the line e . x = d (e the outward normal), along t from u0 to u1."""

    def __init__(self, e, d, u0, u1, zlo, zhi, tris, eaves):
        self.e = e / np.linalg.norm(e)
        self.t = np.array([self.e[1], -self.e[0]])
        self.d, self.u0, self.u1, self.zlo, self.zhi, self.tris, self.eaves = d, u0, u1, zlo, zhi, tris, eaves
        # the wall's line: the places on one line share it (Layout.taken)
        self.key = (int(round(math.degrees(math.atan2(self.e[1], self.e[0])))) % 360, int(round(d * 2)))
        self.openings = []
        self._poly = None

    @property
    def length(self):
        return self.u1 - self.u0

    def at(self, u, s=0.0):
        """The point u along the façade, s m out of the wall."""
        return self.e * (self.d + s) + self.t * u

    def poly(self):
        if self._poly is None:
            self._poly = fc.facade_polygon(self.tris, np.r_[self.t, 0.0])
        return self._poly

    def top(self, ua, ub):
        """Lowest top of the wall over [ua, ub]."""
        F = self.poly()
        if F is None:
            return self.zhi
        us = np.linspace(ua, ub, max(3, int((ub - ua) / 0.5)))
        tp = fc.top_profile(F, us)
        return float(np.nanmin(tp)) if np.isfinite(tp).any() else self.zhi

    def angle(self):
        """Angle of the local x axis (t) of the façade frame: x along, y out, z up."""
        return math.atan2(self.t[1], self.t[0])


class Buildings:
    """The walls and openings of the building meshes near the places."""

    def __init__(self, zi, lv, pts):
        tree = cKDTree(pts)
        idx = house_extras.atlas_index()
        names = list(idx)
        R = np.array([idx[k][:4] for k in names])
        walls, ops = [], []
        for o in pl.read_items(zi, f"{lv}/main/MissionGroup/buildings/items.level.json"):
            sn = o.get("shapeName", "").lstrip("/")
            if o.get("class") != "TSStatic" or sn not in zi.NameToInfo or "/details/" in sn or "/extras/" in sn:
                continue
            V, N, T, C, parts, _ = optimize_level.parse(zi.read(sn).decode("utf-8"))
            W = V + np.asarray(o.get("position", [0, 0, 0]), np.float64)
            for m, ix in parts:
                if m.startswith("bld_roof"):
                    continue
                tri = W[ix[:, 0]].reshape(-1, 3, 3)
                near = np.isfinite(tree.query(tri.mean(1)[:, :2], distance_upper_bound=SEARCH_R + 15.0)[0])
                if not near.any():
                    continue
                if m.startswith("bld_openings"):
                    uv = T[ix[:, 2 if ix.shape[1] > 2 else 1]].reshape(-1, 3, 2)
                    for k in range(0, len(tri) - 1, 2):
                        if not (near[k] or near[k + 1]):
                            continue
                        q = np.concatenate([tri[k], tri[k + 1]])
                        uc = uv[k:k + 2].reshape(-1, 2).mean(0) % 1.0
                        j = np.flatnonzero((R[:, 0] <= uc[0]) & (uc[0] <= R[:, 2]) & (R[:, 1] <= uc[1]) & (uc[1] <= R[:, 3]))
                        xy = q[:, :2]
                        dd = np.linalg.norm(xy[:, None] - xy[None], axis=2)
                        i1, i2 = np.unravel_index(np.argmax(dd), dd.shape)
                        ops.append((names[j[0]] if len(j) else "", xy[i1], xy[i2], q[:, 2].min(), q[:, 2].max()))
                else:
                    t = tri[near]
                    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
                    ln = np.linalg.norm(n, axis=1)
                    vert = (np.abs(n[:, 2]) < 0.08 * np.maximum(ln, 1e-12)) & (ln > 1e-6)
                    walls.append(t[vert])
        self.walls = np.concatenate(walls) if walls else np.zeros((0, 3, 3))
        self.wtree = cKDTree(self.walls.mean(1)[:, :2]) if len(self.walls) else None
        self.ops = ops
        self.otree = cKDTree(np.array([(a + b) / 2 for _, a, b, _, _ in ops])) if ops else None

    def segments(self, p, r):
        """The walls within r m of p as façade lines: [(e, d, u0, u1, zlo, zhi, triangles)], e either way."""
        if self.wtree is None:
            return []
        k = self.wtree.query_ball_point(p, r)
        if not k:
            return []
        T = self.walls[k]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])[:, :2]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        ang = np.arctan2(n[:, 1], n[:, 0]) % math.pi
        out = []
        order = np.argsort(ang)
        groups, cur = [], [order[0]]
        for a, b in zip(order[:-1], order[1:]):
            if ang[b] - ang[a] > math.radians(2.5):
                groups.append(cur)
                cur = []
            cur.append(b)
        groups.append(cur)
        if len(groups) > 1 and ang[groups[0][0]] + math.pi - ang[groups[-1][-1]] < math.radians(2.5):
            groups[0] = groups[-1] + groups[0]
            groups.pop()
        for g in groups:
            g = np.array(g)
            a0 = ang[g[0]]
            e = np.array([math.cos(a0), math.sin(a0)])
            if np.ptp(ang[g]) > math.pi / 2:          # across the wrap: the normals of the group either way
                sgn = np.sign(n[g] @ e)
                e = (n[g] * sgn[:, None]).mean(0)
            else:
                e = np.array([math.cos(ang[g].mean()), math.sin(ang[g].mean())])
            e /= np.linalg.norm(e)
            t = np.array([e[1], -e[0]])
            c = T[g].mean(1)[:, :2]
            d = c @ e
            od = np.argsort(d)
            run = [od[0]]
            for a, b in zip(od[:-1], od[1:]):
                if d[b] - d[a] > 0.25:
                    out += self._spans(T[g[run]], e, t)
                    run = []
                run.append(b)
            out += self._spans(T[g[run]], e, t)
        return out

    @staticmethod
    def _spans(T, e, t):
        d = float(np.median(T.mean(1)[:, :2] @ e))
        u = T[:, :, :2] @ t
        lo, hi = u.min(1), u.max(1)
        o = np.argsort(lo)
        out, start, end, members = [], lo[o[0]], hi[o[0]], [o[0]]
        for i in o[1:]:
            if lo[i] > end + 0.5:
                out.append((e, d, start, end, members))
                start, end, members = lo[i], hi[i], []
            end = max(end, hi[i])
            members.append(i)
        out.append((e, d, start, end, members))
        return [(e, d, float(a), float(b), float(T[m][:, :, 2].min()), float(T[m][:, :, 2].max()), T[m])
                for e, d, a, b, m in out]

    def openings_on(self, f):
        """The openings of the façade f: [(name, ua, ub, zb, zt)]."""
        if self.otree is None:
            return []
        c = f.at(0.5 * (f.u0 + f.u1))
        out = []
        for j in self.otree.query_ball_point(c, 0.5 * f.length + 2.0):
            name, a, b, zb, zt = self.ops[j]
            if abs((a + b) / 2 @ f.e - f.d) > 0.4:
                continue
            v = b - a
            L = np.linalg.norm(v)
            if L < 0.2 or abs(v @ f.e) > 0.3 * L:
                continue
            ua, ub = sorted((a @ f.t, b @ f.t))
            if ub < f.u0 - 0.2 or ua > f.u1 + 0.2:
                continue
            out.append((name, float(ua), float(ub), float(zb), float(zt)))
        return out


class Roofs:
    """The roofs of the level on a grid around a point, joined into buildings (connected cells)."""

    def __init__(self, site, p, half=SEARCH_R + 25.0):
        n = int(2 * half / ROOF_CELL)
        self.o = p - half
        g = (np.arange(n) + 0.5) * ROOF_CELL
        X, Y = np.meshgrid(self.o[0] + g, self.o[1] + g)
        z = site.roof.height(X.ravel(), Y.ravel(), "high")
        zt = site.terrain(X.ravel(), Y.ravel())
        self.m = (np.isfinite(z) & (z > zt + ROOF_MIN_H)).reshape(n, n)
        self.lab, _ = ndimage.label(self.m)
        self.n = n

    def label(self, q):
        c = np.floor((np.atleast_2d(q) - self.o) / ROOF_CELL).astype(int)
        ok = (c >= 0).all(1) & (c < self.n).all(1)
        out = np.zeros(len(c), int)
        out[ok] = self.lab[c[ok, 1], c[ok, 0]]
        return out

    def building_at(self, p, near=BUILDING_NEAR):
        """The building under p, else the nearest within `near` m; 0 for none."""
        lb = self.label(p)[0]
        if lb:
            return lb
        if not self.m.any():
            return 0
        dist, (iy, ix) = ndimage.distance_transform_edt(~self.m, return_indices=True)
        c = np.floor((p - self.o) / ROOF_CELL).astype(int)
        if not (0 <= c[0] < self.n and 0 <= c[1] < self.n) or dist[c[1], c[0]] * ROOF_CELL > near:
            return 0
        return int(self.lab[iy[c[1], c[0]], ix[c[1], c[0]]])

    def run(self, q, d, lb, smax=10.0):
        """How far from q along d the cells stay roofs of the building lb (m)."""
        s = np.arange(0.25, smax, 0.25)
        L = self.label(q + s[:, None] * d)
        off = np.flatnonzero(L != lb)
        return float(s[off[0]]) if len(off) else smax


class Roads:
    """The axes of the AI roads every metre: points, widths."""

    def __init__(self, zi, lv):
        P, W = [], []
        for o in pl.read_items(zi, f"{lv}/main/MissionGroup/AIRoads/items.level.json"):
            if o.get("class") != "DecalRoad":
                continue
            s = pl.sample(o["nodes"])
            if s is not None:
                P.append(s[0])
                W.append(s[2])
        self.P = np.concatenate(P)
        self.W = np.concatenate(W)
        self.tree = cKDTree(self.P[:, :2])


def choose_facade(place, bld, roofs, roads, site):
    """The façade of the place: (Facade, why) with why None when found."""
    p = place.p
    lb = roofs.building_at(p)
    if not lb:
        return None, "no building"
    best, best_s = None, -1e9
    for e, d, u0, u1, zlo, zhi, tris in bld.segments(p, SEARCH_R):
        if u1 - u0 < MIN_FACADE:
            continue
        t = np.array([e[1], -e[0]])
        # its outside: where the roof of the building ends first (its eaves); a party wall has roof on both sides
        votes, eav = 0, []
        for f in (0.25, 0.5, 0.75):
            q = e * d + t * (u0 + f * (u1 - u0))
            if roofs.label(q - e * 0.6)[0] != lb and roofs.label(q + e * 0.6)[0] != lb and roofs.label(q)[0] != lb:
                continue
            a, b = roofs.run(q, e, lb), roofs.run(q, -e, lb)
            if a <= EAVES_MAX and b > a + 0.75:
                votes += 1
                eav.append(a)
            elif b <= EAVES_MAX and a > b + 0.75:
                votes -= 1
                eav.append(b)
        if votes == 0 or not eav:
            continue
        if votes < 0:
            e, d, t = -e, -d, -t
            u0, u1 = -u1, -u0
        f = Facade(e, d, u0, u1, zlo, zhi, tris, float(np.median(eav)))
        up = float(np.clip(p @ f.t, f.u0 + 0.5, f.u1 - 0.5)) if f.length > 1.0 else 0.5 * (f.u0 + f.u1)
        c = f.at(up)
        zg = float(site.ground([c[0] + f.e[0] * 0.4], [c[1] + f.e[1] * 0.4])[0])
        if zlo > zg + GROUND_GAP:
            continue
        # the road it faces, nothing in between
        k = roads.tree.query_ball_point(c, ROAD_R)
        if not k:
            continue
        R = roads.P[k, :2] - c
        dist = np.linalg.norm(R, axis=1)
        front = R @ f.e
        ok = front > f.eaves + 0.5
        if not ok.any():
            continue
        facing = np.where(ok, front / np.maximum(dist, 1e-6), -1)
        edge = np.maximum(dist - roads.W[k] / 2, 0.0)
        j = int(np.argmax(facing * 3.0 - edge / 10.0))
        if facing[j] < 0.25:
            continue
        dirn = R[j] / max(dist[j], 1e-6)
        s = np.arange(f.eaves + 0.75, max(edge[j], f.eaves + 0.8), 0.75)
        if len(s) and (roofs.label(c + s[:, None] * dirn) > 0).sum() > 1:
            continue
        dp = abs(float(p @ f.e) - f.d) + max(0.0, f.u0 - p @ f.t, p @ f.t - f.u1)
        f.openings = bld.openings_on(f)
        shops = any(nm.startswith("shop") for nm, *_ in f.openings)
        big = place.big and f.length >= BIG_L
        score = (2.5 * facing[j] - edge[j] / 10.0 - dp / (25.0 if place.big else 8.0) +
                 min(f.length, 40.0) / (15.0 if place.big else 40.0) + 0.8 * shops + 0.3 * big)
        if score > best_s:
            best, best_s = f, score
    if best is None:
        return None, "no street façade"
    return best, None


# ------------------------------------------------------------------ textures
_fonts = {}
FONTS = {"sans": "DejaVuSans-Bold.ttf", "sans_it": "DejaVuSans-BoldOblique.ttf", "serif": "DejaVuSerif-Bold.ttf",
         "serif_it": "DejaVuSerif-BoldItalic.ttf", "script": "STIXGeneralBolIta.ttf", "plain": "DejaVuSans.ttf"}


def _font(style, px):
    """The lettering `style` at px: the fonts that come with matplotlib (the same on every machine), else those of
    the system, else Pillow's own."""
    key = (style, int(px))
    if key in _fonts:
        return _fonts[key]
    name = FONTS.get(style, FONTS["sans"])
    dirs = []
    try:
        import matplotlib
        dirs.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"))
    except ImportError:
        pass
    dirs += ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/stix", "C:/Windows/Fonts"]
    f = None
    for d in dirs:
        for n in (name, FONTS["sans"]):
            if os.path.exists(os.path.join(d, n)):
                f = ImageFont.truetype(os.path.join(d, n), max(6, int(px)))
                break
        if f:
            break
    _fonts[key] = f or ImageFont.load_default(size=max(6, int(px)))
    return _fonts[key]


class Sketch:
    """A drawing at SS times its size; coordinates in pixels of the texture."""

    def __init__(self, w, h, bg, mode="RGB"):
        self.w, self.h = int(w), int(h)
        self.img = Image.new(mode, (self.w * SS, self.h * SS), tuple(bg))
        self.d = ImageDraw.Draw(self.img)

    def P(self, pts):
        return [(x * SS, y * SS) for x, y in pts]

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=0, radius=0):
        b = [x0 * SS, y0 * SS, x1 * SS, y1 * SS]
        if radius:
            self.d.rounded_rectangle(b, radius * SS, fill=fill, outline=outline, width=int(width * SS))
        else:
            self.d.rectangle(b, fill=fill, outline=outline, width=int(width * SS))

    def ellipse(self, x0, y0, x1, y1, fill=None, outline=None, width=0):
        self.d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill, outline=outline, width=int(width * SS))

    def poly(self, pts, fill):
        self.d.polygon(self.P(pts), fill=fill)

    def line(self, pts, fill, width):
        self.d.line(self.P(pts), fill=fill, width=max(1, int(width * SS)), joint="curve")

    def arc(self, box, a0, a1, fill, width):
        self.d.arc([v * SS for v in box], a0, a1, fill=fill, width=max(1, int(width * SS)))

    def text(self, s, box, style, fill, align="c"):
        """s as large as fits the box (x0, y0, x1, y1)."""
        x0, y0, x1, y1 = box
        bw, bh = (x1 - x0) * SS, (y1 - y0) * SS
        if bw <= 2 or bh <= 2 or not s:
            return 0
        size = int(bh * 1.3)
        for _ in range(4):
            f = _font(style, size)
            l, t, r, b = self.d.textbbox((0, 0), s, font=f)
            k = min(bw / max(r - l, 1), bh / max(b - t, 1))
            if 0.96 <= k <= 1.0:
                break
            size = max(6, int(size * k * 0.98))
        f = _font(style, size)
        l, t, r, b = self.d.textbbox((0, 0), s, font=f)
        cy = (y0 + y1) / 2 * SS
        x = {"l": x0 * SS - l, "r": x1 * SS - r}.get(align, (x0 + x1) / 2 * SS - (l + r) / 2)
        self.d.text((x, cy - (t + b) / 2), s, font=f, fill=tuple(fill))
        return (r - l) / SS

    def done(self):
        return self.img.resize((self.w, self.h), Image.LANCZOS)


def icon(sk, name, box, fg, bg):
    """A small picture of the kind (or a chain's logo, never theirs) in the square box."""
    x0, y0, x1, y1 = box
    s = min(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    U = lambda u, v: (cx + (u - 0.5) * s, cy + (v - 0.5) * s)
    fg, bg = tuple(fg), tuple(bg)
    w = max(1.5, s * 0.07)
    if name == "cross":
        sk.poly([U(0.37, 0.08), U(0.63, 0.08), U(0.63, 0.37), U(0.92, 0.37), U(0.92, 0.63), U(0.63, 0.63), U(0.63, 0.92),
                 U(0.37, 0.92), U(0.37, 0.63), U(0.08, 0.63), U(0.08, 0.37), U(0.37, 0.37)], fg)
    elif name == "cup":
        sk.poly([U(0.18, 0.38), U(0.72, 0.38), U(0.66, 0.78), U(0.24, 0.78)], fg)
        sk.ellipse(*U(0.62, 0.42), *U(0.88, 0.66), outline=fg, width=w)
        sk.ellipse(*U(0.1, 0.78), *U(0.82, 0.9), fill=fg)
        for u in (0.33, 0.5):
            sk.line([U(u, 0.32), U(u + 0.05, 0.22), U(u - 0.02, 0.13)], fg, w * 0.7)
    elif name == "cutlery":
        sk.rect(*U(0.24, 0.1), *U(0.44, 0.42), fill=fg)
        for u in (0.29, 0.36):
            sk.rect(*U(u, 0.1), *U(u + 0.03, 0.32), fill=bg)
        sk.rect(*U(0.31, 0.4), *U(0.37, 0.92), fill=fg)
        sk.poly([U(0.6, 0.1), U(0.72, 0.1), U(0.72, 0.92), U(0.66, 0.92), U(0.66, 0.55), U(0.58, 0.5)], fg)
    elif name == "glass":
        sk.poly([U(0.15, 0.12), U(0.85, 0.12), U(0.5, 0.55)], fg)
        sk.rect(*U(0.47, 0.5), *U(0.53, 0.86), fill=fg)
        sk.rect(*U(0.28, 0.84), *U(0.72, 0.9), fill=fg)
        sk.ellipse(*U(0.62, 0.02), *U(0.76, 0.16), fill=fg)
    elif name == "cone":
        sk.poly([U(0.3, 0.45), U(0.7, 0.45), U(0.5, 0.95)], (205, 150, 80))
        sk.ellipse(*U(0.28, 0.12), *U(0.72, 0.52), fill=fg)
        sk.ellipse(*U(0.38, 0.02), *U(0.62, 0.24), fill=fg)
    elif name == "slice":
        sk.poly([U(0.12, 0.18), U(0.88, 0.18), U(0.5, 0.92)], fg)
        sk.rect(*U(0.1, 0.12), *U(0.9, 0.22), fill=(200, 140, 60))
        for u, v in ((0.38, 0.32), (0.6, 0.36), (0.5, 0.56)):
            sk.ellipse(*U(u - 0.06, v - 0.06), *U(u + 0.06, v + 0.06), fill=(190, 30, 30) if fg != (190, 30, 30) else bg)
    elif name == "bread":
        sk.ellipse(*U(0.06, 0.3), *U(0.94, 0.78), fill=fg)
        for u in (0.3, 0.48, 0.66):
            sk.line([U(u, 0.4), U(u + 0.1, 0.66)], bg, w)
    elif name == "cleaver":
        sk.poly([U(0.1, 0.25), U(0.66, 0.25), U(0.66, 0.66), U(0.16, 0.66)], fg)
        sk.ellipse(*U(0.18, 0.31), *U(0.28, 0.41), fill=bg)
        sk.rect(*U(0.66, 0.38), *U(0.94, 0.5), fill=fg)
    elif name == "apple":
        sk.ellipse(*U(0.16, 0.26), *U(0.84, 0.92), fill=fg)
        sk.line([U(0.5, 0.3), U(0.52, 0.1)], fg, w)
        sk.ellipse(*U(0.54, 0.08), *U(0.8, 0.22), fill=fg)
    elif name == "flower":
        for a in range(5):
            u, v = 0.5 + 0.22 * math.cos(a * 1.2566 - 1.57), 0.42 + 0.22 * math.sin(a * 1.2566 - 1.57)
            sk.ellipse(*U(u - 0.15, v - 0.15), *U(u + 0.15, v + 0.15), fill=fg)
        sk.ellipse(*U(0.41, 0.33), *U(0.59, 0.51), fill=bg)
        sk.line([U(0.5, 0.62), U(0.5, 0.96)], fg, w)
    elif name == "paper":
        sk.rect(*U(0.14, 0.12), *U(0.86, 0.88), fill=fg)
        sk.rect(*U(0.22, 0.2), *U(0.78, 0.34), fill=bg)
        for v in (0.44, 0.56, 0.68, 0.8):
            sk.line([U(0.22, v), U(0.78, v)], bg, w * 0.6)
    elif name == "scissors":
        sk.ellipse(*U(0.12, 0.62), *U(0.42, 0.92), outline=fg, width=w)
        sk.ellipse(*U(0.58, 0.62), *U(0.88, 0.92), outline=fg, width=w)
        sk.poly([U(0.36, 0.66), U(0.42, 0.62), U(0.78, 0.06), U(0.72, 0.06)], fg)
        sk.poly([U(0.64, 0.66), U(0.58, 0.62), U(0.22, 0.06), U(0.28, 0.06)], fg)
    elif name == "glasses":
        sk.ellipse(*U(0.06, 0.36), *U(0.44, 0.7), outline=fg, width=w)
        sk.ellipse(*U(0.56, 0.36), *U(0.94, 0.7), outline=fg, width=w)
        sk.arc((*U(0.4, 0.38), *U(0.6, 0.58)), 200, 340, fg, w)
    elif name == "bottle":
        sk.rect(*U(0.42, 0.06), *U(0.58, 0.32), fill=fg)
        sk.rect(*U(0.32, 0.36), *U(0.68, 0.94), fill=fg, radius=s * 0.06)
        sk.poly([U(0.42, 0.3), U(0.58, 0.3), U(0.68, 0.4), U(0.32, 0.4)], fg)
    elif name == "bike":
        for u in (0.24, 0.76):
            sk.ellipse(*U(u - 0.2, 0.46), *U(u + 0.2, 0.86), outline=fg, width=w)
        sk.line([U(0.24, 0.66), U(0.44, 0.38), U(0.66, 0.38), U(0.76, 0.66), U(0.5, 0.66), U(0.24, 0.66)], fg, w)
        sk.line([U(0.44, 0.38), U(0.5, 0.66)], fg, w)
        sk.line([U(0.4, 0.28), U(0.5, 0.28)], fg, w)
        sk.line([U(0.66, 0.38), U(0.62, 0.24), U(0.72, 0.24)], fg, w)
    elif name == "car":
        sk.poly([U(0.06, 0.62), U(0.12, 0.46), U(0.3, 0.42), U(0.4, 0.28), U(0.66, 0.28), U(0.78, 0.42), U(0.94, 0.48),
                 U(0.94, 0.66), U(0.06, 0.66)], fg)
        sk.poly([U(0.42, 0.33), U(0.52, 0.33), U(0.52, 0.42), U(0.36, 0.42)], bg)
        sk.poly([U(0.56, 0.33), U(0.64, 0.33), U(0.72, 0.42), U(0.56, 0.42)], bg)
        for u in (0.26, 0.74):
            sk.ellipse(*U(u - 0.1, 0.56), *U(u + 0.1, 0.76), fill=bg, outline=fg, width=w)
    elif name in ("stars", "star3"):
        n = 3
        for i in range(n):
            u = 0.5 + (i - (n - 1) / 2) * 0.3
            pts = [U(u + 0.14 * math.cos(-1.5708 + k * 2.513) * (1 if k % 2 == 0 else 1), 0.5 + 0.14 * math.sin(-1.5708 + k * 2.513))
                   for k in range(5)]
            sk.poly(pts, fg)
    elif name == "hanger":
        sk.arc((*U(0.42, 0.1), *U(0.58, 0.3)), 180, 450, fg, w)
        sk.line([U(0.5, 0.3), U(0.1, 0.72), U(0.9, 0.72), U(0.5, 0.3)], fg, w)
    elif name == "paw":
        sk.ellipse(*U(0.28, 0.48), *U(0.72, 0.88), fill=fg)
        for u, v in ((0.2, 0.36), (0.38, 0.18), (0.62, 0.18), (0.8, 0.36)):
            sk.ellipse(*U(u - 0.09, v - 0.11), *U(u + 0.09, v + 0.11), fill=fg)
    elif name == "square":
        sk.rect(*U(0.1, 0.1), *U(0.9, 0.9), fill=fg)
        sk.text("B", (*U(0.1, 0.12), *U(0.9, 0.88)), "serif", bg)
    elif name == "M":
        sk.text("M", (*U(0.0, 0.05), *U(1.0, 0.95)), "sans", fg)
    elif name == "keys":
        for a in (0.0, 2.094, 4.189):
            ca, sa = math.cos(a - 1.5708), math.sin(a - 1.5708)
            sk.line([U(0.5, 0.55), U(0.5 + 0.38 * ca, 0.55 + 0.38 * sa)], fg, w)
            u, v = 0.5 + 0.38 * ca, 0.55 + 0.38 * sa
            sk.ellipse(*U(u - 0.09, v - 0.09), *U(u + 0.09, v + 0.09), outline=fg, width=w)
    elif name == "gable":
        sk.rect(*U(0.06, 0.06), *U(0.94, 0.94), fill=fg)
        sk.line([U(0.22, 0.85), U(0.78, 0.25)], bg, w * 1.4)
        sk.line([U(0.78, 0.85), U(0.22, 0.25)], bg, w * 1.4)
        sk.poly([U(0.78, 0.25), U(0.86, 0.14), U(0.7, 0.18)], bg)
        sk.poly([U(0.22, 0.25), U(0.14, 0.14), U(0.3, 0.18)], bg)
    elif name == "tree":
        sk.ellipse(*U(0.04, 0.04), *U(0.96, 0.96), fill=bg, outline=(225, 30, 40), width=w)
        sk.poly([U(0.5, 0.14), U(0.78, 0.74), U(0.22, 0.74)], fg)
        sk.rect(*U(0.46, 0.74), *U(0.54, 0.86), fill=fg)
    elif name == "ring":
        sk.ellipse(*U(0.04, 0.04), *U(0.96, 0.96), fill=(255, 214, 0), outline=(226, 0, 26), width=w * 1.2)
    elif name == "stripes":
        for i, col in enumerate(((255, 140, 0), (255, 210, 0), (110, 190, 235))):
            o = 0.22 * i
            sk.poly([U(0.1 + o, 0.9), U(0.26 + o, 0.9), U(0.56 + o, 0.1), U(0.4 + o, 0.1)], col)
    elif name == "humps":
        for i in range(3):
            sk.arc((*U(0.06 + 0.29 * i, 0.2), *U(0.36 + 0.29 * i, 1.4)), 180, 360, fg, w * 1.6)
    elif name == "oval":
        sk.ellipse(*U(0.0, 0.2), *U(1.0, 0.8), fill=fg)
    elif name == "quarters":
        sk.ellipse(*U(0.06, 0.06), *U(0.94, 0.94), fill=(20, 20, 20))
        sk.d.pieslice([v * SS for v in (*U(0.16, 0.16), *U(0.84, 0.84))], 180, 270, fill=(20, 120, 210))
        sk.d.pieslice([v * SS for v in (*U(0.16, 0.16), *U(0.84, 0.84))], 0, 90, fill=(20, 120, 210))
        sk.d.pieslice([v * SS for v in (*U(0.16, 0.16), *U(0.84, 0.84))], 90, 180, fill=(255, 255, 255))
        sk.d.pieslice([v * SS for v in (*U(0.16, 0.16), *U(0.84, 0.84))], 270, 360, fill=(255, 255, 255))
    elif name == "dot":
        sk.ellipse(*U(0.3, 0.3), *U(0.7, 0.7), fill=fg)
    elif name == "swoosh":
        sk.arc((*U(-0.2, -0.6), *U(1.2, 0.95)), 30, 150, fg, w * 1.5)


def fork_logo(sk, box, red, white):
    """The parody of the post's sign: a red square with a white fork."""
    x0, y0, x1, y1 = box
    s = min(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    U = lambda u, v: (cx + (u - 0.5) * s, cy + (v - 0.5) * s)
    sk.rect(*U(0.06, 0.06), *U(0.94, 0.94), fill=tuple(red))
    sk.rect(*U(0.3, 0.16), *U(0.7, 0.5), fill=tuple(white))
    for u in (0.38, 0.48, 0.58):
        sk.rect(*U(u, 0.16), *U(u + 0.04, 0.38), fill=tuple(red))
    sk.rect(*U(0.45, 0.48), *U(0.55, 0.86), fill=tuple(white))


def sign_image(place, w, h, big=False):
    """The sign of the place: its name and logo on its board, w x h px."""
    bg, fg, ac = (tuple(c) for c in place.colours)
    sk = Sketch(w, h, bg)
    m = 0.1 * h
    if not place.brand and place.kind not in ("post",):
        sk.rect(m * 0.45, m * 0.45, w - m * 0.45, h - m * 0.45, outline=ac, width=max(1.5, h * 0.025))
    x = m * 1.4
    logo = place.logo
    if logo:
        box = (x, m * 1.2, x + h - 2.4 * m, h - m * 1.2)
        if logo == "fork":
            fork_logo(sk, box, ac if place.brand in ("posta", "postfinance") or place.kind == "post" else fg, bg)
        elif logo == "bar":
            pass
        else:
            icon(sk, logo, box, ac if logo not in ("M", "oval", "dot", "swoosh", "humps") else fg, bg)
        if logo not in ("bar", "swoosh"):
            x = box[2] + m
    if place.brand == "ikea":
        sk.ellipse(x - 0.4 * m, m * 0.9, w - m, h - m * 0.9, fill=(255, 218, 26))
        sk.text(place.title, (x + m, m * 1.8, w - 2 * m, h - m * 1.8), place.font, fg)
        return sk.done()
    if place.brand == "toyota":
        sk.ellipse(x - h, m * 0.9, x - m, h - m * 0.9, outline=fg, width=h * 0.04)
    x1 = w - m * 1.4
    if place.sub:
        if place.brand:                       # chains: the second word beside the name, in the accent colour
            tw = sk.text(place.title, (x, h * 0.16, x + (x1 - x) * 0.62, h * 0.84), place.font, fg, align="l")
            sk.text(place.sub, (x + tw + m, h * 0.3, x1, h * 0.76), "sans_it", ac, align="l")
        else:
            sk.text(place.title, (x, h * 0.12, x1, h * 0.66), place.font, fg)
            sk.text(place.sub, (x, h * 0.7, x1, h * 0.88), "sans", ac)
    else:
        sk.text(place.title, (x, h * 0.15, x1, h * 0.85), place.font, fg)
    if place.brand == "denner":
        sk.arc((x, h * 0.66, x1, h * 1.1), 200, 340, ac, h * 0.05)
    if place.brand == "coop":
        sk.rect(m * 1.4, h * 0.86, w - m * 1.4, h * 0.9, fill=ac)
    if place.brand == "aldi":
        for i, col in enumerate(((255, 140, 0), (255, 210, 0), (110, 190, 235))):
            sk.rect(w - m * 3.6 + i * m, 0, w - m * 2.9 + i * m, h, fill=col)
    return sk.done()


def band_image(place, w, h, repeat=2):
    """The edge of a canopy or a valance: the name repeated on the board colour."""
    bg, fg, ac = (tuple(c) for c in place.colours)
    sk = Sketch(w, h, bg)
    for i in range(repeat):
        sk.text(place.title, (w * i / repeat + h * 0.4, h * 0.14, w * (i + 1) / repeat - h * 0.4, h * 0.86), place.font, fg)
    return sk.done()


def text_board(lines, w, h, bg, fg, style="sans", frame=None):
    """A board with lines of text (menus, prices, newspapers)."""
    sk = Sketch(w, h, bg)
    if frame:
        sk.rect(0, 0, w - 1, h - 1, outline=frame, width=max(2, w * 0.04))
    n = len(lines)
    for i, (s, k) in enumerate(lines):
        y0 = h * (0.08 + 0.84 * i / n)
        sk.text(s, (w * 0.1, y0, w * 0.9, y0 + 0.84 * h / n * k), style, fg)
    return sk.done()


class Atlas:
    """Drawings packed into pages (shelves of their height); put() gives their rectangle as (material, u0, v0, u1,
    v1). The pages are written as PNG; each page is one or more materials (mats(page))."""

    def __init__(self, prefix, size, mode="RGB", fill=(128, 128, 128)):
        self.prefix, self.size, self.mode, self.fill = prefix, size, mode, fill
        self.pages = []
        self.cache = {}

    def _page(self):
        img = Image.new(self.mode, (self.size, self.size), self.fill)
        self.pages.append([img, [], 0])
        return len(self.pages) - 1

    def put(self, img, key=None, pad=4):
        if key is not None and key in self.cache:
            return self.cache[key]
        w, h = img.size[0] + 2 * pad, img.size[1] + 2 * pad
        hh = int(math.ceil(h / 16.0)) * 16
        if not self.pages:
            self._page()
        for pi in (len(self.pages) - 1, None):
            if pi is None:
                pi = self._page()
            page = self.pages[pi]
            spot = None
            for sh in page[1]:
                if sh[1] == hh and sh[2] + w <= self.size:
                    spot = sh
                    break
            if spot is None and page[2] + hh <= self.size:
                spot = [page[2], hh, 0]
                page[1].append(spot)
                page[2] += hh
            if spot is not None:
                break
        x, y = spot[2], spot[0]
        spot[2] += w
        big = img.resize((w, h), Image.NEAREST)              # the edges spread into the padding (mipmaps)
        page[0].paste(big, (x, y))
        page[0].paste(img, (x + pad, y + pad))
        S = float(self.size)
        r = (pi, (x + pad + 0.5) / S, 1 - (y + pad + img.size[1] - 0.5) / S, (x + pad + img.size[0] - 0.5) / S,
             1 - (y + pad + 0.5) / S)
        if key is not None:
            self.cache[key] = r
        return r

    def swatch(self, rgb):
        """A plain colour: a point in the middle of a block of it."""
        key = ("swatch",) + tuple(int(v) for v in rgb)
        if key not in self.cache:
            pi, u0, v0, u1, v1 = self.put(Image.new(self.mode, (24, 24), tuple(int(v) for v in rgb) +
                                                    ((255,) if self.mode == "RGBA" else ())), pad=4)
            u, v = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            self.cache[key] = (pi, u, v, u, v)
        return self.cache[key]


class Tex:
    """The texture pages of the step and the materials on them."""

    def __init__(self):
        self.signs = Atlas("signs", SIGN_PAGE, fill=(90, 90, 90))
        self.props = Atlas("props", PROP_PAGE, fill=(120, 120, 120))
        self.leaves = Atlas("leaves", LEAF_PAGE, mode="RGBA", fill=(60, 90, 40, 0))

    # rectangles with the material they are drawn with
    def sign(self, img, key=None, lit=True):
        pi, *r = self.signs.put(img, key)
        return (f"mp_shop_{'sign' if lit else 'board'}{pi}", *r)

    def prop(self, img, key=None, glass=False):
        pi, *r = self.props.put(img, key)
        return (f"mp_shop_{'glass' if glass else 'props'}{pi}", *r)

    def col(self, rgb):
        pi, *r = self.props.swatch(rgb)
        return (f"mp_shop_props{pi}", *r)

    def lit_col(self, rgb):
        return self.sign_col(rgb, True)

    def sign_col(self, rgb, lit):
        pi, *r = self.signs.swatch(rgb)
        return (f"mp_shop_{'sign' if lit else 'board'}{pi}", *r)

    def leaf(self, img, key=None):
        pi, *r = self.leaves.put(img, key)
        return (f"mp_shop_leaves{pi}", *r)

    def write(self, dst):
        """The pages as PNG in dst and the materials: {file name: path}, [materials]."""
        t = f"/levels/{LEVEL_NAME}/{D}"
        files, mats = {}, []
        for i, (img, _, _) in enumerate(self.signs.pages):
            n = f"t_shop_signs{i}.color.png"
            img.save(os.path.join(dst, n))
            files[n] = os.path.join(dst, n)
            mats.append(bng.material(f"mp_shop_sign{i}", f"{t}/{n}", roughness=0.45, double_sided=True,
                                     extra={"Stages": [{"baseColorMap": f"{t}/{n}", "roughnessFactor": 0.45,
                                                        "emissiveMap": f"{t}/{n}", "emissiveFactor": [0.8, 0.8, 0.8],
                                                        "instanceEmissive": True}, {}, {}, {}]}))
            mats.append(bng.material(f"mp_shop_board{i}", f"{t}/{n}", roughness=0.55, double_sided=True))
        for i, (img, _, _) in enumerate(self.props.pages):
            n = f"t_shop_props{i}.color.png"
            img.save(os.path.join(dst, n))
            files[n] = os.path.join(dst, n)
            mats.append(bng.material(f"mp_shop_props{i}", f"{t}/{n}", roughness=0.7, double_sided=True))
            mats.append(bng.material(f"mp_shop_glass{i}", f"{t}/{n}", roughness=0.08, metallic=0.2, double_sided=True))
        for i, (img, _, _) in enumerate(self.leaves.pages):
            n = f"t_shop_leaves{i}.color.png"
            img.save(os.path.join(dst, n))
            files[n] = os.path.join(dst, n)
            mats.append(bng.material(f"mp_shop_leaves{i}", f"{t}/{n}", roughness=0.85, alpha_test=90, double_sided=True))
        return files, mats


def stripes_image(c1, c2, plain=False, n=3):
    """An awning's cloth: stripes along its slope (n pairs across), or plain with a seam."""
    w, h = 128, 64
    img = Image.new("RGB", (w, h), tuple(c1))
    d = ImageDraw.Draw(img)
    if not plain:
        for i in range(n):
            x0 = (2 * i + 1) * w / (2 * n)
            d.rectangle([x0, 0, x0 + w / (2 * n) - 1, h], fill=tuple(c2))
    else:
        d.rectangle([0, h - 6, w, h], fill=tuple(int(v * 0.85) for v in c1))
    return img


def pattern(kind, rng):
    """The prints and patterns of the props (rng: seeded)."""
    if kind.startswith("cloth"):
        c1, c2 = {"cloth_red": ((200, 30, 35), (245, 245, 240)), "cloth_green": ((40, 120, 60), (245, 245, 240)),
                  "cloth_blue": ((40, 70, 150), (245, 245, 240))}.get(kind, ((245, 245, 240), (230, 228, 220)))
        img = Image.new("RGB", (64, 64), c2)
        d = ImageDraw.Draw(img)
        for i in range(8):
            for j in range(8):
                if (i + j) % 2 == 0:
                    d.rectangle([i * 8, j * 8, i * 8 + 7, j * 8 + 7], fill=c1)
        return img
    if kind == "wood":
        a = np.zeros((64, 128, 3), np.float32) + np.array(WOOD, np.float32)
        a *= (0.85 + 0.15 * np.sin(np.linspace(0, 40, 128))[None, :, None] * rng.uniform(0.6, 1.0, (64, 1, 1)))
        a[::16] *= 0.6
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if kind == "grid":
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for i in range(0, 64, 8):
            d.line([i, 0, i, 63], fill=(190, 192, 196, 255), width=2)
            d.line([0, i, 63, i], fill=(190, 192, 196, 255), width=2)
        return img
    if kind == "gas":
        img = Image.new("RGB", (128, 128), (60, 60, 64))
        d = ImageDraw.Draw(img)
        for i in range(4):
            x = 8 + i * 30
            d.rounded_rectangle([x, 30, x + 24, 124], 8, fill=(30, 90, 170) if i % 2 else (90, 140, 200))
            d.rectangle([x + 8, 18, x + 16, 32], fill=(150, 150, 150))
        for i in range(0, 128, 10):
            d.line([i, 0, i, 127], fill=(200, 200, 200), width=2)
            d.line([0, i, 127, i], fill=(200, 200, 200), width=2)
        return img
    if kind.startswith("fruit"):
        cols = {"fruit_orange": ((245, 140, 20), (230, 120, 10)), "fruit_apple": ((200, 30, 30), (130, 170, 40)),
                "fruit_lemon": ((245, 220, 40), (230, 200, 30)), "fruit_green": ((70, 150, 50), (110, 180, 60)),
                "fruit_tomato": ((220, 40, 30), (200, 30, 20))}[kind]
        img = Image.new("RGB", (64, 64), (60, 40, 25))
        d = ImageDraw.Draw(img)
        for _ in range(26):
            x, y, r = rng.uniform(0, 64), rng.uniform(0, 64), rng.uniform(6, 9)
            c = cols[int(rng.integers(2))]
            d.ellipse([x - r, y - r, x + r, y + r], fill=c, outline=tuple(int(v * 0.7) for v in c))
        return img
    if kind == "papers":
        img = Image.new("RGB", (128, 128), (235, 235, 230))
        sk = Sketch(128, 128, (235, 235, 230))
        heads = (("Corriere del Ticinese", (20, 20, 20)), ("laRegiona", (200, 20, 30)), ("21 Minuti", (20, 80, 160)),
                 ("Il Giornalino", (20, 20, 20)))
        for i, (s, c) in enumerate(heads):
            y = i * 32
            sk.rect(2, y + 2, 126, y + 30, fill=(245, 245, 240), outline=(150, 150, 150), width=1)
            sk.text(s, (6, y + 4, 122, y + 14), "serif", c)
            for k in range(3):
                sk.line([(8, y + 18 + k * 4), (120, y + 18 + k * 4)], (120, 120, 120), 1)
        return sk.done()
    if kind == "glass_door":
        w, h = 256, 160
        a = np.zeros((h, w, 3), np.float32)
        yy = np.linspace(0, 1, h)[:, None]
        xx = np.linspace(0, 1, w)[None, :]
        a[:] = (np.array([0.22, 0.27, 0.30]) + 0.25 * np.clip(1 - np.abs(xx - yy * 0.6 - 0.2) * 4, 0, 1)[..., None]) * 255
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        alu = (190, 192, 195)
        for x in (0, 64, 127, 128, 192, 255):
            d.rectangle([x - 3, 0, x + 3, h], fill=alu)
        d.rectangle([0, 0, w, 8], fill=alu)
        d.rectangle([0, h - 8, w, h], fill=alu)
        d.rectangle([100, 70, 156, 76], fill=(220, 220, 220))
        return img
    if kind == "barber":
        img = Image.new("RGB", (64, 128), (255, 255, 255))
        d = ImageDraw.Draw(img)
        for i in range(-4, 10):
            y = i * 24
            d.polygon([(0, y), (64, y + 32), (64, y + 40), (0, y + 8)], fill=(200, 20, 30) if i % 2 else (20, 50, 150))
        return img
    if kind == "chalk":
        return text_board([("MENU", 1.0), ("del giorno", 0.7), ("Risotto", 0.6), ("Polenta e brasato", 0.6),
                           ("Torta di pane", 0.6)], 96, 128, (35, 45, 40), (240, 240, 235), "script", (120, 85, 50))
    return Image.new("RGB", (32, 32), (128, 128, 128))


def leaf_image(kind, rng):
    """Cut-out pictures: foliage, flower bunches, a bicycle wheel."""
    if kind == "wheel":
        sk = Sketch(64, 64, (0, 0, 0, 0), "RGBA")
        sk.ellipse(3, 3, 61, 61, outline=(25, 25, 25, 255), width=5)
        for a in range(0, 180, 30):
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            sk.line([(32 - 27 * ca, 32 - 27 * sa), (32 + 27 * ca, 32 + 27 * sa)], (170, 170, 170, 255), 1)
        sk.ellipse(28, 28, 36, 36, fill=(120, 120, 120, 255))
        return sk.done()
    w, h = 128, 128
    img = np.zeros((h, w, 4), np.uint8)
    Y, X = np.mgrid[0:h, 0:w]
    leaf = np.zeros((h, w), bool)
    for _ in range(60):
        cx, cy, r = rng.uniform(10, w - 10), h - rng.uniform(0, 0.85) ** 1.3 * h, rng.uniform(6, 14)
        leaf |= (X - cx) ** 2 + (Y - cy) ** 2 < r ** 2
    shade = 0.75 + 0.3 * rng.uniform(size=(h, w))
    col = np.array([40, 85, 30])[None, None] * shade[..., None]
    if kind.startswith("flowers"):
        fl = {"flowers_red": (210, 30, 40), "flowers_yellow": (245, 200, 30), "flowers_pink": (235, 110, 160),
              "flowers_white": (245, 245, 240), "flowers_purple": (140, 60, 170)}[kind]
        f = np.zeros((h, w), bool)
        for _ in range(45):
            cx, cy, r = rng.uniform(8, w - 8), rng.uniform(0.05, 0.6) * h, rng.uniform(4, 7)
            f |= (X - cx) ** 2 + (Y - cy) ** 2 < r ** 2
        col = np.where(f[..., None], np.array(fl)[None, None] * (0.85 + 0.2 * rng.uniform(size=(h, w, 1))), col)
        leaf |= f
    img[..., :3] = np.clip(col, 0, 255).astype(np.uint8)
    img[..., 3] = leaf * 255
    return Image.fromarray(img, "RGBA")


# ------------------------------------------------------------------ meshes
class Piece:
    """Triangles with texture coordinates by material, in a frame of its own (x, y, z)."""

    def __init__(self):
        self.parts = {}

    def _put(self, mat, T, UV):
        a = self.parts.setdefault(mat, ([], []))
        a[0].append(np.asarray(T, np.float64).reshape(-1, 3, 3))
        a[1].append(np.asarray(UV, np.float64).reshape(-1, 3, 2))

    def tri(self, a, b, c, r, uv=None):
        mat, u0, v0, u1, v1 = r
        self._put(mat, [[a, b, c]], uv if uv is not None else [[(u0, v0), (u1, v0), (u1, v1)]])

    def quad(self, a, b, c, d, r):
        """a b c d counter-clockwise seen from the front: r's corners (u0, v0), (u1, v0), (u1, v1), (u0, v1)."""
        mat, u0, v0, u1, v1 = r
        self._put(mat, [[a, b, c], [a, c, d]], [[(u0, v0), (u1, v0), (u1, v1)], [(u0, v0), (u1, v1), (u0, v1)]])

    def box(self, lo, hi, r, faces=None, skip=()):
        """An upright box from lo to hi; r on every face, or faces {'+x', '-x', '+y', '-y', '+z', '-z': r}."""
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        F = {"-y": ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
             "+y": ((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)),
             "+x": ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)),
             "-x": ((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)),
             "+z": ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
             "-z": ((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0))}
        for k, q in F.items():
            if k in skip:
                continue
            self.quad(*q, (faces or {}).get(k, r))

    def prism(self, c, r0, r1, z0, z1, n, r, top=None, bottom=None, phase=0.0, wrap=False):
        """An upright n-sided frustum round c (x, y) from radius r0 at z0 to r1 at z1; wrap: r once round it."""
        a = phase + np.arange(n + 1) * 2 * math.pi / n
        A = np.column_stack([c[0] + r0 * np.cos(a), c[1] + r0 * np.sin(a), np.full(n + 1, z0)])
        B = np.column_stack([c[0] + r1 * np.cos(a), c[1] + r1 * np.sin(a), np.full(n + 1, z1)])
        mat, u0, v0, u1, v1 = r
        for k in range(n):
            if wrap:
                ua, ub = u0 + (u1 - u0) * k / n, u0 + (u1 - u0) * (k + 1) / n
                self.quad(A[k], A[k + 1], B[k + 1], B[k], (mat, ua, v0, ub, v1))
            else:
                self.quad(A[k], A[k + 1], B[k + 1], B[k], r)
        if top is not None and r1 > 0:
            ctr = (c[0], c[1], z1)
            for k in range(n):
                self.tri(ctr, B[k], B[k + 1], top, [[(top[1], top[2])] * 3] if top[1] == top[3] else None)
        if bottom is not None and r0 > 0:
            ctr = (c[0], c[1], z0)
            for k in range(n):
                self.tri(ctr, A[k + 1], A[k], bottom, [[(bottom[1], bottom[2])] * 3] if bottom[1] == bottom[3] else None)

    def bar(self, a, b, w, r):
        """A square bar w across from a to b (3,)."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-6:
            return
        d /= L
        up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
        s1 = np.cross(d, up)
        s1 /= np.linalg.norm(s1)
        s2 = np.cross(s1, d)
        h = w / 2
        C = [s1 * h + s2 * h, -s1 * h + s2 * h, -s1 * h - s2 * h, s1 * h - s2 * h]
        for i in range(4):
            p, q = C[i], C[(i + 1) % 4]
            self.quad(a + q, a + p, b + p, b + q, r)

    def add(self, other):
        for m, (T, UV) in other.parts.items():
            a = self.parts.setdefault(m, ([], []))
            a[0].extend(T)
            a[1].extend(UV)
        return self

    def placed(self, x, y, z, ang):
        """The piece turned by ang about z and moved to (x, y, z)."""
        c, s = math.cos(ang), math.sin(ang)
        R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
        out = Piece()
        for m, (T, UV) in self.parts.items():
            TT = np.concatenate(T) @ R.T + np.array([x, y, z])
            out.parts[m] = ([TT], [np.concatenate(UV)])
        return out

    def count(self):
        return sum(sum(len(t) for t in T) for T, _ in self.parts.values())


class Out:
    """What the step adds: pieces by category (CATS) and tile, and the counts."""

    def __init__(self):
        self.tiles = {}
        self.counts = {}

    def add(self, cat, anchor, piece, what=None):
        size = CATS[cat][0]
        k = (cat, int(math.floor(anchor[0] / size)), int(math.floor(anchor[1] / size)))
        self.tiles.setdefault(k, Piece()).add(piece)
        if what:
            self.counts[what] = self.counts.get(what, 0) + 1

    def count(self, what, n=1):
        self.counts[what] = self.counts.get(what, 0) + n


# ------------------------------------------------------------------ the props, drawn here (a frame of their own: x
# along the façade, y out of it, z up from their foot)
def m_table(tex, cloth):
    """A square table, its cloth hanging over the sides."""
    s = Piece()
    h, a = 0.75, 0.42
    s.box((-a, -a, h - 0.24), (a, a, h), tex.prop(pattern(cloth, None), key=cloth), skip=("-z",))
    leg = tex.col(DARK_METAL)
    s.box((-0.035, -0.035, 0.03), (0.035, 0.035, h - 0.24), leg, skip=("-z", "+z"))
    s.box((-0.28, -0.035, 0), (0.28, 0.035, 0.03), leg, skip=("-z",))
    s.box((-0.035, -0.28, 0), (0.035, 0.28, 0.03), leg, skip=("-z",))
    return s


def m_round_table(tex, top):
    s = Piece()
    s.prism((0, 0), 0.33, 0.33, 0.71, 0.74, 8, tex.col(top), top=tex.col(top))
    s.box((-0.025, -0.025, 0.03), (0.025, 0.025, 0.71), tex.col(DARK_METAL), skip=("-z", "+z"))
    s.prism((0, 0), 0.22, 0.2, 0.0, 0.03, 6, tex.col(DARK_METAL), top=tex.col(DARK_METAL))
    return s


def m_chair(tex, col, wood=False):
    """A chair looking along +x."""
    s = Piece()
    c, f = tex.col(col), tex.col(DARK_METAL if not wood else DARK_WOOD)
    s.box((-0.2, -0.2, 0.43), (0.2, 0.2, 0.47), c)
    s.box((-0.23, -0.2, 0.47), (-0.19, 0.2, 0.88), c)
    for x in (-0.18, 0.16):
        for y in (-0.18, 0.16):
            s.box((x, y, 0.0), (x + 0.025, y + 0.025, 0.43), f, skip=("-z", "+z"))
    return s


def m_umbrella(tex, c1, c2, band=None, R=1.25, H=2.35):
    """(pole and foot, canopy): eight panels of two colours, a valance with the print band."""
    hard, soft = Piece(), Piece()
    hard.box((-0.025, -0.025, 0.08), (0.025, 0.025, H + 0.08), tex.col(WHITE), skip=("-z",))
    hard.box((-0.25, -0.25, 0.0), (0.25, 0.25, 0.08), tex.col(DARK_METAL), skip=("-z",))
    n = 8
    a = np.arange(n + 1) * 2 * math.pi / n + math.pi / n
    zr = H - 0.32
    apex = (0, 0, H + 0.04)
    for k in range(n):
        p, q = (R * math.cos(a[k]), R * math.sin(a[k]), zr), (R * math.cos(a[k + 1]), R * math.sin(a[k + 1]), zr)
        r = tex.col(c1 if k % 2 == 0 else c2)
        soft.tri(apex, p, q, r, [[r[1:3]] * 3])
    soft.prism((0, 0), R, R, zr - 0.16, zr, n, band or tex.col(c1), phase=math.pi / n)
    return hard, soft


def m_aboard(tex, img_rect, frame=DARK_WOOD, w=0.6, h=0.95):
    """A board standing as an A: the print on both sides."""
    s = Piece()
    a = w / 2
    s.quad((a, 0.24, 0), (-a, 0.24, 0), (-a, 0.03, h), (a, 0.03, h), img_rect)
    s.quad((-a, -0.24, 0), (a, -0.24, 0), (a, -0.03, h), (-a, -0.03, h), img_rect)
    fr = tex.col(frame)
    for x in (-a - 0.01, a + 0.01):
        s.bar((x, 0.24, 0), (x, 0.03, h), 0.03, fr)
        s.bar((x, -0.24, 0), (x, -0.03, h), 0.03, fr)
    s.bar((-a - 0.02, 0, h + 0.01), (a + 0.02, 0, h + 0.01), 0.04, fr)
    return s


def m_pot(tex, leaves, colour=TERRACOTTA, r=0.26, h=0.5, plant_h=0.8):
    """(pot, plant): an octagonal pot and its plant (two crossed cut-out pictures)."""
    hard, soft = Piece(), Piece()
    hard.prism((0, 0), r * 0.8, r, 0, h, 8, tex.col(colour), top=tex.col((60, 45, 30)))
    w = r * 1.5
    for ang in (0.0, math.pi / 2):
        c, s_ = math.cos(ang) * w, math.sin(ang) * w
        soft.quad((-c, -s_, h - 0.05), (c, s_, h - 0.05), (c, s_, h + plant_h), (-c, -s_, h + plant_h), leaves)
    return hard, soft


def m_bench(tex, L=1.5):
    s = Piece()
    wd, mt = tex.col(WOOD), tex.col(DARK_METAL)
    s.box((-L / 2, -0.2, 0.42), (L / 2, 0.2, 0.46), wd)
    s.box((-L / 2, -0.24, 0.5), (L / 2, -0.2, 0.86), wd)
    for x in (-L / 2 + 0.1, L / 2 - 0.15):
        s.box((x, -0.22, 0), (x + 0.05, 0.18, 0.42), mt, skip=("-z",))
    return s


def m_trolley(tex, grid):
    """A shopping trolley along +x (handle at -x)."""
    s = Piece()
    mt = tex.col(METAL)
    b0, b1 = 0.42, 0.95
    lo = [(-0.42, -0.26), (0.40, -0.21), (0.40, 0.21), (-0.42, 0.26)]
    P0 = [(x, y, b0) for x, y in lo]
    P1 = [(x * 1.05, y * 1.04, b1) for x, y in lo]
    for i in range(4):
        j = (i + 1) % 4
        s.quad(P0[i], P0[j], P1[j], P1[i], grid)
    s.quad(P0[3], P0[2], P0[1], P0[0], grid)
    s.bar((-0.5, -0.27, 1.0), (-0.5, 0.27, 1.0), 0.03, tex.col((200, 40, 40)))
    for y in (-0.22, 0.22):
        s.bar((-0.5, y, 1.0), (-0.44, y * 1.04, b1), 0.025, mt)
        s.bar((-0.42, y, 0.12), (0.42, y * 0.8, 0.12), 0.03, mt)
        s.bar((-0.42, y, 0.12), (-0.42, y, b0), 0.025, mt)
    for x, y in ((-0.4, -0.22), (-0.4, 0.22), (0.4, -0.18), (0.4, 0.18)):
        s.box((x - 0.05, y - 0.02, 0), (x + 0.05, y + 0.02, 0.1), tex.col((40, 40, 40)), skip=("-z",))
    return s


def m_shelter(tex, place, L=3.6, Dp=1.55, H=2.15):
    """A trolley shelter along x with the chain's name on its roof edge."""
    s = Piece()
    mt = tex.col(METAL)
    for x in (-L / 2, L / 2 - 0.08):
        for y in (0.0, Dp - 0.08):
            s.box((x, y, 0), (x + 0.08, y + 0.08, H), mt, skip=("-z", "+z"))
    bg, fg, ac = place.colours
    roof = tex.col(ac if sum(bg) > 690 else bg)
    s.box((-L / 2 - 0.1, -0.1, H), (L / 2 + 0.1, Dp + 0.1, H + 0.1), roof)
    band = tex.prop(band_image(place, 384, 48, 1), key=("band1", place.brand or place.id))
    s.box((-L / 2 - 0.1, Dp + 0.1, H - 0.22), (L / 2 + 0.1, Dp + 0.14, H + 0.1), roof, faces={"+y": band})
    s.box((-L / 2, -0.04, 0.9), (L / 2, 0.0, 2.0), tex.col((150, 160, 165)), skip=("-z", "+z"))
    return s


def m_fruit_stand(tex, rng):
    """A table with crates of fruit and vegetables in two steps."""
    s = Piece()
    wd = tex.prop(pattern("wood", np.random.default_rng(5)), key="wood")
    s.box((-0.8, -0.4, 0.55), (0.8, 0.4, 0.6), wd)
    for x in (-0.75, 0.7):
        for y in (-0.35, 0.3):
            s.box((x, y, 0), (x + 0.05, y + 0.05, 0.55), tex.col(DARK_WOOD), skip=("-z", "+z"))
    kinds = ["fruit_orange", "fruit_apple", "fruit_lemon", "fruit_green", "fruit_tomato"]
    k = int(rng.integers(5))
    for row, (y0, z0) in enumerate(((0.0, 0.6), (-0.38, 0.78))):
        for x in (-0.78, -0.26, 0.26):
            fr = kinds[k % 5]
            k += 1
            s.box((x, y0, z0), (x + 0.5, y0 + 0.36, z0 + 0.14), wd,
                  faces={"+z": tex.prop(pattern(fr, np.random.default_rng(len(fr))), key=fr)})
        if row == 1:
            s.box((-0.8, -0.4, 0.6), (0.8, -0.02, 0.78), tex.col(DARK_WOOD), skip=("-z",))
    return s


def m_crates(tex, rng, n=5):
    s = Piece()
    cols = [(40, 140, 60), (30, 80, 160), (200, 40, 40), (230, 180, 30)]
    for i in range(n):
        x, z = (i % 2) * 0.58 - 0.29, (i // 2) * 0.29
        c = cols[int(rng.integers(len(cols)))]
        s.box((x - 0.27, -0.18, z), (x + 0.27, 0.18, z + 0.28), tex.col(c), skip=("-z",) if z == 0 else ())
    return s


def m_box_print(tex, size, colour, front, top=None):
    """A box (gas cage, ice chest, newspaper stand...) with its print on the front."""
    w, d, h = size
    s = Piece()
    c = tex.col(colour)
    s.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), c, faces={"+y": front, "+z": top or c}, skip=("-z",))
    return s


def m_bin(tex, colour=(45, 75, 55)):
    s = Piece()
    s.prism((0, 0), 0.22, 0.25, 0, 0.92, 8, tex.col(colour), top=tex.col((40, 40, 40)))
    return s


def m_buckets(tex, rng, flower_rects):
    """(a stand of three steps and its buckets, the flowers)."""
    hard, soft = Piece(), Piece()
    wd = tex.col(GREEN_PAINT)
    zinc = tex.col((165, 170, 172))
    for k, (y, z) in enumerate(((0.3, 0.2), (0.0, 0.45), (-0.3, 0.7))):
        hard.box((-0.7, y - 0.15, 0), (0.7, y + 0.15, z), wd, skip=("-z",))
        for x in (-0.38, 0.0, 0.38):
            hard.prism((x, y), 0.1, 0.13, z, z + 0.26, 6, zinc)
            fr = flower_rects[int(rng.integers(len(flower_rects)))]
            for ang in (0.3, 1.87):
                c, s_ = math.cos(ang) * 0.2, math.sin(ang) * 0.2
                soft.quad((x - c, y - s_, z + 0.15), (x + c, y + s_, z + 0.15), (x + c, y + s_, z + 0.62),
                          (x - c, y - s_, z + 0.62), fr)
    return hard, soft


def m_rack(tex, rng):
    """A clothes rack along x with clothes hanging."""
    s = Piece()
    mt = tex.col(METAL)
    for x in (-0.7, 0.7):
        s.bar((x, 0, 0.02), (x, 0, 1.55), 0.035, mt)
        s.box((x - 0.04, -0.25, 0), (x + 0.04, 0.25, 0.03), mt, skip=("-z",))
    s.bar((-0.72, 0, 1.55), (0.72, 0, 1.55), 0.03, mt)
    cols = [(30, 30, 35), (200, 200, 205), (40, 70, 140), (170, 40, 50), (230, 200, 120), (80, 120, 80), (240, 240, 240)]
    for x in np.linspace(-0.6, 0.6, 7):
        c = cols[int(rng.integers(len(cols)))]
        ln = rng.uniform(0.6, 0.95)
        s.box((x - 0.02, -0.23, 1.5 - ln), (x + 0.03, 0.23, 1.5), tex.col(c))
    return s


def m_barrel(tex):
    s = Piece()
    wd = tex.col((120, 75, 40))
    s.prism((0, 0), 0.3, 0.36, 0, 0.45, 10, wd)
    s.prism((0, 0), 0.36, 0.3, 0.45, 0.9, 10, wd, top=tex.col((95, 60, 32)))
    for z in (0.12, 0.74):
        s.prism((0, 0), 0.34, 0.345, z, z + 0.04, 10, tex.col(DARK_METAL))
    return s


def m_bikes(tex, rng, wheel, n=3):
    """A low rack along x with n bicycles standing out of it (along y)."""
    s = Piece()
    mt = tex.col(METAL)
    L = 0.75 * n
    s.bar((-L / 2, 0.1, 0.35), (L / 2, 0.1, 0.35), 0.04, mt)
    for x in (-L / 2, L / 2):
        s.bar((x, 0.1, 0), (x, 0.1, 0.35), 0.04, mt)
    cols = [(200, 30, 30), (30, 90, 180), (30, 30, 30), (240, 200, 40), (60, 150, 70), (230, 230, 230)]
    for i in range(n):
        x = -L / 2 + 0.375 + 0.75 * i
        fr = tex.col(cols[int(rng.integers(len(cols)))])
        for yc in (0.25, 1.28):
            s.quad((x, yc - 0.34, 0.0), (x, yc + 0.34, 0.0), (x, yc + 0.34, 0.68), (x, yc - 0.34, 0.68), wheel)
        A, B, C, Dd = (x, 1.28, 0.34), (x, 0.8, 0.3), (x, 0.9, 0.82), (x, 0.35, 0.78)
        for a, b in ((A, B), (B, C), (C, A), (B, Dd), (Dd, C), (Dd, (x, 0.25, 0.34))):
            s.bar(a, b, 0.035, fr)
        s.box((x - 0.06, 0.85, 0.84), (x + 0.06, 1.05, 0.88), tex.col((25, 25, 25)))
        s.bar((x - 0.25, 0.38, 0.95), (x + 0.25, 0.38, 0.95), 0.025, tex.col((25, 25, 25)))
        s.bar((x, 0.35, 0.78), (x, 0.38, 0.95), 0.03, fr)
    return s


def m_flag_pole(tex, flag, H=3.4, W=0.7):
    """(pole and foot, flag): a feather flag standing."""
    hard, soft = Piece(), Piece()
    hard.bar((0, 0, 0.05), (0, 0, H), 0.04, tex.col(METAL))
    hard.box((-0.3, -0.3, 0), (0.3, 0.3, 0.06), tex.col(DARK_METAL), skip=("-z",))
    # v3.1: the print reads from the street (+y; seen from there x runs to the left), not mirrored
    soft.quad((W, 0, 0.8), (0.02, 0, 0.7), (0.02, 0, H), (W, 0, H - 0.2), flag)
    return hard, soft


def m_post_box(tex, front):
    s = Piece()
    s.bar((0, 0, 0), (0, 0, 0.9), 0.07, tex.col(DARK_METAL))
    s.box((-0.22, -0.16, 0.9), (0.22, 0.16, 1.45), tex.col((255, 204, 0)), faces={"+y": front})
    return s


# ------------------------------------------------------------------ prints
BOARDS = {
    "bakery": ([("PANE FRESCO", 1.0), ("ogni giorno", 0.7), ("Cornetti · Focaccia", 0.6)], (90, 55, 30), (250, 235, 205), "serif"),
    "butcher": ([("OFFERTA", 1.0), ("Luganighe", 0.7), ("Salametti nostrani", 0.6)], (245, 240, 230), (140, 20, 25), "serif"),
    "pharmacy": ([("FARMACIA", 1.0), ("di turno", 0.7), ("Consigli · Misure", 0.6)], (255, 255, 255), (0, 130, 60), "sans"),
    "hair": ([("TAGLIO", 1.0), ("DONNA · UOMO", 0.7), ("senza appuntamento", 0.55)], (20, 20, 22), (255, 255, 255), "script"),
    "kiosk": ([("LOTTO", 1.0), ("Quotidiani", 0.7), ("Tabacchi · Riviste", 0.6)], (20, 60, 140), (255, 255, 255), "sans"),
    "clothes": ([("SALDI", 1.0), ("-30%", 1.0), ("nuova collezione", 0.55)], (255, 255, 255), (200, 20, 30), "sans"),
    "wine": ([("DEGUSTAZIONE", 1.0), ("vini ticinesi", 0.7), ("Merlot del Ticino", 0.6)], (90, 20, 35), (235, 205, 130), "serif_it"),
    "gelato": ([("GELATI", 1.0), ("artigianali", 0.7), ("Coppe · Frappé", 0.6)], (250, 240, 245), (200, 60, 110), "script"),
    "price": ([("OCCASIONE", 0.7), ("CHF 18'900", 1.0), ("Leasing 2.9%", 0.6)], (255, 255, 255), (200, 20, 30), "sans"),
    "price2": ([("NUOVA", 0.7), ("CHF 32'500", 1.0), ("pronta consegna", 0.6)], (255, 255, 255), (20, 60, 140), "sans"),
    "shop": ([("APERTO", 1.0), ("Benvenuti", 0.7)], (245, 245, 240), (40, 40, 45), "serif_it"),
    "grocer": ([("OFFERTE", 1.0), ("della settimana", 0.65), ("Frutta di stagione", 0.6)], (255, 230, 0), (200, 20, 30), "sans"),
}


def board_rect(tex, key):
    if key == "menu":
        return tex.prop(pattern("chalk", None), key="chalk")
    lines, bg, fg, style = BOARDS[key]
    return tex.prop(text_board(lines, 96, 128, bg, fg, style, frame=tuple(int(v * 0.7) for v in fg)), key=("board", key))


def flag_rect(tex, kind, place=None):
    if kind == "swiss":
        img = Image.new("RGB", (64, 64), (215, 25, 32))
        d = ImageDraw.Draw(img)
        d.rectangle([26, 12, 38, 52], fill=(255, 255, 255))
        d.rectangle([12, 26, 52, 38], fill=(255, 255, 255))
        return tex.prop(img, key="flag_ch")
    if kind == "ticino":
        img = Image.new("RGB", (64, 96), (215, 25, 32))
        ImageDraw.Draw(img).rectangle([0, 48, 64, 96], fill=(20, 60, 150))
        return tex.prop(img, key="flag_ti")
    band = band_image(place, 320, 64, 1).rotate(90, expand=True)       # a feather flag: the name upright
    return tex.prop(band, key=("flag", place.brand or place.id))


def ice_rect(tex):
    img = Sketch(128, 96, (240, 244, 248))
    img.rect(0, 0, 128, 30, fill=(30, 90, 180))
    img.text("GHIACCIO", (8, 4, 120, 26), "sans", (255, 255, 255))
    img.text("ICE · EIS", (16, 40, 112, 62), "sans", (30, 90, 180))
    for x in range(14, 120, 22):
        img.d.regular_polygon(((x + 6) * SS, 80 * SS, 7 * SS), 6, fill=(150, 200, 240))
    return tex.prop(img.done(), key="ice")


def post_box_image():
    img = Sketch(96, 64, (255, 204, 0))
    fork_logo(img, (6, 6, 34, 34), (220, 0, 20), (255, 255, 255))
    img.text("LA PASTA", (38, 10, 92, 30), "sans", (20, 20, 20))
    img.rect(14, 44, 82, 52, fill=(40, 40, 40))
    return img.done()


# ------------------------------------------------------------------ the fronts of a place
class Layout:
    """Where the signs are on each wall line (Facade.key), shared by the places."""

    def __init__(self):
        self.taken = {}

    def free(self, f, ua, ub):
        return all(ub < a - 0.3 or ua > b + 0.3 for a, b in self.taken.get(f.key, []))

    def take(self, f, ua, ub):
        self.taken.setdefault(f.key, []).append((ua, ub))


class Ctx:
    """What the fronts and props of the places need: the site, the textures, the output, the layout."""

    def __init__(self, site, tex, out, layout):
        self.site, self.tex, self.out, self.layout = site, tex, out, layout

    def ground(self, f, ua, ub, s=0.4):
        us = np.linspace(ua, ub, 5)
        P = np.array([f.at(u, s) for u in us])
        return float(np.nanmin(self.site.ground(P[:, 0], P[:, 1])))

    def world(self, f, piece):
        """A piece drawn in the façade's frame (x along, y out, origin at u = 0 on the wall, z absolute)."""
        o = f.e * f.d
        return piece.placed(o[0], o[1], 0.0, f.angle())


def shop_group(f, u_p, near=10.0):
    """(ua, ub) of the run of shop windows facades.py drew nearest u_p, or None."""
    sh = sorted((a, b) for n, a, b, zb, zt in f.openings if n.startswith("shop"))
    runs = []
    for a, b in sh:
        if runs and a - runs[-1][1] < 1.2:
            runs[-1][1] = max(runs[-1][1], b)
        else:
            runs.append([a, b])
    if not runs:
        return None
    r = min(runs, key=lambda r: max(0.0, r[0] - u_p, u_p - r[1]))
    return tuple(r) if max(0.0, r[0] - u_p, u_p - r[1]) < near else None


def sign_span(place, f, ctx):
    """(ua, ub) of the place's sign along the façade, or None: over its shop windows, else round the point; moved
    along the wall where another sign is."""
    H, (lmin, lmax) = KINDS[place.kind][:2]
    u_p = float(np.clip(place.p @ f.t, f.u0 + 0.4, f.u1 - 0.4))
    g = shop_group(f, u_p)
    if g:
        c, L = 0.5 * (g[0] + g[1]), float(np.clip(g[1] - g[0] + 0.3, lmin, lmax))
    else:
        c, L = u_p, float(np.clip((0.35 if place.big else 0.45) * f.length, lmin, lmax))
    lo, hi = f.u0 + 0.3, f.u1 - 0.3
    for Lc in (L, max(lmin * 0.7, 1.6)):
        Lc = min(Lc, hi - lo)
        if Lc < 1.5:
            return None
        for dc in sorted(np.arange(-9.0, 9.01, 0.5), key=abs):
            ua = float(np.clip(c + dc - Lc / 2, lo, hi - Lc))
            if ctx.layout.free(f, ua, ua + Lc):
                return ua, ua + Lc
    return None


def sign_heights(f, ua, ub, zg, H):
    """(z0, z1) of a sign over [ua, ub]: above the ground-floor openings and SIGN_Z[0], below the openings of the
    floor above and the top of the wall; None where less than 0.38 m is left."""
    lo = zg + SIGN_Z[0]
    hi = f.top(ua, ub) - 0.25
    for n, a, b, zb, zt in f.openings:
        if b < ua - 0.05 or a > ub + 0.05:
            continue
        if zb < zg + 1.2:                                  # ground floor: a shop window's own fascia is covered
            lo = max(lo, (zb + 2.62) if n.startswith("shop") else zt + SIGN_Z[1])
        elif zb > zg + FIRST_FLOOR:
            hi = min(hi, zb - SIGN_Z[1])
    if hi - lo < 0.38:
        return None
    return lo, lo + min(H, hi - lo)


def sign_texture(place, ctx, L, H, lit, big=False):
    """The rectangle of the place's sign texture and its aspect (width / height)."""
    hpx = 2 * SIGN_H if big else SIGN_H
    asp = float(np.clip(L / H, 2.0, 8.0))
    wpx = int(round(hpx * asp / 32.0)) * 32
    key = ("sign", place.brand or place.id, wpx, hpx)
    return ctx.tex.sign(sign_image(place, wpx, hpx, big), key=key, lit=lit), wpx / hpx


def sign_board(piece, tex, place, rect, asp, ua, ub, y0, y1, z0, z1, lit):
    """A board from ua to ub, y0 to y1 out of the wall, z0 to z1: its front the sign (aspect x height wide in the
    middle, the rest its board colour), the other faces the board colour."""
    side = tex.sign_col(place.colours[0], lit)
    L, H = ub - ua, z1 - z0
    piece.box((ua, y0, z0), (ub, y1, z1), side, skip=("+y",))
    w = min(L, asp * H)
    m0, m1 = 0.5 * (ua + ub) - w / 2, 0.5 * (ua + ub) + w / 2
    # seen from outside the x axis runs to the left: the texture starts at m1
    piece.quad((m1, y1, z0), (m0, y1, z0), (m0, y1, z1), (m1, y1, z1), rect)
    mat, u0, v0, u1, v1 = rect
    eu = (u1 - u0) * 0.004
    for a, b, uu in ((ub, m1, u0 + eu), (m0, ua, u1 - eu)):
        if a - b > 0.005:
            piece.quad((a, y1, z0), (b, y1, z0), (b, y1, z1), (a, y1, z1), (mat, uu, v0, uu, v1))


def clear_depth(ctx, f, us, dmax, lift=0.15, start=0.6):
    """How far out of the wall (m) the ground at us stays off the carriageways and clear of posts, lamps, trunks."""
    site = ctx.site
    D = 0.0
    for s in np.arange(start, dmax + 0.01, 0.2):
        P = np.array([f.at(u, s + lift) for u in us])
        if site.on_carriageway(P[:, 0], P[:, 1]).any():
            break
        if any(site.obst.query_ball_point(q, 0.3, return_length=True) for q in P):
            break
        D = float(s)
    return D


def awning(place, f, ctx, ua, ub, z_att, zg, rng):
    """(piece, depth) of a sloped awning from ua to ub hung at z_att, as deep as the ground in front allows."""
    dmax = min(rng.uniform(*AWNING_D), (z_att - zg - AWNING_CLEAR) / AWNING_SLOPE)
    us = np.linspace(ua + 0.1, ub - 0.1, max(3, int((ub - ua) / 0.8) + 1))
    D = clear_depth(ctx, f, us, dmax)
    if D < 0.9:
        return None, 0.0
    bg, fg, ac = place.colours
    c1 = bg if sum(bg) < 690 else ac
    c2 = (245, 243, 236) if sum(c1) < 600 else fg
    plain = _unit(place.id, "plain") < 0.35
    tex = ctx.tex
    cloth = tex.prop(stripes_image(c1, c2, plain), key=("awning", tuple(c1), tuple(c2), plain))
    p = Piece()
    zf = z_att - D * AWNING_SLOPE
    n = max(1, int(round((ub - ua) / 1.0)))
    xs = np.linspace(ua, ub, n + 1)
    mat, u0, v0, u1, v1 = cloth
    for a, b in zip(xs[:-1], xs[1:]):
        p.quad((a, 0.02, z_att), (b, 0.02, z_att), (b, D, zf), (a, D, zf), cloth)
        p.quad((b, D, zf - 0.22), (a, D, zf - 0.22), (a, D, zf), (b, D, zf), (mat, u0, v0, u1, v0 + (v1 - v0) * 0.3))
    if place.kind in ("restaurant", "pizzeria", "grotto", "bar", "cafe", "bakery", "ice_cream") and ub - ua >= 2.4:
        band = tex.prop(band_image(place, 512, 48, max(1, int((ub - ua) / 3.5))), key=("valance", place.id))
        p.quad((ub, D + 0.005, zf - 0.22), (ua, D + 0.005, zf - 0.22), (ua, D + 0.005, zf), (ub, D + 0.005, zf), band)
    for x in (ua + 0.05, ub - 0.05):
        p.bar((x, 0.03, z_att - 0.55), (x, D - 0.05, zf - 0.02), 0.03, tex.col(METAL))
    return p, D


def projecting(place, ctx, kind, u, zc):
    """A sign standing out of the wall at u, its middle at zc (the façade's frame)."""
    tex = ctx.tex
    p = Piece()
    bg, fg, ac = place.colours
    if kind == "cross":                                    # the green cross of the pharmacies, lit
        g = tex.lit_col((0, 175, 80))
        P, y0 = 0.62, 0.2
        a = P / 3
        p.box((u - 0.05, y0 + a, zc - P / 2), (u + 0.05, y0 + 2 * a, zc + P / 2), g)
        p.box((u - 0.05, y0, zc - a / 2), (u + 0.05, y0 + a, zc + a / 2), g)
        p.box((u - 0.05, y0 + 2 * a, zc - a / 2), (u + 0.05, y0 + P, zc + a / 2), g)
        p.bar((u, 0.0, zc + P / 2 + 0.05), (u, y0 + 2 * a, zc + P / 2 + 0.05), 0.04, tex.col(DARK_METAL))
        return p
    if kind == "blade":
        w, h = 0.5, 0.85
        img = Sketch(64, 108, bg)
        icon(img, place.logo or "cup", (8, 6, 56, 54), ac, bg)
        img.text(STYLES[place.kind][3] if not place.brand else place.title, (4, 62, 60, 98), "sans", fg)
    else:
        w = h = 0.62
        img = Sketch(96, 96, bg)
        if place.logo == "fork" or kind == "post":
            fork_logo(img, (8, 6, 88, 66), ac, (255, 255, 255))
            img.text("LA PASTA" if kind == "post" else place.title, (6, 70, 90, 90), "sans", fg)
        elif place.logo:
            icon(img, place.logo, (14, 8, 82, 64), ac, bg)
            img.text(place.title, (6, 70, 90, 90), place.font, fg)
        else:
            img.text(place.title, (6, 20, 90, 76), place.font, fg)
    r = tex.sign(img.done(), key=("proj", kind, place.brand or place.id))
    y0 = 0.18
    p.box((u - 0.04, y0, zc - h / 2), (u + 0.04, y0 + w, zc + h / 2), tex.sign_col(bg, True), faces={"+x": r, "-x": r})
    p.bar((u, 0.0, zc + h / 2 + 0.05), (u, y0 + w, zc + h / 2 + 0.05), 0.035, tex.col(DARK_METAL))
    return p


def hotel_front(place, f, ctx, uc, zg, z_top):
    """(canopy, flags) of a hotel's entrance; the canopy's height."""
    tex = ctx.tex
    zc = min(zg + 2.75, z_top - 0.3)
    p, soft = Piece(), Piece()
    W = min(2.6, f.length - 0.6)
    Dp = clear_depth(ctx, f, [uc - W / 2 + 0.1, uc, uc + W / 2 - 0.1], 1.5, start=0.4)
    if Dp >= 0.8:
        band = tex.prop(band_image(place, 320, 40, 1), key=("band1", place.id))
        bg = place.colours[0]
        p.box((uc - W / 2, 0.0, zc), (uc + W / 2, Dp, zc + 0.22), tex.col(bg), faces={"+y": band, "-z": tex.col(WHITE)})
        for x in (uc - W / 2 + 0.1, uc + W / 2 - 0.1):
            p.bar((x, 0.0, zc + 1.0), (x, Dp - 0.1, zc + 0.22), 0.02, tex.col(METAL))
    flags = [flag_rect(tex, "swiss"), flag_rect(tex, "ticino"), flag_rect(tex, "own", place)]
    for i, x in enumerate((uc - 1.7, uc + 1.7, uc + 2.5)):
        z0 = zc + 0.9
        if not (f.u0 + 0.3 < x < f.u1 - 0.3) or z0 + 1.2 > z_top:
            continue
        soft.bar((x, 0.05, z0), (x, 1.35, z0 + 0.9), 0.03, tex.col(WHITE))
        soft.quad((x, 0.45, z0 + 0.28 - 0.95), (x, 1.3, z0 + 0.87 - 0.95), (x, 1.3, z0 + 0.87), (x, 0.45, z0 + 0.28),
                  flags[i])
        ctx.out.count("flags")
    return p, soft, zc


def big_store(place, f, ctx, zg, rng):
    """The relief of a big store's façade (the façade's frame): the signage band of the brand's colour and the light
    box on it, entrance canopy and glazed doors, pilasters, a cornice along a level top. Returns (piece, the light
    box's span or None, the entrance u)."""
    tex, site = ctx.tex, ctx.site
    u0, u1 = f.u0, f.u1
    ztop = f.top(u0 + 0.3, u1 - 0.3)
    Hw = ztop - zg
    if Hw < 3.4:
        return None, None, None
    u_p = float(np.clip(place.p @ f.t, u0 + 3, u1 - 3))
    g = shop_group(f, u_p, near=25.0)
    ue = float(np.clip(0.5 * (g[0] + g[1]) if g else u_p, u0 + 4.0, u1 - 4.0))
    p = Piece()
    bg, fg, ac = place.colours
    band_col = ac if sum(bg) > 690 else bg
    F = f.poly()
    level = F is not None and np.nanmax(fc.top_profile(F, np.linspace(u0 + 0.3, u1 - 0.3, 20))) - ztop < 0.4
    zb1 = ztop - 0.25
    if level:
        p.box((u0 - 0.05, 0.0, ztop - 0.45), (u1 + 0.05, 0.3, ztop + 0.06), tex.col((222, 220, 214)))
        zb1 = ztop - 0.55
        ctx.out.count("cornices")
    hb = float(np.clip(0.22 * Hw, 0.7, 1.3))
    zb0 = zb1 - hb
    box_span = None
    if zb0 >= zg + 2.9 and not ctx.layout.taken.get(f.key):
        p.box((u0 + 0.5, 0.0, zb0), (u1 - 0.5, 0.12, zb1), tex.col(band_col))
        lmin, lmax = KINDS[place.kind][1]
        L = float(np.clip(0.4 * f.length, lmin, lmax))
        hs = min(hb + 0.35, 1.7)
        ua = float(np.clip(ue - L / 2, u0 + 0.6, u1 - 0.6 - L))
        rect, asp = sign_texture(place, ctx, L, hs, True, big=True)
        sign_board(p, tex, place, rect, asp, ua, ua + L, 0.12, 0.34, zb0 - (hs - hb) / 2, zb1 + (hs - hb) / 2, True)
        ctx.layout.take(f, u0, u1)                     # the band: the whole wall
        box_span = (ua, ua + L)
        ctx.out.count("light_boxes")
        ctx.out.count("signs")
    else:
        zb0 = ztop - 0.25
    # entrance: a canopy (on posts where it is deep), glazed sliding doors under it
    Wc = min(float(np.clip(0.3 * f.length, 6.0, 12.0)), f.length - 1.0)
    zc = float(min(zg + 3.2, zb0 - 0.25))
    us = np.linspace(ue - Wc / 2 + 0.2, ue + Wc / 2 - 0.2, 6)
    Dc = clear_depth(ctx, f, us, rng.uniform(*CANOPY_D), lift=0.2, start=0.8)
    if Dc >= 1.2 and zc - zg >= 2.6:
        band = tex.prop(band_image(place, 512, 48, max(1, int(Wc / 5))), key=("canopy", place.brand or place.id, int(Wc / 5)))
        p.box((ue - Wc / 2, 0.0, zc), (ue + Wc / 2, Dc, zc + 0.28), tex.col((200, 200, 198)))
        p.box((ue - Wc / 2 - 0.05, Dc - 0.06, zc - 0.12), (ue + Wc / 2 + 0.05, Dc + 0.04, zc + 0.5), tex.col(band_col),
              faces={"+y": band})
        if Dc >= 2.2:
            for x in (ue - Wc / 2 + 0.35, ue + Wc / 2 - 0.35):
                q = f.at(x, Dc - 0.35)
                if site.on_carriageway([q[0]], [q[1]])[0]:
                    continue
                zq = float(site.ground([q[0]], [q[1]])[0])
                p.box((x - 0.12, Dc - 0.47, zq - 0.1), (x + 0.12, Dc - 0.23, zc), tex.col((200, 200, 198)),
                      skip=("-z", "+z"))
        ctx.out.count("canopies")
    glass = tex.prop(pattern("glass_door", None), key="glass_door", glass=True)
    wd = min(4.4, Wc - 0.6)
    p.box((ue - wd / 2, 0.02, zg - 0.05), (ue + wd / 2, 0.09, zg + 2.6), tex.col((190, 192, 195)), faces={"+y": glass})
    ctx.out.count("glass_doors")
    # pilasters, not over the openings nor at the entrance
    zp = (zb0 if box_span is not None else ztop - (0.45 if level else 0.3)) - 0.02
    n_pil = 0
    for x in np.arange(u0 + 0.35, u1 - 0.3, PILASTER_PITCH):
        if abs(x - ue) < max(Wc, wd) / 2 + 0.6 or any(a - 0.35 < x < b + 0.35 for n, a, b, zb, zt in f.openings):
            continue
        p.box((x - 0.25, 0.0, zg - 0.15), (x + 0.25, 0.16, zp), tex.col((210, 208, 203)), skip=("-z",))
        n_pil += 1
    ctx.out.count("pilasters", n_pil)
    ctx.out.count("big_stores")
    return p, box_span, ue


def free_spot(ctx, f, us, ss, r):
    """The first free point (q, z, u, s) for a prop of radius r at the façade's u in us, s in ss m out of the wall."""
    for s in ss:
        for u in us:
            if not (f.u0 - 3.0 <= u <= f.u1 + 3.0):
                continue
            q = f.at(u, s)
            z = ctx.site.free(q, r)
            if z is not None:
                return q, z, u, s
    return None


def put(ctx, f, piece, q, z, r, cat="prop", what=None, ang=0.0):
    """A piece drawn in a frame of its own (x along the façade, y out of it) at q, turned by ang more."""
    ctx.out.add(cat, q, piece.placed(q[0], q[1], z, f.angle() + ang), what)
    if r:
        ctx.site.take(np.asarray(q, float), r)


def place_props(place, f, ctx, ua, ub, awning_d, rng, entrance=None):
    """The things outside the place, by its kind (KINDS[kind][5])."""
    what = KINDS[place.kind][5]
    if not what:
        return
    tex = ctx.tex
    uc = 0.5 * (ua + ub) if entrance is None else entrance
    s0 = f.eaves + 0.5
    ss = np.arange(s0, s0 + 6.0, 0.4)
    side_us = [ua - 0.6, ub + 0.6, ua - 1.2, ub + 1.2, ua - 1.8, ub + 1.8, uc]
    leaves = tex.leaf(leaf_image("foliage", np.random.default_rng(3)), key="foliage")

    def one(make, us, ssub, r, what_, soft=None):
        res = free_spot(ctx, f, us, ssub, r)
        if res is None:
            return None
        pc = make()
        if isinstance(pc, tuple):
            put(ctx, f, pc[0], res[0], res[1], r, what=what_)
            put(ctx, f, pc[1], res[0], res[1], 0, cat="soft")
        else:
            put(ctx, f, pc, res[0], res[1], r, what=what_)
        return res

    def pots(n=2, colour=TERRACOTTA):
        for u in side_us[:n]:
            one(lambda: m_pot(tex, leaves, colour), [u, u - 0.5 * np.sign(uc - u)], ss[:4], 0.32, "plant_pots")

    def board(key, us=None):
        one(lambda: m_aboard(tex, board_rect(tex, key)), us or side_us, ss[:6], 0.38, "boards")

    def tables(n, square, cloth=None, umbrella=None, chairs=2):
        """n tables in rows along the façade, nearest the door first; an umbrella over those beyond the awning."""
        placed, used = 0, []
        cands = sorted(np.arange(ua - 2.0, ub + 2.01, 0.6), key=lambda u: abs(u - uc))
        for s in ss:
            for u in cands:
                if placed >= n:
                    break
                if any(abs(u - v) < 2.3 and abs(s - t) < 2.2 for v, t in used):
                    continue
                q = f.at(u, s)
                umb = umbrella is not None and s > awning_d + 1.0
                R = 1.3 if umb else 1.0
                z = ctx.site.free(q, R)
                if z is None:
                    continue
                t = m_table(tex, cloth) if square else m_round_table(tex, WHITE if rng.uniform() < 0.5 else (60, 60, 64))
                put(ctx, f, t, q, z, 0, what="tables")
                col = [WHITE, (60, 60, 64), WOOD, GREEN_PAINT][int(_unit(place.id, "chair") * 4)]
                for k in range(chairs):
                    a = math.pi * k
                    off = math.cos(a) * (0.62 if square else 0.55)
                    cq = q + f.t * off
                    zc = float(ctx.site.ground([cq[0]], [cq[1]])[0])
                    put(ctx, f, m_chair(tex, col, wood=col == WOOD), cq, zc, 0, what="chairs",
                        ang=a + math.pi + rng.uniform(-0.2, 0.2))
                if umb:
                    hard, soft = m_umbrella(tex, *umbrella)
                    put(ctx, f, hard, q, z, 0, what="umbrellas")
                    put(ctx, f, soft, q, z, 0, cat="soft")
                ctx.site.take(q, R)
                used.append((u, s))
                placed += 1
            if placed >= n:
                break
        return placed

    def umbrella_of(brands):
        name, c1, c2, letters = brands[int(_unit(place.id, "umb") * len(brands))]
        img = Sketch(256, 40, c1)
        img.text(name, (10, 5, 246, 35), "sans", letters)
        return c1, c2, tex.prop(img.done(), key=("umb", name))

    if what == "terrace":
        cloth = ["cloth_red", "cloth_white", "cloth_green", "cloth_blue"][int(_unit(place.id, "cloth") * 4)]
        tables(int(rng.integers(2, 5)), True, cloth, umbrella_of(BEER) if rng.uniform() < 0.7 else None)
        board("menu")
        pots(2)
    elif what == "cafe":
        tables(int(rng.integers(2, 4)), False, umbrella=umbrella_of(COFFEE))
        if rng.uniform() < 0.5:
            board("menu")
    elif what == "gelato":
        tables(2, False, umbrella=umbrella_of(GELATO))
        board("gelato")
    elif what == "fast_food":
        tables(2, False)
        one(lambda: m_bin(tex, (200, 40, 30)), side_us, ss[:5], 0.3, "bins")
    elif what == "market":
        far = [uc + 6.0, uc - 6.0, uc + 9.0, uc - 9.0, uc + 12.0, uc - 12.0]
        res = one(lambda: m_shelter(tex, place), far, ss, 2.0, "trolley_shelters")
        if res:
            tr = m_trolley(tex, tex.leaf(pattern("grid", None), key="grid"))
            for k in range(int(rng.integers(4, 8))):
                q = res[0] + f.t * (1.3 - 0.3 * k) + f.e * 0.75
                put(ctx, f, tr, q, res[1], 0, what="trolleys")
        near = [uc - 4.0, uc + 4.0, uc - 7.0, uc + 7.0, uc - 10.0, uc + 10.0]
        one(lambda: m_box_print(tex, (1.2, 0.6, 1.5), (60, 60, 64), tex.prop(pattern("gas", None), key="gas")), near, ss,
            0.75, "gas_cages")
        one(lambda: m_box_print(tex, (1.1, 0.65, 0.85), WHITE, ice_rect(tex)), near, ss, 0.65, "ice_chests")
        one(lambda: m_crates(tex, rng, 6), near, ss, 0.65, "crate_stacks")
        one(lambda: m_bin(tex), near, ss, 0.3, "bins")
    elif what == "grocer":
        one(lambda: m_fruit_stand(tex, rng), side_us, ss[:5], 0.95, "fruit_stands")
        one(lambda: m_crates(tex, rng, int(rng.integers(3, 6))), side_us, ss[:5], 0.65, "crate_stacks")
        if place.kind == "convenience":
            one(lambda: m_box_print(tex, (1.1, 0.65, 0.85), WHITE, ice_rect(tex)), side_us, ss[:6], 0.65, "ice_chests")
        board("grocer")
    elif what == "bakery":
        one(lambda: m_bench(tex), side_us, ss[:4], 0.8, "benches")
        board("bakery")
    elif what == "florist":
        roses = [tex.leaf(leaf_image(k, np.random.default_rng(i)), key=k) for i, k in enumerate(
            ("flowers_red", "flowers_yellow", "flowers_pink", "flowers_white", "flowers_purple"))]
        one(lambda: m_buckets(tex, rng, roses), side_us, ss[:5], 0.8, "flower_stands")
        pots(2, (200, 200, 195))
    elif what == "kiosk":
        one(lambda: m_box_print(tex, (0.8, 0.35, 1.3), (30, 60, 130), tex.prop(pattern("papers", None), key="papers")),
            side_us, ss[:4], 0.45, "news_stands")
        board("kiosk")
    elif what == "hair":
        board("hair")
    elif what == "clothes":
        one(lambda: m_rack(tex, rng), side_us, ss[:4], 0.8, "clothes_racks")
        board("clothes")
    elif what == "wine":
        for _ in range(2):
            one(lambda: m_barrel(tex), side_us, ss[:4], 0.4, "barrels")
        board("wine")
    elif what == "bikes":
        wheel = tex.leaf(leaf_image("wheel", None), key="wheel")
        one(lambda: m_bikes(tex, rng, wheel, int(rng.integers(2, 5))), side_us, ss[:4], 1.4, "bike_racks")
    elif what == "dealer":
        fl = flag_rect(tex, "own", place)
        n = 0
        for u in np.arange(f.u0 + 1.0, f.u1, 4.0):
            if n < 5 and one(lambda: m_flag_pole(tex, fl), [u], np.arange(3.0, 12.0, 1.0), 0.35, "feather_flags"):
                n += 1
        for key in ("price", "price2"):
            board(key, [uc - 3, uc + 3, uc - 6, uc + 6])
    elif what == "hotel":
        pots(2, (90, 90, 95))
    elif what == "post":
        one(lambda: m_post_box(tex, tex.prop(post_box_image(), key="post_box")), side_us, ss[:4], 0.3, "post_boxes")
    elif what == "board":
        board({"pharmacy": "pharmacy", "butcher": "butcher"}.get(place.kind, "shop"))


def place_front(place, f, ctx):
    """Everything of one place on and in front of its façade."""
    rng = place.rng()
    tex, out = ctx.tex, ctx.out
    H, (lmin, lmax), lit, aw_share, proj, props = KINDS[place.kind]
    o = f.e * f.d
    pieces = []
    entrance = None
    span = None
    awning_d = 0.0
    if place.big and f.length >= BIG_L:
        zg = ctx.ground(f, f.u0 + 1, f.u1 - 1)
        p, box_span, entrance = big_store(place, f, ctx, zg, rng)
        if p is not None:
            pieces.append(("front", p))
            span = box_span or (entrance - 2.5, entrance + 2.5)
    if span is None:
        span = sign_span(place, f, ctx)
        if span is None:
            return "no room on the façade"
        ua, ub = span
        zg = ctx.ground(f, ua, ub)
        hz = sign_heights(f, ua, ub, zg, H)
        p = Piece()
        z_att = zg + 2.7
        z_top = f.top(ua, ub)
        if hz:
            z0, z1 = hz
            rect, asp = sign_texture(place, ctx, ub - ua, z1 - z0, lit)
            sign_board(p, tex, place, rect, asp, ua, ub, SIGN_OUT, SIGN_OUT + (0.18 if lit else 0.07), z0, z1, lit)
            ctx.layout.take(f, ua, ub)
            out.count("signs")
            if lit:
                out.count("light_boxes")
            z_att = z0 - 0.04
        elif proj is None:
            proj = "panel"                           # no room for a board: a sign standing out of the wall
        pieces.append(("front", p))
        if place.kind == "hotel":
            c, soft, zc = hotel_front(place, f, ctx, 0.5 * (ua + ub), zg, z_top)
            pieces += [("front", c), ("awning", soft)]
        elif _unit(place.id, "awning") < aw_share and z_att - zg > AWNING_CLEAR + 0.3:
            g = shop_group(f, 0.5 * (ua + ub), near=0.5)
            a0, a1 = (max(g[0], ua - 0.5), min(g[1], ub + 0.5)) if g else (ua, ub)
            aw, awning_d = awning(place, f, ctx, a0, a1, z_att, zg, rng)
            if aw is not None:
                pieces.append(("awning", aw))
                out.count("awnings")
        if proj in ("cross", "blade", "post", "bank", "panel"):
            zc = max(zg + 3.0, (hz[1] + 0.5) if hz else zg + 3.0)
            for u in ((ub + 0.45, ua - 0.45) if proj != "panel" else (0.5 * (ua + ub) + 0.45 * (ub - ua) + 0.45,)):
                if f.u0 + 0.2 < u < f.u1 - 0.2 and zc + 0.5 < z_top:
                    pieces.append(("awning", projecting(place, ctx, proj, u, zc)))
                    out.count("projecting_signs")
                    break
        if props == "hair":
            u = ua - 0.35 if ua - 0.35 > f.u0 + 0.15 else ub + 0.35
            pole = Piece()
            pole.prism((u, 0.2), 0.08, 0.08, zg + 2.0, zg + 2.65, 8, tex.prop(pattern("barber", None), key="barber"),
                       wrap=True)
            pole.prism((u, 0.2), 0.1, 0.1, zg + 2.65, zg + 2.72, 8, tex.col(METAL), top=tex.col(METAL))
            pole.prism((u, 0.2), 0.1, 0.1, zg + 1.93, zg + 2.0, 8, tex.col(METAL), bottom=tex.col(METAL))
            pole.bar((u, 0.0, zg + 2.3), (u, 0.12, zg + 2.3), 0.04, tex.col(METAL))
            pieces.append(("front", pole))
            out.count("barber_poles")
    mid = f.at(0.5 * (span[0] + span[1]))
    place.where = [round(float(v), 2) for v in (mid[0], mid[1], zg, f.e[0], f.e[1])]
    for cat, p in pieces:
        if p.parts:
            out.add(cat, mid, p.placed(o[0], o[1], 0.0, f.angle()))
    place_props(place, f, ctx, span[0], span[1], awning_d, rng, entrance)
    return None


class AreaFiles:
    """A LevelFiles seen through boxes (x0, y0, x1, y1): the objects of the items files and the forest items farther
    than MARGIN m from them left out (runs on a part of the map)."""
    MARGIN = 700.0

    def __init__(self, zi, boxes):
        self.zi, self.boxes = zi, np.asarray(boxes, float)
        self.NameToInfo = zi.NameToInfo

    def namelist(self):
        return self.zi.namelist()

    def infolist(self):
        return self.zi.infolist()

    def _near(self, p, m):
        x, y = float(p[0]), float(p[1])
        b = self.boxes
        return bool(np.any((x > b[:, 0] - m) & (x < b[:, 2] + m) & (y > b[:, 1] - m) & (y < b[:, 3] + m)))

    def read(self, name):
        data = self.zi.read(name)
        if name.endswith("items.level.json"):
            keep = []
            for l in data.decode("utf-8").splitlines():
                if not l.strip():
                    continue
                o = json.loads(l)
                pos = o.get("position")
                if o.get("class") != "TSStatic" or not pos or (abs(pos[0]) < 1 and abs(pos[1]) < 1) or \
                        self._near(pos, self.MARGIN):
                    keep.append(l)
            return ("\n".join(keep) + "\n").encode("utf-8")
        if name.endswith(".forest4.json"):
            keep = [l for l in data.decode("utf-8").splitlines() if l.strip() and self._near(json.loads(l)["pos"], 60.0)]
            return ("\n".join(keep) + "\n").encode("utf-8")
        return data


def shopfronts_step(root, report=None, area=None):
    """The step; area: boxes (x0, y0, x1, y1) to do only the places in them (a test run on a part of the map)."""
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    places, why = load_places(swiss_area())
    zr = zi
    if area:
        places = [p for p in places if any(b[0] <= p.p[0] <= b[2] and b[1] <= p.p[1] <= b[3] for b in area)]
        zr = AreaFiles(zi, area)
    site = street_life.Site(zr, lv)
    bld = Buildings(zr, lv, np.array([p.p for p in places]).reshape(-1, 2))
    roads = Roads(zr, lv)
    print("shop fronts: %d places, geometry read in %.0f s" % (len(places), time.time() - t0), flush=True)
    tex, out, layout = Tex(), Out(), Layout()
    ctx = Ctx(site, tex, out, layout)
    left, used, kinds = dict(why), [], {}
    # the big stores first: their façades and the ground in front are theirs
    for place in sorted(places, key=lambda p: (not p.big, p.id)):
        roofs = Roofs(site, place.p)
        f, w = choose_facade(place, bld, roofs, roads, site)
        if f is None:
            left[w] = left.get(w, 0) + 1
            continue
        w = place_front(place, f, ctx)
        if w:
            left[w] = left.get(w, 0) + 1
            continue
        used.append(place)
        kinds[place.kind] = kinds.get(place.kind, 0) + 1
    print("shop fronts: %d places used, left out %s; %s" % (len(used), left, out.counts), flush=True)

    tmp = tempfile.mkdtemp(prefix="magliaso_shops_")
    try:
        new_files, items, tris = {}, [], {}
        for (cat, tx, ty), piece in sorted(out.tiles.items()):
            size, draw, coll, night = CATS[cat]
            mb = bng.MeshBuilder()
            origin = np.array([(tx + 0.5) * size, (ty + 0.5) * size, 0.0])
            allv = []
            for m, (T, UV) in sorted(piece.parts.items()):
                T, UV = np.concatenate(T), np.concatenate(UV)
                V = T.reshape(-1, 3)
                mb.add(m, V, uvs=UV.reshape(-1, 2), normals=bng.flat_normals_soup(V))
                tris[cat] = tris.get(cat, 0) + len(T)
                allv.append(V)
            allv = np.concatenate(allv)
            origin[2] = float(np.floor(allv[:, 2].min()))
            detail = max(2, int(round(0.5 * float(np.linalg.norm(np.ptp(allv, axis=0))) * optimize_level.PIX_K / draw)))
            rel = f"{D}/shop_{cat}_{tx:+03d}_{ty:+03d}.dae"
            fn = os.path.join(tmp, os.path.basename(rel))
            mb.write_dae(fn, name=f"shop_{cat}", origin=origin, detail=detail)
            new_files[f"{lv}/{rel}"] = open(fn, "rb").read()
            ob = bng.tsstatic(f"/{lv}/{rel}", origin, collision=coll)
            if night:
                ob.update(NIGHT)
            ob["__parent"] = "shopfronts"
            items.append(ob)
        files, mats = tex.write(tmp)
        for n, path in files.items():
            new_files[f"{lv}/{D}/{n}"] = open(path, "rb").read()
        mf = os.path.join(tmp, "m.json")
        bng.write_materials(mf, mats)
        new_files[f"{lv}/{D}/shopfronts.materials.json"] = open(mf, "rb").read()
        grp = f"{lv}/main/MissionGroup/props/items.level.json"
        gitems = [g for g in pl.read_items(zi, grp) if g.get("name") != "shopfronts"]
        gitems.append({"name": "shopfronts", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "props"})
        enc = lambda objs: ("\n".join(json.dumps(x, separators=(",", ":")) for x in objs) + "\n").encode("utf-8")
        new_files[grp] = enc(gitems)
        new_files[f"{lv}/main/MissionGroup/props/shopfronts/items.level.json"] = enc(items)
        old = re.compile(re.escape(f"{lv}/{D}/"))
        with zi.writer() as zo:
            for inf in zi.infolist():
                if inf.filename in new_files or old.match(inf.filename):
                    continue
                zo.writestr(inf, zi.read(inf), compress_type=inf.compress_type)
            for name, data in sorted(new_files.items()):
                zo.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rep = {"places": len(places) + sum(v for k, v in why.items()), "swiss_with_front": len(places),
           "used": len(used), "by_kind": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
           "brands": sorted({p.brand for p in used if p.brand}), "left_out": left, "counts": out.counts,
           "triangles": tris, "triangles_total": sum(tris.values()), "tiles": len(out.tiles),
           "texture_pages": {"signs": len(tex.signs.pages), "props": len(tex.props.pages), "leaves": len(tex.leaves.pages)},
           "seconds": round(time.time() - t0),
           "where": {p.id: [p.kind, p.title] + p.where for p in used}}
    print("written in %.0f s: %d tiles, %d triangles %s" % (time.time() - t0, len(out.tiles), rep["triangles_total"], tris),
          flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1, default=str)
    return 0
