"""Test dello strumento generico: configurazione, metodi di rendimento atteso, portafogli misti, end-to-end."""
import copy
import numpy as np
import pandas as pd
import pytest

import analisi
import configurazione as C
import dati as D
from configurazione import BENCH, ErroreConfig


# ---------------------------------------------------------------- configurazione
def test_pesi_che_non_sommano_a_100(cfg_piccola):
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"][1]["titoli"] = {"CCC": 60, "AAA.MI": 30}
    with pytest.raises(ErroreConfig, match="sommano a 90"):
        C.prepara(cfg)


def test_pesi_uguali_se_non_indicati(cfg_piccola):
    cfg = C.prepara(copy.deepcopy(cfg_piccola))
    assert cfg["composizione"]["Uno"] == {"AAA.MI": 0.5, "BBB.DE": 0.5}
    assert cfg["composizione"]["Due"] == pytest.approx({"CCC": 0.6, "AAA.MI": 0.4})
    assert cfg["composizione"]["Benchmark test"] == {BENCH: 1.0}
    assert cfg["orizzonti"] == [2, 4]


def test_errori_chiari(cfg_piccola):
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"][0]["titoli"] = {"AAA.MI": 50, "BBB.DE": None}
    with pytest.raises(ErroreConfig, match="alcuni titoli hanno il peso"):
        C.prepara(cfg)
    cfg = copy.deepcopy(cfg_piccola)
    cfg["rendimento_atteso"] = {"metodo": "personalizzato", "personalizzato": {"Uno": 0.05}}
    with pytest.raises(ErroreConfig, match="«Due»"):
        C.prepara(cfg)
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"][1]["nome"] = "Uno"
    with pytest.raises(ErroreConfig, match="stesso nome"):
        C.prepara(cfg)


def test_ticker_inesistente(cfg_piccola, finto_yahoo, tmp_path):
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"][0]["titoli"] = ["AAA.MI", "NONESISTE"]
    cfg = C.prepara(cfg)
    with pytest.raises(D.ErroreDati, match="NONESISTE"):
        analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=finto_yahoo, log=lambda *a: None)


# ---------------------------------------------------------------- portafogli misti
def test_portafoglio_misto(cfg_piccola):
    cfg = copy.deepcopy(cfg_piccola)
    cfg["portafogli"].append({"nome": "Satellite", "titoli": {"benchmark": 80, "Uno": 20}})
    cfg["portafogli"].append({"nome": "Doppio", "titoli": {"Satellite": 50, "Due": 50}})
    cfg = C.prepara(cfg)
    assert cfg["composizione"]["Satellite"] == pytest.approx({BENCH: 0.8, "AAA.MI": 0.1, "BBB.DE": 0.1})
    assert cfg["composizione"]["Doppio"] == pytest.approx({BENCH: 0.4, "AAA.MI": 0.05 + 0.2, "BBB.DE": 0.05, "CCC": 0.3})
    assert C.misto(cfg, "Satellite") and not C.misto(cfg, "Uno")
    cfg2 = copy.deepcopy(cfg_piccola)
    cfg2["portafogli"] = [{"nome": "X", "titoli": ["Y"]}, {"nome": "Y", "titoli": ["X"]}]
    with pytest.raises(ErroreConfig, match="circolo"):
        C.prepara(cfg2)


# ---------------------------------------------------------------- metodi di rendimento atteso
def _R_sintetico(beta=1.5, n=2600):
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2010-01-01", periods=n)
    b = rng.normal(0.0003, 0.01, n)
    return pd.DataFrame({BENCH: b, "X": beta * b + rng.normal(0, 0.005, n)}, index=idx)


