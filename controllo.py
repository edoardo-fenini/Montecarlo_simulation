"""Controllo dei dati prima della simulazione: una riga con semaforo per ogni titolo (e per il benchmark).

ROSSO  (blocca la simulazione): ticker/ISIN non trovato o con cifra di controllo errata, nessun prezzo, meno di 1 anno di
       storia, ultimo prezzo più vecchio di 30 giorni, prezzi zero o negativi.
GIALLO (avviso, si può procedere): meno di 3 anni di storia, più del 5% di giorni mancanti, ultimo prezzo più vecchio di 7 giorni,
       movimenti giornalieri estremi, nome trovato molto diverso da quello atteso (`nomi_attesi` in configurazione).
VERDE  tutto a posto.
Le soglie sono in configurazione (`controllo_dati`)."""

from __future__ import annotations

import datetime

import pandas as pd

import dati as D
import isin as I
from dati import ErroreDati
from nomi import somiglianza_nomi

VERDE, GIALLO, ROSSO = "VERDE", "GIALLO", "ROSSO"
SEMAFORO = {VERDE: "🟢", GIALLO: "🟡", ROSSO: "🔴"}
COLONNE_TABELLA = [
    "Esito", "Input", "ISIN", "Ticker usato", "Nome", "Borsa", "Valuta", "Fonte", "Prima data", "Ultima data", "Anni di storia",
    "% giorni mancanti", "Ultimo prezzo", "Dettagli",
]  # fmt: skip


def _it(x, dec=1):
    return f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data(d):
    return "" if d is None else pd.Timestamp(d).strftime("%d/%m/%Y")


# ------------------------------------------------------------------ risultati vecchi
AVVISO_RISULTATI_VECCHI = "Questi risultati non corrispondono più ai dati attuali: rilancia la simulazione."


def motivo_risultati_vecchi(
    stato: dict | None,
    chiave_attuale: str | None,
    dati_attuali: float,
    controllo_app: dict | None = None,
    chiave_dati_attuale: str | None = None,
) -> str | None:
    """None se i risultati in memoria sono ancora validi, altrimenti il motivo (in italiano) per cui vanno nascosti.
    `stato` = {'chiave': impronta di tutte le impostazioni, 'dati': data di modifica della cache dei prezzi} registrato a fine simulazione.
    `controllo_app` = ultimo controllo dei dati ({'chiave', 'esito'}); conta solo se riguarda i titoli attuali (`chiave_dati_attuale`)."""
    if not stato:
        return None
    if controllo_app and controllo_app.get("chiave") == chiave_dati_attuale and controllo_app["esito"]["blocca"]:
        return "il controllo dei dati è rosso: ci sono titoli con un errore"
    if chiave_attuale is None or chiave_attuale != stato["chiave"]:
        return "dopo la simulazione hai cambiato titoli, pesi o impostazioni"
    if dati_attuali > stato["dati"]:
        return "i prezzi in cache sono stati aggiornati dopo la simulazione"
    return None


# ------------------------------------------------------------------ nome atteso
# ------------------------------------------------------------------ giorni mancanti
def giorni_mancanti(serie: dict[str, pd.Series]) -> dict[str, float]:
    """Quota di giorni di borsa senza prezzo, per titolo, tra la prima e l'ultima data del titolo. Il calendario di riferimento è
    quello del progetto (giorni in cui almeno metà dei titoli quotati ha scambiato): le festività di una borsa non contano."""
    if not serie:
        return {}
    cal = D.calendario_comune(serie)
    out = {}
    for t, s in serie.items():
        giorni = cal[(cal >= s.index[0]) & (cal <= s.index[-1])]
        out[t] = float((~giorni.isin(s.index)).sum() / len(giorni)) if len(giorni) else 0.0
    return out


# ------------------------------------------------------------------ controllo
def _titoli_della_configurazione(cfg: dict) -> list[tuple[str, str]]:
    """[(input come scritto, ruolo)] senza doppioni: titoli dei portafogli (ma non i riferimenti ad altri portafogli) e benchmark."""
    riferimenti = {p["nome"].lower() for p in cfg["portafogli"]} | {"benchmark", cfg["benchmark"]["nome"].lower()}
    visti, out = set(), []
    for p in cfg["portafogli"]:
        for k in p["pesi"]:
            if k.lower() in riferimenti or I.normalizza(k) in visti:
                continue
            visti.add(I.normalizza(k))
            out.append((k, "titolo"))
    b = cfg["benchmark"]["ticker"]
    if I.normalizza(b) not in visti:
        out.append((b, "benchmark"))
    return out


