"""The app: a web page on http://127.0.0.1:<port> (this PC only) over the build manager.

    python -m app.server [--port 8765] [--no-browser]

The API answers only requests that carry the page's token (a header the page reads from its own HTML): another web
site open in the browser cannot start or delete builds through this server.
"""
import argparse
import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import BUILDER, HERE, VERSION
from . import jobs, system, zone as zonemod

WEB = os.path.join(BUILDER, "web")
OWN_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript", ".svg": "image/svg+xml",
             ".png": "image/png", ".json": "application/json"}
TOKEN = secrets.token_urlsafe(24)
SEARCH = "https://api3.geo.admin.ch/rest/services/api/SearchServer"

manager = None
settings = None


def regions_geojson():
    d = json.load(open(os.path.join(HERE, "data", "regions.json"), encoding="utf-8"))
    return {"type": "FeatureCollection", "features":
            [{"type": "Feature", "properties": {"code": c["code"], "name": c["name"]}, "geometry": c["geometry"]}
             for c in d["cantons"]]}


class Handler(BaseHTTPRequestHandler):
    server_version = "SwissBuilder/" + VERSION

    def log_message(self, fmt, *a):          # quiet console
        if os.environ.get("SWISSBUILDER_HTTP_LOG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % a))

    # ------------------------------------------------------------------ replies
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _authorised(self):
        return secrets.compare_digest(self.headers.get("X-Builder-Token", ""), TOKEN)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path
        if path in ("/", "/index.html"):
            html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read().replace("__TOKEN__", TOKEN) \
                .replace("__VERSION__", VERSION)
            return self._send(200, html, "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._static(path)
        if not self._authorised():
            return self._send(403, {"error": "no token"})
        try:
            if path == "/api/state":
                return self._send(200, self.state())
            if path == "/api/regions":
                return self._send(200, regions_geojson())
            if path == "/api/check":
                bbox = [float(v) for v in q["bbox"][0].split(",")]
                return self._send(200, zonemod.check(bbox))
            if path == "/api/search":
                return self._send(200, search(q.get("q", [""])[0]))
            if path.startswith("/api/builds/") and path.endswith("/log"):
                bid = path.split("/")[3]
                b = manager.builds[bid]
                off = int(q.get("offset", ["0"])[0])
                p = os.path.join(b.folder, "build.log")
                size = os.path.getsize(p) if os.path.exists(p) else 0
                if off < 0 or off > size:
                    off = max(0, size - 200000)
                with open(p, "rb") as f:
                    f.seek(off)
                    data = f.read(min(size - off, 400000))
                return self._send(200, {"offset": off + len(data), "size": size, "text": data.decode("utf-8", "replace")})
        except KeyError as e:
            return self._send(404, {"error": f"not found: {e}"})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "unknown"})

    def _static(self, path):
        rel = os.path.normpath(urllib.parse.unquote(path).lstrip("/"))
        full = os.path.join(WEB, rel)
        if rel.startswith("..") or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        # the Windows registry can map an extension to another type (or to none): the page's own files by name first
        ctype = OWN_TYPES.get(os.path.splitext(full)[1].lower()) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        return self._send(200, open(full, "rb").read(), ctype, {"Cache-Control": "max-age=60"})

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._authorised():
            return self._send(403, {"error": "no token"})
        path = urllib.parse.urlparse(self.path).path
        try:
            d = self._json()
            if path == "/api/builds":
                b = manager.create(d.get("name", ""), d["bbox"], start=d.get("start", True))
                return self._send(200, b.public())
            if path.startswith("/api/builds/"):
                bid, action = path.split("/")[3], path.split("/")[4]
                if action == "start":
                    manager.start(bid)
                elif action == "cancel":
                    manager.cancel(bid)
                elif action == "delete":
                    manager.delete(bid)
                elif action == "install":
                    return self._send(200, manager.install(bid))
                elif action == "open":
                    open_folder(manager.builds[bid].root if d.get("what") != "zip" else
                                os.path.dirname(manager.builds[bid].zip_path))
                else:
                    return self._send(404, {"error": "unknown action"})
                return self._send(200, {"ok": True})
            if path == "/api/settings":
                for k in ("data_dir", "beamng_user", "auto_install", "workers"):
                    if k in d:
                        settings[k] = d[k]
                if "data_dir" in d:
                    settings["data_dir"] = os.path.abspath(os.path.expanduser(d["data_dir"]))
                    os.makedirs(settings["data_dir"], exist_ok=True)
                    manager.reload()
                system.save_settings(settings)
                return self._send(200, self.state())
            if path == "/api/quit":
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                return self._send(200, {"ok": True})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except KeyError as e:
            return self._send(404, {"error": f"not found: {e}"})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        return self._send(404, {"error": "unknown"})

    def state(self):
        cur = manager.current[0].id if manager.current else None
        return {"version": VERSION, "settings": settings, "system": system.info(settings),
                "builds": sorted([b.public() for b in manager.builds.values()], key=lambda s: s["created"], reverse=True),
                "running": cur, "queue": list(manager.queue)}


def search(text):
    """Places by name (swisstopo's search service): [{label, lat, lon, bbox?}]."""
    if not text.strip():
        return []
    url = SEARCH + "?" + urllib.parse.urlencode({"searchText": text, "type": "locations", "sr": "4326", "limit": "12",
                                                 "lang": "en"})
    req = urllib.request.Request(url, headers={"User-Agent": "SwitzerlandBuilder/" + VERSION})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.load(r)
    out = []
    import re
    for f in d.get("results", []):
        a = f.get("attrs", {})
        out.append({"label": re.sub(r"<[^>]+>", "", a.get("label", "")), "lat": a.get("lat"), "lon": a.get("lon"),
                    "origin": a.get("origin")})
    return out


def open_folder(path):
    import subprocess
    if sys.platform == "win32":
        os.startfile(path)                          # noqa: the user's own folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def free_port(start):
    for p in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("no free port")


def main():
    global manager, settings
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("SWISSBUILDER_PORT", "8765")))
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    settings = system.load_settings()
    os.makedirs(settings["data_dir"], exist_ok=True)
    system.save_settings(settings)
    manager = jobs.Manager(settings)
    port = free_port(a.port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  switzerlandNG {VERSION} by wintrymichi is running at {url}\n  Data folder: {settings['data_dir']}\n"
          f"  Close this window (or press Ctrl+C) to stop it; a build that is running stops with it and resumes "
          f"from its last step when you start it again.\n", flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    jobs.stop_on_signals()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # the steps run in process groups of their own: stop them with the app (current[1] is a list while the
        # downloads run side by side: the old .pid here raised AttributeError and left them running)
        manager.shutdown()


if __name__ == "__main__":
    main()
