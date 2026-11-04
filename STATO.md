# STATO del progetto – strumento riutilizzabile

## Tappe
- [x] 1. Motore generico e configurabile (`configurazione.py`, `dati.py`, `analisi.py`, `simula.py`, `metriche.py`) + test
- [x] 2. Script da riga di comando `confronta.py --config ...` -> report/AAAA-MM-GG_nome/ (HTML, PDF con reportlab, CSV con ; e virgola decimale per Excel)
- [x] 3. App Streamlit `app.py` (verificata in headless: simulazione completa, schede, download, errori chiari)
- [x] 4. `Installa.command` (uv + Python 3.12 dentro la cartella: .uv, .python, .venv) e `Avvia.command` (porta libera, solo 127.0.0.1, apre il browser) — provati su Linux in una copia pulita senza uv
- [x] 5. README passo passo, GitHub Action `.github/workflows/zip-release.yml` (zip allegato alla release), esempio `esempi/2026-11-03_tre_portafogli_metodo_beta/`
- [ ] Release v1.0.0: vedi sotto (tappa 5)

## Versione 1.1 (ramo `v1.1`, poi pull request verso main)
- [x] 0. Rete di sicurezza: 17 test verdi; test di non regressione (1.236 numeri, dati sintetici, seed fisso)
- [x] 1. Dati più affidabili: `fonti.py` (yfinance → Yahoo diretto → Stooq; BCE per i cambi; 3 tentativi 1,5/3/6 s; timeout 25 s),
      offline con cache, CSV manuali, freschezza, controllo ticker. Da qui Stooq è bloccato dalla rete della sessione e Yahoo diretto
      risponde 429: la verifica reale è nel workflow macOS (passo «Quali fonti di prezzi rispondono»).
      Scelta: User-Agent onesto ("confronta-portafogli/1.1"), nessun tentativo di aggirare i limiti di Yahoo.
- [x] 2. Report più leggibile: copertina, indice cliccabile e segnalibri PDF, «In una pagina» con livello di rischio 1-5
      (volatilità simulata: <8% / 8-14% / 14-20% / 20-30% / >=30%, ispirato alla scala SRI), tabelle A e B separate,
      percentuali con un decimale, didascalie automatiche, zona sotto il capitale nei fan chart. PDF controllato pagina per pagina.
      Verifica fonti sul Mac di GitHub: yfinance OK, Yahoo diretto OK (ma con range=max dava dati mensili: corretto),
      BCE falliva per certificati SSL (corretto con certifi, anche per la FRED), Stooq non restituisce dati.
- [x] 3. Estetica: tema (Streamlit 1.66 ha un solo [theme]: impostati solo colore principale #3366A3, angoli e palette, validi
      in chiaro e scuro; con un tema personalizzato lo scuro si sceglie da ⋮ → Settings → Theme), stile.py, Plotly (fan chart,
      cali), card, pagina iniziale, aiuto, avanzamento con stima, log.txt. Provata in browser headless in chiaro e scuro.
- [x] 4. Funzioni in più: analisi salvate (report/AAAA-MM-GG_HHMMSS_nome con riassunto.json) e confronto tra due,
      prova rapida dei pesi (analisi.prova_pesi, 2.000 simulazioni), Excel (openpyxl), configurazioni core_satellite_80_20 ed
      etf_europei (ETF verificati su Yahoo; TER lasciati al default 0,20% perché non verificati).
- [x] 5. Qualità e prestazioni: tempi misurati (dati ~1 s, simulazioni ~95%, stress ~10 s, report ~5 s); parallelismo a livello
      di lavori (ProcessPoolExecutor, spawn): 291 s -> 123 s su 4 core, numeri identici (test). Ottimizzazioni interne al motore
      scartate: richiederebbero di riordinare i calcoli (rischio di cambiare i numeri). Cache di sessione nell'app, log.txt.
      ruff (commit separato 17a97e6, «All checks passed»), type hints sulle funzioni principali, nessuna funzione inutilizzata.
      Misura su Mac reale: passo informativo nel workflow «Prova su Mac».
- [x] 6. README con 3 screenshot, CHANGELOG, RELEASE_NOTES v1.1.0, esempio completo; tempo sul Mac M1 (3 core) di GitHub
      con i default: 102 s. Pull request #1 unita in main (2ef9b61) dopo 50 test verdi e prova su Mac verde.
- [ ] Release v1.1.0: da pubblicare dal sito (Claude non ha lo strumento): Releases → Draft a new release → tag v1.1.0
      (Create new tag on publish) → Target main → testo di RELEASE_NOTES.md → Publish; poi controllare in Actions lo zip.
- [ ] Ramo predefinito: impostare main dal sito (Settings → General → Default branch).

