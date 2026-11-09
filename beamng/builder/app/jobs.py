"""The builds: one folder each under <data>/builds, its state in build.json, its log in build.log; one build runs at a
time, step by step, each step a process of its own (resumable from the step that failed or was stopped).

A build's steps are those of the pipeline's own GitHub build of a Ticino zone (ticino branch, zone_build.yml), in the
same order and with the same environment, plus the app's own: copy the pipeline into the build, move the finished
level to its own origin (recenter.py), pack it, put it in the game's mods folder.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback

from . import BEAMNG, BUILDER, VERSION
from . import cache, system, zone as zonemod

REFERENCE_URL = "https://github.com/wintrymichi/magliasinaNG/releases/download/v1.1/magliaso_pura_v1.1.zip"
REFERENCE_SIZE = 104178839

# (key, label, script, minutes for a dense 64 km2 zone on a 4-core GitHub runner, scales with the area)
PRE = [
    ("prepare_work", "Seed the work folder", "prepare_work.py", 0.2, False),
    ("swisstopo", "Download swisstopo: terrain, surface, buildings, orthophoto, names", "download_swisstopo.py", 25, True),
    ("worldcover", "Download ESA WorldCover land cover", "download_worldcover.py", 2, False),
    ("survey", "Download the cadastral survey (geodienste.ch)", "download_av.py", 10, True),
    ("tlm", "Download swissTLM3D roads, railways, rivers", "download_tlm.py", 6, False),
    ("gwr", "Download the Register of Buildings (BFS)", "download_gwr.py", 3, False),
    ("osm", "Download OpenStreetMap (Geofabrik extracts)", "download_osm.py", 8, False),
    ("rasters", "Rasters: terrain and surface grids", "build_rasters.py", 12, True),
    ("landcover", "Land cover from the survey", "landcover.py", 5, True),
    ("buildings", "Buildings from swissBUILDINGS3D", "extract_buildings.py", 6, True),
    ("missing_buildings", "Buildings the 3D model lacks (survey)", "missing_buildings.py", 3, True),
    ("trees", "Trees from the surface model", "trees.py", 10, True),
    ("network", "Road network (swissTLM3D + survey)", "network.py", 30, True),
    ("network_surface", "Road surfaces", "network_surface.py", 10, True),
]
STAGES_MIN = 106          # the stages of build_level.py, together (ti_1_0: 1 h 46 min)
FINISH_MIN = {"optimize": 10, "paved_edges": 32, "roof_posts": 24, "steep_skin": 19, "tunnels": 8, "unpaved": 8,
              "markings": 6, "road_wear": 5, "parking": 5, "signs": 5, "understory": 6, "forest_mosaic": 5, "grass": 3,
              "steep_yards": 3, "skin_grass": 3, "skin_blend": 6, "road_seams": 5, "sidewalks": 4, "wall_fill": 4}
FINISH_DEFAULT = 2
# switzerlandNG faster builds (2026-11-09): the downloads run beside each other, and the steps that need only
# swisstopo's files start as soon as those are there; everything after them waits for all of them. Value: the steps
# it waits for. The Axenstrasse spent 14.6 min in these one after the other, OpenStreetMap alone 9.1.
EARLY = {"swisstopo": (), "worldcover": (), "survey": (), "tlm": (), "gwr": (), "osm": (),
         "rasters": ("swisstopo",), "buildings": ("swisstopo",)}
# the finishing steps in one process (build_level.py --finish a b c ...: each step in a forked child of it, as
# before), its progress read from what it prints; not on Windows (no fork: there each step keeps its own process)
FINISH_CHAIN = hasattr(os, "fork")
TAIL = [("recenter", "Move the level to its own origin", 3), ("package", "Pack the level as a mod (zip)", 8),
        ("install", "Put it in BeamNG's mods folder", 1)]
STEP_FORK_WIN = sys.platform == "win32"
# A step HANGS (michi 2026-11-09: "la costruzione del livello non si deve bloccare in alcun modo") when for STALL_MIN
# minutes its log has not grown and its processes have used neither CPU nor the disk: then the stacks of its threads
# go to the log (SIGUSR1, config.py), it is stopped and run again (STEP_RETRIES times), else it fails with a message
# that says so. The downloads are run again after any failure as well (they keep what they have).
STALL_MIN = float(os.environ.get("SWISSBUILDER_STALL_MIN", "20"))
STEP_RETRIES = int(os.environ.get("SWISSBUILDER_STEP_RETRIES", "2"))
RETRY_WAIT = float(os.environ.get("SWISSBUILDER_RETRY_WAIT", "60"))
DOWNLOADS = {"swisstopo", "worldcover", "survey", "tlm", "gwr", "osm"}
# finishing steps that must never run twice on the same level (CLAUDE.md): a hang there is a failure, not a retry
NOT_REPEATABLE = {"skin_grass", "sidewalks", "road_seams", "road_sags", "steep_skin", "skin_blend"}
WORKER_VARS = ("PATCH_WORKERS", "NET_WORKERS", "OPT_WORKERS", "TILE_WORKERS", "ZIP_WORKERS")


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def popen(args, **kw):
    """A step's process: in a process group of its own (POSIX: a session; Windows: CREATE_NEW_PROCESS_GROUP), so that
    kill_tree reaches its forked workers too, also those a dead parent left behind (2026-11-09: build_level.py killed
    for memory left its pool workers running, holding their memory and the output pipe)."""
    if sys.platform == "win32":
        kw.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kw.setdefault("start_new_session", True)
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.Popen(args, **kw)


def _tree(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        return [p] + p.children(recursive=True)
    except Exception:
        return []


class Watch:
    """Is a step's process hung? Its log files' sizes, and the CPU time and disk bytes of its process tree, looked at
    every CHECK s: when none of them moved for STALL_MIN min it is hung (a download waits on the network with no CPU,
    but its progress lines grow the log every few seconds; a long computation uses CPU)."""
    CHECK = 30.0

    warned = False

    def __init__(self, p, paths):
        self.p, self.paths = p, [x for x in paths if x]
        self.t_moved = self.t_check = time.time()
        self.last = None
        try:
            import psutil  # noqa: F401
            self.on = True
        except ImportError:
            # without psutil the CPU and disk of the tree are unknown: a long silent computation would look hung
            self.on = False
            if not Watch.warned:
                Watch.warned = True
                print("watchdog off: psutil is not installed (a hung step is not stopped by itself)", flush=True)

    def _sample(self):
        sizes = []
        for x in self.paths:
            try:
                sizes.append(os.path.getsize(x))
            except OSError:
                sizes.append(-1)
        cpu, io = 0.0, 0
        for q in _tree(self.p.pid):
            try:
                c = q.cpu_times()
                cpu += c.user + c.system
                try:
                    i = q.io_counters()
                    io += i.read_bytes + i.write_bytes
                except (AttributeError, NotImplementedError, OSError):
                    pass
            except Exception:
                pass
        return sizes, cpu, io

    def hung(self):
        now_ = time.time()
        if not self.on or now_ - self.t_check < self.CHECK:
            return False
        self.t_check = now_
        sizes, cpu, io = self._sample()
        if self.last is not None:
            s0, c0, i0 = self.last
            if sizes != s0 or cpu - c0 > 0.5 or io - i0 > (1 << 20):
                self.t_moved = now_
        else:
            self.t_moved = now_
        self.last = (sizes, cpu, io)
        return now_ - self.t_moved > STALL_MIN * 60

    def idle_min(self):
        return (time.time() - self.t_moved) / 60


class Build:
    def __init__(self, folder):
        self.folder = folder
        self.path = os.path.join(folder, "build.json")
        self.state = json.load(open(self.path, encoding="utf-8"))
        self.lock = threading.Lock()

    @property
    def id(self):
        return self.state["id"]

    def save(self):
        with self.lock:
            tmp = self.path + ".part"
            json.dump(self.state, open(tmp, "w", encoding="utf-8"), indent=1)
            os.replace(tmp, self.path)

    def log(self, text):
        with open(os.path.join(self.folder, "build.log"), "a", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")

    # paths
    @property
    def code(self):
        return os.path.join(self.folder, "code", "beamng")

    @property
    def root(self):
        return os.path.join(self.folder, "root")

    @property
    def level_dir(self):
        return os.path.join(self.root, "beamng_user", "levels", self.state["level"])

    @property
    def zip_path(self):
        return os.path.join(self.root, "dist", self.state["level"] + ".zip")

    def public(self):
        s = dict(self.state)
        s["log_size"] = os.path.getsize(os.path.join(self.folder, "build.log")) if os.path.exists(
            os.path.join(self.folder, "build.log")) else 0
        s["zip_exists"] = os.path.exists(self.zip_path)
        s["zip_gb"] = round(os.path.getsize(self.zip_path) / 2 ** 30, 2) if s["zip_exists"] else None
        done = sum(st["weight"] for st in s["steps"] if st["status"] in ("done", "skipped"))
        total = sum(st["weight"] for st in s["steps"]) or 1
        s["progress"] = round(done / total, 4)
        el = sum(st.get("seconds", 0) for st in s["steps"] if st["status"] in ("done", "skipped"))
        if s.get("status") == "running":
            cur = [st for st in s["steps"] if st["status"] == "running"]
            if cur and cur[0].get("started_ts"):
                el += time.time() - cur[0]["started_ts"]
        # remaining time: the estimate, corrected by how fast this PC went through the steps done so far
        speed = (el / 60) / done if done > total * 0.03 else 1.0
        s["eta_minutes"] = round(max(0.0, (total - done) * min(max(speed, 0.25), 4.0)))
        return s


class Manager:
    def __init__(self, settings):
        self.settings = settings
        self.builds = {}
        self.queue = []
        self.current = None            # (build, Popen or None)
        self.cancel_flag = False
        self._step_now = None          # the step run_process runs (the watchdog marks it hung)
        self._chain_hung = False
        self._tracked = set()
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.reload()
        threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ folders
    @property
    def data_dir(self):
        return self.settings["data_dir"]

    @property
    def cache_dir(self):
        return os.path.join(self.data_dir, "cache")

    @property
    def builds_dir(self):
        return os.path.join(self.data_dir, "builds")

    def reload(self):
        self.builds = {}
        if not os.path.isdir(self.builds_dir):
            return
        for d in sorted(os.listdir(self.builds_dir)):
            p = os.path.join(self.builds_dir, d)
            if os.path.exists(os.path.join(p, "build.json")):
                try:
                    b = Build(p)
                except (OSError, ValueError):
                    continue
                if b.state.get("status") in ("running", "queued"):
                    # the app was closed while it ran (or killed): its step processes may still be running in
                    # their own group; stop them before the build can be resumed
                    for g in b.state.pop("pids", []) or []:
                        kill_stale(g)
                    b.state["status"] = "stopped"          # the app was closed while it ran: resumable
                    for st in b.state["steps"]:
                        if st["status"] == "running":
                            st["status"] = "pending"
                    b.save()
                self.builds[b.id] = b

    # ------------------------------------------------------------------ create
    def create(self, name, bbox, start=True):
        chk = zonemod.check(bbox)
        if not chk.get("ok"):
            raise ValueError(" ".join(chk["errors"]))
        title = (name or "").strip() or "Swiss area"
        base = zonemod.slug(title, 18)
        level = "ch_" + base
        bid, k = base, 1
        while os.path.exists(os.path.join(self.builds_dir, bid)) or any(
                b.state["level"] == level for b in self.builds.values()):
            k += 1
            bid, level = f"{base}_{k}", f"ch_{base}_{k}"
        folder = os.path.join(self.builds_dir, bid)
        os.makedirs(folder)
        z = zonemod.make_zone(level, title, bbox)
        km2 = chk["km2"]
        scale = max(km2 / 64.0, 0.15)
        steps = [{"key": "copy", "label": "Copy the pipeline into the build", "kind": "copy", "weight": 0.5}]
        steps += [{"key": k_, "label": lab, "kind": "script", "script": sc, "weight": round(m * (scale if sc_ else 1), 2)}
                  for k_, lab, sc, m, sc_ in PRE]
        steps += [{"key": "stages", "label": "Level: terrain, roads, walls, water, buildings, railway, vegetation, AI",
                   "kind": "stages", "weight": round(STAGES_MIN * scale, 1)}]
        # the finishing steps are listed by the pipeline itself once it is copied (copy step); a placeholder until then
        steps += [{"key": "finish", "label": "Finishing steps", "kind": "finish_placeholder", "weight": round(170 * scale, 1)}]
        steps += [{"key": k_, "label": lab, "kind": k_, "weight": m} for k_, lab, m in TAIL]
        for st in steps:
            st["status"] = "pending"
        state = {"id": bid, "title": title, "level": level, "bbox": [float(v) for v in bbox], "created": now(),
                 "status": "queued" if start else "new", "steps": steps, "check": chk, "zone": z,
                 "shift": list(zonemod.recenter_shift(z)), "app_version": VERSION, "error": None, "installed": None}
        json.dump(state, open(os.path.join(folder, "build.json"), "w", encoding="utf-8"), indent=1)
        json.dump(z, open(os.path.join(folder, "zone.json"), "w", encoding="utf-8"), indent=1)
        b = Build(folder)
        b.log(f"[{now()}] build '{title}' created: level {level}, box {bbox}, {km2} km2, cantons {chk['cantons']}")
        self.builds[bid] = b
        if start:
            self.start(bid)
        return b

    # ------------------------------------------------------------------ control
    def start(self, bid):
        b = self.builds[bid]
        if b.state["status"] == "running":
            return
        with self.lock:
            b.state["status"] = "queued"
            b.state["error"] = None
            for st in b.state["steps"]:
                if st["status"] in ("failed", "running", "cancelled"):
                    st["status"] = "pending"
            b.save()
            if bid not in self.queue:
                self.queue.append(bid)
        self.wake.set()

    def cancel(self, bid):
        with self.lock:
            if bid in self.queue:
                self.queue.remove(bid)
                b = self.builds[bid]
                b.state["status"] = "stopped"
                b.save()
            if self.current and self.current[0].id == bid:
                self.cancel_flag = True
                p = self.current[1]
                for q in (p if isinstance(p, list) else [p] if p is not None else []):
                    kill_tree(q.pid)

    def shutdown(self):
        """The app closes (Ctrl+C, the window, SIGTERM): stop the running step's processes with it (they run in
        groups of their own, which a Ctrl+C in the terminal no longer reaches)."""
        with self.lock:
            cur = self.current
            self.cancel_flag = True
        if cur:
            p = cur[1]
            for q in (p if isinstance(p, list) else [p] if p is not None else []):
                kill_tree(q.pid)

    def _track(self, b, procs):
        """The running processes into build.json (a later start of the app stops them if this one was killed)."""
        out = []
        for q in procs:
            try:
                import psutil
                out.append([q.pid, psutil.Process(q.pid).create_time()])
            except Exception:
                out.append([q.pid, None])
        b.state["pids"] = out
        b.save()

    def delete(self, bid):
        self.cancel(bid)
        for _ in range(50):
            if not (self.current and self.current[0].id == bid):
                break
            time.sleep(0.2)
        b = self.builds.pop(bid)
        shutil.rmtree(b.folder, ignore_errors=True)

    def install(self, bid):
        b = self.builds[bid]
        return install_zip(b, self.settings)

    # ------------------------------------------------------------------ the runner
    def _loop(self):
        while True:
            self.wake.wait(2.0)
            self.wake.clear()
            with self.lock:
                if self.current or not self.queue:
                    continue
                b = self.builds.get(self.queue.pop(0))
                if b is None:
                    continue
                self.current = (b, None)
                self.cancel_flag = False
            try:
                self._run(b)
            except Exception:
                b.state["status"] = "failed"
                b.state["error"] = traceback.format_exc()[-2000:]
                b.log(b.state["error"])
                b.save()
            finally:
                with self.lock:
                    self.current = None
                self.wake.set()

    def _run(self, b):
        b.state["status"] = "running"
        b.state["started"] = b.state.get("started") or now()
        b.save()
        free = system.free_gb(self.data_dir)
        need = b.state["check"]["estimate_disk_gb"] - self._used_gb(b)
        if free < need:
            b.log(f"[{now()}] WARNING: {free:.0f} GB free on the data disk, the build may need about {need:.0f} GB more")
        i = 0
        while i < len(b.state["steps"]):
            st = b.state["steps"][i]
            if st["status"] in ("done", "skipped"):
                i += 1
                continue
            if self.cancel_flag:
                break
            until = b.state.get("until")
            if st["kind"] == "script" and st["key"] in EARLY:
                group = [s_ for s_ in b.state["steps"] if s_["key"] in EARLY and s_["status"] not in ("done", "skipped")]
                if until not in {s_["key"] for s_ in group} and len(group) > 1:
                    if not self.run_early(b, group):
                        return
                    continue
            if st["kind"] == "finish" and FINISH_CHAIN:
                chain = []
                for s_ in b.state["steps"][i:]:
                    if s_["kind"] != "finish" or s_["status"] in ("done", "skipped"):
                        break
                    chain.append(s_)
                    if s_["key"] == until:
                        break
                if len(chain) > 1:
                    r = self.run_finish_chain(b, chain)
                    if r == "failed":
                        bad = next((s_ for s_ in chain if s_["status"] == "failed"), None)
                        if bad is not None and self._retry(b, bad):
                            b.state["status"], b.state["error"], b.state["failed_step"] = "running", None, None
                            b.save()
                            continue
                        if bad is not None:
                            self._fail(b, bad)
                        return
                    if r == "cancelled":
                        break
                    if until in {s_["key"] for s_ in chain}:
                        b.state["until"] = None
                        b.state["status"] = "stopped"
                        b.log(f"[{now()}] stopped after {until} (--until)")
                        b.save()
                        return
                    continue
            st["status"] = "running"
            st["started"] = now()
            st["started_ts"] = time.time()
            b.save()
            b.log(f"\n[{now()}] ===== {st['label']} ({st['key']})")
            t0 = time.time()
            try:
                ok = self._step(b, st)
            except Exception:
                b.log(traceback.format_exc())
                ok = False
            st["seconds"] = round(time.time() - t0)
            if ok == "expanded":                # the placeholder became the finishing steps, from index i on
                b.save()
                continue
            if self.cancel_flag:
                st["status"] = "pending"
                b.log(f"[{now()}] stopped by the user")
                break
            if ok == "skipped":
                st["status"] = "skipped"
            elif ok:
                st["status"] = "done"
            elif self._retry(b, st):
                continue
            else:
                st["status"] = "failed"
                b.state["status"] = "failed"
                b.state["error"] = self._error(st)
                b.state["failed_step"] = st["key"]
                b.save()
                return
            st["ended"] = now()
            b.save()
            i += 1
            if b.state.get("until") == st["key"]:        # cli --until: stop after this step, resumable
                b.state["until"] = None
                b.state["status"] = "stopped"
                b.log(f"[{now()}] stopped after {st['key']} (--until)")
                b.save()
                return
        if self.cancel_flag:
            b.state["status"] = "stopped"
        else:
            b.state["status"] = "done"
            b.state["finished"] = now()
            b.log(f"\n[{now()}] BUILD DONE: {b.zip_path}")
        b.save()

    def _retry(self, b, st):
        """After a failure: a download, or a step stopped as hung, runs again (STEP_RETRIES times, RETRY_WAIT s
        later). True when it is to run again (status pending)."""
        hung = st.pop("hung", False)
        if not (hung or st["key"] in DOWNLOADS):
            return False
        n = st.get("tries", 0)
        if n >= STEP_RETRIES:
            if hung:
                st["error_note"] = "hung"
            return False
        if st["key"] not in DOWNLOADS:
            why = self._unsafe_retry(b, st)
            if why:
                b.log(f"[{now()}] {st['label']} ({st['key']}) hung and cannot be run again by itself: {why}")
                st["error_note"] = "hung_written"
                st["written_note"] = why
                return False
            st["hangs"] = st.get("hangs", 0) + 1          # the retry gets half the workers (memory, swap)
        st["tries"] = n + 1
        st["status"] = "pending"
        b.save()
        b.log(f"[{now()}] {st['label']} ({st['key']}) {'hung' if hung else 'failed'}: run again in {RETRY_WAIT:.0f} s "
              f"(attempt {n + 2} of {STEP_RETRIES + 1}; what it finished is kept)")
        t = time.time()
        while time.time() - t < RETRY_WAIT and not self.cancel_flag:
            time.sleep(0.5)
        return not self.cancel_flag

    def _unsafe_retry(self, b, st):
        """Why a hung step may not simply run again, or None. A finishing step listed in NOT_REPEATABLE never; any
        other step only if it wrote no file into the level or the work folder (bng.LevelWriter writes its files at
        the end: a step stopped while computing has written none)."""
        if st.get("kind") == "finish" and st.get("step") in NOT_REPEATABLE:
            return (f"'{st['step']}' must not run twice on the same level; resume from an earlier step or build "
                    f"the area again")
        t0 = st.get("started_ts")
        if not t0 or st.get("kind") in ("script", "stages", "recenter"):
            # the rule: script steps (downloads, rasters, buildings...) rewrite their outputs from scratch and are
            # repeatable; stages resume from their checkpoint, recenter from its journal; only the finishing steps,
            # which change the level in place, need the test below
            return None
        n, first = 0, None
        for top in (b.level_dir, os.path.join(b.root, "work")):
            for dp, dns, fs in os.walk(top):
                dns[:] = [d for d in dns if d not in ("logs", "reports", "__pycache__")]
                for f in fs:
                    if f.endswith((".log", ".pkl")) or "report" in f:
                        continue
                    q = os.path.join(dp, f)
                    try:
                        if os.path.getmtime(q) >= t0 - 1:
                            n += 1
                            first = first or q
                    except OSError:
                        pass
        if n and st.get("chain_start"):
            return (f"it hung before it printed its first line, and the finishing steps of the same run before it "
                    f"wrote {n} files since then (e.g. {os.path.relpath(first, b.root)}): which of them are its own "
                    f"cannot be told, so it is not run again by itself; resume from this step")
        if n:
            return (f"it had already written {n} files (e.g. {os.path.relpath(first, b.root)}), so a second run "
                    f"could apply its changes twice; resume from an earlier step or build the area again")
        return None

    def _fail(self, b, st):
        st["status"] = "failed"
        b.state["status"] = "failed"
        b.state["error"] = self._error(st)
        b.state["failed_step"] = st["key"]
        b.save()

    def _error(self, st):
        note = st.pop("error_note", None)
        if note == "hung_written":
            return (f"Step '{st['label']}' stopped responding (no output, no CPU, no disk for {STALL_MIN:.0f} min) "
                    f"and {st.pop('written_note', '')}. See the log, which has the stacks of its threads.")
        if note == "hung":
            return (f"Step '{st['label']}' stopped responding (no output, no CPU, no disk for {STALL_MIN:.0f} min) "
                    f"{STEP_RETRIES + 1} times: see the log, which has the stacks of its threads (the build can be "
                    f"resumed from this step).")
        return f"Step '{st['label']}' failed: see the log (the build can be resumed from this step)."

    def _hang(self, b, procs, label, w):
        """A hung step: its threads' stacks into the log, then its processes stopped."""
        b.log(f"\n[{now()}] WATCHDOG: {label}: no output, no CPU and no disk for {w.idle_min():.0f} min: the step "
              f"hangs. The stacks of its threads follow, then it is stopped.")
        for q in procs:
            if sys.platform != "win32":
                import signal
                try:
                    os.killpg(q.pid, signal.SIGUSR1)
                except OSError:
                    pass
        time.sleep(5)
        for q in procs:
            kill_tree(q.pid)

    def run_early(self, b, group):
        """The EARLY steps of the group at once, each as soon as the steps it waits for are done; each writes its own
        log (logs/<key>.log), put into build.log when it ends. True when all are done; False on a failure or a stop
        (the others are let finish first: they are downloads, kept for the resume)."""
        pipe = os.path.join(b.code, "pipeline")
        logs = os.path.join(b.folder, "logs")
        os.makedirs(logs, exist_ok=True)
        keys = {st["key"] for st in group}
        todo, running, failed = list(group), {}, None
        b.log(f"\n[{now()}] ===== {len(group)} steps side by side: {', '.join(st['key'] for st in group)}")
        while todo or running:
            if not self.cancel_flag and failed is None:
                for st in list(todo):
                    if st.get("retry_at", 0) > time.time():
                        continue
                    wait = [k for k in EARLY[st["key"]] if k in keys and
                            next(s_ for s_ in group if s_["key"] == k)["status"] != "done"]
                    if wait:
                        continue
                    todo.remove(st)
                    st["status"], st["started"], st["started_ts"] = "running", now(), time.time()
                    lp = os.path.join(logs, st["key"] + ".log")
                    lf = open(lp, "w", encoding="utf-8", errors="replace")
                    lf.write(f"$ {sys.executable} {st['script']}\n")
                    lf.flush()
                    p = popen([sys.executable, st["script"]], cwd=pipe, env=self.env(b, st.get("hangs", 0)), stdout=lf,
                                         stderr=subprocess.STDOUT)
                    running[st["key"]] = (st, p, lf, lp, Watch(p, [lp]))
                    b.log(f"[{now()}] started: {st['label']} ({st['key']})")
                    b.save()
            elif todo:
                for st in todo:                       # stopped or failed: the rest stay for the resume
                    st["status"] = "pending"
                todo = []
            with self.lock:
                self.current = (b, [r[1] for r in running.values()])
            if running and set(running) != set(getattr(self, "_tracked", ())):
                self._tracked = set(running)
                self._track(b, [r[1] for r in running.values()])
            for k, (st, p, lf, lp, w) in list(running.items()):
                code = p.poll()
                if code is None:
                    if w.hung():
                        self._hang(b, [p], st["label"], w)
                        st["hung"] = True
                    continue
                lf.close()
                del running[k]
                sweep_group(p.pid)                    # what it left behind in its group
                st["seconds"] = round(time.time() - st["started_ts"])
                with open(lp, encoding="utf-8", errors="replace") as f:
                    out = f.read()
                b.log(f"\n[{now()}] ===== {st['label']} ({k}): {st['seconds']} s, side by side")
                b.log(out)
                if self.cancel_flag:
                    st["status"] = "pending"
                elif code:
                    b.log(f"[{now()}] exit code {code}")
                    hung = st.pop("hung", False)
                    n = st.get("tries", 0)
                    if (hung or k in DOWNLOADS) and n < STEP_RETRIES and failed is None:
                        st["tries"] = n + 1
                        st["status"] = "pending"
                        st["retry_at"] = time.time() + RETRY_WAIT
                        todo.append(st)
                        b.log(f"[{now()}] {st['label']} ({k}) {'hung' if hung else 'failed'}: run again in "
                              f"{RETRY_WAIT:.0f} s (attempt {n + 2} of {STEP_RETRIES + 1}; what it finished is kept)")
                    else:
                        if hung:
                            st["error_note"] = "hung"
                        st["status"] = "failed"
                        failed = failed or st
                else:
                    st["status"] = "done"
                    st["ended"] = now()
                b.save()
            if running or todo:
                time.sleep(0.5)
        self._tracked = set()
        b.state.pop("pids", None)
        with self.lock:
            self.current = (b, None)
        if all(st["status"] == "done" for st in group):
            # the new downloads into the cache (as after the osm step one by one)
            cache.harvest(self.cache_dir, os.path.join(b.root, "data"), b.log)
            return True
        if failed is not None:
            self._fail(b, failed)
        return False

    def run_finish_chain(self, b, chain):
        """The finishing steps of chain in one process (build_level.py --finish ...): their status from the lines it
        prints ("== finish: <name>", "[finish <name>: <s> s]", a step left out). "done", "failed" or "cancelled"."""
        import re
        pipe = os.path.join(b.code, "pipeline")
        self.step_reference(b)
        by = {st["step"]: st for st in chain}
        args = [sys.executable, "build_level.py", "--finish"] + [st["step"] for st in chain]
        b.log(f"\n[{now()}] ===== {len(chain)} finishing steps in one process")
        b.log(f"$ {' '.join(args)}")
        # its output goes to a file read here as it grows (2026-11-09: reading a pipe to its end waited for every forked
        # worker that held it, also after build_level.py itself had been killed)
        os.makedirs(os.path.join(b.folder, "logs"), exist_ok=True)
        lp = os.path.join(b.folder, "logs", "finish_chain.log")
        lf = open(lp, "wb")
        t_chain = time.time()
        p = popen(args, cwd=pipe, env=self.env(b, max(st.get("hangs", 0) for st in chain)), stdout=lf,
                  stderr=subprocess.STDOUT)
        lf.close()
        with self.lock:
            self.current = (b, p)
        self._track(b, [p])
        w = Watch(p, [lp])
        cur = None
        start = re.compile(r"^== finish: (\w+)")
        end = re.compile(r"^\[finish (\w+): (\d+) s\]")

        def close(st, status="done"):
            st["status"] = status
            st["seconds"] = round(time.time() - st["started_ts"])
            st["ended"] = now()

        def lines():
            """The lines the chain printed, as they come, until it ends (and whatever it printed last)."""
            off, rest, hung = 0, b"", False
            with open(lp, "rb") as f:
                while True:
                    code_ = p.poll()
                    f.seek(off)
                    data = f.read()
                    off += len(data)
                    rest += data
                    *full, rest = rest.split(b"\n")
                    for ln in full:
                        yield ln.decode("utf-8", "replace") + "\n"
                    if code_ is not None:
                        if rest:
                            yield rest.decode("utf-8", "replace") + "\n"
                        return
                    if not data:
                        if not hung and w.hung():
                            hung = True
                            self._hang(b, [p], "the finishing steps", w)
                            self._chain_hung = True
                        time.sleep(0.5)

        self._chain_hung = False
        with open(os.path.join(b.folder, "build.log"), "a", encoding="utf-8", errors="replace") as logf:
            for line in lines():
                m1, m2 = start.match(line), end.match(line)
                if m1 and m1.group(1) in by:
                    if cur is not None and cur["status"] == "running":
                        close(cur)                  # left out in this zone: no time line
                    cur = by[m1.group(1)]
                    logf.write(f"\n[{now()}] ===== {cur['label']} ({cur['key']})\n")
                    cur["status"], cur["started"], cur["started_ts"] = "running", now(), time.time()
                    cur.pop("chain_start", None)
                    b.save()
                logf.write(line)
                logf.flush()
                if m2 and m2.group(1) in by and by[m2.group(1)]["status"] == "running":
                    close(by[m2.group(1)])
                    b.save()
            code = p.wait()
        sweep_group(p.pid)                            # what it left behind in its group
        b.state.pop("pids", None)
        with self.lock:
            self.current = (b, None)
        if self.cancel_flag:
            for st in chain:
                if st["status"] == "running":
                    st["status"] = "pending"
            b.log(f"[{now()}] stopped by the user")
            b.save()
            return "cancelled"
        if code:
            b.log(f"[{now()}] exit code {code}")
            bad = cur if cur is not None and cur["status"] == "running" else next(
                (st for st in chain if st["status"] == "pending"), chain[0])
            if bad.get("started_ts"):
                bad["seconds"] = round(time.time() - bad["started_ts"])
            if self._chain_hung:
                bad["hung"] = True
            # failed here; _run decides whether it runs again (a hang) or the build stops (_fail)
            bad["status"] = "failed"
            if not bad.get("started_ts"):
                bad["started_ts"], bad["chain_start"] = t_chain, True
            b.save()
            return "failed"
        for st in chain:
            if st["status"] in ("running", "pending"):
                st["started_ts"] = st.get("started_ts") or time.time()
                close(st)
        b.save()
        return "done"

    def _used_gb(self, b):
        t = 0
        for dp, _, fs in os.walk(b.folder):
            for f in fs:
                try:
                    t += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        return t / 2 ** 30

    # ------------------------------------------------------------------ one step
    def env(self, b, hangs=None):
        """hangs: how often the step to run hung before (default: the step run_process runs); each hang halves the
        workers, so a step that hung thrashing the swap gets a chance on its retry."""
        if hangs is None:
            hangs = self._step_now.get("hangs", 0) if self._step_now else 0
        e = dict(os.environ)
        for k in ("PYTHONPATH", "PYTHONHOME", "MAGLIASO_ZONE", "MAGLIASO_LEVEL_DIR"):
            e.pop(k, None)
        chk = b.state["check"]
        e.update({
            "MAGLIASO_ROOT": b.root,
            "MAGLIASO_DATASET": os.path.join(b.folder, "code"),
            "MAGLIASO_BEAMNG_USER": os.path.join(b.root, "beamng_user"),
            "MAGLIASO_BEAMNG_GAME": os.path.join(b.folder, "no_game_install"),
            "MAGLIASO_NO_PHOTO_TEXTURES": "1",
            "MAGLIASO_REFERENCE_ZIP": os.path.join(self.cache_dir, "reference", "magliaso_pura_v1.1.zip"),
            "MAGLIASO_ZONE": os.path.join(b.folder, "zone.json"),
            "MAGLIASO_GWR_CANTONS": ",".join(chk["cantons"]) or "ti",
            "MAGLIASO_GWR_REUSE": "1",
            "MAGLIASO_OSM_PBFS": " ".join(chk["osm_extracts"]),
            "MAGLIASO_CHECKPOINT": "1",
            # procedural textures drawn the same in every build (buildings, the skin), kept here (texcache.py)
            "MAGLIASO_TEXTURE_CACHE": os.path.join(self.cache_dir, "textures"),
            "PYTHONHASHSEED": "0",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            # GDAL's /vsicurl/ waits for ever by default (download_worldcover, 2026-11-09)
            "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_CONNECTTIMEOUT": "30", "GDAL_HTTP_LOW_SPEED_TIME": "60",
            "GDAL_HTTP_LOW_SPEED_LIMIT": "1024", "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "5",
        })
        e.update(system.workers(self.settings.get("workers", "auto")))
        if hangs:
            for k in WORKER_VARS:
                if k in e:
                    e[k] = str(max(1, int(e[k]) >> hangs))
        return e

    def run_process(self, b, args, cwd, env=None):
        b.log(f"$ {' '.join(args)}")
        # popen: its own process group (Ctrl+C reaches the app, which stops the step itself); on Windows the app's
        # console still: when that window is closed, Windows ends the step with it (with CREATE_NO_WINDOW it would run on)
        lp = os.path.join(b.folder, "build.log")
        with open(lp, "a", encoding="utf-8", errors="replace") as logf:
            p = popen(args, cwd=cwd, env=env or self.env(b), stdout=logf, stderr=subprocess.STDOUT)
        with self.lock:
            self.current = (b, p)
        self._track(b, [p])
        w = Watch(p, [lp])
        while p.poll() is None:
            if w.hung():
                self._hang(b, [p], self._step_now["label"] if self._step_now else " ".join(args)[:120], w)
                if self._step_now is not None:
                    self._step_now["hung"] = True
                p.wait()
                break
            time.sleep(1.0)
        code = p.wait()
        sweep_group(p.pid)                            # what it left behind in its group
        b.state.pop("pids", None)
        with self.lock:
            self.current = (b, None)
        if code:
            b.log(f"[{now()}] exit code {code}")
        return code == 0

    def _step(self, b, st):
        self._step_now = st
        try:
            return self._step_kind(b, st)
        finally:
            self._step_now = None

    def _step_kind(self, b, st):
        k = st["kind"]
        pipe = os.path.join(b.code, "pipeline")
        if k in ("stages", "finish_placeholder", "finish", "package"):
            self.step_reference(b)               # a build moved to another PC or data folder: the cache may lack it
        if k == "copy":
            return self.step_copy(b)
        if k == "script":
            if st["key"] == "prepare_work":
                self.step_reference(b)
                os.makedirs(os.path.join(b.root, "data"), exist_ok=True)
                cache.link_in(self.cache_dir, os.path.join(b.root, "data"), b.log)
            ok = self.run_process(b, [sys.executable, st["script"]], pipe)
            if ok and st["key"] == "osm":
                cache.harvest(self.cache_dir, os.path.join(b.root, "data"), b.log)
            return ok
        if k == "stages":
            args = [sys.executable, "build_level.py", "--no-finish"]
            if os.path.exists(os.path.join(b.root, "work", "build_checkpoint.pkl")):
                args.append("--resume")
            return self.run_process(b, args, pipe)
        if k == "finish_placeholder":
            return self.expand_finish(b, st)
        if k == "finish":
            return self.run_process(b, [sys.executable, "build_level.py", "--finish", st["step"]], pipe)
        if k == "recenter":
            dx, dy = b.state["shift"]
            miss = os.path.join(b.root, "beamng_user", "gameplay", "missions", b.state["level"])
            if os.path.exists(os.path.join(b.level_dir, "recenter.json")):
                b.log("level moved already")
                return True
            env = dict(os.environ)
            env["PYTHONPATH"] = BUILDER
            return self.run_process(b, [sys.executable, "-m", "app.recenter", b.level_dir, str(dx), str(dy),
                                        "--missions", miss], BUILDER, env)
        if k == "package":
            return self.run_process(b, [sys.executable, "package.py", b.state["level"]], pipe)
        if k == "install":
            if not self.settings.get("auto_install", True):
                return "skipped"
            r = install_zip(b, self.settings)
            b.log(f"install: {r}")
            return True if r.get("ok") else "skipped"
        raise ValueError(k)

    def step_copy(self, b):
        """The pipeline as it is now into the build (the downloads write into dati: never into the app's own copy)."""
        dst = os.path.join(b.folder, "code", "beamng")
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        ign = shutil.ignore_patterns("__pycache__", "*.pyc", ".zones_root")
        shutil.copytree(os.path.join(BEAMNG, "pipeline"), os.path.join(dst, "pipeline"), ignore=ign)
        shutil.copytree(os.path.join(BEAMNG, "dati"), os.path.join(dst, "dati"), ignore=ign)
        shutil.copytree(os.path.join(BEAMNG, "ticino", "dati"), os.path.join(dst, "ticino", "dati"), ignore=ign)
        os.makedirs(os.path.join(b.root, "logs"), exist_ok=True)
        b.log(f"pipeline copied to {dst}")
        return True

    def update_code(self, b):
        """The app's pipeline code into a stopped build (after an update of the app): only beamng/pipeline; the data
        files (dati) stay as the build's downloads left them."""
        dst = os.path.join(b.code, "pipeline")
        if not os.path.isdir(dst):
            return False
        shutil.rmtree(dst)
        shutil.copytree(os.path.join(BEAMNG, "pipeline"), dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".zones_root"))
        b.log(f"[{now()}] pipeline code updated from {os.path.join(BEAMNG, 'pipeline')}")
        return True

    def step_reference(self, b):
        """The released v1.1 level: its copies of the game's own textures stand in for the game install (vanilla.py)."""
        dst = os.path.join(self.cache_dir, "reference", "magliaso_pura_v1.1.zip")
        if os.path.exists(dst) and os.path.getsize(dst) == REFERENCE_SIZE:
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)                    # a wrong size: again
        b.log(f"downloading {REFERENCE_URL} ({REFERENCE_SIZE / 2 ** 20:.0f} MB)")
        netio = pipeline_netio()
        netio.SAY = b.log                     # its progress lines into the build's log
        try:
            prog = netio.Progress("reference level v1.1", files=1)
            netio.fetch(REFERENCE_URL, dst, prog, expect_size=REFERENCE_SIZE)
            prog.done()
        except netio.DownloadError as e:
            raise RuntimeError(f"the reference level v1.1 could not be downloaded: {e}")
        finally:
            netio.SAY = None
        if os.path.getsize(dst) != REFERENCE_SIZE:
            os.remove(dst)
            raise RuntimeError("the reference level v1.1 came with a wrong size")

    def expand_finish(self, b, st):
        """The finishing steps of the pipeline (build_level.py --list) in place of the placeholder."""
        pipe = os.path.join(b.code, "pipeline")
        r = subprocess.run([sys.executable, "build_level.py", "--list"], cwd=pipe, env=self.env(b), capture_output=True,
                           text=True, timeout=900)
        if r.returncode:
            b.log(r.stdout + r.stderr)
            return False
        names = json.loads(r.stdout.strip().splitlines()[-1])["finish"]
        scale = st["weight"] / 170.0
        new = [{"key": "finish:" + n, "label": "Finish: " + n.replace("_", " "), "kind": "finish", "step": n,
                "weight": round(FINISH_MIN.get(n, FINISH_DEFAULT) * scale, 2), "status": "pending"} for n in names]
        i = b.state["steps"].index(st)
        b.state["steps"][i:i + 1] = new
        b.log(f"{len(names)} finishing steps: {', '.join(names)}")
        b.save()
        return "expanded"


