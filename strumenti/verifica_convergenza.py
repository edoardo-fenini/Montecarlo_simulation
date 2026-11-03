"""Verifica che il numero di simulazioni basti (convergenza).

Uso:  python strumenti/verifica_convergenza.py [--config configurazioni/esempio_tre_portafogli.yaml]
Scrive i risultati in esempi/verifica_convergenza/ (risultati.md e CSV)."""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd

import analisi
import configurazione as C
from simula import GG, Bootstrap


def forma_array(cfg):
    """Mostra la forma reale degli array generati dal bootstrap (con 1.000 percorsi per blocco di calcolo)."""
    import dati as D

    arch = D.Archivio(log=lambda *a: None)
    d = D.costruisci(cfg, arch)
    per, _ = analisi.periodi(cfg, d["R"], None, arch, print)
    M, porte, colonne, _ = analisi.matrice(cfg, per["A"])
    g = Bootstrap(M, cfg["blocco_medio_giorni"])
    T = cfg["orizzonte_anni"] * 12 * GG
    g.prepara(1000, T, np.random.default_rng(0))
    b = g.blocco(0)
    return {
        "storia (giorni x colonne)": M.shape,
        "indici bootstrap per blocco di calcolo (percorsi x giorni)": g.idx.shape,
        "rendimenti di un mese (percorsi x giorni x colonne)": b.shape,
        "giorni simulati": T,
        "colonne (titoli)": M.shape[1],
        "colonne per portafoglio": {k: len(v[0]) for k, v in porte.items()},
    }


def e(v):
    return f"{v:,.0f} €".replace(",", ".")


def p(v):
    return f"±{v * 100:.1f}%".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configurazioni/esempio_tre_portafogli.yaml")
    ap.add_argument("--uscita", default="esempi/verifica_convergenza")
    a = ap.parse_args()
    cfg = C.carica(a.config)
    cfg["rendimento_atteso"]["metodo"] = "beta"
    for k in cfg["moduli"]:
        cfg["moduli"][k] = False  # solo la simulazione principale
    H = cfg["orizzonte_anni"]
    os.makedirs(a.uscita, exist_ok=True)
    righe, tempi = [], {}
    forme = forma_array(cfg)

    def corri(n, seed):
        t = time.time()
        ris = analisi.esegui(cfg, n=n, seed=seed, solo=["A"], log=lambda *x: None)
        s = ris["sim"]["A"]
        for k in s["nomi"]:
            righe.append(
                {
                    "n richiesto": n,
                    "seed": seed,
                    "percorsi effettivi": s["n_effettivi"],
                    "portafoglio": k,
                    "mediana": s["orizzonti"][H].loc["Valore mediano", k],
                    "p5": s["orizzonti"][H].loc["5° percentile", k],
                }
            )
        tempi[(n, seed)] = time.time() - t
        print(f"  n={n:>6} seed={seed}: {s['n_effettivi']} percorsi, {tempi[(n, seed)]:.0f}s", flush=True)

    for n in (1000, 5000, 10000, 20000):
        corri(n, cfg["seed"])
    for j in range(1, 5):
        corri(10000, cfg["seed"] + j)
    df = pd.DataFrame(righe)
    df.to_csv(os.path.join(a.uscita, "risultati.csv"), index=False, sep=";", decimal=",")

    out = [
        "# Verifica della convergenza",
        "",
        f"Configurazione: `{a.config}`, metodo beta, analisi A, orizzonte {H} anni.",
        "",
        "## Forma degli array",
        "",
    ]
    out += [f"- {k}: {v}" for k, v in forme.items()]
    out += [
        "",
        "## Al crescere del numero di simulazioni (stesso seed)",
        "",
        "| simulazioni | percorsi effettivi | portafoglio | mediana | 5° percentile | tempo (s) |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in df[df["seed"] == cfg["seed"]].iterrows():
        out.append(
            f"| {r['n richiesto']} | {r['percorsi effettivi']} | {r['portafoglio']} | {e(r['mediana'])} | {e(r['p5'])} | {tempi[(r['n richiesto'], r['seed'])]:.0f} |"
        )
    d10 = df[df["n richiesto"] == 10000]
    out += [
        "",
        "## 10.000 simulazioni con 5 seed diversi",
        "",
        "| portafoglio | mediana min–max | scarto max mediana | 5° perc. min–max | scarto max 5° perc. |",
        "|---|---|---|---|---|",
    ]
    for k, g in d10.groupby("portafoglio", sort=False):
        sm = (g["mediana"] - g["mediana"].mean()).abs().max() / g["mediana"].mean()
        sp = (g["p5"] - g["p5"].mean()).abs().max() / g["p5"].mean()
        out.append(
            f"| {k} | {e(g['mediana'].min())} – {e(g['mediana'].max())} | {p(sm)} | {e(g['p5'].min())} – {e(g['p5'].max())} | {p(sp)} |"
        )
    open(os.path.join(a.uscita, "risultati.md"), "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
