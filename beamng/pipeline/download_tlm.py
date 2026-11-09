"""swissTLM3D (swisstopo topographic landscape model, 3D) for the playable area.

The national package is a 4-5 GB zip; only a few of its shapefiles are needed and only the
features in the area, so the zip is read over HTTP range requests (no local copy of the package); the members it
needs are kept decompressed in data/tlm_pkg for the next builds (switzerlandNG faster builds, 2026-11-09):
  TLM_STRASSE            roads and paths: class (OBJEKTART), surface (BELAGSART), bridge or
                         tunnel (KUNSTBAUTE), level (STUFE), 3D line (the z of a bridge is its deck)
  TLM_EISENBAHN          railways (the Lugano-Ponte Tresa line crosses the area)
  TLM_FLIESSGEWAESSER    streams (the gaps that bridges cross)
  TLM_UEBRIGE_BAHN       cable cars and lifts (v3.0.40: the Miglieglia - Monte Lema cable car, landmarks.py)
  TLM_BODENBEDECKUNG     Switzerland Builder only: the land cover polygons (forest, lakes, rivers, rock, scree,
                         glaciers, wetlands) that landcover.py lays where the cadastral survey has nothing (the cantons
                         whose survey is not open on geodienste.ch); written without z
Output: data/tlm/<layer>.json: {"fields": [...], "features": [{"props": {...}, "parts": [[[E, N, Z], ...]]}]}
(LV95 / LN02).
"""
import io, json, os, struct, sys, time, zipfile
import numpy as np
import netio
from config import DATA, ZONE, local_to_lv95
import area

URL = ("https://data.geo.admin.ch/ch.swisstopo.swisstlm3d/swisstlm3d_2026-02/"
       "swisstlm3d_2026-02_2056_5728.shp.zip")
LAYERS = {"TLM_STRASSE": "TLM_STRASSEN\\swissTLM3D_TLM_STRASSE",
          "TLM_EISENBAHN": "TLM_OEV\\swissTLM3D_TLM_EISENBAHN",
          "TLM_FLIESSGEWAESSER": "TLM_GEWAESSER\\swissTLM3D_TLM_FLIESSGEWAESSER",
          "TLM_UEBRIGE_BAHN": "TLM_OEV\\swissTLM3D_TLM_UEBRIGE_BAHN"}
LAYERS_BUILDER = {"TLM_BODENBEDECKUNG": "TLM_BB\\swissTLM3D_TLM_BODENBEDECKUNG"}
FLAT = ("TLM_BODENBEDECKUNG",)      # polygons: east and north only
MARGIN = 300.0


class RangeFile(io.RawIOBase):
    """A remote file read with HTTP range requests (seekable, for zipfile). switzerlandNG faster builds (2026-11-09):
    CHUNK-sized ranges on kept-alive connections, and AHEAD of them fetched at once while the file is read straight
    on: one 4 MB request after the other took 583 s for the small Sisikon area while the other downloads ran beside
    it (84 s alone before)."""
    CHUNK = 8 << 20
    AHEAD = 4

    def __init__(self, url):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self.url, self.pos = url, 0
        self.size, _ = netio.head(url)
        if not self.size:
            raise netio.DownloadError("swissTLM3D: no size of %s (the server did not answer)" % url)
        self._pool = ThreadPoolExecutor(self.AHEAD)
        self._chunks = {}
        self._last = None

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().close()

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _get(self, k):
        a, b = k * self.CHUNK, min((k + 1) * self.CHUNK, self.size) - 1
        # netio: kept-alive session per thread, (connect, read) timeouts, the stall watchdog, resumed after a cut;
        # the bytes count into the step's percentage (PROG)
        return netio.get_range(self.url, a, b, PROG, what="swissTLM3D bytes %d-%d" % (a, b))

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        k = self.pos // self.CHUNK
        # read straight on (the chunk read last or the next): fetch AHEAD chunks beyond; a jump (zipfile looking
        # for its directory) fetches the one chunk only
        straight = self._last is not None and k in (self._last, self._last + 1)
        last_k = (self.size - 1) // self.CHUNK
        for kk in range(k, min(k + (self.AHEAD if straight else 1), last_k + 1)):
            if kk not in self._chunks:
                self._chunks[kk] = self._pool.submit(self._get, kk)
        for kk in [kk for kk in self._chunks if kk < k or kk > k + self.AHEAD]:
            self._chunks.pop(kk).cancel()
        data = self._chunks[k].result()          # get_range ends (a DownloadError at worst): no wait without end
        self._last = k
        off = self.pos - k * self.CHUNK
        n = min(len(b), len(data) - off)
        b[:n] = data[off:off + n]
        self.pos += n
        return n


