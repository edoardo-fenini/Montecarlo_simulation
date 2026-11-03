"""Fonti dei prezzi: più fonti gratuite senza chiave API, tentativi ripetuti con attesa crescente, CSV manuali.

Ordine per i titoli:  1) Yahoo Finance tramite yfinance  2) Yahoo Finance, API diretta (senza yfinance)  3) Stooq
Ordine per i cambi EURxxx=X:  le stesse, più la Banca Centrale Europea (tassi di riferimento, dal 1999).
"""

from __future__ import annotations

import io
import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

log = logging.getLogger("confronta")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

TIMEOUT = 25  # secondi per ogni richiesta
TENTATIVI = 3  # tentativi per fonte in caso di errore di rete
ATTESA_INIZIALE = 1.5  # secondi; raddoppia a ogni tentativo (1,5 – 3 – 6)
AGENTE = "confronta-portafogli/1.1 (strumento personale di analisi; python-urllib)"

# suffisso Yahoo -> (suffisso Stooq, valuta dei prezzi Stooq)
STOOQ = {"": (".us", "USD"), ".DE": (".de", "EUR"), ".F": (".de", "EUR"), ".L": (".uk", "GBp"), ".T": (".jp", "JPY"), ".HK": (".hk", "HKD")}


class ErroreRete(Exception):
    """Errore temporaneo (connessione assente, timeout, troppe richieste): ha senso riprovare o usare la cache."""


def vuota():
    return pd.Series(dtype=float), {}


def _pulisci(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s > 0]
    idx = s.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = pd.DatetimeIndex(idx).normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _contesto_ssl():
    """Certificati di certifi: il Python installato da uv/python.org sul Mac a volte non trova quelli di sistema
    (errore CERTIFICATE_VERIFY_FAILED, visto sul Mac di GitHub Actions con la BCE e la FRED)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _scarica_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_contesto_ssl()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (404, 400):
            return b""  # risorsa inesistente: non è un problema di rete
        raise ErroreRete(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise ErroreRete(str(e)) from e


def con_tentativi(funzione, *args, tentativi: int = TENTATIVI, attesa: float = ATTESA_INIZIALE):
    """Ripete `funzione` in caso di ErroreRete, con attesa crescente. Solleva l'ultimo ErroreRete."""
    for i in range(tentativi):
        try:
            return funzione(*args)
        except ErroreRete:
            if i == tentativi - 1:
                raise
            time.sleep(attesa * 2**i)


# ------------------------------------------------------------------ fonti
def yahoo_yfinance(ticker: str):
    """Adjusted close (dividendi inclusi) tramite la libreria yfinance."""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    try:
        h = tk.history(period="max", auto_adjust=False, actions=False, timeout=TIMEOUT)
    except Exception as e:  # la libreria solleva molti tipi diversi
        raise ErroreRete(str(e)) from e
    if h is None or h.empty or "Adj Close" not in h:
        return vuota()
    md = tk.history_metadata or {}
    return _pulisci(h["Adj Close"]), {
        "valuta": md.get("currency"),
        "tipo": md.get("instrumentType"),
        "nome": md.get("longName") or md.get("shortName"),
        "borsa": md.get("fullExchangeName") or md.get("exchangeName"),
    }


def yahoo_diretto(ticker: str):
    """Stessi dati di Yahoo, chiesti direttamente all'API dei grafici (utile quando yfinance smette di funzionare)."""
    # con range=max Yahoo restituisce dati mensili: servono le date esplicite per avere i prezzi giornalieri
    url = (
        "https://query2.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(ticker)
        + f"?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit&includeAdjustedClose=true"
    )
    raw = _scarica_url(url)
    if not raw:
        return vuota()
    try:
        r = json.loads(raw)["chart"]["result"][0]
    except (KeyError, IndexError, TypeError, ValueError):
        return vuota()
    ts = r.get("timestamp") or []
    ind = r.get("indicators", {})
    serie = (ind.get("adjclose") or [{}])[0].get("adjclose") or (ind.get("quote") or [{}])[0].get("close")
    if not ts or not serie:
        return vuota()
    md = r.get("meta", {})
    date = pd.to_datetime(pd.Series(ts) + int(md.get("gmtoffset") or 0), unit="s")
    s = _pulisci(pd.Series(serie, index=date))
    if len(s) > 20 and s.index.to_series().diff().dt.days.median() > 4:
        log.warning("%s: Yahoo diretto ha restituito dati non giornalieri, li scarto", ticker)
        return vuota()
    return s, {
        "valuta": md.get("currency"),
        "tipo": md.get("instrumentType"),
        "nome": md.get("longName") or md.get("shortName"),
        "borsa": md.get("fullExchangeName") or md.get("exchangeName"),
    }


def simbolo_stooq(ticker: str):
    """Ticker Yahoo -> (simbolo Stooq, valuta) oppure None se la borsa non è coperta."""
    t = ticker.upper()
    if t.startswith("EUR") and t.endswith("=X") and len(t) == 8:
        return t[:6].lower(), t[3:6]
    if t.startswith("^"):
        return None
    base, punto, suff = t.rpartition(".")
    if not punto:
        base, suff = t, ""
    else:
        suff = "." + suff
    if suff not in STOOQ:
        return None
    s, valuta = STOOQ[suff]
    return base.lower().replace("-", ".") + s, valuta


