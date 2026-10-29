# Ticino for BeamNG.drive

The second map of this repository: all of Canton Ticino (87 zones of 7.7 x 7.7 km, about 62 x 93 km) in one
BeamNG level, `ticino`, streamed around the car. It is built by the same pipeline as the Malcantone map
(`beamng/pipeline`, level `magliaso_pura`) with the same detail: swissALTI3D terrain at 1.5 m, swissBUILDINGS3D
buildings, the survey's roads, walls, pavements, bridges, tunnels, motorways, forest, signs and traffic signals.
The two maps are separate mods and can be installed together: nothing here changes the Malcantone level.

Branch: `ticino`. Status: draft release, not public yet (see "State" at the end).

## Install (Windows)

Needs BeamNG.drive 0.40.x from Steam, about **52 GB** free on the disk of the BeamNG user folder for the mod and
about 15 GB more that the game fills with its cache of the level as you drive, 16 GB of RAM (32 GB recommended) and
a GPU with 8 GB of video memory or more.

1. Download `installer_ticino.zip` from the release and unpack it anywhere.
2. Close BeamNG and double-click **`Install Ticino.bat`**.

The installer (`install/install_ticino.ps1`):

- downloads the 88 zips of the release (`ticino_base_<n>.zip` with the scene and the streaming mod, one
  `ticino_<zone>_<n>.zip` per zone) into `mods`, resumes a broken download where it stopped and checks every zip
  by its sha256 before it goes into `mods` (a zip already there and checked is skipped: an update downloads only
  the zips that changed);
- moves Ticino zips the release no longer has to `ticino_download\old` (or deletes them with `-DeleteOld`);
- moves any user-folder files of the level (`levels\ticino`, `lua\ge\extensions\ticino`, left by tests or older
  versions: they would win over the zips) to `ticino_download\overrides_<date>`;
- clears the game's cache of the level (`temp\levels\ticino`) when the base zip changed;
- turns the Ticino mods back on in `mods\db.json` (BeamNG turns every mod off after a game update);
- installs the streaming helper (`ticino_tools\ticino_helper.exe`), writes `settings\ticino.json` if there is none,
  and puts a **Start Ticino (BeamNG)** shortcut on the desktop.

Options: `-ListOnly` (show what it would do), `-DeleteOld`, `-NoHelper`, `-NoShortcut`, `-KeepCache`,
`-UserFolder <path>` (another BeamNG user folder), `-GameFolder <path>` (BeamNG not in a Steam library),
`-Tag <release>`, `-Uninstall` (removes the zips, the cache, the tools and the shortcut; keeps the settings).
A draft release can only be downloaded with the GitHub CLI logged in (`gh auth login`); a published one needs nothing.

Run the installer again to update. Linux or by hand: put every `ticino_*.zip` of the release into
`<user folder>/mods`, nothing else is needed (the helper runs with `python3 helper/ticino_helper.py`).

## Play

Start with the desktop shortcut (BeamNG goes straight into the map, the helper starts beside it and stops with the
game), or in the game: Freeroam > Ticino. There are spawn points in every zone (villages and towns).

The **first start** after an install mounts about 600,000 new files: the game can show "not responding" for one or
two minutes before the main menu. Wait; it is not a crash. The first time a place is seen the game converts its
shapes and textures (stutters in a new area); the second time they come from its cache. To convert them before
driving, run the warm-up (below, "How it works").

## Settings

`<user folder>\settings\ticino.json` (default `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\settings\ticino.json`), read
when the level starts:

```json
{ "preset": "standard", "helper": true, "diagnostics": false }
```

| Field | Values | What it does |
|---|---|---|
| `preset` | `standard` (default), `light` | `standard` is the level as built and tested. `light` is for PCs with little video memory or a slow CPU: trees shown within 3 tiles (1.2 km) instead of 4, fewer of them at a distance, far ground to 10 tiles instead of 16. The near scene (roads, buildings, collision) stays the same. |
| `helper` | `true` (default), `false` | use the helper process when it runs |
| `diagnostics` | `false` (default), `true` | write `ticino_perf.csv` (every terrain move, timings) and `ticino_frames.csv` (frame times every 5 s) to the user folder |
| `stream`, `objects`, `forest` | objects of fields | advanced: any constant of `stream.lua`, `objects.lua`, `forest.lua` of the same type, e.g. `{"forest": {"RADIUS": 5}}` |
| `level` | object of numbers | advanced: numbers of the level's `stream.json`, e.g. `{"level": {"farRadius": 20}}` |

A file that is not valid JSON is ignored (the log says so). Tables indexed from 0 (`forest.SHARE`) cannot be set from
JSON. `ticino_stream_cfg.json` in the user folder root still overrides everything (tests only).

## How it works

