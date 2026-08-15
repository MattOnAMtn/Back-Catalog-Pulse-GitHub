#!/bin/zsh
set -e
cd "${0:A:h}"

APP_PORT=${PORT:-8765}

stop_existing_listener() {
  listener_pids=($(lsof -tiTCP:"$APP_PORT" -sTCP:LISTEN 2>/dev/null || true))
  (( ${#listener_pids[@]} == 0 )) && return

  echo ""
  echo "Something is already running on port $APP_PORT:"
  for listener_pid in $listener_pids; do
    listener_cwd=$(lsof -a -p "$listener_pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    ps -p "$listener_pid" -o pid=,command= 2>/dev/null || true
    [[ -n "$listener_cwd" ]] && echo "  Folder: $listener_cwd"
  done
  echo ""
  read "stop_choice?Terminate the old process and continue? [y/N] "
  if [[ "${stop_choice:l}" != "y" && "${stop_choice:l}" != "yes" ]]; then
    echo "The existing process was left running."
    exit 1
  fi

  for listener_pid in $listener_pids; do
    kill -TERM "$listener_pid" 2>/dev/null || true
  done
  for wait_step in {1..20}; do
    still_running=0
    for listener_pid in $listener_pids; do
      kill -0 "$listener_pid" 2>/dev/null && still_running=1
    done
    (( still_running == 0 )) && break
    sleep 0.25
  done
  for listener_pid in $listener_pids; do
    if kill -0 "$listener_pid" 2>/dev/null; then
      echo "The old process did not stop normally; force-stopping PID $listener_pid."
      kill -KILL "$listener_pid" 2>/dev/null || true
    fi
  done
}

stop_existing_listener

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -q -r requirements.txt

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
