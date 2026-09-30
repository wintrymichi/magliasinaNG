# Revisione della mappa su Street View (v2.2)

Generato da `pipeline/review_report.py` (dati in `revisione.json`). Per ogni strada della rete: quanta parte è coperta dalle panoramiche Street View (entro 15 m) e di che anni, quante panoramiche sono state usate nella revisione (una ogni 20 m, `sv_fetch.py`), gli edifici lungo la strada con il tono della facciata misurato nelle foto, i muri di cui le foto mostrano il materiale, i guardrail visti nelle foto e la quota dei bordi della strada osservata, gli eventi della prova di guida virtuale (`drive_test.py`: STEP gradino sotto una ruota, LIFT ruota staccata, HARD accelerazione verticale forte, HOLE ruota senza superficie, TWIST cambio brusco di rollio o beccheggio) prima (v2.1) e dopo questa revisione, e i luoghi confrontati a vista (foto e mappa dalla stessa camera). Stato: `[x]` verificata sulle foto e sui dati, `[~]` foto solo per una parte, `[!]` nessuna panoramica (strade forestali, private): verificata sui dati ufficiali e sull'ortofoto.

Totale: 227.7 km di strade, 176.9 km verificati sulle foto (`[x]`), 43.3 km in parte (`[~]`).

Le misure prese nelle foto sono state controllate a campione guardando le foto stesse: i guardrail rilevati (tratti a caso con la linea del guardrail proiettata nella panoramica: tutti veri e allineati), le classi dei muri (la pietra è affidabile; calcestruzzo e intonaco solo quando le foto sono chiare, altrimenti resta la pietra) e il tono delle facciate (schiarito: le foto lo danno più scuro e più grigio). I luoghi confrontati e l'esito di ognuno sono in `dati/qa_review.json`.

## Agno

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 2.14 | 30 % (2013-2022) | 31 | 91 | plaster 1, stone 2, unknown 8 | - | 16 % | HARD 962, LIFT 62, STEP 33, TWIST 24 | HARD 532, LIFT 26, STEP 7, TWIST 26 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.84 | 48 % (2013-2014) | 22 | 33 | concrete 3, stone 1, unknown 6 | - | 27 % | HARD 424, LIFT 94, STEP 12, TWIST 37 | HARD 306 | 0 | - | [~] |
| Contrada Nuova | 0.07 | 0 %  | 0 | 4 | - | - | 0 % | HARD 6 | 0 | 0 | - | [!] |
| Contrada San Marco | 1.00 | 100 % (2018-2022) | 35 | 16 | stone 22, unknown 1 | 22 m | 50 % | HARD 313, LIFT 14 | HARD 302, LIFT 4 | 0 | - | [x] |
| Piazza Col. Vicari | 0.17 | 47 % (2014-2022) | 3 | 8 | - | - | 29 % | HARD 491, LIFT 5 | HARD 375 | 0 | - | [~] |
| Piazza Giovanni Negri | 0.17 | 100 % (2013-2014) | 6 | 11 | stone 1, unknown 1 | - | 28 % | HARD 145, LIFT 1 | HARD 119 | 0 | - | [x] |
| Piazza San Provino | 0.11 | 44 % (2013) | 2 | 6 | unknown 1 | - | 23 % | 0 | 0 | 0 | - | [~] |
| Piazza del Sole | 0.07 | 47 % (2013) | 1 | 3 | - | - | 22 % | HARD 28, STEP 2 | HARD 1 | 0 | - | [~] |
| Strada Regina | 1.85 | 78 % (2013-2014) | 46 | 44 | plaster 1, stone 2, unknown 5 | 86 m | 38 % | HARD 2032, LIFT 87 | HARD 1597, LIFT 35, STEP 2 | 0 | - | [x] |
| Via Bernardino Quadri | 0.17 | 0 %  | 0 | 5 | - | - | 0 % | 0 | 0 | 0 | - | [!] |
| Via Burico | 0.10 | 100 % (2013) | 6 | 3 | stone 2 | - | 37 % | HARD 123, LIFT 10 | HARD 136 | 0 | - | [x] |
| Via Campagna | 0.30 | 68 % (2013) | 9 | 5 | unknown 1 | - | 36 % | HARD 216, LIFT 24, STEP 2 | HARD 134, LIFT 13 | 0 | - | [x] |
| Via Cassinelle | 0.26 | 100 % (2013-2014) | 11 | 11 | unknown 1 | - | 50 % | HARD 361, LIFT 14, STEP 2, TWIST 8 | HARD 211, LIFT 17 | 0 | - | [x] |
| Via Collina | 0.13 | 13 % (2013) | 1 | 3 | unknown 1 | - | 4 % | HARD 230, LIFT 24, STEP 6, TWIST 28 | HARD 224, LIFT 7 | 0 | - | [~] |
| Via Fontanelle | 0.12 | 100 % (2014) | 7 | 10 | stone 2, unknown 2 | - | 45 % | HARD 89, LIFT 2 | HARD 102 | 0 | - | [x] |
| Via Fontanone | 0.12 | 11 % (2022) | 1 | 3 | stone 1 | - | 7 % | 0 | 0 | 0 | - | [~] |
| Via Gaggio | 0.35 | 83 % (2013) | 11 | 6 | - | - | 40 % | HARD 889, LIFT 26 | HARD 775, LIFT 7, STEP 2 | 0 | - | [x] |
| Via Gasparetto | 0.32 | 89 % (2013) | 11 | 10 | unknown 2 | - | 42 % | HARD 263, LIFT 6, STEP 4, TWIST 6 | HARD 192 | 0 | - | [x] |
| Via Giacomo Rusca | 0.17 | 100 % (2013-2014) | 8 | 11 | plaster 1, unknown 1 | - | 44 % | HARD 3 | 0 | 0 | - | [x] |
| Via Ginnasio | 0.22 | 84 % (2014) | 6 | 8 | concrete 1, stone 2, unknown 2 | - | 42 % | HARD 193 | HARD 70 | 0 | - | [x] |
| Via Girora | 0.31 | 100 % (2013) | 15 | 22 | concrete 2, stone 1, unknown 1 | - | 50 % | HARD 11 | 0 | 0 | - | [x] |
| Via Giuseppe Quadri | 0.17 | 100 % (2013) | 8 | 15 | stone 1, unknown 1 | - | 40 % | HARD 410, LIFT 17, STEP 4, TWIST 9 | HARD 251, LIFT 14, TWIST 9 | 1 | fienile in mattoni e pietra reso come casa intonacata | [x] |
| Via Guasti | 0.08 | 0 %  | 0 | 1 | - | - | 0 % | HARD 31 | HARD 21 | 0 | - | [!] |
| Via Laghetti | 0.37 | 100 % (2013) | 16 | 21 | concrete 2, stone 2, unknown 2 | - | 50 % | HARD 128, LIFT 24, STEP 8, TWIST 10 | HARD 6 | 0 | - | [x] |
| Via Molinazzo | 0.15 | 100 % (2013-2022) | 6 | 12 | plaster 1, stone 2, unknown 1 | - | 43 % | HARD 66 | HARD 26, STEP 2 | 0 | - | [x] |
| Via Mondadiscio | 0.15 | 13 % (2013) | 0 | 4 | unknown 1 | - | 2 % | HARD 41 | HARD 19 | 0 | - | [~] |
| Via Mondonico | 0.99 | 100 % (2013-2014) | 36 | 37 | plaster 2, stone 3, unknown 10 | 58 m | 43 % | HARD 1180, LIFT 26, STEP 5 | HARD 894 | 0 | - | [x] |
| Via Mulino della Bolla | 0.20 | 84 % (2013-2014) | 7 | 6 | - | - | 44 % | HARD 230, LIFT 2 | HARD 200 | 0 | - | [x] |
| Via Oro | 0.24 | 17 % (2013) | 2 | 8 | stone 1, unknown 1 | - | 10 % | HARD 27 | HARD 4 | 0 | - | [~] |
| Via Ortaccio | 0.09 | 100 % (2013) | 5 | 12 | - | - | 47 % | HARD 201, LIFT 3 | HARD 62 | 0 | - | [x] |
| Via Pezza | 0.30 | 100 % (2013-2014) | 15 | 10 | unknown 4 | - | 46 % | HARD 853, LIFT 62, STEP 15, TWIST 33 | HARD 597, LIFT 19, STEP 3, TWIST 2 | 0 | - | [x] |
| Via Prada | 0.50 | 59 % (2013) | 11 | 15 | stone 2, unknown 3 | 38 m | 30 % | HARD 1409, LIFT 50, STEP 2, TWIST 2 | HARD 1048, LIFT 7 | 0 | - | [x] |
| Via Redondello | 0.38 | 42 % (2013) | 6 | 9 | unknown 1 | - | 22 % | HARD 208, LIFT 14 | HARD 267, LIFT 8, STEP 4, TWIST 44 | 0 | - | [~] |
| Via Righetti | 0.56 | 100 % (2013) | 20 | 4 | plaster 1, unknown 1 | 12 m | 32 % | HARD 138, LIFT 5, STEP 1 | HARD 146, LIFT 3, STEP 1 | 0 | - | [x] |
| Via Rivera | 0.09 | 100 % (2013-2022) | 5 | 0 | - | - | 50 % | HARD 76, LIFT 2, STEP 4 | HARD 5 | 0 | - | [x] |
| Via Ronchettaccio | 0.15 | 100 % (2013) | 5 | 9 | concrete 1 | - | 48 % | HARD 344, LIFT 76, STEP 2, TWIST 23 | HARD 378, LIFT 45, STEP 4, TWIST 34 | 0 | - | [x] |
| Via Ronco | 0.47 | 91 % (2013) | 17 | 5 | plaster 1, unknown 1 | - | 39 % | HARD 600, LIFT 37, STEP 7 | HARD 413, LIFT 4 | 0 | - | [x] |
| Via San Giorgio | 0.23 | 100 % (2013) | 8 | 12 | stone 1 | 12 m | 30 % | HARD 98, LIFT 13, STEP 3 | HARD 268, LIFT 17 | 0 | - | [x] |
| Via Sasselli | 0.47 | 71 % (2013-2014) | 13 | 26 | stone 3, unknown 6 | - | 33 % | HARD 792, LIFT 27, STEP 8, TWIST 5 | HARD 510 | 0 | - | [x] |
| Via Selva | 0.81 | 100 % (2013) | 32 | 23 | stone 5, unknown 2 | - | 43 % | HARD 777, LIFT 67, STEP 10, TWIST 47 | HARD 622, LIFT 47, STEP 6, TWIST 8 | 0 | - | [x] |
| Via Stazione | 0.09 | 100 % (2013) | 5 | 7 | unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Svena | 0.26 | 36 % (2013) | 3 | 13 | unknown 1 | - | 13 % | HARD 191, LIFT 15, STEP 4, TWIST 6 | HARD 79 | 0 | - | [~] |
| Via Vidighetto | 1.11 | 91 % (2013-2014) | 39 | 37 | concrete 1, stone 8, unknown 6 | 138 m | 45 % | HARD 882, LIFT 43, STEP 7, TWIST 30 | HARD 487, LIFT 14 | 0 | - | [x] |
| Via Vignascia | 0.40 | 65 % (2013) | 9 | 20 | stone 1, unknown 3 | - | 33 % | HARD 182, LIFT 23, STEP 10, TWIST 2 | HARD 45 | 0 | - | [x] |
| Via ai Campi | 0.18 | 63 % (2013) | 5 | 3 | stone 1 | - | 21 % | HARD 247, LIFT 50, STEP 8, TWIST 27 | HARD 60 | 1 | - | [x] |
| Via al Bosco | 0.15 | 100 % (2013) | 7 | 11 | - | - | 23 % | HARD 119 | HARD 31 | 0 | - | [x] |
| Via alle Ere | 0.14 | 36 % (2013) | 2 | 4 | - | - | 0 % | HARD 311, LIFT 28, STEP 2 | HARD 239, LIFT 20 | 0 | - | [~] |
| Viale Filippo Reina | 0.12 | 100 % (2013-2022) | 5 | 7 | unknown 2 | - | 48 % | HARD 17 | 0 | 0 | - | [x] |

## Alto Malcantone

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 4 m) | 0.31 | 59 % (2013-2022) | 7 | 3 | stone 2, unknown 3 | - | 28 % | HARD 833, LIFT 61, STEP 6, TWIST 28 | HARD 835, LIFT 53, STEP 6, TWIST 34 | 0 | - | [x] |
| Bárca | 0.14 | 100 % (2013) | 7 | 8 | unknown 3 | - | 50 % | 0 | HARD 17 | 0 | - | [x] |
| Canavée | 0.24 | 100 % (2013) | 10 | 19 | unknown 1 | - | 49 % | 0 | HARD 68 | 0 | - | [x] |
| Cámpa | 0.22 | 100 % (2013-2022) | 9 | 10 | plaster 2, stone 1, unknown 2 | - | 44 % | 0 | 0 | 0 | - | [x] |
| Focón | 0.12 | 100 % (2013-2022) | 5 | 6 | stone 2 | - | 27 % | 0 | HARD 5, LIFT 1 | 0 | - | [x] |
| Lücc | 0.21 | 8 % (2022) | 1 | 1 | stone 1, unknown 1 | - | 7 % | 0 | HARD 2 | 0 | - | [~] |
| Roanéra | 0.30 | 100 % (2013) | 13 | 12 | concrete 1, unknown 2 | - | 41 % | 0 | 0 | 0 | - | [x] |
| Scernéscia | 0.15 | 13 % (2022) | 1 | 0 | - | - | 6 % | 0 | HARD 8 | 0 | - | [~] |
| Sgambáda | 0.14 | 100 % (2013-2022) | 6 | 8 | plaster 2, unknown 1 | - | 29 % | 0 | 0 | 0 | - | [x] |
| Stradón da Brén | 0.16 | 100 % (2022) | 7 | 7 | stone 3, unknown 5 | - | 47 % | HARD 796, LIFT 19, STEP 1 | HARD 801, LIFT 21 | 0 | - | [x] |
| Stradón da Rós | 3.06 | 100 % (2013-2022) | 94 | 35 | plaster 2, stone 4, unknown 10 | 591 m | 39 % | 0 | HARD 5534, LIFT 247, TWIST 8 | 8 | guardrail visto nella foto e assente nella prima costruzione (tornante); guardrail visto nella foto e assente nella prima costruzione; guardrail dalle panoramiche segmentate del corridoio (sv_guardrails.py) nella costruzione finale; guardrail dalle panoramiche segmentate del corridoio (sv_guardrails.py) nella costruzione finale | [x] |
| Stráda Végia da Brén | 0.29 | 100 % (2013-2022) | 14 | 18 | stone 2, unknown 3 | - | 46 % | HARD 627, LIFT 121, STEP 11, TWIST 160 | HARD 472, LIFT 114, TWIST 132 | 1 | - | [x] |
| Stráda Végia da Rós | 0.11 | 100 % (2013-2014) | 5 | 13 | stone 4, unknown 2 | - | 44 % | 0 | HARD 334, LIFT 22, TWIST 9 | 1 | - | [x] |
| Tavarón | 0.42 | 100 % (2013) | 14 | 1 | - | - | 36 % | HARD 209, LIFT 9 | HARD 146, LIFT 4 | 0 | - | [x] |
| Via Ponte di Vello | 1.93 | 100 % (2013-2022) | 65 | 3 | stone 11, unknown 11 | 170 m | 38 % | HARD 1841, LIFT 136, STEP 3, TWIST 66 | HARD 1579, LIFT 44, STEP 2 | 0 | - | [x] |
| Via alla Chiesa di San Michele | 0.30 | 100 % (2013-2014) | 13 | 26 | plaster 1, stone 5, unknown 8 | - | 44 % | 0 | HARD 1503, LIFT 107, STEP 4, TWIST 93 | 2 | - | [x] |

