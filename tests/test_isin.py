"""ISIN: riconoscimento, cifra di controllo, conversione in ticker (con risposte simulate, senza internet), scelta della quotazione."""

import datetime
import json

import pytest

import configurazione as C
import fonti
import isin

OGGI = datetime.date(2026, 11, 4)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(fonti.time, "sleep", lambda s: None)


# ------------------------------------------------------------------ riconoscimento e cifra di controllo
@pytest.mark.parametrize("codice", ["IE00B4L5Y983", "US0378331005", "IT0003128367", "DE000A0H0785", "LU0290358497", "FR0000120271"])
def test_isin_validi(codice):
    assert isin.cifra_controllo_ok(codice)
    assert isin.riconosci(codice) == ("isin", codice)


@pytest.mark.parametrize("codice", ["IE00B4L5Y984", "US0378331006", "IT0003128368", "IE00B4L5Y98"])
def test_cifra_di_controllo_sbagliata(codice):
    assert not isin.cifra_controllo_ok(codice)


def test_riconosci_normalizza_spazi_e_minuscole():
    assert isin.riconosci(" ie00 b4l5y983 ") == ("isin", "IE00B4L5Y983")


def test_riconosci_isin_con_cifra_errata_e_ticker():
    assert isin.riconosci("IE00B4L5Y984") == ("isin_errato", "IE00B4L5Y984")
    for t in ["AAPL", "IWDA.AS", "ENEL.MI", "BRK-B", "^GSPC", "EURUSD=X", "benchmark"]:
        assert isin.riconosci(t)[0] == "ticker"
    assert not isin.e_isin("AAPL") and isin.e_isin("US0378331005")


def test_risolvi_rifiuta_isin_errato_e_ticker(tmp_path):
    with pytest.raises(isin.ErroreIsin, match="cifra di controllo"):
        isin.risolvi("IE00B4L5Y984", str(tmp_path))
    with pytest.raises(isin.ErroreIsin, match="non è un ISIN"):
        isin.risolvi("AAPL", str(tmp_path))


# ------------------------------------------------------------------ risposte simulate
def figi(*voci):
    """Risposta OpenFIGI simulata: voci = (ticker, codice borsa)."""
    return json.dumps([{"data": [{"ticker": t, "exchCode": e, "name": "NOME " + t} for t, e in voci]}]).encode()


def scheda(valuta="EUR", borsa="Milan", storia_anni=10, volume=100000, ultimo="2026-11-03", nome="Nome vero"):
    primo = datetime.datetime.combine(OGGI - datetime.timedelta(days=int(storia_anni * 365.25)), datetime.time(), datetime.UTC)
    return {
        "valuta": valuta,
        "borsa": borsa,
        "nome": nome,
        "tipo": "ETF",
        "primo": int(primo.timestamp()),
        "volume": volume,
        "ultimo": ultimo,
    }


class Finto:
    """http / ispettore / ricerca finti che contano le chiamate."""

    def __init__(self, risposta_figi, schede, ricerca=None, errore_figi=False):
        self.risposta_figi, self.schede, self.ricerca_ris = risposta_figi, schede, ricerca or []
        self.errore_figi, self.chiamate_figi, self.chiamate_ricerca = errore_figi, 0, 0

    def http(self, url, dati=None, intestazioni=None):
        self.chiamate_figi += 1
        self.intestazioni = intestazioni
        if self.errore_figi:
            raise fonti.ErroreRete("HTTP 429")
        return self.risposta_figi

    def ispettore(self, ticker):
        return self.schede.get(ticker)

    def ricerca(self, q):
        self.chiamate_ricerca += 1
        return [{"symbol": s, "longname": "Nome " + s} for s in self.ricerca_ris]

    def kw(self):
        return {"http": self.http, "ispettore": self.ispettore, "ricerca": self.ricerca, "oggi": OGGI}


ETF = Finto(
    figi(("IWDA", "NA"), ("SWDA", "IM"), ("EUNL", "GY"), ("EUNL", "GR"), ("IWDA", "LN"), ("IWDA", "EO"), ("IWDAA", "IX")),
    {
        "IWDA.AS": scheda("EUR", "Amsterdam", 17, 90000),
        "SWDA.MI": scheda("EUR", "Milan", 17, 92000),
        "EUNL.DE": scheda("EUR", "XETRA", 17, 288000),
        "IWDA.L": scheda("USD", "LSE", 17, 565000),
    },
)


def test_openfigi_convertito_in_suffissi_yahoo():
    c = isin.candidati_openfigi("IE00B4L5Y983", http=ETF.http)
    # codici sconosciuti (EO, IX) scartati; GY e GR danno lo stesso ticker (un solo EUNL.DE)
    assert [x["ticker"] for x in c] == ["IWDA.AS", "SWDA.MI", "EUNL.DE", "IWDA.L"]


