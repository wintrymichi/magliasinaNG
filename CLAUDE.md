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
- A screenshot on michi's PC while he uses it took his real desktop (browser, terminal) instead of the game, because
  Windows did not bring BeamNG to the front (2026-10-20; deleted at once). Capture only the game window or the virtual
  display, never the whole screen, and check the picture shows the game before keeping it.
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

## Checking a finish step in the cloud container

- Actions artifacts and run log zips are blocked by the proxy; `get_job_logs` with return_content works, and a
  long log is saved to a file to grep. The nightly also attaches its reports to the pre-release (nightly_reports.zip).
- The released zip downloads in seconds with curl from `github.com/.../releases/download/<tag>/<zip>`; extract it
  (5.5 GB) and run the step on the folder (`bng.LevelFiles`). jsdelivr is blocked: render3d's three.module.js comes
  from the npm tarball (`registry.npmjs.org/three/-/three-0.170.0.tgz`) into `WORK`.
- swissNAMES3D is not reachable, so `places.villages()` is empty: the spawn spheres of the released level
  (village names on their main road) stood in for testing direction_signs.
- OSM ways run where the level has no road (Italy, beyond the corridors): a prop placed along an OSM road must
  first check the carriageway mesh is there (87 of 295 junction poles were in fields).
- "Off the carriageway" is not free ground: yards and squares (`mp_hard_*`) are driven on too.
- Render cameras placed along an OSM line ended inside houses; put them over the carriageway mesh, at the
  height of the mesh, and aim at the object's real position, not the planned one (it moves when it is placed).

## Meshes

- Check winding/orientation when placing text or UVs along an outline: the fuel station fascia text was
  mirrored on outlines that ran the other way.

- BeamNG 0.40 draws a forest shape's imposters as opaque squares (white or dark grey, from one far tree in ten to the
  whole slope, for the rest of the session) when it bakes them itself during the session: shape newer than its cached
  imposter (every new build) or an empty cache. In v3.0 and the first nightlies (2026-10-20). The baked files are
  byte-identical to good ones: only the in-session bake and hot reload break. The game's own trees ship
  `<shape>.dae.imposter.dds`, `.imposter_normals.dds` and `.dae.asset.json` and are never baked; far_trees.prebaked
  does the same from dati/far_imposters (baked by the game, md5 of the DAE in baked.json): no bake, no squares.
  A test with a warm cache shows nothing wrong: delete `temp/levels/<level>/art/shapes/trees/far_*` first.
  The imposters fit only the DAE they were baked from: when a far model changes, far_trees prints "no imposter of ..."
  and check_level `far_models_without_imposters` goes over 0. Then bake them again in the game (empty cache, load,
  copy the two DDS of each model from temp) into dati/far_imposters and update the md5 in baked.json.
  Nightly #2 was patched in place (nightly_patch.yml), not built with them: the nightlies from #3 carry them from the build.
  dati/far_imposters is the first folder in dati: prepare_work.py shutil.copy'd every entry of dati and a fresh build
  failed at its first step (IsADirectoryError, found by "Tetti fluttuanti"). It now skips folders; far_trees reads
  them from dati itself. A new folder in dati needs the same: check that prepare_work and package skip or read it.
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
  Weld by distance (cKDTree pairs), not by rounding to a 5 mm grid: rounding split corners 1 mm apart across a grid
  line. The edge's own triangle is the one with all three of its corners: skipping every triangle that touched one
  end skipped a face doubled along another's side (10 m counted). Not holes, nothing to see: triangles of no width
  (slivers left by the `difference` cuts of wall_footprints), faces back to back, edges lying in other faces (T
  joints). With these the 56 m of the first v3.0.40 nightly were 8.5 m of cm cracks.
- Two walls side by side a few cm apart (the two lines the survey draws for one wall, left unjoined by
  walls.paired_lines; pillar notches) show a dark groove from above that the hole check cannot see (no open edge):
  1,100 gaps, 8.6 km in v3.0 and the first v3.0.40 nightly. walls.wall_gaps_step lays a lid on every gap narrower
  than 25 cm between the tops. Measure the rise across the gap per lid triangle: over the whole gap it skipped the
  walls climbing with the road (4.8 km left). A CDT of the outline joins three corners in a line into a mm-thin
  triangle that stands up as a fin (open edges): flip it with its neighbour (walls._no_slivers). Why paired_lines
  leaves these pairs is not known; one suspect is `ga.intersects(gb)` (lines that touch are never paired). Not
  changed: the AV survey is blocked in the cloud, so it could not be tested.
- A released zip can be checked in the cloud without a build: unzip the parts a finish step reads and run it on that
  folder (bng.LevelFiles takes a folder). pip install shapely pyproj rasterio opencv-python-headless playwright;
  render3d needs three.js from `npm pack three@0.170.0` (set render3d.THREE). Cameras placed by guess ended
  inside meshes: put them on a road vertex beside the target, at eye height, looking at it. The merged shapes
  (walls_m3_*) have their position at a corner of a 384 m chunk: a scratch script that read the shapes within
  200 m of a point missed the walls there.

## Data from the cloud sessions

- swisstopo (data.geo.admin.ch, api3), Overpass and the BFS register (public.madd.bfs.admin.ch) are blocked from the
  cloud container (proxy 403). Compute anything that needs them in a small GitHub workflow that commits its result
  to the branch (strade_extra.yml, paesi_interi.yml), and test the code locally with stand-in inputs first.
