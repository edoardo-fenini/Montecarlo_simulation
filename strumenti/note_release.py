"""Strumenti per la release automatica: valida il nome del tag (solo vX.Y.Z) e ricava le note dalla sezione giusta di CHANGELOG.md.

Uso (dal workflow .github/workflows/release.yml):
    python strumenti/note_release.py tag v1.3.0            -> stampa il tag normalizzato (errore se il formato è sbagliato)
    python strumenti/note_release.py note v1.3.0 [CHANGELOG.md]  -> stampa le note della sezione «## 1.3.0 (...)»
"""

from __future__ import annotations

import pathlib
import re
import sys

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def normalizza_tag(testo: str) -> str:
    """'1.3.0' o 'v1.3.0' -> 'v1.3.0'. Qualsiasi altra forma (V_1.3.0, v1.3, 1.3.0-beta ...) è un errore."""
    t = str(testo).strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", t):
        t = "v" + t
    if not TAG_RE.match(t):
        raise ValueError(f"Nome di tag non valido: «{testo}». Il formato è vX.Y.Z (per esempio v1.3.0).")
    return t


def note_dal_changelog(testo: str, tag: str) -> str:
    """Testo della sezione «## X.Y.Z …» del CHANGELOG (fino alla prossima «## »), senza il titolo. Errore se manca o è vuota."""
    versione = normalizza_tag(tag)[1:]
    righe = testo.splitlines()
    inizio = next((i for i, r in enumerate(righe) if re.match(rf"^##\s+{re.escape(versione)}(\s|$)", r)), None)
    if inizio is None:
        raise ValueError(f"In CHANGELOG.md manca la sezione «## {versione}»: aggiungila prima di creare il tag {tag}.")
    fine = next((i for i in range(inizio + 1, len(righe)) if righe[i].startswith("## ")), len(righe))
    corpo = "\n".join(righe[inizio + 1 : fine]).strip()
    if not corpo:
        raise ValueError(f"La sezione «## {versione}» di CHANGELOG.md è vuota.")
    return corpo + "\n"


def main(argv: list[str]) -> int:
    try:
        if len(argv) >= 3 and argv[1] == "tag":
            print(normalizza_tag(argv[2]))
        elif len(argv) >= 3 and argv[1] == "note":
            percorso = pathlib.Path(argv[3] if len(argv) > 3 else "CHANGELOG.md")
            print(note_dal_changelog(percorso.read_text(encoding="utf-8"), argv[2]), end="")
        else:
            print(__doc__)
            return 2
    except (ValueError, OSError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
