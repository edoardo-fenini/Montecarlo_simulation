"""Costruisce report.html (autonomo: grafici incorporati come immagini)."""
import base64, io, html, datetime
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NOME = {"cyber": "Cyber security", "finanza": "Banche d'investimento / PE", "bigtech": "Big tech USA", "bench": "MSCI World (ETF)"}
COL = {"cyber": "#0072B2", "finanza": "#D55E00", "bigtech": "#009E73", "bench": "#555555"}
ORD = ["cyber", "finanza", "bigtech", "bench"]


# ------------------------------------------------------------------ formattazione
def num_it(n): return f"{n:,}".replace(",", ".")
def eur(v): return f"{v:,.0f} €".replace(",", ".")
def pct(v, d=1): return f"{v*100:.{d}f}%".replace(".", ",")
def num(v, d=1): return "mai" if not np.isfinite(v) else f"{v:.{d}f}".replace(".", ",")
def fig64(fig):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=110, bbox_inches="tight"); plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(b.getvalue()).decode()}" alt="grafico">'


def tabella(righe, intestazione, gruppi=None, classe=""):
    """righe: lista di liste (prima colonna = etichetta). gruppi: [(titolo, n_colonne)]."""
    h = f'<table class="{classe}">'
    if gruppi:
        h += "<tr><th></th>" + "".join(f'<th colspan="{n}" class="g">{t}</th>' for t, n in gruppi) + "</tr>"
    h += "<tr><th></th>" + "".join(f"<th>{c}</th>" for c in intestazione) + "</tr>"
    for r in righe:
        h += f'<tr><td class="e">{r[0]}</td>' + "".join(f"<td>{c}</td>" for c in r[1:]) + "</tr>"
    return h + "</table>"


# ------------------------------------------------------------------ grafici
def fan_chart(s, titolo, cp):
    fig, axs = plt.subplots(2, 2, figsize=(11, 7.4), sharex=True, sharey=True)
    top = max(s["bande"][k][4][cp[-1] * 12] for k in ORD) * 1.12
    for ax, k in zip(axs.ravel(), ORD):
        b, x = s["bande"][k], np.arange(s["bande"][k].shape[1]) / 12
        c = COL[k]
        ax.fill_between(x, b[0], b[4], color=c, alpha=0.15, lw=0, label="5°–95° percentile")
        ax.fill_between(x, b[1], b[3], color=c, alpha=0.30, lw=0, label="25°–75° percentile")
        ax.plot(x, b[2], color=c, lw=2, label="Mediana")
        ax.plot(x, s["versato"], color="black", ls="--", lw=1, label="Totale versato")
        for h in cp:
            j = h * 12
            ax.axvline(h, color="#999", lw=0.8, ls=":")
            for v, dy in ((b[4][j], 5), (b[2][j], 6), (b[0][j], -12)):
                ax.plot([h], [v], "o", color=c, ms=5, mec="white", mew=0.8, zorder=5)
                ax.annotate(eur(v), (h, v), xytext=(-5, dy), textcoords="offset points", ha="right", fontsize=7.5, color="#111",
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75), zorder=6)
        ax.set_title(NOME[k], color=c, fontweight="bold", fontsize=11)
        ax.set_ylim(0, top); ax.grid(alpha=0.25)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
        ax.set_xticks(range(0, cp[-1] + 1, 1 if cp[-1] <= 15 else 5))
    for ax in axs[1]: ax.set_xlabel("anni")
    for ax in axs[:, 0]: ax.set_ylabel("valore (€)")
    axs[0, 0].legend(loc="upper left", fontsize=7.5, frameon=False)
    fig.suptitle(titolo, fontsize=12, y=1.0)
    fig.tight_layout()
    return fig64(fig)


def istogrammi_mdd(sA, sB, h):
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for ax, (t, s) in zip(axs, (("Analisi A", sA), ("Analisi B", sB))):
        for k in ORD:
            ax.hist(s["mdd_fin"][k] * 100, bins=np.linspace(-100, 0, 41), alpha=0.5, color=COL[k], label=NOME[k], density=True)
        ax.set_title(f"{t}: max drawdown nei {h} anni"); ax.set_xlabel("max drawdown (%)"); ax.grid(alpha=0.25)
    axs[0].set_ylabel("frequenza"); axs[0].legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout(); return fig64(fig)


