# Ticino for BeamNG.drive

The second map of this repository: all of Canton Ticino (87 zones of 7.7 x 7.7 km, about 62 x 93 km) in one
BeamNG level, `ticino`, streamed around the car. It is built by the same pipeline as the Malcantone map
(`beamng/pipeline`, level `magliaso_pura`) with the same detail: swissALTI3D terrain at 1.5 m, swissBUILDINGS3D
buildings, the survey's roads, walls, pavements, bridges, tunnels, motorways, forest, signs and traffic signals.
The two maps are separate mods and can be installed together: nothing here changes the Malcantone level.

Branch: `ticino`. Status: public pre-release `ticino-v1` since 2026-10-31 (the builds stay on drafts until copied there,
`ticino_publish.yml`; see "State" at the end).

## Install (Windows)

Needs BeamNG.drive 0.40.x from Steam, about **52 GB** free on the disk of the BeamNG user folder for the mod and
about 15 GB more that the game fills with its cache of the level as you drive, 16 GB of RAM (32 GB recommended) and
a GPU with 8 GB of video memory or more.

1. Download `installer_ticino.zip` from the release and unpack it anywhere.
2. Close BeamNG and double-click **`Install Ticino.bat`**.

The installer (`install/install_ticino.ps1`):

- downloads the zips of the release (90 in October 2026: `ticino_base_<n>.zip` with the scene and the streaming mod, one
  `ticino_<zone>_<n>.zip` per zone) into `mods`, resumes a broken download where it stopped and checks every zip
  by its sha256 before it goes into `mods` (a zip already there and checked is skipped: an update downloads only
  the zips that changed);
- moves Ticino zips the release no longer has to `ticino_download\old` (or deletes them with `-DeleteOld`); a zip
  of a zone the release has no zip of at all (a release still being uploaded) is kept, with a warning;
- moves any user-folder files of the level (`levels\ticino`, `lua\ge\extensions\ticino`, left by tests or older
  versions: they would win over the zips) to `ticino_download\overrides_<date>`;
- clears the game's cache of the level (`temp\levels\ticino`) when the base zip changed;
- turns the Ticino mods back on in `mods\db.json` (BeamNG turns every mod off after a game update);
- installs the streaming helper (`ticino_tools\ticino_helper.exe`), or in server mode the Ticino server
  (`ticino_tools\ticino_server.exe`), writes `settings\ticino.json` if there is none, and puts a
  **Start Ticino (BeamNG)** shortcut on the desktop;
- in **server mode** (the default when the release has the server, see "Ticino server" below) puts only the base zip
  into `mods` and the zone zips into `<user folder>\ticino_data`: the game starts in seconds instead of mounting
  the zones for a minute and a half. Zips already in the other folder are moved, not downloaded again (a rename on
  the same disk; a zip held open by another program is left where it is and reported).

Options: `-Mode auto|server|packs`, `-DataFolder <path>` (server mode: where the zones go), `-ListOnly` (show what
it would do), `-DeleteOld`, `-NoHelper`, `-NoShortcut`, `-KeepCache`,
`-UserFolder <path>` (another BeamNG user folder), `-GameFolder <path>` (BeamNG not in a Steam library),
`-Tag <release>`, `-Uninstall` (removes the zips, the cache, the tools and the shortcut; keeps the settings).
A draft release can only be downloaded with the GitHub CLI logged in (`gh auth login`); a published one needs nothing.

Run the installer again to update. Linux or by hand: put every `ticino_*.zip` of the release into
`<user folder>/mods`, nothing else is needed (the helper runs with `python3 helper/ticino_helper.py`).

## Ticino Server app (Windows)

`TicinoServer.exe` (`gui/`, `app_ticino.zip` on the release) is the map's Windows app, in English: one self-contained exe
(.NET 10, WPF with the Fluent theme of Windows 11), nothing to install. It runs the server mode (the zone packs outside `mods`,
see "Ticino server" below), or the packs mode of an install that has every zip in `mods`, and keeps everything up to
date from the GitHub release (the public pre-release `ticino-v1` by default; a draft needs `gh auth login`):

