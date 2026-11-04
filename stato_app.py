"""Copia di sicurezza delle impostazioni dell'app.

Streamlit cancella lo stato dei widget che in un'esecuzione non vengono disegnati (per esempio se un'esecuzione si interrompe con un
errore a metà della barra laterale). Senza una copia, capitale, orizzonte, tassi … tornerebbero ai valori minimi (0 €, 1 anno).
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping

CHIAVE_COPIA = "_impostazioni"


def conserva(stato: MutableMapping, chiavi: Iterable[str]) -> list[str]:
    """Salva nella copia il valore attuale di ogni chiave presente; ripristina dalla copia quelle sparite. Ritorna le chiavi ripristinate."""
    copia = stato.setdefault(CHIAVE_COPIA, {})
    ripristinate = []
    for k in chiavi:
        if k in stato:
            copia[k] = stato[k]
        elif k in copia:
            stato[k] = copia[k]
            ripristinate.append(k)
    return ripristinate
