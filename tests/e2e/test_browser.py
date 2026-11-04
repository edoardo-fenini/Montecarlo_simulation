"""Prova nel browser vero (Playwright + Chromium) dell'app con una finta rete (nessun accesso a internet).

La tabella «Controllo dati» è un canvas: il suo contenuto NON si legge dal testo della pagina. Le verifiche sul contenuto usano quindi
il testo associato «Ticker usati: …» (stessi dati della tabella) e, alla fine, il report scaricato."""

import pathlib
import re

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect  # noqa: E402

DATI = pathlib.Path(__file__).parent / "dati"
ISIN = "IE00B4L5Y983"


def carica_config(pagina, nome_file):
    pagina.locator("input[type=file]").last.set_input_files(str(DATI / nome_file))
    expect(pagina.get_by_text("caricata.")).to_be_visible()


def controlla(pagina):
    pagina.get_by_role("button", name="Controlla i dati").click()


def scegli_quotazione(pagina, codice, ticker, tentativi=4):
    """Sceglie la quotazione dal menu (ha la ricerca: si scrive il ticker, si attende l'opzione e si conferma con Invio).
    Su macchine lente l'Invio può arrivare prima che il menu sia filtrato: si riprova e si verifica dal testo «Ticker usati»."""
    for i in range(tentativi):
        menu = pagina.get_by_role("combobox", name=re.compile(f"Quotazione scelta per {codice}"))
        menu.click()
        menu.press_sequentially(ticker.split(".")[0], delay=80)
        opzione = pagina.locator("[role=option]").filter(has_text=ticker)
        try:
            opzione.first.wait_for(state="visible", timeout=5000)
        except Exception:
            pagina.wait_for_timeout(1000)
        menu.press("Enter")
        try:
            expect(pagina.get_by_text("Ticker usati:")).to_contain_text(f"{codice} → {ticker}", timeout=20000)
            return
        except AssertionError:
            if i == tentativi - 1:
                raise
            pagina.keyboard.press("Escape")


def test_app_si_apre_e_ha_i_pulsanti(pagina):
    expect(pagina.get_by_role("button", name="Controlla i dati")).to_be_visible()
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_enabled()


def test_isin_errato_blocca_la_simulazione(pagina):
    carica_config(pagina, "config_isin_errato.yaml")
    controlla(pagina)
    expect(pagina.get_by_text("1 errore").first).to_be_visible()
    expect(pagina.get_by_text("cifra di controllo").first).to_be_visible()
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_disabled()


def test_percorso_completo_isin_quotazione_simulazione_report_e_risultati_vecchi(pagina):
    carica_config(pagina, "config_isin.yaml")
    controlla(pagina)
    expect(pagina.get_by_text("0 errori").first).to_be_visible(timeout=60000)
    # contenuto della tabella (canvas) verificato dal testo associato, non dal canvas
    usati = pagina.get_by_text("Ticker usati:")
    expect(usati).to_contain_text(f"{ISIN} → SWDA.MI")
    expect(usati).to_contain_text("US0378331005 → AAPL")
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_enabled()

    # cambio della quotazione dal menu: il controllo si rifà e il testo associato cambia
    scegli_quotazione(pagina, ISIN, "EUNL.DE")
    expect(pagina.get_by_text("Ticker usati:")).not_to_contain_text("SWDA.MI")

    # simulazione e report
    pagina.get_by_role("button", name="Avvia simulazione").first.click()
    bottone_html = pagina.get_by_role("button", name="Report HTML")
    expect(bottone_html).to_be_visible(timeout=240000)
    with pagina.expect_download() as d:
        bottone_html.click()
    html = pathlib.Path(d.value.path()).read_text(encoding="utf-8")
    assert "EUNL.DE" in html and "SWDA.MI" not in html

    # cambiando un'impostazione i risultati vecchi vengono nascosti con un avviso ben visibile
    capitale = pagina.get_by_role("spinbutton", name="Capitale iniziale (€)")
    capitale.fill("7777")
    capitale.press("Enter")
    expect(pagina.get_by_text("Questi risultati non corrispondono più ai dati attuali: rilancia la simulazione.")).to_be_visible()
    expect(bottone_html).to_have_count(0)


