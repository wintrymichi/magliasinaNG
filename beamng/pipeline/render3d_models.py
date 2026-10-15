"""Stand-ins for the game's own models in the renders of render3d.py (v3.0).

The level places thousands of the game's models: Italy's street lights (italy_light_single, 8.75 m with its arm
along local +x, lamps.py), the wooden poles of the country roads (electric_pole_wood_old_01, 10.05 m at scale 1,
poles.py), Italy's guard rail modules as forest items (italy_guardrails_basic and its two end pieces,
guardrail_mesh.py) and the clutter of street_life.py (bins, skips, drums, pallets, benches, tables, chairs,
umbrellas, planters, hydrants, letter boxes, mirrors, rubbish bags). Their files are not here without the game:
render3d drew them as grey 4 m posts and the guard rails not at all. Here each gets a simple proxy of its real
size (street_life.MODELS and the modules' frame of guardrail_mesh.py), built from boxes, cylinders, cones, tubes
and ellipsoids in the model's own frame (origin on the ground, z up, the front of the models that have one
towards local -y), in plausible colours; render3d draws it, instanced, with each object's position, rotation
matrix and scale. Recognisable, not the game's models.

    geometry(name) -> (triangles (k, 3, 3), vertex normals (k, 3, 3), sRGB colour per triangle (k, 3)) or None
    SHINY: the models drawn with a highlight (galvanised steel)
"""
import math
import numpy as np

# ---------------------------------------------------------------------------------------------- primitives
_STEEL = (0.74, 0.76, 0.77)
_POST_STEEL = (0.60, 0.62, 0.63)
_WOOD = (0.55, 0.40, 0.25)
_DARK = (0.16, 0.16, 0.17)


def _orient(T, N):
    """Triangles turned so that their winding agrees with their vertex normals (counter-clockwise from outside)."""
    g = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    flip = (g * N.mean(1)).sum(1) < 0
    T[flip] = T[flip][:, ::-1]
    N[flip] = N[flip][:, ::-1]
    return T, N


def _part(T, N, col):
    T, N = _orient(np.asarray(T, np.float64), np.asarray(N, np.float64))
    return T, N, np.tile(np.asarray(col, np.float64), (len(T), 1))


def box(x0, x1, y0, y1, z0, z1, col):
    c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], np.float64)   # index 4x+2y+z
    quads = [((0, 2, 3, 1), (-1, 0, 0)), ((4, 5, 7, 6), (1, 0, 0)), ((0, 1, 5, 4), (0, -1, 0)),
             ((2, 6, 7, 3), (0, 1, 0)), ((0, 4, 6, 2), (0, 0, -1)), ((1, 3, 7, 5), (0, 0, 1))]
    T, N = [], []
    for q, n in quads:
        T += [c[[q[0], q[1], q[2]]], c[[q[0], q[2], q[3]]]]
        N += [[n] * 3, [n] * 3]
    return _part(T, N, col)


def cyl(r0, r1, z0, z1, col, n=10, cx=0.0, cy=0.0, caps=(True, True)):
    """A cylinder or truncated cone about the vertical through (cx, cy), radius r0 at z0 and r1 at z1."""
    a = np.linspace(0, 2 * math.pi, n + 1)
    ca, sa = np.cos(a), np.sin(a)
    lo = np.column_stack([cx + r0 * ca, cy + r0 * sa, np.full(n + 1, z0)])
    hi = np.column_stack([cx + r1 * ca, cy + r1 * sa, np.full(n + 1, z1)])
    slope = (r0 - r1) / max(z1 - z0, 1e-9)
    nr = np.column_stack([ca, sa, np.full(n + 1, slope)])
    nr /= np.linalg.norm(nr, axis=1, keepdims=True)
    T, N = [], []
    for i in range(n):
        T += [[lo[i], lo[i + 1], hi[i + 1]], [lo[i], hi[i + 1], hi[i]]]
        N += [[nr[i], nr[i + 1], nr[i + 1]], [nr[i], nr[i + 1], nr[i]]]
        if caps[0] and r0 > 0:
            T.append([[cx, cy, z0], lo[i + 1], lo[i]])
            N.append([[0, 0, -1]] * 3)
        if caps[1] and r1 > 0:
            T.append([[cx, cy, z1], hi[i], hi[i + 1]])
            N.append([[0, 0, 1]] * 3)
    return _part(T, N, col)