def test_beta_stimato_e_rendimento_atteso(cfg_piccola):
    beta = analisi.stima_beta(_R_sintetico(1.5))
    assert beta[BENCH] == 1.0
    assert beta["X"] == pytest.approx(1.5, abs=0.05)
    cfg = C.prepara(copy.deepcopy(cfg_piccola))  # metodo beta di default: 2% + beta x 4%
    mu = analisi.rendimento_colonne(cfg, [("P", "X"), ("P", BENCH)], beta={"X": 1.5, BENCH: 1.0})
    assert mu == pytest.approx([0.02 + 1.5 * 0.04, 0.06])


def test_metodi_uguale_personalizzato_storico(cfg_piccola):
    cols = [("Uno", "AAA.MI"), ("Due", "CCC"), ("Benchmark test", BENCH)]
    beta = {"AAA.MI": 1.3, "CCC": 0.7, BENCH: 1.0}
    cfg = copy.deepcopy(cfg_piccola)
    cfg["rendimento_atteso"] = {"metodo": "uguale", "valore_uguale": 0.05}
    assert analisi.rendimento_colonne(C.prepara(cfg), cols, beta=beta) == pytest.approx([0.05] * 3)
    cfg["rendimento_atteso"] = {"metodo": "personalizzato", "personalizzato": {"Uno": 0.04, "due": 0.07, "benchmark": 0.055}}
    assert analisi.rendimento_colonne(C.prepara(cfg), cols, beta=beta) == pytest.approx([0.04, 0.07, 0.055])
    cfg["rendimento_atteso"] = {"metodo": "storico"}
    c = C.prepara(cfg)
    assert analisi.rendimento_colonne(c, cols, beta=beta) is None
    M = np.random.default_rng(1).normal(0.001, 0.01, (500, 3))
    assert np.array_equal(analisi.prepara_M(c, M, cols, None), M)  # storico: dati non toccati


def test_ricentratura_con_metodo_beta_da_il_rendimento_atteso(cfg_piccola):
    cfg = C.prepara(copy.deepcopy(cfg_piccola))
    cols = [("P", "X"), ("P", BENCH)]
    mu = analisi.rendimento_colonne(cfg, cols, beta={"X": 1.5, BENCH: 1.0})
    M = analisi.prepara_M(cfg, np.random.default_rng(2).normal(0.002, 0.02, (1000, 2)), cols, mu)
    assert (1 + M[:, 0].mean()) ** 252 - 1 == pytest.approx(0.08, abs=1e-12)
    assert (1 + M[:, 1].mean() + 0.002 / 252) ** 252 - 1 == pytest.approx(0.06, abs=1e-12)


# ---------------------------------------------------------------- end-to-end
def test_end_to_end_configurazione_piccola(cfg_piccola, finto_yahoo, tmp_path):
    cfg = C.prepara(copy.deepcopy(cfg_piccola))
    passi = []
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=finto_yahoo, log=lambda *a: None,
                         progresso=lambda f, m: passi.append(f))
    assert set(ris["sim"]) == {"A", "B"}
    assert ris["periodi"]["A"][0] >= pd.Timestamp("2016-01-01")      # BBB.DE nasce nel 2016
    assert ris["periodi"]["B"][0] < pd.Timestamp("2013-01-01")
    tab = ris["sim"]["A"]["orizzonti"][4]
    assert list(tab.columns) == ["Uno", "Due", "Benchmark test"]
    assert (tab.loc["Totale versato"] == 1000).all()
    assert ((tab.loc["Prob. sotto il versato"] >= 0) & (tab.loc["Prob. sotto il versato"] <= 1)).all()
    assert len(ris["stress"]["A"]) == 3 * 2 + 2       # 2 scenari x 3 portafogli + singolo titolo x 2
    assert set(ris["idio"]) == {"A", "B"}
    assert passi[-1] == 1.0 and passi == sorted(passi)
    # il beta di AAA (costruito con 1,5) deve uscire vicino a 1,5
    assert ris["beta"]["AAA.MI"] == pytest.approx(1.5, abs=0.1)
    # la seconda esecuzione usa la cache (nessun download)
    analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=lambda t: (_ for _ in ()).throw(AssertionError(t)),
                   log=lambda *a: None, n=100)
