"""Esegue l'intero confronto a partire da una configurazione già controllata.

Uso:  ris = esegui(cfg, aggiorna_dati=False, progresso=funzione(frazione, messaggio), log=print)
"""

import logging
import multiprocessing as mp
import os
import pickle
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import dati as D
import metriche
from configurazione import BENCH
from simula import Bootstrap, ConCrolli, Garch, StudentT, ricentra, simula

registro_log = logging.getLogger("confronta")


# ------------------------------------------------------------------ rendimenti attesi
def stima_beta(R):
    """Beta di ogni titolo rispetto al benchmark, su rendimenti settimanali (riduce l'effetto degli
    orari di chiusura diversi tra le borse), usando solo i dati reali disponibili."""
    W = D.settimanali(R)
    b = W[BENCH]
    out = {}
    for t in R.columns:
        if t == BENCH:
            out[t] = 1.0
            continue
        ok = W[t].notna() & b.notna()
        x, y = b[ok].values, W.loc[ok, t].values
        out[t] = float(np.cov(x, y)[0, 1] / x.var(ddof=1)) if ok.sum() >= 26 else 1.0
    return out


def rendimento_colonne(cfg, colonne, metodo=None, premio=None, uguale=None, spost=0.0, beta=None):
    """Rendimento atteso annuo per ogni colonna della matrice (None = storico, nessuna ricentratura).
    colonne: lista di (portafoglio, ticker)."""
    ra = cfg["rendimento_atteso"]
    metodo = metodo or ra["metodo"]
    if metodo == "storico":
        return None
    premio = ra["premio_mercato"] if premio is None else premio
    uguale = ra["valore_uguale"] if uguale is None else uguale
    out = []
    for p, t in colonne:
        if metodo == "beta":
            out.append(ra["tasso_privo_rischio"] + beta[t] * premio)
        elif metodo == "uguale":
            out.append(uguale)
        else:
            out.append(ra["personalizzato"][p] + spost)
    return np.array(out)


def ter_titolo(cfg, t, tipi=None):
    """Costo annuo (TER) sottratto con la ricentratura: quello del benchmark, quello indicato in
    configurazione per gli ETF, oppure il default per gli ETF senza TER noto. Le azioni non hanno TER."""
    if t == BENCH:
        return cfg["benchmark"]["ter"]
    if t in cfg["ter"]:
        return cfg["ter"][t]
    if str((tipi or {}).get(t, "")).upper() == "ETF":
        return cfg["ter_etf_default"]
    return 0.0


def spiega_rendimenti(cfg, beta, tipi=None):
    """Tabella: per portafoglio beta e rendimento atteso annuo (metodo scelto)."""
    ra, comp = cfg["rendimento_atteso"], cfg["composizione"]
    righe = {}
    for p, pesi in comp.items():
        bp = sum(w * beta[t] for t, w in pesi.items())
        if ra["metodo"] == "beta":
            mu = ra["tasso_privo_rischio"] + bp * ra["premio_mercato"]
        elif ra["metodo"] == "uguale":
            mu = ra["valore_uguale"]
        elif ra["metodo"] == "personalizzato":
            mu = ra["personalizzato"][p]
        else:
            mu = np.nan
        ter = sum(w * ter_titolo(cfg, t, tipi) for t, w in pesi.items()) if ra["metodo"] != "storico" else 0.0
        righe[p] = {"Beta verso il benchmark": bp, "Rendimento atteso annuo": mu, "di cui costi ETF (TER)": ter}
    return pd.DataFrame(righe)


# ------------------------------------------------------------------ matrice per la simulazione
def matrice(cfg, R):
    """Una colonna per ogni (portafoglio, titolo). I buchi (titolo non ancora quotato) sono riempiti con la
    media pesata dei titoli disponibili dello stesso portafoglio = pesi ridistribuiti tra quelli disponibili."""
    blocchi, porte, colonne, i = [], {}, [], 0
    for p, pesi in cfg["composizione"].items():
        tick, w = list(pesi), np.array(list(pesi.values()))
        X = R[tick].values.astype(float)
        disp = ~np.isnan(X)
        den = (disp * w).sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            media = np.nansum(X * w, 1) / den
        X = np.where(disp, X, media[:, None])
        blocchi.append(X)
        porte[p] = (np.arange(i, i + len(tick)), w)
        colonne += [(p, t) for t in tick]
        i += len(tick)
    M = np.hstack(blocchi)
    ok = ~np.isnan(M).any(1)
    return M[ok], porte, colonne, R.index[ok]


