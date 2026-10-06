# The v2.8 build: the nine patches chained

How the release zip is made and checked before the test in the game: [`final_test_plan.md`](../final_test_plan.md); the scripts: `beamng/pipeline/patch_v2_8.py` (the chain), `v28_check.py` (this check), `.github/workflows/v28_build_test.yml` and `release_v2.8.yml`. The release itself is not built yet and nothing here is checked in BeamNG.drive.

| File | What it is |
|---|---|
| `check.json` | `v28_check.py` on the chain of the merged patches (main after #43, #44, #45, #46): the numbers of every patch's report that differ from the patch alone, the entries of the zip, the feet of the objects against the v2.8 ground, the clearances between the objects of different patches |

## The build to test (main, 6.10.2026)

*v2.8 build test* run 37503859978 on main (f619516; #33, merged after it, changes only the website), the zip in its `v28-build-test` artifact (kept 14 days by GitHub; afterwards the workflow is run again on main and gives the same zip):

- **digest `7c9842faf2187fac9159df52e0fa8502e055da7b1962d3249e15b5192da2b4a0`**, 3,070 entries (503 added, 328 changed, none removed), 520.3 MB, 25 min. The same patches built in a cloud container (Python 3.13) gave the same digest. This is the `tested_digest` for `release_v2.8.yml` if this zip is the one tested in the game.
- **`check_level.py`:** no value changed between v2.7 and v2.8.
- **`drive_test.py`, v2.7 → v2.8** (only the paved edges change the ground; nothing else is on the roads): HARD knocks on the main roads 12,284 → 12,150, on the minor roads 142,463 → 142,383, on the paths 445,849 → 440,950; on the paths LIFT 74,129 → 72,232, STEP 76,863 → 76,452, TWIST 139,339 → 134,226; minor LIFT and TWIST as in v2.7. Places with knocks: main HARD 159 → 155, minor HARD 2,470 → 2,459; three single counts grow by one (minor LIFT 512 → 513, minor TWIST 98 → 99, paths HARD 12,303 → 12,304).
- **The objects against each other** (`check.json`): no two feet of different kinds (street lamps, delineators, wooden poles, signs) closer than 1 m, none within 0.5 m of a catenary mast, none on the railway's ballast; no lamp column with a wooden pole's cable within 0.5 m or a gutter or downpipe within 0.3 m; no cable under a roof.
- **On the v2.8 ground:** the new objects stand on the ground the paved edges raise (none more than 5 cm under it); placed alone on the v2.7 ground, 579 of the new lamps and 302 of the wooden poles would stand more than 5 cm under it. Of the 73 lamps of v2.7, which the patches do not move, 15 have the v2.8 ground more than 5 cm over their foot (6 in v2.7), 6 more than 15 cm (2 in v2.7): the column a little shorter.
- **The counts in the chain:** 1,764 new street lamps, 499 delineators, 543 wooden poles in 110 lines (433 cable spans; 74 times a line ended where its cable would have passed a lamp or a house), 168 catenary masts over 8.1 km, 80 signs, 23 piers and 137 boats, 7,212 houses with 305 km of gutters, 38,405 downpipes, 1,903 aerials, 1,483 dishes and 398 roofs with solar panels; 1.24 million terrain vertices raised beside the paved edges (none in the keep-out zones), 200,441 without grass behind the walls.

## What the first chain showed

The first chain of the nine patches (as merged before 6.10.2026 evening), read together by an audit and measured with `v28_check.py`, had:

| | First chain | Fixed by |
|---|---|---|
| terrain raised inside the keep-out zones of the paved edges (against walls, fences, houses), up to 0.99 m | 499,255 vertices | wintrymichi/magliasinaNG#43 |
| lamp columns with a gutter or downpipe within 0.3 m | 25 | wintrymichi/magliasinaNG#45 |
| lamp columns with a wooden pole's cable within 0.5 m | 8 | #45 |
| places where a cable passes through a house | 18 | #45 |
| lamps, delineators, wooden poles on the railway's ballast | 3, 1, 1 | #45 |
| catenary on standard-gauge yards and spurs OSM tags electrified=no | 5 chains, 2.4 km | wintrymichi/magliasinaNG#44 |

Two runs of the build test on the same commit then gave the same digest on GitHub (on Python 3.11.17 and 3.11.16), which `release_v2.8.yml` relies on; two runs in the container agreed with each other but not with GitHub at the time (the cause was not looked into: the final build above matches on both).
