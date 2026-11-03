"""I numeri chiave del report non devono cambiare (configurazione e seed fissi, dati sintetici)."""
import non_regressione as NR


def test_non_regressione():
    attesi = NR.carica_riferimento()
    ottenuti = NR.numeri_chiave(NR.calcola())
    diff = NR.confronta(attesi, ottenuti)
    assert not diff, f"{len(diff)} numeri diversi dal riferimento, ad esempio:\n" + "\n".join(diff[:20])
    assert len(attesi) > 500
