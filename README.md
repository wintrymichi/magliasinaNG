<div align="center"> 

# Malcantone · BeamNG.drive

**The Malcantone (Canton Ticino, Switzerland) rebuilt at 1:1 scale for BeamNG.drive: 58.6 km² of villages, roads, trails, woods and lake between Ponte Tresa, Caslano, Agno, Bioggio, Gravesano, Arosio and Novaggio.**

![BeamNG.drive 0.40](https://img.shields.io/badge/BeamNG.drive-0.40-orange)
![Version](https://img.shields.io/badge/release-3.1-blue)
![Scale](https://img.shields.io/badge/scale-1%3A1-brightgreen)
![Area](https://img.shields.io/badge/area-58.6%20km%C2%B2-informational)
![Data](https://img.shields.io/badge/data-swisstopo%20%C2%B7%20MU%20TI%20%C2%B7%20OSM-lightgrey)
[![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey)](LICENSE)
[![Website](https://img.shields.io/badge/website-wintrymichi.ch-00549b)](https://wintrymichi.ch)

**[wintrymichi.ch](https://wintrymichi.ch)** · [Download v3.1](https://github.com/wintrymichi/magliasinaNG/releases/latest)

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/wintrymichii)

![Novaggio, Miglieglia and the Alto Malcantone in v3.0, in the game](beamng/verifica/screenshots/v3.0/overview-novaggio-miglieglia.jpg)

</div>

The Malcantone is the hilly corner of Ticino west of Lugano, between Lake Lugano and the Italian border. This mod turns about 58.6 km² of it into a drivable BeamNG.drive map: every real road and trail, every building, the woods and the lake, all at their real position and height.

Nothing is modelled by hand. A Python pipeline builds the whole map from open data: swisstopo (terrain, roads, buildings, aerial photos), the official cadastral survey of Canton Ticino, the Federal Register of Buildings and OpenStreetMap. Google Street View panoramas are used only as a **visual reference** (poses, measurements, comparisons). No Street View image is in the repository or in the map: everything you see in the photos (façades, shutters, signs, guardrails, walls) is redrawn with original textures. Since v3.0.40 open street-level photos (Mapillary, Panoramax, KartaView) also tell hedges from walls and show the village fountains; only positions and votes taken from them are kept, no photo.

**Contents:** [Quick start](#quick-start) · [Where to drive](#where-to-drive) · [Troubleshooting](#troubleshooting) · [At a glance](#at-a-glance) · [Gallery](#gallery) · [How the map is made](#how-the-map-is-made) · [Quality and verification](#quality-and-verification) · [Known limitations](#known-limitations) · [Repository layout](#repository-layout) · [Where to read more](#where-to-read-more) · [The panorama dataset](#the-panorama-dataset) · [Licence](#licence) · [Sources and licences](#sources-and-licences)

## Quick start

1. **Download** `magliaso_pura_v3.1.zip` from the [latest release](https://github.com/wintrymichi/magliasinaNG/releases/latest).
2. **Install it:** copy the zip, without unpacking it, to `Documents/BeamNG.drive/current/mods/` (or add it from the game's mod manager).
3. **Remove older versions** of the map from the same folder (any other `magliaso_pura_v*.zip`, also `magliaso_pura_v3.0.zip`). Every version uses the same level name, `magliaso_pura`, so two zips in the folder conflict.
4. **Enable it** in the game's mod manager if it shows as disabled: after an update of the game (0.39 → 0.40) BeamNG.drive switches every mod off.
5. **Play:** in the game choose *Freeroam* → *Malcantone - Magliaso, Pura and around*. You start at the Magliaso junction, at the foot of the cantonal road to Pura.

**What you need:** BeamNG.drive 0.40 and 16 GB of RAM. v3.1, measured in its in-game test (BeamNG.drive 0.40.3, Windows, Direct3D 12, RTX 4070): loads in about 229 s, 16.8 GB of RAM and 7.2 GB of video memory at its peak (about 12.5 GB of RAM once loaded); it is 7.9 GB unpacked, 1.3 GB more than v3.0.40. v3.0.40 is made for 0.40: the game moved its own textures that the map uses, and v3.0 shows missing textures there (on 0.39 keep v3.0). v3.0.40, measured in its in-game test (BeamNG.drive 0.40.1, Windows, Direct3D 12, RTX 4070): loads in about 230 s (0.40 empties its cache at every start, so every load is a first load), 6.7 GB of RAM and 5.8 GB of video memory at its peak, 8.8 GB of RAM with the traffic and parked cars on. v3.0, measured in its in-game test (native Linux build, RTX 4070, 14 GB RAM): loads in about 80 s with a warm cache, 10.3 GB of memory at its peak (the first v3.0 test build: 11.1 GB). v2.8 was tested on BeamNG.drive 0.39 (native Linux build) with an RTX 4070: the game used 6.4 GB of memory at its peak. Under Windows with DirectX 12 it needs much more (v2.7 measured about 12 GB): if the game stalls, start it with DirectX 11 (`-gfx dx11`).

**Loading time:** v2.8 loaded in about 130 s in the test. The first time is the slowest, because the game converts the map's shapes and tree pictures and keeps them in its cache.

## Where to drive

![Map of the playable area: roads, trails and villages](web/map.svg)

The map has 30 spawn points. Pick one in the game's spawn menu once the level is loaded.

| Spawn point | Where it puts you |
|---|---|
| `spawn_magliaso` (default) | the Magliaso junction, facing up the cantonal road to Pura |
| `spawn_mid` | halfway up the Magliaso–Pura cantonal road |
| `spawn_pura` | the top of the cantonal road, 160 m from Curio |
| one per village | `spawn_agno`, `spawn_aranno`, `spawn_arosio`, `spawn_astano`, `spawn_banco`, `spawn_bedigliora`, `spawn_bioggio`, `spawn_bosco_luganese`, `spawn_breno`, `spawn_cademario`, `spawn_caslano`, `spawn_cassina_d_agno`, `spawn_castelrotto`, `spawn_cimo`, `spawn_gravesano`, `spawn_magliaso_paese`, `spawn_manno`, `spawn_miglieglia`, `spawn_molinazzo_di_monteggio`, `spawn_monteggio`, `spawn_neggio`, `spawn_novaggio`, `spawn_ponte_tresa`, `spawn_pura_paese`, `spawn_purasca`, `spawn_sessa`, `spawn_vernate` |

A few drives to start with:

- **Magliaso → Pura**, the Strada Cantonale (3.7 km). This is where the project began, and the most detailed road on the map: markings, signs, street lamps and walls placed from the panoramas.
- **Along the lake**, from Magliaso on the Strada Regina to Agno, then through Bioggio and Manno to Gravesano (8.8 km).
- **The Penudria**, the hairpin pass from Gravesano up to Arosio (Stradón da Rós).
- **The Alto Malcantone loop** (new in v2.8): from Arosio over Mugena, Vezio, Fescoggia and Breno down to Miglieglia and Novaggio (9.6 km), then back down to the lake.
- **Caslano and Via Torrazza**, the narrow lakeside road to the Torrazza, and the border bridge at Ponte Tresa. Since v3.0.40 the whole of Caslano is in the map, with the golf course and the whole Monte Caslano, and the whole village of Arosio.
- **Time trials** (new in v3.0.40): four races with checkpoints and the game's leaderboard, started from the big map or at their start on the road: the hillclimbs Magliaso – Pura (3.7 km) and the Penudria Gravesano – Arosio (4.1 km), the hairpins Astano – Banco (3.0 km) and the village stage Novaggio – Miglieglia – Breno (5.6 km), each also the other way round.
- **The Monte Lema cable car** (new in v3.0.40), from Miglieglia up to the radar dome on the summit: to look at from the roads of the Alto Malcantone.
- **Off the asphalt:** every trail, mule track, forest road and stairway in the area has a solid surface. Since v2.4 gravel, dirt, setts and cobblestones also change the grip.

AI traffic works on the whole road network, with one-way streets, roundabouts and dual carriageways. Roads closed to traffic are avoided. Since v3.0.40 it follows the Swiss limits (20 to 80 km/h), stops at the STOP signs, gives way at the give-way lines and keeps one lane each way on two-way roads from 4.5 m. In v3.0.40 the traffic still stalls around the player's car: see [Known limitations](#known-limitations).

## Troubleshooting

| Problem | What to do |
|---|---|
| The game stalls after loading, or the whole PC lags | v3.0.40 needs 6.7 GB of RAM at its peak (8.8 GB with the traffic and parked cars on). Close the browser, Discord and other programs before loading it. |
| The level is missing from the Freeroam list, or loads the wrong version | Check that only one `magliaso_pura_v*.zip` is in the `mods` folder and that it is still zipped. |
| Missing textures on the stone walls and some plastic parts on BeamNG.drive 0.40 | That is v3.0 on 0.40: the game moved some of its own textures the map uses. Install v3.0.40. |
| White or dark grey squares among the far trees on BeamNG.drive 0.40 | That is v3.0 on 0.40: the game draws the far trees' pictures as squares when it makes them itself while you play. v3.0.40 ships them ready made. Install it. |
| The map is missing from the Freeroam list after updating the game | 0.40 switches every mod off after the update: enable the map in the mod manager. |
| The first load is slow | That is normal: the game converts the shapes once (v2.8 about 130 s in the test), then loads faster. |
| After updating, parts of the map still look like the old version | The game may still show shapes it converted for the old zip. Delete the `temp/levels/magliaso_pura/` folder in the game's user folder (the one that holds `mods`) and load the level again. |
| Low frame rate in meadows and gardens | The grass is the game's own groundcover: lower the vegetation quality in the game's graphics settings. |
| A road ends in the middle of nowhere | Some roads leave the modelled area and stop at its edge; beyond it there is only terrain. See [Known limitations](#known-limitations). |

Found something wrong on the map? Open an [issue](https://github.com/wintrymichi/magliasinaNG/issues) with the place (village and road) and, if you can, a screenshot.

## At a glance

| | |
|---|---|
| **Area** | about 58.6 km² (since v3.0.40 the whole of Caslano with Monte Caslano and the whole village of Arosio; 56 km² in v2.8 and v3.0, 52 km² up to v2.7), a 12.3 × 12.3 km terrain at 1.5 m (swissALTI3D LiDAR) |
| **Roads and trails** | 228 km of roads and 337 km of trails, mule tracks and stairways, all drivable; 167 bridges; since v2.2 also the pass above Gravesano to Arosio, the Ponte Tresa–Caslano cantonal road and Via Torrazza; since v2.4 asphalt, gravel, dirt, setts and cobblestones according to OpenStreetMap; since v2.7 dirt and gravel tracks flush with the ground |
| **Buildings** | 12,792 buildings (swissBUILDINGS3D and the official survey) with façades, windows, shutters, doors, shop windows, plinths and chimneys |
| **Guardrails** | 2.0 km on the Magliaso–Pura cantonal road and, since v2.2, another 9.7 km on the rest of the network, wherever the panoramas show them |
| **Vegetation** | every tree measured in the surface model: about 161,000 trees and shrubs with the game's models near the roads, and since v2.7 another 201,634 lighter drawn trees on the slopes further away; kept out of the roads' clearance envelope. Since v3.0 every tree takes the model closest to its real height (no shrunk models), and the woods outside the cadastral survey (the Collina d'Oro, the Italian side, the ridges around) are planted from ESA WorldCover: about 330,000 more far trees on 64 km². Grass and flowers with the game's own textures (v2.6), palms in lakeside gardens, vines on their wires in 475 vineyards |
| **Water** | Lake Lugano and, since v2.4, the rivers (Magliasina, Vedeggio, Tresa and the other watercourses surveyed as areas) |
| **Markings** | detected in the 10 cm orthophoto and, since v2.7, redrawn as they are painted in Switzerland: 4,240 strips (62.7 km), smooth lines, regular dashes, standard yellow pedestrian crossings |
| **Road signs** | since v2.7 Swiss signs on the whole network (286 new: crossings, roundabouts, one-way streets, zones, speed limits, village limits, signs mapped in OpenStreetMap), plus STOP and give-way signs, bus stops and the cantonal road's plates |
| **AI traffic** | complete network with one-way streets, roundabouts and dual carriageways; since v3.0.40 welded at the junctions (235 of 242 km in one network), Swiss speed limits, STOP and give way, a lane each way from 4.5 m, European cars |
| **Landmarks** (v3.0.40) | the churches, chapels and bell towers with bell chambers and bells, clock faces lit at night, crosses, portals, rose windows and stone quoins; the Monte Lema cable car with its pylons and cabins, the radar dome on the summit |
| **Time trials** (v3.0.40) | four races with checkpoints and the game's leaderboard, each both ways |
| **Sounds** (v3.0.40) | the game's water sounds near the roads: rivers, streams and the lake shore, 174 places |
| **Villages** (v3.0) | shop fronts with signs and awnings on the shops, bars and restaurants OpenStreetMap records, 8 petrol stations with canopy, pumps and price totem, registered as the game's gas stations, 11,069 parking spots with white bays for the game's parked cars, shelters with benches at the bus stops, about 13,000 props of street life (bins, hydrants, café terraces, planters, mirrors, letter boxes, pallets), flower boxes and woodpiles at the houses |
| **Spawn points** | 30, one in every village |

## Gallery

### New in v3.1: bridges, roofs, slopes and woods

> **Released on 23 October 2026, tested in the game on 24 October 2026.** The screenshots below are from that test. **The AI traffic is still broken** ([#83](https://github.com/wintrymichi/magliasinaNG/issues/83)): see the known limitations.

v3.1 rebuilds the Magliaso bridge from the survey, gives every roof its walls or posts, and adds detail to the roofs, the road cuts and the woods. The full list is in [`CHANGELOG.md`](CHANGELOG.md).

**In-game test:** BeamNG.drive 0.40.3 on Windows, Direct3D 12, RTX 4070, at 2048 × 1152, Ultra preset with normal texture quality. The map loads in about 229 seconds, uses 16.8 GB of RAM (working set, during the load; about 12.5 GB once loaded) and 7.2 GB of video memory at peak, and runs at 54–78 FPS at six places (the Magliaso roundabout, the Via Golf underpass, a Cantonale cut slope, a woods road, the Ponte Tresa bridge, 150 m over Magliaso; v3.0.40: 230 s, 6.7 GB, 5.8 GB, 62–134 FPS at 13 places). The level is 7.9 GB unpacked (+1.3 GB, mostly the cut slopes) and the zip 1.5 GB. At night 2,113 lamp lights light the road between the lamps. The time trials and the AI traffic were not part of this test. The complete test report is in [`beamng/verifica/v3.1/ingame_test_report.md`](beamng/verifica/v3.1/ingame_test_report.md).

#### What changed

- **The Magliaso bridge rebuilt from the survey.** The Via Cantonale bridge over the Magliasina at the Magliaso roundabout is one 25 m deck taken from the outline of the cadastral survey, its height fitted to the swissSURFACE3D lidar, instead of two narrow strips with the river showing between them and parapets in the middle of the road (issues [#73](https://github.com/wintrymichi/magliasinaNG/issues/73), [#78](https://github.com/wintrymichi/magliasinaNG/issues/78)). The channelled river banks are stone instead of grey asphalt ramps.
- **Bridges as wide as the road.** About 20 bridges were narrower than the road on both sides of them. They now take the width of the surveyed bridge, or of the road at their ends; the Ponte Tresa border bridge is 11 m wide. The steps between deck and road at the Magliaso bridges are gone.
- **The Via Golf underpass** between Caslano and Magliaso. The road ran into the FLP embankment from both sides; it now passes under the tracks (its two footways still stand about 2 m above the road there, see the known limitations).
- **No more floating roofs.** 469 roofs of swissBUILDINGS3D hung in the air without walls (canopies, covered car parks, boat houses, sheds): now none. The cadastral survey decides what each one is. Shelters stand on posts kept off roads and tracks, houses and low sheds get walls, and about 4,300 posts hold up porches and lean-tos.
- **Detailed roofs.** Eaves with a rim of tile heads, fascia boards, ridge caps, and new textures for coppi, flat tiles and metal sheet.
- **Rock cuts along the roads.** Where a road is cut into the hill the face is rock down to the asphalt instead of green earth, with a brown stepped strip at its foot and about 90,000 bushes on the steep faces.
- **Wilder undergrowth.** Ferns, shrubs, deadwood and fallen trunks under the trees, denser at the wood edges and in clearings.
- **Railway.** The ballast reaches up to the sleepers, and between Caslano and Ponte Tresa the rails no longer climb a ramp of sleepers into the retaining wall.
- **Walls.** Fewer saw-tooth tops (in the game some walls of the Magliaso–Pura Cantonale, the hairpin among them, still have them), and a lid over the dark grooves where two walls stood a few centimetres apart (1,100 gaps, 8.6 km).
- **Street lamps that light the road at night.** Each lamp lit only a small pool under itself and left the road between lamps dark. They now cast a warm cone downwards, as in the game's Italy level.
- **Time trials.** The cars start facing up the route.
- **Pavements on kerbs.** Pavements were flush with the road everywhere; they now stand on 12 cm kerbs, lowered at entrances and pedestrian crossings.
- **Roundabouts** with a raised green middle on its kerb inside a mountable ring of setts.
- **Less uniform asphalt.** Newer and older stretches, patches and joints read from the 2024 orthophoto; cracks only where the road is old.
- **19 buildings closer to the real ones** along the main roads: plaster colours and details from open street photos.
- **The forest floor as a mosaic:** ragged wood edges, thickets on sunny slopes, bare leaf litter under the beeches, rock outcrops, ferns and stones on the wooded banks.
- **Bus stops** with their yellow zigzags, BUS letters and yellow lines as the orthophoto shows them, and the crossings the rules had missed.
- **Traffic islands:** the keep-right poles stand in the black and yellow sleeve of the Swiss island posts.
- **Bus shelters** off the carriageway (6 stood on it), squared to the road beside their stop.
- **Also:** the Caslano slipway stops at the lake shore instead of going on under the water ([#84](https://github.com/wintrymichi/magliasinaNG/issues/84)); the strip of Arosio that the OpenStreetMap extract did not cover; the far trees' pictures for the distance are made by the build itself (v3.0.40 got them by a patch of its zip).

#### At the wheel

*Screenshots from the driver's seat of an ETK 800 in the right-hand lane.*

| | |
|---|---|
| ![Crossing the Magliaso bridge](beamng/verifica/screenshots/v3.1/driver-magliaso-bridge.jpg)<br>*Over the Magliasina at the Magliaso roundabout, one 25 m deck* | ![The Ponte Tresa border bridge](beamng/verifica/screenshots/v3.1/driver-ponte-tresa-bridge.jpg)<br>*The Ponte Tresa border bridge, now 11 m wide* |
| ![The Via Golf underpass](beamng/verifica/screenshots/v3.1/driver-via-golf-underpass.jpg)<br>*Via Golf under the FLP between Caslano and Magliaso* | ![A rock cut beside the road](beamng/verifica/screenshots/v3.1/driver-cut-slope.jpg)<br>*Rock cut down to the asphalt beside the road* |
| ![A road through the woods](beamng/verifica/screenshots/v3.1/driver-forest-undergrowth.jpg)<br>*A road through the woods, ferns and deadwood under the trees* | ![The wall at the Magliaso–Pura hairpin](beamng/verifica/screenshots/v3.1/driver-hairpin-wall.jpg)<br>*The Magliaso–Pura hairpin wall: its top is still saw-toothed in the game* |
| ![The road lit at night](beamng/verifica/screenshots/v3.1/driver-night-lamps.jpg)<br>*The road lit between the lamps at night* | |

#### Bridges and the underpass

| | |
|---|---|
| ![The Magliaso bridge from above](beamng/verifica/screenshots/v3.1/bridge-magliaso-above.jpg)<br>*The Magliaso bridge and its stone river banks* | ![A bridge as wide as the road](beamng/verifica/screenshots/v3.1/bridges-wide.jpg)<br>*A bridge as wide as the road* |
| ![The Via Golf underpass from the side](beamng/verifica/screenshots/v3.1/underpass-via-golf-side.jpg)<br>*The Via Golf underpass and the FLP above it* | ![Magliaso from above](beamng/verifica/screenshots/v3.1/overview-magliaso.jpg)<br>*Magliaso, the lake and the Magliasina from above* |

#### Roofs

| | |
|---|---|
| ![A canopy at Caslano](beamng/verifica/screenshots/v3.1/roofs-caslano-canopy.jpg)<br>*A large canopy on its posts beside the FLP at Caslano* | ![A covered car park](beamng/verifica/screenshots/v3.1/roofs-covered-car-park.jpg)<br>*A covered car park on posts* |
| ![Posts under porches](beamng/verifica/screenshots/v3.1/roofs-porch-posts.jpg)<br>*Posts under porches and lean-tos* | ![Coppi roofs in a village core](beamng/verifica/screenshots/v3.1/roofs-coppi-village.jpg)<br>*Coppi roofs with ridge caps and tile heads at the eaves* |

#### Slopes, woods and railway

| | |
|---|---|
| ![Bushes on the cut slopes](beamng/verifica/screenshots/v3.1/cut-slopes-bushes.jpg)<br>*Bushes on the steep cut faces* | ![Undergrowth at a wood edge](beamng/verifica/screenshots/v3.1/undergrowth-wood-edge.jpg)<br>*Undergrowth at a wood edge* |
| ![A clearing with fallen trunks](beamng/verifica/screenshots/v3.1/undergrowth-clearing.jpg)<br>*Ferns, shrubs and fallen trunks in a clearing* | ![Ballast at Caslano](beamng/verifica/screenshots/v3.1/railway-caslano-ballast.jpg)<br>*Ballast up to the sleepers at Caslano* |
| ![The rails beside the wall](beamng/verifica/screenshots/v3.1/railway-wall-caslano-tresa.jpg)<br>*The rails beside the wall between Caslano and Ponte Tresa* | ![A village at night](beamng/verifica/screenshots/v3.1/lamps-night-village.jpg)<br>*A village at night under the new street lamps* |

<details>
<summary>3D renders of the test build, v3.0.40 and v3.1 side by side (not in-game)</summary>

| | |
|---|---|
| ![Magliasina bridge](beamng/verifica/v3.1/render/01_ponte_magliaso.jpg)<br>*The Magliaso bridge* | ![Bridges as wide as the road](beamng/verifica/v3.1/render/02_ponti_allargati.jpg)<br>*Bridges as wide as the road* |
| ![No steps at the Magliaso bridges](beamng/verifica/v3.1/render/03_ponti_scalini.jpg)<br>*No steps at the Magliaso bridges* | ![Via Golf underpass](beamng/verifica/v3.1/render/04_sottopassaggio_via_golf.jpg)<br>*Via Golf underpass* |
| ![Caslano station canopy](beamng/verifica/v3.1/render/05_tettoia_caslano.jpg)<br>*Caslano station canopy* | ![Covered car park](beamng/verifica/v3.1/render/06_parcheggio_coperto.jpg)<br>*Covered car park* |
| ![Posts under porches](beamng/verifica/v3.1/render/07_tettoie_case.jpg)<br>*Posts under porches* | ![Coppi roofs](beamng/verifica/v3.1/render/08_tetti_coppi.jpg)<br>*Coppi roofs* |
| ![Magliaso roofs](beamng/verifica/v3.1/render/09_tetti_magliaso.jpg)<br>*Magliaso roofs* | ![Cut slope beside the Cantonale](beamng/verifica/v3.1/render/10_scarpate_cantonale.jpg)<br>*Cut slope beside the Cantonale* |
| ![Bushes on the cut slopes](beamng/verifica/v3.1/render/11_scarpate_cespugli.jpg)<br>*Bushes on the cut slopes* | ![Undergrowth at a wood edge](beamng/verifica/v3.1/render/12_sottobosco_margine.jpg)<br>*Undergrowth at a wood edge* |
| ![Rails at Caslano](beamng/verifica/v3.1/render/13_binari_caslano.jpg)<br>*Rails at Caslano* | ![Wall at the hairpin](beamng/verifica/v3.1/render/14_muro_tornante.jpg)<br>*Wall at the hairpin* |
| ![Street lamps at night](beamng/verifica/v3.1/render/15_lampioni_notte.jpg)<br>*Street lamps at night* | |

</details>

#### Coming next

- **AI traffic that flows.** The spawn points off the carriageway, a test with the player driving, and the give-way junctions where cars ran into each other in the v3.0.40 test (see *Known limitations*).
- **A Swiss licence plate** for the cars of the map, instead of the game's default.
- The pale bands on some wall tops and the pale patches in the grass at Agno ([#73](https://github.com/wintrymichi/magliasinaNG/issues/73)), the windowless street façade of the Panetteria Magliasino ([#74](https://github.com/wintrymichi/magliasinaNG/issues/74)), the palm at Magliaso and the ochre of Bedigliora ([#77](https://github.com/wintrymichi/magliasinaNG/issues/77)), the ground against the walls ([#78](https://github.com/wintrymichi/magliasinaNG/issues/78)).
- **Windows and doors measured from the open street photos**, once the detector finds more than about half of them; and the roofs the photos measured off by 0.5–2.9 m, once they are checked one by one.

### New in v3.0.40: the map on BeamNG.drive 0.40

v3.0.40 adapts the map to BeamNG.drive 0.40 and includes the fixes and additions since v3.0. The full list is in [`CHANGELOG.md`](CHANGELOG.md).

**In-game test:** BeamNG.drive 0.40.1 on Windows, Direct3D 12, RTX 4070, at 2560 × 1440. The map loads in about 230 seconds, uses 6.7 GB of RAM and 5.8 GB of video memory at peak, and runs at 62–134 FPS at 13 fixed locations. The test found no missing textures and no squares among the distant trees. AI traffic still stalls; see [Known limitations](#known-limitations). The complete test report is in [`beamng/verifica/v3.0.40/ingame_test_report.md`](beamng/verifica/v3.0.40/ingame_test_report.md).

#### What changed

- **Compatibility with BeamNG.drive 0.40.** The game moved 73 files used by the map, mostly textures from Italy, into new folders. The map now points to the new paths, fixing missing textures on stone walls and some plastic parts. Another 192 duplicate textures have been consolidated, reducing the files the game needs to convert and cache.
- **Road wear without bright patches or gaps.** Tyre tracks, patches and cracked stretches now receive shadows from cars, trees and walls and continue through junctions, lay-bys and bridges (the track coverage grew from 270 to 325 km). Bare road showing through the wear was reduced from 1–5% of its area to 0.06%.
- **Traffic follows Swiss rules.** The AI roads are connected at junctions (235 of 242 km in one network) and have no abrupt width changes. Speed limits range from 20 to 80 km/h; two-way roads at least 4.5 m wide get one lane each way; traffic responds to STOP and give-way signs, with European cars. Traffic can still stall around the player's car. Where a footpath meets a road, the road now remains level to the edge of the carriageway.
- **Caslano and Arosio are complete.** The map includes Caslano's golf course, lakeside up to Torrazza and all of Monte Caslano, as well as the whole village of Arosio. The area grows from 56.0 to 58.6 km² ([issue #16](https://github.com/wintrymichi/magliasinaNG/issues/16)).
- **Churches and bell towers.** Added recognisable bell chambers, bells, illuminated clock faces, crosses, portals, rose windows, arched windows, granite plinths and stone quoins. Details include Novaggio's round towers, Agno's lantern tower and towers embedded in Bedigliora's village blocks. Bare-stone churches are represented as stone where the photos show it ([issue #11](https://github.com/wintrymichi/magliasinaNG/issues/11)).
- **The Monte Lema cable car.** The route from Miglieglia has ropes, lattice pylons and blue and green cabins; the summit has its white radar dome and mast.
- **Four time trials.** Missions with checkpoints and the game's leaderboard: Magliaso–Pura (3.7 km, +238 m), Gravesano–Arosio over the Penudria (4.1 km, +491 m), Astano–Banco (3.0 km) and Novaggio–Miglieglia–Breno (5.6 km). Every route can also be driven in reverse. Up to v3.0 the map was free roam only.
- **Water sounds.** The game's water audio is placed near rivers (Magliasina, Tresa and Vedeggio), streams crossing roads and the lakeshore, at 174 locations. BeamNG.drive 0.40 does not provide church bells, birds or crickets.
- **Walls without holes** ([issue #76](https://github.com/wintrymichi/magliasinaNG/issues/76)). Cantonal-road walls are closed at their ends and backs; their feet reach beneath the asphalt and steep ground, and adjoining pieces of different heights no longer pull their tops down.
- **Smoother roads.** Fixed the large step after the hairpin below Astano towards Banco, steps on narrow roads and junctions in Vezio and Arosio, and bridge approaches. Trees no longer stand in the road at Vezio.
- **Direction signs at main-road junctions.** Signs point to the villages reached first, positioned before the junction on the side they indicate.
- **Hedges and fountains from open street photos.** Mapillary, Panoramax and KartaView images help distinguish hedges from walls and fences and locate village fountains; only positions and derived votes are kept, not the images.
- **A clearer level-list entry.** The in-game name is shorter, in English, and uses the aerial view over Novaggio as its preview.

#### On the roads

*Screenshots show an ETK 800 from the chase camera in the right-hand lane. The test's driver's-seat camera did not activate.*

| | |
|---|---|
| ![Stone wall and tyre tracks in the shade on the road to Pura](beamng/verifica/screenshots/v3.0.40/road-pura-wall-wear.jpg)<br>*Stone wall and tyre tracks in the shade on the road to Pura* | ![Tyre tracks and shaded patches between Novaggio and Miglieglia](beamng/verifica/screenshots/v3.0.40/road-novaggio-miglieglia-wear.jpg)<br>*Novaggio–Miglieglia: tyre tracks and shaded patches* |
| ![Cantonal road between Magliaso and Pura](beamng/verifica/screenshots/v3.0.40/road-cantonale-pura.jpg)<br>*Cantonal road between Magliaso and Pura* | ![Astano–Banco along a high stone wall](beamng/verifica/screenshots/v3.0.40/road-astano-banco-wall.jpg)<br>*Astano–Banco along a high stone wall* |
| ![Roadside wall on the cantonal road to Pura, closed at the back and ends](beamng/verifica/screenshots/v3.0.40/wall-cantonale-pura.jpg)<br>*Roadside wall on the cantonal road to Pura, closed at the back and ends (issue #76)* | ![Caslano, west side of Monte Caslano](beamng/verifica/screenshots/v3.0.40/road-caslano.jpg)<br>*Caslano, west side of Monte Caslano* |
| ![Arosio village, complete since v3.0.40](beamng/verifica/screenshots/v3.0.40/road-arosio.jpg)<br>*Arosio village, complete since v3.0.40* | ![Main road through Novaggio](beamng/verifica/screenshots/v3.0.40/road-novaggio.jpg)<br>*Main road through Novaggio* |
| ![Magliaso towards the cantonal-road junction](beamng/verifica/screenshots/v3.0.40/road-magliaso.jpg)<br>*Magliaso towards the cantonal-road junction* | |
#### Time trials

*The screenshots show the car positioned on each route. The races were not driven as part of this test.*

| | |
|---|---|
| ![Start of the Magliaso–Pura hillclimb at the Magliaso roundabout](beamng/verifica/screenshots/v3.0.40/race-magliaso-pura-start.jpg)<br>*Start of the Magliaso–Pura hillclimb at the roundabout* | ![The Penudria, Gravesano–Arosio](beamng/verifica/screenshots/v3.0.40/race-penudria.jpg)<br>*The Penudria, Gravesano–Arosio* |
| ![Hairpins on the Astano–Banco route](beamng/verifica/screenshots/v3.0.40/race-astano-banco.jpg)<br>*Hairpins on the Astano–Banco route* | ![Village stage Novaggio–Miglieglia–Breno](beamng/verifica/screenshots/v3.0.40/race-novaggio-breno.jpg)<br>*Village stage Novaggio–Miglieglia–Breno* |

#### Churches, cable car and views from above

| | |
|---|---|
| ![Church of Agno and its bell tower, viewed from the road](beamng/verifica/screenshots/v3.0.40/church-agno.jpg)<br>*Church of Agno and its bell tower, viewed from the road* | ![Miglieglia from above, with a Monte Lema cable-car pylon](beamng/verifica/screenshots/v3.0.40/lema-cable-car-miglieglia.jpg)<br>*Miglieglia from above, with a Monte Lema cable-car pylon* |
| ![Slopes above Novaggio on BeamNG 0.40, with no squares among distant trees](beamng/verifica/screenshots/v3.0.40/overview-far-trees-040.jpg)<br>*Slopes above Novaggio: no squares among distant trees* | ![Monte Caslano and the lake, with the whole area present since v3.0.40](beamng/verifica/screenshots/v3.0.40/overview-monte-caslano.jpg)<br>*Monte Caslano and the lake* |
| ![Complete village of Arosio viewed from above](beamng/verifica/screenshots/v3.0.40/overview-arosio.jpg)<br>*Arosio viewed from above* |
### v3.0 in the game: the review round

> v3.0 was released on 17 October 2026 for BeamNG.drive 0.39. After the first v3.0 test build (the `v3 build test` workflow) came a review round with the fixes and additions below. It was built on a PC from scratch and **tested in the game** (BeamNG.drive 0.39.4, native Linux, RTX 4070, 2560 × 1440, Ultra): the frame rate at 13 fixed places before and after, and the screenshots below. Full test in [`beamng/verifica/v3.0/ingame_test_report.md`](beamng/verifica/v3.0/ingame_test_report.md), all screenshots in [`beamng/verifica/screenshots/v3.0/`](beamng/verifica/screenshots/v3.0).

**What changed**

- **More frames, same look.** The smooth skin of the steep banks (18 million triangles, drawn whole at every distance in the first test build) now has three detail levels: the round skin near the camera, coarser planes farther out, nothing beyond 3 km, where the terrain under it looks the same; the far levels cast no shadow. +1 % to +12 % FPS at the same places (table below), and 0.8 GB less memory at the peak.
- **Tyre tracks through the roundabouts and the tight bends.** The wear was cut on purpose 10 m around every roundabout, and dropped in the hairpins where the measured width of the road jumped. Now the ring of 33 roundabouts carries its tracks all round, and the width is measured along the asphalt (the cross fall of a hairpin no longer ends it).
- **The Eni of Magliaso Paese**, by the FLP stop, now stands with its canopy, pumps and totem: OpenStreetMap maps it only as a charging point. Any charging point run by a fuel company marks a station where the survey has its canopy.
- **Refuelling at the pumps.** The 8 petrol stations of the map are registered as gas stations of the game, with a refuelling area and icon on both sides of every dispenser (the first review build had the stations without their pump areas: no refuelling, and an error every frame while driving; fixed and checked in the game: the car stopped at a pump of the Eni of Magliaso gets the game's *Refuel vehicle* prompt, petrol and diesel, and no error while driving).
- **Parked cars and Swiss parking bays.** 11,069 parking spots in 469 car parks of OpenStreetMap, where the game's traffic puts its parked cars, and the bays painted white as in Switzerland (6,474 lines).
- **Bus shelters.** 40 more bus stops have the game's shelter with its bench, where there is room beside the road.
- **No more windowless blocks.** In Bedigliora the church tower, the church and the houses down the slope are one object of the survey classed as a tower, and they were drawn as one tower without a window; offices and shop blocks of the register were drawn as sheds. Both now have their windows.
- **One wall instead of two.** The survey often draws a wall as its two faces, and every line was a wall: two low walls side by side along many roads (2,290 pairs, 55 km). They are now one wall of the right thickness.
- **Road lettering.** "ZONE 30" and "STOP" are drawn from a bold font instead of thin angular strokes; the car dealers' flags read the right way.

**Frame rate, first test build → v3.0** (free camera at the same place and direction, 5 s average, textures loaded):

| Place | test build | v3.0 | | Place | test build | v3.0 |
|---|---:|---:|---|---|---:|---:|
| Magliaso junction | 101 | 102 | | Breno | 79 | 82 |
| Pura | 81 | 86 | | Arosio | 120 | 121 |
| Magliaso Paese | 135 | 138 | | Ponte Tresa | 122 | 123 |
| Agno, lakeside | 70 | **78** | | Cantonal road, hairpin | 64 | 66 |
| Caslano | 133 | 136 | | Over Magliaso and the lake | 59 | **65** |
| Novaggio | 89 | 92 | | Over Novaggio | 67 | **73** |
| Bedigliora | 74 | 76 | | **Average of the 13** | **92** | **95** |

Most of the remaining cost is the trees near the roads (the game's own models, the same as in v2.8): hiding the whole forest gives 13–25 FPS more. They are left as they are, so the woods keep their look.

| | |
|---|---|
| ![The Eni of Magliaso Paese](beamng/verifica/screenshots/v3.0/new-eni-magliaso-paese.jpg)<br>*The Eni of Magliaso Paese, by the FLP stop (a parody brand)* | ![Parking bays and the petrol station](beamng/verifica/screenshots/v3.0/new-eni-and-parking-bays.jpg)<br>*White parking bays in front of it* |
| ![Parking bays at the FLP station of Magliaso](beamng/verifica/screenshots/v3.0/new-parking-bays-flp-magliaso.jpg)<br>*The park and ride of the FLP station Magliaso* | ![Tyre tracks through the hairpin](beamng/verifica/screenshots/v3.0/new-wear-hairpin.jpg)<br>*Tyre tracks through the hairpin of the cantonal road* |

**From the driver's seat**

| | |
|---|---|
| ![Cantonal road Magliaso–Pura, guard rail](beamng/verifica/screenshots/v3.0/cockpit-cantonale-guardrail.jpg)<br>*Cantonal road Magliaso–Pura, along the guard rail* | ![Cantonal road down to Magliaso](beamng/verifica/screenshots/v3.0/cockpit-cantonale-down-to-magliaso.jpg)<br>*Down the cantonal road towards Magliaso* |
| ![Cantonal road, stone wall](beamng/verifica/screenshots/v3.0/cockpit-cantonale-stone-wall.jpg)<br>*Halfway up the cantonal road, stone wall* | ![The roundabout of Magliaso](beamng/verifica/screenshots/v3.0/cockpit-roundabout-magliaso.jpg)<br>*Into the roundabout of Magliaso* |
| ![The roundabout of Magliaso, other way](beamng/verifica/screenshots/v3.0/cockpit-roundabout-magliaso-2.jpg)<br>*The roundabout of Magliaso, the other way* | ![Agno along the lake](beamng/verifica/screenshots/v3.0/cockpit-agno-lakeside.jpg)<br>*Agno along the lake* |
| ![The Penudria](beamng/verifica/screenshots/v3.0/cockpit-penudria.jpg)<br>*The Penudria, Gravesano – Arosio* | ![Miglieglia – Novaggio](beamng/verifica/screenshots/v3.0/cockpit-miglieglia-novaggio.jpg)<br>*Miglieglia – Novaggio* |
| ![Novaggio – Miglieglia](beamng/verifica/screenshots/v3.0/cockpit-novaggio-miglieglia.jpg)<br>*Novaggio – Miglieglia, tyre tracks in the bend* | ![Caslano](beamng/verifica/screenshots/v3.0/cockpit-caslano.jpg)<br>*Caslano* |
| ![Behind the car on the cantonal road](beamng/verifica/screenshots/v3.0/chase-cantonale.jpg)<br>*Behind the car on the cantonal road* | ![Tyre tracks through the hairpin, the other way](beamng/verifica/screenshots/v3.0/new-wear-hairpin-2.jpg)<br>*The same hairpin from the valley side* |

**Passages and landscapes**

| | |
|---|---|
| ![Magliaso and the lake](beamng/verifica/screenshots/v3.0/overview-magliaso-lake.jpg)<br>*Magliaso, the Magliasina and the lake* | ![Agno and the lake](beamng/verifica/screenshots/v3.0/overview-agno-lake.jpg)<br>*Agno and the Vedeggio plain* |
| ![The hairpins of the cantonal road](beamng/verifica/screenshots/v3.0/overview-cantonale-hairpins.jpg)<br>*The hairpins of the cantonal road above Magliaso* | ![Magliaso Paese](beamng/verifica/screenshots/v3.0/overview-magliaso-paese.jpg)<br>*Magliaso Paese* |
| ![Pura](beamng/verifica/screenshots/v3.0/overview-pura.jpg)<br>*Pura* | ![Novaggio and Miglieglia](beamng/verifica/screenshots/v3.0/overview-novaggio-miglieglia.jpg)<br>*Novaggio, Miglieglia and the Alto Malcantone* |
| ![Caslano and the lake](beamng/verifica/screenshots/v3.0/overview-caslano-lake.jpg)<br>*Caslano and the Torrazza* | ![Ponte Tresa](beamng/verifica/screenshots/v3.0/overview-ponte-tresa.jpg)<br>*Ponte Tresa and the border bridge* |

### New in v3.0 (everything since v2.8)

> The whole of v3.0 compared with v2.8; its in-game test and screenshots are in the section above. Full notes in [`beamng/RELEASE_v3.0.md`](beamng/RELEASE_v3.0.md) and [`CHANGELOG.md`](CHANGELOG.md).

v3.0 polishes the v2.8 map up close and from afar, after the feedback that it looked "blocky, smeary, lacking detail". Same area, roads and buildings.

- **Trees, not shrubs.** No tree model is shrunk below 0.75 of its size any more, each tree takes the model closest to its real height, and false tops under taller crowns are dropped.
- **Woods on every mountain.** The forest of ESA WorldCover 2021 is planted as far trees on the whole terrain block outside the cadastral survey, and the terrain and the distant backdrop take its land cover.
- **Ground coloured from the aerial photo**, with detail out to 160 m and a material of its own for the steep banks.
- **The game's own look.** The asphalt, stone and concrete walls, parapets and cobbles of the game's Italy level, with the wear of the traffic: tyre tracks in every lane, lighter and darker patches, cracked stretches, dusty edges.
- **Smooth curves.** Roads, pavements, yards and walls follow curves through the surveyed points instead of straight pieces a few metres long.
- **Road paint and signs by the Swiss rules.** Markings laid from the road geometry by the Swiss standard (give-way lines at every roundabout entry, edge lines from the real edge of the asphalt), raised traffic islands on kerbs with their keep-right sign, direction signs at the roundabout exits.
- **Villages lived in.** Shop fronts with signs and awnings, petrol stations, street life (bins, hydrants, café terraces, planters, convex mirrors, letter boxes, pallets and drums), flower boxes at the windows and woodpiles at the stone houses. The shop names are parodies and the small props stand where rules put them, not at their real places.
- **Vineyards** with the vines on their wires, in two detail levels.
- **Steep banks along the roads** drawn as a smooth textured skin over the terrain, joined smoothly to the ground above and below; a road 1–3 m over the ground stands on an embankment instead of a vertical face of asphalt.
- **Walls, bridges, rivers and rails.** Wall feet under the ground, fences laid once, two road bridges side by side joined into one, river banks eased instead of a row of terrain steps, rails on a smooth line, the ground along walls and beside the railway on the lake without the terrain teeth of v2.8, gutters and downpipes only where a roof has a wall under it.

### New in v2.8

> In-game screenshots of the released v2.8 zip (BeamNG.drive 0.39, native Linux, RTX 4070): from the driver's seat, behind the car and from the air, on the cantonal road with the game's guard rails and on the new road Arosio – Mugena – Vezio – Breno – Miglieglia – Novaggio. All 15 in [`beamng/verifica/screenshots/v2.8/`](beamng/verifica/screenshots/v2.8), the test in [`beamng/verifica/v2.8/ingame_test_report.md`](beamng/verifica/v2.8/ingame_test_report.md).

| | |
|---|---|
| ![Driver's view: the cantonal road Magliaso–Pura with its guard rail](beamng/verifica/screenshots/v2.8/driver-cantonale-magliaso-pura-1.jpg)<br>*Driver's view: the cantonal road Magliaso–Pura with its guard rail* | ![Driver's view: the cantonal road, guard rail along the bend](beamng/verifica/screenshots/v2.8/driver-cantonale-magliaso-pura-2.jpg)<br>*Driver's view: the cantonal road, guard rail along the bend* |
| ![Driver's view: the new road Miglieglia–Novaggio, stone wall](beamng/verifica/screenshots/v2.8/driver-miglieglia-novaggio-stone-wall.jpg)<br>*Driver's view: the new road Miglieglia–Novaggio, stone wall* | ![The cantonal road near Pura, guard rail whole](beamng/verifica/screenshots/v2.8/chase-cantonale-near-pura.jpg)<br>*The cantonal road near Pura, guard rail whole* |
| ![New road: Mugena–Vezio](beamng/verifica/screenshots/v2.8/chase-mugena-vezio-stone-wall.jpg)<br>*New road: Mugena–Vezio* | ![New road: the climb from Vezio to Breno](beamng/verifica/screenshots/v2.8/chase-vezio-breno-village-climb.jpg)<br>*New road: the climb from Vezio to Breno* |
| ![New road: hairpin above Breno](beamng/verifica/screenshots/v2.8/chase-breno-hairpin-valley-view.jpg)<br>*New road: hairpin above Breno* | ![New road: down from Miglieglia to Novaggio](beamng/verifica/screenshots/v2.8/chase-miglieglia-novaggio-tree-lined.jpg)<br>*New road: down from Miglieglia to Novaggio* |
| ![Magliaso and the lake](beamng/verifica/screenshots/v2.8/overview-magliaso-lake.jpg)<br>*Magliaso and the lake* | ![Novaggio, Miglieglia and the Alto Malcantone](beamng/verifica/screenshots/v2.8/overview-novaggio-miglieglia-malcantone.jpg)<br>*Novaggio, Miglieglia and the Alto Malcantone* |
| ![Agno and the Vedeggio plain](beamng/verifica/screenshots/v2.8/overview-agno-plain.jpg)<br>*Agno and the Vedeggio plain* | ![The Magliasina valley](beamng/verifica/screenshots/v2.8/overview-valle-magliasina.jpg)<br>*The Magliasina valley* |

### New in v2.7

> In-game screenshots of the v2.7 level (BeamNG.drive 0.39, driver's eye height): Swiss road signs, markings redrawn to the Swiss standard, dirt tracks flush with the ground, wooded slopes. More in [`beamng/verifica/screenshots/v2.7/`](beamng/verifica/screenshots/v2.7).

| | |
|---|---|
| ![Roundabout entry: 2.41.1 over give way](beamng/verifica/screenshots/v2.7/signs_roundabout.jpg)<br>*Road signs: roundabout entry* | ![The 50 "generale" with the village name](beamng/verifica/screenshots/v2.7/signs_village50.jpg)<br>*Road signs: the 50 "generale" into Magliaso* |
| ![Zone 30 with the 16 t limit on the cantonal road](beamng/verifica/screenshots/v2.7/signs_cantonale_zone30_16t.jpg)<br>*Cantonal road: zone 30 with the 16 t limit, as in the photos* | ![Swiss pedestrian crossing](beamng/verifica/screenshots/v2.7/markings_crossing.jpg)<br>*Markings: Swiss pedestrian crossing and arrows* |
| ![Dashed centre line](beamng/verifica/screenshots/v2.7/markings_dashed_line.jpg)<br>*Markings: dashes at one length and period* | ![Roundabout markings](beamng/verifica/screenshots/v2.7/markings_roundabout.jpg)<br>*Markings: roundabout* |
| ![Track above Arosio](beamng/verifica/screenshots/v2.7/unpaved_arosio.jpg)<br>*Dirt track above Arosio, flush with the ground* | ![Track at Cademario](beamng/verifica/screenshots/v2.7/unpaved_cademario.jpg)<br>*Gravel track at Cademario* |
| ![The pass above Gravesano](beamng/verifica/screenshots/v2.7/fartrees_gravesano_pass.jpg)<br>*Far trees: the pass above Gravesano from the village* | ![The Malcantone from the lake](beamng/verifica/screenshots/v2.7/fartrees_lake_malcantone.jpg)<br>*Far trees: the Malcantone from the lake* |

### v2.6

> Screenshots taken in BeamNG.drive 0.39 on the v2.6 level, at the same views as the earlier renders (`beamng/pipeline/run_readme_screenshots.ps1`: free camera, no HUD, the game's own light, sky, vegetation and terrain).

| | |
|---|---|
| ![Agno, the old town and the Collegiate Church](beamng/verifica/screenshots/02_agno_nucleo.jpg)<br>*Agno, the old town and the Collegiate Church* | ![Cademario](beamng/verifica/screenshots/03_cademario.jpg)<br>*Cademario* |
| ![Novaggio](beamng/verifica/screenshots/04_novaggio.jpg)<br>*Novaggio* | ![Ponte Tresa, seen from across the border](beamng/verifica/screenshots/05_ponte_tresa.jpg)<br>*Ponte Tresa, seen from across the border* |
| ![Bioggio and Manno, the Vedeggio plain](beamng/verifica/screenshots/06_bioggio_manno.jpg)<br>*Bioggio and Manno, the Vedeggio plain* | ![Astano](beamng/verifica/screenshots/07_astano.jpg)<br>*Astano* |
| ![Sessa](beamng/verifica/screenshots/08_sessa.jpg)<br>*Sessa* | ![The pass above Gravesano towards Arosio (the Penudria)](beamng/verifica/screenshots/09_passo_arosio.jpg)<br>*The pass above Gravesano towards Arosio (the Penudria)* |
| ![Caslano and Via Torrazza along the lake](beamng/verifica/screenshots/10_caslano_torrazza.jpg)<br>*Caslano and Via Torrazza along the lake* | ![Magliaso, a street towards the old town](beamng/verifica/screenshots/11_magliaso_strada.jpg)<br>*Magliaso, a street towards the old town* |
| ![The cantonal road towards Pura](beamng/verifica/screenshots/12_pura_cantonale.jpg)<br>*The cantonal road towards Pura* | ![Agno, a street in the old town](beamng/verifica/screenshots/13_agno_via.jpg)<br>*Agno, a street in the old town* |

## How the map is made

The map is rebuilt from scratch from the data every time: there is no hand-edited level file. In short:

1. **Download the official data** for the area: terrain and surface models, aerial photos, the road network, the cadastral survey, 3D buildings, the building register, OpenStreetMap.
2. **Build the road network.** Every road and trail line is re-centred on the surveyed carriageway, and one least-squares fit computes a smooth height profile for the whole network, so heights match at every junction and gradients are the real ones.
3. **Lay the drivable surfaces** (carriageways, pavements, yards, trails) and carve the terrain 10 cm under them, so it never pokes through a road.
4. **Add everything else:** buildings with drawn façades, walls, bridges, guardrails, road markings detected in the 10 cm aerial photo, trees from the surface model, grass, rivers and the lake, the railway, signs and bus stops.
5. **Write the BeamNG level** with spawn points and the AI road network.
6. **Check it automatically** (`check_level.py`, `drive_test.py`). If the checks fail, no release is published.
7. **Finish it** (`build_level.FINISH`, since v2.8 all inside the build): make it lighter for the game (`optimize_level.py`), add the game's grass, lay the tracks and the paved edges flush, redraw the markings, bring back the far trees, put up the road signs, raise the traffic islands and the direction signs (v3.0), shade the ground behind the walls, add the undergrowth, the street lamps (lit at night), delineators and pole lines, the railway's overhead line, the piers and boats, the gutters, aerials and solar panels of the houses, and since v3.0 the wear of the asphalt, flower boxes and woodpiles, petrol stations, street life, shop fronts, the skin of the steep banks and the vineyards on the final ground, and since v3.0.40 the sounds of the water, the time trials, one file for every identical texture and the game's own files where BeamNG.drive 0.40 keeps them.

```mermaid
flowchart LR
    subgraph Sources
        A[swissALTI3D / swissSURFACE3D<br/>terrain and surface]
        B[swissTLM3D<br/>network, bridges, railway]
        C[Official survey TI<br/>carriageways, buildings, walls]
        D[swissBUILDINGS3D<br/>3D buildings]
        E[GWR building register<br/>use, period, floors]
        F[OpenStreetMap<br/>one-ways, signs, shops, surfaces]
        G[Street View<br/>reference and measurements only]
    end
    A & B & C --> R[Network and profile<br/>network_surface.py]
    R --> M[Drivable surfaces<br/>network_mesh.py]
    D & C & E & F --> H[Buildings and façades<br/>facades.py]
    G -. colours, shutters, guardrails, walls .-> H
    M & H --> L[BeamNG level<br/>build_level.py]
    L --> O[Finishing steps<br/>build_level.FINISH:<br/>lighter level, grass, tracks, markings,<br/>far trees, signs, lamps, railway line, lake,<br/>sounds, time trials, 0.40 paths]
    O --> Q
    Q --> Z[v3.0.40 zip<br/>package.py]
```

**How a release is built.** The [`release_v2.8.yml`](.github/workflows/release_v2.8.yml) workflow builds the level from scratch on a GitHub server (*Actions* → *Release v2.8* → *Run workflow*): it downloads the data, builds the level with every finishing step, runs the checks and publishes the zip. Up to v2.8 the versions after v2.4 were patch scripts run on the previous zip; since v2.8 those steps are part of the build itself (`build_level.FINISH`), and [`v28_build_test.yml`](.github/workflows/v28_build_test.yml) makes the same zip for the test in the game. v2.8 itself is the zip of the [`final_build_test.yml`](.github/workflows/final_build_test.yml) workflow, tested in the game and published unchanged by [`release_v2.8_tested.yml`](.github/workflows/release_v2.8_tested.yml). v3.0 is built the same way by [`v3_build_test.yml`](.github/workflows/v3_build_test.yml): the level from scratch with every finishing step, the checks and the zip to test in the game. Since v3.0.40 every build to test goes to the pre-release [*nightly*](https://github.com/wintrymichi/magliasinaNG/releases/tag/nightly), built by [`nightly_build.yml`](.github/workflows/nightly_build.yml) when `beamng/nightly/stamp.txt` changes: it replaces the previous nightly and is never the latest release. A release is a nightly zip tested in the game. v3.1 is the exception: the nightly of 23 October 2026 (built from `21ff47b`) with nine small patches applied to its zip in place by the `nightly_patch_*` workflows of the integration branch, published before the in-game test.

```bash
cd beamng/pipeline
python build_level.py                          # the whole level, with the finishing steps
python build_level.py --finish lamps signs     # only some finishing steps, again, on the built level
python package.py magliaso_pura_v3.0.40        # the mod zip (with the time trials) and its digest
```

How to run the pipeline yourself, the environment variables, the coordinate system and the role of every script are in [`beamng/README.md`](beamng/README.md).

**Where the numbers come from.** Coordinates are Swiss LV95 shifted to a local origin in the map (1 unit = 1 m), and heights are the real ones above sea level. The Street View panoramas never enter the map: from them the pipeline only takes numbers, like a façade colour, whether a guardrail is there, or what a wall is made of.

## Quality and verification

> **The drive tests are diagnostics, not a verdict on playability.** The virtual drive test and the game's AI drives exist to find spots worth a look (a step, a bump, an object at the road edge). A simulated wheel or the game's AI stops or counts an event where a player simply drives on, so a number in these reports, or an AI that got stuck, does not mean a road cannot be driven.

- **Automatic checks over the whole map** (`check_level.py`, results in [`beamng/verifica/check_level.json`](beamng/verifica/check_level.json)): terrain above the roads, holes, steps, seams between blocks, obstacles on the carriageway searched along every road and trail, trees in the clearance envelope, the AI network, missing files and, since v2.4, building walls facing inwards; since v3.0.40 the holes left in the walls (`wall_holes`).
- **Virtual drive test** (`drive_test.py`, [`beamng/verifica/drive_test.json`](beamng/verifica/drive_test.json)): a simulated car (a quarter-car model on all four wheels) drives every road in both directions and every trail, 670 km, on the level's surfaces as written. On the same roads as v2.1 it counts 66 % fewer steps on minor roads (1695 → 570) and 20 % fewer on main roads (74 → 59); wheels lifting off the road drop by 57 % on minor roads and 58 % on main roads, hard hits by 25 % and sharp twists by 61 % on minor roads.
- **Street View review** ([`beamng/verifica/REVISIONE.md`](beamng/verifica/REVISIONE.md)): for every road, the panorama coverage, the measured buildings, the guardrails and walls seen, the drive-test events before and after, and the places compared photo/map from the same camera, with the problems found and the fixes.
- **In the game** (since v2.5): loading time, memory and frame rate measured in BeamNG.drive 0.39 at the spawn points, for v2.6 on meadows and gardens, for v2.7 at the test views of the signs, markings, tracks and slopes, with every kind of sign checked from the traffic ([`beamng/verifica/screenshots/v2.7/test.json`](beamng/verifica/screenshots/v2.7/test.json)), and for v2.8 the released zip driven on the new roads, guard rails and bridges ([`beamng/verifica/v2.8/ingame_test_report.md`](beamng/verifica/v2.8/ingame_test_report.md)); for v3.0 the frame rate at 13 places ([`beamng/verifica/v3.0/ingame_test_report.md`](beamng/verifica/v3.0/ingame_test_report.md)). for v3.0.40 on BeamNG.drive 0.40.1 the same 13 places, the memory, the screenshots of what is new and the AI traffic ([`beamng/verifica/v3.0.40/ingame_test_report.md`](beamng/verifica/v3.0.40/ingame_test_report.md)).

## Known limitations

Each limitation has an issue where the details, the places and the possible fix are tracked.

| Limitation | Issue |
|---|---|
| Not yet reviewed in the game: the river water, the grip of the paving, the street lamp lights at night. | [#8](https://github.com/wintrymichi/magliasinaNG/issues/8) |
| Palms, grass density and vineyard row spacing are estimates. Where OpenStreetMap gives no surface, swissTLM3D applies. | [#9](https://github.com/wintrymichi/magliasinaNG/issues/9) |
| The plinth of a few houses blocks a trail (12 blocked trail points instead of 10, for example in an alley below Pura). | [#10](https://github.com/wintrymichi/magliasinaNG/issues/10) |
| Façades: windows, balconies and doors are plausible but not copied one by one (v3.0.40 can measure them from open street photos, but the detector still misses about half, so that is off); some colours measured in shadow are wrong; arcades and storey-high plinths are not modelled; exposed stone only on the churches known from photos (a church and its tower in one survey building get one material: San Cristoforo in Caslano is all plaster; the nave of Bedigliora is drawn like the houses of its block). | [#11](https://github.com/wintrymichi/magliasinaNG/issues/11) |
| Yards on two levels become steep ramps beside the road (for example in Caslano). | [#12](https://github.com/wintrymichi/magliasinaNG/issues/12) |
| Some buildings have walls under only part of the roof (a shed in Pura). | [#13](https://github.com/wintrymichi/magliasinaNG/issues/13) |
| Guardrails and wall materials only where the panoramas see them; 736 walls stay stone. | [#14](https://github.com/wintrymichi/magliasinaNG/issues/14) |
| The drive test still reports spots to fix: the steep junction in Castelrotto, Via Giuseppe Soldati, the bridge ends on Via Mondonico and Via Roncaccio, the level crossing on Via Grumo, the corridor edges. | [#15](https://github.com/wintrymichi/magliasinaNG/issues/15) |
| Photo/map review: 116 places checked, 20 differences still to be looked at. | [#17](https://github.com/wintrymichi/magliasinaNG/issues/17) |
| On the Italian side there is only terrain and landscape: no roads, buildings or trees beyond the Ponte Tresa border bridge. | [#18](https://github.com/wintrymichi/magliasinaNG/issues/18) |
| Tunnels are not built: roads and the railway stop at the portals. | [#19](https://github.com/wintrymichi/magliasinaNG/issues/19) |
| One-way streets only where OpenStreetMap records them. | [#20](https://github.com/wintrymichi/magliasinaNG/issues/20) |
| Road signs only where OpenStreetMap maps them or records the rule that needs them: signs nobody mapped that no rule implies are missing (direction signs only at the junctions with the main roads, since v3.0.40); 35 plates of the cantonal road keep a single colour; the general 50 has no village name in the communes of several villages. | [#21](https://github.com/wintrymichi/magliasinaNG/issues/21) |
| v3.0: tested in the game (frame rate, memory, the new features). The façade of the Panetteria Magliasino at Magliaso Paese (a block of the survey made of several houses) still has no windows on its street side. On the Strada Cantonale between Magliaso and Agno, at the foot of some retaining walls on the hill side, the ground rises in a slope against the wall as in the terrain model. The twin bridges of the Strada Cantonale over the Magliasina keep the two decks of v1.1 with the gap between them. 92 bus stops have no room for a shelter beside the road. The parked cars need the game's traffic with parked vehicles on. The AI driver stopped at a few spots in v2.8 (Mugena, Vezio, Miglieglia, Pura): spots to look at, not roads you cannot drive (see *Quality and verification*). | — |
| v3.0.40: the AI traffic stalls. In the game test the 12 cars stopped within one or two minutes and never moved again: they gather around the player's car standing still. At the level's default spawn, which is on the carriageway of the cantonal road just before the Magliaso roundabout, six cars queued in one line behind it, undamaged, and waited for it until the end of the test (10 minutes); at two give-way points cars ran into each other. The game moves only cars that are far from the player and out of sight (2 of 12), so the jam never clears. With the player's car standing on the open cantonal road it was the same: all 12 stopped within 133 m of it, none at a signal. **Still broken in v3.1:** in its game test 13 cars queued behind the player's car parked on the Magliaso bridge and then ran into the traffic island at the roundabout exit; 8 of 12 cars were damaged within 2 minutes. To fix: the spawn points beside the road, the give-way junctions and islands, a test with the player driving. | [#83](https://github.com/wintrymichi/magliasinaNG/issues/83) |
| v3.0.40: the time trials were not driven in the game test (the screenshots stand on their routes), and the sounds of the water were not listened to. BeamNG.drive 0.40 has no church bells, birds or crickets. The open street photos were analysed only around Pura, Miglieglia and Novaggio, and the façades measured from them are off (the detector misses about half of the windows). The slipway at Caslano goes on under the lake (fixed for v3.1). | [#84](https://github.com/wintrymichi/magliasinaNG/issues/84) |
| Within about 12 m the far trees (v2.7) look almost black. No road comes that close to them, but on foot or off-road you can see it. | [#30](https://github.com/wintrymichi/magliasinaNG/issues/30) |
| Magliaso bridges over the Magliasina: at the south-east corner of the main deck, over the river bank, the deck meets the road with a step of up to 0.4 m over about 1.5 m, and at the west corners of the upstream bridge with 6-8 cm. Both are outside the lanes. | – |
| v3.1: under the FLP at the Via Golf underpass (Caslano - Magliaso) the two footways beside the road lie about 2 m above the road, and the rail deck is 2.9 m over the road at its north edge. The footways are fixed in the code for the next build. The 8 marked crossings added at bus stops keep a 12 cm kerb. | – |
| v3.1, seen in the game test: some walls of the Magliaso–Pura Cantonale (the hairpin, a cut above Magliaso) still have saw-tooth tops; the Via Golf underpass deck is a flat grey slab with no texture; the new traffic island posts miss two materials (`mp_island_reflector`, `mp_island_beacon`); grass tufts grow on the asphalt of the Ponte Tresa bridge at its Italian end; large angular wall blocks beside the Cantonale near Magliaso. The game also warns that its bindless material slots are full (8,192) and finds no licence plate template for the level. | [#85](https://github.com/wintrymichi/magliasinaNG/issues/85) |

## Repository layout

Every file of the repository and what it is; the folders of screenshots and renders are one line each (the check folders of `beamng/verifica/v2.8/` also hold a `render3d/` folder with the before/after renders). The folders marked *local only* are not in the repository. The scripts are described in more detail in [`beamng/README.md`](beamng/README.md) (*Script order* and the technical notes by version), the pinned data in [`beamng/dati/`](beamng/dati) and the checks in [`beamng/verifica/`](beamng/verifica).

```
.
├── README.md                                 # This file: install, where to drive, how the map is made
├── CHANGELOG.md                              # What changed in each version of the map, newest first
├── .gitignore                                # Keeps the local Street View images and Python caches out
├── panoramas.csv                             # The 366 panoramas: position, date, heading, distance
├── panoramas.json                            # Metadata of the 366 panoramas used, read by the pipeline
├── panoramas.geojson                         # Positions of the 366 panoramas as GeoJSON points
├── panoramas_all_dates.json                  # All 910 panoramas found along the road, 2013 to 2022
├── cameras.json                              # Poses of the 5856 Street View views: GPS, yaw, pitch, FOV
├── sv_capture.py                             # Finds and downloads the panoramas, cuts 16 views each
├── expand.py                                 # Adds linked neighbour panoramas within 15 m of the road
├── finalize.py                               # Picks 2022 panoramas, older in gaps; writes panoramas.*
├── download.log                              # Log of sv_capture.py download: 366 panoramas, 5856 views
├── panorami/                                 # 360° panoramas (local only, not in the repository)
├── viste/                                    # 16 perspective views per panorama (local only)
├── storici_2013_2014/                        # Panoramas of 2013/2014 (local only)
├── .github/                                  # GitHub configuration
│   └── workflows/                            # GitHub Actions: release builds, the v2.8 and v3.0 test builds, the nightly builds, website
│       ├── final_build_test.yml              # Final v2.8 build from scratch, checks, doubles and the zip (v2.8)
│       ├── landmarks.yml                     # Development pack of the churches, bell towers and cable car (v3.0.40)
│       ├── nightly_build.yml                 # Nightly build from scratch to the pre-release "nightly" (v3.0.40)
│       ├── nightly_patch.yml                 # Patches the nightly zip in place: the far trees' imposters (v3.0.40)
│       ├── paesi_interi.yml                  # The whole villages of Caslano and Arosio, computed and pinned (v3.0.40)
│       ├── pages.yml                         # Publishes web/ on GitHub Pages when web/ changes on main
│       ├── release_notes.yml                 # Updates the notes of a published release from beamng/RELEASE_<tag>.md
│       ├── release_v1.1.yml                  # Release build: the v1.0 zip fixed by patch_release.py (v1.1)
│       ├── release_v2.0.yml                  # Release build from scratch: the whole 51 km² area (v2.0)
│       ├── release_v2.1.yml                  # Release build from scratch: markings, AI, railway (v2.1)
│       ├── release_v2.2.yml                  # Release build from scratch: façades, new roads (v2.2)
│       ├── release_v2.3.yml                  # Release build from scratch: surface fix, fewer trees (v2.3)
│       ├── release_v2.4.yml                  # Release build from scratch: houses, OSM surfaces (v2.4)
│       ├── release_v2.7.yml                  # Release build: the v2.6 zip through four patches (v2.7)
│       ├── release_v2.8.yml                  # Release build from scratch, finishing steps inside (v2.8)
│       ├── release_v2.8_tested.yml           # Release v2.8: publishes the final build test zip tested in the game
│       ├── strade_extra.yml                  # The roads added beyond the boundary, recomputed and pinned (v2.8)
│       ├── street_reference.yml              # Open street photos: download, fit, segment, small results (v3.0.40)
│       ├── traffic_build.yml                 # Build with the traffic work and its review, by hand only (v3.0.40)
│       ├── traffic_probe.yml                 # Traffic and drivability probe of a released level (v3.0.40)
│       ├── v28_build_test.yml                # Test build from scratch, checks and the zip to test (v2.8)
│       ├── v3_build_test.yml                 # Test build from scratch, checks and the zip to test (v3.0)
│       └── v3_preview.yml                    # Quick previews of v3.0 changes without the whole build (v3.0)
├── beamng/                                   # The BeamNG.drive map
│   ├── README.md                             # Pipeline guide: building, script order, notes by version
│   ├── RELEASE_v*.md                         # Release notes, one per version (v2.0 … v3.0)
│   ├── pipeline/                             # Python pipeline: from open data to the level zip
│   │   ├── README_livello.md                 # Player README copied into the level as README.md
│   │   ├── ai_roads.py                       # Invisible AI DecalRoads that BeamNG builds its navgraph from
│   │   ├── ambient_sounds.py                 # Water sounds of the game by the rivers, streams and lake (v3.0.40)
│   │   ├── area.py                           # Playable area polygon: boundary plus road corridors
│   │   ├── asset_bounds.py                   # Bounding boxes of vanilla DAE shapes read from game zips
│   │   ├── backdrop.py                       # Distant terrain ring mesh around the block, visual only
│   │   ├── bld_textures.py                   # Procedural building textures and the openings atlas
│   │   ├── bng.py                            # Level writers: .ter terrain, scene NDJSON, materials, DAE
│   │   ├── bridge_report.py                  # Bridge review sheets: profile and three views per bridge
│   │   ├── bridges.py                        # Bridge decks, parapets and piers on swissTLM3D bridge lines
│   │   ├── build_level.py                    # Assembles the level and runs its finishing steps (FINISH)
│   │   ├── build_rasters.py                  # Resamples swisstopo DTM, DSM and orthophoto to map grids
│   │   ├── buildings_mesh.py                 # Building meshes from swissBUILDINGS3D LOD2 in 256 m tiles
│   │   ├── calib_camheight.py                # Street View camera height calibration (camera_height.json)
│   │   ├── calibrate_attitude.py             # Sign convention of Street View pitch/roll from verticals
│   │   ├── camera.py                         # Equirectangular panorama camera model and rotations
│   │   ├── canopy.py                         # Moves trees out of road clearance and solids, onto ground
│   │   ├── carryover.py                      # Route paint and props carried over from the released level
│   │   ├── catenary_tour.py                  # Before/after views of the railway overhead line check (v2.8)
│   │   ├── check_level.py                    # Pre-release checks of roads, obstacles, trees, AI and files
│   │   ├── clearance.py                      # Keeps vegetation off paved surfaces, AI lines on one surface
│   │   ├── config.py                         # Shared paths, LV95-to-local coordinates and map extent
│   │   ├── copy_materials.py                 # Copies vanilla material definitions into the level
│   │   ├── direction_signs.py                # Direction signs at the roundabout exits (v3.0) and junctions (v3.0.40)
│   │   ├── doubles.py                        # What the level has twice: signs, guard rails, walls (v2.8)
│   │   ├── download_av.py                    # Downloads Ticino cadastral survey layers (MOpublic WFS)
│   │   ├── download_gwr.py                   # Downloads the Federal Register of Buildings extract (GWR)
│   │   ├── download_osm.py                   # OSM extract (Overpass): roads, signs, POIs, communes (v2.1)
│   │   ├── download_swisstopo.py             # Downloader of swisstopo DTM, DSM, orthophoto, 3D buildings
│   │   ├── download_tlm.py                   # Streamed swissTLM3D extract: roads, railway, streams (v2.0)
│   │   ├── download_worldcover.py            # ESA WorldCover 2021 land cover around the map (v3.0)
│   │   ├── drive_context.py                  # Drive-test events by site: junction, seam, bridge end (v2.2)
│   │   ├── drive_test.py                     # Virtual quarter-car drive test of every road and path (v2.2)
│   │   ├── extract_buildings.py              # Extractor of swissBUILDINGS3D LOD2 walls, roofs and floors
│   │   ├── facades.py                        # Facades: windows, doors, shops, balconies, roofs (v2.2)
│   │   ├── far_trees.py                      # Far trees away from roads: drawn models, imposters (v2.7, baked since v3.0.40)
│   │   ├── fences.py                         # Railings and fences on roadside wall crests, from panoramas
│   │   ├── final_screenshots.py              # Final in-game check views: signs, markings, tracks (v2.7)
│   │   ├── fix_probe.py                      # Why a road has a step: cells and top faces around it (v3.0)
│   │   ├── forest_fill.py                    # Far trees on the woods outside the cadastral survey (v3.0)
│   │   ├── bus_shelters.py                   # Shelters with a bench at the bus stops (v3.0)
│   │   ├── fuel_stations.py                  # Petrol stations: canopies, pump islands, price totems, refuelling (v3.0)
│   │   ├── game_paths.py                     # The game's own files where BeamNG.drive 0.40 keeps them (v3.0.40)
│   │   ├── geo.py                            # Raster helpers: LV95 tile mosaics and the local Grid class
│   │   ├── groundcover.py                    # GroundCover grass and flowers (v2.6) and shrubs (v2.8)
│   │   ├── guardrail_mesh.py                 # Guard rails from the game's Italy models along the runs (v2.8)
│   │   ├── guardrails.py                     # Cantonal road guardrails from LiDAR, checked in panoramas
│   │   ├── guardrails2.py                    # Cantonal road guardrails by multi-view panorama voting
│   │   ├── house_extras.py                   # Flower boxes and woodpiles at the houses (v3.0)
│   │   ├── houses_tour.py                    # House details check: sites, renders, game views (v2.8)
│   │   ├── ingame_screenshots.py             # In-game camera tour for the README screenshots (v2.6)
│   │   ├── islands.py                        # Raised traffic islands with the keep-right sign (v3.0)
│   │   ├── italy_mats.py                     # Materials on the textures of the game's Italy level (v3.0)
│   │   ├── lake_tour.py                      # Piers and boats check: sites, renders, game views (v2.8)
│   │   ├── lamps.py                          # Street lamps: cantonal road (panoramas), villages (v2.8)
│   │   ├── lamps_tour.py                     # Village street lamps check: sites, renders, views (v2.8)
│   │   ├── landmark_textures.py              # Textures of the bell chambers, portals, windows and granite (v3.0.40)
│   │   ├── landmarks.py                      # Churches, bell towers and the Monte Lema cable car (v3.0.40)
│   │   ├── landmarks_pack.py                 # Development pack of the landmark sites (v3.0.40)
│   │   ├── landmarks_preview.py              # Before/after renders of the landmark sites (v3.0.40)
│   │   ├── landcover.py                      # Cadastral survey land cover: 0.5 m raster and local polygons
│   │   ├── lidar_extract.py                  # Non-vegetation LiDAR points near the cantonal road and walls
│   │   ├── marking_votes.py                  # Panorama votes on cantonal road marking cells and polygons
│   │   ├── markings.py                       # Cantonal road lines traced in the straightened orthophoto
│   │   ├── markings_clean.py                 # Network paint redrawn as Swiss road markings (v2.7)
│   │   ├── markings_decals.py                # Cantonal road markings as painted mesh strips
│   │   ├── markings_net.py                   # Network road paint as meshes on the road faces (v2.1)
│   │   ├── markings_photo.py                 # Cantonal road edge lines by multi-view panorama voting
│   │   ├── markings_raster.py                # Cantonal road crossings, stop lines, arrows from 10 cm ortho
│   │   ├── markings_rules.py                 # Road markings of the whole network by the Swiss rules (v3.0)
│   │   ├── markings_state.py                 # Marking state in the 2022 panoramas: unmarked, red bands
│   │   ├── markings_std.py                   # Road paint from a library of standard pieces (v2.8)
│   │   ├── mesh_strips.py                    # Simplifies steep road mesh strips within 4 mm (v2.5)
│   │   ├── missing_buildings.py              # Missing and gone buildings vs swissBUILDINGS3D (v2.2)
│   │   ├── missing_veg.py                    # Shrubs seen in the panoramas but missing in the game
│   │   ├── network.py                        # Road and path network from swissTLM3D, in stations (v2.0)
│   │   ├── network_markings.py               # Road paint of the whole network from the 10 cm ortho (v2.1)
│   │   ├── network_mesh.py                   # Drivable meshes of the whole road and path network (v2.0)
│   │   ├── network_surface.py                # Smooth heights, grade and cross slope per station (v2.0)
│   │   ├── objects.py                        # Benches, bins, hydrants, mailboxes located from Street View
│   │   ├── ogr_tin.py                        # Reads swissBUILDINGS3D TIN layers via GDAL ctypes (v2.0)
│   │   ├── optimize_level.py                 # Lighter level: merged tiles, welded meshes, culling (v2.5)
│   │   ├── ortho.py                          # On-demand reader of the local 10 cm SWISSIMAGE tiles
│   │   ├── ortho10.py                        # Window reads of the 10 cm SWISSIMAGE cloud GeoTIFFs (v2.1)
│   │   ├── osm.py                            # OpenStreetMap data of the area in local coordinates (v2.1)
│   │   ├── osm_surface.py                    # Road and path surface categories from OSM tags (v2.4)
│   │   ├── paesi_interi.py                   # The whole villages of Caslano and Arosio for the area (v3.0.40)
│   │   ├── package.py                        # Zips the built level as a BeamNG mod into dist/, its digest
│   │   ├── palms.py                          # Windmill palms in lakeside gardens, model drawn here (v2.4)
│   │   ├── pano_strip.py                     # Straightened road strip coloured from Street View panoramas
│   │   ├── patch_far_imposters.py            # Patch: the baked far tree imposters into a built zip (v3.0.40)
│   │   ├── patch_release.py                  # Patch: the v1.1 road fixes into the v1.0 zip (v1.1)
│   │   ├── paved_tour.py                     # Sites and before/after views of the paved edges check (v2.8)
│   │   ├── photo_votes.py                    # Multi-view label votes of segmented panoramas at 3D points
│   │   ├── places.py                         # Villages from swissNAMES3D for the spawn points (v2.0)
│   │   ├── poles.py                          # Poles, lamps and sign plates located in segmented panoramas
│   │   ├── prepare_work.py                   # Seeds WORK with the photo results kept in dati (v2.0)
│   │   ├── preview_smooth.py                 # Quick 3D preview of the smoothed survey curves (v3.0)
│   │   ├── props.py                          # Lamps, poles, sign plates and furniture from the photos
│   │   ├── props_osm.py                      # STOP signs, benches, lamps and bus stops from OSM (v2.1)
│   │   ├── qa_log.py                         # Writes the visual review log dati/qa_review.json (v2.2)
│   │   ├── races.py                          # Time trials over the AI roads as missions of the game (v3.0.40)
│   │   ├── railway.py                        # Railway tracks, ballast and bridges from swissTLM3D (v2.1)
│   │   ├── refine_poses.py                   # Panorama poses refined against orthophoto and DTM
│   │   ├── render3d.py                       # Headless three.js screenshots of a built level for review (v3.0: game textures and models)
│   │   ├── render3d_models.py                # Stand-ins for the game's models in render3d.py (v3.0)
│   │   ├── render3d_textures.py              # Stand-ins for the game's textures in render3d.py (v3.0)
│   │   ├── review_map.py                     # Review screenshots of the whole map with render3d (v2.0)
│   │   ├── review_report.py                  # Writes REVISIONE.md: road-by-road Street View review (v2.2)
│   │   ├── rivers.py                         # Water meshes and material of the surveyed rivers (v2.4)
│   │   ├── road_mesh.py                      # Road surface meshes from the cadastral paved polygons
│   │   ├── road_profile.py                   # Carriageway edges and width along the cantonal road
│   │   ├── road_strip.py                     # Straightened orthophoto strip of the cantonal road
│   │   ├── parking.py                        # Parking spots for the parked cars and white bays (v3.0)
│   │   ├── road_wear.py                      # Tyre tracks, patches and dusty edges on the asphalt (v3.0)
│   │   ├── roadheight.py                     # Fitted heights of the paved surfaces (road_surface.npz)
│   │   ├── roadside_tour.py                  # Sites and before/after views of the roadside check (v2.8)
│   │   ├── roadside_walls.py                 # Retaining walls along the cantonal road from DTM and photos
│   │   ├── run_catenary_screenshots.ps1      # In-game screenshots and fps of the catenary check (v2.8)
│   │   ├── run_final_screenshots.ps1         # Final in-game test of the zip: shots, load time, fps (v2.7)
│   │   ├── run_houses_screenshots.ps1        # In-game before/after check of the house details (v2.8)
│   │   ├── run_lake_screenshots.ps1          # In-game before/after check of lake piers and boats (v2.8)
│   │   ├── run_lamps_screenshots.ps1         # In-game day/night check of the street lamps (v2.8)
│   │   ├── run_paved_screenshots.ps1         # In-game before/after check of the flush paved edges (v2.8)
│   │   ├── run_readme_screenshots.ps1        # In-game README screenshots via magliaso_readme (v2.6)
│   │   ├── run_roadside_screenshots.ps1      # In-game check of delineators and wooden pole lines (v2.8)
│   │   ├── run_signs_more_screenshots.ps1    # In-game check of the unmapped warning/parking signs (v2.8)
│   │   ├── run_signs_screenshots.ps1         # In-game road-sign screenshots via magliaso_signs (v2.7)
│   │   ├── run_understory_screenshots.ps1    # In-game check of undergrowth and darker forest floor (v2.8)
│   │   ├── run_unpaved_screenshots.ps1       # In-game before/after check of the unpaved tracks (v2.7)
│   │   ├── run_v28_screenshots.ps1           # Full in-game release test: 9 checks, fps, memory (v2.8)
│   │   ├── run_validation.ps1                # In-game camera tour at the Street View poses (v1.0)
│   │   ├── run_wall_fill_screenshots.ps1     # In-game before/after check of the ground behind walls (v2.8)
│   │   ├── same_textures.py                  # One file for each identical texture of the level (v3.0.40)
│   │   ├── screenshots.py                    # README views rendered with render3d.py, no game (v2.2)
│   │   ├── segment_views.py                  # Mask2Former segmentation of the Street View views (v1.0)
│   │   ├── shopfronts.py                     # Shop fronts: signs, awnings and what stands outside (v3.0)
│   │   ├── signs_ch.py                       # Swiss road sign plates (OSStr) drawn as textures (v2.7)
│   │   ├── signs_more.py                     # Placement rules for unmapped warning/parking signs (v2.8)
│   │   ├── signs_more_tour.py                # Sites, renders and game views of the unmapped signs (v2.8)
│   │   ├── signs_net.py                      # Road sign positions from OSM tags and Swiss rules (v2.7)
│   │   ├── signs_screenshots.py              # Camera tour of the in-game road-sign check (v2.7)
│   │   ├── smooth_geom.py                    # Curves of the cadastral survey smoothed (v3.0)
│   │   ├── solve_poses.py                    # Viterbi solve of panorama poses on the orthophoto (v1.0)
│   │   ├── steep_skin.py                     # Steep banks along the roads as a smooth skin (v3.0)
│   │   ├── strade_extra.py                   # Gravesano, Arosio, Caslano roads via swissTLM3D (v2.0, v2.2)
│   │   ├── street_life.py                    # Bins, hydrants, terraces, mirrors and props by rules (v3.0)
│   │   ├── street_*.py                       # Open street photo reference: fit, segment, hedges, fountains (v3.0.40)
│   │   ├── surface_fit.py                    # Thin-plate fit of the paved surfaces to the DTM (v1.1)
│   │   ├── surface_textures.py               # Procedural gravel, earth and stone road textures (v2.4)
│   │   ├── sv_coverage.py                    # Lists the Street View panoramas covering the area (v2.2)
│   │   ├── sv_facades.py                     # Facade and shutter colours measured in Street View (v2.2)
│   │   ├── sv_fetch.py                       # Downloads Street View panoramas about every 20 m (v2.2)
│   │   ├── sv_guardrails.py                  # Guard rails of the whole network seen in Street View (v2.2)
│   │   ├── sv_review.py                      # Contact sheets: orthophoto, Street View, map render (v2.2)
│   │   ├── sv_segment.py                     # Mask2Former segmentation of Street View panoramas (v2.2)
│   │   ├── sv_walls.py                       # Survey wall materials classified from Street View (v2.2)
│   │   ├── terrain.py                        # BeamNG terrain builder: heights and material layers
│   │   ├── terrain_colors.py                 # Terrain material colours measured in orthophoto and photos
│   │   ├── test_load.ps1                     # Load test in BeamNG: screenshot and beamng.log errors
│   │   ├── texture_buildings.py              # Facade photo textures near the Cantonale (local build only)
│   │   ├── texture_walls.py                  # Wall photo textures near the Cantonale (local build only)
│   │   ├── texturing.py                      # Projective texturing of walls/facades and atlas packing
│   │   ├── traffic_probe.py                  # AI network of v3.0.40 on the released level, without a build (v3.0.40)
│   │   ├── traffic_report.py                 # Numbers of the in-game traffic test: AI graph, stuck cars (v3.0.40)
│   │   ├── trees.py                          # Tree tops and crowns from the canopy height model
│   │   ├── understory.py                     # Shrubs and hedges from the 0.6-6 m vegetation height
│   │   ├── understory_tour.py                # Sites, renders and views of the undergrowth check (v2.8)
│   │   ├── unpaved_tour.py                   # Sites, views and drives of the unpaved tracks check (v2.7)
│   │   ├── v28_check.py                      # Check of the chained v2.8 patches against each alone (v2.8)
│   │   ├── v28_tour.py                       # In-game tour of the views of all nine v2.8 checks (v2.8)
│   │   ├── validate_metrics.py               # Photo vs game segmentation agreement, IoU per class group
│   │   ├── validation.py                     # Validation camera tour and photo crops at Street View poses
│   │   ├── vanilla.py                        # Game-derived files taken from the released level zip (v2.0)
│   │   ├── vegetation.py                     # Forest items for the measured trees: model choice and scale
│   │   ├── verify_report.py                  # VERIFICA.md summary and chart of the full validation
│   │   ├── vine_textures.py                  # Drawn textures of the vine rows (v3.0)
│   │   ├── vineyards.py                      # Vine rows in the survey's vineyards (v2.4; v3.0 vines on their wires)
│   │   ├── wall_caps.py                      # Wall tops near the road capped where photos see no wall
│   │   ├── wall_fill_tour.py                 # Sites, renders and views of the wall backfill check (v2.8)
│   │   ├── walls.py                          # Cadastral walls: meshes, terrain carving beside them
│   │   ├── water.py                          # Lake Lugano as water blocks that stop at its shore (v2.0)
│   │   ├── zone_report.py                    # Zones, road checklist and discrepancy register (v2.1)
│   │   └── bng_lua/                          # Game extensions for the in-game tours
│   │       ├── magliaso_readme.lua           # In-game README screenshots from the free camera (v2.6)
│   │       ├── magliaso_signs.lua            # In-game road-sign screenshot tour with fps log (v2.7)
│   │       ├── magliaso_traffic.lua          # In-game traffic test: the AI graph and how the traffic drives (v3.0.40)
│   │       ├── magliaso_unpaved.lua          # In-game unpaved track check: views, drive probe, fps (v2.7)
│   │       └── magliaso_validate.lua         # In-game validation screenshots at the Street View poses
│   ├── dati/                                 # Small results pinned for the release builds
│   │   ├── asset_bounds.json                 # Tree model sizes at scale 1, for builds without the game
│   │   ├── attitude_convention.json          # Sign convention of the Street View pitch and roll
│   │   ├── buildings_diff.json               # Added and demolished buildings with their evidence (v2.2)
│   │   ├── camera_height.json                # Calibrated Street View camera height above the road
│   │   ├── camera_height_calib.json          # Ground-registration score per panorama and camera height
│   │   ├── cantonale_gravesano.json          # Magliaso–Gravesano cantonal road line in LV95 (v2.0)
│   │   ├── facade_colors.json                # Plaster and shutter colours per building, from photos (v2.2)
│   │   ├── far_imposters/                    # Far tree imposters baked by BeamNG 0.40, md5 of their models (v3.0.40)
│   │   ├── fences.json                       # Railings and fences on Magliaso–Pura walls, from panoramas
│   │   ├── guardrails_final.json             # Magliaso–Pura guardrails from photo votes and LiDAR
│   │   ├── guardrails_sv.json                # Guardrails of the whole network seen in Street View (v2.2)
│   │   ├── gwr_area.json.gz                  # Pinned Federal Register of Buildings (GWR) extract (v2.2)
│   │   ├── lamps.json                        # Magliaso–Pura street lamps triangulated in the panoramas
│   │   ├── marking_poly_votes.json           # Photo votes per orthophoto marking polygon of the route
│   │   ├── marking_votes.npz                 # Lane-marking photo votes on the route's road strip grid
│   │   ├── markings.json                     # Magliaso–Pura centre and edge lines from the orthophoto
│   │   ├── markings_photo.json               # Magliaso–Pura edge lines voted in the panoramas
│   │   ├── markings_raster.json              # Route's crossings, stop lines and arrows from the orthophoto
│   │   ├── markings_state.json               # Road markings as of Oct 2022: unmarked spans, red bands
│   │   ├── network_markings.json.gz          # Road paint of the whole network from the orthophoto (v2.1)
│   │   ├── objects.json                      # Street furniture (benches, bins, hydrants) from panoramas
│   │   ├── osm_area.json.gz                  # Pinned OpenStreetMap extract of the area (v2.1)
│   │   ├── osm_communes.json.gz              # Pinned OSM municipality boundaries of the area (v2.1)
│   │   ├── osm_pois.json.gz                  # Pinned OSM shops, bars and offices for shop fronts (v2.2)
│   │   ├── photo_shrubs.npz                  # Shrubs seen in the photos but missing in the game
│   │   ├── poles.json                        # Poles, utility poles and sign plates from the panoramas
│   │   ├── ponti.json                        # Bridge list with the manual deck corrections (v2.0)
│   │   ├── poses.json                        # Calibrated poses of the 366 Street View panoramas
│   │   ├── qa_review.json                    # Log of the photo/map review: findings and actions (v2.2)
│   │   ├── road_profile.npz                  # Magliaso–Pura carriageway centre, edges and width
│   │   ├── roadside_walls.json               # Retaining walls along the route missing from the survey
│   │   ├── signs_panorama.json               # Codes of the cantonal road's panorama sign plates (v2.7)
│   │   ├── strade_extra_v22.json             # Roads to Arosio, Caslano and the Torrazza in LV95 (v2.2)
│   │   ├── sv_coverage.json.gz               # Street View coverage metadata of the whole area (v2.2)
│   │   ├── terrain_colors.json               # Measured base colours of the terrain materials
│   │   ├── trees.npz                         # Trees of the 4 × 4 km corridor from the canopy model (v1.0)
│   │   ├── understory.npz                    # Shrubs and hedges along the route from the canopy model
│   │   ├── vineyard_rows.json                # Vine row directions measured on the orthophoto (v2.4)
│   │   ├── wall_caps.json                    # Photo-checked crest heights of the walls near the route
│   │   └── wall_materials.json               # Wall materials (stone, concrete, plaster) from photos (v2.2)
│   └── verifica/                             # Checks, reviews, screenshots and renders
│       ├── canopy_v2.0.json                  # Vegetation checks of the v2.0 level, baseline (v2.1)
│       ├── check_level.json                  # Automatic level checks: problem counts and places (v2.4)
│       ├── concordanza_percorso.png          # Plot of photo/game agreement along the cantonal road (v1.0)
│       ├── drive_test.json                   # Virtual drive test: events per road class and place (v2.4)
│       ├── drive_test_v2.1.json              # Virtual drive test of the v2.1 level, baseline (v2.2)
│       ├── metrics_final.json                # Per-view segmentation metrics of VERIFICA.md (v1.0)
│       ├── metrics_full1.json                # Per-view metrics before the last correction round (v1.0)
│       ├── REGISTRO.md                       # Log of map/reality differences, action, status (v2.1, v2.2)
│       ├── revisione.json                    # Per-road Street View review data for REVISIONE.md (v2.2)
│       ├── REVISIONE.md                      # Road-by-road review against Street View (v2.2)
│       ├── signs_v2.7.json                   # Every road sign placed: position, facing, plates (v2.7)
│       ├── signs_v2.7.png                    # Contact sheet of the Swiss sign plates drawn (v2.7)
│       ├── STRADE.md                         # Every road of the network with each check's status (v2.1)
│       ├── VERIFICA.md                       # Photo vs game segmentation agreement, 1464 views (v1.0)
│       ├── ZONE.md                           # Per-municipality figures and check status (v2.1)
│       ├── zone_report.json                  # Data of ZONE.md and STRADE.md, per zone and road (v2.1)
│       ├── mappa/                            # Render sheets: roads, trails, villages, flagged spots (v2.0)
│       ├── ponti/                            # Table and profile sheets of every bridge (v2.0)
│       ├── screenshots/                      # In-game README views (v2.6), v2.7 checks and v2.8 driver/chase/aerial shots
│       │   ├── signs_v2.7/                   # In-game shots of each sign kind, near and far (v2.7)
│       │   └── v2.7/                         # In-game test of the final zip: views, load time, fps (v2.7)
│       ├── v2.1/                             # Renders of markings, STOP, railway, Tresa bridge (v2.1)
│       ├── v2.3/                             # Before/after renders: Magliaso road, thinned woods (v2.3)
│       ├── v2.4/                             # Before/after renders: road surfaces, houses, river (v2.4)
│       ├── v2.7/                             # Marking renders, unpaved-track checks, game test plan (v2.7)
│       │   └── unpaved/                      # Before/after in-game shots and drives, unpaved tracks (v2.7)
│       └── v2.8/                             # Checks of the nine patches and of the chained build (v2.8)
│           ├── final_test_plan.md            # In-game test plan of the whole zip before release (v2.8)
│           ├── build/                        # Chained-build check: digest, object feet, clearances (v2.8)
│           ├── catenary/                     # Report, before/after renders: railway overhead line (v2.8)
│           ├── houses/                       # Report, before/after renders: gutters, aerials, PV (v2.8)
│           ├── lake/                         # Report, before/after renders: lake piers and boats (v2.8)
│           ├── lamps/                        # Report, before/after renders: village street lamps (v2.8)
│           ├── paved_edges/                  # Report, before/after renders: paved edges made flush (v2.8)
│           ├── roadside/                     # Report, map, before/after renders: delineators, poles (v2.8)
│           ├── signs/                        # Report, before/after renders: warning, parking signs (v2.8)
│           ├── understory/                   # Report, before/after renders: darker forest floor (v2.8)
│           └── wall_fill/                    # Report, before/after renders: backfill behind walls (v2.8)
└── web/                                      # Project website (GitHub Pages)
    ├── README.md                             # Website files, publishing and DNS setup
    ├── CNAME                                 # Custom domain of the website on GitHub Pages
    ├── index.html                            # The website's single page: map, drives, pictures, download
    ├── map.svg                               # Map of the playable area, roads and spawn villages
    ├── style.css                             # Website styles: map-paper colours, Swiss sign blue
    ├── img/                                  # In-game screenshots resized for the site, with thumbnails
    └── tools/                                # Scripts that draw the site's map and images
        ├── make_images.py                    # Resizes game screenshots into web/img/, full and small
        └── make_map.py                       # Draws map.svg from area.polygon() and the OSM extract
```

## Where to read more

| If you want to… | Read |
|---|---|
| see what changed in each version | [`CHANGELOG.md`](CHANGELOG.md) |
| read the notes of a single release | [`beamng/RELEASE_v2.7.md`](beamng/RELEASE_v2.7.md) and the other `RELEASE_v*.md` |
| see every road sign placed in v2.7 | [`beamng/verifica/signs_v2.7.json`](beamng/verifica/signs_v2.7.json) |
| run the pipeline, or understand what each script does | [`beamng/README.md`](beamng/README.md) |
| know what's in the level and how accurate it is (this text also ships inside the mod) | [`beamng/pipeline/README_livello.md`](beamng/pipeline/README_livello.md) |
| look at the road-by-road review against Street View | [`beamng/verifica/REVISIONE.md`](beamng/verifica/REVISIONE.md) |
| see the status of every road and village | [`beamng/verifica/STRADE.md`](beamng/verifica/STRADE.md), [`beamng/verifica/ZONE.md`](beamng/verifica/ZONE.md) |

## The panorama dataset

The project started from a dataset of Street View panoramas along the Strada Cantonale from Magliaso to Pura (45.981686, 8.878474 → 46.001760, 8.860159, 3.7 km, almost all from October 2022). **The images are not in the repository**: the `panorami/`, `viste/` and `storici_2013_2014/` folders (9.4 GB) stay local. The repository contains the metadata and the scripts to download them again.

| Folder / file | Contents |
|---|---|
| `panorami/` *(local only)* | 360° equirectangular panoramas, 6656 × 3328, one every ~10 m; named `NNNN_<panoId>.jpg` (NNNN = order along the road) |
| `viste/` *(local only)* | 16 perspective views per panorama (FOV 90°, 1600 × 1200): 8 directions × 2 tilts |
| `panoramas.csv` / `.json` | for each panorama: lat, lon, altitude, date, camera heading, pitch and roll, distance along the road |
| `panoramas.geojson` | panorama positions (opens in QGIS or on geojson.io) |
| `cameras.json` | for each view: file, GPS position, altitude, direction (yaw), pitch, FOV: known poses for photogrammetry |
| `panoramas_all_dates.json` | also the historical panoramas (2013/2014) of the same stretch, not downloaded |
| `sv_capture.py`, `expand.py`, `finalize.py` | the (re-runnable) scripts that download and prepare the images |

The views are named `NNNN_<panoId>_<direction>_p<pitch>.jpg`: the direction is relative to the direction of travel (`fwd`, `fwd_r`, `right`, `back_r`, `back`, `back_l`, `left`, `fwd_l`, in 45° steps), `p00` is the horizon and `p25` looks 25° upwards (façades, roofs, slopes).

**Coverage.** Almost all images are from October 2022; three panoramas from 2013 cover the spots where 2022 is missing. Between 1.28 and 1.36 km from the start (45.9858, 8.8692 → 45.9869, 8.8694) there is a gap of about 110 m with no panoramas on any nearby date. The pole and shadow of the Google car are visible at the bottom of the `p00` views towards `fwd`/`back`.

**3D reconstruction.** The `viste/` work with COLMAP, RealityCapture and Metashape (known intrinsics: fx = fy = 800 px, cx = 800, cy = 600, no distortion; the GPS positions in `cameras.json` serve as georeferencing); Metashape also accepts the spherical panoramas ("Spherical" camera); for Gaussian Splatting or NeRF go through the `viste/` with COLMAP first.

## Credits

- [**wintrymichi**](https://github.com/wintrymichi): creator and maintainer of the map.
- [**LoJaeggli09**](https://github.com/LoJaeggli09) (Elia Jaeggli): the v2.8 additions (street lamps, catenary, piers and boats, house details, roadside furniture, the release workflow).
- [**ginobaby**](https://github.com/ginobaby) (popular cat): the first v3 build (smooth curved roads and walls, the v3 polish).

## Licence

The map, the mod and this repository are **free for non-commercial use** under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). You can play, share and modify them, provided you give appropriate credit, indicate any changes, and comply with the licence terms.

**Commercial use of my original work is not permitted without my prior written permission and a separate commercial licence, subject to a fee agreed in writing.** This includes selling or commercially redistributing the map or derivative mods, paid downloads, paywalls, paid bundles, subscriptions, and commercial services incorporating my work. Advertising-supported use may also require permission depending on the circumstances. To request a commercial licence, contact [**info@wintrymichi.ch**](mailto:info@wintrymichi.ch).

Third-party materials remain subject to their respective licences. OpenStreetMap data and extracts remain under the ODbL. The full terms are available in [`LICENSE`](LICENSE).

## Sources and licences

- © swisstopo: swissALTI3D, swissSURFACE3D, SWISSIMAGE, swissBUILDINGS3D 3.0, swissTLM3D, swissNAMES3D (open geodata of the Swiss Confederation).
- Official survey: Ufficio del catasto e dei riordini fondiari (Cadastre and Land Consolidation Office), Canton Ticino (geodienste.ch).
- Federal Register of Buildings and Dwellings (Federal Statistical Office).
- © OpenStreetMap contributors, ODbL 1.0: the extracts in `beamng/dati/osm_*.json.gz` are under the ODbL.
- Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA): distant landscape.
- Google Street View: visual reference only; no image is distributed.
- Street-level photos from Mapillary (CC BY-SA 4.0), Panoramax and KartaView contributors (under their open licences): used to check hedges, fountains and roof heights; only positions and votes derived from them are kept (`beamng/dati/street_*.json`), no image is distributed.
