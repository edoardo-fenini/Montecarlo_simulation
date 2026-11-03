"""Esegue l'intero confronto a partire da una configurazione già controllata.

Uso:  ris = esegui(cfg, aggiorna_dati=False, progresso=funzione(frazione, messaggio), log=print)
"""
import time
import numpy as np
import pandas as pd

import dati as D
import metriche
from configurazione import BENCH
from simula import Bootstrap, StudentT, Garch, ConCrolli, ricentra, simula


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


def spiega_rendimenti(cfg, beta):
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
        ter = cfg["benchmark"]["ter"] * pesi.get(BENCH, 0.0)
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


def prepara_M(cfg, M, colonne, mu):
    if mu is None:
        return M
    ter = np.array([cfg["benchmark"]["ter"] if t == BENCH else 0.0 for _, t in colonne])
    return ricentra(M, mu, ter, 252)


# ------------------------------------------------------------------ periodi A, B, C
def periodi(cfg, R, proxy_info, arch, log):
    titoli = list(R.columns)
    out, note = {}, {}
    inizio_A = max(R[t].first_valid_index() for t in titoli)
    A = R.loc[inizio_A:].dropna()
    if len(A) < 252:
        raise D.ErroreDati(f"Il periodo comune a tutti i titoli è troppo breve ({len(A)} giorni di borsa, dal {inizio_A:%d/%m/%Y}). "
                           "Servono almeno 12 mesi: togli o sostituisci i titoli quotati più di recente.")
    out["A"] = A
    inizio_B = pd.Timestamp(cfg["analisi"]["inizio_B"])
    if inizio_A > inizio_B + pd.Timedelta(days=365):
        primi = [min(R[t].first_valid_index() for t in pesi) for pesi in cfg["composizione"].values()]
        out["B"] = R.loc[max([inizio_B] + primi):]
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
    def __init__(self, pesi, callback):
        self.pesi, self.cb, self.fatto = pesi, callback, 0.0
        self.tot = sum(pesi.values()) or 1

    def passo(self, nome, messaggio):
        base = self.fatto
        peso = self.pesi[nome]

        def f(x):
            if self.cb:
                self.cb(min((base + peso * x) / self.tot, 1.0), messaggio)
        f(0)
        self.fatto += peso
        return f