def read_exact(f, n):
    out = bytearray()
    while len(out) < n:
        chunk = f.read(n - len(out))
        if not chunk:
            raise EOFError
        out += chunk
    return bytes(out)


def shp_records(f, bbox):
    """Stream a .shp: yields (index, parts) for the records whose box meets bbox; parts are
    arrays (n, 3) of E, N, Z."""
    head = read_exact(f, 100)
    total = struct.unpack(">i", head[24:28])[0] * 2
    pos, i = 100, 0
    e0, n0, e1, n1 = bbox
    while pos < total:
        rh = read_exact(f, 8)
        clen = struct.unpack(">i", rh[4:8])[0] * 2
        c = read_exact(f, clen)
        pos += 8 + clen
        st = struct.unpack("<i", c[:4])[0]
        if st in (3, 5, 13, 15, 23, 25):
            xmin, ymin, xmax, ymax = struct.unpack("<4d", c[4:36])
            if xmax >= e0 and xmin <= e1 and ymax >= n0 and ymin <= n1:
                npart, npt = struct.unpack("<2i", c[36:44])
                parts = struct.unpack(f"<{npart}i", c[44:44 + 4 * npart])
                o = 44 + 4 * npart
                xy = np.frombuffer(c, "<f8", 2 * npt, o).reshape(npt, 2)
                o += 16 * npt
                if st in (13, 15) and len(c) >= o + 16 + 8 * npt:
                    z = np.frombuffer(c, "<f8", npt, o + 16)
                else:
                    z = np.full(npt, np.nan)
                P = np.column_stack([xy, z])
                bounds = list(parts) + [npt]
                yield i, [P[bounds[k]:bounds[k + 1]] for k in range(npart)]
        i += 1


def dbf_records(f, keep):
    """Stream a .dbf: returns (field names, {index: {field: value}}) for the indices in keep."""
    h = read_exact(f, 32)
    nrec, hlen, rlen = struct.unpack("<IHH", h[4:12])
    fields = []
    rest = read_exact(f, hlen - 32)
    for k in range(0, len(rest) - 1, 32):
        d = rest[k:k + 32]
        if d[0] == 0x0D:
            break
        name = d[:11].split(b"\0")[0].decode("latin-1")
        fields.append((name, chr(d[11]), d[16]))
    out = {}
    keep = set(keep)
    for i in range(nrec):
        r = read_exact(f, rlen)
        if i not in keep:
            continue
        o, rec = 1, {}
        for name, typ, ln in fields:
            v = r[o:o + ln].decode("utf-8", "replace").strip()
            o += ln
            if typ in "NF":
                try:
                    v = float(v) if v else None
                    if v is not None and v == int(v):
                        v = int(v)
                except ValueError:
                    v = None
            rec[name] = v
        out[i] = rec
    return [n for n, _, _ in fields], out


# the members read from the national package, kept for the next builds (decompressed, named after the package): the
# Switzerland Builder's cache shares data/tlm_pkg between its builds (app/cache.py SHARED)
PKG = os.path.join(DATA, "tlm_pkg")
PKG_STEM = os.path.basename(URL).split(".")[0]
# the bytes read from the package by every layer (side by side): one percentage line for the step
PROG = netio.Progress("swissTLM3D")


