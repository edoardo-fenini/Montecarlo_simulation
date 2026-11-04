"""Prova completa con un ISIN nella configurazione (dati finti): simulazione, report con ISIN + ticker e tabella «Controllo dati»."""

import copy
import datetime
import json

import pytest

import analisi
import configurazione as C
import controllo
import dati as D
import report

ISIN = "IT0003128367"


def kw():
    figi = json.dumps([{"data": [{"ticker": "AAA", "exchCode": "IM", "name": "AAA SPA"}]}]).encode()
    scheda = {"valuta": "EUR", "borsa": "Milan", "nome": "AAA", "tipo": "EQUITY", "primo": 1.3e9, "volume": 1e5, "ultimo": "2024-12-31"}
    return {"http": lambda url, dati=None, intestazioni=None: figi, "ispettore": {"AAA.MI": scheda}.get, "ricerca": lambda q: [], "oggi": datetime.date(2025, 1, 2)}


@pytest.fixture(scope="module")
def ris(tmp_path_factory, cfg_piccola=None):
    from dati_finti import crea_finto_yahoo

    d = str(tmp_path_factory.mktemp("cache"))
    cfg = {
        "nome": "isin",
        "capitale_iniziale": 1000,
        "orizzonte_anni": 4,
        "orizzonti_intermedi": [2],
        "n_simulazioni": 200,
        "seed": 1,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01", "inizio_C": "2012-06-01"},
        "moduli": {"stress_test": False, "rischio_singolo_titolo": False, "confronto_modelli": False, "analisi_C": False, "verifica_convergenza": False},
        "portafogli": [{"nome": "Uno", "titoli": [ISIN, "BBB.DE"]}, {"nome": "Due", "titoli": {"CCC": 60, ISIN: 40}}],
        "nomi_attesi": {ISIN: "Tesla"},
    }
    cfg = C.prepara(copy.deepcopy(cfg))
    arch = D.Archivio(d, log=lambda *a: None, scaricatore=crea_finto_yahoo())
    e = controllo.controlla(cfg, arch, **kw())
    out = analisi.esegui(e["cfg"], archivio=arch, controllo=controllo.per_report(e), log=lambda *a: None)
    return out, e


def test_il_controllo_vede_isin_ticker_e_avviso_sul_nome(ris):
    _, e = ris
    r = next(x for x in e["righe"] if x["input"] == ISIN)
    assert (r["isin"], r["ticker"]) == (ISIN, "AAA.MI")
    assert r["esito"] == "GIALLO" and "molto diverso" in r["gialli"][0]
    assert not e["blocca"] and "1 avviso" in e["riepilogo"]


def test_il_report_mostra_isin_e_ticker(ris):
    r, _ = ris
    assert r["dati_info"].loc["AAA.MI", "isin"] == ISIN and r["dati_info"].loc["BBB.DE", "isin"] == ""
    S = report.sezioni(r)
    html = report.html_report(r, S)
    assert "Controllo dei dati prima della simulazione" in html and ISIN in html and "AAA.MI" in html and "GIALLO" in html
    csv = report.tabelle_csv(r)
    assert "controllo_dati.csv" in csv and ISIN in set(csv["controllo_dati.csv"]["ISIN"])
    assert "isin" in csv["titoli.csv"].columns


def test_il_report_si_salva_con_pdf_ed_excel(ris, tmp_path):
    r, _ = ris
    report.salva(r, str(tmp_path / "out"), log=lambda *a: None)
    import openpyxl

    assert (tmp_path / "out" / "report.pdf").stat().st_size > 5000
    assert "Controllo dati" in openpyxl.load_workbook(tmp_path / "out" / "report.xlsx").sheetnames
    assert "SEGRETO" not in (tmp_path / "out" / "configurazione_usata.yaml").read_text()
