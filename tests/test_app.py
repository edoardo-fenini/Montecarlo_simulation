"""L'app Streamlit si avvia senza errori (senza internet: all'avvio non scarica nulla)."""

import os
import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from streamlit.testing.v1 import AppTest  # noqa: E402


def test_app_si_avvia_con_esempio_precaricato():
    os.chdir(RADICE)
    at = AppTest.from_file(str(RADICE / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert any("Confronto del rischio" in t.value for t in at.title)
    assert at.number_input(key="capitale").value == 5000
    assert at.radio(key="metodo").value == "beta"
    # pulsante pesi uguali e cambio metodo funzionano senza errori
    next(b for b in at.button if b.label == "Pesi uguali").click().run()
    assert not at.exception
    at.radio(key="metodo").set_value("personalizzato").run()
    assert not at.exception
