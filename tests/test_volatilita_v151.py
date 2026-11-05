"""v1.5.1, tappa 2: la volatilità annua simulata coincide con quella storica della stessa serie (misura mensile, che tiene conto del
legame tra giorni vicini) e i valori sbagliati isolati dell'indice di mercato vengono corretti. Offline."""

import numpy as np
import pandas as pd

import fattori as FA
import metriche as ME
import simula as S


def _serie_con_legame(n=4000, vol=0.008, theta=-0.15, seed=1):
    """Rendimenti giornalieri con correlazione negativa tra giorni consecutivi (come un indice convertito in euro con l'orario del cambio sfasato)."""
    e = np.random.default_rng(seed).normal(0, vol, n + 1)
    return 0.0003 + e[1:] + theta * e[:-1]


def test_volatilita_simulata_del_fattore_mercato_coincide_con_la_storica():
    r = _serie_con_legame()
    storica = ME.vol_annua(r)
    # generatore a fattori con il solo fattore mercato (esposizione 1, nessun residuo): è il caso del benchmark
    gen = FA.Fattoriale(r[:, None], np.array([[1.0]]), [np.zeros(10)], np.array([0]), np.array([r.mean()]), blocco=20)
    res = S.simula(gen, {"mercato": (np.array([0]), np.array([1.0]))}, 4000, 3, 1000, 0, 0.0, [1], 5)
    assert abs(res["mercato"]["vol"] / storica - 1) < 0.07, (res["mercato"]["vol"], storica)
    # con i giorni legati la vecchia misura (giornaliera × √252) sovrastimava di di oltre il 12% (nei dati veri di quasi il 20%): era il «19% invece di 16%»
    assert res["mercato"]["vol_giorn"] > 1.12 * storica
    assert ME.stat_storiche(r)["vol_giorn"] > 1.12 * storica


def test_con_giorni_indipendenti_le_due_misure_coincidono():
    r = np.random.default_rng(2).normal(0.0003, 0.01, 4000)
    assert abs(ME.vol_annua(r) / (r.std(ddof=1) * np.sqrt(252)) - 1) < 0.05
    res = S.simula(S.Bootstrap(r[:, None], 20), {"P": (np.array([0]), np.array([1.0]))}, 4000, 3, 1000, 0, 0.0, [1], 5)
    assert abs(res["P"]["vol"] / res["P"]["vol_giorn"] - 1) < 0.05
    assert abs(res["P"]["vol"] / ME.vol_annua(r) - 1) < 0.07


def test_poche_osservazioni_ripiegano_sulla_misura_giornaliera():
    r = np.random.default_rng(3).normal(0, 0.01, 100)
    assert ME.vol_annua(r) == ME.stat_storiche(r)["vol_giorn"]


def _indice_e_riferimento(n=1500):
    idx = pd.bdate_range("2000-01-03", periods=n)
    rng = np.random.default_rng(4)
    q = rng.normal(0.0003, 0.01, n)
    r = 0.8 * q + rng.normal(0, 0.003, n)
    return idx, q, r


def test_togli_picchi_corregge_il_valore_sbagliato_isolato_e_conserva_il_livello():
    idx, q, r = _indice_e_riferimento()
    ref = pd.Series(100 * np.cumprod(1 + q), index=idx)
    sano = pd.Series(100 * np.cumprod(1 + r), index=idx)
    r2 = r.copy()
    r2[700] += 0.12   # valore sbagliato: +12% per un giorno...
    r2[701] -= 0.12   # ...e il giorno dopo si annulla
    guasto = pd.Series(100 * np.cumprod(1 + r2), index=idx)
    pulito, corrette = FA.togli_picchi(guasto, ref, 15.0)
    assert corrette == [idx[700]]
    # dopo i due giorni il livello è quello dell'indice guasto (che coincide con quello sano a meno del rapporto dei due giorni)
    assert pulito.iloc[702:].div(guasto.iloc[702:]).round(10).nunique() == 1
    rp = pulito.pct_change().dropna()
    assert rp.abs().max() < 0.05  # niente più salti del 12%
    assert abs(rp.std() / sano.pct_change().dropna().std() - 1) < 0.1


def test_togli_picchi_non_tocca_i_giorni_veri_di_forte_volatilita():
    idx, q, r = _indice_e_riferimento()
    q[500], q[501], q[502] = -0.09, 0.06, -0.08   # crisi: forti oscillazioni di segno opposto, ma confermate dal riferimento
    r[500], r[501], r[502] = 0.8 * -0.09, 0.8 * 0.06, 0.8 * -0.08
    ref = pd.Series(100 * np.cumprod(1 + q), index=idx)
    ind = pd.Series(100 * np.cumprod(1 + r), index=idx)
    pulito, corrette = FA.togli_picchi(ind, ref, 15.0)
    assert corrette == [] and pulito.equals(ind)


def test_serie_fattori_con_pulizia_mercato(tmp_path):
    """La pulizia è applicata dal file dei fattori e segnalata."""
    import dati as D

    idx, q, r = _indice_e_riferimento(1200)
    r[600] += 0.12
    r[601] -= 0.12
    dati = {
        "IND": (pd.Series(100 * np.cumprod(1 + r), index=idx), {"valuta": "EUR", "tipo": "INDEX"}),
        "RIF": (pd.Series(100 * np.cumprod(1 + q), index=idx), {"valuta": "EUR", "tipo": "ETF"}),
    }
    arch = D.Archivio(str(tmp_path), scaricatore=lambda t: (dati[t][0].copy(), dict(dati[t][1])), log=lambda *a: None)
    conf = {
        "inizio_storia": pd.Timestamp("2000-01-03"),
        "fattori": [{"nome": "Mercato", "gruppo": "mercato", "lungo": "IND", "valuta": "EUR"}],
        "pulizia_mercato": {"riferimento": "RIF", "valuta": "EUR", "soglia": 15},
    }
    messaggi = []
    F, _, info = FA.serie_fattori(conf, arch, log=messaggi.append)
    assert info.attrs["picchi_corretti"] == [idx[600].date().isoformat()]
    assert F["Mercato"].abs().max() < 0.05 and any("corretti" in m for m in messaggi)
