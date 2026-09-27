"""Visual review of a built level (v2.0): screenshots of the whole map with render3d.py.

Sets (default: all):
  overview  the map from above, tile by tile (1 px/m), and one picture of the whole area
  bridges   every bridge of dati/ponti.json from the side (no trees) and from the approach
  roads     the driver's view every ROAD_EVERY m along all the roads
  paths     the driver's view every PATH_EVERY m along the paths
  villages  every village of the area from above at an angle
  corners   the four corners of the area
  flagged   the places listed by check_level.py (beamng/verifica/check_level.json, "places")
Every view goes to <WORK>/review/<set>/ with an index.json (place, class, name); contact sheets of
them and the overview go to beamng/verifica/mappa/.
    python review_map.py [set ...] [--level <folder>]
"""
import json, math, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import LEVEL_DIR, WORK
import area
import network
import network_surface
from render3d import Renderer, Camera

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "verifica", "mappa")
SHOTS = os.path.join(WORK, "review")
ROAD_EVERY = 700.0
PATH_EVERY = 2000.0
SETS = ("overview", "bridges", "roads", "paths", "villages", "corners", "flagged")


def font(size):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def contact_sheets(entries, name, cols=4, tw=480, th=270, per=16, title=""):
    """Sheets of `per` thumbnails with their captions: beamng/verifica/mappa/<name>_NN.jpg."""
    os.makedirs(OUT, exist_ok=True)
    f, fb = font(15), font(20)
    out = []
    for k in range(0, len(entries), per):
        chunk = entries[k:k + per]
        rows = int(math.ceil(len(chunk) / cols))
        img = Image.new("RGB", (cols * tw, 34 + rows * (th + 24)), "white")
        d = ImageDraw.Draw(img)
        d.text((8, 6), f"{title}  ({k + 1}-{k + len(chunk)} di {len(entries)})", fill="black", font=fb)
        for j, (path, cap) in enumerate(chunk):
            x, y = (j % cols) * tw, 34 + (j // cols) * (th + 24)
            try:
                im = Image.open(path).convert("RGB")
                im.thumbnail((tw - 4, th))
                img.paste(im, (x + 2, y))
            except OSError:
                d.rectangle([x + 2, y, x + tw - 2, y + th], outline="red")
            d.text((x + 4, y + th + 3), cap[:62], fill="black", font=f)
        p = os.path.join(OUT, f"{name}_{k // per + 1:02d}.jpg")
        img.save(p, quality=85)
        out.append(p)
    return out


def save_index(sub, rows):
    os.makedirs(os.path.join(SHOTS, sub), exist_ok=True)
    json.dump(rows, open(os.path.join(SHOTS, sub, "index.json"), "w"), indent=1, ensure_ascii=False)


class Net:
    def __init__(self):
        self.segs, st, _ = network.load()
        self.x, self.y, self.seg = st["x"], st["y"], st["seg"]
        self.z = network_surface.load()["z"]

    def heading(self, i, ahead=4):
        s = self.segs[self.seg[i]]
        a, n = s["first"], s["n"]
        j = min(i + ahead, a + n - 1)
        k = i if j > i else max(i - ahead, a)
        if j == k:
            j, k = min(i + 1, a + n - 1), max(i - 1, a)
        return math.atan2(self.y[j] - self.y[k], self.x[j] - self.x[k])


def overview(r, tile=1024.0, ppm=1.0):
    x0, y0, x1, y1 = area.bounds(150.0)
    x0, y0 = math.floor(x0 / tile) * tile, math.floor(y0 / tile) * tile
    nx, ny = int(math.ceil((x1 - x0) / tile)), int(math.ceil((y1 - y0) / tile))
    poly = area.polygon()
    import shapely
    sub = os.path.join(SHOTS, "overview")
    os.makedirs(sub, exist_ok=True)
    small = 4                                           # m per pixel of the overview
    big = Image.new("RGB", (int(nx * tile / small), int(ny * tile / small)), (200, 200, 200))
    rows = []
    for j in range(ny):
        for i in range(nx):
            tx, ty = x0 + i * tile, y0 + j * tile
            if not poly.buffer(300).intersects(shapely.box(tx, ty, tx + tile, ty + tile)):
                continue
            p = os.path.join(sub, f"tile_{i:02d}_{j:02d}.jpg")
            if not os.path.exists(p):
                t = time.time()
                r.shot(Camera.top(tx, ty, tx + tile, ty + tile, ppm), p)
                print(f"overview tile {i},{j} {time.time() - t:.0f} s", flush=True)
            im = Image.open(p).resize((int(tile / small), int(tile / small)), Image.LANCZOS)
            big.paste(im, (int(i * tile / small), int((ny - 1 - j) * tile / small)))
            rows.append({"file": os.path.basename(p), "x0": tx, "y0": ty, "x1": tx + tile, "y1": ty + tile})
    d = ImageDraw.Draw(big)
    B = [((x - x0) / small, (ny * tile - (y - y0)) / small) for x, y in np.array(area.boundary())]
    d.line(B + [B[0]], fill=(255, 40, 40), width=3)
    f = font(22)
    for j in range(ny):
        for i in range(nx):
            d.text((i * tile / small + 6, (ny - 1 - j) * tile / small + 4), f"{i},{j}", fill=(255, 255, 255), font=f)
    for i in range(nx + 1):
        d.line([(i * tile / small, 0), (i * tile / small, big.height)], fill=(255, 255, 255), width=1)
    for j in range(ny + 1):
        d.line([(0, j * tile / small), (big.width, j * tile / small)], fill=(255, 255, 255), width=1)
    os.makedirs(OUT, exist_ok=True)
    big.save(os.path.join(OUT, "panoramica.jpg"), quality=88)
    save_index("overview", rows)
    return rows


def samples(net, kind, every):
    """Stations every `every` m of the segments of one kind (not on bridges), in segment order."""
    out, acc = [], every * 0.5
    for s in net.segs:
        if s["kind"] != kind or s["bridge"]:
            continue
        a, n = s["first"], s["n"]
        for i in range(a, a + n):
            acc += 2.0
            if acc >= every and i > a + 1:
                acc = 0.0
                out.append(i)
    return out


def road_views(r, net, kind, every):
    sub = "roads" if kind == "road" else "paths"
    os.makedirs(os.path.join(SHOTS, sub), exist_ok=True)
    rows, entries = [], []
    for k, i in enumerate(samples(net, kind, every)):
        s = net.segs[net.seg[i]]
        p = os.path.join(SHOTS, sub, f"{k:04d}.jpg")
        if not os.path.exists(p):
            r.shot(Camera.driver(net.x[i], net.y[i], net.z[i], net.heading(i)), p, near=300, far=3000)
        cap = f"{k:04d} {s['class']} {s['name'][:22]} ({net.x[i]:.0f}, {net.y[i]:.0f})"
        rows.append({"file": os.path.basename(p), "i": int(i), "seg": int(net.seg[i]), "class": s["class"],
                     "name": s["name"], "x": float(net.x[i]), "y": float(net.y[i]), "z": float(net.z[i])})
        entries.append((p, cap))
        if k % 25 == 0:
            print(sub, k, flush=True)
    save_index(sub, rows)
    return contact_sheets(entries, sub, title="Strade: vista del guidatore" if kind == "road" else "Sentieri: vista a piedi/in moto")


def bridge_views(r, net):
    import bridges
    data = json.load(open(bridges.PONTI, encoding="utf-8"))["ponti"]
    sub = os.path.join(SHOTS, "bridges")
    os.makedirs(sub, exist_ok=True)
    rows, entries = [], []
    for k, b in enumerate(data):
        s = net.segs[b["seg"]]
        a, n = s["first"], s["n"]
        P = np.column_stack([net.x[a:a + n], net.y[a:a + n]])
        z = net.z[a:a + n]
        L = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        m = P[n // 2]
        t = P[-1] - P[0]
        t /= max(np.linalg.norm(t), 1e-9)
        az = math.degrees(math.atan2(-t[1], t[0]))          # compass azimuth of the left normal (-t_y, t_x)
        dist = max(35.0, 1.1 * L)
        p1 = os.path.join(sub, f"{k:03d}_side.jpg")
        p2 = os.path.join(sub, f"{k:03d}_drive.jpg")
        zc = float(z[n // 2])
        if not os.path.exists(p1):
            r.shot(Camera.orbit(m[0], m[1], zc - 1.5, dist, az, 14.0), p1, near=max(200.0, dist + 80), far=2500,
                   trees=False)
        if not os.path.exists(p2):
            t0 = P[1] - P[0]
            t0 /= max(np.linalg.norm(t0), 1e-9)
            back = P[0] - t0 * 30.0
            d, j = r_tree(net).query(back)
            zb = float(net.z[j]) if d < 4 else float(z[0])
            h = math.atan2(t0[1], t0[0])
            r.shot(Camera.driver(back[0], back[1], zb, h, pitch=-3.0), p2, near=300, far=3000)
        flags = ",".join(b.get("flags", []))
        cap = f"{k:03d} {s['class']} {L:.0f} m h{b.get('max_height_m', 0):.1f} {flags}"
        rows.append({"k": k, "tlm": b["tlm"], "x": float(m[0]), "y": float(m[1]), "length": L, "flags": b.get("flags", [])})
        entries += [(p1, cap + " lato"), (p2, cap + " arrivo")]
        if k % 10 == 0:
            print("bridges", k, flush=True)
    save_index("bridges", rows)
    return contact_sheets(entries, "ponti", cols=4, per=16, title="Ponti: di lato (senza alberi) e in arrivo")


_TREE = {}


def r_tree(net):
    if "t" not in _TREE:
        from scipy.spatial import cKDTree
        _TREE["t"] = cKDTree(np.column_stack([net.x, net.y]))
    return _TREE["t"]


def village_views(r, net):
    import places
    sub = os.path.join(SHOTS, "villages")
    os.makedirs(sub, exist_ok=True)
    rows, entries = [], []
    tree = r_tree(net)
    for k, (name, x, y, people) in enumerate(places.villages()):
        d, j = tree.query([x, y])
        z = float(net.z[j]) if d < 300 else float(r.level.heights(
            int((y - r.level.ty0) / r.level.sq), int((y - r.level.ty0) / r.level.sq) + 1,
            int((x - r.level.tx0) / r.level.sq), int((x - r.level.tx0) / r.level.sq) + 1)[0, 0])
        p = os.path.join(sub, f"{k:02d}.jpg")
        if not os.path.exists(p):
            r.shot(Camera.orbit(x, y, z, 380.0, 200.0, 32.0), p, near=450, far=3500)
        rows.append({"file": os.path.basename(p), "name": name, "x": x, "y": y, "people": people})
        entries.append((p, f"{name} ({people} ab.)"))
    save_index("villages", rows)
    return contact_sheets(entries, "paesi", cols=3, tw=640, th=360, per=9, title="Paesi dall'alto")


def corner_views(r):
    sub = os.path.join(SHOTS, "corners")
    os.makedirs(sub, exist_ok=True)
    B = np.array(area.boundary())
    c = B.mean(0)
    entries = []
    for k, (x, y) in enumerate(B):
        az = math.degrees(math.atan2(x - c[0], y - c[1]))      # from outside, looking inwards
        L = r.level
        zc = float(L.heights(int(np.clip((y - L.ty0) / L.sq, 0, L.n - 2)), int(np.clip((y - L.ty0) / L.sq, 0, L.n - 2)) + 1,
                             int(np.clip((x - L.tx0) / L.sq, 0, L.n - 2)), int(np.clip((x - L.tx0) / L.sq, 0, L.n - 2)) + 1)[0, 0])
        p = os.path.join(sub, f"P{k + 1}.jpg")
        if not os.path.exists(p):
            r.shot(Camera.orbit(x, y, zc, 700.0, az, 30.0), p, near=600, far=4000)
        entries.append((p, f"P{k + 1} ({x:.0f}, {y:.0f})"))
    return contact_sheets(entries, "angoli", cols=2, tw=800, th=450, per=4, title="Angoli dell'area")


FLAGGED_PER_KIND = 24


def flagged_views(r, net):
    f = os.path.join(os.path.dirname(HERE), "verifica", "check_level.json")
    places = json.load(open(f)).get("places", []) if os.path.exists(f) else []
    per = {}
    keep = []
    for pl in places:                                  # the worst of every kind (they come worst first)
        per[pl["what"]] = per.get(pl["what"], 0) + 1
        if per[pl["what"]] <= FLAGGED_PER_KIND:
            keep.append(pl)
    places = keep
    sub = os.path.join(SHOTS, "flagged")
    os.makedirs(sub, exist_ok=True)
    entries = []
    for k, pl in enumerate(places):
        p = os.path.join(sub, f"{k:03d}.jpg")
        if not os.path.exists(p):
            x, y, z = pl["x"], pl["y"], pl["z"]
            r.shot(Camera.orbit(x, y, z, 30.0, pl.get("az", 200.0), 35.0), p, near=150, far=1500,
                   trees=pl.get("trees", True))
        entries.append((p, f"{k:03d} {pl['what']} ({pl['x']:.0f}, {pl['y']:.0f})"))
    return contact_sheets(entries, "segnalati", title="Punti segnalati dai controlli")


def main(argv):
    lv = LEVEL_DIR
    if "--level" in argv:
        lv = argv[argv.index("--level") + 1]
    sets = [a for a in argv if a in SETS] or list(SETS)
    net = Net()
    t0 = time.time()
    with Renderer(lv) as r:
        for s in sets:
            t = time.time()
            if s == "overview":
                overview(r)
            elif s == "bridges":
                bridge_views(r, net)
            elif s == "roads":
                road_views(r, net, "road", ROAD_EVERY)
            elif s == "paths":
                road_views(r, net, "path", PATH_EVERY)
            elif s == "villages":
                village_views(r, net)
            elif s == "corners":
                corner_views(r)
            elif s == "flagged":
                flagged_views(r, net)
            print(f"[{s}: {time.time() - t:.0f} s]", flush=True)
    print(f"review done in {time.time() - t0:.0f} s -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
