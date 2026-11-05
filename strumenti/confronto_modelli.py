"""Confronto tra modello «storico» e modello «a fattori» sull'esempio dei tre portafogli (dati reali Yahoo, serve internet o la cache).

Uso:  python strumenti/confronto_modelli.py [cartella_di_uscita] [numero_simulazioni]
Scrive risultati.md (tabelle come in esempi/confronto_modelli_v1_5/) e backtest_var.csv. Pensato per rigenerare il confronto a ogni versione."""

import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analisi  # noqa: E402
import configurazione as C  # noqa: E402

NOMI = {"Cyber security": "Cyber security", "Banche d'investimento / PE": "Banche / PE", "Big tech USA": "Big tech USA", "MSCI World (ETF)": "MSCI World"}


def esegui(modello, n, backtest=False):
    cfg = C.carica("configurazioni/esempio_tre_portafogli.yaml")
    cfg["moduli"].update(stress_test=False, rischio_singolo_titolo=False, verifica_convergenza=False, backtest_var=backtest)
    cfg["modello_simulazione"] = modello
    return analisi.esegui(cfg, n=n, solo=["A", "B"] if modello == "storico" else ["A"], log=lambda *a: None)


def righe(titolo, serie):
    """serie: {etichetta: valore per portafoglio}."""
    return titolo, serie


def main():
    uscita = sys.argv[1] if len(sys.argv) > 1 else "esempi/confronto_modelli_v1_5_1"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    os.makedirs(uscita, exist_ok=True)
    rs = esegui("storico", n, backtest=True)
    rf = esegui("fattori", n)
    cols = list(NOMI)
    fonti = {"storico A": rs["sim"]["A"], "storico B": rs["sim"]["B"], "fattori": rf["sim"]["A"]}
    h_fin = rs["cfg"]["orizzonte_anni"]
    hh = [5, 10, h_fin]

    def pct(x):
        return f"{x * 100:.1f}%".replace(".", ",")

    def eur(x):
        return f"{x:,.0f}".replace(",", ".")

    def riga(prima_cella, fn):
        return "| " + prima_cella + " | " + " | ".join(fn(c) for c in cols) + " |"

    L = ["| | " + " | ".join(NOMI[c] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for i, (nome, s) in enumerate(fonti.items()):
        L.append(riga(("**Volatilità annua simulata** " if i == 0 else "") + nome, lambda c, s=s: pct(s["vol_sim"][c])))
    for i, (nome, s) in enumerate(fonti.items()):
        L.append(riga(("**Max drawdown mediano a %d anni** " % h_fin if i == 0 else "") + nome, lambda c, s=s: f"{s['orizzonti'][h_fin].loc['Max drawdown mediano', c] * 100:.0f}%".replace("-", "−")))
    for riganame, prefisso in (("Valore mediano", "**Mediana a 5 / 10 / %d anni** " % h_fin), ("5° percentile", "**5° percentile a 5 / 10 / %d anni** " % h_fin)):
        for i, (nome, s) in enumerate(fonti.items()):
            L.append(riga((prefisso if i == 0 else "") + nome, lambda c, s=s, r=riganame: " / ".join(eur(s["orizzonti"][h].loc[r, c]) for h in hh)))
    plaus = []
    for nome, r_, a in (("storico", rs, "A"), ("storico", rs, "B"), ("fattori", rf, "A")):
        df = r_["plausibilita"][a]
        for p in cols:
            x = df.loc[p]
            plaus.append(f"| {nome} {a} | {NOMI[p]} | {pct(x['atteso'])} | {pct(x['simulato'])} | ±{pct(x['tolleranza'])} | {'sì' if x['ok'] else 'NO'} |")
    bt = rs.get("backtest")
    testo = [
        f"# Confronto tra modello «storico» e modello «a fattori» (versione 1.5.1, {__import__('datetime').date.today():%d/%m/%Y})",
        "",
        f"Esempio `configurazioni/esempio_tre_portafogli.yaml` (3 portafogli + MSCI World), dati reali Yahoo, {n:,} simulazioni, {h_fin} anni, capitale 5.000 €,".replace(f"{n:,}", f"{n:,}".replace(",", ".")),
        "rendimento atteso con metodo beta (2% / 4%), stesso seed. Valori in euro. La **volatilità annua** è calcolata dai rendimenti di un mese (×√12), come dalla 1.5.1.",
        f"Storico A: periodo comune dal {rs['periodi']['A'][0]:%d/%m/%Y}; storico B: dal {rs['periodi']['B'][0]:%d/%m/%Y}; fattori: storia dei fattori dal 2000 (residui dei titoli dalle stesse date).",
        "",
        *L,
        "",
        "## Controllo di plausibilità (rendimento medio del primo anno contro il rendimento atteso)",
        "",
        "| modello e analisi | serie | atteso | simulato | tolleranza | coincide |",
        "|---|---|---|---|---|---|",
        *plaus,
        "",
    ]
    if bt is not None:
        t = bt["tabella"]
        testo += [
            f"## Backtest del VaR a 1 giorno ({int(t['giorni'].iloc[0])} giorni di prova dopo la finestra di 2 anni)",
            "",
            "Sforamenti (attesi: 5% dei giorni al 95%, 1% al 99%) e semaforo. «fattori (1.5.0)» = modello precedente; «fattori (ora)» = covarianza e rischio specifico EWMA (lambda "
            + f"{bt['lambda']:.2f}".replace(".", ",")
            + "), code grasse.",
            "",
            "| serie | VaR | attesi | storico | fattori (1.5.0) | fattori (ora) |",
            "|---|---|---|---|---|---|",
        ]
        icone = {"verde": "🟢", "giallo": "🟡", "rosso": "🔴"}
        for (serie, lv), g in t.groupby(["serie", "livello"], sort=False):
            def cella(m, g=g):
                x = g[g["modello"] == m].iloc[0]
                return f"{int(x['sforamenti'])} {icone[x['semaforo']]}"

            attesi = f"{g.iloc[0]['attesi']:.1f}".replace(".", ",")
            testo.append(f"| {NOMI.get(serie, serie)} | {int(round(lv * 100))}% | {attesi} | {cella('storico')} | {cella('fattori (1.5.0)')} | {cella('fattori')} |")
        t.drop(columns=[]).to_csv(os.path.join(uscita, "backtest_var.csv"), index=False, sep=";", decimal=",")
        testo += ["", "Il modello storico è più adatto al rischio di breve termine; il modello a fattori è più informativo per orizzonti lunghi perché include le grandi crisi.", ""]
    open(os.path.join(uscita, "risultati.md"), "w", encoding="utf-8").write("\n".join(testo))
    print("\n".join(testo))
    _ = np


if __name__ == "__main__":
    main()