| What | Size | Where in the zips |
|---|---|---|
| Zone (build unit) | 4 x 4 terrain blocks = 7,680 m, built by the full pipeline with an overlap | one `ticino_<zone>_<n>.zip` |
| Terrain block (data unit) | 1,280 x 1,280 samples at 1.5 m = 1,920 m | `blocks/terrain/t_<bx>_<by>.bin` |
| Tile (objects, trees, window step) | 256 samples = 384 m | `tiles/o_<cx>_<cy>.json`, `tiles/t_<cx>_<cy>.trees.json` |
| Terrain window in the game | one TerrainBlock of 2,048 x 2,048 samples (3.07 km) | written to `<user>/temp/ticino/` |
| Base colour of the open ground | 4 samples a pixel, one combined map for the window | `blocks/base/<texture>_<bx>_<by>.rgb` |
| Far ground (outside the window) | a mesh every 12 m per tile, vertex colours, no collision, 16 tiles round the car | `far/f_<cx>_<cy>.cdae` |
| Collision cell | 64 m, the level's own meshes as collision only (roads exact, skin and houses simplified), ProceduralMesh pieces of at most 1,200 triangles per ground type, 3 x 3 cells round the car | `col/c_<i>_<j>.bin` |

The streamer is the GE extension `ticino_stream` (`mod/lua/ge/extensions/ticino/`, loaded by
`mod/scripts/ticino/modScript.lua`; it does nothing outside the level `ticino`):

- **Terrain.** One TerrainBlock follows the car. The window moves when the car's tile leaves the places 2..5 of its
  8, by 4 tiles, so a straight drive moves it about every 1.5 km. The next window (`.ter` and base map) is put
  together from the blocks over 15-30 frames (4 ms of Lua a frame, `terwin.lua`, `png.lua`), or by the helper on
  another core, and swapped in by `terrainFile` + `postApply` (the way BeamNG.Earth moves its block).
- **Objects.** Each object is shown within its group's radius in tiles (street props 2, roads and walls 5,
  buildings 6). They come in a wave: the tiles next to the car first, the far ones after, at most one heavy object
  a frame (`objects.lua`). Heavy shapes are cut into 192 m pieces at build time so a piece is cheap to make.
- **Collision.** `be:reloadCollision` costs about 0.15 us a ProceduralMesh triangle, so the drawn shapes do not collide;
  the 3 x 3 collision cells of 64 m round the car do, with the right ground type for the tyres. Small street clutter
  never collides. No rebuild runs within 3 frames and 150 ms of a terrain swap.
- **Forest.** Every tile's trees are made within 4 tiles of the car, all of them near, a share far (`forest.lua`).
- **Jumps.** A spawn or a teleport far away pauses the game, makes the window and the near objects at once, and goes
  on.
- **Warm-up.** Optional, from the console inside the level: `extensions.load('ticino_warmup')` loads once every shape
  of the zones within 3 km and cooks the sign textures, so the game writes its cache now instead of stuttering the
  first time it sees them (about 15 min a region; drive elsewhere and run it again there).
- **Helper.** `helper/ticino_helper.py` (or `ticino_helper.exe`) makes the terrain windows with numpy, byte for byte
  what the Lua makes (`tests/test_helper.py`), and keeps the 8 the next move can need ready. It talks to the mod only
  through files in `<user>/temp/ticino/helper/` (`ticino/helper.lua`). Without it the Lua makes them, as before.
  Only data can be made outside the game: everything in the scene (terrain swap, objects, forest, collision, the AI
  map) has to run on the game's own thread.

## Build

All builds run on GitHub Actions (the cloud sessions cannot reach swisstopo), on the branch `ticino`:

| Workflow | Started by (push of) | Does |
|---|---|---|
| `zone_build.yml` | `zone_stamp.txt` (zones in `zone_list.txt`) | the full pipeline for each zone (`MAGLIASO_ZONE`), zips on the draft `ticino-zones` |
| `ticino_all.yml` | `all_stamp.txt` (zones in `all_list.txt`; `[all base]` in the commit message: base only) | per zone `region_slice.py` -> `ticino_<zone>_<n>.zip`, then `region_base.py` -> `ticino_base_<n>.zip` (scene, welded AI roads, signals, at most 6,000 parking spots, materials, info.json with every spawn, stream.json), on the draft `ticino-all` |
| `ticino_tools.yml` | `install/**`, `helper/**`, `tools_release.txt` | `helper_ticino.zip` (exe) and `installer_ticino.zip` on the release named in `tools_release.txt` |
| `ticino_helper.yml` | `helper/**` | test pack of the helper with the Lua as user-folder override, draft `ticino-helper` |

The zone grid and what every zone shares (terrain heights, layers, forest and ground types) are fixed in
`zones/ticino_plan.json` (`region_plan.py`; lists append only), so the slice jobs never need each other.

Files: `zones.py` (the grid), `region_plan.py`, `region_slice.py`, `region_base.py`, `region_net.py` (AI road
welding across zone edges, signals, sites), `collision.py`, `cdae.py` (the `.cdae` writer, from BeamNG.Earth),
`zipremote.py` (zips read by HTTP range), `blocks.py`, `region.py`, `pack_region.py` (the older one-job region),
`helper/`, `install/`, `mod/`, `tests/` (`sim_stream.lua`: the mod driven outside the game with the game API stubbed,
`python tests/luajit.py tests/sim_stream.lua <level folder> <seconds>`; `test_helper.py`, `test_cdae.py`,
`test_region_net.py`, `wave_order.lua`).

