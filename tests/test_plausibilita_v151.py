"""v1.5.1, tappa 1: il rendimento simulato coincide con quello atteso anche quando i giorni sono legati tra loro,
un titolo entra a metà periodo o ha buchi nei dati. Tutto offline (dati sintetici)."""

import copy

import numpy as np
import pandas as pd
import pytest
import yaml

import analisi
import configurazione as C
import rendimento as RE
import simula as S

GIORNI = pd.bdate_range("2012-01-02", "2024-12-31")
THETA = -0.5  # legame negativo tra giorni vicini (dopo un calo, un rimbalzo): correlazione tra giorni consecutivi ≈ -0,4


def _ma1(rng, n, vol, media=0.0003):
    """Rendimenti con legame tra giorni consecutivi: e_t + THETA * e_(t-1)."""
    e = rng.normal(0, vol, n + 1)
    return media + e[1:] + THETA * e[:-1]


# ------------------------------------------------------------------ la correzione in sé
def test_crescita_attesa_esatta_coincide_con_la_simulazione():
    """La formula esatta della crescita con i blocchi coincide con la media dei percorsi simulati."""
    rng = np.random.default_rng(5)
    X = np.column_stack([_ma1(rng, 3000, 0.01), _ma1(rng, 3000, 0.006)])
    gen = S.Bootstrap(X, 20)
    gen.prepara(40000, 63, np.random.default_rng(1))
    G = np.prod(1.0 + gen.M[gen.idx], axis=1)  # (percorsi, colonne): crescita su 63 giorni
    esatta = S.crescita_attesa_bootstrap(X, 20, giorni=63)
    assert np.allclose(G.mean(0), esatta, atol=4 * G.std(0).max() / np.sqrt(40000))
    # a un anno la crescita attesa è più bassa di (1+media)^252 perché il legame tra i giorni è negativo
    assert (S.crescita_attesa_bootstrap(X, 20) < (1 + X.mean(0)) ** 252 - 0.003).all()


def test_correzione_riporta_la_crescita_al_rendimento_voluto():
    rng = np.random.default_rng(6)
    X = np.column_stack([_ma1(rng, 3000, 0.012), _ma1(rng, 3000, 0.008, 0.0005), rng.normal(0.0002, 0.01, 3000)])
    Xc, delta = S.allinea_media_composta(X, 20)
    bersaglio = (1 + X.mean(0)) ** 252
    assert np.allclose(S.crescita_attesa_bootstrap(Xc, 20), bersaglio, rtol=1e-9)
    # lo spostamento è piccolo e non tocca volatilità e correlazioni
    assert np.abs(delta * 252).max() < 0.05
    assert np.allclose(np.cov(Xc.T), np.cov(X.T))
    # con giorni indipendenti lo spostamento è quasi nullo (solo rumore del campione)
    assert abs(delta[2] * 252) < 0.01


def test_prima_della_correzione_il_primo_anno_era_sbagliato_dopo_no():
    """Simulazione completa di un portafoglio con giorni legati: media del primo anno vicina all'atteso solo dopo la correzione."""
    rng = np.random.default_rng(7)
    X = np.column_stack([_ma1(rng, 3000, 0.012), _ma1(rng, 3000, 0.010, 0.0004)])
    X = X - X.mean(0) + 0.0003
    porte = {"P": (np.array([0, 1]), np.array([0.5, 0.5]))}
    atteso = RE.atteso_netto_annuo(X.mean(0), np.array([0, 1]), np.array([0.5, 0.5]))
    Xc = S.allinea_media_composta(X, 20)[0]

    def anno1(M):
        r = S.simula(S.Bootstrap(M, 20), porte, 20000, 2, 1000, 0, 0.0, [1], 3)["_rend"]["P"]
        return r["anno1"], r["se_anno1"]

    prima, se = anno1(X)
    dopo, _ = anno1(Xc)
    assert prima < atteso - 5 * se  # senza correzione: errore evidente
    assert abs(dopo - atteso) < 4 * se + 0.002


def test_anno1_non_dipende_dai_versamenti():
    rng = np.random.default_rng(8)
    X = rng.normal(0.0003, 0.01, (2000, 2))
    porte = {"P": (np.array([0, 1]), np.array([0.5, 0.5]))}
    a = S.simula(S.Bootstrap(X, 20), porte, 3000, 2, 1000, 0, 0.001, [1], 3)["_rend"]["P"]["anno1"]
    b = S.simula(S.Bootstrap(X, 20), porte, 3000, 2, 1000, 200, 0.001, [1], 3)["_rend"]["P"]["anno1"]
    assert a == pytest.approx(b, abs=1e-12)


