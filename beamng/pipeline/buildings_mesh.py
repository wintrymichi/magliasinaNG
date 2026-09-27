"""Building meshes from swissBUILDINGS3D 3.0 (LOD2), grouped into 256 m tiles.

Facades seen in the Street View panoramas carry their projected photo texture
(texture_buildings.py -> work/facades, packed here into 4096 px atlases). All other
walls use a neutral plaster texture tinted (vertex colour) with the building's own
photographed facade colour, or a neutral plaster tone when the building was never
photographed. Roofs use a neutral clay-tile texture laid along the roof slope, tinted
with the median SWISSIMAGE colour of that roof (footprint eroded 1.5 m against relief
displacement). Collision on (visible mesh).
"""
import json, os, pickle
import numpy as np
import cv2
import rasterio
import shapely
from PIL import Image
import bng
from config import NO_PHOTO, WORK, BEAMNG_GAME

TILE = 256.0
DEFAULT_WALL = np.array([0.84, 0.80, 0.72])


def wall_uvs(tris):
    t = tris.reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    horiz = np.stack([-n[:, 1], n[:, 0]], 1)
    ln = np.linalg.norm(horiz, axis=1, keepdims=True)
    ln[ln == 0] = 1
    horiz /= ln
    u = (t[..., 0] * horiz[:, None, 0] + t[..., 1] * horiz[:, None, 1])
    return np.stack([u, t[..., 2]], -1).reshape(-1, 2)


def roof_uvs(tris, tile=1.6):
    t = tris.reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    down = np.stack([n[:, 0], n[:, 1]], 1)                # horizontal direction of the fall line
    ln = np.linalg.norm(down, axis=1, keepdims=True)
    flat = ln[:, 0] < 0.05
    down = np.where(flat[:, None], [[0.0, 1.0]], down / np.maximum(ln, 1e-9))
    along = np.stack([-down[:, 1], down[:, 0]], 1)
    u = (t[..., :2] * along[:, None]).sum(-1)
    v = (t[..., :2] * down[:, None]).sum(-1) / np.maximum(np.abs(n[:, 2:3]), 0.3)
    return np.stack([u, v], -1).reshape(-1, 2) / tile


def orient(b):
    allp = np.concatenate([b["walls"].reshape(-1, 3), b["roofs"].reshape(-1, 3)])
    ctr = allp.mean(0)
    out = {}
    for part in ("walls", "roofs"):
        t = b[part].copy()
        if len(t):
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            if part == "walls":
                o = t.mean(1) - ctr; o[:, 2] = 0
                flip = (n * o).sum(1) < 0
            else:
                flip = n[:, 2] < 0
            t[flip] = t[flip][:, ::-1]
        out[part] = t
    return out


def neutral_texture(src_zip_path, dst, gain=0.95):
    """Grey-normalised copy of a vanilla texture (keeps pattern, colour comes from vertex colours)."""
    import zipfile, io
    p = src_zip_path.lstrip("/")
    if p.startswith("levels/"):
        z = zipfile.ZipFile(os.path.join(BEAMNG_GAME, "content", "levels", p.split("/")[1] + ".zip"))
    else:
        z = zipfile.ZipFile(os.path.join(BEAMNG_GAME, "content", "assets", "materials", "trim.zip"))
    names = {n.lower(): n for n in z.namelist()}
    im = np.asarray(Image.open(io.BytesIO(z.read(names[p.lower()]))).convert("RGB")).astype(np.float32)
    g = im.mean(-1, keepdims=True)
    g = g / max(g.mean(), 1) * 255 * gain
    out = np.clip(np.repeat(g, 3, -1), 0, 255).astype(np.uint8)
    Image.fromarray(out).save(dst)


def roof_colors(blds):
    with rasterio.open(os.path.join(WORK, "ortho05.tif")) as s:
        o = s.read().transpose(1, 2, 0)
        tr = s.transform
    cols = {}
    for b in blds:
        r = b["roofs"]
        if len(r) == 0:
            continue
        fp = shapely.MultiPoint(r.reshape(-1, 3)[:, :2]).convex_hull.buffer(-1.5)
        if fp.is_empty or fp.area < 1:
            fp = shapely.MultiPoint(r.reshape(-1, 3)[:, :2]).convex_hull
        x0, y0, x1, y1 = fp.bounds
        xs = np.arange(x0, x1, 0.5); ys = np.arange(y0, y1, 0.5)
        if len(xs) == 0 or len(ys) == 0:
            continue
        X, Y = np.meshgrid(xs, ys)
        inside = shapely.contains_xy(fp, X, Y)
        if not inside.any():
            continue
        cc = ((X[inside] - tr.c) / tr.a).astype(int); rr = ((Y[inside] - tr.f) / tr.e).astype(int)
        ok = (cc >= 0) & (cc < o.shape[1]) & (rr >= 0) & (rr < o.shape[0])
        if ok.sum() < 3:
            continue
        cols[b["uuid"]] = np.median(o[rr[ok], cc[ok]], 0) / 255.0
    return cols