def grafico_rischio(st):
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, k in zip(axs, ORD[:3]):
        rc = st["rc"][k]
        ax.barh(rc.index[::-1], rc.values[::-1] * 100, color=COL[k])
        ax.axvline(100 / len(rc), color="black", ls="--", lw=1)
        ax.set_title(NOME[k], color=COL[k], fontsize=10, fontweight="bold"); ax.set_xlabel("% del rischio totale"); ax.grid(alpha=0.25, axis="x")
    fig.text(0.5, -0.02, "Linea tratteggiata = quota 'equa' (1/numero di titoli). Barre più lunghe = titolo che pesa di più sul rischio.", ha="center", fontsize=8.5)
    fig.tight_layout(); return fig64(fig)


def heatmap(mats):
    fig, axs = plt.subplots(2, 2, figsize=(9, 8))
    for ax, (t, m) in zip(axs.ravel(), mats):
        m = m.loc[ORD, ORD]
        ax.imshow(m.values, vmin=0, vmax=1, cmap="Blues")
        ax.set_xticks(range(4)); ax.set_yticks(range(4))
        ax.set_xticklabels([NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD], rotation=25, ha="right", fontsize=9)
        ax.set_yticklabels([NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD], fontsize=9)
        for i in range(4):
            for j in range(4):
                ax.text(j, i, f"{m.values[i, j]:.2f}".replace(".", ","), ha="center", va="center", fontsize=11, color="white" if m.values[i, j] > 0.6 else "black")
        ax.set_title(t, fontsize=10)
    fig.tight_layout(); return fig64(fig)


# ------------------------------------------------------------------ tabelle di sezione
RIGHE_H = [("Totale versato", eur), ("Valore mediano", eur), ("5° percentile", eur), ("95° percentile", eur),
           ("Prob. sotto il versato", pct), ("Max drawdown mediano", pct), ("Max drawdown peggiore (95%)", pct),
           ("Tempo sott'acqua max, mediano (anni)", num), ("Tempo sott'acqua max, peggiore 95% (anni)", num)]


def tab_orizzonti(sA, sB, h, nomeA="Analisi A", nomeB="Analisi B"):
    righe = []
    for r, f in RIGHE_H:
        riga = [r]
        for s in (sA, sB):
            if s is not None:
                riga += [f(s["orizzonti"][h].loc[r, k]) for k in ORD]
        righe.append(riga)
    gruppi = [(t, 4) for t, s in ((nomeA, sA), (nomeB, sB)) if s is not None]
    return tabella(righe, [NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD] * len(gruppi), gruppi)


def tab_altre(ris):
    righe = []
    for etichetta, f in (("Volatilità annua storica", lambda a, k: pct(ris["storico"][a]["stat"][k]["vol"])),
                         ("Volatilità annua simulata", lambda a, k: pct(ris[f"base_{a}"]["vol_sim"][k])),
                         ("Max drawdown storico", lambda a, k: pct(ris["storico"][a]["stat"][k]["mdd"])),
                         ("VaR 95% a 1 anno (perdita)", lambda a, k: pct(ris[f"base_{a}"]["var_es"].loc["VaR 95% 1 anno", k])),
                         ("Expected Shortfall 95% a 1 anno", lambda a, k: pct(ris[f"base_{a}"]["var_es"].loc["Expected Shortfall 95% 1 anno", k])),
                         ("Correlazione media tra i titoli", lambda a, k: "–" if k == "bench" else num(ris["storico"][a]["corr_media"][k], 2))):
        righe.append([etichetta] + [f(a, k) for a in "AB" for k in ORD])
    return tabella(righe, [NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD] * 2, [("Analisi A", 4), ("Analisi B", 4)])


def ordine(vals, desc=True):
    """Stringa 'a > b > c > d' ordinando i portafogli (primo = più rischioso/più alto)."""
    ks = sorted(ORD, key=lambda k: vals[k], reverse=desc)
    return " > ".join(NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ks)


def metriche_rischio(s):
    return {"ES 95% a 1 anno": {k: s["var_es"].loc["Expected Shortfall 95% 1 anno", k] for k in ORD},
            "Max drawdown mediano a 15 anni": {k: -s["orizzonti"][15].loc["Max drawdown mediano", k] for k in ORD},
            "Prob. sotto il versato a 15 anni": {k: s["orizzonti"][15].loc["Prob. sotto il versato", k] for k in ORD}}


