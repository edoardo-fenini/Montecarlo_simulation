"""v1.3 – ricerca di titoli per nome (risposte di Yahoo simulate, senza internet) e aggiunta al portafoglio nell'app."""

import pytest

import fonti
import ricerca as R

QUOTES = [
    {"symbol": "ENEL.MI", "longname": "Enel S.p.A.", "exchDisp": "Milan", "quoteType": "EQUITY"},
    {"symbol": "ENLAY", "shortname": "ENEL SPA ADR", "exchDisp": "OTC Markets", "quoteType": "EQUITY"},
    {"symbol": "ENL.DE", "longname": "Enel S.p.A.", "exchDisp": "XETRA", "quoteType": "EQUITY"},
    {"symbol": "ENEL.MI", "longname": "doppione", "quoteType": "EQUITY"},
    {"symbol": "EURUSD=X", "shortname": "EUR/USD", "quoteType": "CURRENCY"},
    {"symbol": "ENELF", "shortname": "Enel future", "quoteType": "FUTURE"},
] + [{"symbol": f"ETF{i}.MI", "longname": f"Enel ETF {i}", "exchDisp": "Milan", "quoteType": "ETF"} for i in range(15)]


def valute(t):
    return {"valuta": "USD" if "." not in t else "EUR", "borsa": "da ispettore"}


def test_al_massimo_dieci_risultati_solo_azioni_ed_etf_senza_doppioni():
    r = R.cerca("enel", ricerca=lambda q: QUOTES, ispettore=valute)
    assert len(r) == 10
    assert [x["ticker"] for x in r[:3]] == ["ENEL.MI", "ENLAY", "ENL.DE"]
    assert all(x["ticker"] not in ("EURUSD=X", "ENELF") for x in r)
    assert r[0] == {"nome": "Enel S.p.A.", "ticker": "ENEL.MI", "isin": "", "borsa": "Milan", "valuta": "EUR", "tipo": "Azione"}
    assert r[1]["nome"] == "ENEL SPA ADR" and r[1]["valuta"] == "USD"
    assert r[3]["tipo"] == "ETF"
    assert "Enel S.p.A. · ENEL.MI · Milan · EUR · Azione" == R.etichetta(r[0])


def test_ricerca_con_isin_riporta_l_isin():
    visti = []
    r = R.cerca(" it0003128367 ", ricerca=lambda q: visti.append(q) or QUOTES[:1], ispettore=valute)
    assert visti == ["IT0003128367"] and r[0]["isin"] == "IT0003128367" and "IT0003128367" in R.etichetta(r[0])


def test_errori_chiari():
    with pytest.raises(R.ErroreRicerca, match="almeno 2"):
        R.cerca("a")
    with pytest.raises(R.ErroreRicerca, match="cifra di controllo"):
        R.cerca("IT0003128368")

    def giu(q):
        raise ConnectionError("rete giù")

    with pytest.raises(R.ErroreRicerca, match="non risponde"):
        R.cerca("enel", ricerca=giu)


def test_senza_risultati_e_valuta_ignota_se_yahoo_non_risponde():
    assert R.cerca("zzzzzz", ricerca=lambda q: []) == []

    def ispettore_giu(t):
        raise fonti.ErroreRete("429")

    r = R.cerca("enel", ricerca=lambda q: QUOTES[:1], ispettore=ispettore_giu)
    assert r[0]["valuta"] == "" and "valuta ?" in R.etichetta(r[0])