def stop_on_signals():
    """SIGTERM and SIGHUP (the terminal closed) end the app as Ctrl+C does, so that it stops its steps (they run in
    groups of their own and do not get the terminal's signals)."""
    import signal

    def stop(sig, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), stop)
            except (ValueError, OSError):
                pass


def pipeline_netio():
    """The pipeline's download module (beamng/pipeline/netio.py, no other pipeline imports)."""
    import importlib.util
    if "sb_netio" in sys.modules:
        return sys.modules["sb_netio"]
    spec = importlib.util.spec_from_file_location("sb_netio", os.path.join(BEAMNG, "pipeline", "netio.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["sb_netio"] = m
    spec.loader.exec_module(m)
    return m


def kill_stale(entry):
    """A step process an earlier run of the app left (pid, create time): stopped with its group, if it is still that
    process."""
    pid, ct = (entry + [None])[:2] if isinstance(entry, list) else (entry, None)
    try:
        import psutil
        q = psutil.Process(pid)
        if ct is not None and abs(q.create_time() - ct) > 1:
            return                                   # the pid was taken by another process since
    except Exception:
        return
    kill_tree(pid)


def sweep_group(pid):
    """After a step ended: what it left in its process group (POSIX; forked workers of a parent that died). Nothing
    on Windows, where a pid of an ended process may already be another program's."""
    if sys.platform != "win32":
        import signal
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass


def kill_tree(pid):
    """A running step: its group (POSIX) and its process tree."""
    sweep_group(pid)                                 # the step's group (popen): its workers, also orphaned ones
    try:
        import psutil
    except ImportError:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        return
    try:
        p = psutil.Process(pid)
        for c in p.children(recursive=True):
            try:
                c.kill()
            except psutil.Error:
                pass
        p.kill()
    except psutil.Error:
        pass


def install_zip(b, settings):
    """The level's zip into <BeamNG user folder>/mods (the game enables a new mod by itself)."""
    user = settings.get("beamng_user") or ""
    if not os.path.isfile(b.zip_path):
        return {"ok": False, "reason": "the level is not packed yet"}
    if not user or not os.path.isdir(user):
        return {"ok": False, "reason": "BeamNG.drive's user folder was not found: set it in Settings, or copy the zip "
                                       "into its mods folder by hand", "zip": b.zip_path}
    mods = os.path.join(user, "mods")
    os.makedirs(mods, exist_ok=True)
    dst = os.path.join(mods, os.path.basename(b.zip_path))
    tmp = dst + ".part"
    shutil.copyfile(b.zip_path, tmp)
    os.replace(tmp, dst)
    b.state["installed"] = {"path": dst, "at": now()}
    b.save()
    return {"ok": True, "path": dst}
