"""Downloads shared by the builds: a tile, an OpenStreetMap or register extract fetched for one area is linked into
the next build that needs it instead of being fetched again (hard links on the same disk, a copy otherwise).

The pipeline's downloaders skip a file that is there already (download_swisstopo.fetch), so a build gets the cached
files linked into its data folder before its downloads, and gives its new files to the cache after them.
"""
import os
import shutil
import time

# data/<sub> folders whose files are the same for every area that needs them (tiles of a national grid, national
# packages, extracts); the rest of data/ (the area's survey, OSM cut, worldcover window) belongs to one build
SHARED = ("swissalti3d_05", "dsm_05", "swissimage_2", "swissalti3d_2", "buildings3d", "names", "copdem30", "osm", "gwr")
# shared files that change with the source and are fetched again after this many days
MAX_AGE_DAYS = {"osm": 14, "gwr": 7}
SHARED_EXT = {"osm": (".osm.pbf",), "gwr": (".zip",), "buildings3d": (".zip",)}


def _link(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def _wanted(sub, name):
    ext = SHARED_EXT.get(sub)
    return not name.endswith(".part") and (ext is None or name.endswith(ext))


def fresh(sub, path):
    days = MAX_AGE_DAYS.get(sub)
    return days is None or (time.time() - os.path.getmtime(path)) < days * 86400


def link_in(cache, data, log=print):
    """Cached files into a build's data folder (only those it does not have). Returns the number linked."""
    n = 0
    for sub in SHARED:
        src = os.path.join(cache, sub)
        if not os.path.isdir(src):
            continue
        for f in os.listdir(src):
            p = os.path.join(src, f)
            dst = os.path.join(data, sub, f)
            if os.path.isfile(p) and _wanted(sub, f) and fresh(sub, p) and not os.path.exists(dst):
                _link(p, dst)
                n += 1
    log(f"cache: {n} downloaded files reused from {cache}")
    return n


def harvest(cache, data, log=print):
    """A build's new shared downloads into the cache. Returns the number added."""
    n = 0
    for sub in SHARED:
        src = os.path.join(data, sub)
        if not os.path.isdir(src):
            continue
        for f in os.listdir(src):
            p = os.path.join(src, f)
            dst = os.path.join(cache, sub, f)
            if not os.path.isfile(p) or not _wanted(sub, f):
                continue
            if os.path.exists(dst):
                if fresh(sub, dst) or os.path.getmtime(dst) >= os.path.getmtime(p):
                    continue
                os.remove(dst)
            _link(p, dst)
            n += 1
    log(f"cache: {n} new downloads kept in {cache} for the next builds")
    return n


def size_gb(cache):
    t = 0
    for dp, _, fs in os.walk(cache):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return t / 2 ** 30