def esegui(cfg, aggiorna_dati=False, progresso=None, log=print, cartella_cache=D.CARTELLA_CACHE, scaricatore=None, n=None):
    t0 = time.time()
    n = n or cfg["n_simulazioni"]
    mod = cfg["moduli"]
    if progresso:
        progresso(0.0, "Scarico/leggo i dati...")
    log("1/4  Dati: lettura dalla cache o download da Yahoo Finance")
    arch = D.Archivio(cartella_cache, aggiorna_dati, log, scaricatore)
    dati = D.costruisci(cfg, arch)
    R = dati["R"]
    proxy_info = None
    if mod["stress_test"] or mod["analisi_C"]:
        log("     riconoscimento del settore dei titoli")
        proxy_info, _ = D.classifica(cfg, dati, arch, log, serve_proxy=mod["analisi_C"])
    beta = stima_beta(R)
    log("2/4  Periodi di analisi")
    per, note = periodi(cfg, R, proxy_info, arch, log)
    anal = list(per)

    # piano di lavoro (per la barra di avanzamento)
    pesi = {}
    for a in anal:
        pesi[f"base_{a}"] = 1.0
        if mod["rischio_singolo_titolo"] and a != "C":
            pesi[f"idio_{a}"] = 1.0
        if mod["stress_test"] and a != "C":
            pesi[f"stress_{a}"] = 0.4
        if mod["confronto_modelli"] and a != "C":
            pesi[f"t_{a}"] = 1.0
            pesi[f"garch_{a}"] = 1.3
            for j in range(2 if cfg["rendimento_atteso"]["metodo"] != "storico" else 0):
                pesi[f"sens{j}_{a}"] = 1.0
    av = Avanzamento(pesi, progresso)

    tipi = dati["info"]["tipo"].to_dict()
    ris = {"cfg": cfg, "n": n, "dati_info": dati["info"], "avvisi": dati["avvisi"], "estremi": dati["estremi"],
           "ultimo_dato": dati["ultimo_dato"], "nomi": list(cfg["composizione"]), "bench_nome": cfg["benchmark"]["nome"],
           "beta": beta, "rend_attesi": spiega_rendimenti(cfg, beta), "proxy_info": proxy_info, "note": note,
           "periodi": {}, "storico": {}, "sim": {}, "stress": {}, "idio": {}, "modelli": {}, "sensibilita": {}}
    rib, costo = cfg["ribilanciamento_mesi"], cfg["costo_ribilanciamento"]

    def corri(gen, porte, chiave, msg, seed_extra=0):
        cb = av.passo(chiave, msg)
        log(f"     {msg} ...")
        res = simula(gen, porte, n, cfg["orizzonte_anni"], cfg["capitale_iniziale"], cfg["versamento_mensile"],
                     costo, cfg["orizzonti"], cfg["seed"] + seed_extra, 252, rib_mesi=rib, progresso=cb)
        return metriche.sommario(res, cfg, n)

    log("3/4  Simulazioni")
    for a in anal:
        M, porte, colonne, idx = matrice(cfg, per[a])
        ris["periodi"][a] = (idx[0], idx[-1], len(idx))
        ris["storico"][a] = storico(cfg, M, porte, colonne, idx)
        mu = rendimento_colonne(cfg, colonne, beta=beta)
        Mr = prepara_M(cfg, M, colonne, mu)
        b = cfg["blocco_medio_giorni"]
        ris["sim"][a] = corri(Bootstrap(Mr, b), porte, f"base_{a}", f"Analisi {a}: simulazione principale")
        if a == "C":
            continue
        azioni = [i for i, (_, t) in enumerate(colonne) if t != BENCH and str(tipi.get(t, "")).upper() != "ETF"]
        if mod["rischio_singolo_titolo"]:
            rs = cfg["rischio_singolo_titolo"]
            g = ConCrolli(Bootstrap(Mr, b), azioni, rs["probabilita_annua"], (rs["perdita_min"], rs["perdita_max"]))
            ris["idio"][a] = corri(g, porte, f"idio_{a}", f"Analisi {a}: rischio sul singolo titolo")
        if mod["stress_test"]:
            cat = {p: [proxy_info[colonne[i][1]]["categoria"] for i in c] for p, (c, _) in porte.items()}
            singolo = {}
            for p, pesi_p in cfg["composizione"].items():
                ws = [w for t, w in pesi_p.items() if t != BENCH and str(tipi.get(t, "")).upper() != "ETF"]
                singolo[p] = max(ws) if ws else None
            log(f"     Analisi {a}: stress test ...")
            cb = av.passo(f"stress_{a}", f"Analisi {a}: stress test")
            ris["stress"][a] = metriche.stress_test(Bootstrap(Mr, b), porte, cfg, ris["sim"][a], cat, singolo,
                                                    n_rec=min(n, 1000), progresso=cb)
        if mod["confronto_modelli"]:
            ris["modelli"][a] = {
                "Student-t multivariata": corri(StudentT(Mr, 5), porte, f"t_{a}", f"Analisi {a}: modello Student-t"),
                "GARCH(1,1) + residui bootstrap": corri(Garch(Mr), porte, f"garch_{a}", f"Analisi {a}: modello GARCH"),
            }
            ris["sensibilita"][a] = sensibilita(cfg, M, porte, colonne, beta, corri, a)
    if progresso:
        progresso(1.0, "Completato")
    ris["durata"] = time.time() - t0
    log(f"4/4  Fatto in {ris['durata']:.0f} secondi")
    return ris


def sensibilita(cfg, M, porte, colonne, beta, corri, a):
    """Due varianti del rendimento atteso, una più bassa e una più alta di quella scelta."""
    ra = cfg["rendimento_atteso"]
    m = ra["metodo"]
    if m == "storico":
        return []
    if m == "beta":
        var = [(f"premio di mercato {ra['premio_mercato'] * 50:.0f}%", dict(premio=ra["premio_mercato"] / 2)),
               (f"premio di mercato {ra['premio_mercato'] * 150:.0f}%", dict(premio=ra["premio_mercato"] * 1.5))]
    elif m == "uguale":
        var = [(f"{(ra['valore_uguale'] - 0.03) * 100:.0f}% per tutti", dict(uguale=ra["valore_uguale"] - 0.03)),
               (f"{(ra['valore_uguale'] + 0.03) * 100:.0f}% per tutti", dict(uguale=ra["valore_uguale"] + 0.03))]
    else:
        var = [("tutti 3 punti più bassi", dict(spost=-0.03)), ("tutti 3 punti più alti", dict(spost=0.03))]
    out = []
    for j, (nome, kw) in enumerate(var):
        mu = rendimento_colonne(cfg, colonne, beta=beta, **kw)
        out.append((nome, corri(Bootstrap(prepara_M(cfg, M, colonne, mu), cfg["blocco_medio_giorni"]), porte,
                                f"sens{j}_{a}", f"Analisi {a}: sensibilità ({nome})")))
    return out


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
