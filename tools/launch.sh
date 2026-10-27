#!/usr/bin/env bash
# Restart the app server (kb.api: API + legacy pages + React shell) from the current working tree, detached, then open it.
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

# The qmd search service (tools/qmd, `pixi run qmd-install` once): long-running so its model stays warm.
# Main checkout only — a worktree would start a second index and download the models again. Restarted
# like the dashboard so a changed server.mjs takes effect.
QMD_PORT="${KB_QMD_PORT:-8766}"
QMD_LOG="${TMPDIR:-/tmp}/thesis-kb-qmd.log"
if [[ "$PWD" == */.claude/worktrees/* ]]; then
  echo "qmd search service: not started from a worktree (the main checkout's service serves search)"
elif [[ ! -d tools/qmd/node_modules ]]; then
  echo "qmd search service: not installed (pixi run qmd-install) — search shows keyword hits only"
elif ! command -v node >/dev/null 2>&1 || (( $(node -p 'process.versions.node.split(".")[0]') < 22 )); then
  echo "qmd search service: needs node >= 22 — search shows keyword hits only"
else
  old=$(lsof -ti "tcp:${QMD_PORT}" -sTCP:LISTEN 2>/dev/null || true)
  [[ -n "$old" ]] && { kill $old 2>/dev/null || true; sleep 1; }
  nohup node tools/qmd/server.mjs >"$QMD_LOG" 2>&1 &
  echo "started qmd search service (pid $!), log: $QMD_LOG"
fi

nohup python -m kb.api --port "$PORT" --no-open >"$LOG" 2>&1 &
echo "started dashboard (pid $!), log: $LOG"

for _ in $(seq 1 360); do   # up to 90 s: kb.api first rebuilds frontend/dist when the sources changed
  if curl -fsS -o /dev/null "$URL"; then
    open "$URL"
    echo "ready: $URL"
    exit 0
  fi
  sleep 0.25
done

echo "dashboard did not come up in 90s; last log lines:" >&2
tail -20 "$LOG" >&2
exit 1
