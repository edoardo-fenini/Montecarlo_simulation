"""Copia di sicurezza delle impostazioni dell'app.

Streamlit cancella lo stato dei widget che in un'esecuzione non vengono disegnati (per esempio se un'esecuzione si interrompe con un
errore a metà della barra laterale). Senza una copia, capitale, orizzonte, tassi … tornerebbero ai valori minimi (0 €, 1 anno).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping

CHIAVE_COPIA = "_impostazioni"


def registra(stato: MutableMapping, k: str) -> None:
    """Il valore attuale di `k` è una scelta voluta (azione dell'utente o codice dell'app): lo scrive nella copia."""
    if k in stato:
        stato.setdefault(CHIAVE_COPIA, {})[k] = stato[k]


def conserva(stato: MutableMapping, chiavi: Iterable[str], predefiniti: Mapping | None = None) -> list[str]:
    """La copia è la fonte autorevole. A ogni esecuzione, PRIMA di disegnare i campi, rimette nello stato il valore della copia.
    Così un valore che cambia senza che l'utente l'abbia toccato (stato cancellato da Streamlit, valore di partenza 0/minimo
    mandato dal browser dopo una riesecuzione interrotta) non diventa mai la nuova impostazione. Le scelte vere (anche 0) entrano
    nella copia con `registra` (on_change dei campi). Una chiave senza copia la prende dallo stato, o dal valore predefinito.
    Ritorna le chiavi il cui valore è stato ripristinato."""
    copia = stato.setdefault(CHIAVE_COPIA, {})
    ripristinate = []
    for k in chiavi:
        if k in copia:
            if k not in stato or stato[k] != copia[k]:
                stato[k] = copia[k]
                ripristinate.append(k)
        elif k in stato:
            copia[k] = stato[k]
        elif predefiniti and k in predefiniti:
            stato[k] = copia[k] = predefiniti[k]
            ripristinate.append(k)
    return ripristinate
