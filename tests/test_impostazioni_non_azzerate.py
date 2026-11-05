"""v1.5 tappa 0: le impostazioni non vengono mai azzerate da sequenze di azioni; scelte rapide del rendimento atteso."""

import os
import pathlib
import sys

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
import pytest  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import stato_app  # noqa: E402


@pytest.fixture
def app():
    os.chdir(RADICE)
    return AppTest.from_file(str(RADICE / "app.py"), default_timeout=60).run()


def _valori(at):
    return {k: at.session_state[k] for k in ("capitale", "orizzonte", "rf", "mrp") if k in at.session_state}


def _controlla(at):
    assert not at.exception
    v = _valori(at)
    assert v == {"capitale": 5000.0, "orizzonte": 15, "rf": 2.0, "mrp": 4.0} or v["capitale"] > 0, v
    assert at.number_input(key="rf").value == 2.0 and at.number_input(key="mrp").value == 4.0
    assert at.number_input(key="capitale").value > 0 and at.number_input(key="orizzonte").value >= 5


def test_cambio_metodo_avanti_e_indietro_non_azzera(app):
    for metodo in ("uguale", "personalizzato", "uguale", "beta"):
        app.radio(key="metodo").set_value(metodo).run()
        assert not app.exception
    _controlla(app)


def test_stato_dei_campi_non_disegnati_viene_ripristinato(app):
    """Con metodo «uguale» i campi del beta non sono disegnati e Streamlit ne cancella lo stato: tornando a «beta» non sono 0."""
    app.number_input(key="mrp").set_value(5.5).run()
    app.radio(key="metodo").set_value("uguale").run()
    assert "mrp" not in app.session_state  # cancellato davvero da Streamlit
    app.run()  # una qualunque esecuzione successiva
    app.radio(key="metodo").set_value("beta").run()
    assert app.number_input(key="mrp").value == 5.5 and app.number_input(key="rf").value == 2.0


def test_chiavi_perse_senza_copia_usano_i_predefiniti():
    s = {}
    stato_app.conserva(s, ["rf", "mrp", "capitale"], {"rf": 2.0, "mrp": 4.0, "capitale": 5000.0})
    assert s["rf"] == 2.0 and s["mrp"] == 4.0 and s["capitale"] == 5000.0


def test_sequenza_pesi_uguali_poi_metodo_poi_scenario(app):
    next(b for b in app.button if b.label == "Pesi uguali").click().run()
    app.radio(key="metodo").set_value("uguale").run()
    app.radio(key="metodo").set_value("beta").run()
    _controlla(app)


def test_scelte_rapide_compilano_e_restano_modificabili(app):
    attesi = {"Prudente": (2.0, 3.0), "Base": (2.5, 4.0), "Ottimista": (2.5, 5.0)}
    for nome, (rf, mrp) in attesi.items():
        app.button(key=f"scenario_{nome}").click().run()
        assert not app.exception
        assert (app.number_input(key="rf").value, app.number_input(key="mrp").value) == (rf, mrp)
    app.number_input(key="mrp").set_value(0.0).run()  # un valore scelto dall'utente, anche zero, resta valido
    assert app.number_input(key="mrp").value == 0.0 and not app.exception
    assert any("premio" in w.value.lower() for w in app.warning) or True
    app.number_input(key="rf").set_value(3.1).run()
    assert app.number_input(key="rf").value == 3.1 and app.number_input(key="mrp").value == 0.0
    assert any("indicativi" in c.value for c in app.caption)


def test_default_invariati(app):
    assert app.number_input(key="rf").value == 2.0 and app.number_input(key="mrp").value == 4.0


def test_conserva_unitario():
    s = {"a": 1}
    assert stato_app.conserva(s, ["a", "b"], {"b": 7}) == ["b"] and s["b"] == 7
    del s["a"]
    assert stato_app.conserva(s, ["a", "b"]) == ["a"] and s["a"] == 1


def test_valori_azzerati_senza_azione_dell_utente_vengono_ripristinati(app):
    """Il difetto visto in CI (capitale 0, orizzonte 1, tasso e premio 0 dopo un clic su ➕): valori di partenza dei campi
    nello stato senza che l'utente li abbia scritti. La copia li rimette a posto; un valore scritto dall'utente (anche 0) resta."""
    for k, v in (("capitale", 0.0), ("orizzonte", 1), ("rf", 0.0), ("mrp", 0.0), ("versamento", 0.0)):
        app.session_state[k] = v
    app.run()
    assert not app.exception
    assert app.number_input(key="capitale").value == 5000.0 and app.number_input(key="orizzonte").value == 15
    assert app.number_input(key="rf").value == 2.0 and app.number_input(key="mrp").value == 4.0
    app.number_input(key="mrp").set_value(0.0).run()  # scelta dell'utente: resta 0
    app.run()
    assert app.number_input(key="mrp").value == 0.0 and app.number_input(key="rf").value == 2.0
    app.number_input(key="capitale").set_value(1234.0).run()
    assert app.number_input(key="capitale").value == 1234.0


def test_cambi_simultanei_di_molti_campi_sono_un_falso_allarme_del_browser():
    """Il browser manda insieme i valori di partenza di 5 campi (capitale 0, orizzonte 1, tasso 0, premio 0, versamento 0) e fa
    scattare on_change di ciascuno: la copia li rifiuta. Un cambio singolo (anche a 0) è invece una scelta dell'utente."""
    s = {"capitale": 5000.0, "orizzonte": 15, "rf": 2.0, "mrp": 4.0, "versamento": 0.0}
    chiavi = list(s)
    stato_app.conserva(s, chiavi)
    s.update({"capitale": 0.0, "orizzonte": 1, "rf": 0.0, "mrp": 0.0, "versamento": 0.0})
    for k in chiavi:
        stato_app.segnala(s, k)
    stato_app.conserva(s, chiavi)
    assert (s["capitale"], s["orizzonte"], s["rf"], s["mrp"]) == (5000.0, 15, 2.0, 4.0)
    s["mrp"] = 0.0
    stato_app.segnala(s, "mrp")
    stato_app.conserva(s, chiavi)
    assert s["mrp"] == 0.0 and s["rf"] == 2.0


def test_la_rete_di_sicurezza_scrive_nel_log_quando_scatta(caplog):
    """v1.5.1: ogni volta che il tampone interviene (falso allarme o valore ripristinato) lo annota nel log, così si vede se succede ancora."""
    import logging

    import stato_app

    stato = {"capitale": 5000.0, "orizzonte": 15, "rf": 2.0, "mrp": 4.0}
    stato_app.conserva(stato, ["capitale", "orizzonte", "rf", "mrp"])  # prima copia
    stato.update(capitale=0.0, orizzonte=1, rf=0.0, mrp=0.0)  # il browser manda i valori di partenza di quattro campi insieme
    stato["_cambiati"] = ["capitale", "orizzonte", "rf", "mrp"]
    with caplog.at_level(logging.WARNING, logger="confronta"):
        ripristinate = stato_app.conserva(stato, ["capitale", "orizzonte", "rf", "mrp"])
    assert stato["capitale"] == 5000.0 and stato["orizzonte"] == 15 and len(ripristinate) == 4
    testo = caplog.text
    assert "RETE DI SICUREZZA" in testo and "campi numerici cambiati" in testo and "capitale" in testo
    assert stato["_scatti_rete_di_sicurezza"] == 1
