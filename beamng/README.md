# Malcantone (Strada Cantonale Magliaso → Pura and surroundings): the BeamNG map pipeline

This pipeline rebuilds the Malcantone (Ticino) at 1:1 scale as a BeamNG.drive level (`magliaso_pura`, version 0.39). The level covers about 52 km² between Ponte Tresa, Caslano, Magliaso, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano and Sessa. At its centre is the Strada Cantonale from Magliaso to Pura of the 1.x versions; to the east is the cantonal road from Magliaso to Gravesano, along the lake to Agno and then along the foot of the mountains through Bioggio and Manno. The work combines two kinds of source:

- the **366 Street View panoramas** of the dataset along the cantonal road (`C:\Users\michi\Documents\magliasinaNG`: 363 from October 2022, 3 from 2013/2014), used for camera poses, objects, road markings, textures and validation;
- the **official data from swisstopo and the Ticino official survey**, used as the metric reference for the whole area: terrain, road network (swissTLM3D), carriageways, buildings, walls and trees.

For players, installation and troubleshooting are in the [main README](../README.md); what changed in each version is in [`CHANGELOG.md`](../CHANGELOG.md). This file is for whoever wants to build the level or change the pipeline.

## Contents of this folder

| Folder | What's in it |
|---|---|
| `pipeline/` | all the scripts, from data download to verification; `config.py` holds the paths |
| `verifica/` | `VERIFICA.md` (comparison with all 1464 views), the agreement chart along the route, per-view metrics (`metrics_final.json`, and `metrics_full1.json` before the last correction round) |
| `dati/` | lightweight computed results, to rebuild the level without redoing the long steps: calibrated panorama poses (`poses.json`), road axis, road markings and their 2022 state, guardrails, retaining walls and wall heights, fences, street lamps, poles and signs, street furniture, trees and shrubs; for v2.0 the bridges with the manual corrections (`ponti.json`) and the Magliaso–Gravesano cantonal road (`cantonale_gravesano.json`); for v2.2 the roads of the new corridors (`strade_extra_v22.json`) |

The **ready-made mod** is in the [v2.7 release](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.7): the v2.6 zip passed through the four v2.7 patch scripts by `.github/workflows/release_v2.7.yml`. The [v2.6 release](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.6) is the [v2.4](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.4) zip passed through `optimize_level.py` (v2.5: same geometry, lighter for the game) and `patch_groundcover.py` (v2.6: the new grass). The v2.4 zip is what the `.github/workflows/release_v2.4.yml` workflow builds from scratch on a GitHub server: it downloads the data, builds the level, checks it with `check_level.py` and `drive_test.py` and publishes it. It is built with `MAGLIASO_NO_PHOTO_TEXTURES=1`, so it contains no Street View images: façades, roofs and walls have original textures drawn by the pipeline in the measured colours, and sign plates are plain-coloured. The cantonal road's objects derived from the photos (road markings, street lamps, poles, signs, street furniture) are taken from the v1.1 release and placed on the new surfaces (`carryover.py`).