## Aranno

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 1.52 | 5 % (2014) | 4 | 1 | unknown 2 | - | 2 % | HARD 535, LIFT 58, STEP 17, TWIST 43 | HARD 351, LIFT 17, STEP 2, TWIST 4 | 0 | - | [!] |
| (senza nome: strada 4 m) | 0.01 | 100 % (2014) | 3 | 7 | unknown 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Ai Pianèll | 0.52 | 100 % (2013-2014) | 20 | 6 | unknown 5 | - | 45 % | HARD 197, LIFT 29, STEP 1, TWIST 13 | HARD 87 | 0 | - | [x] |
| Ar Paiaröö | 0.26 | 0 %  | 0 | 1 | - | - | 0 % | HARD 25 | HARD 8 | 0 | - | [!] |
| Ara Zòta | 0.51 | 11 % (2014) | 2 | 3 | unknown 2 | - | 5 % | HARD 322, LIFT 22, STEP 4, TWIST 3 | HARD 178 | 0 | - | [~] |
| In Campágna | 0.67 | 100 % (2014) | 24 | 32 | concrete 2, unknown 5 | 12 m | 50 % | HARD 48, LIFT 2, STEP 2 | HARD 13 | 0 | - | [x] |
| In Pasquée | 0.08 | 0 %  | 0 | 8 | unknown 4 | - | 4 % | HARD 65, LIFT 7, STEP 2, TWIST 2 | HARD 5 | 0 | - | [!] |
| Ra Stráda da Brén | 1.22 | 100 % (2013-2014) | 45 | 3 | stone 1, unknown 2 | 14 m | 27 % | HARD 1490, LIFT 43 | HARD 1224, LIFT 18 | 0 | - | [x] |
| Ra Stráda dra Ca di Biss | 0.17 | 100 % (2014) | 7 | 12 | unknown 8 | - | 49 % | HARD 245 | HARD 262, LIFT 9 | 1 | facciata verso strada senza aperture (casa su pendio con garage sotto), tono troppo scuro; facciate per casa, piani dal fronte strada, toni e persiane rivisti (facades.py, buildings_mesh.py) | [x] |
| Ur Stradón | 2.86 | 100 % (2014) | 112 | 42 | stone 3, unknown 28 | 104 m | 41 % | HARD 1718, LIFT 114, STEP 10, TWIST 165 | HARD 1525, LIFT 67, STEP 1 | 1 | classe concrete sbagliata (nella foto è pietra o intonaco); classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |

## Bioggio

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: raccordo) | 0.01 | 100 % (2014) | 1 | 3 | - | - | 50 % | HARD 4 | 0 | 1 | piani superiori senza finestre: le gronde del fronte prese dall'ala bassa a filo della casa; gronde dalla parte in piano più alta del muro (facades.py): tre piani con finestre e persiane | [x] |
| (senza nome: strada 3 m) | 2.20 | 35 % (2013-2022) | 43 | 85 | concrete 2, plaster 1, stone 7, unknown 7 | - | 20 % | HARD 1724, LIFT 219, STEP 55, TWIST 225 | HARD 1514, LIFT 156, STEP 42, TWIST 206 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.62 | 21 % (2013-2022) | 11 | 17 | concrete 1, unknown 2 | - | 14 % | HARD 64, LIFT 8 | HARD 10 | 0 | - | [~] |
| (senza nome: strada 6 m) | 0.07 | 79 % (2022) | 3 | 1 | - | - | 40 % | HARD 338, LIFT 4 | HARD 160 | 0 | - | [x] |
| Alla Chiesa | 0.15 | 24 % (2013-2014) | 1 | 7 | - | - | 8 % | HARD 230, LIFT 48, STEP 4, TWIST 38 | HARD 185, LIFT 23, TWIST 12 | 0 | - | [~] |
| Belvedere | 0.19 | 89 % (2013-2014) | 7 | 11 | concrete 3, plaster 1, stone 1, unknown 5 | - | 47 % | HARD 250, LIFT 49, STEP 4, TWIST 48 | HARD 104 | 0 | - | [x] |
| Case Lucchina | 0.15 | 100 % (2013) | 7 | 7 | - | - | 19 % | HARD 94, LIFT 4, STEP 4, TWIST 25 | HARD 28 | 0 | - | [x] |
| Contrada Böiro | 0.10 | 0 %  | 0 | 6 | - | - | 0 % | HARD 15 | 0 | 0 | - | [!] |
| Contrada Municipio | 0.14 | 100 % (2013-2014) | 7 | 9 | stone 2, unknown 2 | - | 41 % | HARD 187, LIFT 25, STEP 6 | HARD 95 | 0 | - | [x] |
| Contrada dei Terrieri | 0.03 | 53 % (2013) | 1 | 5 | stone 1, unknown 2 | - | 20 % | HARD 137, LIFT 28, TWIST 40 | HARD 51 | 0 | - | [x] |
| Contrada del Torchio | 0.15 | 19 % (2014-2022) | 3 | 11 | - | - | 9 % | HARD 19, LIFT 4, STEP 2 | HARD 1 | 0 | - | [~] |
| Salita Bassengo | 0.03 | 100 % (2014) | 2 | 1 | - | - | 50 % | HARD 20 | HARD 8, STEP 2 | 0 | - | [x] |
| Salita Cuccarello | 0.10 | 19 % (2014) | 1 | 2 | - | - | 13 % | HARD 87, LIFT 4 | HARD 9 | 0 | - | [~] |
| Salita San Rocco | 0.10 | 14 % (2013) | 0 | 2 | stone 1 | - | 2 % | HARD 114 | HARD 188 | 0 | - | [~] |
| Salita Sant'Ilario | 0.15 | 100 % (2013) | 5 | 6 | stone 1, unknown 1 | - | 50 % | HARD 34 | HARD 158, LIFT 16, STEP 6, TWIST 8 | 0 | - | [x] |
| Sotto Carà | 0.16 | 21 % (2014) | 2 | 8 | plaster 2, stone 1 | - | 9 % | HARD 101, LIFT 1, STEP 4, TWIST 8 | HARD 23 | 0 | - | [~] |
| Strada Regina | 1.47 | 86 % (2013-2022) | 49 | 29 | concrete 2, plaster 1, stone 2, unknown 3 | - | 42 % | HARD 2630, LIFT 207, STEP 4, TWIST 31 | HARD 2065, LIFT 20 | 1 | mattoni faccia a vista e negozio al piano terra, nella mappa intonaco e tapparelle; vetrine dove OSM registra un negozio; il paramento in mattoni non è nei dati | [x] |
| Via Bassengo | 0.10 | 100 % (2013-2014) | 3 | 4 | stone 1, unknown 1 | - | 40 % | HARD 604, LIFT 56, STEP 6, TWIST 5 | HARD 558, LIFT 46, STEP 5, TWIST 5 | 0 | - | [x] |
| Via Cademario | 5.04 | 100 % (2013-2022) | 177 | 87 | concrete 1, plaster 4, stone 32, unknown 27 | 616 m | 45 % | HARD 8429, LIFT 525, STEP 20, TWIST 125 | HARD 7164, LIFT 302, STEP 19, TWIST 71 | 0 | - | [x] |
| Via Cantonale | 1.58 | 100 % (2014) | 61 | 16 | stone 1, unknown 5 | 28 m | 37 % | HARD 271, LIFT 15 | HARD 334, LIFT 41 | 0 | - | [x] |
| Via Cimo | 1.29 | 100 % (2013) | 52 | 50 | concrete 2, stone 6, unknown 26 | 296 m | 49 % | HARD 948, LIFT 166, STEP 13, TWIST 78 | HARD 799, LIFT 10, STEP 3, TWIST 2 | 4 | guardrail nella foto, assente nella mappa; guardrail di 18 m visto nelle panoramiche (voti 10/10); guardrail di tutta la rete dalle panoramiche (sv_guardrails.py); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Ciossetto | 0.18 | 100 % (2013-2014) | 5 | 9 | unknown 1 | - | 44 % | HARD 47, LIFT 10, STEP 4 | HARD 11 | 0 | - | [x] |
| Via Gaggio | 2.00 | 100 % (2013) | 66 | 20 | stone 1, unknown 6 | 527 m | 42 % | HARD 2960, LIFT 304, STEP 15, TWIST 135 | HARD 2681, LIFT 108, TWIST 23 | 1 | guardrail di 38 m visto nelle panoramiche (voti 28/28); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Industria | 0.35 | 100 % (2013-2022) | 13 | 6 | - | - | 50 % | HARD 300, LIFT 24, STEP 8 | HARD 227, LIFT 24, STEP 8 | 0 | - | [x] |
| Via Longa | 0.17 | 10 % (2018-2022) | 1 | 3 | concrete 1 | - | 7 % | HARD 37, STEP 4 | 0 | 0 | - | [~] |
| Via Lugano | 0.18 | 100 % (2013-2022) | 10 | 2 | - | 138 m | 50 % | HARD 174 | HARD 86 | 0 | - | [x] |
| Via Masmedo | 0.07 | 100 % (2013-2014) | 4 | 3 | unknown 1 | - | 41 % | HARD 120, LIFT 4 | HARD 14 | 0 | - | [x] |
| Via Mondonico | 0.62 | 100 % (2013) | 22 | 12 | plaster 1, stone 1, unknown 4 | 56 m | 39 % | HARD 662, HOLE 5, LIFT 59, STEP 8, TWIST 24 | HARD 495, HOLE 5, LIFT 41, STEP 5, TWIST 24 | 0 | - | [x] |
| Via Nuova Bioggio | 0.38 | 60 % (2013-2018) | 8 | 19 | stone 1 | - | 29 % | HARD 121, LIFT 17, STEP 3 | HARD 52 | 0 | - | [x] |
| Via Pianaccio | 0.15 | 100 % (2013-2014) | 7 | 8 | plaster 1, stone 2, unknown 2 | - | 47 % | HARD 94, STEP 4 | HARD 22 | 0 | - | [x] |
| Via Pradello | 0.14 | 91 % (2022) | 5 | 10 | - | - | 50 % | HARD 164, LIFT 9, STEP 1, TWIST 5 | HARD 108, LIFT 1 | 0 | - | [x] |
| Via Renera | 0.36 | 100 % (2013) | 15 | 1 | stone 2, unknown 1 | - | 37 % | HARD 10 | 0 | 0 | - | [x] |
| Via Righetto | 0.67 | 83 % (2013) | 21 | 7 | stone 1, unknown 1 | - | 31 % | HARD 504, LIFT 77, STEP 4, TWIST 16 | HARD 266, LIFT 2 | 0 | - | [x] |
| Via S. Maurizio | 0.30 | 43 % (2014) | 6 | 13 | stone 1, unknown 2 | - | 23 % | HARD 204, LIFT 27, STEP 2, TWIST 4 | HARD 232, LIFT 22, STEP 8, TWIST 40 | 0 | - | [~] |
| Via Santa Maria | 0.51 | 100 % (2013-2014) | 20 | 7 | stone 1 | - | 28 % | HARD 118, LIFT 15, STEP 4 | HARD 42 | 0 | - | [x] |
| Via Serta | 0.19 | 81 % (2018) | 7 | 11 | concrete 1 | - | 42 % | HARD 140, LIFT 24, STEP 6, TWIST 20 | HARD 20 | 0 | - | [x] |
| Via Stazione | 0.17 | 0 %  | 0 | 3 | - | - | 1 % | HARD 487, LIFT 2 | HARD 407 | 0 | - | [!] |
| Via Strecce | 0.10 | 100 % (2013-2022) | 4 | 0 | - | - | 48 % | HARD 106, LIFT 10, STEP 2 | HARD 20, LIFT 1 | 0 | - | [x] |
| Via Valle Maggiore | 0.37 | 30 % (2013) | 4 | 9 | unknown 1 | - | 17 % | HARD 960, LIFT 68, STEP 4 | HARD 837, LIFT 16 | 0 | - | [~] |
| Via al Chioso | 0.30 | 86 % (2013-2014) | 9 | 18 | unknown 2 | - | 43 % | HARD 450, LIFT 19, STEP 5 | HARD 386, LIFT 5 | 0 | - | [x] |
| Via alla Fabbrica | 0.21 | 100 % (2013-2018) | 9 | 5 | stone 1 | - | 49 % | HARD 173, LIFT 3, STEP 2 | HARD 117 | 0 | - | [x] |
| Via della Posta | 0.43 | 100 % (2014-2022) | 18 | 16 | concrete 1, stone 1 | - | 50 % | HARD 506, LIFT 8 | HARD 326 | 1 | portici al piano terra non modellati (vetrine al loro posto) | [x] |
| Via la Barca | 0.25 | 96 % (2013-2014) | 9 | 11 | stone 1, unknown 1 | - | 45 % | HARD 250, LIFT 1, STEP 2 | HARD 168, LIFT 19, STEP 5, TWIST 10 | 0 | - | [x] |
| Via sotto il monte | 0.04 | 65 % (2022) | 1 | 2 | - | - | 25 % | HARD 12, LIFT 6 | 0 | 0 | - | [x] |
| a Camp Urlásc | 0.15 | 32 % (2013) | 3 | 4 | unknown 2 | - | 16 % | HARD 195, LIFT 12, STEP 2 | HARD 162, LIFT 9, STEP 3, TWIST 7 | 0 | - | [~] |
| a Prelónch | 0.19 | 99 % (2013) | 7 | 8 | unknown 2 | - | 46 % | HARD 42 | HARD 40 | 0 | - | [x] |
| i Cánvi | 0.02 | 62 % (2014) | 1 | 1 | - | - | 50 % | HARD 133, LIFT 78, STEP 4, TWIST 28 | HARD 82, LIFT 6, TWIST 9 | 0 | - | [x] |
| i Pré Lunc | 0.26 | 100 % (2013) | 12 | 9 | concrete 4, unknown 2 | - | 48 % | HARD 99, LIFT 4 | HARD 61 | 0 | - | [x] |
| in Recèss | 0.16 | 100 % (2013-2014) | 6 | 9 | stone 1 | 22 m | 49 % | HARD 59, LIFT 10, STEP 4 | HARD 72, LIFT 2 | 0 | - | [x] |
| ra Ca da Brèn | 0.14 | 38 % (2013-2014) | 2 | 2 | unknown 5 | - | 9 % | HARD 34 | HARD 17 | 1 | tono rosso scuro come nella foto; il portico ad archi non è ricostruito | [~] |
| ra Piázza di Fughítt | 0.08 | 100 % (2014) | 4 | 5 | unknown 4 | - | 50 % | HARD 48, LIFT 4, STEP 3 | HARD 7 | 0 | - | [x] |

