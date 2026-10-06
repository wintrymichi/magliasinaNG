# Check of `patch_understory.py` (v2.8, in progress)

A darker forest floor and undergrowth in the woods. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-undergrowth-and-a-darker-forest-floor).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The renderer draws the ground in the median colour of its terrain layer's base texture, so it shows the darker forest floor. It does not draw the undergrowth: the game's GroundCover places it around the camera at run time. The undergrowth, its look and its frame rate can only be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: forest floor vertices, those turned to the verge twins (no undergrowth) near roads, paths, walls, buildings and the railway, the floor colour before and after, the undergrowth settings |
| `sites.json` | the three views (`understory_tour.py sites`): a driver on a forest road near Arosio, the pass above Gravesano from the village, the Malcantone from the lake off Agno |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side. On the far views only what is within 400 m has trees and meshes; beyond is the coarse terrain |

## Results (3D renderer)

- The forest floor goes from the light brown measured on the sunlit forest edges (102, 98, 67) to a darker olive (62, 66, 42). From the lake and from Gravesano the wooded slopes no longer show light brown ground between the crowns. On the forest road the banks are darker.
- 980,953 of the 26.1 million forest floor vertices are within a terrain square of a road, path, wall, building or the railway: there, no undergrowth.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `understory-test` artifact of the *Understory test zip* workflow, or `python patch_understory.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_understory.zip`.
2. On Windows with the game: `run_understory_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_understory.zip -Tag after` (the three views, the frame rate of every view and the game's peak memory in `game/`).
3. Look at:
   - the undergrowth: do the shrubs appear? This is the first GroundCover of the map with game models instead of grass cards;
   - their size and density;
   - no shrub on roads and paths or through walls;
   - the colour of the forest floor near and far.
4. Compare the frame rate in the woods before and after. The undergrowth density (`groundcover.UNDERSTORY`: 600 elements within 60 m) can be lowered there if needed.
