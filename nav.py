"""Storico delle quote (NAV) di un fondo importato da CSV e collegato all'ISIN.

Uso tipico (app): `leggi(contenuto)` → anteprima → `salva(arch, isin, serie, valuta, nome)`.
Da riga di comando: in configurazione `prezzi_da_file: {ISIN: {file: percorso.csv, valuta: EUR}}` (vedi dati.importa_da_configurazione).
Una volta salvato lo storico, ogni analisi successiva con quell'ISIN lo riusa (il controllo dati indica la fonte «CSV importato»)."""

from __future__ import annotations

import numpy as np
import pandas as pd

import dati as D
import fonti
import isin as I
from dati import ErroreDati

VALUTE = ["EUR", "USD", "GBP", "CHF", "JPY", "SEK", "NOK", "DKK", "CAD", "AUD"]


def leggi(contenuto: bytes) -> pd.Series:
    """Legge il CSV (separatore, decimali, formato data e intestazioni riconosciuti da soli). Solleva ErroreDati con un messaggio chiaro."""
    try:
        return fonti.leggi_csv_prezzi(contenuto)
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as e:
        raise ErroreDati(f"Non riesco a leggere il file: {e}. Servono una colonna con la data e una con il valore della quota.") from e


def anteprima(s: pd.Series, righe: int = 5) -> pd.DataFrame:
    """Prime e ultime righe della serie letta, nel formato italiano, per controllare che sia stata capita bene."""

    def formato(parte):
        return pd.DataFrame({"Data": parte.index.strftime("%d/%m/%Y"), "Valore quota": [f"{v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".") for v in parte.values]})

    if len(s) <= 2 * righe:
        return formato(s)
    sep = pd.DataFrame({"Data": ["…"], "Valore quota": ["…"]})
    return pd.concat([formato(s.iloc[:righe]), sep, formato(s.iloc[-righe:])], ignore_index=True)


def riassunto(s: pd.Series) -> str:
    anni = (s.index[-1] - s.index[0]).days / 365.25
    return f"{len(s)} valori dal {s.index[0]:%d/%m/%Y} al {s.index[-1]:%d/%m/%Y} ({anni:.1f} anni); ultimo valore {s.iloc[-1]:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ classe a distribuzione
def avviso_distribuzione(s: pd.Series, finestra: int = 3, soglia_sd: float = 2.5, quota_anni: float = 0.6, anni_min: int = 3) -> str | None:
    """GIALLO se la serie sembra di una classe a distribuzione: cali bruschi ricorrenti negli stessi giorni dell'anno (lo stacco della
    cedola fa scendere la quota). Per ogni giorno dell'anno si guarda se, in una finestra di ±`finestra` giorni, c'è stato un calo
    superiore a `soglia_sd` volte la variabilità normale della serie; se succede in almeno il 60% degli anni (e in almeno 3) è sospetto.
    Ritorna il testo dell'avviso oppure None."""
    r = s.pct_change().dropna()
    if len(r) < 250 * anni_min:
        return None
    sd = 1.4826 * float(np.median(np.abs(r - r.median()))) or float(r.std())
    if sd <= 0:
        return None
    forte = r < -soglia_sd * sd
    anni = sorted(set(r.index.year))
    doy = r.index.day_of_year.values
    anno_riga, forte_v = r.index.year.values, forte.values
    migliore = (0.0, 0, 0)
    for centro in range(1, 366):
        distanza = np.minimum(np.abs(doy - centro), 365 - np.abs(doy - centro))
        in_finestra = distanza <= finestra
        anni_con_calo = np.unique(anno_riga[in_finestra & forte_v])
        anni_validi = np.unique(anno_riga[in_finestra])
        if len(anni_validi) < anni_min:
            continue
        quota = len(anni_con_calo) / len(anni_validi)
        if len(anni_con_calo) >= anni_min and quota > migliore[0]:
            migliore = (quota, len(anni_con_calo), centro)
    if migliore[0] >= quota_anni:
        data = pd.Timestamp("2021-01-01") + pd.Timedelta(days=migliore[2] - 1)
        return (
            f"la serie sembra di una classe a DISTRIBUZIONE: calo brusco ricorrente intorno al {data.day}/{data.month} in {migliore[1]} anni su "
            f"{len(anni)}. Il valore della quota non include le cedole incassate, quindi il rendimento è sottostimato: "
            "meglio la classe ad accumulazione."
        )
    return None


# ------------------------------------------------------------------ salvataggio
def salva(arch: D.Archivio, isin_cod: str, s: pd.Series, valuta: str, nome: str = "") -> None:
    """Salva lo storico in cache con l'ISIN come chiave (fonte «CSV importato»). Verrà riusato dalle analisi successive."""
    tipo, cod = I.riconosci(isin_cod)
    if tipo == "isin_errato" or not cod:
        raise ErroreDati(f"«{isin_cod}» non è valido: lo storico delle quote si collega a un ISIN o a un ticker.")
    if valuta not in VALUTE:
        raise ErroreDati(f"Valuta «{valuta}» non prevista. Scegli tra: {', '.join(VALUTE)}.")
    arch.importa_serie(cod, s, valuta, "MUTUALFUND", nome or f"{cod} (storico delle quote importato)", D.FONTE_NAV)
