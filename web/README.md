# Website

The project website, at **https://wintrymichi.ch**, published on GitHub Pages by [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) on every push to `main` that touches `web/`. All its links are relative, so it works both at the root of the domain and at `wintrymichi.github.io/magliasinaNG/`.

| File | What it is |
|---|---|
| `index.html`, `style.css` | the page; no build step, no framework |
| `map.svg` | the map of the playable area, drawn by `tools/make_map.py` from `area.polygon()` and the OpenStreetMap extract in `beamng/dati/` |
| `img/` | in-game screenshots from `beamng/verifica/screenshots/`, resized by `tools/make_images.py` |
| `CNAME` | the domain, `wintrymichi.ch` |

## Domain

Set once in the repository, **Settings → Pages**: *Build and deployment → Source: GitHub Actions*; *Custom domain*: `wintrymichi.ch` (save, wait for the DNS check), then *Enforce HTTPS* once GitHub has issued the certificate. A site deployed by Actions takes its domain from this setting; the `CNAME` file is ignored by GitHub in that case and is copied only to record the domain.

DNS records at the registrar of `wintrymichi.ch` (GitHub Pages' addresses):

| Name | Type | Value |
|---|---|---|
| `wintrymichi.ch` (apex, `@`) | `A` | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| `wintrymichi.ch` (apex, `@`) | `AAAA` | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| `www` | `CNAME` | `wintrymichi.github.io` |

No other `A`, `AAAA` or `CNAME` record on the apex or on `www` (remove a registrar's parking records), and no wildcard (`*`) record. To protect the domain from being taken by another GitHub Pages site, verify it in the account settings of `wintrymichi`: **Settings → Pages → Add a domain**, which asks for a `TXT` record `_github-pages-challenge-wintrymichi.wintrymichi.ch`; leave that record in place. With the `www` record, `www.wintrymichi.ch` redirects to `wintrymichi.ch`.

To preview it locally: `python -m http.server -d web` and open http://localhost:8000.

After new screenshots or a new release, rerun the two scripts and update the version, the zip size and the numbers in `index.html`.
