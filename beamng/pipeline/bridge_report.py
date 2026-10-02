"""Review sheets of the bridges of dati/ponti.json (bridges.py), for the manual check.

For every bridge one sheet: the profile along the line and ENDS m beyond each end (DTM ground,
the road on the approaches, the deck and its slab, the height of the swissTLM3D line) and three
views of the built level (render3d.py): from the side without trees, and from both approaches at
the driver's eye. Contact sheets of the profiles give a first pass over all of them.
Manual corrections go into dati/ponti.json (see bridges.py) and the level is built again.
    python bridge_report.py [level folder] [--only 3,17,42]
Output: <WORK>/review/ponti/<rank>.jpg (sheets), beamng/verifica/ponti/README.md (table) and
beamng/verifica/ponti/profili_NN.jpg (profiles).
"""
import io, json, math, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree
from config import LEVEL_DIR, WORK
from geo import Grid
import bridges
import network
import network_surface

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verifica", "ponti")
SHEETS = os.path.join(WORK, "review", "ponti")
ENDS = 40.0


class Data:
    def __init__(self):
        self.ponti = json.load(open(bridges.PONTI, encoding="utf-8"))["ponti"]
        self.segs, self.st, _ = network.load()
        self.z = network_surface.load()["z"]
        self.dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
        self.tree = cKDTree(np.column_stack([self.st["x"], self.st["y"]]))

    def line(self, b):
        s = self.segs[b["seg"]]
        a, n = s["first"], s["n"]
        P = np.column_stack([self.st["x"][a:a + n], self.st["y"][a:a + n]])
        return s, a, n, P


def profile(b, D):
    """Distance along the bridge (and ENDS m beyond), DTM ground, road/deck height, TLM height, length."""
    s, a, n, P = D.line(b)
    z = D.z[a:a + n].copy()
    if "z0" in b or "z1" in b or b.get("profile") == "straight":
        z0, z1 = float(b.get("z0", z[0])), float(b.get("z1", z[-1]))
        ss = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        z = z0 + (z1 - z0) * ss / max(ss[-1], 1e-9)
    s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t0 = (P[0] - P[1]) / max(np.linalg.norm(P[0] - P[1]), 1e-9)
    t1 = (P[-1] - P[-2]) / max(np.linalg.norm(P[-1] - P[-2]), 1e-9)
    e = np.arange(0.5, ENDS + 0.1, 0.5)
    before = P[0][None] + t0[None] * e[::-1, None]
    after = P[-1][None] + t1[None] * e[:, None]
    Q = np.concatenate([before, P, after])
    sq = np.r_[-e[::-1], s_, s_[-1] + e]
    ground = D.dtm.sample(Q[:, 0], Q[:, 1])
    d, j = D.tree.query(np.concatenate([before, after]))
    road = np.where(d < 3.0, D.z[j], np.nan)
    tlm = np.r_[np.full(len(e), np.nan), D.st["z_tlm"][a:a + n], np.full(len(e), np.nan)]
    return sq, ground, np.r_[road[:len(e)], z, road[len(e):]], tlm, s_[-1]


def plot_profile(ax, b, D, small=False):
    sq, ground, road, tlm, L = profile(b, D)
    span = (sq >= 0) & (sq <= L)
    lo = np.nanmin(np.r_[ground, road]) - 2
    ax.fill_between(sq, ground, lo, color="#b9a77e", alpha=0.6, label="terreno (DTM)")
    ax.plot(sq[~span], road[~span], ".", ms=1.5 if small else 2.5, color="#444444", label="strada")
    ax.plot(sq[span], road[span], "-", lw=2 if small else 2.5, color="#1f4e8c", label="impalcato")
    ax.plot(sq[span], road[span] - bridges.SLAB, "-", lw=0.8, color="#1f4e8c")
    ax.plot(sq, tlm, "--", lw=1, color="#d62728", label="quota swissTLM3D")
    ax.axvline(0, color="#999", lw=0.6)
    ax.axvline(L, color="#999", lw=0.6)
    if not small:
        ax.set_xlabel("m lungo il ponte")
        ax.set_ylabel("quota m")
        ax.legend(fontsize=7, loc="lower right")
    return L


def title(i, b):
    fl = ",".join(b.get("flags", []))
    typ = b.get("type", b.get("auto_type", ""))
    skip = " SALTATO" if b.get("skip") else ""
    return (f"{i:03d} {b['class']} {b.get('name') or ''} {b['length_m']:.0f} m, h max {b['max_height_m']:.1f} m, "
            f"{typ}{skip} {fl}").strip()


