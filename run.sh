#!/usr/bin/env bash
# Bring the whole TLOU Factions revival backend up with one command.
#   ./run.sh          run all servers in the foreground (Ctrl-C stops all)
#   ./run.sh -d       run in the background (logs -> server/logs/)
#   ./run.sh stop     stop background servers
# Port 80 needs privilege: run with sudo, or use Docker (docker compose up).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
case "${1:-}" in
  -d|--daemon)
    mkdir -p "$HERE/server/logs"
    nohup "$PY" "$HERE/server/run_all.py" > "$HERE/server/logs/run_all.out" 2>&1 &
    echo "backend started in background (pid $!); logs in server/logs/" ;;
  stop)
    pkill -f "$HERE/server/run_all.py" && echo "backend stopped" || echo "nothing running" ;;
  *)
    exec "$PY" "$HERE/server/run_all.py" ;;
esac
