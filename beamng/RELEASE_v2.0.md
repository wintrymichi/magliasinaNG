Mappa BeamNG.drive (0.39) del **Malcantone**: la Strada Cantonale Magliaso–Pura delle versioni 1.x più tutto il territorio compreso tra Ponte Tresa, Manno, Cademario, Novaggio, Astano e Sessa, circa 46 km² in scala 1:1.

**Installazione:** copiare `magliaso_pura_v2.0.zip` in `Documents/BeamNG.drive/current/mods/` (o installarlo dal gestore delle mod). Il livello si chiama sempre `magliaso_pura` e sostituisce la v1.1.

## Novità della v2.0

- **Area ampliata.** Il terreno misura 12,3 × 12,3 km (maglia 1,5 m, swissALTI3D; Copernicus sul lato italiano), con il Lago di Lugano e il paesaggio lontano fino a 24 km.
- **Tutta la rete guidabile.** Ogni strada e sentiero di swissTLM3D nell'area ha una superficie solida e liscia: circa 157 km di strade e 293 km di sentieri e mulattiere. Le carreggiate seguono i limiti della misurazione ufficiale. Il profilo è calcolato su tutta la rete insieme, così agli incroci le quote coincidono. Le pendenze reali restano, il rumore del rilievo sparisce. La cantonale Magliaso–Pura tiene la superficie verificata della v1.1.
- **Ponti.** 137 ponti con impalcato, parapetti e piloni sulle campate alte, controllati uno per uno. Le correzioni manuali sono in `beamng/dati/ponti.json`. Le strade che passano sotto un ponte restano.
- **Edifici.** Tutti gli 8490 edifici swissBUILDINGS3D dell'area, con il colore dei tetti dall'ortofoto.
- **Muri** della misurazione ufficiale lungo strade e sentieri.
- **Vegetazione.** Circa 240 000 alberi e arbusti ricavati dal modello di superficie swisstopo:
  - tutti quelli entro 150 m dalle strade e 30 m dai sentieri, più radi oltre;
  - nessun tronco sulla carreggiata, a meno di 1 m dal bordo delle strade o a meno di 0,5 m da quello dei sentieri;
  - nessun arbusto sulla superficie guidabile.
- **Traffico IA** su tutte le strade carrozzabili (circa 1700 tratti).
- **Punti di partenza.** Oltre ai tre della cantonale, uno per paese: Manno, Aranno, Astano, Banco, Bedigliora, Bosco Luganese, Cademario, Castelrotto, Cimo, Curio, Miglieglia, Molinazzo di Monteggio, Monteggio, Novaggio, Ponte Tresa, Purasca, Sessa e Pura (paese).
- **Percorso originale invariato.** Sulla cantonale restano segnaletica, lampioni, pali, cartelli, guardrail e recinzioni ricavati dalle panoramiche.

## Verifica

Il livello è controllato automaticamente su tutta la mappa (`check_level.py`, risultati in `beamng/verifica/check_level.json`) e visivamente con screenshot di tutta l'area, di ogni ponte, delle strade e dei paesi (`review_map.py`, `bridge_report.py`).

## Limiti noti

- Sul lato italiano ci sono solo il terreno e il paesaggio, senza strade, edifici e alberi.
- Le gallerie di swissTLM3D non sono costruite.
- swissTLM3D non indica i sensi unici, quindi l'IA li percorre in entrambi i sensi.
- La maglia del terreno di 1,5 m non era mai stata provata in gioco con questo progetto: segnalate eventuali problemi.

Fonti: © swisstopo (swissALTI3D, SWISSIMAGE, swissSURFACE3D, swissBUILDINGS3D, swissTLM3D, swissNAMES3D); misurazione ufficiale del Cantone Ticino (geodienste.ch); Copernicus DEM GLO-30 (© DLR e.V. / Airbus, fornito nell'ambito di COPERNICUS da UE ed ESA). La mod non contiene immagini Street View.
