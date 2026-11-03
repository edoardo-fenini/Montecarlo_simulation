"""Dati sintetici deterministici: un 'finto Yahoo Finance' che non usa internet (usato da test e non regressione)."""

import numpy as np
import pandas as pd

GIORNI = pd.bdate_range("2012-01-02", "2024-12-31")


def _serie(seed, beta=1.0, vol=0.01, inizio=None, base=None):
    rng = np.random.default_rng(seed)
    m = base if base is not None else rng.normal(0.0003, 0.01, len(GIORNI))
    r = beta * m + rng.normal(0, vol, len(GIORNI))
    s = pd.Series(100 * np.cumprod(1 + r), index=GIORNI)
    return s if inizio is None else s[s.index >= inizio]


def crea_finto_yahoo():
    mercato = np.random.default_rng(0).normal(0.0003, 0.01, len(GIORNI))
    dati = {
        "BMK.AS": (_serie(1, 1.0, 0.001, base=mercato), {"valuta": "EUR", "tipo": "ETF"}),
        "^IDX": (_serie(2, 1.0, 0.001, base=mercato), {"valuta": "USD", "tipo": "INDEX"}),
        "AAA.MI": (_serie(3, 1.5, 0.012, base=mercato), {"valuta": "EUR", "tipo": "EQUITY"}),
        "BBB.DE": (_serie(4, 0.8, 0.010, base=mercato, inizio="2016-01-01"), {"valuta": "EUR", "tipo": "EQUITY"}),
        "CCC": (_serie(5, 1.2, 0.015, base=mercato), {"valuta": "USD", "tipo": "EQUITY"}),
        "EURUSD=X": (pd.Series(1.1 + 0.05 * np.sin(np.arange(len(GIORNI)) / 200), index=GIORNI), {"valuta": "USD", "tipo": "CURRENCY"}),
    }

    def scarica(t):
        if t in dati:
            return dati[t][0].copy(), dict(dati[t][1])
        return pd.Series(dtype=float), {}

    return scarica
