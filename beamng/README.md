# Malcantone (Strada Cantonale Magliaso → Pura e dintorni): pipeline della mappa BeamNG

Questa pipeline ricostruisce in scala 1:1 il Malcantone (Ticino) come livello BeamNG.drive (`magliaso_pura`, versione 0.39). Il livello copre circa 51 km² tra Ponte Tresa, Magliaso, Agno, Bioggio, Manno, Gravesano, Cademario, Novaggio, Astano e Sessa. Al centro c'è la Strada Cantonale da Magliaso a Pura delle versioni 1.x; a est c'è la cantonale da Magliaso a Gravesano, lungo il lago fino ad Agno e poi ai piedi dei monti per Bioggio e Manno. Il lavoro combina due tipi di fonte:

- le **366 panoramiche Street View** del dataset lungo la cantonale (`C:\Users\michi\Documents\magliasinaNG`: 363 di ottobre 2022, 3 del 2013/2014), usate per le pose delle camere, gli oggetti, la segnaletica, le texture e la validazione;
- i **dati ufficiali swisstopo e della misurazione ufficiale ticinese**, usati come riferimento metrico per tutta l'area: terreno, rete stradale (swissTLM3D), carreggiate, edifici, muri e alberi.

## Contenuto di questa cartella

| Cartella | Cosa c'è |
|---|---|
| `pipeline/` | tutti gli script, dal download dei dati alla verifica; `config.py` contiene i percorsi |
| `verifica/` | `VERIFICA.md` (confronto con tutte le 1464 viste), il grafico della concordanza lungo il percorso, le metriche per vista (`metrics_final.json`, e `metrics_full1.json` prima dell'ultimo ciclo di correzione) |
| `dati/` | risultati di calcolo leggeri, per ricostruire il livello senza rifare i passi lunghi: pose calibrate delle panoramiche (`poses.json`), asse stradale, segnaletica e suo stato 2022, guardrail, muri di sostegno e altezze dei muri, recinzioni, lampioni, pali e cartelli, arredo, alberi e arbusti; per la v2.0 i ponti con le correzioni manuali (`ponti.json`) e la cantonale Magliaso–Gravesano (`cantonale_gravesano.json`); per la v2.2 le strade dei nuovi corridoi (`strade_extra_v22.json`) |

La **mod pronta** è nella [release v2.4](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.4), che il workflow `.github/workflows/release_v2.4.yml` costruisce da zero su un server GitHub: scarica i dati, costruisce il livello, lo controlla con `check_level.py` e `drive_test.py` e lo pubblica. È costruita con `MAGLIASO_NO_PHOTO_TEXTURES=1`, quindi non contiene immagini Street View: facciate, tetti e muri hanno texture originali disegnate dalla pipeline nei colori misurati e le targhe sono a tinta unita. Gli oggetti della cantonale ricavati dalle foto (segnaletica, lampioni, pali, cartelli, arredo) vengono presi dalla release v1.1 e appoggiati sulle nuove superfici (`carryover.py`).

Le versioni precedenti restano disponibili:
- **v1.0**: solo il corridoio della cantonale.
- **v1.1**: la cantonale con le strade lisce e la carreggiata sgombra (`patch_release.py`, `.github/workflows/release_v1.1.yml`).
- **v2.0**: l'area di 51 km² con tutta la rete stradale, i ponti e la cantonale fino a Gravesano (`release_v2.0.yml`).
- **v2.1**: segnaletica su tutta la rete, alberi fuori dalla sagoma libera, traffico IA, ferrovia (`release_v2.1.yml`).
- **v2.2**: revisione su Street View, facciate, guardrail di tutta la rete, strade nuove verso Arosio e Caslano (`release_v2.2.yml`).

Le metriche di `verifica/VERIFICA.md` riguardano la cantonale nella versione locale con le texture fotografiche e la geometria della v1.0. La verifica dell'ultima versione è in `verifica/check_level.json` (controlli automatici su tutta la mappa), `verifica/drive_test.json` (prova di guida virtuale) e `verifica/REVISIONE.md` (revisione su Street View); i profili dei ponti in `verifica/ponti/`.

## Versione 2.0: area, rete stradale, ponti

- **Area** (`area.py`, `config.BOUNDARY`): unione di tre parti; il terreno è un blocco di 8192 × 8192 campioni a 1,5 m (12,3 km di lato).
  - Il quadrilatero dei quattro punti indicati, allargato di 150 m.
  - Il corridoio della cantonale Magliaso–Pura.
  - La cantonale Magliaso–Agno–Bioggio–Manno–Gravesano, con 150 m attorno e tutta la fascia tra la strada e il lato est del quadrilatero. `strade_extra.py` la estrae da swissTLM3D (percorso più breve sulle strade del Cantone) e la salva in `dati/cantonale_gravesano.json`: così l'area non dipende da swissTLM3D, che si scarica in base all'area.
  - (v2.2) Un corridoio di 100 m attorno alle strade che uscivano dalla mappa: il passo sopra Gravesano fino ad Arosio (Stradón da Rós, la «Penudria»), la cantonale Ponte Tresa–Caslano–Magliaso e, a Caslano, il paese dalla stazione al lago e Via Torrazza fino alla Torrazza. `strade_extra.py` le calcola come la cantonale di Gravesano e le salva in `dati/strade_extra_v22.json`; una sacca che un corridoio chiude contro il resto dell'area ne fa parte.
- **Rete** (`network.py`): tutte le linee di swissTLM3D nell'area, cioè strade, strade forestali, sentieri, mulattiere, scalinate e ponti; le gallerie sono escluse. Le linee sono spezzate agli incroci, ricentrate sulle carreggiate della misurazione ufficiale e campionate ogni 2 m.
- **Profilo** (`network_surface.py`): un unico sistema ai minimi quadrati su tutte le stazioni della rete.
  - Adattamento al DTM, liscezza per classe di strada, quota unica agli incroci, pesi di Tukey contro le anomalie del rilievo.
  - La cantonale è vincolata alla superficie della v1.1.
  - Sui ponti conta il profilo tra le spalle, salvo i tombini, dove swissTLM3D e il DTM stanno sul terreno.
- **Superfici** (`network_mesh.py`): i poligoni della misurazione ufficiale (carreggiate, marciapiedi, piazzali) e una striscia lungo le linee senza rilievo.
  - Le quote vengono dalla proiezione sulle linee entro 6 m dalla carreggiata; i piazzali lontani dalle linee seguono il DTM.
  - Nessuna superficie scende più di 0,75 m sotto il terreno nudo più basso entro 1 m.
  - Il terreno viene scavato sotto le mesh costruite (`road_mesh.carve_window`): ogni vertice i cui triangoli toccano una mesh scende 10 cm sotto la faccia più bassa nel quadrato di un passo di griglia attorno a sé, così il terreno non sporge neanche tra un vertice e l'altro.
- **Muri** (`walls.py`): ogni vertice del terreno i cui triangoli toccano un muro scende alla base del muro, così la griglia di 1,5 m non fa sporgere il terreno davanti alla faccia. Dietro i muri di sostegno una mesh sulla griglia del terreno (`build_backfill`) rimette il suolo al suo livello, nel materiale del terreno lì intorno. Un muro del rilievo che sporge più di 30 cm sopra una carreggiata, o sopra la fascia di passaggio attorno a una linea, viene tagliato lì (`drive_free`, `above_way`): il rilievo e swissTLM3D non sempre coincidono, e un muro disegnato in mezzo a una strada la chiuderebbe.
- **Edifici** (`buildings_mesh.py`): dove un edificio sta su una strada o un sentiero della rete (sottoportici, la tettoia della dogana di Ponte Tresa, un vicolo sotto un campanile, una linea di swissTLM3D disegnata dentro una casa) si taglia un passaggio alto 4,2 m sulle strade e 3 m sui sentieri, chiuso da soffitto e pareti (`passages`); sotto un tetto più basso il passaggio si ferma sotto il tetto, se restano almeno 3 m (2,2 m sui sentieri).
- **Ponti** (`bridges.py`): impalcato, parapetti, piloni (mai su una strada o un sentiero), terreno abbassato sotto la soletta. Le correzioni manuali sono in `dati/ponti.json` (`z0`, `z1`, `profile` `straight` o `tlm`, `type`, `skip`); `tlm` segue la linea 3D di swissTLM3D, per le passerelle con le scale sopra una strada. Le schede di controllo si fanno con `bridge_report.py`.
- **Verifica** (`check_level.py`, `review_map.py`, `render3d.py`):
  - controlli automatici su tutta la mappa, con i luoghi dei problemi; tra questi gli ostacoli sulla carreggiata, cercati lungo ogni strada e sentiero a 0,5 e 1,6 m d'altezza contro tutte le mesh solide, e i buchi nel terreno;
  - screenshot 3D del livello senza il gioco (three.js in Chromium), con panoramica dall'alto, ponti, strade, sentieri, paesi e punti segnalati.

## Versione 2.1: rifinitura sulla realtà

Revisione del livello v2.0 confrontato con fonti reali: l'ortofoto SWISSIMAGE 10 cm del 2024 per tutta la rete, gli attributi di swissTLM3D che la v2.0 non usava, OpenStreetMap, i controlli automatici su tutta la mappa e screenshot 3D. Tutto quello che viene aggiunto ha una fonte: nessuna linea, cartello od oggetto è messo perché "di solito c'è".

- **Vegetazione nella sagoma libera delle strade** (`canopy.py`): non solo il tronco ma tutta la chioma di ogni albero resta fuori dalla sagoma, 4,50 m sopra le carreggiate e 2,50 m sopra marciapiedi, piazzali e sentieri. Un albero la cui chioma entra nella sagoma viene spostato di al massimo 3 m su terreno libero, oppure prende il modello più stretto della sua specie; se non basta la scala viene ridotta e, come ultima possibilità, l'albero viene tolto. Ogni pianta poggia sul suolo sotto il tronco (terreno o terrapieno dietro i muri) e nessun tronco sta dentro muri, edifici, parapetti o recinzioni. Il passo lavora sul livello già scritto, sia nella costruzione sia sul livello pubblicato, e `check_level.py` misura le stesse regole.
- **Segnaletica orizzontale di tutta la rete** (`network_markings.py`, `ortho10.py`, `markings_net.py`): linee di mezzeria, di corsia e di bordo, tratteggiate o continue, rilevate nell'ortofoto 10 cm lungo ogni strada, più strisce pedonali gialle, linee d'arresto, frecce e zebrature. Nei tratti coperti da alberi o in ombra una linea vista ai due lati continua fino a 60 m; i tratti più lunghi restano senza vernice. Il giallo (anche sbiadito) è tarato sulle strisce pedonali registrate in OpenStreetMap e va solo su asfalto grigio; le macchie larghe con i finestrini e l'ombra di un veicolo e i riflessi sulle auto scure sono scartati. Il risultato è in `dati/network_markings.json.gz`. La cantonale Magliaso–Pura tiene la sua segnaletica verificata nelle foto.
- **Traffico IA**: sensi unici di OpenStreetMap; rotonde (in senso antiorario) e carreggiate separate (si tiene la destra) da swissTLM3D; le strade con divieto generale di circolazione hanno percorribilità 0,1.
- **Dati OpenStreetMap fissati** in `dati/osm_area.json.gz` e `dati/osm_communes.json.gz` (estratto Overpass del 28.9.2026, completato il 30.9.2026 con le strisce dei corridoi della v2.2, © OpenStreetMap contributors, licenza ODbL 1.0): la release usa questi, così non cambia con OSM e non dipende dai server Overpass; `download_osm.py --pin` li aggiorna.
- **Cartelli e arredo di OpenStreetMap** (`props_osm.py`): STOP e precedenza dove OSM li registra, con il pannello disegnato (non fotografato), sul bordo destro della strada che li ha; panchine, cestini e lampioni con i modelli già usati dal livello.
- **Ferrovia** (`railway.py`): i binari della FLP (scartamento metrico) e delle FFS di swissTLM3D, con traversine, rotaie, massicciata, passaggi a livello a filo della strada e ponti. I binari stanno alla quota reale di swissTLM3D: dove il terreno del livello è più alto viene scavata una trincea (lungo il lago ad Agno, sotto la scarpata della cantonale), dove è più basso il binario sta su un terrapieno di massicciata; quelli sotto il parcheggio della stazione di Ponte Tresa non sono costruiti, come le gallerie. La linea di contatto non è costruita.
- **La Tresa a Ponte Tresa** (`water.py`): la diga del modello del lago è alla traversa, 420 m a valle, e non più alla foce. Il tratto al livello del lago, sotto il ponte di confine, ha l'acqua.
- **Zone, strade e registro** (`zone_report.py`): `verifica/ZONE.md` (stato per comune), `verifica/STRADE.md` (ogni strada della rete con lo stato di ogni aspetto) e `verifica/REGISTRO.md` (differenze trovate, azione, stato).

## Versione 2.4: case da ogni lato, rotonda di Magliaso, superfici OSM e più realismo

- **Verso delle pareti** (`buildings_mesh.py`: `orient`, `undecided_walls`, `soffits`): il gioco disegna una
  faccia sola. Il verso di ogni parete si decide con due raggi quasi orizzontali che partono appena davanti
  alla parete: se attraversano le superfici dell'edificio un numero dispari di volte la parete è girata
  verso l'interno e viene invertita (prima si guardava il centro dell'edificio, sbagliato negli edifici a L,
  a U, a corte e nelle file di case). Dove i raggi non decidono (gusci aperti del rilievo 3D) la parete ha
  due facce. Sotto ogni falda del tetto che sporge dalla pianta c'è il sottotetto, 3 cm sotto la falda.
  `bng.MeshBuilder.orient_closed` gira verso fuori i solidi di muri, recinzioni, guardrail, pali e binari.
  `render3d.py` disegna una faccia sola come il gioco (doppia solo per i materiali `doubleSided`).
  Nuovo controllo `building_walls_inward_share` in `check_level.py`: un punto 0,3 m davanti alla parete
  dentro una pianta e quello dietro fuori = parete girata verso l'interno.
