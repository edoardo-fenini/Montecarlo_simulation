"""Lettura e controllo della configurazione (file YAML o dizionario dall'app).

Un portafoglio è descritto da `nome` e `titoli`:
  - lista di ticker                  -> pesi uguali
  - dizionario ticker: peso (in %)   -> i pesi devono sommare a 100
Un "titolo" può anche essere il nome di un altro portafoglio o la parola `benchmark`:
così si costruiscono portafogli misti (es. 80% benchmark + 20% Cyber security).
"""
import copy
import yaml

BENCH = "BENCH"  # simbolo interno della serie del benchmark

RIBILANCIAMENTO_MESI = {"annuale": 12, "semestrale": 6, "trimestrale": 3, "mensile": 1, "mai": 0}
METODI = ("beta", "uguale", "storico", "personalizzato")

DEFAULT = {
    "nome": "confronto",
    "capitale_iniziale": 5000,
    "versamento_mensile": 0,
    "orizzonte_anni": 15,
    "orizzonti_intermedi": [5, 10],
    "n_simulazioni": 10000,
    "seed": 12345,
    "costo_ribilanciamento": 0.001,
    "ribilanciamento": "annuale",
    "blocco_medio_giorni": 20,
    "rendimento_atteso": {
        "metodo": "beta",
        "tasso_privo_rischio": 0.02,
        "premio_mercato": 0.04,
        "valore_uguale": 0.06,
        "personalizzato": {},
    },
    "benchmark": {
        "nome": "MSCI World (ETF)",
        "descrizione": "iShares Core MSCI World UCITS ETF USD (Acc)",
        "ticker": "IWDA.AS",
        "isin": "IE00B4L5Y983",
        "ter": 0.0020,
        "proxy_storico": "^990100-USD-STRD",
    },
    "moduli": {
        "stress_test": True,
        "rischio_singolo_titolo": True,
        "confronto_modelli": False,
        "analisi_C": False,
    },
    "analisi": {"inizio_B": "2007-01-01", "inizio_C": "1999-01-04"},
    "rischio_singolo_titolo": {"probabilita_annua": 0.015, "perdita_min": 0.8, "perdita_max": 1.0},
    "settori": {},   # opzionale: TICKER: tech | finanza | altro  (per gli stress test)
    "proxy": {},     # opzionale: TICKER: TICKER_PROXY            (per l'analisi C)
    "portafogli": [],
}


class ErroreConfig(Exception):
    """Errore nella configurazione, con un messaggio comprensibile."""