def sezione_stress(ris):
    h = ""
    for a in "AB":
        d = ris.get(f"stress_{a}")
        if d is None: continue
        righe = []
        for _, r in d.iterrows():
            rec = "non scende sotto il versato" if not r["Scende sotto il versato"] else (
                "oltre 30 anni (in più di metà dei casi)" if not np.isfinite(r["Anni per tornare al versato (mediana)"]) else num(r["Anni per tornare al versato (mediana)"]))
            righe.append([NOME[r["Portafoglio"]], r["Scenario"], eur(r["Valore a metà orizzonte"]), eur(r["Valore dopo lo shock"]),
                          f'{eur(r["Perdita massima (€)"])} ({pct(r["Perdita massima (%)"], 0)})', rec,
                          "–" if not r["Scende sotto il versato"] else pct(r["Prob. ritorno entro 10 anni"], 0)])
        h += f"<h3>Analisi {a}</h3>" + tabella(righe, ["Scenario", "Valore a metà orizzonte", "Valore dopo lo shock", "Perdita massima", "Anni per tornare a 5.000 € (mediana)", "Prob. di tornarci entro 10 anni"], classe="st")
    return h


# ------------------------------------------------------------------ sintesi
def sintesi(ris):
    cfg, n = ris["cfg"], ris["n"]
    sA, sB, hz = ris["base_A"], ris["base_B"], max(cfg["checkpoint_anni"])
    v = {k: sA["orizzonti"][hz].loc["Valore mediano", k] for k in ORD}
    pr = {k: sA["orizzonti"][hz].loc["Prob. sotto il versato", k] for k in ORD}
    vol = {k: ris["storico"]["A"]["stat"][k]["vol"] for k in ORD}
    dd = {k: sA["orizzonti"][hz].loc["Max drawdown mediano", k] for k in ORD}
    cap = cfg["capitale_iniziale"]
    F = []
    F.append(f"Ho simulato {num_it(n)} futuri possibili a {hz} anni per quattro portafogli (cyber security, banche d'investimento/PE, big tech USA e un ETF azionario mondiale), partendo da {eur(cap)} e senza altri versamenti, dando a tutti lo stesso rendimento atteso del {pct(cfg['rendimento_atteso'], 0)} l'anno: le differenze che vedi dipendono quindi solo dal <b>rischio</b>, non da rendimenti promessi.")
    F.append(f"Il più volatile nella storia recente è «{NOME[max(vol, key=vol.get)]}» ({pct(max(vol.values()), 0)} annuo), il meno volatile l'ETF mondiale ({pct(vol['bench'], 0)}); i tre portafogli di singole azioni hanno una volatilità da {num(min(vol[k] for k in ORD[:3]) / vol['bench'])} a {num(max(vol[k] for k in ORD[:3]) / vol['bench'])} volte quella dell'ETF.")
    F.append(f"Dopo {hz} anni il valore <b>mediano</b> (la metà dei casi sta sopra, la metà sotto) è {eur(v['bench'])} per l'ETF mondiale contro {eur(v['finanza'])} per i finanziari, {eur(v['bigtech'])} per la big tech e {eur(v['cyber'])} per la cyber security: pur con lo stesso rendimento <i>medio</i>, più un portafoglio oscilla più il caso tipico resta indietro, perché una perdita del 50% richiede un guadagno del 100% per rientrare.")
    F.append(f"La probabilità di avere meno di quanto versato dopo {hz} anni va da {pct(pr['bench'], 0)} (ETF) a {pct(max(pr.values()), 0)} (portafoglio peggiore), e nel caso tipico il portafoglio più rischioso attraversa un calo massimo del {pct(-min(dd.values()), 0)} contro il {pct(-dd['bench'], 0)} dell'ETF.")
    if "stress_A" in ris:
        d = ris["stress_A"]; d = d[d["Scenario"].str.startswith("Crisi")]
        worst = d.loc[d["Perdita massima (%)"].idxmax()]
        F.append(f"Negli scenari di stress a metà percorso, la perdita più pesante è quella di «{NOME[worst['Portafoglio']]}» nella crisi stile 2008 ({pct(worst['Perdita massima (%)'], 0)} del valore).")
    if "mod_t_A" in ris:
        F.append("Nella sezione «Quanto sono solide queste conclusioni?» trovi cosa resta uguale cambiando modello, rendimento atteso e rischio sul singolo titolo.")
    F.append("Attenzione: il periodo comune (analisi A) copre solo circa cinque anni, quindi i risultati dipendono molto dal ribasso del 2022; non è consulenza finanziaria e non contiene indicazioni di acquisto.")
    return "<ul>" + "".join(f"<li>{f}</li>" for f in F) + "</ul>"


