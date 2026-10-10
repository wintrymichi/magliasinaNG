"""BeamNG.drive level writers: terrain (.ter + .terrain.json), scene NDJSON
(items.level.json), materials (main.materials.json) and COLLADA meshes (.dae).

Formats follow the vanilla levels shipped with BeamNG.drive 0.39
(content/levels/template.zip, italy.zip).
"""
import re
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
_TRIM_ZEROS = re.compile(r"(\.\d*?)0+\b")     # 2.500 -> 2.5, 3.000 -> 3.
_TRIM_DOT = re.compile(r"\.(?= |$)")            # 3. -> 3


NORMAL_STEP = 0.25     # corners whose normals round to the same 0.25 steps are welded (about 10 degrees)


def weld_corners(V, N, UV, T, C=None, step=NORMAL_STEP):
    """Indexed mesh with shared vertices (v2.5): corners at the same position (mm), texture
    coordinate (1e-4) and colour and with about the same normal become one vertex with the mean
    normal; degenerate triangles are dropped. Positions, triangles and texture coordinates do not
    change, a crease keeps its two vertices. The meshes were written as triangle soups (three own
    vertices per triangle), twice the vertices the game has to store, draw and collide with.
    Returns (V, N, UV, T, C)."""
    T = np.asarray(T, np.int64)
    used, inv_used = np.unique(T, return_inverse=True)
    cols = [np.round(V[used] * 1000), np.round(UV[used] * 1e4), np.round(N[used] / step)]
    if C is not None:
        cols.append(np.round(C[used] * 1000))
    u, inv = np.unique(np.column_stack(cols).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.ravel()
    m = len(u)
    cnt = np.bincount(inv, minlength=m)[:, None]

    def mean(A):
        W = np.zeros((m, A.shape[1]))
        np.add.at(W, inv, A[used])
        return W / cnt
    V2, UV2 = mean(V), mean(UV)
    N2 = mean(N)
    N2 /= np.maximum(np.linalg.norm(N2, axis=1, keepdims=True), 1e-9)
    C2 = mean(C) if C is not None else None
    T2 = inv[inv_used.ravel()].reshape(-1, 3)
    good = (T2[:, 0] != T2[:, 1]) & (T2[:, 1] != T2[:, 2]) & (T2[:, 0] != T2[:, 2])
    return V2, N2, UV2, T2[good], C2


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

    def orient_closed(self):
        """Every solid piece (posts, boxes, wall prisms, sleepers, rails: no edge shared by more than two
        triangles, open at most where it stands on the ground) with its faces turned the same way and
        out of the piece (v2.4: the game draws a face from its front only, and boxes built in a
        left-handed frame had their faces turned in). The side comes from the volume swept from the
        piece's centre; flat pieces (a mesh fence, a guard rail sheet) are left as they are. Returns
        the number of triangles turned."""
        tri_part, tri_idx, corners = [], [], []
        for mat, p in self.parts.items():
            V = np.concatenate(p[0])
            T = np.concatenate(p[3])
            tri_part += [mat] * len(T)
            tri_idx.append(np.arange(len(T)))
            corners.append(V[T])
        if not corners:
            return 0
        C = np.concatenate(corners)                              # (k, 3, 3)
        tri_idx = np.concatenate(tri_idx)
        tri_part = np.array(tri_part)
        key = np.round(C.reshape(-1, 3) * 1000).astype(np.int64)
        _, vid = np.unique(key, axis=0, return_inverse=True)
        vid = vid.reshape(-1, 3)
        k = len(vid)
        # directed edges -> undirected edge ids, and the triangles of every edge
        a = vid[:, [0, 1, 2]].ravel()
        b = vid[:, [1, 2, 0]].ravel()
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        eid_key = lo.astype(np.int64) * (vid.max() + 1) + hi
        ue, eid, cnt = np.unique(eid_key, return_inverse=True, return_counts=True)
        etri = np.repeat(np.arange(k), 3)
        fwd = a < b                                                 # direction of the edge in its triangle
        # components through shared edges
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        order = np.argsort(eid, kind="stable")
        e_s, t_s, f_s = eid[order], etri[order], fwd[order]
        same = e_s[1:] == e_s[:-1]
        A = coo_matrix((np.ones(int(same.sum())), (t_s[:-1][same], t_s[1:][same])), shape=(k, k))
        ncomp, comp = connected_components(A, directed=False)
        closed = np.ones(ncomp, bool)                              # manifold: no edge of 3+ triangles
        np.logical_and.at(closed, comp[etri], (cnt[eid] <= 2))
        flip = np.zeros(k, bool)
        # consistent orientation by breadth-first search over the shared edges (a closed piece only)
        nbr = {}
        for i in np.flatnonzero(same):
            t1, t2 = t_s[i], t_s[i + 1]
            if closed[comp[t1]] and cnt[e_s[i]] == 2:
                opp = f_s[i] != f_s[i + 1]                          # consistent when the edge runs both ways
                nbr.setdefault(t1, []).append((t2, opp))
                nbr.setdefault(t2, []).append((t1, opp))
        seen = np.zeros(k, bool)
        for s in np.flatnonzero(closed[comp]):
            if seen[s]:
                continue
            seen[s] = True
            stack = [s]
            members = [s]
            while stack:
                t = stack.pop()
                for u, opp in nbr.get(t, []):
                    if not seen[u]:
                        seen[u] = True
                        flip[u] = flip[t] ^ (not opp)
                        stack.append(u)
                        members.append(u)
            m = np.array(members)
            P = C[m].copy()
            P[flip[m]] = P[flip[m]][:, ::-1]
            ctr = P.reshape(-1, 3).mean(0)
            Q = P - ctr
            vol = np.einsum("ij,ij->i", Q[:, 0], np.cross(Q[:, 1], Q[:, 2])).sum() / 6.0
            box = np.prod(np.maximum(P.reshape(-1, 3).max(0) - P.reshape(-1, 3).min(0), 1e-6))
            if abs(vol) < 0.05 * box:                               # flat: no inside to turn away from
                flip[m] = False
            elif vol < 0:
                flip[m] = ~flip[m]
        if not flip.any():
            return 0
        # write the turns back: reversed corners and opposite normals of the turned triangles
        base = 0
        for mat, p in self.parts.items():
            T = np.concatenate(p[3])
            n_t = len(T)
            f = flip[base:base + n_t]
            base += n_t
            if not f.any():
                continue
            N = np.concatenate(p[1])
            used = np.zeros(len(N), np.int32)
            np.add.at(used, T[~f].ravel(), 1)
            T[f] = T[f][:, [0, 2, 1]]
            own = np.unique(T[f].ravel())
            own = own[used[own] == 0]                           # vertices of turned triangles only
            N[own] = -N[own]
            V = np.concatenate(p[0]); U = np.concatenate(p[2]); Cc = np.concatenate(p[5])
            p[0], p[1], p[2], p[3], p[5] = [V], [N], [U], [T], [Cc]
        return int(flip.sum())

    def write_dae(self, path, name="mesh", origin=(0, 0, 0), detail=2, orient=False, weld=True, billboard=None):
        """One geometry with one <triangles> list per material, in a single node named
        '<name>_a<detail>' under base00/start01. Torque reads the trailing number of a mesh
        node as its LOD pixel size, so node names must not end with other digits.
        orient: the solid pieces turned out first (orient_closed, v2.4).
        weld: shared vertices (weld_corners, v2.5).
        billboard: (pixel size, {"BB::...": value}) adds an imposter detail level (an empty node
        'bb_autobillboard<size>' beside start01, its BB:: settings as FCOLLADA user properties):
        under that size on screen the game draws a picture of the mesh it renders itself (v2.7)."""
        if orient:
            self.orient_closed()
        if weld:
            for mat, p in self.parts.items():
                V2, N2, U2, T2, C2 = weld_corners(np.concatenate(p[0]), np.concatenate(p[1]),
                                                  np.concatenate(p[2]), np.concatenate(p[3]), np.concatenate(p[5]))
                self.parts[mat] = [[V2], [N2], [U2], [T2], len(V2), [C2]]
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
        # shortest text that keeps mm positions and 1e-4 texture coordinates (a v2.0 map has
        # gigabytes of these); tiling texture coordinates far from 0 are moved by whole tiles
        fl = lambda a, d: _TRIM_DOT.sub("", _TRIM_ZEROS.sub(r"\1", " ".join(f"{v:.{d}f}" for v in np.asarray(a).ravel())))
        if len(T) and np.abs(T.mean(0)).max() > 2.0:
            T = T - np.floor(T.mean(0))
        col_src = (f'<source id="g-c"><float_array id="g-ca" count="{Cc.size}">{fl(Cc, 3)}</float_array>'
                   f'<technique_common><accessor source="#g-ca" count="{len(Cc)}" stride="4"><param name="R" type="float"/>'
                   f'<param name="G" type="float"/><param name="B" type="float"/><param name="A" type="float"/></accessor>'
                   f'</technique_common></source>') if use_col else ""
        safe = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "mesh"
        safe = safe.rstrip("0123456789_") or "mesh"
        node = f"{safe}_a{int(detail)}"
        bb = ""
        if billboard is not None:
            size, props = billboard
            bb = (f'<node id="bb" name="bb_autobillboard{int(size)}" type="NODE"><extra><technique profile="FCOLLADA">'
                  f'<user_properties>{" ".join(f"{k}={v}" for k, v in props.items())}</user_properties>'
                  f'</technique></extra></node>')
        doc = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><contributor><authoring_tool>magliaso_pura pipeline</authoring_tool></contributor><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_effects>{"".join(effects)}</library_effects>
<library_materials>{"".join(mats)}</library_materials>
<library_geometries><geometry id="g" name="{node}"><mesh>
<source id="g-p"><float_array id="g-pa" count="{V.size}">{fl(V, 3)}</float_array>
<technique_common><accessor source="#g-pa" count="{len(V)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g-n"><float_array id="g-na" count="{N.size}">{fl(N, 3)}</float_array>
<technique_common><accessor source="#g-na" count="{len(N)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="g-t"><float_array id="g-ta" count="{T.size}">{fl(T, 4)}</float_array>
<technique_common><accessor source="#g-ta" count="{len(T)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source>
{col_src}
<vertices id="g-v"><input semantic="POSITION" source="#g-p"/></vertices>
{"".join(prims)}
</mesh></geometry></library_geometries>
<library_visual_scenes><visual_scene id="Scene" name="Scene">
<node id="base00" name="base00" type="NODE"><node id="start01" name="start01" type="NODE">
<node id="{node}" name="{node}" type="NODE"><instance_geometry url="#g" name="{node}"><bind_material><technique_common>{"".join(binds)}</technique_common></bind_material></instance_geometry></node>
</node>{bb}</node>
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


def box_uvs_soup(V, tile):
    """For triangle soups: texture coordinates (k*3, 2) projected along each face's main axis, `tile` m
    per repeat: (x, y) on faces that look up or down, (y, z) or (x, z) on the others. The (x + y, z) of
    the walls gives a face lying flat (the underside of a bridge deck, a parapet top) or one running
    along x = -y a single texture row stretched into stripes."""
    V = np.asarray(V, np.float64).reshape(-1, 3, 3)
    fn = np.abs(np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0]))
    ax = np.argmax(fn, axis=1)                   # 0: faces x, 1: faces y, 2: faces z
    u = np.where(ax == 0, V[:, :, 1].T, V[:, :, 0].T).T
    v = np.where(ax == 2, V[:, :, 1].T, V[:, :, 2].T).T
    return np.column_stack([u.reshape(-1), v.reshape(-1)]) / tile


