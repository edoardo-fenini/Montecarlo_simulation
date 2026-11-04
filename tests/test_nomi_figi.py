"""v1.3 – controllo incrociato dei nomi (OpenFIGI contro Yahoo) e borse non mappate (tutto senza internet)."""

import datetime
import json

import pytest
from test_controllo import base, config, meta, riga, serie

import controllo
import dati as D
import fonti
import isin
import nomi

OGGI = datetime.date(2026, 11, 4)
ISIN = "IE00B4L5Y983"


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(fonti.time, "sleep", lambda s: None)


def figi(voci, extra=()):
    """voci = (ticker, borsa, nome OpenFIGI). extra = (ticker, borsa) su borse che non so tradurre."""
    dati = [{"ticker": t, "exchCode": e, "name": n} for t, e, n in voci] + [{"ticker": t, "exchCode": e, "name": "Altro"} for t, e in extra]
    return json.dumps([{"data": dati}]).encode()


def scheda(nome, volume=1e5, borsa="Milan"):
    return {"valuta": "EUR", "borsa": borsa, "nome": nome, "tipo": "ETF", "primo": 1.2e9, "volume": volume, "ultimo": "2026-11-03"}


# ------------------------------------------------------------------ confronto tollerante
@pytest.mark.parametrize(
    "a,b",
    [
        ("APPLE INC", "Apple Inc."),
        ("ENEL SPA", "Enel S.p.A."),
        ("UNICREDIT SPA", "UniCredit S.p.A"),
        ("SIEMENS AG", "Siemens Aktiengesellschaft AG"),
        ("ASTRAZENECA PLC", "AstraZeneca PLC"),
        ("ISHARES CORE MSCI WORLD UCITS ETF", "iShares Core MSCI World UCITS ETF USD (Acc)"),
        ("ISHARES CORE MSCI WRLD", "iShares Core MSCI World UCITS ETF"),
        ("L'OREAL", "L’Oréal S.A."),  # accento: la parola resta simile
    ],
)
def test_nomi_simili_non_sono_discordanti(a, b):
    assert nomi.somiglianza_nomi(a, b) >= isin.SOMIGLIANZA_NOMI_MIN


@pytest.mark.parametrize("a,b", [("APPLE INC", "Tesla Inc."), ("ENEL SPA", "Eni S.p.A."), ("ISHARES CORE S&P 500", "Vanguard FTSE All-World")])
def test_nomi_molto_diversi(a, b):
    assert nomi.somiglianza_nomi(a, b) < isin.SOMIGLIANZA_NOMI_MIN


def test_il_vecchio_import_da_controllo_funziona_ancora():
    assert controllo.somiglianza_nomi("Apple", "Apple Inc.") == 1


def test_senza_un_nome_o_con_solo_forma_societaria_non_si_confronta():
    assert not isin.nome_discordante({"nome_figi": "", "nome_yahoo": "Apple Inc."})
    assert not isin.nome_discordante({"nome_figi": "INC", "nome_yahoo": "Apple Inc."})
    assert not isin.nome_discordante({"nome_figi": "APPLE INC"})
    assert isin.nome_discordante({"nome_figi": "TESLA INC", "nome_yahoo": "Apple Inc."})
    assert not isin.nome_discordante({"nome_figi": "TESLA INC", "nome_yahoo": "Apple Inc."}, None)


# ------------------------------------------------------------------ scelta con nomi discordanti
def risolvi(tmp_path, risposta, schede, **kw):
    return isin.risolvi(
        ISIN, str(tmp_path), http=lambda *a, **k: risposta, ispettore=schede.get, ricerca=lambda q: [], oggi=OGGI, **kw
    )


