"""The pose of a street photo in the 3D scene (v3.0.40): where the camera stood and where it looked, to a few
centimetres and tenths of a degree, so that a pixel of the photo falls on the right point of a facade.

The services give a first pose: Mapillary its own reconstruction (position and rotation of the camera, its focal length
and distortion), Panoramax the GPS and the compass of the phone. That pose is then fitted to the scene: the photo's
segmentation (sky, building, vegetation, ground: Mapillary's own, or a model's) has to agree with the label panorama of
the scene seen from the camera (street_render.py). A fixed set of the photo's pixels (along the edges between labels,
and sparse inside) is cast into the scene for a candidate pose; the score is the mean log-probability of their label
in the blurred label panorama (rays from a camera moved off the render position follow the distances of the render).
A fixed set of pixels matters: scoring the scene's points that fall inside the photo would favour poses that push the
hard ones out of the frame. The six parameters (position, heading, tilt, roll; the camera height between 1 and 3.5 m
over the ground) are searched from coarse to fine blur, the panorama rendered again at the new position each round.

    fit(photo, labels, scene) -> Fit(camera, score, agreement, rounds)
"""
import math
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.optimize import minimize
import street_camera as sc
import street_render as sr

# Mapillary Vistas values -> labels of the scene (anything else is not modelled: cars, people, poles, walls, fences ...)
VISTAS = {
    "nature--sky": sr.SKY,
    "construction--structure--building": sr.BUILDING,
    "nature--vegetation": sr.VEG,
    "nature--terrain": sr.GROUND, "nature--sand": sr.GROUND, "nature--snow": sr.GROUND, "nature--water": sr.GROUND,
    "nature--mountain": sr.GROUND,
    "construction--flat--road": sr.GROUND, "construction--flat--sidewalk": sr.GROUND,
    "construction--flat--driveway": sr.GROUND, "construction--flat--parking": sr.GROUND,
    "construction--flat--pedestrian-area": sr.GROUND, "construction--flat--crosswalk-plain": sr.GROUND,
    "construction--flat--bike-lane": sr.GROUND, "construction--flat--service-lane": sr.GROUND,
    "construction--flat--rail-track": sr.GROUND, "construction--flat--curb-cut": sr.GROUND,
    "construction--flat--road-shoulder": sr.GROUND, "construction--flat--traffic-island": sr.GROUND,
    "construction--barrier--curb": sr.GROUND,
    "marking--discrete--crosswalk-zebra": sr.GROUND,
}
NLAB = 4                      # sky, ground, vegetation, building
MOUNT = (1.0, 3.5)            # m over the ground: the camera height the fit may give
STEPS = (6.0, 2.5)            # px of blur of the segmentation (at label_w) in every round
# how far a round may move the camera (m, m, m, deg, deg, deg) and how far the whole fit may take it from the first
# pose before a penalty grows (the services' poses: Mapillary's reconstruction within a few metres and degrees)
BOUNDS = (2.5, 2.5, 1.0, 8.0, 4.0, 4.0)
PRIOR = (4.0, 10.0)           # m, deg
PRIOR_W = 0.02                # weight of the prior against the score (a mean over the photo's pixels: some 50 of them
                              # independent); stronger, it holds a camera a few metres off where it stood


def label_map(dets, W, H):
    """(H, W) uint8 map of a photo's labels from Mapillary detections (255: not modelled)."""
    import cv2
    out = np.full((H, W), 255, np.uint8)
    # the large classes first, so that the objects drawn later keep their own pixels
    order = sorted(dets, key=lambda d: -sum(_area(p) for p in d["polys"]))
    for d in order:
        lab = VISTAS.get(d["value"], 255)
        pts = [np.round(np.asarray(p) * [W, H]).astype(np.int32) for p in d["polys"]]
        cv2.fillPoly(out, pts, int(lab))
    return out


def _area(p):
    p = np.asarray(p)
    return 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))


class PhotoSamples:
    """Pixels of a photo's label map that the fit compares with the scene: along the edges between two labels it models
    every step-th, inside the regions one in inner_step; their rays in the camera frame and their labels."""

    def __init__(self, labs, cam, step=2, inner_step=6):
        from scipy.ndimage import binary_dilation
        L = labs
        m = L < NLAB
        edge = np.zeros(L.shape, bool)
        edge[:, 1:] |= (L[:, 1:] != L[:, :-1]) & m[:, 1:] & m[:, :-1]
        edge[1:, :] |= (L[1:, :] != L[:-1, :]) & m[1:, :] & m[:-1, :]
        edge = binary_dilation(edge, iterations=3)
        grid = np.zeros(L.shape, bool)
        grid[::step, ::step] = edge[::step, ::step]
        grid[::inner_step, ::inner_step] = True
        grid &= m
        rows, cols = np.nonzero(grid)
        s = L.shape[1] / cam.W
        self.ray = cam.cam_dirs((cols + 0.5) / s - 0.5, (rows + 0.5) / s - 0.5)
        self.label = L[rows, cols].astype(np.int64)
        # every label weighs the same overall (the sky and the ground would drown the buildings otherwise)
        cnt = np.bincount(self.label, minlength=NLAB).astype(float)
        self.w = 1.0 / np.maximum(cnt[self.label], 1.0)
        self.w /= self.w.sum()