def _nome_quotazione(r: dict) -> str:
    """Nome dalla ricerca ISIN, se Yahoo non lo dà nei dati dei prezzi."""
    ris = r.get("risoluzione") or {}
    return next((q["nome"] for q in ris.get("quotazioni", []) if q["ticker"] == r["ticker"]), "")


def _riga_vuota(inp: str, ruolo: str) -> dict:
    return {
        "input": inp, "ruolo": ruolo, "isin": "", "ticker": "", "nome": "", "borsa": "", "valuta": "", "fonte": "", "primo": None,
        "ultimo": None, "anni": None, "mancanti": None, "ultimo_prezzo": None, "esito": VERDE, "rossi": [], "gialli": [],
        "trovato": False, "risoluzione": None, "info": [],
    }  # fmt: skip


def controlla(cfg: dict, arch: D.Archivio, oggi: datetime.date | None = None, http=None, ispettore=None, ricerca=None, log=print) -> dict:
    """Controlla tutti i titoli. Ritorna {'righe', 'cfg' (ISIN già sostituiti dai ticker), 'riepilogo', 'blocca', 'messaggio'}.
    Non solleva errori per i singoli titoli: li segna in rosso. Scarica (e mette in cache) i prezzi, così la simulazione dopo è più veloce."""
    oggi = oggi or datetime.date.today()
    soglie = cfg["controllo_dati"]
    opz = cfg["isin"]
    D.importa_da_configurazione(cfg, arch)
    righe, mappa = [], {}
    for inp, ruolo in _titoli_della_configurazione(cfg):
        r = _riga_vuota(inp, ruolo)
        tipo, codice = I.riconosci(inp)
        r["ticker"] = codice
        if tipo == "isin_errato":
            r["isin"] = codice
            r["ticker"] = ""
            r["rossi"].append(f"l'ISIN {codice} non ha la cifra di controllo giusta (errore di battitura?)")
        elif tipo == "isin":
            r["isin"] = codice
            try:
                ris = I.risolvi(
                    codice, arch.dir, opz["preferenze"], cfg["isin_scelte"].get(codice), arch.aggiorna, http, opz.get("openfigi_chiave"),
                    opz["max_quotazioni"], oggi, ricerca, ispettore, soglie["somiglianza_nome_min"],
                )  # fmt: skip
                r["risoluzione"], r["ticker"] = ris, ris["ticker"]
                mappa[codice] = ris["ticker"]
                r["nome_figi_avvisi"] = ris.get("avvisi_nome", [])
                if ris.get("borse_non_mappate"):
                    elenco_b = ", ".join(f"{b['borsa']} ({b['ticker']})" if b.get("ticker") else b["borsa"] for b in ris["borse_non_mappate"])
                    r["info"].append(f"OpenFIGI elenca quotazioni su borse non mappate, ignorate: {elenco_b}")
            except ErroreDati as e:
                r["ticker"] = ""
                r["rossi"].append(str(e))
        righe.append(r)

    serie = {}
    for r in righe:
        if r["rossi"]:
            continue
        t = r["ticker"]
        try:
            s, meta = arch.prezzi(t)
            if (oggi - s.index[-1].date()).days > soglie["ultimo_prezzo_avviso_giorni"]:
                arch.rinfresca(t)  # cache vecchia: riprovo a scaricare prima di dichiararlo vecchio
                s, meta = arch.prezzi(t)
        except ErroreDati as e:
            msg = str(e)
            r["rossi"].append(
                "ticker non trovato su Yahoo Finance"
                if "non esiste" in msg or "non ha dati" in msg
                else "dati non disponibili: " + msg.split(".")[0]
            )
            continue
        if len(s) == 0:
            r["rossi"].append("nessun prezzo disponibile")
            continue
        r["trovato"] = True
        serie[t] = s
        r.update(
            nome=meta.get("nome") or _nome_quotazione(r), borsa=meta.get("borsa") or "", valuta=meta.get("valuta") or "",
            fonte=meta.get("fonte") or "Yahoo Finance", primo=s.index[0].date(), ultimo=s.index[-1].date(),
            anni=(s.index[-1] - s.index[0]).days / 365.25, ultimo_prezzo=float(s.iloc[-1]),
        )  # fmt: skip
        r["_meta"] = meta
    manc = giorni_mancanti(serie)

    for r in righe:
        if not r["trovato"]:
            continue
        s, meta = serie[r["ticker"]], r.pop("_meta")
        r["mancanti"] = manc.get(r["ticker"], 0.0)
        eta = (oggi - r["ultimo"]).days
        npos = int(meta.get("prezzi_non_positivi") or 0) + int((s <= 0).sum())
        if npos:
            r["rossi"].append(f"{npos} prezzi zero o negativi nei dati originali")
        if r["anni"] < soglie["storia_min_anni"]:
            r["rossi"].append(f"solo {_it(r['anni'])} anni di storia (minimo {_it(soglie['storia_min_anni'], 0)})")
        elif r["anni"] < soglie["storia_avviso_anni"]:
            r["gialli"].append(
                f"solo {_it(r['anni'])} anni di storia (meno di {_it(soglie['storia_avviso_anni'], 0)}): risultati poco affidabili"
            )
        if eta > soglie["ultimo_prezzo_blocco_giorni"]:
            r["rossi"].append(f"ultimo prezzo del {_data(r['ultimo'])} ({eta} giorni fa)")
        elif eta > soglie["ultimo_prezzo_avviso_giorni"]:
            r["gialli"].append(f"ultimo prezzo del {_data(r['ultimo'])} ({eta} giorni fa)")
        if r["mancanti"] > soglie["giorni_mancanti_max"]:
            r["gialli"].append(f"{_it(r['mancanti'] * 100)}% di giorni senza prezzo (oltre {_it(soglie['giorni_mancanti_max'] * 100, 0)}%)")
        mov = s.pct_change().dropna()
        estremi = mov[mov.abs() > soglie["movimento_estremo"]]
        if len(estremi):
            peggiore = estremi.abs().idxmax()
            r["gialli"].append(
                f"{len(estremi)} movimenti giornalieri oltre ±{_it(soglie['movimento_estremo'] * 100, 0)}% "
                f"(il maggiore {estremi[peggiore]:+.0%} il {_data(peggiore)})"
            )
        r["gialli"] += r.pop("nome_figi_avvisi", [])
        atteso = next((cfg["nomi_attesi"][k] for k in (I.normalizza(r["input"]), r["ticker"], r["isin"]) if k in cfg["nomi_attesi"]), None)
        if atteso and not r["nome"]:
            r["gialli"].append(f"non trovo il nome del titolo per confrontarlo con quello atteso («{atteso}»)")
        elif atteso and somiglianza_nomi(atteso, r["nome"]) < soglie["somiglianza_nome_min"]:
            r["gialli"].append(f"il nome trovato («{r['nome']}») è molto diverso da quello atteso («{atteso}»)")
    for r in righe:
        r["esito"] = ROSSO if r["rossi"] else GIALLO if r["gialli"] else VERDE
    return costruisci_esito(righe, I.applica_mappa(cfg, mappa) if mappa else cfg)


