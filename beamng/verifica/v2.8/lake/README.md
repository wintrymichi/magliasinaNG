# Check of `patch_lake.py` (v2.8, in progress)

The piers of the lake and the boats moored at them. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-piers-and-boats-on-the-lake).

**Verification method so far: 3D renderer fallback** (`render3d.py` with textures, without the game). Piers and boats are pipeline meshes, so the renders show them as they are; the look in the game (the water around the floats and the hulls, the planks), the collisions and the frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: piers built (fixed, floating, length), left out, boats, tiles; every pier built (OSM id, floating, width, mooring, centre, length) |
| `sites.json` | the three views (`lake_tour.py sites`): the longest pier where boats moor (Ponte Tresa), the longest fixed pier (the lido of Caslano) and the longest pier OSM maps as a mooring (Caslano), from the lake 28 m beside the pier and 3 m over the water |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |

## Results (on the v2.7 zip)

- 25 piers mapped on the Swiss side; 23 built over the water (12 fixed on posts, 11 floating), 954 m in all; 2 mapped on land left out.
- 137 boats at the piers where boats moor: covered and open motor boats, sailing boats with a mast.
- 15,291 triangles and 2.5 MB in 16 shapes (12 pier tiles drawn up to 600 m, 4 boat tiles up to 400 m), one 256 px texture: a small cost, still to be measured in the game.
- Where they are: 11 at Caslano, 4 at Magliaso, 4 at Agno, 3 at Ponte Tresa, 1 at Collina d'Oro.

## Questions for michi

- The boats are a rule (OSM maps where boats moor, not the boats): one every 3 m, a quarter of the berths empty. More, fewer, none?
- Mooring buoys with boats on them are common along the shore but not in the data: leave them out, or place some by a rule?

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `lake-test` artifact of the *Lake test zip* workflow, or `python patch_lake.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_lake.zip`.
2. On Windows with the game: `run_lake_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_lake.zip -Tag after` (the three views, the frame rate and the game's peak memory in `game/`).
3. Look at:
   - the floats and the hulls at the water line (the game's water has waves; the boats do not move);
   - the planks of the decks, the posts into the lake bed;
   - walk or drive onto a pier: the deck holds, a car against a boat or a post stops.