# ------------------------------------------------------------------ the built level, file by file
class LevelInfo:
    """One file of a built level, named as in the mod's zip (levels/<name>/...)."""

    def __init__(self, filename, date_time=None, file_size=0):
        self.filename = filename
        self.date_time = date_time
        self.file_size = file_size
        self.compress_type = 0
        self.external_attr = 0

    def is_dir(self):
        return False


class LevelFiles:
    """The level folder of the build (root: the folder that holds levels/<name>/) read and rewritten by
    the steps that finish the level after build_level.py has written it (optimize_level, groundcover, the
    road paint, the signs, the lamps...): read(name), namelist(), infolist(), NameToInfo as on the zip of
    the mod, and writer(): every file the step keeps is written to it (writestr, as into a new zip); at
    the end the files written with other contents are replaced, the new ones added and those not written
    removed. A file written with the contents it had keeps its date (the game keeps its converted shape)."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.NameToInfo = {}
        for dp, _, fs in os.walk(os.path.join(self.root, "levels")):
            for f in fs:
                p = os.path.join(dp, f)
                n = os.path.relpath(p, self.root).replace(os.sep, "/")
                self.NameToInfo[n] = LevelInfo(n, file_size=os.path.getsize(p))
        self.NameToInfo = dict(sorted(self.NameToInfo.items()))

    def path(self, name):
        return os.path.join(self.root, *name.split("/"))

    def namelist(self):
        return list(self.NameToInfo)

    def infolist(self):
        return list(self.NameToInfo.values())

    def read(self, name):
        name = getattr(name, "filename", name)
        if name not in self.NameToInfo:
            raise KeyError(name)
        with open(self.path(name), "rb") as f:
            return f.read()

    def writer(self):
        return LevelWriter(self)


class LevelWriter:
    """See LevelFiles: the new contents wait in a folder beside the level until close()."""

    def __init__(self, files):
        import tempfile
        self.files = files
        self.stage = tempfile.mkdtemp(prefix=".level_step_", dir=files.root)
        self.kept, self.new = set(), set()

    def writestr(self, info, data, compress_type=None):
        name = getattr(info, "filename", info)
        if name.endswith("/"):                   # a directory entry of a zip: the folders follow their files
            return
        if isinstance(data, str):
            data = data.encode("utf-8")
        if name in self.files.NameToInfo and self.files.NameToInfo[name].file_size == len(data) \
                and self.files.read(name) == data:
            self.kept.add(name)
            return
        p = os.path.join(self.stage, *name.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        self.new.add(name)

    def close(self):
        import shutil
        for name in list(self.files.NameToInfo):
            if name not in self.kept and name not in self.new:
                os.remove(self.files.path(name))
                del self.files.NameToInfo[name]
        for name in sorted(self.new):
            dst = self.files.path(name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(os.path.join(self.stage, *name.split("/")), dst)
            self.files.NameToInfo[name] = LevelInfo(name, file_size=os.path.getsize(dst))
        shutil.rmtree(self.stage, ignore_errors=True)
        for dp, ds, fs in os.walk(os.path.join(self.files.root, "levels"), topdown=False):
            if not ds and not fs:
                os.rmdir(dp)
        self.files.NameToInfo = dict(sorted(self.files.NameToInfo.items()))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            import shutil
            shutil.rmtree(self.stage, ignore_errors=True)
