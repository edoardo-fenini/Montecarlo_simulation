"""Sezione «Da dove viene il rischio» del report (v1.5): scomposizione del rischio con il modello a fattori.

Si calcola dalle regressioni (non dalla simulazione): disponibile con entrambi i modelli di simulazione."""

from __future__ import annotations

import numpy as np
import pandas as pd

import fattori as FA

COLORI_GRUPPI = {
    "Mercato": "#1F3A5F",
    "Regioni": "#0072B2",
    "Settori": "#D55E00",
    "Stile": "#009E73",
    "Tassi e valute": "#E69F00",
    "Rischio specifico": "#999999",
}
FRASE = {  # come si chiama il fattore dentro una frase
    "Mercato mondiale": "il mercato azionario in generale",
    "USA": "l'area USA",
    "Europa": "l'area Europa",
    "Giappone": "l'area Giappone",
    "Emergenti": "i mercati emergenti",
    "Tecnologia": "il settore tecnologico",
    "Finanziari": "il settore finanziario",
    "Salute": "il settore salute",
    "Energia": "il settore energia",
    "Industriali": "il settore industriale",
    "Consumi ciclici": "i consumi ciclici",
    "Consumi difensivi": "i consumi difensivi",
    "Growth contro value": "lo stile growth",
    "Piccole imprese": "le piccole imprese",
    "Momentum": "lo stile momentum",
    "Qualità": "lo stile qualità",
    "Obbligazioni lunghe": "i tassi di interesse (obbligazioni lunghe)",
    "Dollaro contro euro": "il cambio dollaro/euro",
}


def _p(v, d=0):
    return f"{v * 100:.{d}f}%".replace(".", ",")


def _n(v, d=2):
    return f"{v:+.{d}f}".replace(".", ",").replace("-", "−")


def _tab(intest, righe):
    return ("tab", {"intest": list(intest)[1:], "righe": righe, "gruppi": None, "sx": True})  # la prima colonna è l'etichetta di riga


def frase_fattore(nome: str, segno: float = 1.0) -> str:
    if nome == "Growth contro value" and segno < 0:
        return "lo stile value"
    return FRASE.get(nome, f"il fattore «{nome}»")


