"""Screenshots of a built level without the game, for the visual review (review_map.py): WebGL
(three.js) in headless Chromium (Playwright, SwiftShader).

- terrain: the heights of the .ter, draped with the orthophoto (WORK/ortho.tif); around it a coarse
  terrain for the horizon and the backdrop mesh of the level;
- the meshes of the level (roads, bridges, road paint, walls, guardrails, fences, buildings, poles
  and signs) in the colours of their materials, vertex colours where the DAE has them; vanilla
  shapes (street lights, furniture) as grey posts;
- trees and shrubs of the forest files as cones / crowns of their size; the lake;
- sun with shadows, sky and haze.
Not a picture of the game (no game textures): a check of the geometry and of what is where.

    with Renderer(level_dir) as r:
        r.shot(Camera.look((x, y, z), (tx, ty, tz)), "view.jpg")
        r.shot(Camera.top(x0, y0, x1, y1, px_per_m=1.0), "tile.jpg")
Needs: pip install playwright (Chromium: PLAYWRIGHT_BROWSERS_PATH or `playwright install chromium`).
"""
import base64, glob, json, math, os, re
import numpy as np
from config import WORK

THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js"
THREE = os.path.join(WORK, "three.module.js")
ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
SKY = (0.70, 0.79, 0.88)
SUN_AZ, SUN_EL = 200.0, 42.0            # degrees: from the south-south-west
RELOAD = 25                             # views per page load
RESTART = 100                           # views per browser: the scene blobs pile up in the driver process
GROUPS = ("roads/surfaces", "roads/markings", "roads/guardrails", "roads/fences", "walls", "buildings", "props", "railway",
          # v2.4: the water of the rivers and the rows of the vineyards (meshes; the lake's water blocks apart)
          "level_objects/Water", "level_objects/vegetation/vineyards")

# material name (substring) -> sRGB colour; the first match wins
MAT_COLORS = [
    ("mp_fill_", (-1.0, -1.0, -1.0)),       # the ground restored behind the walls: the orthophoto, as the terrain
    ("asphalt_fresh", (0.23, 0.23, 0.24)), ("mp_road_asphalt", (0.36, 0.36, 0.37)),
    ("hard_asphalt", (0.40, 0.40, 0.40)), ("sidewalk", (0.56, 0.56, 0.55)), ("island", (0.62, 0.62, 0.58)),
    ("road_wall", (0.56, 0.51, 0.45)), ("gravel", (0.64, 0.59, 0.49)), ("_dirt", (0.55, 0.45, 0.33)),
    ("_sett", (0.55, 0.55, 0.53)), ("_cobble", (0.56, 0.54, 0.50)),
    ("path_paved", (0.46, 0.46, 0.45)), ("parapet", (0.74, 0.73, 0.70)), ("paint_yellow", (0.93, 0.78, 0.2)),
    ("paint_red", (0.75, 0.2, 0.18)), ("paint", (0.96, 0.96, 0.94)), ("guardrail", (0.80, 0.81, 0.82)),
    ("chainlink", (0.55, 0.58, 0.55)), ("fence", (0.5, 0.5, 0.5)), ("wall_stone_top", (0.70, 0.69, 0.66)),
    ("wall_stone", (0.60, 0.55, 0.48)), ("bld_roof", (0.58, 0.36, 0.30)), ("bld", (0.86, 0.83, 0.77)),
    ("rail_head", (0.62, 0.62, 0.63)), ("rail_steel", (0.33, 0.30, 0.28)), ("sleeper", (0.55, 0.54, 0.51)),
    ("ballast", (0.50, 0.48, 0.45)), ("rail_deck", (0.70, 0.69, 0.66)), ("osm_stop", (0.76, 0.07, 0.11)),
    ("osm_giveway", (0.95, 0.95, 0.95)),
    ("pole", (0.55, 0.56, 0.58)), ("sign", (0.9, 0.9, 0.92)), ("delineator_black", (0.1, 0.1, 0.1)),
    ("delineator", (0.95, 0.95, 0.95)), ("cabinet", (0.6, 0.6, 0.55)), ("backdrop", (0.35, 0.42, 0.28)),
    # v2.8 lake (patch_lake.py): the colours of its materials
    ("pier_deck", (0.50, 0.44, 0.36)), ("pier_beam", (0.30, 0.25, 0.19)), ("pier_float", (0.16, 0.17, 0.17)),
    ("pier_pile", (0.42, 0.43, 0.44)), ("boat_white", (0.90, 0.90, 0.88)), ("boat_blue", (0.08, 0.16, 0.32)),
    ("boat_grey", (0.50, 0.52, 0.54)), ("boat_beige", (0.72, 0.66, 0.54)), ("boat_dark", (0.08, 0.08, 0.09)),
    ("boat_metal", (0.75, 0.76, 0.77)), ("boat_inside", (0.78, 0.78, 0.76)),
    # v2.8 house details (patch_house_details.py)
    ("house_zinc", (0.60, 0.61, 0.60)), ("house_copper", (0.47, 0.30, 0.20)), ("house_metal", (0.70, 0.71, 0.72)),
    ("house_dish", (0.86, 0.86, 0.84)),
]
CONIFER = ("fir", "pine", "spruce", "larch", "cypress", "conifer")
# m, height at scale 1 of the game models drawn as posts (measured on the cantonal road: dati/lamps.json and
# the wooden poles of props.py); the others are drawn 4 m high
POST_HEIGHT = {"italy_light_single": 8.75, "electric_pole_wood_old_01": 10.05}
# sRGB colour of every terrain layer (terrain.TERRAIN_MATS; the verges as their meadow): the ground where
# there is no orthophoto in WORK (a level checked on a machine without the downloads, v2.8), when the level
# has no base texture for the layer (Level._layer_colors takes the median of those first)
LAYER_COLORS = {"Grass": (0.40, 0.50, 0.27), "GardenGrass": (0.37, 0.49, 0.26), "ForestFloor": (0.33, 0.29, 0.21),
                "ForestFloor2": (0.36, 0.32, 0.23), "Asphalt": (0.36, 0.36, 0.37), "Concrete": (0.55, 0.55, 0.53),
                "Gravel": (0.58, 0.55, 0.48), "Rock": (0.50, 0.48, 0.45), "Mud": (0.36, 0.31, 0.25),
                "Moss": (0.35, 0.42, 0.25), "GrassVerge": (0.40, 0.50, 0.27), "GardenGrassVerge": (0.37, 0.49, 0.26)}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;background:#000}canvas{display:block}</style></head><body><canvas id="c"></canvas>