def tube(P, r, col, n=6):
    """A tube of radius r along the polyline P (k, 3)."""
    P = np.asarray(P, np.float64)
    D = np.gradient(P, axis=0)
    D /= np.linalg.norm(D, axis=1, keepdims=True)
    up = np.where(np.abs(D[:, 2:3]) > 0.9, [[1.0, 0, 0]], [[0, 0, 1.0]])
    U = np.cross(D, up)
    U /= np.linalg.norm(U, axis=1, keepdims=True)
    V = np.cross(U, D)
    a = np.linspace(0, 2 * math.pi, n + 1)
    R = np.cos(a)[None, :, None] * U[:, None] + np.sin(a)[None, :, None] * V[:, None]      # (k, n+1, 3)
    X = P[:, None] + r * R
    T, N = [], []
    for k in range(len(P) - 1):
        for i in range(n):
            T += [[X[k, i], X[k + 1, i], X[k + 1, i + 1]], [X[k, i], X[k + 1, i + 1], X[k, i + 1]]]
            N += [[R[k, i], R[k + 1, i], R[k + 1, i + 1]], [R[k, i], R[k + 1, i + 1], R[k, i + 1]]]
    return _part(T, N, col)


def ellipsoid(c, r, col, sub=1):
    """An ellipsoid of centre c and semi-axes r (an icosahedron subdivided `sub` times)."""
    t = (1 + 5 ** 0.5) / 2
    V = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
         [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]]
    F = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
         [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
         [8, 6, 7], [9, 8, 1]]
    tris = np.array(V, np.float64)[np.array(F)]
    tris /= np.linalg.norm(tris, axis=2, keepdims=True)
    for _ in range(sub):
        a, b, cc = tris[:, 0], tris[:, 1], tris[:, 2]
        ab, bc, ca = [(p + q) / np.linalg.norm(p + q, axis=1, keepdims=True) for p, q in ((a, b), (b, cc), (cc, a))]
        tris = np.concatenate([np.stack(x, 1) for x in ((a, ab, ca), (ab, b, bc), (ca, bc, cc), (ab, bc, ca))])
    r = np.asarray(r, np.float64)
    N = tris / r ** 2
    N /= np.linalg.norm(N, axis=2, keepdims=True)
    return _part(tris * r + np.asarray(c, np.float64), N, col)


def sheet(profile, path, col, thick=0.004):
    """A thin sheet: the profile (m, 2) in the y-z plane swept along path (k, 3) offsets (x, dy, dz), both faces
    (the front towards -y), with smooth normals across the profile."""
    prof = np.asarray(profile, np.float64)
    path = np.asarray(path, np.float64)
    d = np.diff(prof, axis=0)
    seg_n = np.column_stack([d[:, 1], -d[:, 0]])                # (y, z) normal of every segment, towards -y
    seg_n *= np.where(seg_n[:, :1] > 0, -1, 1)
    seg_n /= np.linalg.norm(seg_n, axis=1, keepdims=True)
    vn = np.vstack([seg_n[:1], 0.5 * (seg_n[:-1] + seg_n[1:]), seg_n[-1:]])
    vn /= np.linalg.norm(vn, axis=1, keepdims=True)
    out = []
    for side in (1, -1):
        X = np.zeros((len(path), len(prof), 3))
        X[..., 0] = path[:, None, 0]
        X[..., 1] = prof[None, :, 0] + path[:, None, 1] + (0 if side > 0 else thick)
        X[..., 2] = prof[None, :, 1] + path[:, None, 2]
        Nv = np.zeros((len(prof), 3))
        Nv[:, 1:] = vn * side
        T, N = [], []
        for k in range(len(path) - 1):
            for j in range(len(prof) - 1):
                T += [[X[k, j], X[k + 1, j], X[k + 1, j + 1]], [X[k, j], X[k + 1, j + 1], X[k, j + 1]]]
                N += [[Nv[j], Nv[j], Nv[j + 1]], [Nv[j], Nv[j + 1], Nv[j + 1]]]
        out.append(_part(T, N, col))
    return out


