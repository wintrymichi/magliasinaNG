# magliaso_pura v3.0.40 – in-game test (2026-10-21)

BeamNG.drive 0.40.1.0 (Steam updated the game from 0.40.0 the night before the test), Windows, Direct3D 12, RTX 4070
(driver 32.0.16.1742), 2560 × 1440 borderless, preset "Custom": meshes, lighting and clustered lighting Ultra; shadows,
terrain, clouds and SSAO High; textures Normal; SMAA, anisotropic 16×, depth of field and dynamic reflections on. The
settings were read from the game, not changed.

Zip: the nightly #2 of the integration branch (built from `afad5c1`, the far trees' imposters added by `nightly_patch.yml`
from `2bc800f`), md5 `cb162c9552da74949a03fca2af7718dc`, 1,175,443,093 bytes: the zip published as v3.0.40.

The test is one game extension and its plans, run by PowerShell scripts that sample the game's memory every 2 s
([`ingame/`](ingame/): `magliaso_v3040.lua`, `make_plan.py`, `plan_v3040.json`, `run_test.ps1`; the traffic run
`magliaso_traffic.lua` of the traffic thread with `run_traffic.ps1`). The game was started with
`-level magliaso_pura/main.level.json -onLevelLoad_ext magliaso_v3040` and quit itself at the end of the plan.

## Load and memory

| | v3.0.40 |
|---|---:|
| level loaded (`Level loaded in`), empty cache | 230.0 s (physics 168.4 s, objects 31.9 s) |
| the traffic run, same zip | 233.9 s |
| peak working set (RAM in use) | 6,715 MB |
| peak private bytes (committed) | 20,765 MB |
| peak dedicated video memory of the game | 5,768 MB |
| peak video memory in use (all processes) | 6,493 MB |
| peak working set with 12 traffic and 30 parked cars | 8,825 MB |