## Cadegliano-Viconago

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 4 m) | 0.86 | 100 % (2023-2025) | 35 | 0 | - | 100 m | 43 % | 0 | 0 | 0 | - | [x] |

## Cademario

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 0.74 | 33 % (2013-2014) | 12 | 29 | concrete 2, stone 6, unknown 5 | - | 15 % | HARD 1034, LIFT 70, STEP 13, TWIST 27 | HARD 853, LIFT 55, STEP 5, TWIST 31 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.40 | 33 % (2013-2014) | 7 | 13 | stone 3, unknown 2 | - | 19 % | HARD 431, LIFT 40, STEP 2, TWIST 9 | HARD 330, LIFT 29, STEP 8, TWIST 14 | 0 | - | [~] |
| Stráda de Prévat | 0.23 | 5 % (2013) | 0 | 2 | unknown 1 | - | 1 % | HARD 3 | 0 | 0 | - | [~] |
| Stráda di Cará | 0.77 | 99 % (2013) | 28 | 30 | stone 6, unknown 13 | - | 39 % | HARD 442, LIFT 54, STEP 6, TWIST 28 | HARD 345, LIFT 6, STEP 2, TWIST 24 | 3 | vista a 2 m, solo intonaco | [x] |
| Strécia Giovannino Guareschi | 0.05 | 54 % (2013) | 2 | 5 | - | - | 18 % | HARD 218, LIFT 14, STEP 1 | HARD 250, LIFT 14 | 0 | - | [x] |
| Via Agra | 0.12 | 69 % (2013) | 3 | 4 | stone 1 | - | 30 % | HARD 51, STEP 4 | HARD 24 | 0 | - | [x] |
| Via Belsito | 0.88 | 100 % (2013-2014) | 30 | 13 | stone 3, unknown 5 | 86 m | 45 % | HARD 1017, LIFT 52, STEP 5, TWIST 2 | HARD 878, LIFT 47, STEP 1, TWIST 2 | 0 | - | [x] |
| Via Cantonale | 2.50 | 86 % (2013-2014) | 79 | 61 | concrete 4, stone 14, unknown 22 | 259 m | 40 % | HARD 3404, LIFT 101, STEP 8, TWIST 109 | HARD 2760, LIFT 54, STEP 10, TWIST 86 | 2 | guardrail di 32 m visto nelle panoramiche (voti 25/25); guardrail di 42 m visto nelle panoramiche (voti 36/38); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato; guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Cetta | 0.43 | 91 % (2013-2014) | 15 | 11 | stone 1, unknown 4 | - | 41 % | HARD 422, LIFT 34, STEP 5, TWIST 7 | HARD 292, LIFT 2, STEP 3 | 0 | - | [x] |
| Via Fontana | 0.34 | 100 % (2013) | 11 | 6 | stone 3, unknown 2 | - | 44 % | HARD 310, LIFT 13, STEP 3, TWIST 32 | HARD 159, LIFT 1 | 0 | - | [x] |
| Via Kurhaus | 0.36 | 71 % (2013-2014) | 10 | 15 | stone 1, unknown 1 | - | 28 % | HARD 447, LIFT 46, STEP 3, TWIST 3 | HARD 155 | 0 | - | [x] |
| Via Lücc | 0.32 | 70 % (2013-2014) | 9 | 11 | concrete 4, stone 1 | - | 36 % | HARD 139, LIFT 12, STEP 4, TWIST 23 | HARD 44 | 0 | - | [x] |
| Via Quadrella | 0.38 | 100 % (2013-2014) | 14 | 29 | concrete 3, stone 1, unknown 9 | - | 48 % | HARD 236, LIFT 24, STEP 8, TWIST 23 | HARD 140, LIFT 2 | 0 | - | [x] |
| Via Sant'Ambrogio | 0.70 | 100 % (2013-2014) | 26 | 6 | stone 7, unknown 2 | 12 m | 47 % | HARD 145, LIFT 15, STEP 2 | HARD 132, LIFT 6 | 0 | - | [x] |
| Via al Monastero | 0.28 | 100 % (2013) | 12 | 4 | concrete 1 | - | 41 % | HARD 12 | HARD 4 | 0 | - | [x] |
| Via dei Campi | 0.13 | 100 % (2013-2014) | 6 | 6 | stone 2, unknown 3 | - | 49 % | HARD 8 | HARD 2 | 0 | - | [x] |
| Via dei Ronchi | 1.95 | 100 % (2013-2014) | 66 | 36 | concrete 2, stone 5, unknown 20 | 16 m | 43 % | HARD 1830, LIFT 161, STEP 19, TWIST 84 | HARD 1440, LIFT 74, STEP 2, TWIST 31 | 1 | muro in concrete come nella foto; materiale del muro dalle panoramiche | [x] |
| ai Camp dra Pórta | 0.31 | 100 % (2013) | 13 | 16 | stone 3, unknown 7 | - | 50 % | HARD 85, LIFT 8, STEP 2 | HARD 95 | 0 | - | [x] |
| ai Mirísg | 0.26 | 0 %  | 0 | 1 | - | - | 0 % | HARD 12 | 0 | 0 | - | [!] |
| ar Campanín | 0.05 | 43 % (2013) | 1 | 6 | stone 1, unknown 1 | - | 9 % | HARD 86, LIFT 10, STEP 3 | HARD 76 | 0 | - | [~] |

## Caslano

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: piazza) | 0.12 | 63 % (2013) | 5 | 3 | stone 1 | - | 45 % | 0 | 0 | 0 | - | [x] |
| (senza nome: strada 3 m) | 1.18 | 24 % (2013-2022) | 18 | 64 | concrete 1, stone 1, unknown 6 | - | 16 % | HARD 14 | HARD 9 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.36 | 50 % (2013-2022) | 11 | 21 | stone 2, unknown 1 | - | 28 % | 0 | 0 | 0 | - | [x] |
| Contrada San Rocco | 0.11 | 81 % (2013) | 4 | 3 | - | - | 20 % | 0 | 0 | 0 | - | [x] |
| Contrada al Lago | 0.15 | 100 % (2013) | 6 | 10 | unknown 1 | - | 20 % | 0 | 0 | 0 | - | [x] |
| Contrada dei Fiori | 0.08 | 40 % (2013) | 2 | 7 | - | - | 9 % | 0 | 0 | 0 | - | [~] |
| Piazza Lago | 0.14 | 100 % (2013) | 7 | 6 | unknown 1 | - | 49 % | 0 | HARD 79 | 0 | - | [x] |
| Strada Cantonale | 0.03 | 100 % (2014-2022) | 3 | 3 | - | - | 50 % | HARD 183, LIFT 8 | HARD 183, LIFT 8 | 0 | - | [x] |
| Strada Regina | 0.13 | 100 % (2013-2022) | 6 | 12 | - | - | 43 % | 0 | 0 | 0 | - | [x] |
| Via Baragia | 0.12 | 100 % (2013-2022) | 6 | 6 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Campagna | 0.11 | 78 % (2013) | 3 | 3 | stone 1 | - | 39 % | 0 | HARD 15 | 0 | - | [x] |
| Via Camparlungo | 0.09 | 100 % (2013-2022) | 5 | 4 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Cantonale | 0.54 | 100 % (2013-2022) | 18 | 26 | plaster 1, stone 4, unknown 3 | 16 m | 48 % | HARD 1079, LIFT 76, STEP 9, TWIST 7 | HARD 1069, LIFT 76, STEP 9, TWIST 7 | 1 | rotonda | [x] |
| Via Cantonetti | 0.32 | 100 % (2013) | 12 | 14 | stone 2, unknown 1 | - | 48 % | 0 | HARD 18 | 1 | piazzale su due livelli reso come rampa accanto alla strada | [x] |
| Via Chiesa | 0.13 | 100 % (2013-2022) | 7 | 12 | stone 1, unknown 3 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chiesuola | 0.13 | 100 % (2013-2022) | 5 | 10 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chioso | 0.10 | 100 % (2013) | 4 | 9 | stone 1, unknown 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chiossetti | 0.06 | 100 % (2013-2022) | 3 | 7 | stone 1, unknown 3 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Colombera | 1.28 | 100 % (2014-2022) | 47 | 42 | plaster 3, stone 17, unknown 13 | 115 m | 50 % | HARD 41 | HARD 127 | 5 | incrocio con strisce e zebrature dall'ortofoto; guardrail visto nella foto e assente nella prima costruzione (tra strada e ferrovia); guardrail dalle panoramiche segmentate del corridoio (sv_guardrails.py) nella costruzione finale | [x] |
| Via Credera | 0.35 | 65 % (2013-2022) | 8 | 7 | unknown 1 | - | 34 % | 0 | HARD 94 | 1 | - | [x] |
| Via Fiume | 0.13 | 12 % (2013) | 1 | 4 | - | - | 1 % | 0 | 0 | 0 | - | [~] |
| Via Glorietta | 0.12 | 14 % (2022) | 1 | 9 | stone 2 | - | 12 % | 0 | 0 | 0 | - | [~] |
| Via Golf | 0.16 | 100 % (2013-2022) | 8 | 11 | concrete 1 | - | 50 % | HARD 156 | HARD 152 | 0 | - | [x] |
| Via Industria | 0.13 | 100 % (2018-2022) | 6 | 11 | - | - | 50 % | 0 | HARD 147, LIFT 4 | 0 | - | [x] |
| Via Martelli | 0.10 | 100 % (2013-2022) | 5 | 7 | concrete 2, unknown 2 | - | 50 % | 0 | HARD 4 | 0 | - | [x] |
| Via Mera | 0.11 | 100 % (2013-2022) | 6 | 10 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Mimosa | 0.13 | 100 % (2013-2022) | 6 | 13 | stone 4, unknown 6 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Muraccio | 0.19 | 100 % (2013) | 8 | 10 | stone 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Nosetto | 0.09 | 100 % (2013-2022) | 4 | 9 | - | - | 50 % | 0 | HARD 5 | 0 | - | [x] |
| Via Pasquee | 0.09 | 100 % (2013) | 3 | 8 | stone 1 | - | 29 % | 0 | 0 | 1 | piazzale della misurazione ufficiale su due livelli (salto di 2 m) reso come rampa di 30 gradi accanto alla via acciottolata | [x] |
| Via Prati | 0.08 | 100 % (2013-2022) | 6 | 7 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Riale | 0.06 | 61 % (2013) | 2 | 5 | stone 1, unknown 3 | - | 21 % | 0 | HARD 127, LIFT 32, TWIST 21 | 0 | - | [x] |
| Via Rompada | 0.10 | 100 % (2018-2022) | 4 | 7 | stone 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Rossée | 0.30 | 100 % (2013-2022) | 14 | 6 | stone 1, unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via San Michele | 0.26 | 100 % (2013-2022) | 12 | 5 | stone 1 | - | 45 % | 0 | HARD 131, LIFT 2 | 0 | - | [x] |
| Via Stazione | 0.87 | 100 % (2013-2022) | 31 | 45 | stone 5, unknown 8 | - | 50 % | 0 | HARD 3 | 1 | - | [x] |
| Via Stremadone | 0.07 | 100 % (2013) | 5 | 4 | stone 1, unknown 5 | - | 31 % | 0 | HARD 22 | 0 | - | [x] |
| Via Torrazza | 1.15 | 100 % (2013) | 46 | 19 | concrete 1, stone 3, unknown 3 | - | 42 % | 0 | HARD 203, LIFT 12, STEP 5, TWIST 3 | 0 | - | [x] |
| Via Valle | 0.45 | 100 % (2013) | 15 | 21 | stone 3, unknown 6 | - | 46 % | 0 | 0 | 0 | - | [x] |

## Cremenaga

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 0.22 | 3 % (2025) | 1 | 0 | - | - | 4 % | 0 | 0 | 0 | - | [!] |
| (senza nome: strada 4 m) | 0.02 | 0 %  | 0 | 0 | - | - | 0 % | 0 | 0 | 0 | - | [!] |

## Gravesano

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 1.02 | 33 % (2013-2022) | 14 | 65 | stone 3, unknown 12 | - | 15 % | HARD 1227, LIFT 106, STEP 27, TWIST 65 | HARD 807, LIFT 31, STEP 7, TWIST 32 | 1 | - | [~] |
| (senza nome: strada 4 m) | 0.15 | 22 % (2013-2022) | 3 | 14 | unknown 3 | - | 8 % | HARD 50, LIFT 1 | HARD 42 | 0 | - | [~] |
| (senza nome: strada 6 m) | 0.04 | 37 % (2022) | 1 | 0 | unknown 1 | - | 34 % | 0 | 0 | 0 | - | [~] |
| Salita al Mattero | 0.30 | 48 % (2013-2022) | 6 | 6 | stone 3, unknown 1 | 18 m | 25 % | HARD 205, LIFT 5 | HARD 151, LIFT 3 | 0 | - | [~] |
| Via Campo Nuovo | 0.13 | 100 % (2013-2022) | 6 | 20 | stone 1, unknown 4 | - | 50 % | HARD 52, LIFT 8, STEP 2 | 0 | 0 | - | [x] |
| Via Cantonale | 0.55 | 55 % (2022) | 11 | 21 | stone 2, unknown 4 | - | 28 % | HARD 2269, LIFT 159, STEP 13, TWIST 51 | HARD 1696, LIFT 48 | 0 | - | [x] |
| Via Cappelletta | 0.15 | 0 %  | 0 | 3 | unknown 1 | - | 0 % | HARD 64, LIFT 7, STEP 2 | HARD 35 | 0 | - | [!] |
| Via Curtora | 0.20 | 100 % (2013-2022) | 7 | 13 | plaster 1, stone 1, unknown 1 | - | 43 % | HARD 289, LIFT 61, STEP 7, TWIST 47 | HARD 99 | 0 | - | [x] |
| Via Danas | 0.05 | 100 % (2022) | 3 | 0 | - | - | 50 % | HARD 257, LIFT 6 | HARD 169 | 0 | - | [x] |
| Via Dragoni | 0.25 | 82 % (2013-2022) | 7 | 15 | stone 1, unknown 4 | - | 44 % | HARD 185, LIFT 25, STEP 2 | HARD 78 | 0 | - | [x] |
| Via Grumo | 0.64 | 57 % (2014-2022) | 13 | 15 | stone 2, unknown 4 | 81 m | 31 % | HARD 1102, LIFT 28 | HARD 740, LIFT 13 | 0 | - | [x] |
| Via Istituto Rusca | 0.22 | 100 % (2013-2022) | 9 | 24 | concrete 1, unknown 4 | - | 50 % | HARD 911, LIFT 89, STEP 14, TWIST 37 | HARD 660, LIFT 8 | 0 | - | [x] |
| Via Mezzene | 0.09 | 100 % (2013-2022) | 5 | 6 | unknown 3 | - | 50 % | HARD 1 | 0 | 0 | - | [x] |
| Via Mondadiscio | 0.08 | 100 % (2014-2022) | 4 | 5 | unknown 2 | - | 50 % | HARD 321, LIFT 39, STEP 8, TWIST 2 | HARD 214 | 0 | - | [x] |
| Via Nobreta | 0.09 | 63 % (2022) | 2 | 4 | - | - | 31 % | HARD 104 | HARD 67 | 0 | - | [x] |
| Via Penodra | 0.41 | 81 % (2013-2022) | 11 | 19 | stone 6, unknown 3 | - | 42 % | HARD 2778, LIFT 327, STEP 1, TWIST 17 | HARD 2669, LIFT 237, STEP 1, TWIST 2 | 1 | - | [x] |
| Via Pracurta | 0.22 | 100 % (2022) | 9 | 13 | plaster 1, unknown 3 | - | 50 % | HARD 167 | HARD 119 | 0 | - | [x] |
| Via Prada | 0.34 | 82 % (2013-2022) | 12 | 29 | unknown 7 | - | 40 % | HARD 75, LIFT 9, STEP 6 | HARD 10 | 0 | - | [x] |
| Via San Pietro | 0.18 | 100 % (2022) | 9 | 9 | stone 1, unknown 2 | - | 50 % | HARD 200, LIFT 69, STEP 2, TWIST 40 | HARD 197, LIFT 68, STEP 2, TWIST 58 | 0 | - | [x] |
| Via Strada Regina | 0.66 | 73 % (2013-2022) | 18 | 32 | plaster 1, stone 3, unknown 10 | - | 35 % | HARD 2537, LIFT 196, STEP 8, TWIST 175 | HARD 1674, LIFT 58, STEP 11, TWIST 36 | 3 | intonaco chiaro e persiane verdi come nella foto; poche finestre; facciate per casa, piani dal fronte strada, toni e persiane rivisti (facades.py, buildings_mesh.py) | [x] |
| Via Vallone | 0.33 | 99 % (2013-2014) | 12 | 25 | stone 4, unknown 6 | - | 48 % | HARD 972, LIFT 83, STEP 5, TWIST 40 | HARD 920, LIFT 8 | 0 | - | [x] |
| Via Vignascia | 0.25 | 100 % (2013-2022) | 8 | 20 | stone 2, unknown 7 | - | 50 % | HARD 926, LIFT 15, STEP 4 | HARD 830, LIFT 3 | 0 | - | [x] |
| Via al Chioso | 0.13 | 19 % (2022) | 1 | 7 | unknown 5 | - | 13 % | HARD 246, LIFT 14 | HARD 204 | 0 | - | [~] |
| Vicolo Gesora | 0.04 | 100 % (2013) | 2 | 9 | unknown 1 | - | 25 % | HARD 80, LIFT 13, STEP 1, TWIST 4 | HARD 43, LIFT 8 | 0 | - | [x] |

