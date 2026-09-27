"""BeamNG.drive level writers: terrain (.ter + .terrain.json), scene NDJSON
(items.level.json), materials (main.materials.json) and COLLADA meshes (.dae).

Formats follow the vanilla levels shipped with BeamNG.drive 0.39
(content/levels/template.zip, italy.zip).
"""
import json, os, struct, uuid
from xml.sax.saxutils import escape
import numpy as np


def pid():
    return str(uuid.uuid4())


# ------------------------------------------------------------------ terrain
def write_ter(path, heights, z0, max_height, layers, materials):
    """heights: (n, n) float metres, row 0 = SOUTH (y = terrain position y), col 0 = west.
    layers : (n, n) uint8 material index per vertex (same orientation)."""
    n = heights.shape[0]
    assert heights.shape == (n, n) and layers.shape == (n, n)
    q = np.clip(np.round((heights - z0) / max_height * 65535.0), 0, 65535).astype("<u2")
    with open(path, "wb") as f:
        f.write(struct.pack("<B", 9))
        f.write(struct.pack("<I", n))
        f.write(q.tobytes())
        f.write(layers.astype(np.uint8).tobytes())
        f.write(struct.pack("<I", len(materials)))
        for m in materials:
            b = m.encode("utf-8")
            f.write(struct.pack("<B", len(b)))
            f.write(b)


def write_terrain_json(path, level, ter_name, n, materials):
    d = {
        "binaryFormat": "version(char), size(unsigned int), heightMap(heightMapSize * heightMapItemSize), "
                        "layerMap(layerMapSize * layerMapItemSize), layerTextureMap(layerMapSize * layerMapItemSize), "
                        "materialNames",
        "datafile": f"/levels/{level}/{ter_name}.ter",
        "heightMapItemSize": 2,
        "heightMapSize": n * n,
        "heightmapImage": f"/levels/{level}/{ter_name}.terrainheightmap.png",
        "layerMapItemSize": 1,
        "layerMapSize": n * n,
        "materials": list(materials),
        "size": n,
        "version": 9,
    }
    json.dump(d, open(path, "w"), indent=2)


# ------------------------------------------------------------------ scene
class Scene:
    """Collects objects per SimGroup path and writes the main/MissionGroup tree."""

    def __init__(self):
        self.groups = {}          # "MissionGroup/level_objects/terrain" -> [objects]
        self.children = {}        # group path -> ordered child group names

    def group(self, path):
        parts = path.split("/")
        for i in range(1, len(parts)):
            parent, child = "/".join(parts[:i]), parts[i]
            self.children.setdefault(parent, [])
            if child not in self.children[parent]:
                self.children[parent].append(child)
        self.groups.setdefault(path, [])
        return self.groups[path]

    def add(self, path, obj):
        obj = dict(obj)
        obj["__parent"] = path.split("/")[-1]
        self.group(path).append(obj)
        return obj

    def write(self, level_dir):
        root = os.path.join(level_dir, "main")
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, "items.level.json"), "w") as f:
            f.write(json.dumps({"name": "MissionGroup", "class": "SimGroup", "persistentId": pid(),
                                "enabled": "1"}) + "\n")
        all_paths = set(self.groups) | set(self.children)
        for path in sorted(all_paths):
            d = os.path.join(root, *path.split("/"))
            os.makedirs(d, exist_ok=True)
            lines = []
            for child in self.children.get(path, []):
                lines.append({"name": child, "class": "SimGroup", "persistentId": pid(),
                              "__parent": path.split("/")[-1]})
            lines += self.groups.get(path, [])
            with open(os.path.join(d, "items.level.json"), "w") as f:
                for o in lines:
                    f.write(json.dumps(o, separators=(",", ":")) + "\n")


def rot_matrix_z(yaw_rad):
    """BeamNG rotationMatrix (row-major 3x3) for a rotation about +z."""
    c, s = float(np.cos(yaw_rad)), float(np.sin(yaw_rad))
    return [c, s, 0, -s, c, 0, 0, 0, 1]


def rot_local_x_to(theta):
    """rotationMatrix turning the object's local +x axis to the world direction with math angle
    theta (radians, counter-clockwise from east). BeamNG reads the ROWS of rotationMatrix as the
    object's x, y, z axes (verified in game: a spawned vehicle faces minus its y row)."""
    c, s = float(np.cos(theta)), float(np.sin(theta))
    return [c, s, 0, -s, c, 0, 0, 0, 1]


