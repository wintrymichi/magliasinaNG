"""Ticino server: the whole map stays beside the game, the game gets only what lies around the car.

Without it, the 87 zone packs (51.6 GB, 596,000 files) sit in <user>/mods and the game mounts every one of them at
start: 75-81 s before the main menu on michi's PC (beamng.log 2026-10-29: "took ... to reorganise 596326 files" 75 s
after the last mountEntry), and the first time a shape is seen the game parses its Collada file and writes its own
.cdae cache (12 GB under temp/levels/ticino after four zones). With the server only the base mod (270 MB) is in
mods; the packs stay in the server's data folder, and the server puts the files of the tiles around the car into the
user folder as the game will load them:

    <user>/temp/ticino/srv/<path under levels/ticino/>     the files, shapes as .cdae (dae2cdae.py: no Collada parse
                                                           and no cache in the game); tile files point at them
    <user>/temp/ticino/helper/ready.json                   {"gen", "near": [tile keys], "far": [tile keys]}: what
                                                           the mod may load now (ticino/files.lua)
    <user>/temp/ticino/helper/alive.json                   as the helper's, plus "serve": true and "root"

A "near" tile (384 m) is its objects file, its trees file, its collision cells, its far tile and every level shape
its objects use; a "far" tile is the far ground shape alone. The server makes the tiles of the next minutes first
(the car's position and speed come from req.json, which the mod writes every 250 ms), keeps the cache under
--cache-gb by deleting the tiles farthest from the car, and also puts the terrain windows together (ticino_helper).
The mod without a running server, or with the packs in mods as before, works as before.

    python ticino_server.py [--user <BeamNG user folder>] [--data <folder with the ticino_<zone>_<n>.zip>]
    python ticino_server.py download [--tag ticino-v1]   the packs of a release: zones to --data, the base to mods
                                                         (resumes, checks size and sha256, skips what is there)
    python ticino_server.py adopt     move the zone packs from <user>/mods to --data (same disk: a rename)
    python ticino_server.py once <x> <y> [--radius 2]  make the tiles around a point and stop (tests, timings)

The base pack (ticino_base_*.zip) stays in <user>/mods: the level, its materials and textures must be there when
the game loads the level.

Settings: the command line, else ticino_server.json beside the server ({"user", "data", "cacheGB", "workers",
"dae", "tag"}), else the defaults.
"""
import argparse
import collections
import concurrent.futures
import glob
import hashlib
import json
import math
import os
import shutil
import signal
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "helper"))
sys.path.insert(0, os.path.join(HERE, ".."))
import ticino_helper as th  # noqa: E402

LEVEL = th.LEVEL
PREFIX = th.PREFIX                       # levels/ticino/
SRV_DIR = "temp/ticino/srv"
GAME_ROOT = "/" + SRV_DIR + "/"          # what the game calls it
GAME_LEVEL = "/" + PREFIX                # /levels/ticino/
VERSION = 1
READY_EVERY_S = 0.2
NEAR_EXTRA = 1                           # near tiles made this many rings beyond the largest object radius
FAR_EXTRA = 1
LOOKAHEAD_S = 12.0                       # the tiles round where the car will be in this many seconds count as near


def log(msg):
    th.log(msg)


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    th.write_atomic(path, data)


def default_data():
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ticino_data")


