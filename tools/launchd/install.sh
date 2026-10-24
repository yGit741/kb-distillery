#!/usr/bin/env bash
# Install (or reinstall) the nightly knowledge-lane sync as a user launchd agent.
# Runs `pixi run daily-sync` at 22:00 local; a run missed while asleep fires on wake.
# Usage: pixi run install-sync            uninstall: pixi run install-sync -- --uninstall
set -euo pipefail

cd "$(dirname "$0")/../.."
LABEL=com.thesis-kb.daily-sync
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/thesis-kb-daily-sync.log"
PIXI="$(command -v pixi || echo "$HOME/.pixi/bin/pixi")"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$DEST"
  echo "uninstalled $LABEL"
  exit 0
fi

mkdir -p "$(dirname "$DEST")" "$(dirname "$LOG")"
sed -e "s|__ROOT__|$PWD|g" -e "s|__PIXI__|$PIXI|g" -e "s|__LOG__|$LOG|g" \
  tools/launchd/$LABEL.plist >"$DEST"
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "installed $LABEL → daily 22:00, log: $LOG"
echo "run now: launchctl kickstart gui/$(id -u)/$LABEL"