def _unisci(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _unisci(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def carica(percorso):
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = yaml.safe_load(f)
    except FileNotFoundError:
        raise ErroreConfig(f"Non trovo il file di configurazione «{percorso}».")
    except yaml.YAMLError as e:
        raise ErroreConfig(f"Il file «{percorso}» non è un YAML valido: {e}")
    return prepara(dati)


def _numero(cfg, chiave, minimo=None, massimo=None, intero=False):
    v = cfg[chiave]
    try:
        v = int(v) if intero else float(v)
    except (TypeError, ValueError):
        raise ErroreConfig(f"«{chiave}» deve essere un numero (trovato: {cfg[chiave]!r}).")
    if minimo is not None and v < minimo:
        raise ErroreConfig(f"«{chiave}» deve essere almeno {minimo} (trovato: {v}).")
    if massimo is not None and v > massimo:
        raise ErroreConfig(f"«{chiave}» deve essere al massimo {massimo} (trovato: {v}).")
    cfg[chiave] = v


def _pesi(nome, titoli):
    """Ritorna {ticker_o_portafoglio: peso in frazione} controllando che i pesi sommino a 100%."""
    if isinstance(titoli, str):
        titoli = [t.strip() for t in titoli.split(",") if t.strip()]
    if isinstance(titoli, list):
        titoli = {t: None for t in titoli}
    if not isinstance(titoli, dict) or not titoli:
        raise ErroreConfig(f"Il portafoglio «{nome}» non ha titoli.")
    chiavi = [str(k).strip() for k in titoli]
    if len(set(c.upper() for c in chiavi)) != len(chiavi):
        raise ErroreConfig(f"Il portafoglio «{nome}» contiene lo stesso titolo più volte.")
    valori = list(titoli.values())
    if all(v is None or v == "" for v in valori):
        return {c: 1 / len(chiavi) for c in chiavi}
    if any(v is None or v == "" for v in valori):
        raise ErroreConfig(f"Nel portafoglio «{nome}» alcuni titoli hanno il peso e altri no: indica tutti i pesi oppure nessuno (= pesi uguali).")
    try:
        valori = [float(v) for v in valori]
    except (TypeError, ValueError):
        raise ErroreConfig(f"Nel portafoglio «{nome}» c'è un peso che non è un numero.")
    if any(v < 0 for v in valori):
        raise ErroreConfig(f"Nel portafoglio «{nome}» c'è un peso negativo.")
    tot = sum(valori)
    if abs(tot - 100) <= 0.5:
        valori = [v / 100 for v in valori]
    elif abs(tot - 1) > 0.005:
        raise ErroreConfig(f"I pesi del portafoglio «{nome}» sommano a {tot:g}%: devono sommare a 100%.")
    s = sum(valori)
    return {c: v / s for c, v in zip(chiavi, valori)}


def prepara(dati):
    """Completa la configurazione con i default e la controlla. Solleva ErroreConfig."""
    if not isinstance(dati, dict):
        raise ErroreConfig("La configurazione è vuota o non è nel formato atteso.")
    cfg = _unisci(DEFAULT, dati)
    _numero(cfg, "capitale_iniziale", 0)
    _numero(cfg, "versamento_mensile", 0)
    if cfg["capitale_iniziale"] <= 0 and cfg["versamento_mensile"] <= 0:
        raise ErroreConfig("Serve un capitale iniziale o un versamento mensile maggiore di zero.")
    if cfg["capitale_iniziale"] <= 0:
        raise ErroreConfig("Il capitale iniziale deve essere maggiore di zero.")
    _numero(cfg, "orizzonte_anni", 1, 50, intero=True)
    _numero(cfg, "n_simulazioni", 100, 200000, intero=True)
    _numero(cfg, "seed", 0, intero=True)
    _numero(cfg, "costo_ribilanciamento", 0, 0.05)
    _numero(cfg, "blocco_medio_giorni", 1, 250)
    inter = cfg.get("orizzonti_intermedi") or []
    if isinstance(inter, (int, float)):
        inter = [inter]
    try:
        inter = sorted({int(x) for x in inter})
    except (TypeError, ValueError):
        raise ErroreConfig("«orizzonti_intermedi» deve essere una lista di anni, es. [5, 10].")
    cfg["orizzonti"] = [h for h in inter if 0 < h < cfg["orizzonte_anni"]] + [cfg["orizzonte_anni"]]
    if cfg["ribilanciamento"] not in RIBILANCIAMENTO_MESI:
        raise ErroreConfig(f"«ribilanciamento» deve essere uno tra: {', '.join(RIBILANCIAMENTO_MESI)}.")
    cfg["ribilanciamento_mesi"] = RIBILANCIAMENTO_MESI[cfg["ribilanciamento"]]

    ra = cfg["rendimento_atteso"]
    if ra["metodo"] not in METODI:
        raise ErroreConfig(f"Il metodo del rendimento atteso deve essere uno tra: {', '.join(METODI)}.")
    for k in ("tasso_privo_rischio", "premio_mercato", "valore_uguale"):
        try:
            ra[k] = float(ra[k])
        except (TypeError, ValueError):
            raise ErroreConfig(f"«rendimento_atteso.{k}» deve essere un numero (es. 0.04 per il 4%).")
        if abs(ra[k]) > 0.5:
            raise ErroreConfig(f"«rendimento_atteso.{k}» = {ra[k]}: scrivilo come frazione (0.04 = 4%).")

    b = cfg["benchmark"]
    if not b.get("ticker"):
        raise ErroreConfig("Manca il ticker del benchmark.")
    b["ter"] = float(b.get("ter") or 0)

    # ---- portafogli
    pf = cfg["portafogli"]
    if not isinstance(pf, list) or not pf:
        raise ErroreConfig("Indica almeno un portafoglio in «portafogli».")
    nomi = []
    for i, p in enumerate(pf):
        if not isinstance(p, dict) or not str(p.get("nome", "")).strip():
            raise ErroreConfig(f"Il portafoglio numero {i + 1} non ha un nome.")
        p["nome"] = str(p["nome"]).strip()
        if p["nome"].lower() in ("benchmark", b["nome"].lower()):
            raise ErroreConfig(f"Il nome «{p['nome']}» è riservato al benchmark: scegline un altro.")
        nomi.append(p["nome"])
        p["pesi"] = _pesi(p["nome"], p.get("titoli"))
    if len(set(n.lower() for n in nomi)) != len(nomi):
        raise ErroreConfig("Due portafogli hanno lo stesso nome.")

    if ra["metodo"] == "personalizzato":
        pers = {str(k).strip().lower(): v for k, v in (ra.get("personalizzato") or {}).items()}
        mancanti = [n for n in nomi if n.lower() not in pers]
        if mancanti:
            raise ErroreConfig("Metodo «personalizzato»: manca il rendimento atteso per " + ", ".join(f"«{m}»" for m in mancanti) + ".")
        try:
            ra["personalizzato"] = {n: float(pers[n.lower()]) for n in nomi}
            ra["personalizzato"][b["nome"]] = float(pers.get("benchmark", pers.get(b["nome"].lower(), ra["valore_uguale"])))
        except (TypeError, ValueError):
            raise ErroreConfig("Metodo «personalizzato»: i rendimenti devono essere numeri (es. 0.05 per il 5%).")

    cfg["composizione"] = appiattisci(cfg)
    cfg["settori"] = {str(k).upper(): str(v).lower() for k, v in (cfg.get("settori") or {}).items()}
    for t, s in cfg["settori"].items():
        if s not in ("tech", "finanza", "altro"):
            raise ErroreConfig(f"Settore di {t}: usa tech, finanza oppure altro (trovato «{s}»).")
    cfg["proxy"] = {str(k).upper(): str(v).upper() for k, v in (cfg.get("proxy") or {}).items()}
    return cfg


def appiattisci(cfg):
    """{nome portafoglio: {TICKER: peso}} risolvendo i portafogli misti. Il benchmark è l'ultimo."""
    per_nome = {p["nome"].lower(): p for p in cfg["portafogli"]}
    bnome = cfg["benchmark"]["nome"]

    def risolvi(nome, catena):
        if nome.lower() in catena:
            raise ErroreConfig("Portafogli misti in circolo: " + " → ".join(catena + [nome.lower()]))
        out = {}
        for chiave, w in per_nome[nome.lower()]["pesi"].items():
            k = chiave.lower()
            if k in ("benchmark", bnome.lower()):
                sotto = {BENCH: 1.0}
            elif k in per_nome:
                sotto = risolvi(k, catena + [nome.lower()])
            else:
                sotto = {chiave.upper(): 1.0}
            for t, v in sotto.items():
                out[t] = out.get(t, 0.0) + w * v
        return out

    comp = {p["nome"]: risolvi(p["nome"], []) for p in cfg["portafogli"]}
    comp[bnome] = {BENCH: 1.0}
    return comp


def misto(cfg, nome):
    """True se il portafoglio contiene altri portafogli o il benchmark."""
    for p in cfg["portafogli"]:
        if p["nome"] == nome:
            altri = {q["nome"].lower() for q in cfg["portafogli"]} | {"benchmark", cfg["benchmark"]["nome"].lower()}
            return any(k.lower() in altri for k in p["pesi"])
    return False


def in_yaml(cfg):
    """Configurazione 'pulita' (solo le chiavi dell'utente) come testo YAML."""
    tieni = [k for k in DEFAULT if k != "portafogli"]
    out = {k: cfg[k] for k in tieni if k in cfg}
    out["portafogli"] = []
    for p in cfg["portafogli"]:
        pesi = p.get("titoli")
        out["portafogli"].append({"nome": p["nome"], "titoli": pesi})
    return yaml.safe_dump(out, allow_unicode=True, sort_keys=False)
