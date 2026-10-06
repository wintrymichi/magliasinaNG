# Check of `patch_wall_fill.py` (v2.8, in progress)

The ground behind the retaining walls shaded like the terrain, and no game grass under it or over low walls. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-the-ground-behind-the-walls).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The test in BeamNG.drive 0.39 is still to be done (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: backfill triangles and vertices, normals, terrain vertices without grass, and the checks that geometry and terrain heights are unchanged |
| `sites.json` | the three places compared (Ponte Tresa, the walls along the lake at Agno, the cantonal road to Pura beside its guard rail) and their views (`wall_fill_tour.py sites`) |
| `render3d/before_*.jpg`, `render3d/after_*.jpg` | the v2.7 level and the patched one at the same views: a driver on the road (`driver`) and from 16 m above without the trees (`above`) |
| `render3d/compare_*.jpg` | the two side by side (left v2.7, right patched) |
| `grass_*.png` | 60 m around each place: the terrain layers by colour, in magenta the terrain vertices that lose the game grass (north up, 1 px = 0.19 m) |

The renders draw the level's own meshes with the normals of their DAE, as the game lights them, and the ground in the colour of its terrain layer (the orthophoto is not downloaded in this check). They show the shading, not the game's textures, sky or grass.

## Results (3D renderer)

- **Ponte Tresa** and **Agno**: the faceted triangles of the ground behind the walls, lighter and darker side by side, become one smoothly shaded slope; from the road the facets on the bank are gone.
- **Cantonal road to Pura**: under the guard rail the light-green facets of the backfill (the "light-green slivers behind the guard rail" seen in the game are probably these, or the grass through them) are smooth; soft darker patches remain where the backfill meets a steep trench of the terrain, without a visible seam.
- Not changed, as expected: the saw-tooth outline along some walls (geometry) and the colour of the backfill (the terrain's base texture).
- A variant with the ground's own normal on the edge too was rendered and rejected: the outline of the backfill shows as a line of light.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the patched zip: the `wall-fill-test` artifact of the *Wall fill test zip* workflow, or `python patch_wall_fill.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_wall_fill.zip`.
2. On Windows with the game: `run_wall_fill_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_wall_fill.zip -Tag after`. Each run puts that zip alone in `mods` (the others go aside and come back), converts the wall shapes again and saves the six views of `sites.json` in `game/<tag>_<site>_<view>.jpg`.
3. Look at: the facets and the light at the edge of the backfill; the grass near the walls (none through the backfill or over low walls, still at the foot of tall walls); the cantonal road to Pura beside the guard rail.
4. Note the loading time, the frame rate and the memory at the three places. The patch adds no object and the backfill has fewer vertices, so nothing should get worse.
