"""The road and path network of the playable area (v2.0), from swissTLM3D.

Every TLM_STRASSE line in the area (roads of every class, paths, mule tracks, stairs, fords and
bridges; not tunnels and underpasses) becomes a segment between two nodes; lines meet at shared
end points (swissTLM3D is noded at junctions; lines that only cross, like a road on a bridge over
another, stay apart). Segments are sampled into stations every STEP m.
Station width: the surveyed carriageway (MU 'strada_sentiero' polygons) measured with rays from the
line where it runs inside one (the line is moved to the middle of it when it is off by less than
MAX_SHIFT), otherwise the nominal width of the swissTLM3D class.
Output: work/network.npz (stations and segments) and work/network.json (summary).
"""
import json, os, pickle
import numpy as np
import shapely
from scipy.ndimage import median_filter
from scipy.spatial import cKDTree
from config import DATA, WORK, lv95_to_local
import area

STEP = 2.0              # m between stations
SNAP = 0.6              # m, line ends closer than this are one node
CLIP = 30.0             # m, the network continues this far beyond the area
MAX_SHIFT = 1.5         # m, largest move of a line onto the middle of the surveyed carriageway
# class: (nominal width m, kind, smoothing wavelength of the profile m)
CLASSES = {
    "Autobahn": (11.0, "road", 60.0), "Autostrasse": (9.0, "road", 55.0), "Ausfahrt": (6.0, "road", 40.0),
    "Einfahrt": (6.0, "road", 40.0), "Raststaette": (6.0, "road", 30.0), "Verbindung": (5.0, "road", 30.0),
    "10m Strasse": (10.0, "road", 50.0), "8m Strasse": (8.0, "road", 48.0), "6m Strasse": (6.0, "road", 45.0),
    "4m Strasse": (4.5, "road", 38.0), "3m Strasse": (3.2, "road", 30.0), "Zufahrt": (4.0, "road", 25.0),
    "Dienstzufahrt": (4.0, "road", 25.0), "Platz": (6.0, "road", 25.0), "Markierte Spur": (2.0, "path", 16.0),
    "2m Weg": (2.0, "path", 16.0), "2m Wegfragment": (2.0, "path", 16.0),
    "1m Weg": (1.3, "path", 12.0), "1m Wegfragment": (1.3, "path", 12.0),
}
SKIP = {"Tunnel", "Unterfuehrung", "Unterfuehrung mit Treppe", "Galerie"}
BRIDGE = {"Bruecke", "Bruecke mit Treppe", "Steg", "Bruecke mit Galerie"}


def load_lines():
    """swissTLM3D lines in the area: [(props, (n, 3) local x, y, z)], each cut to the area + CLIP."""
    d = json.load(open(os.path.join(DATA, "tlm", "TLM_STRASSE.json")))
    keep = area.polygon().buffer(CLIP)
    shapely.prepare(keep)
    out = []
    for f in d["features"]:
        p = f["props"]
        if p.get("OBJEKTART") not in CLASSES or p.get("KUNSTBAUTE") in SKIP:
            continue
        for part in f["parts"]:
            P = np.array(part, np.float64)
            if len(P) < 2:
                continue
            x, y = lv95_to_local(P[:, 0], P[:, 1])
            Q = np.column_stack([x, y, P[:, 2]])
            # cut to the area: runs of densified points inside it
            Qd = densify(Q, 1.0)
            ins = shapely.contains_xy(keep, Qd[:, 0], Qd[:, 1])
            if not ins.any():
                continue
            if ins.all():
                out.append((p, Q))
                continue
            edges = np.flatnonzero(np.diff(np.r_[0, ins.astype(int), 0]))
            for a, b in zip(edges[::2], edges[1::2]):
                if b - a >= 3:
                    out.append((p, Qd[a:b]))
    return out


def densify(P, step):
    """Points along the polyline P (n, k) at most `step` apart (original vertices kept)."""
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(int(np.ceil(np.linalg.norm(b[:2] - a[:2]) / step)), 1)
        t = np.arange(1, n + 1)[:, None] / n
        out.append(a + (b - a) * t)
    return np.concatenate(out)


def resample(P, step):
    """Stations every ~step m along P (n, 3): (m, 3) points and their arc length."""
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))]
    n = max(int(np.round(d[-1] / step)), 1)
    s = np.linspace(0, d[-1], n + 1)
    Q = np.column_stack([np.interp(s, d, P[:, k]) for k in range(P.shape[1])])
    return Q, s


def nodes_of(lines):
    """Node id of both ends of every line (ends closer than SNAP are one node) and node positions."""
    ends = np.array([[L[0, :2], L[-1, :2]] for _, L in lines]).reshape(-1, 2)
    tree = cKDTree(ends)
    parent = np.arange(len(ends))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i, j in tree.query_pairs(SNAP):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    roots = np.array([find(i) for i in range(len(ends))])
    _, nid = np.unique(roots, return_inverse=True)
    pos = np.zeros((nid.max() + 1, 2))
    cnt = np.zeros(nid.max() + 1)
    np.add.at(pos, nid, ends)
    np.add.at(cnt, nid, 1)
    return nid.reshape(-1, 2), pos / cnt[:, None]


def av_carriageway():
    """Union of the surveyed carriageways (MU strada_sentiero) and a tree of its parts."""
    av = pickle.load(open(os.path.join(WORK, "av_local.pkl"), "rb"))
    polys = [g for g, _ in av["LCSF"].get("strada_sentiero", [])]
    return polys