def prepara_M(cfg, M, colonne, mu, tipi=None):
    """Ricentra i rendimenti sul rendimento atteso `mu` e sottrae il TER di benchmark ed ETF.
    Con il metodo storico (mu None) i dati restano come sono: i prezzi storici degli ETF sono già al netto del TER."""
    if mu is None:
        return M
    ter = np.array([ter_titolo(cfg, t, tipi) for _, t in colonne])
    return ricentra(M, mu, ter, 252)


# ------------------------------------------------------------------ periodi A, B, C
def periodi(cfg, R, proxy_info, arch, log):
    titoli = list(R.columns)
    out, note = {}, {}
    inizio_A = max(R[t].first_valid_index() for t in titoli)
    A = R.loc[inizio_A:].dropna()
    if len(A) < 252:
        raise D.ErroreDati(
            f"Il periodo comune a tutti i titoli è troppo breve ({len(A)} giorni di borsa, dal {inizio_A:%d/%m/%Y}). "
            "Servono almeno 12 mesi: togli o sostituisci i titoli quotati più di recente."
        )
    out["A"] = A
    inizio_B = pd.Timestamp(cfg["analisi"]["inizio_B"])
    if inizio_A > inizio_B + pd.Timedelta(days=365):
        primi = [min(R[t].first_valid_index() for t in pesi) for pesi in cfg["composizione"].values()]
        out["B"] = R.loc[max([inizio_B] + primi) :]
    else:
        note["B"] = "Tutti i titoli hanno una storia lunga: il periodo comune (A) copre già il periodo lungo, quindi l'analisi B non serve."
    if cfg["moduli"]["analisi_C"]:
        inizio_C = pd.Timestamp(cfg["analisi"]["inizio_C"])
        C = R.loc[inizio_C:].copy()
        frac = {}
        rng = np.random.default_rng(7)
        for t in titoli:
            reale = C[t].notna()
            frac[t] = float((~reale).mean())
            if reale.all() or t == BENCH:
                continue
            px = D.rendimenti_proxy(arch, R, proxy_info[t]["proxy"]).reindex(C.index)
            ok = reale & px.notna()
            if ok.sum() < 120:
                continue
            x, y = px[ok].values, C.loc[ok, t].values
            beta = np.cov(x, y)[0, 1] / x.var(ddof=1)
            resid = y - y.mean() - beta * (x - x.mean())
            manca = ~reale & px.notna()
            C.loc[manca, t] = beta * px[manca].values + rng.choice(resid, size=int(manca.sum()))
        out["C"] = C.dropna()
        note["C_proxy"] = frac
    return out, note


# ------------------------------------------------------------------ esecuzione
class Avanzamento:
    """Avanzamento complessivo come media pesata dell'avanzamento dei singoli lavori (anche in parallelo)."""

    def __init__(self, pesi, callback):
        self.pesi, self.cb = pesi, callback
        self.fatto = {k: 0.0 for k in pesi}
        self.tot = sum(pesi.values()) or 1

    def aggiorna(self, chiave, frazione, messaggio):
        self.fatto[chiave] = max(self.fatto.get(chiave, 0.0), min(frazione, 1.0))
        if self.cb:
            self.cb(min(sum(self.pesi[k] * f for k, f in self.fatto.items()) / self.tot, 1.0), messaggio)


@dataclass
class Lavoro:
    """Una simulazione indipendente (ha il suo seed): si può eseguire in un altro processo con risultati identici."""

    chiave: str
    tipo: str  # bootstrap | crolli | t | garch | stress
    messaggio: str
    peso: float
    M: np.ndarray
    porte: dict
    seed_extra: int = 0
    extra: dict = field(default_factory=dict)


