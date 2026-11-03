"""Palette fissa e coerente (app, report, PDF) e grafici interattivi."""

import pytest

import grafici_app as G
import report as R
import stile


def test_palette_fissa_e_benchmark_grigio():
    nomi = ["A", "B", "Bench", "C"]
    c = stile.colori(nomi, "Bench")
    assert c["Bench"] == stile.GRIGIO and c["A"] == stile.PALETTE[0] and c["B"] == stile.PALETTE[1] and c["C"] == stile.PALETTE[2]
    assert stile.colori(nomi, "Bench") == c  # sempre gli stessi
    assert len(set(stile.PALETTE)) == len(stile.PALETTE)
    idx = stile.indice(nomi, "Bench")
    assert idx["Bench"] == 0 and len({idx[k] for k in "ABC"}) == 3  # tratteggi diversi: non solo il colore


def test_tacche_italiane():
    valori, testi = G.tacche_euro(43000)
    assert testi[0] == "0" and "10.000" in testi and all("," not in t for t in testi)


@pytest.fixture(scope="module")
def ris(tmp_path_factory):
    from dati_finti import crea_finto_yahoo

    import analisi
    import configurazione as C

    cfg = {
        "nome": "grafici",
        "capitale_iniziale": 1000,
        "orizzonte_anni": 3,
        "orizzonti_intermedi": [1],
        "n_simulazioni": 150,
        "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "proxy_storico": "^IDX"},
        "analisi": {"inizio_B": "2012-06-01"},
        "moduli": {"stress_test": False, "rischio_singolo_titolo": False, "verifica_convergenza": False},
        "portafogli": [{"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]}, {"nome": "Due", "titoli": ["CCC"]}],
    }
    return analisi.esegui(
        C.prepara(cfg), cartella_cache=str(tmp_path_factory.mktemp("c")), scaricatore=crea_finto_yahoo(), log=lambda *a: None
    )


def test_fan_chart_interattivo(ris):
    fig = G.fan_chart(ris, "A")
    mediane = [t for t in fig.data if t.showlegend is not False and t.name in ris["nomi"]]
    assert [t.name for t in mediane] == ris["nomi"]
    col = R.colori(ris)
    assert all(t.line.color == col[t.name] for t in mediane)  # stessi colori del report
    assert all("5°" in t.hovertemplate and "95°" in t.hovertemplate for t in mediane)
    assert {t.legendgroup for t in fig.data if t.legendgroup} == set(ris["nomi"])  # clic sulla legenda nasconde anche la fascia
    assert fig.data[0].name == "Sotto il capitale investito"
    assert len(G.fan_chart(ris, "A", fasce=False).data) == len(ris["nomi"]) + 2


def test_istogramma_con_motivi(ris):
    fig = G.istogramma_mdd(ris, "A")
    assert [t.name for t in fig.data] == ris["nomi"]
    assert len({t.marker.pattern.shape for t in fig.data}) == len(ris["nomi"])
