"""v1.5.1, tappa 8: menu delle classi di quote dei fondi trovati per nome (nome, valuta, storia) e scelta salvata nella configurazione. Offline."""

import datetime
import json
import os
import pathlib
import sys

import pandas as pd
import pytest
from test_fondi_v14 import CANDIDATI, FONDO, OGGI, ricerca_fondi, voci

import fondi
import fonti
import isin

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_etichetta_classe_ha_nome_valuta_storia_e_differenze():
    ris = fondi.cerca_fondo(FONDO, "JPMIF US GROWTH-A USD CAP", ["JPMorgan Funds - US Growth Fund"], OGGI, ricerca_fondi, lambda t: CANDIDATI.get(t))
    righe = {q["ticker"]: fondi.etichetta_classe(q) for q in ris}
    assert righe["0P00000001"].startswith("JPM US Growth A acc USD · USD · 4,7 anni di storia · 0P00000001") and "⚠" not in righe["0P00000001"]
    assert "⚠" in righe["0P00000002"] and "distribuzione" in righe["0P00000002"]  # classe a distribuzione: differenza segnalata
    assert "classe I invece di A" in righe["0P00000004"]
    assert len(ris) == 4  # tutte le classi candidate restano nel menu, la migliore per prima


@pytest.fixture
def app(tmp_path, monkeypatch):
    os.symlink(RADICE / "configurazioni", tmp_path / "configurazioni")
    monkeypatch.chdir(tmp_path)

    def scarica(t):
        idx = pd.bdate_range(end=datetime.date.today(), periods=1300)
        s = pd.Series(100.0, index=idx)
        if t.startswith("EUR") and t.endswith("=X"):
            return s * 1.1, {"valuta": t[3:6], "tipo": "CURRENCY", "fonte": "Finto"}
        return s, {"valuta": "USD", "tipo": "MUTUALFUND" if t.startswith("0P") else "EQUITY", "nome": f"Nome {t}", "fonte": "Finto Yahoo"}

    def scheda(t, http=None, ispettore=None):
        c = CANDIDATI.get(t)
        if not c:
            return {"valuta": "EUR", "borsa": t, "nome": "Bench", "tipo": "ETF", "primo": 1.25e9, "volume": 1e5, "ultimo": datetime.date.today().isoformat()}
        spost = datetime.date.today() - OGGI  # le date dei candidati sono relative al 4/11/2026: si spostano a oggi (limite di 30 giorni sull'ultimo prezzo)
        return {**c, "primo": int(c["primo"] + spost.total_seconds()), "ultimo": (datetime.date.fromisoformat(c["ultimo"]) + spost).isoformat()}

    def figi(url, dati=None, intestazioni=None, timeout=0):
        d = voci("Open-End Fund", "Mutual Fund", "LX")
        d[0]["name"] = "JPMIF US GROWTH-A USD CAP"
        return json.dumps([{"data": d}]).encode()

    monkeypatch.setattr(fonti, "scarica_con_ripiego", scarica)
    monkeypatch.setattr(isin, "_http", figi)
    monkeypatch.setattr(isin, "ispeziona_ticker", scheda)
    monkeypatch.setattr(fondi, "_ricerca_yahoo", ricerca_fondi)
    monkeypatch.setattr(isin, "candidati_yahoo_ricerca", lambda i, ricerca=None: [])
    return AppTest.from_file(str(RADICE / "app.py"), default_timeout=120).run()


def test_menu_delle_classi_del_fondo_e_scelta_salvata_nella_configurazione(app):
    app.session_state["tabella"] = pd.DataFrame([["P", FONDO, None]], columns=["Portafoglio", "Ticker", "Peso (%)"])
    app.session_state["versione"] += 1
    app = app.run()
    next(b for b in app.button if "Controlla i dati" in b.label).click()
    app = app.run()
    assert not app.exception
    menu = app.selectbox(key=f"quot_{FONDO}")
    etichette = list(menu.options)
    assert len(etichette) == 4 and menu.value == "0P00000001"
    assert any(e.startswith("JPM US Growth A dist USD · USD · ") and "⚠" in e for e in etichette)  # nome, valuta, storia, differenza
    menu.select("0P00000002").run()
    assert not app.exception
    assert app.session_state["scelte_isin"] == {FONDO: "0P00000002"}  # salvata per la configurazione scaricabile
    riga = next(r for r in app.session_state["controllo"]["esito"]["righe"] if r["input"] == FONDO)
    assert riga["ticker"] == "0P00000002"
