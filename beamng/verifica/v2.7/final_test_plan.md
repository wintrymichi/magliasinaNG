# v2.7 final build and in-game test (michi's PC)

michi asked for one v2.7 with everything (markings #26, signs #27, far trees #28, dirt roads #29), in-game
screenshots of the improvements in the PR and in the README, and then the PC shut down.

1. `git fetch` and `git checkout claude/real-road-signs-mphrtz`, then `git pull`. The branch holds all four changes.
2. Build from the v2.6 release zip, in this order (scripts in `beamng/pipeline`):
   ```
   python patch_unpaved.py magliaso_pura_v2.6.zip v26u.zip
   python patch_markings.py v26u.zip v26m.zip
   python patch_far_trees.py v26m.zip v26t.zip D:\beamng_magliaso\work\trees_area.npz
   python patch_signs.py v26t.zip magliaso_pura_v2.7.zip --report ..\verifica\signs_v2.7.json
   ```
   Keep each script's printed summary, the zip size and its MD5.
3. Put `magliaso_pura_v2.7.zip` in `Documents/BeamNG.drive/current/mods` in place of the current v2.7 (only v2.0 stays in
   `mods_aside`). Delete `<user>\temp\levels\magliaso_pura` so the game converts the shapes and impostors again.
4. Start BeamNG.drive, load `magliaso_pura`, note the load time, the fps and any error in the log. Take in-game
   screenshots (1920x1080 jpg, under ~400 KB each, 12-16 in all) from a driver's or low point of view, reusing the
   existing scripts (`bng_lua/magliaso_signs.lua`, `signs_screenshots.py`, the sites in `beamng/verifica/v2.7/`):
   - signs: zone 30, roundabout, the 50 "generale" with the village name, a crossing sign, STOP, and 2-3 of the redrawn
     cantonal road plates (2.33 pass on the right, zone 30 with 16 t, the pointer to Caslano / Pura);
   - markings: a dashed centre line, a Swiss pedestrian crossing, a roundabout;
   - dirt roads: the Arosio and Cademario tracks flush with the ground;
   - far trees: wooded slopes from the valley (the pass above Gravesano from Gravesano, the Malcantone from the lake).
   Save them as `beamng/verifica/screenshots/v2.7/<topic>_<place>.jpg`. No Street View image anywhere.
5. Commit the screenshots, the new `signs_v2.7.json` and `beamng/verifica/screenshots/v2.7/test.json` (load time, fps
   per site, log errors, zip MD5) to `claude/real-road-signs-mphrtz` and push. The zip stays on the PC.
6. Close BeamNG and report. If something is wrong in the game, describe it and stop. Shut the PC down
   (`shutdown /s /t 60`) only after everything is pushed and nothing is wrong.

## Round 2 (after the first test)

The first test found the panorama plates kept "as measured" showing as dark rectangles: `patch_signs.py` now writes their
outline as an opacity map (`sign_NNN_k_o.data.png`, `opacityMap` in `main.materials.json`).

1. `git pull` on `claude/real-road-signs-mphrtz`.
2. Run only the last step again: `python patch_signs.py v26t.zip magliaso_pura_v2.7.zip --report ..\verifica\signs_v2.7.json`
   (it should print `panorama_opacity_maps: 67`), and put the zip in `mods` in place of the first one.
3. Delete `<user>\temp\levels\magliaso_pura\art\shapes\props` and `...\art\shapes\signs` (the trees' cache can stay).
4. Start the game, take again `signs_cantonale_233.jpg`, `signs_cantonale_pointer.jpg`, `signs_zone30.jpg` and
   `signs_stop.jpg` with `final_screenshots.py`, and check that no plate shows a dark rectangle around its shape.
5. Update `test.json` (new zip MD5 and size, the result of this check, `problems` emptied if fixed), commit, push.
6. If everything is right, close BeamNG and shut the PC down (`shutdown /s /t 60`); otherwise describe the problem and stop.
