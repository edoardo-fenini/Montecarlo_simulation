"""App per confrontare il rischio di portafogli con una simulazione Monte Carlo.
Avvio:  streamlit run app.py   (oppure doppio clic su Avvia.command)"""

from __future__ import annotations

import copy
import os
import re
import time

import pandas as pd
import streamlit as st
import yaml

import analisi
import configurazione as C
import controllo
import dati as D
import fondi
import grafici_app as G
import importa_broker as B
import isin as I
import nav
import registro
import rendimento
import report
import ricerca as R
import stato_app
from dati import ErroreDati

log = registro.configura()
ESEMPIO = "configurazioni/esempio_tre_portafogli.yaml"

AIUTO = {
    "nome": "Serve a riconoscere il report: compare nel titolo e nel nome del file.",
    "tabella": "Una riga per titolo. Scrivi il ticker come su finance.yahoo.com (es. ENEL.MI) oppure l'ISIN (es. IT0003128367): "
    "l'ISIN è riconosciuto da solo e convertito in ticker. Peso in %: vuoto = pesi uguali. "
    "Portafoglio misto: come ticker scrivi il nome di un altro portafoglio oppure «benchmark».",
    "capitale": "Quanto investi all'inizio, in euro.",
    "versamento": "Quanto aggiungi ogni mese (0 = solo l'investimento iniziale). I versamenti seguono i pesi del portafoglio.",
    "orizzonte": "Per quanti anni simulare.",
    "intermedi": "Anni intermedi in cui vedere i risultati, separati da virgola (es. 5, 10).",
    "metodo": "Il rendimento atteso è la crescita media ipotizzata. Volatilità, cadute e correlazioni vengono sempre dalla storia; "
    "con la «ricentratura» si cambia solo la media dei rendimenti storici, per non proiettare nel futuro il passato.",
    "rf": "Rendimento di un investimento senza rischio (es. titoli di Stato a breve).",
    "mrp": "Rendimento in più che il mercato azionario paga in media per il suo rischio.",
    "uguale": "Stesso rendimento medio annuo per tutti i portafogli.",
    "nsim": "Quanti futuri possibili simulare. Più sono, più i risultati sono stabili ma il calcolo è più lungo. "
    "20.000 = risultati stabili (circa ±2%); 1.000 = prova veloce.",
    "rib": "Ogni quanto riportare i titoli ai pesi scelti, pagando il costo di ribilanciamento.",
    "costo": "Costo pagato sull'importo comprato e venduto a ogni ribilanciamento.",
    "seed": "Numero di partenza delle estrazioni casuali: con lo stesso seed si ottengono gli stessi risultati.",
    "b_ticker": "L'ETF di confronto: ticker Yahoo oppure ISIN. Default: iShares Core MSCI World (IWDA.AS).",
    "b_proxy": "Indice usato per gli anni prima della nascita dell'ETF.",
    "aggiorna": "Riscarica i prezzi anche se sono già salvati sul computer (per avere gli ultimi giorni).",
}
SPIEGA_METODO = {
    "beta": "**Beta (consigliato):** rendimento = tasso privo di rischio + beta × premio di mercato. Chi si muove di più con il "
    "mercato rende di più in media; il rischio del singolo titolo non è premiato perché si può diversificare.",
    "uguale": "**Uguale:** stesso rendimento medio per tutti: le differenze dipendono solo dal rischio.",
    "storico": "**Storico:** i rendimenti del passato. ⚠️ Proietta il passato nel futuro: troppo ottimista se scegli titoli che sono già andati bene.",
    "personalizzato": "**Personalizzato:** scegli tu il rendimento medio di ogni portafoglio.",
}
MODULI = {
    "stress_test": (
        "Stress test",
        "Crolli stile 2000-2002 e 2008 e un titolo che perde il 90%: quanto si perde e in quanto tempo si recupera.",
    ),
    "rischio_singolo_titolo": (
        "Rischio sul singolo titolo",
        "Aggiunge la piccola probabilità che un'azione crolli dell'80-100% (fallimento, frode).",
    ),
    "verifica_convergenza": (
        "Le simulazioni bastano?",
        "Ripete il calcolo con 3 seed e controlla che i risultati cambino poco (tempo +50% circa).",
    ),
    "confronto_modelli": (
        "Confronto tra modelli",
        "Rifà i conti con altri due modelli (Student-t e GARCH) e varia il rendimento atteso. Lento.",
    ),
    "analisi_C": (
        "Storia dal 1999 (analisi C)",
        "Allunga la storia fino al 1999 usando ETF di settore per i titoli non ancora quotati. Lento.",
    ),
}

