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
- The 0.40 vehicle AI (`lua/vehicle/ai.lua`) acts on signal actions 1-3 only: a "yield" (4) or "slow" (5) signal
  is driven through like "go". Give way by giving the minor road piece a lower drivability than the main road.
- The 0.40 FMOD strings bank keeps the event paths as a prefix trie: a scan for whole `event:/` strings finds none.
  0.40 has no church bell, bird or cricket events (`dati/ambient_events.json`).

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
