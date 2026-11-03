"""Test di non regressione: con una configurazione fissa e un seed fisso i numeri chiave devono restare identici.

Rigenerare il riferimento SOLO per una modifica intenzionale al calcolo (da spiegare in CHANGELOG.md):
    python tests/non_regressione.py --aggiorna
"""

import copy
import json
import math
import os
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
sys.path.insert(0, QUI)

RIFERIMENTO = os.path.join(QUI, "riferimento_non_regressione.json")

CONFIG = {
    "nome": "non regressione",
    "capitale_iniziale": 1000,
    "versamento_mensile": 20,
    "orizzonte_anni": 4,
    "orizzonti_intermedi": [2],
    "n_simulazioni": 400,
    "seed": 4242,
    "benchmark": {"nome": "Benchmark test", "ticker": "BMK.AS", "ter": 0.002, "proxy_storico": "^IDX"},
    "analisi": {"inizio_B": "2012-06-01", "inizio_C": "2012-06-01"},
    "moduli": {
        "stress_test": True,
        "rischio_singolo_titolo": True,
        "confronto_modelli": True,
        "analisi_C": True,
        "verifica_convergenza": True,
    },
    "verifica_convergenza": {"numero_seed": 2},
    "settori": {"AAA.MI": "tech", "BBB.DE": "finanza", "CCC": "altro"},
    "proxy": {"BBB.DE": "AAA.MI"},
    "portafogli": [
        {"nome": "Uno", "titoli": ["AAA.MI", "BBB.DE"]},
        {"nome": "Due", "titoli": {"CCC": 60, "AAA.MI": 40}},
        {"nome": "Satellite", "titoli": {"benchmark": 80, "Uno": 20}},
    ],
}


def calcola():
    from dati_finti import crea_finto_yahoo

    import analisi
    import configurazione as C

    cfg = C.prepara(copy.deepcopy(CONFIG))
    with tempfile.TemporaryDirectory() as d:
        return analisi.esegui(cfg, cartella_cache=d, scaricatore=crea_finto_yahoo(), log=lambda *a: None)


def numeri_chiave(ris):
    """Dizionario piatto {chiave: numero} con i risultati principali."""
    out = {}

    def tab(prefisso, df):
        for r in df.index:
            for c in df.columns:
                out[f"{prefisso}|{r}|{c}"] = float(df.loc[r, c])

    def somm(prefisso, s):
        for h, df in s["orizzonti"].items():
            tab(f"{prefisso}|{h}a", df)
        tab(f"{prefisso}|var_es", s["var_es"])
        for k, v in s["vol_sim"].items():
            out[f"{prefisso}|vol_sim|{k}"] = float(v)

    for a, s in ris["sim"].items():
        somm(f"sim {a}", s)
        for k, st in ris["storico"][a]["stat"].items():
            for m, v in st.items():
                out[f"storico {a}|{m}|{k}"] = float(v)
    for a, s in ris["idio"].items():
        somm(f"idio {a}", s)
    for a, mm in ris["modelli"].items():
        for nome, s in mm.items():
            somm(f"modello {nome} {a}", s)
    for a, var in ris["sensibilita"].items():
        for nome, s in var:
            somm(f"sensibilita {nome} {a}", s)
    for a, df in ris["stress"].items():
        for _, r in df.iterrows():
            for col in ("Valore dopo lo shock", "Perdita (%)", "Anni per tornare al versato (mediana)", "Prob. di tornarci entro 10 anni"):
                out[f"stress {a}|{r['Portafoglio']}|{r['Scenario']}|{col}"] = float(r[col])
    c = ris["convergenza"]
    tab("convergenza|mediana", c["mediana"].T)
    tab("convergenza|p5", c["p5"].T)
    for k, v in ris["beta"].items():
        out[f"beta|{k}"] = float(v)
    return out


def confronta(attesi, ottenuti):
    """Lista delle differenze (vuota = tutto uguale). GARCH: tolleranza più larga (ottimizzatore numerico)."""
    diff = []
    for k in sorted(set(attesi) | set(ottenuti)):
        if k not in attesi or k not in ottenuti:
            diff.append(f"{k}: presente solo in {'riferimento' if k in attesi else 'nuovo calcolo'}")
            continue
        a, b = attesi[k], ottenuti[k]
        if isinstance(a, float) and math.isinf(a) and a == b:
            continue
        tol = 1e-3 if "GARCH" in k else 1e-7
        if not math.isclose(a, b, rel_tol=tol, abs_tol=1e-9):
            diff.append(f"{k}: riferimento {a!r}, ora {b!r}")
    return diff


def carica_riferimento():
    with open(RIFERIMENTO, encoding="utf-8") as f:
        return {k: (float("inf") if v == "inf" else v) for k, v in json.load(f).items()}


if __name__ == "__main__":
    if "--aggiorna" in sys.argv:
        n = numeri_chiave(calcola())
        with open(RIFERIMENTO, "w", encoding="utf-8") as f:
            json.dump(
                {k: ("inf" if isinstance(v, float) and math.isinf(v) else v) for k, v in n.items()},
                f,
                indent=1,
                ensure_ascii=False,
                sort_keys=True,
            )
        print(f"Riferimento salvato: {len(n)} numeri in {RIFERIMENTO}")
    else:
        d = confronta(carica_riferimento(), numeri_chiave(calcola()))
        print("Nessuna differenza" if not d else "\n".join(d[:50]))
