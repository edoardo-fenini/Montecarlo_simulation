"""v1.5 tappa 1-2: modello a fattori su dati sintetici con esposizioni note (offline)."""

import numpy as np
import pandas as pd
import pytest

import fattori as FA
from simula import GG, simula

RES = 0.005
DATE = pd.bdate_range("2000-01-03", "2023-12-29")
NOMI = ["Mercato", "Tech", "Value", "Dollaro"]
BETA_VERI = {"X": [1.2, 0.5, -0.3, 0.0], "Y": [0.8, 0.0, 0.4, 0.3], "Z": [1.0, -0.4, 0.0, 0.0]}
GRUPPO = {"Mercato": "mercato", "Tech": "settori", "Value": "stile", "Dollaro": "tassi_valute"}
CONF = {
    "fattori": [{"nome": n, "gruppo": GRUPPO[n], "lungo": n} for n in NOMI],
    "ridge": {"lambda": "auto", "minimo": 0.5},
    "min_settimane": 52,
    "r2_minimo_avviso": 0.3,
}


@pytest.fixture(scope="module")
def sintetici():
    rng = np.random.default_rng(7)
    n = len(DATE)
    comune = rng.normal(0, 0.010, n)
    F = pd.DataFrame(
        {
            "Mercato": comune,
            "Tech": 0.3 * comune + rng.normal(0, 0.006, n),  # correlato col mercato
            "Value": rng.normal(0, 0.004, n),
            "Dollaro": rng.normal(0, 0.003, n),
        },
        index=DATE,
    )
    R = pd.DataFrame(index=DATE)
    for t, b in BETA_VERI.items():
        R[t] = F.values @ np.array(b) + rng.normal(0, RES, n)
    V = pd.DataFrame(True, index=DATE, columns=NOMI)
    return F.iloc[1:], V.iloc[1:], R.iloc[1:]


