BeamNG.drive (0.39) map of the **Malcantone**, version 2.5: the [v2.4](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.4) map with the same geometry, rebuilt so that the game needs much less memory and time to load. Same area (about 52 km² between Ponte Tresa, Caslano, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano and Sessa, 1:1 scale), same roads, buildings and vegetation.

**Installation:** copy `magliaso_pura_v2.5.zip` to `Documents/BeamNG.drive/current/mods/` (or install it from the mod manager) and remove the previous versions: the level is still called `magliaso_pura`.

## Why

This is the first version measured inside BeamNG.drive (0.39.4, on a PC with 16 GB of RAM, RTX 4070, Ryzen 7 7800X3D). v2.4 loaded in 215 s (371 s through BeamMP) and then wanted more memory than the PC had free: more than 10 minutes on the loading screen and the whole PC lagging.

Partial levels, loaded with a memory and frame-rate probe, showed where the memory goes (game memory at the peak):

| Level | Game memory | FPS at 3 spawn points |
|---|---|---|
| terrain + forest only | 7.1 GB | 100–140 |
| v2.5 without the road surfaces | 10.8 GB | 90–128 |
| v2.5 without the forest | 11.0 GB | 112–125 |
| v2.5 without the terrain | 10.6 GB | 100–125 |
| v2.5 complete | ~12 GB | 82–109 |

The meshes cost about 300 bytes of game memory per triangle, with or without collision. The forest costs about 0.7 GB and the 8192 × 8192 terrain 1–1.5 GB. Collision, the size of the terrain texture arrays and `useInstanceRenderData` make no measurable difference.

## Changes

- **Fewer objects.** The 128 m blocks of buildings, walls, road surfaces, guardrails, fences, water and vineyards are merged 3 × 3 (384 m), each group with its own collision and decal type: 7916 objects become 2188.
- **Shared vertices.** The meshes were written as triangle soups, with three vertices of their own for every triangle (2 per triangle on roads). Now the triangles share them: 38.2 → 19.7 million vertices. Positions, triangles and texture coordinates are unchanged (checked shape by shape against v2.4: 0 mm).
- **Road edges.** The skirts under the edges of the paved areas and the kerb faces along straight stretches have fewer triangles. Every piece was checked both ways and stays within 4 mm of the v2.4 shape: 15.9 → 15.3 million triangles in total.
- **Detail by distance.** Up to v2.4 every object was drawn up to 12 km. Now guardrails are no longer drawn beyond about 600 m, fences beyond 400 m, painted markings beyond 500 m, walls beyond 1.2 km, vineyards beyond 1 km, water and backfill beyond 2.5 km, and buildings and roads beyond 3 km. The distant landscape and the props spread over the whole map are always drawn.
- **Sun shadows** up to 800 m instead of 1600; terrain base textures at 1024 px instead of 2048 (smooth colour noise seen only from afar).

## Result in the game

| | v2.4 | v2.5 |
|---|---|---|
| Loading | 215 s (371 s through BeamMP), then stuck | 60 s (about 145 s the first time, while the game converts the shapes) |
| Objects | 7916 | 2188 |
| Vertices | 38.2 million | 19.7 million |
| FPS at the spawn points | not measurable | 82–128 |

## Known limitations

- **Memory:** the game still needs about 12 GB at its peak. On a 16 GB PC with other programs open (browser, Discord, ...) it can stall after loading: close them before playing.
- Only loading, memory and frame rate were measured in the game, at the spawn points. The look was not reviewed in the game, so the distances at which objects stop being drawn may need adjusting.
- The first load after installing is slower (about 145 s), because the game converts the shapes and keeps them in its cache.
- The v2.4 limitations remain (see its notes).

## How it is made

`beamng/pipeline/optimize_level.py` (with `mesh_strips.py`) turns the v2.4 release zip into this one:

```bash
python optimize_level.py magliaso_pura_v2.4.zip magliaso_pura_v2.5.zip
```

New builds share their vertices directly (`bng.MeshBuilder.write_dae`) and use the new terrain texture and shadow settings.

Sources: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); official survey of Canton Ticino (geodienste.ch); Federal Register of Buildings and Dwellings (FSO); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, provided under COPERNICUS by the EU and ESA). The Google Street View panoramas were used only as a visual reference: the mod contains no Street View images.