# ------------------------------------------------------------------ correzione 1.3: StreamlitDuplicateElementId
ERRORI_STREAMLIT = "[data-testid=stException]"


def config_completa(tmp_path, sorgente):
    """Configurazione dell'esempio indicato con TUTTI i moduli attivi e poche simulazioni."""
    import yaml

    raw = yaml.safe_load((pathlib.Path(__file__).resolve().parents[2] / sorgente).read_text(encoding="utf-8"))
    raw["n_simulazioni"] = 500
    raw["moduli"] = dict.fromkeys(["stress_test", "rischio_singolo_titolo", "verifica_convergenza", "confronto_modelli", "analisi_C"], True)
    raw.setdefault("verifica_convergenza", {})["numero_seed"] = 2
    f = tmp_path / ("completa_" + pathlib.Path(sorgente).name)
    f.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return f


@pytest.mark.parametrize("sorgente", ["configurazioni/esempio_tre_portafogli.yaml", "configurazioni/esempio_isin.yaml"])
def test_analisi_completa_tutte_le_schede_senza_errori_streamlit(pagina, tmp_path, sorgente):
    pagina.locator("input[type=file]").last.set_input_files(str(config_completa(tmp_path, sorgente)))
    expect(pagina.get_by_text("caricata.")).to_be_visible()
    pagina.get_by_role("button", name="Avvia simulazione").first.click()
    bottone_html = pagina.get_by_role("button", name="Report HTML")
    expect(bottone_html).to_be_visible(timeout=600000)
    expect(pagina.locator(ERRORI_STREAMLIT)).to_have_count(0)
    schede = pagina.get_by_role("tab")
    nomi = [t.strip() for t in schede.all_inner_texts()]
    for nome in ["In una pagina", "Sintesi", "Fan chart", "Drawdown", "Stress test", "Robustezza"]:
        assert any(nome in n for n in nomi), f"manca la scheda {nome}: {nomi}"
    # apre ogni scheda dei risultati e per ultima «Analisi salvate» (che nasconde le altre): nessun errore deve comparire
    ordine = [n for n in nomi if "Analisi salvate" not in n and "Simulazione" not in n] + [n for n in nomi if "Analisi salvate" in n]
    for nome in ordine:
        pagina.get_by_role("tab", name=nome, exact=True).click()
        pagina.wait_for_timeout(400)
        expect(pagina.locator(ERRORI_STREAMLIT)).to_have_count(0)
    assert "DuplicateElement" not in pagina.content()
    pagina.get_by_role("tab", name=next(n for n in nomi if "Simulazione" in n), exact=True).click()
    with pagina.expect_download() as d:
        bottone_html.click()
    html = pathlib.Path(d.value.path()).read_text(encoding="utf-8")
    assert "<html" in html.lower() and "Fan chart" in html


# ------------------------------------------------------------------ v1.3: importazione dal broker e ricerca per nome
def test_importa_csv_del_broker_con_anteprima(pagina):
    pagina.get_by_text("Importa il portafoglio dal broker (CSV)").click()
    caricatore = pagina.locator("[data-testid=stFileUploader]").filter(has_text="File CSV del broker").locator("input[type=file]")
    caricatore.set_input_files(str(pathlib.Path(__file__).resolve().parents[2] / "esempi/portafoglio_broker_esempio.csv"))
    nome = pagina.get_by_role("textbox", name="Nome del portafoglio")
    nome.fill("Conto broker")
    nome.press("Enter")
    pagina.get_by_role("button", name="Mostra anteprima").click()
    expect(pagina.get_by_text("Anteprima di «Conto broker»")).to_be_visible()
    expect(pagina.get_by_role("button", name="Conferma e aggiungi")).to_be_visible()
    pagina.get_by_role("button", name="Conferma e aggiungi").click()
    expect(pagina.get_by_text("Portafoglio «Conto broker» aggiunto alla tabella (4 titoli)")).to_be_visible()
    controlla(pagina)
    expect(pagina.get_by_text("Ticker usati:")).to_contain_text("IE00BK5BQT80 →")


