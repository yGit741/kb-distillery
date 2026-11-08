#!/usr/bin/env bash
# Install (or reinstall) the nightly knowledge-lane sync as a user launchd agent.
# Runs `pixi run daily-sync` at 22:00 local; a run missed while asleep fires on wake.
# Usage: pixi run install-sync -- --kb <id|path>      (or KB=<id|path> pixi run install-sync)
#        uninstall: pixi run install-sync -- --uninstall
# The job runs against that knowledge base: the engine repo is not one.
set -euo pipefail

cd "$(dirname "$0")/../.."
LABEL=com.kb-distillery.daily-sync
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/kb-distillery-daily-sync.log"
PIXI="$(command -v pixi || echo "$HOME/.pixi/bin/pixi")"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$DEST"
  echo "uninstalled $LABEL"
  exit 0
fi

KB_REF="${KB:-}"
if [[ "${1:-}" == "--kb" ]]; then KB_REF="${2:-}"; fi
if [[ -z "$KB_REF" ]]; then
  echo "error: pass the knowledge base the nightly job should sync: pixi run install-sync -- --kb <id|path> (or set KB)" >&2
  exit 2
fi

mkdir -p "$(dirname "$DEST")" "$(dirname "$LOG")"
sed -e "s|__ROOT__|$PWD|g" -e "s|__PIXI__|$PIXI|g" -e "s|__LOG__|$LOG|g" -e "s|__KB__|$KB_REF|g" \
  examples/launchd/$LABEL.plist >"$DEST"
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $LABEL → daily 22:00, log: $LOG"
echo "run now: launchctl kickstart gui/$(id -u)/$LABEL"
