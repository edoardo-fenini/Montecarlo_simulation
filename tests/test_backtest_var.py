"""v1.5 tappa 3: test di Kupiec e Christoffersen su casi noti, backtest su dati sintetici (offline)."""

import numpy as np
import pandas as pd
import pytest

import backtest_var as BT
import fattori as FA


def test_kupiec_casi_noti():
    lr, p = BT.kupiec(250, 10, 0.01)
    atteso = -2 * ((240 * np.log(0.99) + 10 * np.log(0.01)) - (240 * np.log(0.96) + 10 * np.log(0.04)))
    assert lr == pytest.approx(atteso) and p < 0.001
    lr, p = BT.kupiec(1000, 50, 0.05)  # esattamente quanti attesi
    assert lr == pytest.approx(0, abs=1e-9) and p == pytest.approx(1.0)
    assert BT.kupiec(100, 0, 0.01)[1] > 0.05  # zero sforamenti su 100 con p=1%: compatibile
    assert BT.kupiec(500, 0, 0.05)[1] < 0.001  # zero su 500 con p=5%: troppo prudente


def test_christoffersen_grappoli_contro_sparsi():
    sparsi = (np.random.default_rng(1).random(1000) < 0.05).astype(int)  # sforamenti casuali, indipendenti
    grappoli = np.zeros(1000, int)
    for i in range(10):
        grappoli[i * 100 : i * 100 + 5] = 1  # 50 sforamenti in 10 grappoli da 5
    assert BT.christoffersen(sparsi)[1] > 0.05
    assert BT.christoffersen(grappoli)[1] < 0.001
    assert BT.christoffersen(np.zeros(100, int)) == (0.0, 1.0)


def test_semaforo():
    assert BT.semaforo(0.5, 0.4) == "verde"
    assert BT.semaforo(0.03, 0.4) == "giallo"
    assert BT.semaforo(0.5, 0.004) == "rosso"


def test_modello_corretto_passa_il_test():
    rng = np.random.default_rng(4)
    r = rng.normal(0, 0.01, 3000)
    var = np.full(3000, 0.01 * 1.6449)
    v = BT.valuta(r, var, 0.95)
    assert v["semaforo"] == "verde" and abs(v["frequenza"] - 0.05) < 0.015
    v_sbagliato = BT.valuta(r, np.full(3000, 0.01 * 0.8), 0.95)  # VaR troppo basso: troppi sforamenti
    assert v_sbagliato["semaforo"] == "rosso"


def test_var_storico_usa_solo_il_passato():
    r = np.r_[np.zeros(600), -0.5, np.zeros(10)]
    v = BT.var_storico(r, 0.99, 504)
    assert np.isnan(v[:504]).all() and v[600] == pytest.approx(0, abs=1e-12)  # il crollo del giorno 600 non è nel VaR del giorno 600
    assert v[601] >= 0


def test_backtest_completo_su_dati_sintetici():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2000-01-03", "2013-12-31")
    n = len(idx)
    F = pd.DataFrame({"Mercato": rng.normal(0, 0.01, n), "Tech": rng.normal(0, 0.005, n)}, index=idx)
    V = pd.DataFrame(True, index=idx, columns=F.columns)
    sub = idx[idx >= "2008-01-01"]
    M = np.column_stack([F.loc[sub, "Mercato"] * 1.1 + F.loc[sub, "Tech"] * 0.4 + rng.normal(0, 0.008, len(sub)), F.loc[sub, "Mercato"] + rng.normal(0, 0.003, len(sub))])
    colonne, porte = [("P", "X"), ("BENCH", "BENCH")], {"P": (np.array([0]), np.array([1.0])), "BENCH": (np.array([1]), np.array([1.0]))}
    conf = {
        "fattori": [{"nome": "Mercato", "gruppo": "mercato"}, {"nome": "Tech", "gruppo": "settori"}],
        "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5},
        "min_settimane": 52,
        "r2_minimo_avviso": 0.3,
    }
    out = BT.esegui(M, porte, colonne, sub, F, V, conf, log=lambda *a: None)
    t = out["tabella"]
    assert set(t["modello"]) == {"storico", "fattori"} and set(t["livello"]) == {0.95, 0.99}
    assert (t["giorni"] > 1000).all()
    # i dati sono generati da un modello a fattori stabile: il modello a fattori non deve essere rifiutato al 95%
    r = t[(t["modello"] == "fattori") & (t["livello"] == 0.95)]
    assert (r["semaforo"] != "rosso").all()
    assert FA.GRUPPI
