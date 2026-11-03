# Verifica della convergenza

Configurazione: `configurazioni/esempio_tre_portafogli.yaml`, metodo beta, analisi A, orizzonte 15 anni.

## Forma degli array

- storia (giorni x colonne): (1342, 20)
- indici bootstrap per blocco di calcolo (percorsi x giorni): (1000, 3780)
- rendimenti di un mese (percorsi x giorni x colonne): (1000, 21, 20)
- giorni simulati: 3780
- colonne (titoli): 20
- colonne per portafoglio: {'Cyber security': 7, "Banche d'investimento / PE": 7, 'Big tech USA': 5, 'MSCI World (ETF)': 1}

## Al crescere del numero di simulazioni (stesso seed)

| simulazioni | percorsi effettivi | portafoglio | mediana | 5° percentile | tempo (s) |
|---|---|---|---|---|---|
| 1000 | 1000 | Cyber security | 5.198 € | 767 € | 2 |
| 1000 | 1000 | Banche d'investimento / PE | 9.559 € | 2.464 € | 2 |
| 1000 | 1000 | Big tech USA | 6.947 € | 1.221 € | 2 |
| 1000 | 1000 | MSCI World (ETF) | 10.040 € | 4.707 € | 2 |
| 5000 | 5000 | Cyber security | 5.210 € | 741 € | 10 |
| 5000 | 5000 | Banche d'investimento / PE | 9.087 € | 2.509 € | 10 |
| 5000 | 5000 | Big tech USA | 7.195 € | 1.284 € | 10 |
| 5000 | 5000 | MSCI World (ETF) | 10.068 € | 4.583 € | 10 |
| 10000 | 10000 | Cyber security | 5.154 € | 716 € | 20 |
| 10000 | 10000 | Banche d'investimento / PE | 9.150 € | 2.524 € | 20 |
| 10000 | 10000 | Big tech USA | 7.158 € | 1.268 € | 20 |
| 10000 | 10000 | MSCI World (ETF) | 10.040 € | 4.550 € | 20 |
| 20000 | 20000 | Cyber security | 5.131 € | 723 € | 38 |
| 20000 | 20000 | Banche d'investimento / PE | 9.250 € | 2.511 € | 38 |
| 20000 | 20000 | Big tech USA | 7.202 € | 1.269 € | 38 |
| 20000 | 20000 | MSCI World (ETF) | 10.059 € | 4.512 € | 38 |

## 10.000 simulazioni con 5 seed diversi

| portafoglio | mediana min–max | scarto max mediana | 5° perc. min–max | scarto max 5° perc. |
|---|---|---|---|---|
| Cyber security | 5.071 € – 5.154 € | ±0,9% | 681 € – 723 € | ±3,6% |
| Banche d'investimento / PE | 9.150 € – 9.417 € | ±1,9% | 2.461 € – 2.580 € | ±2,7% |
| Big tech USA | 6.902 € – 7.274 € | ±3,2% | 1.226 € – 1.281 € | ±2,5% |
| MSCI World (ETF) | 10.034 € – 10.182 € | ±0,9% | 4.412 € – 4.550 € | ±1,7% |
## 20.000 simulazioni con 5 seed diversi (per confronto)

| portafoglio | mediana min–max | scarto max mediana | 5° perc. min–max | scarto max 5° perc. |
|---|---|---|---|---|
| Cyber security | 5.033 € – 5.172 € | ±1,7% | 698 € – 726 € | ±2,0% |
| Banche d'investimento / PE | 9.158 € – 9.278 € | ±0,7% | 2.504 € – 2.526 € | ±0,5% |
| Big tech USA | 7.033 € – 7.202 € | ±1,3% | 1.244 € – 1.274 € | ±1,2% |
| MSCI World (ETF) | 10.059 € – 10.154 € | ±0,6% | 4.462 € – 4.476 € | ±0,8% |

## Conclusione

- Il numero di percorsi effettivi coincide sempre con quello richiesto (1.000, 5.000, 10.000, 20.000).
- Con **10.000** simulazioni la mediana a 15 anni cambia tra seed fino a **±3,2%** (Big tech USA): sopra la soglia indicativa del ±2%.
- Con **20.000** simulazioni lo scarto massimo scende a **±1,7%**: entro la soglia per tutti i portafogli.
- L'incertezza scende come 1/√n: raddoppiare le simulazioni la riduce di circa il 30%, ma raddoppia anche il tempo.
