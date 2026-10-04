BeamNG.drive (0.39) map of the **Malcantone**, version 2.7: the [v2.6](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.6) map with the Swiss road signs on the whole network. Same area, roads, buildings, trees and grass.

**Installation:** copy `magliaso_pura_v2.7.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

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

**The STOP, give-way and bus-stop signs now face the traffic.** Up to v2.6 their plates were wound the wrong way for the game, which draws a triangle from one side only: approaching cars saw the grey back. Those plates are turned (2,152 triangles), and the STOP and give-way plates are drawn again.

## Limits

- A sign is there only where OpenStreetMap maps it or records the rule that needs it: warning signs, direction signs and parking rules nobody mapped are missing, and a sign the rule implies (a crossing, a zone) can stand a few metres from the real one.
- On the Magliaso–Pura cantonal road the panorama plates stay plain-coloured, except 10 plates (6 poles) where OpenStreetMap or a rule says which sign stands there.
- The village name is on the sign only where the commune has a single village; in Alto Malcantone, Tresa, Lema, Bioggio and Lugano the 50 "generale" sign stands without a name.
- 387 signs of the OSM extract are on roads beyond the edge of the map and are not built; 8 found no free ground beside the road.

The list of every sign placed is in [`beamng/verifica/signs_v2.7.json`](https://github.com/wintrymichi/magliasinaNG/blob/main/beamng/verifica/signs_v2.7.json).

## How it is made

`beamng/pipeline/patch_signs.py` turns the v2.6 release zip into this one (`signs_ch.py` draws the signals, `signs_net.py` decides where they stand):

```bash
python patch_signs.py magliaso_pura_v2.6.zip magliaso_pura_v2.7.zip --report ../verifica/signs_v2.7.json
```

Sources: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); official survey of Canton Ticino (geodienste.ch); Federal Register of Buildings and Dwellings (FSO); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA). The Google Street View panoramas were used only as a visual reference: the mod contains no Street View images.
