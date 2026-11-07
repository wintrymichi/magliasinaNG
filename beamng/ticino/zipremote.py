"""Zips on a (draft) release read in parts with HTTP range requests: the scene files, materials and spot files of a
1-2 GB zone zip come down in seconds, without the whole download (CLAUDE.md, region_net, 2026-10-28).

    assets(tag) -> {name: asset id}
    open_zip(asset_id) -> zipfile.ZipFile
    extract(zf, names, dst)

The token comes from GH_TOKEN / GITHUB_TOKEN, or from `gh auth token`.
"""
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

REPO = os.environ.get("GH_REPO", "wintrymichi/magliasinaNG")


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not t:
        t = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    return t


def _get(url, headers=None, timeout=120):
    h = {"Authorization": "Bearer " + token(), "Accept": "application/vnd.github+json"}
    h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)


def assets(tag):
    """{asset name: id} of the release with this tag (drafts included: they are found only in the list)."""
    out = {}
    page = 1
    while True:
        rels = json.load(_get(f"https://api.github.com/repos/{REPO}/releases?per_page=50&page={page}"))
        if not rels:
            break
        for r in rels:
            if r["tag_name"] == tag:
                for p in range(1, 20):
                    a = json.load(_get(f"https://api.github.com/repos/{REPO}/releases/{r['id']}/assets?per_page=100&page={p}"))
                    if not a:
                        break
                    out.update({x["name"]: x["id"] for x in a})
                return out
        page += 1
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class RangeFile(io.RawIOBase):
    """A release asset read with HTTP range requests (seekable, for zipfile). The signed download URL the API
    redirects to expires after a few minutes: it is asked again when a request fails."""

    def __init__(self, asset_id):
        self.asset_id, self.pos, self.url = asset_id, 0, None
        self._resolve()

    def _resolve(self):
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/assets/{self.asset_id}",
                                     headers={"Authorization": "Bearer " + token(),
                                              "Accept": "application/octet-stream"})
        op = urllib.request.build_opener(_NoRedirect)
        try:
            op.open(req, timeout=60)
            raise RuntimeError("no redirect for asset %s" % self.asset_id)
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
            self.url = e.headers["Location"]
        r = urllib.request.urlopen(urllib.request.Request(self.url, headers={"Range": "bytes=0-0"}), timeout=60)
        self.size = int(r.headers["Content-Range"].split("/")[1])
        self.t_url = time.time()

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        err = None
        for attempt in range(8):
            try:
                if time.time() - self.t_url > 240:
                    self._resolve()
                r = urllib.request.urlopen(urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"}),
                                           timeout=180)
                data = r.read()
                break
            except Exception as e:          # expired URL (403), a cut connection: ask again
                err = e
                time.sleep(2 * (attempt + 1))
                try:
                    self._resolve()
                except Exception:
                    pass
        else:
            raise IOError("range read failed: %s" % err)
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def open_zip(asset_id):
    return zipfile.ZipFile(io.BufferedReader(RangeFile(asset_id), buffer_size=1 << 22))


def extract(zf, names, dst):
    """The members `names` of zf under dst (folders made); returns the paths written."""
    out = []
    for n in names:
        p = os.path.join(dst, *n.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with zf.open(n) as fi, open(p, "wb") as fo:
            while True:
                b = fi.read(1 << 22)
                if not b:
                    break
                fo.write(b)
        out.append(p)
    return out
