# Malcantone: Magliaso, Pura e dintorni (BeamNG.drive 0.39)

Ricostruzione in scala 1:1 di circa 52 km² del Malcantone (Canton Ticino), tra Ponte Tresa, Caslano, Magliaso, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano e Sessa. Al centro ci sono i 3,7 km di Strada Cantonale tra Magliaso e Pura delle versioni 1.x, ricostruiti dalle 366 panoramiche Street View del percorso (quasi tutte di ottobre 2022). A est c'è la cantonale da Magliaso a Gravesano: lungo il lago fino ad Agno, poi ai piedi dei monti per Bioggio e Manno. Dalla v2.2 ci sono anche il passo sopra Gravesano fino ad Arosio (lo Stradón da Rós, la «Penudria», con i suoi tornanti), la cantonale da Ponte Tresa per Caslano a Magliaso e, a Caslano, il paese dalla stazione al lago e Via Torrazza lungo la riva fino alla Torrazza. Il resto dell'area viene dai dati ufficiali di swisstopo e del Cantone Ticino.

## Come si gioca

- **Livello:** `magliaso_pura`.
- **Punti di partenza:**
  - `spawn_magliaso` (predefinito, all'incrocio di Magliaso), `spawn_mid` (a metà salita) e `spawn_pura` (in cima alla cantonale). Qui le auto partono nella corsia di marcia, rivolte verso Pura.
  - Un punto in ogni paese dell'area: `spawn_agno`, `spawn_caslano`, `spawn_bioggio`, `spawn_gravesano`, `spawn_magliaso_paese`, `spawn_manno`, `spawn_pura_paese`, `spawn_aranno`, `spawn_arosio`, `spawn_astano`, `spawn_banco`, `spawn_bedigliora`, `spawn_bosco_luganese`, `spawn_breno`, `spawn_cademario`, `spawn_cassina_d_agno`, `spawn_castelrotto`, `spawn_cimo`, `spawn_miglieglia`, `spawn_molinazzo_di_monteggio`, `spawn_monteggio`, `spawn_neggio`, `spawn_novaggio`, `spawn_ponte_tresa`, `spawn_purasca`, `spawn_sessa` e `spawn_vernate`. Per Curio c'è `spawn_pura`, a 160 m dal paese.
- **Tutto è guidabile:** ogni strada e ogni sentiero dell'area ha una superficie solida, compresi mulattiere, scalinate e sentieri nel bosco.
- **Traffico IA:** la rete stradale per l'IA copre tutte le strade carrozzabili, con i sensi unici, le rotonde e le carreggiate separate; le strade chiuse al traffico sono evitate.

## Cosa c'è e da dove viene

| Elemento | Fonte | Precisione |
|---|---|---|
| Terreno 12,3 × 12,3 km, maglia 1,5 m | swissALTI3D 0,5 m e 2 m (LiDAR); Copernicus GLO-30 sul lato italiano | quota ±0,3 m nell'area |
| Strade e sentieri (circa 228 km di strade, 337 km di sentieri) | swissTLM3D (assi, classi, pavimentazione, ponti), misurazione ufficiale TI (limiti delle carreggiate) | profilo liscio calcolato su tutta la rete insieme: le quote coincidono agli incroci, le pendenze sono quelle reali |
| Ponti (167) | swissTLM3D, controllati uno per uno sul profilo e nelle viste | impalcato, parapetti e piloni; le strade sotto i ponti restano |
| Edifici (12 792) | swissBUILDINGS3D 3.0 (LOD2, tetti compresi), gli edifici della misurazione ufficiale costruiti dopo il rilievo 3D, Registro federale degli edifici (uso, epoca, piani), negozi di OpenStreetMap | ±0,3–0,5 m; facciate con finestre, persiane o tapparelle, porte, portoni, garage, vetrine, balconi, zoccoli e comignoli disegnati dalla pipeline (nessuna foto), casa per casa nei nuclei; tono dell'intonaco e colore delle persiane misurati nelle panoramiche Street View; coperture in coppi, tegole, piode, lamiera o piane |
| Muri | misurazione ufficiale (muri) + muri di sostegno della cantonale ricavati da DTM e foto | lungo la cantonale l'altezza visibile è misurata nelle foto; texture originali di pietra, calcestruzzo e intonaco, il materiale visto nelle panoramiche dove è chiaro |
| Guardrail, ringhiere e recinzioni della cantonale | voto multi-vista sulla segmentazione delle foto, LiDAR dove disponibile | posizione ±0,3 m |
| Guardrail del resto della rete (v2.2) | panoramiche Street View di tutta l'area segmentate lungo i bordi di ogni strada | dove le panoramiche li mostrano, sul bordo della strada costruita |
| Fermate dei bus (v2.2) | OpenStreetMap | palo, cartello, orario e, dove registrata, pensilina |
| Segnaletica della cantonale | ortofoto 10 cm (tratteggi 3 m / 6 m, strisce, zebre gialle), verificata nelle foto | stato di ottobre 2022 (vedi sotto) |
| Lampioni, pali e cartelli, delineatori, arredo urbano della cantonale | triangolati dalle foto con le pose calibrate | ±0,3–0,5 m; targhe nella forma e nel colore misurati nelle foto (senza l'immagine del cartello) |
| Alberi, siepi e arbusti (circa 240 000) | modello di superficie swissSURFACE3D (posizione, altezza e chioma di ogni albero), ortofoto | tutti entro 30 m dalle strade e 5 m dai sentieri, più radi oltre (v2.3: prima 150 m); specie approssimate con modelli vanilla; nessun tronco sulla carreggiata né a meno di 1 m dal bordo delle strade (0,5 m dei sentieri), nessuna chioma nella sagoma libera (4,50 m sopra le carreggiate, 2,50 m sopra marciapiedi e sentieri), ogni pianta sul suolo |
| Segnaletica orizzontale del resto della rete | ortofoto SWISSIMAGE 10 cm (2024): linee tracciate lungo ogni strada, segni vettorializzati | solo la vernice visibile nell'ortofoto; tratti coperti da alberi o ombra ricostruiti solo tra due parti viste (fino a 60 m) |
| Sensi unici, cartelli STOP e precedenza, panchine e cestini del resto della rete | OpenStreetMap; rotonde e carreggiate separate da swissTLM3D | posizione di OSM, cartelli sul bordo della strada che li ha |
| Ferrovia (FLP e FFS) | swissTLM3D (assi, quote, scartamento, ponti) | binari a scartamento reale alla quota di swissTLM3D, mai sotto il terreno, a filo della strada nei passaggi a livello; niente linea di contatto, niente binari sotto il parcheggio della stazione di Ponte Tresa |
| Lago di Lugano, paesaggio lontano | swissALTI3D, Copernicus GLO-30 | — |

## Stato del 2022 riprodotto sulla cantonale

Le foto di ottobre 2022 sono più recenti dell'ortofoto e della misurazione ufficiale. Dove le fonti non concordano, il livello segue le foto:

- **Nessuna segnaletica** dove la strada era in rifacimento o non era segnata: s ≈ 1,23–1,27 km, 1,52–1,82 km e 3,64–3,72 km. Nel cantiere l'asfalto nuovo è più scuro.
- **Bande rosse** ai due bordi nel tratto s ≈ 2,29–2,44 km.
- **Incrocio di Magliaso:** l'incrocio era stato ricostruito, quindi le due isole pedonali e l'isola dipinta del rilievo sono state rimosse, e la mezzeria segue la posizione visibile nelle foto.

## Versione 2.3

- **Cantonale a Magliaso:** all'incrocio con Via Piscicoltura la carreggiata verso Pura non scende più verso la strada più bassa al di là del muro (prima, per circa 60 m, era fino a 2,2 m sotto il terreno reale sul bordo).
- **Boschi più leggeri:** tutti gli alberi restano entro 30 m dalle strade e 5 m dai sentieri, più lontano il bosco è diradato; i versanti con molti tornanti, come il passo sopra Gravesano, pesano meno sul gioco.

## Versione 2.2

- **Nuove strade:** il passo sopra Gravesano fino ad Arosio (Stradón da Rós, la «Penudria»), la cantonale Ponte Tresa – Caslano – Magliaso e Via Torrazza a Caslano finivano sul bordo della mappa (oltre c'era solo il terreno). Ora sono strade vere, con superficie, segnaletica, guardrail e un corridoio di 100 m con edifici, alberi e muri, riviste su Street View come il resto della mappa.
- **Edifici con le facciate:** finestre con persiane, tapparelle o serramenti moderni, porte, portoni, garage, vetrine, balconi, zoccoli e comignoli su ogni edificio, distribuiti per piani e campate secondo uso, epoca e piani del Registro federale degli edifici. Nei nuclei ogni casa ha le sue facciate, i suoi piani, la sua porta e il suo tono; i piani partono dal fronte strada anche sui pendii. Coperture in coppi, tegole, piode, lamiera o tetto piano. Tutte le texture sono disegnate: nessuna foto.
- **Colori dalle foto:** il tono dell'intonaco e il colore delle persiane vengono dalle panoramiche Street View dove l'edificio è visto (solo i valori, corretti per l'ombra).
- **Edifici mancanti** (costruiti dopo il rilievo 3D) aggiunti dalla misurazione ufficiale; demoliti tolti.
- **Guardrail su tutta la rete** dove le panoramiche li mostrano, sul bordo della strada.
- **Muri** con texture originali di pietra, calcestruzzo e intonaco.
- **Fermate dei bus** di OpenStreetMap.
- **Strade più guidabili:** superfici continue tra carreggiata, marciapiedi e piazzali e agli incroci, verificate con una prova di guida virtuale su tutta la rete.

## Versione 2.1

- **Segnaletica orizzontale su tutta la rete**, rilevata nell'ortofoto SWISSIMAGE 10 cm del 2024: linee di mezzeria, di corsia e di bordo (tratteggiate o continue, nella posizione e con il ritmo misurati), strisce pedonali gialle, linee d'arresto, frecce e zebrature. Si dipinge solo ciò che l'ortofoto mostra; una linea nascosta da alberi od ombra continua solo se si vede ai due lati (fino a 60 m).
- **Alberi fuori dalla sagoma libera delle strade:** nessuna chioma sotto 4,50 m sopra le carreggiate né sotto 2,50 m sopra marciapiedi, piazzali e sentieri (0,3 m di tolleranza sul bordo). Gli alberi sono stati spostati di al massimo 3 m o hanno un modello più stretto della stessa specie; pochissimi sono stati tolti. Ogni pianta poggia sul suolo e nessun tronco sta dentro muri o edifici.
- **Traffico IA:** sensi unici (OpenStreetMap), rotonde in senso antiorario e carreggiate separate (swissTLM3D); le strade con divieto generale di circolazione sono evitate.
- **Cartelli STOP e precedenza** di OpenStreetMap (pannelli svizzeri disegnati, non fotografati), **panchine e cestini**.
- **Ferrovia:** binari della FLP Lugano–Ponte Tresa e delle FFS, con passaggi a livello e ponti.
- **La Tresa a Ponte Tresa** ha l'acqua sotto il ponte di confine, fino alla traversa.

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
- v2.2: una prova di guida virtuale percorre tutte le strade e i sentieri sulle superfici del livello e segnala gradini, ruote staccate, colpi e buchi; la mappa è stata confrontata con le panoramiche Street View strada per strada (copertura, edifici misurati, guardrail e muri visti, luoghi confrontati foto/mappa).
- Le pose delle 366 panoramiche della cantonale sono state stimate sull'ortofoto 10 cm con precisione di circa 0,3 m. La verifica della cantonale confronta le foto con le schermate del gioco nella stessa posa. Le cifre sono nel file `VERIFICA.md` e si riferiscono alla geometria della v1.0.
- Tra 1,28 e 1,36 km della cantonale non esistono panoramiche: lì il livello si basa solo sui dati swisstopo e sulla misurazione ufficiale.

## Limiti noti

- Sul lato italiano ci sono solo il terreno e il paesaggio, senza strade, edifici e alberi.
- Le gallerie non sono costruite.
- I sensi unici vengono da OpenStreetMap: dove OSM non li registra, l'IA percorre la strada nei due sensi.
- Segnaletica verticale (limiti, località, direzioni) e linea di contatto della ferrovia ci sono solo dove esiste una fonte (le foto della cantonale Magliaso–Pura, i cartelli di OpenStreetMap); i guardrail dove le panoramiche Street View li mostrano.
- Le facciate sono ricostruite dai dati (uso, epoca, piani) e dai colori visti nelle foto: numero e posizione delle finestre, balconi e portici sono plausibili ma non copiati uno per uno.
- Vedeggio, Magliasina e la Tresa a valle della traversa non hanno acqua.

## Fonti e licenze

- © swisstopo: swissALTI3D, SWISSIMAGE, swissBUILDINGS3D, swissSURFACE3D, swissTLM3D, swissNAMES3D.
- Misurazione ufficiale: Ufficio del catasto e dei riordini fondiari, Cantone Ticino.
- © OpenStreetMap contributors (ODbL 1.0), estratto del 28.9.2026 (completato il 30.9.2026 nei corridoi della v2.2): sensi unici, cartelli STOP e precedenza, panchine e cestini (v2.1); fermate dei bus, negozi ed esercizi (v2.2).
- Registro federale degli edifici e delle abitazioni (Ufficio federale di statistica): uso, epoca e piani degli edifici (v2.2).
- Copernicus DEM GLO-30: © DLR e.V. 2010-2014 e © Airbus Defence and Space GmbH 2014-2018, forniti nell'ambito di COPERNICUS da Unione Europea ed ESA.
- Le panoramiche Google Street View sono servite solo come riferimento visivo (pose, misure, confronti): la mod non contiene immagini Street View.
- Modelli 3D di alberi, lampioni e arredo: asset vanilla di BeamNG (East Coast USA, Italy), referenziati e non copiati.