def tsstatic(shape, pos=(0, 0, 0), rot=None, scale=None, collision=True, decal=False, name=None, **kw):
    o = {"class": "TSStatic", "persistentId": pid(), "position": [float(v) for v in pos],
         "shapeName": shape, "useInstanceRenderData": True}
    if name:
        o["name"] = name
    if rot is not None:
        o["rotationMatrix"] = [float(v) for v in rot]
    if scale is not None:
        o["scale"] = [float(v) for v in scale]
    o["collisionType"] = "Visible Mesh Final" if collision else "None"
    o["decalType"] = "Visible Mesh" if decal else "None"
    o.update(kw)
    return o


# ------------------------------------------------------------------ materials
def material(name, color_map=None, normal_map=None, roughness_map=None, ao_map=None, base_color=None,
             uv_scale=None, alpha_test=None, double_sided=False, ground_type=None, roughness=None,
             metallic=None, detail=None, extra=None, vert_color=False):
    st = {}
    if color_map:
        st["baseColorMap"] = color_map
    if base_color is not None:
        st["baseColorFactor"] = [float(v) for v in base_color]
    if normal_map:
        st["normalMap"] = normal_map
    if roughness_map:
        st["roughnessMap"] = roughness_map
    if roughness is not None:
        st["roughnessFactor"] = float(roughness)
    if metallic is not None:
        st["metallicFactor"] = float(metallic)
    if ao_map:
        st["ambientOcclusionMap"] = ao_map
    if detail:
        st.update(detail)
    if vert_color:
        st["vertColor"] = True
    m = {"name": name, "mapTo": name, "class": "Material", "persistentId": pid(),
         "Stages": [st, {}, {}, {}], "materialTag0": "beamng", "version": 1.5}
    if alpha_test is not None:
        m["alphaTest"] = True
        m["alphaRef"] = int(alpha_test)
    if double_sided:
        m["doubleSided"] = True
    if ground_type:
        m["groundType"] = ground_type
    if extra:
        m.update(extra)
    return m


def write_materials(path, mats):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = json.load(open(path)) if os.path.exists(path) else {}
    for m in mats:
        old[m["name"]] = m
    json.dump(old, open(path, "w"), indent=1)


