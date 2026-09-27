# Malcantone: Magliaso, Pura e dintorni (BeamNG.drive 0.39)

Ricostruzione in scala 1:1 di circa 46 km² del Malcantone (Canton Ticino), tra Ponte Tresa, Magliaso, Manno, Cademario, Novaggio, Astano e Sessa. Al centro ci sono i 3,7 km di Strada Cantonale tra Magliaso e Pura delle versioni 1.x, ricostruiti dalle 366 panoramiche Street View del percorso (quasi tutte di ottobre 2022). Il resto dell'area viene dai dati ufficiali di swisstopo e del Cantone Ticino.

## Come si gioca

- **Livello:** `magliaso_pura`.
- **Punti di partenza:**
  - `spawn_magliaso` (predefinito, all'incrocio di Magliaso), `spawn_mid` (a metà salita) e `spawn_pura` (in cima alla cantonale). Qui le auto partono nella corsia di marcia, rivolte verso Pura.
  - Un punto in ogni paese dell'area: `spawn_manno`, `spawn_aranno`, `spawn_astano`, `spawn_banco`, `spawn_bedigliora`, `spawn_bosco_luganese`, `spawn_cademario`, `spawn_castelrotto`, `spawn_cimo`, `spawn_curio`, `spawn_miglieglia`, `spawn_molinazzo_di_monteggio`, `spawn_monteggio`, `spawn_novaggio`, `spawn_ponte_tresa`, `spawn_purasca`, `spawn_sessa` e `spawn_pura_paese`.
- **Tutto è guidabile:** ogni strada e ogni sentiero dell'area ha una superficie solida, compresi mulattiere, scalinate e sentieri nel bosco.
- **Traffico IA:** la rete stradale per l'IA copre tutte le strade carrozzabili.

## Cosa c'è e da dove viene

| Elemento | Fonte | Precisione |
|---|---|---|
| Terreno 12,3 × 12,3 km, maglia 1,5 m | swissALTI3D 0,5 m e 2 m (LiDAR); Copernicus GLO-30 sul lato italiano | quota ±0,3 m nell'area |
| Strade e sentieri (circa 157 km di strade, 293 km di sentieri) | swissTLM3D (assi, classi, pavimentazione, ponti), misurazione ufficiale TI (limiti delle carreggiate) | profilo liscio calcolato su tutta la rete insieme: le quote coincidono agli incroci, le pendenze sono quelle reali |
| Ponti (137) | swissTLM3D, controllati uno per uno sul profilo e nelle viste | impalcato, parapetti e piloni; le strade sotto i ponti restano |
| Edifici (8490) | swissBUILDINGS3D 3.0 (LOD2, tetti compresi) | ±0,3–0,5 m; colore dei tetti dall'ortofoto; lungo la cantonale facciate viste dalla strada con la texture delle foto |
| Muri | misurazione ufficiale (muri) + muri di sostegno della cantonale ricavati da DTM e foto | lungo la cantonale l'altezza visibile è misurata nelle foto; texture fotografiche a circa 3 cm/px |
| Guardrail, ringhiere e recinzioni della cantonale | voto multi-vista sulla segmentazione delle foto, LiDAR dove disponibile | posizione ±0,3 m |
| Segnaletica della cantonale | ortofoto 10 cm (tratteggi 3 m / 6 m, strisce, zebre gialle), verificata nelle foto | stato di ottobre 2022 (vedi sotto) |
| Lampioni, pali e cartelli, delineatori, arredo urbano della cantonale | triangolati dalle foto con le pose calibrate | ±0,3–0,5 m; le targhe riportano l'immagine vista nella foto, nessun testo inventato |
| Alberi, siepi e arbusti (circa 240 000) | modello di superficie swissSURFACE3D (posizione, altezza e chioma di ogni albero), ortofoto | tutti entro 150 m dalle strade e 30 m dai sentieri, più radi oltre; specie approssimate con modelli vanilla; nessun tronco sulla carreggiata né a meno di 1 m dal bordo delle strade (0,5 m dei sentieri) |
| Lago di Lugano, paesaggio lontano | swissALTI3D, Copernicus GLO-30 | — |

## Stato del 2022 riprodotto sulla cantonale

Le foto di ottobre 2022 sono più recenti dell'ortofoto e della misurazione ufficiale. Dove le fonti non concordano, il livello segue le foto:

- **Nessuna segnaletica** dove la strada era in rifacimento o non era segnata: s ≈ 1,23–1,27 km, 1,52–1,82 km e 3,64–3,72 km. Nel cantiere l'asfalto nuovo è più scuro.
- **Bande rosse** ai due bordi nel tratto s ≈ 2,29–2,44 km.
- **Incrocio di Magliaso:** l'incrocio era stato ricostruito, quindi le due isole pedonali e l'isola dipinta del rilievo sono state rimosse, e la mezzeria segue la posizione visibile nelle foto.

## Versione 2.0

- **Area ampliata** dal corridoio della cantonale (4 × 4 km) a tutto il Malcantone tra i quattro punti di confine indicati, con il terreno allargato a 12,3 km.
- **Rete completa e liscia.** Tutte le linee di swissTLM3D (strade, strade forestali, sentieri, mulattiere, scalinate) hanno una superficie. La quota viene da un unico calcolo su tutta la rete: segue il terreno con le pendenze reali, senza il rumore del rilievo, ed è continua agli incroci e tra un tratto e l'altro. I ponti sono impalcati veri; dove swissTLM3D segna un ponte su un tombino, la strada resta sul terreno.
- **Il terreno non sporge mai sopra le strade:** sotto ogni superficie guidabile è scavato 10 cm più in basso della superficie più bassa lì intorno.
- **Vegetazione sgombra** su tutta la rete, non solo sulla cantonale.
- **La cantonale** tiene la superficie e tutti gli oggetti verificati della v1.1.

## Versione 1.1

- **Strade lisce** sulla cantonale: la superficie non ricalca più il modello del terreno punto per punto, la sezione della carreggiata è piana.
- **Ponte a 3,05 km e tratto a sbalzo a 3,27 km** alla quota della strada, con i fianchi in pietra.
- **Muri tra superfici a quote diverse** come gradini con una faccia in pietra invece di rampe.
- **Carreggiata sgombra** da alberi e arbusti.

## Precisione e verifica

- La v2.0 è controllata automaticamente su tutta la mappa. Il controllo cerca:
  - buchi e gradini lungo ogni strada e sentiero;
  - terreno sopra la strada;
  - giunzioni tra i pezzi;
  - alberi vicino alla carreggiata;
  - continuità della rete IA.
- Ci sono anche screenshot di tutta l'area, di ogni ponte, delle strade e dei paesi.
- Le pose delle 366 panoramiche della cantonale sono state stimate sull'ortofoto 10 cm con precisione di circa 0,3 m. La verifica della cantonale confronta le foto con le schermate del gioco nella stessa posa. Le cifre sono nel file `VERIFICA.md` e si riferiscono alla geometria della v1.0.
- Tra 1,28 e 1,36 km della cantonale non esistono panoramiche: lì il livello si basa solo sui dati swisstopo e sulla misurazione ufficiale.

## Limiti noti

- Sul lato italiano ci sono solo il terreno e il paesaggio, senza strade, edifici e alberi.
- Le gallerie non sono costruite.
- swissTLM3D non indica i sensi unici, quindi l'IA li percorre in entrambi i sensi.

## Fonti e licenze

- © swisstopo: swissALTI3D, SWISSIMAGE, swissBUILDINGS3D, swissSURFACE3D, swissTLM3D, swissNAMES3D.
- Misurazione ufficiale: Ufficio del catasto e dei riordini fondiari, Cantone Ticino.
- Copernicus DEM GLO-30: © DLR e.V. 2010-2014 e © Airbus Defence and Space GmbH 2014-2018, forniti nell'ambito di COPERNICUS da Unione Europea ed ESA.
- Le texture fotografiche delle facciate e dei muri e le targhe dei cartelli derivano da immagini Google Street View e sono solo per uso personale. Per pubblicare la mod bisogna costruire la versione senza di esse (`MAGLIASO_NO_PHOTO_TEXTURES=1`).
- Modelli 3D di alberi, lampioni e arredo: asset vanilla di BeamNG (East Coast USA, Italy), referenziati e non copiati.
