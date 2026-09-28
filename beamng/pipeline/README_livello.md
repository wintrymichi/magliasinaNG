# Malcantone: Magliaso, Pura e dintorni (BeamNG.drive 0.39)

Ricostruzione in scala 1:1 di circa 51 km² del Malcantone (Canton Ticino), tra Ponte Tresa, Magliaso, Agno, Bioggio, Manno, Gravesano, Cademario, Novaggio, Astano e Sessa. Al centro ci sono i 3,7 km di Strada Cantonale tra Magliaso e Pura delle versioni 1.x, ricostruiti dalle 366 panoramiche Street View del percorso (quasi tutte di ottobre 2022). A est c'è la cantonale da Magliaso a Gravesano: lungo il lago fino ad Agno, poi ai piedi dei monti per Bioggio e Manno. Il resto dell'area viene dai dati ufficiali di swisstopo e del Cantone Ticino.

## Come si gioca

- **Livello:** `magliaso_pura`.
- **Punti di partenza:**
  - `spawn_magliaso` (predefinito, all'incrocio di Magliaso), `spawn_mid` (a metà salita) e `spawn_pura` (in cima alla cantonale). Qui le auto partono nella corsia di marcia, rivolte verso Pura.
  - Un punto in ogni paese dell'area: `spawn_agno`, `spawn_bioggio`, `spawn_gravesano`, `spawn_magliaso_paese`, `spawn_manno`, `spawn_pura_paese`, `spawn_aranno`, `spawn_astano`, `spawn_banco`, `spawn_bedigliora`, `spawn_bosco_luganese`, `spawn_breno`, `spawn_cademario`, `spawn_cassina_d_agno`, `spawn_castelrotto`, `spawn_cimo`, `spawn_miglieglia`, `spawn_molinazzo_di_monteggio`, `spawn_monteggio`, `spawn_neggio`, `spawn_novaggio`, `spawn_ponte_tresa`, `spawn_purasca`, `spawn_sessa` e `spawn_vernate`. Per Curio c'è `spawn_pura`, a 160 m dal paese.
- **Tutto è guidabile:** ogni strada e ogni sentiero dell'area ha una superficie solida, compresi mulattiere, scalinate e sentieri nel bosco.
- **Traffico IA:** la rete stradale per l'IA copre tutte le strade carrozzabili.

## Cosa c'è e da dove viene

| Elemento | Fonte | Precisione |
|---|---|---|
| Terreno 12,3 × 12,3 km, maglia 1,5 m | swissALTI3D 0,5 m e 2 m (LiDAR); Copernicus GLO-30 sul lato italiano | quota ±0,3 m nell'area |
| Strade e sentieri (circa 212 km di strade, 331 km di sentieri) | swissTLM3D (assi, classi, pavimentazione, ponti), misurazione ufficiale TI (limiti delle carreggiate) | profilo liscio calcolato su tutta la rete insieme: le quote coincidono agli incroci, le pendenze sono quelle reali |
| Ponti (161) | swissTLM3D, controllati uno per uno sul profilo e nelle viste | impalcato, parapetti e piloni; le strade sotto i ponti restano |
| Edifici (11 220) | swissBUILDINGS3D 3.0 (LOD2, tetti compresi) | ±0,3–0,5 m; colore dei tetti dall'ortofoto; lungo la cantonale facciate viste dalla strada con la texture delle foto |
| Muri | misurazione ufficiale (muri) + muri di sostegno della cantonale ricavati da DTM e foto | lungo la cantonale l'altezza visibile è misurata nelle foto; texture fotografiche a circa 3 cm/px |
| Guardrail, ringhiere e recinzioni della cantonale | voto multi-vista sulla segmentazione delle foto, LiDAR dove disponibile | posizione ±0,3 m |
| Segnaletica della cantonale | ortofoto 10 cm (tratteggi 3 m / 6 m, strisce, zebre gialle), verificata nelle foto | stato di ottobre 2022 (vedi sotto) |
| Lampioni, pali e cartelli, delineatori, arredo urbano della cantonale | triangolati dalle foto con le pose calibrate | ±0,3–0,5 m; le targhe riportano l'immagine vista nella foto, nessun testo inventato |
| Alberi, siepi e arbusti (circa 241 000) | modello di superficie swissSURFACE3D (posizione, altezza e chioma di ogni albero), ortofoto | tutti entro 150 m dalle strade e 20 m dai sentieri, più radi oltre; specie approssimate con modelli vanilla; nessun tronco sulla carreggiata né a meno di 1 m dal bordo delle strade (0,5 m dei sentieri) |
| Lago di Lugano, paesaggio lontano | swissALTI3D, Copernicus GLO-30 | — |

## Stato del 2022 riprodotto sulla cantonale

Le foto di ottobre 2022 sono più recenti dell'ortofoto e della misurazione ufficiale. Dove le fonti non concordano, il livello segue le foto:

- **Nessuna segnaletica** dove la strada era in rifacimento o non era segnata: s ≈ 1,23–1,27 km, 1,52–1,82 km e 3,64–3,72 km. Nel cantiere l'asfalto nuovo è più scuro.
- **Bande rosse** ai due bordi nel tratto s ≈ 2,29–2,44 km.
- **Incrocio di Magliaso:** l'incrocio era stato ricostruito, quindi le due isole pedonali e l'isola dipinta del rilievo sono state rimosse, e la mezzeria segue la posizione visibile nelle foto.

## Versione 2.0

- **Area ampliata** dal corridoio della cantonale (4 × 4 km) a tutto il Malcantone tra i quattro punti di confine indicati, con il terreno allargato a 12,3 km.
- **Cantonale Magliaso–Gravesano** (8,8 km): dall'incrocio di Magliaso lungo il lago (Strada Regina) fino ad Agno, poi con Via Cantonale e Contrada San Marco per Bioggio e Manno fino a Gravesano. L'area comprende 150 m di territorio oltre la strada e tutto il pendio tra la strada e il resto della mappa.
- **Rete completa e liscia.** Tutte le linee di swissTLM3D (strade, strade forestali, sentieri, mulattiere, scalinate) hanno una superficie. La quota viene da un unico calcolo su tutta la rete: segue il terreno con le pendenze reali, senza il rumore del rilievo, ed è continua agli incroci e tra un tratto e l'altro. I ponti sono impalcati veri; dove swissTLM3D segna un ponte su un tombino, la strada resta sul terreno.
- **Il terreno non sporge mai sopra strade e sentieri**, neanche tra un vertice e l'altro della sua griglia di 1,5 m: ogni vertice i cui triangoli toccano una superficie guidabile sta 10 cm sotto la faccia più bassa lì intorno. Nessuna superficie guidabile sta sotto il terreno nudo.
- **Muri:** il terreno non sporge più a dente di sega davanti ai muri. Dietro i muri di sostegno il suolo resta al suo livello naturale.
- **Nessun ostacolo sulla carreggiata.** Dove il rilievo mette un muro in mezzo a una strada o a un sentiero, il muro è tagliato. Sotto gli edifici che stanno sulla strada (portici, la tettoia della dogana di Ponte Tresa, un vicolo sotto un campanile) c'è il passaggio. La passerella pedonale di Agno scavalca la cantonale a circa 4 m d'altezza, e nessun pilone sta su una strada.
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
  - terreno sopra strade e sentieri, misurato sulle facce e non solo sui vertici;
  - buchi nel terreno;
  - superfici guidabili sotto il terreno nudo;
  - giunzioni tra i pezzi;
  - ostacoli sulla carreggiata (muri, edifici, ponti, gradini), cercati lungo ogni strada e sentiero all'altezza di un'auto;
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
