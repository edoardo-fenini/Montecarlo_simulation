"""Report: costruisce le sezioni (blocchi di testo, tabelle e grafici) e le scrive in HTML, PDF e CSV.

Le stesse sezioni sono mostrate come schede nell'app Streamlit."""

from __future__ import annotations

import base64
import datetime
import html
import io
import json
import os
import re

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

import report_fattori
import stile
from configurazione import BENCH
from metriche import RIGHE_ORIZZONTE, SINGOLO

SCHEDE = [
    "In una pagina",
    "Sintesi",
    "Risultati per orizzonte",
    "Fan chart",
    "Drawdown",
    "Rischio e correlazioni",
    "Da dove viene il rischio",
    "Stress test",
    "Robustezza",
    "Validazione del modello",
    "Limiti dell'analisi",
]
PALETTE, GRIGIO = stile.PALETTE, stile.GRIGIO
NOME_ANALISI = {"A": "Analisi A – periodo comune", "B": "Analisi B – periodo lungo", "C": "Analisi C – dal 1999 con proxy"}
ROSSO_SOTTO = stile.ROSSO_SOTTO  # zona sotto il capitale investito

# Indicatore di rischio a 5 livelli, in base alla volatilità annua simulata (ispirato alla scala SRI europea).
# colori scuri: il testo bianco sopra resta leggibile (contrasto >= 4,5:1)
LIVELLI_RISCHIO = [
    (0.08, "Basso", "#1B5E20"),
    (0.14, "Medio-basso", "#3F6B12"),
    (0.20, "Medio", "#8A5A00"),
    (0.30, "Alto", "#B23C00"),
    (float("inf"), "Molto alto", "#A31515"),
]


def livello_rischio(vol):
    """(numero 1-5, etichetta, colore) dalla volatilità annua."""
    for i, (soglia, nome, col) in enumerate(LIVELLI_RISCHIO):
        if vol < soglia:
            return i + 1, nome, col
    return 5, LIVELLI_RISCHIO[-1][1], LIVELLI_RISCHIO[-1][2]


def criteri_rischio():
    righe, basso = [], 0.0
    for i, (soglia, nome, _) in enumerate(LIVELLI_RISCHIO):
        intervallo = f"da {pct(basso, 0)} a {pct(soglia, 0)}" if np.isfinite(soglia) else f"da {pct(basso, 0)} in su"
        righe.append([f"{i + 1} – {nome}", intervallo])
        basso = soglia
    return T(["Volatilità annua simulata"], righe, sx=True)


# ------------------------------------------------------------------ formattazione italiana
def num_it(n):
    return f"{n:,}".replace(",", ".")


def eur(v):
    return "–" if v is None or not np.isfinite(v) else f"{v:,.0f} €".replace(",", ".")


def pct(v, d=1):
    """Percentuale in formato italiano, sempre con almeno una cifra decimale (es. 12,3%)."""
    return "–" if v is None or not np.isfinite(v) else f"{v * 100:.{max(d, 1)}f}%".replace(".", ",")


def num(v, d=1):
    return "mai" if not np.isfinite(v) else f"{v:.{d}f}".replace(".", ",")


def esc(s):
    return html.escape(str(s), quote=False)


def colori(ris):
    """Colori fissi dei portafogli (gli stessi in app, report e PDF): vedi stile.py."""
    return stile.colori(ris["nomi"], ris["bench_nome"])


def corto(k, n=22):
    return k if len(k) <= n else k[: n - 1] + "…"


def png(fig):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return b.getvalue()


def _euro_asse(ax):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))


# ------------------------------------------------------------------ grafici
def fan_chart(ris, a):
    s, cfg, col = ris["sim"][a], ris["cfg"], colori(ris)
    nomi, cp = s["nomi"], cfg["orizzonti"]
    nc = 2 if len(nomi) > 1 else 1
    nr = int(np.ceil(len(nomi) / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(11, 3.7 * nr), sharex=True, sharey=True, squeeze=False)
    top = max(s["bande"][k][4][cp[-1] * 12] for k in nomi) * 1.12
    for ax, k in zip(axs.ravel(), nomi):
        b = s["bande"][k]
        x = np.arange(b.shape[1]) / 12
        c = col[k]
        ax.fill_between(x, 0, s["versato"], color=ROSSO_SOTTO, alpha=0.11, lw=0, label="Sotto il capitale investito")
        ax.fill_between(x, b[0], b[4], color=c, alpha=0.15, lw=0, label="5°–95° percentile")
        ax.fill_between(x, b[1], b[3], color=c, alpha=0.30, lw=0, label="25°–75° percentile")
        ax.plot(x, b[2], color=c, lw=2, label="Mediana")
        ax.plot(x, s["versato"], color="black", ls="--", lw=1, label="Totale versato")
        for h in cp:
            j = h * 12
            ax.axvline(h, color="#999", lw=0.8, ls=":")
            for v, dy in ((b[4][j], 5), (b[2][j], 6), (b[0][j], -12)):
                ax.plot([h], [v], "o", color=c, ms=5, mec="white", mew=0.8, zorder=5)
                ax.annotate(
                    eur(v),
                    (h, v),
                    xytext=(-5, dy),
                    textcoords="offset points",
                    ha="right",
                    fontsize=7.5,
                    color="#111",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75),
                    zorder=6,
                )
        ax.set_title(k, color=c, fontweight="bold", fontsize=11)
        ax.set_ylim(0, top)
        ax.grid(alpha=0.25)
        _euro_asse(ax)
    for ax in axs.ravel()[len(nomi) :]:
        ax.axis("off")
    for ax in axs[-1]:
        ax.set_xlabel("anni")
    for ax in axs[:, 0]:
        ax.set_ylabel("valore (€)")
    axs[0, 0].legend(loc="upper left", fontsize=7.5, frameon=False)
    fig.tight_layout()
    return png(fig)


def istogrammi_mdd(ris):
    anal = [a for a in ris["sim"] if a != "C"]
    col, h = colori(ris), ris["cfg"]["orizzonte_anni"]
    fig, axs = plt.subplots(1, len(anal), figsize=(5.5 * len(anal), 3.9), sharey=True, squeeze=False)
    for ax, a in zip(axs[0], anal):
        s = ris["sim"][a]
        idx = stile.indice(s["nomi"], ris["bench_nome"])
        for k in s["nomi"]:
            ax.hist(
                s["mdd_fin"][k] * 100,
                bins=np.linspace(-100, 0, 41),
                alpha=0.35,
                color=col[k],
                density=True,
                hatch=stile.MOTIVI_MPL[idx[k]],
                edgecolor=col[k],
                linewidth=0,
            )
            ax.hist(
                s["mdd_fin"][k] * 100,
                bins=np.linspace(-100, 0, 41),
                histtype="step",
                color=col[k],
                density=True,
                linestyle=stile.TRATTI_MPL[idx[k]],
                linewidth=1.6,
                label=corto(k, 30),
            )
        ax.set_title(f"Analisi {a}: calo massimo nei {h} anni")
        ax.set_xlabel("max drawdown (%)")
        ax.grid(alpha=0.25)
    axs[0, 0].set_ylabel("frequenza")
    axs[0, 0].legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    return png(fig)


def grafico_rischio(ris, a):
    st, col = ris["storico"][a], colori(ris)
    nomi = [k for k in ris["nomi"] if k in st["rc"]]
    if not nomi:
        return None
    nc = min(3, len(nomi))
    nr = int(np.ceil(len(nomi) / nc))
    alt = max(len(st["rc"][k]) for k in nomi)
    fig, axs = plt.subplots(nr, nc, figsize=(11, max(2.6, 0.32 * alt + 1.2) * nr), squeeze=False)
    for ax, k in zip(axs.ravel(), nomi):
        rc = st["rc"][k]
        ax.barh(rc.index[::-1], rc.values[::-1] * 100, color=col[k])
        pesi = list(ris["cfg"]["composizione"][k].values())
        ax.scatter(np.array(pesi[::-1]) * 100, range(len(pesi)), marker="|", s=200, color="black", zorder=5)
        ax.set_title(corto(k, 32), color=col[k], fontsize=10, fontweight="bold")
        ax.set_xlabel("% del rischio totale")
        ax.grid(alpha=0.25, axis="x")
    for ax in axs.ravel()[len(nomi) :]:
        ax.axis("off")
    fig.text(
        0.5,
        -0.02,
        "Barra = quota del rischio del titolo; trattino nero = suo peso nel portafoglio. "
        "Barra più lunga del trattino = il titolo pesa sul rischio più di quanto pesa in euro.",
        ha="center",
        fontsize=8.5,
    )
    fig.tight_layout()
    return png(fig)


