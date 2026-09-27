# Verifica finale contro l'intero dataset

Per ciascuna delle 366 panoramiche (4 direzioni: 1464 viste) la camera del gioco è stata messa nella posa calibrata della foto, con la stessa direzione e lo stesso campo visivo (90°). Foto e schermata sono state segmentate con lo stesso modello (Mask2Former, Mapillary Vistas) e confrontate pixel per pixel. Veicoli e persone nelle foto sono esclusi.

## Risultato complessivo

- Concordanza media dei pixel: **0.629**
- Sovrapposizione (IoU) per classe: cielo 0.45, edifici 0.31, vegetazione 0.54, strada 0.66, muri 0.33, guardrail/recinzioni 0.16, terreno 0.29, pali/cartelli 0.01
- Per direzione: back 0.686, fwd 0.668, left 0.553, right 0.607

## Effetto dell'ultimo ciclo di correzione

La stessa verifica, ripetuta prima dell'ultimo ciclo di confronto e correzione, aveva dato i valori della colonna "Prima". Quel ciclo ha misurato nelle foto l'altezza dei muri, portato a piena risoluzione le texture dei muri lunghi e aggiunto gli arbusti mancanti.

| Misura | Prima | Dopo |
|---|---|---|
| Concordanza media | 0.623 | 0.629 |
| IoU cielo | 0.453 | 0.454 |
| IoU edifici | 0.312 | 0.306 |
| IoU vegetazione | 0.535 | 0.540 |
| IoU strada | 0.655 | 0.655 |
| IoU muri | 0.304 | 0.328 |
| IoU guardrail/recinzioni | 0.157 | 0.159 |
| IoU terreno | 0.282 | 0.288 |
| IoU pali/cartelli | 0.009 | 0.010 |

## Lungo il percorso (tratti di 200 m)

| Tratto (m) | Panoramiche | Concordanza |
|---|---|---|
| 0–200 | 23 | 0.672 |
| 200–400 | 20 | 0.670 |
| 400–600 | 18 | 0.626 |
| 600–800 | 20 | 0.605 |
| 800–1000 | 19 | 0.590 |
| 1000–1200 | 25 | 0.600 |
| 1200–1400 | 10 | 0.602 |
| 1400–1600 | 21 | 0.542 |
| 1600–1800 | 20 | 0.591 |
| 1800–2000 | 20 | 0.574 |
| 2000–2200 | 20 | 0.657 |
| 2200–2400 | 19 | 0.621 |
| 2400–2600 | 20 | 0.693 |
| 2600–2800 | 20 | 0.687 |
| 2800–3000 | 20 | 0.647 |
| 3000–3200 | 18 | 0.568 |
| 3200–3400 | 22 | 0.660 |
| 3400–3600 | 20 | 0.676 |
| 3600–3800 | 11 | 0.651 |

## Le 10 panoramiche meno concordanti

| Panoramica | Distanza (m) | Anno | Concordanza |
|---|---|---|---|
| 0140 | 1450 | 2022 | 0.315 |
| 0136 | 1412 | 2022 | 0.377 |
| 0317 | 3240 | 2022 | 0.391 |
| 0035 | 322 | 2022 | 0.407 |
| 0309 | 3159 | 2022 | 0.448 |
| 0135 | 1402 | 2022 | 0.452 |
| 0118 | 1149 | 2022 | 0.455 |
| 0285 | 2903 | 2022 | 0.463 |
| 0228 | 2336 | 2022 | 0.465 |
| 0141 | 1460 | 2022 | 0.467 |

## Come leggere i numeri

- Anche con due immagini identiche la concordanza non arriverebbe a 1: la segmentazione di foto e gioco ha il suo rumore. Cielo, strada e vegetazione pesano di più perché occupano più pixel.
- Pali e cartelli sono oggetti sottili: a 10 m, 0,3 m di errore valgono circa 25 pixel, più della loro larghezza. La loro IoU resta quindi bassa anche quando sono al posto giusto; le posizioni sono state verificate a parte, per riproiezione nelle foto.
- Tra 1,28 e 1,36 km non esistono panoramiche, quindi il tratto non entra nel confronto.
- Le differenze che restano sono soprattutto nella vegetazione: forma e specie delle piante, siepi e arbusti dei giardini privati, scarpate con reti paramassi. Il cielo è coperto nelle foto e a nubi sparse nel gioco.