def test_openfigi_ticker_particolari():
    r = figi(("BRK/B", "UN"), ("BP/", "LN"), ("AAPL*", "MM"), ("A B", "FP"))
    c = isin.candidati_openfigi("US0846707026", http=lambda *a, **k: r)
    assert [x["ticker"] for x in c] == ["BRK-B", "BP.L", "AB.PA"]


def test_openfigi_chiave_opzionale():
    f = Finto(figi(("X", "IM")), {})
    isin.candidati_openfigi("IT0003128367", http=f.http)
    assert "X-OPENFIGI-APIKEY" not in f.intestazioni
    isin.candidati_openfigi("IT0003128367", http=f.http, chiave="abc")
    assert f.intestazioni["X-OPENFIGI-APIKEY"] == "abc"


def test_conversione_etf_default_preferisce_eur_poi_milano(tmp_path):
    r = isin.risolvi("IE00B4L5Y983", str(tmp_path), **ETF.kw())
    assert r["ticker"] == "SWDA.MI" and r["metodo"] == "OpenFIGI" and not r["scelta_utente"]
    # in ordine: EUR (.MI, .DE, .AS), poi le altre
    assert [q["ticker"] for q in r["quotazioni"]] == ["SWDA.MI", "EUNL.DE", "IWDA.AS", "IWDA.L"]
    assert r["quotazioni"][0]["storia_anni"] == pytest.approx(17, abs=0.2)


def test_regola_configurabile(tmp_path):
    kw = ETF.kw()
    assert isin.risolvi("IE00B4L5Y983", str(tmp_path), [".AS"], **kw)["ticker"] == "IWDA.AS"
    assert isin.risolvi("IE00B4L5Y983", str(tmp_path), [".DE", "EUR"], **kw)["ticker"] == "EUNL.DE"
    assert isin.risolvi("IE00B4L5Y983", str(tmp_path), ["USD"], **kw)["ticker"] == "IWDA.L"


def test_scelta_dell_utente(tmp_path):
    r = isin.risolvi("IE00B4L5Y983", str(tmp_path), scelta="eunl.de", **ETF.kw())
    assert r["ticker"] == "EUNL.DE" and r["scelta_utente"] and r["predefinito"] == "SWDA.MI"


def test_cache_conversione(tmp_path):
    f = Finto(ETF.risposta_figi, ETF.schede)
    r1 = isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())
    assert f.chiamate_figi == 1 and (tmp_path / "isin_ticker.json").exists()
    r2 = isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())
    assert f.chiamate_figi == 1 and r2["ticker"] == r1["ticker"] and r2["metodo"].startswith("cache")
    isin.risolvi("IE00B4L5Y983", str(tmp_path), aggiorna=True, **f.kw())
    assert f.chiamate_figi == 2
    # la regola si applica anche ai dati in cache, senza nuove richieste
    assert isin.risolvi("IE00B4L5Y983", str(tmp_path), [".AS"], **f.kw())["ticker"] == "IWDA.AS"
    assert f.chiamate_figi == 2


def test_riserva_ricerca_yahoo_se_openfigi_non_risponde(tmp_path):
    f = Finto(b"", {"IWDA.L": scheda("USD", "LSE")}, ricerca=["IWDA.L"], errore_figi=True)
    r = isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())
    assert r["ticker"] == "IWDA.L" and r["metodo"] == "Ricerca Yahoo Finance"
    assert f.chiamate_ricerca == 1


def test_riserva_ricerca_yahoo_se_openfigi_non_trova_ticker_esistenti(tmp_path):
    f = Finto(figi(("ZZZ", "IM")), {"IWDA.L": scheda("USD", "LSE")}, ricerca=["IWDA.L"])  # ZZZ.MI non esiste su Yahoo
    assert isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())["ticker"] == "IWDA.L"


def test_isin_non_trovato(tmp_path):
    f = Finto(json.dumps([{"warning": "No identifier found."}]).encode(), {})
    with pytest.raises(isin.ErroreIsin, match="non trovo nessuna quotazione") as e:
        isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())
    assert not e.value.rete
    assert not (tmp_path / "isin_ticker.json").exists()  # un fallimento non finisce in cache


def test_senza_connessione(tmp_path):
    f = Finto(b"", {}, errore_figi=True)
    f.ricerca = lambda q: (_ for _ in ()).throw(RuntimeError("niente rete"))
    with pytest.raises(isin.ErroreIsin, match="non rispondono") as e:
        isin.risolvi("IE00B4L5Y983", str(tmp_path), **f.kw())
    assert e.value.rete


# ------------------------------------------------------------------ scelta della quotazione
def q(ticker, valuta="EUR", storia=10, volume=1000, ultimo="2026-11-03"):
    return {"ticker": ticker, "valuta": valuta, "storia_anni": storia, "volume_medio": volume, "ultimo_scambio": ultimo}


