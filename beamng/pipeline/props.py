"""Street furniture from the photo detections (poles.json).

Pole type from measured height/signs: > 5.5 m or top not seen and no plate -> street
light (Italian single-arm luminaire, arm towards the carriageway); plates attached ->
sign pole (grey steel tube up to 0.1 m above the top plate); <= 1.6 m -> delineator
post (white, black band); 'utility_pole' -> wooden pole scaled to its height.
Sign plates: the plate pixels of the best frontal photo (segmentation mask as alpha)
on a flat plate of the measured size (pixel extent x distance / focal length), at the
measured height, facing the camera that saw it frontally. Back-only plates get a grey
back of the same outline.
"""
import json, math, os
import numpy as np
import cv2
from PIL import Image
from config import WORK, DATASET, NO_PHOTO
import bng
import asset_bounds
import camera

LIGHT = "/levels/italy/art/shapes/buildings/italy_light_single.dae"
WOODPOLE = "/art/shapes/common/power_lines_procedural/electric_pole_wood_old_01.dae"
F = 800.0   # focal length (px) of the dataset views
LAMP_RADIUS = 14.0          # m lit by the light of a street lamp (v2.4)
LAMP_BRIGHTNESS = 1.2
LAMP_LUMEN = 6000.0         # a street light of a village road


def tube(c, z0, z1, r=0.045, n=10):
    a = np.linspace(0, 2 * np.pi, n + 1)
    ring = np.column_stack([np.cos(a), np.sin(a)]) * r + c
    tris = []
    for k in range(n):
        p0, p1 = ring[k], ring[k + 1]
        A, B = np.r_[p0, z0], np.r_[p1, z0]
        Ct, Dt = np.r_[p0, z1], np.r_[p1, z1]
        tris += [A, B, Dt, A, Dt, Ct]
    return np.array(tris)


def box(c, t, w, d, z0, z1):
    nrm = np.array([-t[1], t[0]])
    cs = [c + t * w / 2 + nrm * d / 2, c - t * w / 2 + nrm * d / 2, c - t * w / 2 - nrm * d / 2, c + t * w / 2 - nrm * d / 2]
    tris = []
    for a in range(4):
        p0, p1 = cs[a], cs[(a + 1) % 4]
        tris += [np.r_[p0, z1], np.r_[p0, z0], np.r_[p1, z0], np.r_[p0, z1], np.r_[p1, z0], np.r_[p1, z1]]
    tris += [np.r_[cs[0], z1], np.r_[cs[1], z1], np.r_[cs[2], z1], np.r_[cs[0], z1], np.r_[cs[2], z1], np.r_[cs[3], z1]]
    return np.array(tris)


