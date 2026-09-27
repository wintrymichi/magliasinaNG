# Strada Cantonale Magliaso → Pura: pipeline della mappa BeamNG

Questa pipeline ricostruisce in scala 1:1 la Strada Cantonale da Magliaso a Pura (Ticino) come livello BeamNG.drive (`magliaso_pura`, versione 0.39). Il lavoro combina due tipi di fonte:

- le **366 panoramiche Street View** del dataset (`C:\Users\michi\Documents\magliasinaNG`: 363 di ottobre 2022, 3 del 2013/2014), usate per le pose delle camere, gli oggetti, la segnaletica, le texture e la validazione;
- i **dati ufficiali swisstopo e della misurazione ufficiale ticinese**, usati come riferimento metrico: terreno, edifici, carreggiate e muri.

## Contenuto di questa cartella

| Cartella | Cosa c'è |
|---|---|
| `pipeline/` | tutti gli script, dal download dei dati alla verifica; `config.py` contiene i percorsi |
| `verifica/` | `VERIFICA.md` (confronto con tutte le 1464 viste), il grafico della concordanza lungo il percorso, le metriche per vista (`metrics_final.json`, e `metrics_full1.json` prima dell'ultimo ciclo di correzione) |
| `dati/` | risultati di calcolo leggeri, per ricostruire il livello senza rifare i passi lunghi: pose calibrate delle panoramiche (`poses.json`), asse stradale, segnaletica e suo stato 2022, guardrail, muri di sostegno e altezze dei muri, recinzioni, lampioni, pali e cartelli, arredo, alberi e arbusti |

La **mod pronta** (livello `magliaso_pura`, BeamNG.drive 0.39) è nella [release v1.0](https://github.com/wintrymichi/magliasinaNG/releases/tag/v1.0). È costruita con `MAGLIASO_NO_PHOTO_TEXTURES=1`, quindi non contiene immagini Street View: facciate e muri hanno texture neutre nei colori misurati e le targhe sono a tinta unita. Le metriche in `verifica/` si riferiscono alla versione locale con le texture fotografiche.

## Dati di lavoro

I dati pesanti (non nel repository) stanno in `D:\beamng_magliaso\`: `data\` = download, `work\` = risultati intermedi, `venv\` = Python 3.13 con CUDA torch. Il livello viene scritto in `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\levels\magliaso_pura`.

## Sistema di coordinate

Il sistema di riferimento è LV95 (EPSG:2056) con origine locale E 2 710 830 / N 1 094 360, trasformata così:

```text
x = (E − E0) / K
y = (N − N0) / K
K = 1.000137497   (fattore di scala LV95 nell'origine)
```

Le quote sono ortometriche (LN02). Il terreno BeamNG misura 4096 × 4096 m, con un campione ogni metro. Tutto il livello (terreno, strade, edifici, oggetti, camere) usa questo stesso sistema.

## Ordine degli script (cartella `pipeline`)

| Fase | Script | Risultato |
|---|---|---|
| Dati | `download_swisstopo.py`, `download_av.py` | swissALTI3D 0,5 m, SWISSIMAGE 10 cm, swissBUILDINGS3D, swissSURFACE3D (LiDAR), misurazione ufficiale TI (WFS geodienste.ch) |
| Raster | `build_rasters.py`, `landcover.py`, `extract_buildings.py`, `lidar_extract.py` | DTM/DSM 0,5 m, ortofoto, copertura del suolo, edifici, punti LiDAR vicino alla strada |
| Pose camere | `calibrate_attitude.py`, `refine_poses.py`, `solve_poses.py`, `calib_camheight.py` | posizione e orientamento di ogni panoramica, registrati sull'ortofoto con precisione di circa 0,3 m (Viterbi lungo la traiettoria) |
| Segmentazione | `segment_views.py` | Mask2Former Swin-L (Mapillary Vistas) su tutte le viste |
| Strada | `road_profile.py`, `road_strip.py`, `pano_strip.py`, `roadheight.py` | asse e sezione della strada; "strisce raddrizzate" da ortofoto e da panoramiche; quota del piano stradale senza cedimenti ai bordi |
| Segnaletica | `markings.py`, `markings_photo.py`, `markings_raster.py`, `marking_votes.py`, `markings_state.py` | linee da ortofoto verificate nelle foto; stato di ottobre 2022: tratti senza segnaletica, bande rosse, mezzeria spostata |
| Muri e barriere | `roadside_walls.py`, `wall_caps.py`, `guardrails.py`, `guardrails2.py`, `fences.py` | muri di sostegno; altezza visibile dei muri misurata nelle foto (via creste LiDAR false: tetti, balconi, guardrail sopra i muri); guardrail; ringhiere e recinzioni sui muri |
| Oggetti | `poles.py`, `lamps.py`, `objects.py` | pali, cartelli (con l'immagine della targa), lampioni triangolati, arredo urbano |
| Vegetazione | `trees.py`, `understory.py` | alberi dal modello di superficie normalizzato (posizione, altezza, chioma), siepi e cespugli |
| Texture | `terrain_colors.py`, `texture_buildings.py`, `texture_walls.py` | colori misurati nelle foto; facciate e muri proiettati dalle panoramiche |
| Livello | `build_level.py` | tutte le fasi, dalla strada agli spawn, più `info.json` |
| Verifica | `validation.py`, `run_validation.ps1`, `validate_metrics.py`, `verify_report.py`, `bng_lua/magliaso_validate.lua` | giro della camera in gioco alle pose delle foto (anche tutte le 1464 viste), confronto per segmentazione, controllo della rete stradale per l'IA, rapporto `VERIFICA.md` |
| Correzione | `photo_votes.py`, `missing_veg.py` | voti multi-vista delle etichette; arbusti che le foto mostrano e il gioco no (dal confronto sull'intero dataset) |
| Pacchetto | `package.py` | zip della mod in `D:\beamng_magliaso\dist` |

## Ricostruire il livello

```bash
D:/beamng_magliaso/venv/Scripts/python.exe -u build_level.py
```

Per una versione senza immagini tratte da Street View (facciate, muri e cartelli fotografici), da usare per la pubblicazione:

```bash
MAGLIASO_NO_PHOTO_TEXTURES=1 D:/beamng_magliaso/venv/Scripts/python.exe -u build_level.py
```

La verifica si fa in tre passi:

1. `validation.py make <indici> 90`, oppure `makefull` per tutte le 366 panoramiche;
2. `run_validation.ps1`: per il giro completo le schermate JPEG vanno spostate in `work\validation_full\game`;
3. `validate_metrics.py <tag>`, oppure `validate_metrics.py <tag> full` seguito da `verify_report.py <tag>`.

## Fonti e licenze

- © swisstopo: swissALTI3D, SWISSIMAGE 10 cm, swissBUILDINGS3D 3.0, swissSURFACE3D (dati geografici aperti della Confederazione).
- Misurazione ufficiale: Ufficio del catasto e dei riordini fondiari, Cantone Ticino (via geodienste.ch).
- © OpenStreetMap contributors (ODbL): strade secondarie per la rete dell'IA.
- Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA): sfondo lontano.
- Google Street View (panoramiche del dataset): riferimento per pose, oggetti, colori e verifica. Il repository e la release non contengono immagini Street View. Solo costruendo il livello in locale con le panoramiche (senza `MAGLIASO_NO_PHOTO_TEXTURES`) facciate, muri e cartelli ricevono le texture proiettate dalle foto; quella versione è per uso personale.
