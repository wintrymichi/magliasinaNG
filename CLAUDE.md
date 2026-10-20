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

- `gh release download` fails in the cloud (GraphQL blocked): download release assets through the REST API
  (`gh api .../releases/tags/<tag>`, then the asset URL with `Accept: application/octet-stream`).
- pip can hang with no output in the cloud: run it with `timeout` and `--progress-bar off`, kill and retry.
- `git commit` during an unfinished rebase folds the new commit into the one being picked: run
  `git rebase --continue` (check `git status`) before committing anything else.

## Testing in the game on the PC

- The monitor may be off (OLED, black window on top): run the game in a virtual KWin session, it renders on the RTX:
  `kwin_wayland --virtual --xwayland --width 2560 --height 1440 --socket wl-mng --exit-with-session <script>` with
  `SDL_VIDEODRIVER=x11` (the plain launch hung at startup with the screen off). Measure before/after in the same setup.
- An extension name `magliaso_v31` loads `lua/ge/extensions/magliaso/v31.lua` (the underscore is a folder).
- `gz()` (getSurfaceHeightBelow) hits roofs: give cameras near buildings absolute heights.
- The game's sites (`city.sites.json`, `facilities.sites.json`) need an `oldId` on every spot and zone, or the level
  stops loading with a Lua error.
- Restore the player's mod zip, temp cache and remove every test file from the user folder at the end.
- A game update can move the game's own files the level uses: 0.40 moved 73 of them from `/levels/italy/...` to
  `/assets/materials/...` and left `.link` redirects, which it follows, except for 3 (the stone wall, italy_plastic):
  missing textures everywhere (2026-10-20). Read the game log ("Failed to load", NO-MATERIAL) before guessing, then
  update `dati/game_paths_<version>.json` (finish step `game_paths`) against the installed game.
- After a version update BeamNG disables every mod in `mods/db.json`, and a relaunch from Steam drops the launch
  options (`-level`, `-gfx dx11`): the game opened West Coast USA. Check both before every test.
- Do not use the laptop DESKTOP-EKDTIGL (AMD iGPU, 512 MB video memory) for load tests on 0.40 (michi, 2026-10-20):
  the released v3.0 took 12-15 min to load and crashed twice "Out of VRAM" while the game converted the sign PNGs.
  0.40 clears `temp/levels/<level>` at every start, so a relaunch converts them again (no warm cache).
- A Remote Control session started from a thread reports only to that thread (@parent): forward its notes to the
  other threads yourself. `list_events`/`interrupt_session` do not reach it, and a message waits until its current
  long step ends.

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
- With `translucentZWrite` the overlay layers of one mesh must be drawn lowest first: a higher layer drawn first hides
  a lower one drawn after it (road wear, 2026-10-20). And a band laid over the road with only 3 rows across lets the
  road's crown and crests poke through it (holes in the wear): rows at most 2 m apart, lifted where the asphalt is
  too close (road_wear.clear_of).
