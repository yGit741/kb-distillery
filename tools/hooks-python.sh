#!/bin/bash
# Forwarding stub (removed in Phase 9): older settings.json copies and worktrees still name tools/hooks-python.sh and the module kb.*.
mod="${1:-}"; shift || true
case "$mod" in kb.*) mod="kb_distillery.${mod#kb.}";; esac
exec bash "$(dirname "$0")/../scripts/hooks-python.sh" "$mod" "$@"
