#!/bin/bash
# Avvia l'app con un doppio clic. Chiudendo questa finestra del Terminale l'app si ferma.
cd "$(dirname "$0")" || exit 1

# Modalità non interattiva (per le prove automatiche su GitHub): ./Avvia.command --non-interattivo
# oppure variabile d'ambiente CI impostata: non apre il browser e non aspetta Invio.
NON_INTERATTIVO=0
if [ "$1" = "--non-interattivo" ] || [ -n "$CI" ]; then NON_INTERATTIVO=1; fi

pausa() {
  if [ "$NON_INTERATTIVO" = 0 ]; then
    read -r -p "Premi Invio per chiudere questa finestra..." _
  fi
}

if [ ! -x .venv/bin/python ]; then
  echo "L'app non è ancora installata: prima fai doppio clic su Installa.command"
  pausa
  exit 1
fi

# una porta libera sul computer (l'app è visibile solo da questo Mac)
PORTA=$(.venv/bin/python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])")
URL="http://localhost:$PORTA"

echo "=================================================="
echo "  Avvio dell'app: confronto rischio portafogli"
echo "  Indirizzo: $URL"
echo "  Per chiudere l'app chiudi questa finestra."
echo "=================================================="

.venv/bin/python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 \
  --server.port "$PORTA" --browser.gatherUsageStats false &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT INT TERM HUP

for _ in $(seq 1 90); do
  if curl -s "$URL/_stcore/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ERRORE: l'app non è partita. Prova a rilanciare Installa.command."
    pausa
    exit 1
  fi
  sleep 1
done

if [ "$NON_INTERATTIVO" = 0 ] && command -v open >/dev/null 2>&1; then
  open "$URL"
else
  echo "Apri il browser su $URL"
fi
wait "$PID"
