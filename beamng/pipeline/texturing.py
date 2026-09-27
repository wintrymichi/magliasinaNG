"""Projective texturing of vertical surfaces (walls, facades) from the calibrated panoramas.

A surface is a 'ribbon': a polyline (x, y) with per-vertex base/top heights and an
outward normal side. Texels (TEX m) are laid out u = distance along the polyline,
v = height from the ribbon's minimum base. Each texel gets the colour of the
panorama that sees it best: score = cos(incidence)^2 / distance, with the ray not
blocked by the DSM (buildings, trees, walls) and the pixel not segmented as
vegetation / vehicle / person / pole / sign. The panorama choice is made per 8x8 texel
block (fewer seams). Unobserved texels are filled from their neighbours; texels never
seen within 12 texels get the ribbon's median colour.
Atlases are shelf-packed (4096 px) and saved as JPG in the level.
"""
import json, math, os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import map_coordinates, distance_transform_edt
from config import WORK, DATASET
from geo import Grid
import camera

REJECT = {19, 20, 21, 22, 30, 44, 45, 46, 47, 48, 49, 50, 52, 54, 55, 56, 57, 59, 60, 61, 62, 63, 64, 27}
BLOCK = 8


class PanoCache:
    def __init__(self, n=6):
        self.n, self.d = n, {}
        self.D = json.load(open(os.path.join(DATASET, "panoramas.json")))

    def get(self, i):
        if i not in self.d:
            if len(self.d) >= self.n:
                self.d.pop(next(iter(self.d)))
            rec = self.D[i]
            img = cv2.imread(os.path.join(DATASET, "panorami", f"{rec['index']:04d}_{rec['id']}.jpg"))
            self.d[i] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return self.d[i]


_segc = {}


def seg_labels(P, pose, rec):
    """Segmentation label (dataset views) of world points P for one panorama; -1 if in no view."""
    lab = np.full(len(P), -1, np.int16)
    for pitch in (0, 25):
        for dn, rel in camera.VIEW_REL.items():
            todo = lab < 0
            if not todo.any():
                return lab
            c, r, ok = camera.world_to_view(P[todo], pose["pos"], pose["R"], rec, rel, pitch)
            inb = ok & (c >= 0) & (c < 1600) & (r >= 0) & (r < 1200)
            if not inb.any():
                continue
            f = os.path.join(WORK, "seg", f"{rec['index']:04d}_{rec['id']}_{dn}_p{pitch:02d}.png")
            if f not in _segc:
                if len(_segc) > 64:
                    _segc.clear()
                _segc[f] = np.asarray(Image.open(f)) if os.path.exists(f) else None
            s = _segc[f]
            if s is None:
                continue
            idx = np.where(todo)[0][inb]
            lab[idx] = s[r[inb].astype(int), c[inb].astype(int)]
    return lab


def occluded(P, cam, dsm, margin=0.35, n=18, skip=0.8):
    d = P - cam
    L = np.linalg.norm(d[:, :2], axis=1)
    occ = np.zeros(len(P), bool)
    for t in np.linspace(0.05, 1.0, n):
        Q = cam + d * t
        near_end = L * (1 - t) < skip
        z = dsm.sample(Q[:, 0], Q[:, 1])
        occ |= (z > Q[:, 2] + margin) & ~near_end
    return occ


