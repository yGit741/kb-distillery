#!/usr/bin/env bash
# Install (or reinstall) the deploy owner (kb.share.owner run) as a user launchd agent: KeepAlive,
# the one process that builds + deploys main to the private site. Everything else only nudges it.
# Usage: pixi run install-deploy-owner            uninstall: pixi run install-deploy-owner -- --uninstall
set -euo pipefail

cd "$(dirname "$0")/../.."
LABEL=com.thesis-kb.deploy-owner
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/thesis-kb-deploy-owner.log"
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
echo "installed $LABEL → always on, log: $LOG"
echo "state: pixi run python -m kb.share.owner status"