def rotated(part, R, t=(0, 0, 0)):
    """A part turned by R (rows: where its x, y, z axes go) and moved by t."""
    T, N, C = part
    R = np.asarray(R, np.float64)
    return T @ R + np.asarray(t, np.float64), N @ R, C


# ---------------------------------------------------------------------------------------------- guard rails
# the W-beam of guardrail_mesh.PROFILE: (depth towards the road, height below the top)
W_PROFILE = np.array([[0.00, 0.00], [0.05, 0.035], [0.08, 0.07], [0.04, 0.155], [0.08, 0.24], [0.05, 0.275],
                      [0.00, 0.31]])
BEAM_TOP = 0.755             # m over the ground: a 0.31 m beam centred 0.6 m up
BEAM_BACK = 0.01             # m, local y of the back of the beam (its ridges at -0.07, guardrail_mesh.BOX)
POSTS = (-0.75, 0.75)        # m along the module (3 m long, laid every 2.8 m)


def _w(path):
    prof = np.column_stack([BEAM_BACK - W_PROFILE[:, 0], BEAM_TOP - W_PROFILE[:, 1]])
    return sheet(prof, path, _STEEL)


def _post(x):
    return [box(x - 0.045, x + 0.045, BEAM_BACK + 0.035, BEAM_BACK + 0.135, -0.3, BEAM_TOP - 0.02, _POST_STEEL),
            box(x - 0.03, x + 0.03, BEAM_BACK + 0.004, BEAM_BACK + 0.035, BEAM_TOP - 0.25, BEAM_TOP - 0.06, _DARK)]


def guardrail_module():
    """italy_guardrails_basic: 3 m of W-beam along local x (-1.5..1.5), its face towards the road (local -y),
    on two C-posts behind it (guardrail_mesh.py: origin on the ground, Y away from the road)."""
    parts = _w([[-1.5, 0, 0], [1.5, 0, 0]])
    for x in POSTS:
        parts += _post(x)
    return parts


def guardrail_end(sign):
    """The end pieces: half a metre of beam beyond the end of the run (sign -1: the start, _end_cw, towards -x;
    +1: the end, _end_ccw), flared away from the road and bent down."""
    t = np.linspace(0, 1, 7)
    path = np.column_stack([sign * (-0.07 + 0.5 * t), 0.30 * t ** 2, -0.12 * t ** 2])
    return _w(path) + [box(sign * 0.36 - 0.04, sign * 0.36 + 0.04, 0.25, 0.33, -0.3, 0.45, _POST_STEEL)]


# ---------------------------------------------------------------------------------------------- street furniture
def street_light():
    """italy_light_single: a grey steel pole of 8.75 m, its arm along local +x curving up to the head, 1.2 m out
    (lamps.HEAD)."""
    grey = (0.46, 0.48, 0.49)
    arm = np.array([[0.0, 0, 8.30], [0.12, 0, 8.52], [0.35, 0, 8.70], [0.7, 0, 8.80], [1.0, 0, 8.83]])
    return [cyl(0.13, 0.12, 0.0, 0.6, grey, n=10), cyl(0.085, 0.055, 0.6, 8.45, grey, n=10),
            tube(arm, 0.035, grey, n=6),
            box(0.88, 1.55, -0.14, 0.14, 8.74, 8.88, (0.30, 0.31, 0.32)),
            box(0.93, 1.48, -0.10, 0.10, 8.715, 8.74, (0.92, 0.91, 0.84))]


