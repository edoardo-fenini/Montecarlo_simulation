# Confronto tra modello «storico» e modello «a fattori» (4 novembre 2026)

Esempio `configurazioni/esempio_tre_portafogli.yaml` (3 portafogli + MSCI World), dati reali Yahoo del 4/11/2026, 20.000 simulazioni, 15 anni,
capitale 5.000 €, rendimento atteso con metodo beta (2% / 4%). Stesso seed. Valori in euro; mediana e 5° percentile sono del valore finale.
«Storico A» usa il periodo comune dei titoli (dal 1/7/2021, 5,4 anni: c'è Palantir); «Storico B» il periodo lungo dal 2007 (pesi ridistribuiti
tra i titoli già quotati); «Fattori» usa la storia dei fattori dal 2000.

| | Cyber security | Banche / PE | Big tech USA | MSCI World |
|---|---|---|---|---|
| **Volatilità simulata** storico A | 35,6% | 24,2% | 29,8% | 14,0% |
| storico B | 32,9% | 31,5% | 28,6% | 17,4% |
| fattori | 29,2% | 27,3% | 29,7% | 19,0% |
| **Max drawdown mediano a 15 anni** storico A | −74% | −51% | −66% | −32% |
| storico B | −71% | −66% | −61% | −42% |
| fattori | −66% | −60% | −67% | −43% |
| **Mediana a 5 / 10 / 15 anni** storico A | 5.015 / 5.082 / 5.130 | 6.161 / 7.526 / 9.250 | 5.654 / 6.433 / 7.219 | 6.347 / 8.041 / 10.103 |
| storico B | 5.337 / 5.669 / 6.039 | 5.402 / 5.804 / 6.215 | 5.801 / 6.710 / 7.784 | 6.207 / 7.625 / 9.287 |
| fattori | 5.614 / 6.389 / 7.132 | 5.981 / 7.070 / 8.291 | 5.596 / 6.316 / 7.130 | 6.117 / 7.431 / 8.966 |
| **5° percentile a 5 / 10 / 15 anni** storico A | 1.624 / 1.010 / 715 | 2.900 / 2.618 / 2.508 | 2.071 / 1.550 / 1.301 | 3.975 / 4.105 / 4.505 |
| storico B | 1.762 / 1.211 / 911 | 2.048 / 1.469 / 1.164 | 2.274 / 1.833 / 1.594 | 3.341 / 3.261 / 3.324 |
| fattori | 2.060 / 1.529 / 1.248 | 2.330 / 1.922 / 1.669 | 1.977 / 1.457 / 1.166 | 3.271 / 3.123 / 3.091 |

## Lettura in parole semplici
- Con lo **storico A** i risultati dipendono da soli 5 anni, in cui la tecnologia ha avuto un gran rialzo e un crollo (2022): Cyber security sembra il portafoglio
  più rischioso (35,6%) e le banche il più tranquillo (24%), e il benchmark ha una volatilità bassa (14%) perché in quei 5 anni il mercato è stato calmo.
- Con i **fattori** i tre portafogli diventano più simili tra loro (29%, 27%, 30%): il rischio di Cyber security non è più «eredità» del solo 2021-2026, ma viene
  dalle sue esposizioni (mercato, tecnologia, growth) viste anche nel 2000-2002 e nel 2008. Le banche risultano più rischiose (27% contro 24%) perché il
  settore finanziario nel 2008 ha avuto un crollo che i 5 anni recenti non contengono.
- Il benchmark sale dal 14% al 19%: i fattori contengono le grandi crisi di mercato, lo storico recente no. È la differenza principale ed è voluta.
- Sul lungo periodo il modello a fattori dà **mediane più alte a Cyber security** (7.132 contro 5.130) perché, a parità di rendimento atteso, il rischio stimato più
  basso («volatility drag» minore) lascia la mediana più vicina alla media. Per le banche e il benchmark avviene l'opposto (più rischio, mediana più bassa).
- I 5° percentili (casi sfavorevoli) a 15 anni sono più alti per Cyber security (1.248 contro 715) e più bassi per il benchmark (3.091 contro 4.505): il modello a
  fattori «toglie» rischio ai titoli con poca storia e lo «dà» al mercato che ha una storia lunga.

## Backtest del VaR a 1 giorno (periodo A, 839 giorni di prova dopo la finestra di 2 anni)
Semafori (verde / giallo / rosso) per i due modelli:

| Serie | VaR 95% storico | VaR 95% fattori | VaR 99% storico | VaR 99% fattori |
|---|---|---|---|---|
| Cyber security | verde | giallo | verde | rosso |
| Banche / PE | verde | rosso (troppo prudente: 15 sforamenti su 42 attesi) | verde | giallo |
| Big tech USA | verde | verde | giallo | giallo |
| MSCI World | rosso (sforamenti a grappolo) | rosso (troppo prudente) | rosso | rosso |

Il VaR del modello storico (finestra di 2 anni) è più calibrato nel periodo recente; il modello a fattori, che usa la covarianza di tutta la storia dal 2000,
è più prudente quando il mercato è calmo (sovrastima il rischio di banche e benchmark) e meno quando i titoli hanno un rischio proprio alto (Cyber security al 99%).
Il test sul benchmark fallisce per entrambi per gli sforamenti raggruppati (aprile 2025). Un test su 3,3 anni ha poca forza.

## Controllo di plausibilità
Il controllo del rendimento medio dei percorsi (v1.4) ha dato un errore nel solo **storico, analisi B, portafoglio Banche** (atteso 7,40%, simulato 6,58%, tolleranza
±0,59%) con i dati reali di oggi: è un comportamento del codice esistente (non toccato in questa versione), da esaminare. Con il modello a fattori il controllo passa.