st.set_page_config(page_title="Confronto portafogli", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """<style>
section[data-testid='stSidebar']{width:470px !important;min-width:470px}
.block-container{padding-top:2.2rem;padding-bottom:3rem;max-width:1400px}
h1{font-weight:700 !important;letter-spacing:-.01em}
div[data-testid='stMetricValue']{font-size:1.45rem}
.badge{display:inline-block;color:#fff;border-radius:6px;padding:2px 9px;font-size:.82rem;font-weight:600}
.passo{font-size:2rem;font-weight:700;color:#3366A3;line-height:1}
</style>""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ stato (configurazione <-> controlli)
def tabella_da_cfg(raw: dict) -> pd.DataFrame:
    righe = []
    for p in raw.get("portafogli", []):
        tit = p.get("titoli") or []
        if isinstance(tit, str):
            tit = [t.strip() for t in tit.split(",") if t.strip()]
        if isinstance(tit, list):
            righe += [{"Portafoglio": p["nome"], "Ticker": t, "Peso (%)": None} for t in tit]
        else:
            righe += [
                {"Portafoglio": p["nome"], "Ticker": t, "Peso (%)": (float(w) if w not in (None, "") else None)} for t, w in tit.items()
            ]
    return pd.DataFrame(righe, columns=["Portafoglio", "Ticker", "Peso (%)"])


def applica_cfg(raw: dict) -> None:
    """Porta una configurazione (dizionario come nel file YAML) nei controlli dell'app."""
    cfg = C._unisci(C.DEFAULT, raw)
    ss = st.session_state
    ss.raw = raw
    ss.tabella = tabella_da_cfg(raw)
    ss.versione = ss.get("versione", 0) + 1
    ss.nome = cfg["nome"]
    ss.capitale = float(cfg["capitale_iniziale"])
    ss.versamento = float(cfg["versamento_mensile"])
    ss.orizzonte = int(cfg["orizzonte_anni"])
    ss.intermedi = ", ".join(str(x) for x in cfg["orizzonti_intermedi"])
    ra = cfg["rendimento_atteso"]
    ss.metodo = ra["metodo"]
    ss.rf, ss.mrp, ss.uguale = ra["tasso_privo_rischio"] * 100, ra["premio_mercato"] * 100, ra["valore_uguale"] * 100
    ss.personalizzato = {str(k): float(v) * 100 for k, v in (ra.get("personalizzato") or {}).items()}
    for k in C.DEFAULT["moduli"]:
        ss[f"mod_{k}"] = bool(cfg["moduli"][k])
    ss.nsim = max(500, int(cfg["n_simulazioni"]))
    ss.seed = int(cfg["seed"])
    ss.rib = cfg["ribilanciamento"]
    ss.costo = float(cfg["costo_ribilanciamento"]) * 100
    b = cfg["benchmark"]
    ss.b_nome, ss.b_ticker, ss.b_ter, ss.b_proxy = b["nome"], b["ticker"], float(b["ter"]) * 100, b.get("proxy_storico") or ""
    ss.proxy_scelti = {str(k).replace(" ", "").upper(): str(v).replace(" ", "").upper() for k, v in (cfg.get("proxy_titoli") or {}).items()}
    ss.pop("azione_titolo", None)
    ss.scelte_isin = {str(k).replace(" ", "").upper(): str(v).strip().upper() for k, v in (cfg.get("isin_scelte") or {}).items()}
    ss.pop("controllo", None)


def cfg_da_stato(tabella: pd.DataFrame) -> dict:
    """Costruisce la configurazione (dizionario) dai controlli dell'app."""
    ss = st.session_state
    raw = copy.deepcopy(ss.raw)
    portafogli: dict[str, dict] = {}
    for _, r in tabella.iterrows():
        nome, tick = str(r["Portafoglio"] or "").strip(), str(r["Ticker"] or "").strip()
        if nome in ("", "None") and tick in ("", "None"):
            continue
        if nome in ("", "None") or tick in ("", "None"):
            raise C.ErroreConfig("Nella tabella dei portafogli ogni riga deve avere sia il nome del portafoglio sia il ticker.")
        peso = r["Peso (%)"]
        portafogli.setdefault(nome, {})[tick] = None if pd.isna(peso) else float(peso)
    raw["portafogli"] = [{"nome": n, "titoli": (list(t) if all(v is None for v in t.values()) else t)} for n, t in portafogli.items()]
    try:
        inter = [int(x) for x in str(ss.intermedi).replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise C.ErroreConfig("Orizzonti intermedi: scrivi gli anni separati da virgola, es. 5, 10.") from None
    raw.update(
        {
            "nome": ss.nome or "confronto",
            "capitale_iniziale": ss.capitale,
            "versamento_mensile": ss.versamento,
            "orizzonte_anni": int(ss.orizzonte),
            "orizzonti_intermedi": inter,
            "n_simulazioni": int(ss.nsim),
            "seed": int(ss.seed),
            "ribilanciamento": ss.rib,
            "costo_ribilanciamento": ss.costo / 100,
        }
    )
    # un campo vuoto o non numerico non diventa mai 0: errore chiaro (solo per i campi del metodo scelto)
    ra_vecchio = C.DEFAULT["rendimento_atteso"]
    raw["rendimento_atteso"] = {
        "metodo": ss.metodo,
        "tasso_privo_rischio": rendimento.numero_pct(ss.rf, "Tasso privo di rischio") if ss.metodo == "beta" else ra_vecchio["tasso_privo_rischio"],
        "premio_mercato": rendimento.numero_pct(ss.mrp, "Premio di mercato") if ss.metodo == "beta" else ra_vecchio["premio_mercato"],
        "valore_uguale": rendimento.numero_pct(ss.uguale, "Rendimento medio annuo") if ss.metodo == "uguale" else ra_vecchio["valore_uguale"],
        "personalizzato": {
            k: (rendimento.numero_pct(v, f"Rendimento di «{k}»") if ss.metodo == "personalizzato" else 0.0)
            for k, v in ss.personalizzato.items()
        },
    }
    raw["moduli"] = {k: bool(ss[f"mod_{k}"]) for k in C.DEFAULT["moduli"]}
    if ss.get("proxy_scelti"):
        raw["proxy_titoli"] = dict(ss.proxy_scelti)
    else:
        raw.pop("proxy_titoli", None)
    if ss.get("scelte_isin"):
        raw["isin_scelte"] = dict(ss.scelte_isin)
    else:
        raw.pop("isin_scelte", None)
    raw["benchmark"] = {
        **(raw.get("benchmark") or {}),
        "nome": ss.b_nome,
        "ticker": ss.b_ticker.strip(),
        "ter": ss.b_ter / 100,
        "proxy_storico": ss.b_proxy.strip() or None,
    }
    return raw


if "raw" not in st.session_state:
    applica_cfg(yaml.safe_load(open(ESEMPIO, encoding="utf-8")))
ss = st.session_state

# copia di sicurezza delle impostazioni: vedi stato_app.py (Streamlit può cancellare lo stato dei widget dopo un errore)
IMPOSTAZIONI = [
    "nome", "capitale", "versamento", "orizzonte", "intermedi", "metodo", "rf", "mrp", "uguale", "nsim", "seed", "rib", "costo",
    "b_nome", "b_ticker", "b_ter", "b_proxy", *(f"mod_{k}" for k in C.DEFAULT["moduli"]),
]  # fmt: skip
if ripristinate := stato_app.conserva(ss, IMPOSTAZIONI):
    log.warning("Impostazioni ripristinate dalla copia di sicurezza: %s", ", ".join(ripristinate))


def pesi_uguali() -> None:
    t = ss.tabella_corrente.copy()
    t = t[~t["Ticker"].astype(str).str.strip().isin(["", "None"])]
    t["Peso (%)"] = t.groupby("Portafoglio")["Ticker"].transform(lambda x: round(100 / len(x), 4))
    ss.tabella = t.reset_index(drop=True)
    ss.versione += 1


def carica_file() -> None:
    f = ss.get("file_cfg")
    if f is None:
        return
    try:
        raw = yaml.safe_load(f.getvalue().decode("utf-8"))
        C.prepara(copy.deepcopy(raw))
        applica_cfg(raw)
        ss.msg_caricamento = ("ok", f"Configurazione «{f.name}» caricata.")
    except (C.ErroreConfig, yaml.YAMLError, UnicodeDecodeError, AttributeError) as e:
        ss.msg_caricamento = ("errore", f"Non riesco a caricare «{f.name}»: {e}")


def conferma_broker() -> None:
    """Aggiunge (o sostituisce, se c'è già un portafoglio con lo stesso nome) il portafoglio dell'anteprima alla tabella."""
    a = ss.pop("anteprima_broker", None)
    if not a:
        return
    t = ss.tabella_corrente.copy()
    t = t[t["Portafoglio"].astype(str).str.strip() != a["nome"]]
    nuove = pd.DataFrame([{"Portafoglio": a["nome"], "Ticker": k, "Peso (%)": v} for k, v in a["ris"]["pesi"].items()])
    ss.tabella = pd.concat([t, nuove], ignore_index=True)[["Portafoglio", "Ticker", "Peso (%)"]]
    ss.versione += 1
    ss.msg_broker = f"Portafoglio «{a['nome']}» aggiunto alla tabella ({len(nuove)} titoli). Ora premi «Controlla i dati»."


def aggiungi_da_ricerca(r: dict, portafoglio: str) -> None:
    """Aggiunge il titolo trovato con la ricerca alla tabella, nel portafoglio indicato (nuovo se non esiste)."""
    portafoglio = (portafoglio or "").strip() or "Nuovo portafoglio"
    t = ss.tabella_corrente.copy()
    stesso = t[t["Portafoglio"].astype(str).str.strip() == portafoglio]
    if (stesso["Ticker"].astype(str).str.upper() == r["ticker"]).any():
        ss.msg_ricerca = ("info", f"{r['ticker']} è già nel portafoglio «{portafoglio}».")
        return
    nuova = pd.DataFrame([{"Portafoglio": portafoglio, "Ticker": r["ticker"], "Peso (%)": None}])
    ss.tabella = pd.concat([t, nuova], ignore_index=True)[["Portafoglio", "Ticker", "Peso (%)"]]
    ss.versione += 1
    con_pesi = stesso["Peso (%)"].notna().any()
    ss.msg_ricerca = (
        "ok",
        f"Aggiunto {r['nome']} ({r['ticker']}) a «{portafoglio}»."
        + (" Il portafoglio ha già dei pesi: scrivi il peso del nuovo titolo nella tabella (o premi «Pesi uguali»)." if con_pesi else ""),
    )


def anteprima_broker(f, nome: str) -> None:
    """Legge il CSV del broker e prepara l'anteprima (scarica l'ultimo prezzo solo per i titoli senza controvalore)."""
    try:
        opz = C._unisci(C.DEFAULT, ss.raw)["isin"]
        with st.spinner("Leggo il file (e cerco gli ultimi prezzi dei titoli senza controvalore)…"):
            ris = B.calcola(f.getvalue(), B.prezzo_da_archivio(D.Archivio(log=lambda *a: None), opz))
        ss.anteprima_broker = {"ris": ris, "nome": nome.strip() or "Portafoglio importato", "file": f.name}
    except (B.ErroreImport, ErroreDati) as e:
        ss.pop("anteprima_broker", None)
        st.error(f"Non riesco a importare «{f.name}»: {e}")


def carica_esempio() -> None:
    applica_cfg(yaml.safe_load(open(ESEMPIO, encoding="utf-8")))
    ss.pop("ris", None)
    ss.pop("ris_stato", None)


# ------------------------------------------------------------------ rendering dei blocchi del report
def md(testo: str) -> str:
    """Mini-HTML dei blocchi -> markdown di Streamlit."""
    t = str(testo).replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*")
    return re.sub(r"<br\s*/?>", "  \n", t)


def tabella_html(t: dict) -> None:
    righe = len(t["righe"])
    contenuto = f"<style>{report.CSS_APP}</style><div class='rep'>{report._html_tab(t)}</div>"
    if righe > 12:
        with st.expander(f"Mostra la tabella ({righe} righe)"):
            st.html(contenuto)
    else:
        st.html(contenuto)


def schede_native(d: dict) -> None:
    """Card per portafoglio: livello di rischio (numero, nome, quadratini, colore) e numeri chiave rispetto al benchmark."""
    schede = d["schede"]
    bench = next((s for s in schede if s["benchmark"]), None)
    for i in range(0, len(schede), 4):
        colonne = st.columns(4)
        for col, s in zip(colonne, schede[i : i + 4]):
            with col.container(border=True):
                st.markdown(f"<span style='color:{s['colore']};font-size:1.3rem'>■</span> **{s['nome']}**", unsafe_allow_html=True)
                st.markdown(
                    f"<span class='badge' style='background:{s['livello_colore']}'>Rischio {s['livello']}/5 · {s['livello_nome']}</span>"
                    f" &nbsp;{report.quadratini(s['livello'])}",
                    unsafe_allow_html=True,
                )
                diff = None if (s["benchmark"] or bench is None) else s["valore_mediano"] - bench["valore_mediano"]
                st.metric(
                    f"Valore mediano a {d['orizzonte']} anni",
                    report.eur(s["valore_mediano"]),
                    delta=None if diff is None else f"{report.eur(diff)} vs benchmark",
                )
                dp = None if (s["benchmark"] or bench is None) else s["prob_perdita"] - bench["prob_perdita"]
                st.metric(
                    "Probabilità di perdita",
                    report.pct(s["prob_perdita"]),
                    delta=None if dp is None else f"{report.num(dp * 100)} punti vs benchmark",
                    delta_color="inverse",
                )
                st.metric("Calo massimo tipico", report.pct(s["mdd"]))
                st.caption(
                    f"Volatilità annua {report.pct(s['vol'])}"
                    + ("" if s["benchmark"] else f" · {report.num(s['vol_vs_bench'])} volte il benchmark")
                )


def mostra_blocchi(blocchi: list) -> None:
    for b in blocchi:
        k = b[0]
        if k in ("h2", "h3"):
            st.subheader(b[1])
        elif k == "sottotitolo":
            st.markdown(f"**{b[1]}**")
        elif k == "p":
            st.markdown(md(b[1]), unsafe_allow_html=True)
        elif k == "nota":
            st.caption(md(b[1]), unsafe_allow_html=True)
        elif k == "didascalia":
            st.caption("💡 " + md(b[1]), unsafe_allow_html=True)
        elif k == "warn":
            st.warning(md(b[1]))
        elif k == "box":
            with st.container(border=True):
                st.markdown("\n".join(f"- {md(x)}" for x in b[1]), unsafe_allow_html=True)
        elif k == "lista":
            st.markdown("\n".join(f"- {md(x)}" for x in b[1]), unsafe_allow_html=True)
        elif k == "tab":
            tabella_html(b[1])
        elif k == "schede":
            schede_native(b[1])
        elif k == "img":
            st.image(b[1], width="stretch")
        elif k == "dettagli":
            with st.expander(b[1]):
                mostra_blocchi(b[2])


def senza_immagini(blocchi: list) -> list:
    return [b for b in blocchi if b[0] not in ("img", "didascalia")]


# ------------------------------------------------------------------ controllo dei dati
def chiave_dati(tabella: pd.DataFrame) -> str | None:
    """Impronta di ciò che il controllo guarda (titoli, benchmark, regole ISIN, soglie). None se le impostazioni non sono valide."""
    try:
        g = cfg_da_stato(tabella)
    except C.ErroreConfig:
        return None
    parti = {k: g.get(k) for k in ("portafogli", "isin", "isin_scelte", "nomi_attesi", "controllo_dati", "prezzi_da_file", "proxy_titoli")}
    parti["benchmark"] = (g.get("benchmark") or {}).get("ticker")
    return yaml.safe_dump(parti, sort_keys=True, allow_unicode=True)


def chiave_completa(tabella: pd.DataFrame) -> str | None:
    """Impronta di TUTTE le impostazioni (per sapere se i risultati in memoria corrispondono ancora ai controlli). None se non valide."""
    try:
        return yaml.safe_dump(cfg_da_stato(tabella), sort_keys=True, allow_unicode=True)
    except (C.ErroreConfig, yaml.YAMLError):
        return None


def calcola_controllo(grezza: dict, aggiorna: bool):
    """Controlla tutti i titoli (scarica i prezzi mancanti). Ritorna (esito, archivio dei prezzi già aperto)."""
    cfg = C.prepara(copy.deepcopy(grezza))
    arch = D.Archivio(aggiorna=bool(aggiorna), log=lambda *a: None)
    esito = controllo.controlla(cfg, arch, log=lambda *a: None)
    esito["rendimenti"] = controllo.rendimenti_attesi(esito, arch)
    return esito, arch


def scegli_quotazione(isin_cod: str, chiave_widget: str, predefinita: str) -> None:
    """Menu «quotazione»: salva la scelta e chiede di rifare il controllo."""
    scelta = ss[chiave_widget]
    if scelta == predefinita:
        ss.scelte_isin.pop(isin_cod, None)
    else:
        ss.scelte_isin[isin_cod] = scelta
    ss.ricontrolla = True


def etichetta_quotazione(q: dict) -> str:
    return (
        f"{q['ticker']} · {q['borsa']} · {q['valuta']} · {report.num(q['storia_anni'])} anni di storia · "
        f"volume medio {report.num_it(int(q['volume_medio']))}"
    )


def form_storico_quote(r: dict, cod: str) -> None:
    """Caricamento del CSV dello storico delle quote: anteprima, valuta, conferma. Salvato in cache con l'ISIN come chiave."""
    f = st.file_uploader(
        "File CSV dello storico delle quote (una colonna con la data e una con il valore della quota)",
        type=["csv", "txt"],
        key=f"up_nav_{cod}",
        help="Separatore ; o , · decimali con la virgola o il punto · date GG/MM/AAAA o AAAA-MM-GG · intestazioni in italiano o inglese.",
    )
    if not f:
        return
    try:
        serie = nav.leggi(f.getvalue())
    except ErroreDati as err:
        st.error(str(err))
        return
    st.caption("**Anteprima** (controlla che date e valori siano letti bene): " + nav.riassunto(serie))
    st.dataframe(nav.anteprima(serie), hide_index=True, width="stretch", key=f"prev_nav_{cod}")
    if (avviso := nav.avviso_distribuzione(serie)) is not None:
        st.warning("🟡 Attenzione: " + avviso)
    attesa = fondi.valuta_attesa(r.get("nome") or "") or "EUR"
    valuta = st.selectbox(
        "Valuta della serie",
        nav.VALUTE,
        index=nav.VALUTE.index(attesa),
        key=f"val_nav_{cod}",
        help="La valuta in cui è espresso il valore della quota (la classe del fondo). Verrà convertita in euro.",
    )
    if st.button("✅ Conferma e usa questo storico", type="primary", key=f"ok_nav_{cod}"):
        try:
            nav.salva(D.Archivio(log=lambda *a: None), cod, serie, valuta, r.get("nome") or "")
        except ErroreDati as err:
            st.error(str(err))
            return
        ss.pop("azione_titolo", None)
        ss.ricontrolla = True
        st.rerun()


def form_proxy(cod: str) -> None:
    p = st.text_input(
        "Ticker o ISIN sostitutivo (es. un ETF sullo stesso indice)",
        key=f"in_prx_{cod}",
        help="I dati di questo titolo prenderanno il posto di quelli del fondo. Nel controllo dati e nel report comparirà sempre «dati del proxy».",
    )
    if st.button("✅ Usa questo proxy", type="primary", key=f"ok_prx_{cod}") and p.strip():
        ss.proxy_scelti[cod] = p.replace(" ", "").upper()
        ss.pop("azione_titolo", None)
        ss.ricontrolla = True
        st.rerun()


def pannello_non_trovati(e: dict) -> None:
    """Per ogni titolo non trovato: errore rosso con i due pulsanti (storico delle quote da CSV, proxy). Per i proxy in uso: «Togli il proxy»."""
    for r in e["righe"]:
        cod = I.normalizza(r["input"])
        if r.get("proxy"):
            if st.button(f"↩️ Togli il proxy {r['proxy']} per {r['input']}", key=f"btn_noprx_{cod}"):
                ss.proxy_scelti.pop(cod, None)
                ss.ricontrolla = True
                st.rerun()
            continue
        if r["trovato"] or not r["rossi"] or I.riconosci(r["input"])[0] == "isin_errato":
            continue
        with st.container(border=True):
            testo = I.MESSAGGIO_FONDO_NON_TROVATO if r["fondo_non_trovato"] else "Non trovo questo titolo nelle fonti online: " + "; ".join(r["rossi"]) + ". Puoi caricare lo storico delle quote oppure scegliere un proxy."
            st.error(f"**{r['input']}**{' · ' + r['nome'] if r['nome'] else ''}: {testo}")
            c1, c2 = st.columns(2)
            if c1.button("📥 Carica lo storico delle quote", key=f"btn_nav_{cod}", width="stretch"):
                ss.azione_titolo = (cod, "csv")
            if c2.button("🔁 Scegli un proxy", key=f"btn_prx_{cod}", width="stretch"):
                ss.azione_titolo = (cod, "proxy")
            az = ss.get("azione_titolo")
            if az and az[0] == cod:
                (form_storico_quote(r, cod) if az[1] == "csv" else form_proxy(cod))


def pannello_controllo(chiave_attuale: str | None, con_ris: bool) -> None:
    cc = ss.get("controllo")
    if not cc:
        return
    e = cc["esito"]
    with st.expander("🔎 Controllo dati", expanded=(e["blocca"] or e["gialli"] > 0 or not con_ris)):
        (st.error if e["blocca"] else st.warning if e["gialli"] else st.success)(f"**{e['riepilogo']}**")
        if cc["chiave"] != chiave_attuale:
            st.info("Dopo questo controllo hai cambiato titoli o impostazioni: premi «Controlla i dati» per aggiornarlo.")
        if e["blocca"]:
            st.error(e["messaggio"].replace("\n", "  \n"))
        st.dataframe(
            controllo.tabella(e["righe"]),
            hide_index=True,
            width="stretch",
            column_config={"Dettagli": st.column_config.TextColumn(width="large")},
            key="tabella_controllo",
        )
        usati = [f"{r['input']} → {r['ticker']}" for r in e["righe"] if r["ticker"]]
        if usati:  # la tabella sopra è un canvas: lo stesso contenuto, in testo, per chi usa lo screen reader e per le prove automatiche
            st.caption("Ticker usati: " + " · ".join(usati), help="Gli stessi dati della tabella, in forma di testo.")
        st.caption("🟢 tutto a posto · 🟡 avviso, si può procedere · 🔴 errore, la simulazione non parte finché non lo correggi.")
        pannello_non_trovati(e)
        multi = [r for r in e["righe"] if r.get("risoluzione") and len(r["risoluzione"]["quotazioni"]) > 1]
        for r in multi:
            ris_i = r["risoluzione"]
            elenco = [q["ticker"] for q in ris_i["quotazioni"]]
            etichette = {q["ticker"]: etichetta_quotazione(q) for q in ris_i["quotazioni"]}
            k = f"quot_{r['isin']}"
            if ris_i["ticker"] not in etichette:  # ticker forzato in configurazione, non tra quelli trovati
                elenco.insert(0, ris_i["ticker"])
                etichette[ris_i["ticker"]] = ris_i["ticker"] + " · scelto in configurazione"
            ss[k] = ris_i["ticker"]
            st.selectbox(
                f"Quotazione scelta per {r['isin']} ({r['nome'] or '–'})",
                elenco,
                format_func=etichette.get,
                key=k,
                on_change=scegli_quotazione,
                args=(r["isin"], k, ris_i["predefinito"]),
                help=f"Trovate {len(elenco)} quotazioni con {ris_i['metodo']}. Scelta automatica: {ris_i['predefinito']} "
                "(preferisce EUR, poi Borsa Italiana, Xetra, Amsterdam; poi più storia e volumi).",
            )


def pannello_rendimento(chiave_attuale: str | None) -> None:
    """Riquadro «Rendimento atteso»: cosa userà la simulazione (e il beta), con avvisi gialli e rossi."""
    avvisi = rendimento.avvisi_campi(ss.metodo, ss.rf, ss.mrp, ss.uguale, ss.personalizzato)
    cc = ss.get("controllo")
    rend = cc["esito"].get("rendimenti") if cc and cc["chiave"] == chiave_attuale else None
    avvisi += rendimento.avvisi_tabella(rend)
    with st.expander("📈 Rendimento atteso che verrà usato", expanded=bool(avvisi) or rend is not None):
        for livello, testo in avvisi:
            (st.error if livello == rendimento.ROSSO else st.warning)(("🔴 " if livello == rendimento.ROSSO else "🟡 ") + testo)
        if rend is not None:
            t = rend.T.copy()
            t.columns = ["Beta", "Rendimento atteso annuo", "di cui costi (TER)"]
            if ss.metodo != "beta":
                t = t.drop(columns="Beta")
            st.dataframe(t.style.format({c: "{:.2%}" if c != "Beta" else "{:.2f}" for c in t.columns}), width="stretch", key="tabella_rendimenti")
            st.caption("Rendimento medio annuo (prima dei costi) che la simulazione assegna a ogni portafoglio; i costi (TER) vengono sottratti.")
        elif ss.metodo == "beta":
            st.caption("Premi «Controlla i dati» per vedere il beta e il rendimento atteso di ogni portafoglio.")
        elif ss.metodo == "storico":
            st.caption("Con il metodo storico si usano i rendimenti del passato: nessun valore da mostrare prima della simulazione.")


# ------------------------------------------------------------------ barra laterale
with st.sidebar:
    st.title("📊 Impostazioni")
    st.text_input("Nome del confronto", key="nome", help=AIUTO["nome"])

    st.header("1 · Portafogli", divider="gray")
    st.caption(
        "Una riga per titolo. Peso vuoto (compare «None») = pesi uguali. Portafoglio misto: come ticker il nome di un altro "
        "portafoglio oppure `benchmark`."
    )
    tab = st.data_editor(
        ss.tabella,
        key=f"editor_{ss.versione}",
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "Portafoglio": st.column_config.TextColumn(width="medium", help="Nome del portafoglio"),
            "Ticker": st.column_config.TextColumn("Ticker o ISIN", width="small", help=AIUTO["tabella"]),
            "Peso (%)": st.column_config.NumberColumn(
                min_value=0.0, max_value=100.0, format="%.2f", width="small", help="Peso in percentuale; vuoto = pesi uguali"
            ),
        },
    )
    ss.tabella_corrente = tab
    c1, c2 = st.columns(2)
    c1.button("Pesi uguali", on_click=pesi_uguali, width="stretch", key="btn_pesi_uguali", help="Imposta pesi uguali dentro ogni portafoglio.")
    c2.button("Ricarica esempio", on_click=carica_esempio, width="stretch", key="btn_ricarica_esempio", help="Torna ai tre portafogli di esempio.")

    with st.expander("🔍 Cerca un titolo per nome", expanded=bool(ss.get("risultati_ricerca"))):
        c1, c2 = st.columns([3, 1])
        testo_ricerca = c1.text_input(
            "Nome dell'azienda o dell'ETF", key="ricerca_testo", placeholder="es. Enel, MSCI World, Apple", label_visibility="collapsed"
        )
        if c2.button("Cerca", width="stretch", key="btn_cerca", disabled=len(testo_ricerca.strip()) < 2):
            try:
                with st.spinner("Cerco su Yahoo Finance…"):
                    ss.risultati_ricerca = {"testo": testo_ricerca.strip(), "righe": R.cerca(testo_ricerca)}
            except R.ErroreRicerca as e:
                ss.risultati_ricerca = None
                st.error(str(e))
        if ss.get("msg_ricerca"):
            tipo_m, testo_m = ss.pop("msg_ricerca")
            (st.success if tipo_m == "ok" else st.info)(testo_m)
        rr = ss.get("risultati_ricerca")
        if rr:
            if not rr["righe"]:
                st.info(f"Nessun risultato per «{rr['testo']}». Prova con un altro nome o con l'ISIN.")
            else:
                nomi_esistenti = list(dict.fromkeys(str(x).strip() for x in tab["Portafoglio"] if str(x).strip() not in ("", "None")))
                dest = st.selectbox(
                    "Aggiungi al portafoglio",
                    nomi_esistenti + ["➕ Nuovo portafoglio"],
                    key="ricerca_destinazione",
                    help="Il titolo viene aggiunto come nuova riga della tabella qui sopra.",
                )
                if dest == "➕ Nuovo portafoglio":
                    dest = st.text_input("Nome del nuovo portafoglio", value="Nuovo portafoglio", key="ricerca_nuovo_nome")
                st.caption(f"Risultati per «{rr['testo']}» (al massimo {R.MASSIMO}): nome · ticker · ISIN · borsa · valuta · tipo")
                for i, r in enumerate(rr["righe"]):
                    c1, c2 = st.columns([5, 1])
                    c1.markdown(f"<small>{R.etichetta(r)}</small>", unsafe_allow_html=True)
                    c2.button("➕", key=f"btn_aggiungi_{i}_{r['ticker']}", help=f"Aggiungi {r['ticker']}", on_click=aggiungi_da_ricerca,
                              args=(r, dest))  # fmt: skip

    with st.expander("📥 Importa il portafoglio dal broker (CSV)", expanded="anteprima_broker" in ss):
        st.caption(
            "CSV esportato dal broker con almeno **ISIN (o ticker) e quantità**, oppure **ISIN e controvalore**. Separatore «;» o «,», "
            "decimali con la virgola o con il punto. I pesi si ricavano dai controvalori (quantità × ultimo prezzo in EUR se manca il "
            "controvalore). Esempio: esempi/portafoglio_broker_esempio.csv."
        )
        f_broker = st.file_uploader("File CSV del broker", type=["csv", "txt"], key="file_broker")
        nome_broker = st.text_input("Nome del portafoglio", value="Portafoglio importato", key="nome_broker")
        if st.button("👀 Mostra anteprima", width="stretch", disabled=f_broker is None, key="btn_anteprima_broker"):
            anteprima_broker(f_broker, nome_broker)
        if ss.get("msg_broker"):
            st.success(ss.pop("msg_broker"))
        a_b = ss.get("anteprima_broker")
        if a_b:
            st.markdown(f"**Anteprima di «{a_b['nome']}»** da `{a_b['file']}` · totale {report.eur(a_b['ris']['totale'])}")
            st.dataframe(B.tabella_anteprima(a_b["ris"]), hide_index=True, width="stretch", key="tabella_anteprima_broker")
            for x in a_b["ris"]["avvisi"]:
                st.warning(x)
            c1, c2 = st.columns(2)
            c1.button("✅ Conferma e aggiungi", type="primary", width="stretch", on_click=conferma_broker, key="btn_conferma_broker")
            c2.button("Annulla", width="stretch", on_click=lambda: ss.pop("anteprima_broker", None), key="btn_annulla_broker")

    with st.expander("📄 Carica prezzi da file"):
        st.caption(
            "Se le fonti online non funzionano, scarica i prezzi a mano (es. Yahoo Finance → Historical data → Download) e "
            "caricali qui. Formato: una colonna con la data e una con il prezzo; vedi esempi/prezzi_esempio.csv."
        )
        f_csv = st.file_uploader("File CSV dei prezzi", type=["csv", "txt"], key="file_prezzi")
        c1, c2 = st.columns(2)
        t_csv = c1.text_input("Ticker", key="ticker_csv", help="Il nome con cui userai questo titolo nella tabella dei portafogli.")
        v_csv = c2.selectbox(
            "Valuta dei prezzi",
            ["EUR", "USD", "GBP", "GBp", "CHF", "JPY", "SEK", "DKK", "NOK", "CAD"],
            key="valuta_csv",
            help="La valuta in cui sono espressi i prezzi del file (GBp = pence).",
        )
        tipo_csv = st.radio(
            "Tipo", ["EQUITY", "ETF"], horizontal=True, key="tipo_csv", format_func=lambda x: "Azione" if x == "EQUITY" else "ETF"
        )
        if st.button("Importa i prezzi", width="stretch", key="btn_importa_prezzi", disabled=f_csv is None or not t_csv.strip()):
            try:
                s_imp = D.Archivio(log=lambda *a: None).importa_csv(t_csv, f_csv.getvalue(), v_csv, tipo_csv)
                st.success(
                    f"Importati {len(s_imp)} prezzi per {t_csv.strip().upper()} dal {s_imp.index[0]:%d/%m/%Y} al "
                    f"{s_imp.index[-1]:%d/%m/%Y}. Ora puoi usare questo ticker nella tabella."
                )
            except ErroreDati as e:
                st.error(str(e))

    st.header("2 · Capitale e orizzonte", divider="gray")
    c1, c2 = st.columns(2)
    c1.number_input("Capitale iniziale (€)", min_value=0.0, step=500.0, key="capitale", help=AIUTO["capitale"])
    c2.number_input("Versamento mensile (€)", min_value=0.0, step=50.0, key="versamento", help=AIUTO["versamento"])
    c1.number_input("Orizzonte (anni)", min_value=1, max_value=50, step=1, key="orizzonte", help=AIUTO["orizzonte"])
    c2.text_input("Orizzonti intermedi", key="intermedi", help=AIUTO["intermedi"])

    st.header("3 · Rendimento atteso", divider="gray")
    st.radio("Metodo", list(SPIEGA_METODO), key="metodo", horizontal=True, help=AIUTO["metodo"])
    st.caption(SPIEGA_METODO[ss.metodo])
    if ss.metodo == "beta":
        c1, c2 = st.columns(2)
        c1.number_input("Tasso privo di rischio (%)", step=0.25, key="rf", help=AIUTO["rf"])
        c2.number_input("Premio di mercato (%)", step=0.25, key="mrp", help=AIUTO["mrp"])
    elif ss.metodo == "uguale":
        st.number_input("Rendimento medio annuo per tutti (%)", step=0.5, key="uguale", help=AIUTO["uguale"])
    elif ss.metodo == "personalizzato":
        nomi = list(dict.fromkeys(str(x).strip() for x in tab["Portafoglio"] if str(x).strip() not in ("", "None"))) + ["benchmark"]
        dfp = pd.DataFrame({"Portafoglio": nomi, "Rendimento (%)": [ss.personalizzato.get(n, ss.uguale) for n in nomi]})
        modp = st.data_editor(dfp, key=f"pers_{ss.versione}", hide_index=True, disabled=["Portafoglio"], width="stretch")
        ss.personalizzato = dict(zip(modp["Portafoglio"], modp["Rendimento (%)"].astype(float)))

    st.header("4 · Moduli e simulazione", divider="gray")
    for k, (et, aiuto) in MODULI.items():
        st.checkbox(et, key=f"mod_{k}", help=aiuto)
    st.number_input("Numero di simulazioni", min_value=500, max_value=100000, step=1000, key="nsim", help=AIUTO["nsim"])
    with st.expander("Benchmark e impostazioni avanzate"):
        st.text_input("Nome del benchmark", key="b_nome")
        st.text_input("Ticker (o ISIN) del benchmark", key="b_ticker", help=AIUTO["b_ticker"])
        st.number_input("TER del benchmark (%)", min_value=0.0, max_value=3.0, step=0.01, key="b_ter", help="Costo annuo dell'ETF.")
        st.text_input("Indice prima della nascita dell'ETF", key="b_proxy", help=AIUTO["b_proxy"])
        st.selectbox("Ribilanciamento", list(C.RIBILANCIAMENTO_MESI), key="rib", help=AIUTO["rib"])
        st.number_input("Costo di ribilanciamento (%)", min_value=0.0, max_value=5.0, step=0.05, key="costo", help=AIUTO["costo"])
        st.number_input("Seed", min_value=0, step=1, key="seed", help=AIUTO["seed"])
    aggiorna = st.checkbox("Aggiorna i dati (riscarica i prezzi)", value=False, help=AIUTO["aggiorna"], key="aggiorna_dati")
    chiave_attuale = chiave_dati(tab)
    cc = ss.get("controllo")
    bloccato = bool(cc and chiave_attuale is not None and cc["chiave"] == chiave_attuale and cc["esito"]["blocca"])
    controlla = st.button(
        "🔎 Controlla i dati",
        width="stretch",
        key="btn_controlla",
        help="Verifica tutti i titoli (anche gli ISIN) prima di simulare: esistenza, storia, prezzi recenti, buchi nei dati.",
    )
    avvia = st.button("▶ Avvia simulazione", type="primary", width="stretch", disabled=bloccato, key="btn_avvia")
    if bloccato:
        da_correggere = ", ".join(r["input"] for r in cc["esito"]["righe"] if r["esito"] == controllo.ROSSO)
        st.error(
            f"Non posso avviare la simulazione: {cc['esito']['rossi']} "
            f"{'titolo ha' if cc['esito']['rossi'] == 1 else 'titoli hanno'} un errore (rosso): **{da_correggere}**. "
            "Correggi o togli i titoli indicati (dettagli in «Controllo dati») e premi di nuovo «Controlla i dati»."
        )

    st.header("Salva / carica", divider="gray")
    try:
        yaml_corrente = yaml.safe_dump(cfg_da_stato(tab), allow_unicode=True, sort_keys=False)
    except C.ErroreConfig:
        yaml_corrente = None
    if yaml_corrente:
        st.download_button(
            "💾 Scarica configurazione (YAML)",
            yaml_corrente,
            file_name=f"{(ss.nome or 'confronto').replace(' ', '_')}.yaml",
            mime="text/yaml",
            width="stretch",
            key="dl_configurazione",
        )
    st.file_uploader("Carica una configurazione salvata", type=["yaml", "yml"], key="file_cfg", on_change=carica_file)
    if ss.get("msg_caricamento"):
        tipo, testo = ss.pop("msg_caricamento")
        (st.success if tipo == "ok" else st.error)(testo)


# ------------------------------------------------------------------ esecuzione
def fase(messaggio: str, n: int) -> str:
    m = messaggio.lower()
    if "dati" in m:
        return "Scarico i prezzi…"
    if "stress" in m:
        return "Calcolo gli stress test…"
    if "seed" in m or "verifica" in m:
        return "Controllo che le simulazioni bastino…"
    if "completato" in m:
        return "Preparo il report…"
    analisi_x = re.search(r"analisi ([abc])", m)
    return f"Simulo {report.num_it(n)} scenari" + (f" (analisi {analisi_x.group(1).upper()})" if analisi_x else "") + "…"


def mmss(secondi: float) -> str:
    secondi = max(0, int(round(secondi)))
    return f"{secondi // 60} min {secondi % 60:02d} s" if secondi >= 60 else f"{secondi} s"


def esegui_simulazione(contenitore) -> None:
    ss.pop("ris", None)
    ss.pop("ris_stato", None)
    ss.pop("mostra_vecchi", None)
    t0 = time.time()
    barra = contenitore.progress(0.0, text="Preparo la simulazione…")

    def progresso(f: float, messaggio: str) -> None:
        f = min(max(f, 0.0), 1.0)
        trascorso = time.time() - t0
        stima = f" · circa {mmss(trascorso * (1 - f) / f)} rimanenti" if f > 0.04 else ""
        barra.progress(f, text=f"{fase(messaggio, int(ss.nsim))} {f * 100:.0f}%{stima}")

    try:
        grezza = cfg_da_stato(tab)
        C.prepara(copy.deepcopy(grezza))  # errori di configurazione subito, prima del controllo dei dati
        barra.progress(0.0, text="Controllo i dati…")
        esito, arch = calcola_controllo(grezza, aggiorna)
        ss.controllo = {"chiave": chiave_attuale, "esito": esito}
        if esito["blocca"]:
            barra.empty()
            contenitore.error("**Simulazione non avviata.** " + esito["messaggio"].replace("\n", "  \n"))
            return
        cfg = esito["cfg"]  # ISIN già convertiti in ticker
        # stessa configurazione e stessi dati già calcolati in questa sessione: risultato istantaneo
        chiave = yaml.safe_dump(grezza, sort_keys=True) + str(D.Archivio(log=lambda *a: None).ultimo_aggiornamento())
        cache = ss.setdefault("cache_risultati", {})
        log.info("Avvio simulazione «%s»: %d portafogli, %d simulazioni", cfg["nome"], len(cfg["portafogli"]), cfg["n_simulazioni"])
        if not aggiorna and chiave in cache:
            ris = cache[chiave]
            log.info("Risultato ripreso dalla cache della sessione")
        else:
            ris = analisi.esegui(
                cfg,
                aggiorna_dati=aggiorna,
                log=lambda m: log.info(m.strip()),
                progresso=progresso,
                archivio=arch,
                controllo=controllo.per_report(esito),
            )
            cache.clear()  # una sola simulazione in memoria, per non occupare troppa RAM
            cache[chiave] = ris
        if ris.get("errore_plausibilita"):  # i risultati non coincidono con il rendimento atteso: non si presentano come validi
            cache.clear()
            barra.empty()
            contenitore.error("🔴 **Risultati non validi.** " + ris["errore_plausibilita"])
            return
        barra.progress(1.0, text="Preparo il report…")
        S = report.sezioni(ris)
        ss.ris, ss.sezioni = ris, S
        ss.ris_stato = {"chiave": chiave_completa(tab), "dati": D.Archivio(log=lambda *a: None).ultimo_aggiornamento()}
        ss.html = report.html_report(ris, S)
        ss.pdf = report.pdf_report(ris, S)
        ss.xlsx = report.excel_report(ris)
        ss.prove_pesi = {}
        try:  # ogni analisi viene salvata in report/ e compare in «Analisi salvate»
            ss.cartella = report.cartella_storico(cfg["nome"])
            report.salva(ris, ss.cartella, S=S, pdf_bytes=ss.pdf)
        except OSError as e:
            log.warning("Non riesco a salvare l'analisi: %s", e)
            ss.cartella = None
        log.info("Simulazione completata in %.0f s", time.time() - t0)
        barra.empty()
    except C.ErroreConfig as e:
        barra.empty()
        contenitore.error(f"**C'è un problema nelle impostazioni.** {e}\n\nCorreggi il valore indicato nella barra a sinistra e riprova.")
    except ErroreDati as e:
        barra.empty()
        contenitore.error(f"**Non riesco a ottenere i dati.** {e}")
    except Exception:  # errore imprevisto: messaggio chiaro a schermo, dettagli tecnici solo nel file di log
        barra.empty()
        log.exception("Errore imprevisto durante la simulazione")
        contenitore.error(
            "**Si è verificato un errore imprevisto.** Controlla i ticker e la connessione a internet, poi riprova. "
            "Se il problema resta, mandami il file **log.txt** che trovi nella cartella del programma "
            f"(`{registro.FILE_LOG}`) insieme alla configurazione (pulsante «Scarica configurazione»)."
        )


def prova_rapida_pesi(ris: dict) -> None:
    """Cursore benchmark/satellite con un ricalcolo veloce (poche simulazioni)."""
    if "matrici" not in ris:
        return
    satelliti = [k for k in ris["nomi"] if k != ris["bench_nome"]]
    with st.container(border=True):
        st.markdown(f"**🎚️ Prova rapida dei pesi: quanto {ris['bench_nome']} e quanto satellite?**")
        c1, c2 = st.columns([2, 3])
        sat = c1.selectbox("Portafoglio satellite", satelliti, key="prova_sat", help="Il portafoglio da affiancare al benchmark.")
        quota = c2.slider(
            f"Quota di {ris['bench_nome']}",
            0,
            100,
            80,
            5,
            format="%d%%",
            key="prova_quota",
            help="0% = tutto nel satellite; 100% = tutto nel benchmark.",
        )
        chiave = (sat, quota)
        if chiave not in ss.setdefault("prove_pesi", {}):
            with st.spinner("Ricalcolo veloce..."):
                ss.prove_pesi[chiave] = analisi.prova_pesi(ris, sat, quota / 100, n=2000)
        p = ss.prove_pesi[chiave]
        H = ris["cfg"]["orizzonte_anni"]
        o = ris["sim"]["A"]["orizzonti"][H]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            f"Valore mediano a {H} anni",
            report.eur(p["valore_mediano"]),
            delta=f"{report.eur(p['valore_mediano'] - o.loc['Valore mediano', sat])} vs solo satellite",
        )
        m2.metric(
            "Probabilità di perdita",
            report.pct(p["prob_perdita"]),
            delta=f"{report.num((p['prob_perdita'] - o.loc['Prob. sotto il versato', sat]) * 100)} punti vs solo satellite",
            delta_color="inverse",
        )
        m3.metric("Calo massimo tipico", report.pct(p["mdd"]))
        m4.metric("Volatilità annua", report.pct(p["vol"]))
        st.caption(
            f"⚠️ Risultato approssimato: {report.num_it(p['n'])} simulazioni sull'analisi A. Per numeri definitivi crea un portafoglio "
            f"misto (es. benchmark {quota} + {sat} {100 - quota}) e rilancia la simulazione completa."
        )


