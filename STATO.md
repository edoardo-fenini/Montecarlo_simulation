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
