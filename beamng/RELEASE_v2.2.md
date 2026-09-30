Mappa BeamNG.drive (0.39) del **Malcantone**, versione 2.2: la mappa v2.1 rivista sistematicamente su Google Street View, con le facciate degli edifici, i guardrail di tutta la rete e le strade rese continue agli incroci. Circa 52 km² tra Ponte Tresa, Caslano, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano e Sessa, scala 1:1.

**Installazione:** copiare `magliaso_pura_v2.2.zip` in `Documents/BeamNG.drive/current/mods/` (o installarlo dal gestore delle mod) e togliere le versioni precedenti: il livello si chiama sempre `magliaso_pura`.

## Novità della v2.2

- **Strade nuove.** Il passo sopra Gravesano fino ad Arosio (Stradón da Rós, la «Penudria», con i suoi tornanti), la cantonale Ponte Tresa – Caslano – Magliaso e Via Torrazza a Caslano finivano sul bordo della mappa: oltre c'era solo il terreno. Ora sono strade vere (7,2 km in più) con un corridoio di 100 m di edifici, alberi e muri, riviste su Street View come il resto.
- **Edifici con le facciate.** Fino alla v2.1 ogni edificio era un volume intonacato senza aperture. Ora gli edifici hanno in tutto 165 533 aperture (finestre con persiane, tapparelle o serramenti moderni, porte, portoni, garage, vetrine, finestre di chiese e stalle), 5 915 balconi, zoccoli e 3 348 comignoli, distribuiti per piani e campate secondo uso, epoca e numero di piani del Registro federale degli edifici. Coperture in coppi, tegole, piode, lamiera o tetto piano. Tutte le texture sono disegnate dalla pipeline: nessuna foto.
- **Nuclei dei paesi casa per casa.** swissBUILDINGS3D unisce le file di case in un solo blocco; ora ogni casa della misurazione ufficiale ha le sue facciate, i suoi piani, la sua porta e il suo tono (4 508 case in blocchi). I piani partono dal marciapiede del fronte strada, anche sui pendii.
- **Colori misurati nelle foto.** Il tono dell'intonaco di 3 637 edifici e il colore delle persiane dove è chiaro vengono dalle panoramiche Street View (solo i valori numerici).
- **Vetrine** dove OpenStreetMap registra un negozio, un bar o un ufficio (173 edifici), **garage** con le porte, **rustici** in pietra.
- **Edifici mancanti:** 538 edifici della misurazione ufficiale costruiti dopo il rilievo 3D sono stati aggiunti; 14 demoliti tolti.
- **Guardrail su tutta la rete.** 326 tratti (10,5 km) di guardrail visti nelle panoramiche Street View, costruiti sul bordo della strada. Fino alla v2.1 c'erano solo quelli della cantonale Magliaso–Pura.
- **Muri** con texture originali di pietra, calcestruzzo e intonaco; il materiale viene dalle foto dove si vede bene.
- **Fermate dei bus** di OpenStreetMap con palo, cartello, orario e pensilina.
- **Strade più guidabili.** Le superfici sono continue tra carreggiata, marciapiedi e piazzali e agli incroci: il salto tra due strade che si incontrano viene distribuito su qualche metro, le carreggiate principali restano come sono. Sulle stesse strade della v2.1 la prova di guida virtuale conta il 62 % di gradini in meno sulle strade secondarie (1695 → 646) e il 20 % in meno sulle principali (74 → 59); le ruote che si staccano dalla strada calano del 56 % sulle secondarie e del 58 % sulle principali, i colpi forti del 24 % e le torsioni brusche del 58 % sulle secondarie.
- **Nessun ostacolo nei passaggi** sotto gli edifici: finestre e zoccoli non restano sospesi sopra la strada.

## Verifica

- Controlli automatici su tutta la mappa (`check_level.py`): tutti i controlli entro i limiti: nessun file mancante, 17 ostacoli sulle strade (ponti, gradini, muri e oggetti da rivedere uno per uno) e 125 sui sentieri, 103 gradini tra blocchi di strada (massimo 0,97 m), livello di 3 138 MB.
- Prova di guida virtuale su 670 km di strade e sentieri (`drive_test.py`, `beamng/verifica/drive_test.json`), confrontata con la v2.1.
- Revisione strada per strada su Street View (`beamng/verifica/REVISIONE.md`): copertura delle panoramiche, edifici misurati, guardrail e muri visti, eventi della prova di guida, luoghi confrontati foto/mappa.

## Limiti noti

- La mappa non è stata provata dentro BeamNG.drive durante questa revisione: le verifiche sono automatiche (`check_level.py`, `drive_test.py`) e sui render del livello confrontati con le panoramiche.
- Facciate: numero e posizione di finestre, balconi e porte sono plausibili (uso, epoca e piani del registro) ma non copiati uno per uno. Il tono viene dalle foto per 3 637 edifici; in ombra alcune tinte escono sbagliate (una facciata crema resa rosa). Pietra a vista, portici e zoccoli alti un piano non sono modellati.
- Piazzali della misurazione ufficiale che scavalcano un salto di quota diventano rampe ripide accanto alla strada (per esempio in Via Torrazza a Caslano).
- Alcuni edifici di swissBUILDINGS3D hanno i muri solo sotto una parte del tetto (un capannone a Pura).
- Guardrail e materiale dei muri solo dove le panoramiche li vedono; 736 muri senza un materiale sicuro restano in pietra.
- La prova di guida segnala ancora punti da sistemare: l'incrocio ripido di Castelrotto, le strade parallele di Via Giuseppe Soldati, le estremità dei ponti di Via Mondonico e Via Roncaccio, il passaggio a livello di Via Grumo, i bordi dei corridoi; sui sentieri gli eventi sono quasi invariati.
- Le strade nuove finiscono al bordo del loro corridoio di 100 m (oltre, come altrove, c'è solo il terreno): Arosio e Caslano sono compresi solo in parte.
- Revisione foto/mappa: 116 luoghi, 20 differenze ancora da verificare (elenco in `beamng/dati/qa_review.json`).

Fonti: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); misurazione ufficiale del Cantone Ticino (geodienste.ch); Registro federale degli edifici e delle abitazioni (UST); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA). Le panoramiche Google Street View sono servite solo come riferimento visivo: la mod non contiene immagini Street View.
