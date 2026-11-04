"""Validazione del modello di rischio (v1.5): backtest del VaR a 1 giorno, come fanno le banche.

Per ogni giorno si calcola il VaR con i soli dati passati (finestra mobile) e lo si confronta con il rendimento del giorno dopo.
Due modelli: «storico» (quantile della finestra di 2 anni) e «fattori» (esposizioni ricalcolate ogni mese sulla finestra, covarianza dei
fattori su tutta la loro storia fino a quel giorno + rischio specifico della finestra). Test di Kupiec (numero di sforamenti) e
di Christoffersen (sforamenti raggruppati); esito a semaforo."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import fattori as FA

LIVELLI = (0.95, 0.99)
FINESTRA = 504  # 2 anni di borsa
PASSO = 21  # le esposizioni si ricalcolano ogni mese
MODELLI = ("storico", "fattori")


# ---------------------------------------------------------------- test statistici
def kupiec(n: int, x: int, p: float) -> tuple[float, float]:
    """Test di copertura (POF): LR e p-value. p = probabilità attesa di sforamento (es. 0,05)."""
    if n <= 0:
        return np.nan, np.nan
    pi = x / n
    ll0 = (n - x) * np.log(1 - p) + x * np.log(p)
    ll1 = (n - x) * np.log(1 - pi) if x == 0 else (x * np.log(pi) if x == n else (n - x) * np.log(1 - pi) + x * np.log(pi))
    lr = max(-2 * (ll0 - ll1), 0.0)
    return float(lr), float(1 - stats.chi2.cdf(lr, 1))


def christoffersen(sforamenti: np.ndarray) -> tuple[float, float]:
    """Test di indipendenza: gli sforamenti sono raggruppati? LR e p-value (chi² con 1 grado di libertà)."""
    h = np.asarray(sforamenti, int)
    a, b = h[:-1], h[1:]
    n00, n01 = int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n10, n11 = int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum())
    if n01 + n11 == 0 or n00 + n10 == 0:
        return 0.0, 1.0  # nessuno sforamento (o sempre): niente da testare

    def ll(n_no, n_si, p):
        out = 0.0
        if n_no:
            out += n_no * np.log(1 - p) if p < 1 else -np.inf
        if n_si:
            out += n_si * np.log(p) if p > 0 else -np.inf
        return out

    p01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    p11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    p = (n01 + n11) / (n00 + n01 + n10 + n11)
    lr = -2 * (ll(n00 + n10, n01 + n11, p) - ll(n00, n01, p01) - ll(n10, n11, p11))
    lr = max(float(lr), 0.0)
    return lr, float(1 - stats.chi2.cdf(lr, 1))


def semaforo(p_kupiec: float, p_chr: float) -> str:
    """verde: entrambi i test non rifiutano (p ≥ 5%); giallo: uno sotto il 5%; rosso: uno sotto l'1%."""
    m = min(p_kupiec, p_chr)
    return "verde" if m >= 0.05 else ("giallo" if m >= 0.01 else "rosso")


def valuta(rend: np.ndarray, var: np.ndarray, livello: float) -> dict:
    s = (rend < -var).astype(int)
    n, x = len(s), int(s.sum())
    p = 1 - livello
    lr_k, p_k = kupiec(n, x, p)
    lr_c, p_c = christoffersen(s)
    return {
        "giorni": n,
        "sforamenti": x,
        "attesi": n * p,
        "frequenza": x / n if n else np.nan,
        "p_kupiec": p_k,
        "p_christoffersen": p_c,
        "semaforo": semaforo(p_k, p_c),
        "flag": s,
    }


# ---------------------------------------------------------------- VaR dei due modelli
def var_storico(r: np.ndarray, livello: float, finestra: int = FINESTRA) -> np.ndarray:
    """VaR del giorno i = quantile (1-livello) dei `finestra` rendimenti precedenti (cambiato di segno). NaN prima di avere la finestra."""
    out = np.full(len(r), np.nan)
    for i in range(finestra, len(r)):
        out[i] = -np.quantile(r[i - finestra : i], 1 - livello)
    return out


def var_fattori(
    M: np.ndarray, porte: dict, colonne: list, idx: pd.DatetimeIndex, F: pd.DataFrame, V: pd.DataFrame, conf: dict, livelli, finestra=FINESTRA, passo=PASSO
) -> dict:
    """Per ogni portafoglio: array dei VaR (uno per livello) con NaN prima di avere la finestra."""
    tick = list(dict.fromkeys(t for _, t in colonne))
    col_di = {t: next(i for i, (_, x) in enumerate(colonne) if x == t) for t in tick}
    R = pd.DataFrame({t: M[:, col_di[t]] for t in tick}, index=idx)
    Fi, Vi = F.reindex(idx).fillna(0.0), V.reindex(idx).fillna(False)
    out = {p: {lv: np.full(len(idx), np.nan) for lv in livelli} for p in porte}
    for t0 in range(finestra, len(idx), passo):
        w = slice(t0 - finestra, t0)
        st = FA.stima_titoli(R.iloc[w], Fi.iloc[w], Vi.iloc[w], conf, tick)
        S = np.atleast_2d(np.cov(F.loc[: idx[t0 - 1]].values.T))  # covarianza giornaliera dei fattori su tutta la storia fino a ieri
        for p, (cols, pesi) in porte.items():
            nomi = [colonne[c][1] for c in cols]
            w_ = np.asarray(pesi, float)
            B = st.beta.reindex(nomi).values
            bp = w_ @ B
            var_g = float(bp @ S @ bp) + sum((wi * st.vol_specifica[t] / np.sqrt(252)) ** 2 for wi, t in zip(w_, nomi, strict=True))
            sd = np.sqrt(var_g)
            for lv in livelli:
                out[p][lv][t0 : t0 + passo] = stats.norm.ppf(lv) * sd
    return out


# ---------------------------------------------------------------- orchestrazione
def esegui(M: np.ndarray, porte: dict, colonne: list, idx: pd.DatetimeIndex, F, V, conf, livelli=LIVELLI, log=print) -> dict:
    """M: rendimenti giornalieri (periodo A) con una colonna per (portafoglio, titolo)."""
    if len(idx) < FINESTRA + 250:
        raise ValueError(f"Servono almeno {FINESTRA + 250} giorni di storia comune per il backtest (ce ne sono {len(idx)}).")
    serie = {p: M[:, cols] @ np.asarray(w, float) for p, (cols, w) in porte.items()}  # rendimenti giornalieri, pesi costanti
    log("     backtest del VaR: stima dei fattori su finestra mobile")
    vf = var_fattori(M, porte, colonne, idx, F, V, conf, livelli)
    righe, flag, linee = [], {}, {}
    for p, r in serie.items():
        for lv in livelli:
            vs = var_storico(r, lv)
            ok = ~np.isnan(vs) & ~np.isnan(vf[p][lv])
            for mod, var in (("storico", vs), ("fattori", vf[p][lv])):
                e = valuta(r[ok], var[ok], lv)
                righe.append({"serie": p, "modello": mod, "livello": lv, **{k: v for k, v in e.items() if k != "flag"}})
                flag[(p, mod, lv)] = e["flag"]
                linee[(p, mod, lv)] = np.where(ok, var, np.nan)
    return {
        "tabella": pd.DataFrame(righe),
        "date": idx,
        "rend": serie,
        "var": linee,
        "flag": flag,
        "ok": {p: ~np.isnan(var_storico(r, 0.95)) & ~np.isnan(vf[p][0.95]) for p, r in serie.items()},
        "finestra": FINESTRA,
    }
