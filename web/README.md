# Website

The project website, published on GitHub Pages by [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) on every push to `main` that touches `web/`.

| File | What it is |
|---|---|
| `index.html`, `style.css` | the page; no build step, no framework |
| `map.svg` | the map of the playable area, drawn by `tools/make_map.py` from `area.polygon()` and the OpenStreetMap extract in `beamng/dati/` |
| `img/` | in-game screenshots from `beamng/verifica/screenshots/`, resized by `tools/make_images.py` |

To preview it locally: `python -m http.server -d web` and open http://localhost:8000.

After new screenshots or a new release, rerun the two scripts and update the version, the zip size and the numbers in `index.html`.
