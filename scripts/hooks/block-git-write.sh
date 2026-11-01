#!/bin/bash
# Block ad-hoc agent git/gh writes; allow only the lane entry points.
# Logic lives in src/kb_distillery/git/git_guard.py (tested by tests/git/test_git_guard.py).
# Wired by Claude Code (PreToolUse Bash, .claude/settings.json).
root="$(cd "$(dirname "$0")/../.." && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "git guard: python3 not found — refusing (fail closed)" >&2
  exit 2
fi
py="$root/.pixi/envs/default/bin/python"; [ -x "$py" ] || py=python3
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec "$py" -m kb_distillery.git.git_guard
