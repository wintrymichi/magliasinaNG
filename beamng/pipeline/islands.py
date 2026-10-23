"""Traffic islands raised on their kerbs, with the keep-right sign on their noses (v3.0), in the built level.

The islands of the cadastral survey (spartitraffico: the splitter islands of the roundabouts and junctions, the
refuges of the crossings) were meshed like the road, at the height of the asphalt: in the game a pale patch in
the carriageway that a car drove over without noticing (the user's screenshots 21, 31, 32), and no sign told
which side to pass. Here, on the built level:
- every island face of the road meshes (material mp_island) goes, and the island is built again KERB_H m over
  the asphalt: its top in Italy's cobbles (granite setts, as most islands of the area are paved), a kerb of
  Italy's concrete kerb stone all round it, down to KERB_DOWN m under the road; with collision (a car hits the kerb);
- on the nose of every island at least NOSE_MIN m long that an approaching driver faces (the carriageway goes on
  beyond the end of the island, along its long axis), the signal 2.33 (pass the obstacle on the right, signs_ch.py)
  on a grey pole, facing that traffic; the pole's foot in the black and yellow sleeve of the Swiss island posts
  (BOLLARD_H m, BANDS bands, black at the bottom and the top), as the street photos of the area show them (v3.1:
  up to then a separate short white beacon with a yellow reflector stood beside the pole, which no island here has).
Meshes in MissionGroup/roads/islands, one shape per TILE m tile; the rest of the level is copied as it is.

A finishing step of build_level.py (FINISH), after the road paint and wear (which keep off the islands' faces) and
before the steps that place objects (they see the islands as raised ground); alone: python build_level.py --finish islands
"""
import json, math, os, re, tempfile, time, zipfile
import numpy as np
import shapely
import bng
import optimize_level
import signs_ch
from config import LEVEL_NAME
from markings_net import read_items

TILE = 512.0
KERB_H = 0.12            # m, the island over the asphalt
KERB_DOWN = 0.10         # m, the kerb's face goes this far under the asphalt
KERB_W = 0.15            # m, the kerb stone on the top, round the edge
NOSE_MIN = 3.0           # m: shorter islands get no sign
APPROACH = 6.0           # m beyond a nose: carriageway there, traffic comes this way
SIGN_D = 0.6             # m, the disk of 2.33
SIGN_C = 1.45            # m, its middle over the island
NOSE_IN = 0.6            # m from the nose to the pole
ISLAND_MAT = "mp_island"
BOLLARD_W = 0.14         # m, the sleeve round the pole's foot
BOLLARD_H = 1.05         # m over the island
BANDS = 7                # black, yellow, ..., black
BOLLARD_TEX = "t_island_bollard_b.color.png"
SHAPE = re.compile(r"art/shapes/roads/islands_[-+]\d+_[-+]\d+\.dae$")
L = f"/levels/{LEVEL_NAME}"
TEX_DIR = f"levels/{LEVEL_NAME}/art/shapes/roads"


def materials():
    import italy_mats as it
    return [it.material("mp_island_top", "italy_cobblestone", ground_type="COBBLESTONE"),
            it.material("mp_island_kerb", "italy_curb_concrete", ground_type="CONCRETE"),
            bng.material("mp_island_pole", base_color=[0.62, 0.63, 0.64, 1], roughness=0.45, metallic=0.6),
            bng.material("mp_island_bollard", f"{L}/art/shapes/roads/{BOLLARD_TEX}", roughness=0.45, ground_type="PLASTIC"),
            bng.material("mp_island_233", f"{L}/art/shapes/roads/t_island_233_b.color.png", roughness=0.35,
                         alpha_test=100, ground_type="METAL",
                         detail={"opacityMap": f"{L}/art/shapes/roads/t_island_233_o.data.png"}),
            bng.material("mp_island_233_back", base_color=[150 / 255, 152 / 255, 154 / 255, 1], roughness=0.5,
                         metallic=0.5, alpha_test=100, ground_type="METAL",
                         detail={"opacityMap": f"{L}/art/shapes/roads/t_island_233_o.data.png"})]


