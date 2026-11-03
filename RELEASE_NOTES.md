# v1.1.0 – Più robusta, più chiara, più bella

Seconda versione dello strumento per confrontare il **rischio** di portafogli di azioni ed ETF con una simulazione Monte Carlo.
Tutte le funzioni della 1.0 restano; i risultati del calcolo sono identici (verificato da un test di non regressione).

> Non è consulenza finanziaria: è un aiuto per capire i rischi, non un consiglio di acquisto.

## Novità
- **Dati più affidabili**: se Yahoo Finance non risponde lo strumento riprova e passa ad altre fonti gratuite (Yahoo diretto, Stooq, Banca Centrale Europea per i cambi); senza internet usa i prezzi già salvati; puoi caricare i prezzi da un file CSV; controllo dei ticker con nome della società, borsa, valuta e anni di storia; «Dati aggiornati al …» sempre in vista.
- **Report più leggibile**: copertina e indice cliccabile, pagina «In una pagina» con una scheda per portafoglio e un livello di rischio da 1 a 5, tabelle che entrano nella pagina, una spiegazione sotto ogni grafico, zona sotto il capitale investito evidenziata.
- **App più curata**: grafici interattivi (passa il mouse per leggere i valori), card riassuntive, pagina iniziale in 3 passi, aiuto «?» su ogni opzione, barra di avanzamento con il tempo stimato, tema chiaro o scuro.
- **Funzioni in più**: analisi salvate e confronto tra due analisi, prova rapida dei pesi tra benchmark e satellite, esportazione in Excel, nuove configurazioni di esempio (core + satellite 80/20, ETF europei).
- **Più veloce**: le simulazioni girano in parallelo; con le impostazioni di default (20.000 simulazioni) circa 1-2 minuti.

## Come installarla sul Mac (Apple Silicon o Intel)
1. Scarica `confronta-portafogli-v1.1.0.zip` qui sotto, aprilo e sposta la cartella in **Documenti**.
2. Doppio clic su **`Installa.command`** (la prima volta: Impostazioni di Sistema → Privacy e sicurezza → **Apri comunque**).
3. Doppio clic su **`Avvia.command`**: si apre il browser con l'app.
4. Se il doppio clic viene bloccato anche dopo "Apri comunque": `xattr -dr com.apple.quarantine ~/Documents/confronta-portafogli-v1.1.0` (nel Terminale).

**Aggiornamento dalla 1.0**: copia nella nuova cartella `configurazioni/` (i tuoi file), `cache_prezzi/` e `report/`, poi rilancia `Installa.command`. Dettagli nel README, punto 8.

## Limiti noti
- Il rendimento atteso è un'ipotesi, non una previsione; il futuro può essere diverso dal passato.
- Le fonti gratuite possono avere errori o limitare gli accessi; Stooq al momento non restituisce dati.
- Il livello di rischio di un portafoglio con volatilità vicina a una soglia può cambiare di uno tra un calcolo e l'altro.
- Il tema scuro va scelto dal menu ⋮ → Settings → Theme (Streamlit non segue da solo il tema del sistema con un tema personalizzato).
- I file `.command` non sono firmati da Apple: la prima volta serve "Apri comunque".
