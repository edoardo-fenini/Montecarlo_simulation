"""v1.4 – fondi comuni e costi: tipo di strumento, codici 0P di Yahoo, storico delle quote da CSV, proxy, costi. Tutto offline."""

import datetime
import json

import numpy as np
import pandas as pd
import pytest
from dati_finti import crea_finto_yahoo
from test_controllo import Mercato, base, config, meta, serie

import analisi
import configurazione as C
import controllo
import dati as D
import fondi
import fonti
import isin
import nav
from dati import ErroreDati

OGGI = datetime.date(2026, 11, 4)
FONDO = "LU0210536198"  # ISIN valido (cifra di controllo giusta)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(fonti.time, "sleep", lambda s: None)


# ------------------------------------------------------------------ tipo di strumento (OpenFIGI simulato)
def voci(tipo1, tipo2, *borse):
    return [{"ticker": f"T{i}", "exchCode": b, "name": "NOME", "securityType": tipo1, "securityType2": tipo2} for i, b in enumerate(borse)]


def risposta(dati):
    return json.dumps([{"data": dati}]).encode()


@pytest.mark.parametrize(
    "dati, atteso",
    [
        (voci("Common Stock", "Common Stock", "US", "UA"), "azione"),
        (voci("ETP", "Mutual Fund", "NA", "LN"), "ETF/ETC"),  # un ETF ha anche securityType2 «Mutual Fund»: vince ETP
        (voci("Open-End Fund", "Mutual Fund", "LX", "GR"), "fondo comune"),
        (voci("Boh", "Boh", "US"), ""),
    ],
)
def test_classifica_tipo(dati, atteso):
    assert isin.classifica_tipo(dati) == atteso


def test_openfigi_restituisce_tipo_e_nome():
    info = {}
    dati = voci("Open-End Fund", "Mutual Fund", "LX", "GR")
    dati[1]["ticker"] = "MSJ6"
    c = isin.candidati_openfigi(FONDO, http=lambda *a, **k: risposta(dati), info=info)
    assert info == {"tipo_strumento": "fondo comune", "nome_isin": "NOME"}
    assert [x["ticker"] for x in c] == ["MSJ6.DE"]  # GR = Xetra; LX (Lussemburgo) non ha suffisso Yahoo


# ------------------------------------------------------------------ codici 0P di Yahoo
def test_riconosce_codici_fondo():
    assert fondi.e_codice_fondo("0P000019CB") and fondi.e_codice_fondo("0P0001LLAM.F") and fondi.e_codice_fondo("XYZ", "MUTUALFUND")
    assert not fondi.e_codice_fondo("AAPL") and not fondi.e_codice_fondo("0P12")


def scheda_fondo(nome, valuta="USD", anni=4.7, ultimo="2026-11-03"):
    primo = datetime.datetime.combine(OGGI - datetime.timedelta(days=int(anni * 365.25)), datetime.time(), datetime.UTC)
    return {"valuta": valuta, "borsa": "OTC", "nome": nome, "tipo": "MUTUALFUND", "primo": int(primo.timestamp()), "volume": 0, "ultimo": ultimo}


CANDIDATI = {
    "0P00000001": scheda_fondo("JPM US Growth A acc USD"),  # giusto
    "0P00000002": scheda_fondo("JPM US Growth A dist USD"),  # classe a distribuzione: penalizzato
    "0P00000003": scheda_fondo("MS INVF US Growth A USD"),  # altro gestore: scartato
    "0P00000004": scheda_fondo("JPM US Growth I acc USD"),  # altra classe (I invece di A): penalizzato
    "0P00000005": scheda_fondo("JPM US Growth A acc USD", anni=0.3),  # storia troppo corta: scartato
    "0P00000006": scheda_fondo("JPM US Growth A acc USD", ultimo="2026-08-01"),  # ultimo prezzo vecchio: scartato
    "0P00000007": scheda_fondo("JPM US Growth Plus A acc USD"),  # parola in più
}


def ricerca_fondi(q):
    return [{"symbol": s, "longname": sc["nome"], "quoteType": "MUTUALFUND"} for s, sc in CANDIDATI.items()]


