# Check of `patch_roadside.py` (v2.8, in progress)

Delineator posts along the main roads outside the villages, and wooden pole lines along the country roads. What the patch does and why: [`beamng/README.md`](../../../README.md#version-28-in-progress-delineators-and-wooden-pole-lines).

**Verification method so far: 3D renderer fallback** (`render3d.py`, without the game). The delineators and the cables are pipeline meshes, so the renders show them as they are. The game's wooden pole is drawn as a grey post of its height. Look, collision and frame rate are still to be checked in BeamNG.drive 0.39 (below).

| File | What it is |
|---|---|
| `report.json` | the patch's report on the v2.7 zip: 507 delineators, 628 poles, 504 cable spans, the tries rejected and why, every post and pole |
| `map.png` | the whole map: the main roads (dark), the other roads (light), the delineators (red) and the poles (blue) |
| `sites.json` | the four views (`roadside_tour.py sites`): the two 300 m squares with the most delineators in open country, and the two with the most poles outside the woods |
| `render3d/before_*.jpg`, `after_*.jpg`, `compare_*.jpg` | v2.7 and patched at the same views, and the two side by side |

## Results (3D renderer)

- The delineators stand along the ring of cantonal roads (Ponte Tresa – Caslano – Magliaso – Agno – Bioggio – Manno – Gravesano) and on the road towards Sessa, at the edge of the carriageway, with the black band towards the road. Where a guard rail, a wall or a building marks the edge there are none. There are none on the Magliaso–Pura cantonal road, which keeps its measured posts.
- The pole lines, with their cable, follow the country roads past the scattered houses. Lines of fewer than 4 poles are left out (1,585 poles), because a lone pole carries nothing.

## Test in BeamNG.drive 0.39 (still to do)

1. Get the zip: the `roadside-test` artifact of the *Roadside test zip* workflow, or `python patch_roadside.py magliaso_pura_v2.7.zip magliaso_pura_v2.7_roadside.zip`.
2. On Windows with the game: `run_roadside_screenshots.ps1 -Zip magliaso_pura_v2.7.zip -Tag before`, then `-Zip magliaso_pura_v2.7_roadside.zip -Tag after` (the four views, the frame rate of every view and the game's peak memory in `game/`).
3. Look at:
   - the delineators: height, band on the road side, none in a car's way;
   - the poles: the cable meets the top of the game model, or it needs an offset (`CABLE_DROP` and the cable's start at the pole's axis in `patch_roadside.py`);
   - drive into a delineator: no collision, the car goes through it;
   - drive into a pole: it stops the car.