def plate_image(best, D):
    """RGBA image of the sign from the dataset view, alpha = segmentation mask of the plate."""
    rec = D[best["pano"]]
    img = cv2.imread(os.path.join(DATASET, "viste", f"{rec['index']:04d}_{rec['id']}_{best['view']}_p00.jpg"))
    seg = np.asarray(Image.open(os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{best['view']}_p00.png")))
    cx, cy, w, h = best["cx"], best["cy"], best["w"], best["h"]
    x0, y0 = int(round(cx - w / 2)) - 2, int(round(cy - h / 2)) - 2
    x1, y1 = x0 + w + 4, y0 + h + 4
    x0, y0 = max(0, x0), max(0, y0)
    crop = img[y0:y1, x0:x1]
    m = np.isin(seg[y0:y1, x0:x1], [49, 50, 46]).astype(np.uint8) * 255
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    rgba = np.dstack([cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), m])
    # upscale for smoother edges (content resolution stays that of the photo)
    k = max(1, int(np.ceil(128 / max(rgba.shape[:2]))))
    return cv2.resize(rgba, (rgba.shape[1] * k, rgba.shape[0] * k), interpolation=cv2.INTER_CUBIC)


def build(level_dir, level_name, scene, hfn):
    poles = json.load(open(os.path.join(WORK, "poles.json")))
    D = json.load(open(os.path.join(DATASET, "panoramas.json")))
    rp = np.load(os.path.join(WORK, "road_profile.npz"))
    centre = rp["center"]
    b = asset_bounds.cached([LIGHT, WOODPOLE])
    lb = b.get(LIGHT)
    g = "MissionGroup/props"
    mb = bng.MeshBuilder()
    mats = [bng.material("mp_pole_steel", base_color=[0.62, 0.63, 0.64, 1], roughness=0.5, metallic=0.6),
            bng.material("mp_delineator_white", base_color=[0.9, 0.9, 0.88, 1], roughness=0.6),
            bng.material("mp_delineator_black", base_color=[0.05, 0.05, 0.05, 1], roughness=0.6),
            bng.material("mp_sign_back", base_color=[0.55, 0.56, 0.57, 1], roughness=0.5, metallic=0.5,
                         double_sided=False),
            bng.material("mp_cabinet", base_color=[0.62, 0.63, 0.60, 1], roughness=0.6, metallic=0.2)]
    sign_dir = os.path.join(level_dir, "art", "shapes", "signs")
    os.makedirs(sign_dir, exist_ok=True)
    counts = {"street_light": 0, "sign_pole": 0, "delineator": 0, "utility_pole": 0, "plates": 0}
    # street lights triangulated from the lamp heads (lamps.py): arm from the pole foot to the head
    lamps_f = os.path.join(WORK, "lamps.json")
    lamps = json.load(open(lamps_f)) if os.path.exists(lamps_f) else []
    lamp_feet = np.array([l["foot"][:2] for l in lamps]) if lamps else np.zeros((0, 2))
    for l in lamps:
        fx, fy, fz = l["foot"]
        hx, hy, hz = l["head"]
        theta_arm = math.atan2(hy - fy, hx - fx)
        if lb:
            ext_pos, ext_neg = lb[1][0], -lb[0][0]
            theta = theta_arm if ext_pos >= ext_neg else theta_arm + math.pi
            hs = float(np.clip(l["height"] / max(lb[1][2] - lb[0][2], 1), 0.6, 1.5))
            scene.add(g + "/street_lights", bng.tsstatic(LIGHT, (fx, fy, float(hfn([fx], [fy])[0])),
                                                          rot=bng.rot_local_x_to(theta), scale=(1, 1, hs),
                                                          collision=True))
            counts["street_light"] += 1
            # v2.4: the light of the lamp, under its head: warm, no shadows (cheap); seen at night
            scene.add(g + "/street_lights", {"class": "PointLight", "persistentId": bng.pid(),
                                              "position": [float(hx), float(hy), float(hz) - 0.35],
                                              "radius": LAMP_RADIUS, "intensity": LAMP_LUMEN, "intensityUnit": "lm",
                                              "brightness": LAMP_BRIGHTNESS,        # the older field, as a fallback
                                              "color": [1.0, 0.82, 0.58, 1.0], "castShadows": False,
                                              "isEnabled": True})
            counts["lamp_light"] = counts.get("lamp_light", 0) + 1
    # gather raw sign observations again to rebuild plate crops (poles.py kept the best per plate)
    for j, p in enumerate(poles):
        x, y = p["x"], p["y"]
        z = float(hfn([x], [y])[0])
        h = p["h"]
        signs = p.get("signs", [])
        k = int(np.argmin(np.hypot(centre[:, 0] - x, centre[:, 1] - y)))
        to_road = centre[k] - np.array([x, y])
        to_road /= max(np.linalg.norm(to_road), 1e-6)
        if p["cls"] == "utility_pole":
            scale = (h or 8.0) / max(b[WOODPOLE][1][2] - b[WOODPOLE][0][2], 1) if b.get(WOODPOLE) else 1
            scene.add(g + "/utility_poles", bng.tsstatic(WOODPOLE, (x, y, z), rot=bng.rot_matrix_z(0),
                                                          scale=(scale, scale, scale), collision=True))
            counts["utility_pole"] += 1
            continue
        if signs:
            top = max(sg["z"] for sg in signs) - z + 0.45
            V = tube(np.array([x, y]), z - 0.3, z + max(top, 1.5))
            mb.add("mp_pole_steel", V, uvs=V[:, :2] + V[:, 2:3], normals=bng.flat_normals_soup(V))
            counts["sign_pole"] += 1
            for q, sg in enumerate(signs):
                # plate size from the photo: pixel size x distance / focal length
                pl_file = os.path.join(WORK, "signs", sg.get("plate", ""))
                if not os.path.exists(pl_file):
                    continue
                ang = math.radians(sg["face_bearing"])
                nrm = np.array([math.sin(ang), math.cos(ang)])            # plate normal (facing)
                tng = np.array([nrm[1], -nrm[0]])
                hp, wp = sg["hpx"], sg["wpx"]
                dist = max(sg["dist"], 2.0)
                W_m = float(np.clip(wp * dist / F, 0.35, 2.5)); H_m = float(np.clip(hp * dist / F, 0.35, 2.0))
                c3 = np.array([x, y]) + nrm * 0.06
                zc = sg["z"]
                corners = [c3 - tng * W_m / 2, c3 + tng * W_m / 2]
                A = np.r_[corners[0], zc - H_m / 2]; B = np.r_[corners[1], zc - H_m / 2]
                Cc = np.r_[corners[1], zc + H_m / 2]; Dd = np.r_[corners[0], zc + H_m / 2]
                front = np.array([A, B, Cc, A, Cc, Dd])
                uv = np.array([[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]], float)
                matname = f"mp_sign_{j:03d}_{q}"
                tex = f"sign_{j:03d}_{q}.png"
                rgba = np.asarray(Image.open(pl_file)).copy()
                if NO_PHOTO:                                   # plate shape and colour only, no photo
                    m = rgba[..., 3] > 127
                    if m.any():
                        rgba[..., :3] = np.median(rgba[..., :3][m], 0).astype(np.uint8)
                kk = max(1, int(np.ceil(96 / max(rgba.shape[:2]))))
                rgba = cv2.resize(rgba, (rgba.shape[1] * kk, rgba.shape[0] * kk), interpolation=cv2.INTER_CUBIC)
                Image.fromarray(rgba).save(os.path.join(sign_dir, tex))
                mats.append(bng.material(matname, f"/levels/{level_name}/art/shapes/signs/{tex}", roughness=0.35,
                                         alpha_test=100, ground_type="METAL"))
                mb.add(matname, front, uvs=uv, normals=np.repeat(np.r_[nrm, 0][None], 6, 0))
                back = front[::-1] - np.r_[nrm * 0.01, 0]
                mb.add("mp_sign_back", back, uvs=uv[::-1], normals=np.repeat(np.r_[-nrm, 0][None], 6, 0))
                counts["plates"] += 1
            continue
        if h is not None and h <= 1.6:
            V = box(np.array([x, y]), np.array([to_road[1], -to_road[0]]), 0.12, 0.10, z - 0.2, z + 1.0)
            mb.add("mp_delineator_white", V, uvs=V[:, :2] + V[:, 2:3], normals=bng.flat_normals_soup(V))
            Vb = box(np.array([x, y]) + to_road * 0.052, np.array([to_road[1], -to_road[0]]), 0.10, 0.004,
                     z + 0.72, z + 0.90)
            mb.add("mp_delineator_black", Vb, uvs=Vb[:, :2], normals=bng.flat_normals_soup(Vb))
            counts["delineator"] += 1
            continue
        if len(lamp_feet) and np.min(np.hypot(lamp_feet[:, 0] - x, lamp_feet[:, 1] - y)) < 3.0:
            continue                                   # already placed from the lamp-head triangulation
        # street light: the model's arm lies along its local +x or -x (the longer side); turn it
        # so the arm points to the carriageway
        theta_road = math.atan2(to_road[1], to_road[0])
        if lb:
            ext_pos, ext_neg = lb[1][0], -lb[0][0]
            theta = theta_road if ext_pos >= ext_neg else theta_road + math.pi
            hs = (h / max(lb[1][2] - lb[0][2], 1)) if (h and h > 5.5) else 1.0
            scene.add(g + "/street_lights", bng.tsstatic(LIGHT, (x, y, z), rot=bng.rot_local_x_to(theta),
                                                          scale=(1, 1, float(np.clip(hs, 0.7, 1.4))), collision=True))
        counts["street_light"] += 1
    # small street furniture (objects.py)
    # models whose materials all resolve (checked with copy_materials); cabinets are procedural boxes
    OBJ_MODEL = {"trash_can": "/levels/italy/art/shapes/buildings/italy_clutter_metal_bin.DAE",
                 "bench": "/levels/east_coast_usa/art/shapes/clutter/clutter_city_bench_wood.dae",
                 "hydrant": "/levels/italy/art/shapes/buildings/italy_clutter_fire_hydrant.DAE",
                 "mailbox": "/levels/italy/art/shapes/buildings/italy_clutter_mailbox.DAE"}
    obj_f = os.path.join(WORK, "objects.json")
    used_models = set()
    if os.path.exists(obj_f):
        for o in json.load(open(obj_f)):
            mdl = OBJ_MODEL.get(o["cls"])
            if o["cls"] == "junction_box":
                k = int(np.argmin(np.hypot(centre[:, 0] - o["x"], centre[:, 1] - o["y"])))
                tr_ = centre[k] - np.array([o["x"], o["y"]])
                tr_ /= max(np.linalg.norm(tr_), 1e-6)
                zc = float(hfn([o["x"]], [o["y"]])[0])
                Vb = box(np.array([o["x"], o["y"]]), np.array([tr_[1], -tr_[0]]), max(0.5, min(o["width"], 1.6)),
                         0.35, zc - 0.1, zc + 1.2)
                mb.add("mp_cabinet", Vb, uvs=Vb[:, :2] + Vb[:, 2:3], normals=bng.flat_normals_soup(Vb))
                counts["junction_box"] = counts.get("junction_box", 0) + 1
                continue
            if not mdl:
                continue
            k = int(np.argmin(np.hypot(centre[:, 0] - o["x"], centre[:, 1] - o["y"])))
            tr_ = centre[k] - np.array([o["x"], o["y"]])
            theta = math.atan2(tr_[1], tr_[0]) + math.pi / 2
            scene.add(g + "/furniture", bng.tsstatic(mdl, (o["x"], o["y"], float(hfn([o["x"]], [o["y"]])[0])),
                                                      rot=bng.rot_local_x_to(theta), collision=True))
            used_models.add(mdl)
            counts[o["cls"]] = counts.get(o["cls"], 0) + 1
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "props", "main.materials.json"), mats)
    rel = "art/shapes/props/props_poles.dae"
    mb.write_dae(os.path.join(level_dir, rel), name="props", origin=(0, 0, 0), orient=True)
    scene.add(g, bng.tsstatic(f"/levels/{level_name}/{rel}", (0, 0, 0), collision=True))
    # materials of the vanilla models used
    import copy_materials
    used = set(asset_bounds.dae_material_names(LIGHT)) | set(asset_bounds.dae_material_names(WOODPOLE))
    for mdl in used_models:
        used |= set(asset_bounds.dae_material_names(mdl))
    used = sorted(used)
    found, missing = copy_materials.collect(used)
    bng.write_materials(os.path.join(level_dir, "art", "shapes", "props", "vanilla.materials.json"), list(found.values()))
    print("props", counts, "missing materials", missing)
