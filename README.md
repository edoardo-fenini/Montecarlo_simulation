# Confronto del rischio di 3 portafogli azionari (Monte Carlo)

Confronta cyber security, banche d'investimento/asset management/PE e big tech USA con un ETF azionario mondiale (MSCI World), partendo da 5.000 € senza versamenti, su 15 anni, con risultati a 5, 10 e 15 anni.
**Non è consulenza finanziaria.**

## Come aprire il report
Apri `report.html` con un doppio clic (si apre nel browser; i grafici sono già dentro il file, non serve internet).
Se sei su GitHub, scarica il file dal repository (pulsante *Download raw file*) e aprilo dal tuo computer.

## Come rilanciare tutto
```bash
python3 -m venv .venv
. .venv/bin/activate          # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scarica_dati.py        # scarica i prezzi in data/ (solo la prima volta o per aggiornarli)
python confronta.py           # simulazione completa (20.000 simulazioni) e report.html
```
Altri comandi utili:
```bash
python confronta.py --veloce      # prova rapida con 1.000 simulazioni -> report_veloce.html
python confronta.py --tappa 3     # si ferma alla tappa 3 (1 base, 2 stress, 3 analisi C, ... vedi sotto)
python confronta.py --rifai       # ricalcola tutto ignorando i risultati salvati in risultati/
python -m pytest tests            # test di correttezza
```
Le tappe: 2 = versione base, 3 = + stress test, 4 = + analisi C con proxy, 5 = + modelli, sensibilità e rischio sul singolo titolo.
I risultati intermedi sono salvati in `risultati/`: se cambi solo il report, il rilancio è rapido. **Se cambi parametri o titoli in `config.yaml` usa `--rifai`.**

## Come cambiare titoli e parametri (`config.yaml`)
- `capitale_iniziale`, `versamento_mensile`, `orizzonte_anni`, `checkpoint_anni` (gli orizzonti mostrati), `n_simulazioni`, `seed`.
- `rendimento_atteso`: rendimento medio annuo uguale per tutti (default 6%).
- `costo_ribilanciamento`: costo sul ribilanciamento annuale (0,1%).
- `portafogli`: elenco dei titoli (ticker Yahoo) di ogni portafoglio, a pesi uguali. Dopo aver cambiato un titolo, rilancia `python scarica_dati.py`.
- `benchmark`: ETF e TER. `rendimenti_settoriali`: scenario con rendimenti diversi per settore.
- `idio_p_anno`: probabilità annua di crollo di un singolo titolo (robustezza 4).

## File
| File | Cosa fa |
|---|---|
| `scarica_dati.py` | scarica prezzi (Yahoo Finance) e cambio EUR/USD (Yahoo + FRED) in `data/` |
| `dati.py` | conversione in EUR, periodi A/B/C, proxy, controlli sui dati |
| `simula.py` | motore Monte Carlo (bootstrap a blocchi, Student-t, GARCH, crolli sul singolo titolo) |
| `metriche.py` | tabelle, drawdown, VaR/ES, stress test |
| `report.py` | costruisce `report.html` |
| `confronta.py` | script principale |
| `tests/` | test pytest |
| `STATO.md` | a che punto siamo e come riprendere |

## Cosa significano le analisi A, B, C
- **A**: dal 02/07/2021, quando esistono tutti i titoli (circa 5 anni). Confronto equo ma breve.
- **B**: dal 2007, ogni portafoglio usa i titoli già quotati (pesi uguali tra quelli disponibili).
- **C**: dal 1999, con rendimenti sintetici (proxy settoriale XLK/XLF) per i giorni in cui un titolo non esisteva. Non sono dati reali.
