"""Correzione 1.3 (StreamlitDuplicateElementId): simulazione completa nell'app con TUTTI i moduli attivi, per l'esempio precaricato e
per l'esempio con ISIN, con dati finti brevi. Con la storia breve l'analisi B copre lo stesso periodo della A e i loro grafici sono
identici: nella 1.2 questo fermava l'app con StreamlitDuplicateElementId. Tutte le schede dei risultati vengono costruite."""

import datetime
import json
import pathlib
import shutil
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

MODULI = ("stress_test", "rischio_singolo_titolo", "verifica_convergenza", "confronto_modelli", "analisi_C")


def finto_scarica(t):
    idx = pd.bdate_range(end=datetime.date.today(), periods=1300)
    r = np.random.default_rng(zlib.crc32(t.encode())).normal(0.0003, 0.012, len(idx))
    s = pd.Series(100 * np.cumprod(1 + r), index=idx)
    if t.startswith("EUR") and t.endswith("=X"):
        s = pd.Series(1.1, index=idx)
    valuta = t[3:6] if t.startswith("EUR") and t.endswith("=X") else ("EUR" if "." in t else "USD")
    return s, {"valuta": valuta, "tipo": "EQUITY", "nome": f"Societa {t}", "borsa": "Prova", "fonte": "Finto"}


def finto_http(url, dati=None, intestazioni=None, timeout=0):
    i = json.loads(dati)[0]["idValue"]
    return json.dumps([{"data": [{"ticker": i[2:6], "exchCode": e, "name": f"NOME {i[2:6]}"} for e in ("IM", "GY")]}]).encode()


def finto_ispettore(t, http=None, ispettore=None):
    nome = f"Nome {t.split('.')[0]}"
    return {"valuta": "EUR", "borsa": t, "nome": nome, "tipo": "EQUITY", "primo": 9e8, "volume": 1e5, "ultimo": datetime.date.today().isoformat()}


@pytest.mark.parametrize("esempio", ["esempio_tre_portafogli.yaml", "esempio_isin.yaml"])
def test_simulazione_completa_tutti_i_moduli_senza_elementi_duplicati(tmp_path, monkeypatch, esempio):
    shutil.copytree(RADICE / "configurazioni", tmp_path / "configurazioni")
    shutil.copy(RADICE / "configurazioni" / esempio, tmp_path / "configurazioni/esempio_tre_portafogli.yaml")  # diventa il precaricato
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fonti, "scarica_con_ripiego", finto_scarica)
    monkeypatch.setattr(isin, "_http", finto_http)
    monkeypatch.setattr(isin, "ispeziona_ticker", finto_ispettore)
    at = AppTest.from_file(str(RADICE / "app.py"), default_timeout=900).run()
    at.session_state["nsim"] = 500
    for k in MODULI:
        at.session_state[f"mod_{k}"] = True
    at = at.run()
    at = next(b for b in at.button if "Avvia simulazione" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "ris" in at.session_state and not at.error
    ris = at.session_state["ris"]
    assert {"A", "B"} <= set(ris["sim"])  # il caso che faceva scattare l'errore: A e B con gli stessi grafici
    etichette = [t.label for t in at.tabs]
    for nome in ("In una pagina", "Sintesi", "Fan chart", "Drawdown", "Stress test", "Robustezza", "Analisi salvate"):
        assert any(nome in e for e in etichette), etichette
    # ogni grafico Plotly ha la sua key: fan chart e cali per A, B (e C se c'è)
    assert len(at.get("plotly_chart")) >= 4
    # un secondo giro (come quando si clicca su una scheda o si sposta un cursore) non deve rompersi
    at = at.run()
    assert not at.exception


def test_simulazione_completa_con_modello_a_fattori(tmp_path, monkeypatch):
    """v1.5: modello a fattori + scomposizione del rischio + backtest del VaR nell'app, senza errori Streamlit."""
    shutil.copytree(RADICE / "configurazioni", tmp_path / "configurazioni")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fonti, "scarica_con_ripiego", finto_scarica)
    monkeypatch.setattr(isin, "_http", finto_http)
    monkeypatch.setattr(isin, "ispeziona_ticker", finto_ispettore)
    at = AppTest.from_file(str(RADICE / "app.py"), default_timeout=900).run()
    at.session_state["nsim"] = 500
    at.session_state["modello"] = "fattori"
    at.session_state["mod_backtest_var"] = True
    at = at.run()
    at = next(b for b in at.button if "Avvia simulazione" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    ris = at.session_state["ris"]
    assert ris["modello_simulazione"] == "fattori" and ris.get("backtest") and ris["fattori"]["scomposizione"]
    etichette = [t.label for t in at.tabs]
    for nome in ("Da dove viene il rischio", "Validazione del modello"):
        assert any(nome in e for e in etichette), etichette
    at = at.run()
    assert not at.exception
