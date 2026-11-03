"""Verifica quali fonti di prezzi rispondono davvero da questo computer (o dal server di GitHub Actions).
Uso:  python strumenti/verifica_fonti.py"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fonti

PROVE = {
    "Yahoo Finance": ["AAPL", "SAP.DE", "ENI.MI", "HSBA.L"],
    "Yahoo Finance (API diretta)": ["AAPL", "SAP.DE", "ENI.MI", "HSBA.L"],
    "Stooq": ["AAPL", "SAP.DE", "HSBA.L", "EURUSD=X"],
    "Banca Centrale Europea": ["EURUSD=X", "EURGBP=X", "EURCHF=X"],
}
FUNZ = dict(fonti.FONTI_CAMBI)


def main():
    print(f"{'fonte':30} {'ticker':10} {'esito':8} {'prezzi':>7} {'dal':>11} {'al':>11} {'valuta':6} secondi")
    ok_fonte = {}
    for nome, tick in PROVE.items():
        for t in tick:
            t0 = time.time()
            try:
                s, m = fonti.con_tentativi(FUNZ[nome], t, tentativi=2, attesa=1)
                esito = "OK" if len(s) else "vuoto"
                riga = (len(s), s.index[0].date() if len(s) else "", s.index[-1].date() if len(s) else "", m.get("valuta") or "")
            except Exception as e:
                esito, riga = "ERRORE", (0, "", "", str(e)[:40])
            ok_fonte.setdefault(nome, []).append(esito == "OK")
            print(f"{nome:30} {t:10} {esito:8} {riga[0]:>7} {str(riga[1]):>11} {str(riga[2]):>11} {riga[3]:6} {time.time() - t0:.1f}")
    print()
    for nome, v in ok_fonte.items():
        print(f"{nome}: {sum(v)}/{len(v)} prove riuscite")


if __name__ == "__main__":
    main()