def _generatore(lav: Lavoro, cfg: dict):
    b = cfg["blocco_medio_giorni"]
    if lav.tipo == "t":
        return StudentT(lav.M, 5)
    if lav.tipo == "garch":
        return Garch(lav.M)
    if lav.tipo == "crolli":
        rs = cfg["rischio_singolo_titolo"]
        return ConCrolli(Bootstrap(lav.M, b), lav.extra["azioni"], rs["probabilita_annua"], (rs["perdita_min"], rs["perdita_max"]))
    return Bootstrap(lav.M, b)


def esegui_lavoro(lav: Lavoro, cfg: dict, n: int, coda=None, callback=None):
    """Esegue un lavoro. L'avanzamento va a `coda` (processo separato) oppure a `callback` (stesso processo)."""

    def prog(f):
        if coda is not None:
            coda.put((lav.chiave, f))
        elif callback is not None:
            callback(f)

    if lav.tipo == "stress":
        e = lav.extra
        return lav.chiave, metriche.stress_test(
            Bootstrap(lav.M, cfg["blocco_medio_giorni"]),
            lav.porte,
            cfg,
            e["sommario"],
            e["categorie"],
            e["singolo"],
            n_rec=min(n, 1000),
            progresso=prog,
        )
    res = simula(
        _generatore(lav, cfg),
        lav.porte,
        n,
        cfg["orizzonte_anni"],
        cfg["capitale_iniziale"],
        cfg["versamento_mensile"],
        cfg["costo_ribilanciamento"],
        cfg["orizzonti"],
        cfg["seed"] + lav.seed_extra,
        252,
        rib_mesi=cfg["ribilanciamento_mesi"],
        progresso=prog,
    )
    return lav.chiave, metriche.sommario(res, cfg, n)


def usa_parallelo(cfg: dict, n: int, n_lavori: int) -> bool:
    scelta = str(cfg.get("parallelo", "auto")).lower()
    if scelta in ("no", "false", "0") or n_lavori < 2 or (os.cpu_count() or 1) < 2:
        return False
    return scelta in ("si", "sì", "true", "1") or n >= 5000


def esegui_lavori(lavori: list, cfg: dict, n: int, av: Avanzamento, log=print) -> dict:
    """Esegue i lavori in parallelo (processi separati) quando conviene, altrimenti uno dopo l'altro.
    I risultati sono identici nei due casi, perché ogni lavoro ha il suo seed."""
    risultati = {}
    if usa_parallelo(cfg, n, len(lavori)):
        processi = max(1, min(len(lavori), os.cpu_count() or 1, 8))
        try:
            ctx = mp.get_context("spawn")
            with ctx.Manager() as gestore:
                coda = gestore.Queue()
                with ProcessPoolExecutor(max_workers=processi, mp_context=ctx) as ex:
                    futuri = {ex.submit(esegui_lavoro, lav, cfg, n, coda): lav for lav in lavori}
                    in_corso = set(futuri)
                    while in_corso:
                        finiti, in_corso = wait(in_corso, timeout=0.25, return_when=FIRST_COMPLETED)
                        while not coda.empty():
                            chiave, f = coda.get_nowait()
                            av.aggiorna(chiave, f, next(lv.messaggio for lv in lavori if lv.chiave == chiave))
                        for fu in finiti:
                            chiave, r = fu.result()  # un errore dentro un lavoro arriva qui come errore vero
                            risultati[chiave] = r
                            av.aggiorna(chiave, 1.0, futuri[fu].messaggio)
            log(f"     ({len(lavori)} simulazioni su {processi} processi in parallelo)")
            return risultati
        except (BrokenProcessPool, OSError, pickle.PicklingError, EOFError) as e:
            log(f"     parallelismo non disponibile ({e}): continuo in sequenza")
            registro_log.warning("parallelismo non disponibile: %s", e)
    for lav in lavori:
        if lav.chiave in risultati:
            continue
        log(f"     {lav.messaggio} ...")
        av.aggiorna(lav.chiave, 0.0, lav.messaggio)
        chiave, r = esegui_lavoro(lav, cfg, n, callback=lambda f, lav=lav: av.aggiorna(lav.chiave, f, lav.messaggio))
        risultati[chiave] = r
    return risultati


