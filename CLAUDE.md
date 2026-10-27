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
  The bracket trick only helps if the plain name is nowhere else in the same command: `pkill -f "[s]core.py"; python3
  score.py` and `pkill -f "[c]ompare.py /home"; ... compare.py /home/...` killed the shell (exit 144) twice in the
  buildings thread (2026-10-23). Kill by PID (`ps aux | grep "[n]ame"` first, then `kill <pid>` in a separate call).
  `ps aux | grep "[c]ompare.py" | xargs kill` is no better: it lists the shell whose command line holds the name
  further on (a third kill). `pgrep -af "^python3 compare"` anchors on the process's own command.
- Push work often. An earlier session lost the fuel stations module because it was never pushed.

- The cloud container cannot upload release assets (uploads.github.com answered 415 through the gateway) and cannot
  dispatch a workflow that is not on the default branch (404): give a new workflow a push trigger on a stamp file of
  the branch (nightly_from_test.yml copies the draft test build to the nightly pre-release on GitHub's side).
- A force-push of a branch restarts every workflow whose push paths the branch touches: two rebases of the roofs
  branch reran roofs_pack.yml (it committed nothing new). Check `actions/runs?branch=` after a force-push.
- The cloud session cannot edit a release either (PATCH .../releases/<id>: 403 "not permitted for this session type",
  2026-10-23): a change to the nightly notes goes into beamng/nightly/v31_notes.md and reaches the release only with the
  next workflow that rewrites the notes.
- `gh release download` fails in the cloud (GraphQL blocked): download release assets through the REST API
  (`gh api .../releases/tags/<tag>`, then the asset URL with `Accept: application/octet-stream`).
- Cloud sessions cannot create, edit or delete releases or their assets (403 "not permitted for this session type",
  2026-10-23, publishing v3.1). Do it from michi's PC through Remote Control: gh is logged in on the Linux PC; on
  Windows DESKTOP-OUPOLOA install gh with winget and let michi enter the device code. A nightly becomes a release
  without re-upload: delete the old assets, rename the zip (PATCH releases/assets/<id>), `gh release edit --tag`.
  Read the asset id from the release itself: an id passed on between threads was wrong (669661675, real 669853164).
  DESKTOP-OUPOLOA has no winget (gh zip from github.com/cli/cli/releases, in %LOCALAPPDATA%\Programs\GitHubCLI), and the
  RC safety filter blocked `gh auth login --web` ("Create Public Surface"): michi must log in himself or say yes in the thread.
  With michi's "sì" in the thread it ran; gh is now logged in on DESKTOP-OUPOLOA (%LOCALAPPDATA%\Programs\GitHubCLI).
  v3.1 was published this way (2026-10-23 23:16Z): the nightly release is gone (only its git tag is left), so the next
  nightly workflow has to create the release again.
- pip can hang with no output in the cloud: run it with `timeout` and `--progress-bar off`, kill and retry.
- `git commit` during an unfinished rebase folds the new commit into the one being picked: run
  `git rebase --continue` (check `git status`) before committing anything else.

## Testing in the game on the PC

- The monitor may be off (OLED, black window on top): run the game in a virtual KWin session, it renders on the RTX:
  `kwin_wayland --virtual --xwayland --width 2560 --height 1440 --socket wl-mng --exit-with-session <script>` with
  `SDL_VIDEODRIVER=x11` (the plain launch hung at startup with the screen off). Measure before/after in the same setup.
- An extension name `magliaso_v31` loads `lua/ge/extensions/magliaso/v31.lua` (the underscore is a folder).
  The v3.0.40 traffic runner still installed `magliaso_traffic.lua` flat and the game never ran it (2026-10-21): check
  every new runner script against this line.
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
- On michi's PC the Remote Control permission check refused to move or even copy the installed mod zip out of `mods`
  ("Irreversible Local Destruction"), so the v3.0 comparison run (swap the zips) was dropped (2026-10-21). Plan a test
  that needs another version as a second install or ask michi to swap the zip himself; and the game had auto-updated
  overnight (0.40 -> 0.40.1): read the version in the log before comparing with an earlier test.
- After stop_rc_session the thread's folder tools (device_list_dir, device_stage_files) never came back (2026-10-21,
  only get_device_info and the computer tools were offered, also to a fresh subagent): the test results were stuck on
  the PC. Copy what you need off the PC while you still have a route; the fallback was an RC session packing one zip
  (PowerShell + .NET) on the Desktop for michi to drag into the thread. PowerShell variable names ignore case: `$w`
  and `$W` are one variable (the first packing attempt wrote nowhere).
- A Remote Control session started from a thread reports only to that thread (@parent): forward its notes to the
  other threads yourself. `list_events`/`interrupt_session` do not reach it, and a message waits until its current
  long step ends.

- Replays keep the time of day they were recorded at; core_environment.setTimeOfDay during playback works only with the
  replay paused. For sunset or night shots record the replay at that hour (tod 0.245 golden sunset, 0.27 dusk, 0.29
  lamps on with an orange sky, 0.5 full night, 0.85 morning) ("Video cinematico con pianoforte", 2026-10-21).
- PowerShell again: script parameters $B/$T collided with variables $b/$t (names ignore case) and the first scripts sent
  the wrong Lua to the game.
- On DESKTOP-OUPOLOA downloading code from raw.githubusercontent.com is blocked: test files (e.g. mngluci.lua) have to
  reach the PC through the thread's folder tools or the coordinator.
- Wikimedia downloads from that PC: Invoke-WebRequest gets 429; curl.exe with a descriptive User-Agent works.
- ETK 800 cockpit camera placed by hand: offset from the reference node forward -0.3, left 0.4, up 0.92 m (forward 0
  ends outside the windscreen).
- SendUserFile takes files under 20 MB.
- Drone video ("Video drone del Malcantone", 2026-10-22): the virtual display \\.\DISPLAY5 was detached at start (michi
  re-attached it). Mid-session the main monitor went off and DISPLAY5 became the only screen, at 0,0: gdigrab with a fixed
  offset of 2560 failed ("capture area outside window area") and then captured the Claude app instead of the game.
  Compute the offset at runtime and set BeamNG topmost.
- After core_environment.setTimeOfDay, scenetree.sunsky.elevation read in the same chunk is still the old value (it
  updates on the next frame). tod 0.77 is already night-dark; the morning golden hour is at 0.80.
- The PC's permission check (auto mode) blocked an RC session's curl download of a release zip because the order came
  from the thread, not from michi (2026-10-22): ask michi to write the download in his own words in the thread first.
  DESKTOP-OUPOLOA has no gh, so a DRAFT release asset cannot reach it: put test zips on the public pre-release nightly.

- v3.1 in-game test (2026-10-24, 0.40.3, DESKTOP-OUPOLOA): the driver camera in 0.40 is not called `driver`:
  `core_camera.getDriverCameraNameById(vehId)` returns `occupant.FL`; set head yaw/pitch through
  `core_camera.getCameraDataById(id)['occupant.FL'].relativeYaw/relativePitch` about 2 s after teleporting (a teleport
  resets it). Asking for "driver" is why every v3.0.40 cockpit shot came out as a chase view.
- BeamNG vehicles face -Y: pass `quatFromDir(-dir, up)` to `setPositionRotation`, or the car stands backwards.
- An unfocused game window is capped at 30 FPS (`fpsLimitBackgroundEnabled`, `fpsLimitBackground` = 30), and on the
  virtual display it is never focused: turn it off with `settings.setValue` before measuring FPS and restore
  settings.json afterwards, or every FPS number is 30.
- `startFreeroamByName(level, spawn, nil, false)` loads the level with no player car and leaves the main menu on top:
  spawn a car, then `guihooks.trigger('ChangeState', {state='play'})`.
- A raycast down from 2000 m hits tree crowns and roofs: use `core_terrain.getTerrainHeight` for eye-level cameras, and
  expect eye-level cameras near buildings to end up inside walls.
- PowerShell parses `"$var:text"` as a scoped variable: write `"${var}:text"`.
- v3.1 was published before its game test, with README captions written from cloud renders: the test (2026-10-24)
  found the hairpin caption "a straight top" false. Write captions of in-game screenshots only after the test.

- Automatic in-game runs on Windows (v3.1 visual check, DESKTOP-OUPOLOA, 2026-10-24/25): start
  `Bin64\BeamNG.drive.x64.exe` from the game folder. `BeamNG.drive.exe` opens the launcher, and with `-gfx dx12` the
  game said "There is no valid rendering device".
- `[System.Windows.Forms.Screen]::AllScreens` is cached inside a long-running PowerShell process: when the monitor went
  to standby the virtual screen moved to 0,0 and gdigrab failed for 40 minutes with the old offset. Compute the offset
  in a NEW process for every shot, and check the picture file exists after each one.
- A command started in the background by the PowerShell tool is not found by Get-CimInstance on its CommandLine: two
  shot runners ran at once and stole each other's teleports. Stop them with TaskStop and redo those points.
- PowerShell variables ignore case (again): a script parameter `[string]$Plan` was overwritten by `$plan = Import-Csv`.
- A test mod in `mods/unpacked` is added to `mods/db.json` by the game by itself: after removing it, restore the
  db.json saved before the test.
- The external camera behind the car ends inside trees and buildings in about 90 of 650 shots: the static raycast
  does not see the forest's vegetation (forest items are not in the static collision it tests).
- The night of 25.10 the clocks go back (03:00 -> 02:00 CEST -> CET): log timestamps run backwards for an hour.
- michi (2026-10-24): in in-game tests that do not measure FPS, cap the frame rate at 30 fps.

## Nightly v3.1.1 (merging the visual check, 2026-10-25)

