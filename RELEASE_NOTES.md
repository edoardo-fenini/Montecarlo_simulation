# v1.5.0 – Modello di rischio a fattori

Nessuna funzione tolta; il test di non regressione è identico. Le note complete vengono dalla sezione 1.5.0 di `CHANGELOG.md`.

## Novità
- **Modello a fattori** (opzione «Modello di simulazione»): ogni titolo è scomposto in esposizioni a mercato, regioni, settori, stile, tassi e valute più una parte
  specifica; utile per titoli e fondi con poca storia, che così «vivono» anche il 2000-2002 e il 2008. Il default resta il modello storico.
- **Da dove viene il rischio**: quota del rischio per gruppo di fattori, esposizioni, R² dei titoli e una sintesi in italiano semplice.
- **Validazione del VaR** (facoltativa): backtest con test di Kupiec e Christoffersen e semaforo.
- Scelte rapide **Prudente / Base / Ottimista** per tasso privo di rischio e premio di mercato; impostazioni più robuste contro gli azzeramenti.

## Come aggiornare dalla 1.4
Scarica `confronta-portafogli-v1.5.0.zip`, estrailo in una nuova cartella, copia `configurazioni/`, `cache_prezzi/` e `report/` dalla vecchia, poi doppio clic su `Installa.command`.
