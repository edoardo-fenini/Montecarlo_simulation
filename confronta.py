"""Confronto del rischio di 3 portafogli azionari + benchmark con Monte Carlo.
Uso:  python confronta.py                 (tutto, 20.000 simulazioni)
      python confronta.py --veloce        (1.000 simulazioni, per provare)
      python confronta.py --tappa 2       (si ferma alla tappa 2 di 5)
      python confronta.py --rifai         (ignora i risultati salvati)"""
import argparse, os, pickle, time, warnings
import numpy as np, pandas as pd
import dati, metriche
from simula import Bootstrap, StudentT, Garch, ConCrolli, ricentra, simula

warnings.filterwarnings("ignore")
NOMI = ["cyber", "finanza", "bigtech", "bench"]


def prepara(cfg, R, ricentrato=True, rend=None):
    """Ritorna (matrice rendimenti, porte, colonne). rend: rendimento atteso annuo (scalare o per gruppo)."""
    tit = dati.titoli_portafoglio(cfg)
    cols = [t for k in ("cyber", "finanza", "bigtech") for t in tit[k]] + ["BENCH"]
    M = R[cols].values
    porte, i = {}, 0
    for k in ("cyber", "finanza", "bigtech"):
        n = len(tit[k])
        porte[k] = (np.arange(i, i + n), np.full(n, 1 / n)); i += n
    porte["bench"] = (np.array([i]), np.array([1.0]))
    if ricentrato:
        rend = cfg["rendimento_atteso"] if rend is None else rend
        if isinstance(rend, dict):  # rendimento per gruppo di portafoglio
            v = np.zeros(M.shape[1])
            for k, (c, _) in porte.items():
                v[c] = rend[k]
            rend = v
        costi = np.zeros(M.shape[1]); costi[-1] = cfg["benchmark"]["ter"]
        M = ricentra(M, rend, costi, cfg["giorni_anno"])
    return M, porte, cols


def genera(modello, M, cfg, porte=None, idio=False):
    g = {"bootstrap": lambda: Bootstrap(M, cfg["blocco_medio_giorni"]),
         "t": lambda: StudentT(M, 5), "garch": lambda: Garch(M)}[modello]()
    if idio:
        stocks = np.concatenate([porte[k][0] for k in ("cyber", "finanza", "bigtech")])
        g = ConCrolli(g, stocks, cfg.get("idio_p_anno", 0.015))
    return g


class Archivio:
    def __init__(self, cartella, rifai):
        self.dir, self.rifai = cartella, rifai
        os.makedirs(cartella, exist_ok=True)

    def prendi(self, chiave, fun):
        f = f"{self.dir}/{chiave}.pkl"
        if os.path.exists(f) and not self.rifai:
            return pickle.load(open(f, "rb"))
        t = time.time()
        r = fun()
        pickle.dump(r, open(f, "wb"))
        print(f"  [{chiave}] calcolato in {time.time() - t:.0f}s", flush=True)
        return r


def esegui(cfg, R, n, modello="bootstrap", ricentrato=True, rend=None, idio=False, seed_extra=0):
    M, porte, _ = prepara(cfg, R, ricentrato, rend)
    gen = genera(modello, M, cfg, porte, idio)
    res = simula(gen, porte, n, cfg["orizzonte_anni"], cfg["capitale_iniziale"], cfg["versamento_mensile"],
                 cfg["costo_ribilanciamento"], cfg["checkpoint_anni"], cfg["seed"] + seed_extra, cfg["giorni_anno"])
    return metriche.sommario(res, cfg, n)