- Nine group PRs were opened from main at once (#90-#98): three of them changed steep_skin.py (#95, #96, #97) and the
  merge had two real conflicts (the ROAD_CLAMP block, colours vs colours.ground). Run every merged finishing step on a
  `cp -al` copy of the released level before starting a 4-5 h build: islands, bare_concrete, yard_wear, steep_skin
  and steep_yards took 40 min together and caught nothing, but a crash at hour 4 costs the day.
- The release "nightly" was gone (turned into v3.1) with its tag left: `gh release create` on an existing tag keeps the
  tag's old commit. nightly_build.yml now deletes the tag first.
- steep_yards (#97) gives a road_m shape vertex colours for all its faces as soon as one yard face in it turns
  mp_hard_bank: the road meshes grew 1.15 -> 1.40 GB (+22 %) for the same triangles (the level +0.36 GB, the zip only
  +16 MB). Writing the colours only into the mp_hard_bank part would save it.
- check_level's network_holes (1,623) has no v3.1 value to compare with (the v3.1 checks were never kept): compare the
  road coverage instead (2 m cells of the roads/surfaces up faces): identical to v3.1 but 7 cells. Keep
  `nightly_reports.zip` of every release build in the repo's verifica folder from now on.
- nightly_patch.yml runs any finishing step on the nightly zip (MOD.FN): unzip, run, `find -newer marker | zip -@`,
  upload with --clobber (only a workflow can upload assets; the cloud gets 415).
- road_seams got a second part (sags, 1c09ad3) after its first version was already patched into the nightly zip. Running
  the whole step again would ramp the seams a second time (stacked ramps up to 78 cm): road_sags_step (steps=False) lifts
  the sags alone. Ask whether a step is idempotent before patching a new version of it onto a zip that has the old one.

## Known issues of the map (found in game, no GitHub issue yet: ask michi before opening one)

Found by the AI driving in lane during the piano video (v3.0.40, 2026-10-21), level coordinates:
- a street lamp on the edge of the carriageway at Pura, about (288, -892): hit twice;
- the inner guard rail of the hairpin about (-206, -220) on the Magliaso-Pura road;
- a post on a traffic island in Magliaso village, about (1111, -963);
- on the route spawn_magliaso -> spawn_pura, between nodes 10 and 14, a junction where the AI road drops 4 m from the
  lower road to the upper one: the car ends against a wall.

Found in the v3.1 game test (2026-10-24, report beamng/verifica/v3.1/ingame_test_report.md), causes not yet looked at:
- saw-tooth wall tops still on the Magliaso-Pura Cantonale (the hairpin, the cut near node 58 above Magliaso), after
  the v3.1 saw-top fix: the renders of the fix did not show them;
- missing materials `mp_island_reflector` and `mp_island_beacon` (30 errors each in beamng.log). Looked at 2026-10-25:
  NO file of the released v3.1 zip names them (every entry grepped); the bollards patch removed the beacon and its
  two materials, and the 30 errors = the 30 island tiles with poles. The game used shapes compiled from an EARLIER
  version (its .cdae cache), which is kept while it is newer than the .dae, and the patched .dae carried the date of
  the patch run. Fixed in the pipeline: the two materials stay defined (islands.materials) and package.py dates every
  zip entry at packaging time. Before an in-game test of a new zip, clear the level's compiled shapes in the user
  folder; and grep the zip itself for a material name before chasing a NO-MATERIAL in the code;
- the Via Golf underpass deck renders as a flat grey slab with no texture (fixed in railway.py, 2026-10-25, not built yet);
- grass tufts on the asphalt of the Ponte Tresa bridge at its Italian end (the bridge was widened in v3.1) (fixed in
  terrain.py, 2026-10-25, not built yet);
- large angular wall blocks beside strada_cantonale_1 near (-222, -60);
- AI traffic (#83) still broken: 13 cars queued behind the player's car parked on the Magliaso bridge, then crashed
  into the island at the roundabout exit (783, -1143), 8 of 12 damaged within 2 minutes. The island part is fixed in
  islands.island_lanes (2026-10-25, see Traffic and AI), not tested in game.

## Props and buildings placed wrong (v3.1 visual check, group 8, 2026-10-25)

- street_life kept its props off the carriageway MESH only: 432 props (156 pallets, benches, drums, skips, bags) stood
  inside the AI roads' width where a road crosses a yard, square or junction with no carriageway mesh (the yards are
  `mp_hard_asphalt`, not `mp_road_*`). Site.free now also keeps off the AI road lines (half width + LANE_CLEAR 0.1 m):
  0 left. A clear of 0.5 m threw out half the hydrants, letter boxes and mirrors, which stand on purpose 0.35-0.4 m
  beyond the carriageway edge: measure a new clearance on the roadside props before choosing it.
- props_osm put a bench of OSM on the rock face of a road cut (-3921, 2303; ground 656.4 to 661.9 m within 1 m): no
  slope test. Furniture now skips a footprint (0.8 m round) that rises more than 0.8 m. props_osm runs in the main
  build, so it cannot be rerun on a released level: check it by evaluating `props_osm.steep` on the final ground.
- Not bugs of the data, checked before changing code (keep them out of the next visual check list):
  "canopies on posts without a roof" are canopies whose roof and underside are there (render3d and the DAE): seen
  from a road 1-2 m under their eaves the slab is edge-on and only the posts and roof_details fascias show.
  "Trees on the road edge" (0304, 0321, 1040): no forest item stands within half width + 0.5 m of an AI road
  (1 on the whole map); the shots had trees between the camera and the car. Buildings "on the carriageway" are
  swissBUILDINGS3D houses at the edge of village lanes whose AI road is as wide as the lane (3,802 wall vertices
  inside the AI widths): moving houses is wrong, the AI width would be the thing to narrow. "Sunk" buildings checked
  (0341, 0403) are low sheds and houses built into the slope; telling a raised terrain from a hillside house needs the
  DTM, which the cloud cannot download.
- Render the in-game check points with render3d at the plan.csv pose (driver: eye 1.3 m; ext: 16 m back, 7 m to the
  right, 6 m up) before reading anything from a shot: the ext camera often stands in a tree or a roof.

## Tyre punctures and steps between road pieces (road_seams.py, v3.1.1)

- In BeamNG 0.40 a puncture is a tyre beam breaking (vehicle/beamstate.lua, beamBroken: `beam.wheelID` -> deflateTire):
  a sharp impact on an edge, never a ground model. Look for vertical edges the wheels can hit, not for materials.
- The "hole on the right before Pura" (michi, 2026-10-25: uphill, right side, after the third main curve) was a 22-26 cm
  step along 40 m between two asphalt pieces of road_m3_-01_-01 at about (-176,-122)..(-194,-104), just after the
  hairpin: the uphill lane's outer strip was meshed lower than the rest. The whole map had 6.2 km of such seams
  (1.1 km over 8 cm, max 30 cm), each a vertical skirt with collision. Finish step `road_seams` (after `roundabouts`)
  raises the lower piece into a ramp (12 m per m of step, 0.75-3 m) with its paint/wear/islands/pavements: 1.9 km
  left, 215 m over 8 cm (corners where three pieces meet; a second pass stacked ramps up to 78 cm, not done).
- The hole of michi's screenshot (2026-10-25: "after the two hairpins up from Magliaso, right after the ~90 degree
  curve", 545,-968) was not a seam: a yard and a dirt track join the cantonale from 1-3 m below, and the corridor's
  edge row was pulled down to them, the uphill lane's edge 0.75-0.85 m under the middle over 2 m (a ramp into a pit
  beside the guard rail). road_seams.sags lifts road-surface corners inside the AI road's lane (and the carriageway's
  own edge row, half width + 0.3 m) to the middle's height minus a crossfall, and ramps what joins from outside up to
  them. Corners in the lane are sparse (rows 1 m apart, the edge row just outside half width - 0.3): lifting only the
  lane's own corners changed nothing in the cross-sections. A height test alone also lifted the lower lane beside
  the wall above Magliaso (690,-1046) by 1.18 m: a sag must be joined to the middle without a step (_joined).
  Found by 0.5 m cross-sections of every AI road (drop at the lane edge vs the middle), not by holes in the mesh:
  the asphalt was there, only too low. Render the place from the player's screenshot pose before guessing.
- First version told the two sides of a seam by connected component: the two strips were one welded component
  (joined elsewhere) and both went up 20 cm, step kept. A corner is on the low side only if it lies behind the seam
  edge (outward normal) and more than half the step under the higher face's plane.
- patch_release.read_dae reads the g-pa array of the first geometry but the triangles of all of them: on the terrain
  skin DAEs (three LODs) it made garbage triangles up to 80 cm over the road. A scan reads only up to the first
  `</geometry>` (patch_release left as it is: rewrite_dae writes back what read_dae reads).
- Not changed, also puncture candidates (checked with a 0.1 m scan across the Magliaso-Pura route): low walls 10-30 cm
  standing up to 0.7 m inside the asphalt edge (walls.drive_free skips the cantonale and keeps walls under FREE_OVER
  0.3 m: s 247-307 at (646,-972) is a stone kerb under the guard rail, (-252,85) a slab by a lamp); the 5-6 cm skirt lip
  at every outer road edge; the 12 cm traffic islands. Real kerbs puncture too: left as they are.
- Writing DAE numbers with "%.4f" grew every array by trailing zeros: strip them (road_seams._set_z).

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
- The "stretched" cut slopes beside the roads (michi, 2026-10-22, "burroni") were NOT the steep skin: the skin stopped one
  terrain square short of the road (solid = road footprint dilated by 1), and the cut face right beside the road (5-7 m
  in ONE 1.5 m square) stayed bare terrain, its colour projected from above in vertical streaks. In render3d the bare
  terrain and the skin both look like smooth grey sheets: check what a surface is by listing the meshes within a few m
  of the point and by rendering once with the skin items emptied. steep_skin.foot now runs the skin into the road
  (under its surface, ROAD_DIVE), and the faces over ROCK_DEG are rock (v3.1). The skin is round: only 5 % of it is
  steeper than 55 degrees, so a rock threshold taken from the real cuts (60-80) leaves almost no rock.
- Clamping the skin lattice under the road surface was not enough (review of 92bf0fd): the rock relief moves points
  along their normal, sideways onto the road, and clip() cuts new points in along the edges. 3,553 points stood over a
  road (645 by more than 3 cm, worst 0.60 m). Clamp the FINAL points of every material after the clips (tile_mesh),
  only up to ROAD_LIFT_MAX over the road ("near" surface: never pull the skin down to a road in a gallery below), and
  keep the relief small within 2 m of a road (RELIEF_NEAR). The report counts the points before the clamp.
- Pale yellow-green patches with sharp edges on the meadow slopes of the Magliaso-Pura road (michi, 2026-10-25, hairpin
  near (-200,-215) and below Pura near (-240,50)) were the steep skin's EARTH (t_steep_bank_b: light beige with bright moss
  blobs and roots), laid on every bank between STEEP and ROCK_DEG, also on grass slopes, not a terrain layer. Under the
  skin the terrain layer is mostly Bank (the steep vertices), which says nothing about meadow or wood: take the layer of
  the nearest non-Bank, non-paved vertex. First fix: a grass texture of the skin's own in the meadow's colour. michi: "non
  mi piace, non si deve vedere differenza": no mesh looks like the terrain with the game's GroundCover grass. Now the finish
  step skin_grass (steep_skin.py, after steep_yards) removes the skin earth on meadow ground (15 % of the skin, 41 tiles
  whole), turns the Bank vertices under it into the meadow layer beside them (so the grass grows) and drops the skin's
  bushes there; rock (> ROCK_DEG) stays. It is not idempotent (the relayered vertices make more meadow: a second run took
  another 0.4 %): run it once on a zip. michi's in-game colours matched the v3.1 skin (EARTH_MIX 0.45) with the vertex
  colours taken as sRGB multipliers: a screenshot may come from the release, not the nightly; check which first.
- road_obstacles (check_level) cannot run on a released folder in the cloud: it needs network.load() data in WORK. The
  steep_skin report's skin_points_over_road stands in for it for the skin.
