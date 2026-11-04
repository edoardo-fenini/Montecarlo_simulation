"""La prova rapida di Installa.command: solo i test marcati «rapido», senza i test lenti né la prova nel browser."""

import pathlib
import subprocess
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent


def test_installa_command_esegue_solo_i_test_rapidi():
    testo = (RADICE / "Installa.command").read_text(encoding="utf-8")
    riga = next(r for r in testo.splitlines() if "pytest" in r and not r.lstrip().startswith("#"))
    assert "-m rapido" in riga


def test_il_sottoinsieme_rapido_esclude_i_test_lenti():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "rapido", "-p", "no:cacheprovider", str(RADICE / "tests")],
        capture_output=True, text=True, cwd=RADICE, timeout=120,
    )  # fmt: skip
    righe = [x for x in r.stdout.splitlines() if "::" in x]
    assert len(righe) > 150  # quasi tutti i test sono rapidi
    for lento in ("test_app_simulazione_completa", "test_app_controllo", "tests/e2e", "test_parallelo_da_gli_stessi_numeri"):
        assert not any(lento in x for x in righe), lento
    assert any("test_non_regressione.py::test_non_regressione" in x for x in righe)  # i numeri si controllano anche all'installazione
    assert any("test_app.py::test_app_si_avvia" in x for x in righe)
