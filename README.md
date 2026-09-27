Strada Cantonale (Magliaso → Pura)

Percorso: 45.981686, 8.878474 → 46.001760, 8.860159 · 3,7 km, tutto sulla Strada Cantonale.

> **Le immagini non sono nel repository.** Le cartelle `panorami/`, `viste/` e `storici_2013_2014/` (9,4 GB) contengono immagini Google Street View e restano in locale. Il repository contiene i metadati (pose, date, posizioni) e gli script con cui le immagini si riscaricano: `sv_capture.py`, `expand.py`, `finalize.py`.

**Mappa BeamNG.drive** ricostruita da questo dataset: vedi [`beamng/`](beamng/README.md). La mod è nella [release v2.0](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.0), che allarga la mappa a tutto il Malcantone (circa 46 km² tra Ponte Tresa, Manno, Cademario, Novaggio e Sessa) con ogni strada e sentiero guidabile. Le versioni precedenti, solo la cantonale, sono la [v1.1](https://github.com/wintrymichi/magliasinaNG/releases/tag/v1.1) (strade lisce, carreggiata senza alberi) e la [v1.0](https://github.com/wintrymichi/magliasinaNG/releases/tag/v1.0).

## Contenuto

| Cartella/file | Cosa c'è |
|---|---|
| `panorami/` | Panorami 360° equirettangolari, 6656×3328, uno ogni ~10 m. Nome: `NNNN_<panoId>.jpg` (NNNN = ordine lungo la strada) |
| `viste/` | 16 viste prospettiche per panorama (FOV 90°, 1600×1200): 8 direzioni × 2 inclinazioni |
| `panoramas.csv / .json` | Per ogni panorama: lat, lon, quota (m), data, heading, pitch/roll della camera, distanza lungo la strada |
| `panoramas.geojson` | Posizioni dei panorami (apribile in QGIS / geojson.io) |
| `cameras.json` | Per ogni vista: file, posizione GPS, quota, direzione bussola (yaw), pitch, FOV → pose note per la fotogrammetria |
| `panoramas_all_dates.json` | Anche i panorami storici (2013/2014) trovati sullo stesso tratto, non scaricati |
| `sv_capture.py`, `expand.py`, `finalize.py` | Script usati (ri-eseguibili) |

Nomi delle viste: `NNNN_<panoId>_<direzione>_p<pitch>.jpg`
- direzione relativa al senso di marcia: `fwd`, `fwd_r`, `right`, `back_r`, `back`, `back_l`, `left`, `fwd_l` (passi di 45°, quindi ~45° di sovrapposizione tra viste adiacenti)
- `p00` = orizzonte, `p25` = 25° verso l'alto (facciate, tetti, versanti)

## Note sulla copertura

- Immagini quasi tutte di **ottobre 2022** (coerenti tra loro). 3 panorami del 2013 usati solo dove il 2022 manca.
- **Buco di ~110 m** a circa 1,28–1,36 km dall'inizio (≈ 45.9858, 8.8692 → 45.9869, 8.8694): Google non ha panorami lì in nessuna data vicina alla strada.
- La barra/ombra della Google car è visibile in basso nelle viste `p00` verso `fwd`/`back`: meglio mascherarla o usare le `p25` per le facciate.

## Uso per la ricostruzione 3D

- **COLMAP / RealityCapture / Metashape**: usa `viste/` (immagini prospettiche, intrinseci noti: fx = fy = 800 px, cx = 800, cy = 600, nessuna distorsione). Le posizioni GPS in `cameras.json` servono come prior/georeferenziazione.
- **Metashape** accetta anche direttamente i panorami sferici di `panorami/` (camera type "Spherical").
- **Gaussian Splatting / NeRF** (nerfstudio, Postshot…): elabora prima le `viste/` con COLMAP, poi allena.

## Mappa BeamNG.drive

La cartella [`beamng/`](beamng/README.md) contiene la pipeline che ricostruisce in scala 1:1 come livello BeamNG.drive 0.39 (`magliaso_pura`) la strada e, dalla v2.0, tutto il Malcantone intorno:

- le panoramiche danno le pose calibrate, gli oggetti, la segnaletica del 2022 e la verifica della cantonale;
- i dati ufficiali swisstopo e della misurazione ufficiale ticinese danno il terreno, la rete di strade e sentieri, i ponti, gli edifici, i muri e gli alberi di tutta l'area.

La cartella contiene anche la verifica della cantonale contro tutte le 1464 viste, i controlli automatici della v2.0 e i risultati di calcolo leggeri. La mod pronta da installare è nella [release v2.0](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.0).
