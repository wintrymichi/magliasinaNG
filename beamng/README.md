# Malcantone (Strada Cantonale Magliaso → Pura e dintorni): pipeline della mappa BeamNG

Questa pipeline ricostruisce in scala 1:1 il Malcantone (Ticino) come livello BeamNG.drive (`magliaso_pura`, versione 0.39). Il livello copre circa 46 km² tra Ponte Tresa, Magliaso, Manno, Cademario, Novaggio, Astano e Sessa. Al centro c'è la Strada Cantonale da Magliaso a Pura delle versioni 1.x. Il lavoro combina due tipi di fonte:

- le **366 panoramiche Street View** del dataset lungo la cantonale (`C:\Users\michi\Documents\magliasinaNG`: 363 di ottobre 2022, 3 del 2013/2014), usate per le pose delle camere, gli oggetti, la segnaletica, le texture e la validazione;
- i **dati ufficiali swisstopo e della misurazione ufficiale ticinese**, usati come riferimento metrico per tutta l'area: terreno, rete stradale (swissTLM3D), carreggiate, edifici, muri e alberi.

## Contenuto di questa cartella

| Cartella | Cosa c'è |
|---|---|
| `pipeline/` | tutti gli script, dal download dei dati alla verifica; `config.py` contiene i percorsi |
| `verifica/` | `VERIFICA.md` (confronto con tutte le 1464 viste), il grafico della concordanza lungo il percorso, le metriche per vista (`metrics_final.json`, e `metrics_full1.json` prima dell'ultimo ciclo di correzione) |
| `dati/` | risultati di calcolo leggeri, per ricostruire il livello senza rifare i passi lunghi: pose calibrate delle panoramiche (`poses.json`), asse stradale, segnaletica e suo stato 2022, guardrail, muri di sostegno e altezze dei muri, recinzioni, lampioni, pali e cartelli, arredo, alberi e arbusti |

La **mod pronta** è nella [release v2.0](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.0), che il workflow `.github/workflows/release_v2.0.yml` costruisce da zero su un server GitHub: scarica i dati, costruisce il livello, lo controlla con `check_level.py` e lo pubblica. È costruita con `MAGLIASO_NO_PHOTO_TEXTURES=1`, quindi non contiene immagini Street View: facciate e muri hanno texture neutre nei colori misurati e le targhe sono a tinta unita. Gli oggetti della cantonale ricavati dalle foto (segnaletica, lampioni, pali, cartelli, arredo) vengono presi dalla release v1.1 e appoggiati sulle nuove superfici (`carryover.py`).

Le versioni precedenti restano disponibili:
- **v1.0**: solo il corridoio della cantonale.
- **v1.1**: la cantonale con le strade lisce e la carreggiata sgombra (`patch_release.py`, `.github/workflows/release_v1.1.yml`).

Le metriche di `verifica/VERIFICA.md` riguardano la cantonale nella versione locale con le texture fotografiche e la geometria della v1.0. La verifica della v2.0 è in `verifica/check_level.json` (controlli automatici su tutta la mappa) e in `verifica/ponti/` (profili dei ponti).

## Versione 2.0: area, rete stradale, ponti

- **Area** (`area.py`, `config.BOUNDARY`): il quadrilatero dei quattro punti indicati, allargato di 150 m, più il corridoio della cantonale. Il terreno è un blocco di 8192 × 8192 campioni a 1,5 m (12,3 km di lato).
- **Rete** (`network.py`): tutte le linee di swissTLM3D nell'area, cioè strade, strade forestali, sentieri, mulattiere, scalinate e ponti; le gallerie sono escluse. Le linee sono spezzate agli incroci, ricentrate sulle carreggiate della misurazione ufficiale e campionate ogni 2 m.
- **Profilo** (`network_surface.py`): un unico sistema ai minimi quadrati su tutte le stazioni della rete.
  - Adattamento al DTM, liscezza per classe di strada, quota unica agli incroci, pesi di Tukey contro le anomalie del rilievo.
  - La cantonale è vincolata alla superficie della v1.1.
  - Sui ponti conta il profilo tra le spalle, salvo i tombini, dove swissTLM3D e il DTM stanno sul terreno.
- **Superfici** (`network_mesh.py`): i poligoni della misurazione ufficiale (carreggiate, marciapiedi, piazzali) e una striscia lungo le linee senza rilievo. Le quote vengono dalla proiezione sulle linee vicine. Il terreno viene scavato sotto le mesh costruite.
- **Ponti** (`bridges.py`): impalcato, parapetti, piloni, terreno abbassato sotto la soletta. Le correzioni manuali sono in `dati/ponti.json` (`z0`, `z1`, `profile`, `type`, `skip`). Le schede di controllo si fanno con `bridge_report.py`.
- **Verifica** (`check_level.py`, `review_map.py`, `render3d.py`):
  - controlli automatici su tutta la mappa, con i luoghi dei problemi;
  - screenshot 3D del livello senza il gioco (three.js in Chromium), con panoramica dall'alto, ponti, strade, sentieri, paesi e punti segnalati.

## Dati di lavoro

I dati pesanti (non nel repository) stanno in `D:\beamng_magliaso\`: `data\` = download, `work\` = risultati intermedi, `venv\` = Python 3.13 con CUDA torch. Il livello viene scritto in `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\levels\magliaso_pura`.

## Sistema di coordinate

Il sistema di riferimento è LV95 (EPSG:2056) con origine locale E 2 710 830 / N 1 094 360, trasformata così:

```text
x = (E − E0) / K
y = (N − N0) / K
K = 1.000137497   (fattore di scala LV95 nell'origine)
```

Le quote sono ortometriche (LN02). Il terreno BeamNG misura 12,3 × 12,3 km: 8192 × 8192 campioni a 1,5 m, con l'angolo sud-ovest in x = −7230, y = −4731 (v1.x: 4096 × 4096 m a 1 m). Tutto il livello (terreno, strade, edifici, oggetti, camere) usa questo stesso sistema.

## Ordine degli script (cartella `pipeline`)

| Fase | Script | Risultato |
|---|---|---|
| Dati | `download_swisstopo.py`, `download_av.py`, `download_tlm.py` | swissALTI3D 0,5 m e 2 m, swissSURFACE3D 0,5 m, SWISSIMAGE 2 m (10 cm e LiDAR lungo la cantonale con `--route-extras`), swissBUILDINGS3D, swissNAMES3D, Copernicus GLO-30; misurazione ufficiale TI (WFS geodienste.ch); swissTLM3D (strade, ferrovie, corsi d'acqua) letto a pezzi dal pacchetto nazionale |
| Raster | `build_rasters.py`, `landcover.py`, `extract_buildings.py`, `lidar_extract.py` | DTM/DSM 0,5 m, ortofoto, copertura del suolo, edifici, punti LiDAR vicino alla strada |
| Pose camere | `calibrate_attitude.py`, `refine_poses.py`, `solve_poses.py`, `calib_camheight.py` | posizione e orientamento di ogni panoramica, registrati sull'ortofoto con precisione di circa 0,3 m (Viterbi lungo la traiettoria) |
| Segmentazione | `segment_views.py` | Mask2Former Swin-L (Mapillary Vistas) su tutte le viste |
| Strada | `road_profile.py`, `road_strip.py`, `pano_strip.py`, `roadheight.py`, `surface_fit.py` | asse e sezione della strada; "strisce raddrizzate" da ortofoto e da panoramiche; superficie idealizzata delle aree pavimentate: adattamento liscio e robusto al DTM (lastra sottile, pesi di Tukey), sezione piana e profilo più rigido sulla carreggiata della cantonale, ponti ricostruiti sopra i vuoti del DTM, gradini dove due superfici stanno a quote diverse |
| Segnaletica | `markings.py`, `markings_photo.py`, `markings_raster.py`, `marking_votes.py`, `markings_state.py` | linee da ortofoto verificate nelle foto; stato di ottobre 2022: tratti senza segnaletica, bande rosse, mezzeria spostata |
| Muri e barriere | `roadside_walls.py`, `wall_caps.py`, `guardrails.py`, `guardrails2.py`, `fences.py` | muri di sostegno; altezza visibile dei muri misurata nelle foto (via creste LiDAR false: tetti, balconi, guardrail sopra i muri); guardrail; ringhiere e recinzioni sui muri |
| Oggetti | `poles.py`, `lamps.py`, `objects.py` | pali, cartelli (con l'immagine della targa), lampioni triangolati, arredo urbano |
| Vegetazione | `trees.py`, `understory.py`, `clearance.py` | alberi dal modello di superficie normalizzato (posizione, altezza, chioma), siepi e cespugli; niente tronchi sulle superfici pavimentate, arbusti e siepi arretrati dal bordo |
| Texture | `terrain_colors.py`, `texture_buildings.py`, `texture_walls.py` | colori misurati nelle foto; facciate e muri proiettati dalle panoramiche |
| Livello | `build_level.py` | tutte le fasi, dalla strada agli spawn, più `info.json` |
| Verifica | `validation.py`, `run_validation.ps1`, `validate_metrics.py`, `verify_report.py`, `bng_lua/magliaso_validate.lua` | giro della camera in gioco alle pose delle foto (anche tutte le 1464 viste), confronto per segmentazione, controllo della rete stradale per l'IA, rapporto `VERIFICA.md` |
| Correzione | `photo_votes.py`, `missing_veg.py` | voti multi-vista delle etichette; arbusti che le foto mostrano e il gioco no (dal confronto sull'intero dataset) |
| Rete (v2.0) | `network.py`, `network_surface.py`, `network_mesh.py`, `bridges.py`, `water.py`, `places.py` | rete stradale e sentieri swissTLM3D, profilo liscio, superfici guidabili, ponti, lago, paesi |
| Verifica (v2.0) | `check_level.py`, `review_map.py`, `bridge_report.py`, `render3d.py` | controlli su tutta la mappa, screenshot 3D, schede dei ponti |
| Senza il gioco | `prepare_work.py`, `vanilla.py`, `carryover.py`, `ogr_tin.py` | costruzione nel cloud: risultati leggeri da `dati/`, file vanilla e oggetti della cantonale dallo zip della v1.1, lettura dei TIN di swissBUILDINGS3D |
| Pacchetto | `package.py` | zip della mod in `<MAGLIASO_ROOT>/dist` |
| Correzione di una release | `patch_release.py` | applica le correzioni della v1.1 (strade, terreno, segnaletica, IA, oggetti, vegetazione) a uno zip già costruito, usando solo lo zip e `dati/` |

## Ricostruire il livello

In locale (Windows, con il gioco e le panoramiche):

```bash
D:/beamng_magliaso/venv/Scripts/python.exe -u build_level.py
```

Senza il gioco e senza le panoramiche (come fa il workflow della v2.0), con i percorsi dati da variabili d'ambiente:

```bash
export MAGLIASO_ROOT=/percorso/dati MAGLIASO_DATASET=$PWD/../.. MAGLIASO_BEAMNG_USER=/percorso/beamng_user
export MAGLIASO_BEAMNG_GAME=/nonexistent MAGLIASO_NO_PHOTO_TEXTURES=1 MAGLIASO_REFERENCE_ZIP=/percorso/magliaso_pura_v1.1.zip
python prepare_work.py && python download_swisstopo.py && python download_av.py && python download_tlm.py
python build_rasters.py && python landcover.py && python extract_buildings.py && python trees.py
python network.py && python network_surface.py && python build_level.py && python check_level.py
python package.py magliaso_pura_v2.0
```

`build_level.py --reuse-roads` rifà tutte le fasi tranne la rete stradale, che è la più lunga (circa 13 minuti). Riusa le mesh stradali della costruzione precedente e `work/roads_state.npz`.

Per una versione senza immagini tratte da Street View (facciate, muri e cartelli fotografici), da usare per la pubblicazione:

```bash
MAGLIASO_NO_PHOTO_TEXTURES=1 D:/beamng_magliaso/venv/Scripts/python.exe -u build_level.py
```

La superficie delle strade (`roadheight.py` → `work\road_surface.npz`) si calcola alla prima fase che la usa; va cancellata per ricalcolarla, per esempio dopo aver cambiato i parametri in `surface_fit.py`. I guardrail e i muri vicini alla strada vengono riallineati alla nuova superficie durante la costruzione. `guardrails2.py` e `wall_caps.py` leggono la superficie solo quando si rifanno quei passi.

Per aggiornare lo zip della v1.0 senza i dati di lavoro (circa 5 minuti; servono numpy, scipy, shapely e rasterio):

```bash
python patch_release.py magliaso_pura_v1.0.zip magliaso_pura_v1.1.zip
```

La verifica si fa in tre passi:

1. `validation.py make <indici> 90`, oppure `makefull` per tutte le 366 panoramiche;
2. `run_validation.ps1`: per il giro completo le schermate JPEG vanno spostate in `work\validation_full\game`;
3. `validate_metrics.py <tag>`, oppure `validate_metrics.py <tag> full` seguito da `verify_report.py <tag>`.

## Fonti e licenze

- © swisstopo: swissALTI3D, SWISSIMAGE 10 cm, swissBUILDINGS3D 3.0, swissSURFACE3D (dati geografici aperti della Confederazione).
- Misurazione ufficiale: Ufficio del catasto e dei riordini fondiari, Cantone Ticino (via geodienste.ch).
- © swisstopo: swissTLM3D (rete stradale e sentieri, ponti), swissNAMES3D (paesi), SWISSIMAGE 2 m (v2.0).
- © OpenStreetMap contributors (ODbL): strade secondarie per la rete dell'IA nelle versioni 1.x (dalla v2.0 la rete dell'IA viene da swissTLM3D).
- Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA): sfondo lontano.
- Google Street View (panoramiche del dataset): riferimento per pose, oggetti, colori e verifica. Il repository e la release non contengono immagini Street View. Solo costruendo il livello in locale con le panoramiche (senza `MAGLIASO_NO_PHOTO_TEXTURES`) facciate, muri e cartelli ricevono le texture proiettate dalle foto; quella versione è per uso personale.
