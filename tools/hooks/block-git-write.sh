#!/bin/bash
# Block ad-hoc agent git/gh writes; allow only the lane entry points.
# Logic lives in backend/src/kb/git/git_guard.py (tested by backend/tests/git/test_git_guard.py).
# Wired by Claude Code (PreToolUse Bash, .claude/settings.json).
root="$(cd "$(dirname "$0")/../.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "git guard: python3 not found — refusing (fail closed)" >&2
  exit 2
fi
py="$root/.pixi/envs/default/bin/python"; [ -x "$py" ] || py=python3
PYTHONPATH="$root/backend/src${PYTHONPATH:+:$PYTHONPATH}" exec "$py" -m kb.git.git_guard
