"""Dati sintetici per i test: un 'finto Yahoo Finance' che non usa internet."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pytest
from dati_finti import GIORNI, crea_finto_yahoo  # noqa: E402,F401


@pytest.fixture
def finto_yahoo():
    return crea_finto_yahoo()


@pytest.fixture
def cfg_piccola():
    return {
        "nome": "test piccolo",
        "capitale_iniziale": 1000,
        "versamento_mensile": 0,
        "orizzonte_anni": 4,
        "orizzonti_intermedi": [2],
        "n_simulazioni": 200,
        "seed": 1,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01", "inizio_C": "2012-06-01"},
        "moduli": {"stress_test": True, "rischio_singolo_titolo": True, "confronto_modelli": False, "analisi_C": False},
        "settori": {"AAA.MI": "tech", "BBB.DE": "finanza", "CCC": "altro"},
        "portafogli": [
            {"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]},
            {"nome": "Due", "titoli": {"CCC": 60, "AAA.MI": 40}},
        ],
    }


# ------------------------------------------------------------------ marker «rapido»: la prova di Installa.command
# Ogni test è «rapido» (veloce e senza internet) tranne quelli elencati qui sotto e la prova nel browser (tests/e2e).
# Installa.command esegue solo `pytest -m rapido` (circa 30 secondi); la suite completa resta per GitHub Actions e per chi sviluppa.
LENTI = (
    "tests/e2e/",  # browser vero (Playwright)
    "tests/test_app_simulazione_completa.py",  # simulazioni complete nell'app, tutti i moduli (circa 2 minuti)
    "tests/test_app_controllo.py",  # interazioni con l'app (AppTest), circa 1 minuto
    "tests/test_non_regressione.py::test_parallelo_da_gli_stessi_numeri",  # avvia processi separati
    "tests/test_fonti.py::test_ripiego_sulla_seconda_fonte",  # attese tra i tentativi
    "tests/test_strumento.py::test_report_html_pdf_csv",
    "tests/test_funzioni_v11.py::test_salva_e_storico",
    "tests/test_prova_rapida.py::test_il_sottoinsieme_rapido_esclude_i_test_lenti",  # rilancia pytest  # salva report HTML, PDF ed Excel (già provati da altri test rapidi)
    "tests/test_isin_report.py::test_il_report_si_salva_con_pdf_ed_excel",
    "tests/test_garch.py::test_end_to_end_ripiego_garch_segnalato_nel_report",
)


def pytest_configure(config):
    config.addinivalue_line("markers", "rapido: test veloce e senza internet, eseguito dalla prova rapida di Installa.command")


def pytest_collection_modifyitems(config, items):
    for item in items:
        nodo = item.nodeid.replace("\\", "/")
        if not any(nodo.startswith(x) or f"/{x}" in nodo for x in LENTI):
            item.add_marker(pytest.mark.rapido)
