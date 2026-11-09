"""What the PC has: memory, cores, free disk, the BeamNG user folder; and the settings of the app."""
import glob
import json
import os
import shutil
import sys

from . import BUILDER

RUNTIME = os.environ.get("SWISSBUILDER_RUNTIME") or os.path.join(BUILDER, ".runtime")
SETTINGS = os.path.join(RUNTIME, "settings.json")


def memory_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / 2 ** 30
    except Exception:
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
        except (ValueError, OSError, AttributeError):
            return 0.0


def free_gb(path):
    p = os.path.abspath(path)
    while not os.path.exists(p):
        q = os.path.dirname(p)
        if q == p:
            return 0.0
        p = q
    return shutil.disk_usage(p).free / 2 ** 30


def default_data_dir():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        # the drive with the most room (a build takes 15-50 GB); the home folder when it is that drive
        best, room = None, -1.0
        for d in "CDEFGHIJ":
            root = f"{d}:\\"
            if os.path.exists(root):
                try:
                    f = shutil.disk_usage(root).free
                except OSError:
                    continue
                if f > room:
                    best, room = root, f
        if best and not home.upper().startswith(best[:2].upper()):
            return os.path.join(best, "SwissBuilder")
    return os.path.join(home, "SwissBuilder")


def beamng_user_dirs():
    """Candidate BeamNG.drive user folders (the one holding 'mods'), newest layout first."""
    out = []
    if sys.platform == "win32":
        la = os.environ.get("LOCALAPPDATA", "")
        out += [os.path.join(la, "BeamNG", "BeamNG.drive", "current")]
        out += sorted(glob.glob(os.path.join(la, "BeamNG", "BeamNG.drive", "[0-9]*")), reverse=True)
        out += sorted(glob.glob(os.path.join(la, "BeamNG.drive", "[0-9]*")), reverse=True)
    else:
        home = os.path.expanduser("~")
        out += [os.path.join(home, ".local", "share", "BeamNG", "BeamNG.drive", "current")]
        out += sorted(glob.glob(os.path.join(home, ".local", "share", "BeamNG", "BeamNG.drive", "[0-9]*")), reverse=True)
        out += sorted(glob.glob(os.path.join(home, ".local", "share", "BeamNG.drive", "[0-9]*")), reverse=True)
        # Proton (Steam app 284160)
        for steam in (os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam")):
            pfx = os.path.join(steam, "steamapps", "compatdata", "284160", "pfx", "drive_c", "users", "steamuser",
                               "AppData", "Local")
            out += [os.path.join(pfx, "BeamNG", "BeamNG.drive", "current")]
            out += sorted(glob.glob(os.path.join(pfx, "BeamNG.drive", "[0-9]*")), reverse=True)
    return [p for p in out if os.path.isdir(p)]


def load_settings():
    s = {}
    try:
        s = json.load(open(SETTINGS, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not s.get("data_dir"):
        s["data_dir"] = default_data_dir()
    if not s.get("beamng_user"):
        found = beamng_user_dirs()
        s["beamng_user"] = found[0] if found else ""
    s.setdefault("auto_install", True)
    s.setdefault("workers", "auto")
    return s


def save_settings(s):
    os.makedirs(RUNTIME, exist_ok=True)
    tmp = SETTINGS + ".part"
    json.dump(s, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, SETTINGS)


def workers(setting="auto"):
    """Worker processes of the heavy steps by memory and cores (the 14 GB PC was OOM-killed with 14 optimize
    workers, CLAUDE.md 2026-10-17): PATCH_WORKERS (unpaved, paved_edges: each holds the level's faces), NET_WORKERS
    (the road tiles), OPT_WORKERS (optimize), TILE_WORKERS (steep_skin, skin_grass: forked tiles that share the step's
    arrays) and ZIP_WORKERS (threads that deflate the zip). switzerlandNG faster builds (2026-11-09): a 16 GB PC got
    the "low" set before (one PATCH worker), though the Axenstrasse's finishing steps used 2-5 GB."""
    ram = memory_gb()
    cpus = os.cpu_count() or 1
    if setting == "low" or ram < 12:
        w = {"PATCH_WORKERS": 1, "NET_WORKERS": 2, "OPT_WORKERS": 2, "TILE_WORKERS": 2, "ZIP_WORKERS": 2}
    elif ram < 20:
        w = {"PATCH_WORKERS": 2, "NET_WORKERS": 2, "OPT_WORKERS": 3, "TILE_WORKERS": 3, "ZIP_WORKERS": 4}
    elif setting == "high" and ram >= 48:
        w = {"PATCH_WORKERS": 3, "NET_WORKERS": 4, "OPT_WORKERS": 6, "TILE_WORKERS": 8, "ZIP_WORKERS": 8}
    else:
        w = {"PATCH_WORKERS": 2, "NET_WORKERS": 3, "OPT_WORKERS": 4, "TILE_WORKERS": 4, "ZIP_WORKERS": 4}
    # never more processes than cores (a 2-core PC with 32 GB ran 3 network workers on 2 cores)
    return {k: str(max(1, min(v, cpus))) for k, v in w.items()}


def info(settings):
    d = settings.get("data_dir")
    return {"ram_gb": round(memory_gb(), 1), "cpus": os.cpu_count(), "platform": sys.platform,
            "data_dir": d, "free_gb": round(free_gb(d), 1) if d else None,
            "beamng_user": settings.get("beamng_user"), "beamng_found": bool(settings.get("beamng_user")) and
            os.path.isdir(settings.get("beamng_user", "")), "beamng_candidates": beamng_user_dirs()}
