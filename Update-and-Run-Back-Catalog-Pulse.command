#!/bin/zsh
set -e

OUTPUT_DIR="${0:A:h}"
APP_DIR="$OUTPUT_DIR/Back-Catalog-Pulse"
ARCHIVE="$OUTPUT_DIR/Back-Catalog-Pulse.zip"
CREDENTIALS="$OUTPUT_DIR/client_secret.json"
BACKUP_DIR="$(mktemp -d /private/tmp/back-catalog-pulse-update.XXXXXX)"

cleanup() {
  rm -rf -- "$BACKUP_DIR"
}
trap cleanup EXIT

pause_on_error() {
  echo ""
  read "?Press Return to close..."
}
trap pause_on_error ZERR

stop_existing_listener() {
  listener_pids=($(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true))
  (( ${#listener_pids[@]} == 0 )) && return

  echo ""
  echo "An older Back Catalog Pulse process, or another app, is using port 8765:"
  for listener_pid in $listener_pids; do
    listener_cwd=$(lsof -a -p "$listener_pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    ps -p "$listener_pid" -o pid=,command= 2>/dev/null || true
    [[ -n "$listener_cwd" ]] && echo "  Folder: $listener_cwd"
  done
  echo ""
  read "stop_choice?Terminate the displayed process and continue updating? [y/N] "
  if [[ "${stop_choice:l}" != "y" && "${stop_choice:l}" != "yes" ]]; then
    echo "The existing process was left running. Nothing was replaced."
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

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Missing Back-Catalog-Pulse.zip in:"
  echo "$OUTPUT_DIR"
  exit 1
fi

if [[ ! -f "$CREDENTIALS" ]]; then
  echo "Missing client_secret.json in:"
  echo "$OUTPUT_DIR"
  exit 1
fi

stop_existing_listener

if [[ -d "$APP_DIR" ]]; then
  [[ -f "$APP_DIR/token.json" ]] && cp "$APP_DIR/token.json" "$BACKUP_DIR/token.json"
  [[ -d "$APP_DIR/datasets" ]] && ditto "$APP_DIR/datasets" "$BACKUP_DIR/datasets"

  if [[ "$APP_DIR" != "$OUTPUT_DIR/Back-Catalog-Pulse" ]]; then
    echo "Safety check failed; the application folder was not removed."
    exit 1
  fi
  rm -rf -- "$APP_DIR"
fi

mkdir -p "$APP_DIR"
ditto -x -k "$ARCHIVE" "$APP_DIR"
cp "$CREDENTIALS" "$APP_DIR/client_secret.json"

[[ -f "$BACKUP_DIR/token.json" ]] && cp "$BACKUP_DIR/token.json" "$APP_DIR/token.json"
[[ -d "$BACKUP_DIR/datasets" ]] && ditto "$BACKUP_DIR/datasets" "$APP_DIR/datasets"

chmod +x "$APP_DIR/start.command"

echo "Back Catalog Pulse was updated successfully."
echo "Launching the app..."
exec "$APP_DIR/start.command"