| Page | What it does |
|---|---|
| Home | server state (tiles ready, cache, shapes converted, where the car is), **Play** (server + BeamNG straight into the map; in packs mode BeamNG and the helper, as Start Ticino), the game and user folders, warnings (zones still in `mods`, with **Move** to the packs folder, which turns packs mode into server mode; a base pack without the server's Lua) |
| Graphics | quality Low / Medium / High / Custom and the draw distance of trees (`forest.RADIUS`), far ground (`level.farRadius`), buildings, roads and walls, details (`objects.GROUP_R`, by path prefix), helper, bursts, diagnostics: written to `settings\ticino.json` only where they differ from the mod's own values, kept fields it does not know |
| Downloads | the release (tag), the data folder (proposed as `<user>\ticino_data` like the installer when that disk has room, else the drive with the most free space; a new one moves the zips), resumable downloads (`<data>\.download\*.part`, in packs mode `<user>\ticino_download\app`, 3 at a time) checked by sha256, automatic check at start and every 6 h, automatic download (off by default); a zone counts in the data folder or in `mods`, and a zip the installer has hashed (`ticino_download\checked.json`) is not hashed again; a downloaded zip (`*.ready`) goes into place only while the server and the game are closed (they keep the zips open), old zips are deleted or moved to `<data>\old` (packs mode: `ticino_download\old`) |
| Server | cache size, conversion processes, terrain windows ahead, `.cdae`, start with Play / stop with the game / start with the app, the server's log; removes a leftover copy of the server's test Lua from the user folder |

The zone packs go to the data folder, the base pack to `mods`. Of `server_ticino.zip` only `ticino_server.exe` is
installed (its `lua` folder is the server's test override): into `<user>\ticino_tools` when the installer has set up the
user folder, else `%LOCALAPPDATA%\TicinoServer\server` (a `ticino_server.exe` beside the app wins). The app stops the
server with Ctrl+C sent to its hidden console, so the server removes its files from the user folder as when stopped by hand.

With the installer (server mode) the app and **Start Ticino** share one setup: at its first start the app takes the
data folder, release and game folder from `ticino_tools\install.json`; every change of its settings goes into
`ticino_tools\ticino_server.json` (user, data, tag, cacheGB, workers, dae; other keys kept) and the data folder into
`install.json`, so the shortcut's server and the next installer run use the same zips. A `ticino_server` process the app
did not start (the shortcut's, with `--game-pid`) is shown as running and never started twice; the shortcut in turn
skips its server when one runs. Before the app starts the server it stops a running streaming helper (Ctrl+C).
Its own settings and log: `%LOCALAPPDATA%\TicinoServer`. Built by `ticino_gui.yml` (draft `ticino-app`, with
screenshots of every page in both themes from `TicinoServer.exe --screenshots <folder>`).

## Play

Start with the desktop shortcut (BeamNG goes straight into the map, the server or the helper starts beside it and
stops with the game), or in the game: Freeroam > Ticino. In server mode the map needs the server: start it with the
shortcut (or the Ticino app), not the game alone. There are spawn points in every zone (villages and towns).

In packs mode the **first start** after an install mounts about 600,000 new files: the game can show "not responding" for one or
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
| `dynamicObjects` | `false` (default), `true` | create the streamed objects dynamic, as BeamNG.Earth does: costs about 5x the frame time standing in a town (each one is drawn into every shadow cascade); for tests only |

Advanced fields that were measured on the PC (October 2026), with their defaults:

| Field | Default | What it does |
|---|---|---|
| `forest.BLOCK` | 3 | the trees of 3 x 3 tiles share one Forest and change in one frame: each frame that changes a Forest costs the engine ~200 ms whatever it adds, so fewer, bigger changes (1: one Forest a tile, 4x more such frames in a drive) |
| `forest.HYST` | 1 | a tile keeps its trees until one ring beyond where they belong (no change on every ring crossed) |
| `forest.RADIUS` | 4 | tiles (384 m) round the car with trees |
| `stream.BURST_EVERY_MS`, `stream.BURST_MS` | 1000, 20 | objects, trees and far ground come in bursts of 20 ms once a second (every frame that changes the scene costs the engine, so few small changes beat many) |
| `stream.BURST_DEL_MS` | 4 | of each burst, for removing the objects the car left behind |
| `stream.BURST_EVERY_SLOW_MS`, `stream.SLOW_MPS` | 200, 4 | a burst every 200 ms while the car is slower than 4 m/s (a new place fills in ~2 min) |
| `stream.BURST_QUEUE_REF` | 300 | more than this many objects waiting shortens the time between bursts (down to 200 ms) |

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
| `ticino_gui.yml` | `gui/**` | `TicinoServer.exe` (the Windows app) with screenshots on the draft `ticino-app`; on `ticino` also `app_ticino.zip` on the tools release |
| `ticino_helper.yml` | `helper/**` | test pack of the helper with the Lua as user-folder override, draft `ticino-helper` |

The zone grid and what every zone shares (terrain heights, layers, forest and ground types) are fixed in
`zones/ticino_plan.json` (`region_plan.py`; lists append only), so the slice jobs never need each other.

Files: `zones.py` (the grid), `region_plan.py`, `region_slice.py`, `region_base.py`, `region_net.py` (AI road
welding across zone edges, signals, sites), `collision.py`, `cdae.py` (the `.cdae` writer, from BeamNG.Earth),
`dae2cdae.py` (every zone shape compiled to `.cdae`, see "Shapes shipped compiled"),
`zipremote.py` (zips read by HTTP range), `blocks.py`, `region.py`, `pack_region.py` (the older one-job region),
`helper/`, `install/`, `mod/`, `tests/` (`sim_stream.lua`: the mod driven outside the game with the game API stubbed,
`python tests/luajit.py tests/sim_stream.lua <level folder> <seconds>`; `test_helper.py`, `test_cdae.py`,
`test_region_net.py`, `test_dae2cdae.py`, `shape_file.lua`, `wave_order.lua`).

## Shapes shipped compiled (.cdae, 2026-10-29)

The game imports a Collada `.dae` the first time it shows it (about 0.1 s, the biggest up to 46 s) and keeps a
compiled copy in `<user>/temp/.../*.cdae`. With 13,707 `.dae` (27 GB of XML) in the zones that was 30 s of stutter in
every new zone, or a warm-up of 968 s for one region (HANDOFF of 2026-10-28, point 3). Now `region_slice.py` compiles
every shape of a zone with `dae2cdae.py` after the collision cells have read them, and ships only the `.cdae`; the
base compiles the shared shapes and points the scene at the slices' `.cdae`. The game loads a `.cdae` as it loads its
own cache: no import, no warm-up (`warmup/<zone>.json` lists only what is left as `.dae`: the game's own props).

- What is compiled: the shapes `bng.write_dae` writes (one node per detail level `<name>_a<size>`, one triangle list per
  material, normals, uvs, vertex colours): all the zones' shapes. Left as `.dae`: forest shapes (`managedItemData.json`)
  and shapes with prebaked imposters beside them (`x.dae.imposter.dds`), anything else the parser does not know.
- Same picture: the same triangles, detail levels and sizes, materials, normals, uvs and colours (`tests/test_dae2cdae.py`
  on a whole zone: 709 of 709 identical), laid out as the game lays out its own cache (`cdae.py`). Against 33 `.cdae`
  the game itself wrote (`--golden`): identical positions, normals, colours and triangles; tangents differ on 2.5 % of
  the vertices, all where the uvs are degenerate (no texture gradient to follow).
- Smaller: zone ti_0_8, 396 MB of `.dae` -> 190 MB of `.cdae` (in the zip 74 -> 86 MB: binary floats compress less).
  709 shapes in 8 s on 4 cores.
- Mixed installs: `objects.lua` takes the `.cdae` when it is there and the `.dae` when a tile names a `.cdae` that is not
  installed (an older zone zip beside a newer base).
- By hand: `python dae2cdae.py <level folder>` (or `--one in.dae out.cdae`).

## Measured

On michi's PC (RTX 4070, 2560 x 1440, BeamNG 0.40.3-0.40.4), October 2026:

| Run | Result |
|---|---|
| Lugano, free camera at 20 m/s, 64 m collision cells | collision rebuilds 25 ms (max 35), terrain move 0.23 s every ~1.5 km |
| Motorway Lamone-Maroggia, 33 m/s | 8 of 65 five-second spans with a frame over 100 ms, all of them terrain moves |
| AI car round Magliaso, up to 166 km/h | 1 of 61 spans with a frame over 100 ms |
| All Ticino, after the spawn | about 1 min of stutter (12 s first window, 28-30 s AI map), then 100 fps |
| Lugano standing still, fresh install, empty cache (2026-10-31) | queues empty after ~2 min, then 84.4 fps (1 % low 60, worst frame 17 ms); Italy at the same settings 81.0 |
| Free camera from Manno north at 33 m/s, 300 s (2026-10-31, 83fabe4) | 94.2 fps, 87 frames over 50 ms, 25 over 100 ms (terrain moves, a few forest changes and heavy objects) |

## Troubleshooting

- **The game loads West Coast USA instead**: an old `levels\ticino\info.json` in the user folder; run the installer
  (it moves user-folder overrides out).
- **Not responding at the first start**: see "Play". `beamng-launcher.log` has the exit code if Windows closed it.
- **Missing textures or grey objects after an update**: run the installer (it clears the level's cache on a new
  base), or delete `<user>\temp\levels\ticino` by hand.
- **Is the streamer running?** `beamng.log` has `ticino` lines (`streaming on`, `settings: ...`, `jump: window at`).
  In the console: `ticino_stream.status()`.

## Ticino server (server mode)

In server mode only the base pack (`ticino_base_*.zip`, 270 MB: the level, materials, textures, Lua) is in
`<user>/mods`; the 87 zone packs (51.6 GB) stay in a data folder (`<user>\ticino_data` by default). While the game
runs, `ticino_server.exe` (`server/ticino_server.py`) puts the files of the tiles round the car into
`<user>/temp/ticino/srv/` (objects and trees files, collision cells, far ground, and every level shape converted to
`.cdae` by `dae2cdae.py`) a few rings ahead of the car, lists the finished tiles in
`<user>/temp/ticino/helper/ready.json`, deletes the farthest tiles when the cache is over `cacheGB`, and makes the
terrain windows as the helper does (it replaces the helper). `ticino/files.lua` in the mod reads from there and skips
a tile until it is listed; tiles that come late are asked for again in groups, and at a jump the mod waits
(`SERVE_WAIT_MS`) for the rings round the car.

Why: with the packs in mods the game mounts all of them at every start (596,326 files: about 85 s before the menu),
and the first time it meets a shape it parses the Collada file and writes its own `.cdae` cache. With the server the
game mounts one pack and loads every shape as `.cdae`.

Measured on DESKTOP-OUPOLOA (0.40.4, 2026-10-31, RTX 4070):

| | packs in mods | server |
|---|---|---|
| game start (mods mounted) | ~85 s | 4 s |
| Lugano standing still, settled | 84.4 fps, 1% low 60.1 | 79.6 fps, 1% low 64.8 |
| flight at 120 km/h, 5 min | 94.2 fps, 25 frames > 100 ms | 93.5 fps, 15 frames > 100 ms |

The installer sets it up (`-Mode auto`, the default when the release has `server_ticino.zip` and a base that can be
served): zones into the data folder, `ticino_tools\ticino_server.exe` with `ticino_tools\ticino_server.json`
(`user`, `data`, `tag`, and optionally `cacheGB`, `workers`, `dae`), and the shortcut starts the server with
`--game-pid`, so it stops and deletes its files when the game ends. If a server is already running (for example
from the Ticino app), the shortcut does not start another one. By hand:

    ticino_server.exe [--user <BeamNG user folder>] [--data <folder>] [--game-pid <pid>]   run (Ctrl+C stops and cleans)
    ticino_server.exe download [--tag ticino-all] [--zones ti_0_0 ...]   the release's packs: zones to data, base to mods
    ticino_server.exe adopt     move the zone packs already in mods to the data folder (nothing moves while one is open)
    python server/ticino_server.py ...   the same from the repository (Linux; numpy needed)

Without the server and with the packs in mods nothing changes (packs mode, `-Mode packs`). A base pack without the
server Lua (`lua/ge/extensions/ticino/files.lua`) cannot be served: the installer then falls back to packs mode.

## State and open work (2026-10-31)

Done: all 87 zones in one level, the streamer with wave loading, 64 m collision cells, the helper, settings, the
installer, shapes shipped as .cdae, static streamed objects and bursts (standing still as fast as Italy). Open:

- Driving fast: about 25 frames over 100 ms in 5 minutes at 120 km/h (terrain moves every ~1.5 km, a few forest
  changes and heavy objects), and a long jump (teleport) pauses the game about 10 s.

- **AI map.** The game builds the AI map from the 57,298 AI roads, which take their heights from the terrain: only
  the window has terrain, so outside it the AI nodes sit at height 0, 4,020 of the 4,065 traffic signals find no road
  and AI traffic works only round the spawn; the same roads cost the 12 s first window and the 30 s map read. Fix in
  progress: a precomputed AI map loaded with `map.reset(nodes)` and no AI roads in the scene.
- Floating origin (coordinates reach 75 km from the origin: no jitter seen so far), AI traffic guard at the window edge.

Credits: the terrain swap, ground cover flush, runtime objects, pause and the `.cdae` writer follow BeamNG.Earth
(TecnaGamer, MIT, `mod/THIRD_PARTY.md`). Data: swisstopo, the cadastral survey of Ticino, OpenStreetMap
contributors. Licence of the map: CC BY-NC 4.0, as the rest of the repository.
