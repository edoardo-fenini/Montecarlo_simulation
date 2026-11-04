#!/bin/bash
# Crea lo zip della release esattamente come il workflow «Release» e ne controlla il contenuto.
# Uso: bash strumenti/crea_zip.sh v1.3.1 [cartella_di_uscita]      -> stampa il percorso dello zip
# Lo zip contiene i file del repository al commit attuale (HEAD), senza quelli marcati «export-ignore» in .gitattributes (.github ...).
set -euo pipefail
TAG="${1:?indica il nome del tag, per esempio v1.3.1}"
USCITA="${2:-.}"
NOME="confronta-portafogli-${TAG}"
ZIP="${USCITA}/${NOME}.zip"
mkdir -p "$USCITA"
git archive --format=zip --prefix="${NOME}/" -o "$ZIP" HEAD
# Installa.command e Avvia.command devono essere eseguibili (permessi -rwx)
COMANDI="$(zipinfo "$ZIP")"
test "$(grep -E "(Installa|Avvia)\.command" <<< "$COMANDI" | grep -c '^-rwx')" = "2" || { echo "ERRORE: i file .command non sono eseguibili" >&2; exit 1; }
ELENCO="$(unzip -l "$ZIP")"   # una volta sola: con pipefail, «grep -q» in una pipe interromperebbe unzip
# niente ambienti, cache o report generati; niente file del solo repository
if echo "$ELENCO" | grep -E "/(\.venv|\.python|cache_prezzi|report|\.github)/"; then echo "ERRORE: file che non devono stare nello zip" >&2; exit 1; fi
for f in app.py isin.py controllo.py nomi.py importa_broker.py Installa.command Avvia.command requirements.txt configurazioni/esempio_isin.yaml tests/conftest.py; do
  grep -q "${NOME}/${f}\$" <<< "$ELENCO" || { echo "ERRORE: manca ${f} nello zip" >&2; exit 1; }
done
echo "$ZIP"