- **Muri che le panoramiche vedono come pavimentazione** (`markings_state.py --walls`, `walls.py`): i muri della
  misurazione su strade, marciapiedi e isole dove la segmentazione delle panoramiche (voto multi-vista,
  `band_votes`) vede strada o marciapiede per almeno il 70 % di almeno 30 voti sono portati a filo della
  pavimentazione, o tolti se attorno il terreno è in piano. È il blocco che sporgeva all'incrocio della rotonda
  di Magliaso. I piccoli pezzi di marciapiede sulle isole tolte nel 2022 sono carreggiata
  (`removed_sidewalks`).
- **Superfici da OpenStreetMap** (`osm_surface.py`, `network_mesh.Network.assign_surfaces`): ogni linea di
  swissTLM3D prende la categoria (asfalto, ghiaia, terra, cubetti, ciottoli) delle vie OSM che le corrono
  accanto, dove sono etichettate (`surface`, per le carrareccie `tracktype`), altrimenti la sua (`BELAGSART`).
  I poligoni delle strade della misurazione sono divisi tra le linee e le vie che contengono, su una griglia
  di 1 m (vince la via più vicina in rapporto alla sua mezza larghezza; pezzi sotto 25 m² uniti al resto).
  Le aree OSM con una superficie (parcheggi, piazze) la danno ai piazzali sotto di loro. Materiali per
  carreggiata, piazzale e sentiero con i tipi di fondo GRAVEL, DIRT e COBBLESTONE; texture procedurali
  (`surface_textures.py`) con la tinta mediana dell'ortofoto 10 cm lungo le vie OSM di quella superficie.
  Le faccette di un poligono (`road_mesh.split_by_surface`) si calcolano sul suo pezzo intero e poi si
  tagliano nelle zone di superficie, così asfalto e ghiaia dello stesso poligono stanno sulle stesse quote; un
  pezzetto di faccetta sotto 3 m² chiuso dentro un'altra passa a quella (`MIN_PIECE`), non uno sul bordo del
  blocco di 128 m, che nel blocco accanto continua alla sua quota.
