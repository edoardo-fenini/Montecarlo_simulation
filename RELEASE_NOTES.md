# v1.0.0 – Confronto del rischio di portafogli

Prima versione dello strumento per confrontare il **rischio** di più portafogli di azioni ed ETF con una simulazione Monte Carlo, pensato per chi non sa programmare e usa un Mac.

> Non è consulenza finanziaria: è un aiuto per capire i rischi, non un consiglio di acquisto.

## Cosa fa
- Confronta quanti portafogli vuoi (azioni ed ETF, anche europei: `.MI`, `.DE`, `.AS`, `.PA`, `.L`, `.SW`) con un benchmark (di default l'iShares Core MSCI World, `IWDA.AS`). Tutto è convertito in euro con il cambio giornaliero.
- Simula migliaia di futuri possibili rimescolando blocchi di storia reale (bootstrap a blocchi), con ribilanciamento, costi e versamenti mensili.
- Per ogni orizzonte (es. 5, 10, 15 anni) mostra il valore mediano, il 5° e il 95° percentile, la probabilità di finire sotto il versato, il calo massimo (drawdown) e il tempo per recuperarlo.
- Quattro metodi per il rendimento atteso: **beta** (default: 2% + beta × 4%), **uguale**, **storico** (con avviso) e **personalizzato**.
- **Portafogli misti**, ad esempio 80% MSCI World + 20% Cyber security.
- Moduli: stress test (crolli stile 2000 e 2008, singolo titolo −90%), rischio di crollo di un singolo titolo, verifica «Le simulazioni bastano?» e, facoltativi, confronto tra modelli (Student-t, GARCH) e storia dal 1999 con proxy di settore.
- Report in **HTML**, **PDF** e tabelle **CSV** per Excel, con una sintesi automatica in italiano semplice.
- **App** nel browser (Streamlit) con tabella dei portafogli, barra di avanzamento, risultati a schede, download dei report e salvataggio/caricamento della configurazione. È precaricato un esempio con tre portafogli.
- In alternativa, **riga di comando**: `python confronta.py --config configurazioni/mio_file.yaml`.

## Come installarlo sul Mac (Apple Silicon o Intel)
1. Scarica `confronta-portafogli-v1.0.0.zip` qui sotto, aprilo e sposta la cartella in **Documenti**.
2. Fai doppio clic su **`Installa.command`**. La prima volta macOS lo blocca: vai in Impostazioni di Sistema → Privacy e sicurezza → **Apri comunque**. Python e le librerie vengono installati dentro la cartella. Serve internet e ci vogliono alcuni minuti.
3. Fai doppio clic su **`Avvia.command`**: si apre il browser con l'app. Per chiuderla, chiudi la finestra del Terminale.
4. Se il doppio clic viene bloccato anche dopo "Apri comunque": `xattr -dr com.apple.quarantine ~/Documents/confronta-portafogli`.

Tutti i dettagli sono nel `README.md`.

## Limiti noti
- **Il rendimento atteso è un'ipotesi**, non una previsione: cambiandolo cambiano i valori finali. Le differenze di rischio tra portafogli sono più solide del livello dei numeri.
- **Il futuro può essere diverso dal passato.** Il modello rimescola eventi già avvenuti, e i titoli quotati da poco hanno poca storia.
- **Dati da Yahoo Finance**: possono contenere errori, e il servizio a volte limita gli accessi (in quel caso basta riprovare dopo qualche minuto). Il settore dei titoli non è sempre disponibile: allora si usa l'ETF di settore più correlato, che si può correggere nella configurazione.
- **Costi**: sono inclusi TER degli ETF e costo di ribilanciamento, ma non imposte, spread e commissioni.
- **Numero di simulazioni**: con le 10.000 di default la mediana può variare di circa ±3% tra un'esecuzione e l'altra. Per numeri più stabili usa 20.000 simulazioni, che richiedono circa il doppio del tempo.
- I file `.command` non sono firmati da Apple, per questo serve "Apri comunque" la prima volta.