BeamNG.drive 0.40 clears `temp/levels/<level>` at every start, so every load is a load with an empty cache (it converts
the level's PNG textures again). The log shows no "Failed to load", no NO-MATERIAL and no missing texture on 0.40.1.

A comparison run with v3.0 on the same PC was planned and dropped: the permission check of the remote session refused to
move the installed mod zip out of `mods` to swap the versions. The v3.0 numbers (native Linux, 0.39.4, Ultra) are not
comparable with these (Windows, Direct3D 12, 0.40.1, Custom).

## Frame rate

Free camera at fixed places and directions (the spawn points of the villages, two views from above and the cantonal road),
frames counted over 5 s after a warm-up pass over every place and 3 s to settle:

| Place | FPS |
|---|---:|
| Magliaso junction | 65.8 |
| Pura | 78.6 |
| Magliaso Paese | 133.5 |
| Agno lakeside | 117.6 |
| Caslano | 70.2 |
| Novaggio | 84.2 |
| Bedigliora | 90.7 |
| Arosio | 62.1 |
| Ponte Tresa | 123.2 |
| Breno | 71.0 |
| over Magliaso and the lake | 75.8 |
| over Novaggio | 83.5 |
| cantonal road | 72.5 |

## Screenshots

28 views of what is new in v3.0.40 and one of the traffic, all taken with the game's own screenshot
(`createScreenshot2`), each after 20 s for the textures to load: an ETK 800 in the right-hand lane (planned from the
driver's seat; `core_camera.setByName(0, "driver")` did not take and the game kept its chase camera, so these are views
from behind the car), the car on the routes of the time trials, the churches and the cable car from the roads
around them (every one found a road point with a clear view), and from above. No white or grey squares among the far
trees (`overview-far-trees-040`).

19 of them are in [`../screenshots/v3.0.40/`](../screenshots/v3.0.40/) and in the README, the views behind the car
renamed from `cockpit-*` to `road-*`. Left out: Bedigliora at night and at dusk (black: time of day 0.5 and 0.4 are real
night there), the churches of Miglieglia and Novaggio and the fountain (the road point found had a wall or an alley in
front), the cable car from the road (no cable car in view), the summit of Monte Lema (meadows off the roads in front),
two road views like others kept, and the second Astano – Banco view (car at about (-3680, 2134) looking east): the top
of the high wall on the hill side has V-shaped notches down into the wall, with the slope showing through them. That is a
defect of the level still to look at (the wall checks of the build count no notches there).

## Traffic

The game's traffic (12 cars) and parked cars (30) set up without errors, on an AI network of 21,424 nodes and 21,598
links, with the signals running and 10,912 parking spots. Then:

- with the ETK 800 of the test standing in the right-hand lane of the cantonal road at (-169, -196): 3 cars moving at
  0 s, 5 at 30 s (up to 13 m/s), 2 at 60 s, none from 90 s to the end at 298 s; all of them stopped on the cantonal road
  around the ETK (`strada_cantonale_12…17`, `111…161`);
- with the player's car at the default spawn of the level, the Magliaso junction (747, -1094), on the carriageway of the
  cantonal road (`strada_cantonale2-3`), for 10 minutes: 11 of 12 cars moving at 0 s (6.5 m/s on average), 6 at 20 s,
  3 at 40 s, 1 at 60 s, none from 80 s to the end at 598 s. All of them within about 130 m of the spawn, queued on
  `strada_cantonale3…7` and the links `tlm_10521…10529` and `tlm_10611`; several damaged (damage 3,771, 6,118 and
  9,683: they ran into each other), and the game moved only 2 of them elsewhere.

So the traffic stalls whatever the place: it gathers around the player's car standing still, queues or crashes into
itself there and never clears.

The pattern is the same in both runs: the cars stop where the player's car is, not at the signals. At the default spawn, six of the cars stand in one line about 9.5 m apart behind the player's car, from 9 to 57 m back on the cantonal road coming down to the Magliaso roundabout (`strada_cantonale3…7`), heading for it, undamaged: the player's car stands in their lane 15 m before the give way into the roundabout (`give_way 226`), and they wait behind it to the end. Beyond it one car (damage 9,683) ran into another 1 m from that give way, and one more stands 4 m in front of the player's car on the link into the cantonal road. 130 m away two cars stand at another give way (`give_way 218`), one of them crashed (6,118). One car near the STOP of the Magliaso junction (`stop 151`) was damaged in its first second (3,771) and holds one behind it. The game respawned only 2 of the 12 (`respawns` 1), and both came back into the same queue. In the first run, on the open cantonal road, all 12 stopped 13–133 m from the ETK, 150–330 m from the nearest signal. One car first appeared outside the terrain (y = −10,270 m, z = 0.2) and the game moved it back.

So the traffic is set up right (network, signals, parking), and what stops it is the player's car standing on the carriageway, which the AI does not drive past, the crashes at give-way points, and the respawn that leaves the stuck cars where they are while they are near the player. The level's default spawn on the carriageway makes it happen at every start. Not tested: the traffic with the player driving. The data (`traffic.json`, `state.json`, `signals.json`) went to the traffic thread; issue #83.

## Errors and warnings in the log

- For every screenshot four `|E| GELua.screenshot: ... unknown job id` lines: the test calls `createScreenshot2` without
  the game's screenshot module; the files are written.
- 43 × "could not find vehicles/common/licenseplates/magliaso_pura/licensePlate-default.sktemplate.json": the level has
  no licence plate design of its own, the cars take the default.
- 2 × "Unable to identify any front wheels" (traffic cars).
- "bindless material cbv array exhausted (8192 slots)", as in earlier tests.
- No error or warning of the test extension.
- The traffic run first did not start: the runner installed the extension `magliaso_traffic` as `magliaso_traffic.lua`,
  and the game looks for it in `magliaso/traffic.lua` (fixed in `run_traffic.ps1`). Its frame time file stayed empty:
  `be:getLastFrameDeltaTime` does not exist in 0.40.1.