def wood_pole():
    """electric_pole_wood_old_01: a wooden pole of 10.05 m at scale 1 with a cross-arm across the line (local y)
    and three insulators."""
    wood = (0.36, 0.28, 0.20)
    parts = [cyl(0.14, 0.10, -0.2, 10.05, wood, n=9),
             box(-0.05, 0.05, -0.85, 0.85, 9.45, 9.56, (0.33, 0.26, 0.19))]
    for y in (-0.7, 0.0, 0.7):
        parts.append(cyl(0.04, 0.03, 9.56, 9.74, (0.82, 0.82, 0.80), n=6, cy=y))
    return parts


def bin_metal():
    """italy_clutter_metal_bin: 0.34 x 0.34 x 0.74 m."""
    return [cyl(0.16, 0.17, 0.0, 0.68, (0.34, 0.37, 0.35), n=12), cyl(0.175, 0.175, 0.66, 0.74, (0.24, 0.26, 0.25), n=12)]


def sorting_bin():
    """italy_clutter_sorting_bin: 0.56 x 0.62 x 0.97 m, its slot at the front (-y)."""
    return [box(-0.28, 0.28, -0.31, 0.31, 0.0, 0.91, (0.20, 0.44, 0.27)),
            box(-0.29, 0.29, -0.32, 0.32, 0.91, 0.97, (0.14, 0.30, 0.19)),
            box(-0.13, 0.13, -0.318, -0.30, 0.70, 0.79, _DARK)]


def dumpster():
    """italy_clutter_dumpster: 1.57 x 0.83 x 1.20 m on wheels, a dark lid."""
    parts = [box(-0.77, 0.77, -0.38, 0.38, 0.14, 1.08, (0.17, 0.32, 0.21)),
             box(-0.785, 0.785, -0.415, 0.40, 1.08, 1.20, (0.12, 0.13, 0.13))]
    for x in (-0.6, 0.6):
        for y in (-0.25, 0.25):
            parts.append(box(x - 0.06, x + 0.06, y - 0.03, y + 0.03, 0.0, 0.14, _DARK))
    return parts


def house_bin():
    """italy_clutter_big_dustbin: 0.60 x 0.60 x 0.68 m."""
    return [box(-0.28, 0.28, -0.28, 0.28, 0.0, 0.62, (0.30, 0.36, 0.31)),
            box(-0.30, 0.30, -0.30, 0.30, 0.62, 0.68, (0.20, 0.24, 0.21))]


def trashbags():
    """s_trashbag_pile_01: a heap of black bags, 1.38 x 1.21 x 1.04 m."""
    black, grey = (0.07, 0.07, 0.08), (0.20, 0.21, 0.23)
    return [ellipsoid((-0.3, -0.2, 0.28), (0.36, 0.32, 0.30), black), ellipsoid((0.3, -0.15, 0.27), (0.34, 0.30, 0.28), grey),
            ellipsoid((0.0, 0.3, 0.30), (0.40, 0.30, 0.31), black), ellipsoid((0.05, 0.0, 0.72), (0.32, 0.30, 0.30), black),
            ellipsoid((-0.42, 0.3, 0.22), (0.25, 0.25, 0.22), grey)]


def hydrant():
    """italy_clutter_fire_hydrant: a red pillar 0.79 m, its outlets to the sides."""
    red = (0.72, 0.10, 0.08)
    return [cyl(0.10, 0.10, 0.0, 0.62, red, n=10), cyl(0.115, 0.05, 0.62, 0.79, red, n=10),
            box(-0.18, 0.18, -0.045, 0.045, 0.42, 0.51, red), cyl(0.13, 0.13, 0.0, 0.05, red, n=10)]


def post_box():
    """italy_clutter_mailboxstand: a letter box on its post, 0.66 x 0.29 x 1.60 m."""
    return [box(-0.04, 0.04, -0.04, 0.04, 0.0, 1.15, (0.35, 0.36, 0.37)),
            box(-0.33, 0.33, -0.145, 0.145, 1.15, 1.60, (0.82, 0.64, 0.14)),
            box(-0.15, 0.15, -0.15, -0.14, 1.45, 1.48, _DARK)]


