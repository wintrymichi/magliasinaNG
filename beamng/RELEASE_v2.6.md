BeamNG.drive (0.39) map of the **Malcantone**, version 2.6: the [v2.5](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.5) map with new grass. Same area (about 52 km² between Ponte Tresa, Caslano, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano and Sessa, 1:1 scale), same roads, buildings and trees.

**Installation:** copy `magliaso_pura_v2.6.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

## Grass

Up to v2.5 the grass was drawn by the pipeline in a single texture without an opacity map: in the game the tufts showed up as dark opaque cards, and only up to 50 m from the camera.

Now the meadows and gardens use the game's own grass and flower textures. They come with colour, opacity, normal, roughness and ambient occlusion maps, and light passes through the blades. They are laid out like the game's Italy level:

| Layer | Texture | Up to (fades from) | Clumps at most |
|---|---|---|---|
| close | short grass | 50 m (30 m) | 160,000 |
| middle | short grass | 120 m (80 m) | 150,000 |
| far | long grass | 120 m (80 m) | 150,000 |
| flowers | daisies, buttercups, geraniums, poppies (meadows only) | 50 m (30 m) | 30,000 |

The gardens have short, mown lawn and no flowers. As before, there is no grass on the road and path verges, so it never stands through the road meshes. The textures are referenced where the game keeps them (`/assets/materials/foliage`): nothing is copied into the mod.

## Measured in the game

BeamNG.drive 0.39.4, 16 GB of RAM, RTX 4070, 2560 × 1440:

- 72–111 fps at the test points: two meadows, a garden, and the cantonal road at Magliaso and halfway up the climb. In v2.5 the spawn points ran at 82–128 fps.
- Memory as in v2.5: the game peaks at about 12 GB, so on a 16 GB PC close other programs before playing.

If the grass costs too much, lower the vegetation quality in the game's graphics settings.

## How it is made

`beamng/pipeline/patch_groundcover.py` turns the v2.5 release zip into this one; new builds get the same grass from `groundcover.py`:

```bash
python patch_groundcover.py magliaso_pura_v2.5.zip magliaso_pura_v2.6.zip
```

Sources: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); official survey of Canton Ticino (geodienste.ch); Federal Register of Buildings and Dwellings (FSO); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA). The Google Street View panoramas were used only as a visual reference: the mod contains no Street View images.
