Mappa BeamNG.drive (0.39) del **Malcantone**, versione 2.4: la [v2.3](https://github.com/wintrymichi/magliasinaNG/releases/tag/v2.3) con due correzioni segnalate nel gioco e una grafica più realistica. Stessa area (circa 52 km² tra Ponte Tresa, Caslano, Agno, Bioggio, Manno, Gravesano, Arosio, Cademario, Novaggio, Astano e Sessa, scala 1:1) e stesse strade.

**Installazione:** copiare `magliaso_pura_v2.4.zip` in `Documents/BeamNG.drive/current/mods/` (o installarlo dal gestore delle mod) e togliere le versioni precedenti: il livello si chiama sempre `magliaso_pura`.

## Correzioni

- **Case trasparenti da certe angolazioni.** Il gioco disegna una faccia sola di ogni parete, quella che guarda fuori. Fino alla v2.3 il verso delle pareti si decideva guardando il centro dell'edificio, e sbagliava negli edifici a L, a U, a corte e nelle file di case: l'8,6 % della superficie delle pareti guardava verso l'interno, e da fuori quelle pareti mancavano (si vedevano i tetti sospesi). Ora il verso si decide con dei raggi: un raggio che parte appena davanti alla parete ed esce dall'edificio attraversa le sue superfici un numero pari di volte. Le pareti girate verso l'interno scendono a 0,06 % (controllo automatico nuovo in `check_level.py`); dove il rilievo 3D lascia l'edificio aperto e il verso non si può decidere, la parete ha due facce. Sotto le gronde c'è il sottotetto, che da sotto prima mancava. Anche muri, recinzioni, guardrail, pali e binari hanno ora tutte le facce verso fuori.
- **Il "cubo" alla rotonda di Magliaso, sulla salita verso Pura.** Era la cima di un muro di sostegno della misurazione ufficiale, accanto alla casa all'incrocio, che la mappa faceva sporgere di 16 cm sopra l'asfalto; il cantiere che quel muro delimitava non c'è più e le panoramiche del 2022 vedono lì solo strada e marciapiede (340 voti su 341). Ora i muri della misurazione che le panoramiche vedono come pavimentazione sono portati a filo della pavimentazione (487 muri) o tolti dove attorno il terreno è in piano (37). Lì accanto anche il pezzo di marciapiede rimasto in mezzo alla strada dall'isola pedonale tolta nel 2022 (il "quadrato per terra") è ora carreggiata.

## Grafica

- **Sterrati, ghiaia e selciati dove lo sono davvero (OpenStreetMap).** Ogni strada e sentiero prende la superficie di OpenStreetMap (asfalto, ghiaia, terra, cubetti, ciottoli) dove è indicata, altrimenti quella di swissTLM3D. Le strade della misurazione ufficiale, prima tutte asfaltate, ora hanno 36 ha di terra, 9,4 ha di ghiaia e 1,2 ha di cubetti e ciottoli nei nuclei; sui sentieri 227 km di terra, 32 km di ghiaia, 76 km pavimentati e 1,5 km di selciato. Le texture sono disegnate dalla pipeline (pietre, ghiaia, foglie, giunti), con la tinta misurata sull'ortofoto lungo le vie OSM con quella superficie. Nel gioco anche l'aderenza e il rumore cambiano: ghiaia, terra e selciato hanno il loro tipo di fondo.
- **Erba e fiori** sui prati e nei giardini, attorno alla telecamera (50 m): ciuffi d'erba e fiori di prato disegnati (margherite, ranuncoli, salvia, trifoglio) come billboard leggeri, 40 000 al massimo, niente erba sui bordi delle strade.
- **Palme nei giardini vicino al lago:** 352 palme (Trachycarpus) disegnate dalla pipeline, al posto di alberi misurati di quella taglia nei giardini entro 400 m dal lago. Quali alberi siano palme non si può misurare: la scelta è una stima (un albero su quattro di quella taglia).
- **Vigneti con i filari:** 475 vigneti della misurazione ufficiale vicino alle strade hanno i loro filari (465 km), nella direzione che si legge sull'ortofoto (307 vigneti) o lungo le curve di livello.
- **Acqua nei fiumi:** la Magliasina, il Vedeggio, la Tresa sotto la traversa e gli altri corsi d'acqua che la misurazione disegna come superfici (30 ha) hanno l'acqua, anche sotto i ponti; nei torrenti sassosi l'acqua sta nel canale più basso, e il letto scende sotto l'acqua (non le sponde ripide delle gole, non accanto a strade e sentieri: ai guadi si guida come prima).
- **Materiali più profondi:** ombre ambientali (ambient occlusion) per intonaco, zoccoli e tetti, muri più scuri verso terra.
- **Lampioni** lungo la cantonale con la loro luce di notte (68, senza ombre), **foschia** un po' più densa sopra il lago.

## Verifica

- Controlli automatici su tutta la mappa (`check_level.py`): tutti entro i limiti; nessun file mancante, nessun buco nel terreno, 12 ostacoli sulle strade (v2.3: 13) e 127 sui sentieri (v2.3: 125), 104 giunzioni con un gradino tra blocchi di strada come nella v2.3 (massimo 0,97 m), livello di 3 287 MB. Controllo nuovo delle pareti degli edifici girate verso l'interno: 0,06 % della superficie delle pareti (v2.3: 8,6 %; limite 2 %).
- Prova di guida virtuale su 670 km di strade e sentieri (`drive_test.py`), confrontata con la v2.3: strade principali identiche; sulle strade secondarie gradini 586 → 576, torsioni brusche 2876 → 2775, ruote staccate 6363 → 6329, quasi tutto in Via alla Chiesa di San Michele; sui sentieri come prima (scarti sotto lo 0,1 %): accanto alle strade e ai sentieri a livello del terreno il letto dei fiumi non è abbassato, così ai guadi si guida come nella v2.3.
- Render di controllo dagli stessi punti di vista prima e dopo (case di Magliaso viste da dietro, rotonda di Magliaso, cubetti, ciottoli, ghiaia, sterrato, vigneto, la Magliasina dall'alto): sono immagini del renderer di verifica della pipeline, non del gioco.

## Prestazioni

La fluidità dentro BeamNG.drive non è misurata (il gioco non è disponibile dove la mappa viene costruita). In numeri, quello che la v2.4 aggiunge alla v2.3:

- **Edifici:** 2,44 milioni di triangoli invece di 2,15 (+13,6 %), per le pareti a due facce dove il verso non si può decidere e per i sottotetti.
- **Erba:** al massimo 40 000 ciuffi di 2 triangoli entro 50 m dalla telecamera, che sfumano da 35 m, senza ombre.
- **Vigneti:** 242 000 triangoli in pezzi di 128 m, che spariscono oltre circa 1 km.
- **Fiumi:** 108 000 triangoli d'acqua trasparente, senza ombre.
- **Palme:** 352, di 70 triangoli ciascuna.
- **Luci:** 68 lampioni con una luce di 14 m di raggio, senza ombre.
- **Alberi:** quanti nella v2.3 (circa 161 000).
- **Livello:** 3 287 MB invece di 3 123.

## Limiti noti

- Non provato dentro BeamNG.drive (il gioco non è disponibile dove la mappa viene costruita): l'erba (oggetto GroundCover), la trasparenza dell'acqua dei fiumi, il fondo "COBBLESTONE" dei selciati e le luci dei lampioni sono scritti nel formato del gioco ma il loro aspetto e il loro costo vanno visti nel gioco. Se l'erba pesa troppo, la qualità della vegetazione nelle impostazioni del gioco la riduce.
- Le palme sono una stima (le foto aeree non distinguono una palma da un piccolo albero); la densità dell'erba e la distanza dei filari (2,2 m) non sono misurate.
- La superficie di OpenStreetMap non è indicata per tutte le strade: dove manca vale quella di swissTLM3D (asfaltato o naturale). Qualche passaggio da asfalto a ghiaia può cadere qualche metro più in là che nella realtà.
- Con le pareti girate dal lato giusto anche lo zoccolo di qualche casa è passato sul lato esterno: la prova degli ostacoli conta 12 punti di sentiero bloccati da edifici invece di 10. Quello controllato, sotto Pura, è un sentiero largo 1 m che entra in un vicolo tra case a schiera, ora attraversato in basso dallo zoccolo (circa 60 cm).
- Restano i limiti della v2.3 (vedi le sue note).

Fonti: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); misurazione ufficiale del Cantone Ticino (geodienste.ch); Registro federale degli edifici e delle abitazioni (UST); © OpenStreetMap contributors (ODbL); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA). Le panoramiche Google Street View sono servite solo come riferimento visivo: la mod non contiene immagini Street View.
