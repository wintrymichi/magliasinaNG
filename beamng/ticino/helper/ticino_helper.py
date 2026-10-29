"""Ticino streaming helper: a process beside the game that puts the terrain window together on another core.

The streamer (mod/lua/ge/extensions/ticino/stream.lua) moves one 2048 x 2048 TerrainBlock with the car. Each move
needs the window's .ter (12 MB) and its combined base colour map, put together from the zone's blocks: in the game
that is Lua, a few ms a frame on the game thread (and all of it at once, paused, at a jump). This helper does the
same from the same blocks with numpy, before the game asks for it, and leaves ready files in the user folder:

    <user>/temp/ticino/helper/alive.json         {"t": unix time, ...} every second: the mod uses the helper only
                                                 while this is fresh (ticino/helper.lua)
    <user>/temp/ticino/helper/req.json           written by the mod every 250 ms: car position and speed, the
                                                 window it is in, the follow places, a jump window if any
    <user>/temp/ticino/helper/r_<wx>_<wy>.json   one per ready window: {"ter": ..., "base": ...} (game paths); the
                                                 mod deletes it when it takes the files, and later the files
    <user>/temp/ticino/helper/h<n>_<wx>_<wy>.ter / .png

The window files are byte for byte what terwin.terParts and stream.lua's combinedRows write (the PNG is the same
image, zlib-compressed instead of stored). Every file is written under a temporary name and renamed, so the game
never reads half a file. Only what the game would read: loose files in <user>/levels/ticino/ first, then the
ticino_*.zip in <user>/mods (any depth).

    python ticino_helper.py [--user "%LOCALAPPDATA%\\BeamNG\\BeamNG.drive\\current"] [--cache-mb 1500]
    python ticino_helper.py --once <wx> <wy> --out <dir>      one window to <dir> (tests, timings)

Needs Python 3.9+ and numpy. Stop it with Ctrl+C; it removes its files.
"""
import argparse
import collections
import glob
import json
import os
import signal
import struct
import time
import zipfile
import zlib

import numpy as np

LEVEL = "ticino"
PREFIX = "levels/%s/" % LEVEL
HELPER_DIR = "temp/ticino/helper"
GAME_DIR = "/" + HELPER_DIR + "/"          # the same folder as the game sees it
VERSION = 1
POLL_S = 0.03
ALIVE_EVERY_S = 1.0
PNG_LEVEL = 1                              # zlib level of the base map: 1 is fast and still 3-4x smaller than stored


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def default_user():
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return os.path.join(la, "BeamNG", "BeamNG.drive", "current")
    return os.path.expanduser("~/.local/share/BeamNG/BeamNG.drive/current")


