# v1.2.0 – ISIN e controllo dei dati

Terza versione dello strumento per confrontare il **rischio** di portafogli di azioni ed ETF con una simulazione Monte Carlo.
Tutte le funzioni della 1.1 restano; **i risultati del calcolo sono identici** (verificato dal test di non regressione, 1.236 numeri).

> Non è consulenza finanziaria: è un aiuto per capire i rischi, non un consiglio di acquisto.

## Novità
- **Puoi usare gli ISIN al posto dei ticker.** In tabella, nel benchmark e nei file YAML scrivi un ticker Yahoo oppure un ISIN (es. `IE00B4L5Y983`): viene riconosciuto da solo, la cifra di controllo viene verificata e il codice è convertito in ticker (OpenFIGI, con la ricerca di Yahoo Finance come riserva). Se l'ISIN ha più quotazioni la scelta segue una regola configurabile (default: EUR, poi Borsa Italiana, Xetra, Amsterdam, poi le altre; a parità più storia e più volumi) e nell'app un menu permette di sceglierne un'altra. Il report mostra ISIN e ticker usato. Esempio: `configurazioni/esempio_isin.yaml`.
- **Controllo dei dati prima della simulazione.** Il pulsante «Controlla i dati» mostra per ogni titolo nome, borsa, valuta, fonte, storia, giorni mancanti e ultimo prezzo, con un semaforo: 🔴 errore (la simulazione non parte), 🟡 avviso, 🟢 tutto a posto. Con un errore «Avvia simulazione» è disattivato e un messaggio dice cosa correggere. Da riga di comando: `python confronta.py --config ... --solo-controllo`. La tabella è anche nel report, nel CSV e in Excel. Soglie modificabili in `controllo_dati`.

## Come installarla sul Mac (Apple Silicon o Intel)
1. Scarica `confronta-portafogli-v1.2.0.zip` qui sotto, aprilo e sposta la cartella in **Documenti**.
2. Doppio clic su **`Installa.command`** (la prima volta: Impostazioni di Sistema → Privacy e sicurezza → **Apri comunque**).
3. Doppio clic su **`Avvia.command`**: si apre il browser con l'app.
4. Se il doppio clic viene bloccato anche dopo "Apri comunque": `xattr -dr com.apple.quarantine ~/Documents/confronta-portafogli-v1.2.0` (nel Terminale).

**Aggiornamento dalla 1.1**: copia nella nuova cartella `configurazioni/` (i tuoi file), `cache_prezzi/` e `report/`, poi rilancia `Installa.command` (non servono librerie nuove, ma è il modo più sicuro). I tuoi file YAML continuano a funzionare senza modifiche. Dettagli nel README, punto 8.

## Limiti noti
- **La chiave OpenFIGI (facoltativa) non è stata provata**: il codice la supporta, ma tutte le prove sono state fatte senza chiave (funziona, con limiti più bassi). Come ottenerla: README.
- La ricerca ISIN dipende da servizi gratuiti (OpenFIGI, Yahoo Finance) che possono limitare gli accessi: le conversioni riuscite restano in cache.
- Il controllo dei dati segnala errori evidenti (storia corta, prezzi vecchi, buchi, movimenti estremi) ma non può garantire che i dati di Yahoo siano giusti: controlla sempre che il nome trovato sia quello che intendevi.
- Il rendimento atteso è un'ipotesi, non una previsione; il futuro può essere diverso dal passato.
- I file `.command` non sono firmati da Apple: la prima volta serve "Apri comunque".