def heatmap(ris):
    mats = []
    for a in ris["sim"]:
        if a == "C":
            continue
        mats += [(f"Storica – analisi {a}", ris["storico"][a]["corr"]), (f"Simulata – analisi {a}", ris["sim"][a]["corr_sim"])]
    nomi = ris["nomi"]
    n = len(nomi)
    lato = max(4.2, 0.75 * n + 1.5)
    fig, axs = plt.subplots(len(mats) // 2, 2, figsize=(2 * lato, lato * len(mats) // 2), squeeze=False)
    for ax, (t, m) in zip(axs.ravel(), mats):
        m = m.loc[nomi, nomi]
        ax.imshow(m.values, vmin=0, vmax=1, cmap="Blues")
        ax.set_xticks(range(n))
        ax.set_yticks(range(n))
        ax.set_xticklabels([corto(k, 16) for k in nomi], rotation=30, ha="right", fontsize=8)
        ax.set_yticklabels([corto(k, 16) for k in nomi], fontsize=8)
        for i in range(n):
            for j in range(n):
                v = m.values[i, j]
                ax.text(j, i, f"{v:.2f}".replace(".", ","), ha="center", va="center", fontsize=9, color="white" if v > 0.6 else "black")
        ax.set_title(t, fontsize=10)
    fig.tight_layout()
    return png(fig)


# ------------------------------------------------------------------ blocchi
def T(intest, righe, gruppi=None, sx=False):
    return ("tab", {"intest": intest, "righe": righe, "gruppi": gruppi, "sx": sx})


FMT = {
    "Totale versato": eur,
    "Valore mediano": eur,
    "5° percentile": eur,
    "95° percentile": eur,
    "Prob. sotto il versato": pct,
    "Max drawdown mediano": pct,
    "Max drawdown peggiore (95%)": pct,
    "Tempo sott'acqua max, mediano (anni)": num,
    "Tempo sott'acqua max, peggiore 95% (anni)": num,
}


def tab_orizzonte(ris, h, a):
    """Tabella di un solo orizzonte e una sola analisi (le analisi non sono più affiancate: entrano nella pagina)."""
    nomi = ris["nomi"]
    righe = [[r] + [FMT[r](ris["sim"][a]["orizzonti"][h].loc[r, k]) for k in nomi] for r in RIGHE_ORIZZONTE]
    return T([corto(k) for k in nomi], righe)


def ordine(vals, desc=True):
    return " > ".join(sorted(vals, key=lambda k: vals[k], reverse=desc))


def metriche_rischio(ris, s):
    h = ris["cfg"]["orizzonte_anni"]
    return {
        "ES 95% a 1 anno": {k: s["var_es"].loc["Expected Shortfall 95% 1 anno", k] for k in s["nomi"]},
        f"Max drawdown mediano a {h} anni": {k: -s["orizzonti"][h].loc["Max drawdown mediano", k] for k in s["nomi"]},
        f"Prob. sotto il versato a {h} anni": {k: s["orizzonti"][h].loc["Prob. sotto il versato", k] for k in s["nomi"]},
    }


def testo_metodo(ris):
    cfg = ris["cfg"]
    ra = cfg["rendimento_atteso"]
    m = ra["metodo"]
    drag = (
        " <b>Volatility drag:</b> il rendimento atteso è una <i>media</i> (1 € vale in media 1+r dopo un anno). "
        "Con le oscillazioni il risultato <i>tipico</i> (la mediana) resta più basso della media: una perdita del 50% "
        "richiede un guadagno del 100% per rientrare. Più un portafoglio oscilla, più la sua mediana resta indietro."
    )
    if m == "beta":
        t = (
            f"<b>Metodo del rendimento atteso: beta.</b> Ogni titolo ha rendimento atteso = {pct(ra['tasso_privo_rischio'], 0)} (tasso privo di rischio) "
            f"+ beta × {pct(ra['premio_mercato'], 0)} (premio per il rischio di mercato). Il beta misura quanto il titolo si muove "
            "con il benchmark (beta 1,5 = in media si muove del 50% in più). Il rischio di mercato, che non si può eliminare "
            "diversificando, viene remunerato; il rischio specifico del singolo titolo no, perché si può diversificare. "
            "Le volatilità, le code e le correlazioni restano quelle storiche: cambia solo la media."
        )
    elif m == "uguale":
        t = (
            f"<b>Metodo del rendimento atteso: uguale.</b> Tutti i portafogli hanno lo stesso rendimento medio del "
            f"{pct(ra['valore_uguale'], 0)} annuo: le differenze dipendono solo dal rischio. Volatilità, code e correlazioni restano quelle storiche."
        )
    elif m == "personalizzato":
        t = "<b>Metodo del rendimento atteso: personalizzato.</b> Il rendimento medio annuo di ogni portafoglio è quello indicato nella configurazione."
    else:
        t = (
            "<b>Metodo del rendimento atteso: storico.</b> ATTENZIONE: si usano i rendimenti realmente ottenuti in passato. "
            "Questo proietta il passato nel futuro: se i titoli sono stati scelti oggi perché sono andati bene (survivorship bias), "
            "i risultati saranno troppo ottimistici."
        )
    if ris.get("modello_simulazione") == "fattori":
        t += (
            " <b>Modello di simulazione: a fattori.</b> Ogni titolo è la somma di esposizioni a fattori comuni (mercato, regioni, settori, stile, "
            "tassi e valute, stimati con una regressione ridge sui rendimenti settimanali) e di una parte specifica del titolo. I fattori "
            "sono ricampionati a blocchi dalla loro storia lunga (dal 2000, con le crisi del 2000-2002 e del 2008) e la parte specifica "
            "dalla storia del titolo, in modo indipendente tra titoli."
        )
    return t + drag


def sintesi(ris):
    cfg, n = ris["cfg"], ris["n"]
    a = "A"
    s = ris["sim"][a]
    nomi, bn, H = ris["nomi"], ris["bench_nome"], cfg["orizzonte_anni"]
    st = ris["storico"][a]["stat"]
    F = []
    vers = f" e versando {eur(cfg['versamento_mensile'])} al mese" if cfg["versamento_mensile"] else " senza altri versamenti"
    metodo = {
        "beta": "rendimento atteso legato al rischio di mercato (metodo beta)",
        "uguale": "stesso rendimento atteso per tutti",
        "storico": "rendimenti storici (proiettano il passato nel futuro)",
        "personalizzato": "rendimenti attesi scelti da te",
    }[cfg["rendimento_atteso"]["metodo"]]
    F.append(
        f"Ho simulato {num_it(n)} futuri possibili a {H} anni per {len(nomi)} portafogli, partendo da {eur(cfg['capitale_iniziale'])}{vers}, con {metodo}."
    )
    vol = {k: st[k]["vol"] for k in nomi}
    altri = [k for k in nomi if k != bn]
    if altri:
        top = max(altri, key=vol.get)
        rapp = "; ".join(f"«{k}» {num(vol[k] / vol[bn])} volte" for k in sorted(altri, key=vol.get, reverse=True))
        F.append(
            f"Il portafoglio che oscilla di più è «{top}» (volatilità {pct(vol[top], 0)} l'anno contro {pct(vol[bn], 0)} del benchmark). "
            f"Rispetto al benchmark la volatilità è: {rapp}."
        )
    prob = "; ".join(
        f"«{k}» " + " / ".join(pct(s["orizzonti"][h].loc["Prob. sotto il versato", k], 0) for h in cfg["orizzonti"]) for k in nomi
    )
    F.append(f"Probabilità di avere meno di quanto versato a {' / '.join(str(h) for h in cfg['orizzonti'])} anni: {prob}.")
    dd = {k: s["orizzonti"][H].loc["Max drawdown mediano", k] for k in nomi}
    lo, hi = min(dd, key=dd.get), max(dd, key=dd.get)
    F.append(f"Il calo massimo tipico (mediano) in {H} anni va dal {pct(-dd[hi], 0)} di «{hi}» al {pct(-dd[lo], 0)} di «{lo}».")
    med = "; ".join(f"«{k}» {eur(s['orizzonti'][H].loc['Valore mediano', k])}" for k in nomi)
    F.append(
        f"Valore mediano dopo {H} anni (versati {eur(s['orizzonti'][H].loc['Totale versato', nomi[0]])}): {med}. "
        "La mediana è più bassa del valore medio, e lo è di più per i portafogli che oscillano di più (volatility drag)."
    )
    if a in ris["stress"]:
        d = ris["stress"][a]
        d2 = d[d["Scenario"] != SINGOLO]
        w = d2.loc[d2["Perdita (%)"].idxmax()]
        lenti = sorted(
            {r["Portafoglio"] for _, r in d2.iterrows() if r["Scende sotto il versato"] and r["Prob. di tornarci entro 10 anni"] < 0.5}
        )
        f = f"Negli stress test la perdita più pesante è di «{w['Portafoglio']}» nello scenario «{w['Scenario']}» (−{pct(w['Perdita (%)'], 0)})."
        if lenti:
            f += (
                " In almeno uno scenario non tornerebbero al versato entro 10 anni in più di metà dei casi: "
                + ", ".join(f"«{k}»" for k in lenti)
                + "."
            )
        F.append(f)
    F += conclusioni_stabili(ris, breve=True)
    if ris.get("convergenza"):
        F.append(testo_convergenza(ris))
    F.append("Questa analisi non è consulenza finanziaria e non contiene indicazioni di acquisto o vendita.")
    return F


def conclusioni_stabili(ris, breve=False):
    out = []
    anal = [a for a in ris["sim"] if a != "C"]
    ES = "ES 95% a 1 anno"
    if ris["modelli"]:
        cambi = []
        for a in ris["modelli"]:
            base = ordine(metriche_rischio(ris, ris["sim"][a])[ES])
            for nome, s in ris["modelli"][a].items():
                if ordine(metriche_rischio(ris, s)[ES]) != base:
                    cambi.append(f"{nome} (analisi {a})")
        out.append(
            "La classifica di rischio (perdita media nei casi peggiori a 1 anno) è la stessa con tutti i modelli."
            if not cambi
            else "La classifica di rischio cambia con: " + ", ".join(cambi) + "."
        )
    if len(anal) > 1:
        o = {a: ordine(metriche_rischio(ris, ris["sim"][a])[ES]) for a in anal}
        out.append(
            "Il periodo storico usato (A o B) non cambia la classifica di rischio."
            if len(set(o.values())) == 1
            else "La classifica di rischio dipende dal periodo storico: analisi A " + o["A"] + "; analisi B " + o["B"] + "."
        )
    if ris["idio"]:
        H = ris["cfg"]["orizzonte_anni"]
        dp = max(
            ris["idio"][a]["orizzonti"][H].loc["Prob. sotto il versato", k] - ris["sim"][a]["orizzonti"][H].loc["Prob. sotto il versato", k]
            for a in ris["idio"]
            for k in ris["nomi"]
        )
        out.append(
            f"Il rischio di crollo di un singolo titolo aumenta la probabilità di finire sotto il versato al massimo di {num(dp * 100)} punti percentuali."
        )
    if ris["sensibilita"]:
        H = ris["cfg"]["orizzonte_anni"]
        cambia = False
        for a, var in ris["sensibilita"].items():
            o0 = ordine({k: ris["sim"][a]["orizzonti"][H].loc["Valore mediano", k] for k in ris["nomi"]})
            cambia |= any(ordine({k: s["orizzonti"][H].loc["Valore mediano", k] for k in ris["nomi"]}) != o0 for _, s in var)
        out.append(
            "Cambiando il rendimento atteso la classifica sul valore finale mediano "
            + ("cambia: dipende dalle ipotesi." if cambia else "non cambia.")
        )
    return out


def testo_convergenza(ris):
    """Frase in italiano semplice sull'esito della verifica con seed diversi."""
    c = ris.get("convergenza")
    if not c:
        return None
    sm = c["scarto_mediana"]
    peggiore = sm.idxmax()
    if c["sufficienti"]:
        return (
            f"Le simulazioni bastano: ripetendo il calcolo con {len(c['seed'])} seed diversi la mediana a {c['orizzonte']} anni "
            f"cambia al massimo del ±{num(sm.max() * 100)}% (soglia ±{num(c['soglia'] * 100, 0)}%)."
        )
    return (
        f"Le simulazioni bastano solo in parte: ripetendo il calcolo con {len(c['seed'])} seed diversi la mediana di «{peggiore}» "
        f"cambia fino al ±{num(sm.max() * 100)}% (soglia ±{num(c['soglia'] * 100, 0)}%). Le differenze tra portafogli più grandi di "
        f"qualche punto percentuale restano affidabili; per numeri più stabili aumenta le simulazioni (es. {num_it(2 * c['n'])})."
    )


def sezione_convergenza(ris):
    c = ris.get("convergenza")
    if not c:
        return []
    nomi = list(c["mediana"].columns)
    righe = []
    for k in nomi:
        ok = c["scarto_mediana"][k] <= c["soglia"]
        righe.append(
            [esc(k)]
            + [eur(c["mediana"].loc[sd, k]) for sd in c["seed"]]
            + [f"±{num(c['scarto_mediana'][k] * 100)}%", f"±{num(c['scarto_p5'][k] * 100)}%", "sì" if ok else "<b>no</b>"]
        )
    return [
        ("h3", "Le simulazioni bastano?"),
        (
            "nota",
            f"Ho ripetuto la simulazione principale (analisi A) con {len(c['seed'])} seed diversi, cioè con altre estrazioni casuali, "
            f"usando {num_it(c['n'])} simulazioni ciascuna. Se i risultati cambiano poco, il numero di simulazioni è sufficiente. "
            f"Soglia indicativa: mediana entro ±{num(c['soglia'] * 100, 0)}% tra i seed. Il 5° percentile (i casi peggiori) è "
            "per natura più instabile, perché si basa su pochi percorsi.",
        ),
        T([f"Mediana, seed {sd}" for sd in c["seed"]] + ["Scarto max mediana", "Scarto max 5° perc.", "Entro la soglia?"], righe),
        ("box", [testo_convergenza(ris)]),
    ]


# ------------------------------------------------------------------ spiegazioni automatiche dei grafici
def didascalia_fan(ris, a):
    s, H = ris["sim"][a], ris["cfg"]["orizzonte_anni"]
    j = H * 12
    larg = {k: (s["bande"][k][4][j] - s["bande"][k][0][j]) / max(s["bande"][k][2][j], 1e-9) for k in s["nomi"]}
    sotto = {k: s["orizzonti"][H].loc["Prob. sotto il versato", k] for k in s["nomi"]}
    piu, meno, rischio = max(larg, key=larg.get), min(larg, key=larg.get), max(sotto, key=sotto.get)
    return (
        f"La fascia di «{piu}» è la più larga: i risultati possibili sono i più dispersi; quella di «{meno}» è la più stretta. "
        f"La zona rossa è sotto il capitale investito: a {H} anni «{rischio}» ci finisce più spesso ({pct(sotto[rischio])} dei casi)."
    )


def didascalia_mdd(ris):
    s, H = ris["sim"]["A"], ris["cfg"]["orizzonte_anni"]
    dd = {k: s["orizzonti"][H].loc["Max drawdown mediano", k] for k in s["nomi"]}
    lo, hi = min(dd, key=dd.get), max(dd, key=dd.get)
    return (
        f"Più una distribuzione sta a sinistra, più i cali sono profondi. Nel caso tipico «{lo}» attraversa il calo più profondo "
        f"({pct(dd[lo])}), «{hi}» il più contenuto ({pct(dd[hi])})."
    )


def didascalia_rischio(ris, a):
    st, comp, frasi = ris["storico"][a], ris["cfg"]["composizione"], []
    for k, rc in st["rc"].items():
        pesi = np.array(list(comp[k].values()))
        rapp = rc.values / pesi
        i = int(np.argmax(rapp))
        if rapp[i] > 1.15:
            frasi.append(f"in «{k}» {rc.index[i]} pesa il {pct(pesi[i])} ma porta il {pct(rc.values[i])} del rischio")
    if not frasi:
        return "In ogni portafoglio il rischio è distribuito in modo simile ai pesi: nessun titolo domina."
    return "Titoli che pesano sul rischio più di quanto pesano in euro: " + "; ".join(frasi) + "."


def didascalia_corr(ris):
    c = ris["storico"]["A"]["corr"].loc[ris["nomi"], ris["nomi"]]
    coppie = [(c.iloc[i, j], c.index[i], c.columns[j]) for i in range(len(c)) for j in range(i + 1, len(c))]
    if not coppie:
        return ""
    alta, bassa = max(coppie), min(coppie)
    return (
        f"I portafogli più legati sono «{alta[1]}» e «{alta[2]}» (correlazione {num(alta[0], 2)}); i meno legati «{bassa[1]}» e "
        f"«{bassa[2]}» ({num(bassa[0], 2)}). Unire portafogli poco correlati riduce le oscillazioni complessive."
    )


def dati_schede(ris: dict, a: str = "A") -> list[dict]:
    """Numeri chiave per portafoglio (usati da «In una pagina» nel report e dalle card dell'app)."""
    s, H, bn = ris["sim"][a], ris["cfg"]["orizzonte_anni"], ris["bench_nome"]
    out = []
    for k in s["nomi"]:
        vol = s["vol_sim"][k]
        liv = livello_rischio(vol)
        o = s["orizzonti"][H]
        out.append(
            {
                "nome": k,
                "colore": colori(ris)[k],
                "valore_mediano": o.loc["Valore mediano", k],
                "versato": o.loc["Totale versato", k],
                "prob_perdita": o.loc["Prob. sotto il versato", k],
                "mdd": o.loc["Max drawdown mediano", k],
                "vol": vol,
                "vol_vs_bench": vol / s["vol_sim"][bn],
                "livello": liv[0],
                "livello_nome": liv[1],
                "livello_colore": liv[2],
                "benchmark": k == bn,
            }
        )
    return out


def sezione_una_pagina(ris):
    H = ris["cfg"]["orizzonte_anni"]
    B = [
        (
            "nota",
            f"I numeri chiave di ogni portafoglio a {H} anni (analisi A, {num_it(ris['n'])} simulazioni). "
            "Il livello di rischio va da 1 (basso) a 5 (molto alto) ed è indicato con numero, nome e quadratini, non solo con il colore.",
        ),
        ("schede", {"orizzonte": H, "schede": dati_schede(ris)}),
        ("h3", "Come si legge il livello di rischio"),
        (
            "nota",
            "Il livello dipende dalla volatilità annua simulata, cioè da quanto oscilla il valore in un anno. Le soglie sono "
            "ispirate alla scala di rischio (SRI) usata nei documenti europei dei prodotti finanziari, ridotta a 5 livelli. "
            "Se la volatilità è vicina a una soglia (es. 14,0%), il livello può cambiare di uno tra un calcolo e l'altro.",
        ),
        criteri_rischio(),
    ]
    return B


COLORE_ESITO = {"VERDE": "#1B5E20", "GIALLO": "#8A5A00", "ROSSO": "#A31515"}


def blocco_controllo_dati(ris: dict) -> list:
    """Tabella «Controllo dati» (semaforo per titolo) calcolata prima della simulazione. Vuota se il controllo non è stato eseguito."""
    c = ris.get("controllo")
    if not c:
        return []
    t = c["tabella_senza_emoji"]
    righe = []
    for _, x in t.iterrows():
        esito = x["Esito"].upper()
        righe.append(
            [
                esc(x["Input"]),
                f'<font color="{COLORE_ESITO[esito]}"><b>{esito}</b></font>',
                esc(x["Ticker usato"]),
                esc(corto(x["Nome"], 26)),
                esc(f"{x['Borsa']} ({x['Valuta']})" if x["Valuta"] else x["Borsa"]),
                esc(x["Fonte"]),
                x["Prima data"],
                x["Ultima data"],
                x["Anni di storia"],
                x["% giorni mancanti"],
                esc(x["Ultimo prezzo"].split(" del ")[0]),
            ]
        )
    B = [
        ("h3", "Controllo dei dati prima della simulazione"),
        (
            "p",
            f"<b>{esc(c['riepilogo'])}.</b> La prima colonna è ciò che hai scritto (ticker o ISIN). Semaforo: <b>verde</b> = tutto a posto; <b>giallo</b> = avviso, si può procedere; <b>rosso</b> = errore che blocca la simulazione.",
        ),
        T(
            [
                "Esito",
                "Ticker usato",
                "Nome",
                "Borsa (valuta)",
                "Fonte",
                "Prima data",
                "Ultima data",
                "Anni",
                "% giorni mancanti",
                "Ultimo prezzo",
            ],
            righe,
            sx=True,
        ),
    ]
    note = [f"<b>{esc(x['Input'])}</b>: {esc(x['Dettagli'])}" for _, x in t.iterrows() if x["Dettagli"] != "tutto a posto"]
    if note:
        B.append(("box", note))
    return B


def blocchi_costi(ris: dict) -> list:
    """Tabella dei costi usati per ogni titolo e effetto dei costi sul rendimento atteso di ogni portafoglio (solo con la ricentratura)."""
    cfg, ra, costi = ris["cfg"], ris["rend_attesi"], ris.get("costi")
    if costi is None or not len(costi):
        return []
    orig = {"indicato": "indicato da te", "default": "default prudente (non indicato)", "benchmark": "TER del benchmark", "azione": "azione: nessun costo"}
    righe = [[esc(c["Titolo"]), esc(c["Nome"] or "–"), c["Tipo"], pct(c["Costo annuo"], 2), orig.get(c["Origine"], c["Origine"])] for _, c in costi.iterrows()]
    B = [("h3", "Costi annui usati"), T(["Nome", "Tipo", "Costo annuo", "Origine"], righe)]
    eff = [
        [k, pct(ra.loc["Rendimento atteso annuo", k]), pct(-ra.loc["di cui costi ETF (TER)", k], 2), pct(ra.loc["Rendimento atteso annuo", k] - ra.loc["di cui costi ETF (TER)", k])]
        for k in ris["nomi"]
    ]
    B.append(T(["Rendimento atteso prima dei costi", "Effetto dei costi", "Rendimento atteso dopo i costi"], eff))
    B.append(
        (
            "nota",
            "I costi di fondi ed ETF riducono il rendimento atteso: con la ricentratura il rendimento storico viene sostituito, quindi i costi già "
            "inclusi nel prezzo non contano più e si sottraggono qui. Dove il costo non è indicato si usa un default prudente "
            f"(fondi comuni {pct(cfg['costo_fondo_default'], 2)}, ETF/ETC {pct(cfg['ter_etf_default'], 2)}). Il benchmark usa il suo TER, una volta sola.",
        )
    )
    return B


def sezioni(ris: dict) -> dict[str, list]:
    """Ritorna {scheda: [blocchi]}."""
    cfg, n, nomi = ris["cfg"], ris["n"], ris["nomi"]
    anal = [a for a in ris["sim"] if a != "C"]
    H = cfg["orizzonte_anni"]
    S = {k: [] for k in SCHEDE}
    S["In una pagina"] = sezione_una_pagina(ris)
    d = lambda t: t.strftime("%d/%m/%Y")

    # ---- Sintesi
    B = S["Sintesi"]
    if n < 5000:
        B.append(("warn", f"<b>Prova rapida:</b> solo {num_it(n)} simulazioni. I numeri sono indicativi."))
    B.append(("box", sintesi(ris)))
    B.append(("warn", testo_metodo(ris)))
    ra = ris["rend_attesi"]
    righe = [
        [
            k,
            num(ra.loc["Beta verso il benchmark", k], 2),
            pct(ra.loc["Rendimento atteso annuo", k]) if cfg["rendimento_atteso"]["metodo"] != "storico" else "storico",
            pct(ra.loc["di cui costi ETF (TER)", k], 2),
        ]
        for k in nomi
    ]
    B.append(("h3", "Rendimento atteso usato"))
    B.append(T(["Beta", "Rendimento atteso annuo", "Costi sottratti (fondi, ETF)"], righe))
    if cfg["rendimento_atteso"]["metodo"] != "storico":
        B.append(
            (
                "nota",
                f"Il costo annuo (TER) è sottratto al benchmark ({pct(cfg['benchmark']['ter'], 2)}) e agli ETF usati come titoli "
                f"(valore indicato in configurazione o, se non indicato, {pct(cfg['ter_etf_default'], 2)}). Le azioni non hanno TER.",
            )
        )
        B += blocchi_costi(ris)
    B.append(("h3", "Come leggere i termini"))
    B.append(
        (
            "box",
            [
                "<b>Percentile</b>: il 5° percentile è il valore sotto cui finisce il 5% dei casi peggiori; il 95° quello sopra cui sta il 5% dei migliori.",
                "<b>Volatilità</b>: quanto oscillano i prezzi in un anno. 30% = oscillazioni tipiche di ±30%.",
                "<b>Max drawdown</b>: il calo massimo da un massimo al minimo successivo (da 10.000 a 4.000 € = −60%).",
                "<b>Tempo sott'acqua</b>: il periodo più lungo passato sotto il massimo precedente.",
                "<b>VaR 95% a 1 anno</b>: la perdita superata solo nel 5% dei casi in un anno. <b>Expected Shortfall (ES)</b>: la perdita media in quel 5% di casi peggiori.",
                "<b>Volatility drag</b>: con le oscillazioni il risultato tipico resta sotto la media; più oscillazioni, più distacco.",
                "<b>Bootstrap a blocchi</b>: si rimescolano pezzi di storia reale (circa 20 giorni di borsa ciascuno), così restano crisi, code e correlazioni.",
                f"<b>Ribilanciamento ({cfg['ribilanciamento']})</b>: si riportano i titoli ai pesi scelti pagando il {pct(cfg['costo_ribilanciamento'], 1)} dell'importo movimentato.",
            ],
        )
    )
    B += blocco_controllo_dati(ris)
    B.append(("h3", "Dati e periodi analizzati"))
    crisi = [
        ("bolla dot-com 2000-2002", "2000-03-10", "2002-10-09"),
        ("crisi finanziaria 2008", "2007-10-09", "2009-03-09"),
        ("debito europeo 2011", "2011-05-01", "2011-10-04"),
        ("Covid 2020", "2020-02-19", "2020-03-23"),
        ("ribasso 2022", "2022-01-03", "2022-10-12"),
        ("crisi bancaria 2023", "2023-03-08", "2023-03-20"),
    ]
    desc = {
        "A": "Periodo comune (tutti i titoli quotati)",
        "B": "Periodo lungo (titoli disponibili a ogni data, pesi ridistribuiti)",
        "C": "Dal 1999 con proxy di settore per i titoli non ancora quotati",
    }
    righe = []
    for a, (i0, i1, ng) in ris["periodi"].items():
        dentro = [c for c, x, y in crisi if pd.Timestamp(x) >= i0 and pd.Timestamp(y) <= i1]
        righe.append([a, desc[a], f"{d(i0)} – {d(i1)}", num_it(ng), ", ".join(dentro) or "nessuna grande crisi"])
    B.append(T(["Descrizione", "Periodo", "Giorni", "Crisi incluse"], righe, sx=True))
    if "B" in ris["note"]:
        B.append(("nota", ris["note"]["B"]))
    b = cfg["benchmark"]
    B.append(
        (
            "nota",
            f"Prezzi Yahoo Finance (adjusted close, dividendi inclusi) aggiornati al {d(ris['ultimo_dato'])}, convertiti in EUR con il cambio giornaliero "
            f"(il rischio di cambio è incluso). Benchmark: {esc(b.get('descrizione') or b['nome'])} ({b['ticker']}{', ISIN ' + b['isin'] if b.get('isin') else ''}, TER {pct(b['ter'], 2)}); "
            f"prima della nascita dell'ETF uso l'indice {b.get('proxy_storico') or '–'} convertito in EUR meno il TER (proxy).",
        )
    )
    if "B" in ris["sim"]:
        B.append(
            (
                "nota",
                "Analisi B: quando un titolo non era ancora quotato, il suo peso è ridistribuito tra i titoli già disponibili dello stesso portafoglio.",
            )
        )
    info = ris["dati_info"]
    righe = []
    for t, r in info.iterrows():
        tt = BENCH if t == b["ticker"] else t
        pi = (ris["proxy_info"] or {}).get(tt, {})
        righe.append(
            [
                t,
                esc(r.get("isin", "") or ""),
                esc(corto(r["nome"] or "", 30)),
                esc(r.get("borsa", "") or ""),
                r["valuta"] or "",
                r["tipo"],
                d(pd.Timestamp(r["primo dato"])),
                d(pd.Timestamp(r["ultimo dato"])) if r.get("ultimo dato") else "",
                num(r["anni di storia"]),
                num(ris["beta"].get(tt, np.nan), 2),
                pi.get("categoria", "–"),
                esc(r.get("fonte", "") or ""),
            ]
        )
    B.append(
        (
            "dettagli",
            "Titoli usati (ISIN, ticker, borsa, valuta, storia, beta, settore, fonte dei dati)",
            [
                T(
                    ["ISIN", "Nome", "Borsa", "Valuta", "Tipo", "Primo dato", "Ultimo dato", "Anni", "Beta", "Settore stress", "Fonte"],
                    righe,
                    sx=True,
                )
            ],
        )
    )
    if ris["avvisi"]:
        B.append(("warn", "<b>Avvisi sui dati:</b><br/>" + "<br/>".join(esc(x) for x in ris["avvisi"])))
    if ris.get("avvisi_modelli"):
        dove = ", ".join(dict.fromkeys(x.split(":", 1)[0] for x in ris["avvisi_modelli"]))
        B.append(
            (
                "warn",
                f"<b>Avviso sui modelli ({esc(dove)}):</b> la stima GARCH non converge per alcuni titoli; nel confronto tra modelli per loro "
                "si usa una volatilità costante. I risultati principali non cambiano (dettagli in «Robustezza»).",
            )
        )
    if ris["estremi"]:
        B.append(
            (
                "dettagli",
                f"Movimenti giornalieri estremi (oltre ±30%): {len(ris['estremi'])}",
                [
                    ("lista", [esc(x) for x in ris["estremi"]]),
                    (
                        "nota",
                        "Di solito sono eventi reali (risultati trimestrali, crisi). "
                        "Se vedi un −50% seguito da un +100%, potrebbe essere uno split non corretto da Yahoo.",
                    ),
                ],
            )
        )

    # ---- Risultati per orizzonte
    B = S["Risultati per orizzonte"]
    B.append(
        (
            "nota",
            "Analisi A: periodo comune a tutti i titoli. "
            + ("Analisi B: periodo lungo. " if "B" in anal else "")
            + "Max drawdown e tempo sott'acqua sono calcolati dall'inizio fino a quell'anno.",
        )
    )
    for h in cfg["orizzonti"]:
        B.append(("h3", f"Dopo {h} anni"))
        for a in anal:
            B.append(("sottotitolo", NOME_ANALISI[a]))
            B.append(tab_orizzonte(ris, h, a))

    # ---- Fan chart
    B = S["Fan chart"]
    B.append(
        (
            "nota",
            "Fascia scura = 50% dei casi, fascia chiara = 90%. I puntini segnano 5°, 50° e 95° percentile agli orizzonti scelti; la linea tratteggiata è il totale versato.",
        )
    )
    for a in anal:
        B.append(("h3", NOME_ANALISI[a]))
        B.append(("img", fan_chart(ris, a)))
        B.append(("didascalia", didascalia_fan(ris, a)))

    # ---- Drawdown
    B = S["Drawdown"]
    B.append(
        (
            "nota",
            "Distribuzione del calo massimo (max drawdown) che ogni portafoglio attraversa nell'intero orizzonte: più la curva sta a sinistra, più sono frequenti cali profondi.",
        )
    )
    B.append(("img", istogrammi_mdd(ris)))
    B.append(("didascalia", didascalia_mdd(ris)))
    for a in anal:
        righe = []
        for r in [
            "Max drawdown mediano",
            "Max drawdown peggiore (95%)",
            "Tempo sott'acqua max, mediano (anni)",
            "Tempo sott'acqua max, peggiore 95% (anni)",
        ]:
            righe.append([r] + [FMT[r](ris["sim"][a]["orizzonti"][H].loc[r, k]) for k in nomi])
        B.append(("sottotitolo", f"{NOME_ANALISI[a]} – a {H} anni"))
        B.append(T([corto(k) for k in nomi], righe))

    # ---- Rischio e correlazioni
    B = S["Rischio e correlazioni"]
    metriche_tab = (
        ("Volatilità annua storica", lambda a, k: pct(ris["storico"][a]["stat"][k]["vol"])),
        ("Volatilità annua simulata", lambda a, k: pct(ris["sim"][a]["vol_sim"][k])),
        ("Max drawdown storico", lambda a, k: pct(ris["storico"][a]["stat"][k]["mdd"])),
        ("VaR 95% a 1 anno", lambda a, k: pct(ris["sim"][a]["var_es"].loc["VaR 95% 1 anno", k])),
        ("Expected Shortfall 95% a 1 anno", lambda a, k: pct(ris["sim"][a]["var_es"].loc["Expected Shortfall 95% 1 anno", k])),
        (
            "Correlazione media tra i titoli",
            lambda a, k: num(ris["storico"][a]["corr_media"][k], 2) if k in ris["storico"][a]["corr_media"] else "–",
        ),
    )
    for a in anal:
        B.append(("sottotitolo", NOME_ANALISI[a]))
        B.append(T([corto(k) for k in nomi], [[et] + [f(a, k) for k in nomi] for et, f in metriche_tab]))
    g = grafico_rischio(ris, "A")
    if g:
        B.append(("h3", "Da dove arriva il rischio dentro ogni portafoglio (analisi A)"))
        B.append(("img", g))
        B.append(("didascalia", didascalia_rischio(ris, "A")))
    B.append(("h3", "Correlazione tra i portafogli"))
    B.append(("nota", "1 = si muovono sempre insieme; 0 = indipendenti."))
    B.append(("img", heatmap(ris)))
    B.append(("didascalia", didascalia_corr(ris)))

    # ---- Da dove viene il rischio (modello a fattori; si calcola dalle regressioni, anche senza simulare con i fattori)
    S["Da dove viene il rischio"] = report_fattori.blocchi(ris)

    S["Validazione del modello"] = report_fattori.blocchi_backtest(ris)

    # ---- Stress test
    B = S["Stress test"]
    if ris["stress"]:
        B.append(
            (
                "nota",
                f"Lo shock colpisce il valore mediano simulato a metà orizzonte ({num(H / 2)} anni). Ogni titolo perde in base al suo settore "
                "(tech, finanza, altro/mercato); un portafoglio perde la media pesata. «Anni per tornare al versato» viene da una nuova "
                "simulazione dopo lo shock (mediana), con lo stesso rendimento atteso: è un'ipotesi ottimistica dopo una crisi. "
                "«Il titolo più pesante perde il 90%» non si applica agli ETF.",
            )
        )
        sc = [("tech", "finanza", "altro")]
        from metriche import SCENARI

        B.append(T(["Tech", "Finanza", "Altro / mercato"], [[k] + [pct(v[c], 0) for c in sc[0]] for k, v in SCENARI.items()]))
        for a, df in ris["stress"].items():
            B.append(("h3", f"Analisi {a}"))
            righe = []
            for _, r in df.iterrows():
                if not r["Scende sotto il versato"]:
                    rec = "resta sopra il versato"
                elif not np.isfinite(r["Anni per tornare al versato (mediana)"]):
                    rec = "oltre 30 anni"
                else:
                    rec = num(r["Anni per tornare al versato (mediana)"])
                righe.append(
                    [
                        esc(r["Portafoglio"]),
                        r["Scenario"],
                        eur(r["Valore prima dello shock"]),
                        eur(r["Valore dopo lo shock"]),
                        f"{eur(r['Perdita (€)'])} ({pct(r['Perdita (%)'], 0)})",
                        rec,
                        "–" if not r["Scende sotto il versato"] else pct(r["Prob. di tornarci entro 10 anni"], 0),
                    ]
                )
            B.append(
                T(
                    [
                        "Scenario",
                        "Valore prima",
                        "Valore dopo",
                        "Perdita",
                        f"Anni per tornare a {eur(df['Totale versato'].iloc[0])}",
                        "Prob. entro 10 anni",
                    ],
                    righe,
                    sx=True,
                )
            )
    else:
        B.append(("p", "Modulo stress test non attivato."))

    # ---- Robustezza
    B = S["Robustezza"]
    if ris["modelli"]:
        B.append(("h3", "Confronto tra modelli"))
        B.append(
            (
                "nota",
                "Student-t: code grasse, nessun raggruppamento della volatilità. GARCH(1,1): volatilità che sale e scende nel tempo. "
                "Classifica = dal portafoglio più rischioso al meno rischioso.",
            )
        )
        if ris.get("avvisi_modelli"):  # GARCH non convergente: ripiego sulla volatilità costante, mai in silenzio
            B.append(("warn", "<b>Avviso sul modello GARCH:</b><br/>" + "<br/>".join(esc(x) for x in ris["avvisi_modelli"])))
        for a in ris["modelli"]:
            righe = []
            mod = [("Block bootstrap", ris["sim"][a])] + list(ris["modelli"][a].items())
            rif = {m: ordine(v) for m, v in metriche_rischio(ris, ris["sim"][a]).items()}
            for m in rif:
                for nome, s in mod:
                    o = ordine(metriche_rischio(ris, s)[m])
                    righe.append([m, nome, esc(o), "sì" if o == rif[m] else "<b>NO</b>"])
            B.append(("sottotitolo", NOME_ANALISI[a]))
            B.append(T(["Modello", "Classifica (dal più rischioso)", "Uguale al bootstrap?"], righe, sx=True))
    if ris["sensibilita"]:
        B.append(("h3", "Sensibilità al rendimento atteso"))
        for a, var in ris["sensibilita"].items():
            righe = []
            for et, s in [("scelta di base", ris["sim"][a])] + var:
                vals = {k: s["orizzonti"][H].loc["Valore mediano", k] for k in nomi}
                righe.append([et] + [eur(vals[k]) for k in nomi] + [esc(ordine(vals))])
            B.append(("sottotitolo", f"{NOME_ANALISI[a]} – valore mediano a {H} anni"))
            B.append(T([corto(k) for k in nomi] + ["Classifica (dal più alto)"], righe))
    if ris["idio"]:
        rs = cfg["rischio_singolo_titolo"]
        B.append(("h3", "Rischio sul singolo titolo"))
        B.append(
            (
                "nota",
                f"Ogni azione ha una probabilità del {pct(rs['probabilita_annua'])} l'anno di crollare dell'{pct(rs['perdita_min'], 0)}–{pct(rs['perdita_max'], 0)} "
                "in un giorno (fallimento, frode). Il rendimento medio resta uguale: cambia solo il rischio. Gli ETF non sono toccati.",
            )
        )
        for a in ris["idio"]:
            righe = []
            for r in ["Prob. sotto il versato", "Max drawdown mediano", "Max drawdown peggiore (95%)", "5° percentile"]:
                righe.append([r + " – senza crolli"] + [FMT[r](ris["sim"][a]["orizzonti"][H].loc[r, k]) for k in nomi])
                righe.append([r + " – con crolli"] + [FMT[r](ris["idio"][a]["orizzonti"][H].loc[r, k]) for k in nomi])
            B.append(("sottotitolo", f"{NOME_ANALISI[a]} – a {H} anni"))
            B.append(T([corto(k) for k in nomi], righe))
    if "C" in ris["sim"]:
        B.append(("h3", "Storia allungata dal 1999 con proxy (analisi C)"))
        frac = ris["note"].get("C_proxy", {})
        pi = ris["proxy_info"] or {}
        sint = [f"{t} {pct(v, 0)} (proxy {pi.get(t, {}).get('proxy', '–')})" for t, v in frac.items() if v > 0.005 and t != BENCH]
        B.append(
            (
                "warn",
                "<b>Dati reali e dati proxy.</b> Per i giorni in cui un titolo non esisteva ho generato rendimenti sintetici: beta × rendimento del proxy "
                "di settore + residui ripescati da quelli reali del titolo (stessa volatilità e correlazione misurate quando il titolo esisteva). "
                "Non sono dati veri. Quota di giorni sintetici: " + (", ".join(sint) or "nessuno") + ".",
            )
        )
        for h in cfg["orizzonti"]:
            B.append(("sottotitolo", f"Dopo {h} anni – analisi C"))
            B.append(tab_orizzonte(ris, h, "C"))
        B.append(("img", fan_chart(ris, "C")))
        B.append(("didascalia", didascalia_fan(ris, "C")))
    if B:
        B.insert(
            0,
            (
                "box",
                conclusioni_stabili(ris)
                + [
                    "Il <b>livello</b> dei numeri dipende sempre dalle ipotesi (rendimento atteso, periodo storico); "
                    "le <b>differenze di rischio</b> tra portafogli sono più solide."
                ],
            ),
        )
        B.insert(0, ("h3", "Quanto sono solide queste conclusioni?"))
    else:
        B.append(("p", "Nessun modulo di robustezza attivato (confronto tra modelli, analisi C)."))
        if ris["idio"] or len(anal) > 1:
            B.append(("box", conclusioni_stabili(ris)))
    B[:0] = sezione_convergenza(ris)

    # ---- Limiti
    S["Limiti dell'analisi"] = [
        (
            "box",
            [
                "<b>Storia breve</b>: i titoli quotati da pochi anni hanno pochi dati; il periodo comune (A) può non contenere grandi crisi.",
                "<b>Rendimento atteso</b>: è un'ipotesi, non una previsione. Cambiandolo cambiano i valori finali.",
                "<b>Survivorship bias</b>: chi sceglie oggi titoli che sono andati bene nel passato rischia di sopravvalutarli; le società fallite non compaiono nei dati.",
                "<b>Concentrazione</b>: pochi titoli dello stesso settore possono essere colpiti tutti insieme da un singolo evento.",
                "<b>Il futuro può essere diverso dal passato</b>: il modello rimescola eventi già avvenuti e non può inventare crisi di tipo nuovo.",
                "<b>Costi e tasse</b>: inclusi solo il TER del benchmark e il costo di ribilanciamento; niente imposte, spread o commissioni.",
                "<b>Dati</b>: Yahoo Finance può contenere errori; prima della nascita dell'ETF il benchmark è un indice (proxy).",
            ],
        ),
        ("p", "<b>Questa analisi non è consulenza finanziaria</b> e non contiene raccomandazioni di acquisto o vendita."),
    ]
    return S


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#fff;--fg:#1c1c1c;--mut:#5f6368;--line:#dcdfe3;--card:#f5f6f8;--warn:#fff4e5;--warnb:#e8a33d;--accento:#1F3A5F}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15181d;--fg:#e8e8e8;--mut:#9aa0a6;--line:#363a40;--card:#1f2329;--warn:#33291a;--warnb:#c58a2b;--accento:#8fb3e0}}
.rep{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
body.rep{max-width:1100px;margin:0 auto;padding:16px 20px}
.rep h1{font-size:1.9rem;margin:.2rem 0}.rep h2{margin-top:2.6rem;border-bottom:2px solid var(--accento);padding-bottom:4px;color:var(--accento)}
.rep h3{margin-top:1.6rem}.rep h4.sottotitolo{margin:1rem 0 .2rem;font-size:.95rem;color:var(--mut);font-weight:600}
.rep table{border-collapse:collapse;margin:8px 0 14px;font-size:.86rem;width:100%}.rep td,.rep th{border:1px solid var(--line);padding:5px 8px;text-align:right}
.rep th{background:var(--card)}.rep th.g{text-align:center}.rep td.e{text-align:left;font-weight:600;background:var(--card)}.rep table.sx td{text-align:left}
.rep .sc{overflow-x:auto}.rep img{max-width:100%;height:auto;background:#fff;border-radius:6px}.rep .box{background:var(--card);padding:10px 16px;border-radius:8px}
.rep .warn{background:var(--warn);border-left:5px solid var(--warnb);padding:10px 16px;border-radius:6px;margin:12px 0}
.rep .nota{color:var(--mut);font-size:.9rem}.rep .didascalia{color:var(--mut);font-size:.9rem;font-style:italic;margin:.2rem 0 1rem;border-left:3px solid var(--line);padding-left:10px}
.rep details{margin:8px 0}.rep summary{cursor:pointer;font-weight:600}
.rep .copertina{border:1px solid var(--line);border-radius:12px;padding:22px 26px;margin:8px 0 18px;background:var(--card)}
.rep .copertina .sotto{color:var(--mut);margin:.2rem 0 .8rem}.rep .chip{display:inline-block;margin:3px 8px 3px 0;padding:2px 10px;border-radius:12px;border:1px solid var(--line);font-size:.88rem}
.rep .chip i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.rep nav.indice ol{columns:2;margin:.4rem 0}.rep nav.indice a{color:var(--accento);text-decoration:none}.rep nav.indice a:hover{text-decoration:underline}
.rep .schede{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin:12px 0}
.rep .scheda{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--bg)}
.rep .scheda .nome{font-weight:700;font-size:1.02rem;margin-bottom:6px}.rep .scheda dl{margin:8px 0 0;display:grid;grid-template-columns:1fr auto;gap:2px 8px;font-size:.88rem}
.rep .scheda dt{color:var(--mut)}.rep .scheda dd{margin:0;text-align:right;font-weight:600}
.rep .badge{display:inline-block;color:#fff;border-radius:6px;padding:2px 8px;font-size:.82rem;font-weight:600}.rep .quadri{letter-spacing:2px;margin-left:6px}
"""


# Nell'app: colori neutri (trasparenze) che vanno bene sia con il tema chiaro sia con quello scuro
CSS_APP = """
.rep{color:inherit;font:inherit}.rep table{border-collapse:collapse;margin:6px 0 12px;font-size:.88rem;width:100%}
.rep td,.rep th{border:1px solid rgba(128,128,128,.32);padding:5px 8px;text-align:right}
.rep th{background:rgba(128,128,128,.12)}.rep td.e{text-align:left;font-weight:600;background:rgba(128,128,128,.07)}
.rep table.sx td{text-align:left}.rep .sc{overflow-x:auto}
"""


def quadratini(n):
    return "■" * n + "□" * (5 - n)


def _html_tab(t):
    h = f'<div class="sc"><table class="{"sx" if t["sx"] else ""}">'
    if t["gruppi"]:
        h += "<tr><th></th>" + "".join(f'<th colspan="{n}" class="g">{esc(g)}</th>' for g, n in t["gruppi"]) + "</tr>"
    h += "<tr><th></th>" + "".join(f"<th>{esc(c)}</th>" for c in t["intest"]) + "</tr>"
    for r in t["righe"]:
        h += f'<tr><td class="e">{r[0]}</td>' + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>"
    return h + "</table></div>"


def html_schede(d):
    h = '<div class="schede">'
    for s in d["schede"]:
        h += (
            f'<div class="scheda" style="border-top:5px solid {s["colore"]}"><div class="nome">{esc(s["nome"])}</div>'
            f'<span class="badge" style="background:{s["livello_colore"]}">Rischio {s["livello"]}/5 · {s["livello_nome"]}</span>'
            f'<span class="quadri" aria-hidden="true">{quadratini(s["livello"])}</span><dl>'
            f"<dt>Valore mediano a {d['orizzonte']} anni</dt><dd>{eur(s['valore_mediano'])}</dd>"
            f"<dt>Totale versato</dt><dd>{eur(s['versato'])}</dd>"
            f"<dt>Probabilità di perdita</dt><dd>{pct(s['prob_perdita'])}</dd>"
            f"<dt>Calo massimo tipico</dt><dd>{pct(s['mdd'])}</dd>"
            f"<dt>Volatilità annua</dt><dd>{pct(s['vol'])}</dd>"
            f"<dt>Volatilità vs benchmark</dt><dd>{'—' if s['benchmark'] else num(s['vol_vs_bench']) + ' volte'}</dd></dl></div>"
        )
    return h + "</div>"


def html_blocchi(blocchi):
    out = []
    for b in blocchi:
        k = b[0]
        if k in ("h2", "h3"):
            out.append(f"<{k}>{esc(b[1])}</{k}>")
        elif k == "sottotitolo":
            out.append(f"<h4 class='sottotitolo'>{esc(b[1])}</h4>")
        elif k == "p":
            out.append(f"<p>{b[1]}</p>")
        elif k == "nota":
            out.append(f"<p class='nota'>{b[1]}</p>")
        elif k == "didascalia":
            out.append(f"<p class='didascalia'>{b[1]}</p>")
        elif k == "warn":
            out.append(f"<div class='warn'>{b[1]}</div>")
        elif k == "box":
            out.append("<div class='box'><ul>" + "".join(f"<li>{x}</li>" for x in b[1]) + "</ul></div>")
        elif k == "lista":
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in b[1]) + "</ul>")
        elif k == "tab":
            out.append(_html_tab(b[1]))
        elif k == "schede":
            out.append(html_schede(b[1]))
        elif k == "img":
            out.append(f'<img alt="grafico" src="data:image/png;base64,{base64.b64encode(b[1]).decode()}">')
        elif k == "dettagli":
            out.append(f"<details><summary>{esc(b[1])}</summary>{html_blocchi(b[2])}</details>")
    return "".join(out)


def intestazione(ris):
    cfg = ris["cfg"]
    vers = f"{eur(cfg['versamento_mensile'])} al mese" if cfg["versamento_mensile"] else "nessun versamento mensile"
    return (
        f"Dati aggiornati al {ris['ultimo_dato']:%d/%m/%Y} – {num_it(ris['n'])} simulazioni – capitale iniziale {eur(cfg['capitale_iniziale'])}, {vers}, orizzonte {cfg['orizzonte_anni']} anni "
        f"(risultati a {', '.join(str(h) for h in cfg['orizzonti'])} anni) – generato il {datetime.date.today():%d/%m/%Y}"
    )


def html_report(ris: dict, S: dict | None = None) -> str:
    S = S or sezioni(ris)
    titolo = f"Confronto portafogli – {esc(ris['cfg']['nome'])}"
    sezioni_piene = [(k, v) for k, v in S.items() if v]
    col = colori(ris)
    chips = "".join(f'<span class="chip"><i style="background:{col[k]}"></i>{esc(k)}</span>' for k in ris["nomi"])
    indice = "".join(f'<li><a href="#sez-{i}">{esc(k)}</a></li>' for i, (k, _) in enumerate(sezioni_piene))
    copertina = (
        f"<header class='copertina'><h1>{titolo}</h1><p class='sotto'>Simulazione Monte Carlo del rischio – {intestazione(ris)}</p>"
        f"<div>{chips}</div><p class='nota'>Non è consulenza finanziaria.</p>"
        f"<nav class='indice'><b>Indice</b><ol>{indice}</ol></nav></header>"
    )
    corpo = "".join(f"<h2 id='sez-{i}'>{esc(k)}</h2>{html_blocchi(v)}" for i, (k, v) in enumerate(sezioni_piene))
    return (
        f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{titolo}</title><style>{CSS}</style></head><body class='rep'>{copertina}{corpo}</body></html>"
    )


# ------------------------------------------------------------------ PDF (reportlab, solo Python)
def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        cartella = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(cartella, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-B", os.path.join(cartella, "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-I", os.path.join(cartella, "DejaVuSans-Oblique.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-BI", os.path.join(cartella, "DejaVuSans-BoldOblique.ttf")))
        from reportlab.lib.fonts import addMapping

        addMapping("DejaVu", 0, 0, "DejaVu")
        addMapping("DejaVu", 1, 0, "DejaVu-B")
        addMapping("DejaVu", 0, 1, "DejaVu-I")
        addMapping("DejaVu", 1, 1, "DejaVu-BI")


def _rl(testo):
    """Converte il mini-HTML dei blocchi nel markup di reportlab."""
    t = re.sub(r"<br\s*/?>", "<br/>", str(testo))
    t = re.sub(r"</?(?!b>|/b>|i>|/i>|br/>)[a-z][^>]*>", "", t)
    return t


def pdf_report(ris: dict, S: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        KeepTogether,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    _font()
    S = S or sezioni(ris)
    buf = io.BytesIO()
    pag = landscape(A4)
    W = pag[0] - 24 * mm
    BLU = colors.HexColor("#1F3A5F")
    st = {
        "titolo": ParagraphStyle("titolo", fontName="DejaVu-B", fontSize=26, leading=31, textColor=BLU, spaceAfter=8),
        "sotto": ParagraphStyle("sotto", fontName="DejaVu", fontSize=12, leading=16, textColor=colors.HexColor("#444444"), spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="DejaVu-B", fontSize=14, leading=18, spaceBefore=4, spaceAfter=8, textColor=BLU),
        "h2indice": ParagraphStyle("h2indice", fontName="DejaVu-B", fontSize=14, leading=18, spaceAfter=10, textColor=BLU),
        "h3": ParagraphStyle("h3", fontName="DejaVu-B", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "sottotitolo": ParagraphStyle(
            "sottotitolo", fontName="DejaVu-B", fontSize=9, leading=12, spaceBefore=4, spaceAfter=2, textColor=colors.HexColor("#555555")
        ),
        "p": ParagraphStyle("p", fontName="DejaVu", fontSize=9, leading=12.5, spaceAfter=4),
        "nota": ParagraphStyle("nota", fontName="DejaVu", fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"), spaceAfter=4),
        "didascalia": ParagraphStyle(
            "didascalia", fontName="DejaVu-I", fontSize=8.5, leading=11, textColor=colors.HexColor("#444444"), spaceAfter=6, leftIndent=6
        ),
        "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=7.5, leading=9.2, alignment=2),
        "cellsx": ParagraphStyle("cellsx", fontName="DejaVu", fontSize=7.5, leading=9.2),
        "head": ParagraphStyle("head", fontName="DejaVu-B", fontSize=7.5, leading=9.2, alignment=1),
        "scheda": ParagraphStyle("scheda", fontName="DejaVu", fontSize=8.5, leading=11.5),
        "schedab": ParagraphStyle("schedab", fontName="DejaVu-B", fontSize=10.5, leading=13),
        "toc0": ParagraphStyle("toc0", fontName="DejaVu", fontSize=11, leading=17, leftIndent=10),
    }

    class Documento(BaseDocTemplate):
        """Documento con indice (TOC) cliccabile e segnalibri del PDF per ogni sezione."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.addPageTemplates(
                [
                    PageTemplate(
                        id="pagina", frames=[Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")], onPage=piede
                    )
                ]
            )
            self.n_sez = 0

        def afterFlowable(self, f):
            if isinstance(f, Paragraph) and f.style.name == "h2":
                self.n_sez += 1
                chiave = f"sez{self.n_sez}-{self.page}"
                testo = f.getPlainText()
                self.canv.bookmarkPage(chiave)
                self.canv.addOutlineEntry(testo, chiave, level=0, closed=False)
                self.notify("TOCEntry", (0, testo, self.page, chiave))

        def beforeDocument(self):
            self.n_sez = 0

    def piede(c, d):
        c.saveState()
        c.setFont("DejaVu", 7)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(12 * mm, 6 * mm, f"Confronto portafogli – {ris['cfg']['nome']} – non è consulenza finanziaria")
        c.drawRightString(pag[0] - 12 * mm, 6 * mm, f"pagina {d.page}")
        c.restoreState()

    doc = Documento(
        buf,
        pagesize=pag,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=13 * mm,
        title=f"Confronto portafogli – {ris['cfg']['nome']}",
        author="confronta-portafogli",
    )

    def riquadro(par, sfondo, bordo=None):
        t = Table([[par]], colWidths=[W])
        stile = [
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(sfondo)),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        if bordo:
            stile.append(("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(bordo)))
        t.setStyle(TableStyle(stile))
        return t

    def tabella(t):
        nc = len(t["intest"]) + 1
        prima = min(0.30, max(0.18, 1.6 / nc)) * W
        altre = (W - prima) / (nc - 1)
        dati = []
        if t["gruppi"]:
            riga = [""]
            for g, n in t["gruppi"]:
                riga += [Paragraph(_rl(g), st["head"])] + [""] * (n - 1)
            dati.append(riga)
        dati.append([""] + [Paragraph(_rl(c), st["head"]) for c in t["intest"]])
        cs = st["cellsx"] if t["sx"] else st["cell"]
        for r in t["righe"]:
            dati.append([Paragraph("<b>" + _rl(r[0]) + "</b>", st["cellsx"])] + [Paragraph(_rl(c), cs) for c in r[1:]])
        tb = Table(dati, colWidths=[prima] + [altre] * (nc - 1), repeatRows=1 + bool(t["gruppi"]))
        stile = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0 + bool(t["gruppi"])), colors.HexColor("#eef1f5")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1f5")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
        if t["gruppi"]:
            c = 1
            for _, n in t["gruppi"]:
                stile.append(("SPAN", (c, 0), (c + n - 1, 0)))
                c += n
        tb.setStyle(TableStyle(stile))
        return tb

    def schede(d):
        per_riga = min(5, len(d["schede"]))
        larg = W / per_riga
        celle = []
        for s in d["schede"]:
            badge = ParagraphStyle(
                "b",
                parent=st["scheda"],
                fontName="DejaVu-B",
                textColor=colors.white,
                backColor=colors.HexColor(s["livello_colore"]),
                borderPadding=2,
            )
            celle.append(
                [
                    Paragraph(_rl(esc(s["nome"])), ParagraphStyle("n", parent=st["schedab"], textColor=colors.HexColor(s["colore"]))),
                    Spacer(1, 3),
                    Paragraph(f"Rischio {s['livello']}/5 · {s['livello_nome']}", badge),
                    Paragraph(quadratini(s["livello"]), st["scheda"]),
                    Spacer(1, 3),
                    Paragraph(f"Valore mediano a {d['orizzonte']} anni: <b>{eur(s['valore_mediano'])}</b>", st["scheda"]),
                    Paragraph(f"Totale versato: {eur(s['versato'])}", st["scheda"]),
                    Paragraph(f"Probabilità di perdita: <b>{pct(s['prob_perdita'])}</b>", st["scheda"]),
                    Paragraph(f"Calo massimo tipico: <b>{pct(s['mdd'])}</b>", st["scheda"]),
                    Paragraph(f"Volatilità annua: {pct(s['vol'])}", st["scheda"]),
                    Paragraph(
                        "Volatilità vs benchmark: " + ("—" if s["benchmark"] else f"<b>{num(s['vol_vs_bench'])} volte</b>"), st["scheda"]
                    ),
                ]
            )
        out = []
        for i in range(0, len(celle), per_riga):
            riga = celle[i : i + per_riga]
            riga += [""] * (per_riga - len(riga))
            tb = Table([riga], colWidths=[larg] * per_riga)
            stile = [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
            for j, s in enumerate(d["schede"][i : i + per_riga]):
                stile += [
                    ("BOX", (j, 0), (j, 0), 0.6, colors.HexColor("#cfd4da")),
                    ("LINEABOVE", (j, 0), (j, 0), 4, colors.HexColor(s["colore"])),
                ]
            tb.setStyle(TableStyle(stile))
            out += [tb, Spacer(1, 8)]
        return out

    def immagine(dati_png, prec, dopo):
        from PIL import Image as PI

        w, h = PI.open(io.BytesIO(dati_png)).size
        larg = min(W, w * 0.62)
        alt = larg * h / w
        if alt > pag[1] - 65 * mm:
            alt = pag[1] - 65 * mm
            larg = alt * w / h
        return KeepTogether(prec + [Image(io.BytesIO(dati_png), width=larg, height=alt)] + dopo)

    def flow(blocchi):
        out, i = [], 0
        while i < len(blocchi):
            b = blocchi[i]
            k = b[0]
            if k in ("h2", "h3", "sottotitolo", "p", "nota", "didascalia"):
                out.append(Paragraph(_rl(b[1]), st[k]))
            elif k == "warn":
                out += [riquadro(Paragraph(_rl(b[1]), st["p"]), "#fff4e5", "#e8a33d"), Spacer(1, 5)]
            elif k in ("box", "lista"):
                par = [Paragraph("• " + _rl(x), st["p"]) for x in b[1]]
                out += [riquadro(par, "#f5f6f8") if k == "box" else KeepTogether(par), Spacer(1, 5)]
            elif k == "tab":
                tb, prec = tabella(b[1]), []
                while out and isinstance(out[-1], Paragraph) and out[-1].style.name in ("sottotitolo", "h3") and len(prec) < 2:
                    prec.insert(0, out.pop())  # titolo e sottotitolo sempre sulla stessa pagina della tabella
                out.append(KeepTogether(prec + [tb]) if prec else tb)
                out.append(Spacer(1, 5))
            elif k == "schede":
                out += schede(b[1])
            elif k == "img":
                prec = []
                while out and isinstance(out[-1], Paragraph) and len(prec) < 2:  # titolo/nota insieme al grafico
                    prec.insert(0, out.pop())
                dopo = []
                if i + 1 < len(blocchi) and blocchi[i + 1][0] == "didascalia":  # e la spiegazione sotto
                    dopo = [Paragraph(_rl(blocchi[i + 1][1]), st["didascalia"])]
                    i += 1
                out += [immagine(b[1], prec, dopo), Spacer(1, 5)]
            elif k == "dettagli":
                out += flow([("h3", b[1])] + list(b[2]))
            i += 1
        return out

    # copertina
    col = colori(ris)
    elenco = Table([[Paragraph(f'<font color="{col[k]}">■</font>  {_rl(esc(k))}', st["sotto"])] for k in ris["nomi"]], colWidths=[W * 0.6])
    elenco.setStyle(
        TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    )
    cfg = ris["cfg"]
    storia = [
        Spacer(1, 30 * mm),
        Paragraph("Confronto del rischio di portafogli", st["titolo"]),
        Paragraph(_rl(esc(cfg["nome"])), st["sotto"]),
        Spacer(1, 6 * mm),
        elenco,
        Spacer(1, 8 * mm),
        Paragraph(_rl(intestazione(ris)), st["p"]),
        Spacer(1, 12 * mm),
        Paragraph(
            "Simulazione Monte Carlo a scopo informativo. Non è consulenza finanziaria e non contiene raccomandazioni "
            "di acquisto o vendita.",
            st["nota"],
        ),
        PageBreak(),
    ]
    toc = TableOfContents()
    toc.levelStyles = [st["toc0"]]
    toc.dotsMinLevel = 0
    storia += [Paragraph("Indice", st["h2indice"]), Paragraph("Clicca su una voce per andare alla sezione.", st["nota"]), toc, PageBreak()]
    primo = True
    for k, v in S.items():
        if not v:
            continue
        if not primo:
            storia.append(PageBreak())
        primo = False
        storia.append(Paragraph(_rl(k), st["h2"]))
        storia += flow(v)
    doc.multiBuild(storia)
    return buf.getvalue()


# ------------------------------------------------------------------ CSV
def tabelle_csv(ris: dict) -> dict[str, pd.DataFrame]:
    """{nome_file: DataFrame} con i numeri del report."""
    out = {}
    righe = []
    for a, s in ris["sim"].items():
        for h, df in s["orizzonti"].items():
            for m in df.index:
                for k in df.columns:
                    righe.append({"analisi": a, "orizzonte_anni": h, "metrica": m, "portafoglio": k, "valore": df.loc[m, k]})
    out["risultati_orizzonti.csv"] = pd.DataFrame(righe)
    righe = []
    for a, s in ris["sim"].items():
        for k in s["nomi"]:
            b = s["bande"][k]
            for j in range(b.shape[1]):
                righe.append(
                    {
                        "analisi": a,
                        "portafoglio": k,
                        "mese": j,
                        "p5": b[0][j],
                        "p25": b[1][j],
                        "p50": b[2][j],
                        "p75": b[3][j],
                        "p95": b[4][j],
                    }
                )
    out["fan_chart_percentili.csv"] = pd.DataFrame(righe)
    righe = []
    for a, s in ris["sim"].items():
        for k in s["nomi"]:
            righe.append(
                {
                    "analisi": a,
                    "portafoglio": k,
                    "vol_storica": ris["storico"][a]["stat"][k]["vol"],
                    "vol_simulata": s["vol_sim"][k],
                    "max_drawdown_storico": ris["storico"][a]["stat"][k]["mdd"],
                    "VaR95_1anno": s["var_es"].loc["VaR 95% 1 anno", k],
                    "ES95_1anno": s["var_es"].loc["Expected Shortfall 95% 1 anno", k],
                    "corr_media_titoli": ris["storico"][a]["corr_media"].get(k, np.nan),
                }
            )
    out["altre_metriche.csv"] = pd.DataFrame(righe)
    out["rendimenti_attesi.csv"] = ris["rend_attesi"].T.rename_axis("portafoglio").reset_index()
    out["titoli.csv"] = (
        ris["dati_info"]
        .assign(beta=[ris["beta"].get(BENCH if t == ris["cfg"]["benchmark"]["ticker"] else t, np.nan) for t in ris["dati_info"].index])
        .reset_index()
    )
    if ris.get("controllo"):
        out["controllo_dati.csv"] = ris["controllo"]["tabella_senza_emoji"]
    if ris["stress"]:
        out["stress_test.csv"] = pd.concat([df.assign(analisi=a) for a, df in ris["stress"].items()])
    if ris["idio"]:
        out["rischio_singolo_titolo.csv"] = (
            pd.concat([df.T.assign(analisi=a, orizzonte_anni=h) for a, s in ris["idio"].items() for h, df in s["orizzonti"].items()])
            .rename_axis("portafoglio")
            .reset_index()
        )
    if ris.get("convergenza"):
        c = ris["convergenza"]
        out["verifica_convergenza.csv"] = (
            pd.concat([c["mediana"].assign(misura="mediana"), c["p5"].assign(misura="5° percentile")]).rename_axis("seed").reset_index()
        )
    if ris["modelli"]:
        out["confronto_modelli.csv"] = (
            pd.concat(
                [
                    df.T.assign(analisi=a, modello=m, orizzonte_anni=h)
                    for a, mm in ris["modelli"].items()
                    for m, s in mm.items()
                    for h, df in s["orizzonti"].items()
                ]
            )
            .rename_axis("portafoglio")
            .reset_index()
        )
    if ris.get("fattori"):
        f = ris["fattori"]
        out["fattori_esposizioni_titoli.csv"] = f["stima"].beta.assign(R2=f["stima"].r2, volatilita=f["stima"].vol, volatilita_specifica=f["stima"].vol_specifica).rename_axis("titolo").reset_index()
        out["fattori_quota_rischio.csv"] = pd.DataFrame({p: s["quote"] for p, s in f["scomposizione"].items()}).rename_axis("gruppo").reset_index()
        out["fattori_elenco.csv"] = f["info"].reset_index()
    if ris.get("backtest"):
        out["backtest_var.csv"] = ris["backtest"]["tabella"]
    return out


# ------------------------------------------------------------------ Excel
def excel_report(ris) -> bytes:
    """Risultati in Excel (.xlsx): una scheda per orizzonte, più sintesi, metriche, stress test e titoli.
    Numeri veri (non testo) con formati leggibili: Excel li mostra con le impostazioni italiane del computer."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    blu, grigio = PatternFill("solid", fgColor="1F3A5F"), PatternFill("solid", fgColor="EEF1F5")
    FMT_X = {"€": '#,##0 "€"', "%": "0.0%", "anni": "0.0", "x": "0.00", "": "General"}

    def tipo(metrica):
        if (
            metrica.startswith("Prob")
            or metrica.startswith("Max drawdown")
            or "VaR" in metrica
            or "Shortfall" in metrica
            or ("Volatilità" in metrica and "volte" not in metrica)
            or "Perdita (%)" in metrica
            or "TER" in metrica
            or "Rendimento atteso" in metrica
        ):
            return "%"
        if "anni" in metrica.lower():
            return "anni"
        if "Beta" in metrica or "Correlazione" in metrica:
            return "x"
        return "€"

    def scrivi(ws, riga, titolo, df, fmt_righe=None):
        ws.cell(riga, 1, titolo).font = Font(bold=True, size=12, color="1F3A5F")
        riga += 1
        ws.cell(riga, 1, "").fill = grigio
        for j, c in enumerate(df.columns, start=2):
            x = ws.cell(riga, j, str(c))
            x.font, x.fill, x.alignment = Font(bold=True, color="FFFFFF"), blu, Alignment(wrap_text=True, horizontal="center")
        for i, (nome, r) in enumerate(df.iterrows(), start=riga + 1):
            x = ws.cell(i, 1, str(nome))
            x.font, x.fill = Font(bold=True), grigio
            for j, v in enumerate(r.values, start=2):
                v = None if isinstance(v, float) and not np.isfinite(v) else v
                c = ws.cell(i, j, v.item() if hasattr(v, "item") else v)
                c.number_format = FMT_X[(fmt_righe or tipo)(str(nome))]
        return riga + len(df) + 2

    def larghezze(ws, prima=42, altre=20):
        ws.column_dimensions["A"].width = prima
        for j in range(2, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(j)].width = altre
        ws.freeze_panes = "B3"

    ws = wb.active
    ws.title = "Sintesi"
    ws.cell(1, 1, f"Confronto portafogli – {ris['cfg']['nome']}").font = Font(bold=True, size=14, color="1F3A5F")
    ws.cell(2, 1, intestazione(ris))
    sch = pd.DataFrame(
        {
            s["nome"]: {
                "Valore mediano a fine orizzonte": s["valore_mediano"],
                "Totale versato": s["versato"],
                "Probabilità di perdita": s["prob_perdita"],
                "Max drawdown mediano": s["mdd"],
                "Volatilità annua": s["vol"],
                "Volatilità rispetto al benchmark (volte)": s["vol_vs_bench"],
                "Livello di rischio (1-5)": s["livello"],
            }
            for s in dati_schede(ris)
        }
    )
    scrivi(ws, 4, "Numeri chiave (analisi A)", sch, lambda m: "x" if "volte" in m else ("" if "Livello" in m else tipo(m)))
    larghezze(ws)
    for h in ris["cfg"]["orizzonti"]:
        ws = wb.create_sheet(f"{h} anni")
        riga = 1
        for a, s in ris["sim"].items():
            riga = scrivi(ws, riga, f"{NOME_ANALISI[a]} – dopo {h} anni", s["orizzonti"][h])
        larghezze(ws)
    ws = wb.create_sheet("Altre metriche")
    riga = 1
    for a in ris["sim"]:
        st_a = ris["storico"][a]
        df = pd.DataFrame(
            {
                k: {
                    "Volatilità annua storica": st_a["stat"][k]["vol"],
                    "Volatilità annua simulata": ris["sim"][a]["vol_sim"][k],
                    "Max drawdown storico": st_a["stat"][k]["mdd"],
                    "VaR 95% a 1 anno": ris["sim"][a]["var_es"].loc["VaR 95% 1 anno", k],
                    "Expected Shortfall 95% a 1 anno": ris["sim"][a]["var_es"].loc["Expected Shortfall 95% 1 anno", k],
                }
                for k in ris["sim"][a]["nomi"]
            }
        )
        riga = scrivi(ws, riga, NOME_ANALISI[a], df)
    larghezze(ws)
    if ris["stress"]:
        ws = wb.create_sheet("Stress test")
        riga = 1
        for a, df in ris["stress"].items():
            d = df.set_index(df["Portafoglio"] + " – " + df["Scenario"])[
                [
                    "Valore prima dello shock",
                    "Valore dopo lo shock",
                    "Perdita (€)",
                    "Perdita (%)",
                    "Anni per tornare al versato (mediana)",
                    "Prob. di tornarci entro 10 anni",
                ]
            ]
            riga = scrivi(ws, riga, NOME_ANALISI[a], d.T)  # righe = misure, colonne = portafoglio e scenario
        larghezze(ws, 40, 30)
    ws = wb.create_sheet("Rendimenti attesi")
    scrivi(ws, 1, "Beta e rendimento atteso", ris["rend_attesi"])
    larghezze(ws)
    if ris.get("controllo"):
        ws = wb.create_sheet("Controllo dati")
        scrivi(
            ws,
            1,
            "Controllo dati: " + ris["controllo"]["riepilogo"],
            ris["controllo"]["tabella_senza_emoji"].set_index("Input"),
            lambda m: "",
        )
        larghezze(ws, 16, 16)
    ws = wb.create_sheet("Titoli")
    info = ris["dati_info"].copy()
    info["beta"] = [ris["beta"].get(BENCH if t == ris["cfg"]["benchmark"]["ticker"] else t, np.nan) for t in info.index]
    for c in ("primo dato", "ultimo dato"):
        if c in info:
            info[c] = info[c].astype(str)
    scrivi(ws, 1, "Titoli usati", info, lambda m: "")
    larghezze(ws, 16, 16)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ storico delle analisi
def riassunto(ris) -> dict:
    """Numeri chiave in forma semplice (JSON) per l'elenco «Analisi salvate» e il confronto tra due analisi."""
    cfg = ris["cfg"]
    return {
        "nome": cfg["nome"],
        "creato": datetime.datetime.now().isoformat(timespec="seconds"),
        "simulazioni": ris["n"],
        "orizzonte": cfg["orizzonte_anni"],
        "capitale": cfg["capitale_iniziale"],
        "versamento": cfg["versamento_mensile"],
        "metodo": cfg["rendimento_atteso"]["metodo"],
        "dati_al": f"{ris['ultimo_dato']:%Y-%m-%d}",
        "portafogli": [{k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in s.items()} for s in dati_schede(ris)],
    }


def cartella_storico(nome: str, base: str = "report") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (nome or "confronto").lower()).strip("-") or "confronto"
    return os.path.join(base, f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{slug}")


def elenco_analisi(base: str = "report") -> list[dict]:
    """Analisi salvate (cartelle con riassunto.json), dalla più recente."""
    out = []
    if not os.path.isdir(base):
        return out
    for d in sorted(os.listdir(base), reverse=True):
        f = os.path.join(base, d, "riassunto.json")
        if os.path.exists(f):
            try:
                r = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            r["cartella"] = os.path.join(base, d)
            out.append(r)
    return out


def salva(ris: dict, cartella: str, pdf: bool = True, log=print, S: dict | None = None, pdf_bytes: bytes | None = None) -> str:
    """Scrive report.html, report.pdf, report.xlsx, i CSV e riassunto.json in `cartella`. Ritorna il percorso dell'HTML."""
    os.makedirs(cartella, exist_ok=True)
    S = S or sezioni(ris)
    f = os.path.join(cartella, "report.html")
    open(f, "w", encoding="utf-8").write(html_report(ris, S))
    if pdf:
        open(os.path.join(cartella, "report.pdf"), "wb").write(pdf_bytes or pdf_report(ris, S))
    dcsv = os.path.join(cartella, "dati_csv")
    os.makedirs(dcsv, exist_ok=True)
    for nome, df in tabelle_csv(ris).items():
        df.to_csv(os.path.join(dcsv, nome), index=False, sep=";", decimal=",", encoding="utf-8-sig")
    from configurazione import in_yaml

    open(os.path.join(cartella, "configurazione_usata.yaml"), "w", encoding="utf-8").write(in_yaml(ris["cfg"]))
    open(os.path.join(cartella, "report.xlsx"), "wb").write(excel_report(ris))
    json.dump(riassunto(ris), open(os.path.join(cartella, "riassunto.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return f
