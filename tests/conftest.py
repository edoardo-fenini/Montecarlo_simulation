"""Dati sintetici per i test: un 'finto Yahoo Finance' che non usa internet."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import pytest

from dati_finti import GIORNI, crea_finto_yahoo  # noqa: E402,F401


@pytest.fixture
def finto_yahoo():
    return crea_finto_yahoo()


@pytest.fixture
def cfg_piccola():
    return {
        "nome": "test piccolo", "capitale_iniziale": 1000, "versamento_mensile": 0, "orizzonte_anni": 4,
        "orizzonti_intermedi": [2], "n_simulazioni": 200, "seed": 1,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01", "inizio_C": "2012-06-01"},
        "moduli": {"stress_test": True, "rischio_singolo_titolo": True, "confronto_modelli": False, "analisi_C": False},
        "settori": {"AAA.MI": "tech", "BBB.DE": "finanza", "CCC": "altro"},
        "portafogli": [
            {"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]},
            {"nome": "Due", "titoli": {"CCC": 60, "AAA.MI": 40}},
        ],
    }
