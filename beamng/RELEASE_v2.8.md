<!-- draft: the release workflow refuses to run while this line is here. Remove it once "Checked in the game" below holds the test of the whole zip in BeamNG.drive (beamng/verifica/v2.8/final_test_plan.md) and the table of screenshots is at the top. -->
BeamNG.drive (0.39) map of the **Malcantone**, version 2.8: the [v2.7](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.7) map with the asphalt flush with the ground, street lamps in the villages, delineators and wooden pole lines between them, the railway's overhead line, piers and boats on the lake, gutters, aerials and solar panels on the houses, the warning and parking signs nobody mapped, undergrowth in the woods and the ground behind the walls shaded like the terrain. Same area, roads and buildings.

**Installation:** copy `magliaso_pura_v2.8.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

## Asphalt flush with the ground

Up to v2.7 the paved roads, pavements and yards stood on the ground like a slab, with a trench beside them: their edge 21 cm over the ground beside it (median; 46 cm on one edge in ten). Now (`patch_paved_edges.py`) the ground beside them is raised to 4 cm under their edge: 7 cm between asphalt and ground 30 cm from the edge (median), and only 2.6 % of the edges more than 30 cm over the ground instead of 25 %. The asphalt itself does not move, so the roads drive as before (`drive_test.py`: the same or fewer knocks). Beside guard rails, fences, walls, houses, the railway and bridge parapets the step stays as it was.

## Street lamps

Up to v2.7 only the Magliaso–Pura cantonal road had street lamps (68 where the panoramas show them, and 5 more). Now (`patch_lamps.py`) 1,779 more stand along the roads of the villages, about one every 30 m on one side of the road, with the same model: where at least six buildings of the Federal Register stand within 45 m, on the pavement or the verge, never on a carriageway, a wall, a bridge or in a building, clear of junctions, signs, furniture and trees. In the old towns, where the lamps hang on the walls, there are few.

**The cantonal road's lamps light at night.** Their lights, described for v2.4, never reached a release (the release builds take the cantonal road's objects from the v1.1 zip, older than the lights); the 73 lamps of v2.7 have them now. The new lamps do not light: what that costs in frame rate is still to be measured.

## Between the villages

White delineator posts with the black band stand on both sides of the main roads (6 m and wider) outside the villages, every 50 m on the straight and closer in the bends (507), except where a guard rail, a wall or a building already marks the edge; they have no collision, like the plastic posts a car knocks over. Lines of the game's wooden poles, one every 45 m with a cable between them, follow the country roads past the scattered houses (628 poles in 124 lines); a pole stops a car (`patch_roadside.py`).

## Signs

v2.7 put up the signs OpenStreetMap maps and those its rules imply. Now (`patch_signs_more.py`) also, by the Swiss rules: a curve warning 150 m before the sharp curves of the main roads outside the villages that come after a straight (a double curve where several follow), the warnings of the level crossings (with or without barriers), falling rocks where OSM records them, and the blue P at the entrance of the public car parks: 80 signs, drawn after the Swiss standard like the others. Not every bend of a mountain road gets one, only the unexpected ones.

## The railway's overhead line

The FLP (and the SBB line where it crosses the map) ran without its catenary. Now (`patch_catenary.py`) steel masts stand beside the tracks every 50 m (closer in the bends), on the outside of the bends, with a cantilever, a messenger wire, droppers and the contact wire 5.5 m over the rails, staggered from mast to mast: 201 masts over 9.9 km of track. The masts stop a car, the wires do not.

## Piers and boats on the lake

The 23 piers OpenStreetMap maps on the Swiss shore stand over the water (11 at Caslano, 4 at Magliaso, 4 at Agno, 3 at Ponte Tresa, 1 at Collina d'Oro): wooden decks on posts, or floating pontoons with their guide piles, 954 m in all. At the piers where boats moor, 137 boats lie bow to the pier: motor boats under their covers or open with an outboard, and sailing boats with their mast. They are drawn by the pipeline (low-poly, plain colours), not the real ones (`patch_lake.py`).

## The houses

Every pitched roof has its gutters along the eaves, in zinc or copper, and downpipes down the corners; and by a rule, TV aerials on a share of the older houses, satellite dishes turned to the satellites, and solar panels on some roofs facing south: 305 km of gutters, 38,407 downpipes, 1,903 aerials, 1,483 dishes, 398 roofs with panels (`patch_house_details.py`). They have no collision.

## The woods

The forest floor had the colour measured in the panoramas on the sunlit forest edges, a light brown that showed between the trunks and, from afar, between the crowns. Now it is a darker olive, the leaf litter in the shade. Low shrubs (0.6–1.5 m, the game's own bush models) grow on it around the camera, within 60 m, never on roads, paths, walls, buildings or the railway: the game places them as it goes, nothing is stored per shrub and they have no collision (`patch_understory.py`).

## The ground behind the walls

Behind every retaining wall the terrain is lowered (a 1.5 m grid cannot hold a step inside a 0.3 m wall) and a mesh puts the ground back at its height: 63 ha in all. Up to v2.7 every triangle of that mesh was lit on its own, so the slopes behind the walls showed flat facets and saw teeth beside the smoothly shaded terrain. Now (`patch_wall_fill.py`) the mesh has the normals of the ground it restores: the same shapes, lit smoothly, with the same collision. The game's grass no longer grows through it, nor over walls lower than the grass (200,441 terrain vertices keep their material without grass); at the foot of the taller walls and on the meadows the grass stays.

## Checked

- **Without the game:** each change on its own with the pipeline's 3D renderer, before and after at the same views ([`beamng/verifica/v2.8/`](https://github.com/wintrymichi/magliasinaNG/tree/main/beamng/verifica/v2.8), one folder per change); the automatic checks of the whole level on v2.7 and on v2.8 (*v2.8 build test* workflow): `check_level.py` RESULT_CHECK_LEVEL, `drive_test.py` RESULT_DRIVE_TEST.
- **In the game:** to be written after the test (load time, frame rate and memory against v2.7 at the same views, what was found and fixed).

## Limits

- Street lamps, delineators, wooden poles, catenary masts, aerials, dishes and solar panels stand where a rule puts them, not where they really are: no open data has them.
- The new street lamps do not light at night.
- The boats do not move with the waves; the undergrowth, the house details and the delineators have no collision.
- Beside guard rails, fences, walls, houses, the railway and bridge parapets the asphalt keeps its step over the ground.
- Not every bend of a mountain road has its warning sign, only the sharp curves after a straight on the main roads.

## How it is made

The nine v2.8 patch scripts turn the v2.7 release zip into this one, the ground first and then what stands on it; `patch_v2_8.py` runs them in this order, and the `release_v2.8.yml` workflow runs it on a GitHub server:

```bash
python patch_v2_8.py magliaso_pura_v2.7.zip magliaso_pura_v2.8.zip
# = patch_paved_edges.py, patch_wall_fill.py, patch_understory.py, patch_lamps.py, patch_roadside.py,
#   patch_catenary.py, patch_signs_more.py, patch_lake.py, patch_house_details.py, one after the other
```

Sources: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); official survey of Canton Ticino (geodienste.ch); Federal Register of Buildings and Dwellings (FSO); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA). The Google Street View panoramas were used only as a visual reference: the mod contains no Street View images.