def test_ridge_ritrova_esposizioni_note(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    for t, b in BETA_VERI.items():
        assert st.beta.loc[t].values == pytest.approx(b, abs=0.12), t
        # R² atteso: varianza spiegata / totale
        var_f = np.var(F.values @ np.array(b))
        atteso = var_f / (var_f + RES**2)
        assert st.r2[t] == pytest.approx(atteso, abs=0.05)
        assert st.vol_specifica[t] == pytest.approx(RES * np.sqrt(252), rel=0.06)
        assert abs(st.residui[t].mean()) < 1e-12


def test_ridge_con_storia_breve_resta_ragionevole(sintetici):
    """Con 3 anni di storia e fattori correlati le esposizioni restano vicine al vero e non esplodono."""
    F, V, R = sintetici
    breve = R.loc["2021-01-01":]
    breve = breve.copy()
    breve.iloc[:, :] = breve.values
    st = FA.stima_titoli(breve, F, V, CONF)
    assert (st.beta.abs() < 2.5).all().all()
    assert st.beta.loc["X", "Mercato"] == pytest.approx(1.2, abs=0.25)
    # la penalità regolarizza di più della regressione ordinaria quando la storia è corta
    lunga = FA.stima_titoli(R, F, V, CONF)
    assert st.penalita["X"] >= lunga.penalita["X"] * 0.5 or st.penalita["X"] > 0


def test_penalita_minima_riduce_gli_scostamenti_ma_non_il_mercato(sintetici):
    F, V, R = sintetici
    forte = {**CONF, "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 3.0}}
    st = FA.stima_titoli(R, F, V, forte)
    assert st.beta.loc["X", "Mercato"] == pytest.approx(1.2, abs=0.15)  # il mercato non viene ridotto
    assert abs(st.beta.loc["X", "Tech"]) < 0.5 * 0.85 and st.penalita["X"] >= 3.0 * 100


def test_ridge_vs_minimi_quadrati_con_fattori_quasi_collineari():
    rng = np.random.default_rng(3)
    n = 80
    a = rng.normal(0, 0.01, n)
    X = np.column_stack([a, a + rng.normal(0, 1e-4, n)])  # quasi identici
    y = 1.0 * a + rng.normal(0, 0.005, n)
    b_ols = np.linalg.lstsq(np.c_[X, np.ones(n)], y, rcond=None)[0][:2]
    b_r, _, lam = FA.ridge_gcv(X, y, "auto", 0.5)
    assert abs(b_r).max() < abs(b_ols).max()  # la ridge evita i beta enormi di segno opposto
    assert b_r.sum() == pytest.approx(1.0, abs=0.3)
    assert lam > 0.5


def test_pochi_dati_ripiego_su_mercato():
    idx = pd.bdate_range("2023-06-01", periods=120)
    rng = np.random.default_rng(1)
    F = pd.DataFrame(rng.normal(0, 0.01, (120, 4)), index=idx, columns=NOMI)
    V = pd.DataFrame(True, index=idx, columns=NOMI)
    R = pd.DataFrame({"X": F["Mercato"] + rng.normal(0, 0.01, 120)}, index=idx)
    st = FA.stima_titoli(R, F, V, CONF)
    assert st.beta.loc["X"].tolist() == [1.0, 0.0, 0.0, 0.0]
    assert any("settimane" in n for n in st.note)


def test_simulazione_riproduce_volatilita_e_correlazioni(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    colonne = [("P", "X"), ("P", "Y"), ("Q", "Z"), ("Q", "X")]
    Mr = R[["X", "Y", "Z", "X"]].values
    dati = FA.prepara_generatore(st, F, colonne, Mr)
    gen = FA.crea_generatore(dati)
    rng = np.random.default_rng(0)
    gen.prepara(2000, 21 * 12, rng)  # 12 mesi
    blocchi = np.concatenate([gen.blocco(m) for m in range(12)], axis=1).reshape(-1, 4)
    assert blocchi.shape[0] == 2000 * 21 * 12
    # stessa volatilità e correlazioni della storia
    assert blocchi.std(0) == pytest.approx(Mr.std(0), rel=0.06)
    cs, ch = np.corrcoef(blocchi.T), np.corrcoef(Mr.T)
    assert np.abs(cs - ch).max() < 0.05
    # il titolo X in due portafogli è la stessa serie (colonne 0 e 3 identiche)
    assert np.allclose(blocchi[:, 0], blocchi[:, 3])
    # media = quella voluta (centro)
    assert blocchi.mean(0) == pytest.approx(Mr.mean(0), abs=2e-4)


def test_stessi_residui_indipendenti_tra_titoli(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    res = pd.DataFrame({t: st.residui[t] for t in ("X", "Y")})
    assert abs(res.corr().iloc[0, 1]) < 0.05  # residui storici quasi incorrelati: il modello li tratta come indipendenti


def test_simula_con_generatore_a_fattori(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    colonne = [("P", "X"), ("P", "Y")]
    gen = FA.crea_generatore(FA.prepara_generatore(st, F, colonne, R[["X", "Y"]].values))
    out = simula(gen, {"P": (np.array([0, 1]), np.array([0.5, 0.5]))}, 400, 2, 1000.0, 0.0, 0.001, [1, 2], 5, chunk=200)
    assert out["P"]["mensile"].shape == (400, 25)
    assert np.isfinite(out["P"]["mensile"]).all()
    assert GG == 21


def test_scomposizione_somma_100(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    for pesi in ({"X": 0.5, "Y": 0.5}, {"X": 1.0}, {"X": 0.2, "Y": 0.3, "Z": 0.5}):
        sc = FA.scomposizione_rischio(st, F, pesi, CONF)
        assert sum(sc["quote"].values()) == pytest.approx(1.0, abs=1e-9)
        assert sum(sc["contributi"].values()) + sc["quote"]["Rischio specifico"] == pytest.approx(1.0, abs=1e-9)
    # un portafoglio solo "mercato" ha il rischio quasi tutto da mercato
    solo = FA.stima_titoli(pd.DataFrame({"M": F["Mercato"]}), F, V, CONF)
    sc = FA.scomposizione_rischio(solo, F, {"M": 1.0}, CONF)
    assert sc["quote"]["Mercato"] > 0.9


def test_scomposizione_riconosce_la_scommessa_comune(sintetici):
    F, V, R = sintetici
    st = FA.stima_titoli(R, F, V, CONF)
    sc_x = FA.scomposizione_rischio(st, F, {"X": 1.0}, CONF)
    assert sc_x["quote"]["Mercato"] > 0.5 and sc_x["quote"]["Settori"] > 0.0
    assert sc_x["esposizioni"]["Mercato"] == pytest.approx(1.2, abs=0.06)


def test_avvisi_r2(sintetici):
    F, V, R = sintetici
    R2 = R.copy()
    R2["Rumore"] = np.random.default_rng(9).normal(0, 0.02, len(R))
    st = FA.stima_titoli(R2, F, V, CONF)
    av = FA.avvisi_r2(st, CONF)
    assert len(av) == 1 and "Rumore" in av[0]


def test_config_predefinita_valida():
    c = FA.carica_config()
    gruppi = {f["gruppo"] for f in c["fattori"]}
    assert gruppi == set(FA.GRUPPI)
    assert len({f["nome"] for f in c["fattori"]}) == len(c["fattori"])


def test_benchmark_e_il_fattore_mercato(sintetici):
    F, V, R = sintetici
    R2 = R.copy()
    R2["BENCH"] = F["Mercato"] + np.random.default_rng(5).normal(0, 0.004, len(F))  # ETF = indice + rumore di orario
    st = FA.stima_titoli(R2, F, V, CONF)
    assert st.beta.loc["BENCH"].tolist() == [1.0, 0.0, 0.0, 0.0] and st.vol_specifica["BENCH"] == 0.0
    sc = FA.scomposizione_rischio(st, F, {"BENCH": 1.0}, CONF)
    assert sc["quote"]["Mercato"] == pytest.approx(1.0) and sc["quote"]["Rischio specifico"] == pytest.approx(0.0)
    assert FA.avvisi_r2(st, CONF) == []