# ------------------------------------------------------------------ dati sintetici con legame tra giorni, ingressi tardivi, buchi
def _scaricatore():
    rng = np.random.default_rng(21)
    n = len(GIORNI)
    mercato = _ma1(rng, n, 0.008)

    def serie(beta, vol, inizio=None, buchi=()):
        r = beta * mercato + _ma1(rng, n, vol, 0.0)
        s = pd.Series(100 * np.cumprod(1 + r), index=GIORNI)
        for a, b in buchi:  # periodi senza quotazioni (il titolo non scambia)
            s = s[(s.index < a) | (s.index > b)]
        return s if inizio is None else s[s.index >= inizio]

    dati = {
        "BMK.AS": (serie(1.0, 0.001), "EUR", "ETF"),
        "^IDX": (serie(1.0, 0.001), "USD", "INDEX"),
        "AAA.MI": (serie(1.5, 0.012), "EUR", "EQUITY"),
        "BBB.DE": (serie(0.8, 0.010, inizio="2016-01-01"), "EUR", "EQUITY"),
        "NEW.MI": (serie(1.1, 0.014, inizio="2019-06-03"), "EUR", "EQUITY"),  # entra a metà periodo
        "GAP.MI": (serie(1.2, 0.013, buchi=[("2015-03-02", "2015-04-24"), ("2021-02-01", "2021-03-26")]), "EUR", "EQUITY"),  # buchi
        "EURUSD=X": (pd.Series(1.1 + 0.05 * np.sin(np.arange(n) / 200), index=GIORNI), "USD", "CURRENCY"),
    }

    def scarica(t):
        if t in dati:
            return dati[t][0].copy(), {"valuta": dati[t][1], "tipo": dati[t][2]}
        return pd.Series(dtype=float), {}

    return scarica


def _cfg(metodo, modello="storico"):
    c = {
        "nome": "plausibilità",
        "capitale_iniziale": 1000,
        "versamento_mensile": 0,
        "orizzonte_anni": 2,
        "orizzonti_intermedi": [1],
        "n_simulazioni": 4000,
        "seed": 99,
        "benchmark": {"nome": "Bmk", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01", "inizio_C": "2012-06-01"},
        "moduli": {"stress_test": False, "rischio_singolo_titolo": False, "confronto_modelli": False, "analisi_C": False, "verifica_convergenza": False},
        "rendimento_atteso": {"metodo": metodo, "tasso_privo_rischio": 0.02, "premio_mercato": 0.04, "valore_uguale": 0.06},
        "portafogli": [
            {"nome": "Ingresso tardivo", "titoli": {"AAA.MI": 40, "NEW.MI": 30, "BBB.DE": 30}},
            {"nome": "Con buchi", "titoli": ["AAA.MI", "GAP.MI", "BBB.DE"]},
        ],
        "modello_simulazione": modello,
    }
    if metodo == "personalizzato":
        c["rendimento_atteso"]["personalizzato"] = {"Ingresso tardivo": 0.07, "Con buchi": 0.05, "benchmark": 0.06}
    return C.prepara(c)


@pytest.mark.parametrize("metodo", ["beta", "uguale", "personalizzato", "storico"])
def test_plausibilita_storico_analisi_A_e_B_tutti_i_metodi(metodo, tmp_path):
    ris = analisi.esegui(_cfg(metodo), cartella_cache=str(tmp_path), scaricatore=_scaricatore(), log=lambda *a: None)
    assert set(ris["plausibilita"]) == {"A", "B"}
    assert ris["errore_plausibilita"] is None, ris["errore_plausibilita"]
    # B parte prima di A: vale anche con il titolo che entra a metà periodo e con i buchi
    assert ris["periodi"]["B"][0] < ris["periodi"]["A"][0]
    for a, df in ris["plausibilita"].items():
        assert df["ok"].all(), (a, df)


def test_senza_correzione_il_rendimento_simulato_era_troppo_basso(tmp_path, monkeypatch):
    """Prova di sensibilità: togliendo la correzione il rendimento simulato resta sotto l'atteso di oltre mezzo punto."""
    monkeypatch.setattr(analisi, "allinea_media_composta", lambda M, b: (M, None))
    cfg = _cfg("uguale")
    cfg["n_simulazioni"] = 8000
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=_scaricatore(), log=lambda *a: None, solo=["A"])
    scarti = ris["plausibilita"]["A"]["scarto"].astype(float)
    assert (scarti < -0.005).any()


def test_modello_a_fattori_plausibile(tmp_path):
    rng = np.random.default_rng(3)
    extra = {n: pd.Series(100 * np.cumprod(1 + _ma1(rng, len(GIORNI), 0.006, 0.0002)), index=GIORNI) for n in ("FX1", "FX2", "FX3")}
    base = _scaricatore()

    def scarica(t):
        if t in extra:
            return extra[t].copy(), {"valuta": "EUR", "tipo": "ETF"}
        return base(t)

    conf = {
        "inizio_storia": "2012-02-01",
        "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5},
        "fattori": [
            {"nome": "Mercato mondiale", "gruppo": "mercato", "lungo": "BMK.AS", "valuta": "EUR"},
            {"nome": "Tecnologia", "gruppo": "settori", "lungo": "FX1", "corto": "BMK.AS", "valuta": "EUR"},
            {"nome": "Growth contro value", "gruppo": "stile", "lungo": "FX2", "corto": "FX3", "valuta": "EUR"},
        ],
    }
    f = tmp_path / "fattori.yaml"
    f.write_text(yaml.safe_dump(conf))
    for metodo in ("beta", "storico"):
        c = copy.deepcopy(_cfg(metodo, "fattori"))
        c["fattori_file"] = str(f)
        ris = analisi.esegui(c, cartella_cache=str(tmp_path / f"c_{metodo}"), scaricatore=scarica, log=lambda *a: None)
        assert list(ris["plausibilita"]) == ["A"]
        assert ris["errore_plausibilita"] is None, ris["errore_plausibilita"]
