# Changelog

What changed in each version of the map, newest first. The release notes that go with each zip are in [`beamng/`](beamng) (`RELEASE_vX.Y.md`); the technical notes for each version (which script does what) are in [`beamng/README.md`](beamng/README.md).

## v2.8 (in progress, not released)

- **The ground behind the retaining walls shaded like the terrain.** Behind every retaining wall the terrain is lowered (a 1.5 m grid cannot hold a step inside a 0.3 m wall) and a mesh puts the ground back at its height: 63 ha in all. Up to v2.7 every triangle of that mesh was lit on its own, so the slopes behind the walls showed flat facets and saw teeth, lighter and darker, beside the smoothly shaded terrain (for example along the walls at Ponte Tresa, Agno and below the cantonal road to Pura). Now (`patch_wall_fill.py`) the mesh has the normals of the ground it restores, computed like the terrain's own, and the terrain's own normal where it meets the terrain: the same shapes, lit smoothly. Same geometry and collision as before.
- **No grass through the ground behind the walls, nor over low walls.** The game's grass grew on the terrain lowered under that mesh and stood through it, and on the foot of the walls lower than the grass it stood over their top. There the terrain keeps its material without the game's grass (200,441 terrain vertices, 0.3 % of the terrain); at the foot of the taller walls and on the meadows the grass stays.
- Checked so far with the 3D renderer of the pipeline (before and after at the same views: `beamng/verifica/v2.8/wall_fill/`); the test in BeamNG.drive is still to be done.
- **Street lamps in the villages.** Up to v2.7 only the Magliaso–Pura cantonal road had street lamps (68, where the panoramas show them, and 5 more elsewhere). Now (`patch_lamps.py`) 1,779 more stand along the roads of the villages, about one every 30 m on one side of the road, with the same model: where at least six buildings of the Federal Register stand within 45 m, on the pavement or the verge beside the carriageway, never on a carriageway, a wall, a bridge or in a building, clear of junctions, signs, furniture and trees. A plausible rule, not the real places: there are no open data on street lamps. In the old towns, where the lamps hang on the walls, there are few.
- **The street lamps light at night.** The lights under the lamp heads described for v2.4 never reached a release: the release builds take the cantonal road's objects from the v1.1 zip, older than the lights. The 73 lamps of v2.7 now have them; the new lamps light only in a variant whose frame rate is still to be measured in the game.
- Street lamps checked so far with the 3D renderer (where they stand: `beamng/verifica/v2.8/lamps/`); frame rate, memory and the lights at night are still to be checked in the game.
- **Darker ground in the woods.** The forest floor had the colour measured in the panoramas on the sunlit forest edges along the cantonal road, a light brown that showed between the trunks and, from afar, between the crowns. Now (`patch_understory.py`) it is a darker olive, the leaf litter in the shade (62, 66, 42 instead of 102, 98, 67).
- **Delineators and wooden pole lines between the villages.** Up to v2.7 the roads between the villages had no posts at all. Now (`patch_roadside.py`) white delineator posts with the black band stand on both sides of the main roads (6 m and wider) outside the villages, every 50 m on the straight and closer in the bends (507), except where a guard rail, a wall or a building already marks the edge; and lines of the game's wooden poles, one every 45 m with a cable between them, follow the country roads past the scattered houses (628 poles in 124 lines). A rule, not their real places: there are no open data on them.
- **Undergrowth.** Low shrubs (0.6–1.5 m, the game's own bush models the map already uses) grow on the forest floor around the camera, within 60 m, never on roads, paths, walls, buildings or the railway. The game places them as it goes: nothing is stored per shrub and they have no collision. To be checked in the game, with the frame rate.

## v2.7

- **Swiss road signs on the whole network** (286 new signs): pedestrian crossings, roundabouts, one-way streets and no entry, 30 zones and meeting zones, speed limits, the general 50 with the village name on the main roads, and every sign mapped one by one in OpenStreetMap. Drawn after the Swiss standard, texts in Italian, on poles at the right edge of the road for the traffic that reads them.
- **STOP, give-way and bus-stop signs face the traffic.** Up to v2.6 their plates were wound the wrong way for the game: approaching cars saw the grey back.
- **The plates of the Magliaso–Pura cantonal road are real signs:** 17 plates seen in the panoramas are drawn as the signal they are (pass on the right, zone 30, crossings, parking, direction signs, curve, STOP, …); 5 that were no sign are gone.
- **Checked in the game** (the whole v2.7): every kind of sign the right way round from the traffic, about 155 s to load the first time and 69–72 s after, 74–131 fps at the test views, no level errors; screenshots in `beamng/verifica/screenshots/v2.7/`. Fixed on the way: plates upside down, the game showing the old converted shapes, textures that did not load because their sides were not powers of two, dark rectangles around the panorama plates kept as measured.
- **Road markings redrawn as they are painted in Switzerland.** Up to v2.6 the markings of the network (208 km of roads outside the cantonal road) were the raw trace of the orthophoto: wobbling lines, dashes of different lengths, a line traced twice (the paint and the light concrete gutter beside it), solid lines broken wherever a car stood, pedestrian crossings made of a few yellow blobs, white blobs left by cars, glare and manholes. Now (`markings_clean.py`, into the zip with `patch_markings.py`):
  - lines follow the road smoothly (a quadratic fit over 14 m, which keeps the curves);
  - dashed lines have one dash length and one period per stretch, at the Swiss values where the measure is close (3 m dashes every 6 or 9 m in most places), with the dashes a car hid put back;
  - solid lines continue under parked cars and shadows (gaps up to 9 m) and under trees (up to 150 m, where the photo is hidden), never across a junction;
  - doubled lines and the gutter beside the edge line are gone;
  - 99 pedestrian crossings are standard Swiss ones (yellow bars 0.5 m wide and 0.5 m apart, across the whole carriageway, the lines along the road stopping 0.5 m before them), and 10 marked crossings of OpenStreetMap that the photo doesn't show (under a tree or a car) are added;
  - stop and give-way lines and the bars of hatched areas are clean rectangles; 1320 blobs that are neither a strip nor an arrow or letter are gone.
  - no paint on gravel and dirt: the light stones and puddles the orthophoto showed there (white pieces lying on the gravel above Arosio) are gone.
- The cantonal road Magliaso – Pura keeps its own markings (measured in the photos, state of October 2022).
- **Dirt and gravel roads and paths are part of the ground.** Up to v2.6 every unpaved track (36 ha of dirt and 10 ha of gravel roads, 19 ha of paths) stood on the terrain like a slab: the terrain under the road meshes was carved 0.1 m under the lowest face within 1.5 m, which left a trench on both sides, and the edge of the track showed about 0.3 m above the ground (median of the outer edges; 0.6 m at the 90th percentile). Now (`patch_unpaved.py`) the terrain around them is raised to their surface and fades back to the ground within 4.5 m, and their outer edges are lowered onto it: between track and ground there are 1–2 cm (median; under 5 cm on 93 % of the edges). The terrain stays under every road face; where a track runs on a wall or a bridge, and where it meets an asphalt road, nothing changes.
- **Wooded mountains again.** Since v2.3 the forest away from the roads was thinned to keep the game fluid: seen from the valley the slopes looked like a mountain with a few scraggy trees. Now every tree measured in the area is back (`far_trees.py`, into the zip with `patch_far_trees.py`): near the roads the same trees as before; farther away a lighter drawn tree (round or narrow broad-leaved, or a fir, in three shades from the orthophoto colour) that the game draws as a flat picture of itself beyond about ten metres, two triangles per tree.

## v2.6

- **New grass.** Up to v2.5 the grass was drawn by the pipeline in one texture without transparency maps: in the game it showed as dark opaque cards, and only up to 50 m. Now the meadows and gardens use the game's own grass and flower textures (colour, opacity, normal, roughness and ambient occlusion maps, light through the blades), laid out like the game's Italy level: short grass up to 50 m around the camera, short and long grass up to 120 m, meadow flowers (daisies, buttercups, geraniums, poppies), mown lawns in the gardens.
- Measured in the game: 72–111 fps at the test points on meadows, gardens and the cantonal road (v2.5: 82–128 at the spawn points).

## v2.5

The first version measured inside BeamNG.drive (0.39.4, on a PC with 16 GB of RAM, RTX 4070). The v2.4 level loaded in 215 s
(371 s through BeamMP) and then wanted more memory than the PC had: minutes on the loading screen and the whole PC lagging.
v2.5 has the same geometry, built so that the game needs much less:

- **7916 → 2188 objects:** the 128 m blocks of buildings, walls, road surfaces, guardrails, water and vineyards are merged 3 × 3.
- **38.2 → 19.7 million vertices:** the meshes were written with three own vertices per triangle; now the triangles share them (positions and texture coordinates unchanged, checked).
- **Road edges:** the skirts and kerb faces along straight stretches with fewer triangles, within 4 mm (15.9 → 15.3 million triangles).
- **Detail by distance:** guardrails are no longer drawn beyond about 600 m, fences 400 m, painted markings 500 m, walls 1.2 km, vineyards 1 km, buildings and roads 3 km (before: up to 12 km). Sun shadows up to 800 m instead of 1600.
- **Result in the game:** 60 s to load once the game has converted the shapes (about 145 s the first time), 82–128 fps at the spawn points.

The game still needs about 12 GB of memory at its peak: on a 16 GB PC close other programs (browser, Discord, ...) before playing.

## v2.4

- **Houses visible from every side.** The game draws only one side of each wall. Up to v2.3, 8.6 % of the wall area faced inwards (L- and U-shaped buildings, courtyard buildings, rows of houses): from some angles the houses were transparent, with floating roofs. Now the facing of each wall is decided with a ray test and inverted walls drop to 0.06 %; where the facing can't be decided the wall is double-sided, and there are soffits under the eaves.
- **Magliaso roundabout, the climb towards Pura.** The "cube" sticking out of the asphalt at the junction was the top of a retaining wall covered by the road, which the map raised by 16 cm; the "square" in the middle of the carriageway was the kerb of the traffic island removed in 2022. Now the walls that the panoramas see as pavement are flush (487) or removed where the ground is flat (37), and that kerb is road.
- **Dirt, gravel and paving where they really are:** the OpenStreetMap surface (otherwise swissTLM3D's) on every road and trail: the survey's roads, previously all asphalt, now have 36 ha of dirt, 9.4 ha of gravel and 1.2 ha of setts and cobblestones in the old towns. Textures drawn with the colour measured on the orthophoto; in the game the grip changes too.
- **Grass and flowers** on the meadows and in the gardens around the camera, **palms** (352) in the gardens near the lake, **rows** in 475 vineyards (465 km, in the direction seen in the orthophoto), **water in the rivers** (30 ha, under the bridges too).
- **Materials and light:** ambient occlusion for render, plinths and roofs, walls darker towards the ground, street lamp light at night, a little more haze over the lake.

## v2.3

- **Magliaso, the cantonal road towards Pura at the junction with Via Piscicoltura.** For about 60 m, right after the junction, the carriageway tilted towards the wall that separates it from Via Piscicoltura, lower down: at the edge it was up to 2.2 m below the real ground, with a dip as if the asphalt had collapsed. The surface computation took that wall for a bump and merged the two roads into a single surface. Now the wall is recognised and each road sits at its own height: on the axis of the cantonal road the largest deviation from the real ground goes from 1.70 m to 0.09 m, on Via Piscicoltura from 0.53 m to 0.24 m. The virtual drive test no longer finds any twists or lifted wheels there (in v2.2: twist 9.6, wheels lifted by 21 cm). The same fix improves another stretch of the cantonal road towards Pura (about 1.3 km from Magliaso); along the whole 3.7 km the points more than 35 cm from the real ground go from 110 to 72.
- **Lighter woods to draw.** Up to v2.2 every measured tree within 150 m of a road was in the map: slopes crossed by hairpins, like the pass above Gravesano seen from the village, were as dense as the real forest and the game slowed down when looking at them. Now all the trees within 30 m of roads and 5 m of trails remain; further away the forest is thinned keeping the tallest ones (up to 100 m from the road the tallest in every square 11–17 m across, beyond that in every 32 m square). In total 160,748 trees and shrubs instead of 239,753 (−33 %); on the slope of the pass above Gravesano 40 % fewer (from 6,165 to 3,722 trees within 700 m). Along the roads, in the first 30 m, the forest is the same as before.

## v2.2

- **New roads.** The pass above Gravesano to Arosio (Stradón da Rós, the «Penudria», with its hairpins), the Ponte Tresa – Caslano – Magliaso cantonal road and Via Torrazza in Caslano ended at the edge of the map: beyond, there was only terrain. Now they are real roads (7.2 km more) with a 100 m corridor of buildings, trees and walls, reviewed on Street View like the rest.
- **Buildings with façades.** Up to v2.1 every building was a rendered volume with no openings. Now the buildings have a total of 165,533 openings (windows with shutters, roller blinds or modern frames, doors, gates, garages, shop windows, church and barn windows), 5,915 balconies, plinths and 3,348 chimneys, laid out by floor and bay according to the use, period and number of floors in the Federal Register of Buildings. Roofs in curved tiles, flat tiles, stone slabs, sheet metal or flat roofs. All textures are drawn by the pipeline: no photos.
- **Old towns house by house.** swissBUILDINGS3D merges rows of houses into a single block; now every house of the official survey has its own façades, floors, door and colour (4,508 houses in blocks). Floors start from the pavement on the street front, on slopes too.
- **Colours measured in the photos.** The render colour of 3,637 buildings, and the shutter colour where it is clear, come from the Street View panoramas (numerical values only).
- **Shop windows** where OpenStreetMap records a shop, bar or office (173 buildings), **garages** with doors, stone **rustici**.
- **Missing buildings:** 538 buildings of the official survey built after the 3D survey have been added; 14 demolished ones removed.
- **Guardrails across the whole network.** 326 guardrail stretches seen in the Street View panoramas; 9.7 km built on the road edge in addition to the 2.0 km on the Magliaso–Pura cantonal road, which up to v2.1 were the only ones.
- **Walls** with original stone, concrete and render textures; the material comes from the photos where it can be seen clearly.
- **Bus stops** from OpenStreetMap with pole, sign, timetable and shelter.
- **More drivable roads.** The surfaces are continuous between carriageway, pavements and yards and at junctions: the step between two roads that meet is spread over a few metres, while the main carriageways stay as they are. On the same roads as v2.1 the virtual drive test counts 62 % fewer steps on minor roads (1695 → 646) and 20 % fewer on main roads (74 → 59); wheels lifting off the road drop by 56 % on minor roads and 58 % on main roads, hard hits by 24 % and sharp twists by 58 % on minor roads.
- **No obstacles in the passages** under buildings: windows and plinths no longer hang over the road.

## v2.1

Road markings on the whole network from the 10 cm orthophoto, trees out of the roads' clearance envelope, AI traffic with one-way streets and roundabouts, STOP and give-way signs, the FLP and SBB railway, water under the Ponte Tresa border bridge. Details in [`beamng/RELEASE_v2.1.md`](beamng/RELEASE_v2.1.md).

## v2.0

The map grows from the 4 × 4 km corridor of the Magliaso–Pura cantonal road to the whole Malcantone (about 51 km²): the full swissTLM3D road and trail network with a single smooth profile, 167 bridges, the Magliaso–Gravesano cantonal road. Details in [`beamng/RELEASE_v2.0.md`](beamng/RELEASE_v2.0.md).

## v1.0 and v1.1

Only the 3.7 km of Strada Cantonale between Magliaso and Pura, rebuilt from the Street View panoramas; v1.1 smoothed the roads and cleared the carriageway.
