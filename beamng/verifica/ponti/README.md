# Ponti della rete v2.0

Un elemento per ponte di `beamng/dati/ponti.json`. Le schede (profilo e tre viste del livello) si rigenerano con `python bridge_report.py`; i profili di tutti i ponti sono in `profili_NN.jpg`. Le correzioni manuali (`z0`, `z1`, `profile`, `type`, `skip`, `note`) stanno in `ponti.json`.

| # | Classe | Nome | x, y (m) | Lunghezza m | Altezza max m | Tipo | Segnalazioni | Nota |
|---|---|---|---|---|---|---|---|---|
| 000 | 2m Weg | — | 1989, -188 | 315 | 3.5 | open |  | Passerella a lago tra Magliaso e Agno (315 m): impalcato diritto tra le due spalle, circa 3,5 m sopra l'acqua come la linea di swissTLM3D (la curva tra gli accessi scendeva di 1,7 m). |
| 001 | 4m Strasse | — | 3706, 3689 | 88 | 0.3 | culvert | tlm | Rampa di Manno che swissTLM3D porta fino al tetto di un edificio (303,5 m, 11 m sopra il terreno): nel gioco finirebbe nel vuoto contro il muro, quindi la strada resta a terra e finisce all'edificio. |
| 002 | 8m Strasse | Via Grumo | 4290, 5813 | 85 | 12.7 | open | terreno,prolungato 40 m | Via Grumo: la linea swissTLM3D finisce al bordo dell'area a 7 m dal suolo; l'impalcato continua per 40 m fino a terra, fuori dall'area. |
| 003 | 1m Weg | — | -4292, 674 | 63 | 0.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 004 | 4m Strasse | Lüsc | -2120, -208 | 56 | 27.0 | open | terreno | Lüsc: ponte alto 27 m sulla gola, con piloni; impalcato alla quota di swissTLM3D. |
| 005 | 10m Strasse | — | -740, -2768 | 46 | 2.4 | open | terreno | Ponte sulla Tresa a Ponte Tresa (confine): impalcato alla quota di swissTLM3D (272,8 m), 2,3 m sopra l'acqua; sul lato italiano finisce sul terreno Copernicus. |
| 006 | 4m Strasse | Via Ponte di Vello | 728, 4527 | 44 | 5.6 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 007 | 4m Strasse | — | -2716, 1032 | 37 | 11.6 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 008 | 1m Weg | — | 2278, 773 | 36 | 4.7 | open | ripido,terreno | Passerella pedonale di Agno sopra la cantonale per Bioggio, con le scale ai due capi: impalcato sulla linea 3D di swissTLM3D, circa 4 m sopra la strada (come tombino sbarrava la carreggiata). |
| 009 | 1m Weg | — | 269, 1479 | 32 | 6.4 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 010 | 3m Strasse | Via Monte Oliveto | -602, -2309 | 31 | 5.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 011 | 1m Wegfragment | — | 1478, 2930 | 31 | 12.9 | open | terreno | Frammento di sentiero isolato: quote di swissTLM3D (nessun altro dato), passerella su un avvallamento. |
| 012 | 4m Strasse | — | 778, -1072 | 30 | 5.6 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 013 | 1m Weg | — | 287, 4104 | 28 | 2.5 | open | tlm,terreno | La rete finisce qui: l'estremità dell'impalcato è raccordata al terreno. |
| 014 | 2m Weg | — | 1040, -266 | 28 | 16.1 | open |  | Passerella alta 16 m sulla gola, con un pilone; impalcato alla quota di swissTLM3D. |
| 015 | 4m Strasse | Via Giacomo Donati | -3726, 1876 | 25 | 8.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 016 | 4m Strasse | Via Agostino de Marchi | -3712, 2128 | 25 | 9.0 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 017 | 4m Strasse | — | -4748, -203 | 24 | 7.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 018 | 2m Weg | — | 2447, 2927 | 23 | 4.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 019 | 1m Weg | — | 2042, 2897 | 22 | 7.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 020 | 4m Strasse | Via Funtanín | -2442, 2352 | 21 | 9.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 021 | 2m Weg | — | 4173, 5296 | 20 | 11.7 | open | terreno,sospeso | Passerella che dal pendio arriva al piano alto di un edificio: il capo sull'edificio resta sospeso, come nei dati. |
| 022 | 4m Strasse | Via Selva | 1647, 134 | 19 | 5.2 | open | terreno |  |
| 023 | 3m Strasse | Via Ponte di Vello | 515, 4397 | 19 | 8.0 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 024 | 4m Strasse | Via Cantonale | 946, 1932 | 19 | 4.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 025 | 1m Weg | — | 1672, 3317 | 19 | 3.1 | open | tlm,terreno,sospeso | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 026 | 1m Wegfragment | — | 279, -165 | 18 | 3.3 | open | terreno,raccordato al terreno | Frammento di sentiero isolato: quote di swissTLM3D, estremità raccordata al terreno. |
| 027 | 1m Weg | — | -3332, -496 | 17 | 2.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 028 | 10m Strasse | Via Lugano | -717, -2746 | 17 | 2.4 | open |  | Via Lugano a Ponte Tresa: impalcato alla quota di swissTLM3D sopra l'acqua (prima seguiva l'acqua perché il DTM è piatto sul fiume). |
| 029 | 4m Strasse | Via Cantonale | -1440, 3422 | 17 | 11.3 | open |  | Controllato: impalcato continuo con gli accessi. |
| 030 | 1m Weg | — | -4506, 717 | 17 | 0.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 031 | 4m Strasse | Romanino | -2323, -422 | 16 | 7.2 | open |  | Controllato: impalcato continuo con gli accessi. |
| 032 | 8m Strasse | Via Cantonale | 787, -1093 | 16 | 6.4 | open |  | Via Cantonale sul fiume Magliasina: profilo piano tra gli accessi a 300,5 m (prima una stazione vincolata alla strada sotto lo tirava giù di 20-35 m). |
| 033 | 8m Strasse | Via Cantonale | 797, -1081 | 16 | 6.3 | open | terreno | Via Cantonale sul fiume Magliasina: profilo piano tra gli accessi a 300,5 m, come il tratto accanto. |
| 034 | 2m Weg | Case del Gatto | 2982, 3666 | 16 | 5.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 035 | 2m Weg | Via Néda | -2542, 1508 | 15 | 7.0 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 036 | 1m Weg | — | -2879, 1625 | 15 | 2.6 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 037 | 1m Weg | — | 3726, 4651 | 15 | 1.7 | culvert |  | Passerella ripida (19 %) che parte dal nodo quasi parallela al sentiero: resta un gradino di circa 2 m tra i due nei primi metri. |
| 038 | 6m Strasse | Via Cantonale | -3276, -396 | 14 | 4.7 | open |  | Controllato: impalcato continuo con gli accessi. |
| 039 | 1m Weg | — | 3554, 3148 | 14 | 3.4 | open | terreno |  |
| 040 | 1m Wegfragment | — | -215, 531 | 14 | 1.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 041 | 2m Weg | — | -1528, 2031 | 14 | 2.2 | open | tlm,terreno | Controllato: impalcato continuo con gli accessi. |
| 042 | 4m Strasse | Via Cantonale | 1780, 3203 | 14 | 0.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 043 | 1m Weg | — | -4544, 734 | 14 | 0.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 044 | 3m Strasse | ai Vezzán | -3759, 2291 | 14 | 1.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 045 | 4m Strasse | Via Astano | -3263, 1218 | 13 | 5.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 046 | 1m Weg | — | 2538, 2642 | 13 | 4.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 047 | 1m Weg | — | 2704, 2427 | 13 | 3.8 | open | terreno |  |
| 048 | 1m Weg | — | -133, 3622 | 12 | 2.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 049 | 1m Weg | — | 2438, 379 | 12 | 1.7 | culvert |  | Tombino: la passerella resta sul terreno, i fianchi scendono al suolo. |
| 050 | 4m Strasse | Via Fornasette | -5281, 367 | 12 | 6.5 | open |  | Controllato: impalcato continuo con gli accessi. |
| 051 | 1m Weg | — | -543, 2498 | 12 | 4.8 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 052 | 4m Strasse | Via Cademario | 2948, 3558 | 11 | 4.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 053 | 3m Strasse | Via Molinazzo | 2478, 441 | 11 | 2.3 | open | terreno |  |
| 054 | 4m Strasse | Ur Stradón | 475, 3564 | 11 | 4.8 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 055 | 2m Weg | — | -3236, -281 | 11 | 4.2 | open |  | Controllato: impalcato continuo con gli accessi. |
| 056 | 1m Weg | — | 3735, 4702 | 11 | 3.5 | open | tlm,ripido,terreno | Controllato: impalcato continuo con gli accessi. |
| 057 | 1m Weg | — | -1827, 3660 | 11 | 2.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 058 | 1m Weg | — | -34, 4009 | 11 | 2.6 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 059 | 1m Weg | — | -4482, 699 | 11 | 0.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 060 | 1m Weg | — | -2817, 3237 | 10 | 4.5 | open | tlm,ripido,terreno | Controllato: impalcato continuo con gli accessi. |
| 061 | 1m Weg | — | 1295, 4895 | 10 | 2.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 062 | 4m Strasse | Strada Regina | 3743, 5344 | 10 | 2.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 063 | 4m Strasse | Ra Stráda da Brén | 707, 4280 | 10 | 7.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 064 | 3m Strasse | Via Selva | 1848, 575 | 10 | 3.1 | open | terreno |  |
| 065 | 4m Strasse | Via Cantonale | 546, 776 | 10 | 1.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 066 | 1m Wegfragment | — | 3511, 2997 | 10 | 2.1 | culvert |  |  |
| 067 | 1m Weg | — | -138, 3905 | 10 | 3.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 068 | 2m Weg | Strada ai Boschi | 741, -327 | 10 | 5.6 | open |  | Controllato: impalcato continuo con gli accessi. |
| 069 | 1m Weg | — | -3386, 34 | 10 | 2.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 070 | 4m Strasse | Via la Barca | 2826, 2794 | 10 | 2.2 | open | terreno |  |
| 071 | 1m Weg | — | -3178, 629 | 10 | 1.5 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 072 | 1m Weg | — | -2804, 1690 | 9 | 6.4 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 073 | 4m Strasse | Via Mavögn | -1242, 2935 | 9 | 3.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 074 | 2m Weg | Via Madrallo | -860, 2814 | 9 | 4.2 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 075 | 2m Weg | — | -4168, -204 | 9 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 076 | 1m Weg | — | -1758, 250 | 9 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 077 | 1m Weg | — | -1934, -1598 | 9 | 1.7 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 078 | 2m Weg | — | 2458, 2951 | 9 | 3.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 079 | 3m Strasse | Via Morina | -4099, 427 | 9 | 2.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 080 | 2m Weg | Strada ara Morèla | -316, -227 | 8 | 3.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 081 | 1m Weg | — | 2693, 3282 | 8 | 1.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 082 | 2m Weg | Via Vei | -316, 3653 | 8 | 1.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 083 | 3m Strasse | Via Roncaccio | -5369, 107 | 8 | 1.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 084 | 3m Strasse | Via Mondonico | 2203, 2036 | 8 | 2.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 085 | 6m Strasse | Via Cantonale | -4080, -127 | 8 | 2.7 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 086 | 1m Wegfragment | — | 1990, 2901 | 8 | 2.1 | culvert |  | Frammento di sentiero isolato: quote di swissTLM3D. |
| 087 | 3m Strasse | Via Costa | -888, 1192 | 8 | 2.4 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 088 | 1m Weg | — | -5918, 114 | 8 | 1.3 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 089 | 2m Weg | — | 402, -62 | 8 | 1.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 090 | 1m Weg | — | -513, 2886 | 8 | 1.3 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 091 | 3m Strasse | — | -662, -2718 | 8 | 0.7 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 092 | 4m Strasse | Via S. Maurizio | 2705, 2433 | 8 | 2.3 | open | terreno |  |
| 093 | 1m Weg | — | 3575, 5359 | 8 | 2.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 094 | 1m Weg | — | -4202, -236 | 7 | 1.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 095 | 2m Wegfragment | — | -299, 554 | 7 | 2.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 096 | 3m Strasse | — | 3345, 5360 | 7 | 2.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 097 | 4m Strasse | Via Ponte di Vello | 471, 4340 | 7 | 4.2 | open |  | Controllato: impalcato continuo con gli accessi. |
| 098 | 4m Strasse | Via Mavögn | -1446, 3411 | 7 | 11.3 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 099 | 1m Weg | — | -2481, 2120 | 7 | 1.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 100 | 2m Weg | — | -1433, 1403 | 7 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 101 | 3m Strasse | — | -3968, 44 | 7 | 1.7 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 102 | 4m Strasse | Via Cademario | 2628, 4184 | 7 | 4.4 | open |  | Controllato: impalcato continuo con gli accessi. |
| 103 | 4m Strasse | — | -2648, 2493 | 7 | 3.4 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 104 | 3m Strasse | — | -1471, 1611 | 7 | 1.2 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 105 | 1m Weg | — | 2021, 1502 | 7 | 1.7 | culvert |  |  |
| 106 | 1m Weg | — | 411, 4404 | 7 | 1.7 | culvert | tlm,ripido,raccordato al terreno | La rete finisce qui: l'estremità dell'impalcato è raccordata al terreno. |
| 107 | 1m Weg | — | 2357, 3037 | 7 | 2.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 108 | 2m Weg | — | -4901, 759 | 7 | 0.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 109 | 4m Strasse | Via Ponte di Vello | 790, 4491 | 7 | 4.7 | open |  | Controllato: impalcato continuo con gli accessi. |
| 110 | 2m Weg | — | -336, 584 | 7 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 111 | 1m Weg | — | -4634, 655 | 6 | 0.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 112 | 4m Strasse | — | -2569, 2524 | 6 | 3.0 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 113 | 4m Strasse | Via Scerèe | -1251, 1211 | 6 | 2.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 114 | 1m Weg | — | -1241, 1265 | 6 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 115 | 2m Wegfragment | — | -4892, 2358 | 6 | 0.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 116 | 4m Strasse | Via Grumo | 3939, 5283 | 6 | 2.5 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 117 | 4m Strasse | — | 709, 4287 | 6 | 7.2 | open |  | Controllato: impalcato continuo con gli accessi. |
| 118 | 1m Weg | — | 301, 3359 | 6 | 1.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 119 | 1m Weg | — | -6045, 991 | 6 | 1.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 120 | 3m Strasse | — | 2608, 1458 | 6 | 1.2 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 121 | 1m Weg | — | -2159, 3877 | 6 | 0.7 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 122 | 1m Weg | — | -668, 2894 | 6 | 0.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 123 | 1m Weg | — | 1810, 3184 | 6 | 4.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 124 | 1m Weg | — | -874, 3968 | 6 | 0.9 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 125 | 4m Strasse | Via Gaggio | 2698, 2432 | 6 | 2.3 | open | terreno |  |
| 126 | 3m Strasse | — | -3947, 176 | 6 | 1.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 127 | 2m Weg | — | 4176, 5211 | 6 | 0.0 | culvert |  |  |
| 128 | 1m Wegfragment | — | -5006, 2594 | 5 | 0.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 129 | 4m Strasse | Via Sótt ara Còsta | -1256, 1210 | 5 | 2.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 130 | 1m Weg | — | 2697, 2706 | 5 | 0.5 | culvert |  |  |
| 131 | 3m Strasse | — | -4982, 2501 | 5 | 0.7 | culvert | tlm,raccordato al terreno | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 132 | 1m Weg | — | -4414, 689 | 5 | 0.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 133 | 2m Weg | — | -5177, 2458 | 5 | 1.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 134 | 2m Weg | — | -4996, 2559 | 5 | 0.5 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 135 | 1m Weg | — | 1832, 135 | 5 | 0.9 | culvert |  |  |
| 136 | 2m Weg | — | 4305, 5183 | 5 | 0.1 | culvert |  |  |
| 137 | 1m Weg | — | 512, 2150 | 5 | 1.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 138 | 1m Weg | — | -2947, 3695 | 5 | 0.6 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 139 | 4m Strasse | Via Cantonale | 583, 922 | 5 | 3.1 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 140 | 1m Weg | — | -1979, -1166 | 4 | 2.7 | open | tlm | Controllato: impalcato continuo con gli accessi. |
| 141 | 1m Weg | — | -5344, 1655 | 4 | 1.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 142 | 1m Weg | — | 2790, 3671 | 4 | 1.4 | culvert | raccordato al terreno | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 143 | 1m Weg | — | -4345, 1292 | 4 | 0.2 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 144 | 1m Weg | Campo Lungo | 2960, 3535 | 4 | 0.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 145 | 3m Strasse | — | -4989, 2530 | 4 | 0.8 | culvert | raccordato al terreno | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 146 | 2m Weg | Via Vinéra | -867, 2812 | 4 | 3.9 | open | terreno | Controllato: impalcato continuo con gli accessi. |
| 147 | 1m Weg | — | 338, 2495 | 4 | 0.7 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 148 | 1m Weg | — | 373, 2659 | 4 | 0.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 149 | 1m Weg | — | 2228, 3216 | 4 | 0.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 150 | 2m Weg | — | 2508, 1769 | 4 | 0.9 | culvert |  |  |
| 151 | 1m Weg | — | -877, 3941 | 4 | 0.3 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 152 | 2m Weg | ara Scísa | 2136, 2827 | 4 | 1.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 153 | 1m Weg | — | 3509, 5738 | 4 | 1.7 | culvert | tlm,raccordato al terreno |  |
| 154 | 4m Strasse | Via Crosa | -4171, 613 | 4 | 1.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 155 | 1m Weg | — | -4890, 1443 | 3 | 0.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 156 | 1m Weg | — | 3304, 2778 | 3 | 0.8 | culvert |  |  |
| 157 | 1m Weg | — | 3525, 4441 | 3 | 0.4 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 158 | 4m Strasse | Via alle Bolle | -4168, 615 | 3 | 1.8 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 159 | 1m Weg | ai Runchítt | -3907, 2260 | 3 | 0.0 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
| 160 | 2m Weg | In Oncèla | -3973, 938 | 2 | 0.1 | culvert |  | Tombino: la strada resta sul terreno, i fianchi scendono al suolo. |
