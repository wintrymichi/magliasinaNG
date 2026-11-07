"""Builds without the web page (tests, scripts):

    python -m app.cli check  S,W,N,E
    python -m app.cli build  "Name" S,W,N,E [--data DIR] [--until STEP]
    python -m app.cli resume <build id>     [--data DIR] [--until STEP]

The same manager and steps as the app; the log goes to the console as well. --until stops after that step (a key as
the build lists them: stages, finish:tunnels, package, ...), so a long build can be split (GitHub's 6 h per job).
"""
import json
import os
import sys
import time

from . import jobs, system, zone as zonemod


def follow(m, b, until=None):
    p = os.path.join(b.folder, "build.log")
    off = 0
    while True:
        if os.path.exists(p):
            with open(p, "rb") as f:
                f.seek(off)
                chunk = f.read()
                off += len(chunk)
            if chunk:
                sys.stdout.write(chunk.decode("utf-8", "replace"))
                sys.stdout.flush()
        st = b.state
        if st["status"] in ("done", "failed", "stopped") and not m.current and b.id not in m.queue:
            print(f"\nbuild {b.id}: {st['status']} {st.get('error') or ''}", flush=True)
            return 0 if st["status"] in ("done", "stopped") and not st.get("error") else 1
        time.sleep(2)


def main(argv):
    if not argv or argv[0] not in ("check", "build", "resume"):
        print(__doc__)
        return 2
    data = None
    until = None
    if "--data" in argv:
        i = argv.index("--data")
        data = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if "--until" in argv:
        i = argv.index("--until")
        until = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if argv[0] == "check":
        print(json.dumps(zonemod.check([float(v) for v in argv[1].split(",")]), indent=1))
        return 0
    s = system.load_settings()
    if data:
        s["data_dir"] = os.path.abspath(data)
    s["auto_install"] = bool(s.get("beamng_user")) and os.environ.get("SWISSBUILDER_INSTALL", "1") == "1"
    os.makedirs(s["data_dir"], exist_ok=True)
    m = jobs.Manager(s)
    if argv[0] == "build":
        b = m.create(argv[1], [float(v) for v in argv[2].split(",")], start=False)
    else:
        b = m.builds[argv[1]]
    b.state["until"] = until
    b.save()
    m.start(b.id)
    print(f"build {b.id} in {b.folder}", flush=True)
    return follow(m, b, until)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
