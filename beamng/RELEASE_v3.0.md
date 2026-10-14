BeamNG.drive (0.39) map of the **Malcantone**, version 3.0: the [v2.8](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.8) map polished up close and from afar, after the feedback on r/BeamNG ("blocky, smeary, lacking detail"). Trees that are trees, woods on every mountain around the map, ground coloured from the aerial photo, the asphalt, walls and paving of the game's Italy level with the wear of the traffic, smooth curves, and the villages lived in: bins, hydrants, recycling points, café terraces, planters, mirrors at blind exits, flower boxes at the windows, woodpiles at the rustici. Same area, roads and buildings.

<!-- screenshots: added after the in-game test, when michi gives the go -->

**Installation:** copy `magliaso_pura_v3.0.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

## Trees, not shrubs

Up to v2.8 many of the 4–9 m trees were drawn with a big model shrunk to about half its size (`tree_aspen_large_b`, `tree_beech_small_d`, `douglasfir_large_a`: about 25,000 trees), which reads as a low ball of leaves, and the crown model sometimes found a false top under the crown of a taller tree and put a small tree there. Now a model is scaled only between 0.75 and 1.6 of its own size, each tree takes the model whose natural height is closest to its own (`vegetation.model_candidates`), and a top under a much taller crown close by is dropped (`vegetation.under_crowns`), for the near and the far trees.

## Woods on every mountain

Every tree of the map came from the canopy model of swisstopo inside the cadastral survey, so outside it (the Collina d'Oro, the Italian side of the Tresa and of the lake, the ridges of the Malcantone beyond the drivable area) the mountains were meadow up to the top, with the edge of the survey drawn across them. Now the forest of ESA WorldCover 2021 (10 m, CC BY 4.0, both sides of the border; `download_worldcover.py`) is planted with far trees on the whole terrain block (`forest_fill.py`): about one tree every 14 m on 64 km² of forest, their heights, crowns and colours drawn from the trees measured in the woods of the area, more conifers higher up. The terrain there takes WorldCover's land cover (forest floor, meadow, rock, villages) with natural, wavy edges, and the distant backdrop is coloured by it too (`backdrop.py`).

## Ground coloured from the aerial photo

Up to v2.8 each ground material had one flat colour and its detail faded out at 80 m, so the ground looked smeared. Now each material has a colour map over the whole terrain taken from the orthophoto (`terrain.base_color_maps`, limited so that it does not copy shadows and crowns), the detail reaches 160 m with stronger relief, and the steep banks over 40° have their own material (forest soil with roots and a rocky macro texture) instead of stretched meadow.

## Vanilla asphalt and its wear

The carriageways, yards, pavements and paths have the asphalt of the game's Italy level with its macro detail map (`italy_mats.py`, one tile every 4 m, the detail every 40 m, so no repeating pattern); up to v2.8 the same texture without its detail, every 1.25 m. On it (`road_wear.py`), with Italy's own road overlays, the way Italy lays them: lighter and darker patches over the whole carriageway, every lane the two tyre tracks, now and then a cracked and patched stretch of 15–45 m, and every edge a light band of dust; all of them stop at the edge of the road they meet. Translucent strips a few millimetres over the asphalt, without collision.

The white edge lines are laid from the edge of the road mesh, measured every metre and smoothed, instead of the AI road's width: up to v2.8 about a tenth of them wandered off the asphalt, now about 1 %.

## Vanilla walls and paving

The stone walls and the stone faces of bridges and steps have Italy's medieval stone wall, the concrete walls, traffic islands and bridge parapets Italy's old concrete, the setts and cobbled streets Italy's cobblestones.

## Smooth curves

The cadastral survey draws a curved road edge, kerb or wall as straight pieces a few metres long, and up to v2.8 the roads, pavements and walls showed every piece. Now every gently turning outline is a curve through the surveyed points, a point every 0.75 m (`smooth_geom.py`); corners of 35° or more stay sharp, and two neighbours (a road and its pavement) get exactly the same curve on their shared edge.

## Street life

The villages had street lamps and little else. Now (`street_life.py`), by rules, with the game's own Italy models:
- litter bins along the village roads (one about every 75 m) and beside every bus stop;
- fire hydrants along the village roads (one about every 120 m);
- the recycling points OpenStreetMap records: three sorting bins and a skip, sometimes rubbish bags;
- terraces in front of the bars, cafés, restaurants and ice-cream shops OpenStreetMap records: round tables with two chairs and an umbrella;
- planters along the pedestrian streets and squares;
- convex mirrors on a pole where a village road ends between houses on another road;
- at the houses: bins between some of them and the road, letter boxes on their stand at the edge of the road, garden tables with chairs and an umbrella; pallets and drums beside sheds, barns and workshops;
- the post boxes, picnic tables and viewpoints OpenStreetMap records;
- the squares, car parks and yards: along their edges benches, planters and bins on the village squares, pallets (some stacked), drums, skips and rubbish bags beside the sheds and workshops, the middle left free for the cars (about 7,800 props on 2,500 yards).

On the v2.8 level that is about 13,000 objects. Not their real places: no open data has them.

## Flower boxes and woodpiles

At the windows of the houses (`house_extras.py`): flower boxes with geraniums (red, pink, white or violet) under about a fifth of the windows with shutters, fewer under the roller shutters and the modern windows, and along some balcony railings; woodpiles against the walls of the stone houses, under the eaves. About 20,000 flower boxes and 140 woodpiles on the v2.8 level, about 250,000 triangles.

## Also

- One "keep right" sign stood twice at the same place: now once (`signs_net.PANO_SAME`).
- The build workflow `v3 build test` builds the whole level from scratch with every finishing step, runs the automatic checks and keeps the downloads between runs.

## Known

Still to fix from v2.8: pale slabs on the Magliasina bridge abutments, pale patches in the grass at Agno, pale jagged bands on some stone wall caps, the AI driver stopping at a few spots (Mugena, Vezio, Miglieglia, Pura).