def picnic_table():
    """italy_clutter_pwood_table: 1.80 x 1.34 x 0.71 m, table top and two benches."""
    return [box(-0.9, 0.9, -0.35, 0.35, 0.67, 0.71, _WOOD), box(-0.9, 0.9, 0.45, 0.67, 0.42, 0.46, _WOOD),
            box(-0.9, 0.9, -0.67, -0.45, 0.42, 0.46, _WOOD),
            box(-0.75, -0.69, -0.62, 0.62, 0.0, 0.67, (0.45, 0.32, 0.20)), box(0.69, 0.75, -0.62, 0.62, 0.0, 0.67, (0.45, 0.32, 0.20))]


def round_table(r=0.30, col=(0.58, 0.59, 0.60)):
    """italy_clutter_round_mtable (0.60 m, metal), _round_ptable (0.72 m, white plastic): 0.74 m high."""
    return [cyl(r, r, 0.70, 0.74, col, n=14), cyl(0.03, 0.03, 0.03, 0.70, col, n=6), cyl(0.22, 0.22, 0.0, 0.03, col, n=10)]


def chair(col=(0.47, 0.49, 0.50)):
    """italy_clutter_metal_chair, _plastic_chair_a: 0.62 x 0.63 x 0.87 m, facing local -y."""
    parts = [box(-0.22, 0.22, -0.22, 0.22, 0.43, 0.47, col), box(-0.21, 0.21, 0.19, 0.23, 0.47, 0.87, col)]
    for x in (-0.19, 0.19):
        for y in (-0.19, 0.19):
            parts.append(box(x - 0.015, x + 0.015, y - 0.015, y + 0.015, 0.0, 0.43, col))
    return parts


def umbrella():
    """italy_clutter_bar_umbrella: a cream canopy of 1.5 m on its pole, 2.32 m, a heavy base."""
    cream = (0.93, 0.90, 0.80)
    return [cyl(0.25, 0.25, 0.0, 0.07, (0.25, 0.25, 0.26), n=10), cyl(0.024, 0.024, 0.07, 2.32, (0.80, 0.78, 0.72), n=6),
            cyl(0.76, 0.0, 1.95, 2.30, cream, n=8, caps=(False, False)),
            cyl(0.76, 0.0, 1.949, 1.95, (0.80, 0.77, 0.68), n=8, caps=(True, False))]


def tree_pot():
    """italy_city_tree_pot_wplant: a concrete trough 1.88 x 0.86 m with a shrub, 1.54 m."""
    return [box(-0.94, 0.94, -0.43, 0.43, 0.0, 0.55, (0.62, 0.61, 0.58)),
            ellipsoid((0, 0, 1.0), (0.85, 0.40, 0.54), (0.24, 0.40, 0.17))]


def planter_round():
    """italy_planter_round_1: 0.56 m across, 0.51 m."""
    return [cyl(0.28, 0.24, 0.0, 0.42, (0.62, 0.45, 0.34), n=12), ellipsoid((0, 0, 0.44), (0.23, 0.23, 0.09), (0.26, 0.42, 0.18))]


def planter_square():
    """italy_planter_square_2: 1.56 x 0.56 x 0.51 m."""
    return [box(-0.78, 0.78, -0.28, 0.28, 0.0, 0.42, (0.60, 0.59, 0.56)),
            ellipsoid((0, 0, 0.44), (0.72, 0.24, 0.10), (0.26, 0.42, 0.18))]


def mirror():
    """italy_clutter_convexmirror: a round traffic mirror 0.5 m, its origin in the middle, facing local -y (its pole
    is the level's own mesh)."""
    R = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]                  # a disc about z turned to face -y
    return [rotated(cyl(0.25, 0.25, -0.03, 0.03, (0.80, 0.22, 0.12), n=16), R),
            rotated(cyl(0.21, 0.21, -0.032, -0.031, (0.80, 0.84, 0.87), n=16, caps=(True, False)), R)]


