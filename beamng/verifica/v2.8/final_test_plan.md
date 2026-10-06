# v2.8: the test of the whole zip in the game, before the release (michi's PC)

Every v2.8 change was checked on its own, on the v2.7 zip, with the 3D renderer of the pipeline (the `README.md` in each folder here); none of them in BeamNG.drive yet. The release is the v2.7 zip through all nine patches (`beamng/pipeline/patch_v2_8.py`, run by `.github/workflows/release_v2.8.yml`), so this test is on that zip, all changes together. The release workflow refuses to run while `beamng/RELEASE_v2.8.md` is still the draft.

1. **The zip.** Either the `v28-build-test` artifact of the latest *v2.8 build test* run (Actions; it also holds the nine patch reports and `check_level.py` / `drive_test.py` on v2.7 and v2.8), or on the PC, in `beamng/pipeline`:
   ```
   python patch_v2_8.py D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip D:\beamng_magliaso\dist\magliaso_pura_v2.8.zip
   ```
   (about an hour; it prints a digest of the zip's contents at the end: the same patches on the same v2.7 zip give the same digest, on the PC and on GitHub).
2. **The views, the frame rate and the memory**, v2.7 first, then v2.8, both cold (the game's converted copy of the level is deleted before each run):
   ```
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip -Tag v27
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.8.zip -Tag v28
   ```
   Each run puts that zip alone in `mods` (the other `magliaso_pura` zips go to `mods_aside` and come back), shows the 42 views of the nine checks (the `sites.json` here: 38 by day, then the 4 street views of the lamps at night) and writes `beamng/verifica/screenshots/v2.8/<topic>_<tag>_<site>.jpg` and `test_<tag>.json` (the zip's MD5, the load time, the frame rate of every view, the game's peak memory, the level errors of the log).
3. **Look and drive**, with the lists of the nine checks (the section *Test in BeamNG.drive 0.39* of each `README.md` here). Above all:
   - nothing standing in another: a lamp, a delineator, a pole, a sign or a catenary mast on another one, on a carriageway or in a wall (each patch keeps clear of what was there before it in the chain);
   - the ground beside the roads (paved edges) under the lamps, delineators and signs: their feet on the ground, not floating;
   - the undergrowth in the woods, and the frame rate there;
   - the houses' gutters and panels, the piers and boats, the overhead line, by day;
   - the cantonal road's lamps lighting at night.
4. **The street lamps' lights** (a choice for michi): the release has them on the 73 lamps of v2.7 only. For the 1,779 new ones, build the variant and run the same views:
   ```
   python patch_v2_8.py D:\beamng_magliaso\dist\magliaso_pura_v2.7.zip D:\beamng_magliaso\dist\magliaso_pura_v2.8_lights.zip --village-lights
   .\run_v28_screenshots.ps1 -Zip D:\beamng_magliaso\dist\magliaso_pura_v2.8_lights.zip -Tag v28lights
   ```
   and compare the night views of `test_v28.json` and `test_v28lights.json`. If they are to light, `release_v2.8.yml` passes `--village-lights` to `patch_v2_8.py` and the release notes say so.
5. **Write it down.** Commit the screenshots and the `test_*.json` on a branch; in `beamng/RELEASE_v2.8.md` fill in *Checked in the game* (load time, frame rate, memory against v2.7, what was found), pick a few screenshots for the table at the top, and remove the draft line; in `CHANGELOG.md` the heading becomes `## v2.8`, and in `beamng/README.md` the ready-made mod is the v2.8 release. If the game shows a problem, describe it in an issue and stop: the patch that causes it is fixed and the test is run again.
6. **The release**, once that is merged: Actions > *Release v2.8* > Run workflow. It builds the same zip again from v2.7 (its log prints the digest of step 1) and publishes it with `beamng/RELEASE_v2.8.md`.
