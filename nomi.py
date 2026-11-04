"""Confronto tollerante tra nomi di società e di fondi (OpenFIGI contro Yahoo, nome atteso contro nome trovato).

Ignora maiuscole, punteggiatura e forme societarie (Inc, SpA, S.p.A., PLC, AG, NV, ...). Valore da 0 (nomi diversi) a 1 (uguali)."""

from __future__ import annotations

import difflib
import re
import unicodedata

PAROLE_VUOTE = {
    "inc", "corp", "corporation", "co", "company", "spa", "sa", "ag", "se", "nv", "plc", "ltd", "limited", "group", "holdings",
    "holding", "the", "ucits", "etf", "acc", "dist", "usd", "eur", "ord", "ordinary", "shares", "share", "class", "a", "c", "de",
    "di", "and", "&", "adr",
    "srl", "sas", "gmbh", "kgaa", "bv", "ab", "asa", "oyj", "llc", "lp", "sarl", "ltda", "pcl", "cl", "inst", "reg", "registered",
}  # fmt: skip


def parole(testo: str) -> set[str]:
    """Parole significative di un nome, in minuscolo. «S.p.A.» e «Inc.» perdono i punti (diventano «spa» e «inc»)."""
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    t = re.sub(r"[.'’`\u0300-\u036f]", "", t)  # punti, apostrofi e accenti (é -> e)
    return {p for p in re.findall(r"[a-z0-9]+", t) if p not in PAROLE_VUOTE}


def somiglianza_nomi(atteso: str, trovato: str) -> float:
    """0-1: quanto `trovato` assomiglia ad `atteso` (parole in comune, tollerante su sigle e forme legali)."""
    a, b = parole(atteso), parole(trovato)
    if not a or not b:
        return 0.0
    comuni = len(a & b) / min(len(a), len(b))
    ja, jb = " ".join(sorted(a)), " ".join(sorted(b))
    # somiglianza dei caratteri solo per nomi lunghi: su nomi brevi («Enel» e «Eni») darebbe un falso «simile»
    ra = difflib.SequenceMatcher(None, ja, jb).ratio() if min(len(ja), len(jb)) >= 8 else 0.0
    # un nome atteso abbreviato (es. «Apple») deve comparire come prefisso di una parola del nome trovato
    prefisso = 1.0 if all(any(w.startswith(p) for w in b) for p in a) else 0.0
    return max(comuni, ra, prefisso)