class SceneProbs:
    """The label panorama of the scene blurred by blur_deg: per label the probability in every direction from the
    render position, and the distances there (for the parallax of a camera moved off that position)."""

    PAD = 8

    def __init__(self, pano, blur_deg):
        self.pano = pano
        px = blur_deg / (360.0 / pano.W)
        P = np.stack([(pano.label == k).astype(np.float32) for k in range(NLAB)])
        P = np.concatenate([P[:, :, -self.PAD:], P, P[:, :, :self.PAD]], 2)
        if px > 0.3:
            P = np.stack([gaussian_filter(p, px, mode=("nearest", "wrap")) for p in P])
        self.P = P
        self.dist = np.where(np.isfinite(pano.dist), pano.dist, np.inf).astype(np.float64)

    def rc(self, d):
        """Fractional (row, column) of world directions d in the padded maps, and the nearest pixel."""
        pano = self.pano
        lon = np.arctan2(d[:, 0], d[:, 1])
        lat = np.arcsin(np.clip(d[:, 2], -1, 1))
        c = (lon + np.pi) / (2 * np.pi) * pano.W - 0.5
        r = (np.pi / 2 - lat) / np.pi * pano.H - 0.5
        return r, c

    def depth(self, d):
        r, c = self.rc(d)
        pano = self.pano
        ri = np.clip(np.round(r).astype(int), 0, pano.H - 1)
        ci = np.round(c).astype(int) % pano.W
        return self.dist[ri, ci]

    def seen_from(self, pos, rays, iters=3):
        """The directions from the render position of the points the rays from pos hit (a fixed point on the
        distances of the render: exact for a camera on the render position, close for a few metres off it)."""
        o = self.pano.pos
        off = pos - o
        if float(off @ off) < 1e-6:
            return rays
        d = rays
        for _ in range(iters):
            D = self.depth(d)
            fin = np.isfinite(D)
            Y = o + d * np.where(fin, D, 0.0)[:, None]
            t = np.maximum(((Y - pos) * rays).sum(1), 0.05)
            v = pos + rays * t[:, None] - o
            dn = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            d = np.where(fin[:, None], dn, rays)
        return d


def perturb(cam, x):
    """The camera moved by x = (dx, dy, dz m, d_heading, d_pitch, d_roll degrees)."""
    R = sc.rot_z(-math.radians(x[3])) @ cam.R @ sc.rot_x(math.radians(x[4])) @ sc.rot_y(math.radians(x[5]))
    return cam.copy(pos=cam.pos + np.asarray(x[:3], float), R=R)


def score(cam, ps, sp_):
    """Mean log-probability, in the blurred label panorama of the scene, of the labels the photo shows (the photo's
    sampled pixels, a fixed set: the score of any pose counts the same pixels), and the share that agree."""
    rays = ps.ray @ cam.R.T
    d = sp_.seen_from(cam.pos, rays)
    r, c = sp_.rc(d)
    c = c + sp_.PAD
    p = np.empty(len(r))
    for k in range(NLAB):
        m = ps.label == k
        if m.any():
            p[m] = map_coordinates(sp_.P[k], [r[m], c[m]], order=1, mode="nearest")
    return float((ps.w * np.log(p + 0.02)).sum()), float((ps.w * (p > 0.5)).sum())


class Fit:
    def __init__(self, cam, score, agreement, rounds):
        self.cam, self.score, self.agreement, self.rounds = cam, score, agreement, rounds

    def offsets(self, cam0):
        """(horizontal shift m, height change m, heading change deg) from the first pose."""
        d = self.cam.pos - cam0.pos
        h0 = sc.angles_of(cam0.R)[0]
        h1 = sc.angles_of(self.cam.R)[0]
        return float(np.hypot(d[0], d[1])), float(d[2]), float((h1 - h0 + 180) % 360 - 180)


def _labels_at(lab, label_w):
    import cv2
    s = label_w / lab.shape[1]
    return cv2.resize(lab, (label_w, max(1, int(round(lab.shape[0] * s)))), interpolation=cv2.INTER_NEAREST)


def _mount_penalty(c, ground):
    h = c.pos[2] - float(ground(c.pos[0], c.pos[1])[0])
    return (max(0.0, MOUNT[0] - h) ** 2 + max(0.0, h - MOUNT[1]) ** 2) * 5


