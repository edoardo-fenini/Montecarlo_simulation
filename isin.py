"""Codici ISIN: riconoscimento, cifra di controllo e conversione in ticker Yahoo Finance.

Come funziona la conversione (metodi provati davvero, vedi README):
  1) OpenFIGI (API gratuita, nessuna chiave obbligatoria): elenca TUTTE le quotazioni di un ISIN con il codice
     di borsa; il codice borsa Bloomberg diventa il suffisso Yahoo (NA -> .AS, IM -> .MI, GY -> .DE ...).
  2) Ricerca di Yahoo Finance (yfinance.Search): restituisce di solito una sola quotazione, ma già con il ticker
     Yahoo giusto. È la riserva se OpenFIGI non risponde o non trova nulla di utilizzabile.
Ogni ticker candidato viene poi verificato su Yahoo (esiste? valuta, storia, volumi, ultimo prezzo): quelli che
non esistono su Yahoo vengono scartati. La quotazione si sceglie con una regola configurabile (`isin.preferenze`).
Le conversioni si salvano in cache (cache_prezzi/isin_ticker.json)."""

from __future__ import annotations

import copy
import datetime
import json
import logging
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import configurazione as C
import fonti
from dati import ErroreDati
from nomi import parole, somiglianza_nomi

log = logging.getLogger("confronta")

FILE_CACHE = "isin_ticker.json"
URL_OPENFIGI = "https://api.openfigi.com/v3/mapping"
PREFERENZE_DEFAULT = ["EUR", ".MI", ".DE", ".AS"]
VOLUME_MINIMO_RELATIVO = 0.02  # sotto il 2% del volume della quotazione più scambiata = poco liquida (in fondo)
SOMIGLIANZA_NOMI_MIN = 0.4  # sotto questa somiglianza il nome di OpenFIGI e quello di Yahoo sono «molto diversi»
GIORNI_ATTIVA = 30  # una quotazione senza scambi da più di 30 giorni è considerata non attiva (messa in fondo)

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# codice borsa Bloomberg/OpenFIGI -> suffisso Yahoo Finance ("" = Stati Uniti)
SUFFISSI_YAHOO = {
    **dict.fromkeys(["US", "UN", "UW", "UQ", "UA", "UR", "UP"], ""),
    "NA": ".AS",
    "IM": ".MI",
    "GY": ".DE",
    "GR": ".DE",
    "GF": ".F",
    "GS": ".SG",
    "GM": ".MU",
    "GD": ".DU",
    "GH": ".HM",
    "GB": ".BE",
    "GI": ".HA",
    "FP": ".PA",
    "LN": ".L",
    "SW": ".SW",
    "SM": ".MC",
    "BB": ".BR",
    "ID": ".IR",
    "PL": ".LS",
    "FH": ".HE",
    "SS": ".ST",
    "DC": ".CO",
    "NO": ".OL",
    "AV": ".VI",
    "GA": ".AT",
    "PW": ".WA",
    "CN": ".TO",
    "JT": ".T",
    "HK": ".HK",
    "AU": ".AX",
    "SP": ".SI",
}


class ErroreIsin(ErroreDati):
    """ISIN non valido o non convertibile. `rete=True` se il problema è la connessione (non l'ISIN)."""

    def __init__(self, messaggio, rete=False, tipo="", nome=""):
        super().__init__(messaggio)
        self.rete = rete
        self.tipo = tipo  # tipo di strumento secondo OpenFIGI (anche se non si trova nessuna quotazione)
        self.nome = nome  # nome secondo OpenFIGI


# ------------------------------------------------------------------ riconoscimento
def normalizza(testo) -> str:
    return re.sub(r"\s+", "", str(testo or "")).upper()


