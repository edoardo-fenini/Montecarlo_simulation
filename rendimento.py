"""Rendimento atteso: campi vuoti, avvisi (giallo/rosso) e controllo di plausibilità dei risultati.

- Un campo vuoto o non numerico non è mai interpretato come 0: è un errore ROSSO.
- GIALLO se il premio di mercato è 0 (nessun premio per il rischio) o se un portafoglio ha un rendimento atteso sotto l'1%.
- Dopo la simulazione: il rendimento medio annuo dei percorsi simulati deve coincidere con quello atteso (al netto dei costi), entro
  una tolleranza basata sull'errore standard della media. Se non coincide il risultato non è valido."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from configurazione import ErroreConfig

ROSSO, GIALLO = "ROSSO", "GIALLO"
SOGLIA_BASSO = 0.01  # sotto l'1% annuo: giallo
N_ERRORI_STANDARD = 5.0  # tolleranza = 5 errori standard (+ un margine fisso)
MARGINE_FISSO = 0.003  # 0,3% annuo: effetti di secondo ordine (pesi che si spostano tra un ribilanciamento e l'altro, interessi composti)


def numero_pct(valore, etichetta: str) -> float:
    """Percentuale scritta nell'app -> frazione. Vuoto o non numerico = ErroreConfig (mai 0 in silenzio)."""
    if valore is None or (isinstance(valore, str) and not valore.strip()):
        raise ErroreConfig(f"«{etichetta}» è vuoto: scrivi un numero (anche 0, se intendi proprio zero).")
    try:
        x = float(str(valore).replace(",", ".")) if isinstance(valore, str) else float(valore)
    except (TypeError, ValueError):
        raise ErroreConfig(f"«{etichetta}» deve essere un numero (trovato: {valore!r}).") from None
    if math.isnan(x):
        raise ErroreConfig(f"«{etichetta}» è vuoto: scrivi un numero (anche 0, se intendi proprio zero).")
    return x / 100.0


def avvisi_campi(metodo: str, rf, mrp, uguale, personalizzato: dict | None = None) -> list[tuple[str, str]]:
    """[(ROSSO|GIALLO, testo)] sui soli campi di input (non servono i dati). Valori in percentuale come nell'app."""
    out = []
    campi = {"beta": [("Tasso privo di rischio", rf), ("Premio di mercato", mrp)], "uguale": [("Rendimento medio annuo", uguale)]}.get(metodo, [])
    if metodo == "personalizzato":
        campi = [(f"Rendimento di «{k}»", v) for k, v in (personalizzato or {}).items()]
    validi = {}
    for etichetta, v in campi:
        try:
            validi[etichetta] = numero_pct(v, etichetta)
        except ErroreConfig as e:
            out.append((ROSSO, str(e)))
    if metodo == "beta" and validi.get("Premio di mercato") == 0:
        out.append((GIALLO, "Il premio di mercato è 0: con il metodo beta ogni portafoglio rende quanto il tasso privo di rischio, senza premio per il rischio."))
    return out


def avvisi_tabella(rend: pd.DataFrame | None) -> list[tuple[str, str]]:
    """GIALLO per ogni portafoglio con rendimento atteso annuo sotto l'1% (la tabella viene da analisi.spiega_rendimenti)."""
    out = []
    if rend is None:
        return out
    for p in rend.columns:
        mu = rend.loc["Rendimento atteso annuo", p]
        if pd.notna(mu) and mu < SOGLIA_BASSO:
            out.append((GIALLO, f"«{p}» ha un rendimento atteso di {mu * 100:.2f}% l'anno, sotto l'1%: controlla i dati di rendimento atteso."))
    return out


# ------------------------------------------------------------------ plausibilità dei risultati
def atteso_netto_annuo(mu_giornaliero_colonne: np.ndarray, indici: np.ndarray, pesi: np.ndarray, giorni: int = 252) -> float:
    """Rendimento annuo atteso del portafoglio dal rendimento medio giornaliero dei suoi titoli (media pesata, poi composizione)."""
    d = float(np.dot(pesi, mu_giornaliero_colonne[indici]))
    return (1.0 + d) ** giorni - 1.0


def controlla_plausibilita(som: dict, M: np.ndarray, porte: dict, attesi: dict | None = None, giorni: int = 252) -> pd.DataFrame:
    """Confronta, per ogni portafoglio, il rendimento medio annuo dei percorsi simulati con quello atteso.
    som: sommario della simulazione (contiene 'rend_sim': {portafoglio: {'media_giorn', 'se_giorn'}}).
    M: matrice dei rendimenti giornalieri già ricentrati usata dalla simulazione.
    attesi: {portafoglio: rendimento annuo atteso netto dei costi}; se manca si usa la media di M (metodo storico).
    Ritorna un DataFrame con atteso, simulato, tolleranza, scarto ed esito (colonna 'ok')."""
    mu_col = np.asarray(M, float).mean(axis=0)
    righe = {}
    for p, (cols, w) in porte.items():
        r = som["rend_sim"][p]
        sim = (1.0 + r["media_giorn"]) ** giorni - 1.0
        att = (attesi or {}).get(p)
        if att is None:
            att = atteso_netto_annuo(mu_col, np.asarray(cols), np.asarray(w, float), giorni)
        tol = N_ERRORI_STANDARD * r["se_giorn"] * giorni + MARGINE_FISSO
        righe[p] = {"atteso": att, "simulato": sim, "tolleranza": tol, "scarto": sim - att, "ok": bool(abs(sim - att) <= tol)}
    return pd.DataFrame(righe).T


def messaggio_plausibilita(per_analisi: dict[str, pd.DataFrame]) -> str | None:
    """None se tutto coincide, altrimenti il testo dell'errore ROSSO."""
    brutte = []
    for a, df in per_analisi.items():
        for p, r in df.iterrows():
            if not r["ok"]:
                brutte.append(
                    f"analisi {a}, «{p}»: atteso {r['atteso'] * 100:.2f}%, simulato {r['simulato'] * 100:.2f}% "
                    f"(scarto {r['scarto'] * 100:+.2f}%, tolleranza ±{r['tolleranza'] * 100:.2f}%)"
                )
    if not brutte:
        return None
    return (
        "Controllo di plausibilità FALLITO: il rendimento medio annuo dei percorsi simulati non coincide con quello atteso. "
        "I risultati non sono affidabili e non vengono presentati come validi. " + "; ".join(brutte)
    )
