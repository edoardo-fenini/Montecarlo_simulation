"""Importazione di un portafoglio da un CSV esportato dal broker.

Il file deve avere almeno una colonna con l'ISIN (o il ticker) e una con la quantità OPPURE il controvalore. Si riconoscono:
  - separatori «;», «,» e tabulazione; decimali con la virgola («1.234,56») o con il punto («1,234.56»);
  - righe di intestazione del broker prima della tabella (vengono saltate fino alla riga con i nomi delle colonne);
  - nomi di colonna comuni in italiano e in inglese (vedi COLONNE).
Il peso di ogni titolo è il suo controvalore in EUR diviso il totale. Se manca il controvalore si usa quantità × ultimo prezzo in EUR
(scaricato da Yahoo; gli ISIN vengono prima convertiti in ticker). Le righe ripetute dello stesso titolo vengono sommate.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Callable

import pandas as pd

import isin as I

# nome logico -> nomi di colonna riconosciuti (minuscolo, senza accenti né punteggiatura)
COLONNE = {
    "isin": ["isin", "codice isin", "isin code", "cod isin"],
    "ticker": ["ticker", "simbolo", "symbol", "sigla", "codice", "codice titolo", "instrument symbol"],
    "quantita": ["quantita", "qta", "q ta", "quantity", "qty", "numero", "numero titoli", "pezzi", "nominale", "shares", "quote",
                 "n titoli", "n azioni", "units", "valore nominale", "quantita nominale"],
    "controvalore": ["controvalore", "controvalore eur", "controvalore in eur", "controvalore di mercato", "valore", "valore eur",
                     "valore di mercato", "valore di mercato eur", "market value", "market value eur", "value", "value eur",
                     "importo", "ctv", "ctv eur", "controvalore attuale", "valore attuale", "totale eur"],
    "nome": ["descrizione", "nome", "titolo", "strumento", "denominazione", "name", "description", "instrument", "security"],
}  # fmt: skip


class ErroreImport(ValueError):
    """CSV del broker non leggibile: il messaggio spiega cosa manca."""


# ------------------------------------------------------------------ lettura
def _norm(testo) -> str:
    t = unicodedata.normalize("NFKD", str(testo or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\(.*?\)", " ", t)  # «Controvalore (EUR)» -> «controvalore»
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# colonne da NON scambiare per il controvalore attuale (costo d'acquisto, prezzo medio, utile ...)
ESCLUSE = ("carico", "acquisto", "costo", "medio", "media", "utile", "perdita", "plus", "minus", "rateo", "cost", "purchase", "gain")


def _colonna(nome_colonna: str) -> str | None:
    n = _norm(nome_colonna)
    if any(e in n.split() for e in ESCLUSE):
        return None
    for logico, nomi in COLONNE.items():
        if n in nomi:
            return logico
    for logico, nomi in COLONNE.items():  # «Controvalore EUR al 31/10» e simili
        if any(n.startswith(x + " ") for x in nomi if len(x) > 4):
            return logico
    return None


def numero(testo) -> float | None:
    """Numero scritto all'italiana o all'inglese: «1.234,56», «1,234.56», «1234,5», «€ 1 234,00», «-3». None se vuoto o non numerico.
    Con una sola virgola e nessun punto la virgola è il separatore dei decimali (formato dei broker italiani)."""
    if testo is None or (isinstance(testo, float) and pd.isna(testo)):
        return None
    if isinstance(testo, (int, float)):
        return float(testo)
    t = re.sub(r"[^\d,.\-]", "", str(testo).replace("−", "-"))
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            t = t.replace(",", "")  # 1,234.56
    elif "," in t:
        t = t.replace(".", "").replace(",", ".") if t.count(",") == 1 else t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")  # 1.234.567
    try:
        return float(t)
    except ValueError:
        return None


def _testo(contenuto: bytes | str) -> str:
    if isinstance(contenuto, str):
        return contenuto
    for codifica in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return contenuto.decode(codifica)
        except UnicodeDecodeError:
            continue
    raise ErroreImport("Non riesco a leggere il file: codifica dei caratteri sconosciuta.")


def _separatore(righe: list[str]) -> str:
    campione = "\n".join(righe[:30])
    conteggi = {s: campione.count(s) for s in (";", "\t", ",")}
    if conteggi[";"] or conteggi["\t"]:  # con «;» o tab la virgola è quasi sempre il separatore dei decimali
        return ";" if conteggi[";"] >= conteggi["\t"] else "\t"
    return ","


def leggi_tabella(contenuto: bytes | str) -> tuple[pd.DataFrame, dict[str, str]]:
    """Legge il CSV e ritorna (tabella di testo, {nome logico: nome della colonna nel file}). Salta le righe prima dell'intestazione."""
    testo = _testo(contenuto)
    righe = [r for r in testo.splitlines() if r.strip()]
    if not righe:
        raise ErroreImport("Il file è vuoto.")
    sep = _separatore(righe)
    tabella = list(csv.reader(io.StringIO("\n".join(righe)), delimiter=sep))
    for i, intest in enumerate(tabella[:40]):
        mappa: dict[str, str] = {}
        for c in intest:
            logico = _colonna(c)
            if logico and logico not in mappa:
                mappa[logico] = c
        if ("isin" in mappa or "ticker" in mappa) and ("quantita" in mappa or "controvalore" in mappa):
            corpo = [r + [""] * (len(intest) - len(r)) for r in tabella[i + 1 :]]
            df = pd.DataFrame([r[: len(intest)] for r in corpo], columns=[c for c in intest])
            df = df.loc[:, ~df.columns.duplicated()]
            return df, mappa
    raise ErroreImport(
        "Non trovo le colonne necessarie. Servono una colonna con l'ISIN (o il ticker) e una con la quantità o il controvalore, "
        "per esempio «ISIN;Quantità;Controvalore». Formato e nomi riconosciuti: vedi il README (Importare il portafoglio dal broker) "
        "e l'esempio esempi/portafoglio_broker_esempio.csv."
    )


