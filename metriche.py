"""Metriche, tabelle riassuntive, stress test e statistiche storiche."""
import numpy as np, pandas as pd
from simula import simula, GG


def versato(capitale, versamento, mese):
    return capitale + versamento * max(mese - 1, 0)


def sommario(res, cfg, n_sim):
    """Riduce i risultati grezzi a ciò che serve al report (piccolo da salvare)."""
    cap, ver = cfg["capitale_iniziale"], cfg["versamento_mensile"]
    nomi = [k for k in res if not k.startswith("_")]
    s = {"nomi": nomi, "n_sim": n_sim, "orizzonti": {}, "bande": {}, "mdd_fin": {}, "vol_sim": {},
         "var_es": {}, "mediane_mensili": {}}
    mesi = res[nomi[0]]["mensile"].shape[1] - 1
    s["versato"] = np.array([versato(cap, ver, j) for j in range(mesi + 1)])
    for h in cfg["checkpoint_anni"]:
        j, tot = h * 12, versato(cap, ver, h * 12)
        righe = {}
        for k in nomi:
            v = res[k]["mensile"][:, j].astype(float)
            mdd, uw = res[k]["mdd"][h].astype(float), res[k]["uw"][h].astype(float)
            righe[k] = {
                "Totale versato": tot,
                "Valore mediano": np.median(v), "5° percentile": np.percentile(v, 5), "95° percentile": np.percentile(v, 95),
                "Prob. sotto il versato": float((v < tot).mean()),
                "Max drawdown mediano": np.median(mdd), "Max drawdown peggiore (95%)": np.percentile(mdd, 5),
                "Tempo sott'acqua max, mediano (anni)": np.median(uw), "Tempo sott'acqua max, peggiore 95% (anni)": np.percentile(uw, 95),
            }
        s["orizzonti"][h] = pd.DataFrame(righe)
    for k in nomi:
        m = res[k]["mensile"]
        s["bande"][k] = np.percentile(m, [5, 25, 50, 75, 95], axis=0)
        h = max(cfg["checkpoint_anni"])
        s["mdd_fin"][k] = res[k]["mdd"][h].copy()
        s["vol_sim"][k] = res[k]["vol"]
        p = (m[:, 12] - cap) / cap  # rendimento a 1 anno
        var = -np.percentile(p, 5)
        es = -p[p <= np.percentile(p, 5)].mean()
        s["var_es"][k] = {"VaR 95% 1 anno": var, "Expected Shortfall 95% 1 anno": es}
    s["corr_sim"] = pd.DataFrame(res["_corr"][1], index=nomi, columns=nomi)
    s["var_es"] = pd.DataFrame(s["var_es"])
    return s


# ---------------------------------------------------------------- storico
def serie_portafoglio(R, pesi, rib=252, costo=0.0):
    """Rendimenti giornalieri di un portafoglio ribilanciato ogni `rib` giorni ai pesi target."""
    R, w = np.asarray(R, float), np.asarray(pesi, float)
    h, out = w.copy(), []
    for i in range(0, len(R), rib):
        blk = R[i:i + rib]
        G = np.cumprod(1 + blk, axis=0) * h
        v = G.sum(1)
        out.append(v / np.concatenate([[h.sum()], v[:-1]]) - 1)
        h = G[-1]
        tot = h.sum(); tgt = tot * w
        h = tgt * (1 - costo * np.abs(h - tgt).sum() / tot)
    return np.concatenate(out)


def stat_storiche(r):
    """Volatilità annua e max drawdown di una serie di rendimenti giornalieri."""
    v = np.cumprod(1 + np.asarray(r))
    dd = v / np.maximum.accumulate(v) - 1
    return {"vol": float(np.std(r, ddof=1) * np.sqrt(252)), "mdd": float(dd.min()),
            "rend_annuo": float(v[-1] ** (252 / len(v)) - 1)}


def contributo_rischio(R):
    """Contributo di ogni titolo alla varianza del portafoglio a pesi uguali + correlazione media."""
    R = np.asarray(R, float)
    n = R.shape[1]
    w = np.full(n, 1 / n)
    C = np.cov(R.T)
    rc = w * (C @ w) / (w @ C @ w)
    corr = np.corrcoef(R.T)
    return rc, float(corr[np.triu_indices(n, 1)].mean())


# ---------------------------------------------------------------- stress test
SCENARI = {
    "Crollo tech stile 2000-2002 (30 mesi)": {"tech": -0.75, "finanza": -0.30, "bench": -0.45},
    "Crisi finanziaria stile 2008 (18 mesi)": {"tech": -0.50, "finanza": -0.75, "bench": -0.55},
}
GRUPPO = {"cyber": "tech", "bigtech": "tech", "finanza": "finanza", "bench": "bench"}


def stress_test(gen, porte, cfg, sommario_base, n_rec=2000, anni_rec=30):
    """Applica gli shock al valore mediano simulato a metà orizzonte (nessun versamento) e stima
    con una nuova simulazione quanti anni servono per tornare al totale versato."""
    cap, ver = cfg["capitale_iniziale"], cfg["versamento_mensile"]
    mid = cfg["orizzonte_anni"] * 12 // 2
    nomi = sommario_base["nomi"]
    casi = []
    for k in nomi:
        v_mid = float(sommario_base["bande"][k][2][mid])
        w = np.asarray(porte[k][1])
        for sc, perd in SCENARI.items():
            casi.append((k, sc, v_mid, perd[GRUPPO[k]]))
        if k != "bench":  # un ETF mondiale non ha un "titolo con peso più alto"
            casi.append((k, "Singolo titolo più pesante perde il 90%", v_mid, -0.90 * float(w.max())))
    tgt = versato(cap, ver, mid)
    righe = []
    for k, sc, v_mid, perdita in casi:
        v_dopo = v_mid * (1 + perdita)
        r = {"Portafoglio": k, "Scenario": sc, "Valore a metà orizzonte": v_mid, "Valore dopo lo shock": v_dopo,
             "Perdita massima (€)": v_mid - v_dopo, "Perdita massima (%)": -perdita, "Totale versato": tgt}
        if v_dopo >= tgt:
            r.update({"Anni per tornare al versato (mediana)": 0.0, "Prob. ritorno entro 10 anni": 1.0, "Scende sotto il versato": False})
        else:
            sim = simula(gen, {k: porte[k]}, n_rec, anni_rec, v_dopo, 0, cfg["costo_ribilanciamento"], [anni_rec],
                         cfg["seed"] + 99, cfg["giorni_anno"])
            m = sim[k]["mensile"]
            hit = m >= tgt
            primo = np.where(hit.any(1), hit.argmax(1), 10 ** 6)
            ok = primo < 10 ** 6
            r.update({"Anni per tornare al versato (mediana)": float(np.median(primo) / 12) if ok.mean() > 0.5 else np.inf,
                      "Prob. ritorno entro 10 anni": float((primo <= 120).mean()), "Scende sotto il versato": True})
        righe.append(r)
    return pd.DataFrame(righe)
