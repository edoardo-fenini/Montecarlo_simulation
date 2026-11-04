"""Confronta portafogli con una simulazione Monte Carlo e produce un report.

Esempi:
  python confronta.py --config configurazioni/esempio_tre_portafogli.yaml
  python confronta.py --config configurazioni/mio_portafoglio.yaml --veloce
  python confronta.py --config configurazioni/mio_portafoglio.yaml --simulazioni 20000 --aggiorna-dati

Prima di simulare il programma controlla i dati e stampa la tabella «Controllo dati»; con un errore (rosso) si ferma.
  python confronta.py --config configurazioni/esempio_isin.yaml --solo-controllo     (solo la verifica, senza simulare)

Il report va in report/AAAA-MM-GG_nome-configurazione/ (report.html, report.pdf, dati_csv/)."""

import argparse
import datetime
import os
import re
import sys
import time

import analisi
import controllo
import dati as D
import registro
import rendimento
import report
from configurazione import ErroreConfig, carica
from dati import ErroreDati


def cartella_uscita(cfg, percorso_cfg, base="report"):
    nome = cfg.get("nome") or os.path.splitext(os.path.basename(percorso_cfg))[0]
    slug = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or "confronto"
    return os.path.join(base, f"{datetime.date.today():%Y-%m-%d}_{slug}")


def main(argv=None, scaricatore=None, kw_isin=None, oggi=None, cartella_cache=D.CARTELLA_CACHE):
    """scaricatore, kw_isin, oggi, cartella_cache: solo per i test (dati finti, niente internet)."""
    ap = argparse.ArgumentParser(description="Confronto del rischio di portafogli con Monte Carlo.")
    ap.add_argument("--config", required=True, help="file YAML di configurazione (vedi cartella configurazioni/)")
    ap.add_argument("--simulazioni", type=int, help="numero di simulazioni (sostituisce quello della configurazione)")
    ap.add_argument("--veloce", action="store_true", help="prova rapida con 1.000 simulazioni")
    ap.add_argument("--aggiorna-dati", action="store_true", help="riscarica i prezzi anche se sono già in cache")
    ap.add_argument("--uscita", help="cartella dove salvare il report (default: report/AAAA-MM-GG_nome)")
    ap.add_argument("--solo-controllo", action="store_true", help="controlla solo i dati (titoli, ISIN, storia, prezzi) senza simulare")
    ap.add_argument("--senza-pdf", action="store_true", help="non creare il PDF")
    a = ap.parse_args(argv)
    log = registro.configura()
    t0 = time.time()
    try:
        cfg = carica(a.config)
        n = 1000 if a.veloce else (a.simulazioni or cfg["n_simulazioni"])
        print(f"Configurazione «{cfg['nome']}»: {len(cfg['portafogli'])} portafogli + benchmark, {n:,} simulazioni".replace(",", "."))
        log.info("riga di comando: %s, %d simulazioni", a.config, n)
        arch = D.Archivio(cartella_cache, a.aggiorna_dati, print, scaricatore)
        print("Controllo dei dati (scarico i prezzi mancanti) ...")
        esito = controllo.controlla(cfg, arch, oggi=oggi, log=print, **(kw_isin or {}))
        print(controllo.testo_tabella(esito))
        if esito["blocca"]:
            log.error("controllo dati: %s", esito["riepilogo"])
            print(f"\nERRORE: {esito['messaggio']}", file=sys.stderr)
            return 1
        rend = controllo.rendimenti_attesi(esito, arch)
        if rend is not None:
            print("\nRendimento atteso annuo che verrà usato (con il metodo beta anche il beta):")
            print(rend.T.to_string(float_format=lambda x: f"{x:.3f}"))
        ra = cfg["rendimento_atteso"]
        for livello, testo in rendimento.avvisi_campi(ra["metodo"], ra["tasso_privo_rischio"] * 100, ra["premio_mercato"] * 100, ra["valore_uguale"] * 100) + rendimento.avvisi_tabella(rend):
            print(f"  {livello}: {testo}")
        if a.solo_controllo:
            print(f"\nControllo terminato: {esito['riepilogo']}. Nessun errore: puoi lanciare la simulazione.")
            return 0
        ris = analisi.esegui(
            esito["cfg"], aggiorna_dati=a.aggiorna_dati, n=n, log=print, archivio=arch, controllo=controllo.per_report(esito)
        )
        if ris.get("errore_plausibilita"):
            log.error("%s", ris["errore_plausibilita"])
            print(f"\nERRORE: {ris['errore_plausibilita']}\nIl report non viene scritto.", file=sys.stderr)
            return 1
        out = a.uscita or cartella_uscita(cfg, a.config)
        print("Scrivo il report ...")
        f = report.salva(ris, out, pdf=not a.senza_pdf)
    except (ErroreConfig, ErroreDati) as e:
        log.error("%s", e)
        print(f"\nERRORE: {e}", file=sys.stderr)
        return 1
    except Exception:
        log.exception("Errore imprevisto")
        print(f"\nERRORE imprevisto: i dettagli sono nel file {registro.FILE_LOG}", file=sys.stderr)
        return 2
    for x in ris["avvisi"]:
        print(f"  avviso: {x}")
    print(f"\nFatto in {time.time() - t0:.0f} secondi. Apri il report con un doppio clic su:\n  {os.path.abspath(f)}")
    return 0


if __name__ == "__main__":  # necessario anche per il calcolo in parallelo (processi "spawn")
    sys.exit(main())