# ------------------------------------------------------------------ the level's files, as the game finds them
class LevelFiles:
    """levels/ticino/<name>: the loose file of the user folder if there is one, else the entry of a ticino zip."""

    def __init__(self, user, extra_zips=()):
        self.loose = os.path.join(user, "levels", LEVEL)
        self.index = {}                          # name under levels/ticino/ -> (zip path, ZipInfo)
        self.zips = {}
        paths = sorted(glob.glob(os.path.join(user, "mods", "**", "ticino_*.zip"), recursive=True)) + list(extra_zips)
        for p in paths:
            try:
                zf = zipfile.ZipFile(p)
            except (OSError, zipfile.BadZipFile) as e:
                log("not a zip, skipped: %s (%s)" % (p, e))
                continue
            n = 0
            for zi in zf.infolist():
                if zi.filename.startswith(PREFIX) and (zi.filename.startswith(PREFIX + "blocks/")
                                                       or zi.filename == PREFIX + "stream.json"):
                    self.index[zi.filename[len(PREFIX):]] = (p, zi)
                    n += 1
            if n:
                zf.filelist, zf.NameToInfo = [], {}     # 88 zips of ~20,000 entries: keep only the indexed ones
                self.zips[p] = zf
            else:
                zf.close()
        log("%d zips with level files, %d block files indexed, loose folder %s" % (
            len(self.zips), len(self.index), "found" if os.path.isdir(self.loose) else "absent"))

    def read(self, name):
        p = os.path.join(self.loose, *name.split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as f:
                return f.read()
        hit = self.index.get(name)
        if not hit:
            return None
        return self.zips[hit[0]].read(hit[1])


class LRU:
    def __init__(self, max_bytes):
        self.max, self.size, self.d = max_bytes, 0, collections.OrderedDict()
        self.misses = 0

    def get(self, key, load):
        if key in self.d:
            self.d.move_to_end(key)
            return self.d[key]
        self.misses += 1
        v = load()
        n = sum(a.nbytes for a in v) if isinstance(v, tuple) else (v.nbytes if v is not None else 0)
        self.d[key] = v
        self.size += n
        while self.size > self.max and len(self.d) > 1:
            _, old = self.d.popitem(last=False)
            self.size -= sum(a.nbytes for a in old) if isinstance(old, tuple) else (old.nbytes if old is not None else 0)
        return v


# ------------------------------------------------------------------ the window
class Windows:
    def __init__(self, files, cache_mb=1500):
        self.files = files
        raw = files.read("stream.json")
        if raw is None:
            raise SystemExit("levels/ticino/stream.json not found (is the ticino base zip in mods?)")
        cfg = json.loads(raw)
        self.cfg = cfg
        self.B, self.W, self.P = cfg["block"], cfg["window"], cfg["basePx"]
        self.keys = list(cfg.get("baseTextures") or [])
        layer_key = {bm[1]: bm[2] for bm in cfg.get("baseMaterials") or []}
        # layer index of the .ter -> index of its base map in keys (stream.lua combinedRows: missing -> the first)
        self.lk = np.zeros(256, np.intp)
        for i, name in enumerate(cfg.get("materials") or []):
            k = layer_key.get(name)
            self.lk[i] = self.keys.index(k) if k in self.keys else 0
        tail = [struct.pack("<I", len(cfg["materials"]))]
        for m in cfg["materials"]:
            b = m.encode("latin-1")
            tail.append(bytes([len(b)]) + b)
        self.ter_tail = b"".join(tail)
        self.cache = LRU(cache_mb * 1024 * 1024)

    def _terrain(self, bx, by):
        def load():
            d = self.files.read("blocks/terrain/t_%d_%d.bin" % (bx, by))
            if d is None:
                return None
            B = self.B
            a = np.frombuffer(d, np.uint8)
            return (a[:2 * B * B].view("<u2").reshape(B, B), a[2 * B * B:3 * B * B].reshape(B, B))
        return self.cache.get(("t", bx, by), load)

    def _base(self, key, bx, by):
        def load():
            d = self.files.read("blocks/base/%s_%d_%d.rgb" % (key, bx, by))
            if d is None:
                return None
            Bp = self.B // self.P
            return np.frombuffer(d, np.uint8).reshape(Bp, Bp, 3)
        return self.cache.get(("b", key, bx, by), load)

    @staticmethod
    def _assemble(get, B, W, wx, wy, out):
        """Copy the blocks of B samples (get(bx, by) -> array or None) under the window into out (rows south)."""
        for by in range(wy // B, (wy + W - 1) // B + 1):
            y0, y1 = max(wy, by * B), min(wy + W, (by + 1) * B)
            for bx in range(wx // B, (wx + W - 1) // B + 1):
                x0, x1 = max(wx, bx * B), min(wx + W, (bx + 1) * B)
                a = get(bx, by)
                if a is not None:
                    out[y0 - wy:y1 - wy, x0 - wx:x1 - wx] = a[y0 - by * B:y1 - by * B, x0 - bx * B:x1 - bx * B]

    def ter(self, wx, wy):
        """The window's .ter (version 9) and its layer array (rows from the south)."""
        B, W = self.B, self.W
        H = np.zeros((W, W), "<u2")
        L = np.zeros((W, W), np.uint8)
        self._assemble(lambda bx, by: (self._terrain(bx, by) or (None, None))[0], B, W, wx, wy, H)
        self._assemble(lambda bx, by: (self._terrain(bx, by) or (None, None))[1], B, W, wx, wy, L)
        head = bytes([9]) + struct.pack("<I", W)
        return b"".join([head, H.tobytes(), L.tobytes(), self.ter_tail]), L

    def base_rgb(self, wx, wy, L):
        """The combined base colour map (rows from the north): each pixel from the map of the layer under the
        sample at its centre, as stream.lua combinedRows."""
        P, W = self.P, self.W
        Wp, Bp = W // P, self.B // P
        half = P // 2
        layers = L[half::P, half::P][:Wp, :Wp]             # rows south
        idx = self.lk[layers]
        out = np.empty((Wp, Wp, 3), np.uint8)
        for k, key in enumerate(self.keys):
            m = idx == k
            if not m.any():
                continue
            a = np.full((Wp, Wp, 3), 128, np.uint8)
            self._assemble(lambda bx, by: self._base(key, bx, by), Bp, Wp, wx // P, wy // P, a)
            out[m] = a[m]
        return out[::-1]

    def window(self, wx, wy):
        t0 = time.perf_counter()
        ter, L = self.ter(wx, wy)
        t1 = time.perf_counter()
        png = encode_png(self.base_rgb(wx, wy, L)) if self.keys else None
        t2 = time.perf_counter()
        return ter, png, (t1 - t0) * 1000, (t2 - t1) * 1000


def encode_png(rgb):
    h, w, _ = rgb.shape
    rows = np.zeros((h, w * 3 + 1), np.uint8)              # filter byte 0 on every row
    rows[:, 1:] = rgb.reshape(h, w * 3)
    data = zlib.compress(rows.tobytes(), PNG_LEVEL)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    for i in range(20):                    # Windows: the game may hold the old file open for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (i + 1))
    raise PermissionError(path)


# ------------------------------------------------------------------ the service
class Helper:
    def __init__(self, user, wins, ahead=8):
        self.dir = os.path.join(user, *HELPER_DIR.split("/"))
        os.makedirs(self.dir, exist_ok=True)
        self.clean_all()
        self.wins = wins
        self.ahead = ahead
        self.gen = 0
        self.ready = {}            # (wx, wy) -> (manifest path, [file paths])
        self.req_mtime = None
        self.req = None
        self.last_alive = 0
        self.built = self.taken = 0
        self.just_taken = set()    # taken since the last request: not made again before the mod says where it is

    def clean_all(self):
        for p in glob.glob(os.path.join(self.dir, "*")):
            try:
                os.remove(p)
            except OSError:
                pass

    def alive(self, force=False):
        now = time.time()
        if force or now - self.last_alive >= ALIVE_EVERY_S:
            self.last_alive = now
            write_atomic(os.path.join(self.dir, "alive.json"), json.dumps(
                {"t": now, "version": VERSION, "pid": os.getpid(), "ready": len(self.ready),
                 "built": self.built, "taken": self.taken}).encode())

    def read_req(self):
        p = os.path.join(self.dir, "req.json")
        try:
            m = os.stat(p).st_mtime_ns
        except OSError:
            return
        if m == self.req_mtime:
            return
        try:
            with open(p, "rb") as f:
                r = json.loads(f.read().decode())
        except (OSError, ValueError):
            return                 # being written: next poll
        self.req_mtime, self.req = m, r
        self.just_taken = set()

    def wanted(self):
        """The windows to have ready, most likely first: a jump's window, then the 8 the next move can go to
        (stream.lua follow: a tile out of places lo..hi moves the window by hi + 1 - lo tiles), ahead of the car."""
        r = self.req
        if not r:
            return []
        cell = int(r["cell"])
        out = []
        if r.get("jump"):
            out.append((int(r["jump"][0]), int(r["jump"][1])))
        wx, wy = int(r["wx"]), int(r["wy"])
        step = (int(r["hi"]) + 1 - int(r["lo"])) * cell
        vx, vy = float(r.get("vx", 0)), float(r.get("vy", 0))
        # the window's middle against the car: the side the car is nearer to comes first too
        n = int(r["n"])
        sq = float(r.get("square", 1.5))
        mx = (r["x"] - r["ox"]) / sq - (wx + n * cell / 2)
        my = (r["y"] - r["oy"]) / sq - (wy + n * cell / 2)
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    score = (dx * vx + dy * vy) * 30 + (dx * mx + dy * my) * sq * 0.02
                    cand.append((-score, (wx + dx * step, wy + dy * step)))
        cand.sort()
        out += [w for _, w in cand[:self.ahead]]
        seen, res = set(), []
        for w in out:
            if w not in seen:
                seen.add(w)
                res.append(w)
        return res

    def consumed(self):
        """Windows whose manifest the mod took (deleted): forget them (the mod deletes their files)."""
        for w, (mp, _) in list(self.ready.items()):
            if not os.path.exists(mp):
                del self.ready[w]
                self.just_taken.add(w)
                self.taken += 1
                log("window %d,%d taken by the game" % w)

    def drop(self, w):
        mp, fs = self.ready.pop(w)
        try:
            os.remove(mp)                      # the manifest first: the mod no longer finds the window
        except OSError:
            return                             # taken just now: the files are the game's
        for p in fs:
            try:
                os.remove(p)
            except OSError:
                pass

    def build(self, w):
        wx, wy = w
        ter, png, ms_ter, ms_png = self.wins.window(wx, wy)
        self.gen += 1
        stem = "h%d_%d_%d" % (self.gen, wx, wy)
        fs, man = [], {"wx": wx, "wy": wy}
        p = os.path.join(self.dir, stem + ".ter")
        write_atomic(p, ter)
        fs.append(p)
        man["ter"] = GAME_DIR + stem + ".ter"
        if png is not None:
            p = os.path.join(self.dir, stem + ".png")
            write_atomic(p, png)
            fs.append(p)
            man["base"] = GAME_DIR + stem + ".png"
        man["ms"] = round(ms_ter + ms_png, 1)
        mp = os.path.join(self.dir, "r_%d_%d.json" % (wx, wy))
        write_atomic(mp, json.dumps(man).encode())
        self.ready[w] = (mp, fs)
        self.built += 1
        log("window %d,%d ready: .ter %.0f ms, base map %.0f ms, block cache %d MB (%d reads)" % (
            wx, wy, ms_ter, ms_png, self.wins.cache.size // 2 ** 20, self.wins.cache.misses))

    def run(self):
        log("helper ready in %s" % self.dir)
        self.alive(force=True)
        while True:
            self.alive()
            self.read_req()
            self.consumed()
            want = self.wanted()
            keep = set(want)
            for w in list(self.ready):
                if w not in keep:
                    self.drop(w)
            todo = [w for w in want if w not in self.ready and w not in self.just_taken]
            if todo:
                self.build(todo[0])            # one at a time: a new request may change the order
                continue
            time.sleep(POLL_S)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=default_user(), help="BeamNG user folder (the one with mods/)")
    ap.add_argument("--zip", action="append", default=[], help="extra ticino zip to read (tests)")
    ap.add_argument("--cache-mb", type=int, default=1500, help="blocks kept in memory")
    ap.add_argument("--ahead", type=int, default=8, help="windows of the next move kept ready (1-8)")
    ap.add_argument("--once", nargs=2, type=int, metavar=("WX", "WY"), help="write one window and stop")
    ap.add_argument("--out", help="folder for --once")
    a = ap.parse_args()
    files = LevelFiles(a.user, a.zip)
    wins = Windows(files, a.cache_mb)
    if a.once:
        ter, png, mt, mp = wins.window(*a.once)
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "w.ter"), "wb").write(ter)
        if png:
            open(os.path.join(a.out, "base.png"), "wb").write(png)
        log("window %d,%d: .ter %.0f ms, base map %.0f ms" % (a.once[0], a.once[1], mt, mp))
        return
    h = Helper(a.user, wins, max(1, min(8, a.ahead)))

    def stop(*_):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK"):          # kill, and the console window closed on Windows
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    try:
        h.run()
    except KeyboardInterrupt:
        pass
    finally:
        h.clean_all()
        log("stopped, files removed")


if __name__ == "__main__":
    main()
