**MagliasinaNG v3.1.1** for BeamNG.drive 0.40. First disable or remove any other `magliaso_pura_*.zip` in the mods folder (it is the same level). After a game update BeamNG switches every mod off: enable this one in the mod manager.

The fixes of the visual check of v3.1 (about 650 in-game shots along every road), now tested in the game. Same zip as the last nightly (sha256 `945d4ab5…a942ff9`).

## Tested in the game (25 October 2026)
BeamNG.drive 0.40.3, Windows 11, Direct3D 12, RTX 4070, 2560x1440 borderless, Ultra preset (texture quality Normal).
- **Load time: 152 s** (v3.1: 229 s): objects 44.7 s, physics 82.5 s, fade 24.4 s.
- **RAM:** working set peak 20.0 GB during the load, about 13.4 GB once loaded (commit 25.5 GB peak, 20.0 GB loaded). Plan on 16 GB of RAM plus a large page file, 32 GB is comfortable.
- **Video memory:** 6.5 GB for the game at its peak, 8.0 GB on the whole GPU (of 12 GB).
- **FPS** (8 s each): Magliaso roundabout 74, Via Golf underpass 89, Cantonale cut slope 61, woods road 83, Ponte Tresa bridge 61, 150 m over Magliaso 74.
- No missing materials any more (the island posts' `mp_island_reflector` and `mp_island_beacon` errors are gone).

## What is new
- **No hole after the 90° bend above the Magliaso hairpins:** a yard joining from below no longer pulls the edge of the uphill lane down (it was 0.75 m lower over 6.5 m; now a normal camber of about 10 cm).
- **No step after the Magliaso–Pura hairpin:** ramps instead of the 1.5–30 cm steps between two pieces of carriageway (steps over 8 cm 1,144 m → 222 m).
- **Cut slopes:** skin on the cuts beside the roads, no "teeth" at their foot, one look for earth and rock (sharper textures, no seams between triangles).
- **No pale patches** on the meadow banks: they are meadow with the game's grass again.
- **Grass in the woods** on the bare leaf litter away from the roads.
- **Ground materials:** steep yards are earth instead of asphalt, gravel and setts less white, no green roofs, no grey-blue concrete patches.
- **Walls of the Cantonale** with smoothed tops, no short stubs.
- **Traffic islands** out of the AI lanes; island posts with their materials.
- **Props off the roads** (432 pallets, benches, drums and skips), no bench on a rock face.
- **Bus stop paint** without the traced blobs.
- **Bridges:** no grass on the Ponte Tresa deck, the Via Golf rail deck in concrete; road ends joined to the ground.
- **The Tresa** continues where the border leaves it.

## Known issues
- **AI traffic is still broken** ([#83](https://github.com/wintrymichi/magliasinaNG/issues/83)): the traffic cars stall around the player's car and run into each other at the give-way junctions and islands. Drive without traffic for now. A single AI car on a route works, but it got stuck at the Magliaso roundabout once in this test.
- Some light grey blocks (wall ends) stand at the foot of the cuts on the Magliaso–Pura Cantonale.
- Via Golf underpass: the footways under the rail deck still stand above the road.
- The game warns that its bindless material slots are full (8,192); no licence plate template for the level.

## Screenshots (in the game)
![Caslano from the air](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-caslano-aerial.jpg)
![On the Cantonale to Agno](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-cantonale-agno.jpg)
![Above the hairpins, no hole](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-above-hairpins-no-hole.jpg)
![The lane after the 90 degree bend](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-lane-after-90-bend-fixed.jpg)
![After the hairpin, no step](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-hairpin-step-fixed.jpg)
![Cut slope beside the Cantonale](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-cut-slope.jpg)
![Grass in the woods](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-forest-grass.jpg)
![The hairpins from above](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-hairpins-from-above.jpg)
![Agno from the air](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-agno-aerial.jpg)
![Magliaso and the lake](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-magliaso-aerial.jpg)
![Magliaso](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-magliaso.jpg)
![Caslano lakefront](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-caslano-lakefront.jpg)
![Ponte Tresa bridge](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-ponte-tresa-bridge.jpg)
![Via Golf underpass](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-via-golf-underpass.jpg)
![Breno](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-breno.jpg)
![Pura](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v3.1.1/v311-driver-pura.jpg)
