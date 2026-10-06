# Check of `patch_lamps.py` (v2.8, in progress)

Street lamps along the roads of the villages, and the lights of the street lamps. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-street-lamps-in-the-villages).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The game's lamp model is not available here, so the renderer draws every game model as a grey post: the renders check where the lamps stand, not how they look. Frame rate, memory and the lights at night are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: lamps before and new, lights, the tries rejected and why, new lamps per commune, and every new lamp (x, y, z, arm direction in degrees) |
| `sites.json` | the four places compared (the 100 m square with the most new lamps in Tresa, Lema, Agno and Caslano) and their views (`lamps_tour.py sites`) |
| `render3d/*_driver.jpg` | a driver on the village street, v2.7 and patched (the lamps as grey posts) |
| `render3d/*_top.jpg` | the 240 m around each place from above, the lamps marked: yellow the new ones, white those of v2.7 |
| `render3d/compare_*.jpg` | the two side by side |

## Results (3D renderer)

- 1,779 new lamps (Tresa 340, Lema 252, Agno 232, Bioggio 187, Gravesano 130, Caslano 128, Manno 111, Pura 100, Cademario 86, Vernate 68, Magliaso 52, Aranno 40, Alto Malcantone 38, Neggio 13, Lamone 2), about one every 30 m on one side of the village streets, at the edge of the carriageway, not at junctions.
- Few in the old towns (Novaggio, Agno): the houses stand at the edge of the road, and there the real lamps hang on the walls.
- Some stand in car parks crossed by a road of the AI network; that is plausible.
- The 73 lamps of v2.7 get their lights. The new ones get lights only in the `_lights` variant.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zips: the `lamps-test` artifact of the *Street lamps test zip* workflow (`magliaso_pura_v2.7_lamps.zip` without the lights of the new lamps, `magliaso_pura_v2.7_lamps_lights.zip` with them), or run `patch_lamps.py`.
2. On Windows with the game: `run_lamps_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag v27`, then `-Zip magliaso_pura_v2.7_lamps.zip -Tag lamps` and `-Zip magliaso_pura_v2.7_lamps_lights.zip -Tag lamps_lights`. Each run puts that zip alone in `mods` and saves the four driver views by day and at night in `game/`, with `<tag>_fps.json` (the frame rate of every view, the load line of the log, the game's peak memory).
3. Look at: the lamps on the pavements and verges, the arm over the road, nothing in a wall or a car's way; at night, whether the cantonal road's lamps light and how the villages look with and without the new lights.
4. Compare `v27`, `lamps` and `lamps_lights`, then choose whether the new lamps light (frame rate at night, memory).