def member(z, names, name):
    """The local copy of a package member (made from the package on the first build that needs it)."""
    dst = os.path.join(PKG, PKG_STEM + "__" + name.replace("\\", "/").split("/")[-1])
    if os.path.exists(dst) and os.path.getsize(dst) == z.getinfo(names[name]).file_size:
        return dst, False
    os.makedirs(PKG, exist_ok=True)
    info = z.getinfo(names[name])
    with PROG.lock:
        PROG.total += info.compress_size             # what this member costs over the network
    short = name.replace("\\", "/").split("/")[-1]
    netio.say("[download]   swissTLM3D %s: %s (%s unpacked)" % (short, netio.human(info.compress_size),
                                                              netio.human(info.file_size)))
    line = netio._FileLine("swissTLM3D " + short, info.file_size)
    with z.open(names[name]) as f, open(dst + ".part", "wb") as o:
        while True:
            c = f.read(1 << 22)
            if not c:
                break
            o.write(c)
            line.add(len(c))
    line.add(0, force=True)
    netio.replace(dst + ".part", dst)
    return dst, True


def layer_job(job):
    """One layer: its features over bbox into dest (data/tlm/<layer>.json). Every layer reads the package through a
    RangeFile of its own: the layers run side by side."""
    layer, stem, dest, bbox = job
    t = time.time()
    rf = RangeFile(URL)
    try:
        z = zipfile.ZipFile(io.BufferedReader(rf, buffer_size=1 << 22))
        names = {n.replace("/", "\\"): n for n in z.namelist()}
        # the file by its name, in whatever folder of the package (the folders have been renamed between releases);
        # a big layer comes in parts (TLM_BODENBEDECKUNG_OST and _WEST in the 2026-02 package: the builder's first
        # Vitznau and Montreux builds found no land cover and no lake, 2026-11-07)
        base = stem.split("\\")[-1].upper()
        stems = {}
        for n in names:
            b = n.upper().split("\\")[-1]
            for ext in (".SHP", ".DBF"):
                if b.endswith(ext) and (b[:-4] == base or b[:-4] in (base + "_OST", base + "_WEST")):
                    stems.setdefault(b[:-4], {})[ext] = n
        pairs = [(v[".SHP"], v[".DBF"]) for k, v in sorted(stems.items()) if ".SHP" in v and ".DBF" in v]
        if not pairs:
            print(layer, "not in the package:", [n for n in names if n.upper().endswith(".SHP")], flush=True)
            return
        dims = 2 if layer in FLAT else 3
        feats, fields, got = [], [], 0
        for shp, dbf in pairs:
            ps, new_s = member(z, names, shp)
            pd, new_d = member(z, names, dbf)
            got += new_s + new_d
            with open(ps, "rb") as f:
                geoms = dict(shp_records(io.BufferedReader(f, 1 << 22), bbox))
            with open(pd, "rb") as f:
                fields, props = dbf_records(io.BufferedReader(f, 1 << 22), geoms.keys())
            feats += [{"props": props.get(i, {}), "parts": [np.round(p[:, :dims], 3).tolist() for p in parts]}
                      for i, parts in sorted(geoms.items())]
            if len(pairs) > 1:
                print(layer, shp.split("\\")[-1], len(geoms), "features", flush=True)
    finally:
        rf.close()
    json.dump({"fields": fields, "bbox_lv95": bbox, "features": feats}, open(dest + ".part", "w"))
    os.replace(dest + ".part", dest)
    print(layer, len(feats), "features in %.0f s (%s)" % (time.time() - t, "from the package" if got else
                                                         "package files kept from an earlier build"), flush=True)


def main():
    from concurrent.futures import ThreadPoolExecutor
    out_dir = os.path.join(DATA, "tlm")
    os.makedirs(out_dir, exist_ok=True)
    x0, y0, x1, y1 = area.bounds(MARGIN)
    ce = [local_to_lv95(x, y) for x in (x0, x1) for y in (y0, y1)]
    bbox = (min(p[0] for p in ce), min(p[1] for p in ce), max(p[0] for p in ce), max(p[1] for p in ce))
    layers = dict(LAYERS)
    if ZONE and ZONE.get("builder"):
        layers.update(LAYERS_BUILDER)
    jobs = []
    for layer, stem in layers.items():
        dest = os.path.join(out_dir, layer + ".json")
        if os.path.exists(dest):
            print(layer, "exists", flush=True)
            continue
        jobs.append((layer, stem, dest, bbox))
    with ThreadPoolExecutor(max(1, len(jobs))) as pool:
        list(pool.map(layer_job, jobs))
    if PROG.total:
        PROG.done()


if __name__ == "__main__":
    main()
