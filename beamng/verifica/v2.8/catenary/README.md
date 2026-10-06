# Check of `patch_catenary.py` (v2.8, in progress)

The overhead line of the railway (issue #21). What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-the-railways-overhead-line).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). Masts and wires are pipeline meshes, so the renders show them as they are. Look, collisions and frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: sleepers, track chains and their length, masts, spans, places where no mast could stand and why |
| `sites.json` | the three views (`catenary_tour.py sites`): the middle of the three longest FLP chains, from 7 m beside the track and 3 m up |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |

## Results (3D renderer)

- 9.9 km of track electrified (all of the FLP in the map, two pieces of the SBB line), 201 masts, median span 50 m.
- Masts on the outside of the bends, cantilevers over the track, the messenger wire sagging between the masts, droppers, the contact wire staggered.
- Where no mast can stand for 75 m or more (6 places: a road, a wall or another track beside the line) the wires stop, rather than hang over a span no real line has.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `catenary-test` artifact of the *Catenary test zip* workflow, or `python patch_catenary.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_catenary.zip`.
2. On Windows with the game: `run_catenary_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_catenary.zip -Tag after` (the three views, the frame rate and the game's peak memory in `game/`).
3. Look at:
   - the wires over the track, not through trees or roofs;
   - the masts: never on a road or in a car's way at the level crossings;
   - a car against a mast stops; the wires are not solid.