def test_scelta_del_fondo_migliore():
    ris = fondi.cerca_fondo(
        FONDO, "JPMIF US GROWTH-A USD CAP", ["JPMorgan Funds - US Growth Fund"], OGGI, ricerca_fondi, lambda t: CANDIDATI.get(t)
    )
    tick = [q["ticker"] for q in ris]
    assert tick[0] == "0P00000001"
    assert set(tick) == {"0P00000001", "0P00000002", "0P00000004", "0P00000007"}  # gli altri sono scartati
    assert ris[0]["penalita"] == 0 and ris[0]["avvisi_fondo"][0].startswith("fondo trovato per nome")
    assert next(q for q in ris if q["ticker"] == "0P00000002")["penalita"] > 0


def test_fondo_valuta_attesa_dal_nome():
    assert fondi.valuta_attesa("MSIF GLOBAL OPPORT-A $ ACC") == "USD" and fondi.valuta_attesa("JPM X A EUR") == "EUR"
    assert fondi.classe_attesa("JPMIF US SEL-A USD CAP") == "acc" and fondi.classe_attesa("X A dist USD") == "dist"
    assert fondi.stesso_gestore(["MORGAN ST-US GROWTH"], "MS INVF US Growth A") and not fondi.stesso_gestore(["MORGAN ST-US GROWTH"], "JPM US Growth")


class Rete:
    def __init__(self, dati, ricerca=None, schede=None):
        self.dati, self.ricerca_ris, self.schede, self.n_figi = dati, ricerca or [], schede or {}, 0

    def http(self, url, dati=None, intestazioni=None):
        self.n_figi += 1
        return risposta(self.dati)

    def kw(self):
        return {
            "http": self.http,
            "ispettore": lambda t: self.schede.get(t),
            "ricerca": lambda q: [{"symbol": s, "longname": self.schede[s]["nome"], "quoteType": "MUTUALFUND"} for s in self.ricerca_ris],
            "oggi": OGGI,
        }


def test_risolvi_fondo_non_quotato_trovato_con_codice_0p(tmp_path):
    rete = Rete(voci("Open-End Fund", "Mutual Fund", "LX"), ["0P00000001"], {"0P00000001": CANDIDATI["0P00000001"]})
    for d in rete.dati:
        d["name"] = "JPMIF US GROWTH-A USD CAP"
    r = isin.risolvi(FONDO, str(tmp_path), **rete.kw())
    assert r["ticker"] == "0P00000001" and r["tipo_strumento"] == "fondo comune"
    assert any("non per ISIN" in a for a in r["avvisi_nome"])  # GIALLO: classe da verificare
    # seconda volta: dalla cache, senza rete
    n = rete.n_figi
    assert isin.risolvi(FONDO, str(tmp_path), **rete.kw())["ticker"] == "0P00000001" and rete.n_figi == n


def test_risolvi_fondo_non_trovato_messaggio_chiaro(tmp_path):
    rete = Rete(voci("Open-End Fund", "Mutual Fund", "LX"))
    with pytest.raises(isin.ErroreIsin) as e:
        isin.risolvi(FONDO, str(tmp_path), **rete.kw())
    assert "fondo comune non quotato" in str(e.value) and "caricare lo storico delle quote" in str(e.value) and "proxy" in str(e.value)
    assert e.value.tipo == "fondo comune"
    n = rete.n_figi  # anche l'esito negativo è in cache
    with pytest.raises(isin.ErroreIsin):
        isin.risolvi(FONDO, str(tmp_path), **rete.kw())
    assert rete.n_figi == n


def test_controllo_fondo_non_trovato_ha_tipo_e_flag(tmp_path):
    rete = Rete(voci("Open-End Fund", "Mutual Fund", "LX"))
    m = base()
    cfg = config(["AAA.MI", FONDO])
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=m.scarica)
    e = controllo.controlla(cfg, arch, oggi=OGGI, **{k: v for k, v in rete.kw().items() if k != "oggi"})
    r = next(x for x in e["righe"] if x["input"] == FONDO)
    assert r["esito"] == "ROSSO" and r["fondo_non_trovato"] and r["tipo"] == "fondo comune" and "Puoi caricare lo storico" in r["rossi"][0]
    assert "Tipo" in controllo.tabella(e["righe"]).columns