def test_quotazione_con_nome_diverso_viene_scartata_e_si_prova_la_successiva(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF"), ("EUNL", "GY", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("Tesla Motors Inc"), "EUNL.DE": scheda("iShares Core MSCI World UCITS ETF USD (Acc)", borsa="XETRA")}
    ris = risolvi(tmp_path, risposta, schede)
    # SWDA.MI sarebbe la prima per regola (.MI) ma il suo nome non torna: si usa EUNL.DE
    assert ris["ticker"] == "EUNL.DE" and ris["quotazioni"][-1]["ticker"] == "SWDA.MI"
    assert len(ris["avvisi_nome"]) == 1 and "SWDA.MI scartata" in ris["avvisi_nome"][0] and "Tesla Motors Inc" in ris["avvisi_nome"][0]


def test_se_tutti_i_nomi_sono_diversi_si_usa_la_prima_ma_con_avviso(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF")])
    ris = risolvi(tmp_path, risposta, {"SWDA.MI": scheda("Tesla Motors Inc")})
    assert ris["ticker"] == "SWDA.MI" and "molto diverso" in ris["avvisi_nome"][0]


def test_nomi_concordanti_nessun_avviso_e_scelta_invariata(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF"), ("EUNL", "GY", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("iShares Core MSCI World UCITS ETF"), "EUNL.DE": scheda("iShares Core MSCI World UCITS ETF (Acc)")}
    ris = risolvi(tmp_path, risposta, schede)
    assert ris["ticker"] == "SWDA.MI" and ris["avvisi_nome"] == []


def test_quotazione_forzata_con_nome_diverso_avvisa_ma_resta(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF"), ("EUNL", "GY", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("iShares Core MSCI World UCITS ETF"), "EUNL.DE": scheda("Tesla Motors Inc")}
    ris = risolvi(tmp_path, risposta, schede, scelta="EUNL.DE")
    assert ris["ticker"] == "EUNL.DE" and "verifica che sia il titolo giusto" in ris["avvisi_nome"][0]


# ------------------------------------------------------------------ borse non mappate
def test_borse_non_mappate_sono_elencate_e_salvate_in_cache(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF")], extra=[("SWDA", "TH"), ("SWDA", "TH"), ("IWDA", "QQ")])
    schede = {"SWDA.MI": scheda("iShares Core MSCI World UCITS ETF")}
    ris = risolvi(tmp_path, risposta, schede)
    assert [(b["borsa"], b["ticker"]) for b in ris["borse_non_mappate"]] == [("TH", "SWDA"), ("QQ", "IWDA")]
    again = isin.risolvi(ISIN, str(tmp_path), oggi=OGGI)  # dalla cache, senza rete
    assert again["metodo"].startswith("cache") and len(again["borse_non_mappate"]) == 2


def test_candidati_openfigi_senza_lista_non_cambia_il_risultato():
    r = figi([("SWDA", "IM", "X")], extra=[("SWDA", "TH")])
    c = isin.candidati_openfigi(ISIN, http=lambda *a, **k: r)
    assert [x["ticker"] for x in c] == ["SWDA.MI"]


# ------------------------------------------------------------------ nel controllo dei dati
def esegui(tmp_path, risposta, schede, extra_cfg=None):
    m = base(SWDA_MI=(serie(seed=7), meta(nome="x", tipo="ETF")), EUNL_DE=(serie(seed=8), meta(nome="x", tipo="ETF")))
    cfg = config(["AAA.MI", ISIN], **(extra_cfg or {}))
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=m.scarica)
    return controllo.controlla(
        cfg, arch, oggi=OGGI, http=lambda *a, **k: risposta, ispettore=schede.get, ricerca=lambda q: []
    )


def test_nel_controllo_nome_diverso_e_giallo_e_usa_la_successiva(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF"), ("EUNL", "GY", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("Tesla Motors Inc"), "EUNL.DE": scheda("iShares Core MSCI World UCITS ETF", borsa="XETRA")}
    e = esegui(tmp_path, risposta, schede)
    r = riga(e, ISIN)
    assert r["ticker"] == "EUNL.DE" and r["esito"] == "GIALLO" and not r["rossi"]
    assert any("SWDA.MI scartata" in g for g in r["gialli"])
    assert not e["blocca"] and e["cfg"]["composizione"]["P"].get("EUNL.DE") == 0.5
    assert "SWDA.MI scartata" in controllo.tabella(e["righe"]).loc[1, "Dettagli"]


def test_nel_controllo_borse_non_mappate_sono_solo_informative(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF")], extra=[("SWDA", "TH")])
    e = esegui(tmp_path, risposta, {"SWDA.MI": scheda("iShares Core MSCI World UCITS ETF")})
    r = riga(e, ISIN)
    assert r["esito"] == "VERDE" and "TH (SWDA)" in r["info"][0]  # nessun colore: solo informazione
    d = controllo.tabella(e["righe"]).loc[1, "Dettagli"]
    assert d.startswith("info: ") and "non mappate" in d
    assert "non mappate" in controllo.testo_tabella(e)
    assert riga(e, "AAA.MI")["info"] == [] and controllo.tabella(e["righe"]).loc[0, "Dettagli"] == "tutto a posto"


def test_nomi_attesi_resta_un_controllo_in_piu(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("iShares Core MSCI World UCITS ETF")}
    e = esegui(tmp_path, risposta, schede, {"nomi_attesi": {ISIN: "Vanguard FTSE All-World"}})
    r = riga(e, ISIN)
    assert r["esito"] == "GIALLO" and any("molto diverso da quello atteso" in g for g in r["gialli"])


def test_soglia_di_somiglianza_configurabile(tmp_path):
    risposta = figi([("SWDA", "IM", "ISHARES CORE MSCI WORLD UCITS ETF")])
    schede = {"SWDA.MI": scheda("Tesla Motors Inc")}
    assert riga(esegui(tmp_path / "a", risposta, schede), ISIN)["esito"] == "GIALLO"
    e = esegui(tmp_path / "b", risposta, schede, {"controllo_dati": {"somiglianza_nome_min": 0.0}})
    assert riga(e, ISIN)["esito"] == "VERDE"