- Growing the area (area.py) changes what the pinned extracts in beamng/dati must cover: re-pinning them pulls newer
  data for the whole map. Add only what is new (download_gwr.py --add) and check the OSM extract's bbox.
- `osm_area.json.gz` is Overpass `out geom`: a way's points are in its own `geometry`, the `node` elements are only
  tagged nodes, and the `bbox` is the nodes' bbox. Looking ways up through node elements found none near a Caslano
  slipway and the integrator wrongly reported Caslano missing from the extract (2026-10-20).
- Overpass answered 502/504 from GitHub runners to every query on 2026-10-20, even 1 km boxes, for hours: read OSM
  from the Geofabrik extract with osmium instead (download_osm.py --add).

## Street photo reference (street_*.py)

- Google Street View terms forbid bulk download and derived data: michi asked twice, it was declined. Use Mapillary,
  Panoramax and KartaView (open licences) plus swisstopo; the step reads extra panoramas only from WORK/sv/pano.
- Mapillary, swisstopo and Hugging Face are blocked from the cloud container: run the network steps in
  street_reference.yml (token from the MAPILLARY_TOKEN secret) and commit only small results. Its devpack job
  commits photos (74 MB): purge them from a branch before it is merged (rebuild the branch without them).
- Pose fits: a fit with a big heading turn and a mediocre building overlap was a false match (a dashcam turned 31 deg).
  Gate on IoU >= 0.45 and >= 0.6 when the heading moved more than 12 deg (street_zone.accept).
- The scene render must open the alleys (street_scene.open_alleys): the 0.5 m DSM closes narrow alleys and
  every photo there failed to fit.
- Hedge votes landed on facades behind the strip when voted at the 3x3 max height: vote just under the cell's own
  top (street_hedges.VOTE_DOWN).
- Facade openings from Grounding DINO: about half the windows missed, eaves bands taken as balconies, a stone arcade
  as a garage. A facade with no detections must never blank a seen wall (facades.Measured.evidence); measured
  facades are off unless MAGLIASO_STREET_FACADES=1 (michi 2026-10-20).
- Roofs: the game's roofs agree with the photos within ~0.5 m (median bias +0.15 m); a one-photo difference is
  noise. Apply only with 2+ photos agreeing (street_collect ROOF_*).
- props_osm: a local helper named like the module-level box() shadowed it and would have crashed the build:
  grep for an existing name before adding a helper.
- Torch with default threads in parallel zone runs oversubscribed the CPU (hours): STREET_THREADS=1 per process.
- pkill with a pattern that is also in your own command line kills your shell (exit 144): kill by PID.
- The photo hedges were applied in understory.main(), which the build never runs: it copies dati/understory.npz
  as it is (prepare_work.py), so nightly #1 had none of them (2026-10-20). Hook new data where the build reads it
  (vegetation.py now applies understory.photo_hedges), and check the build log prints the hook's counts.
- A workflow's commit step pushed nothing: `git pull --rebase` refused because street_collect also rewrote a file
  that was not committed (street_facades.json). Restore the rest (`git checkout -- beamng/dati`) before pulling.
  Tile results stay in the run's artifacts: rerun only the collect with mode=area from_run=<run id>.
- The whole-area run measured 31 roofs off by 0.5-2.9 m, 28 of them too LOW in the game, while the three test zones
  had a +0.15 m bias and nothing to move: a one-sided shift smells of a measurement bias, so they are kept in
  verifica/street/roofs_measured.json and not applied (dati/street_roofs.json empty) until sheets of them are checked.

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
- A workflow edited by a script got a mis-indented step and failed at once on GitHub (no jobs): check every
  edited workflow with `python3 -c "import yaml; yaml.safe_load(open(f))"` before pushing.

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

## Landmarks (churches, bell towers, cable car)

- The cloud container cannot reach swisstopo, Commons or Mapillary, and Actions artifacts and logs are blocked by
  the proxy: `.github/workflows/landmarks.yml` (bump its `# stamp:` line to rerun) commits a small dev pack to
  `beamng/verifica/monumenti/pack` and `landmarks_preview.py` renders before/after from it in about 4 min a site.
- Actions caches are per branch: the first run of a new branch downloads everything again (about 13 min).
- Contact sheets made of CC BY-SA photos must not go into git (they are derivatives, the repo is CC BY-NC):
  they are in .gitignore, only `sheets/credits.json` is kept.
- The survey often keeps a church's roof as a separate object without walls: query buildings by their boxes,
  and take the roofs over a footprint from those objects (`landmarks.roofs_of`), or towers come out roofless.
- Round towers are many narrow facets (none wide enough for a module): use `landmarks.round_faces`. A tower with a
  lantern on top: take the eaves of its widest faces, not the median of all.
- A facade polygon can be split by a slot of a few cm (a downpipe in the survey): close it before `fits`, or one
  side of a tower got no bell chamber.
- A sacred block of the survey can hold a whole village core (Bedigliora) and the register gives it to a house:
  `landmarks.split_tower` draws its tower anyway.
- Heights stored as uint16 cm wrap after 655 m: the cable car climbs 900 m (decimetres there, `dtm_unit`).
- `bng.write_dae` subtracts the origin itself; do not subtract it again in the geometry.
- `landmarks_preview.py --before` must also switch off `landmarks.USES`, or the "before" shows the new details.
- Force-pushing this branch or merging another thread's branch into it was blocked: hand the branch over and let
  the integrator merge it.

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