## Lamone

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: autostrada) | 0.28 | 100 % (2022) | 8 | 0 | - | 74 m | 49 % | HARD 13, LIFT 2 | HARD 13, LIFT 2 | 0 | - | [x] |
| (senza nome: strada 3 m) | 0.15 | 100 % (2013-2022) | 8 | 1 | plaster 1, unknown 3 | - | 50 % | 0 | 0 | 0 | - | [x] |
| (senza nome: strada 4 m) | 0.11 | 47 % (2022) | 1 | 1 | - | - | 18 % | 0 | 0 | 0 | - | [~] |
| Via Pré d'là | 0.19 | 100 % (2013-2022) | 9 | 1 | plaster 1, unknown 3 | - | 47 % | HARD 10 | HARD 12 | 0 | - | [x] |
| Via alla Resega | 0.11 | 100 % (2022) | 4 | 5 | - | - | 50 % | 0 | 0 | 0 | - | [x] |

## Lavena Ponte Tresa

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 10 m) | 0.05 | 33 % (2025) | 1 | 0 | - | - | 0 % | HARD 75 | HARD 75 | 0 | - | [~] |
| (senza nome: strada 3 m) | 0.03 | 0 %  | 0 | 1 | - | - | 0 % | HARD 7, LIFT 3 | HARD 7, LIFT 3 | 0 | - | [!] |
| (senza nome: strada 4 m) | 0.15 | 0 %  | 0 | 1 | - | - | 0 % | 0 | 0 | 0 | - | [!] |

## Lema

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 3.52 | 25 % (2013-2022) | 52 | 86 | concrete 1, plaster 1, stone 5, unknown 11 | - | 11 % | HARD 3153, LIFT 356, STEP 60, TWIST 182 | HARD 2074, LIFT 159, STEP 18, TWIST 157 | 1 | un blocco di muro in pietra dove la foto mostra una siepe | [~] |
| (senza nome: strada 4 m) | 1.81 | 76 % (2013-2022) | 59 | 56 | concrete 1, plaster 2, stone 24, unknown 23 | 144 m | 31 % | HARD 2020, LIFT 148, STEP 11, TWIST 54 | HARD 1454, LIFT 80, STEP 6 | 2 | classe stone sbagliata (nella foto è pietra o intonaco); classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |
| Moriscio | 0.32 | 100 % (2022) | 11 | 4 | stone 1 | 32 m | 43 % | HARD 150, LIFT 4, STEP 3, TWIST 8 | HARD 150, LIFT 4, STEP 3, TWIST 8 | 0 | - | [x] |
| Piazza San Rocco | 0.05 | 93 % (2014) | 2 | 2 | - | - | 5 % | HARD 346, LIFT 150, STEP 68, TWIST 169 | HARD 351, LIFT 152, STEP 68, TWIST 169 | 0 | - | [x] |
| Ra Müs'cia | 0.05 | 17 % (2013) | 1 | 6 | - | - | 0 % | HARD 95 | HARD 120 | 0 | - | [~] |
| Strada Cantonale | 1.91 | 100 % (2013-2022) | 65 | 56 | concrete 1, plaster 2, stone 29, unknown 15 | 420 m | 45 % | HARD 2044, LIFT 86, STEP 9, TWIST 31 | HARD 2058, LIFT 83, STEP 18, TWIST 61 | 2 | annesso-garage reso come rustico in pietra; casa principale più scura della foto; garage bassi senza registro con le porte; toni schiariti | [x] |
| Strada per Beride | 1.48 | 49 % (2013-2014) | 27 | 5 | stone 2 | - | 13 % | HARD 1611, LIFT 201, STEP 22, TWIST 171 | HARD 1104, LIFT 28 | 0 | - | [~] |
| Via Agostino de Marchi | 1.15 | 90 % (2013) | 42 | 11 | stone 5, unknown 2 | 308 m | 36 % | HARD 604, LIFT 23, TWIST 7 | HARD 562, LIFT 40, STEP 7, TWIST 37 | 1 | guardrail di 26 m visto nelle panoramiche (voti 24/24); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Alfredo Ryser | 0.08 | 0 %  | 0 | 0 | - | - | 0 % | 0 | 0 | 0 | - | [!] |
| Via Alice Meyer | 0.25 | 100 % (2013-2014) | 12 | 19 | stone 1, unknown 1 | - | 50 % | HARD 140, LIFT 8 | HARD 65 | 0 | - | [x] |
| Via Alpetti | 1.53 | 43 % (2013) | 24 | 19 | stone 3, unknown 3 | - | 16 % | HARD 520, LIFT 21 | HARD 241, LIFT 4 | 0 | - | [~] |
| Via Angelo Tamburini | 0.15 | 100 % (2013-2022) | 9 | 20 | stone 4 | - | 49 % | HARD 121, LIFT 20, STEP 4, TWIST 2 | HARD 24 | 4 | tono misurato bianco (foto recenti) contro giallo nella foto 2013; persiane azzurre invece di marroni; campanile in pietra a vista reso intonacato; persiane marroni misurate accettate quando chiare; le chiese restano intonacate: il materiale non è nei dati | [x] |
| Via Banghès | 0.44 | 89 % (2013) | 15 | 10 | - | - | 44 % | HARD 268, LIFT 24, STEP 2 | HARD 148, LIFT 3 | 0 | - | [x] |
| Via Barèla | 0.66 | 86 % (2013) | 23 | 1 | unknown 1 | - | 12 % | HARD 120, STEP 4 | HARD 5 | 0 | - | [x] |
| Via Bedéa | 0.14 | 100 % (2013-2022) | 7 | 8 | - | - | 50 % | HARD 5 | 0 | 0 | - | [x] |
| Via Bisada | 0.17 | 100 % (2013-2022) | 6 | 12 | unknown 1 | - | 49 % | HARD 67, STEP 2 | HARD 43, STEP 2 | 0 | - | [x] |
| Via Bressanèla | 0.24 | 100 % (2013) | 10 | 28 | unknown 2 | - | 47 % | HARD 13, LIFT 6 | 0 | 0 | - | [x] |
| Via Briv | 0.78 | 100 % (2013-2022) | 29 | 5 | stone 1 | - | 36 % | HARD 12 | HARD 12 | 0 | - | [x] |
| Via Camana | 0.39 | 0 %  | 0 | 5 | stone 1 | - | 0 % | HARD 154, LIFT 21, TWIST 1 | HARD 102, LIFT 5 | 0 | - | [!] |
| Via Campagna | 0.13 | 0 %  | 0 | 2 | - | - | 0 % | HARD 11 | 0 | 0 | - | [!] |
| Via Canavee | 0.05 | 31 % (2022) | 1 | 7 | stone 1, unknown 1 | - | 22 % | HARD 144, LIFT 15, STEP 4, TWIST 21 | HARD 76 | 0 | - | [~] |
| Via Cantonale | 1.84 | 100 % (2014-2022) | 66 | 29 | stone 12, unknown 9 | 411 m | 48 % | HARD 1668, LIFT 73, STEP 3, TWIST 21 | HARD 1005, LIFT 20 | 1 | guardrail di 30 m visto nelle panoramiche (voti 18/21); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Caradora | 0.28 | 100 % (2013-2022) | 12 | 16 | concrete 1, plaster 3, stone 6, unknown 4 | - | 40 % | HARD 69, LIFT 10, STEP 3 | HARD 28, LIFT 2 | 0 | - | [x] |
| Via Carbonscín | 0.23 | 100 % (2013) | 9 | 13 | stone 1 | - | 48 % | HARD 101, STEP 4, TWIST 7 | HARD 12 | 0 | - | [x] |
| Via Costa | 0.33 | 100 % (2013-2022) | 13 | 5 | unknown 1 | - | 47 % | HARD 39, LIFT 8, STEP 3 | HARD 7 | 0 | - | [x] |
| Via Cruséta | 0.30 | 100 % (2013-2014) | 11 | 18 | stone 4 | - | 50 % | HARD 295, LIFT 11 | HARD 15 | 0 | - | [x] |
| Via Crüisc | 0.19 | 94 % (2013) | 7 | 6 | - | - | 49 % | HARD 11 | HARD 11 | 0 | - | [x] |
| Via Domenico Trezzini | 0.12 | 100 % (2013) | 6 | 6 | concrete 1, plaster 1, stone 1, unknown 2 | - | 15 % | 0 | 0 | 0 | - | [x] |
| Via Dr. Erich Schwarz | 0.24 | 23 % (2013-2014) | 2 | 8 | unknown 2 | - | 8 % | HARD 57, LIFT 1 | HARD 73, LIFT 5, STEP 2 | 0 | - | [~] |
| Via Fausto Buzzi | 0.13 | 100 % (2013) | 5 | 12 | unknown 1 | - | 33 % | HARD 134, LIFT 6, STEP 1 | HARD 107, LIFT 8, STEP 8 | 0 | - | [x] |
| Via Favirolo | 0.45 | 100 % (2013-2022) | 18 | 21 | plaster 1, stone 6, unknown 13 | 69 m | 46 % | HARD 191, LIFT 13 | HARD 130 | 0 | - | [x] |
| Via Felice Gambazzi | 0.10 | 13 % (2022) | 2 | 1 | - | - | 11 % | HARD 15, LIFT 8, STEP 1 | 0 | 0 | - | [~] |
| Via Funtanín | 0.44 | 100 % (2013-2014) | 18 | 14 | concrete 1, stone 6, unknown 1 | 124 m | 46 % | HARD 212, LIFT 3, STEP 4 | HARD 340, LIFT 10 | 2 | muro in stone come nella foto; classe concrete sbagliata (nella foto è pietra o intonaco); materiale del muro dalle panoramiche; classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |
| Via Gerò | 0.35 | 100 % (2013) | 15 | 12 | unknown 1 | - | 49 % | HARD 116, LIFT 1 | HARD 82 | 0 | - | [x] |
| Via Giacomo Donati | 1.22 | 100 % (2013) | 49 | 19 | stone 3, unknown 6 | 323 m | 35 % | HARD 745, LIFT 117, STEP 1, TWIST 62 | HARD 513, LIFT 9, STEP 3 | 0 | - | [x] |
| Via Gána | 0.44 | 100 % (2013) | 17 | 9 | concrete 1 | - | 49 % | 0 | 0 | 0 | - | [x] |
| Via Lema | 0.38 | 100 % (2022) | 13 | 26 | unknown 1 | - | 50 % | HARD 1028, LIFT 50, TWIST 20 | HARD 735, LIFT 19 | 0 | - | [x] |
| Via Madrallo | 0.07 | 100 % (2014-2022) | 3 | 1 | unknown 2 | - | 49 % | HARD 31, LIFT 10, STEP 4 | 0 | 0 | - | [x] |
| Via Malcantón | 0.22 | 100 % (2013-2014) | 9 | 17 | stone 2, unknown 3 | - | 44 % | HARD 119, LIFT 12, STEP 2 | HARD 78 | 0 | - | [x] |
| Via Maria Boschetti-Alberti | 0.52 | 36 % (2013-2022) | 7 | 6 | stone 3, unknown 1 | 44 m | 20 % | HARD 533 | HARD 488 | 0 | - | [~] |
| Via Mavögn | 1.53 | 100 % (2022) | 54 | 12 | stone 18, unknown 1 | 396 m | 48 % | HARD 93, LIFT 13, TWIST 5 | HARD 65, LIFT 6, TWIST 6 | 0 | - | [x] |
| Via Meguldín | 0.50 | 100 % (2014) | 18 | 11 | stone 3, unknown 5 | 48 m | 44 % | HARD 293, LIFT 44, STEP 1, TWIST 3 | HARD 174, LIFT 17 | 0 | - | [x] |
| Via Minòra | 0.57 | 93 % (2013) | 18 | 5 | plaster 1, stone 1, unknown 1 | - | 29 % | HARD 332, LIFT 1 | HARD 311, LIFT 11 | 0 | - | [x] |
| Via Monte Lema | 0.63 | 100 % (2013-2022) | 21 | 27 | stone 1, unknown 6 | - | 48 % | HARD 385, LIFT 20 | HARD 319, LIFT 17 | 0 | - | [x] |
| Via Mora | 0.68 | 100 % (2013-2022) | 29 | 17 | stone 1, unknown 4 | 66 m | 49 % | HARD 616, LIFT 111, TWIST 64 | HARD 149, LIFT 1 | 0 | - | [x] |
| Via Mulino | 0.20 | 79 % (2013-2022) | 5 | 11 | stone 4, unknown 3 | 18 m | 37 % | HARD 250, LIFT 44, STEP 4, TWIST 54 | HARD 222, LIFT 27, STEP 2, TWIST 20 | 0 | - | [x] |
| Via Muntáda | 0.43 | 99 % (2013-2014) | 18 | 19 | plaster 1, stone 6, unknown 3 | 20 m | 48 % | HARD 700, LIFT 28, STEP 2 | HARD 627, LIFT 32, STEP 2 | 1 | classe plaster sbagliata (nella foto è pietra o intonaco); classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |
| Via Nóga | 0.19 | 100 % (2013-2022) | 9 | 12 | unknown 1 | - | 28 % | HARD 134, LIFT 9 | HARD 89 | 0 | - | [x] |
| Via Pazz | 2.50 | 92 % (2013-2014) | 89 | 13 | concrete 1 | - | 24 % | HARD 479, LIFT 25, STEP 2, TWIST 14 | HARD 267, LIFT 4 | 0 | - | [x] |
| Via Piánca | 0.24 | 100 % (2013-2014) | 10 | 3 | unknown 1 | - | 39 % | HARD 21 | 0 | 1 | - | [x] |
| Via Pèzza | 0.82 | 96 % (2013) | 32 | 14 | stone 1 | - | 23 % | HARD 291, LIFT 22 | HARD 88, LIFT 3 | 1 | muro alto in calcestruzzo reso in pietra; materiale dei muri dalle panoramiche segmentate (sv_walls.py) nella costruzione finale | [x] |
| Via Ronchetto | 0.19 | 100 % (2013-2022) | 8 | 12 | stone 1 | - | 48 % | HARD 59, LIFT 9, STEP 4 | HARD 31 | 0 | - | [x] |
| Via Rívra | 0.16 | 100 % (2013-2022) | 8 | 15 | unknown 1 | - | 50 % | HARD 103, LIFT 12, STEP 4 | HARD 6 | 0 | - | [x] |
| Via Rónch du Vécc | 0.18 | 100 % (2013) | 6 | 5 | plaster 1, stone 1, unknown 2 | 50 m | 36 % | HARD 71, STEP 4 | HARD 51 | 0 | - | [x] |
| Via Santo Stefano | 0.27 | 100 % (2013) | 12 | 23 | stone 3, unknown 4 | - | 36 % | HARD 218 | HARD 99 | 1 | - | [x] |
| Via Scerèe | 0.54 | 100 % (2013-2022) | 20 | 2 | - | - | 24 % | HARD 79 | HARD 14 | 0 | - | [x] |
| Via Scüpell | 0.15 | 100 % (2013-2022) | 7 | 10 | stone 7, unknown 6 | - | 42 % | HARD 134, STEP 4, TWIST 10 | HARD 105, LIFT 34, STEP 4, TWIST 28 | 1 | - | [x] |
| Via Selva Bella | 0.50 | 100 % (2013-2014) | 16 | 1 | - | - | 11 % | HARD 355, LIFT 7, TWIST 4 | HARD 329, LIFT 12, STEP 6, TWIST 4 | 0 | - | [x] |
| Via Sott i Ca | 0.28 | 100 % (2013-2022) | 13 | 17 | unknown 1 | - | 50 % | HARD 153, LIFT 11 | HARD 96 | 0 | - | [x] |
| Via Sótt ara Còsta | 0.32 | 100 % (2022) | 14 | 1 | - | - | 20 % | 0 | HARD 42, LIFT 10, STEP 2 | 0 | - | [x] |
| Via Sótt ara Gésa | 0.24 | 100 % (2013-2014) | 8 | 13 | concrete 1, stone 1 | - | 48 % | HARD 311, LIFT 29, STEP 4, TWIST 12 | HARD 250, LIFT 4 | 0 | - | [x] |
| Via Teatro | 0.18 | 100 % (2013-2014) | 6 | 19 | stone 6 | 12 m | 45 % | HARD 495, LIFT 10, STEP 1 | HARD 193, LIFT 4 | 3 | vista a 3 m, solo parti di facciata | [x] |
| Via Traverságn | 0.14 | 11 % (2013-2014) | 1 | 3 | - | - | 8 % | HARD 19 | HARD 7 | 0 | - | [~] |
| Via Vinéra | 0.28 | 71 % (2013-2022) | 7 | 8 | - | - | 33 % | HARD 77, LIFT 7, STEP 1 | HARD 30, LIFT 1 | 0 | - | [x] |
| Via Virgilio Chiesa | 0.01 | 100 % (2013) | 2 | 6 | unknown 1 | - | 50 % | HARD 65, LIFT 6 | HARD 37 | 0 | - | [x] |
| Via i Quádra | 0.31 | 100 % (2013-2022) | 12 | 18 | unknown 1 | - | 46 % | HARD 122, LIFT 9 | HARD 55 | 0 | - | [x] |
| Via Òrt de Prüvín | 0.10 | 92 % (2013-2014) | 3 | 6 | - | - | 41 % | HARD 21, LIFT 3, STEP 1 | HARD 16 | 0 | - | [x] |
| Viale Gisòra | 0.22 | 100 % (2013-2022) | 10 | 10 | unknown 1 | - | 50 % | HARD 39 | HARD 20 | 0 | - | [x] |
| Viale Pietro Grassi | 0.82 | 100 % (2014-2022) | 30 | 12 | plaster 1, stone 4, unknown 3 | 36 m | 43 % | HARD 829, LIFT 61, STEP 13, TWIST 47 | HARD 490, LIFT 21, STEP 1 | 0 | - | [x] |
| Vianova | 0.10 | 28 % (2022) | 2 | 5 | plaster 2, stone 1, unknown 1 | - | 8 % | HARD 78, LIFT 8, STEP 4 | HARD 59 | 0 | - | [~] |
| Vianova di Sotto | 0.06 | 29 % (2013) | 1 | 2 | - | - | 8 % | HARD 36, LIFT 8, STEP 4 | HARD 5 | 0 | - | [~] |
| a Nüs | 0.01 | 0 %  | 0 | 0 | - | - | 0 % | HARD 11 | HARD 11, LIFT 1 | 0 | - | [!] |
| a Riazzóra | 0.03 | 0 %  | 0 | 1 | - | - | 0 % | HARD 26, LIFT 4 | HARD 8 | 0 | - | [!] |
| a Zorént | 0.07 | 29 % (2013) | 1 | 4 | unknown 1 | - | 18 % | HARD 50, LIFT 4 | HARD 18 | 0 | - | [~] |
| ai Perlá | 0.59 | 41 % (2013) | 8 | 0 | - | - | 13 % | HARD 158 | HARD 104 | 0 | - | [~] |
| ai Pezzásc | 0.94 | 2 % (2013) | 1 | 0 | - | - | 1 % | HARD 117 | HARD 72 | 0 | - | [!] |
| ai Sceré | 0.17 | 0 %  | 0 | 0 | - | - | 0 % | 0 | HARD 4 | 0 | - | [!] |
| ai Vezzán | 0.59 | 0 %  | 0 | 3 | - | - | 0 % | HARD 51, STEP 1 | HARD 41, STEP 1 | 0 | - | [!] |
| ar Fontanón | 0.15 | 100 % (2013) | 6 | 7 | concrete 1, plaster 1, stone 3, unknown 2 | - | 40 % | HARD 357, LIFT 8, STEP 2 | HARD 223 | 0 | - | [x] |
| ar Inèra | 0.15 | 39 % (2013) | 2 | 5 | stone 1, unknown 1 | - | 20 % | HARD 35, LIFT 2 | HARD 5 | 0 | - | [~] |
| ar Laghétt | 0.47 | 100 % (2013) | 17 | 6 | stone 3, unknown 3 | 24 m | 39 % | HARD 230, LIFT 8, STEP 1 | HARD 113, LIFT 11 | 0 | - | [x] |
| ar Ronchée | 0.38 | 100 % (2013) | 17 | 16 | stone 1, unknown 4 | - | 46 % | HARD 33 | HARD 19 | 3 | - | [x] |
| ara Dogána | 0.73 | 100 % (2013) | 28 | 7 | - | - | 28 % | HARD 101 | HARD 66 | 0 | - | [x] |
| ara Gésa | 0.14 | 100 % (2013) | 6 | 8 | concrete 1, plaster 1, stone 1, unknown 2 | - | 50 % | HARD 31, LIFT 4 | HARD 22, LIFT 2, STEP 1 | 0 | - | [x] |
| ara Mósa | 0.36 | 5 % (2013) | 1 | 4 | unknown 2 | - | 1 % | HARD 71, LIFT 1, STEP 7 | HARD 53, LIFT 1, STEP 4 | 0 | - | [!] |