- **Erba e fiori** (`groundcover.py`): oggetto GroundCover (scritto come nei livelli del gioco, un elemento di
  `Types` per tipo) con ciuffi a billboard (2 triangoli) da un atlante disegnato, su `Grass` e `GardenGrass`,
  40 000 elementi entro 50 m; i prati entro un quadrato di terreno dalle strade hanno un livello di terreno
  gemello senza erba (`terrain.VERGE`), così i ciuffi non attraversano le strade.
- **Palme** (`palms.py`): modello disegnato di Trachycarpus; un quarto degli alberi misurati alti 3-9 m con
  chioma fino a 6 m nei giardini entro 400 m dal lago e sotto 320 m diventano palme (stima: la specie non si
  misura).
- **Vigneti** (`vineyards.py`): filari ogni 2,2 m nei vigneti della misurazione entro 150 m dalla rete, nella
  direzione delle righe dell'ortofoto (tensore di struttura, misurata una volta: `dati/vineyard_rows.json`) o
  lungo le curve di livello; mesh a pezzi di 128 m con un livello di dettaglio che le toglie oltre circa un
  chilometro.
- **Fiumi** (`rivers.py`): superficie d'acqua semitrasparente sulle superfici `corso_acqua` larghe almeno 2,5 m,
  all'altezza del fondo più basso entro 3 m + 12 cm, anche sotto i ponti, non sui guadi né sul lago. Il
  terreno (griglia di 1,5 m, più liscia del letto) scende 35 cm sotto l'acqua dentro quelle superfici, tranne
  dove sta più di 1,5 m sopra l'acqua (le sponde ripide delle gole che la superficie rilevata comprende) e
  entro 2,5 m dalle strade e dai sentieri a livello del terreno: a un guado le ruote di un'auto su un sentiero
  largo 1 m stanno sul terreno accanto, che resta com'era.