- The green and brown "teeth" along the foot of the rock cuts (G1 of the v3.1 visual check, ~45 points, e.g. 0277 at
  2290,5649) were the SKIN, not terrain poking through it: sampled every 25 cm the terrain was under the skin
  everywhere (max 7 cm). Within ROAD_CLAMP (1.5 m) of a road the skin was clamped to split_max of the terrain + EPS
  (against the issue #15 lip), and where a road runs across the terrain grid its carve leaves the foot of a cut as a
  staircase (road level, then 2-3 m up one square further): the higher split of those squares is a row of pyramids
  one square apart, and the skin copied them. First tries that failed: blurring the normals the rock/earth line is
  told by (the teeth stayed, the narrow faces lost their rock), blurring the rock weight alone (teeth stayed: they
  were geometry). Now steep_skin.foot_line draws a line up from the TRUE road edge (a FOOT_FINE raster of the road
  surface; the terrain-vertex footprint steps across the road too) and lower_under lowers the terrain under the
  whole skin until no split of a square stands over it, the road's own vertices outside its surface included. The
  first version of that left the terrain up to 3 m over the skin 25 cm outside the road edge: the line went on down
  under every road, also where the bank falls away from the road (the skin comes up to its edge from below) and
  under the terrain under the road. Check a skin change with the dense terrain-vs-skin sampling outside the road
  surfaces (both splits, 25 cm), not only in renders. Preview harness: run steep_skin_step on a cp -al copy with
  the tile loop limited to the tiles of the view (one tile 3 min, the whole map 13-16 min).
- G1 points NOT from the skin: 0570 (2134,3110) is a ridge of 2-3 terrain vertices 2.4 m over the road at the edge of
  an embankment with no mesh over it, the same in v3.0.40 (likely a DTM wall smear of a wall the level does not
  build); 0328 and 0091 are teeth at the foot or top of walls (walls.carve_terrain lets a terrain square rise across a
  wall "as a short bank of earth at its foot", which along a diagonal wall is a saw). Not fixed in the G1 thread.
- The skin's 90,000 bushes made check_level forest_floating jump 3,751 -> 31,847 (build test v2, 2026-10-23): canopy.check
  measured items against the terrain and mp_fill only, and the skin stands up to metres over the terrain. On the v2 zip
  every bush was 8 cm into the skin (PLANT_SINK), none over it. canopy.skin_height now reads the skin as ground (one
  tile at a time: the whole skin, 20 M triangles, in one TriSurface was OOM-killed in the 15 GB container): 1,690. A
  new kind of surface things stand on must go into every check that measures "ground", not only into its own step.
- The skin DAEs grew +51 % for +25 % triangles (v2): the rock/earth split, the clip along rw = 0.5 and the per-axis
  projection add vertices (0.59 -> 0.72 per triangle), and write_dae repeats every corner index 4 times in <p> (56 % of
  a skin file). One index per corner (all inputs at offset 0, valid COLLADA) measured -42 % on 80 tiles: not applied,
  it needs a load test in the game first (it would change every mesh of the map).
- Cut slopes patchy and low-res (michi's v3.1.1 screenshot, 2026-10-25, "rendi più omogeneo e alta risoluzione"): three
  causes in steep_skin. (1) The earth texture was 512 px over 3 m with bright green moss blobs and root lines: the
  same blobs every 3 m on every bank. (2) Each face took the projection axis it is turned to: on a rock face about 45
  degrees to x and y the relief flipped the axis from one triangle to the next, a patchwork of seams. (3) The rock
  texture's mean was 150 and the earth's 205 (and yellow, 225/212/167) for the SAME vertex colour at the line where
  they meet: a 27 % brightness and hue step along it. v3.1.3: textures 2048 px over 6 m, one mean (180, the earth
  nearly grey), axes from normals averaged over 4.5 m (smooth_axes), a cut-out fringe of earth over the rock in 5
  bands that nest (one alpha texture, alphaRef per band: border), the rock's moss calmer away from the line. A
  built level gets it from the finish step skin_blend (6 min, no-op after a build; the steep yards keep the old
  texture as t_hard_bank_*). +9 % skin triangles (the fringe), FPS not measured in game.
- render3d views of cuts were covered by big flat grey planes: the coarse far terrain (one vertex every 12 squares
  at far=2500, lowered only 1 m) spans the cut and stands over the skin inside the near region. It is not in the
  game; for views of cut slopes lower the coarse terrain (scratch monkeypatch of Renderer._terrain, cast=False).
- render3d draws every forest tree as a big cone or crown: views of slopes in woods show only trees. Render from a copy of
  the level without its `forest` folder (cp -al, then rm the folder: the hard links keep the original).
- Visual review of v3.1, group 3 ("scarpate stirate", 2026-10-25): most of the ~50 stretched cuts had NO skin at all
  (0022, 0338, 0548, 1011...): their steep vertices all lay within one or two squares of the road, inside `solid` (road
  dilated by 1), so skin_mask never seeded them and foot() only runs on from a skin that exists. 23,000 vertices over 50
  degrees near roads were bare terrain on the v3.1 zip. Before changing a texture or a threshold, check whether the face
  in the screenshot is the skin or the terrain: rasterise the near skin triangles over the terrain slope on a top-view map
  (mp_steep_bank_far parts index their own g1/g2 arrays: optimize_level.parse reads only the first geometry, so a probe
  that takes every part of a skin DAE gets triangles of 200 m). Seeding every steep vertex of the ring cost +48 % skin
  triangles; only those over STEEP_ROAD (45) and halving rock edges only over SUB_DZ 1.5 m: +11.6 % (19.4 -> 21.6 M).
  Halving edges alone did not round a face beside a road (0439): within ROAD_CLAMP the lattice was set to the terrain's
  facet and the relief capped at 12 cm, so it stayed one plane however finely cut. Now the clamp holds only the foot
  (CLAMP_HAB) and the relief may reach part of the clearance to the road edge (RELIEF_CLEAR); skin points over a road
  surface stayed 7 (none over 0.3 m) on the whole map. Each try = steep_skin on the whole released level (12 min) +
  renders (10 min): compare against a "before" run of main's steep_skin on the same copy (the step lowers the terrain
  again on a released level, so the released skin is no fair "before").
- render3d (textured) draws many road surfaces as smooth untextured grey: in the review renders a big grey sheet in front
  of the camera is the road or a yard, not a terrain slope.
- A 3x3 median "tooth" scan near the roads found 28,000 vertices, mostly in villages (yards, sidewalks): not a way to find
  a place from a screenshot. Find it from the video it came from (frames, then the road and the railway beside it).
- railway.carve_terrain kept every vertex more than CARVE_MAX (4 m) over the cutting, also one beside the bed: a lone
  vertex of the ground on top of the wall north of the line between Caslano and Ponte Tresa (-361,-2326) stood 4.1 m
  over it, and railway.build, which took the HIGHEST terrain sample across the bed, lifted the track 2.5 m onto it in a
  few metres: rails up a ramp of sleeper steps into the wall (seen in the piano video, v3.0.40; also 5 teeth at Agno
  near 2090,0). Now the carve lowers any vertex within one terrain step of the bed, and the bed sits at most LIFT
  (0.3 m) over the median of the samples. The same max sample made the 4 tracks at Ponte Tresa station climb 1 m to
  the face of the deck over them: the covered stations no longer feed the bed's smoothing. Checked in the cloud with
  TLM_EISENBAHN printed into a workflow log (swisstopo blocked here) and railway.build run on the released level
  (rebuilt "before" matched the released sleepers to the cm). render3d.Level takes the level name from the folder
  name: a copy of the level in a folder named otherwise draws none of its meshes.
- network.SKIP left out every swissTLM3D underpass (KUNSTBAUTE Unterfuehrung) with the tunnels: Via Golf (Caslano -
  Magliaso, 874,-1306) ran down into its cutting on both sides of the FLP and ended against 4-5 m of railway embankment
  (v3.0.40, 2026-10-23). The rails there are not a TLM Bruecke: the road line carries the structure. An underpass is
  kept only under a railway and under no road (network.underpasses; Caslano station's footway runs under the Via
  Cantonale too), and the lines over it become bridges there (over_underpass). In the TLM a Treppe (stairs) is not
  an underpass: filter on the exact KUNSTBAUTE value (a probe filtering "not Keine/Bruecke" listed 200 stairs).
  The first v3.1 build with it still had two faults there: the two 1 m footways kept with it took the DTM, which beside
  the road is the embankment smeared under the deck (2 m over the road, 1.2 m under the rail deck: the 9 new path
  "binario" obstacles of check_level, also in the v3.0.40.1 test build), and the survey's wing walls stood 0.4-0.9 m
  into the asphalt at the four corners (the drive-free band is a quarter of the width, and the survey has no road
  polygon in an underpass). network_surface.under_walkways puts the footways on the road + 15 cm, walls.drive_free
  frees the whole width + 0.3 m of an underpass. Not built yet (fixed after the v3.1 nightly) The wing walls of the nightly zip were
  patched in place (patch_underpass_walls.py, nightly_patch_v31.yml): only the numbers of the DAE's g-pa array
  change, so the solid stays closed and nothing else of the file moves (rewriting the 1.5 GB zip takes about 6 min).
  Pushing the walls out also showed the raised footway under the deck from the road (not patched: it needs the build).
  So the nightly v3.1 zip is NOT a plain build of its commit: compare a fresh build with it knowing the Via Golf walls
  were moved afterwards. The collision is the visible mesh ("Visible Mesh Final"), so the cars hit the moved walls. The
  patch script and its workflow are left out of the release PR to main (michi's rule, PR #49: no patch scripts there).
- A height band is not the lake: network.LakeCut cut every dtm05 cell between lake level -2 m and +0.15 m out of the
  surveyed paved polygons, and the floor of the Tresa valley below Ponte Tresa (268.6-270.5 m, lake 270.48) lost its
  yards and roads (about 1,800 4 m cells, network_holes 418 -> 1417 in the bridge thread's test build, 2026-10-21).
  Cut only the low patches that touch the surveyed lake (MU specchio_acqua), and check a lake cut by the area it removes.

## Yards, bare Concrete and river gaps (v3.1 visual review, group 5)

- The "grey-blue flat surfaces without texture" of the review (0205, 0207, 0410, 0473, 0485, 0493; two were reported as
  water planes) were no mesh at all: the terrain layer Concrete (classes edificio and bacino_idrico) where no building
  stands. terrain_colors.py measured Concrete on the open ground of those cells, which is the water of pools and basins:
  151,165,165, grey-blue, and the orthophoto base map made it bluer still. 36.6 ha of it lay bare (houses built into a
  slope, buildings missing from swissBUILDINGS3D, basins). Before calling a flat surface "water" in a screenshot, look
  for a water mesh there (level_objects/Water) and read the terrain layer: neither showed water at five of the six.
  Fixed by the finish step bare_concrete (nearest non-Concrete layer where no solid mesh touches it), a fixed Concrete
  colour in dati/terrain_colors.json (terrain_colors.FIXED) and no orthophoto base map for Concrete.
- The big yards (mp_hard_asphalt, 172 ha) had none of road_wear's dressing: it works along AI roads only. yard_wear (after
  road_wear, it needs its overlay materials) lays the blotches, dusty edges, patches and cracks on yards of 600 m2 or
  more (452 yards, +754k overlay triangles, mostly the blotch layer). Random patch angles looked scattered: lay
  rectangles along or across a yard's long axis.
- The Swiss survey stops at the border, which runs along the Tresa: where the river is all in Italy the water ended
  in a point (0391) and the bed went on dry under forest floor. rivers.osm_channels adds the channel along OSM
  waterway=river outside the survey (lowest ground of each cross-section + CHANNEL_DZ). Tested in the cloud only by
  emulation on the released level (the .ter as the DTM, the existing water as the survey): with CHANNEL_DZ 0.6 and no
  opening it also took ragged patches of the flat ground beside the Tresa below Ponte Tresa; 0.45 and an opening of
  2 cells left one small low patch. Check the build log's osm_channels / ha_osm_channels and the river near
  (-2250, -1060) in the first build with it.
- The render tool render.py of the thread was run on a `cp -al` copy; the .ter was replaced as a new file (os.remove,
  then write) so the hard-linked original stayed as it was. Cameras placed by hand at (x, y, z) without reading the
  terrain ended under the ground twice: take z from the .ter.

## Ground materials (visual review of v3.1, group G4)

- The pale grey-green banks all over the map (whole hairpins, every cut in the woods, 0456 at -3872,119) were the
  terrain skin's colour, not its rock: steep_skin.BaseColours looked a layer's colour map up as
  `t_base_<layer>_b.png`, and the twins added later (understory: ForestFloorVerge/Light, forest_mosaic: ForestRock,
  BankWood) have no such file: their vertices took a flat 0.55 grey, which EARTH_MIX made pale. Read the map from the
  level's terrain materials (baseColorBaseTex). A step that adds terrain layers must check every reader of layer names
  (BaseColours, render3d._layer_colors, groundcover lists), not only its own.
- The skin runs into the road (FOOT) and its colours are blurred over 3 squares: the light Asphalt/Concrete layer under
  the road meshes greyed the foot of every bank. The skin takes the nearest natural layer's colour (BaseColours.ground).
- With the colours right the skin was still about twice as bright as the forest floor round it (pale patches with a
  sharp edge, 0192/0509/0519): EARTH_MIX 0.45 pulled every colour towards EARTH, a light beige. Three rounds of renders
  to settle it: the terrain's brightness alone (as dark as the forest floor's macro colour, 62 sRGB, darker than the
  detail-textured terrain beside it), times 1.35 (meadow banks still pale beige: the desaturation, not the brightness,
  made the edge), then EARTH_MIX 0.25 at the terrain's luminance + EARTH_LIFT 0.08 (steep_skin.earth_colour). A full
  steep_skin rerun + renders is about 40 min in the cloud: try a tint on a few lattice colours against the ground
  colours of the review points first, and check it against the ground beside it, not alone.
- `pkill -f "[s]hots.py /home/..."` in a command that also named that path later killed the shell again (exit 144).
- The "asphalt on slopes" (0030, 0160, 0161, 0399) were survey yards (altro_rivestimento_duro) meshed on the DTM, which
  smears walls and terrace edges into slopes: 14 ha of mp_hard_asphalt at 20-60 degrees in v3.1. Finish step
  steep_yards (after steep_skin) gives yard faces over 18 degrees (32 %) the skin's earth (mp_hard_bank, same geometry);
  24 degrees missed the light ramp of 0399, mostly 10-20 degrees.
  The skirts (over 72 degrees) are left alone. Mean slopes per material lie: area per slope band is the useful probe.
- Gravel at 150 sRGB (surface_textures.BRIGHTNESS) read near white with a blue cast in the game's light (0280); now 124.
  Italy's setts and cobbles at 1.0 were the brightest thing in a meadow (0367): STONE_TINT.
- Roof colours were the orthophoto median over the roof: tree crowns over a roof made 5-14 % of the roof area green
  (0165, a shed with a "grass" roof). buildings_mesh.roof_colors drops the green pixels; a roof is never green.
- Checking these in the cloud: probe the level for terrain layers and mesh materials near a point (layer counts +
  mesh area per slope band) before guessing; render3d (no orthophoto) draws the terrain in the layer colours and the
  skin with its vertex colours, so it reproduces the pale skin. Rerunning steep_skin on a released level lowers the
  terrain under the old skin a second time (changed_max_m 4 m): fine for renders, never for a release.
- PIL `save` onto a path that is a hard link (cp -al copy) writes into the original too: remove the file first.

## Bridges

- On a bridge the survey draws the bridge (SOSF ponte_passerella), not the carriageway (LCSF strada_sentiero), so
  network.measure_width found nothing there and the deck took the nominal width of the class (3.2 / 4.5 m, decks of
  3.8 / 5.1 m) between approaches measured at 6-9 m: about 20 of the 64 road bridges of the v3.1 test build were a
  bottleneck (2026-10-23). A deck width equal to the nominal one is the sign. Now measured in the bridge polygon, or
  as wide as the narrower approach (network.widen_bridges, one width for a bridge in pieces).
- A survey bridge polygon is not always the deck: at Ponte Tresa the Swiss half is one 19.7 x 18.6 m polygon with the
  bridgehead, and the border bridge came out 18.7 m wide (a second piece, in Italy with no survey, took it over the
  chain). Its approach was no check either (the customs square measured 15 m). Polygon widths are now capped at the
  narrower approach + 2 m (network.cap_bridge_polygons) and Ponte Tresa has "width": 11 in ponti.json (supervisor's
  review, 2026-10-23). List every widened deck with old/new and approach width before handing a width change over.
- A survey deck (bridges.survey_height) was eased at its edges to the bare DTM, not to the road that joins it: the
  road surfaces (corridor, network_surface) are smoothed and differ from the DTM, steps of 0.3-0.45 m at the Magliaso
  bridge corners. Join a deck to the road mesh beside it (build_level passes the road tops as `surface`).
- The bridge thread tested in the cloud without a full build: a temporary workflow ran the downloads, network.py and
  `build_level.py roads` alone (about 35 min, the roads stage 21 min) and put the road meshes on the draft release;
  swapped into the extracted test build (roads/surfaces items + DAEs) they gave before/after renders and measures.
  First try of the road join took any road surface within 1 m: a path beside the bank pulled a deck corner 0.8 m
  down; within 0.5 m, and a surface further off is a drop (no join to the ground there either).

- Grass on the Ponte Tresa deck (v3.1 test, visual check group 6, 2026-10-25): the deck, 11 m wide since v3.1, lies on
  its Italian bank (Copernicus meadow, no survey) and paved_edges raised that ground to 5 cm under the asphalt; the
  layer stayed Grass because no_cover (no GroundCover) is made from the road carve, and the decks are not carved, only
  capped. 22 grass vertices there, 45 under all the decks. terrain.build_terrain now gives the verge twins (no cover)
  to the ground under a deck within DECK_COVER m of its slab. render3d draws no GroundCover: check grass by the layer
  under the road faces (Grass/GardenGrass vertices less than 1 m under a top face), not in a render.
- The Via Golf rail deck was a flat grey slab in the game: mp_rail_deck was a plain colour (railway.build) and its uvs
  the (x + z, y + z) of the track parts. Now Italy's m_concrete_old with box uvs, as the road decks.
- The "road ends on a raised slab" points of the visual check (0055, 0352, 0373, 0440, 0479, 0576, 0577): 124 of the
  128 km of paved outer edges more than 0.5 m over the ground were in the paved_edges keep-out (2 m of 1 m cells round
  walls, buildings, fences, guard rails, railway, water, parapets), where nothing over KEEP_OUT_LIFT is raised. Most
  of it was not a slab but a TRENCH: the road carve lowers the ground to 0.1 m under the lowest face within one
  terrain step, so beside (and under) a road that climbs into a slope it dug up to 1.7 m (0576), and near a wall it
  stayed. A first rule "raise where no wall is closer than the road + HOLD" (hold()) changed only 43,446 vertices and
  no render showed it; the second rule (pits(): ground higher than the road by PIT_UP within PIT_N steps, not under a
  road) does the work. Its first version compared with the vertex's NEW height and took the ground between the road
  and a wall as "higher ground": 327,373 vertices, also beyond retaining walls. Compare with the road height
  (block() now returns it). Together: 227,040 vertices, edges over 0.5 m 127.8 -> 49.9 km. 0448 and 0561 are flush
  (the line just ends), 0352 is the lake (water kept out), 0577's yard stands 6 m over the ground (over EMB_MAX).
  A rerun of paved_edges on a released level is no preview of a change: later steps moved things and the rerun alone
  raised 321,241 vertices. Run it twice (with and without the change) and take only the vertices that differ into
  the released terrain (about 15 min a run, PATCH_WORKERS=3). render3d cameras 9 m out from an uphill edge end up
  under the ground: put them on the road looking out. Do not truncate a log a running process still writes (nohup
  restarted on the same file left NULs and the old run's last lines in it).
- The Ponte Tresa road ends at the border on the Italian meadow (no Italian roads in the level): the deck end is flush
  with the ground (checked along the axis and 6.5 / 9 m to the sides); the "slab" of the shots is the deck's side over
  the bank. Not changed.

## Checking a finish step in the cloud container

- Rerunning a finish step on the released folder for a preview: copy it with `cp -al` (bng.LevelWriter replaces
  files with os.replace, so the hard-linked original stays as it was). steep_skin on the whole map takes 10-12 min.

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

## Bridges and survey data (v3.1, Magliasina bridge at the Magliaso roundabout)

- The cloud container cannot reach data.geo.admin.ch, geodienste.ch or Overpass (proxy 403), and cannot download
  Actions artifacts; it can download release assets. `ponte_ref.yml` fetches a swisstopo/survey window on GitHub and
  commits it; `ponte_test.yml` builds the level to a DRAFT release (not public) whose zip the session can download.
  The raw window (rif/, 6 MB of swisstopo data) is not kept in git: run ponte_ref.yml on a scratch branch to get it
  again, and delete the draft release when the test is read.
- A force-push that rebuilds a branch counts every file as changed: it started ponte_ref.yml and ponte_test.yml
  (path triggers on their stamps) and the first would have committed the raw data again. Cancel them at once
  (`gh api -X POST .../actions/runs/<id>/cancel`) or give such workflows only `workflow_dispatch`.
- A bridge drawn as a strip along the swissTLM3D line is only as wide as one carriageway: the Magliasina bridge is
  one 25 m deck carrying two roads, and the strip left the river showing through it for three versions. The
  survey (SOSF ponte_passerella) has the true outline, swissSURFACE3D the deck top (LiDAR class 17).
- Two swissTLM3D pieces of the SAME line (split at a node on the bridge) were paired as "twin decks" by
  twin_pairs (collinear, 0 m apart): the twin test does not tell a split line from two carriageways.
- swissALTI3D slopes down 1-3 m out from a bridge end (the bridge is removed and the abutment smeared): read the
  ground 1-3 m out (the highest) before calling an edge a drop or a join, or parapets stand across the road.
- The survey marks channelised stream banks as 'altro_rivestimento_duro' (hard surface): meshed as asphalt they
  were grey ramps into the river. landcover.channel_linings turns steep ones along a 'corso_acqua' into stones.
- A big grid is stored by Grid.save as `<name>.npy` + `.json` and the `.npz` is removed: checking
  `os.path.exists("dsm05.npz")` found nothing and the first test build fit no LiDAR plane (line heights only).
  Check both names, load with Grid.load("<name>.npz"), and grep the build log for what the step really used.
- Compare a test build with the last nightly by the road mesh it covers (roads/road_*.dae on a 4 m grid), not only
  by check_level counts: network_holes rose 418 -> 1417 and the cells showed two causes, the intended banks and
  network.LakeCut removing the paved yards on the Tresa valley floor (at lake level, 2026-10-21).

## Pavements and kerbs (sidewalks.py, v3.1)

- Up to the v3.1 test zip every pavement (mp_sidewalk) was meshed flush with the road (dz 0 on the shared edges): no
  kerb anywhere. The finish step `sidewalks` raises them on the built level (works on a folder, so a zip can be patched).
- The AI roads are as wide as the carriageway: "no kerb within the AI road's half width" lowered 94 % of the kerbs
  (the kerb IS the AI road's edge). Only the part more than 1.25 m inside the half width stays flush (AI_CLEAR).
- A yard (mp_hard_*) next to a pavement is not always an entrance: the survey draws a garden wall as a line between
  the two areas, so check the walls and fences along the edge before lowering the kerb (barriers()).
- Merged pipeline shapes have their position at the tile middle with z 0: lifting objects by the ground under their
  position would lift a whole tile. Skip objects whose position z is 0.
- numpy 2: np.cross of 2D vectors raises ValueError; write the 2D cross product out.
- Parking spots (city.sites.json) can reach over a pavement: a car spawned on a raised kerb jumps. The build keeps the
  pavement flush under them; the nightly patched before that had its 8 spots removed (patch_parking_kerbs.py).
- Props merged per tile (delineators, direction signs, OSM furniture) are not moved by changing an item position: lift
  each connected piece of the DAE whose feet stood on the pavement (sidewalks.py, merged_pieces_raised).
- sidewalks.py is not idempotent: on a zip that already has roads/sidewalks it finds no pavement in roads/surfaces.
  A follow-up to a patched zip needs its own small patch, not the step again.
- Roundabouts (roundabouts.py): the survey draws the setts round the middle as an island (islands.py raised it and put
  a keep-right sign on it), leaves asphalt under part of the middle, and the terrain makes a mound there; a green top
  on a plane cut through both. The middle reaches out to that island ring, the road faces under it go, and the top
  never goes under the highest terrain vertex round each point. The mean of an OSM ring arc is off-centre: use the
  box of the joined ways.
- Mapillary photos and orthophoto crops for a few points: luoghi_ref.yml commits them to beamng/verifica/luoghi/ref on
  the thread branch (a check only: never merge that folder; the photos are CC BY-SA).

## Bus stop paint (stop_paint.py, v3.1)

- The road paint is laid by rules (markings_rules.py, v3.0), not traced: anything the rules do not know is missing
  everywhere. Bus stop paint (yellow zigzags, BUS) was on 17 of 265 Swiss stops. stop_paint.py lays it from the
  orthophoto. The v2 trace had them only in pieces: network_markings' 2x2 opening breaks lines 1-2 cells wide, and
  faded yellow (saturation 26-50 in a 10 cm cell) fails its S>45 test. Measure thin paint against the ground round it
  (median of R+G-2B over 3 m) and join pieces before classifying. A join wider than 3 cells merged the bars of every
  crossing into one blob (156 -> 61 crossings).
- A yellow car, a flower bed and the yellow van of a bus yard read like letters or bars: drop marks with dark cells round
  them (windows, leaves), crossings need 3 parallel bars, and paint must lie on the asphalt faces of roads/surfaces
  (whitelist the materials: the up faces of mp_road_wall are wall tops). Paint "off the road" far east (x > 4000) is
  outside the level's network: OSM covers more than the map.
- The v3.1 stop paint still laid every traced shape it could not name (G9 of the v3.1 visual check, 2026-10-25): BUS
  letters and crosses of a faded bus yard came out as yellow blobs, a star and L shapes (Caslano station), a yellow bus
  front and a motorcyclist's jacket in the lane passed the "mark" test, a sunlit shade edge on a mountain road became a
  5 m yellow bar across the lane, the corners of bay frames passed as zigzags (Ln >= 4 m, low fill: an L has both), and
  the real zigzags were their traced outline widened, a thick wavy band. Now marks are not laid, a zigzag must swing
  left and right 3 times with 1 m legs and is redrawn straight from its centre line, and strips need 2 m and a zigzag
  or crossing within 15 m: 626 pieces laid -> 107 on the v3.1 zip. Look at a traced class over the photo crops
  (overlay of the polygons on luoghi/gialli, kept on claude/project-thread-bpnv3b) before laying it, not only at counts.
- islands.py (v3.0) put a short white beacon with a yellow reflector beside every keep-right pole: no island of the
  area has one, the photos show the pole's foot in a black and yellow sleeve (155 poles). Check a street object's look
  against a photo of the area before modelling it from a norm or from memory.
- Game views at a Mapillary photo's pose: the pose is off by metres and the nearest AI road can be a side road or a
  yard, so a camera at "AI node z + 1.45 m" stood on a parking lot higher than the road and saw nothing of a roundabout.
  Snap to the road the photo looks along and take the height of the asphalt faces under it.
- render3d skipped every merged shape whose position (the corner of its 384 m chunk) was over 300 m from a small view:
  whole blocks of Agno came out without buildings and looked like a level bug. The margin is now 560 m.
- luoghi_ref read only one orthophoto tile: crops near a 1 km tile edge came out half white. It now mosaics every tile
  the crop touches.
- Bus shelters (bus_shelters.py): "the edge of the asphalt" was found on parking.Ground.S, which holds every paved
  surface (yards, pavements): where a yard joined the road no edge was found and the shelter stood at the AI lane's
  half width + 0.5 m, on the carriageway (6 of the 36 v3.0 shelters, one on a roof). Read the edge on the mp_road_*
  faces only. The shelter (Italy's model) is not in the cloud and render3d draws nothing there: check placements
  by drawing the footprints on the orthophoto crops (luoghi/gialli has 60 m crops of every bus stop). The step took
  33 min because the edge scan asked TriSurface.height one point at a time: one call for the 32 offsets, 5 min.

## Meshes

- The FLP track showed as a brown zigzag in michi's video beside the cantonale (2026-10-22): the geometry is straight
  (no rail triangle wider than 30 cm in the v3.0.40 zip, rails straight in plan); the sleepers stood 16 cm out of a flat
  bed and low sun threw the rails' shadow in steps. railway.CRIB brings the ballast up to 4 cm under the sleeper tops.
  Not seen in the game yet (PC unavailable that night).
- Floating roofs left in the v3.1 test build (2026-10-22): the 5 check_level counted were all swissBUILDINGS3D
  `Flugdach` records (station canopies at Magliaso and Caslano, the fuel station forecourt, Sessa): the survey gives
  them "walls" that are only the 10 cm edges of the slab, so `len(walls) > 0` made buildings_mesh treat them as houses
  and canopy() never gave them posts. Do not tell a roof without walls by an empty wall list: look at how far its walls
  reach under the eaves. The check could not see the other kind at all: a house's own roof reaching metres out over a
  porch or lean-to with nothing under it (the house's walls touch the roof outline). Finish step roof_posts finds both
  on the built level (roof plan minus what tall faces hold) and adds posts. A detector that tests only the outline of
  a roof flags every normal eave (0.6-1.5 m): measure the overhang from the walls, not from the outline. Facade
  plaster between windows is made of faces under 0.8 m high: a "tall faces hold the roof" test with 0.8 m missed such
  walls and stood a post along a facade (TALL 0.35 m, above the 0.27 m fascias of roof_details).
  The first runs also doubled the posts of buildings_mesh's canopies (a wide canopy left free strips between its own
  posts): roof_posts now skips every roof that has a post already, told by the post vertex colour (post_color).
  roof_posts was first put right after roof_details, before fuel_stations: its posts would have counted as walls under
  the survey canopy fuel_stations replaces. Anything new that stands on the ground goes before parking/street_life
  (they keep off the building meshes) and after the steps that cut or replace building pieces.
  Keeping posts off the carriageway MESH was not enough: build test v2 had 3 new 'edificio' obstacles (road 43 -> 44,
  paths 172 -> 174), posts under porches and yard roofs where a road or path runs with no mesh of its own (check_level
  drives the swissTLM3D line with its width). roof_posts now also keeps off the AI roads with their width and the OSM
  highways (1 m round): anything placed on the ground must test the lines, not only the meshes.

- Roofs were a sheet with no thickness and plain folds at the ridges; tegole/metal textures of 2 m with thin, low-contrast
  lines read as one grey surface from 30 m (michi 2026-10-22, lake-shore house in the cinematic video). v3.1: finish step
  `roof_details` (rim with tile heads and fascia, ridge caps; after house_details/house_extras, which read the bare
  roofs) and new 4 m textures for coppi, tegole and metal. Costs: +931k triangles on 2.61M of the buildings (+36 %).
  A first draft of the tile colours divided the blue by the "redder" factor: blue tiles. Changing ROOF_TILE changes
  the roof UVs only in a full build: to preview new textures on a released level, scale the roof UVs too, or the
  tiles come out at half or double size. The many plain grey roofs of houses are `metal` (facades.roof_kind: grey
  orthophoto, slope < 25 degrees), not tegole: check which kind a roof is before changing a texture for it.
- Floating roofs (v3.1): 620 roofs of swissBUILDINGS3D have no walls at all (canopies, covered parkings, boat houses,
  platform roofs; OBJEKTART says "Gebaeude Einzelhaus", only 5 are "Flugdach"), so a kind filter finds none of
  them. 3490 more records are roofs alone too, but their house's walls are a separate record under them: tell them
  apart by the roof plan over the ground plans of buildings with walls (buildings_mesh.canopies), never by
  `len(walls) == 0` alone, or every such house gets posts and a slab.
- Finding them in a built level: union the roof faces per tile and look for faces of other materials near the
  outline that reach down from the eaves (check_level.floating_roofs). Counting "wall feet above the terrain" per
  vertex column gave only noise (chimneys, upper storeys, plinth decals): drop that approach.
- Posts are not right for every roof without walls: the cadastral survey says which are open (SOSF riparo,
  altra_parte_di_edificio: posts) and which are houses (LCSF edificio: walls along it). The unknown ones got walls
  under the roof at first, which turned a roof 12 m over a railway yard into a box across the tracks: walls only up
  to eaves SHED_EAVE m high (buildings_mesh.close_roofs). A pack made without missing_buildings.py counts 912
  instead of 620, because the survey's buildings it adds stand under 292 of these roofs: test against the built level.
- An attempt to add posts under roofs that overhang their walls by more than 1.8 m (issue #13) found 1260 roofs,
  mostly garage decks at ground level and canopies merged into a house's roof: not done, #13 stays open.
- render3d.Renderer resolves the shapes by the level folder's name: a test copy of a level must be called
  `magliaso_pura` (a copy named otherwise renders terrain only). Use `cp -al` (hard links) and replace the files you
  change by new files, so the original level is not touched.
- The cloud container cannot reach swisstopo: data packs come from a workflow that commits them to the branch
  (roofs_pack.yml, landmarks.yml). prepare_work.py crashed on the folder dati/far_imposters (fixed: folders skipped).

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

## Undergrowth (understory.understory_step, groundcover.UNDERSTORY_COVERS)

- ECA's `lush_ferns_*` (art/shapes/groundcover) use the material `forest_vegetation`, which East Coast USA itself
  does not define (Cliff and driver_training do): a material lookup in the model's own level found nothing. The
  definitions of the undergrowth models are in dati/understory_materials.json (taken from the game, 2026-10-22).
- An edge band measured from "any other layer" made the whole wood outside the area a light-green speckle: the land
  cover leaves specks of meadow inside the forest. Openings under 400 m2 are no edge (SPECK_M2).
- The trees' crown radius from the model's bounding box (asset_bounds) is wider than the leaves (median 7.3 m): with
  it no forest floor was ever in a gap (0.03 %). The gap test uses the distance to the nearest trunk instead.
- A GroundCover places shapes upright on the ground, not along the slope: a 10 m fallen tree on a 30 deg slope hangs
  5 m in the air. The first limits (9 and 14 deg) still lifted an end 0.7-0.8 m (supervisor review): 4 deg for
  tree_beech_dead_b, 6 deg for _a.
- A GroundCover takes at most 8 Types (Torque3D MAX_COVERTYPES; every GroundCover of the game's levels has at most 8).
  The first version had 16, 34 and 18 in one object each: if the cap holds only the first 8 (all shade rows) would
  have stayed and the light zone would have had nothing (supervisor review, 2026-10-22). Now one GroundCover per
  layer, at most 8 Types each, which also stops one layer's types thinning another's (groundcover.density).
- GroundCover plants have no collision: stumps and 1.5 m stones near a road are drive-through ghosts. Keep them in the
  shade; in the light only small stones, and every model's reach checked against its box (check_light_reach).
- A finishing step can only be tried on a released level after undoing what the step itself added: the released
  .ter already has the verge twins and understory_step refuses it. Map the Verge layers back and drop their names
  from the .ter tail, terrain.json and terrain materials (done for the v3.1 test, 85 s for the step).

## Forest floor (understory, forest_mosaic)

- `understory.face_cells` over the terrain skin (`level_objects/terrain_skin`, 3.9 GB of DAE, ~20 M triangles) ran more
  than 30 min without finishing in the cloud; the SOLID groups alone take about 2 min. The skin's triangles are about a
  terrain square: rasterise its vertices (forest_mosaic.skin_cells, 23 s).
- understory.py imports trees.py, which needs scikit-image: a patch workflow that imports understory must install it.
- The shade rows of the undergrowth hold 10 m fallen beeches and 4 m clumps: understory kept the shade EDGE_M (10 m)
  from every edge. Narrowing the edge to 3 m along roads under the crowns (forest_mosaic) first put the shade 3 m from
  the asphalt; within SHADE_CLEAR_M of a solid mesh there is now only light (reach-checked models) or bare litter.
- A steep bank (Bank layer, >40 deg) is not an opening of the wood: counted as one, the cut slopes made every road in
  the wood look like a meadow edge (wide light bands). Thresholding one smooth noise field gives round blobs with
  smooth outlines: add a finer octave (forest_mosaic._field).
- The terrain skin is not in understory.SOLID, so the undergrowth (and at first the mosaic's woodland grass and outcrop
  stones of 2 m) stood on the forest layers under the skin of the road shoulders, through it beside the asphalt; the
  integrator saw it in a render of this thread (2026-10-23). The skin is ground of its own: no forest layer under it or
  within two squares (forest_mosaic: the verge twins there), outcrops ROCK_CLEAR_M and bank stones BANK_CLEAR squares
  from it and every solid. Check every new GroundCover against the road AND the skin footprint in a render.
- `/usr/bin/time` is not installed in the cloud container (a background run died at once): use resource.getrusage.
- "No grass in the wood" (michi, 2026-10-25, v3.1.1): v3.1 had grass only on the light twins; the shade had none, and
  the verge twins were both "near a mesh" and the mosaic's bare litter, so 75 % of the wood floor 5-10 m from an AI
  road and 50 % at 25-40 m had no plant at all. Measure the layer shares by distance to the AI roads (what the car
  sees) before tuning a cover's density. Now the litter twins (forest_mosaic.LITTER, +2 terrain layers) take the
  bare litter more than two squares from any mesh or skin, and SHADE_GRASS/LITTER_GRASS put grass there; finish step
  forest_grass does it on a level of v3.1. The ground right beside most woodland roads is the terrain skin (a mesh):
  no GroundCover can green it, only its own bushes. The first density (1 tuft per m2 in the shade) looked bare in
  the renders: 2 now. The renders draw each billboard as a 6-blade tuft, thinner than the game's textures: judge the
  density in the game.

## Tunnels (tunnels.py, finish step `tunnels`, 2026-10-26)

- The swissTLM3D tunnel lines of all of Ticino come from tunnels_ref.yml (beamng/ticino/dati/tunnels_tlm.json.gz): 436
  lines, 346 km. In the Malcantone level only the FLP Galleria del Vallone d'Agno (60 m, 2064,-54 -> 2091,0) joins
  the built meshes: Crespera has no track near it, the other road tunnels are in Italy or outside the network.
- A portal is "live" if a road or track mesh is there. Rail heads are 7 cm wide: a point-in-triangle test at the
  portal never hit one and the first run found no live portal. Tops.height takes the median rail-head z within 2.5 m.
- Holes are terrain layer 255 (no render, no collision). Anything that indexes a lookup table by layer crashes on it
  (render3d's layer colours did: IndexError 255). So the step runs last among the steps that touch the ground
  (after vineyards_ground). Steps that read layers (steep_skin, forest_mosaic, understory) must never run after it
  without handling 255. The assumed square convention (sample (r,c) owns [c..c+1] x [r..r+1]) is NOT checked in the
  game yet.
- The first tube had no straight walls: the inner sweep took ring[1:-1], so the vault started at the wall top and
  one saw the lake under it from inside. Sweep the whole ring.
- A yard of the roads group (mp_hard_bank of steep_yards, meshed on the DTM over the tube) stood inside the tube as a
  big curved grey sheet: the roads are cut too (in_volume only, so a road on top of the tube stays). Check the inside
  with a probe (points of every group inside the inner profile), not only with renders.
- In render3d the coarse far terrain (step > 1) spans the holes and draws a grey sheet through the tube that the game
  does not have. Lower it in the render script, as for the cut slopes.
- The camera "25 m out on the tangent" stood inside the bank: the track curves before the portal. Place cameras from
  the Tube's own stations.
- cut_meshes read every shape of the groups across the whole level (76 s for one tunnel). Skipping shapes whose
  position is more than SHAPE_REACH from a tube: 12 s.
- Importing config without MAGLIASO_ROOT made a folder "D:\beamng_magliaso" in beamng/pipeline (Windows paths taken as
  relative): export MAGLIASO_ROOT before any scratch import.
- In the game (laptop run 3) the vault stood bare behind the S headwall: the DTM's portal cuttings reach 4-8 m into
  the swissTLM3D tube and on the lake side the slope stands under the shell along the whole tunnel (holes there, the
  shell was what one saw). tunnels.mound raises the terrain over the tube (COVER_MIN over the shell, 1:1 down over
  MOUND_W, never over a road/track face beside it): shell points over the ground 38 -> 0, holes 100 -> 27. Raising
  vertices up to the headwall's back made the terrain and the hole caps in front of the face slope up into the
  opening (spikes on the track): only from the swissTLM3D portal in. A floor plate now covers the stretch under the
  headwall (one saw the lake through the holes beside the ballast). Check with a probe of shell points vs the
  terrain (square_height, holes skipped), not by eye.
- Laptop run 4: the headwalls stood on nothing on the lake side (ground 2.4 m under the floor beside the track, the
  wall's sides ended 0.6 m under it): a gap under the S portal at track level. Each side now goes FOOT under the
  lowest ground at its outer edge, with the triangle under the floor's edge closed.

## Data from the cloud sessions

- swisstopo (data.geo.admin.ch, api3), Overpass and the BFS register (public.madd.bfs.admin.ch) are blocked from the
  cloud container (proxy 403). Compute anything that needs them in a small GitHub workflow that commits its result
  to the branch (strade_extra.yml, paesi_interi.yml), and test the code locally with stand-in inputs first.
- Growing the area (area.py) changes what the pinned extracts in beamng/dati must cover: re-pinning them pulls newer
  data for the whole map. Add only what is new (download_gwr.py --add) and check the OSM extract's bbox.
  It also leaves the README/website map (web/map.svg) stale: v3.0.40 grew to 58.6 km2 and the map still showed
  56 km2 without Caslano until v3.1 (michi noticed). Rerun `python web/tools/make_map.py` (needs shapely, pyproj).
- `osm_area.json.gz` is Overpass `out geom`: a way's points are in its own `geometry`, the `node` elements are only
  tagged nodes, and the `bbox` is the nodes' bbox. Looking ways up through node elements found none near a Caslano
  slipway and the integrator wrongly reported Caslano missing from the extract (2026-10-20).
- Overpass answered 502/504 from GitHub runners to every query on 2026-10-20, even 1 km boxes, for hours: read OSM
  from the Geofabrik extract with osmium instead (download_osm.py --add).

## Asphalt age from the photos (road_age.py, asphalt_survey.py, v3.1)

- In the 2024 SWISSIMAGE the shadows of trees are 0.15-0.4 of the asphalt and new asphalt is about 0.6 of old: shadow
  masks relative to a road's own median failed on roads that lie wholly in the wood (the median was the shadow). Mask
  against the asphalt of the 1 km photo tile and grow the mask by 2 cells: the half shadow reads as new asphalt.
- The first patch search found 1,178 "patches", nearly all shadow fringes, dark cars beside light ones and road
  edges: keep only dark rectangles with sunlit road all round them (ring test, no light car next to it): 36 left.
- The two halves of a road segmented apart rarely agreed where a stretch is new, and drew a joint along the axis
  almost everywhere: a half next to a new one that is unmeasured or nearly as dark is new too (Survey._halves).
- TriSurface.height(..., "near") needs a zhint for every point: a point without a height of its own goes through
  "high" first (road_wear.top_height), or it fails with IndexError.
- road_wear.outer_edges counts the edge against a pavement as a joint (the pavement is in Sall): kerbed edges never
  reached the drains; they are found on their own (outer_edges(..., Sk=...)).
- Mapillary's map features over the bbox of the AI roads: 89 drains, only about 20 near the map's roads (the bbox
  takes in Italy and the hills): the drains come mostly from the low points of kerbed edges.
- The sidewalks patch moved the pavement tops from roads/surfaces to roads/sidewalks while the road_age patch was
  queued behind it: road_wear would have seen no kerb on the patched zip (crumbled edges along every pavement). A
  step that reads another step's meshes must read them where either order of the finish steps (build or nightly
  patch) leaves them; cancel a queued nightly patch when the zip changes under it (run 39975412003, cancelled).
- Do not point a new material at a game texture the level never used (Italy's t_thin_damaged_edge): game_paths
  does not know where 0.40 keeps it, and a missing texture is a hole in the road. The crumbled edge is drawn here.

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

- Wall tops as a saw (2-3 m teeth, 1-2 m V notches; Magliaso-Pura hairpin at 645,-1005 in michi's video, 2026-10-22):
  walls.wall_geometry looked the photo caps (dati/wall_caps.json, measured every 0.5 m on the outlines of their day)
  up by the exact cm key of each vertex. The outlines are now segmented every 1 m and redrawn, so only one vertex
  in two to six matched, and the top jumped between the cap and the LiDAR crest from one vertex to the next. There
  the survey draws one wall as 2-4 lines 0.2-0.5 m apart and the caps disagree (kerb on the road line, 2.5 m on the
  lines behind, bank 4 m higher): taking the nearest cap only moved the teeth. walls.caps_at takes the highest cap
  within the wall's thickness. Never look up per-vertex data by rounded coordinates when the vertices can change.
  Found by a column check on the released zip (top of each xy column vs its mesh neighbours, ±0.6 m).
- The caps_at fix above did NOT reach the Cantonale: there (24 of 58 points with saw tops in the v3.1 screenshots,
  2026-10-25) the walls are the ROADSIDE walls (rwalls_*, walls.build_roadside from dati/roadside_walls.json), not the
  survey walls. roadside_walls.py smooths a run's height over 8 m but takes its foot station by station (where the DTM
  scan finds the steep rise, 0.25 m steps): the foot jumped 0.3 m every 0.5 m, up to 1.5 m, and the top (foot +
  height) with it. walls.roadside_runs smooths foot and plan line, joins runs < RUN_JOIN apart and drops runs under
  RUN_MIN (the 4-7 m stubs). Before fixing a wall, find WHICH builder made it (shape name: rwalls_ / walls_).
  The survey walls took each top rule per vertex (caps or none, near the road or not, paving or ground under a flush
  top): walls.ring_smooth now smooths the final top along the outline (2 m median + 1 m mean); stubs under CUT_MIN_LEN
  left by the drive-free cut are dropped. Neither builder can run in the cloud (no WORK data): both were checked by
  emulation on the released level (build_roadside with the road mesh as road surface reproduced the released rwalls to
  the mm; ring_smooth applied to the top rings of the released DAEs) and render3d before/after.
- render3d draws grey terrain rising in front of the roadside walls of the Cantonale that the game does not show
  (seen in every view of them, before and after): do not read it as a wall fault.

## Buildings closer to the real ones (edifici_veri.py, v3.1)

- The built shapes shift their uvs by whole tiles (bng.write_dae: `T - floor(T.mean)` when the mean is over 2): the
  openings' uvs are not in 0..1, and looking them up in the atlas found no module at all (6,352 of 6,352 triangles).
  Take the fraction, and give the whole-tile shift back when writing new uvs.
- Cameras placed by rule in front of a facade (in front of its middle, 20 m out, eye height) ended inside other houses,
  roofs and walls in half the views. Put the game camera at the photo's own position and heading (the credits of the
  pack): the views compare with the photos (what michi asked) and are on the road.
- The houses a photo shows are often not the site's own: the yellow corner house of Agno (e03) and the red house of Pura
  (e18) were the next block, and the first round toned the wrong houses (the one in the site red instead of white).
  Check each site's photo against its render before and after (look up the blocks near the camera), then fix the spec.
- `bng.LevelFiles` takes a level folder, not a zip: a patch of the released zip unpacks it, runs the step and puts
  back only the files newer than a marker (`zip -@`), which copies the other entries as they are.
- Wall tones are vertex colours = tone / mean(plaster texture), the same as buildings_mesh: light pinks come out
  greyish mauve in the renders; give pinks a little more saturation than the photo's sunlit wall.

## Races (time trials, races.py)

- Mission files go in `gameplay/missions/<level>/timeTrial/<id>/` beside `levels/`, not inside the level folder:
  a zip made from the level folder alone loses them (package.py adds them).
- The game's mission format was guessed at first (no game files in the cloud, beamng.com blocked): copy the keys of
  a vanilla 0.40 mission instead (Italy `timeTrial/002-Asphalt`, loose files in `<install>/gameplay/missions/`).
- Start positions: the game reads the quaternion as the inverse rotation of +Y onto the road, angle = 90 deg minus
  the bearing. v3.0.40 shipped bearing + 90 deg (turning -Y the usual way), checked only against Italy 002-Asphalt,
  whose start faces due east where both readings agree: in the game the car started across the road at Magliaso.
  Check an orientation convention on a vanilla example that faces north or south, not east or west.
- Plain shortest paths over the AI roads cut through village lanes: weight by drivability**4, and follow the
  measured cantonal road by name, including its split pieces `<name>_<n>` / `<name>_g<n>` (traffic thread).
- The cantonal AI road starts with a hook inside the Magliaso junction, and a start position on the start line
  spawns the car on it: trim turn-backs at the route ends and start the car 15 m before the line.

## Night lights

- The street lamps' lights were PointLights of 14 m radius under a head 8.4 m up, one lamp every 30 m: the road was lit
  only in a pool under each lamp (michi, 2026-10-21, "la strada non si vede"). Italy lights its road lamps with a
  SpotLight aimed down (rotationMatrix [1,0,0, 0,0,-1, 0,1,0]; s_lamp_post_street_single_01 1500 lm, range 30,
  inner/outer 100/140; highway 7500 lm from 12 m), brightness = lumen/5000, nightLight "1", isEnabled false.
  Read Italy's values from `content/levels/italy.zip` on the PC before guessing a light's numbers.
- Calibrating lights live in the game without a build: a GE extension in the user folder
  (`lua/ge/extensions/<name>.lua`), michi pastes one console line, it swaps the lights, takes one screenshot per variant
  (`require("screenshot").createScreenshotTracked`) into `screenshots/` and writes a report; read them through the
  approved user folder. In 0.40 `getObjectsByClass("PointLight")` returned nothing and `getField("nightLight")` did not
  match: list lights with `scenetree.findSubClassObjects("LightBase")` as core_environment does (two wasted rounds).
  A file-polling "run any Lua" hook in the game was refused by the permission check: keep the test fixed.
- In a night view from above, the big white cone was the player car's headlights, not a lamp: turn them off first.
- Spot lumen barely changed the picture (3000 vs 6000 alike); range and cone width did.
- fuel_stations.LIGHT (the canopy lights) is defined but never placed: the v3.0.40 zip has no light but the lamps'.

## Traffic and AI

- Splitter islands stood in the AI lanes (v3.1 visual check, spot 1102: a car set mid lane at the Magliaso
  roundabout exit stood on the island, where the traffic crashed): swissTLM3D draws most roundabout arms and many
  roads with a refuge as ONE line down the middle of the island, the AI road follows it and its two lanes (a quarter
  of the width either side) run along the kerbs or over the island. 85 lane lines crossed 45 of the 124 islands.
  islands.island_lanes (in the islands finish step, which knows the raised islands) splits such a road there into
  two one-way roads, one each side in the middle of the free carriageway, or moves it to the side with room.
  Measured on the released v3.1: 51 lane lines on 23 islands left (mostly the Agno junctions), network pieces and
  dead ends unchanged (34 / 647). Three things it took:
  - _ease must never move a road's end node (np.interp with the end both pinned at 0 and in the measured keys
    took the measured value): the first try cut 19 pieces off the network (pieces 34 -> 53, dead ends +76).
    Check ai_roads.graph_report before/after any change to AI road geometry.
  - two roads meeting end to end in the middle of a long median each converged on their common node: the lanes
    crossed the island in an X. Such ends (exactly two two-way roads, both with an island near) stay open and the
    pieces are joined at the midpoint of their ends.
  - races.route_line chains a named road by "<name>(_g?<n>)*": the pieces past an island are "<name>_i<n>"
    (the way on), "<name>_j<n>" (the other direction, not chained) and "<name>_i<n>_0" (after it); the regex
    now takes _i too. A new piece naming must be checked against every reader of the AI road names.

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

## Ticino a blocchi (beamng/ticino, 2026-10-26)

- A second map in the same repo: level `ticino`, its own mod zip, never `levels/magliaso_pura` (michi: "devono convivere
  le due versioni"). Phase 1 cuts the released v3.1.1 into blocks (blocks.py) instead of building; on the PC all data
  goes on the 6 TB disk (pc_prepare.sh <disk>).
- The scene objects kept in the level (backdrop, landmarks) still pointed at /levels/magliaso_pura/ after the first cut:
  copy_level rewrote the files it copied but write_scene wrote the kept objects as read. Grep the cut level for the old
  level name after any change to blocks.py.
- A coroutine keeps the arguments of its FIRST resume: the yield function made in runJob read the first frame's start
  time forever, so every later call yielded at once and a window took 461 frames (7.7 s) instead of ~17. Read the frame
  start from a table the caller updates (job.t0).
- Writing the 12 MB window .ter in one f:write took ~40 ms (one frame): write it row by row with yields (writeParts).
  The PNG writer also never joins its 800 kB IDAT (CRC computed over the parts).
- `blocks.py --no-far` first deleted the far/ folder with the other outputs (a quick rerun lost the far tiles).
- Unknown until the game test: the terrain materials' *BaseTexSize unit. The pipeline writes metres (12288 = 8192 x 1.5),
  BeamNG.Earth measured samples in game; the window's maps assume samples (zone `base_size_unit`).
- BeamNG.Earth (github.com/TecnaGamer/BeamNG.Earth, MIT, cloned fine from the cloud) has in-game measurements of every
  engine limit the streaming needs (docs/research/2026-10-12-engine-limits-and-worldgen.md): read it before guessing.
- blocks.py hard-links the source level into the output and then wrote info.json over the linked file: the SOURCE
  v3.1.1 info.json got "Streaming test of the Ticino level:" once more per run (seen 4 times). Every write into the
  output goes through blocks.wopen (removes the path first). After a run, `find <src> -newer <zip>` must list nothing.
- michi tests the Ticino mod on the Windows PC DESKTOP-OUPOLOA (2026-10-26, "questo qua è un pc windows usa questo"),
  not on the Linux PC: no Python there, so ticino_test.yml cuts and packs on GitHub (draft release ticino-test) and
  tests/game/run_test.ps1 runs the test (autotest.lua, as the v3.0.40 runner did).
- First in-game look (2026-10-26, DESKTOP-OUPOLOA, 0.40.3): level ticino loads in 9 s, no missing material, streaming
  runs. Hitches: every tile change ended in be:reloadCollision and the physics rebuilt ALL static collision ("Loaded
  Static Collision" 0.3-1.5 s, 7.4 M triangles) once per 384 m; the window swap itself is 0.16-0.2 s. The first jump
  made all ~1,000 far tiles at once (7.8 s: the game converts every new DAE). Now far tiles come a few a frame, a
  deleted collider no longer forces a rebuild, and ticino_stream.setCollision(radius, groupsOff) switches groups (the
  skin is 26 of the 46 M collidable triangles) for measuring. michi drove east past Agno, out of the built zone (the
  airport runway is bare terrain there in v3.1.1 too): "no objects" at the zone edge is not a streaming bug.
- What a collision rebuild costs (console, standing still in ticino, 2026-10-26): the whole static collision 7.12 M
  triangles 3.40 s; without the Forest 1.12 M and STILL 3.40 s (274k tree instances share ~30 meshes: free); only
  the car's tile 156 k, 0.54 s; no streamed object at all 4.8 k, 0.002 s (the terrain costs nothing). The time is
  "Loaded Static Collision" after "Physics collision reloaded" (0.05-0.12 s): about 3 us per unique triangle, skin
  the worst (57 % of the collidable triangles, most of the time). Do not delete the Forest object to test: the game
  log stopped being written after it (the game went on).
- Quick travel into a zone never seen: about 40 s, nearly all "Importing COLLADA" of 551 shapes (the game converts
  each .dae once, cached afterwards) + 4 s of collision.
- Collision cells (collision.py, 2026-10-26): fast_simplification (quadric) on a road mesh left holes (1.2 % of the
  surface samples at 50 % reduction, 4 % at 70 %) and moved edges by up to 0.5 m (the skirts): roads, sidewalks and
  railway stay exact; only the skin (to 7 %), houses, walls and props are simplified. A sim run whose clock is CPU
  time (tests/sim_stream.lua) never let a "150 ms after the swap" wait expire: count such waits in dtReal.
  Collision .cdae with real normals and tangents were 1.1 GB (563 MB zipped); with constant normals 228 MB zipped.
- Laptop run 1 (2026-10-26, DESKTOP-EKDTIGL, 0.40.1, iGPU 512 MB): no crash, no Out of VRAM, load 48 s, peak 9.5 GB
  private, ~10 fps. The car fell through the road during autotest's own reload test (cells radius -1 for 12 s with
  the physics running: no road collision under it) into a yard 1.6 m lower and was stuck for the whole drive. The test
  now pauses the physics and puts the car back. map.findClosestRoad(vec3(x, y, 1000)) found nothing with 20,810 nodes
  in the graph: query near the ground (and the test falls back to the nearest node by hand, noting it).
  colPiece's ffi.cast of the Lua string raised "arithmetic on a string value" for one cell (10 times, the pos not
  advanced): the piece is now copied into an ffi buffer, and any failure turns ffi off for the session.
- Laptop run 2 (2026-10-26): that fix made it worse: `ffi.new('uint16_t[?]')` is an array, and `u + 3 * nv` on it
  raises "bad argument #1 to '__add' (invalid C type)" for EVERY piece (colTris 0, 2,126 failures, no cell had any
  collision; the car fell through the tunnel floor). The fallback never ran: the error came after the pcall'd copy.
  Index the array (u[3 * nv + k]); a failed piece now drops the rest of its cell (the read position is lost). Run any
  decoder change against a real cell file in luajit with stubs before a game test (the ffi and byte paths agree).
  The AI drove this time (2.3 km in 14 min, 9 stops, "moved 30 m on" worked). Every jump put the car at z 0.5: the
  AI map's nodes far from the start had z 0 (the AI DecalRoads clip to the terrain, which exists only in the
  streamed window; the json nodes have their heights). The test now takes the ground under the node and counts the
  z < 1 nodes before and after a map.reset() at each jump; the 3,124 core_trafficSignals "Map node could not be set"
  likely have the same cause. Also logged: material cbv array exhausted (8192 slots) at 113 s, a 16x448 bollard
  texture that is not a power of two (TextureCooker refuses it).
- Laptop run 3 (2026-10-26): collision cells work (colFailed 0, 1.7 M triangles made), no jump fell, the car stands
  on the tunnel floor. map.reset() after the window came gave every AI node within 300 m its height (0 of 59-281 left
  at z < 1), while 14-19 k of the 20,810 stayed at 0: stream.lua now reads the AI map again MAP_RESET_FRAMES after
  every window swap (perf row "mapreset"). A collision cell dropped half made left its pieces in the scene and the
  remade cell registered the same names (56 SimNameDictionary::insert warnings); colTris was a "made" counter, now live.
  createScreenshot2 takes the shot a few frames later: with the camera moved on at once, every tunnel shot showed the
  NEXT pose (and the last two were alike). Wait 2 s after each shot before moving the camera.
- Laptop run 4: that map.reset() froze the game 1.9-2.5 s at EVERY window move (perf rows "mapreset"): never call it
  on the fly. map.lua (0.40, loadJsonDecalMap) takes a DecalRoad's subdivided edges (clipped to the terrain) when
  useSubdivisions is on and edgeCount > 2, else its control points with their own z: blocks.py now writes the ticino
  AI roads with useSubdivisions false and MAP_RESET_FRAMES is nil. The AI left the road twice at Pura (250-290,-890,
  runs 3 and 4, into the wood against a tree): the same place as the known lamp/4 m AI drop of the piano video
  (Known issues), a map fault, not streaming.
- Laptop run 5: useSubdivisions false CRASHED the level load. map.lua (0.40.1) L459 edgeCompare compares `a.lanes <
  b.lanes`; the node reduction (RDP, ~L1985) builds a new edge with NO lanes when it removes a middle node between two
  nodes already linked directly, and compares it with that edge: "attempt to compare nil with string" when posMin/max,
  radii, drivability, oneWay and speedLimit are all equal (two AI roads joining the same two nodes, one with a node in
  between). Control points coincide exactly where subdivided edges differed by mm. The game then reloaded the level by
  itself and crashed in C++ (c0000005). In the ticino roads the ties were the two one-way halves of a road round a
  splitter island (X and X_j1, islands.island_lanes). beamng/ticino/aimap_check.py emulates map.lua's passes from
  the code read on the laptop and blocks.py stops if it finds a crashing compare (resolveT/XJunctions and
  mergeNodesToLines are not emulated).
- Laptop run 6: the first fix, a speed limit of its own per road, crashed the same way: 0.40.1 does NOT read a
  DecalRoad's `speedLimit` from items.level.json (an in-game probe read r.speedLimit nil and getField '' on all 3,451
  roads; vanilla Utah writes none), so createSpeedLimits gave both halves the same value. The emulation had read the
  json value, so it said 0. Emulate only what the game is shown to read. Now blocks.ai_roads gives every road a node
  width of its own (+2e-6 m per road, float32 keeps it), which ends the compare at the radii: 11 crashing compares in
  3 orders before, 0 in 8 after, with the speed emulated as one auto value and the nodes as float32. Not drivability:
  a lower drivability makes the AI give way at the joint. (The probe also read useSubdivisions as nil, yet runs 1-4
  without the key had subdivided z 0 nodes and no crash, and 5-6 with false crashed: the key is read.)
- Laptop run 7: the width offsets loaded (47.9 s, no crash) but the control-point graph did not help: far nodes kept
  z 0 all the same (the control points' z is also clipped where no terrain is loaded) and the AI drove 762 m against
  2,383 m in run 2 (more stops, it hung at joints the subdivided graph had smooth). Reverted: the ticino AI roads are
  written as the source has them (subdivided, no width offsets, aimap_check.py kept as a tool), and stream.lua calls
  map.reset() once at each jump, while the game is paused for the reload (MAP_RESET_ON_JUMP), never on the fly.
  Between jumps the far nodes stay at z 0 (only the window's are right). Also seen: 4,857 core_trafficSignals errors,
  hitches up to 260 ms at jumps. The S tunnel portal showed the lake through two small gaps at the jamb feet: an
  apron (tunnels.APRON, 1.6 m of ballast/asphalt 3 cm under the floor) now runs out in front of each face.
- Laptop run 8: loads (48.7 s), no crash, jumps fine, the reset at a jump reads every node near it (1.8-2.5 s inside
  the paused jump), the jamb gaps are closed. But the apron stood out past the S headwall as a plate 1-1.5 m over the
  lake-side slope: its open edges now go FOOT under the lowest ground beside them. The AI drove only 873 m: in "span"
  mode it turned into a 3.4 m village lane north of the start (630-690,-790..-850), spun its wheels there and looped
  with the "moved 30 m on" helper, never leaving the first window. Not a streaming fault: the cell collision there
  matched the exact meshes on every road cell (0.25 m raster, 0 cells over 3 cm; only the skin moved, up to 0.67 m,
  off the road), the lane is smooth at 14 %. Which way span mode turns is luck: the drive now follows the scripted
  route (16.8 km, Magliaso-Pura-Ponte Tresa-Caslano-Agno) first, then the AI. The autotest's own map.reset at a jump
  doubled stream.lua's (6,553 trafficSignals errors): removed.
- Laptop run 9: load, jumps, cells and the tunnel all fine (the apron skirt closes the S portal; tunnel done). The
  scripted route flipped the car after 155 m: it started inside the Magliaso roundabout, hung there 26 s, then
  scriptai raced the late timeline at 14 m/s (it keeps to the times, not to a speed) and at the bend at 684,-1040 the
  car left the cantonale and fell 2 m on its roof into the lane below. make_route.py now starts on the cantonale,
  weights the path by drivability ** 4, drives at most 40 km/h and slower in bends (A_LAT). The AI drive after it went
  1.16 km west through Pura with 6 short stops. The jump check 1 s after stream.lua's reset log still saw the old
  heights; 5 s later all were right (the reset lands a few frames after its log line).
- Laptop run 10: the slower route (A_LAT, 40 km/h) flipped at the same place, 684,-1040, at 3-7 m/s: not speed. The AI
  road strada_cantonale_i1_0 there lies on the EAST EDGE of the cantonale, and its 7.7-9 m width covers the lane
  tlm_1052 1.2-1.6 m lower beside it: every car on that AI line (scriptai, span AI) goes over the edge. Making the route
  graph directed for one-way roads gave a 33.8 km detour (reverted). New finish step ai_lanes (pipeline/ai_lanes.py, in
  ticino_test.yml after tunnels): every AI node walks the road surfaces across its width, and a step over 0.5 m inside
  it moves the node away and narrows the width (lane 0.3 m from the drop, never under 3 m), spread over 2 nodes each
  side, faded out 6 m from the ends. On v3.1.1: 9 of 3,451 roads, 48 nodes, at most 3.2 m (the cantonale 2.9 m west).
  route.json regenerated from the fixed roads. Not run in the main build yet (only on the Ticino test level).
- Laptop run 11: the ai_lanes fix held (the car stayed on the cantonale at 684,-1040), 2.3 km of route, 6 window moves,
  no fall. Two stops: (1) at 59,-748 the car hit a street lamp standing 2.2 m inside the cantonale's AI width and stood
  40 s: 17 of the 2,108 lamps stood inside an AI width (also the known one at Pura, 287,-892). ai_lanes.lamps_clear moves
  those out to the half width + 0.6 m with their lights, or removes them where the ground there is 0.8 m off (2). A first
  version moved every lamp closer than half width + 0.6 (1,447): the lamps stand 0.3-0.5 m beyond the edge on purpose;
  only lamps INSIDE the width move. (2) the route ran into dead ends and back over the same nodes ((-240,50) and
  (-250,-1000) were places on side roads), and scriptai cannot turn round: it stopped at -259,61. make_route.py now
  makes roads already driven cost 20x, cuts spurs under 120 m and reports longer ones; new places, 19.6 km, no
  turn-round (cos < -0.8) left. Unwinding every A-B-A with no length limit collapsed the route to 7.7 km (whole legs).
- Collision cells as ProceduralMesh (EarthNG's way, michi: "basta che non cambia la grafica"): decoding a piece in Lua
  is the cost, not the file: a 2,500-triangle piece took 7-10 ms in luajit with s:byte, so a frame went over budget.
  ffi.cast of the string to uint16_t* and pieces of 1,200 triangles keep a piece under ~5 ms. The cells hold
  triangles by their centre, so a piece reaches up to ~70 m outside its cell (long road triangles): a range check of
  a cell file must allow that (XY_OFF_CM). Not known until the game test: whether setRenderEnabled exists on
  ProceduralMesh in 0.40 (pcall; the materials are alpha 0 anyway) and whether the winding (clockwise) lets the car
  stand on it.
- Zone builds (zone_build.yml, MAGLIASO_ZONE, 2026-10-27): download_worldcover failed at once on the probe zone ti_1_0
  (Lugano): the window of tile N45E006 rounded to start one cell west of the map's box, c0 = -1, and `out[r0:, -1:...]`
  is an empty slice ("boolean index did not match ... size of axis is 0"). The Malcantone box never touched a tile
  edge. Clamp a pasted window's offsets, never slice with a start that may be negative.
- Next on ti_1_0: network_surface.cantonale_hold -> roadheight.build crashed (NaN bounds): the corridor surfaces are
  cut along the Malcantone Street View route (poses.json main_run), which no other zone touches. With no polygons
  roadheight now saves an empty Surface (distance inf, height nan). Expect more such Malcantone-only data (poses,
  road_profile, photo markings, wall caps): a zone has none of it in reach and every reader must take "nothing".
  The Actions cache saves only when the job succeeds: the zone workflow saves the downloads right after them.
- More Malcantone-only assumptions found on ti_1_0 (2026-10-27), all fixed so the Malcantone build is unchanged:
  stage_roads with no corridor polygons (bb of an empty list); vanilla/carryover read the reference zip under
  levels/<LEVEL_NAME> (the zip's level is always magliaso_pura) and carryover took over the v1.1 route paint and props
  (now none in a zone); the Monte Lema cable car/summit outside the zone's terrain; guardrails_final.json and the
  photo rails (NaN feet outside the zone's DTM: savgol "array must not contain infs or NaNs"): area.in_zone drops
  photo data outside a zone; spawns from poses.json (zone_route picks main roads near the core); races skipped.
- A dense zone is slow on one process: ti_1_0 stages roads 81 min, walls 21, buildings 36, vegetation 20, canopy 28,
  finishing optimize 11, unpaved 17, markings 13, road_wear 12 (cloud container). wintryserver (6 cores) ran the
  stages in 73 min. GitHub stops a job at 6 h: zone_build.yml runs the stages and the finishing steps as two jobs.
  NET_WORKERS forks the network tiles (results added in tile order, same level). MAGLIASO_CHECKPOINT=1 pickles
  (scene, ctx) after every stage (700 MB on ti_1_0) and `build_level.py --reuse-roads --resume` goes on after a crash.
- The cloud container's disk (about 30 GB usable) fills with a zone: the raw swisstopo tiles (data/swissalti3d_05,
  dsm_05, buildings3d) are not read after build_rasters/extract_buildings and can go during a build.
- skimage was missing in the cloud container (vegetation's watershed): pip install scikit-image before a local build.
- wintryserver (michi's Ubuntu server, 6 cores, 14 GB, /mnt/disk8tb): RC sessions work only inside /mnt/disk8tb/ticino.
  Claude Code's auto-mode check refused to run the cloned repo's Python ("Code from External") until michi wrote the
  exact permission in the thread; sudo asks a password (osmium-tool unpacked from the .deb into /mnt/disk8tb/ticino).
  `claude remote-control` in a terminal registers the folder as a device; an RC started inside a running session did not.
- Traffic lights (markings_rules, 2026-10-27): OSM highway=traffic_signals on an arm makes the junction signalled
  (3+ arms): every way in gets a stop line, an instance of a two-phase sequence (axes) and the stock boom
  /art/shapes/objects/s_trafficlight_boom_sn.dae on its kerb side, local +x to the kerb (as BeamNG.Earth places it,
  tested by them in 0.40.3; not yet seen in our level). Controllers and instances share one id count.
- signs_net had `levels/magliaso_pura` written in (KeyError in a zone after 6 min of the signs step): grep the pipeline for
  the old level name, every reader must use LEVEL_NAME.
- wintryserver OOM (2026-10-27, ti_1_0): the finishing step unpaved peaked at 12.95 GB RSS + 2 workers of 1.7 GB, and
  immich/java hold ~3 GB with 3 GB swap: the kernel killed build_level (rc 137, no traceback). PATCH_WORKERS=1 passed
  (633 s). Run the zone finishing steps there with PATCH_WORKERS=1.