Test di non regressione: identico dall'inizio alla fine della 1.1 (anche in parallelo). Nessun numero del calcolo è cambiato.

## Versione 1.2 (ramo `claude/optimistic-gates-68p7ry`): ISIN e controllo dei dati
- [x] 1. `isin.py`: riconoscimento + cifra di controllo (Luhn), conversione ISIN → ticker Yahoo, scelta della quotazione, cache
      `cache_prezzi/isin_ticker.json`; opzioni `isin`, `isin_scelte`, `nomi_attesi`, `controllo_dati` in `configurazione.py`.
- [x] 2. `controllo.py`: tabella «Controllo dati» con semaforo; `confronta.py` (blocco con rosso, `--solo-controllo`); report
      (Sintesi, CSV, Excel) con ISIN e ticker usato.
- [x] 3. App: colonna «Ticker o ISIN», pulsante «Controlla i dati», «Avvia simulazione» disattivato con un rosso, menu delle quotazioni.
- [x] 4. Test: `test_isin.py`, `test_controllo.py`, `test_isin_report.py`, `test_app_controllo.py` (tutti offline); non regressione verde.
- [x] 5. Prova reale (4/11/2026): `IE00B4L5Y983` → `SWDA.MI`, `US0378331005` → `AAPL`, `IT0003128367` → `ENEL.MI`;
      `confronta.py --config configurazioni/esempio_isin.yaml --solo-controllo`: 13 titoli, 3 avvisi (movimenti estremi storici), 0 errori.

Scelte fatte (annotate, senza chiedere):
- **Fonti ISIN provate davvero**: OpenFIGI senza chiave funziona (tutte le quotazioni, ma con codici borsa Bloomberg da tradurre in
  suffissi Yahoo: tabella `SUFFISSI_YAHOO`); `yfinance.Search` funziona (una sola quotazione, ticker già Yahoo); la ricerca Yahoo
  chiamata direttamente con lo user-agent del programma dà 429 (non aggirato: il progetto usa uno user-agent onesto). Quindi OpenFIGI
  principale (+ verifica di ogni candidato su Yahoo con yfinance, ripiego API diretta), `yfinance.Search` come riserva.
- **Regola di scelta** letta come ordine lessicografico: EUR, poi `.MI`, `.DE`, `.AS`, poi le altre; a parità anni di storia (interi) e
  volumi. Aggiunte due protezioni non richieste ma necessarie: quotazioni senza scambi da 30 giorni e quelle con volume sotto il 2% della più
  scambiata vanno in fondo (senza questa regola Apple sarebbe finita su `1AAPL.MI`, 5.000 azioni al giorno, invece di `AAPL`).
- **Giorni mancanti**: rispetto al calendario comune del progetto (giorni in cui almeno metà dei titoli ha scambiato), non ai giorni
  feriali: così le festività di una borsa non fanno scattare il giallo. Con un solo titolo il calendario è il suo e il valore è 0.
- «Prima e ultima data» e «data dell'ultimo prezzo» coincidono: la tabella ha «Ultima data» e «Ultimo prezzo» (valore + valuta + data).
- Prezzi zero o negativi: `fonti._pulisci` li scartava in silenzio; ora li conta (`prezzi_non_positivi` nei metadati, anche nella cache).
- Il blocco sta in `confronta.py` e nell'app, **non** in `analisi.esegui` (resta usabile da codice e dai test con dati finti di date vecchie);
  `esegui` converte comunque gli ISIN rimasti e accetta `controllo=` (salvato nel report) e `archivio=` (niente doppio download).
- Cache dei prezzi più vecchia di 7 giorni: il controllo riscarica quel ticker una volta prima di dichiarare il rosso/giallo.
- Nome atteso: solo da `nomi_attesi` (non dalla `descrizione` del benchmark, che ha un default); se manca il nome → giallo.
- Rimosso il vecchio riquadro «Controllo dei ticker» dall'app (sostituito dal nuovo flusso); `dati.verifica_ticker` resta (test).
- Non provato: browser reale per l'app con ISIN (provata con `streamlit.testing`), Mac reale.

## Versione 1.2: verifiche, merge e release (4 novembre 2026)
- [x] Prova in **browser vero** (Playwright + Chromium headless, Streamlit su localhost): caricata una configurazione con
      `IE00B4L5Y983`, `US0378331005`, `IT0003128367` → «Controlla i dati» → «4 titoli trovati, 1 avviso, 0 errori»
      (Apple gialla per movimenti storici estremi) → «Avvia simulazione» attivo → quotazione di `IE00B4L5Y983` cambiata dal menu
      (`SWDA.MI` → `EUNL.DE`; la tabella e il report scaricato usano `EUNL.DE`) → simulazione da 500 scenari → download del report HTML
      → configurazione con `IE00B4L5Y984` (cifra errata): «1 errore», «Avvia simulazione» **disattivato**, messaggio sulla cifra di controllo.
      Screenshot in `docs/screenshot/` (usati nel README).
      Nota: la mia asserzione automatica «EUNL.DE compare nel testo della pagina» dava FAIL perché la tabella è un canvas, non testo;
      la verifica vera è lo screenshot + il report scaricato (contiene `EUNL.DE`, non `SWDA.MI`).
