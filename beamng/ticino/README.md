# Ticino a blocchi

The second map of this repository: all of Canton Ticino, streamed around the car in terrain blocks. It lives beside
the Malcantone map (`levels/magliaso_pura`, built by `beamng/pipeline`) and changes nothing of it: its own level
(`levels/ticino`), its own mod zip, its own release tags (`ticino-v0.x`). The two mods can be installed together.

Plan: the doc "Piano: Ticino a blocchi di terreno da 4 km2" (2026-10-26). Phase 1 here: the Malcantone of v3.1.1,
cut into blocks and streamed, must look and drive like v3.1.1.

## How it works

| What | Size | Where |
|---|---|---|
| Terrain block (data and build unit) | 1,280 x 1,280 samples at 1.5 m = 1,920 m (3.7 km2) | `blocks/terrain/t_<bx>_<by>.bin` |
| Tile (objects, window step) | 256 samples = 384 m | `tiles/o_<cx>_<cy>.json` |
| Terrain window in the game | one TerrainBlock of 2,048 x 2,048 samples (3.07 km) | written to `<user>/temp/ticino/` |
| Base colour of the open ground | 4 samples a pixel (6 m), 512 px over the window | `blocks/base/<texture>_<bx>_<by>.rgb` |
| Far ground (outside the window) | a mesh every 12 m per tile, vertex colours, no collision | `far/f_<cx>_<cy>.cdae` |
| Collision cell | 128 m, the level's own meshes as collision only (roads exact, skin and houses simplified), pieces of at most 1,200 triangles per ground type, made in the game as ProceduralMesh that is not drawn | `col/c_<i>_<j>.bin`, `col/col.materials.json` |

- The window keeps the car's tile the 4th or 5th of its 8, so the car is always at least 1,152 m from its edge. When
  the car crosses a tile, the next window is written over about 15-20 frames (4 ms of Lua a frame) and swapped in by
  `terrainFile` + `postApply`, the way BeamNG.Earth moves its block (92 ms for 2048^2 measured there).
- Objects are shown within a radius per group (`zones/malcantone.json`: street props 2 tiles, roads and walls 5,
  buildings 6). Every `be:reloadCollision` rebuilds all collision, at about 3 us per unique triangle (in game: the
  3 x 3 tiles round the car, 1.12 M triangles, froze the physics 3.4 s at every tile). So the level's own shapes do
  not collide with what is drawn: `collision.py` puts their triangles, welded, the terrain skin cut to 7 % and the
  houses to 40 % (roads, sidewalks and railway exact), into collision cells of 128 m (a small binary file each), made in
  the game as ProceduralMesh pieces that are not drawn, a piece a frame (EarthNG measured a ProceduralMesh at 0.27 ms
  per 1,000 triangles in a rebuild, ten times less than our shapes), one material per ground type so the tyres feel
  asphalt, gravel or grass as before; only the 3 x 3 cells round the car collide (`col_radius`; `ticino_stream.setColRadius(r)` in the console). The game's own props (lamps,
  poles) are instanced and keep their own collision within `collision_radius` tiles. No rebuild runs within 3
  frames and 150 ms of a terrain swap (BeamNG.Earth: a car fell through the block taken before its heights).
- The forest, ground cover, water planes, AI roads, spawn points, sky and sounds stay in the level as today.
- A spawn or teleport far away is a jump: the game pauses, the window and the near objects are made at once, then it
  goes on.

## Files

- `blocks.py`: cuts a built level (the released zip unpacked) into the files above, plus the level `ticino` with the
  rest of the scene. Nothing is rebuilt: the window holds the source terrain's own samples.
- `package.py`: the mod zip (or an unpacked folder).
- `pc_prepare.sh <disk>`: on the Linux PC, all of the above on the data disk.
- `mod/lua/ge/extensions/ticino/`: `stream.lua` (the extension `ticino_stream`), `terwin.lua` (window and base maps
  from the blocks), `png.lua`, `objects.lua`. `mod/scripts/ticino/modScript.lua` keeps the extension loaded.
- `collision.py`: the collision cells (needs `fast_simplification`); `cdae.py`: the far ground as `.cdae` (writer from BeamNG.Earth).
- `dae2cdae.py`: every shape of the zones compiled to `.cdae` at build time (see "Shapes shipped compiled").
- `tests/test_cdae.py` (the writer against shapes the game compiled), `tests/test_dae2cdae.py` (compiled shapes read
  back against their `.dae`, and against the game's own cache files with `--golden`), `tests/shape_file.lua`, `tests/check_blocks.py`, `tests/test_lua.py` (needs `luajit`), `tests/sim_stream.lua` (the mod driven at 120 km/h
  outside the game, with the game API stubbed).

## Checked in the cloud (2026-10-26, v3.1.1 zip)

- `blocks.py` on the released level: 49 blocks, 22,821 objects in 467 tiles, 1,024 far tiles, 37 s.
- 16 windows (corners, edges, random) put together from the blocks: every sample on the source terrain identical
  (heights and layers). The Lua window is byte-identical to the Python one; its base PNGs decode to the block maps.
