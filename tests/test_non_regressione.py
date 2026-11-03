"""I numeri chiave del report non devono cambiare (configurazione e seed fissi, dati sintetici)."""
import non_regressione as NR


def test_non_regressione():
    attesi = NR.carica_riferimento()
    ottenuti = NR.numeri_chiave(NR.calcola())
    diff = NR.confronta(attesi, ottenuti)
    assert not diff, f"{len(diff)} numeri diversi dal riferimento, ad esempio:\n" + "\n".join(diff[:20])
    assert len(attesi) > 500


def test_parallelo_da_gli_stessi_numeri():
    """Le simulazioni indipendenti eseguite in processi separati danno esattamente gli stessi risultati."""
    import copy
    import tempfile
    import analisi
    import configurazione as C
    from dati_finti import crea_finto_yahoo
    cfg = copy.deepcopy(NR.CONFIG)
    cfg["parallelo"] = "si"
    with tempfile.TemporaryDirectory() as d:
        ris = analisi.esegui(C.prepara(cfg), cartella_cache=d, scaricatore=crea_finto_yahoo(), log=lambda *a: None)
    diff = NR.confronta(NR.carica_riferimento(), NR.numeri_chiave(ris))
    assert not diff, "\n".join(diff[:20])
