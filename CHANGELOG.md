# Registro delle modifiche

## 1.5.0 (4 novembre 2026)

Versione «modello di rischio a fattori». Nessuna funzione tolta; **il test di non regressione (1.236 numeri) è identico**. Il modello `storico` resta il default.

### Modello a fattori
- Nuova opzione `modello_simulazione: fattori` (YAML) / «Modello di simulazione» (app). Ogni titolo = esposizioni a fattori comuni + parte specifica;
  regressione ridge su rendimenti settimanali in euro (penalità scelta per GCV, minimo 0,5 × settimane, mercato non penalizzato); simulazione con block
  bootstrap dei fattori (storia dal 2000) e residui ricampionati per titolo, indipendenti tra titoli; rendimento atteso e costi applicati come prima.
- Fattori in `modelli/fattori.yaml` (modificabile): mercato mondiale (MSCI World), regioni (USA, Europa, Giappone, Emergenti), 7 settori USA, growth-value,
  piccole imprese, momentum, qualità, obbligazioni lunghe USA, dollaro/euro. Le date di inizio sono nel report e nel README. Il benchmark è trattato come il fattore mercato.
- Con i fattori si esegue solo l'analisi A (la storia lunga entra dai fattori).

### Da dove viene il rischio
- Scheda del report e dell'app: quota di rischio per gruppo (barre impilate), esposizioni dei portafogli, R² dei titoli con avviso sotto 0,3, sintesi in italiano
  sulle scommesse comuni. Disponibile anche con il modello storico (modulo `scomposizione_rischio`). CSV: `fattori_*.csv`.

### Validazione del modello (backtest del VaR)
- Modulo `backtest_var` (disattivato di default): VaR a 1 giorno 95%/99% su finestra mobile di 2 anni per benchmark e portafogli, modelli storico e fattori,
  test di Kupiec e di Christoffersen con semaforo, grafico dei rendimenti contro il VaR. CSV `backtest_var.csv`.

### Impostazioni non azzerate
- `stato_app.conserva` ricorre ai valori predefiniti se un campo manca anche nella copia di sicurezza (mai 0 per caso); pulsanti Prudente (2% / 3%), Base (2,5% / 4%),
  Ottimista (2,5% / 5%) per tasso privo di rischio e premio di mercato (campi sempre modificabili, anche a 0). Default invariati (2% / 4%). La causa dell'azzeramento
  osservato non è stata riprodotta; verificate le sequenze con `AppTest` (test nuovi).

### Test
- `test_fattori.py`, `test_fattori_e2e.py`, `test_backtest_var.py`, `test_impostazioni_non_azzerate.py`; app completa con i fattori (AppTest e browser Playwright).

## 1.4.0 (4 novembre 2026)

Versione «fondi comuni e costi». Nessuna funzione tolta. **Il test di non regressione (1.236 numeri) è identico.**
Modifiche volute al calcolo (spiegate): il default dei costi per gli ETF senza TER indicato passa da 0,20% a 0,30% e i fondi comuni
(tipo di strumento «fondo comune») non sono più trattati come azioni nel rischio sul singolo titolo e negli stress test; nessuno dei due casi
compare nei dati finti del test di non regressione.
Il cambio dei default del metodo beta (2,5% / 4%) **non è stato fatto**, su richiesta: restano 2% e 4%.

### Tipo di strumento e fondi comuni
- OpenFIGI (`securityType`, `securityType2`) classifica ogni ISIN come azione, ETF/ETC o fondo comune; nuova colonna «Tipo» nel controllo dati
  (app, report, CSV, Excel). I quattro ISIN di prova (LU0073232471, LU0552385295, LU0070214290, LU0210536198) risultano fondi comuni lussemburghesi.
- Ricerca automatica dei fondi (`fondi.py`): codici Morningstar di Yahoo («0P…»); candidato scelto dopo il confronto di gestore, nome, valuta,
  classe a accumulazione/distribuzione, lunghezza della storia e ultimo prezzo; avviso giallo perché la classe non è certa. Esito in cache.
- Storico delle quote da CSV collegato all'ISIN (`nav.py`): separatore, decimali con la virgola, formati di data e intestazioni italiane/inglesi
  riconosciuti da soli, anteprima, valuta, fonte «CSV importato»; da YAML con `prezzi_da_file`; avviso giallo per le classi a distribuzione.
- Proxy dichiarato (`proxy_titoli`), segnalato nel controllo dati e nel report. Errore rosso chiaro con i due pulsanti per i fondi non trovati.

### Costi di fondi ed ETF
- Colonna «Costi annui (%)» nell'app e chiave `costi` nel YAML; default prudente (fondi 1,5%, ETF/ETC 0,3%) con avviso giallo; tabelle dei costi
  e dell'effetto sul rendimento atteso nel report; il benchmark usa il suo TER una sola volta.

### Rendimento atteso
- Riquadro «Rendimento atteso che verrà usato» (app e riga di comando); campo vuoto o non numerico = errore rosso (mai 0);
  giallo con premio di mercato 0 o rendimento sotto l'1%; controllo di plausibilità dei risultati (errore rosso e report non scritto se non coincide).