Every version is on the [releases](https://github.com/wintrymichi/magliasinaNG/releases) page:
- **v1.0**: only the cantonal road corridor.
- **v1.1**: the cantonal road with smooth roads and a clear carriageway (`patch_release.py`, `.github/workflows/release_v1.1.yml`).
- **v2.0**: the 51 km² area with the whole road network, the bridges and the cantonal road to Gravesano (`release_v2.0.yml`).
- **v2.1**: road markings on the whole network, trees out of the clearance envelope, AI traffic, railway (`release_v2.1.yml`).
- **v2.2**: Street View review, façades, guardrails on the whole network, new roads towards Arosio and Caslano (`release_v2.2.yml`).
- **v2.3**: fixes after the first in-game tests, lighter woods (`release_v2.3.yml`).
- **v2.4**: houses from every side, OSM surfaces, grass, palms, vineyards, rivers (`release_v2.4.yml`).
- **v2.5**: the v2.4 zip made lighter for the game (`optimize_level.py`).
- **v2.6**: the game's own grass and flowers (`patch_groundcover.py`).
- **v2.7**: the road markings of the network redrawn as Swiss markings (`markings_clean.py`, `patch_markings.py`); dirt and gravel roads and paths flush with the ground (`patch_unpaved.py`); every measured tree back on the slopes away from the roads, drawn as imposters (`far_trees.py`, `patch_far_trees.py`); the Swiss road signs of the whole network (`patch_signs.py`).

The metrics in `verifica/VERIFICA.md` concern the cantonal road in the local version with photographic textures and the v1.0 geometry. The verification of the latest version is in `verifica/check_level.json` (automatic checks over the whole map), `verifica/drive_test.json` (virtual drive test) and `verifica/REVISIONE.md` (Street View review); the bridge profiles are in `verifica/ponti/`.

## Start here

**What the pipeline does.** It reads open data for the area and writes a complete BeamNG.drive level folder (`levels/magliaso_pura`), then zips it as a mod. Every step is a separate Python script that reads the previous steps' results from a working folder and writes its own; the order is in [Script order](#script-order-pipeline-folder). The small results that are expensive to recompute or need the local panoramas (poses, markings, colours, guardrails, OSM and GWR extracts) are pinned in `dati/`, so a build on another machine needs neither the game nor the panoramas.

**Three ways to get a level:**

| You want to… | Do this | Time |
|---|---|---|
| publish a release built from scratch | GitHub *Actions* → *Release v2.4* → *Run workflow* ([`release_v2.4.yml`](../.github/workflows/release_v2.4.yml)) | about 1 hour |
| build it on your own machine | the commands under [Building without the game](#building-without-the-game) | depends on the machine, plus the downloads |
| change an already built zip | a patch script: `optimize_level.py` (v2.5), `patch_groundcover.py` (v2.6), `patch_unpaved.py`, `patch_markings.py`, `patch_far_trees.py` and `patch_signs.py` (v2.7), `patch_paved_edges.py`, `patch_wall_fill.py` and the other v2.8 patches (in progress; `patch_paved_edges.py` first, it changes the terrain heights the others stand on) | minutes |

v2.6 is the v2.4 workflow's zip passed through the first two patch scripts; the current release, v2.7, adds four more, in this order (the paint follows the flattened dirt tracks):

```bash
python optimize_level.py magliaso_pura_v2.4.zip magliaso_pura_v2.5.zip
python patch_groundcover.py magliaso_pura_v2.5.zip magliaso_pura_v2.6.zip
python patch_unpaved.py magliaso_pura_v2.6.zip magliaso_pura_v2.6u.zip
python patch_markings.py magliaso_pura_v2.6u.zip magliaso_pura_v2.6m.zip
python patch_far_trees.py magliaso_pura_v2.6m.zip magliaso_pura_v2.6t.zip   # needs work/trees.npz (trees.py)
python patch_signs.py magliaso_pura_v2.6t.zip magliaso_pura_v2.7.zip --report ../verifica/signs_v2.7.json
```

### Requirements

Python 3.11 or newer with the packages the workflow installs:

```bash
pip install numpy scipy shapely rasterio pyproj scikit-image opencv-python-headless pillow requests matplotlib pyogrio
```

The exact versions are pinned in [`release_v2.4.yml`](../.github/workflows/release_v2.4.yml). The Street View steps (`segment_views.py`, `sv_segment.py`) also need PyTorch with CUDA; the release build does not run them.

### Paths and environment variables

`pipeline/config.py` holds every path. The defaults are the author's Windows machine; on any other machine set them with environment variables:

| Variable | What it points to | Default |
|---|---|---|
| `MAGLIASO_ROOT` | heavy data: `data/` downloads, `work/` intermediate results, `dist/` mod zips | `D:\beamng_magliaso` |
| `MAGLIASO_DATASET` | the repository root (panorama metadata and, locally, the images) | `C:\Users\michi\Documents\magliasinaNG` |
| `MAGLIASO_BEAMNG_USER` | the game's user folder; the level is written to `levels/magliaso_pura` inside it | `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current` |
| `MAGLIASO_BEAMNG_GAME` | the game's install folder (vanilla assets); `/nonexistent` to build without the game | Steam's `BeamNG.drive` folder |
| `MAGLIASO_LEVEL_DIR` | where the level folder is written | `<BEAMNG_USER>/levels/magliaso_pura` |
| `MAGLIASO_REFERENCE_ZIP` | the v1.1 release zip, source of the cantonal road's objects (`carryover.py`) | `<ROOT>/dist/magliaso_pura_v1.1.zip` |
| `MAGLIASO_NO_PHOTO_TEXTURES` | `1` (default): no Street View imagery in the level. `0` only for private study, never distributed | `1` |

## Building the level

### Locally, with the game and the panoramas

On Windows, with the default paths of `config.py`:

```bash
D:/beamng_magliaso/venv/Scripts/python.exe -u build_level.py
```

### Building without the game

Without the game and without the panoramas, the same steps as [`release_v2.4.yml`](../.github/workflows/release_v2.4.yml). The workflow first downloads the v1.1 release zip into `$MAGLIASO_ROOT/dist` (`gh release download v1.1`): the build takes the cantonal road's objects from it.

```bash
export MAGLIASO_ROOT=/path/data MAGLIASO_DATASET=$PWD MAGLIASO_BEAMNG_USER=/path/beamng_user
export MAGLIASO_BEAMNG_GAME=/nonexistent MAGLIASO_NO_PHOTO_TEXTURES=1 MAGLIASO_REFERENCE_ZIP=/path/magliaso_pura_v1.1.zip
cd beamng/pipeline
python prepare_work.py && python download_swisstopo.py && python download_av.py && python download_tlm.py && python download_gwr.py
python build_rasters.py && python landcover.py && python extract_buildings.py && python missing_buildings.py && python trees.py
python network.py && python network_surface.py && python build_level.py
python check_level.py && python drive_test.py
python package.py magliaso_pura_v2.4
```

### After the build

Since v2.5 the mod zip comes from `optimize_level.py` (merged tiles, detail by distance, lighter road strips):

```bash
python optimize_level.py "$MAGLIASO_BEAMNG_USER/levels/magliaso_pura" "$MAGLIASO_ROOT/dist/magliaso_pura_v2.5.zip"
```

`build_level.py --reuse-roads` redoes all the stages except the road network, which is the longest (about 13 minutes). It reuses the road meshes of the previous build and `work/roads_state.npz`.

Since v2.2 the level never contains images taken from Street View: this is the default behaviour
(`config.NO_PHOTO`). Only `MAGLIASO_NO_PHOTO_TEXTURES=0` brings back the photographic textures of the local 1.x
versions, for private study; that version must not be distributed.

The road surface (`roadheight.py` → `work\road_surface.npz`) is computed at the first stage that uses it; delete it to recompute it, for example after changing the parameters in `surface_fit.py`. Guardrails and walls near the road are realigned to the new surface during the build. `guardrails2.py` and `wall_caps.py` read the surface only when those steps are redone.

### Older steps

To update the v1.0 zip without the working data (about 5 minutes; requires numpy, scipy, shapely and rasterio):

```bash
python patch_release.py magliaso_pura_v1.0.zip magliaso_pura_v1.1.zip
```

The photo verification of the cantonal road (local only, with the game) takes three steps:

1. `validation.py make <indices> 90`, or `makefull` for all 366 panoramas;
2. `run_validation.ps1`: for the full tour the JPEG screenshots must be moved to `work\validation_full\game`;
3. `validate_metrics.py <tag>`, or `validate_metrics.py <tag> full` followed by `verify_report.py <tag>`.

## Coordinate system

The reference system is LV95 (EPSG:2056) with local origin E 2 710 830 / N 1 094 360, transformed as follows:

```text
x = (E − E0) / K
y = (N − N0) / K
K = 1.000137497   (LV95 scale factor at the origin)
```

Heights are orthometric (LN02). The BeamNG terrain measures 12.3 × 12.3 km: 8192 × 8192 samples at 1.5 m, with the south-west corner at x = −7230, y = −4731 (v1.x: 4096 × 4096 m at 1 m). The whole level (terrain, roads, buildings, objects, cameras) uses this same system.

## Script order (`pipeline` folder)

| Stage | Script | Result |
|---|---|---|
| Data | `download_swisstopo.py`, `download_av.py`, `download_tlm.py` | swissALTI3D 0.5 m and 2 m, swissSURFACE3D 0.5 m, SWISSIMAGE 2 m (10 cm and LiDAR along the cantonal road with `--route-extras`), swissBUILDINGS3D, swissNAMES3D, Copernicus GLO-30; Ticino official survey (WFS geodienste.ch); swissTLM3D (roads, railways, watercourses) read piecewise from the national package |
| Rasters | `build_rasters.py`, `landcover.py`, `extract_buildings.py`, `lidar_extract.py` | DTM/DSM 0.5 m, orthophoto, land cover, buildings, LiDAR points near the road |
| Camera poses | `calibrate_attitude.py`, `refine_poses.py`, `solve_poses.py`, `calib_camheight.py` | position and orientation of every panorama, registered on the orthophoto to about 0.3 m (Viterbi along the trajectory) |
| Segmentation | `segment_views.py` | Mask2Former Swin-L (Mapillary Vistas) on all views |
| Road | `road_profile.py`, `road_strip.py`, `pano_strip.py`, `roadheight.py`, `surface_fit.py` | road axis and cross-section; "rectified strips" from the orthophoto and the panoramas; idealised surface of the paved areas: smooth, robust fit to the DTM (thin plate, Tukey weights), flat cross-section and stiffer profile on the cantonal road's carriageway, bridges rebuilt over the gaps in the DTM, steps where two surfaces lie at different heights |
| Road markings | `markings.py`, `markings_photo.py`, `markings_raster.py`, `marking_votes.py`, `markings_state.py` | lines from the orthophoto verified in the photos; state of October 2022: stretches without markings, red bands, shifted centre line |
| Walls and barriers | `roadside_walls.py`, `wall_caps.py`, `guardrails.py`, `guardrails2.py`, `fences.py` | retaining walls; visible wall height measured in the photos (removing false LiDAR ridges: roofs, balconies, guardrails above the walls); guardrails; railings and fences on the walls |
| Objects | `poles.py`, `lamps.py`, `objects.py` | poles, signs (with the image of the plate), triangulated street lamps, street furniture |
| Vegetation | `trees.py`, `understory.py`, `clearance.py` | trees from the normalised surface model (position, height, crown), hedges and bushes; no trunks on paved surfaces, shrubs and hedges set back from the edge |
| Textures | `terrain_colors.py`, `texture_buildings.py`, `texture_walls.py` | colours measured in the photos; façades and walls projected from the panoramas |
| Level | `build_level.py` | all stages, from the road to the spawns, plus `info.json` |
| Verification | `validation.py`, `run_validation.ps1`, `validate_metrics.py`, `verify_report.py`, `bng_lua/magliaso_validate.lua` | in-game camera tour at the photo poses (all 1464 views too), comparison by segmentation, check of the road network for the AI, `VERIFICA.md` report |
| Correction | `photo_votes.py`, `missing_veg.py` | multi-view label votes; shrubs that the photos show and the game doesn't (from the comparison over the whole dataset) |
| Network (v2.0) | `network.py`, `network_surface.py`, `network_mesh.py`, `bridges.py`, `water.py`, `places.py`, `strade_extra.py` | swissTLM3D road and trail network, smooth profile, drivable surfaces, bridges, lake, villages, Magliaso–Gravesano cantonal road |
| Verification (v2.0) | `check_level.py`, `review_map.py`, `bridge_report.py`, `render3d.py` | checks over the whole map, 3D screenshots, bridge sheets |
| Without the game | `prepare_work.py`, `vanilla.py`, `carryover.py`, `ogr_tin.py` | cloud build: lightweight results from `dati/`, vanilla files and the cantonal road's objects from the v1.1 zip, reading of the swissBUILDINGS3D TINs |
| Street View (v2.2) | `sv_coverage.py`, `sv_fetch.py`, `sv_segment.py`, `sv_facades.py`, `sv_guardrails.py`, `sv_walls.py` | coverage (metadata), review panoramas stored locally, segmentation of the roadside band; measurements: façade colour, shutters, guardrails, wall material |
| Buildings (v2.2) | `download_gwr.py`, `missing_buildings.py`, `bld_textures.py`, `facades.py` | building register, missing and demolished buildings, original textures, per-house façades |
| Review (v2.2) | `sv_review.py`, `qa_log.py`, `review_report.py`, `drive_test.py`, `drive_context.py`, `screenshots.py` | photo/map comparison from the same camera, log of the reviewed places, `verifica/REVISIONE.md`, virtual drive test, screenshots |
| Graphics (v2.4) | `osm_surface.py`, `surface_textures.py`, `groundcover.py`, `palms.py`, `vineyards.py`, `rivers.py` | road and trail surfaces from OSM with their textures, grass and flowers, palms, vineyard rows, water in the rivers |
| Package | `package.py` | mod zip in `<MAGLIASO_ROOT>/dist` |
| Grass (v2.6) | `groundcover.py`, `patch_groundcover.py` | grass and flowers with the game's textures; into a built zip |
| Road signs (v2.7) | `signs_ch.py`, `signs_net.py`, `patch_signs.py` | the Swiss signals drawn as textures; where they stand from OpenStreetMap (mapped signs and the rules); into a built zip |
| Road markings, cleaned (v2.7) | `markings_clean.py`, `patch_markings.py` | the paint traced by `network_markings.py` redrawn as Swiss markings (smooth lines, regular dashes, standard crossings, no blobs); into a built zip |
| Unpaved surfaces flush (v2.7) | `patch_unpaved.py` | the terrain raised to the edges of the dirt and gravel meshes (no trench beside them, never over a road face) and their outer edges lowered onto it: 1-2 cm between track and ground instead of about 0.3 m; into a built zip, before `patch_markings.py` (the paint follows the faces) |
| Far trees (v2.7) | `far_trees.py`, `patch_far_trees.py` | the trees the thinning leaves out, as three drawn models in three shades with an imposter detail level; into a built zip |
| Ground behind the walls (v2.8, in progress) | `patch_wall_fill.py`, `wall_fill_tour.py`, `run_wall_fill_screenshots.ps1` | the backfill behind the retaining walls with the normals of the ground it restores (smooth, like the terrain) instead of one per triangle, and no game grass under it or over walls lower than the grass; geometry and terrain heights unchanged (checked by the script); into a built zip, first on the v2.7 zip; the places and views of its check, rendered with `render3d.py` or in the game |
| Street lamps (v2.8, in progress) | `patch_lamps.py`, `lamps_tour.py`, `run_lamps_screenshots.ps1` | a street lamp of the game's Italy model every 30 m along the roads of the villages (where the Federal Register has at least 6 buildings within 45 m), beside the carriageway; the lights of the street lamps; into a built zip; the places and views of its check, rendered with `render3d.py` or in the game (with the frame rate and the peak memory) |
| Undergrowth (v2.8, in progress) | `patch_understory.py`, `groundcover.py` (`understory_object`), `understory_tour.py`, `run_understory_screenshots.ps1` | the forest floor layers a darker olive; low shrubs of the game's bush models on them around the camera (a GroundCover); verge twins of the forest layers along roads, paths, walls, buildings and the railway, without them; into a built zip |
| Delineators and pole lines (v2.8, in progress) | `patch_roadside.py`, `roadside_tour.py`, `run_roadside_screenshots.ps1` | delineator posts (pipeline meshes, no collision) along the 6 m roads outside the villages; lines of the game's wooden pole with a cable along the country roads past houses; into a built zip |
| Paved edges flush (v2.8, in progress) | `patch_paved_edges.py` (with `patch_unpaved.main`), `paved_tour.py`, `run_paved_screenshots.ps1` | the terrain raised to 4 cm under the outer edges of the asphalt, sett, cobble and pavement meshes (the meshes unchanged), not within 2 m of a guard rail, fence, wall, building, the railway or a bridge parapet; into a built zip, before the other v2.8 patches (it changes the terrain heights) |
| Railway overhead line (v2.8, in progress) | `patch_catenary.py`, `catenary_tour.py`, `run_catenary_screenshots.ps1` | the axes of the tracks from the sleepers of the railway meshes; masts, cantilevers, messenger and contact wires of the FLP and the SBB line; into a built zip |
| Optimisation (v2.5) | `optimize_level.py`, `mesh_strips.py` | built level (folder or zip) → lighter mod zip: merged tiles, shared vertices, simpler road strips, detail by distance |
| Patching a release | `patch_release.py` | applies the v1.1 fixes (roads, terrain, road markings, AI, objects, vegetation) to an already built zip, using only the zip and `dati/` |

## Working data

The heavy data (not in the repository) is in `D:\beamng_magliaso\`: `data\` = downloads, `work\` = intermediate results, `venv\` = Python 3.13 with CUDA torch. The level is written to `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\levels\magliaso_pura`.

## Technical notes by version

What each version changed in the pipeline and which scripts do it, newest first. The player-facing summary is in [`CHANGELOG.md`](../CHANGELOG.md).

### Version 2.8 (in progress): the ground behind the walls

The terrain is a 1.5 m grid and cannot hold a step inside a 0.3 m wall: `walls.carve_terrain` lowers every terrain
vertex whose triangles touch a wall to the foot of the wall, and `walls.build_backfill` covers the trench this leaves on
the high side with a mesh at the height of the ground as it was (784,035 triangles, 63 ha in v2.7). That mesh had one
normal per triangle (`bng.flat_normals_soup`): in the game every triangle was lit on its own, flat facets and saw teeth
beside a smoothly shaded terrain. And the game's grass grew on the terrain lowered under it (29 % of those vertices are
less than 0.8 m under the backfill, the grass clumps up to 0.8 m tall) and over the walls lower than the grass.

`patch_wall_fill.py <in.zip> <out.zip> [--report <json>]` changes neither the geometry nor the terrain heights (the
script checks every backfill triangle, position and texture coordinate, and the heights of the `.ter`):
- **normals**: every backfill vertex takes the normal of the ground it restores, computed like the terrain's own
  (central differences over one terrain step) on the heights of the backfill at the terrain vertices and of the
  terrain elsewhere; the vertices lowered to the foot of a wall and not covered are left out (one-sided differences).
  On the edge where the backfill meets the visible terrain it takes the terrain's own normal, so the light does not
  jump at the seam (tried the other way, with the ground's normal on the edge too: in the renders the outline of the
  backfill shows as a line of light). The cut vertices inside a terrain square interpolate the normals of its corners.
  Welded again, the backfill has 896,120 vertices instead of 1,551,036;
- **grass**: the terrain vertices of the squares under the backfill, and those of the squares a wall passes through
  from which the tallest grass (`groundcover.py`, 0.8 m) would reach over the wall top, go to the verge twins of their
  layer (`terrain.VERGE`: the same material without grass, as along the roads since v2.4): 200,441 vertices
  (183,889 under the backfill, 16,552 over low walls), 0.3 % of the terrain. At the foot of the taller walls and on
  the rest of the meadows the grass stays.

Not changed: the saw teeth themselves (the corners of the backfill alternate between the wall top and the meadow), the
crests of the walls along noisy heights, and the colour of the backfill (the terrain's base texture without its detail
textures). Those need the geometry rebuilt (`walls.build_backfill` with smoothed heights, a full build).

Checked without the game with `wall_fill_tour.py` (`render3d.py` with the DAE normals, `dae_normals=True`, and the
colours of the terrain layers where there is no orthophoto): `verifica/v2.8/wall_fill/`. The same views in the game:
`run_wall_fill_screenshots.ps1 -Zip <zip> -Tag before|after`.

### Version 2.8 (in progress): paved edges flush with the ground

The build carves the terrain 0.1 m under the lowest road face within one terrain step of every vertex
(`network_mesh.carve_tile`), so that it stays under the road whatever the grade. Beside a road with nothing at its
edge this leaves the asphalt standing on the ground like a slab, with a trench beside it. The dirt and gravel tracks
were laid flush in v2.7 (`patch_unpaved.py`); `patch_paved_edges.py <in.zip> <out.zip> [--report <json>]` raises the
terrain to the paved surfaces (asphalt, setts, cobbles, pavements, yards) with `patch_unpaved.main` (its materials,
deepest drop and keep-out cells are parameters now; called without them it does what it did in v2.7, checked on the
v2.6 zip: the same terrain and road shapes as the v2.7 release):
- the terrain within 1.5 m of a paved top face raised to 4 cm under its height (fading back to the ground at 4.5 m,
  only where the ground is lower, not where it lies more than 1 m under the road: an embankment or a bridge stays),
  never over a road face;
- the faces themselves stay as they are. The first version of the patch also lowered the outer edges onto the
  raised terrain by up to 8 cm, as `patch_unpaved.py` does for the tracks: `check_level.py` did not change, but
  `drive_test.py` counted 41 % more hard knocks on the main roads and 64 % more on the minor ones (the last strip of a
  road tilts, by a different amount at every edge vertex, under the wheels of a car);
- the paved paths are left out: the drive test runs its car along them with the wheels on the ground beside them;
- nothing within 2 m of a guard rail, a fence, a wall (and the backfill behind it), a building, the railway or a
  bridge parapet (1 m cells around the outlines of their meshes: 5.7 km² in all): there the step is a real one,
  an embankment behind a guard rail, a kerb against a wall, a plinth.
On v2.7: 1.74 million terrain vertices raised (median 0.11 m), no face changed. The outer edges out of the keep-out
zones (443 of the 973 km of edges of these surfaces) stand 7 cm over the ground 0.3 m beyond them instead of 21 cm
(median; 90th percentile 12 instead of 46 cm; over 15 cm: 6.7 % instead of 74 %); the terrain over the faces inside
the edges as in v2.7 (0.006 % of the points, 0.004 % in v2.7). Nothing is added: only the terrain file changes.
Checked without the game with `paved_tour.py` (`render3d.py` before and after at three places, a driver on the road
and a low view along the edge): `verifica/v2.8/paved_edges/`; in the game: `run_paved_screenshots.ps1`.

### Version 2.8 (in progress): the railway's overhead line

`railway.py` builds the tracks from swissTLM3D but not the catenary ("its masts are not in the data", issue #21).
`patch_catenary.py <in.zip> <out.zip> [--report <json>]` adds it on the tracks as the level has them:
- the axes: the centre of the top of every sleeper box of the railway meshes (the duplicated sleepers of
  overlapping lines removed), its length telling the gauge (1.90 m FLP, 2.60 m SBB); chained 1 m apart (the
  released level has a sleeper every metre), the chains joined across the level crossings (no sleepers there) up to
  30 m; electrified: all the metre gauge, the standard-gauge chains of 400 m or more (the line; the sidings of the
  industrial zones are shorter);
- a steel mast every 50 m (30 m in bends under 150 m of radius, 40 m under 400 m), 2.6 m (FLP) or 3.1 m (SBB) from the
  axis on the outside of the bend or the other side, not on a carriageway, in a building or on a wall, not within 2 m
  of another track's axis; 7.2 m over the rails, a cantilever to over the track;
- the contact wire 5.5 m over the rails, staggered ±0.2 m, under a messenger wire from 6.7 m at the masts down to
  0.35 m over the contact wire mid-span, droppers every 9 m; no wires over a gap of more than 75 m between masts;
- meshes in 512 m tiles in the railway group: the masts with collision (drawn up to 800 m), the wires without (up to
  400 m), materials in `art/shapes/railway/catenary.materials.json`.
On v2.7: 11,504 sleepers, 20 chains, 9.9 km electrified, 201 masts (median span 50 m), 6 gaps without wires.
Checked without the game: `verifica/v2.8/catenary/`; in the game: `run_catenary_screenshots.ps1`.

### Version 2.8 (in progress): delineators and wooden pole lines

`patch_roadside.py <in.zip> <out.zip> [--report <json>]`, by a rule (no open data), outside the villages of
`patch_lamps.py` and away from the panoramas' route:
- **delineators** on the AI roads of drivability ≥ 0.9 (swissTLM3D roads of 6 m and more), on both sides, every 50 m,
  every 25 m in bends under 300 m of radius and 12.5 m under 100 m; 0.5 m beyond the carriageway edge on ground within
  0.6 m of its height; not where a guard rail, fence, wall, building or another road is, not within 12 m of another
  road's axis. The post of props.py (white, black band towards the road, 1 m high), pipeline meshes in 384 m tiles
  (`art/shapes/props/roadside_*.dae`) drawn up to 300 m, without collision (a plastic post a car knocks over). On v2.7:
  507;
- **wooden pole lines** on the roads of drivability 0.5-0.8 (3 and 4 m) with a building within 60 m, on one side,
  every 45 m, 1.5 m beyond the edge, only lines of 4 poles or more: the game's `electric_pole_wood_old_01.dae`
  (10.05 m at scale 1, from the cantonal road's poles) at 0.85, with collision; a cable from the top of a pole to the
  next (0.25 m under the top, sagging by 1.5 % of the span, `mp_cable` in `roadside.materials.json`). The attachment
  points of the game model are not known without the game: the cable starts at the pole's axis. On v2.7: 628 poles,
  124 lines, 504 spans.

`render3d.py` draws the game models it cannot load as posts of their known height (`POST_HEIGHT`). Checked without
the game: `verifica/v2.8/roadside/`; in the game: `run_roadside_screenshots.ps1`.

### Version 2.8 (in progress): undergrowth and a darker forest floor

`patch_understory.py <in.zip> <out.zip> [--report <json>]`:
- the base textures of ForestFloor and ForestFloor2 (`art/terrains/t_base_forestfloor*_b.png`, the colour measured
  by `terrain_colors.py` on the forest edges in the panoramas, 102, 98, 67) scaled to `FLOOR` (62, 66, 42), their noise
  kept; the backfill behind the walls in the woods uses the same textures and follows;
- a GroundCover `understory` (`groundcover.understory_object`): the bush models the level already uses
  (`generibush`, `fluffy_bush` of Italy, `tree_beech_bush_c`, `tree_oak_bush_b` of East Coast USA, scaled to
  0.6-1.5 m) on the two forest floor layers, within 60 m of the camera (fading from 40 m), at most 600 elements of 1-2
  shrubs, no collision, no shadows;
- the forest floor vertices of the terrain squares under a face of the road surfaces, walls (with the backfill),
  buildings or railway, and one square around them, go to new terrain materials `ForestFloorVerge` and
  `ForestFloor2Verge` (copies of the forest ones, the same textures) without the undergrowth: 980,953 of 26.1
  million forest floor vertices. Terrain heights unchanged.

No fern among the game models the level already uses (verified in the game); the undergrowth is low bushes.
Checked without the game: `verifica/v2.8/understory/` (`render3d.py` draws the ground in the median colour of its
layer's base texture, not the GroundCover). In the game: `run_understory_screenshots.ps1`.

### Version 2.8 (in progress): street lamps in the villages

There are no open data on street lamps: `patch_lamps.py <in.zip> <out.zip> [--village-lights] [--report <json>]`
places them by a rule. A point of a road of the AI network is in a village where at least 6 existing buildings of the
Federal Register (`dati/gwr_area.json.gz`, at least 30 m²) stand within 45 m. There a lamp every 30 m, 0.6 m beyond
the edge of the carriageway (the `mp_road_*` faces), on the side of the previous lamp where it can stand: on a
pavement, a yard or the ground within 0.6 m of the height of the road edge, not on a carriageway, under a roof or on
a wall, 1 m clear of furniture, sign poles, guard rails, fences and trunks, 9 m from the axis of another road (a
junction) and 18 m from any other lamp. None along the panoramas' route (the cantonal road), where the lamps are
the measured ones. The model is the one of those lamps (`italy_light_single.dae` of the game's Italy level,
referred to), arm towards the road. On v2.7: 1,779 new lamps; rejected tries are counted in the report (most in the
old towns: a wall or a building at the edge of the road).

The lights: `props.py` puts a PointLight under every lamp head since v2.4, but the release builds take the cantonal
road's objects from the v1.1 zip (`carryover.py`), so no release had them. The patch adds them to the 73 lamps of
v2.7 (the head 1.2 m along the arm and 8.75 m up at scale 1, the median of `dati/lamps.json`), and to the new lamps
only with `--village-lights`: 1,852 lights in all, whose cost in the game is to be measured
(`.github/workflows/lamps_test.yml` builds both zips; `run_lamps_screenshots.ps1` takes the views by day and at
night with the frame rate and the peak memory).

### Version 2.7: far trees

Since v2.3 `vegetation.thin` keeps every tree only within 30 m of a road and 5 m of a path; farther out one tree per
11–17 m cell, beyond 100 m one per cell of a grid coarse enough for `CAP`: seen from the valley the slopes looked bald.
The trees it leaves out now come back as **far trees** (`far_trees.py`): three drawn models (a round and a narrow
broad-leaved crown, a fir; about 150 triangles of cut-out leaf and needle cards around a trunk, textures drawn, no
photos) in three shades each, the shade being the measured orthophoto colour of the tree (terciles of brightness per
kind, median colour made more saturated and darker: `SATURATION`, `VALUE`). Each DAE has two detail levels: the mesh
above `MESH_PX` pixels on screen (within about 10 m of the camera; in the first in-game test 600 px still drew the mesh
150 m away at 1440p, 8000 px 8 m; now 5000 px) and an **imposter** below it: an empty node `bb_autobillboard<size>` beside `start01` with
its `BB::` settings as FCOLLADA user properties (`bng.MeshBuilder.write_dae(billboard=...)`), from which the game renders
8 pictures of the mesh around it and draws every tree as one camera-facing quad, batched per forest cell. The last
detail level is never culled, so the far trees stay visible at any distance. Far trees are never near a road, so from
the roads they are always quads; the vanilla trees near the roads are the same as before.

The leaves have no colour texture: each leaf material is its shade as `baseColorFactor` times a vertex colour per
card, cut out by a drawn `opacityMap` (`*_o.data.dds`, BC1 with mipmaps, `far_trees.write_dds`; the game rejects
uncompressed DDS). With a colour texture, png or dds, the game baked the imposters pale grey: it bakes them at load
before the texture is there, and keeps them in its cache. Without an `opacityMap` it ignores the alpha of the colour
texture, so the leaf cards were drawn as full squares.
In game (round 6, BeamNG 0.39.4 at 1440p) the far trees on a cold load are dark green, within the range of the
vanilla trees beside them; 3-6 % fewer fps, about 20 s longer load, about 1 GB more memory. The mesh itself, seen
only within about 12 m of a far tree (never from a road), renders much darker than its imposter: near-black leaves.

No far tree has its crown within 0.5 m of a path; `canopy.py` treats them like the other trees (`far_fir_*` are conifers).
`optimize_level.py` leaves shapes with an imposter as they are. `patch_far_trees.py <in.zip> <out.zip> [trees.npz]`
adds them to a built zip: the measured trees more than 33 m from a road surface and 8 m from a path surface of the zip,
with no forest item within 1 m.

### Version 2.6: grass

`groundcover.py` no longer draws its own grass atlas (in the game it showed as dark opaque cards: the material had no
opacity map). The meadows (`Grass` layer) and gardens (`GardenGrass`) use the game's own textures in
`/assets/materials/foliage` (referenced, not copied), under materials of this level (`mp_gc_grass_short`,
`mp_gc_grass_long`, `mp_gc_flowers`), with the billboard rectangles and sizes of the game's Italy level:

| GroundCover | Texture | Radius (fade from) | Clumps at most |
|---|---|---|---|
| `grass_close` | short grass | 50 m (30 m) | 160,000 |
| `grass_mid` | short grass | 120 m (80 m) | 150,000 |
| `grass_far` | long grass | 120 m (80 m) | 150,000 |
| `flowers` | meadow flowers, meadows only | 50 m (30 m) | 30,000 |

`patch_groundcover.py <in.zip> <out.zip>` puts it into a built level. In the game: 72–111 fps at the test points.

### Version 2.5: performance (measured in the game)

The v2.4 level, tried in BeamNG.drive 0.39.4 on a PC with 16 GB of RAM (RTX 4070, Ryzen 7 7800X3D): 215 s to load
(371 s through BeamMP), then the game wanted more memory than the PC had free (paging, more than 10 minutes on the
loading screen, the whole PC lagging). Partial levels, loaded with an FPS and memory probe (game memory at the peak):

| Level | Game memory | FPS (3 spawns) |
|---|---|---|
| terrain + forest only | 7.1 GB | 100–140 |
| v2.5 without the road surfaces | 10.8 GB | 90–128 |
| v2.5 without the forest | 11.0 GB | 112–125 |
| v2.5 without the terrain | 10.6 GB | 100–125 |
| v2.5 complete | ~12 GB | 82–109 |

The meshes cost about 300 bytes of game memory per triangle, with or without collision; the forest about 0.7 GB, the
8192 × 8192 terrain 1–1.5 GB; the size of the terrain texture arrays makes no measurable difference.

`optimize_level.py` turns a built level (folder or zip) into a lighter one with the same geometry:
- **tiles merged 3 × 3** (128 m → 384 m) per group, with the same collision and decal type: 7916 → 2188 objects;
- **shared vertices** (`bng.weld_corners`, now done by every build in `MeshBuilder.write_dae`): the meshes were
  triangle soups; 38.2 → 19.7 million vertices, positions and texture coordinates unchanged;
- **road strips** (`mesh_strips.py`): skirts and kerb faces along straight runs in fewer quads, within 4 mm
  (checked both ways for every piece): 15.9 → 15.3 million triangles;
- **detail size by distance**: guard rails disappear beyond about 600 m, fences 400 m, markings 500 m, walls
  1.2 km, vineyards 1 km, buildings and roads 3 km (they were drawn up to 12 km);
- terrain base textures at 1024 px (`terrain.BASE_TEX`), sun shadows up to 800 m instead of 1600.

Result: 60 s to load with the game's converted shapes in its cache (about 145 s the first time), 82–128 fps at the
spawns. With other programs open (Discord, a browser, ...) the PC is still at its memory limit: the game peaks at about 12 GB.

### Version 2.4: houses from every side, Magliaso roundabout, OSM surfaces and more realism

- **Wall facing** (`buildings_mesh.py`: `orient`, `undecided_walls`, `soffits`): the game draws only one
  side. The facing of each wall is decided with two nearly horizontal rays starting just in front of
  the wall: if they cross the building's surfaces an odd number of times the wall faces inwards and is
  flipped (previously the building centre was used, which is wrong for L- and U-shaped buildings,
  courtyard buildings and rows of houses). Where the rays can't decide (open shells of the 3D survey) the
  wall is double-sided. Under every roof pitch that overhangs the footprint there is a soffit, 3 cm below the pitch.
  `bng.MeshBuilder.orient_closed` turns the solids of walls, fences, guardrails, poles and tracks outwards.
  `render3d.py` draws a single side like the game (double only for `doubleSided` materials).
  New check `building_walls_inward_share` in `check_level.py`: a point 0.3 m in front of the wall
  inside a footprint and the one behind outside = wall facing inwards.
- **Walls that the panoramas see as pavement** (`markings_state.py --walls`, `walls.py`): the survey's walls on
  roads, pavements and islands where the panorama segmentation (multi-view vote, `band_votes`) sees road
  or pavement for at least 70 % of at least 30 votes are brought flush with the pavement, or removed if the
  ground around them is flat. This is the block that stuck out at the junction of the Magliaso
  roundabout. The small pieces of pavement on the islands removed in 2022 are carriageway
  (`removed_sidewalks`).
- **Surfaces from OpenStreetMap** (`osm_surface.py`, `network_mesh.Network.assign_surfaces`): every swissTLM3D
  line takes the category (asphalt, gravel, dirt, setts, cobblestones) of the OSM ways running
  beside it, where they are tagged (`surface`, for tracks `tracktype`), otherwise its own (`BELAGSART`).
  The road polygons of the survey are split among the lines and ways they contain, on a 1 m grid (the
  nearest way relative to its half-width wins; pieces under 25 m² are merged into the rest).
  OSM areas with a surface (car parks, squares) pass it on to the yards beneath them. Materials for
  carriageway, yard and trail with the GRAVEL, DIRT and COBBLESTONE ground types; procedural textures
  (`surface_textures.py`) with the median colour of the 10 cm orthophoto along the OSM ways of that surface.
  A polygon's facets (`road_mesh.split_by_surface`) are computed on its whole piece and then cut into
  the surface zones, so asphalt and gravel of the same polygon sit at the same heights; a small facet
  piece under 3 m² enclosed inside another one goes over to it (`MIN_PIECE`), but not one on the edge of
  the 128 m block, which continues at its own height in the neighbouring block.
- **Grass and flowers** (`groundcover.py`): a GroundCover object (written as in the game's levels, one
  `Types` element per type) with billboard tufts (2 triangles) from a drawn atlas, on `Grass` and `GardenGrass`,
  40,000 elements within 50 m; meadows within one terrain square of the roads have a twin terrain layer
  without grass (`terrain.VERGE`), so the tufts don't poke through the roads.
- **Palms** (`palms.py`): a drawn Trachycarpus model; a quarter of the measured trees 3–9 m tall with
  a crown up to 6 m in gardens within 400 m of the lake and below 320 m become palms (an estimate: the species
  can't be measured).
- **Vineyards** (`vineyards.py`): rows every 2.2 m in the survey's vineyards within 150 m of the network, in the
  direction of the rows in the orthophoto (structure tensor, measured once: `dati/vineyard_rows.json`) or
  along the contour lines; meshes in 128 m pieces with a level of detail that removes them beyond about one
  kilometre.
- **Rivers** (`rivers.py`): a semi-transparent water surface on the `corso_acqua` (watercourse) areas at least 2.5 m wide,
  at the height of the lowest bed within 3 m + 12 cm, under bridges too, not on fords or the lake. The
  terrain (1.5 m grid, smoother than the bed) drops 35 cm below the water inside those areas, except
  where it lies more than 1.5 m above the water (the steep banks of gorges that the surveyed area includes) and
  within 2.5 m of roads and trails at ground level: at a ford the wheels of a car on a 1 m wide
  trail rest on the ground beside it, which stays as it was.
- **Materials**: ambient occlusion maps for render, plinth and roofs (`bld_textures.py`), walls darker
  towards the ground in the vertex colours (`buildings_mesh.GROUND_AO`); light from the 68 triangulated street lamps
  (`props.py`, without shadows); haze 1.3e-4 up to 1000 m (previously 1.1e-4 up to 1200 m).

### Version 2.3: fixes after the first in-game tests

- **Walls between two roads at different heights** (`surface_fit.py`, `cross_bands`): a steep DTM band between two
  surfaces is a wall when it has cells both higher and lower than itself around it; the comparison is now made with
  the midpoint between the highest and the lowest value of the neighbouring band and not with the median, which for a
  wide, blurred wall falls on the side of the cell itself. In Magliaso the wall between the Strada Cantonale and Via
  Piscicoltura, lower down, was taken for a bump: the two roads became a single surface and the
  cantonal road dropped up to 2.2 m below the ground at the edge for about 60 m. Now each road has its own
  surface (largest deviation on the axis of the cantonal road from 1.70 m to 0.09 m). Along the corridor of the
  cantonal road only 6 bands change, all towards the real ground.
- **Forest thinning** (`vegetation.py`, `thin`): all measured trees remain within 30 m of the
  roads and 5 m of the trails (previously 150 m from the roads); up to 60 m and 100 m from the road the tallest in each
  11 m and 17 m cell, beyond that the tallest in each cell of a grid just wide enough to stay under
  `CAP`. Slopes crossed by hairpins, like the pass above Gravesano seen from the village, are no longer
  as dense as the whole forest and the game draws them faster.

### Version 2.2: Street View review, façades, guardrails and drivability

A systematic review of the whole map compared with Google Street View, used **only as a visual
reference**: no Street View image goes into the level or the repository. Only measurements are taken
from the photos (the colour of a render, the colour of shutters, the presence of a guardrail, the material of a wall);
everything that can be seen is redrawn with original textures.

- **New roads** (`strade_extra.py`, `area.py`): the pass above Gravesano to Arosio, the Ponte Tresa–Caslano–Magliaso cantonal road and Via Torrazza ended at the edge of the map; now they are in the network with a 100 m corridor, and the Street View review covers them like the rest (1297 more panoramas, 477 downloaded and segmented).
- **Street View of the whole area** (`sv_coverage.py`, `sv_fetch.py`): 19,679 panoramas listed (metadata
  only, in `dati/sv_coverage.json.gz`), one every 20 m of road downloaded locally for the review
  (7278). `sv_segment.py` segments them (Mask2Former, Mapillary Vistas) in the roadside band.
- **Photo/map review** (`sv_review.py`): for every place, orthophoto, panorama and map rendered from the
  same camera; the results are in `dati/qa_review.json` (`qa_log.py`) and, road by road, in
  `verifica/REVISIONE.md` (`review_report.py`).
- **Façades** (`facades.py`, `bld_textures.py`, `buildings_mesh.py`): windows with shutters, roller blinds or
  modern frames, doors, gates, garages, shop windows, church and barn windows, plinths and chimneys on
  every building, according to the category, period and floors in the Federal Register of Buildings (`download_gwr.py`,
  extract pinned in `dati/gwr_area.json.gz`). In the old towns swissBUILDINGS3D merges rows of houses into one
  block: the façades are cut at the boundaries of the official survey's houses and every house has its own
  record, floors, door and colour. Floors start from the ground on the street front.
  Shop windows where OpenStreetMap records a shop, bar or office (`dati/osm_pois.json.gz`). The render colour
  and shutter colour are measured in the panoramas (`sv_facades.py` →
  `dati/facade_colors.json`). Roofs in curved tiles, flat tiles, stone slabs, sheet metal or flat, with original textures.
- **Missing buildings** (`missing_buildings.py`): the official survey's buildings that
  swissBUILDINGS3D doesn't have (built after the 3D survey) are added with the height from the surface
  model or from the GWR floor count; demolished ones are removed. List in `dati/buildings_diff.json`.
- **Guardrails on the whole network** (`sv_guardrails.py` → `dati/guardrails_sv.json`, `guardrail_mesh.py`): the
  edges of every road projected into the segmented panoramas; there is a guardrail where the majority of the
  views show one. Built just outside the last face of the road, at the height of the edge.
- **Walls** (`walls.py`, `sv_walls.py` → `dati/wall_materials.json`): original stone,
  concrete and render textures; the material comes from the panoramas only where the photos are clear.
- **Bus stops and signs** (`props_osm.py`): the OSM stops with pole, yellow sign, timetable and,
  where there is one, a shelter.
- **Drivability** (`network_mesh.py`, `drive_test.py`): the surfaces are continuous between carriageway,
  pavements and yards and at junctions (the step is spread over 4 m in the gradient domain,
  the main carriageways stay fixed); the virtual drive test (quarter-car model, 640 km over
  the whole network) measures steps, lifted wheels, accelerations and holes before and after (`verifica/drive_test_v2.1.json`,
  `verifica/drive_test.json`).
- **Screenshots** of the level for the documentation (`screenshots.py`, rendered with the level's textures).

### Version 2.1: refinement against reality

A review of the v2.0 level compared with real sources: the 2024 SWISSIMAGE 10 cm orthophoto for the whole network, the swissTLM3D attributes that v2.0 didn't use, OpenStreetMap, the automatic checks over the whole map and 3D screenshots. Everything added has a source: no line, sign or object is placed because "there usually is one".

- **Vegetation out of the roads' clearance envelope** (`canopy.py`): not just the trunk but the whole crown of every tree stays out of the envelope, 4.50 m above carriageways and 2.50 m above pavements, yards and trails. A tree whose crown enters the envelope is moved by at most 3 m onto free ground, or takes the narrowest model of its species; if that's not enough its scale is reduced and, as a last resort, the tree is removed. Every plant rests on the ground under its trunk (terrain or backfill behind walls) and no trunk stands inside walls, buildings, parapets or fences. The step works on the level as already written, both in the build and on the published level, and `check_level.py` measures the same rules.
- **Road markings on the whole network** (`network_markings.py`, `ortho10.py`, `markings_net.py`): centre, lane and edge lines, dashed or solid, detected in the 10 cm orthophoto along every road, plus yellow pedestrian crossings, stop lines, arrows and hatched areas. In stretches covered by trees or in shadow a line seen on both sides continues for up to 60 m; longer stretches stay unpainted. Yellow (faded too) is calibrated on the pedestrian crossings recorded in OpenStreetMap and only goes on grey asphalt; wide blobs with a vehicle's windows and shadow and reflections on dark cars are discarded. The result is in `dati/network_markings.json.gz`. The Magliaso–Pura cantonal road keeps its markings verified in the photos.
- **AI traffic**: one-way streets from OpenStreetMap; roundabouts (anticlockwise) and dual carriageways (keep right) from swissTLM3D; roads with a general traffic ban have drivability 0.1.
- **Pinned OpenStreetMap data** in `dati/osm_area.json.gz` and `dati/osm_communes.json.gz` (Overpass extract of 28.9.2026, completed on 30.9.2026 with the strips of the v2.2 corridors, © OpenStreetMap contributors, ODbL 1.0 licence): the release uses these, so it doesn't change with OSM and doesn't depend on the Overpass servers; `download_osm.py --pin` updates them.
- **Signs and street furniture from OpenStreetMap** (`props_osm.py`): STOP and give-way where OSM records them, with the panel drawn (not photographed), on the right-hand edge of the road they belong to; benches, bins and street lamps with the models already used by the level.
- **Railway** (`railway.py`): the FLP (metre gauge) and SBB tracks from swissTLM3D, with sleepers, rails, ballast, level crossings flush with the road and bridges. The tracks sit at the real swissTLM3D height: where the level's terrain is higher a cutting is dug (along the lake in Agno, under the embankment of the cantonal road), where it is lower the track sits on a ballast embankment; those under the car park of Ponte Tresa station are not built, like the tunnels. The overhead line is not built.
- **The Tresa at Ponte Tresa** (`water.py`): the lake model's dam is at the weir, 420 m downstream, and no longer at the outlet. The stretch at lake level, under the border bridge, has water.
- **Zones, roads and log** (`zone_report.py`): `verifica/ZONE.md` (status by municipality), `verifica/STRADE.md` (every road of the network with the status of each aspect) and `verifica/REGISTRO.md` (differences found, action, status).

### Version 2.0: area, road network, bridges

- **Area** (`area.py`, `config.BOUNDARY`): the union of three parts; the terrain is a block of 8192 × 8192 samples at 1.5 m (12.3 km per side).
  - The quadrilateral of the four given points, widened by 150 m.
  - The corridor of the Magliaso–Pura cantonal road.
  - The Magliaso–Agno–Bioggio–Manno–Gravesano cantonal road, with 150 m around it and the whole strip between the road and the east side of the quadrilateral. `strade_extra.py` extracts it from swissTLM3D (shortest path over the Canton's roads) and saves it in `dati/cantonale_gravesano.json`: this way the area doesn't depend on swissTLM3D, which is downloaded based on the area.
  - (v2.2) A 100 m corridor around the roads that left the map: the pass above Gravesano to Arosio (Stradón da Rós, the «Penudria»), the Ponte Tresa–Caslano–Magliaso cantonal road and, in Caslano, the village from the station to the lake and Via Torrazza up to the Torrazza. `strade_extra.py` computes them like the Gravesano cantonal road and saves them in `dati/strade_extra_v22.json`; a pocket that a corridor closes off against the rest of the area is included.
- **Network** (`network.py`): all swissTLM3D lines in the area, i.e. roads, forest roads, trails, mule tracks, stairways and bridges; tunnels are excluded. The lines are split at junctions, re-centred on the carriageways of the official survey and sampled every 2 m.
- **Profile** (`network_surface.py`): a single least-squares system over all the stations of the network.
  - Fit to the DTM, smoothness by road class, a single height at junctions, Tukey weights against survey anomalies.
  - The cantonal road is constrained to the v1.1 surface.
  - On bridges the profile between the abutments counts, except on culverts, where swissTLM3D and the DTM lie on the ground.
- **Surfaces** (`network_mesh.py`): the polygons of the official survey (carriageways, pavements, yards) and a strip along the lines with no survey polygon.
  - Heights come from projecting onto the lines within 6 m of the carriageway; yards far from the lines follow the DTM.
  - No surface goes more than 0.75 m below the lowest bare ground within 1 m.
  - The terrain is carved under the built meshes (`road_mesh.carve_window`): every vertex whose triangles touch a mesh drops 10 cm below the lowest face in the square of one grid step around it, so the terrain doesn't stick out even between one vertex and the next.
- **Walls** (`walls.py`): every terrain vertex whose triangles touch a wall drops to the base of the wall, so the 1.5 m grid doesn't make the terrain stick out in front of the face. Behind retaining walls a mesh on the terrain grid (`build_backfill`) puts the ground back at its level, in the material of the surrounding terrain. A survey wall that sticks out more than 30 cm above a carriageway, or above the passage strip around a line, is cut there (`drive_free`, `above_way`): the survey and swissTLM3D don't always agree, and a wall drawn across a road would block it.
- **Buildings** (`buildings_mesh.py`): where a building stands on a road or trail of the network (underpasses, the canopy of the Ponte Tresa customs post, an alley under a bell tower, a swissTLM3D line drawn inside a house) a passage 4.2 m high on roads and 3 m on trails is cut, closed by a ceiling and walls (`passages`); under a lower roof the passage stops under the roof, if at least 3 m (2.2 m on trails) remain.
- **Bridges** (`bridges.py`): deck, parapets, piers (never on a road or trail), terrain lowered under the slab. The manual corrections are in `dati/ponti.json` (`z0`, `z1`, `profile` `straight` or `tlm`, `type`, `skip`); `tlm` follows the swissTLM3D 3D line, for footbridges with stairs over a road. The check sheets are made with `bridge_report.py`.
- **Verification** (`check_level.py`, `review_map.py`, `render3d.py`):
  - automatic checks over the whole map, with the locations of the problems; among them the obstacles on the carriageway, searched along every road and trail at 0.5 and 1.6 m height against all solid meshes, and holes in the terrain;
  - 3D screenshots of the level without the game (three.js in Chromium), with an overview from above, bridges, roads, trails, villages and flagged spots.

## Sources and licences

- © swisstopo: swissALTI3D, SWISSIMAGE 10 cm, swissBUILDINGS3D 3.0, swissSURFACE3D (open geodata of the Swiss Confederation).
- Official survey: Ufficio del catasto e dei riordini fondiari (Cadastre and Land Consolidation Office), Canton Ticino (via geodienste.ch).
- © swisstopo: swissTLM3D (road and trail network, bridges), swissNAMES3D (villages), SWISSIMAGE 2 m (v2.0).
- © OpenStreetMap contributors (ODbL): minor roads for the AI network in the 1.x versions (since v2.0 the AI network comes from swissTLM3D).
- Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA): distant background.
- Federal Register of Buildings and Dwellings (RBD/GWR, Federal Statistical Office): category, period and floors of the buildings (v2.2).
- © OpenStreetMap contributors (ODbL): one-way streets, signs, stops, street furniture and, since v2.2, shops and businesses (`dati/osm_pois.json.gz`).
- Google Street View: visual reference only, for poses, objects, colours, guardrails, materials and verification. The repository and the release contain no Street View images; since v2.2 the photographic textures are not used even in local builds (except with `MAGLIASO_NO_PHOTO_TEXTURES=0`, for private study).
