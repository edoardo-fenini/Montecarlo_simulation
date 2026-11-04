"""Crea il CSV di esempio dello storico delle quote (esempi/storico_quote_esempio.csv) con numeri INVENTATI che arrivano fino a ieri.

Serve per provare l'importazione: il controllo dati blocca (rosso) uno storico con l'ultimo valore più vecchio di 30 giorni, quindi un
file di esempio vecchio non andrebbe bene. Uso:  python strumenti/crea_csv_esempio.py [percorso_di_uscita]"""

import datetime
import sys

import numpy as np
import pandas as pd


def crea(percorso: str, fine: datetime.date | None = None, anni: int = 7, seed: int = 7) -> str:
    fine = fine or datetime.date.today() - datetime.timedelta(days=1)
    idx = pd.bdate_range(end=pd.Timestamp(fine), periods=anni * 261)
    rng = np.random.default_rng(seed)
    quote = 100 * np.cumprod(1 + rng.normal(0.0004, 0.009, len(idx)))
    righe = ["Data;Valore quota"] + [f"{d:%d/%m/%Y};{v:.4f}".replace(".", ",") for d, v in zip(idx, quote)]
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
    return percorso


if __name__ == "__main__":
    print(crea(sys.argv[1] if len(sys.argv) > 1 else "esempi/storico_quote_esempio.csv"))
