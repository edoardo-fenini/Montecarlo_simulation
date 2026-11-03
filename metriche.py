"""Metriche dei risultati simulati, statistiche storiche e stress test."""
import numpy as np
import pandas as pd
from simula import simula

RIGHE_ORIZZONTE = ["Totale versato", "Valore mediano", "5° percentile", "95° percentile", "Prob. sotto il versato",
                   "Max drawdown mediano", "Max drawdown peggiore (95%)",
                   "Tempo sott'acqua max, mediano (anni)", "Tempo sott'acqua max, peggiore 95% (anni)"]


def versato(capitale, versamento, mese):
    """Totale versato a fine mese `mese` (i versamenti partono dall'inizio del secondo mese)."""
    return capitale + versamento * max(mese - 1, 0)


def sommario(res, cfg, n_sim):
    """Riduce i risultati grezzi della simulazione a ciò che serve al report."""
    cap, ver = cfg["capitale_iniziale"], cfg["versamento_mensile"]
    nomi = [k for k in res if not k.startswith("_")]
    mesi = res[nomi[0]]["mensile"].shape[1] - 1
    s = {"nomi": nomi, "n_sim": n_sim, "n_effettivi": int(res[nomi[0]]["mensile"].shape[0]), "orizzonti": {}, "bande": {}, "mdd_fin": {}, "vol_sim": {}, "var_es": {},
         "versato": np.array([versato(cap, ver, j) for j in range(mesi + 1)])}
    for h in cfg["orizzonti"]:
        j, tot = h * 12, versato(cap, ver, h * 12)
        righe = {}
        for k in nomi:
            v = res[k]["mensile"][:, j].astype(float)
            mdd, uw = res[k]["mdd"][h].astype(float), res[k]["uw"][h].astype(float)
            righe[k] = dict(zip(RIGHE_ORIZZONTE, [
                tot, np.median(v), np.percentile(v, 5), np.percentile(v, 95), float((v < tot).mean()),
                np.median(mdd), np.percentile(mdd, 5), np.median(uw), np.percentile(uw, 95)]))
        s["orizzonti"][h] = pd.DataFrame(righe)
    tot1 = versato(cap, ver, 12)
    for k in nomi:
        m = res[k]["mensile"]
        s["bande"][k] = np.percentile(m, [5, 25, 50, 75, 95], axis=0)
        s["mdd_fin"][k] = res[k]["mdd"][cfg["orizzonte_anni"]].copy()
        s["vol_sim"][k] = res[k]["vol"]
        p = (m[:, 12].astype(float) - tot1) / tot1  # rendimento del primo anno
        q = np.percentile(p, 5)
        s["var_es"][k] = {"VaR 95% 1 anno": -q, "Expected Shortfall 95% 1 anno": -p[p <= q].mean()}
    s["var_es"] = pd.DataFrame(s["var_es"])
    s["corr_sim"] = pd.DataFrame(res["_corr"][1], index=nomi, columns=nomi)
    return s


# ------------------------------------------------------------------ storico
def serie_portafoglio(R, pesi, rib_giorni=252, costo=0.0):
    """Rendimenti giornalieri storici di un portafoglio ribilanciato ogni `rib_giorni` (0 = mai)."""
    R, w = np.asarray(R, float), np.asarray(pesi, float)
    passo = rib_giorni if rib_giorni else len(R)
    h, out = w.copy(), []
    for i in range(0, len(R), passo):
        G = np.cumprod(1 + R[i:i + passo], axis=0) * h
        v = G.sum(1)
        out.append(v / np.concatenate([[h.sum()], v[:-1]]) - 1)
        h = G[-1]
        tot = h.sum()
        tgt = tot * w
        h = tgt * (1 - costo * np.abs(h - tgt).sum() / tot)
    return np.concatenate(out)


def stat_storiche(r):
    v = np.cumprod(1 + np.asarray(r))
    return {"vol": float(np.std(r, ddof=1) * np.sqrt(252)), "mdd": float((v / np.maximum.accumulate(v) - 1).min()),
            "rend_annuo": float(v[-1] ** (252 / len(v)) - 1)}


