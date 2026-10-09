"""The views of the check of railway.catenary_step (v2.8): the overhead line of the railway.
    python catenary_tour.py sites <zip before>                    -> verifica/v2.8/catenary/sites.json
    python catenary_tour.py render <level before> <level after>  -> verifica/v2.8/catenary/render3d/
    python catenary_tour.py views <zip> <tag>                    -> <user>/magliaso_unpaved_views.json
sites: the middle of the three longest metre-gauge track chains (railway.chains/join): a view from 7 m
beside the track (the side with no roof or wall top in the way) and 3 m up, 30 m back, looking 70 m along it.
render: before and after with render3d.py (masts and wires are pipeline meshes, drawn as they are), side by
side (compare_<site>.jpg).
views: the same views for the in-game tour of run_catenary_screenshots.ps1 (bng_lua/magliaso_unpaved.lua), with
the frame rate of every view.
    python catenary_tour.py electrified <zip v2.7> <zip first version> <zip now>  -> verifica/v2.8/catenary/electrified.png
electrified: the standard-gauge tracks from above (their sleepers, blue where OpenStreetMap tags them
electrified=contact_line, grey where not) with the masts of the first version and of the patch now.
"""
import json, os, sys, zipfile
import numpy as np
import railway as pc
import wall_fill_tour as wft
from config import BEAMNG_USER, LEVEL_NAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "verifica", "v2.8", "catenary")
SITES = os.path.join(OUT_DIR, "sites.json")
VIEWS = os.path.join(BEAMNG_USER, "magliaso_unpaved_views.json")
LV = f"levels/{LEVEL_NAME}"


def sites(zp):
    zi = zipfile.ZipFile(zp)
    C, Ls = pc.sleepers(zi, LV)
    P = C[Ls < 2.25]
    lines = pc.join([P[c] for c in pc.chains(P)])
    lines.sort(key=lambda l: -np.linalg.norm(np.diff(l[:, :2], axis=0), axis=1).sum())
    out = []
    for k, l in enumerate(lines[:3]):
        m = len(l) // 2
        t = l[min(m + 5, len(l) - 1), :2] - l[max(m - 5, 0), :2]
        t /= np.linalg.norm(t)
        n = np.array([t[1], -t[0]])
        c = l[m]
        tgt = np.r_[c[:2] + 70 * t, c[2] + 3.0]
        ob = wft.obstacles(zi, c)
        for side in (1.0, -1.0):                        # the side with no roof or wall top in the way
            cam = np.r_[c[:2] - 30 * t + side * 7 * n, c[2] + 3.0]
            if wft.clear(ob, cam, tgt):
                break
        out.append({"name": f"flp_{k + 1}", "cam": [round(float(v), 2) for v in cam],
                    "target": [round(float(v), 2) for v in tgt], "fov": 60.0})
        print(out[-1])
    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(out, open(SITES, "w"), indent=1)


def render(before, after):
    import render3d
    from PIL import Image, ImageDraw
    out = os.path.join(OUT_DIR, "render3d")
    os.makedirs(out, exist_ok=True)
    S = json.load(open(SITES))
    for tag, lv in (("before", before), ("after", after)):
        with render3d.Renderer(lv, W=1280, H=720, dae_normals=True) as R:
            for s in S:
                R.shot(render3d.Camera.look(s["cam"], s["target"], fov=s["fov"]), os.path.join(out, f"{tag}_{s['name']}.jpg"),
                       near=300.0, far=2500.0)
    for s in S:
        ims = [Image.open(os.path.join(out, f"{t}_{s['name']}.jpg")) for t in ("before", "after")]
        w, h = ims[0].size
        im = Image.new("RGB", (2 * w + 8, h), "white")
        for k, (a, label) in enumerate(zip(ims, ("v2.7", "railway.catenary_step"))):
            im.paste(a, (k * (w + 8), 0))
            ImageDraw.Draw(im).text((k * (w + 8) + 14, 12), label, fill="white", font_size=28, stroke_width=2,
                                    stroke_fill="black")
        f = os.path.join(out, f"compare_{s['name']}.jpg")
        im.resize((w, h // 2)).save(f, quality=86)
        print(f, flush=True)


def views(zp, tag):
    out = [{"kind": "view", "name": f"{tag}_{s['name']}", "cam": s["cam"], "target": s["target"], "fov": s["fov"],
            "wait": 9.0, "fps": True} for s in json.load(open(SITES))]
    os.makedirs(os.path.dirname(VIEWS), exist_ok=True)
    json.dump(out, open(VIEWS, "w"), indent=1)
    print(VIEWS, len(out), "views")


def masts(zp):
    """xy (k, 2) of the catenary masts of a patched zip: the mast tiles' vertices, one point a mast."""
    import optimize_level
    from scipy.cluster.hierarchy import fcluster, linkage
    zi = zipfile.ZipFile(zp)
    pts = []
    for o in [json.loads(l) for l in zi.read(f"{LV}/main/MissionGroup/railway/items.level.json").decode().splitlines() if l.strip()]:
        sn = o.get("shapeName", "").lstrip("/")
        if "catenary_masts" in sn and sn in zi.NameToInfo:
            V = optimize_level.parse(zi.read(sn).decode("utf-8"))[0] + np.asarray(o["position"])
            pts.append(V[V[:, 2] < np.percentile(V[:, 2], 30)][:, :2])     # the feet
    P = np.unique(np.round(np.concatenate(pts), 1), axis=0)
    out = []
    for cell in set(map(tuple, np.floor(P / 200).astype(int))):
        Q = P[(np.floor(P / 200).astype(int) == cell).all(1)]
        lab = fcluster(linkage(Q, "single"), 1.0, "distance") if len(Q) > 1 else np.ones(1, int)
        out += [Q[lab == k].mean(0) for k in np.unique(lab)]
    return np.array(out)


def electrified(z27, zfirst, znow):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C, Ls = pc.sleepers(zipfile.ZipFile(z27), LV)
    P = C[Ls >= 2.25]
    f = pc.osm_contact_line()
    fig, ax = plt.subplots(figsize=(9, 9))
    for l in pc.join([P[c] for c in pc.chains(P)]):
        on = f(l)[1] >= 0.5
        ax.plot(l[:, 0], l[:, 1], "-", color="tab:blue" if on else "0.6", lw=3 if on else 2)
    box = (P[:, 0].min() - 50, P[:, 0].max() + 50, P[:, 1].min() - 50, P[:, 1].max() + 50)
    for zp, mk, label in ((zfirst, "x", "masts, first version"), (znow, "o", "masts now")):
        M = masts(zp)
        M = M[(M[:, 0] > box[0]) & (M[:, 0] < box[1]) & (M[:, 1] > box[2]) & (M[:, 1] < box[3])]
        ax.plot(M[:, 0], M[:, 1], mk, ms=7, mfc="none", color="tab:red" if mk == "x" else "black", label=f"{label} ({len(M)})")
    ax.plot([], [], "-", color="tab:blue", lw=3, label="standard gauge, OSM electrified=contact_line")
    ax.plot([], [], "-", color="0.6", lw=2, label="standard gauge, OSM electrified=no")
    ax.set_aspect("equal")
    ax.set_xlim(box[:2])
    ax.set_ylim(box[2:])
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title("The standard-gauge tracks of the map and their catenary masts")
    f_ = os.path.join(OUT_DIR, "electrified.png")
    fig.savefig(f_, dpi=80)
    print(f_)


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"sites": sites, "render": render, "views": views, "electrified": electrified}[cmd](*args)
