#!/bin/bash
# Block ad-hoc agent git/gh writes; allow only the lane entry points.
# Logic lives in src/kb_distillery/git/git_guard.py (tested by tests/git/test_git_guard.py).
# Wired by Claude Code (PreToolUse Bash, .claude/settings.json). hooks-python.sh exits 2 when the module cannot import.
exec bash "$(dirname "$0")/../hooks-python.sh" kb_distillery.git.git_guard
