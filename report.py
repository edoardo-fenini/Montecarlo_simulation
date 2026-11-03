"""Report: costruisce le sezioni (blocchi di testo, tabelle e grafici) e le scrive in HTML, PDF e CSV.

Le stesse sezioni sono mostrate come schede nell'app Streamlit."""
import base64, datetime, html, io, os, re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from configurazione import BENCH
from metriche import RIGHE_ORIZZONTE, SINGOLO

SCHEDE = ["Sintesi", "Risultati per orizzonte", "Fan chart", "Drawdown", "Rischio e correlazioni",
          "Stress test", "Robustezza", "Limiti dell'analisi"]
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#882255", "#117733"]
GRIGIO = "#555555"


# ------------------------------------------------------------------ formattazione italiana
def num_it(n): return f"{n:,}".replace(",", ".")
def eur(v): return "–" if v is None or not np.isfinite(v) else f"{v:,.0f} €".replace(",", ".")
def pct(v, d=1): return "–" if v is None or not np.isfinite(v) else f"{v * 100:.{d}f}%".replace(".", ",")
def num(v, d=1): return "mai" if not np.isfinite(v) else f"{v:.{d}f}".replace(".", ",")
def esc(s): return html.escape(str(s), quote=False)


def colori(ris):
    c, i = {}, 0
    for k in ris["nomi"]:
        if k == ris["bench_nome"]:
            c[k] = GRIGIO
        else:
            c[k] = PALETTE[i % len(PALETTE)]; i += 1
    return c


def corto(k, n=22):
    return k if len(k) <= n else k[:n - 1] + "…"


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
        ax.fill_between(x, b[0], b[4], color=c, alpha=0.15, lw=0, label="5°–95° percentile")
        ax.fill_between(x, b[1], b[3], color=c, alpha=0.30, lw=0, label="25°–75° percentile")
        ax.plot(x, b[2], color=c, lw=2, label="Mediana")
        ax.plot(x, s["versato"], color="black", ls="--", lw=1, label="Totale versato")
        for h in cp:
            j = h * 12
            ax.axvline(h, color="#999", lw=0.8, ls=":")
            for v, dy in ((b[4][j], 5), (b[2][j], 6), (b[0][j], -12)):
                ax.plot([h], [v], "o", color=c, ms=5, mec="white", mew=0.8, zorder=5)
                ax.annotate(eur(v), (h, v), xytext=(-5, dy), textcoords="offset points", ha="right", fontsize=7.5,
                            color="#111", bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75), zorder=6)
        ax.set_title(k, color=c, fontweight="bold", fontsize=11)
        ax.set_ylim(0, top)
        ax.grid(alpha=0.25)
        _euro_asse(ax)
    for ax in axs.ravel()[len(nomi):]:
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
        for k in s["nomi"]:
            ax.hist(s["mdd_fin"][k] * 100, bins=np.linspace(-100, 0, 41), alpha=0.45, color=col[k], label=corto(k, 30), density=True)
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
    for ax in axs.ravel()[len(nomi):]:
        ax.axis("off")
    fig.text(0.5, -0.02, "Barra = quota del rischio del titolo; trattino nero = suo peso nel portafoglio. "
             "Barra più lunga del trattino = il titolo pesa sul rischio più di quanto pesa in euro.", ha="center", fontsize=8.5)
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
        ax.set_xticks(range(n)); ax.set_yticks(range(n))
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


FMT = {"Totale versato": eur, "Valore mediano": eur, "5° percentile": eur, "95° percentile": eur,
       "Prob. sotto il versato": pct, "Max drawdown mediano": pct, "Max drawdown peggiore (95%)": pct,
       "Tempo sott'acqua max, mediano (anni)": num, "Tempo sott'acqua max, peggiore 95% (anni)": num}


def tab_orizzonte(ris, h, anal):
    nomi = ris["nomi"]
    righe = [[r] + [FMT[r](ris["sim"][a]["orizzonti"][h].loc[r, k]) for a in anal for k in nomi] for r in RIGHE_ORIZZONTE]
    gruppi = [(f"Analisi {a}", len(nomi)) for a in anal] if len(anal) > 1 else None
    return T([corto(k) for k in nomi] * len(anal), righe, gruppi)


def ordine(vals, desc=True):
    return " > ".join(sorted(vals, key=lambda k: vals[k], reverse=desc))


def metriche_rischio(ris, s):
    h = ris["cfg"]["orizzonte_anni"]
    return {"ES 95% a 1 anno": {k: s["var_es"].loc["Expected Shortfall 95% 1 anno", k] for k in s["nomi"]},
            f"Max drawdown mediano a {h} anni": {k: -s["orizzonti"][h].loc["Max drawdown mediano", k] for k in s["nomi"]},
            f"Prob. sotto il versato a {h} anni": {k: s["orizzonti"][h].loc["Prob. sotto il versato", k] for k in s["nomi"]}}