## Luino

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Via Cantonale | 0.05 | 100 % (2018-2025) | 3 | 3 | unknown 1 | - | 10 % | HARD 72 | HARD 72 | 0 | - | [x] |

## Magliaso

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: raccordo) | 0.01 | 100 % (2014-2022) | 2 | 4 | stone 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| (senza nome: strada 3 m) | 0.80 | 34 % (2013-2022) | 15 | 26 | stone 1, unknown 5 | - | 14 % | HARD 431, LIFT 15, STEP 8, TWIST 7 | HARD 326, LIFT 6, STEP 1, TWIST 7 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.52 | 41 % (2013-2022) | 14 | 29 | stone 5, unknown 1 | 14 m | 21 % | HARD 27, LIFT 4 | HARD 12, LIFT 4 | 0 | - | [~] |
| Via Bött | 0.09 | 100 % (2013-2022) | 4 | 3 | plaster 3, stone 3 | - | 49 % | HARD 33, LIFT 7 | 0 | 0 | - | [x] |
| Via Cantonale | 1.48 | 79 % (2013-2022) | 41 | 42 | plaster 3, stone 21, unknown 7 | 21 m | 39 % | HARD 683, LIFT 16, STEP 5, TWIST 5 | HARD 429, LIFT 15, STEP 5, TWIST 5 | 3 | facciata verso la strada quasi cieca (piani contati dal terreno a monte), negozi al piano terra; facciate per casa, piani dal fronte strada, toni e persiane rivisti (facades.py, buildings_mesh.py); vetrine dai negozi di OSM | [x] |
| Via Castellaccio | 0.15 | 100 % (2013-2022) | 6 | 10 | stone 1 | - | 50 % | HARD 66, LIFT 10, STEP 2 | HARD 9 | 1 | vetrine del piano terra rese come finestre; con le gronde corrette il piano terra è alto abbastanza per le vetrine (facades.py) | [x] |
| Via Chiesa | 0.35 | 12 % (2014) | 2 | 3 | stone 1, unknown 1 | - | 4 % | HARD 194, LIFT 4, STEP 5 | HARD 77 | 0 | - | [~] |
| Via Chioso | 0.11 | 95 % (2013) | 5 | 11 | unknown 2 | - | 38 % | 0 | 0 | 1 | - | [x] |
| Via Ressiga | 0.33 | 100 % (2013) | 12 | 15 | unknown 2 | - | 50 % | HARD 19, LIFT 3, STEP 1 | HARD 3 | 0 | - | [x] |
| Via Robbiolo | 0.16 | 77 % (2013-2014) | 6 | 4 | stone 1, unknown 3 | - | 33 % | HARD 219, LIFT 4, STEP 2 | HARD 145, LIFT 3 | 0 | - | [x] |
| Via San Giorgio | 1.03 | 88 % (2013-2022) | 35 | 6 | stone 8, unknown 2 | 36 m | 35 % | HARD 968, LIFT 72, STEP 13, TWIST 60 | HARD 560, LIFT 19, STEP 1, TWIST 3 | 0 | - | [x] |
| Via San Rocco | 0.06 | 35 % (2013) | 1 | 7 | - | - | 13 % | HARD 8 | 0 | 0 | - | [~] |
| Via Stazione | 0.61 | 100 % (2013-2018) | 26 | 25 | stone 6, unknown 3 | - | 44 % | HARD 196, LIFT 11, STEP 5 | HARD 88, LIFT 5, STEP 3 | 0 | - | [x] |
| Via Vedeggi | 0.13 | 76 % (2013) | 4 | 11 | stone 1 | - | 26 % | 0 | 0 | 0 | - | [x] |