- **Materiali**: mappe di ambient occlusion per intonaco, zoccolo e tetti (`bld_textures.py`), pareti più scure
  verso terra nei colori dei vertici (`buildings_mesh.GROUND_AO`); luce dei 68 lampioni triangolati
  (`props.py`, senza ombre); foschia 1,3e-4 fino a 1000 m (prima 1,1e-4 fino a 1200 m).

## Versione 2.3: correzioni dopo le prime prove nel gioco

- **Muri tra due strade a quote diverse** (`surface_fit.py`, `cross_bands`): una fascia ripida del DTM fra due
  superfici è un muro quando attorno ha celle sia più alte sia più basse di lei; il confronto ora si fa con
  il punto medio tra il dato più alto e il più basso della fascia vicina e non con la mediana, che per un
  muro largo e sfumato cade dalla parte della cella stessa. A Magliaso il muro tra la Strada Cantonale e Via
  Piscicoltura, più in basso, era preso per un dosso: le due strade diventavano una superficie sola e la
  cantonale scendeva fino a 2,2 m sotto il terreno sul bordo per circa 60 m. Ora ogni strada ha la sua
  superficie (scarto massimo sull'asse della cantonale da 1,70 m a 0,09 m). Lungo il corridoio della
  cantonale cambiano solo 6 fasce, tutte verso il terreno reale.
- **Diradamento del bosco** (`vegetation.py`, `thin`): tutti gli alberi misurati restano entro 30 m dalle
  strade e 5 m dai sentieri (prima 150 m dalle strade); fino a 60 m e 100 m dalla strada il più alto di ogni
  cella di 11 m e 17 m, oltre il più alto di ogni cella di una griglia larga quanto basta per stare sotto
  `CAP`. I versanti attraversati da tornanti, come il passo sopra Gravesano visto dal paese, non sono più
  fitti come il bosco intero e il gioco li disegna più in fretta.

## Versione 2.2: revisione su Street View, facciate, guardrail e guidabilità

Revisione sistematica di tutta la mappa confrontata con Google Street View, usato **solo come riferimento
visivo**: nessuna immagine Street View entra nel livello o nel repository. Dalle foto si prendono solo
misure (tono di un intonaco, colore delle persiane, presenza di un guardrail, materiale di un muro);
tutto quello che si vede viene ridisegnato con texture originali.

- **Nuove strade** (`strade_extra.py`, `area.py`): il passo sopra Gravesano fino ad Arosio, la cantonale Ponte Tresa–Caslano–Magliaso e Via Torrazza finivano sul bordo della mappa; ora sono nella rete con un corridoio di 100 m, e la revisione Street View le copre come il resto (1297 panoramiche in più, 477 scaricate e segmentate).
- **Street View di tutta l'area** (`sv_coverage.py`, `sv_fetch.py`): 19 679 panoramiche elencate (solo i
  metadati, in `dati/sv_coverage.json.gz`), una ogni 20 m di strada scaricata in locale per la revisione
  (7278). `sv_segment.py` le segmenta (Mask2Former, Mapillary Vistas) nella fascia del bordo strada.
