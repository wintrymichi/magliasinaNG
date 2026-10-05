# Malcantone: Magliaso, Pura and surroundings (BeamNG.drive 0.39)

A 1:1 scale reconstruction of about 52 km² of the Malcantone (Canton Ticino, Switzerland), between Ponte Tresa, Caslano, Magliaso, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano and Sessa. At its centre are the 3.7 km of Strada Cantonale between Magliaso and Pura from the 1.x versions, rebuilt from the 366 Street View panoramas of the route (almost all from October 2022). To the east is the cantonal road from Magliaso to Gravesano: along the lake to Agno, then along the foot of the mountains through Bioggio and Manno. Since v2.2 there are also the pass above Gravesano to Arosio (the Stradón da Rós, the «Penudria», with its hairpins), the cantonal road from Ponte Tresa through Caslano to Magliaso and, in Caslano, the village from the station to the lake and Via Torrazza along the shore up to the Torrazza. The rest of the area comes from the official data of swisstopo and Canton Ticino.

## How to play

- **Install:** copy the zip, without unpacking it, to `Documents/BeamNG.drive/current/mods/` and remove older versions of this map: they all use the same level name. In the game: *Freeroam* → *Malcantone - Magliaso, Pura e dintorni*.
- **Memory:** the game needs about 12 GB at its peak; close other programs before loading the map. The first load takes longer (about 145 s) because the game converts the shapes; after that about 60 s.
- **Level:** `magliaso_pura`.
- **Spawn points:**
  - `spawn_magliaso` (default, at the Magliaso junction), `spawn_mid` (halfway up the climb) and `spawn_pura` (at the top of the cantonal road). Here the cars start in the driving lane, facing towards Pura.
  - One point in every village of the area: `spawn_agno`, `spawn_caslano`, `spawn_bioggio`, `spawn_gravesano`, `spawn_magliaso_paese`, `spawn_manno`, `spawn_pura_paese`, `spawn_aranno`, `spawn_arosio`, `spawn_astano`, `spawn_banco`, `spawn_bedigliora`, `spawn_bosco_luganese`, `spawn_breno`, `spawn_cademario`, `spawn_cassina_d_agno`, `spawn_castelrotto`, `spawn_cimo`, `spawn_miglieglia`, `spawn_molinazzo_di_monteggio`, `spawn_monteggio`, `spawn_neggio`, `spawn_novaggio`, `spawn_ponte_tresa`, `spawn_purasca`, `spawn_sessa` and `spawn_vernate`. For Curio there is `spawn_pura`, 160 m from the village.
- **Everything is drivable:** every road and every trail in the area has a solid surface, including mule tracks, stairways and forest trails.
- **AI traffic:** the AI road network covers all roads open to vehicles, with one-way streets, roundabouts and dual carriageways; roads closed to traffic are avoided.

## What's there and where it comes from

