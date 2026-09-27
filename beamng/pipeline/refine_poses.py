"""Refine every panorama pose against the swisstopo data.

A. Attitude (pitch/roll): vertical vanishing point from near-vertical line
   segments (buildings, poles, walls) seen in 8 level views, regularised by the
   Street View metadata.
B. Position + heading: the panorama ground (1.8-14 m around the car) is
   projected onto the DTM surface and registered to the 10 cm SWISSIMAGE
   orthophoto with masked normalised cross-correlation (road markings, curbs,
   manholes, road edges), searching heading offsets and planar shifts.
C. Robust smoothing of the corrections along the route (GPS/INS errors are
   smooth); per-pano results that disagree with their neighbours are rejected.

Usage: python refine_poses.py [camheight | test i,j,k | all]
Output: work/poses.json  (per pano: pos [x,y,z], R (3x3 camera->world), quality)
"""
import json, math, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import cv2
from scipy.ndimage import gaussian_filter
from config import DATASET, WORK
from camera import Pano, rot_z, pixel_to_dir_cam
from geo import Grid
import ortho

cv2.setNumThreads(2)
RES = 0.1                 # registration grid (m)
R_IN, R_OUT = 1.8, 14.0   # ground ring used from the panorama (m)
PATCH = 20.0              # half size of the orthophoto patch (m)
SHIFT = 5.0               # max planar correction searched (m)
HEAD_RANGE, HEAD_STEP = 3.0, 0.25
DIAG = os.path.join(WORK, "pose_diag")
os.makedirs(DIAG, exist_ok=True)

_dtm = None


def dtm():
    global _dtm
    if _dtm is None:
        _dtm = Grid.load(os.path.join(WORK, "dtm05.npz"))
    return _dtm


def pano_file(rec):
    return os.path.join(DATASET, "panorami", f"{rec['index']:04d}_{rec['id']}.jpg")


# ---------------------------------------------------------------- A. attitude
def level_view_rays(yaw, R, w=1024, fov=90.0, pitch=0.0):
    f = w / 2 / math.tan(math.radians(fov) / 2)
    y, p = math.radians(yaw), math.radians(pitch)
    fwd = np.array([math.sin(y) * math.cos(p), math.cos(y) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(y), -math.sin(y), 0.0])
    up = np.cross(right, fwd)
    return f, fwd, right, up


