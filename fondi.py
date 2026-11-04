"""Fondi comuni non quotati: ricerca dei codici di Yahoo Finance (tipo Morningstar «0P0000XXXX», a volte con suffisso «.F»).

Per un ISIN classificato come fondo comune (vedi isin.classifica_tipo) la ricerca di Yahoo per ISIN di solito non trova il fondo
giusto: Yahoo conosce i fondi con codici Morningstar e li trova bene solo per nome. Qui si fanno alcune ricerche per nome, poi ogni
candidato viene verificato (stesso gestore, nome simile a quello di OpenFIGI, valuta, classe ad accumulazione/distribuzione, storia,
ultimo prezzo recente) e si sceglie il migliore. Non c'è certezza che sia la classe giusta (Yahoo non indica l'ISIN): il risultato
porta sempre un avviso GIALLO. Se nessun candidato supera i controlli il fondo si considera non trovato (si carica lo storico delle
quote oppure si sceglie un proxy)."""

from __future__ import annotations

import datetime
import logging
import re

import isin as I
from nomi import parole, somiglianza_nomi

log = logging.getLogger("confronta")

STORIA_MIN_ANNI = 1.0  # sotto questa storia un candidato non serve
GIORNI_ULTIMO_PREZZO = 30  # ultimo prezzo più vecchio di così: candidato scartato
SOMIGLIANZA_MIN = 0.5
MAX_RICERCHE = 14
MAX_VERIFICHE = 10

# sigle con cui Yahoo/Morningstar scrive alcuni gestori (usate solo per costruire le ricerche)
ALIAS_GESTORI = {
    "morgan stanley": ["MS INVF", "MS"],
    "jpmorgan": ["JPM"],
    "jp morgan": ["JPM"],
    "jpmif": ["JPM"],
    "blackrock": ["BGF", "BlackRock"],
    "amundi": ["Amundi"],
    "pictet": ["Pictet"],
    "fidelity": ["Fidelity"],
    "schroder": ["Schroder ISF"],
    "franklin": ["Franklin"],
    "bnp paribas": ["BNP Paribas"],
    "carmignac": ["Carmignac"],
    "allianz": ["Allianz"],
    "axa": ["AXA WF"],
    "candriam": ["Candriam"],
}
PAROLE_GENERICHE = {"sicav", "investment", "funds", "fund", "fd", "inv", "invf", "the", "of", "plc", "trust", "sub", "comparto"}


def e_codice_fondo(simbolo: str, tipo_quote: str = "") -> bool:
    """Codice Morningstar di Yahoo (0P..., con o senza suffisso di borsa) oppure strumento di tipo MUTUALFUND."""
    return bool(re.match(r"^0P[A-Z0-9]{8}(\.[A-Z]{1,3})?$", str(simbolo or "").upper())) or str(tipo_quote).upper() == "MUTUALFUND"


# ------------------------------------------------------------------ che cosa ci aspettiamo dal nome di OpenFIGI
def valuta_attesa(nome: str) -> str | None:
    """Valuta della classe letta nel nome del fondo («$», USD, EUR, ...). None se non si capisce."""
    t = f" {str(nome or '').upper()} "
    if "$" in t or re.search(r"\bA?USD\b|\bUS\$", t):
        return "USD"
    for v in ("EUR", "GBP", "CHF", "JPY", "SEK", "NOK", "DKK"):
        if re.search(rf"\b[A-Z]?{v}\b", t):
            return v
    if "€" in t:
        return "EUR"
    return None


def classe_attesa(nome: str) -> str | None:
    """'acc' (accumulazione) o 'dist' (distribuzione) se il nome lo dice, altrimenti None."""
    p = set(re.findall(r"[a-z]+", str(nome or "").lower()))
    if p & {"acc", "cap", "capitalisation", "capitalization", "accumulating"}:
        return "acc"
    if p & {"dist", "dis", "inc", "income", "div", "dividend", "mdis", "mdist"}:
        return "dist"
    return None


def e_coperta(nome: str) -> bool:
    """True se il nome indica una classe coperta dal rischio di cambio (hedged)."""
    t = str(nome or "").lower()
    return bool(re.search(r"\bhdg\b|hedged|\b[a-z]h\b|\bh\b", t))


