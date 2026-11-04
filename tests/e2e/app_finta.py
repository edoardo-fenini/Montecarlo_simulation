"""Avvia l'app vera (app.py) con una finta rete: prezzi sintetici e finte risposte di OpenFIGI/Yahoo. Così la prova nel browser
non dipende da internet. Uso: streamlit run tests/e2e/app_finta.py (dalla cartella di lavoro che contiene configurazioni/)."""

import datetime
import json
import pathlib
import runpy
import sys
import zlib

import numpy as np
import pandas as pd

RADICE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
import fonti  # noqa: E402
import isin  # noqa: E402
import ricerca  # noqa: E402

NOME_ETF = "iShares Core MSCI World UCITS ETF"
FIGI = json.dumps(
    {
        "IE00B4L5Y983": [("SWDA", "IM"), ("EUNL", "GY"), ("IWDA", "NA")],
        "US0378331005": [("AAPL", "UW")],
    }
)


def finto_scarica(t):
    if t.startswith("ZZZ"):
        return pd.Series(dtype=float), {}
    idx = pd.bdate_range(end=datetime.date.today(), periods=1300)
    r = np.random.default_rng(zlib.crc32(t.encode())).normal(0.0003, 0.01, len(idx))
    s = pd.Series(100 * np.cumprod(1 + r), index=idx)
    if t.startswith("EUR") and t.endswith("=X"):
        s = pd.Series(1.1, index=idx)
    valuta = t[3:6] if t.startswith("EUR") and t.endswith("=X") else ("EUR" if "." in t else "USD")
    return s, {"valuta": valuta, "tipo": "EQUITY", "nome": f"Societa {t}", "borsa": "Prova", "fonte": "Finto Yahoo"}


def finto_http(url, dati=None, intestazioni=None, timeout=0):
    isin_ = json.loads(dati)[0]["idValue"]
    noti = json.loads(FIGI)
    voci = noti.get(isin_, [(isin_[2:6], "IM"), (isin_[2:6], "GY")])  # ISIN qualsiasi: due quotazioni inventate
    nome = "APPLE INC" if isin_ == "US0378331005" else NOME_ETF.upper() if isin_ in noti else f"NOME {isin_[2:6]}"
    return json.dumps([{"data": [{"ticker": t, "exchCode": e, "name": nome} for t, e in voci]}]).encode()


def finto_ispettore(t, http=None, ispettore=None):
    apple = t == "AAPL"
    if not apple and t.split(".")[0] not in ("SWDA", "EUNL", "IWDA"):
        nome = f"Nome {t.split('.')[0]}"
        return {"valuta": "EUR", "borsa": t, "nome": nome, "tipo": "EQUITY", "primo": 9e8, "volume": 1e5, "ultimo": datetime.date.today().isoformat()}
    return {
        "valuta": "USD" if apple else "EUR",
        "borsa": "NasdaqGS" if apple else t,
        "nome": "Apple Inc." if apple else NOME_ETF,
        "tipo": "EQUITY" if apple else "ETF",
        "primo": 1.25e9,
        "volume": 1e5,
        "ultimo": datetime.date.today().isoformat(),
    }


def finta_ricerca(testo):
    """Ricerca per nome finta: due quotazioni dell'azienda cercata e un ETF."""
    base = testo.strip().split()[0].upper()[:4]
    return [
        {"symbol": f"{base}.MI", "longname": f"{testo.title()} S.p.A.", "exchDisp": "Milan", "quoteType": "EQUITY"},
        {"symbol": f"{base}.DE", "longname": f"{testo.title()} S.p.A.", "exchDisp": "XETRA", "quoteType": "EQUITY"},
        {"symbol": f"{base}X.MI", "longname": f"{testo.title()} UCITS ETF", "exchDisp": "Milan", "quoteType": "ETF"},
    ]


fonti.scarica_con_ripiego = finto_scarica
ricerca._ricerca_yahoo = finta_ricerca
isin._http = finto_http
isin.ispeziona_ticker = finto_ispettore

runpy.run_path(str(RADICE / "app.py"), run_name="__main__")