def testo_metodo(ris):
    cfg = ris["cfg"]
    ra = cfg["rendimento_atteso"]
    m = ra["metodo"]
    drag = (" <b>Volatility drag:</b> il rendimento atteso è una <i>media</i> (1 € vale in media 1+r dopo un anno). "
            "Con le oscillazioni il risultato <i>tipico</i> (la mediana) resta più basso della media: una perdita del 50% "
            "richiede un guadagno del 100% per rientrare. Più un portafoglio oscilla, più la sua mediana resta indietro.")
    if m == "beta":
        t = (f"<b>Metodo del rendimento atteso: beta.</b> Ogni titolo ha rendimento atteso = {pct(ra['tasso_privo_rischio'], 0)} (tasso privo di rischio) "
             f"+ beta × {pct(ra['premio_mercato'], 0)} (premio per il rischio di mercato). Il beta misura quanto il titolo si muove "
             "con il benchmark (beta 1,5 = in media si muove del 50% in più). Il rischio di mercato, che non si può eliminare "
             "diversificando, viene remunerato; il rischio specifico del singolo titolo no, perché si può diversificare. "
             "Le volatilità, le code e le correlazioni restano quelle storiche: cambia solo la media.")
    elif m == "uguale":
        t = (f"<b>Metodo del rendimento atteso: uguale.</b> Tutti i portafogli hanno lo stesso rendimento medio del "
             f"{pct(ra['valore_uguale'], 0)} annuo: le differenze dipendono solo dal rischio. Volatilità, code e correlazioni restano quelle storiche.")
    elif m == "personalizzato":
        t = "<b>Metodo del rendimento atteso: personalizzato.</b> Il rendimento medio annuo di ogni portafoglio è quello indicato nella configurazione."
    else:
        t = ("<b>Metodo del rendimento atteso: storico.</b> ATTENZIONE: si usano i rendimenti realmente ottenuti in passato. "
             "Questo proietta il passato nel futuro: se i titoli sono stati scelti oggi perché sono andati bene (survivorship bias), "
             "i risultati saranno troppo ottimistici.")
    return t + drag


def sintesi(ris):
    cfg, n = ris["cfg"], ris["n"]
    a = "A"
    s = ris["sim"][a]
    nomi, bn, H = ris["nomi"], ris["bench_nome"], cfg["orizzonte_anni"]
    st = ris["storico"][a]["stat"]
    F = []
    vers = f" e versando {eur(cfg['versamento_mensile'])} al mese" if cfg["versamento_mensile"] else " senza altri versamenti"
    metodo = {"beta": "rendimento atteso legato al rischio di mercato (metodo beta)", "uguale": "stesso rendimento atteso per tutti",
              "storico": "rendimenti storici (proiettano il passato nel futuro)", "personalizzato": "rendimenti attesi scelti da te"}[cfg["rendimento_atteso"]["metodo"]]
    F.append(f"Ho simulato {num_it(n)} futuri possibili a {H} anni per {len(nomi)} portafogli, partendo da {eur(cfg['capitale_iniziale'])}{vers}, con {metodo}.")
    vol = {k: st[k]["vol"] for k in nomi}
    altri = [k for k in nomi if k != bn]
    if altri:
        top = max(altri, key=vol.get)
        rapp = "; ".join(f"«{k}» {num(vol[k] / vol[bn])} volte" for k in sorted(altri, key=vol.get, reverse=True))
        F.append(f"Il portafoglio che oscilla di più è «{top}» (volatilità {pct(vol[top], 0)} l'anno contro {pct(vol[bn], 0)} del benchmark). "
                 f"Rispetto al benchmark la volatilità è: {rapp}.")
    prob = "; ".join(f"«{k}» " + " / ".join(pct(s['orizzonti'][h].loc['Prob. sotto il versato', k], 0) for h in cfg["orizzonti"]) for k in nomi)
    F.append(f"Probabilità di avere meno di quanto versato a {' / '.join(str(h) for h in cfg['orizzonti'])} anni: {prob}.")
    dd = {k: s["orizzonti"][H].loc["Max drawdown mediano", k] for k in nomi}
    lo, hi = min(dd, key=dd.get), max(dd, key=dd.get)
    F.append(f"Il calo massimo tipico (mediano) in {H} anni va dal {pct(-dd[hi], 0)} di «{hi}» al {pct(-dd[lo], 0)} di «{lo}».")
    med = "; ".join(f"«{k}» {eur(s['orizzonti'][H].loc['Valore mediano', k])}" for k in nomi)
    F.append(f"Valore mediano dopo {H} anni (versati {eur(s['orizzonti'][H].loc['Totale versato', nomi[0]])}): {med}. "
             "La mediana è più bassa del valore medio, e lo è di più per i portafogli che oscillano di più (volatility drag).")
    if a in ris["stress"]:
        d = ris["stress"][a]
        d2 = d[d["Scenario"] != SINGOLO]
        w = d2.loc[d2["Perdita (%)"].idxmax()]
        lenti = sorted({r["Portafoglio"] for _, r in d2.iterrows() if r["Scende sotto il versato"] and r["Prob. di tornarci entro 10 anni"] < 0.5})
        f = f"Negli stress test la perdita più pesante è di «{w['Portafoglio']}» nello scenario «{w['Scenario']}» (−{pct(w['Perdita (%)'], 0)})."
        if lenti:
            f += " In almeno uno scenario non tornerebbero al versato entro 10 anni in più di metà dei casi: " + ", ".join(f"«{k}»" for k in lenti) + "."
        F.append(f)
    F += conclusioni_stabili(ris, breve=True)
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
        out.append("La classifica di rischio (perdita media nei casi peggiori a 1 anno) è la stessa con tutti i modelli." if not cambi
                   else "La classifica di rischio cambia con: " + ", ".join(cambi) + ".")
    if len(anal) > 1:
        o = {a: ordine(metriche_rischio(ris, ris["sim"][a])[ES]) for a in anal}
        out.append("Il periodo storico usato (A o B) non cambia la classifica di rischio." if len(set(o.values())) == 1
                   else "La classifica di rischio dipende dal periodo storico: analisi A " + o["A"] + "; analisi B " + o["B"] + ".")
    if ris["idio"]:
        H = ris["cfg"]["orizzonte_anni"]
        dp = max(ris["idio"][a]["orizzonti"][H].loc["Prob. sotto il versato", k] - ris["sim"][a]["orizzonti"][H].loc["Prob. sotto il versato", k]
                 for a in ris["idio"] for k in ris["nomi"])
        out.append(f"Il rischio di crollo di un singolo titolo aumenta la probabilità di finire sotto il versato al massimo di {num(dp * 100)} punti percentuali.")
    if ris["sensibilita"]:
        H = ris["cfg"]["orizzonte_anni"]
        cambia = False
        for a, var in ris["sensibilita"].items():
            o0 = ordine({k: ris["sim"][a]["orizzonti"][H].loc["Valore mediano", k] for k in ris["nomi"]})
            cambia |= any(ordine({k: s["orizzonti"][H].loc["Valore mediano", k] for k in ris["nomi"]}) != o0 for _, s in var)
        out.append("Cambiando il rendimento atteso la classifica sul valore finale mediano " + ("cambia: dipende dalle ipotesi." if cambia else "non cambia."))
    return out