def storico(cfg, R):
    """Statistiche storiche per portafoglio: volatilità, max drawdown, contributo al rischio, correlazioni."""
    tit = dati.titoli_portafoglio(cfg)
    out = {"serie": {}, "stat": {}, "rc": {}, "corr_media": {}}
    for k in ("cyber", "finanza", "bigtech"):
        X = R[tit[k]].values
        w = np.full(X.shape[1], 1 / X.shape[1])
        out["serie"][k] = pd.Series(metriche.serie_portafoglio(X, w, 252, cfg["costo_ribilanciamento"]), index=R.index)
        rc, cm = metriche.contributo_rischio(X)
        out["rc"][k], out["corr_media"][k] = pd.Series(rc, index=tit[k]), cm
    out["serie"]["bench"] = R["BENCH"].copy()
    for k, s in out["serie"].items():
        out["stat"][k] = metriche.stat_storiche(s.values)
    out["corr"] = pd.DataFrame(out["serie"]).corr()
    out["periodo"] = (R.index[0], R.index[-1], len(R))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veloce", action="store_true")
    ap.add_argument("--tappa", type=int, default=5)
    ap.add_argument("--rifai", action="store_true")
    a = ap.parse_args()
    cfg = dati.carica_config()
    n = 1000 if a.veloce else cfg["n_simulazioni"]
    arc = Archivio("risultati_veloce" if a.veloce else "risultati", a.rifai)
    print(f"Simulazioni per run: {n}")

    Rall, eur = dati.rendimenti_eur(cfg)
    avvisi = dati.controlli(Rall, eur, cfg)
    an = dati.costruisci_analisi(cfg, Rall)
    ris = {"cfg": cfg, "n": n, "avvisi": avvisi, "frac_proxy": an["C"][1]["proxy"], "tappa": a.tappa,
           "periodi": {k: (v[0].index[0], v[0].index[-1], len(v[0])) for k, v in an.items()}}

    # ---- Tappa 2: versione base
    ris["storico"] = {k: arc.prendi(f"storico_{k}", lambda k=k: storico(cfg, an[k][0])) for k in "ABC"}
    for k in "AB":
        R = an[k][0]
        ris[f"base_{k}"] = arc.prendi(f"base_{k}", lambda R=R: esegui(cfg, R, n))
        ris[f"nr_{k}"] = arc.prendi(f"nr_{k}", lambda R=R: esegui(cfg, R, n, ricentrato=False))
    # ---- Tappa 3: stress test
    if a.tappa >= 3:
        for k in "AB":
            def fs(k=k):
                M, porte, _ = prepara(cfg, an[k][0])
                return metriche.stress_test(Bootstrap(M, cfg["blocco_medio_giorni"]), porte, cfg, ris[f"base_{k}"],
                                            n_rec=min(n, 2000))
            ris[f"stress_{k}"] = arc.prendi(f"stress_{k}", fs)
    # ---- Tappa 4: analisi C con proxy
    if a.tappa >= 4:
        ris["base_C"] = arc.prendi("base_C", lambda: esegui(cfg, an["C"][0], n))
    # ---- Tappa 5: modelli, sensibilità, rischio idiosincratico
    if a.tappa >= 5:
        for k in "AB":
            R = an[k][0]
            ris[f"mod_t_{k}"] = arc.prendi(f"mod_t_{k}", lambda R=R: esegui(cfg, R, n, "t"))
            ris[f"mod_garch_{k}"] = arc.prendi(f"mod_garch_{k}", lambda R=R: esegui(cfg, R, n, "garch"))
            for r in (0.03, 0.09):
                ris[f"sens_{int(r*100)}_{k}"] = arc.prendi(f"sens_{int(r*100)}_{k}", lambda R=R, r=r: esegui(cfg, R, n, rend=r))
            ris[f"sens_settori_{k}"] = arc.prendi(f"sens_settori_{k}", lambda R=R: esegui(cfg, R, n, rend=cfg["rendimenti_settoriali"]))
            ris[f"idio_{k}"] = arc.prendi(f"idio_{k}", lambda R=R: esegui(cfg, R, n, idio=True))
    from report import scrivi_report
    out = "report_veloce.html" if a.veloce else "report.html"
    scrivi_report(ris, out)
    print("Report scritto in", out)


if __name__ == "__main__":
    main()