def contributo_rischio(R, w):
    """Quota della varianza del portafoglio dovuta a ogni titolo + correlazione media tra i titoli."""
    R, w = np.asarray(R, float), np.asarray(w, float)
    C = np.cov(R.T)
    rc = w * (C @ w) / (w @ C @ w)
    corr = np.corrcoef(R.T)
    return rc, float(corr[np.triu_indices(len(w), 1)].mean())


# ------------------------------------------------------------------ stress test
SCENARI = {
    "Crollo tech stile 2000-2002 (30 mesi)": {"tech": -0.75, "finanza": -0.30, "altro": -0.45, "mercato": -0.45},
    "Crisi finanziaria stile 2008 (18 mesi)": {"tech": -0.50, "finanza": -0.75, "altro": -0.55, "mercato": -0.55},
}
SINGOLO = "Il titolo più pesante perde il 90%"


def stress_test(gen, porte, cfg, somm, categorie, peso_singolo, n_rec=2000, anni_rec=30, progresso=None):
    """Shock applicato al valore mediano simulato a metà orizzonte; poi una nuova simulazione stima
    quanti anni servono per tornare al totale versato.
    categorie: {portafoglio: lista categoria per colonna}; peso_singolo: {portafoglio: peso del titolo
    singolo più grande, None se non ci sono azioni singole}."""
    cap, ver = cfg["capitale_iniziale"], cfg["versamento_mensile"]
    mid = cfg["orizzonte_anni"] * 12 // 2
    casi = []
    for k in somm["nomi"]:
        v_mid = float(somm["bande"][k][2][mid])
        w = np.asarray(porte[k][1])
        for sc, perd in SCENARI.items():
            casi.append((k, sc, v_mid, float(sum(wi * perd[c] for wi, c in zip(w, categorie[k])))))
        if peso_singolo.get(k):
            casi.append((k, SINGOLO, v_mid, -0.90 * peso_singolo[k]))
    tgt = versato(cap, ver, mid)
    # Una sola simulazione di "crescita di 1 €" per portafoglio, riusata per tutti gli scenari: senza versamenti
    # il valore è proporzionale al capitale di partenza; i versamenti si aggiungono come percorso separato.
    percorsi = {}

    def crescita(k):
        if k not in percorsi:
            args = dict(n=n_rec, anni=anni_rec, costo_rb=cfg["costo_ribilanciamento"], checkpoint_anni=[anni_rec],
                        seed=cfg["seed"] + 99, giorni=252, rib_mesi=cfg["ribilanciamento_mesi"])
            G = simula(gen, {k: porte[k]}, capitale=1.0, versamento=0, **args)[k]["mensile"].astype(float)
            K = simula(gen, {k: porte[k]}, capitale=1e-9, versamento=ver, **args)[k]["mensile"].astype(float) if ver else 0.0
            percorsi[k] = (G, K)
        return percorsi[k]

    righe = []
    for i, (k, sc, v_mid, perdita) in enumerate(casi):
        v_dopo = v_mid * (1 + perdita)
        r = {"Portafoglio": k, "Scenario": sc, "Valore prima dello shock": v_mid, "Valore dopo lo shock": v_dopo,
             "Perdita (€)": v_mid - v_dopo, "Perdita (%)": -perdita, "Totale versato": tgt}
        if v_dopo >= tgt:
            r.update({"Anni per tornare al versato (mediana)": 0.0, "Prob. di tornarci entro 10 anni": 1.0, "Scende sotto il versato": False})
        else:
            G, K = crescita(k)
            m = v_dopo * G + K
            obiettivo = tgt + ver * np.arange(m.shape[1])
            hit = m >= obiettivo
            primo = np.where(hit.any(1), hit.argmax(1), 10 ** 6)
            r.update({"Anni per tornare al versato (mediana)": float(np.median(primo) / 12) if (primo < 10 ** 6).mean() > 0.5 else np.inf,
                      "Prob. di tornarci entro 10 anni": float((primo <= 120).mean()), "Scende sotto il versato": True})
        righe.append(r)
        if progresso:
            progresso((i + 1) / len(casi))
    return pd.DataFrame(righe)
