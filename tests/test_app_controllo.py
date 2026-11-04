"""App: pulsante «Controlla i dati», riepilogo, blocco di «Avvia simulazione» con un rosso, ISIN e menu delle quotazioni (dati finti)."""

import datetime
import json
import os
import pathlib
import sys
import zlib

import numpy as np
import pandas as pd
import pytest

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from streamlit.testing.v1 import AppTest  # noqa: E402

import fonti  # noqa: E402
import isin  # noqa: E402

ISIN = "IE00B4L5Y983"
FIGI = json.dumps(
    [
        {
            "data": [
                {"ticker": "SWDA", "exchCode": "IM", "name": "X"},
                {"ticker": "EUNL", "exchCode": "GY", "name": "X"},
                {"ticker": "IWDA", "exchCode": "NA", "name": "X"},
            ]
        }
    ]
).encode()


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


def scheda(t):
    return {
        "valuta": "EUR",
        "borsa": t,
        "nome": "iShares Core MSCI World",
        "tipo": "ETF",
        "primo": 1.25e9,
        "volume": 1e5,
        "ultimo": datetime.date.today().isoformat(),
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    os.symlink(RADICE / "configurazioni", tmp_path / "configurazioni")
    monkeypatch.chdir(tmp_path)  # cache e report in una cartella temporanea
    monkeypatch.setattr(fonti, "scarica_con_ripiego", finto_scarica)
    monkeypatch.setattr(isin, "_http", lambda url, dati=None, intestazioni=None, timeout=0: FIGI)
    monkeypatch.setattr(isin, "ispeziona_ticker", lambda t, http=None, ispettore=None: scheda(t))
    return AppTest.from_file(str(RADICE / "app.py"), default_timeout=120).run()


def bottone(at, parte):
    return next(b for b in at.button if parte in b.label)


def con_tabella(at, righe):
    at.session_state["tabella"] = pd.DataFrame(righe, columns=["Portafoglio", "Ticker", "Peso (%)"])
    at.session_state["versione"] += 1
    return at.run()


def test_controlla_i_dati_tutto_verde_e_avvia_attivo(app):
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ENEL.MI", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    e = app.session_state["controllo"]["esito"]
    assert e["riepilogo"].startswith("3 titoli trovati") and not e["blocca"]  # AAPL, ENEL.MI + benchmark
    assert not bottone(app, "Avvia simulazione").disabled


def test_un_rosso_disattiva_avvia_simulazione_e_spiega(app):
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ZZZ.MI", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    assert app.session_state["controllo"]["esito"]["blocca"]
    assert bottone(app, "Avvia simulazione").disabled
    testi = " ".join(x.value for x in app.error)
    assert "ZZZ.MI" in testi and "Correggi" in testi
    # togliendo il titolo sbagliato e ricontrollando il pulsante torna attivo
    app = con_tabella(app, [["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not bottone(app, "Avvia simulazione").disabled


def test_isin_nel_controllo_con_menu_delle_quotazioni(app):
    app = con_tabella(app, [["P", ISIN, None], ["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    riga = next(r for r in app.session_state["controllo"]["esito"]["righe"] if r["input"] == ISIN)
    assert riga["isin"] == ISIN and riga["ticker"] == "SWDA.MI"
    menu = app.selectbox(key=f"quot_{ISIN}")
    etichette = {o.split(" · ")[0]: o for o in menu.options}  # il menu mostra «ticker · borsa · valuta · storia · volumi»
    assert menu.value == "SWDA.MI" and set(etichette) == {"SWDA.MI", "EUNL.DE", "IWDA.AS"}
    menu.select("IWDA.AS").run()  # altra quotazione: il controllo si rifa da solo
    assert not app.exception
    assert app.session_state["scelte_isin"] == {ISIN: "IWDA.AS"}
    riga = next(r for r in app.session_state["controllo"]["esito"]["righe"] if r["input"] == ISIN)
    assert riga["ticker"] == "IWDA.AS" and riga["risoluzione"]["scelta_utente"]


def test_isin_con_cifra_errata_blocca(app):
    app = con_tabella(app, [["P", "IE00B4L5Y984", None], ["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert bottone(app, "Avvia simulazione").disabled
    assert "cifra di controllo" in " ".join(x.value for x in app.error)