def build(level_dir, level_name, keep=None):
    import texturing
    blds = pickle.load(open(os.path.join(WORK, "buildings.pkl"), "rb"))
    shp_dir = os.path.join(level_dir, "art", "shapes", "buildings")
    os.makedirs(shp_dir, exist_ok=True)
    neutral_texture("/assets/materials/trim/plaster/t_highrise_plaster/t_highrise_plaster_b.color.dds",
                    os.path.join(shp_dir, "t_plaster_neutral.png"))
    neutral_texture("/levels/italy/art/shapes/buildings/Italy_bld_roof_tiles_d.dds",
                    os.path.join(shp_dir, "t_rooftiles_neutral.png"), gain=1.0)
    L = f"/levels/{level_name}/art/shapes/buildings"
    rcol = roof_colors(blds)
    atlas = texturing.Atlas(4096)
    tiles = {}
    for b in blds:
        if keep is not None and not keep(b):
            continue
        c = (np.array(b["bbox"][0]) + np.array(b["bbox"][1])) / 2
        tiles.setdefault((int(np.floor(c[0] / TILE)), int(np.floor(c[1] / TILE))), []).append(b)
    out, n_photo = [], 0
    for (tx, ty), bl in sorted(tiles.items()):
        mb = bng.MeshBuilder()
        origin = np.array([(tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.0])
        for b in bl:
            ob = orient(b)
            walls, roofs = ob["walls"], ob["roofs"]
            assigned = np.zeros(len(walls), bool)
            wall_col = DEFAULT_WALL
            f = os.path.join(WORK, "facades", f"{b['uuid'].strip('{}')}.npz")
            if len(walls) and os.path.exists(f):
                d = np.load(f)
                meds = []
                for k in range(int(d["n"]) if "n" in d else 0):
                    img, idx, mp = d[f"img{k}"], d[f"idx{k}"], d[f"map{k}"]
                    if NO_PHOTO:                               # keep only the measured facade tone
                        meds.append(np.median(img.reshape(-1, 3), 0))
                        continue
                    u0, ul, v0, vl = mp[:4]; axis = mp[4:7]
                    page, (ax, ay, aw, ah) = atlas.add(img)
                    t = walls[idx].reshape(-1, 3)
                    U = ax + ((t @ axis) - u0) / max(ul, 1e-6) * aw
                    V = ay + ((v0 + vl) - t[:, 2]) / max(vl, 1e-6) * ah
                    mb.add(f"mp_bld_photo_{page}", t, uvs=np.column_stack([U, 1.0 - V]),
                           normals=bng.flat_normals_soup(t))
                    assigned[idx] = True
                    meds.append(np.median(img.reshape(-1, 3), 0))
                    n_photo += 1
                if meds:
                    wall_col = np.median(np.array(meds), 0) / 255.0
            rest = walls[~assigned]
            if len(rest):
                V = rest.reshape(-1, 3)
                mb.add("bld_plaster", V, uvs=wall_uvs(rest) / 2.5, normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(wall_col / 0.9, 0, 1), 1.0])
            if len(roofs):
                V = roofs.reshape(-1, 3)
                col = rcol.get(b["uuid"], np.array([0.55, 0.42, 0.36]))
                mb.add("bld_roof", V, uvs=roof_uvs(roofs), normals=bng.flat_normals_soup(V),
                       colors=np.r_[np.clip(col / 0.85, 0, 1), 1.0])
        if mb.empty():
            continue
        rel = f"art/shapes/buildings/bld_{tx:+03d}_{ty:+03d}.dae"
        mb.write_dae(os.path.join(level_dir, rel), name="bld", origin=origin)
        out.append((f"/levels/{level_name}/{rel}", origin, mb.triangle_count()))
    mats = [bng.material("bld_plaster", f"{L}/t_plaster_neutral.png", roughness=0.9, vert_color=True),
            bng.material("bld_roof", f"{L}/t_rooftiles_neutral.png", roughness=0.8, vert_color=True)]
    for i, page in enumerate(atlas.pages if n_photo else []):     # no empty page without photo facades
        rel = f"art/shapes/buildings/bld_photo_{i}.jpg"
        cv2.imwrite(os.path.join(level_dir, rel), cv2.cvtColor(page, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        mats.append(bng.material(f"mp_bld_photo_{i}", f"/levels/{level_name}/{rel}", roughness=0.85))
    bng.write_materials(os.path.join(shp_dir, "main.materials.json"), mats)
    print("building photo facades", n_photo, "atlas pages", len(atlas.pages) if n_photo else 0)
    return out
