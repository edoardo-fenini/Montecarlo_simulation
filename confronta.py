"""Confronta portafogli con una simulazione Monte Carlo e produce un report.

Esempi:
  python confronta.py --config configurazioni/esempio_tre_portafogli.yaml
  python confronta.py --config configurazioni/mio_portafoglio.yaml --veloce
  python confronta.py --config configurazioni/mio_portafoglio.yaml --simulazioni 20000 --aggiorna-dati

Il report va in report/AAAA-MM-GG_nome-configurazione/ (report.html, report.pdf, dati_csv/)."""
import argparse, datetime, os, re, sys, time

import analisi
import registro
import report
from configurazione import ErroreConfig, carica
from dati import ErroreDati


def cartella_uscita(cfg, percorso_cfg, base="report"):
    nome = cfg.get("nome") or os.path.splitext(os.path.basename(percorso_cfg))[0]
    slug = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or "confronto"
    return os.path.join(base, f"{datetime.date.today():%Y-%m-%d}_{slug}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confronto del rischio di portafogli con Monte Carlo.")
    ap.add_argument("--config", required=True, help="file YAML di configurazione (vedi cartella configurazioni/)")
    ap.add_argument("--simulazioni", type=int, help="numero di simulazioni (sostituisce quello della configurazione)")
    ap.add_argument("--veloce", action="store_true", help="prova rapida con 1.000 simulazioni")
    ap.add_argument("--aggiorna-dati", action="store_true", help="riscarica i prezzi anche se sono già in cache")
    ap.add_argument("--uscita", help="cartella dove salvare il report (default: report/AAAA-MM-GG_nome)")
    ap.add_argument("--senza-pdf", action="store_true", help="non creare il PDF")
    a = ap.parse_args(argv)
    log = registro.configura()
    t0 = time.time()
    try:
        cfg = carica(a.config)
        n = 1000 if a.veloce else (a.simulazioni or cfg["n_simulazioni"])
        print(f"Configurazione «{cfg['nome']}»: {len(cfg['portafogli'])} portafogli + benchmark, {n:,} simulazioni".replace(",", "."))
        log.info("riga di comando: %s, %d simulazioni", a.config, n)
        ris = analisi.esegui(cfg, aggiorna_dati=a.aggiorna_dati, n=n, log=print)
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