| Element | Source | Accuracy |
|---|---|---|
| Terrain 12.3 × 12.3 km, 1.5 m grid | swissALTI3D 0.5 m and 2 m (LiDAR); Copernicus GLO-30 on the Italian side | height ±0.3 m within the area |
| Roads and trails (about 228 km of roads, 337 km of trails) | swissTLM3D (axes, classes, paving, bridges), Ticino official survey (carriageway boundaries) | smooth profile computed over the whole network at once: heights match at junctions, the gradients are the real ones |
| Bridges (167) | swissTLM3D, checked one by one on the profile and in the views | deck, parapets and piers; the roads under the bridges remain |
| Buildings (12,792) | swissBUILDINGS3D 3.0 (LOD2, roofs included), the official survey's buildings built after the 3D survey, Federal Register of Buildings (use, period, floors), shops from OpenStreetMap | ±0.3–0.5 m; façades with windows, shutters or roller blinds, doors, gates, garages, shop windows, balconies, plinths and chimneys drawn by the pipeline (no photos), house by house in the old towns; render colour and shutter colour measured in the Street View panoramas; roofs in curved tiles, flat tiles, stone slabs, sheet metal or flat |
| Walls | official survey (walls) + retaining walls of the cantonal road derived from the DTM and photos | along the cantonal road the visible height is measured in the photos; original stone, concrete and render textures, the material seen in the panoramas where it's clear |
| Guardrails, railings and fences of the cantonal road | multi-view vote on the photo segmentation, LiDAR where available | position ±0.3 m |
| Guardrails on the rest of the network (v2.2) | Street View panoramas of the whole area segmented along the edges of every road | where the panoramas show them, on the edge of the built road |
| Bus stops (v2.2) | OpenStreetMap | pole, sign, timetable and, where recorded, shelter |
| Road markings of the cantonal road | 10 cm orthophoto (3 m / 6 m dashes, lines, yellow zebra crossings), verified in the photos | state of October 2022 (see below) |
| Street lamps, poles and signs, delineators, street furniture of the cantonal road | triangulated from the photos with the calibrated poses | ±0.3–0.5 m; plates with the shape and colour measured in the photos (without the image of the sign) |
| Trees, hedges and shrubs (about 161,000) | swissSURFACE3D surface model (position, height and crown of every tree), orthophoto | all within 30 m of roads and 5 m of trails with the game's models; farther away every measured tree too, as a lighter drawn model the game shows as a flat picture (v2.7; v2.3–v2.6: thinned beyond 30 m); species approximated with vanilla models, drawn palms in gardens near the lake (v2.4, an estimate); no trunks on the carriageway or less than 1 m from the road edge (0.5 m on trails), no crowns in the clearance envelope (4.50 m above carriageways, 2.50 m above pavements and trails), every plant on the ground |
| Road markings on the rest of the network | SWISSIMAGE 10 cm orthophoto (2024): lines traced along every road, vectorised markings; redrawn to the Swiss standard shapes (v2.7) | only the paint visible in the orthophoto, at its measured position; dashes at the Swiss lengths and periods where the measure is close; solid lines continued under cars (up to 9 m) and under trees (up to 150 m), never across a junction; pedestrian crossings as standard yellow bars across the carriageway, plus the marked crossings of OpenStreetMap the photo does not show |
| One-way streets, STOP and give-way signs, benches and bins on the rest of the network | OpenStreetMap; roundabouts and dual carriageways from swissTLM3D | OSM position, signs on the edge of the road they belong to |
| Road signs of the network (v2.7) | OpenStreetMap: the signs mapped one by one, and the regulation it records (speed limits, 30 zones and meeting zones, one-way streets, zebra crossings, roundabouts) | Swiss signals drawn after the standard (OSStr, SN 640 871), not photographed; mapped signs at the mapped point, the others where the rule puts them, on the right edge of the road for the traffic that reads them |
| Railway (FLP and SBB) | swissTLM3D (axes, heights, gauge, bridges) | real-gauge tracks at the swissTLM3D height, never below the terrain, flush with the road at level crossings; no overhead line, no tracks under the car park of Ponte Tresa station |
| Road and trail surface (v2.4) | OpenStreetMap (`surface`, `tracktype`), otherwise swissTLM3D | asphalt, gravel, dirt, setts, cobblestones; where OSM is silent swissTLM3D applies; transitions from one surface to another follow the OSM ways to within a few metres |
| Grass and flowers (v2.6) | meadow and garden layers of the terrain (official survey) | the game's own grass and meadow-flower textures around the camera: short grass up to 50 m, short and long grass up to 120 m, flowers on the meadows; density estimated, not measured |
| Vineyards (v2.4) | official survey (vineyards), 10 cm orthophoto (row direction) | rows every 2.2 m (typical spacing, not measured) in vineyards within 150 m of roads and trails |
| Rivers (v2.4) | official survey (watercourses at least 2.5 m wide), swissALTI3D | water at the height of the lowest bed within 3 m; under bridges too, not on fords |
| Lake Lugano, distant landscape | swissALTI3D, Copernicus GLO-30 | — |

## 2022 state reproduced on the cantonal road

The October 2022 photos are more recent than the orthophoto and the official survey. Where the sources disagree, the level follows the photos:

- **No road markings** where the road was being resurfaced or was unmarked: s ≈ 1.23–1.27 km, 1.52–1.82 km and 3.64–3.72 km. In the roadworks the new asphalt is darker.
- **Red bands** on both edges in the stretch s ≈ 2.29–2.44 km.
- **Magliaso junction:** the junction had been rebuilt, so the two pedestrian islands and the painted island from the survey have been removed, and the centre line follows the position visible in the photos.

## Version 2.6

- **New grass:** the game's own grass and flower textures (with normal, roughness and ambient occlusion maps) instead of the tufts drawn by the pipeline, which in the game showed up as dark opaque cards. Short grass up to 50 m around the camera, short and long grass up to 120 m (before: 50 m), daisies, buttercups, geraniums and poppies on the meadows, mown lawns in the gardens.

## Version 2.5

- **Lighter for the game, same geometry:** the 128 m blocks are merged 3 × 3 (7916 → 2188 objects), the triangles share their vertices (38.2 → 19.7 million vertices), road skirts and kerb faces along straight stretches have fewer triangles (within 4 mm), and small objects are no longer drawn far away (guardrails beyond about 600 m, walls 1.2 km, buildings and roads 3 km). Sun shadows up to 800 m.
- Measured in BeamNG.drive 0.39.4 (16 GB of RAM, RTX 4070): 60 s to load once the game has converted the shapes (about 145 s the first time), 82–128 fps at the spawn points; the game needs about 12 GB of memory at its peak, so on a 16 GB PC close other programs before playing.

