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
| Far ground (outside the window) | a mesh every 12 m per tile, vertex colours, no collision | `far/f_<cx>_<cy>.dae` |

- The window keeps the car's tile the 4th or 5th of its 8, so the car is always at least 1,152 m from its edge. When
  the car crosses a tile, the next window is written over about 15-20 frames (4 ms of Lua a frame) and swapped in by
  `terrainFile` + `postApply`, the way BeamNG.Earth moves its block (92 ms for 2048^2 measured there).
- Objects are shown within a radius per group (`zones/malcantone.json`: street props 2 tiles, roads and walls 5,
  buildings 6) and collide only in the 3 x 3 tiles around the car (`collision_radius`): every `be:reloadCollision`
  rebuilds all collision, and the whole map collides with about 46 M triangles today.
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
- `tests/check_blocks.py`, `tests/test_lua.py` (needs `luajit`), `tests/sim_stream.lua` (the mod driven at 120 km/h
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

## Not done yet (phase 1 and later)

- Floating origin (rebase every ~15 km): not needed for the Malcantone (12 km), needed for Ticino (62 x 93 km).
- Forest streaming (840k items are one Forest today), AI navgraph clipped to the window and a traffic guard.
- The pipeline building a zone block by block (today: cut a finished level), new zones, the detail modules of the plan
  (guard rails and walls from LiDAR, lamps, tunnels).
- `.cdae` shipped in the zip instead of DAE (no conversion in the game).
- Big map, time trials and spawn points of a zone set in the mod.

Credits: the terrain swap, ground cover flush, runtime objects and pause follow BeamNG.Earth (TecnaGamer, MIT,
`mod/THIRD_PARTY.md`).