## Measured

On michi's PC (RTX 4070, 2560 x 1440, BeamNG 0.40.3-0.40.4), October 2026:

| Run | Result |
|---|---|
| Lugano, free camera at 20 m/s, 64 m collision cells | collision rebuilds 25 ms (max 35), terrain move 0.23 s every ~1.5 km |
| Motorway Lamone-Maroggia, 33 m/s | 8 of 65 five-second spans with a frame over 100 ms, all of them terrain moves |
| AI car round Magliaso, up to 166 km/h | 1 of 61 spans with a frame over 100 ms |
| All Ticino, after the spawn | about 1 min of stutter (12 s first window, 28-30 s AI map), then 100 fps |

## Troubleshooting

- **The game loads West Coast USA instead**: an old `levels\ticino\info.json` in the user folder; run the installer
  (it moves user-folder overrides out).
- **Not responding at the first start**: see "Play". `beamng-launcher.log` has the exit code if Windows closed it.
- **Missing textures or grey objects after an update**: run the installer (it clears the level's cache on a new
  base), or delete `<user>\temp\levels\ticino` by hand.
- **Is the streamer running?** `beamng.log` has `ticino` lines (`streaming on`, `settings: ...`, `jump: window at`).
  In the console: `ticino_stream.status()`.

## Ticino server (optional, 2026-10-29)

`server/ticino_server.py` keeps the whole map beside the game: only the base pack (`ticino_base_*.zip`, 270 MB: the
level, materials, textures, Lua) is in `<user>/mods`; the 87 zone packs (51.6 GB) stay in the server's data folder
(any disk). While the game runs, the server puts the files of the tiles round the car into
`<user>/temp/ticino/srv/` (objects and trees files, collision cells, far ground, and every level shape converted to
`.cdae` by `dae2cdae.py`) a few rings ahead of the car, lists the finished tiles in
`<user>/temp/ticino/helper/ready.json`, deletes the farthest tiles when the cache is over `--cache-gb`, and makes the
terrain windows as the helper does (it is the helper with more to do). `ticino/files.lua` in the mod reads from there
and skips a tile until it is listed; at a jump it waits (`SERVE_WAIT_MS`) for the rings round the car.

Why: with the packs in mods the game mounts all of them at every start (596,326 files: 75-81 s before the menu in
michi's beamng.log of 2026-10-29), and the first time it meets a shape it parses the Collada file (195 GB of XML for
all of Ticino) and writes its own `.cdae` cache (12 GB in `temp/levels/ticino` after four zones). With the server the
game mounts one pack and loads every shape as `.cdae`.

    python server/ticino_server.py download [--zones ti_0_0 ...]   the release's packs: zones to the data folder, base to mods
    python server/ticino_server.py adopt                           move the zone packs already in mods to the data folder
    python server/ticino_server.py                                 run it (before or with the game), Ctrl+C stops and cleans
    python server/ticino_server.py once <x> <y> --radius 7         the tiles round a point, timed

Settings on the command line or in `ticino_server.json` beside it (`user`, `data`, `cacheGB`, `workers`, `dae`, `tag`,
`zones`). Without the server and with the packs in mods nothing changes (simulator: the same scene, object for object).

Checked in the cloud (zone ti_0_0, 4 cores): 225 near tiles (radius 7) in 80 s with the conversion (70 ms a shape),
33 s without; the simulator at 120 km/h for 100 s with the server running beside it ended with the same scene as with
the packs (5,175 objects, 1,155 far tiles, the same collision triangles), 28 tiles late while driving (the start
aside) on the shared 4-core container. `dae2cdae.py` against 7 shapes the game compiled itself (michi's cache): the
same vertices, triangles, normals, colours, materials and detail levels; the node tree (base00/start01) is left out,
texture coordinates differ in the last bit of a float. Not checked in the game yet: the start time with the base pack
alone, files written under temp while the game runs (the game's file watcher), our `.cdae` shapes with detail levels.

## State and open work (2026-10-29)

Done: all 87 zones in one level, the streamer with wave loading, 64 m collision cells, the helper, settings, the
installer. Open, each in its own thread:

- **AI map.** The game builds the AI map from the 57,298 AI roads, which take their heights from the terrain: only
  the window has terrain, so outside it the AI nodes sit at height 0, 4,020 of the 4,065 traffic signals find no road
  and AI traffic works only round the spawn; the same roads cost the 12 s first window and the 30 s map read. Fix in
  progress: a precomputed AI map loaded with `map.reset(nodes)` and no AI roads in the scene.
- **Shapes converted on first sight.** 13,707 `.dae` files are imported by the game the first time they are seen.
  Fix in progress: ship them already converted.
- Floating origin (coordinates reach 75 km from the origin: no jitter seen so far), AI traffic guard at the window edge.

Credits: the terrain swap, ground cover flush, runtime objects, pause and the `.cdae` writer follow BeamNG.Earth
(TecnaGamer, MIT, `mod/THIRD_PARTY.md`). Data: swisstopo, the cadastral survey of Ticino, OpenStreetMap
contributors. Licence of the map: CC BY-NC 4.0, as the rest of the repository.