# ------------------------------------------------------------------ CSV dello storico delle quote
def csv_testo(sep=";", dec=",", fmt="%d/%m/%Y", intest=("Data", "Valore quota"), n=60, ordine="asc", migliaia=False):
    idx = pd.bdate_range("2024-01-02", periods=n)
    val = 1000 + np.arange(n) * 3.25 + 0.5
    righe = list(zip(idx, val))
    if ordine == "desc":
        righe = righe[::-1]

    def num(v):
        t = f"{v:,.2f}" if migliaia else f"{v:.2f}"
        if migliaia:
            t = t.replace(",", "X").replace(".", dec).replace("X", ".")
        else:
            t = t.replace(".", dec)
        return t

    return (sep.join(intest) + "\n" + "\n".join(f"{d.strftime(fmt)}{sep}{num(v)}" for d, v in righe) + "\n").encode()


@pytest.mark.parametrize(
    "kw",
    [
        {},  # ; e virgola, GG/MM/AAAA, intestazioni italiane
        {"sep": ",", "dec": ".", "fmt": "%Y-%m-%d", "intest": ("Date", "NAV")},
        {"sep": "\t", "dec": ",", "intest": ("Data valorizzazione", "Valore unitario quota")},
        {"sep": ";", "dec": ",", "fmt": "%d-%m-%Y", "intest": ("Giorno", "Valore della quota"), "ordine": "desc"},
        {"sep": ";", "dec": ",", "migliaia": True},  # 1.234,50
        {"sep": ",", "dec": ".", "fmt": "%Y-%m-%d", "intest": ("Date", "Close")},
    ],
)
def test_csv_formati_riconosciuti(kw):
    s = nav.leggi(csv_testo(**kw))
    assert len(s) == 60 and s.index.is_monotonic_increasing
    assert s.index[0] == pd.Timestamp("2024-01-02") and s.iloc[0] == pytest.approx(1000.5) and s.iloc[-1] == pytest.approx(1000.5 + 59 * 3.25, abs=0.01)


def test_csv_errori_chiari():
    with pytest.raises(ErroreDati, match="almeno"):
        nav.leggi(csv_testo(n=5))
    with pytest.raises(ErroreDati):
        nav.leggi(b"")


def test_anteprima_prime_e_ultime_righe():
    s = nav.leggi(csv_testo())
    a = nav.anteprima(s)
    assert len(a) == 11 and a.iloc[5]["Data"] == "…" and a.iloc[0]["Data"] == "02/01/2024"
    assert "60 valori" in nav.riassunto(s)
    assert len(nav.anteprima(s.iloc[:6])) == 6


def test_salvataggio_in_cache_e_riuso_nel_controllo(tmp_path):
    s = serie(anni=5, fine="2026-11-03", seed=11)
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=base().scarica)
    nav.salva(arch, FONDO, s, "USD", "Fondo di prova")
    with pytest.raises(ErroreDati, match="Valuta"):
        nav.salva(arch, FONDO, s, "XXX")
    # nuova sessione: stessa cartella, nessuna rete (OpenFIGI non deve essere chiamato)
    def vietato(*a, **k):
        raise AssertionError("la rete non va usata per un ISIN con storico importato")

    arch2 = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=base().scarica)
    e = controllo.controlla(config(["AAA.MI", FONDO]), arch2, oggi=OGGI, http=vietato, ricerca=vietato)
    r = next(x for x in e["righe"] if x["input"] == FONDO)
    assert r["fonte"] == "CSV importato" and r["ticker"] == FONDO and r["tipo"] == "fondo comune" and r["valuta"] == "USD"
    assert r["ultimo"] == s.index[-1].date() and any("storico importato" in i for i in r["info"])
    assert r["esito"] != "ROSSO" and not e["blocca"]
    assert e["cfg"]["isin_mappa"][FONDO] == FONDO


def test_csv_da_configurazione_yaml(tmp_path):
    f = tmp_path / "quote.csv"
    f.write_bytes(_csv_recente())
    cfg = config(["AAA.MI", FONDO], prezzi_da_file={FONDO: {"file": str(f), "valuta": "EUR"}})
    arch = D.Archivio(str(tmp_path / "cache"), log=lambda *a: None, scaricatore=base().scarica)
    e = controllo.controlla(cfg, arch, oggi=OGGI, http=lambda *a, **k: (_ for _ in ()).throw(AssertionError("rete")))
    r = next(x for x in e["righe"] if x["input"] == FONDO)
    assert r["fonte"] == "CSV importato" and r["esito"] != "ROSSO"