def cifra_controllo_ok(isin: str) -> bool:
    """Controllo di Luhn sull'ISIN: le lettere diventano numeri (A=10 ... Z=35), poi si raddoppia una cifra su due da destra."""
    isin = normalizza(isin)
    if not ISIN_RE.match(isin):
        return False
    cifre = "".join(str(int(c, 36)) for c in isin)
    tot = 0
    for i, c in enumerate(reversed(cifre)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        tot += n
    return tot % 10 == 0


def riconosci(testo) -> tuple[str, str]:
    """('isin', ISIN) se ha la forma di un ISIN con cifra di controllo giusta; ('isin_errato', ISIN) se ha la forma di
    un ISIN ma la cifra di controllo non torna (quasi certamente un errore di battitura); altrimenti ('ticker', TICKER)."""
    t = normalizza(testo)
    if ISIN_RE.match(t):
        return ("isin", t) if cifra_controllo_ok(t) else ("isin_errato", t)
    return "ticker", t


def e_isin(testo) -> bool:
    return riconosci(testo)[0] == "isin"


# ------------------------------------------------------------------ rete
def _http(url, dati=None, intestazioni=None, timeout=fonti.TIMEOUT) -> bytes:
    """GET (o POST se `dati`) con i certificati di certifi. Errori di rete e 429 -> ErroreRete; 400/404 -> b''."""
    h = {"User-Agent": fonti.AGENTE, "Accept": "application/json", **(intestazioni or {})}
    req = urllib.request.Request(url, data=dati, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=fonti._contesto_ssl()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (404, 400):
            return b""
        raise fonti.ErroreRete(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise fonti.ErroreRete(str(e)) from e


def _pulisci_ticker(t: str) -> str | None:
    t = (t or "").strip().upper().replace(" ", "")
    if t.endswith("/"):
        t = t[:-1]
    t = t.replace("/", "-")
    return t if re.fullmatch(r"[A-Z0-9][A-Z0-9\-]*", t) else None


TIPO_AZIONE, TIPO_ETF, TIPO_FONDO = "azione", "ETF/ETC", "fondo comune"
_TIPI_FONDO = {"open-end fund", "mutual fund", "unit inv trust", "unit trust", "open end fund"}
_TIPI_AZIONE = {"common stock", "adr", "gdr", "preference", "preferred stock", "reit", "depositary receipt", "right", "ordinary shares"}


def classifica_tipo(dati_figi: list[dict]) -> str:
    """Tipo di strumento da una risposta di OpenFIGI (campi securityType, securityType2): 'azione', 'ETF/ETC' o 'fondo comune'
    ('' se non si capisce). Se tra le quotazioni c'è un ETP (prodotto quotato in borsa: ETF o ETC) vince: un ETF ha anche
    securityType2 = «Mutual Fund», ma è quotato. Un fondo comune ha solo «Open-End Fund»."""
    tipi = {str(x.get("securityType") or "").strip().lower() for x in dati_figi}
    tipi2 = {str(x.get("securityType2") or "").strip().lower() for x in dati_figi}
    if "etp" in tipi or "closed-end fund" in tipi or "exchange traded fund" in tipi:
        return TIPO_ETF
    if tipi & _TIPI_FONDO:
        return TIPO_FONDO
    if tipi & _TIPI_AZIONE or "common stock" in tipi2:
        return TIPO_AZIONE
    if "mutual fund" in tipi2:
        return TIPO_FONDO
    return ""


def tipo_da_yahoo(tipo_yahoo: str) -> str:
    """Tipo di Yahoo (instrumentType) -> stessa classificazione. '' se sconosciuto."""
    return {"EQUITY": TIPO_AZIONE, "ETF": TIPO_ETF, "MUTUALFUND": TIPO_FONDO}.get(str(tipo_yahoo or "").upper(), "")


def candidati_openfigi(
    isin: str, http=None, chiave: str | None = None, non_mappate: list | None = None, info: dict | None = None
) -> list[dict]:
    """Quotazioni dell'ISIN secondo OpenFIGI, già convertite in ticker Yahoo (senza verificarle). Le quotazioni su borse di cui non
    conosco il suffisso Yahoo non sono utilizzabili: se si passa una lista in `non_mappate` ci si aggiungono {'borsa', 'ticker', 'nome'}.
    Se si passa un dizionario in `info`, vi si scrivono `tipo_strumento` (azione, ETF/ETC, fondo comune) e `nome_isin` (nome di OpenFIGI)."""
    http = http or _http
    chiave = chiave or os.environ.get("OPENFIGI_API_KEY") or None
    intest = {"Content-Type": "application/json", **({"X-OPENFIGI-APIKEY": chiave} if chiave else {})}
    corpo = json.dumps([{"idType": "ID_ISIN", "idValue": isin}]).encode()
    raw = fonti.con_tentativi(lambda: http(URL_OPENFIGI, dati=corpo, intestazioni=intest), tentativi=2, attesa=3.0)
    if not raw:
        return []
    try:
        dati = json.loads(raw)[0].get("data") or []
    except (ValueError, IndexError, AttributeError, TypeError):
        return []
    if info is not None and dati:
        info["tipo_strumento"] = classifica_tipo(dati)
        info["nome_isin"] = next((x.get("name") for x in dati if x.get("name")), "") or ""
    out, visti = [], set()
    for x in dati:
        suff = SUFFISSI_YAHOO.get(x.get("exchCode"))
        tk = _pulisci_ticker(x.get("ticker"))
        if suff is None:
            if non_mappate is not None and x.get("exchCode") and not any(n["borsa"] == x["exchCode"] for n in non_mappate):
                non_mappate.append({"borsa": x["exchCode"], "ticker": x.get("ticker") or "", "nome": x.get("name") or ""})
            continue
        if not tk:
            continue
        yt = tk + suff
        if yt not in visti:
            visti.add(yt)
            out.append({"ticker": yt, "nome_figi": x.get("name") or ""})
    return out


def candidati_yahoo_ricerca(isin: str, ricerca=None) -> list[dict]:
    """Ricerca di Yahoo Finance (yfinance.Search) per ISIN: di solito la quotazione principale."""
    if ricerca is None:

        def ricerca(q):
            import yfinance as yf

            return yf.Search(q, max_results=10, news_count=0).quotes

    try:
        quotes = ricerca(isin) or []
    except Exception as e:  # yfinance solleva tipi diversi (rete, limiti, formato)
        raise fonti.ErroreRete(str(e)) from e
    return [{"ticker": q["symbol"].upper(), "nome_ricerca": q.get("longname") or q.get("shortname") or ""} for q in quotes if q.get("symbol")]


def ispeziona_ticker(ticker: str, http=None, ispettore=None) -> dict | None:
    """Verifica che il ticker esista su Yahoo e ne legge valuta, borsa, nome, primo scambio, volume medio (3 mesi) e ultimo
    prezzo. None se Yahoo non lo conosce. Solleva ErroreRete se Yahoo non risponde."""
    if ispettore is not None:
        return ispettore(ticker)
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        h = tk.history(period="3mo", auto_adjust=False, actions=False, timeout=fonti.TIMEOUT)
        md = tk.history_metadata or {}
        if h is not None and not h.empty and md:
            vol = pd.to_numeric(h["Volume"], errors="coerce").dropna()
            ultimo = h.index[-1]
            return {
                "valuta": md.get("currency"),
                "borsa": md.get("fullExchangeName") or md.get("exchangeName") or "",
                "nome": md.get("longName") or md.get("shortName") or "",
                "tipo": md.get("instrumentType") or "",
                "primo": md.get("firstTradeDate"),
                "volume": float(vol.mean()) if len(vol) else 0.0,
                "ultimo": pd.Timestamp(ultimo).date().isoformat(),
            }
    except Exception as e:
        log.info("%s: yfinance non ha risposto (%s), provo l'API diretta", ticker, e)
    return _ispeziona_diretto(ticker, http or _http)


def _ispeziona_diretto(ticker: str, http) -> dict | None:
    import urllib.parse

    raw = fonti.con_tentativi(
        lambda: http(f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=3mo&interval=1d"),
        tentativi=2,
    )
    if not raw:
        return None
    try:
        r = json.loads(raw)["chart"]["result"][0]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    md, ts = r.get("meta", {}), r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    vol = pd.to_numeric(pd.Series(q.get("volume") or []), errors="coerce").dropna()
    if not ts:
        return None
    return {
        "valuta": md.get("currency"),
        "borsa": md.get("fullExchangeName") or md.get("exchangeName") or "",
        "nome": md.get("longName") or md.get("shortName") or "",
        "tipo": md.get("instrumentType") or "",
        "primo": md.get("firstTradeDate"),
        "volume": float(vol.mean()) if len(vol) else 0.0,
        "ultimo": datetime.datetime.fromtimestamp(ts[-1], datetime.UTC).date().isoformat(),
    }


def _anni_di_storia(primo, oggi: datetime.date) -> float:
    """Anni dal primo scambio. `primo` può essere un timestamp (secondi), una data o None."""
    if primo is None or primo == "":
        return 0.0
    try:
        if isinstance(primo, (int, float)):
            d0 = datetime.datetime.fromtimestamp(int(primo), datetime.UTC).date()
        else:
            d0 = pd.Timestamp(primo).date()
        return round((oggi - d0).days / 365.25, 1)
    except (TypeError, ValueError, OverflowError, OSError):
        return 0.0


def _verifica(cand: list[dict], oggi: datetime.date, http, ispettore, massimo: int) -> tuple[list[dict], bool]:
    """Verifica i candidati su Yahoo (in parallelo). Ritorna (quotazioni esistenti, True se ci sono stati problemi di rete)."""
    cand = cand[:massimo]
    problemi = []

    def uno(c):
        try:
            return c, ispeziona_ticker(c["ticker"], http, ispettore)
        except fonti.ErroreRete as e:
            problemi.append(str(e))
            return c, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        esiti = list(ex.map(uno, cand))
    out = []
    for c, m in esiti:
        if not m:
            continue
        storia = _anni_di_storia(m.get("primo"), oggi)
        out.append(
            {
                "ticker": c["ticker"],
                "nome": m.get("nome") or c.get("nome_figi") or c.get("nome_ricerca") or "",
                "nome_yahoo": m.get("nome") or "",
                "nome_figi": c.get("nome_figi") or "",
                "borsa": m.get("borsa") or "",
                "valuta": m.get("valuta") or "",
                "tipo": m.get("tipo") or "",
                "storia_anni": storia,
                "volume_medio": round(float(m.get("volume") or 0)),
                "ultimo_scambio": m.get("ultimo") or "",
            }
        )
    return out, bool(problemi) and not out


# ------------------------------------------------------------------ scelta della quotazione
def _corrisponde(q: dict, pref: str) -> bool:
    """Una preferenza è una valuta ("EUR") oppure un suffisso di borsa (".MI")."""
    if pref.startswith("."):
        return q["ticker"].upper().endswith(pref.upper())
    return (q.get("valuta") or "").upper() == pref.upper()


def nome_discordante(q: dict, somiglianza_min: float | None = SOMIGLIANZA_NOMI_MIN) -> bool:
    """True se il nome di OpenFIGI e quello di Yahoo (entrambi noti) sono molto diversi. Senza uno dei due nomi: False (nulla da confrontare)."""
    if somiglianza_min is None or not parole(q.get("nome_figi")) or not parole(q.get("nome_yahoo")):
        return False  # manca un nome (o resta solo «ETF», «Inc», ...): niente da confrontare
    return somiglianza_nomi(q["nome_figi"], q["nome_yahoo"]) < somiglianza_min


def ordina_quotazioni(
    quotazioni: list[dict],
    preferenze=None,
    oggi: datetime.date | None = None,
    volume_minimo_relativo: float = VOLUME_MINIMO_RELATIVO,
    somiglianza_min: float | None = SOMIGLIANZA_NOMI_MIN,
) -> list[dict]:
    """Ordina dalla più alla meno preferita. Regola: prima le quotazioni attive (scambi negli ultimi 30 giorni) e abbastanza
    liquide (volume medio almeno il 2% di quello della quotazione più scambiata: evita borse minori con pochi scambi); poi, nell'ordine,
    quelle che soddisfano la 1ª preferenza (default EUR), tra queste la 2ª (.MI), la 3ª (.DE), la 4ª (.AS), poi tutte le altre;
    a parità, più anni di storia (interi) e poi più volumi medi. Le quotazioni il cui nome Yahoo è molto diverso da quello di OpenFIGI
    (`nome_discordante`) vanno dopo tutte le altre: si prova la successiva (`somiglianza_min=None` spegne questo controllo)."""
    preferenze = list(preferenze or PREFERENZE_DEFAULT)
    oggi = oggi or datetime.date.today()

    def attiva(q):
        try:
            return (oggi - datetime.date.fromisoformat(q.get("ultimo_scambio") or "")).days <= GIORNI_ATTIVA
        except ValueError:
            return False

    vmax = max((q.get("volume_medio") or 0 for q in quotazioni), default=0)

    def liquida(q):
        return (q.get("volume_medio") or 0) >= vmax * volume_minimo_relativo

    def chiave(q):
        return (
            q.get("penalita", 0),  # solo fondi comuni (fondi.py): valuta, classe o copertura diverse da quelle attese
            nome_discordante(q, somiglianza_min),
            not attiva(q),
            not liquida(q),
            *(not _corrisponde(q, p) for p in preferenze),
            -int(q.get("storia_anni") or 0),
            -(q.get("volume_medio") or 0),
            q["ticker"],
        )

    return sorted(quotazioni, key=chiave)


def scegli_quotazione(quotazioni: list[dict], preferenze=None, oggi=None) -> dict | None:
    o = ordina_quotazioni(quotazioni, preferenze, oggi)
    return o[0] if o else None


# ------------------------------------------------------------------ cache
def _percorso_cache(cartella: str) -> str:
    return os.path.join(cartella, FILE_CACHE)


def _leggi_cache(cartella: str) -> dict:
    try:
        with open(_percorso_cache(cartella), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _scrivi_cache(cartella: str, cache: dict) -> None:
    try:
        os.makedirs(cartella, exist_ok=True)
        with open(_percorso_cache(cartella), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    except OSError as e:
        log.warning("Non riesco a salvare la cache degli ISIN: %s", e)


MESSAGGIO_FONDO_NON_TROVATO = (
    "È un fondo comune non quotato e non è disponibile nelle fonti online. "
    "Puoi caricare lo storico delle quote oppure scegliere un proxy."
)


# ------------------------------------------------------------------ conversione
def cerca_quotazioni(
    isin, http=None, chiave=None, massimo=12, oggi=None, ricerca=None, ispettore=None, preferenze=None, extra: dict | None = None
) -> tuple[list[dict], str]:
    """Tutte le quotazioni Yahoo trovate per l'ISIN e il metodo usato ('OpenFIGI' o 'Ricerca Yahoo Finance').
    Solleva ErroreIsin se non ne trova nessuna. Se si passa un dizionario in `extra`, vi si scrive `borse_non_mappate`: le quotazioni
    elencate da OpenFIGI su borse di cui non conosco il suffisso Yahoo (non utilizzabili, ma da segnalare)."""
    oggi = oggi or datetime.date.today()
    errori = []
    non_mappate: list[dict] = []
    extra = extra if extra is not None else {}
    extra["borse_non_mappate"] = non_mappate
    for metodo, fonte in (
        ("OpenFIGI", lambda: candidati_openfigi(isin, http, chiave, non_mappate, extra)),
        ("Ricerca Yahoo Finance", lambda: candidati_yahoo_ricerca(isin, ricerca)),
    ):
        try:
            cand = fonte()
        except fonti.ErroreRete as e:
            log.warning("%s: %s non risponde (%s)", isin, metodo, e)
            errori.append(f"{metodo}: {e}")
            continue
        if not cand:
            log.info("%s: %s non conosce questo ISIN", isin, metodo)
            continue
        # i candidati si verificano in ordine di preferenza di borsa, così il limite non taglia quelli importanti
        suffissi = [p.upper() for p in (preferenze or PREFERENZE_DEFAULT) if p.startswith(".")]
        cand.sort(key=lambda c: next((i for i, sfx in enumerate(suffissi) if c["ticker"].upper().endswith(sfx)), len(suffissi)))
        quote, rete = _verifica(cand, oggi, http, ispettore, massimo)
        if quote:
            log.info("%s: %d quotazioni trovate con %s", isin, len(quote), metodo)
            return quote, metodo
        if rete:
            errori.append(f"{metodo}: Yahoo non risponde")
    tipo, nome = extra.get("tipo_strumento", ""), extra.get("nome_isin", "")
    if errori and (tipo != TIPO_FONDO or any("Yahoo non risponde" in e for e in errori)):
        raise ErroreIsin(
            f"Non riesco a convertire l'ISIN {isin} in un ticker: le fonti online non rispondono ({'; '.join(errori)}). "
            "Controlla la connessione a internet e riprova, oppure scrivi direttamente il ticker Yahoo.",
            rete=True,
        )
    if tipo == TIPO_FONDO:
        raise ErroreIsin(MESSAGGIO_FONDO_NON_TROVATO, tipo=tipo, nome=nome)
    raise ErroreIsin(
        f"L'ISIN {isin} ha la forma giusta ma non trovo nessuna quotazione su Yahoo Finance (né con OpenFIGI né con la ricerca di "
        "Yahoo). Controlla il codice sul sito del broker oppure scrivi direttamente il ticker Yahoo.",
        tipo=tipo,
        nome=nome,
    )


def risolvi(
    isin,
    cartella: str,
    preferenze=None,
    scelta: str | None = None,
    aggiorna: bool = False,
    http=None,
    chiave=None,
    massimo=12,
    oggi=None,
    ricerca=None,
    ispettore=None,
    somiglianza_min: float | None = SOMIGLIANZA_NOMI_MIN,
) -> dict:
    """ISIN -> {'isin', 'ticker' (scelto), 'quotazioni' (ordinate), 'metodo', 'scelta_utente', 'avvisi_nome', 'borse_non_mappate'}.
    `scelta`: ticker imposto dall'utente (menu dell'app o `isin_scelte` in configurazione). Usa la cache su disco.
    `avvisi_nome`: frasi (da mostrare in GIALLO) sulle quotazioni il cui nome Yahoo è molto diverso da quello di OpenFIGI."""
    tipo, isin = riconosci(isin)
    if tipo == "isin_errato":
        raise ErroreIsin(f"«{isin}» sembra un ISIN ma la cifra di controllo non torna: c'è un errore di battitura. Ricontrolla il codice.")
    if tipo != "isin":
        raise ErroreIsin(f"«{isin}» non è un ISIN.")
    cache = _leggi_cache(cartella)
    voce = cache.get(isin)
    if not voce or aggiorna:
        extra: dict = {}
        try:
            quote, metodo = cerca_quotazioni(isin, http, chiave, massimo, oggi, ricerca, ispettore, preferenze, extra)
        except ErroreIsin as e:
            if e.tipo != TIPO_FONDO:
                raise
            quote, metodo = [], "OpenFIGI"
        if extra.get("tipo_strumento") == TIPO_FONDO:
            quote, metodo = _fondo_comune(isin, extra, quote, metodo, oggi, ricerca, ispettore, http)
        voce = {
            "metodo": metodo,
            "aggiornato": (oggi or datetime.date.today()).isoformat(),
            "quotazioni": quote,
            "borse_non_mappate": extra.get("borse_non_mappate", []),
            "tipo_strumento": extra.get("tipo_strumento", ""),
            "nome_isin": extra.get("nome_isin", ""),
        }
        cache[isin] = voce
        _scrivi_cache(cartella, cache)
        da_cache = False
    else:
        da_cache = True
    if not voce["quotazioni"]:  # fondo comune già cercato senza successo
        raise ErroreIsin(MESSAGGIO_FONDO_NON_TROVATO, tipo=voce.get("tipo_strumento", ""), nome=voce.get("nome_isin", ""))
    ordinate = ordina_quotazioni(voce["quotazioni"], preferenze, oggi, somiglianza_min=somiglianza_min)
    ticker = (scelta or "").strip().upper() or ordinate[0]["ticker"]
    # senza il confronto dei nomi, quale quotazione avrei scelto? Se è diversa, l'ho scartata perché il nome non torna
    prima = ordina_quotazioni(voce["quotazioni"], preferenze, oggi, somiglianza_min=None)[0]
    avvisi_nome = []
    if not scelta and prima["ticker"] != ticker and nome_discordante(prima, somiglianza_min):
        avvisi_nome.append(
            f"quotazione {prima['ticker']} scartata: il nome di OpenFIGI («{prima['nome_figi']}») è molto diverso da quello di Yahoo "
            f"(«{prima['nome_yahoo']}»); uso {ticker}"
        )
    scelta_q = next((q for q in ordinate if q["ticker"] == ticker), None)
    if scelta_q:
        avvisi_nome += scelta_q.get("avvisi_fondo", [])
    if scelta_q and nome_discordante(scelta_q, somiglianza_min):
        avvisi_nome.append(
            f"il nome di OpenFIGI («{scelta_q['nome_figi']}») è molto diverso da quello di Yahoo («{scelta_q['nome_yahoo']}») "
            f"per {ticker}: verifica che sia il titolo giusto"
        )
    return {
        "isin": isin,
        "ticker": ticker,
        "quotazioni": ordinate,
        "metodo": ("cache (" + voce["metodo"] + ")") if da_cache else voce["metodo"],
        "scelta_utente": bool(scelta),
        "predefinito": ordinate[0]["ticker"],
        "avvisi_nome": avvisi_nome,
        "borse_non_mappate": voce.get("borse_non_mappate", []),
        "tipo_strumento": voce.get("tipo_strumento") or tipo_da_yahoo(ordinate[0].get("tipo")),
        "nome_isin": voce.get("nome_isin", ""),
    }


def _fondo_comune(isin, extra, quote, metodo, oggi, ricerca, ispettore, http):
    """Per un fondo comune: tiene le quotazioni con almeno un anno di storia e cerca i codici Morningstar («0P...») di Yahoo.
    Ritorna (quotazioni, metodo); lista vuota se non trova niente di utilizzabile (la voce viene messa in cache lo stesso)."""
    import fondi

    utili = [q for q in quote if q.get("storia_anni", 0) >= fondi.STORIA_MIN_ANNI]
    nomi_yahoo = [q["nome_yahoo"] for q in quote if q.get("nome_yahoo")]
    trovati = fondi.cerca_fondo(isin, extra.get("nome_isin", ""), nomi_yahoo, oggi, ricerca, ispettore, http)
    if trovati:
        return utili + trovati, "Ricerca Yahoo Finance (codici fondo)"
    return utili, metodo


# ------------------------------------------------------------------ configurazione
def isin_nella_configurazione(cfg: dict) -> list[str]:
    """Tutti i valori che sembrano ISIN (anche con cifra errata) tra i titoli dei portafogli e il benchmark, senza doppioni."""
    visti = []
    cand = [k for p in cfg["portafogli"] for k in p["pesi"]] + [cfg["benchmark"]["ticker"]]
    for k in cand:
        tipo, v = riconosci(k)
        if tipo != "ticker" and v not in visti:
            visti.append(v)
    return visti


def storico_importato(cartella: str, isin: str) -> bool:
    """True se in cache c'è uno storico delle quote importato dall'utente per questo ISIN."""
    try:
        with open(os.path.join(cartella, re.sub(r"[^A-Za-z0-9._-]", "_", isin) + ".json"), encoding="utf-8") as f:
            return json.load(f).get("fonte") in ("CSV importato", "File CSV caricato a mano")
    except (OSError, ValueError):
        return False


def risolvi_configurazione(cfg: dict, cartella: str, aggiorna=False, http=None, log_fn=None, oggi=None, ricerca=None, ispettore=None):
    """Sostituisce gli ISIN con i ticker scelti. Ritorna (cfg nuova, {ISIN: risoluzione}). Gli ISIN senza risposta
    sollevano ErroreIsin. Aggiunge `cfg['isin_di']` = {TICKER: ISIN} per il report.
    Gli ISIN con uno storico importato (CSV) restano ISIN (la cache li contiene); quelli con un proxy dichiarato usano il proxy."""
    proxy_dich = {k: v for k, v in (cfg.get("proxy_titoli") or {}).items()}
    tutti = isin_nella_configurazione(cfg)
    importati = {i for i in tutti if i in (cfg.get("prezzi_da_file") or {}) or storico_importato(cartella, i)}
    proxy_attivi = {k: v for k, v in proxy_dich.items() if k in {normalizza(x) for x in _titoli_cfg(cfg)} and k not in importati}
    da_cercare = [i for i in tutti if i not in importati and i not in proxy_attivi and (cfg.get("isin_mappa") or {}).get(i) != i]
    da_cercare += [v for v in proxy_attivi.values() if riconosci(v)[0] == "isin" and v not in da_cercare]
    if not da_cercare and not importati and not proxy_attivi:
        return cfg, {}
    opz = cfg["isin"]
    scelte = {normalizza(k): str(v).strip().upper() for k, v in (cfg.get("isin_scelte") or {}).items()}
    ris = {}
    for i in da_cercare:
        if log_fn:
            log_fn(f"  converto l'ISIN {i} in ticker ...")
        ris[i] = risolvi(
            i,
            cartella,
            opz["preferenze"],
            scelte.get(i),
            aggiorna,
            http,
            opz.get("openfigi_chiave"),
            opz["max_quotazioni"],
            oggi,
            ricerca,
            ispettore,
            cfg["controllo_dati"]["somiglianza_nome_min"],
        )
    mappa = {i: r["ticker"] for i, r in ris.items()}
    mappa.update({i: i for i in importati})
    proxy_ris = {k: mappa.get(v, ris[v]["ticker"] if v in ris else v) for k, v in proxy_attivi.items()}
    return applica_mappa(cfg, mappa, proxy_ris), ris


def _titoli_cfg(cfg: dict) -> list[str]:
    return [k for p in cfg["portafogli"] for k in p["pesi"]] + [cfg["benchmark"]["ticker"]]


def applica_mappa(cfg: dict, mappa: dict[str, str], proxy: dict[str, str] | None = None) -> dict:
    """Copia della configurazione con ISIN -> ticker in portafogli, benchmark e impostazioni per ticker.
    `proxy` = {titolo: ticker sostitutivo}: i dati del sostituto prendono il posto di quelli del titolo (resta traccia in `proxy_usati`)."""
    cfg = copy.deepcopy(cfg)
    proxy = proxy or {}

    def conv(k):
        return proxy.get(normalizza(k)) or mappa.get(normalizza(k), k)

    for p in cfg["portafogli"]:
        nuovi: dict = {}
        for k, v in p["pesi"].items():  # se due titoli finiscono sullo stesso ticker i pesi si sommano
            nuovi[conv(k)] = nuovi.get(conv(k), 0.0) + v
        p["pesi"] = nuovi
    cfg["proxy_usati"] = {**(cfg.get("proxy_usati") or {}), **proxy}
    b = cfg["benchmark"]
    b["ticker"] = conv(b["ticker"])
    for chiave in ("settori", "ter", "proxy", "prezzi_da_file"):
        cfg[chiave] = {normalizza(conv(k)): v for k, v in (cfg.get(chiave) or {}).items()}
    cfg["proxy"] = {k: conv(v) for k, v in cfg["proxy"].items()}
    cfg["composizione"] = C.appiattisci(cfg)
    inverso = dict(cfg.get("isin_di") or {})
    inverso.update({t: i for i, t in mappa.items()})
    cfg["isin_di"] = inverso
    cfg["isin_mappa"] = {**(cfg.get("isin_mappa") or {}), **mappa}
    return cfg
