"""Street View panoramas of the whole area for the review (v2.2), downloaded into WORK/sv/pano.

From the coverage (sv_coverage.py) a panorama every SPACING m is kept, the most recent capture first
(2025, 2022, then the older ones), so every covered street is seen about every SPACING m. The
images are a visual reference only: the review compares them with the map (sv_review.py) and
measures the plaster tone of the facades seen from the street (sv_facades.py); they never enter
the level or the repository (.gitignore: the WORK folder is outside it).
    python sv_fetch.py [spacing m] [zoom]        (defaults 20 m, zoom 2 = 2048 x 1024)
Needs the `streetlevel` package.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from scipy.spatial import cKDTree
from config import WORK

COVER = os.path.join(WORK, "sv", "coverage.json")
PANO = os.path.join(WORK, "sv", "pano")
SELECTED = os.path.join(WORK, "sv", "selected.json")


def select(spacing=20.0):
    """Panoramas at least `spacing` m apart, most recent first."""
    P = json.load(open(COVER))["panoramas"]
    P.sort(key=lambda p: (p.get("date") or "0000"), reverse=True)
    xy = np.array([[p["x"], p["y"]] for p in P])
    tree = cKDTree(xy)
    taken = np.zeros(len(P), bool)
    blocked = np.zeros(len(P), bool)
    for i in range(len(P)):
        if blocked[i]:
            continue
        taken[i] = True
        blocked[tree.query_ball_point(xy[i], spacing)] = True
    return [p for p, t in zip(P, taken) if t]


def fetch(p, zoom):
    from streetlevel import streetview
    f = os.path.join(PANO, f"{p['id']}.jpg")
    if os.path.exists(f):
        return p["id"], "skip"
    for attempt in range(4):
        try:
            pano = streetview.find_panorama_by_id(p["id"])
            if pano is None:
                return p["id"], "gone"
            img = streetview.get_panorama(pano, zoom=zoom)
            img.convert("RGB").save(f + ".part.jpg", quality=86)
            os.replace(f + ".part.jpg", f)
            return p["id"], "ok"
        except Exception as e:
            err = e
            time.sleep(2 * (attempt + 1))
    return p["id"], f"failed {err}"


def main(spacing=20.0, zoom=2):
    os.makedirs(PANO, exist_ok=True)
    sel = select(spacing)
    json.dump(sel, open(SELECTED, "w"))
    print(len(sel), "panoramas selected every", spacing, "m", flush=True)
    stats = {}
    with ThreadPoolExecutor(8) as ex:
        for k, (pid, st) in enumerate(ex.map(lambda p: fetch(p, zoom), sel)):
            stats[st.split()[0]] = stats.get(st.split()[0], 0) + 1
            if k % 250 == 0:
                print("  %d/%d %s" % (k + 1, len(sel), stats), flush=True)
    print("done", stats)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(float(a[0]) if a else 20.0, int(a[1]) if len(a) > 1 else 2)