def measure_width(P, N, polys, nominal):
    """Carriageway edges along the stations P (n, 2) with normals N from rays in the surveyed
    polygons: (width, offset of the middle along N) per station, NaN where the station is not
    inside a polygon or the edges are implausible."""
    tree = shapely.STRtree(polys)
    n = len(P)
    width, off = np.full(n, np.nan), np.full(n, np.nan)
    pts = shapely.points(P[:, 0], P[:, 1])
    hit = tree.query(pts, predicate="within")
    inside = np.zeros(n, bool)
    inside[hit[0]] = True
    if not inside.any():
        return width, off
    maxw = max(2.0 * nominal, 8.0)
    tt = np.arange(0.0, maxw, 0.1)
    union = shapely.union_all([polys[j] for j in np.unique(hit[1])])
    shapely.prepare(union)
    for sg in (1, -1):
        Q = P[inside, None, :] + sg * N[inside, None, :] * tt[None, :, None]
        ins = shapely.contains_xy(union, Q[..., 0].ravel(), Q[..., 1].ravel()).reshape(Q.shape[:2])
        first_out = np.where(ins.all(1), len(tt), np.argmin(ins, axis=1))
        dist = tt[np.clip(first_out, 0, len(tt) - 1)]
        dist[first_out >= len(tt)] = np.nan
        if sg == 1:
            dl = dist
        else:
            dr = dist
    w = dl + dr
    o = (dl - dr) / 2
    ok = (w > 0.5 * nominal) & (w < max(2.2 * nominal, 6.0)) & (np.abs(o) < MAX_SHIFT)
    width[np.flatnonzero(inside)[ok]] = w[ok]
    off[np.flatnonzero(inside)[ok]] = o[ok]
    return width, off


def build():
    lines = load_lines()
    ends, node_pos = nodes_of(lines)
    polys = av_carriageway()
    segs = []
    sx, sy, sz, sseg, sidx, snode, sw, sss = [], [], [], [], [], [], [], []
    count = 0
    for k, ((props, L), (na, nb)) in enumerate(zip(lines, ends)):
        cls = props["OBJEKTART"]
        nominal, kind, lc = CLASSES[cls]
        L = L.copy()
        L[0, :2], L[-1, :2] = node_pos[na], node_pos[nb]
        Q, s = resample(L, STEP)
        if len(Q) < 2:
            continue
        T = np.gradient(Q[:, :2], axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        N = np.column_stack([-T[:, 1], T[:, 0]])
        width, off = measure_width(Q[:, :2], N, polys, nominal) if kind == "road" else (np.full(len(Q), np.nan),) * 2
        # smooth the measurements along the line; ends stay on the nodes
        good = ~np.isnan(width)
        if good.sum() >= 3:
            wf = np.where(good, width, np.nanmedian(width))
            of = np.where(good, off, 0.0)
            wf = median_filter(wf, 7, mode="nearest")
            of = median_filter(of, 7, mode="nearest")
            of[:3], of[-3:] = 0.0, 0.0
            Q[:, :2] += N * of[:, None]
            width = np.where(good, wf, nominal)
        else:
            width = np.full(len(Q), nominal)
        structure = props.get("KUNSTBAUTE") or "Keine"
        segs.append({"id": len(segs), "tlm": props.get("UUID"), "class": cls, "kind": kind, "lc": lc,
                     "surface": "hard" if props.get("BELAGSART") == "Hart" else "natural",
                     "structure": structure, "bridge": structure in BRIDGE, "stairs": "Treppe" in structure,
                     "level": int(props.get("STUFE") or 0), "name": props.get("STRNAME") or props.get("NAME") or "",
                     "nodes": [int(na), int(nb)], "length": float(s[-1]), "n": len(Q), "first": count})
        count += len(Q)
        sx.append(Q[:, 0]); sy.append(Q[:, 1]); sz.append(Q[:, 2]); sss.append(s)
        sseg.append(np.full(len(Q), len(segs) - 1)); sidx.append(np.arange(len(Q)))
        nd = np.full(len(Q), -1)
        nd[0], nd[-1] = na, nb
        snode.append(nd); sw.append(width)
    st = {k: np.concatenate(v) for k, v in (("x", sx), ("y", sy), ("z_tlm", sz), ("seg", sseg), ("idx", sidx),
                                              ("node", snode), ("width", sw), ("s", sss))}
    deg = np.bincount(np.array([s_["nodes"] for s_ in segs]).ravel(), minlength=len(node_pos))
    np.savez_compressed(os.path.join(WORK, "network.npz"), node_pos=node_pos, **st)
    json.dump(segs, open(os.path.join(WORK, "network.json"), "w"))
    km = {}
    for s_ in segs:
        km[s_["kind"]] = km.get(s_["kind"], 0) + s_["length"] / 1000
    print("network: %d segments, %d nodes (%d junctions, %d dead ends), %d stations; km %s; bridges %d" %
          (len(segs), len(node_pos), int((deg >= 3).sum()), int((deg == 1).sum()), len(st["x"]),
           {k: round(v, 1) for k, v in km.items()}, sum(s_["bridge"] for s_ in segs)))
    return segs, st, node_pos


def load():
    d = np.load(os.path.join(WORK, "network.npz"))
    segs = json.load(open(os.path.join(WORK, "network.json")))
    return segs, {k: d[k] for k in d.files if k != "node_pos"}, d["node_pos"]


if __name__ == "__main__":
    build()
