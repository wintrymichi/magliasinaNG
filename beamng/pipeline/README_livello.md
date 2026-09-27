# Strada Cantonale Magliaso → Pura (BeamNG.drive 0.39)

Ricostruzione in scala 1:1 dei 3,7 km di Strada Cantonale tra Magliaso e Pura (Canton Ticino). Il riferimento principale sono le 366 panoramiche Street View del percorso, quasi tutte di ottobre 2022. Le misure vengono dai dati ufficiali di swisstopo e del Cantone Ticino.

## Come si gioca

- **Livello:** `magliaso_pura`.
- **Punti di partenza:** `spawn_magliaso` (predefinito, all'incrocio di Magliaso), `spawn_mid` (a metà salita) e `spawn_pura` (in cima). Le auto partono nella corsia di marcia, rivolte verso Pura.
- **Traffico IA:** la rete stradale per l'IA copre la cantonale e le strade laterali.

## Cosa c'è e da dove viene

| Elemento | Fonte | Precisione |
|---|---|---|
| Terreno 4 × 4 km, maglia 1 m | swissALTI3D 0,5 m (LiDAR) | quota ±0,3 m |
| Strade e marciapiedi | misurazione ufficiale TI (limiti delle superfici), quota dal DTM | posizione ±0,1–0,2 m; superficie liscia adattata al DTM, con le pendenze reali (vedi Versione 1.1) |
| Edifici | swissBUILDINGS3D 3.0 (LOD2, tetti compresi) | ±0,3–0,5 m; facciate viste dalla strada con la texture delle foto |
| Muri | misurazione ufficiale (muri) + muri di sostegno ricavati da DTM e foto | altezza visibile misurata nelle foto dove il LiDAR prendeva tetti, balconi o guardrail sopra il muro; texture fotografiche a circa 3 cm/px |
| Guardrail (1,95 km), ringhiere e recinzioni sui muri (0,8 km) | voto multi-vista sulla segmentazione delle foto, LiDAR dove disponibile | posizione ±0,3 m |
| Segnaletica | ortofoto 10 cm (tratteggi 3 m / 6 m, strisce, zebre gialle), verificata nelle foto | stato di ottobre 2022 (vedi sotto) |
| Lampioni (73), pali e cartelli (50 pali, 67 targhe), delineatori, arredo urbano | triangolati dalle foto con le pose calibrate | ±0,3–0,5 m; le targhe riportano l'immagine vista nella foto, nessun testo inventato |
| Alberi (~112 000), siepi e arbusti | modello di superficie LiDAR (posizione, altezza e chioma di ogni albero), ortofoto; 169 arbusti aggiunti dove le foto li mostrano e il gioco no | specie approssimate (latifoglie, conifere, palme, cipressi) con modelli vanilla; nessuno sulla carreggiata |
| Lago di Lugano, paesaggio lontano | misurazione ufficiale, Copernicus GLO-30 | — |

## Stato del 2022 riprodotto

Le foto di ottobre 2022 sono più recenti dell'ortofoto e della misurazione ufficiale. Dove le fonti non concordano, il livello segue le foto:

- **Nessuna segnaletica** dove la strada era in rifacimento o non era segnata: s ≈ 1,23–1,27 km, 1,52–1,82 km e 3,64–3,72 km. Nel cantiere l'asfalto nuovo è più scuro.
- **Bande rosse** ai due bordi nel tratto s ≈ 2,29–2,44 km.
- **Incrocio di Magliaso:** l'incrocio era stato ricostruito, quindi le due isole pedonali e l'isola dipinta del rilievo sono state rimosse, e la mezzeria segue la posizione visibile nelle foto.

## Versione 1.1

- **Strade lisce.** Strade, marciapiedi e piazzali non ricalcano più il modello del terreno punto per punto: la loro superficie è liscia e adattata ai dati. Pendenze e curve restano quelle reali, mentre il rumore del LiDAR, le gobbe e gli avvallamenti spariscono. Sulla cantonale la sezione della carreggiata è piana.
- **Ponte e tratto a sbalzo.** Il modello del terreno rappresenta il suolo senza i ponti. Per questo la strada sul ponte del riale, a circa 3,05 km da Magliaso, scendeva di 7 m nel fosso, e il bordo a valle del tratto a circa 3,27 km cedeva di 3-4 m. Ora entrambi sono alla quota della strada, con i fianchi in pietra.
- **Muri tra superfici a quote diverse.** Dove una strada, un piazzale o una terrazza sta più in alto o più in basso della superficie accanto, il modello del terreno aveva spalmato il muro in una rampa. Ora al suo posto c'è un gradino con una faccia in pietra, e il terreno non sporge più sopra l'asfalto.
- **Carreggiata sgombra.** Gli alberi con il tronco sulla strada o a meno di 0,5 m dal bordo sono stati tolti. Gli arbusti e le siepi che sporgevano sulla carreggiata sono stati spostati indietro fino a 1,5 m; quelli che non ci stavano sono stati tolti.
- **Il resto segue la strada.** Segnaletica, rete dell'IA, lampioni, pali, cartelli, arredo e guardrail stanno sulla nuova superficie. Verso 1,25 km la linea dell'IA della cantonale non passa più sopra il muro tra le due strade.
- **Verifica.** Le cifre di `VERIFICA.md` si riferiscono alla geometria della v1.0.

## Precisione e verifica

- Le pose delle 366 panoramiche sono state stimate sull'ortofoto 10 cm con precisione di circa 0,3 m. In gioco, una camera posta nella stessa posa e con la stessa direzione vede la stessa inquadratura della foto.
- La verifica confronta le foto con le schermate del gioco nella stessa posa, segmentate con lo stesso modello (Mask2Former, Mapillary Vistas). Le cifre sono nel file `VERIFICA.md`.
- Tra 1,28 e 1,36 km non esistono panoramiche: lì il livello si basa solo sui dati swisstopo e sulla misurazione ufficiale.

## Fonti e licenze

- © swisstopo: swissALTI3D, SWISSIMAGE 10 cm, swissBUILDINGS3D, swissSURFACE3D.
- Misurazione ufficiale: Ufficio del catasto e dei riordini fondiari, Cantone Ticino.
- © OpenStreetMap contributors (ODbL).
- Copernicus DEM GLO-30: © DLR e.V. 2010-2014 e © Airbus Defence and Space GmbH 2014-2018, forniti nell'ambito di COPERNICUS da Unione Europea ed ESA.
- Le texture fotografiche delle facciate e dei muri e le targhe dei cartelli derivano da immagini Google Street View e sono solo per uso personale. Per pubblicare la mod bisogna costruire la versione senza di esse (`MAGLIASO_NO_PHOTO_TEXTURES=1`).
- Modelli 3D di alberi, lampioni e arredo: asset vanilla di BeamNG (East Coast USA, Italy), referenziati e non copiati.