def texture_ribbon(pts, zb, zt, out_side, poses, cache, dsm, tex=0.02, maxd=30.0):
    """pts (n,2) polyline, zb/zt (n,) base/top, out_side: +1 = texture the left side of the
    polyline direction, -1 = right side. Returns RGB image (H, W) and (u_len, v0, v_len)."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    L = s[-1]
    v0, v1 = float(zb.min()), float(zt.max())
    W = max(2, int(np.ceil(L / tex)))
    H = max(2, int(np.ceil((v1 - v0) / tex)))
    if W * H > 4_000_000:                                   # cap memory: coarser texels on huge walls
        tex *= math.sqrt(W * H / 4_000_000)
        W = max(2, int(np.ceil(L / tex)))
        H = max(2, int(np.ceil((v1 - v0) / tex)))
    us = (np.arange(W) + 0.5) * tex
    vs = v1 - (np.arange(H) + 0.5) * tex                              # row 0 = top
    X = np.interp(us, s, pts[:, 0]); Y = np.interp(us, s, pts[:, 1])
    T = np.column_stack([np.gradient(X), np.gradient(Y)])
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Nrm = out_side * np.column_stack([-T[:, 1], T[:, 0]])
    ZB = np.interp(us, s, zb); ZT = np.interp(us, s, zt)
    P = np.stack(np.broadcast_arrays(X[None, :], Y[None, :], vs[:, None]), -1).reshape(-1, 3)
    P[:, :2] += np.repeat(Nrm[None], H, 0).reshape(-1, 2) * 0.03       # just in front of the surface
    inside = ((vs[:, None] >= ZB[None, :] - 0.05) & (vs[:, None] <= ZT[None, :] + 0.05)).ravel()
    NN = np.repeat(Nrm[None], H, 0).reshape(-1, 2)
    best_score = np.zeros(len(P))
    best_i = np.full(len(P), -1)
    colors = np.zeros((len(P), 3), np.uint8)
    ctr = np.array([X.mean(), Y.mean()])
    dmin_cam = np.array([np.min(np.hypot(X - p["pos"][0], Y - p["pos"][1])) for p in poses])
    order = np.argsort(dmin_cam)
    cand = [poses[i] for i in order[:16] if dmin_cam[i] < maxd]
    per_pano = []
    for p in cand:
        cam = np.array(p["pos"])
        d = P - cam
        dist = np.linalg.norm(d, axis=1)
        dh = d[:, :2] / np.maximum(np.linalg.norm(d[:, :2], axis=1, keepdims=True), 1e-9)
        cosi = -(dh * NN).sum(1)
        ok = inside & (cosi > 0.25) & (dist < maxd) & (dist > 1.5)
        if ok.sum() < 20:
            continue
        idx = np.where(ok)[0]
        occ = occluded(P[idx], cam, dsm)
        idx = idx[~occ]
        if len(idx) < 20:
            continue
        rec = cache.D[p["index"]]
        lab = seg_labels(P[idx], p, rec)
        idx = idx[~np.isin(lab, list(REJECT))]
        if len(idx) < 20:
            continue
        score = np.zeros(len(P), np.float32); score[idx] = cosi[idx] ** 2 / np.maximum(dist[idx], 2.0)
        per_pano.append((p, score))
    if not per_pano:
        return None, (L, v0, v1 - v0)
    # block-wise choice
    S = np.stack([sc.reshape(H, W) for _, sc in per_pano])            # (k, H, W)
    hb, wb = int(np.ceil(H / BLOCK)), int(np.ceil(W / BLOCK))
    pad = np.zeros((len(per_pano), hb * BLOCK, wb * BLOCK), np.float32); pad[:, :H, :W] = S
    blk = pad.reshape(len(per_pano), hb, BLOCK, wb, BLOCK).mean((2, 4))
    choice = np.argmax(blk, 0)
    choice_px = np.repeat(np.repeat(choice, BLOCK, 0), BLOCK, 1)[:H, :W].ravel()
    valid_any = S.max(0).ravel() > 0
    img = np.zeros((H * W, 3), np.uint8)
    have = np.zeros(H * W, bool)
    for k, (p, sc) in enumerate(per_pano):
        use = (choice_px == k) & (sc > 0)
        # texels whose block choice cannot see them: take the best other panorama
        if not use.any():
            continue
        pano = cache.get(p["index"])
        Hi, Wi = pano.shape[:2]
        dc = (P[use] - np.array(p["pos"])) @ np.array(p["R"])
        lon = np.arctan2(dc[:, 0], dc[:, 1])
        lat = np.arcsin(np.clip(dc[:, 2] / np.linalg.norm(dc, axis=1), -1, 1))
        u = (lon + np.pi) / (2 * np.pi) * Wi - 0.5
        v = (np.pi / 2 - lat) / np.pi * Hi - 0.5
        img[use] = np.stack([map_coordinates(pano[..., c], [v, u % Wi], order=1, mode="wrap") for c in range(3)], -1)
        have |= use
    rest = valid_any & ~have
    if rest.any():
        k_best = np.argmax(S.reshape(len(per_pano), -1)[:, rest], 0)
        for k in np.unique(k_best):
            p = per_pano[k][0]
            sel = np.where(rest)[0][k_best == k]
            pano = cache.get(p["index"])
            Hi, Wi = pano.shape[:2]
            dc = (P[sel] - np.array(p["pos"])) @ np.array(p["R"])
            lon = np.arctan2(dc[:, 0], dc[:, 1])
            lat = np.arcsin(np.clip(dc[:, 2] / np.linalg.norm(dc, axis=1), -1, 1))
            u = (lon + np.pi) / (2 * np.pi) * Wi - 0.5
            v = (np.pi / 2 - lat) / np.pi * Hi - 0.5
            img[sel] = np.stack([map_coordinates(pano[..., c], [v, u % Wi], order=1, mode="wrap") for c in range(3)], -1)
            have[sel] = True
    img = img.reshape(H, W, 3)
    have = have.reshape(H, W)
    if have.any():
        med = np.median(img[have], 0).astype(np.uint8)
        dist_t, (ri, ci) = distance_transform_edt(~have, return_indices=True)
        filled = img[ri, ci]
        far = dist_t > 12
        filled[far] = med
        img = filled
        # soften the far fill
        img = np.where(far[..., None], cv2.GaussianBlur(img, (0, 0), 3), img)
    return img, (L, v0, v1 - v0)


class Atlas:
    """Shelf packer for texture rectangles."""

    def __init__(self, size=4096, pad=2):
        self.size, self.pad = size, pad
        self.pages = []
        self._new()

    def _new(self):
        self.pages.append(np.full((self.size, self.size, 3), 128, np.uint8))
        self.x = self.y = self.row_h = 0

    def add(self, img):
        h, w = img.shape[:2]
        if w + 2 * self.pad > self.size or h + 2 * self.pad > self.size:
            k = (self.size - 2 * self.pad) / max(w, h)
            img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]
        if self.x + w + 2 * self.pad > self.size:
            self.x = 0; self.y += self.row_h; self.row_h = 0
        if self.y + h + 2 * self.pad > self.size:
            self._new()
        x0, y0 = self.x + self.pad, self.y + self.pad
        page = self.pages[-1]
        page[y0:y0 + h, x0:x0 + w] = img
        page[y0 - self.pad:y0, x0:x0 + w] = img[:1]; page[y0 + h:y0 + h + self.pad, x0:x0 + w] = img[-1:]
        page[y0 - self.pad:y0 + h + self.pad, x0 - self.pad:x0] = page[y0 - self.pad:y0 + h + self.pad, x0:x0 + 1]
        page[y0 - self.pad:y0 + h + self.pad, x0 + w:x0 + w + self.pad] = page[y0 - self.pad:y0 + h + self.pad, x0 + w - 1:x0 + w]
        self.x += w + 2 * self.pad
        self.row_h = max(self.row_h, h + 2 * self.pad)
        S = float(self.size)
        return len(self.pages) - 1, (x0 / S, y0 / S, w / S, h / S)


def facade_groups(tris, ang_tol=6.0, off_tol=0.35):
    """Group wall triangles (n,3,3) of one building into planar facades.
    Returns list of (indices, unit normal (outward), plane offset)."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    nrm = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    nh = nrm.copy(); nh[:, 2] = 0
    nh /= np.maximum(np.linalg.norm(nh, axis=1, keepdims=True), 1e-12)
    groups = []
    used = np.zeros(len(tris), bool)
    order = np.argsort(-area)
    ctr = tris.mean(1)
    for i in order:
        if used[i] or area[i] < 1e-4:
            continue
        d0 = (ctr[i] * nh[i]).sum()
        same = (~used) & ((nh @ nh[i]) > math.cos(math.radians(ang_tol))) & (np.abs((ctr * nh[i]).sum(1) - d0) < off_tol)
        idx = np.where(same)[0]
        used[idx] = True
        groups.append((idx, nh[i], d0))
    return groups


