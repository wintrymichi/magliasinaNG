# Check of `patch_paved_edges.py` (v2.8, in progress)

Paved roads, pavements and yards flush with the ground where nothing marks their edge. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-paved-edges-flush-with-the-ground).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The terrain and the road meshes are the pipeline's own, so the renders show the geometry as it is; the look of the edges, the grass on the raised ground and the frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: the outer edges of the paved faces out of the keep-out zones, their height over the terrain 0.3 m beyond them and the terrain over the faces 0.15 and 0.5 m inside them, before and after |
| `sites.json` | the three places (`paved_tour.py sites`): near the spawn points of Magliaso, Agno and Cademario, the nearest asphalt edge that stood 0.25-0.6 m over the ground in v2.7, out of the keep-out zones; a driver's view on the road and a low view along the edge |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |

## Results (on the v2.7 zip)

The outer edges of the paved faces out of the keep-out zones (452 of 991 km; the other 539 km are within 2 m of a guard rail, fence, wall, building, the railway or a bridge parapet and stay as they were):

| | v2.7 | patched |
|---|---|---|
| edge over the ground 0.3 m beyond it, median | 0.21 m | 0.036 m |
| 75th / 90th percentile | 0.30 / 0.46 m | 0.07 / 0.12 m |
| edges over 0.15 m | 74 % | 6.6 % |
| edges over 0.3 m | 25 % | 2.6 % |
| terrain over the faces 0.15 and 0.5 m inside the edges | 0.004 % of the points | 0.006 % |

- 1.75 million terrain vertices raised (median 0.11 m), 287,085 edge vertices lowered (at most 8 cm) in 323 road shapes, 417,465 terrain vertices lowered again (median 2 cm) to stay 2 cm under the faces as they are after the edges went down; 60,804 paint vertices in 137 shapes lowered with the faces (median 3 cm, at most 7.6 cm: they would have floated over the asphalt).
- Without that last check the terrain showed through the asphalt at 0.46 % of the points inside the edges (a lowered edge tilts the last strip of its face over the terrain raised under it): found by this measure on a first run, fixed before these renders.
- Nothing is added (same vertices and objects, the zip 0.6 MB bigger): no change in frame rate or memory is expected; the game converts the 460 changed shapes again on the first load.
- In the renders: the dark side of the asphalt slab along the edge in v2.7 (low views at Magliaso and Agno, the right edge in the driver's views at Magliaso and Cademario) is gone; the ground meets the asphalt.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `paved-edges-test` artifact of the *Paved edges test* workflow, or `python patch_paved_edges.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_paved_edges.zip`.
2. On Windows with the game: `run_paved_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_paved_edges.zip -Tag after` (the six views, the frame rate and the game's peak memory in `game/`).
3. Look at, and drive along the edges:
   - no green showing through the asphalt near its edges, no flicker between road and ground;
   - the raised ground beside the road: its verge and the grass beyond it as in v2.7, only higher;
   - the road paint near the edges on the asphalt, not over it or under it;
   - a car leaving the road at the edge: no step any more where nothing marks the edge;
   - beside guard rails, walls, fences and houses: as in v2.7.
