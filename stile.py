"""Stile condiviso da app, report HTML e PDF: ogni portafoglio ha sempre lo stesso colore e lo stesso tratto.

Palette Okabe-Ito (distinguibile anche da chi ha difficoltà con i colori); il benchmark è sempre grigio.
Il colore non è mai l'unico segnale: nei grafici ogni portafoglio ha anche un tratteggio o un motivo diverso e un'etichetta."""

from __future__ import annotations

PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#882255", "#117733"]
GRIGIO = "#666666"
BLU_NOTTE = "#1F3A5F"  # titoli e intestazioni
PRIMARIO = "#3366A3"  # colore principale dell'app (contrasto sufficiente su sfondo chiaro e scuro)
ROSSO_SOTTO = "#C62828"  # zona sotto il capitale investito
TRATTI_MPL = ["-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1, 1, 1)), (0, (1, 1)), (0, (5, 3))]
TRATTI_PLOTLY = ["solid", "dash", "dashdot", "dot", "longdash", "longdashdot", "solid", "dash"]
MOTIVI_PLOTLY = ["", "/", "\\", "x", ".", "+", "-", "|"]
MOTIVI_MPL = ["", "//", "\\\\", "xx", "..", "++", "--", "||"]


def colori(nomi: list[str], bench: str) -> dict[str, str]:
    """{portafoglio: colore}: i portafogli prendono i colori della palette nell'ordine, il benchmark il grigio."""
    out, i = {}, 0
    for k in nomi:
        if k == bench:
            out[k] = GRIGIO
        else:
            out[k] = PALETTE[i % len(PALETTE)]
            i += 1
    return out


def indice(nomi: list[str], bench: str) -> dict[str, int]:
    """Posizione di ogni portafoglio (per tratteggi e motivi); il benchmark usa sempre il tratto pieno."""
    out, i = {}, 1
    for k in nomi:
        if k == bench:
            out[k] = 0
        else:
            out[k] = i % len(TRATTI_MPL)
            i += 1
    return out


def rgba(colore: str, alfa: float) -> str:
    c = colore.lstrip("#")
    return f"rgba({int(c[0:2], 16)},{int(c[2:4], 16)},{int(c[4:6], 16)},{alfa})"