def posizioni(contenuto: bytes | str) -> tuple[list[dict], list[str]]:
    """Righe utilizzabili del CSV: [{'input', 'nome', 'quantita', 'controvalore'}] (titoli ripetuti sommati) e avvisi sulle righe scartate."""
    df, m = leggi_tabella(contenuto)
    avvisi, per_titolo = [], {}
    for n, r in enumerate(df.to_dict("records"), start=2):
        codice = ""
        if "isin" in m:
            codice = I.normalizza(r.get(m["isin"]))
        if not codice and "ticker" in m:
            codice = I.normalizza(r.get(m["ticker"]))
        if not codice or codice in ("TOTALE", "TOTAL", "LIQUIDITA", "CASH"):
            continue  # righe vuote, di totale o di liquidità
        q = numero(r.get(m["quantita"])) if "quantita" in m else None
        v = numero(r.get(m["controvalore"])) if "controvalore" in m else None
        if (q is None or q <= 0) and (v is None or v <= 0):
            avvisi.append(f"riga {n} ({codice}): quantità e controvalore mancanti o non positivi, riga ignorata")
            continue
        p = per_titolo.setdefault(codice, {"input": codice, "nome": "", "quantita": 0.0, "controvalore": 0.0, "righe": 0,
                                           "senza_valore": False})  # fmt: skip
        p["righe"] += 1
        p["nome"] = p["nome"] or str(r.get(m.get("nome"), "") or "").strip()
        p["quantita"] += q if q and q > 0 else 0.0
        if v and v > 0:
            p["controvalore"] += v
        else:
            p["senza_valore"] = True
    if not per_titolo:
        raise ErroreImport("Nel file non c'è nessuna riga con un titolo e una quantità o un controvalore positivi.")
    for p in per_titolo.values():
        if p["righe"] > 1:
            avvisi.append(f"{p['input']}: {p['righe']} righe sommate")
    return list(per_titolo.values()), avvisi


