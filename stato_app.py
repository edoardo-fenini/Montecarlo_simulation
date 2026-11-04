"""Copia di sicurezza delle impostazioni dell'app.

Streamlit cancella lo stato dei widget che in un'esecuzione non vengono disegnati (per esempio se un'esecuzione si interrompe con un
errore a metà della barra laterale). Senza una copia, capitale, orizzonte, tassi … tornerebbero ai valori minimi (0 €, 1 anno).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping

CHIAVE_COPIA = "_impostazioni"


def conserva(stato: MutableMapping, chiavi: Iterable[str], predefiniti: Mapping | None = None) -> list[str]:
    """Salva nella copia il valore attuale di ogni chiave presente; ripristina dalla copia quelle sparite. Ritorna le chiavi ripristinate.

    Se una chiave manca sia nello stato sia nella copia (non dovrebbe succedere) si usa il valore predefinito, se dato: così un campo
    non torna mai a 0 per caso (Streamlit, senza valore, parte da 0 o dal minimo del campo).
    """
    copia = stato.setdefault(CHIAVE_COPIA, {})
    ripristinate = []
    for k in chiavi:
        if k in stato:
            copia[k] = stato[k]
        elif k in copia:
            stato[k] = copia[k]
            ripristinate.append(k)
        elif predefiniti and k in predefiniti:
            stato[k] = copia[k] = predefiniti[k]
            ripristinate.append(k)
    return ripristinate