def esegui(
    cfg, aggiorna_dati=False, progresso=None, log=print, cartella_cache=D.CARTELLA_CACHE, scaricatore=None, n=None, solo=None, seed=None
):
    """solo: lista di analisi da fare (es. ["A"]); seed: sostituisce quello della configurazione."""
    t0 = time.time()
    tempi = {}
    n = n or cfg["n_simulazioni"]
    if seed is not None:
        cfg = {**cfg, "seed": int(seed)}
    mod = cfg["moduli"]
    if progresso:
        progresso(0.0, "Scarico/leggo i dati...")
    log("1/4  Dati: lettura dalla cache o download da Yahoo Finance")
    arch = D.Archivio(cartella_cache, aggiorna_dati, log, scaricatore)
    D.importa_da_configurazione(cfg, arch)
    dati = D.costruisci(cfg, arch)
    R = dati["R"]
    proxy_info = None
    if mod["stress_test"] or mod["analisi_C"]:
        log("     riconoscimento del settore dei titoli")
        proxy_info, _ = D.classifica(cfg, dati, arch, log, serve_proxy=mod["analisi_C"])
    beta = stima_beta(R)
    log("2/4  Periodi di analisi")
    per, note = periodi(cfg, R, proxy_info, arch, log)
    anal = [x for x in per if solo is None or x in solo]
    n_seed = int(cfg["verifica_convergenza"]["numero_seed"]) if mod.get("verifica_convergenza") else 1
    tempi["dati"] = time.time() - t0

    tipi = dati["info"]["tipo"].to_dict()
    ris = {
        "cfg": cfg,
        "n": n,
        "dati_info": dati["info"],
        "avvisi": dati["avvisi"],
        "estremi": dati["estremi"],
        "ultimo_dato": dati["ultimo_dato"],
        "nomi": list(cfg["composizione"]),
        "bench_nome": cfg["benchmark"]["nome"],
        "beta": beta,
        "rend_attesi": spiega_rendimenti(cfg, beta, tipi),
        "proxy_info": proxy_info,
        "note": note,
        "periodi": {},
        "storico": {},
        "sim": {},
        "stress": {},
        "idio": {},
        "modelli": {},
        "sensibilita": {},
        "convergenza": None,
    }

    # ---- piano dei lavori: le simulazioni indipendenti tra loro (ognuna con il suo seed)
    lavori, stress_da_fare, nomi_sens = [], {}, {}
    for a in anal:
        M, porte, colonne, idx = matrice(cfg, per[a])
        ris["periodi"][a] = (idx[0], idx[-1], len(idx))
        ris["storico"][a] = storico(cfg, M, porte, colonne, idx)
        Mr = prepara_M(cfg, M, colonne, rendimento_colonne(cfg, colonne, beta=beta), tipi)
        lavori.append(Lavoro(f"base_{a}", "bootstrap", f"Analisi {a}: simulazione principale", 1.0, Mr, porte))
        if a == "A":
            ris["matrici"] = {"A": (Mr, porte)}  # per la prova rapida dei pesi nell'app
            for j in range(1, n_seed):  # stessa simulazione con seed diversi: verifica che le simulazioni bastino
                lavori.append(
                    Lavoro(f"conv{j}", "bootstrap", f"Verifica: stessa simulazione con il seed n. {j + 1}", 1.0, Mr, porte, 1000 * j)
                )
        if a == "C":
            continue
        if mod["rischio_singolo_titolo"]:
            azioni = [i for i, (_, t) in enumerate(colonne) if t != BENCH and str(tipi.get(t, "")).upper() != "ETF"]
            lavori.append(
                Lavoro(f"idio_{a}", "crolli", f"Analisi {a}: rischio sul singolo titolo", 1.2, Mr, porte, extra={"azioni": azioni})
            )
        if mod["stress_test"]:
            cat = {p: [proxy_info[colonne[i][1]]["categoria"] for i in c] for p, (c, _) in porte.items()}
            singolo = {}
            for p, pesi_p in cfg["composizione"].items():
                ws = [w for t, w in pesi_p.items() if t != BENCH and str(tipi.get(t, "")).upper() != "ETF"]
                singolo[p] = max(ws) if ws else None
            stress_da_fare[a] = (Mr, porte, cat, singolo)
        if mod["confronto_modelli"]:
            lavori.append(Lavoro(f"t_{a}", "t", f"Analisi {a}: modello Student-t", 1.0, Mr, porte))
            lavori.append(Lavoro(f"garch_{a}", "garch", f"Analisi {a}: modello GARCH", 1.3, Mr, porte))
            for j, (nome_v, kw) in enumerate(varianti_sensibilita(cfg)):
                Mv = prepara_M(cfg, M, colonne, rendimento_colonne(cfg, colonne, beta=beta, **kw), tipi)
                lavori.append(Lavoro(f"sens{j}_{a}", "bootstrap", f"Analisi {a}: sensibilità ({nome_v})", 1.0, Mv, porte))
                nomi_sens[f"sens{j}_{a}"] = nome_v

    pesi = {lav.chiave: lav.peso for lav in lavori}
    pesi.update({f"stress_{a}": 0.4 for a in stress_da_fare})
    av = Avanzamento(pesi, progresso)

    log("3/4  Simulazioni")
    t1 = time.time()
    risultati = esegui_lavori(lavori, cfg, n, av, log)
    tempi["simulazioni"] = time.time() - t1
    if stress_da_fare:  # gli stress test usano il valore mediano della simulazione principale: vengono dopo
        t1 = time.time()
        lavori_s = [
            Lavoro(
                f"stress_{a}",
                "stress",
                f"Analisi {a}: stress test",
                0.4,
                Mr,
                porte,
                extra={"sommario": risultati[f"base_{a}"], "categorie": cat, "singolo": singolo},
            )
            for a, (Mr, porte, cat, singolo) in stress_da_fare.items()
        ]
        risultati.update(esegui_lavori(lavori_s, cfg, n, av, log))
        tempi["stress test"] = time.time() - t1

    # ---- raccolta dei risultati
    for a in anal:
        ris["sim"][a] = risultati[f"base_{a}"]
        if f"idio_{a}" in risultati:
            ris["idio"][a] = risultati[f"idio_{a}"]
        if f"stress_{a}" in risultati:
            ris["stress"][a] = risultati[f"stress_{a}"]
        if f"t_{a}" in risultati:
            ris["modelli"][a] = {"Student-t multivariata": risultati[f"t_{a}"], "GARCH(1,1) + residui bootstrap": risultati[f"garch_{a}"]}
            ris["sensibilita"][a] = [(nomi_sens[k], risultati[k]) for k in sorted(nomi_sens) if k.endswith(f"_{a}")]
    if "A" in anal and n_seed > 1:
        ris["convergenza"] = confronto_seed(cfg, [ris["sim"]["A"]] + [risultati[f"conv{j}"] for j in range(1, n_seed)], n)
    if progresso:
        progresso(1.0, "Completato")
    ris["durata"] = time.time() - t0
    tempi["totale"] = ris["durata"]
    ris["tempi"] = tempi
    registro_log.info("tempi: %s", ", ".join(f"{k} {v:.1f}s" for k, v in tempi.items()))
    log(f"4/4  Fatto in {ris['durata']:.0f} secondi")
    return ris


