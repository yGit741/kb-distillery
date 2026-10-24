#!/usr/bin/env bash
# Restart the dashboard from the current working tree, detached, then open it.
# Kills whatever already listens on the port so a stale server never answers.
# Usage: pixi run launch [-- --port N]
set -euo pipefail

cd "$(dirname "$0")/.."
PORT=8765
[[ "${1:-}" == "--port" && -n "${2:-}" ]] && PORT="$2"
URL="http://127.0.0.1:${PORT}/start"
LOG="${TMPDIR:-/tmp}/thesis-kb-dashboard.log"

pids=$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null || true)
if [[ -n "$pids" ]]; then
  echo "stopping old dashboard (pid $pids)"
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    lsof -ti "tcp:${PORT}" -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 0.25
  done
  kill -9 $(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true
fi

find backend -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

nohup python -m kb.dashboard --port "$PORT" --no-open >"$LOG" 2>&1 &
echo "started dashboard (pid $!), log: $LOG"

for _ in $(seq 1 40); do
  if curl -fsS -o /dev/null "$URL"; then
    open "$URL"
    echo "ready: $URL"
    exit 0
  fi
  sleep 0.25
done

echo "dashboard did not come up in 10s; last log lines:" >&2
tail -20 "$LOG" >&2
exit 1