def fig_image(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def views(r, b, D):
    """Side view (no trees) and the two approaches, as images."""
    from render3d import Camera
    s, a, n, P = D.line(b)
    z = D.z[a:a + n]
    L = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
    m, zc = P[n // 2], float(z[n // 2])
    t = P[-1] - P[0]
    t /= max(np.linalg.norm(t), 1e-9)
    # from the side where the ground is lower (the valley under the bridge)
    left = D.dtm.sample([m[0] - t[1] * 15], [m[1] + t[0] * 15])[0]
    right = D.dtm.sample([m[0] + t[1] * 15], [m[1] - t[0] * 15])[0]
    nrm = np.array([-t[1], t[0]]) if left <= right else np.array([t[1], -t[0]])
    az = math.degrees(math.atan2(nrm[0], nrm[1]))
    dist = max(30.0, 1.0 * L + 10)
    out = []
    tmp = os.path.join(SHEETS, "_v.jpg")
    r.shot(Camera.orbit(m[0], m[1], zc - 2.0, dist, az, 12.0, fov=60), tmp, near=max(180.0, dist + 60), far=2500,
           trees=False)
    out.append(Image.open(tmp).convert("RGB"))
    for end, (p0, p1, zi) in enumerate(((P[0], P[min(1, n - 1)], z[0]), (P[-1], P[max(n - 2, 0)], z[-1]))):
        cam = approach(D, s, end, p0, p1, zi)
        r.shot(Camera.driver(*cam, pitch=-3.0), tmp, near=280, far=2500)
        out.append(Image.open(tmp).convert("RGB"))
    return out


def approach(D, s, end, p0, p1, zi, back=25.0):
    """Driver's position (x, y, z, heading) BACK m before a bridge end on the road that leads to it
    (straight back from the end when the network stops there)."""
    node = s["nodes"][end]
    for q in D.segs:
        if q["id"] == s["id"] or node not in q["nodes"] or q["n"] < 2:
            continue
        a, n = q["first"], q["n"]
        idx = np.arange(a, a + n) if q["nodes"][0] == node else np.arange(a + n - 1, a - 1, -1)
        P = np.column_stack([D.st["x"][idx], D.st["y"][idx]])
        ss = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        k = int(min(np.searchsorted(ss, back), n - 1))
        if k == 0:
            continue
        x, y, zz = P[k][0], P[k][1], float(D.z[idx[k]])
        return x, y, zz, math.atan2(p0[1] - y, p0[0] - x)
    d = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
    b = p0 - d * back
    zg = float(D.dtm.sample([b[0]], [b[1]])[0])
    return b[0], b[1], max(float(zi), zg), math.atan2(d[1], d[0])


def sheet(i, b, D, r):
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
    plot_profile(ax, b, D)
    ax.set_title(title(i, b), fontsize=9)
    fig.tight_layout()
    prof = fig_image(fig).resize((800, 450))
    v = [im.resize((800, 450)) for im in views(r, b, D)]
    img = Image.new("RGB", (1600, 900), "white")
    for k, im in enumerate([prof] + v):
        img.paste(im, ((k % 2) * 800, (k // 2) * 450))
    d = ImageDraw.Draw(img)
    for k, lab in ((1, "di lato, senza alberi"), (2, "arrivo dal primo capo"), (3, "arrivo dall'altro capo")):
        d.rectangle([(k % 2) * 800, (k // 2) * 450, (k % 2) * 800 + 190, (k // 2) * 450 + 18], fill="white")
        d.text(((k % 2) * 800 + 4, (k // 2) * 450 + 3), lab, fill="black")
    out = os.path.join(SHEETS, f"{i:03d}.jpg")
    img.save(out, quality=85)
    return out


def contact_sheets(D, cols=5, rows=6):
    """Profiles of all the bridges, cols x rows per image: beamng/verifica/ponti/profili_NN.jpg."""
    os.makedirs(OUT, exist_ok=True)
    out = []
    per = cols * rows
    for k in range(0, len(D.ponti), per):
        fig, axes = plt.subplots(rows, cols, figsize=(3.3 * cols, 2.3 * rows), dpi=90)
        for ax in np.ravel(axes):
            ax.axis("off")
        for ax, (i, b) in zip(np.ravel(axes), list(enumerate(D.ponti))[k:k + per]):
            ax.axis("on")
            plot_profile(ax, b, D, small=True)
            ax.set_title(title(i, b)[:58], fontsize=6.5)
            ax.tick_params(labelsize=6)
        fig.tight_layout()
        p = os.path.join(OUT, f"profili_{k // per + 1:02d}.jpg")
        fig.savefig(p)
        plt.close(fig)
        out.append(p)
    return out


def main(lv=None, only=None):
    from render3d import Renderer
    lv = lv or LEVEL_DIR
    D = Data()
    os.makedirs(SHEETS, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    contact_sheets(D)
    rows = []
    with Renderer(lv) as r:
        for i, b in enumerate(D.ponti):
            if only is None or i in only:
                sheet(i, b, D, r)
            rows.append(f"| {i:03d} | {b['class']} | {b.get('name') or '—'} | {b['x']:.0f}, {b['y']:.0f} | "
                        f"{b['length_m']:.0f} | {b['max_height_m']:.1f} | {b.get('type', b.get('auto_type', ''))} | "
                        f"{','.join(b.get('flags', []))} | {b.get('note', '')} |")
            if i % 10 == 0:
                print("bridge sheets", i, flush=True)
    md = ["# Bridges of the v2.0 network", "",
          "One entry per bridge in `beamng/dati/ponti.json`. The sheets (profile and three views of the level) are "
          "regenerated with `python bridge_report.py`; the profiles of all the bridges are in `profili_NN.jpg`. "
          "The manual corrections (`z0`, `z1`, `profile`, `type`, `skip`, `note`) are in `ponti.json`.", "",
          "| # | Class | Name | x, y (m) | Length m | Max height m | Type | Flags | Note |",
          "|---|---|---|---|---|---|---|---|---|"] + rows
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(len(rows), "bridges ->", OUT, SHEETS)


if __name__ == "__main__":
    a = sys.argv[1:]
    only = None
    if "--only" in a:
        only = {int(v) for v in a[a.index("--only") + 1].split(",")}
        del a[a.index("--only"):a.index("--only") + 2]
    main(a[0] if a else None, only)