# ------------------------------------------------------------------ meshes
class MeshBuilder:
    """Triangle soup grouped by material; writes Z-up COLLADA 1.4.1."""

    def __init__(self):
        self.parts = {}   # material -> [verts(list of arrays), normals, uvs, count]

    def add(self, material, verts, uvs=None, normals=None, tris=None, colors=None):
        """verts (n,3); tris (m,3) indices into verts (default: consecutive triangles);
        colors (n,4) or (4,) RGBA 0..1 vertex colours (optional, used with vertColor materials)."""
        verts = np.asarray(verts, np.float64)
        if tris is None:
            tris = np.arange(len(verts)).reshape(-1, 3)
        tris = np.asarray(tris, np.int64)
        if len(tris) == 0:
            return
        if uvs is None:
            uvs = verts[:, :2] / 4.0
        uvs = np.asarray(uvs, np.float64)
        if normals is None:
            normals = vertex_normals(verts, tris)
        if colors is None:
            colors = np.ones((len(verts), 4))
        colors = np.broadcast_to(np.asarray(colors, np.float64), (len(verts), 4))
        p = self.parts.setdefault(material, [[], [], [], [], 0, []])
        p[0].append(verts); p[1].append(np.asarray(normals, np.float64)); p[2].append(uvs)
        p[3].append(tris + p[4]); p[4] += len(verts); p[5].append(colors)

    def empty(self):
        return not self.parts

    def triangle_count(self):
        return sum(sum(len(t) for t in p[3]) for p in self.parts.values())

    def write_dae(self, path, name="mesh", origin=(0, 0, 0), detail=2):
        """One geometry with one <triangles> list per material, in a single node named
        '<name>_a<detail>' under base00/start01. Torque reads the trailing number of a mesh
        node as its LOD pixel size, so node names must not end with other digits."""
        o = np.asarray(origin, np.float64)
        Vs, Ns, Ts, Cs, prims, mats, effects, binds = [], [], [], [], [], [], [], []
        off = 0
        use_col = any(not np.allclose(np.concatenate(p[5]), 1.0) for p in self.parts.values())
        nin = 4 if use_col else 3
        for mat, p in self.parts.items():
            V = np.concatenate(p[0]) - o
            I = np.concatenate(p[3]) + off
            Vs.append(V)
            Ns.append(np.concatenate(p[1]))
            Ts.append(np.concatenate(p[2]))
            Cs.append(np.concatenate(p[5]))
            idx = np.repeat(I.ravel()[:, None], nin, 1).ravel()
            m = escape(mat)
            col_in = '<input semantic="COLOR" source="#g-c" offset="3" set="0"/>' if use_col else ""
            prims.append(f'<triangles material="{m}-mat" count="{len(I)}">'
                         f'<input semantic="VERTEX" source="#g-v" offset="0"/>'
                         f'<input semantic="NORMAL" source="#g-n" offset="1"/>'
                         f'<input semantic="TEXCOORD" source="#g-t" offset="2" set="0"/>{col_in}'
                         f'<p>{" ".join(map(str, idx))}</p></triangles>')
            mats.append(f'<material id="{m}-mat" name="{m}"><instance_effect url="#{m}-fx"/></material>')
            effects.append(f'<effect id="{m}-fx"><profile_COMMON><technique sid="common"><lambert>'
                           f'<diffuse><color>0.8 0.8 0.8 1</color></diffuse></lambert></technique></profile_COMMON></effect>')
            binds.append(f'<instance_material symbol="{m}-mat" target="#{m}-mat">'
                         f'<bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/></instance_material>')
            off += len(V)
        V, N, T, Cc = np.concatenate(Vs), np.concatenate(Ns), np.concatenate(Ts), np.concatenate(Cs)
        col_src = (f'<source id="g-c"><float_array id="g-ca" count="{Cc.size}">{" ".join(f"{v:.4f}" for v in Cc.ravel())}</float_array>'
                   f'<technique_common><accessor source="#g-ca" count="{len(Cc)}" stride="4"><param name="R" type="float"/>'
                   f'<param name="G" type="float"/><param name="B" type="float"/><param name="A" type="float"/></accessor>'
                   f'</technique_common></source>') if use_col else ""
        fl = lambda a: " ".join(f"{v:.5f}" for v in a.ravel())
        safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "mesh"
        safe = safe.rstrip("0123456789_") or "mesh"
        node = f"{safe}_a{int(detail)}"
        doc = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><contributor><authoring_tool>magliaso_pura pipeline</authoring_tool></contributor><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_effects>{"".join(effects)}</library_effects>
<library_materials>{"".join(mats)}</library_materials>
<library_geometries><geometry id="g" name="{node}"><mesh>
<source id="g-p"><float_array id="g-pa" count="{V.size}">{fl(V)}</float_array>
<technique_common><accessor source="#g-pa" count="{len(V)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g-n"><float_array id="g-na" count="{N.size}">{fl(N)}</float_array>
<technique_common><accessor source="#g-na" count="{len(N)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g-t"><float_array id="g-ta" count="{T.size}">{fl(T)}</float_array>
<technique_common><accessor source="#g-ta" count="{len(T)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source>
{col_src}
<vertices id="g-v"><input semantic="POSITION" source="#g-p"/></vertices>
{"".join(prims)}
</mesh></geometry></library_geometries>
<library_visual_scenes><visual_scene id="Scene" name="Scene">
<node id="base00" name="base00" type="NODE"><node id="start01" name="start01" type="NODE">
<node id="{node}" name="{node}" type="NODE"><instance_geometry url="#g" name="{node}"><bind_material><technique_common>{"".join(binds)}</technique_common></bind_material></instance_geometry></node>
</node></node>
</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)


def vertex_normals(V, T):
    V = np.asarray(V, np.float64)
    T = np.asarray(T, np.int64)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    n = np.linalg.norm(N, axis=1, keepdims=True)
    n[n == 0] = 1
    return N / n


def flat_normals_soup(V):
    """For triangle soups (every 3 consecutive vertices a face): per-face normals."""
    V = np.asarray(V, np.float64).reshape(-1, 3, 3)
    fn = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    n = np.linalg.norm(fn, axis=1, keepdims=True)
    n[n == 0] = 1
    return np.repeat(fn / n, 3, 0)