def pallet():
    """italy_clutter_pallet: 1.37 x 0.91 x 0.20 m."""
    wood = (0.66, 0.55, 0.38)
    return [box(-0.685, 0.685, -0.455, 0.455, 0.16, 0.20, wood)] + \
        [box(-0.685, 0.685, y - 0.05, y + 0.05, 0.0, 0.16, (0.58, 0.48, 0.33)) for y in (-0.40, 0.0, 0.40)]


def drum():
    """italy_clutter_metal_drum: a steel drum, 1.0 m."""
    blue = (0.16, 0.29, 0.52)
    return [cyl(0.30, 0.30, 0.0, 0.98, blue, n=14), cyl(0.31, 0.31, 0.30, 0.33, (0.12, 0.22, 0.40), n=14),
            cyl(0.31, 0.31, 0.65, 0.68, (0.12, 0.22, 0.40), n=14)]


def bench(w=0.79, col=_WOOD):
    """italy_clutter_pwood_bench (1.58 x 0.61 x 0.79 m) and the east coast's wooden bench: seat and back of wooden
    slats on a dark frame, facing local -y."""
    return [box(-w, w, -0.25, 0.18, 0.42, 0.46, col), box(-w, w, 0.21, 0.25, 0.50, 0.79, col),
            box(-w + 0.12, -w + 0.17, -0.25, 0.26, 0.0, 0.50, _DARK), box(w - 0.17, w - 0.12, -0.25, 0.26, 0.0, 0.50, _DARK)]


def grey_post():
    """Any other model of the game: a grey post 4 m high (render3d up to v2.8)."""
    return [box(-0.125, 0.125, -0.125, 0.125, 0.0, 4.0, (0.50, 0.50, 0.52))]


# model name (lower case, without extension) -> builder
MODELS = {
    "italy_guardrails_basic": guardrail_module,
    "italy_guardrails_basic_end_cw": lambda: guardrail_end(-1),
    "italy_guardrails_basic_end_ccw": lambda: guardrail_end(1),
    "italy_light_single": street_light,
    "electric_pole_wood_old_01": wood_pole,
    "italy_clutter_metal_bin": bin_metal,
    "italy_clutter_sorting_bin": sorting_bin,
    "italy_clutter_dumpster": dumpster,
    "italy_clutter_big_dustbin": house_bin,
    "s_trashbag_pile_01": trashbags,
    "italy_clutter_fire_hydrant": hydrant,
    "italy_clutter_mailboxstand": post_box,
    "italy_clutter_pwood_table": picnic_table,
    "italy_clutter_round_mtable": round_table,
    "italy_clutter_round_ptable": lambda: round_table(0.36, (0.90, 0.90, 0.88)),
    "italy_clutter_metal_chair": chair,
    "italy_clutter_plastic_chair_a": lambda: chair((0.90, 0.90, 0.88)),
    "italy_clutter_bar_umbrella": umbrella,
    "italy_city_tree_pot_wplant": tree_pot,
    "italy_planter_round_1": planter_round,
    "italy_planter_square_2": planter_square,
    "italy_clutter_convexmirror": mirror,
    "italy_clutter_pallet": pallet,
    "italy_clutter_metal_drum": drum,
    "italy_clutter_pwood_bench": bench,
    "clutter_city_bench_wood": lambda: bench(0.90, (0.50, 0.36, 0.22)),
    "_post": grey_post,
}
SHINY = {"italy_guardrails_basic", "italy_guardrails_basic_end_cw", "italy_guardrails_basic_end_ccw"}
_cache = {}


def name_of(shape):
    """Model name of a shape path or forest type: base name, lower case, without extension."""
    base = shape.replace("\\", "/").rsplit("/", 1)[-1]
    return (base.rsplit(".", 1)[0] if "." in base else base).lower()


def has(name):
    return name in MODELS


def geometry(name):
    if name not in MODELS:
        return None
    if name not in _cache:
        parts = []
        for p in MODELS[name]():
            parts += p if isinstance(p, list) else [p]
        _cache[name] = tuple(np.concatenate([p[k] for p in parts]) for k in range(3))
    return _cache[name]
