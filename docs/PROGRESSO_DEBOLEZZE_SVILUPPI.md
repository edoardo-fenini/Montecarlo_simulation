# Progresso, debolezze e sviluppi

Aggiornato al 4 novembre 2026, dopo la versione **1.3.0** (consolidamento).
Nota: nelle versioni precedenti questo report era stato consegnato solo in chat (PDF). Da ora sta nel repository, così si aggiorna
insieme al codice.

## 1. Progresso: dove siamo

| Versione | Contenuto principale |
|---|---|
| 1.0 | Motore Monte Carlo configurabile, riga di comando, app Streamlit, installazione con doppio clic su Mac, report HTML/PDF/CSV |
| 1.1 | Più fonti di dati e modalità offline, report più leggibile («In una pagina», livello di rischio 1-5), grafici interattivi, analisi salvate, Excel, calcolo in parallelo |
| 1.2 | ISIN al posto dei ticker (OpenFIGI + Yahoo), controllo dei dati con semaforo che blocca la simulazione con un errore |
| **1.3** | Correzione di `StreamlitDuplicateElementId`, risultati vecchi nascosti, controllo incrociato dei nomi, importazione dal broker, ricerca per nome, release automatica, prova nel browser nel repository |

Numeri della 1.3:
- **Test automatici: 198** (112 a inizio 1.3), tutti senza internet, compresi 7 nel browser vero (Playwright + Chromium) e il test di
  non regressione (1.236 numeri, identici dalla 1.1).
- Workflow: **Test** (Linux, a ogni push, con la prova nel browser), **Prova su Mac** (macOS 14 Apple Silicon, installazione vera e dati
  reali), **Release** (dal tag `vX.Y.Z`: test, zip, release con le note del CHANGELOG).
- Nessuna funzione tolta; i numeri del calcolo non sono cambiati.

## 2. Cosa è cambiato nella 1.3 (in breve)
1. **Bug che fermava l'app** a fine analisi (`StreamlitDuplicateElementId`): riprodotto (analisi B uguale alla A → grafici identici →
   stesso ID automatico), corretto con chiavi univoche su tutti gli elementi, protetto da un test che impedisce di dimenticarle.
2. **Risultati vecchi**: nascosti con un avviso grande quando cambiano impostazioni, dati, o il controllo dei dati è rosso.
3. **Nomi**: confronto automatico OpenFIGI/Yahoo per ogni ISIN (giallo e quotazione successiva se non tornano); borse non riconosciute elencate.
4. **CSV del broker** (app e riga di comando) con anteprima; **ricerca per nome** con aggiunta in un clic.
5. **Release automatica** e regola dei tag `vX.Y.Z`; **prova nel browser** nel repository, con dati finti, nel workflow dei test.

## 3. Debolezze (aggiornate)

Risolte nella 1.3:
- ~~L'app poteva fermarsi a fine analisi con `StreamlitDuplicateElementId`~~ → corretto e protetto da test.
- ~~Risultati vecchi visibili dopo aver cambiato i dati~~ → avviso e nascondimento.
- ~~Nome del titolo controllato solo se scritto a mano in `nomi_attesi`~~ → controllo automatico OpenFIGI/Yahoo.
- ~~Quotazioni su borse sconosciute ignorate in silenzio~~ → elencate come informazione.
- ~~Release da creare a mano dal sito, tag con nomi incoerenti~~ → release automatica, formato unico `vX.Y.Z`.
- ~~La prova nel browser era fuori dal repository e dava un falso errore sulla tabella in canvas~~ → `tests/e2e/`, verifica dal testo associato.
- ~~Portafoglio da ricopiare a mano dal conto titoli~~ → importazione dal CSV del broker.

Ancora aperte:
- **Dipendenza da servizi gratuiti** (Yahoo Finance, OpenFIGI): possono limitare o cambiare senza preavviso. Mitigato da cache, più fonti,
  CSV manuali; non eliminabile senza un fornitore a pagamento.
- **La ricerca di Yahoo non dà gli ISIN** né sempre la valuta: la valuta si legge con una seconda chiamata per ogni risultato (più lenta,
  e può restare «?» se Yahoo limita gli accessi).
- **CSV del broker**: il controvalore è considerato in euro; formati molto particolari (più tabelle nello stesso file, colonne con nomi
  insoliti) possono non essere riconosciuti. Il messaggio d'errore dice quali colonne servono.
- **Confronto dei nomi** euristico: nomi molto abbreviati da OpenFIGI possono dare un giallo superfluo; la soglia è regolabile
  (`controllo_dati.somiglianza_nome_min`).
- **L'analisi B può coincidere con la A** (stesso periodo): oggi non dà più errori, ma il report mostra due analisi uguali. Toglierla in quel
  caso cambierebbe le uscite: rimandato per non toccare i risultati senza una decisione.
- **Prova su Mac solo su GitHub**: manca una prova manuale sul Mac dell'utente con la 1.3 (doppio clic, Gatekeeper, app completa).
- **Modello**: il rendimento atteso resta un'ipotesi; bootstrap a blocchi e modelli alternativi non coprono tutti i regimi di mercato.
- **I file `.command` non sono firmati** da Apple (serve «Apri comunque» la prima volta).

## 4. Sviluppi possibili (in ordine di utilità)
1. **Non mostrare l'analisi B quando coincide con la A** (con una nota nel report), dopo una decisione esplicita perché cambia le uscite.
2. **Importazione broker più ricca**: valuta del controvalore (colonna «Divisa»), modelli già pronti per i broker più usati (Fineco,
   Directa, Banca Sella, Degiro, Trade Republic), salvataggio della corrispondenza delle colonne.
3. **Ricerca per nome con ISIN**: completare i risultati con l'ISIN quando disponibile (es. tramite OpenFIGI per le azioni quotate).
4. **Ribilanciamento verso i pesi del conto reale**: confronto tra pesi attuali (dal CSV) e pesi obiettivo, con le operazioni suggerite.
5. **Pacchetto Mac firmato** (o un'app con icona) per evitare «Apri comunque».
6. **Controllo dei dati più severo sugli split e sui dividendi** (salti di prezzo non spiegati).
7. **Rendimento atteso da fonti esterne** (stime di consenso, CAPE) come alternativa al metodo beta.

## 5. Cosa deve fare l'utente
- Scaricare la release **v1.3.0** (se creata: vedi STATO.md) e provarla sul Mac con un'analisi completa, aprendo tutte le schede.
- Se il ramo predefinito del repository non è `main`: Settings → General → Default branch → `main`.
- Per le prossime versioni: aggiungere la sezione al `CHANGELOG.md` e avviare **Actions → Release → Run workflow** con la versione.
