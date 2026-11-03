"""Grafici interattivi (Plotly) per l'app. Stessi colori e stesse informazioni dei grafici statici del report."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

import stile


def tacche_euro(massimo: float, n: int = 6) -> tuple[list[float], list[str]]:
    """Tacche dell'asse in formato italiano (1.000 €): il tema di Streamlit ignora il separatore delle migliaia di Plotly."""
    grezzo = max(massimo, 1) / n
    base = 10 ** np.floor(np.log10(grezzo))
    passo = min((m * base for m in (1, 2, 2.5, 5, 10) if m * base >= grezzo), default=10 * base)
    valori = list(np.arange(0, massimo + passo, passo))
    return valori, [f"{v:,.0f}".replace(",", ".") for v in valori]


def _layout(fig: go.Figure, titolo_y: str, altezza: int = 520) -> go.Figure:
    fig.update_layout(
        height=altezza,
        separators=",.",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        yaxis=dict(title=titolo_y, tickformat=",.0f", rangemode="tozero"),
        hoverlabel=dict(namelength=-1),
    )
    return fig


def fan_chart(ris: dict, a: str, fasce: bool = True) -> go.Figure:
    """Fan chart con tutti i portafogli: passando il mouse si leggono mediana, 5° e 95° percentile di quell'anno;
    clic sulla legenda per nascondere un portafoglio."""
    s, cfg = ris["sim"][a], ris["cfg"]
    nomi, bn = s["nomi"], ris["bench_nome"]
    col, idx = stile.colori(nomi, bn), stile.indice(nomi, bn)
    x = np.arange(s["bande"][nomi[0]].shape[1]) / 12
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=s["versato"],
            fill="tozeroy",
            fillcolor=stile.rgba(stile.ROSSO_SOTTO, 0.08),
            line=dict(color="rgba(0,0,0,0)"),
            name="Sotto il capitale investito",
            hoverinfo="skip",
        )
    )
    for k in nomi:
        b = s["bande"][k]
        if fasce:
            fig.add_trace(go.Scatter(x=x, y=b[4], line=dict(width=0), legendgroup=k, showlegend=False, hoverinfo="skip"))
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=b[0],
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor=stile.rgba(col[k], 0.13),
                    legendgroup=k,
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=b[2],
                name=k,
                legendgroup=k,
                line=dict(color=col[k], width=2.6, dash=stile.TRATTI_PLOTLY[idx[k]]),
                customdata=np.stack([b[0], b[4]], axis=1),
                hovertemplate=f"<b>{k}</b>: mediana %{{y:,.0f}} € · 5° %{{customdata[0]:,.0f}} € · 95° %{{customdata[1]:,.0f}} €<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=s["versato"],
            name="Totale versato",
            line=dict(color="#888888", dash="dash", width=1.5),
            hovertemplate="Totale versato %{y:,.0f} €<extra></extra>",
        )
    )
    for h in cfg["orizzonti"]:
        fig.add_vline(x=h, line=dict(color="#999999", width=1, dash="dot"))
    massimo = max(float(s["bande"][k][4 if fasce else 2].max()) for k in nomi)
    valori, testi = tacche_euro(massimo)
    fig.update_xaxes(title="anni", hoverformat=".1f", dtick=1 if cfg["orizzonte_anni"] <= 20 else 5)
    _layout(fig, "valore (€)")
    fig.update_yaxes(tickvals=valori, ticktext=testi, range=[0, massimo * 1.03])
    return fig


def istogramma_mdd(ris: dict, a: str) -> go.Figure:
    s = ris["sim"][a]
    nomi, bn = s["nomi"], ris["bench_nome"]
    col, idx = stile.colori(nomi, bn), stile.indice(nomi, bn)
    fig = go.Figure()
    for k in nomi:
        fig.add_trace(
            go.Histogram(
                x=s["mdd_fin"][k] * 100,
                name=k,
                histnorm="percent",
                opacity=0.55,
                xbins=dict(start=-100, end=0, size=2.5),
                marker=dict(color=col[k], pattern=dict(shape=stile.MOTIVI_PLOTLY[idx[k]], fgcolor=col[k])),
                hovertemplate=f"<b>{k}</b>: %{{y:.1f}}% dei casi<extra></extra>",
            )
        )
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title="calo massimo (%)", ticksuffix="%", hoverformat=".1f")
    return _layout(fig, "% delle simulazioni", 420).update_layout(yaxis=dict(tickformat=".0f", ticksuffix="%"))