def stooq(ticker: str):
    """Prezzi di chiusura da Stooq (corretti per gli split ma SENZA dividendi reinvestiti)."""
    sv = simbolo_stooq(ticker)
    if sv is None:
        return vuota()
    raw = _scarica_url(f"https://stooq.com/q/d/l/?s={sv[0]}&i=d")
    if not raw or b"Date" not in raw[:50]:
        return vuota()
    df = pd.read_csv(io.BytesIO(raw), index_col="Date", parse_dates=True)
    if "Close" not in df or df.empty:
        return vuota()
    return _pulisci(df["Close"]), {
        "valuta": sv[1],
        "tipo": "CURRENCY" if ticker.endswith("=X") else None,
        "nome": None,
        "borsa": "Stooq",
        "nota": "prezzi senza dividendi",
    }


def bce(ticker: str):
    """Cambi di riferimento della Banca Centrale Europea: unità di valuta per 1 euro, dal 1999."""
    t = ticker.upper()
    if not (t.startswith("EUR") and t.endswith("=X") and len(t) == 8):
        return vuota()
    raw = _scarica_url(f"https://data-api.ecb.europa.eu/service/data/EXR/D.{t[3:6]}.EUR.SP00.A?format=csvdata")
    if not raw:
        return vuota()
    df = pd.read_csv(io.BytesIO(raw))
    if "TIME_PERIOD" not in df or "OBS_VALUE" not in df:
        return vuota()
    s = pd.Series(df["OBS_VALUE"].values, index=pd.to_datetime(df["TIME_PERIOD"]))
    return _pulisci(s), {"valuta": t[3:6], "tipo": "CURRENCY", "nome": f"Cambio BCE EUR/{t[3:6]}", "borsa": "BCE"}


FONTI_TITOLI = [("Yahoo Finance", yahoo_yfinance), ("Yahoo Finance (API diretta)", yahoo_diretto), ("Stooq", stooq)]
FONTI_CAMBI = FONTI_TITOLI[:2] + [("Banca Centrale Europea", bce), ("Stooq", stooq)]


def scarica_con_ripiego(ticker: str, fonti=None):
    """Prova le fonti in ordine. Ritorna (serie, metadati con 'fonte') oppure una serie vuota se nessuna fonte
    conosce il ticker. Solleva ErroreRete solo se TUTTE le fonti hanno avuto problemi di rete."""
    if fonti is None:
        fonti = FONTI_CAMBI if ticker.upper().endswith("=X") else FONTI_TITOLI
    errori = []
    for nome, f in fonti:
        try:
            s, meta = con_tentativi(f, ticker)
        except ErroreRete as e:
            log.warning("%s: %s non risponde (%s)", ticker, nome, e)
            errori.append(f"{nome}: {e}")
            continue
        except Exception as e:  # una fonte che cambia formato non deve fermare le altre
            log.warning("%s: errore inatteso da %s (%s)", ticker, nome, e)
            errori.append(f"{nome}: {e}")
            continue
        if len(s):
            meta["fonte"] = nome
            if errori:
                log.info("%s: scaricato da %s dopo problemi con %s", ticker, nome, "; ".join(errori))
            return s, meta
    if errori and len(errori) == len(fonti):
        raise ErroreRete("; ".join(errori))
    return vuota()


# ------------------------------------------------------------------ CSV manuali
def leggi_csv_prezzi(contenuto: bytes) -> pd.Series:
    """Legge un CSV di prezzi scaricato a mano. Formato: una colonna con la data e una con il prezzo.
    Accetta separatore virgola o punto e virgola, decimali con punto o virgola, date AAAA-MM-GG o GG/MM/AAAA.
    Nomi di colonna riconosciuti: Date/Data e Adj Close/Close/Prezzo/Chiusura (altrimenti la prima e l'ultima colonna)."""
    testo = contenuto.decode("utf-8-sig", errors="replace")
    righe = [r for r in testo.splitlines() if r.strip() and not r.lstrip().startswith("#")]
    if len(righe) < 2:
        raise ValueError("il file è vuoto o ha una sola riga")
    sep = ";" if righe[0].count(";") >= righe[0].count(",") and ";" in righe[0] else ","
    df = pd.read_csv(io.StringIO("\n".join(righe)), sep=sep, dtype=str)
    cols = {c.strip().lower(): c for c in df.columns}
    c_data = next((cols[k] for k in ("date", "data", "giorno") if k in cols), df.columns[0])
    c_prezzo = next((cols[k] for k in ("adj close", "adj_close", "prezzo", "close", "chiusura", "price") if k in cols), df.columns[-1])
    valori = df[c_prezzo].astype(str).str.strip().str.replace("€", "", regex=False).str.replace(" ", "", regex=False)
    if valori.str.contains(",", regex=False).any():  # decimali con la virgola (eventuali punti = migliaia)
        valori = valori.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    date_testo = df[c_data].astype(str).str.strip()
    giorno_prima = date_testo.str.match(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}$").all()
    date = pd.to_datetime(date_testo, dayfirst=bool(giorno_prima), errors="coerce")
    s = _pulisci(pd.Series(pd.to_numeric(valori, errors="coerce").values, index=date)).loc[lambda x: x.index.notna()]
    if len(s) < 30:
        raise ValueError(f"servono almeno 30 prezzi validi, ne ho trovati {len(s)}: controlla le colonne data e prezzo")
    return s
