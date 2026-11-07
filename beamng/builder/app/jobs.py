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
import urllib.request

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
TAIL = [("recenter", "Move the level to its own origin", 3), ("package", "Pack the level as a mod (zip)", 8),
        ("install", "Put it in BeamNG's mods folder", 1)]
STEP_FORK_WIN = sys.platform == "win32"


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


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
                if p is not None:
                    kill_tree(p.pid)

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
            else:
                st["status"] = "failed"
                b.state["status"] = "failed"
                b.state["error"] = f"Step '{st['label']}' failed: see the log (the build can be resumed from this step)."
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
    def env(self, b):
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
            "PYTHONHASHSEED": "0",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        })
        e.update(system.workers(self.settings.get("workers", "auto")))
        return e

    def run_process(self, b, args, cwd, env=None):
        b.log(f"$ {' '.join(args)}")
        kw = {}
        if sys.platform == "win32":
            # its own process group (Ctrl+C reaches the app, which stops the step itself), but the app's console: when
            # that window is closed, Windows ends the step with it (with CREATE_NO_WINDOW it would run on alone)
            kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        with open(os.path.join(b.folder, "build.log"), "a", encoding="utf-8", errors="replace") as logf:
            p = subprocess.Popen(args, cwd=cwd, env=env or self.env(b), stdout=logf, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, **kw)
            with self.lock:
                self.current = (b, p)
            code = p.wait()
            with self.lock:
                self.current = (b, None)
        if code:
            b.log(f"[{now()}] exit code {code}")
        return code == 0

    def _step(self, b, st):
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
        b.log(f"downloading {REFERENCE_URL} ({REFERENCE_SIZE / 2 ** 20:.0f} MB)")
        for attempt in range(5):
            try:
                with urllib.request.urlopen(REFERENCE_URL, timeout=120) as r, open(dst + ".part", "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
                if os.path.getsize(dst + ".part") == REFERENCE_SIZE:
                    os.replace(dst + ".part", dst)
                    return
            except OSError as e:
                b.log(f"retry: {e}")
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("the reference level v1.1 could not be downloaded")

    def expand_finish(self, b, st):
        """The finishing steps of the pipeline (build_level.py --list) in place of the placeholder."""
        pipe = os.path.join(b.code, "pipeline")
        r = subprocess.run([sys.executable, "build_level.py", "--list"], cwd=pipe, env=self.env(b), capture_output=True,
                           text=True)
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


def kill_tree(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        for c in p.children(recursive=True):
            try:
                c.kill()
            except psutil.Error:
                pass
        p.kill()
    except Exception:
        try:
            os.kill(pid, 9)
        except OSError:
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
