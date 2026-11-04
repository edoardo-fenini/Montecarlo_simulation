"""App: pulsante «Controlla i dati», riepilogo, blocco di «Avvia simulazione» con un rosso, ISIN e menu delle quotazioni (dati finti)."""

import datetime
import json
import os
import pathlib
import sys
import zlib

import numpy as np
import pandas as pd
import pytest

RADICE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from streamlit.testing.v1 import AppTest  # noqa: E402

import fonti  # noqa: E402
import isin  # noqa: E402

ISIN = "IE00B4L5Y983"
FIGI = json.dumps(
    [
        {
            "data": [
                {"ticker": "SWDA", "exchCode": "IM", "name": "ISHARES CORE MSCI WORLD"},
                {"ticker": "EUNL", "exchCode": "GY", "name": "ISHARES CORE MSCI WORLD"},
                {"ticker": "IWDA", "exchCode": "NA", "name": "ISHARES CORE MSCI WORLD"},
            ]
        }
    ]
).encode()


def finto_scarica(t):
    if t.startswith("ZZZ"):
        return pd.Series(dtype=float), {}
    idx = pd.bdate_range(end=datetime.date.today(), periods=1300)
    r = np.random.default_rng(zlib.crc32(t.encode())).normal(0.0003, 0.01, len(idx))
    s = pd.Series(100 * np.cumprod(1 + r), index=idx)
    if t.startswith("EUR") and t.endswith("=X"):
        s = pd.Series(1.1, index=idx)
    valuta = t[3:6] if t.startswith("EUR") and t.endswith("=X") else ("EUR" if "." in t else "USD")
    return s, {"valuta": valuta, "tipo": "EQUITY", "nome": f"Societa {t}", "borsa": "Prova", "fonte": "Finto Yahoo"}


