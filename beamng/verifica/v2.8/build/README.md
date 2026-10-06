# The v2.8 build: the nine patches chained

How the release zip is made and checked before the test in the game: [`final_test_plan.md`](../final_test_plan.md); the scripts: `beamng/pipeline/patch_v2_8.py` (the chain), `v28_check.py` (this check), `.github/workflows/v28_build_test.yml` and `release_v2.8.yml`. The release itself is not built yet and nothing here is checked in BeamNG.drive.

| File | What it is |
|---|---|
| `check.json` | `v28_check.py` on the chain of the merged patches (the v2.7 zip through the nine, in a cloud container): the numbers of every patch's report that differ from the patch alone, the entries of the zip, the feet of the objects against the v2.8 ground, the clearances between the objects of different patches |

## The chain (v2.7 zip, the patches as merged on 6.10.2026)

- 3,076 entries (509 added, 328 changed, none removed), 520.8 MB; 21-26 min on GitHub, 34-36 min in the container.
- **The same zip every time on GitHub:** two runs of the *v2.8 build test* on the same commit (37491137150 and 37492589295, on Python 3.11.17 and 3.11.16) printed the same digest, `d006f533c56e…`; two runs in the container (Python 3.13, with random hash seeds or not) gave the same digest too, `7005440d3ecf…`, another one than GitHub's (other library builds; `patch_v2_8.py` leaves out only the random persistent ids). So the release built on GitHub is the zip of the build test: `release_v2.8.yml` checks it with `tested_digest`.
- **`check_level.py`:** no value changed between v2.7 and v2.8.
- **`drive_test.py`, v2.7 → v2.8:** the same as with the paved edges alone (the other patches put nothing on the roads): HARD knocks on the main roads 12,284 → 12,110, on the minor roads 142,463 → 142,342, on the paths 445,849 → 439,093; LIFT on the minor roads 6,463 → 6,453; places with knocks on the main roads 159 → 154, minor 2,470 → 2,459. Three place counts on the minor roads grow by one (LIFT 512 → 513, STEP 151 → 152, TWIST 98 → 99).
- **Chained against alone:** placed on the ground the paved edges raise, the new objects stand on it (none more than 5 cm under it); the same patches alone, on the v2.7 ground, would have 693 of the new lamps and 383 of the wooden poles more than 5 cm under the v2.8 ground. The raised ground changes which places pass the lamps' step test: 1,785 new lamps instead of 1,779; and the downpipes reach it: 38,377 instead of 38,407.

## What the chain showed, and the follow-ups

An audit of the nine patches read together, and `check.json`, found:

| | In this chain | Follow-up |
|---|---|---|
| terrain raised inside the keep-out zones of the paved edges (against walls, fences, houses), up to 0.99 m | 499,255 vertices | wintrymichi/magliasinaNG#43: 0 |
| lamp columns with a gutter or downpipe within 0.3 m | 25 | wintrymichi/magliasinaNG#45: 0 |
| lamp columns with a wooden pole's cable within 0.5 m | 8 | #45: 0 |
| places where a cable passes through a house | 18 | #45: 0 |
| lamps, delineators, wooden poles on the railway's ballast | 3, 1, 1 | #45: 0 |
| catenary on standard-gauge yards and spurs OSM tags electrified=no | 5 chains, 2.4 km | wintrymichi/magliasinaNG#44: 0 |
| feet of two kinds closer than 1 m; feet within 0.5 m of a catenary mast | 0 | |

With #43 and #45 the chain was built again in the container: `v28_check.py` gave 0 for every clearance but one place where a cable still grazed the corner of a roof, between two samples 0.5 m apart; #45 now samples the cables every 0.25 m and also 1 m beside them, and on `patch_roadside.py` alone no cable point (every 0.1 m) is under a roof. The release notes and the changelog take their numbers from the build test of the commit that is released.
