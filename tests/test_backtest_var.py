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
    assert set(t["modello"]) == {"storico", "fattori", "fattori (1.5.0)"} and set(t["livello"]) == {0.95, 0.99}
    assert (t["giorni"] > 1000).all()
    # i dati sono generati da un modello a fattori stabile: il modello a fattori non deve essere rifiutato al 95%
    r = t[(t["modello"] == "fattori") & (t["livello"] == 0.95)]
    assert (r["semaforo"] != "rosso").all()
    assert FA.GRUPPI


# ------------------------------------------------------------------ v1.5.1: VaR a breve termine che segue il regime (EWMA, code grasse)
def test_ewma_usa_solo_il_passato_e_converge():
    rng = np.random.default_rng(10)
    X = rng.normal(0, 0.01, (3000, 2))
    S = BT.covarianze_ewma(X, 0.97)
    Y = X.copy()
    Y[1500:] *= 5  # cambiare il futuro non cambia il valore di oggi
    assert np.allclose(S[:1500], BT.covarianze_ewma(Y, 0.97)[:1500])
    assert abs(np.sqrt(S[-1][0, 0]) - 0.01) < 0.004
    v = BT.varianza_ewma(X[:, 0], 0.97)
    assert np.allclose(v[:1500], BT.varianza_ewma(Y[:, 0], 0.97)[:1500]) and abs(np.sqrt(v[-1]) - 0.01) < 0.004


def test_ewma_segue_il_regime_e_la_storia_lunga_no():
    rng = np.random.default_rng(11)
    X = np.concatenate([rng.normal(0, 0.03, 1000), rng.normal(0, 0.006, 1000)])  # crisi, poi calma
    ewma = np.sqrt(BT.varianza_ewma(X, 0.97))
    assert ewma[-1] < 0.01  # dopo la crisi il rischio stimato è tornato basso
    assert X[:1999].std() > 0.02  # la storia lunga lo vedrebbe ancora a oltre il doppio


def test_stima_t_riconosce_code_grasse_e_normale():
    rng = np.random.default_rng(12)
    nu, scala = BT.stima_t(rng.standard_t(5, 3000) * 0.5)
    assert 3.5 < nu < 8 and abs(scala - 0.5) < 0.08
    nu_n, _ = BT.stima_t(rng.normal(0, 1, 3000))
    assert nu_n > 20  # normale: gradi di libertà alti (VaR praticamente normale)
    piccolo = rng.normal(0, 1, 20)  # meno di 100 osservazioni: normale con la deviazione standard dei dati
    assert BT.stima_t(piccolo) == (BT.GDL_MAX, float(piccolo.std()))


def test_modello_a_fattori_di_breve_termine_e_meno_prudente_con_mercato_calmo():
    """Mercato molto agitato nei primi anni e calmo dopo: il VaR della 1.5.0 (storia lunga) è troppo prudente, quello nuovo no."""
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2000-01-03", "2013-12-31")
    n = len(idx)
    vol = np.where(np.arange(n) < 1300, 0.022, 0.007)  # 2000-2005 turbolento, poi calma
    F = pd.DataFrame({"Mercato": rng.normal(0, 1, n) * vol, "Tech": rng.normal(0, 0.003, n)}, index=idx)
    V = pd.DataFrame(True, index=idx, columns=F.columns)
    sub = idx[idx >= "2008-01-01"]
    M = np.column_stack([F.loc[sub, "Mercato"] * 1.1 + rng.normal(0, 0.004, len(sub)), F.loc[sub, "Mercato"] + rng.normal(0, 0.001, len(sub))])
    colonne, porte = [("P", "X"), ("BENCH", "BENCH")], {"P": (np.array([0]), np.array([1.0])), "BENCH": (np.array([1]), np.array([1.0]))}
    conf = {
        "fattori": [{"nome": "Mercato", "gruppo": "mercato"}, {"nome": "Tech", "gruppo": "settori"}],
        "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5},
        "min_settimane": 52,
        "r2_minimo_avviso": 0.3,
    }
    t = BT.esegui(M, porte, colonne, sub, F, V, conf, log=lambda *a: None)["tabella"]
    for serie in ("P", "BENCH"):
        r = t[(t["serie"] == serie) & (t["livello"] == 0.95)].set_index("modello")
        attesi = r.loc["storico", "attesi"]
        assert r.loc[BT.VECCHIO, "sforamenti"] < 0.5 * attesi, (serie, r["sforamenti"].to_dict())  # troppo prudente (pochi sforamenti)
        assert 0.6 * attesi < r.loc["fattori", "sforamenti"] < 1.6 * attesi, (serie, r["sforamenti"].to_dict(), attesi)


def test_prima_e_dopo_nel_report():
    import report_fattori as RF

    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2000-01-03", "2013-12-31")
    n = len(idx)
    F = pd.DataFrame({"Mercato": rng.normal(0, 0.01, n), "Tech": rng.normal(0, 0.005, n)}, index=idx)
    V = pd.DataFrame(True, index=idx, columns=F.columns)
    sub = idx[idx >= "2008-01-01"]
    M = np.column_stack([F.loc[sub, "Mercato"] + rng.normal(0, 0.005, len(sub))])
    conf = {"fattori": [{"nome": "Mercato", "gruppo": "mercato"}, {"nome": "Tech", "gruppo": "settori"}], "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5}, "min_settimane": 52, "r2_minimo_avviso": 0.3}
    bt = BT.esegui(M, {"P": (np.array([0]), np.array([1.0]))}, [("P", "X")], sub, F, V, conf, log=lambda *a: None, lam=0.95)
    assert bt["lambda"] == 0.95
    blocchi = RF.blocchi_backtest({"backtest": bt})
    testo = str(blocchi)
    assert "prima e dopo la calibrazione" in testo and "Prima (1.5.0)" in testo and "lambda 0,95" in testo
    assert "il modello storico è più adatto al rischio di breve termine" in testo


def test_configurazione_lambda_ewma():
    import pytest

    import configurazione as C

    base = {"portafogli": [{"nome": "x", "titoli": ["A", "B"]}]}
    assert C.prepara(dict(base))["var_breve_termine"] == {"lambda_ewma": 0.97, "code_grasse": True}
    assert C.prepara({**base, "var_breve_termine": {"lambda_ewma": 0.94}})["var_breve_termine"]["lambda_ewma"] == 0.94
    for male in (0.5, 1.2, "boh"):
        with pytest.raises(C.ErroreConfig, match="lambda_ewma"):
            C.prepara({**base, "var_breve_termine": {"lambda_ewma": male}})
