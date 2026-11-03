"""Dati: download da Yahoo Finance con cache su disco, conversione in EUR, controlli,
classificazione automatica del settore (per stress test e proxy dell'analisi C)."""
import io, json, logging, os, re, urllib.request, warnings
import numpy as np
import pandas as pd
from configurazione import BENCH

warnings.filterwarnings("ignore")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

CARTELLA_CACHE = "cache_prezzi"
# ETF settoriali USA (storia dal dicembre 1998): usati per riconoscere il settore e come proxy
ETF_SETTORE = {"XLK": "tech", "XLF": "finanza", "XLV": "altro", "XLE": "altro", "XLI": "altro",
               "XLP": "altro", "XLU": "altro", "XLB": "altro", "XLY": "altro"}
SETTORE_YAHOO = {"Technology": ("tech", "XLK"), "Communication Services": ("tech", "XLK"),
                 "Financial Services": ("finanza", "XLF"), "Real Estate": ("finanza", "XLF"),
                 "Healthcare": ("altro", "XLV"), "Energy": ("altro", "XLE"), "Industrials": ("altro", "XLI"),
                 "Consumer Defensive": ("altro", "XLP"), "Utilities": ("altro", "XLU"),
                 "Basic Materials": ("altro", "XLB"), "Consumer Cyclical": ("altro", "XLY")}
VALUTE_MINORI = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}


class ErroreDati(Exception):
    """Problema sui dati (ticker inesistente, connessione assente...), con messaggio chiaro."""