- **Revisione foto/mappa** (`sv_review.py`): per ogni luogo, ortofoto, panoramica e mappa renderizzata dalla
  stessa camera; i risultati sono in `dati/qa_review.json` (`qa_log.py`) e, strada per strada, in
  `verifica/REVISIONE.md` (`review_report.py`).
- **Facciate** (`facades.py`, `bld_textures.py`, `buildings_mesh.py`): finestre con persiane, tapparelle o
  serramenti moderni, porte, portoni, garage, vetrine, finestre di chiese e stalle, zoccoli e comignoli su
  ogni edificio, secondo categoria, epoca e piani del Registro federale degli edifici (`download_gwr.py`,
  estratto fissato in `dati/gwr_area.json.gz`). Nei nuclei swissBUILDINGS3D unisce file di case in un
  blocco: le facciate vengono tagliate ai confini delle case della misurazione ufficiale e ogni casa ha il
  suo record, i suoi piani, la sua porta e il suo tono. I piani partono dal terreno del fronte strada.
  Vetrine dove OpenStreetMap registra un negozio, bar o ufficio (`dati/osm_pois.json.gz`). Il tono
  dell'intonaco e il colore delle persiane sono misurati nelle panoramiche (`sv_facades.py` →
  `dati/facade_colors.json`). Coperture in coppi, tegole, piode, lamiera o piane con texture originali.