- [x] Workflow: `prova-mac.yml` ora parte anche sulle pull request verso `main` e aggiunge
      `confronta.py --solo-controllo --config configurazioni/esempio_isin.yaml` (+ controllo della sezione e del CSV «Controllo dati» nel report);
      nuovo `test.yml` (Linux: ruff + pytest, push e pull request verso `main`); `zip-release.yml` controlla che `Installa.command` e
      `Avvia.command` siano eseguibili (`-rwx`), che non ci siano `.venv`, `.python`, `cache_prezzi`, `report` e che ci siano `isin.py`,
      `controllo.py`, `esempio_isin.yaml` (verificato in locale con `git archive`; `.github` e `.gitattributes` restano esclusi).
- [x] **Pull request [#2](https://github.com/edoardo-fenini/Montecarlo_simulation/pull/2)** verso `main`: `Test` verde (Linux) e `Prova su Mac`
      (macOS 14, Apple Silicon) verde sia sul push sia sulla pull request; nessun conflitto con `main` (il ramo era un avanzamento lineare di `main`).
- [ ] **Release v1.2.0: da creare dal sito** (la GitHub CLI qui non è autenticata e gli strumenti GitHub non creano release): Releases → Draft a new
      release → tag `v1.2.0` (Create new tag on publish) → Target `main` → incolla `RELEASE_NOTES.md` → Publish. Poi controllare in Actions
      che «Zip per la release» allegi lo zip (il workflow fallisce se i `.command` non sono eseguibili o se ci sono file non voluti).
- [ ] Ramo predefinito: impostare `main` dal sito (Settings → General → Default branch) se non è già così.
- Non provato: la chiave OpenFIGI (indicato nei limiti noti delle note di rilascio).

## Versione 1.3 (ramo `v1.3`): consolidamento (4 novembre 2026)
Scelte annotate: il ramo è `v1.3` come chiesto (il ramo di sessione `claude/sharp-lovelace-fc6742` non è usato). Il «report progresso,
debolezze e sviluppi» non era nel repository: lo creo in `docs/PROGRESSO_DEBOLEZZE_SVILUPPI.md`.
- [x] 0. **Correzione prioritaria (richiesta a metà lavoro): StreamlitDuplicateElementId a fine analisi.** Riprodotto sulla 1.2 (commit 4da7e8b)
      con AppTest e dati finti brevi (1.300 giorni), esempio precaricato ed esempio ISIN, tutti i moduli: l'analisi B coincide con la A e
      `fan_chart(A) == fan_chart(B)` → stesso ID automatico. Sulla 1.3: nessuna eccezione con entrambi gli esempi. Key univoche e stabili a tutti
      gli elementi con ID (inventario in CHANGELOG); test AST che lo impone. La prova Playwright che completa un'analisi e apre tutte le schede è
      nel commit della tappa 4 (serve l'infrastruttura e2e); verificato che FALLISCE sulla 1.2 e passa sulla 1.3.
      Non verificato: il messaggio esatto sul Mac dell'utente (non disponibile); la causa trovata è l'unica che produce questo errore nell'app.
- [x] 1. Risultati vecchi: `controllo.motivo_risultati_vecchi` + avviso e nascondimento in `app.py` (impronta di tutte le impostazioni
      + data della cache dei prezzi, registrate a fine simulazione; controllo rosso sui titoli attuali). 4 nuovi test. 116 test verdi.
- [x] 2. Controllo incrociato dei nomi: `nomi.py` (confronto tollerante, accenti e punti tolti, somiglianza dei caratteri solo per nomi lunghi),
      `isin.nome_discordante`, quotazioni discordanti in fondo all'ordine (si prova la successiva), `avvisi_nome` → GIALLO; borse OpenFIGI non
      mappate → `borse_non_mappate` (cache) → «info» nel Dettagli. Scelta: l'ordine mette i nomi discordanti PRIMA di ogni altra regola; se manca
      uno dei due nomi (o resta solo «ETF», «Inc»…) non si confronta. Nei test vecchi il nome OpenFIGI finto «X» è diventato realistico.
- [x] 3. Release automatica: `.github/workflows/release.yml` (tag `vX.Y.Z` o avvio manuale con la versione; test → zip → release con note da
      CHANGELOG → zip), `strumenti/note_release.py` + `tests/test_release.py`. Tag vecchi (`V_1.0.1`, `V_1.1.0`, `V_1.2.0`, `prova`) intatti. Scelta:
      il sito di GitHub non crea un tag da solo, quindi il metodo A è «Actions → Release → Run workflow» (crea tag e release); il push del tag dal
      terminale e il pulsante delle release funzionano uguale. `zip-release.yml` tenuto per le release create a mano.
- [x] 4. Prova nel browser: `tests/e2e/` (conftest avvia Streamlit su porta libera in una cartella temporanea con `app_finta.py`; Chromium di
      Playwright, ripiego su /opt/pw-browsers in questa sessione), 5 prove (2 percorsi + analisi completa ×2 esempi + apertura). Falso FAIL
      del canvas: verificato il testo associato «Ticker usati: …» aggiunto all'app. Menu delle quotazioni: si scrive nella ricerca e si preme
      Invio (il clic sulle opzioni BaseWeb non è affidabile). Workflow `test.yml`: installa Playwright + Chromium. Tempo locale: ~5 min.
- [x] 5. Importazione da CSV del broker: `importa_broker.py` (lettura, colonne IT/EN, numeri, pesi), `importa_portafoglio.py` (CLI con
      anteprima e conferma), riquadro nell'app con anteprima → conferma. Scelte: una sola virgola = decimale; il controvalore del file è
      considerato in EUR; colonne «di carico/costo/medio…» escluse; il portafoglio importato sostituisce uno con lo stesso nome; il prezzo
      del file non è usato (valuta ignota): per le righe senza controvalore si usa l'ultimo prezzo Yahoo in EUR. 26 test + prova nel browser.
- [x] 6. Ricerca per nome: `ricerca.py` (yfinance.Search, filtro tipi, max 10, valuta letta dai dati del ticker in parallelo perché la
      ricerca non la dà), riquadro nell'app con ➕ per riga e portafoglio di destinazione. Provata dal vivo (4/11/2026): «MSCI World» →
      IWDA.AS, EUNL.DE, URTH…; «IE00B4L5Y983» → IWDA.L con ISIN. Scelta: ISIN mostrato solo se cercato (Yahoo non lo restituisce); un titolo
      già presente nel portafoglio non viene duplicato; il peso del nuovo titolo resta vuoto. 7 test + prova nel browser.
- [x] Correzione emersa in CI sulla pull request 3: in un'esecuzione di «Test» la prova della ricerca ha trovato le impostazioni azzerate
      (capitale 0, orizzonte 1). Causa: Streamlit, quando un'esecuzione termina con un'eccezione, cancella lo stato dei widget non disegnati
      (`script_runner.py`, `remove_stale_widgets`). Non riprodotto in locale (5/5 verdi). Correzione difensiva: `stato_app.conserva` (copia di
      sicurezza delle impostazioni ripristinata a ogni esecuzione) + test; la prova nel browser ora riporta nel riepilogo gli errori del log di Streamlit.
- [x] 7. Chiusura: RELEASE_NOTES v1.3.0, README (novità, aggiornamento), user-agent 1.3, report `docs/PROGRESSO_DEBOLEZZE_SVILUPPI.md`.
      199 test verdi in locale, non regressione identica.
- [x] **Pull request [#3](https://github.com/edoardo-fenini/Montecarlo_simulation/pull/3)** verso `main`: Test (Linux, con la prova nel browser)
      e Prova su Mac (macOS 14) verdi sul push e sulla pull request → unita (merge f9e09b4).
- [x] **Release v1.3.0 creata dalla release automatica** (4/11/2026): il push del tag da questa sessione è bloccato dal proxy (non dal
      repository), quindi ho usato il Metodo A del README (Actions → Release → Run workflow, versione 1.3.0, ramo main) tramite l'API:
      test verdi → tag `v1.3.0` su f9e09b4 creato dal GITHUB_TOKEN → release con le note della sezione 1.3.0 del CHANGELOG →
      `confronta-portafogli-v1.3.0.zip` (7,4 MB) allegato. Il percorso «push del tag» non è stato provato da qui (stesso workflow).

## Versione 1.3.1 (ramo `v1.3.1`): correzioni dopo la prova su un Mac reale (4 novembre 2026)
Segnalazione dell'utente: dallo zip della v1.3.0 su Mac Apple Silicon, prova rapida di Installa.command «1 failed, 191 passed, 1 skipped»
in 153 s (`test_release.py` leggeva `.github/workflows/release.yml`, escluso dallo zip) + `ConvergenceWarning` (SLSQP codice 4) da simula.py:79.
- [x] GARCH (commit separato): causa = SLSQP sul bordo (alpha≈0) per serie senza raggruppamenti di volatilità (i dati sintetici dei test)
      o quasi costanti; codice 4 «Inequality constraints incompatible»; parametri = ultimo tentativo, usati in silenzio. Riprodotto qui
      solo con una serie quasi costante (sui dati finti Linux converge: il caso del Mac dipende dall'aritmetica arm64). Ora: stima standard
      (identica), poi 3 punti di partenza, poi volatilità costante + avviso (log, Sintesi, Robustezza). 5 test, uno con ottimizzatore finto «codice 4».
- [x] Test dei file del solo repository: `tests/solo_repository.richiede` → skip con messaggio. Verificato eseguendo TUTTA la suite dentro
      lo zip costruito come la release: era l'unico test interessato.
- [x] Marker `rapido` (tutti i test tranne l'elenco LENTI in `tests/conftest.py` e tests/e2e); Installa.command usa `-m rapido`.
      31 s su questa macchina (Linux 4 core, Python 3.13); prova reale dello zip con Installa.command qui: 179 passed, 3 skipped, 38 s.
- [x] Job `zip-release` in «Prova su Mac» (zip costruito con `strumenti/crea_zip.sh` come la release, oppure scaricato con l'input `release`;
      cartella pulita; Installa.command non interattivo; limite di 75 s sulla prova rapida; Avvia.command).

## Chiusura del progetto (seconda richiesta)
- [x] 1. Verifica della convergenza: `strumenti/verifica_convergenza.py` -> `esempi/verifica_convergenza/risultati.md`;
      modulo «Le simulazioni bastano?» (attivo, 3 seed); test sul numero di percorsi.
- [x] 4. TER sottratto anche agli ETF usati come titoli (`ter:` per ticker, `ter_etf_default` 0,20%).
- [x] 2. Prova su Mac reale con GitHub Actions (`.github/workflows/prova-mac.yml`, macos-14 Apple Silicon):
      prima esecuzione **riuscita** (run 41713088802, circa 1 minuto e 15 secondi): Installa.command --non-interattivo
      (Python 3.12.16 arm64 in .python), 17 test ok, confronta.py --veloce con dati Yahoo reali, app headless risponde
      e si ferma. Nota sulla quarantena (xattr) nel README.
- [x] 3. Ramo `main` creato con tutto il lavoro (fast-forward da claude/new-session-extdst). Il ramo predefinito va
      impostato dal sito: Settings → General → Default branch → ⇄ → main → Update (Claude non ha lo strumento per farlo).
- [ ] 5. Release v1.0.0: **da creare dal sito** (la GitHub CLI qui è solo per ricerche e gli strumenti GitHub non creano release).
      Note in `RELEASE_NOTES.md`. Passaggi: Releases → Draft a new release → tag v1.0.0 (Create new tag on publish) → Target main
      → incolla RELEASE_NOTES.md → Publish release. Poi controllare in Actions che «Zip per la release» alleghi lo zip (non verificabile da qui).
- [x] 6. Riepilogo PDF aggiornato (convergenza, prova su Mac, ramo main, TER, release) inviato in chat.
- Prove su Mac successive: run 2 (ramo di lavoro) e 3 (main) riuscite anche con actions/checkout@v5 e upload-artifact@v5.

### Risultati della convergenza (metodo beta, analisi A, 15 anni)
- Array: storia 1.342 giorni x 20 colonne; per ogni blocco di calcolo indici 1.000 percorsi x 3.780 giorni,
  rendimenti di un mese 1.000 x 21 x 20. Percorsi effettivi = richiesti (1.000, 5.000, 10.000, 20.000).
- 10.000 simulazioni, 5 seed: mediana fino a ±3,2% (Big tech USA), 5° percentile fino a ±3,6% -> sopra la soglia ±2%.
- 20.000 simulazioni, 5 seed: mediana entro ±1,7% per tutti, 5° percentile entro ±2,0%.
- **Proposta: 20.000 simulazioni.** Tempo dell'esecuzione completa di default (A+B, stress, rischio singolo titolo,
  verifica con 3 seed) su questa macchina a 4 core: 10.000 = circa 2,5 minuti; 20.000 = circa 5 minuti.
  **Decisione dell'utente: default portato a 20.000** (config, esempio, app, README, note di rilascio).

## Scelte fatte (default ragionevoli)
- Rendimento atteso = media aritmetica annua (1 € vale in media 1+r dopo un anno), come nell'analisi iniziale.
- Metodo `beta`: beta stimato su rendimenti **settimanali** in EUR rispetto al benchmark (le borse chiudono a orari diversi:
  con i giornalieri il beta dei titoli USA verso un ETF quotato ad Amsterdam risulterebbe troppo basso). Solo dati reali.
- Con la ricentratura si sottrae il TER del benchmark e degli ETF usati come titoli (valore in `ter:` o `ter_etf_default`, 0,20%). Con il metodo storico no: i prezzi storici sono già al netto.
- Calendario: giorni in cui almeno metà dei titoli quotati ha scambiato (gestisce borse diverse e festività).
- Valute: cambio giornaliero Yahoo `EURxxx=X`; per il dollaro prima del 2003 cambio FRED. Pence (GBp) divisi per 100.
- Settore (stress test e proxy analisi C): indicato in configurazione → settore Yahoo (se disponibile) → ETF di settore USA più correlato.
- Analisi B solo se il periodo comune (A) parte almeno un anno dopo `inizio_B`; altrimenti A copre già il periodo lungo.
- Il modulo "confronto tra modelli" include anche la sensibilità al rendimento atteso (variante più bassa e più alta).
- Stress test: lo shock di un portafoglio è la media pesata degli shock per categoria (tech/finanza/altro); dopo lo shock i versamenti continuano.

## Verifiche fatte
- 16 test pytest (offline, con un finto Yahoo): configurazione, errori, metodi di rendimento, portafogli misti, end-to-end, report, app.
- App provata in headless con browser automatico: simulazione completa, schede, download, errore chiaro per ticker sbagliato.
- `Installa.command` provato su Linux in una copia pulita senza uv (scarica uv e Python 3.12 nella cartella); `Avvia.command` avvia e si ferma alla chiusura. Non provato su un Mac vero.
- Prova con dati reali europei (EUR, CHF, GBp), ETF, versamenti e portafoglio misto.

## Come riprendere
`python -m pytest -q tests` (offline; 112 test). Esempio di configurazione: `configurazioni/esempio_tre_portafogli.yaml`.
L'analisi iniziale (rendimento uguale 6%) è in `esempi/2026-11-03_analisi_iniziale_rendimento_uguale_6/`.
- PDF generato con reportlab (solo Python, niente Chrome) e font DejaVu incluso in matplotlib.
- Stress test: una sola simulazione di "crescita di 1 €" per portafoglio riusata per tutti gli scenari (veloce); 1.000 percorsi.
- App: tema chiaro fisso (`.streamlit/config.toml`); le schede mostrano gli stessi blocchi del report HTML; default 20.000 simulazioni.
- Avvia.command avvia Streamlit in modalità headless e apre il browser con `open`: così Streamlit non chiede l'email al primo avvio.
- requirements.txt: versioni fissate delle librerie dirette, verificate su PyPI con pacchetti per Mac arm64 e x86_64 (Python 3.12/3.13).

## Versione 1.4 (ramo `v1.4`): fondi comuni e costi (4 novembre 2026)
Baseline all'inizio: tutti i test verdi (senza browser), non regressione identica.
- [x] Tappa 0 – correzioni in sospeso. **Già presenti** (1.3.1): ConvergenceWarning GARCH/SLSQP risolto e mai usato in silenzio;
      prova rapida di `Installa.command` con marker `rapido` (~30 s) e test del solo repository saltati con messaggio.
      **Applicate ora**: riquadro «Rendimento atteso che verrà usato» (app e riga di comando: beta e rendimento per portafoglio);
      campo vuoto o non numerico = ROSSO, mai 0 (`rendimento.numero_pct`); GIALLO con premio di mercato 0 o rendimento sotto l'1%;
      controllo di plausibilità (`rendimento.controlla_plausibilita`: rendimento medio dei percorsi simulati contro l'atteso al netto
      dei costi, tolleranza = 5 errori standard + 0,3%); se fallisce: errore ROSSO, l'app non mostra i risultati e `confronta.py` non scrive il report.
      **NON applicata, su richiesta dell'utente («la parte dei default lasciala stare»)**: il cambio dei default a 2,5% / 4%
      (restano 2% / 4% in `configurazione.py`, app, YAML di esempio e README). Il test di non regressione resta quindi identico.
- [x] Tappa 1 – tipo di strumento: `isin.classifica_tipo` (OpenFIGI `securityType`/`securityType2`: ETP → ETF/ETC; Open-End Fund → fondo comune;
      Common Stock/ADR → azione), salvato nella cache degli ISIN; nuova colonna «Tipo» nel controllo dati (app, report, CSV, Excel).
      **Verificato dal vivo (4/11/2026)**: i quattro ISIN sono tutti «Open-End Fund» (borsa OpenFIGI «LX») = fondi comuni lussemburghesi non quotati.
      Prima la ricerca li convertiva in codici tedeschi (es. `MSJ6.F`) che su Yahoo hanno solo 1d/5d di dati: da qui «storia 0 anni».
- [x] Tappa 2 – ricerca automatica (`fondi.py`): ricerche Yahoo per ISIN e per nome (con sigle dei gestori note: MS INVF, JPM, BGF…), codici
      `0P…` o tipo MUTUALFUND; verifiche: stesso gestore, nome simile a OpenFIGI/Yahoo (≥0,5), valuta, accumulazione/distribuzione, lettera della
      classe, parole in più (es. «Plus»), copertura del cambio, storia ≥1 anno, ultimo prezzo ≤30 giorni; poi le regole di `ordina_quotazioni`.
      Sempre un avviso GIALLO: Yahoo non indica l'ISIN, quindi la classe non è certa. Cache come gli altri ISIN (anche l'esito negativo).
      **Prova reale (4/11/2026)**, storia ≈ 4,7 anni per tutti (Yahoo ha i dati Morningstar solo dal 07/03/2022):
      | ISIN | esito | codice | nome | valuta | storia |
      |---|---|---|---|---|---|
      | LU0073232471 | trovato (classe NON certa: A in EUR scelta, l'ISIN è probabilmente la classe in USD) | `0P0001LLAM.F` | MS INVF US Growth A EUR | EUR | 4,7 |
      | LU0552385295 | trovato | `0P0000RZ2H` | MS INVF Global Opportunity A | USD | 4,7 |
      | LU0070214290 | trovato | `0P00000DTX` | JPM US Select Equity A acc USD | USD | 4,7 |
      | LU0210536198 | trovato | `0P00000C2V` | JPM US Growth A dist USD | USD | 4,7 |
      Limite: la ricerca di Yahoo per nome è capricciosa; per fondi di altri gestori può non trovare nulla → tappa 3 (CSV o proxy).
      Una storia di 4,7 anni è corta per simulare 15 anni, ma sopra la soglia gialla esistente (3 anni): nessun avviso di storia corta, la serie va solo valutata con attenzione.
- [x] Tappa 3 – alternative per i fondi non trovati. 3a: `nav.py` + `fonti.leggi_csv_prezzi` più tollerante (separatori `;` `,` tab, decimali con la
      virgola, date GG/MM/AAAA e AAAA-MM-GG, intestazioni IT/EN, righe in qualsiasi ordine); anteprima e conferma nell'app; valuta chiesta (default dal
      nome del fondo, poi EUR); storico salvato in cache con l'**ISIN come chiave**, fonte «CSV importato», riusato in automatico (ha la precedenza sulla
      ricerca online); da YAML: `prezzi_da_file: {ISIN: {file, valuta}}`; avviso GIALLO per classi a distribuzione (`nav.avviso_distribuzione`: calo
      brusco >2,5 volte la variabilità normale negli stessi giorni dell'anno in ≥60% degli anni, almeno 3). CSV di esempio `esempi/storico_quote_esempio.csv`
      (numeri INVENTATI; si rigenera con `strumenti/crea_csv_esempio.py` perché il controllo dati rifiuta uno storico con l'ultimo valore oltre 30 giorni fa).
      3b: `proxy_titoli: {titolo: sostituto}` (YAML e app), sempre segnalato (controllo dati giallo, avviso nel report, riga «proxy» nella tabella dei costi);
      il tipo mostrato è quello del titolo vero. 3c: messaggio ROSSO «È un fondo comune non quotato…» con i pulsanti «Carica lo storico delle quote» e
      «Scegli un proxy» (anche per altri titoli non trovati). Scelta: CSV e proxy dichiarati vincono sulla ricerca automatica; il CSV vince sul proxy.
- [x] Tappa 4 – costi: colonna «Costi annui (%)» nella tabella dell'app e chiave YAML `costi` (per ticker o ISIN); `analisi.costo_titolo`: indicato →
      default per tipo (fondo comune 1,5% `costo_fondo_default`, ETF/ETC 0,3% `ter_etf_default`) con avviso GIALLO «costi non indicati, uso il default»;
      azioni 0. Sottratti dal rendimento atteso solo con la ricentratura (con il metodo storico i prezzi sono già al netto, come per gli ETF prima).
      Report: tabelle «Costi annui usati» e «effetto dei costi» per portafoglio. Benchmark: usa il suo TER una sola volta (colonna BENCH separata,
      nessun doppio conteggio; il TER dentro il proxy storico non pesa perché la media storica viene sostituita). **Modifica voluta**: il default per gli ETF
      senza costo passa da 0,20% a 0,30% (richiesto); i fondi comuni (tipo MUTUALFUND) non sono più trattati come «azioni» nel rischio sul singolo titolo e
      negli stress test. Test di non regressione invariato (i dati finti non hanno ETF o fondi nei portafogli).
- [x] Tappa 5 – test: `tests/test_fondi_v14.py` (30 test offline: tipo di strumento da risposte OpenFIGI simulate, codici `0P…` e scelta del
      candidato, risoluzione/cache dei fondi trovati e non trovati, CSV con separatori/decimali/date/intestazioni italiane, anteprima, salvataggio
      in cache e riuso senza rete, avviso classe a distribuzione, proxy nel controllo e nel report, costi: default con avviso, sottrazione, nessun
      doppio conteggio sul benchmark) e `tests/test_rendimento.py` (campo vuoto ≠ 0, avvisi, plausibilità; i default 2,5%/4% NON sono stati
      cambiati su richiesta). Prova nel browser: fondo non trovato → errore rosso con i due pulsanti → CSV (generato con date aggiornate) →
      0 avvisi, 0 errori → simulazione completa senza errori Streamlit → report con «CSV importato» e «Costi annui usati».
      Quattro test esistenti sono stati adattati perché un ETF senza costi indicati ora è giallo (voluto): aggiunto `costi` alla loro configurazione.
      Emerso dalla prova nel browser e corretto: dopo un rosso risolto «Avvia simulazione» restava disattivato fino al clic successivo.
      Nella prova nel browser FRED è finto (senza rete vera): altrimenti il controllo dati, che ora calcola anche il beta, aspettava il timeout di FRED.
      Risultato: 248 test verdi in locale (8 min 34 s, prova nel browser inclusa); `ruff check` pulito; non regressione identica.

## Versione 1.5 (ramo `v1.5`): modello di rischio a fattori (4 novembre 2026, lavoro notturno autonomo)
Ora: tappe 1-2 quasi chiuse (modello, report, app). Prossimo passo: test app con modello fattori, tappa 3 (backtest VaR, modulo `backtest_var.py`), poi confronto modelli, README/CHANGELOG, PR e tag.
- [x] Tappa 0 – impostazioni azzerate. Verificato con AppTest: cambio metodo (beta→uguale→personalizzato→beta), pesi uguali, scelte rapide:
      con la copia di sicurezza della 1.3 (`stato_app.conserva`) i valori non si azzerano mai. Causa più probabile: Streamlit cancella lo stato dei
      campi non disegnati (rf/mrp esistono solo con metodo «beta») e un number_input senza valore riparte da 0/minimo (capitale 0, orizzonte 1,
      premio 0). Non riprodotto in locale (come già annotato nella 1.3). Rafforzato: `conserva` accetta valori predefiniti (mai 0 se la chiave
      manca anche nella copia); pulsanti Prudente (2/3), Base (2,5/4), Ottimista (2,5/5) con callback + didascalia; default 2%/4% invariati;
      campi sempre liberi (anche 0). Test: `tests/test_impostazioni_non_azzerate.py`.
- [x] Tappa 1 – `fattori.py` + `modelli/fattori.yaml` (18 fattori in EUR: mercato MSCI World; regioni USA/Europa/Giappone/Emergenti come scarti dal mondo;
      7 settori USA come scarti da SPY; growth-value, piccole, momentum, qualità; obbligazioni lunghe TLT e dollaro/euro). Inizio storia 2000-01-03; momentum e qualità
      solo dal 2013, emergenti 2003, obbligazioni 2002: prima valgono 0 e non entrano nelle regressioni. Ridge su rendimenti settimanali, penalità per GCV con minimo
      0,5×settimane (scelto con prova fuori campione su titoli reali), mercato NON penalizzato. Simulazione: fattori con block bootstrap + residui iid per titolo
      (stesso residuo per lo stesso titolo in portafogli diversi), media ricentrata come per il metodo storico. Con `modello_simulazione: fattori` si fa solo l'analisi A.
      Scelta: il file dei fattori sta in `modelli/` perché un test valida ogni YAML di `configurazioni/` come portafoglio.
      Limite noto: il benchmark ETF ha correlazione giornaliera 0,6 con l'indice MSCI (fusi orari/qualità del dato Yahoo): i suoi scarti regionali sono rumore.
- [x] Tappa 2 – `report_fattori.py`: scheda «Da dove viene il rischio» (barre impilate, esposizioni, R², avvisi R²<0,3, sintesi in italiano), anche con modello storico
      (modulo `scomposizione_rischio`). App: selettore del modello + due moduli nuovi.
- [x] Tappa 3 – `backtest_var.py`: VaR 1 giorno 95/99% su finestra mobile 504 giorni, modelli storico (quantile) e fattori (beta ricalcolati ogni 21 giorni, covarianza
      dei fattori su tutta la storia fino a ieri + varianza specifica, VaR normale); Kupiec, Christoffersen, semaforo; scheda «Validazione del modello» (tabelle + grafico);
      modulo `backtest_var` disattivato di default. Test: `tests/test_backtest_var.py`. Primo esito reale (Cyber/Big tech/MSCI World, 5,4 anni): vedi il riepilogo finale.
  Ora: prova nel browser con modello fattori, confronto dei due modelli sull'esempio, README/CHANGELOG/RELEASE_NOTES, PR, tag.
