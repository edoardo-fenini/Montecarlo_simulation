# v1.3.0 – Consolidamento

Quarta versione dello strumento per confrontare il **rischio** di portafogli di azioni ed ETF con una simulazione Monte Carlo.
Tutte le funzioni della 1.2 restano; **i risultati del calcolo sono identici** (verificato dal test di non regressione, 1.236 numeri).
Le note complete della release automatica vengono dalla sezione 1.3.0 di `CHANGELOG.md`.

> Non è consulenza finanziaria: è un aiuto per capire i rischi, non un consiglio di acquisto.

## Novità
- **Correzione importante**: l'app poteva fermarsi a fine analisi con l'errore `StreamlitDuplicateElementId` (quando le analisi A e B
  hanno grafici identici). Corretto dando una chiave univoca a ogni elemento dell'app.
- **Risultati vecchi nascosti**: se cambi titoli, pesi, impostazioni o dati, o se il controllo dei dati diventa rosso, al posto dei
  risultati compare «Questi risultati non corrispondono più ai dati attuali: rilancia la simulazione».
- **Controllo incrociato dei nomi** per gli ISIN (OpenFIGI contro Yahoo): se non tornano, avviso giallo e si prova la quotazione successiva.
  Le borse non riconosciute sono elencate come informazione.
- **Importazione dal broker**: carichi il CSV del conto titoli (ISIN e quantità o controvalore), vedi l'anteprima e confermi. Anche da
  riga di comando: `python importa_portafoglio.py file.csv`.
- **Ricerca per nome**: scrivi «Enel» o «MSCI World» e aggiungi il titolo con un clic.
- **Release automatica** dal tag `vX.Y.Z` e prova nel browser eseguita a ogni push.

## Come installarla sul Mac (Apple Silicon o Intel)
1. Scarica `confronta-portafogli-v1.3.0.zip` qui sotto, aprilo e sposta la cartella in **Documenti**.
2. Doppio clic su **`Installa.command`** (la prima volta: Impostazioni di Sistema → Privacy e sicurezza → **Apri comunque**).
3. Doppio clic su **`Avvia.command`**: si apre il browser con l'app.

**Aggiornamento dalla 1.2**: copia nella nuova cartella `configurazioni/` (i tuoi file), `cache_prezzi/` e `report/`, poi rilancia
`Installa.command`. I tuoi file YAML funzionano senza modifiche.

## Limiti noti
- La ricerca per nome e la conversione degli ISIN dipendono da servizi gratuiti (Yahoo Finance, OpenFIGI) che possono limitare gli accessi.
- La ricerca di Yahoo non restituisce gli ISIN: la colonna ISIN dei risultati è piena solo se cerchi un ISIN.
- Nel CSV del broker il controvalore è considerato in euro.
- Il rendimento atteso è un'ipotesi, non una previsione. I file `.command` non sono firmati da Apple.
