# Registro delle modifiche

## 1.1.0 (in sviluppo, ramo `v1.1`)

### Dati più affidabili
- Più fonti gratuite senza chiave API, provate in ordine: Yahoo Finance (yfinance) → Yahoo Finance API diretta → Stooq;
  per i cambi anche la Banca Centrale Europea. Ogni fonte con tentativi ripetuti e attesa crescente, timeout di 25 secondi.
- Modalità offline: senza internet si usano i prezzi in cache, con un avviso e la data dell'ultimo aggiornamento.
- Prezzi da file CSV (pulsante «Carica prezzi da file» nell'app, oppure `prezzi_da_file:` in configurazione); esempio in
  `esempi/prezzi_esempio.csv`. I prezzi manuali non vengono mai sovrascritti.
- «Dati aggiornati al …» nell'app e nel report; nel report fonte, borsa e ultimo dato di ogni titolo.
- Controllo dei ticker nell'app: nome completo, borsa, valuta, anni di storia e fonte.
- `strumenti/verifica_fonti.py`: mostra quali fonti rispondono (eseguito anche nella prova automatica su Mac).

### Report più leggibile
- Copertina e indice cliccabile (HTML e PDF, con i segnalibri del PDF).
- Nuova prima sezione «In una pagina»: una scheda per portafoglio con valore mediano, probabilità di perdita, calo massimo
  tipico, volatilità rispetto al benchmark e livello di rischio da 1 a 5 (numero, nome, quadratini e colore; criteri spiegati).
- Le tabelle delle analisi A e B non sono più affiancate: nel PDF entrano sempre nella pagina; titoli tenuti con la tabella.
- Percentuali sempre con una cifra decimale (TER con due), migliaia con il punto, € dopo il numero.
- Sotto ogni grafico una spiegazione automatica di cosa guardare.
- Nei fan chart la zona sotto il capitale investito è colorata.

### Correzioni
- Sul Mac le richieste dirette (FRED, BCE) fallivano con un errore di certificato SSL: ora si usano i certificati di
  `certifi`. Nella 1.0 il cambio del dollaro prima del 2003 (FRED) poteva mancare sul Mac: interessava solo l'analisi C.
- Yahoo diretto: richiesta con date esplicite per avere prezzi giornalieri (con `range=max` Yahoo li dà mensili).

### Sicurezza delle modifiche
- Test di non regressione (`tests/test_non_regressione.py`): con configurazione e seed fissi, 1.236 numeri chiave
  (mediane, percentili, probabilità, drawdown, stress test, convergenza, modelli) devono restare identici.

## 1.0.0 (3 novembre 2026)
- Prima versione: motore generico da YAML, quattro metodi di rendimento atteso, analisi A/B/C, moduli opzionali,
  portafogli misti, riga di comando, app Streamlit, report HTML/PDF/CSV, script per Mac, prova automatica su macOS.
- Default 20.000 simulazioni dopo la verifica della convergenza.
