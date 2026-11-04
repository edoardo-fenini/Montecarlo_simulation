"""Ricerca di titoli per nome (azienda o ETF) con la ricerca di Yahoo Finance (yfinance.Search), senza chiavi.

Per ogni risultato: nome, ticker Yahoo, ISIN (se si è cercato un ISIN: la ricerca di Yahoo non restituisce gli ISIN), borsa, valuta
(letta dai dati del ticker, perché la ricerca non la dà) e tipo. Al massimo 10 risultati; solo azioni, ETF, fondi e indici.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import fonti
import isin as I

TIPI = {"EQUITY": "Azione", "ETF": "ETF", "MUTUALFUND": "Fondo", "INDEX": "Indice"}
MASSIMO = 10


class ErroreRicerca(Exception):
    """La ricerca non è possibile (testo troppo corto, rete): il messaggio è per l'utente."""


def _ricerca_yahoo(testo: str) -> list[dict]:
    import yfinance as yf

    return yf.Search(testo, max_results=20, news_count=0).quotes


def cerca(testo: str, ricerca=None, ispettore=None, massimo: int = MASSIMO, con_valuta: bool = True) -> list[dict]:
    """Fino a `massimo` risultati: [{'nome', 'ticker', 'isin', 'borsa', 'valuta', 'tipo'}]. `ricerca(testo)` e `ispettore(ticker)`
    si possono sostituire (test senza internet). Solleva ErroreRicerca se il testo è troppo corto o se Yahoo non risponde."""
    testo = (testo or "").strip()
    if len(testo) < 2:
        raise ErroreRicerca("Scrivi almeno 2 caratteri del nome (per esempio «Enel» o «MSCI World»).")
    tipo, codice = I.riconosci(testo)
    if tipo == "isin_errato":
        raise ErroreRicerca(f"«{codice}» sembra un ISIN ma la cifra di controllo non torna: ricontrolla il codice.")
    isin_cercato = codice if tipo == "isin" else ""
    try:
        quotes = (ricerca or _ricerca_yahoo)(isin_cercato or testo) or []
    except Exception as e:  # yfinance solleva tipi diversi (rete, limiti, formato)
        raise ErroreRicerca(f"La ricerca di Yahoo Finance non risponde ({str(e)[:80]}). Controlla la connessione e riprova.") from e
    out, visti = [], set()
    for q in quotes:
        t = (q.get("symbol") or "").upper()
        tipo_q = (q.get("quoteType") or "").upper()
        if not t or t in visti or tipo_q not in TIPI:
            continue
        visti.add(t)
        out.append(
            {
                "nome": q.get("longname") or q.get("shortname") or t,
                "ticker": t,
                "isin": isin_cercato,
                "borsa": q.get("exchDisp") or q.get("exchange") or "",
                "valuta": q.get("currency") or "",
                "tipo": TIPI[tipo_q],
            }
        )
        if len(out) >= massimo:
            break
    if con_valuta:
        _completa_valute(out, ispettore)
    return out


def _completa_valute(risultati: list[dict], ispettore=None) -> None:
    """La ricerca di Yahoo non dà la valuta: la legge dai dati di ogni ticker (in parallelo). Se Yahoo non risponde resta vuota."""
    mancanti = [r for r in risultati if not r["valuta"]]

    def una(r):
        try:
            m = I.ispeziona_ticker(r["ticker"], ispettore=ispettore)
        except fonti.ErroreRete:
            return
        if m:
            r["valuta"] = m.get("valuta") or ""
            r["borsa"] = r["borsa"] or m.get("borsa") or ""

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(una, mancanti))


def etichetta(r: dict) -> str:
    """Una riga leggibile: «Enel S.p.A. · ENEL.MI · Milan · EUR · Azione» (con l'ISIN se noto)."""
    parti = [r["nome"], r["ticker"], r["isin"], r["borsa"], r["valuta"] or "valuta ?", r["tipo"]]
    return " · ".join(p for p in parti if p)


__all__ = ["cerca", "etichetta", "ErroreRicerca", "MASSIMO"]
