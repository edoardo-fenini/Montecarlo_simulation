"""Alcuni file stanno solo nel repository e non nello zip della release (vedi .gitattributes, «export-ignore»): i workflow in
.github/, .gitattributes. I test che li leggono servono a chi sviluppa: nello zip installato sul Mac vanno saltati, non falliti."""

import pathlib

import pytest

RADICE = pathlib.Path(__file__).resolve().parent.parent


def richiede(*percorsi: str) -> None:
    """Salta il test (con un messaggio chiaro) se manca uno dei file indicati, relativi alla cartella del programma."""
    mancanti = [p for p in percorsi if not (RADICE / p).exists()]
    if mancanti:
        pytest.skip(
            "File presenti solo nel repository di sviluppo, non nello zip della release: " + ", ".join(mancanti)
            + ". Questo test serve a chi sviluppa ed è saltato: non è un errore."
        )
