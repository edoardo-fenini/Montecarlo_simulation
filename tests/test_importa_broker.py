"""v1.3 – importazione del portafoglio da un CSV del broker (senza internet: i prezzi mancanti vengono da una funzione finta)."""

import pathlib

import pytest
import yaml

import importa_broker as B
import importa_portafoglio as CLI

RADICE = pathlib.Path(__file__).resolve().parent.parent
ESEMPIO = RADICE / "esempi/portafoglio_broker_esempio.csv"


def prezzo_finto(codice):
    prezzi = {"IE00BK5BQT80": (90.0, "VWCE.DE"), "AAPL": (200.0, "AAPL"), "ENEL.MI": (8.0, "ENEL.MI")}
    if codice not in prezzi:
        raise LookupError("titolo sconosciuto")
    return prezzi[codice]


@pytest.mark.parametrize(
    "testo,atteso",
    [("1.234,56", 1234.56), ("1,234.56", 1234.56), ("1234,5", 1234.5), ("€ 1 234,00", 1234.0), ("12", 12.0), ("1.234.567", 1234567.0),
     ("0,5", 0.5), ("", None), ("n.d.", None), ("-3,5", -3.5), (7, 7.0), ("1.234", 1.234)],
)  # fmt: skip
def test_numeri_italiani_e_inglesi(testo, atteso):
    assert B.numero(testo) == atteso


def test_esempio_del_repository_salta_intestazione_e_totale_e_usa_il_prezzo_per_la_riga_senza_controvalore():
    r = B.calcola(ESEMPIO.read_bytes(), prezzo_finto)
    pesi = r["pesi"]
    assert set(pesi) == {"IE00B4L5Y983", "IT0003128367", "US0378331005", "IE00BK5BQT80"}
    assert round(sum(pesi.values()), 6) == 100
    assert r["totale"] == pytest.approx(12638.40 + 6280 + 3526.50 + 40 * 90)
    vang = next(x for x in r["righe"] if x["input"] == "IE00BK5BQT80")
    assert vang["controvalore"] == 3600 and vang["ticker"] == "VWCE.DE" and "quantità" in vang["fonte_valore"]
    assert pesi["IE00B4L5Y983"] == pytest.approx(12638.40 / r["totale"] * 100, abs=0.01)
    t = B.tabella_anteprima(r)
    assert list(t.columns) == ["Titolo", "Nome", "Quantità", "Prezzo EUR", "Controvalore EUR", "Peso %", "Valore da"]
    assert t.iloc[0]["Controvalore EUR"] == "12.638,40"


def test_virgola_come_separatore_e_punto_decimale_e_colonne_in_inglese():
    csv = "Symbol,Name,Quantity,Market Value\nAAPL,Apple,10,\"2,000.00\"\nENEL.MI,Enel,100,800.00\n"
    r = B.calcola(csv)
    assert r["pesi"] == {"AAPL": 71.43, "ENEL.MI": 28.57}


def test_solo_quantita_usa_ultimo_prezzo_in_euro():
    r = B.calcola("ISIN;Quantità\nIE00BK5BQT80;10\n", prezzo_finto)
    assert r["pesi"] == {"IE00BK5BQT80": 100.0} and r["righe"][0]["controvalore"] == 900


def test_tabulazione_e_righe_ripetute_sommate():
    r = B.calcola("ISIN\tControvalore\nIT0003128367\t100,00\nIT0003128367\t300,00\nUS0378331005\t600,00\n")
    assert r["pesi"] == {"US0378331005": 60.0, "IT0003128367": 40.0}
    assert any("2 righe sommate" in a for a in r["avvisi"])


def test_colonne_di_costo_non_sono_scambiate_per_il_controvalore():
    csv = "ISIN;Quantità;Controvalore di carico;Controvalore di mercato\nIT0003128367;10;10,00;90,00\nUS0378331005;1;90,00;10,00\n"
    r = B.calcola(csv)
    assert r["pesi"] == {"IT0003128367": 90.0, "US0378331005": 10.0}


def test_righe_senza_valori_e_prezzo_non_trovato_sono_avvisi():
    csv = "ISIN;Quantità;Controvalore\nIT0003128367;0;0\nXX0000000000;5;\nUS0378331005;1;100\n"
    r = B.calcola(csv, prezzo_finto)
    assert r["pesi"] == {"US0378331005": 100.0}
    assert any("riga 2" in a for a in r["avvisi"]) and any("non trovo l'ultimo prezzo" in a for a in r["avvisi"])


def test_errori_chiari():
    with pytest.raises(B.ErroreImport, match="colonne necessarie"):
        B.calcola("Nome;Prezzo\nEnel;3\n")
    with pytest.raises(B.ErroreImport, match="vuoto"):
        B.calcola(b"")
    with pytest.raises(B.ErroreImport, match="nessuna riga"):
        B.calcola("ISIN;Quantità\nIT0003128367;0\n")


def test_codifica_windows_e_bom():
    testo = "ISIN;Quantità;Controvalore\nIT0003128367;1;10,00\n"
    assert B.calcola(testo.encode("cp1252"))["pesi"] == {"IT0003128367": 100.0}
    assert B.calcola(testo.encode("utf-8-sig"))["pesi"] == {"IT0003128367": 100.0}


def test_arrotondamento_somma_cento():
    p = B.arrotonda_pesi({"a": 100 / 3, "b": 100 / 3, "c": 100 / 3})
    assert round(sum(p.values()), 2) == 100 and sorted(p.values()) == [33.33, 33.33, 33.34]


def test_portafoglio_valido_per_la_configurazione():
    import configurazione as C

    r = B.calcola(ESEMPIO.read_bytes(), prezzo_finto)
    cfg = C.prepara({"benchmark": {"nome": "B", "ticker": "IWDA.AS"}, "portafogli": [B.portafoglio(r, "Conto")]})
    assert abs(sum(cfg["composizione"]["Conto"].values()) - 1) < 1e-9


# ------------------------------------------------------------------ riga di comando
def test_riga_di_comando_anteprima_conferma_e_salvataggio(tmp_path, capsys):
    uscita = tmp_path / "conto.yaml"
    base = RADICE / "configurazioni/esempio_tre_portafogli.yaml"
    codice = CLI.main([str(ESEMPIO), "--nome", "Conto", "--base", str(base), "--uscita", str(uscita)], chiedi=lambda m: "s",
                      prezzo_eur=prezzo_finto)  # fmt: skip
    out = capsys.readouterr().out
    assert codice == 0 and "Anteprima del portafoglio «Conto»" in out and "12.638,40" in out
    cfg = yaml.safe_load(uscita.read_text(encoding="utf-8"))
    conto = next(p for p in cfg["portafogli"] if p["nome"] == "Conto")
    assert round(sum(conto["titoli"].values()), 6) == 100 and len(cfg["portafogli"]) > 1  # aggiunto ai portafogli della base


def test_riga_di_comando_senza_conferma_non_scrive(tmp_path, capsys):
    uscita = tmp_path / "x.yaml"
    codice = CLI.main([str(ESEMPIO), "--uscita", str(uscita)], chiedi=lambda m: "n", prezzo_eur=prezzo_finto)
    assert codice == 2 and not uscita.exists() and "Nessun file scritto" in capsys.readouterr().out


def test_riga_di_comando_file_sbagliato(tmp_path, capsys):
    f = tmp_path / "x.csv"
    f.write_text("a;b\n1;2\n")
    assert CLI.main([str(f), "--si"], prezzo_eur=prezzo_finto) == 1
    assert "colonne necessarie" in capsys.readouterr().err