- Già presenti dalla 1.3.1 e non toccati: correzione del ConvergenceWarning del GARCH e prova rapida di `Installa.command`.

### Altro
- Corretto: dopo un controllo dati rosso risolto (per esempio caricando lo storico delle quote) «Avvia simulazione» restava disattivato fino al
  clic successivo.
- Nuovi test offline (`test_fondi_v14.py`, `test_rendimento.py`) e prova nel browser: fondo non trovato → errore rosso con i due pulsanti → CSV → verde → simulazione.

## 1.3.1 (4 novembre 2026)

Versione di correzione. Nessuna funzione tolta. Il test di non regressione (1.236 numeri) è identico; il modello GARCH del
«Confronto tra modelli» dà gli stessi numeri di prima tutte le volte che la stima converge.

### Correzione: stima GARCH non convergente usata in silenzio
- **Cosa succedeva**: nel modulo «Confronto tra modelli» il GARCH(1,1) di ogni titolo si stima per massima verosimiglianza con
  l'ottimizzatore SLSQP (parametri omega, alpha, beta con i vincoli omega > 0, alpha ≥ 0, beta ≥ 0, alpha + beta < 1). Su serie senza
  raggruppamenti di volatilità riconoscibili (alpha finisce sul bordo 0, verosimiglianza piatta) o quasi costanti (prezzo fermo, varianza
  quasi nulla) il sottoproblema quadratico di SLSQP diventa mal condizionato e l'ottimizzatore si ferma con il codice 4, «Inequality
  constraints incompatible» (`ConvergenceWarning` visto sul Mac nella prova di Installa.command, con i dati sintetici dei test). I parametri
  restituiti sono l'ultimo tentativo, non un ottimo, e venivano usati lo stesso.
- **Effetto sui risultati**: solo sul modello GARCH del confronto tra modelli (sezione «Robustezza»); i risultati principali (block
  bootstrap), gli stress test e il rischio sul singolo titolo non usano il GARCH. Con parametri non ottimi la volatilità simulata dal GARCH
  per quel titolo poteva essere sbagliata (di solito di poco: la volatilità media resta vicina a quella storica).
- **Correzione**: la stima standard è identica a prima; se non converge si riprova da altri tre punti di partenza; se nessuna stima converge
  con parametri validi, per quel titolo si usa la **volatilità costante** (alpha = beta = 0, equivale a ripescare i rendimenti giornalieri). Il
  ripiego non è mai silenzioso: avviso nel log, nella Sintesi e nella sezione «Robustezza» del report («Avviso sul modello GARCH»). Le
  serie (quasi) costanti non vengono nemmeno stimate. Gli avvisi di scipy non arrivano più al terminale.
- 5 nuovi test (`tests/test_garch.py`), compreso un ottimizzatore finto che risponde sempre «codice 4».

### Correzione: la prova di Installa.command falliva nello zip della release
- `tests/test_release.py` leggeva `.github/workflows/release.yml`, che sta solo nel repository (lo zip lo esclude): sul Mac
  «1 failed». Ora i test che dipendono da file presenti solo nel repository usano `tests/solo_repository.richiede(...)` e, se il
  file manca, sono **saltati con un messaggio chiaro** («File presenti solo nel repository di sviluppo … non è un errore»).
  Verificato eseguendo l'intera suite dentro lo zip costruito come nella release: era l'unico test interessato.
- La prova rapida di `Installa.command` eseguiva **tutta** la suite (sul Mac 153 secondi invece dei 30 annunciati). Ora esegue solo i
  test con il marker pytest **`rapido`** (`pytest -m rapido`): veloci, senza internet, compresi il test di non regressione, l'avvio
  dell'app e la creazione del PDF. Sono esclusi i test lenti elencati in `tests/conftest.py` (simulazioni complete nell'app, interazioni
  AppTest, calcolo in parallelo, prova nel browser). Tempo misurato: 31 secondi su Linux a 4 core (sul Mac di GitHub la suite gira circa il 40%
  più veloce). La suite completa resta nei workflow «Test» e «Prova su Mac» e per chi sviluppa.

### Prova su Mac «come l'utente»
- Nuovo job `zip-release` in «Prova su Mac» (macOS 14, Apple Silicon): costruisce lo zip esattamente come la release (o, avviandolo a mano,
  scarica lo zip di una release pubblicata), lo estrae in una cartella pulita fuori dal repository, esegue `Installa.command
  --non-interattivo`, controlla che la prova rapida non abbia test falliti e duri al massimo 75 secondi (obiettivo circa 30), poi avvia e
  ferma `Avvia.command`. Avrebbe trovato il problema di `release.yml` prima della 1.3.0.
- Lo zip si crea con `strumenti/crea_zip.sh`, usato sia dal workflow «Release» sia da questa prova (stesso contenuto, stessi controlli).

### Altro
- 12 nuovi test (211 in tutto). Note di rilascio v1.3.1, README e report «progresso, debolezze e sviluppi» aggiornati.

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
