All of Canton Ticino in BeamNG.drive: {ZONES} zones of 7.7 x 7.7 km (about 62 x 93 km) in one level, `ticino`, streamed
around the car. Terrain at 1.5 m and every building from swisstopo, the survey's roads, walls, pavements, bridges,
tunnels and motorways, forest, signs and traffic lights, built by the same pipeline as the Malcantone map. It is a
separate mod: the Malcantone map (latest release) stays as it is and both can be installed together.

**This is a pre-release.** It has been played on one PC so far: expect rough edges, and please report them in the
issues (with `app.log` or `beamng.log`).

## Requirements

- BeamNG.drive 0.40.x (Steam); Windows 10/11 for the app and the installer
- about {SIZE} of disk for the map, plus about 15 GB that the game fills with its cache as you drive
- 16 GB of RAM (32 GB recommended), a GPU with 8 GB of video memory or more

## Install

**With the app (recommended).** Download `app_ticino.zip`, unpack it anywhere and run `TicinoServer.exe` (nothing to
install). Choose where to keep the map, press Download, then Play. The app downloads only what changed, resumes an
interrupted download, checks every zip against its sha256, and keeps the map up to date. Play starts the Ticino
server beside BeamNG: the zone packs stay outside the game's mods and the server hands the game only what is around
the car, so the game starts in seconds.

**With the installer.** Download `installer_ticino.zip`, unpack it, close BeamNG and double-click `Install Ticino.bat`.
Then start with the **Start Ticino (BeamNG)** shortcut on the desktop. Run it again to update.

**By hand (any OS).** Put every `ticino_*.zip` of this release into `<BeamNG user folder>/mods`. The game then mounts all
of them at every start: the first start shows "not responding" for a minute or two before the menu. Wait, it is not
a crash.

The programs are not signed: Windows SmartScreen may warn the first time (More info > Run anyway).

## Files

| File | What |
|---|---|
| `app_ticino.zip` | Ticino Server, the Windows app: download, update, graphics settings, server, Play |
| `installer_ticino.zip` | the installer and the Start Ticino shortcut |
| `server_ticino.zip` | the Ticino server alone (the app and the installer fetch it themselves) |
| `helper_ticino.zip` | the streaming helper used when every zip is in mods |
| `ticino_base_*.zip` | the level: scene, roads, materials, the streaming mod |
| `ticino_<zone>_*.zip` | one per zone ({ZONES}) |

## Known issues

- The first minute after the spawn stutters while the first terrain window loads and the AI map is read.
- Driving fast: a few frames over 100 ms at every terrain move (about every 1.5 km).
- The first time a place is seen the game converts its textures: short stutters in a new area, not the second time.
- AI traffic works only near the spawn for now (the AI map far from the car has no heights yet); the log shows
  "Map node could not be set" for traffic lights far away.

## Credits and licence

Data: swisstopo (swissALTI3D, swissBUILDINGS3D, swissTLM3D), the official cadastral survey of Canton Ticino,
OpenStreetMap contributors (ODbL). The terrain swap, the runtime objects and the `.cdae` writer follow BeamNG.Earth
(TecnaGamer, MIT). Licence of the map: CC BY-NC 4.0 (commercial use: info@wintrymichi.ch). BeamNG.drive is a trademark
of BeamNG GmbH; this mod is not affiliated with BeamNG.