def mostra_salvate() -> None:
    elenco = report.elenco_analisi()
    if not elenco:
        st.info(
            "Non ci sono ancora analisi salvate. Ogni simulazione completata viene salvata qui automaticamente, nella cartella «report»."
        )
        return
    tab_el = pd.DataFrame(
        [
            {
                "Data": r["creato"].replace("T", " ")[:16],
                "Nome": r["nome"],
                "Portafogli": ", ".join(p["nome"] for p in r["portafogli"]),
                "Simulazioni": r["simulazioni"],
                "Anni": r["orizzonte"],
                "Metodo": r["metodo"],
                "Dati al": r["dati_al"],
            }
            for r in elenco
        ]
    )
    st.dataframe(tab_el, hide_index=True, width="stretch", key="salvate_elenco")
    etichette = [f"{r['creato'].replace('T', ' ')[:16]} – {r['nome']}" for r in elenco]
    st.subheader("Apri un'analisi")
    scelta = st.selectbox("Analisi", range(len(elenco)), format_func=lambda i: etichette[i], key="salvata_scelta")
    r = elenco[scelta]
    cols = st.columns(4)
    for col, (file, et, mime) in zip(
        cols,
        [
            ("report.html", "⬇️ HTML", "text/html"),
            ("report.pdf", "⬇️ PDF", "application/pdf"),
            ("report.xlsx", "⬇️ Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("configurazione_usata.yaml", "⬇️ Configurazione", "text/yaml"),
        ],
    ):
        percorso = f"{r['cartella']}/{file}"
        try:
            col.download_button(et, open(percorso, "rb").read(), file_name=file, mime=mime, width="stretch", key=f"dl_salvata_{os.path.basename(r['cartella'])}_{file}")
        except OSError:
            col.caption(f"{file} non disponibile")
    if st.toggle("Mostra il report qui", key="salvata_mostra"):
        try:
            import streamlit.components.v1 as components

            components.html(open(f"{r['cartella']}/report.html", encoding="utf-8").read(), height=900, scrolling=True)
        except OSError:
            st.warning("Il file report.html non c'è più.")
    st.subheader("Confronta due analisi")
    due = st.multiselect(
        "Scegli due analisi",
        range(len(elenco)),
        format_func=lambda i: etichette[i],
        max_selections=2,
        key="salvate_confronto",
        placeholder="Scegli due analisi da mettere a confronto",
    )
    if len(due) == 2:
        for col, i in zip(st.columns(2), due):
            with col.container(border=True):
                ri = elenco[i]
                st.markdown(
                    f"**{etichette[i]}**  \n{report.num_it(ri['simulazioni'])} simulazioni · {ri['orizzonte']} anni · metodo {ri['metodo']}"
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Portafoglio": p["nome"],
                                f"Mediana a {ri['orizzonte']} anni": report.eur(p["valore_mediano"]),
                                "Prob. perdita": report.pct(p["prob_perdita"]),
                                "Calo tipico": report.pct(p["mdd"]),
                                "Rischio": f"{p['livello']}/5 {p['livello_nome']}",
                            }
                            for p in ri["portafogli"]
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                    key=f"salvate_confronto_{os.path.basename(ri['cartella'])}",
                )
        a1, a2 = (elenco[i] for i in due)
        comuni = [p["nome"] for p in a1["portafogli"] if p["nome"] in {q["nome"] for q in a2["portafogli"]}]
        if comuni:
            d1 = {p["nome"]: p for p in a1["portafogli"]}
            d2 = {p["nome"]: p for p in a2["portafogli"]}
            st.caption("Differenze per i portafogli presenti in entrambe (seconda meno prima):")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Portafoglio": k,
                            "Mediana": report.eur(d2[k]["valore_mediano"] - d1[k]["valore_mediano"]),
                            "Prob. perdita (punti)": report.num((d2[k]["prob_perdita"] - d1[k]["prob_perdita"]) * 100),
                            "Calo tipico (punti)": report.num((d2[k]["mdd"] - d1[k]["mdd"]) * 100),
                        }
                        for k in comuni
                    ]
                ),
                hide_index=True,
                width="stretch",
                key="salvate_differenze",
            )