def texture_planar(tris, normal, poses, cache, dsm, tex=0.04, maxd=40.0, expect=(17, 6, 3, 16)):
    """Texture of a planar vertical facade (triangles (n,3,3), outward horizontal normal).
    u = horizontal coordinate along the facade, v = height. Returns img, (u0, ulen, v0, vlen, axis_u)."""
    axis_u = np.array([-normal[1], normal[0], 0.0])
    P = tris.reshape(-1, 3)
    u = P @ axis_u
    u0, u1 = u.min(), u.max()
    v0, v1 = P[:, 2].min(), P[:, 2].max()
    W = max(2, int(np.ceil((u1 - u0) / tex))); H = max(2, int(np.ceil((v1 - v0) / tex)))
    if W * H > 6_000_000:
        k = math.sqrt(W * H / 6_000_000)
        tex *= k
        W = max(2, int(np.ceil((u1 - u0) / tex))); H = max(2, int(np.ceil((v1 - v0) / tex)))
    uu = u0 + (np.arange(W) + 0.5) * tex
    vv = v1 - (np.arange(H) + 0.5) * tex
    d0 = (tris.reshape(-1, 3)[:, :2] @ normal[:2]).mean()
    base = normal[:2] * d0
    UU, VV = np.meshgrid(uu, vv)
    Pw = np.stack([base[0] + UU * axis_u[0], base[1] + UU * axis_u[1], VV], -1).reshape(-1, 3)
    Pw[:, :2] += normal[:2] * 0.05
    # texels inside the facade polygon (rasterise triangles in (u, v))
    import cv2 as _cv
    mask = np.zeros((H, W), np.uint8)
    for t in tris:
        tu = (t @ axis_u - u0) / tex; tv = (v1 - t[:, 2]) / tex
        _cv.fillPoly(mask, [np.round(np.column_stack([tu, tv]) * 4).astype(np.int32)], 1, shift=2)
    inside = mask.ravel() > 0
    return _texture_points(Pw, inside, normal[:2], H, W, poses, cache, dsm, maxd), (u0, u1 - u0, v0, v1 - v0, axis_u)