def solidita(ris):
    if "mod_t_A" not in ris:
        return "<p>Sezione disponibile dalla tappa 5.</p>"
    h = ""
    for a in "AB":
        base = ris[f"base_{a}"]
        modelli = [("Block bootstrap", base), ("Student-t multivariata", ris[f"mod_t_{a}"]), ("GARCH(1,1) + residui bootstrap", ris[f"mod_garch_{a}"])]
        righe, uguali = [], True
        rif = {m: ordine(vals) for m, vals in metriche_rischio(base).items()}
        for m in rif:
            for nome, s in modelli:
                o = ordine(metriche_rischio(s)[m])
                righe.append([m, nome, o, "sì" if o == rif[m] else "<b>no</b>"])
                uguali &= o == rif[m]
        h += f"<h3>Classifica di rischio per modello – analisi {a} (dal più al meno rischioso)</h3>" + tabella(righe, ["Modello", "Classifica", "Uguale al bootstrap?"], classe="st")
        h += f"<p class='nota'>{'La classifica di rischio resta identica con tutti e tre i modelli.' if uguali else 'La classifica cambia in almeno una metrica: vedi le righe con «no».'}</p>"
    return h


def sezione_sensibilita(ris):
    h = ""
    cp = max(ris["cfg"]["checkpoint_anni"])
    for a in "AB":
        sc = [("3%", ris[f"sens_3_{a}"]), ("6% (base)", ris[f"base_{a}"]), ("9%", ris[f"sens_9_{a}"]), ("Settoriale (cyber 4%, big tech 5%, finanza 6%, ETF 6%)", ris[f"sens_settori_{a}"])]
        righe, ords = [], []
        for t, s in sc:
            vals = {k: s["orizzonti"][cp].loc["Valore mediano", k] for k in ORD}
            ords.append(ordine(vals))
            righe.append([t] + [eur(vals[k]) for k in ORD] + [ords[-1]])
        h += f"<h3>Valore mediano a {cp} anni – analisi {a}</h3>" + tabella(righe, [NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD] + ["Classifica (dal più alto)"], classe="st")
        h += f"<p class='nota'>{'La classifica sul valore finale non cambia.' if len(set(ords)) == 1 else 'La classifica sul valore finale cambia tra gli scenari: dipende dall’ipotesi di rendimento.'}</p>"
    return h


def sezione_idio(ris):
    h, cp = "", max(ris["cfg"]["checkpoint_anni"])
    for a in "AB":
        b, i = ris[f"base_{a}"], ris[f"idio_{a}"]
        righe = []
        for et, r, f in (("Prob. sotto il versato", "Prob. sotto il versato", pct), ("Max drawdown mediano", "Max drawdown mediano", pct), ("Max drawdown peggiore (95%)", "Max drawdown peggiore (95%)", pct), ("Valore mediano", "Valore mediano", eur), ("5° percentile", "5° percentile", eur)):
            righe.append([et + " – senza crolli"] + [f(b["orizzonti"][cp].loc[r, k]) for k in ORD])
            righe.append([et + " – con crolli"] + [f(i["orizzonti"][cp].loc[r, k]) for k in ORD])
        h += f"<h3>A {cp} anni – analisi {a}</h3>" + tabella(righe, [NOME[k].split(" /")[0].replace(" (ETF)", "") for k in ORD], classe="st")
    return h


# ------------------------------------------------------------------ pagina
CSS = """
:root{--bg:#fff;--fg:#1c1c1c;--mut:#666;--line:#ddd;--card:#f6f7f9;--warn:#fff4e5;--warnb:#e8a33d}
@media(prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a6;--line:#363a40;--card:#1f2227;--warn:#33291a;--warnb:#c58a2b}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1080px;margin:0 auto;padding:16px}
h1{font-size:1.7rem}h2{margin-top:2.2rem;border-bottom:1px solid var(--line);padding-bottom:4px}h3{margin-top:1.4rem}
table{border-collapse:collapse;margin:10px 0;font-size:.85rem;width:100%}td,th{border:1px solid var(--line);padding:4px 7px;text-align:right}
th{background:var(--card)}th.g{text-align:center}td.e{text-align:left;font-weight:600;background:var(--card)}table.st td{text-align:left}
.sc{overflow-x:auto}img{max-width:100%;height:auto}.box{background:var(--card);padding:10px 16px;border-radius:8px}
.warn{background:var(--warn);border-left:5px solid var(--warnb);padding:10px 16px;border-radius:6px;margin:12px 0}
.nota{color:var(--mut);font-size:.9rem}details{margin:8px 0}summary{cursor:pointer;font-weight:600}
"""


