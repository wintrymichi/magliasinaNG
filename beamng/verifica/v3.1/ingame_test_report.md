# v3.1 in-game test (2026-10-24, DESKTOP-OUPOLOA)

Build: release asset `magliaso_pura_v3.1.zip`, 1,525,507,935 bytes, sha256 a1f10666…67fd8 (matches the release digest).
Game: BeamNG.drive 0.40.3.0 (log), Direct3D 12 on NVIDIA GeForce RTX 4070, 2048x1152 borderless on the virtual display, Ultra preset, texture quality Normal (michi's settings). Only magliaso_pura_v3.1 active (v3.1_test zip disabled; BeamMP mod left as it was).

## Numbers
- Load time: **229 s** ("Level loaded in 228.941s": objects 58.4 s, physics 144.8 s, fade 25.6 s). Second load in the same session, shapes already converted.
- RAM (game process): working set peak **16.8 GB** (during the load), commit (private) peak **24.0 GB**; steady after load about 12.5 GB working set / 18.7 GB commit.
- VRAM: process dedicated peak **7.2 GB**; whole GPU peak 8.5 GB of 12 GB (1.5 GB used before the start).
- FPS (8 s each, background FPS cap off):
  | view | fps | worst frame ms |
  |---|---|---|
  | Magliaso roundabout | 69.0 | 16 |
  | Via Golf underpass | 77.2 | 16 |
  | Cantonale cut slope | 54.4 | 21 |
  | Woods road (Alto Malcantone) | 77.5 | 13 |
  | Ponte Tresa bridge | 62.6 | 16 |
  | 150 m over Magliaso | 77.0 | 13 |
- Night lamps: 2113 night lights and 453 emissive statics registered; at about 22:00 the road is lit between the lamps.

## Problems found
1. **Walls still have saw-tooth tops** on the Magliaso - Pura Cantonale, including the hairpin (driver-hairpin-wall.jpg) and the cut near node 58 above Magliaso: the README caption "a straight top" is not true in the game.
2. **Missing materials** `mp_island_reflector` and `mp_island_beacon` (30 errors each in beamng.log): the new traffic island posts.
3. **Via Golf underpass deck** renders as a flat untextured grey slab; the raised footways (known issue) are visible from the driver's seat.
4. Grass tufts on the asphalt of the Ponte Tresa bridge at the Italian end; the Italian side is flat low-detail ground, so the driver shot looks towards Switzerland.
5. Large angular wall blocks beside strada_cantonale_1 near (-222,-60).
6. AI traffic (#83, test stopped on michi's request): 13 cars queued behind the parked player car on the Magliaso bridge, then crashed into the traffic island at the roundabout exit (783,-1143); 8 of 12 cars damaged within 2 minutes.
7. beamng.log: "material cbv array exhausted (8192 slots)" warning (bindless), and no licence plate template for the level.

## Not done
- Time trials and AI traffic: skipped on michi's request (he tested the time trials himself). race-start-facing.jpg not taken.
- Placement guesses: roofs-caslano-canopy is the large canopy on posts at (255,-1928) next to the FLP (not verified as the station); roofs-porch-posts is a roof on posts at Novaggio (-982,1995).

## Lessons for CLAUDE.md
- The driver camera in 0.40 is not called 'driver': `core_camera.getDriverCameraNameById(vehId)` returns `occupant.FL`; head yaw/pitch via `core_camera.getCameraDataById(id)['occupant.FL'].relativeYaw/Pitch`, set ~2 s after teleporting (a teleport resets it). This is why the v3.0.40 cockpit shots came out as chase views.
- BeamNG vehicles face -Y: `quatFromDir(-dir, up)` for `setPositionRotation`.
- The game caps an unfocused window at 30 fps (`fpsLimitBackgroundEnabled`, `fpsLimitBackground`=30): turn it off with `settings.setValue` before measuring FPS, restore settings.json afterwards.
- `startFreeroamByName(level, spawn, nil, false)` loads the level without a player car and leaves the main menu UI on top: spawn a car and `guihooks.trigger('ChangeState', {state='play'})`.
- Ground height by raycast from 2000 m hits tree canopies and roofs: use `core_terrain.getTerrainHeight` for eye-level cameras, and expect eye-level cameras near buildings to end up inside walls.
- In PowerShell, `"$var:text"` is parsed as a scoped variable: write `${var}:text`.
