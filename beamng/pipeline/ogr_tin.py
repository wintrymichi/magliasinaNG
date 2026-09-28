"""Read TIN / MultiPatch layers (swissBUILDINGS3D FileGDB) without the GDAL Python bindings.

extract_buildings.py uses osgeo.ogr when it is installed (the Windows build environment). Elsewhere
the GDAL library bundled with pyogrio is called through ctypes: pyogrio itself refuses layers of
type TIN Z. Features come back as (fields dict, triangles (n, 3, 3)).
"""
import ctypes, glob, os, struct
import numpy as np

_lib = None


def lib():
    global _lib
    if _lib is None:
        import pyogrio
        d = os.path.join(os.path.dirname(os.path.dirname(pyogrio.__file__)), "pyogrio.libs")
        path = sorted(glob.glob(os.path.join(d, "libgdal*.so*")) + glob.glob(os.path.join(d, "gdal*.dll")))[0]
        L = ctypes.CDLL(path)
        L.GDALAllRegister()
        L.GDALOpenEx.restype = ctypes.c_void_p
        L.GDALOpenEx.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        L.GDALDatasetGetLayerByName.restype = ctypes.c_void_p
        L.GDALDatasetGetLayerByName.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        L.OGR_L_ResetReading.argtypes = [ctypes.c_void_p]
        L.OGR_L_GetNextFeature.restype = ctypes.c_void_p
        L.OGR_L_GetNextFeature.argtypes = [ctypes.c_void_p]
        L.OGR_F_GetGeometryRef.restype = ctypes.c_void_p
        L.OGR_F_GetGeometryRef.argtypes = [ctypes.c_void_p]
        L.OGR_F_GetFieldIndex.restype = ctypes.c_int
        L.OGR_F_GetFieldIndex.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        L.OGR_F_GetFieldAsString.restype = ctypes.c_char_p
        L.OGR_F_GetFieldAsString.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.OGR_F_IsFieldSetAndNotNull.restype = ctypes.c_int
        L.OGR_F_IsFieldSetAndNotNull.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.OGR_F_Destroy.argtypes = [ctypes.c_void_p]
        L.OGR_G_WkbSize.restype = ctypes.c_int
        L.OGR_G_WkbSize.argtypes = [ctypes.c_void_p]
        L.OGR_G_ExportToIsoWkb.restype = ctypes.c_int
        L.OGR_G_ExportToIsoWkb.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        L.GDALClose.argtypes = [ctypes.c_void_p]
        _lib = L
    return _lib


def _triangles(wkb):
    """Triangles (n, 3, 3) of an ISO WKB geometry: TIN, Triangle, Polygon (fan) and collections."""
    out = []

    def geom(o):
        order = "<" if wkb[o] == 1 else ">"
        t = struct.unpack(order + "I", wkb[o + 1:o + 5])[0]
        o += 5
        base, dim = t % 1000, (3 if t // 1000 in (1, 3) else 2) + (1 if t // 1000 in (2, 3) else 0)
        if base in (3, 17):                                     # Polygon, Triangle
            nr = struct.unpack(order + "I", wkb[o:o + 4])[0]
            o += 4
            for k in range(nr):
                n = struct.unpack(order + "I", wkb[o:o + 4])[0]
                o += 4
                P = np.frombuffer(wkb, order + "f8", n * dim, o).reshape(n, dim)[:, :3]
                o += 8 * n * dim
                if k == 0 and n >= 4:
                    ring = P[:-1] if np.allclose(P[0], P[-1]) else P
                    for i in range(1, len(ring) - 1):         # fan (triangles and planar quads)
                        out.append(np.stack([ring[0], ring[i], ring[i + 1]]))
            return o
        if base in (6, 7, 15, 16):                             # MultiPolygon, Collection, PolyhedralSurface, TIN
            n = struct.unpack(order + "I", wkb[o:o + 4])[0]
            o += 4
            for _ in range(n):
                o = geom(o)
            return o
        raise ValueError(f"WKB type {t}")
    geom(0)
    return np.array(out, np.float64).reshape(-1, 3, 3)


def read_tin_layer(path, layer, fields):
    """Yields ({field: value}, triangles (n, 3, 3) LV95) for every feature of a layer."""
    L = lib()
    ds = L.GDALOpenEx(path.encode(), 0x04, None, None, None)          # GDAL_OF_VECTOR
    if not ds:
        raise IOError(path)
    try:
        lay = L.GDALDatasetGetLayerByName(ds, layer.encode())
        if not lay:
            return
        L.OGR_L_ResetReading(lay)
        while True:
            f = L.OGR_L_GetNextFeature(lay)
            if not f:
                break
            try:
                g = L.OGR_F_GetGeometryRef(f)
                if not g:
                    continue
                n = L.OGR_G_WkbSize(g)
                buf = ctypes.create_string_buffer(n)
                L.OGR_G_ExportToIsoWkb(g, 1, buf)
                tris = _triangles(buf.raw)
                props = {}
                for name in fields:
                    i = L.OGR_F_GetFieldIndex(f, name.encode())
                    props[name] = (L.OGR_F_GetFieldAsString(f, i).decode("utf-8", "replace")
                                   if i >= 0 and L.OGR_F_IsFieldSetAndNotNull(f, i) else None)
                yield props, tris
            finally:
                L.OGR_F_Destroy(f)
    finally:
        L.GDALClose(ds)
