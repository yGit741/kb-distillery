#!/bin/bash
# Block ad-hoc agent git/gh writes; allow only the lane entry points.
# Logic lives in meta/git_guard.py (tested by meta/test_git_guard.py).
# Shared by Cursor (beforeShellExecution) and Claude Code (PreToolUse Bash).
root="$(cd "$(dirname "$0")/../.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "git guard: python3 not found — refusing (fail closed)" >&2
  exit 2
fi
exec python3 "$root/meta/git_guard.py"