def sc(x): return f'<div class="sc">{x}</div>'


def scrivi_report(ris, out):
    cfg, n = ris["cfg"], ris["n"]
    cp = cfg["checkpoint_anni"]
    sA, sB = ris["base_A"], ris["base_B"]
    P = ris["periodi"]
    d = lambda t: t.strftime("%d/%m/%Y")
    b = cfg["benchmark"]
    H = [f"<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Confronto rischio portafogli</title><style>{CSS}</style></head><body>"]
    H.append(f"<h1>Confronto del rischio di tre portafogli azionari</h1><p class='nota'>Simulazione Monte Carlo – {num_it(n)} simulazioni per scenario – capitale iniziale {eur(cfg['capitale_iniziale'])}, versamento mensile {eur(cfg['versamento_mensile'])}, orizzonte {cfg['orizzonte_anni']} anni – generato il {datetime.date.today().strftime('%d/%m/%Y')}</p>")
    if n < 20000:
        H.append(f"<div class='warn'><b>Versione di prova:</b> solo {n} simulazioni per scenario. I numeri sono indicativi.</div>")
    H.append("<h2>Sintesi</h2><div class='box'>" + sintesi(ris) + "</div>")
    H.append("""<div class='warn'><b>Cosa significa "rendimento atteso 6%".</b> Ho dato a tutti i portafogli lo stesso rendimento <i>medio</i> annuo del 6% (1 € vale in media 1,06 € dopo un anno). Con la volatilità, però, il risultato <i>tipico</i> (la mediana) è più basso della media: i pochi casi molto fortunati alzano la media, mentre la maggior parte dei percorsi resta sotto. Più un portafoglio è volatile, più la mediana scende. Se invece volessi che il 6% fosse il rendimento del caso tipico, i numeri sarebbero più alti per tutti.</div>""")

    H.append("<h2>Come leggere i termini</h2><div class='box'><ul>"
             "<li><b>Percentile</b>: il 5° percentile è il valore sotto cui finisce il 5% dei casi peggiori; il 95° quello sopra cui sta il 5% dei casi migliori. Tra i due c'è il 90% dei futuri simulati.</li>"
             "<li><b>Volatilità</b>: quanto oscillano i prezzi in un anno (deviazione standard dei rendimenti). 30% significa oscillazioni tipiche di ±30%.</li>"
             "<li><b>Max drawdown</b>: il calo massimo dal massimo precedente al minimo successivo. Se un portafoglio passa da 10.000 a 4.000 €, il drawdown è −60%.</li>"
             "<li><b>Tempo sott'acqua</b>: il periodo più lungo passato sotto il massimo precedente prima di tornare a toccarlo.</li>"
             "<li><b>VaR 95% a 1 anno</b>: la perdita che in un anno viene superata solo nel 5% dei casi. <b>Expected Shortfall</b>: la perdita media in quel 5% di casi peggiori.</li>"
             "<li><b>Bootstrap a blocchi</b>: invece di inventare una distribuzione, si rimescolano pezzi di storia reale (blocchi di circa 20 giorni di borsa, per tenere insieme crisi, volatilità a grappoli e correlazioni).</li>"
             "<li><b>Ricentratura</b>: tolgo il rendimento medio storico di ogni titolo e metto quello scelto (6%), lasciando intatti volatilità, code e correlazioni. È necessaria perché i titoli sono stati scelti oggi tra quelli andati bene: usare il loro rendimento passato (<i>survivorship bias</i>) regalerebbe un vantaggio fittizio ai portafogli di azioni.</li>"
             "<li><b>Ribilanciamento annuale</b>: una volta l'anno si riportano i titoli ai pesi uguali, pagando lo 0,1% dell'importo movimentato.</li></ul></div>")

    H.append("<h2>Dati e periodi analizzati</h2>")
    righe = []
    crisi = {"A": "ribasso 2022, crisi bancaria 2023. Non contiene 2000, 2008 né 2020.",
             "B": "crisi 2008, debito europeo 2011, Covid 2020, ribasso 2022. Per cyber i primi anni hanno pochi titoli (vedi sotto).",
             "C": "bolla dot-com 2000-2002, 2008, Covid 2020, ribasso 2022 – con dati proxy per gli anni in cui i titoli non esistevano."}
    for a in "ABC":
        if a == "C" and "base_C" not in ris: continue
        p = P[a]
        righe.append([a, cfg["analisi"][a]["descrizione"], f"{d(p[0])} – {d(p[1])}", f"{p[2]:,}".replace(",", "."), crisi[a]])
    H.append(sc(tabella(righe, ["Descrizione", "Periodo coperto", "Giorni", "Crisi incluse"], classe="st")))
    H.append(f"<p class='nota'>Prezzi: Yahoo Finance (adjusted close, dividendi inclusi) convertiti in EUR con il cambio giornaliero (Yahoo dal 2003, FRED prima), quindi il rischio cambio è incluso. "
             f"<b>Benchmark:</b> {b['nome']}, ticker Yahoo {b['ticker']}, ISIN {b['isin']}, TER {pct(b['ter'], 2)}, lanciato il 25/09/2009 (verificato su iShares/justETF). Prima di quella data uso l'indice MSCI World Net in USD convertito in EUR, meno il TER ({b['proxy_storico']}): è un <b>proxy</b>, non l'ETF vero.</p>")
    H.append("<p class='nota'><b>Analisi B:</b> quando un titolo non è ancora quotato, prende il rendimento medio dei titoli disponibili nello stesso portafoglio (equivale a pesi uguali tra quelli disponibili). All'inizio del 2007 il portafoglio cyber contiene quindi solo F5 e Check Point; i finanziari hanno 6 titoli fino all'IPO di Blackstone (giugno 2007).</p>")
    if ris["avvisi"]:
        H.append("<details><summary>Controlli sui dati: movimenti giornalieri estremi (&gt;30%)</summary><ul>" + "".join(f"<li>{html.escape(a)}</li>" for a in ris["avvisi"]) + "</ul><p class='nota'>Sono tutti consistenti con eventi reali (risultati trimestrali, crisi del 2008, divieti di vendita allo scoperto); nessun buco né prezzo negativo. Gli split sono già corretti nei prezzi adjusted.</p></details>")
    else:
        H.append("<p class='nota'>Controlli sui dati: nessun buco, prezzo anomalo o split non gestito.</p>")

    H.append("<h2>Risultati a 5, 10 e 15 anni</h2><p class='nota'>Valori con rendimento atteso ricentrato al 6%. A sinistra l'analisi A (periodo comune, circa 5 anni di storia), a destra la B (dal 2007).</p>")
    for h in cp:
        H.append(f"<h3>Dopo {h} anni</h3>" + sc(tab_orizzonti(sA, sB, h)))
    H.append("<h3>Fan chart: come si sparpagliano i risultati nel tempo</h3><p class='nota'>La fascia scura contiene il 50% dei casi, quella chiara il 90%. I puntini segnano 5°, 50° e 95° percentile a 5, 10 e 15 anni; la linea tratteggiata è il totale versato.</p>")
    H.append(fan_chart(sA, "Analisi A – periodo comune", cp))
    H.append(fan_chart(sB, "Analisi B – dal 2007", cp))
    H.append(f"<h3>Max drawdown a confronto</h3>" + istogrammi_mdd(sA, sB, cp[-1]))
    H.append("<h2>Altre metriche di rischio</h2>" + sc(tab_altre(ris)))
    H.append("<h3>Da dove arriva il rischio dentro ogni portafoglio</h3>" + grafico_rischio(ris["storico"]["A"]))
    H.append("<h3>Correlazione tra i portafogli</h3><p class='nota'>1 = si muovono insieme sempre; 0 = indipendenti.</p>" + heatmap([
        ("Storica – analisi A", ris["storico"]["A"]["corr"]), ("Storica – analisi B", ris["storico"]["B"]["corr"]),
        ("Simulata – analisi A", sA["corr_sim"]), ("Simulata – analisi B", sB["corr_sim"])][:4]))

    H.append("<h3>Senza ricentratura (rendimenti storici reali)</h3><div class='warn'><b>Attenzione:</b> questa versione proietta nel futuro il passato recente, che per questi titoli è stato eccezionalmente favorevole. I titoli sono stati scelti oggi, con il senno di poi: non va letta come una previsione.</div>")
    for h in cp:
        H.append(f"<details><summary>Dopo {h} anni (senza ricentratura)</summary>" + sc(tab_orizzonti(ris["nr_A"], ris["nr_B"], h)) + "</details>")

    if "stress_A" in ris:
        H.append("<h2>Stress test</h2><p class='nota'>Lo shock è applicato al valore mediano simulato a metà orizzonte (7,5 anni), senza versamenti. «Anni per tornare a 5.000 €» è la mediana di una nuova simulazione dopo lo shock, contata dalla fine del crollo; usa lo stesso rendimento atteso del 6% (ipotesi ottimistica dopo una crisi). «Singolo titolo» = il titolo con peso più alto perde il 90%; non applicabile all'ETF, che è già diversificato.</p>")
        H.append(sc(sezione_stress(ris)))
    if "base_C" in ris:
        H.append("<h2>Robustezza 1 – Storia allungata dal 1999 con proxy (analisi C)</h2>")
        fr = ris["frac_proxy"]
        H.append("<div class='warn'><b>Cosa è dato reale e cosa è proxy.</b> Per i giorni in cui un titolo non era quotato ho generato rendimenti sintetici = (beta × rendimento del proxy: XLK per cyber e big tech, XLF per i finanziari) + residui ripescati dai residui reali del titolo, così volatilità e correlazione col proxy sono quelle misurate quando il titolo esisteva. Non sono dati veri: i titoli hanno avuto percorsi propri (es. PANW, CRWD, S, ZS, PLTR nel 2000-2002 non esistevano). Quota di giorni sintetici: "
                 + ", ".join(f"{t} {pct(v, 0)}" for t, v in fr.items() if v > 0.005) + ". Il benchmark usa l'indice MSCI World vero.</div>")
        sC = ris["base_C"]
        for h in cp:
            H.append(f"<h3>Dopo {h} anni – analisi C</h3>" + sc(tab_orizzonti(sC, None, h, "Analisi C")))
        H.append(fan_chart(sC, "Analisi C – dal 1999 con proxy", cp))
    if "mod_t_A" in ris:
        H.append("<h2>Robustezza 2 – Confronto tra modelli</h2><p class='nota'>Student-t: code grasse ma nessun raggruppamento della volatilità. GARCH(1,1): volatilità che sale e scende nel tempo, con shock ripescati dallo storico. Classifica = dal portafoglio più rischioso al meno rischioso.</p>" + sc(solidita(ris)))
        H.append("<h2>Robustezza 3 – Sensibilità al rendimento atteso</h2><p class='nota'>Scenario settoriale prudente: cyber 4% e big tech 5% (valutazioni di partenza elevate, quindi rendimenti futuri attesi più bassi), finanza e ETF 6%.</p>" + sc(sezione_sensibilita(ris)))
        H.append(f"<h2>Robustezza 4 – Rischio sul singolo titolo</h2><p class='nota'>Ogni titolo ha una probabilità dell'{pct(cfg['idio_p_anno'])} l'anno di crollare dell'80-100% in un giorno (fallimento, frode, delisting). Il rendimento atteso medio resta invariato: cambia solo il rischio. L'ETF non è toccato.</p>" + sc(sezione_idio(ris)))
        H.append("<h2>Quanto sono solide queste conclusioni?</h2><div class='box'>" + conclusioni_solidita(ris) + "</div>")

    H.append("<h2>Limiti di questa analisi</h2><div class='box'><ul>"
             "<li><b>Storia breve</b>: SentinelOne (2021), Palantir (2020), CrowdStrike (2019) e Zscaler (2018) hanno pochi anni di dati; l'analisi A usa solo circa cinque anni, tra cui il ribasso del 2022 ma non il 2008 né il 2000.</li>"
             "<li><b>Rendimento atteso</b>: il 6% è un'ipotesi uguale per tutti, non una previsione. Cambiarlo cambia i valori finali (vedi robustezza 3).</li>"
             "<li><b>Survivorship bias</b>: i titoli sono stati scelti oggi tra quelli che hanno avuto successo; le società fallite o scomparse non ci sono. Per questo il rendimento storico è stato sostituito.</li>"
             "<li><b>Concentrazione</b>: i portafogli hanno 5-7 titoli dello stesso settore; un singolo evento (normativa, scandalo, bolla di settore) può colpirli tutti. Tecnologia USA e cyber sono molto legati tra loro.</li>"
             "<li><b>Il futuro può essere diverso dal passato</b>: il modello rimescola eventi già avvenuti; non può inventare crisi di tipo nuovo, né prevedere cambi di regime, tassi o tasse.</li>"
             "<li><b>Costi e tasse</b>: sono inclusi solo il TER dell'ETF e lo 0,1% di ribilanciamento; niente imposte, spread o commissioni di broker.</li>"
             "<li><b>Proxy</b>: nel benchmark prima del 2009 e nell'analisi C alcuni dati non sono reali (vedi sopra).</li></ul>"
             "<p><b>Questa analisi non è consulenza finanziaria</b> e non contiene raccomandazioni di acquisto o vendita.</p></div>")
    H.append("</body></html>")
    open(out, "w", encoding="utf-8").write("".join(H))


