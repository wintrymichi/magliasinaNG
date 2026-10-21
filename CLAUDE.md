# Notes for Claude sessions on MagliasinaNG

Mistakes made in earlier sessions and what to do instead. Add to this list when a new one costs time.

## Building the level locally

- Mirror `.github/workflows/v3_build_test.yml` with `MAGLIASO_ROOT` etc. exported. Without the env vars,
  `config.py` falls back to Windows paths (`BEAMNG_USER = C:\Users\...`) and scripts silently find nothing
  (a mesh search returned no items until the build env was sourced).
- A full build takes about 3.5 h; `build_level.py --finish <steps>` reruns single finish steps. After a
  container restart mid-build, resume from the failed step instead of starting over.
- Never run whole-terrain analysis (full 8192x8192 arrays, the 0.5 m DTM) while a build runs: it OOM-killed
  a pool worker and deadlocked the `optimize` step. Use small windows (memmap slices) during a build.
- `pkill -f build_level.py` also matches the shell running the pkill and kills it. Use `pkill -f "[b]uild_level.py"`.
- The build rewrites files in `beamng/dati` (e.g. `ponti.json`). Run `git checkout -- beamng/dati` before
  committing, or generated data ends up in the commit.
- The cloud container idles when no turn is active: keep a foreground wait loop while a build runs
  (`timeout 590 bash -c 'until grep -qE "BUILD DONE|Traceback" LOG; do sleep 20; done'`).
- `optimize_level` used os.cpu_count() - 2 processes (14) and the OOM killer took the build and the Claude session on
  the 14 GB PC (2026-10-17): now OPT_WORKERS (default 4). Keep PATCH_WORKERS=2 and nothing else heavy meanwhile.
- `pgrep -f`/`pkill -f` with a pattern in your own command line stops your own shell: use "[r]un_build" style patterns.
- Push work often. An earlier session lost the fuel stations module because it was never pushed.

## Testing in the game on the PC

- The monitor may be off (OLED, black window on top): run the game in a virtual KWin session, it renders on the RTX:
  `kwin_wayland --virtual --xwayland --width 2560 --height 1440 --socket wl-mng --exit-with-session <script>` with
  `SDL_VIDEODRIVER=x11` (the plain launch hung at startup with the screen off). Measure before/after in the same setup.
- An extension name `magliaso_v31` loads `lua/ge/extensions/magliaso/v31.lua` (the underscore is a folder).
- `gz()` (getSurfaceHeightBelow) hits roofs: give cameras near buildings absolute heights.
- The game's sites (`city.sites.json`, `facilities.sites.json`) need an `oldId` on every spot and zone, or the level
  stops loading with a Lua error.
- Restore the player's mod zip, temp cache and remove every test file from the user folder at the end.

## Terrain fixes

- Terrain heights are written in several places, in this order: the road carve override (`terrain_override`,
  applied as the height under and one terrain step around every paved mesh), the posts (walls.carve_terrain +
  adjust_terrain_roadside, water.lake_bed, rivers, railway.carve_terrain), then `min(H, override)`, then the
  finish steps `unpaved` and `paved_edges` (network_mesh.block raises ground up to EMB_MAX). Fixing one of
  them repeatedly let the same teeth come back from another.
- To find which step made a spike, compare in a small window: the final `.ter` (uint16 at offset 5,
  Z0/MAXH from the terrain json), `work/terrain_heights.npy` (stage terrain), the DTM, and the override
  stored in `work/roads_state.npz` (`ov_i`, `ov_v`). Only then change code.
- The override raises terrain, not only lowers it: a pavement on top of a retaining wall raised the vertices
  one ring beyond the wall carve to pavement height (single white teeth beside the railway under Magliaso,
  about 2500 over the map). walls.carve_terrain now lowers that ring on the low side of a wall.
- Do not tell the side of a wall from a vertex's own height: the DTM smears walls into slopes. Read the
  ground a few metres out on both sides (walls.wall_side), and read beyond any vertex that may itself be raised.
- Anything that raises ground near the railway must respect its bed (railway.bed_fn, network_mesh rail caps).

## Meshes

- Check winding/orientation when placing text or UVs along an outline: the fuel station fascia text was
  mirrored on outlines that ran the other way.

- Translucent overlay materials need `"translucentZWrite": true` (as Italy has them): without it the game draws
  them in a pass that takes no shadows, and they glow under cars and trees (road wear, 2026-10-18). DecalRoads
  draw on the road meshes only with `overObjects` set, and they do not fix that by themselves.

## Traffic and AI

- Started a full build on GitHub Actions for one thread while the other v3.0.40 threads were still working;
  michi stopped it. In a combined round, build only once, when every thread is ready (traffic_build.yml is manual).
- Merging the whole scalini branch into the traffic branch pulled 490 fix_review dumps (~850k lines). Base a
  thread branch on the integration branch and bring over only your own files.
- The cloud container cannot reach data.geo.admin.ch and the other data hosts: run analyses that need the
  downloads on GitHub Actions (traffic_probe.yml), not locally.
- BeamNG 0.40 vehicle/ai.lua ignores the "yield" signal action (only stop/briefStop/alert are handled). At a
  junction without a signal the AI yields when it turns or when its road has a lower drivability than another
  road there, so give way is a short lower-drivability piece (markings_rules.give_way_drivability).
- DecalRoad `speedLimit` is in m/s; without it the AI guesses the speed from the width (too fast on narrow
  roads). signals.json `sequences` is an object `{}` as in Italy, not a list.
- With autoLanes the game gives a road one lane until 5.4 m wide, so two-way cars meet in the middle: set
  autoLanes false and one lane each way from 4.5 m (ai_roads.lanes).
- info.json country: the game only knows usa/germany/italy/france/japan; anything else weighs no country.
- Welding road ends by snapping to the nearest node made V-shaped zigzags: snap an end only onto the other
  road's end, otherwise insert a node on it (ai_roads.weld, NODE_SNAP 0.5 m).
- Village speed zone from building counts: 60 buildings within 100 m left Magliaso's roundabouts at 80 km/h;
  25 within 150 m matches the signs.
- Roundabout give-way points found on the OSM ways landed on the ring: move them onto the entry road's
  incoming lane (snap_ring_signals), or the game binds them to the ring.
- The traffic test script said to install it flat as magliaso_traffic.lua; the game looks for
  magliaso/traffic.lua, so the first in-game run had no extension. be:getLastFrameDeltaTime does not exist in 0.40.1.
- Traffic test 2026-10-20 (0.40.1): all 12 traffic cars ended up stopped around the player's car, which stood in
  the lane of the cantonal road at the default spawn. The AI queues behind a standing car and the game respawns
  only far, unseen cars. Test traffic with the player driving or parked off the carriageway.
- A workflow edited by a script got a mis-indented step and failed at once on GitHub (no jobs): check every
  edited workflow with `python3 -c "import yaml; yaml.safe_load(open(f))"` before pushing.

## Working with cat (the owner)

- Show the 3D renders and wait for cat's OK before running the GitHub Actions rebuild workflow. No PRs
  or merges without asking.
- Keep the README "Known limitations" up to date when one gets fixed.
- Reply in Italian, times in CEST, few subagents.