# ------------------------------------------------------------------ the packs
class Packs:
    """The zone packs: every file name under levels/ticino/ -> its pack, the zip files opened when needed."""

    OPEN_MAX = 16

    def __init__(self, dirs):
        self.paths = []
        self.index = {}
        t0 = time.time()
        for d in dirs:
            for p in sorted(glob.glob(os.path.join(d, "**", "ticino_*.zip"), recursive=True)):
                if os.path.basename(p).startswith("ticino_base"):
                    continue
                try:
                    zf = zipfile.ZipFile(p)
                except (OSError, zipfile.BadZipFile) as e:
                    log("not a zip, skipped: %s (%s)" % (p, e))
                    continue
                k = len(self.paths)
                self.paths.append(p)
                for name in zf.namelist():
                    if name.startswith(PREFIX) and not name.endswith("/"):
                        self.index[name[len(PREFIX):]] = k
                zf.close()
        self.open = collections.OrderedDict()
        log("%d zone packs, %d files indexed in %.1f s" % (len(self.paths), len(self.index), time.time() - t0))

    def _zip(self, k):
        zf = self.open.get(k)
        if zf is None:
            zf = zipfile.ZipFile(self.paths[k])
            self.open[k] = zf
            while len(self.open) > self.OPEN_MAX:
                self.open.popitem(last=False)[1].close()
        else:
            self.open.move_to_end(k)
        return zf

    def has(self, rel):
        return rel in self.index

    def read(self, rel):
        k = self.index.get(rel)
        if k is None:
            return None
        return self._zip(k).read(PREFIX + rel)


class Files(th.LevelFiles):
    """The helper's level files (stream.json, blocks) from the base pack in mods and from the server's packs."""

    def __init__(self, user, packs):
        super().__init__(user, extra_zips=packs.paths)


# ------------------------------------------------------------------ the conversion (worker processes)
def convert_job(src_bytes, out_path):
    """Collada bytes to a .cdae at out_path (written under a temporary name). Returns (out_path, bytes, ms)."""
    import dae2cdae
    t0 = time.perf_counter()
    data = dae2cdae.compile_bytes(src_bytes)       # raises dae2cdae.Unsupported for a shape it cannot write
    write_file(out_path, data)
    return out_path, len(data), (time.perf_counter() - t0) * 1000


# ------------------------------------------------------------------ the cache
class Unit:
    __slots__ = ("kind", "key", "files", "bytes", "pending", "ready", "t0")

    def __init__(self, kind, key):
        self.kind, self.key = kind, key
        self.files, self.bytes, self.pending, self.ready, self.t0 = [], 0, set(), False, time.time()


