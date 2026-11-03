# STATO del progetto

## Fatto
- [x] Tappa 1: dati scaricati (`python scarica_dati.py`), convertiti in EUR e controllati (`python dati.py` -> `data/controlli.txt`).

## Da fare
- [x] Tappa 2: simulazione base + report.html (analisi A e B), test pytest (5 passano)
- [ ] Tappa 3: stress test
- [ ] Tappa 4: robustezza punto 1 (analisi C con proxy)
- [ ] Tappa 5: robustezza punti 2-4 (modelli, sensibilità, rischio idiosincratico)

## Come riprendere
Leggi questo file, poi `config.yaml`. Parametri scelti dall'utente: 5.000 € iniziali, nessun versamento, 15 anni, risultati a 5/10/15 anni.
Benchmark: iShares Core MSCI World (IWDA.AS, IE00B4L5Y983, TER 0,20%), prima del 2009 indice MSCI World Net (^990100-USD-STRD) meno TER.