## Manno

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: accesso) | 0.18 | 100 % (2013-2022) | 8 | 2 | - | - | 50 % | HARD 21 | HARD 14 | 0 | - | [x] |
| (senza nome: raccordo) | 0.01 | 100 % (2014-2022) | 1 | 0 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| (senza nome: strada 3 m) | 1.36 | 34 % (2013-2022) | 21 | 57 | plaster 2, stone 4, unknown 7 | - | 19 % | HARD 1119, LIFT 143, STEP 20, TWIST 81 | HARD 714, LIFT 36, STEP 10, TWIST 40 | 0 | - | [~] |
| (senza nome: strada 4 m) | 1.35 | 56 % (2013-2022) | 33 | 33 | concrete 1, plaster 1, stone 3, unknown 2 | 42 m | 25 % | HARD 920, LIFT 182, STEP 16, TWIST 105 | HARD 446, LIFT 5 | 0 | - | [x] |
| (senza nome: strada 6 m) | 0.70 | 100 % (2013-2022) | 27 | 8 | - | - | 50 % | HARD 338, LIFT 32, STEP 4 | HARD 70 | 0 | - | [x] |
| (senza nome: uscita) | 0.03 | 100 % (2014-2022) | 3 | 0 | - | - | 50 % | HARD 2 | 0 | 0 | - | [x] |
| Piazza Bironico | 0.01 | 0 %  | 0 | 4 | - | - | 50 % | HARD 18 | HARD 7 | 0 | - | [!] |
| Strada Bassa | 0.18 | 94 % (2013-2014) | 8 | 12 | stone 1, unknown 1 | - | 38 % | HARD 236, LIFT 4, STEP 2 | HARD 180, LIFT 2 | 1 | piccolo garage reso come casa con una finestra, senza portone | [x] |
| Strada Costa | 0.40 | 100 % (2013-2022) | 14 | 9 | unknown 2 | - | 48 % | HARD 628, LIFT 78, STEP 4 | HARD 555, LIFT 27 | 0 | - | [x] |
| Strada Regina | 0.56 | 68 % (2014) | 16 | 23 | stone 3, unknown 2 | - | 31 % | HARD 1149, LIFT 105, STEP 8, TWIST 101 | HARD 869, LIFT 10, STEP 5, TWIST 8 | 1 | rustico in pietra reso come officina con finestre a nastro e tetto in lamiera; piccoli depositi del registro come rustici o capanni; tetti in ombra nell'ortofoto coperti secondo l'età | [x] |
| Streccia di Caminada | 0.14 | 83 % (2013-2022) | 3 | 7 | unknown 2 | - | 43 % | HARD 151 | HARD 155, LIFT 3 | 0 | - | [x] |
| Via Asilo | 0.07 | 21 % (2013) | 1 | 2 | unknown 1 | - | 10 % | HARD 21 | HARD 9 | 0 | - | [~] |
| Via Campagnola | 0.20 | 0 %  | 0 | 2 | - | - | 0 % | 0 | HARD 5 | 0 | - | [!] |
| Via Cantonale | 2.05 | 78 % (2013-2022) | 55 | 19 | plaster 3, unknown 1 | - | 39 % | HARD 1158, LIFT 43, STEP 4, TWIST 6 | HARD 398, LIFT 19, STEP 1 | 0 | - | [x] |
| Via Carà | 0.46 | 100 % (2013-2022) | 17 | 24 | plaster 1, stone 4, unknown 6 | - | 49 % | HARD 1746, LIFT 53, STEP 2 | HARD 1340, LIFT 30, TWIST 4 | 0 | - | [x] |
| Via Cassinelle | 0.26 | 60 % (2013) | 6 | 17 | plaster 1, unknown 3 | - | 32 % | HARD 283, LIFT 44, TWIST 35 | HARD 174, LIFT 8 | 0 | - | [x] |
| Via Dragoni | 0.09 | 0 %  | 0 | 2 | - | - | 0 % | HARD 14 | 0 | 0 | - | [!] |
| Via Gerre | 0.13 | 9 % (2022) | 2 | 0 | - | - | 21 % | HARD 110 | 0 | 0 | - | [~] |
| Via Grumo | 0.61 | 66 % (2013-2022) | 17 | 19 | plaster 1, stone 3, unknown 4 | - | 32 % | HARD 1343, HOLE 2, LIFT 85, STEP 11, TWIST 29 | HARD 945, HOLE 2, LIFT 42, STEP 12, TWIST 16 | 0 | - | [x] |
| Via Industria | 0.14 | 13 % (2022) | 1 | 2 | - | - | 10 % | HARD 6 | 0 | 0 | - | [~] |
| Via Masma | 0.17 | 100 % (2013) | 7 | 16 | plaster 1, unknown 5 | - | 49 % | HARD 76, LIFT 10, STEP 2, TWIST 5 | HARD 10 | 0 | - | [x] |
| Via Mondadiscio | 0.22 | 70 % (2022) | 5 | 10 | stone 1, unknown 2 | - | 38 % | HARD 845, LIFT 9, STEP 5 | HARD 788, LIFT 2 | 0 | - | [x] |
| Via Norello | 0.49 | 100 % (2013-2022) | 16 | 21 | plaster 1, stone 1, unknown 1 | - | 50 % | HARD 615, LIFT 2, STEP 4 | HARD 339 | 0 | - | [x] |
| Via Orti | 0.28 | 98 % (2013-2022) | 10 | 8 | plaster 1, unknown 1 | - | 47 % | HARD 395, LIFT 27, STEP 1 | HARD 210, LIFT 5 | 0 | - | [x] |
| Via Pobiette | 0.43 | 68 % (2013-2022) | 10 | 4 | plaster 1 | - | 37 % | 0 | 0 | 0 | - | [x] |
| Via Quadrella | 0.15 | 100 % (2013-2022) | 6 | 13 | stone 1, unknown 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Rivalta | 0.09 | 89 % (2022) | 2 | 7 | stone 1, unknown 1 | - | 39 % | HARD 6, LIFT 2 | 0 | 0 | - | [x] |
| Via San Rocco | 0.04 | 0 %  | 0 | 4 | - | - | 5 % | HARD 139 | HARD 152, LIFT 2 | 0 | - | [!] |
| Via Scuola Vecchia | 0.05 | 0 %  | 0 | 6 | - | - | 0 % | HARD 316, LIFT 95, STEP 4, TWIST 103 | HARD 225, LIFT 35, TWIST 27 | 0 | - | [!] |
| Via Sialunga | 0.21 | 100 % (2022) | 10 | 16 | concrete 1, stone 2, unknown 7 | - | 49 % | HARD 137, LIFT 8, STEP 2 | HARD 55 | 0 | - | [x] |
| Via Vecchio Castagno | 0.24 | 43 % (2013) | 5 | 12 | - | - | 26 % | HARD 796, LIFT 65, TWIST 15 | HARD 600, LIFT 39 | 0 | - | [~] |
| Via Vedeggio | 0.25 | 34 % (2022) | 4 | 4 | - | - | 16 % | HARD 450, LIFT 73, STEP 7, TWIST 41 | HARD 447, LIFT 76, STEP 9, TWIST 46 | 0 | - | [~] |
| Via Vignascia | 0.17 | 87 % (2013) | 5 | 13 | concrete 2, stone 1, unknown 2 | - | 43 % | 0 | 0 | 0 | - | [x] |
| Via Vignole | 0.17 | 100 % (2013-2022) | 5 | 9 | concrete 1, plaster 1, unknown 2 | - | 47 % | HARD 18, LIFT 8 | 0 | 0 | - | [x] |
| Via Violino | 0.31 | 63 % (2013-2022) | 5 | 2 | - | - | 32 % | HARD 301, LIFT 25, STEP 5, TWIST 20 | HARD 280, LIFT 25, STEP 5, TWIST 20 | 0 | - | [x] |
| Via ai Boschetti | 1.01 | 59 % (2013) | 22 | 35 | plaster 1, stone 2, unknown 7 | - | 27 % | HARD 4527, LIFT 299, STEP 30, TWIST 188 | HARD 3526, LIFT 168, STEP 7, TWIST 25 | 0 | - | [x] |

## Neggio

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 0.67 | 34 % (2013-2014) | 10 | 10 | stone 3, unknown 3 | - | 12 % | HARD 49, LIFT 2, STEP 3 | HARD 22 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.16 | 100 % (2013-2014) | 10 | 4 | unknown 1 | - | 50 % | HARD 65 | HARD 59 | 0 | - | [x] |
| Strada Regina | 0.93 | 100 % (2013-2014) | 39 | 16 | stone 6, unknown 9 | - | 32 % | HARD 817, LIFT 19, STEP 4 | HARD 584, LIFT 2, STEP 1 | 3 | ocra con persiane marroni, nella mappa beige-grigio con persiane grigie; tono della facciata: giallo nella foto, bianco nella mappa (misurato su altre facciate); toni schiariti; persiane marroni misurate accettate | [x] |
| Via Giuseppe Soldati | 1.04 | 100 % (2014) | 37 | 11 | stone 5, unknown 1 | 197 m | 46 % | HARD 1669, HOLE 6, LIFT 114, STEP 4, TWIST 52 | HARD 1550, HOLE 6, LIFT 65, STEP 4, TWIST 52 | 0 | - | [x] |
| Via Laghetti | 0.27 | 59 % (2013-2014) | 6 | 4 | stone 5 | - | 20 % | HARD 4 | 0 | 0 | - | [x] |
| Via Robbiolo | 0.04 | 100 % (2013-2014) | 2 | 2 | stone 1, unknown 1 | - | 48 % | HARD 4 | 0 | 0 | - | [x] |
| Via ai Mulini | 0.20 | 100 % (2013) | 10 | 8 | unknown 2 | - | 44 % | HARD 85, LIFT 7, STEP 1, TWIST 9 | HARD 46 | 0 | - | [x] |

## Pura

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 1.28 | 33 % (2013-2022) | 19 | 46 | concrete 2, plaster 1, stone 12, unknown 12 | - | 14 % | HARD 599, LIFT 26, STEP 8, TWIST 16 | HARD 346, LIFT 24 | 3 | casa bianca con tetto in coppi; tono un po' più grigio; capannone: swissBUILDINGS3D ha i muri solo sotto metà del tetto (24 m di tetto su 12 m di muri); toni misurati schiariti (SV_LIFT); limite dei dati (13 edifici su 11 700 hanno il tetto oltre i muri dove la misurazione ufficiale ha l'edificio) | [~] |
| (senza nome: strada 4 m) | 0.06 | 50 % (2014-2022) | 3 | 5 | stone 1, unknown 1 | - | 25 % | HARD 373, LIFT 46, STEP 6, TWIST 4 | HARD 280, LIFT 13 | 0 | - | [x] |
| Contrada Cozóra | 0.25 | 99 % (2022) | 9 | 15 | stone 10, unknown 3 | - | 31 % | HARD 84, LIFT 12 | HARD 130, LIFT 14, STEP 4 | 0 | - | [x] |
| Contrada vecchia cantonale | 0.13 | 0 %  | 0 | 8 | stone 3 | - | 6 % | HARD 15 | HARD 15 | 0 | - | [!] |
| Piazzale Gesòra | 0.06 | 37 % (2022) | 1 | 3 | stone 2 | - | 17 % | 0 | LIFT 1 | 0 | - | [~] |
| Piazzale Latéria | 0.06 | 71 % (2022) | 2 | 6 | stone 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Strada Cantonale | 2.38 | 92 % (2013-2022) | 74 | 63 | plaster 3, stone 25, unknown 16 | 536 m | 44 % | HARD 3622, LIFT 380, STEP 70, TWIST 198 | HARD 3622, LIFT 380, STEP 70, TWIST 198 | 1 | guardrail di 26 m visto nelle panoramiche (voti 13/14); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Strada Regina | 0.01 | 100 % (2022) | 1 | 2 | - | - | 10 % | 0 | HARD 4, LIFT 2 | 0 | - | [x] |
| Strada ara Morèla | 0.26 | 12 % (2013-2022) | 1 | 9 | stone 3, unknown 1 | - | 6 % | HARD 486, LIFT 20, STEP 8, TWIST 36 | HARD 478, LIFT 21, STEP 8, TWIST 36 | 0 | - | [~] |
| Via Biée | 0.35 | 100 % (2013-2022) | 15 | 21 | concrete 2, stone 1, unknown 8 | - | 48 % | HARD 248, LIFT 7, STEP 4, TWIST 26 | HARD 149, LIFT 7, STEP 2, TWIST 19 | 0 | - | [x] |
| Via Brocásg | 0.30 | 100 % (2013-2022) | 12 | 20 | stone 4 | - | 48 % | HARD 291, LIFT 7 | HARD 239 | 1 | tono della facciata: rosa salmone nella foto, grigio chiaro nella mappa (misura in ombra) | [x] |
| Via Campágna | 0.17 | 75 % (2013) | 5 | 7 | unknown 1 | - | 41 % | HARD 2 | 0 | 0 | - | [x] |
| Via Cüchée | 0.15 | 100 % (2013-2022) | 7 | 10 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Latéria | 0.12 | 13 % (2022) | 1 | 4 | stone 2, unknown 2 | - | 5 % | HARD 6, LIFT 2 | 0 | 0 | - | [~] |
| Via Lögh | 0.15 | 15 % (2022) | 1 | 7 | - | - | 11 % | HARD 38, LIFT 6, STEP 2, TWIST 1 | HARD 17 | 0 | - | [~] |
| Via Mangára | 0.30 | 100 % (2013-2022) | 11 | 20 | concrete 2, unknown 4 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Mistorni | 1.45 | 100 % (2013-2022) | 55 | 25 | stone 4, unknown 1 | 72 m | 40 % | HARD 73, LIFT 3 | HARD 53 | 0 | - | [x] |
| Via Mött | 0.44 | 85 % (2014) | 16 | 8 | concrete 1, stone 6 | - | 41 % | HARD 415, LIFT 92, STEP 7, TWIST 89 | HARD 323, LIFT 43, STEP 8, TWIST 52 | 0 | - | [x] |
| Via Paladina | 0.64 | 100 % (2013-2022) | 26 | 24 | stone 3, unknown 6 | - | 45 % | HARD 46 | 0 | 0 | - | [x] |
| Via Piscicoltura | 0.35 | 100 % (2013-2022) | 13 | 4 | stone 1, unknown 3 | 14 m | 43 % | HARD 68, LIFT 2 | HARD 68, LIFT 2 | 0 | - | [x] |
| Via Piánca | 0.21 | 28 % (2022) | 2 | 1 | plaster 1, unknown 3 | - | 12 % | HARD 92, LIFT 6, STEP 2 | HARD 91, LIFT 6, STEP 2 | 0 | - | [~] |
| Via Posgésa | 0.20 | 28 % (2013-2022) | 3 | 11 | plaster 1 | - | 16 % | HARD 150, STEP 2 | HARD 64, STEP 2 | 0 | - | [~] |
| Via Prelòngh | 1.04 | 94 % (2013-2022) | 33 | 20 | stone 6, unknown 9 | - | 33 % | HARD 65, LIFT 8, STEP 2 | HARD 24 | 0 | - | [x] |
| Via Prüssiána | 0.33 | 100 % (2014-2022) | 11 | 6 | plaster 3, unknown 5 | - | 32 % | 0 | HARD 137, LIFT 4 | 0 | - | [x] |
| Via Ronchétt | 0.14 | 100 % (2022) | 8 | 12 | stone 1, unknown 2 | - | 50 % | HARD 114, LIFT 4 | HARD 112 | 0 | - | [x] |
| Via Selváscia | 0.09 | 100 % (2013-2022) | 4 | 1 | - | - | 50 % | HARD 61 | HARD 49 | 0 | - | [x] |
| Via Sorìsc | 0.05 | 28 % (2014) | 1 | 3 | stone 2 | - | 12 % | HARD 59 | HARD 64 | 0 | - | [~] |
| Via Sélva | 0.33 | 0 %  | 0 | 0 | - | - | 0 % | HARD 203, LIFT 2 | HARD 191, LIFT 1 | 0 | - | [!] |
| Via Sótt Nüsei | 0.73 | 93 % (2013-2022) | 22 | 7 | stone 8, unknown 6 | 12 m | 22 % | HARD 432, LIFT 33, STEP 4, TWIST 7 | HARD 434, LIFT 19, STEP 2, TWIST 10 | 0 | - | [x] |
| Via Valcaldána | 0.15 | 100 % (2013) | 5 | 5 | stone 1, unknown 2 | - | 47 % | HARD 281, LIFT 22, TWIST 17 | HARD 236 | 0 | - | [x] |
| Via ai Romani | 0.21 | 7 % (2013) | 0 | 7 | stone 1, unknown 1 | - | 1 % | HARD 44 | HARD 38 | 0 | - | [~] |

