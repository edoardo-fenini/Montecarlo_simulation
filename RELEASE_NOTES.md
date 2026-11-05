# v1.5.1 – Correzioni

Versione di correzioni dopo la 1.5.0. Nessuna funzione tolta; il modello storico resta il default. Le note complete, con i numeri prima/dopo, sono nella sezione 1.5.1 di `CHANGELOG.md`.

## Cosa cambia per te
- **Rendimento simulato = rendimento atteso.** Il controllo di plausibilità ha trovato un errore vero nel modello storico: con giorni «legati» tra loro (rimbalzi dopo i cali) il rendimento composto di un anno
  restava sotto l'atteso (banche, analisi B: 4,7% invece di 7,4% nel primo anno). Corretto, per tutte le analisi e tutti i metodi; il controllo ora misura il rendimento del primo anno.
- **Volatilità più vicina alla realtà.** Si misura sui rendimenti di un mese, non su quelli di un giorno: il mondo azionario in euro passa dal 19% (modello a fattori) al 16,3%, in linea con la storia (circa 16%).
  Corretti anche due valori sbagliati dell'indice MSCI World di Yahoo (aprile e settembre 2001). I livelli di rischio 1-5 possono spostarsi di uno vicino alle soglie.
- **Modello a fattori più completo:** VaR a 1 giorno che segue il regime corrente (EWMA, code grasse; sforamenti molto più vicini all'attesa), residui dei titoli ricampionati dalle stesse date (nelle crisi i titoli dello
  stesso settore si muovono insieme), fattori nati tardi ricostruiti dal mercato invece di valere 0.
- **Fondi:** menu con tutte le classi di quote candidate (nome, valuta, storia), scelta salvata nella configurazione.
- **Impostazioni:** ogni intervento della rete di sicurezza contro gli azzeramenti è scritto in `log.txt` («RETE DI SICUREZZA»). La causa vera non è stata riprodotta.

## Nuove opzioni (facoltative)
`var_breve_termine: {lambda_ewma: 0.97, code_grasse: true}` nel YAML; in `modelli/fattori.yaml`: `residui_congiunti`, `riempimento_fattori` (`zero` | `condizionato`), `pulizia_mercato`.

## Come aggiornare dalla 1.5.0
Scarica `confronta-portafogli-v1.5.1.zip`, estrailo in una nuova cartella, copia `configurazioni/`, `cache_prezzi/` e `report/` dalla vecchia, poi doppio clic su `Installa.command`.
I risultati salvati con la 1.5.0 restano com'erano; per confrontarli con i nuovi rilancia l'analisi.