- **Edifici mancanti** (`missing_buildings.py`): gli edifici della misurazione ufficiale che
  swissBUILDINGS3D non ha (costruiti dopo il rilievo 3D) vengono aggiunti con l'altezza dal modello di
  superficie o dai piani del GWR; quelli demoliti tolti. Elenco in `dati/buildings_diff.json`.
- **Guardrail di tutta la rete** (`sv_guardrails.py` → `dati/guardrails_sv.json`, `guardrail_mesh.py`): i
  bordi di ogni strada proiettati nelle panoramiche segmentate; un guardrail c'è dove la maggioranza delle
  viste lo mostra. Costruito appena fuori dall'ultima faccia della strada, alla quota del bordo.
- **Muri** (`walls.py`, `sv_walls.py` → `dati/wall_materials.json`): texture originali di pietra,
  calcestruzzo e intonaco; il materiale viene dalle panoramiche solo dove le foto sono chiare.
- **Fermate dei bus e cartelli** (`props_osm.py`): le fermate di OSM con palo, cartello giallo, orario e,
  dove c'è, pensilina.
- **Guidabilità** (`network_mesh.py`, `drive_test.py`): le superfici sono continue tra carreggiata,
  marciapiedi e piazzali e agli incroci (il salto viene distribuito su 4 m nel dominio dei gradienti,
  le carreggiate principali restano fisse); la prova di guida virtuale (modello quarter-car, 640 km su
  tutta la rete) misura gradini, ruote staccate, accelerazioni e buchi prima e dopo (`verifica/drive_test_v2.1.json`,
  `verifica/drive_test.json`).
