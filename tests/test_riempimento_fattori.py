"""v1.5.1, tappa 6: fattori con storia breve riempiti in modo condizionato al mercato invece di 0. Dati sintetici, offline."""

import numpy as np
import pandas as pd
import pytest

import dati as D
import fattori as FA

N, INIZIO = 3000, 1800  # il fattore esiste solo dal giorno INIZIO


def _mercato_con_crisi(seed=1):
    rng = np.random.default_rng(seed)
    vol = np.full(N, 0.006)
    vol[300:500] = 0.03  # crisi nel periodo in cui il fattore non esiste ancora
    return rng.normal(0, 1, N) * vol


def _fattore(m, seed=2, b=0.7, vol_res=0.004):
    rng = np.random.default_rng(seed)
    f = b * m + rng.normal(0, vol_res, N)
    f[:INIZIO] = np.nan
    return f


def _dati():
    idx = pd.bdate_range("2000-01-03", periods=N)
    m = _mercato_con_crisi()
    F = pd.DataFrame({"Mercato": m, "Mom": _fattore(m)}, index=idx)
    V = F.notna()
    return F, V, m


def test_riempimento_segue_il_mercato_nella_crisi():
    F, V, m = _dati()
    Fr, info = FA.riempi_condizionato(F, V, "Mercato")
    f = Fr["Mom"].values
    assert not np.isnan(f).any() and info["Mom"][0] == INIZIO
    assert abs(info["Mom"][1] - 0.7) < 0.05  # la beta sul mercato stimata nel periodo vero
    assert abs(np.polyfit(m[:INIZIO], f[:INIZIO], 1)[0] - 0.7) < 0.06  # nel periodo riempito il fattore ha la stessa sensibilità al mercato
    crisi, calma = f[300:500].std(), f[600:1000].std()
    assert crisi > 3 * calma  # con il mercato in crisi il fattore si muove molto (con 0 non si muoverebbe)
    assert np.allclose(Fr["Mercato"], F["Mercato"]) and np.allclose(Fr["Mom"][INIZIO:], F["Mom"][INIZIO:])  # i dati veri non cambiano


def test_riempimento_e_riproducibile_e_rispetta_poca_storia():
    F, V, _ = _dati()
    a, _ = FA.riempi_condizionato(F, V, "Mercato")
    b, _ = FA.riempi_condizionato(F, V, "Mercato")
    assert a.equals(b)
    corto = F.copy()
    corto.iloc[: N - 100, 1] = np.nan  # solo 100 giorni veri: troppo pochi per stimare la relazione
    out, info = FA.riempi_condizionato(corto, corto.notna(), "Mercato")
    assert info == {} and out["Mom"].isna().sum() == N - 100  # resta da riempire con 0 (come prima)


def test_serie_fattori_opzione_zero_o_condizionato(tmp_path):
    idx = pd.bdate_range("2000-01-03", periods=N)
    m = _mercato_con_crisi()
    prezzi = {
        "MKT": pd.Series(100 * np.cumprod(1 + m), index=idx),
        "LATE": pd.Series(np.nan, index=idx),
    }
    f = _fattore(m)
    prezzi["LATE"] = pd.Series(100 * np.cumprod(1 + np.nan_to_num(f, nan=0.0)), index=idx)[INIZIO:]
    arch = D.Archivio(str(tmp_path), scaricatore=lambda t: (prezzi[t].copy(), {"valuta": "EUR", "tipo": "ETF"}), log=lambda *a: None)

    def conf(modo):
        return {
            "inizio_storia": pd.Timestamp("2000-01-03"),
            "riempimento_fattori": modo,
            "fattori": [
                {"nome": "Mercato", "gruppo": "mercato", "lungo": "MKT", "valuta": "EUR"},
                {"nome": "Mom", "gruppo": "stile", "lungo": "LATE", "valuta": "EUR"},
            ],
        }

    Fz, Vz, _ = FA.serie_fattori(conf("zero"), arch, log=lambda *a: None)
    Fc, Vc, info = FA.serie_fattori(conf("condizionato"), arch, log=lambda *a: None)
    assert (Fz["Mom"].iloc[: INIZIO - 5] == 0).all()
    assert Fc["Mom"].iloc[: INIZIO - 5].abs().sum() > 0 and Fc["Mom"].iloc[300:500].std() > 0.01
    assert Vz.equals(Vc) and not Vc["Mom"].iloc[: INIZIO - 5].any()  # la maschera dei dati veri non cambia: le regressioni usano solo dati veri
    assert "Mom" in info.attrs["riempiti"]
    # le stime dei titoli ignorano i valori riempiti
    st = pd.DataFrame({"X": 0.9 * m[1:] + np.random.default_rng(3).normal(0, 0.01, N - 1)}, index=Fz.index)
    cf = {"fattori": [{"nome": "Mercato", "gruppo": "mercato"}, {"nome": "Mom", "gruppo": "stile"}], "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5}, "min_settimane": 52, "r2_minimo_avviso": 0.3}
    sz = FA.stima_titoli(st, Fz, Vz, cf, ["X"])
    sc = FA.stima_titoli(st, Fc, Vc, cf, ["X"])
    assert np.allclose(sz.beta.values, sc.beta.values) and np.allclose(sz.residui["X"], sc.residui["X"])


def test_configurazione_riempimento_fattori(tmp_path):
    p = tmp_path / "f.yaml"
    base = "fattori:\n  - {nome: M, gruppo: mercato, lungo: X}\n"
    p.write_text(base)
    assert FA.carica_config(str(p))["riempimento_fattori"] == "condizionato"  # default
    p.write_text(base + "riempimento_fattori: zero\n")
    assert FA.carica_config(str(p))["riempimento_fattori"] == "zero"
    p.write_text(base + "riempimento_fattori: boh\n")
    with pytest.raises(FA.ErroreConfig, match="riempimento_fattori"):
        FA.carica_config(str(p))