## Tresa

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: raccordo) | 0.02 | 77 % (2014-2022) | 2 | 1 | - | - | 46 % | HARD 27, LIFT 3 | HARD 32, STEP 2 | 0 | - | [x] |
| (senza nome: strada 3 m) | 7.68 | 48 % (2013-2022) | 168 | 155 | concrete 1, plaster 2, stone 24, unknown 33 | 32 m | 21 % | HARD 3839, LIFT 441, STEP 84, TWIST 303 | HARD 2656, LIFT 270, STEP 25, TWIST 215 | 2 | - | [~] |
| (senza nome: strada 4 m) | 2.83 | 69 % (2013-2022) | 79 | 37 | plaster 2, stone 15, unknown 1 | 407 m | 33 % | HARD 4884, LIFT 398, STEP 36, TWIST 166 | HARD 3854, LIFT 190, STEP 14, TWIST 89 | 0 | - | [x] |
| (senza nome: strada 6 m) | 0.05 | 38 % (2013) | 2 | 2 | stone 1 | - | 27 % | HARD 155, LIFT 15, STEP 4 | HARD 48 | 0 | - | [~] |
| Al Marcadello | 0.07 | 0 %  | 0 | 0 | - | - | 0 % | HARD 66, LIFT 5, STEP 4 | HARD 12 | 0 | - | [!] |
| Ar Valécc | 0.14 | 100 % (2013) | 7 | 9 | stone 1, unknown 1 | - | 38 % | HARD 31, LIFT 2 | HARD 2 | 2 | salmone con persiane bianche, nella mappa bruno con persiane verdi; casa in mattoni e pietra resa intonacata; toni schiariti | [x] |
| Barico nucleo | 0.77 | 100 % (2013-2014) | 28 | 13 | stone 4, unknown 6 | 48 m | 43 % | HARD 1587, LIFT 206, STEP 2, TWIST 21 | HARD 1489, LIFT 148, STEP 2, TWIST 11 | 1 | classe plaster sbagliata (nella foto è pietra o intonaco); classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |
| Beride | 1.02 | 100 % (2013) | 37 | 15 | unknown 4 | - | 35 % | HARD 359, LIFT 19, STEP 4 | HARD 266, LIFT 19, STEP 2 | 0 | - | [x] |
| Biogno | 0.89 | 100 % (2013-2022) | 31 | 14 | stone 8, unknown 2 | 94 m | 40 % | HARD 1184, LIFT 108, STEP 51, TWIST 79 | HARD 393, LIFT 22, STEP 2, TWIST 14 | 0 | - | [x] |
| Campagna | 0.14 | 0 %  | 0 | 1 | - | - | 0 % | HARD 3 | 0 | 0 | - | [!] |
| Cascine di Barico | 0.66 | 100 % (2013-2022) | 27 | 10 | unknown 1 | - | 38 % | HARD 286, LIFT 14, STEP 6, TWIST 6 | HARD 188 | 0 | - | [x] |
| Castelrotto nucleo | 0.37 | 4 % (2014) | 1 | 4 | stone 2 | - | 3 % | HARD 1626, LIFT 312, STEP 67, TWIST 192 | HARD 1406, HOLE 22, LIFT 242, STEP 37, TWIST 199 | 0 | - | [!] |
| Contrada Mons. Celestino Trezzini | 0.13 | 100 % (2013) | 6 | 8 | stone 2, unknown 2 | - | 15 % | HARD 53 | HARD 19 | 0 | - | [x] |
| Croglio | 0.30 | 100 % (2013) | 12 | 5 | stone 6, unknown 2 | - | 29 % | HARD 238, LIFT 2 | HARD 233, LIFT 2 | 0 | - | [x] |
| Lisora | 0.34 | 100 % (2013-2022) | 14 | 0 | - | - | 48 % | HARD 10, LIFT 6 | 0 | 0 | - | [x] |
| Lungo Tresa | 0.57 | 100 % (2022) | 21 | 8 | stone 2, unknown 1 | - | 49 % | HARD 11 | HARD 35 | 0 | - | [x] |
| Lüsc | 0.98 | 41 % (2013-2022) | 15 | 4 | stone 5, unknown 2 | 40 m | 19 % | HARD 1221, LIFT 145, STEP 9, TWIST 61 | HARD 854, LIFT 29, STEP 1 | 0 | - | [~] |
| Madonna del Piano | 0.39 | 100 % (2013-2022) | 16 | 18 | stone 3, unknown 3 | - | 44 % | HARD 427, LIFT 38, STEP 4, TWIST 6 | HARD 227, LIFT 14, STEP 4, TWIST 6 | 0 | - | [x] |
| Madonnone | 0.88 | 6 % (2022) | 2 | 1 | - | - | 4 % | HARD 623, LIFT 130, STEP 4, TWIST 94 | HARD 368, LIFT 81, TWIST 50 | 0 | - | [~] |
| Mött | 0.25 | 100 % (2014-2022) | 8 | 6 | stone 4, unknown 4 | - | 50 % | HARD 1136, LIFT 85, STEP 10, TWIST 30 | HARD 795, LIFT 12 | 0 | - | [x] |
| Nuova Barico | 0.85 | 100 % (2014) | 28 | 13 | stone 1, unknown 3 | - | 38 % | HARD 376, LIFT 20, STEP 5, TWIST 20 | HARD 180 | 0 | - | [x] |
| Piazza Castello | 0.04 | 100 % (2013) | 2 | 3 | - | - | 45 % | HARD 108, LIFT 12 | HARD 71 | 0 | - | [x] |
| Piazzale della Stazione | 0.08 | 100 % (2013-2022) | 4 | 4 | stone 2 | - | 32 % | HARD 228, LIFT 3, STEP 1 | HARD 63 | 1 | - | [x] |
| Purasca Inferiore | 1.12 | 62 % (2014-2022) | 23 | 25 | concrete 3, stone 12, unknown 8 | - | 26 % | HARD 1467, LIFT 177, STEP 12, TWIST 104 | HARD 1226, LIFT 65, TWIST 23 | 3 | tono troppo scuro, facciata cieca; zoccolo in pietra alto un piano non modellato; facciate per casa, piani dal fronte strada, toni e persiane rivisti (facades.py, buildings_mesh.py) | [x] |
| Purasca Superiore | 0.46 | 100 % (2014) | 17 | 10 | plaster 3, stone 2, unknown 16 | - | 49 % | HARD 485, LIFT 16, STEP 4 | HARD 453 | 1 | muro in stone come nella foto; materiale del muro dalle panoramiche | [x] |
| Romanino | 1.05 | 75 % (2013-2022) | 31 | 15 | stone 6, unknown 2 | 20 m | 30 % | HARD 585, LIFT 47, STEP 6, TWIST 11 | HARD 405, LIFT 9, STEP 2 | 0 | - | [x] |
| Ronchetto | 0.22 | 94 % (2013) | 8 | 1 | - | - | 31 % | HARD 23 | HARD 16 | 0 | - | [x] |
| Ronco | 0.46 | 100 % (2013) | 16 | 5 | stone 2 | - | 21 % | HARD 25, LIFT 2 | HARD 25, LIFT 2 | 0 | - | [x] |
| Ronco Regina | 0.05 | 100 % (2013-2022) | 2 | 3 | stone 2, unknown 2 | - | 50 % | HARD 259, LIFT 23, STEP 10, TWIST 27 | HARD 131, LIFT 2 | 0 | - | [x] |
| Salita Rocchetta | 0.03 | 100 % (2013-2022) | 1 | 5 | - | - | 17 % | HARD 243, LIFT 10, STEP 3, TWIST 8 | HARD 181, LIFT 6 | 0 | - | [x] |
| Strada Cantonale | 2.07 | 100 % (2013-2022) | 81 | 18 | stone 6, unknown 6 | 304 m | 49 % | HARD 386, LIFT 34, STEP 4, TWIST 36 | HARD 144, LIFT 4 | 0 | - | [x] |
| Strada per Biogno | 0.20 | 100 % (2022) | 8 | 0 | - | - | 30 % | HARD 33 | HARD 11 | 0 | - | [x] |
| Ur Streción | 0.24 | 100 % (2013-2014) | 9 | 7 | - | - | 29 % | HARD 56 | HARD 21, LIFT 3 | 0 | - | [x] |
| Valegiöö | 0.14 | 100 % (2022) | 6 | 3 | stone 3, unknown 1 | - | 15 % | HARD 258, LIFT 13, STEP 1 | HARD 252, LIFT 17 | 0 | - | [x] |
| Via Astano | 2.06 | 100 % (2013) | 76 | 19 | stone 5, unknown 1 | 327 m | 46 % | HARD 2017, LIFT 42, TWIST 9 | HARD 1945, LIFT 33 | 0 | - | [x] |
| Via Balgine | 0.13 | 23 % (2013) | 2 | 10 | - | - | 13 % | HARD 53 | HARD 48 | 0 | - | [~] |
| Via Bonere | 0.40 | 100 % (2013) | 15 | 18 | plaster 1, unknown 2 | - | 45 % | HARD 148, LIFT 1 | HARD 172, LIFT 16, STEP 2 | 1 | casa bianca in ombra resa azzurra (la luce del cielo nella misura del tono); i toni blu misurati perdono saturazione (facades.sv_tone, SV_BLUE): 108 → 4 toni bluastri | [x] |
| Via Bonzaglio | 0.17 | 100 % (2013-2014) | 6 | 6 | - | - | 43 % | HARD 45, LIFT 3, STEP 2 | HARD 4 | 0 | - | [x] |
| Via Boscioro | 1.13 | 100 % (2013-2022) | 40 | 35 | plaster 1, stone 6, unknown 5 | 225 m | 47 % | HARD 2017, LIFT 109, STEP 10, TWIST 36 | HARD 1550, LIFT 1 | 1 | - | [x] |
| Via Brusata | 0.11 | 100 % (2013-2014) | 5 | 9 | stone 2 | - | 44 % | HARD 109, LIFT 6, STEP 2 | HARD 88 | 0 | - | [x] |
| Via Buseno | 1.15 | 100 % (2013-2014) | 46 | 10 | unknown 4 | 42 m | 37 % | HARD 93, LIFT 6 | HARD 40, LIFT 7 | 0 | - | [x] |
| Via Campagna | 0.44 | 100 % (2013-2022) | 19 | 24 | concrete 1, stone 2 | - | 50 % | HARD 295, LIFT 17, STEP 6, TWIST 18 | HARD 88, LIFT 2, STEP 1 | 0 | - | [x] |
| Via Cantonale | 4.55 | 99 % (2013-2022) | 170 | 79 | plaster 1, stone 17, unknown 11 | 690 m | 47 % | HARD 2402, LIFT 272, STEP 8, TWIST 76 | HARD 1615, LIFT 91, STEP 8, TWIST 48 | 2 | guardrail di 40 m visto nelle panoramiche (voti 33/33); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Cassinone | 0.85 | 100 % (2013) | 33 | 15 | - | - | 49 % | HARD 26 | HARD 3 | 0 | - | [x] |
| Via Crocivaglio | 0.50 | 100 % (2013-2022) | 19 | 20 | plaster 1, stone 7, unknown 4 | - | 46 % | HARD 1239, LIFT 111, STEP 4, TWIST 26 | HARD 1234, LIFT 106, STEP 3 | 0 | - | [x] |
| Via Crosa | 0.63 | 100 % (2014) | 18 | 3 | stone 2, unknown 1 | 30 m | 41 % | HARD 1442, LIFT 113, STEP 2, TWIST 47 | HARD 1254, LIFT 50 | 0 | - | [x] |
| Via Fornasette | 1.91 | 100 % (2013-2018) | 73 | 33 | stone 11, unknown 5 | 100 m | 39 % | HARD 2038, LIFT 119, STEP 3, TWIST 94 | HARD 1791, LIFT 73, STEP 5, TWIST 47 | 1 | guardrail di 40 m visto nelle panoramiche (voti 20/20); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Grappoli | 0.46 | 100 % (2013-2014) | 18 | 15 | plaster 1, stone 1 | - | 27 % | HARD 192, LIFT 8, STEP 6 | HARD 87 | 0 | - | [x] |
| Via Industrie | 0.05 | 100 % (2013-2014) | 4 | 5 | unknown 1 | - | 50 % | HARD 26, LIFT 7 | 0 | 0 | - | [x] |
| Via Lanscino | 0.31 | 100 % (2014) | 14 | 15 | stone 1 | - | 47 % | HARD 43 | HARD 19 | 0 | - | [x] |
| Via Lisora | 0.52 | 100 % (2013) | 20 | 16 | stone 3 | - | 40 % | HARD 3 | HARD 4 | 0 | - | [x] |
| Via Lovrón | 1.33 | 100 % (2013-2014) | 50 | 17 | - | - | 48 % | HARD 460, LIFT 53, STEP 6, TWIST 18 | HARD 245, LIFT 25, STEP 6 | 0 | - | [x] |
| Via Lugano | 0.84 | 96 % (2013-2022) | 29 | 21 | stone 4, unknown 4 | 12 m | 42 % | HARD 382, LIFT 30, STEP 10, TWIST 34 | HARD 113, LIFT 8 | 0 | - | [x] |
| Via Mairocoli | 0.26 | 100 % (2013-2014) | 10 | 8 | - | - | 28 % | HARD 8 | 0 | 0 | - | [x] |
| Via Miniera | 0.12 | 100 % (2013) | 5 | 5 | unknown 1 | - | 46 % | HARD 33, LIFT 3 | HARD 8 | 0 | - | [x] |
| Via Monte Oliveto | 0.29 | 99 % (2013) | 11 | 20 | stone 2, unknown 1 | - | 44 % | HARD 33, LIFT 11, STEP 2 | HARD 21, LIFT 1 | 0 | - | [x] |
| Via Monteggio | 0.49 | 100 % (2013-2014) | 20 | 18 | stone 7, unknown 3 | 150 m | 48 % | HARD 898, LIFT 73, STEP 2, TWIST 72 | HARD 674, LIFT 68, STEP 2, TWIST 31 | 2 | vista lontana (2014) | [x] |
| Via Morina | 0.22 | 100 % (2013-2014) | 9 | 3 | plaster 1 | - | 26 % | HARD 53, LIFT 8, STEP 4 | HARD 45, LIFT 5, STEP 2 | 0 | - | [x] |
| Via Persico | 0.30 | 100 % (2014) | 11 | 7 | - | - | 45 % | HARD 473, LIFT 53, STEP 4, TWIST 18 | HARD 376, LIFT 11 | 0 | - | [x] |
| Via Pezza | 0.12 | 100 % (2014) | 3 | 11 | unknown 1 | - | 45 % | HARD 216, LIFT 47, TWIST 5 | HARD 170, LIFT 37, TWIST 5 | 0 | - | [x] |
| Via Pezze | 0.28 | 100 % (2013) | 12 | 20 | concrete 1, plaster 1, stone 1, unknown 4 | - | 49 % | HARD 74 | HARD 20 | 0 | - | [x] |
| Via Ponte Tresa | 0.44 | 100 % (2014) | 19 | 9 | plaster 1, stone 1 | 52 m | 50 % | HARD 234, LIFT 7 | HARD 187, LIFT 6 | 0 | - | [x] |
| Via Purasca | 0.82 | 77 % (2022) | 20 | 31 | stone 6, unknown 3 | - | 36 % | HARD 837, LIFT 70, TWIST 46 | HARD 669, LIFT 11 | 0 | - | [x] |
| Via Regina | 0.56 | 69 % (2013-2022) | 15 | 5 | stone 4, unknown 4 | - | 35 % | HARD 230, STEP 4 | HARD 181 | 0 | - | [x] |
| Via Roncaccio | 0.42 | 100 % (2013-2014) | 17 | 15 | stone 2 | - | 41 % | HARD 1331, HOLE 11, LIFT 75, STEP 9, TWIST 25 | HARD 1130, HOLE 11, LIFT 30, STEP 6, TWIST 22 | 0 | - | [x] |
| Via San Bernardino | 0.34 | 57 % (2014-2022) | 6 | 17 | plaster 1, stone 7, unknown 4 | - | 28 % | HARD 376, LIFT 1 | HARD 323, LIFT 6 | 1 | - | [x] |
| Via San Martino | 0.20 | 100 % (2013-2014) | 8 | 9 | stone 2, unknown 2 | - | 50 % | HARD 1406, LIFT 69, STEP 4, TWIST 41 | HARD 1091, LIFT 14 | 0 | - | [x] |
| Via Santa Maria | 0.37 | 100 % (2013-2014) | 15 | 16 | stone 1, unknown 1 | - | 41 % | HARD 294, LIFT 18, STEP 2 | HARD 286, LIFT 13, STEP 1 | 0 | - | [x] |
| Via Sceré | 0.16 | 18 % (2014) | 1 | 3 | - | - | 4 % | HARD 61, LIFT 10, STEP 4 | HARD 45 | 0 | - | [~] |
| Via Suino | 1.11 | 100 % (2013) | 42 | 12 | - | - | 39 % | HARD 169, LIFT 8 | HARD 59 | 0 | - | [x] |
| Via Suvino | 0.13 | 100 % (2013) | 6 | 12 | unknown 2 | - | 49 % | HARD 16, STEP 4 | 0 | 0 | - | [x] |
| Via Termine | 1.29 | 98 % (2013-2014) | 47 | 19 | concrete 1, stone 4 | 121 m | 35 % | HARD 641, LIFT 31, STEP 8, TWIST 29 | HARD 285, LIFT 24, STEP 1 | 1 | guardrail di 68 m visto nelle panoramiche (voti 45/46); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via ai Ronchi | 0.69 | 87 % (2014-2022) | 24 | 20 | plaster 1, stone 2, unknown 1 | - | 37 % | HARD 1413, LIFT 116, STEP 4, TWIST 55 | HARD 930, LIFT 22 | 0 | - | [x] |
| Via alle Bolle | 0.16 | 100 % (2014) | 8 | 5 | - | - | 48 % | HARD 32, LIFT 2 | HARD 52, LIFT 7, STEP 1 | 0 | - | [x] |
| Via delle Scuole | 0.30 | 23 % (2013-2022) | 2 | 4 | - | - | 7 % | HARD 1044, LIFT 41, STEP 7, TWIST 11 | HARD 847, LIFT 16, STEP 1 | 0 | - | [~] |
| Via la Piana | 0.30 | 13 % (2014-2022) | 2 | 6 | stone 1, unknown 1 | - | 6 % | HARD 29, LIFT 5, STEP 6 | 0 | 0 | - | [~] |
| Vicolo Baragia | 0.05 | 0 %  | 0 | 0 | - | - | 0 % | HARD 81 | HARD 44 | 0 | - | [!] |
| Villaggio del Sole | 0.24 | 100 % (2013) | 9 | 21 | - | - | 45 % | HARD 161, LIFT 1, STEP 2, TWIST 1 | HARD 165, LIFT 1 | 0 | - | [x] |
| Villalta | 0.28 | 95 % (2013) | 10 | 2 | - | - | 13 % | HARD 21, LIFT 8, STEP 2 | HARD 48 | 0 | - | [x] |
| Zona artigianale | 0.31 | 100 % (2013-2022) | 13 | 9 | unknown 4 | - | 50 % | 0 | 0 | 0 | - | [x] |