- Lua cost (LuaJIT, container CPU): window .ter about 50 ms, 7 base PNGs about 45 ms, spread over about 17 frames.
- Simulated drive, 8 km at 120 km/h: a window move every 320 m, worst Lua frame about 20 ms (reading a new tile's
  JSON with the test's slow stub decoder).

Not checked (needs the game): everything in the next section.

## Phase 0 test on the PC (what to measure)

Game closed while preparing; 30 fps cap except where FPS is measured; remove the test files at the end.

1. `bash pc_prepare.sh /mnt/<6TB disk>` (about 15 min with the download).
2. Put `ticino_test.zip` in `mods/`, start the level `ticino` (`-level ticino/main.level.json`), check the game log for
   `ticino` lines and errors (`ticino_stream`, missing materials, `Failed to load`).
3. At the spawn: does the terrain have its colours, does grass grow, are buildings and roads where they were in v3.1.1
   (rotated props facing the right way: the quaternion convention is BeamNG.Earth's, not tested on our objects).
4. Drive 5-10 km on the Cantonale at 80-120 km/h, then the AI drives (scenario: the same route as the v3.1.1 test).
   `<user>/ticino_perf.csv` logs every window move and tile change: build ms, swap ms, grass flush ms, worst frame
   after it, collision rebuild ms, objects in the scene. Pass: no fall through the ground, swap frame under 150 ms.
5. Load time, RAM and VRAM peak against v3.1.1 (152 s, 20.0 GB, 6.5 GB).
6. Open questions to answer there:
   - base colour size unit: the window's maps assume samples (BeamNG.Earth). If the open-ground colours look 1.5 x
     too large or shifted against v3.1.1, set `base_size_unit` to `metres` in the zone and cut again;
   - `io.open(path, 'wb')` into the user folder from GE Lua (the window files): if it fails the log says
     "window files failed";
   - the 3,451 AI DecalRoads re-clip on every terrain change (BeamNG.Earth: ~37 us each, ~130 ms here): compare a move
     before and after `ticino_stream.dropAIRoads()` in the console;
   - first use of a shape converts its DAE in the game (the cut-slope tiles are 3 MB each): hitches the first time a
     tile is seen, none the second time?
   - AI traffic cars that drive out of the window have no ground (no guard yet).

After the test: remove `mods/ticino_test.zip`, `<user>/temp/ticino/`, `<user>/ticino_perf.csv` (copy it off first).

## Helper process (optional, 2026-10-29)

`helper/ticino_helper.py` (or `ticino_helper.exe`, built by `.github/workflows/ticino_helper.yml` into the draft
release `ticino-helper`) runs beside the game and puts the terrain window together with numpy on another core: the
2048 x 2048 `.ter` and the combined base colour map, byte for byte what `terwin.lua` and `stream.lua` make
(`tests/test_helper.py`). It reads the same files the game reads (loose `<user>/levels/ticino/` first, then the
`ticino_*.zip` in `<user>/mods`) and talks to the mod through files in `<user>/temp/ticino/helper/` (`ticino/helper.lua`):
the mod writes the car's position every 250 ms, the helper keeps the 8 windows the next move can go to ready (the
one ahead of the car first), and the streamer takes them instead of making them. At a jump the mod waits up to
`HELPER_WAIT_MS` for the helper's window. Without a helper (not started, closed, `alive.json` older than 4 s)
nothing changes. Only the window's files move off the game thread: the swap (`terrainFile` + `postApply`), objects,
forest, collision and the AI map stay where they are, the engine makes them on its own thread.

    avvia_helper.bat                     (Windows: before the game, leave the window open)
    python helper/ticino_helper.py --user <BeamNG user folder>
    python helper/ticino_helper.py --user <dir> --once <wx> <wy> --out <dir>      one window, with timings

Simulator (`tests/sim_stream.lua`, `REALTIME=1` runs it in real time so the helper can work beside it; no luajit in
the cloud: `python tests/luajit.py tests/sim_stream.lua <level folder> 150`), zone ti_0_0, 120 km/h for 5 km:
without the helper the jump's window took 333 ms and a move 181 ms of Lua over 33 frames (worst Lua frame 151 ms);
with it every move used the helper's files (0 ms of Lua, worst Lua frame 36-108 ms, that is objects and collision
now), the jump waited 122-382 ms for it (a cold helper reads the blocks from the zips), a window took the helper
30-130 ms. Helper killed halfway: the next moves were made in Lua again, as before.

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
  on a whole zone: 709 of 709 identical), laid out as the game lays out its own cache (`cdae.py`).
- Smaller: zone ti_0_8, 396 MB of `.dae` -> 190 MB of `.cdae` (in the zip 74 -> 86 MB: binary floats compress less).
  709 shapes in 8 s on 4 cores.
- Mixed installs: `objects.lua` takes the `.cdae` when it is there and the `.dae` when a tile names a `.cdae` that is not
  installed (an older zone zip beside a newer base).
- By hand: `python dae2cdae.py <level folder>` (or `--one in.dae out.cdae`).

## Not done yet (phase 1 and later)

- Floating origin (rebase every ~15 km): not needed for the Malcantone (12 km), needed for Ticino (62 x 93 km).
- Forest streaming (840k items are one Forest today), AI navgraph clipped to the window and a traffic guard.
- The pipeline building a zone block by block (today: cut a finished level), new zones, the detail modules of the plan
  (guard rails and walls from LiDAR, lamps, tunnels).
- Big map, time trials and spawn points of a zone set in the mod.

Credits: the terrain swap, ground cover flush, runtime objects and pause follow BeamNG.Earth (TecnaGamer, MIT,
`mod/THIRD_PARTY.md`).
