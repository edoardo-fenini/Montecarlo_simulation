# STATO del progetto – strumento riutilizzabile

## Tappe
- [x] 1. Motore generico e configurabile (`configurazione.py`, `dati.py`, `analisi.py`, `simula.py`, `metriche.py`) + test
- [x] 2. Script da riga di comando `confronta.py --config ...` -> report/AAAA-MM-GG_nome/ (HTML, PDF con reportlab, CSV con ; e virgola decimale per Excel)
- [x] 3. App Streamlit `app.py` (verificata in headless: simulazione completa, schede, download, errori chiari)
- [x] 4. `Installa.command` (uv + Python 3.12 dentro la cartella: .uv, .python, .venv) e `Avvia.command` (porta libera, solo 127.0.0.1, apre il browser) — provati su Linux in una copia pulita senza uv
- [x] 5. README passo passo, GitHub Action `.github/workflows/zip-release.yml` (zip allegato alla release), esempio `esempi/2026-11-03_tre_portafogli_metodo_beta/`
- [ ] Release v1.0.0: da creare dal sito di GitHub (Claude non ha lo strumento per creare release; istruzioni nel README)

## Chiusura del progetto (seconda richiesta)
- [x] 1. Verifica della convergenza: `strumenti/verifica_convergenza.py` -> `esempi/verifica_convergenza/risultati.md`;
      modulo «Le simulazioni bastano?» (attivo, 3 seed); test sul numero di percorsi.
- [x] 4. TER sottratto anche agli ETF usati come titoli (`ter:` per ticker, `ter_etf_default` 0,20%).
- [x] 2. Prova su Mac reale con GitHub Actions (`.github/workflows/prova-mac.yml`, macos-14 Apple Silicon):
      prima esecuzione **riuscita** (run 41713088802, circa 1 minuto e 15 secondi): Installa.command --non-interattivo
      (Python 3.12.16 arm64 in .python), 17 test ok, confronta.py --veloce con dati Yahoo reali, app headless risponde
      e si ferma. Nota sulla quarantena (xattr) nel README.
- [ ] 3. Ramo main
- [ ] 5. Release v1.0.0
- [ ] 6. Riepilogo finale

### Risultati della convergenza (metodo beta, analisi A, 15 anni)
- Array: storia 1.342 giorni x 20 colonne; per ogni blocco di calcolo indici 1.000 percorsi x 3.780 giorni,
  rendimenti di un mese 1.000 x 21 x 20. Percorsi effettivi = richiesti (1.000, 5.000, 10.000, 20.000).
- 10.000 simulazioni, 5 seed: mediana fino a ±3,2% (Big tech USA), 5° percentile fino a ±3,6% -> sopra la soglia ±2%.
- 20.000 simulazioni, 5 seed: mediana entro ±1,7% per tutti, 5° percentile entro ±2,0%.
- **Proposta: 20.000 simulazioni.** Tempo dell'esecuzione completa di default (A+B, stress, rischio singolo titolo,
  verifica con 3 seed) su questa macchina a 4 core: 10.000 = circa 2,5 minuti; 20.000 = circa 5 minuti.
  Il default resta 10.000 finché l'utente non decide.

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
`python -m pytest -q tests` (offline). Esempio di configurazione: `configurazioni/esempio_tre_portafogli.yaml`.
L'analisi iniziale (rendimento uguale 6%) è in `esempi/2026-11-03_analisi_iniziale_rendimento_uguale_6/`.
- PDF generato con reportlab (solo Python, niente Chrome) e font DejaVu incluso in matplotlib.
- Stress test: una sola simulazione di "crescita di 1 €" per portafoglio riusata per tutti gli scenari (veloce); 1.000 percorsi.
- App: tema chiaro fisso (`.streamlit/config.toml`); le schede mostrano gli stessi blocchi del report HTML; default 10.000 simulazioni.
- Avvia.command avvia Streamlit in modalità headless e apre il browser con `open`: così Streamlit non chiede l'email al primo avvio.
- requirements.txt: versioni fissate delle librerie dirette, verificate su PyPI con pacchetti per Mac arm64 e x86_64 (Python 3.12/3.13).
