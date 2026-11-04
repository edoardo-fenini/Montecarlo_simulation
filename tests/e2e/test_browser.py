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
    expect(pagina.get_by_text("0 errori").first).to_be_visible()
    # contenuto della tabella (canvas) verificato dal testo associato, non dal canvas
    usati = pagina.get_by_text("Ticker usati:")
    expect(usati).to_contain_text(f"{ISIN} → SWDA.MI")
    expect(usati).to_contain_text("US0378331005 → AAPL")
    expect(pagina.get_by_role("button", name="Avvia simulazione").first).to_be_enabled()

    # cambio della quotazione dal menu: il controllo si rifà e il testo associato cambia
    menu = pagina.get_by_role("combobox", name=re.compile(f"Quotazione scelta per {ISIN}"))
    menu.click()
    menu.press_sequentially("EUNL")  # il menu ha la ricerca: si scrive e si conferma con Invio
    menu.press("Enter")
    expect(pagina.get_by_text("Ticker usati:")).to_contain_text(f"{ISIN} → EUNL.DE")
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
