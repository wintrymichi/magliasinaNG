# Check of `patch_paved_edges.py` (v2.8, in progress)

Paved roads, pavements and yards flush with the ground where nothing marks their edge. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-paved-edges-flush-with-the-ground).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The terrain and the road meshes are the pipeline's own, so the renders show the geometry as it is; the look of the edges, the grass on the raised ground and the frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: the outer edges of the paved faces (not the paths) out of the keep-out zones, their height over the terrain 0.3 m beyond them and the terrain over the faces 0.15 and 0.5 m inside them, before and after |
| `sites.json` | the three places (`paved_tour.py sites`): near the spawn points of Magliaso, Agno and Cademario, the nearest asphalt edge that stood 0.25-0.6 m over the ground in v2.7, out of the keep-out zones; a driver's view on the road and a low view along the edge |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |
| `keep_sites.json`, `render3d/keep_map_*.png` | beside a fence, a wall and a house (`paved_tour.py keep_sites`): the terrain the first merged version raised there, and the patch now (`keep_map`, 40 x 40 m from above, the outlines of what marks the edge in red) |

## Results (on the v2.7 zip)

The outer edges of the paved faces out of the keep-out zones (443 of 973 km; the rest are within 2 m of a guard rail, fence, wall, building, the railway or a bridge parapet and stay as they were):

| | v2.7 | patched |
|---|---|---|
| edge over the ground 0.3 m beyond it, median | 0.21 m | 0.07 m |
| 75th / 90th percentile | 0.30 / 0.46 m | 0.09 / 0.14 m |
| edges over 0.15 m | 74 % | 8.3 % |
| edges over 0.3 m | 25 % | 3.1 % |
| terrain over the faces 0.15 and 0.5 m inside the edges | 0.004 % of the points | 0.006 % |

- 1.24 million terrain vertices raised (median 0.13 m), none in the keep-out zones; no road face changed, only `theTerrain.ter`: no change in frame rate or memory is expected.
- The keep-out zones keep their ground. The first merged version left only the faces in them out of the raise: the faces farther off still raised 499,255 terrain vertices in the zones through their 4.5 m fade, against the walls (106,348 vertices within 0.75 m of one, 16,518 by more than 0.3 m), the fences (median 0.33 m) and the houses, up to 0.99 m; found by an audit of the v2.8 patches chained (`patch_v2_8.py`). Now those vertices are put back as they were (`keep_map_*.png`). The edges next to a zone rise a little less: over 15 cm 8.3 % of them instead of 6.7 %.
- The first version of the patch also lowered the outer edges onto the raised terrain by up to 8 cm (to 3.6 cm over the ground). In the *Paved edges test* workflow `check_level.py` did not change, but `drive_test.py` counted 41 % more hard knocks (HARD) on the main roads and 64 % more on the minor ones, and more wheels lifting (LIFT): the last strip of a road tilts, by a different amount at every edge vertex, under the wheels. Now the faces stay as they are.
- In the renders: the dark side of the asphalt slab along the edge in v2.7 (low views at Magliaso and Agno, the right edge in the driver's views at Magliaso and Cademario) is a thin line; the ground meets the asphalt.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `paved-edges-test` artifact of the *Paved edges test* workflow, or `python patch_paved_edges.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_paved_edges.zip`.
2. On Windows with the game: `run_paved_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_paved_edges.zip -Tag after` (the six views, the frame rate and the game's peak memory in `game/`).
3. Look at, and drive along the edges:
   - no green showing through the asphalt near its edges, no flicker between road and ground (the terrain is 4 cm under it, as beside the tracks of v2.7);
   - the raised ground beside the road: its verge and the grass beyond it as in v2.7, only higher;
   - a car leaving the road at the edge: no step any more where nothing marks the edge;
   - beside guard rails, walls, fences and houses: as in v2.7.
