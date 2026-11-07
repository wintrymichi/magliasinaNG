"""The tunnels, galleries and underpasses of swissTLM3D over all of Ticino (roads and railways), for the tunnel module
(tunnels.py). The cloud sessions cannot reach swisstopo: tunnels_ref.yml runs this on GitHub and commits the result.

Output: dati/tunnels_tlm.json.gz {"bbox_lv95", "roads": {"fields", "features"}, "rail": {...}}, every feature a line
(LV95 / LN02, z = the line's own height, the carriageway or the rail in the tunnel) with its props.
"""
import gzip, io, json, os, sys, time, zipfile
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import download_tlm as tlm                     # noqa: E402

# Canton Ticino with a margin (Moesano and the Italian border lakes included): LV95
BBOX = (2670000.0, 1068000.0, 2738000.0, 1170000.0)
KINDS = {"Tunnel", "Galerie", "Unterfuehrung", "Unterfuehrung mit Treppe"}
LAYERS = {"roads": "TLM_STRASSE", "rail": "TLM_EISENBAHN"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati", "tunnels_tlm.json.gz")


def main():
    z = zipfile.ZipFile(io.BufferedReader(tlm.RangeFile(tlm.URL), buffer_size=1 << 22))
    names = {n.replace("/", "\\"): n for n in z.namelist()}
    out = {"bbox_lv95": BBOX, "source": tlm.URL}
    for key, layer in LAYERS.items():
        stem = tlm.LAYERS[layer]
        t = time.time()
        with z.open(names[stem + ".shp"]) as f:
            geoms = dict(tlm.shp_records(io.BufferedReader(f, 1 << 22), BBOX))
        with z.open(names[stem + ".dbf"]) as f:
            fields, props = tlm.dbf_records(io.BufferedReader(f, 1 << 22), geoms.keys())
        feats = [{"props": props[i], "parts": [np.round(p, 2).tolist() for p in parts]}
                 for i, parts in sorted(geoms.items()) if props.get(i, {}).get("KUNSTBAUTE") in KINDS]
        out[key] = {"fields": fields, "features": feats}
        kinds = {}
        for f in feats:
            k = f["props"]["KUNSTBAUTE"]
            kinds[k] = kinds.get(k, 0) + 1
        print(layer, len(geoms), "lines in the box,", len(feats), "kept", kinds, "%.0f s" % (time.time() - t), flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt") as f:
        json.dump(out, f)
    print("written", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
