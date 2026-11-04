"""v1.3.1 – stima GARCH: un risultato non convergente non viene mai usato in silenzio (senza internet)."""

import warnings

import numpy as np

import simula


def rendimenti_garch(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    h, e, out = 1e-4, 0.0, []
    for _ in range(n):
        h = 1e-6 + 0.08 * e**2 + 0.9 * h
        e = np.sqrt(h) * rng.normal()
        out.append(e)
    return np.array(out)


def test_serie_con_volatilita_variabile_stima_convergente_senza_avvisi():
    M = np.column_stack([rendimenti_garch(seed=1), rendimenti_garch(seed=2)])
    g = simula.Garch(M, ["AAA", "BBB"])
    assert g.avvisi == [] and g.ripieghi == []
    assert (g.par[:, 1] > 0.02).all() and (g.par[:, 1] + g.par[:, 2] < 1).all()


def test_serie_quasi_costante_ripiega_sulla_volatilita_costante_e_avvisa():
    rng = np.random.default_rng(3)
    M = np.column_stack([rendimenti_garch(seed=4), 1e-12 * rng.normal(size=1500)])
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # nessun ConvergenceWarning deve arrivare all'utente
        g = simula.Garch(M, ["AAA", "FERMO"])
    assert g.ripieghi == ["FERMO"] and "FERMO" in g.avvisi[0] and "volatilità costante" in g.avvisi[0]
    om, al, be = g.par[1]
    assert al == 0 and be == 0 and np.isfinite(g.h0).all()
    g.prepara(50, 21, np.random.default_rng(0))
    assert np.isfinite(g.blocco(0)).all()


def test_stima_non_convergente_non_viene_usata(monkeypatch):
    """Simula SLSQP che risponde sempre «codice 4»: si provano gli altri punti di partenza e poi si ripiega."""
    import arch.univariate.base as base

    originale = base.ARCHModel.fit
    chiamate = []

    def fit_finto(self, *a, **k):
        f = originale(self, *a, **k)
        chiamate.append(k.get("starting_values"))
        f.__dict__["convergence_flag"] = 4  # «Inequality constraints incompatible»
        return f

    monkeypatch.setattr(base.ARCHModel, "fit", fit_finto)
    M = np.column_stack([rendimenti_garch(seed=5)])
    g = simula.Garch(M, ["AAA"])
    assert len(chiamate) == 1 + len(simula.Garch.PARTENZE)  # stima standard + altri punti di partenza
    assert g.ripieghi == ["AAA"] and g.par[0, 1] == 0 and g.par[0, 2] == 0


def test_secondo_punto_di_partenza_recupera_la_stima(monkeypatch):
    import arch.univariate.base as base

    originale = base.ARCHModel.fit

    def fit_finto(self, *a, **k):
        f = originale(self, *a, **k)
        if k.get("starting_values") is None:
            f.__dict__["convergence_flag"] = 4  # solo la prima stima fallisce
        return f

    monkeypatch.setattr(base.ARCHModel, "fit", fit_finto)
    g = simula.Garch(np.column_stack([rendimenti_garch(seed=6)]), ["AAA"])
    assert g.ripieghi == [] and g.avvisi == [] and g.par[0, 1] > 0


def test_end_to_end_ripiego_garch_segnalato_nel_report(cfg_piccola, finto_yahoo, tmp_path):
    """Un titolo con prezzo fermo (rendimenti nulli): il GARCH non si può stimare, il report lo dice in Sintesi e in Robustezza."""
    import pandas as pd
    from dati_finti import GIORNI

    import analisi
    import configurazione as C
    import report

    def scarica(t):
        if t == "FERMO.MI":
            return pd.Series(100.0, index=GIORNI), {"valuta": "EUR", "tipo": "EQUITY"}
        return finto_yahoo(t)

    cfg_piccola["moduli"] = {"stress_test": False, "rischio_singolo_titolo": False, "confronto_modelli": True, "analisi_C": False}
    cfg_piccola["portafogli"][0]["titoli"] = ["AAA.MI", "FERMO.MI"]
    cfg_piccola["rendimento_atteso"] = {"metodo": "storico"}
    cfg = C.prepara(cfg_piccola)
    with warnings.catch_warnings(record=True) as avvisi_python:
        warnings.simplefilter("always")
        ris = analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=scarica, log=lambda *a: None)
    assert not [w for w in avvisi_python if "ConvergenceWarning" in type(w.message).__name__ or "optimizer" in str(w.message)]
    assert ris["avvisi_modelli"] and all("FERMO.MI" in x and "volatilità costante" in x for x in ris["avvisi_modelli"])
    html = report.html_report(ris, report.sezioni(ris))
    assert "Avviso sul modello GARCH" in html and "Avviso sui modelli" in html