def box(c, w, d, z0, z1, ax):
    """Triangles of a box w (along ax) x d about c from z0 to z1, outward."""
    ax = np.asarray(ax, float) / max(np.hypot(*ax), 1e-9)
    n = np.array([-ax[1], ax[0]])
    q = [c + ax * w / 2 + n * d / 2, c - ax * w / 2 + n * d / 2, c - ax * w / 2 - n * d / 2, c + ax * w / 2 - n * d / 2]
    out = []
    for a in range(4):
        p0, p1 = q[a], q[(a + 1) % 4]
        out += [np.r_[p0, z1], np.r_[p0, z0], np.r_[p1, z0], np.r_[p0, z1], np.r_[p1, z0], np.r_[p1, z1]]
    out += [np.r_[q[0], z1], np.r_[q[1], z1], np.r_[q[2], z1], np.r_[q[0], z1], np.r_[q[2], z1], np.r_[q[3], z1]]
    return np.array(out).reshape(-1, 3, 3)


def bollard(p, d, zt):
    """(triangles, uvs) of the black and yellow sleeve round a pole at p (its faces along d) from the island's top zt:
    u round the sleeve, v up it (one texture height = the sleeve)."""
    T = box(p, BOLLARD_W, BOLLARD_W, zt, zt + BOLLARD_H, d)
    V = T.reshape(-1, 3)
    ax = np.asarray(d, float) / max(np.hypot(*d), 1e-9)
    ang = np.arctan2(V[:, 1] - p[1], V[:, 0] - p[0])
    u = (ang - math.atan2(ax[1], ax[0])) / (2 * math.pi) % 1.0
    v = (V[:, 2] - zt) / BOLLARD_H
    return T, np.column_stack([u, v])


def bollard_png():
    """The sleeve's texture: BANDS bands up a 1 x 8 strip, black at the bottom and the top."""
    from PIL import Image
    import io
    h = 64 * BANDS
    img = Image.new("RGB", (16, h))
    for k in range(BANDS):
        col = (18, 18, 18) if k % 2 == 0 else (238, 190, 22)
        img.paste(col, (0, h - (k + 1) * 64, 16, h - k * 64))
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def disk(c, nrm, zc, r, n=20):
    """Front (facing nrm) and back fans of a disk, with texture coordinates for the front."""
    rt = np.array([-nrm[1], nrm[0]])
    a = np.linspace(0, 2 * np.pi, n + 1)
    P = [np.r_[c + rt * math.cos(t) * r, zc + math.sin(t) * r] for t in a]
    U = [(0.5 + 0.5 * math.cos(t), 0.5 + 0.5 * math.sin(t)) for t in a]
    C, Uc = np.r_[c, zc], (0.5, 0.5)
    front = np.array([[C, P[k], P[k + 1]] for k in range(n)])
    uv = np.array([[Uc, U[k], U[k + 1]] for k in range(n)])
    back = front[:, ::-1] - np.r_[nrm * 0.004, 0]
    return front, uv, back


