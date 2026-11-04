"""Il meccanismo che salta i test dei file presenti solo nel repository (zip della release)."""

import pytest

from solo_repository import richiede


def test_file_presente_non_salta():
    richiede("app.py")


def test_file_mancante_salta_con_messaggio_chiaro():
    with pytest.raises(pytest.skip.Exception, match="solo nel repository di sviluppo.*non è un errore"):
        richiede(".github/workflows/non_esiste.yml")


def test_i_file_esclusi_dallo_zip_sono_quelli_di_gitattributes():
    import pathlib

    attr = pathlib.Path(__file__).resolve().parent.parent / ".gitattributes"
    if not attr.exists():
        pytest.skip("File presenti solo nel repository di sviluppo, non nello zip della release: .gitattributes. Non è un errore.")
    esclusi = {r.split()[0] for r in attr.read_text().splitlines() if "export-ignore" in r}
    assert esclusi == {".github", ".gitattributes"}  # se ne aggiungi uno, controlla i test che lo leggono (usa richiede)
