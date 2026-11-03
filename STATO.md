# STATO del progetto – strumento riutilizzabile

## Tappe
- [x] 1. Motore generico e configurabile (`configurazione.py`, `dati.py`, `analisi.py`, `simula.py`, `metriche.py`) + test
- [x] 2. Script da riga di comando `confronta.py --config ...` -> report/AAAA-MM-GG_nome/ (HTML, PDF con reportlab, CSV con ; e virgola decimale per Excel)
- [ ] 3. App Streamlit
- [ ] 4. Script di installazione e avvio per Mac
- [ ] 5. README e release

## Scelte fatte (default ragionevoli)
- Rendimento atteso = media aritmetica annua (1 € vale in media 1+r dopo un anno), come nell'analisi iniziale.
- Metodo `beta`: beta stimato su rendimenti **settimanali** in EUR rispetto al benchmark (le borse chiudono a orari diversi:
  con i giornalieri il beta dei titoli USA verso un ETF quotato ad Amsterdam risulterebbe troppo basso). Solo dati reali.
- Il TER del benchmark è sottratto dopo la ricentratura; per altri ETF usati come titoli non viene sottratto (i loro prezzi storici sono già al netto, ma con la ricentratura il TER non è riconosciuto: limite noto).
- Calendario: giorni in cui almeno metà dei titoli quotati ha scambiato (gestisce borse diverse e festività).
- Valute: cambio giornaliero Yahoo `EURxxx=X`; per il dollaro prima del 2003 cambio FRED. Pence (GBp) divisi per 100.
- Settore (stress test e proxy analisi C): indicato in configurazione → settore Yahoo (se disponibile) → ETF di settore USA più correlato.
- Analisi B solo se il periodo comune (A) parte almeno un anno dopo `inizio_B`; altrimenti A copre già il periodo lungo.
- Il modulo "confronto tra modelli" include anche la sensibilità al rendimento atteso (variante più bassa e più alta).
- Stress test: lo shock di un portafoglio è la media pesata degli shock per categoria (tech/finanza/altro); dopo lo shock i versamenti continuano.

## Come riprendere
`python -m pytest -q tests` (offline). Esempio di configurazione: `configurazioni/esempio_tre_portafogli.yaml`.
L'analisi iniziale (rendimento uguale 6%) è in `esempi/2026-11-03_analisi_iniziale_rendimento_uguale_6/`.
- PDF generato con reportlab (solo Python, niente Chrome) e font DejaVu incluso in matplotlib.
- Stress test: una sola simulazione di "crescita di 1 €" per portafoglio riusata per tutti gli scenari (veloce); 1.000 percorsi.