def sezioni(ris):
    """Ritorna {scheda: [blocchi]}."""
    cfg, n, nomi = ris["cfg"], ris["n"], ris["nomi"]
    anal = [a for a in ris["sim"] if a != "C"]
    H = cfg["orizzonte_anni"]
    S = {k: [] for k in SCHEDE}
    d = lambda t: t.strftime("%d/%m/%Y")

    # ---- Sintesi
    B = S["Sintesi"]
    if n < 5000:
        B.append(("warn", f"<b>Prova rapida:</b> solo {num_it(n)} simulazioni. I numeri sono indicativi."))
    B.append(("box", sintesi(ris)))
    B.append(("warn", testo_metodo(ris)))
    ra = ris["rend_attesi"]
    righe = [[k, num(ra.loc["Beta verso il benchmark", k], 2), pct(ra.loc["Rendimento atteso annuo", k]) if cfg["rendimento_atteso"]["metodo"] != "storico" else "storico",
              pct(ra.loc["di cui costi ETF (TER)", k], 2)] for k in nomi]
    B.append(("h3", "Rendimento atteso usato"))
    B.append(T(["Beta", "Rendimento atteso annuo", "Costo ETF sottratto"], righe))
    B.append(("h3", "Come leggere i termini"))
    B.append(("box", [
        "<b>Percentile</b>: il 5° percentile è il valore sotto cui finisce il 5% dei casi peggiori; il 95° quello sopra cui sta il 5% dei migliori.",
        "<b>Volatilità</b>: quanto oscillano i prezzi in un anno. 30% = oscillazioni tipiche di ±30%.",
        "<b>Max drawdown</b>: il calo massimo da un massimo al minimo successivo (da 10.000 a 4.000 € = −60%).",
        "<b>Tempo sott'acqua</b>: il periodo più lungo passato sotto il massimo precedente.",
        "<b>VaR 95% a 1 anno</b>: la perdita superata solo nel 5% dei casi in un anno. <b>Expected Shortfall (ES)</b>: la perdita media in quel 5% di casi peggiori.",
        "<b>Volatility drag</b>: con le oscillazioni il risultato tipico resta sotto la media; più oscillazioni, più distacco.",
        "<b>Bootstrap a blocchi</b>: si rimescolano pezzi di storia reale (circa 20 giorni di borsa ciascuno), così restano crisi, code e correlazioni.",
        f"<b>Ribilanciamento ({cfg['ribilanciamento']})</b>: si riportano i titoli ai pesi scelti pagando il {pct(cfg['costo_ribilanciamento'], 1)} dell'importo movimentato."]))
    B.append(("h3", "Dati e periodi analizzati"))
    crisi = [("bolla dot-com 2000-2002", "2000-03-10", "2002-10-09"), ("crisi finanziaria 2008", "2007-10-09", "2009-03-09"),
             ("debito europeo 2011", "2011-05-01", "2011-10-04"), ("Covid 2020", "2020-02-19", "2020-03-23"),
             ("ribasso 2022", "2022-01-03", "2022-10-12"), ("crisi bancaria 2023", "2023-03-08", "2023-03-20")]
    desc = {"A": "Periodo comune (tutti i titoli quotati)", "B": "Periodo lungo (titoli disponibili a ogni data, pesi ridistribuiti)",
            "C": "Dal 1999 con proxy di settore per i titoli non ancora quotati"}
    righe = []
    for a, (i0, i1, ng) in ris["periodi"].items():
        dentro = [c for c, x, y in crisi if pd.Timestamp(x) >= i0 and pd.Timestamp(y) <= i1]
        righe.append([a, desc[a], f"{d(i0)} – {d(i1)}", num_it(ng), ", ".join(dentro) or "nessuna grande crisi"])
    B.append(T(["Descrizione", "Periodo", "Giorni", "Crisi incluse"], righe, sx=True))
    if "B" in ris["note"]:
        B.append(("nota", ris["note"]["B"]))
    b = cfg["benchmark"]
    B.append(("nota", f"Prezzi Yahoo Finance (adjusted close, dividendi inclusi) aggiornati al {d(ris['ultimo_dato'])}, convertiti in EUR con il cambio giornaliero "
                      f"(il rischio di cambio è incluso). Benchmark: {esc(b.get('descrizione') or b['nome'])} ({b['ticker']}{', ISIN ' + b['isin'] if b.get('isin') else ''}, TER {pct(b['ter'], 2)}); "
                      f"prima della nascita dell'ETF uso l'indice {b.get('proxy_storico') or '–'} convertito in EUR meno il TER (proxy)."))
    if "B" in ris["sim"]:
        B.append(("nota", "Analisi B: quando un titolo non era ancora quotato, il suo peso è ridistribuito tra i titoli già disponibili dello stesso portafoglio."))
    info = ris["dati_info"]
    righe = []
    for t, r in info.iterrows():
        tt = BENCH if t == b["ticker"] else t
        pi = (ris["proxy_info"] or {}).get(tt, {})
        righe.append([t, esc(corto(r["nome"] or "", 30)), r["valuta"] or "", r["tipo"], d(pd.Timestamp(r["primo dato"])), num(r["anni di storia"]),
                      num(ris["beta"].get(tt, np.nan), 2), pi.get("categoria", "–"), esc(pi.get("fonte", ""))])
    B.append(("dettagli", "Titoli usati (valuta, storia, beta, settore)", [T(["Nome", "Valuta", "Tipo", "Primo dato", "Anni", "Beta", "Settore stress", "Come è stato riconosciuto"], righe, sx=True)]))
    if ris["avvisi"]:
        B.append(("warn", "<b>Avvisi sui dati:</b><br/>" + "<br/>".join(esc(x) for x in ris["avvisi"])))
    if ris["estremi"]:
        B.append(("dettagli", f"Movimenti giornalieri estremi (oltre ±30%): {len(ris['estremi'])}",
                  [("lista", [esc(x) for x in ris["estremi"]]), ("nota", "Di solito sono eventi reali (risultati trimestrali, crisi). "
                                                                       "Se vedi un −50% seguito da un +100%, potrebbe essere uno split non corretto da Yahoo.")]))

    # ---- Risultati per orizzonte
    B = S["Risultati per orizzonte"]
    B.append(("nota", "Analisi A: periodo comune a tutti i titoli. " + ("Analisi B: periodo lungo. " if "B" in anal else "")
              + "Max drawdown e tempo sott'acqua sono calcolati dall'inizio fino a quell'anno."))
    for h in cfg["orizzonti"]:
        B.append(("h3", f"Dopo {h} anni"))
        if len(nomi) <= 4:
            B.append(tab_orizzonte(ris, h, anal))
        else:
            for a in anal:
                B.append(("nota", f"Analisi {a}"))
                B.append(tab_orizzonte(ris, h, [a]))

    # ---- Fan chart
    B = S["Fan chart"]
    B.append(("nota", "Fascia scura = 50% dei casi, fascia chiara = 90%. I puntini segnano 5°, 50° e 95° percentile agli orizzonti scelti; la linea tratteggiata è il totale versato."))
    for a in anal:
        B.append(("h3", f"Analisi {a}"))
        B.append(("img", fan_chart(ris, a)))

    # ---- Drawdown
    B = S["Drawdown"]
    B.append(("nota", "Distribuzione del calo massimo (max drawdown) che ogni portafoglio attraversa nell'intero orizzonte: più la curva sta a sinistra, più sono frequenti cali profondi."))
    B.append(("img", istogrammi_mdd(ris)))
    righe = []
    for r in ["Max drawdown mediano", "Max drawdown peggiore (95%)", "Tempo sott'acqua max, mediano (anni)", "Tempo sott'acqua max, peggiore 95% (anni)"]:
        righe.append([r] + [FMT[r](ris["sim"][a]["orizzonti"][H].loc[r, k]) for a in anal for k in nomi])
    B.append(T([corto(k) for k in nomi] * len(anal), righe, [(f"Analisi {a}", len(nomi)) for a in anal] if len(anal) > 1 else None))

    # ---- Rischio e correlazioni
    B = S["Rischio e correlazioni"]
    righe = []
    for et, f in (("Volatilità annua storica", lambda a, k: pct(ris["storico"][a]["stat"][k]["vol"])),
                  ("Volatilità annua simulata", lambda a, k: pct(ris["sim"][a]["vol_sim"][k])),
                  ("Max drawdown storico", lambda a, k: pct(ris["storico"][a]["stat"][k]["mdd"])),
                  ("VaR 95% a 1 anno", lambda a, k: pct(ris["sim"][a]["var_es"].loc["VaR 95% 1 anno", k])),
                  ("Expected Shortfall 95% a 1 anno", lambda a, k: pct(ris["sim"][a]["var_es"].loc["Expected Shortfall 95% 1 anno", k])),
                  ("Correlazione media tra i titoli", lambda a, k: num(ris["storico"][a]["corr_media"][k], 2) if k in ris["storico"][a]["corr_media"] else "–")):
        righe.append([et] + [f(a, k) for a in anal for k in nomi])
    B.append(T([corto(k) for k in nomi] * len(anal), righe, [(f"Analisi {a}", len(nomi)) for a in anal] if len(anal) > 1 else None))
    g = grafico_rischio(ris, "A")
    if g:
        B.append(("h3", "Da dove arriva il rischio dentro ogni portafoglio (analisi A)"))
        B.append(("img", g))
    B.append(("h3", "Correlazione tra i portafogli"))
    B.append(("nota", "1 = si muovono sempre insieme; 0 = indipendenti."))
    B.append(("img", heatmap(ris)))

    # ---- Stress test
    B = S["Stress test"]
    if ris["stress"]:
        B.append(("nota", f"Lo shock colpisce il valore mediano simulato a metà orizzonte ({num(H / 2)} anni). Ogni titolo perde in base al suo settore "
                          "(tech, finanza, altro/mercato); un portafoglio perde la media pesata. «Anni per tornare al versato» viene da una nuova "
                          "simulazione dopo lo shock (mediana), con lo stesso rendimento atteso: è un'ipotesi ottimistica dopo una crisi. "
                          "«Il titolo più pesante perde il 90%» non si applica agli ETF."))
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
                righe.append([esc(r["Portafoglio"]), r["Scenario"], eur(r["Valore prima dello shock"]), eur(r["Valore dopo lo shock"]),
                              f"{eur(r['Perdita (€)'])} ({pct(r['Perdita (%)'], 0)})", rec,
                              "–" if not r["Scende sotto il versato"] else pct(r["Prob. di tornarci entro 10 anni"], 0)])
            B.append(T(["Scenario", "Valore prima", "Valore dopo", "Perdita", f"Anni per tornare a {eur(df['Totale versato'].iloc[0])}", "Prob. entro 10 anni"], righe, sx=True))
    else:
        B.append(("p", "Modulo stress test non attivato."))

    # ---- Robustezza
    B = S["Robustezza"]
    if ris["modelli"]:
        B.append(("h3", "Confronto tra modelli"))
        B.append(("nota", "Student-t: code grasse, nessun raggruppamento della volatilità. GARCH(1,1): volatilità che sale e scende nel tempo. "
                          "Classifica = dal portafoglio più rischioso al meno rischioso."))
        for a in ris["modelli"]:
            righe = []
            mod = [("Block bootstrap", ris["sim"][a])] + list(ris["modelli"][a].items())
            rif = {m: ordine(v) for m, v in metriche_rischio(ris, ris["sim"][a]).items()}
            for m in rif:
                for nome, s in mod:
                    o = ordine(metriche_rischio(ris, s)[m])
                    righe.append([m, nome, esc(o), "sì" if o == rif[m] else "<b>NO</b>"])
            B.append(("nota", f"Analisi {a}"))
            B.append(T(["Modello", "Classifica (dal più rischioso)", "Uguale al bootstrap?"], righe, sx=True))
    if ris["sensibilita"]:
        B.append(("h3", "Sensibilità al rendimento atteso"))
        for a, var in ris["sensibilita"].items():
            righe = []
            for et, s in [("scelta di base", ris["sim"][a])] + var:
                vals = {k: s["orizzonti"][H].loc["Valore mediano", k] for k in nomi}
                righe.append([et] + [eur(vals[k]) for k in nomi] + [esc(ordine(vals))])
            B.append(("nota", f"Analisi {a} – valore mediano a {H} anni"))
            B.append(T([corto(k) for k in nomi] + ["Classifica (dal più alto)"], righe))
    if ris["idio"]:
        rs = cfg["rischio_singolo_titolo"]
        B.append(("h3", "Rischio sul singolo titolo"))
        B.append(("nota", f"Ogni azione ha una probabilità del {pct(rs['probabilita_annua'])} l'anno di crollare dell'{pct(rs['perdita_min'], 0)}–{pct(rs['perdita_max'], 0)} "
                          "in un giorno (fallimento, frode). Il rendimento medio resta uguale: cambia solo il rischio. Gli ETF non sono toccati."))
        for a in ris["idio"]:
            righe = []
            for r in ["Prob. sotto il versato", "Max drawdown mediano", "Max drawdown peggiore (95%)", "5° percentile"]:
                righe.append([r + " – senza crolli"] + [FMT[r](ris["sim"][a]["orizzonti"][H].loc[r, k]) for k in nomi])
                righe.append([r + " – con crolli"] + [FMT[r](ris["idio"][a]["orizzonti"][H].loc[r, k]) for k in nomi])
            B.append(("nota", f"Analisi {a}, a {H} anni"))
            B.append(T([corto(k) for k in nomi], righe))
    if "C" in ris["sim"]:
        B.append(("h3", "Storia allungata dal 1999 con proxy (analisi C)"))
        frac = ris["note"].get("C_proxy", {})
        pi = ris["proxy_info"] or {}
        sint = [f"{t} {pct(v, 0)} (proxy {pi.get(t, {}).get('proxy', '–')})" for t, v in frac.items() if v > 0.005 and t != BENCH]
        B.append(("warn", "<b>Dati reali e dati proxy.</b> Per i giorni in cui un titolo non esisteva ho generato rendimenti sintetici: beta × rendimento del proxy "
                          "di settore + residui ripescati da quelli reali del titolo (stessa volatilità e correlazione misurate quando il titolo esisteva). "
                          "Non sono dati veri. Quota di giorni sintetici: " + (", ".join(sint) or "nessuno") + "."))
        for h in cfg["orizzonti"]:
            B.append(("nota", f"Dopo {h} anni – analisi C"))
            B.append(tab_orizzonte(ris, h, ["C"]))
        B.append(("img", fan_chart(ris, "C")))
    if B:
        B.insert(0, ("box", conclusioni_stabili(ris) + ["Il <b>livello</b> dei numeri dipende sempre dalle ipotesi (rendimento atteso, periodo storico); "
                                                        "le <b>differenze di rischio</b> tra portafogli sono più solide."]))
        B.insert(0, ("h3", "Quanto sono solide queste conclusioni?"))
    else:
        B.append(("p", "Nessun modulo di robustezza attivato (confronto tra modelli, analisi C)."))
        if ris["idio"] or len(anal) > 1:
            B.append(("box", conclusioni_stabili(ris)))

    # ---- Limiti
    S["Limiti dell'analisi"] = [("box", [
        "<b>Storia breve</b>: i titoli quotati da pochi anni hanno pochi dati; il periodo comune (A) può non contenere grandi crisi.",
        "<b>Rendimento atteso</b>: è un'ipotesi, non una previsione. Cambiandolo cambiano i valori finali.",
        "<b>Survivorship bias</b>: chi sceglie oggi titoli che sono andati bene nel passato rischia di sopravvalutarli; le società fallite non compaiono nei dati.",
        "<b>Concentrazione</b>: pochi titoli dello stesso settore possono essere colpiti tutti insieme da un singolo evento.",
        "<b>Il futuro può essere diverso dal passato</b>: il modello rimescola eventi già avvenuti e non può inventare crisi di tipo nuovo.",
        "<b>Costi e tasse</b>: inclusi solo il TER del benchmark e il costo di ribilanciamento; niente imposte, spread o commissioni.",
        "<b>Dati</b>: Yahoo Finance può contenere errori; prima della nascita dell'ETF il benchmark è un indice (proxy)."]),
        ("p", "<b>Questa analisi non è consulenza finanziaria</b> e non contiene raccomandazioni di acquisto o vendita.")]
    return S


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#fff;--fg:#1c1c1c;--mut:#666;--line:#ddd;--card:#f5f6f8;--warn:#fff4e5;--warnb:#e8a33d}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a6;--line:#363a40;--card:#1f2227;--warn:#33291a;--warnb:#c58a2b}}
.rep{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
body.rep{max-width:1100px;margin:0 auto;padding:16px}
.rep h1{font-size:1.7rem}.rep h2{margin-top:2.2rem;border-bottom:1px solid var(--line);padding-bottom:4px}.rep h3{margin-top:1.4rem}
.rep table{border-collapse:collapse;margin:10px 0;font-size:.84rem;width:100%}.rep td,.rep th{border:1px solid var(--line);padding:4px 7px;text-align:right}
.rep th{background:var(--card)}.rep th.g{text-align:center}.rep td.e{text-align:left;font-weight:600;background:var(--card)}.rep table.sx td{text-align:left}
.rep .sc{overflow-x:auto}.rep img{max-width:100%;height:auto;background:#fff}.rep .box{background:var(--card);padding:10px 16px;border-radius:8px}
.rep .warn{background:var(--warn);border-left:5px solid var(--warnb);padding:10px 16px;border-radius:6px;margin:12px 0}
.rep .nota{color:var(--mut);font-size:.9rem}.rep details{margin:8px 0}.rep summary{cursor:pointer;font-weight:600}
"""


def _html_tab(t):
    h = f'<div class="sc"><table class="{"sx" if t["sx"] else ""}">'
    if t["gruppi"]:
        h += "<tr><th></th>" + "".join(f'<th colspan="{n}" class="g">{esc(g)}</th>' for g, n in t["gruppi"]) + "</tr>"
    h += "<tr><th></th>" + "".join(f"<th>{esc(c)}</th>" for c in t["intest"]) + "</tr>"
    for r in t["righe"]:
        h += f'<tr><td class="e">{r[0]}</td>' + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>"
    return h + "</table></div>"


def html_blocchi(blocchi):
    out = []
    for b in blocchi:
        k = b[0]
        if k in ("h2", "h3"):
            out.append(f"<{k}>{esc(b[1])}</{k}>")
        elif k == "p":
            out.append(f"<p>{b[1]}</p>")
        elif k == "nota":
            out.append(f"<p class='nota'>{b[1]}</p>")
        elif k == "warn":
            out.append(f"<div class='warn'>{b[1]}</div>")
        elif k == "box":
            out.append("<div class='box'><ul>" + "".join(f"<li>{x}</li>" for x in b[1]) + "</ul></div>")
        elif k == "lista":
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in b[1]) + "</ul>")
        elif k == "tab":
            out.append(_html_tab(b[1]))
        elif k == "img":
            out.append(f'<img alt="grafico" src="data:image/png;base64,{base64.b64encode(b[1]).decode()}">')
        elif k == "dettagli":
            out.append(f"<details><summary>{esc(b[1])}</summary>{html_blocchi(b[2])}</details>")
    return "".join(out)


def intestazione(ris):
    cfg = ris["cfg"]
    vers = f"{eur(cfg['versamento_mensile'])} al mese" if cfg["versamento_mensile"] else "nessun versamento mensile"
    return (f"{num_it(ris['n'])} simulazioni – capitale iniziale {eur(cfg['capitale_iniziale'])}, {vers}, orizzonte {cfg['orizzonte_anni']} anni "
            f"(risultati a {', '.join(str(h) for h in cfg['orizzonti'])} anni) – generato il {datetime.date.today():%d/%m/%Y}")


def html_report(ris, S=None):
    S = S or sezioni(ris)
    titolo = f"Confronto portafogli – {esc(ris['cfg']['nome'])}"
    corpo = "".join(f"<h2>{esc(k)}</h2>{html_blocchi(v)}" for k, v in S.items() if v)
    return (f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{titolo}</title><style>{CSS}</style></head><body class='rep'><h1>{titolo}</h1><p class='nota'>{intestazione(ris)}</p>{corpo}</body></html>")


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
        addMapping("DejaVu", 0, 0, "DejaVu"); addMapping("DejaVu", 1, 0, "DejaVu-B")
        addMapping("DejaVu", 0, 1, "DejaVu-I"); addMapping("DejaVu", 1, 1, "DejaVu-BI")


def _rl(testo):
    """Converte il mini-HTML dei blocchi nel markup di reportlab."""
    t = re.sub(r"<br\s*/?>", "<br/>", str(testo))
    t = re.sub(r"</?(?!b>|/b>|i>|/i>|br/>)[a-z][^>]*>", "", t)
    return t


def pdf_report(ris, S=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    _font()
    S = S or sezioni(ris)
    buf = io.BytesIO()
    pag = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=pag, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Confronto portafogli – {ris['cfg']['nome']}")
    W = pag[0] - 24 * mm
    st = {
        "h1": ParagraphStyle("h1", fontName="DejaVu-B", fontSize=17, leading=21, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName="DejaVu-B", fontSize=13.5, leading=17, spaceBefore=6, spaceAfter=6, textColor=colors.HexColor("#0b3d6b")),
        "h3": ParagraphStyle("h3", fontName="DejaVu-B", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="DejaVu", fontSize=9, leading=12.5, spaceAfter=4),
        "nota": ParagraphStyle("nota", fontName="DejaVu", fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"), spaceAfter=4),
        "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=7, leading=8.6, alignment=2),
        "cellsx": ParagraphStyle("cellsx", fontName="DejaVu", fontSize=7, leading=8.6),
        "head": ParagraphStyle("head", fontName="DejaVu-B", fontSize=7, leading=8.6, alignment=1),
    }

    def riquadro(par, sfondo, bordo=None):
        t = Table([[par]], colWidths=[W])
        stile = [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(sfondo)), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
        if bordo:
            stile.append(("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(bordo)))
        t.setStyle(TableStyle(stile))
        return t

    def tabella(t):
        nc = len(t["intest"]) + 1
        prima = min(0.30, max(0.16, 1.6 / nc)) * W
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
        stile = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("BACKGROUND", (0, 0), (-1, 0 + bool(t["gruppi"])), colors.HexColor("#f0f2f5")),
                 ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f5")),
                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if t["gruppi"]:
            c = 1
            for _, n in t["gruppi"]:
                stile.append(("SPAN", (c, 0), (c + n - 1, 0))); c += n
        tb.setStyle(TableStyle(stile))
        return tb

    def flow(blocchi):
        out = []
        for b in blocchi:
            k = b[0]
            if k in ("h2", "h3"):
                out.append(Paragraph(_rl(b[1]), st[k]))
            elif k in ("p", "nota"):
                out.append(Paragraph(_rl(b[1]), st[k]))
            elif k == "warn":
                out += [riquadro(Paragraph(_rl(b[1]), st["p"]), "#fff4e5", "#e8a33d"), Spacer(1, 5)]
            elif k in ("box", "lista"):
                par = [Paragraph("• " + _rl(x), st["p"]) for x in b[1]]
                out += [riquadro(par, "#f5f6f8") if k == "box" else KeepTogether(par), Spacer(1, 5)]
            elif k == "tab":
                out += [tabella(b[1]), Spacer(1, 5)]
            elif k == "img":
                from PIL import Image as PI
                w, h = PI.open(io.BytesIO(b[1])).size
                larg = min(W, w * 0.62)
                alt = larg * h / w
                if alt > pag[1] - 60 * mm:
                    alt = pag[1] - 60 * mm; larg = alt * w / h
                img = Image(io.BytesIO(b[1]), width=larg, height=alt)
                if out and isinstance(out[-1], Paragraph):  # tiene insieme titolo/nota e grafico
                    prec = [out.pop()]
                    if out and isinstance(out[-1], Paragraph):
                        prec.insert(0, out.pop())
                    out.append(KeepTogether(prec + [img]))
                else:
                    out.append(img)
                out.append(Spacer(1, 5))
            elif k == "dettagli":
                out.append(Paragraph(_rl(b[1]), st["h3"]))
                out += flow(b[2])
        return out

    storia = [Paragraph(_rl(f"Confronto portafogli – {ris['cfg']['nome']}"), st["h1"]), Paragraph(_rl(intestazione(ris)), st["nota"])]
    primo = True
    for k, v in S.items():
        if not v:
            continue
        if not primo:
            storia.append(PageBreak())
        primo = False
        storia.append(Paragraph(_rl(k), st["h2"]))
        storia += flow(v)

    def piede(c, d):
        c.saveState()
        c.setFont("DejaVu", 7)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(12 * mm, 6 * mm, "Non è consulenza finanziaria.")
        c.drawRightString(pag[0] - 12 * mm, 6 * mm, f"pagina {d.page}")
        c.restoreState()
    doc.build(storia, onFirstPage=piede, onLaterPages=piede)
    return buf.getvalue()


# ------------------------------------------------------------------ CSV
def tabelle_csv(ris):
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
                righe.append({"analisi": a, "portafoglio": k, "mese": j, "p5": b[0][j], "p25": b[1][j], "p50": b[2][j], "p75": b[3][j], "p95": b[4][j]})
    out["fan_chart_percentili.csv"] = pd.DataFrame(righe)
    righe = []
    for a, s in ris["sim"].items():
        for k in s["nomi"]:
            righe.append({"analisi": a, "portafoglio": k, "vol_storica": ris["storico"][a]["stat"][k]["vol"], "vol_simulata": s["vol_sim"][k],
                          "max_drawdown_storico": ris["storico"][a]["stat"][k]["mdd"], "VaR95_1anno": s["var_es"].loc["VaR 95% 1 anno", k],
                          "ES95_1anno": s["var_es"].loc["Expected Shortfall 95% 1 anno", k],
                          "corr_media_titoli": ris["storico"][a]["corr_media"].get(k, np.nan)})
    out["altre_metriche.csv"] = pd.DataFrame(righe)
    out["rendimenti_attesi.csv"] = ris["rend_attesi"].T.rename_axis("portafoglio").reset_index()
    out["titoli.csv"] = ris["dati_info"].assign(beta=[ris["beta"].get(BENCH if t == ris["cfg"]["benchmark"]["ticker"] else t, np.nan) for t in ris["dati_info"].index]).reset_index()
    if ris["stress"]:
        out["stress_test.csv"] = pd.concat([df.assign(analisi=a) for a, df in ris["stress"].items()])
    if ris["idio"]:
        out["rischio_singolo_titolo.csv"] = pd.concat([df.T.assign(analisi=a, orizzonte_anni=h) for a, s in ris["idio"].items() for h, df in s["orizzonti"].items()]).rename_axis("portafoglio").reset_index()
    if ris["modelli"]:
        out["confronto_modelli.csv"] = pd.concat([df.T.assign(analisi=a, modello=m, orizzonte_anni=h) for a, mm in ris["modelli"].items()
                                                  for m, s in mm.items() for h, df in s["orizzonti"].items()]).rename_axis("portafoglio").reset_index()
    return out


def salva(ris, cartella, pdf=True, log=print):
    """Scrive report.html, report.pdf e i CSV in `cartella`. Ritorna il percorso dell'HTML."""
    os.makedirs(cartella, exist_ok=True)
    S = sezioni(ris)
    f = os.path.join(cartella, "report.html")
    open(f, "w", encoding="utf-8").write(html_report(ris, S))
    if pdf:
        open(os.path.join(cartella, "report.pdf"), "wb").write(pdf_report(ris, S))
    dcsv = os.path.join(cartella, "dati_csv")
    os.makedirs(dcsv, exist_ok=True)
    for nome, df in tabelle_csv(ris).items():
        df.to_csv(os.path.join(dcsv, nome), index=False, sep=";", decimal=",", encoding="utf-8-sig")
    from configurazione import in_yaml
    open(os.path.join(cartella, "configurazione_usata.yaml"), "w", encoding="utf-8").write(in_yaml(ris["cfg"]))
    return f
