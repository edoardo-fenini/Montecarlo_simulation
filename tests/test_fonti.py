"""Fonti dei dati: tentativi ripetuti, fonti alternative, modalità offline, CSV manuali, verifica dei ticker (senza internet)."""

import copy
import os

import numpy as np
import pandas as pd
import pytest

import analisi
import configurazione as C
import dati as D
import fonti

QUI = os.path.dirname(os.path.abspath(__file__))
ESEMPIO_CSV = os.path.join(QUI, "..", "esempi", "prezzi_esempio.csv")


def serie(n=300, inizio="2020-01-01"):
    idx = pd.bdate_range(inizio, periods=n)
    return pd.Series(100 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, n)), index=idx)


def test_tentativi_con_attesa_crescente():
    chiamate = []

    def instabile(x):
        chiamate.append(x)
        if len(chiamate) < 3:
            raise fonti.ErroreRete("timeout")
        return "ok"

    assert fonti.con_tentativi(instabile, "AAPL", tentativi=3, attesa=0) == "ok" and len(chiamate) == 3
    chiamate.clear()
    with pytest.raises(fonti.ErroreRete):
        fonti.con_tentativi(lambda x: (_ for _ in ()).throw(fonti.ErroreRete("giù")), "X", tentativi=2, attesa=0)


def test_ripiego_sulla_seconda_fonte(monkeypatch):
    monkeypatch.setattr(fonti, "ATTESA_INIZIALE", 0)
    rotta = lambda t: (_ for _ in ()).throw(fonti.ErroreRete("429"))
    buona = lambda t: (serie(), {"valuta": "USD"})
    s, m = fonti.scarica_con_ripiego("AAPL", [("Prima", rotta), ("Seconda", buona)])
    assert len(s) == 300 and m["fonte"] == "Seconda"
    # tutte le fonti senza rete -> ErroreRete; tutte "non conosco il ticker" -> serie vuota
    with pytest.raises(fonti.ErroreRete):
        fonti.scarica_con_ripiego("AAPL", [("A", rotta), ("B", rotta)])
    s, m = fonti.scarica_con_ripiego("NONESISTE", [("A", lambda t: fonti.vuota()), ("B", lambda t: fonti.vuota())])
    assert len(s) == 0
    # una fonte che si rompe in modo inatteso non ferma le altre
    s, m = fonti.scarica_con_ripiego("AAPL", [("Rotta", lambda t: 1 / 0), ("Buona", buona)])
    assert m["fonte"] == "Buona"


def test_simboli_stooq():
    assert fonti.simbolo_stooq("AAPL") == ("aapl.us", "USD")
    assert fonti.simbolo_stooq("SAP.DE") == ("sap.de", "EUR")
    assert fonti.simbolo_stooq("HSBA.L") == ("hsba.uk", "GBp")
    assert fonti.simbolo_stooq("BRK-B") == ("brk.b.us", "USD")
    assert fonti.simbolo_stooq("EURUSD=X") == ("eurusd", "USD")
    assert fonti.simbolo_stooq("ENI.MI") is None and fonti.simbolo_stooq("^990100-USD-STRD") is None


def test_modalita_offline_usa_la_cache(tmp_path):
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=lambda t: (serie(), {"valuta": "EUR", "fonte": "Prova"}))
    s1, _ = arch.prezzi("AAA")
    offline = D.Archivio(
        str(tmp_path),
        aggiorna=True,
        log=lambda *a: None,
        scaricatore=lambda t: (_ for _ in ()).throw(fonti.ErroreRete("nessuna connessione")),
    )
    s2, m = offline.prezzi("AAA")
    assert s2.equals(s1)
    assert any("uso i prezzi salvati" in a and f"{s1.index[-1]:%d/%m/%Y}" in a for a in offline.avvisi)
    with pytest.raises(D.ErroreDati, match="Carica prezzi da file"):
        offline.prezzi("NUOVO")


def test_importa_csv_formati_diversi(tmp_path):
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=lambda t: (serie(), {"valuta": "USD"}))
    s = arch.importa_csv("esempio", open(ESEMPIO_CSV, "rb").read(), "EUR", nome="Titolo di esempio")
    assert len(s) > 1000 and s.index[0] == pd.Timestamp("2021-01-04") and s.iloc[0] > 40
    p, m = arch.prezzi("ESEMPIO")
    assert m["fonte"] == D.FONTE_MANUALE and m["valuta"] == "EUR" and len(p) == len(s)
    inglese = "Date,Open,High,Low,Close,Adj Close,Volume\n" + "\n".join(
        f"{d:%Y-%m-%d},1,1,1,{10 + i},{9.5 + i * 0.5},100" for i, d in enumerate(pd.bdate_range("2022-01-03", periods=40))
    )
    s = fonti.leggi_csv_prezzi(inglese.encode())
    assert s.iloc[0] == 9.5 and s.iloc[-1] == pytest.approx(9.5 + 39 * 0.5)  # usa Adj Close
    italiano = "data;prezzo\n" + "\n".join(f"{d:%d/%m/%Y};1.234,5{i % 10}" for i, d in enumerate(pd.bdate_range("2022-01-03", periods=40)))
    s = fonti.leggi_csv_prezzi(italiano.encode())
    assert s.iloc[0] == pytest.approx(1234.50) and s.index[1] == pd.Timestamp("2022-01-04")
    with pytest.raises(D.ErroreDati, match="almeno 30"):
        arch.importa_csv("POCHI", b"Date,Close\n2024-01-02,10\n2024-01-03,11\n", "EUR")


def test_prezzi_manuali_non_vengono_sovrascritti(tmp_path):
    arch = D.Archivio(
        str(tmp_path),
        aggiorna=True,
        log=lambda *a: None,
        scaricatore=lambda t: (_ for _ in ()).throw(AssertionError("non doveva scaricare")),
    )
    arch.importa_csv("MIO", open(ESEMPIO_CSV, "rb").read(), "EUR")
    s, m = arch.prezzi("MIO")
    assert m["fonte"] == D.FONTE_MANUALE


def test_verifica_ticker_e_fonte_nel_report(cfg_piccola, finto_yahoo, tmp_path):
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=finto_yahoo)
    v = D.verifica_ticker(arch, "AAA.MI")
    assert v["valuta"] == "EUR" and v["anni"] > 12 and v["dal"] == pd.Timestamp("2012-01-02").date()
    with pytest.raises(D.ErroreDati, match="NONESISTE"):
        D.verifica_ticker(arch, "NONESISTE")
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"].append({"nome": "Da file", "titoli": ["ESEMPIO", "AAA.MI"]})
    cfg["prezzi_da_file"] = {"esempio": {"file": ESEMPIO_CSV, "valuta": "EUR"}}
    cfg["settori"]["ESEMPIO"] = "altro"
    ris = analisi.esegui(C.prepara(cfg), cartella_cache=str(tmp_path), scaricatore=finto_yahoo, log=lambda *a: None, n=100)
    info = ris["dati_info"]
    assert info.loc["ESEMPIO", "fonte"] == D.FONTE_MANUALE
    assert info.loc["AAA.MI", "fonte"] == "dati di prova" and str(info.loc["AAA.MI", "ultimo dato"]) == "2024-12-31"
