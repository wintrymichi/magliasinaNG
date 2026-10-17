# magliaso_pura v3.1 – in-game test (2026-10-17)

BeamNG.drive 0.39.4, native Linux build, RTX 4070, 14 GB RAM, 2560 × 1440, Ultra preset (textures Normal, shadows High).
The game ran in a virtual KWin session (`kwin_wayland --virtual --xwayland`, no monitor), the same for both versions.

Zips: v3.0 = the `v3 build test` artifact of `main` (run 38921057526, md5 62e0a51a…); v3.1 = this branch, built from scratch
on the PC (`run_build.sh` + `build_level.py --finish`, package digest 19405e64…).

## Load and memory

| | v3.0 | v3.1 |
|---|---:|---:|
| load to world ready (warm cache) | 56 s | 78 s |
| peak RSS | 11.1 GB | 10.3 GB |

The first v3.1 load stopped with a Lua error: the game indexes the parking spots of `city.sites.json` by `oldId`
(fixed in `parking.py` and `fuel_stations.py`). The game then found 8 gas stations (`freeroam_facilities`), but the zip
had none of their pump areas (`fuel_stations.refuel_points` ran after the items file was written): no refuelling, and
while a car drives `gameplay/markerInteraction` raised "kdtreebox2d.lua:219 attempt to compare nil with number" every
frame (the NaN box of a station without pumps; found by the trailer session). Fixed in the code and in the built level
(104 pump areas and icons, `magliaso_pura_v3.1_fix.zip`); checked again in the game on 2026-10-17: 8 stations with 4-8 pumps each, the car stopped in a pump area of the
Eni of Magliaso Paese gets the *Refuel vehicle* prompt (gasoline, diesel), no kdtreebox2d error after 20 s of AI driving.
The FPS above were measured
without a car driving, so that error did not weigh on them.

## Frame rate

Free camera at fixed places and directions (`fps.lua`, frames counted over 5 s after a warm-up pass over every place):

| Place | v3.0 | v3.1 | change |
|---|---:|---:|---:|
| Magliaso junction | 101 | 102 | +1 % |
| Pura | 81 | 86 | +6 % |
| Magliaso Paese | 135 | 138 | +3 % |
| Agno lakeside | 70 | 78 | +12 % |
| Caslano | 133 | 136 | +2 % |
| Novaggio | 89 | 92 | +3 % |
| Bedigliora | 74 | 76 | +3 % |
| Arosio | 120 | 121 | +1 % |
| Ponte Tresa | 122 | 123 | +1 % |
| Breno | 79 | 82 | +4 % |
| over Magliaso and the lake | 59 | 65 | +12 % |
| over Novaggio | 67 | 73 | +9 % |
| cantonal road hairpin | 64 | 66 | +3 % |

Where the frames go (v3.0, on the real screen, hiding one group at a time): the whole forest 13–25 FPS (the far trees
alone 2–9), the steep skin 2–12, everything else (buildings, street life, vineyards, grass, lamps) within 1–3.

## Checked

- Eni Magliaso Paese with canopy, pumps and totem; white bays in its car park and at the FLP station Magliaso.
- Bedigliora: the church block with the windows of its houses (before: one windowless tower).
- Tyre tracks through the hairpin of the cantonal road; 33 roundabout rings with wear (Magliaso included, after the
  second fix: its AI ring runs 6–7 m off the ring OpenStreetMap maps).
- "ZONE 30" from the font at Magliaso Paese.
- Cockpit views on the main drives (ETK 800), chase views, landscapes: `beamng/verifica/screenshots/v3.1/`.

## Still open

- The Panetteria Magliasino: the street façade of its block (several houses of one survey object) still has no windows.
- The parked cars did not appear in the scripted test (`gameplay_parking.setupVehicles` from the test script); the spots
  load without error. To check with the game's traffic menu.
- "Holes in the walls from some angles": not found in the test views.