def test_ricerca_per_nome_e_aggiunta_con_un_clic(pagina):
    pagina.get_by_text("Cerca un titolo per nome").click()
    campo = pagina.get_by_role("textbox", name="Nome dell'azienda o dell'ETF")
    campo.fill("Ferrari")
    campo.press("Enter")
    pagina.get_by_role("button", name="Cerca", exact=True).click()
    expect(pagina.get_by_text("Ferrari S.p.A. · FERR.MI · Milan · EUR · Azione")).to_be_visible()
    expect(pagina.get_by_text("Ferrari Ucits Etf · FERRX.MI")).to_be_visible()
    pagina.get_by_role("button", name="➕").first.click()
    expect(pagina.get_by_text("Aggiunto Ferrari S.p.A. (FERR.MI)")).to_be_visible()
    controlla(pagina)
    expect(pagina.get_by_text("Ticker usati:")).to_contain_text("FERR.MI → FERR.MI")


# ------------------------------------------------------------------ v1.4: fondo comune non trovato -> storico delle quote da CSV
def test_fondo_non_trovato_errore_rosso_csv_semaforo_verde_e_simulazione(pagina, tmp_path):
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "strumenti"))
    from crea_csv_esempio import crea

    carica_config(pagina, "config_fondo.yaml")
    controlla(pagina)
    # errore rosso con il messaggio chiaro e i due pulsanti; la simulazione non parte
    expect(pagina.get_by_text("È un fondo comune non quotato e non è disponibile nelle fonti online").first).to_be_visible()
    expect(pagina.get_by_role("button", name="Carica lo storico delle quote")).to_be_visible()
    expect(pagina.get_by_role("button", name="Scegli un proxy")).to_be_visible()
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_disabled()
    # caricamento del CSV di esempio (generato con date aggiornate): anteprima e conferma
    pagina.get_by_role("button", name="Carica lo storico delle quote").click()
    csv = crea(str(tmp_path / "storico.csv"))
    pagina.locator("[data-testid=stFileUploader]").filter(has_text="File CSV dello storico").locator("input[type=file]").set_input_files(csv)
    expect(pagina.get_by_text("valori dal").first).to_be_visible()
    pagina.get_by_role("button", name="Conferma e usa questo storico").click()
    # semaforo verde: nessun errore e nessun avviso, la fonte è il CSV importato
    expect(pagina.get_by_text("0 avvisi, 0 errori").first).to_be_visible(timeout=60000)
    expect(pagina.get_by_text("Ticker usati:")).to_contain_text("LU0210536198 → LU0210536198")
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_enabled()
    # simulazione completa senza errori Streamlit
    pagina.get_by_role("button", name="Avvia simulazione").first.click()
    bottone_html = pagina.get_by_role("button", name="Report HTML")
    expect(bottone_html).to_be_visible(timeout=300000)
    expect(pagina.locator(ERRORI_STREAMLIT)).to_have_count(0)
    with pagina.expect_download() as d:
        bottone_html.click()
    html = pathlib.Path(d.value.path()).read_text(encoding="utf-8")
    assert "CSV importato" in html and "Costi annui usati" in html


# ------------------------------------------------------------------ v1.5: modello a fattori nel browser vero
def test_modello_a_fattori_completo_senza_errori_streamlit(pagina, tmp_path):
    import yaml

    raw = yaml.safe_load((pathlib.Path(__file__).resolve().parents[2] / "configurazioni/esempio_tre_portafogli.yaml").read_text(encoding="utf-8"))
    raw["n_simulazioni"] = 500
    raw["modello_simulazione"] = "fattori"
    raw["moduli"] = {"stress_test": True, "verifica_convergenza": False, "backtest_var": True, "scomposizione_rischio": True}
    f = tmp_path / "fattori.yaml"
    f.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    pagina.locator("input[type=file]").last.set_input_files(str(f))
    expect(pagina.get_by_text("caricata.")).to_be_visible()
    pagina.get_by_role("button", name="Avvia simulazione").first.click()
    expect(pagina.get_by_role("button", name="Report HTML")).to_be_visible(timeout=600000)
    expect(pagina.locator(ERRORI_STREAMLIT)).to_have_count(0)
    for nome in ("Da dove viene il rischio", "Validazione del modello"):
        pagina.get_by_role("tab", name=nome, exact=True).click()
        pagina.wait_for_timeout(500)
        expect(pagina.locator(ERRORI_STREAMLIT)).to_have_count(0)
        expect(pagina.get_by_text("Niente da mostrare")).to_have_count(0)
