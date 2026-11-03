#!/bin/bash
# Installa lo strumento con un doppio clic. Python e librerie restano dentro questa cartella.
cd "$(dirname "$0")" || exit 1

fine() {
  echo
  read -r -p "Premi Invio per chiudere questa finestra..." _
  exit "$1"
}

echo "=================================================="
echo "  Installazione: confronto rischio portafogli"
echo "=================================================="
echo "Cartella: $PWD"
echo

# Python e cache di uv dentro la cartella del progetto
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
export UV_CACHE_DIR="$PWD/.uv-cache"
export UV_PYTHON_PREFERENCE=only-managed   # usa sempre il Python scaricato in .python, non quello di sistema

UV=""
if [ -x "$PWD/.uv/uv" ]; then
  UV="$PWD/.uv/uv"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
fi

if [ -z "$UV" ]; then
  echo "1/4  Scarico uv (lo strumento che installa Python)..."
  if ! curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$PWD/.uv" UV_NO_MODIFY_PATH=1 sh; then
    echo
    echo "ERRORE: non riesco a scaricare uv. Controlla la connessione a internet e riprova."
    fine 1
  fi
  UV="$PWD/.uv/uv"
  [ -x "$UV" ] || UV="$PWD/.uv/bin/uv"
else
  echo "1/4  uv già presente: $UV"
fi

echo "2/4  Preparo Python 3.12 e l'ambiente .venv (la prima volta scarica circa 30 MB)..."
if ! "$UV" venv --python 3.12 --allow-existing .venv; then
  echo
  echo "ERRORE: non riesco a creare l'ambiente Python. Controlla la connessione e riprova."
  fine 1
fi

echo "3/4  Installo le librerie (qualche minuto la prima volta)..."
if ! "$UV" pip install --python .venv/bin/python -r requirements.txt; then
  echo
  echo "ERRORE: installazione delle librerie non riuscita. Controlla la connessione e riprova."
  echo "Se il problema resta, cancella la cartella .venv e rilancia Installa.command."
  fine 1
fi

echo "4/4  Prova rapida (circa 30 secondi, senza internet)..."
if ! .venv/bin/python -m pytest -q tests; then
  echo
  echo "ERRORE: la prova rapida non è riuscita. Copia i messaggi qui sopra e chiedi aiuto."
  fine 1
fi

echo
echo "=================================================="
echo "  Installazione completata"
echo "  Ora fai doppio clic su Avvia.command"
echo "=================================================="
fine 0
