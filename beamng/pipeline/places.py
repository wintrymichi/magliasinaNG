"""Villages of the playable area from swissNAMES3D (swisstopo), for the spawn points (v2.0).

data/names/swissnames3d_<year>_2056.csv.zip (download_swisstopo.py): the named settlements
(OBJEKTART 'Ort') with at least MIN_PEOPLE inhabitants inside the area.
"""
import csv, glob, io, os, zipfile
import shapely
from config import DATA, lv95_to_local
import area

CATEGORIES = {"< 20": 0, "20 bis 49": 20, "50 bis 99": 50, "100 bis 999": 100, "1'000 bis 1'999": 1000,
              "2'000 bis 9'999": 2000, "10'000 bis 49'999": 10000, "50'000 bis 100'000": 50000, "> 100'000": 100000}
MIN_PEOPLE = 100


def villages(min_people=MIN_PEOPLE):
    """[(name, x, y, inhabitants class lower bound)] of the settlements in the area, largest first."""
    files = sorted(glob.glob(os.path.join(DATA, "names", "swissnames3d_*_2056.csv.zip")))
    if not files:
        return []
    A = area.polygon()
    out = []
    with zipfile.ZipFile(files[-1]) as z:
        f = io.TextIOWrapper(z.open("swissNAMES3D_PKT.csv"), encoding="utf-8-sig")
        r = csv.reader(f, delimiter=";")
        head = next(r)
        for row in r:
            d = dict(zip(head, row))
            if d["OBJEKTART"] != "Ort":
                continue
            people = CATEGORIES.get(d["EINWOHNERKATEGORIE"], 0)
            if people < min_people:
                continue
            x, y = lv95_to_local(float(d["E"]), float(d["N"]))
            if A.contains(shapely.Point(x, y)):
                out.append((d["NAME"], float(x), float(y), people))
    return sorted(out, key=lambda v: (-v[3], v[0]))
