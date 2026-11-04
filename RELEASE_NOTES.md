# v1.3.1 – Correzioni dopo la prova su un Mac reale

Versione di correzione della 1.3.0. Nessuna funzione tolta; **i risultati del calcolo sono identici** (test di non regressione).
Le note complete vengono dalla sezione 1.3.1 di `CHANGELOG.md`.

## Correzioni
- **La prova rapida di Installa.command non fallisce più nello zip**: un test leggeva un file presente solo nel repository
  (`.github/workflows/release.yml`). Ora i test di questo tipo sono saltati con un messaggio chiaro.
- **La prova rapida dura davvero circa 30 secondi**: esegue solo i test veloci (marker `rapido`), non tutta la suite.
- **Modello GARCH**: se la stima non converge (avviso di scipy «Inequality constraints incompatible») il risultato non viene più usato
  in silenzio: si riprova con altri punti di partenza e, se serve, si usa la volatilità costante per quel titolo, con un avviso nel report.
  Riguarda solo il «Confronto tra modelli»; i risultati principali non cambiano.
- **Prova automatica su Mac come l'utente**: zip della release, cartella pulita, Installa.command, prova rapida, Avvia.command.

## Come aggiornare dalla 1.3.0
Scarica `confronta-portafogli-v1.3.1.zip` qui sotto, estrailo in una nuova cartella, copia `configurazioni/` (i tuoi file), `cache_prezzi/`
e `report/` dalla cartella vecchia e fai doppio clic su `Installa.command`.
