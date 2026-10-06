# Check of `patch_house_details.py` (v2.8, in progress)

Gutters, downpipes, TV aerials, satellite dishes and solar panels on the houses. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-gutters-downpipes-aerials-dishes-solar-panels).

**Verification method so far: 3D renderer fallback** (`render3d.py` with textures, without the game). The details are pipeline meshes, so the renders show them as they are; their look in the game, the drawing distances and above all the frame rate and the memory are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: houses, gutters (km), downpipes, aerials, dishes, roofs with panels, tiles and triangles |
| `sites.json` | the four views (`houses_tour.py sites`): an aerial and solar panels near the spawn of Gravesano, solar panels near the spawn of Caslano, a street at the spawn of Magliaso |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |

## Results (on the v2.7 zip)

- 7,212 houses (GWR residential categories) among the roofs of the level.
- 305 km of gutters on every pitched roof, 38,407 downpipes (4 a roof at most), 1,903 aerials, 1,483 dishes, 398 roofs with solar panels (16,151 m²).
- 547,354 triangles in 263 shapes (207 tiles of 512 m for gutters, downpipes, aerials and dishes, drawn up to 450 m; 56 tiles of 1024 m for the panels, up to 1100 m), no collision; one 256 px texture for the panels. The level has about 15 million triangles (v2.7) and had 2,188 objects after v2.5: this adds about 4 % and 12 %. **To be measured in the game** (the map is at about 12 GB at its peak, #31).

## Questions for michi

- The shares are a guess: an aerial on 30 % of the houses built before 1991, a dish on 20 %, solar panels on 20 % of those with a roof facing south. More, fewer?
- Gutters and downpipes on every pitched roof: copper on about a third of the roofs, zinc grey on the others.
- If the frame rate or the memory suffer, the first thing to try is drawing the gutters and downpipes only up to 250 m (smaller tiles, more objects) or leaving the downpipes out.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `houses-test` artifact of the *House details test zip* workflow, or `python patch_house_details.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_houses.zip`.
2. On Windows with the game: `run_houses_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_houses.zip -Tag after` (the four views, the frame rate and the game's peak memory in `game/`).
3. Look at:
   - the gutters along the eaves, not floating over a roof or inside a wall; the downpipes against the walls, down to the ground;
   - the panels on the roofs, not through them; the dishes and aerials on the roofs;
   - the frame rate in the villages (Magliaso, Caslano, Agno), and the load time.
