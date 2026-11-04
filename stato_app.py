"""Copia di sicurezza delle impostazioni dell'app.

Streamlit cancella lo stato dei widget che in un'esecuzione non vengono disegnati (per esempio se un'esecuzione si interrompe con un
errore a metà della barra laterale). Senza una copia, capitale, orizzonte, tassi … tornerebbero ai valori minimi (0 €, 1 anno).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping

CHIAVE_COPIA = "_impostazioni"
CHIAVE_CAMBIATI = "_cambiati"
# campi numerici che il browser, dopo aver ricreato i widget, può mandare tutti insieme con il valore di partenza (0 o minimo)
CAMPI_A_RISCHIO = frozenset({"capitale", "versamento", "orizzonte", "rf", "mrp", "uguale"})
SOGLIA_FALSO_ALLARME = 3  # un utente non cambia 3 campi numerici nella stessa interazione


def segnala(stato: MutableMapping, k: str) -> None:
    """on_change di un campo: il campo è stato cambiato (dall'utente o, a volte, dal browser per errore). Si decide in `conserva`."""
    stato.setdefault(CHIAVE_CAMBIATI, []).append(k)


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
    cambiati = list(dict.fromkeys(stato.pop(CHIAVE_CAMBIATI, [])))
    falso_allarme = len([k for k in cambiati if k in CAMPI_A_RISCHIO]) >= SOGLIA_FALSO_ALLARME
    if not falso_allarme:  # cambi voluti dall'utente: entrano nella copia
        for k in cambiati:
            if k in stato:
                copia[k] = stato[k]
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
