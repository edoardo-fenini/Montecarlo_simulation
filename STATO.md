# STATO del progetto

## Fatto (tutte le tappe)
- [x] Tappa 1: dati scaricati (`python scarica_dati.py`), convertiti in EUR e controllati (`data/controlli.txt`).
- [x] Tappa 2: simulazione base (bootstrap a blocchi, 20.000 sim.), report.html, test pytest (5 passano).
- [x] Tappa 3: stress test (A e B, senza versamenti, anni per tornare a 5.000 €).
- [x] Tappa 4: robustezza 1 – analisi C dal 1999 con proxy XLK/XLF.
- [x] Tappa 5: robustezza 2-4 – modelli (bootstrap/Student-t/GARCH), sensibilità al rendimento atteso (3/6/9% e settoriale), rischio sul singolo titolo.

## Come riprendere / modificare
- `python confronta.py` rigenera tutto (usa i risultati in `risultati/`; con `--rifai` ricalcola, circa 25 minuti). `--veloce` per prove.
- Parametri scelti: 5.000 € iniziali, nessun versamento, 15 anni, risultati a 5/10/15 anni, rendimento atteso 6% (media aritmetica, non mediana).
- Benchmark: iShares Core MSCI World (IWDA.AS, IE00B4L5Y983, TER 0,20%); prima del 2009 indice MSCI World Net (proxy).
- Idee per varianti: rendimento 6% come mediana (geometrico), pesi diversi, versamento mensile, orizzonte più lungo.