def scheda(t):
    return {
        "valuta": "EUR",
        "borsa": t,
        "nome": "iShares Core MSCI World",
        "tipo": "ETF",
        "primo": 1.25e9,
        "volume": 1e5,
        "ultimo": datetime.date.today().isoformat(),
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    os.symlink(RADICE / "configurazioni", tmp_path / "configurazioni")
    monkeypatch.chdir(tmp_path)  # cache e report in una cartella temporanea
    monkeypatch.setattr(fonti, "scarica_con_ripiego", finto_scarica)
    monkeypatch.setattr(isin, "_http", lambda url, dati=None, intestazioni=None, timeout=0: FIGI)
    monkeypatch.setattr(isin, "ispeziona_ticker", lambda t, http=None, ispettore=None: scheda(t))
    return AppTest.from_file(str(RADICE / "app.py"), default_timeout=120).run()


def bottone(at, parte):
    return next(b for b in at.button if parte in b.label)


def con_tabella(at, righe):
    at.session_state["tabella"] = pd.DataFrame(righe, columns=["Portafoglio", "Ticker", "Peso (%)"])
    at.session_state["versione"] += 1
    return at.run()


def test_controlla_i_dati_tutto_verde_e_avvia_attivo(app):
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ENEL.MI", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    e = app.session_state["controllo"]["esito"]
    assert e["riepilogo"].startswith("3 titoli trovati") and not e["blocca"]  # AAPL, ENEL.MI + benchmark
    assert not bottone(app, "Avvia simulazione").disabled


def test_un_rosso_disattiva_avvia_simulazione_e_spiega(app):
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ZZZ.MI", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    assert app.session_state["controllo"]["esito"]["blocca"]
    assert bottone(app, "Avvia simulazione").disabled
    testi = " ".join(x.value for x in app.error)
    assert "ZZZ.MI" in testi and "Correggi" in testi
    # togliendo il titolo sbagliato e ricontrollando il pulsante torna attivo
    app = con_tabella(app, [["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not bottone(app, "Avvia simulazione").disabled


def test_isin_nel_controllo_con_menu_delle_quotazioni(app):
    app = con_tabella(app, [["P", ISIN, None], ["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert not app.exception
    riga = next(r for r in app.session_state["controllo"]["esito"]["righe"] if r["input"] == ISIN)
    assert riga["isin"] == ISIN and riga["ticker"] == "SWDA.MI"
    menu = app.selectbox(key=f"quot_{ISIN}")
    etichette = {o.split(" · ")[0]: o for o in menu.options}  # il menu mostra «ticker · borsa · valuta · storia · volumi»
    assert menu.value == "SWDA.MI" and set(etichette) == {"SWDA.MI", "EUNL.DE", "IWDA.AS"}
    menu.select("IWDA.AS").run()  # altra quotazione: il controllo si rifa da solo
    assert not app.exception
    assert app.session_state["scelte_isin"] == {ISIN: "IWDA.AS"}
    riga = next(r for r in app.session_state["controllo"]["esito"]["righe"] if r["input"] == ISIN)
    assert riga["ticker"] == "IWDA.AS" and riga["risoluzione"]["scelta_utente"]


def test_isin_con_cifra_errata_blocca(app):
    app = con_tabella(app, [["P", "IE00B4L5Y984", None], ["P", "AAPL", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert bottone(app, "Avvia simulazione").disabled
    assert "cifra di controllo" in " ".join(x.value for x in app.error)


# ------------------------------------------------------------------ v1.3: risultati vecchi
def simula_piccola(app):
    app.number_input(key="nsim").set_value(500)
    app.number_input(key="orizzonte").set_value(2)
    for k in ("stress_test", "rischio_singolo_titolo", "verifica_convergenza", "confronto_modelli", "analisi_C"):
        app.checkbox(key=f"mod_{k}").set_value(False)
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ENEL.MI", None]])
    app = bottone(app, "Avvia simulazione").click().run()
    assert not app.exception and "ris" in app.session_state
    return app


def errori_in_testo(app):
    return " ".join(x.value for x in app.error)


def test_risultati_nascosti_se_cambiano_le_impostazioni(app):
    app = simula_piccola(app)
    assert "non corrispondono più" not in errori_in_testo(app) and len(app.tabs) > 3
    app.number_input(key="capitale").set_value(7777.0)
    app = app.run()
    assert not app.exception
    assert "Questi risultati non corrispondono più ai dati attuali: rilancia la simulazione." in errori_in_testo(app)
    assert not [t for t in app.tabs if t.label == "Sintesi"]  # risultati nascosti
    # tornando al valore di prima l'avviso scompare
    app.number_input(key="capitale").set_value(5000.0)
    app = app.run()
    assert "non corrispondono più" not in errori_in_testo(app)


def test_risultati_nascosti_se_il_controllo_dati_e_rosso(app):
    app = simula_piccola(app)
    app = con_tabella(app, [["P", "AAPL", None], ["P", "ZZZ.MI", None]])
    app = bottone(app, "Controlla i dati").click().run()
    assert "non corrispondono più" in errori_in_testo(app)
    assert not [t for t in app.tabs if t.label == "Sintesi"]


def test_risultati_nascosti_se_i_dati_cambiano_e_toggle_per_vederli(app):
    app = simula_piccola(app)
    t = pathlib.Path("cache_prezzi")
    prossimo = max(f.stat().st_mtime for f in t.glob("*.csv")) + 100
    for f in t.glob("AAPL.csv"):
        os.utime(f, (prossimo, prossimo))
    app = app.run()
    assert "non corrispondono più" in errori_in_testo(app) and "prezzi in cache" in errori_in_testo(app)
    app.toggle(key="mostra_vecchi").set_value(True).run()
    assert [t for t in app.tabs if t.label == "Sintesi"]  # su richiesta si rivedono, con l'avviso ancora in cima
    assert "non corrispondono più" in errori_in_testo(app)


def test_motivo_risultati_vecchi_funzione_pura():
    import controllo

    stato = {"chiave": "k", "dati": 10.0}
    f = controllo.motivo_risultati_vecchi
    assert f(None, "x", 99.0) is None
    assert f(stato, "k", 10.0) is None
    assert "cambiato" in f(stato, "altra", 10.0) and "cambiato" in f(stato, None, 10.0)
    assert "aggiornati" in f(stato, "k", 11.0)
    rosso = {"chiave": "d", "esito": {"blocca": True}}
    assert "rosso" in f(stato, "k", 10.0, rosso, "d")
    assert f(stato, "k", 10.0, rosso, "altro") is None  # controllo di titoli che non sono più quelli attuali


# ------------------------------------------------------------------ v1.3: importazione dal broker
def test_importa_dal_broker_anteprima_e_conferma(app, monkeypatch):
    import importa_broker

    monkeypatch.setattr(importa_broker, "prezzo_da_archivio", lambda arch, opz=None: lambda c: (90.0, "VWCE.DE"))
    csv = (RADICE / "esempi/portafoglio_broker_esempio.csv").read_bytes()

    class FileFinto:
        name = "conto.csv"

        def getvalue(self):
            return csv

    # il file_uploader non si riempie da AppTest: l'anteprima si prepara come farebbe il pulsante (nel browser la prova è in tests/e2e)
    ris = importa_broker.calcola(FileFinto().getvalue(), importa_broker.prezzo_da_archivio(None))
    app.session_state["anteprima_broker"] = {"ris": ris, "nome": "Conto", "file": "conto.csv"}
    app = app.run()
    assert not app.exception
    assert any("Anteprima di «Conto»" in m.value for m in app.markdown)
    next(b for b in app.button if "Conferma e aggiungi" in b.label).click().run()
    assert not app.exception and "anteprima_broker" not in app.session_state
    t = app.session_state["tabella"]
    conto = t[t["Portafoglio"] == "Conto"]
    assert set(conto["Ticker"]) == {"IE00B4L5Y983", "IT0003128367", "US0378331005", "IE00BK5BQT80"}
    assert round(conto["Peso (%)"].sum(), 6) == 100
    assert len(t) > len(conto)  # i portafogli già presenti restano
    assert any("aggiunto alla tabella" in m.value for m in app.success)


# ------------------------------------------------------------------ v1.3: ricerca per nome
def test_ricerca_per_nome_e_aggiunta_con_un_clic(app, monkeypatch):
    import ricerca

    risultati = [
        {"nome": "Enel S.p.A.", "ticker": "ENEL.MI", "isin": "", "borsa": "Milan", "valuta": "EUR", "tipo": "Azione"},
        {"nome": "Enel ADR", "ticker": "ENLAY", "isin": "", "borsa": "OTC", "valuta": "USD", "tipo": "Azione"},
    ]
    monkeypatch.setattr(ricerca, "cerca", lambda testo, **kw: risultati)
    app = con_tabella(app, [["P", "AAPL", None]])
    app.text_input(key="ricerca_testo").set_value("enel").run()
    app = bottone(app, "Cerca").click().run()
    assert not app.exception and app.session_state["risultati_ricerca"]["righe"] == risultati
    assert any("Enel S.p.A. · ENEL.MI · Milan · EUR · Azione" in m.value for m in app.markdown)
    next(b for b in app.button if b.key == "btn_aggiungi_0_ENEL.MI").click().run()
    assert not app.exception
    t = app.session_state["tabella"]
    assert list(t[t["Portafoglio"] == "P"]["Ticker"]) == ["AAPL", "ENEL.MI"]
    assert any("Aggiunto Enel S.p.A. (ENEL.MI)" in m.value for m in app.success)
    # secondo clic sullo stesso titolo: nessun doppione
    next(b for b in app.button if b.key == "btn_aggiungi_0_ENEL.MI").click().run()
    t = app.session_state["tabella"]
    assert (t["Ticker"] == "ENEL.MI").sum() == 1


def test_ricerca_in_un_nuovo_portafoglio_e_avviso_sui_pesi(app, monkeypatch):
    import ricerca

    r = {"nome": "Enel S.p.A.", "ticker": "ENEL.MI", "isin": "", "borsa": "Milan", "valuta": "EUR", "tipo": "Azione"}
    monkeypatch.setattr(ricerca, "cerca", lambda testo, **kw: [r])
    app = con_tabella(app, [["P", "AAPL", 100.0]])
    app.text_input(key="ricerca_testo").set_value("enel").run()
    app = bottone(app, "Cerca").click().run()
    next(b for b in app.button if b.key == "btn_aggiungi_0_ENEL.MI").click().run()
    assert any("scrivi il peso del nuovo titolo" in m.value for m in app.success)
    app.selectbox(key="ricerca_destinazione").select("➕ Nuovo portafoglio").run()
    app.text_input(key="ricerca_nuovo_nome").set_value("Italia").run()
    next(b for b in app.button if b.key == "btn_aggiungi_0_ENEL.MI").click().run()
    t = app.session_state["tabella"]
    assert list(t[t["Portafoglio"] == "Italia"]["Ticker"]) == ["ENEL.MI"]


# ------------------------------------------------------------------ v1.3: impostazioni conservate
def test_impostazioni_ripristinate_se_streamlit_cancella_lo_stato_dei_widget(app):
    import stato_app

    app.number_input(key="capitale").set_value(12345.0)
    app.number_input(key="orizzonte").set_value(7)
    app = app.run()
    copia = app.session_state["_impostazioni"]
    assert copia["capitale"] == 12345.0 and copia["orizzonte"] == 7 and copia["rf"] == 2.0  # la copia segue i valori attuali
    # ripristino: come dopo un'esecuzione interrotta da un errore, quando Streamlit ha cancellato lo stato dei widget
    stato = {"capitale": 1.0, stato_app.CHIAVE_COPIA: dict(copia)}
    assert stato_app.conserva(stato, ["capitale", "orizzonte", "rf"]) == ["capitale", "orizzonte", "rf"]  # vince la copia (v1.5)
    assert stato["capitale"] == 12345.0 and stato["orizzonte"] == 7 and stato["rf"] == 2.0
    stato["capitale"] = 1.0
    stato_app.segnala(stato, "capitale")  # una scelta voluta (un solo campo) aggiorna la copia
    assert stato_app.conserva(stato, ["capitale"]) == [] and stato["capitale"] == 1.0