- The game draws one side of a face, so any gap in a mesh is a hole you see through. The roadside walls
  (walls.build_roadside) were only a face and a 1.75 m cap: where a run ended one saw under the cap into the bank
  (issue #76, 2026-10-20). Close every solid: back and end faces (walls.roadside_shut).
- walls.wall_feet_step took "a vertex lower than another at the same x, y" for a foot: where two wall pieces of
  different heights meet, or the two faces of a thin wall touch, it pulled the lower TOP corners to the ground
  (5,831 notches in v3.0). Vertices of `*_top` triangles are never feet. A first fix (measure "wall on a bridge"
  from the highest terrain vertex) raised the notches to 7,986 before that exclusion: after moving vertices,
  check which triangles (top or side) they belong to.
- A road can stand metres over the terrain carved under it: wall feet measured only against the terrain hung over
  the asphalt (slots up to 60 cm). The road surface within 1 m is the ground too (wall_feet_step, FOOT_ROAD).
- Counting holes: an edge of only one triangle over the ground is a hole unless another face closes it. Weld all
  the wall shapes together and look across the edge in its triangle's plane, under a top's edge and behind a
  side's edge (check_level.wall_holes). A test only "15 cm under the edge" counted the edge's own quad as cover.
- A released zip can be checked in the cloud without a build: unzip the parts a finish step reads and run it on that
  folder (bng.LevelFiles takes a folder). pip install shapely pyproj rasterio opencv-python-headless playwright;
  render3d needs three.js from `npm pack three@0.170.0` (set render3d.THREE). Cameras placed by guess ended
  inside meshes: put them on a road vertex beside the target, at eye height, looking at it.

## Data from the cloud sessions

- swisstopo (data.geo.admin.ch, api3), Overpass and the BFS register (public.madd.bfs.admin.ch) are blocked from the
  cloud container (proxy 403). Compute anything that needs them in a small GitHub workflow that commits its result
  to the branch (strade_extra.yml, paesi_interi.yml), and test the code locally with stand-in inputs first.
- Growing the area (area.py) changes what the pinned extracts in beamng/dati must cover: re-pinning them pulls newer
  data for the whole map. Add only what is new (download_gwr.py --add) and check the OSM extract's bbox.

## Races (time trials, races.py)

- Mission files go in `gameplay/missions/<level>/timeTrial/<id>/` beside `levels/`, not inside the level folder:
  a zip made from the level folder alone loses them (package.py adds them).
- The game's mission format was guessed at first (no game files in the cloud, beamng.com blocked): copy the keys of
  a vanilla 0.40 mission instead (Italy `timeTrial/002-Asphalt`, loose files in `<install>/gameplay/missions/`).
- Start positions turn the vehicle's -Y onto the road, not +Y (the first guess faced the cars backwards).
- Plain shortest paths over the AI roads cut through village lanes: weight by drivability**4, and follow the
  measured cantonal road by name, including its split pieces `<name>_<n>` / `<name>_g<n>` (traffic thread).
- The cantonal AI road starts with a hook inside the Magliaso junction, and a start position on the start line
  spawns the car on it: trim turn-backs at the route ends and start the car 15 m before the line.

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

## Sounds

- Event names copied from an old forum list (BeamNG 0.2x: `Church_Bells_01`, `Jungle Rock>River Large 01`, Italy
  `Water QP04`...) do not exist in 0.40, and a whole feature (bells on the hour, birds/crickets by time of day with a
  mod Lua) was built on them and thrown away. Check the event list of the installed game (`dati/ambient_events.json`)
  before designing around a sound. 0.40 ambient events: `Ambient>Water>River/Waves/Waterfall`, `Roomtones>*`, `Wind>*`.
- Never rerun `ambient_sounds.py --scan` on 0.40: it finds no paths in the trie bank and would overwrite the
  hand-written `ambient_events.json` with an empty list.
- An FMOD event fixes its own range and looping (`isLooping`, `maxDistance` of the SFXEmitter do nothing with `track`);
  a 2D event (or a roomtone that may be one) placed as an emitter is heard everywhere at full volume. Turn such a
  sound on only after listening in the game (the "use" entry of `ambient_events.json`).
- The cloud container cannot reach documentation.beamng.com or the game files (proxy 403): get facts about the game
  from the PC (the integrator's RC session), not from guesses.

## Working with cat (the owner)

- Show the 3D renders and wait for cat's OK before running the GitHub Actions rebuild workflow. No PRs
  or merges without asking.
- Keep the README "Known limitations" up to date when one gets fixed.
- Reply in Italian, times in CEST, few subagents.
- v3.0.40 and later rounds: one thread integrates and builds; only it opens the release PR. Two other threads opened
  PRs (#80, #81) from branches that carried the whole integration branch to main and they had to be closed.
- Untested builds for michi go to the GitHub pre-release "nightly" (`nightly_build.yml`, started by changing
  `beamng/nightly/stamp.txt`), never the latest release; michi tests them on the main PC.
- Document every error and failed attempt in this file, under its topic (michi, 2026-10-20: "sempre").