## Vernate

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 0.78 | 72 % (2013-2014) | 25 | 25 | concrete 1, stone 6, unknown 6 | 14 m | 20 % | HARD 767, LIFT 62, STEP 22, TWIST 92 | HARD 468, LIFT 21, STEP 8, TWIST 18 | 0 | - | [x] |
| (senza nome: strada 4 m) | 0.03 | 100 % (2013-2014) | 3 | 10 | stone 1, unknown 3 | - | 50 % | HARD 319, LIFT 40, TWIST 2 | HARD 97, LIFT 2 | 0 | - | [x] |
| Summer Village | 0.30 | 19 % (2014) | 4 | 6 | plaster 1, stone 2, unknown 1 | - | 6 % | HARD 439, LIFT 72, STEP 4, TWIST 16 | HARD 174, LIFT 19 | 0 | - | [~] |
| Via Balà | 0.12 | 37 % (2013) | 1 | 2 | - | - | 8 % | HARD 229, LIFT 41, STEP 3, TWIST 28 | HARD 118, STEP 2 | 0 | - | [~] |
| Via Cantonale | 4.04 | 89 % (2013-2014) | 137 | 51 | concrete 1, plaster 5, stone 18, unknown 15 | 470 m | 35 % | HARD 6922, LIFT 779, STEP 63, TWIST 520 | HARD 5385, LIFT 309, STEP 36, TWIST 165 | 0 | - | [x] |
| Via Cimo | 0.10 | 100 % (2013) | 4 | 4 | stone 1, unknown 2 | 85 m | 50 % | HARD 67 | HARD 17 | 1 | guardrail di 85 m visto nelle panoramiche (voti 64/66); guardrail costruito sul bordo della strada; controllato sulla foto: c'è ed è allineato | [x] |
| Via Evia | 0.24 | 94 % (2013-2014) | 8 | 12 | plaster 1, unknown 1 | - | 37 % | HARD 244, LIFT 5, STEP 2 | HARD 169 | 1 | tono della facciata: crema nella foto, rosa nella mappa (misura in ombra) | [x] |
| Via Mornirolo | 0.14 | 11 % (2014) | 2 | 4 | - | - | 5 % | HARD 102, LIFT 16, STEP 4, TWIST 10 | HARD 40 | 0 | - | [~] |
| Via Pree | 0.73 | 85 % (2014) | 24 | 32 | concrete 1, stone 3, unknown 5 | - | 40 % | HARD 801, LIFT 35, STEP 3 | HARD 687, LIFT 12 | 4 | edificio del 2025, dopo le foto del 2014; muro in stone come nella foto; materiale del muro dalle panoramiche; classi dei muri solo quando le foto sono chiare (sv_walls.py: STONE_C, SMOOTH_C) | [x] |
| Via Ravetta | 0.38 | 31 % (2013-2014) | 5 | 2 | stone 2 | - | 15 % | HARD 71, LIFT 4 | HARD 60 | 0 | - | [~] |
| Via alla Chiesa | 0.06 | 100 % (2013) | 2 | 10 | stone 3, unknown 3 | - | 45 % | HARD 125, TWIST 1 | HARD 131 | 1 | muro in stone come nella foto; materiale del muro dalle panoramiche | [x] |
| Villaggio del Sole | 0.36 | 94 % (2013) | 11 | 0 | stone 2 | - | 34 % | HARD 167 | HARD 174 | 0 | - | [x] |

## fuori dai comuni

| Strada | km | Street View | Panoramiche usate | Edifici misurati | Muri visti | Guardrail visti | Bordi visti | Guida v2.1 | Guida v2.2 | Luoghi rivisti | Problemi e modifiche | Stato |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (senza nome: strada 3 m) | 0.59 | 30 % (2013-2022) | 11 | 29 | concrete 1, stone 2 | - | 16 % | HARD 41, STEP 2 | HARD 54 | 0 | - | [~] |
| (senza nome: strada 4 m) | 0.07 | 57 % (2022) | 4 | 5 | - | - | 28 % | HARD 6 | HARD 6 | 0 | - | [x] |
| (senza nome: strada 6 m) | 0.01 | 100 % (2022) | 2 | 1 | - | - | 50 % | HARD 50, LIFT 7 | 0 | 0 | - | [x] |
| Caürga | 0.01 | 100 % (2013) | 1 | 1 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Contrada Nuova | 0.06 | 45 % (2022) | 2 | 4 | unknown 1 | - | 31 % | HARD 2 | 0 | 1 | edificio moderno con vetrine reso con persiane: il GWR lo data 1919-45 (ristrutturato); stile dal registro; il rinnovo della facciata non è nei dati | [~] |
| Cámpa | 0.00 | 100 % (2013) | 2 | 0 | - | - | 0 % | 0 | 0 | 0 | - | [x] |
| Focón | 0.03 | 100 % (2013) | 2 | 1 | - | - | 50 % | 0 | HARD 38 | 0 | - | [x] |
| Piazza Lago | 0.07 | 100 % (2013) | 5 | 2 | stone 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Stradón da Brén | 0.20 | 100 % (2022) | 9 | 10 | stone 5, unknown 4 | - | 50 % | HARD 590, LIFT 28 | HARD 563, LIFT 18 | 2 | intonaco chiaro, persiane grigio-verdi, porta | [x] |
| Stráda Végia da Brén | 0.03 | 93 % (2013) | 1 | 5 | - | - | 46 % | HARD 20 | HARD 22 | 1 | casa in pietra resa intonacata | [x] |
| Tavarón | 0.05 | 100 % (2013-2022) | 3 | 1 | - | - | 50 % | HARD 61, TWIST 1 | HARD 47 | 0 | - | [x] |
| Via Baragia | 0.01 | 100 % (2013) | 1 | 3 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Bernardino Quadri | 0.03 | 0 %  | 0 | 4 | unknown 1 | - | 0 % | 0 | 0 | 0 | - | [!] |
| Via Campagna | 0.05 | 0 %  | 0 | 0 | - | - | 0 % | 0 | 0 | 0 | - | [!] |
| Via Campagnora | 0.01 | 100 % (2013) | 3 | 3 | unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Camparlungo | 0.04 | 52 % (2013) | 2 | 3 | - | - | 38 % | 0 | 0 | 0 | - | [x] |
| Via Cantonale | 0.04 | 100 % (2014-2022) | 3 | 9 | stone 1, unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Castellaccio | 0.05 | 100 % (2013) | 3 | 5 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chiesa | 0.00 | 100 % (2022) | 2 | 3 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chiesuola | 0.00 | 100 % (2013) | 1 | 2 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chioso | 0.04 | 100 % (2013) | 4 | 10 | unknown 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Chiossetti | 0.09 | 100 % (2013) | 4 | 8 | unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Credera | 0.10 | 100 % (2013) | 5 | 5 | unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Danas | 0.04 | 100 % (2022) | 3 | 1 | - | - | 50 % | HARD 46 | HARD 44 | 0 | - | [x] |
| Via Golf | 0.02 | 100 % (2022) | 2 | 3 | concrete 2 | - | 50 % | HARD 24, LIFT 3 | HARD 27, LIFT 6 | 0 | - | [x] |
| Via Grumo | 0.08 | 100 % (2022) | 4 | 1 | - | - | 0 % | 0 | 0 | 0 | - | [x] |
| Via Industria | 0.08 | 95 % (2013-2022) | 6 | 5 | unknown 1 | - | 39 % | HARD 9 | HARD 10 | 0 | - | [x] |
| Via Industrie | 0.16 | 100 % (2013) | 7 | 3 | - | - | 50 % | HARD 77, LIFT 11 | HARD 37, LIFT 4 | 0 | - | [x] |
| Via Martelli | 0.04 | 100 % (2013) | 3 | 5 | concrete 1 | - | 50 % | 0 | HARD 1 | 0 | - | [x] |
| Via Mera | 0.02 | 100 % (2013) | 2 | 4 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Meriggi | 0.04 | 100 % (2013) | 3 | 3 | unknown 1 | - | 30 % | 0 | HARD 10 | 0 | - | [x] |
| Via Mimosa | 0.04 | 100 % (2013) | 3 | 3 | unknown 2 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Molinazzo | 0.03 | 100 % (2013) | 3 | 3 | - | - | 32 % | HARD 6, LIFT 2 | 0 | 0 | - | [x] |
| Via Monda | 0.05 | 100 % (2013) | 4 | 7 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Mulini | 0.03 | 60 % (2013) | 1 | 3 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Muraccio | 0.09 | 100 % (2013) | 5 | 9 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Neguggio | 0.18 | 100 % (2013-2018) | 8 | 11 | unknown 1 | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Nobreta | 0.06 | 100 % (2022) | 4 | 1 | - | - | 50 % | HARD 12 | HARD 11 | 0 | - | [x] |
| Via Nosetto | 0.04 | 100 % (2013) | 3 | 7 | unknown 1 | - | 50 % | 0 | HARD 7 | 0 | - | [x] |
| Via Orti | 0.14 | 100 % (2013-2022) | 7 | 12 | stone 1, unknown 3 | - | 49 % | 0 | 0 | 0 | - | [x] |
| Via Pradello | 0.16 | 98 % (2022) | 8 | 7 | - | - | 50 % | HARD 176, LIFT 22, TWIST 16 | HARD 47, LIFT 2 | 0 | - | [x] |
| Via Prati | 0.06 | 100 % (2013) | 4 | 5 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Prati Maggiori | 0.38 | 49 % (2013) | 8 | 3 | - | - | 26 % | 0 | 0 | 0 | - | [~] |
| Via Roggia | 0.01 | 100 % (2013) | 2 | 3 | - | - | 50 % | HARD 5 | 0 | 0 | - | [x] |
| Via Rompada | 0.03 | 100 % (2018) | 1 | 4 | stone 1 | - | 50 % | 0 | HARD 7 | 0 | - | [x] |
| Via San Pietro | 0.06 | 100 % (2013-2022) | 2 | 4 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via Serta | 0.06 | 100 % (2018) | 3 | 7 | - | - | 50 % | HARD 6 | HARD 3 | 0 | - | [x] |
| Via Stazione | 0.11 | 100 % (2013) | 5 | 8 | unknown 1 | - | 50 % | HARD 7, LIFT 2 | HARD 7, LIFT 3 | 0 | - | [x] |
| Via Stremadone | 0.06 | 100 % (2013) | 3 | 2 | stone 1, unknown 4 | - | 40 % | 0 | HARD 24 | 0 | - | [x] |
| Via Vedeggi | 0.07 | 100 % (2013) | 4 | 8 | stone 1 | - | 50 % | HARD 81, LIFT 1 | HARD 29, LIFT 1 | 0 | - | [x] |
| Via al Chioso | 0.06 | 69 % (2013) | 2 | 3 | plaster 1, unknown 2 | - | 42 % | HARD 19 | HARD 15 | 0 | - | [x] |
| Via al Fiume | 0.10 | 100 % (2022) | 5 | 0 | - | 22 m | 49 % | 0 | 0 | 0 | - | [x] |
| Via alla Chiesa di San Michele | 0.06 | 100 % (2014) | 3 | 7 | plaster 1, stone 1, unknown 4 | - | 48 % | 0 | HARD 14, LIFT 3, STEP 1 | 1 | muro in pietra della casa reso intonacato | [x] |
| Via alla Resega | 0.07 | 69 % (2022) | 4 | 10 | unknown 1 | - | 41 % | HARD 10 | 0 | 0 | - | [x] |
| Via dei Faggi | 0.01 | 0 %  | 0 | 1 | - | - | 0 % | HARD 13 | HARD 13 | 0 | - | [!] |
| Via del Parco | 0.12 | 100 % (2013) | 6 | 3 | - | - | 50 % | 0 | 0 | 0 | - | [x] |
| Via del Sole | 0.14 | 21 % (2013) | 1 | 7 | unknown 1 | - | 11 % | 0 | 0 | 0 | - | [~] |
| Via della Posta | 0.06 | 100 % (2022) | 3 | 5 | concrete 1 | - | 50 % | HARD 11 | HARD 23 | 0 | - | [x] |

