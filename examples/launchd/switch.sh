#!/usr/bin/env bash
# Phase 9: move the owner's live launchd setup from the old thesis-kb monorepo to kb-distillery.
#   1. back up every old com.thesis-kb.* plist (and any current com.kb-distillery.* plist) to a
#      timestamped dir under ~/Library/LaunchAgents/.kb-distillery-backup/, with a loaded-state manifest
#   2. unload + remove the old com.thesis-kb.* agents
#   3. install the com.kb-distillery.* agents by running install.sh and install-deploy-owner.sh
#   4. verify with launchctl
# Usage: bash examples/launchd/switch.sh [--dry-run | --rollback [--dry-run]]
#   --dry-run   print every action, change nothing (use this first)
#   --rollback  undo: unload + remove the com.kb-distillery.* agents, restore the newest backup, reload
# Idempotent: re-running with nothing left to move only reinstalls and re-verifies.
# This script never deploys, shares, or touches Cloudflare; the deploy owner it installs does that later.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
BACKUP_ROOT="$AGENTS/.kb-distillery-backup"
GUI="gui/$(id -u)"
OLD_PREFIX="com.thesis-kb."
NEW_LABELS=(com.kb-distillery.daily-sync com.kb-distillery.deploy-owner)

DRY=0
ROLLBACK=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --rollback) ROLLBACK=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (use --dry-run, --rollback)" >&2; exit 2 ;;
  esac
done

say() { echo "$*"; }
# run CMD... — print it; execute unless --dry-run
run() {
  if ((DRY)); then say "[dry-run] $*"; else say "+ $*"; "$@"; fi
}
is_loaded() { launchctl print "$GUI/$1" >/dev/null 2>&1; }
# unload LABEL — bootout if loaded (tolerates not loaded)
unload() {
  if ((DRY)); then say "[dry-run] launchctl bootout $GUI/$1  (if loaded)"
  else say "+ launchctl bootout $GUI/$1"; launchctl bootout "$GUI/$1" 2>/dev/null || true; fi
}
# load PLIST LABEL — enable (the old state may be disabled) then bootstrap
load() {
  if ((DRY)); then
    say "[dry-run] launchctl enable $GUI/$2"
    say "[dry-run] launchctl bootstrap $GUI $1"
  else
    say "+ launchctl bootstrap $GUI $1"
    launchctl enable "$GUI/$2" 2>/dev/null || true
    launchctl bootstrap "$GUI" "$1"
  fi
}

shopt -s nullglob
((DRY)) && say "DRY RUN: nothing will be changed. HOME=$HOME"