def costruisci_esito(righe: list[dict], cfg: dict) -> dict:
    n_rossi = sum(r["esito"] == ROSSO for r in righe)
    n_gialli = sum(r["esito"] == GIALLO for r in righe)
    trovati = sum(r["trovato"] for r in righe)
    riepilogo = (
        f"{trovati} {'titolo trovato' if trovati == 1 else 'titoli trovati'}, "
        f"{n_gialli} {'avviso' if n_gialli == 1 else 'avvisi'}, {n_rossi} {'errore' if n_rossi == 1 else 'errori'}"
    )
    messaggio = ""
    if n_rossi:
        elenco = "\n".join(f"  • {r['input']}: " + "; ".join(r["rossi"]) for r in righe if r["esito"] == ROSSO)
        messaggio = (
            f"Simulazione bloccata: {n_rossi} {'titolo ha' if n_rossi == 1 else 'titoli hanno'} un errore (rosso). "
            f"Correggi o togli {'questo titolo' if n_rossi == 1 else 'questi titoli'} e riprova:\n{elenco}"
        )
    return {
        "righe": righe,
        "cfg": cfg,
        "riepilogo": riepilogo,
        "blocca": n_rossi > 0,
        "messaggio": messaggio,
        "rossi": n_rossi,
        "gialli": n_gialli,
    }