## Version 2.4

- **Houses visible from every side:** the walls that faced inwards (L- and U-shaped buildings, courtyard buildings, rows of houses) and were missing from outside now face outwards; where the facing can't be decided the wall is double-sided; there are soffits under the eaves.
- **Magliaso roundabout, the climb towards Pura:** removed the block that stuck out 16 cm from the asphalt at the junction (the top of a retaining wall covered by the road) and the piece of kerb left in the middle of the carriageway from the traffic island removed in 2022.
- **Dirt, gravel and paving** where OpenStreetMap indicates them (otherwise according to swissTLM3D), with drawn textures and the right ground type for grip: gravel, dirt, setts, cobblestones.
- **Grass and flowers** on the meadows and in the gardens around the camera; **palms** in the gardens near the lake; **rows** in the vineyards; **water** in the rivers; ambient occlusion in the building materials; street lamp light at night; a little more haze over the lake.

## Version 2.3

- **Cantonal road in Magliaso:** at the junction with Via Piscicoltura the carriageway towards Pura no longer drops towards the lower road beyond the wall (previously, for about 60 m, it was up to 2.2 m below the real ground at the edge).
- **Lighter woods:** all trees remain within 30 m of roads and 5 m of trails, further away the forest is thinned; slopes with many hairpins, like the pass above Gravesano, weigh less on the game.

## Version 2.2

- **New roads:** the pass above Gravesano to Arosio (Stradón da Rós, the «Penudria»), the Ponte Tresa – Caslano – Magliaso cantonal road and Via Torrazza in Caslano ended at the edge of the map (beyond, there was only terrain). Now they are real roads, with surface, road markings, guardrails and a 100 m corridor with buildings, trees and walls, reviewed on Street View like the rest of the map.
- **Buildings with façades:** windows with shutters, roller blinds or modern frames, doors, gates, garages, shop windows, balconies, plinths and chimneys on every building, laid out by floor and bay according to the use, period and floors in the Federal Register of Buildings. In the old towns every house has its own façades, floors, door and colour; floors start from the street front, on slopes too. Roofs in curved tiles, flat tiles, stone slabs, sheet metal or flat roofs. All textures are drawn: no photos.
- **Colours from the photos:** the render colour and the shutter colour come from the Street View panoramas where the building is seen (values only, corrected for shadow).
- **Missing buildings** (built after the 3D survey) added from the official survey; demolished ones removed.
- **Guardrails on the whole network** where the panoramas show them, on the edge of the road.
- **Walls** with original stone, concrete and render textures.
- **Bus stops** from OpenStreetMap.
- **More drivable roads:** continuous surfaces between carriageway, pavements and yards and at junctions, verified with a virtual drive test over the whole network.

## Version 2.1

- **Road markings on the whole network**, detected in the 2024 SWISSIMAGE 10 cm orthophoto: centre, lane and edge lines (dashed or solid, in the measured position and rhythm), yellow pedestrian crossings, stop lines, arrows and hatched areas. Only what the orthophoto shows is painted; a line hidden by trees or shadow continues only if it can be seen on both sides (up to 60 m).
- **Trees out of the roads' clearance envelope:** no crown below 4.50 m above carriageways or below 2.50 m above pavements, yards and trails (0.3 m tolerance at the edge). Trees have been moved by at most 3 m or have a narrower model of the same species; very few have been removed. Every plant rests on the ground and no trunk stands inside walls or buildings.
- **AI traffic:** one-way streets (OpenStreetMap), anticlockwise roundabouts and dual carriageways (swissTLM3D); roads with a general traffic ban are avoided.
- **STOP and give-way signs** from OpenStreetMap (drawn Swiss panels, not photographed), **benches and bins**.
- **Railway:** tracks of the FLP Lugano–Ponte Tresa and of the SBB, with level crossings and bridges.
- **The Tresa at Ponte Tresa** has water under the border bridge, up to the weir.

## Version 2.0