def lettera_classe(nome: str) -> str | None:
    """Lettera della classe di azioni (A, B, I, Z ...): l'ultima parola di una sola lettera del nome, esclusa la «H» di «hedged»."""
    lettere = [w for w in re.findall(r"\b[A-Za-z]\b", re.sub(r"[.]", "", str(nome or ""))) if w.lower() != "h"]
    return lettere[-1].upper() if lettere else None


def parole_in_piu(riferimenti: list[str], candidato: str) -> int:
    """Quante parole significative del candidato non compaiono in nessun nome di riferimento (es. «Plus» in «US Select Equity Plus»)."""
    note = set().union(*(parole(r) for r in riferimenti)) if riferimenti else set()
    return len({w for w in parole(candidato) if not w.isdigit() and len(w) > 1} - note - {"acc", "dist", "usd", "eur", "hdg", "ms", "invf", "jpm"})


def stesso_gestore(nomi_riferimento: list[str], nome_candidato: str) -> bool:
    """La prima parola del candidato (es. «MS», «JPM», «BGF») deve essere l'inizio di una delle prime parole dei nomi di riferimento
    («JPM» per «JPMorgan») oppure le iniziali delle loro prime parole («Morgan Stanley» -> «MS»)."""
    prima = re.findall(r"[a-z0-9]+", str(nome_candidato or "").lower())
    if not prima or len(prima[0]) < 2:
        return False
    t = prima[0]
    for rif in nomi_riferimento:
        parti = re.findall(r"[a-z0-9]+", str(rif or "").lower())
        if any(len(w) >= 3 and (w.startswith(t) or t.startswith(w)) for w in parti[:3]):
            return True
        if any(len(parti) >= k and "".join(w[0] for w in parti[:k]) == t for k in (2, 3, 4)):
            return True
    return False


# ------------------------------------------------------------------ ricerche
def _contenuto(nome: str) -> list[str]:
    """Parole del nome senza gestore e parole generiche (es. «US Growth»)."""
    return [w for w in re.findall(r"[A-Za-z0-9$]+", str(nome or "")) if w.lower() not in PAROLE_GENERICHE]


def costruisci_ricerche(isin_cod: str, nomi: list[str]) -> list[str]:
    """Testi da cercare su Yahoo: l'ISIN, i nomi puliti e, per i gestori noti, la sigla usata da Morningstar + il nome del fondo."""
    out = [isin_cod]
    for nome in nomi:
        pulito = re.sub(r"\b([A-Za-z])\.([A-Za-z])\.?", r"\1\2", str(nome or ""))  # U.S. -> US
        pulito = re.sub(r"[-–_/]", " ", re.sub(r"\bsicav\b", "", pulito, flags=re.I))
        pulito = re.sub(r"\s+", " ", pulito).strip()
        if not pulito:
            continue
        out.append(pulito)
        parole_n = pulito.lower()
        parti = pulito.split()
        for gestore, alias in ALIAS_GESTORI.items():
            if gestore in parole_n:
                # il resto del nome dopo il gestore: «Morgan Stanley Investment Funds US Growth» -> «US Growth»
                resto = _contenuto(re.sub(gestore, "", parole_n, count=1, flags=re.I))
                resto = [w for w in resto if w.lower() not in {"a", "b", "c", "i", "x", "z"}] or resto
                for a in alias:
                    out.append(f"{a} {' '.join(resto[:4])} A".strip())
                    out.append(f"{a} {' '.join(resto[:4])}".strip())
        coda = _contenuto(" ".join(parti[-4:]))
        if len(coda) >= 2:
            out.append(" ".join(coda[-3:]))
    visti, finale = set(), []
    for q in out:
        k = q.lower()
        if k not in visti and len(q) >= 3:
            visti.add(k)
            finale.append(q)
    return finale[:MAX_RICERCHE]


def _ricerca_yahoo(q: str):
    import yfinance as yf

    return yf.Search(q, max_results=15, news_count=0).quotes


