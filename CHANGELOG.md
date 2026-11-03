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

### App più curata
- Tema sobrio (blu notte come colore principale, angoli arrotondati) valido in modalità chiara e scura; i blocchi del
  report nell'app usano colori neutri leggibili in entrambe.
- Palette fissa e coerente in app, report e PDF (`stile.py`, Okabe-Ito, benchmark sempre grigio); il colore non è mai
  l'unico segnale: tratteggi, motivi ed etichette diversi per ogni portafoglio.
- Fan chart e distribuzione dei cali interattivi (Plotly): passando il mouse si leggono mediana, 5° e 95° percentile;
  clic sulla legenda per nascondere un portafoglio. Nel PDF restano grafici statici con lo stesso stile.
- Card riassuntive (valore mediano, probabilità di perdita, calo tipico, confronto col benchmark e livello di rischio).
- Pagina iniziale in 3 passi con l'esempio pronto da lanciare; aiuto «?» su ogni opzione.
- Barra di avanzamento con fase corrente e tempo stimato.
- Tabelle grandi in sezioni espandibili; errori spiegati in modo semplice, dettagli tecnici solo in `log.txt`.

### Funzioni in più
- «Analisi salvate»: ogni simulazione dell'app viene salvata in `report/` (HTML, PDF, Excel, CSV, configurazione e
  `riassunto.json`); la scheda elenca le analisi, le riapre e ne confronta due affiancate.
- Prova rapida dei pesi nella scheda Sintesi: cursore benchmark/satellite con ricalcolo veloce (2.000 simulazioni,
  risultato approssimato e indicato come tale).
- Esportazione Excel (`report.xlsx`): una scheda per orizzonte più sintesi, metriche, stress test, rendimenti attesi e
  titoli; numeri veri con formati € e %.
- Configurazioni di esempio: `core_satellite_80_20.yaml` e `etf_europei.yaml` (oltre ai tre portafogli).

### Prestazioni e affidabilità
- Le simulazioni indipendenti (principale, seed di verifica, rischio sul singolo titolo, analisi A e B, modelli) girano
  in parallelo su più processori, con risultati identici (verificato da un test). Su una macchina a 4 core l'esecuzione
  completa di default (20.000 simulazioni) passa da circa 290 a circa 125 secondi; su un Mac recente con più core è più
  veloce. Opzione `parallelo: auto | si | no`; se il parallelismo non è disponibile si torna da soli al calcolo in sequenza.
- Nell'app la stessa configurazione rilanciata con gli stessi dati non viene ricalcolata.
- File di log `log.txt` nella cartella del programma (app e riga di comando), con i tempi delle fasi principali.

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