<script type="module">
import * as THREE from './three.module.js';
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({canvas, antialias: true, preserveDrawingBuffer: true});
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
let scene = null;
const T = {f4: Float32Array, u1: Uint8Array, u4: Uint32Array};
const texCache = new Map();                         // textures of the level materials, loaded once
async function getTex(name, info) {
  if (texCache.has(name)) return texCache.get(name);
  const buf = await (await fetch('http://r3d.local/tex/' + name)).arrayBuffer();
  const t = new THREE.DataTexture(new Uint8Array(buf), info.w, info.h, THREE.RGBAFormat);
  t.colorSpace = info.srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = true; t.anisotropy = 8; t.needsUpdate = true;
  texCache.set(name, t);
  return t;
}
function dispose(s) {
  s.traverse(o => {
    if (o.isInstancedMesh) o.dispose();             // its instance buffers
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (o.material.map && !o.material.userData.cached) o.material.map.dispose();
      o.material.dispose();
    }
  });
  renderer.renderLists.dispose();
}
function geom(A, pos, extra) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(A(pos), 3));
  return g;
}
window.renderView = async function (url) {
  const buf = await (await fetch(url)).arrayBuffer();
  const hl = new DataView(buf).getUint32(0, true);
  const H = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl)));
  const A = k => { const d = H.arrays[k]; return new T[d.t](buf, d.o, d.n); };
  if (scene) dispose(scene);
  scene = new THREE.Scene();
  scene.background = new THREE.Color().setRGB(...H.sky, THREE.SRGBColorSpace);
  if (H.fog) scene.fog = new THREE.Fog(scene.background.clone(), H.fog[0], H.fog[1]);
  const hemi = new THREE.HemisphereLight(0xdfe8f2, 0x6a5a45, H.hemi);
  hemi.position.set(0, 0, 1);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff3e2, H.sun);
  sun.position.set(...H.sunPos);
  sun.target.position.set(...H.sunTarget);
  scene.add(sun, sun.target);
  sun.castShadow = true;
  sun.shadow.mapSize.set(H.shadowMap, H.shadowMap);
  const sc = sun.shadow.camera;
  sc.left = -H.shadowR; sc.right = H.shadowR; sc.top = H.shadowR; sc.bottom = -H.shadowR;
  sc.near = 1; sc.far = H.shadowFar;
  sun.shadow.bias = -0.0008; sun.shadow.normalBias = 0.12;
  for (const t of H.terrains) {
    const g = geom(A, t.pos);
    g.setAttribute('uv', new THREE.BufferAttribute(A(t.uv), 2));
    g.setIndex(new THREE.BufferAttribute(A(t.idx), 1));
    g.computeVertexNormals();
    const tex = new THREE.DataTexture(A(t.tex), t.tw, t.th, THREE.RGBAFormat);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.minFilter = THREE.LinearMipmapLinearFilter; tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = true; tex.anisotropy = 8; tex.needsUpdate = true;
    const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({map: tex}));
    m.receiveShadow = true; m.castShadow = t.cast;
    scene.add(m);
  }
  for (const s of H.soups) {
    const g = geom(A, s.pos);
    g.setAttribute('color', new THREE.BufferAttribute(A(s.col), 3, true));
    if (s.nrm) g.setAttribute('normal', new THREE.BufferAttribute(A(s.nrm), 3));
    else g.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({vertexColors: true, side: THREE.DoubleSide});
    if (s.offset) { mat.polygonOffset = true; mat.polygonOffsetFactor = -1; mat.polygonOffsetUnits = -2; }
    const m = new THREE.Mesh(g, mat);
    m.castShadow = s.cast; m.receiveShadow = true;
    scene.add(m);
  }
  for (const s of (H.tsoups || [])) {                // meshes with the textures of their material
    const g = geom(A, s.pos);
    g.setAttribute('uv', new THREE.BufferAttribute(A(s.uv), 2));
    g.setAttribute('color', new THREE.BufferAttribute(A(s.col), 3, true));
    g.computeVertexNormals();
    // one side, as in the game, unless the material is double sided (v2.4)
    const opt = {map: await getTex(s.tex, s.texInfo), vertexColors: true,
                 side: s.double ? THREE.DoubleSide : THREE.FrontSide,
                 roughness: s.rough, metalness: 0.0};
    if (s.nrm) { opt.normalMap = await getTex(s.nrm, s.nrmInfo); opt.normalScale = new THREE.Vector2(1, 1); }
    if (s.alpha) opt.alphaTest = 0.43;
    const mat = new THREE.MeshStandardMaterial(opt);
    mat.userData.cached = true;
    if (s.offset) { mat.polygonOffset = true; mat.polygonOffsetFactor = -1; mat.polygonOffsetUnits = -2; }
    const m = new THREE.Mesh(g, mat);
    m.castShadow = !s.alpha; m.receiveShadow = true;
    scene.add(m);
  }
  for (const inst of H.instances) {
    let g;
    if (inst.shape === 'cone') g = new THREE.ConeGeometry(1, 1, 7, 1);
    else if (inst.shape === 'trunk') g = new THREE.CylinderGeometry(1, 1, 1, 5, 1);
    else if (inst.shape === 'box') g = new THREE.BoxGeometry(1, 1, 1);
    else if (inst.shape === 'crown0') g = new THREE.IcosahedronGeometry(1, 0);
    else g = new THREE.IcosahedronGeometry(1, 1);
    g.rotateX(Math.PI / 2);
    if (inst.shape === 'cone' || inst.shape === 'trunk' || inst.shape === 'box') g.translate(0, 0, 0.5);
    const mat = new THREE.MeshLambertMaterial({color: 0xffffff});
    const n = H.arrays[inst.m].n / 16;
    const m = new THREE.InstancedMesh(g, mat, n);
    m.instanceMatrix = new THREE.InstancedBufferAttribute(A(inst.m), 16);
    m.instanceColor = new THREE.InstancedBufferAttribute(A(inst.c), 3);
    m.castShadow = true; m.receiveShadow = true;
    m.frustumCulled = false;
    scene.add(m);
  }
  for (const w of H.water) {
    const g = new THREE.PlaneGeometry(w[2] - w[0], w[3] - w[1]);
    g.translate(0.5 * (w[0] + w[2]), 0.5 * (w[1] + w[3]), w[4]);
    const m = new THREE.Mesh(g, new THREE.MeshPhongMaterial({color: new THREE.Color().setRGB(0.16, 0.30, 0.36, THREE.SRGBColorSpace),
      transparent: true, opacity: 0.88, shininess: 90, specular: 0x555555}));
    m.receiveShadow = true;
    scene.add(m);
  }
  let cam;
  const c = H.camera;
  if (c.kind === 'top') {
    cam = new THREE.OrthographicCamera(-c.w / 2, c.w / 2, c.h / 2, -c.h / 2, 1, 20000);
    cam.up.set(0, 1, 0);
    cam.position.set(c.x, c.y, c.z);
    cam.lookAt(c.x, c.y, c.z - 100);
  } else {
    cam = new THREE.PerspectiveCamera(c.fov, H.W / H.H, c.near, c.far);
    cam.up.set(0, 0, 1);
    cam.position.set(...c.pos);
    cam.lookAt(...c.target);
  }
  renderer.setSize(H.W, H.H, false);
  renderer.render(scene, cam);
  return canvas.toDataURL('image/jpeg', H.quality);
};
window.ready = true;
</script></body></html>"""


def srgb_to_lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def mat_color(name):
    n = name.lower()
    for k, c in MAT_COLORS:
        if k in n:
            return c
    return (0.6, 0.6, 0.6)


class Camera(dict):
    @staticmethod
    def look(pos, target, fov=62.0, near=0.3, far=9000.0):
        return Camera(kind="persp", pos=[float(v) for v in pos], target=[float(v) for v in target], fov=fov,
                      near=near, far=far)

    @staticmethod
    def driver(x, y, z, heading, eye=1.5, pitch=-4.0, fov=68.0):
        """At the eye height above (x, y, z) looking along heading (radians from +x, math angle)."""
        d = np.array([math.cos(heading), math.sin(heading), math.tan(math.radians(pitch))])
        p = np.array([x, y, z + eye])
        return Camera.look(p, p + 50 * d, fov=fov)

    @staticmethod
    def orbit(tx, ty, tz, dist, azimuth, elevation, fov=55.0):
        """Looking at (tx, ty, tz) from dist m away, from the compass azimuth (deg, 0 = from the
        north) and elevation (deg above the horizon)."""
        a, e = math.radians(azimuth), math.radians(elevation)
        p = (tx + dist * math.cos(e) * math.sin(a), ty + dist * math.cos(e) * math.cos(a), tz + dist * math.sin(e))
        return Camera.look(p, (tx, ty, tz), fov=fov)

    @staticmethod
    def top(x0, y0, x1, y1, px_per_m=1.0):
        return Camera(kind="top", x0=x0, y0=y0, x1=x1, y1=y1, W=int(round((x1 - x0) * px_per_m)),
                      H=int(round((y1 - y0) * px_per_m)))

    def region(self, near_r):
        """(x0, y0, x1, y1) of the detailed scene of the view."""
        if self["kind"] == "top":
            return self["x0"], self["y0"], self["x1"], self["y1"]
        p, t = np.array(self["pos"]), np.array(self["target"])
        d = t[:2] - p[:2]
        d = d / max(np.linalg.norm(d), 1e-9)
        c = p[:2] + d * near_r * 0.55
        return c[0] - near_r, c[1] - near_r, c[0] + near_r, c[1] + near_r


def _read_dae_parts(path):
    """[(material, triangles (k, 3, 3), uvs (k, 3, 2) or None, vertex colours (k, 3, 3) or None)] of a DAE."""
    s = open(path, encoding="utf-8").read()

    def arr(i):
        m = re.search(r'<float_array id="%s" count="\d+">([^<]*)</float_array>' % i, s)
        return np.array(m.group(1).split(), np.float64) if m else None
    V = arr("g-pa")
    if V is None:
        return []
    V = V.reshape(-1, 3)
    TC = arr("g-ta")
    TC = TC.reshape(-1, 2) if TC is not None else None
    C = arr("g-ca")
    C = C.reshape(-1, 4) if C is not None else None
    out = []
    for m in re.finditer(r'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', s, re.S):
        nin = m.group(2).count("<input")
        idx = np.array(m.group(3).split(), np.int64).reshape(-1, nin)
        t = V[idx[:, 0]].reshape(-1, 3, 3)
        uv = TC[idx[:, 2]].reshape(-1, 3, 2) if TC is not None and nin > 2 else None
        col = C[idx[:, 3], :3].reshape(-1, 3, 3) if C is not None and nin > 3 else None
        out.append((m.group(1), t.astype(np.float32), uv, col))
    return out


def _read_dae(path):
    """Triangles (k, 3, 3) float64 in the DAE frame, their sRGB vertex colours (k, 3, 3) (from the
    material or the vertex colours) and the normals of their corners (k, 3, 3) as the DAE has them."""
    s = open(path, encoding="utf-8").read()

    def arr(i):
        m = re.search(r'<float_array id="%s" count="\d+">([^<]*)</float_array>' % i, s)
        return np.array(m.group(1).split(), np.float64) if m else None
    V = arr("g-pa")
    if V is None:
        return np.zeros((0, 3, 3)), np.zeros((0, 3, 3), np.float32), np.zeros((0, 3, 3), np.float32)
    V = V.reshape(-1, 3)
    C = arr("g-ca")
    C = C.reshape(-1, 4) if C is not None else None
    N = arr("g-na")
    N = N.reshape(-1, 3) if N is not None else None
    tris, cols, nrms = [], [], []
    for m in re.finditer(r'<triangles material="([^"]*)-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', s, re.S):
        nin = m.group(2).count("<input")
        idx = np.array(m.group(3).split(), np.int64).reshape(-1, nin)
        t = V[idx[:, 0]].reshape(-1, 3, 3)
        base = np.array(mat_color(m.group(1)))
        if C is not None and nin > 3:
            col = C[idx[:, 3], :3].reshape(-1, 3, 3) * base[None, None] / max(base.max(), 1e-6) \
                if "bld" not in m.group(1) else C[idx[:, 3], :3].reshape(-1, 3, 3)
        else:
            col = np.broadcast_to(base, t.shape)
        tris.append(t)
        cols.append(np.asarray(col, np.float32))
        nrms.append(N[idx[:, 1]].reshape(-1, 3, 3) if N is not None and nin > 1 else np.zeros(t.shape))
    if not tris:
        return np.zeros((0, 3, 3), np.float32), np.zeros((0, 3, 3), np.float32), np.zeros((0, 3, 3), np.float32)
    return np.concatenate(tris).astype(np.float32), np.concatenate(cols), np.concatenate(nrms).astype(np.float32)


class Level:
    """What of a built level the renderer draws, read once (the meshes on first use)."""

    def __init__(self, lv):
        self.lv = lv
        blk = [o for o in self._items("level_objects/terrain") if o.get("class") == "TerrainBlock"][0]
        self.tx0, self.ty0, self.tz0 = blk["position"]
        self.maxh = float(blk["maxHeight"])
        self.sq = float(blk.get("squareSize", 1))
        path = os.path.join(lv, blk.get("terrainFile", "theTerrain.ter").split("/")[-1])
        if not os.path.exists(path):
            path = os.path.join(lv, "theTerrain.ter")
        n = int(np.fromfile(path, "<u4", count=1, offset=1)[0])
        self.n = n
        self.ter_path = path
        self.q = np.memmap(path, "<u2", "r", offset=5, shape=(n, n))          # row 0 = south
        self.statics = []                                                      # (group, shape, position)
        for g in GROUPS + ("level_objects/backdrop",):
            for dp, _, fs in os.walk(os.path.join(lv, "main", "MissionGroup", *g.split("/"))):
                if "items.level.json" in fs:
                    for o in self._read(os.path.join(dp, "items.level.json")):
                        if o.get("class") == "TSStatic" and "shapeName" in o:
                            self.statics.append((g, o["shapeName"], np.array(o.get("position", [0, 0, 0]), float),
                                                 o.get("scale", [1, 1, 1])))
        self.water = []
        for o in self._items("level_objects/Water"):
            if o.get("class") == "WaterBlock":
                x, y, z = o["position"]
                sx, sy, _ = o.get("scale", [1, 1, 1])
                self.water.append((x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2, z))
            elif o.get("class") == "WaterPlane":
                self.water.append((-1e5, -1e5, 1e5, 1e5, o["position"][2]))
        self.forest = self._forest()
        self._dae = {}
        self._parts = {}
        self._ortho = None
        self.materials = {}                                   # name -> first stage + flags, of the level's materials
        for dp, _, fs in os.walk(lv):
            for fn in fs:
                if fn.endswith(".materials.json"):
                    try:
                        for k, m in json.load(open(os.path.join(dp, fn), encoding="utf-8")).items():
                            if isinstance(m, dict) and m.get("class") == "Material":
                                st = dict((m.get("Stages") or [{}])[0])
                                st["_alpha"] = bool(m.get("alphaTest"))
                                st["_double"] = bool(m.get("doubleSided"))
                                self.materials[m.get("name", k)] = st
                    except (ValueError, OSError):
                        pass

    def _read(self, f):
        return [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]

    def _items(self, group):
        f = os.path.join(self.lv, "main", "MissionGroup", *group.split("/"), "items.level.json")
        return self._read(f) if os.path.exists(f) else []

    def _forest(self):
        """x, y, z, height, crown radius, kind (0 broadleaf, 1 conifer, 2 shrub) of every forest item."""
        b = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati",
                                        "asset_bounds.json")))
        size = {}
        for k, v in b.items():
            if k.startswith("_"):
                continue
            lo, hi = np.array(v[0]), np.array(v[1])
            size[os.path.basename(k)[:-4]] = (hi[2] - max(lo[2], -0.5), 0.25 * ((hi[0] - lo[0]) + (hi[1] - lo[1])))
        rows = []
        for f in glob.glob(os.path.join(self.lv, "forest", "*.forest4.json")):
            name = os.path.basename(f)[:-len(".forest4.json")]
            h, r = size.get(name, (10.0, 3.0))
            kind = 2 if ("bush" in name or "hedge" in name) else (1 if any(c in name for c in CONIFER) else 0)
            for o in self._read(f):
                s = float(o.get("scale", 1.0))
                rows.append((o["pos"][0], o["pos"][1], o["pos"][2], h * s, r * s, kind))
        return np.array(rows, np.float64).reshape(-1, 6)

    def heights(self, r0, r1, c0, c1, step=1):
        q = np.asarray(self.q[r0:r1:step, c0:c1:step], np.float64)
        return self.tz0 + q / 65535.0 * self.maxh

    def ortho(self):
        if self._ortho is None and not os.path.exists(os.path.join(WORK, "ortho.tif")):
            self._ortho = self._layer_colors()
        if self._ortho is None:
            import rasterio
            from config import E0, N0, K
            with rasterio.open(os.path.join(WORK, "ortho.tif")) as s:
                o = s.read()
                inv = ~s.transform

            def fn(x, y):
                c, r = inv * (E0 + x * K, N0 + y * K)
                c = np.clip(np.floor(c).astype(np.int64), 0, o.shape[2] - 1)
                r = np.clip(np.floor(r).astype(np.int64), 0, o.shape[1] - 1)
                return o[:, r, c]
            self._ortho = fn
        return self._ortho

    def _layer_colors(self):
        """In place of the orthophoto: (x, y) -> sRGB uint8 (3, k), the colour of the terrain layer at the
        nearest terrain vertex: the median of its base colour texture in the level, else LAYER_COLORS."""
        n = self.n
        f = self.ter_path
        lay = np.memmap(f, np.uint8, "r", offset=5 + 2 * n * n, shape=(n, n))
        tail = open(f, "rb").read()[5 + 3 * n * n:]
        names, o = [], 4
        for _ in range(int(np.frombuffer(tail[:4], "<u4")[0])):
            names.append(tail[o + 1:o + 1 + tail[o]].decode("utf-8"))
            o += 1 + tail[o]
        base = {}
        f_mat = os.path.join(self.lv, "art", "terrains", "main.materials.json")
        if os.path.exists(f_mat):
            from PIL import Image
            for m in json.load(open(f_mat, encoding="utf-8")).values():
                tex = self.local_file(m.get("baseColorBaseTex")) if m.get("class") == "TerrainMaterial" else None
                if tex:
                    a = np.asarray(Image.open(tex).convert("RGB")).reshape(-1, 3)
                    base[m["internalName"]] = np.median(a, 0)
        lut = np.array([base[m] if m in base else [round(255 * v) for v in LAYER_COLORS.get(m, (0.4, 0.45, 0.3))]
                        for m in names], np.uint8)

        def fn(x, y):
            c = np.clip(np.round((np.asarray(x) - self.tx0) / self.sq).astype(np.int64), 0, n - 1)
            r = np.clip(np.round((np.asarray(y) - self.ty0) / self.sq).astype(np.int64), 0, n - 1)
            return lut[lay[r, c]].T
        return fn

    def parts(self, shape):
        if shape not in self._parts:
            path = os.path.join(self.lv, *shape.split("/")[3:])
            self._parts[shape] = _read_dae_parts(path) if os.path.exists(path) else []
        return self._parts[shape]

    def local_file(self, ref):
        """Path in the level folder of a texture the materials refer to (None for vanilla files)."""
        pref = "/levels/" + os.path.basename(os.path.normpath(self.lv)) + "/"
        if not isinstance(ref, str) or not ref.lower().startswith(pref.lower()):
            return None
        f = os.path.join(self.lv, *ref[len(pref):].split("/"))
        return f if os.path.exists(f) else None

    def dae(self, shape):
        if shape not in self._dae:
            path = os.path.join(self.lv, *shape.split("/")[3:])
            self._dae[shape] = _read_dae(path) if os.path.exists(path) else None
        return self._dae[shape]


class Renderer:
    def __init__(self, lv, W=1280, H=720, quality=0.88, textured=False, dae_normals=False):
        """textured: the meshes whose materials have textures in the level folder (the buildings of
        v2.2) are drawn with them (colour, opacity, normal map), the rest in the colours of MAT_COLORS.
        dae_normals: the untextured meshes are lit with the normals of their DAE, as in the game (v2.8:
        patch_wall_fill.py), instead of one normal per triangle."""
        self.level = Level(lv)
        self.W, self.H, self.quality = W, H, quality
        self.textured = textured
        self.dae_normals = dae_normals
        self._tex = {}
        if not os.path.exists(THREE):
            import requests
            open(THREE, "wb").write(requests.get(THREE_URL, timeout=60).content)
        self._blob = b""
        self._start()

    def _start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = os.environ.get("MAGLIASO_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium")
                                                      else None)
        try:
            self._browser = self._pw.chromium.launch(args=ARGS)
        except Exception:
            if not exe:
                raise
            self._browser = self._pw.chromium.launch(args=ARGS, executable_path=exe)
        self.page = self._browser.new_page()
        three = open(THREE, "rb").read()

        def serve(route):
            u = route.request.url
            if u.endswith("/index.html"):
                route.fulfill(body=PAGE, content_type="text/html")
            elif u.endswith("three.module.js"):
                route.fulfill(body=three, content_type="application/javascript")
            elif "/view" in u:
                route.fulfill(body=self._blob, content_type="application/octet-stream")
            elif "/tex/" in u:
                route.fulfill(body=self._tex[u.rsplit("/", 1)[1]][0], content_type="application/octet-stream")
            else:
                route.fulfill(status=404, body="")
        self.page.route("http://r3d.local/**", serve)
        self.page.goto("http://r3d.local/index.html")
        self.page.wait_for_function("window.ready === true", timeout=60000)
        self._n = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        self._browser.close()
        self._pw.stop()

    # -------------------------------------------------------------- scene of one view
    def _terrain(self, x0, y0, x1, y1, step, origin, texres, lower=0.0, cast=True):
        L = self.level
        c0 = max(int(math.floor((x0 - L.tx0) / L.sq)), 0)
        c1 = min(int(math.ceil((x1 - L.tx0) / L.sq)) + 1, L.n)
        r0 = max(int(math.floor((y0 - L.ty0) / L.sq)), 0)
        r1 = min(int(math.ceil((y1 - L.ty0) / L.sq)) + 1, L.n)
        if c1 - c0 < 2 or r1 - r0 < 2:
            return None
        h = L.heights(r0, r1, c0, c1, step) - lower
        ny, nx = h.shape
        xs = L.tx0 + (c0 + np.arange(nx) * step) * L.sq
        ys = L.ty0 + (r0 + np.arange(ny) * step) * L.sq
        X, Y = np.meshgrid(xs, ys)
        pos = np.stack([X - origin[0], Y - origin[1], h - origin[2]], -1).reshape(-1, 3).astype(np.float32)
        u = (X - xs[0]) / max(xs[-1] - xs[0], 1e-9)
        v = (Y - ys[0]) / max(ys[-1] - ys[0], 1e-9)
        uv = np.stack([u, v], -1).reshape(-1, 2).astype(np.float32)
        i = np.arange(ny * nx, dtype=np.uint32).reshape(ny, nx)
        a, b, c, d = i[:-1, :-1], i[:-1, 1:], i[1:, 1:], i[1:, :-1]
        idx = np.stack([a, b, c, a, c, d], -1).reshape(-1).astype(np.uint32)
        tw = int(min(4096, max(2, round((xs[-1] - xs[0]) / texres))))
        th = int(min(4096, max(2, round((ys[-1] - ys[0]) / texres))))
        tx = np.linspace(xs[0], xs[-1], tw)
        ty = np.linspace(ys[0], ys[-1], th)
        TX, TY = np.meshgrid(tx, ty)
        rgb = L.ortho()(TX.ravel(), TY.ravel()).T.copy()             # (n, 3)
        rgb[(rgb == 0).all(1)] = (96, 108, 80)                       # no orthophoto (Italy)
        tex = np.concatenate([rgb, np.full((tw * th, 1), 255, np.uint8)], 1).astype(np.uint8)
        return dict(pos=pos, uv=uv, idx=idx, tex=tex.reshape(-1), tw=tw, th=th, cast=cast)

    def _soups(self, x0, y0, x1, y1, origin):
        L = self.level
        out = {"mesh": ([], [], []), "paint": ([], [], []), "posts": []}
        far_x0, far_y0, far_x1, far_y1 = x0 - 300, y0 - 300, x1 + 300, y1 + 300
        for g, shape, pos, scale in L.statics:
            if g == "level_objects/backdrop":
                continue
            local = shape.startswith("/levels/") and os.path.exists(os.path.join(L.lv, *shape.split("/")[3:]))
            if not local:
                if x0 < pos[0] < x1 and y0 < pos[1] < y1:
                    h = POST_HEIGHT.get(os.path.basename(shape).rsplit(".", 1)[0], 4.0) * float(np.asarray(scale).ravel()[-1])
                    out["posts"].append((pos, h))
                continue
            whole = np.allclose(pos, 0)
            if not whole and not (far_x0 < pos[0] < far_x1 and far_y0 < pos[1] < far_y1):
                continue
            if self.textured:
                rest = []
                for mat, tri, uv, vc in L.parts(shape):
                    info = self.texture(mat) if uv is not None else None
                    if info is None:
                        rest.append(mat)
                        continue
                    tw = tri + pos
                    c = tw.mean(1)
                    m = (c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1)
                    if not m.any():
                        continue
                    col = vc[m] if vc is not None else np.ones((int(m.sum()), 3, 3), np.float32)
                    out.setdefault("textured", []).append((mat, info, tw[m] - origin, uv[m], col))
                if not rest:
                    continue
            d = L.dae(shape)
            if d is None or not len(d[0]):
                continue
            tri, col, nrm = d
            if self.textured:                          # the untextured materials of the shape only
                keep = np.zeros(len(tri), bool)
                o = 0
                for mat, t_, uv_, vc_ in L.parts(shape):
                    if mat in rest:
                        keep[o:o + len(t_)] = True
                    o += len(t_)
                tri, col, nrm = tri[keep], col[keep], nrm[keep]
            tw = tri + pos
            c = tw.mean(1)
            m = (c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1)
            if not m.any():
                continue
            ground = col[:, 0, 0] < 0
            if ground.any():                                 # coloured like the terrain around it
                col = np.array(col, np.float32)
                V = tw[ground].reshape(-1, 3)
                rgb = L.ortho()(V[:, 0], V[:, 1]).T.astype(np.float32) / 255.0
                col[ground] = np.nan_to_num(rgb, nan=0.4).reshape(-1, 3, 3)
            key = "paint" if "markings" in shape else "mesh"
            out[key][0].append(tw[m] - origin)
            out[key][1].append(col[m])
            out[key][2].append(nrm[m])
        return out

    def texture(self, mat):
        """(name, info) of the colour texture (with the opacity map as alpha) and of the normal map of a
        level material, loaded once; None where it has no texture in the level folder."""
        st = self.level.materials.get(mat)
        if not st:
            return None
        cf = self.level.local_file(st.get("baseColorMap"))
        if cf is None:
            return None
        from PIL import Image
        out = []
        for key, f, srgb, limit in (("c", cf, True, 2048), ("n", self.level.local_file(st.get("normalMap")), False, 1024)):
            if f is None:
                out.append((None, None))
                continue
            name = f"{mat}_{key}"
            if name not in self._tex:
                im = Image.open(f).convert("RGBA")
                if key == "c":
                    of = self.level.local_file(st.get("opacityMap"))
                    if of:
                        im.putalpha(Image.open(of).convert("L").resize(im.size))
                if max(im.size) > limit:
                    k = limit / max(im.size)
                    im = im.resize((max(1, int(im.size[0] * k)), max(1, int(im.size[1] * k))), Image.LANCZOS)
                a = np.asarray(im)[::-1].copy()                            # row 0 = bottom (v = 0)
                self._tex[name] = (a.tobytes(), {"w": im.size[0], "h": im.size[1], "srgb": srgb})
            out.append((name, self._tex[name][1]))
        rough = float(st.get("roughnessFactor", 0.85)) if "roughnessFactor" in st else 0.85
        return {"tex": out[0][0], "texInfo": out[0][1], "nrm": out[1][0], "nrmInfo": out[1][1],
                "alpha": bool(st.get("_alpha")), "double": bool(st.get("_double")), "rough": rough}

    def _backdrop(self, cx, cy, radius, origin):
        L = self.level
        for g, shape, pos, scale in L.statics:
            if g != "level_objects/backdrop":
                continue
            if self.textured:
                rest = []
                for mat, tri, uv, vc in L.parts(shape):
                    info = self.texture(mat) if uv is not None else None
                    if info is None:
                        rest.append(mat)
                        continue
                    tw = tri + pos
                    c = tw.mean(1)
                    m = (c[:, 0] > x0) & (c[:, 0] < x1) & (c[:, 1] > y0) & (c[:, 1] < y1)
                    if not m.any():
                        continue
                    col = vc[m] if vc is not None else np.ones((int(m.sum()), 3, 3), np.float32)
                    out.setdefault("textured", []).append((mat, info, tw[m] - origin, uv[m], col))
                if not rest:
                    continue
            d = L.dae(shape)
            if d is None or not len(d[0]):
                continue
            tri, col = d[0], d[1]
            if self.textured:                          # the untextured materials of the shape only
                keep = np.zeros(len(tri), bool)
                o = 0
                for mat, t_, uv_, vc_ in L.parts(shape):
                    if mat in rest:
                        keep[o:o + len(t_)] = True
                    o += len(t_)
                tri, col = tri[keep], col[keep]
            tw = tri + pos
            c = tw.mean(1)
            m = np.hypot(c[:, 0] - cx, c[:, 1] - cy) < radius
            return tw[m] - origin, col[m]
        return None

    def _trees(self, x0, y0, x1, y1, origin, eye=None):
        """Instances of trunks, cones and crowns; seen from `eye`, the trunks only within 250 m and
        rounder crowns within 150 m."""
        F = self.level.forest
        if not len(F):
            return []
        m = (F[:, 0] > x0) & (F[:, 0] < x1) & (F[:, 1] > y0) & (F[:, 1] < y1)
        F = F[m]
        dist = np.hypot(F[:, 0] - eye[0], F[:, 1] - eye[1]) if eye is not None else np.zeros(len(F))
        rng = np.random.default_rng(7)
        out = []

        def mats(x, y, z, sx, sy, sz):
            M = np.zeros((len(x), 16), np.float32)
            M[:, 0], M[:, 5], M[:, 10], M[:, 15] = sx, sy, sz, 1
            M[:, 12], M[:, 13], M[:, 14] = x - origin[0], y - origin[1], z - origin[2]
            return M

        def colors(base, n, var=0.12):
            c = np.clip(np.asarray(base)[None] * (1 + var * rng.standard_normal((n, 1))), 0, 1)
            return srgb_to_lin(c).astype(np.float32)
        x, y, z, h, r, k = F.T
        tree = (k < 2) & (dist < 250)
        if tree.any():
            t = tree
            out.append(("trunk", mats(x[t], y[t], z[t] - 0.3, 0.012 * h[t] + 0.12, 0.012 * h[t] + 0.12, 0.55 * h[t] + 0.3),
                        colors((0.33, 0.26, 0.2), t.sum(), 0.05)))
        c = k == 1
        if c.any():
            rr = np.maximum(r[c], 0.9)
            out.append(("cone", mats(x[c], y[c], z[c] + 0.18 * h[c], rr, rr, 0.84 * h[c]),
                        colors((0.17, 0.30, 0.16), c.sum())))
        for shape, b in (("crown", (k == 0) & (dist < 150)), ("crown0", (k == 0) & (dist >= 150))):
            if b.any():
                rr = np.maximum(r[b], 1.0)
                hh = np.maximum(0.33 * h[b], 1.0)
                out.append((shape, mats(x[b], y[b], z[b] + h[b] - hh, rr, rr, hh),
                            colors((0.29, 0.42, 0.18), b.sum())))
        s = k == 2
        if s.any():
            out.append(("crown", mats(x[s], y[s], z[s] + 0.5 * h[s], np.maximum(r[s], 0.4), np.maximum(r[s], 0.4),
                                      0.5 * h[s]), colors((0.27, 0.45, 0.2), s.sum())))
        return out

    def _pack(self, header, arrays):
        blobs, off, meta = [], 0, {}
        for k, a in arrays.items():
            a = np.ascontiguousarray(a)
            t = {np.dtype(np.float32): "f4", np.dtype(np.uint8): "u1", np.dtype(np.uint32): "u4"}[a.dtype]
            meta[k] = {"t": t, "n": int(a.size), "o": 0, "b": a.tobytes()}
        header["arrays"] = {k: {"t": v["t"], "n": v["n"], "o": 0} for k, v in meta.items()}
        # offsets after the header (header length is fixed by padding it)
        head = json.dumps(header).encode()
        base = 4 + len(head) + 4096
        base += (-base) % 16
        off = base
        for k, v in meta.items():
            header["arrays"][k]["o"] = off
            off += len(v["b"])
            off += (-off) % 16
        head = json.dumps(header).encode()
        assert 4 + len(head) <= base, "header grew"
        out = bytearray(off)
        out[0:4] = np.uint32(base - 4).tobytes()
        out[4:4 + len(head)] = head
        out[4 + len(head):base] = b" " * (base - 4 - len(head))
        for k, v in meta.items():
            o = header["arrays"][k]["o"]
            out[o:o + len(v["b"])] = v["b"]
        return bytes(out)

    def scene(self, cam, near=450.0, far=3500.0, trees=True, W=None, H=None):
        L = self.level
        W, H = W or self.W, H or self.H
        x0, y0, x1, y1 = cam.region(near)
        if cam["kind"] == "top":
            cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            W, H = cam["W"], cam["H"]
        else:
            cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        rr = int(np.clip((cy - L.ty0) / L.sq, 0, L.n - 1))
        cc = int(np.clip((cx - L.tx0) / L.sq, 0, L.n - 1))
        oz = float(L.heights(rr, rr + 1, cc, cc + 1)[0, 0])
        origin = np.array([cx, cy, oz])
        arrays, terrains, soups, instances = {}, [], [], []

        def add_terrain(t, name):
            if t is None:
                return
            for k in ("pos", "uv", "idx", "tex"):
                arrays[f"{name}_{k}"] = t[k]
            terrains.append({"pos": f"{name}_pos", "uv": f"{name}_uv", "idx": f"{name}_idx", "tex": f"{name}_tex",
                             "tw": t["tw"], "th": t["th"], "cast": t["cast"]})
        pad = 20.0 if cam["kind"] == "top" else 0.0
        add_terrain(self._terrain(x0 - pad, y0 - pad, x1 + pad, y1 + pad, 1, origin, 2.0), "tn")
        if cam["kind"] != "top":
            step = max(4, int(math.ceil(2 * far / (300 * L.sq))))
            add_terrain(self._terrain(cx - far, cy - far, cx + far, cy + far, step, origin, 8.0, lower=1.0, cast=False),
                        "tf")
            bd = self._backdrop(cx, cy, far * 1.8, origin)
            if bd is not None and len(bd[0]):
                arrays["bd_pos"] = bd[0].reshape(-1).astype(np.float32)
                arrays["bd_col"] = (srgb_to_lin(bd[1]).reshape(-1) * 255).astype(np.uint8)
                soups.append({"pos": "bd_pos", "col": "bd_col", "cast": False, "offset": False})
        S = self._soups(x0 - pad, y0 - pad, x1 + pad, y1 + pad, origin)
        tsoups = []
        groups = {}
        for mat, info, tw, uv, col in S.get("textured", []):
            groups.setdefault(mat, (info, [], [], []))
            groups[mat][1].append(tw); groups[mat][2].append(uv); groups[mat][3].append(col)
        for j, (mat, (info, tws, uvs, cols)) in enumerate(groups.items()):
            arrays[f"ts{j}_pos"] = np.concatenate(tws).reshape(-1).astype(np.float32)
            arrays[f"ts{j}_uv"] = np.concatenate(uvs).reshape(-1).astype(np.float32)
            arrays[f"ts{j}_col"] = (srgb_to_lin(np.clip(np.concatenate(cols), 0, 1)).reshape(-1) * 255).astype(np.uint8)
            tsoups.append(dict(pos=f"ts{j}_pos", uv=f"ts{j}_uv", col=f"ts{j}_col", **info,
                               offset="markings" in mat or "openings" in mat or "plinth" in mat))
        for key, off in (("mesh", False), ("paint", True)):
            tris, cols, nrms = S[key]
            if tris:
                arrays[f"{key}_pos"] = np.concatenate(tris).reshape(-1).astype(np.float32)
                arrays[f"{key}_col"] = (srgb_to_lin(np.concatenate(cols)).reshape(-1) * 255).astype(np.uint8)
                soups.append({"pos": f"{key}_pos", "col": f"{key}_col", "cast": key == "mesh", "offset": off})
                if self.dae_normals:                   # the normals the game lights the meshes with
                    arrays[f"{key}_nrm"] = np.concatenate(nrms).reshape(-1).astype(np.float32)
                    soups[-1]["nrm"] = f"{key}_nrm"
        if S["posts"]:
            P = np.array([p for p, _ in S["posts"]])
            M = np.zeros((len(P), 16), np.float32)
            M[:, 0], M[:, 5], M[:, 10], M[:, 15] = 0.25, 0.25, np.array([h for _, h in S["posts"]]), 1
            M[:, 12:15] = P - origin
            arrays["posts_m"] = M.reshape(-1)
            arrays["posts_c"] = np.tile(srgb_to_lin([0.5, 0.5, 0.52]).astype(np.float32), len(P))
            instances.append({"shape": "box", "m": "posts_m", "c": "posts_c"})
        if trees:
            eye = cam["pos"] if cam["kind"] != "top" else None
            for j, (shape, M, C) in enumerate(self._trees(x0 - pad, y0 - pad, x1 + pad, y1 + pad, origin, eye)):
                arrays[f"tree{j}_m"] = M.reshape(-1)
                arrays[f"tree{j}_c"] = C.reshape(-1)
                instances.append({"shape": shape, "m": f"tree{j}_m", "c": f"tree{j}_c"})
        water = [[max(w[0], cx - far) - cx, max(w[1], cy - far) - cy, min(w[2], cx + far) - cx,
                  min(w[3], cy + far) - cy, w[4] - oz] for w in L.water
                 if w[0] < cx + far and w[2] > cx - far and w[1] < cy + far and w[3] > cy - far]
        a, e = math.radians(SUN_AZ), math.radians(SUN_EL)
        sd = np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])
        if cam["kind"] == "top":
            span = max(x1 - x0, y1 - y0)
            focus = np.zeros(3)
            camd = {"kind": "top", "x": 0.0, "y": 0.0, "z": 3000.0, "w": x1 - x0, "h": y1 - y0}
            fog = None
        else:
            p, t = np.array(cam["pos"]) - origin, np.array(cam["target"]) - origin
            d = (t - p) / max(np.linalg.norm(t - p), 1e-9)
            span = 2.0 * min(near, 260.0)
            focus = p + d * 0.5 * span
            camd = {"kind": "persp", "pos": p.tolist(), "target": t.tolist(), "fov": cam["fov"],
                    "near": cam["near"], "far": cam["far"]}
            fog = [600.0, 9000.0]
        header = {"W": int(W), "H": int(H), "quality": self.quality, "sky": list(SKY), "fog": fog,
                  "hemi": 1.25, "sun": 2.6, "sunPos": (focus + sd * 1500).tolist(), "sunTarget": focus.tolist(),
                  "shadowR": 0.75 * span, "shadowFar": 4000.0, "shadowMap": 4096,
                  "terrains": terrains, "soups": soups, "tsoups": tsoups, "instances": instances, "water": water,
                  "camera": camd}
        return self._pack(header, arrays)

    def shot(self, cam, out, **kw):
        self._blob = self.scene(cam, **kw)
        n = self._n + 1
        if n % RESTART == 0:                   # a new browser and driver: their memory only grows
            self.close()
            self._start()
        elif n % RELOAD == 0:                  # a fresh WebGL context now and then (SwiftShader memory)
            self.page.reload()
            self.page.wait_for_function("window.ready === true", timeout=60000)
        self._n = n
        url = self.page.evaluate("u => window.renderView(u)", f"http://r3d.local/view{self._n}.bin")
        data = base64.b64decode(url.split(",", 1)[1])
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        open(out, "wb").write(data)
        return out


if __name__ == "__main__":
    import sys
    from config import LEVEL_DIR
    a = sys.argv[1:]
    with Renderer(LEVEL_DIR) as r:
        r.shot(Camera.look(a[0:3], a[3:6]), a[6])
