# Registro delle modifiche

## 1.1.0 (in sviluppo, ramo `v1.1`)

### Sicurezza delle modifiche
- Test di non regressione (`tests/test_non_regressione.py`): con configurazione e seed fissi, 1.236 numeri chiave
  (mediane, percentili, probabilità, drawdown, stress test, convergenza, modelli) devono restare identici.

## 1.0.0 (3 novembre 2026)
- Prima versione: motore generico da YAML, quattro metodi di rendimento atteso, analisi A/B/C, moduli opzionali,
  portafogli misti, riga di comando, app Streamlit, report HTML/PDF/CSV, script per Mac, prova automatica su macOS.
- Default 20.000 simulazioni dopo la verifica della convergenza.