def test_ordine_eur_poi_mi_de_as_poi_altre():
    quote = [q("A.PA"), q("A.L", "GBP"), q("A.AS"), q("A.DE"), q("A", "USD"), q("A.MI")]
    assert [x["ticker"] for x in isin.ordina_quotazioni(quote, oggi=OGGI)][:3] == ["A.MI", "A.DE", "A.AS"]
    assert isin.scegli_quotazione(quote, oggi=OGGI)["ticker"] == "A.MI"
    # senza .MI/.DE/.AS: tra le altre EUR vince la più storica (a parità di valuta) e poi le non-EUR
    senza = [q("A.PA", storia=5, volume=9999), q("A.BR", storia=12, volume=9000), q("A", "USD", storia=40, volume=10**4)]
    assert [x["ticker"] for x in isin.ordina_quotazioni(senza, oggi=OGGI)] == ["A.BR", "A.PA", "A"]


def test_parita_storia_poi_volumi():
    quote = [q("A.PA", storia=10.2, volume=500), q("A.BR", storia=10.8, volume=900), q("A.LS", storia=10.1, volume=5000)]
    # stessa storia in anni interi: contano i volumi
    assert isin.scegli_quotazione(quote, oggi=OGGI)["ticker"] == "A.LS"


def test_quotazioni_inattive_e_poco_liquide_vanno_in_fondo():
    quote = [q("A.MI", ultimo="2026-01-02", volume=10**6), q("B.MI", volume=10), q("C.PA", volume=10**6, valuta="EUR")]
    o = [x["ticker"] for x in isin.ordina_quotazioni(quote, oggi=OGGI)]
    assert o == ["C.PA", "B.MI", "A.MI"]


def test_regola_nelle_configurazione_e_errori():
    cfg = C.prepara({"portafogli": [{"nome": "P", "titoli": ["AAPL"]}]})
    assert cfg["isin"]["preferenze"] == ["EUR", ".MI", ".DE", ".AS"]
    cfg = C.prepara({"portafogli": [{"nome": "P", "titoli": ["AAPL"]}], "isin": {"preferenze": "usd, .l"}})
    assert cfg["isin"]["preferenze"] == ["USD", ".L"]
    with pytest.raises(C.ErroreConfig, match="isin.preferenze"):
        C.prepara({"portafogli": [{"nome": "P", "titoli": ["AAPL"]}], "isin": {"preferenze": ["euro!!"]}})


# ------------------------------------------------------------------ configurazione
def cfg_con_isin():
    return C.prepara(
        {
            "portafogli": [
                {"nome": "Mix", "titoli": {"IE00B4L5Y983": 50, "US0378331005": 30, "ENEL.MI": 20}},
                {"nome": "Solo ETF", "titoli": ["ie00b4l5y983"]},
            ],
            "settori": {"US0378331005": "tech"},
            "isin_scelte": {"IE00B4L5Y983": "EUNL.DE"},
        }
    )


def test_isin_trovati_nella_configurazione():
    assert isin.isin_nella_configurazione(cfg_con_isin()) == ["IE00B4L5Y983", "US0378331005"]


def test_sostituzione_isin_con_ticker(tmp_path):
    f = Finto(ETF.risposta_figi, {**ETF.schede, "AAPL": scheda("USD", "NasdaqGS", 45, 4 * 10**7)})
    risposte = {"IE00B4L5Y983": ETF.risposta_figi, "US0378331005": figi(("AAPL", "UN"))}
    f.http = lambda url, dati=None, intestazioni=None: risposte[json.loads(dati)[0]["idValue"]]
    cfg, ris = isin.risolvi_configurazione(cfg_con_isin(), str(tmp_path), **f.kw())
    assert cfg["isin_di"] == {"EUNL.DE": "IE00B4L5Y983", "AAPL": "US0378331005"}  # la scelta dell'utente vince sulla regola
    assert cfg["composizione"]["Mix"] == {"EUNL.DE": 0.5, "AAPL": 0.3, "ENEL.MI": 0.2}
    assert cfg["composizione"]["Solo ETF"] == {"EUNL.DE": 1.0}
    assert cfg["settori"] == {"AAPL": "tech"}
    assert ris["IE00B4L5Y983"]["scelta_utente"]


def test_benchmark_con_solo_isin():
    cfg = C.prepara({"benchmark": {"nome": "Mondo", "isin": "IE00B4L5Y983"}, "portafogli": [{"nome": "P", "titoli": ["AAPL"]}]})
    assert cfg["benchmark"]["ticker"] == "IE00B4L5Y983"
    assert isin.isin_nella_configurazione(cfg) == ["IE00B4L5Y983"]


def test_chiave_openfigi_non_finisce_nei_report():
    cfg = C.prepara({"portafogli": [{"nome": "P", "titoli": ["AAPL"]}], "isin": {"openfigi_chiave": "SEGRETO"}})
    assert cfg["isin"]["openfigi_chiave"] == "SEGRETO"
    assert "SEGRETO" not in C.in_yaml(cfg)