def _csv_recente():
    idx = pd.bdate_range(end="2026-11-03", periods=1300)
    v = 100 * np.cumprod(1 + np.random.default_rng(3).normal(0.0003, 0.008, len(idx)))
    return ("Data;Valore quota\n" + "\n".join(f"{d:%d/%m/%Y};{x:.4f}".replace(".", ",") for d, x in zip(idx, v)) + "\n").encode()


# ------------------------------------------------------------------ classe a distribuzione
def serie_con_cedola(cedola=True):
    idx = pd.bdate_range("2018-01-01", "2025-12-31")
    r = np.random.default_rng(1).normal(0.0003, 0.008, len(idx))
    if cedola:
        r[(idx.month == 4) & (idx.day == 10)] -= 0.03  # ogni anno, lo stesso giorno
    return pd.Series(100 * np.cumprod(1 + r), index=idx)


def test_avviso_classe_a_distribuzione():
    assert "DISTRIBUZIONE" in nav.avviso_distribuzione(serie_con_cedola(True))
    assert nav.avviso_distribuzione(serie_con_cedola(False)) is None


def test_avviso_distribuzione_diventa_giallo_nel_controllo(tmp_path):
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=base().scarica)
    s = serie_con_cedola(True)
    s.index = s.index + (pd.Timestamp("2026-11-03") - s.index[-1])  # fino a ieri, così non è «vecchio»
    nav.salva(arch, FONDO, s, "EUR")
    e = controllo.controlla(config(["AAA.MI", FONDO]), arch, oggi=OGGI)
    r = next(x for x in e["righe"] if x["input"] == FONDO)
    assert r["esito"] == "GIALLO" and any("DISTRIBUZIONE" in g for g in r["gialli"])


# ------------------------------------------------------------------ proxy dichiarato
def test_proxy_nel_controllo_e_nel_report(tmp_path):
    rete = Rete(voci("Open-End Fund", "Mutual Fund", "LX"))
    kw = {k: v for k, v in rete.kw().items() if k != "oggi"}
    cfg = config(["AAA.MI", FONDO], proxy_titoli={FONDO: "BBB.DE"})
    arch = D.Archivio(str(tmp_path), log=lambda *a: None, scaricatore=base().scarica)
    e = controllo.controlla(cfg, arch, oggi=OGGI, **kw)
    r = next(x for x in e["righe"] if x["input"] == FONDO)
    assert r["ticker"] == "BBB.DE" and r["proxy"] == "BBB.DE" and r["tipo"] == "fondo comune" and r["esito"] == "GIALLO"
    assert any("dati del proxy BBB.DE, non del fondo" in g for g in r["gialli"])
    assert not e["blocca"] and e["cfg"]["composizione"]["P"].keys() == {"AAA.MI", "BBB.DE"} and e["cfg"]["proxy_usati"] == {FONDO: "BBB.DE"}


