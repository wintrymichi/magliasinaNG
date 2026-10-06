# v2.8: the test of the whole zip in the game, before the release (michi's PC)

Every v2.8 change was checked on its own, on the v2.7 zip, with the 3D renderer of the pipeline (the `README.md` in each folder here); none of them in BeamNG.drive yet. The release is the v2.7 zip through all nine patches (`beamng/pipeline/patch_v2_8.py`, run by `.github/workflows/release_v2.8.yml`), so this test is on that zip, all changes together. The release workflow refuses to run while `beamng/RELEASE_v2.8.md` is still the draft.

1. **The zip:** the `v28-build-test` artifact of the latest *v2.8 build test* run (Actions) on the commit to release. It is built on GitHub exactly as the release will be, and also holds the nine patch reports, `patch_v2_8.log` and `check_level.py` / `drive_test.py` on v2.7 and v2.8. Note the digest on the last line of `patch_v2_8.log`. A zip built on the PC (`python patch_v2_8.py <v2.7 zip> <v2.8 zip>`, about an hour) has the same changes but not the same digest: a few text plates are drawn in Arial instead of DejaVu (`signs_ch._font`), and other versions of Python and its libraries can move a value by a rounding.
2. **The views, the frame rate and the memory**, v2.7 first, then v2.8, both cold (the game's converted copy of the level is deleted before each run), in `beamng/pipeline`:
   ```
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip -Tag v27
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.8.zip -Tag v28
   ```
   Each run puts that zip alone in `mods` (the other `magliaso_pura` zips go to `mods_aside` and come back), shows the 42 views of the nine checks (the `sites.json` here: 38 by day, then the 4 street views of the lamps at night) and writes `beamng/verifica/screenshots/v2.8/<topic>_<tag>_<site>.jpg` and `test_<tag>.json` (the zip's MD5, the load time, the frame rate of every view, the game's peak memory, the level errors of the log).
3. **Look and drive**, with the lists of the nine checks (the section *Test in BeamNG.drive 0.39* of each `README.md` here). Above all:
   - the feet of the lamps, delineators, wooden poles and signs on the ground beside the roads (they are placed on the ground the paved edges raised: `build/check.json`);
   - nothing standing in another: a lamp, a delineator, a pole, a sign or a catenary mast on another one, on a carriageway, on the ballast or in a wall; a lamp column through a gutter, a wooden pole's cable through a lamp or a roof (`build/README.md` lists what the automatic check covers and what it found);
   - the undergrowth in the woods, and the frame rate there;
   - the houses' gutters and panels, the piers and boats, the overhead line, by day;
   - the cantonal road's lamps lighting at night.
4. **The street lamps' lights** (a choice for michi): the release has them on the 73 lamps of v2.7 only. For the 1,785 new ones, build the variant and run the same views:
   ```
   python patch_v2_8.py D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip D:\beamng_magliaso\dist\magliaso_pura_v2.8_lights.zip --village-lights
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.8_lights.zip -Tag v28lights
   ```
   and compare the night views of `test_v28.json` and `test_v28lights.json`. If they are to light, `release_v2.8.yml` and `v28_build_test.yml` pass `--village-lights` to `patch_v2_8.py` and the release notes say so.
5. **Write it down.** Commit the screenshots and the `test_*.json` on a branch; in `beamng/RELEASE_v2.8.md` fill in *Checked in the game* (load time, frame rate, memory against v2.7, what was found) and the results of the build test, pick a few screenshots for the table at the top, and remove the draft line; in `CHANGELOG.md` the heading becomes `## v2.8`, and in `beamng/README.md` the ready-made mod is the v2.8 release. The numbers in the release notes and the changelog are those of the reports in the artifact. If the game shows a problem, describe it in an issue and stop: the patch that causes it is fixed, and the build test and this test are run again.
6. **The release**, once that is merged: Actions > *Release v2.8* > Run workflow, with the digest of step 1 in *tested_digest*. It builds the zip again from v2.7, stops if its digest is not the one tested, and publishes it with `beamng/RELEASE_v2.8.md`.
