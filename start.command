#!/bin/zsh
set -e
cd "${0:A:h}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -q -r requirements.txt

APP_PORT=${PORT:-8765}
if lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo ""
  echo "Back Catalog Pulse is already running on port $APP_PORT."
  echo "Close its older Terminal window, then run this launcher again."
  echo ""
  lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN
  echo ""
  read "?Press Return to close..."
  exit 1
fi

if [[ ! -f client_secret.json ]]; then
  echo ""
  echo "Missing client_secret.json"
  echo "Follow the OAuth setup steps in README.md, then run this file again."
  echo ""
  read "?Press Return to close..."
  exit 1
fi

python app.py &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null || true' EXIT INT TERM
sleep 2
open "http://127.0.0.1:$APP_PORT"
wait $APP_PID
