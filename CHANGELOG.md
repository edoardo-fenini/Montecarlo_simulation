# Registro delle modifiche

## 1.3.0 (4 novembre 2026)

Versione di consolidamento. Nessuna funzione precedente è stata tolta. **I numeri del calcolo non sono cambiati**: il test di
non regressione (1.236 numeri chiave) è rimasto identico.

### Correzione di bug (prioritaria): l'app si fermava a fine analisi con `StreamlitDuplicateElementId`
- **Causa**: quando l'analisi B copre lo stesso periodo dell'analisi A (nessun titolo ha una storia più lunga del periodo comune), i due
  fan chart e i due istogrammi dei cali sono identici; Streamlit dava loro lo stesso ID automatico e interrompeva l'app subito dopo la
  simulazione. Riprodotto sulla 1.2 con l'esempio precaricato e con l'esempio ISIN, tutti i moduli attivi.
- **Correzione**: ogni elemento Streamlit che riceve un ID (grafici Plotly, tabelle, pulsanti di download, pulsanti, menu, interruttori,
  caselle) ha ora una `key` univoca e stabile: fan chart e cali per analisi (`fan_A`, `mdd_B` …), i tre download del report, il download
  della configurazione, la tabella del controllo dati, le tabelle e i download delle «Analisi salvate» (key dal nome della cartella, non
  dalla posizione nell'elenco), i pulsanti della barra laterale e della pagina iniziale, la casella «Aggiorna i dati».
- **Test**: simulazione completa nell'app con tutti i moduli per entrambi gli esempi (`tests/test_app_simulazione_completa.py`) e un
  controllo automatico che nessun elemento con ID resti senza `key` e che nessuna key si ripeta (`tests/test_chiavi_streamlit.py`).
  La prova nel browser (Playwright) completa un'analisi intera, apre tutte le schede, verifica che non compaiano errori Streamlit e scarica il report.
- Correzione collegata: se un'esecuzione dell'app si interrompe con un errore, Streamlit cancella lo stato dei widget non ancora disegnati e
  le impostazioni della barra laterale tornavano ai minimi (capitale 0 €, orizzonte 1 anno, tassi 0%). Ora una copia di sicurezza delle
  impostazioni (`stato_app.py`) le ripristina all'esecuzione successiva (e lo annota in `log.txt`).
- Gli expander, le immagini e le metriche non ricevono un ID da Streamlit (se non hanno una key) e non possono causare questo errore.

### Risultati vecchi nascosti
- Se dopo una simulazione cambiano titoli, pesi o impostazioni, se i prezzi in cache vengono aggiornati o se il controllo dei dati
  diventa rosso, i risultati sono nascosti e al loro posto compare l'avviso «Questi risultati non corrispondono più ai dati attuali:
  rilancia la simulazione», con il motivo. Un interruttore permette di rivederli comunque (l'avviso resta in cima).

### Controllo incrociato dei nomi (ISIN)
- Per ogni ISIN convertito, il nome di OpenFIGI è confrontato con quello di Yahoo (confronto tollerante: ignora maiuscole, accenti,
  punteggiatura e forme societarie come Inc, SpA/S.p.A., PLC, AG, NV, UCITS, ETF). Se sono molto diversi (somiglianza sotto
  `controllo_dati.somiglianza_nome_min`, default 0,4) la riga è **gialla** e si prova la quotazione successiva; l'avviso dice quale è stata
  scartata e perché. Se tutte le quotazioni hanno il nome diverso, o la quotazione è forzata da te, si usa quella con l'avviso.
- `nomi_attesi` resta come controllo aggiuntivo facoltativo.
- Le quotazioni elencate da OpenFIGI su borse non mappate (di cui non conosco il suffisso Yahoo) non sono più ignorate in silenzio: compaiono
  come **info** nella colonna «Dettagli» del controllo dati (senza cambiare il colore) e sono salvate nella cache degli ISIN.
- Il confronto dei nomi è nel nuovo modulo `nomi.py` (`controllo.somiglianza_nomi` funziona come prima).

### Importazione del portafoglio dal CSV del broker
- Nell'app (riquadro «📥 Importa il portafoglio dal broker (CSV)») e da riga di comando (`importa_portafoglio.py`): si carica il CSV con
  ISIN (o ticker) e quantità, oppure ISIN e controvalore; si vede un'**anteprima** (controvalori e pesi) e solo dopo la conferma il portafoglio
  viene creato (nella tabella dell'app, o in un file YAML).
- Pesi dai controvalori in EUR; se manca il controvalore, quantità × ultimo prezzo in EUR. Separatori `;` `,` e tab, decimali con la
  virgola o con il punto, righe d'intestazione del broker e righe di totale saltate, titoli ripetuti sommati, colonne di costo ignorate.
- Esempio `esempi/portafoglio_broker_esempio.csv`; formato documentato nel README.

### Ricerca per nome
- Nell'app, riquadro «🔍 Cerca un titolo per nome»: fino a 10 risultati (nome, ticker, ISIN se si cerca un ISIN, borsa, valuta, tipo) da
  aggiungere al portafoglio scelto (anche nuovo) con un clic su ➕. Solo azioni, ETF, fondi e indici; nessun doppione. Modulo `ricerca.py`.

### Prova nel browser nel repository
- `tests/e2e/`: prova Playwright dell'app con una finta rete (nessun accesso a internet), eseguita nel workflow **Test** (Linux).
- Corretto il falso FAIL della 1.2 sulla tabella in canvas: sotto la tabella «Controllo dati» c'è ora la riga di testo «Ticker usati:
  ISIN → ticker …» (utile anche per gli screen reader) e la prova verifica quella, oltre al report scaricato.
- Controlli: ISIN errato → «Avvia simulazione» disattivato; cambio di quotazione dal menu (SWDA.MI → EUNL.DE) che si ritrova nel report;
  risultati vecchi nascosti dopo un cambio; analisi completa con tutte le schede senza errori Streamlit. `requirements-e2e.txt`.

### Release automatica
- Nuovo workflow `release.yml`: con il push di un tag `vX.Y.Z` (o avviandolo a mano da Actions → Release → Run workflow con la versione)
  lancia i test, costruisce lo zip, controlla il contenuto, crea la release con le note prese dalla sezione giusta di `CHANGELOG.md` e allega
  lo zip. Usa solo il `GITHUB_TOKEN` del repository. `test.yml` è richiamabile dagli altri workflow.
- `strumenti/note_release.py` valida il nome del tag (solo `vX.Y.Z`) ed estrae le note. `zip-release.yml` resta per le release create a mano.
- README: spiegazione dei tag vecchi (`V_1.0.1`, `V_1.1.0`, `V_1.2.0`, `prova`, non cancellati) e della procedura passo passo dal sito.

### Altro
- Report «progresso, debolezze e sviluppi» ora nel repository: `docs/PROGRESSO_DEBOLEZZE_SVILUPPI.md`.
- 87 nuovi test (199 in tutto), tutti senza internet; i workflow «Test» e «Prova su Mac» girano a ogni push.

## 1.2.0 (4 novembre 2026)

Nessuna funzione precedente è stata tolta. **I numeri del calcolo non sono cambiati**: il test di non regressione
(1.236 numeri chiave) è rimasto identico.

### Supporto agli ISIN
- Per ogni titolo (tabella dell'app, benchmark, file YAML) si può scrivere un ticker Yahoo **oppure un ISIN**: è riconosciuto
  da solo (2 lettere + 9 caratteri + cifra di controllo) e la cifra di controllo viene verificata.
- Conversione in ticker con OpenFIGI (gratuito, nessuna chiave obbligatoria) e, come riserva, la ricerca di Yahoo Finance
  (`yfinance.Search`). Ogni ticker candidato è verificato su Yahoo (valuta, storia, volumi, ultimo scambio).
- Scelta della quotazione con una regola configurabile (`isin.preferenze`, default EUR → `.MI` → `.DE` → `.AS` → altre; a parità
  più storia e più volumi; le quotazioni ferme o con volumi trascurabili vanno in fondo). Nell'app un menu mostra la quotazione scelta
  e le altre trovate; `isin_scelte` in configurazione forza una quotazione.
- Conversioni in cache (`cache_prezzi/isin_ticker.json`). Chiave OpenFIGI facoltativa (`isin.openfigi_chiave` o variabile
  `OPENFIGI_API_KEY`), mai scritta nei report.
- Il report mostra per ogni titolo l'ISIN e il ticker usato (tabella «Titoli usati», `titoli.csv`, Excel).
- Nuovo esempio `configurazioni/esempio_isin.yaml` (azioni ed ETF europei).

### Controllo dei dati prima della simulazione
- Tabella «Controllo dati» con semaforo per titolo (input, ticker usato, nome, borsa, valuta, fonte, prima/ultima data, anni di
  storia, % giorni mancanti, ultimo prezzo, esito), riepilogo in cima («12 titoli trovati, 1 avviso, 0 errori»).
- Rosso (blocca): non trovato / ISIN errato, nessun prezzo, meno di 1 anno di storia, ultimo prezzo oltre 30 giorni, prezzi
  zero o negativi. Giallo (avviso): meno di 3 anni, oltre 5% di giorni mancanti, ultimo prezzo oltre 7 giorni, movimenti
  giornalieri estremi, nome molto diverso da quello atteso (`nomi_attesi`). Soglie in `controllo_dati`.
- App: pulsante **Controlla i dati** separato; con almeno un rosso **Avvia simulazione** è disattivato con un messaggio su cosa
  correggere. Sostituisce il vecchio riquadro «Controllo dei ticker».
- Riga di comando: `confronta.py` stampa la tabella e si ferma con un messaggio chiaro se c'è un rosso; `--solo-controllo`
  esegue solo la verifica.
- La tabella è nel report (Sintesi), in `dati_csv/controllo_dati.csv` e in una scheda Excel.

### Altro
- Le fonti di prezzi segnalano quanti prezzi zero o negativi hanno scartato (`prezzi_non_positivi` nei metadati).
- Prezzi in cache più vecchi di 7 giorni: il controllo prova a riscaricarli prima di dichiararli vecchi.
- 62 nuovi test (ISIN, scelta della quotazione, ogni regola del semaforo, blocco con un rosso, app, report), tutti senza internet.

## 1.1.0 (3 novembre 2026)

Nessuna funzione della 1.0 è stata tolta. **I numeri del calcolo non sono cambiati**: il test di non regressione
(1.236 numeri chiave con configurazione e seed fissi) è rimasto identico dall'inizio alla fine dello sviluppo, anche con
il calcolo in parallelo. Unica differenza sui dati reali: sul Mac il cambio del dollaro prima del 2003 ora viene
scaricato correttamente (vedi Correzioni).

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