class Server:
    def __init__(self, user, packs, cfg, helper=None, cache_gb=8.0, workers=4, cdae=True):
        self.user, self.packs, self.cfg, self.helper = user, packs, cfg, helper
        self.root = os.path.join(user, *SRV_DIR.split("/"))
        self.hdir = os.path.join(user, *th.HELPER_DIR.split("/"))
        os.makedirs(self.root, exist_ok=True)
        os.makedirs(self.hdir, exist_ok=True)
        self.cap = int(cache_gb * 2 ** 30)
        self.cdae = cdae
        self.pool = concurrent.futures.ProcessPoolExecutor(max_workers=workers) if workers > 0 else None
        self.workers = workers
        self.futs = {}                       # future -> (unit, out path)
        self.units = {}                      # ("near" | "far", key) -> Unit
        self.refs = collections.Counter()    # file path -> units using it
        self.size = 0
        self.gen = 0
        self.ready_dirty = True
        self.last_ready = 0
        self.req = None
        self.req_mtime = None
        self.stats = collections.Counter()
        o = cfg["origin"]
        self.ox, self.oy = o[0], o[1]
        self.tile_m = cfg["cell"] * cfg["square"]
        self.col_m = cfg.get("colCell") or 64.0
        self.col_dir = cfg.get("colDir") or "col"
        self.maxR = int(cfg.get("maxRadius") or 6)
        self.farR = int(cfg.get("farRadius") or 16)
        self.has = cfg.get("tiles") or {}
        self.forest = cfg.get("forestTiles") or {}
        self.far = set(cfg.get("far") or [])
        self.base_keys = list(cfg.get("baseTextures") or [])
        self.sq = cfg["square"]
        per = int(round(self.tile_m / self.col_m))
        self.cols = collections.defaultdict(list)          # tile key -> its collision cells
        for k in cfg.get("colCells") or []:
            i, j = (int(v) for v in k.split("_"))
            self.cols["%d_%d" % (i // per, j // per)].append(k)
        self.clean_all()

    # ---- files
    def clean_all(self):
        shutil.rmtree(self.root, ignore_errors=True)
        os.makedirs(self.root, exist_ok=True)
        try:
            os.remove(os.path.join(self.hdir, "ready.json"))
        except OSError:
            pass

    def out_path(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def game_name(self, rel):
        """The file's name for the game: shapes become .cdae when the server converts them."""
        if self.cdae and rel.endswith(".dae"):
            return rel[:-4] + ".cdae"
        return rel

    def _add_file(self, u, rel, data):
        p = self.out_path(rel)
        if self.refs[p] == 0 and not os.path.exists(p):
            write_file(p, data)
            self.size += len(data)
            self.stats["files"] += 1
            self.stats["bytes"] += len(data)
        self.refs[p] += 1
        u.files.append(p)
        u.bytes += len(data)

    def _add_shape(self, u, rel):
        """A level shape of a tile: copied, or converted to .cdae in a worker (a ready .cdae in the pack is copied)."""
        name = self.game_name(rel)
        p = self.out_path(name)
        if self.refs[p] or os.path.exists(p):
            self.refs[p] += 1
            u.files.append(p)
            return
        if name != rel and self.packs.has(name):           # the pack carries the .cdae already
            self._add_file(u, name, self.packs.read(name))
            return
        data = self.packs.read(rel)
        if data is None:
            self.stats["missing"] += 1
            return
        if name == rel or self.pool is None:
            if name != rel:
                import dae2cdae
                try:
                    data = dae2cdae.compile_bytes(data)
                except Exception as e:             # noqa: BLE001 - a bad shape must not stop the server
                    self.stats["failed"] += 1
                    log("shape not converted: %s (%s)" % (p, e))
                    return
                self.stats["converted"] += 1
            self._add_file(u, name, data)
            return
        self.refs[p] += 1                                  # held from now on: a second tile waits for the same job
        u.files.append(p)
        f = self.pool.submit(convert_job, data, p)
        self.futs[f] = (u, p)
        u.pending.add(f)

    def _shape_rel(self, s):
        if isinstance(s, str) and s.lower().startswith(GAME_LEVEL):
            rel = s[len(GAME_LEVEL):]
            if self.packs.has(rel):
                return rel
        return None

    # ---- units
    def tile_of(self, x, y):
        return int(math.floor((x - self.ox) / self.tile_m)), int(math.floor((y - self.oy) / self.tile_m))

    def make_near(self, key):
        u = Unit("near", key)
        cx, cy = (int(v) for v in key.split("_"))
        if key in self.has:
            raw = self.packs.read("tiles/o_%d_%d.json" % (cx, cy))
            if raw is not None:
                ents = json.loads(raw.decode("utf-8"))
                for e in ents:
                    rel = self._shape_rel(e.get("shapeName"))
                    if rel:
                        self._add_shape(u, rel)
                        e["shapeName"] = GAME_ROOT + self.game_name(rel)
                self._add_file(u, "tiles/o_%d_%d.json" % (cx, cy), json.dumps(ents, separators=(",", ":")).encode())
        if key in self.forest:
            rel = "tiles/t_%d_%d.trees.json" % (cx, cy)
            data = self.packs.read(rel)
            if data is not None:
                self._add_file(u, rel, data)
        for k in self.cols.get(key, ()):
            rel = "%s/c_%s.bin" % (self.col_dir, k)
            data = self.packs.read(rel)
            if data is not None:
                self._add_file(u, rel, data)
        self._far_file(u, key)
        return u

    def _far_file(self, u, key):
        if key in self.far:
            rel = "far/f_%s.cdae" % key
            data = self.packs.read(rel)
            if data is not None:
                self._add_file(u, rel, data)

    def make_blk(self, key):
        """A terrain block's heights and base colour maps: the mod makes a window in Lua from them when the
        server's own window is late."""
        u = Unit("blk", key)
        for rel in ["blocks/terrain/t_%s.bin" % key] + ["blocks/base/%s_%s.rgb" % (b, key) for b in self.base_keys]:
            data = self.packs.read(rel)
            if data is not None:
                self._add_file(u, rel, data)
        return u

    def blocks_of(self, wx, wy):
        B, W = self.cfg["block"], self.cfg["window"]
        return ["%d_%d" % (bx, by) for by in range(wy // B, (wy + W - 1) // B + 1)
                for bx in range(wx // B, (wx + W - 1) // B + 1)]

    def make_far(self, key):
        u = Unit("far", key)
        self._far_file(u, key)
        return u

    def drop(self, u):
        for f in list(u.pending):
            f.cancel()
        for p in u.files:
            self.refs[p] -= 1
            if self.refs[p] <= 0:
                del self.refs[p]
                try:
                    n = os.path.getsize(p)
                    os.remove(p)
                    self.size -= n
                except OSError:
                    pass                   # open in the game (Windows): left, overwritten or removed later
        del self.units[(u.kind, u.key)]
        if u.ready:
            self.ready_dirty = True
        self.stats["dropped"] += 1

    # ---- what to make
    def read_req(self):
        p = os.path.join(self.hdir, "req.json")
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
            return
        self.req_mtime, self.req = m, r

    def wanted(self):
        """[(score, kind, key)] of the tiles to have, the most urgent first."""
        r = self.req
        if not r:
            return []
        cx, cy = self.tile_of(r["x"], r["y"])
        px, py = self.tile_of(r["x"] + r.get("vx", 0) * LOOKAHEAD_S, r["y"] + r.get("vy", 0) * LOOKAHEAD_S)
        out = []
        Rn, Rf = self.maxR + NEAR_EXTRA, self.farR + FAR_EXTRA
        R = max(Rn, Rf)
        for ty in range(min(cy, py) - R, max(cy, py) + R + 1):
            for tx in range(min(cx, px) - R, max(cx, px) + R + 1):
                d = max(abs(tx - cx), abs(ty - cy))
                dp = max(abs(tx - px), abs(ty - py))
                key = "%d_%d" % (tx, ty)
                dn = min(d, dp)
                if dn <= Rn and (key in self.has or key in self.forest or key in self.cols or key in self.far):
                    # rings 0-1 first, then the far ground of the window's edge, then the rest by distance
                    out.append((dn * 2 + (0 if d <= 1 else 1), "near", key))
                elif d <= Rf and key in self.far:
                    out.append((d + 4, "far", key))
        # the blocks of the car's window and of the windows the helper keeps ready
        wins = [(int(r["wx"]), int(r["wy"]))] if "wx" in r else []
        if self.helper:
            wins += self.helper.wanted()
        seen = set()
        for i, (wx, wy) in enumerate(wins):
            for key in self.blocks_of(wx, wy):
                if key not in seen:
                    seen.add(key)
                    out.append((3 if i == 0 else 7, "blk", key))
        out.sort()
        return out

    def keep_r(self, kind):
        if kind == "blk":
            return 2 * self.cfg["block"] * self.sq / self.tile_m + 6
        return (self.maxR + NEAR_EXTRA + 2) if kind == "near" else (self.farR + FAR_EXTRA + 2)

    def evict(self):
        if self.size <= self.cap or not self.req:
            return
        cx, cy = self.tile_of(self.req["x"], self.req["y"])
        far = []
        per_blk = self.cfg["block"] * self.sq / self.tile_m
        for (kind, key), u in self.units.items():
            tx, ty = (int(v) for v in key.split("_"))
            if kind == "blk":                           # a block's middle, in tiles
                tx, ty = int((tx + 0.5) * per_blk), int((ty + 0.5) * per_blk)
            d = max(abs(tx - cx), abs(ty - cy))
            if d > self.keep_r(kind):
                far.append((-d, u.t0, u))
        far.sort(key=lambda t: (t[0], t[1]))
        for _, _, u in far:
            if self.size <= self.cap * 0.9:
                break
            self.drop(u)

    # ---- the loop
    def collect(self):
        done = [f for f in self.futs if f.done()]
        for f in done:
            u, p = self.futs.pop(f)
            u.pending.discard(f)
            if f.cancelled():
                continue
            try:
                _, n, ms = f.result()
                self.size += n
                u.bytes += n
                self.stats["converted"] += 1
                self.stats["convert_ms"] += int(ms)
            except Exception as e:                       # noqa: BLE001 - a bad shape must not stop the server
                self.stats["failed"] += 1
                log("shape not converted: %s (%s)" % (p, e))
            self.finish(u)

    def finish(self, u):
        if not u.ready and not u.pending and (u.kind, u.key) in self.units:
            u.ready = True
            self.ready_dirty = True
            self.stats["ready_" + u.kind] += 1

    def write_ready(self, force=False):
        now = time.time()
        if not force and (not self.ready_dirty or now - self.last_ready < READY_EVERY_S):
            return
        self.gen += 1
        near = sorted(k for (kind, k), u in self.units.items() if kind == "near" and u.ready)
        far = sorted(k for (kind, k), u in self.units.items() if u.ready and kind != "blk")   # near: with its far tile
        write_file(os.path.join(self.hdir, "ready.json"),
                        json.dumps({"gen": self.gen, "root": GAME_ROOT, "near": near, "far": far},
                                   separators=(",", ":")).encode())
        self.ready_dirty, self.last_ready = False, now

    def step(self, budget_s=0.05):
        """Start or finish tiles for about budget_s; False when there was nothing to do."""
        t0 = time.time()
        self.collect()
        busy = len(self.futs)
        did = False
        for _, kind, key in self.wanted():
            if time.time() - t0 > budget_s or len(self.futs) >= self.workers * 6:
                break
            if (kind, key) in self.units or (kind == "far" and ("near", key) in self.units):
                continue
            ts = time.time()
            u = self.make_near(key) if kind == "near" else self.make_far(key) if kind == "far" else self.make_blk(key)
            self.units[(kind, key)] = u
            self.stats["read_ms"] += int((time.time() - ts) * 1000)
            self.finish(u)
            did = True
        if did or busy:
            self.evict()
        self.write_ready()
        return did or bool(self.futs)

    def alive_extra(self):
        return {"serve": True, "root": GAME_ROOT, "cacheMB": self.size // 2 ** 20, "units": len(self.units),
                "pending": len(self.futs), "converted": self.stats["converted"]}


class ServeHelper(th.Helper):
    """The helper's terrain windows and alive.json, with the server's state in alive.json."""

    def __init__(self, user, wins, server, ahead=8):
        self.server = server
        super().__init__(user, wins, ahead)

    def clean_all(self):
        super().clean_all()

    def alive(self, force=False):
        now = time.time()
        if force or now - self.last_alive >= th.ALIVE_EVERY_S:
            self.last_alive = now
            d = {"t": now, "version": th.VERSION, "pid": os.getpid(), "ready": len(self.ready), "built": self.built,
                 "taken": self.taken}
            if self.server:
                d.update(self.server.alive_extra())
            th.write_atomic(os.path.join(self.dir, "alive.json"), json.dumps(d).encode())

    def tick(self):
        """One round of the helper's own loop: True when it made a window."""
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
            self.build(todo[0])
            return True
        return False


def run(user, data, cache_gb, workers, cdae, ahead):
    packs = Packs([data])
    if not packs.paths:
        raise SystemExit("no ticino_<zone>_<n>.zip in %s (python ticino_server.py adopt moves them from mods)" % data)
    files = Files(user, packs)
    wins = th.Windows(files)
    srv = Server(user, packs, wins.cfg, cache_gb=cache_gb, workers=workers, cdae=cdae)
    h = ServeHelper(user, wins, srv, ahead)
    srv.helper = h

    def stop(*_):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    log("server ready: %s -> %s, cache %.1f GB, %d workers, shapes as %s" % (
        data, srv.root, cache_gb, workers, ".cdae" if cdae else ".dae"))
    last = 0
    try:
        h.alive(force=True)
        while True:
            srv.read_req()
            busy = h.tick()
            busy = srv.step() or busy
            if time.time() - last > 30:
                last = time.time()
                s = srv.stats
                log("cache %d MB, %d tiles ready, %d converting; %d shapes converted (%d failed), %d tiles dropped" % (
                    srv.size // 2 ** 20, s["ready_near"] + s["ready_far"], len(srv.futs), s["converted"],
                    s["failed"], s["dropped"]))
            if not busy:
                time.sleep(th.POLL_S)
    except KeyboardInterrupt:
        pass
    finally:
        if srv.pool:
            srv.pool.shutdown(cancel_futures=True)
        h.clean_all()
        srv.clean_all()
        log("stopped, files removed")


def once(user, data, x, y, radius, workers, cdae):
    """The near tiles within radius of (x, y), timed (tests)."""
    packs = Packs([data])
    files = Files(user, packs)
    raw = files.read("stream.json")
    if raw is None:
        raise SystemExit("stream.json not found (base pack in <user>/mods?)")
    cfg = json.loads(raw)
    srv = Server(user, packs, cfg, workers=workers, cdae=cdae)
    srv.req = {"x": x, "y": y, "vx": 0, "vy": 0}
    srv.maxR, srv.farR = radius - NEAR_EXTRA, -FAR_EXTRA - 1
    t0 = time.time()
    while True:
        srv.step(budget_s=0.2)
        if not srv.futs and all(u.ready for u in srv.units.values()) and \
                all((k, key) in srv.units for _, k, key in srv.wanted()):
            break
        time.sleep(0.01)
    dt = time.time() - t0
    s = srv.stats
    log("%d tiles in %.1f s: %d files, %.0f MB, %d shapes converted (%.0f ms of conversion, %d failed), "
        "%d missing" % (len(srv.units), dt, s["files"] + s["converted"], srv.size / 2 ** 20, s["converted"],
                        s["convert_ms"], s["failed"], s["missing"]))
    if srv.pool:
        srv.pool.shutdown()
    return srv


def adopt(user, data):
    """Move the zone packs out of <user>/mods into the data folder (a rename on the same disk, else a copy)."""
    os.makedirs(data, exist_ok=True)
    n = 0
    for p in sorted(glob.glob(os.path.join(user, "mods", "**", "ticino_*.zip"), recursive=True)):
        b = os.path.basename(p)
        if b.startswith("ticino_base"):
            continue
        dst = os.path.join(data, b)
        log("%s -> %s" % (p, dst))
        shutil.move(p, dst)
        n += 1
    log("%d packs moved; the base pack stays in mods" % n)


REPO = "wintrymichi/magliasinaNG"


def _get(url, headers=None):
    h = {"User-Agent": "ticino-server"}
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok and "api.github.com" in url:
        h["Authorization"] = "Bearer " + tok
    h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120)


def release(tag):
    try:
        return json.load(_get("https://api.github.com/repos/%s/releases/tags/%s" % (REPO, tag)))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    for page in range(1, 6):                     # a draft is found only in the list (with a token)
        for r in json.load(_get("https://api.github.com/repos/%s/releases?per_page=50&page=%d" % (REPO, page))):
            if r["tag_name"] == tag:
                assets, p = [], 1
                while True:
                    a = json.load(_get("%s?per_page=100&page=%d" % (r["assets_url"], p)))
                    if not a:
                        break
                    assets += a
                    p += 1
                r["assets"] = assets
                return r
    raise SystemExit("release %s not found" % tag)


def download(user, data, tag, zones=None):
    """The packs of release `tag`: zone packs into data, the base pack into <user>/mods (an older base removed).
    zones: only these zone names (and the base)."""
    rel = release(tag)
    assets = [a for a in rel.get("assets", []) if a["name"].startswith("ticino_") and a["name"].endswith(".zip")]
    if zones:
        assets = [a for a in assets if a["name"].startswith("ticino_base")
                  or any(a["name"].startswith("ticino_%s_" % z) and a["name"][len("ticino_%s_" % z):-4].isdigit()
                         for z in zones)]
    total = sum(a["size"] for a in assets)
    log("release %s: %d packs, %.1f GB" % (tag, len(assets), total / 1e9))
    os.makedirs(data, exist_ok=True)
    mods = os.path.join(user, "mods")
    done = 0
    for a in sorted(assets, key=lambda a: a["name"]):
        base = a["name"].startswith("ticino_base")
        dst = os.path.join(mods if base else data, a["name"])
        if os.path.exists(dst) and os.path.getsize(dst) == a["size"]:
            done += a["size"]
            continue
        part = dst + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        hdr = {"Accept": "application/octet-stream"}
        if have:
            hdr["Range"] = "bytes=%d-" % have
        url = a["url"] if os.environ.get("GH_TOKEN") else a["browser_download_url"]
        t0 = time.time()
        with _get(url, hdr) as r, open(part, "ab" if have and r.status == 206 else "wb") as f:
            if r.status != 206:
                have = 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        if os.path.getsize(part) != a["size"]:
            raise SystemExit("%s: %d of %d bytes, run download again" % (a["name"], os.path.getsize(part), a["size"]))
        dig = a.get("digest") or ""
        if dig.startswith("sha256:"):
            h = hashlib.sha256()
            with open(part, "rb") as f:
                for b in iter(lambda: f.read(1 << 24), b""):
                    h.update(b)
            if h.hexdigest() != dig[7:]:
                os.remove(part)
                raise SystemExit("%s: sha256 differs, removed; run download again" % a["name"])
        if base:
            for old in glob.glob(os.path.join(mods, "ticino_base_*.zip")):
                os.remove(old)
        os.replace(part, dst)
        done += a["size"]
        log("%s %.0f MB in %.0f s (%.1f of %.1f GB)" % (a["name"], a["size"] / 1e6, time.time() - t0, done / 1e9,
                                                       total / 1e9))
    log("all packs there")


def settings():
    p = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ticino_server.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    cfg = settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "adopt", "once", "download"])
    ap.add_argument("xy", nargs="*", type=float)
    ap.add_argument("--user", default=cfg.get("user") or th.default_user(), help="BeamNG user folder (with mods/)")
    ap.add_argument("--data", default=cfg.get("data"), help="folder with the zone packs (default: ticino_data beside "
                    "the server)")
    ap.add_argument("--cache-gb", type=float, default=float(cfg.get("cacheGB", 8.0)), help="files kept in the user folder")
    ap.add_argument("--workers", type=int, default=int(cfg.get("workers", max(1, min(6, (os.cpu_count() or 4) - 2)))),
                    help="processes converting shapes (0: none, in the main loop)")
    ap.add_argument("--dae", action="store_true", default=bool(cfg.get("dae", False)),
                    help="give the game the Collada files as they are (no .cdae)")
    ap.add_argument("--tag", default=cfg.get("tag", "ticino-all"), help="download: the release")
    ap.add_argument("--zones", nargs="*", default=cfg.get("zones"), help="download: only these zones (ti_0_0 ...)")
    ap.add_argument("--ahead", type=int, default=8, help="terrain windows of the next move kept ready (1-8)")
    ap.add_argument("--radius", type=int, default=2, help="once: rings of near tiles")
    a = ap.parse_args()
    data = a.data or default_data()
    if a.cmd == "adopt":
        adopt(a.user, data)
    elif a.cmd == "download":
        download(a.user, data, a.tag, a.zones)
    elif a.cmd == "once":
        once(a.user, data, a.xy[0], a.xy[1], a.radius, a.workers, not a.dae)
    else:
        run(a.user, data, a.cache_gb, a.workers, not a.dae, max(1, min(8, a.ahead)))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()          # the Windows .exe starts its conversion workers through main
    main()