# ------------------------------------------------------------------ pesi
def calcola(contenuto: bytes | str, prezzo_eur: Callable[[str], tuple[float, str]] | None = None) -> dict:
    """Anteprima del portafoglio. `prezzo_eur(codice)` -> (ultimo prezzo in EUR, ticker usato): serve solo per le righe senza controvalore.
    Ritorna {'righe': [...], 'avvisi': [...], 'totale': float, 'pesi': {codice: peso %}}; i pesi sono arrotondati a 2 decimali e sommano 100."""
    pos, avvisi = posizioni(contenuto)
    righe = []
    for p in pos:
        r = {**p, "prezzo_eur": None, "ticker": "", "fonte_valore": "controvalore del file"}
        if p["senza_valore"] or p["controvalore"] <= 0:
            if p["quantita"] <= 0:
                avvisi.append(f"{p['input']}: manca il controvalore per alcune righe e non c'è la quantità, titolo ignorato")
                continue
            if prezzo_eur is None:
                raise ErroreImport(f"{p['input']}: manca il controvalore e non posso cercare il prezzo.")
            try:
                prezzo, ticker = prezzo_eur(p["input"])
            except Exception as e:  # rete, ISIN sconosciuto, ticker inesistente
                avvisi.append(f"{p['input']}: non trovo l'ultimo prezzo ({str(e).split('.')[0]}), titolo ignorato")
                continue
            r.update(prezzo_eur=prezzo, ticker=ticker, controvalore=p["quantita"] * prezzo, fonte_valore="quantità × ultimo prezzo")
        righe.append(r)
    if not righe:
        raise ErroreImport("Nessun titolo utilizzabile: " + "; ".join(avvisi))
    totale = sum(r["controvalore"] for r in righe)
    pesi = arrotonda_pesi({r["input"]: r["controvalore"] / totale * 100 for r in righe})
    for r in righe:
        r["peso"] = pesi[r["input"]]
    righe.sort(key=lambda r: -r["controvalore"])
    return {"righe": righe, "avvisi": avvisi, "totale": totale, "pesi": {r["input"]: r["peso"] for r in righe}}


def arrotonda_pesi(pesi: dict[str, float], decimali: int = 2) -> dict[str, float]:
    """Arrotonda i pesi in modo che la somma sia esattamente 100 (la differenza va al peso più grande)."""
    out = {k: round(v, decimali) for k, v in pesi.items()}
    diff = round(100 - sum(out.values()), decimali)
    if out and diff:
        k = max(out, key=out.get)
        out[k] = round(out[k] + diff, decimali)
    return out


def prezzo_da_archivio(arch, cfg_isin: dict | None = None) -> Callable[[str], tuple[float, str]]:
    """Funzione `prezzo_eur` che usa l'archivio dei prezzi (cache + Yahoo) e la conversione ISIN -> ticker del programma."""
    import dati as D

    opz = cfg_isin or {}

    def prezzo(codice: str) -> tuple[float, str]:
        ticker = codice
        if I.riconosci(codice)[0] != "ticker":
            ticker = I.risolvi(codice, arch.dir, opz.get("preferenze"), aggiorna=False, chiave=opz.get("openfigi_chiave"))["ticker"]
        s, _ = D.serie_eur(arch, ticker)
        return float(s.iloc[-1]), ticker

    return prezzo


def tabella_anteprima(ris: dict) -> pd.DataFrame:
    """Anteprima leggibile (testi all'italiana) per l'app e il terminale."""

    def it(x, d=2):
        return "" if x is None else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return pd.DataFrame(
        [
            {
                "Titolo": r["input"],
                "Nome": r["nome"],
                "Quantità": it(r["quantita"], 4).rstrip("0").rstrip(",") if r["quantita"] else "",
                "Prezzo EUR": it(r["prezzo_eur"]),
                "Controvalore EUR": it(r["controvalore"]),
                "Peso %": it(r["peso"]),
                "Valore da": r["fonte_valore"] + (f" ({r['ticker']})" if r["ticker"] and r["ticker"] != r["input"] else ""),
            }
            for r in ris["righe"]
        ]
    )


def portafoglio(ris: dict, nome: str) -> dict:
    """Voce di configurazione pronta: {'nome', 'titoli': {codice: peso %}}."""
    return {"nome": nome.strip() or "Portafoglio importato", "titoli": dict(ris["pesi"])}


__all__ = ["calcola", "posizioni", "leggi_tabella", "numero", "arrotonda_pesi", "prezzo_da_archivio", "tabella_anteprima", "portafoglio"]
