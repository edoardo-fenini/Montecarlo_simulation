"""v1.5: modello a fattori end-to-end con dati finti (senza internet): analisi, report e scomposizione anche con il modello storico."""

import copy

import numpy as np
import pandas as pd
import yaml
from dati_finti import GIORNI, crea_finto_yahoo

import analisi
import configurazione as C
import report


def _scaricatore():
    base = crea_finto_yahoo()
    rng = np.random.default_rng(11)
    extra = {}
    for nome in ("FX1", "FX2", "FX3"):
        extra[nome] = pd.Series(100 * np.cumprod(1 + rng.normal(0.0002, 0.006, len(GIORNI))), index=GIORNI)

    def scarica(t):
        if t in extra:
            return extra[t].copy(), {"valuta": "EUR", "tipo": "ETF"}
        return base(t)

    return scarica


def _file_fattori(tmp_path):
    conf = {
        "inizio_storia": "2012-02-01",
        "ridge": {"lambda": "auto", "minimo": 0.5, "frazione_minima": 0.5},
        "fattori": [
            {"nome": "Mercato mondiale", "gruppo": "mercato", "lungo": "BMK.AS", "valuta": "EUR"},
            {"nome": "Tecnologia", "gruppo": "settori", "lungo": "FX1", "corto": "BMK.AS", "valuta": "EUR"},
            {"nome": "Growth contro value", "gruppo": "stile", "lungo": "FX2", "corto": "FX3", "valuta": "EUR"},
        ],
    }
    p = tmp_path / "fattori.yaml"
    p.write_text(yaml.safe_dump(conf))
    return str(p)


def _cfg(cfg_piccola, tmp_path, modello, **moduli):
    c = copy.deepcopy(cfg_piccola)
    c["modello_simulazione"], c["fattori_file"] = modello, _file_fattori(tmp_path)
    c["moduli"] = {"stress_test": False, "rischio_singolo_titolo": False, "confronto_modelli": False, "analisi_C": False, **moduli}
    c["n_simulazioni"] = 300
    return C.prepara(c)


def test_modello_fattori_end_to_end_e_report(cfg_piccola, tmp_path):
    cfg = _cfg(cfg_piccola, tmp_path, "fattori")
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path / "c"), scaricatore=_scaricatore(), log=lambda *a: None, solo=["A"])
    assert ris["modello_simulazione"] == "fattori" and list(ris["sim"]) == ["A"]
    sc = ris["fattori"]["scomposizione"]
    for p in ris["nomi"]:
        assert abs(sum(sc[p]["quote"].values()) - 1) < 1e-9
    assert not ris["errore_plausibilita"]
    S = report.sezioni(ris)
    assert S["Da dove viene il rischio"]
    assert "a fattori" in report.testo_metodo(ris)
    assert "<html" in report.html_report(ris, S)
    # volatilità simulata vicina a quella storica (i dati finti hanno un solo fattore vero: il mercato)
    storico = ris["storico"]["A"]["stat"]
    for p in ris["nomi"]:
        assert abs(ris["sim"]["A"]["vol_sim"][p] / storico[p]["vol"] - 1) < 0.25


def test_scomposizione_disponibile_anche_con_modello_storico(cfg_piccola, tmp_path):
    cfg = _cfg(cfg_piccola, tmp_path, "storico", scomposizione_rischio=True)
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path / "c"), scaricatore=_scaricatore(), log=lambda *a: None, solo=["A"])
    assert ris["modello_simulazione"] == "storico" and ris["fattori"]["scomposizione"]
    assert report.sezioni(ris)["Da dove viene il rischio"]


def test_modello_non_valido():
    import pytest

    with pytest.raises(C.ErroreConfig, match="modello_simulazione"):
        C.prepara({"modello_simulazione": "boh", "portafogli": [{"nome": "x", "titoli": ["A"]}]})