if ((ROLLBACK)); then
  backups=("$BACKUP_ROOT"/*/)
  if ((${#backups[@]} == 0)); then
    say "rollback: no backup under $BACKUP_ROOT, nothing to restore" >&2
    exit 1
  fi
  bdir="${backups[${#backups[@]} - 1]%/}"   # timestamped names sort oldest -> newest
  say "rollback: restoring from $bdir"
  for label in "${NEW_LABELS[@]}"; do
    unload "$label"
    if [[ -e "$AGENTS/$label.plist" ]]; then run rm -f "$AGENTS/$label.plist"; else say "skip: $label.plist not installed"; fi
  done
  for plist in "$bdir"/*.plist; do
    label="$(basename "$plist" .plist)"
    run cp -p "$plist" "$AGENTS/$label.plist"
    # reload what was loaded at switch time; with no manifest, reload the old thesis-kb agents only
    if [[ -f "$bdir/loaded.txt" ]]; then want=0; grep -qxF "$label" "$bdir/loaded.txt" && want=1
    else want=0; [[ "$label" == "$OLD_PREFIX"* ]] && want=1; fi
    if ((want)); then unload "$label"; load "$AGENTS/$label.plist" "$label"
    else say "restored but left unloaded (was not loaded before): $label"; fi
  done
  if ((DRY)); then say "[dry-run] launchctl print $GUI/<label>  (verify each reloaded agent)"
  else
    for plist in "$bdir"/*.plist; do
      label="$(basename "$plist" .plist)"
      if [[ -f "$bdir/loaded.txt" ]] && grep -qxF "$label" "$bdir/loaded.txt" || { [[ ! -f "$bdir/loaded.txt" ]] && [[ "$label" == "$OLD_PREFIX"* ]]; }; then
        is_loaded "$label" && say "ok: $label loaded" || { say "FAIL: $label not loaded" >&2; exit 1; }
      fi
    done
  fi
  say "rollback done. Also run: pixi run share -- rollback  (if a new Worker version went out)"
  exit 0
fi

# ---- forward switch -------------------------------------------------------------------------
old=("$AGENTS/$OLD_PREFIX"*.plist)
existing_new=()
for label in "${NEW_LABELS[@]}"; do [[ -e "$AGENTS/$label.plist" ]] && existing_new+=("$AGENTS/$label.plist"); done
tobackup=(${old[@]+"${old[@]}"} ${existing_new[@]+"${existing_new[@]}"})

if ((${#tobackup[@]})); then
  stamp="$(date +%Y%m%d-%H%M%S)"
  bdir="$BACKUP_ROOT/$stamp"
  say "backup: ${#tobackup[@]} plist(s) -> $bdir"
  run mkdir -p "$bdir"
  loaded=()
  for plist in "${tobackup[@]}"; do
    label="$(basename "$plist" .plist)"
    run cp -p "$plist" "$bdir/$label.plist"
    if ((DRY)); then say "[dry-run] record whether $label is loaded"
    elif is_loaded "$label"; then loaded+=("$label"); fi
  done
  if ((DRY)); then say "[dry-run] write $bdir/loaded.txt"
  else
    : >"$bdir/loaded.txt"
    for l in ${loaded[@]+"${loaded[@]}"}; do echo "$l" >>"$bdir/loaded.txt"; done
  fi
else
  say "backup: no old $OLD_PREFIX* plists and no current kb-distillery plists, nothing to back up"
fi

if ((${#old[@]})); then
  for plist in "${old[@]}"; do
    label="$(basename "$plist" .plist)"
    unload "$label"
    run rm -f "$plist"
  done
else
  say "remove: no $OLD_PREFIX* agents in $AGENTS (already switched)"
fi

# install.sh / install-deploy-owner.sh render the plist templates, bootout + bootstrap (idempotent),
# and also clear the pre-rename labels themselves.
for label in "${NEW_LABELS[@]}"; do
  if ((DRY)); then say "[dry-run] launchctl enable $GUI/$label  (a previously disabled agent would refuse to load)"
  else launchctl enable "$GUI/$label" 2>/dev/null || true; fi
done
run bash "$HERE/install.sh"
run bash "$HERE/install-deploy-owner.sh"

if ((DRY)); then
  for label in "${NEW_LABELS[@]}"; do say "[dry-run] launchctl print $GUI/$label  (verify loaded)"; done
  say "[dry-run] verify no $OLD_PREFIX* agent remains in $AGENTS or launchctl"
  say "DRY RUN complete: nothing changed."
  exit 0
fi

fail=0
for label in "${NEW_LABELS[@]}"; do
  if is_loaded "$label"; then say "ok: $label loaded"; else say "FAIL: $label not loaded" >&2; fail=1; fi
done
for plist in "$AGENTS/$OLD_PREFIX"*.plist; do say "FAIL: old plist still present: $plist" >&2; fail=1; done
if launchctl list | awk '{print $3}' | grep -q "^$OLD_PREFIX"; then say "FAIL: an old $OLD_PREFIX* agent is still loaded" >&2; fail=1; fi
((fail == 0)) || exit 1
say "switched. Rollback: bash examples/launchd/switch.sh --rollback"