def estimate_up(img_small, pano, lam=40.0):
    """Return corrected camera->world rotation and diagnostics."""
    Hs, Ws = img_small.shape[:2]
    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    normals, weights = [], []
    w = 1024
    for pitch in (0.0, 25.0):
        for k in range(8):
            yaw = pano.heading + 45 * k
            f, fwd, right, up = level_view_rays(yaw, pano.R, w, 90.0, pitch)
            ii, jj = np.meshgrid(np.arange(w) - w / 2 + 0.5, w / 2 - np.arange(w) - 0.5)
            d = fwd * f + ii[..., None] * right + jj[..., None] * up
            u, v = pano.dir_to_pixel(d)
            u, v = u * Ws / pano.W, v * Hs / pano.H
            view = cv2.remap(img_small, u.astype(np.float32), v.astype(np.float32),
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
            lines = lsd.detect(cv2.cvtColor(view, cv2.COLOR_BGR2GRAY))[0]
            if lines is None:
                continue
            l = np.asarray(lines).reshape(-1, 4)
            dx, dy = l[:, 2] - l[:, 0], l[:, 3] - l[:, 1]
            length = np.hypot(dx, dy)
            ang = np.degrees(np.arctan2(dx, dy))
            ang = (ang + 90) % 180 - 90
            ok = (length > 45) & (np.abs(ang) < 10)
            for x1, y1, x2, y2 in l[ok]:
                p1 = fwd * f + (x1 - w / 2) * right + (w / 2 - y1) * up
                p2 = fwd * f + (x2 - w / 2) * right + (w / 2 - y2) * up
                n = np.cross(p1, p2)
                nn = np.linalg.norm(n)
                if nn > 0:
                    normals.append(n / nn)
            weights += list(length[ok])
    if len(normals) < 10:
        return np.eye(3), dict(n=len(normals), tilt=0.0)
    N = np.array(normals)
    W = np.array(weights) / np.mean(weights)
    v = np.array([0, 0, 1.0])
    ex, ey = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    prior = lam * (np.outer(ex, ex) + np.outer(ey, ey))
    for it in range(8):
        r = np.degrees(np.arcsin(np.clip(np.abs(N @ v), 0, 1)))
        wr = W / (1 + (r / 0.6) ** 2)                          # Cauchy weights
        M = (N * wr[:, None]).T @ N + prior
        evals, evecs = np.linalg.eigh(M)
        v = evecs[:, 0] * np.sign(evecs[2, 0])
    # rotation taking v (true up expressed in the prior world frame) to +z
    axis = np.cross(v, [0, 0, 1.0])
    s = np.linalg.norm(axis)
    if s < 1e-9:
        C = np.eye(3)
    else:
        axis /= s
        a = math.asin(min(1.0, s))
        K_ = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        C = np.eye(3) + math.sin(a) * K_ + (1 - math.cos(a)) * K_ @ K_
    inl = int(np.sum(np.degrees(np.arcsin(np.clip(np.abs(N @ v), 0, 1))) < 1.0))
    return C, dict(n=len(normals), inliers=inl, tilt=float(np.degrees(math.acos(min(1, v[2])))),
                   v=[float(t) for t in v])


# ------------------------------------------------------ B. ground registration
def lcn(img, sigma):
    """Local contrast normalisation of a float image."""
    m = gaussian_filter(img, sigma)
    d = img - m
    s = np.sqrt(gaussian_filter(d * d, sigma)) + 1e-3
    return d / s


_dsm = None


def dsm():
    global _dsm
    if _dsm is None:
        _dsm = Grid.load(os.path.join(WORK, "dsm05.npz"))
    return _dsm


def ground_geometry(cam_xy, h_cam, n_half, occlusion=True):
    """Ground grid around cam_xy: camera->ground vectors D and the usable mask
    (inside the ring, bare ground, visible from the camera). Heading independent."""
    xs = cam_xy[0] + (np.arange(2 * n_half) - n_half + 0.5) * RES
    ys = cam_xy[1] + (n_half - np.arange(2 * n_half) - 0.5) * RES
    X, Y = np.meshgrid(xs, ys)
    Z = dtm().sample(X.ravel(), Y.ravel()).reshape(X.shape)
    cz = dtm().sample([cam_xy[0]], [cam_xy[1]])[0] + h_cam
    D = np.stack([X - cam_xy[0], Y - cam_xy[1], Z - cz], -1)
    r = np.hypot(D[..., 0], D[..., 1])
    mask = (r > R_IN) & (r < R_OUT)
    if occlusion:
        ndsm = dsm().sample(X.ravel(), Y.ravel()).reshape(X.shape) - Z
        mask &= ndsm < 0.4
        idx = np.where(mask)
        Dm = D[idx]
        blocked = np.zeros(len(Dm), bool)
        for t in np.linspace(0.08, 0.97, 24):
            s = dsm().sample(cam_xy[0] + Dm[:, 0] * t, cam_xy[1] + Dm[:, 1] * t)
            blocked |= s > cz + Dm[:, 2] * t + 0.15
        mask[idx[0][blocked], idx[1][blocked]] = False
    return D, mask


def ground_sample(img, R, D):
    dc = D @ R
    lon = np.arctan2(dc[..., 0], dc[..., 1])
    lat = np.arcsin(np.clip(dc[..., 2] / np.linalg.norm(dc, axis=-1), -1, 1))
    Hi, Wi = img.shape[:2]
    u = ((lon + np.pi) / (2 * np.pi) * Wi - 0.5).astype(np.float32)
    v = ((np.pi / 2 - lat) / np.pi * Hi - 0.5).astype(np.float32)
    return cv2.remap(img, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def ground_render(img, pano, cam_xy, h_cam, heading_off, n_half, occlusion=True):
    D, mask = ground_geometry(cam_xy, h_cam, n_half, occlusion)
    R = rot_z(-math.radians(heading_off)) @ pano.R
    return ground_sample(img, R, D), mask


def feature(bgr, valid):
    """Road-marking + edge response, robust to illumination (float32, 0 outside valid)."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    top = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, k)
    gs = cv2.GaussianBlur(g, (0, 0), 1.2)
    gx = cv2.Sobel(gs, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gs, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.hypot(gx, gy)
    def norm(a):
        a = a.copy()
        a[~valid] = 0
        m = a[valid].mean() if valid.any() else 0
        sd = a[valid].std() + 1e-6 if valid.any() else 1
        return np.clip((a - m) / sd, -2, 6)
    f = norm(top) + 0.5 * norm(grad)
    f = cv2.GaussianBlur(f, (0, 0), 1.0)
    f[~valid] = 0
    return f


def masked_ncc(F, M, mask):
    """NCC of moving M (with mask) against fixed F for all integer shifts (same size arrays).
    Returns ncc[dy, dx] with the zero shift at the centre."""
    h, w = F.shape
    mm = mask.astype(np.float64)
    n = mm.sum()
    Mv = (M - (M * mm).sum() / n) * mm
    sM = np.sqrt((Mv ** 2).sum())
    fF = np.fft.rfft2(F)
    fF2 = np.fft.rfft2(F * F)
    fM = np.conj(np.fft.rfft2(Mv))
    fm = np.conj(np.fft.rfft2(mm))
    A = np.fft.irfft2(fF * fM, s=(h, w))
    F1 = np.fft.irfft2(fF * fm, s=(h, w))
    F2 = np.fft.irfft2(fF2 * fm, s=(h, w))
    var = np.maximum(F2 - F1 * F1 / n, 1e-6)
    ncc = A / (np.sqrt(var) * sM + 1e-9)
    return np.fft.fftshift(ncc)


def register(img, pano, h_cam, heads=None):
    cx, cy = pano.pos[0], pano.pos[1]
    nf = int(round(PATCH / RES))
    orth = ortho.patch(cx - PATCH, cy - PATCH, cx + PATCH, cy + PATCH, RES)
    ob = cv2.cvtColor(orth, cv2.COLOR_RGB2BGR)
    # orthophoto: exclude above-ground objects (tree crowns, roofs hide the ground)
    xs = cx + (np.arange(2 * nf) - nf + 0.5) * RES
    ys = cy + (nf - np.arange(2 * nf) - 0.5) * RES
    X, Y = np.meshgrid(xs, ys)
    ndsm = (dsm().sample(X.ravel(), Y.ravel()) - dtm().sample(X.ravel(), Y.ravel())).reshape(X.shape)
    ovalid = (orth.sum(-1) > 0) & (ndsm < 0.4)
    F = feature(ob, ovalid)
    heads = np.arange(-HEAD_RANGE, HEAD_RANGE + 1e-6, HEAD_STEP) if heads is None else heads
    best = None
    lim = int(SHIFT / RES)
    for dh in heads:
        g, mask = ground_render(img, pano, (cx, cy), h_cam, dh, nf)
        M = feature(g, mask)
        ncc = masked_ncc(F, M, mask)
        c = ncc.shape[0] // 2
        win = ncc[c - lim:c + lim + 1, c - lim:c + lim + 1]
        k = np.unravel_index(np.argmax(win), win.shape)
        val = win[k]
        if best is None or val > best[0]:
            best = (val, dh, k, win, int(mask.sum()))
    val, dh, (ky, kx), win, npx = best

    def sub(a, b, c):
        d = a - 2 * b + c
        return 0.0 if abs(d) < 1e-9 else 0.5 * (a - c) / d
    sy = sub(win[ky - 1, kx], win[ky, kx], win[ky + 1, kx]) if 0 < ky < win.shape[0] - 1 else 0
    sx = sub(win[ky, kx - 1], win[ky, kx], win[ky, kx + 1]) if 0 < kx < win.shape[1] - 1 else 0
    # ncc index (dy,dx): render pixel p matches ortho pixel p + s; rows grow southwards
    dxm = (kx - lim + sx) * RES
    dym = -(ky - lim + sy) * RES
    yy, xx = np.mgrid[:win.shape[0], :win.shape[1]]
    far = np.hypot(yy - ky, xx - kx) > 1.0 / RES
    k2 = np.unravel_index(np.argmax(np.where(far, win, -9)), win.shape)
    second = win[k2]
    return dict(dx=float(dxm), dy=float(dym), dh=float(dh), ncc=float(val), sharp=float(val - second),
                second_dx=float((k2[1] - lim) * RES), second_dy=float(-(k2[0] - lim) * RES), npx=npx)


def ncc_volume(img, pano, h_cam, heads):
    """NCC for every heading offset in `heads` and every planar shift within +-SHIFT."""
    cx, cy = pano.pos[0], pano.pos[1]
    nf = int(round(PATCH / RES))
    orth = ortho.patch(cx - PATCH, cy - PATCH, cx + PATCH, cy + PATCH, RES)
    ob = cv2.cvtColor(orth, cv2.COLOR_RGB2BGR)
    xs = cx + (np.arange(2 * nf) - nf + 0.5) * RES
    ys = cy + (nf - np.arange(2 * nf) - 0.5) * RES
    X, Y = np.meshgrid(xs, ys)
    ndsm = (dsm().sample(X.ravel(), Y.ravel()) - dtm().sample(X.ravel(), Y.ravel())).reshape(X.shape)
    ovalid = (orth.sum(-1) > 0) & (ndsm < 0.4)
    F = feature(ob, ovalid)
    lim = int(SHIFT / RES)
    vol = np.zeros((len(heads), 2 * lim + 1, 2 * lim + 1), np.float32)
    npx = 0
    D, mask = ground_geometry((cx, cy), h_cam, nf)
    for i, dh in enumerate(heads):
        g = ground_sample(img, rot_z(-math.radians(dh)) @ pano.R, D)
        ncc = masked_ncc(F, feature(g, mask), mask)
        c = ncc.shape[0] // 2
        vol[i] = ncc[c - lim:c + lim + 1, c - lim:c + lim + 1]
        npx = int(mask.sum())
    return vol, npx, float(ovalid.mean())


def process_volume(args):
    rec, h_cam = args
    out_f = os.path.join(WORK, "ncc_vol", f"{rec['index']:04d}.npz")
    if os.path.exists(out_f):
        return rec["index"], "skip"
    img = cv2.imread(pano_file(rec))
    pano = Pano(rec, W=img.shape[1], H=img.shape[0])
    small = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
    C, att = estimate_up(small, pano)
    pano.R = C @ pano.R
    heads = np.arange(-HEAD_RANGE, HEAD_RANGE + 1e-6, HEAD_STEP)
    vol, npx, ov = ncc_volume(img, pano, h_cam, heads)
    np.savez_compressed(out_f, vol=vol.astype(np.float16), heads=heads, R_att=pano.R,
                        pos0=pano.pos, att=json.dumps(att), npx=npx, ortho_valid=ov)
    return rec["index"], "ok"


def process(args):
    rec, h_cam, mode = args
    img = cv2.imread(pano_file(rec))
    pano = Pano(rec, W=img.shape[1], H=img.shape[0])
    small = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
    C, att = estimate_up(small, pano)
    pano.R = C @ pano.R
    out = dict(index=rec["index"], id=rec["id"], att=att)
    if mode == "camheight":
        out["h"] = {}
        for h in (2.2, 2.35, 2.5, 2.65, 2.8, 2.95):
            out["h"][h] = register(img, pano, h)
        return out
    r = register(img, pano, h_cam)
    # refine heading finely around the best
    r2 = register(img, pano, h_cam, heads=r["dh"] + np.arange(-0.3, 0.31, 0.05))
    if r2["ncc"] >= r["ncc"]:
        r = r2
    out.update(r)
    out["R_att"] = pano.R.tolist()
    if mode == "test" or rec["index"] % 25 == 0:
        diag(img, pano, rec, h_cam, r)
    return out


def diag(img, pano, rec, h_cam, r):
    cx, cy = pano.pos[0] + r["dx"], pano.pos[1] + r["dy"]
    n = int(round(PATCH / RES))
    orth = ortho.patch(cx - PATCH, cy - PATCH, cx + PATCH, cy + PATCH, RES)
    g0, m0 = ground_render(img, pano, (pano.pos[0], pano.pos[1]), h_cam, 0.0, n)
    g1, m1 = ground_render(img, pano, (cx, cy), h_cam, r["dh"], n)
    o = cv2.cvtColor(orth, cv2.COLOR_RGB2BGR)
    blend0 = o.copy(); blend0[m0] = (0.5 * o[m0] + 0.5 * g0[m0]).astype(np.uint8)
    blend1 = o.copy(); blend1[m1] = (0.5 * o[m1] + 0.5 * g1[m1]).astype(np.uint8)
    sheet = np.concatenate([o, blend0, blend1], 1)
    cv2.putText(sheet, f"#{rec['index']} raw GPS", (370, 25), 0, 0.7, (0, 255, 255), 2)
    cv2.putText(sheet, f"refined dx={r['dx']:.2f} dy={r['dy']:.2f} dh={r['dh']:.2f} ncc={r['ncc']:.2f}",
                (730, 25), 0, 0.6, (0, 255, 255), 2)
    cv2.imwrite(os.path.join(DIAG, f"reg_{rec['index']:04d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    panos = json.load(open(os.path.join(DATASET, "panoramas.json")))
    h_cam = 2.5
    hf = os.path.join(WORK, "camera_height.json")
    if os.path.exists(hf):
        h_cam = json.load(open(hf))["h_cam"]
    if mode == "camheight":
        sel = panos[5::9]
        with ProcessPoolExecutor(6) as ex:
            res = list(ex.map(process, [(r, h_cam, mode) for r in sel]))
        hs = sorted(res[0]["h"].keys(), key=float)
        tab = np.array([[r["h"][h]["ncc"] for h in hs] for r in res])
        good = tab.max(1) > 0.25
        mean = tab[good].mean(0)
        print("camera height candidates", hs, "mean ncc", np.round(mean, 4), "n", good.sum())
        # parabola through the best three
        k = int(np.argmax(mean)); k = min(max(k, 1), len(hs) - 2)
        x = np.array([float(h) for h in hs[k - 1:k + 2]]); y = mean[k - 1:k + 2]
        a, b, c = np.polyfit(x, y, 2)
        hbest = float(-b / (2 * a)) if a < 0 else float(hs[int(np.argmax(mean))])
        print("camera height ->", hbest)
        json.dump({"h_cam": hbest, "table": tab.tolist(), "hs": hs}, open(hf, "w"))
        return
    if mode == "volumes":
        os.makedirs(os.path.join(WORK, "ncc_vol"), exist_ok=True)
        with ProcessPoolExecutor(6) as ex:
            for i, st in ex.map(process_volume, [(r, h_cam) for r in panos]):
                print(i, st, flush=True)
        return
    if mode == "test":
        idx = [int(t) for t in sys.argv[2].split(",")]
        sel = [panos[i] for i in idx]
    else:
        sel = panos
    with ProcessPoolExecutor(6) as ex:
        res = list(ex.map(process, [(r, h_cam, mode) for r in sel]))
    for r in res:
        print(r["index"], "att", r["att"].get("tilt"), r["att"].get("n"), "reg dx %.2f dy %.2f dh %.2f ncc %.3f sharp %.3f"
              % (r["dx"], r["dy"], r["dh"], r["ncc"], r["sharp"]), flush=True)
    json.dump(res, open(os.path.join(WORK, "registration_raw.json" if mode == "all" else "registration_test.json"), "w"))


if __name__ == "__main__":
    main()