def _texture_points(P, inside, nrm2, H, W, poses, cache, dsm, maxd):
    ctr = P[inside].mean(0) if inside.any() else P.mean(0)
    cand = [p for p in poses if np.hypot(p["pos"][0] - ctr[0], p["pos"][1] - ctr[1]) < maxd + 20]
    per = []
    for p in cand:
        cam = np.array(p["pos"])
        d = P - cam
        dist = np.linalg.norm(d, axis=1)
        dh = d[:, :2] / np.maximum(np.linalg.norm(d[:, :2], axis=1, keepdims=True), 1e-9)
        cosi = -(dh @ nrm2)
        ok = inside & (cosi > 0.2) & (dist < maxd) & (dist > 2.0)
        if ok.sum() < 30:
            continue
        idx = np.where(ok)[0]
        idx = idx[~occluded(P[idx], cam, dsm)]
        if len(idx) < 30:
            continue
        lab = seg_labels(P[idx], p, cache.D[p["index"]])
        idx = idx[~np.isin(lab, list(REJECT))]
        if len(idx) < 30:
            continue
        sc = np.zeros(len(P)); sc[idx] = cosi[idx] ** 2 / np.maximum(dist[idx], 3.0)
        per.append((p, sc))
    if not per:
        return None
    S = np.stack([sc.reshape(H, W) for _, sc in per])
    hb, wb = int(np.ceil(H / BLOCK)), int(np.ceil(W / BLOCK))
    pad = np.zeros((len(per), hb * BLOCK, wb * BLOCK)); pad[:, :H, :W] = S
    choice = np.argmax(pad.reshape(len(per), hb, BLOCK, wb, BLOCK).mean((2, 4)), 0)
    choice_px = np.repeat(np.repeat(choice, BLOCK, 0), BLOCK, 1)[:H, :W].ravel()
    Sf = S.reshape(len(per), -1)
    fallback = np.argmax(Sf, 0)
    ok_block = Sf[choice_px, np.arange(H * W)] > 0
    pick = np.where(ok_block, choice_px, fallback)
    valid = Sf.max(0) > 0
    img = np.zeros((H * W, 3), np.uint8)
    for k, (p, _) in enumerate(per):
        sel = np.where(valid & (pick == k))[0]
        if not len(sel):
            continue
        pano = cache.get(p["index"])
        Hi, Wi = pano.shape[:2]
        dc = (P[sel] - np.array(p["pos"])) @ np.array(p["R"])
        lon = np.arctan2(dc[:, 0], dc[:, 1])
        lat = np.arcsin(np.clip(dc[:, 2] / np.linalg.norm(dc, axis=1), -1, 1))
        uu = (lon + np.pi) / (2 * np.pi) * Wi - 0.5
        vv = (np.pi / 2 - lat) / np.pi * Hi - 0.5
        img[sel] = np.stack([map_coordinates(pano[..., c], [vv, uu % Wi], order=1, mode="wrap") for c in range(3)], -1)
    img = img.reshape(H, W, 3)
    have = valid.reshape(H, W)
    if not have.any():
        return None
    med = np.median(img[have], 0).astype(np.uint8)
    dist_t, (ri, ci) = distance_transform_edt(~have, return_indices=True)
    filled = img[ri, ci]
    far = dist_t > 10
    filled[far] = med
    return np.where(far[..., None], cv2.GaussianBlur(filled, (0, 0), 3), filled), float(have[inside.reshape(H, W)].mean())