# ------------------------------------------------------------------ download
def scarica_yahoo(ticker):
    """Prezzi 'adjusted close' (dividendi inclusi) e metadati di un ticker da Yahoo Finance."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    try:
        h = tk.history(period="max", auto_adjust=False, actions=False)
    except Exception as e:
        raise ErroreDati(f"Non riesco a scaricare «{ticker}» da Yahoo Finance ({e}). Controlla la connessione a internet.")
    if h is None or h.empty or "Adj Close" not in h:
        return pd.Series(dtype=float), {}
    s = h["Adj Close"].dropna()
    s = s[s > 0]
    idx = s.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = pd.DatetimeIndex(idx).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    md = tk.history_metadata or {}
    return s, {"valuta": md.get("currency"), "tipo": md.get("instrumentType"),
               "nome": md.get("longName") or md.get("shortName")}


def settore_yahoo(ticker):
    """Settore secondo Yahoo (può non essere disponibile: in quel caso None)."""
    try:
        import yfinance as yf
        return (yf.Ticker(ticker).info or {}).get("sector")
    except Exception:
        return None


def scarica_fred_usd():
    """Cambio USD per 1 EUR dalla FRED (dal 1999), usato prima dei dati Yahoo (2003)."""
    raw = urllib.request.urlopen("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSEU", timeout=60).read()
    f = pd.read_csv(io.BytesIO(raw), index_col=0, parse_dates=True).iloc[:, 0]
    return pd.to_numeric(f, errors="coerce").dropna()


class Archivio:
    """Cache su disco dei prezzi. Con aggiorna=True ogni ticker viene riscaricato (una volta per esecuzione)."""

    def __init__(self, cartella=CARTELLA_CACHE, aggiorna=False, log=print, scaricatore=None):
        self.dir, self.aggiorna, self.log = cartella, aggiorna, log
        self.scarica = scaricatore or scarica_yahoo
        self.in_rete = scaricatore is None  # con un downloader di prova (test) niente accessi a internet
        self.fatti, self.memoria = set(), {}
        os.makedirs(cartella, exist_ok=True)

    def _base(self, t):
        return os.path.join(self.dir, re.sub(r"[^A-Za-z0-9._-]", "_", t))

    def _da_scaricare(self, t, f):
        return not os.path.exists(f) or (self.aggiorna and t not in self.fatti)

    def prezzi(self, t):
        if t in self.memoria:
            return self.memoria[t]
        base = self._base(t)
        if self._da_scaricare(t, base + ".csv"):
            self.log(f"  scarico {t} ...")
            s, meta = self.scarica(t)
            if s is None or len(s) == 0:
                raise ErroreDati(f"Il ticker «{t}» non esiste su Yahoo Finance o non ha dati. "
                                 "Scrivilo come compare su finance.yahoo.com (es. AAPL, ENI.MI, SAP.DE, IWDA.AS).")
            s.rename("prezzo").to_csv(base + ".csv", index_label="Date")
            vecchio = self._meta(t)
            if "settore" in vecchio and not self.aggiorna:
                meta["settore"] = vecchio["settore"]
            json.dump(meta, open(base + ".json", "w"))
            self.fatti.add(t)
        s = pd.read_csv(base + ".csv", index_col=0, parse_dates=True).iloc[:, 0]
        self.memoria[t] = (s, self._meta(t))
        return self.memoria[t]

    def _meta(self, t):
        f = self._base(t) + ".json"
        return json.load(open(f)) if os.path.exists(f) else {}

    def settore(self, t):
        meta = self._meta(t)
        if "settore" not in meta:
            meta["settore"] = settore_yahoo(t) if self.in_rete else None
            json.dump(meta, open(self._base(t) + ".json", "w"))
        return meta["settore"]

    def fred(self):
        f = os.path.join(self.dir, "FRED_DEXUSEU.csv")
        if not self.in_rete:
            return pd.Series(dtype=float)
        if self._da_scaricare("FRED", f):
            try:
                self.log("  scarico il cambio storico EUR/USD (FRED) ...")
                scarica_fred_usd().rename("usd_per_eur").to_csv(f, index_label="Date")
                self.fatti.add("FRED")
            except Exception:
                if not os.path.exists(f):
                    return pd.Series(dtype=float)
        return pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]


# ------------------------------------------------------------------ conversione in EUR
def cambio(arch, valuta):
    """Unità di `valuta` per 1 EUR (serie giornaliera)."""
    fx, _ = arch.prezzi(f"EUR{valuta}=X")
    if valuta == "USD":
        fred = arch.fred()
        if len(fred):
            fx = pd.concat([fred[fred.index < fx.index[0]], fx]).sort_index()
    return fx[~fx.index.duplicated()]


def serie_eur(arch, t, valuta_default=None, avvisi=None):
    s, meta = arch.prezzi(t)
    valuta = meta.get("valuta") or valuta_default
    if valuta is None:
        valuta = "EUR"
        if avvisi is not None:
            avvisi.append(f"{t}: Yahoo non indica la valuta, la considero EUR.")
    valuta, divisore = VALUTE_MINORI.get(valuta, (valuta, 1))
    s = s / divisore
    if valuta != "EUR":
        fx = cambio(arch, valuta)
        fx = fx.reindex(fx.index.union(s.index)).ffill().reindex(s.index)
        prima = s.index[0]
        s = (s / fx).dropna()
        if len(s) and avvisi is not None and (s.index[0] - prima).days > 365 and s.index[0] > pd.Timestamp("2000-01-01"):
            avvisi.append(f"{t}: il cambio {valuta}/EUR è disponibile solo dal {s.index[0]:%d/%m/%Y}; i dati precedenti non sono usati.")
    if len(s) == 0:
        raise ErroreDati(f"«{t}»: nessun dato utilizzabile dopo la conversione in EUR.")
    return s, {**meta, "valuta": valuta}


def _allinea(s, calendario, limite=10):
    """Porta una serie di prezzi sul calendario comune (riempie al massimo `limite` giorni di borsa chiusa)."""
    x = s.reindex(s.index.union(calendario)).ffill(limit=limite).reindex(calendario)
    return x.where((x.index >= s.index[0]) & (x.index <= s.index[-1] + pd.Timedelta(days=15)))


def calendario_comune(serie):
    """Giorni in cui almeno metà dei titoli già quotati ha scambiato (evita festività di singole borse)."""
    unione = sorted(set().union(*[s.index for s in serie.values()]))
    idx = pd.DatetimeIndex(unione)
    oss = pd.DataFrame({t: idx.isin(s.index) for t, s in serie.items()}, index=idx)
    vivi = pd.DataFrame({t: (idx >= s.index[0]) & (idx <= s.index[-1]) for t, s in serie.items()}, index=idx)
    quota = oss.sum(1) / vivi.sum(1).clip(lower=1)
    return idx[(quota >= 0.5) & (idx.dayofweek < 5)]


# ------------------------------------------------------------------ costruzione dataset
def costruisci(cfg, arch):
    """Rendimenti giornalieri in EUR di tutti i titoli (NaN prima della quotazione) e del benchmark.
    Ritorna dict con R, info sui titoli, avvisi, movimenti estremi."""
    avvisi = []
    titoli = sorted({t for comp in cfg["composizione"].values() for t in comp if t != BENCH})
    b = cfg["benchmark"]
    eur, info = {}, {}
    for t in titoli:
        eur[t], info[t] = serie_eur(arch, t, avvisi=avvisi)
    etf, info_b = serie_eur(arch, b["ticker"], avvisi=avvisi)
    proxy = None
    if b.get("proxy_storico"):
        proxy, _ = serie_eur(arch, b["proxy_storico"], valuta_default="USD", avvisi=avvisi)
    cal = calendario_comune(eur if eur else {b["ticker"]: etf})
    inizio_cal = min(min(s.index[0] for s in eur.values()) if eur else etf.index[0],
                     proxy.index[0] if proxy is not None else etf.index[0])
    # il calendario parte dal primo dato disponibile; prima del primo titolo uso i giorni del benchmark
    extra = (proxy if proxy is not None else etf).index
    cal = cal.union(extra[(extra >= inizio_cal) & (extra < cal[0])])
    prezzi = pd.DataFrame({t: _allinea(s, cal) for t, s in eur.items()}, index=cal)
    R = prezzi.pct_change(fill_method=None)
    # benchmark: ETF reale quando esiste, prima l'indice (proxy) meno il TER
    r_etf = _allinea(etf, cal).pct_change(fill_method=None)
    if proxy is not None:
        r_idx = _allinea(proxy, cal).pct_change(fill_method=None) - b["ter"] / 252
        R[BENCH] = r_etf.where(cal >= etf.index[0] + pd.Timedelta(days=1), r_idx)
    else:
        R[BENCH] = r_etf
    R = R.iloc[1:]
    R = R[R[BENCH].notna() | R.drop(columns=BENCH).notna().any(axis=1)]

    righe, estremi = [], []
    for t in titoli + [BENCH]:
        s = R[t].dropna()
        if t == BENCH:
            nome, primo = b["ticker"], etf.index[0]
            m = info_b
        else:
            nome, primo, m = t, s.index[0], info[t]
        anni = (s.index[-1] - primo).days / 365.25
        righe.append({"ticker": nome, "nome": m.get("nome") or "", "valuta": m.get("valuta"), "tipo": m.get("tipo") or "",
                      "primo dato": primo.date(), "anni di storia": round(anni, 1)})
        if anni < 3:
            avvisi.append(f"{nome}: solo {anni:.1f} anni di storia. I risultati che lo riguardano sono poco affidabili.")
        for d, v in s[s.abs() > 0.30].items():
            estremi.append(f"{nome}: {v:+.0%} il {d:%d/%m/%Y}")
    return {"R": R, "info": pd.DataFrame(righe).set_index("ticker"), "avvisi": avvisi, "estremi": estremi,
            "ultimo_dato": R.index[-1], "calendario": cal}


def settimanali(r):
    return (1 + r).resample("W-FRI").prod(min_count=1) - 1


def classifica(cfg, dati, arch, log=print, serve_proxy=False):
    """Per ogni titolo: categoria per gli stress test (tech/finanza/altro) e proxy per l'analisi C.
    Ordine: indicazione in configurazione -> settore Yahoo -> ETF di settore più correlato."""
    R = dati["R"]
    titoli = [t for t in R.columns if t != BENCH]
    serve_corr = [t for t in titoli if t not in cfg["settori"] or (serve_proxy and t not in cfg["proxy"])]
    etf_r = {}
    if serve_corr:
        cal = R.index
        for e in ETF_SETTORE:
            try:
                s, _ = serie_eur(arch, e, valuta_default="USD")
                etf_r[e] = _allinea(s, cal).pct_change(fill_method=None)
            except ErroreDati:
                pass
    W = settimanali(pd.DataFrame({**etf_r, BENCH: R[BENCH]}))
    out = {}
    for t in titoli:
        cat, prox, fonte = None, None, ""
        if t not in serve_corr:
            out[t] = {"categoria": cfg["settori"][t], "proxy": cfg["proxy"].get(t, BENCH), "fonte": "indicato in configurazione"}
            continue
        sett = arch.settore(t) if t not in cfg["settori"] else None
        if sett in SETTORE_YAHOO:
            cat, prox = SETTORE_YAHOO[sett]
            fonte = f"settore Yahoo: {sett}"
        if cat is None or prox is None:
            w = settimanali(R[t]).dropna()
            cor = W.loc[w.index].corrwith(w).dropna() if len(w) >= 52 else pd.Series(dtype=float)
            if len(cor):
                best = cor.idxmax()
                prox = prox or best
                cat = cat or ETF_SETTORE.get(best, "altro")
                fonte = fonte or f"più correlato con {best if best != BENCH else 'il benchmark'} ({cor.max():.2f})"
            else:
                cat, prox, fonte = cat or "altro", prox or BENCH, fonte or "storia troppo breve: uso il benchmark"
        if t in cfg["settori"]:
            cat, fonte = cfg["settori"][t], "indicato in configurazione"
        if t in cfg["proxy"]:
            prox = cfg["proxy"][t]
        out[t] = {"categoria": cat, "proxy": prox, "fonte": fonte}
    out[BENCH] = {"categoria": "mercato", "proxy": None, "fonte": "benchmark"}
    return out, etf_r


def rendimenti_proxy(arch, R, ticker_proxy):
    """Rendimenti EUR di un proxy sul calendario di R (anche se non è un ETF di settore)."""
    if ticker_proxy == BENCH:
        return R[BENCH]
    s, _ = serie_eur(arch, ticker_proxy, valuta_default="USD")
    return _allinea(s, R.index).pct_change(fill_method=None)
