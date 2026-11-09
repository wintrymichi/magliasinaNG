"""Generated textures kept between builds (switzerlandNG faster builds, 2026-11-09).

Some steps draw the same procedural textures in every build (the skin's bank and rock: 32 s, twice a build). get()
keeps what a maker returns ({file name: bytes}) in MAGLIASO_TEXTURE_CACHE (the Switzerland Builder sets it to its
cache folder), keyed by the source files that draw them and the library versions: the same bytes as drawing them
again. Without MAGLIASO_TEXTURE_CACHE the maker runs every time, as before.
"""
import hashlib
import os
import pickle


def key(name, sources):
    import numpy as np
    import PIL
    import scipy
    h = hashlib.sha1(name.encode())
    for s in sources:
        h.update(open(os.path.abspath(s), "rb").read())
    h.update(("%s %s %s" % (np.__version__, scipy.__version__, PIL.__version__)).encode())
    return "%s_%s" % (name, h.hexdigest()[:16])


def get(name, make, sources):
    """make() -> {file name: bytes}, from the cache when it holds this name drawn by the same sources."""
    cache = os.environ.get("MAGLIASO_TEXTURE_CACHE")
    if not cache:
        return make()
    p = os.path.join(cache, key(name, sources) + ".pkl")
    if os.path.exists(p):
        try:
            out = pickle.load(open(p, "rb"))
            print("textures %s kept from an earlier build" % name, flush=True)
            return out
        except Exception as e:                      # a broken file: drawn again
            print("textures %s: cache not read (%s)" % (name, e), flush=True)
    out = make()
    try:
        os.makedirs(cache, exist_ok=True)
        with open(p + ".part", "wb") as f:
            pickle.dump(out, f, protocol=4)
        os.replace(p + ".part", p)
    except OSError as e:
        print("textures %s not kept: %s" % (name, e), flush=True)
    return out