def prova_pesi(ris, satellite, quota_benchmark, n=2000):
    """Prova rapida: portafoglio misto «quota_benchmark» di benchmark + resto nel portafoglio «satellite», simulato con poche
    simulazioni (risultato approssimato). Ritorna i numeri chiave a fine orizzonte."""
    cfg = ris["cfg"]
    M, porte = ris["matrici"]["A"]
    cb, wb = porte[ris["bench_nome"]]
    cs, ws = porte[satellite]
    q = float(quota_benchmark)
    colonne = np.concatenate([cb, cs])
    pesi = np.concatenate([wb * q, ws * (1 - q)])
    tieni = pesi > 0
    mix = {"Mix": (colonne[tieni], pesi[tieni] / pesi[tieni].sum())}
    res = simula(
        Bootstrap(M, cfg["blocco_medio_giorni"]),
        mix,
        n,
        cfg["orizzonte_anni"],
        cfg["capitale_iniziale"],
        cfg["versamento_mensile"],
        cfg["costo_ribilanciamento"],
        cfg["orizzonti"],
        cfg["seed"],
        252,
        rib_mesi=cfg["ribilanciamento_mesi"],
    )
    s = metriche.sommario(res, cfg, n)
    o = s["orizzonti"][cfg["orizzonte_anni"]]["Mix"]
    return {
        "valore_mediano": o["Valore mediano"],
        "p5": o["5° percentile"],
        "prob_perdita": o["Prob. sotto il versato"],
        "mdd": o["Max drawdown mediano"],
        "vol": s["vol_sim"]["Mix"],
        "n": n,
    }