def grafico_barre(ris: dict) -> bytes:
    import matplotlib.pyplot as plt

    import report as RP

    sc = ris["fattori"]["scomposizione"]
    nomi = [k for k in ris["nomi"] if k in sc]
    fig, ax = plt.subplots(figsize=(max(6.5, 1.5 * len(nomi) + 3), 4.2))
    pos0 = np.zeros(len(nomi))
    neg0 = np.zeros(len(nomi))
    for g, col in COLORI_GRUPPI.items():
        v = np.array([sc[k]["quote"].get(g, 0.0) for k in nomi]) * 100
        base = np.where(v >= 0, pos0, neg0)
        ax.bar(range(len(nomi)), v, bottom=base, color=col, label=g, width=0.6)
        for i, x in enumerate(v):
            if abs(x) >= 6:
                ax.text(i, base[i] + x / 2, f"{x:.0f}%", ha="center", va="center", fontsize=8, color="white")
        pos0 += np.where(v >= 0, v, 0)
        neg0 += np.where(v < 0, v, 0)
    ax.set_xticks(range(len(nomi)), [RP.corto(k, 18) for k in nomi], fontsize=9)
    ax.set_ylabel("% del rischio (varianza)")
    ax.axhline(0, color="black", lw=0.6)
    ax.grid(alpha=0.25, axis="y")
    ax.legend(ncols=3, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
    return RP.png(fig)


def _fattori_principali(sc: dict, escludi_mercato: set, k: int = 2) -> list[tuple[str, float]]:
    """I fattori (non di mercato) che contribuiscono di più al rischio, con la quota."""
    c = [(n, v) for n, v in sc["contributi"].items() if n not in escludi_mercato]
    return sorted(c, key=lambda x: -abs(x[1]))[:k]


def somiglianza(sc_a: dict, sc_b: dict, F: pd.DataFrame, stima: FA.Stima) -> float:
    """Correlazione tra i due portafogli dovuta ai soli fattori (parte comune)."""
    S = np.atleast_2d(np.cov(F.values.T)) * 252
    a, b = sc_a["esposizioni"].values, sc_b["esposizioni"].values
    va, vb = a @ S @ a, b @ S @ b
    return float(a @ S @ b / np.sqrt(va * vb))


def sintesi_testo(ris: dict) -> list[str]:
    f = ris["fattori"]
    sc, conf = f["scomposizione"], f["conf"]
    mercati = {x["nome"] for x in conf["fattori"] if x["gruppo"] == "mercato"}
    righe = []
    nomi = [k for k in ris["nomi"] if k in sc]
    for k in nomi:
        q = sc[k]["quote"]
        top = _fattori_principali(sc[k], mercati, 2)
        top = [(n, v) for n, v in top if v > 0.03]
        parti = ", ".join(f"{_p(v)} {frase_fattore(n, sc[k]['esposizioni'][n])}" for n, v in top)
        t = f"<b>{k}</b>: il {_p(q['Mercato'])} del rischio viene dal mercato nel suo complesso e il {_p(q['Rischio specifico'])} dai singoli titoli"
        t += f"; tra le altre scommesse pesano {parti}." if parti else "."
        righe.append(t)
    propri = [k for k in nomi if k != ris["bench_nome"]]  # il benchmark non è una «scommessa» da confrontare
    for i, a in enumerate(propri):
        for b in propri[i + 1 :]:
            s = somiglianza(sc[a], sc[b], f["F"], f["stima"])
            if s >= 0.85:
                ta = _fattori_principali(sc[a], mercati, 2)
                comuni = " e ".join(frase_fattore(n, sc[a]["esposizioni"][n]) for n, v in ta if v > 0.03)
                quota = sum(v for _, v in ta if v > 0) + sc[a]["quote"]["Mercato"]
                righe.append(
                    f"Il {_p(quota)} del rischio del portafoglio <b>{a}</b> viene dal mercato"
                    + (f", da {comuni}" if comuni else "")
                    + f": è in gran parte la stessa scommessa del portafoglio <b>{b}</b> (somiglianza {str(round(s, 2)).replace('.', ',')} su 1). "
                    "Averli entrambi diversifica meno di quanto sembri."
                )
    return righe


def descrizione_esposizioni(sc: dict, conf: dict) -> str:
    e = sc["esposizioni"]
    mercati = [x["nome"] for x in conf["fattori"] if x["gruppo"] == "mercato"]
    parti = [f"beta al mercato {_n(float(e[mercati[0]]), 1).lstrip('+')}"]
    altri = sorted((n for n in e.index if n not in mercati), key=lambda n: -abs(e[n]))
    for n in altri[:3]:
        if abs(e[n]) >= 0.15:
            parti.append(f"{frase_fattore(n, e[n])} ({_n(float(e[n]), 2)})" if e[n] > 0 or n != "Growth contro value" else f"{frase_fattore(n, e[n])} ({_n(float(-e[n]), 2)})")
    return "; ".join(parti)


def blocchi(ris: dict) -> list:
    f = ris.get("fattori")
    if not f:
        return []
    sc, stima, conf, info = f["scomposizione"], f["stima"], f["conf"], f["info"]
    nomi = [k for k in ris["nomi"] if k in sc]
    B = [
        (
            "p",
            "Ogni titolo è scomposto in <b>esposizioni a fattori comuni</b> (mercato, regioni, settori, stile, tassi e valute) più una "
            "<b>parte specifica</b> del titolo. Qui si vede quanta parte del rischio di ogni portafoglio viene da ciascun gruppo. "
            "È calcolato dalle regressioni sulla storia dei titoli, quindi è disponibile anche con il modello di simulazione «storico».",
        ),
        ("h3", "Da dove viene il rischio di ogni portafoglio"),
        ("img", grafico_barre(ris)),
        ("didascalia", "Ogni barra è il 100% del rischio (varianza) del portafoglio, diviso per gruppo di fattori. Più è grande «Rischio specifico», più il portafoglio è diversificato; più sono grandi gli altri gruppi, più dipende da scommesse comuni."),
        ("box", sintesi_testo(ris)),
        ("h3", "Quota del rischio per gruppo"),
        _tab(["Gruppo"] + nomi, [[g] + [_p(sc[k]["quote"].get(g, 0.0), 1) for k in nomi] for g in COLORI_GRUPPI]),
        ("h3", "Esposizioni principali"),
        ("box", [f"<b>{k}</b>: {descrizione_esposizioni(sc[k], conf)}." for k in nomi]),
    ]
    fatt_nomi = list(stima.nomi_fattori)
    B.append(("h3", "Esposizione di ogni portafoglio a tutti i fattori"))
    B.append(_tab(["Fattore", "Gruppo"] + nomi, [[n, info.loc[n, "gruppo"]] + [_n(float(sc[k]["esposizioni"][n])) for k in nomi] for n in fatt_nomi]))
    B.append(("nota", "Mercato: 1,00 = si muove come il mercato mondiale. Regioni, settori e stile sono scostamenti rispetto al mercato (o a S&P 500): +0,30 sul settore tecnologico = come il mercato più 0,30 volte la differenza tra tecnologia e mercato. «Growth contro value» positivo = growth, negativo = value."))
    # R² dei titoli
    B.append(("h3", "Quanto i fattori spiegano ogni titolo"))
    soglia = float(conf["r2_minimo_avviso"])
    tit = [t for t in stima.beta.index]
    righe = []
    for t in tit:
        r2 = stima.r2.get(t, np.nan)
        flag = " ⚠" if pd.notna(r2) and r2 < soglia and t != "BENCH" else ""
        righe.append([ "Benchmark" if t == "BENCH" else t, "–" if pd.isna(r2) else _p(r2) + flag, _p(stima.vol[t]), _p(stima.vol_specifica[t]), str(int(stima.n_sett[t]))])
    B.append(_tab(["Titolo", "R² (quota di rischio spiegata)", "Volatilità annua", "di cui specifica", "Settimane usate"], righe))
    medio = float(stima.r2.drop("BENCH", errors="ignore").mean())
    B.append(("nota", f"R² medio dei titoli: {_p(medio)}. Un R² basso non è un errore: vuol dire che il titolo si muove soprattutto per ragioni sue."))
    for a in f["avvisi_r2"]:
        B.append(("warn", a))
    for n in stima.note:
        B.append(("warn", n))
    cop = f.get("copertura_residui") or {}
    if f["conf"].get("residui_congiunti", True) and cop:
        corte = {t: v for t, v in cop.items() if v < 0.9}
        B.append(("nota", "Residui: nella simulazione i residui di tutti i titoli sono pescati dalle stesse date dei fattori, così nelle crisi i titoli dello stesso settore si muovono insieme come è successo davvero."))
        if corte:
            B.append(("nota", "Per i titoli senza residui in quelle date (non quotavano ancora) il residuo è ripescato dalla loro storia: " + ", ".join(f"{t} ({_p(v, 0)} dei giorni con residuo vero)" for t, v in corte.items()) + "."))
    for t, esc in stima.fattori_esclusi.items():
        B.append(("nota", f"{t}: storia troppo breve per usare {', '.join(esc)}; questi fattori non sono stati usati per questo titolo."))
    # fattori
    B.append(("h3", "I fattori usati"))
    B.append(_tab(["Fattore", "Gruppo", "Costruzione", "Primo dato"], [[n, r["gruppo"], r["ticker"], r["inizio"].strftime("%d/%m/%Y")] for n, r in info.iterrows()]))
    tardi = [n for n, r in info.iterrows() if pd.Timestamp(r["inizio"]) > pd.Timestamp(conf["inizio_storia"]) + pd.Timedelta(days=45)]
    if tardi:
        B.append(("nota", f"I fattori {', '.join(tardi)} nascono dopo l'inizio della storia ({pd.Timestamp(conf['inizio_storia']):%d/%m/%Y}): prima valgono 0 nelle simulazioni (nessuna esposizione nota) e non entrano nelle regressioni."))
    B.append(("nota", "La regressione usa rendimenti settimanali in euro, con penalità ridge (esposizioni più prudenti quando la storia è breve o i fattori si somigliano; il fattore mercato non è penalizzato)."))
    return B


# ---------------------------------------------------------------- validazione del modello (backtest del VaR)
SEMAFORO = {"verde": "🟢 verde", "giallo": "🟡 giallo", "rosso": "🔴 rosso"}


def grafico_backtest(ris: dict) -> bytes:
    import matplotlib.pyplot as plt

    import report as RP

    bt = ris["backtest"]
    serie = list(bt["rend"])
    nc = min(2, len(serie))
    nr = int(np.ceil(len(serie) / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(11, 3.2 * nr), squeeze=False)
    d = bt["date"]
    for ax, p in zip(axs.ravel(), serie):
        ok = bt["ok"][p]
        r = bt["rend"][p] * 100
        ax.plot(d[ok], r[ok], color="#999999", lw=0.5, label="Rendimento del giorno")
        ax.plot(d[ok], -bt["var"][(p, "storico", 0.95)][ok] * 100, color="#E69F00", lw=1, label="VaR 95% storico")
        ax.plot(d[ok], -bt["var"][(p, "fattori", 0.95)][ok] * 100, color="#0072B2", lw=1, label="VaR 95% a fattori")
        for mod, col, mk in (("storico", "#E69F00", "o"), ("fattori", "#D55E00", "x")):
            f = bt["flag"][(p, mod, 0.95)].astype(bool)
            ax.scatter(d[ok][f], r[ok][f], s=14, color=col, marker=mk, zorder=5, label=f"Sforamenti ({mod})")
        ax.set_title(RP.corto(p, 32), fontsize=10, fontweight="bold")
        ax.set_ylabel("%")
        ax.grid(alpha=0.25)
    for ax in axs.ravel()[len(serie) :]:
        ax.axis("off")
    h, lab = axs.ravel()[0].get_legend_handles_labels()
    fig.legend(h, lab, ncols=5, fontsize=8, loc="lower center", frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return RP.png(fig)


def RPcorto(nome: str) -> str:  # noqa: N802
    import report as RP

    return RP.corto(nome, 24)


def blocchi_backtest(ris: dict) -> list:
    bt = ris.get("backtest")
    if not bt:
        return []
    t = bt["tabella"]
    B = [
        (
            "p",
            f"Per ogni giorno si calcola il VaR a 1 giorno con i soli dati passati (finestra mobile di {bt['finestra']} giorni di borsa) e si "
            "confronta con il rendimento del giorno dopo, come fanno le banche. Con un VaR al 95% ci si aspetta di superarlo in circa 1 giorno su 20; "
            "al 99% in circa 1 su 100.",
        ),
        (
            "box",
            [
                "<b>Test di Kupiec</b>: gli sforamenti sono tanti quanti ci aspettiamo? (p-value sotto 5% = no).",
                "<b>Test di Christoffersen</b>: gli sforamenti arrivano sparsi o a grappolo? A grappolo = il modello reagisce tardi alle crisi.",
                "<b>Semaforo</b>: verde = entrambi i test passati; giallo = uno sotto il 5%; rosso = uno sotto l'1%.",
            ],
        ),
    ]
    for lv in sorted(t["livello"].unique()):
        B.append(("h3", f"VaR a 1 giorno al {int(round(lv * 100))}%"))
        righe = []
        for _, r in t[t["livello"] == lv].iterrows():
            righe.append(
                [
                    r["serie"],
                    r["modello"],
                    str(int(r["giorni"])),
                    f"{int(r['sforamenti'])} (attesi {r['attesi']:.1f})".replace(".", ","),
                    _p(r["p_kupiec"], 1),
                    _p(r["p_christoffersen"], 1),
                    SEMAFORO[r["semaforo"]],
                ]
            )
        B.append(("tab", {"intest": ["Modello", "Giorni", "Sforamenti", "Kupiec (p)", "Christoffersen (p)", "Esito"], "righe": righe, "gruppi": None, "sx": True}))
    vecchio = "fattori (1.5.0)"
    if vecchio in set(t["modello"]):  # prima/dopo la calibrazione del modello a fattori (v1.5.1)
        B.append(("h3", "Modello a fattori: prima e dopo la calibrazione di breve termine"))
        righe = []
        for (serie, lv), g in t.groupby(["serie", "livello"], sort=False):
            a, n = g[g["modello"] == vecchio].iloc[0], g[g["modello"] == "fattori"].iloc[0]
            righe.append(
                [
                    serie,
                    f"{int(round(lv * 100))}%",
                    f"{a['attesi']:.1f}".replace(".", ","),
                    f"{int(a['sforamenti'])} {SEMAFORO[a['semaforo']].split()[0]}",
                    f"{int(n['sforamenti'])} {SEMAFORO[n['semaforo']].split()[0]}",
                ]
            )
        B.append(("tab", {"intest": ["Serie", "VaR", "Sforamenti attesi", "Prima (1.5.0)", "Ora"], "righe": righe, "gruppi": None, "sx": True}))
        gdl = ", ".join(f"{int(round(v))} per {RPcorto(k)}" for k, v in (bt.get("gdl") or {}).items() if v == v)
        lam = f"{bt.get('lambda', 0.97):.2f}".replace(".", ",")
        B.append(
            (
                "nota",
                "Prima: covarianza dei fattori su tutta la storia, rischio specifico medio della finestra, distribuzione normale. Ora: covarianza dei fattori e rischio specifico "
                f"EWMA (lambda {lam}, memoria di circa un mese, modificabile in «var_breve_termine»), code grasse (t di Student; gradi di libertà stimati, mediana {gdl}).",
            )
        )
        B.append(("box", ["<b>In parole semplici</b>: il modello storico è più adatto al rischio di breve termine; il modello a fattori è più informativo per orizzonti lunghi perché include le grandi crisi."]))
    B.append(("h3", "Rendimenti effettivi contro VaR"))
    B.append(("img", grafico_backtest(ris)))
    B.append(("didascalia", "Linee: VaR 95% dei due modelli (cambiato di segno). Punti e croci: giorni in cui la perdita ha superato il VaR."))
    mig = t.groupby("modello")["semaforo"].apply(lambda s: s.map({"verde": 0, "giallo": 1, "rosso": 2}).mean())
    B.append(("nota", "Voto medio dei semafori (0 = tutti verdi, 2 = tutti rossi): " + ", ".join(f"{m} {v:.2f}".replace(".", ",") for m, v in mig.items()) + "."))
    B.append(
        (
            "nota",
            "Il modello «fattori» del VaR a 1 giorno segue il regime corrente (covarianza e rischio specifico EWMA, code grasse); il modello «storico» è il quantile degli ultimi 2 anni. "
            "La simulazione di lungo periodo usa invece la storia lunga dei fattori. Un test su pochi anni ha poca forza: un esito verde non è una garanzia.",
        )
    )
    return B
