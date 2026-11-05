"""Validazione del modello di rischio (v1.5): backtest del VaR a 1 giorno, come fanno le banche.

Per ogni giorno si calcola il VaR con i soli dati passati (finestra mobile) e lo si confronta con il rendimento del giorno dopo.
Tre modelli:
- «storico»: quantile della finestra di 2 anni;
- «fattori»: dalla 1.5.1 segue il regime corrente (rischio di BREVE termine): esposizioni ricalcolate ogni mese sulla finestra, covarianza dei
  fattori EWMA (si aggiorna ogni giorno, lambda 0,97 = memoria di circa un mese), varianza specifica EWMA del portafoglio (tiene conto anche
  delle correlazioni tra i residui dei titoli) e code grasse (t di Student con gradi di libertà stimati sui residui standardizzati della finestra);
- «fattori (1.5.0)»: il modello della versione precedente (covarianza dei fattori su tutta la storia, rischio specifico medio della finestra,
  normale), tenuto per il confronto prima/dopo. Il modello a fattori resta quello per i rischi di lungo periodo; la simulazione non cambia.
Test di Kupiec (numero di sforamenti) e di Christoffersen (sforamenti raggruppati); esito a semaforo."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import fattori as FA

LIVELLI = (0.95, 0.99)
FINESTRA = 504  # 2 anni di borsa
PASSO = 21  # le esposizioni si ricalcolano ogni mese
LAMBDA_EWMA = 0.97  # memoria della covarianza EWMA: peso 0,97 al giorno prima (circa un mese di dati)
BURN_IN = 60  # giorni iniziali della finestra usati solo per avviare le medie EWMA
GDL_MIN, GDL_MAX = 4.5, 100.0  # gradi di libertà della t di Student: sopra GDL_MAX la distribuzione è praticamente normale
VECCHIO = "fattori (1.5.0)"
MODELLI = ("storico", "fattori", VECCHIO)


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


# ---------------------------------------------------------------- VaR a fattori che segue il regime corrente (1.5.1)
def covarianze_ewma(X: np.ndarray, lam: float = LAMBDA_EWMA, avvio: int = BURN_IN) -> np.ndarray:
    """S[i] = covarianza EWMA (media zero) dei rendimenti X (giorni × k) usando solo i dati fino al giorno i-1. Si parte dalla covarianza dei primi
    `avvio` giorni. Ritorna un array (giorni, k, k)."""
    X = np.atleast_2d(np.asarray(X, float))
    if X.shape[0] == 1 and X.shape[1] > 1:
        X = X.T
    T, k = X.shape
    s = np.atleast_2d(np.cov(X[: min(avvio, T)].T)) if T > 2 else np.zeros((k, k))
    out = np.empty((T, k, k))
    for i in range(T):
        out[i] = s
        s = lam * s + (1 - lam) * np.outer(X[i], X[i])
    return out


def varianza_ewma(e: np.ndarray, lam: float = LAMBDA_EWMA, avvio: int = BURN_IN) -> np.ndarray:
    """Varianza EWMA (media zero) di una serie: v[i] usa solo i dati fino al giorno i-1."""
    e = np.asarray(e, float)
    v0 = float(np.mean(e[: min(avvio, len(e))] ** 2)) if len(e) else 0.0
    out = np.empty(len(e))
    v = v0
    for i in range(len(e)):
        out[i] = v
        v = lam * v + (1 - lam) * e[i] ** 2
    return out


def stima_t(z: np.ndarray) -> tuple[float, float]:
    """(gradi di libertà, scala) della t di Student centrata in 0 stimata sui residui standardizzati z (massima verosimiglianza).
    Se le code non sono più grasse della normale i gradi di libertà vanno al massimo (= normale)."""
    z = np.asarray(z, float)
    z = z[np.isfinite(z)]
    if len(z) < 100:
        return GDL_MAX, float(z.std()) if len(z) else 1.0
    try:
        nu, _, scala = stats.t.fit(z, floc=0.0)
    except Exception:
        return GDL_MAX, float(z.std())
    return float(min(max(nu, GDL_MIN), GDL_MAX)), float(scala)


def var_fattori_ewma(
    M: np.ndarray, porte: dict, colonne: list, idx: pd.DatetimeIndex, F: pd.DataFrame, V: pd.DataFrame, conf: dict, livelli, lam: float = LAMBDA_EWMA,
    finestra=FINESTRA, passo=PASSO, code_grasse: bool = True,
) -> tuple[dict, dict]:  # fmt: skip
    """Per ogni portafoglio: VaR (uno per livello) del modello a fattori di breve termine, con NaN prima di avere la finestra.
    Esposizioni dalla regressione ridge sulla finestra (ogni `passo` giorni); covarianza dei fattori EWMA aggiornata ogni giorno; varianza specifica
    EWMA del residuo del PORTAFOGLIO (r − esposizioni·fattori), che comprende le correlazioni tra residui di titoli diversi; distribuzione t di Student
    con gradi di libertà stimati sui residui standardizzati della finestra (se `code_grasse`). Ritorna (VaR, {portafoglio: ultimi gradi di libertà})."""
    tick = list(dict.fromkeys(t for _, t in colonne))
    col_di = {t: next(i for i, (_, x) in enumerate(colonne) if x == t) for t in tick}
    R = pd.DataFrame({t: M[:, col_di[t]] for t in tick}, index=idx)
    Fi, Vi = F.reindex(idx).fillna(0.0), V.reindex(idx).fillna(False)
    # covarianza EWMA dei fattori sulla storia completa, poi presa nei giorni dell'analisi (il valore del giorno usa solo dati precedenti)
    S_tutta = covarianze_ewma(F.values, lam)
    pos = F.index.get_indexer(idx, method="pad")
    S = S_tutta[np.where(pos < 0, 0, pos)]
    Fv = Fi.values
    out = {p: {lv: np.full(len(idx), np.nan) for lv in livelli} for p in porte}
    gdl = {p: [] for p in porte}
    for t0 in range(finestra, len(idx), passo):
        w = slice(t0 - finestra, t0)
        fine = min(t0 + passo, len(idx))
        st = FA.stima_titoli(R.iloc[w], Fi.iloc[w], Vi.iloc[w], conf, tick)
        for p, (cols, pesi) in porte.items():
            nomi = [colonne[c][1] for c in cols]
            w_ = np.asarray(pesi, float)
            bp = w_ @ st.beta.reindex(nomi).values  # esposizioni del portafoglio ai fattori
            rp = M[t0 - finestra : fine][:, cols] @ w_
            f = Fv[t0 - finestra : fine]
            eps = rp - f @ bp  # residuo del portafoglio (rendimento non spiegato dai fattori)
            v_spec = varianza_ewma(eps, lam)
            v_fat = np.einsum("i,tij,j->t", bp, S[t0 - finestra : fine], bp)
            sig = np.sqrt(v_fat + v_spec)
            nu, scala = GDL_MAX, 1.0
            z = (rp / np.where(sig > 0, sig, np.nan))[BURN_IN:finestra]
            if code_grasse:
                nu, scala = stima_t(z)
            else:
                scala = float(np.nanstd(z))
            gdl[p].append(nu)
            for lv in livelli:
                q = -stats.t.ppf(1 - lv, nu) * scala if nu < GDL_MAX else stats.norm.ppf(lv) * scala
                out[p][lv][t0:fine] = q * sig[finestra:]
    return out, {p: float(np.median(g)) if g else np.nan for p, g in gdl.items()}


# ---------------------------------------------------------------- orchestrazione
def esegui(
    M: np.ndarray, porte: dict, colonne: list, idx: pd.DatetimeIndex, F, V, conf, livelli=LIVELLI, log=print, lam: float = LAMBDA_EWMA, code_grasse: bool = True
) -> dict:  # fmt: skip
    """M: rendimenti giornalieri (periodo A) con una colonna per (portafoglio, titolo). lam: memoria EWMA del modello a fattori di breve termine."""
    if len(idx) < FINESTRA + 250:
        raise ValueError(f"Servono almeno {FINESTRA + 250} giorni di storia comune per il backtest (ce ne sono {len(idx)}).")
    serie = {p: M[:, cols] @ np.asarray(w, float) for p, (cols, w) in porte.items()}  # rendimenti giornalieri, pesi costanti
    log("     backtest del VaR: stima dei fattori su finestra mobile")
    vv = var_fattori(M, porte, colonne, idx, F, V, conf, livelli)  # modello della 1.5.0 (storia lunga): per il confronto prima/dopo
    log("     backtest del VaR: modello a fattori di breve termine (covarianza e rischio specifico EWMA, code grasse)")
    vf, gdl = var_fattori_ewma(M, porte, colonne, idx, F, V, conf, livelli, lam, code_grasse=code_grasse)
    righe, flag, linee = [], {}, {}
    for p, r in serie.items():
        for lv in livelli:
            vs = var_storico(r, lv)
            ok = ~np.isnan(vs) & ~np.isnan(vf[p][lv])
            ok &= ~np.isnan(vv[p][lv])
            for mod, var in (("storico", vs), ("fattori", vf[p][lv]), (VECCHIO, vv[p][lv])):
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
        "ok": {p: ~np.isnan(var_storico(r, 0.95)) & ~np.isnan(vf[p][0.95]) & ~np.isnan(vv[p][0.95]) for p, r in serie.items()},
        "finestra": FINESTRA,
        "lambda": lam,
        "gdl": gdl,
    }
