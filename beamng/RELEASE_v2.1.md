Mappa BeamNG.drive (0.39) del **Malcantone**, versione 2.1: il livello v2.0 rivisto sulla realtà. Stessa area (circa 51 km² tra Ponte Tresa, Agno, Bioggio, Manno, Gravesano, Cademario, Novaggio, Astano e Sessa, scala 1:1), con quello che nella v2.0 mancava o non corrispondeva alle fonti reali.

**Installazione:** copiare `magliaso_pura_v2.1.zip` in `Documents/BeamNG.drive/current/mods/` (o installarlo dal gestore delle mod) e togliere la v2.0: il livello si chiama sempre `magliaso_pura`.

## Novità della v2.1

- **Segnaletica orizzontale su tutta la rete.** Fino alla v2.0 solo la cantonale Magliaso–Pura era segnata. Ora le linee di mezzeria, di corsia e di bordo, tratteggiate o continue, sono rilevate nell'ortofoto SWISSIMAGE 10 cm del 2024 lungo ogni strada, con il loro ritmo e la loro posizione, insieme a strisce pedonali gialle, linee d'arresto, frecce, zebrature e zig-zag delle fermate: 55 km di linee e circa 5200 segni. Si dipinge solo ciò che l'ortofoto mostra: le strade senza segnaletica restano senza.
- **Alberi fuori dalla sagoma libera delle strade.** Nella v2.0 3733 alberi avevano la chioma nella sagoma libera di una strada, molti all'altezza di un'auto sopra la corsia. Ora le chiome restano fuori dalla sagoma libera (0,3 m di tolleranza sul bordo): 4,50 m sopra le carreggiate, 2,50 m sopra marciapiedi, piazzali e sentieri. Gli alberi sono stati spostati di al massimo 3 m o sostituiti con un modello più stretto della stessa specie; pochissimi sono stati tolti. Ogni albero e arbusto poggia sul suolo (nella v2.0 14 430 erano sospesi, soprattutto lungo le strade scavate nel terreno) e i tronchi non attraversano più muri o edifici (erano 144, ne resta 1).
- **Traffico IA più realistico.** 154 strade a senso unico: sensi unici di OpenStreetMap, rotonde percorse in senso antiorario e carreggiate separate (swissTLM3D). Le 28 strade con divieto generale di circolazione sono evitate.
- **35 cartelli STOP e 57 di precedenza** dove OpenStreetMap li registra, sul bordo della strada che li ha, con il pannello svizzero disegnato (non fotografato). **128 panchine e 14 cestini** di OpenStreetMap con i modelli già usati dal livello.
- **Ferrovia.** I binari della FLP Lugano–Ponte Tresa (scartamento metrico) e quelli delle FFS vicino a Manno, alla loro quota reale: traversine, rotaie, massicciata, passaggi a livello a filo della strada, binari nei piazzali, ponti.
- **La Tresa a Ponte Tresa.** Sotto il ponte di confine ora scorre l'acqua. Nella v2.0 il fiume era asciutto fino alla traversa, perché il lago era chiuso alla foce.
- **Documentazione della verifica:** stato per comune (`beamng/verifica/ZONE.md`), elenco di tutte le strade con lo stato di ogni aspetto (`STRADE.md`), registro delle differenze trovate (`REGISTRO.md`).

## Verifica

Il livello è controllato automaticamente su tutta la mappa (`check_level.py`, risultati in `beamng/verifica/check_level.json`). Ai controlli della v2.0 si aggiungono le chiome nella sagoma delle strade, i tronchi dentro gli oggetti solidi e le piante sospese o interrate.

## Limiti noti

- La segnaletica verticale (limiti di velocità, cartelli di località e di direzione), i guardrail e la linea di contatto della ferrovia sono verificati e costruiti solo dove esistono fonti: la cantonale Magliaso–Pura (foto) e i cartelli registrati in OpenStreetMap.
- La segnaletica nei tratti coperti da alberi o in ombra nell'ortofoto è ricostruita solo dove la stessa linea si vede ai due lati (fino a 60 m). I segni sono vettorializzati dall'ortofoto: hanno contorni un po' seghettati, qualche cordolo chiaro o riflesso è preso per vernice e qualche freccia o scritta lontana da altre linee manca.
- Vedeggio, Magliasina e la Tresa a valle della traversa non hanno acqua. I binari della stazione di Ponte Tresa sotto il parcheggio di Piazzale della Stazione non sono costruiti.
- Sul lato italiano ci sono solo il terreno e il paesaggio; le gallerie non sono costruite.
- Il livello non è stato provato nel gioco durante questa revisione: segnalate eventuali problemi.

Fonti: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); misurazione ufficiale del Cantone Ticino (geodienste.ch); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA). La mod non contiene immagini Street View.
