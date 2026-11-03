"""App per confrontare portafogli con una simulazione Monte Carlo.
Avvio:  streamlit run app.py   (oppure doppio clic su Avvia.command)"""
import copy
import traceback

import pandas as pd
import streamlit as st
import yaml

import analisi
import configurazione as C
import report
from dati import ErroreDati

ESEMPIO = "configurazioni/esempio_tre_portafogli.yaml"
SPIEGA_METODO = {
    "beta": "Rendimento atteso = tasso privo di rischio + beta × premio di mercato. Chi si muove di più con il mercato "
            "rende di più in media; il rischio specifico del singolo titolo non è remunerato. **Consigliato.**",
    "uguale": "Stesso rendimento medio per tutti i portafogli: le differenze dipendono solo dal rischio.",
    "storico": "Rendimenti realmente ottenuti in passato. ⚠️ Proietta il passato nel futuro: troppo ottimistico per titoli scelti oggi perché sono andati bene.",
    "personalizzato": "Scegli tu il rendimento medio annuo di ogni portafoglio.",
}
ETICHETTE_MODULI = {
    "stress_test": "Stress test (crolli stile 2000 e 2008)",
    "rischio_singolo_titolo": "Rischio sul singolo titolo (crollo improvviso)",
    "confronto_modelli": "Confronto tra modelli e sensibilità (lento: tempo × 2,5 circa)",
    "analisi_C": "Analisi C: storia dal 1999 con proxy di settore",
}

st.set_page_config(page_title="Confronto portafogli", page_icon="📊", layout="wide")
# barra laterale più larga, così la tabella dei portafogli si legge per intero
st.markdown("<style>section[data-testid='stSidebar']{width:480px !important;min-width:480px}</style>", unsafe_allow_html=True)


# ------------------------------------------------------------------ stato
def tabella_da_cfg(raw):
    righe = []
    for p in raw.get("portafogli", []):
        tit = p.get("titoli") or []
        if isinstance(tit, str):
            tit = [t.strip() for t in tit.split(",") if t.strip()]
        if isinstance(tit, list):
            righe += [{"Portafoglio": p["nome"], "Ticker": t, "Peso (%)": None} for t in tit]
        else:
            righe += [{"Portafoglio": p["nome"], "Ticker": t, "Peso (%)": (float(w) if w not in (None, "") else None)} for t, w in tit.items()]
    return pd.DataFrame(righe, columns=["Portafoglio", "Ticker", "Peso (%)"])


def applica_cfg(raw):
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
    ss.rf = ra["tasso_privo_rischio"] * 100
    ss.mrp = ra["premio_mercato"] * 100
    ss.uguale = ra["valore_uguale"] * 100
    ss.personalizzato = {str(k): float(v) * 100 for k, v in (ra.get("personalizzato") or {}).items()}
    for k in C.DEFAULT["moduli"]:
        ss[f"mod_{k}"] = bool(cfg["moduli"][k])
    ss.nsim = max(500, int(cfg["n_simulazioni"]))
    ss.seed = int(cfg["seed"])
    ss.rib = cfg["ribilanciamento"]
    ss.costo = float(cfg["costo_ribilanciamento"]) * 100
    b = cfg["benchmark"]
    ss.b_nome, ss.b_ticker, ss.b_ter, ss.b_proxy = b["nome"], b["ticker"], float(b["ter"]) * 100, b.get("proxy_storico") or ""


def cfg_da_stato(tabella):
    """Costruisce la configurazione (dizionario) dai controlli dell'app."""
    ss = st.session_state
    raw = copy.deepcopy(ss.raw)
    portafogli = {}
    for _, r in tabella.iterrows():
        nome, tick = str(r["Portafoglio"] or "").strip(), str(r["Ticker"] or "").strip()
        if not nome and not tick:
            continue
        if not nome or not tick:
            raise C.ErroreConfig("Nella tabella dei portafogli ogni riga deve avere sia il nome del portafoglio sia il ticker.")
        peso = r["Peso (%)"]
        portafogli.setdefault(nome, {})[tick] = None if pd.isna(peso) else float(peso)
    raw["portafogli"] = [{"nome": n, "titoli": (list(t) if all(v is None for v in t.values()) else t)} for n, t in portafogli.items()]
    try:
        inter = [int(x) for x in str(ss.intermedi).replace(";", ",").split(",") if x.strip()]
    except ValueError:
        raise C.ErroreConfig("Orizzonti intermedi: scrivi gli anni separati da virgola, es. 5, 10.")
    raw.update({"nome": ss.nome or "confronto", "capitale_iniziale": ss.capitale, "versamento_mensile": ss.versamento,
                "orizzonte_anni": int(ss.orizzonte), "orizzonti_intermedi": inter, "n_simulazioni": int(ss.nsim),
                "seed": int(ss.seed), "ribilanciamento": ss.rib, "costo_ribilanciamento": ss.costo / 100})
    raw["rendimento_atteso"] = {"metodo": ss.metodo, "tasso_privo_rischio": ss.rf / 100, "premio_mercato": ss.mrp / 100,
                                "valore_uguale": ss.uguale / 100,
                                "personalizzato": {k: v / 100 for k, v in ss.personalizzato.items()}}
    raw["moduli"] = {k: bool(ss[f"mod_{k}"]) for k in C.DEFAULT["moduli"]}
    raw["benchmark"] = {**(raw.get("benchmark") or {}), "nome": ss.b_nome, "ticker": ss.b_ticker.strip(),
                        "ter": ss.b_ter / 100, "proxy_storico": ss.b_proxy.strip() or None}
    return raw