def _render_w(cam, label_w):
    """Columns of the scene panorama for a photo: about as fine as its label map (360 degree photos 1440)."""
    if cam.kind == "equirect":
        return 1440
    deg = cam.deg_per_px() * cam.W / label_w
    return int(min(2880, max(1440, 360.0 / deg / 2)) // 8 * 8)


def fit(cam0, lab, scene, ground, heading_search=0.0, label_w=720, rounds=4, prior=PRIOR):
    """The pose of a photo fitted to the scene.
    cam0: the first pose (street_camera.Camera); lab: the photo's label map (any size, same aspect as the photo);
    ground(x, y): bare ground height; heading_search: +- degrees of heading tried first (an unreliable compass);
    prior: (m, deg) the first pose is trusted to."""
    labs = _labels_at(lab, label_w)
    ps = PhotoSamples(labs, cam0)
    deg_px = cam0.deg_per_px() * cam0.W / label_w            # degrees per pixel of the label map
    h0 = sc.angles_of(cam0.R)[0]
    rw = _render_w(cam0, label_w)
    cam = cam0
    log = []
    for rnd in range(rounds):
        pano = sr.render(scene, cam.pos, W=rw)
        if heading_search and rnd == 0:
            spr = SceneProbs(pano, STEPS[0] * 2 * deg_px)
            best = max((score(perturb(cam, [0, 0, 0, a, 0, 0]), ps, spr)[0], a)
                       for a in np.arange(-heading_search, heading_search + 0.1, 1.0))
            cam = perturb(cam, [0, 0, 0, best[1], 0, 0])
        start = cam
        for blur in STEPS:
            spr = SceneProbs(pano, blur * deg_px)
            base = cam

            def cost(x):
                c = perturb(base, x)
                # the first pose as a weak prior: the score alone slides along a street of look-alike houses
                sh = np.hypot(c.pos[0] - cam0.pos[0], c.pos[1] - cam0.pos[1])
                dh = (sc.angles_of(c.R)[0] - h0 + 180) % 360 - 180
                pen = _mount_penalty(c, ground) + PRIOR_W * ((sh / prior[0]) ** 2 + (dh / prior[1]) ** 2)
                return -score(c, ps, spr)[0] + pen
            r = minimize(cost, np.zeros(6), method="Powell", bounds=[(-b, b) for b in BOUNDS],
                         options={"xtol": 1e-3, "ftol": 1e-5, "maxfev": 600})
            cam = perturb(base, r.x)
        moved = float(np.linalg.norm(cam.pos - start.pos))
        log.append((rnd, cam.pos.tolist(), sc.angles_of(cam.R), moved))
        if moved < 0.15 and rnd >= 1:
            break
    # the final score on a render at the final pose
    sc_, ag = score(cam, ps, SceneProbs(sr.render(scene, cam.pos, W=rw), STEPS[-1] * deg_px))
    return Fit(cam, sc_, ag, log)


def move_group(cams, x, centre):
    """The cameras moved together, as one rigid body: rotated by (d_heading, d_tilt_east, d_tilt_north) degrees about
    the vertical and horizontal axes through centre, then shifted by (dx, dy, dz)."""
    Rg = sc.rot_z(-math.radians(x[3])) @ sc.rot_x(math.radians(x[4])) @ sc.rot_y(math.radians(x[5]))
    t = np.asarray(x[:3], float)
    return [c.copy(pos=centre + Rg @ (c.pos - centre) + t, R=Rg @ c.R) for c in cams]


def fit_group(cams0, labs, scene, ground, label_w=720, rounds=4, prior=PRIOR):
    """The poses of photos taken one after the other (a sequence of one reconstruction: their relative poses hold)
    fitted to the scene together, as one rigid body. Returns the cameras, the mean score and the rounds."""
    L = [_labels_at(l, label_w) for l in labs]
    PS = [PhotoSamples(l, c) for l, c in zip(L, cams0)]
    DP = [c.deg_per_px() * c.W / label_w for c in cams0]
    RW = [_render_w(c, label_w) for c in cams0]
    centre = np.mean([c.pos for c in cams0], 0)
    h0 = sc.angles_of(cams0[0].R)[0]
    cams = list(cams0)
    log = []
    for rnd in range(rounds):
        panos = [sr.render(scene, c.pos, W=w) for c, w in zip(cams, RW)]
        start = [c.pos.copy() for c in cams]
        for blur in STEPS:
            SP = [SceneProbs(p, blur * dp) for p, dp in zip(panos, DP)]
            base = cams

            def cost(x):
                cs = move_group(base, x, centre)
                tot = 0.0
                for c, ps, spr in zip(cs, PS, SP):
                    tot += -score(c, ps, spr)[0] + _mount_penalty(c, ground)
                d = cs[0].pos - cams0[0].pos
                dh = (sc.angles_of(cs[0].R)[0] - h0 + 180) % 360 - 180
                tot += PRIOR_W * len(cs) * ((np.hypot(d[0], d[1]) / prior[0]) ** 2 + (dh / prior[1]) ** 2)
                return tot / len(cs)
            r = minimize(cost, np.zeros(6), method="Powell", bounds=[(-b, b) for b in BOUNDS],
                         options={"xtol": 1e-3, "ftol": 1e-6, "maxfev": 800})
            cams = move_group(base, r.x, centre)
            centre = np.mean([c.pos for c in cams], 0)
        moved = float(max(np.linalg.norm(c.pos - p) for c, p in zip(cams, start)))
        log.append((rnd, moved))
        if moved < 0.1 and rnd >= 1:
            break
    sc_ = float(np.mean([score(c, ps, SceneProbs(sr.render(scene, c.pos, W=w), STEPS[-1] * dp))[0]
                         for c, ps, w, dp in zip(cams, PS, RW, DP)]))
    return cams, sc_, log
