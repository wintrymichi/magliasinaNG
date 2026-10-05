BeamNG.drive (0.39) map of the **Malcantone**, version 2.7: the [v2.6](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.6) map with Swiss road signs on the whole network, road markings redrawn as they are painted in Switzerland, dirt and gravel tracks flush with the ground, and the wooded slopes back. Same area, roads and buildings.

**Installation:** copy `magliaso_pura_v2.7.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

| | |
|---|---|
| ![Roundabout entry: 2.41.1 over give way](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/signs_roundabout.jpg)<br>*Roundabout entry: 2.41.1 over give way* | ![The 50 "generale" with the village name](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/signs_village50.jpg)<br>*The 50 "generale" with the village name* |
| ![Swiss pedestrian crossing, clean dashes](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/markings_crossing.jpg)<br>*Swiss pedestrian crossing and arrows* | ![Dashed centre line](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/markings_dashed_line.jpg)<br>*Dashed lines at one length and period* |
| ![Track above Arosio, flush with the ground](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/unpaved_arosio.jpg)<br>*Track above Arosio, flush with the ground* | ![Gravesano and the wooded pass](https://raw.githubusercontent.com/wintrymichi/magliasinaNG/main/beamng/verifica/screenshots/v2.7/fartrees_gravesano_pass.jpg)<br>*The pass above Gravesano, wooded again* |

## Road signs

Up to v2.6 the map had the STOP and give-way signs recorded in OpenStreetMap, the bus stops and, on the Magliaso–Pura cantonal road, the plates seen in the panoramas in a single colour. v2.7 adds 286 signs:

| Signs | Where they come from | Placed |
|---|---|---|
| 4.11 pedestrian crossing | every zebra crossing OpenStreetMap records on a road, both directions | 122 |
| 2.41.1 roundabout over 3.02 give way | every road into a roundabout | 40 |
| 4.08 one-way street, 2.02 no entry | the beginning and the end of every one-way street | 31 + 32 |
| 2.59.1 / 2.59.2 30 zone, 2.59.3 meeting zone | every road into and out of a zone | 11 + 17 + 4 |
| 2.30 speed limit, 2.30.1 / 2.53.1 general limit with the village name (4.27 / 4.28) | where the limit changes along a road; the main roads into and out of the villages | 17 + 11 |
| signs mapped one by one (weight, width, height and length limits, no-entry with exceptions, dead ends, narrowing, place names, …) | OpenStreetMap, at the mapped point and facing the mapped direction | 17 |

The signals are drawn by the pipeline after the Swiss standard (OSStr, SN 640 871 colours), with the texts in Italian: no photos. They stand on grey steel poles at the right edge of the road for the traffic that reads them, 0.6 m from the carriageway, with the lowest plate at 2.1 m in the villages and 1.5 m outside.

**The STOP, give-way and bus-stop signs now face the traffic.** Up to v2.6 their plates were wound the wrong way for the game, which draws a triangle from one side only: approaching cars saw the grey back. Those plates are turned, and the STOP and give-way plates are drawn again.

**The cantonal road's plates are real signs.** Up to v2.6 the plates seen in the Magliaso–Pura panoramas were plain-coloured. Each one was looked at again in the photos and 17 of them are now drawn as the signal they are, at the size of the standard, in the measured place and height: 2.33 pass on the right (5), zone 30 with the 16 t limit under it (2), pedestrian crossing (2), parking (2), direction signs to Astano and to Caslano / Pura (2), end of the 60 limit, curve to the right, no entry and STOP. 5 plates that were no sign (a vehicle behind a hedge, a delineator, a utility cabinet, a stone marker, meter boxes) are gone. The bus stops, the information, hiking and street-name boards, the backs of signs and 10 plates the photos do not show well enough keep the measured shape and colour.

## Road markings

Up to v2.6 the markings of the network (208 km of roads outside the cantonal road) were the raw trace of the orthophoto: wobbling lines, dashes of different lengths, lines traced twice, solid lines broken wherever a car stood, crossings made of a few yellow blobs. Now (`markings_clean.py`, `patch_markings.py`) lines follow the road smoothly, dashed lines have one length and period per stretch at the Swiss values, solid lines continue under parked cars and trees, doubled lines and blobs are gone (1320), and 99 pedestrian crossings are standard Swiss yellow bars across the carriageway, plus 10 marked crossings of OpenStreetMap the photo does not show. No paint on gravel and dirt. The cantonal road Magliaso – Pura keeps its own markings (measured in the photos, October 2022). In all: 4240 strips, 62.7 km.

## Dirt and gravel tracks

Up to v2.6 every unpaved track (36 ha of dirt and 10 ha of gravel roads, 19 ha of paths) stood on the terrain like a slab, about 0.3 m above the ground with a trench beside it. Now (`patch_unpaved.py`) the terrain is raised to the track and fades back within 4.5 m, and the outer edges are lowered onto it: 1–2 cm between track and ground (median). Where a track runs on a wall or a bridge, or meets an asphalt road, nothing changes.

## Wooded slopes

Since v2.3 the forest away from the roads was thinned to keep the game fluid, and from the valley the slopes looked bare. Now every measured tree is back (`far_trees.py`, `patch_far_trees.py`): near the roads the same trees as before, farther away 201,634 lighter drawn trees (round or narrow broad-leaved, or firs, in three shades from the orthophoto) that the game draws as a flat picture of themselves beyond about ten metres.

## Checked in the game

On michi's PC (BeamNG.drive 0.39, RTX 4070, 2560 × 1440): the level loads in about 155 s the first time (the game converts the shapes and the tree pictures) and 69–72 s after that; 74–131 fps at the test views; no level errors in the log. Every kind of sign reads correctly from the traffic. The screenshots are in [`beamng/verifica/screenshots/v2.7/`](https://github.com/wintrymichi/magliasinaNG/tree/main/beamng/verifica/screenshots/v2.7) and the measures in `test.json` there.

The checks found and fixed: sign plates upside down; the game showing the v2.6 shapes it had converted before (the changed files carry the date of the patch); plate textures whose sides are not powers of two not loading; and the panorama plates kept as measured showing as dark rectangles around their shape (their outline is now an opacity map).

## Limits

- A sign is there only where OpenStreetMap maps it or records the rule that needs it: warning signs, direction signs and parking rules nobody mapped are missing, and a sign the rule implies (a crossing, a zone) can stand a few metres from the real one.
- On the Magliaso–Pura cantonal road 35 plates (bus stops, boards, backs of signs, plates the photos do not show well enough) keep the measured shape in a single colour, without a picture.
- The village name is on the sign only where the commune has a single village; in Alto Malcantone, Tresa, Lema, Bioggio and Lugano the 50 "generale" sign stands without a name.
- 387 signs of the OSM extract are on roads beyond the edge of the map and are not built; 8 found no free ground beside the road.

- Within about 12 m the far trees look almost black; no road comes that close to them.

The list of every sign placed is in [`beamng/verifica/signs_v2.7.json`](https://github.com/wintrymichi/magliasinaNG/blob/main/beamng/verifica/signs_v2.7.json).

## How it is made

Four patch scripts turn the v2.6 release zip into this one, in this order (the paint follows the flattened tracks):

```bash
python patch_unpaved.py magliaso_pura_v2.6.zip v26u.zip
python patch_markings.py v26u.zip v26m.zip
python patch_far_trees.py v26m.zip v26t.zip trees_area.npz
python patch_signs.py v26t.zip magliaso_pura_v2.7.zip --report ../verifica/signs_v2.7.json
```

Sources: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); official survey of Canton Ticino (geodienste.ch); Federal Register of Buildings and Dwellings (FSO); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA). The Google Street View panoramas were used only as a visual reference: the mod contains no Street View images.
