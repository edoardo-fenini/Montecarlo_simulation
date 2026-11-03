"""Caricamento prezzi, conversione in EUR, costruzione dei periodi A/B/C, controlli di qualità."""
import numpy as np, pandas as pd, yaml


def carica_config(path="config.yaml"):
    return yaml.safe_load(open(path))


def titoli_portafoglio(cfg):
    return {k: list(p["titoli"]) for k, p in cfg["portafogli"].items()}


def carica_prezzi():
    px = pd.read_csv("data/prices.csv", index_col=0, parse_dates=True)
    fred = pd.read_csv("data/fx_fred.csv", index_col=0, parse_dates=True).iloc[:, 0]
    return px, fred


def serie_cambio(px, fred, cfg, calendario):
    """USD per 1 EUR: Yahoo dal 2003, FRED prima. Riempito in avanti sul calendario USA."""
    y = px[cfg["cambio"]].dropna()
    fx = pd.concat([fred[fred.index < y.index[0]], y]).sort_index()
    fx = fx[~fx.index.duplicated()]
    return fx.reindex(fx.index.union(calendario)).ffill().reindex(calendario)


def rendimenti_eur(cfg, px=None, fred=None):
    """Rendimenti giornalieri semplici in EUR di tutti i titoli, benchmark e proxy.
    Calendario = giorni di borsa USA (date di XLK). Ritorna (R, prezzi_eur)."""
    if px is None:
        px, fred = carica_prezzi()
    cal = px["XLK"].dropna().index
    fx = serie_cambio(px, fred, cfg, cal)
    b = cfg["benchmark"]
    eur = pd.DataFrame(index=cal)
    for t in px.columns:
        if t in (cfg["cambio"], b["ticker"]):
            continue
        s = px[t].reindex(cal)
        first, last = px[t].first_valid_index(), px[t].last_valid_index()
        s = s.where((s.index >= first) & (s.index <= last)).ffill(limit=5)
        eur[t] = s / fx
    ret = eur.pct_change(fill_method=None)
    # Benchmark: indice MSCI World Net (USD->EUR) meno TER prima della nascita dell'ETF, poi l'ETF in EUR
    ter_d = b["ter"] / cfg["giorni_anno"]
    idx = ret[b["proxy_storico"]] - ter_d
    etf = px[b["ticker"]].reindex(cal.union(px[b["ticker"]].dropna().index)).ffill(limit=5).reindex(cal)
    etf = etf.where(etf.index >= px[b["ticker"]].first_valid_index())
    etf_r = etf.pct_change(fill_method=None)
    ret["BENCH"] = etf_r.where(etf_r.notna(), idx.where(etf.index < px[b["ticker"]].first_valid_index()))
    ret = ret.drop(columns=[b["proxy_storico"]])
    return ret.iloc[1:], eur


def _tutte_colonne(cfg):
    cols = [t for ts in titoli_portafoglio(cfg).values() for t in ts]
    return cols + ["BENCH"]


def riempi_con_media(R, cfg):
    """Analisi B: un titolo non ancora quotato prende il rendimento medio (pesi uguali)
    dei titoli disponibili dello stesso portafoglio in quel giorno."""
    R = R.copy()
    for ts in titoli_portafoglio(cfg).values():
        media = R[ts].mean(axis=1)
        for t in ts:
            R[t] = R[t].fillna(media)
    return R.dropna()


def riempi_con_proxy(R, cfg, seed=7):
    """Analisi C: per i giorni in cui il titolo non esisteva usa proxy*beta + residui ribootstrappati,
    con volatilità e correlazione stimate sui giorni reali. Ritorna (R_completo, frazione_proxy)."""
    rng = np.random.default_rng(seed)
    R = R.copy()
    frac = {}
    for key, p in cfg["portafogli"].items():
        proxy = R[p["proxy"]]
        for t in p["titoli"]:
            reale = R[t].notna()
            frac[t] = float((~reale).mean())
            if reale.all():
                continue
            ok = reale & proxy.notna()
            y, x = R.loc[ok, t].values, proxy[ok].values
            beta = np.cov(x, y)[0, 1] / x.var(ddof=1)
            resid = y - y.mean() - beta * (x - x.mean())
            mancanti = ~reale
            sint = beta * proxy[mancanti].values + rng.choice(resid, size=mancanti.sum())
            R.loc[mancanti, t] = sint
    return R.dropna(subset=_tutte_colonne(cfg)), frac


def costruisci_analisi(cfg, R_completo):
    """Ritorna dict {'A': (R, info), 'B': ..., 'C': ...} con solo le colonne titoli + BENCH."""
    cols = _tutte_colonne(cfg)
    out = {}
    dati = R_completo
    primo = max(dati[t].first_valid_index() for t in cols)
    A = dati.loc[primo:, cols].iloc[1:].dropna()
    out["A"] = (A, {"proxy": {}})
    iniB = pd.Timestamp(cfg["analisi"]["B"]["inizio"])
    B = riempi_con_media(dati.loc[iniB:, cols], cfg)
    out["B"] = (B, {"proxy": {}})
    iniC = pd.Timestamp(cfg["analisi"]["C"]["inizio"])
    extra = list({p["proxy"] for p in cfg["portafogli"].values()})
    C, frac = riempi_con_proxy(dati.loc[iniC:, cols + extra], cfg)
    out["C"] = (C[cols], {"proxy": frac})
    return out


def controlli(R, eur, cfg):
    """Controlli di qualità dei dati. Ritorna lista di avvisi testuali."""
    avvisi = []
    for t in R.columns:
        s = R[t].dropna()
        if t != "BENCH":
            e = eur[t].dropna()
            if (e <= 0).any():
                avvisi.append(f"{t}: prezzi <= 0")
            vuoti = eur[t].loc[e.index[0]:e.index[-1]].isna()
            if vuoti.sum():
                avvisi.append(f"{t}: {int(vuoti.sum())} giorni senza prezzo dentro la storia (buchi)")
        for d, v in s[s.abs() > 0.30].items():
            avvisi.append(f"{t}: rendimento giornaliero {v:+.0%} il {d.date()} (verificare: split o evento reale?)")
    return avvisi


if __name__ == "__main__":
    cfg = carica_config()
    R, eur = rendimenti_eur(cfg)
    av = controlli(R, eur, cfg)
    an = costruisci_analisi(cfg, R)
    righe = ["CONTROLLI DATI", f"Calendario: {R.index[0].date()} -> {R.index[-1].date()}"]
    for k, (r, info) in an.items():
        righe.append(f"Analisi {k}: {r.index[0].date()} -> {r.index[-1].date()}, {len(r)} giorni, {r.shape[1]} serie, NaN: {int(r.isna().sum().sum())}")
    righe += ["Avvisi:"] + (av or ["nessuno"])
    righe.append("Frazione di giorni sintetici (proxy) in analisi C: " + ", ".join(f"{t} {v:.0%}" for t, v in an["C"][1]["proxy"].items() if v > 0))
    open("data/controlli.txt", "w").write("\n".join(righe))
    print("\n".join(righe))
