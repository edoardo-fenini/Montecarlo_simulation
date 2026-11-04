"""Tappa 0 (v1.4): campi vuoti, avvisi sul rendimento atteso, controllo di plausibilità. Tutto offline."""

import numpy as np
import pandas as pd
import pytest

import rendimento as R
from configurazione import ErroreConfig


def test_campo_vuoto_non_e_zero():
    for vuoto in (None, "", "  ", float("nan")):
        with pytest.raises(ErroreConfig, match="vuoto"):
            R.numero_pct(vuoto, "Premio di mercato")
    with pytest.raises(ErroreConfig, match="numero"):
        R.numero_pct("abc", "Premio di mercato")
    assert R.numero_pct("2,5", "x") == pytest.approx(0.025)
    assert R.numero_pct(0, "x") == 0.0  # zero scritto davvero è valido


def test_avvisi_campi():
    assert R.avvisi_campi("beta", 2.5, 4, 6) == []
    rossi = R.avvisi_campi("beta", None, 4, 6)
    assert rossi and rossi[0][0] == R.ROSSO
    gialli = R.avvisi_campi("beta", 2.5, 0, 6)
    assert gialli and gialli[0][0] == R.GIALLO
    assert R.avvisi_campi("uguale", None, None, "x")[0][0] == R.ROSSO  # i campi del beta non contano con «uguale»
    assert R.avvisi_campi("personalizzato", 0, 0, 0, {"A": None})[0][0] == R.ROSSO


def test_avviso_rendimento_sotto_1_per_cento():
    t = pd.DataFrame({"A": {"Rendimento atteso annuo": 0.005}, "B": {"Rendimento atteso annuo": 0.05}})
    av = R.avvisi_tabella(t)
    assert len(av) == 1 and av[0][0] == R.GIALLO and "«A»" in av[0][1]


def _som(media_annua, se_annuo=0.001):
    d = (1 + media_annua) ** (1 / 252) - 1
    return {"rend_sim": {"P": {"media_giorn": d, "se_giorn": se_annuo / 252}}}


def test_plausibilita_ok_e_fallita():
    M = np.full((10, 1), 0.0003)
    porte = {"P": (np.array([0]), np.array([1.0]))}
    ok = R.controlla_plausibilita(_som(0.06), M, porte, attesi={"P": 0.0605})
    assert ok["ok"].all() and R.messaggio_plausibilita({"A": ok}) is None
    male = R.controlla_plausibilita(_som(0.02), M, porte, attesi={"P": 0.06})
    assert not male["ok"].any()
    assert "FALLITO" in R.messaggio_plausibilita({"A": male})


def test_simulazione_completa_e_plausibile(tmp_path):
    import copy

    import non_regressione as N
    from dati_finti import crea_finto_yahoo

    import analisi
    import configurazione as C

    cfg = C.prepara(copy.deepcopy(N.CONFIG))
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=crea_finto_yahoo(), log=lambda *a: None)
    assert ris["errore_plausibilita"] is None
    assert set(ris["plausibilita"]) >= {"A"}
