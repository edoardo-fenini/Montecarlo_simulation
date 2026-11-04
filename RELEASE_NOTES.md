# v1.4.0 – Fondi comuni e costi

Nessuna funzione tolta; il test di non regressione è identico. Le note complete vengono dalla sezione 1.4.0 di `CHANGELOG.md`.

## Novità
- **Fondi comuni non quotati**: l'ISIN viene classificato (azione, ETF/ETC, fondo comune); i fondi si cercano su Yahoo con i codici `0P…`;
  se non si trovano puoi **caricare lo storico delle quote (CSV)** o scegliere un **proxy**. Tutto è segnalato nel controllo dati e nel report.
- **Costi annui** di fondi ed ETF sottratti dal rendimento atteso (default prudente 1,5% fondi, 0,3% ETF, con avviso giallo).
- **Rendimento atteso** visibile prima della simulazione, con avvisi e controllo di plausibilità dei risultati.

## Come aggiornare dalla 1.3.1
Scarica `confronta-portafogli-v1.4.0.zip`, estrailo in una nuova cartella, copia `configurazioni/` (i tuoi file), `cache_prezzi/` e `report/`
dalla cartella vecchia e fai doppio clic su `Installa.command`.