st.title("Confronto del rischio di portafogli")
scheda_sim, scheda_salvate = st.tabs(["🧮 Simulazione", "🗂️ Analisi salvate"])
zona_messaggi = scheda_sim.container()
avvia = (avvia or ss.pop("avvia_ora", False)) and not bloccato  # pulsante della pagina iniziale (il callback gira prima dello script)

with scheda_sim:
    if "ris" not in ss and not avvia:
        st.markdown(
            "Simula migliaia di futuri possibili per i tuoi portafogli e ne confronta il **rischio**: quanto possono "
            "scendere, quanto è probabile perdere, quanto tempo serve per recuperare. Tutto in euro, con dati reali di borsa."
        )
        passi = [
            ("1", "Definisci i portafogli", "Nella barra a sinistra: titoli e pesi. C'è già un esempio con tre portafogli e l'MSCI World."),
            ("2", "Scegli capitale e orizzonte", "Capitale iniziale, versamento mensile, anni e metodo del rendimento atteso."),
            ("3", "Avvia", "Premi «Avvia simulazione». In pochi minuti hai i risultati e il report in HTML e PDF."),
        ]
        for col, (n, titolo, testo) in zip(st.columns(3), passi):
            with col.container(border=True):
                st.markdown(f"<div class='passo'>{n}</div>", unsafe_allow_html=True)
                st.markdown(f"**{titolo}**")
                st.caption(testo)
        nomi_pf = list(dict.fromkeys(str(x).strip() for x in tab["Portafoglio"] if str(x).strip() not in ("", "None")))
        st.markdown(
            "**Pronto da lanciare:** "
            + " · ".join(nomi_pf + [ss.b_nome])
            + f" — {report.eur(ss.capitale)} iniziali, {ss.orizzonte} anni, {report.num_it(int(ss.nsim))} simulazioni."
        )
        st.button(
            "▶ Avvia la simulazione con queste impostazioni",
            type="primary",
            on_click=lambda: ss.update(avvia_ora=True),
            disabled=bloccato,
            key="btn_avvia_pagina_iniziale",
        )
        st.caption("Questo strumento non è consulenza finanziaria.")

    if controlla or ss.pop("ricontrolla", False):
        try:
            with st.spinner("Controllo i dati (scarico i prezzi mancanti)…"):
                esito_c, _ = calcola_controllo(cfg_da_stato(tab), aggiorna)
            ss.controllo = {"chiave": chiave_attuale, "esito": esito_c}
            if esito_c["blocca"]:
                st.rerun()  # per disattivare subito «Avvia simulazione»
        except C.ErroreConfig as e:
            zona_messaggi.error(f"**C'è un problema nelle impostazioni.** {e}")
        except ErroreDati as e:
            zona_messaggi.error(f"**Non riesco a controllare i dati.** {e}")

    if avvia:
        esegui_simulazione(zona_messaggi)

    motivo_vecchi = None
    if "ris" in ss:
        motivo_vecchi = controllo.motivo_risultati_vecchi(
            ss.get("ris_stato"),
            chiave_completa(tab),
            D.Archivio(log=lambda *a: None).ultimo_aggiornamento(),
            ss.get("controllo"),
            chiave_attuale,
        )
    pannello_controllo(chiave_attuale, "ris" in ss)
    pannello_rendimento(chiave_attuale)

    if motivo_vecchi:
        st.error(f"### ⚠️ {controllo.AVVISO_RISULTATI_VECCHI}\n\nMotivo: {motivo_vecchi}.", icon="⚠️")
        st.toggle("Mostra comunque i vecchi risultati", key="mostra_vecchi", help="Solo per consultarli: non rispecchiano le impostazioni attuali.")

    if "ris" in ss and (not motivo_vecchi or ss.get("mostra_vecchi")):
        ris, S = ss.ris, ss.sezioni
        st.caption("📅 " + report.intestazione(ris))
        c1, c2, c3, _ = st.columns([1, 1, 1, 2])
        nome_file = f"report_{(ris['cfg']['nome'] or 'confronto').replace(' ', '_')}"
        c1.download_button("⬇️ Report HTML", ss.html, file_name=f"{nome_file}.html", mime="text/html", width="stretch", key="dl_report_html")
        c2.download_button(
            "⬇️ Report PDF", ss.pdf, file_name=f"{nome_file}.pdf", mime="application/pdf", width="stretch", key="dl_report_pdf"
        )
        c3.download_button(
            "⬇️ Excel",
            ss.xlsx,
            file_name=f"{nome_file}.xlsx",
            width="stretch",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_report_excel",
        )
        if ss.get("cartella"):
            st.caption(f"Analisi salvata in `{ss.cartella}`: la ritrovi nella scheda «Analisi salvate».")
        schede = st.tabs(report.SCHEDE)
        anal = [a for a in ris["sim"] if a != "C"]
        for scheda, nome in zip(schede, report.SCHEDE):
            with scheda:
                blocchi = S.get(nome) or []
                if nome == "Sintesi":
                    d = report.dati_schede(ris)
                    bench = next(s for s in d if s["benchmark"])
                    for col, s in zip(st.columns(len(d)), d):
                        diff = None if s["benchmark"] else s["valore_mediano"] - bench["valore_mediano"]
                        col.metric(
                            s["nome"],
                            report.eur(s["valore_mediano"]),
                            delta=None if diff is None else f"{report.eur(diff)} vs benchmark",
                            help=f"Valore mediano a {ris['cfg']['orizzonte_anni']} anni; probabilità di perdita {report.pct(s['prob_perdita'])}",
                        )
                    prova_rapida_pesi(ris)
                    mostra_blocchi(blocchi)
                elif nome == "Fan chart":
                    st.caption(
                        "Passa il mouse sul grafico per leggere mediana, 5° e 95° percentile di ogni anno; clicca su un nome nella "
                        "legenda per nasconderlo. La zona rossa è sotto il capitale investito."
                    )
                    fasce = st.toggle("Mostra le fasce 5°–95°", value=True, key="fan_fasce")
                    for a in anal:
                        st.subheader(report.NOME_ANALISI[a])
                        st.plotly_chart(G.fan_chart(ris, a, fasce), width="stretch", theme="streamlit", key=f"fan_{a}")
                        st.caption("💡 " + report.didascalia_fan(ris, a))
                elif nome == "Drawdown":
                    for a in anal:
                        st.subheader(f"{report.NOME_ANALISI[a]}: calo massimo nei {ris['cfg']['orizzonte_anni']} anni")
                        st.plotly_chart(G.istogramma_mdd(ris, a), width="stretch", theme="streamlit", key=f"mdd_{a}")
                    st.caption("💡 " + report.didascalia_mdd(ris))
                    mostra_blocchi(senza_immagini(blocchi))
                elif blocchi:
                    mostra_blocchi(blocchi)
                else:
                    st.info("Niente da mostrare: modulo non attivato.")

with scheda_salvate:
    mostra_salvate()
