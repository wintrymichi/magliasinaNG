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
| Free camera from Manno north at 33 m/s, 300 s (2026-10-31) | 83.0 fps, 52 frames over 100 ms (terrain moves, bursts, 3 forest changes) |

## Troubleshooting

- **The game loads West Coast USA instead**: an old `levels\ticino\info.json` in the user folder; run the installer
  (it moves user-folder overrides out).
- **Not responding at the first start**: see "Play". `beamng-launcher.log` has the exit code if Windows closed it.
- **Missing textures or grey objects after an update**: run the installer (it clears the level's cache on a new
  base), or delete `<user>\temp\levels\ticino` by hand.
- **Is the streamer running?** `beamng.log` has `ticino` lines (`streaming on`, `settings: ...`, `jump: window at`).
  In the console: `ticino_stream.status()`.

## State and open work (2026-10-31)

Done: all 87 zones in one level, the streamer with wave loading, 64 m collision cells, the helper, settings, the
installer, shapes shipped as .cdae, static streamed objects and bursts (standing still as fast as Italy). Open:

- Driving fast: about 3 frames a second of 50-100 ms while a new area fills in at 120 km/h, the trees fall behind,
  and a long jump (teleport) pauses the game about 10 s.

- **AI map.** The game builds the AI map from the 57,298 AI roads, which take their heights from the terrain: only
  the window has terrain, so outside it the AI nodes sit at height 0, 4,020 of the 4,065 traffic signals find no road
  and AI traffic works only round the spawn; the same roads cost the 12 s first window and the 30 s map read. Fix in
  progress: a precomputed AI map loaded with `map.reset(nodes)` and no AI roads in the scene.
- Floating origin (coordinates reach 75 km from the origin: no jitter seen so far), AI traffic guard at the window edge.

Credits: the terrain swap, ground cover flush, runtime objects, pause and the `.cdae` writer follow BeamNG.Earth
(TecnaGamer, MIT, `mod/THIRD_PARTY.md`). Data: swisstopo, the cadastral survey of Ticino, OpenStreetMap
contributors. Licence of the map: CC BY-NC 4.0, as the rest of the repository.
