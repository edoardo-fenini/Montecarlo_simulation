"""v1.5.1, tappa 5: nel modello a fattori i residui dei titoli sono ricampionati dalle stesse date (bootstrap congiunto): le correlazioni restano. Offline."""

import numpy as np
import pandas as pd

import fattori as FA
import simula as S

N = 3000


def _residui_correlati(rho=0.6, seed=1):
    rng = np.random.default_rng(seed)
    comune = rng.normal(0, 1, N)
    a = (np.sqrt(rho) * comune + np.sqrt(1 - rho) * rng.normal(0, 1, N)) * 0.01
    b = (np.sqrt(rho) * comune + np.sqrt(1 - rho) * rng.normal(0, 1, N)) * 0.01
    return a - a.mean(), b - b.mean()


def _gen(res_matrice, a, b):
    F = np.random.default_rng(2).normal(0, 0.01, (N, 1))  # un fattore che non spiega nulla (esposizioni 0): il rischio è tutto nei residui
    beta = np.zeros((2, 1))
    return FA.Fattoriale(F, beta, [a, b], np.array([0, 1]), np.array([0.0003, 0.0003]), blocco=20, res_matrice=res_matrice)


def _correlazione_simulata(gen, n=4000):
    gen.prepara(n, 21, np.random.default_rng(5))
    x = gen.blocco(0).reshape(-1, 2)
    return float(np.corrcoef(x.T)[0, 1])


def test_il_bootstrap_congiunto_conserva_la_correlazione_dei_residui():
    a, b = _residui_correlati(0.6)
    storica = float(np.corrcoef(a, b)[0, 1])
    congiunto = _correlazione_simulata(_gen(np.column_stack([a, b]), a, b))
    indipendente = _correlazione_simulata(_gen(None, a, b))
    assert abs(congiunto - storica) < 0.05, (congiunto, storica)
    assert abs(indipendente) < 0.06  # prima: titoli dello stesso settore tra loro scollegati


def test_titolo_senza_residui_in_alcune_date_ripesca_dalla_sua_storia():
    a, b = _residui_correlati(0.6)
    mb = np.column_stack([a, b])
    mb[: int(N * 0.6), 1] = np.nan  # il titolo B non quotava nel primo 60% delle date
    b_veri = b[int(N * 0.6) :]
    gen = _gen(mb, a, b_veri - b_veri.mean())
    gen.prepara(4000, 21, np.random.default_rng(6))
    x = gen.blocco(0).reshape(-1, 2)
    assert abs(x[:, 1].mean() - 0.0003) < 0.0004  # nessuna distorsione della media
    assert abs(x[:, 1].std() / b_veri.std() - 1) < 0.1  # stessa volatilità del titolo
    # la correlazione si conserva solo nelle date in cui B ha il residuo (circa il 40%)
    c = np.corrcoef(x.T)[0, 1]
    assert 0.1 < c < 0.4, c


def test_matrice_residui_allinea_le_date_dei_fattori():
    idx = pd.bdate_range("2010-01-04", periods=800)
    F = pd.DataFrame({"M": np.random.default_rng(3).normal(0, 0.01, 800)}, index=idx)
    dr = idx[300:]
    res = np.random.default_rng(4).normal(0, 0.005, len(dr))
    stima = FA.Stima(["M"], pd.DataFrame({"M": [1.0, 1.0]}, index=["TARDI", "BENCH"]), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float),
                     pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), {"TARDI": res, "BENCH": np.zeros(2)}, [], {},
                     date_residui={"TARDI": dr, "BENCH": pd.DatetimeIndex([])})  # fmt: skip
    m = FA.matrice_residui(stima, F, ["TARDI", "BENCH"])
    assert np.isnan(m[:300, 0]).all() and np.allclose(m[300:, 0], res)
    assert np.isnan(m[:, 1]).all()  # il benchmark non ha residuo
    assert FA.copertura_residui(stima, F) == {"TARDI": (800 - 300) / 800}


def test_il_bootstrap_congiunto_non_sposta_il_rendimento_atteso():
    """La correzione della media tiene conto dei residui che viaggiano con le date: 1 € cresce come voluto."""
    a, b = _residui_correlati(0.6)
    F = pd.DataFrame({"M": np.random.default_rng(2).normal(0, 0.01, N)}, index=pd.bdate_range("2005-01-03", periods=N))
    stima = FA.Stima(["M"], pd.DataFrame({"M": [0.0, 0.0]}, index=["A", "B"]), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float),
                     pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), {"A": a, "B": b}, [], {},
                     date_residui={"A": F.index, "B": F.index})  # fmt: skip
    colonne = [("P", "A"), ("P", "B")]
    Mr = np.full((100, 2), 0.0003)
    dati = FA.prepara_generatore(stima, F, colonne, Mr, 20, congiunti=True)
    gen = FA.crea_generatore(dati)
    porte = {"P": (np.array([0, 1]), np.array([0.5, 0.5]))}
    res = S.simula(gen, porte, 6000, 2, 1000, 0, 0.0, [1], 7)["_rend"]["P"]
    atteso = (1.0003) ** 252 - 1
    assert abs(res["anno1"] - atteso) < 4 * res["se_anno1"] + 0.003, (res["anno1"], atteso)
