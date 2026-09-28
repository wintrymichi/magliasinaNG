"""swissTLM3D (swisstopo topographic landscape model, 3D) for the playable area.

The national package is a 4-5 GB zip; only a few of its shapefiles are needed and only the
features in the area, so the zip is read over HTTP range requests and the members are parsed
while they stream (no local copy of the package):
  TLM_STRASSE            roads and paths: class (OBJEKTART), surface (BELAGSART), bridge or
                         tunnel (KUNSTBAUTE), level (STUFE), 3D line (the z of a bridge is its deck)
  TLM_EISENBAHN          railways (the Lugano-Ponte Tresa line crosses the area)
  TLM_FLIESSGEWAESSER    streams (the gaps that bridges cross)
Output: data/tlm/<layer>.json: {"fields": [...], "features": [{"props": {...}, "parts": [[[E, N, Z], ...]]}]}
(LV95 / LN02).
"""
import io, json, os, struct, sys, time, zipfile
import numpy as np
import requests
from config import DATA, local_to_lv95
import area

URL = ("https://data.geo.admin.ch/ch.swisstopo.swisstlm3d/swisstlm3d_2026-02/"
       "swisstlm3d_2026-02_2056_5728.shp.zip")
LAYERS = {"TLM_STRASSE": "TLM_STRASSEN\\swissTLM3D_TLM_STRASSE",
          "TLM_EISENBAHN": "TLM_OEV\\swissTLM3D_TLM_EISENBAHN",
          "TLM_FLIESSGEWAESSER": "TLM_GEWAESSER\\swissTLM3D_TLM_FLIESSGEWAESSER"}
MARGIN = 300.0


class RangeFile(io.RawIOBase):
    """A remote file read with HTTP range requests (seekable, for zipfile)."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        self.size = int(requests.head(url, timeout=60).headers["content-length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        for attempt in range(6):
            try:
                r = requests.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=120)
                r.raise_for_status()
                data = r.content
                break
            except Exception as e:
                print("retry range", self.pos, e, flush=True)
                time.sleep(3 * (attempt + 1))
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


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


def main():
    out_dir = os.path.join(DATA, "tlm")
    os.makedirs(out_dir, exist_ok=True)
    x0, y0, x1, y1 = area.bounds(MARGIN)
    ce = [local_to_lv95(x, y) for x in (x0, x1) for y in (y0, y1)]
    bbox = (min(p[0] for p in ce), min(p[1] for p in ce), max(p[0] for p in ce), max(p[1] for p in ce))
    z = zipfile.ZipFile(io.BufferedReader(RangeFile(URL), buffer_size=1 << 22))
    names = {n.replace("/", "\\"): n for n in z.namelist()}
    for layer, stem in LAYERS.items():
        dest = os.path.join(out_dir, layer + ".json")
        if os.path.exists(dest):
            print(layer, "exists", flush=True)
            continue
        t = time.time()
        with z.open(names[stem + ".shp"]) as f:
            geoms = dict(shp_records(io.BufferedReader(f, 1 << 22), bbox))
        with z.open(names[stem + ".dbf"]) as f:
            fields, props = dbf_records(io.BufferedReader(f, 1 << 22), geoms.keys())
        feats = [{"props": props.get(i, {}), "parts": [np.round(p, 3).tolist() for p in parts]}
                 for i, parts in sorted(geoms.items())]
        json.dump({"fields": fields, "bbox_lv95": bbox, "features": feats}, open(dest + ".part", "w"))
        os.replace(dest + ".part", dest)
        print(layer, len(feats), "features in %.0f s" % (time.time() - t), flush=True)


if __name__ == "__main__":
    main()
