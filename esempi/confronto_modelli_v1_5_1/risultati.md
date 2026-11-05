# Confronto tra modello «storico» e modello «a fattori» (versione 1.5.1, 05/11/2026)

Esempio `configurazioni/esempio_tre_portafogli.yaml` (3 portafogli + MSCI World), dati reali Yahoo, 20.000 simulazioni, 15 anni, capitale 5.000 €,
rendimento atteso con metodo beta (2% / 4%), stesso seed. Valori in euro. La **volatilità annua** è calcolata dai rendimenti di un mese (×√12), come dalla 1.5.1.
Storico A: periodo comune dal 01/07/2021; storico B: dal 03/01/2007; fattori: storia dei fattori dal 2000 (residui dei titoli dalle stesse date).

| | Cyber security | Banche / PE | Big tech USA | MSCI World |
|---|---|---|---|---|
| **Volatilità annua simulata** storico A | 32,6% | 21,8% | 27,8% | 13,2% |
| storico B | 30,8% | 26,0% | 25,5% | 15,8% |
| fattori | 31,3% | 25,5% | 30,4% | 16,3% |
| **Max drawdown mediano a 15 anni** storico A | −72% | −50% | −64% | −32% |
| storico B | −69% | −62% | −60% | −41% |
| fattori | −71% | −61% | −70% | −42% |
| **Mediana a 5 / 10 / 15 anni** storico A | 5.526 / 6.160 / 6.843 | 6.482 / 8.336 / 10.773 | 5.894 / 6.998 / 8.181 | 6.411 / 8.207 / 10.421 |
| storico B | 5.692 / 6.440 / 7.310 | 6.074 / 7.333 / 8.837 | 6.090 / 7.397 / 9.010 | 6.310 / 7.876 / 9.750 |
| fattori | 5.668 / 6.429 / 7.165 | 6.181 / 7.593 / 9.254 | 5.746 / 6.579 / 7.451 | 6.327 / 7.912 / 9.753 |
| **5° percentile a 5 / 10 / 15 anni** storico A | 1.781 / 1.220 / 954 | 3.050 / 2.898 / 2.917 | 2.159 / 1.683 / 1.478 | 4.022 / 4.193 / 4.638 |
| storico B | 1.879 / 1.376 / 1.104 | 2.302 / 1.857 / 1.650 | 2.390 / 2.026 / 1.847 | 3.401 / 3.363 / 3.488 |
| fattori | 1.817 / 1.257 / 975 | 2.353 / 1.957 / 1.832 | 1.872 / 1.321 / 1.051 | 3.368 / 3.276 / 3.426 |

## Controllo di plausibilità (rendimento medio del primo anno contro il rendimento atteso)

| modello e analisi | serie | atteso | simulato | tolleranza | coincide |
|---|---|---|---|---|---|
| storico A | Cyber security | 7,4% | 7,1% | ±1,5% | sì |
| storico A | Banche / PE | 7,4% | 7,5% | ±1,1% | sì |
| storico A | Big tech USA | 7,3% | 7,0% | ±1,4% | sì |
| storico A | MSCI World | 5,8% | 5,8% | ±0,8% | sì |
| storico B | Cyber security | 7,4% | 7,5% | ±1,5% | sì |
| storico B | Banche / PE | 7,4% | 7,2% | ±1,3% | sì |
| storico B | Big tech USA | 7,3% | 7,4% | ±1,3% | sì |
| storico B | MSCI World | 5,8% | 5,8% | ±0,9% | sì |
| fattori A | Cyber security | 7,4% | 7,4% | ±1,5% | sì |
| fattori A | Banche / PE | 7,4% | 7,4% | ±1,3% | sì |
| fattori A | Big tech USA | 7,3% | 7,5% | ±1,5% | sì |
| fattori A | MSCI World | 5,8% | 5,9% | ±0,9% | sì |

## Backtest del VaR a 1 giorno (839 giorni di prova dopo la finestra di 2 anni)

Sforamenti (attesi: 5% dei giorni al 95%, 1% al 99%) e semaforo. «fattori (1.5.0)» = modello precedente; «fattori (ora)» = covarianza e rischio specifico EWMA (lambda 0,97), code grasse.

| serie | VaR | attesi | storico | fattori (1.5.0) | fattori (ora) |
|---|---|---|---|---|---|
| Cyber security | 95% | 42,0 | 49 🟢 | 62 🔴 | 46 🟢 |
| Cyber security | 99% | 8,4 | 10 🟢 | 32 🔴 | 12 🟢 |
| Banche / PE | 95% | 42,0 | 36 🟢 | 16 🔴 | 48 🟢 |
| Banche / PE | 99% | 8,4 | 9 🟢 | 4 🟡 | 15 🔴 |
| Big tech USA | 95% | 42,0 | 35 🟢 | 36 🟢 | 48 🟢 |
| Big tech USA | 99% | 8,4 | 7 🟡 | 7 🟡 | 7 🟡 |
| MSCI World | 95% | 42,0 | 37 🔴 | 11 🔴 | 54 🟢 |
| MSCI World | 99% | 8,4 | 11 🔴 | 7 🔴 | 13 🟡 |

Il modello storico è più adatto al rischio di breve termine; il modello a fattori è più informativo per orizzonti lunghi perché include le grandi crisi.