def confronto_seed(cfg, sommari, n):
    """Mediana e 5° percentile a fine orizzonte per ogni seed, e scarto massimo dalla media in %."""
    H = cfg["orizzonte_anni"]
    seeds = [cfg["seed"] + 1000 * j for j in range(len(sommari))]
    out = {"n": n, "seed": seeds, "soglia": cfg["verifica_convergenza"]["soglia"], "orizzonte": H}
    for riga, chiave in (("Valore mediano", "mediana"), ("5° percentile", "p5")):
        df = pd.DataFrame({sd: s["orizzonti"][H].loc[riga] for sd, s in zip(seeds, sommari)}).T
        out[chiave] = df
        out[f"scarto_{chiave}"] = (df - df.mean()).abs().max() / df.mean()
    out["sufficienti"] = bool((out["scarto_mediana"] <= out["soglia"]).all())
    return out


def varianti_sensibilita(cfg):
    """Due varianti del rendimento atteso, una più bassa e una più alta di quella scelta: [(nome, parametri), ...]."""
    ra = cfg["rendimento_atteso"]
    m = ra["metodo"]
    if m == "storico":
        return []
    if m == "beta":
        return [
            (f"premio di mercato {ra['premio_mercato'] * 50:.0f}%", dict(premio=ra["premio_mercato"] / 2)),
            (f"premio di mercato {ra['premio_mercato'] * 150:.0f}%", dict(premio=ra["premio_mercato"] * 1.5)),
        ]
    if m == "uguale":
        return [
            (f"{(ra['valore_uguale'] - 0.03) * 100:.0f}% per tutti", dict(uguale=ra["valore_uguale"] - 0.03)),
            (f"{(ra['valore_uguale'] + 0.03) * 100:.0f}% per tutti", dict(uguale=ra["valore_uguale"] + 0.03)),
        ]
    return [("tutti 3 punti più bassi", dict(spost=-0.03)), ("tutti 3 punti più alti", dict(spost=0.03))]


def storico(cfg, M, porte, colonne, idx):
    rib = cfg["ribilanciamento_mesi"] * 21
    out = {"serie": {}, "stat": {}, "rc": {}, "corr_media": {}}
    for p, (c, w) in porte.items():
        X = M[:, c]
        r = metriche.serie_portafoglio(X, w, rib, cfg["costo_ribilanciamento"])
        out["serie"][p] = pd.Series(r, index=idx)
        out["stat"][p] = metriche.stat_storiche(r)
        if len(c) > 1:
            rc, cm = metriche.contributo_rischio(X, w)
            out["rc"][p] = pd.Series(rc, index=[colonne[i][1].replace(BENCH, "benchmark") for i in c])
            out["corr_media"][p] = cm
    out["corr"] = pd.DataFrame(out["serie"]).corr()
    return out
