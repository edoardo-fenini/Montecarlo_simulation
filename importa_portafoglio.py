"""Crea un portafoglio da un CSV esportato dal broker e lo salva in un file di configurazione YAML.

Esempi:
    python importa_portafoglio.py esempi/portafoglio_broker_esempio.csv
    python importa_portafoglio.py mio.csv --nome "Il mio conto" --base configurazioni/esempio_tre_portafogli.yaml \\
        --uscita configurazioni/mio_conto.yaml
Prima mostra un'anteprima (titoli, controvalori, pesi) e chiede conferma; `--si` salta la domanda.
Il CSV deve avere almeno ISIN (o ticker) e quantità, oppure ISIN e controvalore: vedi README, «Importare il portafoglio dal broker».
"""

from __future__ import annotations

import argparse
import copy
import pathlib
import sys

import yaml

import configurazione as C
import dati as D
import importa_broker as B


def main(argv: list[str] | None = None, chiedi=input, prezzo_eur=None) -> int:
    ap = argparse.ArgumentParser(description="Crea un portafoglio da un CSV del broker (anteprima + conferma).")
    ap.add_argument("csv", help="file CSV esportato dal broker")
    ap.add_argument("--nome", default="Portafoglio importato", help="nome del portafoglio (default: «Portafoglio importato»)")
    ap.add_argument("--base", help="configurazione a cui aggiungere il portafoglio (se manca: solo il portafoglio e il benchmark di default)")
    ap.add_argument("--uscita", help="file YAML da scrivere (default: configurazioni/<nome>.yaml)")
    ap.add_argument("--si", action="store_true", help="non chiedere conferma")
    a = ap.parse_args(argv)
    try:
        contenuto = pathlib.Path(a.csv).read_bytes()
        base = yaml.safe_load(open(a.base, encoding="utf-8")) if a.base else {"nome": a.nome, "portafogli": []}
        cfg_isin = C.prepara(copy.deepcopy(base))["isin"] if base.get("portafogli") else C.DEFAULT["isin"]
        ris = B.calcola(contenuto, prezzo_eur or B.prezzo_da_archivio(D.Archivio(log=lambda *x: None), cfg_isin))
    except (OSError, B.ErroreImport, C.ErroreConfig, yaml.YAMLError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    print(f"Anteprima del portafoglio «{a.nome}» (totale {ris['totale']:,.2f} €)\n".replace(",", "X").replace(".", ",").replace("X", "."))
    print(B.tabella_anteprima(ris).to_string(index=False))
    for x in ris["avvisi"]:
        print(f"  avviso: {x}")
    if not a.si and chiedi("\nConfermi e salvi il portafoglio? [s/N] ").strip().lower() not in ("s", "si", "sì", "y", "yes"):
        print("Nessun file scritto.")
        return 2
    base = copy.deepcopy(base)
    base["portafogli"] = [p for p in base.get("portafogli") or [] if p.get("nome") != a.nome] + [B.portafoglio(ris, a.nome)]
    try:
        C.prepara(copy.deepcopy(base))  # la configurazione risultante deve essere valida
    except C.ErroreConfig as e:
        print(f"ERRORE: la configurazione risultante non è valida: {e}", file=sys.stderr)
        return 1
    uscita = pathlib.Path(a.uscita or f"configurazioni/{a.nome.strip().replace(' ', '_').lower()}.yaml")
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Salvato in {uscita}. Ora puoi lanciare: python confronta.py --config {uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