- **Enlarged area** from the cantonal road corridor (4 × 4 km) to the whole Malcantone between the four given boundary points, with the terrain widened to 12.3 km.
- **Magliaso–Gravesano cantonal road** (8.8 km): from the Magliaso junction along the lake (Strada Regina) to Agno, then along Via Cantonale and Contrada San Marco through Bioggio and Manno to Gravesano. The area includes 150 m of land beyond the road and the whole slope between the road and the rest of the map.
- **Complete, smooth network.** All swissTLM3D lines (roads, forest roads, trails, mule tracks, stairways) have a surface. The height comes from a single computation over the whole network: it follows the terrain with the real gradients, without the survey noise, and is continuous at junctions and from one stretch to the next. Bridges are real decks; where swissTLM3D marks a bridge over a culvert, the road stays on the ground.
- **The terrain never sticks out above roads and trails**, not even between one vertex and the next of its 1.5 m grid: every vertex whose triangles touch a drivable surface sits 10 cm below the lowest face around it. No drivable surface lies below the bare ground.
- **Walls:** the terrain no longer sticks out in a sawtooth pattern in front of walls. Behind retaining walls the ground stays at its natural level.
- **No obstacles on the carriageway.** Where the survey puts a wall in the middle of a road or trail, the wall is cut. Under the buildings that stand over the road (arcades, the canopy of the Ponte Tresa customs post, an alley under a bell tower) there is a passage. The Agno footbridge spans the cantonal road at a height of about 4 m, and no pier stands on a road.
- **Clear vegetation** on the whole network, not just on the cantonal road.
- **The cantonal road** keeps the surface and all the verified objects of v1.1.

## Version 1.1

- **Smooth roads** on the cantonal road: the surface no longer follows the terrain model point by point, the carriageway cross-section is flat.
- **Bridge at 3.05 km and cantilevered stretch at 3.27 km** at road height, with stone sides.
- **Walls between surfaces at different heights** as steps with a stone face instead of ramps.
- **Carriageway clear** of trees and shrubs.

## Accuracy and verification

- v2.0 is checked automatically over the whole map. The check looks for:
  - holes and steps along every road and trail;
  - terrain above roads and trails, measured on the faces and not just on the vertices;
  - holes in the terrain;
  - drivable surfaces below the bare ground;
  - seams between the pieces;
  - obstacles on the carriageway (walls, buildings, bridges, steps), searched along every road and trail at the height of a car;
  - trees near the carriageway;
  - continuity of the AI network.
- There are also screenshots of the whole area, of every bridge, of the roads and of the villages.
- v2.2: a virtual drive test runs over all roads and trails on the level's surfaces and reports steps, lifted wheels, hits and holes; the map has been compared with the Street View panoramas road by road (coverage, measured buildings, guardrails and walls seen, places compared photo/map).
- The poses of the 366 panoramas of the cantonal road were estimated on the 10 cm orthophoto to about 0.3 m. The verification of the cantonal road compares the photos with in-game screenshots from the same pose. The figures are in the `VERIFICA.md` file and refer to the v1.0 geometry.
- Between 1.28 and 1.36 km of the cantonal road there are no panoramas: there the level is based only on swisstopo data and the official survey.

## Known limitations

- Memory: about 12 GB at the peak (v2.5). On a 16 GB PC with other programs open the game can stall after loading.
- On the Italian side there is only terrain and landscape, without roads, buildings and trees.
- One-way streets come from OpenStreetMap: where OSM doesn't record them, the AI drives the road in both directions.
- Vertical signs (v2.7): where OpenStreetMap maps a sign or records the rule that needs one (speed limits, zones, one-way streets, zebra crossings, roundabouts, the main roads into the villages). Signs nobody mapped (warning signs, direction signs, parking rules) are missing, and a sign the rule implies may stand a few metres from the real one. On the Magliaso–Pura cantonal road the plates seen in the photos are drawn as the signal they are where it could be read (17); bus stops, boards and unreadable plates keep the measured shape and colour. No railway overhead line; guardrails where the Street View panoramas show them.
- The façades are rebuilt from data (use, period, floors) and from the colours seen in the photos: the number and position of windows, balconies and arcades are plausible but not copied one by one.
- Tunnels are not built. The full list, with an issue for each limitation, is in the project README: https://github.com/wintrymichi/magliasinaNG#known-limitations

## Sources and licences

- © swisstopo: swissALTI3D, SWISSIMAGE, swissBUILDINGS3D, swissSURFACE3D, swissTLM3D, swissNAMES3D.
- Official survey: Ufficio del catasto e dei riordini fondiari (Cadastre and Land Consolidation Office), Canton Ticino.
- © OpenStreetMap contributors (ODbL 1.0), extract of 28.9.2026 (completed on 30.9.2026 in the v2.2 corridors): one-way streets, STOP and give-way signs, benches and bins (v2.1); bus stops, shops and businesses (v2.2); road signs, speed limits, zones, crossings and roundabouts (v2.7).
- Federal Register of Buildings and Dwellings (Federal Statistical Office): use, period and floors of the buildings (v2.2).
- Copernicus DEM GLO-30: © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA.
- The Google Street View panoramas were used only as a visual reference (poses, measurements, comparisons): the mod contains no Street View images.
- 3D models of trees, street lamps and street furniture: BeamNG vanilla assets (East Coast USA, Italy), referenced and not copied.
