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
(`createScreenshot2`), each after 20 s for the textures to load: from the driver's seat of an ETK 800 in the right-hand
lane, behind the car at the starts and checkpoints of the time trials, the churches and the cable car from the roads
around them (every one found a road point with a clear view), and from above. No white or grey squares among the far
trees (`overview-far-trees-040`). The pictures are in [`../screenshots/v3.0.40/`](../screenshots/v3.0.40/).

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
itself there and never clears. TRAFFIC_CAUSE

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