def test_proxy_in_analisi_segnalato_nei_risultati(tmp_path):
    cfg = C.prepara(
        {
            "orizzonte_anni": 2, "orizzonti_intermedi": [1], "n_simulazioni": 200,
            "benchmark": {"nome": "Bench", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
            "moduli": {"stress_test": False, "rischio_singolo_titolo": False, "verifica_convergenza": False},
            "proxy_titoli": {FONDO: "AAA.MI"},
            "costi": {FONDO: 0.02},
            "portafogli": [{"nome": "P", "titoli": {FONDO: 50, "CCC": 50}}],
        }
    )  # fmt: skip
    ris = analisi.esegui(cfg, cartella_cache=str(tmp_path), scaricatore=crea_finto_yahoo(), log=lambda *a: None)
    assert any("dati del proxy AAA.MI, non del fondo" in a for a in ris["avvisi"])
    riga = ris["costi"][ris["costi"]["Titolo"].str.contains("proxy")].iloc[0]
    assert riga["Titolo"] == f"{FONDO} (proxy AAA.MI)" and riga["Costo annuo"] == 0.02 and riga["Origine"] == "indicato"


# ------------------------------------------------------------------ costi
def cfg_costi(**extra):
    return C.prepara(
        {"benchmark": {"nome": "Bench", "ticker": "BMK.AS", "ter": 0.002}, "portafogli": [{"nome": "P", "titoli": ["F", "E", "AZ"]}], **extra}
    )


TIPI = {"F": "MUTUALFUND", "E": "ETF", "AZ": "EQUITY"}


def test_costi_default_per_tipo():
    c = cfg_costi()
    assert analisi.costo_titolo(c, "F", TIPI) == (0.015, "default")
    assert analisi.costo_titolo(c, "E", TIPI) == (0.003, "default")
    assert analisi.costo_titolo(c, "AZ", TIPI)[0] == 0.0
    assert analisi.costo_titolo(c, "BENCH") == (0.002, "benchmark")


def test_costi_indicati_hanno_la_precedenza():
    c = cfg_costi(costi={"f": 0.0185, "E": 0.0007})
    assert analisi.costo_titolo(c, "F", TIPI) == (0.0185, "indicato") and analisi.costo_titolo(c, "E", TIPI) == (0.0007, "indicato")
    with pytest.raises(C.ErroreConfig, match="costi"):
        cfg_costi(costi={"F": 0.5})
    with pytest.raises(C.ErroreConfig, match="costi"):
        cfg_costi(costi={"F": "tanto"})


def test_costi_sottratti_dal_rendimento_atteso():
    c = cfg_costi(costi={"F": 0.02})
    cols = [("P", "F"), ("P", "E"), ("P", "AZ")]
    mu = np.array([0.07, 0.07, 0.07])
    M = analisi.prepara_M(c, np.random.default_rng(0).normal(0.0004, 0.01, (5000, 3)), cols, mu, TIPI)
    annuo = (1 + M.mean(axis=0)) ** 252 - 1
    assert annuo[0] == pytest.approx(0.07 - 0.02, abs=0.002)  # fondo: costo indicato
    assert annuo[1] == pytest.approx(0.07 - 0.003, abs=0.002)  # ETF: default
    assert annuo[2] == pytest.approx(0.07, abs=0.002)  # azione: nessun costo
    # con il metodo storico (mu = None) i dati restano com'erano: i prezzi sono già al netto dei costi
    X = np.random.default_rng(1).normal(0.0004, 0.01, (50, 3))
    assert analisi.prepara_M(c, X, cols, None, TIPI) is X


def test_nessun_doppio_conteggio_sul_benchmark():
    c = cfg_costi(costi={"F": 0.02})
    c["portafogli"].append({"nome": "SoloBench", "titoli": ["benchmark"], "pesi": {"benchmark": 1.0}})
    c["composizione"] = C.appiattisci(c)
    t = analisi.spiega_rendimenti(c, {"F": 1.0, "E": 1.0, "AZ": 1.0, "BENCH": 1.0}, TIPI)
    assert t.loc["di cui costi ETF (TER)", "SoloBench"] == pytest.approx(0.002)  # solo il suo TER, una volta
    assert t.loc["di cui costi ETF (TER)", "Bench"] == pytest.approx(0.002)
    tab = analisi.tabella_costi(c, TIPI)
    assert (tab["Origine"] == "benchmark").sum() == 1


def test_avviso_giallo_costi_non_indicati(tmp_path):
    m = Mercato(**{"AAA_MI": (serie(seed=1), meta()), "FND": (serie(seed=2), meta(tipo="MUTUALFUND", nome="Fondo X")),
                   "ETFX": (serie(seed=3), meta(tipo="ETF", nome="Etf X")), "BMK_AS": (serie(seed=4), meta(tipo="ETF"))})  # fmt: skip

    def controlla(**extra):
        arch = D.Archivio(str(tmp_path / str(len(extra))), log=lambda *a: None, scaricatore=m.scarica)
        return controllo.controlla(config(["AAA.MI", "FND", "ETFX"], **extra), arch, oggi=OGGI)

    e = controlla()
    assert "costi non indicati, uso il default 1,50%" in " ".join(next(r for r in e["righe"] if r["input"] == "FND")["gialli"])
    assert "default 0,30%" in " ".join(next(r for r in e["righe"] if r["input"] == "ETFX")["gialli"])
    assert not any("costi non indicati" in g for g in next(r for r in e["righe"] if r["input"] == "AAA.MI")["gialli"])
    e2 = controlla(costi={"FND": 0.02, "ETFX": 0.001})
    assert not any("costi non indicati" in g for r in e2["righe"] for g in r["gialli"])