if "raw" not in st.session_state:
    applica_cfg(yaml.safe_load(open(ESEMPIO, encoding="utf-8")))
ss = st.session_state


def pesi_uguali():
    t = ss.tabella_corrente.copy()
    t = t[t["Ticker"].astype(str).str.strip() != ""]
    t["Peso (%)"] = t.groupby("Portafoglio")["Ticker"].transform(lambda x: round(100 / len(x), 4))
    ss.tabella = t.reset_index(drop=True)
    ss.versione += 1


def carica_file():
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


def carica_esempio():
    applica_cfg(yaml.safe_load(open(ESEMPIO, encoding="utf-8")))
    ss.pop("ris", None)


# ------------------------------------------------------------------ barra laterale
with st.sidebar:
    st.header("Impostazioni")
    st.text_input("Nome del confronto", key="nome")
    st.subheader("Portafogli")
    st.caption("Una riga per titolo. Ticker come su finance.yahoo.com (es. AAPL, ENI.MI, SAP.DE, IWDA.AS). "
               "Peso in %: lascialo vuoto (compare «None») per pesi uguali. Per un portafoglio **misto** scrivi come ticker il nome di un altro "
               "portafoglio oppure `benchmark` (es. 80 benchmark + 20 Cyber security).")
    tab = st.data_editor(ss.tabella, key=f"editor_{ss.versione}", num_rows="dynamic", width="stretch", hide_index=True,
                         column_config={"Portafoglio": st.column_config.TextColumn(width="medium"),
                                        "Ticker": st.column_config.TextColumn(width="small"),
                                        "Peso (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f", width="small")})
    ss.tabella_corrente = tab
    c1, c2 = st.columns(2)
    c1.button("Pesi uguali", on_click=pesi_uguali, width="stretch")
    c2.button("Ricarica esempio", on_click=carica_esempio, width="stretch")

    st.subheader("Capitale e orizzonte")
    st.number_input("Capitale iniziale (€)", min_value=0.0, step=500.0, key="capitale")
    st.number_input("Versamento mensile (€)", min_value=0.0, step=50.0, key="versamento")
    st.number_input("Orizzonte (anni)", min_value=1, max_value=50, step=1, key="orizzonte")
    st.text_input("Orizzonti intermedi (anni)", key="intermedi", help="Separati da virgola, es. 5, 10")

    st.subheader("Rendimento atteso")
    st.radio("Metodo", list(SPIEGA_METODO), key="metodo", horizontal=True)
    st.caption(SPIEGA_METODO[ss.metodo])
    if ss.metodo == "beta":
        c1, c2 = st.columns(2)
        c1.number_input("Tasso privo di rischio (%)", step=0.25, key="rf")
        c2.number_input("Premio di mercato (%)", step=0.25, key="mrp")
    elif ss.metodo == "uguale":
        st.number_input("Rendimento medio annuo per tutti (%)", step=0.5, key="uguale")
    elif ss.metodo == "personalizzato":
        nomi = list(dict.fromkeys(str(x).strip() for x in tab["Portafoglio"] if str(x).strip())) + ["benchmark"]
        dfp = pd.DataFrame({"Portafoglio": nomi, "Rendimento (%)": [ss.personalizzato.get(n, ss.uguale) for n in nomi]})
        modp = st.data_editor(dfp, key=f"pers_{ss.versione}", hide_index=True, disabled=["Portafoglio"], width="stretch")
        ss.personalizzato = dict(zip(modp["Portafoglio"], modp["Rendimento (%)"].astype(float)))

    st.subheader("Moduli")
    for k, et in ETICHETTE_MODULI.items():
        st.checkbox(et, key=f"mod_{k}")

    st.subheader("Simulazione")
    st.number_input("Numero di simulazioni", min_value=500, max_value=100000, step=1000, key="nsim",
                    help="10.000 = circa 1-3 minuti. Per una prova veloce usa 1.000.")
    with st.expander("Benchmark e impostazioni avanzate"):
        st.text_input("Nome del benchmark", key="b_nome")
        st.text_input("Ticker del benchmark", key="b_ticker")
        st.number_input("TER del benchmark (%)", min_value=0.0, max_value=3.0, step=0.01, key="b_ter")
        st.text_input("Indice usato prima della nascita dell'ETF", key="b_proxy", help="Lascia vuoto se non serve.")
        st.selectbox("Ribilanciamento", list(C.RIBILANCIAMENTO_MESI), key="rib")
        st.number_input("Costo di ribilanciamento (%)", min_value=0.0, max_value=5.0, step=0.05, key="costo")
        st.number_input("Seed (stesso numero = stessi risultati)", min_value=0, step=1, key="seed")
    aggiorna = st.checkbox("Aggiorna i dati (riscarica i prezzi)", value=False)
    avvia = st.button("▶ Avvia simulazione", type="primary", width="stretch")

    st.subheader("Salva / carica configurazione")
    try:
        yaml_corrente = yaml.safe_dump(cfg_da_stato(tab), allow_unicode=True, sort_keys=False)
    except C.ErroreConfig:
        yaml_corrente = None
    if yaml_corrente:
        st.download_button("💾 Scarica configurazione (YAML)", yaml_corrente, file_name=f"{(ss.nome or 'confronto').replace(' ', '_')}.yaml",
                           mime="text/yaml", width="stretch")
    st.file_uploader("Carica una configurazione salvata", type=["yaml", "yml"], key="file_cfg", on_change=carica_file)
    if ss.get("msg_caricamento"):
        tipo, testo = ss.pop("msg_caricamento")
        (st.success if tipo == "ok" else st.error)(testo)


