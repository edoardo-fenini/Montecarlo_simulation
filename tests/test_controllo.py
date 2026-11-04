"""Controllo dati: ogni regola del semaforo, riepilogo, blocco con un rosso (app esclusa), --solo-controllo, ISIN nel controllo."""

import datetime
import json

import numpy as np
import pandas as pd
import pytest

import analisi
import configurazione as C
import confronta
import controllo
import dati as D
import fonti

OGGI = datetime.date(2026, 11, 4)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(fonti.time, "sleep", lambda s: None)


def serie(anni=6.0, fine="2026-11-03", mancanti=0.0, salto=None, seed=0):
    idx = pd.bdate_range(end=fine, periods=int(anni * 261))
    r = np.random.default_rng(seed).normal(0.0003, 0.01, len(idx))
    if salto:
        r[len(r) // 2] = salto
    s = pd.Series(100 * np.cumprod(1 + r), index=idx)
    if mancanti:
        togli = np.random.default_rng(seed + 1).choice(np.arange(5, len(idx) - 5), int(len(idx) * mancanti), replace=False)
        s = s.drop(idx[togli])
    return s


def meta(**kw):
    return {"valuta": "EUR", "tipo": "EQUITY", "nome": "Nome Vero Spa", "borsa": "Milan", "fonte": "Yahoo Finance", **kw}


class Mercato:
    """Finto Yahoo: {ticker: (serie, meta)}; i ticker mancanti 'non esistono'."""

    def __init__(self, **titoli):
        self.titoli = {k.replace("_", "."): v for k, v in titoli.items()}

    def scarica(self, t):
        if t in self.titoli:
            return self.titoli[t][0].copy(), dict(self.titoli[t][1])
        return pd.Series(dtype=float), {}


def config(titoli, **extra):
    return C.prepara({"benchmark": {"nome": "Bench", "ticker": "BMK.AS"}, "portafogli": [{"nome": "P", "titoli": titoli}], **extra})


def esegui_controllo(tmp_path, mercato, titoli, **extra):
    cfg = config(titoli, **extra)
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=mercato.scarica)
    return controllo.controlla(cfg, arch, oggi=OGGI)


def base(**modifiche):
    """Mercato con tre titoli e un benchmark tutti a posto; `modifiche` sostituiscono (serie, meta) di un ticker."""
    m = {
        "AAA_MI": (serie(seed=1), meta()),
        "BBB_DE": (serie(seed=2), meta(nome="Beta Group AG", borsa="XETRA")),
        "CCC": (serie(seed=3), meta(valuta="USD", nome="Gamma Inc.")),
        "BMK_AS": (serie(seed=4), meta(tipo="ETF", nome="Bench ETF")),
    }
    m.update({k.replace("_", "."): v for k, v in modifiche.items()})
    return Mercato(**{k.replace(".", "_"): v for k, v in m.items()})


def riga(esito, inp):
    return next(r for r in esito["righe"] if r["input"] == inp)


TITOLI = ["AAA.MI", "BBB.DE", "CCC"]


def test_tutto_verde_e_riepilogo(tmp_path):
    e = esegui_controllo(tmp_path, base(), TITOLI)
    assert [r["esito"] for r in e["righe"]] == ["VERDE"] * 4  # tre titoli + benchmark
    assert e["riepilogo"] == "4 titoli trovati, 0 avvisi, 0 errori" and not e["blocca"] and e["messaggio"] == ""
    r = riga(e, "AAA.MI")
    assert r["nome"] == "Nome Vero Spa" and r["borsa"] == "Milan" and r["valuta"] == "EUR" and r["fonte"] == "Yahoo Finance"
    assert r["anni"] == pytest.approx(6, abs=0.1) and r["mancanti"] == pytest.approx(0, abs=0.001)
    assert r["ultimo"] == datetime.date(2026, 11, 3)


def test_tabella_ha_tutte_le_colonne(tmp_path):
    t = controllo.tabella(esegui_controllo(tmp_path, base(), TITOLI)["righe"])
    assert list(t.columns) == controllo.COLONNE_TABELLA
    for c in [
        "Input",
        "Ticker usato",
        "Nome",
        "Borsa",
        "Valuta",
        "Fonte",
        "Prima data",
        "Ultima data",
        "Anni di storia",
        "% giorni mancanti",
        "Ultimo prezzo",
        "Esito",
    ]:
        assert c in t.columns
    assert t.loc[0, "Esito"].startswith("🟢") and t.loc[0, "Ultima data"] == "03/11/2026"


# ------------------------------------------------------------------ ROSSO
def test_rosso_ticker_non_trovato(tmp_path):
    e = esegui_controllo(tmp_path, base(), TITOLI + ["ZZZ.MI"])
    r = riga(e, "ZZZ.MI")
    assert r["esito"] == "ROSSO" and "non trovato" in r["rossi"][0]
    assert e["blocca"] and e["riepilogo"] == "4 titoli trovati, 0 avvisi, 1 errore" and "ZZZ.MI" in e["messaggio"]