def candidati_fondo(isin_cod: str, nomi: list[str], ricerca=None) -> list[dict]:
    """Codici di fondo trovati da Yahoo con le ricerche per ISIN e per nome: [{'ticker', 'nome_ricerca'}], senza doppioni."""
    ricerca = ricerca or _ricerca_yahoo
    trovati: dict[str, dict] = {}
    for q in costruisci_ricerche(isin_cod, nomi):
        try:
            risultati = ricerca(q) or []
        except Exception as e:  # rete, limiti di Yahoo, formato: una ricerca che fallisce non ferma le altre
            log.info("ricerca fondi «%s»: %s", q, e)
            continue
        for r in risultati:
            sim = str(r.get("symbol") or "").upper()
            if sim and e_codice_fondo(sim, r.get("quoteType")) and sim not in trovati:
                trovati[sim] = {"ticker": sim, "nome_ricerca": r.get("longname") or r.get("shortname") or ""}
    return list(trovati.values())


# ------------------------------------------------------------------ scelta
def cerca_fondo(
    isin_cod: str,
    nome_isin: str,
    nomi_yahoo: list[str],
    oggi: datetime.date | None = None,
    ricerca=None,
    ispettore=None,
    http=None,
) -> list[dict]:
    """Candidati verificati per un fondo comune, dal migliore. Ogni elemento è una quotazione come quelle di isin._verifica più:
    'somiglianza' (nome), 'penalita' (valuta/classe/copertura diverse da quelle attese: 0 = tutto coincide), 'avvisi_fondo'.
    Lista vuota se nessun candidato supera i controlli."""
    oggi = oggi or datetime.date.today()
    riferimenti = [n for n in [nome_isin, *nomi_yahoo] if n]
    cand = candidati_fondo(isin_cod, riferimenti, ricerca)
    # prima il controllo del gestore e del nome sul testo della ricerca (gratis), poi la verifica dei prezzi (costosa)
    plausibili = []
    for c in cand:
        n = c["nome_ricerca"]
        if not stesso_gestore(riferimenti, n):
            continue
        if max((somiglianza_nomi(r, n) for r in riferimenti), default=0.0) < SOMIGLIANZA_MIN:
            continue
        plausibili.append(c)
    quote, _ = I._verifica(plausibili[:MAX_VERIFICHE], oggi, http, ispettore, MAX_VERIFICHE)
    v_att, c_att, h_att = valuta_attesa(nome_isin), classe_attesa(nome_isin), e_coperta(nome_isin)
    scelte = []
    for q in quote:
        try:
            eta = (oggi - datetime.date.fromisoformat(q["ultimo_scambio"])).days
        except ValueError:
            continue
        if eta > GIORNI_ULTIMO_PREZZO or q["storia_anni"] < STORIA_MIN_ANNI:
            continue
        nome = q["nome_yahoo"] or q["nome"]
        sim = max(somiglianza_nomi(r, nome) for r in riferimenti)
        pen = 0
        avvisi = []
        if v_att and (q["valuta"] or "").upper() != v_att:
            pen += 4
            avvisi.append(f"valuta {q['valuta']} invece di {v_att}")
        if c_att and classe_attesa(nome) and classe_attesa(nome) != c_att:
            pen += 2
            avvisi.append("classe " + ("a distribuzione" if c_att == "acc" else "ad accumulazione") + " diversa da quella attesa")
        l_att, l_cand = lettera_classe(nome_isin), lettera_classe(nome)
        if l_att and l_cand and l_att != l_cand:
            pen += 8
            avvisi.append(f"classe {l_cand} invece di {l_att}")
        if e_coperta(nome) != h_att:
            pen += 1
            avvisi.append("copertura del cambio diversa da quella attesa")
        q.update(
            {
                "nome_figi": "",  # il confronto nome OpenFIGI / Yahoo qui è già stato fatto (somiglianza)
                "nome_isin": nome_isin,
                "somiglianza": round(sim, 2),
                "penalita": pen + 3 * parole_in_piu(riferimenti, nome),
                "tipo": q.get("tipo") or "MUTUALFUND",
                "avvisi_fondo": [
                    f"fondo trovato per nome («{nome}»), non per ISIN: verifica che sia la classe giusta"
                    + (" (" + "; ".join(avvisi) + ")" if avvisi else "")
                ],
            }
        )
        scelte.append(q)
    return sorted(scelte, key=lambda q: (q["penalita"], -q["somiglianza"], -int(q["storia_anni"]), q["ticker"]))


__all__ = ["cerca_fondo", "e_codice_fondo", "costruisci_ricerche", "valuta_attesa", "classe_attesa", "stesso_gestore", "parole"]
