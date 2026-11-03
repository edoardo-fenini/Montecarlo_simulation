"""Funzioni 1.1: analisi salvate, esportazione Excel, prova rapida dei pesi, configurazioni di esempio."""

import glob
import io
import json
import os

import pytest
from openpyxl import load_workbook

import analisi
import configurazione as C
import report as R

QUI = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="module")
def ris(tmp_path_factory):
    from dati_finti import crea_finto_yahoo

    cfg = {
        "nome": "funzioni nuove",
        "capitale_iniziale": 1000,
        "orizzonte_anni": 4,
        "orizzonti_intermedi": [2],
        "n_simulazioni": 300,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01"},
        "settori": {"AAA.MI": "tech", "BBB.DE": "finanza", "CCC": "altro"},
        "portafogli": [{"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]}, {"nome": "Due", "titoli": ["CCC"]}],
    }
    return analisi.esegui(
        C.prepara(cfg), cartella_cache=str(tmp_path_factory.mktemp("c")), scaricatore=crea_finto_yahoo(), log=lambda *a: None
    )


def test_salva_e_storico(ris, tmp_path):
    base = str(tmp_path / "report")
    c1 = os.path.join(base, "2026-01-01_100000_primo")
    c2 = os.path.join(base, "2026-02-01_100000_secondo")
    R.salva(ris, c1, pdf=False)
    R.salva(ris, c2, pdf=False)
    for f in ("report.html", "report.xlsx", "riassunto.json", "configurazione_usata.yaml"):
        assert os.path.exists(os.path.join(c1, f))
    el = R.elenco_analisi(base)
    assert [os.path.basename(e["cartella"]) for e in el] == ["2026-02-01_100000_secondo", "2026-01-01_100000_primo"]  # più recente prima
    r = el[0]
    assert r["nome"] == "funzioni nuove" and r["simulazioni"] == 300 and [p["nome"] for p in r["portafogli"]] == ris["nomi"]
    assert isinstance(r["portafogli"][0]["livello"], int)
    json.dumps(r)
    assert R.elenco_analisi(str(tmp_path / "non_esiste")) == []
    assert R.cartella_storico("Il mio confronto!", base).startswith(os.path.join(base, "20"))


def test_excel_con_formati(ris):
    wb = load_workbook(io.BytesIO(R.excel_report(ris)))
    assert wb.sheetnames[:3] == ["Sintesi", "2 anni", "4 anni"] and "Stress test" in wb.sheetnames
    ws = wb["4 anni"]
    righe = {}
    for i in range(1, ws.max_row + 1):
        righe.setdefault(ws.cell(i, 1).value, i)  # prima occorrenza = analisi A
    r_med, r_prob = righe["Valore mediano"], righe["Prob. sotto il versato"]
    assert isinstance(ws.cell(r_med, 2).value, float) and "€" in ws.cell(r_med, 2).number_format  # numeri veri, non testo
    assert ws.cell(r_prob, 2).number_format == "0.0%" and 0 <= ws.cell(r_prob, 2).value <= 1
    assert ws.cell(r_med, 2).value == pytest.approx(ris["sim"]["A"]["orizzonti"][4].loc["Valore mediano", "Uno"])


def test_prova_rapida_dei_pesi(ris):
    tutto_bench = analisi.prova_pesi(ris, "Uno", 1.0, n=600)
    niente_bench = analisi.prova_pesi(ris, "Uno", 0.0, n=600)
    assert tutto_bench["vol"] == pytest.approx(ris["sim"]["A"]["vol_sim"]["Benchmark test"], rel=0.08)
    assert niente_bench["vol"] == pytest.approx(ris["sim"]["A"]["vol_sim"]["Uno"], rel=0.08)
    mezzo = analisi.prova_pesi(ris, "Uno", 0.5, n=600)
    assert min(tutto_bench["vol"], niente_bench["vol"]) <= mezzo["vol"] <= max(tutto_bench["vol"], niente_bench["vol"])


@pytest.mark.parametrize("percorso", sorted(glob.glob(os.path.join(QUI, "..", "configurazioni", "*.yaml"))))
def test_configurazioni_di_esempio_valide(percorso):
    cfg = C.carica(percorso)
    assert cfg["portafogli"] and cfg["composizione"]


def test_file_di_log(tmp_path):
    import logging

    import registro

    f = tmp_path / "log.txt"
    log = registro.configura(percorso=str(f))
    log.error("prova di scrittura nel log")
    for h in log.handlers:
        h.flush()
    assert "prova di scrittura nel log" in f.read_text(encoding="utf-8")
    n = len(log.handlers)
    registro.configura(percorso=str(f))
    assert len(log.handlers) == n  # idempotente
    for h in list(log.handlers):
        if getattr(h, "baseFilename", "") == str(f):
            log.removeHandler(h)
            h.close()
    assert logging.getLogger("confronta") is log
