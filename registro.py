"""File di log (log.txt nella cartella del programma): utile per segnalare un problema."""
from __future__ import annotations

import logging
import logging.handlers
import os

FILE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")


def configura(livello: int = logging.INFO) -> logging.Logger:
    """Scrive i messaggi di 'confronta' in log.txt (massimo 1 MB, con 2 copie precedenti). Idempotente."""
    log = logging.getLogger("confronta")
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in log.handlers):
        try:
            h = logging.handlers.RotatingFileHandler(FILE_LOG, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
            log.addHandler(h)
        except OSError:
            pass  # cartella in sola lettura: si continua senza file di log
    log.setLevel(livello)
    return log