def components(T):
    """Groups (lists of face indices) of the faces T (k, 3, 3) that share corners."""
    key = np.round(T.reshape(-1, 3)[:, :2] * 200).astype(np.int64)
    _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
    vid = vid.reshape(-1, 3)
    parent = np.arange(vid.max() + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for t in vid:
        ra = find(t[0])
        for v in t[1:]:
            rb = find(v)
            if ra != rb:
                parent[rb] = ra
    root = np.array([find(t[0]) for t in vid])
    return [np.flatnonzero(root == r) for r in np.unique(root)]


def islands_step(root, report=None):
    from road_mesh import TriSurface
    from markings_net import shape_tris, up_faces, CARRIAGE_MATS
    t0 = time.time()
    zi = bng.LevelFiles(root)
    lv = f"levels/{LEVEL_NAME}"
    items_name = f"{lv}/main/MissionGroup/roads/surfaces/items.level.json"
    items = read_items(zi, items_name)
    new_dae, tops = {}, []
    for o in items:
        sn = o.get("shapeName", "").lstrip("/")
        if o.get("class") != "TSStatic" or sn not in zi.NameToInfo:
            continue
        text = zi.read(sn).decode("utf-8")
        if f'material="{ISLAND_MAT}-mat"' not in text:
            continue
        V, N, UV, C, parts, node = optimize_level.parse(text)
        pos = np.asarray(o.get("position", [0, 0, 0]), np.float64)
        mb = bng.MeshBuilder()
        for mat, idx in parts:
            if mat == ISLAND_MAT:
                tops.append(up_faces((V[idx[:, 0]] + pos).reshape(-1, 3, 3)))
                continue
            col = C[idx[:, 3]] if C is not None and idx.shape[1] > 3 else None
            mb.add(mat, V[idx[:, 0]], uvs=UV[idx[:, 2]], normals=N[idx[:, 1]],
                   tris=np.arange(len(idx)).reshape(-1, 3), colors=col)
        if mb.empty():
            new_dae[sn] = None
            continue
        base, detail = re.match(r"(.*)_a(\d+)$", node).groups()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.dae")
            mb.write_dae(path, name=base, origin=(0, 0, 0), detail=int(detail))
            new_dae[sn] = open(path, "rb").read()
    rep = {"islands": 0, "island_m2": 0.0, "signs": 0}
    builders = {}
    if tops:
        T = np.concatenate(tops)
        surf = shape_tris(zi, lv, items)
        carr = TriSurface(np.concatenate([up_faces(t) for m, t in surf.items() if m in CARRIAGE_MATS]))
        del surf

        def add(mat, tris, uvs=None):
            c = tris.reshape(-1, 3).mean(0)
            key = (int(np.floor(c[0] / TILE)), int(np.floor(c[1] / TILE)))
            V = tris.reshape(-1, 3)
            builders.setdefault(key, bng.MeshBuilder()).add(mat, V, uvs=uvs if uvs is not None else V[:, :2] / 1.5,
                                                            normals=bng.flat_normals_soup(V))
        for g in components(T):
            F = T[g]
            poly = shapely.union_all([shapely.Polygon(f[:, :2]) for f in F]).buffer(0.01).buffer(-0.01)
            if poly.is_empty or poly.area < 0.5:
                continue
            rep["islands"] += 1
            rep["island_m2"] += float(poly.area)
            # the top: the faces raised; the kerb stone and its face round every boundary edge
            top = F.copy()
            top[:, :, 2] += KERB_H
            add("mp_island_top", top)
            key = np.round(F.reshape(-1, 3)[:, :2] * 200).astype(np.int64)
            _, vid = np.unique(key[:, 0] * 4_000_003 + key[:, 1], return_inverse=True)
            vid = vid.reshape(-1, 3)
            E = np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]])
            P3 = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
            k = np.sort(E, 1)
            kk = k[:, 0] * (vid.max() + 1) + k[:, 1]
            _, first, cnt = np.unique(kk, return_index=True, return_counts=True)
            B = P3[first[cnt == 1]]                       # boundary edges (a, b) of the island
            a, b = B[:, 0], B[:, 1]
            at, bt = a + [0, 0, KERB_H], b + [0, 0, KERB_H]
            ab, bb = a - [0, 0, KERB_DOWN], b - [0, 0, KERB_DOWN]
            face = np.stack([at, ab, bb, at, bb, bt], 1).reshape(-1, 3, 3)
            # outward: away from the island's middle
            c2 = np.array(poly.representative_point().coords[0])
            nrm = np.cross(face[:, 1] - face[:, 0], face[:, 2] - face[:, 0])[:, :2]
            out = ((face.mean(1)[:, :2] - c2) * nrm).sum(1) < 0
            face[out] = face[out][:, ::-1]
            u = np.linalg.norm(b - a, axis=1)
            s0 = np.zeros(len(u))
            uv = np.stack([np.c_[s0, np.full(len(u), 1.0)], np.c_[s0, np.zeros(len(u))], np.c_[u, np.zeros(len(u))],
                           np.c_[s0, np.full(len(u), 1.0)], np.c_[u, np.zeros(len(u))], np.c_[u, np.full(len(u), 1.0)]],
                          1).reshape(-1, 3, 2) * [1.0, KERB_H + KERB_DOWN]
            uv[out] = uv[out][:, ::-1]
            add("mp_island_kerb", face, uv.reshape(-1, 2))
            # the signs: on the noses that traffic approaches along the island's axis
            mrr = poly.minimum_rotated_rectangle
            R = np.asarray(mrr.exterior.coords)[:4]
            e0, e1 = R[1] - R[0], R[2] - R[1]
            ax = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
            Lr = float(np.hypot(*ax))
            if Lr < NOSE_MIN or poly.area < 2.0:
                continue
            ax /= Lr
            ctr = np.array(mrr.centroid.coords[0])
            zt = float(np.median(F[:, :, 2])) + KERB_H
            for sgn in (1.0, -1.0):
                d = ax * sgn
                nose = ctr + d * Lr / 2
                q = nose + d * APPROACH
                if not np.isfinite(carr.height([q[0]], [q[1]], "high")[0]):
                    continue
                # the pole on the island, NOSE_IN m in from its end
                p = None
                for back in np.arange(NOSE_IN, Lr / 2, 0.2):
                    cand = nose - d * back
                    if poly.buffer(-0.25).contains(shapely.Point(cand)):
                        p = cand
                        break
                if p is None:
                    continue
                for tri in box(p, 0.06, 0.06, zt - 0.3, zt + SIGN_C + SIGN_D / 2, d):
                    add("mp_island_pole", tri[None])
                front, uv, back_ = disk(p + d * 0.04, d, zt + SIGN_C, SIGN_D / 2)
                add("mp_island_233", front, uv.reshape(-1, 2))
                add("mp_island_233_back", back_)
                bt, buv = bollard(p, d, zt)
                add("mp_island_bollard", bt, buv)
                rep["signs"] += 1
    rep["island_m2"] = round(rep["island_m2"])
    files = {}
    objs = []
    with tempfile.TemporaryDirectory() as tmp:
        for (tx, ty), mb in sorted(builders.items()):
            rel = f"art/shapes/roads/islands_{tx:+03d}_{ty:+03d}.dae"
            origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
            f = os.path.join(tmp, "i.dae")
            mb.write_dae(f, name=f"islands_{tx}_{ty}", origin=origin)
            files[f"{lv}/{rel}"] = open(f, "rb").read()
            objs.append(bng.tsstatic(f"{L}/{rel}", origin, collision=True, decal=False))
    pl = signs_ch.plate("2.33")
    if pl is not None:
        import signs_net
        col, op = signs_net.rgba_files(pl.img)
        files[f"{TEX_DIR}/t_island_233_b.color.png"] = col
        files[f"{TEX_DIR}/t_island_233_o.data.png"] = op
    files[f"{TEX_DIR}/{BOLLARD_TEX}"] = bollard_png()
    mats_name = f"{lv}/art/shapes/roads/main.materials.json"
    mats = json.loads(zi.read(mats_name))
    for m in materials():
        mats[m["name"]] = m
    files[mats_name] = json.dumps(mats, indent=1).encode("utf-8")
    g_items = f"{lv}/main/MissionGroup/roads/islands/items.level.json"
    for ob in objs:
        ob["__parent"] = "islands"
    files[g_items] = ("\n".join(json.dumps(ob, separators=(",", ":")) for ob in objs) + "\n").encode("utf-8")
    # the group in the roads group
    r_items = f"{lv}/main/MissionGroup/roads/items.level.json"
    rows = read_items(zi, r_items)
    if not any(r.get("name") == "islands" and r.get("class") == "SimGroup" for r in rows):
        rows.append({"name": "islands", "class": "SimGroup", "persistentId": bng.pid(), "__parent": "roads"})
    files[r_items] = ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode("utf-8")
    gone = {"/" + n for n, d in new_dae.items() if d is None}
    with zi.writer() as zo:
        now = time.localtime()[:6]
        for i in zi.infolist():
            nm = i.filename
            if nm in files or SHAPE.search(nm) or (nm in new_dae and new_dae[nm] is None):
                continue
            if nm in new_dae:
                ni = zipfile.ZipInfo(nm, now)
                ni.compress_type, ni.external_attr = i.compress_type, i.external_attr
                zo.writestr(ni, new_dae[nm])
            elif nm == items_name and gone:
                zo.writestr(i, "\n".join(json.dumps(o, separators=(",", ":")) for o in items
                                         if o.get("shapeName") not in gone) + "\n")
            else:
                zo.writestr(i, zi.read(i), compress_type=i.compress_type)
        for n, data in sorted(files.items()):
            zo.writestr(n, data)
    rep["shapes_rewritten"] = len(new_dae)
    rep["seconds"] = round(time.time() - t0)
    print("islands:", rep, flush=True)
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(rep, open(report, "w"), indent=1)
    return rep