- **Screenshot** del livello per la documentazione (`screenshots.py`, render con le texture del livello).

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
| Rete (v2.0) | `network.py`, `network_surface.py`, `network_mesh.py`, `bridges.py`, `water.py`, `places.py`, `strade_extra.py` | rete stradale e sentieri swissTLM3D, profilo liscio, superfici guidabili, ponti, lago, paesi, cantonale Magliaso–Gravesano |
| Verifica (v2.0) | `check_level.py`, `review_map.py`, `bridge_report.py`, `render3d.py` | controlli su tutta la mappa, screenshot 3D, schede dei ponti |
| Senza il gioco | `prepare_work.py`, `vanilla.py`, `carryover.py`, `ogr_tin.py` | costruzione nel cloud: risultati leggeri da `dati/`, file vanilla e oggetti della cantonale dallo zip della v1.1, lettura dei TIN di swissBUILDINGS3D |
| Street View (v2.2) | `sv_coverage.py`, `sv_fetch.py`, `sv_segment.py`, `sv_facades.py`, `sv_guardrails.py`, `sv_walls.py` | copertura (metadati), panoramiche di revisione in locale, segmentazione della fascia del bordo strada; misure: tono delle facciate, persiane, guardrail, materiale dei muri |
| Edifici (v2.2) | `download_gwr.py`, `missing_buildings.py`, `bld_textures.py`, `facades.py` | registro degli edifici, edifici mancanti e demoliti, texture originali, facciate per casa |
| Revisione (v2.2) | `sv_review.py`, `qa_log.py`, `review_report.py`, `drive_test.py`, `drive_context.py`, `screenshots.py` | confronto foto/mappa dalla stessa camera, registro dei luoghi rivisti, `verifica/REVISIONE.md`, prova di guida virtuale, screenshot |
| Grafica (v2.4) | `osm_surface.py`, `surface_textures.py`, `groundcover.py`, `palms.py`, `vineyards.py`, `rivers.py` | superfici di strade e sentieri da OSM con le loro texture, erba e fiori, palme, filari dei vigneti, acqua nei fiumi |
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

Dalla v2.2 il livello non contiene mai immagini tratte da Street View: è il comportamento predefinito
(`config.NO_PHOTO`). Solo `MAGLIASO_NO_PHOTO_TEXTURES=0` rimette le texture fotografiche delle versioni 1.x
locali, per studio privato; quella versione non va distribuita.

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
- Registro federale degli edifici e delle abitazioni (REA/GWR, Ufficio federale di statistica): categoria, epoca e piani degli edifici (v2.2).
- © OpenStreetMap contributors (ODbL): sensi unici, cartelli, fermate, arredo e, dalla v2.2, negozi ed esercizi (`dati/osm_pois.json.gz`).
- Google Street View: solo riferimento visivo per pose, oggetti, colori, guardrail, materiali e verifica. Il repository e la release non contengono immagini Street View; dalla v2.2 le texture fotografiche non si usano nemmeno nelle costruzioni locali (salvo `MAGLIASO_NO_PHOTO_TEXTURES=0`, per studio privato).
