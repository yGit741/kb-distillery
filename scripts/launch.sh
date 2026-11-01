#!/usr/bin/env bash
# Restart the app server (kb_distillery.api: API + legacy pages + React shell) from the current working tree, detached, then open it.
# Kills whatever already listens on the port so a stale server never answers.
# Usage: pixi run launch [-- --kb <id>] [-- --port N]
# The knowledge base: --kb <id|path> (else $KB, the only one; `kbd kb-list`).
set -euo pipefail

cd "$(dirname "$0")/.."
PORT=8765
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --kb) export KB="$2"; shift 2 ;;
    --kb=*) export KB="${1#--kb=}"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
KB_SHOW="$(python -m kb_distillery.kbconfig show)" || { echo "$KB_SHOW" >&2; exit 1; }
KB_ID="$(printf '%s\n' "$KB_SHOW" | sed -n 's/^id  *//p')"
[[ "$KB_ID" == "None" ]] && KB_ID=""
KB_ROOT_DIR="$(printf '%s\n' "$KB_SHOW" | sed -n 's/^root  *//p')"
echo "knowledge base: ${KB_ID:-none} ($KB_ROOT_DIR)"
export KB_LIVE=1                    # this dashboard's lint runs keep the qmd search cards in step
export KB_SHARE_AUTODEPLOY="${KB_SHARE_AUTODEPLOY:-0}"   # POC: nothing deploys from the split layout
URL="http://127.0.0.1:${PORT}/start"
LOG="${TMPDIR:-/tmp}/kb-distillery-${KB_ID:-none}-dashboard.log"

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

find src -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

# The qmd search service (scripts/qmd, `pixi run qmd-install` once): long-running so its model stays warm.
# Main checkout only — a worktree would start a second index and download the models again. Restarted
# like the dashboard so a changed server.mjs takes effect.
QMD_PORT="${KB_QMD_PORT:-8766}"
QMD_LOG="${TMPDIR:-/tmp}/kb-distillery-qmd.log"
if [[ "$PWD" == */.claude/worktrees/* ]]; then
  echo "qmd search service: not started from a worktree (the main checkout's service serves search)"
elif [[ ! -d scripts/qmd/node_modules ]]; then
  echo "qmd search service: not installed (pixi run qmd-install) — search shows keyword hits only"
elif ! command -v node >/dev/null 2>&1 || (( $(node -p 'process.versions.node.split(".")[0]') < 22 )); then
  echo "qmd search service: needs node >= 22 — search shows keyword hits only"
else
  old=$(lsof -ti "tcp:${QMD_PORT}" -sTCP:LISTEN 2>/dev/null || true)
  [[ -n "$old" ]] && { kill $old 2>/dev/null || true; sleep 1; }
  KB_ROOT="$KB_ROOT_DIR" nohup node scripts/qmd/server.mjs >"$QMD_LOG" 2>&1 &   # the selected kb, never the checkout
  echo "started qmd search service (pid $!), log: $QMD_LOG"
fi
# The card vectors are per kb too (graph math): say so when this kb has none or they lag its cards.
if ! VEC_STATUS="$(python -m kb_distillery.search.vectors status 2>&1)"; then
  echo "card vectors: $VEC_STATUS"
fi

nohup python -m kb_distillery.api --port "$PORT" --no-open >"$LOG" 2>&1 &
echo "started dashboard (pid $!), log: $LOG"

for _ in $(seq 1 1200); do   # up to 5 min: kb_distillery.api installs the frontend dependencies on a fresh clone and rebuilds src/kb_distillery/_webapp when the sources changed
  if curl -fsS -o /dev/null "$URL"; then
    open "$URL"
    echo "ready: $URL"
    exit 0
  fi
  sleep 0.25
done

echo "dashboard did not come up in 5 min (a first run installs and builds the frontend and needs the network); last log lines:" >&2
tail -20 "$LOG" >&2
exit 1
