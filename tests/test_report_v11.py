"""Report 1.1: formati italiani, livello di rischio, copertina e indice, schede, tabelle non affiancate, spiegazioni."""

import re

import pytest

import analisi
import configurazione as C
import report as R


def test_formati_italiani():
    assert R.eur(1234567.4) == "1.234.567 €"
    assert R.eur(999) == "999 €"
    assert R.pct(0.1234) == "12,3%" and R.pct(-0.5) == "-50,0%" and R.pct(0.05, 0) == "5,0%"  # sempre una cifra decimale
    assert R.pct(0.002, 2) == "0,20%"  # TER con due decimali
    assert R.num(3.14159) == "3,1" and R.num(float("inf")) == "mai" and R.num_it(20000) == "20.000"


def test_contrasto_colori_livelli():
    def lum(h):
        c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    for _, _, col in R.LIVELLI_RISCHIO:
        assert (1.05) / (lum(col) + 0.05) >= 4.5, col  # testo bianco leggibile


@pytest.mark.parametrize("vol,livello", [(0.05, 1), (0.10, 2), (0.14, 3), (0.19, 3), (0.25, 4), (0.30, 5), (0.60, 5)])
def test_livello_rischio(vol, livello):
    assert R.livello_rischio(vol)[0] == livello


@pytest.fixture(scope="module")
def ris_report(tmp_path_factory):
    from dati_finti import crea_finto_yahoo

    cfg = {
        "nome": "prova report",
        "capitale_iniziale": 1000,
        "orizzonte_anni": 4,
        "orizzonti_intermedi": [2],
        "n_simulazioni": 200,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01"},
        "settori": {"AAA.MI": "tech", "BBB.DE": "finanza", "CCC": "altro"},
        "portafogli": [{"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]}, {"nome": "Due", "titoli": {"CCC": 60, "AAA.MI": 40}}],
    }
    ris = analisi.esegui(
        C.prepara(cfg), cartella_cache=str(tmp_path_factory.mktemp("c")), scaricatore=crea_finto_yahoo(), log=lambda *a: None
    )
    return ris, R.sezioni(ris)


def test_html_copertina_indice_schede(ris_report):
    ris, S = ris_report
    h = R.html_report(ris, S)
    assert "class='copertina'" in h and "nav class='indice'" in h and "Dati aggiornati al 31/12/2024" in h
    ancore = re.findall(r'href="#(sez-\d+)"', h)
    assert ancore and all(f"id='{a}'" in h for a in ancore)  # ogni voce dell'indice porta a una sezione
    assert list(S)[0] == "In una pagina" and h.count('class="scheda"') == 3
    assert "Rischio " in h and "■" in h  # livello con numero e quadratini, non solo colore
    assert h.count("class='didascalia'") >= 4  # spiegazioni sotto i grafici


def test_tabelle_non_affiancate(ris_report):
    ris, S = ris_report
    for blocchi in S.values():
        for b in blocchi:
            if b[0] == "tab":
                assert not b[1]["gruppi"], "le analisi A e B non devono essere affiancate nella stessa tabella"
                assert len(b[1]["intest"]) <= 11


def test_pdf_con_indice_e_segnalibri(ris_report):
    ris, S = ris_report
    pdf = R.pdf_report(ris, S)
    assert pdf[:4] == b"%PDF"
    assert b"/Outlines" in pdf  # segnalibri del PDF (indice laterale)
    assert b"/Link" in pdf  # voci dell'indice cliccabili
