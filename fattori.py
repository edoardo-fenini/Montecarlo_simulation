"""Modello di rischio a fattori (v1.5).

Ogni titolo è scomposto in esposizioni (beta) a pochi fattori comuni più una parte specifica (residuo):
    rendimento titolo = alfa + somma(beta_k × fattore_k) + residuo
I beta si stimano con una regressione ridge sui rendimenti settimanali (per ridurre il problema dei fusi orari); la penalità
evita esposizioni assurde quando la storia è breve o i fattori sono correlati. Per simulare si ricampionano a blocchi i fattori
(storia lunga, dal 2000) e, in modo indipendente per ogni titolo, i suoi residui giornalieri.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

import dati as D
from configurazione import BENCH, ErroreConfig
from simula import GG, Bootstrap, allinea_media_composta

FILE_PREDEFINITO = str(pathlib.Path(__file__).resolve().parent / "modelli" / "fattori.yaml")
GRUPPI = {
    "mercato": "Mercato",
    "regioni": "Regioni",
    "settori": "Settori",
    "stile": "Stile",
    "tassi_valute": "Tassi e valute",
}
SPECIALE_MERCATO, SPECIALE_USD = "@MERCATO", "@USD_EUR"


# ---------------------------------------------------------------- configurazione dei fattori
def carica_config(percorso: str | None = None) -> dict:
    """Legge e controlla il file dei fattori. Solleva ErroreConfig con un messaggio chiaro."""
    percorso = percorso or FILE_PREDEFINITO
    try:
        with open(percorso, encoding="utf-8") as f:
            c = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise ErroreConfig(f"Non riesco a leggere il file dei fattori «{percorso}»: {e}") from None
    if not isinstance(c, dict) or not c.get("fattori"):
        raise ErroreConfig(f"Il file dei fattori «{percorso}» non contiene la lista «fattori».")
    c.setdefault("inizio_storia", "2000-01-03")
    c.setdefault("ridge", {})
    c["ridge"].setdefault("lambda", "auto")
    c["ridge"].setdefault("minimo", 0.5)
    c["ridge"].setdefault("frazione_minima", 0.5)
    c.setdefault("min_settimane", 52)
    c["residui_congiunti"] = bool(c.get("residui_congiunti", True))
    c.setdefault("r2_minimo_avviso", 0.30)
    try:
        c["inizio_storia"] = pd.Timestamp(c["inizio_storia"])
    except (ValueError, TypeError):
        raise ErroreConfig("«inizio_storia» nel file dei fattori deve essere una data (AAAA-MM-GG).") from None
    nomi = []
    for f in c["fattori"]:
        if not isinstance(f, dict) or not f.get("nome") or not f.get("lungo"):
            raise ErroreConfig("Ogni fattore deve avere «nome» e «lungo» (il ticker).")
        if f.get("gruppo") not in GRUPPI:
            raise ErroreConfig(f"Il fattore «{f['nome']}» ha un gruppo non valido: usa uno tra {', '.join(GRUPPI)}.")
        nomi.append(f["nome"])
    if len(set(nomi)) != len(nomi):
        raise ErroreConfig("Nel file dei fattori ci sono due fattori con lo stesso nome.")
    if not any(f["gruppo"] == "mercato" for f in c["fattori"]):
        raise ErroreConfig("Nel file dei fattori serve almeno un fattore del gruppo «mercato».")
    return c


# ---------------------------------------------------------------- serie dei fattori
def togli_picchi(s: pd.Series, rif: pd.Series, soglia: float = 15.0) -> tuple[pd.Series, list]:
    """Corregge i valori sbagliati isolati di un indice (es. MSCI World su Yahoo nel 2001: +11,9% e il giorno dopo −13,2% mentre l'S&P 500 faceva −3,3% e +0,4%).
    Un giorno è un «picco» se il rendimento dell'indice si discosta da quello della serie di riferimento (stessa valuta) di più di `soglia` volte lo scarto tipico
    (MAD) e il giorno dopo si discosta altrettanto nel verso opposto: un errore che si annulla. Il rendimento del primo giorno diventa quello atteso dal
    riferimento (beta × riferimento) e quello del secondo si adegua, così il livello dell'indice dopo i due giorni resta quello originale.
    Ritorna (serie corretta, lista delle date corrette)."""
    r = s.pct_change(fill_method=None)
    q = rif.reindex(s.index).pct_change(fill_method=None)
    ok = r.notna() & q.notna()
    if ok.sum() < 250:
        return s, []
    x, y = q[ok].values, r[ok].values
    beta = float(np.cov(x, y)[0, 1] / x.var(ddof=1))
    res = (r - beta * q).values
    sig = 1.4826 * float(np.nanmedian(np.abs(res[ok.values] - np.nanmedian(res[ok.values]))))
    rr = r.values.copy()
    corrette = []
    for t in range(len(rr) - 1):
        a, b = res[t], res[t + 1]
        if np.isnan(a) or np.isnan(b) or a * b >= 0 or min(abs(a), abs(b)) <= soglia * sig:
            continue
        atteso = beta * q.values[t]
        if np.isnan(atteso):
            continue
        cumulato = (1 + rr[t]) * (1 + rr[t + 1])
        rr[t] = atteso
        rr[t + 1] = cumulato / (1 + atteso) - 1
        corrette.append(s.index[t])
    if not corrette:
        return s, []
    out = pd.Series(s.iloc[0] * np.cumprod(1.0 + np.nan_to_num(rr, nan=0.0)), index=s.index)
    return out, corrette


def _prezzi(arch: D.Archivio, t: str, locale: bool, valuta: str | None) -> pd.Series:
    if t == SPECIALE_USD:
        return 1.0 / D.cambio(arch, "USD")
    if locale:
        s, _ = arch.prezzi(t)
        return s
    return D.serie_eur(arch, t, valuta_default=valuta or "USD")[0]


def serie_fattori(conf: dict, arch: D.Archivio, log=print) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Ritorna (F, valido, info): rendimenti giornalieri dei fattori (0 prima dell'inizio), maschera dei dati veri, tabella
    con gruppo, ticker e data di inizio di ogni fattore. Calendario = giorni del fattore «mercato» dall'inizio della storia."""
    fatt = conf["fattori"]
    cache: dict[tuple, pd.Series] = {}

    def prezzi(t, locale, valuta):
        k = (t, locale, valuta)
        if k not in cache:
            cache[k] = _prezzi(arch, t, locale, valuta)
        return cache[k]

    mercato = next(f for f in fatt if f["gruppo"] == "mercato")
    s_merc = prezzi(mercato["lungo"], bool(mercato.get("valuta_locale")), mercato.get("valuta"))
    pul = conf.get("pulizia_mercato") or {}
    picchi: list = []
    if pul.get("riferimento"):  # valori sbagliati isolati dell'indice di mercato, controllati con una serie di riferimento
        rif = prezzi(pul["riferimento"], False, pul.get("valuta", "USD"))
        s_merc, picchi = togli_picchi(s_merc, rif, float(pul.get("soglia", 15.0)))
        cache[(mercato["lungo"], bool(mercato.get("valuta_locale")), mercato.get("valuta"))] = s_merc
        if picchi:
            log(f"  fattore mercato: {len(picchi)} valori isolati sbagliati corretti ({', '.join(f'{d:%d/%m/%Y}' for d in picchi[:6])})")
    cal = s_merc.index[(s_merc.index >= conf["inizio_storia"]) & (s_merc.index.day_of_week < 5)]
    if len(cal) < 500:
        raise D.ErroreDati("Il fattore «mercato» ha troppo poca storia dopo la data di inizio.")
    cols, valido, righe = {}, {}, []
    r_merc = D._allinea(s_merc, cal).pct_change(fill_method=None)
    for f in fatt:
        try:
            if f["lungo"] == SPECIALE_MERCATO:
                lungo = r_merc
            else:
                lungo = D._allinea(prezzi(f["lungo"], bool(f.get("valuta_locale")), f.get("valuta")), cal).pct_change(fill_method=None)
            corto = None
            if f.get("corto"):
                corto = r_merc if f["corto"] == SPECIALE_MERCATO else D._allinea(prezzi(f["corto"], False, f.get("valuta")), cal).pct_change(fill_method=None)
        except D.ErroreDati as e:
            raise D.ErroreDati(f"Fattore «{f['nome']}»: {e}") from None
        r = lungo if corto is None else lungo - corto
        v = r.notna()
        cols[f["nome"]], valido[f["nome"]] = r, v
        primo = r.first_valid_index()
        righe.append(
            {
                "fattore": f["nome"],
                "gruppo": GRUPPI[f["gruppo"]],
                "ticker": f["lungo"] + (f" − {f['corto']}" if f.get("corto") else ""),
                "inizio": primo.date() if primo is not None else None,
                "descrizione": f.get("descrizione", ""),
            }
        )
        log(f"  fattore {f['nome']}: dal {primo:%d/%m/%Y}" if primo is not None else f"  fattore {f['nome']}: nessun dato")
    F = pd.DataFrame(cols, index=cal).iloc[1:]
    V = pd.DataFrame(valido, index=cal).iloc[1:]
    senza = [r["fattore"] for r in righe if r["inizio"] is None]
    if senza:
        raise D.ErroreDati(f"Nessun dato per i fattori: {', '.join(senza)}.")
    info = pd.DataFrame(righe).set_index("fattore")
    info.attrs["picchi_corretti"] = [d.date().isoformat() for d in picchi]
    return F.fillna(0.0), V, info


# ---------------------------------------------------------------- regressione ridge
def ridge_gcv(
    X: np.ndarray, y: np.ndarray, lam: float | str = "auto", minimo: float = 0.5, liberi: tuple = (), frazione_min: float = 0.0
) -> tuple[np.ndarray, float, float]:
    """Ridge sui fattori standardizzati. Ritorna (beta sulla scala originale, intercetta, penalità usata).
    liberi: indici dei fattori NON penalizzati (il mercato: l'esposizione al mercato non va ridotta verso 0, solo gli scostamenti).
    lam='auto': penalità scelta per convalida incrociata generalizzata, mai sotto max(minimo, frazione_min × n osservazioni)."""
    n = len(y)
    xm, ym = X.mean(0), y.mean()
    sd = X.std(0)
    Xc, yc = X - xm, y - ym
    lib = [j for j in liberi if sd[j] > 1e-12]
    pen = [j for j in range(X.shape[1]) if j not in lib and sd[j] > 1e-12]
    beta = np.zeros(X.shape[1])
    if not pen and not lib:
        return beta, float(ym), 0.0
    if lib:  # tolgo dalla parte penalizzata ciò che i fattori liberi già spiegano
        Mf = Xc[:, lib]
        proiez = lambda A: A - Mf @ np.linalg.lstsq(Mf, A, rcond=None)[0]  # noqa: E731
    else:
        proiez = lambda A: A  # noqa: E731
    lam_usata = 0.0
    if pen:
        Z = Xc[:, pen] / sd[pen]
        Zr, yr = proiez(Z), proiez(yc)
        U, s, Vt = np.linalg.svd(Zr, full_matrices=False)
        uty = U.T @ yr
        gdl_lib = len(lib)
        base = max(minimo, frazione_min * n)
        if lam == "auto":
            migliore, scelta = np.inf, base
            for p in np.geomspace(max(base, 1e-3), 1e5, 60):
                d = s**2 / (s**2 + p)
                res = yr - U @ (d * uty)
                gcv = n * float(res @ res) / (n - d.sum() - gdl_lib) ** 2
                if gcv < migliore:
                    migliore, scelta = gcv, p
            lam_usata = scelta
        else:
            lam_usata = max(float(lam), 0.0)
        b_std = Vt.T @ (s / (s**2 + lam_usata) * uty)
        beta[pen] = b_std / sd[pen]
    if lib:
        resto = yc - Xc[:, pen] @ beta[pen] if pen else yc
        beta[lib] = np.linalg.lstsq(Xc[:, lib], resto, rcond=None)[0]
    return beta, float(ym - xm @ beta), lam_usata


@dataclass
class Stima:
    """Risultato della stima per tutti i titoli."""

    nomi_fattori: list
    beta: pd.DataFrame  # titoli × fattori
    alfa_sett: pd.Series  # intercetta settimanale (non usata per simulare: la media si sceglie con il rendimento atteso)
    r2: pd.Series
    n_sett: pd.Series
    penalita: pd.Series
    vol: pd.Series  # volatilità annua totale (giornaliera × √252)
    vol_specifica: pd.Series  # volatilità annua dei residui
    residui: dict  # titolo -> array dei residui giornalieri (media 0)
    note: list  # avvisi (titoli con poca storia, fattori esclusi...)
    fattori_esclusi: dict  # titolo -> fattori non usati per mancanza di storia
    date_residui: dict = field(default_factory=dict)  # titolo -> date (DatetimeIndex) dei residui giornalieri: servono al bootstrap congiunto


def _settimanali_df(x: pd.DataFrame | pd.Series):
    return (1 + x).resample("W-FRI").prod(min_count=1) - 1


def stima_titoli(R: pd.DataFrame, F: pd.DataFrame, V: pd.DataFrame, conf: dict, titoli: list | None = None) -> Stima:
    """R: rendimenti giornalieri dei titoli (NaN prima della quotazione, colonna BENCH inclusa). F, V: vedi serie_fattori."""
    titoli = titoli or list(R.columns)
    nf = list(F.columns)
    Fw = _settimanali_df(F)
    # settimana valida per un fattore solo se tutti i giorni erano veri (la settimana a cavallo dell'inizio non vale)
    Vw = V.astype(float).resample("W-FRI").min().reindex(Fw.index).fillna(0).astype(bool)
    rid = conf["ridge"]
    mercati = {f["nome"] for f in conf["fattori"] if f["gruppo"] == "mercato"}
    minw = int(conf["min_settimane"])
    betas, alfa, r2, nsett, pen, vol, volsp, residui, note, esclusi = {}, {}, {}, {}, {}, {}, {}, {}, [], {}
    date_res: dict = {}
    for t in titoli:
        r = R[t].dropna()
        r = r[r.index.isin(F.index)]
        if t == BENCH and len(r) >= 60:
            # il benchmark è il mercato mondiale: il fattore «mercato» è lo stesso indice. Esposizione 1, nessun rischio specifico
            # (la differenza tra ETF e indice è soprattutto rumore di orari di chiusura e verrebbe contata come rischio in più).
            b = pd.Series(0.0, index=nf)
            b[next(iter(mercati))] = 1.0
            betas[t], alfa[t], r2[t], pen[t], nsett[t] = b, 0.0, np.nan, 0.0, len(_settimanali_df(r).dropna())
            vol[t], volsp[t], residui[t] = float(r.std() * np.sqrt(252)), 0.0, np.zeros(2)
            date_res[t] = pd.DatetimeIndex([])
            continue
        if len(r) < 60:
            note.append(f"{t}: meno di 60 giorni di storia in comune con i fattori, non stimato.")
            continue
        yw = _settimanali_df(r).dropna()
        yw = yw[yw.index.isin(Fw.index)]
        usati = list(nf)
        # se un fattore nasce troppo tardi per questo titolo lo si toglie dalla stima (finché restano abbastanza settimane)
        tardivi = sorted(nf, key=lambda k: Vw[k].idxmax() if Vw[k].any() else pd.Timestamp.max, reverse=True)
        while True:
            righe = yw.index[Vw.loc[yw.index, usati].all(axis=1)]
            if len(righe) >= min(150, int(0.6 * len(yw))) or len(usati) <= 1:
                break
            esc = next(k for k in tardivi if k in usati and not Vw.loc[yw.index, k].all())
            usati.remove(esc)
            esclusi.setdefault(t, []).append(esc)
        if len(righe) < minw:
            # storia troppo breve: esposizione 1 al mercato, il resto è rischio specifico
            mk = nf[0]
            b = pd.Series(0.0, index=nf)
            b[mk] = 1.0
            note.append(f"{t}: meno di {minw} settimane di storia, uso esposizione 1 al mercato e il resto è rischio specifico.")
            a_s, l_s, pr2 = 0.0, 0.0, np.nan
            nsett[t] = len(righe)
        else:
            X, y = Fw.loc[righe, usati].values, yw.loc[righe].values
            liberi = tuple(i for i, k in enumerate(usati) if k in mercati)
            bu, a_s, l_s = ridge_gcv(X, y, rid["lambda"], float(rid["minimo"]), liberi, float(rid.get("frazione_minima", 0.0)))
            b = pd.Series(0.0, index=nf)
            b[usati] = bu
            res_w = y - (X @ bu + a_s)
            pr2 = 1 - res_w.var() / y.var() if y.var() > 0 else np.nan
            nsett[t] = len(righe)
        fit_d = F.loc[r.index].values @ b.values
        res_d = r.values - fit_d
        res_d = res_d - res_d.mean()
        betas[t], alfa[t], r2[t], pen[t] = b, a_s, pr2, l_s
        vol[t] = float(r.std() * np.sqrt(252))
        volsp[t] = float(res_d.std() * np.sqrt(252))
        residui[t] = res_d
        date_res[t] = r.index
    if not betas:
        raise D.ErroreDati("Nessun titolo ha abbastanza storia per il modello a fattori.")
    ix = list(betas)
    return Stima(
        nomi_fattori=nf,
        beta=pd.DataFrame(betas).T.reindex(columns=nf),
        alfa_sett=pd.Series(alfa),
        r2=pd.Series(r2),
        n_sett=pd.Series(nsett),
        penalita=pd.Series(pen),
        vol=pd.Series(vol).reindex(ix),
        vol_specifica=pd.Series(volsp).reindex(ix),
        residui=residui,
        note=note,
        fattori_esclusi=esclusi,
        date_residui=date_res,
    )


# ---------------------------------------------------------------- simulazione
class Fattoriale:
    """Generatore di rendimenti a fattori (stessa interfaccia di Bootstrap/StudentT: prepara + blocco).
    rendimento = centro + beta·(fattori − media) + (residuo − media). `centro` = rendimento medio giornaliero voluto per colonna
    (già ricentrato sul rendimento atteso e al netto dei costi, come per il metodo storico)."""

    def __init__(
        self, F: np.ndarray, beta: np.ndarray, residui: list, colonna_titolo: np.ndarray, centro: np.ndarray, blocco: int = 20, res_matrice: np.ndarray | None = None
    ):  # fmt: skip
        F = np.asarray(F, float)
        # res_matrice (giorni dei fattori × titoli, NaN dove il titolo non ha il residuo): se c'è, i residui si pescano dalle STESSE date dei
        # fattori (bootstrap congiunto), così le correlazioni tra residui di titoli diversi restano quelle reali; dove manca si ripesca
        # dalla storia del titolo, come prima.
        self.Rres = None if res_matrice is None else np.asarray(res_matrice, float)
        self.F = F - F.mean(0)
        self.beta = np.asarray(beta, float)  # (titoli unici × fattori)
        self.res = [np.asarray(x, float) - np.mean(x) for x in residui]
        self.col = np.asarray(colonna_titolo, int)
        self.centro = np.asarray(centro, float)
        self.boot = Bootstrap(self.F, blocco)

    def prepara(self, n, T, rng):
        self.n, self.rng = n, rng
        self.boot.prepara(n, T, rng)

    def blocco(self, m):
        f = self.boot.blocco(m)  # (n, GG, fattori)
        core = f @ self.beta.T  # (n, GG, titoli unici)
        if self.Rres is None:  # residui indipendenti tra titoli (1.5.0)
            for j, r in enumerate(self.res):
                core[:, :, j] += r[self.rng.integers(0, len(r), size=(self.n, GG))]
        else:  # bootstrap congiunto: stessa data storica dei fattori
            res = self.Rres[self.boot.idx[:, m * GG : (m + 1) * GG]]  # (n, GG, titoli unici)
            for j, r in enumerate(self.res):
                manca = np.isnan(res[:, :, j])
                if manca.any():
                    res[:, :, j][manca] = r[self.rng.integers(0, len(r), size=int(manca.sum()))]
            core += res
        return np.maximum(core[:, :, self.col] + self.centro, -0.99)


def matrice_residui(stima: Stima, F: pd.DataFrame, tick: list) -> np.ndarray:
    """Residui giornalieri di ogni titolo sulle date dei fattori (giorni × titoli); NaN dove il titolo non ha il residuo (non quotava o senza dati)."""
    out = np.full((len(F.index), len(tick)), np.nan)
    for j, t in enumerate(tick):
        d = stima.date_residui.get(t)
        if d is None or len(d) == 0 or len(stima.residui[t]) != len(d):
            continue
        pos = F.index.get_indexer(d)
        ok = pos >= 0
        out[pos[ok], j] = np.asarray(stima.residui[t])[ok]
    return out


def copertura_residui(stima: Stima, F: pd.DataFrame) -> dict:
    """{titolo: quota dei giorni della storia dei fattori in cui il titolo ha un residuo vero} (gli altri giorni il residuo è ripescato dalla sua storia)."""
    tick = [t for t in stima.beta.index if t != BENCH]
    m = matrice_residui(stima, F, tick)
    return {t: float(np.mean(~np.isnan(m[:, j]))) for j, t in enumerate(tick)}


def prepara_generatore(stima: Stima, F: pd.DataFrame, colonne: list, Mr: np.ndarray, blocco: int = 20, congiunti: bool = True) -> dict:
    """Dati (leggeri e serializzabili) per costruire il generatore in un altro processo. colonne: [(portafoglio, titolo)]."""
    tick = list(dict.fromkeys(t for _, t in colonne))
    mancanti = [t for t in tick if t not in stima.residui]
    if mancanti:
        raise D.ErroreDati(f"Titoli senza stima a fattori: {', '.join(mancanti)}.")
    col = np.array([tick.index(t) for _, t in colonne])
    beta = stima.beta.loc[tick].values
    centro = np.asarray(Mr).mean(0)
    # dalla 1.5.1: come per il bootstrap dei titoli, il legame tra giorni vicini dei fattori sposta la crescita annua attesa;
    # si corregge il centro (meno di 0,01% al giorno) perché 1 € cresca in media esattamente del rendimento annuo atteso.
    # I residui ripescati dalla storia del titolo sono indipendenti e a media zero: non cambiano il valore atteso. Quelli del bootstrap congiunto
    # viaggiano con le date dei fattori: entrano nel calcolo (dove mancano valgono 0).
    res_m = matrice_residui(stima, F, tick) if congiunti else None
    Fv = F.values - F.values.mean(0)
    X = (Fv @ beta.T)[:, col] + centro
    if res_m is not None:
        X = X + np.nan_to_num(res_m, nan=0.0)[:, col]
    centro = centro + allinea_media_composta(X, blocco)[1]
    return {
        "F": F.values,
        "beta": beta,
        "residui": [stima.residui[t] for t in tick],
        "colonna_titolo": col,
        "centro": centro,
        "blocco": blocco,
        "res_matrice": res_m,
    }


def crea_generatore(dati: dict) -> Fattoriale:
    return Fattoriale(dati["F"], dati["beta"], dati["residui"], dati["colonna_titolo"], dati["centro"], dati["blocco"], dati.get("res_matrice"))


# ---------------------------------------------------------------- scomposizione del rischio (tappa 2)
def scomposizione_rischio(stima: Stima, F: pd.DataFrame, pesi: dict, conf: dict) -> dict:
    """Quota della varianza di un portafoglio dovuta a ogni gruppo di fattori e al rischio specifico (somma 100%).
    pesi: {titolo: peso}. Varianza = beta_p' Σ_F beta_p + somma(w_i² σ²_res,i). Il contributo del gruppo g è
    beta_g' (Σ_F beta_p) (scomposizione di Eulero: i contributi sommano al totale anche con fattori correlati)."""
    tick = [t for t in pesi if t in stima.beta.index]
    w = np.array([pesi[t] for t in tick], float)
    w = w / w.sum()
    B = stima.beta.loc[tick].values
    bp = w @ B  # esposizione del portafoglio a ogni fattore
    S = np.cov(F.values.T) * 252
    S = np.atleast_2d(S)
    Sb = S @ bp
    var_f = float(bp @ Sb)
    var_s = float(sum((wi * stima.vol_specifica[t]) ** 2 for wi, t in zip(w, tick, strict=True)))
    tot = var_f + var_s
    gruppo = {f["nome"]: f["gruppo"] for f in conf["fattori"]}
    quote = {g: 0.0 for g in GRUPPI.values()}
    contr = {}
    for k, nome in enumerate(stima.nomi_fattori):
        c = bp[k] * Sb[k] / tot
        contr[nome] = float(c)
        quote[GRUPPI[gruppo[nome]]] += float(c)
    quote["Rischio specifico"] = var_s / tot
    return {
        "quote": quote,
        "contributi": contr,
        "esposizioni": pd.Series(bp, index=stima.nomi_fattori),
        "volatilita": float(np.sqrt(tot)),
        "pesi": dict(zip(tick, w, strict=True)),
    }


def avvisi_r2(stima: Stima, conf: dict) -> list[str]:
    soglia = float(conf["r2_minimo_avviso"])
    return [
        f"{t}: i fattori spiegano solo il {v:.0%} del suo rischio (R² sotto {soglia:.0%}): il modello a fattori lo descrive male."
        for t, v in stima.r2.items()
        if pd.notna(v) and v < soglia and t != BENCH
    ]