# ------------------------------------------------------------------ rendimento atteso (prima della simulazione)
def rendimenti_attesi(esito: dict, arch: D.Archivio):
    """Tabella (beta e rendimento atteso annuo per portafoglio) che verrà usata dalla simulazione, calcolata con i prezzi già in cache.
    None se non si può calcolare (controllo rosso o dati insufficienti): in quel caso la simulazione dirà il motivo."""
    import analisi

    if esito["blocca"]:
        return None
    try:
        dati = D.costruisci(esito["cfg"], arch)
        tipi = dati["info"]["tipo"].to_dict()
        return analisi.spiega_rendimenti(esito["cfg"], analisi.stima_beta(dati["R"]), tipi)
    except (ErroreDati, KeyError, ValueError):
        return None


# ------------------------------------------------------------------ presentazione
def dettagli(r: dict) -> str:
    parti = [f"ERRORE: {x}" for x in r["rossi"]] + [f"avviso: {x}" for x in r["gialli"]]
    info = [f"info: {x}" for x in r.get("info", [])]
    return "; ".join(parti + info) if parti or info else "tutto a posto"


def tabella(righe: list[dict], emoji: bool = True) -> pd.DataFrame:
    """Tabella «Controllo dati» come DataFrame di testo, pronta per app, CSV ed Excel."""
    out = []
    for r in righe:
        prezzo = f"{_it(r['ultimo_prezzo'], 2)} {r['valuta']} del {_data(r['ultimo'])}".strip() if r["ultimo_prezzo"] is not None else ""
        out.append(
            {
                "Esito": (SEMAFORO[r["esito"]] + " " if emoji else "") + r["esito"].capitalize(),
                "Input": r["input"],
                "ISIN": r["isin"],
                "Ticker usato": r["ticker"],
                "Nome": r["nome"],
                "Borsa": r["borsa"],
                "Valuta": r["valuta"],
                "Fonte": r["fonte"],
                "Prima data": _data(r["primo"]),
                "Ultima data": _data(r["ultimo"]),
                "Anni di storia": "" if r["anni"] is None else _it(r["anni"]),
                "% giorni mancanti": "" if r["mancanti"] is None else _it(r["mancanti"] * 100),
                "Ultimo prezzo": prezzo,
                "Dettagli": dettagli(r),
            }
        )
    return pd.DataFrame(out, columns=COLONNE_TABELLA)


def testo_tabella(esito: dict) -> str:
    """Tabella per il terminale: riepilogo + una riga per titolo (colonne essenziali) + dettagli di avvisi ed errori."""
    t = tabella(esito["righe"], emoji=False)[["Esito", "Input", "Ticker usato", "Nome", "Borsa", "Valuta", "Anni di storia", "Ultima data"]]
    t["Nome"] = t["Nome"].str.slice(0, 28)
    corpo = t.to_string(index=False)
    note = [f"  {r['input']}: {dettagli(r)}" for r in esito["righe"] if r["esito"] != VERDE or r.get("info")]
    return f"Controllo dati: {esito['riepilogo']}\n{corpo}" + ("\n" + "\n".join(note) if note else "")


def per_report(esito: dict) -> dict:
    """Parte serializzabile (senza oggetti pesanti) da salvare nei risultati e nel report."""
    return {
        "riepilogo": esito["riepilogo"],
        "blocca": esito["blocca"],
        "tabella": tabella(esito["righe"]),
        "tabella_senza_emoji": tabella(esito["righe"], emoji=False),
        "conteggi": {"rossi": esito["rossi"], "gialli": esito["gialli"]},
    }


__all__ = ["motivo_risultati_vecchi", "AVVISO_RISULTATI_VECCHI", "controlla", "tabella", "testo_tabella", "per_report", "somiglianza_nomi", "giorni_mancanti"]
