"""Files derived from the game install, taken from the released level when the game is missing.

The level build copies a few things out of the BeamNG.drive install (BEAMNG_GAME): grey copies of
vanilla textures for the buildings, the material definitions of the vanilla tree models, the
sizes of those models. A released level (config.REFERENCE_ZIP, e.g. magliaso_pura_v1.1.zip)
already contains all of them; a build without the game (a cloud build of v2.0) takes them from
there. The facade colours measured in the photos (texture_buildings.py, work/facades) are also
recovered from the vertex colours of the released building meshes.
"""
import io, json, os, re, zipfile
import numpy as np
from config import BEAMNG_GAME, REFERENCE_ZIP, LEVEL_NAME

LEVEL = f"levels/{LEVEL_NAME}"


def have_game():
    return os.path.isdir(os.path.join(BEAMNG_GAME, "content"))


def reference():
    if not os.path.exists(REFERENCE_ZIP):
        raise FileNotFoundError(f"neither the game ({BEAMNG_GAME}) nor the reference level ({REFERENCE_ZIP})")
    return zipfile.ZipFile(REFERENCE_ZIP)


def copy(rel, dst):
    """Copy levels/<level>/<rel> of the reference level to dst."""
    with reference() as z:
        data = z.read(f"{LEVEL}/{rel}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(data)


def read_json(rel):
    with reference() as z:
        return json.loads(z.read(f"{LEVEL}/{rel}").decode("utf-8"))


def wall_colors():
    """Wall vertex colour of every building of the reference level: (points (n, 3) world, colours
    (n, 3)) sampled on the plaster walls (the tone measured in the photos, or the default)."""
    pts, cols = [], []
    with reference() as z:
        items = [json.loads(l) for l in z.read(f"{LEVEL}/main/MissionGroup/buildings/items.level.json").decode().splitlines()
                 if l.strip()]
        for it in items:
            rel = it["shapeName"].split("/", 3)[3]
            s = z.read(f"{LEVEL}/{rel}").decode("utf-8")
            pos = np.array(it["position"], np.float64)

            def arr(i):
                m = re.search(r'<float_array id="%s" count="\d+">([^<]*)</float_array>' % i, s)
                return np.array(m.group(1).split(), np.float64) if m else None
            V, C = arr("g-pa"), arr("g-ca")
            if V is None or C is None:
                continue
            V, C = V.reshape(-1, 3) + pos, C.reshape(-1, 4)[:, :3]
            for m in re.finditer(r'<triangles material="bld_plaster-mat" count="\d+">(.*?)<p>([^<]*)</p></triangles>', s, re.S):
                nin = m.group(1).count("<input")
                idx = np.array(m.group(2).split(), np.int64).reshape(-1, nin)
                vi, ci = idx[:, 0], idx[:, 3] if nin > 3 else None
                if ci is None:
                    continue
                pts.append(V[vi[::3]])
                cols.append(C[ci[::3]])
    if not pts:
        return np.zeros((0, 3)), np.zeros((0, 3))
    return np.concatenate(pts), np.concatenate(cols)


def tree_sizes():
    """Height and crown width (m) of the vanilla tree models at scale 1, from the reference level:
    the scale of every tree there and the height/crown measured for it (work/trees.npz of v1.0)."""
    f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "asset_bounds.json")
    return json.load(open(f))