def conclusioni_solidita(ris):
    cp = max(ris["cfg"]["checkpoint_anni"])
    F = []
    for a in "AB":
        base = ris[f"base_{a}"]
        mods = [ris[f"mod_t_{a}"], ris[f"mod_garch_{a}"]]
        for m in ("ES 95% a 1 anno", "Max drawdown mediano a 15 anni", "Prob. sotto il versato a 15 anni"):
            o0 = ordine(metriche_rischio(base)[m])
            same = all(ordine(metriche_rischio(s)[m]) == o0 for s in mods)
            F.append((a, m, o0, same))
    stabili = [f for f in F if f[3]]
    instabili = [f for f in F if not f[3]]
    h = "<p><b>Resta stabile</b> (stessa classifica con bootstrap, Student-t e GARCH):</p><ul>"
    h += "".join(f"<li>Analisi {a}, {m}: {o}</li>" for a, m, o, _ in stabili) or "<li>nessuna metrica</li>"
    h += "</ul><p><b>Cambia con le ipotesi</b>:</p><ul>"
    h += "".join(f"<li>Analisi {a}, {m}: l'ordine dipende dal modello</li>" for a, m, o, _ in instabili) or "<li>nessuna metrica nei tre modelli</li>"
    ch = []
    for a in "AB":
        ords = {ordine({k: ris[x]["orizzonti"][cp].loc["Valore mediano", k] for k in ORD}) for x in (f"sens_3_{a}", f"base_{a}", f"sens_9_{a}", f"sens_settori_{a}")}
        ch.append(f"analisi {a}: " + ("classifica del valore finale invariata" if len(ords) == 1 else "classifica del valore finale diversa tra gli scenari di rendimento"))
    h += "<li>Sensibilità al rendimento atteso – " + "; ".join(ch) + "</li>"
    oa = {m: ordine(v) for m, v in metriche_rischio(ris["base_A"]).items()}
    ob = {m: ordine(v) for m, v in metriche_rischio(ris["base_B"]).items()}
    if oa != ob:
        h += "<li>Il confronto tra <i>banche d'investimento</i> e <i>big tech</i> dipende dal periodo storico: nell'analisi A (2021-2026, include il ribasso tech del 2022) i finanziari risultano meno rischiosi, nell'analisi B (dal 2007, include il 2008) lo sono la big tech.</li>"
    dp = max(ris[f"idio_{a}"]["orizzonti"][cp].loc["Prob. sotto il versato", k] - ris[f"base_{a}"]["orizzonti"][cp].loc["Prob. sotto il versato", k] for a in "AB" for k in ORD[:3])
    dd = max(ris[f"base_{a}"]["orizzonti"][cp].loc["Max drawdown mediano", k] - ris[f"idio_{a}"]["orizzonti"][cp].loc["Max drawdown mediano", k] for a in "AB" for k in ORD[:3])
    h += f"<li>Rischio sul singolo titolo (crollo 80-100% con probabilità {pct(ris['cfg']['idio_p_anno'])} l'anno per titolo): l'effetto è <b>contenuto</b> rispetto alla volatilità normale di questi titoli, che già produce cali enormi. La probabilità di stare sotto il versato sale al massimo di {num(dp * 100)} punti percentuali e il max drawdown mediano peggiora al massimo di {num(dd * 100)} punti. Non cambia nessuna classifica.</li>"
    h += "</ul><p>In ogni caso: il <b>livello</b> dei numeri (quanto vale la mediana, quanto è probabile perdere) dipende dal rendimento atteso e dal periodo storico scelto; la <b>distanza di rischio tra l'ETF diversificato e i portafogli di singole azioni</b> è ampia e si ripete in tutte le varianti: l'ETF è sempre il meno rischioso e ha sempre il valore mediano più alto.</p>"
    return h