# ------------------------------------------------------------------ pagina principale
st.title("📊 Confronto del rischio di portafogli")

if avvia:
    ss.pop("ris", None)
    barra = st.progress(0.0, text="Preparo la simulazione...")
    try:
        cfg = C.prepara(cfg_da_stato(tab))
        ris = analisi.esegui(cfg, aggiorna_dati=aggiorna, log=lambda *a: None,
                             progresso=lambda f, m: barra.progress(min(max(f, 0.0), 1.0), text=f"{m} ({f * 100:.0f}%)"))
        barra.progress(1.0, text="Preparo il report...")
        S = report.sezioni(ris)
        ss.ris, ss.sezioni = ris, S
        ss.html = report.html_report(ris, S)
        ss.pdf = report.pdf_report(ris, S)
        barra.empty()
    except (C.ErroreConfig, ErroreDati) as e:
        barra.empty()
        st.error(f"**Non posso completare la simulazione.** {e}")
    except Exception as e:  # errore imprevisto: messaggio chiaro + dettagli per chi vuole
        barra.empty()
        st.error("**Si è verificato un errore imprevisto.** Controlla i ticker e la connessione a internet, poi riprova. "
                 "Se il problema resta, salva la configurazione e i dettagli qui sotto.")
        with st.expander("Dettagli tecnici"):
            st.code("".join(traceback.format_exception(e)))

if "ris" not in ss:
    st.markdown(
        "Questa app simula migliaia di futuri possibili per i tuoi portafogli e ne confronta il **rischio** "
        "(quanto possono scendere, quanto è probabile perdere, quanto tempo serve per recuperare).\n\n"
        "1. Nella barra a sinistra scrivi i portafogli (è precaricato un esempio con tre portafogli e l'MSCI World).\n"
        "2. Scegli capitale, versamento, orizzonte e metodo del rendimento atteso.\n"
        "3. Premi **▶ Avvia simulazione**. Al termine trovi i risultati in schede e puoi scaricare il report in HTML e PDF.\n\n"
        "_Questo strumento non è consulenza finanziaria._")
else:
    ris = ss.ris
    st.caption(report.intestazione(ris))
    c1, c2, _ = st.columns([1, 1, 3])
    nome_file = f"report_{(ris['cfg']['nome'] or 'confronto').replace(' ', '_')}"
    c1.download_button("⬇️ Report HTML", ss.html, file_name=f"{nome_file}.html", mime="text/html", width="stretch")
    c2.download_button("⬇️ Report PDF", ss.pdf, file_name=f"{nome_file}.pdf", mime="application/pdf", width="stretch")
    schede = st.tabs(report.SCHEDE)
    for scheda, nome in zip(schede, report.SCHEDE):
        with scheda:
            blocchi = ss.sezioni.get(nome) or [("p", "Niente da mostrare: modulo non attivato.")]
            st.html(f"<style>{report.CSS_APP}</style><div class='rep'>{report.html_blocchi(blocchi)}</div>")