def test_rosso_nessun_prezzo(tmp_path):
    vuota = pd.Series(dtype=float)
    m = base(CCC=(serie(), meta()))
    m.scarica_originale = m.scarica
    m.scarica = lambda t: (vuota.copy(), {"valuta": "EUR"}) if t == "CCC" else m.scarica_originale(t)
    e = esegui_controllo(tmp_path, m, TITOLI)
    assert riga(e, "CCC")["esito"] == "ROSSO" and e["blocca"]


def test_rosso_meno_di_un_anno(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(anni=0.6), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "ROSSO" and "anni di storia" in r["rossi"][0] and e["blocca"]


def test_rosso_ultimo_prezzo_oltre_30_giorni(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(fine="2026-09-25"), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "ROSSO" and "ultimo prezzo" in r["rossi"][0]


def test_rosso_prezzi_zero_o_negativi(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(), meta(prezzi_non_positivi=3))), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "ROSSO" and "zero o negativi" in r["rossi"][0]


def test_prezzi_non_positivi_contati_dalle_fonti():
    s = fonti._pulisci(pd.Series([1.0, 0.0, -3.0, 2.0], index=pd.date_range("2020-01-01", periods=4)))
    assert len(s) == 2 and s.attrs["non_positivi"] == 2


def test_rosso_isin_con_cifra_di_controllo_errata(tmp_path):
    e = esegui_controllo(tmp_path, base(), TITOLI + ["IE00B4L5Y984"])
    r = riga(e, "IE00B4L5Y984")
    assert r["esito"] == "ROSSO" and "cifra di controllo" in r["rossi"][0] and e["blocca"]


# ------------------------------------------------------------------ GIALLO
def test_giallo_meno_di_tre_anni(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(anni=2), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "GIALLO" and "anni di storia" in r["gialli"][0] and not e["blocca"]
    assert e["riepilogo"] == "4 titoli trovati, 1 avviso, 0 errori"


def test_giallo_giorni_mancanti_oltre_5_per_cento(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(mancanti=0.10), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "GIALLO" and r["mancanti"] > 0.05 and "senza prezzo" in r["gialli"][0]
    # sotto il 5% resta verde
    e2 = esegui_controllo(tmp_path / "b", base(AAA_MI=(serie(mancanti=0.03), meta())), TITOLI)
    assert riga(e2, "AAA.MI")["esito"] == "VERDE"


def test_giallo_ultimo_prezzo_oltre_7_giorni(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(fine="2026-10-23"), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "GIALLO" and "ultimo prezzo" in r["gialli"][0]


def test_giallo_movimenti_estremi(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(salto=0.5), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "GIALLO" and "movimenti giornalieri" in r["gialli"][0] and "+50%" in r["gialli"][0]


def test_giallo_nome_molto_diverso_da_quello_atteso(tmp_path):
    attesi = {"nomi_attesi": {"AAA.MI": "Tesla Motors", "BBB.DE": "Beta", "CCC": "gamma"}}
    e = esegui_controllo(tmp_path, base(), TITOLI, **attesi)
    assert riga(e, "AAA.MI")["esito"] == "GIALLO" and "molto diverso" in riga(e, "AAA.MI")["gialli"][0]
    assert riga(e, "BBB.DE")["esito"] == "VERDE" and riga(e, "CCC")["esito"] == "VERDE"  # nomi abbreviati o in minuscolo: ok


def test_somiglianza_nomi():
    assert controllo.somiglianza_nomi("Apple", "Apple Inc.") == 1
    assert controllo.somiglianza_nomi("Enel", "Enel SpA") == 1
    assert controllo.somiglianza_nomi("iShares Core MSCI World", "iShares Core MSCI World UCITS ETF USD (Acc)") == 1
    assert controllo.somiglianza_nomi("Tesla", "Apple Inc.") < 0.4


def test_soglie_configurabili(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(anni=2), meta())), TITOLI, controllo_dati={"storia_avviso_anni": 1.5})
    assert riga(e, "AAA.MI")["esito"] == "VERDE"
    e = esegui_controllo(
        tmp_path / "b", base(AAA_MI=(serie(anni=2), meta())), TITOLI, controllo_dati={"storia_min_anni": 2.5, "storia_avviso_anni": 3}
    )
    assert riga(e, "AAA.MI")["esito"] == "ROSSO"
    with pytest.raises(C.ErroreConfig, match="soglie"):
        config(TITOLI, controllo_dati={"storia_min_anni": 5, "storia_avviso_anni": 3})


def test_il_peggiore_vince_e_i_motivi_si_sommano(tmp_path):
    e = esegui_controllo(tmp_path, base(AAA_MI=(serie(anni=0.5, salto=0.5), meta())), TITOLI)
    r = riga(e, "AAA.MI")
    assert r["esito"] == "ROSSO" and r["rossi"] and r["gialli"]


# ------------------------------------------------------------------ ISIN nel controllo
FIGI_ETF = json.dumps(
    [{"data": [{"ticker": "SWDA", "exchCode": "IM", "name": "ETF"}, {"ticker": "EUNL", "exchCode": "GY", "name": "ETF"}]}]
).encode()


def kw_isin():
    schede = {
        "SWDA.MI": {"valuta": "EUR", "borsa": "Milan", "nome": "ETF", "tipo": "ETF", "primo": 1.2e9, "volume": 1e5, "ultimo": "2026-11-03"},
        "EUNL.DE": {"valuta": "EUR", "borsa": "XETRA", "nome": "ETF", "tipo": "ETF", "primo": 1.2e9, "volume": 3e5, "ultimo": "2026-11-03"},
    }
    return {"http": lambda url, dati=None, intestazioni=None: FIGI_ETF, "ispettore": schede.get, "ricerca": lambda q: []}


def test_isin_nel_controllo_mostra_isin_e_ticker(tmp_path):
    m = base(SWDA_MI=(serie(seed=7), meta(nome="ETF", tipo="ETF")))
    cfg = config(["AAA.MI", "IE00B4L5Y983"], costi={"IE00B4L5Y983": 0.002})  # senza costi indicati un ETF sarebbe giallo (v1.4)
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=m.scarica)
    e = controllo.controlla(cfg, arch, oggi=OGGI, **kw_isin())
    r = riga(e, "IE00B4L5Y983")
    assert r["isin"] == "IE00B4L5Y983" and r["ticker"] == "SWDA.MI" and r["esito"] == "VERDE"
    assert [q["ticker"] for q in r["risoluzione"]["quotazioni"]] == ["SWDA.MI", "EUNL.DE"]
    assert e["cfg"]["composizione"]["P"] == {"AAA.MI": 0.5, "SWDA.MI": 0.5}
    t = controllo.tabella(e["righe"])
    assert {"IE00B4L5Y983", "SWDA.MI"} <= set(t["ISIN"]) | set(t["Ticker usato"])


def test_isin_non_trovato_e_rosso(tmp_path):
    kw = kw_isin()
    kw["http"] = lambda url, dati=None, intestazioni=None: json.dumps([{"warning": "No identifier found."}]).encode()
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=base().scarica)
    e = controllo.controlla(config(["AAA.MI", "IE00B4L5Y983"]), arch, oggi=OGGI, **kw)
    assert riga(e, "IE00B4L5Y983")["esito"] == "ROSSO" and e["blocca"]


# ------------------------------------------------------------------ riga di comando
def scrivi_config(tmp_path, titoli):
    p = tmp_path / "c.yaml"
    p.write_text(
        json.dumps({"nome": "prova", "benchmark": {"nome": "Bench", "ticker": "BMK.AS"}, "portafogli": [{"nome": "P", "titoli": titoli}]})
    )
    return str(p)


class SimulazioneVietata(Exception):
    pass


@pytest.fixture
def senza_simulare(monkeypatch):
    chiamate = []

    def vietato(*a, **k):
        chiamate.append(k)
        raise SimulazioneVietata

    monkeypatch.setattr(analisi, "esegui", vietato)
    return chiamate


def lancia(tmp_path, m, titoli, *opz, **kw):
    return confronta.main(
        ["--config", scrivi_config(tmp_path, titoli), *opz], scaricatore=m.scarica, oggi=OGGI, cartella_cache=str(tmp_path / "cache"), **kw
    )


def test_cli_con_un_rosso_si_ferma_senza_simulare(tmp_path, senza_simulare, capsys):
    assert lancia(tmp_path, base(), TITOLI + ["ZZZ.MI"]) == 1
    out = capsys.readouterr()
    assert "Controllo dati: 4 titoli trovati, 0 avvisi, 1 errore" in out.out
    assert "Simulazione bloccata" in out.err and "ZZZ.MI" in out.err
    assert senza_simulare == []  # la simulazione non è partita


def test_cli_solo_controllo(tmp_path, senza_simulare, capsys):
    assert lancia(tmp_path, base(), TITOLI, "--solo-controllo") == 0
    out = capsys.readouterr().out
    assert "4 titoli trovati, 0 avvisi, 0 errori" in out and "AAA.MI" in out and "Nessun errore" in out
    assert lancia(tmp_path, base(), TITOLI + ["ZZZ.MI"], "--solo-controllo") == 1
    assert senza_simulare == []


def test_cli_con_un_giallo_prosegue(tmp_path, senza_simulare, capsys):
    lancia(tmp_path, base(AAA_MI=(serie(anni=2), meta())), TITOLI)  # la simulazione (finta) viene chiamata
    assert len(senza_simulare) == 1 and senza_simulare[0]["controllo"]["conteggi"] == {"rossi": 0, "gialli": 1}
    assert "1 avviso" in capsys.readouterr().out
