# Check of `patch_signs_more.py` (v2.8, in progress)

Warning and parking signs nobody mapped in OpenStreetMap (issue #21). What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-warning-and-parking-signs-nobody-mapped).

**Verification method so far: 3D renderer fallback** (`render3d.py` with textures, without the game). The poles and plates are pipeline meshes with the drawn plates as textures, so the renders show them as they are; how they read in the game, their collision and the frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: the signs planned by kind, put up, left out (no room), on roads the map does not build, moved back from a sign already there; every sign put up (place, facing, plates, OSM object) |
| `sites.json` | the five views (`signs_more_tour.py sites`): one sign of every kind, from the road 15 m before it, where the traffic that reads it comes from |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |
| `plates.png` | the new plates as `signs_ch.py` draws them (1.23 and 1.24 are drawn for the OSM hazards, none on the Swiss roads of the map so far) |

## Results (on the v2.7 zip)

| Signal | Planned | Put up | On roads the map does not build |
|---|---|---|---|
| 4.17 parking | 110 | 54 | 55, and 1 with no room beside the road |
| 1.15 level crossing with barriers | 13 | 10 | 3 |
| 1.16 level crossing without barriers | 8 | 8 | 0 |
| 1.01-1.04 curves, double curves | 16 | 5 | 11 |
| 1.13 falling rocks | 4 | 3 | 1 |
| **total** | **151** | **80** | **70** |

- 4 signs went 12 m back because one the same traffic already reads stood within 10 m (in the falling rocks view at Magliaso, the beginning of the village sign of v2.7 in front of it).
- 9 new textures (the new signals and three length plates), 256 px or less; one new shape for the whole map, like `props_signs.dae` of v2.7: no change in frame rate or memory is expected.

## Questions for michi

- **Parking:** 54 blue P at the entrances of the public car parks. Too many, too few? The rule leaves out the car parks whose access OSM does not record unless they are large (1000 m² or 40 places).
- **Curves:** only the unexpected sharp curves outside the villages (a straight of 150 m before them). On the mountain roads with one hairpin after another (to Cademario, Arosio) there is none: that is how they look in reality as far as I know, but you know them.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `signs-test` artifact of the *Signs test zip* workflow, or `python patch_signs_more.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_signs.zip`.
2. On Windows with the game: `run_signs_more_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_signs.zip -Tag after` (the five views, the frame rate and the game's peak memory in `game/`).
3. Look at:
   - every plate facing the traffic that reads it (the picture, not the grey back), upright, not mirrored;
   - the poles beside the road, not on it, not in a wall or a hedge;
   - a car against a pole stops.
